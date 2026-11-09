"""Evaluation metrics, synthetic data generator, and the training pipeline end to end."""
import json

import numpy as np
import pytest

from conftest import TEST_CITY
from ml.aqi import pm25_category, pm25_to_aqi
from ml.evaluation import interval_coverage, regression_metrics, skill_score, spearman


def test_regression_metrics_exact():
    m = regression_metrics([1, 2, 3, 4], [1, 2, 3, 6])
    assert m["rmse"] == pytest.approx(1.0) and m["mae"] == pytest.approx(0.5) and m["bias"] == pytest.approx(0.5)
    assert m["r2"] == pytest.approx(1 - 4 / 5)
    w = regression_metrics([1, 2], [2, 2], weights=[3, 1])
    assert w["mae"] == pytest.approx(0.75)
    assert regression_metrics([], [])["rmse"] is None
    assert skill_score(8.0, 10.0) == pytest.approx(0.2)
    assert interval_coverage([1, 5, 9], [0, 0, 0], [2, 6, 8]) == pytest.approx(2 / 3, abs=1e-4)
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)


@pytest.mark.parametrize("c, aqi, cat", [(0.0, 0, "Good"), (9.0, 50, "Good"), (9.1, 51, "Moderate"), (35.4, 100, "Moderate"),
                                         (35.5, 101, "Unhealthy for Sensitive Groups"), (55.5, 151, "Unhealthy"),
                                         (125.5, 201, "Very Unhealthy"), (225.5, 301, "Hazardous"), (325.4, 500, "Hazardous")])
def test_aqi_breakpoints_2024(c, aqi, cat):
    assert pm25_to_aqi(c) == aqi and pm25_category(c) == cat


def test_aqi_handles_invalid_values():
    assert pm25_to_aqi(None) is None and pm25_to_aqi(-1) is None and pm25_category(float("nan")) is None


def test_demo_generator_is_deterministic_and_consistent():
    from data.demo_generator import build_demo_dataset, demo_cache_path, get_nature_run

    a = build_demo_dataset("islamabad")
    b = build_demo_dataset("islamabad")
    assert a["observations"]["values"] == b["observations"]["values"]
    with open(demo_cache_path("islamabad"), encoding="utf-8") as fh:
        bundled = json.load(fh)
    assert bundled["observations"]["values"] == a["observations"]["values"], "bundled demo cache is out of date"
    assert bundled["provenance"]["synthetic"] is True
    nature = get_nature_run("islamabad")
    st = bundled["stations"][0]
    truth = nature.pm25([st["latitude"]], [st["longitude"]])[:, 0]
    obs = np.array([np.nan if v is None else v for v in bundled["observations"]["values"][st["id"]]], dtype=float)
    ok = np.isfinite(obs) & (obs > 0) & (obs < 1000)
    ratio = np.median(obs[ok] / truth[ok])
    assert 0.9 < ratio < 1.1  # stations sample the nature run (plus noise)
    assert (truth > 0).all()


def test_training_artifacts_and_honest_metrics(trained_city, settings):
    from ml.predict import CityModel

    m = trained_city
    assert m["provenance"]["synthetic"] is True and "SYNTHETIC" in m["honesty_note"]
    names = [row["model"] for row in m["loso"]["models"]]
    assert names[0] == "AirScope ensemble" and any(n.startswith("Baseline") for n in names)
    assert isinstance(m["loso"]["ensemble_beats_best_baseline"], bool)
    assert m["calibration"]["levels"] == [0.5, 0.8, 0.9, 0.95]
    assert m["variogram"]["range_km"] > 0
    model = CityModel.load(CityModel.dir_for(settings.models_dir, TEST_CITY))
    assert model.metadata["dataset_fingerprint"] and model.params.calibrated
    assert model.period is not None and np.isfinite(model.period["pm25_mean"]).all()
    assert len(model.cv_predictions) == m["data"]["n_observations"]


def test_grid_predictor_produces_valid_fields(trained_city, settings):
    from config import get_city
    from data.dataset_service import DatasetService
    from geospatial.city_grid import get_city_grid
    from ml.features import get_feature_builder
    from ml.predict import CityModel, GridPredictor

    city = get_city(TEST_CITY)
    model = CityModel.load(CityModel.dir_for(settings.models_dir, TEST_CITY))
    pred = GridPredictor(model, DatasetService().get(TEST_CITY), get_feature_builder(city), get_city_grid(city))
    field = pred.snapshot(pred.latest_timestamp())
    assert field.pm25.shape == (get_city_grid(city).n_inside,)
    assert np.all(field.lower <= field.pm25) and np.all(field.pm25 <= field.upper)
    assert np.all((field.rho >= 0) & (field.rho <= 1))
    # the spatial (kriging) term grows away from stations; for a fixed model spread the total
    # uncertainty is therefore never smaller far from stations than next to them
    from geospatial.distance import nearest_distance_km

    d, _ = nearest_distance_km(pred.grid.inside_lat, pred.grid.inside_lon, pred.st_lat, pred.st_lon)
    assert field.rho[d > 6].mean() > field.rho[d < 1].mean()
    sm2 = np.full(2, float(np.median(field.sigma_model2)))
    near_far = model.params.sigma_total(sm2, np.array([field.rho[d < 1].mean(), field.rho[d > 6].mean()]))
    assert near_far[1] >= near_far[0] and model.params.spatial_var >= 0
