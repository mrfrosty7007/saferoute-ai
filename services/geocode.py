"""
Place search via OpenStreetMap Nominatim with Prayagraj focus.
"""
from __future__ import annotations

import requests

from services.contracts import Place

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "SafeRouteAI-Research/1.0 (admin@saferoute.ai)"}


class GeocodingError(Exception):
    pass


def search_places(query: str, limit: int = 8, timeout: float = 8.0) -> list:
    try:
        q_clean = query.strip()
        # Biasing towards Prayagraj if not explicitly stated
        if "prayagraj" not in q_clean.lower() and "allahabad" not in q_clean.lower():
            q_search = f"{q_clean}, Prayagraj, India"
        else:
            q_search = q_clean

        r = requests.get(
            NOMINATIM_URL,
            params={"q": q_search, "format": "jsonv2", "limit": limit},
            headers=HEADERS,
            timeout=timeout,
        )
        r.raise_for_status()
        items = r.json()
        if not items and q_search != q_clean:
            # Fallback to verbatim search
            r = requests.get(
                NOMINATIM_URL,
                params={"q": q_clean, "format": "jsonv2", "limit": limit},
                headers=HEADERS,
                timeout=timeout,
            )
            r.raise_for_status()
            items = r.json()

        return [Place(i["display_name"], float(i["lat"]), float(i["lon"])) for i in items]
    except (requests.RequestException, KeyError, ValueError) as exc:
        raise GeocodingError("Place search is currently unavailable. Enter coordinates instead.") from exc
