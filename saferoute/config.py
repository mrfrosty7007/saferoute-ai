"""
SafeRouteAI - Configuration & System Constants
Author: SafeRouteAI Team

Centralized configuration file defining all geographic, hydrological,
vehicle clearance, routing, file path, and visualization constants.
No magic numbers exist outside this module.
"""

import os
from typing import Dict

# ==============================================================================
# Project & Study Area Settings
# ==============================================================================
PROJECT_NAME: str = "SafeRouteAI"
PLACE_NAME: str = "Daraganj, Prayagraj, India"
CENTER_LAT: float = 25.4430
CENTER_LON: float = 81.8805
RADIUS_METERS: int = 2000
NETWORK_TYPE: str = "drive"

# ==============================================================================
# File System Paths
# ==============================================================================
BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR: str = os.path.join(BASE_DIR, "data")

GRAPH_FILE: str = os.path.join(DATA_DIR, "graph.graphml")
ELEVATIONS_CACHE_FILE: str = os.path.join(DATA_DIR, "elevations.json")
DEPRESSIONS_CACHE_FILE: str = os.path.join(DATA_DIR, "depressions.pkl")
ELEVATION_PLOT_FILE: str = os.path.join(DATA_DIR, "elevation_network.png")
GRID_PLOT_FILE: str = os.path.join(DATA_DIR, "passability_3x3_grid.png")
DEMO_SCENARIOS_FILE: str = os.path.join(DATA_DIR, "demo_scenarios.json")
DEMO_PLOT_FILE: str = os.path.join(DATA_DIR, "demo_route_comparison.png")

# ==============================================================================
# Geodesic & Metric Constants
# ==============================================================================
METERS_PER_DEG_LAT: float = 111320.0
METERS_PER_DEG_LON: float = 100500.0
EARTH_RADIUS_METERS: float = 6371000.0
CM_PER_METER: float = 100.0

# ==============================================================================
# OpenTopoData SRTM API Parameters
# ==============================================================================
OPENTOPO_SRTM30_URL: str = "https://api.opentopodata.org/v1/srtm30m"
OPENTOPO_SRTM90_URL: str = "https://api.opentopodata.org/v1/srtm90m"
API_BATCH_SIZE: int = 100
API_REQUEST_DELAY_SEC: float = 1.0
API_MAX_RETRIES: int = 3
API_TIMEOUT_SEC: int = 20
OSMNX_TIMEOUT_SEC: int = 60
USER_AGENT: str = "SafeRouteAI-Research/1.0 (admin@saferoute.ai)"

# ==============================================================================
# Hydrological & Topographic Risk Parameters
# ==============================================================================
K_RAIN_FACTOR: float = 0.25             # Tunable rain ponding coefficient k
SIGMOID_SCALE_S: float = 5.0            # Logistic transition softness s in cm
DEPRESSION_RADIUS_M: float = 300.0      # Spatial neighborhood radius for topographic depression
BRIDGE_CLEARANCE_MARGIN_M: float = 1.0  # Height above bridge approaches before overtopping
PROBABILITY_EPSILON: float = 1e-6       # Minimum probability floor to prevent log(0)

# ==============================================================================
# Vehicle Clearances (Safe Wading Depths in cm)
# ==============================================================================
VEHICLES: Dict[str, float] = {
    "ambulance": 28.0,                  # Emergency Medical Services
    "fire_tender": 50.0,                # Fire & Rescue Response
    "rescue_truck": 65.0,               # High-Clearance Disaster Truck
}

# ==============================================================================
# UI Slider Bounds & Calibration Scenarios
# ==============================================================================
RIVER_LEVEL_MIN_M: float = 74.0         # Lowest elevation road in Daraganj
RIVER_LEVEL_MAX_M: float = 90.0         # Severe river stage
RAINFALL_MAX_MM_HR: float = 100.0       # Monsoon cloudburst intensity

SCENARIOS: Dict[str, Dict[str, float]] = {
    "Dry": {"river": 75.0, "rain": 0.0},
    "Moderate": {"river": 82.0, "rain": 45.0},
    "Severe": {"river": 87.0, "rain": 90.0},
}

# ==============================================================================
# Phase 3 Routing Constants
# ==============================================================================
DEFAULT_SPEED_KMH: float = 30.0         # Urban collector default speed
MAX_SPEED_WATER_PENALTY: float = 0.5    # Speed reduces to 50% in deep water
LAMBDA_RISK: Dict[str, float] = {
    "low": 30.0,                        # 30 seconds detour tolerated per unit risk
    "medium": 120.0,                    # 120 seconds detour tolerated per unit risk
    "critical": 400.0,                  # 400 seconds detour tolerated per unit risk
}
DEFAULT_LAMBDA: float = 120.0
RISKY_EDGE_P_THRESHOLD: float = 0.95    # Edges below this are penalized for backup route
BACKUP_PENALTY_RISKY: float = 10.0      # Multiplier on risky primary edges
BACKUP_PENALTY_ALL: float = 3.0         # Fallback multiplier on all primary edges
MIN_OD_DISTANCE_M: float = 1500.0       # Minimum origin-destination distance for demo pairs
NUM_OD_SAMPLES: int = 300               # Number of pairs to evaluate in demo finder

# ==============================================================================
# Visualization Theme
# ==============================================================================
THEME_BG_COLOR: str = "#0e1117"
THEME_TEXT_COLOR: str = "#f7fafc"
THEME_MUTED_COLOR: str = "#a0aec0"
THEME_BORDER_COLOR: str = "#2d3748"
PLOT_DPI: int = 300
GRID_PLOT_DPI: int = 250
