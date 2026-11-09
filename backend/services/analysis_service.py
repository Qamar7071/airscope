"""Orchestrates datasets, models and analyses into API payloads.

The HTTP layer (api/routes.py) only parses requests and calls this service;
all domain logic lives in ml/, data/ and geospatial/.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

import numpy as np
import pandas as pd

from api.schemas import NotReadyError, ValidationError, full_grid_labels, full_grid_list, jsonable
from config import get_city, load_cities
from data.dataset_service import DatasetService, get_dataset_service
from geospatial.city_grid import domain_area_km2, get_city_grid
from geospatial.distance import nearest_distance_km
from geospatial.gazetteer import load_localities
from ml.aqi import PM25_BREAKPOINTS, WHO_24H_GUIDELINE, pm25_category, pm25_to_aqi
from ml.features import get_feature_builder
from ml.gaps import GAP_CLASSES, AnalysisContext, GapWeights, _range, analyze_gaps, scale
from ml.predict import CityModel, GridField, GridPredictor
from ml.sensor_placement import PlacementConstraints, recommend, simulate
from ml.uncertainty import default_params
from .model_registry import NO_DATA, ModelRegistry, get_registry

logger = logging.getLogger(__name__)

GAP_CODES = {name: i for i, (name, _thr) in enumerate(reversed(GAP_CLASSES))}  # low=0 ... critical=3


class AnalysisService:
    def __init__(self, registry: ModelRegistry | None = None, datasets: DatasetService | None = None):
        self.registry = registry or get_registry()
        self.datasets = datasets or get_dataset_service()
        self._predictors: dict[str, tuple[tuple, GridPredictor]] = {}
        self._osse_baselines: dict[tuple, dict] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------ plumbing
    def _model(self, city_id: str) -> CityModel | None:
        get_city(city_id)  # raises KeyError for unknown cities
        model = self.registry.get_model(city_id)
        if model is None:
            st = self.registry.status(city_id)
            if st.state == NO_DATA:
                return None
            raise NotReadyError(city_id, st.to_dict())
        return model

    def predictor(self, city_id: str) -> GridPredictor | None:
        model = self._model(city_id)
        if model is None:
            return None
        ds = self.datasets.get(city_id)
        key = (model.metadata.get("trained_at"), ds.fingerprint())
        with self._lock:
            hit = self._predictors.get(city_id)
            if hit and hit[0] == key:
                return hit[1]
        city = ds.city
        pred = GridPredictor(model, ds, get_feature_builder(city), get_city_grid(city))
        with self._lock:
            self._predictors[city_id] = (key, pred)
        return pred

    @staticmethod
    def _resolve(predictor: GridPredictor, time_param: str) -> pd.Timestamp | None:
        if time_param == "period":
            return None
        if time_param == "latest":
            ts = predictor.latest_timestamp()
            if ts is None:
                raise ValidationError("No hour with enough station data is available")
            return ts
        ts = pd.Timestamp(time_param)
        if ts not in set(predictor.valid_timestamps()):
            raise ValidationError("No station data for that hour; pick a timestamp from /timesteps")
        return ts

    def field(self, city_id: str, time_param: str) -> tuple[GridField | None, GridPredictor | None]:
        predictor = self.predictor(city_id)
        if predictor is None:
            return None, None
        ts = self._resolve(predictor, time_param)
        return (predictor.period() if ts is None else predictor.snapshot(ts)), predictor

    def context(self, city_id: str, time_param: str = "period") -> tuple[AnalysisContext, GridField | None]:
        field, predictor = self.field(city_id, time_param)
        ds = self.datasets.get(city_id)
        city = ds.city
        grid = get_city_grid(city)
        if predictor is None:  # no usable stations: coverage/population-only analysis
            builder = get_feature_builder(city)
            pop = builder.static_features(grid.inside_lat, grid.inside_lon)["population_density"].to_numpy()
            st = ds.stations[ds.stations.get("inside_domain", True) == True] if len(ds.stations) else ds.stations  # noqa: E712
            ctx = AnalysisContext(city, grid, np.zeros(grid.n_inside), np.zeros(grid.n_inside), pop,
                                  list(st.get("station_id", [])), st.get("latitude", pd.Series(dtype=float)).to_numpy(dtype=float),
                                  st.get("longitude", pd.Series(dtype=float)).to_numpy(dtype=float),
                                  default_params(city.correlation_length_km), mode="coverage-only", pm25_available=False)
            return ctx, None
        pop = predictor.static["population_density"].to_numpy()
        ctx = AnalysisContext(city, grid, field.pm25, field.sigma_model2, pop, list(predictor.station_ids),
                              predictor.st_lat, predictor.st_lon, predictor.model.params,
                              mode=field.mode, timestamp=field.timestamp)
        return ctx, field

    def provenance(self, city_id: str) -> dict:
        return jsonable(self.datasets.get(city_id).provenance)

    # ------------------------------------------------------------ catalogue
    def cities_payload(self) -> list[dict]:
        out = []
        for cid in load_cities():
            self.registry.get_model(cid)  # loads current artifacts and refreshes status
        statuses = self.registry.statuses()
        for cid, city in load_cities().items():
            ds = self.datasets.get(cid)
            out.append({
                **city.summary(),
                "boundary": city.boundary_geojson(),
                "n_stations": int(len(ds.stations)),
                "n_usable_stations": int(ds.stations["usable"].sum()) if "usable" in ds.stations else int(len(ds.stations)),
                "data_mode": ds.provenance.get("mode"),
                "data_label": ds.provenance.get("label"),
                "synthetic": bool(ds.provenance.get("synthetic")),
                "model_status": statuses.get(cid),
            })
        return out

    def city_payload(self, city_id: str) -> dict:
        city = get_city(city_id)
        ds = self.datasets.get(city_id)
        grid = get_city_grid(city)
        model = self.registry.get_model(city_id)
        return jsonable({
            **city.summary(),
            "boundary": city.boundary_geojson(),
            "domain_area_km2": round(domain_area_km2(city), 1),
            "grid": {"cells": grid.n_inside, "cell_km": grid.cell_km, "nrows": grid.nrows, "ncols": grid.ncols},
            "dataset": {
                "n_stations": int(len(ds.stations)),
                "n_usable_stations": int(ds.stations["usable"].sum()),
                "n_observations": int(len(ds.observations)),
                "period": ds.qc.get("period"),
                "qc": ds.qc,
            },
            "provenance": ds.provenance,
            "model_status": self.registry.status(city_id).to_dict(),
            "localities": [{"name": n, "lat": la, "lon": lo} for n, la, lo in load_localities().get(city_id, [])],
            "model": None if model is None else {
                "trained_at": model.metadata.get("trained_at"),
                "members": model.metadata.get("member_labels"),
                "n_stations": model.metadata.get("n_stations"),
                "evaluation_available": model.metadata.get("evaluation_available"),
                "uncertainty": model.params.to_dict(),
            },
        })

    # ------------------------------------------------------------ stations
    def stations_payload(self, city_id: str, time_param: str = "latest") -> dict:
        get_city(city_id)
        ds = self.datasets.get(city_id)
        wide = ds.obs_wide(usable_only=False)
        model = self.registry.get_model(city_id)
        loso = {s["station_id"]: s for s in ((model.metrics.get("loso") or {}).get("per_station") or [])} if model else {}
        ref_ts = None
        if time_param not in ("latest", "period"):
            ref_ts = pd.Timestamp(time_param)
        st = ds.stations
        lat = st["latitude"].to_numpy(dtype=float)
        lon = st["longitude"].to_numpy(dtype=float)
        stations = []
        for i, row in enumerate(st.itertuples()):
            series = wide[row.station_id] if row.station_id in wide else pd.Series(dtype=float)
            if ref_ts is not None:
                series_upto = series.loc[:ref_ts]
            else:
                series_upto = series
            valid = series_upto.dropna()
            latest_val = float(valid.iloc[-1]) if len(valid) else None
            latest_ts = valid.index[-1].isoformat() if len(valid) else None
            others = np.arange(len(st)) != i
            near = nearest_distance_km([lat[i]], [lon[i]], lat[others], lon[others])[0][0] if others.any() else None
            value_at = None
            if ref_ts is not None and ref_ts in series.index and np.isfinite(series.loc[ref_ts]):
                value_at = float(series.loc[ref_ts])
            stations.append({
                "id": row.station_id,
                "name": row.name,
                "lat": float(row.latitude),
                "lon": float(row.longitude),
                "kind": getattr(row, "kind", None),
                "provider": getattr(row, "provider", None),
                "license": getattr(row, "license", None),
                "synthetic": bool(getattr(row, "synthetic", False)),
                "usable": bool(getattr(row, "usable", True)),
                "qc_flags": list(getattr(row, "qc_flags", []) or []),
                "completeness": float(getattr(row, "completeness", np.nan)),
                "latest_pm25": None if latest_val is None else round(latest_val, 1),
                "latest_timestamp": latest_ts,
                "value_at_time": None if value_at is None else round(value_at, 1),
                "mean_pm25": None if series.dropna().empty else round(float(series.mean()), 1),
                "aqi": pm25_to_aqi(value_at if value_at is not None else latest_val),
                "aqi_category": pm25_category(value_at if value_at is not None else latest_val),
                "nearest_other_station_km": None if near is None or not np.isfinite(near) else round(float(near), 2),
                "loso": loso.get(row.station_id),
            })
        return jsonable({"city": city_id, "time": time_param, "stations": stations, "provenance": ds.provenance})

    def station_timeseries(self, city_id: str, station_id: str, hours: int = 168) -> dict:
        get_city(city_id)
        ds = self.datasets.get(city_id)
        if station_id not in set(ds.stations["station_id"]):
            raise KeyError(station_id)
        wide = ds.obs_wide(usable_only=False)
        series = wide[station_id].iloc[-hours:]
        model = self.registry.get_model(city_id)
        pred = lower = upper = [None] * len(series)
        loso = None
        if model is not None:
            cv = model.cv_predictions
            cv = cv[cv["station_id"] == station_id]
            if len(cv):
                cv = cv.copy()
                cv["timestamp"] = pd.to_datetime(cv["timestamp"], utc=True)
                cv = cv.set_index("timestamp").reindex(series.index)
                pred, lower, upper = cv["predicted"].tolist(), cv["lower"].tolist(), cv["upper"].tolist()
            loso = next((s for s in ((model.metrics.get("loso") or {}).get("per_station") or []) if s["station_id"] == station_id), None)
        return jsonable({
            "city": city_id,
            "station_id": station_id,
            "timestamps": [t.isoformat() for t in series.index],
            "observed": [None if pd.isna(v) else round(float(v), 1) for v in series],
            "predicted": pred,
            "lower": lower,
            "upper": upper,
            "loso": loso,
            "note": "Predicted values are leave-one-station-out estimates: the model never saw this station.",
        })

    def timesteps_payload(self, city_id: str) -> dict:
        city = get_city(city_id)
        predictor = self.predictor(city_id)
        ds = self.datasets.get(city_id)
        if predictor is not None:
            valid = predictor.valid_timestamps()
            counts = predictor.reporting_counts().reindex(valid)
        else:
            wide = ds.obs_wide(usable_only=False)
            counts = wide.notna().sum(axis=1)
            valid = counts.index[counts > 0]
            counts = counts.reindex(valid)
        return jsonable({
            "city": city_id,
            "timezone": city.timezone,
            "timestamps": [t.isoformat() for t in valid],
            "stations_reporting": [int(c) for c in counts],
            "latest": valid[-1].isoformat() if len(valid) else None,
            "period": ds.qc.get("period"),
        })

    def weather_payload(self, city_id: str, hours: int = 168) -> dict:
        get_city(city_id)
        ds = self.datasets.get(city_id)
        w = ds.weather.iloc[-hours:]
        net = ds.obs_wide().reindex(pd.DatetimeIndex(w["timestamp"])).mean(axis=1)
        return jsonable({
            "city": city_id,
            "timestamps": [t.isoformat() for t in w["timestamp"]],
            "temperature_c": w["temperature_c"].round(1).tolist(),
            "relative_humidity_pct": w["relative_humidity_pct"].round(1).tolist(),
            "wind_speed_ms": w["wind_speed_ms"].round(2).tolist(),
            "wind_direction_deg": w["wind_direction_deg"].round(0).tolist(),
            "boundary_layer_height_m": w["boundary_layer_height_m"].round(0).tolist(),
            "ventilation_index": (w["boundary_layer_height_m"] * w["wind_speed_ms"]).round(0).tolist(),
            "network_mean_pm25": [None if pd.isna(v) else round(float(v), 1) for v in net],
            "provenance": ds.provenance,
        })

    # ------------------------------------------------------------ grid & analyses
    def grid_payload(self, city_id: str, time_param: str) -> dict:
        ctx, field = self.context(city_id, time_param)
        grid = ctx.grid
        people = ctx.people
        total_people = float(people.sum()) or 1.0
        layers: dict[str, Any] = {
            "coverage": full_grid_list(grid, ctx.coverage(), 3),
            "population": full_grid_list(grid, ctx.population, 0),
            "nearest_station_km": full_grid_list(grid, ctx.nearest_station_km(), 2),
        }
        stats: dict[str, Any] = {"population_total": int(round(total_people))}
        if field is not None:
            pm = field.pm25
            rel = 100.0 * field.halfwidth / np.maximum(pm, 1.0)
            layers.update({
                "pm25": full_grid_list(grid, pm, 1),
                "lower": full_grid_list(grid, field.lower, 1),
                "upper": full_grid_list(grid, field.upper, 1),
                "uncertainty": full_grid_list(grid, field.halfwidth, 1),
                "relative_uncertainty": full_grid_list(grid, rel, 1),
                "uncertainty_score": full_grid_list(grid, scale(field.sigma_total, _range(field.sigma_total)), 3),
                "kriging_variance": full_grid_list(grid, field.rho, 3),
            })
            if field.osse_abs_error is not None:
                layers["osse_error"] = full_grid_list(grid, field.osse_abs_error, 1)
            aqi_rows = []
            for c_lo, c_hi, _ilo, _ihi, cat, color in PM25_BREAKPOINTS:
                sel = (pm >= c_lo) & (pm <= c_hi + 0.0999) if cat != "Hazardous" else (pm >= c_lo)
                aqi_rows.append({"category": cat, "color": color, "cells": int(sel.sum()),
                                 "area_km2": round(float(sel.sum() * ctx.cell_area_km2), 2),
                                 "population": int(round(float(people[sel].sum()))),
                                 "population_pct": round(100.0 * float(people[sel].sum()) / total_people, 2)})
            stats.update({
                "pm25": {
                    "min": round(float(pm.min()), 1), "max": round(float(pm.max()), 1), "mean": round(float(pm.mean()), 1),
                    "population_weighted_mean": round(float(np.sum(people * pm) / total_people), 1),
                    "p10": round(float(np.percentile(pm, 10)), 1), "p50": round(float(np.percentile(pm, 50)), 1),
                    "p90": round(float(np.percentile(pm, 90)), 1),
                },
                "aqi_distribution": aqi_rows,
                "population_above_who_24h": int(round(float(people[pm > WHO_24H_GUIDELINE].sum()))),
                "population_unhealthy": int(round(float(people[pm >= 55.5].sum()))),
                "uncertainty": {
                    "mean_halfwidth": round(float(field.halfwidth.mean()), 1),
                    "mean_relative_pct": round(float(rel.mean()), 1),
                    "max_relative_pct": round(float(rel.max()), 1),
                },
            })
        return jsonable({
            "city": city_id,
            "mode": ctx.mode,
            "timestamp": ctx.timestamp,
            "hours": None if field is None else field.hours,
            "n_stations_used": None if field is None else field.n_stations_used,
            "pm25_available": ctx.pm25_available,
            "geometry": grid.geometry(),
            "layers": layers,
            "stats": stats,
            "uncertainty_model": ctx.params.to_dict(),
            "coverage_radius_km": ctx.radius_km,
            "provenance": self.provenance(city_id),
        })

    def gaps_payload(self, city_id: str, time_param: str, weights: GapWeights) -> dict:
        ctx, _field = self.context(city_id, time_param)
        res = analyze_gaps(ctx, weights)
        grid = ctx.grid
        return jsonable({
            "city": city_id,
            "mode": ctx.mode,
            "timestamp": ctx.timestamp,
            "weights": res["weights"],
            "classes": res["classes"],
            "class_codes": GAP_CODES,
            "geometry": {"nrows": grid.nrows, "ncols": grid.ncols},
            "gap_index": full_grid_list(grid, res["gap_index"], 3),
            "labels": full_grid_labels(grid, res["labels"], GAP_CODES),
            "observation_deficit": full_grid_list(grid, res["observation_deficit"], 3),
            "exposure_need": full_grid_list(grid, res["exposure_need"], 3),
            "components": {k: full_grid_list(grid, v, 3) for k, v in res["components"].items()},
            "summary": res["summary"],
            "clusters": res["clusters"],
            "pm25_available": ctx.pm25_available,
            "provenance": self.provenance(city_id),
        })

    def recommendations_payload(self, city_id: str, time_param: str, weights: GapWeights, constraints: PlacementConstraints) -> dict:
        ctx, _field = self.context(city_id, time_param)
        res = recommend(ctx, weights, constraints)
        res.update({"city": city_id, "mode": ctx.mode, "timestamp": ctx.timestamp, "pm25_available": ctx.pm25_available,
                    "provenance": self.provenance(city_id)})
        return jsonable(res)

    def simulate_payload(self, city_id: str, time_param: str, weights: GapWeights, sites: list[tuple[float, float]]) -> dict:
        ctx, _field = self.context(city_id, time_param)
        try:
            res = simulate(ctx, weights, sites)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        res.update({"city": city_id, "mode": ctx.mode, "timestamp": ctx.timestamp, "provenance": self.provenance(city_id)})
        return jsonable(res)

    def metrics_payload(self, city_id: str) -> dict:
        model = self._model(city_id)
        if model is None:
            return {"city_id": city_id, "evaluation_available": False, "message": self.registry.status(city_id).message}
        out = dict(model.metrics)
        out["model"] = {
            "trained_at": model.metadata.get("trained_at"),
            "members": model.metadata.get("member_labels"),
            "features": model.metadata.get("features"),
            "network_features": model.metadata.get("network_features"),
            "target_transform": model.metadata.get("target_transform"),
            "library_versions": model.metadata.get("library_versions"),
        }
        return jsonable(out)

    # ------------------------------------------------------------ OSSE what-if
    def osse_payload(self, city_id: str, sites: list[tuple[float, float]]) -> dict:
        from data.demo_generator import get_nature_run
        from ml.evaluation import regression_metrics
        from ml.osse import _eval_times, _grid_predictions, augment_dataset
        from ml.train import PROFILES, fit_ensemble

        ds = self.datasets.get(city_id)
        if not ds.provenance.get("synthetic"):
            raise ValidationError("OSSE validation needs the synthetic truth and is only available in demo mode")
        if not sites:
            raise ValidationError("Add at least one site to test")
        predictor = self.predictor(city_id)
        if predictor is None:
            raise ValidationError("No model available for this city")
        grid = predictor.grid
        for la, lo in sites:
            if grid.locate(la, lo) < 0:
                raise ValidationError("All sites must lie inside the city's analysis domain")
        profile = PROFILES["fast"]
        nature = get_nature_run(city_id)
        times = _eval_times(predictor, profile.osse_eval_stride_h)
        idx = pd.DatetimeIndex(nature.timestamps).get_indexer(times)
        times, idx = times[idx >= 0], idx[idx >= 0]
        truth = nature.pm25(grid.inside_lat, grid.inside_lon, idx)
        w = np.tile(predictor.static["population_density"].to_numpy(), (len(times), 1))
        builder = predictor.builder
        seed = 42

        def score(extra):
            ds_aug = augment_dataset(ds, nature, extra, seed + 7)
            tab = builder.training_table(ds_aug, list(ds_aug.training_stations["station_id"]))
            ens = fit_ensemble(tab.X, tab.y, profile, seed, with_quantiles=False, features=predictor.model.ensemble.features)
            p = _grid_predictions(ens, ds_aug, builder, predictor.static, times)
            return {"rmse": regression_metrics(truth.ravel(), p.ravel())["rmse"],
                    "population_weighted_rmse": regression_metrics(truth.ravel(), p.ravel(), w.ravel())["rmse"]}

        key = (city_id, ds.fingerprint())
        with self._lock:
            base = self._osse_baselines.get(key)
        if base is None:
            base = score([])
            with self._lock:
                self._osse_baselines[key] = base
        res = score(sites)
        return jsonable({
            "city": city_id,
            "synthetic": True,
            "sites": [{"lat": a, "lon": b} for a, b in sites],
            "baseline": base,
            "with_sites": res,
            "improvement_pct": round(100 * (1 - res["rmse"] / base["rmse"]), 2),
            "pop_improvement_pct": round(100 * (1 - res["population_weighted_rmse"] / base["population_weighted_rmse"]), 2),
            "eval_hours": int(len(times)),
            "note": "Virtual sensors sample the synthetic truth; the ensemble is retrained (fast profile) and the "
                    "city-wide error is re-measured against the truth. Synthetic experiment - not a real-world guarantee.",
        })


_service: AnalysisService | None = None
_service_lock = threading.Lock()


def get_analysis_service() -> AnalysisService:
    global _service
    with _service_lock:
        if _service is None:
            _service = AnalysisService()
        return _service


def reset_analysis_service(service: AnalysisService | None = None) -> None:
    global _service
    with _service_lock:
        _service = service
