"""Feature engineering, validation and preprocessing.

Every training observation (one station-hour) and every prediction target
(one grid cell at one hour) is described by the same feature vector:

Spatial (static)            latitude, longitude*, elevation_m,
                            distance_to_center_km, log_population_density
Temporal (local time)       hour_sin, hour_cos, doy_sin, doy_cos, month
Meteorological (hourly)     temperature_c, relative_humidity_pct, wind_speed_ms,
                            wind_u, wind_v, surface_pressure_hpa,
                            boundary_layer_height_m, ventilation_index
Network context (hourly)    network_mean_pm25, idw_pm25

(*) Raw coordinates are part of every observation but are not used as model inputs
by default - see MODEL_FEATURES below.

Encoding choices: hour and day-of-year are cyclic (sin/cos) so 23:00 is close
to 00:00; wind direction becomes u/v components (359° ~ 1°); population density
is log-transformed; ``ventilation_index`` = boundary-layer height x wind speed
(m²/s), the standard dispersion proxy. The network-context features summarise
what the *other* stations measure at the same hour: their mean and an inverse
distance weighted (IDW) estimate. A station never sees its own reading in these
features, which keeps training consistent with prediction at unmonitored cells.

Missing values: physically impossible values are set to NaN by
:class:`FeatureValidator`, then a median imputer fitted on the training data
fills them - inside the same scikit-learn pipeline that is saved with the model,
so training and inference are preprocessed identically.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import TransformedTargetRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from config import CityConfig
from data.data_processor import CityDataset
from data.population_loader import ElevationLoader, PopulationLoader, get_elevation_loader, get_population_loader
from geospatial.distance import haversine_km, pairwise_haversine_km

FEATURE_SCHEMA_VERSION = 3
IDW_SMOOTHING_KM = 0.5

SPATIAL_FEATURES = ["latitude", "longitude", "elevation_m", "distance_to_center_km", "log_population_density"]
TEMPORAL_FEATURES = ["hour_sin", "hour_cos", "doy_sin", "doy_cos", "month"]
WEATHER_FEATURES = [
    "temperature_c",
    "relative_humidity_pct",
    "wind_speed_ms",
    "wind_u",
    "wind_v",
    "surface_pressure_hpa",
    "boundary_layer_height_m",
    "ventilation_index",
]
NETWORK_FEATURES = ["network_mean_pm25", "idw_pm25"]
COORDINATE_FEATURES = ["latitude", "longitude"]
# Every observation carries all of these (and they are validated) ...
ALL_FEATURES = SPATIAL_FEATURES + TEMPORAL_FEATURES + WEATHER_FEATURES + NETWORK_FEATURES
# ... but by default the tree models do not split on raw coordinates: with a handful of
# stations, such splits create axis-aligned artefacts and generalised worse to held-out
# stations in all three demo cities (ablation in docs/methodology.md). Location still enters
# through elevation, distance to centre, population density and the IDW network feature.
MODEL_FEATURES = [f for f in ALL_FEATURES if f not in COORDINATE_FEATURES]


def model_features(use_coordinates: bool = False) -> list[str]:
    """Model input columns; raw coordinates are opt-in (AIRSCOPE_COORDINATE_FEATURES=true)."""
    return list(ALL_FEATURES) if use_coordinates else list(MODEL_FEATURES)


FEATURE_GROUPS = {
    "spatial": SPATIAL_FEATURES,
    "temporal": TEMPORAL_FEATURES,
    "meteorological": WEATHER_FEATURES,
    "network_context": NETWORK_FEATURES,
}

# Physical plausibility limits; values outside become NaN and are imputed.
FEATURE_RANGES: dict[str, tuple[float, float]] = {
    "latitude": (-90.0, 90.0),
    "longitude": (-180.0, 180.0),
    "elevation_m": (-100.0, 6000.0),
    "distance_to_center_km": (0.0, 300.0),
    "log_population_density": (0.0, 12.0),
    "hour_sin": (-1.0, 1.0),
    "hour_cos": (-1.0, 1.0),
    "doy_sin": (-1.0, 1.0),
    "doy_cos": (-1.0, 1.0),
    "month": (1.0, 12.0),
    "temperature_c": (-40.0, 60.0),
    "relative_humidity_pct": (0.0, 100.0),
    "wind_speed_ms": (0.0, 75.0),
    "wind_u": (-75.0, 75.0),
    "wind_v": (-75.0, 75.0),
    "surface_pressure_hpa": (500.0, 1100.0),
    "boundary_layer_height_m": (0.0, 6000.0),
    "ventilation_index": (0.0, 450000.0),
    "network_mean_pm25": (0.0, 1000.0),
    "idw_pm25": (0.0, 1000.0),
}

FEATURE_DESCRIPTIONS = {
    "latitude": "Latitude (WGS84)",
    "longitude": "Longitude (WGS84)",
    "elevation_m": "Ground elevation (m)",
    "distance_to_center_km": "Distance to city reference point (km)",
    "log_population_density": "log(1 + population density per km²)",
    "hour_sin": "Hour of day (sine, local time)",
    "hour_cos": "Hour of day (cosine, local time)",
    "doy_sin": "Day of year (sine)",
    "doy_cos": "Day of year (cosine)",
    "month": "Month",
    "temperature_c": "Air temperature (°C)",
    "relative_humidity_pct": "Relative humidity (%)",
    "wind_speed_ms": "Wind speed (m/s)",
    "wind_u": "Wind eastward component (m/s)",
    "wind_v": "Wind northward component (m/s)",
    "surface_pressure_hpa": "Surface pressure (hPa)",
    "boundary_layer_height_m": "Boundary-layer height (m)",
    "ventilation_index": "Ventilation index = BLH x wind speed (m²/s)",
    "network_mean_pm25": "Mean PM2.5 at other stations, same hour",
    "idw_pm25": "Inverse-distance-weighted PM2.5 from other stations",
}


class FeatureValidator(BaseEstimator, TransformerMixin):
    """Coerce to float and blank out physically impossible values (-> NaN)."""

    def __init__(self, ranges: dict | None = None, columns: list | None = None):
        self.ranges = ranges
        self.columns = columns

    def fit(self, X, y=None):
        self.columns_ = list(self.columns or MODEL_FEATURES)
        return self

    def transform(self, X):
        cols = getattr(self, "columns_", self.columns or MODEL_FEATURES)
        ranges = self.ranges or FEATURE_RANGES
        if isinstance(X, pd.DataFrame):
            arr = X.reindex(columns=cols).to_numpy(dtype=float, copy=True)
        else:
            arr = np.array(X, dtype=float, copy=True)
        arr[~np.isfinite(arr)] = np.nan
        for j, col in enumerate(cols):
            lo, hi = ranges.get(col, (-np.inf, np.inf))
            bad = (arr[:, j] < lo) | (arr[:, j] > hi)
            arr[bad, j] = np.nan
        return arr

    def get_feature_names_out(self, input_features=None):
        return np.asarray(getattr(self, "columns_", self.columns or MODEL_FEATURES), dtype=object)


def make_model_pipeline(estimator, log_target: bool = True, columns: list[str] | None = None):
    """Validation -> median imputation -> estimator, optionally on log1p(PM2.5)."""
    pipe = Pipeline(
        [
            ("validate", FeatureValidator(columns=list(columns) if columns else None)),
            ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("model", estimator),
        ]
    )
    if log_target:
        return TransformedTargetRegressor(regressor=pipe, func=np.log1p, inverse_func=np.expm1, check_inverse=False)
    return pipe


def validation_report(X: pd.DataFrame) -> dict:
    """Counts of missing and out-of-range values per feature (before imputation)."""
    report = {}
    for col in ALL_FEATURES:
        values = pd.to_numeric(X[col], errors="coerce") if col in X else pd.Series(np.nan, index=X.index)
        lo, hi = FEATURE_RANGES[col]
        report[col] = {
            "missing": int(values.isna().sum()),
            "out_of_range": int(((values < lo) | (values > hi)).sum()),
        }
    return report


# --------------------------------------------------------------------------- builder


@dataclass
class TrainingTable:
    X: pd.DataFrame
    y: np.ndarray
    station_id: np.ndarray
    timestamp: pd.DatetimeIndex


class FeatureBuilder:
    """Builds model features for station-hours and grid-cell-hours of one city."""

    def __init__(self, city: CityConfig, population: PopulationLoader | None = None, elevation: ElevationLoader | None = None):
        self.city = city
        self.population = population or get_population_loader()
        self.elevation = elevation or get_elevation_loader()

    # -- static -----------------------------------------------------------
    def static_features(self, lat, lon) -> pd.DataFrame:
        lat = np.asarray(lat, dtype=float).ravel()
        lon = np.asarray(lon, dtype=float).ravel()
        pop = self.population.density_at(self.city.id, lat, lon)
        return pd.DataFrame(
            {
                "latitude": lat,
                "longitude": lon,
                "elevation_m": self.elevation.elevation_at(self.city.id, lat, lon),
                "distance_to_center_km": haversine_km(lat, lon, self.city.center_lat, self.city.center_lon),
                "log_population_density": np.log1p(pop),
                "population_density": pop,
            }
        )

    # -- temporal + weather -----------------------------------------------
    def time_weather_features(self, timestamps: pd.DatetimeIndex, weather: pd.DataFrame) -> pd.DataFrame:
        ts = pd.DatetimeIndex(timestamps)
        if ts.tz is None:
            ts = ts.tz_localize("UTC")
        local = ts.tz_convert(self.city.timezone)
        hour = local.hour.to_numpy() + local.minute.to_numpy() / 60.0
        doy = local.dayofyear.to_numpy()
        out = pd.DataFrame(
            {
                "hour_sin": np.sin(2 * np.pi * hour / 24.0),
                "hour_cos": np.cos(2 * np.pi * hour / 24.0),
                "doy_sin": np.sin(2 * np.pi * doy / 365.25),
                "doy_cos": np.cos(2 * np.pi * doy / 365.25),
                "month": local.month.to_numpy().astype(float),
            },
            index=ts,
        )
        w = weather.set_index("timestamp").reindex(ts)
        ws = w["wind_speed_ms"].to_numpy(dtype=float)
        wd = np.radians(w["wind_direction_deg"].to_numpy(dtype=float))
        blh = w["boundary_layer_height_m"].to_numpy(dtype=float)
        out["temperature_c"] = w["temperature_c"].to_numpy(dtype=float)
        out["relative_humidity_pct"] = w["relative_humidity_pct"].to_numpy(dtype=float)
        out["wind_speed_ms"] = ws
        # meteorological convention: direction the wind blows FROM
        out["wind_u"] = -ws * np.sin(wd)
        out["wind_v"] = -ws * np.cos(wd)
        out["surface_pressure_hpa"] = w["surface_pressure_hpa"].to_numpy(dtype=float)
        out["boundary_layer_height_m"] = blh
        out["ventilation_index"] = blh * ws
        return out

    # -- network context --------------------------------------------------
    @staticmethod
    def network_features(values: np.ndarray, distances_km: np.ndarray, exclude: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
        """Network mean and IDW estimate for targets from station readings.

        values:       (T, S) station PM2.5 (NaN = missing)
        distances_km: (N, S) target-to-station distances
        exclude:      optional (N, S) boolean mask of station readings a target
                      must not use (a station's own reading)
        Returns two (T, N) arrays; NaN where no station reading is available.
        """
        avail = ~np.isnan(values)  # (T, S)
        v = np.where(avail, values, 0.0)
        w = 1.0 / (distances_km**2 + IDW_SMOOTHING_KM**2)  # (N, S)
        use = np.ones_like(w, dtype=float) if exclude is None else (~exclude).astype(float)
        w = w * use
        a = avail.astype(float)
        num_idw = v @ w.T  # (T, N)
        den_idw = a @ w.T
        num_mean = v @ use.T
        den_mean = a @ use.T
        with np.errstate(invalid="ignore", divide="ignore"):
            idw = np.where(den_idw > 0, num_idw / den_idw, np.nan)
            mean = np.where(den_mean > 0, num_mean / den_mean, np.nan)
        return mean, idw

    # -- assembled tables -------------------------------------------------
    def training_table(self, ds: CityDataset, station_ids: list[str], network_ids: list[str] | None = None) -> TrainingTable:
        """Rows for the given stations; network features from ``network_ids`` (default: same set).

        A station's own reading is always excluded from its network features.
        """
        network_ids = list(network_ids if network_ids is not None else station_ids)
        st = ds.stations.set_index("station_id")
        wide = ds.obs_wide(usable_only=False)
        ts = wide.index
        net_vals = wide[network_ids].to_numpy(dtype=float)
        tgt = st.loc[station_ids]
        d = pairwise_haversine_km(tgt["latitude"], tgt["longitude"], st.loc[network_ids, "latitude"], st.loc[network_ids, "longitude"])
        exclude = np.array([[sid == nid for nid in network_ids] for sid in station_ids], dtype=bool)
        mean, idw = self.network_features(net_vals, d, exclude)
        tw = self.time_weather_features(ts, ds.weather)
        static = self.static_features(tgt["latitude"], tgt["longitude"])
        frames, ys, sids, tss = [], [], [], []
        for j, sid in enumerate(station_ids):
            y = wide[sid].to_numpy(dtype=float)
            ok = ~np.isnan(y)
            if not ok.any():
                continue
            block = tw.iloc[ok].reset_index(drop=True)
            for col in SPATIAL_FEATURES:
                block[col] = static[col].iloc[j]
            block["network_mean_pm25"] = mean[ok, j]
            block["idw_pm25"] = idw[ok, j]
            frames.append(block)
            ys.append(y[ok])
            sids.append(np.full(ok.sum(), sid, dtype=object))
            tss.append(ts[ok])
        if not frames:
            empty = pd.DataFrame(columns=ALL_FEATURES)
            return TrainingTable(empty, np.array([]), np.array([], dtype=object), pd.DatetimeIndex([], tz="UTC"))
        X = pd.concat(frames, ignore_index=True)[ALL_FEATURES]
        return TrainingTable(X, np.concatenate(ys), np.concatenate(sids), tss[0].append(tss[1:]))

    def target_features(
        self,
        lat,
        lon,
        timestamps: pd.DatetimeIndex,
        weather: pd.DataFrame,
        station_values: np.ndarray,
        station_lat,
        station_lon,
        static: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """Features for arbitrary targets (e.g. grid cells) at the given hours.

        ``station_values`` has shape (len(timestamps), n_stations). Rows are
        ordered time-major: all targets for timestamps[0], then timestamps[1]...
        """
        static = static if static is not None else self.static_features(lat, lon)
        n = len(static)
        ts = pd.DatetimeIndex(timestamps)
        d = pairwise_haversine_km(static["latitude"], static["longitude"], station_lat, station_lon)
        mean, idw = self.network_features(np.asarray(station_values, dtype=float).reshape(len(ts), -1), d)
        tw = self.time_weather_features(ts, weather)
        X = pd.DataFrame(np.repeat(tw.to_numpy(), n, axis=0), columns=tw.columns)
        for col in SPATIAL_FEATURES:
            X[col] = np.tile(static[col].to_numpy(), len(ts))
        X["network_mean_pm25"] = mean.ravel()
        X["idw_pm25"] = idw.ravel()
        return X[ALL_FEATURES]


@lru_cache(maxsize=8)
def get_feature_builder(city: CityConfig) -> FeatureBuilder:
    return FeatureBuilder(city)
