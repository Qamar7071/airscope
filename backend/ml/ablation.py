"""Reproducible ablation of how location enters the model (demo mode).

    python -m ml.ablation                    # all cities
    python -m ml.ablation --city islamabad

Compares three ways of giving the tree ensemble location information:
  raw   - latitude and longitude as features
  none  - no raw coordinates (location enters via elevation, distance to centre,
          population density and the IDW network feature) - AirScope's default
  ogc   - oblique geographic coordinates: the local frame rotated by 30/60/120/150°
          (Møller et al., 2020, SOIL 6, 269-289)

For each variant it reports leave-one-station-out RMSE and, using the synthetic
truth, city-wide RMSE and the spatial-pattern correlation. Synthetic data only.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import load_cities  # noqa: E402
from data.dataset_service import get_dataset_service  # noqa: E402
from data.demo_generator import get_nature_run  # noqa: E402
from geospatial.city_grid import get_city_grid  # noqa: E402
from geospatial.distance import to_local_km  # noqa: E402
from .features import ALL_FEATURES, MODEL_FEATURES, get_feature_builder  # noqa: E402
from .train import PROFILES, fit_ensemble  # noqa: E402

OGC_ANGLES = (30, 60, 120, 150)
OGC = [f"ogc_{a}" for a in OGC_ANGLES]


def _with_ogc(X: pd.DataFrame, lat0: float, lon0: float) -> pd.DataFrame:
    X = X.copy()
    x, y = to_local_km(X["latitude"].to_numpy(), X["longitude"].to_numpy(), lat0, lon0)
    for name, ang in zip(OGC, OGC_ANGLES):
        t = np.radians(ang)
        X[name] = x * np.cos(t) + y * np.sin(t)
    return X


def _rmse(a, b) -> float:
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


def run_city(city_id: str, profile_name: str = "full", seed: int = 42, stride_h: int = 20) -> list[dict]:
    ds = get_dataset_service().get(city_id)
    if not ds.provenance.get("synthetic"):
        raise SystemExit("The ablation needs the synthetic truth: run it in demo mode.")
    profile = PROFILES[profile_name]
    city = ds.city
    b = get_feature_builder(city)
    ids = list(ds.training_stations["station_id"])
    grid = get_city_grid(city)
    nature = get_nature_run(city_id)
    t_idx = np.arange(stride_h // 3, len(nature.timestamps), stride_h)
    wide = ds.obs_wide()
    st = ds.stations.set_index("station_id").loc[ids]
    static = b.static_features(grid.inside_lat, grid.inside_lon)
    Xg = b.target_features(None, None, wide.index[t_idx], ds.weather, wide.to_numpy()[t_idx], st["latitude"], st["longitude"], static=static)
    truth = nature.pm25(grid.inside_lat, grid.inside_lon, t_idx)
    folds = [(b.training_table(ds, [s for s in ids if s != h]), b.training_table(ds, [h], network_ids=[s for s in ids if s != h])) for h in ids]
    tab = b.training_table(ds, ids)
    variants = {"raw": list(ALL_FEATURES), "none": list(MODEL_FEATURES), "ogc": list(MODEL_FEATURES) + OGC}
    out = []
    for name, feats in variants.items():
        prep = (lambda X: _with_ogc(X, city.center_lat, city.center_lon)) if name == "ogc" else (lambda X: X)
        ys, ps = [], []
        for tr, te in folds:
            ens = fit_ensemble(prep(tr.X), tr.y, profile, seed, with_quantiles=False, features=feats)
            ys.append(te.y)
            ps.append(ens.predict(prep(te.X)))
        ens = fit_ensemble(prep(tab.X), tab.y, profile, seed, with_quantiles=False, features=feats)
        pg = ens.predict(prep(Xg)).reshape(len(t_idx), -1)
        out.append({
            "city": city_id,
            "variant": name,
            "loso_rmse": round(_rmse(np.concatenate(ys), np.concatenate(ps)), 2),
            "grid_rmse": round(_rmse(truth.ravel(), pg.ravel()), 2),
            "spatial_corr": round(float(np.corrcoef(pg.mean(axis=0), truth.mean(axis=0))[0, 1]), 3),
        })
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Coordinate-feature ablation (demo mode)")
    parser.add_argument("--city", default="all")
    parser.add_argument("--profile", default="full", choices=sorted(PROFILES))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    cities = list(load_cities()) if args.city == "all" else [args.city]
    print("| City | Variant | LOSO RMSE | Grid RMSE (vs synthetic truth) | Spatial pattern corr. |")
    print("|---|---|---|---|---|")
    for cid in cities:
        for r in run_city(cid, args.profile):
            print(f"| {r['city']} | {r['variant']} | {r['loso_rmse']} | {r['grid_rmse']} | {r['spatial_corr']} |", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
