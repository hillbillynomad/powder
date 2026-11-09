"""Open-Meteo weather API provider (free, no API key required)."""

from datetime import date, datetime

from ..cache import get_session
from ..conditions import DayConditions, summarize_hourly
from ..forecast import DailyForecast
from ..resorts import SkiResort
from .base import ForecastProvider

# Hourly fields for mountain conditions (snow quality, freezing level, wind). They ride along on
# the same request as the daily snowfall, so conditions never cost a second network call.
HOURLY_FIELDS = "temperature_2m,freezing_level_height,snowfall,rain,wind_gusts_10m"


class OpenMeteoProvider(ForecastProvider):
    """Forecast provider using Open-Meteo API."""

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    @property
    def name(self) -> str:
        return "Open-Meteo"

    def _fetch(self, resort: SkiResort, days: int) -> dict | None:
        """One request for daily snowfall + hourly conditions, 14 past days included.

        get_snowfall_forecast and get_conditions build identical params, so the second of the
        two is answered from the HTTP cache.
        """
        params = {
            "latitude": resort.latitude,
            "longitude": resort.longitude,
            "daily": "snowfall_sum",
            "hourly": HOURLY_FIELDS,
            "timezone": resort.timezone if hasattr(resort, 'timezone') else "UTC",
            "forecast_days": days,
            "past_days": 14,  # Include 14 days of historical data
        }
        try:
            session = get_session()
            response = session.get(self.BASE_URL, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"[{self.name}] Error fetching forecast: {e}")
            return None

    def get_snowfall_forecast(
        self, resort: SkiResort, days: int = 7
    ) -> list[DailyForecast]:
        """Fetch snowfall forecast from Open-Meteo."""
        data = self._fetch(resort, days)
        if data is None:
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

    def get_conditions(self, resort: SkiResort, days: int = 16) -> dict[date, DayConditions]:
        """Daily mid-mountain conditions (past 14 days + forecast), unrated."""
        data = self._fetch(resort, days)
        if not data or not data.get("hourly"):
            return {}
        return summarize_hourly(
            data["hourly"], data.get("elevation"), resort.elevation_base_ft, resort.elevation_peak_ft
        )
