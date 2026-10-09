"""
SafeRouteAI - Phase 1 Data Ingestion & Elevation Enrichment
Author: SafeRouteAI Team

Responsible for downloading the drivable road network via OSMnx, querying
OpenTopoData SRTM elevation APIs in polite rate-limited batches, filling
null elevations via topological neighbor averaging, assigning elev_min
attributes to edges, and managing persistent GraphML caching.
"""

import glob
import json
import math
import os
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import networkx as nx
import osmnx as ox
import requests

from .config import (
    API_BATCH_SIZE,
    API_MAX_RETRIES,
    API_REQUEST_DELAY_SEC,
    API_TIMEOUT_SEC,
    CENTER_LAT,
    CENTER_LON,
    DATA_DIR,
    EARTH_RADIUS_METERS,
    ELEVATIONS_CACHE_FILE,
    GRAPH_FILE,
    METERS_PER_DEG_LAT,
    METERS_PER_DEG_LON,
    NETWORK_TYPE,
    OPENTOPO_SRTM30_URL,
    OPENTOPO_SRTM90_URL,
    OSMNX_TIMEOUT_SEC,
    PLACE_NAME,
    RADIUS_METERS,
    USER_AGENT,
)

# Configure global OSMnx settings
ox.settings.overpass_rate_limit = False
ox.settings.requests_timeout = OSMNX_TIMEOUT_SEC
ox.settings.use_cache = True
ox.settings.user_agent = USER_AGENT


def ensure_data_dir() -> None:
    """Ensure that the local data directory exists."""
    os.makedirs(DATA_DIR, exist_ok=True)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two geographic coordinates in meters.

    Args:
        lat1: Latitude of point 1 in degrees.
        lon1: Longitude of point 1 in degrees.
        lat2: Latitude of point 2 in degrees.
        lon2: Longitude of point 2 in degrees.

    Returns:
        Distance in meters.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_METERS * c


def fetch_road_network() -> nx.MultiDiGraph:
    """
    Load the drivable road network within RADIUS_METERS of PLACE_NAME.
    Checks existing local Overpass cache first, then attempts direct query,
    with an automated bounding-box plus circular distance filter fallback.

    Returns:
        Simplified networkx.MultiDiGraph road network.
    """
    print(f"Loading road network for '{PLACE_NAME}' (radius: {RADIUS_METERS}m)...", flush=True)

    # 1. Check local Overpass response cache
    cache_files = glob.glob("cache/*.json")
    for cf in cache_files:
        if os.path.getsize(cf) > 500_000:
            try:
                print(f"  Found cached OSM Overpass data in {cf}, loading graph...", flush=True)
                with open(cf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                G_raw = ox.graph._create_graph([data], False)
                G_simple = ox.simplification.simplify_graph(G_raw)

                nodes_in_circle = [
                    n for n, d in G_simple.nodes(data=True)
                    if haversine_distance(CENTER_LAT, CENTER_LON, d["y"], d["x"]) <= RADIUS_METERS
                ]
                G = G_simple.subgraph(nodes_in_circle).copy()
                print(f"  Loaded from cache: {len(G.nodes()):,} nodes, {len(G.edges()):,} edges.", flush=True)
                return G
            except Exception as e:
                print(f"  Could not load from {cf}: {e}", flush=True)

    # 2. Try direct ox.graph_from_address
    try:
        G = ox.graph_from_address(PLACE_NAME, dist=RADIUS_METERS, network_type=NETWORK_TYPE)
        print(f"  Loaded via graph_from_address: {len(G.nodes()):,} nodes, {len(G.edges()):,} edges.", flush=True)
        return G
    except Exception as e:
        print(f"  Notice: Direct graph_from_address query timed out ({e}).", flush=True)

    # 3. Fallback: Geocode and load via bounding box with exact circular radius filter
    print("  Using geocoded bounding box with circular radius filtering fallback...", flush=True)
    center_lat, center_lon = ox.geocode(PLACE_NAME)
    d_lat = RADIUS_METERS / METERS_PER_DEG_LAT
    d_lon = RADIUS_METERS / METERS_PER_DEG_LON
    bbox = (center_lon - d_lon, center_lat - d_lat, center_lon + d_lon, center_lat + d_lat)

    G_box = ox.graph_from_bbox(bbox, network_type=NETWORK_TYPE)
    nodes_in_circle = [
        n for n, d in G_box.nodes(data=True)
        if haversine_distance(center_lat, center_lon, d["y"], d["x"]) <= RADIUS_METERS
    ]
    G = G_box.subgraph(nodes_in_circle).copy()
    print(f"  Loaded via bbox filter: {len(G.nodes()):,} nodes, {len(G.edges()):,} edges.", flush=True)
    return G


def fetch_elevation_batch(coords: List[Tuple[float, float]], endpoint_url: str) -> Optional[List[Optional[float]]]:
    """
    Fetch elevations for a batch of (lat, lon) coordinates from OpenTopoData.
    Implements exponential backoff on HTTP 429 and network failures.

    Args:
        coords: List of (latitude, longitude) coordinate pairs.
        endpoint_url: OpenTopoData REST API endpoint URL.

    Returns:
        List of elevation values in meters, or None if the batch failed after all retries.
    """
    loc_string = "|".join(f"{lat:.6f},{lon:.6f}" for lat, lon in coords)
    params = {"locations": loc_string}

    for attempt in range(1, API_MAX_RETRIES + 1):
        try:
            response = requests.get(endpoint_url, params=params, timeout=API_TIMEOUT_SEC)
            if response.status_code == 200:
                data = response.json()
                if "results" in data:
                    return [item.get("elevation") for item in data["results"]]
            elif response.status_code == 429:
                wait_time = 2.0 * attempt
                print(f"    [429 Rate Limit] Backing off for {wait_time:.1f}s (attempt {attempt}/{API_MAX_RETRIES})...", flush=True)
                time.sleep(wait_time)
                continue
            else:
                print(f"    [HTTP {response.status_code}] Attempt {attempt}/{API_MAX_RETRIES} failed.", flush=True)
        except requests.RequestException as e:
            print(f"    [Request Exception: {e}] Attempt {attempt}/{API_MAX_RETRIES} failed.", flush=True)

        if attempt < API_MAX_RETRIES:
            time.sleep(1.5 * attempt)

    return None


def fetch_all_elevations(G: nx.MultiDiGraph) -> Dict[Union[int, str], Optional[float]]:
    """
    Fetch node elevations from OpenTopoData SRTM in batches of 100 with a 1s delay.
    Checks data/elevations.json first and caches raw elevations immediately upon completion.

    Args:
        G: Road network graph with 'y' (lat) and 'x' (lon) node attributes.

    Returns:
        Dictionary mapping node ID to elevation in meters.
    """
    # 1. Check raw elevation disk cache
    if os.path.exists(ELEVATIONS_CACHE_FILE):
        print(f"Loading raw elevations from cache: {ELEVATIONS_CACHE_FILE}...", flush=True)
        with open(ELEVATIONS_CACHE_FILE, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        elev_dict: Dict[Union[int, str], Optional[float]] = {}
        for k, v in raw_data.items():
            try:
                elev_dict[int(k)] = v
            except ValueError:
                elev_dict[k] = v
        return elev_dict

    # 2. Query OpenTopoData API
    nodes = list(G.nodes())
    total_nodes = len(nodes)
    total_batches = (total_nodes + API_BATCH_SIZE - 1) // API_BATCH_SIZE
    print(f"Fetching elevations for {total_nodes} nodes in {total_batches} batches...", flush=True)

    elev_dict = {}
    active_url = OPENTOPO_SRTM30_URL

    for i in range(0, total_nodes, API_BATCH_SIZE):
        batch_nodes = nodes[i : i + API_BATCH_SIZE]
        coords = [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in batch_nodes]
        batch_num = (i // API_BATCH_SIZE) + 1
        print(f"  Fetching batch {batch_num}/{total_batches} ({len(batch_nodes)} nodes)...", flush=True)

        elevations = fetch_elevation_batch(coords, active_url)

        # Fallback to SRTM 90m if SRTM 30m fails
        if elevations is None and active_url == OPENTOPO_SRTM30_URL:
            print("    SRTM 30m failed. Attempting fallback to SRTM 90m...", flush=True)
            active_url = OPENTOPO_SRTM90_URL
            elevations = fetch_elevation_batch(coords, active_url)

        if elevations is None:
            print(f"    Warning: Batch {batch_num} failed completely; assigning None.", flush=True)
            elevations = [None] * len(batch_nodes)

        for n, elev in zip(batch_nodes, elevations):
            elev_dict[n] = elev

        if i + API_BATCH_SIZE < total_nodes:
            time.sleep(API_REQUEST_DELAY_SEC)

    # Immediately cache raw elevations
    print(f"Saving raw elevations cache to {ELEVATIONS_CACHE_FILE}...", flush=True)
    with open(ELEVATIONS_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in elev_dict.items()}, f, indent=2)

    return elev_dict


def fill_null_elevations(G: nx.MultiDiGraph, elev_dict: Dict[Union[int, str], Optional[float]]) -> int:
    """
    Handle null elevations by filling null nodes from the average of their neighbors' elevations.

    Args:
        G: Road network graph to populate with node 'elevation' attributes.
        elev_dict: Raw node-to-elevation lookup dictionary.

    Returns:
        Number of null nodes that required filling.
    """
    null_nodes = set()
    for n in G.nodes():
        val = elev_dict.get(n)
        if val is None:
            val = elev_dict.get(str(n))
        G.nodes[n]["elevation"] = val
        if val is None or (isinstance(val, float) and math.isnan(val)):
            null_nodes.add(n)

    filled_count = len(null_nodes)
    if filled_count == 0:
        return 0

    print(f"Found {filled_count} nodes with null elevations. Filling from neighbors...", flush=True)
    remaining = set(null_nodes)
    max_passes = 15
    current_pass = 0

    while remaining and current_pass < max_passes:
        current_pass += 1
        resolved_this_pass = {}
        for n in remaining:
            neighbors = set(G.predecessors(n)).union(set(G.successors(n)))
            valid_elevs = [
                G.nodes[nbr]["elevation"]
                for nbr in neighbors
                if G.nodes[nbr].get("elevation") is not None and not math.isnan(G.nodes[nbr]["elevation"])
            ]
            if valid_elevs:
                resolved_this_pass[n] = sum(valid_elevs) / len(valid_elevs)

        if not resolved_this_pass:
            break

        for n, avg_val in resolved_this_pass.items():
            G.nodes[n]["elevation"] = avg_val
            remaining.remove(n)

    # Fallback for disconnected nodes
    if remaining:
        valid_elevs = [
            G.nodes[n]["elevation"]
            for n in G.nodes()
            if G.nodes[n].get("elevation") is not None and not math.isnan(G.nodes[n]["elevation"])
        ]
        fallback_val = sum(valid_elevs) / len(valid_elevs) if valid_elevs else 70.0
        for n in remaining:
            G.nodes[n]["elevation"] = fallback_val

    return filled_count


def calculate_edge_elev_min(G: nx.MultiDiGraph) -> None:
    """Assign elev_min attribute to each edge as min(elev_u, elev_v)."""
    for u, v, _, data in G.edges(keys=True, data=True):
        elev_u = G.nodes[u]["elevation"]
        elev_v = G.nodes[v]["elevation"]
        data["elev_min"] = float(min(elev_u, elev_v))


def cast_graph_types(G: nx.MultiDiGraph) -> None:
    """Explicitly cast node elevation and edge elev_min back to python floats."""
    for _, d in G.nodes(data=True):
        if "elevation" in d and d["elevation"] is not None:
            d["elevation"] = float(d["elevation"])

    for _, _, _, d in G.edges(keys=True, data=True):
        if "elev_min" in d and d["elev_min"] is not None:
            d["elev_min"] = float(d["elev_min"])


def load_cached_graph(graph_path: str = GRAPH_FILE) -> nx.MultiDiGraph:
    """
    Load an already cached GraphML file with guaranteed float dtypes.

    Args:
        graph_path: Path to graph.graphml.

    Returns:
        Loaded networkx.MultiDiGraph.
    """
    if not os.path.exists(graph_path):
        raise FileNotFoundError(f"Graph cache not found at {graph_path}. Run run_data.py first.")

    G = ox.load_graphml(
        graph_path,
        node_dtypes={"elevation": float},
        edge_dtypes={"elev_min": float},
    )
    cast_graph_types(G)
    return G


def load_or_create_graph(graph_path: str = GRAPH_FILE) -> Tuple[nx.MultiDiGraph, int]:
    """
    Loads cached graph if present; otherwise downloads road network,
    enriches with SRTM elevations, fills nulls, and caches to GraphML.

    Returns:
        Tuple of (enriched_graph, filled_nulls_count).
    """
    ensure_data_dir()
    if os.path.exists(graph_path):
        print(f"Found cached graph: loading {graph_path} (skipping downloads)...", flush=True)
        G = load_cached_graph(graph_path)

        filled_nulls_count = 0
        if os.path.exists(ELEVATIONS_CACHE_FILE):
            try:
                with open(ELEVATIONS_CACHE_FILE, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                filled_nulls_count = sum(1 for v in raw_data.values() if v is None)
            except Exception:
                filled_nulls_count = 0

        return G, filled_nulls_count

    # 1. Download road network
    G = fetch_road_network()

    # 2. Fetch elevations
    elev_dict = fetch_all_elevations(G)

    # 3. Fill null elevations
    filled_nulls_count = fill_null_elevations(G, elev_dict)

    # 4. Add elev_min attribute to edges
    print("Assigning elev_min attribute to all edges...", flush=True)
    calculate_edge_elev_min(G)

    # 5. Cache graph to GraphML
    print(f"Saving enriched graph to cache: {graph_path}...", flush=True)
    ox.save_graphml(G, graph_path)

    return G, filled_nulls_count


def get_graph_summary(G: nx.MultiDiGraph, filled_nulls_count: int = 0) -> Dict[str, Any]:
    """Calculate summary statistics for the network, elevation distribution, and structures."""
    node_elevs = [G.nodes[n]["elevation"] for n in G.nodes()]
    bridge_count = 0
    tunnel_count = 0

    for _, _, _, d in G.edges(keys=True, data=True):
        b = d.get("bridge")
        if b and b not in ("no", "false", False):
            bridge_count += 1
        t = d.get("tunnel")
        if t and t not in ("no", "false", False):
            tunnel_count += 1

    return {
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
        "min_elevation_m": min(node_elevs) if node_elevs else 0.0,
        "max_elevation_m": max(node_elevs) if node_elevs else 0.0,
        "mean_elevation_m": sum(node_elevs) / len(node_elevs) if node_elevs else 0.0,
        "filled_nulls": filled_nulls_count,
        "bridge_edges": bridge_count,
        "tunnel_edges": tunnel_count,
    }
