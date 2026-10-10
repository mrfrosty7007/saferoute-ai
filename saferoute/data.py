"""
SafeRouteAI - Phase 1 Data Ingestion & Elevation Enrichment
Author: SafeRouteAI Team

Responsible for downloading the drivable road network via OSMnx, querying
OpenTopoData SRTM elevation APIs in polite rate-limited batches, filling
null elevations via topological neighbor averaging, assigning elev_min
attributes to edges, and managing persistent GraphML caching.
"""

import glob
import hashlib
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


def get_network_query_fingerprint(
    place_name: str = PLACE_NAME,
    center_lat: float = CENTER_LAT,
    center_lon: float = CENTER_LON,
    radius_m: float = RADIUS_METERS,
    network_type: str = NETWORK_TYPE,
) -> str:
    """
    Compute a deterministic 16-hex query fingerprint for road network parameters.

    Args:
        place_name: Target locality string.
        center_lat: Latitude of study area center.
        center_lon: Longitude of study area center.
        radius_m: Network radius in meters.
        network_type: OSMnx network type ('drive', 'walk', etc.).

    Returns:
        16-character hexadecimal SHA-256 digest string.
    """
    query_str = f"{place_name}|{center_lat:.4f}|{center_lon:.4f}|{radius_m:.0f}|{network_type}"
    return hashlib.sha256(query_str.encode("utf-8")).hexdigest()[:16]


def validate_osm_cache_candidate(
    cache_path: str,
    center_lat: float = CENTER_LAT,
    center_lon: float = CENTER_LON,
    radius_m: float = RADIUS_METERS,
    min_matching_nodes: int = 500,
) -> Optional[nx.MultiDiGraph]:
    """
    Validate that a cached OSM JSON file corresponds to the requested study area:
    1. Safely parses JSON structure and ensures Overpass elements exist.
    2. Verifies geographic relevance: nodes must be centered near (center_lat, center_lon).
    3. Verifies that the candidate contains sufficient drivable road network nodes within radius_m.
    4. Constructs and simplifies the circular subgraph.

    Args:
        cache_path: Path to candidate Overpass JSON cache file.
        center_lat: Study area center latitude.
        center_lon: Study area center longitude.
        radius_m: Study area radius in meters.
        min_matching_nodes: Minimum acceptable nodes in circular network.

    Returns:
        Validated networkx.MultiDiGraph if candidate matches, or None if invalid/unrelated.
    """
    if not os.path.isfile(cache_path):
        return None

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    elements = data.get("elements")
    if not isinstance(elements, list) or len(elements) < 100:
        return None

    # Extract node coordinates for fast geographic bounding check
    node_coords = [
        (e["lat"], e["lon"])
        for e in elements
        if isinstance(e, dict) and e.get("type") == "node" and "lat" in e and "lon" in e
    ]
    if len(node_coords) < min_matching_nodes:
        return None

    # Count nodes within study area bounding envelope
    nodes_in_envelope = [
        (lat, lon) for lat, lon in node_coords
        if haversine_distance(center_lat, center_lon, lat, lon) <= (radius_m * 1.5)
    ]
    if len(nodes_in_envelope) < min_matching_nodes:
        return None

    # Check centroid geographic proximity
    mean_lat = sum(lat for lat, _ in nodes_in_envelope) / len(nodes_in_envelope)
    mean_lon = sum(lon for _, lon in nodes_in_envelope) / len(nodes_in_envelope)
    if haversine_distance(center_lat, center_lon, mean_lat, mean_lon) > radius_m:
        return None

    # Build and simplify graph from candidate
    try:
        G_raw = ox.graph._create_graph([data], False)
        G_simple = ox.simplification.simplify_graph(G_raw)

        nodes_in_circle = [
            n for n, d in G_simple.nodes(data=True)
            if haversine_distance(center_lat, center_lon, d["y"], d["x"]) <= radius_m
        ]
        if len(nodes_in_circle) < min_matching_nodes:
            return None

        G = G_simple.subgraph(nodes_in_circle).copy()
        if G.number_of_nodes() < min_matching_nodes or G.number_of_edges() < (min_matching_nodes * 2):
            return None

        return G
    except Exception as e:
        print(f"    [Cache Check] Could not construct graph from {cache_path}: {e}", flush=True)
        return None


def fetch_road_network() -> nx.MultiDiGraph:
    """
    Load the drivable road network within RADIUS_METERS of PLACE_NAME.
    Uses deterministic query-specific cache selection and validates candidate
    geographic relevance before falling back to Overpass API / bbox queries.

    Returns:
        Simplified networkx.MultiDiGraph road network.

    Raises:
        RuntimeError: If all local cache candidates and network queries fail.
    """
    print(f"Loading road network for '{PLACE_NAME}' (radius: {RADIUS_METERS}m)...", flush=True)

    fingerprint = get_network_query_fingerprint()
    dedicated_cache = os.path.join("cache", f"query_{fingerprint}.json")

    # 1. Check dedicated query-fingerprint cache file first
    if os.path.exists(dedicated_cache):
        print(f"  Checking dedicated query cache: {dedicated_cache}...", flush=True)
        G_ded = validate_osm_cache_candidate(dedicated_cache)
        if G_ded is not None:
            print(f"  Loaded from query cache: {len(G_ded.nodes()):,} nodes, {len(G_ded.edges()):,} edges.", flush=True)
            return G_ded

    # 2. Check and validate candidate Overpass response cache files
    cache_files = glob.glob("cache/*.json")
    for cf in cache_files:
        if os.path.abspath(cf) == os.path.abspath(dedicated_cache):
            continue
        # Only inspect files with realistic Overpass response size (> 100 KB)
        if os.path.getsize(cf) > 100_000:
            G_cand = validate_osm_cache_candidate(cf)
            if G_cand is not None:
                print(f"  Found verified matching OSM Overpass data in {cf}.", flush=True)
                print(f"  Loaded from validated cache: {len(G_cand.nodes()):,} nodes, {len(G_cand.edges()):,} edges.", flush=True)
                return G_cand

    # 3. Try direct ox.graph_from_address
    print("  No matching offline cache found. Attempting live Overpass API query...", flush=True)
    try:
        G = ox.graph_from_address(PLACE_NAME, dist=RADIUS_METERS, network_type=NETWORK_TYPE)
        print(f"  Loaded via graph_from_address: {len(G.nodes()):,} nodes, {len(G.edges()):,} edges.", flush=True)
        return G
    except Exception as e:
        print(f"  Notice: Direct graph_from_address query failed or timed out ({e}).", flush=True)

    # 4. Fallback: Geocode and load via bounding box with exact circular radius filter
    print("  Using geocoded bounding box with circular radius filtering fallback...", flush=True)
    try:
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
        if G.number_of_nodes() >= 500:
            print(f"  Loaded via bbox filter: {len(G.nodes()):,} nodes, {len(G.edges()):,} edges.", flush=True)
            return G
        raise ValueError(f"Extracted bbox network contains only {G.number_of_nodes()} nodes (insufficient).")
    except Exception as e:
        print(f"  Bbox query fallback failed: {e}", flush=True)

    # 5. Fail gracefully with clear actionable error
    raise RuntimeError(
        f"Failed to load drivable road network for '{PLACE_NAME}' (radius {RADIUS_METERS}m). "
        "No matching local cache was found in cache/ and live Overpass API queries failed. "
        "Please check your internet connection or place a valid Overpass JSON file into cache/."
    )


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
