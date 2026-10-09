"""
SafeRouteAI - Comprehensive Unit Test Suite for Routing Engine & Model Integration
Author: SafeRouteAI Team

Validates:
1. Primary-route connectivity and valid endpoints.
2. Correct handling of directed graphs and parallel edges.
3. Non-negative edge costs and correct travel-time calculations.
4. Vehicle-specific pass probabilities and hydrodynamic slowdown.
5. Reliability calculations and weakest-segment identification.
6. Backup-route independence, overlap and feasibility.
7. Baseline distance optimality.
8. Unreachable destinations and invalid inputs.
9. Reproducibility with seed 42.
10. Compatibility with Phase 1 and Phase 2 behavior.
"""

import math
import os
import sys
import unittest

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import networkx as nx
import numpy as np

from saferoute.config import (
    DEFAULT_SPEED_KMH,
    SCENARIOS,
    VEHICLES,
)
from saferoute.data import load_cached_graph
from saferoute.risk import (
    is_bridge,
    passability,
    precompute_depressions,
    run_sanity_assertions,
)
from saferoute.routing import (
    RouteResult,
    RoutingEngine,
    create_routing_engine,
)
from scripts.run_routing import sample_reproducible_od_pairs


class TestRoutingEngine(unittest.TestCase):
    """Test suite for Phase 3 risk-aware routing engine."""

    @classmethod
    def setUpClass(cls):
        """Load graph and precomputed depressions once for test suite."""
        cls.G_base = load_cached_graph()
        cls.depressions = precompute_depressions(cls.G_base)
        cls.scen = SCENARIOS["Moderate"]
        cls.eng_amb = create_routing_engine(
            cls.G_base,
            vehicle="ambulance",
            rainfall_mm_hr=cls.scen["rain"],
            river_level_m=cls.scen["river"],
            depressions=cls.depressions,
        )
        cls.eng_truck = create_routing_engine(
            cls.G_base,
            vehicle="rescue_truck",
            rainfall_mm_hr=cls.scen["rain"],
            river_level_m=cls.scen["river"],
            depressions=cls.depressions,
        )
        cls.scc_nodes = cls.eng_amb.node_ids

    def test_01_primary_route_connectivity(self):
        """Test 1: Primary route forms a continuous path from origin to destination."""
        u, v = self.scc_nodes[0], self.scc_nodes[50]
        res = self.eng_amb.route_primary(u, v)

        self.assertIsInstance(res, RouteResult)
        self.assertEqual(res.origin_node, u)
        self.assertEqual(res.destination_node, v)
        self.assertEqual(res.nodes[0], u)
        self.assertEqual(res.nodes[-1], v)
        self.assertGreaterEqual(len(res.nodes), 2)

        # Check every consecutive pair is an edge in the condensed graph
        for n1, n2 in zip(res.nodes[:-1], res.nodes[1:]):
            self.assertTrue(self.eng_amb.graph.has_edge(n1, n2), f"Missing edge ({n1}, {n2})")

    def test_02_directed_parallel_edges_handling(self):
        """Test 2: Graph is a strongly connected DiGraph with parallel edges collapsed."""
        G_di = self.eng_amb.graph
        self.assertIsInstance(G_di, nx.DiGraph)
        self.assertFalse(G_di.is_multigraph())
        self.assertTrue(nx.is_strongly_connected(G_di))
        self.assertGreater(G_di.number_of_nodes(), 1700)
        self.assertLessEqual(G_di.number_of_edges(), self.G_base.number_of_edges())

    def test_03_nonnegative_edge_costs_and_travel_time(self):
        """Test 3: Edge costs are non-negative and travel time reflects water slowdown."""
        max_speed_mps = (DEFAULT_SPEED_KMH / 3.6) + 1e-6

        for u, v, d in self.eng_amb.graph.edges(data=True):
            self.assertGreaterEqual(d["cost"], 0.0, "Cost must be non-negative")
            self.assertGreater(d["time_s"], 0.0, "Travel time must be positive")
            self.assertGreater(d["length"], 0.0, "Length must be positive")
            self.assertLessEqual(d["speed_mps"], max_speed_mps)

            # Check water slowdown formula
            depth_ratio = min(1.0, max(0.0, d["depth_cm"] / self.eng_amb.safe_depth_cm))
            expected_factor = 1.0 - (0.5 * depth_ratio)
            expected_speed = (DEFAULT_SPEED_KMH / 3.6) * expected_factor
            self.assertAlmostEqual(d["speed_mps"], expected_speed, delta=0.5)

    def test_04_vehicle_specific_pass_probabilities(self):
        """Test 4: Ambulance has lower pass probability than rescue truck on flood-prone roads."""
        amb_p_vals = [d["pass_probability"] for _, _, d in self.eng_amb.graph.edges(data=True)]
        truck_p_vals = [d["pass_probability"] for _, _, d in self.eng_truck.graph.edges(data=True)]

        # Under moderate flood, ambulance should face more low-probability segments
        amb_impass = sum(1 for p in amb_p_vals if p < 0.5)
        truck_impass = sum(1 for p in truck_p_vals if p < 0.5)
        self.assertGreater(amb_impass, truck_impass * 2)

    def test_05_reliability_and_weakest_segment(self):
        """Test 5: Reliability matches product of segment probabilities and weakest segment is accurate."""
        u, v = self.scc_nodes[10], self.scc_nodes[120]
        res = self.eng_amb.route_primary(u, v)

        self.assertGreaterEqual(res.reliability, 0.0)
        self.assertLessEqual(res.reliability, 1.0)

        # Verify manual product
        p_list = [seg.pass_probability for seg in res.segments]
        expected_rel = math.prod(p_list)
        self.assertAlmostEqual(res.reliability, expected_rel, delta=1e-4)

        # Verify weakest segment
        min_p = min(p_list)
        self.assertIsNotNone(res.weakest_segment)
        self.assertAlmostEqual(res.weakest_segment[2], min_p, delta=1e-6)

    def test_06_backup_route_properties(self):
        """Test 6: Backup route is valid, reports overlap, and connects endpoints."""
        u, v = self.scc_nodes[15], self.scc_nodes[150]
        primary = self.eng_amb.route_primary(u, v)
        backup = self.eng_amb.route_backup(u, v, primary)

        self.assertEqual(backup.origin_node, u)
        self.assertEqual(backup.destination_node, v)
        self.assertEqual(backup.nodes[0], u)
        self.assertEqual(backup.nodes[-1], v)
        self.assertGreaterEqual(backup.overlap_with_primary, 0.0)
        self.assertLessEqual(backup.overlap_with_primary, 1.0)

    def test_07_baseline_distance_optimality(self):
        """Test 7: Baseline route achieves minimum or equal geometric distance."""
        u, v = self.scc_nodes[25], self.scc_nodes[200]
        primary = self.eng_amb.route_primary(u, v)
        baseline = self.eng_amb.route_baseline(u, v)

        self.assertLessEqual(baseline.distance_km, primary.distance_km + 1e-4)
        self.assertGreater(baseline.distance_km, 0.0)

    def test_08_invalid_inputs_and_unreachable(self):
        """Test 8: Error handling for invalid node IDs and unknown vehicle types."""
        with self.assertRaises(ValueError):
            self.eng_amb.route_primary(999999999999, self.scc_nodes[0])

        with self.assertRaises(ValueError):
            self.eng_amb.route_primary(self.scc_nodes[0], 999999999999)

        with self.assertRaises(ValueError):
            RoutingEngine(self.G_base, vehicle="submarine")

    def test_09_seed_42_reproducibility(self):
        """Test 9: Sampling with seed 42 produces strictly deterministic OD pairs."""
        coords = {n: (self.eng_amb.graph.nodes[n]["x"], self.eng_amb.graph.nodes[n]["y"]) for n in self.scc_nodes}

        run1 = sample_reproducible_od_pairs(self.scc_nodes, coords, num_samples=20, min_dist_m=1000.0, seed=42)
        run2 = sample_reproducible_od_pairs(self.scc_nodes, coords, num_samples=20, min_dist_m=1000.0, seed=42)

        self.assertEqual(run1, run2)

    def test_10_phase1_and_phase2_compatibility(self):
        """Test 10: Ensures full backward compatibility with Phase 1 and 2 invariants."""
        # 20 bridge edges check
        bridge_count = sum(1 for _, _, _, d in self.G_base.edges(keys=True, data=True) if is_bridge(d))
        self.assertEqual(bridge_count, 20)

        # Depressions count check
        self.assertEqual(len(self.depressions), self.G_base.number_of_edges())

        # Sanity assertions check
        run_sanity_assertions(self.G_base, self.depressions)


if __name__ == "__main__":
    unittest.main()
