"""SNOTEL daily snow water, depth and precipitation for the stations in snotel_sites.json.

    poetry run python tools/calibrate/snotel.py     # fetch into .cache/snotel/

SNOTEL measures the same way everywhere (snow pillow, depth sensor, storage gauge), so it tests
the precipitation step of the model without each resort's reporting habits. Data comes from
NOAA's GHCN-Daily copy (NCEI), ids `USS...`; NRCS's own API is the primary source.
"""

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hindcast  # noqa: E402

HERE = Path(__file__).resolve().parent
CACHE = hindcast.CACHE / "snotel"
SITES = json.loads((HERE / "snotel_sites.json").read_text())
URL = "https://www.ncei.noaa.gov/access/services/data/v1"


def fetch() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    for sid in SITES["stations"]:
        path = CACHE / f"{sid}.json"
        if path.exists():
            continue
        for attempt in range(5):
            try:
                resp = requests.get(URL, timeout=120, params=dict(
                    dataset="daily-summaries", stations=sid, dataTypes="PRCP,SNWD,WESD",
                    startDate=hindcast.START, endDate=hindcast.END, units="standard", format="json"))
                resp.raise_for_status()
                path.write_text(resp.text)
                print("fetched", sid, flush=True)
                break
            except requests.RequestException:
                time.sleep(5 * (attempt + 1))


def daily(sid: str) -> dict:
    """{date: {"PRCP": in, "WESD": in of water on the ground, "SNWD": in of depth}} (None if missing)."""
    rows = json.loads((CACHE / f"{sid}.json").read_text())
    num = lambda v: float(v) if v not in (None, "") and str(v).strip() else None  # noqa: E731
    return {date.fromisoformat(r["DATE"]): {k: num(r.get(k)) for k in ("PRCP", "WESD", "SNWD")} for r in rows}


def gains(sid: str) -> dict:
    """{date: (snow water gained, depth gained, gauge precipitation)} in inches over that day.

    In GHCN-Daily the snow water / depth on date D is the reading that closes the day (checked
    against model days: the gain D minus D-1 lines up with the gauge total for D).
    """
    d = daily(sid)
    out = {}
    for day, cur in d.items():
        prev = d.get(day - timedelta(days=1))
        if not prev:
            continue
        diff = lambda k, lo, hi: (max(0.0, cur[k] - prev[k]) if cur[k] is not None and prev[k] is not None  # noqa: E731
                                  and lo <= cur[k] - prev[k] < hi else 0.0)
        out[day] = (diff("WESD", 0, 6), diff("SNWD", 1, 40), cur["PRCP"] or 0.0)
    return out


if __name__ == "__main__":
    fetch()
