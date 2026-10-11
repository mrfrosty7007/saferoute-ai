"""
Rakshapath - Automated Regional Routing Benchmark Suite
Author: Rakshapath Team

Performs an opt-in, rigorous benchmark on a specified region:
- Loads regional graph and measures asset loading latency, traced Python allocation,
  and process RSS where a supported OS interface is available.
- Verifies graph elevation and depression coverage rates.
- Evaluates 300 deterministic origin-destination pairs sampled with seed 42 (min distance >= 1.5 km).
- Measures first-route latency vs subsequent-route latency for Ambulance and Rescue Truck.
- Tracks routing success rate, primary/backup overlap, and reliability gains.
- Exports reproducible JSON benchmark results and an informative multi-panel plot.

Usage:
    python scripts/run_benchmarks.py [--region REGION_ID] [--samples 300] [--min-dist 1500] [--seed 42]
"""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import platform
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np

# Add repository root to Python path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from saferoute.regions import DEFAULT_REGION_ID, get_registry
from services.contracts import Place, RouteRequest, RoutingError
from services.service import compute_routes, load_engine


def _process_rss_mb() -> float | None:
    """Return current process resident memory in MiB where supported."""
    try:
        if sys.platform == "win32":
            class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_ulong),
                    ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                    ("PrivateUsage", ctypes.c_size_t),
                ]

            counters = PROCESS_MEMORY_COUNTERS_EX()
            counters.cb = ctypes.sizeof(counters)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            psapi.GetProcessMemoryInfo.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX),
                ctypes.c_ulong,
            ]
            psapi.GetProcessMemoryInfo.restype = ctypes.c_int
            ok = psapi.GetProcessMemoryInfo(
                kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
            )
            return counters.WorkingSetSize / (1024 * 1024) if ok else None

        statm = "/proc/self/statm"
        if os.path.exists(statm):
            with open(statm, "r", encoding="ascii") as f:
                resident_pages = int(f.read().split()[1])
            return resident_pages * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024)

        try:
            import psutil
            return psutil.Process().memory_info().rss / (1024 * 1024)
        except ImportError:
            return None
    except (OSError, AttributeError, ValueError, IndexError):
        return None


def sample_deterministic_od_pairs(
    node_ids: List[int],
    coords: Dict[int, Tuple[float, float]],
    m_per_deg_lat: float,
    m_per_deg_lon: float,
    num_samples: int = 300,
    min_dist_m: float = 1500.0,
    seed: int = 42,
) -> List[Tuple[int, int, float]]:
    """
    Sample exactly num_samples OD pairs at least min_dist_m apart using seed 42.
    """
    rng = np.random.default_rng(seed)
    pairs: List[Tuple[int, int, float]] = []
    attempts = 0
    max_attempts = num_samples * 200

    while len(pairs) < num_samples and attempts < max_attempts:
        attempts += 1
        u = int(rng.choice(node_ids))
        v = int(rng.choice(node_ids))
        if u == v:
            continue

        x1, y1 = coords[u]  # lon, lat
        x2, y2 = coords[v]

        dx = (x2 - x1) * m_per_deg_lon
        dy = (y2 - y1) * m_per_deg_lat
        dist_m = math.hypot(dx, dy)

        if dist_m >= min_dist_m:
            pairs.append((u, v, dist_m))

    return pairs


def run_benchmark(
    region_id: str = DEFAULT_REGION_ID,
    num_samples: int = 300,
    min_dist_m: float = 1500.0,
    seed: int = 42,
    output_json: str | None = None,
    output_plot: str | None = None,
) -> Dict[str, Any]:
    """Execute complete benchmark suite and output reproducible metrics."""
    reg = get_registry().get_region(region_id)
    if reg is None:
        print(f"[ERROR] Region '{region_id}' not found in registry.")
        sys.exit(1)

    print(f"==================================================================")
    print(f"Rakshapath Nationwide Regional Benchmark: {reg.display_name}")
    print(f"Region ID: {reg.region_id} | Status: {reg.status.name}")
    print(f"State: {reg.state} | District: {reg.district}")
    print(f"Target Samples: {num_samples} OD pairs | Min Distance: {min_dist_m}m | Seed: {seed}")
    print(f"==================================================================")

    # 1. Measure loading latency, Python allocations, and process RSS.
    rss_before_mb = _process_rss_mb()
    tracemalloc.start()
    t_load_start = time.perf_counter()
    engine = load_engine(region_id)
    load_time_s = time.perf_counter() - t_load_start
    _current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rss_after_load_mb = _process_rss_mb()

    traced_peak_mb = peak_mem / (1024 * 1024)
    rss_delta_mb = (
        round(rss_after_load_mb - rss_before_mb, 2)
        if rss_before_mb is not None and rss_after_load_mb is not None
        else None
    )
    print(
        f"[LOAD] Engine/assets in {load_time_s:.3f}s; traced Python peak: {traced_peak_mb:.2f} MiB; "
        f"process RSS before/after: {rss_before_mb!s}/{rss_after_load_mb!s} MiB "
        f"(delta: {rss_delta_mb!s} MiB). RSS is an OS snapshot, not a memory ceiling."
    )

    # 2. Inspect Network and Data Coverage
    G = engine.G_base
    num_nodes = G.number_of_nodes()
    num_edges = G.number_of_edges()

    edges_with_elev = sum(1 for _, _, d in G.edges(data=True) if "elev_min" in d or "elev_start" in d)
    elev_coverage_pct = (edges_with_elev / num_edges * 100.0) if num_edges > 0 else 0.0

    depressions = engine.depressions
    dep_count = len(depressions) if depressions else 0
    dep_coverage_pct = (dep_count / num_edges * 100.0) if num_edges > 0 else 0.0

    print(f"[NETWORK] Nodes: {num_nodes:,} | Edges: {num_edges:,}")
    print(f"[COVERAGE] Elevation coverage: {elev_coverage_pct:.1f}% | Depression coverage: {dep_coverage_pct:.1f}%")

    # 3. Extract Candidate Coordinates and Sample OD Pairs
    node_coords: Dict[int, Tuple[float, float]] = {}
    for n, d in G.nodes(data=True):
        node_coords[n] = (float(d["x"]), float(d["y"]))  # lon, lat

    import networkx as nx

    largest_scc = max(nx.strongly_connected_components(G), key=len)
    scc_nodes = list(largest_scc)
    pairs = sample_deterministic_od_pairs(
        scc_nodes,
        node_coords,
        m_per_deg_lat=reg.meters_per_deg_lat,
        m_per_deg_lon=reg.meters_per_deg_lon,
        num_samples=num_samples,
        min_dist_m=min_dist_m,
        seed=seed,
    )
    print(f"[SAMPLING] Sampled {len(pairs)} pairs meeting >= {min_dist_m}m criteria.")

    # 4. Benchmark Routes for Ambulance and Rescue Truck
    vehicles = ["ambulance", "rescue_truck"]
    vehicle_results: Dict[str, Dict[str, Any]] = {}

    for v_key in vehicles:
        print(f"\n[EVALUATION] Benchmarking Vehicle: {v_key.upper()}...")
        latencies_ms: List[float] = []
        primary_reliabilities: List[float] = []
        baseline_reliabilities: List[float] = []
        overlaps: List[float] = []
        distances_km: List[float] = []
        unreachable_count = 0

        for i, (u, v, dist_m) in enumerate(pairs):
            u_lon, u_lat = node_coords[u]
            v_lon, v_lat = node_coords[v]

            req = RouteRequest(
                origin=Place(f"Node_{u}", u_lat, u_lon),
                destination=Place(f"Node_{v}", v_lat, v_lon),
                vehicle=v_key,
                hazard="flood",
                params={"rainfall": 50.0, "river_level": 84.7},
                severity="High",
                region_id=region_id,
            )

            t_start = time.perf_counter()
            try:
                res = compute_routes(req, engine=engine)
                route_time_ms = (time.perf_counter() - t_start) * 1000.0
                latencies_ms.append(route_time_ms)

                if res.primary is not None:
                    primary_reliabilities.append(res.primary.reliability)
                    distances_km.append(res.primary.distance_km)
                else:
                    unreachable_count += 1

                if res.baseline is not None:
                    baseline_reliabilities.append(res.baseline.reliability)

                if res.overlap_pct is not None:
                    overlaps.append(res.overlap_pct)

            except (RoutingError, Exception) as exc:
                unreachable_count += 1
                route_time_ms = (time.perf_counter() - t_start) * 1000.0
                latencies_ms.append(route_time_ms)

            if (i + 1) % 50 == 0 or (i + 1) == len(pairs):
                sys.stdout.write(f"\r  Progress: {i + 1}/{len(pairs)} pairs evaluated...")
                sys.stdout.flush()

        print()
        success_rate = ((len(pairs) - unreachable_count) / len(pairs) * 100.0) if pairs else 0.0
        first_route_lat = latencies_ms[0] if latencies_ms else 0.0
        subsequent_lats = latencies_ms[1:] if len(latencies_ms) > 1 else latencies_ms
        mean_lat = float(np.mean(subsequent_lats)) if subsequent_lats else 0.0
        p95_lat = float(np.percentile(subsequent_lats, 95)) if subsequent_lats else 0.0

        mean_prim_rel = float(np.mean(primary_reliabilities)) if primary_reliabilities else 0.0
        mean_base_rel = float(np.mean(baseline_reliabilities)) if baseline_reliabilities else 0.0
        mean_overlap = float(np.mean(overlaps)) if overlaps else 0.0

        vehicle_results[v_key] = {
            "success_rate_pct": round(success_rate, 2),
            "total_tested": len(pairs),
            "unreachable_count": unreachable_count,
            "first_route_latency_ms": round(first_route_lat, 2),
            "subsequent_route_mean_latency_ms": round(mean_lat, 2),
            "subsequent_route_p95_latency_ms": round(p95_lat, 2),
            "mean_primary_reliability_pct": round(mean_prim_rel * 100.0, 2),
            "mean_baseline_reliability_pct": round(mean_base_rel * 100.0, 2),
            "mean_backup_overlap_pct": round(mean_overlap, 2),
            "latencies_ms": latencies_ms,
            "primary_reliabilities": primary_reliabilities,
            "baseline_reliabilities": baseline_reliabilities,
            "overlaps": overlaps,
            "distances_km": distances_km,
        }

        print(f"  Success Rate: {success_rate:.1f}% ({unreachable_count} unreachable)")
        print(f"  First Route: {first_route_lat:.2f} ms | Subsequent Mean: {mean_lat:.2f} ms (p95: {p95_lat:.2f} ms)")
        print(f"  Mean Primary Reliability: {mean_prim_rel:.1%} vs Baseline: {mean_base_rel:.1%}")
        print(f"  Mean Backup Overlap: {mean_overlap:.1f}%")

    # 5. Compile Benchmark Metrics
    benchmark_data = {
        "region_id": region_id,
        "display_name": reg.display_name,
        "state": reg.state,
        "district": reg.district,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "hardware_os": platform.platform(),
        "python_version": platform.python_version(),
        "machine_architecture": platform.machine(),
        "parameters": {
            "num_od_pairs": len(pairs),
            "min_distance_meters": min_dist_m,
            "random_seed": seed,
        },
        "system_metrics": {
            "loading_time_seconds": round(load_time_s, 4),
            "traced_python_peak_mb": round(traced_peak_mb, 2),
            "process_rss_before_load_mb": round(rss_before_mb, 2) if rss_before_mb is not None else None,
            "process_rss_after_load_mb": round(rss_after_load_mb, 2) if rss_after_load_mb is not None else None,
            "process_rss_delta_mb": rss_delta_mb,
            "memory_measurement_method": (
                "Windows GetProcessMemoryInfo WorkingSetSize" if sys.platform == "win32"
                else "/proc/self/statm resident pages" if os.path.exists("/proc/self/statm")
                else "psutil RSS" if rss_after_load_mb is not None
                else "RSS unavailable"
            ),
            "memory_measurement_note": "Single-process snapshot around engine loading; excludes other services and is not a deployment limit.",
            "num_nodes": num_nodes,
            "num_edges": num_edges,
            "elevation_coverage_pct": round(elev_coverage_pct, 2),
            "depression_coverage_pct": round(dep_coverage_pct, 2),
        },
        "vehicles": {
            k: {
                m: v[m]
                for m in v
                if not isinstance(v[m], list)
            }
            for k, v in vehicle_results.items()
        },
    }

    # 6. Save JSON Results
    if not output_json:
        os.makedirs(os.path.join(_REPO_ROOT, "data"), exist_ok=True)
        output_json = os.path.join(_REPO_ROOT, "data", f"benchmark_results_{region_id}.json")

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(benchmark_data, f, indent=2)
    print(f"\n[SAVED] Benchmark metrics written to: {output_json}")

    # 7. Generate Multi-Panel Benchmark Visualization Plot
    if not output_plot:
        output_plot = os.path.join(_REPO_ROOT, "data", f"benchmark_plot_{region_id}.png")

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(
        f"Rakshapath Multi-Hazard Regional Routing Benchmark\n"
        f"{reg.display_name} ({reg.district}, {reg.state}) — {len(pairs)} Deterministic Pairs (Seed 42)",
        fontsize=14,
        fontweight="bold",
    )

    # Panel 1: Route Latencies
    ax1 = axes[0, 0]
    amb_lats = vehicle_results["ambulance"]["latencies_ms"][1:]
    truck_lats = vehicle_results["rescue_truck"]["latencies_ms"][1:]
    ax1.hist(amb_lats, bins=25, alpha=0.6, color="#1d5fd1", label="Ambulance")
    ax1.hist(truck_lats, bins=25, alpha=0.6, color="#0f5c6e", label="Rescue Truck")
    ax1.axvline(vehicle_results["ambulance"]["first_route_latency_ms"], color="#c62828", linestyle="--", label=f"First Route ({vehicle_results['ambulance']['first_route_latency_ms']:.1f}ms)")
    ax1.set_title("Route Calculation Latency Distribution (Subsequent Routes)")
    ax1.set_xlabel("Latency (ms)")
    ax1.set_ylabel("Count")
    ax1.legend()
    ax1.grid(True, linestyle=":", alpha=0.6)

    # Panel 2: Reliability Comparison (Primary vs Conventional Baseline)
    ax2 = axes[0, 1]
    amb_prim = [r * 100.0 for r in vehicle_results["ambulance"]["primary_reliabilities"]]
    amb_base = [r * 100.0 for r in vehicle_results["ambulance"]["baseline_reliabilities"]]
    truck_prim = [r * 100.0 for r in vehicle_results["rescue_truck"]["primary_reliabilities"]]
    truck_base = [r * 100.0 for r in vehicle_results["rescue_truck"]["baseline_reliabilities"]]

    positions = [1, 2, 4, 5]
    box_data = [amb_base, amb_prim, truck_base, truck_prim]
    colors = ["#7b8794", "#1d5fd1", "#7b8794", "#0f5c6e"]
    bp = ax2.boxplot(box_data, positions=positions, patch_artist=True, widths=0.6)
    for patch, c in zip(bp["boxes"], colors):
        patch.set_facecolor(c)
        patch.set_alpha(0.7)
    ax2.set_xticks([1.5, 4.5])
    ax2.set_xticklabels(["Ambulance\n(Baseline vs SafeRoute)", "Rescue Truck\n(Baseline vs SafeRoute)"])
    ax2.set_title("Reliability Gain: SafeRoute Primary vs Baseline")
    ax2.set_ylabel("Reliability (%)")
    ax2.grid(True, linestyle=":", alpha=0.6)

    # Panel 3: Backup Route Corridor Overlap
    ax3 = axes[1, 0]
    amb_overlaps = vehicle_results["ambulance"]["overlaps"]
    truck_overlaps = vehicle_results["rescue_truck"]["overlaps"]
    ax3.hist(amb_overlaps, bins=20, alpha=0.6, color="#e8820c", label="Ambulance")
    ax3.hist(truck_overlaps, bins=20, alpha=0.6, color="#d68a00", label="Rescue Truck")
    ax3.set_title("Backup Route Spatial Overlap with Primary")
    ax3.set_xlabel("Overlap with Primary Route (%)")
    ax3.set_ylabel("Count")
    ax3.legend()
    ax3.grid(True, linestyle=":", alpha=0.6)

    # Panel 4: Distance vs Distance Distribution
    ax4 = axes[1, 1]
    dists = vehicle_results["ambulance"]["distances_km"]
    ax4.hist(dists, bins=25, alpha=0.7, color="#2b5c70", edgecolor="#14232b")
    ax4.set_title("Tested OD Route Distances")
    ax4.set_xlabel("Route Distance (km)")
    ax4.set_ylabel("Count")
    ax4.grid(True, linestyle=":", alpha=0.6)

    plt.tight_layout()
    plt.savefig(output_plot, dpi=150)
    plt.close()
    print(f"[SAVED] Benchmark multi-panel plot saved to: {output_plot}\n")

    return benchmark_data


def main():
    parser = argparse.ArgumentParser(description="Run Rakshapath Regional Routing Benchmark")
    parser.add_argument("--region", default=DEFAULT_REGION_ID, help="Region ID to benchmark")
    parser.add_argument("--samples", type=int, default=300, help="Number of OD pairs to evaluate")
    parser.add_argument("--min-dist", type=float, default=1500.0, help="Minimum OD distance in meters")
    parser.add_argument("--seed", type=int, default=42, help="Random number generator seed")
    parser.add_argument("--output-json", default=None, help="Output JSON results path")
    parser.add_argument("--output-plot", default=None, help="Output plot image path")

    args = parser.parse_args()
    run_benchmark(
        region_id=args.region,
        num_samples=args.samples,
        min_dist_m=args.min_dist,
        seed=args.seed,
        output_json=args.output_json,
        output_plot=args.output_plot,
    )


if __name__ == "__main__":
    main()
