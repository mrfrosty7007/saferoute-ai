"""
Rakshapath - Nationwide Regions Subsystem
Author: Rakshapath Team

Exports regional data models, bounding boxes, and the central RegionRegistry.
"""
from .models import BoundingBox, RegionMetadata, RegionStatus
from .registry import DEFAULT_REGION_ID, RegionRegistry, get_registry, registry

__all__ = [
    "BoundingBox",
    "RegionMetadata",
    "RegionStatus",
    "RegionRegistry",
    "DEFAULT_REGION_ID",
    "get_registry",
    "registry",
]
