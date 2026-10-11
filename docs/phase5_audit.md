# Rakshapath (formerly SafeRouteAI) — Phase 5 repository and implementation audit

Date: 2026-10-11
Repository: `C:\1.Projects\SafeRouteAI`
Branch: `integration/ui-backend`
Audited starting commit: `aa9ad65` (`fix(ui): prevent KeyError on destination selectbox and enforce landmark validation`)

## Repository state

- The starting working tree was clean. The branch was at `aa9ad65`, matching `origin/integration/ui-backend`; recent commits included the Streamlit integration and Community Cloud packaging commit.
- Python is pinned to the 3.12 line by `.python-version` (`3.12`); the checked interpreters reported Python 3.12.10.
- Runtime graph, elevation and depression-cache assets are present under `data/`. The runtime path constants in `saferoute/config.py` resolve from the module location, not the shell's current directory.
- Streamlit configuration exists at `.streamlit/config.toml` and enables headless operation. No Streamlit Community Cloud deployment metadata, hosted URL or deployment secret is present in the checkout.
- The runtime needs no API key. Geocoding is an optional search-place workflow; the default landmark and coordinate workflows use local data.
- The original `requirements.txt` used lower bounds. Phase 5.2 adds a complete version lock and includes it from the Community Cloud-recognized `requirements.txt`; the lock pins versions but does not include hashes or platform wheels.

## Confirmed fixes made

1. **Earthquake simulation banner:** `RealRoutingEngine` previously returned `simulated=False` for earthquake requests, so the shared UI simulation banner did not appear. It now marks earthquake output as simulated. Regression: `TestTeammateUIAdapter.test_earthquake_scenario_simulation`.
2. **Reliability underflow:** route reliability used `exp(max(-50, sum(log(p))))`, imposing a false positive floor on sufficiently unlikely routes. It now computes `exp(sum(log(p)))`; ordinary floating-point underflow is displayed as zero. Regression: `TestRoutingEngine.test_reliability_underflow_is_reported_as_zero`.
3. **Backup overlap:** the UI describes overlap as the share of the backup route that is also in the primary route. The implementation used primary-edge count as the denominator. It now divides by backup-edge count, with a regression assertion in `TestRoutingEngine.test_06_backup_route_properties`.
4. **Backup naming:** the route label said “Independent Detour” even when it shared substantial road segments. It now says “Alternate”; the measured overlap remains visible.
5. **River-stage precision:** the slider step was 0.5 m, which could not select 84.7 m. It now uses 0.1 m increments. Regression: `TestPhase5Workflows.test_warning_stage_precision_and_recalculation`.
6. **Severity control meaning:** severity was recorded and displayed but did not change the hazard model. The control now says “Incident classification” and explains that numeric hazard controls are the model inputs.
7. **Live-data wording:** the dashboard header said “live hazard scenarios” although scenarios are user-configured model inputs. It now says “selected hazard scenarios.”

## Routing and interface findings

- Primary route uses non-negative edge cost `time_s + lambda * -ln(p)` and the configured 120-second risk weight. The baseline uses shortest geometric distance. Existing optimality tests cover both objectives.
- The river-stage value is carried by `RouteRequest.params["river_level"]` into `RealRoutingEngine`, `FloodHazardModel.evaluate_risk`, edge passability, and then the routing edge `cost`. In the current cached routing graph, changing stage from 82.0 m to 84.7 m at rainfall 45 mm/h changes pass probability and cost on 52 of 4,676 edges. None of the selected default primary, backup, or baseline edges is among those 52. Consequently their geometry, ETA, distance, reliability, and objective cost remain identical. This is expected for these default inputs, not a disconnected parameter. A synthetic regression proves the primary switches from a short low corridor to a longer high corridor when the stage makes the low corridor riskier.
- Backup candidates are found by penalizing risky primary edges and then the full primary corridor at multipliers 3, 10, and 30. Each candidate is scored on the original graph as base route cost plus a diversity penalty proportional to its share of primary edges. On the default moderate-flood ambulance request, the selected backup now shares **9 of 42 edges (21.4%)**, down from **28 of 36 (77.8%)**. It costs 656.82 objective seconds vs 526.89 for primary (+24.7%), takes 7.26 vs 5.78 minutes (+1.49 minutes), and is 2.85 vs 2.28 km. Reliability falls from 22.25% to 15.83%. The backup's weakest pass probability is 84.68%, slightly above primary's 83.49%; both routes have zero segments below p=0.5. Both old and new alternatives avoid the primary's weakest p=0.8349 segment but share another critical edge at p=0.8867. The backup's weakest segment is not that shared segment. The interface reports overlap and calls it an alternate; lower edge overlap does not imply hazard independence.
- Reliability is the product of segment pass probabilities, evaluated as an exponential of summed log probabilities. The hazard models floor individual probabilities at `1e-6`; this is a model floor, not a route reliability floor.
- All three vehicle choices generate all three routes in the Streamlit AppTest workflow. Vehicle-specific passability behavior is also covered by `TestTeammateUIAdapter.test_vehicle_differentiation_via_adapter` and hazard tests.
- The dashboard now plots DEM-derived road-node elevations against cumulative route distance for each calculated route. The profile is useful for terrain context; straight lines between node samples are illustrative and do not represent a continuous surveyed elevation trace.
- The rendered local browser's map-view radio changed to **Routes with risk** and the Folium map iframe rerendered with its segment pass-probability legend. Folium structure and risk rendering are also covered in adapter tests.
- The 84.7 m value is accepted, included in the submitted request signature, and recalculates route results. The default geometry/metrics remain the same because the selected edges' flood inputs do not change. Streamlit uses the result request and result together when building map lines and metrics; the workflow regression confirms route geometry, distance, ETA, reliability, and profile distance remain consistent after recalculation.
- For a no-path routing error, the app clears stale results and shows “Routes were not calculated” with the engine's specific message. A same-node snap has its own prompt to choose locations further apart. Backend no-path handling and AppTest UI error presentation are covered.
- Stale/empty landmark selections fall back to valid benchmark landmarks in the picker. Coordinate validation rejects values outside the Daraganj bounds; route snapping and no-path handling have unit coverage.

## Risks and unresolved items

- **Hosted deployment: NOT VERIFIED.** No hosted URL or deployment access was provided. The local clean install and startup do not prove Community Cloud deployment status.
- **Local browser: VERIFIED for the default rendered workflow and risk-view selection.** The app served locally at `http://127.0.0.1:8765/`; route metrics, map, and elevation chart rendered, and the risk-view radio switch updated the map component. Hosted deployment remains unverified.
- `requirements.txt` retains its broad lower bounds for library compatibility, while `requirements-lock.txt` pins the complete Python 3.12.10 clean-environment resolution, including transitive packages. The root requirements file includes the lock. The lock does not pin package hashes or platform wheels.
- Current Streamlit 1.65 emits deprecation warnings for `use_container_width`; it still works in the tested version. Since the project advertises Streamlit >=1.30, changing to the replacement API should be paired with an explicit supported minimum version.
- No current flood observations, real-time traffic feed, operational dispatch, trained ML prediction, or hospital capacity integration was found. The flood calculations are a regional stage/elevation simplification; earthquake results are an exploratory simulation.

## Evidence pointers

- Automated baseline/final results and scenario workflow evidence: [`phase5_test_report.md`](phase5_test_report.md)
- Clean install/start procedure and limitations: [`phase5_deployment_checklist.md`](phase5_deployment_checklist.md)
- Five-minute evaluator walkthrough: [`phase5_demo_script.md`](phase5_demo_script.md)
