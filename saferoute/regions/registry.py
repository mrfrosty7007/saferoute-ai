"""
Rakshapath - Regional Registry
Author: Rakshapath Team

Central repository of nationwide states, districts, and study areas.
Preserves Daraganj, Prayagraj as the default validated benchmark while providing
a clean administrative hierarchy across India.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from .models import BoundingBox, RegionMetadata, RegionStatus

# Absolute path resolution root for data files
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_REGION_ID = "daraganj_prayagraj"

# Benchmark landmarks for Daraganj (preserves 100% backward compatibility)
DARAGANJ_LANDMARKS: Dict[str, Tuple[float, float]] = {
    "Daraganj South (Benchmark Origin)": (25.4348, 81.8785),
    "Daraganj North (Benchmark Dest)": (25.4514, 81.8825),
    "Alop Shankari Devi Temple (North-West)": (25.4485, 81.8781),
    "Bakhshi Bandh (North Collector)": (25.4539, 81.8721),
    "Sangam Confluence Ghat (Riverfront)": (25.4286, 81.8837),
    "Daraganj Railway Station (Central)": (25.4398, 81.8797),
    "Nagvasuki Temple (Riverfront East)": (25.4460, 81.8888),
}

# Declarative built-in regional catalog
_BUILTIN_REGIONS: List[RegionMetadata] = [
    # 1. Bundled & Verified Pilot Region (Daraganj, Prayagraj)
    RegionMetadata(
        region_id=DEFAULT_REGION_ID,
        display_name="Daraganj (Riverfront Pilot)",
        state="Uttar Pradesh",
        district="Prayagraj",
        city="Prayagraj",
        center_lat=25.4430,
        center_lon=81.8805,
        radius_meters=2000.0,
        bounds=BoundingBox(
            min_lat=25.420,
            max_lat=25.465,
            min_lon=81.855,
            max_lon=81.905,
        ),
        status=RegionStatus.SUPPORTED_BUNDLED,
        status_description="Validated riverfront pilot corridor (2 km radius) with checked-in road graph and elevation models.",
        graph_file=os.path.join(_REPO_ROOT, "data", "graph.graphml"),
        depressions_file=os.path.join(_REPO_ROOT, "data", "depressions.pkl"),
        elevations_file=os.path.join(_REPO_ROOT, "data", "elevations.json"),
        landmarks=DARAGANJ_LANDMARKS,
        default_origin=(25.4348, 81.8785),  # Daraganj South
        default_dest=(25.4514, 81.8825),    # Daraganj North
        supported_hazards=("flood", "earthquake"),
        elevation_availability="SRTM 30m / OpenTopoData DEM (100% enriched)",
        hazard_model_availability="Hydrodynamic Backwater + Depression Ponding (Validated Phase 2)",
        data_provenance="OSM Overpass drivable road network via OSMnx (1,823 nodes, 4,740 edges)",
        version="1.0.0",
        notes=[
            "Official Phase 1-3 validation baseline.",
            "River stage calibrated for Ganges/Yamuna confluence at Prayagraj.",
        ],
    ),

    # 2. Planned / Expansion Regions across Indian States (Explicitly Marked UNAVAILABLE)
    RegionMetadata(
        region_id="varanasi_ghats",
        display_name="Varanasi Ghats & Old City",
        state="Uttar Pradesh",
        district="Varanasi",
        city="Varanasi",
        center_lat=25.3050,
        center_lon=83.0100,
        radius_meters=3000.0,
        bounds=BoundingBox(min_lat=25.280, max_lat=25.335, min_lon=82.980, max_lon=83.040),
        status=RegionStatus.UNAVAILABLE,
        status_description="Planned expansion region. Road graph not yet ingested into local repository.",
        graph_file=os.path.join(_REPO_ROOT, "data", "regions", "varanasi_ghats", "graph.graphml"),
        landmarks={
            "Dashashwamedh Ghat": (25.3073, 83.0104),
            "Assi Ghat": (25.2885, 83.0064),
            "Kashi Vishwanath Corridor": (25.3109, 83.0107),
        },
        default_origin=(25.2885, 83.0064),
        default_dest=(25.3109, 83.0107),
        supported_hazards=("flood",),
        elevation_availability="Pending SRTM ingestion",
        hazard_model_availability="Pending calibration",
        data_provenance="Not ingested",
        version="0.1.0",
        notes=["Target region for Gangetic urban flooding expansion."],
    ),
    RegionMetadata(
        region_id="mumbai_kurla",
        display_name="Kurla & Mithi River Basin",
        state="Maharashtra",
        district="Mumbai Suburban",
        city="Mumbai",
        center_lat=19.0680,
        center_lon=72.8800,
        radius_meters=3500.0,
        bounds=BoundingBox(min_lat=19.040, max_lat=19.100, min_lon=72.850, max_lon=72.915),
        status=RegionStatus.UNAVAILABLE,
        status_description="Planned expansion region. Road graph not yet ingested into local repository.",
        graph_file=os.path.join(_REPO_ROOT, "data", "regions", "mumbai_kurla", "graph.graphml"),
        landmarks={
            "Kurla West Station": (19.0657, 72.8794),
            "BKC G-Block": (19.0600, 72.8650),
            "Bail Bazar": (19.0805, 72.8880),
        },
        default_origin=(19.0657, 72.8794),
        default_dest=(19.0600, 72.8650),
        supported_hazards=("flood",),
        elevation_availability="Pending SRTM ingestion",
        hazard_model_availability="Pending tidal/rainfall calibration",
        data_provenance="Not ingested",
        version="0.1.0",
        notes=["Target region for Mithi river overflow and coastal rain ponding."],
    ),
    RegionMetadata(
        region_id="delhi_yamuna",
        display_name="Yamuna Floodplain (Kashmere Gate)",
        state="Delhi",
        district="Central Delhi",
        city="New Delhi",
        center_lat=28.6670,
        center_lon=77.2300,
        radius_meters=3000.0,
        bounds=BoundingBox(min_lat=28.640, max_lat=28.700, min_lon=77.200, max_lon=77.260),
        status=RegionStatus.UNAVAILABLE,
        status_description="Planned expansion region. Road graph not yet ingested into local repository.",
        graph_file=os.path.join(_REPO_ROOT, "data", "regions", "delhi_yamuna", "graph.graphml"),
        landmarks={
            "Kashmere Gate ISBT": (28.6675, 77.2290),
            "Old Delhi Railway Station": (28.6619, 77.2274),
            "Monastery Market": (28.6750, 77.2340),
        },
        default_origin=(28.6675, 77.2290),
        default_dest=(28.6619, 77.2274),
        supported_hazards=("flood",),
        elevation_availability="Pending SRTM ingestion",
        hazard_model_availability="Pending calibration",
        data_provenance="Not ingested",
        version="0.1.0",
        notes=["Target region for Yamuna high discharge inundation."],
    ),
    RegionMetadata(
        region_id="chennai_adyar",
        display_name="Adyar River Basin (Saidapet - Kotturpuram)",
        state="Tamil Nadu",
        district="Chennai",
        city="Chennai",
        center_lat=13.0150,
        center_lon=80.2250,
        radius_meters=3000.0,
        bounds=BoundingBox(min_lat=12.990, max_lat=13.045, min_lon=80.200, max_lon=80.260),
        status=RegionStatus.UNAVAILABLE,
        status_description="Planned expansion region. Road graph not yet ingested into local repository.",
        graph_file=os.path.join(_REPO_ROOT, "data", "regions", "chennai_adyar", "graph.graphml"),
        landmarks={
            "Saidapet Bridge": (13.0210, 80.2220),
            "Kotturpuram": (13.0180, 80.2430),
            "Adyar Gate": (13.0250, 80.2520),
        },
        default_origin=(13.0210, 80.2220),
        default_dest=(13.0180, 80.2430),
        supported_hazards=("flood",),
        elevation_availability="Pending SRTM ingestion",
        hazard_model_availability="Pending calibration",
        data_provenance="Not ingested",
        version="0.1.0",
        notes=["Target region for northeast monsoon urban deluge."],
    ),
    RegionMetadata(
        region_id="bengaluru_bellandur",
        display_name="Bellandur - Outer Ring Road Corridor",
        state="Karnataka",
        district="Bengaluru Urban",
        city="Bengaluru",
        center_lat=12.9300,
        center_lon=77.6750,
        radius_meters=3000.0,
        bounds=BoundingBox(min_lat=12.900, max_lat=12.960, min_lon=77.645, max_lon=77.710),
        status=RegionStatus.UNAVAILABLE,
        status_description="Planned expansion region. Road graph not yet ingested into local repository.",
        graph_file=os.path.join(_REPO_ROOT, "data", "regions", "bengaluru_bellandur", "graph.graphml"),
        landmarks={
            "Bellandur Central Junction": (12.9320, 77.6740),
            "EcoSpace Tech Park": (12.9260, 77.6830),
            "Iblur Junction": (12.9230, 77.6680),
        },
        default_origin=(12.9320, 77.6740),
        default_dest=(12.9260, 77.6830),
        supported_hazards=("flood",),
        elevation_availability="Pending SRTM ingestion",
        hazard_model_availability="Pending calibration",
        data_provenance="Not ingested",
        version="0.1.0",
        notes=["Target region for urban depression flash flooding and drain overflow."],
    ),
    RegionMetadata(
        region_id="guwahati_brahmaputra",
        display_name="Guwahati Riverfront (Fancy Bazar)",
        state="Assam",
        district="Kamrup Metropolitan",
        city="Guwahati",
        center_lat=26.1850,
        center_lon=91.7450,
        radius_meters=3000.0,
        bounds=BoundingBox(min_lat=26.160, max_lat=26.210, min_lon=91.720, max_lon=91.775),
        status=RegionStatus.UNAVAILABLE,
        status_description="Planned expansion region. Road graph not yet ingested into local repository.",
        graph_file=os.path.join(_REPO_ROOT, "data", "regions", "guwahati_brahmaputra", "graph.graphml"),
        landmarks={
            "Fancy Bazar Ghat": (26.1880, 91.7420),
            "Guwahati Railway Station": (26.1810, 91.7510),
            "Panbazar": (26.1860, 91.7490),
        },
        default_origin=(26.1880, 91.7420),
        default_dest=(26.1810, 91.7510),
        supported_hazards=("flood", "earthquake"),
        elevation_availability="Pending SRTM ingestion",
        hazard_model_availability="Pending calibration",
        data_provenance="Not ingested",
        version="0.1.0",
        notes=["Target region for high-energy riverine floods and seismic Zone V simulation."],
    ),
]


class RegionRegistry:
    """
    In-memory registry managing regional metadata, administrative hierarchy,
    and boundary lookups.
    """

    def __init__(self, regions: Optional[List[RegionMetadata]] = None):
        self._regions: Dict[str, RegionMetadata] = {}
        initial = regions if regions is not None else _BUILTIN_REGIONS
        for r in initial:
            self.register(r)

    def register(self, region: RegionMetadata) -> None:
        """Register or update a region in the catalog."""
        self._regions[region.region_id] = region

    def get(self, region_id: str) -> Optional[RegionMetadata]:
        """Retrieve a region by ID, or None if not found."""
        return self._regions.get(region_id)

    def get_region(self, region_id: str) -> Optional[RegionMetadata]:
        """Alias for get(region_id)."""
        return self.get(region_id)

    def get_or_default(self, region_id: Optional[str] = None) -> RegionMetadata:
        """Retrieve the specified region or fall back safely to Daraganj benchmark."""
        if region_id and region_id in self._regions:
            return self._regions[region_id]
        return self._regions[DEFAULT_REGION_ID]

    def list_regions(self, routable_only: bool = False) -> List[RegionMetadata]:
        """List all registered regions, optionally filtering to currently routable ones."""
        regs = list(self._regions.values())
        if routable_only:
            regs = [r for r in regs if r.is_routable]
        return regs

    def list_states(self) -> List[str]:
        """List sorted unique states/UTs present in the registry."""
        return sorted({r.state for r in self._regions.values()})

    def list_districts(self, state: str) -> List[str]:
        """List sorted unique districts present in a state."""
        return sorted({r.district for r in self._regions.values() if r.state == state})

    def list_regions_for_district(self, state: str, district: str) -> List[RegionMetadata]:
        """List regions belonging to a state and district."""
        return [
            r for r in self._regions.values()
            if r.state == state and r.district == district
        ]

    def find_by_coordinates(self, lat: float, lon: float, buffer_deg: float = 0.0) -> Optional[RegionMetadata]:
        """
        Find a matching region containing the given coordinate.
        Prefers routable regions over unrouted placeholders.
        """
        matches = [
            r for r in self._regions.values()
            if r.bounds.contains(lat, lon, buffer_deg=buffer_deg)
        ]
        if not matches:
            return None
        # Prefer supported/routable regions if coordinate overlaps
        routable = [r for r in matches if r.is_routable]
        return routable[0] if routable else matches[0]

    def get_hierarchy(self) -> Dict[str, Dict[str, List[RegionMetadata]]]:
        """
        Return the complete administrative tree: State -> District -> [Regions].
        """
        tree: Dict[str, Dict[str, List[RegionMetadata]]] = {}
        for r in self._regions.values():
            tree.setdefault(r.state, {}).setdefault(r.district, []).append(r)
        return tree


# Global shared registry singleton
registry = RegionRegistry()


def get_registry() -> RegionRegistry:
    """Return the global RegionRegistry instance."""
    return registry
