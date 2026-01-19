"""National Weather Service (NWS) API provider (free US government API)."""

from datetime import date, datetime

import requests

from ..forecast import DailyForecast
from ..resorts import SkiResort
from .base import ForecastProvider


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
            response = requests.get(url, headers=self.HEADERS, timeout=10)
            response.raise_for_status()
            data = response.json()
            props = data.get("properties", {})
            return (
                props.get("gridId"),
                props.get("gridX"),
                props.get("gridY"),
            )
        except requests.RequestException as e:
            print(f"[{self.name}] Error getting grid point: {e}")
            return None

    def get_snowfall_forecast(
        self, resort: SkiResort, days: int = 7
    ) -> list[DailyForecast]:
        """Fetch snowfall forecast from NWS."""
        grid_info = self._get_grid_point(resort.latitude, resort.longitude)
        if not grid_info:
            return []

        grid_id, grid_x, grid_y = grid_info
        url = f"{self.BASE_URL}/gridpoints/{grid_id}/{grid_x},{grid_y}"

        try:
            response = requests.get(url, headers=self.HEADERS, timeout=10)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            print(f"[{self.name}] Error fetching forecast: {e}")
            return []

        props = data.get("properties", {})
        snowfall_data = props.get("snowfallAmount", {}).get("values", [])

        # Aggregate hourly snowfall into daily totals
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
                forecast_date = dt.date()

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
