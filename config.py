"""
SafeRouteAI - Dashboard Configuration
Author: SafeRouteAI Team (Integrated Frontend & Backend)

Declarative configuration for emergency vehicles, multi-hazard parameters,
route styles, and geographic study area settings for Daraganj, Prayagraj.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Vehicle:
    key: str
    label: str
    speed_factor: float
    vulnerability: float
    note: str


@dataclass(frozen=True)
class Param:
    key: str
    label: str
    unit: str
    min: float
    max: float
    default: float
    step: float


@dataclass(frozen=True)
class Hazard:
    key: str
    label: str
    note: str
    is_validated: bool
    params: tuple[Param, ...]


# Study Area Geographic Definitions (Daraganj, Prayagraj, India)
STUDY_AREA_NAME = "Daraganj, Prayagraj, India"
STUDY_AREA_CENTER = (25.4430, 81.8805)
STUDY_AREA_RADIUS_M = 2000.0
STUDY_AREA_BOUNDS = {
    "min_lat": 25.420,
    "max_lat": 25.465,
    "min_lon": 81.855,
    "max_lon": 81.905,
}

# Verified Daraganj Emergency Vehicles & Clearances
VEHICLES: dict[str, Vehicle] = {
    v.key: v
    for v in (
        Vehicle("ambulance", "Ambulance (EMS)", 0.90, 0.85, "28 cm safe water clearance, low chassis rubble limit"),
        Vehicle("fire_tender", "Fire Tender", 1.15, 1.00, "50 cm safe water clearance, medium chassis clearance"),
        Vehicle("rescue_truck", "Rescue Truck", 1.05, 0.75, "65 cm safe water clearance, high 4x4 rubble resilience"),
    )
}

# Natural Disaster Hazards (Supported & Extensible)
HAZARDS: dict[str, Hazard] = {
    h.key: h
    for h in (
        Hazard(
            "flood",
            "Flood Inundation (Validated)",
            "Ganges & Yamuna river stage backwater rise and rainfall depression ponding [Validated Phase 2 Model]",
            True,
            (
                Param("rainfall", "Rainfall intensity", "mm/h", 0, 100, 45, 5),
                Param("river_level", "River stage elevation", "m", 74.0, 90.0, 82.0, 0.5),
            ),
        ),
        Hazard(
            "earthquake",
            "Earthquake Debris (Scenario Simulation)",
            "Ground shaking attenuation, narrow street masonry collapse, and bridge structural caution [Exploratory Scenario]",
            False,
            (
                Param("magnitude", "Epicenter shaking intensity", "MMI", 5.0, 9.5, 7.2, 0.1),
                Param("epicenter_dist", "Distance to epicenter", "km", 1.0, 50.0, 12.0, 1.0),
                Param("debris_vuln", "Masonry debris factor", "x", 0.5, 2.0, 1.0, 0.1),
            ),
        ),
    )
}

# Severity scaling multipliers
SEVERITIES: dict[str, float] = {
    "Low": 0.70,
    "Moderate": 1.00,
    "High": 1.25,
    "Extreme": 1.50,
}

# Route cartography and labels
ROUTE_COLORS = {
    "primary": "#1d5fd1",      # Deep Royal Blue
    "backup": "#e8820c",       # Vibrant Amber / Orange
    "baseline": "#7b8794",     # Muted Slate Grey
}

ROUTE_LABELS = {
    "primary": "Primary route (SafeRoute)",
    "backup": "Backup route (Independent Detour)",
    "baseline": "Conventional baseline (Shortest Path)",
}

# Verified Landmarks in Daraganj
DARAGANJ_LANDMARKS = {
    "Daraganj South (Benchmark Origin)": (25.4348, 81.8785),
    "Daraganj North (Benchmark Dest)": (25.4514, 81.8825),
    "Alop Shankari Devi Temple (North-West)": (25.4485, 81.8781),
    "Bakhshi Bandh (North Collector)": (25.4539, 81.8721),
    "Sangam Confluence Ghat (Riverfront)": (25.4286, 81.8837),
    "Daraganj Railway Station (Central)": (25.4398, 81.8797),
    "Nagvasuki Temple (Riverfront East)": (25.4460, 81.8888),
}

# Default Origin and Destination (Rank 1 Benchmark Pair in Daraganj)
DEFAULT_ORIGIN = (25.4348, 81.8785)   # Daraganj South (Benchmark Origin, elev 94m)
DEFAULT_DEST = (25.4514, 81.8825)     # Daraganj North (Benchmark Dest, elev 91m)


def hazard_intensity(hazard_key: str, params: dict[str, float]) -> float:
    """Normalised 0..1 mean of the hazard's parameters."""
    if hazard_key not in HAZARDS:
        return 0.5
    hz = HAZARDS[hazard_key]
    vals = []
    for p in hz.params:
        span = (p.max - p.min) or 1.0
        vals.append(min(1.0, max(0.0, (params.get(p.key, p.default) - p.min) / span)))
    return sum(vals) / len(vals) if vals else 0.5
