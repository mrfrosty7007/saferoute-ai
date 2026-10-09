"""
SafeRouteAI Package
Flood-resilient emergency vehicle routing system for Daraganj, Prayagraj, India.
"""

from .config import (
    K_RAIN_FACTOR,
    PROJECT_NAME,
    SCENARIOS,
    VEHICLES,
)
from .data import (
    get_graph_summary,
    load_cached_graph,
    load_or_create_graph,
)
from .risk import (
    compute_depths,
    evaluate_scenarios,
    is_bridge,
    pass_probability,
    passability,
    precompute_depressions,
    run_sanity_assertions,
)
from .viz import (
    plot_3x3_grid,
    plot_elevation_network,
    plot_passability,
)

__all__ = [
    "PROJECT_NAME",
    "K_RAIN_FACTOR",
    "VEHICLES",
    "SCENARIOS",
    "load_or_create_graph",
    "load_cached_graph",
    "get_graph_summary",
    "is_bridge",
    "precompute_depressions",
    "compute_depths",
    "pass_probability",
    "passability",
    "evaluate_scenarios",
    "run_sanity_assertions",
    "plot_elevation_network",
    "plot_passability",
    "plot_3x3_grid",
]
