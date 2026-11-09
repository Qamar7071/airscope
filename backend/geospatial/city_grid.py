"""Regular analysis grid covering a city's boundary polygon.

Layout convention (shared with the frontend):
  * cells are approximately square (``cell_km`` on each side);
  * row 0 is the northernmost row and column 0 the westernmost column;
  * the flat index of a cell is ``row * ncols + col`` (row-major);
  * arrays sent to the frontend cover *all* cells, with ``null`` outside the
    boundary, so that they can be painted directly onto a canvas.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from config import CityConfig
from .distance import KM_PER_DEG_LAT, km_per_deg_lon
from .spatial_utils import points_in_polygon, polygon_area_km2


@dataclass(frozen=True)
class CityGrid:
    city_id: str
    north: float
    south: float
    east: float
    west: float
    nrows: int
    ncols: int
    dlat: float
    dlon: float
    cell_km: float
    lat: np.ndarray
    lon: np.ndarray
    mask: np.ndarray

    @property
    def n_cells(self) -> int:
        return self.nrows * self.ncols

    @property
    def inside_index(self) -> np.ndarray:
        return np.flatnonzero(self.mask)

    @property
    def n_inside(self) -> int:
        return int(self.mask.sum())

    @property
    def cell_area_km2(self) -> float:
        return float((self.dlat * KM_PER_DEG_LAT) * (self.dlon * km_per_deg_lon((self.north + self.south) / 2)))

    @property
    def inside_lat(self) -> np.ndarray:
        return self.lat[self.mask]

    @property
    def inside_lon(self) -> np.ndarray:
        return self.lon[self.mask]

    def rowcol(self, flat_index) -> tuple[np.ndarray, np.ndarray]:
        flat_index = np.asarray(flat_index)
        return flat_index // self.ncols, flat_index % self.ncols

    def locate(self, lat: float, lon: float) -> int:
        """Flat index of the cell containing (lat, lon), or -1 if outside the domain."""
        if not (self.south <= lat <= self.north and self.west <= lon <= self.east):
            return -1
        row = min(int((self.north - lat) / self.dlat), self.nrows - 1)
        col = min(int((lon - self.west) / self.dlon), self.ncols - 1)
        idx = row * self.ncols + col
        return idx if self.mask[idx] else -1

    def to_full(self, inside_values, fill=np.nan) -> np.ndarray:
        """Scatter values defined on inside cells into a full-grid array."""
        inside_values = np.asarray(inside_values)
        full = np.full(self.n_cells, fill, dtype=float if inside_values.dtype.kind in "fiu" else object)
        full[self.mask] = inside_values
        return full

    def inside_position(self) -> np.ndarray:
        """Map flat index -> position within the inside-cell arrays (-1 outside)."""
        pos = np.full(self.n_cells, -1, dtype=int)
        pos[self.mask] = np.arange(self.n_inside)
        return pos

    def geometry(self) -> dict:
        return {
            "north": self.north,
            "south": self.south,
            "east": self.east,
            "west": self.west,
            "nrows": self.nrows,
            "ncols": self.ncols,
            "dlat": self.dlat,
            "dlon": self.dlon,
            "cell_km": self.cell_km,
            "cell_area_km2": round(self.cell_area_km2, 4),
            "n_inside": self.n_inside,
            "mask": self.mask.astype(int).tolist(),
        }


def build_city_grid(city: CityConfig, cell_km: float | None = None) -> CityGrid:
    cell_km = float(cell_km or city.grid_cell_km)
    min_lon, min_lat, max_lon, max_lat = city.bbox
    dlat = cell_km / KM_PER_DEG_LAT
    dlon = cell_km / km_per_deg_lon(city.center_lat)
    ncols = int(np.ceil((max_lon - min_lon) / dlon))
    nrows = int(np.ceil((max_lat - min_lat) / dlat))
    north, west = max_lat, min_lon
    south, east = north - nrows * dlat, west + ncols * dlon
    rows, cols = np.divmod(np.arange(nrows * ncols), ncols)
    lat = north - (rows + 0.5) * dlat
    lon = west + (cols + 0.5) * dlon
    mask = points_in_polygon(lon, lat, city.boundary)
    return CityGrid(
        city_id=city.id, north=north, south=south, east=east, west=west,
        nrows=nrows, ncols=ncols, dlat=dlat, dlon=dlon, cell_km=cell_km,
        lat=lat, lon=lon, mask=mask,
    )


@lru_cache(maxsize=16)
def get_city_grid(city: CityConfig) -> CityGrid:
    return build_city_grid(city)


def domain_area_km2(city: CityConfig) -> float:
    return polygon_area_km2(city.boundary)
