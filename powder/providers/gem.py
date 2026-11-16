"""Canadian GEM model provider via Open-Meteo API (free, no API key required).

Environment Canada's GEM (global 15 km, blended with the regional and 2.5 km HRDPS models over
North America). It is the second model in the snowfall calibration: averaged with ECMWF it
balances ECMWF's high Sierra totals and low Wasatch totals. Global, so used for every resort.
"""

from ..forecast import DailyForecast
from ..resorts import SkiResort
from .base import ForecastProvider
from .open_meteo_common import daily_snowfall, fetch, request_params

MODEL = "gem_seamless"


class GEMProvider(ForecastProvider):
    """Forecast provider using the Canadian GEM model via Open-Meteo API."""

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    @property
    def name(self) -> str:
        return "GEM"

    def get_snowfall_forecast(
        self, resort: SkiResort, days: int = 7
    ) -> list[DailyForecast]:
        """Fetch snowfall forecast from GEM via Open-Meteo (up to 10 days)."""
        params = request_params(resort, min(days, 10), model=MODEL)
        return daily_snowfall(fetch(self.BASE_URL, params, self.name), self.name, resort)
