import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestRegressor

from config import get_city
from data.dataset_service import DatasetService
from ml.features import (
    ALL_FEATURES,
    COORDINATE_FEATURES,
    FEATURE_RANGES,
    MODEL_FEATURES,
    model_features,
    FeatureBuilder,
    FeatureValidator,
    make_model_pipeline,
    validation_report,
)


@pytest.fixture(scope="module")
def ds():
    return DatasetService().get("islamabad")


def test_feature_list_covers_specification():
    required = {"latitude", "longitude", "temperature_c", "relative_humidity_pct", "wind_speed_ms", "surface_pressure_hpa",
                "boundary_layer_height_m", "elevation_m", "distance_to_center_km", "log_population_density", "month"}
    assert required <= set(ALL_FEATURES)
    assert {"hour_sin", "hour_cos", "doy_sin", "doy_cos", "wind_u", "wind_v"} <= set(MODEL_FEATURES)
    assert set(FEATURE_RANGES) == set(ALL_FEATURES)


def test_raw_coordinates_are_opt_in_model_inputs():
    assert not set(COORDINATE_FEATURES) & set(MODEL_FEATURES)
    assert model_features(False) == MODEL_FEATURES
    assert set(COORDINATE_FEATURES) <= set(model_features(True))


def test_time_features_are_cyclic_and_local(ds):
    b = FeatureBuilder(get_city("islamabad"))
    ts = pd.DatetimeIndex(["2025-11-10T19:00:00Z", "2025-11-10T18:59:00Z"])  # 00:00 and 23:59 local (UTC+5)
    tw = b.time_weather_features(ts, ds.weather)
    assert tw["hour_cos"].iloc[0] == pytest.approx(1.0)
    assert abs(tw["hour_sin"].iloc[0] - tw["hour_sin"].iloc[1]) < 0.01  # midnight neighbours stay close


def test_wind_components_follow_meteorological_convention(ds):
    b = FeatureBuilder(get_city("islamabad"))
    w = ds.weather.iloc[:1].copy()
    w["wind_speed_ms"] = 2.0
    w["wind_direction_deg"] = 0.0  # wind FROM the north blows southwards
    tw = b.time_weather_features(pd.DatetimeIndex(w["timestamp"]), w)
    assert tw["wind_v"].iloc[0] == pytest.approx(-2.0)
    assert tw["wind_u"].iloc[0] == pytest.approx(0.0, abs=1e-9)


def test_network_features_exclude_own_station():
    values = np.array([[10.0, 30.0, np.nan]])  # one hour, three stations
    d = np.array([[0.0, 1.0, 2.0], [1.0, 0.0, 1.0]])
    exclude = np.array([[True, False, False], [False, True, False]])
    mean, idw = FeatureBuilder.network_features(values, d, exclude)
    assert mean[0, 0] == pytest.approx(30.0)  # station 0 only sees station 1
    assert mean[0, 1] == pytest.approx(10.0)
    assert idw[0, 0] == pytest.approx(30.0)
    mean_all, _ = FeatureBuilder.network_features(np.array([[np.nan, np.nan, np.nan]]), d)
    assert np.isnan(mean_all).all()


def test_training_table_is_consistent(ds):
    b = FeatureBuilder(ds.city)
    ids = list(ds.training_stations["station_id"])
    tab = b.training_table(ds, ids)
    assert list(tab.X.columns) == ALL_FEATURES
    assert len(tab.X) == len(tab.y) == len(tab.station_id) == len(tab.timestamp)
    assert len(tab.y) == int(ds.obs_wide().notna().sum().sum())
    report = validation_report(tab.X)
    assert all(v["out_of_range"] == 0 for v in report.values())
    # static features are constant within a station
    first = tab.X[tab.station_id == ids[0]]
    assert first["elevation_m"].nunique() == 1 and first["log_population_density"].nunique() == 1


def test_validator_blanks_impossible_values():
    X = pd.DataFrame([[0.0] * len(ALL_FEATURES)], columns=ALL_FEATURES)
    X["relative_humidity_pct"] = 150.0
    X["temperature_c"] = np.inf
    X["month"] = 11
    out = FeatureValidator(columns=ALL_FEATURES).fit(X).transform(X)
    cols = {c: i for i, c in enumerate(ALL_FEATURES)}
    assert np.isnan(out[0, cols["relative_humidity_pct"]]) and np.isnan(out[0, cols["temperature_c"]])
    assert out[0, cols["month"]] == 11


def test_pipeline_handles_missing_values_and_empty_columns():
    rng = np.random.default_rng(0)
    X = pd.DataFrame(rng.random((200, len(MODEL_FEATURES))), columns=MODEL_FEATURES)
    X["month"] = 11
    X["boundary_layer_height_m"] = np.nan  # e.g. not provided by the weather source
    X.iloc[::7, 3] = np.nan
    y = 20 + 50 * X["elevation_m"].to_numpy()
    model = make_model_pipeline(RandomForestRegressor(n_estimators=10, random_state=0)).fit(X, y)
    pred = model.predict(X)
    assert np.isfinite(pred).all() and (pred > 0).all()
