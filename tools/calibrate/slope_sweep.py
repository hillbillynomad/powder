"""Which snow-ratio temperature slope makes site factors independent of storm temperature?"""
import sys, math, json
from datetime import date, timedelta
sys.path.insert(0, "tools/calibrate")
import numpy as np, coop, model2, hindcast

BANDS = ((-99, -8), (-8, -3), (-3, 99))
cache = {}
def hours(sid, m):
    if (sid, m) not in cache:
        chunks = []
        for season in coop.SEASONS:
            p = coop.model_path(sid, season)
            if not p.exists(): continue
            h = json.loads(p.read_text())["hourly"]
            pr = np.array(h.get(f"precipitation_{m}") or [], dtype=float)
            if not len(pr) or np.isnan(pr).mean() > 0.1: continue
            t = np.array(h[f"temperature_2m_{m}"], dtype=float); rh = np.array(h.get(f"relative_humidity_2m_{m}") or [np.nan] * len(pr), dtype=float)
            chunks.append((season, pr, t, rh))
        cache[(sid, m)] = chunks
    return cache[(sid, m)]

def days(sid, m, elev, params):
    out = {}
    for season, pr, t, rh in hours(sid, m):
        ok = ~np.isnan(pr) & ~np.isnan(t)
        p_, t_ = np.where(ok, pr, 0.0), np.where(ok, t, 0.0)
        sw = p_ * model2.snow_fraction(model2.wet_bulb(t_, np.where(np.isnan(rh), 85.0, rh), elev))
        snow = sw * model2.snow_ratio(t_, model2.rolling_mean(sw), params) / 25.4
        start = date(season, 11, 1)
        for k in range(len(p_) // 24):
            sl = slice(k * 24, (k + 1) * 24); w = p_[sl].sum()
            out[start + timedelta(days=k)] = (snow[sl].sum(), (p_[sl] * t_[sl]).sum() / w if w > 0.5 else None)
    return out

def coop_eval(params, m="ecmwf_ifs"):
    band_logs = [[] for _ in BANDS]; miss = [[] for _ in BANDS]; shift = []
    for sid, st in coop.stations().items():
        seasons = coop.complete_seasons(sid)
        if not seasons: continue
        ob, md = coop.daily(sid), days(sid, m, st["elev_m"], params)
        acc = [[0.0, 0.0] for _ in BANDS]
        for d, (s, tw) in md.items():
            if tw is None or d not in ob or not any(hindcast.in_season(d, x) for x in seasons): continue
            for i, (lo, hi) in enumerate(BANDS):
                if lo <= tw < hi: acc[i][0] += ob[d][0]; acc[i][1] += s
        if all(a[0] > 5 and a[1] > 5 for a in acc):
            f = math.log(sum(a[0] for a in acc) / sum(a[1] for a in acc))
            for i, a in enumerate(acc):
                band_logs[i].append(math.log(a[0] / a[1])); miss[i].append(abs(math.exp(f) * a[1] / a[0] - 1))
            shift.append(math.log(acc[2][0] / acc[2][1]) - math.log(acc[0][0] / acc[0][1]))
    return ([math.exp(np.median(b)) for b in band_logs], [np.median(x) for x in miss],
            math.exp(np.median(shift)) - 1, len(shift))

def resort_eval(params):
    out = []
    for label, models in (("days 3-10", model2.LONG),):
        rows = model2.table(models, 0.5, "air", params)
        nh = model2.score(rows, models, "none", True)
        rf = model2.score(rows, models, "none", True, True)
        seas = lambda e: np.median([abs(x[3]) for x in e])
        out.append((seas(nh), seas(rf)))
    return out[0]

print(f"{'scale':>5s} {'cold':>5s} {'warm':>5s} {'rate':>5s} | COOP obs/model cold/mid/warm | miss in band (factor from all days) | warm-cold shift | resorts per season: no history / own factor")
for scale, cold, warm, rate in ((0.84, 0.92, 2, -0.31), (0.84, 0.6, 2, -0.31), (0.84, 0.3, 2, -0.31),
                                (0.84, 0.0, 2, -0.31), (0.84, 0.3, 1, -0.31), (0.84, 0.3, 2, -0.15),
                                (0.84, 0.0, 1, -0.15)):
    params = (scale, cold, rate)
    model2_ratio = model2.snow_ratio
    # warm slope is fixed at 2 in model2.snow_ratio; patch it for this run
    def ratio(t_c, rate_mm_h, p=params, w=warm):
        k = np.where(t_c < -2, 12 + p[1] * (-2 - t_c), 12 - w * (t_c + 2))
        return np.clip(p[0] * k * np.maximum(rate_mm_h, 0.05) ** p[2], 5, 25)
    model2.snow_ratio = ratio
    b, mi, sh, n = coop_eval(params)
    nh, rf = resort_eval(params)
    model2.snow_ratio = model2_ratio
    print(f"{scale:5.2f} {cold:5.2f} {warm:5.1f} {rate:5.2f} | {b[0]:.2f} / {b[1]:.2f} / {b[2]:.2f}             | "
          f"{mi[0]:4.0%} / {mi[1]:4.0%} / {mi[2]:4.0%}                  | {sh:+6.0%} (n={n})  | {nh:4.0%} / {rf:4.0%}", flush=True)
