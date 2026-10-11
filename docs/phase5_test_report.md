# Rakshapath Phase 5 test and verification report

Date: 2026-10-11. Tests ran on Windows with Python 3.12.10.

## Test baseline and prior Phase 5 results

The repository documents `python -m unittest discover tests`. The repository `.venv` contained the required packages and was used for the baseline and Phase 5 runs. The 63-test rows below are intermediate historical runs; Phase 5.1 expanded the suite to 67 tests, and the final release-closure results are recorded at the end of this report.

| Run | Command | Tests | Passed | Failed / errors | Skipped | unittest runtime |
|---|---|---:|---:|---:|---:|---:|
| Baseline at `aa9ad65` | `.\.venv\Scripts\python.exe -m unittest discover tests -v` | 59 | 59 | 0 | 0 | 25.734 s |
| Intermediate Phase 5 working tree | `.\.venv\Scripts\python.exe -m unittest discover tests -v` | 63 | 63 | 0 | 0 | 8.345 s |
| Intermediate clean dependency environment | `python -m unittest discover tests -v` from temporary Python 3.12.10 venv | 63 | 63 | 0 | 0 | 8.396 s |

Phase 5.1 adds synthetic scenario/backup regressions, default-stage edge and cost comparison, an elevation chart check, and a user-visible unreachable-route check. Final results are below.

The first, unqualified `python -m unittest discover tests -v` attempt used the global interpreter, which did not have `networkx` installed; all five test modules failed to import and no tests executed. The `.venv` run above is the documented-environment baseline. The temporary clean environment was built with `pip install -r requirements.txt`; `pip check` reported no broken requirements.

## Relevant tests

- `TestPhase2ScientificBehaviorProtection`: non-negative depths, rainfall/stage monotonicity, vehicle differentiation, bridge classification.
- `TestRoutingEngine.test_05_reliability_and_weakest_segment`: reliability product and weakest segment.
- `TestRoutingEngine.test_06_backup_route_properties`: endpoints and corrected backup-overlap denominator.
- `TestRoutingEngine.test_07_baseline_distance_optimality`: conventional distance objective.
- `TestRoutingEngine.test_08_invalid_inputs_and_unreachable`: invalid nodes and unreachable graph paths.
- `TestRoutingEngine.test_reliability_underflow_is_reported_as_zero`: new numerical regression.
- `TestTeammateUIAdapter.test_fresh_app_startup_and_defaults`: clean app initialization and benchmark defaults.
- `TestTeammateUIAdapter.test_place_picker_stale_or_invalid_landmark_handling`: stale/empty picker fallback.
- `TestTeammateUIAdapter.test_all_daraganj_landmarks_routable`: registered landmark routes.
- `TestTeammateUIAdapter.test_earthquake_scenario_simulation`: simulation output labeling.
- `TestPhase5Workflows.test_default_benchmark_pair_calculates_routes`: default pair, all three vehicle types, all three routes, and earthquake selection through Streamlit AppTest.
- `TestPhase5Workflows.test_warning_stage_precision_and_recalculation`: 84.7 m entry and recalculated request signature.
- `TestPhase5Workflows.test_coordinate_origin_can_generate_routes`: coordinate-origin input and route generation.
- `TestTeammateUIAdapter.test_build_route_map_rendering` and `test_build_study_area_map`: Folium map structure and route/risk rendering.

## End-to-end results

| Workflow | Expected | Observed | Outcome |
|---|---|---|---|
| Launch from repository root in headless mode | Streamlit starts and serves app | `streamlit run app.py --server.headless true --server.port 8765` started; `/_stcore/health` returned HTTP 200 `ok` | PASS (local server) |
| Clean Python 3.12 install and startup | Requirements install and app serves | Fresh temporary venv installed `requirements.txt`; `pip check` clean; port 8766 health returned HTTP 200 `ok` | PASS |
| Default Daraganj South → Daraganj North | Primary, backup and baseline routes render | AppTest calculated all three; no Streamlit exception | PASS |
| Vehicle selection | Each supported vehicle recalculates | Ambulance, Fire Tender and Rescue Truck each produced all three route results | PASS |
| River stage 84.7 m | Value is selectable and submitted in recalculation | AppTest read back 84.7 and confirmed it in `result_request` and the result signature | PASS |
| Earthquake scenario | UI labels outputs as modeled simulation | AppTest selected earthquake; `result.simulated` is true and adapter regression passes | PASS |
| Landmark and coordinate input | Valid selections route; invalid/stale choices are safe | All registered landmarks route in adapter tests; coordinate-origin AppTest routes; stale/empty picker fallback and out-of-bounds validation tests pass | PASS for tested paths |
| Route geometries and landmarks | Map object contains route polylines/markers | Folium rendering tests pass; local browser showed the map iframe, route layer, origin/destination markers and OpenStreetMap attribution | PASS locally |
| Risk overlay | Segment-level route-risk layer is available | Adapter map test passes; local browser radio selected “Routes with risk” and map iframe rerendered | PASS (local browser) |
| Elevation profile | Profile renders without exception | Interactive chart displays cumulative route distance vs sampled road-node elevation; AppTest checks chart and profile data | PASS |
| Unreachable route message in UI | User sees a clear no-route message | AppTest injects a `RoutingError`; UI clears stale result and displays “Routes were not calculated” with the error detail | PASS |
| Hosted application | Hosted deployment responds | No hosted URL supplied or tested | NOT VERIFIED |

## Observed default route metrics

For Ambulance, flood model, rainfall 45 mm/h, stage 82 m, default benchmark pair:

| Route | Distance | ETA | Reliability | Segments |
|---|---:|---:|---:|---:|
| Primary | 2.28 km | 5.8 min | 22.2459% | 33 |
| Backup | 2.85 km | 7.3 min | 15.8304% | 42 |
| Baseline | 2.11 km | 5.7 min | 0.0551% | 40 |

After Phase 5.1 backup selection, overlap is 21.4% (9/42 backup edges), compared with 77.8% (28/36) before. Before: 6.03 min, 2.38 km, 21.64% reliability. After: 7.26 min, 2.85 km, 15.83% reliability. In both versions, the backup avoids the primary's weakest p=0.8349 segment, but shares one critical primary edge at p=0.8867; neither has a p<0.5 segment. The lower overlap costs about 1.49 minutes and lowers modeled reliability by 5.81 percentage points versus the old backup; it does not establish hazard independence.

## Interpretation and limitations

- Test runtimes vary with process and filesystem cache state; the table records `unittest`'s reported duration, not a performance benchmark.
- The stage value flows into the flood model, pass probabilities and Dijkstra edge costs. Exactly 52 of 4,676 directed condensed-graph edges change pass probability/cost between 82.0 m and 84.7 m; none are on the selected default primary, backup, or baseline. Thus default routes and their metrics are expected to stay the same. A diamond-graph test demonstrates an actual route switch when the altered hazard changes corridor preference.
- A local browser session loaded `http://127.0.0.1:8765/`, calculated benchmark routes, showed the elevation chart, and selected the “Routes with risk” radio. The map iframe rerendered, with the probability legend available. AppTest verifies 84.7 m recalculation and consistency of primary segment geometry and metrics. No screenshot was saved in the repository.
- No hosted app was accessed; local browser verification does not establish public deployment status.

## Phase 5.2 release-closure results

- Command: `.\.venv\Scripts\python.exe -m unittest discover tests -v`
- Result: **67 tests, 67 passed, 0 failures/errors, 0 skipped** in 50.957 s before the branding-only follow-up. A post-rebrand full run also passed: 67 tests in 45.585 s.
- Clean-lock run: `& "$envPath\Scripts\python.exe" -m unittest discover tests -v` after installing `requirements.txt` in the temporary Python 3.12.10 environment — **67 passed, 0 failures/errors, 0 skipped** in 50.304 s.
- ` .\.venv\Scripts\python.exe -m pip check`: PASS (`No broken requirements found`).
- `git diff --check`: PASS. Git emitted line-ending conversion notices only; no whitespace errors.
- Linux x86_64 Python 3.12 dependency-resolution dry-run: `python -m pip install --dry-run --ignore-installed --platform manylinux_2_28_x86_64 --platform manylinux2014_x86_64 --python-version 3.12 --implementation cp --abi cp312 --only-binary=:all: -r requirements.txt` — PASS; all pinned wheels resolved. This checks wheel availability/resolution, not a Cloud deployment.
- Secret scan of source/docs found no credential assignments. No Streamlit deployment URL is configured or present in the repository. The working changes remain unpublished, so hosted verification is blocked pending publication and the actual URL.
