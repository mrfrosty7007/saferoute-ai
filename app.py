"""Emergency routing control dashboard. Launch with: streamlit run app.py"""
import streamlit as st
from streamlit_folium import st_folium

from saferoute.regions import get_registry
from services.contracts import RoutingError
from services.service import compute_routes, load_engine
from ui import panels
from ui.map_view import build_map, build_study_area_map
from ui.sidebar import render_sidebar
from ui.styles import inject_css

st.set_page_config(
    page_title="Rakshapath — AI-Assisted Emergency Routing and Disaster Response",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()


ss = st.session_state
ss.setdefault("result", None)
ss.setdefault("result_sig", None)
ss.setdefault("result_request", None)
ss.setdefault("errors", [])

state = render_sidebar()

if state.calculate:
    ss["errors"] = []
    if state.errors:
        ss["errors"] = state.errors
    else:
        try:
            with st.spinner("Calculating modeled multi-hazard routes with Rakshapath"):
                target_region = state.request.region_id if state.request else "daraganj_prayagraj"
                # load_engine uses RegionalEngineManager's bounded LRU. Avoid a
                # second Streamlit resource cache retaining evicted region engines.
                ss["result"] = compute_routes(state.request, load_engine(target_region))
            ss["result_sig"] = state.request.signature()
            ss["result_request"] = state.request
        except RoutingError as exc:
            ss["result"], ss["result_request"], ss["result_sig"] = None, None, None
            ss["errors"] = [str(exc)]

if ss["errors"]:
    status = ("Needs attention", "#e5484d")
elif ss["result"] is None:
    status = ("Awaiting calculation", "#a9bec7")
elif state.request is None or state.request.signature() != ss["result_sig"]:
    status = ("Inputs changed, recalculate", "#e8a317")
else:
    status = ("Routes current", "#3fb96b")

current_reg_id = state.request.region_id if state.request else "daraganj_prayagraj"
reg_meta = get_registry().get_region(current_reg_id)
region_name = reg_meta.display_name if reg_meta else "Daraganj, Prayagraj"
radius_km = int(round(reg_meta.radius_m / 1000.0)) if reg_meta else 2

panels.header(*status, region_name=region_name)
panels.banners(ss["result"], ss["errors"])

result, shown_request = ss["result"], ss["result_request"]
st.write("")
panels.route_cards(result)

left, right = st.columns([2.3, 1], gap="medium")
with left:
    st.markdown('<div class="section">Map</div>', unsafe_allow_html=True)
    if result is None:
        st.markdown(
            f'<div style="font-size: 0.86rem; color: #4a5c66; margin-bottom: 0.4rem;">'
            f'<b>{region_name} Study Area Preview:</b> {radius_km} km operational radius. '
            f'Configure your scenario in the sidebar and select <b>Calculate routes</b>.</div>',
            unsafe_allow_html=True,
        )
        fmap = build_study_area_map(state.request)
        st_folium(
            fmap,
            height=600,
            use_container_width=True,
            returned_objects=[],
            key="preview_map",
        )
    else:
        view = st.radio(
            "Map view",
            ["Routes", "Routes with risk"],
            horizontal=True,
            key="map_view",
            label_visibility="collapsed",
        )
        fmap = build_map(result, shown_request or state.request, show_risk=(view == "Routes with risk"))
        st_folium(
            fmap,
            height=600,
            use_container_width=True,
            returned_objects=[],
            key=f"result_map_{view}",
        )
with right:
    st.markdown('<div class="section">Incident and risk</div>', unsafe_allow_html=True)
    panels.incident_panel(shown_request or state.request)
    panels.insights(result)

panels.elevation_profile(result)
panels.route_table(result)
