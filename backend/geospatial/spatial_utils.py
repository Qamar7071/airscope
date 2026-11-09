"""Geometry utilities: point-in-polygon, areas, connected regions.

Implemented with NumPy/SciPy only so the core platform does not require
GeoPandas/Shapely (they remain optional for users who want GIS exports).
"""
from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np
from scipy import ndimage

from .distance import to_local_km

Ring = Sequence[tuple[float, float]]  # (lon, lat) pairs


def _points_in_ring(lon: np.ndarray, lat: np.ndarray, ring: Ring) -> np.ndarray:
    """Even-odd ray casting for a single ring. Vectorised over points."""
    pts = np.asarray(ring, dtype=float)
    if np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]
    xs, ys = pts[:, 0], pts[:, 1]
    inside = np.zeros(lon.shape, dtype=bool)
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi, xj, yj = xs[i], ys[i], xs[j], ys[j]
        crosses = (yi > lat) != (yj > lat)
        with np.errstate(divide="ignore", invalid="ignore"):
            x_at = (xj - xi) * (lat - yi) / (yj - yi) + xi
        inside ^= crosses & (lon < x_at)
        j = i
    return inside


def points_in_polygon(lon, lat, rings: Sequence[Ring]) -> np.ndarray:
    """True where a point lies inside the polygon (outer ring minus holes)."""
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    if not rings:
        return np.zeros(lon.shape, dtype=bool)
    inside = _points_in_ring(lon, lat, rings[0])
    for hole in rings[1:]:
        inside &= ~_points_in_ring(lon, lat, hole)
    return inside


def ring_area_km2(ring: Ring) -> float:
    """Planar (shoelace) area of a lon/lat ring after local projection, in km²."""
    pts = np.asarray(ring, dtype=float)
    lat0 = float(pts[:, 1].mean())
    lon0 = float(pts[:, 0].mean())
    x, y = to_local_km(pts[:, 1], pts[:, 0], lat0, lon0)
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)


def polygon_area_km2(rings: Sequence[Ring]) -> float:
    if not rings:
        return 0.0
    return ring_area_km2(rings[0]) - sum(ring_area_km2(h) for h in rings[1:])


def label_regions(mask_2d: np.ndarray, connectivity: int = 8) -> tuple[np.ndarray, int]:
    """Label connected True regions of a 2-D boolean mask (4- or 8-connectivity)."""
    if connectivity not in (4, 8):
        raise ValueError("connectivity must be 4 or 8")
    structure = np.ones((3, 3), dtype=bool) if connectivity == 8 else ndimage.generate_binary_structure(2, 1)
    labels, n = ndimage.label(np.asarray(mask_2d, dtype=bool), structure=structure)
    return labels, int(n)


def polyline_points(line: Iterable[Sequence[float]], spacing_km: float) -> np.ndarray:
    """Densify a polyline given as [(lat, lon), ...] into points ~``spacing_km`` apart.

    Returns an array of shape (n, 2) with (lat, lon) rows. Used to represent
    line sources such as road corridors.
    """
    line = np.asarray(list(line), dtype=float)
    if len(line) == 1:
        return line.copy()
    lat0, lon0 = float(line[:, 0].mean()), float(line[:, 1].mean())
    x, y = to_local_km(line[:, 0], line[:, 1], lat0, lon0)
    out = []
    for i in range(len(line) - 1):
        seg_len = float(np.hypot(x[i + 1] - x[i], y[i + 1] - y[i]))
        n = max(1, int(np.ceil(seg_len / max(spacing_km, 1e-6))))
        for k in range(n):
            t = k / n
            out.append((line[i, 0] + t * (line[i + 1, 0] - line[i, 0]), line[i, 1] + t * (line[i + 1, 1] - line[i, 1])))
    out.append(tuple(line[-1]))
    return np.asarray(out, dtype=float)
