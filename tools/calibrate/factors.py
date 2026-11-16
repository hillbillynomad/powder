"""Per-model, per-region snowfall bias factors from the hindcast (model output statistics).

    poetry run python tools/calibrate/factors.py            # score with leave-one-resort-out CV
    poetry run python tools/calibrate/factors.py --write    # also write powder/data/snow_calibration.json

Every model's season snowfall (the app's method: mid-mountain, temperature snow ratio) is compared
with resort-reported totals on complete seasons. A region's factor for a model is the geometric
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
import hindcast  # noqa: E402
from reported import complete  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "powder" / "data" / "snow_calibration.json"
# hindcast model -> app provider name
PROVIDERS = {"best_match": "Open-Meteo", "ecmwf_ifs": "ECMWF", "gem_seamless": "GEM"}
MIN_RESORTS = 2  # a region needs this many other resorts to get its own factor


def region_key(r) -> str:
    return f"{r.country}-{r.state}" if r.state else r.country


RATIO = None  # snow-ratio function for season_totals (None = the app's snow_ratio)


def ratios() -> dict:
    """{model: {resort name: (region key, display region, log(reported / model))}}"""
    out = {m: {} for m in PROVIDERS}
    for r in hindcast.resorts():
        if not hindcast.cache_path(r, 0.5).exists():
            continue
        data = hindcast.merged(r, 0.5)
        rep = hindcast.REPORTED[r.name]
        seasons = [s for s in hindcast.SEASONS if complete(rep, str(s))]
        for m in PROVIDERS:
            tot = (hindcast.season_totals(data, models=(m,)) if RATIO is None
                   else rate_totals(data, m, RATIO))
            if not tot or not seasons:
                continue
            model_in = sum(tot[s] for s in seasons)
            if model_in > 0:
                out[m][r.name] = (region_key(r), hindcast.region(r),
                                  math.log(sum(rep[str(s)][0] for s in seasons) / model_in))
    return out


def rate_totals(data: dict, model: str, params) -> dict:
    """Season totals with a temperature x storm-rate ratio (optimize.py's kuchera form)."""
    import numpy as np
    import optimize
    optimize.FORM = "kuchera"
    out = {}
    for s in hindcast.SEASONS:
        arrs = optimize.arrays(data, (model,), [s])
        out[s] = sum(float((w * optimize.ratio(params, t, r)).sum()) for w, t, r, _ in arrs) / 25.4
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
        table = {"_doc": "Snowfall bias factors per provider: multiply that provider's snowfall by "
                         "regions[country-state] (or default). Fitted by tools/calibrate/factors.py "
                         "against resort-reported season totals, 2022-23 to 2025-26."}
        for m, rows in rat.items():
            regions, glob = fit(rows)
            table[PROVIDERS[m]] = {"default": round(math.exp(glob), 3),
                                   "regions": {k: round(math.exp(v), 3) for k, v in sorted(regions.items())}}
        OUT.write_text(json.dumps(table, indent=2) + "\n")
        print(f"wrote {OUT}")


if __name__ == "__main__":
    for a in sys.argv[1:]:
        if a.startswith("--ratio="):
            RATIO = tuple(float(x) for x in a.split("=", 1)[1].split(","))
    main("--write" in sys.argv)
