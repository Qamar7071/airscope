"""Distance and projection helpers (vectorised, NumPy-based).

All public functions accept scalars or array-likes and broadcast like NumPy.
Distances are great-circle (haversine) distances in kilometres. For the city
scale used by AirScope (< 60 km) a local equirectangular projection is accurate
to well below 0.1 %, so it is used where planar geometry is convenient.
"""
from __future__ import annotations

import numpy as np

EARTH_RADIUS_KM = 6371.0088
KM_PER_DEG_LAT = np.pi * EARTH_RADIUS_KM / 180.0  # ~111.195 km


def haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Great-circle distance in km between (lat1, lon1) and (lat2, lon2)."""
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(v, dtype=float)) for v in (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def pairwise_haversine_km(lat_a, lon_a, lat_b, lon_b) -> np.ndarray:
    """Matrix of distances, shape ``(len(a), len(b))``."""
    lat_a = np.asarray(lat_a, dtype=float).reshape(-1, 1)
    lon_a = np.asarray(lon_a, dtype=float).reshape(-1, 1)
    lat_b = np.asarray(lat_b, dtype=float).reshape(1, -1)
    lon_b = np.asarray(lon_b, dtype=float).reshape(1, -1)
    return haversine_km(lat_a, lon_a, lat_b, lon_b)


def nearest_distance_km(lat, lon, ref_lat, ref_lon) -> tuple[np.ndarray, np.ndarray]:
    """Distance to, and index of, the nearest reference point for each query point.

    Returns ``(inf, -1)`` for every query point when there are no reference points.
    """
    lat = np.atleast_1d(np.asarray(lat, dtype=float))
    lon = np.atleast_1d(np.asarray(lon, dtype=float))
    ref_lat = np.atleast_1d(np.asarray(ref_lat, dtype=float))
    if ref_lat.size == 0:
        return np.full(lat.shape, np.inf), np.full(lat.shape, -1, dtype=int)
    d = pairwise_haversine_km(lat, lon, ref_lat, ref_lon)
    idx = np.argmin(d, axis=1)
    return d[np.arange(d.shape[0]), idx], idx


def km_per_deg_lon(lat0: float) -> float:
    return KM_PER_DEG_LAT * float(np.cos(np.radians(lat0)))


def to_local_km(lat, lon, lat0: float, lon0: float) -> tuple[np.ndarray, np.ndarray]:
    """Equirectangular projection to (x east, y north) in km around (lat0, lon0)."""
    x = (np.asarray(lon, dtype=float) - lon0) * km_per_deg_lon(lat0)
    y = (np.asarray(lat, dtype=float) - lat0) * KM_PER_DEG_LAT
    return x, y


def from_local_km(x, y, lat0: float, lon0: float) -> tuple[np.ndarray, np.ndarray]:
    """Inverse of :func:`to_local_km`; returns (lat, lon)."""
    lat = lat0 + np.asarray(y, dtype=float) / KM_PER_DEG_LAT
    lon = lon0 + np.asarray(x, dtype=float) / km_per_deg_lon(lat0)
    return lat, lon


def bearing_deg(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Initial bearing from point 1 to point 2 in degrees clockwise from north."""
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(v, dtype=float)) for v in (lat1, lon1, lat2, lon2))
    dlon = lon2 - lon1
    x = np.sin(dlon) * np.cos(lat2)
    y = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)
    return (np.degrees(np.arctan2(x, y)) + 360.0) % 360.0


def compass_label(bearing: float) -> str:
    labels = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return labels[int(((float(bearing) % 360) + 22.5) // 45) % 8]
