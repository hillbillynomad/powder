"""Fit one hourly snow-to-liquid ratio for every resort, against reported season totals.

    poetry run python tools/calibrate/optimize.py [--form=kuchera|exp] model [model ...]

Forms (T = mid-mountain 2 m temperature °C that hour, R = model snow water averaged over the
surrounding 6 hours, mm/h):

    kuchera: ratio = clamp(m * (12 + s_cold*(-2.0 - T) if T < -2 else 12 + 2*(-2.0 - T)) * R**c, LO, HI)
    exp:     ratio = clamp(exp(a + b*T + c*ln R), LO, HI)

Snowfall = sum over hours of water x ratio, averaged over the models. Parameters minimise the
mean |log(model / reported)| over resorts, using only seasons whose reports look complete.
Leave-one-region-out cross-validation checks that it generalises.
"""

import math
import statistics
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hindcast import OPEN_METEO_SLR, REPORTED, SEASONS, cache_path, in_season, merged, region, resorts  # noqa: E402
from reported import complete  # noqa: E402

LO, HI = 5.0, 25.0
WINDOW = 6
FORM = "exp"


def arrays(data: dict, models, seasons) -> list:
    """Per model: (water mm, temp C, 6 h rate mm/h, season index) for in-season snowing hours."""
    h = data["hourly"]
    days = [datetime.strptime(t[:10], "%Y-%m-%d").date() for t in h["time"]]
    season = np.array([d.year if d.month >= 7 else d.year - 1 for d in days])
    keep = np.array([in_season(d, s) for d, s in zip(days, season)]) & np.isin(season, seasons)
    out = []
    for m in models:
        snow = np.array([x if x is not None else 0.0 for x in h.get(f"snowfall_{m}", [])], dtype=float)
        if snow.size == 0 or not snow.any():
            continue
        temp = np.array([x if x is not None else -5.0 for x in h[f"temperature_2m_{m}"]], dtype=float)
        water = snow * 10 / OPEN_METEO_SLR
        rate = np.convolve(water, np.ones(WINDOW) / WINDOW, mode="same")
        sel = keep & (water > 0)
        out.append((water[sel], temp[sel], np.maximum(rate[sel], 0.05), season[sel]))
    return out


def ratio(p, t, r):
    if FORM == "kuchera":
        m, s_cold, c = p
        base = np.where(t < -2.0, 12 + s_cold * (-2.0 - t), 12 + 2 * (-2.0 - t))
        return np.clip(m * base * r ** c, LO, HI)
    a, b, c = p
    return np.clip(np.exp(a + b * t + c * np.log(r)), LO, HI)


def load(models):
    data = []
    for res in resorts():
        if not cache_path(res, 0.5).exists():
            continue
        rep = REPORTED[res.name]
        seasons = [s for s in SEASONS if complete(rep, str(s))]
        arr = arrays(merged(res, 0.5), models, seasons)
        if not arr or not seasons:
            continue
        data.append((region(res), res.name, arr, sum(rep[str(s)][0] for s in seasons)))
    return data


TERRAIN = {}  # resort name -> (mid-mountain ft - mean DEM within 30 km) / 1000, when --terrain


def errors(p, data):
    out = []
    k = p[-1] if TERRAIN else 0.0
    q = p[:-1] if TERRAIN else p
    for _, name, arrs, rep in data:
        model_in = statistics.mean(float((w * ratio(q, t, r)).sum()) for w, t, r, _ in arrs) / 25.4
        model_in *= math.exp(k * TERRAIN.get(name, 0.0))
        out.append(math.log(model_in / rep))
    return np.array(out)


def fit(data, start):
    """Nelder-Mead on mean |log error| (numpy only)."""
    f = lambda p: float(np.mean(np.abs(errors(p, data))))  # noqa: E731
    pts = [np.array(start, float)]
    for i in range(len(start)):
        q = np.array(start, float)
        q[i] += 0.1 * (abs(q[i]) or 1)
        pts.append(q)
    vals = [f(p) for p in pts]
    for _ in range(250):
        order = np.argsort(vals)
        pts, vals = [pts[i] for i in order], [vals[i] for i in order]
        centroid = np.mean(pts[:-1], axis=0)
        xr = centroid + (centroid - pts[-1])
        fr = f(xr)
        if fr < vals[0]:
            xe = centroid + 2 * (centroid - pts[-1])
            fe = f(xe)
            pts[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = xr, fr
        else:
            xc = centroid + 0.5 * (pts[-1] - centroid)
            fc = f(xc)
            if fc < vals[-1]:
                pts[-1], vals[-1] = xc, fc
            else:
                pts = [pts[0] + 0.5 * (p - pts[0]) for p in pts]
                vals = [f(p) for p in pts]
    best = int(np.argmin(vals))
    return pts[best], vals[best]


def report(label, data, errs, verbose=False):
    pct = np.exp(errs) - 1
    print(f"\n{label}: median |err| {np.median(abs(pct)):.0%}, within 20%: {np.mean(abs(pct) <= 0.2):.0%}")
    for reg in sorted({x[0] for x in data}):
        e = [pct[i] for i, x in enumerate(data) if x[0] == reg]
        print(f"   {reg:10s} n={len(e):2d} median bias {statistics.median(e):+.0%}  median |err| "
              f"{statistics.median(map(abs, e)):.0%}  within 20% {np.mean(np.abs(e) <= .2):.0%}")
    if verbose:
        for i, x in sorted(enumerate(data), key=lambda ix: (ix[1][0], pct[ix[0]])):
            print(f"      {x[0]:10s} {x[1]:26s} {pct[i]:+.0%}")


def main(models, start):
    data = load(models)
    if TERRAIN:
        start = tuple(start) + (0.0,)
    p, obj = fit(data, start)
    print(f"{FORM} {models}: params {np.round(p, 4)}  (mean |log err| {obj:.3f})")
    q = p[:-1] if TERRAIN else p
    for t in (-12, -8, -4, -1):
        print(f"   ratio at {t * 9 / 5 + 32:.0f}F: " + "  ".join(
            f"{r} mm/h -> {float(ratio(q, np.array([t]), np.array([r]))[0]):.1f}" for r in (0.3, 1.0, 3.0)))
    report("in-sample", data, errors(p, data), verbose=True)
    cv = np.zeros(len(data))
    for reg in sorted({x[0] for x in data}):
        idx = [i for i, x in enumerate(data) if x[0] == reg]
        pr, _ = fit([x for x in data if x[0] != reg], tuple(p))
        cv[idx] = errors(pr, [data[i] for i in idx])
    report("leave-one-region-out", data, cv)
    return p


if __name__ == "__main__":
    args = sys.argv[1:]
    for a in [a for a in args if a.startswith("--form=")]:
        FORM = a.split("=", 1)[1]
        args.remove(a)
    if "--terrain" in args:
        args.remove("--terrain")
        import json as _json
        import hindcast as _h
        terr = _json.loads((_h.CACHE / "terrain.json").read_text())
        for res in resorts():
            if res.name in terr:
                mid = _h.elevation_m(res, 0.5) * 3.28084
                TERRAIN[res.name] = (mid - terr[res.name]["r30"]["mean"]) / 1000
    main(tuple(args) or ("ecmwf_ifs",), (1.0, 1.0, 0.0) if FORM == "kuchera" else (2.5, -0.05, -0.2))
