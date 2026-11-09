"""Optimal placement of new monitoring stations.

Strategies
----------
``coverage`` (default) - maximise need-weighted probabilistic coverage

    F(S) = sum_c w_c * [1 - prod_{s in E u S} (1 - exp(-d(c, s) / R))]

with priority weights w_c = N_c * (0.5 + 0.5 * U_c) (exposure need, boosted by
uncertainty). F is monotone submodular, so the greedy algorithm is guaranteed to
reach at least (1 - 1/e) ~ 63 % of the optimal value for an unconstrained budget
of k sites (Nemhauser, Wolsey & Fisher, 1978). AirScope adds practical spacing
constraints, under which greedy remains a strong heuristic.

``variance`` - greedily maximise the need-weighted reduction of kriging
prediction variance, the classic geostatistical network-design criterion
(cf. Krause, Singh & Guestrin, 2008, JMLR 9). Rank-one posterior updates keep
each step O(n²).

``population`` and ``random`` - transparent baselines used for comparison and
in the OSSE benchmark.

Constraints: candidates are grid cells inside the city domain whose population
density is at least ``min_population_density`` (a proxy for power, access and
security), at least ``min_station_distance_km`` from existing stations, and at
least ``min_spacing_km`` from each other.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from functools import lru_cache

import numpy as np

from geospatial.distance import nearest_distance_km, pairwise_haversine_km
from geospatial.gazetteer import describe_location
from .aqi import pm25_category
from .gaps import AnalysisContext, GapWeights, compute_components, gap_index, network_metrics

STRATEGIES = {
    "coverage": "Need-weighted coverage (greedy, submodular)",
    "variance": "Kriging-variance reduction (greedy)",
    "population": "Population heuristic (baseline)",
    "random": "Random eligible sites (baseline)",
}
MAX_K = 25


@dataclass(frozen=True)
class PlacementConstraints:
    k: int = 5
    strategy: str = "coverage"
    min_spacing_km: float = 2.0
    min_station_distance_km: float = 1.5
    min_population_density: float = 200.0
    seed: int = 0
    curve_max_k: int = 12

    def validated(self) -> "PlacementConstraints":
        if self.strategy not in STRATEGIES:
            raise ValueError(f"Unknown strategy '{self.strategy}'. Choose one of: {', '.join(STRATEGIES)}")
        if not 1 <= int(self.k) <= MAX_K:
            raise ValueError(f"k must be between 1 and {MAX_K}")
        for name in ("min_spacing_km", "min_station_distance_km"):
            v = getattr(self, name)
            if not (math.isfinite(v) and 0.0 <= v <= 20.0):
                raise ValueError(f"{name} must be between 0 and 20 km")
        if not (math.isfinite(self.min_population_density) and self.min_population_density >= 0):
            raise ValueError("min_population_density must be >= 0")
        return self

    def to_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=4)
def _cell_distances(city_id: str, n: int, lat_bytes: bytes, lon_bytes: bytes) -> np.ndarray:
    lat = np.frombuffer(lat_bytes, dtype=float)
    lon = np.frombuffer(lon_bytes, dtype=float)
    return pairwise_haversine_km(lat, lon, lat, lon).astype(np.float32)


def cell_distance_matrix(ctx: AnalysisContext) -> np.ndarray:
    lat = np.ascontiguousarray(ctx.lat, dtype=float)
    lon = np.ascontiguousarray(ctx.lon, dtype=float)
    return _cell_distances(ctx.city.id, len(lat), lat.tobytes(), lon.tobytes())


def eligible_candidates(ctx: AnalysisContext, c: PlacementConstraints) -> np.ndarray:
    ok = ctx.population >= c.min_population_density
    if len(ctx.station_lat):
        ok &= ctx.nearest_station_km() >= c.min_station_distance_km
    return ok


def priority_weights(ctx: AnalysisContext, weights: GapWeights) -> np.ndarray:
    comps = compute_components(ctx)
    _mgi, _obs, need = gap_index(comps, weights)
    w = need * (0.5 + 0.5 * comps["uncertainty"])
    return w if w.sum() > 0 else np.ones_like(w)


def _apply_spacing(available: np.ndarray, dist_row: np.ndarray, spacing: float) -> None:
    if spacing > 0:
        available &= dist_row >= spacing


def greedy_coverage(ctx: AnalysisContext, available: np.ndarray, w: np.ndarray, k: int, spacing: float) -> list[tuple[int, float]]:
    dist = cell_distance_matrix(ctx)
    decay = np.exp(-dist / ctx.radius_km)  # (N, N) symmetric
    miss = 1.0 - ctx.coverage()
    total = float(w.sum())
    available = available.copy()
    picks = []
    for _ in range(k):
        if not available.any():
            break
        gains = decay @ (w * miss)
        gains[~available] = -np.inf
        j = int(np.argmax(gains))
        if not np.isfinite(gains[j]):
            break
        picks.append((j, float(gains[j] / total)))
        miss = miss * (1.0 - decay[j])
        available[j] = False
        _apply_spacing(available, dist[j], spacing)
    return picks


def greedy_variance(ctx: AnalysisContext, available: np.ndarray, w: np.ndarray, k: int, spacing: float) -> list[tuple[int, float]]:
    eta = float(np.clip(ctx.params.nugget_ratio, 0.0, 0.99))
    L = ctx.params.range_km
    dist = cell_distance_matrix(ctx).astype(float)
    P = (1 - eta) * np.exp(-dist / L)  # prior signal covariance between cells
    if len(ctx.station_lat):
        d_cs = pairwise_haversine_km(ctx.lat, ctx.lon, ctx.station_lat, ctx.station_lon)
        d_ss = pairwise_haversine_km(ctx.station_lat, ctx.station_lon, ctx.station_lat, ctx.station_lon)
        c_cs = (1 - eta) * np.exp(-d_cs / L)
        k_ss = (1 - eta) * np.exp(-d_ss / L) + eta * np.eye(len(ctx.station_lat))
        P = P - c_cs @ np.linalg.solve(k_ss, c_cs.T)
    total = float(np.sum(w * (np.diag(P) + eta)))
    available = available.copy()
    picks = []
    for _ in range(k):
        if not available.any():
            break
        gains = (w @ (P**2)) / (np.diag(P) + eta)
        gains[~available] = -np.inf
        j = int(np.argmax(gains))
        if not np.isfinite(gains[j]):
            break
        picks.append((j, float(gains[j] / total)))
        pj = P[:, j].copy()
        P -= np.outer(pj, pj) / (pj[j] + eta)
        available[j] = False
        _apply_spacing(available, dist[j], spacing)
    return picks


def population_heuristic(ctx: AnalysisContext, available: np.ndarray, k: int, spacing: float) -> list[tuple[int, float]]:
    dist = cell_distance_matrix(ctx)
    available = available.copy()
    order = np.argsort(-ctx.population)
    picks = []
    for j in order:
        if len(picks) >= k:
            break
        if available[j]:
            picks.append((int(j), 0.0))
            available[j] = False
            _apply_spacing(available, dist[j], spacing)
    return picks


def random_sites(ctx: AnalysisContext, available: np.ndarray, k: int, spacing: float, seed: int) -> list[tuple[int, float]]:
    dist = cell_distance_matrix(ctx)
    rng = np.random.default_rng(seed)
    available = available.copy()
    picks = []
    for j in rng.permutation(len(available)):
        if len(picks) >= k:
            break
        if available[j]:
            picks.append((int(j), 0.0))
            available[j] = False
            _apply_spacing(available, dist[j], spacing)
    return picks


def select_sites(ctx: AnalysisContext, weights: GapWeights, constraints: PlacementConstraints, k: int | None = None) -> list[tuple[int, float]]:
    c = constraints.validated()
    k = int(k or c.k)
    available = eligible_candidates(ctx, c)
    if c.strategy == "coverage":
        return greedy_coverage(ctx, available, priority_weights(ctx, weights), k, c.min_spacing_km)
    if c.strategy == "variance":
        _m, _o, need = gap_index(compute_components(ctx), weights)
        return greedy_variance(ctx, available, need if need.sum() > 0 else np.ones_like(need), k, c.min_spacing_km)
    if c.strategy == "population":
        return population_heuristic(ctx, available, k, c.min_spacing_km)
    return random_sites(ctx, available, k, c.min_spacing_km, c.seed)


# --------------------------------------------------------------------------- reporting


def _percentile_rank(values: np.ndarray, v: float) -> float:
    return float((values < v).mean() * 100.0)


def _reasons(ctx: AnalysisContext, j: int, comps: dict, near_km: float, newly_covered: int) -> list[str]:
    reasons = []
    pop_pct = _percentile_rank(ctx.population, ctx.population[j])
    if pop_pct >= 60:
        reasons.append(f"Dense area: about {ctx.population[j]:,.0f} people/km² (more than {pop_pct:.0f}% of the city)")
    if near_km >= 1.5 * ctx.radius_km:
        reasons.append(f"{near_km:.1f} km from the nearest monitor (representativeness radius {ctx.radius_km:g} km)")
    if ctx.pm25_available:
        pm_pct = _percentile_rank(ctx.pm25, ctx.pm25[j])
        if pm_pct >= 60:
            reasons.append(f"High estimated PM2.5: {ctx.pm25[j]:.0f} µg/m³ ({pm25_category(float(ctx.pm25[j]))}), above {pm_pct:.0f}% of the city")
    unc_pct = _percentile_rank(comps["uncertainty"], comps["uncertainty"][j])
    if unc_pct >= 75:
        reasons.append(f"Model uncertainty higher than {unc_pct:.0f}% of the city")
    if newly_covered > 0:
        reasons.append(f"Brings about {newly_covered:,} residents within {ctx.radius_km:g} km of a monitor")
    if not reasons:
        reasons.append("Best remaining trade-off between coverage gain and exposure need")
    return reasons


def evaluate_curve(ctx: AnalysisContext, weights: GapWeights, lat: np.ndarray, lon: np.ndarray) -> list[dict]:
    scaling = ctx.baseline_scaling()
    base = network_metrics(ctx, weights, scaling=scaling)
    curve = []
    for m in range(0, len(lat) + 1):
        met = base if m == 0 else network_metrics(ctx, weights, lat[:m], lon[:m], scaling)
        curve.append({
            "k": m,
            "need_weighted_coverage_pct": met["need_weighted_coverage_pct"],
            "population_within_radius_pct": met["population_within_radius_pct"],
            "uncertainty_reduction_pct": round(100.0 * (1 - met["mean_sigma_log"] / base["mean_sigma_log"]), 2) if base["mean_sigma_log"] else 0.0,
            "population_in_critical_gaps": met["population_in_critical_gaps"],
            "mean_gap_index": met["mean_gap_index"],
        })
    return curve


def describe_sites(ctx: AnalysisContext, weights: GapWeights, cells: list[int], gains: list[float] | None = None) -> list[dict]:
    comps = compute_components(ctx)
    mgi, _o, _n = gap_index(comps, weights)
    lat = ctx.lat[cells]
    lon = ctx.lon[cells]
    within_before = ctx.nearest_station_km() <= ctx.radius_km
    sites = []
    for rank, j in enumerate(cells, start=1):
        near_existing, _ = nearest_distance_km([ctx.lat[j]], [ctx.lon[j]], ctx.station_lat, ctx.station_lon)
        prev_lat, prev_lon = lat[: rank - 1], lon[: rank - 1]
        within_prev = within_before | (ctx.nearest_station_km(prev_lat, prev_lon) <= ctx.radius_km if rank > 1 else within_before)
        within_now = within_prev | (pairwise_haversine_km(ctx.lat, ctx.lon, [ctx.lat[j]], [ctx.lon[j]])[:, 0] <= ctx.radius_km)
        newly = int(round(float(ctx.people[within_now & ~within_prev].sum())))
        sites.append({
            "rank": rank,
            "lat": round(float(ctx.lat[j]), 5),
            "lon": round(float(ctx.lon[j]), 5),
            "cell_index": int(ctx.grid.inside_index[j]),
            "location": describe_location(ctx.city.id, float(ctx.lat[j]), float(ctx.lon[j])),
            "pm25": round(float(ctx.pm25[j]), 1) if ctx.pm25_available else None,
            "aqi_category": pm25_category(float(ctx.pm25[j])) if ctx.pm25_available else None,
            "uncertainty_score": round(float(comps["uncertainty"][j]), 3),
            "gap_index": round(float(mgi[j]), 3),
            "population_density": round(float(ctx.population[j]), 0),
            "nearest_station_km": round(float(near_existing[0]), 2) if np.isfinite(near_existing[0]) else None,
            "objective_gain": None if gains is None else round(float(gains[rank - 1]), 5),
            "newly_covered_population": newly,
            "reasons": _reasons(ctx, j, comps, float(near_existing[0]) if np.isfinite(near_existing[0]) else float("inf"), newly),
        })
    return sites


def recommend(ctx: AnalysisContext, weights: GapWeights, constraints: PlacementConstraints) -> dict:
    c = constraints.validated()
    k_curve = max(c.k, c.curve_max_k)
    picks = select_sites(ctx, weights, c, k=k_curve)
    cells = [j for j, _ in picks]
    gains = [g for _, g in picks]
    lat, lon = ctx.lat[cells], ctx.lon[cells]
    chosen = cells[: c.k]
    scaling = ctx.baseline_scaling()
    before = network_metrics(ctx, weights, scaling=scaling)
    after = network_metrics(ctx, weights, lat[: c.k], lon[: c.k], scaling) if chosen else before
    eligible = int(eligible_candidates(ctx, c).sum())
    return {
        "strategy": c.strategy,
        "strategy_label": STRATEGIES[c.strategy],
        "constraints": c.to_dict(),
        "weights": weights.to_dict(),
        "eligible_cells": eligible,
        "sites": describe_sites(ctx, weights, chosen, gains[: c.k]),
        "impact": {"before": before, "after": after, "delta": _delta(before, after)},
        "curve": evaluate_curve(ctx, weights, lat, lon),
        "message": None if len(chosen) == c.k else (
            f"Only {len(chosen)} of {c.k} sites satisfy the constraints; relax spacing or the population threshold to get more."
        ),
    }


def simulate(ctx: AnalysisContext, weights: GapWeights, sites: list[tuple[float, float]]) -> dict:
    """Impact of user-chosen hypothetical sites (must lie inside the analysis domain)."""
    lat = np.array([s[0] for s in sites], dtype=float)
    lon = np.array([s[1] for s in sites], dtype=float)
    scaling = ctx.baseline_scaling()
    before = network_metrics(ctx, weights, scaling=scaling)
    after = network_metrics(ctx, weights, lat, lon, scaling) if len(lat) else before
    cells = []
    for la, lo in zip(lat, lon):
        flat = ctx.grid.locate(float(la), float(lo))
        cells.append(int(ctx.grid.inside_position()[flat]) if flat >= 0 else -1)
    if any(c < 0 for c in cells):
        raise ValueError("All simulated sites must lie inside the city's analysis domain")
    described = describe_sites(ctx, weights, cells) if cells else []
    for s, la, lo in zip(described, lat, lon):  # keep the exact user coordinates
        s["lat"], s["lon"] = round(float(la), 5), round(float(lo), 5)
    return {
        "sites": described,
        "impact": {"before": before, "after": after, "delta": _delta(before, after)},
        "curve": evaluate_curve(ctx, weights, lat, lon),
    }


def _delta(before: dict, after: dict) -> dict:
    out = {}
    for key, b in before.items():
        a = after.get(key)
        if isinstance(b, (int, float)) and isinstance(a, (int, float)):
            out[key] = round(a - b, 4)
    if before.get("mean_sigma_log"):
        out["uncertainty_reduction_pct"] = round(100.0 * (1 - after["mean_sigma_log"] / before["mean_sigma_log"]), 2)
    return out
