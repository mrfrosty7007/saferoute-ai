"""
Rakshapath - Regional Data Models and Schemas
Author: Rakshapath Team

Defines declarative data classes for regional metadata, administrative hierarchy,
bounding boxes, and support status across India.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class RegionStatus(str, Enum):
    """Support status of a regional study area."""
    SUPPORTED_BUNDLED = "supported_bundled"  # Bundled with repository and verified
    SUPPORTED_LOCAL = "supported_local"      # Ingested and cached locally on disk
    PARTIAL = "partial"                      # Road network available, hazard model uncalibrated
    UNAVAILABLE = "unavailable"              # Listed in administrative registry, no graph ingested


@dataclass(frozen=True)
class BoundingBox:
    """Geographic bounding box for a study area."""
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

    def contains(self, lat: float, lon: float, buffer_deg: float = 0.0) -> bool:
        """Check if a coordinate falls within this bounding box with optional buffer."""
        return (
            (self.min_lat - buffer_deg) <= lat <= (self.max_lat + buffer_deg)
            and (self.min_lon - buffer_deg) <= lon <= (self.max_lon + buffer_deg)
        )

    def to_dict(self) -> Dict[str, float]:
        return {
            "min_lat": self.min_lat,
            "max_lat": self.max_lat,
            "min_lon": self.min_lon,
            "max_lon": self.max_lon,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> BoundingBox:
        return cls(
            min_lat=float(data["min_lat"]),
            max_lat=float(data["max_lat"]),
            min_lon=float(data["min_lon"]),
            max_lon=float(data["max_lon"]),
        )


@dataclass
class RegionMetadata:
    """
    Complete metadata describing a regional routing network in India.
    Decouples geographic boundaries and assets from hardcoded constants.
    """
    region_id: str
    display_name: str
    state: str
    district: str
    city: str
    center_lat: float
    center_lon: float
    radius_meters: float
    bounds: BoundingBox
    status: RegionStatus
    status_description: str
    graph_file: str
    # Requests farther than this from a road node are rejected instead of snapped.
    snap_tolerance_m: float = 500.0
    depressions_file: Optional[str] = None
    elevations_file: Optional[str] = None
    metadata_file: Optional[str] = None
    landmarks: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    default_origin: Tuple[float, float] = (0.0, 0.0)
    default_dest: Tuple[float, float] = (0.0, 0.0)
    supported_hazards: Tuple[str, ...] = ("flood", "earthquake")
    elevation_availability: str = "SRTM 30m / Copernicus DEM"
    hazard_model_availability: str = "Hydrodynamic Backwater + Depression Ponding"
    data_provenance: str = "OSM Overpass via OSMnx"
    version: str = "1.0.0"
    country: str = "India"
    notes: List[str] = field(default_factory=list)

    @property
    def meters_per_deg_lat(self) -> float:
        """Meters per degree latitude (~111.32 km)."""
        return 111320.0

    @property
    def meters_per_deg_lon(self) -> float:
        """Local meters per degree longitude, scaling with cosine of latitude."""
        return 111320.0 * math.cos(math.radians(self.center_lat))

    @property
    def radius_m(self) -> float:
        """Alias for radius_meters in meters."""
        return self.radius_meters

    @property
    def is_routable(self) -> bool:
        """True if the region possesses an active graph capable of routing."""
        return self.status in (RegionStatus.SUPPORTED_BUNDLED, RegionStatus.SUPPORTED_LOCAL)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-serializable dictionary."""
        d = asdict(self)
        d["status"] = self.status.value
        d["bounds"] = self.bounds.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RegionMetadata:
        """Construct RegionMetadata from a dictionary."""
        d = dict(data)
        d["status"] = RegionStatus(d["status"])
        d["bounds"] = BoundingBox.from_dict(d["bounds"])
        if "supported_hazards" in d and isinstance(d["supported_hazards"], list):
            d["supported_hazards"] = tuple(d["supported_hazards"])
        return cls(**d)
