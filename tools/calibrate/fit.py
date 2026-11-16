"""Fit one shared correction: log(reported / model water) against generic predictors.

    poetry run python tools/calibrate/fit.py [fraction]

Predictors are things the app knows for any resort from the forecast itself: snow-hour
temperature, snow-hour water intensity, season water. Leave-one-region-out cross-validation
checks the fit generalises instead of memorising regions.
"""

import json
import math
import statistics
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
MODELS = ("ecmwf_ifs",)
from hindcast import OPEN_METEO_SLR, REPORTED, SCORED_SEASONS, cache_path, in_season, region, resorts  # noqa: E402


def features(data: dict) -> tuple[float, float, float]:
    """(water in per season, snow-weighted temp C, mean water mm per snowing hour), models averaged."""
    h = data["hourly"]
    days = [datetime.strptime(t[:10], "%Y-%m-%d").date() for t in h["time"]]
    res = []
    for m in MODELS:
        snow, temp = h[f"snowfall_{m}"], h[f"temperature_2m_{m}"]
        water_mm, wt, hours = 0.0, 0.0, 0
        for i, day in enumerate(days):
            cm = snow[i]
            if not cm or cm < 0.05:
                continue
            season = day.year if day.month >= 7 else day.year - 1
            if season in SCORED_SEASONS and in_season(day, season):
                w = cm * 10 / OPEN_METEO_SLR
                water_mm += w
                wt += w * (temp[i] if temp[i] is not None else -5)
                hours += 1
        if hours:
            res.append((water_mm / 25.4 / len(SCORED_SEASONS), wt / water_mm, water_mm / hours))
    return tuple(statistics.mean(x[k] for x in res) for k in range(3))


def table(fraction: float):
    rows = []
    for r in resorts():
        p = cache_path(r, fraction)
        if not p.exists():
            continue
        water, temp, rate = features(json.loads(p.read_text()))
        rep = statistics.mean(REPORTED[r.name][str(s)][0] for s in SCORED_SEASONS)
        rows.append(dict(region=region(r), name=r.name, water=water, temp=temp, rate=rate,
                         ratio=rep / water, rep=rep))
    return rows


def design(rows, keys):
    cols = [np.ones(len(rows))]
    for k in keys:
        v = np.array([x[k] for x in rows])
        cols.append(np.log(v) if k in ("water", "rate") else v)
    return np.column_stack(cols)


def evaluate(rows, keys):
    y = np.log([x["ratio"] for x in rows])
    X = design(rows, keys)
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    errs = np.exp(X @ coef - y) - 1  # predicted/reported - 1
    cv = []
    for reg in sorted({x["region"] for x in rows}):
        tr = [i for i, x in enumerate(rows) if x["region"] != reg]
        te = [i for i, x in enumerate(rows) if x["region"] == reg]
        c, *_ = np.linalg.lstsq(X[tr], y[tr], rcond=None)
        cv += list(np.exp(X[te] @ c - y[te]) - 1)
    return coef, errs, np.array(cv)


def main(fraction: float):
    rows = table(fraction)
    for x in sorted(rows, key=lambda x: x["rate"]):
        print(f"{x['region']:10s} {x['name']:26s} water {x['water']:5.1f}in/season  temp {x['temp'] * 9 / 5 + 32:5.1f}F"
              f"  rate {x['rate']:4.2f}mm/h  implied ratio {x['ratio']:5.1f}")
    for keys in ([], ["temp"], ["rate"], ["water"], ["temp", "rate"], ["temp", "water"], ["temp", "rate", "water"]):
        coef, errs, cv = evaluate(rows, keys)
        print(f"\n{keys or ['constant']}: coef {np.round(coef, 3)}")
        print(f"   in-sample  median|err| {np.median(abs(errs)):.0%}  within20 {np.mean(abs(errs) <= .2):.0%}")
        print(f"   leave-region-out  median|err| {np.median(abs(cv)):.0%}  within20 {np.mean(abs(cv) <= .2):.0%}")
        for reg in sorted({x['region'] for x in rows}):
            e = [errs[i] for i, x in enumerate(rows) if x["region"] == reg]
            print(f"     {reg:10s} bias {statistics.median(e):+.0%}  |err| {statistics.median(map(abs, e)):.0%}")


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 0.5)
