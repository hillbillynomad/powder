"""Does a site's correction factor hold in warm storms as well as cold ones? (COOP daily data)"""
import sys, math, json
from datetime import date, timedelta
sys.path.insert(0, "tools/calibrate")
import numpy as np, coop, model2, hindcast

def model_days(sid, m, elev):
    out = {}
    for season in coop.SEASONS:
        p = coop.model_path(sid, season)
        if not p.exists(): continue
        h = json.loads(p.read_text())["hourly"]
        pr = np.array(h.get(f"precipitation_{m}") or [], dtype=float)
        t = np.array(h.get(f"temperature_2m_{m}") or [], dtype=float)
        rh = np.array(h.get(f"relative_humidity_2m_{m}") or [], dtype=float)
        if not len(pr) or np.isnan(pr).mean() > 0.1: continue
        ok = ~np.isnan(pr) & ~np.isnan(t)
        pr, t = np.where(ok, pr, 0.0), np.where(ok, t, 0.0)
        frac = model2.snow_fraction(model2.wet_bulb(t, np.where(np.isnan(rh), 85.0, rh), elev))
        sw = pr * frac
        snow = sw * model2.snow_ratio(t, model2.rolling_mean(sw)) / 25.4
        start = date(season, 11, 1)
        for k in range(len(pr) // 24):
            sl = slice(k * 24, (k + 1) * 24)
            w = pr[sl].sum()
            tw = (pr[sl] * t[sl]).sum() / w if w > 0.5 else None
            out[start + timedelta(days=k)] = (snow[sl].sum(), w / 25.4, tw)
    return out

BANDS = (("cold  (< -8 C)", -99, -8), ("mid   (-8..-3 C)", -8, -3), ("warm  (> -3 C)", -3, 99))
rows = []
for m in ("ecmwf_ifs", "gfs_global", "gem_global"):
    per = []
    for sid, st in coop.stations().items():
        seasons = coop.complete_seasons(sid)
        if not seasons: continue
        ob, md = coop.daily(sid), model_days(sid, m, st["elev_m"])
        days = [d for d in md if d in ob and md[d][2] is not None and any(hindcast.in_season(d, s) for s in seasons)]
        acc = {b[0]: [0.0, 0.0, 0.0, 0.0, 0] for b in BANDS}
        for d in days:
            for name, lo, hi in BANDS:
                if lo <= md[d][2] < hi:
                    a = acc[name]; a[0] += ob[d][0]; a[1] += md[d][0]; a[2] += ob[d][1]; a[3] += md[d][1]; a[4] += 1
        allo = sum(a[0] for a in acc.values()); allm = sum(a[1] for a in acc.values())
        if allo > 30 and all(a[0] > 5 and a[1] > 5 for a in acc.values()):
            per.append((sid, st, acc, math.log(allo / allm)))
    print(f"\n{m}: {len(per)} stations with snow in all three temperature bands")
    print(f"  {'storm temperature':18s} {'snow obs/model':>14s} {'water obs/model':>15s}  {'factor fitted on all days, miss in band':>40s}")
    shifts = {}
    for name, _, _ in BANDS:
        s = np.array([math.log(a[name][0] / a[name][1]) for _, _, a, _ in per])
        w = np.array([math.log(max(a[name][2], .01) / max(a[name][3], .01)) for _, _, a, _ in per])
        f_all = np.array([x[3] for x in per])
        miss = np.abs(np.exp(f_all - s) - 1)
        shifts[name] = s - f_all
        print(f"  {name:18s} {math.exp(np.median(s)):14.2f} {math.exp(np.median(w)):15.2f}  {np.median(miss):40.0%}")
    c = np.array([math.log(a['cold  (< -8 C)'][0] / a['cold  (< -8 C)'][1]) for _, _, a, _ in per])
    wa = np.array([math.log(a['warm  (> -3 C)'][0] / a['warm  (> -3 C)'][1]) for _, _, a, _ in per])
    print(f"  station factor cold vs warm storms: r = {np.corrcoef(c, wa)[0, 1]:.2f}; warm minus cold, median {math.exp(np.median(wa - c)) - 1:+.0%}")
