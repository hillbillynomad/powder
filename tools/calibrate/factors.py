"""Per-model, per-region snowfall bias factors from the hindcast (model output statistics).

    poetry run python tools/calibrate/factors.py            # score with leave-one-resort-out CV
    poetry run python tools/calibrate/factors.py --write    # also write powder/data/snow_calibration.json

Every model's season snowfall (the app's own `daily_snowfall` on the raw archive of the model the
provider pins, appmodel.py) is compared with resort-reported totals on complete seasons. A region's factor for a model is the geometric
median of reported / model over its resorts; regions without enough resorts fall back to the
model's global factor, which is also what every resort outside the calibrated regions uses.

Scoring is leave-one-resort-out: each resort is predicted with factors fitted without it, so the
numbers show how the calibration does on a resort it has never seen.
"""

import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import appmodel  # noqa: E402
import hindcast  # noqa: E402
from appmodel import PROVIDERS  # noqa: E402  (underlying model -> app provider name)
from reported import complete  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "powder" / "data" / "snow_calibration.json"
MIN_RESORTS = 2  # a region needs this many other resorts to get its own factor


def region_key(r) -> str:
    return f"{r.country}-{r.state}" if r.state else r.country


def ratios(seasons=None) -> dict:
    """{model: {resort name: (region key, display region, log(reported / model))}} over the
    resort's complete seasons (optionally only those in `seasons`)."""
    out = {m: {} for m in PROVIDERS}
    for r in hindcast.resorts():
        rep = hindcast.REPORTED[r.name]
        use = [s for s in (seasons or hindcast.SEASONS) if complete(rep, str(s))]
        for m in PROVIDERS:
            tot = appmodel.season_totals(r.name, r, m)
            ss = [s for s in use if tot.get(s, 0) > 0]
            if ss:
                out[m][r.name] = (region_key(r), hindcast.region(r),
                                  math.log(sum(rep[str(s)][0] for s in ss) / sum(tot[s] for s in ss)))
    return out


def fit(rows: dict, exclude: str | None = None) -> tuple[dict, float]:
    """(per-region log factors, global log factor), leaving one resort out."""
    use = {n: v for n, v in rows.items() if n != exclude}
    glob = statistics.median(v[2] for v in use.values())
    regions = {}
    for key in {v[0] for v in use.values()}:
        vals = [v[2] for v in use.values() if v[0] == key]
        if len(vals) >= MIN_RESORTS:
            regions[key] = statistics.median(vals)
    return regions, glob


def main(write: bool):
    rat = ratios()
    names = sorted(set.intersection(*(set(v) for v in rat.values())))
    errs = []
    for name in names:
        preds, rep_log = [], None
        for m, rows in rat.items():
            key, disp, lr = rows[name]
            regions, glob = fit(rows, exclude=name)
            # calibrated model / reported = exp(factor) * model / reported = exp(factor - lr)
            preds.append(math.exp(regions.get(key, glob) - lr))
        errs.append((rat["ecmwf_ifs"][name][1], name, statistics.mean(preds) - 1))
    print("leave-one-resort-out, mean of calibrated models vs reported:")
    for disp, name, e in sorted(errs):
        print(f"  {disp:10s} {name:26s} {e:+.0%}")
    for disp in sorted({e[0] for e in errs}) + ["ALL"]:
        es = [e[2] for e in errs if disp in ("ALL", e[0])]
        print(f"  == {disp:10s} n={len(es):2d} median bias {statistics.median(es):+.0%}  median |err| "
              f"{statistics.median(map(abs, es)):.0%}  within 20% {sum(abs(x) <= .2 for x in es) / len(es):.0%}")
    if write:
        table = {"_doc": "Snowfall bias factors per provider (GFS global, ECMWF IFS, GEM global): "
                         "multiply that provider's snowfall by regions[country-state] (or default). "
                         "Fitted by tools/calibrate/factors.py against resort-reported season "
                         "totals, 2022-23 to 2025-26."}
        for m, rows in rat.items():
            regions, glob = fit(rows)
            table[PROVIDERS[m]] = {"default": round(math.exp(glob), 3),
                                   "regions": {k: round(math.exp(v), 3) for k, v in sorted(regions.items())}}
        OUT.write_text(json.dumps(table, indent=2) + "\n")
        print(f"wrote {OUT}")


if __name__ == "__main__":
    main("--write" in sys.argv)
