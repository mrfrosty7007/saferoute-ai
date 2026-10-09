"""
SafeRouteAI - Phase 3: Risk-Aware Routing Engine
Author: SafeRouteAI Team

Features:
1. Prepares the routing graph:
   - Extracts the largest strongly connected component (SCC) to ensure full reachability.
   - Collapses multi-directed edges to the single minimum-cost directed edge per (u, v).
   - Builds a metric cKDTree for instant geographic coordinate snapping.
2. Evaluates hydrodynamic edge travel time:
   - Base speed: 30 km/h (or edge maxspeed if present).
   - Water slowdown: speed_factor = 1.0 - 0.5 * min(1.0, depth_cm / safe_depth_cm).
3. Evaluates additive log-risk Dijkstra routing cost:
   - cost_s = time_s + lambda * (-ln(max(p, 1e-6))).
4. Solves three distinct route types:
   - Primary Route: Optimal risk-penalized travel time path.
   - Backup Route: Re-routed path penalizing primary route's riskiest segments (p < 0.95) by 10x
     (or all primary segments by 3x if identical).
   - Baseline Route: Conventional shortest geometric distance path.
5. Computes numerically stable end-to-end reliability (product of segment pass probabilities)
   and identifies the weakest segment (lowest p).
"""

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import networkx as nx
import numpy as np
from scipy.spatial import cKDTree

from .config import (
    BACKUP_PENALTY_ALL,
    BACKUP_PENALTY_RISKY,
    CENTER_LAT,
    CENTER_LON,
    DEFAULT_LAMBDA,
    DEFAULT_SPEED_KMH,
    LAMBDA_RISK,
    MAX_SPEED_WATER_PENALTY,
    METERS_PER_DEG_LAT,
    METERS_PER_DEG_LON,
    PROBABILITY_EPSILON,
    RISKY_EDGE_P_THRESHOLD,
    VEHICLES,
)
from .risk import passability


@dataclass
class SegmentInfo:
    """Represents a single directed road segment in a route."""
    u: int
    v: int
    length_m: float
    time_s: float
    depth_cm: float
    pass_probability: float
    cost: float


@dataclass
class RouteResult:
    """Represents the complete result of a routing query."""
    route_type: str                   # 'primary', 'backup', or 'baseline'
    vehicle: str                      # Vehicle identifier
    origin_node: int
    destination_node: int
    nodes: List[int]                  # Sequence of node IDs
    segments: List[SegmentInfo]       # Detailed segment statistics
    eta_min: float                    # Total travel time in minutes
    distance_km: float                # Total distance in kilometers
    reliability: float                # Multiplicative end-to-end pass probability in [0, 1]
    weakest_segment: Optional[Tuple[int, int, float]]  # (u, v, lowest_p)
    has_impassable: bool              # True if any segment has p < 0.5
    overlap_with_primary: float = 0.0 # Fraction of edges overlapping with primary route [0, 1]
    is_fallback_backup: bool = False  # True if backup used all-edges penalty multiplier

    def to_dict(self) -> Dict[str, Any]:
        """Convert route result to a serializable dictionary."""
        d = asdict(self)
        return d


class RoutingEngine:
    """
    High-performance risk-aware routing engine for SafeRouteAI.
    Operates on a condensed, strongly connected directed graph.
    """

    def __init__(
        self,
        G_enriched: nx.MultiDiGraph,
        vehicle: str,
        lambda_val: float = DEFAULT_LAMBDA,
    ):
        """
        Initialize the routing engine with an enriched multi-graph.

        Args:
            G_enriched: Road network graph with 'pass_probability' and 'water_depth_cm' edge attributes.
            vehicle: Emergency vehicle identifier ('ambulance', 'fire_tender', 'rescue_truck').
            lambda_val: Risk sensitivity weight in seconds per unit of negative log-risk.
        """
        if vehicle not in VEHICLES:
            raise ValueError(f"Unknown vehicle '{vehicle}'. Must be one of: {list(VEHICLES.keys())}")

        self.vehicle = vehicle
        self.safe_depth_cm = VEHICLES[vehicle]
        self.lambda_val = float(lambda_val)

        # 1. Extract largest strongly connected component
        scc_nodes = max(nx.strongly_connected_components(G_enriched), key=len)
        self.G_scc_raw = G_enriched.subgraph(scc_nodes).copy()

        # 2. Build condensed DiGraph collapsing parallel edges
        self.graph = self._build_condensed_digraph(self.G_scc_raw)

        # 3. Build spatial index for coordinate snapping
        self._build_node_spatial_index()

    def _build_condensed_digraph(self, G_scc: nx.MultiDiGraph) -> nx.DiGraph:
        """
        Collapse parallel edges to the single cheapest directed edge per (u, v).
        Precomputes base travel time, hydrodynamic slowdown, and additive log-risk cost.
        """
        G_di = nx.DiGraph()

        # Copy node attributes
        for n, d in G_scc.nodes(data=True):
            G_di.add_node(n, x=float(d["x"]), y=float(d["y"]), elevation=float(d.get("elevation", 0.0)))

        # Evaluate and collapse edges
        prob_attr = f"pass_probability_{self.vehicle}"

        for u, v, k, data in G_scc.edges(keys=True, data=True):
            length_m = float(data.get("length", 10.0))
            depth_cm = float(data.get("water_depth_cm", 0.0))

            # Retrieve pass probability
            p = float(data.get(prob_attr, data.get("pass_probability", 1.0)))
            p = max(PROBABILITY_EPSILON, min(1.0, p))

            # Travel speed and hydrodynamic slowdown
            base_speed_kmh = DEFAULT_SPEED_KMH
            if "maxspeed" in data and data["maxspeed"] is not None:
                try:
                    ms_val = data["maxspeed"]
                    if isinstance(ms_val, list):
                        ms_val = ms_val[0]
                    base_speed_kmh = float(str(ms_val).split()[0])
                except Exception:
                    base_speed_kmh = DEFAULT_SPEED_KMH

            # Slowdown formula: speed_factor = 1.0 - 0.5 * min(1.0, depth_cm / safe_depth_cm)
            depth_ratio = min(1.0, max(0.0, depth_cm / self.safe_depth_cm))
            speed_factor = 1.0 - (MAX_SPEED_WATER_PENALTY * depth_ratio)
            effective_speed_mps = max(0.5, (base_speed_kmh / 3.6) * speed_factor)

            time_s = length_m / effective_speed_mps

            # Additive cost: time_s + lambda * (-ln(max(p, 1e-6)))
            risk_penalty_s = self.lambda_val * (-math.log(p))
            cost_s = time_s + risk_penalty_s

            edge_attrs = {
                "length": length_m,
                "depth_cm": depth_cm,
                "pass_probability": p,
                "speed_mps": effective_speed_mps,
                "time_s": time_s,
                "risk_penalty_s": risk_penalty_s,
                "cost": cost_s,
                "original_key": k,
            }

            # Select the cheapest edge for parallel pairs (u, v)
            if not G_di.has_edge(u, v):
                G_di.add_edge(u, v, **edge_attrs)
            else:
                if cost_s < G_di[u][v]["cost"]:
                    G_di.add_edge(u, v, **edge_attrs)

        return G_di

    def _build_node_spatial_index(self) -> None:
        """Build a metric cKDTree for nearest-node geographic snapping."""
        self.node_ids = list(self.graph.nodes())
        coords_m = []

        for n in self.node_ids:
            x_deg = self.graph.nodes[n]["x"]
            y_deg = self.graph.nodes[n]["y"]
            x_m = (x_deg - CENTER_LON) * METERS_PER_DEG_LON
            y_m = (y_deg - CENTER_LAT) * METERS_PER_DEG_LAT
            coords_m.append((x_m, y_m))

        self.coords_m = np.array(coords_m)
        self.kdtree = cKDTree(self.coords_m)

    def snap_to_nearest_node(self, lat: float, lon: float) -> int:
        """
        Find the nearest network node in the SCC to a given (lat, lon) coordinate.

        Args:
            lat: Latitude in degrees.
            lon: Longitude in degrees.

        Returns:
            Nearest node ID in the graph.
        """
        target_x_m = (lon - CENTER_LON) * METERS_PER_DEG_LON
        target_y_m = (lat - CENTER_LAT) * METERS_PER_DEG_LAT
        _, idx = self.kdtree.query((target_x_m, target_y_m))
        return self.node_ids[idx]

    def _compile_route_result(
        self,
        G_used: nx.DiGraph,
        nodes: List[int],
        route_type: str,
        primary_edges: Optional[Set[Tuple[int, int]]] = None,
        is_fallback_backup: bool = False,
    ) -> RouteResult:
        """Compile detailed segment-by-segment stats and metrics for a sequence of nodes."""
        if len(nodes) < 2:
            raise ValueError("Route must contain at least 2 nodes.")

        segments: List[SegmentInfo] = []
        total_time_s = 0.0
        total_distance_m = 0.0
        log_prob_sum = 0.0
        lowest_p = 1.0
        weakest_seg: Optional[Tuple[int, int, float]] = None
        has_impassable = False

        for u, v in zip(nodes[:-1], nodes[1:]):
            if not G_used.has_edge(u, v):
                raise ValueError(f"Edge ({u}, {v}) does not exist in graph.")

            edata = G_used[u][v]
            length_m = edata["length"]
            time_s = edata["time_s"]
            depth_cm = edata["depth_cm"]
            p = edata["pass_probability"]
            cost = edata.get("cost", length_m)

            segments.append(
                SegmentInfo(
                    u=u,
                    v=v,
                    length_m=length_m,
                    time_s=time_s,
                    depth_cm=depth_cm,
                    pass_probability=p,
                    cost=cost,
                )
            )

            total_time_s += time_s
            total_distance_m += length_m
            log_prob_sum += math.log(max(PROBABILITY_EPSILON, p))

            if p < lowest_p:
                lowest_p = p
                weakest_seg = (u, v, p)

            if p < 0.5:
                has_impassable = True

        # Numerically stable reliability: exp(sum(log(p)))
        reliability = math.exp(max(-50.0, log_prob_sum))

        # Overlap with primary edges
        overlap = 0.0
        if primary_edges is not None and len(primary_edges) > 0:
            current_edges = set(zip(nodes[:-1], nodes[1:]))
            common = current_edges.intersection(primary_edges)
            overlap = len(common) / len(primary_edges)

        return RouteResult(
            route_type=route_type,
            vehicle=self.vehicle,
            origin_node=nodes[0],
            destination_node=nodes[-1],
            nodes=nodes,
            segments=segments,
            eta_min=total_time_s / 60.0,
            distance_km=total_distance_m / 1000.0,
            reliability=reliability,
            weakest_segment=weakest_seg,
            has_impassable=has_impassable,
            overlap_with_primary=overlap,
            is_fallback_backup=is_fallback_backup,
        )

    def route_primary(self, source: int, target: int) -> RouteResult:
        """
        Compute the primary risk-minimized route using Dijkstra's algorithm.

        Args:
            source: Origin node ID.
            target: Destination node ID.

        Returns:
            RouteResult for the primary route.
        """
        if source not in self.graph:
            raise ValueError(f"Source node {source} not in graph.")
        if target not in self.graph:
            raise ValueError(f"Target node {target} not in graph.")

        nodes = nx.shortest_path(self.graph, source=source, target=target, weight="cost")
        return self._compile_route_result(self.graph, nodes, route_type="primary")

    def route_backup(self, source: int, target: int, primary_result: RouteResult) -> RouteResult:
        """
        Compute an independent backup route:
        1. Identifies primary edges with pass_probability < 0.95.
        2. Penalizes their cost by 10x on a graph copy and reruns Dijkstra.
        3. If no risky edges exist or result matches primary, penalizes all primary edges by 3x.
        4. If still identical, reports the primary route with overlap=1.0.

        Args:
            source: Origin node ID.
            target: Destination node ID.
            primary_result: Previously computed primary RouteResult.

        Returns:
            RouteResult for the backup route.
        """
        primary_nodes = primary_result.nodes
        primary_edges = set(zip(primary_nodes[:-1], primary_nodes[1:]))

        # Copy graph for penalized pathfinding
        G_backup = self.graph.copy()

        # Identify risky edges on primary route (p < 0.95)
        risky_edges = [
            (u, v) for u, v in primary_edges
            if G_backup[u][v]["pass_probability"] < RISKY_EDGE_P_THRESHOLD
        ]

        is_fallback = False
        if risky_edges:
            # Penalize risky primary edges by 10x
            for u, v in risky_edges:
                G_backup[u][v]["cost"] = G_backup[u][v]["cost"] * BACKUP_PENALTY_RISKY

            try:
                candidate_nodes = nx.shortest_path(G_backup, source=source, target=target, weight="cost")
            except nx.NetworkXNoPath:
                candidate_nodes = primary_nodes

            # Check if candidate differs from primary
            if candidate_nodes == primary_nodes:
                is_fallback = True
        else:
            is_fallback = True

        # Fallback: penalize ALL primary edges by 3x to find an alternate corridor
        if is_fallback:
            G_backup_all = self.graph.copy()
            for u, v in primary_edges:
                G_backup_all[u][v]["cost"] = G_backup_all[u][v]["cost"] * BACKUP_PENALTY_ALL

            try:
                candidate_nodes = nx.shortest_path(G_backup_all, source=source, target=target, weight="cost")
            except nx.NetworkXNoPath:
                candidate_nodes = primary_nodes

        return self._compile_route_result(
            self.graph,  # Evaluate actual unpenalized travel times and costs on base graph
            candidate_nodes,
            route_type="backup",
            primary_edges=primary_edges,
            is_fallback_backup=is_fallback,
        )

    def route_baseline(self, source: int, target: int) -> RouteResult:
        """
        Compute the conventional shortest geometric distance baseline.

        Args:
            source: Origin node ID.
            target: Destination node ID.

        Returns:
            RouteResult for the baseline shortest path.
        """
        if source not in self.graph:
            raise ValueError(f"Source node {source} not in graph.")
        if target not in self.graph:
            raise ValueError(f"Target node {target} not in graph.")

        nodes = nx.shortest_path(self.graph, source=source, target=target, weight="length")
        return self._compile_route_result(self.graph, nodes, route_type="baseline")

    def route_all(self, source: int, target: int) -> Dict[str, RouteResult]:
        """
        Convenience method to compute primary, backup, and baseline routes simultaneously.

        Args:
            source: Origin node ID.
            target: Destination node ID.

        Returns:
            Dictionary with keys 'primary', 'backup', 'baseline'.
        """
        primary = self.route_primary(source, target)
        backup = self.route_backup(source, target, primary)
        baseline = self.route_baseline(source, target)

        return {
            "primary": primary,
            "backup": backup,
            "baseline": baseline,
        }


def create_routing_engine(
    G_base: nx.MultiDiGraph,
    vehicle: str,
    rainfall_mm_hr: float,
    river_level_m: float,
    depressions: Optional[Dict[Tuple[int, int, int], float]] = None,
    lambda_val: float = DEFAULT_LAMBDA,
) -> RoutingEngine:
    """
    Factory function: Enriches G_base under given flood conditions and returns a RoutingEngine.

    Args:
        G_base: Road network graph.
        vehicle: Vehicle identifier.
        rainfall_mm_hr: Rainfall intensity in mm/hr.
        river_level_m: Regional river stage in meters.
        depressions: Precomputed edge depressions dictionary.
        lambda_val: Risk sensitivity weight.

    Returns:
        Configured RoutingEngine instance.
    """
    G_enriched = passability(
        G=G_base,
        vehicle=vehicle,
        rainfall=rainfall_mm_hr,
        river_level=river_level_m,
        depressions=depressions,
    )
    return RoutingEngine(G_enriched, vehicle=vehicle, lambda_val=lambda_val)
