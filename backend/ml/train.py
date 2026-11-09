"""Reproducible training pipeline.

    python -m ml.train --city islamabad            # one city, full profile
    python -m ml.train --city all --profile fast   # every city, quick settings

Pipeline for one city
---------------------
1. Load the dataset (demo or live) and apply quality control.
2. Build features for every valid station-hour (see ml/features.py).
3. Leave-one-station-out (LOSO) cross-validation of the deployed ensemble and of
   transparent baselines (training mean, network mean, inverse distance weighting).
4. Fit an exponential variogram to LOSO residuals; calibrate the uncertainty
   model with nested LOSO conformal scaling (ml/uncertainty.py).
5. Permutation importance on held-out stations (marginal replacement, so that
   static station attributes are also tested).
6. Random K-fold over station-hours, reported only to show the optimism of
   non-spatial validation.
7. Fit the final ensemble on all stations; compute the period-average grid.
8. Demo mode only: OSSE scoring against the synthetic truth (ml/osse.py).
9. Save artifacts to ``models/<city>/``.

Why a fixed ensemble rather than "pick the best LOSO model"? With a handful of
mostly central stations, LOSO has very few folds and those folds are not
representative of the whole city, so it cannot reliably choose between model
families (Wadoux et al., 2021, Ecological Modelling 457). AirScope therefore
pre-specifies a multi-model ensemble (random forest + histogram gradient
boosting + XGBoost when installed) and uses LOSO to *report* honest
out-of-station skill against simple baselines - including when a baseline is
better - and to calibrate uncertainty.
"""
from __future__ import annotations

import argparse
import logging
import os
import platform
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.model_selection import KFold

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import get_settings, load_cities  # noqa: E402
from data.data_processor import CityDataset  # noqa: E402
from data.dataset_service import get_dataset_service  # noqa: E402
from geospatial.city_grid import get_city_grid  # noqa: E402
from geospatial.distance import nearest_distance_km  # noqa: E402
from .evaluation import regression_metrics, skill_score, summarize_models  # noqa: E402
from .features import (  # noqa: E402
    FEATURE_DESCRIPTIONS,
    ALL_FEATURES,
    FEATURE_GROUPS,
    FEATURE_SCHEMA_VERSION,
    MODEL_FEATURES,
    NETWORK_FEATURES,
    get_feature_builder,
    make_model_pipeline,
    model_features,
    validation_report,
)
from .predict import MEMBER_LABELS, CityModel, EnsembleModel, GridPredictor  # noqa: E402
from .uncertainty import (  # noqa: E402
    calibrate,
    default_params,
    empirical_variogram,
    fit_variogram,
    normalized_kriging_variance,
)

logger = logging.getLogger(__name__)

MIN_STATIONS_FOR_CV = 3
ProgressFn = Callable[[str, float], None]

try:  # optional dependency
    from xgboost import XGBRegressor  # type: ignore

    XGBOOST_AVAILABLE = True
except Exception:  # pragma: no cover - depends on environment
    XGBRegressor = None
    XGBOOST_AVAILABLE = False


class InsufficientDataError(RuntimeError):
    """Raised when a city has no usable station data to train on."""


@dataclass(frozen=True)
class TrainingProfile:
    name: str
    rf_estimators: int
    hgb_max_iter: int
    xgb_estimators: int
    quantile_max_iter: int
    permutation_repeats: int
    random_kfold_splits: int
    period_stride_h: int
    osse: bool
    osse_eval_stride_h: int
    osse_random_draws: int
    osse_k: int


PROFILES = {
    "full": TrainingProfile("full", 150, 300, 400, 200, 2, 5, 3, True, 20, 5, 5),
    "fast": TrainingProfile("fast", 40, 100, 120, 80, 0, 0, 8, False, 40, 1, 3),
}


def _n_jobs() -> int:
    return max(1, min(4, os.cpu_count() or 1))


def member_factories(profile: TrainingProfile, seed: int) -> dict[str, Callable]:
    factories: dict[str, Callable] = {
        "random_forest": lambda: RandomForestRegressor(
            n_estimators=profile.rf_estimators, min_samples_leaf=5, max_features=0.5, n_jobs=_n_jobs(), random_state=seed
        ),
        "gradient_boosting": lambda: HistGradientBoostingRegressor(
            max_iter=profile.hgb_max_iter, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=20,
            l2_regularization=1.0, random_state=seed
        ),
    }
    if XGBOOST_AVAILABLE:
        factories["xgboost"] = lambda: XGBRegressor(
            n_estimators=profile.xgb_estimators, max_depth=5, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
            min_child_weight=5, reg_lambda=1.0, tree_method="hist", n_jobs=_n_jobs(), random_state=seed, verbosity=0
        )
    return factories


def quantile_factories(profile: TrainingProfile, seed: int) -> dict[str, Callable]:
    def make(q: float):
        return lambda: HistGradientBoostingRegressor(
            loss="quantile", quantile=q, max_iter=profile.quantile_max_iter, learning_rate=0.05,
            max_leaf_nodes=15, min_samples_leaf=40, random_state=seed
        )

    return {"q05": make(0.05), "q95": make(0.95)}


def fit_ensemble(X: pd.DataFrame, y: np.ndarray, profile: TrainingProfile, seed: int, with_quantiles: bool = True,
                 features: list[str] | None = None) -> EnsembleModel:
    features = list(features or MODEL_FEATURES)
    Xf = X[features]
    members = {name: make_model_pipeline(f(), columns=features).fit(Xf, y) for name, f in member_factories(profile, seed).items()}
    quantiles = {}
    if with_quantiles:
        quantiles = {name: make_model_pipeline(f(), columns=features).fit(Xf, y) for name, f in quantile_factories(profile, seed).items()}
    return EnsembleModel(members, quantiles, features)


def hyperparameters(profile: TrainingProfile) -> dict:
    hp = {
        "random_forest": {"n_estimators": profile.rf_estimators, "min_samples_leaf": 5, "max_features": 0.5},
        "gradient_boosting": {"max_iter": profile.hgb_max_iter, "learning_rate": 0.05, "max_leaf_nodes": 31,
                              "min_samples_leaf": 20, "l2_regularization": 1.0},
        "quantiles": {"loss": "quantile", "quantiles": [0.05, 0.95], "max_iter": profile.quantile_max_iter},
    }
    if XGBOOST_AVAILABLE:
        hp["xgboost"] = {"n_estimators": profile.xgb_estimators, "max_depth": 5, "learning_rate": 0.05,
                         "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 5}
    return hp


# --------------------------------------------------------------------------- LOSO


def _rmse(a, b) -> float:
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


def _fold_importance(ens: EnsembleModel, X_te: pd.DataFrame, y_te: np.ndarray, pool: pd.DataFrame,
                     repeats: int, rng: np.random.Generator) -> tuple[dict, dict, float]:
    base = _rmse(y_te, ens.predict(X_te))
    n = len(X_te)
    used = set(ens.features)
    blocks, keys = [], []
    for r in range(repeats):
        for col in ens.features:
            Xp = X_te.copy()
            Xp[col] = pool[col].to_numpy()[rng.integers(0, len(pool), n)]
            blocks.append(Xp)
            keys.append(("feature", col))
        for group, all_cols in FEATURE_GROUPS.items():
            cols = [c for c in all_cols if c in used]
            if not cols:
                continue
            Xp = X_te.copy()
            idx = rng.integers(0, len(pool), n)
            Xp[cols] = pool[cols].to_numpy()[idx]
            blocks.append(Xp)
            keys.append(("group", group))
    preds = ens.predict(pd.concat(blocks, ignore_index=True))
    feat, grp = {}, {}
    for i, (kind, name) in enumerate(keys):
        inc = _rmse(y_te, preds[i * n : (i + 1) * n]) - base
        (feat if kind == "feature" else grp).setdefault(name, []).append(inc)
    return {k: float(np.mean(v)) for k, v in feat.items()}, {k: float(np.mean(v)) for k, v in grp.items()}, base


def run_loso(ds: CityDataset, ids: list[str], profile: TrainingProfile, seed: int, pool: pd.DataFrame,
             progress: ProgressFn | None = None, features: list[str] | None = None) -> tuple[pd.DataFrame, dict | None]:
    builder = get_feature_builder(ds.city)
    rows = []
    imp_feat: dict[str, list] = {}
    imp_grp: dict[str, list] = {}
    weights = []
    for i, h in enumerate(ids):
        if progress:
            progress(f"Spatial cross-validation: holding out station {i + 1}/{len(ids)}", 0.05 + 0.45 * i / len(ids))
        tr_ids = [s for s in ids if s != h]
        tr = builder.training_table(ds, tr_ids)
        te = builder.training_table(ds, [h], network_ids=tr_ids)
        if len(te.y) == 0 or len(tr.y) == 0:
            continue
        ens = fit_ensemble(tr.X, tr.y, profile, seed, features=features)
        comps = ens.predict_components(te.X)
        train_mean = float(np.mean(tr.y))
        df = pd.DataFrame({
            "station_id": h,
            "timestamp": te.timestamp,
            "y": te.y,
            "pred": comps["pred"],
            "sigma_model2": comps["sigma_model2"],
            "q05": comps["q05"],
            "q95": comps["q95"],
            "base_global_mean": train_mean,
            "base_network_mean": te.X["network_mean_pm25"].fillna(train_mean).to_numpy(),
            "base_idw": te.X["idw_pm25"].fillna(te.X["network_mean_pm25"]).fillna(train_mean).to_numpy(),
        })
        for name, p in comps["members"].items():
            df[f"pred_{name}"] = p
        rows.append(df)
        if profile.permutation_repeats > 0:
            f_imp, g_imp, _ = _fold_importance(ens, te.X, te.y, pool, profile.permutation_repeats, np.random.default_rng(seed + i))
            for k, v in f_imp.items():
                imp_feat.setdefault(k, []).append(v)
            for k, v in g_imp.items():
                imp_grp.setdefault(k, []).append(v)
            weights.append(len(te.y))
    oof = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    importance = None
    if weights:
        w = np.asarray(weights, dtype=float)
        base_rmse = regression_metrics(oof["y"], oof["pred"])["rmse"] or 1.0

        def summarize(d: dict) -> list[dict]:
            out = []
            for k, vals in d.items():
                v = np.asarray(vals)
                mean = float(np.sum(w * v) / w.sum())
                out.append({"name": k, "rmse_increase": round(mean, 4), "relative_pct": round(100 * mean / base_rmse, 2),
                            "fold_std": round(float(np.std(v)), 4)})
            return sorted(out, key=lambda r: r["rmse_increase"], reverse=True)

        features = summarize(imp_feat)
        group_of = {f: g for g, cols in FEATURE_GROUPS.items() for f in cols}
        for r in features:
            r["description"] = FEATURE_DESCRIPTIONS.get(r["name"], r["name"])
            r["group"] = group_of.get(r["name"])
        importance = {
            "method": "Permutation importance on held-out stations (LOSO): each feature is replaced by random draws "
                      "from its pooled distribution and the increase in RMSE (µg/m³) is averaged over folds.",
            "features": features,
            "groups": summarize(imp_grp),
        }
    return oof, importance


# --------------------------------------------------------------------------- main entry


def train_city(city_id: str, profile_name: str | None = None, dataset: CityDataset | None = None,
               models_dir: Path | None = None, progress: ProgressFn | None = None, seed: int | None = None) -> dict:
    settings = get_settings()
    profile = PROFILES[profile_name or settings.training_profile]
    seed = settings.random_seed if seed is None else seed
    models_dir = Path(models_dir or settings.models_dir)
    t0 = time.time()

    def step(msg: str, frac: float) -> None:
        logger.info("[%s] %s", city_id, msg)
        if progress:
            progress(msg, frac)

    step("Loading and quality-checking data", 0.01)
    ds = dataset or get_dataset_service().get(city_id)
    city = ds.city
    builder = get_feature_builder(city)
    grid = get_city_grid(city)
    stations = ds.training_stations
    ids = list(stations["station_id"])
    if not ids:
        raise InsufficientDataError(f"No usable monitoring stations for {city.name}")

    step("Building features", 0.03)
    features = model_features(settings.use_coordinate_features)
    tab = builder.training_table(ds, ids)
    if len(tab.y) == 0:
        raise InsufficientDataError(f"No valid PM2.5 observations for {city.name}")
    network_enabled = len(ids) >= 2
    if not network_enabled:
        tab.X[NETWORK_FEATURES] = np.nan

    metrics: dict = {
        "city_id": city.id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provenance": {k: ds.provenance.get(k) for k in ("mode", "synthetic", "label", "sources", "period_start", "period_end", "fallback")},
        "honesty_note": (
            "Computed on SYNTHETIC demo data (an OSSE nature run). These numbers show how the pipeline behaves on "
            "realistic simulated data; they are not a validation against real-world measurements."
            if ds.provenance.get("synthetic") else
            "Computed on live measurements via leave-one-station-out validation. With few stations these estimates are uncertain."
        ),
        "data": {
            "n_stations": len(ids),
            "n_observations": int(len(tab.y)),
            "period_start": ds.provenance.get("period_start"),
            "period_end": ds.provenance.get("period_end"),
            "qc": ds.qc.get("observations"),
            "feature_validation": {k: v for k, v in validation_report(tab.X).items() if v["missing"] or v["out_of_range"]},
        },
        "evaluation_available": len(ids) >= MIN_STATIONS_FOR_CV,
        "loso": None, "random_kfold": None, "calibration": None, "variogram": None,
        "feature_importance": None, "osse": None,
    }
    cv_out = None
    st_idx = stations.set_index("station_id")

    if len(ids) >= MIN_STATIONS_FOR_CV:
        oof, importance = run_loso(ds, ids, profile, seed, tab.X, progress=step, features=features)
        oof["r"] = np.log1p(oof["y"]) - np.log1p(oof["pred"])
        columns = {"AirScope ensemble": "pred"}
        columns.update({MEMBER_LABELS.get(m, m): f"pred_{m}" for m in member_factories(profile, seed)})
        columns.update({"Baseline: inverse distance weighting": "base_idw", "Baseline: network mean": "base_network_mean",
                        "Baseline: training mean": "base_global_mean"})
        model_table = summarize_models(oof, columns)
        ens_rmse = model_table[0]["rmse"]
        baselines = {r["model"]: r["rmse"] for r in model_table if r["model"].startswith("Baseline")}
        best_baseline = min(baselines, key=lambda k: baselines[k])

        step("Fitting spatial variogram and calibrating uncertainty", 0.52)
        resid_wide = oof.pivot_table(index="timestamp", columns="station_id", values="r")
        lat = st_idx.loc[resid_wide.columns, "latitude"].to_numpy()
        lon = st_idx.loc[resid_wide.columns, "longitude"].to_numpy()
        vario = fit_variogram(empirical_variogram(resid_wide, lat, lon), float(np.var(oof["r"])), city.correlation_length_km)
        rho_by_station = {}
        for h in ids:
            others = [s for s in ids if s != h]
            rho_by_station[h] = float(normalized_kriging_variance(
                [st_idx.loc[h, "latitude"]], [st_idx.loc[h, "longitude"]],
                st_idx.loc[others, "latitude"], st_idx.loc[others, "longitude"], vario.range_km, vario.nugget_ratio)[0])
        params, calib = calibrate(oof, rho_by_station, vario)

        per_station = []
        for sid, grp in oof.groupby("station_id"):
            others = [s for s in ids if s != sid]
            d, _ = nearest_distance_km([st_idx.loc[sid, "latitude"]], [st_idx.loc[sid, "longitude"]],
                                       st_idx.loc[others, "latitude"], st_idx.loc[others, "longitude"])
            m = regression_metrics(grp["y"], grp["pred"])
            per_station.append({
                "station_id": sid,
                "name": st_idx.loc[sid, "name"],
                "kind": st_idx.loc[sid, "kind"] if "kind" in st_idx else None,
                "n": m["n"], "rmse": m["rmse"], "mae": m["mae"], "bias": m["bias"],
                "rmse_idw": regression_metrics(grp["y"], grp["base_idw"])["rmse"],
                "rmse_network_mean": regression_metrics(grp["y"], grp["base_network_mean"])["rmse"],
                "nearest_other_station_km": round(float(d[0]), 2),
                "kriging_variance": round(rho_by_station[sid], 4),
                "mean_observed": round(float(grp["y"].mean()), 2),
            })
        metrics["loso"] = {
            "scheme": "Leave-one-station-out: each station is predicted by a model trained without it, using only the "
                      "other stations for network features.",
            "models": model_table,
            "per_station": per_station,
            "skill_vs_idw": skill_score(ens_rmse, baselines["Baseline: inverse distance weighting"]),
            "skill_vs_network_mean": skill_score(ens_rmse, baselines["Baseline: network mean"]),
            "best_baseline": best_baseline,
            "ensemble_beats_best_baseline": bool(ens_rmse < baselines[best_baseline]),
        }
        metrics["calibration"] = calib
        metrics["variogram"] = vario.to_dict()
        metrics["feature_importance"] = importance

        if profile.random_kfold_splits > 1:
            step("Random K-fold (for comparison only)", 0.58)
            kf = KFold(n_splits=profile.random_kfold_splits, shuffle=True, random_state=seed)
            preds = np.empty(len(tab.y))
            rf_factory = member_factories(profile, seed)["random_forest"]
            for tr_i, te_i in kf.split(tab.X):
                est = make_model_pipeline(rf_factory(), columns=features).fit(tab.X[features].iloc[tr_i], tab.y[tr_i])
                preds[te_i] = est.predict(tab.X[features].iloc[te_i])
            rk = regression_metrics(tab.y, preds)
            loso_rf = regression_metrics(oof["y"], oof["pred_random_forest"])
            metrics["random_kfold"] = {
                "model": "Random forest",
                "random_kfold": rk,
                "loso": loso_rf,
                "optimism_pct": round(100.0 * (1 - rk["rmse"] / loso_rf["rmse"]), 1) if loso_rf["rmse"] else None,
                "note": "Random K-fold lets neighbouring hours of the same station leak into training, so it "
                        "overstates accuracy at unmonitored locations. AirScope reports LOSO as its primary score.",
            }
        oof["sigma"] = params.sigma_total(oof["sigma_model2"], oof["station_id"].map(rho_by_station))
        lo, hi = params.interval(oof["pred"], oof["sigma"], 0.9)
        cv_out = pd.DataFrame({"station_id": oof["station_id"], "timestamp": oof["timestamp"],
                               "observed": oof["y"].round(2), "predicted": oof["pred"].round(2),
                               "lower": np.round(lo, 2), "upper": np.round(hi, 2)})
    else:
        resid_var = float(np.var(np.log1p(tab.y))) * 0.3 if len(tab.y) > 1 else None
        params = default_params(city.correlation_length_km, resid_var)

    step("Fitting final ensemble on all stations", 0.62)
    ensemble = fit_ensemble(tab.X, tab.y, profile, seed, features=features)
    meta = {
        "city_id": city.id,
        "city_name": city.name,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "profile": asdict(profile),
        "seed": seed,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "features": features,
        "observation_features": ALL_FEATURES,
        "coordinate_features": settings.use_coordinate_features,
        "network_features": network_enabled,
        "members": list(ensemble.members),
        "member_labels": {m: MEMBER_LABELS.get(m, m) for m in ensemble.members},
        "target_transform": "log1p",
        "dataset_fingerprint": ds.fingerprint(),
        "data_provenance": metrics["provenance"],
        "n_stations": len(ids),
        "n_observations": int(len(tab.y)),
        "evaluation_available": metrics["evaluation_available"],
        "xgboost_available": XGBOOST_AVAILABLE,
        "library_versions": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
                             "scikit-learn": sklearn.__version__},
    }
    model = CityModel(city.id, ensemble, params, meta, stations[["station_id", "latitude", "longitude"]])

    step("Computing period-average city grid", 0.7)
    predictor = GridPredictor(model, ds, builder, grid)
    model.period = predictor.compute_period(profile.period_stride_h)

    if ds.provenance.get("synthetic") and profile.osse:
        from .osse import run_osse

        metrics["osse"] = run_osse(model, ds, builder, grid, profile, seed, progress=step)
        if metrics["osse"] and "abs_error_map" in metrics["osse"]:
            model.period["osse_abs_error"] = np.asarray(metrics["osse"].pop("abs_error_map"))

    metrics["training"] = {
        "profile": profile.name,
        "seconds": round(time.time() - t0, 1),
        "members": [MEMBER_LABELS.get(m, m) for m in ensemble.members],
        "xgboost_available": XGBOOST_AVAILABLE,
        "hyperparameters": hyperparameters(profile),
        "target_transform": "log1p(PM2.5); predictions back-transformed with expm1",
        "uncertainty": params.to_dict(),
    }
    meta["training_seconds"] = metrics["training"]["seconds"]
    step("Saving model artifacts", 0.98)
    model.save(CityModel.dir_for(models_dir, city.id), metrics=metrics, cv_predictions=cv_out)
    step("Done", 1.0)
    return metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train AirScope models")
    parser.add_argument("--city", default="all", help="City id or 'all'")
    parser.add_argument("--profile", choices=sorted(PROFILES), default=None)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cities = list(load_cities()) if args.city == "all" else [args.city]
    for cid in cities:
        m = train_city(cid, args.profile)
        loso = m.get("loso") or {}
        ens = (loso.get("models") or [{}])[0]
        print(f"{cid}: trained in {m['training']['seconds']} s; LOSO RMSE {ens.get('rmse')} µg/m³ "
              f"(data: {m['provenance']['label']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
