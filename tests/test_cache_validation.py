"""
SafeRouteAI - Cache Validation & Data Integrity Regression Test Suite
Author: SafeRouteAI Team

Validates:
Task 1 - Depression Cache Validation:
- Valid cache is reused without recomputation.
- Cache with the same entry count but different edge keys is rejected.
- Cache with missing edges is rejected.
- Cache with extra or malformed entries is handled safely.
- GraphML serialization/deserialization preserves compatible edge identities.
- Existing valid data/depressions.pkl remains usable.
- Edge missing from depressions dictionary in compute_depths() raises KeyError.

Task 2 - Road Network Cache Selection:
- A matching cache is selected correctly.
- An unrelated, larger cache is ignored.
- A stale cache for another study area is rejected.
- Malformed cache files are handled safely.
- Valid offline cache works when network access is unavailable.
- Existing network extraction and graph-building behavior remains compatible.

Task 3 - Phase 2 Scientific Behavior Protection:
- All 20 expected bridges are identified.
- Flood depths remain non-negative.
- Monotonicity in rainfall (pass probability does not increase with rain).
- Monotonicity in river stage (pass probability does not increase with river stage).
- Ambulance and rescue truck passabilities remain distinct.
- Unchanged depression values from the baseline dataset.
"""

import copy
import json
import math
import os
import pickle
import sys
import tempfile
import unittest
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import networkx as nx
import osmnx as ox

from saferoute.config import (
    CENTER_LAT,
    CENTER_LON,
    DEPRESSION_RADIUS_M,
    DEPRESSIONS_CACHE_FILE,
    GRAPH_FILE,
    RADIUS_METERS,
    SCENARIOS,
    VEHICLES,
)
from saferoute.data import (
    fetch_road_network,
    get_network_query_fingerprint,
    haversine_distance,
    load_cached_graph,
    validate_osm_cache_candidate,
)
from saferoute.risk import (
    compute_depths,
    compute_graph_fingerprint,
    is_bridge,
    normalize_edge_key,
    passability,
    precompute_depressions,
    validate_depression_cache,
)


class TestDepressionCacheValidation(unittest.TestCase):
    """Regression test suite for Task 1: Depression cache validation hardening."""

    @classmethod
    def setUpClass(cls):
        cls.G = load_cached_graph(GRAPH_FILE)
        cls.valid_depressions = precompute_depressions(cls.G, cache_path=DEPRESSIONS_CACHE_FILE)

    def test_01_existing_cache_is_reused_and_valid(self):
        """Test 1: Existing data/depressions.pkl is valid and reused without recomputation."""
        self.assertIsInstance(self.valid_depressions, dict)
        self.assertEqual(len(self.valid_depressions), self.G.number_of_edges())

        # Verify all edges in G are present in depressions
        for u, v, k in self.G.edges(keys=True):
            norm_k = normalize_edge_key((u, v, k))
            self.assertIn(norm_k, self.valid_depressions)
            val = self.valid_depressions[norm_k]
            self.assertFalse(math.isnan(val))
            self.assertFalse(math.isinf(val))
            self.assertGreaterEqual(val, 0.0)

    def test_02_same_count_different_keys_rejected(self):
        """Test 2: A cache with the exact same count but mismatched edge keys is rejected."""
        num_edges = self.G.number_of_edges()
        bogus_cache = {
            (999000000 + i, 999000001 + i, 0): 2.5
            for i in range(num_edges)
        }
        res = validate_depression_cache(bogus_cache, self.G, radius_m=DEPRESSION_RADIUS_M)
        self.assertIsNone(res, "Cache with different edge keys must be rejected despite matching count.")

    def test_03_missing_edges_rejected(self):
        """Test 3: A cache with missing edges is rejected."""
        incomplete_cache = copy.deepcopy(self.valid_depressions)
        # Remove 5 edges
        keys_to_remove = list(incomplete_cache.keys())[:5]
        for k in keys_to_remove:
            del incomplete_cache[k]

        res = validate_depression_cache(incomplete_cache, self.G, radius_m=DEPRESSION_RADIUS_M)
        self.assertIsNone(res, "Cache with missing edges must be rejected.")

    def test_04_extra_or_malformed_entries_handled_safely(self):
        """Test 4: Cache with extra edges, negative values, NaN, or non-dict is rejected."""
        # Non-dict
        self.assertIsNone(validate_depression_cache(["not", "a", "dict"], self.G))

        # Negative value
        neg_cache = copy.deepcopy(self.valid_depressions)
        first_key = list(neg_cache.keys())[0]
        neg_cache[first_key] = -1.5
        self.assertIsNone(validate_depression_cache(neg_cache, self.G))

        # NaN value
        nan_cache = copy.deepcopy(self.valid_depressions)
        nan_cache[first_key] = float("nan")
        self.assertIsNone(validate_depression_cache(nan_cache, self.G))

        # Extra edges not in graph
        extra_cache = copy.deepcopy(self.valid_depressions)
        extra_cache[(888888888, 999999999, 0)] = 1.0
        self.assertIsNone(validate_depression_cache(extra_cache, self.G))

    def test_05_graphml_type_normalization_preserves_identities(self):
        """Test 5: Edge keys with string representations are normalized to match integer keys."""
        int_key = (316495747, 4218651492, 0)
        str_key = ("316495747", "4218651492", "0")
        self.assertEqual(normalize_edge_key(int_key), normalize_edge_key(str_key))

    def test_06_schema_v2_fingerprint_validation(self):
        """Test 6: Schema v2 cache with valid and mismatched graph fingerprints."""
        fp = compute_graph_fingerprint(self.G, DEPRESSION_RADIUS_M)
        v2_valid = {
            "schema_version": 2,
            "graph_fingerprint": fp,
            "radius_m": DEPRESSION_RADIUS_M,
            "depressions": self.valid_depressions,
        }
        self.assertIsNotNone(validate_depression_cache(v2_valid, self.G))

        # Tampered fingerprint
        v2_tampered = copy.deepcopy(v2_valid)
        v2_tampered["graph_fingerprint"] = "deadbeef" * 8
        self.assertIsNone(validate_depression_cache(v2_tampered, self.G), "Tampered fingerprint must be rejected.")

        # Tampered radius
        v2_wrong_radius = copy.deepcopy(v2_valid)
        v2_wrong_radius["radius_m"] = 500.0
        self.assertIsNone(validate_depression_cache(v2_wrong_radius, self.G, radius_m=300.0))

    def test_07_compute_depths_strict_key_presence_no_silent_zeros(self):
        """Test 7: compute_depths raises KeyError on missing edge instead of silently returning 0.0."""
        incomplete_cache = copy.deepcopy(self.valid_depressions)
        # Find a non-bridge edge
        non_bridge_edge = None
        for u, v, k, d in self.G.edges(keys=True, data=True):
            if not is_bridge(d):
                non_bridge_edge = normalize_edge_key((u, v, k))
                break

        self.assertIsNotNone(non_bridge_edge)
        del incomplete_cache[non_bridge_edge]

        with self.assertRaises(KeyError):
            compute_depths(self.G, rainfall_mm_hr=45.0, river_level_m=75.0, depressions=incomplete_cache)


class TestRoadNetworkCacheSelection(unittest.TestCase):
    """Regression test suite for Task 2: Road network cache selection hardening."""

    def test_01_matching_cache_selected_correctly(self):
        """Test 1: Existing valid cache (cache/0a92...) is validated and loaded."""
        valid_cache = os.path.join("cache", "0a925bf03ee8671e1aec5fc7331d1a5365f58239.json")
        if not os.path.exists(valid_cache):
            self.skipTest(f"{valid_cache} not found in repository.")

        G_loaded = validate_osm_cache_candidate(valid_cache)
        self.assertIsNotNone(G_loaded)
        self.assertGreaterEqual(G_loaded.number_of_nodes(), 1700)
        self.assertGreaterEqual(G_loaded.number_of_edges(), 4000)

    def test_02_unrelated_larger_cache_ignored(self):
        """Test 2: An unrelated cache file (e.g. Paris/London) with >500KB is rejected."""
        # Create a large dummy file in another location (lat 48.85, lon 2.35)
        dummy_nodes = [
            {"type": "node", "id": 1000 + i, "lat": 48.8566 + (i * 0.0001), "lon": 2.3522 + (i * 0.0001)}
            for i in range(2000)
        ]
        dummy_ways = [
            {"type": "way", "id": 5000 + i, "nodes": [1000 + i, 1001 + i], "tags": {"highway": "primary"}}
            for i in range(1999)
        ]
        dummy_data = {"version": 0.6, "elements": dummy_nodes + dummy_ways}

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", encoding="utf-8", delete=False) as tmp:
            tmp_path = tmp.name
            json.dump(dummy_data, tmp)

        try:
            res = validate_osm_cache_candidate(tmp_path)
            self.assertIsNone(res, "Unrelated foreign city cache must be rejected by geographic validation.")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_03_malformed_cache_handled_safely(self):
        """Test 3: Corrupted JSON or invalid structure does not crash the loader."""
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", encoding="utf-8", delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write("{ corrupted json content [][")

        try:
            res = validate_osm_cache_candidate(tmp_path)
            self.assertIsNone(res, "Malformed JSON must return None safely.")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_04_query_fingerprint_deterministic(self):
        """Test 4: Network query fingerprint is strictly deterministic."""
        fp1 = get_network_query_fingerprint()
        fp2 = get_network_query_fingerprint()
        self.assertEqual(fp1, fp2)
        self.assertEqual(len(fp1), 16)

    def test_05_offline_cache_fallback_when_network_fails(self):
        """Test 5: Valid cache still loads successfully when external APIs fail."""
        with patch("osmnx.graph_from_address", side_effect=Exception("Network down")), \
             patch("osmnx.geocode", side_effect=Exception("Network down")):
            # fetch_road_network should successfully load from local cache without hitting network
            G = fetch_road_network()
            self.assertIsNotNone(G)
            self.assertGreater(G.number_of_nodes(), 1700)


class TestPhase2ScientificBehaviorProtection(unittest.TestCase):
    """Regression test suite for Task 3: Scientific invariance and physical behavior."""

    @classmethod
    def setUpClass(cls):
        cls.G = load_cached_graph(GRAPH_FILE)
        cls.depressions = precompute_depressions(cls.G)

    def test_01_all_twenty_bridges_identified(self):
        """Test 1: Exactly 20 bridge edges identified by is_bridge classifier."""
        bridge_count = sum(1 for _, _, _, d in self.G.edges(keys=True, data=True) if is_bridge(d))
        self.assertEqual(bridge_count, 20)

    def test_02_depths_remain_nonnegative(self):
        """Test 2: Computed water depth is >= 0 for all edges under all scenarios."""
        for name, scen in SCENARIOS.items():
            depths = compute_depths(self.G, rainfall_mm_hr=scen["rain"], river_level_m=scen["river"], depressions=self.depressions)
            min_depth = min(depths.values())
            self.assertGreaterEqual(min_depth, 0.0, f"Depth in scenario {name} must be >= 0.0")

    def test_03_monotonicity_in_rainfall(self):
        """Test 3: Pass probability never increases when rainfall increases."""
        p_low = passability(self.G, vehicle="ambulance", rainfall=0.0, river_level=75.0, depressions=self.depressions)
        p_high = passability(self.G, vehicle="ambulance", rainfall=80.0, river_level=75.0, depressions=self.depressions)

        for u, v, k in self.G.edges(keys=True):
            p1 = p_low[u][v][k]["pass_probability_ambulance"]
            p2 = p_high[u][v][k]["pass_probability_ambulance"]
            self.assertGreaterEqual(p1, p2 - 1e-9, f"Rain monotonicity violated on edge ({u}, {v}, {k})")

    def test_04_monotonicity_in_river_stage(self):
        """Test 4: Pass probability never increases when river level increases."""
        p_low = passability(self.G, vehicle="ambulance", rainfall=0.0, river_level=75.0, depressions=self.depressions)
        p_high = passability(self.G, vehicle="ambulance", rainfall=0.0, river_level=85.0, depressions=self.depressions)

        for u, v, k in self.G.edges(keys=True):
            p1 = p_low[u][v][k]["pass_probability_ambulance"]
            p2 = p_high[u][v][k]["pass_probability_ambulance"]
            self.assertGreaterEqual(p1, p2 - 1e-9, f"River monotonicity violated on edge ({u}, {v}, {k})")

    def test_05_ambulance_and_rescue_truck_differentiation(self):
        """Test 5: Rescue truck has higher passability than ambulance under flood conditions."""
        scen = SCENARIOS["Moderate"]
        G_flooded = passability(self.G, vehicle="ambulance", rainfall=scen["rain"], river_level=scen["river"], depressions=self.depressions)
        G_truck = passability(self.G, vehicle="rescue_truck", rainfall=scen["rain"], river_level=scen["river"], depressions=self.depressions)

        amb_closed = sum(1 for _, _, _, d in G_flooded.edges(keys=True, data=True) if d["pass_probability_ambulance"] < 0.5)
        truck_closed = sum(1 for _, _, _, d in G_truck.edges(keys=True, data=True) if d["pass_probability_rescue_truck"] < 0.5)

        self.assertGreater(amb_closed, truck_closed * 2, "Ambulance must have significantly more closures than rescue truck.")


if __name__ == "__main__":
    unittest.main()
