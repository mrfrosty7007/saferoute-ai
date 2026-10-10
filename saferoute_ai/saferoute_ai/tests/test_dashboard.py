import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fake_engine
from services.contracts import Place, RouteRequest, RoutingError, validate_request
from services.mock_engine import MockEngine
from services.service import compute_routes


def req(**kw):
    base = dict(origin=Place("A", 10, 20), destination=Place("B", 10.3, 20.3), vehicle="ambulance",
                hazard="flood", params={"rainfall": 120, "river_level": 5}, severity="High")
    base.update(kw)
    return RouteRequest(**base)


def test_three_routes_with_metrics():
    r = compute_routes(req(), MockEngine(fake_engine.three_routes))
    assert r.simulated and r.primary and r.backup and r.baseline
    assert r.primary.reliability >= r.backup.reliability
    assert 0 <= r.overlap_pct <= 100
    assert r.primary.weakest_segment().risk >= 0


def test_missing_backup_is_graceful():
    r = compute_routes(req(), MockEngine(fake_engine.one_route))
    assert r.backup is None and r.overlap_pct is None and r.notes


def test_higher_severity_lowers_reliability():
    lo = compute_routes(req(severity="Low"), MockEngine(fake_engine.three_routes)).primary.reliability
    hi = compute_routes(req(severity="Extreme"), MockEngine(fake_engine.three_routes)).primary.reliability
    assert hi < lo


@pytest.mark.parametrize("kw", [dict(destination=Place("B", 10.0001, 20.0001)), dict(vehicle="bike"),
                                dict(origin=Place("A", 95, 20))])
def test_invalid_requests_are_rejected(kw):
    assert validate_request(req(**kw))
    with pytest.raises(RoutingError):
        compute_routes(req(**kw), MockEngine(fake_engine.three_routes))


def test_engine_crash_is_wrapped():
    class Bad:
        def route(self, r):
            raise RuntimeError("boom")
    with pytest.raises(RoutingError):
        compute_routes(req(), Bad())


def test_every_hazard_runs():
    from config import HAZARDS
    for key, hz in HAZARDS.items():
        params = {p.key: p.default for p in hz.params}
        assert compute_routes(req(hazard=key, params=params), MockEngine(fake_engine.three_routes)).primary


def test_map_builds():
    from ui.map_view import build_map
    q = req()
    r = compute_routes(q, MockEngine(fake_engine.three_routes))
    assert "Conventional baseline" in build_map(r, q, True).get_root().render()


def test_app_smoke(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("EMERGENCY_ENGINE", "fake_engine:build")
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=30).run()
    assert not at.exception
    at.button[0].click().run()
    assert not at.exception, at.exception
    assert at.session_state["result"] is not None
