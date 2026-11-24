"""Daily snow log: what the app forecast at every lead time, and what resorts later reported.

    poetry run powder --export-json                        # a fresh powder/web/data/forecasts.json
    poetry run python tools/calibrate/daily_log.py         # -> tools/calibrate/.cache/snow-log/<date>.jsonl
    poetry run python tools/calibrate/daily_log.py --out DIR [--forecasts PATH] [--no-reports] [--force]

Writes one JSONL file per day, named by the UTC date of the export's `generated_at`, one line per
resort. Read only by `daily_score.py`; nothing here feeds back into the forecasts.

    resort, country, region, timezone
    issued      export's generated_at (UTC)
    today       resort-local date at `issued`; lead = date - today
    forecast    every daily_forecasts[] entry: date, lead, avg_in, sources {model: in},
                snow_temp_f, freezing_level_ft [min, max], temp_f [min, max]
    past        the last 3 historical_snowfall[] days (lead < 0, model snowfall `snow_in`, same
                conditions): the model's own view of the days just gone, for storm temperature
    report      the 46 resorts in reported.SLUGS only: OnTheSnow skireport, inches
                report_date    the date the resort's latest report is for (it stays put while a
                               resort stops reporting, e.g. off season)
                updated_at     when the report was posted (UTC)
                new_24h_in / new_48h_in / new_72h_in, depth_mid_in, open_flag (1 = open)
                recent         {date: in} the resort's last 8 daily reports, to backfill missed days
                error          instead of the above when the page couldn't be read

OnTheSnow pages are fetched about 1 per second with a descriptive User-Agent after checking
robots.txt; after 5 failures in a row the rest are skipped. The forecasts are always written.
"""

import argparse
import json
import re
import sys
import time
import urllib.robotparser
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from reported import SLUGS  # noqa: E402

FORECASTS = HERE.parents[1] / "powder" / "web" / "data" / "forecasts.json"
OUT = HERE / ".cache" / "snow-log"
SITE = "https://www.onthesnow.com"
USER_AGENT = "Mozilla/5.0 (compatible; powder-snow-log/1.0; daily snow report logging)"
PAST_DAYS = 3
MAX_FAILURES = 5
CM_PER_IN = 2.54


def local_today(issued: datetime, tz_name: str) -> date:
    try:
        return issued.astimezone(ZoneInfo(tz_name or "UTC")).date()
    except Exception:
        return issued.astimezone(UTC).date()


def _conditions(entry: dict) -> dict:
    c = entry.get("conditions") or {}
    return {
        "snow_temp_f": c.get("snow_temp_f"),
        "freezing_level_ft": c.get("freezing_level_ft"),
        "temp_f": [c.get("temp_min_f"), c.get("temp_max_f")],
    }


def resort_record(resort: dict, issued: datetime) -> dict:
    """One resort's forecast at every lead time (no report yet)."""
    today = local_today(issued, resort.get("timezone"))

    def lead(d: str) -> int:
        return (date.fromisoformat(d) - today).days

    forecast = [{"date": d["date"], "lead": lead(d["date"]), "avg_in": d["avg_inches"],
                 "sources": d.get("sources", {}), **_conditions(d)}
                for d in resort.get("daily_forecasts", [])]
    past = [{"date": h["date"], "lead": lead(h["date"]), "snow_in": h["snowfall_inches"], **_conditions(h)}
            for h in resort.get("historical_snowfall", [])[-PAST_DAYS:]]
    return {
        "resort": resort["name"], "country": resort.get("country"), "region": resort.get("region"),
        "timezone": resort.get("timezone"), "issued": issued.isoformat().replace("+00:00", "Z"),
        "today": today.isoformat(), "forecast": forecast, "past": past,
    }


# --- OnTheSnow skireport -------------------------------------------------------------------------
# The page is a Next.js app: its data rides in self.__next_f.push([1, "..."]) script chunks that
# join into lines of `<hex id>:<json>`, where a string "$<id>" points at another line. The resort
# object is the one carrying snow / updatedAt / recent.

def _payload_rows(html: str) -> dict:
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', html, flags=re.S)
    payload = "".join(json.loads(f'"{c}"') for c in chunks)
    rows = {}
    for line in payload.split("\n"):
        m = re.match(r"([0-9a-f]+):([\[{].*)$", line)
        if m:
            try:
                rows[m.group(1)] = json.loads(m.group(2))
            except ValueError:
                pass
    return rows


def _resolve(value, rows: dict, depth: int = 0):
    if isinstance(value, str) and re.fullmatch(r"\$[0-9a-f]+", value) and depth < 5:
        return _resolve(rows.get(value[1:]), rows, depth + 1)
    if isinstance(value, list):
        return [_resolve(v, rows, depth + 1) for v in value]
    if isinstance(value, dict):
        return {k: _resolve(v, rows, depth + 1) for k, v in value.items()}
    return value


def _inches(cm):
    return None if cm is None else round(cm / CM_PER_IN, 2)


def parse_report(html: str) -> dict:
    """The resort-reported snow from a skireport page (OnTheSnow serves centimetres)."""
    rows = _payload_rows(html)
    resort = next((r for r in rows.values()
                   if isinstance(r, dict) and {"snow", "updatedAt", "recent"} <= r.keys()), None)
    if resort is None:
        raise ValueError("no snow report found in page")
    snow = _resolve(resort["snow"], rows) or {}
    status = _resolve(resort.get("status"), rows) or {}
    recent = _resolve(resort.get("recent"), rows) or []
    updated = resort.get("updatedAt")
    report_date = (resort.get("recentStartingReportedDate") or updated or "")[:10] or None
    return {
        "report_date": report_date,
        "updated_at": updated,
        "new_24h_in": _inches(snow.get("last24")),
        "new_48h_in": _inches(snow.get("last48")),
        "new_72h_in": _inches(snow.get("last72")),
        "depth_mid_in": _inches(snow.get("middle")),
        "open_flag": status.get("openFlag"),
        "recent": {r["date"]: _inches(r.get("snow")) for r in recent if isinstance(r, dict) and r.get("date")},
    }


def fetch(session: requests.Session, url: str, tries: int = 3) -> requests.Response:
    """GET, retrying network errors, 429 and 5xx with a growing pause; other errors raise at once."""
    for attempt in range(tries):
        last = attempt == tries - 1
        try:
            resp = session.get(url, timeout=30)
        except requests.RequestException:
            if last:
                raise
        else:
            if (resp.status_code != 429 and resp.status_code < 500) or last:
                resp.raise_for_status()
                return resp
        time.sleep(10 * (attempt + 1))
    raise AssertionError("unreachable")


def scrape_reports(slugs: dict[str, str], delay: float = 1.0) -> dict[str, dict]:
    """{resort name: report or {error}} for every slug, politely."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    robots = urllib.robotparser.RobotFileParser()
    try:
        robots.parse(fetch(session, f"{SITE}/robots.txt").text.splitlines())
        blocked = None
    except requests.RequestException as e:
        blocked = f"robots.txt unreadable, not scraping: {e}"[:300]
    out, failures = {}, 0
    for name, slug in slugs.items():
        url = f"{SITE}/{slug}/skireport"
        base = {"slug": slug, "fetched": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")}
        if blocked or not robots.can_fetch(USER_AGENT, url):
            out[name] = {**base, "error": blocked or "disallowed by robots.txt"}
            continue
        if failures >= MAX_FAILURES:
            out[name] = {**base, "error": f"skipped after {MAX_FAILURES} failures in a row"}
            continue
        try:
            out[name] = {**base, **parse_report(fetch(session, url).text)}
            failures = 0
        except Exception as e:  # one bad page must not lose the day's log
            out[name] = {**base, "error": f"{type(e).__name__}: {e}"[:300]}
            failures += 1
        time.sleep(delay)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--forecasts", type=Path, default=FORECASTS)
    ap.add_argument("--out", type=Path, default=OUT, help="directory for <date>.jsonl")
    ap.add_argument("--no-reports", action="store_true", help="forecasts only, no scraping")
    ap.add_argument("--force", action="store_true", help="overwrite the day's file / log a stale export")
    args = ap.parse_args(argv)

    data = json.loads(args.forecasts.read_text(encoding="utf-8"))
    issued = datetime.fromisoformat(data["generated_at"].replace("Z", "+00:00"))
    if issued.tzinfo is None:
        issued = issued.replace(tzinfo=UTC)
    age = datetime.now(UTC) - issued
    if age > timedelta(hours=24) and not args.force:
        print(f"{args.forecasts} was generated {age} ago; run `powder --export-json` first (or --force)")
        return 1
    path = args.out / f"{issued.date().isoformat()}.jsonl"
    if path.exists() and not args.force:
        print(f"{path} already logged; --force to overwrite")
        return 0

    records = [resort_record(r, issued) for r in data["resorts"]]
    by_name = {r["resort"]: r for r in records}
    if not args.no_reports:
        reports = scrape_reports({n: s for n, s in SLUGS.items() if n in by_name})
        for name, report in reports.items():
            by_name[name]["report"] = report
        bad = [n for n, r in reports.items() if "error" in r]
        dated = Counter(r["report_date"] for r in reports.values() if r.get("report_date"))
        spread = ", ".join(f"{n} x {d}" for d, n in sorted(dated.items(), reverse=True)[:3])
        print(f"{len(reports) - len(bad)}/{len(reports)} reports read; latest report dates: {spread}")
        for n in bad:
            print(f"  {n}: {reports[n]['error']}")

    args.out.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for rec in records:
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")
    tmp.replace(path)
    print(f"{len(records)} resorts, {sum(len(r['forecast']) for r in records)} forecast days -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
