"""Prediction: the deployed ensemble, model artifacts, and city-wide grid fields.

Artifacts for a city live in ``models/<city_id>/``:
  model.joblib        fitted ensemble members and quantile models
  metadata.json       training metadata, data provenance, uncertainty parameters
  metrics.json        evaluation results (written by ml.train)
  cv_predictions.csv  leave-one-station-out predictions (for validation charts)
  period_grid.npz     period-average grid fields (used for planning views)
"""
from __future__ import annotations

import json
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from data.data_processor import CityDataset
from geospatial.city_grid import CityGrid
from .features import FeatureBuilder, MODEL_FEATURES, NETWORK_FEATURES
from .uncertainty import Z90, UncertaintyParams, normalized_kriging_variance

logger = logging.getLogger(__name__)

ARTIFACT_VERSION = 4
MEMBER_LABELS = {
    "random_forest": "Random forest",
    "gradient_boosting": "Histogram gradient boosting",
    "xgboost": "XGBoost",
}


class EnsembleModel:
    """Geometric-mean ensemble of tree models plus quantile models for spread."""

    def __init__(self, members: dict, quantiles: dict | None = None, features: list[str] | None = None):
        if not members:
            raise ValueError("Ensemble needs at least one member")
        self.members = members
        self.quantiles = quantiles or {}
        self.features = list(features or MODEL_FEATURES)

    def member_names(self) -> list[str]:
        return list(self.members)

    def predict_components(self, X: pd.DataFrame) -> dict:
        X = X[self.features]
        member_preds = {name: np.maximum(est.predict(X), 0.0) for name, est in self.members.items()}
        logs = np.log1p(np.vstack(list(member_preds.values())))
        log_pred = logs.mean(axis=0)
        sigma_mm = logs.std(axis=0) if len(self.members) > 1 else np.zeros(logs.shape[1])
        out = {"pred": np.expm1(log_pred), "log_pred": log_pred, "sigma_mm": sigma_mm, "members": member_preds}
        if "q05" in self.quantiles and "q95" in self.quantiles:
            q05 = np.maximum(self.quantiles["q05"].predict(X), 0.0)
            q95 = np.maximum(self.quantiles["q95"].predict(X), 0.0)
            lo, hi = np.minimum(q05, q95), np.maximum(q05, q95)
            sigma_q = (np.log1p(hi) - np.log1p(lo)) / (2.0 * Z90)
            out.update(q05=lo, q95=hi, sigma_q=sigma_q)
        else:
            out.update(q05=None, q95=None, sigma_q=np.zeros_like(log_pred))
        out["sigma_model2"] = out["sigma_q"] ** 2 + sigma_mm**2
        return out

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        X = X[self.features]
        logs = np.log1p(np.vstack([np.maximum(est.predict(X), 0.0) for est in self.members.values()]))
        return np.expm1(logs.mean(axis=0))


@dataclass
class GridField:
    """City-wide estimate on the inside cells of a :class:`CityGrid`."""

    mode: str  # "snapshot" | "period"
    timestamp: str | None
    pm25: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    sigma_total: np.ndarray
    sigma_model2: np.ndarray
    rho: np.ndarray
    n_stations_used: int
    hours: int = 1
    osse_abs_error: np.ndarray | None = None

    @property
    def halfwidth(self) -> np.ndarray:
        return (self.upper - self.lower) / 2.0


class CityModel:
    def __init__(self, city_id: str, ensemble: EnsembleModel, params: UncertaintyParams, metadata: dict,
                 stations: pd.DataFrame, period: dict | None = None, directory: Path | None = None):
        self.city_id = city_id
        self.ensemble = ensemble
        self.params = params
        self.metadata = metadata
        self.stations = stations.reset_index(drop=True)
        self.period = period
        self.directory = directory
        self._metrics: dict | None = None
        self._cv: pd.DataFrame | None = None

    # ---------------------------------------------------------------- io
    @staticmethod
    def dir_for(models_dir: Path, city_id: str) -> Path:
        return Path(models_dir) / city_id

    def save(self, directory: Path, metrics: dict | None = None, cv_predictions: pd.DataFrame | None = None) -> None:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        joblib.dump({"members": self.ensemble.members, "quantiles": self.ensemble.quantiles, "features": self.ensemble.features},
                    directory / "model.joblib", compress=3)
        meta = dict(self.metadata)
        meta["artifact_version"] = ARTIFACT_VERSION
        meta["uncertainty"] = self.params.to_dict()
        meta["stations"] = self.stations[["station_id", "latitude", "longitude"]].to_dict(orient="records")
        with open(directory / "metadata.json", "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2, default=str)
        if metrics is not None:
            with open(directory / "metrics.json", "w", encoding="utf-8") as fh:
                json.dump(metrics, fh, indent=1, default=_json_default)
        if cv_predictions is not None:
            cv_predictions.to_csv(directory / "cv_predictions.csv", index=False)
        if self.period is not None:
            np.savez_compressed(directory / "period_grid.npz", **{k: v for k, v in self.period.items() if isinstance(v, np.ndarray)})
            with open(directory / "period_meta.json", "w", encoding="utf-8") as fh:
                json.dump({k: v for k, v in self.period.items() if not isinstance(v, np.ndarray)}, fh, default=str)
        self.directory = directory

    @classmethod
    def load(cls, directory: Path) -> "CityModel":
        directory = Path(directory)
        with open(directory / "metadata.json", encoding="utf-8") as fh:
            meta = json.load(fh)
        if meta.get("artifact_version") != ARTIFACT_VERSION:
            raise ValueError(f"Model artifact version {meta.get('artifact_version')} != {ARTIFACT_VERSION}")
        blob = joblib.load(directory / "model.joblib")
        params = UncertaintyParams(**meta["uncertainty"])
        stations = pd.DataFrame(meta["stations"])
        period = None
        if (directory / "period_grid.npz").exists():
            with np.load(directory / "period_grid.npz") as npz:
                period = {k: npz[k] for k in npz.files}
            meta_path = directory / "period_meta.json"
            if meta_path.exists():
                with open(meta_path, encoding="utf-8") as fh:
                    period.update(json.load(fh))
        ensemble = EnsembleModel(blob["members"], blob["quantiles"], blob.get("features"))
        return cls(meta["city_id"], ensemble, params, meta, stations, period, directory)

    @property
    def metrics(self) -> dict:
        if self._metrics is None:
            path = self.directory / "metrics.json" if self.directory else None
            if path and path.exists():
                with open(path, encoding="utf-8") as fh:
                    self._metrics = json.load(fh)
            else:
                self._metrics = {}
        return self._metrics

    @property
    def cv_predictions(self) -> pd.DataFrame:
        if self._cv is None:
            path = self.directory / "cv_predictions.csv" if self.directory else None
            if path and path.exists():
                self._cv = pd.read_csv(path, parse_dates=["timestamp"])
            else:
                self._cv = pd.DataFrame(columns=["station_id", "timestamp", "observed", "predicted", "lower", "upper"])
        return self._cv


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    return str(o)


class GridPredictor:
    """Binds a trained model to a dataset and grid to produce city-wide fields."""

    CACHE_SIZE = 96

    def __init__(self, model: CityModel, dataset: CityDataset, builder: FeatureBuilder, grid: CityGrid):
        self.model = model
        self.dataset = dataset
        self.builder = builder
        self.grid = grid
        self.static = builder.static_features(grid.inside_lat, grid.inside_lon)
        known = set(dataset.stations["station_id"])
        self.station_ids = [s for s in model.stations["station_id"] if s in known]
        st = dataset.stations.set_index("station_id").loc[self.station_ids]
        self.st_lat = st["latitude"].to_numpy(dtype=float)
        self.st_lon = st["longitude"].to_numpy(dtype=float)
        self.wide = dataset.obs_wide(usable_only=False).reindex(columns=self.station_ids)
        self._cache: OrderedDict[str, GridField] = OrderedDict()
        self._rho_cache: dict[tuple, np.ndarray] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------ helpers
    def reporting_counts(self) -> pd.Series:
        return self.wide.notna().sum(axis=1)

    def valid_timestamps(self) -> pd.DatetimeIndex:
        counts = self.reporting_counts()
        need = min(2, len(self.station_ids))
        return pd.DatetimeIndex(counts.index[counts >= max(need, 1)])

    def latest_timestamp(self) -> pd.Timestamp | None:
        valid = self.valid_timestamps()
        return valid[-1] if len(valid) else None

    def _features(self, times: pd.DatetimeIndex, values: np.ndarray) -> pd.DataFrame:
        X = self.builder.target_features(None, None, times, self.dataset.weather, values, self.st_lat, self.st_lon, static=self.static)
        if not self.model.metadata.get("network_features", True):
            X[NETWORK_FEATURES] = np.nan  # trained without network context (single station)
        return X

    def rho_for(self, mask: np.ndarray) -> np.ndarray:
        key = tuple(bool(m) for m in mask)
        if key not in self._rho_cache:
            p = self.model.params
            self._rho_cache[key] = normalized_kriging_variance(
                self.grid.inside_lat, self.grid.inside_lon, self.st_lat[mask], self.st_lon[mask], p.range_km, p.nugget_ratio
            )
        return self._rho_cache[key]

    # ------------------------------------------------------------ fields
    def snapshot(self, ts: pd.Timestamp) -> GridField:
        ts = pd.Timestamp(ts)
        ts = ts.tz_localize("UTC") if ts.tz is None else ts.tz_convert("UTC")
        key = ts.isoformat()
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        if ts not in self.wide.index:
            raise KeyError(f"No data for {key}")
        values = self.wide.loc[ts].to_numpy(dtype=float)
        mask = ~np.isnan(values)
        X = self._features(pd.DatetimeIndex([ts]), values[None, :])
        comps = self.model.ensemble.predict_components(X)
        rho = self.rho_for(mask)
        sigma = self.model.params.sigma_total(comps["sigma_model2"], rho)
        lo, hi = self.model.params.interval(comps["pred"], sigma, 0.9)
        field = GridField("snapshot", key, comps["pred"], lo, hi, sigma, comps["sigma_model2"], rho, int(mask.sum()))
        with self._lock:
            self._cache[key] = field
            while len(self._cache) > self.CACHE_SIZE:
                self._cache.popitem(last=False)
        return field

    def period(self) -> GridField:
        p = self.model.period
        if p is None:
            raise RuntimeError("Model has no period summary")
        rho = self.rho_for(np.ones(len(self.station_ids), dtype=bool))
        sigma = self.model.params.sigma_total(p["sigma_model2_mean"], rho)
        lo, hi = self.model.params.interval(p["pm25_mean"], sigma, 0.9)
        return GridField("period", None, p["pm25_mean"], lo, hi, sigma, p["sigma_model2_mean"], rho,
                         len(self.station_ids), int(p.get("hours", 0)), p.get("osse_abs_error"))

    def compute_period(self, stride_h: int = 3, batch: int = 24) -> dict:
        """Average hourly predictions over the dataset period (every ``stride_h`` hours)."""
        valid = self.valid_timestamps()
        times = valid[:: max(1, stride_h)]
        n = self.grid.n_inside
        preds = np.empty((len(times), n))
        sm2_sum = np.zeros(n)
        values_all = self.wide.loc[times].to_numpy(dtype=float)
        for start in range(0, len(times), batch):
            tt = times[start : start + batch]
            vals = values_all[start : start + batch]
            X = self._features(tt, vals)
            comps = self.model.ensemble.predict_components(X)
            preds[start : start + len(tt)] = comps["pred"].reshape(len(tt), n)
            sm2_sum += comps["sigma_model2"].reshape(len(tt), n).sum(axis=0)
        return {
            "pm25_mean": preds.mean(axis=0),
            "pm25_p90": np.percentile(preds, 90, axis=0),
            "sigma_model2_mean": sm2_sum / max(len(times), 1),
            "hours": int(len(times)),
            "stride_h": int(stride_h),
            "start": times[0].isoformat() if len(times) else None,
            "end": times[-1].isoformat() if len(times) else None,
        }
