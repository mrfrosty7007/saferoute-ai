from __future__ import annotations

import folium

from config import ROUTE_COLORS, ROUTE_LABELS
from services.contracts import RouteRequest, RouteResult


def risk_color(risk: float) -> str:
    stops = [(0.0, (27, 122, 61)), (0.35, (233, 170, 20)), (0.7, (198, 40, 40)), (1.0, (120, 10, 10))]
    risk = min(1.0, max(0.0, risk))
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if risk <= b:
            t = (risk - a) / (b - a)
            return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(ca, cb))
    return "#780a0a"


def _marker(lat, lon, letter, color, tip):
    html = (f'<div style="width:28px;height:28px;border-radius:50%;background:{color};color:#fff;'
            f'border:3px solid #fff;box-shadow:0 0 0 1px #14232b;font:600 13px IBM Plex Sans,sans-serif;'
            f'display:flex;align-items:center;justify-content:center">{letter}</div>')
    return folium.Marker((lat, lon), tooltip=tip, icon=folium.DivIcon(html=html, icon_size=(28, 28), icon_anchor=(14, 14)))


LEGEND = """
<div style="position:absolute;bottom:22px;left:12px;z-index:9999;background:#fff;border:1px solid #c2cad1;
 border-radius:3px;padding:10px 12px;font:13px 'IBM Plex Sans',sans-serif;color:#14232b;line-height:1.7">
 <div style="font-weight:600;margin-bottom:2px">Routes</div>
 <div><span style="display:inline-block;width:30px;border-top:5px solid #1d5fd1;vertical-align:middle;margin-right:8px"></span>Primary</div>
 <div><span style="display:inline-block;width:30px;border-top:5px dashed #e8820c;vertical-align:middle;margin-right:8px"></span>Backup</div>
 <div><span style="display:inline-block;width:30px;border-top:5px solid #7b8794;vertical-align:middle;margin-right:8px"></span>Conventional baseline</div>
 <div style="font-weight:600;margin:6px 0 2px">Segment pass probability</div>
 <div style="height:8px;width:170px;background:linear-gradient(90deg,#780a0a,#c62828,#e9aa14,#1b7a3d);border-radius:2px"></div>
 <div style="display:flex;justify-content:space-between;width:170px;font-size:11px;color:#5b6b75"><span>0%</span><span>50%</span><span>100%</span></div>
 <div style="font-size:11px;color:#5b6b75;margin-top:4px">Drawn along the routes in the "Routes with risk" view</div>
</div>
"""


def build_map(result: RouteResult, request: RouteRequest, show_risk: bool) -> folium.Map:
    m = folium.Map(tiles="OpenStreetMap", control_scale=True)
    style = {  # baseline first so the primary stays on top where routes overlap
        "baseline": dict(weight=6, opacity=0.75),
        "backup": dict(weight=6, opacity=0.95, dash_array="12 9"),
        "primary": dict(weight=8, opacity=0.95),
    }
    pts = []
    for kind in ("baseline", "backup", "primary"):
        route = getattr(result, kind)
        if route is None:
            continue
        coords = route.all_coords()
        pts += coords
        folium.PolyLine(coords, color=ROUTE_COLORS[kind], tooltip=ROUTE_LABELS[kind], **style[kind]).add_to(m)

    if show_risk:
        for kind in ("baseline", "backup", "primary"):
            route = getattr(result, kind)
            if route is None:
                continue
            for s in route.segments:
                folium.PolyLine(s.coords, color=risk_color(s.risk), weight=3 if kind != "primary" else 4, opacity=1,
                                tooltip=f"{ROUTE_LABELS[kind]}, {s.label}: pass probability {s.pass_probability:.0%}").add_to(m)

    if result.primary:
        w = result.primary.weakest_segment()
        if w and w.risk >= 0.25:
            folium.CircleMarker(w.coords[len(w.coords) // 2], radius=11, color="#c62828", weight=3, fill=True,
                                fill_color="#fff", fill_opacity=1,
                                tooltip=f"Weakest primary segment: pass probability {w.pass_probability:.0%}").add_to(m)

    o, d = request.origin, request.destination
    _marker(o.lat, o.lon, "A", "#0f5c6e", "Origin").add_to(m)
    _marker(d.lat, d.lon, "B", "#14232b", "Destination").add_to(m)
    pts += [(o.lat, o.lon), (d.lat, d.lon)]
    m.fit_bounds([[min(p[0] for p in pts), min(p[1] for p in pts)], [max(p[0] for p in pts), max(p[1] for p in pts)]], padding=(30, 30))
    m.get_root().html.add_child(folium.Element(LEGEND))
    return m
