"""Worldwide place search (countries, cities, towns, villages) via OpenStreetMap Nominatim."""
from __future__ import annotations

import requests

from services.contracts import Place

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "resilient-emergency-routing-dashboard/0.1"}


class GeocodingError(Exception):
    pass


def search_places(query: str, limit: int = 8, timeout: float = 8.0) -> list:
    try:
        r = requests.get(NOMINATIM_URL, params={"q": query, "format": "jsonv2", "limit": limit},
                         headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return [Place(i["display_name"], float(i["lat"]), float(i["lon"])) for i in r.json()]
    except (requests.RequestException, KeyError, ValueError) as exc:
        raise GeocodingError("Place search is unavailable. Enter coordinates instead.") from exc
