"""
Rakshapath - Regional Registry Unit Tests
Author: Rakshapath Team

Tests regional metadata models, administrative state/district hierarchy,
bounding box calculations, and request validation under multi-region configurations.
"""
from __future__ import annotations

import os
import unittest

from saferoute.regions import (
    DEFAULT_REGION_ID,
    BoundingBox,
    RegionMetadata,
    RegionStatus,
    RegionRegistry,
    registry,
)
from services.contracts import Place, RouteRequest, validate_request


class TestRegionRegistry(unittest.TestCase):
    """Test suite for regional registry models and administrative hierarchy."""

    def test_default_region_is_daraganj(self):
        """Confirm DEFAULT_REGION_ID is daraganj_prayagraj and loads with complete metadata."""
        self.assertEqual(DEFAULT_REGION_ID, "daraganj_prayagraj")
        reg = registry.get(DEFAULT_REGION_ID)
        self.assertIsNotNone(reg)
        self.assertEqual(reg.state, "Uttar Pradesh")
        self.assertEqual(reg.district, "Prayagraj")
        self.assertEqual(reg.status, RegionStatus.SUPPORTED_BUNDLED)
        self.assertTrue(reg.is_routable)
        self.assertGreater(len(reg.landmarks), 0)
        self.assertEqual(reg.default_origin, (25.4348, 81.8785))
        self.assertEqual(reg.default_dest, (25.4514, 81.8825))

    def test_administrative_hierarchy_navigation(self):
        """Confirm states and districts can be enumerated cleanly."""
        states = registry.list_states()
        self.assertIn("Uttar Pradesh", states)
        self.assertIn("Maharashtra", states)
        self.assertIn("Karnataka", states)
        self.assertIn("Tamil Nadu", states)
        self.assertIn("Delhi", states)

        up_districts = registry.list_districts("Uttar Pradesh")
        self.assertIn("Prayagraj", up_districts)
        self.assertIn("Varanasi", up_districts)

        prayagraj_regions = registry.list_regions_for_district("Uttar Pradesh", "Prayagraj")
        self.assertEqual(len(prayagraj_regions), 1)
        self.assertEqual(prayagraj_regions[0].region_id, "daraganj_prayagraj")

    def test_bounding_box_containment(self):
        """Test BoundingBox.contains with and without buffer."""
        bbox = BoundingBox(min_lat=25.0, max_lat=26.0, min_lon=81.0, max_lon=82.0)
        # Inside
        self.assertTrue(bbox.contains(25.5, 81.5))
        # Outside
        self.assertFalse(bbox.contains(26.5, 81.5))
        # Outside without buffer, inside with buffer
        self.assertFalse(bbox.contains(26.02, 81.5, buffer_deg=0.0))
        self.assertTrue(bbox.contains(26.02, 81.5, buffer_deg=0.05))

    def test_local_longitude_scaling_by_latitude(self):
        """Test that meters_per_deg_lon correctly scales with latitude."""
        reg_equator = RegionMetadata(
            region_id="test_eq",
            display_name="Test Equator",
            state="Test",
            district="Test",
            city="Test",
            center_lat=0.0,
            center_lon=0.0,
            radius_meters=1000.0,
            bounds=BoundingBox(0, 0, 0, 0),
            status=RegionStatus.UNAVAILABLE,
            status_description="Test",
            graph_file="none",
        )
        self.assertAlmostEqual(reg_equator.meters_per_deg_lon, 111320.0, delta=1.0)

        daraganj = registry.get(DEFAULT_REGION_ID)
        # Around 25.44°N, meters_per_deg_lon should be ~100.5 km
        self.assertAlmostEqual(daraganj.meters_per_deg_lon, 100523.0, delta=200.0)

    def test_find_by_coordinates(self):
        """Test spatial lookup of regions from coordinates."""
        # Sangam / Daraganj coordinates
        found = registry.find_by_coordinates(25.4348, 81.8785)
        self.assertIsNotNone(found)
        self.assertEqual(found.region_id, "daraganj_prayagraj")

        # Far away (e.g. Arabian sea)
        none_found = registry.find_by_coordinates(15.0, 68.0)
        self.assertIsNone(none_found)

    def test_validate_request_with_unknown_region(self):
        """Confirm validate_request flags unknown region IDs."""
        req = RouteRequest(
            origin=Place("O", 25.4348, 81.8785),
            destination=Place("D", 25.4514, 81.8825),
            vehicle="ambulance",
            hazard="flood",
            params={},
            severity="Moderate",
            region_id="non_existent_region_999",
        )
        errs = validate_request(req)
        self.assertTrue(any("Unknown region" in e for e in errs))

    def test_validate_request_with_unavailable_region(self):
        """Confirm validate_request clearly reports unavailable expansion regions."""
        req = RouteRequest(
            origin=Place("Fancy Bazar", 26.1880, 91.7420),
            destination=Place("Railway Station", 26.1810, 91.7510),
            vehicle="ambulance",
            hazard="flood",
            params={},
            severity="Moderate",
            region_id="guwahati_brahmaputra",
        )
        errs = validate_request(req)
        self.assertTrue(any("currently unavailable" in e for e in errs))

    def test_varanasi_registry_separates_routable_roads_from_synthetic_hazards(self):
        region = registry.get("varanasi_ghats")
        self.assertTrue(region.is_routable)
        self.assertEqual(region.status, RegionStatus.SUPPORTED_LOCAL)
        self.assertIn("dummy placeholder", region.status_description)
        self.assertIn("Synthetic", region.hazard_model_availability)
        self.assertEqual(region.supported_hazards, ())

    def test_mumbai_and_delhi_are_routeable_demo_regions_with_local_assets(self):
        for region_id in ("mumbai_kurla", "delhi_yamuna"):
            with self.subTest(region=region_id):
                region = registry.get(region_id)
                self.assertEqual(region.status, RegionStatus.SUPPORTED_LOCAL)
                self.assertTrue(region.is_routable)
                self.assertTrue(os.path.isfile(region.graph_file))
                self.assertTrue(os.path.isfile(region.depressions_file))
                self.assertTrue(os.path.isfile(region.metadata_file))
                self.assertEqual(region.supported_hazards, ())
                self.assertIn("dummy placeholder", region.status_description)
                self.assertIn("synthetic", region.status_description.lower())

    def test_daraganj_request_uses_explicit_bounds_without_degree_buffer(self):
        def request(origin):
            return RouteRequest(
                origin=Place("O", *origin),
                destination=Place("D", 25.4514, 81.8825),
                vehicle="ambulance",
                hazard="flood",
                params={},
                severity="Moderate",
                region_id=DEFAULT_REGION_ID,
            )

        # Golden baseline landmarks remain valid, as does a point on the east
        # study-area boundary near a mapped road.
        self.assertEqual(validate_request(request((25.4348, 81.8785))), [])
        self.assertEqual(validate_request(request((25.443, 81.905))), [])

        reported = validate_request(request((25.51, 81.95)))
        self.assertTrue(any("outside the" in error for error in reported), reported)

        far = validate_request(request((19.07, 72.87)))
        self.assertTrue(any("outside the" in error for error in far), far)

    def test_serialization_round_trip(self):
        """Confirm RegionMetadata can serialize to and from dict cleanly."""
        daraganj = registry.get(DEFAULT_REGION_ID)
        d = daraganj.to_dict()
        reconstructed = RegionMetadata.from_dict(d)
        self.assertEqual(daraganj.region_id, reconstructed.region_id)
        self.assertEqual(daraganj.status, reconstructed.status)
        self.assertEqual(daraganj.bounds.min_lat, reconstructed.bounds.min_lat)

    def test_geographic_distortion_across_representative_indian_latitudes(self):
        """
        Verify dynamic cosine longitude scaling keeps distance error < 0.25%
        against geodesic Haversine across representative Indian latitudes (8°N to 34°N).
        """
        from saferoute.data import haversine_distance

        representative_points = [
            ("Kanyakumari", 8.08, 77.55),
            ("Chennai", 13.08, 80.27),
            ("Mumbai", 19.07, 72.87),
            ("Prayagraj", 25.43, 81.88),
            ("Delhi", 28.61, 77.20),
            ("Srinagar", 34.08, 74.79),
        ]

        delta_lon = 0.05  # ~4.5 to 5.5 km East-West offset
        for name, lat, lon in representative_points:
            reg = RegionMetadata(
                region_id=f"test_{name.lower()}",
                display_name=name,
                state="Test",
                district="Test",
                city=name,
                center_lat=lat,
                center_lon=lon,
                radius_meters=5000.0,
                bounds=BoundingBox(lat - 0.1, lat + 0.1, lon - 0.1, lon + 0.1),
                status=RegionStatus.UNAVAILABLE,
                status_description="Test",
                graph_file="none",
            )
            # Projected metric distance
            projected_dist_m = delta_lon * reg.meters_per_deg_lon
            # Geodesic ground-truth distance
            true_dist_m = haversine_distance(lat, lon, lat, lon + delta_lon)

            relative_error = abs(projected_dist_m - true_dist_m) / true_dist_m
            self.assertLess(relative_error, 0.0025, f"Distortion exceeded 0.25% at {name} ({lat}°N)")


if __name__ == "__main__":
    unittest.main()
