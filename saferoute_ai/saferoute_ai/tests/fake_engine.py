"""Test double: MockEngine with fixed geometry so tests never touch the network."""
from services.mock_engine import MockEngine, RawRoute


def _line(lat0, lon0, lat1, lon1, bulge=0.0, n=50):
    return [(lat0 + (lat1 - lat0) * i / n + bulge * min(i, n - i) / n, lon0 + (lon1 - lon0) * i / n) for i in range(n + 1)]


def three_routes(_req):
    return [RawRoute(_line(10, 20, 10.3, 20.3, 0.0), 1200),
            RawRoute(_line(10, 20, 10.3, 20.3, 0.02), 1500),
            RawRoute(_line(10, 20, 10.3, 20.3, -0.04), 1800)]


def one_route(_req):
    return three_routes(_req)[:1]


def build():
    return MockEngine(geometry_provider=three_routes)
