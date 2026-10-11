"""
Rakshapath - Regional Ingestion Pipeline Unit Tests
Author: Rakshapath Team

Tests offline road network validation, strongly connected component extraction,
topological elevation filling, and metadata generation using synthetic graphs.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import networkx as nx

from saferoute.ingestion.pipeline import IngestionError, RegionIngestionPipeline
from saferoute.regions.models import BoundingBox, RegionMetadata, RegionStatus


class TestRegionIngestionPipeline(unittest.TestCase):
    """Test suite for RegionIngestionPipeline."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.pipeline = RegionIngestionPipeline(data_root=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_synthetic_graph(self, n_nodes: int = 30) -> nx.MultiDiGraph:
        """Create a synthetic strongly-connected directed road network."""
        G = nx.MultiDiGraph()
        for i in range(n_nodes):
            G.add_node(i, x=81.88 + i * 0.001, y=25.44 + i * 0.001, elevation=85.0 + (i % 5))

        # Build bidirectional ring plus cross edges for strong connectivity
        for i in range(n_nodes):
            nxt = (i + 1) % n_nodes
            G.add_edge(i, nxt, key=0, length=100.0, bridge=False)
            G.add_edge(nxt, i, key=0, length=100.0, bridge=False)
            if i % 3 == 0:
                opp = (i + 10) % n_nodes
                G.add_edge(i, opp, key=0, length=250.0, bridge="yes" if i == 0 else False)
                G.add_edge(opp, i, key=0, length=250.0, bridge=False)
        return G

    def test_validate_raw_network_bounds(self):
        """Confirm network size validation rejects empty, tiny, or huge graphs."""
        empty_g = nx.MultiDiGraph()
        with self.assertRaises(IngestionError):
            self.pipeline.validate_raw_network(empty_g, "Test Empty")

        tiny_g = nx.MultiDiGraph()
        for i in range(10):
            tiny_g.add_node(i, x=0, y=0)
        with self.assertRaises(IngestionError):
            self.pipeline.validate_raw_network(tiny_g, "Test Tiny")

        valid_g = self._create_synthetic_graph(25)
        # Should not raise
        self.pipeline.validate_raw_network(valid_g, "Test Valid")

    def test_extract_strongly_connected_component(self):
        """Confirm SCC extraction removes dead-end one-way branches."""
        G = self._create_synthetic_graph(25)
        # Add 3 dangling outgoing-only nodes
        G.add_node(99, x=81.9, y=25.5, elevation=90.0)
        G.add_edge(0, 99, key=0, length=50.0)

        G_scc, removed = self.pipeline.extract_strongly_connected_component(G)
        self.assertEqual(removed, 1)
        self.assertNotIn(99, G_scc.nodes())
        self.assertTrue(nx.is_strongly_connected(G_scc))

    def test_fill_and_validate_elevations(self):
        """Confirm missing elevations are filled from topological neighbors."""
        G = self._create_synthetic_graph(25)
        # Clear elevations on nodes 1 and 2
        G.nodes[1]["elevation"] = None
        G.nodes[2]["elevation"] = float("nan")

        filled = self.pipeline.fill_and_validate_elevations(G, default_elev_m=80.0)
        self.assertEqual(filled, 2)
        self.assertIsNotNone(G.nodes[1]["elevation"])
        self.assertFalse(math.isnan(G.nodes[2]["elevation"]))

        # Verify all edges received elev_min
        for _, _, _, d in G.edges(keys=True, data=True):
            self.assertIn("elev_min", d)
            self.assertIsInstance(d["elev_min"], float)

    def test_zero_and_mixed_missing_elevations(self):
        G = nx.MultiDiGraph()
        G.add_node("zero")
        G.add_node("positive")
        G.add_node("missing")
        G.add_node("nan")
        G.add_edge("zero", "positive", key=0)
        G.add_edge("positive", "zero", key=0)
        G.add_edge("positive", "missing", key=0)
        G.add_edge("missing", "positive", key=0)
        G.add_edge("missing", "nan", key=0)
        G.add_edge("nan", "missing", key=0)

        filled = self.pipeline.fill_and_validate_elevations(
            G,
            {"zero": 0.0, "positive": 12.5, "missing": None, "nan": float("nan")},
        )

        self.assertEqual(filled, 2)
        self.assertEqual(G.nodes["zero"]["elevation"], 0.0)
        self.assertEqual(G.nodes["positive"]["elevation"], 12.5)
        self.assertEqual(G.nodes["missing"]["elevation"], 12.5)
        self.assertEqual(G.nodes["nan"]["elevation"], 12.5)

    def test_string_missing_elevation_marker_is_filled(self):
        G = nx.MultiDiGraph()
        G.add_node(1, elevation=10.0)
        G.add_node(2)
        G.add_edge(1, 2, key=0)
        G.add_edge(2, 1, key=0)
        filled = self.pipeline.fill_and_validate_elevations(G, {"2": "NaN"})
        self.assertEqual(filled, 1)
        self.assertEqual(G.nodes[2]["elevation"], 10.0)

    def test_pipeline_process_and_save(self):
        """Confirm full synthetic region processing writes graph, depressions, and metadata."""
        G = self._create_synthetic_graph(30)
        region = RegionMetadata(
            region_id="test_synthetic_region",
            display_name="Test Synthetic Study Area",
            state="Test State",
            district="Test District",
            city="Test City",
            center_lat=25.44,
            center_lon=81.88,
            radius_meters=1500.0,
            bounds=BoundingBox(min_lat=25.40, max_lat=25.48, min_lon=81.80, max_lon=81.95),
            status=RegionStatus.SUPPORTED_LOCAL,
            status_description="Synthetic test region",
            graph_file="none",
        )

        out_dir = os.path.join(self.temp_dir, "output")
        g_path, dep_path, meta_path = self.pipeline.process_and_save(
            region=region,
            G_raw=G,
            output_dir=out_dir,
            default_elev_m=85.0,
        )

        self.assertTrue(os.path.exists(g_path))
        self.assertTrue(os.path.exists(dep_path))
        self.assertTrue(os.path.exists(meta_path))

        # Check metadata content
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        self.assertEqual(meta["region_id"], "test_synthetic_region")
        self.assertEqual(meta["node_count"], 30)
        self.assertGreater(meta["edge_count"], 0)


import math
import json

if __name__ == "__main__":
    unittest.main()
