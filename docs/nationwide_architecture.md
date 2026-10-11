# Rakshapath — Nationwide Regional Architecture

## 1. Architectural Overview & Philosophy

**Rakshapath** is an AI-assisted emergency routing and disaster-response decision platform. Expanding from the initial Daraganj, Prayagraj pilot toward nationwide India coverage requires balancing geographic reach with strict cloud runtime constraints.

### Core Architecture Invariant: Bounded Regional Graphs
The nationwide road network is too large to treat as one bundled application asset. This project uses region-specific graph assets, but it does not claim a measured national graph size or a guaranteed memory requirement for any hosting tier.

**Rakshapath solves this through a modular, on-demand Regional Architecture:**
1. **Administrative Catalog & Registry**: A lightweight registry of the states, districts, and study regions currently declared in `saferoute/regions/registry.py`. It is an extensible subset, not a complete catalog of India.
2. **On-Demand Dynamic Asset Loading**: Graph assets (`.graphml` / `.pkl`) and precomputed topographic depression models are loaded into memory only when an emergency route is requested in that specific study area.
3. **Regional Engine Cache**: The `RegionalEngineManager` retains at most two engine entries and calls garbage collection after eviction. This bounds its own cache entries, not process RSS: active requests, Python objects, native libraries, and allocator behavior affect total memory. No deployment memory ceiling is claimed.
4. **Honest Coverage Status**: Nationwide-capable architecture is strictly distinguished from nationwide data availability. Regions without validated, ingested assets are explicitly marked `UNAVAILABLE` or `PARTIAL`, preventing misleading route claims.

```
                              [ India Nationwide Catalog ]
                                            │
                    ┌───────────────────────┴───────────────────────┐
             [ Uttar Pradesh ]                               [ Maharashtra ]
                    │                                               │
             [ Prayagraj ]                                    [ Mumbai Suburban ]
                    │                                               │
     [ Daraganj Riverfront Pilot ]                           [ Kurla Mithi Basin ]
       Status: SUPPORTED_BUNDLED                               Status: UNAVAILABLE
       Assets: data/graph.graphml + depressions.pkl              Assets: Not yet ingested
       (1,823 nodes, 4,740 edges)
```

---

## 2. Administrative Hierarchy & Region Models

Defined in [`saferoute/regions/models.py`](../saferoute/regions/models.py) and [`saferoute/regions/registry.py`](../saferoute/regions/registry.py):

### Region Lifecycle Status (`RegionStatus`)
- `SUPPORTED_BUNDLED`: Fully ingested, validated, and packaged with production assets. Serves as the golden regression baseline (`daraganj_prayagraj`).
- `SUPPORTED_LOCAL`: Ingested, validated, and stored in the local data directory. Routable.
- `PARTIAL`: Ingested with limitations (e.g., road network present, but elevation or flood depression model pending).
- `UNAVAILABLE`: Planned catalog entry. Explicitly non-routable until ingestion and verification are performed.

### Geodesic Latitude Scaling
Because India spans from latitude ~8°N (Kanyakumari) to ~37°N (Kashmir), the distance per degree of longitude varies significantly:
$$\Delta x_{\text{meters}} = \Delta \text{lon} \times (111,320 \times \cos(\text{lat}_{\text{center}}))$$
$$\Delta y_{\text{meters}} = \Delta \text{lat} \times 111,320$$
Every `RegionMetadata` instance dynamically calculates its regional metric projection factors based on its local `center_lat`, eliminating distance distortion outside Uttar Pradesh.

Coordinate requests must first lie inside the region's explicit bounding box. They are then snapped only when the nearest road is within the region's configurable `snap_tolerance_m` (500 m by default); otherwise routing returns a clear error.

---

## 3. Data Ingestion & Validation Pipeline

Defined in [`saferoute/ingestion/pipeline.py`](../saferoute/ingestion/pipeline.py) and exposed to callers as a Python API; the inspection CLI is [`scripts/ingest_region.py`](../scripts/ingest_region.py).

### Ingestion Workflow
1. **OSM Network Preparation**: The pipeline library processes a supplied road graph. The current `scripts/ingest_region.py` CLI lists catalog entries and validates assets; it does not download or ingest a new region. Obtain and prepare source data offline under the data provider's terms before calling the pipeline API.
2. **Topology & Connectivity Validation**:
   - Asserts node count is between 20 and 60,000 nodes (preventing runaway memory footprints).
   - Extracts the Largest Strongly Connected Component (SCC), ensuring no isolated disconnected road segments.
3. **Elevation Model Normalization**:
   - Accepts node elevations supplied by the caller; this pipeline does not fetch or validate a particular DEM source.
   - Replaces missing/null elevations using topological neighbor interpolation or a regional fallback value.
   - Enforces edge `elev_min` attribute for flood water depth computation.
4. **Topographic Depression Precomputation**:
   - Evaluates road segment depressions within a configurable radius (default: 300m).
   - Generates schema v2 `depressions.pkl` for fast, real-time flood water depth calculations.
5. **Metadata Provenance**:
   - Generates `metadata.json` with the ingestion timestamp and duration, graph counts, removed-node and elevation-fill counts, elevation summary, bridge/tunnel counts, actual graph bounds, a general OSMnx provenance label, and OSM attribution. It does not record the source-data OSM timestamp, a specific DEM source, or validation checksums.

---

## 4. How to Add a New State, District, or Study Area

### Step 1: Add Entry to Registry Manifest
Open [`saferoute/regions/registry.py`](../saferoute/regions/registry.py) and add a new `RegionMetadata` declaration in `_BUILTIN_REGIONS`:

```python
RegionMetadata(
    region_id="varanasi_ghats",
    display_name="Varanasi Ghats & Old City",
    state="Uttar Pradesh",
    district="Varanasi",
    city="Varanasi",
    center_lat=25.3176,
    center_lon=83.0064,
    radius_meters=2500.0,
    bounds=BoundingBox(
        min_lat=25.295, max_lat=25.340,
        min_lon=82.980, max_lon=83.030,
    ),
    graph_file="data/regions/varanasi_ghats/graph.graphml",
    depressions_file="data/regions/varanasi_ghats/depressions.pkl",
    status=RegionStatus.UNAVAILABLE,  # Mark UNAVAILABLE until ingested
    status_description="Planned pilgrimage flood corridor along the Ganges.",
    data_provenance="OpenStreetMap contributors via OSMnx",
)
```

### Step 2: Ingest and Validate Graph Data
The current CLI only lists and validates already prepared assets. It does not ingest or download a new region:
```bash
python scripts/ingest_region.py --list
```
To validate an existing graph without downloading:
```bash
python scripts/ingest_region.py --region varanasi_ghats --validate-only
```
New regional graph preparation currently requires calling `RegionIngestionPipeline.process_and_save` from offline Python code with a supplied graph and elevation data.

### Step 3: Update Region Status
Only after required assets exist and their region bounds, graph, elevations, and hazard calibration have been verified should the registry status be changed to a routable value. The validation-only CLI currently checks asset presence, not semantic completeness or safety.

---

## 5. Hazard Models & Integrity Disclosure

| Hazard Model | Status | Description | Limitations |
| :--- | :--- | :--- | :--- |
| **Monsoon Flood** | **Implemented (Physics Model)** | Hydraulic depression ponding, gauge-relative river stage, rainfall runoff, vehicle-specific water depth clearance curves. | Relies on precomputed static depression terrain and uniform rainfall assumptions. Does not incorporate 2D hydrodynamic flow equations. |
| **Earthquake Debris** | **Exploratory Scenario** | Distance-attenuated Modified Mercalli Intensity (MMI), structural vulnerability debris probabilities. | Stylized engineering vulnerability proxy for emergency simulations; not a seismological prediction or structural collapse forecast. |
| **Cyclone / Landslide / Wildfire** | **Unimplemented** | Not implemented. Clearly labeled in UI and rejected if requested. | Will not fabricate synthetic routing for unmodeled hazards. |

---

## 6. Empirical Benchmark Results (Daraganj Golden Baseline)

Measured on actual graph data using [`scripts/run_benchmarks.py`](../scripts/run_benchmarks.py) evaluating **300 deterministic OD pairs sampled with seed 42 ($\ge 1.5$ km apart)** under a severe monsoon flood scenario (50 mm/h rainfall, 84.7 m river stage):

| Benchmark Metric | Ambulance | Rescue Truck |
| :--- | :--- | :--- |
| **Pairs Evaluated** | 300 | 300 |
| **Routing Success Rate** | **100.0%** (0 unreachable) | **100.0%** (0 unreachable) |
| **Region Loading Time** | **0.674 s** | **0.674 s** |
| **Traced Python Peak Allocation (legacy run)** | **27.26 MiB** | **27.26 MiB** |
| **First-Route Latency** | 105.34 ms | 666.62 ms |
| **Subsequent Route Mean Latency** | 607.65 ms | 521.98 ms |
| **Subsequent Route p95 Latency** | 872.35 ms | 852.34 ms |
| **Mean Primary SafeRoute Reliability** | **0.52%** | **75.50%** |
| **Mean Conventional Baseline Reliability** | **0.00%** | **62.58%** |
| **Mean Primary-Backup Corridor Overlap** | **8.40%** | **4.66%** |
| **Elevation Data Coverage** | **100.0%** | **100.0%** |
| **Depression Data Coverage** | **100.0%** | **100.0%** |

*These are recorded results from a single legacy run. Its 27.26 MiB memory value came from `tracemalloc`; process RSS was not recorded. The JSON artifact labels this limitation. A single run is not a memory ceiling. Artifacts: `data/benchmark_results_daraganj_prayagraj.json` and `data/benchmark_plot_daraganj_prayagraj.png`.*

---

## 7. Cloud Deployment & Resource Observations

### Render Web Service Compatibility
- **Entrypoint**: `python -m streamlit run app.py --server.address 0.0.0.0 --server.port $PORT`
- **Memory Footprint**: Not measured as process RSS in the deployment environment. Benchmark output now records traced Python allocations and, where supported, process RSS snapshots around asset loading; these are observational measurements, not guarantees.
- **Cache Policy**: `RegionalEngineManager` retains at most two engine entries and calls `gc.collect()` after eviction. Active requests and runtime libraries can retain additional memory.
- **Startup**: The app loads regional assets on demand. Startup timing depends on the deployment environment and has no published guarantee.

#### Local Memory Measurement Example

A one-pair benchmark sanity run on Windows 11 x64 with Python 3.12.10 measured 154.64 MiB process working set before engine loading and 187.43 MiB after loading (32.79 MiB delta); `tracemalloc` reported 27.26 MiB of Python allocations during that load. The RSS snapshots use Windows `GetProcessMemoryInfo` / `WorkingSetSize`. Python and benchmark dependencies were already imported before the first snapshot. This small local run is illustrative only, excludes other deployment services, and does not predict or guarantee Render memory use.

#### Browser Chart Warning Note

During local browser retesting, Vega logged transient “Infinite extent” warnings for `Distance (km)` and `Elevation (m)` while the elevation chart was mounting after route calculation. The completed primary profile displayed 34 finite road-node samples, spanning 0–2.279 km and 90–99 m, and the route table contained finite metrics. No malformed profile data was found; the warning appears to occur during the chart's interim empty-data initialization, not from the completed data. No chart code change was made.
