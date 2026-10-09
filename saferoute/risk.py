"""
SafeRouteAI - Phase 2 Flood Risk & Passability Modeling
Author: SafeRouteAI Team

Responsible for:
1. Robust bridge classification (handling 'yes', 'viaduct', lists, and stringified lists).
2. Topographic depression precomputation and caching via metric cKDTree.
3. Flood water depth calculation combining riverine flooding and rainfall depression ponding.
   - NOTE: Riverine depth is a regional stage simplification (roads below river level
     are treated as flooded without solving 2D hydrodynamic flow equations).
4. Soft logistic sigmoid passability probability computation for emergency vehicles.
5. Invariant sanity assertions (bridge count == 20, non-negative depth, monotonicity).
6. Multi-scenario evaluation (Dry, Moderate, Severe).
"""

import ast
import os
import pickle
from typing import Any, Dict, List, Optional, Tuple, Union

import networkx as nx
import numpy as np
from scipy.spatial import cKDTree

from .config import (
    BRIDGE_CLEARANCE_MARGIN_M,
    CENTER_LAT,
    CENTER_LON,
    CM_PER_METER,
    DEPRESSION_RADIUS_M,
    DEPRESSIONS_CACHE_FILE,
    K_RAIN_FACTOR,
    METERS_PER_DEG_LAT,
    METERS_PER_DEG_LON,
    PROBABILITY_EPSILON,
    SCENARIOS,
    SIGMOID_SCALE_S,
    VEHICLES,
)


def is_bridge(data: Dict[str, Any]) -> bool:
    """
    Classify whether an OSM edge represents a bridge structure.
    Handles 'yes', 'viaduct', 'aqueduct', Python lists, and GraphML stringified lists.

    Args:
        data: Edge attribute dictionary.

    Returns:
        True if the edge is a bridge structure, False otherwise.
    """
    val = data.get("bridge")
    if val is None or val is False or val == "":
        return False

    if isinstance(val, (list, tuple, set)):
        return any(str(v).strip().lower() not in ("no", "false", "none", "", "0") for v in val)

    s = str(val).strip().lower()
    if s in ("no", "false", "none", "0", "[]", "['no']", '["no"]'):
        return False

    if s.startswith("[") and s.endswith("]"):
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, (list, tuple)):
                return any(str(v).strip().lower() not in ("no", "false", "none", "", "0") for v in parsed)
        except Exception:
            pass
        clean = s.replace("[", "").replace("]", "").replace("'", "").replace('"', "").strip()
        return clean not in ("no", "false", "none", "", "0")

    return True


def precompute_depressions(
    G: nx.MultiDiGraph,
    radius_m: float = DEPRESSION_RADIUS_M,
    cache_path: str = DEPRESSIONS_CACHE_FILE,
) -> Dict[Tuple[int, int, int], float]:
    """
    Precompute topographic depressions for all edges in G within radius_m.
    Caches the result to disk to ensure instantaneous reloading.

    Args:
        G: Road network graph with 'elev_min' and node coordinates.
        radius_m: Neighborhood radius in meters.
        cache_path: Path to depressions.pkl cache file.

    Returns:
        Dictionary mapping edge key (u, v, k) to depression in meters.
    """
    if os.path.exists(cache_path):
        print(f"Loading cached topographic depressions from {cache_path}...", flush=True)
        with open(cache_path, "rb") as f:
            depressions = pickle.load(f)
        if len(depressions) == G.number_of_edges():
            return depressions
        print("  Cache size mismatch. Recomputing depressions...", flush=True)

    print(f"Precomputing edge topographic depressions (radius: {radius_m}m)...", flush=True)

    edge_keys: List[Tuple[int, int, int]] = []
    midpoint_coords: List[Tuple[float, float]] = []
    elev_mins: List[float] = []

    for u, v, k, d in G.edges(keys=True, data=True):
        lat1, lon1 = G.nodes[u]["y"], G.nodes[u]["x"]
        lat2, lon2 = G.nodes[v]["y"], G.nodes[v]["x"]
        mid_lat = (lat1 + lat2) / 2.0
        mid_lon = (lon1 + lon2) / 2.0

        x_m = (mid_lon - CENTER_LON) * METERS_PER_DEG_LON
        y_m = (mid_lat - CENTER_LAT) * METERS_PER_DEG_LAT

        edge_keys.append((u, v, k))
        midpoint_coords.append((x_m, y_m))
        elev_mins.append(float(d["elev_min"]))

    coords_arr = np.array(midpoint_coords)
    elevs_arr = np.array(elev_mins)

    tree = cKDTree(coords_arr)
    depressions: Dict[Tuple[int, int, int], float] = {}

    for idx, pt in enumerate(coords_arr):
        nbr_indices = tree.query_ball_point(pt, r=radius_m)
        local_mean = elevs_arr[nbr_indices].mean()
        depressions[edge_keys[idx]] = max(0.0, float(local_mean - elevs_arr[idx]))

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "wb") as f:
        pickle.dump(depressions, f)
    print(f"Saved {len(depressions):,} edge depressions to cache: {cache_path}.", flush=True)

    return depressions


def compute_depths(
    G: nx.MultiDiGraph,
    rainfall_mm_hr: float,
    river_level_m: float,
    depressions: Optional[Dict[Tuple[int, int, int], float]] = None,
    k: float = K_RAIN_FACTOR,
) -> Dict[Tuple[int, int, int], float]:
    """
    Compute flood water depth in centimeters for every edge in G.

    Components:
    - Riverine flooding: max(0, river_level_m - elev_min) * 100
    - Rainfall ponding: k * rainfall_mm_hr * (1.0 + depression)
    - Bridges: exempt from depth formula unless river level exceeds
      approach endpoint elevations plus BRIDGE_CLEARANCE_MARGIN_M.

    Args:
        G: Road network graph.
        rainfall_mm_hr: Rain intensity in mm/hr.
        river_level_m: Regional river stage in meters.
        depressions: Precomputed edge depressions dictionary.
        k: Tunable rainfall ponding coefficient.

    Returns:
        Dictionary mapping edge key (u, v, k) to water depth in cm.
    """
    if depressions is None:
        depressions = precompute_depressions(G)

    depths: Dict[Tuple[int, int, int], float] = {}
    for u, v, key, data in G.edges(keys=True, data=True):
        edge_key = (u, v, key)
        elev_min = float(data["elev_min"])

        if is_bridge(data):
            elev_u = float(G.nodes[u]["elevation"])
            elev_v = float(G.nodes[v]["elevation"])
            bridge_deck_thresh = max(elev_u, elev_v) + BRIDGE_CLEARANCE_MARGIN_M

            if river_level_m > bridge_deck_thresh:
                depth_cm = (river_level_m - bridge_deck_thresh) * CM_PER_METER
            else:
                depth_cm = 0.0
        else:
            riverine_depth_cm = max(0.0, river_level_m - elev_min) * CM_PER_METER
            depression_m = depressions.get(edge_key, 0.0)
            rain_depth_cm = k * float(rainfall_mm_hr) * (1.0 + depression_m)
            depth_cm = riverine_depth_cm + rain_depth_cm

        depths[edge_key] = max(0.0, float(depth_cm))

    return depths


def pass_probability(
    depth_cm: Union[float, np.ndarray],
    vehicle: str = "ambulance",
    scale_s: float = SIGMOID_SCALE_S,
) -> Union[float, np.ndarray]:
    """
    Evaluate logistic sigmoid passability probability p in [0, 1] for a given depth and vehicle.
    p = 1 / (1 + exp((depth - safe_depth) / s))

    Args:
        depth_cm: Water depth in cm (scalar or numpy array).
        vehicle: Vehicle identifier ('ambulance', 'fire_tender', 'rescue_truck').
        scale_s: Softness width parameter in cm.

    Returns:
        Probability value(s) in [0.0, 1.0].
    """
    if vehicle not in VEHICLES:
        raise ValueError(f"Unknown vehicle '{vehicle}'. Must be one of: {list(VEHICLES.keys())}")

    safe_depth = VEHICLES[vehicle]
    diff = (np.asarray(depth_cm, dtype=float) - safe_depth) / float(scale_s)
    diff = np.clip(diff, -50.0, 50.0)
    p = 1.0 / (1.0 + np.exp(diff))

    if np.isscalar(depth_cm):
        return float(p)
    return p


def passability(
    G: nx.MultiDiGraph,
    vehicle: str,
    rainfall: float,
    river_level: float,
    depressions: Optional[Dict[Tuple[int, int, int], float]] = None,
    k: float = K_RAIN_FACTOR,
) -> nx.MultiDiGraph:
    """
    Primary API: Computes water depth and pass probability for all edges,
    writing 'water_depth_cm' and 'pass_probability_<vehicle>' onto a copy of G.

    Args:
        G: Base road network.
        vehicle: Vehicle identifier.
        rainfall: Rainfall intensity in mm/hr.
        river_level: River stage in meters.
        depressions: Precomputed edge depressions dictionary.
        k: Tunable rainfall ponding coefficient.

    Returns:
        Deep copy of G with enriched edge attributes.
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


def evaluate_scenarios(
    G: nx.MultiDiGraph,
    scenarios: Dict[str, Dict[str, float]] = SCENARIOS,
    depressions: Optional[Dict[Tuple[int, int, int], float]] = None,
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Evaluate passability across scenarios and vehicles, returning closure counts and percentages.

    Returns:
        Nested dict: scenarios -> vehicles -> {"closed_count": int, "closed_pct": float, ...}
    """
    if depressions is None:
        depressions = precompute_depressions(G)

    total_edges = G.number_of_edges()
    results: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for scen_name, params in scenarios.items():
        riv = params["river"]
        rain = params["rain"]
        results[scen_name] = {}

        for v_name in VEHICLES:
            G_eval = passability(G, v_name, rainfall=rain, river_level=riv, depressions=depressions)
            prob_key = f"pass_probability_{v_name}"
            probs = [d[prob_key] for _, _, _, d in G_eval.edges(keys=True, data=True)]

            closed_count = sum(1 for p in probs if p < 0.5)
            closed_pct = (closed_count / total_edges) * 100.0 if total_edges > 0 else 0.0

            results[scen_name][v_name] = {
                "river_m": riv,
                "rain_mm_hr": rain,
                "closed_count": closed_count,
                "closed_pct": closed_pct,
                "total_edges": total_edges,
            }

    return results


def run_sanity_assertions(
    G: nx.MultiDiGraph,
    depressions: Optional[Dict[Tuple[int, int, int], float]] = None,
) -> None:
    """
    Verify model mathematical and topological sanity invariants:
    1. Bridge edge count matches Phase 1 exactly (20 bridges).
    2. Water depths are strictly non-negative.
    3. Monotonicity in rainfall: higher rain never increases pass probability.
    4. Monotonicity in river level: higher river level never increases pass probability.
    """
    print("\nExecuting model sanity assertions...", flush=True)

    # 1. Bridge count check
    detected_bridges = sum(1 for _, _, _, d in G.edges(keys=True, data=True) if is_bridge(d))
    print(f"  Assertion 1: Bridge edge count = {detected_bridges} (expected 20)...", end=" ")
    assert detected_bridges == 20, f"Expected 20 bridge edges, found {detected_bridges}"
    print("PASSED")

    if depressions is None:
        depressions = precompute_depressions(G)

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
