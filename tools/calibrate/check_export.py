"""Sanity-check powder/web/data/forecasts.json after a model change.

    poetry run python tools/calibrate/check_export.py [start YYYY-MM-DD] [days]

Prints the resorts with the biggest totals for the window, any day above 60" or with sources
disagreeing more than 4x, and the window total per resort for a list of names.
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "powder" / "web" / "data" / "forecasts.json"


def main(start: date, days: int, names: list[str]):
    resorts = json.loads(DATA.read_text())["resorts"]
    end = start + timedelta(days=days - 1)
    totals, flags = [], []
    for r in resorts:
        tot = 0.0
        for d in r["daily_forecasts"]:
            day = date.fromisoformat(d["date"])
            if start <= day <= end:
                tot += d["avg_inches"]
            vals = [v for v in d["sources"].values() if v is not None]
            if d["avg_inches"] > 60 or (len(vals) > 1 and max(vals) > 8 and max(vals) > 4 * max(min(vals), 0.5)):
                flags.append(f"{r['name']} {d['date']} {d['sources']}")
        totals.append((tot, r["name"], r["country"], r.get("region")))
    totals.sort(reverse=True)
    print(f"{len(resorts)} resorts; top {start}..{end} totals:")
    for t, n, c, reg in totals[:12]:
        print(f"  {t:6.1f}  {n} ({reg}, {c})")
    print(f"\n{len(flags)} flagged days (avg > 60\" or sources > 4x apart):")
    for f in flags[:25]:
        print("  " + f)
    for n in names:
        match = [t for t in totals if t[1] == n]
        if match:
            print(f"  {n:22s} {match[0][0]:.1f}")


if __name__ == "__main__":
    args = sys.argv[1:]
    s = date.fromisoformat(args[0]) if args else date.today()
    d = int(args[1]) if len(args) > 1 else 7
    main(s, d, ["Palisades Tahoe", "Northstar", "Heavenly", "Sierra-at-Tahoe", "Sugar Bowl",
                "Kirkwood", "Bear Valley", "Mammoth Mountain", "Big Bear Mountain", "Snow Valley"])
