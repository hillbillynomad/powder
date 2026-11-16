"""Per resort: model snow water, snow-weighted temperature, and the snow ratio the reports imply.

    poetry run python tools/calibrate/diagnose.py [fraction]
"""

import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hindcast  # noqa: E402
from hindcast import MODELS, OPEN_METEO_SLR, REPORTED, SCORED_SEASONS, cache_path, in_season, region, resorts  # noqa: E402


def stats(data: dict) -> dict:
    """Season water (in) per model, plus snow-weighted mean temperature (°C)."""
    h = data["hourly"]
    days = [datetime.strptime(t[:10], "%Y-%m-%d").date() for t in h["time"]]
    out = {}
    for m in MODELS:
        snow, temp = h.get(f"snowfall_{m}") or [], h.get(f"temperature_2m_{m}") or []
        water, wt = {s: 0.0 for s in SCORED_SEASONS}, []
        for i, day in enumerate(days):
            cm = snow[i] if i < len(snow) else None
            if not cm:
                continue
            season = day.year if day.month >= 7 else day.year - 1
            if season in water and in_season(day, season):
                w = cm * 10 / OPEN_METEO_SLR / 25.4
                water[season] += w
                if temp[i] is not None:
                    wt.append((w, temp[i]))
        out[m] = (water, sum(w * t for w, t in wt) / sum(w for w, _ in wt) if wt else None)
    return out


def main(fraction: float):
    rows = []
    for r in resorts():
        p = cache_path(r, fraction)
        if not p.exists():
            continue
        st = stats(json.loads(p.read_text()))
        water = statistics.mean(sum(st[m][0].values()) for m in MODELS)
        temp = statistics.mean(st[m][1] for m in MODELS if st[m][1] is not None)
        rep = sum(REPORTED[r.name][str(s)][0] for s in SCORED_SEASONS)
        mid_ft = hindcast.elevation_m(r, fraction) * 3.28084
        rows.append((region(r), r.name, water, temp, rep / water, mid_ft, r.latitude, r.longitude))
    for reg, name, w, t, need, el, lat, lon in sorted(rows, key=lambda x: x[3]):
        print(f"{reg:10s} {name:26s} water {w:5.1f}in  snow-temp {t * 9 / 5 + 32:5.1f}F  "
              f"implied ratio {need:5.1f}  mid {el:5.0f}ft  lon {lon:7.1f}")
    return rows


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 0.5)
