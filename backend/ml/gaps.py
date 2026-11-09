"""Monitoring blind-spot detection: the Monitoring Gap Index (MGI).

For every grid cell AirScope computes four components in [0, 1]:

  D  coverage deficit     1 - C, with C = 1 - prod_s (1 - exp(-d_s / R)) the
                          probability that at least one station represents the
                          cell (R = station representativeness radius)
  U  uncertainty          calibrated predictive sigma (relative, log units),
                          robustly scaled across the city
  P  pollution            estimated PM2.5, robustly scaled across the city
  Pop population          log population density, robustly scaled

They are combined in two stages:

  Observation deficit  O = (w_D D + w_U U) / (w_D + w_U)   "how poorly observed"
  Exposure need        N = (w_P P + w_Pop Pop) / (w_P + w_Pop)  "how much it matters"
  MGI = O^alpha * N^(1 - alpha)           (weighted geometric mean, alpha = balance)

The geometric mean means a blind spot must be BOTH poorly observed AND
important: a well-monitored dense district, or an uninhabited forest far from
any station, does not score highly. (The same reasoning moved the UN Human
Development Index from an arithmetic to a geometric mean in 2010.)

Robust scaling uses the 2nd-98th percentiles of the *baseline* network, and the
same scaling is reused for "after" scenarios so before/after scores are
directly comparable.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from config import CityConfig
from geospatial.city_grid import CityGrid
from geospatial.distance import nearest_distance_km, pairwise_haversine_km
from geospatial.gazetteer import describe_location
from geospatial.spatial_utils import label_regions
from .uncertainty import UncertaintyParams, normalized_kriging_variance

GAP_CLASSES = (("critical", 0.75), ("high", 0.60), ("moderate", 0.45), ("low", 0.0))
CLUSTER_MIN_CELLS = 2


@dataclass(frozen=True)
class GapWeights:
    coverage: float = 0.5
    uncertainty: float = 0.5
    pollution: float = 0.5
    population: float = 0.5
    balance: float = 0.5  # alpha: 1 = only observation deficit, 0 = only exposure need

    def validated(self) -> "GapWeights":
        vals = [self.coverage, self.uncertainty, self.pollution, self.population, self.balance]
        if any((v is None) or (not np.isfinite(v)) for v in vals):
            raise ValueError("Gap weights must be finite numbers")
        if min(vals[:4]) < 0:
            raise ValueError("Gap weights must be non-negative")
        if not 0.0 <= self.balance <= 1.0:
            raise ValueError("balance must be between 0 and 1")
        if self.coverage + self.uncertainty == 0 and self.pollution + self.population == 0:
            raise ValueError("At least one gap weight must be positive")
        return self

    def to_dict(self) -> dict:
        return {"coverage": self.coverage, "uncertainty": self.uncertainty, "pollution": self.pollution,
                "population": self.population, "balance": self.balance}


@dataclass
class Scaling:
    """Percentile ranges fixed on the baseline network."""

    uncertainty: tuple[float, float]
    pollution: tuple[float, float]
    population: tuple[float, float]


def _range(x: np.ndarray, lo_pct: float = 2.0, hi_pct: float = 98.0) -> tuple[float, float]:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return 0.0, 1.0
    lo, hi = float(np.percentile(x, lo_pct)), float(np.percentile(x, hi_pct))
    return (lo, hi) if hi > lo else (lo, lo + 1e-9)


def scale(x, rng: tuple[float, float]) -> np.ndarray:
    lo, hi = rng
    return np.clip((np.asarray(x, dtype=float) - lo) / (hi - lo), 0.0, 1.0)


def coverage_probability(lat, lon, s_lat, s_lon, radius_km: float) -> np.ndarray:
    """P(cell represented by >= 1 station) with exponential distance decay."""
    lat = np.asarray(lat, dtype=float)
    s_lat = np.atleast_1d(np.asarray(s_lat, dtype=float))
    if s_lat.size == 0:
        return np.zeros(lat.shape)
    d = pairwise_haversine_km(lat, lon, s_lat, s_lon)
    miss = np.prod(1.0 - np.exp(-d / radius_km), axis=1)
    return 1.0 - miss


@dataclass
class AnalysisContext:
    """Everything gap analysis and sensor placement need about one city view."""

    city: CityConfig
    grid: CityGrid
    pm25: np.ndarray
    sigma_model2: np.ndarray
    population: np.ndarray
    station_ids: list[str]
    station_lat: np.ndarray
    station_lon: np.ndarray
    params: UncertaintyParams
    mode: str = "period"
    timestamp: str | None = None
    pm25_available: bool = True
    _cache: dict = field(default_factory=dict, repr=False)

    @property
    def lat(self) -> np.ndarray:
        return self.grid.inside_lat

    @property
    def lon(self) -> np.ndarray:
        return self.grid.inside_lon

    @property
    def radius_km(self) -> float:
        return self.city.coverage_radius_km

    @property
    def cell_area_km2(self) -> float:
        return self.grid.cell_area_km2

    @property
    def people(self) -> np.ndarray:
        """Estimated residents per cell (density x cell area)."""
        return self.population * self.cell_area_km2

    def network(self, extra_lat=None, extra_lon=None) -> tuple[np.ndarray, np.ndarray]:
        if extra_lat is None or len(extra_lat) == 0:
            return self.station_lat, self.station_lon
        return (np.concatenate([self.station_lat, np.asarray(extra_lat, dtype=float)]),
                np.concatenate([self.station_lon, np.asarray(extra_lon, dtype=float)]))

    def rho(self, extra_lat=None, extra_lon=None) -> np.ndarray:
        key = ("rho", tuple(np.round(extra_lat, 6)) if extra_lat is not None else (), tuple(np.round(extra_lon, 6)) if extra_lon is not None else ())
        if key not in self._cache:
            s_lat, s_lon = self.network(extra_lat, extra_lon)
            self._cache[key] = normalized_kriging_variance(self.lat, self.lon, s_lat, s_lon, self.params.range_km, self.params.nugget_ratio)
        return self._cache[key]

    def sigma_total(self, extra_lat=None, extra_lon=None) -> np.ndarray:
        return self.params.sigma_total(self.sigma_model2, self.rho(extra_lat, extra_lon))

    def coverage(self, extra_lat=None, extra_lon=None) -> np.ndarray:
        s_lat, s_lon = self.network(extra_lat, extra_lon)
        return coverage_probability(self.lat, self.lon, s_lat, s_lon, self.radius_km)

    def nearest_station_km(self, extra_lat=None, extra_lon=None) -> np.ndarray:
        s_lat, s_lon = self.network(extra_lat, extra_lon)
        d, _ = nearest_distance_km(self.lat, self.lon, s_lat, s_lon)
        return d

    def baseline_scaling(self) -> Scaling:
        if "scaling" not in self._cache:
            self._cache["scaling"] = Scaling(
                uncertainty=_range(self.sigma_total()),
                pollution=_range(self.pm25) if self.pm25_available else (0.0, 1.0),
                population=_range(np.log1p(self.population)),
            )
        return self._cache["scaling"]


def compute_components(ctx: AnalysisContext, extra_lat=None, extra_lon=None, scaling: Scaling | None = None) -> dict[str, np.ndarray]:
    scaling = scaling or ctx.baseline_scaling()
    sigma = ctx.sigma_total(extra_lat, extra_lon)
    return {
        "coverage_deficit": 1.0 - ctx.coverage(extra_lat, extra_lon),
        "uncertainty": scale(sigma, scaling.uncertainty),
        "pollution": scale(ctx.pm25, scaling.pollution) if ctx.pm25_available else np.full(len(ctx.lat), np.nan),
        "population": scale(np.log1p(ctx.population), scaling.population),
        "sigma_total": sigma,
    }


def gap_index(components: dict[str, np.ndarray], weights: GapWeights) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (MGI, observation deficit O, exposure need N)."""
    w = weights.validated()
    d, u = components["coverage_deficit"], components["uncertainty"]
    p, pop = components["pollution"], components["population"]
    w_p = 0.0 if np.all(np.isnan(p)) else w.pollution
    p = np.nan_to_num(p, nan=0.0)
    wo = w.coverage + w.uncertainty
    wn = w_p + w.population
    obs = (w.coverage * d + w.uncertainty * u) / wo if wo > 0 else np.ones_like(d)
    need = (w_p * p + w.population * pop) / wn if wn > 0 else np.ones_like(d)
    alpha = w.balance if (wo > 0 and wn > 0) else (1.0 if wn == 0 else 0.0)
    mgi = np.power(np.clip(obs, 0, 1), alpha) * np.power(np.clip(need, 0, 1), 1.0 - alpha)
    return mgi, obs, need


def classify(mgi: np.ndarray) -> np.ndarray:
    labels = np.full(mgi.shape, "low", dtype=object)
    for name, thr in reversed(GAP_CLASSES):
        labels[mgi >= thr] = name
    return labels


def class_summary(ctx: AnalysisContext, mgi: np.ndarray) -> dict:
    labels = classify(mgi)
    people = ctx.people
    total_people = float(people.sum())
    out = {}
    for name, thr in GAP_CLASSES:
        sel = labels == name
        out[name] = {
            "threshold": thr,
            "cells": int(sel.sum()),
            "area_km2": round(float(sel.sum() * ctx.cell_area_km2), 2),
            "population": int(round(float(people[sel].sum()))),
            "population_pct": round(100.0 * float(people[sel].sum()) / total_people, 2) if total_people else 0.0,
        }
    return out


def network_metrics(ctx: AnalysisContext, weights: GapWeights, extra_lat=None, extra_lon=None, scaling: Scaling | None = None) -> dict:
    """Coverage, uncertainty and gap metrics for the network (+ optional extra sites)."""
    scaling = scaling or ctx.baseline_scaling()
    comps = compute_components(ctx, extra_lat, extra_lon, scaling)
    mgi, _obs, need = gap_index(comps, weights)
    people = ctx.people
    total_people = float(people.sum()) or 1.0
    near = ctx.nearest_station_km(extra_lat, extra_lon)
    within = near <= ctx.radius_km
    cov = 1.0 - comps["coverage_deficit"]
    w_need = need if need.sum() > 0 else np.ones_like(need)
    sigma = comps["sigma_total"]
    classes = class_summary(ctx, mgi)
    return {
        "stations": int(len(ctx.station_lat) + (0 if extra_lat is None else len(extra_lat))),
        "population_within_radius_pct": round(100.0 * float(people[within].sum()) / total_people, 2),
        "area_within_radius_pct": round(100.0 * float(within.mean()), 2),
        "need_weighted_coverage_pct": round(100.0 * float(np.sum(w_need * cov) / np.sum(w_need)), 2),
        "mean_sigma_log": round(float(np.sum(w_need * sigma) / np.sum(w_need)), 5),
        "typical_relative_halfwidth_pct": round(100.0 * float(np.expm1(1.6449 * np.sum(w_need * sigma) / np.sum(w_need))), 2),
        "mean_gap_index": round(float(mgi.mean()), 4),
        "population_weighted_gap_index": round(float(np.sum(people * mgi) / total_people), 4),
        "critical_cells": classes["critical"]["cells"],
        "critical_area_km2": classes["critical"]["area_km2"],
        "population_in_critical_gaps": classes["critical"]["population"],
        "population_in_high_or_critical_gaps": classes["critical"]["population"] + classes["high"]["population"],
        "median_distance_to_station_km": round(float(np.median(near)), 3),
        "max_distance_to_station_km": round(float(np.max(near)), 3),
    }


def blind_spots(ctx: AnalysisContext, mgi: np.ndarray, threshold: float | None = None, max_clusters: int = 12) -> list[dict]:
    """Connected regions of critical MGI (8-connectivity), ranked by population-weighted severity."""
    threshold = GAP_CLASSES[0][1] if threshold is None else threshold
    grid = ctx.grid
    full = np.zeros(grid.n_cells, dtype=bool)
    full[grid.mask] = mgi >= threshold
    labels, n = label_regions(full.reshape(grid.nrows, grid.ncols), connectivity=8)
    pos = grid.inside_position()
    flat_labels = labels.ravel()
    people = ctx.people
    near = ctx.nearest_station_km()
    clusters = []
    for lab in range(1, n + 1):
        cells = pos[flat_labels == lab]
        cells = cells[cells >= 0]
        if len(cells) < CLUSTER_MIN_CELLS:
            continue
        w = mgi[cells] * np.maximum(people[cells], 1.0)
        c_lat = float(np.sum(w * ctx.lat[cells]) / w.sum())
        c_lon = float(np.sum(w * ctx.lon[cells]) / w.sum())
        peak = cells[np.argmax(mgi[cells])]
        clusters.append({
            "cells": [int(grid.inside_index[c]) for c in cells],
            "n_cells": int(len(cells)),
            "area_km2": round(float(len(cells) * ctx.cell_area_km2), 2),
            "centroid": {"lat": round(c_lat, 5), "lon": round(c_lon, 5)},
            "peak": {"lat": round(float(ctx.lat[peak]), 5), "lon": round(float(ctx.lon[peak]), 5)},
            "peak_gap_index": round(float(mgi[cells].max()), 4),
            "mean_gap_index": round(float(mgi[cells].mean()), 4),
            "mean_pm25": round(float(np.mean(ctx.pm25[cells])), 1) if ctx.pm25_available else None,
            "population": int(round(float(people[cells].sum()))),
            "distance_to_nearest_station_km": round(float(np.min(near[cells])), 2),
            "location": describe_location(ctx.city.id, c_lat, c_lon),
            "_priority": float(np.sum(w)),
        })
    clusters.sort(key=lambda c: c["_priority"], reverse=True)
    for i, c in enumerate(clusters[:max_clusters]):
        c["id"] = chr(ord("A") + i) if i < 26 else f"Z{i}"
        c.pop("_priority")
    return clusters[:max_clusters]


def analyze_gaps(ctx: AnalysisContext, weights: GapWeights) -> dict:
    comps = compute_components(ctx)
    mgi, obs, need = gap_index(comps, weights)
    return {
        "weights": weights.to_dict(),
        "classes": [{"name": n, "threshold": t} for n, t in GAP_CLASSES],
        "gap_index": mgi,
        "observation_deficit": obs,
        "exposure_need": need,
        "components": {k: v for k, v in comps.items() if k != "sigma_total"},
        "labels": classify(mgi),
        "summary": {"by_class": class_summary(ctx, mgi), "network": network_metrics(ctx, weights)},
        "clusters": blind_spots(ctx, mgi),
    }
