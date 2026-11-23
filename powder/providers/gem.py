"""Canadian GEM model provider via Open-Meteo API (free, no API key required).

Environment Canada's GEM global (15 km), the same model for the whole range and every resort.
Not gem_seamless: that swaps in HRDPS (2.5 km) and GEM regional (10 km) over North America for
the first days, each with its own bias, and HRDPS has no archive to calibrate it on.
"""

from ..forecast import DailyForecast
from ..resorts import SkiResort
from .base import ForecastProvider
from .open_meteo_common import daily_snowfall, fetch, request_params

MODEL = "gem_global"


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
