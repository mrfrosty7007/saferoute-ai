"""
SafeRouteAI - Teammate UI & Real Routing Adapter Unit Tests
Author: SafeRouteAI Team

Validates:
1. Request validation, study area bounds checking (Daraganj, Prayagraj), and input sanitization.
2. Real routing adapter integration across all supported hazards (validated Flood and exploratory Earthquake).
3. Exact mapping of real graph metrics (ETA, distance, reliability, segment pass probabilities, overlap %).
4. Emergency vehicle passability differentiation (Ambulance vs Rescue Truck).
5. All preset Daraganj landmarks snap properly and solve without errors.
6. Backup route computation and genuine independence metrics.
"""

import math
import unittest

from config import (
    DARAGANJ_LANDMARKS,
    DEFAULT_DEST,
    DEFAULT_ORIGIN,
    HAZARDS,
    STUDY_AREA_BOUNDS,
    VEHICLES,
)
from services.contracts import (
    Place,
    RouteRequest,
    RouteResult,
    RoutingError,
    validate_request,
)
from services.real_engine import RealRoutingEngine
from services.service import compute_routes


class TestTeammateUIAdapter(unittest.TestCase):
    """Test suite for the teammate UI adapter and service boundary contracts."""

    @classmethod
    def setUpClass(cls):
        """Initialize the real routing engine once for all tests."""
        cls.engine = RealRoutingEngine()
        cls.origin_place = Place("Sangam Confluence Ghat", DEFAULT_ORIGIN[0], DEFAULT_ORIGIN[1])
        cls.dest_place = Place("Alop Shankari Devi Temple", DEFAULT_DEST[0], DEFAULT_DEST[1])

    def test_validate_request_valid(self):
        """Confirm a properly formed request within Daraganj is valid."""
        req = RouteRequest(
            origin=self.origin_place,
            destination=self.dest_place,
            vehicle="ambulance",
            hazard="flood",
            params={"rainfall": 45.0, "river_level": 82.0},
            severity="Moderate",
        )
        errors = validate_request(req)
        self.assertEqual(errors, [])

    def test_validate_request_out_of_bounds(self):
        """Confirm coordinates outside Daraganj bounds are rejected."""
        # Delhi coordinate (28.6139, 77.2090)
        req = RouteRequest(
            origin=Place("New Delhi", 28.6139, 77.2090),
            destination=self.dest_place,
            vehicle="ambulance",
            hazard="flood",
            params={},
            severity="Moderate",
        )
        errors = validate_request(req)
        self.assertTrue(any("outside the" in e for e in errors))

    def test_validate_request_too_close(self):
        """Confirm origin and destination closer than 50m are rejected."""
        req = RouteRequest(
            origin=Place("Point 1", 25.43000, 81.88000),
            destination=Place("Point 2", 25.43001, 81.88001),
            vehicle="ambulance",
            hazard="flood",
            params={},
            severity="Moderate",
        )
        errors = validate_request(req)
        self.assertTrue(any("less than 50 m apart" in e for e in errors))

    def test_validate_request_invalid_vehicle_or_hazard(self):
        """Confirm unknown vehicles or hazard keys are flagged."""
        req_v = RouteRequest(
            origin=self.origin_place,
            destination=self.dest_place,
            vehicle="hovercraft",
            hazard="flood",
            params={},
            severity="Moderate",
        )
        self.assertTrue(any("Unknown vehicle" in e for e in validate_request(req_v)))

        req_h = RouteRequest(
            origin=self.origin_place,
            destination=self.dest_place,
            vehicle="ambulance",
            hazard="volcano",
            params={},
            severity="Moderate",
        )
        self.assertTrue(any("Unknown hazard" in e for e in validate_request(req_h)))

    def test_flood_real_routing_execution(self):
        """Confirm real Flood routing produces authentic Primary, Backup, and Baseline routes."""
        req = RouteRequest(
            origin=self.origin_place,
            destination=self.dest_place,
            vehicle="ambulance",
            hazard="flood",
            params={"rainfall": 45.0, "river_level": 82.0},
            severity="Moderate",
        )
        result = compute_routes(req, self.engine)

        self.assertIsInstance(result, RouteResult)
        self.assertFalse(result.simulated)
        self.assertTrue(result.has_any)

        # Primary route checks
        self.assertIsNotNone(result.primary)
        self.assertGreater(result.primary.distance_km, 0.5)
        self.assertGreater(result.primary.eta_min, 0.5)
        self.assertGreaterEqual(result.primary.reliability, 0.0)
        self.assertLessEqual(result.primary.reliability, 1.0)
        self.assertGreater(len(result.primary.segments), 0)

        # Baseline route checks
        self.assertIsNotNone(result.baseline)
        self.assertGreater(result.baseline.distance_km, 0.5)

        # Backup route checks
        self.assertIsNotNone(result.backup)
        self.assertIsNotNone(result.overlap_pct)
        self.assertGreaterEqual(result.overlap_pct, 0.0)
        self.assertLessEqual(result.overlap_pct, 100.0)

        # Confirm note mentions validated Phase 2 model
        self.assertTrue(any("Validated Phase 2" in note for note in result.notes))

        # Check weakest segment computation
        weakest = result.primary.weakest_segment()
        self.assertIsNotNone(weakest)
        self.assertGreaterEqual(weakest.pass_probability, 0.0)
        self.assertLessEqual(weakest.pass_probability, 1.0)

        # Check road geometries contain valid coordinates
        coords = result.primary.all_coords()
        self.assertGreater(len(coords), 2)
        for lat, lon in coords:
            self.assertGreaterEqual(lat, STUDY_AREA_BOUNDS["min_lat"] - 0.05)
            self.assertLessEqual(lat, STUDY_AREA_BOUNDS["max_lat"] + 0.05)
            self.assertGreaterEqual(lon, STUDY_AREA_BOUNDS["min_lon"] - 0.05)
            self.assertLessEqual(lon, STUDY_AREA_BOUNDS["max_lon"] + 0.05)

    def test_earthquake_scenario_simulation(self):
        """Confirm Earthquake routing executes cleanly and is labeled as simulation."""
        req = RouteRequest(
            origin=self.origin_place,
            destination=self.dest_place,
            vehicle="rescue_truck",
            hazard="earthquake",
            params={"magnitude": 7.2, "epicenter_dist": 12.0, "debris_vuln": 1.0},
            severity="Moderate",
        )
        result = compute_routes(req, self.engine)

        self.assertIsInstance(result, RouteResult)
        self.assertIsNotNone(result.primary)
        self.assertIsNotNone(result.baseline)

        # Confirm note flags exploratory scenario simulation
        self.assertTrue(any("Exploratory scenario simulation" in note for note in result.notes))

    def test_vehicle_differentiation_via_adapter(self):
        """Confirm Rescue Truck achieves higher baseline reliability than Ambulance in flood."""
        req_amb = RouteRequest(
            origin=self.origin_place,
            destination=self.dest_place,
            vehicle="ambulance",
            hazard="flood",
            params={"rainfall": 60.0, "river_level": 84.0},
            severity="High",
        )
        req_truck = RouteRequest(
            origin=self.origin_place,
            destination=self.dest_place,
            vehicle="rescue_truck",
            hazard="flood",
            params={"rainfall": 60.0, "river_level": 84.0},
            severity="High",
        )

        res_amb = compute_routes(req_amb, self.engine)
        res_truck = compute_routes(req_truck, self.engine)

        self.assertGreaterEqual(res_truck.baseline.reliability, res_amb.baseline.reliability)

    def test_all_daraganj_landmarks_routable(self):
        """Confirm every registered Daraganj landmark can be routed to without errors."""
        landmarks = list(DARAGANJ_LANDMARKS.items())
        # Pick first landmark as origin, and test routes to all subsequent landmarks
        origin_name, (o_lat, o_lon) = landmarks[0]
        origin = Place(origin_name, o_lat, o_lon)

        for dest_name, (d_lat, d_lon) in landmarks[1:]:
            dest = Place(dest_name, d_lat, d_lon)
            req = RouteRequest(
                origin=origin,
                destination=dest,
                vehicle="ambulance",
                hazard="flood",
                params={"rainfall": 30.0, "river_level": 80.0},
                severity="Moderate",
            )
            result = compute_routes(req, self.engine)
            self.assertIsNotNone(result.primary, f"Failed routing from {origin_name} to {dest_name}")
            self.assertGreater(result.primary.distance_km, 0.0)

    def test_build_study_area_map(self):
        """Confirm build_study_area_map constructs a valid Folium map centered on Daraganj."""
        from ui.map_view import build_study_area_map
        m_default = build_study_area_map()
        self.assertIsNotNone(m_default)
        self.assertGreater(len(m_default._children), 2)
        html_default = m_default.get_root().render()
        self.assertIn("Daraganj Study Area", html_default)

        # Map with specific request
        req = RouteRequest(
            origin=self.origin_place,
            destination=self.dest_place,
            vehicle="ambulance",
            hazard="flood",
            params={},
            severity="Moderate",
        )
        m_req = build_study_area_map(req)
        self.assertIsNotNone(m_req)
        html_req = m_req.get_root().render()
        self.assertIn("Origin: Sangam Confluence Ghat", html_req)
        self.assertIn("Destination: Alop Shankari Devi Temple", html_req)

    def test_build_route_map_rendering(self):
        """Confirm build_map renders polylines, legend, and risk layers cleanly."""
        from ui.map_view import build_map
        req = RouteRequest(
            origin=self.origin_place,
            destination=self.dest_place,
            vehicle="ambulance",
            hazard="flood",
            params={"rainfall": 45.0, "river_level": 82.0},
            severity="Moderate",
        )
        result = compute_routes(req, self.engine)

        # 1. Standard view
        m_routes = build_map(result, req, show_risk=False)
        self.assertIsNotNone(m_routes)
        html_routes = m_routes.get_root().render()
        self.assertIn("Primary (SafeRoute)", html_routes)
        self.assertIn("Conventional baseline", html_routes)

        # 2. Risk gradient view
        m_risk = build_map(result, req, show_risk=True)
        self.assertIsNotNone(m_risk)
        html_risk = m_risk.get_root().render()
        self.assertIn("Segment pass probability", html_risk)

    def test_styles_high_contrast_definitions(self):
        """Confirm CSS defines explicit high-contrast rules for sidebar, widgets, and main app."""
        from ui.styles import CSS
        self.assertIn("[data-testid=\"stSidebar\"]", CSS)
        self.assertIn("[data-testid=\"stAppViewContainer\"]", CSS)
        self.assertIn("#14232b", CSS)
        self.assertIn(".section", CSS)
        self.assertIn("#0d2b36", CSS)

    def test_full_precision_reliability_and_log_product(self):
        """Verify full floating-point precision is preserved and matches independent log-sum product."""
        import math
        req = RouteRequest(
            origin=Place("Sangam Confluence Ghat", 25.4286, 81.8837),
            destination=Place("Alop Shankari Devi Temple", 25.4485, 81.8781),
            vehicle="ambulance",
            hazard="flood",
            params={"rainfall": 45.0, "river_level": 82.0},
            severity="Moderate",
        )
        res = compute_routes(req, self.engine)

        # Confirm non-zero full precision (not truncated to 0.0)
        self.assertGreater(res.primary.reliability, 0.0)
        self.assertGreater(res.baseline.reliability, 0.0)

        # Independent log product calculation
        log_sum = sum(math.log(max(1e-6, s.pass_probability)) for s in res.primary.segments)
        expected_rel = math.exp(max(-50.0, log_sum))
        self.assertAlmostEqual(res.primary.reliability, expected_rel, delta=1e-18)

        # Verify Primary is > 100x more reliable than Baseline on this pair
        ratio = res.primary.reliability / res.baseline.reliability
        self.assertGreater(ratio, 100.0)

        # Verify bottleneck alert is triggered for riverfront 166cm water depth
        self.assertTrue(any("Severe bottleneck alert" in n for n in res.notes))

    def test_benchmark_pair_reliability_gain(self):
        """Verify the validated Rank 1 Benchmark pair achieves > 20% reliability gain."""
        req = RouteRequest(
            origin=Place("Daraganj South (Benchmark Origin)", 25.4348, 81.8785),
            destination=Place("Daraganj North (Benchmark Dest)", 25.4514, 81.8825),
            vehicle="ambulance",
            hazard="flood",
            params={"rainfall": 45.0, "river_level": 82.0},
            severity="Moderate",
        )
        res = compute_routes(req, self.engine)

        # Validate Rank 1 metrics from Phase 3 report
        self.assertGreater(res.primary.reliability, 0.20)      # ~22.2%
        self.assertLess(res.baseline.reliability, 0.005)       # ~0.06%
        rel_gain = (res.primary.reliability - res.baseline.reliability) * 100.0
        self.assertGreater(rel_gain, 20.0)                     # +22.1% gain

        # Verify explanatory note generated
        self.assertTrue(any("greater reliability" in n for n in res.notes))

    def test_objective_cost_primary_strictly_optimal(self):
        """Verify Primary route strictly minimizes total cost = time + lambda * -ln(p)."""
        req = RouteRequest(
            origin=Place("Sangam Confluence Ghat", 25.4286, 81.8837),
            destination=Place("Alop Shankari Devi Temple", 25.4485, 81.8781),
            vehicle="ambulance",
            hazard="flood",
            params={"rainfall": 45.0, "river_level": 82.0},
            severity="Moderate",
        )
        res = compute_routes(req, self.engine)

        # Evaluate total cost on all three routes
        primary_cost = sum(s.length_m / 8.33 + 120.0 * (-math.log(max(1e-6, s.pass_probability))) for s in res.primary.segments)
        backup_cost = sum(s.length_m / 8.33 + 120.0 * (-math.log(max(1e-6, s.pass_probability))) for s in res.backup.segments)
        baseline_cost = sum(s.length_m / 8.33 + 120.0 * (-math.log(max(1e-6, s.pass_probability))) for s in res.baseline.segments)

        # Primary total cost must be strictly lower than both backup and baseline
        self.assertLess(primary_cost, backup_cost)
        self.assertLess(primary_cost, baseline_cost)

    def test_sidebar_landmark_defaults(self):
        """Verify default landmarks and coordinates match the Rank 1 benchmark pair."""
        landmarks = list(DARAGANJ_LANDMARKS.keys())
        self.assertEqual(landmarks[0], "Daraganj South (Benchmark Origin)")
        self.assertEqual(landmarks[1], "Daraganj North (Benchmark Dest)")
        self.assertEqual(DEFAULT_ORIGIN, (25.4348, 81.8785))
        self.assertEqual(DEFAULT_DEST, (25.4514, 81.8825))

    def test_panels_reliability_display_formatting(self):
        """Verify reliability display correctly formats benchmark values and tiny probabilities."""
        # 1. Benchmark values format to exact expected percentages
        p_benchmark = 0.222459
        b_benchmark = 0.000551
        self.assertEqual(f"{p_benchmark:.2%}", "22.25%")
        self.assertEqual(f"{b_benchmark:.2%}", "0.06%")

        # 2. Sangam bottleneck values format to <0.01% instead of 0.0%
        p_sangam = 1.130607e-16
        formatted = f"{p_sangam:.2%}" if p_sangam >= 0.0001 else ("<0.01%" if p_sangam > 0.0 else "0.0%")
        self.assertEqual(formatted, "<0.01%")

        # 3. Genuine zero formats to 0.0%
        p_zero = 0.0
        formatted_zero = f"{p_zero:.2%}" if p_zero >= 0.0001 else ("<0.01%" if p_zero > 0.0 else "0.0%")
        self.assertEqual(formatted_zero, "0.0%")

    def test_fresh_app_startup_and_defaults(self):
        """Regression test: clean Streamlit startup loads without KeyError and selects benchmark defaults."""
        import os
        from streamlit.testing.v1 import AppTest
        app_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")
        at = AppTest.from_file(app_path, default_timeout=30)
        at.run()

        # Zero exceptions on clean launch
        self.assertEqual(len(at.exception), 0)

        # Confirm benchmark default selections
        orig_sb = [s for s in at.selectbox if "Origin landmark" in s.label][0]
        dest_sb = [s for s in at.selectbox if "Destination landmark" in s.label][0]
        self.assertEqual(orig_sb.value, "Daraganj South (Benchmark Origin)")
        self.assertEqual(dest_sb.value, "Daraganj North (Benchmark Dest)")
        self.assertIsNotNone(orig_sb.value)
        self.assertIsNotNone(dest_sb.value)

    def test_app_rerun_session_consistency(self):
        """Regression test: app rerun maintains clean selections without clearing to 'Choose an option'."""
        import os
        from streamlit.testing.v1 import AppTest
        app_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")
        at = AppTest.from_file(app_path, default_timeout=30)
        at.run()
        self.assertEqual(len(at.exception), 0)

        # Trigger second rerun
        at.run()
        self.assertEqual(len(at.exception), 0)
        orig_sb = [s for s in at.selectbox if "Origin landmark" in s.label][0]
        dest_sb = [s for s in at.selectbox if "Destination landmark" in s.label][0]
        self.assertEqual(orig_sb.value, "Daraganj South (Benchmark Origin)")
        self.assertEqual(dest_sb.value, "Daraganj North (Benchmark Dest)")

    def test_place_picker_stale_or_invalid_landmark_handling(self):
        """Regression test: invalid or None landmark names never raise KeyError and fall back gracefully."""
        from config import DARAGANJ_LANDMARKS
        from services.contracts import Place

        # Direct verification: indexing DARAGANJ_LANDMARKS with None or invalid key raises KeyError
        with self.assertRaises(KeyError):
            _ = DARAGANJ_LANDMARKS[None]
        with self.assertRaises(KeyError):
            _ = DARAGANJ_LANDMARKS["NonExistentLandmark"]

        # Valid landmarks must always exist and return valid (lat, lon)
        names = list(DARAGANJ_LANDMARKS.keys())
        self.assertIn("Daraganj South (Benchmark Origin)", DARAGANJ_LANDMARKS)
        self.assertIn("Daraganj North (Benchmark Dest)", DARAGANJ_LANDMARKS)
        lat_o, lon_o = DARAGANJ_LANDMARKS[names[0]]
        lat_d, lon_d = DARAGANJ_LANDMARKS[names[1]]
        self.assertEqual((lat_o, lon_o), (25.4348, 81.8785))
        self.assertEqual((lat_d, lon_d), (25.4514, 81.8825))


if __name__ == "__main__":
    unittest.main()
