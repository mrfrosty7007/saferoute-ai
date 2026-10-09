"""
SafeRouteAI - Phase 3 Runner Script: Risk-Aware Route Demonstration & Benchmarking
Author: SafeRouteAI Team

Usage:
    python scripts/run_routing.py
"""

import json
import math
import os
import sys
from typing import Any, Dict, List, Tuple

import numpy as np

# Ensure repository root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from saferoute.config import (
    DEMO_PLOT_FILE,
    DEMO_SCENARIOS_FILE,
    METERS_PER_DEG_LAT,
    METERS_PER_DEG_LON,
    MIN_OD_DISTANCE_M,
    NUM_OD_SAMPLES,
    SCENARIOS,
)
from saferoute.data import load_cached_graph
from saferoute.risk import passability, precompute_depressions
from saferoute.routing import RouteResult, create_routing_engine
from saferoute.viz import plot_route_comparison


def sample_reproducible_od_pairs(
    node_ids: List[int],
    coords: Dict[int, Tuple[float, float]],
    num_samples: int = NUM_OD_SAMPLES,
    min_dist_m: float = MIN_OD_DISTANCE_M,
    seed: int = 42,
) -> List[Tuple[int, int, float]]:
    """
    Sample reproducible origin-destination pairs at least min_dist_m apart using seed 42.

    Args:
        node_ids: List of candidate node IDs in the SCC.
        coords: Dictionary mapping node ID to (x, y) coordinates in degrees.
        num_samples: Number of pairs to sample.
        min_dist_m: Minimum euclidean distance in meters.
        seed: Random number generator seed.

    Returns:
        List of (origin_node, destination_node, distance_meters) tuples.
    """
    rng = np.random.default_rng(seed)
    pairs: List[Tuple[int, int, float]] = []

    while len(pairs) < num_samples:
        u = int(rng.choice(node_ids))
        v = int(rng.choice(node_ids))
        if u == v:
            continue

        x1, y1 = coords[u]
        x2, y2 = coords[v]
        dist_m = math.hypot((x2 - x1) * METERS_PER_DEG_LON, (y2 - y1) * METERS_PER_DEG_LAT)

        if dist_m >= min_dist_m:
            pairs.append((u, v, dist_m))

    return pairs


def score_and_rank_scenarios(
    pairs: List[Tuple[int, int, float]],
    eng_amb: Any,
    eng_truck: Any,
) -> List[Dict[str, Any]]:
    """
    Evaluate and rank sampled OD pairs:
    Favors pairs where:
    1. Ambulance SafeRoute achieves high reliability while baseline is low / flooded.
    2. Ambulance route and Rescue Truck route differ (demonstrating vehicle adaptation).
    3. Trade-off between distance/ETA detour and safety gain is realistic and convincing.

    Returns:
        Sorted list of candidate dictionaries in descending order of quality.
    """
    candidates: List[Dict[str, Any]] = []

    for u, v, dist_m in pairs:
        try:
            amb_routes = eng_amb.route_all(u, v)
            truck_routes = eng_truck.route_all(u, v)

            amb_prim: RouteResult = amb_routes["primary"]
            amb_back: RouteResult = amb_routes["backup"]
            amb_base: RouteResult = amb_routes["baseline"]
            truck_prim: RouteResult = truck_routes["primary"]

            rel_gain = amb_prim.reliability - amb_base.reliability
            rel_ratio = amb_prim.reliability / max(1e-6, amb_base.reliability)
            has_impass = amb_base.has_impassable
            truck_diff = (amb_prim.nodes != truck_prim.nodes)

            # Detour ratio (ETA increase)
            eta_detour = max(0.0, (amb_prim.eta_min - amb_base.eta_min) / max(0.1, amb_base.eta_min))

            # Composite ranking score:
            # - Primary weight on absolute reliability gain & flooded baseline
            # - Bonus for vehicle differentiation (ambulance vs truck taking different paths)
            # - Preference for routes where SafeRoute maintains high survival (>10%)
            # - Slight penalty on extreme excessive detour times (>3x)
            score = (
                (rel_gain * 4.0)
                + (1.5 if has_impass else 0.0)
                + (1.0 if truck_diff else 0.0)
                + (min(1.0, amb_prim.reliability))
                - (0.08 * min(5.0, eta_detour))
            )

            candidates.append({
                "score": float(score),
                "origin_node": u,
                "destination_node": v,
                "euclidean_distance_km": round(dist_m / 1000.0, 3),
                "rel_gain": float(rel_gain),
                "rel_ratio": float(rel_ratio),
                "truck_diff": bool(truck_diff),
                "ambulance_primary": amb_prim.to_dict(),
                "ambulance_backup": amb_back.to_dict(),
                "ambulance_baseline": amb_base.to_dict(),
                "rescue_truck_primary": truck_prim.to_dict(),
                "objects": {
                    "amb_prim": amb_prim,
                    "amb_back": amb_back,
                    "amb_base": amb_base,
                    "truck_prim": truck_prim,
                },
            })
        except Exception:
            continue

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates


def main() -> None:
    """Execute Phase 3 demonstration runner, benchmark evaluation, and plot generation."""
    print("=" * 75)
    print("      SAFEROUTEAI — PHASE 3: RISK-AWARE ROUTING ENGINE BENCHMARK")
    print("=" * 75)

    # 1. Load road network & depressions
    G = load_cached_graph()
    depressions = precompute_depressions(G)

    # 2. Configure Moderate Scenario
    scen = SCENARIOS["Moderate"]
    riv_m = scen["river"]
    rain_mm = scen["rain"]
    print(f"\nEvaluation Flood Scenario: MODERATE (River Stage = {riv_m:.1f} m, Rain = {rain_mm:.1f} mm/hr)")

    # 3. Initialize routing engines for Ambulance and Rescue Truck
    print("Initializing risk-aware routing engines for Ambulance and Rescue Truck...", flush=True)
    eng_amb = create_routing_engine(G, vehicle="ambulance", rainfall_mm_hr=rain_mm, river_level_m=riv_m, depressions=depressions)
    eng_truck = create_routing_engine(G, vehicle="rescue_truck", rainfall_mm_hr=rain_mm, river_level_m=riv_m, depressions=depressions)

    scc_nodes = eng_amb.node_ids
    coords = {n: (eng_amb.graph.nodes[n]["x"], eng_amb.graph.nodes[n]["y"]) for n in scc_nodes}
    print(f"Routing graph prepared: {len(scc_nodes):,} strongly connected nodes, {eng_amb.graph.number_of_edges():,} directed edges.")

    # 4. Sample 300 reproducible OD pairs (seed=42, >= 1.5 km apart)
    print(f"Sampling {NUM_OD_SAMPLES} reproducible OD pairs at least {MIN_OD_DISTANCE_M / 1000.0:.1f} km apart (seed=42)...", flush=True)
    pairs = sample_reproducible_od_pairs(scc_nodes, coords, num_samples=NUM_OD_SAMPLES, min_dist_m=MIN_OD_DISTANCE_M, seed=42)

    # 5. Evaluate and rank pairs
    print(f"Routing all {len(pairs)} pairs across Ambulance, Rescue Truck, and Baseline...", flush=True)
    ranked_candidates = score_and_rank_scenarios(pairs, eng_amb, eng_truck)

    if not ranked_candidates:
        raise RuntimeError("No feasible route candidates could be found. Check graph connectivity.")

    top_5 = ranked_candidates[:5]

    # 6. Print Benchmark Summary Table
    print("\n" + "=" * 90)
    print("                   TOP 5 EMERGENCY ROUTING DEMONSTRATION SCENARIOS")
    print("=" * 90)
    print(f"{'Rank':<5} | {'Origin -> Dest':<24} | {'Dist(km)':<8} | {'SafeRoute Amb':<22} | {'Baseline (Naive)':<22} | {'Truck Diff'}")
    print(f"{'':<5} | {'':<24} | {'':<8} | {'Rel% | ETA | Weak-p':<22} | {'Rel% | ETA | Flooded':<22} | {''}")
    print("-" * 90)

    serializable_top_5 = []

    for rank, c in enumerate(top_5, 1):
        p = c["ambulance_primary"]
        b = c["ambulance_baseline"]
        p_weak_p = p["weakest_segment"][2] if p["weakest_segment"] else 1.0
        b_flooded = "Yes" if b["has_impassable"] else "No"
        od_str = f"{c['origin_node']} -> {c['destination_node']}"

        p_summary = f"{p['reliability'] * 100:5.1f}% | {p['eta_min']:4.1f}m | {p_weak_p:.2f}"
        b_summary = f"{b['reliability'] * 100:5.1f}% | {b['eta_min']:4.1f}m | {b_flooded}"

        print(f"#{rank:<4} | {od_str:<24} | {c['euclidean_distance_km']:<8.2f} | {p_summary:<22} | {b_summary:<22} | {str(c['truck_diff']):<10}")

        # Prepare JSON record (excluding non-serializable objects)
        record = {
            "rank": rank,
            "score": c["score"],
            "origin_node": c["origin_node"],
            "destination_node": c["destination_node"],
            "euclidean_distance_km": c["euclidean_distance_km"],
            "reliability_gain": c["rel_gain"],
            "truck_differs": c["truck_diff"],
            "flood_conditions": {
                "scenario": "Moderate",
                "river_level_m": riv_m,
                "rainfall_mm_hr": rain_mm,
            },
            "ambulance_primary": c["ambulance_primary"],
            "ambulance_backup": c["ambulance_backup"],
            "ambulance_baseline": c["ambulance_baseline"],
            "rescue_truck_primary": c["rescue_truck_primary"],
        }
        serializable_top_5.append(record)

    print("-" * 90)

    # 7. Save top 5 scenarios to data/demo_scenarios.json
    os.makedirs(os.path.dirname(DEMO_SCENARIOS_FILE), exist_ok=True)
    with open(DEMO_SCENARIOS_FILE, "w", encoding="utf-8") as f:
        json.dump(serializable_top_5, f, indent=2)
    print(f"\nTop 5 scenario benchmarks saved to: {DEMO_SCENARIOS_FILE}")

    # 8. Render visualization for the #1 best scenario
    best = top_5[0]
    best_objs = best["objects"]
    print(f"\nGenerating visualization for Rank #1 scenario (O={best['origin_node']}, D={best['destination_node']})...")

    # Re-obtain enriched graph for ambulance under moderate conditions for plotting background
    G_plot = passability(G, vehicle="ambulance", rainfall=rain_mm, river_level=riv_m, depressions=depressions)

    plot_route_comparison(
        G_assessed=G_plot,
        primary_route=best_objs["amb_prim"],
        backup_route=best_objs["amb_back"],
        baseline_route=best_objs["amb_base"],
        vehicle="ambulance",
        rainfall_mm_hr=rain_mm,
        river_level_m=riv_m,
        output_path=DEMO_PLOT_FILE,
    )

    print("\nPhase 3 execution complete.")


if __name__ == "__main__":
    main()
