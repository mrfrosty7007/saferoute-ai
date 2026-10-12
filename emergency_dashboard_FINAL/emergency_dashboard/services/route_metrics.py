"""Read comparable numbers from any route object or dict. Unknown values are None, never guessed.

_ALIASES maps each metric to the attribute names to try. Edit it to match the real engine.
The current mock engine's Route exposes eta_min, distance_km and all_coords() but no single
risk score and no blocked-segment count, so risk is derived from its returned segments and
blocked stays None (unknown).
"""
from __future__ import annotations

_ALIASES = {
    "time_min": ("time_min", "travel_time_min", "eta_min", "duration_min"),
    "distance_km": ("distance_km", "length_km"),
    "risk": ("risk_score", "risk", "total_risk", "hazard_exposure"),
    "blocked": ("blocked_segments", "blocked_count", "n_blocked"),
    "coords": ("coords", "coordinates", "path", "geometry", "all_coords"),
}
_FIELDS = tuple(_ALIASES)


def _get(obj, name):
    val = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
    if callable(val):
        try:
            val = val()
        except Exception:
            return None
    return val


def _num(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _derived_risk(route):
    """Length-weighted mean of the segment risks the engine returned, if any."""
    segs = _get(route, "segments")
    if not segs:
        return None
    try:
        total = sum(float(_get(s, "length_m") or 0) for s in segs)
        if total <= 0:
            return None
        return sum(float(_get(s, "risk")) * float(_get(s, "length_m")) for s in segs) / total
    except (TypeError, ValueError):
        return None


def route_metrics(route) -> dict:
    out = {k: None for k in _FIELDS}
    if route is None:
        return out
    for field in _FIELDS:
        for name in _ALIASES[field]:
            val = _get(route, name)
            if val is None:
                continue
            if field == "blocked":
                val = len(val) if isinstance(val, (list, tuple, set)) else _num(val)
                val = None if val is None else int(val)
            elif field == "coords":
                val = tuple(tuple(c) for c in val) if val else None
            else:
                val = _num(val)
            if val is not None:
                out[field] = val
                break
    if out["risk"] is None:
        out["risk"] = _derived_risk(route)
    return out
