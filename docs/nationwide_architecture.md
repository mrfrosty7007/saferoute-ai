# Rakshapath — Nationwide Regional Architecture

## 1. Architectural Overview & Philosophy

**Rakshapath** is an AI-assisted emergency routing and disaster-response decision platform. Expanding from the initial Daraganj, Prayagraj pilot toward nationwide India coverage requires balancing geographic reach with strict cloud runtime constraints.

### Core Architecture Invariant: Bounded Regional Graphs
The nationwide road network is too large to treat as one bundled application asset. This project uses region-specific graph assets, but it does not claim a measured national graph size or a guaranteed memory requirement for any hosting tier.

**Rakshapath solves this through a modular, on-demand Regional Architecture:**
1. **Administrative Catalog & Registry**: A lightweight registry of the states, districts, and study regions currently declared in `saferoute/regions/registry.py`. It is an extensible subset, not a complete catalog of India.
2. **On-Demand Dynamic Asset Loading**: Graph assets (`.graphml` / `.pkl`) and precomputed topographic depression models are loaded into memory only when an emergency route is requested in that specific study area.
3. **Regional Engine Cache**: The `RegionalEngineManager` retains at most two engine entries and calls garbage collection after eviction. This bounds its own cache entries, not process RSS: active requests, Python objects, native libraries, and allocator behavior affect total memory. No deployment memory ceiling is claimed.
4. **Honest Coverage Status**: Nationwide-capable architecture is strictly distinguished from nationwide data availability. Daraganj is the only calibrated hazard-model pilot. Varanasi's checked-in OSM road extract is usable for a synthetic demo only; its terrain/elevation and hazard impacts are dummy values. Other declared regions remain `UNAVAILABLE`.

```
                              [ India Nationwide Catalog ]
                                            │
                    ┌───────────────────────┴───────────────────────┐
             [ Uttar Pradesh ]                               [ Maharashtra ]
                    │                                               │
             [ Prayagraj / Varanasi ]                          [ Mumbai Suburban ]
                    │                                               │
       ┌────────────┴──────────┐                           [ Kurla Mithi Basin ]
       │                       │                               Status: UNAVAILABLE
 [ Daraganj Pilot ]     [ Varanasi Demo ]                    Assets: Not yet ingested
 SUPPORTED_BUNDLED       SUPPORTED_LOCAL
 Validated flood         OSM roads; dummy 50 m elevations
 model                   and synthetic hazard outputs
```

---

## 2. Administrative Hierarchy & Region Models

Defined in [`saferoute/regions/models.py`](../saferoute/regions/models.py) and [`saferoute/regions/registry.py`](../saferoute/regions/registry.py):

### Region Lifecycle Status (`RegionStatus`)
- `SUPPORTED_BUNDLED`: Fully ingested, validated, and packaged with production assets. Serves as the golden regression baseline (`daraganj_prayagraj`).
- `SUPPORTED_LOCAL`: Road graph ingested, locally stored, and routable. Hazard and terrain validation are region-specific; routable does not mean a calibrated emergency model is available.
- `PARTIAL`: Ingested with limitations (e.g., road network present, but elevation or flood depression model pending).
- `UNAVAILABLE`: Planned catalog entry. Explicitly non-routable until ingestion and verification are performed.

### Geodesic Latitude Scaling
Because India spans from latitude ~8°N (Kanyakumari) to ~37°N (Kashmir), the distance per degree of longitude varies significantly:
$$\Delta x_{\text{meters}} = \Delta \text{lon} \times (111,320 \times \cos(\text{lat}_{\text{center}}))$$
$$\Delta y_{\text{meters}} = \Delta \text{lat} \times 111,320$$
Every `RegionMetadata` instance dynamically calculates its regional metric projection factors based on its local `center_lat`, eliminating distance distortion outside Uttar Pradesh.

Coordinate requests must first lie inside the region's explicit bounding box. They are then snapped only when the nearest road is within the region's configurable `snap_tolerance_m` (500 m by default); otherwise routing returns a clear error.

### Current routeable assets
- **Daraganj, Prayagraj** (`SUPPORTED_BUNDLED`): validated pilot graph and elevation/depression assets.
- **Varanasi Ghats** (`SUPPORTED_LOCAL`, demo only): OpenStreetMap extract timestamped `2026-10-11T11:39:11Z`; the retained largest strongly connected component has 5,029 nodes and 12,647 directed edges. Every node uses a flat dummy elevation of 50 m. The app labels the region as demo-only and marks hazard/passability/reliability output synthetic. No flood, earthquake, cyclone, landslide, or wildfire model is calibrated for Varanasi.
- **Mumbai Kurla** (`SUPPORTED_LOCAL`, demo only): BBBike Bombay city extract, spatially clipped to the corridor and 0.01° context; retained largest strongly connected component has 20,685 nodes and 49,281 directed edges. **Delhi Yamuna** (`SUPPORTED_LOCAL`, demo only): BBBike New Delhi extract, clipped the same way; 16,948 nodes and 44,507 directed edges. Both use flat dummy 50 m elevations and synthetic hazard/passability/reliability output. Their `metadata.json` files record the source URL, retrieval time, compressed-source SHA-256, clip bounds, and ODbL attribution. BBBike did not include an exact OSM source snapshot timestamp with these downloads.
- Chennai, Bengaluru, and Guwahati still have no checked-in road graph and remain unavailable.

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
   - The generic ingestion pipeline generates `metadata.json` with the ingestion timestamp and duration, graph counts, removed-node and elevation-fill counts, elevation summary, bridge/tunnel counts, actual graph bounds, a general OSMnx provenance label, and OSM attribution. It does not automatically capture a source-data OSM timestamp, DEM source, or validation checksums. Varanasi separately records its OSM snapshot timestamp. Mumbai and Delhi record the source download URL, retrieval time, compressed-source checksum, clip bounds, ODbL attribution, and the fact that the exact OSM snapshot time was not supplied. All three demo assets explicitly identify their dummy elevation source.

---

## 4. How to Add a New State, District, or Study Area

### Step 1: Add Entry to Registry Manifest
Open [`saferoute/regions/registry.py`](../saferoute/regions/registry.py) and add a new `RegionMetadata` declaration in `_BUILTIN_REGIONS`:

```python
RegionMetadata(
    region_id="example_city_corridor",
    display_name="Example City Corridor",
    state="Example State",
    district="Example District",
    city="Example City",
    center_lat=20.0000,
    center_lon=75.0000,
    radius_meters=2500.0,
    bounds=BoundingBox(
        min_lat=19.980, max_lat=20.020,
        min_lon=74.980, max_lon=75.020,
    ),
    graph_file="data/regions/example_city_corridor/graph.graphml",
    depressions_file="data/regions/example_city_corridor/depressions.pkl",
    status=RegionStatus.UNAVAILABLE,  # Mark UNAVAILABLE until ingested
    status_description="Example area; route only after road graph and bounds are checked.",
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
Set a region to a routable status only after its road graph and bounds are verified. That enables route demonstrations, not calibrated hazard decisions: if terrain or hazard models are placeholders, label every associated input, profile, impact, and reliability result synthetic in the registry and UI. The validation-only CLI checks asset presence, not semantic completeness or safety.

---

## 5. Hazard Models & Integrity Disclosure

| Hazard Model | Status | Description | Limitations |
| :--- | :--- | :--- | :--- |
| **Monsoon Flood** | **Implemented (Physics Model)** | Hydraulic depression ponding, gauge-relative river stage, rainfall runoff, vehicle-specific water depth clearance curves. | Relies on precomputed static depression terrain and uniform rainfall assumptions. Does not incorporate 2D hydrodynamic flow equations. |
| **Earthquake Debris** | **Synthetic Demo** | Dummy MMI and debris inputs drive a stylized edge-impact score. | Not an observation, forecast, seismological prediction, structural-collapse forecast, or emergency safety assessment. |
| **Cyclone** | **Synthetic Demo** | Dummy wind/rain inputs drive an illustrative edge-impact index. | No cyclone, surge, or weather observations; not calibrated or suitable for emergency decisions. |
| **Landslide** | **Synthetic Demo** | Dummy rainfall/susceptibility inputs and a simple graph-slope proxy drive an illustrative edge-impact index. | No landslide inventory or warning data; not calibrated or suitable for emergency decisions. |
| **Wildfire** | **Synthetic Demo** | Dummy intensity/distance inputs and available map-tag proxies drive an illustrative edge-impact index. | No active fire perimeter or detection data; not calibrated or suitable for emergency decisions. |

All synthetic demo controls and outputs are labeled in the dashboard. They demonstrate how scenario inputs can alter route selection; they do not represent real hazard likelihood, segment passability, reliability, or safe emergency routes. ETA remains a graph-based estimate without live traffic.

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
