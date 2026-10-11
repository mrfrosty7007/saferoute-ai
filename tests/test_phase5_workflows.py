"""Focused Streamlit workflow regressions for Phase 5 release verification."""

import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from services.contracts import RoutingError
from ui.map_view import build_map
from folium.vector_layers import PolyLine


class TestPhase5Workflows(unittest.TestCase):
    def setUp(self):
        self.app_path = str(Path(__file__).resolve().parents[1] / "app.py")

    def test_default_benchmark_pair_calculates_routes(self):
        app = AppTest.from_file(self.app_path, default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.selectbox[1].value, "Daraganj South (Benchmark Origin)")
        self.assertEqual(app.selectbox[2].value, "Daraganj North (Benchmark Dest)")

        for vehicle_key in ("ambulance", "fire_tender", "rescue_truck"):
            app.session_state["vehicle"] = vehicle_key
            app.run()
            app.button[0].click().run()
            self.assertEqual(len(app.exception), 0)
            result = app.session_state["result"]
            self.assertIsNotNone(result.primary)
            self.assertIsNotNone(result.backup)
            self.assertIsNotNone(result.baseline)
            self.assertEqual(app.session_state["result_request"].vehicle, vehicle_key)
            if vehicle_key == "ambulance":
                self.assertGreaterEqual(len(result.primary.elevation_profile), 2)
                self.assertEqual(len(app.get("vega_lite_chart")), 1)

        app.session_state["hazard"] = "earthquake"
        app.run()
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(app.session_state["result"].simulated)

    def test_coordinate_origin_can_generate_routes(self):
        app = AppTest.from_file(self.app_path, default_timeout=30).run()
        app.radio[1].set_value("Coordinates").run()
        app.number_input[0].set_value(25.4352)
        app.number_input[1].set_value(81.8783).run()
        self.assertEqual(len(app.exception), 0)

        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertAlmostEqual(app.session_state["result_request"].origin.lat, 25.4352)
        self.assertAlmostEqual(app.session_state["result_request"].origin.lon, 81.8783)

    def test_warning_stage_precision_and_recalculation(self):
        app = AppTest.from_file(self.app_path, default_timeout=30).run()
        app.button[0].click().run()
        normal_result = app.session_state["result"]
        river_slider = next(s for s in app.slider if s.label == "River stage elevation (m)")
        river_slider.set_value(84.7).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.slider[1].value, 84.7)

        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        request = app.session_state["result_request"]
        self.assertEqual(request.params["river_level"], 84.7)
        self.assertEqual(app.session_state["result_sig"], request.signature())
        warning_result = app.session_state["result"]
        self.assertEqual(warning_result.primary.distance_km, normal_result.primary.distance_km)
        self.assertEqual(warning_result.primary.eta_min, normal_result.primary.eta_min)
        self.assertEqual(warning_result.primary.reliability, normal_result.primary.reliability)
        self.assertEqual(
            [segment.coords for segment in warning_result.primary.segments],
            [segment.coords for segment in normal_result.primary.segments],
        )
        self.assertAlmostEqual(
            warning_result.primary.elevation_profile[-1][0],
            warning_result.primary.distance_km,
            delta=0.01,
        )
        rendered_map = build_map(warning_result, request, show_risk=False)
        route_lines = [child for child in rendered_map._children.values() if isinstance(child, PolyLine)]
        self.assertEqual(
            [tuple(point) for point in route_lines[2].locations],
            warning_result.primary.all_coords(),
        )

    def test_unreachable_route_is_presented_as_a_clear_error(self):
        app = AppTest.from_file(self.app_path, default_timeout=30).run()
        with patch("services.service.compute_routes", side_effect=RoutingError("No connected path exists for this scenario.")):
            app.button[0].click().run()

        self.assertEqual(len(app.exception), 0)
        self.assertIsNone(app.session_state["result"])
        self.assertIsNone(app.session_state["result_request"])
        self.assertTrue(any("Routes were not calculated." in item.value for item in app.markdown))
        self.assertTrue(any("No connected path exists for this scenario." in item.value for item in app.markdown))

    def test_switching_to_unavailable_region_and_reset_restores_benchmark(self):
        app = AppTest.from_file(self.app_path, default_timeout=30).run()
        app.selectbox(key="region_state").set_value("Maharashtra").run()

        self.assertEqual(app.session_state["region_state"], "Maharashtra")
        self.assertEqual(app.session_state["region_district"], "Mumbai Suburban")
        self.assertEqual(app.session_state["region_id"], "mumbai_kurla")
        self.assertEqual(app.session_state["origin_landmark"], "Kurla West Station")
        self.assertTrue(any("UNAVAILABLE" in item.value for item in app.warning))

        app.session_state["errors"] = ["stale region error"]
        app.button[1].click().run()

        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["region_state"], "Uttar Pradesh")
        self.assertEqual(app.session_state["region_district"], "Prayagraj")
        self.assertEqual(app.session_state["region_id"], "daraganj_prayagraj")
        self.assertEqual(app.session_state["origin_landmark"], "Daraganj South (Benchmark Origin)")
        self.assertEqual(app.session_state["dest_landmark"], "Daraganj North (Benchmark Dest)")
        self.assertEqual(app.session_state["origin_lat"], 25.4348)
        self.assertEqual(app.session_state["dest_lat"], 25.4514)
        self.assertEqual(app.session_state["errors"], [])
        self.assertFalse(app.warning)

    def test_risk_radio_selects_risk_segment_rendering(self):
        app = AppTest.from_file(self.app_path, default_timeout=30).run()
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)

        app.radio(key="map_view").set_value("Routes with risk").run()
        self.assertEqual(app.session_state["map_view"], "Routes with risk")
        result = app.session_state["result"]
        request = app.session_state["result_request"]
        plain_map = build_map(result, request, show_risk=False)
        risk_map = build_map(result, request, show_risk=True)
        plain_lines = [item for item in plain_map._children.values() if isinstance(item, PolyLine)]
        risk_lines = [item for item in risk_map._children.values() if isinstance(item, PolyLine)]
        self.assertGreater(len(risk_lines), len(plain_lines))


if __name__ == "__main__":
    unittest.main()
