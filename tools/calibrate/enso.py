"""Do resort factors hold across ENSO phases? Each season is predicted with factors fitted on the
other three (2023-24 was a strong El Nino, the rest La Nina).

    poetry run python tools/calibrate/enso.py
"""
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import model2  # noqa: E402
ENSO = {2022: "La Nina", 2023: "El Nino (strong)", 2024: "La Nina (weak)", 2025: "La Nina (weak)"}
models = model2.LONG
rows = model2.table(models, 0.5, "air")
no_hist = model2.score(rows, models, "none", True)            # region factors only
with_rf = model2.score(rows, models, "none", True, True)      # + resort factor fitted on the OTHER seasons
def med(xs): return statistics.median(xs) if xs else float("nan")
print("Per held-out season (resort factor fitted on the other three seasons):")
print(f"  {'season':8s} {'ENSO':17s} {'n':>3s} {'region only |err|':>18s} {'+ resort factor |err|':>22s} {'within 20%':>10s}")
for s in sorted(ENSO):
    a = [abs(e[3]) for e in no_hist if e[2] == s]; b = [abs(e[3]) for e in with_rf if e[2] == s]
    print(f"  {s}-{str(s+1)[2:]:4s} {ENSO[s]:17s} {len(b):3d} {med(a):18.0%} {med(b):22.0%} {sum(x <= .2 for x in b)/len(b):10.0%}")
print("\nSigned bias with resort factor (median of predicted / reported - 1), by region and season:")
regs = sorted({e[0] for e in with_rf})
print(f"  {'region':11s} " + " ".join(f"{s}-{str(s+1)[2:]:>8s}" for s in sorted(ENSO)))
for reg in regs:
    cells = []
    for s in sorted(ENSO):
        v = [e[3] for e in with_rf if e[0] == reg and e[2] == s]
        cells.append(f"{med(v):+11.0%} ({len(v)})" if v else f"{'-':>15s}")
    print(f"  {reg:11s} " + " ".join(cells))
# how much does each resort's factor move when the El Nino year is included vs excluded
moves = []
for row in rows:
    pred = model2.predict(row, models, *model2.fit(rows, models, "none", True, exclude=row["name"]))
    if 2023 not in pred or len(pred) < 3: continue
    others = [math.log(row["rep"][o] / pred[o]) for o in pred if o != 2023]
    nino = math.log(row["rep"][2023] / pred[2023])
    moves.append((row["region"], row["name"], math.exp(statistics.fmean(others)), math.exp(nino)))
d = np.array([math.log(n / o) for _, _, o, n in moves])
print(f"\nEl Nino season's own factor vs factor from the La Nina seasons ({len(moves)} resorts):")
print(f"  median change {math.exp(np.median(d)) - 1:+.0%}, typical size {np.median(np.abs(d)):.2f} log (~{math.exp(np.median(np.abs(d))) - 1:.0%}),"
      f" over 25%: {sum(abs(x) > math.log(1.25) for x in d)} resorts")
for reg, name, o, n in sorted(moves, key=lambda x: -abs(math.log(x[3] / x[2])))[:8]:
    print(f"    {reg:10s} {name:26s} La Nina factor x{o:.2f}  El Nino season x{n:.2f}")
# compare: same statistic for a La Nina season held out
for s in (2022, 2024, 2025):
    dd = []
    for row in rows:
        pred = model2.predict(row, models, *model2.fit(rows, models, "none", True, exclude=row["name"]))
        if s not in pred or len(pred) < 3: continue
        others = [math.log(row["rep"][o] / pred[o]) for o in pred if o != s]
        dd.append(math.log(row["rep"][s] / pred[s]) - statistics.fmean(others))
    print(f"  for comparison, {s}-{str(s+1)[2:]} ({ENSO[s]}) vs the other seasons: typical size {np.median(np.abs(dd)):.2f} log, over 25%: {sum(abs(x) > math.log(1.25) for x in dd)} of {len(dd)}")
