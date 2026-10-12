"""Worldwide place search (countries, cities, towns, villages).

Tries OpenStreetMap Nominatim first, then Photon (also OpenStreetMap data, more forgiving of
partial or misspelled names). Only non-empty results are cached.
"""
from __future__ import annotations

import logging
import time

import requests

from services.contracts import Place

log = logging.getLogger("saferoute.geocode")
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
PHOTON_URL = "https://photon.komoot.io/api/"
HEADERS = {"User-Agent": "resilient-emergency-routing-dashboard/0.1", "Accept-Language": "en"}
_CACHE: dict = {}
_TTL_S = 3600


class GeocodingError(Exception):
    pass


def _nominatim(query: str, limit: int, timeout: float) -> list:
    r = requests.get(NOMINATIM_URL, params={"q": query, "format": "jsonv2", "limit": limit},
                     headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return [Place(i["display_name"], float(i["lat"]), float(i["lon"])) for i in r.json()]


def _photon(query: str, limit: int, timeout: float) -> list:
    r = requests.get(PHOTON_URL, params={"q": query, "limit": limit, "lang": "en"}, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    out = []
    for f in r.json().get("features", []):
        p, (lon, lat) = f.get("properties", {}), f["geometry"]["coordinates"][:2]
        parts = []
        for k in ("name", "street", "district", "city", "county", "state", "country"):
            v = p.get(k)
            if v and v not in parts:
                parts.append(v)
        out.append(Place(", ".join(parts) or f"{lat:.4f}, {lon:.4f}", float(lat), float(lon)))
    return out


def search_places(query: str, limit: int = 8, timeout: float = 8.0) -> list:
    query = query.strip()
    hit = _CACHE.get(query.lower())
    if hit and time.monotonic() - hit[0] < _TTL_S:
        return hit[1]
    failures = 0
    for name, fn in (("nominatim", _nominatim), ("photon", _photon)):
        try:
            places = fn(query, limit, timeout)
        except (requests.RequestException, KeyError, ValueError, TypeError) as exc:
            failures += 1
            log.warning("Place search via %s failed: %s", name, type(exc).__name__)
            continue
        if places:
            _CACHE[query.lower()] = (time.monotonic(), places)
            return places
    if failures == 2:
        raise GeocodingError("Place search could not be reached (check your internet connection). "
                             "Use Coordinates instead.")
    return []
