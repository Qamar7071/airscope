import numpy as np
import pandas as pd
import pytest

from data.data_processor import CityDataset, DataProcessor
from data.dataset_service import DatasetService

from conftest import make_test_city


def _dataset(values: dict[str, list], weather: pd.DataFrame | None = None, stations=None) -> CityDataset:
    city = make_test_city()
    n = len(next(iter(values.values())))
    ts = pd.date_range("2025-11-01", periods=n, freq="h", tz="UTC")
    obs = pd.concat([pd.DataFrame({"station_id": sid, "timestamp": ts, "pm25": v}) for sid, v in values.items()], ignore_index=True)
    stations = stations if stations is not None else pd.DataFrame({
        "station_id": list(values), "name": list(values), "latitude": 33.64, "longitude": 73.05,
        "kind": "reference", "provider": "test", "license": "test", "synthetic": True})
    if weather is None:
        weather = pd.DataFrame({"timestamp": ts, "temperature_c": 15.0, "relative_humidity_pct": 60.0, "wind_speed_ms": 2.0,
                                "wind_direction_deg": 90.0, "surface_pressure_hpa": 950.0, "boundary_layer_height_m": 500.0})
    return CityDataset(city, stations, obs, weather, {"mode": "demo", "synthetic": True})


def test_range_stuck_and_spike_rules():
    base = list(50 + 5 * np.sin(np.arange(48) / 3.0))
    v = base.copy()
    v[5] = -3.0          # negative
    v[6] = 1500.0        # above valid range
    v[20] = 400.0        # isolated spike
    for i in range(30, 38):
        v[i] = 61.5      # stuck sensor (8 identical hours)
    out = DataProcessor().clean(_dataset({"A": v}))
    qc = out.qc["observations"]
    assert qc["out_of_range"] == 2
    assert qc["stuck"] == 8
    assert qc["spikes"] == 1
    kept = set(out.observations["pm25"].round(1))
    assert 400.0 not in kept and 61.5 not in kept and -3.0 not in kept


def test_duplicates_are_merged_and_non_numeric_dropped():
    ds = _dataset({"A": [10.0, 20.0, 30.0, 40.0]})
    extra = pd.DataFrame({"station_id": ["A", "A"], "timestamp": [ds.observations.timestamp[0] + pd.Timedelta(minutes=20)] * 2,
                          "pm25": [14.0, "bad"]})
    ds.observations = pd.concat([ds.observations, extra], ignore_index=True)
    out = DataProcessor().clean(ds)
    assert out.qc["observations"]["missing_or_non_numeric"] == 1
    assert out.qc["observations"]["duplicates_merged"] == 1
    first = out.observations.sort_values("timestamp").iloc[0]["pm25"]
    assert first == pytest.approx(12.0)


def test_completeness_and_domain_flags():
    vals = {"good": [30.0] * 4 + [31.0, 32.0, 33.0, 34.0] * 5, "sparse": [np.nan] * 22 + [40.0, 41.0]}
    stations = pd.DataFrame({"station_id": ["good", "sparse", "outside"], "name": ["g", "s", "o"],
                             "latitude": [33.64, 33.65, 10.0], "longitude": [73.05, 73.06, 10.0],
                             "kind": "reference", "provider": "t", "license": "t", "synthetic": True})
    out = DataProcessor().clean(_dataset(vals, stations=stations))
    st = out.stations.set_index("station_id")
    assert bool(st.loc["good", "usable"])
    assert not bool(st.loc["sparse", "usable"]) and "insufficient_data" in st.loc["sparse", "qc_flags"]
    assert not bool(st.loc["outside", "inside_domain"]) and "outside_analysis_domain" in st.loc["outside", "qc_flags"]
    assert list(out.training_stations["station_id"]) == ["good"]


def test_weather_gaps_interpolated_with_circular_wind():
    ts = pd.date_range("2025-11-01", periods=12, freq="h", tz="UTC")
    weather = pd.DataFrame({"timestamp": ts, "temperature_c": np.linspace(10, 21, 12), "relative_humidity_pct": 60.0,
                            "wind_speed_ms": 2.0, "wind_direction_deg": [350.0] * 6 + [10.0] * 6,
                            "surface_pressure_hpa": 950.0, "boundary_layer_height_m": np.nan})
    weather.loc[3:4, "temperature_c"] = np.nan
    weather.loc[5:6, "wind_direction_deg"] = np.nan
    weather.loc[8, "relative_humidity_pct"] = 140.0  # impossible
    out = DataProcessor().clean(_dataset({"A": [20.0 + i for i in range(12)]}, weather=weather))
    w = out.weather.set_index("timestamp")
    assert w["temperature_c"].iloc[3] == pytest.approx(13.0)
    wd = w["wind_direction_deg"].iloc[5]
    assert wd > 340 or wd < 20  # interpolated through north, not through 180°
    assert out.qc["weather"]["out_of_range"]["relative_humidity_pct"] == 1
    assert "boundary_layer_height_m" in out.qc["weather"]["unavailable"]


def test_bundled_demo_faults_are_detected():
    ds = DatasetService().get("islamabad")
    qc = ds.qc["observations"]
    # the generator injects 2 negative values per station and one 10-hour stuck run
    assert qc["out_of_range"] >= 2 * len(ds.stations)
    assert qc["stuck"] == 10
    assert qc["spikes"] > 0
    assert ds.provenance["synthetic"] is True and ds.provenance["mode"] == "demo"
