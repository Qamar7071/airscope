"""Evaluation metrics and summaries.

All metrics here are *computed* from model predictions; nothing is hard-coded.
The provenance of the underlying data (synthetic demo vs live measurements) is
attached by the training pipeline, and the UI states it next to every number.

Validation schemes used by AirScope:
  * leave-one-station-out (LOSO) spatial cross-validation - the primary score,
    because AirScope's job is to estimate PM2.5 where there is no station;
  * random K-fold over station-hours - reported only to show how optimistic a
    non-spatial split is (neighbouring hours of the same station leak information);
  * in demo mode, an OSSE comparison against the full synthetic truth field.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def regression_metrics(y, pred, weights=None) -> dict:
    y = np.asarray(y, dtype=float)
    pred = np.asarray(pred, dtype=float)
    ok = np.isfinite(y) & np.isfinite(pred)
    y, pred = y[ok], pred[ok]
    w = np.ones_like(y) if weights is None else np.asarray(weights, dtype=float)[ok]
    if len(y) == 0 or w.sum() <= 0:
        return {"n": 0, "rmse": None, "mae": None, "bias": None, "r2": None, "nrmse": None}
    err = pred - y
    rmse = float(np.sqrt(np.sum(w * err**2) / w.sum()))
    mae = float(np.sum(w * np.abs(err)) / w.sum())
    bias = float(np.sum(w * err) / w.sum())
    ybar = float(np.sum(w * y) / w.sum())
    ss_tot = float(np.sum(w * (y - ybar) ** 2))
    r2 = float(1.0 - np.sum(w * err**2) / ss_tot) if ss_tot > 0 else None
    return {
        "n": int(len(y)),
        "rmse": round(rmse, 3),
        "mae": round(mae, 3),
        "bias": round(bias, 3),
        "r2": None if r2 is None else round(r2, 4),
        "nrmse": round(rmse / ybar, 4) if ybar > 0 else None,
    }


def skill_score(rmse_model: float | None, rmse_reference: float | None) -> float | None:
    """1 - RMSE_model / RMSE_reference (positive = better than the reference)."""
    if rmse_model is None or not rmse_reference:
        return None
    return round(1.0 - rmse_model / rmse_reference, 4)


def spearman(a, b) -> float | None:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3 or np.std(a[ok]) == 0 or np.std(b[ok]) == 0:
        return None
    return round(float(stats.spearmanr(a[ok], b[ok]).statistic), 4)


def interval_coverage(y, lo, hi) -> float | None:
    y, lo, hi = (np.asarray(v, dtype=float) for v in (y, lo, hi))
    ok = np.isfinite(y) & np.isfinite(lo) & np.isfinite(hi)
    if not ok.any():
        return None
    return round(float(np.mean((y[ok] >= lo[ok]) & (y[ok] <= hi[ok]))), 4)


def per_group_metrics(df: pd.DataFrame, group_col: str, y_col: str, pred_col: str) -> dict[str, dict]:
    return {str(g): regression_metrics(sub[y_col], sub[pred_col]) for g, sub in df.groupby(group_col)}


def summarize_models(oof: pd.DataFrame, columns: dict[str, str]) -> list[dict]:
    """One row per model/baseline: overall metrics plus mean per-station RMSE."""
    rows = []
    for label, col in columns.items():
        if col not in oof:
            continue
        overall = regression_metrics(oof["y"], oof[col])
        per_station = per_group_metrics(oof, "station_id", "y", col)
        st_rmse = [m["rmse"] for m in per_station.values() if m["rmse"] is not None]
        rows.append({
            "model": label,
            **overall,
            "station_rmse_mean": round(float(np.mean(st_rmse)), 3) if st_rmse else None,
            "station_rmse_max": round(float(np.max(st_rmse)), 3) if st_rmse else None,
        })
    return rows
