"""Request validation and response serialisation helpers for the HTTP API.

Validation is explicit and dependency-free: every parser raises
:class:`ValidationError` with a user-facing message, which the API turns into
an HTTP 400 response.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np
import pandas as pd

from geospatial.city_grid import CityGrid
from ml.gaps import GapWeights
from ml.sensor_placement import MAX_K, STRATEGIES, PlacementConstraints

MAX_SIM_SITES = 25


class ValidationError(ValueError):
    """Invalid client input (HTTP 400)."""


class NotReadyError(RuntimeError):
    """Model for a city is not trained yet (HTTP 503)."""

    def __init__(self, city_id: str, status: dict):
        super().__init__(f"Model for {city_id} is not ready")
        self.city_id = city_id
        self.status = status


# --------------------------------------------------------------------------- parsing


def _float(args: Mapping[str, Any], name: str, default: float, lo: float | None = None, hi: float | None = None) -> float:
    raw = args.get(name, default)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValidationError(f"'{name}' must be a number")
    if not math.isfinite(value):
        raise ValidationError(f"'{name}' must be finite")
    if lo is not None and value < lo:
        raise ValidationError(f"'{name}' must be >= {lo}")
    if hi is not None and value > hi:
        raise ValidationError(f"'{name}' must be <= {hi}")
    return value


def _int(args: Mapping[str, Any], name: str, default: int, lo: int, hi: int) -> int:
    raw = args.get(name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValidationError(f"'{name}' must be an integer")
    if not lo <= value <= hi:
        raise ValidationError(f"'{name}' must be between {lo} and {hi}")
    return value


def parse_time(args: Mapping[str, Any]) -> str:
    """'period' (default), 'latest', or an ISO-8601 timestamp."""
    raw = str(args.get("time", "period") or "period").strip()
    if raw.lower() in ("period", "latest"):
        return raw.lower()
    try:
        ts = pd.Timestamp(raw)
    except (ValueError, TypeError):
        raise ValidationError("'time' must be 'period', 'latest' or an ISO-8601 timestamp")
    ts = ts.tz_localize("UTC") if ts.tz is None else ts.tz_convert("UTC")
    return ts.floor("h").isoformat()


def parse_weights(args: Mapping[str, Any]) -> GapWeights:
    try:
        return GapWeights(
            coverage=_float(args, "w_coverage", 0.5, 0.0, 10.0),
            uncertainty=_float(args, "w_uncertainty", 0.5, 0.0, 10.0),
            pollution=_float(args, "w_pollution", 0.5, 0.0, 10.0),
            population=_float(args, "w_population", 0.5, 0.0, 10.0),
            balance=_float(args, "balance", 0.5, 0.0, 1.0),
        ).validated()
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


def parse_constraints(args: Mapping[str, Any]) -> PlacementConstraints:
    strategy = str(args.get("strategy", "coverage") or "coverage")
    if strategy not in STRATEGIES:
        raise ValidationError(f"'strategy' must be one of: {', '.join(STRATEGIES)}")
    try:
        return PlacementConstraints(
            k=_int(args, "k", 5, 1, MAX_K),
            strategy=strategy,
            min_spacing_km=_float(args, "min_spacing_km", 2.0, 0.0, 20.0),
            min_station_distance_km=_float(args, "min_station_distance_km", 1.5, 0.0, 20.0),
            min_population_density=_float(args, "min_population_density", 200.0, 0.0, 1e6),
            seed=_int(args, "seed", 0, 0, 10**6),
        ).validated()
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


def parse_sites(body: Any, max_sites: int = MAX_SIM_SITES) -> list[tuple[float, float]]:
    if not isinstance(body, Mapping):
        raise ValidationError("Request body must be a JSON object")
    sites = body.get("sites")
    if not isinstance(sites, list):
        raise ValidationError("'sites' must be a list of {lat, lon} objects")
    if len(sites) > max_sites:
        raise ValidationError(f"At most {max_sites} sites can be simulated at once")
    out = []
    for i, s in enumerate(sites):
        if not isinstance(s, Mapping):
            raise ValidationError(f"Site {i + 1} must be an object with 'lat' and 'lon'")
        lat = _float(s, "lat", float("nan"), -90.0, 90.0) if "lat" in s else None
        lon = _float(s, "lon", float("nan"), -180.0, 180.0) if "lon" in s else None
        if lat is None or lon is None or not (math.isfinite(lat) and math.isfinite(lon)):
            raise ValidationError(f"Site {i + 1} needs numeric 'lat' and 'lon'")
        out.append((lat, lon))
    return out


# --------------------------------------------------------------------------- serialisation


def clean_number(x: Any, decimals: int = 3):
    if x is None:
        return None
    if isinstance(x, (np.integer,)):
        return int(x)
    try:
        f = float(x)
    except (TypeError, ValueError):
        return x
    if not math.isfinite(f):
        return None
    return round(f, decimals)


def full_grid_list(grid: CityGrid, inside_values, decimals: int = 2) -> list:
    """Inside-cell values -> full-grid list with ``None`` outside the domain."""
    full = grid.to_full(np.asarray(inside_values, dtype=float))
    rounded = np.round(full, decimals)
    return [None if not math.isfinite(v) else (int(v) if decimals == 0 else float(v)) for v in rounded]


def full_grid_labels(grid: CityGrid, labels, mapping: dict[str, int]) -> list:
    codes = np.array([mapping.get(str(lab), -1) for lab in labels], dtype=float)
    full = grid.to_full(codes)
    return [None if not math.isfinite(v) else int(v) for v in full]


def jsonable(obj: Any) -> Any:
    """Recursively convert NumPy/Pandas values to JSON-safe Python types."""
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [jsonable(v) for v in obj.tolist()]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return None if not math.isfinite(float(obj)) else float(obj)
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    return obj
