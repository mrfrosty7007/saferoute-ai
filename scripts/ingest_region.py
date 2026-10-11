"""
Rakshapath - Regional Ingestion CLI
Author: Rakshapath Team

Command-line utility for listing the region catalog and checking already-prepared
regional assets. New regional data preparation is currently available through
the offline Python pipeline API, not this CLI.

Usage examples:
  python scripts/ingest_region.py --list
  python scripts/ingest_region.py --validate-only --region daraganj_prayagraj
"""
from __future__ import annotations

import argparse
import os
import sys

# Ensure repository root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from saferoute.regions import registry


def main():
    parser = argparse.ArgumentParser(
        description="List registered regions and validate existing regional assets"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all registered regions and their support status",
    )
    parser.add_argument(
        "--region",
        type=str,
        help="Region ID to inspect or validate (e.g. daraganj_prayagraj)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate existing assets for the specified region without re-downloading",
    )
    args = parser.parse_args()

    if args.list:
        print("=" * 80)
        print(" Rakshapath - Registered Regions Catalog")
        print("=" * 80)
        for r in registry.list_regions():
            icon = "[READY]" if r.is_routable else "[PLAN]"
            print(f" {icon:<7} [{r.region_id:<22}] {r.display_name}")
            print(f"         State: {r.state} | District: {r.district} | Status: {r.status.value}")
            print(f"         Bounds: {r.bounds.min_lat:.3f}N..{r.bounds.max_lat:.3f}N, {r.bounds.min_lon:.3f}E..{r.bounds.max_lon:.3f}E")
            print(f"         Graph: {r.graph_file}")
            print("-" * 80)
        return 0

    if not args.region:
        parser.print_help()
        return 1

    reg = registry.get(args.region)
    if not reg:
        print(f"Error: Region '{args.region}' is not registered in RegionRegistry.", file=sys.stderr)
        return 1

    print(f"Selected Region: {reg.display_name} ({reg.region_id})")
    print(f"  Administrative: {reg.state} -> {reg.district} -> {reg.city}")
    print(f"  Status: {reg.status.value} ({reg.status_description})")

    if args.validate_only:
        print("\nValidating regional assets on disk...")
        if not os.path.exists(reg.graph_file):
            print(f"  [MISSING] Graph file missing: {reg.graph_file}")
            return 2
        print(f"  [FOUND]   Graph file exists: {reg.graph_file} ({os.path.getsize(reg.graph_file):,} bytes)")

        if reg.depressions_file and os.path.exists(reg.depressions_file):
            print(f"  [FOUND]   Depressions cache exists: {reg.depressions_file} ({os.path.getsize(reg.depressions_file):,} bytes)")
        else:
            print(f"  [WARN]    Depressions cache not found or unconfigured: {reg.depressions_file}")

        print("Validation complete.")
        return 0

    print("\nThis CLI does not download or ingest regional data.")
    print("Use --validate-only to verify existing local assets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
