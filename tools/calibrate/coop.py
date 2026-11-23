"""Test the snowfall method against NWS cooperative (COOP) observers instead of resorts.

    poetry run python tools/calibrate/coop.py select   # balanced set of mountain COOP stations
    poetry run python tools/calibrate/coop.py obs      # their daily SNOW / PRCP / SNWD (NCEI GHCN-Daily)
    poetry run python tools/calibrate/coop.py model    # GFS / ECMWF / GEM hourly at each station (~150 calls)
    poetry run python tools/calibrate/coop.py score

COOP observers measure once a day on a cleared board to the NWS standard, and melt the snow for
its water (PRCP). That gives the two halves of the method separately: precipitation (model water
vs PRCP) and snow ratio (SNOW / PRCP vs the app's ratio), plus the end-to-end snowfall, at sites
where nobody has a reason to round up. Stations at a resort (Alta, Brighton, Winter Park...) are
flagged so they can be compared with the rest.
"""

import json
import math
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hindcast  # noqa: E402
import model2  # noqa: E402
import raw  # noqa: E402

CACHE = hindcast.CACHE / "coop"
SITES = Path(__file__).resolve().parent / "coop_sites.json"
NCEI = "https://www.ncei.noaa.gov/access/services/data/v1"
MODELS = ("gfs_global", "ecmwf_ifs", "gem_global")
SEASONS = raw.SEASONS
# minimum elevation (m) by state, and how many stations to take per state
STATES = {"CO": (2300, 8), "UT": (2000, 6), "WY": (2000, 5), "MT": (1600, 5), "ID": (1500, 5),
          "NM": (2200, 4), "AZ": (2100, 3), "NV": (1900, 3), "CA": (1400, 7), "OR": (1100, 5),
          "WA": (900, 5)}


def km(a, b, c, d):
    return 6371 * math.hypot(math.radians(c - a), math.radians(d - b) * math.cos(math.radians(a)))


def select() -> None:
    inv = {}
    for line in open(CACHE / "ghcnd-inventory.txt"):
        sid, el, y0, y1 = line[:11], line[31:35], int(line[36:40]), int(line[41:45])
        if sid.startswith("USC") and el in ("SNOW", "PRCP"):
            inv.setdefault(sid, {})[el] = (y0, y1)
    resorts = hindcast.resorts()
    by_state = {}
    for line in open(CACHE / "ghcnd-stations.txt"):
        sid, state = line[:11], line[38:40]
        e = inv.get(sid)
        if state not in STATES or not e or not all(k in e and e[k][0] <= 2021 and e[k][1] >= 2026 for k in ("SNOW", "PRCP")):
            continue
        lat, lon, elev = float(line[12:20]), float(line[21:30]), float(line[31:37])
        if elev < STATES[state][0]:
            continue
        d, name = min((km(lat, lon, r.latitude, r.longitude), r.name) for r in resorts)
        by_state.setdefault(state, []).append(dict(id=sid, name=line[41:71].strip(), state=state, lat=lat,
                                                   lon=lon, elev_m=elev, at_resort=name if d < 3 else None))
    out = {}
    for state, rows in by_state.items():
        rows.sort(key=lambda r: -r["elev_m"])
        # prefer the highest, but keep them at least 15 km apart so one valley doesn't dominate
        picked = []
        for r in rows:
            if all(km(r["lat"], r["lon"], p["lat"], p["lon"]) > 15 for p in picked):
                picked.append(r)
            if len(picked) >= 2 * STATES[state][1]:  # take extra: some will have gappy records
                break
        for r in picked:
            out[r.pop("id")] = r
    SITES.write_text(json.dumps({"_doc": "Mountain COOP stations (GHCN-Daily) for coop.py", "stations": out}, indent=1))
    print(len(out), "stations:", {s: sum(r["state"] == s for r in out.values()) for s in STATES})


def stations() -> dict:
    return json.loads(SITES.read_text())["stations"]


def obs(workers: int = 4) -> None:
    (CACHE / "obs").mkdir(parents=True, exist_ok=True)

    def one(sid):
        p = CACHE / "obs" / f"{sid}.json"
        if p.exists():
            return
        for attempt in range(6):
            try:
                r = requests.get(NCEI, timeout=180, params=dict(
                    dataset="daily-summaries", stations=sid, dataTypes="SNOW,PRCP,SNWD",
                    startDate=hindcast.START, endDate=hindcast.END, units="standard", format="json"))
                r.raise_for_status()
                tmp = p.with_suffix(".tmp")
                tmp.write_text(r.text)
                tmp.replace(p)
                print("obs", sid, flush=True)
                return
            except requests.RequestException:
                time.sleep(4 * (attempt + 1))

    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(one, stations()))


def daily(sid: str) -> dict:
    """{date: (snow in, water in)} for days where both were reported. COOP readings are taken once a
    day (often 7-8 am) and cover the 24 h before, so the value on date D is mostly day D-1."""
    p = CACHE / "obs" / f"{sid}.json"
    if not p.exists():
        return {}
    out = {}
    for r in json.loads(p.read_text()):
        s, w = r.get("SNOW", "").strip(), r.get("PRCP", "").strip()
        if s and w:
            out[date.fromisoformat(r["DATE"]) - timedelta(days=1)] = (float(s), float(w))
    return out


def complete_seasons(sid: str, min_share: float = 0.9) -> list[int]:
    d = daily(sid)
    out = []
    for s in SEASONS:
        days = (date(s + 1, 4, 30) - date(s, 11, 1)).days + 1
        if sum(hindcast.in_season(day, s) for day in d) >= min_share * days:
            out.append(s)
    return out


def model_path(sid: str, season: int) -> Path:
    return CACHE / "model" / f"{sid}_{season}.json"


def model(workers: int = 3) -> None:
    (CACHE / "model").mkdir(parents=True, exist_ok=True)
    jobs = [(sid, s, st) for sid, st in stations().items() for s in complete_seasons(sid)
            if not model_path(sid, s).exists()]
    print(len(jobs), "station-seasons to fetch", flush=True)

    def one(job):
        sid, season, st = job
        data = raw.get(dict(latitude=st["lat"], longitude=st["lon"], elevation=round(st["elev_m"]),
                            timezone="auto", start_date=f"{season}-11-01", end_date=f"{season + 1}-04-30",
                            hourly=raw.HOURLY, models=",".join(MODELS)))
        model_path(sid, season).write_text(json.dumps(data))
        print("fetched", sid, season, flush=True)

    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(one, jobs))


def model_daily(sid: str, m: str, elev_m: float) -> dict:
    """{date: (snow in, water in, snow water in)} the app's way at the station: wet-bulb snow
    fraction, then the app's snow ratio (temperature and storm rate)."""
    out = {}
    for season in SEASONS:
        p = model_path(sid, season)
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        h = d["hourly"]
        pr = np.array(h.get(f"precipitation_{m}") or [], dtype=float)
        t = np.array(h.get(f"temperature_2m_{m}") or [], dtype=float)
        rh = np.array(h.get(f"relative_humidity_2m_{m}") or [], dtype=float)
        if not len(pr) or np.isnan(pr).mean() > 0.1:
            continue
        ok = ~np.isnan(pr) & ~np.isnan(t)
        pr, t = np.where(ok, pr, 0.0), np.where(ok, t, 0.0)
        frac = model2.snow_fraction(model2.wet_bulb(t, np.where(np.isnan(rh), 85.0, rh), elev_m))
        sw = pr * frac
        snow = sw * model2.snow_ratio(t, model2.rolling_mean(sw)) / 25.4
        start = date(season, 11, 1)
        for k in range(len(pr) // 24):
            sl = slice(k * 24, (k + 1) * 24)
            out[start + timedelta(days=k)] = (float(snow[sl].sum()), float(pr[sl].sum() / 25.4), float(sw[sl].sum() / 25.4))
    return out


def loo(y: np.ndarray) -> float:
    """Median |error| predicting each station with the median log factor of the others."""
    return float(np.median([abs(math.exp(np.median(np.delete(y, i)) - y[i]) - 1) for i in range(len(y))]))


def score() -> None:
    sts = stations()
    rows = []
    for sid, st in sts.items():
        ob = daily(sid)
        seasons = complete_seasons(sid)
        if not seasons:
            continue
        per_model = {}
        for m in MODELS:
            md = model_daily(sid, m, st["elev_m"])
            days = [d for d in md if d in ob and any(hindcast.in_season(d, s) for s in seasons)]
            if len(days) < 150:
                continue
            per_model[m] = dict(
                obs_snow=sum(ob[d][0] for d in days), obs_water=sum(ob[d][1] for d in days),
                mod_snow=sum(md[d][0] for d in days), mod_water=sum(md[d][1] for d in days),
                daily=[(ob[d][0], md[d][0], ob[d][1], md[d][1]) for d in days],
                seasons={s: (sum(ob[d][0] for d in days if hindcast.in_season(d, s)),
                             sum(md[d][0] for d in days if hindcast.in_season(d, s))) for s in seasons})
        if len(per_model) == len(MODELS) and per_model["ecmwf_ifs"]["obs_snow"] > 20:
            rows.append(dict(id=sid, **st, models=per_model))
    resort = [r for r in rows if r["at_resort"]]
    print(f"{len(rows)} COOP stations with complete seasons ({len(resort)} at a resort: "
          f"{', '.join(sorted(r['at_resort'] for r in resort))})")

    print("\n1. End to end: season snowfall, one factor per model for every station (leave-one-station-out)")
    print(f"   {'model':11s} {'obs/model':>9s} {'station miss':>12s}   {'per season':>10s}   {'within 20%':>10s}")
    blend_logs = {}
    for m in MODELS:
        y = np.array([math.log(r["models"][m]["obs_snow"] / r["models"][m]["mod_snow"]) for r in rows])
        seas = []
        for i, r in enumerate(rows):
            f = math.exp(np.median(np.delete(y, i)))
            seas += [abs(f * mo / ob - 1) for ob, mo in r["models"][m]["seasons"].values() if ob > 5]
        stn = [abs(math.exp(np.median(np.delete(y, i)) - y[i]) - 1) for i in range(len(y))]
        print(f"   {m:11s} {math.exp(np.median(y)):9.2f} {np.median(stn):12.0%}   {np.median(seas):10.0%}   "
              f"{sum(x <= .2 for x in stn) / len(stn):10.0%}")
        blend_logs[m] = y
    # blend: each model scaled by its LOO factor, then averaged
    stn, seas = [], []
    for i, r in enumerate(rows):
        f = {m: math.exp(np.median(np.delete(blend_logs[m], i))) for m in MODELS}
        pred = statistics.mean(f[m] * r["models"][m]["mod_snow"] for m in MODELS)
        stn.append(abs(pred / r["models"]["ecmwf_ifs"]["obs_snow"] - 1))
        for s, (ob, _) in r["models"]["ecmwf_ifs"]["seasons"].items():
            if ob > 5:
                seas.append(abs(statistics.mean(f[m] * r["models"][m]["seasons"][s][1] for m in MODELS) / ob - 1))
    print(f"   {'blend':11s} {'':9s} {np.median(stn):12.0%}   {np.median(seas):10.0%}   {sum(x <= .2 for x in stn) / len(stn):10.0%}")
    print(f"   (resort stations only: blend station miss {np.median([s for s, r in zip(stn, rows) if r['at_resort']]):.0%};"
          f" others {np.median([s for s, r in zip(stn, rows) if not r['at_resort']]):.0%})")

    print("\n2. Where the error comes from (ECMWF): precipitation vs snow ratio, leave-one-station-out")
    m = "ecmwf_ifs"
    water = np.array([math.log(r["models"][m]["obs_water"] / r["models"][m]["mod_water"]) for r in rows])
    ratio_obs = np.array([r["models"][m]["obs_snow"] / r["models"][m]["obs_water"] for r in rows])
    snow = blend_logs[m]
    print(f"   station miss, precipitation (model water vs melted COOP water): {loo(water):.0%}")
    print(f"   station miss, snowfall (end to end):                           {loo(snow):.0%}")
    print(f"   observed season snow / water ratio: median {np.median(ratio_obs):.1f}:1, "
          f"middle half {np.percentile(ratio_obs, 25):.1f}-{np.percentile(ratio_obs, 75):.1f}:1 "
          f"(includes rain in the water)")
    r_ = np.corrcoef(water, snow)[0, 1]
    print(f"   correlation of the precipitation miss with the snowfall miss across stations: r = {r_:.2f} "
          f"(r^2 {r_ ** 2:.0%} of the snowfall miss is precipitation)")

    print("\n3. Snow ratio on snowy days (COOP >= 3 in of snow and >= 0.2 in of water, model snowing too)")
    obs_r, app_r, temps = [], [], []
    for r in rows:
        for ob_s, mo_s, ob_w, mo_w in r["models"][m]["daily"]:
            if ob_s >= 3 and ob_w >= 0.2 and mo_w >= 0.1 and mo_s > 0:
                obs_r.append(ob_s / ob_w)
                app_r.append(mo_s / mo_w)
    obs_r, app_r = np.array(obs_r), np.array(app_r)
    print(f"   {len(obs_r)} station-days: observed median {np.median(obs_r):.1f}:1 (middle half "
          f"{np.percentile(obs_r, 25):.1f}-{np.percentile(obs_r, 75):.1f}), app median {np.median(app_r):.1f}:1;"
          f" correlation day by day r = {np.corrcoef(obs_r, app_r)[0, 1]:.2f}")

    print("\n4. Day to day (ECMWF, scaled by its factor): 3-day snowfall on stormy spells")
    f = math.exp(np.median(snow))
    o3, m3 = [], []
    for r in rows:
        d = r["models"][m]["daily"]
        o = np.convolve([x[0] for x in d], np.ones(3), "valid")
        w = np.convolve([x[1] for x in d], np.ones(3), "valid") * f
        sel = (o >= 4) | (w >= 4)
        o3 += list(o[sel])
        m3 += list(w[sel])
    o3, m3 = np.array(o3), np.array(m3)
    print(f"   {len(o3)} spells: correlation r = {np.corrcoef(o3, m3)[0, 1]:.2f}, median |miss| "
          f"{np.median(np.abs(m3 - o3)):.1f} in on a median spell of {np.median(o3):.1f} in")



def compare() -> None:
    """The same correction ladder used for resorts, applied to COOP stations (blend of 3 models)."""
    sts = stations()
    rows = []
    for sid, st in sts.items():
        ob = daily(sid)
        seasons = complete_seasons(sid)
        mods = {m: model_daily(sid, m, st["elev_m"]) for m in MODELS}
        per = {}
        for s in seasons:
            days = [d for d in ob if hindcast.in_season(d, s) and all(d in mods[m] for m in MODELS)]
            if len(days) < 150:
                continue
            o = sum(ob[d][0] for d in days)
            if o > 5:
                per[s] = (o, {m: sum(mods[m][d][0] for d in days) for m in MODELS})
        if per:
            rows.append(dict(id=sid, state=st["state"], elev=st["elev_m"], resort=st["at_resort"], seasons=per))
    print(f"{len(rows)} stations, {sum(len(r['seasons']) for r in rows)} station-seasons")

    def logs(rs, m, skip=None):
        """log(obs / model) per station over its seasons (optionally without one season)."""
        out = []
        for r in rs:
            ss = [s for s in r["seasons"] if s != skip]
            if ss:
                out.append(math.log(sum(r["seasons"][s][0] for s in ss) / sum(r["seasons"][s][1][m] for s in ss)))
        return out

    def run(label, region: bool, own: bool, shrink: float = 0.0):
        errs, stn = [], {}
        for i, r in enumerate(rows):
            others = rows[:i] + rows[i + 1:]
            pool = [o for o in others if o["state"] == r["state"]] if region else others
            if region and len(pool) < 2:
                pool = others
            f = {m: math.exp(statistics.median(logs(pool, m))) for m in MODELS}
            for s, (o, mod) in r["seasons"].items():
                pred = statistics.mean(f[m] * mod[m] for m in MODELS)
                if own:
                    rest = [x for x in r["seasons"] if x != s]
                    if not rest:
                        continue
                    lr = [math.log(r["seasons"][x][0] / statistics.mean(f[m] * r["seasons"][x][1][m] for m in MODELS)) for x in rest]
                    pred *= math.exp(statistics.fmean(lr) * len(lr) / (len(lr) + shrink))
                errs.append(abs(pred / o - 1))
                t = stn.setdefault(r["id"], [0.0, 0.0])
                t[0] += pred
                t[1] += o
        st_err = [abs(p / o - 1) for p, o in stn.values()]
        print(f"   {label:46s} per station {np.median(st_err):4.0%}   per season {np.median(errs):4.0%}"
              f"   within 20% {sum(e <= .2 for e in errs) / len(errs):4.0%}  (n={len(errs)})")

    print("\nCOOP observers, same ladder as resorts (blend of GFS, ECMWF, GEM global):")
    run("one factor per model (no history)", False, False)
    run("+ state factors (no history)", True, False)
    run("+ station's own factor, other seasons", True, True)
    run("+ station's own factor, shrunk n/(n+1)", True, True, 1.0)

    # stability of the station factor: first half vs second half
    a, b = [], []
    f = {m: math.exp(statistics.median(logs(rows, m))) for m in MODELS}
    for r in rows:
        early = [s for s in r["seasons"] if s <= 2023]
        late = [s for s in r["seasons"] if s >= 2024]
        if early and late:
            g = lambda ss: math.log(sum(r["seasons"][s][0] for s in ss) / sum(statistics.mean(f[m] * r["seasons"][s][1][m] for m in MODELS) for s in ss))  # noqa: E731
            a.append(g(early))
            b.append(g(late))
    print(f"\n   station factor 2022-24 vs 2024-26: r = {np.corrcoef(a, b)[0, 1]:.2f} over {len(a)} stations "
          f"(spread {np.std(a):.2f} log; resorts: r = 0.66, spread 0.22)")
    by = {}
    for r, y in zip(rows, logs(rows, "ecmwf_ifs")):
        band = "below 2000 m" if r["elev"] < 2000 else "2000-2500 m" if r["elev"] < 2500 else "above 2500 m"
        by.setdefault(band, []).append(y)
    print("   ECMWF obs/model by station elevation: " + ", ".join(
        f"{k} x{math.exp(np.median(v)):.2f} (spread {np.std(v):.2f}, n={len(v)})" for k, v in sorted(by.items())))


if __name__ == "__main__":
    {"select": select, "obs": obs, "model": model, "score": score, "compare": compare}[sys.argv[1]]()
