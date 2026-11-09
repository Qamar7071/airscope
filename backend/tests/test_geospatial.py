import numpy as np
import pytest

from config import load_cities
from geospatial.city_grid import build_city_grid
from geospatial.distance import (
    KM_PER_DEG_LAT,
    bearing_deg,
    compass_label,
    from_local_km,
    haversine_km,
    nearest_distance_km,
    to_local_km,
)
from geospatial.gazetteer import describe_location
from geospatial.spatial_utils import label_regions, points_in_polygon, polygon_area_km2, polyline_points
from geospatial.surfaces import GriddedSurface

from conftest import make_test_city


def test_haversine_known_values():
    assert haversine_km(0, 0, 1, 0) == pytest.approx(KM_PER_DEG_LAT, rel=1e-9)
    assert haversine_km(0, 0, 0, 1) == pytest.approx(KM_PER_DEG_LAT, rel=1e-9)
    assert haversine_km(33.6, 73.0, 33.6, 73.0) == 0
    # Islamabad Zero Point to Lahore city centre: roughly 260-275 km
    assert 255 < haversine_km(33.6938, 73.0652, 31.5497, 74.3436) < 280


def test_local_projection_round_trip():
    x, y = to_local_km(33.7, 73.1, 33.6, 73.0)
    lat, lon = from_local_km(x, y, 33.6, 73.0)
    assert lat == pytest.approx(33.7) and lon == pytest.approx(73.1)
    assert np.hypot(x, y) == pytest.approx(haversine_km(33.6, 73.0, 33.7, 73.1), rel=2e-3)


def test_nearest_distance_and_bearing():
    d, idx = nearest_distance_km([33.6], [73.0], [33.7, 33.61], [73.0, 73.0])
    assert idx[0] == 1 and d[0] == pytest.approx(0.01 * KM_PER_DEG_LAT, rel=1e-6)
    d, idx = nearest_distance_km([33.6], [73.0], [], [])
    assert np.isinf(d[0]) and idx[0] == -1
    assert bearing_deg(0, 0, 1, 0) == pytest.approx(0)
    assert bearing_deg(0, 0, 0, 1) == pytest.approx(90)
    assert compass_label(225) == "SW" and compass_label(359) == "N"


def test_point_in_polygon_with_hole():
    outer = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
    hole = [(4, 4), (6, 4), (6, 6), (4, 6), (4, 4)]
    lon = np.array([1, 5, 11, 9.9])
    lat = np.array([1, 5, 5, 9.9])
    assert list(points_in_polygon(lon, lat, [outer, hole])) == [True, False, False, True]


def test_polygon_area_one_degree_square_at_equator():
    ring = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
    assert polygon_area_km2([ring]) == pytest.approx(KM_PER_DEG_LAT**2, rel=1e-3)


def test_label_regions_connectivity():
    m = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=bool)
    assert label_regions(m, 8)[1] == 1
    assert label_regions(m, 4)[1] == 3


def test_polyline_densification_spacing():
    pts = polyline_points([(33.6, 73.0), (33.6, 73.1)], spacing_km=1.0)
    gaps = haversine_km(pts[:-1, 0], pts[:-1, 1], pts[1:, 0], pts[1:, 1])
    assert gaps.max() <= 1.0 + 1e-6 and len(pts) >= 10


def test_city_grid_layout_and_locate():
    city = make_test_city(cell_km=1.0)
    g = build_city_grid(city)
    assert g.n_cells == g.nrows * g.ncols and g.n_inside > 50
    assert g.cell_area_km2 == pytest.approx(1.0, rel=0.02)
    # row 0 is north: latitude decreases with row index
    assert g.lat[0] > g.lat[g.ncols]
    j = g.inside_index[10]
    assert g.locate(g.lat[j], g.lon[j]) == j
    assert g.locate(0.0, 0.0) == -1
    full = g.to_full(np.arange(g.n_inside))
    assert np.isnan(full[~g.mask]).all() and full[g.inside_index[3]] == 3


def test_real_city_grids_cover_their_stations():
    import json
    from config import get_settings

    stations = json.load(open(get_settings().datasets_dir / "demo_stations.json"))["cities"]
    for cid, city in load_cities().items():
        g = build_city_grid(city)
        assert 500 < g.n_inside < 3000
        for s in stations[cid]:
            assert g.locate(s["latitude"], s["longitude"]) >= 0, (cid, s["id"])


def test_gridded_surface_bilinear_and_clamp():
    import pandas as pd

    df = pd.DataFrame({"latitude": [0, 0, 1, 1], "longitude": [0, 1, 0, 1], "v": [0.0, 10.0, 20.0, 30.0]})
    s = GriddedSurface.from_frame(df, "v")
    assert s.sample(0.5, 0.5) == pytest.approx(15.0)
    assert s.sample(0, 0.25) == pytest.approx(2.5)
    assert s.sample(-5, -5) == pytest.approx(0.0)  # clamped to the edge


def test_describe_location():
    out = describe_location("islamabad", 33.7290, 73.0760)
    assert out["name"] == "F-6" and out["label"] == "F-6"
    far = describe_location("islamabad", 33.66, 73.12)
    assert "km" in far["label"]
