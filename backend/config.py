"""Central configuration for the AirScope backend.

Settings come from environment variables (optionally loaded from ``backend/.env``).
City definitions (boundary, centre, grid resolution, modelling defaults) are
loaded from ``datasets/city_boundaries.json`` so that adding a city is a data
change, not a code change. See ``docs/adding_a_city.md``.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")

APP_VERSION = "1.0.0"
VALID_DATA_MODES = ("demo", "live", "auto")


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    """Runtime settings. Instances are immutable; use :func:`get_settings`."""

    data_mode: str = "demo"
    openaq_api_key: str | None = None
    openaq_base_url: str = "https://api.openaq.org/v3"
    open_meteo_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    open_meteo_archive_url: str = "https://archive-api.open-meteo.com/v1/archive"
    http_timeout_s: float = 20.0
    live_history_days: int = 14
    live_cache_ttl_hours: float = 1.0
    datasets_dir: Path = BACKEND_DIR / "datasets"
    cache_dir: Path = BACKEND_DIR / "cache"
    models_dir: Path = BACKEND_DIR / "models"
    frontend_dist: Path = PROJECT_DIR / "frontend" / "dist"
    random_seed: int = 42
    train_on_startup: bool = True
    training_profile: str = "full"
    use_coordinate_features: bool = False
    cors_origins: tuple[str, ...] = ("*",)
    log_level: str = "INFO"

    @property
    def live_enabled(self) -> bool:
        """Live mode needs an OpenAQ key (OpenAQ v3 requires a free key)."""
        return self.data_mode in ("live", "auto") and bool(self.openaq_api_key)


def load_settings() -> Settings:
    mode = _env_str("AIRSCOPE_DATA_MODE", "demo").lower()
    if mode not in VALID_DATA_MODES:
        logging.getLogger(__name__).warning("Unknown AIRSCOPE_DATA_MODE=%r; using 'demo'", mode)
        mode = "demo"
    origins = tuple(o.strip() for o in _env_str("AIRSCOPE_CORS_ORIGINS", "*").split(",") if o.strip())
    models_dir = Path(_env_str("AIRSCOPE_MODELS_DIR", str(BACKEND_DIR / "models")))
    cache_dir = Path(_env_str("AIRSCOPE_CACHE_DIR", str(BACKEND_DIR / "cache")))
    profile = _env_str("AIRSCOPE_TRAINING_PROFILE", "full").lower()
    return Settings(
        data_mode=mode,
        openaq_api_key=os.environ.get("OPENAQ_API_KEY") or None,
        openaq_base_url=_env_str("OPENAQ_BASE_URL", Settings.openaq_base_url),
        open_meteo_forecast_url=_env_str("OPEN_METEO_FORECAST_URL", Settings.open_meteo_forecast_url),
        open_meteo_archive_url=_env_str("OPEN_METEO_ARCHIVE_URL", Settings.open_meteo_archive_url),
        http_timeout_s=_env_float("AIRSCOPE_HTTP_TIMEOUT_S", 20.0),
        live_history_days=max(2, min(_env_int("AIRSCOPE_LIVE_HISTORY_DAYS", 14), 90)),
        live_cache_ttl_hours=_env_float("AIRSCOPE_LIVE_CACHE_TTL_HOURS", 1.0),
        models_dir=models_dir,
        cache_dir=cache_dir,
        random_seed=_env_int("AIRSCOPE_RANDOM_SEED", 42),
        train_on_startup=_env_bool("AIRSCOPE_TRAIN_ON_STARTUP", True),
        training_profile=profile if profile in ("full", "fast") else "full",
        use_coordinate_features=_env_bool("AIRSCOPE_COORDINATE_FEATURES", False),
        cors_origins=origins or ("*",),
        log_level=_env_str("AIRSCOPE_LOG_LEVEL", "INFO").upper(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


# --------------------------------------------------------------------------- cities


@dataclass(frozen=True)
class CityConfig:
    """Static description of a supported city / analysis domain."""

    id: str
    name: str
    country: str
    timezone: str
    center_lat: float
    center_lon: float
    center_label: str
    boundary: tuple[tuple[tuple[float, float], ...], ...]  # rings of (lon, lat)
    grid_cell_km: float
    coverage_radius_km: float
    correlation_length_km: float
    openaq_radius_m: int
    domain_note: str
    is_primary: bool = False
    extra: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """(min_lon, min_lat, max_lon, max_lat) of the outer boundary ring."""
        lons = [p[0] for p in self.boundary[0]]
        lats = [p[1] for p in self.boundary[0]]
        return min(lons), min(lats), max(lons), max(lats)

    def summary(self) -> dict:
        min_lon, min_lat, max_lon, max_lat = self.bbox
        return {
            "id": self.id,
            "name": self.name,
            "country": self.country,
            "timezone": self.timezone,
            "center": {"lat": self.center_lat, "lon": self.center_lon, "label": self.center_label},
            "bbox": {"west": min_lon, "south": min_lat, "east": max_lon, "north": max_lat},
            "grid_cell_km": self.grid_cell_km,
            "coverage_radius_km": self.coverage_radius_km,
            "domain_note": self.domain_note,
            "is_primary": self.is_primary,
        }

    def boundary_geojson(self) -> dict:
        return {
            "type": "Polygon",
            "coordinates": [[list(p) for p in ring] for ring in self.boundary],
        }


def _parse_city(feature: dict) -> CityConfig:
    props = feature["properties"]
    geom = feature["geometry"]
    if geom.get("type") != "Polygon":
        raise ValueError(f"City {props.get('id')}: only Polygon boundaries are supported")
    rings = []
    for ring in geom["coordinates"]:
        pts = tuple((float(lon), float(lat)) for lon, lat in ring)
        if len(pts) < 4:
            raise ValueError(f"City {props.get('id')}: boundary ring needs >= 4 points")
        rings.append(pts)
    known = {
        "id", "name", "country", "timezone", "center", "grid_cell_km", "coverage_radius_km",
        "correlation_length_km", "openaq_radius_m", "domain_note", "is_primary",
    }
    return CityConfig(
        id=str(props["id"]).lower(),
        name=props["name"],
        country=props.get("country", ""),
        timezone=props.get("timezone", "UTC"),
        center_lat=float(props["center"]["lat"]),
        center_lon=float(props["center"]["lon"]),
        center_label=props["center"].get("label", "City centre"),
        boundary=tuple(rings),
        grid_cell_km=float(props.get("grid_cell_km", 0.75)),
        coverage_radius_km=float(props.get("coverage_radius_km", 2.0)),
        correlation_length_km=float(props.get("correlation_length_km", 3.0)),
        openaq_radius_m=int(min(25000, props.get("openaq_radius_m", 25000))),
        domain_note=props.get("domain_note", ""),
        is_primary=bool(props.get("is_primary", False)),
        extra={k: v for k, v in props.items() if k not in known},
    )


@lru_cache(maxsize=4)
def load_cities(datasets_dir: str | None = None) -> dict[str, CityConfig]:
    """Load the city registry (ordered: primary city first, then file order)."""
    path = Path(datasets_dir or get_settings().datasets_dir) / "city_boundaries.json"
    with open(path, encoding="utf-8") as fh:
        collection = json.load(fh)
    cities = [_parse_city(f) for f in collection["features"]]
    cities.sort(key=lambda c: (not c.is_primary,))
    return {c.id: c for c in cities}


def get_city(city_id: str) -> CityConfig:
    cities = load_cities()
    key = (city_id or "").lower()
    if key not in cities:
        raise KeyError(city_id)
    return cities[key]
