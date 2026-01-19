"""ECMWF weather model provider via Open-Meteo API (free, no API key required).

Uses the ECMWF IFS (Integrated Forecasting System) model, which is consistently
rated as the most accurate global weather model. See MODELS.md for details.
"""

from datetime import datetime

from ..cache import get_session
from ..forecast import DailyForecast
from ..resorts import SkiResort
from .base import ForecastProvider


class ECMWFProvider(ForecastProvider):
    """Forecast provider using ECMWF model via Open-Meteo API."""

    BASE_URL = "https://api.open-meteo.com/v1/ecmwf"

    @property
    def name(self) -> str:
        return "ECMWF"

    def get_snowfall_forecast(
        self, resort: SkiResort, days: int = 7
    ) -> list[DailyForecast]:
        """Fetch snowfall forecast from ECMWF model via Open-Meteo."""
        # ECMWF endpoint supports up to 10 days
        forecast_days = min(days, 10)

        params = {
            "latitude": resort.latitude,
            "longitude": resort.longitude,
            "daily": "snowfall_sum",
            "timezone": "America/Denver",
            "forecast_days": forecast_days,
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
