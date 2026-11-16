"""Shared request + snowfall maths for the Open-Meteo-backed providers (GFS, ECMWF, GEM, ICON, JMA, BOM).

One snowfall model for every resort, calibrated against resort-reported season totals
(tools/calibrate/, see providers/MODELS.md):

* Every request carries `elevation` = mid-mountain. Resort coordinates sit at the base lodge, and
  Open-Meteo otherwise downscales to the terrain there, so storms with a snow level between base
  and mid-mountain came back as rain.
* Open-Meteo's `snowfall` is the model's frozen water times a fixed 7 (cm = mm x 0.7). We turn it
  back into water and apply a snow-to-liquid ratio from the hour's mid-mountain temperature
  (Kuchera-style: colder = fluffier) damped by storm intensity (heavy, wet storms pack denser).
* Each provider's snowfall is then multiplied by its bias factor for the resort's region
  (`powder/data/snow_calibration.json`, written by tools/calibrate/factors.py), or the
  provider's global factor where no region was calibrated. Providers without a calibration
  (ICON, JMA, BOM) use 1.
"""

import json
from collections import defaultdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

from ..cache import get_session
from ..conditions import FT_PER_M, mid_mountain_ft
from ..forecast import DailyForecast
from ..resorts import SkiResort

OPEN_METEO_SLR = 7.0  # Open-Meteo snowfall (cm) = snow water (mm) * 0.7
SNOW_HOURLY_FIELDS = "snowfall,temperature_2m"
CALIBRATION_FILE = Path(__file__).resolve().parents[1] / "data" / "snow_calibration.json"

# Snow ratio = clamp(SCALE * kuchera(T) * rate ** RATE_EXP, MIN_SLR, MAX_SLR), fitted by
# tools/calibrate/optimize.py (kuchera form) on ECMWF against reported season totals.
PIVOT_C = -2.0  # about 28 °F: Kuchera's 12:1
COLD_SLOPE = 0.92  # ratio per °C colder than the pivot
WARM_SLOPE = 2.0  # ratio lost per °C warmer
SCALE = 0.84
RATE_EXP = -0.31  # ratio x rate^-0.31: 1 mm/h of water -> x1, 3 mm/h -> x0.71
RATE_WINDOW_H = 6  # storm rate = water averaged over the surrounding 6 hours
MIN_RATE = 0.05  # mm/h
MIN_SLR = 5.0
MAX_SLR = 25.0


def mid_mountain_m(resort: SkiResort) -> int:
    return round(mid_mountain_ft(resort.elevation_base_ft, resort.elevation_peak_ft) / FT_PER_M)


def snow_ratio(temp_c: Optional[float], rate_mm_h: float = 1.0) -> float:
    """Snow-to-liquid ratio for snow falling at `temp_c` with `rate_mm_h` of water per hour."""
    if temp_c is None:
        temp_c = -5.0
    if temp_c < PIVOT_C:
        kuchera = 12 + COLD_SLOPE * (PIVOT_C - temp_c)
    else:
        kuchera = 12 + WARM_SLOPE * (PIVOT_C - temp_c)
    ratio = SCALE * kuchera * max(rate_mm_h, MIN_RATE) ** RATE_EXP
    return min(max(ratio, MIN_SLR), MAX_SLR)


def storm_rates(water_mm: list[float]) -> list[float]:
    """Water per hour averaged over a centred RATE_WINDOW_H window (edges padded with zero)."""
    n, half = len(water_mm), RATE_WINDOW_H // 2
    prefix = [0.0]
    for w in water_mm:
        prefix.append(prefix[-1] + w)
    # matches numpy.convolve(water, ones(6) / 6, mode="same"): hours i-3 .. i+2
    return [(prefix[min(i + RATE_WINDOW_H - half, n)] - prefix[max(i - half, 0)]) / RATE_WINDOW_H
            for i in range(n)]


@lru_cache(maxsize=1)
def _calibration() -> dict:
    try:
        return json.loads(CALIBRATION_FILE.read_text())
    except (OSError, ValueError):
        return {}


def resort_factor(source: str, resort: Optional[SkiResort]) -> float:
    """The resort's own correction (from its reported history) for calibrated providers."""
    cal = _calibration()
    if resort is None or not isinstance(cal.get(source), dict):
        return 1.0
    return float((cal.get("resorts") or {}).get(resort.name, 1.0))


def calibration_factor(source: str, resort: Optional[SkiResort]) -> float:
    entry = _calibration().get(source)
    if not isinstance(entry, dict):
        return 1.0
    regions = entry.get("regions", {})
    if resort is not None:
        # most specific first: "US-UT" (calibrated on reports), then "FR" (tied to ECMWF)
        for key in (f"{resort.country}-{resort.state}" if resort.state else None, resort.country):
            if key and key in regions:
                return float(regions[key])
    return float(entry.get("default", 1.0))


def request_params(resort: SkiResort, days: int, hourly: str = SNOW_HOURLY_FIELDS,
                   model: Optional[str] = None) -> dict:
    params = {
        "latitude": resort.latitude,
        "longitude": resort.longitude,
        "elevation": mid_mountain_m(resort),
        "daily": "snowfall_sum",
        "hourly": hourly,
        "timezone": getattr(resort, "timezone", None) or "UTC",
        "forecast_days": days,
    }
    if model:
        params["models"] = model
    return params


def fetch(url: str, params: dict, name: str) -> Optional[dict]:
    try:
        response = get_session().get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[{name}] Error fetching forecast: {e}")
        return None


def daily_snowfall(data: Optional[dict], source: str, resort: Optional[SkiResort] = None,
                   use_resort_factor: bool = True) -> list[DailyForecast]:
    """Daily snowfall in inches: hourly water x snow ratio, times the provider's calibration
    (region or default) and the resort's own correction where it has reported history.

    Falls back to the daily `snowfall_sum` (Open-Meteo's own 7:1) when hourly data is missing.
    """
    if not data:
        return []
    factor = calibration_factor(source, resort)
    if use_resort_factor:
        factor *= resort_factor(source, resort)
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    snow_cm = hourly.get("snowfall") or []
    temps = hourly.get("temperature_2m") or []

    if times and snow_cm:
        water = [((snow_cm[i] if i < len(snow_cm) else None) or 0.0) * 10 / OPEN_METEO_SLR
                 for i in range(len(times))]
        rates = storm_rates(water)
        totals: dict = defaultdict(float)
        for i, t in enumerate(times):
            day = datetime.strptime(t[:10], "%Y-%m-%d").date()
            totals[day] += 0.0
            if water[i] > 0:
                temp = temps[i] if i < len(temps) else None
                totals[day] += water[i] / 25.4 * snow_ratio(temp, rates[i])
        return [
            DailyForecast(date=day, snowfall_inches=round(totals[day] * factor, 1), source=source)
            for day in sorted(totals)
        ]

    daily = data.get("daily") or {}
    return [
        DailyForecast(
            date=datetime.strptime(d, "%Y-%m-%d").date(),
            snowfall_inches=round((cm or 0) * 0.393701 * factor, 1),
            source=source,
        )
        for d, cm in zip(daily.get("time") or [], daily.get("snowfall_sum") or [])
    ]
