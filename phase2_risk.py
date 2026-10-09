"""
SafeRouteAI - Phase 2: Flood Risk & Vehicle Passability Modeling
Author: SafeRouteAI Team

Features:
1. Reloads cached road network from data/graph.graphml with float dtypes.
2. Identifies bridge edges via a robust is_bridge() helper (handling 'yes', 'viaduct', lists, stringified lists).
3. Precomputes and caches topographic depressions (within 300 m) using scipy cKDTree to data/depressions.pkl.
4. Computes per-edge flood depth (cm) combining riverine flooding and rainfall ponding.
   - NOTE: Riverine depth = max(0, river_level - elev_min) is a demo simplification;
     it models any road below the river stage as flooded without requiring full hydraulic 2D flow connectivity.
5. Implements logistic sigmoid passability probability for Ambulance (28 cm), Fire Tender (50 cm), and Rescue Truck (65 cm).
6. Writes 'water_depth_cm' and 'pass_probability_<vehicle>' onto edge attributes of a graph copy.
7. Includes strict sanity assertions (non-negative depth, monotonicity in rainfall & river level, 20 bridge verification).
8. Evaluates Dry, Moderate, and Severe scenarios and renders a comprehensive 3x3 comparison grid plot.
"""

import os
import ast
import math
import pickle
import numpy as np
import networkx as nx
import osmnx as ox
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.cm as cm
from scipy.spatial import cKDTree

# ==============================================================================
# Model Parameters & Tunable Constants
# ==============================================================================

K_RAIN_FACTOR = 0.25             # Tunable rainfall ponding coefficient k
SIGMOID_SCALE_S = 5.0            # Soft-threshold transition width s in cm
DEPRESSION_RADIUS_M = 300.0      # Topographic neighborhood radius for depression calculation
BRIDGE_CLEARANCE_MARGIN_M = 1.0  # Clearance margin above bridge approaches before overtopping

# Vehicle safe wading clearance thresholds (cm)
VEHICLES = {
    "ambulance": 28.0,           # Emergency medical transport
    "fire_tender": 50.0,         # Fire and emergency response vehicle
    "rescue_truck": 65.0,        # High-clearance multi-axle disaster rescue truck
}

# Sliders & Domain Bounds (Daraganj Road Elevation Range: ~74 m to 99 m)
RIVER_LEVEL_MIN_M = 74.0
RIVER_LEVEL_MAX_M = 90.0
RAINFALL_MAX_MM_HR = 100.0

DATA_DIR = "data"
GRAPH_FILE = os.path.join(DATA_DIR, "graph.graphml")
DEPRESSIONS_CACHE_FILE = os.path.join(DATA_DIR, "depressions.pkl")
GRID_PLOT_OUTPUT_FILE = os.path.join(DATA_DIR, "passability_3x3_grid.png")


# ==============================================================================
# Graph Loading & Bridge Identification
# ==============================================================================

def load_graph(graph_path=GRAPH_FILE):
    """
    Load the cached OSMnx graph from GraphML with explicit float dtypes for
    elevation and elev_min.
    """
    if not os.path.exists(graph_path):
        raise FileNotFoundError(f"Graph file not found: {graph_path}. Please run phase1_data.py first.")

    G = ox.load_graphml(
        graph_path,
        node_dtypes={"elevation": float},
        edge_dtypes={"elev_min": float},
    )

    # Cast node and edge attributes to python floats to ensure type integrity
    for _, d in G.nodes(data=True):
        if "elevation" in d and d["elevation"] is not None:
            d["elevation"] = float(d["elevation"])

    for _, _, _, d in G.edges(keys=True, data=True):
        if "elev_min" in d and d["elev_min"] is not None:
            d["elev_min"] = float(d["elev_min"])

    return G


def is_bridge(data):
    """
    Robust bridge classifier for OSMnx edge attributes.
    Handles 'yes', 'viaduct', 'aqueduct', Python lists, and stringified lists from GraphML.
    Returns True for any edge tagged as an elevated/bridge structure, False otherwise.
    """
    val = data.get("bridge")
    if val is None or val is False or val == "":
        return False

    # Direct python list check
    if isinstance(val, (list, tuple, set)):
        return any(str(v).strip().lower() not in ("no", "false", "none", "", "0") for v in val)

    # Convert to string and inspect
    s = str(val).strip().lower()
    if s in ("no", "false", "none", "0", "[]", "['no']", '["no"]'):
        return False

    # Attempt parsing stringified list e.g. "['yes', 'viaduct']"
    if s.startswith("[") and s.endswith("]"):
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, (list, tuple)):
                return any(str(v).strip().lower() not in ("no", "false", "none", "", "0") for v in parsed)
        except Exception:
            pass
        # Fallback string check inside brackets
        clean = s.replace("[", "").replace("]", "").replace("'", "").replace('"', "").strip()
        return clean not in ("no", "false", "none", "", "0")

    return True


# ==============================================================================
# Topographic Depression Precomputation & Caching
# ==============================================================================

def precompute_depressions(G, radius_m=DEPRESSION_RADIUS_M, cache_path=DEPRESSIONS_CACHE_FILE):
    """
    Compute edge depression: mean elev_min of edges within radius_m minus this edge's elev_min.
    Caches the resulting dict {(u, v, k): depression_m} to cache_path for instant reload.
    """
    if os.path.exists(cache_path):
        print(f"Loading cached topographic depressions from {cache_path}...", flush=True)
        with open(cache_path, "rb") as f:
            depressions = pickle.load(f)
        if len(depressions) == G.number_of_edges():
            return depressions
        print("  Cache size mismatch. Recomputing depressions...", flush=True)

    print(f"Precomputing edge topographic depressions (neighborhood radius: {radius_m} m)...", flush=True)

    edge_keys = []
    midpoint_coords = []
    elev_mins = []

    # Center coordinates around Daraganj (lat ~25.44, lon ~81.88)
    center_lat, center_lon = 25.4430, 81.8805
    meters_per_deg_lat = 111320.0
    meters_per_deg_lon = 100500.0

    for u, v, k, d in G.edges(keys=True, data=True):
        lat1, lon1 = G.nodes[u]["y"], G.nodes[u]["x"]
        lat2, lon2 = G.nodes[v]["y"], G.nodes[v]["x"]
        mid_lat = (lat1 + lat2) / 2.0
        mid_lon = (lon1 + lon2) / 2.0

        # Metric Cartesian coordinates (x_meters, y_meters)
        x_m = (mid_lon - center_lon) * meters_per_deg_lon
        y_m = (mid_lat - center_lat) * meters_per_deg_lat

        edge_keys.append((u, v, k))
        midpoint_coords.append((x_m, y_m))
        elev_mins.append(float(d["elev_min"]))

    midpoint_coords = np.array(midpoint_coords)
    elev_mins = np.array(elev_mins)

    # Build KD-Tree on metric edge midpoints
    tree = cKDTree(midpoint_coords)

    depressions = {}
    for idx, pt in enumerate(midpoint_coords):
        neighbor_indices = tree.query_ball_point(pt, r=radius_m)
        local_mean_elev = elev_mins[neighbor_indices].mean()
        depression_val = max(0.0, float(local_mean_elev - elev_mins[idx]))
        depressions[edge_keys[idx]] = depression_val

    # Save to disk cache
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "wb") as f:
        pickle.dump(depressions, f)
    print(f"Saved {len(depressions):,} edge depressions to cache: {cache_path}.", flush=True)

    return depressions


# ==============================================================================
# Depth & Passability Calculation
# ==============================================================================

def compute_depths(G, rainfall_mm_hr, river_level_m, depressions=None, k=K_RAIN_FACTOR):
    """
    Computes flood water depth (cm) for every edge in G.

    Components:
    1. Riverine depth: max(0, river_level_m - elev_min) * 100
       [Simplification Note: Models any road below river stage as flooded by backwater/overflow.]
    2. Rain ponding depth: k * rainfall_mm_hr * (1.0 + depression)
    3. Bridges: exempt from depth formula (depth = 0 cm) unless river level exceeds
       approach endpoint elevations plus BRIDGE_CLEARANCE_MARGIN_M (overtopping condition).

    Returns:
        dict: mapping (u, v, k) -> water_depth_cm
    """
    if depressions is None:
        depressions = precompute_depressions(G)

    depths = {}
    for u, v, key, data in G.edges(keys=True, data=True):
        edge_key = (u, v, key)
        elev_min = float(data["elev_min"])

        # Check bridge status
        if is_bridge(data):
            elev_u = float(G.nodes[u]["elevation"])
            elev_v = float(G.nodes[v]["elevation"])
            bridge_deck_thresh = max(elev_u, elev_v) + BRIDGE_CLEARANCE_MARGIN_M

            if river_level_m > bridge_deck_thresh:
                # Bridge approach/deck is overtopped by extreme river stage
                depth_cm = (river_level_m - bridge_deck_thresh) * 100.0
            else:
                # Bridge remains elevated above localized water and runoff
                depth_cm = 0.0
        else:
            # Standard road segment
            riverine_depth_cm = max(0.0, river_level_m - elev_min) * 100.0
            depression_m = depressions.get(edge_key, 0.0)
            rain_depth_cm = k * float(rainfall_mm_hr) * (1.0 + depression_m)
            depth_cm = riverine_depth_cm + rain_depth_cm

        depths[edge_key] = max(0.0, float(depth_cm))

    return depths


def pass_probability(depth_cm, vehicle="ambulance", scale_s=SIGMOID_SCALE_S):
    """
    Evaluates soft logistic passability probability p in [0, 1] for a given depth and vehicle.
    p = 1 / (1 + exp((depth - safe_depth) / scale_s))

    Safe wading depths:
        ambulance: 28 cm
        fire_tender: 50 cm
        rescue_truck: 65 cm
    """
    if vehicle not in VEHICLES:
        raise ValueError(f"Unknown vehicle '{vehicle}'. Must be one of: {list(VEHICLES.keys())}")

    safe_depth = VEHICLES[vehicle]

    # Handle array or scalar
    diff = (np.asarray(depth_cm, dtype=float) - safe_depth) / float(scale_s)
    # Clip exponent to avoid numerical overflow / underflow
    diff = np.clip(diff, -50.0, 50.0)
    p = 1.0 / (1.0 + np.exp(diff))

    if np.isscalar(depth_cm):
        return float(p)
    return p


def passability(G, vehicle, rainfall, river_level, depressions=None, k=K_RAIN_FACTOR):
    """
    Primary API function:
    Computes water depth and pass probability for all edges, and writes:
        - data['water_depth_cm']
        - data[f'pass_probability_{vehicle}']
        - data['pass_probability'] (for the active vehicle)
    onto edge attributes of a deep copy of graph G.

    Returns:
        G_copy: networkx.MultiDiGraph with enriched edge attributes
    """
    G_copy = G.copy()
    depths = compute_depths(G_copy, rainfall, river_level, depressions=depressions, k=k)

    prob_attr_name = f"pass_probability_{vehicle}"
    for u, v, key, data in G_copy.edges(keys=True, data=True):
        edge_key = (u, v, key)
        d_cm = depths[edge_key]
        p_val = pass_probability(d_cm, vehicle=vehicle, scale_s=SIGMOID_SCALE_S)

        data["water_depth_cm"] = d_cm
        data[prob_attr_name] = p_val
        data["pass_probability"] = p_val

    return G_copy


# ==============================================================================
# Visualization Routines
# ==============================================================================

def plot_passability(G_assessed, vehicle, rainfall, river_level, output_path=None, ax=None, show_colorbar=True):
    """
    Plots the road network colored by pass probability from Red (0.0) to Yellow (0.5) to Green (1.0).
    Can render onto a standalone figure or an existing matplotlib axis (for subplots).
    """
    prob_key = f"pass_probability_{vehicle}"
    probs = [d.get(prob_key, d.get("pass_probability", 1.0)) for _, _, _, d in G_assessed.edges(keys=True, data=True)]

    cmap = plt.cm.RdYlGn
    norm = mcolors.Normalize(vmin=0.0, vmax=1.0)
    edge_colors = [cmap(norm(p)) for p in probs]

    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(11, 10), facecolor="#0e1117")
    else:
        fig = ax.figure

    ox.plot_graph(
        G_assessed,
        ax=ax,
        node_size=4,
        node_color="#333842",
        node_alpha=0.35,
        edge_color=edge_colors,
        edge_linewidth=1.3,
        edge_alpha=0.92,
        bgcolor="#0e1117",
        show=False,
        close=False,
    )
    ax.set_facecolor("#0e1117")

    impassable_count = sum(1 for p in probs if p < 0.5)
    impassable_pct = (impassable_count / len(probs)) * 100.0 if probs else 0.0

    vehicle_title = vehicle.replace("_", " ").title()
    ax.set_title(
        f"{vehicle_title} (Safe: {VEHICLES[vehicle]:.0f} cm)\n"
        f"River: {river_level:.1f} m | Rain: {rainfall:.0f} mm/hr | Closed: {impassable_pct:.1f}%",
        color="#f7fafc",
        fontsize=10.5,
        pad=10,
        fontweight="semibold",
    )

    if show_colorbar:
        sm = cm.ScalarMappable(norm=norm, cmap=cmap)
        sm.set_array([])
        cbar = fig.colorbar(sm, ax=ax, orientation="vertical", shrink=0.72, pad=0.03, aspect=24)
        cbar.set_label("Pass Probability (1.0 = Safe, 0.0 = Impassable)", color="#e2e8f0", fontsize=9.5, labelpad=10)
        cbar.ax.yaxis.set_tick_params(color="#a0aec0", labelcolor="#e2e8f0", labelsize=8.5)
        if hasattr(cbar, "outline") and cbar.outline is not None:
            cbar.outline.set_edgecolor("#2d3748")

    if standalone and output_path:
        fig.tight_layout()
        fig.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="#0e1117", edgecolor="none")
        plt.close(fig)
        print(f"Plot saved: {output_path}", flush=True)

    return ax


def generate_3x3_grid(G, scenarios, depressions, output_path=GRID_PLOT_OUTPUT_FILE):
    """
    Renders a 3x3 comparison grid:
        Rows = Scenarios (Dry, Moderate, Severe)
        Cols = Vehicles (Ambulance, Fire Tender, Rescue Truck)
    Saves the final composite figure to output_path.
    """
    print(f"\nGenerating 3x3 scenario comparison grid plot...", flush=True)
    vehicles_list = ["ambulance", "fire_tender", "rescue_truck"]

    fig, axes = plt.subplots(3, 3, figsize=(18, 18), facecolor="#0e1117")

    for row_idx, (scen_name, params) in enumerate(scenarios.items()):
        riv = params["river"]
        rain = params["rain"]

        for col_idx, v_name in enumerate(vehicles_list):
            ax = axes[row_idx, col_idx]
            G_eval = passability(G, v_name, rainfall=rain, river_level=riv, depressions=depressions)
            plot_passability(
                G_eval,
                vehicle=v_name,
                rainfall=rain,
                river_level=riv,
                ax=ax,
                show_colorbar=False,
            )

            # Row title annotation on left column
            if col_idx == 0:
                ax.annotate(
                    f"SCENARIO: {scen_name.upper()}",
                    xy=(0.03, 0.94),
                    xycoords="axes fraction",
                    color="#63b3ed",
                    fontsize=11,
                    fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="#1a202c", edgecolor="#4a5568", alpha=0.85),
                )

    fig.suptitle(
        "SafeRouteAI — Vehicle Passability Under Confluence Flood & Rain Scenarios\n"
        "Daraganj, Prayagraj, India (2 km radius road network)",
        color="#ffffff",
        fontsize=16,
        fontweight="bold",
        y=0.995,
    )

    # Shared horizontal colorbar at bottom
    sm = cm.ScalarMappable(norm=mcolors.Normalize(vmin=0.0, vmax=1.0), cmap=plt.cm.RdYlGn)
    sm.set_array([])
    cbar_ax = fig.add_axes([0.25, 0.02, 0.50, 0.016])
    cbar = fig.colorbar(sm, cax=cbar_ax, orientation="horizontal")
    cbar.set_label("Pass Probability p  [ Red = Impassable (p < 0.5)  |  Green = Safe (p ≥ 0.5) ]",
                   color="#e2e8f0", fontsize=11, labelpad=8, fontweight="medium")
    cbar.ax.xaxis.set_tick_params(color="#a0aec0", labelcolor="#e2e8f0", labelsize=9.5)
    if hasattr(cbar, "outline") and cbar.outline is not None:
        cbar.outline.set_edgecolor("#4a5568")

    fig.tight_layout(rect=[0.01, 0.045, 0.99, 0.98])
    fig.savefig(output_path, dpi=250, bbox_inches="tight", facecolor="#0e1117", edgecolor="none")
    plt.close(fig)
    print(f"3x3 comparison grid saved successfully: {output_path}", flush=True)


# ==============================================================================
# Sanity Assertions & Main Execution
# ==============================================================================

def run_sanity_assertions(G, depressions):
    """
    Verifies mathematical and physical invariants:
    1. Bridge edge count matches Phase 1 exactly (20 bridges).
    2. Water depths are strictly non-negative.
    3. Monotonicity in rainfall: higher rain never increases pass probability.
    4. Monotonicity in river level: higher river level never increases pass probability.
    """
    print("\nExecuting model sanity assertions...", flush=True)

    # 1. Bridge tag count check
    detected_bridges = sum(1 for _, _, _, d in G.edges(keys=True, data=True) if is_bridge(d))
    print(f"  Assertion 1: Bridge edge count = {detected_bridges} (expected 20)...", end=" ")
    assert detected_bridges == 20, f"Expected 20 bridge edges, found {detected_bridges}"
    print("PASSED")

    # 2. Non-negative depth check
    depths_sample = compute_depths(G, rainfall_mm_hr=40.0, river_level_m=80.0, depressions=depressions)
    min_depth = min(depths_sample.values())
    print(f"  Assertion 2: Minimum computed depth = {min_depth:.4f} cm (>= 0)...", end=" ")
    assert min_depth >= 0.0, f"Found negative depth: {min_depth}"
    print("PASSED")

    # 3. Monotonicity in rainfall
    d_rain_low = compute_depths(G, rainfall_mm_hr=20.0, river_level_m=78.0, depressions=depressions)
    d_rain_high = compute_depths(G, rainfall_mm_hr=70.0, river_level_m=78.0, depressions=depressions)
    for k in d_rain_low:
        assert d_rain_high[k] >= d_rain_low[k] - 1e-9, f"Rain depth non-monotonic on edge {k}"
        p_low = pass_probability(d_rain_low[k], "ambulance")
        p_high = pass_probability(d_rain_high[k], "ambulance")
        assert p_high <= p_low + 1e-9, f"Pass probability increased with rainfall on edge {k}"
    print("  Assertion 3: Monotonicity in rainfall (higher rain -> p_pass decreases)... PASSED")

    # 4. Monotonicity in river level
    d_riv_low = compute_depths(G, rainfall_mm_hr=30.0, river_level_m=76.0, depressions=depressions)
    d_riv_high = compute_depths(G, rainfall_mm_hr=30.0, river_level_m=85.0, depressions=depressions)
    for k in d_riv_low:
        assert d_riv_high[k] >= d_riv_low[k] - 1e-9, f"River depth non-monotonic on edge {k}"
        p_low = pass_probability(d_riv_low[k], "rescue_truck")
        p_high = pass_probability(d_riv_high[k], "rescue_truck")
        assert p_high <= p_low + 1e-9, f"Pass probability increased with river level on edge {k}"
    print("  Assertion 4: Monotonicity in river level (higher river -> p_pass decreases)... PASSED")


def main():
    print("=" * 65)
    print("      SAFEROUTEAI — PHASE 2: FLOOD RISK & PASSABILITY MODEL")
    print("=" * 65)

    # 1. Load road network
    G = load_graph()
    total_edges = G.number_of_edges()
    print(f"Loaded road network: {G.number_of_nodes():,} nodes, {total_edges:,} edges.")

    # 2. Precompute / load topographic depressions
    depressions = precompute_depressions(G)

    # 3. Verify sanity invariants
    run_sanity_assertions(G, depressions)

    # 4. Define Calibration Scenarios
    # Note: River level is relative to node/edge elevation (Daraganj roads range 74m - 99m).
    # Model Simplification Notice:
    # Riverine flooding: max(0, river_level - elev_min) treats all low-lying roads as
    # flooded by stage elevation. This captures the severe vulnerability of the Sangam
    # riverbank sector, serving as an effective baseline for emergency routing.
    scenarios = {
        "Dry": {"river": 75.0, "rain": 0.0},
        "Moderate": {"river": 82.0, "rain": 45.0},
        "Severe": {"river": 87.0, "rain": 90.0},
    }

    print("\n" + "=" * 65)
    print("           SCENARIO PASSABILITY EVALUATION TABLE")
    print("=" * 65)
    print(f"{'Scenario':<10} | {'River (m)':<9} | {'Rain (mm/h)':<11} | {'Vehicle':<14} | {'Closed (p<0.5)':<14} | {'Status'}")
    print("-" * 75)

    results = {}
    for scen_name, params in scenarios.items():
        riv = params["river"]
        rain = params["rain"]
        results[scen_name] = {}

        for v_name, safe_d in VEHICLES.items():
            G_assessed = passability(G, v_name, rainfall=rain, river_level=riv, depressions=depressions)
            prob_key = f"pass_probability_{v_name}"
            probs = [d[prob_key] for _, _, _, d in G_assessed.edges(keys=True, data=True)]

            closed_count = sum(1 for p in probs if p < 0.5)
            closed_pct = (closed_count / total_edges) * 100.0
            results[scen_name][v_name] = closed_pct

            status_desc = "Optimal (Green)" if closed_pct < 2.0 else ("Moderate Impact" if closed_pct < 30.0 else "Heavy Inundation")
            print(f"{scen_name:<10} | {riv:<9.1f} | {rain:<11.1f} | {v_name:<14} | {closed_pct:6.1f}% ({closed_count:4d}) | {status_desc}")
        print("-" * 75)

    # Verify Checkpoints
    amb_mod = results["Moderate"]["ambulance"]
    res_mod = results["Moderate"]["rescue_truck"]
    dry_max = max(results["Dry"].values())
    sev_amb = results["Severe"]["ambulance"]

    print("\nCheckpoint Validations:")
    print(f"  [1] Moderate Scenario: Ambulance ({amb_mod:.1f}%) vs Rescue Truck ({res_mod:.1f}%) closures -> "
          f"{'PASSED (Noticeably higher)' if amb_mod > res_mod * 2 else 'FAILED'}")
    print(f"  [2] Dry Scenario: Maximum vehicle closure = {dry_max:.1f}% -> "
          f"{'PASSED (Almost all green)' if dry_max < 2.0 else 'FAILED'}")
    print(f"  [3] Severe Scenario: Ambulance closure = {sev_amb:.1f}% -> "
          f"{'PASSED (Substantial red, but not 100%)' if 20.0 < sev_amb < 95.0 else 'FAILED'}")

    # 5. Render and save the 3x3 comparison grid
    generate_3x3_grid(G, scenarios, depressions)

    print("\nPhase 2 execution complete.")


if __name__ == "__main__":
    main()
