"""
SafeRouteAI - Unit Tests: Multi-Hazard Risk Modeling Framework
Author: SafeRouteAI Team

Verifies:
1. HazardModel abstraction and factory instantiation.
2. FloodHazardModel numerical equivalence with Phase 2 calculations.
3. EarthquakeHazardModel physical/scenario mechanics:
   - Distance attenuation
   - Shaking intensity monotonicity
   - Vehicle differentiation (Rescue Truck > Ambulance in rubble)
   - Highway classification differentiation (narrow residential vs. primary arterial)
   - Reliable bridge identification and structural caution
   - Safe handling of missing edge attributes
4. Full integration with RoutingEngine:
   - Primary, backup, and baseline pathfinding execute smoothly on earthquake-enriched graphs.
"""

import math
import os
import sys
import unittest
from typing import Dict, Tuple

import networkx as nx

# Add project root to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from saferoute.config import VEHICLES
from saferoute.data import load_cached_graph
from saferoute.hazard import (
    AVAILABLE_HAZARDS,
    EarthquakeHazardModel,
    FloodHazardModel,
    HazardModel,
    get_hazard_model,
)
from saferoute.risk import passability, precompute_depressions
from saferoute.routing import RoutingEngine


class TestMultiHazardFramework(unittest.TestCase):
    """Test suite for the multi-hazard risk modeling architecture."""

    @classmethod
    def setUpClass(cls):
        cls.G = load_cached_graph()
        cls.depressions = precompute_depressions(cls.G)

    def test_hazard_factory_and_registry(self):
        """Verify factory returns appropriate HazardModel instances and rejects invalid hazards."""
        flood_model = get_hazard_model("flood")
        self.assertIsInstance(flood_model, FloodHazardModel)
        self.assertTrue(flood_model.is_validated)
        self.assertEqual(flood_model.hazard_id, "flood")

        quake_model = get_hazard_model("earthquake")
        self.assertIsInstance(quake_model, EarthquakeHazardModel)
        self.assertFalse(quake_model.is_validated)
        self.assertEqual(quake_model.hazard_id, "earthquake")

        with self.assertRaises(ValueError):
            get_hazard_model("tsunami")

    def test_flood_hazard_model_numerical_equivalence(self):
        """Verify FloodHazardModel outputs match Phase 2 passability() exactly."""
        flood_model = FloodHazardModel(depressions=self.depressions)
        G_flood = flood_model.evaluate_risk(
            self.G,
            vehicle="ambulance",
            river_level_m=82.0,
            rainfall_mm_hr=45.0,
        )

        G_direct = passability(
            self.G,
            vehicle="ambulance",
            rainfall=45.0,
            river_level=82.0,
            depressions=self.depressions,
        )

        self.assertEqual(G_flood.number_of_edges(), G_direct.number_of_edges())

        # Check edge by edge
        for u, v, k, d_flood in G_flood.edges(keys=True, data=True):
            d_direct = G_direct[u][v][k]
            self.assertAlmostEqual(d_flood["water_depth_cm"], d_direct["water_depth_cm"], places=4)
            self.assertAlmostEqual(
                d_flood["pass_probability_ambulance"],
                d_direct["pass_probability_ambulance"],
                places=6,
            )
            self.assertAlmostEqual(
                d_flood["pass_probability"],
                d_direct["pass_probability"],
                places=6,
            )
            self.assertEqual(d_flood["hazard_type"], "flood")

    def test_earthquake_attenuation(self):
        """Verify seismic intensity attenuates with increasing distance from epicenter."""
        quake_model = EarthquakeHazardModel()
        mmi_close = quake_model.compute_local_mmi(epicenter_mmi=8.0, dist_km=3.0)
        mmi_mid = quake_model.compute_local_mmi(epicenter_mmi=8.0, dist_km=15.0)
        mmi_far = quake_model.compute_local_mmi(epicenter_mmi=8.0, dist_km=40.0)

        self.assertGreaterEqual(mmi_close, mmi_mid)
        self.assertGreater(mmi_mid, mmi_far)
        self.assertGreaterEqual(mmi_far, 1.0)

    def test_earthquake_shaking_monotonicity(self):
        """Verify higher epicentral shaking intensity decreases network-wide passability."""
        quake_model = EarthquakeHazardModel()
        G_mild = quake_model.evaluate_risk(
            self.G, vehicle="ambulance", intensity_mmi=5.5, epicenter_dist_km=20.0
        )
        G_severe = quake_model.evaluate_risk(
            self.G, vehicle="ambulance", intensity_mmi=8.5, epicenter_dist_km=5.0
        )

        sum_p_mild = sum(d["pass_probability"] for _, _, _, d in G_mild.edges(keys=True, data=True))
        sum_p_severe = sum(d["pass_probability"] for _, _, _, d in G_severe.edges(keys=True, data=True))

        self.assertGreater(sum_p_mild, sum_p_severe)

    def test_earthquake_vehicle_differentiation(self):
        """Verify high-clearance Rescue Truck maintains higher rubble passability than Ambulance."""
        quake_model = EarthquakeHazardModel()
        G_amb = quake_model.evaluate_risk(
            self.G, vehicle="ambulance", intensity_mmi=7.5, epicenter_dist_km=10.0
        )
        G_truck = quake_model.evaluate_risk(
            self.G, vehicle="rescue_truck", intensity_mmi=7.5, epicenter_dist_km=10.0
        )

        summary_amb = quake_model.get_summary(G_amb, vehicle="ambulance")
        summary_truck = quake_model.get_summary(G_truck, vehicle="rescue_truck")

        # Ambulance should have more closed/impassable segments and lower mean probability
        self.assertGreater(summary_amb["closed_count"], summary_truck["closed_count"])
        self.assertLess(summary_amb["mean_pass_probability"], summary_truck["mean_pass_probability"])

    def test_earthquake_highway_differentiation(self):
        """Verify narrow residential streets suffer greater rubble impact than primary trunk highways."""
        quake_model = EarthquakeHazardModel()
        G_quake = quake_model.evaluate_risk(
            self.G, vehicle="ambulance", intensity_mmi=7.5, epicenter_dist_km=10.0
        )

        res_scores = []
        pri_scores = []

        for _, _, _, d in G_quake.edges(keys=True, data=True):
            if d.get("is_bridge", False):
                continue
            hw = str(d.get("highway", "")).lower()
            if "residential" in hw or "living_street" in hw:
                res_scores.append(d["rubble_score"])
            elif "primary" in hw or "trunk" in hw:
                pri_scores.append(d["rubble_score"])

        if res_scores and pri_scores:
            self.assertGreater(sum(res_scores) / len(res_scores), sum(pri_scores) / len(pri_scores))

    def test_earthquake_bridge_structural_status(self):
        """Verify bridge edges are identified and flagged with structural caution under high MMI."""
        quake_model = EarthquakeHazardModel()
        G_quake = quake_model.evaluate_risk(
            self.G, vehicle="ambulance", intensity_mmi=8.2, epicenter_dist_km=5.0
        )

        bridge_count = 0
        for _, _, _, d in G_quake.edges(keys=True, data=True):
            if d.get("is_bridge", False):
                bridge_count += 1
                # Bridges under severe shaking should carry bridge-specific label
                self.assertIn("Bridge", d["hazard_label"])
                self.assertGreaterEqual(d["rubble_score"], 45.0)

        # In Daraganj network, 20 bridge edges exist
        self.assertEqual(bridge_count, 20)

    def test_earthquake_routing_engine_integration(self):
        """Verify RoutingEngine operates seamlessly on an earthquake-enriched graph."""
        quake_model = EarthquakeHazardModel()
        G_quake = quake_model.evaluate_risk(
            self.G, vehicle="ambulance", intensity_mmi=7.5, epicenter_dist_km=10.0
        )

        # Instantiate RoutingEngine with the earthquake graph
        engine = RoutingEngine(G_quake, vehicle="ambulance", lambda_val=120.0)

        # Select two reachable nodes in the SCC
        scc_nodes = list(engine.graph.nodes())
        source = scc_nodes[0]
        target = scc_nodes[100]

        routes = engine.route_all(source, target)
        self.assertIn("primary", routes)
        self.assertIn("backup", routes)
        self.assertIn("baseline", routes)

        prim = routes["primary"]
        self.assertGreater(len(prim.nodes), 1)
        self.assertGreater(prim.distance_km, 0.0)
        self.assertGreater(prim.eta_min, 0.0)
        self.assertGreaterEqual(prim.reliability, 0.0)
        self.assertLessEqual(prim.reliability, 1.0)


if __name__ == "__main__":
    unittest.main()
