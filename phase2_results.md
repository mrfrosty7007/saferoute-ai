# SafeRouteAI — Phase 2: Flood Risk & Vehicle Passability Modeling

## Scenario Passability Evaluation Table

```text
===========================================================================
                 SCENARIO PASSABILITY EVALUATION TABLE
===========================================================================
Scenario   | River (m) | Rain (mm/h) | Vehicle        | Closed (p<0.5) | Status
---------------------------------------------------------------------------
Dry        | 75.0      | 0.0         | ambulance      |    0.0% (   2) | Optimal (Green)
Dry        | 75.0      | 0.0         | fire_tender    |    0.0% (   2) | Optimal (Green)
Dry        | 75.0      | 0.0         | rescue_truck   |    0.0% (   2) | Optimal (Green)
---------------------------------------------------------------------------
Moderate   | 82.0      | 45.0        | ambulance      |   19.1% ( 906) | Moderate Impact
Moderate   | 82.0      | 45.0        | fire_tender    |    4.1% ( 196) | Moderate Impact
Moderate   | 82.0      | 45.0        | rescue_truck   |    2.3% ( 108) | Moderate Impact
---------------------------------------------------------------------------
Severe     | 87.0      | 90.0        | ambulance      |   44.5% (2110) | Heavy Inundation
Severe     | 87.0      | 90.0        | fire_tender    |   23.6% (1120) | Moderate Impact
Severe     | 87.0      | 90.0        | rescue_truck   |   16.6% ( 785) | Moderate Impact
---------------------------------------------------------------------------
```

### Model Checkpoint Validations
- **[1] Moderate Scenario Checkpoint**: Ambulance closures (**19.1%**) are over **8× higher** than Rescue Truck (**2.3%**). Passability differences are stark and clinically significant.
- **[2] Dry Scenario Checkpoint**: All vehicles operate at **0.0% closed** (nearly 100% green).
- **[3] Severe Scenario Checkpoint**: Ambulance closures reach **44.5%** (substantial red across riverfront and drainage basins), but key elevated arterial routes remain navigable.

---

## 3×3 Scenario & Vehicle Comparison Grid

![SafeRouteAI 3x3 Passability Grid](C:/Users/mahad/.gemini/antigravity-ide/brain/f068fffb-bcba-466f-8da1-715b002b6939/passability_3x3_grid.png)

---

## Technical Implementations & Architecture

1. **`is_bridge(data)` Classifier**:
   - Accurately parses string values (`'yes'`, `'viaduct'`), native lists, and stringified lists from GraphML (`"['yes', 'viaduct']"`).
   - Validated against exactly **20 bridge edges** in Daraganj.
2. **Topographic Depression Caching**:
   - Edge midpoints are indexed via `scipy.spatial.cKDTree` within a 300 m radius.
   - Depressions are cached to [`data/depressions.pkl`](file:///c:/1.Projects/SafeRouteAI/data/depressions.pkl), ensuring re-evaluations and UI slider updates execute in milliseconds without re-running spatial neighbor searches.
3. **Graph Copy & Enriched Edge Attributes**:
   - `passability()` writes `water_depth_cm`, `pass_probability_<vehicle>`, and `pass_probability` onto a copy of the graph, ready for consumption by Phase 3 (Dijkstra/A* routing).
4. **Sanity Assertions**:
   - `depth >= 0.0` strictly enforced across the network.
   - Verified monotonicity: $\frac{\partial p}{\partial \text{rain}} \le 0$ and $\frac{\partial p}{\partial \text{river}} \le 0$.
5. **Physical Modeling Note**:
   - Riverine flooding is modeled as $\max(0, \text{river\_level} - \text{elev\_min}) \times 100$ cm. This represents a simplified regional stage model (assuming backwater inundation on low terrain without requiring a full 2D hydrodynamic flow mesh).
