"""The app's snowfall code run over the raw per-model archive (raw.py), for the calibration fits.

Every fit (factors.py, anchor.py, resort_factors.py, verify.py) goes through
`open_meteo_common.daily_snowfall`, the exact function the providers call, on the same fields
the providers request (precipitation, temperature, humidity at mid-mountain). So what is fitted
is what ships.

PROVIDERS maps the underlying model the app pins to the provider name the calibration table
uses. Raw files cover Nov 1 - Apr 30 of each season in `raw.SEASONS`.
"""

import json
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import raw  # noqa: E402

from powder.providers import open_meteo_common as omc  # noqa: E402

PROVIDERS = {"gfs_global": "Open-Meteo", "ecmwf_ifs": "ECMWF", "gem_global": "GEM"}
MIN_COVER = 0.9  # share of hours with precipitation and temperature for a season to count


def single(data: dict, model: str) -> dict | None:
    """One model's hourly block from a multi-model response, as a provider would receive it."""
    h = data.get("hourly") or {}
    precip = h.get(f"precipitation_{model}") or h.get("precipitation")
    temps = h.get(f"temperature_2m_{model}") or h.get("temperature_2m")
    if not precip or not temps:
        return None
    ok = sum(p is not None and t is not None for p, t in zip(precip, temps))
    if ok < MIN_COVER * len(h["time"]):
        return None
    return {"elevation": data.get("elevation"),
            "hourly": {"time": h["time"], "precipitation": precip, "temperature_2m": temps,
                       "relative_humidity_2m": h.get(f"relative_humidity_2m_{model}")
                       or h.get("relative_humidity_2m") or []}}


@lru_cache(maxsize=None)
def _raw(key: str, season: int) -> dict | None:
    p = raw.path(key, season)
    return json.loads(p.read_text()) if p.exists() else None


def season_totals(key: str, resort, model: str, source: str = "_raw",
                  use_resort_factor: bool = False) -> dict[int, float]:
    """{season: inches} for one model at one raw point. source "_raw" = no calibration; a
    provider name applies that provider's shipped region / default factor."""
    out = {}
    for season in raw.SEASONS:
        data = _raw(key, season)
        block = single(data, model) if data else None
        if block is None:
            continue
        days = omc.daily_snowfall(block, source, resort, use_resort_factor=use_resort_factor)
        out[season] = sum(d.snowfall_inches for d in days)
    return out
