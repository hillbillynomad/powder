"""National Weather Service (NWS) API provider (free US government API).

NWS grid cells are 2.5 km, and resort coordinates sit at the base lodge, so the cell there is
often well below the skiing (Palisades' base cell is 6,280 ft; one cell up the hill is 7,380 ft
and forecasts ~40% more snow). We look up the grid cell for a nearby point at mid-mountain
instead, picked from a ring of candidates with one call to Open-Meteo's free elevation API.
Snowfall is grouped into the resort's local days (NWS times are UTC).
"""

import math
from datetime import date, datetime, timezone, tzinfo
from typing import Optional
from zoneinfo import ZoneInfo

from ..cache import get_session
from ..conditions import FT_PER_M, mid_mountain_ft
from ..forecast import DailyForecast
from ..resorts import SkiResort
from .base import ForecastProvider

ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
SEARCH_RADII_M = (1000, 2000, 3000)
SEARCH_BEARINGS = 8
DISTANCE_PENALTY_FT_PER_KM = 150  # prefer close points: 1 km further must buy 150 ft closer to mid
MIN_GAIN_FT = 300  # stay at the resort point unless mid-mountain is this far above it


def candidate_points(lat: float, lon: float) -> list[tuple[float, float, float]]:
    """(lat, lon, distance m) for the resort point and rings around it."""
    points = [(lat, lon, 0.0)]
    for r in SEARCH_RADII_M:
        for k in range(SEARCH_BEARINGS):
            b = 2 * math.pi * k / SEARCH_BEARINGS
            dlat = r * math.cos(b) / 111_320
            dlon = r * math.sin(b) / (111_320 * math.cos(math.radians(lat)))
            points.append((round(lat + dlat, 4), round(lon + dlon, 4), float(r)))
    return points


def pick_point(
    points: list[tuple[float, float, float]], elevations_m: list, target_ft: float
) -> tuple[float, float]:
    """The candidate nearest the target elevation, with a small penalty for distance."""
    best, best_score = (points[0][0], points[0][1]), math.inf
    for (lat, lon, dist), elev in zip(points, elevations_m):
        if elev is None:
            continue
        score = abs(elev * FT_PER_M - target_ft) + dist / 1000 * DISTANCE_PENALTY_FT_PER_KM
        if score < best_score:
            best, best_score = (lat, lon), score
    return best


def _local_tz(resort: SkiResort) -> tzinfo:
    try:
        return ZoneInfo(getattr(resort, "timezone", None) or "UTC")
    except Exception:
        return timezone.utc


class NWSProvider(ForecastProvider):
    """Forecast provider using NWS API."""

    BASE_URL = "https://api.weather.gov"
    HEADERS = {
        "User-Agent": "(Powder Snowfall Tracker, contact@example.com)",
        "Accept": "application/geo+json",
    }

    @property
    def name(self) -> str:
        return "NWS"

    def _get_grid_point(self, lat: float, lon: float) -> tuple[str, int, int] | None:
        """Get NWS grid point for coordinates."""
        url = f"{self.BASE_URL}/points/{lat},{lon}"
        try:
            session = get_session()
            response = session.get(url, headers=self.HEADERS, timeout=10)
            response.raise_for_status()
            data = response.json()
            props = data.get("properties", {})
            return (
                props.get("gridId"),
                props.get("gridX"),
                props.get("gridY"),
            )
        except Exception as e:
            print(f"[{self.name}] Error getting grid point: {e}")
            return None

    def query_point(self, resort: SkiResort) -> tuple[float, float]:
        """A point near the resort at about mid-mountain (the resort's own point on any failure)."""
        home = (resort.latitude, resort.longitude)
        target_ft = mid_mountain_ft(resort.elevation_base_ft, resort.elevation_peak_ft)
        if target_ft - resort.elevation_base_ft < MIN_GAIN_FT:
            return home
        points = candidate_points(resort.latitude, resort.longitude)
        try:
            response = get_session().get(
                ELEVATION_URL,
                params={
                    "latitude": ",".join(str(p[0]) for p in points),
                    "longitude": ",".join(str(p[1]) for p in points),
                },
                timeout=10,
            )
            response.raise_for_status()
            elevations = response.json().get("elevation") or []
        except Exception as e:
            print(f"[{self.name}] Elevation lookup failed, using resort point: {e}")
            return home
        if len(elevations) != len(points):
            return home
        return pick_point(points, elevations, target_ft)

    def get_snowfall_forecast(
        self, resort: SkiResort, days: int = 7
    ) -> list[DailyForecast]:
        """Fetch snowfall forecast from NWS."""
        grid_info = self._get_grid_point(*self.query_point(resort))
        if not grid_info:
            return []

        grid_id, grid_x, grid_y = grid_info
        url = f"{self.BASE_URL}/gridpoints/{grid_id}/{grid_x},{grid_y}"

        try:
            session = get_session()
            response = session.get(url, headers=self.HEADERS, timeout=10)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"[{self.name}] Error fetching forecast: {e}")
            return []

        props = data.get("properties", {})
        snowfall_data = props.get("snowfallAmount", {}).get("values", [])

        # Aggregate hourly snowfall into the resort's local days
        tz = _local_tz(resort)
        daily_totals: dict[date, float] = {}
        for entry in snowfall_data:
            valid_time = entry.get("validTime", "")
            value_mm = entry.get("value", 0) or 0

            # Parse ISO 8601 duration format (e.g., "2024-01-15T06:00:00+00:00/PT6H")
            if "/" in valid_time:
                time_str = valid_time.split("/")[0]
            else:
                time_str = valid_time

            try:
                dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                forecast_date = dt.astimezone(tz).date() if dt.tzinfo else dt.date()

                if forecast_date not in daily_totals:
                    daily_totals[forecast_date] = 0.0
                # Convert mm to inches (1 mm = 0.0393701 inches)
                daily_totals[forecast_date] += value_mm * 0.0393701
            except (ValueError, AttributeError):
                continue

        # Sort by date and limit to requested days
        today = date.today()
        forecasts = []
        for forecast_date in sorted(daily_totals.keys()):
            if forecast_date < today:
                continue
            if len(forecasts) >= days:
                break
            forecasts.append(
                DailyForecast(
                    date=forecast_date,
                    snowfall_inches=round(daily_totals[forecast_date], 1),
                    source=self.name,
                )
            )

        return forecasts
