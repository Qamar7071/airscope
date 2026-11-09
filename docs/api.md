# AirScope REST API

Base URL: `http://127.0.0.1:8000/api` (the Vite dev server proxies `/api` to it).
All responses are JSON. Every data-bearing response includes a `provenance`
object that states whether the data are synthetic (offline demo) or live.

## Conventions

* **City ids**: `islamabad`, `lahore`, `karachi` (see `GET /cities`).
* **`time`**: `period` (average over the dataset period, default), `latest`, or an
  ISO-8601 timestamp listed by `GET /cities/{city}/timesteps`.
* **Grid arrays** (`layers.*`, `gap_index`, ...) cover *all* cells of the analysis grid
  in row-major order (row 0 = north, column 0 = west), with `null` outside the city
  boundary. Use `geometry` (`north`, `south`, `east`, `west`, `nrows`, `ncols`, `mask`)
  to place them.
* **Gap-index weights** (query parameters or a `weights` object): `w_coverage`,
  `w_uncertainty`, `w_pollution`, `w_population` (0-10, default 0.5) and `balance`
  (0-1, default 0.5).
* **Errors**: `{"error": "<code>", "message": "..."}` with HTTP 400 (invalid input),
  404 (unknown city/station), 503 (`model_not_ready`, includes the training `status`
  and a `Retry-After` header) or 500.

## Meta

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Status, version, data mode, live-mode configuration and the training state of every city's model |
| GET | `/sources` | Data sources, licences and attribution; air-quality standards used |
| GET | `/config` | Placement strategies, gap classes and UI defaults |

## Cities and data

| Method | Path | Description |
|---|---|---|
| GET | `/cities` | All cities with boundary, data mode and model status (primary city first) |
| GET | `/cities/{city}` | Details: domain area, grid size, dataset summary, full QC report, provenance, locality gazetteer, model summary |
| GET | `/cities/{city}/status` | Model training status (`ready`, `training`, `pending`, `error`, `no_data`) |
| POST | `/cities/{city}/train` | Queue retraining (HTTP 202) |
| GET | `/cities/{city}/stations?time=latest` | Stations with latest/selected-hour values, period mean, completeness, QC flags, AQI and held-out (LOSO) errors |
| GET | `/cities/{city}/stations/{id}/timeseries?hours=168` | Observed hourly PM2.5 with leave-one-station-out estimates and calibrated 90 % intervals |
| GET | `/cities/{city}/timesteps` | Hours with enough station data for snapshots, stations reporting per hour, period bounds |
| GET | `/cities/{city}/weather?hours=168` | Weather series, ventilation index and network-mean PM2.5 |

## Analyses

| Method | Path | Description |
|---|---|---|
| GET | `/cities/{city}/grid?time=period` | City-wide estimate: PM2.5, 90 % interval, uncertainty (absolute, relative, normalised), kriging variance, coverage, population, distance to nearest station, OSSE error map (demo, period view); summary statistics including residents per AQI category |
| GET | `/cities/{city}/gaps?w_coverage=0.5&...` | Monitoring Gap Index per cell, class labels, components, observation deficit, exposure need, class summary, network metrics and ranked blind-spot clusters (planning view, period average) |
| GET | `/cities/{city}/recommendations?k=5&strategy=coverage&...` | Recommended sites with reasons, before/after impact and the greedy diminishing-returns curve |
| POST | `/cities/{city}/simulate` | Impact of user-chosen hypothetical sites |
| POST | `/cities/{city}/osse` | Demo only: retrain with virtual stations at the given sites and measure the city-wide error change against the synthetic truth |
| GET | `/cities/{city}/metrics` | Computed evaluation: LOSO table vs baselines, per-station errors, random K-fold contrast, calibration, variogram, permutation importance, OSSE results, training metadata |

### Recommendation parameters

| Parameter | Default | Range | Meaning |
|---|---|---|---|
| `k` | 5 | 1-25 | number of new stations |
| `strategy` | `coverage` | `coverage`, `variance`, `population`, `random` | placement strategy |
| `min_spacing_km` | 2.0 | 0-20 | minimum distance between new sites |
| `min_station_distance_km` | 1.5 | 0-20 | minimum distance to existing stations |
| `min_population_density` | 200 | ≥ 0 | eligible cells need at least this many people per km² |
| `seed` | 0 | ≥ 0 | random strategy only |

## Examples

```bash
curl -s http://127.0.0.1:8000/api/health
```

```bash
curl -s "http://127.0.0.1:8000/api/cities/islamabad/recommendations?k=3&strategy=coverage&min_spacing_km=2"
```

```bash
curl -s -X POST http://127.0.0.1:8000/api/cities/islamabad/simulate -H "Content-Type: application/json" -d '{"sites": [{"lat": 33.62, "lon": 73.07}], "time": "period", "weights": {"w_coverage": 0.5, "w_uncertainty": 0.5, "w_pollution": 0.5, "w_population": 0.5, "balance": 0.5}}'
```

Abbreviated recommendation response:

```json
{
  "strategy": "coverage",
  "strategy_label": "Need-weighted coverage (greedy, submodular)",
  "eligible_cells": 1343,
  "sites": [
    {
      "rank": 1,
      "lat": 33.61585,
      "lon": 73.09686,
      "location": {"name": "Chaklala (Rawalpindi)", "distance_km": 0.7, "label": "0.7 km N of Chaklala (Rawalpindi)"},
      "pm25": 90.1,
      "aqi_category": "Unhealthy",
      "gap_index": 0.82,
      "population_density": 9213,
      "nearest_station_km": 5.0,
      "newly_covered_population": 106957,
      "reasons": ["Dense area: about 9,213 people/km² (more than 81% of the city)", "5.0 km from the nearest monitor (representativeness radius 2 km)", "..."]
    }
  ],
  "impact": {"before": {"need_weighted_coverage_pct": 31.2, "...": "..."}, "after": {"...": "..."}, "delta": {"uncertainty_reduction_pct": 10.2}},
  "curve": [{"k": 0, "need_weighted_coverage_pct": 31.2, "population_within_radius_pct": 23.1, "uncertainty_reduction_pct": 0.0}],
  "provenance": {"mode": "demo", "synthetic": true, "label": "Synthetic demo data"}
}
```

The values in this example come from the bundled synthetic demo and are shown
only to illustrate the response shape.
