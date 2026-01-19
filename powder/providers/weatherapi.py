"""Weather API provider using wttr.in (free, no API key required)."""

from datetime import date, datetime

import requests

from ..forecast import DailyForecast
from ..resorts import SkiResort
from .base import ForecastProvider


class WeatherAPIProvider(ForecastProvider):
    """Forecast provider using wttr.in API (wrapper around multiple sources)."""

    BASE_URL = "https://wttr.in"

    @property
    def name(self) -> str:
        return "wttr.in"

    def get_snowfall_forecast(
        self, resort: SkiResort, days: int = 7
    ) -> list[DailyForecast]:
        """Fetch snowfall forecast from wttr.in."""
        # wttr.in accepts coordinates in format "lat,lon"
        location = f"{resort.latitude},{resort.longitude}"
        url = f"{self.BASE_URL}/{location}"
        params = {"format": "j1"}  # JSON format

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            print(f"[{self.name}] Error fetching forecast: {e}")
            return []
        except ValueError as e:
            print(f"[{self.name}] Error parsing response: {e}")
            return []

        forecasts = []
        weather_data = data.get("weather", [])

        for day_data in weather_data[:days]:
            date_str = day_data.get("date")
            if not date_str:
                continue

            try:
                forecast_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                continue

            # Calculate total snowfall from hourly data
            total_snow_cm = 0.0
            for hourly in day_data.get("hourly", []):
                # totalSnow_cm is cumulative, we need the max for the day
                snow_cm = float(hourly.get("totalSnow_cm", 0) or 0)
                total_snow_cm = max(total_snow_cm, snow_cm)

            # Convert cm to inches
            snow_inches = total_snow_cm * 0.393701

            forecasts.append(
                DailyForecast(
                    date=forecast_date,
                    snowfall_inches=round(snow_inches, 1),
                    source=self.name,
                )
            )

        return forecasts
