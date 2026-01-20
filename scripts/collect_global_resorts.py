#!/usr/bin/env python3
"""
Collect global ski resort data from OpenStreetMap via Overpass API.

This script queries OpenStreetMap for ski resorts with their lift infrastructure
and outputs a JSON file compatible with the Powder app.

Usage:
    poetry install --with dev
    python scripts/collect_global_resorts.py
"""

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import requests

try:
    from timezonefinder import TimezoneFinder
    TZ_FINDER = TimezoneFinder()
except ImportError:
    TZ_FINDER = None
    print("Warning: timezonefinder not installed. Timezones will default to UTC.")

# Overpass API endpoint
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Country bounding boxes (approximate) for targeted queries
# Format: (min_lat, min_lon, max_lat, max_lon)
COUNTRY_BOUNDS = {
    # Europe - Alps
    "FR": (41.3, -5.2, 51.1, 9.6),      # France
    "CH": (45.8, 5.9, 47.8, 10.5),      # Switzerland
    "AT": (46.4, 9.5, 49.0, 17.2),      # Austria
    "IT": (35.5, 6.6, 47.1, 18.5),      # Italy
    "DE": (47.3, 5.9, 55.1, 15.0),      # Germany
    # Europe - Other
    "ES": (35.9, -9.3, 43.8, 4.3),      # Spain
    "AD": (42.4, 1.4, 42.7, 1.8),       # Andorra
    "SE": (55.3, 11.1, 69.1, 24.2),     # Sweden
    "NO": (57.9, 4.6, 71.2, 31.1),      # Norway
    "FI": (59.8, 20.6, 70.1, 31.6),     # Finland
    "PL": (49.0, 14.1, 54.8, 24.2),     # Poland
    "CZ": (48.6, 12.1, 51.1, 18.9),     # Czech Republic
    "SK": (47.7, 16.8, 49.6, 22.6),     # Slovakia
    "SI": (45.4, 13.4, 46.9, 16.6),     # Slovenia
    "BG": (41.2, 22.4, 44.2, 28.6),     # Bulgaria
    "RO": (43.6, 20.3, 48.3, 29.7),     # Romania
    # Asia
    "JP": (24.0, 122.9, 45.5, 145.8),   # Japan
    "KR": (33.1, 124.6, 38.6, 131.9),   # South Korea
    "CN": (18.2, 73.5, 53.6, 134.8),    # China
    # Oceania
    "AU": (-43.6, 113.2, -10.7, 153.6), # Australia
    "NZ": (-47.3, 166.4, -34.4, 178.6), # New Zealand
    # South America
    "CL": (-55.9, -75.7, -17.5, -66.4), # Chile
    "AR": (-55.0, -73.6, -21.8, -53.6), # Argentina
}

# European countries for weather provider selection
EUROPEAN_COUNTRIES = {"FR", "CH", "AT", "IT", "DE", "ES", "AD", "SE", "NO", "FI",
                      "PL", "CZ", "SK", "SI", "BG", "RO"}


@dataclass
class ResortData:
    name: str
    country: str
    region: str
    latitude: float
    longitude: float
    elevation_base_ft: int
    elevation_peak_ft: int | None = None
    lift_count: int = 0
    avg_snowfall_inches: int | None = None
    pass_type: str | None = None
    timezone: str = "UTC"


def get_timezone(lat: float, lon: float) -> str:
    """Get IANA timezone from coordinates."""
    if TZ_FINDER:
        tz = TZ_FINDER.timezone_at(lat=lat, lng=lon)
        return tz if tz else "UTC"
    return "UTC"


def meters_to_feet(meters: float) -> int:
    """Convert meters to feet."""
    return int(meters * 3.28084)


def query_ski_areas_with_lifts(bounds: tuple[float, float, float, float]) -> list[dict]:
    """
    Query OpenStreetMap for ski areas with their lift counts.

    Uses Overpass API to find ski areas and count associated lifts.
    """
    min_lat, min_lon, max_lat, max_lon = bounds

    # Query for ski areas and their associated lifts
    query = f"""
    [out:json][timeout:120];
    (
      // Ski areas/resorts
      way["landuse"="winter_sports"]({min_lat},{min_lon},{max_lat},{max_lon});
      relation["landuse"="winter_sports"]({min_lat},{min_lon},{max_lat},{max_lon});
      way["piste:type"="downhill"]["name"]({min_lat},{min_lon},{max_lat},{max_lon});
      node["sport"="skiing"]["name"]({min_lat},{min_lon},{max_lat},{max_lon});
    );
    out center tags;
    """

    try:
        response = requests.post(OVERPASS_URL, data={"data": query}, timeout=180)
        response.raise_for_status()
        return response.json().get("elements", [])
    except Exception as e:
        print(f"  Error querying Overpass: {e}")
        return []


def query_lifts_in_area(center_lat: float, center_lon: float, radius_km: float = 10) -> int:
    """Count ski lifts within a radius of a point."""
    # Convert km to degrees (approximate)
    lat_delta = radius_km / 111.0
    lon_delta = radius_km / (111.0 * abs(center_lat) / 90 + 0.01)

    min_lat = center_lat - lat_delta
    max_lat = center_lat + lat_delta
    min_lon = center_lon - lon_delta
    max_lon = center_lon + lon_delta

    query = f"""
    [out:json][timeout:60];
    (
      // All types of ski lifts
      way["aerialway"="cable_car"]({min_lat},{min_lon},{max_lat},{max_lon});
      way["aerialway"="gondola"]({min_lat},{min_lon},{max_lat},{max_lon});
      way["aerialway"="chair_lift"]({min_lat},{min_lon},{max_lat},{max_lon});
      way["aerialway"="drag_lift"]({min_lat},{min_lon},{max_lat},{max_lon});
      way["aerialway"="t-bar"]({min_lat},{min_lon},{max_lat},{max_lon});
      way["aerialway"="j-bar"]({min_lat},{min_lon},{max_lat},{max_lon});
      way["aerialway"="platter"]({min_lat},{min_lon},{max_lat},{max_lon});
      way["aerialway"="rope_tow"]({min_lat},{min_lon},{max_lat},{max_lon});
      way["aerialway"="magic_carpet"]({min_lat},{min_lon},{max_lat},{max_lon});
      way["aerialway"="funicular"]({min_lat},{min_lon},{max_lat},{max_lon});
    );
    out count;
    """

    try:
        response = requests.post(OVERPASS_URL, data={"data": query}, timeout=90)
        response.raise_for_status()
        data = response.json()
        # Overpass returns count in elements[0].tags.total for count queries
        elements = data.get("elements", [])
        if elements and "tags" in elements[0]:
            return int(elements[0]["tags"].get("total", 0))
        return len(elements)
    except Exception as e:
        print(f"    Error counting lifts: {e}")
        return 0


def get_elevation(lat: float, lon: float) -> int:
    """Get elevation from Open-Elevation API."""
    try:
        url = f"https://api.open-elevation.com/api/v1/lookup?locations={lat},{lon}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])
        if results:
            return meters_to_feet(results[0].get("elevation", 0))
    except Exception:
        pass
    return 0


def get_region_from_coords(lat: float, lon: float) -> str:
    """Get region/state name from coordinates using Nominatim reverse geocoding."""
    try:
        url = f"https://nominatim.openstreetmap.org/reverse"
        params = {
            "lat": lat,
            "lon": lon,
            "format": "json",
            "zoom": 8,  # State/region level
        }
        headers = {"User-Agent": "PowderApp/1.0 (ski forecast tracker)"}
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        address = data.get("address", {})
        # Try different address components for region
        region = (
            address.get("state") or
            address.get("province") or
            address.get("region") or
            address.get("county") or
            ""
        )
        return region
    except Exception:
        return ""


def collect_resorts_for_country(country_code: str, bounds: tuple, min_lifts: int = 10) -> list[ResortData]:
    """Collect ski resorts for a country."""
    print(f"\nProcessing {country_code}...")
    print(f"  Querying ski areas in bounds: {bounds}")

    areas = query_ski_areas_with_lifts(bounds)
    print(f"  Found {len(areas)} potential ski areas")

    resorts = []
    seen_names = set()

    for i, area in enumerate(areas):
        name = area.get("tags", {}).get("name")
        if not name or name in seen_names:
            continue
        seen_names.add(name)

        # Get center coordinates
        if "center" in area:
            lat = area["center"]["lat"]
            lon = area["center"]["lon"]
        elif "lat" in area and "lon" in area:
            lat = area["lat"]
            lon = area["lon"]
        else:
            continue

        print(f"  [{i+1}/{len(areas)}] Checking {name}...")

        # Count lifts in the area
        lift_count = query_lifts_in_area(lat, lon, radius_km=15)
        time.sleep(1)  # Be polite to Overpass API

        if lift_count < min_lifts:
            print(f"    Only {lift_count} lifts, skipping")
            continue

        print(f"    Found {lift_count} lifts")

        # Get additional details
        elevation = get_elevation(lat, lon)
        region = get_region_from_coords(lat, lon)
        timezone = get_timezone(lat, lon)

        time.sleep(1)  # Rate limiting

        resort = ResortData(
            name=name,
            country=country_code,
            region=region,
            latitude=round(lat, 6),
            longitude=round(lon, 6),
            elevation_ft=elevation,
            lift_count=lift_count,
            timezone=timezone,
        )
        resorts.append(resort)

    return resorts


def load_known_resorts() -> dict:
    """Load manually curated resort data with verified base and peak elevations.

    Elevation data sourced from official resort websites and verified sources.
    base_elev = base/village elevation in feet
    peak_elev = summit/peak elevation in feet
    """
    known_resorts = {
        # France - Major resorts
        "FR": [
            {"name": "Les 3 Vallées", "lat": 45.3167, "lon": 6.5833, "lifts": 169, "region": "Savoie", "base_elev": 4265, "peak_elev": 10597},
            {"name": "Portes du Soleil", "lat": 46.1833, "lon": 6.75, "lifts": 196, "region": "Haute-Savoie", "base_elev": 3280, "peak_elev": 7546},
            {"name": "Paradiski", "lat": 45.5167, "lon": 6.8833, "lifts": 141, "region": "Savoie", "base_elev": 4101, "peak_elev": 10663},
            {"name": "Tignes/Val d'Isère", "lat": 45.4667, "lon": 6.9, "lifts": 79, "region": "Savoie", "base_elev": 5085, "peak_elev": 11339},
            {"name": "Chamonix Mont-Blanc", "lat": 45.9237, "lon": 6.8694, "lifts": 47, "region": "Haute-Savoie", "base_elev": 3396, "peak_elev": 12605},
            {"name": "Alpe d'Huez", "lat": 45.0917, "lon": 6.0667, "lifts": 81, "region": "Isère", "base_elev": 4101, "peak_elev": 10925},
            {"name": "Les 2 Alpes", "lat": 45.0167, "lon": 6.1333, "lifts": 47, "region": "Isère", "base_elev": 5413, "peak_elev": 11811},
            {"name": "Serre Chevalier", "lat": 44.9333, "lon": 6.5833, "lifts": 61, "region": "Hautes-Alpes", "base_elev": 4265, "peak_elev": 9186},
            {"name": "La Plagne", "lat": 45.5, "lon": 6.7, "lifts": 79, "region": "Savoie", "base_elev": 3937, "peak_elev": 10663},
            {"name": "Les Arcs", "lat": 45.5667, "lon": 6.8167, "lifts": 54, "region": "Savoie", "base_elev": 3937, "peak_elev": 10663},
            {"name": "Megève/Saint-Gervais", "lat": 45.8567, "lon": 6.6178, "lifts": 84, "region": "Haute-Savoie", "base_elev": 3609, "peak_elev": 6562},
            {"name": "Flaine/Grand Massif", "lat": 46.0058, "lon": 6.6897, "lifts": 64, "region": "Haute-Savoie", "base_elev": 2297, "peak_elev": 8202},
            {"name": "La Clusaz", "lat": 45.9042, "lon": 6.4239, "lifts": 49, "region": "Haute-Savoie", "base_elev": 3412, "peak_elev": 8038},
            {"name": "Avoriaz", "lat": 46.1906, "lon": 6.7739, "lifts": 34, "region": "Haute-Savoie", "base_elev": 5906, "peak_elev": 7546},
        ],
        # Switzerland
        "CH": [
            {"name": "Zermatt", "lat": 46.0207, "lon": 7.7491, "lifts": 52, "region": "Valais", "base_elev": 5315, "peak_elev": 12739},
            {"name": "Verbier", "lat": 46.0967, "lon": 7.2283, "lifts": 82, "region": "Valais", "base_elev": 4921, "peak_elev": 10925},
            {"name": "St. Moritz", "lat": 46.4908, "lon": 9.8355, "lifts": 56, "region": "Graubünden", "base_elev": 5748, "peak_elev": 10837},
            {"name": "Davos Klosters", "lat": 46.8027, "lon": 9.8360, "lifts": 55, "region": "Graubünden", "base_elev": 4856, "peak_elev": 9331},
            {"name": "Laax/Flims", "lat": 46.8419, "lon": 9.2594, "lifts": 28, "region": "Graubünden", "base_elev": 3543, "peak_elev": 9843},
            {"name": "Saas-Fee", "lat": 46.1086, "lon": 7.9283, "lifts": 22, "region": "Valais", "base_elev": 5906, "peak_elev": 11811},
            {"name": "Crans-Montana", "lat": 46.3108, "lon": 7.4819, "lifts": 27, "region": "Valais", "base_elev": 4921, "peak_elev": 9842},
            {"name": "Arosa Lenzerheide", "lat": 46.7833, "lon": 9.6667, "lifts": 43, "region": "Graubünden", "base_elev": 4265, "peak_elev": 9186},
            {"name": "Grindelwald", "lat": 46.6244, "lon": 8.0414, "lifts": 26, "region": "Bern", "base_elev": 3445, "peak_elev": 9748},
            {"name": "Wengen/Jungfrau", "lat": 46.6083, "lon": 7.9222, "lifts": 44, "region": "Bern", "base_elev": 3445, "peak_elev": 9748},
            {"name": "Adelboden-Lenk", "lat": 46.4922, "lon": 7.5606, "lifts": 56, "region": "Bern", "base_elev": 4429, "peak_elev": 7546},
            {"name": "Engelberg-Titlis", "lat": 46.8214, "lon": 8.4072, "lifts": 25, "region": "Obwalden", "base_elev": 3281, "peak_elev": 9908},
        ],
        # Austria
        "AT": [
            {"name": "Ski Arlberg", "lat": 47.1289, "lon": 10.2106, "lifts": 88, "region": "Tirol/Vorarlberg", "base_elev": 4265, "peak_elev": 9222},
            {"name": "SkiWelt Wilder Kaiser", "lat": 47.4667, "lon": 12.1167, "lifts": 90, "region": "Tirol", "base_elev": 2034, "peak_elev": 6201},
            {"name": "Saalbach Hinterglemm", "lat": 47.3906, "lon": 12.6361, "lifts": 70, "region": "Salzburg", "base_elev": 3281, "peak_elev": 6890},
            {"name": "Ischgl/Samnaun", "lat": 46.9689, "lon": 10.2906, "lifts": 45, "region": "Tirol", "base_elev": 4593, "peak_elev": 9518},
            {"name": "Kitzbühel", "lat": 47.4492, "lon": 12.3919, "lifts": 57, "region": "Tirol", "base_elev": 2625, "peak_elev": 6562},
            {"name": "Sölden", "lat": 46.9667, "lon": 10.8667, "lifts": 31, "region": "Tirol", "base_elev": 4429, "peak_elev": 10958},
            {"name": "Zillertal Arena", "lat": 47.1667, "lon": 11.8833, "lifts": 52, "region": "Tirol", "base_elev": 1804, "peak_elev": 7956},
            {"name": "Obertauern", "lat": 47.2500, "lon": 13.5667, "lifts": 26, "region": "Salzburg", "base_elev": 5577, "peak_elev": 7218},
            {"name": "Schladming", "lat": 47.3942, "lon": 13.6875, "lifts": 44, "region": "Steiermark", "base_elev": 2461, "peak_elev": 6201},
            {"name": "Mayrhofen", "lat": 47.1667, "lon": 11.8667, "lifts": 44, "region": "Tirol", "base_elev": 2034, "peak_elev": 8202},
            {"name": "Obergurgl-Hochgurgl", "lat": 46.8667, "lon": 11.0167, "lifts": 25, "region": "Tirol", "base_elev": 6201, "peak_elev": 10827},
            {"name": "Bad Gastein", "lat": 47.1167, "lon": 13.1333, "lifts": 50, "region": "Salzburg", "base_elev": 2789, "peak_elev": 8497},
            {"name": "Stubaier Gletscher", "lat": 47.0, "lon": 11.1167, "lifts": 26, "region": "Tirol", "base_elev": 4593, "peak_elev": 10531},
            {"name": "Hintertux Glacier", "lat": 47.0667, "lon": 11.6667, "lifts": 21, "region": "Tirol", "base_elev": 4921, "peak_elev": 10663},
        ],
        # Italy
        "IT": [
            {"name": "Dolomiti Superski", "lat": 46.5333, "lon": 11.8667, "lifts": 450, "region": "Trentino-Alto Adige", "base_elev": 3937, "peak_elev": 10341},
            {"name": "Livigno", "lat": 46.5386, "lon": 10.1356, "lifts": 31, "region": "Lombardia", "base_elev": 5971, "peak_elev": 9514},
            {"name": "Cervinia", "lat": 45.9333, "lon": 7.6333, "lifts": 21, "region": "Valle d'Aosta", "base_elev": 6726, "peak_elev": 11417},
            {"name": "Cortina d'Ampezzo", "lat": 46.5369, "lon": 12.1356, "lifts": 37, "region": "Veneto", "base_elev": 4101, "peak_elev": 10643},
            {"name": "Sestriere/Via Lattea", "lat": 44.9583, "lon": 6.8792, "lifts": 92, "region": "Piemonte", "base_elev": 4593, "peak_elev": 9514},
            {"name": "Madonna di Campiglio", "lat": 46.2292, "lon": 10.8269, "lifts": 24, "region": "Trentino", "base_elev": 4921, "peak_elev": 8858},
            {"name": "Bormio", "lat": 46.4669, "lon": 10.3711, "lifts": 14, "region": "Lombardia", "base_elev": 3904, "peak_elev": 10466},
            {"name": "Val Gardena", "lat": 46.5583, "lon": 11.7556, "lifts": 83, "region": "Trentino-Alto Adige", "base_elev": 4101, "peak_elev": 8202},
            {"name": "Alta Badia", "lat": 46.55, "lon": 11.8833, "lifts": 53, "region": "Trentino-Alto Adige", "base_elev": 4101, "peak_elev": 8858},
            {"name": "Kronplatz", "lat": 46.7417, "lon": 11.9583, "lifts": 32, "region": "Trentino-Alto Adige", "base_elev": 3117, "peak_elev": 7462},
            {"name": "Courmayeur", "lat": 45.7911, "lon": 6.9686, "lifts": 18, "region": "Valle d'Aosta", "base_elev": 3937, "peak_elev": 9186},
        ],
        # Germany
        "DE": [
            {"name": "Garmisch-Partenkirchen", "lat": 47.4917, "lon": 11.0958, "lifts": 33, "region": "Bayern", "base_elev": 2362, "peak_elev": 9718},
            {"name": "Oberstdorf", "lat": 47.4083, "lon": 10.2792, "lifts": 45, "region": "Bayern", "base_elev": 2690, "peak_elev": 7218},
            {"name": "Zugspitze", "lat": 47.4211, "lon": 10.9853, "lifts": 10, "region": "Bayern", "base_elev": 7635, "peak_elev": 9718},
            {"name": "Winterberg", "lat": 51.1942, "lon": 8.5333, "lifts": 26, "region": "Nordrhein-Westfalen", "base_elev": 1804, "peak_elev": 2789},
            {"name": "Feldberg", "lat": 47.8583, "lon": 8.0333, "lifts": 14, "region": "Baden-Württemberg", "base_elev": 3117, "peak_elev": 4757},
        ],
        # Japan
        "JP": [
            {"name": "Niseko United", "lat": 42.8625, "lon": 140.6869, "lifts": 38, "region": "Hokkaido", "base_elev": 787, "peak_elev": 4101},
            {"name": "Hakuba Valley", "lat": 36.6983, "lon": 137.8322, "lifts": 135, "region": "Nagano", "base_elev": 2526, "peak_elev": 5905},
            {"name": "Shiga Kogen", "lat": 36.6861, "lon": 138.4831, "lifts": 51, "region": "Nagano", "base_elev": 4593, "peak_elev": 7218},
            {"name": "Nozawa Onsen", "lat": 36.9231, "lon": 138.4408, "lifts": 21, "region": "Nagano", "base_elev": 1706, "peak_elev": 5413},
            {"name": "Rusutsu", "lat": 42.7333, "lon": 140.8833, "lifts": 18, "region": "Hokkaido", "base_elev": 656, "peak_elev": 3281},
            {"name": "Furano", "lat": 43.3433, "lon": 142.3819, "lifts": 11, "region": "Hokkaido", "base_elev": 755, "peak_elev": 3707},
            {"name": "Myoko Kogen", "lat": 36.8833, "lon": 138.1833, "lifts": 28, "region": "Niigata", "base_elev": 2461, "peak_elev": 5413},
            {"name": "Zao Onsen", "lat": 38.1667, "lon": 140.4167, "lifts": 32, "region": "Yamagata", "base_elev": 2625, "peak_elev": 5577},
            {"name": "Naeba", "lat": 36.8167, "lon": 138.7167, "lifts": 27, "region": "Niigata", "base_elev": 2953, "peak_elev": 5413},
            {"name": "Appi Kogen", "lat": 39.9333, "lon": 140.9333, "lifts": 21, "region": "Iwate", "base_elev": 1969, "peak_elev": 4593},
            {"name": "Madarao Kogen", "lat": 36.8667, "lon": 138.3167, "lifts": 18, "region": "Nagano", "base_elev": 2953, "peak_elev": 4429},
            {"name": "Kiroro", "lat": 43.0833, "lon": 140.9833, "lifts": 10, "region": "Hokkaido", "base_elev": 1640, "peak_elev": 3871},
        ],
        # Scandinavia
        "NO": [
            {"name": "Trysil", "lat": 61.3133, "lon": 12.2603, "lifts": 32, "region": "Innlandet", "base_elev": 1312, "peak_elev": 3609},
            {"name": "Hemsedal", "lat": 60.8658, "lon": 8.5697, "lifts": 21, "region": "Viken", "base_elev": 2132, "peak_elev": 5905},
            {"name": "Geilo", "lat": 60.5333, "lon": 8.2, "lifts": 20, "region": "Viken", "base_elev": 2625, "peak_elev": 3773},
            {"name": "Hafjell", "lat": 61.2333, "lon": 10.4333, "lifts": 14, "region": "Innlandet", "base_elev": 656, "peak_elev": 3609},
            {"name": "Kvitfjell", "lat": 61.4667, "lon": 10.1333, "lifts": 11, "region": "Innlandet", "base_elev": 1640, "peak_elev": 3707},
        ],
        "SE": [
            {"name": "Åre", "lat": 63.3983, "lon": 13.0778, "lifts": 42, "region": "Jämtland", "base_elev": 1247, "peak_elev": 4429},
            {"name": "Sälen", "lat": 61.1667, "lon": 13.2667, "lifts": 99, "region": "Dalarna", "base_elev": 1640, "peak_elev": 3445},
            {"name": "Vemdalen", "lat": 62.4333, "lon": 13.9167, "lifts": 21, "region": "Härjedalen", "base_elev": 1969, "peak_elev": 3281},
        ],
        "FI": [
            {"name": "Levi", "lat": 67.8, "lon": 24.8167, "lifts": 26, "region": "Lapland", "base_elev": 656, "peak_elev": 1706},
            {"name": "Ylläs", "lat": 67.55, "lon": 24.25, "lifts": 29, "region": "Lapland", "base_elev": 656, "peak_elev": 2297},
            {"name": "Ruka", "lat": 66.1667, "lon": 29.1333, "lifts": 21, "region": "Lapland", "base_elev": 656, "peak_elev": 1640},
        ],
        # Australia/New Zealand
        "AU": [
            {"name": "Perisher", "lat": -36.4, "lon": 148.4167, "lifts": 47, "region": "New South Wales", "base_elev": 5577, "peak_elev": 6890},
            {"name": "Thredbo", "lat": -36.5, "lon": 148.3, "lifts": 14, "region": "New South Wales", "base_elev": 4593, "peak_elev": 6726},
            {"name": "Falls Creek", "lat": -36.8667, "lon": 147.2833, "lifts": 14, "region": "Victoria", "base_elev": 4921, "peak_elev": 6033},
            {"name": "Mount Hotham", "lat": -37.0833, "lon": 147.1333, "lifts": 13, "region": "Victoria", "base_elev": 4921, "peak_elev": 6102},
            {"name": "Mount Buller", "lat": -37.15, "lon": 146.4333, "lifts": 22, "region": "Victoria", "base_elev": 4921, "peak_elev": 5905},
        ],
        "NZ": [
            {"name": "Queenstown (Remarkables + Coronet Peak)", "lat": -45.0378, "lon": 168.6617, "lifts": 15, "region": "Otago", "base_elev": 3609, "peak_elev": 6201},
            {"name": "Whakapapa", "lat": -39.2333, "lon": 175.55, "lifts": 14, "region": "Manawatu-Wanganui", "base_elev": 5085, "peak_elev": 7546},
            {"name": "Treble Cone", "lat": -44.6333, "lon": 168.9, "lifts": 4, "region": "Otago", "base_elev": 4429, "peak_elev": 6890},
            {"name": "Cardrona", "lat": -44.8667, "lon": 168.9333, "lifts": 7, "region": "Otago", "base_elev": 4921, "peak_elev": 6201},
        ],
        # South America
        "CL": [
            {"name": "Valle Nevado", "lat": -33.3833, "lon": -70.2833, "lifts": 14, "region": "Metropolitana", "base_elev": 9842, "peak_elev": 12303},
            {"name": "Portillo", "lat": -32.8333, "lon": -70.1333, "lifts": 14, "region": "Valparaíso", "base_elev": 9186, "peak_elev": 10925},
        ],
        "AR": [
            {"name": "Las Leñas", "lat": -35.15, "lon": -70.0833, "lifts": 14, "region": "Mendoza", "base_elev": 7546, "peak_elev": 11253},
            {"name": "Cerro Catedral", "lat": -41.1667, "lon": -71.4333, "lifts": 39, "region": "Río Negro", "base_elev": 3445, "peak_elev": 6890},
            {"name": "Chapelco", "lat": -40.2, "lon": -71.25, "lifts": 12, "region": "Neuquén", "base_elev": 3773, "peak_elev": 6201},
        ],
        # Other European
        "AD": [
            {"name": "Grandvalira", "lat": 42.5667, "lon": 1.7, "lifts": 67, "region": "Andorra", "base_elev": 5906, "peak_elev": 8858},
            {"name": "Vallnord", "lat": 42.5833, "lon": 1.5333, "lifts": 30, "region": "Andorra", "base_elev": 5249, "peak_elev": 8530},
        ],
        "ES": [
            {"name": "Baqueira-Beret", "lat": 42.6967, "lon": 0.9433, "lifts": 36, "region": "Cataluña", "base_elev": 4921, "peak_elev": 8366},
            {"name": "Sierra Nevada", "lat": 37.0958, "lon": -3.3958, "lifts": 24, "region": "Andalucía", "base_elev": 6890, "peak_elev": 11155},
            {"name": "Formigal-Panticosa", "lat": 42.7667, "lon": -0.35, "lifts": 37, "region": "Aragón", "base_elev": 4921, "peak_elev": 7546},
        ],
        "PL": [
            {"name": "Zakopane (Kasprowy Wierch)", "lat": 49.2333, "lon": 19.9833, "lifts": 17, "region": "Małopolska", "base_elev": 3281, "peak_elev": 6453},
            {"name": "Szczyrk", "lat": 49.7167, "lon": 19.0333, "lifts": 28, "region": "Śląskie", "base_elev": 1640, "peak_elev": 4101},
        ],
        "CZ": [
            {"name": "Špindlerův Mlýn", "lat": 50.7333, "lon": 15.6167, "lifts": 25, "region": "Hradec Králové", "base_elev": 2297, "peak_elev": 4265},
        ],
        "SK": [
            {"name": "Jasná", "lat": 48.9833, "lon": 19.5833, "lifts": 30, "region": "Žilina", "base_elev": 3609, "peak_elev": 6890},
        ],
        "SI": [
            {"name": "Kranjska Gora", "lat": 46.4833, "lon": 13.7833, "lifts": 18, "region": "Gorenjska", "base_elev": 2625, "peak_elev": 5577},
            {"name": "Vogel", "lat": 46.2667, "lon": 13.8333, "lifts": 8, "region": "Gorenjska", "base_elev": 4101, "peak_elev": 5577},
        ],
        "BG": [
            {"name": "Bansko", "lat": 41.8167, "lon": 23.4833, "lifts": 14, "region": "Blagoevgrad", "base_elev": 3117, "peak_elev": 8497},
            {"name": "Borovets", "lat": 42.2667, "lon": 23.6, "lifts": 12, "region": "Sofia", "base_elev": 4265, "peak_elev": 8530},
        ],
        "RO": [
            {"name": "Poiana Brașov", "lat": 45.5833, "lon": 25.55, "lifts": 12, "region": "Brașov", "base_elev": 3281, "peak_elev": 5905},
        ],
        "KR": [
            {"name": "Yongpyong", "lat": 37.6333, "lon": 128.6833, "lifts": 28, "region": "Gangwon-do", "base_elev": 2461, "peak_elev": 4921},
            {"name": "Alpensia", "lat": 37.65, "lon": 128.6833, "lifts": 6, "region": "Gangwon-do", "base_elev": 2297, "peak_elev": 4593},
            {"name": "Phoenix Park", "lat": 37.5833, "lon": 128.3167, "lifts": 21, "region": "Gangwon-do", "base_elev": 1969, "peak_elev": 4265},
            {"name": "Jisan Forest", "lat": 37.2167, "lon": 127.3167, "lifts": 10, "region": "Gyeonggi-do", "base_elev": 656, "peak_elev": 1640},
        ],
        "CN": [
            {"name": "Wanlong", "lat": 40.9, "lon": 115.4167, "lifts": 22, "region": "Hebei", "base_elev": 5085, "peak_elev": 6890},
            {"name": "Thaiwoo", "lat": 40.95, "lon": 115.4167, "lifts": 17, "region": "Hebei", "base_elev": 5413, "peak_elev": 7546},
            {"name": "Yabuli", "lat": 44.6167, "lon": 128.4667, "lifts": 17, "region": "Heilongjiang", "base_elev": 1476, "peak_elev": 4429},
            {"name": "Changbaishan", "lat": 42.05, "lon": 128.0833, "lifts": 12, "region": "Jilin", "base_elev": 2953, "peak_elev": 5413},
            {"name": "Beidahu", "lat": 43.2167, "lon": 127.4667, "lifts": 15, "region": "Jilin", "base_elev": 1804, "peak_elev": 3445},
        ],
    }
    return known_resorts


def main():
    """Main entry point."""
    print("Loading curated resort data...")
    known_resorts = load_known_resorts()

    all_resorts = []

    for country_code, resort_list in known_resorts.items():
        print(f"\nProcessing {country_code}...")
        for data in resort_list:
            if data["lifts"] < 10:
                continue

            timezone = get_timezone(data["lat"], data["lon"])

            # Use curated elevation data from known_resorts
            base_elev = data.get("base_elev", 0)
            peak_elev = data.get("peak_elev")

            resort = ResortData(
                name=data["name"],
                country=country_code,
                region=data["region"],
                latitude=round(data["lat"], 6),
                longitude=round(data["lon"], 6),
                elevation_base_ft=base_elev,
                elevation_peak_ft=peak_elev,
                lift_count=data["lifts"],
                timezone=timezone,
            )
            all_resorts.append(resort)
            vert = peak_elev - base_elev if peak_elev else 0
            print(f"  Added: {data['name']} ({data['lifts']} lifts, {vert}' vert)")

    # Sort by country, then by lift count descending
    all_resorts.sort(key=lambda r: (r.country, -r.lift_count))

    # Convert to dict format
    resorts_data = {
        "resorts": [asdict(r) for r in all_resorts]
    }

    # Write output
    output_path = Path(__file__).parent.parent / "powder" / "data" / "resorts_global.json"
    with open(output_path, "w") as f:
        json.dump(resorts_data, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Collected {len(all_resorts)} resorts total")
    print(f"Output written to: {output_path}")

    # Summary by country
    print("\nResorts by country:")
    from collections import Counter
    counts = Counter(r.country for r in all_resorts)
    for country, count in sorted(counts.items()):
        print(f"  {country}: {count}")


if __name__ == "__main__":
    main()
