"""Data contract between the dashboard and the routing engine.

The real engine only has to accept a RouteRequest and return a RouteResult.
Nothing in the UI depends on how routes or risks are computed.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from config import HAZARDS, VEHICLES, SEVERITIES
from services.geo import haversine_m

HIGH_RISK_THRESHOLD = 0.60  # segment risk at or above this counts as "highly risky"


class RoutingError(Exception):
    """Raised by an engine when no result can be produced."""


@dataclass(frozen=True)
class Place:
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class RouteRequest:
    origin: Place
    destination: Place
    vehicle: str
    hazard: str
    params: dict
    severity: str

    def signature(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


@dataclass
class Segment:
    coords: list  # [(lat, lon), ...] real road geometry
    risk: float   # 0..1, higher is worse
    length_m: float
    label: str = ""

    @property
    def pass_probability(self) -> float:
        return 1.0 - self.risk


@dataclass
class Route:
    kind: str  # primary | backup | baseline
    segments: list
    eta_min: float
    distance_km: float
    reliability: float  # 0..1

    def weakest_segment(self) -> Segment | None:
        return max(self.segments, key=lambda s: s.risk, default=None)

    def high_risk_count(self, threshold: float = HIGH_RISK_THRESHOLD) -> int:
        return sum(1 for s in self.segments if s.risk >= threshold)

    def all_coords(self) -> list:
        return [c for s in self.segments for c in s.coords]


@dataclass
class RouteResult:
    primary: Route | None = None
    backup: Route | None = None
    baseline: Route | None = None
    overlap_pct: float | None = None  # share of backup length also used by primary
    simulated: bool = False
    source: str = ""
    notes: list = field(default_factory=list)

    def routes(self) -> list:
        return [("primary", self.primary), ("backup", self.backup), ("baseline", self.baseline)]

    @property
    def has_any(self) -> bool:
        return any(r is not None for _, r in self.routes())


def validate_request(req: RouteRequest) -> list:
    """Return a list of human-readable problems; empty means valid."""
    errs = []
    for label, p in (("Origin", req.origin), ("Destination", req.destination)):
        if p is None:
            errs.append(f"{label} is not set.")
        elif not (-90 <= p.lat <= 90 and -180 <= p.lon <= 180):
            errs.append(f"{label} coordinates are outside the valid range.")
    if errs:
        return errs
    if haversine_m(req.origin.lat, req.origin.lon, req.destination.lat, req.destination.lon) < 100:
        errs.append("Origin and destination are less than 100 m apart. Choose two distinct locations.")
    if req.vehicle not in VEHICLES:
        errs.append(f"Unknown vehicle '{req.vehicle}'.")
    if req.hazard not in HAZARDS:
        errs.append(f"Unknown hazard '{req.hazard}'.")
    if req.severity not in SEVERITIES:
        errs.append(f"Unknown severity '{req.severity}'.")
    return errs
