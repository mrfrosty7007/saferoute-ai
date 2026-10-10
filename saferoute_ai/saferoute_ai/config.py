"""Static configuration: vehicles, hazards, severities, colours.

Hazard parameters are declarative so that adding a hazard is a data change,
not a UI change. The risk model itself lives in the routing engine, not here.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Vehicle:
    key: str
    label: str
    speed_factor: float   # only used by the mock engine
    vulnerability: float  # only used by the mock engine
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
    params: tuple[Param, ...]


VEHICLES: dict[str, Vehicle] = {
    v.key: v
    for v in (
        Vehicle("ambulance", "Ambulance", 0.90, 0.85, "Light, fast, low ground clearance"),
        Vehicle("fire_tender", "Fire tender", 1.15, 1.00, "Heavy, wide, needs strong road surface"),
        Vehicle("rescue_truck", "Rescue truck", 1.05, 0.75, "High clearance, off-road capable"),
    )
}

HAZARDS: dict[str, Hazard] = {
    h.key: h
    for h in (
        Hazard("flood", "Flood", "River and rainfall driven inundation", (
            Param("rainfall", "Rainfall", "mm/h", 0, 250, 60, 5),
            Param("river_level", "River level above flood stage", "m", 0, 12, 2.5, 0.1),
        )),
        Hazard("cyclone", "Cyclone, hurricane or typhoon", "Wind and storm surge", (
            Param("wind", "Sustained wind", "km/h", 30, 320, 140, 5),
            Param("surge", "Storm surge", "m", 0, 10, 2.0, 0.1),
        )),
        Hazard("earthquake", "Earthquake", "Shaking, ground failure and collapse", (
            Param("magnitude", "Magnitude", "Mw", 3.0, 9.5, 6.5, 0.1),
            Param("aftershocks", "Aftershock activity", "events/h", 0, 40, 6, 1),
        )),
        Hazard("tsunami", "Tsunami", "Coastal inundation", (
            Param("wave", "Wave height at shore", "m", 0, 30, 4, 0.5),
            Param("inland", "Inundation distance", "km", 0, 10, 1.5, 0.1),
        )),
        Hazard("landslide", "Landslide and mudflow", "Slope failure", (
            Param("rainfall", "Rainfall (72 h)", "mm", 0, 600, 180, 10),
            Param("slope", "Slope instability index", "0-100", 0, 100, 50, 1),
        )),
        Hazard("wildfire", "Wildfire", "Fire spread and smoke", (
            Param("fdi", "Fire danger index", "0-100", 0, 100, 65, 1),
            Param("smoke", "Smoke density", "0-100", 0, 100, 40, 1),
        )),
        Hazard("volcano", "Volcanic eruption", "Ashfall, lava and pyroclastic flows", (
            Param("ash", "Ashfall depth", "mm", 0, 300, 20, 5),
            Param("vei", "Eruption size", "VEI", 0, 8, 3, 0.5),
        )),
        Hazard("blizzard", "Blizzard and heavy snow", "Snow accumulation and whiteout", (
            Param("snowfall", "Snowfall rate", "cm/h", 0, 15, 4, 0.5),
            Param("visibility", "Visibility loss", "%", 0, 100, 50, 5),
        )),
        Hazard("avalanche", "Avalanche", "Snow slab release on mountain roads", (
            Param("danger", "Avalanche danger level", "1-5", 1, 5, 3, 1),
            Param("snowpack", "New snow (24 h)", "cm", 0, 150, 40, 5),
        )),
        Hazard("storm", "Tornado and severe storm", "Wind, hail and lightning", (
            Param("wind", "Peak gust", "km/h", 40, 400, 120, 5),
            Param("hail", "Hail size", "cm", 0, 12, 2, 0.5),
        )),
        Hazard("dust", "Dust or sand storm", "Low visibility and drifting sand", (
            Param("visibility", "Visibility loss", "%", 0, 100, 60, 5),
            Param("wind", "Sustained wind", "km/h", 20, 150, 60, 5),
        )),
        Hazard("heat", "Extreme heat", "Road surface and vehicle stress", (
            Param("temp", "Air temperature", "C", 25, 55, 42, 1),
            Param("duration", "Duration", "days", 0, 21, 5, 1),
        )),
    )
}

# Multiplier applied to hazard intensity by the mock engine.
SEVERITIES: dict[str, float] = {"Low": 0.55, "Moderate": 0.80, "High": 1.00, "Extreme": 1.25}

ROUTE_COLORS = {"primary": "#1d5fd1", "backup": "#e8820c", "baseline": "#7b8794"}
ROUTE_LABELS = {"primary": "Primary route", "backup": "Backup route", "baseline": "Conventional baseline"}


def hazard_intensity(hazard_key: str, params: dict[str, float]) -> float:
    """Normalised 0..1 mean of the hazard's parameters (used for display and mock)."""
    hz = HAZARDS[hazard_key]
    vals = []
    for p in hz.params:
        span = (p.max - p.min) or 1.0
        vals.append(min(1.0, max(0.0, (params.get(p.key, p.default) - p.min) / span)))
    return sum(vals) / len(vals)
