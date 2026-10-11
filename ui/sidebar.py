"""
Rakshapath - Sidebar Controls Component
Author: Rakshapath Team (Preserving Teammate Sidebar Layout)

Controls nationwide location hierarchy, incident definition, hazard parameters,
vehicle selection, and verified origin/destination input.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import MutableMapping, Optional

import streamlit as st

from config import (
    DARAGANJ_LANDMARKS,
    DEFAULT_DEST,
    DEFAULT_ORIGIN,
    HAZARDS,
    SEVERITIES,
    VEHICLES,
)
from saferoute.regions import DEFAULT_REGION_ID, RegionMetadata, RegionStatus, registry
from services.contracts import Place, RouteRequest, validate_request
from services.geocode import GeocodingError, search_places


@dataclass
class SidebarState:
    request: RouteRequest | None
    errors: list
    calculate: bool


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_search(query: str) -> list:
    return search_places(query)


def _group(title: str) -> None:
    st.markdown(f'<div class="group">{title}</div>', unsafe_allow_html=True)


def _field(title: str) -> None:
    st.markdown(f'<div class="field">{title}</div>', unsafe_allow_html=True)


def _place_picker(
    title: str,
    key: str,
    default: tuple,
    region: Optional[RegionMetadata] = None,
) -> tuple[Place | None, str | None]:
    """Returns (Place | None, error | None)."""
    reg = region or registry.get_or_default(DEFAULT_REGION_ID)
    _field(title)

    # Use 'Daraganj Landmarks' for Daraganj to preserve backward compatibility, or city landmarks for others
    landmark_label = "Daraganj Landmarks" if reg.region_id == DEFAULT_REGION_ID else f"{reg.city} Landmarks"
    mode = st.radio(
        f"{title} input",
        [landmark_label, "Coordinates", "Search place"],
        key=f"{key}_mode",
        horizontal=True,
        label_visibility="collapsed",
    )

    if mode == landmark_label:
        landmarks_dict = reg.landmarks if reg.landmarks else DARAGANJ_LANDMARKS
        landmark_names = list(landmarks_dict.keys())
        default_idx = 0 if "origin" in key else (1 if len(landmark_names) > 1 else 0)
        widget_key = f"{key}_landmark"

        # Keep widget state as the source of selection to avoid Streamlit's
        # warning when a key set by a callback is combined with an index default.
        if widget_key in st.session_state and st.session_state[widget_key] in landmark_names:
            pass
        else:
            st.session_state[widget_key] = landmark_names[default_idx]

        selected_name = st.selectbox(
            f"{title} landmark",
            landmark_names,
            key=widget_key,
            label_visibility="collapsed",
        )

        # Validate selection before indexing landmarks_dict
        if selected_name and selected_name in landmarks_dict:
            lat, lon = landmarks_dict[selected_name]
            return Place(selected_name, lat, lon), None
        else:
            # Safe fallback to benchmark default if selection is empty, None, or invalid
            fallback_name = landmark_names[default_idx]
            lat, lon = landmarks_dict[fallback_name]
            st.session_state[widget_key] = fallback_name
            return Place(fallback_name, lat, lon), None

    elif mode == "Search place":
        search_scope = f"{reg.city}, {reg.state}"
        q = st.text_input(
            f"{title} search",
            key=f"{key}_q",
            label_visibility="collapsed",
            placeholder=f"Landmark or street in {search_scope}",
        ).strip()
        if len(q) < 3:
            st.caption("Type at least 3 characters and press Enter.")
            return None, f"{title}: enter a place name in {reg.city}."
        try:
            places = _cached_search(f"{q}, {search_scope}, India")
            if not places:
                places = _cached_search(q)
        except GeocodingError as exc:
            st.caption(str(exc))
            return None, f"{title}: {exc}"
        if not places:
            st.caption(f"No matches found. Try selecting from {landmark_label}.")
            return None, f"{title}: no match found for '{q}' in {reg.city}."
        idx = st.selectbox(
            f"{title} matches",
            range(len(places)),
            key=f"{key}_match::{q.lower()}",
            format_func=lambda i: places[i].name,
            label_visibility="collapsed",
        )
        return places[idx], None

    else:
        c1, c2 = st.columns(2)
        lat = c1.number_input("Latitude", -90.0, 90.0, default[0], format="%.5f", key=f"{key}_lat")
        lon = c2.number_input("Longitude", -180.0, 180.0, default[1], format="%.5f", key=f"{key}_lon")
        return Place(f"{lat:.4f}, {lon:.4f}", lat, lon), None


def _on_region_change() -> None:
    """Callback when region is changed in sidebar: sync coordinates before widget creation."""
    rid = st.session_state.get("region_id")
    r = registry.get(rid)
    if r:
        st.session_state["origin_lat"] = r.default_origin[0]
        st.session_state["origin_lon"] = r.default_origin[1]
        st.session_state["dest_lat"] = r.default_dest[0]
        st.session_state["dest_lon"] = r.default_dest[1]
        if r.landmarks:
            l_names = list(r.landmarks.keys())
            st.session_state["origin_landmark"] = l_names[0]
            st.session_state["dest_landmark"] = l_names[1] if len(l_names) > 1 else l_names[0]


def _on_state_change() -> None:
    """Select the first configured district and region for the new state."""
    districts = registry.list_districts(st.session_state.get("region_state", ""))
    if not districts:
        return
    st.session_state["region_district"] = districts[0]
    _on_district_change()


def _on_district_change() -> None:
    """Select a configured region in the current state/district before rerender."""
    regions = registry.list_regions_for_district(
        st.session_state.get("region_state", ""),
        st.session_state.get("region_district", ""),
    )
    if regions:
        st.session_state["region_id"] = regions[0].region_id
        _on_region_change()


def reset_benchmark_state(session_state: MutableMapping) -> None:
    """Reset region, trip widgets, calculated results, and stale errors."""
    landmarks = list(DARAGANJ_LANDMARKS)
    session_state["region_state"] = "Uttar Pradesh"
    session_state["region_district"] = "Prayagraj"
    session_state["region_id"] = DEFAULT_REGION_ID
    session_state["_last_selected_region"] = DEFAULT_REGION_ID
    session_state["origin_landmark"] = landmarks[0]
    session_state["dest_landmark"] = landmarks[1]
    session_state["origin_mode"] = "Daraganj Landmarks"
    session_state["dest_mode"] = "Daraganj Landmarks"
    session_state["origin_lat"], session_state["origin_lon"] = DEFAULT_ORIGIN
    session_state["dest_lat"], session_state["dest_lon"] = DEFAULT_DEST
    session_state["result"] = None
    session_state["result_sig"] = None
    session_state["result_request"] = None
    session_state["errors"] = []


def _reset_to_benchmark() -> None:
    reset_benchmark_state(st.session_state)


def render_sidebar() -> SidebarState:
    errors = []
    # Resolve the active region before rendering the dynamic sidebar heading.
    current_reg_id = st.session_state.get("region_id", DEFAULT_REGION_ID)
    active_region = registry.get_or_default(current_reg_id)
    with st.sidebar:
        st.markdown(
            '<div class="side-title">Scenario controls</div>'
            f'<div class="side-sub">Set the incident, vehicle, and trip in {active_region.display_name}.</div>',
            unsafe_allow_html=True,
        )

        # ----------------------------------------------------------------------
        # Determine active region (defaults to Daraganj, Prayagraj baseline)
        # ----------------------------------------------------------------------
        # ======================================================================
        # 1. Incident & Hazard Scenario (selectbox[0], sliders)
        # ======================================================================
        _group("Incident")
        hazard_key = st.selectbox("Hazard type", list(HAZARDS), format_func=lambda k: HAZARDS[k].label, key="hazard")
        hz = HAZARDS[hazard_key]
        st.caption(hz.note)
        params = {}
        for p in hz.params:
            fmt = "%d" if float(p.step).is_integer() else "%.1f"
            params[p.key] = st.slider(
                f"{p.label} ({p.unit})",
                float(p.min),
                float(p.max),
                float(p.default),
                float(p.step),
                format=fmt,
                key=f"p_{hz.key}_{p.key}",
            )
        severity = st.select_slider("Incident classification", options=list(SEVERITIES), value="Moderate", key="severity")
        st.caption("Classification only; the numeric hazard controls above drive the model inputs.")

        # ======================================================================
        # 2. Emergency Vehicle Choice (radio[0])
        # ======================================================================
        _group("Vehicle")
        vehicle = st.radio(
            "Vehicle",
            list(VEHICLES),
            format_func=lambda k: VEHICLES[k].label,
            key="vehicle",
            label_visibility="collapsed",
        )
        st.caption(VEHICLES[vehicle].note)

        # ======================================================================
        # 3. Trip Origin & Destination (radio[1], selectbox[1], radio[2], selectbox[2])
        # ======================================================================
        _group("Trip")
        origin, e1 = _place_picker(
            "Origin", "origin", active_region.default_origin, region=active_region
        )
        destination, e2 = _place_picker(
            "Destination", "dest", active_region.default_dest, region=active_region
        )
        errors += [e for e in (e1, e2) if e]

        # ======================================================================
        # 4. Location & Regional Hierarchy Selection (selectbox[3], [4], [5])
        # ======================================================================
        _group("Regional Study Area (India-wide)")

        states = registry.list_states()
        default_state_idx = states.index(active_region.state) if active_region.state in states else 0
        if st.session_state.get("region_state") not in states:
            st.session_state["region_state"] = states[default_state_idx]
        selected_state = st.selectbox(
            "State / UT",
            states,
            key="region_state",
            on_change=_on_state_change,
        )

        districts = registry.list_districts(selected_state)
        default_dist_idx = districts.index(active_region.district) if active_region.district in districts else 0
        if districts and st.session_state.get("region_district") not in districts:
            st.session_state["region_district"] = districts[default_dist_idx]
        selected_district = st.selectbox(
            "District",
            districts,
            key="region_district",
            on_change=_on_district_change,
        )

        regions = registry.list_regions_for_district(selected_state, selected_district)
        if not regions:
            selected_region = registry.get_or_default(DEFAULT_REGION_ID)
            st.caption(f"No specific study areas configured for {selected_district}.")
        else:
            region_ids = [r.region_id for r in regions]
            def _fmt_reg_id(rid: str) -> str:
                r = registry.get(rid)
                if not r:
                    return rid
                tag = "Supported" if r.is_routable else r.status.value.title()
                return f"{r.display_name} ({tag})"

            default_reg_idx = region_ids.index(active_region.region_id) if active_region.region_id in region_ids else 0
            if st.session_state.get("region_id") not in region_ids:
                st.session_state["region_id"] = region_ids[default_reg_idx]
            selected_reg_id = st.selectbox(
                "Routing Region",
                region_ids,
                format_func=_fmt_reg_id,
                key="region_id",
                on_change=_on_region_change,
            )
            selected_region = registry.get_or_default(selected_reg_id)

        # Region status indicator
        if selected_region.is_routable:
            st.caption(f"Status: **{selected_region.status_description}**")
        else:
            st.warning(
                f"Status: **{selected_region.status.value.upper()}** — {selected_region.status_description}"
            )

        clicked = st.button("Calculate routes", type="primary", use_container_width=True)
        st.button("Reset to benchmark pair", on_click=_reset_to_benchmark, use_container_width=True)

    request = None
    if origin and destination:
        request = RouteRequest(
            origin=origin,
            destination=destination,
            vehicle=vehicle,
            hazard=hazard_key,
            params=params,
            severity=severity,
            region_id=selected_region.region_id,
        )
        errors += validate_request(request)
    return SidebarState(request, errors, clicked)
