# Rakshapath five-minute evaluator walkthrough

Use the local app started with `python -m streamlit run app.py`. The dashboard uses a cached Daraganj road graph and modeled hazard scenarios; it is not a live emergency-dispatch or forecasting service.

## 0:00–0:40 — Identify the study area and defaults

- Point out Daraganj, Prayagraj and the initial study-area preview map.
- Confirm the default pair: **Daraganj South → Daraganj North**.
- Explain that routes appear after selecting **Calculate routes**.

## 0:40–1:30 — Compare the three route objectives

- Keep Flood Inundation selected at rainfall 45 mm/h and river stage 82 m.
- Select Ambulance and calculate routes.
- Explain the blue primary as risk-aware time plus passability cost, orange as an alternate, and grey as shortest-distance baseline.
- Show distance, modeled travel-time estimate, reliability and backup overlap.
- State that the default backup now shares 21.4% of its edges with the primary. It takes about 1.5 minutes longer and has lower modeled reliability (15.83% vs 22.25%); it is an alternate, not a guaranteed safer independent route.

## 1:30–2:15 — Compare vehicle assumptions

- Select Fire Tender, calculate and observe its route metrics.
- Repeat with Rescue Truck.
- Explain that each vehicle uses a different modeled clearance/passability parameter; the displayed metric is a model output, not a vehicle certification.

## 2:15–3:00 — Change flood scenario

- Set river stage to 84.7 m and calculate again.
- Note that the input is accepted at 0.1 m precision and recalculation is tied to that exact value.
- The network-wide modeled depth changes; explain that the chosen route may remain unchanged when the current corridor stays preferable.

## 3:00–3:45 — Show alternate origin entry

- Switch Origin input to Coordinates and enter a point inside the Daraganj study bounds.
- Calculate again. Optionally pick a different registered landmark for Destination.
- Mention that values outside the study bounds or points too close together are rejected with a validation message.

## 3:45–4:30 — Inspect route risk

- Select the **Routes with risk** map view.
- Point out segment pass-probability coloring and the weakest segment indicator.
- Explain that route risk is modeled from cached elevation/road data and the selected scenario; the basemap is OpenStreetMap.
- Show the route elevation profile. Its samples are road-network node elevations; the connecting line is illustrative.

## 4:30–5:00 — Show earthquake scenario and limitations

- Select **Earthquake Debris (Scenario Simulation)**, keep the configured MMI, distance and debris factor, then calculate.
- Point out the simulated-data banner and label.
- Close by stating that the application has no live flood observations, real-time traffic, earthquake forecast, hospital-capacity feed or dispatch integration.
