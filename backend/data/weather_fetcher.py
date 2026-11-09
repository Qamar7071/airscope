"""Open-Meteo weather client (no API key required).

Hourly variables requested (Open-Meteo names -> AirScope columns):
  temperature_2m         -> temperature_c
  relative_humidity_2m   -> relative_humidity_pct
  wind_speed_10m         -> wind_speed_ms          (requested in m/s)
  wind_direction_10m     -> wind_direction_deg
  surface_pressure       -> surface_pressure_hpa
  boundary_layer_height  -> boundary_layer_height_m (not available for every
                            model/endpoint; the request is retried without it)

Recent periods (<= 92 days back) use the forecast API with ``past_days``; older
periods use the ERA5-based archive API. Licence: Open-Meteo data are CC BY 4.0
and the free API is for non-commercial use - see docs/data_sources_and_licensing.md.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests

from .cache_manager import CacheManager

logger = logging.getLogger(__name__)

VARIABLE_MAP = {
    "temperature_2m": "temperature_c",
    "relative_humidity_2m": "relative_humidity_pct",
    "wind_speed_10m": "wind_speed_ms",
    "wind_direction_10m": "wind_direction_deg",
    "surface_pressure": "surface_pressure_hpa",
    "boundary_layer_height": "boundary_layer_height_m",
}
WEATHER_COLUMNS = list(VARIABLE_MAP.values())
MAX_PAST_DAYS = 92


class WeatherError(RuntimeError):
    pass


class WeatherFetcher:
    def __init__(
        self,
        forecast_url: str = "https://api.open-meteo.com/v1/forecast",
        archive_url: str = "https://archive-api.open-meteo.com/v1/archive",
        timeout_s: float = 20.0,
        session: requests.Session | None = None,
        cache: CacheManager | None = None,
    ):
        self.forecast_url = forecast_url
        self.archive_url = archive_url
        self.timeout_s = timeout_s
        self.session = session or requests.Session()
        self.cache = cache

    @staticmethod
    def parse_response(doc: dict) -> pd.DataFrame:
        hourly = doc.get("hourly") or {}
        times = hourly.get("time")
        if not times:
            raise WeatherError("Open-Meteo response has no hourly data")
        df = pd.DataFrame({"timestamp": pd.to_datetime(times, utc=True)})
        for api_name, col in VARIABLE_MAP.items():
            values = hourly.get(api_name)
            df[col] = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy() if values is not None else np.nan
        units = doc.get("hourly_units") or {}
        if str(units.get("wind_speed_10m", "m/s")).lower() in ("km/h", "kmh"):
            df["wind_speed_ms"] = df["wind_speed_ms"] / 3.6
        return df

    def _request(self, url: str, params: dict) -> dict:
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout_s, headers={"User-Agent": "AirScope/1.0"})
        except requests.RequestException as exc:
            raise WeatherError(f"Open-Meteo request failed: {exc}") from exc
        if resp.status_code == 400 and "boundary_layer_height" in params.get("hourly", ""):
            logger.info("Open-Meteo rejected boundary_layer_height for this endpoint; retrying without it")
            reduced = dict(params)
            reduced["hourly"] = ",".join(v for v in params["hourly"].split(",") if v != "boundary_layer_height")
            return self._request(url, reduced)
        if resp.status_code != 200:
            raise WeatherError(f"Open-Meteo HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            return resp.json()
        except ValueError as exc:
            raise WeatherError("Open-Meteo returned invalid JSON") from exc

    def fetch_hourly(self, lat: float, lon: float, start: datetime, end: datetime, now: datetime | None = None) -> pd.DataFrame:
        """Hourly weather at (lat, lon) between ``start`` and ``end`` (UTC, inclusive)."""
        now = now or datetime.now(timezone.utc)
        start = start.astimezone(timezone.utc)
        end = end.astimezone(timezone.utc)
        common = {
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "hourly": ",".join(VARIABLE_MAP.keys()),
            "wind_speed_unit": "ms",
            "timezone": "GMT",
        }
        days_back = (now - start).days + 1
        if days_back <= MAX_PAST_DAYS:
            params = {**common, "past_days": max(1, days_back), "forecast_days": 1}
            doc = self._request(self.forecast_url, params)
        else:
            params = {**common, "start_date": start.date().isoformat(), "end_date": end.date().isoformat()}
            doc = self._request(self.archive_url, params)
        df = self.parse_response(doc)
        mask = (df["timestamp"] >= pd.Timestamp(start).floor("h")) & (df["timestamp"] <= pd.Timestamp(end).ceil("h"))
        return df.loc[mask].reset_index(drop=True)

    def fetch_recent(self, lat: float, lon: float, days: int, now: datetime | None = None) -> pd.DataFrame:
        now = (now or datetime.now(timezone.utc)).replace(minute=0, second=0, microsecond=0)
        return self.fetch_hourly(lat, lon, now - timedelta(days=days), now, now=now)
