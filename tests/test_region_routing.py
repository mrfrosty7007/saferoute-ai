"""
Rakshapath - Regional Graph Loader and Routing Integration Tests
Author: Rakshapath Team

Tests RegionalEngineManager on-demand loading, bounded LRU cache eviction,
thread-safety, and synthetic multi-region routing.
"""
from __future__ import annotations

import os
import hashlib
import shutil
import tempfile
import unittest
import weakref
from concurrent.futures import ThreadPoolExecutor

import networkx as nx
import osmnx as ox

from saferoute.regions import (
    DEFAULT_REGION_ID,
    BoundingBox,
    RegionMetadata,
    RegionStatus,
    RegionRegistry,
    registry,
)
from services.contracts import Place, RouteRequest, RoutingError
from services.region_loader import RegionalEngineManager
from services.real_engine import RealRoutingEngine
from services.service import compute_routes


class TestRegionalRoutingIntegration(unittest.TestCase):
    """Test suite for RegionalEngineManager and multi-region routing execution."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.mgr = RegionalEngineManager(max_cached_regions=2)

    def tearDown(self):
        self.mgr.clear()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_dummy_graph_file(self, filename: str) -> str:
        """Create a tiny strongly connected graph file in temp_dir."""
        G = nx.MultiDiGraph()
        for i in range(5):
            G.add_node(i, x=80.0 + i * 0.001, y=13.0 + i * 0.001, elevation=10.0)
        for i in range(5):
            nxt = (i + 1) % 5
            G.add_edge(i, nxt, key=0, length=100.0, elev_min=10.0, bridge=False)
            G.add_edge(nxt, i, key=0, length=100.0, elev_min=10.0, bridge=False)

        path = os.path.join(self.temp_dir, filename)
        ox.save_graphml(G, path)
        return path

    def test_default_engine_load_and_cache(self):
        """Confirm default region loads cleanly and is stored in LRU cache."""
        engine = self.mgr.get_engine(DEFAULT_REGION_ID)
        self.assertIsNotNone(engine)
        self.assertEqual(engine.region.region_id, DEFAULT_REGION_ID)
        self.assertIn(DEFAULT_REGION_ID, self.mgr.cached_region_ids())

    def test_varanasi_osm_region_routes_with_explicit_synthetic_disclosure(self):
        """The checked-in OSM road graph is routeable, while its demo risks stay labeled synthetic."""
        region = registry.get("varanasi_ghats")
        self.assertTrue(region.is_routable)
        self.assertTrue(os.path.isfile(region.graph_file))
        self.assertTrue(os.path.isfile(region.depressions_file))

        request = RouteRequest(
            origin=Place("Assi Ghat", *region.landmarks["Assi Ghat"]),
            destination=Place("Kashi Vishwanath Corridor", *region.landmarks["Kashi Vishwanath Corridor"]),
            vehicle="ambulance",
            hazard="flood",
            params={"river_level": 82.0, "rainfall": 20.0},
            severity="Moderate",
            region_id=region.region_id,
        )
        result = compute_routes(request, self.mgr.get_engine(region.region_id))

        self.assertIsNotNone(result.primary)
        self.assertTrue(result.simulated)
        self.assertTrue(any("synthetic placeholders" in note for note in result.notes))
        self.assertTrue(any("flat 50 m placeholder" in note for note in result.notes))

    def test_mumbai_and_delhi_osm_regions_route_with_synthetic_disclosure(self):
        """Bundled city extracts route locally, while modeled hazard output stays synthetic."""
        for region_id in ("mumbai_kurla", "delhi_yamuna"):
            with self.subTest(region=region_id):
                region = registry.get(region_id)
                request = RouteRequest(
                    origin=Place("Origin", *region.default_origin),
                    destination=Place("Destination", *region.default_dest),
                    vehicle="ambulance",
                    hazard="flood",
                    params={"river_level": 82.0, "rainfall": 45.0},
                    severity="Moderate",
                    region_id=region_id,
                )
                result = compute_routes(request, self.mgr.get_engine(region_id))
                self.assertIsNotNone(result.primary)
                self.assertTrue(result.simulated)
                self.assertTrue(any("Regional demo data" in note for note in result.notes))
                self.assertGreater(result.primary.distance_km, 0.0)

    def test_missing_regional_depression_cache_does_not_overwrite_default(self):
        graph_file = self._make_dummy_graph_file("regional_cache.graphml")
        cache_file = os.path.join(self.temp_dir, "regional_depressions.pkl")
        region = RegionMetadata(
            region_id="test_region_cache_scope", display_name="Cache Scope", state="S", district="D", city="C",
            center_lat=13.0, center_lon=80.0, radius_meters=1000.0,
            bounds=BoundingBox(12.9, 13.1, 79.9, 80.1), status=RegionStatus.SUPPORTED_LOCAL,
            status_description="Test region", graph_file=graph_file, depressions_file=cache_file,
        )
        with open(os.path.join("data", "depressions.pkl"), "rb") as f:
            baseline_digest = hashlib.sha256(f.read()).digest()

        engine = RealRoutingEngine(G_base=ox.load_graphml(graph_file), region=region)

        self.assertTrue(os.path.isfile(cache_file))
        self.assertEqual(engine.region.region_id, region.region_id)
        with open(os.path.join("data", "depressions.pkl"), "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).digest(), baseline_digest)

    def test_lru_cache_eviction(self):
        """Confirm LRU cache evicts oldest region when max capacity is exceeded."""
        # Create 3 synthetic regions
        r1_graph = self._make_dummy_graph_file("r1.graphml")
        r2_graph = self._make_dummy_graph_file("r2.graphml")
        r3_graph = self._make_dummy_graph_file("r3.graphml")

        r1 = RegionMetadata(
            region_id="test_r1", display_name="R1", state="S", district="D", city="C",
            center_lat=13.0, center_lon=80.0, radius_meters=1000.0,
            bounds=BoundingBox(12.9, 13.1, 79.9, 80.1), status=RegionStatus.SUPPORTED_LOCAL,
            status_description="Ready", graph_file=r1_graph,
        )
        r2 = RegionMetadata(
            region_id="test_r2", display_name="R2", state="S", district="D", city="C",
            center_lat=13.0, center_lon=80.0, radius_meters=1000.0,
            bounds=BoundingBox(12.9, 13.1, 79.9, 80.1), status=RegionStatus.SUPPORTED_LOCAL,
            status_description="Ready", graph_file=r2_graph,
        )
        r3 = RegionMetadata(
            region_id="test_r3", display_name="R3", state="S", district="D", city="C",
            center_lat=13.0, center_lon=80.0, radius_meters=1000.0,
            bounds=BoundingBox(12.9, 13.1, 79.9, 80.1), status=RegionStatus.SUPPORTED_LOCAL,
            status_description="Ready", graph_file=r3_graph,
        )

        registry.register(r1)
        registry.register(r2)
        registry.register(r3)

        # Manager has max_cached_regions=2
        first_engine = self.mgr.get_engine("test_r1")
        evicted_engine = weakref.ref(first_engine)
        del first_engine
        self.mgr.get_engine("test_r2")
        self.assertEqual(self.mgr.cached_region_ids(), ["test_r1", "test_r2"])

        # Loading r3 should evict r1
        self.mgr.get_engine("test_r3")
        self.assertEqual(self.mgr.cached_region_ids(), ["test_r2", "test_r3"])
        self.assertNotIn("test_r1", self.mgr.cached_region_ids())
        self.assertIsNone(evicted_engine(), "The manager should release an engine after LRU eviction.")

    def test_unavailable_region_raises_routing_error(self):
        """Confirm requesting uningested region raises informative RoutingError."""
        with self.assertRaises(RoutingError) as ctx:
            self.mgr.get_engine("chennai_adyar")
        self.assertIn("unavailable", str(ctx.exception).lower())

    def test_missing_graph_file_raises_routing_error(self):
        """Confirm missing graph file on disk raises clear RoutingError."""
        r_missing = RegionMetadata(
            region_id="test_missing_file", display_name="Missing", state="S", district="D", city="C",
            center_lat=13.0, center_lon=80.0, radius_meters=1000.0,
            bounds=BoundingBox(12.9, 13.1, 79.9, 80.1), status=RegionStatus.SUPPORTED_LOCAL,
            status_description="Ready", graph_file=os.path.join(self.temp_dir, "nonexistent.graphml"),
        )
        registry.register(r_missing)
        with self.assertRaises(RoutingError) as ctx:
            self.mgr.get_engine("test_missing_file")
        self.assertIn("not found on disk", str(ctx.exception).lower())

    def test_concurrent_engine_retrieval(self):
        """Confirm thread-safe engine retrieval without race conditions."""
        def fetch():
            return self.mgr.get_engine(DEFAULT_REGION_ID)

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(fetch) for _ in range(8)]
            results = [f.result() for f in futures]

        self.assertEqual(len(results), 8)
        # All threads should receive the same cached instance
        self.assertEqual(len(set(id(r) for r in results)), 1)

    def test_synthetic_region_route_calculation(self):
        """Confirm full route calculation works end-to-end on a synthetic second region."""
        synth_graph = self._make_dummy_graph_file("synth_route.graphml")
        r_synth = RegionMetadata(
            region_id="test_synthetic_routable",
            display_name="Synthetic City Area",
            state="Test State",
            district="Test District",
            city="Test City",
            center_lat=13.0,
            center_lon=80.0,
            radius_meters=2000.0,
            bounds=BoundingBox(min_lat=12.95, max_lat=13.05, min_lon=79.95, max_lon=80.05),
            status=RegionStatus.SUPPORTED_LOCAL,
            status_description="Synthetic routable region",
            graph_file=synth_graph,
            default_origin=(13.0, 80.0),
            default_dest=(13.002, 80.002),
        )
        registry.register(r_synth)

        req = RouteRequest(
            origin=Place("Origin", 13.0, 80.0),
            destination=Place("Dest", 13.002, 80.002),
            vehicle="ambulance",
            hazard="flood",
            params={"river_level": 5.0, "rainfall": 20.0},
            severity="Moderate",
            region_id="test_synthetic_routable",
        )

        result = compute_routes(req)
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.primary)
        self.assertGreater(result.primary.distance_km, 0.0)


if __name__ == "__main__":
    unittest.main()
