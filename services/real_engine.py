"""
SafeRouteAI - Real Routing Engine Adapter
Author: SafeRouteAI Team

Adapter implementing the teammate's service contract (route(RouteRequest) -> RouteResult)
by delegating to the verified SafeRouteAI Phase 1, Phase 2, and Phase 3 backend modules.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import networkx as nx

from saferoute.data import load_cached_graph
from saferoute.hazard import get_hazard_model
from saferoute.risk import precompute_depressions
from saferoute.routing import RouteResult as BackendRouteResult, RoutingEngine
from services.contracts import Route, RouteRequest, RouteResult, RoutingError, Segment


class RealRoutingEngine:
    """
    Production adapter that executes genuine risk-aware pathfinding on the
    Daraganj, Prayagraj road network graph.
    """
    simulated: bool = False

    def __init__(self, G_base: Optional[nx.MultiDiGraph] = None, depressions: Optional[dict] = None):
        """Initialize engine, caching the base network and precomputed depressions."""
        self.G_base = G_base if G_base is not None else load_cached_graph()
        self.depressions = depressions if depressions is not None else precompute_depressions(self.G_base)

    def route(self, request: RouteRequest) -> RouteResult:
        """
        Execute real multi-hazard risk evaluation and routing for the given request.

        Args:
            request: RouteRequest with origin, destination, vehicle, hazard, and parameters.

        Returns:
            services.contracts.RouteResult populated with real primary, backup, and baseline routes.
        """
        # 1. Instantiate the appropriate hazard model
        try:
            if request.hazard == "flood":
                hazard_model = get_hazard_model(request.hazard, depressions=self.depressions)
            else:
                hazard_model = get_hazard_model(request.hazard)
        except ValueError as exc:
            raise RoutingError(str(exc)) from exc

        # 2. Map request parameters to hazard model arguments
        params = request.params or {}
        if request.hazard == "flood":
            raw_river = float(params.get("river_level", 82.0))
            # Handle both relative meters above gauge (e.g. 2.5m) and absolute elevation (e.g. 82.0m)
            river_level_m = raw_river if raw_river >= 70.0 else (79.5 + raw_river)
            rainfall_mm_hr = float(params.get("rainfall", 45.0))

            G_enriched = hazard_model.evaluate_risk(
                self.G_base,
                vehicle=request.vehicle,
                river_level_m=river_level_m,
                rainfall_mm_hr=rainfall_mm_hr,
            )
        elif request.hazard == "earthquake":
            magnitude = float(params.get("magnitude", 7.2))
            epicenter_dist = float(params.get("epicenter_dist", 12.0))
            debris_vuln = float(params.get("debris_vuln", 1.0))

            G_enriched = hazard_model.evaluate_risk(
                self.G_base,
                vehicle=request.vehicle,
                intensity_mmi=magnitude,
                epicenter_dist_km=epicenter_dist,
                debris_vulnerability=debris_vuln,
            )
        else:
            raise RoutingError(f"Hazard '{request.hazard}' is not yet supported by the routing engine.")

        # 3. Instantiate RoutingEngine with the enriched graph
        engine = RoutingEngine(G_enriched, vehicle=request.vehicle, lambda_val=120.0)

        # 4. Snap origin and destination coordinates to network nodes
        try:
            source_node = engine.snap_to_nearest_node(request.origin.lat, request.origin.lon)
            target_node = engine.snap_to_nearest_node(request.destination.lat, request.destination.lon)
        except Exception as exc:
            raise RoutingError(f"Failed to snap coordinates to the road network: {exc}") from exc

        if source_node == target_node:
            raise RoutingError("Origin and destination snapped to the exact same road node. Choose locations further apart.")

        # 5. Solve Primary, Backup, and Baseline routes
        try:
            backend_routes = engine.route_all(source_node, target_node)
        except nx.NetworkXNoPath:
            raise RoutingError(
                f"No connected path exists between origin ({request.origin.name}) and "
                f"destination ({request.destination.name}) under the active hazard conditions."
            )
        except Exception as exc:
            raise RoutingError(f"Pathfinding calculation error: {exc}") from exc

        # 6. Convert backend RouteResults into contract Route objects
        primary_route = self._convert_route(backend_routes["primary"], engine, "primary")
        backup_route = self._convert_route(backend_routes["backup"], engine, "backup")
        baseline_route = self._convert_route(backend_routes["baseline"], engine, "baseline")

        # 7. Calculate overlap percentage
        overlap_pct: Optional[float] = None
        if backend_routes.get("backup") is not None:
            overlap_pct = round(backend_routes["backup"].overlap_with_primary * 100.0, 1)

        # 8. Add contextual notes
        notes: List[str] = []
        if request.hazard == "flood":
            notes.append("Validated Phase 2 hydrodynamic backwater and elevation ponding model.")
        elif request.hazard == "earthquake":
            notes.append("Exploratory scenario simulation for Daraganj urban morphology (Not a live seismic forecast).")

        rel_gain = (primary_route.reliability - baseline_route.reliability) * 100.0
        if rel_gain >= 0.5:
            notes.append(f"SafeRoute delivers +{rel_gain:.1f}% greater reliability over conventional shortest path.")
        elif primary_route.reliability > 0 and baseline_route.reliability > 0:
            ratio = primary_route.reliability / baseline_route.reliability
            if ratio >= 1.5:
                notes.append(f"SafeRoute achieves {ratio:.1f}× higher relative survival probability than conventional baseline.")
        elif primary_route.reliability > 0 and baseline_route.reliability == 0:
            notes.append("SafeRoute navigates elevated ground, avoiding impassable flooded segments that sever the baseline path.")

        # Check for impassable bottleneck segment
        w_p = primary_route.weakest_segment()
        if w_p and w_p.pass_probability < 0.50:
            notes.append(
                f"Severe bottleneck alert: Weakest segment on primary route has only {w_p.pass_probability:.1%} pass probability "
                f"(water depth exceeds safe clearance). Corridor is physically hazardous for standard {request.vehicle}."
            )

        return RouteResult(
            primary=primary_route,
            backup=backup_route,
            baseline=baseline_route,
            overlap_pct=overlap_pct,
            simulated=False,
            source=f"SafeRouteAI Risk-Aware Routing Engine ({hazard_model.display_name})",
            notes=notes,
        )

    def _convert_route(
        self,
        b_route: BackendRouteResult,
        engine: RoutingEngine,
        kind: str,
    ) -> Route:
        """Convert a backend RouteResult to a frontend Route contract."""
        segments: List[Segment] = []

        for seg_info in b_route.segments:
            u, v = seg_info.u, seg_info.v
            u_node = engine.graph.nodes[u]
            v_node = engine.graph.nodes[v]

            # Extract actual road geometry from base graph if available
            coords: List[Tuple[float, float]] = []
            orig_k = engine.graph[u][v].get("original_key", 0)
            if self.G_base.has_edge(u, v, orig_k) and "geometry" in self.G_base[u][v][orig_k]:
                geom = self.G_base[u][v][orig_k]["geometry"]
                coords = [(float(lat), float(lon)) for lon, lat in geom.coords]
            else:
                coords = [(float(u_node["y"]), float(u_node["x"])), (float(v_node["y"]), float(v_node["x"]))]

            # Risk = 1.0 - pass_probability (preserve full floating precision)
            p = seg_info.pass_probability
            risk = max(0.0, min(1.0, 1.0 - p))
            label = f"Edge {u} -> {v}"

            segments.append(
                Segment(
                    coords=coords,
                    risk=float(risk),
                    length_m=round(seg_info.length_m, 1),
                    label=label,
                )
            )

        return Route(
            kind=kind,
            segments=segments,
            eta_min=round(b_route.eta_min, 1),
            distance_km=round(b_route.distance_km, 2),
            reliability=float(b_route.reliability),
        )


def build() -> RealRoutingEngine:
    """Factory function for RealRoutingEngine."""
    return RealRoutingEngine()
