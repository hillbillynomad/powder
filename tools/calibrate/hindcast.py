"""Hindcast our snowfall method against resort-reported season totals.

Fetches archived model runs (Open-Meteo historical-forecast API: the same models the app uses,
stitched from their short-range forecasts) for every resort in reported_seasons.json at a chosen
elevation, rebuilds season snowfall with the app's snow-ratio maths, and scores it against what
the resorts reported.

    poetry run python tools/calibrate/hindcast.py fetch [fraction ...]   # cache raw hourly data
    poetry run python tools/calibrate/hindcast.py score [fraction]       # print the comparison

`fraction` is where between base (0) and summit (1) the forecast is made; 0.5 = mid-mountain.
Raw responses are cached in tools/calibrate/.cache/ (gitignored) so scoring is offline.
"""

import json
import statistics
import sys
import time
from datetime import date, datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from powder.providers.open_meteo_common import OPEN_METEO_SLR, snow_ratio  # noqa: E402
from powder.resorts import load_resorts  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reported import complete  # noqa: E402

HERE = Path(__file__).resolve().parent
CACHE = HERE / ".cache"
REPORTED = json.loads((HERE / "reported_seasons.json").read_text())
URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
MODELS = ("best_match", "ecmwf_ifs")  # stand-ins for the app's Open-Meteo + ECMWF providers
SEASONS = (2022, 2023, 2024, 2025)
# OnTheSnow totals are sums of the daily reports a resort sent in; seasons with far fewer
# snowfall days than the resort's usual are incomplete and skipped (reported.complete).
SCORED_SEASONS = SEASONS
START, END = "2022-10-01", "2026-05-31"
SEASON_MONTHS = ((11, 1), (4, 30))  # Nov 1 - Apr 30
REGION = {"CA": "California", "CO": "Colorado", "UT": "Utah", "WY": "Wyoming", "MT": "Montana"}


def resorts():
    by_name = {r.name: r for r in load_resorts()}
    return [by_name[n] for n in REPORTED if not n.startswith("_") and n in by_name]


def region(r) -> str:
    return "Canada" if r.country == "CA" else REGION.get(r.state, r.state)


def elevation_m(r, fraction: float) -> int:
    peak = r.elevation_peak_ft or r.elevation_base_ft
    return round((r.elevation_base_ft + fraction * (peak - r.elevation_base_ft)) / 3.28084)


def cache_path(r, fraction: float, tag: str = "") -> Path:
    return CACHE / f"{r.name.replace(' ', '_')}_{fraction:.2f}{tag}.json"


def merged(r, fraction: float) -> dict:
    """Base cache merged with any extra-model caches (e.g. `_gem`) for the same resort."""
    data = json.loads(cache_path(r, fraction).read_text())
    for extra in CACHE.glob(f"{r.name.replace(' ', '_')}_{fraction:.2f}_*.json"):
        model = TAG_MODELS[extra.stem.rsplit("_", 1)[1]]
        for k, v in json.loads(extra.read_text())["hourly"].items():
            if k != "time":
                # a single-model response has no `_<model>` suffix on its fields
                data["hourly"][k if k.endswith(model) else f"{k}_{model}"] = v
    return data


TAG_MODELS = {"gem": "gem_seamless", "icon": "icon_seamless"}


def fetch(fractions: list[float], models=MODELS, tag: str = "") -> None:
    CACHE.mkdir(exist_ok=True)
    for fraction in fractions:
        for r in resorts():
            path = cache_path(r, fraction, tag)
            if path.exists():
                continue
            for attempt in range(5):
                try:
                    resp = _get(r, fraction, models)
                except requests.ConnectionError as e:
                    print(f"network error ({r.name}): {type(e).__name__}, retrying", flush=True)
                    time.sleep(30 * (attempt + 1))
                    continue
                if resp.status_code == 429 or "limit" in resp.text[:200].lower():
                    print(f"rate limited, waiting ({r.name})", flush=True)
                    time.sleep(70 * (attempt + 1))
                    continue
                resp.raise_for_status()
                path.write_text(resp.text)
                print(f"fetched {r.name} @ {fraction}", flush=True)
                time.sleep(2)
                break


def _get(r, fraction: float, models):
    return requests.get(URL, params={
        "latitude": r.latitude, "longitude": r.longitude,
        "elevation": elevation_m(r, fraction),
        "start_date": START, "end_date": END,
        "hourly": "snowfall,temperature_2m",
        "models": ",".join(models), "timezone": r.timezone,
    }, timeout=120)


def in_season(day: date, season: int) -> bool:
    (m0, d0), (m1, d1) = SEASON_MONTHS
    return date(season, m0, d0) <= day <= date(season + 1, m1, d1)


def season_totals(data: dict, ratio=snow_ratio, models=MODELS) -> dict[int, float]:
    """Mean over models of season snowfall (inches), the app's way: water x temperature ratio."""
    h = data["hourly"]
    days = [datetime.strptime(t[:10], "%Y-%m-%d").date() for t in h["time"]]
    per_model = []
    for m in models:
        snow, temp = h.get(f"snowfall_{m}") or [], h.get(f"temperature_2m_{m}") or []
        tot = {s: 0.0 for s in SEASONS}
        for i, day in enumerate(days):
            cm = snow[i] if i < len(snow) else None
            if not cm:
                continue
            season = day.year if day.month >= 7 else day.year - 1
            if season in tot and in_season(day, season):
                water_in = cm * 10 / OPEN_METEO_SLR / 25.4
                tot[season] += water_in * ratio(temp[i] if i < len(temp) else None)
        if any(tot.values()):
            per_model.append(tot)
    return {s: statistics.mean(t[s] for t in per_model) for s in SEASONS} if per_model else {}


def score(fraction: float, ratio=snow_ratio, seasons=SCORED_SEASONS, quiet=False, models=MODELS) -> dict:
    rows = []
    for r in resorts():
        path = cache_path(r, fraction)
        if not path.exists():
            continue
        model = season_totals(merged(r, fraction), ratio, models)
        rep = REPORTED[r.name]
        pairs = [(model[s], rep[str(s)][0]) for s in seasons
                 if model and complete(rep, str(s))]
        if not pairs:
            continue
        m, o = sum(p[0] for p in pairs), sum(p[1] for p in pairs)
        rows.append((region(r), r.name, m, o, m / o - 1, [p[0] / p[1] - 1 for p in pairs]))
    if not quiet:
        print(f"\nfraction {fraction}: model vs reported, {'+'.join(map(str, seasons))} seasons (Nov-Apr)")
        for reg, name, m, o, err, per in sorted(rows):
            print(f"  {reg:10s} {name:26s} model {m:6.0f}  reported {o:6.0f}  {err:+6.0%}   "
                  + " ".join(f"{e:+.0%}" for e in per))
    summary = {}
    for reg in sorted({x[0] for x in rows}) + ["ALL"]:
        errs = [x[4] for x in rows if reg in ("ALL", x[0])]
        summary[reg] = {
            "n": len(errs),
            "bias": statistics.median(errs),
            "mape": statistics.median(abs(e) for e in errs),
            "within20": sum(abs(e) <= 0.2 for e in errs) / len(errs),
        }
        if not quiet:
            s = summary[reg]
            print(f"  == {reg:10s} n={s['n']:2d} median bias {s['bias']:+.0%}  median |err| {s['mape']:.0%}"
                  f"  within 20%: {s['within20']:.0%}")
    return summary


if __name__ == "__main__":
    cmd = sys.argv[1]
    args = [float(a) for a in sys.argv[2:] if not a.startswith("--models=")]
    picked = [a.split("=", 1)[1].split(",") for a in sys.argv[2:] if a.startswith("--models=")]
    if cmd == "fetch":
        if picked:
            fetch(args or [0.5], tuple(picked[0]), "_" + "_".join(m.split("_")[0] for m in picked[0]))
        else:
            fetch(args or [0.5])
    else:
        score(args[0] if args else 0.5, models=tuple(picked[0]) if picked else MODELS)
