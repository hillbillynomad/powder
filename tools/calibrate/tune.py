"""Grid-search the shared snowfall settings against reported season totals.

    poetry run python tools/calibrate/tune.py [fraction ...]

For each cached elevation fraction, tries snow-ratio pivots / caps and an overall precipitation
multiplier, and prints the settings with the best share of resorts within 20% of reported.
"""

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hindcast  # noqa: E402


def make_ratio(pivot_k: float, base: float, cold: float, warm: float, lo: float, hi: float, mult: float):
    def ratio(temp_c):
        if temp_c is None:
            return 7.0 * mult
        t = temp_c + 273.15
        r = base + (warm * (pivot_k - t) if t > pivot_k else cold * (pivot_k - t))
        return min(max(r, lo), hi) * mult
    return ratio


def main(fractions):
    results = []
    for fraction, base, cold, warm, hi, mult in itertools.product(
        fractions, (10, 12), (1.0, 0.5), (2.0,), (12, 15, 18), (0.8, 0.9, 1.0, 1.1, 1.2, 1.35, 1.5),
    ):
        ratio = make_ratio(271.16, base, cold, warm, 7.0, hi, mult)
        s = hindcast.score(fraction, ratio, quiet=True)
        if not s:
            continue
        worst_region_bias = max(abs(v["bias"]) for k, v in s.items() if k != "ALL")
        results.append((s["ALL"]["within20"], -s["ALL"]["mape"], -worst_region_bias,
                        dict(fraction=fraction, base=base, cold=cold, hi=hi, mult=mult), s))
    results.sort(key=lambda x: (x[0], x[1]), reverse=True)
    for within, nmape, nbias, params, s in results[:12]:
        regions = "  ".join(f"{k} {v['bias']:+.0%}" for k, v in s.items() if k != "ALL")
        print(f"within20 {within:.0%}  mape {-nmape:.0%}  worst region bias {-nbias:.0%}  {params}\n    {regions}")


if __name__ == "__main__":
    main([float(a) for a in sys.argv[1:]] or [0.5])
