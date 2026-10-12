"""Routing call boundary. The UI only ever calls compute_routes().

To plug in the real engine, set EMERGENCY_ENGINE="package.module:factory"
where factory() returns an object with route(RouteRequest) -> RouteResult.
"""
from __future__ import annotations

import importlib
import os

from services.contracts import RouteRequest, RouteResult, RoutingError, validate_request
from services.mock_engine import MockEngine


def load_engine():
    spec = os.environ.get("EMERGENCY_ENGINE", "").strip()
    if not spec:
        return MockEngine()
    module_name, _, attr = spec.partition(":")
    try:
        return getattr(importlib.import_module(module_name), attr or "build")()
    except (ImportError, AttributeError) as exc:
        raise RoutingError(f"Could not load routing engine '{spec}': {exc}") from exc


def compute_routes(request: RouteRequest, engine=None) -> RouteResult:
    problems = validate_request(request)
    if problems:
        raise RoutingError(" ".join(problems))
    engine = engine or load_engine()
    try:
        result = engine.route(request)
    except RoutingError:
        raise
    except Exception as exc:  # engine failures must never crash the dashboard
        raise RoutingError(f"The routing engine failed: {exc}") from exc
    if result is None or not result.has_any:
        raise RoutingError("No route could be found for this scenario.")
    return result


# --- SafeRoute Extras: thin wrappers only; the routing engine is untouched ---
from services.fire_exit import get_fire_exit_result  # noqa: E402
from services.nearby import find_nearby  # noqa: E402
from services.recommendation import build_recommendation  # noqa: E402


def get_nearby(reference, categories=None, radius_m=None):
    """reference is (lat, lon[, label]) or None."""
    if not reference:
        return find_nearby(None, None, categories, radius_m)
    return find_nearby(reference[0], reference[1], categories, radius_m)


def get_recommendation(primary, backup=None, baseline=None, hazard_label=None):
    return build_recommendation(primary, backup, baseline, hazard_label=hazard_label)


def get_fire_exits(origin, scenario_key, route_fn):
    return get_fire_exit_result(origin, scenario_key, route_fn)
