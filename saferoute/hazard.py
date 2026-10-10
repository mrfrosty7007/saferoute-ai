"""
SafeRouteAI - Multi-Hazard Risk Modeling Framework
Author: SafeRouteAI Team

Provides a unified HazardModel abstraction separating disaster-specific physical/scenario
calculations from the shared routing engine.

Supported Hazard Models:
1. FloodHazardModel (Validated):
   - Reuses the Phase 2 hydrodynamic backwater + topographic depression ponding model.
   - Scientifically calibrated for the Daraganj, Prayagraj study area.
2. EarthquakeHazardModel (Scenario Simulation):
   - Explicitly designed as a scenario-based physical disruption simulation for Daraganj.
   - Models ground shaking attenuation, narrow urban street masonry collapse,
     bridge structural inspection cautions, and vehicle-specific rubble clearance.
   - Clearly documented as an exploratory scenario tool, NOT a live seismic forecast.
"""

import math
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Type, Union

import networkx as nx
import numpy as np

from .config import (
    BRIDGE_CLEARANCE_MARGIN_M,
    CM_PER_METER,
    DEPRESSION_RADIUS_M,
    DEPRESSIONS_CACHE_FILE,
    K_RAIN_FACTOR,
    PROBABILITY_EPSILON,
    SIGMOID_SCALE_S,
    VEHICLES,
)
from .risk import (
    compute_depths,
    is_bridge,
    pass_probability,
    passability,
    precompute_depressions,
)


class HazardModel(ABC):
    """
    Abstract Base Class for natural disaster risk models in SafeRouteAI.
    Decouples hazard-specific physics from the shared graph pathfinding engine.
    """

    hazard_id: str
    display_name: str
    description: str
    is_validated: bool
    geographic_coverage: str = "Daraganj, Prayagraj, India (2 km radius)"

    @abstractmethod
    def evaluate_risk(
        self,
        G: nx.MultiDiGraph,
        vehicle: str,
        **kwargs: Any,
    ) -> nx.MultiDiGraph:
        """
        Enrich a road network graph with hazard impact and passability attributes.

        Args:
            G: Base road network graph.
            vehicle: Vehicle identifier ('ambulance', 'fire_tender', 'rescue_truck').
            **kwargs: Hazard-specific parameters.

        Returns:
            A graph copy enriched with:
            - 'pass_probability': float in [PROBABILITY_EPSILON, 1.0]
            - f'pass_probability_{vehicle}': float in [PROBABILITY_EPSILON, 1.0]
            - 'water_depth_cm': float (0.0 if not flood)
            - 'closed': bool (True if pass_probability < 0.5)
            - 'hazard_type': str
            - 'hazard_severity': float
            - 'hazard_label': str
        """
        pass

    def get_summary(
        self,
        G_enriched: nx.MultiDiGraph,
        vehicle: str,
    ) -> Dict[str, Any]:
        """
        Compute high-level network impact summary for the active hazard and vehicle.

        Args:
            G_enriched: Graph previously evaluated by evaluate_risk.
            vehicle: Vehicle identifier.

        Returns:
            Dictionary with network statistics.
        """
        prob_attr = f"pass_probability_{vehicle}"
        total_edges = G_enriched.number_of_edges()

        closed_count = 0
        caution_count = 0
        safe_count = 0
        probs: List[float] = []

        for _, _, _, d in G_enriched.edges(keys=True, data=True):
            p = float(d.get(prob_attr, d.get("pass_probability", 1.0)))
            probs.append(p)
            if p < 0.5:
                closed_count += 1
            elif p < 0.8:
                caution_count += 1
            else:
                safe_count += 1

        closed_pct = (closed_count / total_edges * 100.0) if total_edges > 0 else 0.0
        mean_prob = float(np.mean(probs)) if probs else 1.0

        return {
            "hazard_id": self.hazard_id,
            "display_name": self.display_name,
            "is_validated": self.is_validated,
            "vehicle": vehicle,
            "total_edges": total_edges,
            "closed_count": closed_count,
            "closed_pct": round(closed_pct, 1),
            "caution_count": caution_count,
            "safe_count": safe_count,
            "mean_pass_probability": round(mean_prob, 3),
            "geographic_coverage": self.geographic_coverage,
        }


class FloodHazardModel(HazardModel):
    """
    Validated Flood Inundation & Topographic Depression Model (Phase 2).
    
    Models:
    1. Regional Ganges-Yamuna riverine stage elevation backwater inundation.
    2. Local topographic depression ponding (300m spatial neighborhood).
    3. Bridge exemption with 1.0m overtopping clearance margin.
    4. Vehicle-specific logistic sigmoid passability based on water clearance.
    """

    hazard_id = "flood"
    display_name = "Flood Inundation Model"
    description = (
        "Validated hydrodynamic model evaluating riverine stage rise and rainfall depression ponding "
        "calibrated for Daraganj, Prayagraj."
    )
    is_validated = True

    def __init__(
        self,
        depressions: Optional[Dict[Tuple[int, int, int], float]] = None,
        k_rain: float = K_RAIN_FACTOR,
    ):
        """
        Initialize the Flood Hazard Model.

        Args:
            depressions: Optional precomputed edge depressions dictionary.
            k_rain: Tunable rainfall ponding factor.
        """
        self.depressions = depressions
        self.k_rain = k_rain

    def evaluate_risk(
        self,
        G: nx.MultiDiGraph,
        vehicle: str,
        river_level_m: float = 82.0,
        rainfall_mm_hr: float = 45.0,
        **kwargs: Any,
    ) -> nx.MultiDiGraph:
        """
        Evaluate flood water depth and passability probabilities.
        Directly delegates to the validated Phase 2 passability engine.

        Args:
            G: Road network graph with 'elev_min' and node elevations.
            vehicle: Vehicle identifier ('ambulance', 'fire_tender', 'rescue_truck').
            river_level_m: Regional river stage in meters (default 82.0m).
            rainfall_mm_hr: Rainfall intensity in mm/hr (default 45.0 mm/hr).

        Returns:
            Enriched graph with water_depth_cm and pass_probability attributes.
        """
        if vehicle not in VEHICLES:
            raise ValueError(f"Unknown vehicle '{vehicle}'. Must be one of: {list(VEHICLES.keys())}")

        # Compute depressions if not already cached
        if self.depressions is None:
            self.depressions = precompute_depressions(G)

        # Re-use exact Phase 2 passability function
        G_enriched = passability(
            G=G,
            vehicle=vehicle,
            rainfall=float(rainfall_mm_hr),
            river_level=float(river_level_m),
            depressions=self.depressions,
            k=self.k_rain,
        )

        # Stamp hazard-specific metadata onto edges
        prob_attr = f"pass_probability_{vehicle}"
        for _, _, _, d in G_enriched.edges(keys=True, data=True):
            depth_cm = float(d.get("water_depth_cm", 0.0))
            p_val = float(d.get(prob_attr, 1.0))
            d["hazard_type"] = self.hazard_id
            d["hazard_severity"] = depth_cm
            d["hazard_label"] = f"{depth_cm:.1f} cm water" if depth_cm > 0.0 else "Dry"
            d["closed"] = bool(p_val < 0.5)

        return G_enriched


class EarthquakeHazardModel(HazardModel):
    """
    Scenario-Based Earthquake Structural & Debris Disruption Model.

    IMPORTANT DISCLAIMER:
    This is an exploratory scenario simulation designed to demonstrate multi-hazard routing
    capabilities for Daraganj's dense urban morphology. It is NOT a real-time seismic forecast
    nor a certified structural engineering prediction.

    Physics & Structural Assumptions:
    1. Ground Shaking Attenuation:
       Evaluates effective local Modified Mercalli Intensity (MMI_eff) using logarithmic
       distance attenuation from a simulated epicenter.
    2. Narrow Street Masonry Collapse Vulnerability:
       In historic Daraganj, dense narrow streets ('residential', 'living_street', 'service')
       face high debris-shedding risk from unreinforced masonry structures abutting narrow rights-of-way.
       Wide arterial corridors ('primary', 'secondary', 'trunk') maintain wider clearance setbacks.
    3. Bridge Structural Restrictions:
       Bridges are identified using is_bridge(data). At MMI >= 7.5, bridges face structural inspection
       cautions; at MMI >= 8.5, severe damage risk significantly restricts passability.
    4. Vehicle Rubble Clearance:
       Vehicles possess differing rubble traversing capabilities:
       - Ambulance: Low ground clearance (28 cm), vulnerable to sharp masonry debris.
       - Fire Tender: Medium clearance (50 cm), heavy-duty chassis.
       - Rescue Truck: High clearance (65 cm), heavy 4x4 push capability, debris-clearing resilience.
    """

    hazard_id = "earthquake"
    display_name = "Earthquake Debris Model (Scenario Simulation)"
    description = (
        "Scenario-based simulation modeling ground shaking attenuation, narrow-street masonry debris "
        "blockage, and bridge inspection restrictions in Daraganj. [Simulated Demo Model]"
    )
    is_validated = False

    # Vehicle safe rubble impact limits (0 to 100 index)
    RUBBLE_TOLERANCE: Dict[str, float] = {
        "ambulance": 22.0,      # Sensitive chassis, low clearance
        "fire_tender": 45.0,    # Medium-heavy commercial chassis
        "rescue_truck": 70.0,   # High-clearance disaster response vehicle
    }

    # Road morphology debris vulnerability weights
    HIGHWAY_VULNERABILITY: Dict[str, float] = {
        "residential": 1.0,
        "living_street": 1.0,
        "service": 0.9,
        "unclassified": 0.85,
        "pedestrian": 0.95,
        "footway": 1.0,
        "path": 0.9,
        "tertiary": 0.5,
        "tertiary_link": 0.5,
        "secondary": 0.25,
        "secondary_link": 0.25,
        "primary": 0.12,
        "primary_link": 0.12,
        "trunk": 0.08,
        "trunk_link": 0.08,
    }
    DEFAULT_HIGHWAY_VULNERABILITY: float = 0.6

    def __init__(self, softness_scale: float = 8.0):
        """
        Initialize the Earthquake Hazard Model.

        Args:
            softness_scale: Sigmoid logistic softness parameter for rubble passability.
        """
        self.softness_scale = softness_scale

    def compute_local_mmi(self, epicenter_mmi: float, dist_km: float) -> float:
        """
        Compute effective local Modified Mercalli Intensity using standard attenuation.

        Args:
            epicenter_mmi: Shaking intensity at epicenter (MMI scale, e.g. 5.0 to 9.5).
            dist_km: Distance to epicenter in kilometers (>= 1.0).

        Returns:
            Effective local MMI in [1.0, epicenter_mmi].
        """
        d = max(1.0, float(dist_km))
        # Logarithmic geometric spreading attenuation
        attenuation = 1.6 * math.log10(d / 3.0) if d > 3.0 else 0.0
        return max(1.0, float(epicenter_mmi) - attenuation)

    def evaluate_risk(
        self,
        G: nx.MultiDiGraph,
        vehicle: str,
        intensity_mmi: float = 7.2,
        epicenter_dist_km: float = 12.0,
        debris_vulnerability: float = 1.0,
        **kwargs: Any,
    ) -> nx.MultiDiGraph:
        """
        Evaluate earthquake structural disruption and vehicle passability across all edges.

        Args:
            G: Road network graph.
            vehicle: Vehicle identifier ('ambulance', 'fire_tender', 'rescue_truck').
            intensity_mmi: Epicentral shaking intensity on MMI scale (5.0 to 9.5, default 7.2).
            epicenter_dist_km: Epicenter distance in kilometers (1.0 to 50.0 km, default 12.0 km).
            debris_vulnerability: Masonry debris susceptibility multiplier (0.5 to 2.0, default 1.0).

        Returns:
            Enriched graph with pass_probability and earthquake attributes.
        """
        if vehicle not in VEHICLES:
            raise ValueError(f"Unknown vehicle '{vehicle}'. Must be one of: {list(VEHICLES.keys())}")

        G_copy = G.copy()
        local_mmi = self.compute_local_mmi(intensity_mmi, epicenter_dist_km)
        safe_rubble_limit = self.RUBBLE_TOLERANCE.get(vehicle, 30.0)

        prob_attr_name = f"pass_probability_{vehicle}"

        for u, v, key, data in G_copy.edges(keys=True, data=True):
            # 1. Determine highway morphology weight
            hw_type = data.get("highway", "residential")
            if isinstance(hw_type, list):
                hw_type = hw_type[0]
            hw_type = str(hw_type).lower().strip()

            vuln_weight = self.HIGHWAY_VULNERABILITY.get(hw_type, self.DEFAULT_HIGHWAY_VULNERABILITY)
            vuln_weight *= float(debris_vulnerability)

            # 2. Check bridge status reliably using is_bridge()
            edge_is_bridge = is_bridge(data)

            # 3. Compute disruption / rubble impact score (0 to 100)
            if edge_is_bridge:
                # Bridges: vulnerable to structural displacement rather than street rubble
                if local_mmi < 6.5:
                    disruption_score = 10.0
                    impact_label = "Bridge Operational (Minor Shaking)"
                elif local_mmi < 7.8:
                    # Structural inspection required; caution advisory
                    disruption_score = 45.0
                    impact_label = f"Bridge Caution: Inspection Required (MMI {local_mmi:.1f})"
                else:
                    # Severe shaking: bridge closure / structural damage risk
                    disruption_score = 85.0
                    impact_label = f"Bridge Impassable: High Structural Damage Risk (MMI {local_mmi:.1f})"
            else:
                # Surface streets: debris blockage from adjacent buildings
                if local_mmi <= 5.0:
                    disruption_score = 0.0
                    impact_label = "No Roadway Obstructions"
                else:
                    # Score scales with (local_mmi - 5.0) and highway vulnerability
                    base_rubble = (local_mmi - 5.0) * 22.0
                    disruption_score = max(0.0, min(100.0, base_rubble * vuln_weight))

                    if disruption_score < 25.0:
                        impact_label = "Minor Dust & Debris"
                    elif disruption_score < 55.0:
                        impact_label = f"Moderate Masonry Rubble ({hw_type})"
                    else:
                        impact_label = f"Heavy Structural Blockage ({hw_type})"

            # 4. Logistic sigmoid passability probability
            diff = (disruption_score - safe_rubble_limit) / self.softness_scale
            diff = np.clip(diff, -50.0, 50.0)
            p_val = float(1.0 / (1.0 + np.exp(diff)))
            p_val = max(PROBABILITY_EPSILON, min(1.0, p_val))

            # 5. Populate edge attributes for RoutingEngine compatibility
            # Note: water_depth_cm is 0.0 so hydrodynamic water slowdown does not miscalculate,
            # while the additive log-risk Dijkstra cost handles rubble avoidance smoothly.
            data["water_depth_cm"] = 0.0
            data["rubble_score"] = round(disruption_score, 1)
            data["is_bridge"] = edge_is_bridge
            data["hazard_type"] = self.hazard_id
            data["hazard_severity"] = round(disruption_score, 1)
            data["hazard_label"] = impact_label
            data[prob_attr_name] = p_val
            data["pass_probability"] = p_val
            data["closed"] = bool(p_val < 0.5)

        return G_copy


# Registry of available hazard models
AVAILABLE_HAZARDS: Dict[str, Type[HazardModel]] = {
    "flood": FloodHazardModel,
    "earthquake": EarthquakeHazardModel,
}


def get_hazard_model(hazard_type: str, **kwargs: Any) -> HazardModel:
    """
    Factory function to retrieve and instantiate a configured HazardModel.

    Args:
        hazard_type: Identifier ('flood' or 'earthquake').
        **kwargs: Arguments passed to the model constructor.

    Returns:
        Instantiated HazardModel.
    """
    hazard_clean = str(hazard_type).lower().strip()
    if hazard_clean not in AVAILABLE_HAZARDS:
        raise ValueError(
            f"Unsupported hazard '{hazard_type}'. Implemented hazards: {list(AVAILABLE_HAZARDS.keys())}"
        )
    return AVAILABLE_HAZARDS[hazard_clean](**kwargs)
