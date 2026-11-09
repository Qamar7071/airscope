import numpy as np
import pandas as pd
import pytest

from ml.uncertainty import (
    UncertaintyParams,
    VariogramFit,
    calibrate,
    fit_variogram,
    normalized_kriging_variance,
)


def test_kriging_variance_limits():
    t_lat = np.array([33.60, 33.60, 33.60])
    t_lon = np.array([73.00, 73.03, 73.30])
    rho = normalized_kriging_variance(t_lat, t_lon, [33.60], [73.00], range_km=3.0, nugget_ratio=0.0)
    assert rho[0] == pytest.approx(0.0, abs=1e-6)  # at a noise-free station
    assert rho[0] < rho[1] < rho[2] <= 1.0
    assert rho[2] > 0.99  # far away -> prior variance
    assert np.all(normalized_kriging_variance(t_lat, t_lon, [], [], 3.0, 0.3) == 1.0)


def test_nugget_keeps_variance_above_zero_at_station():
    rho = normalized_kriging_variance([33.6], [73.0], [33.6], [73.0], range_km=3.0, nugget_ratio=0.3)
    assert 0.0 < rho[0] < 0.6


def test_more_stations_never_increase_variance():
    t_lat = np.linspace(33.55, 33.75, 30)
    t_lon = np.linspace(72.95, 73.15, 30)
    one = normalized_kriging_variance(t_lat, t_lon, [33.6], [73.0], 3.0, 0.2)
    two = normalized_kriging_variance(t_lat, t_lon, [33.6, 33.7], [73.0, 73.1], 3.0, 0.2)
    assert np.all(two <= one + 1e-9)


def test_variogram_fit_recovers_known_parameters():
    true = VariogramFit(nugget=0.02, psill=0.1, range_km=4.0, method="truth")
    d = np.linspace(0.5, 15, 40)
    pairs = [{"distance_km": float(x), "semivariance": float(true.semivariance(x)), "n": 500} for x in d]
    fit = fit_variogram(pairs, total_variance=0.12, default_range_km=2.0)
    assert fit.method == "weighted_least_squares"
    assert fit.range_km == pytest.approx(4.0, rel=0.1)
    assert fit.nugget == pytest.approx(0.02, abs=0.01)


def test_variogram_falls_back_with_too_few_pairs():
    fit = fit_variogram([{"distance_km": 1.0, "semivariance": 0.1, "n": 100}], 0.2, 3.5)
    assert fit.method == "fallback" and fit.range_km == 3.5


def test_calibration_reaches_nominal_coverage_on_gaussian_residuals():
    rng = np.random.default_rng(1)
    rows = []
    for s in range(8):
        rho = 0.2 + 0.08 * s
        true_sigma = np.sqrt(0.01 + 0.2 * rho)  # spatial term the model must discover
        r = rng.normal(0.0, true_sigma, 400)
        y = 50.0 * np.exp(r)
        rows.append(pd.DataFrame({"station_id": f"S{s}", "y": y, "pred": 50.0, "sigma_model2": 0.01}))
    oof = pd.concat(rows, ignore_index=True)
    rho_by = {f"S{s}": 0.2 + 0.08 * s for s in range(8)}
    vario = VariogramFit(0.01, 0.2, 3.0, "test")
    params, report = calibrate(oof, rho_by, vario)
    assert params.spatial_var == pytest.approx(0.2, rel=0.25)
    cov90 = report["empirical_coverage"][report["levels"].index(0.9)]
    assert 0.85 <= cov90 <= 0.95
    assert report["model_only_coverage_90"] < 0.5  # model spread alone is badly over-confident here


def test_interval_is_ordered_and_non_negative():
    p = UncertaintyParams(scale=1.2, spatial_var=0.1)
    sigma = p.sigma_total(np.array([0.01, 0.05]), np.array([0.1, 0.9]))
    assert sigma[1] > sigma[0]
    lo, hi = p.interval(np.array([5.0, 80.0]), sigma, 0.9)
    assert np.all(lo >= 0) and np.all(lo < np.array([5.0, 80.0])) and np.all(hi > np.array([5.0, 80.0]))
    lo50, hi50 = p.interval(np.array([5.0, 80.0]), sigma, 0.5)
    assert np.all(hi50 < hi) and np.all(lo50 > lo)
