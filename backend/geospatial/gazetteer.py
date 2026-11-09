"""Tiny gazetteer used to describe coordinates in words ("near I-10, 0.8 km SW")."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from config import get_settings
from .distance import bearing_deg, compass_label, haversine_km


@lru_cache(maxsize=4)
def load_localities(datasets_dir: str | None = None) -> dict[str, list[tuple[str, float, float]]]:
    path = Path(datasets_dir or get_settings().datasets_dir) / "localities.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return {city.lower(): [(str(n), float(a), float(b)) for n, a, b in rows] for city, rows in raw.get("cities", {}).items()}


def describe_location(city_id: str, lat: float, lon: float) -> dict:
    """Return the nearest named locality with distance and direction."""
    places = load_localities().get(city_id.lower(), [])
    if not places:
        return {"name": None, "distance_km": None, "direction": None, "label": f"{lat:.4f}, {lon:.4f}"}
    names = [p[0] for p in places]
    lats = np.array([p[1] for p in places])
    lons = np.array([p[2] for p in places])
    d = haversine_km(lat, lon, lats, lons)
    i = int(np.argmin(d))
    dist = float(d[i])
    if dist < 0.6:
        label = names[i]
    else:
        direction = compass_label(float(bearing_deg(lats[i], lons[i], lat, lon)))
        label = f"{dist:.1f} km {direction} of {names[i]}"
    return {"name": names[i], "distance_km": round(dist, 2), "label": label}
