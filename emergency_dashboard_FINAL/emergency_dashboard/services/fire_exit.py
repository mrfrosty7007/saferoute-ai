"""Fire exit routing from VERIFIED exits only. Reuses the routing engine through route_fn."""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path

import config
from services.contracts import FireExit, FireExitOption, FireExitResult
from services.geo import haversine_m
from services.route_metrics import route_metrics

log = logging.getLogger("saferoute.fire_exit")
MSG_NO_DATA = ("No verified exit data is available. Fire exit routing needs verified exit coordinates "
               "(and indoor-network data for indoor routing). SafeRoute will not invent exits.")
MSG_NO_FIRE = "The active scenario is not a fire hazard, so fire exit routing is not available."
MSG_NO_LOC = "No current or selected location. Choose an origin, custom coordinates or device location."
MSG_OK = ("Calculated from available map data; not an official evacuation plan. "
          "Follow emergency responders and building procedures.")
MSG_BLOCKED = "Every reachable exit route crosses a known blocked segment. No exit is recommended."
MSG_UNREACHABLE = "No evaluated exit could be reached with the available map data."


def is_fire_scenario(key) -> bool:
    return isinstance(key, str) and key.strip().lower() in config.FIRE_HAZARD_KEYS


def load_exits(path=None):
    """Returns (verified_exits, ignored_count, error_or_None)."""
    p = Path(path or config.FIRE_EXIT_DATA_PATH)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        features = data["features"]
        if not isinstance(features, list):
            raise ValueError("features is not a list")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [], 0, f"Exit data file could not be read ({type(exc).__name__})."
    exits, ignored = [], 0
    for n, f in enumerate(features, 1):
        try:
            props = f.get("properties") or {}
            coords = f["geometry"]["coordinates"]
            lon, lat = float(coords[0]), float(coords[1])
            source = props.get("source")
            if (props.get("verified") is not True or not isinstance(source, str) or not source.strip()
                    or not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180)):
                ignored += 1
                continue
            exits.append(FireExit(id=str(props.get("id") or f"exit-{n}"), name=str(props.get("name") or f"Exit {n}"),
                                  lat=lat, lon=lon, source=source.strip(),
                                  last_verified=props.get("last_verified"), kind=props.get("kind")))
        except (AttributeError, KeyError, IndexError, TypeError, ValueError):
            ignored += 1
    return exits, ignored, None


def get_fire_exit_result(origin, scenario_key, route_fn, path=None, max_candidates=8) -> FireExitResult:
    exits, ignored, err = load_exits(path)
    if not exits:
        msg = MSG_NO_DATA + (f" {err}" if err else "") + (f" {ignored} unverified or malformed record(s) were ignored." if ignored else "")
        return FireExitResult("no_data", msg, unverified_count=ignored)
    if not is_fire_scenario(scenario_key):
        return FireExitResult("no_fire_scenario", MSG_NO_FIRE, unverified_count=ignored)
    if origin is None or len(origin) < 2 or origin[0] is None or origin[1] is None:
        return FireExitResult("no_location", MSG_NO_LOC, unverified_count=ignored)

    notes = []
    exits.sort(key=lambda e: haversine_m(origin[0], origin[1], e.lat, e.lon))
    if len(exits) > max_candidates:
        notes.append(f"Only the nearest {max_candidates} of {len(exits)} verified exits were evaluated to limit routing calls.")
        exits = exits[:max_candidates]

    options = []
    for ex in exits:
        try:
            route = route_fn((origin[0], origin[1]), (ex.lat, ex.lon))
        except Exception as exc:
            log.warning("Exit routing failed: %s", type(exc).__name__)
            route = None
        m = route_metrics(route)
        if route is None or not m["coords"]:
            options.append(FireExitOption(ex, "unreachable"))
            continue
        status = "blocked" if (m["blocked"] or 0) > 0 else "ok"
        options.append(FireExitOption(ex, status, m["time_min"], m["distance_km"], m["risk"],
                                      None if m["blocked"] is None else int(m["blocked"]), m["coords"]))

    oks = [o for o in options if o.status == "ok"]
    if any(o.risk is None for o in oks):
        notes.append("Risk was not reported for some exits, so reachable exits were ranked by travel time only.")
    if any(o.blocked is None for o in options if o.status != "unreachable"):
        notes.append("Blocked-segment data was not reported, so blockage could not be checked.")
    all_risk = all(o.risk is not None for o in oks)
    inf = float("inf")
    order = {"ok": 0, "blocked": 1, "unreachable": 2}

    def key(o):
        t = o.time_min if o.time_min is not None else inf
        if o.status == "ok":
            return (0, (o.risk, t) if all_risk else (t,))
        if o.status == "blocked":
            return (1, (o.blocked or 0, t))
        return (2, ())

    options.sort(key=key)  # stable: ties keep nearest-first order
    first = options[0]
    if first.status == "ok":
        return FireExitResult("ok", MSG_OK, tuple(options), first.exit.id, ignored, tuple(notes))
    if first.status == "blocked":
        return FireExitResult("blocked", MSG_BLOCKED, tuple(options), None, ignored, tuple(notes))
    return FireExitResult("unreachable", MSG_UNREACHABLE, tuple(options), None, ignored, tuple(notes))
