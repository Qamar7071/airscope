# AirScope demo results (generated)

_Generated 2026-11-08 17:40 UTC by `python -m ml.report` from `backend/models/*/metrics.json`._

> **All numbers below are computed on SYNTHETIC demo data** (AirScope's documented OSSE nature run).
> They show how the pipeline behaves on realistic simulated data. They are **not** a validation
> against real-world measurements and must not be quoted as real-world accuracy.

## 1. Leave-one-station-out (LOSO) validation

Each station is predicted by a model trained without it. RMSE in µg/m³.

| City | Stations | Ensemble RMSE | Ensemble R² | IDW RMSE | Network-mean RMSE | Ensemble beats best baseline? | Random K-fold optimism |
|---|---|---|---|---|---|---|---|
| Islamabad | 7 | 27.4 | 0.52 | 23.7 | 23.1 | no | 62% |
| Lahore | 7 | 44.5 | 0.88 | 47.5 | 43.9 | no | 28% |
| Karachi | 7 | 10.1 | 0.82 | 12.9 | 13.3 | yes | 29% |

_Random K-fold optimism_: how much lower the RMSE looks with a non-spatial random split - the reason AirScope reports LOSO.

## 2. Uncertainty calibration (nested LOSO)

| City | Coverage of 90% intervals | Coverage of 50% intervals | Tree-model spread only (90%) | Variogram range |
|---|---|---|---|---|
| Islamabad | 86% | 42% | 43% | 6.4 km (weighted_least_squares) |
| Lahore | 89% | 45% | 66% | 3.5 km (fallback) |
| Karachi | 88% | 53% | 75% | 4.0 km (fallback) |

## 3. OSSE: city-wide reconstruction against the synthetic truth

| City | Ensemble RMSE | IDW RMSE | Population-weighted RMSE | Cells inside 90% interval | Uncertainty-error Spearman | Spatial pattern correlation |
|---|---|---|---|---|---|---|
| Islamabad | 22.2 | 23.2 | 25.8 | 93% | 0.39 | 0.39 |
| Lahore | 39.4 | 47.2 | 42.6 | 89% | -0.00 | 0.46 |
| Karachi | 13.9 | 14.2 | 15.2 | 85% | 0.18 | 0.61 |

## 4. OSSE: city-wide error reduction from new stations

Virtual stations sample the synthetic truth; the ensemble is retrained; city-wide RMSE is re-measured.

| City | New stations | AirScope coverage | AirScope kriging variance | Population heuristic | Random (mean ± sd) |
|---|---|---|---|---|---|
| Islamabad | 5 | 17.8% (beats 2/5) | 22.1% (beats 3/5) | 18.8% (beats 2/5) | 16.5% ± 9.6 |
| Lahore | 5 | -3.9% (beats 2/5) | -10.7% (beats 1/5) | 2.8% (beats 4/5) | -2.7% ± 6.3 |
| Karachi | 5 | 18.9% (beats 5/5) | 15.8% (beats 5/5) | 6.6% (beats 5/5) | 3.4% ± 3.0 |

See `docs/methodology.md` for how each number is computed and for the limitations of these experiments.
