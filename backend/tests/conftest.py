"""Shared pytest fixtures.

The suite runs fully offline on the bundled synthetic demo data. One city is
trained once per session with the fast profile into a temporary directory, so
tests never depend on (or modify) the user's ``models/`` folder.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

_TMP = Path(tempfile.mkdtemp(prefix="airscope-tests-"))
os.environ.update({
    "AIRSCOPE_DATA_MODE": "demo",
    "OPENAQ_API_KEY": "",
    "AIRSCOPE_MODELS_DIR": str(_TMP / "models"),
    "AIRSCOPE_TRAINING_PROFILE": "fast",
    "AIRSCOPE_TRAIN_ON_STARTUP": "false",
    "AIRSCOPE_LOG_LEVEL": "WARNING",
})

from config import get_settings  # noqa: E402

get_settings.cache_clear()

TEST_CITY = "karachi"  # smallest grid -> fastest tests


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def trained_city(settings):
    """Train TEST_CITY once (fast profile) and return its metrics."""
    from ml.train import train_city

    return train_city(TEST_CITY, "fast", models_dir=settings.models_dir)


@pytest.fixture(scope="session")
def app(trained_city):
    from app import create_app
    from services.analysis_service import reset_analysis_service
    from services.model_registry import reset_registry

    reset_registry(None)
    reset_analysis_service(None)
    return create_app(start_training=False)


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def fixture_json():
    import json

    def load(name: str):
        with open(BACKEND / "tests" / "fixtures" / name, encoding="utf-8") as fh:
            return json.load(fh)

    return load


# --------------------------------------------------------------------------- synthetic context


def make_test_city(cell_km: float = 0.5):
    """A small square test city (about 10 x 10 km) for fast unit tests."""
    from config import CityConfig

    ring = ((73.00, 33.60), (73.10, 33.60), (73.10, 33.69), (73.00, 33.69), (73.00, 33.60))
    return CityConfig(
        id="testville", name="Testville", country="Nowhere", timezone="Asia/Karachi",
        center_lat=33.645, center_lon=73.05, center_label="Centre", boundary=(ring,),
        grid_cell_km=cell_km, coverage_radius_km=2.0, correlation_length_km=3.0,
        openaq_radius_m=25000, domain_note="test",
    )


@pytest.fixture()
def test_context():
    """AnalysisContext with a dense, polluted, unmonitored north-east and stations in the south-west."""
    from geospatial.city_grid import build_city_grid
    from geospatial.distance import haversine_km
    from ml.gaps import AnalysisContext
    from ml.uncertainty import UncertaintyParams

    city = make_test_city()
    grid = build_city_grid(city)
    lat, lon = grid.inside_lat, grid.inside_lon
    hot_lat, hot_lon = 33.675, 73.085  # north-east hot spot
    d_hot = haversine_km(lat, lon, hot_lat, hot_lon)
    population = 500 + 20000 * np.exp(-0.5 * (d_hot / 1.5) ** 2)
    pm25 = 40 + 60 * np.exp(-0.5 * (d_hot / 2.0) ** 2)
    station_lat = np.array([33.61, 33.62, 33.615])
    station_lon = np.array([73.01, 73.03, 73.05])
    params = UncertaintyParams(scale=1.0, spatial_var=0.1, range_km=3.0, nugget_ratio=0.2, calibrated=True)
    return AnalysisContext(city, grid, pm25, np.full(len(lat), 0.01), population, ["S1", "S2", "S3"],
                           station_lat, station_lon, params)
