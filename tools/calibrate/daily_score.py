"""Score the daily snow log: forecast vs resort-reported new snow, by lead time and storm temperature.

    poetry run python tools/calibrate/daily_score.py                      # tools/calibrate/.cache/snow-log
    git fetch origin snow-log && poetry run python tools/calibrate/daily_score.py --git origin/snow-log
    poetry run python tools/calibrate/daily_score.py DIR [--leads 1,2,3,5,7] [--align blend|prev|same]
        [--min 1.0] [--sources] [--backfill]

A resort's report dated D gives the new snow of the 24 h up to that morning, so by default it is
compared with 0.75 x the forecast for D-1 + 0.25 x the forecast for D (a ~6 am measurement;
`--align prev` / `same` use one day). Lead N joins it to the forecast logged N days before D
(issue date = the resort-local `today` of that log line), using the same forecast for both days.

Only events where the report or the forecast reaches `--min` inches count (dry days would make
every error zero). The storm temperature is the snowfall-weighted `snow_temp_f` over the same two
days, from the latest log that has them (the model's analysis of D-1 once it is past), falling
back to the middle of the day's temperature range: cold < 18 F, mid 18-27 F, warm > 27 F.

`--backfill` also uses days a resort reported but no log caught on the day, from the `recent`
list of a later report. `--sources` repeats the table per model.
"""

import argparse
import json
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE / ".cache" / "snow-log"
ALIGN = {"blend": (0.75, 0.25), "prev": (1.0, 0.0), "same": (0.0, 1.0)}


def band_of(temp_f):
    if temp_f is None:
        return "unknown"
    if temp_f < 18:
        return "cold"
    return "mid" if temp_f <= 27 else "warm"


def read_logs(directory: Path | None = None, git_ref: str | None = None) -> list[dict]:
    """Every line of every <date>.jsonl, from a directory or a git ref (e.g. origin/snow-log)."""
    texts = []
    if git_ref:
        names = subprocess.run(["git", "ls-tree", "-r", "--name-only", git_ref], check=True,
                               capture_output=True, text=True).stdout.split()
        for name in sorted(n for n in names if n.endswith(".jsonl")):
            texts.append(subprocess.run(["git", "show", f"{git_ref}:{name}"], check=True,
                                        capture_output=True, text=True, encoding="utf-8").stdout)
    else:
        for p in sorted(set(directory.glob("*.jsonl")) | set(directory.glob("log/*.jsonl"))):
            texts.append(p.read_text(encoding="utf-8"))
    return [json.loads(line) for text in texts for line in text.splitlines() if line.strip()]


def index(lines: list[dict], backfill: bool = False):
    """forecasts[resort][issue date] = {date: entry}; reports[(resort, report date)] = inches."""
    forecasts, reports, filled = defaultdict(dict), {}, {}
    for rec in lines:
        days = {d["date"]: {**d, "snow": d["snow_in"]} for d in rec.get("past", [])}
        days.update({d["date"]: {**d, "snow": d["avg_in"]} for d in rec.get("forecast", [])})
        forecasts[rec["resort"]][rec["today"]] = days
        rep = rec.get("report") or {}
        recent = rep.get("recent") or {}
        # Some pages leave last24 empty while the same report's day is in `recent`
        new = rep.get("new_24h_in")
        new = recent.get(rep.get("report_date")) if new is None else new
        if rep.get("report_date") and new is not None:
            reports[(rec["resort"], rep["report_date"])] = new
        for d, inches in recent.items():
            if inches is not None and (rep.get("report_date") is None or d <= rep["report_date"]):
                filled[(rec["resort"], d)] = inches
    if backfill:
        reports = {**filled, **reports}
    return forecasts, reports


def _shift(d: str, days: int) -> str:
    return (date.fromisoformat(d) + timedelta(days=days)).isoformat()


def window(days: dict, report_date: str, weights, key=None):
    """Forecast for the 24 h a report covers: weighted D-1 and D, or None if a needed day is missing."""
    total = 0.0
    for d, w in ((_shift(report_date, -1), weights[0]), (report_date, weights[1])):
        if w == 0:
            continue
        entry = days.get(d)
        value = None if entry is None else (entry["snow"] if key is None else entry.get("sources", {}).get(key))
        if value is None:
            return None
        total += w * value
    return total


def storm_temp(by_issue: dict, report_date: str, weights):
    """Snowfall-weighted snow temperature over the report's two days, from the latest log that has them."""
    prev, cur = _shift(report_date, -1), report_date
    for issue in sorted((i for i in by_issue if i <= _shift(cur, 1)), reverse=True):
        days = by_issue[issue]
        parts = [(days[d], w) for d, w in ((prev, weights[0]), (cur, weights[1])) if w and d in days]
        if not parts:
            continue
        snowy = [(e["snow_temp_f"], w * max(e["snow"], 0.01)) for e, w in parts if e.get("snow_temp_f") is not None]
        if snowy:
            return sum(t * w for t, w in snowy) / sum(w for _, w in snowy)
        mids = [(sum(e["temp_f"]) / 2, w) for e, w in parts if None not in (e.get("temp_f") or [None])]
        if mids:
            return sum(t * w for t, w in mids) / sum(w for _, w in mids)
    return None


def pairs(forecasts: dict, reports: dict, leads, weights, min_in: float, key=None):
    """[(lead, band, forecast, reported)] for every report with a forecast `lead` days earlier."""
    out = []
    for (resort, report_date), reported in reports.items():
        by_issue = forecasts.get(resort, {})
        band = None
        for lead in leads:
            days = by_issue.get(_shift(report_date, -lead))
            if days is None:
                continue
            fc = window(days, report_date, weights, key)
            if fc is None or max(fc, reported) < min_in:
                continue
            if band is None:
                band = band_of(storm_temp(by_issue, report_date, weights))
            out.append((lead, band, fc, reported))
    return out


def stats(rows):
    err = [f - r for _, _, f, r in rows]
    obs = sum(r for *_, r in rows)
    return {
        "n": len(rows),
        "mae": statistics.median(abs(e) for e in err),
        "bias": statistics.median(err),
        "mean": statistics.fmean(err),
        "ratio": sum(f for _, _, f, _ in rows) / obs if obs else None,
    }


def table(rows, leads, title):
    print(f"\n{title}")
    print(f"  {'lead':>4} {'band':<8} {'n':>5} {'med |err|':>9} {'med bias':>9} {'mean bias':>9} {'fcst/rep':>8}")
    groups = defaultdict(list)
    for row in rows:
        groups[(row[0], "all")].append(row)
        groups[(row[0], row[1])].append(row)
    for lead in leads:
        for band in ("all", "cold", "mid", "warm", "unknown"):
            g = groups.get((lead, band))
            if not g:
                continue
            s = stats(g)
            ratio = f"{s['ratio']:8.2f}" if s["ratio"] is not None else f"{'-':>8}"
            print(f"  {lead:>4} {band:<8} {s['n']:>5} {s['mae']:8.1f}\" {s['bias']:+8.1f}\" {s['mean']:+8.1f}\" {ratio}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dir", nargs="?", type=Path, default=LOG)
    ap.add_argument("--git", metavar="REF", help="read the logs from a git ref instead, e.g. origin/snow-log")
    ap.add_argument("--leads", default="1,2,3,5,7")
    ap.add_argument("--align", choices=ALIGN, default="blend")
    ap.add_argument("--min", type=float, default=1.0, help="inches the report or forecast must reach")
    ap.add_argument("--sources", action="store_true", help="also score each model on its own")
    ap.add_argument("--backfill", action="store_true", help="also use reports from later `recent` lists")
    args = ap.parse_args(argv)

    leads = [int(x) for x in args.leads.split(",")]
    weights = ALIGN[args.align]
    lines = read_logs(None if args.git else args.dir, args.git)
    forecasts, reports = index(lines, args.backfill)
    logged = sorted({rec["issued"][:10] for rec in lines if rec.get("issued")})
    report_days = sorted({d for _, d in reports})

    def span(days):
        return f"{days[0]}..{days[-1]}" if days else "-"

    print(f"{len(lines)} log lines from {len(logged)} days ({span(logged)}); "
          f"{len(reports)} resort reports dated {span(report_days)}")
    print(f"Window: {weights[0]:.2f} x D-1 + {weights[1]:.2f} x D; events with report or forecast >= {args.min}\"; "
          f"error = forecast - reported")

    rows = pairs(forecasts, reports, leads, weights, args.min)
    if not rows:
        print(f"\nNo report has a forecast {args.leads} days before it yet: the log needs more days.")
        return 0
    table(rows, leads, "Forecast average (avg_in)")
    if args.sources:
        names = sorted({k for by_issue in forecasts.values() for days in by_issue.values()
                        for d in days.values() for k in d.get("sources", {})})
        for name in names:
            src = pairs(forecasts, reports, leads, weights, args.min, key=name)
            if src:
                table(src, leads, name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
