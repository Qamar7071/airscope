"""Predictive uncertainty: model spread + spatial (kriging) variance + calibration.

AirScope's predictive standard deviation, in log1p(PM2.5) units, is

    sigma_total(x, t) = c * sqrt( sigma_q(x,t)^2 + sigma_mm(x,t)^2 + s_sp^2 * rho(x) )

* sigma_q   conditional spread from quantile gradient-boosting models
            (5th/95th percentiles): how variable PM2.5 is under these conditions;
* sigma_mm  disagreement between the ensemble members (multi-model spread);
* rho(x)    normalised simple-kriging variance in [0, 1] computed from the station
            geometry alone (exponential covariance). It is ~0 next to a station and
            -> 1 far from all stations: the "monitoring blind-spot" term that tree
            models cannot express on their own;
* s_sp^2    the extra error variance at unmonitored locations, estimated from
            leave-one-station-out (LOSO) residuals;
* c         a conformal scale factor chosen so that 90 % intervals cover 90 % of
            LOSO residuals.

The covariance range and nugget come from an exponential variogram fitted to
LOSO residuals between station pairs (falling back to the city default when
there are too few pairs). Calibration quality is reported honestly with a
*nested* LOSO procedure: the parameters used to judge station h are estimated
without station h.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd
from scipy import optimize, stats

from geospatial.distance import pairwise_haversine_km

logger = logging.getLogger(__name__)

Z90 = float(stats.norm.ppf(0.95))
COVERAGE_LEVELS = (0.5, 0.8, 0.9, 0.95)
MIN_COMMON_HOURS = 24


# --------------------------------------------------------------------------- variogram


@dataclass
class VariogramFit:
    nugget: float
    psill: float
    range_km: float
    method: str  # "weighted_least_squares" | "fallback"
    pairs: list[dict] = field(default_factory=list)

    @property
    def sill(self) -> float:
        return self.nugget + self.psill

    @property
    def nugget_ratio(self) -> float:
        return float(self.nugget / self.sill) if self.sill > 0 else 0.5

    def semivariance(self, d) -> np.ndarray:
        d = np.asarray(d, dtype=float)
        return self.nugget + self.psill * (1.0 - np.exp(-d / self.range_km))

    def to_dict(self) -> dict:
        out = asdict(self)
        out["nugget_ratio"] = self.nugget_ratio
        curve_d = np.linspace(0.0, max([p["distance_km"] for p in self.pairs] + [self.range_km * 3, 5.0]), 40)
        out["curve"] = [{"distance_km": round(float(d), 3), "semivariance": round(float(g), 5)} for d, g in zip(curve_d, self.semivariance(curve_d))]
        return out


def empirical_variogram(residuals: pd.DataFrame, lat, lon) -> list[dict]:
    """Pairwise semivariances of residual time series: 0.5 * mean_t (r_i - r_j)^2."""
    cols = list(residuals.columns)
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    d = pairwise_haversine_km(lat, lon, lat, lon)
    values = residuals.to_numpy(dtype=float)
    pairs = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            both = ~np.isnan(values[:, i]) & ~np.isnan(values[:, j])
            n = int(both.sum())
            if n < MIN_COMMON_HOURS:
                continue
            gamma = 0.5 * float(np.mean((values[both, i] - values[both, j]) ** 2))
            pairs.append({"a": cols[i], "b": cols[j], "distance_km": round(float(d[i, j]), 3), "semivariance": round(gamma, 6), "n": n})
    return pairs


def fit_variogram(pairs: list[dict], total_variance: float, default_range_km: float) -> VariogramFit:
    """Exponential variogram by weighted least squares, with a documented fallback."""
    total_variance = float(max(total_variance, 1e-4))
    fallback = VariogramFit(0.3 * total_variance, 0.7 * total_variance, float(default_range_km), "fallback", pairs)
    if len(pairs) < 3:
        return fallback
    d = np.array([p["distance_km"] for p in pairs], dtype=float)
    g = np.array([p["semivariance"] for p in pairs], dtype=float)
    w = np.sqrt(np.array([p["n"] for p in pairs], dtype=float))

    def resid(theta):
        nug, ps, rng = theta
        return w * (nug + ps * (1.0 - np.exp(-d / rng)) - g)

    x0 = [max(g.min() * 0.5, 1e-5), max(g.max() - g.min() * 0.5, 1e-5), float(default_range_km)]
    hi = [max(g.max() * 2, 1e-3), max(g.max() * 3, 1e-3), 25.0]
    x0 = [min(max(v, 1e-6), h * 0.99) for v, h in zip(x0, hi)]
    try:
        res = optimize.least_squares(resid, x0=x0, bounds=([0.0, 0.0, 0.5], hi), loss="soft_l1")
    except (ValueError, np.linalg.LinAlgError) as exc:
        logger.info("Variogram fit failed (%s); using fallback", exc)
        return fallback
    nug, ps, rng = (float(v) for v in res.x)
    if not res.success or ps <= 1e-8 or not np.isfinite([nug, ps, rng]).all():
        return fallback
    return VariogramFit(nug, ps, rng, "weighted_least_squares", pairs)


# --------------------------------------------------------------------------- kriging variance


def normalized_kriging_variance(t_lat, t_lon, s_lat, s_lon, range_km: float, nugget_ratio: float) -> np.ndarray:
    """Simple-kriging prediction variance with unit sill (in [0, 1]).

    Observations are modelled as signal (variance 1 - eta, exponential correlation
    with range ``range_km``) plus nugget noise (variance eta). The value returned
    for a target is the variance of predicting an observation there:
    ``1 - k^T K^{-1} k``.
    """
    t_lat = np.atleast_1d(np.asarray(t_lat, dtype=float))
    t_lon = np.atleast_1d(np.asarray(t_lon, dtype=float))
    s_lat = np.atleast_1d(np.asarray(s_lat, dtype=float))
    s_lon = np.atleast_1d(np.asarray(s_lon, dtype=float))
    if s_lat.size == 0:
        return np.ones(t_lat.shape)
    eta = float(np.clip(nugget_ratio, 0.0, 0.99))
    k_ss = (1 - eta) * np.exp(-pairwise_haversine_km(s_lat, s_lon, s_lat, s_lon) / range_km) + eta * np.eye(len(s_lat))
    k_ts = (1 - eta) * np.exp(-pairwise_haversine_km(t_lat, t_lon, s_lat, s_lon) / range_km)
    sol = np.linalg.solve(k_ss + 1e-9 * np.eye(len(s_lat)), k_ts.T)  # (S, N)
    rho = 1.0 - np.einsum("ns,sn->n", k_ts, sol)
    return np.clip(rho, 0.0, 1.0)


# --------------------------------------------------------------------------- calibration


@dataclass
class UncertaintyParams:
    scale: float = 1.0  # conformal factor c
    spatial_var: float = 0.05  # s_sp^2 (log units)
    range_km: float = 3.0
    nugget_ratio: float = 0.3
    calibrated: bool = False
    method: str = "default"

    def sigma_total(self, sigma_model2, rho) -> np.ndarray:
        return self.scale * np.sqrt(np.maximum(np.asarray(sigma_model2, dtype=float), 0.0) + self.spatial_var * np.asarray(rho, dtype=float))

    def interval(self, pred, sigma_total, level: float = 0.9) -> tuple[np.ndarray, np.ndarray]:
        z = float(stats.norm.ppf(0.5 + level / 2.0))
        centre = np.log1p(np.maximum(np.asarray(pred, dtype=float), 0.0))
        lo = np.expm1(centre - z * sigma_total)
        hi = np.expm1(centre + z * sigma_total)
        return np.maximum(lo, 0.0), hi

    def to_dict(self) -> dict:
        return asdict(self)


def _estimate(r: np.ndarray, sm2: np.ndarray, rho: np.ndarray, target: float = 0.9) -> tuple[float, float]:
    mean_rho = max(float(np.mean(rho)), 1e-6)
    s_sp2 = max(0.0, (float(np.mean(r**2)) - float(np.mean(sm2))) / mean_rho)
    z = np.abs(r) / np.sqrt(np.maximum(sm2 + s_sp2 * rho, 1e-12))
    zq = float(stats.norm.ppf(0.5 + target / 2.0))
    c = float(np.quantile(z, target)) / zq if len(z) else 1.0
    return s_sp2, float(np.clip(c, 0.3, 10.0))


def calibrate(oof: pd.DataFrame, rho_by_station: dict[str, float], vario: VariogramFit) -> tuple[UncertaintyParams, dict]:
    """Calibrate on LOSO out-of-fold rows and report nested coverage.

    ``oof`` needs columns: station_id, y, pred, sigma_model2.
    """
    df = oof.dropna(subset=["y", "pred", "sigma_model2"]).copy()
    df["r"] = np.log1p(df["y"]) - np.log1p(df["pred"].clip(lower=0))
    df["rho"] = df["station_id"].map(rho_by_station).astype(float)
    s_sp2, c = _estimate(df["r"].to_numpy(), df["sigma_model2"].to_numpy(), df["rho"].to_numpy())
    params = UncertaintyParams(scale=c, spatial_var=s_sp2, range_km=vario.range_km, nugget_ratio=vario.nugget_ratio,
                               calibrated=True, method="nested-LOSO conformal scaling")
    # nested evaluation
    levels = list(COVERAGE_LEVELS)
    hits = {lv: [] for lv in levels}
    raw_hits = []
    per_station = {}
    for sid, grp in df.groupby("station_id"):
        others = df[df["station_id"] != sid]
        if others.empty:
            continue
        s2, cc = _estimate(others["r"].to_numpy(), others["sigma_model2"].to_numpy(), others["rho"].to_numpy())
        sig = cc * np.sqrt(grp["sigma_model2"].to_numpy() + s2 * grp["rho"].to_numpy())
        z = np.abs(grp["r"].to_numpy()) / np.maximum(sig, 1e-12)
        st_cov = {}
        for lv in levels:
            inside = z <= stats.norm.ppf(0.5 + lv / 2.0)
            hits[lv].append(inside)
            st_cov[str(lv)] = round(float(inside.mean()), 4)
        raw_sig = np.sqrt(grp["sigma_model2"].to_numpy())
        raw_hits.append(np.abs(grp["r"].to_numpy()) <= Z90 * raw_sig)
        per_station[sid] = {"coverage": st_cov, "rho": round(float(grp["rho"].iloc[0]), 4), "n": int(len(grp))}
    empirical = [round(float(np.concatenate(hits[lv]).mean()), 4) if hits[lv] else None for lv in levels]
    report = {
        "method": params.method,
        "levels": levels,
        "empirical_coverage": empirical,
        "model_only_coverage_90": round(float(np.concatenate(raw_hits).mean()), 4) if raw_hits else None,
        "scale": round(c, 4),
        "spatial_variance": round(s_sp2, 6),
        "per_station": per_station,
        "note": "Empirical coverage is computed with nested leave-one-station-out: the calibration used for each "
                "held-out station never saw that station.",
    }
    return params, report


def default_params(range_km: float, residual_var: float | None = None) -> UncertaintyParams:
    """Uncalibrated fallback used when there are too few stations for LOSO."""
    var = float(residual_var) if residual_var is not None and np.isfinite(residual_var) else 0.25
    return UncertaintyParams(scale=1.0, spatial_var=max(var, 0.04), range_km=range_km, nugget_ratio=0.3,
                             calibrated=False, method="uncalibrated default (fewer than 3 usable stations)")
