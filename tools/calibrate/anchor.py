"""Factors for regions without reported snowfall: tie GFS and GEM to ECMWF.

    poetry run python tools/calibrate/anchor.py fetch     # one season of hourly data, up to 3 resorts/country
    poetry run python tools/calibrate/anchor.py write     # add per-country factors to snow_calibration.json

ECMWF's global calibration factor against resort reports is ~1.0, so outside the calibrated
regions ECMWF is the anchor: for each country, GFS and GEM get the factor that makes their
season snowfall (the app's method) match ECMWF's ECMWF-default-scaled season snowfall, taken
as the median over that country's sampled resorts. Countries with calibrated regions (US, CA)
keep the reported-snowfall factors and their regions; a country with no sample uses the
provider default.
"""

import json
import math
import statistics
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import appmodel  # noqa: E402
import hindcast  # noqa: E402

from powder.providers import open_meteo_common as omc  # noqa: E402
from powder.resorts import load_resorts  # noqa: E402

CACHE = hindcast.CACHE / "anchor_v2"  # GFS global / ECMWF IFS / GEM global, precipitation-based
MODELS = appmodel.PROVIDERS
SKIP = {"US", "CA"}  # countries whose regions are keyed by state / province
PER_COUNTRY = 3
SEASONS = {"north": ("2024-11-01", "2025-04-30"), "south": ("2025-05-15", "2025-10-15")}


def region_key(r) -> str:
    """US / Canada by state or province (matching the reported-snowfall regions), else country."""
    return f"{r.country}-{r.state}" if r.country in SKIP and r.state else r.country


def calibrated() -> set:
    table = json.loads(omc.CALIBRATION_FILE.read_text())
    return {k for k in table["Open-Meteo"]["regions"] if "-" in k}


def sample():
    done = calibrated()
    by_region = defaultdict(list)
    for r in load_resorts():
        key = region_key(r)
        if key not in done and r.elevation_peak_ft:
            by_region[key].append(r)
    return {c: sorted(rs, key=lambda r: -(r.elevation_peak_ft - r.elevation_base_ft))[:PER_COUNTRY]
            for c, rs in by_region.items()}


def path(r) -> Path:
    return CACHE / f"{r.name.replace(' ', '_').replace('/', '-')}.json"


def fetch(workers: int = 3):
    CACHE.mkdir(parents=True, exist_ok=True)
    jobs = [(c, r) for c, rs in sample().items() for r in rs if not path(r).exists()]
    print(len(jobs), "resorts to fetch", flush=True)

    def one(job):
        country, r = job
        start, end = SEASONS["south" if r.latitude < 0 else "north"]
        for attempt in range(8):
            try:
                resp = requests.get(hindcast.URL, params={
                    "latitude": r.latitude, "longitude": r.longitude,
                    "elevation": omc.mid_mountain_m(r), "start_date": start, "end_date": end,
                    "hourly": omc.SNOW_HOURLY_FIELDS, "models": ",".join(MODELS),
                    "timezone": r.timezone}, timeout=180)
            except (requests.ConnectionError, requests.Timeout):
                time.sleep(10 * (attempt + 1))
                continue
            if resp.status_code == 429 or "limit" in resp.text[:300].lower():
                print("rate limited, waiting", resp.text[:100], flush=True)
                time.sleep(70 * (attempt + 1))
                continue
            resp.raise_for_status()
            path(r).write_text(resp.text)
            print(f"fetched {country} {r.name}", flush=True)
            return

    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(one, jobs))


def season_snow(data: dict, model: str, provider: str, resort) -> float:
    block = appmodel.single(data, model)
    if block is None:
        return 0.0
    return sum(d.snowfall_inches for d in omc.daily_snowfall(block, provider, None))


def write():
    table = json.loads(omc.CALIBRATION_FILE.read_text())
    ecmwf_default = table["ECMWF"]["default"]
    for country, rs in sorted(sample().items()):
        logs = defaultdict(list)
        for r in rs:
            if not path(r).exists():
                continue
            data = json.loads(path(r).read_text())
            # uncalibrated season totals (calibration off), so factors are relative to raw models
            ecmwf = season_snow(data, "ecmwf_ifs", "_raw", r) * ecmwf_default
            for model, provider in MODELS.items():
                if provider == "ECMWF":
                    continue
                other = season_snow(data, model, "_raw", r)
                if ecmwf > 5 and other > 5:
                    logs[provider].append(math.log(ecmwf / other))
        for provider, vals in logs.items():
            factor = round(math.exp(statistics.median(vals)), 3)
            table[provider]["regions"][country] = factor
            print(f"{country}: {provider} x{factor} (n={len(vals)})")
        if logs:
            table["ECMWF"]["regions"].setdefault(country, ecmwf_default)
    table["_doc"] = (table["_doc"].split(" Countries without")[0] +
                     " Countries without reported data (bare country codes) tie GFS and GEM to ECMWF's"
                     " season snowfall there (tools/calibrate/anchor.py).")
    omc.CALIBRATION_FILE.write_text(json.dumps(table, indent=2) + "\n")


if __name__ == "__main__":
    fetch() if sys.argv[1] == "fetch" else write()
