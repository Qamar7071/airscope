"""Gridded raster-like surfaces (population density, elevation, ...).

A :class:`GriddedSurface` is built from a CSV with ``latitude, longitude, value``
rows on a regular lat/lon lattice and supports vectorised bilinear sampling.
Points outside the lattice are clamped to the nearest edge value, which is the
conservative choice for slightly-out-of-domain queries.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class GriddedSurface:
    lats: np.ndarray  # ascending, shape (nlat,)
    lons: np.ndarray  # ascending, shape (nlon,)
    values: np.ndarray  # shape (nlat, nlon)
    name: str = "surface"

    @classmethod
    def from_frame(cls, df: pd.DataFrame, value_col: str, name: str | None = None) -> "GriddedSurface":
        if df.empty:
            raise ValueError("Cannot build a surface from an empty table")
        lats = np.sort(df["latitude"].astype(float).unique())
        lons = np.sort(df["longitude"].astype(float).unique())
        table = df.pivot_table(index="latitude", columns="longitude", values=value_col, aggfunc="mean")
        table = table.reindex(index=lats, columns=lons)
        values = table.to_numpy(dtype=float)
        if np.isnan(values).any():
            # Fill holes in an incomplete lattice with the nearest valid value.
            from scipy import ndimage

            invalid = np.isnan(values)
            idx = ndimage.distance_transform_edt(invalid, return_distances=False, return_indices=True)
            values = values[tuple(idx)]
        return cls(lats=lats, lons=lons, values=values, name=name or value_col)

    def sample(self, lat, lon) -> np.ndarray:
        """Bilinear interpolation at the given coordinates (broadcasting)."""
        lat = np.asarray(lat, dtype=float)
        lon = np.asarray(lon, dtype=float)
        if len(self.lats) == 1 or len(self.lons) == 1:
            i = np.clip(np.searchsorted(self.lats, lat), 0, len(self.lats) - 1)
            j = np.clip(np.searchsorted(self.lons, lon), 0, len(self.lons) - 1)
            return self.values[i, j]
        lat_c = np.clip(lat, self.lats[0], self.lats[-1])
        lon_c = np.clip(lon, self.lons[0], self.lons[-1])
        i = np.clip(np.searchsorted(self.lats, lat_c) - 1, 0, len(self.lats) - 2)
        j = np.clip(np.searchsorted(self.lons, lon_c) - 1, 0, len(self.lons) - 2)
        lat0, lat1 = self.lats[i], self.lats[i + 1]
        lon0, lon1 = self.lons[j], self.lons[j + 1]
        ty = (lat_c - lat0) / (lat1 - lat0)
        tx = (lon_c - lon0) / (lon1 - lon0)
        v00 = self.values[i, j]
        v01 = self.values[i, j + 1]
        v10 = self.values[i + 1, j]
        v11 = self.values[i + 1, j + 1]
        return (v00 * (1 - tx) * (1 - ty) + v01 * tx * (1 - ty) + v10 * (1 - tx) * ty + v11 * tx * ty)

    @property
    def resolution_deg(self) -> tuple[float, float]:
        dlat = float(np.median(np.diff(self.lats))) if len(self.lats) > 1 else 0.0
        dlon = float(np.median(np.diff(self.lons))) if len(self.lons) > 1 else 0.0
        return dlat, dlon
