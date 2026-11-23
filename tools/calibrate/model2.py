"""Prototype snowfall model (research only: the app does not use it yet).

    poetry run python tools/calibrate/model2.py            # ladder of variants, scored
    poetry run python tools/calibrate/model2.py --fit-slr  # also refit the snow-ratio constants
    poetry run python tools/calibrate/model2.py --snotel   # precipitation step against SNOTEL

The chain, from what a model grid cell gives us to what a resort's snow plot collects:

    cell precipitation  x  downscaling (model bias and unresolved terrain height)
                        x  snow fraction (wet-bulb temperature at the plot's elevation)
                        x  snow-to-liquid ratio (temperature and storm rate)
                        =  snowfall at the plot

Each *underlying* model is handled on its own (raw.py): the app's "GFS" is HRRR 3 km for two
days and GFS 13-25 km after, its "GEM" is GEM regional 10 km and then GEM global 15 km, and their
grid cells sit at different heights with different biases.

Scores are against resort-reported season totals (reported_seasons.json), leave-one-resort-out:
every coefficient is refitted without the resort being predicted.
"""

import json
import math
import statistics
import sys
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hindcast  # noqa: E402
import raw  # noqa: E402
from reported import complete  # noqa: E402
import snotel  # noqa: E402

HERE = Path(__file__).resolve().parent
SITES = {k: v for k, v in json.loads((HERE / "report_sites.json").read_text()).items()
         if not k.startswith("_")}
SHORT = ("ncep_hrrr_conus", "ecmwf_ifs", "gem_regional")  # what the app's 3 providers serve, days 1-2
LONG = ("gfs_global", "ecmwf_ifs", "gem_global")          # days 3-10
LAPSE_C_KM = 6.5
DEFAULT_FRACTION = 0.63   # median position of the known reporting plots between base and summit
APP_SLR = (0.84, 0.92, -0.31)  # scale, cold slope, rate exponent (open_meteo_common)
FT = 3.28084


# ---------------------------------------------------------------- physics

def wet_bulb(t_c, rh, z_m):
    """Wet-bulb temperature (C) from the psychrometric equation at the pressure of height z."""
    p = 1013.25 * (1 - 2.25577e-5 * z_m) ** 5.25588
    es = lambda t: 6.112 * np.exp(17.62 * t / (243.12 + t))  # noqa: E731
    e = np.clip(rh, 5, 100) / 100 * es(t_c)
    tw = t_c - (100 - np.clip(rh, 5, 100)) / 10  # start a little below the air temperature
    for _ in range(12):
        f = es(tw) - 6.6e-4 * p * (t_c - tw) - e
        df = es(tw) * 17.62 * 243.12 / (243.12 + tw) ** 2 + 6.6e-4 * p
        tw = tw - f / df
    return np.minimum(tw, t_c)


def snow_fraction(tw_c):
    """Share of precipitation falling as snow: Wang et al. 2019 wet-bulb sigmoid (50% at +0.8 C)."""
    return 1 / (1 + 6.99e-5 * np.exp(2.0 * (tw_c + 3.97)))


def snow_ratio(t_c, rate_mm_h, params=APP_SLR):
    """The app's ratio form: Kuchera on temperature, damped by the 6 h storm rate, 5-25:1."""
    scale, cold, rate_exp = params
    k = np.where(t_c < -2, 12 + cold * (-2 - t_c), 12 - 2 * (t_c + 2))
    return np.clip(scale * k * np.maximum(rate_mm_h, 0.05) ** rate_exp, 5, 25)


def rolling_mean(x, window=6):
    return np.convolve(x, np.ones(window) / window, mode="same")


# ---------------------------------------------------------------- data

HRRR, HRRR_ARCHIVE = "ncep_hrrr_conus", "hrrr_archive"


@lru_cache(maxsize=None)
def series(key: str):
    """{model: (season idx, precipitation mm, temperature C, humidity %)} plus the response height.

    HRRR comes from its day-ahead forecasts (raw.py hrrr), the lead the live app serves; the
    archive's HRRR (first forecast hours, precipitation not spun up) is kept as "hrrr_archive"
    only to show what calibrating on it does.
    """
    out, z = {}, None
    parts = {m: [] for m in raw.MODELS + (HRRR_ARCHIVE,)}
    for si, season in enumerate(raw.SEASONS):
        p = raw.path(key, season)
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        z = d["elevation"]
        h = d["hourly"]
        n = len(h["time"])
        day1 = raw.hrrr_path(key, season)
        h1 = json.loads(day1.read_text())["hourly"] if day1.exists() else {}
        for m in parts:
            src = HRRR if m == HRRR_ARCHIVE else m
            if m == HRRR:
                arr = lambda f: np.array((h1.get(f"{f}_previous_day1") or [None] * n)[:n], dtype=float)  # noqa: E731
            else:
                arr = lambda f: np.array(h.get(f"{f}_{src}") or [None] * n, dtype=float)  # noqa: E731
            parts[m].append((np.full(n, si), arr("precipitation"), arr("temperature_2m"),
                             arr("relative_humidity_2m")))
    for m, chunks in parts.items():
        if chunks:
            out[m] = tuple(np.concatenate(c) for c in zip(*chunks))
    return out, z


@lru_cache(maxsize=None)
def cells() -> dict:
    p = raw.RAW / "cells.json"
    return json.loads(p.read_text()) if p.exists() else {}


def target_elevation_m(r, where) -> float:
    """`where`: a base-to-summit fraction, or "plot" (the resort's reporting plot when known)."""
    if where == "plot":
        if r.name in SITES:
            return SITES[r.name]["elev_ft"] / FT
        where = DEFAULT_FRACTION
    return hindcast.elevation_m(r, where)


def season_sums(key: str, model: str, z_target: float, phase: str, slr=APP_SLR):
    """(snowfall inches, snow water inches) per season index for one model at one point."""
    data, z_resp = series(key)
    if model not in data:
        return None
    si, p, t, rh = data[model]
    ok = ~np.isnan(p) & ~np.isnan(t)
    if not ok.any():
        return None
    p = np.where(ok, p, 0.0)
    t = np.where(ok, t, 0.0) - LAPSE_C_KM * (z_target - z_resp) / 1000
    if phase == "wetbulb":
        frac = snow_fraction(wet_bulb(t, np.where(np.isnan(rh), 85.0, rh), z_target))
    else:  # "air": all snow at or below +1 C, as a stand-in for the model's own snowfall field
        frac = (t <= 1.0).astype(float)
    water = p * frac
    snow = water * snow_ratio(t, rolling_mean(water), slr) / 25.4
    n = len(raw.SEASONS)
    return (np.bincount(si, snow, n), np.bincount(si, water, n) / 25.4,
            np.bincount(si, ok.astype(float), n) / np.bincount(si, minlength=n).clip(1))


# ---------------------------------------------------------------- PRISM climatological downscaling

RES_KM = {"ncep_hrrr_conus": 3, "hrrr_archive": 3, "ecmwf_ifs": 9, "gem_regional": 10, "gfs_global": 13, "gem_global": 15}
PRISM_TIF = hindcast.CACHE / "prism" / "prism_ppt_us_30s_202001_avg_30y.tif"


@lru_cache(maxsize=None)
def _prism():
    """January 1991-2020 precipitation normals on PRISM's 800 m grid (contiguous US only)."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    im = Image.open(PRISM_TIF)
    step = im.tag_v2[33550][0]
    tie = im.tag_v2[33922]
    a = np.array(im)
    return np.where(a < 0, np.nan, a), tie[3], tie[4], step


def _prism_box(lat, lon, half_km):
    a, x0, y0, step = _prism()
    dy = half_km / 111.0 / step
    dx = half_km / (111.0 * math.cos(math.radians(lat))) / step
    r, c = (y0 - lat) / step, (lon - x0) / step
    if not (0 <= r < a.shape[0] and 0 <= c < a.shape[1]):
        return None
    box = a[max(0, int(r - dy)):int(r + dy) + 1, max(0, int(c - dx)):int(c + dx) + 1]
    return box[~np.isnan(box)]


def prism_ratio(r, model: str, pct: float = 75, radius_km: float = 3.0):
    """log of (climatological precipitation on the mountain) / (the same averaged over the model's
    grid cell): how much wetter the plot is than the cell the model can resolve. The mountain is
    the `pct` percentile of PRISM within `radius_km` of the resort marker (plots sit upslope of
    the base lodge). None outside PRISM's domain or without cell data."""
    cell = cells().get(r.name, {}).get(HRRR if model == HRRR_ARCHIVE else model)
    if not cell or not PRISM_TIF.exists():
        return None
    mountain = _prism_box(r.latitude, r.longitude, radius_km)
    grid = _prism_box(cell["lat"], cell["lon"], RES_KM[model] / 2)
    if mountain is None or grid is None or not len(mountain) or not len(grid):
        return None
    return math.log(np.percentile(mountain, pct) / grid.mean())


# ---------------------------------------------------------------- fit and score

def region_key(r) -> str:
    return f"{r.country}-{r.state}" if r.state else r.country


def table(models, where, phase, slr=APP_SLR, predictor="height", only=None):
    """Rows per resort: reported and per-model season snowfall on complete seasons, plus the
    downscaling predictor per model in row["gap"]: km of terrain the model's cell sits below the
    plot ("height"), or the PRISM climatological ratio ("prism", US only)."""
    rows = []
    for r in hindcast.resorts():
        if only and r.country != only:
            continue
        rep = hindcast.REPORTED[r.name]
        z = target_elevation_m(r, where)
        row = dict(name=r.name, region=hindcast.region(r), key=region_key(r), models={}, gap={})
        for m in models:
            if m in (HRRR, HRRR_ARCHIVE) and r.country != "US":
                continue  # HRRR's domain ends near the border; its edge values are not usable
            sums = season_sums(r.name, m, z, phase, slr)
            if sums is None:
                continue
            snow, _, cover = sums
            seasons = [i for i, s in enumerate(raw.SEASONS) if complete(rep, str(s)) and cover[i] > 0.9
                       and snow[i] > 0]
            if not seasons:
                continue
            if predictor == "prism":
                x = prism_ratio(r, m)
                if x is None:
                    continue
            else:
                cell = cells().get(r.name, {}).get(HRRR if m == HRRR_ARCHIVE else m)
                x = (z - cell["elev_m"]) / 1000 if cell else 0.0
            row["models"][m] = {raw.SEASONS[i]: snow[i] for i in seasons}
            row["gap"][m] = x
        row["rep"] = {s: rep[str(s)][0] for s in raw.SEASONS if complete(rep, str(s))}
        if row["models"]:
            rows.append(row)
    return rows


def fit(rows, models, gradient: str, regional: bool, exclude=None, weighted=False):
    """Per-model log bias (+ height-gap gradient), optionally per-region offsets.

    gradient: "none" | "shared" (one orographic gradient for all models) | "each".
    """
    use = [r for r in rows if r["name"] != exclude]
    xs, ys, ms = [], [], []
    for r in use:
        for m in models:
            if m in r["models"]:
                seasons = [s for s in r["models"][m] if s in r["rep"]]
                if seasons:
                    ys.append(math.log(sum(r["rep"][s] for s in seasons) / sum(r["models"][m][s] for s in seasons)))
                    xs.append(r["gap"][m])
                    ms.append(m)
    xs, ys = np.array(xs), np.array(ys)
    alpha, grad, weights = {}, {}, {}
    if gradient == "shared":
        # demean within model, one slope
        xd, yd = xs.copy(), ys.copy()
        for m in models:
            sel = np.array([k == m for k in ms])
            if sel.any():
                xd[sel] -= xs[sel].mean()
                yd[sel] -= ys[sel].mean()
        g = float((xd * yd).sum() / max((xd * xd).sum(), 1e-9))
        grad = {m: g for m in models}
    for m in models:
        sel = np.array([k == m for k in ms])
        if not sel.any():
            continue
        if gradient == "each" and sel.sum() > 5 and np.ptp(xs[sel]) > 0.05:
            g, a = np.polyfit(xs[sel], ys[sel], 1)
            grad[m], alpha[m] = float(g), float(a)
        else:
            g = grad.setdefault(m, 0.0)
            alpha[m] = float(np.median(ys[sel] - g * xs[sel]))
        # skill weight: inverse variance of this model's resort-to-resort misses
        weights[m] = 1 / max(float(np.var(ys[sel] - alpha[m] - grad[m] * xs[sel])), 1e-3) if weighted else 1.0
    regions = {}
    if regional:
        res = {}
        for r in use:
            p = predict(r, models, alpha, grad, {}, weights)
            if p:
                res.setdefault(r["key"], []).append(math.log(sum(r["rep"][s] for s in p) / sum(p.values())))
        regions = {k: statistics.median(v) for k, v in res.items() if len(v) >= 2}
    return alpha, grad, regions, weights


def predict(row, models, alpha, grad, regions, weights=None) -> dict:
    """{season: inches}: (weighted) mean of the calibrated models available for the resort."""
    out = {}
    off = regions.get(row["key"], 0.0)
    for s in row["rep"]:
        vals = [(row["models"][m][s] * math.exp(alpha[m] + grad[m] * row["gap"][m] + off), (weights or {}).get(m, 1.0))
                for m in models if m in row["models"] and s in row["models"][m] and m in alpha]
        if vals:
            out[s] = sum(v * w for v, w in vals) / sum(w for _, w in vals)
    return out


def score(rows, models, gradient="none", regional=False, resort_factor=False, weighted=False):
    """Leave-one-resort-out errors per resort-season: [(region, name, season, pred / reported - 1)].

    With resort_factor, each season is also scaled by the resort's own reported / predicted on
    its *other* seasons (leave-one-season-out), as the app's per-resort factors do.
    """
    errs = []
    for row in rows:
        pred = predict(row, models, *fit(rows, models, gradient, regional, exclude=row["name"], weighted=weighted))
        for s, v in pred.items():
            if resort_factor:
                others = [math.log(row["rep"][o] / pred[o]) for o in pred if o != s]
                if not others:
                    continue
                v *= math.exp(statistics.fmean(others))
            errs.append((row["region"], row["name"], s, v / row["rep"][s] - 1, v, row["rep"][s]))
    return errs


def summary(errs, by_region=False) -> str:
    """Median error per resort (seasons pooled, as factors.py scores) and per resort-season."""
    def line(es):
        a = [abs(e[3]) for e in es]
        tot = {}
        for e in es:
            t = tot.setdefault(e[1], [0.0, 0.0])
            t[0] += e[4]
            t[1] += e[5]
        b = [abs(p / r - 1) for p, r in tot.values()]
        return (f"per resort {statistics.median(b):4.0%} (within 20%: {sum(x <= .2 for x in b) / len(b):4.0%}, n={len(b)})"
                f"   per season {statistics.median(a):4.0%} (within 20%: {sum(x <= .2 for x in a) / len(a):4.0%}, n={len(a)})")
    out = line(errs)
    if by_region:
        out += "".join(f"\n      {reg:10s} {line([e for e in errs if e[0] == reg])}"
                       for reg in sorted({e[0] for e in errs}))
    return out


# ---------------------------------------------------------------- SNOTEL: the precipitation step

def daily_water(key: str, model: str) -> dict:
    """{date: inches of snow water} at the point's own elevation (wet-bulb snow fraction)."""
    data, z = series(key)
    if model not in data:
        return {}
    si, p, t, rh = data[model]
    ok = ~np.isnan(p) & ~np.isnan(t)
    frac = snow_fraction(wet_bulb(np.where(ok, t, 0.0), np.where(np.isnan(rh), 85.0, rh), z))
    water = np.where(ok, p, np.nan) * frac / 25.4
    out = {}
    for s in np.unique(si):
        w = water[si == s]
        start = date(raw.SEASONS[int(s)], 11, 1)
        for d in range(len(w) // 24):
            v = w[d * 24:(d + 1) * 24]
            if not np.isnan(v).any():
                out[start + timedelta(days=d)] = float(v.sum())
    return out


def snotel_eval():
    """Model snow water against what the SNOTEL pillows collected: bias, height gap, daily skill."""
    stations = snotel.SITES["stations"]
    rows = {m: [] for m in raw.MODELS}
    for sid, st in stations.items():
        obs = snotel.gains(sid)
        for m in raw.MODELS:
            mod = daily_water(sid, m)
            days = sorted(set(mod) & set(obs))
            if len(days) < 300:
                continue
            o = np.array([obs[d][0] for d in days])
            w = np.array([mod[d] for d in days])
            o3, w3 = np.convolve(o, np.ones(3), "valid"), np.convolve(w, np.ones(3), "valid")
            wet = (o3 > 0.2) | (w3 > 0.2)
            cell = cells().get(sid, {}).get(m)
            rows[m].append(dict(sid=sid, name=st["name"], log=math.log(o.sum() / w.sum()),
                                gap=(st["elev_m"] - cell["elev_m"]) / 1000 if cell else 0.0,
                                corr=float(np.corrcoef(o3[wet], w3[wet])[0, 1]),
                                mae3=float(np.median(np.abs(w3[wet] * o.sum() / w.sum() - o3[wet]) / np.maximum(o3[wet], 0.2)))))
    print("\nSNOTEL snow water vs model snow water at the station (Nov-Apr, 21 stations):")
    print(f"  {'model':17s} {'stations':>8s} {'obs/model':>9s} {'spread':>7s} {'LOO err':>8s} {'+gap err':>8s} {'gradient':>9s} {'3-day r':>8s} {'gap km':>7s}")
    for m, rs in rows.items():
        if len(rs) < 5:
            continue
        y, x = np.array([r["log"] for r in rs]), np.array([r["gap"] for r in rs])
        loo0, loo1 = [], []
        for i in range(len(rs)):
            keep = np.arange(len(rs)) != i
            loo0.append(abs(math.exp(np.median(y[keep]) - y[i]) - 1))
            g, a = np.polyfit(x[keep], y[keep], 1) if np.ptp(x[keep]) > 0.05 else (0.0, np.median(y[keep]))
            loo1.append(abs(math.exp(a + g * x[i] - y[i]) - 1))
        g = np.polyfit(x, y, 1)[0] if np.ptp(x) > 0.05 else 0.0
        print(f"  {m:17s} {len(rs):8d} {math.exp(np.median(y)):9.2f} {np.std(y):7.2f} {np.median(loo0):8.0%} "
              f"{np.median(loo1):8.0%} {math.exp(g) - 1:+9.0%} {np.median([r['corr'] for r in rs]):8.2f} {np.median(x):+7.2f}")
    return rows



def slr_check(model="ecmwf_ifs"):
    """Observed snow ratio at SNOTEL (daily depth gain / snow-water gain) by temperature, next to
    the app's ratio for the same hours. Depth sensors read settled 24 h snow, so observed ratios
    run below a cleared snow board; the shape against temperature is what to compare."""
    obs_r, app_r, temps = [], [], []
    for sid in snotel.SITES["stations"]:
        data, z = series(sid)
        if model not in data:
            continue
        si, p, t, rh = data[model]
        ok = ~np.isnan(p) & ~np.isnan(t)
        water = np.where(ok, p, 0.0) * snow_fraction(wet_bulb(np.where(ok, t, 0.0), np.where(np.isnan(rh), 85.0, rh), z))
        snow = water * snow_ratio(np.where(ok, t, 0.0), rolling_mean(water))
        g = snotel.gains(sid)
        for s_ in np.unique(si):
            sel = si == s_
            w, sn, tt = water[sel], snow[sel], np.where(ok, t, 0.0)[sel]
            start = date(raw.SEASONS[int(s_)], 11, 1)
            for d in range(len(w) // 24):
                day = start + timedelta(days=d)
                sl = slice(d * 24, (d + 1) * 24)
                if day in g and g[day][0] >= 0.3 and g[day][1] >= 2 and w[sl].sum() > 2.5:
                    obs_r.append(g[day][1] / g[day][0])
                    app_r.append(sn[sl].sum() / w[sl].sum())
                    temps.append((w[sl] * tt[sl]).sum() / w[sl].sum())
    obs_r, app_r, temps = map(np.array, (obs_r, app_r, temps))
    print(f"\nSnow ratio by temperature while snowing ({len(temps)} station-days with >= 0.3 in of water):")
    print(f"  {'temp C':>10s} {'days':>5s} {'SNOTEL median':>14s} {'app ratio':>10s}")
    for lo, hi in ((-30, -14), (-14, -10), (-10, -7), (-7, -4), (-4, -2), (-2, 0), (0, 3)):
        sel = (temps >= lo) & (temps < hi)
        if sel.sum() >= 8:
            print(f"  {lo:4d}..{hi:<4d} {sel.sum():5d} {np.median(obs_r[sel]):14.1f} {np.median(app_r[sel]):10.1f}")


def restrict(rows, seasons):
    """Rows keeping only the given seasons."""
    out = []
    for r in rows:
        models = {m: {s: v for s, v in d.items() if s in seasons} for m, d in r["models"].items()}
        models = {m: d for m, d in models.items() if d}
        rep = {s: v for s, v in r["rep"].items() if s in seasons}
        if models and rep:
            out.append(dict(r, models=models, rep=rep))
    return out


def overfit_checks(models=LONG):
    """Three ways the scores could flatter the model, each tested."""
    rows = table(models, 0.5, "air")

    print("\n1. Out of time: everything fitted on 2022-23 and 2023-24, scored on 2024-25 and 2025-26")
    train, test = restrict(rows, (2022, 2023)), restrict(rows, (2024, 2025))
    alpha, grad, regions, _ = fit(train, models, "none", True)
    by_train = {r["name"]: r for r in train}
    for label, shrink in (("region factors only", None), ("+ resort factor", 0.0), ("+ resort factor, shrunk (k=1)", 1.0)):
        errs = []
        for r in test:
            pred = predict(r, models, alpha, grad, regions)
            f = 0.0
            if shrink is not None and r["name"] in by_train:
                tr = by_train[r["name"]]
                p_tr = predict(tr, models, alpha, grad, regions)
                logs = [math.log(tr["rep"][s] / p_tr[s]) for s in p_tr]
                if logs:
                    f = statistics.fmean(logs) * len(logs) / (len(logs) + shrink)
            errs += [(r["region"], r["name"], s, v * math.exp(f) / r["rep"][s] - 1, v * math.exp(f), r["rep"][s])
                     for s, v in pred.items()]
        print(f"   {label:32s} {summary(errs)}")

    print("\n2. Resort factor from few seasons: shrink it toward 1 by n / (n + k)? (leave-one-season-out)")
    for k in (0.0, 0.5, 1.0, 2.0):
        errs = []
        for row in rows:
            pred = predict(row, models, *fit(rows, models, "none", True, exclude=row["name"]))
            for s, v in pred.items():
                others = [math.log(row["rep"][o] / pred[o]) for o in pred if o != s]
                if others:
                    v *= math.exp(statistics.fmean(others) * len(others) / (len(others) + k))
                    errs.append((row["region"], row["name"], s, v / row["rep"][s] - 1, v, row["rep"][s]))
        print(f"   k={k:3.1f}  {summary(errs)}")

    print("\n3. Is the resort factor steady, or noise? Factor from 2022-23 + 2023-24 vs from 2024-25 + 2025-26")
    a, b = [], []
    by_test = {r["name"]: r for r in test}
    for name, tr in by_train.items():
        if name not in by_test:
            continue
        halves = []
        for part in (tr, by_test[name]):
            pr = predict(part, models, alpha, grad, regions)
            halves.append(statistics.fmean(math.log(part["rep"][s] / pr[s]) for s in pr))
        a.append(halves[0])
        b.append(halves[1])
    print(f"   correlation between the two halves: r = {np.corrcoef(a, b)[0, 1]:.2f} over {len(a)} resorts"
          f"   (spread of the factor: {np.std(a):.2f} in log units; change between halves: {np.std(np.array(b) - np.array(a)):.2f})")


def altitude_sweep(models=LONG):
    """Where on the mountain should the model be evaluated to match what resorts report?"""
    print("\nAltitude the model is evaluated at (wet-bulb phase), leave-one-resort-out:")
    for where in (0.0, 0.25, 0.5, 0.63, 0.75, 1.0, "plot"):
        rows = table(models, where, "wetbulb")
        label = "known plot / 0.63" if where == "plot" else f"{where:.2f} of vertical"
        print(f"   {label:18s} no history, region factors: {summary(score(rows, models, 'none', True))}")
    known = set(SITES)
    print(f"   The {len(known)} resorts with a published plot elevation only (no region factors, in-sample factor per model):")
    for where in (0.5, "plot"):
        rows = table(models, where, "wetbulb")
        alpha, grad, regions, _ = fit(rows, models, "none", False)
        errs = []
        for r in rows:
            if r["name"] in known:
                errs += [(r["region"], r["name"], s, v / r["rep"][s] - 1, v, r["rep"][s])
                         for s, v in predict(r, models, alpha, grad, regions).items()]
        print(f"   {'mid-mountain' if where == 0.5 else 'at the plot':18s} {summary(errs)}")
    print("   Share of Nov-Apr precipitation falling as snow (ECMWF, wet-bulb), base / mid / summit:")
    for name in ("Palisades Tahoe", "Whistler Blackcomb", "Heavenly", "Alta", "Vail", "Jackson Hole"):
        r = next(x for x in hindcast.resorts() if x.name == name)
        data, _ = series(name)
        p = np.nansum(data["ecmwf_ifs"][1]) / 25.4
        shares = [season_sums(name, "ecmwf_ifs", hindcast.elevation_m(r, f), "wetbulb")[1].sum() / p for f in (0.0, 0.5, 1.0)]
        print(f"     {name:20s} " + " / ".join(f"{x:.0%}" for x in shares))


LADDER = [
    # label, where, phase, gradient, regional, skill-weighted blend
    ("A  mid-mountain, air-temp phase, region factors (today's method)", 0.5, "air", "none", True, False),
    ("B  A without region factors (one factor per model)", 0.5, "air", "none", False, False),
    ("C  B + wet-bulb snow fraction", 0.5, "wetbulb", "none", False, False),
    ("D  C at the reporting plot (known plot, else 0.63 of vertical)", "plot", "wetbulb", "none", False, False),
    ("E  D + terrain-height gap, one gradient", "plot", "wetbulb", "shared", False, False),
    ("F  D + terrain-height gap, per model", "plot", "wetbulb", "each", False, False),
    ("G  E + region factors", "plot", "wetbulb", "shared", True, False),
    ("H  A + skill-weighted blend", 0.5, "air", "none", True, True),
    ("I  G + skill-weighted blend", "plot", "wetbulb", "shared", True, True),
]


def main(args):
    if "--checks" in args:
        overfit_checks()
        altitude_sweep()
        return
    if "--snotel" in args:
        snotel_eval()
        slr_check()
        return
    slr = APP_SLR
    if "--fit-slr" in args:
        slr = fit_slr()
    for label, models in (("days 1-2 (HRRR, ECMWF, GEM regional)", SHORT), ("days 3-10 (GFS, ECMWF, GEM global)", LONG)):
        print(f"\n=== {label}; leave-one-resort-out, snow ratio {slr}")
        for name, where, phase, gradient, regional, weighted in LADDER:
            rows = table(models, where, phase, slr)
            print(f"  {name}\n      no history: {summary(score(rows, models, gradient, regional, False, weighted))}"
                  f"\n      with resort factor: {summary(score(rows, models, gradient, regional, True, weighted))}")
        rows = table(models, "plot", "wetbulb", slr)
        alpha, grad, _, _ = fit(rows, models, "shared", False)
        print("  E coefficients:", {m: f"x{math.exp(alpha[m]):.2f}" for m in alpha},
              f"gradient {math.exp(next(iter(grad.values()))) - 1:+.0%} per km of unresolved height")
        print("  E by region:", summary(score(rows, models, "shared", False), by_region=True))
        print("  G by region, with resort factor:", summary(score(rows, models, "shared", True, True), by_region=True))
        if PRISM_TIF.exists() and cells():
            print("  US resorts only, downscaling choices (no region factors):")
            for name, predictor, gradient in (("none", "height", "none"), ("height gap", "height", "shared"),
                                              ("PRISM ratio", "prism", "shared")):
                rows = table(models, "plot", "wetbulb", slr, predictor=predictor, only="US")
                _, grad, _, _ = fit(rows, models, gradient, False)
                print(f"    {name:12s} coefficient {next(iter(grad.values())):+.2f}  {summary(score(rows, models, gradient, False))}")
    lead_mismatch(slr)


def lead_mismatch(slr=APP_SLR):
    """Today's factors are fitted on the archive of the app's providers, which holds the
    high-resolution models (HRRR, GEM regional). The live forecast serves those for ~2-3.5 days
    and the global GFS / GEM after. Score the global models with the high-resolution factors."""
    twin = {"gfs_global": HRRR_ARCHIVE, "gem_global": "gem_regional", "ecmwf_ifs": "ecmwf_ifs"}
    archive = (HRRR_ARCHIVE, "ecmwf_ifs", "gem_regional")
    short = table(archive, 0.5, "air", slr, only="US")
    long_ = table(LONG, 0.5, "air", slr, only="US")
    a_s, g_s, reg_s, _ = fit(short, archive, "none", True)
    a_l, g_l, reg_l, _ = fit(long_, LONG, "none", True)
    print("\n=== US resorts, days 3-10 models scored with factors fitted on the days 1-2 models (in-sample)")
    for label, alpha, reg in (("own factors", a_l, reg_l), ("days 1-2 factors (today)", {m: a_s[twin[m]] for m in LONG}, reg_s)):
        errs = []
        for row in long_:
            for s_, v in predict(row, LONG, alpha, {m: 0.0 for m in LONG}, reg).items():
                errs.append((row["region"], row["name"], s_, v / row["rep"][s_] - 1, v, row["rep"][s_]))
        bias = statistics.median(e[3] for e in errs)
        print(f"  {label:26s} median bias {bias:+.0%}  {summary(errs)}")
    print("  factor per model:", {m: f"x{math.exp(a_l[m]):.2f} (twin x{math.exp(a_s[twin[m]]):.2f})" for m in LONG})


def fit_slr():
    """Coarse grid over the snow-ratio constants, judged leave-one-resort-out on variant E."""
    best = None
    for scale in (0.7, 0.84, 1.0):
        for cold in (0.5, 0.92, 1.3):
            for rate_exp in (0.0, -0.15, -0.31, -0.45):
                p = (scale, cold, rate_exp)
                es = []
                for models in (SHORT, LONG):
                    rows = table(models, "plot", "wetbulb", p)
                    es += [abs(e[3]) for e in score(rows, models, "shared", False)]
                val = statistics.median(es) + statistics.fmean(es) / 4
                print(f"  slr {p}: median {statistics.median(es):.1%} mean {statistics.fmean(es):.1%}", flush=True)
                if best is None or val < best[0]:
                    best = (val, p)
    print("best snow ratio:", best[1])
    return best[1]


if __name__ == "__main__":
    main(sys.argv[1:])
