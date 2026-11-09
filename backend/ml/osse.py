"""Observing System Simulation Experiment (OSSE) - demo mode only.

Because the synthetic nature run is known everywhere, AirScope can measure what
is impossible to measure with real data alone:

1. **Reconstruction skill** - error of the city-wide map against the truth at
   every grid cell, including far from stations; whether 90 % intervals really
   cover ~90 % of cells; whether the uncertainty map ranks cells by their actual
   error (Spearman correlation).
2. **Placement benchmark** - for each strategy, virtual stations are "installed"
   at the chosen sites (sampling the nature run with reference-grade noise), the
   ensemble is retrained, and the city-wide error is re-measured. Strategies are
   compared with each other and with random placements.

All results are labelled synthetic. They show that the methodology behaves
sensibly; they do not prove real-world performance.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from typing import Callable

import numpy as np
import pandas as pd

from data.data_processor import CityDataset
from data.demo_generator import get_nature_run
from geospatial.city_grid import CityGrid
from .evaluation import interval_coverage, regression_metrics, spearman
from .features import FeatureBuilder
from .gaps import AnalysisContext, GapWeights
from .predict import CityModel, GridPredictor
from .sensor_placement import PlacementConstraints, STRATEGIES, select_sites

logger = logging.getLogger(__name__)

DISTANCE_BANDS = ((0.0, 1.0), (1.0, 2.0), (2.0, 4.0), (4.0, 8.0), (8.0, 1e9))


def _eval_times(predictor: GridPredictor, stride_h: int) -> pd.DatetimeIndex:
    valid = predictor.valid_timestamps()
    return valid[stride_h // 3 :: max(1, stride_h)]


def augment_dataset(ds: CityDataset, nature, sites: list[tuple[float, float]], seed: int) -> CityDataset:
    """Add virtual reference stations that sample the nature run."""
    if not sites:
        return ds
    lat = np.array([s[0] for s in sites])
    lon = np.array([s[1] for s in sites])
    obs = nature.observe(lat, lon, None, kind="reference", seed=seed)  # (T, k)
    ids = [f"OSSE-V{i + 1:02d}" for i in range(len(sites))]
    new_st = pd.DataFrame({
        "station_id": ids, "name": [f"Virtual site {i + 1}" for i in range(len(sites))], "latitude": lat, "longitude": lon,
        "kind": "reference", "provider": "OSSE", "license": "synthetic", "synthetic": True, "inside_domain": True,
        "n_valid": len(nature.timestamps), "completeness": 1.0, "usable": True, "qc_flags": [[] for _ in ids],
    })
    new_obs = pd.concat([
        pd.DataFrame({"station_id": sid, "timestamp": nature.timestamps, "pm25": obs[:, j]}) for j, sid in enumerate(ids)
    ], ignore_index=True)
    return replace(ds, stations=pd.concat([ds.stations, new_st], ignore_index=True),
                   observations=pd.concat([ds.observations, new_obs], ignore_index=True))


def _grid_predictions(ens, ds: CityDataset, builder: FeatureBuilder, static: pd.DataFrame, times: pd.DatetimeIndex) -> np.ndarray:
    ids = list(ds.training_stations["station_id"])
    st = ds.stations.set_index("station_id").loc[ids]
    vals = ds.obs_wide(usable_only=False).reindex(index=times, columns=ids).to_numpy(dtype=float)
    X = builder.target_features(None, None, times, ds.weather, vals, st["latitude"], st["longitude"], static=static)
    return ens.predict(X).reshape(len(times), -1)


def run_osse(model: CityModel, ds: CityDataset, builder: FeatureBuilder, grid: CityGrid, profile, seed: int,
             progress: Callable[[str, float], None] | None = None) -> dict:
    from .train import fit_ensemble  # local import avoids a cycle

    nature = get_nature_run(ds.city.id)
    predictor = GridPredictor(model, ds, builder, grid)
    times = _eval_times(predictor, profile.osse_eval_stride_h)
    t_index = pd.DatetimeIndex(nature.timestamps)
    eval_idx = t_index.get_indexer(times)
    keep = eval_idx >= 0
    times, eval_idx = times[keep], eval_idx[keep]
    if len(times) == 0:
        return {}
    if progress:
        progress("OSSE: scoring the city-wide map against the synthetic truth", 0.74)
    truth = nature.pm25(grid.inside_lat, grid.inside_lon, eval_idx)  # (T, N)
    pop = predictor.static["population_density"].to_numpy()
    fields = [predictor.snapshot(t) for t in times]
    pred = np.vstack([f.pm25 for f in fields])
    lo = np.vstack([f.lower for f in fields])
    hi = np.vstack([f.upper for f in fields])
    sig = np.vstack([f.sigma_total for f in fields])
    w = np.tile(pop, (len(times), 1))
    abs_err = np.abs(pred - truth)
    log_err = np.abs(np.log1p(pred) - np.log1p(truth))

    st_lat, st_lon = predictor.st_lat, predictor.st_lon
    from geospatial.distance import nearest_distance_km

    near, _ = nearest_distance_km(grid.inside_lat, grid.inside_lon, st_lat, st_lon)
    bands = []
    for a, b in DISTANCE_BANDS:
        sel = (near >= a) & (near < b)
        if not sel.any():
            continue
        bands.append({
            "band": f"{a:g}-{b:g} km" if b < 1e8 else f">{a:g} km",
            "cells": int(sel.sum()),
            "rmse": regression_metrics(truth[:, sel].ravel(), pred[:, sel].ravel())["rmse"],
            "interval_coverage_90": interval_coverage(truth[:, sel], lo[:, sel], hi[:, sel]),
            "mean_sigma_log": round(float(sig[:, sel].mean()), 4),
        })
    # IDW map baseline on the same grid
    vals = predictor.wide.reindex(index=times).to_numpy(dtype=float)
    from geospatial.distance import pairwise_haversine_km

    d = pairwise_haversine_km(grid.inside_lat, grid.inside_lon, st_lat, st_lon)
    _mean, idw = builder.network_features(vals, d)
    reconstruction = {
        "metrics": regression_metrics(truth.ravel(), pred.ravel()),
        "population_weighted": regression_metrics(truth.ravel(), pred.ravel(), w.ravel()),
        "idw_baseline": regression_metrics(truth.ravel(), idw.ravel()),
        "interval_coverage_90": interval_coverage(truth, lo, hi),
        "coverage_by_distance": bands,
        "uncertainty_error_spearman": spearman(sig.mean(axis=0), log_err.mean(axis=0)),
        "spatial_pattern_correlation": round(float(np.corrcoef(pred.mean(axis=0), truth.mean(axis=0))[0, 1]), 4),
    }

    # ---------------------------------------------------------------- placement benchmark
    period = predictor.period()
    ctx = AnalysisContext(ds.city, grid, period.pm25, period.sigma_model2, pop, list(predictor.station_ids),
                          st_lat, st_lon, model.params, mode="period")
    weights = GapWeights()
    k = profile.osse_k
    sites: dict[str, list[tuple[float, float]]] = {}
    for strategy in ("coverage", "variance", "population"):
        picks = select_sites(ctx, weights, PlacementConstraints(k=k, strategy=strategy))
        sites[strategy] = [(float(ctx.lat[j]), float(ctx.lon[j])) for j, _ in picks]
    random_sets = []
    for r in range(profile.osse_random_draws):
        picks = select_sites(ctx, weights, PlacementConstraints(k=k, strategy="random", seed=seed + 100 + r))
        random_sets.append([(float(ctx.lat[j]), float(ctx.lon[j])) for j, _ in picks])

    static = predictor.static

    def score(extra: list[tuple[float, float]], label: str) -> dict:
        ds_aug = augment_dataset(ds, nature, extra, seed + 7)
        ids = list(ds_aug.training_stations["station_id"])
        tab = builder.training_table(ds_aug, ids)
        ens = fit_ensemble(tab.X, tab.y, profile, seed, with_quantiles=False, features=model.ensemble.features)
        p = _grid_predictions(ens, ds_aug, builder, static, times)
        return {
            "rmse": regression_metrics(truth.ravel(), p.ravel())["rmse"],
            "population_weighted_rmse": regression_metrics(truth.ravel(), p.ravel(), w.ravel())["rmse"],
        }

    scenarios = []
    n_total = 1 + len(sites) + len(random_sets)
    done = 0

    def tick(label):
        nonlocal done
        done += 1
        if progress:
            progress(f"OSSE: testing placement scenario {done}/{n_total} ({label})", 0.76 + 0.2 * done / n_total)

    base = score([], "baseline")
    tick("current network")
    scenarios.append({"key": "baseline", "label": "Current network", **base, "improvement_pct": 0.0, "pop_improvement_pct": 0.0})
    for strategy, s in sites.items():
        res = score(s, strategy)
        tick(strategy)
        scenarios.append({
            "key": strategy, "label": f"+{len(s)} sites: {STRATEGIES[strategy]}", **res,
            "improvement_pct": round(100 * (1 - res["rmse"] / base["rmse"]), 2),
            "pop_improvement_pct": round(100 * (1 - res["population_weighted_rmse"] / base["population_weighted_rmse"]), 2),
            "sites": [{"lat": round(a, 5), "lon": round(b, 5)} for a, b in s],
        })
    rand = []
    for i, s in enumerate(random_sets):
        res = score(s, "random")
        tick(f"random draw {i + 1}")
        rand.append({
            **res,
            "improvement_pct": round(100 * (1 - res["rmse"] / base["rmse"]), 2),
            "pop_improvement_pct": round(100 * (1 - res["population_weighted_rmse"] / base["population_weighted_rmse"]), 2),
        })
    if rand:
        imp = np.array([r["improvement_pct"] for r in rand])
        for sc in scenarios:
            if sc["key"] in ("coverage", "variance", "population"):
                sc["beats_random_draws"] = int(np.sum(imp < sc["improvement_pct"]))
                sc["random_draws"] = int(len(imp))
        pimp = np.array([r["pop_improvement_pct"] for r in rand])
        scenarios.append({
            "key": "random", "label": f"+{k} sites: random eligible (mean of {len(rand)} draws)",
            "rmse": round(float(np.mean([r["rmse"] for r in rand])), 3),
            "population_weighted_rmse": round(float(np.mean([r["population_weighted_rmse"] for r in rand])), 3),
            "improvement_pct": round(float(imp.mean()), 2), "improvement_std": round(float(imp.std()), 2),
            "pop_improvement_pct": round(float(pimp.mean()), 2), "pop_improvement_std": round(float(pimp.std()), 2),
            "draws": rand,
        })
    return {
        "description": "Observing System Simulation Experiment on the synthetic nature run. Errors are measured "
                       "against the known synthetic truth at every grid cell.",
        "synthetic": True,
        "eval_hours": int(len(times)),
        "cells": int(grid.n_inside),
        "reconstruction": reconstruction,
        "placement_benchmark": {"k": k, "weights": weights.to_dict(), "scenarios": scenarios},
        "abs_error_map": abs_err.mean(axis=0),
    }
