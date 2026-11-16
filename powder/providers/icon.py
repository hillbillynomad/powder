"""DWD ICON weather model provider via Open-Meteo API (free, no API key required).

Uses the German Weather Service (DWD) ICON model, which provides excellent
resolution (2.2-11km) for European mountain terrain. Best for Alpine forecasts.
"""

from ..forecast import DailyForecast
from ..resorts import SkiResort
from .base import ForecastProvider
from .open_meteo_common import daily_snowfall, fetch, request_params


class ICONProvider(ForecastProvider):
    """Forecast provider using DWD ICON model via Open-Meteo API."""

    BASE_URL = "https://api.open-meteo.com/v1/dwd-icon"

    @property
    def name(self) -> str:
        return "ICON"

    def get_snowfall_forecast(
        self, resort: SkiResort, days: int = 7
    ) -> list[DailyForecast]:
        """Fetch snowfall forecast from ICON model via Open-Meteo."""
        # ICON endpoint supports up to 7 days
        params = request_params(resort, min(days, 7))
        return daily_snowfall(fetch(self.BASE_URL, params, self.name), self.name, resort)
