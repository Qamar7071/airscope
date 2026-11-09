# AirScope backend

Flask API and machine-learning engine (Python 3.11). Runs fully offline on the bundled
synthetic demo; optionally uses OpenAQ v3 and Open-Meteo for live data.

## Setup and run

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-optional.txt
.venv/bin/python app.py
```

The API listens on http://127.0.0.1:8000 (`AIRSCOPE_PORT`, `AIRSCOPE_HOST`). Missing or
stale models are trained in a background thread (Islamabad first); `/api/health` reports
progress and model-dependent endpoints answer `503 model_not_ready` until then. If
`../frontend/dist` exists, the built UI is served from the same origin.

`requirements-optional.txt` installs XGBoost (`xgboost-cpu` on Linux/Windows, `xgboost`
on macOS, which may also need `brew install libomp`). Without it the ensemble uses two
members and everything else works.

## Commands

| Command | What it does |
|---|---|
| `python -m ml.train --city all [--profile fast]` | Train models (LOSO CV, calibration, importance, OSSE in demo mode) |
| `python -m ml.report` | Write `../docs/demo_results.md` from computed metrics |
| `python -m ml.ablation` | Reproduce the coordinate-feature ablation (demo mode) |
| `python -m data.demo_generator [--check]` | Regenerate (or verify) the deterministic synthetic demo data |
| `python -m pytest -q` | Run the test-suite (offline; trains one city with the fast profile into a temp dir) |

## Module map

| Module | Responsibility |
|---|---|
| `config.py` | Environment settings; city registry loaded from `datasets/city_boundaries.json` |
| `api/routes.py` | HTTP endpoints (see `../docs/api.md`) |
| `api/schemas.py` | Input validation (HTTP 400 on bad input) and JSON serialisation |
| `services/analysis_service.py` | Orchestrates datasets, models and analyses into payloads |
| `services/model_registry.py` | Loads current artifacts, detects stale ones (dataset fingerprint, schema version), trains in the background |
| `data/openaq_fetcher.py` | OpenAQ v3 client: locations, hourly sensor data, retries, licence capture |
| `data/weather_fetcher.py` | Open-Meteo client: forecast/archive, m/s units, boundary-layer-height fallback |
| `data/cache_manager.py` | Atomic JSON file cache with TTL and stale-entry fallback |
| `data/data_processor.py` | `CityDataset` and quality control with a full QC report |
| `data/dataset_service.py` | Demo/live/auto mode resolution and honest provenance |
| `data/demo_generator.py` | Synthetic nature run (OSSE), weather, surfaces, demo caches |
| `data/population_loader.py` | Population and elevation surfaces (bilinear sampling) |
| `data/sources.py` | Data sources, licences and attribution |
| `ml/features.py` | Feature engineering, validation, imputation pipeline |
| `ml/train.py` | Training pipeline and profiles |
| `ml/predict.py` | Ensemble, artifacts, grid predictor (snapshots and period averages) |
| `ml/uncertainty.py` | Variogram, kriging variance, calibration |
| `ml/evaluation.py` | Metrics |
| `ml/gaps.py` | Monitoring Gap Index, classes, network metrics, blind-spot clusters |
| `ml/sensor_placement.py` | Placement strategies, impact, curve, simulation |
| `ml/osse.py` | Synthetic-truth reconstruction scoring and placement benchmark |
| `ml/aqi.py` | US EPA 2024 AQI breakpoints |
| `geospatial/*` | Distances, grid, point-in-polygon, surfaces, gazetteer |

## Model artifacts

`models/<city>/` contains `model.joblib` (ensemble members, quantile models, feature
list), `metadata.json` (provenance, dataset fingerprint, uncertainty parameters, library
versions), `metrics.json` (all computed evaluation results), `cv_predictions.csv`
(held-out predictions for the station charts) and `period_grid.npz` (period-average
fields). Delete the folder, or run `make clean-models`, to retrain.

## Tests

The suite covers geospatial maths, QC rules, feature engineering, the live-API clients
(with recorded-shape fixtures and fake HTTP sessions, including fallback provenance),
uncertainty and calibration, the gap index's mathematical properties, placement
constraints and submodular behaviour, the API contract and an end-to-end fast training
run. It never touches the network and never modifies `models/`.
