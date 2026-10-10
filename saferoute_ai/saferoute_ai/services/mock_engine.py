"""SIMULATED routing engine used until the real engine is integrated.

Real road geometry comes from the public OSRM demo server. Risk, reliability
and ETA penalties are synthetic and exist only to exercise the UI.
This is deliberately NOT a routing algorithm and NOT the project's risk model.
"""
from __future__ import annotations

import math
import zlib
from dataclasses import dataclass, replace

import requests

from config import SEVERITIES, VEHICLES, hazard_intensity
from services.contracts import Route, RouteRequest, RouteResult, RoutingError, Segment
from services.geo import haversine_m

OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"


@dataclass
class RawRoute:
    coords: list  # [(lat, lon), ...]
    duration_s: float


def fetch_osrm_routes(request: RouteRequest, timeout: float = 12.0) -> list:
    o, d = request.origin, request.destination
    r = requests.get(OSRM_URL.format(lon1=o.lon, lat1=o.lat, lon2=d.lon, lat2=d.lat),
                     params={"alternatives": "3", "overview": "full", "geometries": "geojson"}, timeout=timeout)
    if r.status_code == 400:
        raise RoutingError("No drivable road connection was found between these locations.")
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError("No drivable road connection was found between these locations.")
    return [RawRoute([(lat, lon) for lon, lat in rt["geometry"]["coordinates"]], float(rt["duration"]))
            for rt in data["routes"]]


def synthetic_routes(request: RouteRequest) -> list:
    """Approximate curved paths, used only when the OSRM service is unreachable."""
    o, d = request.origin, request.destination
    dist = haversine_m(o.lat, o.lon, d.lat, d.lon)
    out = []
    for amp in (0.0, 0.08, -0.08):
        pts = []
        for i in range(61):
            t = i / 60
            lat = o.lat + (d.lat - o.lat) * t
            lon = o.lon + (d.lon - o.lon) * t
            off = amp * math.sin(math.pi * t)
            pts.append((lat + off * (d.lon - o.lon), lon - off * (d.lat - o.lat)))
        out.append(RawRoute(pts, dist * (1 + abs(amp)) / (45 / 3.6)))
    return out


def _noise(lat: float, lon: float, salt: str) -> float:
    return (zlib.crc32(f"{salt}:{lat:.2f},{lon:.2f}".encode()) % 10000) / 10000


def _split(coords: list, target_m: float) -> list:
    chunks, cur, acc = [], [coords[0]], 0.0
    for a, b in zip(coords, coords[1:]):
        cur.append(b)
        acc += haversine_m(a[0], a[1], b[0], b[1])
        if acc >= target_m:
            chunks.append(cur)
            cur, acc = [b], 0.0
    if len(cur) > 1:
        chunks.append(cur)
    return chunks or [coords]


def _edges(coords: list) -> dict:
    def k(p):
        return (round(p[0], 5), round(p[1], 5))
    return {(k(a), k(b)): haversine_m(a[0], a[1], b[0], b[1]) for a, b in zip(coords, coords[1:])}


class MockEngine:
    simulated = True

    def __init__(self, geometry_provider=fetch_osrm_routes):
        self._provider = geometry_provider

    def route(self, request: RouteRequest) -> RouteResult:
        notes = []
        source = "Simulated risk on real road geometry (OSRM public demo server)"
        try:
            raw = self._provider(request)
        except RoutingError:
            raise
        except (requests.RequestException, KeyError, ValueError):
            raw = synthetic_routes(request)
            source = "Simulated risk on approximate geometry (road service unreachable)"
            notes.append("The road geometry service could not be reached, so approximate paths are shown instead of real roads.")
        if not raw:
            raise RoutingError("No routes were returned.")

        vehicle = VEHICLES[request.vehicle]
        exposure = hazard_intensity(request.hazard, request.params) * SEVERITIES[request.severity] * vehicle.vulnerability
        cands = [self._build(r, request, exposure, vehicle.speed_factor) for r in raw]

        ranked = sorted(cands, key=lambda c: (-c["reliability"], c["route"].eta_min))
        primary = ranked[0]
        backup = ranked[1] if len(ranked) > 1 else None
        baseline = min(cands, key=lambda c: c["raw"].duration_s)

        overlap = None
        if backup:
            shared = sum(l for e, l in backup["edges"].items() if e in primary["edges"])
            total = sum(backup["edges"].values()) or 1.0
            overlap = round(100 * shared / total, 1)
        else:
            notes.append("Only one road alternative exists for this pair, so no backup route is available.")

        return RouteResult(
            primary=replace(primary["route"], kind="primary"),
            backup=replace(backup["route"], kind="backup") if backup else None,
            baseline=replace(baseline["route"], kind="baseline"),
            overlap_pct=overlap, simulated=True, source=source, notes=notes)

    @staticmethod
    def _build(raw: RawRoute, req: RouteRequest, exposure: float, speed_factor: float) -> dict:
        edges = _edges(raw.coords)
        total = sum(edges.values()) or 1.0
        segs = []
        chunks = _split(raw.coords, max(250.0, total / 100))
        for i, ch in enumerate(chunks):
            mlat = sum(p[0] for p in ch) / len(ch)
            mlon = sum(p[1] for p in ch) / len(ch)
            n = _noise(mlat, mlon, req.hazard)
            risk = min(1.0, exposure * (0.15 + 1.15 * n ** 1.6))
            length = sum(haversine_m(a[0], a[1], b[0], b[1]) for a, b in zip(ch, ch[1:]))
            segs.append(Segment(ch, risk, length, f"Segment {i + 1} of {len(chunks)}"))
        seg_total = sum(s.length_m for s in segs) or 1.0
        mean_risk = sum(s.risk * s.length_m for s in segs) / seg_total
        reliability = 0.6 * (1 - mean_risk) + 0.4 * min(s.pass_probability for s in segs)
        eta = raw.duration_s / 60 * speed_factor * (1 + 0.8 * mean_risk)
        route = Route("primary", segs, round(eta, 1), round(seg_total / 1000, 2), round(reliability, 4))
        return {"raw": raw, "route": route, "edges": edges, "reliability": reliability}
