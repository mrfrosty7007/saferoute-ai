"""Nearby emergency support from OpenStreetMap (Overpass). Nothing is guessed or invented."""
from __future__ import annotations

import math
import time

import logging

import requests

import config
from services.contracts import NearbyResult, SupportFacility
from services.geo import haversine_m

log = logging.getLogger("saferoute.nearby")
ATTRIBUTION = "Data (c) OpenStreetMap contributors. Coverage varies; details may be missing or outdated."
_CACHE: dict = {}
_TTL_S = 300


def clear_cache() -> None:
    _CACHE.clear()


def _valid(lat, lon) -> bool:
    for v in (lat, lon):
        if v is None or isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            return False
    return -90 <= lat <= 90 and -180 <= lon <= 180


def build_query(lat, lon, categories, radius_m) -> str:
    lines = [f"  nwr{f}(around:{int(radius_m)},{lat},{lon});"
             for c in categories for f in config.NEARBY_CATEGORIES[c]["filters"]]
    return f"[out:json][timeout:{config.NEARBY_TIMEOUT_S}];\n(\n" + "\n".join(lines) + "\n);\nout center tags;"


def _default_fetch(query: str) -> dict:
    r = requests.post(config.OVERPASS_URL, data={"data": query},
                      headers={"User-Agent": config.HTTP_USER_AGENT},
                      timeout=config.NEARBY_TIMEOUT_S + 5)
    r.raise_for_status()
    return r.json()


def _matches(cat: str, t: dict) -> bool:
    return {
        "hospital": t.get("amenity") == "hospital",
        "ambulance": t.get("emergency") == "ambulance_station",
        "fire_station": t.get("amenity") == "fire_station",
        "police": t.get("amenity") == "police",
        "shelter": t.get("emergency") == "assembly_point" or t.get("social_facility") == "shelter",
    }.get(cat, False)


def _address(t: dict):
    if t.get("addr:full"):
        return t["addr:full"]
    street = " ".join(p for p in (t.get("addr:housenumber"), t.get("addr:street")) if p)
    parts = [p for p in (street, t.get("addr:suburb"), t.get("addr:city")) if p]
    return ", ".join(parts) or None


def _parse(data: dict, lat: float, lon: float, selected: list) -> list:
    seen, out = set(), []
    for el in (data or {}).get("elements", []):
        tags = el.get("tags") or {}
        cat = next((c for c in selected if _matches(c, tags)), None)
        if cat is None:
            continue
        pos = el if "lat" in el and "lon" in el else el.get("center") or {}
        try:
            flat, flon = float(pos["lat"]), float(pos["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        fid = f'{el.get("type", "node")}/{el.get("id")}'
        if fid in seen:
            continue
        seen.add(fid)
        out.append(SupportFacility(
            id=fid, category=cat, lat=flat, lon=flon, distance_m=haversine_m(lat, lon, flat, flon),
            name=tags.get("name") or None, address=_address(tags),
            phone=tags.get("phone") or tags.get("contact:phone") or None,
            opening_hours=tags.get("opening_hours") or None))
    out.sort(key=lambda f: f.distance_m)
    return out[:config.NEARBY_MAX_RESULTS]


def find_nearby(lat, lon, categories=None, radius_m=None, *, fetch=None) -> NearbyResult:
    radius_m = int(radius_m or config.NEARBY_RADIUS_M)
    if not _valid(lat, lon):
        return NearbyResult("no_location",
                            "No valid location. Choose an origin, a destination, custom coordinates or your device location.",
                            radius_m=radius_m, attribution=ATTRIBUTION)
    ref = (float(lat), float(lon))
    cats = list(config.NEARBY_CATEGORIES) if categories is None else \
        [c for c in categories if c in config.NEARBY_CATEGORIES]
    if not cats:
        return NearbyResult("empty", "No support categories are selected.", reference=ref,
                            radius_m=radius_m, attribution=ATTRIBUTION)

    key = (round(ref[0], 4), round(ref[1], 4), radius_m, tuple(sorted(cats)))
    if fetch is None:
        hit = _CACHE.get(key)
        if hit and time.monotonic() - hit[0] < _TTL_S:
            return hit[1]
    try:
        data = (fetch or _default_fetch)(build_query(ref[0], ref[1], cats, radius_m))
        facilities = _parse(data, ref[0], ref[1], cats)
    except Exception as exc:
        log.warning("Facility lookup failed: %s", type(exc).__name__)
        return NearbyResult("unavailable",
                            "The facility data source could not be reached. No results were guessed.",
                            reference=ref, radius_m=radius_m, attribution=ATTRIBUTION)
    if not facilities:
        result = NearbyResult("empty",
                              "No matching facilities were found in the data. This does not prove that none exist.",
                              reference=ref, radius_m=radius_m, attribution=ATTRIBUTION)
    else:
        n = len(facilities)
        result = NearbyResult(
            "ok",
            f"Found {n} facilit{'y' if n == 1 else 'ies'} within {radius_m / 1000:g} km. "
            "Distances are straight-line and details may be missing or outdated.",
            tuple(facilities), ref, radius_m, ATTRIBUTION)
    if fetch is None:
        _CACHE[key] = (time.monotonic(), result)
    return result


def directions_url(origin, facility) -> str:
    url = f"https://www.google.com/maps/dir/?api=1&destination={facility.lat},{facility.lon}"
    if origin is not None and _valid(origin[0], origin[1]):
        url += f"&origin={origin[0]},{origin[1]}"
    return url
