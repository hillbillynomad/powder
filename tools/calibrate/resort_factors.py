"""Per-resort correction on top of the shared model, scored leave-one-season-out.

    poetry run python tools/calibrate/resort_factors.py            # score
    poetry run python tools/calibrate/resort_factors.py --write    # add "resorts" to snow_calibration.json

Each resort measures and reports snow its own way (plot elevation, exposure, how often it
reports), so the shared model is off by a steady amount per resort: Bear Valley high every
season, Brighton low every season. The resort's factor is the median over its complete seasons
of reported / model, where model is the app's calibrated provider average
(open_meteo_common.daily_snowfall). Resorts without history keep the regional / default factors.

Scoring holds out one season at a time: the factor is fitted on the resort's other seasons and
predicts the held-out one. The regional factor cancels out of that prediction, so nothing about
the held-out season leaks in.
"""

import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hindcast  # noqa: E402
from factors import PROVIDERS  # noqa: E402
from reported import complete  # noqa: E402

from powder.providers import open_meteo_common as omc  # noqa: E402

MIN_SEASONS = 1  # other seasons needed to fit a resort factor


def season_model(r) -> dict[int, float]:
    """Calibrated provider average (inches) per Nov-Apr season, the app's way, no resort factor."""
    h = hindcast.merged(r, 0.5)["hourly"]
    per_day: dict = {}
    for model, provider in PROVIDERS.items():
        if not any(h.get(f"snowfall_{model}") or []):
            continue
        single = {"hourly": {"time": h["time"], "snowfall": h[f"snowfall_{model}"],
                             "temperature_2m": h[f"temperature_2m_{model}"]}}
        for d in omc.daily_snowfall(single, provider, r, use_resort_factor=False):
            per_day.setdefault(d.date, []).append(d.snowfall_inches)
    return {s: sum(statistics.mean(v) for d, v in per_day.items() if hindcast.in_season(d, s))
            for s in hindcast.SEASONS}


def table() -> list:
    rows = []
    for r in hindcast.resorts():
        if not hindcast.cache_path(r, 0.5).exists():
            continue
        rep = hindcast.REPORTED[r.name]
        seasons = [s for s in hindcast.SEASONS if complete(rep, str(s))]
        model = season_model(r)
        logs = {s: math.log(rep[str(s)][0] / model[s]) for s in seasons if model.get(s, 0) > 0}
        rows.append((hindcast.region(r), r.name, logs, model, rep))
    return rows


def main(write: bool):
    rows = table()
    season_errs, resort_errs = [], []
    for reg, name, logs, model, rep in rows:
        pred_tot = rep_tot = 0.0
        for s, lr in logs.items():
            others = [v for k, v in logs.items() if k != s]
            if len(others) < MIN_SEASONS:
                continue
            pred = model[s] * math.exp(statistics.fmean(others))
            season_errs.append((reg, name, s, pred / rep[str(s)][0] - 1))
            pred_tot += pred
            rep_tot += rep[str(s)][0]
        if rep_tot:
            resort_errs.append((reg, name, pred_tot / rep_tot - 1))
    print("leave-one-season-out, per resort (held-out seasons pooled):")
    for reg, name, e in sorted(resort_errs):
        print(f"  {reg:10s} {name:26s} {e:+.0%}")
    for label, errs, idx in (("resort (pooled seasons)", resort_errs, 2), ("single season", season_errs, 3)):
        print(f"\nby {label}:")
        for reg in sorted({e[0] for e in errs}) + ["ALL"]:
            es = [e[idx] for e in errs if reg in ("ALL", e[0])]
            print(f"  == {reg:10s} n={len(es):3d} median bias {statistics.median(es):+.0%}  median |err| "
                  f"{statistics.median(map(abs, es)):.0%}  within 20% {sum(abs(x) <= .2 for x in es) / len(es):.0%}")
    if write:
        cal = json.loads(omc.CALIBRATION_FILE.read_text())
        cal["resorts"] = {name: round(math.exp(statistics.fmean(logs.values())), 3)
                          for _, name, logs, _, _ in sorted(rows, key=lambda x: x[1]) if logs}
        omc.CALIBRATION_FILE.write_text(json.dumps(cal, indent=2, ensure_ascii=False) + "\n")
        print(f"\nwrote {len(cal['resorts'])} resort factors to {omc.CALIBRATION_FILE}")


if __name__ == "__main__":
    main("--write" in sys.argv)
