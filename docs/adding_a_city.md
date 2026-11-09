# Adding a city

AirScope's city support is data, not code. To add a city (say, Peshawar) you add
records to a few files in `backend/datasets/`; the backend, the API and the UI pick
it up automatically.

## 1. Analysis domain - `city_boundaries.json` (required)

Add a GeoJSON `Feature` with a `Polygon` geometry in WGS84 `[lon, lat]` order and
these properties:

```json
{
  "type": "Feature",
  "properties": {
    "id": "peshawar",
    "name": "Peshawar",
    "country": "Pakistan",
    "timezone": "Asia/Karachi",
    "is_primary": false,
    "center": {"lat": 34.0080, "lon": 71.5785, "label": "Peshawar city centre"},
    "grid_cell_km": 0.75,
    "coverage_radius_km": 2.0,
    "correlation_length_km": 3.5,
    "openaq_radius_m": 25000,
    "domain_note": "How the domain was drawn and what it covers."
  },
  "geometry": {"type": "Polygon", "coordinates": [[[71.45, 33.95], [71.70, 33.95], [71.70, 34.10], [71.45, 34.10], [71.45, 33.95]]]}
}
```

| Property | Meaning |
|---|---|
| `grid_cell_km` | analysis cell size; aim for 800-2,500 cells inside the domain |
| `coverage_radius_km` | station representativeness scale used by coverage and the gap index |
| `correlation_length_km` | fallback covariance range if the variogram fit is unstable |
| `openaq_radius_m` | live-mode search radius around the centre (OpenAQ maximum 25,000 m) |

## 2. Population and elevation - `population_density.csv`, `elevation.csv` (required)

Regular lat/lon lattices covering the domain (with a small margin):

```
city,latitude,longitude,population_density_per_km2
peshawar,33.94,71.44,812
...
city,latitude,longitude,elevation_m
peshawar,33.94,71.44,352.0
```

For real analyses, derive them from WorldPop or GHSL (population) and a DEM such
as Copernicus GLO-90 (elevation): resample to ~0.005-0.01° cells, then export
cell centres. Values are interpolated bilinearly, so any lattice spacing works.

If you also want a synthetic demo for the new city, add a profile to
`synthetic_city_profiles.json` (population kernels, terrain, climate, sources) and
run `make data` - the generator writes both CSV files and `cache/peshawar_demo.json`.

## 3. Stations

* **Live mode** discovers stations from OpenAQ automatically within
  `openaq_radius_m` of the centre; stations outside the polygon are kept for display
  but excluded from training.
* **Demo mode** needs entries in `demo_stations.json` (`id`, `name`, `latitude`,
  `longitude`, `kind` = `reference` or `low-cost`) and a profile in
  `synthetic_city_profiles.json`.

## 4. Locality names - `localities.json` (optional)

`[name, lat, lon]` triples used to label clusters and recommended sites ("0.8 km
NE of Hayatabad"). Without them, coordinates are shown instead.

## 5. Train and check

```bash
make data        # demo mode only: regenerate surfaces and the demo cache
```

```bash
cd backend && .venv/bin/python -m ml.train --city peshawar
```

```bash
make test
```

The new city appears in the city switcher once its model is trained (the server
also trains missing models in the background on start-up). A city with no usable
stations still gets coverage-only gap analysis and sensor placement - often the
most useful output for a city about to install its first monitors.
