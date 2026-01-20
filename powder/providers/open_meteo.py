"""Open-Meteo weather API provider (free, no API key required)."""

from datetime import datetime

from ..cache import get_session
from ..forecast import DailyForecast
from ..resorts import SkiResort
from .base import ForecastProvider


class OpenMeteoProvider(ForecastProvider):
    """Forecast provider using Open-Meteo API."""

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    @property
    def name(self) -> str:
        return "Open-Meteo"

    def get_snowfall_forecast(
        self, resort: SkiResort, days: int = 7
    ) -> list[DailyForecast]:
        """Fetch snowfall forecast from Open-Meteo."""
        params = {
            "latitude": resort.latitude,
            "longitude": resort.longitude,
            "daily": "snowfall_sum",
            "timezone": resort.timezone if hasattr(resort, 'timezone') else "UTC",
            "forecast_days": days,
            "past_days": 14,  # Include 14 days of historical data
        }

        try:
            session = get_session()
            response = session.get(self.BASE_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"[{self.name}] Error fetching forecast: {e}")
            return []

        forecasts = []
        daily = data.get("daily", {})
        dates = daily.get("time", [])
        snowfall_cm = daily.get("snowfall_sum", [])

        for date_str, snow_cm in zip(dates, snowfall_cm):
            forecast_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            # Convert cm to inches (1 cm = 0.393701 inches)
            snow_inches = (snow_cm or 0) * 0.393701
            forecasts.append(
                DailyForecast(
                    date=forecast_date,
                    snowfall_inches=round(snow_inches, 1),
                    source=self.name,
                )
            )

        return forecasts
