"""
SafeRouteAI - Phase 2 Runner Script: Flood Risk & Vehicle Passability Modeling
Author: SafeRouteAI Team

Usage:
    python scripts/run_risk.py
"""

import os
import sys

# Ensure repository root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from saferoute.config import SCENARIOS, VEHICLES
from saferoute.data import load_cached_graph
from saferoute.risk import (
    evaluate_scenarios,
    precompute_depressions,
    run_sanity_assertions,
)
from saferoute.viz import plot_3x3_grid


def main() -> None:
    """Execute Phase 2 pipeline: load cached graph, run assertions, evaluate scenarios, and render 3x3 grid."""
    print("=" * 65)
    print("      SAFEROUTEAI — PHASE 2: FLOOD RISK & PASSABILITY MODEL")
    print("=" * 65)

    G = load_cached_graph()
    total_edges = G.number_of_edges()
    print(f"Loaded road network: {G.number_of_nodes():,} nodes, {total_edges:,} edges.")

    depressions = precompute_depressions(G)
    run_sanity_assertions(G, depressions)

    print("\n" + "=" * 65)
    print("           SCENARIO PASSABILITY EVALUATION TABLE")
    print("=" * 65)
    print(f"{'Scenario':<10} | {'River (m)':<9} | {'Rain (mm/h)':<11} | {'Vehicle':<14} | {'Closed (p<0.5)':<14} | {'Status'}")
    print("-" * 75)

    results = evaluate_scenarios(G, SCENARIOS, depressions)

    for scen_name, v_data in results.items():
        for v_name, metrics in v_data.items():
            riv = metrics["river_m"]
            rain = metrics["rain_mm_hr"]
            closed_pct = metrics["closed_pct"]
            closed_count = metrics["closed_count"]

            status_desc = (
                "Optimal (Green)"
                if closed_pct < 2.0
                else ("Moderate Impact" if closed_pct < 30.0 else "Heavy Inundation")
            )
            print(
                f"{scen_name:<10} | {riv:<9.1f} | {rain:<11.1f} | {v_name:<14} | "
                f"{closed_pct:6.1f}% ({closed_count:4d}) | {status_desc}"
            )
        print("-" * 75)

    # Checkpoint verifications
    amb_mod = results["Moderate"]["ambulance"]["closed_pct"]
    res_mod = results["Moderate"]["rescue_truck"]["closed_pct"]
    dry_max = max(v["closed_pct"] for v in results["Dry"].values())
    sev_amb = results["Severe"]["ambulance"]["closed_pct"]

    print("\nCheckpoint Validations:")
    print(
        f"  [1] Moderate Scenario: Ambulance ({amb_mod:.1f}%) vs Rescue Truck ({res_mod:.1f}%) closures -> "
        f"{'PASSED (Noticeably higher)' if amb_mod > res_mod * 2 else 'FAILED'}"
    )
    print(
        f"  [2] Dry Scenario: Maximum vehicle closure = {dry_max:.1f}% -> "
        f"{'PASSED (Almost all green)' if dry_max < 2.0 else 'FAILED'}"
    )
    print(
        f"  [3] Severe Scenario: Ambulance closure = {sev_amb:.1f}% -> "
        f"{'PASSED (Substantial red, but not 100%)' if 20.0 < sev_amb < 95.0 else 'FAILED'}"
    )

    plot_3x3_grid(G, SCENARIOS, depressions)

    print("\nPhase 2 execution complete.")


if __name__ == "__main__":
    main()
