"""Builds analysis-ready city datasets in demo or live mode, with honest provenance.

Mode resolution (``AIRSCOPE_DATA_MODE``):
  * ``demo`` - always the bundled synthetic dataset (default; fully offline);
  * ``live`` / ``auto`` - OpenAQ v3 + Open-Meteo when an OpenAQ key is set.
    If the live fetch fails, the last good live response is used and marked
    *stale*; if there is none, the demo dataset is used and the response says
    that it is a fallback and why. Synthetic data are never labelled as live.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from config import CityConfig, Settings, get_city, get_settings
from .cache_manager import CacheManager
from .data_processor import CityDataset, DataProcessor, WEATHER_COLUMNS
from .demo_generator import load_demo_payload
from .openaq_fetcher import OpenAQError, OpenAQFetcher
from .weather_fetcher import WeatherError, WeatherFetcher

logger = logging.getLogger(__name__)

DEMO_LABEL = "Synthetic demo data"
LIVE_LABEL = "Live data: OpenAQ v3 + Open-Meteo"


class DatasetService:
    def __init__(
        self,
        settings: Settings | None = None,
        processor: DataProcessor | None = None,
        openaq: OpenAQFetcher | None = None,
        weather: WeatherFetcher | None = None,
    ):
        self.settings = settings or get_settings()
        self.cache = CacheManager(self.settings.cache_dir, "live")
        self.processor = processor or DataProcessor()
        self.openaq = openaq or OpenAQFetcher(
            self.settings.openaq_api_key, self.settings.openaq_base_url, self.settings.http_timeout_s, cache=self.cache
        )
        self.weather = weather or WeatherFetcher(
            self.settings.open_meteo_forecast_url, self.settings.open_meteo_archive_url, self.settings.http_timeout_s, cache=self.cache
        )
        self._memo: dict[str, tuple[CityDataset, float]] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ api
    def requested_mode(self) -> str:
        return "live" if self.settings.live_enabled else "demo"

    def get(self, city_id: str, force_refresh: bool = False) -> CityDataset:
        city = get_city(city_id)
        mode = self.requested_mode()
        key = f"{city.id}:{mode}"
        ttl = None if mode == "demo" else self.settings.live_cache_ttl_hours * 3600
        with self._lock:
            hit = self._memo.get(key)
            if hit and not force_refresh and (ttl is None or time.time() - hit[1] < ttl):
                return hit[0]
            raw = self._load_demo(city) if mode == "demo" else self._load_live(city, force_refresh)
            cleaned = self.processor.clean(raw)
            self._memo[key] = (cleaned, time.time())
            return cleaned

    def invalidate(self, city_id: str | None = None) -> None:
        with self._lock:
            if city_id is None:
                self._memo.clear()
            else:
                for k in [k for k in self._memo if k.startswith(f"{city_id}:")]:
                    del self._memo[k]

    # ----------------------------------------------------------------- demo
    def _load_demo(self, city: CityConfig) -> CityDataset:
        payload = load_demo_payload(city.id)
        stations = pd.DataFrame(payload["stations"]).rename(columns={"id": "station_id"})
        obs = payload["observations"]
        ts = pd.to_datetime(obs["timestamps"], utc=True)
        frames = [
            pd.DataFrame({"station_id": sid, "timestamp": ts, "pm25": pd.to_numeric(pd.Series(vals), errors="coerce").to_numpy()})
            for sid, vals in obs["values"].items()
        ]
        observations = pd.concat(frames, ignore_index=True)
        w = payload["weather"]
        weather = pd.DataFrame({c: pd.to_numeric(pd.Series(w[c]), errors="coerce").to_numpy() for c in WEATHER_COLUMNS})
        weather.insert(0, "timestamp", pd.to_datetime(w["timestamps"], utc=True))
        prov = payload["provenance"]
        provenance = {
            "mode": "demo",
            "synthetic": True,
            "label": DEMO_LABEL,
            "sources": ["AirScope synthetic nature run (OSSE)"],
            "description": prov.get("description"),
            "generator": prov.get("generator"),
            "seed": prov.get("seed"),
            "period_start": prov.get("period_start"),
            "period_end": prov.get("period_end"),
            "fetched_at": None,
            "stale": False,
            "fallback": None,
            "licenses": ["Synthetic data released with AirScope"],
        }
        return CityDataset(city=city, stations=stations, observations=observations, weather=weather, provenance=provenance)

    # ----------------------------------------------------------------- live
    def _live_key(self, city: CityConfig) -> str:
        return CacheManager.make_key("citydata", city.id, days=self.settings.live_history_days)

    def _fetch_live_payload(self, city: CityConfig) -> dict:
        raw = self.openaq.fetch_city(city, self.settings.live_history_days)
        if not raw["stations"]:
            raise OpenAQError(f"OpenAQ lists no PM2.5 stations within {city.openaq_radius_m / 1000:.0f} km of {city.name}")
        obs = raw["observations"]
        if obs.empty:
            raise OpenAQError(f"OpenAQ returned no PM2.5 measurements for {city.name} in the last {self.settings.live_history_days} days")
        start = pd.Timestamp(raw["period_start"]).to_pydatetime()
        end = pd.Timestamp(raw["period_end"]).to_pydatetime()
        weather = self.weather.fetch_hourly(city.center_lat, city.center_lon, start, end)
        return {
            "stations": raw["stations"],
            "observations": [
                {"station_id": r.station_id, "timestamp": r.timestamp.isoformat(), "pm25": None if pd.isna(r.pm25) else float(r.pm25)}
                for r in obs.itertuples()
            ],
            "weather": [
                {"timestamp": r["timestamp"].isoformat(), **{c: (None if pd.isna(r[c]) else float(r[c])) for c in WEATHER_COLUMNS}}
                for _, r in weather.iterrows()
            ],
            "fetched_at": raw["fetched_at"],
            "period_start": raw["period_start"],
            "period_end": raw["period_end"],
        }

    def _dataset_from_live(self, city: CityConfig, payload: dict, stale_reason: str | None) -> CityDataset:
        stations = pd.DataFrame(payload["stations"])
        observations = pd.DataFrame(payload["observations"])
        observations["timestamp"] = pd.to_datetime(observations["timestamp"], utc=True)
        weather = pd.DataFrame(payload["weather"])
        weather["timestamp"] = pd.to_datetime(weather["timestamp"], utc=True)
        licenses = sorted({lic for lic in stations.get("license", pd.Series(dtype=str)).dropna().astype(str)})
        provenance = {
            "mode": "live",
            "synthetic": False,
            "label": LIVE_LABEL + (" (stale cache)" if stale_reason else ""),
            "sources": ["OpenAQ API v3", "Open-Meteo"],
            "description": "Measured PM2.5 from OpenAQ-listed stations and modelled weather from Open-Meteo.",
            "period_start": payload.get("period_start"),
            "period_end": payload.get("period_end"),
            "fetched_at": payload.get("fetched_at"),
            "stale": bool(stale_reason),
            "stale_reason": stale_reason,
            "fallback": None,
            "licenses": licenses,
        }
        return CityDataset(city=city, stations=stations, observations=observations, weather=weather, provenance=provenance)

    def _load_live(self, city: CityConfig, force_refresh: bool) -> CityDataset:
        key = self._live_key(city)
        ttl_s = self.settings.live_cache_ttl_hours * 3600
        cached = None if force_refresh else self.cache.get(key, max_age_s=ttl_s)
        if cached is not None:
            return self._dataset_from_live(city, cached, None)
        try:
            payload = self._fetch_live_payload(city)
            self.cache.set(key, payload)
            return self._dataset_from_live(city, payload, None)
        except (OpenAQError, WeatherError) as exc:
            logger.warning("Live data unavailable for %s: %s", city.id, exc)
            entry = self.cache.get_entry(key)
            if entry is not None:
                age_h = (datetime.now(timezone.utc) - entry[1]) / timedelta(hours=1)
                return self._dataset_from_live(city, entry[0], f"{exc} - showing cached live data from {age_h:.1f} h ago")
            demo = self._load_demo(city)
            demo.provenance["fallback"] = {"requested_mode": "live", "reason": str(exc)}
            demo.provenance["label"] = DEMO_LABEL + " (live data unavailable)"
            return demo


_service: DatasetService | None = None
_service_lock = threading.Lock()


def get_dataset_service() -> DatasetService:
    global _service
    with _service_lock:
        if _service is None:
            _service = DatasetService()
        return _service
