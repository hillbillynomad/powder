"""Run the app's own snowfall code over the hindcast and score it against reported totals.

    poetry run python tools/calibrate/verify.py

Feeds each archived model's hourly data through `open_meteo_common.daily_snowfall` (the exact
code providers use, shipped calibration included), averages the providers per day like the
app, sums complete Nov-Apr seasons and compares with resort reports. This is in-sample for the
calibration factors; factors.py reports the leave-one-resort-out numbers.
"""

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hindcast  # noqa: E402
from factors import PROVIDERS  # noqa: E402
from reported import complete  # noqa: E402

from powder.providers.open_meteo_common import daily_snowfall  # noqa: E402


def main():
    rows = []
    for r in hindcast.resorts():
        if not hindcast.cache_path(r, 0.5).exists():
            continue
        data = hindcast.merged(r, 0.5)
        h = data["hourly"]
        per_day: dict = {}
        for model, provider in PROVIDERS.items():
            if not any(h.get(f"snowfall_{model}") or []):
                continue
            single = {"hourly": {"time": h["time"], "snowfall": h[f"snowfall_{model}"],
                                 "temperature_2m": h[f"temperature_2m_{model}"]}}
            for d in daily_snowfall(single, provider, r):
                per_day.setdefault(d.date, []).append(d.snowfall_inches)
        rep = hindcast.REPORTED[r.name]
        seasons = [s for s in hindcast.SEASONS if complete(rep, str(s))]
        model_in = sum(statistics.mean(v) for d, v in per_day.items()
                       for s in seasons if hindcast.in_season(d, s))
        if seasons:
            rows.append((hindcast.region(r), r.name, model_in / sum(rep[str(s)][0] for s in seasons) - 1))
    for reg in sorted({x[0] for x in rows}) + ["ALL"]:
        es = [x[2] for x in rows if reg in ("ALL", x[0])]
        print(f"== {reg:10s} n={len(es):2d} median bias {statistics.median(es):+.0%}  median |err| "
              f"{statistics.median(map(abs, es)):.0%}  within 20% {sum(abs(e) <= .2 for e in es) / len(es):.0%}")


if __name__ == "__main__":
    main()
