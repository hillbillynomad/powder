#!/usr/bin/env python3
"""Merge existing US/CA resorts with global resorts into a single file."""

import json
from pathlib import Path

try:
    from timezonefinder import TimezoneFinder
    TZ_FINDER = TimezoneFinder()
except ImportError:
    TZ_FINDER = None

def get_timezone(lat: float, lon: float) -> str:
    """Get IANA timezone from coordinates."""
    if TZ_FINDER:
        tz = TZ_FINDER.timezone_at(lat=lat, lng=lon)
        return tz if tz else "UTC"
    return "UTC"

# Lift counts for US/CA resorts (approximate)
US_CA_LIFTS = {
    "Park City Mountain": 41,
    "Deer Valley": 21,
    "Snowbird": 14,
    "Alta": 11,
    "Brighton": 7,  # Below threshold but keep for existing data
    "Solitude": 8,  # Below threshold but keep for existing data
    "Snowbasin": 10,
    "Vail": 31,
    "Beaver Creek": 25,
    "Breckenridge": 35,
    "Keystone": 20,
    "Crested Butte": 16,
    "Steamboat": 18,
    "Winter Park": 24,
    "Copper Mountain": 24,
    "Aspen Mountain": 8,  # Below threshold but keep
    "Aspen Highlands": 5,  # Below threshold but keep
    "Snowmass": 21,
    "Telluride": 18,
    "Arapahoe Basin": 9,  # Below threshold but keep
    "Purgatory": 12,
    "Mammoth Mountain": 28,
    "Palisades Tahoe": 29,
    "Heavenly": 28,
    "Northstar": 20,
    "Kirkwood": 15,
    "Big Bear Mountain": 26,
    "Jackson Hole": 13,
    "Big Sky": 36,
    "Whitefish Mountain": 14,
    "Sun Valley": 18,
    "Taos Ski Valley": 14,
    "Crystal Mountain": 11,
    "Stevens Pass": 10,
    "Mt. Bachelor": 11,
    "Killington": 22,
    "Stowe": 13,
    "Sugarbush": 16,
    "Okemo": 20,
    "Stratton": 11,
    "Loon Mountain": 10,
    "Sunday River": 18,
    "Sugarloaf": 14,
    "Whistler Blackcomb": 37,
    "Mont Tremblant": 14,
    "Lake Louise": 10,
    "Sun Peaks": 13,
    "Banff Sunshine": 12,
    "Big White": 16,
    "Blue Mountain": 42,
    "Panorama": 10,
    "Fernie Alpine Resort": 10,
    "SilverStar": 12,
}

def main():
    data_dir = Path(__file__).parent.parent / "powder" / "data"

    # Load existing US/CA resorts
    with open(data_dir / "resorts.json") as f:
        existing = json.load(f)

    # Load global resorts
    with open(data_dir / "resorts_global.json") as f:
        global_data = json.load(f)

    merged_resorts = []

    # Process existing US/CA resorts
    for resort in existing["resorts"]:
        country = resort.get("country", "US")
        region = resort.get("state", "")
        name = resort["name"]
        lat = resort["latitude"]
        lon = resort["longitude"]

        merged_resorts.append({
            "name": name,
            "country": country,
            "region": region,
            "latitude": lat,
            "longitude": lon,
            "elevation_ft": resort["elevation_ft"],
            "lift_count": US_CA_LIFTS.get(name, 10),
            "avg_snowfall_inches": resort.get("avg_snowfall_inches"),
            "pass_type": resort.get("pass_type"),
            "timezone": get_timezone(lat, lon),
        })

    # Add global resorts
    merged_resorts.extend(global_data["resorts"])

    # Sort by country, then by lift count descending
    merged_resorts.sort(key=lambda r: (r["country"], -r.get("lift_count", 0)))

    # Write merged file
    output = {"resorts": merged_resorts}
    with open(data_dir / "resorts.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"Merged {len(merged_resorts)} resorts")

    # Count by country
    from collections import Counter
    counts = Counter(r["country"] for r in merged_resorts)
    print("\nResorts by country:")
    for country, count in sorted(counts.items()):
        print(f"  {country}: {count}")

if __name__ == "__main__":
    main()
