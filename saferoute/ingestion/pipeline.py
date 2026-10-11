"""
Rakshapath - Regional Ingestion Pipeline
Author: Rakshapath Team

Reproducible workflow for obtaining, validating, and preparing OpenStreetMap
road networks and elevation data for any regional study area across India.
"""
from __future__ import annotations

import json
import math
import os
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import networkx as nx
import osmnx as ox

from saferoute.regions.models import BoundingBox, RegionMetadata, RegionStatus
from saferoute.risk import precompute_depressions

# Global OSMnx timeout and user agent
USER_AGENT = "Rakshapath-Research/1.0 (admin@rakshapath.in)"
ox.settings.overpass_rate_limit = False
ox.settings.requests_timeout = 60
ox.settings.use_cache = True
ox.settings.user_agent = USER_AGENT


class IngestionError(Exception):
    """Raised when regional ingestion fails validation."""


class RegionIngestionPipeline:
    """
    Standardized ingestion pipeline for regional road networks and hazard assets.
    """

    def __init__(self, data_root: Optional[str] = None):
        if data_root is None:
            data_root = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "data",
            )
        self.data_root = data_root

    def validate_raw_network(self, G: nx.MultiDiGraph, region_name: str) -> None:
        """Defensive validation on extracted road graph."""
        if G is None or G.number_of_nodes() == 0:
            raise IngestionError(f"Extracted road network for '{region_name}' is empty (0 nodes).")
        if G.number_of_nodes() < 20:
            raise IngestionError(
                f"Extracted road network for '{region_name}' has only {G.number_of_nodes()} nodes (minimum 20 required)."
            )
        if G.number_of_nodes() > 60_000:
            raise IngestionError(
                f"Extracted network for '{region_name}' has {G.number_of_nodes()} nodes, exceeding memory safety bound of 60,000."
            )

    def extract_strongly_connected_component(self, G: nx.MultiDiGraph) -> Tuple[nx.MultiDiGraph, int]:
        """Extract the largest SCC to guarantee routability across all included nodes."""
        scc_nodes = max(nx.strongly_connected_components(G), key=len)
        removed_nodes = G.number_of_nodes() - len(scc_nodes)
        G_scc = G.subgraph(scc_nodes).copy()
        return G_scc, removed_nodes

    def fill_and_validate_elevations(
        self,
        G: nx.MultiDiGraph,
        elev_dict: Optional[Dict[Any, Optional[float]]] = None,
        default_elev_m: float = 50.0,
    ) -> int:
        """
        Assign node elevations and fill missing/null values via topological neighbor averaging.
        """
        elev_dict = elev_dict or {}
        null_nodes = set()

        for n, d in G.nodes(data=True):
            # A numeric zero is valid terrain elevation. Resolve keys by presence,
            # then recognize only explicit missing markers before falling back.
            if n in elev_dict:
                val = elev_dict[n]
            elif str(n) in elev_dict:
                val = elev_dict[str(n)]
            else:
                val = None
            if self._is_missing_elevation(val):
                val = d.get("elevation")
            if self._is_missing_elevation(val):
                null_nodes.add(n)
                G.nodes[n]["elevation"] = None
            else:
                try:
                    G.nodes[n]["elevation"] = float(val)
                except (TypeError, ValueError) as exc:
                    raise IngestionError(f"Invalid elevation value {val!r} for node {n!r}.") from exc

        filled_count = len(null_nodes)
        if filled_count > 0:
            remaining = set(null_nodes)
            passes = 0
            while remaining and passes < 15:
                passes += 1
                resolved = {}
                for n in remaining:
                    neighbors = set(G.predecessors(n)).union(set(G.successors(n)))
                    valid_elevs = [
                        G.nodes[nbr]["elevation"]
                        for nbr in neighbors
                        if G.nodes[nbr].get("elevation") is not None
                    ]
                    if valid_elevs:
                        resolved[n] = sum(valid_elevs) / len(valid_elevs)

                if not resolved:
                    break
                for n, val in resolved.items():
                    G.nodes[n]["elevation"] = val
                    remaining.remove(n)

            # Global mean or default fallback for isolated nodes
            valid_all = [
                G.nodes[n]["elevation"]
                for n in G.nodes()
                if G.nodes[n].get("elevation") is not None
            ]
            fallback = sum(valid_all) / len(valid_all) if valid_all else default_elev_m
            for n in remaining:
                G.nodes[n]["elevation"] = fallback

        # Calculate edge elev_min
        for u, v, k, d in G.edges(keys=True, data=True):
            e_u = float(G.nodes[u].get("elevation", default_elev_m))
            e_v = float(G.nodes[v].get("elevation", default_elev_m))
            d["elev_min"] = float(min(e_u, e_v))

        return filled_count

    @staticmethod
    def _is_missing_elevation(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str) and value.strip().lower() in {"", "nan", "none", "null"}:
            return True
        try:
            return not math.isfinite(float(value))
        except (TypeError, ValueError, OverflowError):
            return False

    def generate_region_metadata(
        self,
        region: RegionMetadata,
        G: nx.MultiDiGraph,
        filled_nulls: int,
        disconnected_removed: int,
        duration_sec: float,
    ) -> Dict[str, Any]:
        """Compile a comprehensive JSON metadata summary for the ingested region."""
        elevs = [float(G.nodes[n]["elevation"]) for n in G.nodes()]
        bridge_count = sum(1 for _, _, _, d in G.edges(keys=True, data=True) if d.get("bridge"))
        tunnel_count = sum(1 for _, _, _, d in G.edges(keys=True, data=True) if d.get("tunnel"))

        lats = [float(G.nodes[n]["y"]) for n in G.nodes()]
        lons = [float(G.nodes[n]["x"]) for n in G.nodes()]

        actual_bounds = {
            "min_lat": min(lats) if lats else region.bounds.min_lat,
            "max_lat": max(lats) if lats else region.bounds.max_lat,
            "min_lon": min(lons) if lons else region.bounds.min_lon,
            "max_lon": max(lons) if lons else region.bounds.max_lon,
        }

        return {
            "region_id": region.region_id,
            "display_name": region.display_name,
            "state": region.state,
            "district": region.district,
            "city": region.city,
            "ingestion_timestamp": time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime()),
            "ingestion_duration_sec": round(duration_sec, 2),
            "node_count": G.number_of_nodes(),
            "edge_count": G.number_of_edges(),
            "disconnected_nodes_removed": disconnected_removed,
            "elevation_nulls_filled": filled_nulls,
            "elevation_min_m": round(min(elevs), 1) if elevs else 0.0,
            "elevation_max_m": round(max(elevs), 1) if elevs else 0.0,
            "elevation_mean_m": round(sum(elevs) / len(elevs), 1) if elevs else 0.0,
            "bridge_edges": bridge_count,
            "tunnel_edges": tunnel_count,
            "actual_bounds": actual_bounds,
            "data_provenance": "OpenStreetMap contributors via OSMnx",
            "attribution": "Map data © OpenStreetMap contributors, ODbL 1.0",
        }

    def process_and_save(
        self,
        region: RegionMetadata,
        G_raw: nx.MultiDiGraph,
        elev_dict: Optional[Dict[Any, Optional[float]]] = None,
        output_dir: Optional[str] = None,
        default_elev_m: float = 50.0,
    ) -> Tuple[str, str, str]:
        """
        Process raw graph: validate, extract SCC, fill elevations, precompute depressions,
        and write artifacts (graph.graphml, depressions.pkl, metadata.json).
        """
        t0 = time.time()
        self.validate_raw_network(G_raw, region.display_name)

        # 1. Extract SCC
        G_scc, removed_nodes = self.extract_strongly_connected_component(G_raw)

        # 2. Enrich and validate elevations
        filled_nulls = self.fill_and_validate_elevations(G_scc, elev_dict, default_elev_m=default_elev_m)

        # 3. Determine target directory
        if output_dir is None:
            output_dir = os.path.join(self.data_root, "regions", region.region_id)
        os.makedirs(output_dir, exist_ok=True)

        graph_path = os.path.join(output_dir, "graph.graphml")
        depressions_path = os.path.join(output_dir, "depressions.pkl")
        metadata_path = os.path.join(output_dir, "metadata.json")

        # 4. Precompute depressions
        depressions = precompute_depressions(
            G_scc,
            radius_m=300.0,
            cache_path=depressions_path,
            center_lat=region.center_lat,
            center_lon=region.center_lon,
        )

        # 5. Save GraphML with guaranteed float dtypes
        ox.save_graphml(G_scc, graph_path)

        # 6. Generate and save metadata
        meta = self.generate_region_metadata(
            region=region,
            G=G_scc,
            filled_nulls=filled_nulls,
            disconnected_removed=removed_nodes,
            duration_sec=time.time() - t0,
        )
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        return graph_path, depressions_path, metadata_path
