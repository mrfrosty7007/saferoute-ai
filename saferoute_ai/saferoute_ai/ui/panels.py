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
