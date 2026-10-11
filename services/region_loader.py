"""
Rakshapath - Regional Engine Loader and Memory-Conscious Cache
Author: Rakshapath Team

Provides thread-safe, on-demand loading of regional road network graphs and hazard models.
Maintains a bounded LRU cache (default max 2 regions in memory) to prevent memory exhaustion
on constrained hosting environments (e.g. Render 512MB RAM limit).
"""
from __future__ import annotations

import gc
import os
import threading
from collections import OrderedDict
from typing import Optional

from saferoute.data import load_cached_graph
from saferoute.regions import DEFAULT_REGION_ID, RegionMetadata, RegionStatus, registry
from saferoute.risk import precompute_depressions
from services.contracts import RoutingError
from services.real_engine import RealRoutingEngine


class RegionalEngineManager:
    """
    Manages bounded in-memory caching of RealRoutingEngine instances across Indian regions.
    """

    def __init__(self, max_cached_regions: int = 2):
        self.max_cached_regions = max(1, int(max_cached_regions))
        self._cache: OrderedDict[str, RealRoutingEngine] = OrderedDict()
        self._lock = threading.Lock()

    def get_engine(self, region_id: Optional[str] = None) -> RealRoutingEngine:
        """
        Retrieve or on-demand load the RealRoutingEngine for the requested region.
        Evicts the least-recently-used region if cache capacity is exceeded.

        Args:
            region_id: Target region identifier (defaults to daraganj_prayagraj).

        Returns:
            RealRoutingEngine configured for the region.
        """
        target_id = str(region_id).strip() if region_id else DEFAULT_REGION_ID
        reg = registry.get(target_id)
        if reg is None:
            raise RoutingError(f"Region '{target_id}' is not registered in the administrative catalog.")

        if not reg.is_routable:
            raise RoutingError(
                f"Region '{reg.display_name}' ({reg.state}) is currently {reg.status.value}. "
                f"{reg.status_description}"
            )

        with self._lock:
            if target_id in self._cache:
                # Move to MRU position
                self._cache.move_to_end(target_id)
                return self._cache[target_id]

            # Validate that the graph asset exists on disk before attempting to load
            if not os.path.exists(reg.graph_file):
                raise RoutingError(
                    f"Road network graph for '{reg.display_name}' not found on disk at: {reg.graph_file}. "
                    "Please run regional ingestion before routing."
                )

            # Load the graph
            try:
                G_base = load_cached_graph(reg.graph_file)
            except Exception as exc:
                raise RoutingError(f"Failed to load road network for '{reg.display_name}': {exc}") from exc

            # Load or precompute depressions
            depressions = None
            if reg.depressions_file and os.path.exists(reg.depressions_file):
                try:
                    depressions = precompute_depressions(
                        G_base,
                        cache_path=reg.depressions_file,
                        center_lat=reg.center_lat,
                        center_lon=reg.center_lon,
                    )
                except Exception:
                    depressions = None

            if depressions is None:
                dep_cache = reg.depressions_file or os.path.join(
                    os.path.dirname(reg.graph_file), "depressions.pkl"
                )
                depressions = precompute_depressions(
                    G_base,
                    cache_path=dep_cache,
                    center_lat=reg.center_lat,
                    center_lon=reg.center_lon,
                )

            engine = RealRoutingEngine(G_base=G_base, depressions=depressions, region=reg)

            # Insert into LRU cache
            self._cache[target_id] = engine

            # Evict LRU if capacity exceeded
            while len(self._cache) > self.max_cached_regions:
                evicted_id, evicted_engine = self._cache.popitem(last=False)
                del evicted_engine
                gc.collect()

            return engine

    def cached_region_ids(self) -> list[str]:
        """Return list of currently cached region IDs."""
        with self._lock:
            return list(self._cache.keys())

    def clear(self) -> None:
        """Evict all cached engines and trigger garbage collection."""
        with self._lock:
            self._cache.clear()
            gc.collect()


# Global singleton regional manager
engine_manager = RegionalEngineManager(max_cached_regions=2)
