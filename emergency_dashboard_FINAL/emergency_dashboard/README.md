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

## SafeRoute Extras: SOS Calling, Nearby Support, route recommendation, Fire Exit

| Feature | Status |
|---|---|
| SOS Calling | Functional once a verified number is configured. Opens the dialer only; not a dispatch integration. |
| Nearby Support | Partially functional. OpenStreetMap data, needs internet. No capacity or live availability. |
| Route recommendation | Functional as a rule-based layer on the engine output. No AI service is called. |
| Fire Exit | Awaiting integration. Needs verified exit data and a fire scenario in the engine. Indoor routing needs floor plans or an evacuation network. |

### Configuration
Environment variable or `.streamlit/secrets.toml` (see `secrets.toml.example`; keep the real file out of git):
- `SAFEROUTE_EMERGENCY_NUMBER`: no default. Without it the SOS dialog shows a setup state and no call link.
- `SAFEROUTE_EMERGENCY_LABEL`: default "Local emergency number".
- `SAFEROUTE_OVERPASS_URL`: default `https://overpass-api.de/api/interpreter`.

### How it works
- **SOS Calling:** a fixed button opens a confirmation dialog. After the user ticks the acknowledgement, a `tel:` link opens the device dialer and the user must press call. Nothing is dialed on load or on click, and the app cannot tell whether a call was placed.
- **Nearby Support:** queries OpenStreetMap through Overpass around a chosen reference point (origin, destination, custom coordinates, or device location if `streamlit-geolocation` is installed). Distances are straight-line. Missing fields show "Not listed". Directions links open an external map and are not hazard-aware.
- **Recommendation:** ranks the primary and backup route by blocked segments, then risk score, then travel time, using only numbers the engine returned. The baseline is a comparison only. A model may rewrite the explanation text only (`config.AI_PROVIDER` is None). The mock engine does not report blocked segments, so that is disclosed. `services/route_metrics.py` `_ALIASES` maps engine field names; the risk score is derived from the length-weighted segment risks when the engine has no single score.
- **Fire Exit:** only exits in `data/fire_exits.geojson` with `verified: true` and a non-empty `source` are used (the shipped file is empty). Each exit is routed through the existing engine for a fire scenario (`wildfire` here; edit `FIRE_HAZARD_KEYS`). Results are "calculated from map data, not an official evacuation plan".

### Exit data format
```
{"type": "Feature", "geometry": {"type": "Point", "coordinates": [LON, LAT]},
 "properties": {"id": "unique-id", "name": "Exit name", "verified": true,
                "source": "Who verified it, and how", "last_verified": "YYYY-MM-DD", "kind": "optional"}}
```

### Tests
    python -m pytest -q
Not covered by automation: a real `tel:` call on a phone, mobile and tablet layout, a live Overpass request, accessibility checks, the SOS dialog opened through a real click, and the real routing engine.

### Before real-world emergency use
- Verify the emergency number for each deployment region and test the dialer link on real phones.
- Replace or supplement OpenStreetMap with an authoritative facility source and show last-verified dates.
- Add a fire hazard model to the routing engine, plus verified exit and indoor data per site.
- Have the routing and risk model validated by domain experts.
- Test accessibility and mobile layouts on real devices.
- Add monitoring and a documented fallback for when the data source or engine is down.
- Obtain sign-off from the responsible emergency authority. This tool supports decisions and does not replace emergency responders or building evacuation procedures.

### Design notes
Dark teal navigation (header band and sidebar, via `[theme.sidebar]` in `.streamlit/config.toml`, needs Streamlit 1.46 or newer) with a light workspace. The SOS button sits in the top bar in red so it never covers the map. The map marks high-risk segments (risk at or above 60%) and the Fire Exit tab lets you pick which verified exit to highlight.

### Latest changes
- Origin and destination use button-style switches ("Search place" first, "Coordinates" second).
- SOS reads the number at click time, shows it prominently, offers a QR code so a computer user can open the dialer on a phone, and keeps Cancel and Confirm.
- Nearby Support: the map now shows facilities even before routes are calculated, "Show on map" zooms to and opens the facility, and "Route here" calculates hazard-aware routes to it inside the app. "External map" still opens Google Maps.
