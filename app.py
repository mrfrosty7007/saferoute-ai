"""Emergency routing control dashboard. Launch with: streamlit run app.py"""
import streamlit as st
from streamlit_folium import st_folium

from services.contracts import RoutingError
from services.service import compute_routes, load_engine
from ui import panels
from ui.map_view import build_map, build_study_area_map
from ui.sidebar import render_sidebar
from ui.styles import inject_css

st.set_page_config(
    page_title="SafeRouteAI — Resilient Emergency Routing",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()


@st.cache_resource(show_spinner="Loading SafeRouteAI routing engine and road network...")
def get_engine():
    return load_engine()


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
            with st.spinner("Calculating real multi-hazard routes with SafeRouteAI"):
                ss["result"] = compute_routes(state.request, get_engine())
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

panels.header(*status)
panels.banners(ss["result"], ss["errors"])

result, shown_request = ss["result"], ss["result_request"]
st.write("")
panels.route_cards(result)

left, right = st.columns([2.3, 1], gap="medium")
with left:
    st.markdown('<div class="section">Map</div>', unsafe_allow_html=True)
    if result is None:
        st.markdown(
            '<div style="font-size: 0.86rem; color: #4a5c66; margin-bottom: 0.4rem;">'
            '<b>Daraganj Study Area Preview:</b> 2 km operational radius in Prayagraj. '
            'Configure your scenario in the sidebar and select <b>Calculate routes</b>.</div>',
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

panels.route_table(result)
