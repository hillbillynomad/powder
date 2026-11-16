"""BOM (Bureau of Meteorology) weather model provider via Open-Meteo API.

Uses the Australian Bureau of Meteorology ACCESS model which provides
excellent resolution (6km) for Australia and New Zealand ski regions.
"""

from ..forecast import DailyForecast
from ..resorts import SkiResort
from .base import ForecastProvider
from .open_meteo_common import daily_snowfall, fetch, request_params


class BOMProvider(ForecastProvider):
    """Forecast provider using BOM ACCESS model via Open-Meteo API."""

    BASE_URL = "https://api.open-meteo.com/v1/bom"

    @property
    def name(self) -> str:
        return "BOM"

    def get_snowfall_forecast(
        self, resort: SkiResort, days: int = 7
    ) -> list[DailyForecast]:
        """Fetch snowfall forecast from BOM model via Open-Meteo."""
        # BOM endpoint supports up to 7 days
        params = request_params(resort, min(days, 7))
        return daily_snowfall(fetch(self.BASE_URL, params, self.name), self.name, resort)
