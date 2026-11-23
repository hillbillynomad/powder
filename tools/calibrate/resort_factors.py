"""Per-resort correction on top of the shared model: fitted small, scored on seasons it never saw.

    poetry run python tools/calibrate/resort_factors.py            # score (and the out-of-time gate)
    poetry run python tools/calibrate/resort_factors.py --write    # add "resorts" to snow_calibration.json

Each resort measures and reports snow its own way (plot elevation, exposure, how often it clears
the board), and the 9-25 km models miss terrain at some resorts, so the shared model is off by a
steady amount per resort. A resort's factor is the mean over its complete seasons of
log(reported / model), where model is the app's calibrated provider average (appmodel.py, the
exact provider code), then:

* only resorts with MIN_SEASONS complete seasons get one;
* it is shrunk toward 1 by n / (n + SHRINK_K) for n seasons: about half of a factor fitted on two
  seasons is noise (factors from 2022-24 and 2024-26 correlate r = 0.66);
* it is capped to [MIN_FACTOR, MAX_FACTOR]: part of a factor absorbs the snow ratio's
  temperature error at that site (against NWS observers, a whole-winter site factor misses by
  30-60% in cold spells), so a large factor amplifies the error when the weather changes.

Scores: leave-one-season-out (the factor fitted on the resort's other seasons), and the gate to
ship on, out-of-time: region and resort factors fitted on 2022-23 + 2023-24 only, scored on
2024-25 + 2025-26. Refit once a year, in spring, on the latest seasons, and ship only if the
out-of-time score holds. Don't tune on a few weeks of weather.
"""

import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import appmodel  # noqa: E402
import factors  # noqa: E402
import hindcast  # noqa: E402
from appmodel import PROVIDERS  # noqa: E402
from reported import complete  # noqa: E402

from powder.providers import open_meteo_common as omc  # noqa: E402

MIN_SEASONS = 2
SHRINK_K = 1.0
MIN_FACTOR, MAX_FACTOR = 0.6, 1.6
EARLY, LATE = (2022, 2023), (2024, 2025)


def resort_factor(logs: list[float]) -> float:
    """Shrunk, capped factor from per-season log(reported / model); 1 with too little history."""
    if len(logs) < MIN_SEASONS:
        return 1.0
    f = math.exp(statistics.fmean(logs) * len(logs) / (len(logs) + SHRINK_K))
    return min(max(f, MIN_FACTOR), MAX_FACTOR)


def per_model(r) -> dict[str, dict[int, float]]:
    """Uncalibrated season snowfall per underlying model."""
    return {m: appmodel.season_totals(r.name, r, m) for m in PROVIDERS}


def blend(raw_tot: dict, factor: dict, season: int) -> float | None:
    vals = [raw_tot[m][season] * factor[m] for m in PROVIDERS if season in raw_tot[m]]
    return statistics.mean(vals) if vals else None


def shipped_factors(r) -> dict[str, float]:
    return {m: omc.calibration_factor(p, r) for m, p in PROVIDERS.items()}


def table():
    rows = []
    for r in hindcast.resorts():
        rep = hindcast.REPORTED[r.name]
        rows.append((r, rep, per_model(r)))
    return rows


def summary(errs) -> str:
    a = [abs(e) for e in errs]
    return (f"median |err| {statistics.median(a):4.0%}  within 20% {sum(x <= .2 for x in a) / len(a):4.0%}"
            f"  bias {statistics.median(errs):+.0%}  (n={len(a)})")


def loso(rows):
    """Leave-one-season-out, with the shipped region factors."""
    none_e, with_e = [], []
    for r, rep, tot in rows:
        f = shipped_factors(r)
        seasons = [s for s in hindcast.SEASONS if complete(rep, str(s))]
        model = {s: blend(tot, f, s) for s in seasons}
        logs = {s: math.log(rep[str(s)][0] / v) for s, v in model.items() if v}
        for s, lr in logs.items():
            k = resort_factor([v for o, v in logs.items() if o != s])
            none_e.append(model[s] / rep[str(s)][0] - 1)
            with_e.append(model[s] * k / rep[str(s)][0] - 1)
    return none_e, with_e


def out_of_time(rows):
    """Everything fitted on EARLY seasons only, scored on LATE seasons."""
    rat = factors.ratios(seasons=EARLY)
    fitted = {m: factors.fit(rat[m]) for m in PROVIDERS}  # (regions, global) per model
    none_e, with_e = [], []
    for r, rep, tot in rows:
        key = factors.region_key(r)
        f = {m: math.exp(fitted[m][0].get(key, fitted[m][1])) for m in PROVIDERS}
        logs = []
        for s in EARLY:
            v = blend(tot, f, s) if complete(rep, str(s)) else None
            if v:
                logs.append(math.log(rep[str(s)][0] / v))
        k = resort_factor(logs)
        for s in LATE:
            v = blend(tot, f, s) if complete(rep, str(s)) else None
            if v:
                none_e.append(v / rep[str(s)][0] - 1)
                with_e.append(v * k / rep[str(s)][0] - 1)
    return none_e, with_e


def main(write: bool):
    rows = table()
    print(f"resort factors: >= {MIN_SEASONS} seasons, shrink n/(n+{SHRINK_K:g}), cap {MIN_FACTOR}-{MAX_FACTOR}")
    n, w = loso(rows)
    print("leave-one-season-out, per season:")
    print(f"  region factors only   {summary(n)}")
    print(f"  + resort factor       {summary(w)}")
    n, w = out_of_time(rows)
    print(f"out of time (fit {'+'.join(map(str, EARLY))}, score {'+'.join(map(str, LATE))}), per season:")
    print(f"  region factors only   {summary(n)}")
    print(f"  + resort factor       {summary(w)}")
    if write:
        cal = json.loads(omc.CALIBRATION_FILE.read_text())
        out = {}
        for r, rep, tot in sorted(rows, key=lambda x: x[0].name):
            f = shipped_factors(r)
            logs = []
            for s in hindcast.SEASONS:
                v = blend(tot, f, s) if complete(rep, str(s)) else None
                if v:
                    logs.append(math.log(rep[str(s)][0] / v))
            k = resort_factor(logs)
            if k != 1.0:
                out[r.name] = round(k, 3)
        cal["resorts"] = out
        omc.CALIBRATION_FILE.write_text(json.dumps(cal, indent=2, ensure_ascii=False) + "\n")
        print(f"\nwrote {len(out)} resort factors ({min(out.values()):.2f}-{max(out.values()):.2f}) "
              f"to {omc.CALIBRATION_FILE}")


if __name__ == "__main__":
    main("--write" in sys.argv)
