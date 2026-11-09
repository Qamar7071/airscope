"""US EPA Air Quality Index for PM2.5 (breakpoints revised 7 February 2024).

The AQI is formally defined for 24-hour average concentrations. AirScope also
applies it to hourly estimates for orientation only and says so in the UI.
"""
from __future__ import annotations

import math

# (C_low, C_high, I_low, I_high, category, colour)
PM25_BREAKPOINTS = [
    (0.0, 9.0, 0, 50, "Good", "#00e400"),
    (9.1, 35.4, 51, 100, "Moderate", "#ffff00"),
    (35.5, 55.4, 101, 150, "Unhealthy for Sensitive Groups", "#ff7e00"),
    (55.5, 125.4, 151, 200, "Unhealthy", "#ff0000"),
    (125.5, 225.4, 201, 300, "Very Unhealthy", "#8f3f97"),
    (225.5, 325.4, 301, 500, "Hazardous", "#7e0023"),
]
WHO_24H_GUIDELINE = 15.0  # µg/m³, WHO 2021 global air quality guideline (24-hour)
WHO_ANNUAL_GUIDELINE = 5.0  # µg/m³, WHO 2021 (annual)


def pm25_to_aqi(concentration: float | None) -> int | None:
    if concentration is None or not math.isfinite(concentration) or concentration < 0:
        return None
    c = math.floor(concentration * 10) / 10.0  # EPA truncation to 0.1 µg/m³
    for c_lo, c_hi, i_lo, i_hi, _cat, _col in PM25_BREAKPOINTS:
        if c <= c_hi:  # truncation guarantees c >= c_lo for the first matching band
            return int(round((i_hi - i_lo) / (c_hi - c_lo) * (c - c_lo) + i_lo))
    # above the top breakpoint: extrapolate the hazardous segment, capped for display
    c_lo, c_hi, i_lo, i_hi = PM25_BREAKPOINTS[-1][:4]
    return int(min(999, round((i_hi - i_lo) / (c_hi - c_lo) * (c - c_lo) + i_lo)))


def pm25_category(concentration: float | None) -> str | None:
    if concentration is None or not math.isfinite(concentration) or concentration < 0:
        return None
    c = math.floor(concentration * 10) / 10.0
    for _c_lo, c_hi, _i_lo, _i_hi, cat, _col in PM25_BREAKPOINTS:
        if c <= c_hi:
            return cat
    return "Hazardous"
