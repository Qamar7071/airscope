# Data sources, licences and attribution

AirScope uses only free and open data and software. Licence terms of
third-party services can change: verify them before any production or commercial
use. The same information is served by `GET /api/sources` and shown in the app
(About → Data & licences).

## External data and services

| Source | Used for | Access | Licence / terms | Required attribution |
|---|---|---|---|---|
| **OpenAQ API v3** (openaq.org) | Live mode: station locations and hourly PM2.5 | Free API key (`X-API-Key` header). Not needed for the offline demo. | OpenAQ aggregates data from many providers; **each location has its own licence** (returned in the `licenses` field). AirScope keeps it per station and shows it in station details. Respect the OpenAQ API terms and rate limits. | "Data from OpenAQ (openaq.org)" plus the original provider of each station |
| **Open-Meteo** (open-meteo.com) | Live mode: hourly weather (temperature, humidity, wind, pressure, boundary-layer height) | No key. Free API for non-commercial use; commercial use requires an API subscription. | Data under **CC BY 4.0**. | "Weather data by Open-Meteo.com" |
| **CARTO basemaps** (Dark Matter) | Map background tiles | No key. | Free for non-commercial use within CARTO's limits; commercial or high-volume use needs a CARTO licence (see carto.com/basemaps and the CartoDB/basemap-styles repository). Map data © OpenStreetMap contributors under the **ODbL**. | "© OpenStreetMap contributors © CARTO" (shown on the map) |

## Bundled data created for AirScope

All bundled files are released with the project. They are **approximations for
demonstration**, documented in [`backend/datasets/README.md`](../backend/datasets/README.md).

| File | Content | Status |
|---|---|---|
| `datasets/city_boundaries.json` | Analysis domains, centres, grid settings | Hand-digitised approximations, not administrative boundaries |
| `datasets/demo_stations.json` | Simulated station sites | Synthetic, plausible locations; not real monitors |
| `datasets/localities.json` | Locality names and approximate coordinates | For labels only; ~0.5-1 km accuracy |
| `datasets/population_density.csv` | Population density lattice | Approximate surface built from locality-level kernels - not census data |
| `datasets/elevation.csv` | Elevation lattice | Simple terrain model (base gradient + Margalla ridge, hills, river floodplain) - not a DEM |
| `datasets/synthetic_city_profiles.json` | Parameters of the synthetic nature run | Illustrative; not an emission inventory |
| `cache/<city>_demo.json` | Offline demo dataset | Synthetic samples of the nature run |

### Recommended replacements for real analyses

| Need | Suggested open source | Licence |
|---|---|---|
| Population | WorldPop (worldpop.org) or the Global Human Settlement Layer (GHSL, JRC) | CC BY 4.0 |
| Elevation | Copernicus DEM GLO-30/GLO-90 (or via the Open-Meteo Elevation API) | Copernicus DEM licence, attribution required |
| Boundaries | Official administrative boundaries or OpenStreetMap | ODbL for OSM |

Resample them to the CSV schemas in `docs/adding_a_city.md`; no code changes are needed.

## Standards referenced

* **US EPA Air Quality Index for PM2.5**, breakpoints revised 7 February 2024
  (Good 0-9.0, Moderate 9.1-35.4, Unhealthy for Sensitive Groups 35.5-55.4,
  Unhealthy 55.5-125.4, Very Unhealthy 125.5-225.4, Hazardous ≥ 225.5 µg/m³). The AQI
  is defined for 24-hour averages; AirScope shows hourly categories for orientation.
* **WHO global air quality guidelines (2021)**: PM2.5 15 µg/m³ (24-hour mean) and
  5 µg/m³ (annual mean).

## Open-source software

| Component | Licence |
|---|---|
| Flask, Werkzeug | BSD-3-Clause |
| Flask-CORS | MIT |
| NumPy, SciPy, pandas, scikit-learn, joblib | BSD-3-Clause |
| XGBoost (optional) | Apache-2.0 |
| requests | Apache-2.0 |
| python-dotenv | BSD-3-Clause |
| pytest | MIT |
| React, React DOM | MIT |
| Leaflet | BSD-2-Clause |
| React Leaflet | Hippocratic License 2.1 (check suitability for your use) |
| Recharts, Framer Motion, Lucide React, Axios, TanStack Query, Tailwind CSS, Vite | MIT (Lucide: ISC) |

React Leaflet v4 is distributed under the Hippocratic License, which adds ethical
use conditions to a permissive licence; confirm it suits your organisation before
redistribution.
