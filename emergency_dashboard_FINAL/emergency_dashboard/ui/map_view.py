from __future__ import annotations

import folium
from branca.element import MacroElement
from jinja2 import Template

from config import ROUTE_COLORS, ROUTE_LABELS
from services.contracts import HIGH_RISK_THRESHOLD, RouteRequest, RouteResult


def risk_color(risk: float) -> str:
    stops = [(0.0, (27, 122, 61)), (0.35, (233, 170, 20)), (0.7, (198, 40, 40)), (1.0, (120, 10, 10))]
    risk = min(1.0, max(0.0, risk))
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if risk <= b:
            t = (risk - a) / (b - a)
            return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(ca, cb))
    return "#780a0a"


def _marker(lat, lon, color, tip):
    """Google-Maps-style dot: filled circle, white border, soft outer ring."""
    html = (f'<div style="width:22px;height:22px;border-radius:50%;background:{color};border:3px solid #fff;'
            f'box-shadow:0 0 0 1px rgba(0,0,0,.35),0 1px 5px rgba(0,0,0,.45)"></div>')
    return folium.Marker((lat, lon), tooltip=tip, icon=folium.DivIcon(html=html, icon_size=(22, 22), icon_anchor=(11, 11)))


class _HideLeafletPrefix(MacroElement):
    """Removes the 'Leaflet' prefix. The OpenStreetMap credit is required by its licence and stays."""
    _template = Template("{% macro script(this, kwargs) %}"
                         "{{ this._parent.get_name() }}.attributionControl.setPrefix(false);"
                         "{% endmacro %}")


LEGEND = """
<div style="position:absolute;bottom:22px;left:12px;z-index:9999;background:#fff;border:1px solid #c2cad1;
 border-radius:3px;padding:10px 12px;font:13px 'IBM Plex Sans',sans-serif;color:#14232b;line-height:1.7">
 <div style="font-weight:600;margin-bottom:2px">Routes</div>
 <div><span style="display:inline-block;width:30px;border-top:5px solid #1d5fd1;vertical-align:middle;margin-right:8px"></span>Primary</div>
 <div><span style="display:inline-block;width:30px;border-top:5px dashed #e8820c;vertical-align:middle;margin-right:8px"></span>Backup</div>
 <div><span style="display:inline-block;width:30px;border-top:5px solid #7b8794;vertical-align:middle;margin-right:8px"></span>Conventional baseline</div>
 <div><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#1a73e8;border:2px solid #fff;box-shadow:0 0 0 1px #888;vertical-align:middle;margin:0 11px 0 9px"></span>Origin</div>
 <div><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#d93025;border:2px solid #fff;box-shadow:0 0 0 1px #888;vertical-align:middle;margin:0 11px 0 9px"></span>Destination</div>
 <div style="font-weight:600;margin:6px 0 2px">Segment pass probability</div>
 <div style="height:8px;width:170px;background:linear-gradient(90deg,#780a0a,#c62828,#e9aa14,#1b7a3d);border-radius:2px"></div>
 <div style="display:flex;justify-content:space-between;width:170px;font-size:11px;color:#5b6b75"><span>0%</span><span>50%</span><span>100%</span></div>
 <div><span style="display:inline-block;width:10px;height:10px;border:2px solid #b3261e;border-radius:50%;margin:0 8px 0 10px;vertical-align:middle"></span>High-risk segment</div>
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

    hazards = folium.FeatureGroup(name="High-risk segments")
    seen = set()
    for kind in ("baseline", "backup", "primary"):
        route = getattr(result, kind)
        for s in (route.segments if route else []):
            if s.risk >= HIGH_RISK_THRESHOLD:
                mid = s.coords[len(s.coords) // 2]
                if (round(mid[0], 4), round(mid[1], 4)) in seen:
                    continue
                seen.add((round(mid[0], 4), round(mid[1], 4)))
                folium.CircleMarker(mid, radius=6, color="#b3261e", weight=2, fill=True, fill_color="#fff", fill_opacity=0.9,
                                    tooltip=f"High-risk segment: pass probability {s.pass_probability:.0%}").add_to(hazards)
    hazards.add_to(m)

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
    _marker(o.lat, o.lon, "#1a73e8", "Origin").add_to(m)
    _marker(d.lat, d.lon, "#d93025", "Destination").add_to(m)
    pts += [(o.lat, o.lon), (d.lat, d.lon)]
    m.fit_bounds([[min(p[0] for p in pts), min(p[1] for p in pts)], [max(p[0] for p in pts), max(p[1] for p in pts)]], padding=(30, 30))
    m.get_root().html.add_child(folium.Element(LEGEND))
    _HideLeafletPrefix().add_to(m)
    return m


# ---------------------------------------------------------------------------
# SafeRoute Extras layers. The existing route layers above are not modified.
# ---------------------------------------------------------------------------
from html import escape as _escape  # noqa: E402

from config import NEARBY_CATEGORIES  # noqa: E402

_GLYPHS = {"hospital": "plus-sign", "ambulance": "plus", "fire_station": "fire", "police": "flag", "shelter": "home"}


def add_support_layer(m, nearby_result, selected_id) -> None:
    if nearby_result is None or nearby_result.status != "ok":
        return
    group = folium.FeatureGroup(name="Nearby support")
    if nearby_result.reference:
        folium.CircleMarker(nearby_result.reference, radius=7, color="#0f4c4c", fill=True, fill_opacity=0.9,
                            tooltip="Search reference point").add_to(group)
    for f in nearby_result.facilities:
        label = NEARBY_CATEGORIES.get(f.category, {}).get("label", f.category)
        name = _escape(f.name) if f.name else "Unnamed facility"
        popup = f"<b>{name}</b><br>{_escape(label)}<br>{f.distance_m / 1000:.2f} km straight line"
        folium.Marker((f.lat, f.lon), tooltip=f"{name} ({_escape(label)})", popup=folium.Popup(popup, max_width=260, show=(f.id == selected_id)),
                      icon=folium.Icon(color="orange" if f.id == selected_id else "cadetblue",
                                       icon=_GLYPHS.get(f.category, "plus"), prefix="glyphicon")).add_to(group)
    group.add_to(m)


def add_fire_exit_layer(m, fire_result, highlight_id=None) -> None:
    if fire_result is None or not fire_result.options:
        return
    group = folium.FeatureGroup(name="Fire exits")
    for opt in fire_result.options:
        sel = opt.exit.id == (highlight_id or fire_result.selected_exit_id)
        name = _escape(opt.exit.name)
        folium.Marker((opt.exit.lat, opt.exit.lon), tooltip=f"Verified exit: {name}",
                      popup=folium.Popup(f"<b>{name}</b><br>Source: {_escape(opt.exit.source)}", max_width=260),
                      icon=folium.Icon(color="green" if sel else "gray", icon="log-out", prefix="glyphicon")).add_to(group)
        if not opt.coords:
            continue
        if opt.status == "blocked":
            folium.PolyLine(opt.coords, color="#c62828", weight=4, dash_array="8 8",
                            tooltip="Crosses a blocked segment: not recommended").add_to(group)
        elif sel:
            folium.PolyLine(opt.coords, color="#0f4c4c", weight=6,
                            tooltip="Calculated from map data, not an official evacuation plan").add_to(group)
        elif opt.status == "ok":
            folium.PolyLine(opt.coords, color="#7b8794", weight=2, opacity=0.8).add_to(group)
    group.add_to(m)


def _prefix_off(m) -> None:
    _HideLeafletPrefix().add_to(m)


def add_extras(m, nearby_result, selected_id, fire_result, layer_control=False, fire_highlight=None) -> None:
    add_support_layer(m, nearby_result, selected_id)
    add_fire_exit_layer(m, fire_result, fire_highlight)
    if nearby_result is not None and nearby_result.status == "ok" and selected_id:
        sel = next((f for f in nearby_result.facilities if f.id == selected_id), None)
        if sel:  # zoom to the chosen facility; this runs after the route fit so it wins
            m.fit_bounds([[sel.lat - 0.004, sel.lon - 0.004], [sel.lat + 0.004, sel.lon + 0.004]])
    if layer_control:
        folium.LayerControl(collapsed=True).add_to(m)


def build_support_map(nearby_result, selected_id, fire_result, fire_highlight=None):
    """Map for support facilities and fire exits when no routes have been calculated yet."""
    m = folium.Map(tiles="OpenStreetMap", control_scale=True)
    pts = []
    if nearby_result is not None and nearby_result.status == "ok":
        pts += [(f.lat, f.lon) for f in nearby_result.facilities]
        if nearby_result.reference:
            pts.append(tuple(nearby_result.reference))
    if fire_result is not None:
        pts += [(o.exit.lat, o.exit.lon) for o in fire_result.options]
    if pts:
        m.fit_bounds([[min(p[0] for p in pts), min(p[1] for p in pts)], [max(p[0] for p in pts), max(p[1] for p in pts)]],
                     padding=(30, 30))
    add_extras(m, nearby_result, selected_id, fire_result, layer_control=True, fire_highlight=fire_highlight)
    _prefix_off(m)
    return m
