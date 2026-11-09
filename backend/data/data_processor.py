"""Data model and quality control for city datasets.

``DataProcessor.clean`` turns raw station readings and weather into an analysis
ready :class:`CityDataset` and records every intervention in a QC report, so
the UI can show exactly what was removed and why.

PM2.5 quality-control rules (applied per station, on an hourly grid):
  1. non-numeric / missing values are dropped;
  2. duplicate readings within the same hour are averaged;
  3. physically implausible values (< 0 or > 1000 µg/m³) are removed;
  4. "stuck" sensors - identical values for >= 6 consecutive hours - are removed;
  5. isolated positive spikes are removed with a Hampel filter
     (|x - rolling median| > 6 x 1.4826 x MAD and x > 2 x median, 7-hour window);
  6. stations with < 25 % valid hours, or outside the analysis domain, are kept
     for display but excluded from model training.

Weather: values outside physical ranges are set to missing, gaps of up to six
hours are interpolated in time (wind direction via u/v components), and any
remaining gaps are left for the model pipeline's median imputer.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from config import CityConfig
from geospatial.spatial_utils import points_in_polygon

logger = logging.getLogger(__name__)

PM_VALID_RANGE = (0.0, 1000.0)
STUCK_MIN_RUN = 6
HAMPEL_WINDOW = 7
HAMPEL_K = 6.0
MIN_COMPLETENESS = 0.25
MAX_INTERP_GAP_H = 6
WEATHER_RANGES = {
    "temperature_c": (-40.0, 60.0),
    "relative_humidity_pct": (0.0, 100.0),
    "wind_speed_ms": (0.0, 75.0),
    "wind_direction_deg": (0.0, 360.0),
    "surface_pressure_hpa": (500.0, 1100.0),
    "boundary_layer_height_m": (0.0, 6000.0),
}
WEATHER_COLUMNS = list(WEATHER_RANGES)
STATION_COLUMNS = ["station_id", "name", "latitude", "longitude", "kind", "provider", "license", "synthetic"]


@dataclass
class CityDataset:
    city: CityConfig
    stations: pd.DataFrame
    observations: pd.DataFrame  # long format: station_id, timestamp (UTC), pm25
    weather: pd.DataFrame  # timestamp + WEATHER_COLUMNS, hourly UTC
    provenance: dict
    qc: dict = field(default_factory=dict)

    @property
    def timestamps(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(self.weather["timestamp"])

    @property
    def training_stations(self) -> pd.DataFrame:
        if "usable" not in self.stations:
            return self.stations
        return self.stations[self.stations["usable"]].reset_index(drop=True)

    def obs_wide(self, usable_only: bool = True) -> pd.DataFrame:
        """Hourly matrix (index = all weather timestamps, columns = station ids)."""
        ids = list(self.training_stations["station_id"] if usable_only else self.stations["station_id"])
        if self.observations.empty:
            return pd.DataFrame(index=self.timestamps, columns=ids, dtype=float)
        wide = self.observations.pivot_table(index="timestamp", columns="station_id", values="pm25", aggfunc="mean")
        return wide.reindex(index=self.timestamps, columns=ids).astype(float)

    def fingerprint(self) -> str:
        h = hashlib.sha1()
        h.update(self.city.id.encode())
        h.update(pd.util.hash_pandas_object(self.stations[["station_id", "latitude", "longitude"]], index=False).values.tobytes())
        if not self.observations.empty:
            obs = self.observations.sort_values(["station_id", "timestamp"])
            h.update(pd.util.hash_pandas_object(obs[["station_id", "timestamp", "pm25"]], index=False).values.tobytes())
        h.update(pd.util.hash_pandas_object(self.weather.fillna(-9999), index=False).values.tobytes())
        return h.hexdigest()[:16]


def _run_lengths(values: np.ndarray) -> np.ndarray:
    """Length of the run of identical consecutive values that each element belongs to."""
    n = len(values)
    if n == 0:
        return np.zeros(0, dtype=int)
    change = np.ones(n, dtype=bool)
    change[1:] = values[1:] != values[:-1]
    run_id = np.cumsum(change)
    counts = np.bincount(run_id)
    return counts[run_id]


class DataProcessor:
    def clean(self, ds: CityDataset) -> CityDataset:
        stations = self._clean_stations(ds)
        obs, obs_report, per_station = self._clean_observations(ds.observations, stations)
        weather, weather_report = self._clean_weather(ds.weather, obs)
        period_hours = len(weather)
        completeness = {sid: per_station.get(sid, 0) / max(period_hours, 1) for sid in stations["station_id"]}
        stations["n_valid"] = stations["station_id"].map(lambda s: int(per_station.get(s, 0)))
        stations["completeness"] = stations["station_id"].map(lambda s: round(float(completeness[s]), 4))
        stations["usable"] = stations["inside_domain"] & (stations["completeness"] >= MIN_COMPLETENESS)

        def flags(row) -> list[str]:
            f = []
            if not row["inside_domain"]:
                f.append("outside_analysis_domain")
            if row["completeness"] < MIN_COMPLETENESS:
                f.append("insufficient_data")
            return f

        stations["qc_flags"] = stations.apply(flags, axis=1)
        qc = {
            "rules": {
                "valid_range_ugm3": list(PM_VALID_RANGE),
                "stuck_min_run_hours": STUCK_MIN_RUN,
                "hampel_window_hours": HAMPEL_WINDOW,
                "hampel_k": HAMPEL_K,
                "min_completeness": MIN_COMPLETENESS,
                "max_weather_interpolation_hours": MAX_INTERP_GAP_H,
            },
            "observations": obs_report,
            "weather": weather_report,
            "stations": [
                {
                    "station_id": r.station_id,
                    "n_valid": int(r.n_valid),
                    "completeness": float(r.completeness),
                    "usable": bool(r.usable),
                    "flags": list(r.qc_flags),
                }
                for r in stations.itertuples()
            ],
            "period": {
                "start": weather["timestamp"].min().isoformat() if len(weather) else None,
                "end": weather["timestamp"].max().isoformat() if len(weather) else None,
                "hours": int(period_hours),
            },
        }
        return replace(ds, stations=stations, observations=obs, weather=weather, qc=qc)

    # ------------------------------------------------------------- stations
    def _clean_stations(self, ds: CityDataset) -> pd.DataFrame:
        st = ds.stations.copy()
        for col in STATION_COLUMNS:
            if col not in st:
                st[col] = None
        st = st.drop_duplicates(subset="station_id").reset_index(drop=True)
        st["latitude"] = pd.to_numeric(st["latitude"], errors="coerce")
        st["longitude"] = pd.to_numeric(st["longitude"], errors="coerce")
        st = st.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
        st["inside_domain"] = points_in_polygon(st["longitude"].to_numpy(), st["latitude"].to_numpy(), ds.city.boundary)
        st["synthetic"] = st["synthetic"].fillna(False).astype(bool)
        return st

    # --------------------------------------------------------- observations
    def _clean_observations(self, raw: pd.DataFrame, stations: pd.DataFrame) -> tuple[pd.DataFrame, dict, dict]:
        report = {"raw": int(len(raw)), "missing_or_non_numeric": 0, "duplicates_merged": 0, "unknown_station": 0,
                  "out_of_range": 0, "stuck": 0, "spikes": 0, "valid": 0}
        if raw.empty:
            return pd.DataFrame(columns=["station_id", "timestamp", "pm25"]), report, {}
        df = raw[["station_id", "timestamp", "pm25"]].copy()
        df["pm25"] = pd.to_numeric(df["pm25"], errors="coerce")
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        bad = df["pm25"].isna() | df["timestamp"].isna()
        report["missing_or_non_numeric"] = int(bad.sum())
        df = df[~bad]
        known = df["station_id"].isin(set(stations["station_id"]))
        report["unknown_station"] = int((~known).sum())
        df = df[known]
        df["timestamp"] = df["timestamp"].dt.floor("h")
        before = len(df)
        df = df.groupby(["station_id", "timestamp"], as_index=False)["pm25"].mean()
        report["duplicates_merged"] = int(before - len(df))
        out_of_range = (df["pm25"] < PM_VALID_RANGE[0]) | (df["pm25"] > PM_VALID_RANGE[1])
        report["out_of_range"] = int(out_of_range.sum())
        df = df[~out_of_range]

        cleaned, per_station = [], {}
        for sid, grp in df.groupby("station_id", sort=False):
            s = grp.set_index("timestamp")["pm25"].sort_index()
            full = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="h"))
            vals = full.to_numpy(dtype=float, copy=True)
            # stuck values: identical consecutive readings (NaN breaks a run)
            filled = np.where(np.isnan(vals), np.arange(len(vals)) * -1e9 - 1, vals)
            stuck = (_run_lengths(filled) >= STUCK_MIN_RUN) & ~np.isnan(vals)
            report["stuck"] += int(stuck.sum())
            vals[stuck] = np.nan
            # Hampel spike filter (positive spikes only)
            series = pd.Series(vals, index=full.index)
            med = series.rolling(HAMPEL_WINDOW, center=True, min_periods=3).median()
            mad = (series - med).abs().rolling(HAMPEL_WINDOW, center=True, min_periods=3).median()
            floor = np.maximum(2.0, 0.1 * med)
            scale = np.maximum(1.4826 * mad, floor)
            spikes = ((series - med) > HAMPEL_K * scale) & (series > 2.0 * med)
            spikes = spikes.fillna(False).to_numpy()
            report["spikes"] += int(spikes.sum())
            vals[spikes] = np.nan
            keep = ~np.isnan(vals)
            per_station[sid] = int(keep.sum())
            cleaned.append(pd.DataFrame({"station_id": sid, "timestamp": full.index[keep], "pm25": vals[keep]}))
        obs = pd.concat(cleaned, ignore_index=True) if cleaned else pd.DataFrame(columns=["station_id", "timestamp", "pm25"])
        report["valid"] = int(len(obs))
        return obs, report, per_station

    # -------------------------------------------------------------- weather
    def _clean_weather(self, raw: pd.DataFrame, obs: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
        report: dict = {"out_of_range": {}, "interpolated": {}, "remaining_missing": {}, "unavailable": []}
        w = raw.copy()
        w["timestamp"] = pd.to_datetime(w["timestamp"], utc=True, errors="coerce").dt.floor("h")
        w = w.dropna(subset=["timestamp"]).groupby("timestamp", as_index=False).mean(numeric_only=True)
        for col in WEATHER_COLUMNS:
            if col not in w:
                w[col] = np.nan
        if obs.empty and w.empty:
            return w, report
        start = obs["timestamp"].min() if not obs.empty else w["timestamp"].min()
        end = obs["timestamp"].max() if not obs.empty else w["timestamp"].max()
        index = pd.date_range(start, end, freq="h")
        w = w.set_index("timestamp").reindex(index)
        w.index.name = "timestamp"
        for col, (lo, hi) in WEATHER_RANGES.items():
            series = pd.to_numeric(w[col], errors="coerce")
            bad = (series < lo) | (series > hi)
            report["out_of_range"][col] = int(bad.sum())
            w[col] = series.mask(bad)
        # wind direction is circular: interpolate its unit-vector components
        rad = np.radians(w["wind_direction_deg"])
        u, v = np.sin(rad), np.cos(rad)
        for col in WEATHER_COLUMNS:
            if col == "wind_direction_deg":
                continue
            before = w[col].isna().sum()
            if w[col].notna().sum() >= 2:
                w[col] = w[col].interpolate(method="time", limit=MAX_INTERP_GAP_H, limit_area="inside")
            report["interpolated"][col] = int(before - w[col].isna().sum())
        before = w["wind_direction_deg"].isna().sum()
        if w["wind_direction_deg"].notna().sum() >= 2:
            u = u.interpolate(method="time", limit=MAX_INTERP_GAP_H, limit_area="inside")
            v = v.interpolate(method="time", limit=MAX_INTERP_GAP_H, limit_area="inside")
            w["wind_direction_deg"] = (np.degrees(np.arctan2(u, v)) + 360.0) % 360.0
        report["interpolated"]["wind_direction_deg"] = int(before - w["wind_direction_deg"].isna().sum())
        for col in WEATHER_COLUMNS:
            missing = int(w[col].isna().sum())
            report["remaining_missing"][col] = missing
            if missing == len(w):
                report["unavailable"].append(col)
        return w.reset_index(), report
