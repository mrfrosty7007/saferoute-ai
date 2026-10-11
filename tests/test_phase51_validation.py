"""Regression tests for scenario sensitivity and diverse backup routing."""

import unittest
import math

import networkx as nx

from saferoute.hazard import FloodHazardModel
from saferoute.routing import RoutingEngine
from saferoute.data import load_cached_graph
from saferoute.risk import precompute_depressions
from config import DEFAULT_ORIGIN, DEFAULT_DEST


def _diamond_graph(primary_edges, alternate_edges):
    graph = nx.MultiDiGraph()
    for node, (lon, lat, elevation) in {
        0: (81.880, 25.440, 84.0),
        1: (81.881, 25.440, 84.0),
        2: (81.882, 25.440, 84.0),
        3: (81.883, 25.440, 84.0),
    }.items():
        graph.add_node(node, x=lon, y=lat, elevation=elevation)
    for path_edges in (primary_edges, alternate_edges):
        for u, v, length_m, elev_min, probability in path_edges:
            attrs = {
                "length": length_m,
                "elev_min": elev_min,
                "pass_probability_ambulance": probability,
            }
            graph.add_edge(u, v, **attrs)
            graph.add_edge(v, u, **attrs)
    return graph


class TestPhase51Validation(unittest.TestCase):
    def test_default_warning_stage_changes_other_edges_not_selected_corridor(self):
        base = load_cached_graph()
        depressions = precompute_depressions(base)
        model = FloodHazardModel(depressions=depressions)
        normal_routes = warning_routes = None
        engines = {}
        for stage in (82.0, 84.7):
            evaluated = model.evaluate_risk(base, "ambulance", river_level_m=stage, rainfall_mm_hr=45.0)
            engines[stage] = RoutingEngine(evaluated, "ambulance")
            source = engines[stage].snap_to_nearest_node(*DEFAULT_ORIGIN)
            target = engines[stage].snap_to_nearest_node(*DEFAULT_DEST)
            routes = engines[stage].route_all(source, target)
            if stage == 82.0:
                normal_routes = routes
            else:
                warning_routes = routes

        normal_graph, warning_graph = engines[82.0].graph, engines[84.7].graph
        changed_edges = {
            (u, v) for u, v in normal_graph.edges
            if not math.isclose(
                normal_graph[u][v]["pass_probability"],
                warning_graph[u][v]["pass_probability"],
                rel_tol=0.0,
                abs_tol=1e-15,
            )
        }
        self.assertGreater(len(changed_edges), 0)
        changed_cost_edges = {
            (u, v) for u, v in normal_graph.edges
            if not math.isclose(
                normal_graph[u][v]["cost"],
                warning_graph[u][v]["cost"],
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        }
        self.assertGreater(len(changed_cost_edges), 0)
        for route_kind in ("primary", "backup", "baseline"):
            normal, warning = normal_routes[route_kind], warning_routes[route_kind]
            self.assertEqual(normal.nodes, warning.nodes)
            selected_edges = set(zip(normal.nodes[:-1], normal.nodes[1:]))
            self.assertFalse(selected_edges & changed_edges)
            self.assertFalse(selected_edges & changed_cost_edges)
            self.assertEqual(normal.eta_min, warning.eta_min)
            self.assertEqual(normal.distance_km, warning.distance_km)
            self.assertEqual(normal.reliability, warning.reliability)

    def test_stage_change_reweights_edges_and_selects_safer_corridor(self):
        low_corridor = [(0, 1, 100.0, 82.5, 1.0), (1, 3, 100.0, 82.5, 1.0)]
        high_corridor = [(0, 2, 400.0, 85.0, 1.0), (2, 3, 400.0, 85.0, 1.0)]
        base = _diamond_graph(low_corridor, high_corridor)
        depressions = {
            (u, v, key): 0.0
            for u, v, key in base.edges(keys=True)
        }
        model = FloodHazardModel(depressions=depressions)

        routes = {}
        graphs = {}
        for stage in (82.0, 84.7):
            evaluated = model.evaluate_risk(base, "ambulance", river_level_m=stage, rainfall_mm_hr=0.0)
            graphs[stage] = evaluated
            routes[stage] = RoutingEngine(evaluated, "ambulance").route_all(0, 3)

        self.assertEqual(routes[82.0]["primary"].nodes, [0, 1, 3])
        self.assertEqual(routes[84.7]["primary"].nodes, [0, 2, 3])
        low_edge_82 = graphs[82.0][0][1][0]
        low_edge_847 = graphs[84.7][0][1][0]
        self.assertLess(low_edge_847["pass_probability"], low_edge_82["pass_probability"])

        normal_engine = RoutingEngine(graphs[82.0], "ambulance")
        warning_engine = RoutingEngine(graphs[84.7], "ambulance")
        self.assertGreater(warning_engine.graph[0][1]["cost"], normal_engine.graph[0][1]["cost"])

    def test_backup_prefers_known_independent_alternative_with_bounded_tradeoff(self):
        primary_edges = [(0, 1, 100.0, 85.0, 0.98), (1, 3, 100.0, 85.0, 0.98)]
        alternate_edges = [(0, 2, 130.0, 85.0, 0.99), (2, 3, 130.0, 85.0, 0.99)]
        engine = RoutingEngine(_diamond_graph(primary_edges, alternate_edges), "ambulance")

        primary = engine.route_primary(0, 3)
        backup = engine.route_backup(0, 3, primary)

        self.assertEqual(primary.nodes, [0, 1, 3])
        self.assertEqual(backup.nodes, [0, 2, 3])
        self.assertEqual(backup.overlap_with_primary, 0.0)
        self.assertGreater(backup.eta_min, primary.eta_min)
        self.assertGreater(backup.reliability, primary.reliability)
        self.assertEqual(backup.has_impassable, False)


if __name__ == "__main__":
    unittest.main()
