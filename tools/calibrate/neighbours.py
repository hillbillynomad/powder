"""Does combining several grid cells beat the single cell Open-Meteo hands back?

    poetry run python tools/calibrate/neighbours.py fetch   # 3x3 cells round every point, daily precipitation
    poetry run python tools/calibrate/neighbours.py score   # cell choices vs SNOTEL and resort reports

For each calibration resort and SNOTEL site, and each model, fetches daily Nov-Apr precipitation
from the four grid cells surrounding the point (raw cells: `elevation=nan`, queried at the corners
of a box one grid spacing wide) for two winters, then compares ways of turning them into one value:

    matched   the cell Open-Meteo picks when asked for the point's elevation (what the app does)
    nearest   the cell whose centre is closest
    bilinear  inverse-distance weighting of the four cells
    mean4     plain mean of the four cells
    highest   the highest of the four cells
    wettest   the wettest of the four cells

Each choice rescales the point's snow water / snowfall from model2.py by a fixed factor: its
precipitation over the fetched winters / the matched cell's over the same winters. How much wetter
one cell is than its neighbour is climatological, so two winters fix it, and a fixed factor is
what the app would ship. (An earlier version fetched 3x3 blocks for 2022-26; those files are still
read when present.) Open-Meteo counts each location and each two weeks of data as a call, so the
fetch is sized to fit inside its free daily limit.
"""

import json
import math
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import numpy as np
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hindcast  # noqa: E402
import raw  # noqa: E402

CACHE = hindcast.CACHE / "neighbours"
SPACING_DEG = {"gfs_global": 0.117, "ecmwf_ifs": 0.08, "gem_global": 0.135}
CHOICES = ("matched", "nearest", "bilinear", "mean4", "highest", "wettest")
WINTERS = (2023, 2024)  # Nov-Apr seasons fetched for the four-cell files


def path(key: str, model: str) -> Path:
    return CACHE / f"{key.replace(' ', '_')}_{model}.json"


def quad_path(key: str, model: str) -> Path:
    return CACHE / f"{key.replace(' ', '_')}_{model}_quad.json"


def fetch(workers: int = 3) -> None:
    """Four surrounding cells per point and model; SNOTEL sites first (the cleaner test)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    pts = raw.points()
    order = sorted(pts, key=lambda k: not k.startswith("USS"))
    jobs = [(key, model, pts[key]) for key in order for model in SPACING_DEG
            if not path(key, model).exists() and not quad_path(key, model).exists()]
    print(len(jobs), "point-models to fetch", flush=True)
    stop = []

    def one(job):
        if stop:
            return
        key, model, (lat, lon, _) = job
        h = SPACING_DEG[model] / 2
        kx = 1 / math.cos(math.radians(lat))
        pts4 = [(lat + a * h, lon + b * h * kx) for a in (-1, 1) for b in (-1, 1)]
        blocks = []
        for season in WINTERS:
            for attempt in range(8):
                try:
                    resp = requests.get(raw.URL, timeout=240, params=dict(
                        latitude=",".join(f"{a:.4f}" for a, _ in pts4),
                        longitude=",".join(f"{b:.4f}" for _, b in pts4),
                        elevation=",".join(["nan"] * 4), cell_selection="nearest",
                        start_date=f"{season}-11-01", end_date=f"{season + 1}-04-30",
                        daily="precipitation_sum", models=model, timezone="auto"))
                except (requests.ConnectionError, requests.Timeout):
                    time.sleep(4 * (attempt + 1))
                    continue
                if resp.status_code == 200:
                    blocks.append(resp.json())
                    break
                if "Daily API request limit" in resp.text:
                    print("daily limit reached; rerun tomorrow", flush=True)
                    stop.append(1)
                    return
                print(resp.status_code, resp.text[:120], flush=True)
                time.sleep(20 * (attempt + 1))
            else:
                return
        # merge the two winters cell by cell
        merged = []
        for cell in zip(*blocks):
            d = dict(cell[0])
            d["daily"] = {"time": sum((c["daily"]["time"] for c in cell), []),
                          "precipitation_sum": sum((c["daily"]["precipitation_sum"] for c in cell), [])}
            merged.append(d)
        quad_path(key, model).write_text(json.dumps(merged))
        print("fetched", key, model, flush=True)

    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(one, jobs))


def season_precip(daily: dict) -> np.ndarray:
    """Nov-Apr precipitation (mm) per season index from one cell's daily block."""
    out = np.zeros(len(raw.SEASONS))
    for t, v in zip(daily["time"], daily["precipitation_sum"]):
        if v is None:
            continue
        day = date.fromisoformat(t)
        season = day.year if day.month >= 7 else day.year - 1
        if season in raw.SEASONS and hindcast.in_season(day, season):
            out[raw.SEASONS.index(season)] += v
    return out


def cell_choices(key: str, model: str, lat: float, lon: float):
    """{choice: season precipitation array} from the cells around the point (no "matched"), plus
    "_seasons": the season indices the file covers."""
    p = path(key, model) if path(key, model).exists() else quad_path(key, model)
    if not p.exists():
        return None
    cells = {}
    for o in json.loads(p.read_text()):
        cells.setdefault((o["latitude"], o["longitude"]), (o["elevation"], season_precip(o["daily"])))
    items = []
    for (clat, clon), (elev, prec) in cells.items():
        dist = math.hypot((clat - lat) * 111, (clon - lon) * 111 * math.cos(math.radians(lat)))
        items.append((dist, elev, prec))
    items.sort(key=lambda x: x[0])
    near4 = items[:4]
    w = np.array([1 / max(d, 0.5) for d, _, _ in near4])
    covered = [i for i in range(len(raw.SEASONS)) if items[0][2][i] > 0]
    return {
        "nearest": items[0][2],
        "bilinear": sum(wi * p_ for wi, (_, _, p_) in zip(w, near4)) / w.sum(),
        "mean4": np.mean([p_ for _, _, p_ in near4], axis=0),
        "highest": max(near4, key=lambda x: x[1])[2],
        "wettest": max(near4, key=lambda x: x[2].sum())[2],
        "_seasons": covered,
        "_n": len(items),
    }


def factor(ch: dict, base: np.ndarray, choice: str) -> float:
    """Fixed precipitation factor of a cell choice relative to the matched cell."""
    if choice == "matched":
        return 1.0
    idx = ch["_seasons"]
    return float(ch[choice][idx].sum() / base[idx].sum()) if base[idx].sum() > 0 else 1.0


def matched_precip(key: str, model: str) -> np.ndarray:
    """Season precipitation (mm) of the elevation-matched cell, from the hourly raw files."""
    import model2
    data, _ = model2.series(key)
    si, p, _, _ = data[model]
    return np.bincount(si, np.nan_to_num(p), len(raw.SEASONS))


def score() -> None:
    import model2
    import snotel
    from reported import complete

    stations = snotel.SITES["stations"]
    print("SNOTEL: snow water collected vs model, by cell choice (error predicting an unseen station)")
    print(f"  {'model':13s} " + " ".join(f"{c:>9s}" for c in CHOICES))
    for model in SPACING_DEG:
        logs = {c: [] for c in CHOICES}
        for sid, st in stations.items():
            ch = cell_choices(sid, model, st["lat"], st["lon"])
            water = model2.daily_water(sid, model)
            obs = snotel.gains(sid)
            days = sorted(set(water) & set(obs))
            if ch is None or len(days) < 300:
                continue
            base = matched_precip(sid, model)
            o, w = sum(obs[d][0] for d in days), sum(water[d] for d in days)
            for c in CHOICES:
                logs[c].append(math.log(o / (w * factor(ch, base, c))))
        row = []
        for c in CHOICES:
            y = np.array(logs[c])
            loo = [abs(math.exp(np.median(np.delete(y, i)) - y[i]) - 1) for i in range(len(y))]
            row.append(f"{np.median(loo):8.0%} ")
        print(f"  {model:13s} " + " ".join(row) + f"  n={len(y)}")

    print("\nResort reports: leave-one-resort-out error, GFS + ECMWF + GEM global, region factors")
    models = model2.LONG
    base_rows = model2.table(models, 0.5, "air")
    by_name = {r.name: r for r in hindcast.resorts()}
    for c in CHOICES:
        rows = []
        for row in base_rows:
            r = by_name[row["name"]]
            new = dict(row, models={})
            for m in row["models"]:
                if c == "matched":
                    new["models"][m] = row["models"][m]
                    continue
                ch = cell_choices(r.name, m, r.latitude, r.longitude)
                if ch is None:
                    continue
                k = factor(ch, matched_precip(r.name, m), c)
                new["models"][m] = {s: v * k for s, v in row["models"][m].items()}
            if new["models"]:
                rows.append(new)
        print(f"  {c:9s} no history: {model2.summary(model2.score(rows, models, 'none', True))}")
        print(f"  {'':9s} no history, no region factors: {model2.summary(model2.score(rows, models, 'none', False))}")
        print(f"  {'':9s} with resort factor: {model2.summary(model2.score(rows, models, 'none', True, True))}")


if __name__ == "__main__":
    {"fetch": fetch, "score": score}[sys.argv[1]]()
