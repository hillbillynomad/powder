"""Raw per-model hindcast for the prototype model (model2.py).

Fetches hourly precipitation, temperature and humidity from each *underlying* model (the app's
`gfs_seamless` is HRRR 3 km for ~2 days then GFS 13-25 km; `gem_seamless` is GEM regional 10 km
then GEM global 15 km) for the calibration resorts and the SNOTEL sites, Nov-Apr 2022-26, plus
each model's grid-cell terrain height at the cell Open-Meteo picks.

    poetry run python tools/calibrate/raw.py fetch      # .cache/raw/<point>_<season>.json
    poetry run python tools/calibrate/raw.py cells      # .cache/raw/cells.json
    poetry run python tools/calibrate/raw.py hrrr       # HRRR day-ahead forecasts (previous-runs archive)
"""

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hindcast  # noqa: E402

HERE = Path(__file__).resolve().parent
RAW = hindcast.CACHE / "raw"
URL = hindcast.URL
MODELS = ("ncep_hrrr_conus", "gfs_global", "ecmwf_ifs", "gem_regional", "gem_global")
HOURLY = "precipitation,temperature_2m,relative_humidity_2m"
SEASONS = hindcast.SEASONS


def points() -> dict:
    """{key: (lat, lon, elevation m)}: resorts at mid-mountain, SNOTEL sites at the station."""
    pts = {r.name: (r.latitude, r.longitude, hindcast.elevation_m(r, 0.5)) for r in hindcast.resorts()}
    for sid, s in json.loads((HERE / "snotel_sites.json").read_text())["stations"].items():
        pts[sid] = (s["lat"], s["lon"], round(s["elev_m"]))
    return pts


def get(params: dict, url: str = URL) -> dict:
    for attempt in range(10):
        try:
            resp = requests.get(url, params=params, timeout=180)
        except (requests.ConnectionError, requests.Timeout):
            time.sleep(5 * (attempt + 1))
            continue
        if resp.status_code == 429 or "limit" in resp.text[:300].lower():
            print("rate limited, waiting", resp.text[:120], flush=True)
            time.sleep(70 * (attempt + 1))
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("gave up")


def path(key: str, season: int) -> Path:
    return RAW / f"{key.replace(' ', '_')}_{season}.json"


def fetch(workers: int = 4) -> None:
    """The archive takes ~40 s to assemble a five-model season, so run a few requests at once."""
    RAW.mkdir(parents=True, exist_ok=True)
    jobs = [(key, season, pt) for key, pt in points().items() for season in SEASONS
            if not path(key, season).exists()]

    def one(job):
        key, season, (lat, lon, elev) = job
        data = get(dict(latitude=lat, longitude=lon, elevation=elev, timezone="auto",
                        start_date=f"{season}-11-01", end_date=f"{season + 1}-04-30",
                        hourly=HOURLY, models=",".join(MODELS)))
        tmp = path(key, season).with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(path(key, season))
        print("fetched", key, season, flush=True)

    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(one, jobs))


PREVIOUS_RUNS = "https://previous-runs-api.open-meteo.com/v1/forecast"
HRRR_SEASONS = (2024, 2025)  # previous-runs archive starts in 2024


def hrrr_path(key: str, season: int) -> Path:
    return RAW / f"{key.replace(' ', '_')}_{season}_hrrr1.json"


def hrrr(workers: int = 4) -> None:
    """HRRR as it was actually forecast one day ahead (previous-runs archive), US resorts.

    The historical-forecast archive stitches HRRR's first forecast hours, before its
    precipitation has spun up: about half of what the same model forecasts a day ahead. The
    day-ahead values are what the live forecast serves, so those are the ones to calibrate on.
    """
    us = {r.name for r in hindcast.resorts() if r.country == "US"}
    jobs = [(key, season, pt) for key, pt in points().items() if key in us for season in HRRR_SEASONS
            if not hrrr_path(key, season).exists()]
    fields = [f"{f}_previous_day1" for f in HOURLY.split(",")]

    def one(job):
        key, season, (lat, lon, elev) = job
        data = get(dict(latitude=lat, longitude=lon, elevation=elev, timezone="auto",
                        start_date=f"{season}-11-01", end_date=f"{season + 1}-04-30",
                        hourly=",".join(fields), models="ncep_hrrr_conus"), url=PREVIOUS_RUNS)
        hrrr_path(key, season).write_text(json.dumps(data))
        print("fetched HRRR day-1", key, season, flush=True)

    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(one, jobs))


def cells(workers: int = 4) -> None:
    """Terrain height and centre of the grid cell each model serves for each point."""
    out_path = RAW / "cells.json"
    out = json.loads(out_path.read_text()) if out_path.exists() else {}
    day = dict(start_date="2024-01-10", end_date="2024-01-10", hourly="temperature_2m", timezone="UTC")

    def one(item):
        key, (lat, lon, elev) = item
        row = dict(out.get(key, {}))
        for model in MODELS:
            if model in row:
                continue
            picked = get(dict(day, latitude=lat, longitude=lon, elevation=elev, models=model))
            raw = get(dict(day, latitude=picked["latitude"], longitude=picked["longitude"],
                           elevation="nan", cell_selection="nearest", models=model))
            row[model] = dict(lat=raw["latitude"], lon=raw["longitude"], elev_m=raw["elevation"])
        print(key, {m: row[m]["elev_m"] for m in MODELS}, flush=True)
        return key, row

    with ThreadPoolExecutor(workers) as pool:
        for key, row in pool.map(one, points().items()):
            out[key] = row
            out_path.write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    {"fetch": fetch, "cells": cells, "hrrr": hrrr}[sys.argv[1]]()
