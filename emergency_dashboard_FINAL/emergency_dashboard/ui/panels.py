from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from config import HAZARDS, ROUTE_COLORS, ROUTE_LABELS, VEHICLES, hazard_intensity
from services.contracts import HIGH_RISK_THRESHOLD, RouteRequest, RouteResult


def _rel_color(r: float) -> str:
    return "#1b7a3d" if r >= 0.8 else "#d68a00" if r >= 0.6 else "#c62828"


def header(status_text: str, status_color: str) -> None:
    st.markdown(
        '<div class="hdr"><div><h1>Resilient Emergency Routing</h1>'
        '<p>Compare the primary, backup and conventional routes for emergency vehicles under a live hazard scenario, anywhere in the world.</p></div>'
        f'<div class="status"><div class="lbl">Scenario status</div>'
        f'<div class="val"><span class="dot" style="background:{status_color}"></span>{escape(status_text)}</div></div></div>',
        unsafe_allow_html=True)


def banners(result: RouteResult | None, errors: list | None) -> None:
    if errors:
        items = "<br>".join(escape(e) for e in errors)
        st.markdown(f'<div class="err"><b>Routes were not calculated.</b><br>{items}</div>', unsafe_allow_html=True)
    if result is None:
        return
    if result.simulated:
        st.markdown(f'<div class="sim"><b>Simulated data.</b> Risk, reliability and ETA values come from a mock engine, not the routing engine. {escape(result.source)}.</div>',
                    unsafe_allow_html=True)
    for n in result.notes:
        st.markdown(f'<div class="note">{escape(n)}</div>', unsafe_allow_html=True)


def route_cards(result: RouteResult | None) -> None:
    tags = {"primary": "Recommended", "backup": "Alternate", "baseline": "Reference"}
    for col, kind in zip(st.columns(3), ("primary", "backup", "baseline")):
        route = getattr(result, kind) if result else None
        if route is None:
            msg = ("Calculate routes to see results." if result is None else
                   "No backup route exists for this pair." if kind == "backup" else "Not available.")
            col.markdown(f'<div class="rc"><div class="top"><span class="name">{ROUTE_LABELS[kind]}</span></div>'
                         f'<div class="msg">{msg}</div></div>', unsafe_allow_html=True)
            continue
        rc = _rel_color(route.reliability)
        col.markdown(
            f'<div class="rc" style="--accent:{ROUTE_COLORS[kind]}"><div class="top"><span class="name">{ROUTE_LABELS[kind]}</span>'
            f'<span class="tag">{tags[kind]}</span></div>'
            f'<div class="eta">{route.eta_min:.0f}<small>min</small></div>'
            f'<div class="kv"><span>Distance</span><b>{route.distance_km:.1f} km</b></div>'
            f'<div class="kv"><span>Reliability</span><b>{route.reliability:.0%}</b></div>'
            f'<div class="bar"><i style="width:{route.reliability * 100:.0f}%;background:{rc}"></i></div></div>',
            unsafe_allow_html=True)


def _panel(title: str, body: str) -> None:
    st.markdown(f'<div class="panel"><h3>{title}</h3>{body}</div>', unsafe_allow_html=True)


def insights(result: RouteResult | None) -> None:
    pending = '<div class="sub">Available after calculation.</div>'

    body = pending
    if result and result.primary:
        w = result.primary.weakest_segment()
        if w:
            lat, lon = w.coords[len(w.coords) // 2]
            cls = "bad" if w.risk >= HIGH_RISK_THRESHOLD else "warn" if w.risk >= 0.35 else "ok"
            body = (f'<div class="big {cls}">{w.pass_probability:.0%} pass probability</div>'
                    f'<div class="sub">{escape(w.label)} on the primary route, near {lat:.4f}, {lon:.4f}</div>')
    _panel("Weakest road segment", body)

    body = pending
    if result and result.baseline:
        n, total = result.baseline.high_risk_count(), len(result.baseline.segments)
        if n:
            body = (f'<div class="big bad">{n} high-risk segment{"s" if n != 1 else ""}</div>'
                    f'<div class="sub">{n} of {total} baseline segments have risk of {HIGH_RISK_THRESHOLD:.0%} or more.</div>')
        else:
            body = f'<div class="big ok">No high-risk segments</div><div class="sub">All {total} baseline segments are below {HIGH_RISK_THRESHOLD:.0%} risk.</div>'
    _panel("Conventional baseline risk", body)

    body = pending
    if result and result.backup is None:
        body = '<div class="sub">There is no backup route to compare.</div>'
    elif result and result.overlap_pct is not None:
        pct = result.overlap_pct
        cls = "bad" if pct >= 70 else "warn" if pct >= 40 else "ok"
        note = ("Backup depends heavily on the primary roads." if pct >= 70 else
                "Backup is largely independent of the primary route." if pct < 40 else
                "Backup shares part of the primary route.")
        body = f'<div class="big {cls}">{pct:.0f}% shared</div><div class="sub">{note}</div>'
    _panel("Backup overlap with primary", body)


def incident_panel(request: RouteRequest | None) -> None:
    if request is None:
        _panel("Incident", '<div class="sub">Complete the origin and destination to define a scenario.</div>')
        return
    hz = HAZARDS[request.hazard]
    rows = [("Hazard", hz.label), ("Severity", request.severity), ("Vehicle", VEHICLES[request.vehicle].label)]
    for p in hz.params:
        rows.append((p.label, f"{request.params.get(p.key, p.default):g} {p.unit}"))
    rows += [("Combined intensity", f"{hazard_intensity(request.hazard, request.params):.0%}"),
             ("Origin", request.origin.name), ("Destination", request.destination.name)]
    _panel("Incident", "".join(f'<div class="kv"><span>{escape(k)}</span><b>{escape(str(v))}</b></div>' for k, v in rows))


def route_table(result: RouteResult | None) -> None:
    st.markdown('<div class="section">Route information</div>', unsafe_allow_html=True)
    if result is None:
        st.caption("Route details appear here after you calculate.")
        return
    rows = []
    for kind, r in result.routes():
        row = {"Route": ROUTE_LABELS[kind], "ETA (min)": None, "Distance (km)": None, "Reliability": None,
               "Weakest pass probability": None, "High-risk segments": None, "Segments": None}
        if r is not None:
            w = r.weakest_segment()
            row.update({"ETA (min)": r.eta_min, "Distance (km)": r.distance_km, "Reliability": r.reliability,
                        "Weakest pass probability": w.pass_probability if w else None,
                        "High-risk segments": r.high_risk_count(), "Segments": len(r.segments)})
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True, column_config={
        "ETA (min)": st.column_config.NumberColumn(format="%.1f"),
        "Distance (km)": st.column_config.NumberColumn(format="%.2f"),
        "Reliability": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
        "Weakest pass probability": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
    })


# ---------------------------------------------------------------------------
# SafeRoute Extras panels
# ---------------------------------------------------------------------------
from services.nearby import directions_url  # noqa: E402
from services.recommendation import DISCLAIMER  # noqa: E402
from config import NEARBY_CATEGORIES  # noqa: E402


def _esc(v) -> str:
    return escape("" if v is None else str(v))


def _missing(v) -> str:
    return _esc(v) if v not in (None, "") else "Not listed"


def _chip(text, tone="muted") -> str:
    return f'<span class="sr-chip sr-chip--{tone}">{_esc(text)}</span>'


def _select_facility(fid, name) -> None:
    st.session_state["nearby_selected"] = fid
    st.toast(f"Highlighted on the map: {name}")


def _route_to_facility(fac) -> None:
    """Make the facility the route destination and recalculate with the existing engine."""
    ss = st.session_state
    ss["dest_mode"] = "Coordinates"
    ss["dest_lat"], ss["dest_lon"] = fac.lat, fac.lon
    ss["route_target"] = {"name": fac.name or "Unnamed facility", "lat": fac.lat, "lon": fac.lon}
    ss["nearby_selected"] = fac.id
    ss["auto_calculate"] = True


def render_nearby_panel(result) -> None:
    if result is None:
        st.info("Choose a reference point and select Find nearby support.")
        return
    if result.status == "no_location":
        st.warning(result.message)
        return
    if result.status == "unavailable":
        st.warning(result.message)
        st.caption("Integration needed: outbound access to an Overpass server, or another verified facility data source.")
        st.button("Retry search", key="retry_nearby", on_click=st.session_state.__setitem__, args=("nearby_retry", True))
        return
    if result.status == "empty":
        st.info(result.message)
        return
    st.caption(result.message)
    st.caption("Route here calculates routes inside this app. External map opens another app and is not hazard-aware.")
    for fac in result.facilities:
        cat = NEARBY_CATEGORIES.get(fac.category, {}).get("label", fac.category)
        with st.container(border=True):
            st.markdown(
                f'<div class="sr-name">{_esc(fac.name) if fac.name else "Unnamed facility"}</div>'
                f'{_chip(cat, "ok")}{_chip(f"{fac.distance_m / 1000:.2f} km straight line")}{_chip(f"{fac.source}, unverified", "muted")}'
                f'<div class="sr-line">Address: {_missing(fac.address)}</div>'
                f'<div class="sr-line">Phone: {_missing(fac.phone)}</div>'
                f'<div class="sr-line">Hours: {_missing(fac.opening_hours)}</div>',
                unsafe_allow_html=True)
            b1, b2, b3 = st.columns(3)
            b1.button("Show on map", key=f"showmap_{fac.id}", on_click=_select_facility,
                      args=(fac.id, fac.name or "Unnamed facility"), use_container_width=True)
            b2.button("Route here", key=f"routehere_{fac.id}", on_click=_route_to_facility, args=(fac,),
                      type="primary", use_container_width=True,
                      help="Calculates hazard-aware routes from your origin to this facility, inside this app.")
            b3.link_button("External map", directions_url(result.reference, fac), use_container_width=True)
    st.caption(result.attribution)


def render_recommendation_card(rec) -> None:
    label = ("Rule-based recommendation" if rec.mode == "rule_based"
             else "Rule-based choice, model-written explanation")
    with st.container(border=True):
        st.markdown(_chip(label, "ok" if rec.recommended_route else "warn"), unsafe_allow_html=True)
        st.markdown(f"**{rec.headline}**")
        st.write(rec.explanation)
        with st.expander("Inspect supporting factors"):
            if rec.factors:
                st.dataframe(pd.DataFrame(list(rec.factors)), hide_index=True, use_container_width=True)
            for lim in rec.limitations:
                st.markdown(f"- {lim}")
        st.caption(DISCLAIMER)


def render_fire_exit_panel(result) -> None:
    if result is None:
        st.info("Choose a reference point and select Find fire exit routes.")
        return
    if result.status == "no_data":
        st.warning(result.message)
        st.markdown("**Setup required**\n"
                    "- A verified exits file with named sources (`data/fire_exits.geojson`)\n"
                    "- Indoor-network or floor-plan data, if indoor routing is needed\n"
                    "- A fire scenario in the routing engine")
        if result.unverified_count:
            st.caption(f"{result.unverified_count} unverified or malformed record(s) were ignored.")
        return
    if result.status in ("no_fire_scenario", "no_location"):
        st.info(result.message)
        return
    {"ok": st.success, "blocked": st.error}.get(result.status, st.warning)(result.message)
    st.caption("Exits are ranked by blocked segments, then risk, then travel time. The first exit is not guaranteed to be the safest.")
    tone = {"ok": ("Route found", "ok"), "blocked": ("Crosses blocked segment", "warn"), "unreachable": ("No route found", "muted")}
    for opt in result.options:
        text, t = tone[opt.status]
        blocked = "not reported" if opt.blocked is None else str(opt.blocked)
        with st.container(border=True):
            body = (f'<div class="sr-name">{_esc(opt.exit.name)}</div>{_chip("Verified exit", "ok")}{_chip(text, t)}')
            if opt.status != "unreachable":
                body += (f'<div class="sr-line">Time: {_missing(None if opt.time_min is None else f"{opt.time_min:.1f} min")}'
                         f' | Distance: {_missing(None if opt.distance_km is None else f"{opt.distance_km:.2f} km")}'
                         f' | Risk: {_missing(None if opt.risk is None else f"{opt.risk:.2f}")}'
                         f' | Blocked segments: {blocked}</div>')
            body += (f'<div class="sr-line">Source: {_esc(opt.exit.source)}</div>'
                     f'<div class="sr-line">Last verified: {_missing(opt.exit.last_verified)}</div>')
            if opt.status == "blocked":
                body += '<div class="sr-line">This route crosses a known blocked segment and is not recommended.</div>'
            if opt.status == "unreachable":
                body += '<div class="sr-line">No route was found to this exit with the available map data.</div>'
            st.markdown(body, unsafe_allow_html=True)
    for n in result.notes:
        st.caption(n)
    if result.unverified_count:
        st.caption(f"{result.unverified_count} unverified or malformed record(s) were ignored.")
