"""OpenAQ API v3 client (optional live mode).

OpenAQ v3 requires a free API key (https://explore.openaq.org/register), sent
in the ``X-API-Key`` header. Without a key AirScope runs in offline demo mode;
nothing in the platform depends on this module succeeding.

Endpoints used:
  * ``GET /v3/locations?coordinates=lat,lon&radius=m&parameters_id=2`` - PM2.5 sites
  * ``GET /v3/sensors/{sensor_id}/hours?datetime_from=..&datetime_to=..`` - hourly means

Data licensing: OpenAQ aggregates data from many providers and each location
carries its own ``licenses`` list. AirScope keeps that list and shows it next to
live data. See docs/data_sources_and_licensing.md.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import requests

from config import CityConfig
from .cache_manager import CacheManager

logger = logging.getLogger(__name__)

PM25_PARAMETER_ID = 2
MAX_PAGES = 10


class OpenAQError(RuntimeError):
    """Any failure talking to OpenAQ (network, auth, schema)."""


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_in(d: Any, *path: str, default=None):
    for key in path:
        if not isinstance(d, dict) or key not in d:
            return default
        d = d[key]
    return d


class OpenAQFetcher:
    def __init__(
        self,
        api_key: str | None,
        base_url: str = "https://api.openaq.org/v3",
        timeout_s: float = 20.0,
        session: requests.Session | None = None,
        cache: CacheManager | None = None,
        max_retries: int = 3,
        backoff_s: float = 1.5,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.session = session or requests.Session()
        self.cache = cache
        self.max_retries = max_retries
        self.backoff_s = backoff_s

    # ------------------------------------------------------------------ http
    def _get(self, path: str, params: dict[str, Any]) -> dict:
        if not self.api_key:
            raise OpenAQError("OpenAQ v3 requires an API key (set OPENAQ_API_KEY); running offline instead")
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {"X-API-Key": self.api_key, "Accept": "application/json", "User-Agent": "AirScope/1.0"}
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(url, params=params, headers=headers, timeout=self.timeout_s)
            except requests.RequestException as exc:
                last_error = exc
                logger.warning("OpenAQ request failed (attempt %d/%d): %s", attempt, self.max_retries, exc)
            else:
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except ValueError as exc:
                        raise OpenAQError(f"OpenAQ returned invalid JSON for {path}") from exc
                if resp.status_code in (401, 403):
                    raise OpenAQError(f"OpenAQ rejected the API key (HTTP {resp.status_code})")
                if resp.status_code == 404:
                    raise OpenAQError(f"OpenAQ resource not found: {path}")
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_error = OpenAQError(f"OpenAQ HTTP {resp.status_code}")
                    retry_after = resp.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after and retry_after.isdigit() else self.backoff_s * attempt
                    logger.warning("OpenAQ HTTP %s; retrying in %.1fs", resp.status_code, wait)
                    time.sleep(min(wait, 30.0))
                    continue
                raise OpenAQError(f"OpenAQ HTTP {resp.status_code}: {resp.text[:200]}")
            time.sleep(self.backoff_s * attempt)
        raise OpenAQError(f"OpenAQ request to {path} failed after {self.max_retries} attempts: {last_error}")

    def _paged(self, path: str, params: dict[str, Any], limit: int = 1000) -> list[dict]:
        results: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            doc = self._get(path, {**params, "limit": limit, "page": page})
            batch = doc.get("results") or []
            results.extend(batch)
            if len(batch) < limit:
                break
        return results

    # ------------------------------------------------------------- locations
    @staticmethod
    def parse_location(loc: dict) -> dict | None:
        """Normalise a v3 location record; ``None`` if it has no usable PM2.5 sensor."""
        lat = _get_in(loc, "coordinates", "latitude")
        lon = _get_in(loc, "coordinates", "longitude")
        if lat is None or lon is None or loc.get("isMobile"):
            return None
        pm_sensors = [
            s.get("id")
            for s in loc.get("sensors") or []
            if _get_in(s, "parameter", "id") == PM25_PARAMETER_ID or _get_in(s, "parameter", "name") == "pm25"
        ]
        pm_sensors = [s for s in pm_sensors if s is not None]
        if not pm_sensors:
            return None
        licenses = [
            {"name": _get_in(lic, "name"), "attribution": _get_in(lic, "attribution", "name")}
            for lic in loc.get("licenses") or []
        ]
        return {
            "station_id": f"openaq-{loc.get('id')}",
            "openaq_location_id": loc.get("id"),
            "name": loc.get("name") or f"OpenAQ location {loc.get('id')}",
            "latitude": float(lat),
            "longitude": float(lon),
            "pm25_sensor_ids": pm_sensors,
            "provider": _get_in(loc, "provider", "name") or "unknown",
            "owner": _get_in(loc, "owner", "name"),
            "kind": "reference" if loc.get("isMonitor") else "low-cost",
            "licenses": licenses,
            "license": "; ".join(sorted({str(lic["name"]) for lic in licenses if lic.get("name")})) or "See provider",
            "datetime_last": _get_in(loc, "datetimeLast", "utc"),
            "synthetic": False,
        }

    def find_locations(self, lat: float, lon: float, radius_m: int, limit: int = 100) -> list[dict]:
        params = {
            "coordinates": f"{lat:.4f},{lon:.4f}",
            "radius": int(min(radius_m, 25000)),
            "parameters_id": PM25_PARAMETER_ID,
        }
        raw = self._paged("locations", params, limit=limit)
        parsed = [p for p in (self.parse_location(r) for r in raw) if p is not None]
        logger.info("OpenAQ: %d PM2.5 locations within %d m of %.3f,%.3f", len(parsed), radius_m, lat, lon)
        return parsed

    # ---------------------------------------------------------- measurements
    @staticmethod
    def parse_hourly(results: list[dict]) -> pd.DataFrame:
        """Parse /sensors/{id}/hours results into ``timestamp, pm25`` rows (UTC hour start)."""
        rows = []
        for r in results:
            value = r.get("value")
            ts = _get_in(r, "period", "datetimeFrom", "utc") or _get_in(r, "datetime", "utc")
            if value is None or ts is None:
                continue
            rows.append({"timestamp": ts, "pm25": value, "flagged": bool(_get_in(r, "flagInfo", "hasFlags", default=False))})
        if not rows:
            return pd.DataFrame(columns=["timestamp", "pm25", "flagged"])
        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce").dt.floor("h")
        df["pm25"] = pd.to_numeric(df["pm25"], errors="coerce")
        return df.dropna(subset=["timestamp"])

    def fetch_sensor_hours(self, sensor_id: int, start: datetime, end: datetime) -> pd.DataFrame:
        params = {"datetime_from": _iso(start), "datetime_to": _iso(end)}
        return self.parse_hourly(self._paged(f"sensors/{sensor_id}/hours", params))

    # ------------------------------------------------------------------ city
    def fetch_city(self, city: CityConfig, days: int, now: datetime | None = None) -> dict:
        """Fetch stations and hourly PM2.5 for the last ``days`` days around a city."""
        now = (now or datetime.now(timezone.utc)).replace(minute=0, second=0, microsecond=0)
        start = now - timedelta(days=days)
        locations = self.find_locations(city.center_lat, city.center_lon, city.openaq_radius_m)
        frames = []
        for loc in locations:
            for sensor_id in loc["pm25_sensor_ids"][:1]:  # one PM2.5 sensor per location
                try:
                    df = self.fetch_sensor_hours(sensor_id, start, now)
                except OpenAQError as exc:
                    logger.warning("Skipping sensor %s: %s", sensor_id, exc)
                    continue
                if not df.empty:
                    df["station_id"] = loc["station_id"]
                    frames.append(df)
        observations = (
            pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["station_id", "timestamp", "pm25", "flagged"])
        )
        return {
            "stations": locations,
            "observations": observations,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "period_start": _iso(start),
            "period_end": _iso(now),
        }
