"""Data sources, licences and attribution shown in the API and the UI.

Keep this in sync with docs/data_sources_and_licensing.md. Licence terms of
third-party services can change: verify them before any production or
commercial use.
"""

DATA_SOURCES = [
    {
        "id": "openaq",
        "name": "OpenAQ API v3",
        "url": "https://openaq.org",
        "used_for": "Live mode: monitoring station locations and hourly PM2.5 measurements.",
        "access": "Free API key required (X-API-Key header). AirScope runs offline without it.",
        "license": "OpenAQ aggregates data from many providers; each location carries its own licence, "
                   "which AirScope shows next to live data.",
        "attribution": "Data from OpenAQ (openaq.org) and the original data providers listed per station.",
        "used_in_demo": False,
    },
    {
        "id": "open-meteo",
        "name": "Open-Meteo",
        "url": "https://open-meteo.com",
        "used_for": "Live mode: hourly temperature, humidity, wind, surface pressure and boundary-layer height.",
        "access": "No API key. The free API is for non-commercial use; commercial use needs a subscription.",
        "license": "Data licensed under CC BY 4.0.",
        "attribution": "Weather data by Open-Meteo.com (CC BY 4.0).",
        "used_in_demo": False,
    },
    {
        "id": "carto",
        "name": "CARTO Dark Matter basemap",
        "url": "https://carto.com/basemaps",
        "used_for": "Background map tiles in the web interface.",
        "access": "No key. Free for non-commercial use within CARTO's limits; larger or commercial use needs a CARTO licence.",
        "license": "Map tiles © CARTO; map data © OpenStreetMap contributors (ODbL).",
        "attribution": "© OpenStreetMap contributors © CARTO",
        "used_in_demo": True,
    },
    {
        "id": "airscope-synthetic",
        "name": "AirScope synthetic demo data (OSSE nature run)",
        "url": None,
        "used_for": "Offline demo: simulated station readings and weather, and the synthetic truth used to score the OSSE.",
        "access": "Bundled; generated deterministically by `python -m data.demo_generator`.",
        "license": "Created for AirScope and released with the project.",
        "attribution": "Synthetic - not observations from any real monitor.",
        "used_in_demo": True,
    },
    {
        "id": "airscope-surfaces",
        "name": "Approximate population density and elevation surfaces",
        "url": None,
        "used_for": "Spatial features and exposure weighting.",
        "access": "Bundled CSV files (datasets/population_density.csv, datasets/elevation.csv).",
        "license": "Created for AirScope and released with the project.",
        "attribution": "Documented approximations built from locality-level density estimates and a simple terrain model; "
                       "replace with WorldPop / GHSL (population, CC BY 4.0) and Copernicus DEM (elevation) for real analyses.",
        "used_in_demo": True,
    },
    {
        "id": "airscope-boundaries",
        "name": "City analysis domains and locality names",
        "url": None,
        "used_for": "Analysis grid extent and human-readable location labels.",
        "access": "Bundled (datasets/city_boundaries.json, datasets/localities.json).",
        "license": "Created for AirScope and released with the project.",
        "attribution": "Hand-digitised approximations - not administrative boundaries.",
        "used_in_demo": True,
    },
]

STANDARDS = [
    {
        "id": "us-epa-aqi-2024",
        "name": "US EPA Air Quality Index for PM2.5 (breakpoints revised February 2024)",
        "note": "Defined for 24-hour averages; AirScope applies it to hourly estimates for orientation only.",
    },
    {
        "id": "who-2021",
        "name": "WHO global air quality guidelines (2021)",
        "note": "PM2.5: 15 µg/m³ (24-hour mean), 5 µg/m³ (annual mean).",
    },
]
