"""
SafeRouteAI - Service Layer
Author: SafeRouteAI Team

Routing boundary: The dashboard calls compute_routes(request).
Loads the RealRoutingEngine by default, or an engine specified via EMERGENCY_ENGINE.
"""
from __future__ import annotations

import importlib
import os

from typing import Optional

from services.contracts import RouteRequest, RouteResult, RoutingError, validate_request
from services.real_engine import build as build_real_engine


def load_engine(region_id: Optional[str] = None):
    spec = os.environ.get("EMERGENCY_ENGINE", "").strip()
    if not spec:
        from services.region_loader import engine_manager
        return engine_manager.get_engine(region_id)
    module_name, _, attr = spec.partition(":")
    try:
        fn = getattr(importlib.import_module(module_name), attr or "build")
        try:
            return fn(region_id=region_id)
        except TypeError:
            return fn()
    except (ImportError, AttributeError) as exc:
        raise RoutingError(f"Could not load routing engine '{spec}': {exc}") from exc


def compute_routes(request: RouteRequest, engine=None) -> RouteResult:
    problems = validate_request(request)
    if problems:
        raise RoutingError(" ".join(problems))

    # Ensure engine matches the request's region
    target_region = getattr(request, "region_id", None)
    if engine is None:
        engine = load_engine(target_region)
    elif hasattr(engine, "region") and engine.region and target_region and engine.region.region_id != target_region:
        engine = load_engine(target_region)

    try:
        result = engine.route(request)
    except RoutingError:
        raise
    except Exception as exc:  # engine failures must never crash the dashboard
        raise RoutingError(f"The routing engine failed: {exc}") from exc
    if result is None or not result.has_any:
        raise RoutingError("No route could be found for this scenario.")
    return result
