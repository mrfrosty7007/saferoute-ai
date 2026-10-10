"""
SafeRouteAI - Sidebar Controls Component
Author: SafeRouteAI Team (Preserving Teammate Sidebar Layout)

Controls incident definition, hazard parameters, vehicle selection,
and verified origin/destination input within Daraganj, Prayagraj.
"""
from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from config import (
    DARAGANJ_LANDMARKS,
    DEFAULT_DEST,
    DEFAULT_ORIGIN,
    HAZARDS,
    SEVERITIES,
    STUDY_AREA_NAME,
    VEHICLES,
)
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


def _place_picker(title: str, key: str, default: tuple) -> tuple[Place | None, str | None]:
    """Returns (Place | None, error | None)."""
    _field(title)
    mode = st.radio(
        f"{title} input",
        ["Daraganj Landmarks", "Coordinates", "Search place"],
        key=f"{key}_mode",
        horizontal=True,
        label_visibility="collapsed",
    )

    if mode == "Daraganj Landmarks":
        landmark_names = list(DARAGANJ_LANDMARKS.keys())
        default_idx = 0 if "origin" in key else 1
        widget_key = f"{key}_landmark"
        idx = None if widget_key in st.session_state else default_idx
        selected_name = st.selectbox(
            f"{title} landmark",
            landmark_names,
            index=idx,
            key=widget_key,
            label_visibility="collapsed",
        )
        lat, lon = DARAGANJ_LANDMARKS[selected_name]
        return Place(selected_name, lat, lon), None

    elif mode == "Search place":
        q = st.text_input(
            f"{title} search",
            key=f"{key}_q",
            label_visibility="collapsed",
            placeholder=f"Landmark or street in {STUDY_AREA_NAME}",
        ).strip()
        if len(q) < 3:
            st.caption("Type at least 3 characters and press Enter.")
            return None, f"{title}: enter a place name in Daraganj."
        try:
            places = _cached_search(q)
        except GeocodingError as exc:
            st.caption(str(exc))
            return None, f"{title}: {exc}"
        if not places:
            st.caption("No matches found. Try selecting from Daraganj Landmarks.")
            return None, f"{title}: no match found for '{q}' in Daraganj."
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


def _reset_to_benchmark() -> None:
    landmarks = list(DARAGANJ_LANDMARKS.keys())
    st.session_state["origin_landmark"] = landmarks[0]
    st.session_state["dest_landmark"] = landmarks[1]
    st.session_state["origin_mode"] = "Daraganj Landmarks"
    st.session_state["dest_mode"] = "Daraganj Landmarks"
    st.session_state["origin_lat"] = DEFAULT_ORIGIN[0]
    st.session_state["origin_lon"] = DEFAULT_ORIGIN[1]
    st.session_state["dest_lat"] = DEFAULT_DEST[0]
    st.session_state["dest_lon"] = DEFAULT_DEST[1]
    st.session_state["result"] = None
    st.session_state["result_sig"] = None
    st.session_state["result_request"] = None


def render_sidebar() -> SidebarState:
    errors = []
    with st.sidebar:
        st.markdown(
            '<div class="side-title">Scenario controls</div>'
            f'<div class="side-sub">Set the incident, vehicle, and trip in {STUDY_AREA_NAME}.</div>',
            unsafe_allow_html=True,
        )

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
        severity = st.select_slider("Severity", options=list(SEVERITIES), value="Moderate", key="severity")

        _group("Vehicle")
        vehicle = st.radio(
            "Vehicle",
            list(VEHICLES),
            format_func=lambda k: VEHICLES[k].label,
            key="vehicle",
            label_visibility="collapsed",
        )
        st.caption(VEHICLES[vehicle].note)

        _group("Trip")
        origin, e1 = _place_picker("Origin", "origin", DEFAULT_ORIGIN)
        destination, e2 = _place_picker("Destination", "dest", DEFAULT_DEST)
        errors += [e for e in (e1, e2) if e]

        clicked = st.button("Calculate routes", type="primary", use_container_width=True)
        st.button("Reset to benchmark pair", on_click=_reset_to_benchmark, use_container_width=True)

    request = None
    if origin and destination:
        request = RouteRequest(origin, destination, vehicle, hazard_key, params, severity)
        errors += validate_request(request)
    return SidebarState(request, errors, clicked)
