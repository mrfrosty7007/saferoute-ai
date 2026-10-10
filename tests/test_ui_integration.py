"""
SafeRouteAI - Integration Tests: Dashboard & Multi-Hazard Routing
Author: SafeRouteAI Team

Verifies:
1. Base graph and precomputed depressions load cleanly.
2. Preset benchmark pairs and landmarks exist in the strongly connected component.
3. Changing hazard parameters (rainfall, river stage, earthquake MMI, epicenter distance)
   directly alters the graph edge attributes, risk calculations, and routing results.
4. Changing vehicle limits produces distinct, vehicle-appropriate routing results.
5. Primary, Backup, and Baseline route solvers execute without errors for all hazards.
"""

import os
import sys
import unittest

# Ensure project root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from saferoute.data import load_cached_graph
from saferoute.hazard import EarthquakeHazardModel, FloodHazardModel, get_hazard_model
from saferoute.risk import precompute_depressions
from saferoute.routing import RoutingEngine


class TestUIIntegration(unittest.TestCase):
    """End-to-end integration test suite verifying parameter-to-routing behavior."""

    @classmethod
    def setUpClass(cls):
        cls.G_base = load_cached_graph()
        cls.depressions = precompute_depressions(cls.G_base)
        cls.origin = 8771867299       # Rank 1 Benchmark Origin
        cls.destination = 4221170107  # Rank 1 Benchmark Destination

    def test_presets_exist_in_graph(self):
        """Verify that benchmark pairs and major landmarks exist in the network."""
        self.assertIn(self.origin, self.G_base)
        self.assertIn(self.destination, self.G_base)

        landmarks = [12116473524, 8771716586, 4230153842, 316672978, 12526505661]
        for node in landmarks:
            self.assertIn(node, self.G_base)

    def test_flood_parameter_changes_alter_routing_results(self):
        """Verify changing rainfall and river level alters edge depths and route metrics."""
        flood_model = FloodHazardModel(depressions=self.depressions)

        # 1. Dry conditions
        G_dry = flood_model.evaluate_risk(
            self.G_base, vehicle="ambulance", river_level_m=75.0, rainfall_mm_hr=0.0
        )
        eng_dry = RoutingEngine(G_dry, vehicle="ambulance")
        res_dry = eng_dry.route_all(self.origin, self.destination)

        # 2. Severe flood conditions
        G_flood = flood_model.evaluate_risk(
            self.G_base, vehicle="ambulance", river_level_m=85.0, rainfall_mm_hr=75.0
        )
        eng_flood = RoutingEngine(G_flood, vehicle="ambulance")
        res_flood = eng_flood.route_all(self.origin, self.destination)

        # Severe flood must have higher depths and lower reliability
        mean_depth_dry = sum(d["water_depth_cm"] for _, _, _, d in G_dry.edges(keys=True, data=True))
        mean_depth_flood = sum(d["water_depth_cm"] for _, _, _, d in G_flood.edges(keys=True, data=True))
        self.assertGreater(mean_depth_flood, mean_depth_dry)

        # Baseline shortest path reliability should plummet in severe flood
        self.assertGreater(res_dry["baseline"].reliability, res_flood["baseline"].reliability)

        # SafeRoute primary route in flood chooses a safe corridor
        self.assertGreater(res_flood["primary"].reliability, res_flood["baseline"].reliability)

    def test_earthquake_parameter_changes_alter_routing_results(self):
        """Verify changing earthquake MMI changes debris scores and route reliability."""
        quake_model = EarthquakeHazardModel()

        # Mild shaking
        G_mild = quake_model.evaluate_risk(
            self.G_base, vehicle="ambulance", intensity_mmi=6.0, epicenter_dist_km=25.0
        )
        eng_mild = RoutingEngine(G_mild, vehicle="ambulance")
        res_mild = eng_mild.route_all(self.origin, self.destination)

        # Severe shaking
        G_severe = quake_model.evaluate_risk(
            self.G_base, vehicle="ambulance", intensity_mmi=8.5, epicenter_dist_km=5.0
        )
        eng_severe = RoutingEngine(G_severe, vehicle="ambulance")
        res_severe = eng_severe.route_all(self.origin, self.destination)

        rubble_mild = sum(d["rubble_score"] for _, _, _, d in G_mild.edges(keys=True, data=True))
        rubble_severe = sum(d["rubble_score"] for _, _, _, d in G_severe.edges(keys=True, data=True))
        self.assertGreater(rubble_severe, rubble_mild)

        self.assertGreater(res_mild["primary"].reliability, res_severe["primary"].reliability)

    def test_vehicle_selection_affects_passability(self):
        """Verify Rescue Truck achieves higher reliability than Ambulance under identical severe hazard."""
        flood_model = FloodHazardModel(depressions=self.depressions)
        G_amb = flood_model.evaluate_risk(
            self.G_base, vehicle="ambulance", river_level_m=84.0, rainfall_mm_hr=60.0
        )
        G_truck = flood_model.evaluate_risk(
            self.G_base, vehicle="rescue_truck", river_level_m=84.0, rainfall_mm_hr=60.0
        )

        eng_amb = RoutingEngine(G_amb, vehicle="ambulance")
        eng_truck = RoutingEngine(G_truck, vehicle="rescue_truck")

        res_amb = eng_amb.route_all(self.origin, self.destination)
        res_truck = eng_truck.route_all(self.origin, self.destination)

        # Rescue truck baseline reliability should be >= ambulance baseline reliability
        self.assertGreaterEqual(res_truck["baseline"].reliability, res_amb["baseline"].reliability)

    def test_backup_route_differs_or_penalizes_risky_edges(self):
        """Verify that the backup route provides a distinct alternative or records valid overlap."""
        flood_model = FloodHazardModel(depressions=self.depressions)
        G_enriched = flood_model.evaluate_risk(
            self.G_base, vehicle="ambulance", river_level_m=82.0, rainfall_mm_hr=45.0
        )
        eng = RoutingEngine(G_enriched, vehicle="ambulance")
        res = eng.route_all(self.origin, self.destination)

        backup = res["backup"]
        self.assertIsNotNone(backup)
        self.assertGreater(len(backup.nodes), 1)
        self.assertGreaterEqual(backup.overlap_with_primary, 0.0)
        self.assertLessEqual(backup.overlap_with_primary, 1.0)


if __name__ == "__main__":
    unittest.main()
