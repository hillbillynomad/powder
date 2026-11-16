"""ECMWF weather model provider via Open-Meteo API (free, no API key required).

Uses the ECMWF IFS (Integrated Forecasting System) model at 9 km, which is consistently
rated as the most accurate global weather model. See MODELS.md for details.
"""

from ..forecast import DailyForecast
from ..resorts import SkiResort
from .base import ForecastProvider
from .open_meteo_common import daily_snowfall, fetch, request_params

MODEL = "ecmwf_ifs"  # the 9 km IFS the snowfall calibration was fitted on


class ECMWFProvider(ForecastProvider):
    """Forecast provider using ECMWF model via Open-Meteo API."""

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    @property
    def name(self) -> str:
        return "ECMWF"

    def get_snowfall_forecast(
        self, resort: SkiResort, days: int = 7
    ) -> list[DailyForecast]:
        """Fetch snowfall forecast from ECMWF model via Open-Meteo."""
        # ECMWF is used out to 10 days
        params = request_params(resort, min(days, 10), model=MODEL)
        return daily_snowfall(fetch(self.BASE_URL, params, self.name), self.name, resort)
