"""Scrape resort-reported season snowfall from OnTheSnow into reported_seasons.json.

    poetry run python tools/calibrate/reported.py

OnTheSnow season totals are the sum of the daily reports a resort sends in, so a season with
missing reports comes out low. Each row keeps [inches, snowfall days]; `complete()` flags a
season whose snowfall days fall well short of the resort's own long-run median.
"""

import json
import re
import statistics
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
OUT = HERE / "reported_seasons.json"
SLUGS = {
    "Blue Mountain": "ontario/blue-mountain", "Whistler Blackcomb": "british-columbia/whistler-blackcomb",
    "Big White": "british-columbia/big-white", "Mont Tremblant": "quebec/tremblant",
    "Sun Peaks": "british-columbia/sun-peaks", "Banff Sunshine": "alberta/banff-sunshine",
    "SilverStar": "british-columbia/silver-star", "Lake Louise": "alberta/lake-louise",
    "Panorama": "british-columbia/panorama-mountain", "Fernie Alpine Resort": "british-columbia/fernie-alpine",
    "Revelstoke Mountain Resort": "british-columbia/revelstoke-mountain", "Kicking Horse": "british-columbia/kicking-horse",
    "Park City Mountain": "utah/park-city-mountain-resort", "Big Sky": "montana/big-sky-resort",
    "Breckenridge": "colorado/breckenridge", "Vail": "colorado/vail", "Palisades Tahoe": "california/palisades-tahoe",
    "Mammoth Mountain": "california/mammoth-mountain-ski-area", "Heavenly": "california/heavenly-mountain-resort",
    "Big Bear Mountain": "california/bear-mountain", "Beaver Creek": "colorado/beaver-creek",
    "Winter Park": "colorado/winter-park-resort", "Copper Mountain": "colorado/copper-mountain-resort",
    "Deer Valley": "utah/deer-valley-resort", "Snowmass": "colorado/aspen-snowmass", "Keystone": "colorado/keystone",
    "Northstar": "california/northstar-california", "Steamboat": "colorado/steamboat", "Telluride": "colorado/telluride",
    "Crested Butte": "colorado/crested-butte-mountain-resort", "Kirkwood": "california/kirkwood",
    "Bear Valley": "california/bear-valley", "Snowbird": "utah/snowbird",
    "Whitefish Mountain": "montana/whitefish-mountain-resort", "Bridger Bowl": "montana/bridger-bowl",
    "Jackson Hole": "wyoming/jackson-hole", "Purgatory": "colorado/durango-mountain-resort",
    "Alta": "utah/alta-ski-area", "Snowbasin": "utah/snowbasin", "Arapahoe Basin": "colorado/arapahoe-basin-ski-area",
    "Solitude": "utah/solitude-mountain-resort", "Brighton": "utah/brighton-resort",
    "Eldora": "colorado/eldora-mountain-resort", "Sierra-at-Tahoe": "california/sierra-at-tahoe",
    "Sugar Bowl": "california/sugar-bowl-resort", "Snow Valley": "california/snow-valley",
}
ROW = re.compile(r"(20\d\d) — (?:20\d\d|To Date)\s*(\d+)\"\s*(\d+) days")


def scrape(slug: str) -> dict:
    html = requests.get(f"https://www.onthesnow.com/{slug}/historical-snowfall", timeout=30,
                        headers={"User-Agent": "Mozilla/5.0 (powder snowfall calibration)"}).text
    rows = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, flags=re.S)]
        if len(cells) >= 3:
            year = re.match(r"(20\d\d)\D+(?:20\d\d|To Date)$", cells[0])
            inches = re.match(r"(\d+)&quot;$", cells[1])
            days = re.match(r"(\d+) days$", cells[2])
            if year and inches and days:
                rows.setdefault(year.group(1), [int(inches.group(1)), int(days.group(1))])
    return rows


def complete(rows: dict, season: str, min_share: float = 0.7) -> bool:
    """Season's snowfall days at least `min_share` of the resort's median over other seasons."""
    if season not in rows:
        return False
    others = [d for y, (_, d) in rows.items() if y != season and y.isdigit() and int(y) <= 2024]
    return bool(others) and rows[season][1] >= min_share * statistics.median(others)


def main():
    data = {"_source": "Resort-reported season snowfall [inches, snowfall days] via OnTheSnow "
                       "historical-snowfall pages; key = season start year."}
    for name, slug in SLUGS.items():
        data[name] = scrape(slug)
        print(name, len(data[name]), "seasons", flush=True)
        time.sleep(1)
    OUT.write_text(json.dumps(data, indent=1))


if __name__ == "__main__":
    main()
