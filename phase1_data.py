"""
SafeRouteAI - Phase 1: Data Ingestion & Elevation Enrichment
Author: SafeRouteAI Team

Features:
1. Loads the drivable road network for a 2 km radius around "Daraganj, Prayagraj, India" with OSMnx.
2. Caches the graph to data/graph.graphml and skips all downloads if cache exists.
3. Fetches node elevations from OpenTopoData SRTM API in batches of 100 with 1s delay and retries.
4. Caches raw elevations to data/elevations.json as soon as fetched to prevent redundant API calls.
5. Fills null elevations from neighboring nodes' average elevation (reporting filled count).
6. Adds 'elevation' attribute to nodes and 'elev_min' attribute to edges.
7. Corrects GraphML float type reloading (ensures elevation and elev_min are floats).
8. Generates a readable network plot colored by edge elev_min with a scaled colorbar.
9. Prints a comprehensive summary including node/edge counts, elevation stats, filled nulls, and bridges/tunnels.
"""

import os
import glob
import json
import math
import time
import requests
import networkx as nx
import osmnx as ox
import matplotlib.cm as cm
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt

# Configuration
PLACE_NAME = "Daraganj, Prayagraj, India"
RADIUS_METERS = 2000
NETWORK_TYPE = "drive"
DATA_DIR = "data"
GRAPH_CACHE_FILE = os.path.join(DATA_DIR, "graph.graphml")
ELEVATIONS_CACHE_FILE = os.path.join(DATA_DIR, "elevations.json")
PLOT_OUTPUT_FILE = os.path.join(DATA_DIR, "elevation_network.png")

OPENTOPO_SRTM30_URL = "https://api.opentopodata.org/v1/srtm30m"
OPENTOPO_SRTM90_URL = "https://api.opentopodata.org/v1/srtm90m"
BATCH_SIZE = 100
REQUEST_DELAY = 1.0  # seconds between batches
MAX_RETRIES = 3

# Configure OSMnx settings
ox.settings.overpass_rate_limit = False
ox.settings.requests_timeout = 60
ox.settings.use_cache = True
ox.settings.user_agent = "SafeRouteAI-Research/1.0 (admin@saferoute.ai)"


def ensure_directories():
    """Ensure that the data directory exists."""
    os.makedirs(DATA_DIR, exist_ok=True)


def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate the great circle distance between two points in meters."""
    r = 6371000.0  # Earth's radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def fetch_road_network():
    """
    Load drivable road network for a 2 km radius around Daraganj, Prayagraj.
    Checks existing local OSM cache files first, then attempts ox.graph_from_address,
    with a robust bounding box + haversine distance filtering fallback.
    """
    print(f"Loading drivable road network for '{PLACE_NAME}' (radius: {RADIUS_METERS}m)...", flush=True)

    # 1. Check if raw OSMnx response cache exists locally in cache/
    cache_files = glob.glob("cache/*.json")
    for cf in cache_files:
        if os.path.getsize(cf) > 500_000:
            try:
                print(f"  Found cached OSM Overpass data in {cf}, loading graph...", flush=True)
                with open(cf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                G_raw = ox.graph._create_graph([data], False)
                G_simple = ox.simplification.simplify_graph(G_raw)

                # Geocode center to filter within 2 km radius
                center_lat, center_lon = 25.4430353, 81.8804985
                nodes_in_circle = [
                    n for n, d in G_simple.nodes(data=True)
                    if haversine_distance(center_lat, center_lon, d["y"], d["x"]) <= RADIUS_METERS
                ]
                G = G_simple.subgraph(nodes_in_circle).copy()
                print(f"  Network loaded from cache: {len(G.nodes())} nodes, {len(G.edges())} edges.", flush=True)
                return G
            except Exception as e:
                print(f"  Could not load from {cf}: {e}", flush=True)

    # 2. Try direct ox.graph_from_address
    try:
        G = ox.graph_from_address(PLACE_NAME, dist=RADIUS_METERS, network_type=NETWORK_TYPE)
        print(f"  Network loaded via graph_from_address: {len(G.nodes())} nodes, {len(G.edges())} edges.", flush=True)
        return G
    except Exception as e:
        print(f"  Notice: Direct graph_from_address query timed out ({e}).", flush=True)

    # 3. Fallback: Geocode and load via bounding box with 2 km radius filter
    print("  Using geocoded bounding box with 2 km radius filtering fallback...", flush=True)
    center_lat, center_lon = ox.geocode(PLACE_NAME)
    d_lat = RADIUS_METERS / 111320.0
    d_lon = RADIUS_METERS / 100500.0
    bbox = (center_lon - d_lon, center_lat - d_lat, center_lon + d_lon, center_lat + d_lat)

    G_box = ox.graph_from_bbox(bbox, network_type=NETWORK_TYPE)
    nodes_in_circle = [
        n for n, d in G_box.nodes(data=True)
        if haversine_distance(center_lat, center_lon, d["y"], d["x"]) <= RADIUS_METERS
    ]
    G = G_box.subgraph(nodes_in_circle).copy()
    print(f"  Network loaded via bbox + radius filter: {len(G.nodes())} nodes, {len(G.edges())} edges.", flush=True)
    return G


def fetch_elevation_batch(coords, endpoint_url, max_retries=MAX_RETRIES):
    """
    Fetch elevations for a batch of (lat, lon) coordinates from OpenTopoData.
    Implements retries with exponential backoff on HTTP 429 / network errors.
    """
    loc_string = "|".join(f"{lat:.6f},{lon:.6f}" for lat, lon in coords)
    params = {"locations": loc_string}

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(endpoint_url, params=params, timeout=20)
            if response.status_code == 200:
                data = response.json()
                if "results" in data:
                    return [item.get("elevation") for item in data["results"]]
            elif response.status_code == 429:
                wait_time = 2.0 * attempt
                print(f"    [429 Rate Limit] Backing off for {wait_time:.1f}s (attempt {attempt}/{max_retries})...", flush=True)
                time.sleep(wait_time)
                continue
            else:
                print(f"    [HTTP {response.status_code}] Attempt {attempt}/{max_retries} failed.", flush=True)
        except requests.RequestException as e:
            print(f"    [Request Exception: {e}] Attempt {attempt}/{max_retries} failed.", flush=True)

        if attempt < max_retries:
            time.sleep(1.5 * attempt)

    return None


def fetch_all_elevations(G):
    """
    Fetch node elevations from OpenTopoData SRTM API in batches of 100 with 1s delay.
    Checks data/elevations.json first to skip repeat calls if an earlier run fetched them.
    Saves raw elevations to data/elevations.json immediately after fetching.
    """
    # 1. Check if raw elevation cache exists
    if os.path.exists(ELEVATIONS_CACHE_FILE):
        print(f"Loading raw elevations from cache: {ELEVATIONS_CACHE_FILE}...", flush=True)
        with open(ELEVATIONS_CACHE_FILE, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        elev_dict = {}
        for k, v in raw_data.items():
            try:
                elev_dict[int(k)] = v
            except ValueError:
                elev_dict[k] = v
        return elev_dict

    # 2. Fetch from OpenTopoData
    nodes = list(G.nodes())
    total_nodes = len(nodes)
    total_batches = (total_nodes + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"Fetching elevations for {total_nodes} nodes in {total_batches} batches of {BATCH_SIZE}...", flush=True)

    elev_dict = {}
    active_url = OPENTOPO_SRTM30_URL

    for i in range(0, total_nodes, BATCH_SIZE):
        batch_nodes = nodes[i : i + BATCH_SIZE]
        coords = [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in batch_nodes]
        batch_num = (i // BATCH_SIZE) + 1
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

        # Enforce rate limit delay between API batches
        if i + BATCH_SIZE < total_nodes:
            time.sleep(REQUEST_DELAY)

    # Immediately cache raw elevations
    print(f"Saving raw elevations cache to {ELEVATIONS_CACHE_FILE}...", flush=True)
    with open(ELEVATIONS_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in elev_dict.items()}, f, indent=2)

    return elev_dict


def fill_null_elevations(G, elev_dict):
    """
    Handle null elevations: fill null nodes using the average of their neighbors' elevations.
    Prints the number of nodes requiring filling.
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
        print("No null elevations encountered.", flush=True)
        return 0

    print(f"Found {filled_count} nodes with null elevations (water bodies / tile gaps). Filling from neighbors...", flush=True)

    # Multi-pass neighbor averaging
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

    # Fallback for any disconnected components
    if remaining:
        valid_elevs = [
            G.nodes[n]["elevation"]
            for n in G.nodes()
            if G.nodes[n].get("elevation") is not None and not math.isnan(G.nodes[n]["elevation"])
        ]
        fallback_val = sum(valid_elevs) / len(valid_elevs) if valid_elevs else 70.0
        print(f"  {len(remaining)} isolated null nodes filled with network mean ({fallback_val:.2f} m).", flush=True)
        for n in remaining:
            G.nodes[n]["elevation"] = fallback_val

    print(f"Successfully filled all {filled_count} null node elevations.", flush=True)
    return filled_count


def calculate_edge_elev_min(G):
    """Add elev_min attribute to edges (the lower of the two endpoint elevations)."""
    for u, v, k, data in G.edges(keys=True, data=True):
        elev_u = G.nodes[u]["elevation"]
        elev_v = G.nodes[v]["elevation"]
        data["elev_min"] = float(min(elev_u, elev_v))


def cast_graph_types(G):
    """
    Explicitly cast custom node and edge attributes back to floats.
    Guards against GraphML reloading them as strings.
    """
    for _, d in G.nodes(data=True):
        if "elevation" in d and d["elevation"] is not None:
            d["elevation"] = float(d["elevation"])

    for _, _, _, d in G.edges(keys=True, data=True):
        if "elev_min" in d and d["elev_min"] is not None:
            d["elev_min"] = float(d["elev_min"])


def load_or_create_graph():
    """
    Check if data/graph.graphml exists.
    If cached: load graph with float dtypes and skip all downloads.
    If missing: fetch road network, query elevations, fill nulls, compute elev_min, and cache.
    """
    if os.path.exists(GRAPH_CACHE_FILE):
        print(f"Found cached graph: loading {GRAPH_CACHE_FILE} (skipping downloads)...", flush=True)
        G = ox.load_graphml(
            GRAPH_CACHE_FILE,
            node_dtypes={"elevation": float},
            edge_dtypes={"elev_min": float},
        )
        cast_graph_types(G)

        # Count filled nulls from raw elevations cache if available
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

    # 2. Fetch elevations (or load raw elevation cache)
    elev_dict = fetch_all_elevations(G)

    # 3. Fill null elevations
    filled_nulls_count = fill_null_elevations(G, elev_dict)

    # 4. Add elev_min attribute to edges
    print("Assigning elev_min attribute to all edges...", flush=True)
    calculate_edge_elev_min(G)

    # 5. Cache graph to GraphML
    print(f"Saving enriched graph to cache: {GRAPH_CACHE_FILE}...", flush=True)
    ox.save_graphml(G, GRAPH_CACHE_FILE)

    return G, filled_nulls_count


def plot_network_elevation(G, output_path=PLOT_OUTPUT_FILE):
    """
    Plot the drivable road network with edges colored by elev_min.
    Includes a scaled colorbar covering actual min and max elevations.
    """
    edge_elevations = [d["elev_min"] for _, _, _, d in G.edges(keys=True, data=True)]
    min_elev = min(edge_elevations)
    max_elev = max(edge_elevations)

    print(f"Rendering elevation-colored network plot (range: {min_elev:.1f} m - {max_elev:.1f} m)...", flush=True)

    norm = mcolors.Normalize(vmin=min_elev, vmax=max_elev)
    cmap = plt.cm.plasma
    edge_colors = [cmap(norm(d["elev_min"])) for _, _, _, d in G.edges(keys=True, data=True)]

    fig, ax = plt.subplots(figsize=(11, 10), facecolor="#0e1117")

    ox.plot_graph(
        G,
        ax=ax,
        node_size=6,
        node_color="#444b58",
        node_alpha=0.45,
        edge_color=edge_colors,
        edge_linewidth=1.35,
        edge_alpha=0.92,
        bgcolor="#0e1117",
        show=False,
        close=False,
    )

    ax.set_facecolor("#0e1117")

    # Add colorbar
    sm = cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, orientation="vertical", shrink=0.72, pad=0.03, aspect=26)
    cbar.set_label("Minimum Edge Elevation: elev_min (meters)", color="#e2e8f0", fontsize=10.5, labelpad=12, fontweight="medium")
    cbar.ax.yaxis.set_tick_params(color="#a0aec0", labelcolor="#e2e8f0", labelsize=9)
    if hasattr(cbar, "outline") and cbar.outline is not None:
        cbar.outline.set_edgecolor("#2d3748")

    ax.set_title(
        f"SafeRouteAI — Road Network Elevation Model\n{PLACE_NAME} (2 km radius)",
        color="#f7fafc",
        fontsize=13,
        pad=18,
        fontweight="bold",
    )

    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="#0e1117", edgecolor="none")
    plt.close(fig)
    print(f"Plot saved successfully: {output_path}", flush=True)


def print_summary(G, filled_nulls_count):
    """Print summary statistics for the road network, elevation, nulls, and bridges/tunnels."""
    node_count = G.number_of_nodes()
    edge_count = G.number_of_edges()

    node_elevs = [G.nodes[n]["elevation"] for n in G.nodes()]
    min_elev = min(node_elevs)
    max_elev = max(node_elevs)
    mean_elev = sum(node_elevs) / len(node_elevs)

    bridge_count = 0
    tunnel_count = 0
    for _, _, _, d in G.edges(keys=True, data=True):
        b = d.get("bridge")
        if b and b not in ("no", "false", False):
            bridge_count += 1
        t = d.get("tunnel")
        if t and t not in ("no", "false", False):
            tunnel_count += 1

    print("\n" + "=" * 55, flush=True)
    print("           SAFEROUTEAI - PHASE 1 SUMMARY REPORT", flush=True)
    print("=" * 55, flush=True)
    print(f"  Total Nodes:                {node_count:,}", flush=True)
    print(f"  Total Edges:                {edge_count:,}", flush=True)
    print(f"  Minimum Node Elevation:     {min_elev:.2f} m", flush=True)
    print(f"  Maximum Node Elevation:     {max_elev:.2f} m", flush=True)
    print(f"  Mean Node Elevation:        {mean_elev:.2f} m", flush=True)
    print(f"  Null Elevations Filled:     {filled_nulls_count:,}", flush=True)
    print(f"  Bridge Edges Tagged:        {bridge_count:,}", flush=True)
    print(f"  Tunnel Edges Tagged:        {tunnel_count:,}", flush=True)
    print("=" * 55 + "\n", flush=True)


def main():
    ensure_directories()
    G, filled_nulls = load_or_create_graph()
    plot_network_elevation(G)
    print_summary(G, filled_nulls)


if __name__ == "__main__":
    main()
