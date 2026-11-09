"""Deterministic synthetic "nature run" for AirScope's offline demo and OSSE.

Why synthetic data?
-------------------
AirScope must run fully offline, without API keys, and produce identical results
on every run. It must also never present fabricated numbers as real
observations. We therefore follow the *Observing System Simulation Experiment*
(OSSE) methodology used in atmospheric science to design observing networks:

1. A documented, physically-motivated synthetic PM2.5 field (the "nature run")
   is defined everywhere in the city and for every hour of the demo period.
2. Simulated monitoring stations sample the nature run with realistic
   measurement noise, gaps and faults. AirScope's pipeline only ever sees these
   station samples, exactly as it would see real OpenAQ data.
3. Because the full truth is known, we can measure how well the pipeline
   reconstructs the city-wide field, whether its uncertainty is meaningful, and
   how much candidate sensor placements would actually reduce error.

Everything produced here is labelled synthetic throughout the API and UI.
Metrics computed on it describe pipeline behaviour on synthetic data, not
real-world accuracy.

The truth model ("fraternal twin")
----------------------------------
PM(x, t) = R(t) D(t) H(t) S(t) [B_reg + B_city (a_pop P(x) E_res(h) + sum_k q_k E_k(h) K_k(x, t))]
           x elev(x) x exp(rf(x)) x marine(x, t)

* D(t)  ventilation dilution (boundary-layer height x wind speed)
* H(t)  hygroscopic growth at high humidity
* R(t)  regional transport episodes (unobserved, common to the whole city)
* S(t)  slow seasonal trend
* P(x)  population term (analytic high-resolution density, not the coarse CSV)
* K_k   wind-advected Gaussian plumes from point, area and road (line) sources
* rf(x) smooth random field (random Fourier features) - local structure that no
        covariate explains, i.e. what only a nearby sensor can reveal
* elev  cleaner air on the Margalla Hills slopes; marine: sea-breeze ventilation

The model never sees the analytic population, the sources or rf(x); it uses the
coarse bundled CSV surfaces instead. This avoids the over-optimism of an
"identical twin" OSSE.

Usage::

    python -m data.demo_generator            # (re)generate everything
    python -m data.demo_generator --city islamabad
    python -m data.demo_generator --check    # verify files match a fresh run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

if __package__ in (None, ""):  # allow `python data/demo_generator.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import CityConfig, get_settings, load_cities  # noqa: E402
from geospatial.distance import pairwise_haversine_km, to_local_km  # noqa: E402
from geospatial.spatial_utils import polyline_points  # noqa: E402

logger = logging.getLogger(__name__)

GENERATOR_VERSION = "airscope-nature-run-1.0"
SPEC_FILE = "synthetic_city_profiles.json"
STATIONS_FILE = "demo_stations.json"
WEATHER_COLUMNS = [
    "temperature_c",
    "relative_humidity_pct",
    "wind_speed_ms",
    "wind_direction_deg",
    "surface_pressure_hpa",
    "boundary_layer_height_m",
]
NOISE_BY_KIND = {"reference": (0.06, 1.0), "low-cost": (0.12, 2.0)}


# --------------------------------------------------------------------------- spec


@lru_cache(maxsize=2)
def load_spec(datasets_dir: str | None = None) -> dict:
    path = Path(datasets_dir or get_settings().datasets_dir) / SPEC_FILE
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=2)
def load_demo_stations(datasets_dir: str | None = None) -> dict:
    path = Path(datasets_dir or get_settings().datasets_dir) / STATIONS_FILE
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def demo_timestamps(spec: dict | None = None) -> pd.DatetimeIndex:
    spec = spec or load_spec()
    period = spec["demo_period"]
    return pd.date_range(pd.Timestamp(period["start"]), periods=int(period["hours"]), freq="h")


def local_hours(timestamps: pd.DatetimeIndex, timezone: str) -> np.ndarray:
    ts = pd.DatetimeIndex(timestamps)
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    local = ts.tz_convert(timezone)
    return (local.hour + local.minute / 60.0).to_numpy(dtype=float)


# --------------------------------------------------------------------------- helpers


def _gauss_hour(h: np.ndarray, centre: float, width: float) -> np.ndarray:
    d = np.abs(((h - centre) + 12.0) % 24.0 - 12.0)
    return np.exp(-0.5 * (d / width) ** 2)


EMISSION_PROFILES = {
    "traffic": lambda h: 0.55 + 0.55 * _gauss_hour(h, 8.5, 1.6) + 0.6 * _gauss_hour(h, 18.5, 2.0),
    "traffic_hub": lambda h: 0.55 + 0.55 * _gauss_hour(h, 8.5, 1.6) + 0.6 * _gauss_hour(h, 18.5, 2.0),
    "residential": lambda h: 0.6 + 0.5 * _gauss_hour(h, 19.5, 2.5) + 0.3 * _gauss_hour(h, 7.0, 1.5),
    "industrial": lambda h: 0.85 + 0.15 * _gauss_hour(h, 13.0, 4.0),
    "brick_kilns": lambda h: 1.0 + 0.1 * _gauss_hour(h, 2.0, 3.0),
    "port": lambda h: 0.9 + 0.1 * _gauss_hour(h, 12.0, 4.0),
    "airport": lambda h: 0.5 + 0.5 * _gauss_hour(h, 13.0, 5.0),
}


def _ar1(rng: np.random.Generator, n: int, phi: float, sigma: float) -> np.ndarray:
    """Stationary AR(1) series with marginal standard deviation ``sigma``."""
    eps = rng.normal(0.0, sigma * np.sqrt(1 - phi**2), size=n)
    out = np.empty(n)
    out[0] = rng.normal(0.0, sigma)
    for i in range(1, n):
        out[i] = phi * out[i - 1] + eps[i]
    return out


class RandomField:
    """Smooth stationary random field via random Fourier features (RBF kernel)."""

    def __init__(self, seed: int, length_km: float, sigma: float, lat0: float, lon0: float, n_features: int = 48):
        rng = np.random.default_rng(seed)
        self.omega = rng.normal(0.0, 1.0 / length_km, size=(n_features, 2))
        self.phase = rng.uniform(0.0, 2 * np.pi, size=n_features)
        self.scale = sigma * np.sqrt(2.0 / n_features)
        self.lat0, self.lon0 = lat0, lon0

    def __call__(self, lat, lon) -> np.ndarray:
        x, y = to_local_km(lat, lon, self.lat0, self.lon0)
        proj = np.outer(np.ravel(x), self.omega[:, 0]) + np.outer(np.ravel(y), self.omega[:, 1])
        return (self.scale * np.cos(proj + self.phase).sum(axis=1)).reshape(np.shape(x))


def _min_distance_to_polyline_km(lat, lon, line, spacing_km: float = 0.25) -> np.ndarray:
    pts = polyline_points(line, spacing_km)
    d = pairwise_haversine_km(np.ravel(lat), np.ravel(lon), pts[:, 0], pts[:, 1])
    return d.min(axis=1).reshape(np.shape(lat))


# --------------------------------------------------------------------------- surfaces


class TerrainModel:
    """Analytic terrain approximation (base plane + ridges + hills + undulation)."""

    def __init__(self, spec: dict, city: CityConfig, seed: int):
        self.spec = spec
        self.city = city
        self.undulation = RandomField(seed, length_km=2.0, sigma=3.0, lat0=city.center_lat, lon0=city.center_lon, n_features=24)

    def elevation(self, lat, lon) -> np.ndarray:
        lat = np.asarray(lat, dtype=float)
        lon = np.asarray(lon, dtype=float)
        x, y = to_local_km(lat, lon, self.city.center_lat, self.city.center_lon)
        g = self.spec.get("gradient_m_per_km", {})
        elev = self.spec["base_elevation_m"] + g.get("north", 0.0) * y + g.get("east", 0.0) * x
        for ridge in self.spec.get("ridges", []):
            d = _min_distance_to_polyline_km(lat, lon, ridge["line"])
            elev = elev + ridge["height_m"] * np.exp(-0.5 * (d / ridge["sigma_km"]) ** 2)
        for _name, hlat, hlon, height, sigma in self.spec.get("hills", []):
            d = pairwise_haversine_km(np.ravel(lat), np.ravel(lon), [hlat], [hlon])[:, 0].reshape(lat.shape)
            elev = elev + height * np.exp(-0.5 * (d / sigma) ** 2)
        elev = elev + self.undulation(lat, lon)
        return np.maximum(elev, 0.0)


class PopulationModel:
    """Analytic population density (persons/km²) from locality kernels."""

    def __init__(self, spec: dict, terrain: TerrainModel):
        self.spec = spec
        self.terrain = terrain
        k = np.array([row[1:] for row in spec["kernels"]], dtype=float)
        self.k_lat, self.k_lon, self.k_peak, self.k_sigma = k.T
        low = np.array([row[1:] for row in spec.get("low_density_areas", [])], dtype=float).reshape(-1, 4)
        self.l_lat, self.l_lon, self.l_depth, self.l_sigma = low.T

    def density(self, lat, lon) -> np.ndarray:
        lat = np.asarray(lat, dtype=float)
        shape = lat.shape
        flat_lat, flat_lon = np.ravel(lat), np.ravel(lon)
        d = pairwise_haversine_km(flat_lat, flat_lon, self.k_lat, self.k_lon)
        kern = self.k_peak * np.exp(-0.5 * (d / self.k_sigma) ** 2)
        dens = self.spec["background_per_km2"] + np.sqrt((kern**2).sum(axis=1))  # soft overlap (2-norm)
        if self.l_lat.size:
            dl = pairwise_haversine_km(flat_lat, flat_lon, self.l_lat, self.l_lon)
            dens = dens * np.prod(1.0 - self.l_depth * np.exp(-0.5 * (dl / self.l_sigma) ** 2), axis=1)
        limit = self.spec.get("habitable_below_elevation_m", 1e4)
        elev = self.terrain.elevation(flat_lat, flat_lon)
        habitable = 1.0 / (1.0 + np.exp((elev - limit) / 40.0))
        dens = np.maximum(dens * habitable, 15.0)
        return dens.reshape(shape)


# --------------------------------------------------------------------------- weather


def generate_weather(climate: dict, timestamps: pd.DatetimeIndex, timezone: str, seed: int) -> pd.DataFrame:
    """Synthetic hourly weather with diurnal cycles and multi-day stagnation episodes."""
    rng = np.random.default_rng(seed)
    n = len(timestamps)
    t_days = np.arange(n) / 24.0
    h = local_hours(timestamps, timezone)

    periods = np.array([2.7, 4.3, 6.9, 11.0])
    amps = np.array([0.45, 0.6, 0.5, 0.35])
    phases = rng.uniform(0, 2 * np.pi, size=len(periods))
    synoptic = (amps[:, None] * np.sin(2 * np.pi * t_days[None, :] / periods[:, None] + phases[:, None])).sum(axis=0)
    synoptic += _ar1(rng, n, 0.97, 0.35)
    stagnation = np.tanh(synoptic / 1.1)  # >0: stagnant (low wind, shallow mixing)

    temp = (
        climate["temperature_mean_c"]
        + climate["temperature_trend_c"] * (t_days / 30.0 - 0.5)
        + climate["temperature_amplitude_c"] * np.cos(2 * np.pi * (h - 14.5) / 24.0)
        - 1.2 * stagnation
        + _ar1(rng, n, 0.9, 0.6)
    )
    rh = (
        climate["rh_mean_pct"]
        - climate["rh_amplitude_pct"] * np.cos(2 * np.pi * (h - 14.5) / 24.0)
        + 8.0 * stagnation
        + _ar1(rng, n, 0.9, 3.0)
    )
    rh = np.clip(rh, 10.0, 99.0)
    ws = (
        climate["wind_mean_ms"]
        * (1.0 + 0.45 * np.cos(2 * np.pi * (h - 14.0) / 24.0))
        * (1.0 - 0.4 * stagnation)
        * np.exp(_ar1(rng, n, 0.85, 0.2))
    )
    ws = np.clip(ws, 0.2, 15.0)
    w_day = np.clip(0.5 + 0.8 * np.cos(2 * np.pi * (h - 15.0) / 24.0), 0.0, 1.0)
    a_night, a_day = np.radians(climate["wind_direction_night_deg"]), np.radians(climate["wind_direction_day_deg"])
    vx = (1 - w_day) * np.sin(a_night) + w_day * np.sin(a_day)
    vy = (1 - w_day) * np.cos(a_night) + w_day * np.cos(a_day)
    wd = (np.degrees(np.arctan2(vx, vy)) + _ar1(rng, n, 0.8, 20.0)) % 360.0
    pressure = (
        climate["pressure_mean_hpa"]
        + 4.0 * stagnation
        + 0.8 * np.cos(2 * np.pi * (h - 10.0) / 12.0)
        + _ar1(rng, n, 0.95, 0.8)
    )
    day_shape = np.where((h > 7.5) & (h < 17.5), np.clip(np.sin(np.pi * (h - 7.5) / 10.0), 0, 1) ** 1.3, 0.0)
    blh_night = climate["blh_night_m"] * (1.0 - 0.3 * stagnation)
    blh_day = climate["blh_day_m"] * (1.0 - 0.45 * stagnation)
    blh = (blh_night + np.maximum(blh_day - blh_night, 0.0) * day_shape) * np.exp(_ar1(rng, n, 0.8, 0.12))
    blh = np.clip(blh, 50.0, 4000.0)

    return pd.DataFrame(
        {
            "timestamp": pd.DatetimeIndex(timestamps),
            "temperature_c": np.round(temp, 1),
            "relative_humidity_pct": np.round(rh, 1),
            "wind_speed_ms": np.round(ws, 2),
            "wind_direction_deg": np.round(wd, 0),
            "surface_pressure_hpa": np.round(pressure, 1),
            "boundary_layer_height_m": np.round(blh, 0),
        }
    )


# --------------------------------------------------------------------------- nature run


@dataclass
class _SourcePoints:
    lat: np.ndarray
    lon: np.ndarray
    strength: np.ndarray
    radius: np.ndarray
    kind: list[str]


class NatureRun:
    """The synthetic truth PM2.5 field for one city over the demo period."""

    def __init__(self, city: CityConfig, profile: dict, weather: pd.DataFrame):
        self.city = city
        self.profile = profile
        seed = int(profile["seed"])
        self.terrain = TerrainModel(profile["terrain"], city, seed * 10 + 4)
        self.population = PopulationModel(profile["population"], self.terrain)
        p = profile["pollution"]
        self.p = p
        self.random_field = RandomField(seed * 10 + 1, p["random_field_length_km"], p["random_field_sigma"], city.center_lat, city.center_lon)
        self.weather = weather.reset_index(drop=True)
        self.timestamps = pd.DatetimeIndex(self.weather["timestamp"])
        self._prepare_temporal(seed)
        self.sources = self._expand_sources(profile.get("sources", []))
        self.coastline = profile.get("coastline")

    # -- temporal factors -------------------------------------------------
    def _prepare_temporal(self, seed: int) -> None:
        w = self.weather
        p = self.p
        self.hour = local_hours(self.timestamps, self.city.timezone)
        ws = w["wind_speed_ms"].to_numpy(dtype=float)
        blh = w["boundary_layer_height_m"].to_numpy(dtype=float)
        rh = w["relative_humidity_pct"].to_numpy(dtype=float)
        wd = w["wind_direction_deg"].to_numpy(dtype=float)
        vent = np.maximum(blh * ws, 60.0)
        self.dilution = np.clip((p["ventilation_reference"] / vent) ** p["ventilation_exponent"], 0.3, 3.5)
        self.humidity = 1.0 + 0.3 * np.clip((rh - 65.0) / 30.0, 0.0, 1.0)
        rng = np.random.default_rng(seed * 10 + 5)
        t_days = np.arange(len(w)) / 24.0
        per = np.array([2.2, 3.7, 5.9, 9.4])
        ph = rng.uniform(0, 2 * np.pi, size=4)
        wave = np.sin(2 * np.pi * t_days[None, :] / per[:, None] + ph[:, None]).mean(axis=0) * 1.6
        self.regional = 1.0 + p["regional_transport_amplitude"] * np.tanh(wave)
        self.seasonal = 1.0 + p["seasonal_trend"] * (t_days / 30.0)
        self.temporal = self.regional * self.dilution * self.humidity * self.seasonal
        to_dir = np.radians(wd + 180.0)  # direction the wind blows towards
        self.ux, self.uy = np.sin(to_dir), np.cos(to_dir)
        self.ws = ws
        self.profiles = {k: f(self.hour) for k, f in EMISSION_PROFILES.items()}
        onshore_dir = p.get("onshore_direction_deg")
        if onshore_dir is not None:
            self.onshore = np.clip(np.cos(np.radians(wd - onshore_dir)), 0.0, 1.0)
        else:
            self.onshore = np.zeros(len(w))

    def _expand_sources(self, sources: list[dict]) -> _SourcePoints:
        lat, lon, strength, radius, kind = [], [], [], [], []
        for s in sources:
            r = float(s["radius_km"])
            if "line" in s:
                spacing = 0.8 * r
                pts = polyline_points(s["line"], spacing)
                per_point = float(s["strength"]) * spacing / (r * np.sqrt(2 * np.pi))
                for plat, plon in pts:
                    lat.append(plat), lon.append(plon), strength.append(per_point), radius.append(r), kind.append(s["type"])
            else:
                lat.append(s["lat"]), lon.append(s["lon"]), strength.append(float(s["strength"])), radius.append(r), kind.append(s["type"])
        return _SourcePoints(np.array(lat), np.array(lon), np.array(strength), np.array(radius), kind)

    # -- static fields ----------------------------------------------------
    def static_terms(self, lat, lon) -> dict[str, np.ndarray]:
        lat = np.ravel(np.asarray(lat, dtype=float))
        lon = np.ravel(np.asarray(lon, dtype=float))
        p = self.p
        pop = self.population.density(lat, lon)
        ref = self.profile["population"]["reference_density"]
        pop_term = np.log1p(pop / 1000.0) / np.log1p(ref / 1000.0)
        elev = self.terrain.elevation(lat, lon)
        elev_factor = np.exp(-np.maximum(elev - p["elevation_reference_m"], 0.0) / p["elevation_scale_m"])
        rf = self.random_field(lat, lon)
        if self.coastline:
            coast_d = _min_distance_to_polyline_km(lat, lon, self.coastline)
            marine = p.get("marine_strength", 0.0) * np.exp(-coast_d / p.get("marine_decay_km", 3.0))
        else:
            marine = np.zeros_like(lat)
        return {"pop": pop, "pop_term": pop_term, "elev": elev, "elev_factor": elev_factor, "rf": rf, "marine": marine}

    # -- the field --------------------------------------------------------
    def pm25(self, lat, lon, time_index=None, chunk: int = 24) -> np.ndarray:
        """Truth PM2.5 (µg/m³) with shape (n_times, n_points)."""
        lat = np.ravel(np.asarray(lat, dtype=float))
        lon = np.ravel(np.asarray(lon, dtype=float))
        t_idx = np.arange(len(self.timestamps)) if time_index is None else np.atleast_1d(np.asarray(time_index, dtype=int))
        st = self.static_terms(lat, lon)
        p = self.p
        src = self.sources
        x, y = to_local_km(lat, lon, self.city.center_lat, self.city.center_lon)
        sx, sy = to_local_km(src.lat, src.lon, self.city.center_lat, self.city.center_lon)
        dx = (x[:, None] - sx[None, :]).astype(np.float32)  # (N, P)
        dy = (y[:, None] - sy[None, :]).astype(np.float32)
        r = src.radius.astype(np.float32)
        kinds = sorted(set(src.kind))
        static_mult = st["elev_factor"] * np.exp(st["rf"])
        out = np.empty((len(t_idx), len(lat)), dtype=float)
        for start in range(0, len(t_idx), chunk):
            tt = t_idx[start : start + chunk]
            ux = self.ux[tt].astype(np.float32)[:, None, None]
            uy = self.uy[tt].astype(np.float32)[:, None, None]
            ws = self.ws[tt].astype(np.float32)[:, None, None]
            along = dx[None] * ux + dy[None] * uy
            cross = -dx[None] * uy + dy[None] * ux
            shift = np.minimum(0.3 * ws, 1.5 * r[None, None, :])
            sig_a = r[None, None, :] * (1.0 + 0.12 * ws)
            kern = np.exp(-0.5 * (((along - shift) / sig_a) ** 2 + (cross / r[None, None, :]) ** 2))
            emis = np.empty((len(tt), len(r)), dtype=np.float32)
            for kname in kinds:
                cols = [i for i, k in enumerate(src.kind) if k == kname]
                emis[:, cols] = self.profiles[kname][tt][:, None] * src.strength[cols][None, :]
            source_term = np.einsum("tnp,tp->tn", kern, emis)
            urban = p["population_coefficient"] * st["pop_term"][None, :] * self.profiles["residential"][tt][:, None]
            inner = p["regional_background"] + p["urban_scale"] * (urban + source_term)
            pm = self.temporal[tt][:, None] * inner * static_mult[None, :]
            pm = pm * (1.0 - st["marine"][None, :] * self.onshore[tt][:, None])
            out[start : start + len(tt)] = pm
        return out

    def observe(self, lat, lon, time_index=None, kind: str = "reference", seed: int = 0) -> np.ndarray:
        """Noisy station-like observations of the truth (no gaps or faults)."""
        truth = self.pm25(lat, lon, time_index)
        rng = np.random.default_rng(seed)
        mult, add = NOISE_BY_KIND.get(kind, NOISE_BY_KIND["reference"])
        noisy = truth * np.exp(rng.normal(0.0, mult, size=truth.shape)) + rng.normal(0.0, add, size=truth.shape)
        return np.maximum(noisy, 0.0)


# --------------------------------------------------------------------------- dataset assembly


def _inject_faults(values: np.ndarray, rng: np.random.Generator, station_index: int) -> tuple[np.ndarray, dict]:
    """Add realistic gaps and faults so the QC pipeline has work to do."""
    v = values.copy()
    n = len(v)
    log = {"random_missing": 0, "outage_hours": 0, "spikes": 0, "negative": 0, "stuck_hours": 0}
    miss = rng.random(n) < 0.03
    v[miss] = np.nan
    log["random_missing"] = int(miss.sum())
    if station_index % 3 == 1:
        length = int(rng.integers(12, 37))
        start = int(rng.integers(24, n - length - 24))
        v[start : start + length] = np.nan
        log["outage_hours"] = length
    spikes = np.flatnonzero((rng.random(n) < 0.004) & ~np.isnan(v))
    v[spikes] = v[spikes] * rng.uniform(3.0, 6.0, size=len(spikes))
    log["spikes"] = int(len(spikes))
    neg = rng.choice(np.flatnonzero(~np.isnan(v)), size=2, replace=False)
    v[neg] = -rng.uniform(1.0, 8.0, size=2)
    log["negative"] = 2
    if station_index == 2:
        start = int(rng.integers(100, n - 50))
        v[start : start + 10] = v[start]
        log["stuck_hours"] = 10
    return v, log


def build_demo_dataset(city_id: str) -> dict:
    """Generate the full offline demo dataset (stations, observations, weather) for a city."""
    cities = load_cities()
    city = cities[city_id]
    spec = load_spec()
    profile = spec["cities"][city_id]
    seed = int(profile["seed"])
    timestamps = demo_timestamps(spec)
    weather = generate_weather(profile["climate"], timestamps, city.timezone, seed * 10 + 2)
    nature = NatureRun(city, profile, weather)
    stations = load_demo_stations()["cities"][city_id]
    lat = np.array([s["latitude"] for s in stations])
    lon = np.array([s["longitude"] for s in stations])
    truth = nature.pm25(lat, lon)  # (T, S)
    rng = np.random.default_rng(seed * 10 + 3)
    values, fault_log = {}, {}
    for j, s in enumerate(stations):
        mult, add = NOISE_BY_KIND[s["kind"]]
        noisy = truth[:, j] * np.exp(rng.normal(0.0, mult, size=len(timestamps))) + rng.normal(0.0, add, size=len(timestamps))
        noisy = np.maximum(noisy, 0.0)
        faulty, log = _inject_faults(noisy, rng, j)
        values[s["id"]] = [None if np.isnan(x) else round(float(x), 1) for x in faulty]
        fault_log[s["id"]] = log
    iso = [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in timestamps]
    return {
        "schema_version": 1,
        "city": city_id,
        "provenance": {
            "mode": "demo",
            "synthetic": True,
            "generator": GENERATOR_VERSION,
            "seed": seed,
            "period_start": iso[0],
            "period_end": iso[-1],
            "description": (
                "Synthetic offline demo dataset. Station readings are samples of AirScope's documented "
                "synthetic nature run with simulated measurement noise, gaps and faults. They are not "
                "observations from any real monitor, and the dates are only used to drive calendar features."
            ),
            "injected_faults": fault_log,
        },
        "stations": [
            {
                "id": s["id"],
                "name": s["name"],
                "latitude": s["latitude"],
                "longitude": s["longitude"],
                "kind": s["kind"],
                "provider": "AirScope synthetic demo",
                "license": "Synthetic data released with AirScope",
                "synthetic": True,
            }
            for s in stations
        ],
        "observations": {"timestamps": iso, "unit": "µg/m³", "parameter": "pm25", "values": values},
        "weather": {"timestamps": iso, **{c: weather[c].tolist() for c in WEATHER_COLUMNS}},
    }


def weather_from_cache(payload: dict) -> pd.DataFrame:
    w = payload["weather"]
    df = pd.DataFrame({c: np.asarray(w[c], dtype=float) for c in WEATHER_COLUMNS})
    df.insert(0, "timestamp", pd.to_datetime(w["timestamps"], utc=True))
    return df


def demo_cache_path(city_id: str) -> Path:
    return get_settings().cache_dir / f"{city_id}_demo.json"


def load_demo_payload(city_id: str) -> dict:
    path = demo_cache_path(city_id)
    if not path.exists():
        logger.info("Demo cache for %s missing - generating", city_id)
        write_demo_cache(city_id)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=8)
def get_nature_run(city_id: str) -> NatureRun:
    """Nature run consistent with the cached demo dataset (used by the OSSE)."""
    payload = load_demo_payload(city_id)
    city = load_cities()[city_id]
    profile = load_spec()["cities"][city_id]
    return NatureRun(city, profile, weather_from_cache(payload))


def write_demo_cache(city_id: str) -> Path:
    payload = build_demo_dataset(city_id)
    path = demo_cache_path(city_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"), ensure_ascii=False)
    tmp.replace(path)
    return path


def build_surfaces(city_ids: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Population and elevation lattices for the bundled CSV files."""
    cities = load_cities()
    spec = load_spec()
    pop_frames, elev_frames = [], []
    for cid in city_ids:
        city = cities[cid]
        profile = spec["cities"][cid]
        step = float(profile["lattice_step_deg"])
        min_lon, min_lat, max_lon, max_lat = city.bbox
        margin = 2 * step
        lats = np.round(np.arange(min_lat - margin, max_lat + margin + step / 2, step), 5)
        lons = np.round(np.arange(min_lon - margin, max_lon + margin + step / 2, step), 5)
        glat, glon = np.meshgrid(lats, lons, indexing="ij")
        terrain = TerrainModel(profile["terrain"], city, int(profile["seed"]) * 10 + 4)
        population = PopulationModel(profile["population"], terrain)
        dens = population.density(glat.ravel(), glon.ravel())
        elev = terrain.elevation(glat.ravel(), glon.ravel())
        pop_frames.append(pd.DataFrame({"city": cid, "latitude": glat.ravel(), "longitude": glon.ravel(), "population_density_per_km2": np.round(dens).astype(int)}))
        elev_frames.append(pd.DataFrame({"city": cid, "latitude": glat.ravel(), "longitude": glon.ravel(), "elevation_m": np.round(elev, 1)}))
    return pd.concat(pop_frames, ignore_index=True), pd.concat(elev_frames, ignore_index=True)


def generate_all(city_ids: list[str] | None = None) -> list[Path]:
    settings = get_settings()
    all_ids = list(load_cities().keys())
    city_ids = city_ids or all_ids
    written = []
    pop, elev = build_surfaces(all_ids)  # surfaces always cover every city
    pop_path = settings.datasets_dir / "population_density.csv"
    elev_path = settings.datasets_dir / "elevation.csv"
    pop.to_csv(pop_path, index=False)
    elev.to_csv(elev_path, index=False)
    written += [pop_path, elev_path]
    for cid in city_ids:
        written.append(write_demo_cache(cid))
    return written


def check_up_to_date() -> bool:
    """True when the bundled files equal a fresh deterministic regeneration."""
    settings = get_settings()
    ok = True
    pop, elev = build_surfaces(list(load_cities().keys()))
    for df, name in ((pop, "population_density.csv"), (elev, "elevation.csv")):
        on_disk = pd.read_csv(settings.datasets_dir / name)
        if not np.allclose(on_disk.select_dtypes("number").to_numpy(), df.select_dtypes("number").to_numpy(), atol=0.11):
            logger.error("%s differs from a fresh regeneration", name)
            ok = False
    for cid in load_cities():
        fresh = build_demo_dataset(cid)
        with open(demo_cache_path(cid), encoding="utf-8") as fh:
            disk = json.load(fh)
        if fresh["observations"]["values"] != disk["observations"]["values"]:
            logger.error("%s demo cache differs from a fresh regeneration", cid)
            ok = False
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate AirScope's deterministic synthetic demo data")
    parser.add_argument("--city", action="append", help="City id (repeatable). Default: all cities")
    parser.add_argument("--check", action="store_true", help="Verify bundled files match a fresh run")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.check:
        ok = check_up_to_date()
        print("Demo data is up to date." if ok else "Demo data differs from a fresh regeneration.")
        return 0 if ok else 1
    for path in generate_all(args.city):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
