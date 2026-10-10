# Resilient Emergency Routing Dashboard

Streamlit + Folium control dashboard for comparing a primary, a backup and a conventional baseline route for emergency vehicles under a hazard scenario. Works anywhere on the map: origin and destination can be searched by name (countries, cities, towns, villages) or entered as coordinates. Twelve hazard types are covered: flood, cyclone, earthquake, tsunami, landslide, wildfire, volcanic eruption, blizzard, avalanche, severe storm and tornado, dust storm, and extreme heat.

## Install

    python -m venv .venv
    source .venv/bin/activate        # Windows: .venv\Scripts\activate
    pip install -r requirements.txt

## Launch

    streamlit run app.py

Opens at http://localhost:8501.

## Test (mock responses, no network needed)

    python -m pytest tests -q

## Simulated data

Until the routing engine is ready, `services/mock_engine.py` supplies results. Road geometry is real (OSRM public demo server; falls back to approximate paths if unreachable). Risk, reliability and ETA penalties are synthetic and the dashboard labels them as simulated. The mock is not a routing algorithm and not the risk model.

## Integrating the real engine

The UI talks only to `services.service.compute_routes(request)`. Implement an object with:

    route(request: RouteRequest) -> RouteResult      # see services/contracts.py

then launch with:

    EMERGENCY_ENGINE="your_package.module:factory" streamlit run app.py

`factory()` returns the engine. Return `Segment` objects with real `(lat, lon)` coordinates and a `risk` in 0..1; set `simulated=False`. Raise `RoutingError` with a readable message when no route exists. The dashboard never computes shortest paths or risk itself.

## Layout

    app.py                 page assembly and session state
    config.py              vehicles, hazards, severities, colours
    services/              contracts, routing call, geocoding, mock engine
    ui/                    styles, sidebar, map, panels
    tests/                 unit tests and app smoke test

## Notes

- Place search uses OpenStreetMap Nominatim and the demo route server is OSRM. Both are public services with usage limits; use your own instances for production.
- Coverage of small villages depends on how complete OpenStreetMap is there.
