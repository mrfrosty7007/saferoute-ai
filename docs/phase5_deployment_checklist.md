# Rakshapath Phase 5 deployment checklist

## Local or clean-environment setup

1. Use Python 3.12 (the repository `.python-version` specifies 3.12; Python 3.12.10 was used for verification).
2. From the repository root, create an isolated environment and install dependencies:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   python -m pip check
   ```

3. Confirm the tracked runtime inputs exist:

   ```powershell
   Test-Path data\graph.graphml
   Test-Path data\depressions.pkl
   Test-Path .streamlit\config.toml
   ```

   The graph and depression cache are required for cached offline routing. They are loaded via paths rooted at the package location. The app does not require a user API key for the default landmark workflow.

4. Start from the repository root:

   ```powershell
   python -m streamlit run app.py
   ```

   For a headless check or service environment:

   ```powershell
   python -m streamlit run app.py --server.headless true --server.port 8501
   Invoke-WebRequest http://127.0.0.1:8501/_stcore/health
   ```

5. On first load, verify the benchmark default is Daraganj South → Daraganj North, choose a vehicle and numeric hazard inputs, then select **Calculate routes**. The preview map is shown before calculation.

## Configuration and data

- `.streamlit/config.toml` sets the theme and headless mode. No application secrets are required for the default workflow.
- `EMERGENCY_ENGINE` is an optional Python module factory override; leave it unset for the production adapter.
- Keep `data/graph.graphml` and `data/depressions.pkl` present and together. The depression cache has schema, edge-key and graph-fingerprint checks.
- `cache/` is an optional ignored OSM ingestion cache. Runtime route generation uses the checked-in graph and depression assets; re-running ingestion is not part of normal startup.
- The map uses OpenStreetMap tiles from the browser; a browser with network access is needed to display those tiles. Local health success alone does not verify map tile access.
- `requirements.txt` includes `requirements-lock.txt`, so the Community Cloud recognized dependency file installs the exact pinned package versions. The lock pins transitive versions without hashes or platform wheels. Avoid upgrading packages during a release-only rebuild.
- The repository remote is `mrfrosty7007/saferoute-ai`; use branch `integration/ui-backend` and entrypoint `app.py` when creating the Community Cloud app. Local changes are not available to Cloud until they are pushed to that branch after review.
- Select Python 3.12 in Community Cloud Advanced settings. Required checked-in data assets are `data/graph.graphml` and `data/depressions.pkl`; `data/elevations.json` is also included. `.streamlit/config.toml` contains app theme/headless settings. The default routing workflow requires no secrets or API keys; optional place search contacts Nominatim and does not use a credential.
- To deploy: create the Community Cloud app from that repository, choose branch `integration/ui-backend`, set main file path `app.py`, and select Python 3.12. Keep the repo root as working directory. Community Cloud reads `requirements.txt`, which now includes the lock. Its deployment documentation covers repository layout, dependency files and configuration: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization and https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies.
- After deployment, copy the actual URL from the Cloud workspace (do not infer it). Open it in a browser, verify startup and the health/status display, calculate the default benchmark routes, check the risk-view toggle and elevation profile, change stage to 84.7 m and recalculate, then provide the actual URL for hosted verification. Check Cloud build logs and confirm required assets if startup fails.

## Troubleshooting

| Symptom | Check |
|---|---|
| Import error at startup | Activate the intended venv and rerun `python -m pip install -r requirements.txt` then `python -m pip check`. |
| Graph or depression asset missing | Run the three `Test-Path` checks above. Do not silently replace missing data with an empty graph. |
| No route for selected coordinates/scenario | Confirm points are in the Daraganj study bounds and separated by at least 50 m; retry a benchmark landmark pair and lower hazard values. The interface should report the routing error. |
| Search-place input fails | Use a registered landmark or coordinate input; place search requires the external geocoding service. |
| Folium basemap blank | Check browser network access to OpenStreetMap tiles; route geometries can still be calculated locally. |
| Low or zero reliability | Treat this as a modeled passability result for the selected scenario, not a guarantee or live safety assessment. |

## Verification status

- Clean Python 3.12 dependency installation: PASS (Python 3.12.10, with lock included through `requirements.txt`).
- Clean headless startup and health endpoint: PASS (local port 8766).
- Phase 5.1 full tests: PASS, 67/67; `git diff --check`: PASS.
- Local browser map and risk-toggle check: PASS.
- Release closure: the exact lock resolves Linux x86_64 Python 3.12 wheels; protobuf is pinned below 6 to match Streamlit Community Cloud guidance. Full working-tree suite, `pip check`, and `git diff --check` are recorded in `phase5_test_report.md`.
- Hosted deployment: NOT VERIFIED; no URL is configured or supplied, and the local changes have not been pushed or deployed.
