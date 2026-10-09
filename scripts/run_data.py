"""
SafeRouteAI - Phase 1 Runner Script: Data Ingestion & Elevation Enrichment
Author: SafeRouteAI Team

Usage:
    python scripts/run_data.py
"""

import os
import sys

# Ensure repository root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from saferoute.data import get_graph_summary, load_or_create_graph
from saferoute.viz import plot_elevation_network


def main() -> None:
    """Execute Phase 1 data pipeline: load graph, enrich with elevation, cache, plot, and summarize."""
    print("=" * 65)
    print("      SAFEROUTEAI — PHASE 1: DATA INGESTION & ELEVATION")
    print("=" * 65)

    G, filled_nulls = load_or_create_graph()
    plot_elevation_network(G)

    stats = get_graph_summary(G, filled_nulls_count=filled_nulls)

    print("\n" + "=" * 55)
    print("           SAFEROUTEAI - PHASE 1 SUMMARY REPORT")
    print("=" * 55)
    print(f"  Total Nodes:                {stats['node_count']:,}")
    print(f"  Total Edges:                {stats['edge_count']:,}")
    print(f"  Minimum Node Elevation:     {stats['min_elevation_m']:.2f} m")
    print(f"  Maximum Node Elevation:     {stats['max_elevation_m']:.2f} m")
    print(f"  Mean Node Elevation:        {stats['mean_elevation_m']:.2f} m")
    print(f"  Null Elevations Filled:     {stats['filled_nulls']:,}")
    print(f"  Bridge Edges Tagged:        {stats['bridge_edges']:,}")
    print(f"  Tunnel Edges Tagged:        {stats['tunnel_edges']:,}")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
