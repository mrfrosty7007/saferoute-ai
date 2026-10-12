"""Emergency routing control dashboard. Launch with: streamlit run app.py"""
import dataclasses
from html import escape

import streamlit as st
from streamlit_folium import st_folium

from config import HAZARDS
from services.contracts import Place, RoutingError
from services.service import compute_routes, get_fire_exits, get_nearby, get_recommendation, load_engine
from ui import panels
from ui.extras import render_sos_button
from ui.map_view import add_extras, build_map, build_support_map
from ui.sidebar import render_reference_selector, render_sidebar, render_support_controls
from ui.styles import inject_css, inject_extras_css

# --- Adapters: edit these tuples if the real contracts use other field names ---
ORIGIN_FIELDS = ("origin", "start", "source")
DEST_FIELDS = ("destination", "dest", "end", "target")
SCENARIO_FIELDS = ("hazard", "incident", "scenario", "disaster")
LATLON_FIELDS = (("lat", "lon"), ("lat", "lng"), ("latitude", "longitude"))
SCENARIO_ID_FIELDS = ("key", "id", "type", "kind", "name")


def _first(obj, names):
    for n in names:
        v = obj.get(n) if isinstance(obj, dict) else getattr(obj, n, None)
        if v is not None:
            return n, v
    return None, None


def _point(obj):
    if obj is None:
        return None
    if isinstance(obj, (tuple, list)) and len(obj) >= 2:
        return float(obj[0]), float(obj[1])
    for la, lo in LATLON_FIELDS:
        a, b = _first(obj, (la,))[1], _first(obj, (lo,))[1]
        if a is not None and b is not None:
            return float(a), float(b)
    return None


def request_origin(req):
    return _point(_first(req, ORIGIN_FIELDS)[1]) if req else None


def request_destination(req):
    return _point(_first(req, DEST_FIELDS)[1]) if req else None


def request_scenario(req) -> str:
    if not req:
        return ""
    val = _first(req, SCENARIO_FIELDS)[1]
    if isinstance(val, str):
        return val
    return str(_first(val, SCENARIO_ID_FIELDS)[1] or "") if val is not None else ""


def route_of(result, which):
    return None if result is None else (result.get(which) if isinstance(result, dict) else getattr(result, which, None))


def _set_point(req, fields, point):
    name, _ = _first(req, fields)
    return dataclasses.replace(req, **{name: Place("Fire exit routing point", point[0], point[1])})


def make_route_to_exit(req, engine, start):
    def route_fn(origin, exit_point):
        if req is None:
            raise ValueError("No scenario inputs are available.")
        moved = _set_point(_set_point(req, ORIGIN_FIELDS, origin), DEST_FIELDS, exit_point)
        return route_of(compute_routes(moved, engine), "primary")
    return route_fn


def fire_pick_key(fr):
    return f"fire_pick_{abs(hash((tuple(o.exit.id for o in fr.options), fr.status)))}"


st.set_page_config(page_title="Resilient Emergency Routing", layout="wide", initial_sidebar_state="expanded")
inject_css()
inject_extras_css()
render_sos_button()


@st.cache_resource
def get_engine():
    return load_engine()


ss = st.session_state
for k, v in (("result", None), ("result_sig", None), ("result_request", None), ("errors", []),
             ("nearby_result", None), ("nearby_selected", None), ("fire_result", None), ("route_target", None)):
    ss.setdefault(k, v)

state = render_sidebar()
with st.sidebar:
    st.divider()
    reference = render_reference_selector(state.origin, state.destination)
    controls = render_support_controls()

if state.calculate or ss.pop("auto_calculate", False):  # auto_calculate is set by "Route here"
    ss["errors"] = []
    ss["fire_result"] = None  # exit routes depend on the last inputs
    if state.errors:
        ss["errors"] = state.errors
    else:
        try:
            with st.spinner("Calculating routes"):
                ss["result"] = compute_routes(state.request, get_engine())
            ss["result_sig"] = state.request.signature()
            ss["result_request"] = state.request
        except RoutingError as exc:
            ss["result"], ss["result_request"], ss["result_sig"] = None, None, None
            ss["errors"] = [str(exc)]

if controls["run_nearby"] or ss.pop("nearby_retry", False):
    with st.spinner("Searching nearby support"):
        ss["nearby_result"] = get_nearby(reference, controls["categories"], controls["radius_km"] * 1000)
    ss["nearby_selected"] = None

if controls["run_fire"]:
    start = (reference[0], reference[1]) if reference else request_origin(state.request)
    scenario_key = request_scenario(state.request) or ss.get("hazard", "")
    with st.spinner("Evaluating verified exits"):
        ss["fire_result"] = get_fire_exits(start, scenario_key, make_route_to_exit(state.request, get_engine(), start))

if ss["errors"]:
    status = ("Needs attention", "#e5484d")
elif ss["result"] is None:
    status = ("Awaiting calculation", "#a9bec7")
elif state.request is None or state.request.signature() != ss["result_sig"]:
    status = ("Inputs changed, recalculate", "#e8a317")
else:
    status = ("Routes current", "#3fb96b")

panels.header(*status)
panels.banners(ss["result"], ss["errors"])

result, shown_request = ss["result"], ss["result_request"]
tgt = ss["route_target"]
if result is not None and tgt and shown_request:
    d = shown_request.destination
    if abs(d.lat - tgt["lat"]) < 1e-4 and abs(d.lon - tgt["lon"]) < 1e-4:
        st.markdown(f'<div class="note">Routing to nearby support facility: <b>{escape(tgt["name"])}</b> '
                    f'(OpenStreetMap data, unverified).</div>', unsafe_allow_html=True)
st.write("")
panels.route_cards(result)

nr, fr = ss["nearby_result"], ss["fire_result"]
pick = ss.get(fire_pick_key(fr)) if fr and fr.options else None
extra_sig = (nr.reference if nr else None, len(nr.facilities) if nr else 0, ss["nearby_selected"],
             fr.status if fr else None, fr.selected_exit_id if fr else None, pick)
extra_key = hash(str(extra_sig))

left, right = st.columns([2.3, 1], gap="medium")
with left:
    st.markdown('<div class="section">Map</div>', unsafe_allow_html=True)
    if result is not None:
        view = st.radio("Map view", ["Routes", "Routes with risk"], horizontal=True, key="map_view", label_visibility="collapsed")
        fmap = build_map(result, shown_request, show_risk=(view == "Routes with risk"))
        add_extras(fmap, nr, ss["nearby_selected"], fr, layer_control=True, fire_highlight=pick)
        st_folium(fmap, height=600, use_container_width=True, returned_objects=[],
                  key=f"map_{hash(ss['result_sig'])}_{view}_{extra_key}")
    elif (nr is not None and nr.status == "ok") or (fr is not None and fr.options):
        st_folium(build_support_map(nr, ss["nearby_selected"], fr, pick), height=600, use_container_width=True,
                  returned_objects=[], key=f"supportmap_{extra_key}")
        st.caption("Calculate routes to also see the route comparison on this map.")
    else:
        st.markdown('<div class="panel"><h3>No routes yet</h3><div class="sub">Choose an incident, a vehicle, an origin and a destination in the sidebar, then select Calculate routes. Nearby support results also appear here once you search.</div></div>', unsafe_allow_html=True)
with right:
    st.markdown('<div class="section">Incident and risk</div>', unsafe_allow_html=True)
    panels.incident_panel(shown_request or state.request)
    panels.insights(result)

tab_support, tab_fire = st.tabs(["Nearby Support and AI Route", "Fire Exit"])
with tab_support:
    if result is None:
        st.info("Calculate routes to see a recommendation.")
    else:
        hz = HAZARDS.get(request_scenario(shown_request))
        panels.render_recommendation_card(get_recommendation(
            route_of(result, "primary"), route_of(result, "backup"), route_of(result, "baseline"),
            hazard_label=hz.label if hz else None))
    panels.render_nearby_panel(nr)
with tab_fire:
    if fr and fr.options:
        by_id = {o.exit.id: o for o in fr.options}
        chosen = st.selectbox("Highlight verified exit on map", list(by_id), format_func=lambda i: by_id[i].exit.name,
                              key=fire_pick_key(fr))
        if by_id[chosen].status != "ok":
            st.warning("This exit is not recommended: its route is blocked or could not be found.")
    panels.render_fire_exit_panel(fr)

panels.route_table(result)
