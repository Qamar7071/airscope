"""Live-data clients, tested offline with recorded-shape fixtures and fake HTTP sessions."""
from dataclasses import replace
from datetime import datetime, timezone

import pandas as pd
import pytest

from config import get_city, get_settings
from data.cache_manager import CacheManager
from data.dataset_service import DatasetService
from data.openaq_fetcher import OpenAQError, OpenAQFetcher
from data.weather_fetcher import WeatherError, WeatherFetcher


class FakeResponse:
    def __init__(self, status: int, payload=None, text: str = "", headers=None):
        self.status_code = status
        self._payload = payload
        self.text = text or (str(payload) if payload is not None else "")
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    def __init__(self, responder):
        self.responder = responder
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {}), "headers": dict(headers or {})})
        return self.responder(url, params or {})


def test_openaq_parses_locations(fixture_json):
    raw = fixture_json("openaq_locations.json")["results"]
    parsed = [OpenAQFetcher.parse_location(r) for r in raw]
    assert parsed[2] is None  # mobile units are ignored
    ref, low = parsed[0], parsed[1]
    assert ref["station_id"] == "openaq-101" and ref["pm25_sensor_ids"] == [5001]
    assert ref["kind"] == "reference" and low["kind"] == "low-cost"
    assert ref["license"] == "CC BY 4.0" and ref["synthetic"] is False


def test_openaq_parses_hourly_values(fixture_json):
    df = OpenAQFetcher.parse_hourly(fixture_json("openaq_hours.json")["results"])
    assert len(df) == 2  # the null value is skipped
    assert df["timestamp"].iloc[0] == pd.Timestamp("2026-11-08T00:00:00Z")
    assert list(df["pm25"]) == [41.5, 44.0]


def test_openaq_requires_key():
    with pytest.raises(OpenAQError, match="API key"):
        OpenAQFetcher(api_key=None).find_locations(33.7, 73.0, 1000)


def test_openaq_sends_key_and_reports_auth_errors():
    session = FakeSession(lambda url, params: FakeResponse(401, {"detail": "invalid"}))
    f = OpenAQFetcher(api_key="test-key", session=session, backoff_s=0)
    with pytest.raises(OpenAQError, match="rejected"):
        f.find_locations(33.7, 73.0, 1000)
    assert session.calls[0]["headers"]["X-API-Key"] == "test-key"
    assert session.calls[0]["params"]["coordinates"] == "33.7000,73.0000"
    assert session.calls[0]["params"]["parameters_id"] == 2


def test_openaq_retries_then_succeeds(fixture_json):
    responses = [FakeResponse(503, None, "busy"), FakeResponse(200, fixture_json("openaq_locations.json"))]
    session = FakeSession(lambda url, params: responses.pop(0))
    f = OpenAQFetcher(api_key="k", session=session, backoff_s=0)
    locs = f.find_locations(33.7, 73.0, 25000)
    assert len(locs) == 2 and len(session.calls) == 2


def test_openaq_fetch_city_end_to_end(fixture_json):
    def responder(url, params):
        if url.endswith("/locations"):
            return FakeResponse(200, fixture_json("openaq_locations.json"))
        return FakeResponse(200, fixture_json("openaq_hours.json"))

    f = OpenAQFetcher(api_key="k", session=FakeSession(responder), backoff_s=0)
    out = f.fetch_city(get_city("islamabad"), days=2, now=datetime(2026, 11, 8, 12, tzinfo=timezone.utc))
    assert len(out["stations"]) == 2
    assert set(out["observations"]["station_id"]) == {"openaq-101", "openaq-102"}


def test_weather_parses_and_retries_without_blh(fixture_json):
    doc = fixture_json("open_meteo_forecast.json")
    df = WeatherFetcher.parse_response(doc)
    assert list(df.columns)[0] == "timestamp" and len(df) == 3
    assert df["boundary_layer_height_m"].iloc[0] == 210

    def responder(url, params):
        if "boundary_layer_height" in params["hourly"]:
            return FakeResponse(400, None, "Cannot initialize boundary_layer_height")
        return FakeResponse(200, {k: v for k, v in doc.items()})

    session = FakeSession(responder)
    w = WeatherFetcher(session=session)
    out = w.fetch_hourly(33.69, 73.06, datetime(2026, 11, 8, 0, tzinfo=timezone.utc), datetime(2026, 11, 8, 2, tzinfo=timezone.utc),
                         now=datetime(2026, 11, 8, 3, tzinfo=timezone.utc))
    assert len(session.calls) == 2 and "boundary_layer_height" not in session.calls[1]["params"]["hourly"]
    assert session.calls[0]["params"]["wind_speed_unit"] == "ms"
    assert len(out) == 3


def test_weather_converts_kmh_units(fixture_json):
    doc = fixture_json("open_meteo_forecast.json")
    doc["hourly_units"]["wind_speed_10m"] = "km/h"
    doc["hourly"]["wind_speed_10m"] = [3.6, 7.2, 10.8]
    df = WeatherFetcher.parse_response(doc)
    assert list(df["wind_speed_ms"].round(3)) == [1.0, 2.0, 3.0]


def test_weather_http_error():
    w = WeatherFetcher(session=FakeSession(lambda url, params: FakeResponse(500, None, "boom")))
    with pytest.raises(WeatherError):
        w.fetch_recent(33.7, 73.0, days=1)


def test_cache_manager_ttl_and_atomic_roundtrip(tmp_path):
    cache = CacheManager(tmp_path, "unit")
    key = CacheManager.make_key("city", "islamabad", days=3)
    assert cache.get(key) is None
    cache.set(key, {"a": [1, 2, 3]})
    assert cache.get(key) == {"a": [1, 2, 3]}
    assert cache.get(key, max_age_s=0) is None  # expired immediately
    assert cache.get_entry(key)[0] == {"a": [1, 2, 3]}  # stale data still retrievable for fallback
    assert cache.invalidate(key) and cache.get(key) is None


class FailingOpenAQ:
    def fetch_city(self, city, days):
        raise OpenAQError("network unreachable")


def test_live_failure_falls_back_to_demo_and_says_so(tmp_path):
    settings = replace(get_settings(), data_mode="live", openaq_api_key="dummy", cache_dir=tmp_path)
    svc = DatasetService(settings=settings, openaq=FailingOpenAQ())
    ds = svc.get("islamabad")
    assert ds.provenance["synthetic"] is True and ds.provenance["mode"] == "demo"
    assert ds.provenance["fallback"]["requested_mode"] == "live"
    assert "unavailable" in ds.provenance["label"]


def test_live_failure_uses_stale_live_cache_with_label(tmp_path):
    settings = replace(get_settings(), data_mode="live", openaq_api_key="dummy", cache_dir=tmp_path, live_cache_ttl_hours=0.0)
    svc = DatasetService(settings=settings, openaq=FailingOpenAQ())
    ts = pd.date_range("2026-11-07", periods=30, freq="h", tz="UTC")
    payload = {
        "stations": [{"station_id": "openaq-1", "name": "A", "latitude": 33.70, "longitude": 73.05, "kind": "reference",
                      "provider": "p", "license": "CC BY 4.0", "synthetic": False},
                     {"station_id": "openaq-2", "name": "B", "latitude": 33.65, "longitude": 73.02, "kind": "reference",
                      "provider": "p", "license": "CC BY 4.0", "synthetic": False}],
        "observations": [{"station_id": sid, "timestamp": t.isoformat(), "pm25": 40.0 + i % 5}
                         for sid in ("openaq-1", "openaq-2") for i, t in enumerate(ts)],
        "weather": [{"timestamp": t.isoformat(), "temperature_c": 12.0, "relative_humidity_pct": 70.0, "wind_speed_ms": 1.5,
                     "wind_direction_deg": 30.0, "surface_pressure_hpa": 951.0, "boundary_layer_height_m": None} for t in ts],
        "fetched_at": "2026-11-08T00:00:00+00:00", "period_start": ts[0].isoformat(), "period_end": ts[-1].isoformat(),
    }
    svc.cache.set(svc._live_key(get_city("islamabad")), payload)
    ds = svc.get("islamabad")
    assert ds.provenance["mode"] == "live" and ds.provenance["synthetic"] is False
    assert ds.provenance["stale"] is True and "stale" in ds.provenance["label"]
    assert len(ds.training_stations) == 2
