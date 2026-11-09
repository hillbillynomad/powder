"""Daily mountain conditions and a snow-quality rating, from Open-Meteo hourly data.

Open-Meteo reports temperature at its model point (the response's `elevation`), which is often
near the base. We shift it to mid-mountain with a standard lapse rate so the rating describes
the snow skiers actually ride, and use the freezing level to tell snow up top from rain below.
"""

from dataclasses import dataclass
from datetime import date, datetime
from statistics import mean
from typing import Optional

LAPSE_C_PER_M = 0.0065  # standard atmosphere: 6.5 °C per km
FT_PER_M = 3.28084
SNOW_LINE_BELOW_FREEZING_FT = 1000  # snow usually reaches ~300 m below the freezing level

# Snow-quality thresholds (mid-mountain temperature while it snows, °F)
CHAMPAGNE_MAX_F = 15
POWDER_MAX_F = 27
MIN_SNOW_IN = 0.5
MIN_RAIN_IN = 0.1

QUALITIES = ("champagne", "powder", "heavy", "mixed", "rain")


@dataclass
class DayConditions:
    """One local day of conditions, temperatures at mid-mountain."""
    date: date
    temp_min_f: Optional[float] = None
    temp_max_f: Optional[float] = None
    snow_temp_f: Optional[float] = None  # mean temperature during precipitation hours
    freezing_level_min_ft: Optional[float] = None
    freezing_level_max_ft: Optional[float] = None
    precip_freezing_level_ft: Optional[float] = None  # lowest freezing level while it precipitates
    snow_line_ft: Optional[float] = None  # only on days with snow
    rain_in: float = 0.0
    gust_max_mph: Optional[float] = None
    ref_elevation_ft: Optional[float] = None  # elevation the temperatures apply to
    quality: Optional[str] = None


def c_to_f(temp_c: float) -> float:
    return temp_c * 9 / 5 + 32


def lapse_temp_c(temp_c: float, from_m: float, to_m: float) -> float:
    """Temperature moved from one elevation to another with the standard lapse rate."""
    return temp_c - (to_m - from_m) * LAPSE_C_PER_M


def mid_mountain_ft(base_ft: float, peak_ft: Optional[float]) -> float:
    return (base_ft + peak_ft) / 2 if peak_ft else base_ft


def _values(hourly: dict, key: str, n: int) -> list:
    vals = hourly.get(key) or []
    return list(vals) + [None] * (n - len(vals))


def summarize_hourly(
    hourly: dict, model_elev_m: Optional[float], base_ft: float, peak_ft: Optional[float]
) -> dict[date, DayConditions]:
    """Group Open-Meteo hourly data (already in the resort's local time) into days."""
    times = hourly.get("time") or []
    n = len(times)
    temps = _values(hourly, "temperature_2m", n)
    freezing = _values(hourly, "freezing_level_height", n)
    snow = _values(hourly, "snowfall", n)
    rain = _values(hourly, "rain", n)
    gusts = _values(hourly, "wind_gusts_10m", n)

    ref_ft = mid_mountain_ft(base_ft, peak_ft)
    ref_m = ref_ft / FT_PER_M
    from_m = model_elev_m if model_elev_m is not None else base_ft / FT_PER_M

    by_day: dict[date, list[int]] = {}
    for i, t in enumerate(times):
        day = datetime.strptime(t[:10], "%Y-%m-%d").date()
        by_day.setdefault(day, []).append(i)

    result = {}
    for day, idx in by_day.items():
        temps_f = [c_to_f(lapse_temp_c(temps[i], from_m, ref_m)) for i in idx if temps[i] is not None]
        levels_ft = [freezing[i] * FT_PER_M for i in idx if freezing[i] is not None]
        snowing = [i for i in idx if (snow[i] or 0) > 0]
        precip = [i for i in idx if (snow[i] or 0) > 0 or (rain[i] or 0) > 0]
        precip_temps = [c_to_f(lapse_temp_c(temps[i], from_m, ref_m)) for i in precip if temps[i] is not None]
        precip_levels = [freezing[i] * FT_PER_M for i in precip if freezing[i] is not None]
        snow_levels = [freezing[i] * FT_PER_M for i in snowing if freezing[i] is not None]
        day_gusts = [gusts[i] / 1.609344 for i in idx if gusts[i] is not None]

        result[day] = DayConditions(
            date=day,
            temp_min_f=min(temps_f) if temps_f else None,
            temp_max_f=max(temps_f) if temps_f else None,
            snow_temp_f=mean(precip_temps) if precip_temps else None,
            freezing_level_min_ft=min(levels_ft) if levels_ft else None,
            freezing_level_max_ft=max(levels_ft) if levels_ft else None,
            precip_freezing_level_ft=min(precip_levels) if precip_levels else None,
            snow_line_ft=(
                max(min(snow_levels) - SNOW_LINE_BELOW_FREEZING_FT, 0) if snow_levels else None
            ),
            rain_in=sum((rain[i] or 0) for i in idx) / 25.4,
            gust_max_mph=max(day_gusts) if day_gusts else None,
            ref_elevation_ft=ref_ft,
        )
    return result


def rate_snow(
    day: DayConditions, snowfall_in: float, base_ft: float, peak_ft: Optional[float]
) -> Optional[str]:
    """champagne / powder / heavy for snow, mixed for snow up top + rain below, rain, or None."""
    if snowfall_in < MIN_SNOW_IN and day.rain_in < MIN_RAIN_IN:
        return None
    top_ft = peak_ft or base_ft
    level = (
        day.precip_freezing_level_ft
        if day.precip_freezing_level_ft is not None
        else day.freezing_level_min_ft
    )
    # Freezing level above the summit: it rains everywhere. Below it, rain at the model point
    # (often the valley) still means snow up top.
    if level is None and snowfall_in < MIN_SNOW_IN:
        return "rain"
    if level is not None and level > top_ft:
        return "rain"
    if day.rain_in >= MIN_RAIN_IN:
        return "mixed"
    temp = day.snow_temp_f
    if temp is None and day.temp_min_f is not None and day.temp_max_f is not None:
        temp = (day.temp_min_f + day.temp_max_f) / 2
    if temp is None:
        return None
    if temp <= CHAMPAGNE_MAX_F:
        return "champagne"
    if temp <= POWDER_MAX_F:
        return "powder"
    return "heavy"


def conditions_json(day: DayConditions) -> dict:
    """JSON shape exported per day in forecasts.json."""
    def r(v, nd=0):
        return None if v is None else round(v, nd) if nd else round(v)

    return {
        "temp_min_f": r(day.temp_min_f),
        "temp_max_f": r(day.temp_max_f),
        "snow_temp_f": r(day.snow_temp_f),
        "freezing_level_ft": [r(day.freezing_level_min_ft), r(day.freezing_level_max_ft)],
        "snow_line_ft": r(day.snow_line_ft),
        "rain_inches": round(day.rain_in, 2),
        "gust_mph": r(day.gust_max_mph),
        "ref_elevation_ft": r(day.ref_elevation_ft),
        "quality": day.quality,
    }
