"""Run the app's own snowfall code over the hindcast and score it against reported totals.

    poetry run python tools/calibrate/verify.py

Feeds each pinned model's raw archive (raw.py) through `open_meteo_common.daily_snowfall` (the
exact code providers use, shipped calibration and resort factors included), averages the
providers like the app, sums complete Nov-Apr seasons and compares with resort reports. This is
in-sample; factors.py and resort_factors.py report the held-out numbers.
"""

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import appmodel  # noqa: E402
import hindcast  # noqa: E402
from appmodel import PROVIDERS  # noqa: E402
from reported import complete  # noqa: E402


def main():
    rows = []
    for r in hindcast.resorts():
        tot = {m: appmodel.season_totals(r.name, r, m, source=p, use_resort_factor=True)
               for m, p in PROVIDERS.items()}
        rep = hindcast.REPORTED[r.name]
        seasons = [s for s in hindcast.SEASONS if complete(rep, str(s)) and all(s in t for t in tot.values())]
        if seasons:
            model_in = sum(statistics.mean(t[s] for t in tot.values()) for s in seasons)
            rows.append((hindcast.region(r), r.name, model_in / sum(rep[str(s)][0] for s in seasons) - 1))
    for reg in sorted({x[0] for x in rows}) + ["ALL"]:
        es = [x[2] for x in rows if reg in ("ALL", x[0])]
        print(f"== {reg:10s} n={len(es):2d} median bias {statistics.median(es):+.0%}  median |err| "
              f"{statistics.median(map(abs, es)):.0%}  within 20% {sum(abs(e) <= .2 for e in es) / len(es):.0%}")


if __name__ == "__main__":
    main()
