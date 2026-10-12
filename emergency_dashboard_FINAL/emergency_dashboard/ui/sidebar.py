from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from config import HAZARDS, NEARBY_CATEGORIES, SEVERITIES, VEHICLES
from services.contracts import Place, RouteRequest, validate_request
from services.geocode import GeocodingError, search_places

DEFAULT_ORIGIN = (51.5031, -0.1132)
DEFAULT_DEST = (51.4826, 0.0077)


@dataclass
class SidebarState:
    request: RouteRequest | None
    errors: list
    calculate: bool
    origin: Place | None = None
    destination: Place | None = None


def _cached_search(query: str) -> list:
    return search_places(query)  # caching of non-empty results happens in services.geocode


def _group(title: str) -> None:
    st.markdown(f'<div class="group">{title}</div>', unsafe_allow_html=True)


def _field(title: str) -> None:
    st.markdown(f'<div class="field">{title}</div>', unsafe_allow_html=True)


def _place_picker(title: str, key: str, default: tuple):
    """Returns (Place | None, error | None)."""
    _field(title)
    mode = st.segmented_control(f"{title} input", ["Search place", "Coordinates"], default="Search place",
                                key=f"{key}_mode", label_visibility="collapsed") or "Search place"
    if mode == "Search place":
        q = st.text_input(f"{title} search", key=f"{key}_q", label_visibility="collapsed",
                          placeholder="Country, city, town, village or address").strip()
        if len(q) < 3:
            st.caption("Type at least 3 characters, then press Enter or click outside the box.")
            return None, f"{title}: enter a place name."
        try:
            places = _cached_search(q)
        except GeocodingError as exc:
            st.caption(str(exc))
            return None, f"{title}: {exc}"
        if not places:
            st.caption("No matches. Add the district or country, for example 'Village, District, State, Country'.")
            return None, f"{title}: no match found for '{q}'."
        idx = st.selectbox(f"{title} matches", range(len(places)), key=f"{key}_match::{q.lower()}",
                           format_func=lambda i: places[i].name, label_visibility="collapsed")
        st.caption(f"Selected: {places[idx].lat:.4f}, {places[idx].lon:.4f}")
        return places[idx], None
    st.session_state.setdefault(f"{key}_lat", default[0])
    st.session_state.setdefault(f"{key}_lon", default[1])
    c1, c2 = st.columns(2)
    lat = c1.number_input("Latitude", -90.0, 90.0, format="%.5f", key=f"{key}_lat")
    lon = c2.number_input("Longitude", -180.0, 180.0, format="%.5f", key=f"{key}_lon")
    return Place(f"{lat:.4f}, {lon:.4f}", lat, lon), None


def render_sidebar() -> SidebarState:
    errors = []
    with st.sidebar:
        st.markdown('<div class="side-title">Scenario controls</div>'
                    '<div class="side-sub">Set the incident, the vehicle and the trip, then calculate.</div>',
                    unsafe_allow_html=True)

        _group("Incident")
        hazard_key = st.selectbox("Hazard type", list(HAZARDS), format_func=lambda k: HAZARDS[k].label, key="hazard")
        hz = HAZARDS[hazard_key]
        st.caption(hz.note)
        params = {}
        for p in hz.params:
            fmt = "%d" if float(p.step).is_integer() else "%.1f"
            params[p.key] = st.slider(f"{p.label} ({p.unit})", float(p.min), float(p.max), float(p.default),
                                      float(p.step), format=fmt, key=f"p_{hz.key}_{p.key}")
        severity = st.select_slider("Severity", options=list(SEVERITIES), value="High", key="severity")

        _group("Vehicle")
        vehicle = st.radio("Vehicle", list(VEHICLES), format_func=lambda k: VEHICLES[k].label,
                           key="vehicle", label_visibility="collapsed")
        st.caption(VEHICLES[vehicle].note)

        _group("Trip")
        origin, e1 = _place_picker("Origin", "origin", DEFAULT_ORIGIN)
        destination, e2 = _place_picker("Destination", "dest", DEFAULT_DEST)
        errors += [e for e in (e1, e2) if e]

        st.write("")
        clicked = st.button("Calculate routes", type="primary", use_container_width=True, key="calculate")

    request = None
    if origin and destination:
        request = RouteRequest(origin, destination, vehicle, hazard_key, params, severity)
        errors += validate_request(request)
    return SidebarState(request, errors, clicked, origin, destination)


# --- SafeRoute Extras controls (rendered below the existing sidebar controls) ---
try:
    from streamlit_geolocation import streamlit_geolocation
except Exception:  # optional dependency
    streamlit_geolocation = None


def render_reference_selector(origin, destination):
    """Reference point for nearby support and fire exits. Returns (lat, lon, label) or None."""
    _group("Reference point")
    options = ["Route origin", "Route destination / incident", "Custom coordinates"]
    if streamlit_geolocation is not None:
        options.append("My device location")
    choice = st.radio("Reference point", options, key="ref_choice", label_visibility="collapsed")
    if choice in ("Route origin", "Route destination / incident"):
        place = origin if choice == "Route origin" else destination
        if place is None:
            st.caption("This point is not set yet.")
            return None
        return place.lat, place.lon, place.name
    if choice == "Custom coordinates":
        c1, c2 = st.columns(2)
        lat = c1.number_input("Latitude", -90.0, 90.0, value=None, format="%.5f", key="ref_lat")
        lon = c2.number_input("Longitude", -180.0, 180.0, value=None, format="%.5f", key="ref_lon")
        if lat is None or lon is None:
            st.caption("Enter both latitude and longitude.")
            return None
        return lat, lon, f"{lat:.4f}, {lon:.4f}"
    loc = streamlit_geolocation() or {}
    lat, lon = loc.get("latitude"), loc.get("longitude")
    if lat is None or lon is None:
        st.caption("Device location is unavailable or permission was denied.")
        return None
    return lat, lon, "Device location"


def render_support_controls() -> dict:
    _group("Support and exits")
    cats = st.multiselect("Support categories", list(NEARBY_CATEGORIES), default=list(NEARBY_CATEGORIES),
                          format_func=lambda k: NEARBY_CATEGORIES[k]["label"], key="support_categories")
    radius_km = st.slider("Search radius (km)", 1, 25, 5, key="support_radius")
    run_nearby = st.button("Find nearby support", key="run_nearby", use_container_width=True)
    run_fire = st.button("Find fire exit routes", key="run_fire", use_container_width=True)
    return {"categories": cats, "radius_km": radius_km, "run_nearby": run_nearby, "run_fire": run_fire}
