"""SafeRoute Extras tests. Synthetic data only; no network calls."""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from services import nearby
from services.contracts import FireExit, NearbyResult, Place, Route, RouteRequest, Segment, SupportFacility
from services.fire_exit import get_fire_exit_result, is_fire_scenario, load_exits
from services.recommendation import build_recommendation
from services.route_metrics import route_metrics


# ------------------------------- SOS ---------------------------------------
@pytest.mark.parametrize("raw,expected", [("112", "112"), ("+91 20 1234 5678", "+912012345678"), ("", None),
                                          (None, None), ("abc", None), ("12", None), ("1; DROP TABLE", None)])
def test_tel_normalisation(raw, expected):
    assert config.get_emergency_tel(raw) == expected


def _sos_app():
    from ui.extras import render_sos_button
    render_sos_button()


def _dialog_app():
    from ui.extras import sos_dialog_content
    sos_dialog_content()


def test_sos_button_renders_and_opens_nothing():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(_sos_app).run()
    assert not at.exception
    assert at.button(key="sos_open").label == "SOS Calling"
    assert "sos_last_open" not in at.session_state


def test_sos_dialog_without_number(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(config, "EMERGENCY_NUMBER", None)
    at = AppTest.from_function(_dialog_app).run()
    assert any("No emergency number is configured" in w.value for w in at.warning)
    assert len(at.checkbox) == 0


def test_sos_dialog_with_number(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(config, "EMERGENCY_NUMBER", "112")
    at = AppTest.from_function(_dialog_app).run()
    assert len(at.checkbox) == 1
    assert at.button(key="sos_cancel").label == "Cancel"
    from ui.extras import _qr_svg
    assert _qr_svg("112").lstrip().startswith("<svg")  # QR fallback for desktops
    assert at.button(key="sos_confirm_disabled").disabled
    assert not any("tel:" in m.value for m in at.markdown)  # no call link before acknowledgement
    at.checkbox(key="sos_ack").set_value(True).run()
    assert any('href="tel:112"' in m.value for m in at.markdown)
    assert any("not an emergency-dispatch integration" in i.value for i in at.info)


# ------------------------------ Nearby -------------------------------------
def _el(i, tags, lat=18.5, lon=73.8, typ="node", center=False):
    e = {"type": typ, "id": i, "tags": tags}
    e.update({"center": {"lat": lat, "lon": lon}} if center else {"lat": lat, "lon": lon})
    return e


def _fetch(elements):
    return lambda q: {"elements": elements}


def test_nearby_sorted_and_filters_unrelated():
    els = [_el(1, {"amenity": "hospital", "name": "Far"}, 18.52, 73.8), _el(2, {"amenity": "police"}, 18.501, 73.8),
           _el(3, {"amenity": "cafe"}), _el(4, {"amenity": "hospital", "name": "Near"}, 18.5005, 73.8, "way", True)]
    r = nearby.find_nearby(18.5, 73.8, fetch=_fetch(els))
    assert r.status == "ok" and [f.id for f in r.facilities] == ["way/4", "node/2", "node/1"]


def test_missing_tags_are_none():
    r = nearby.find_nearby(18.5, 73.8, ["hospital"], fetch=_fetch([_el(1, {"amenity": "hospital"})]))
    f = r.facilities[0]
    assert f.name is None and f.phone is None and f.address is None and f.opening_hours is None


@pytest.mark.parametrize("lat,lon", [(None, None), (91, 0), (0, 181)])
def test_nearby_no_location(lat, lon):
    assert nearby.find_nearby(lat, lon, fetch=_fetch([])).status == "no_location"


def test_nearby_empty_and_unavailable():
    assert nearby.find_nearby(18.5, 73.8, fetch=_fetch([])).status == "empty"
    assert nearby.find_nearby(18.5, 73.8, categories=[], fetch=_fetch([])).status == "empty"

    def boom(q):
        raise ConnectionError("down")
    r = nearby.find_nearby(18.5, 73.8, fetch=boom)
    assert r.status == "unavailable" and not r.facilities


def test_query_contents_and_category_filter():
    q = nearby.build_query(18.5, 73.8, ["hospital", "shelter"], 5000)
    assert '["amenity"="hospital"]' in q and '["social_facility"="shelter"]' in q and "police" not in q
    assert "around:5000,18.5,73.8" in q and q.rstrip().endswith("out center tags;")
    r = nearby.find_nearby(18.5, 73.8, ["police", "bogus"], fetch=_fetch([_el(1, {"amenity": "hospital"})]))
    assert r.status == "empty"


def test_directions_url():
    f = SupportFacility("node/1", "hospital", 1.5, 2.5, 10)
    assert nearby.directions_url(None, f) == "https://www.google.com/maps/dir/?api=1&destination=1.5,2.5"
    assert nearby.directions_url((3.0, 4.0), f).endswith("&origin=3.0,4.0")


# --------------------------- Recommendation --------------------------------
def R(t, risk, blocked=None, km=10):
    d = {"time_min": t, "risk": risk, "distance_km": km}
    if blocked is not None:
        d["blocked_segments"] = blocked
    return d


def test_metrics_missing_fields_none():
    m = route_metrics({"time_min": 5})
    assert m["time_min"] == 5 and m["risk"] is None and m["blocked"] is None and m["coords"] is None
    assert all(v is None for v in route_metrics(None).values())
    assert route_metrics({"blocked_segments": [1, 2]})["blocked"] == 2


def test_metrics_on_real_route_object():
    seg = Segment([(0, 0), (0, 1)], 0.4, 100)
    m = route_metrics(Route("primary", [seg], 12.0, 3.0, 0.7))
    assert m["time_min"] == 12 and m["risk"] == pytest.approx(0.4) and m["blocked"] is None and m["coords"]


def test_recommendation_success():
    rec = build_recommendation(R(22, 3.0), R(25, 4.5), R(18, 6.0), hazard_label="Flood")
    assert rec.recommended_route == "primary"
    assert "+4.0 min" in rec.explanation and "50%" in rec.explanation and "safe" not in rec.explanation.lower()


def test_recommendation_insufficient_data():
    for p in (None, {"time_min": 5}):
        rec = build_recommendation(p)
        assert rec.recommended_route is None and rec.limitations


def test_blocked_primary_yields_backup():
    rec = build_recommendation(R(10, 1.0, 2), R(30, 5.0, 0), R(9, 2.0, 0))
    assert rec.recommended_route == "backup"


def test_missing_backup_disclosed():
    rec = build_recommendation(R(10, 1.0, 0), None, R(9, 2.0, 0))
    assert any("No independent backup" in l for l in rec.limitations)


def test_explainer_changes_text_only():
    base = build_recommendation(R(22, 3.0), R(25, 4.5), R(18, 6.0))
    rec = build_recommendation(R(22, 3.0), R(25, 4.5), R(18, 6.0), explainer=lambda r: "Model words.")
    assert rec.mode == "model_based_explanation" and rec.explanation == "Model words."
    assert rec.recommended_route == base.recommended_route and rec.factors == base.factors
    bad = build_recommendation(R(22, 3.0), explainer=lambda r: 1 / 0)
    assert bad.mode == "rule_based"


# ------------------------------ Fire exit ----------------------------------
def _geo(tmp_path, feats):
    p = tmp_path / "e.geojson"
    p.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return str(p)


def _feat(i, lon, lat, verified=True, source="Fire dept survey"):
    props = {"id": i, "name": i, "verified": verified}
    if source is not None:
        props["source"] = source
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props}


def _route(t=5, risk=1.0, blocked=0):
    return {"time_min": t, "risk": risk, "distance_km": 1, "blocked_segments": blocked, "coords": [(0, 0), (0, 1)]}


def test_missing_and_shipped_empty_file(tmp_path):
    assert get_fire_exit_result((1, 1), "wildfire", lambda a, b: None, path=str(tmp_path / "nope")).status == "no_data"
    assert get_fire_exit_result((1, 1), "wildfire", lambda a, b: None, path=os.path.join(ROOT, "data", "fire_exits.geojson")).status == "no_data"


def test_unverified_and_sourceless_ignored(tmp_path):
    p = _geo(tmp_path, [_feat("a", 1, 1, verified=False), _feat("b", 1, 1, source=None), _feat("c", 1, 1, source="  ")])
    exits, ignored, err = load_exits(p)
    assert exits == [] and ignored == 3 and err is None
    assert get_fire_exit_result((1, 1), "wildfire", lambda a, b: _route(), path=p).unverified_count == 3


def test_scenarios_and_location(tmp_path):
    p = _geo(tmp_path, [_feat("a", 1, 1)])
    assert is_fire_scenario(" Wildfire ") and not is_fire_scenario("flood") and not is_fire_scenario(None)
    assert get_fire_exit_result((1, 1), "flood", lambda a, b: _route(), path=p).status == "no_fire_scenario"
    assert get_fire_exit_result(None, "wildfire", lambda a, b: _route(), path=p).status == "no_location"


def test_risk_beats_distance(tmp_path):
    p = _geo(tmp_path, [_feat("near", 0.1, 0), _feat("far", 5, 0)])
    risks = {0.1: 4.0, 5: 1.0}
    r = get_fire_exit_result((0, 0), "wildfire", lambda o, e: _route(risk=risks[e[1]]), path=p)
    assert r.status == "ok" and r.selected_exit_id == "far" and "not an official evacuation plan" in r.message


def test_unreachable_and_engine_exception(tmp_path):
    p = _geo(tmp_path, [_feat("a", 1, 1)])
    assert get_fire_exit_result((0, 0), "wildfire", lambda o, e: None, path=p).status == "unreachable"

    def boom(o, e):
        raise RuntimeError("x")
    assert get_fire_exit_result((0, 0), "wildfire", boom, path=p).status == "unreachable"


def test_all_blocked_and_blocked_near_skipped(tmp_path):
    p = _geo(tmp_path, [_feat("near", 0.1, 0), _feat("far", 5, 0)])
    r = get_fire_exit_result((0, 0), "wildfire", lambda o, e: _route(blocked=2), path=p)
    assert r.status == "blocked" and r.selected_exit_id is None
    r = get_fire_exit_result((0, 0), "wildfire", lambda o, e: _route(blocked=2 if e[1] == 0.1 else 0), path=p)
    assert r.status == "ok" and r.selected_exit_id == "far"


def test_candidate_limit_note(tmp_path):
    p = _geo(tmp_path, [_feat(f"e{i}", i, 0) for i in range(1, 6)])
    r = get_fire_exit_result((0, 0), "wildfire", lambda o, e: _route(), path=p, max_candidates=2)
    assert len(r.options) == 2 and any("nearest 2" in n for n in r.notes)


# ------------------------------ UI smoke -----------------------------------
def _nearby_ui():
    from services.contracts import NearbyResult, SupportFacility
    from ui.panels import render_nearby_panel
    f = SupportFacility("node/1", "hospital", 1.0, 1.0, 500, name="<script>alert(1)</script>")
    render_nearby_panel(NearbyResult("ok", "Found 1 facility.", (f,), (1.0, 1.0), 5000, "attr"))


def test_nearby_panel_escapes_and_not_listed():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(_nearby_ui).run()
    assert not at.exception
    html = " ".join(m.value for m in at.markdown)
    assert "&lt;script&gt;" in html and "<script>" not in html and "Not listed" in html


def _rec_ui():
    from services.recommendation import build_recommendation
    from ui.panels import render_recommendation_card
    render_recommendation_card(build_recommendation({"time_min": 5, "risk": 1.0}))


def test_recommendation_card_renders():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(_rec_ui).run()
    assert not at.exception and any("Rule-based recommendation" in m.value for m in at.markdown)


def _fire_ui_ok():
    from services.contracts import FireExit, FireExitOption, FireExitResult
    from ui.panels import render_fire_exit_panel
    ex = FireExit("a", "Exit <b>A</b>", 1, 1, "Survey", "2026-01-01")
    render_fire_exit_panel(FireExitResult("ok", "Calculated from map data.", (FireExitOption(ex, "ok", 4.0, 1.2, 0.5, None, ((1, 1), (1, 2))),), "a"))


def _fire_ui_nodata():
    from services.contracts import FireExitResult
    from ui.panels import render_fire_exit_panel
    render_fire_exit_panel(FireExitResult("no_data", "No verified exit data.", unverified_count=2))


@pytest.mark.parametrize("fn", [_fire_ui_ok, _fire_ui_nodata])
def test_fire_panel_states(fn):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(fn).run()
    assert not at.exception


def test_map_layers_build():
    from ui.map_view import add_extras, build_map
    import folium
    fac = SupportFacility("node/1", "hospital", 18.5, 73.8, 100, name="<b>X</b>")
    nr = NearbyResult("ok", "m", (fac,), (18.5, 73.8), 5000, "a")
    ex = FireExit("a", "A", 18.5, 73.8, "Survey")
    from services.contracts import FireExitOption, FireExitResult
    fr = FireExitResult("ok", "m", (FireExitOption(ex, "ok", 1, 1, 1, 0, ((18.5, 73.8), (18.51, 73.81))),), "a")
    m = folium.Map()
    add_extras(m, nr, "node/1", fr, layer_control=True)
    html = m.get_root().render()
    assert "Nearby support" in html and "Fire exits" in html and "&lt;b&gt;X&lt;/b&gt;" in html


# ------------------------- Merged app.py ------------------------------------
@pytest.fixture
def app(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("EMERGENCY_ENGINE", "fake_engine:build")
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60)
    at.session_state["origin_mode"] = "Coordinates"
    at.session_state["dest_mode"] = "Coordinates"
    return at


def test_app_recommendation_and_fire_states(app, monkeypatch, tmp_path):
    at = app.run()
    assert not at.exception
    at.button(key="calculate").click().run()
    assert not at.exception and any("Recommended:" in m.value for m in at.markdown)
    at.button(key="run_fire").click().run()
    assert at.session_state["fire_result"].status == "no_data"

    p = tmp_path / "exits.geojson"
    p.write_text(json.dumps({"type": "FeatureCollection", "features": [_feat("x", 20.1, 10.1)]}))
    monkeypatch.setattr(config, "FIRE_EXIT_DATA_PATH", p)
    at.button(key="run_fire").click().run()
    assert at.session_state["fire_result"].status == "no_fire_scenario"
    at.selectbox(key="hazard").select("wildfire").run()
    at.button(key="run_fire").click().run()
    assert not at.exception and at.session_state["fire_result"].status == "ok"
    monkeypatch.setattr(nearby, "_default_fetch", lambda q: (_ for _ in ()).throw(ConnectionError("offline")))
    at.button(key="run_nearby").click().run()  # source down: must degrade gracefully, never invent results
    assert not at.exception and at.session_state["nearby_result"].status == "unavailable"


def test_recommendation_reports_extra_distance():
    rec = build_recommendation(R(22, 3.0, km=10.35), R(25, 4.5, km=10.0), R(18, 6.0, km=10.0))
    assert "about 350 m longer" in rec.explanation


def test_high_risk_marker():
    from ui.map_view import build_map
    seg = Segment([(10, 20), (10, 20.01)], 0.8, 1000)
    rt = Route("primary", [seg], 5, 1, 0.2)
    from services.contracts import RouteResult
    q = RouteRequest(Place("A", 10, 20), Place("B", 10, 20.01), "ambulance", "flood", {}, "High")
    html = build_map(RouteResult(primary=rt, baseline=rt), q, False).get_root().render()
    assert "High-risk segment: pass probability 20%" in html


# ------------------------------ Geocoding ----------------------------------
class _Resp:
    def __init__(self, data, status=200):
        self._d, self.status_code = data, status

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError("bad")

    def json(self):
        return self._d


def test_geocode_falls_back_to_photon(monkeypatch):
    import requests
    from services import geocode
    geocode._CACHE.clear()

    def fake_get(url, **kw):
        if "nominatim" in url:
            raise requests.ConnectionError("blocked")
        return _Resp({"features": [{"geometry": {"coordinates": [73.85, 18.52]},
                                    "properties": {"name": "Pune", "state": "Maharashtra", "country": "India"}}]})
    monkeypatch.setattr(requests, "get", fake_get)
    out = geocode.search_places("Pune")
    assert out[0].name == "Pune, Maharashtra, India" and out[0].lat == 18.52 and out[0].lon == 73.85


def test_geocode_both_down_and_empty_not_cached(monkeypatch):
    import requests
    from services import geocode
    geocode._CACHE.clear()
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("x")))
    with pytest.raises(geocode.GeocodingError):
        geocode.search_places("Nowhere")
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp([] if "nominatim" in a[0] else {"features": []}))
    assert geocode.search_places("Nowhere") == [] and "nowhere" not in geocode._CACHE


def test_route_here_sets_destination_and_calculates(app):
    from services.contracts import NearbyResult, SupportFacility
    fac = SupportFacility("node/9", "hospital", 10.2, 20.2, 900, name="City Hospital")
    at = app
    at.session_state["nearby_result"] = NearbyResult("ok", "m", (fac,), (10.0, 20.0), 5000, "a")
    at.run()
    assert not at.exception
    at.button(key="routehere_node/9").click().run()
    assert not at.exception, at.exception
    d = at.session_state["result_request"].destination
    assert (round(d.lat, 3), round(d.lon, 3)) == (10.2, 20.2)
    assert any("City Hospital" in m.value for m in at.markdown)


def test_support_map_without_routes():
    from ui.map_view import build_support_map
    fac = SupportFacility("node/1", "hospital", 18.5, 73.8, 100, name="H")
    nr = NearbyResult("ok", "m", (fac,), (18.5, 73.8), 5000, "a")
    html = build_support_map(nr, "node/1", None).get_root().render()
    assert "Nearby support" in html and "setPrefix(false)" in html


def test_tel_read_at_call_time(monkeypatch):
    monkeypatch.setenv("SAFEROUTE_EMERGENCY_NUMBER", "112")
    monkeypatch.setattr(config, "EMERGENCY_NUMBER", None)
    assert config.get_emergency_tel() == "112"
