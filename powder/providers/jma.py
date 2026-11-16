"""JMA (Japan Meteorological Agency) weather model provider via Open-Meteo API.

Uses the JMA GSM model which provides good resolution (20km) for Japan
and surrounding regions. Best for Japanese ski resort forecasts.
"""

from ..forecast import DailyForecast
from ..resorts import SkiResort
from .base import ForecastProvider
from .open_meteo_common import daily_snowfall, fetch, request_params


class JMAProvider(ForecastProvider):
    """Forecast provider using JMA model via Open-Meteo API."""

    BASE_URL = "https://api.open-meteo.com/v1/jma"

    @property
    def name(self) -> str:
        return "JMA"

    def get_snowfall_forecast(
        self, resort: SkiResort, days: int = 7
    ) -> list[DailyForecast]:
        """Fetch snowfall forecast from JMA model via Open-Meteo."""
        # JMA endpoint supports up to 7 days
        params = request_params(resort, min(days, 7))
        return daily_snowfall(fetch(self.BASE_URL, params, self.name), self.name, resort)
