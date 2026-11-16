"""Open-Meteo weather API provider (free, no API key required)."""

from datetime import date

from ..conditions import DayConditions, summarize_hourly
from ..forecast import DailyForecast
from ..resorts import SkiResort
from .base import ForecastProvider
from .open_meteo_common import daily_snowfall, fetch, request_params

# Hourly fields for snowfall (snow water + temperature for the snow ratio) and mountain
# conditions (snow quality, freezing level, wind), all on one request.
HOURLY_FIELDS = "temperature_2m,freezing_level_height,snowfall,rain,wind_gusts_10m"
MODEL = "gfs_seamless"


class OpenMeteoProvider(ForecastProvider):
    """Forecast provider using Open-Meteo API."""

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    @property
    def name(self) -> str:
        return "Open-Meteo"

    def _fetch(self, resort: SkiResort, days: int) -> dict | None:
        """One request for snowfall + hourly conditions at mid-mountain, 14 past days included.

        get_snowfall_forecast and get_conditions build identical params, so the second of the
        two is answered from the HTTP cache.
        """
        # Pinned to GFS (labelled GFS in the UI): best_match picks a different model per region,
        # and the snowfall calibration was fitted on GFS.
        params = request_params(resort, days, HOURLY_FIELDS, model=MODEL)
        params["past_days"] = 14  # Include 14 days of historical data
        return fetch(self.BASE_URL, params, self.name)

    def get_snowfall_forecast(
        self, resort: SkiResort, days: int = 7
    ) -> list[DailyForecast]:
        """Fetch snowfall forecast from Open-Meteo."""
        return daily_snowfall(self._fetch(resort, days), self.name, resort)

    def get_conditions(self, resort: SkiResort, days: int = 16) -> dict[date, DayConditions]:
        """Daily mid-mountain conditions (past 14 days + forecast), unrated."""
        data = self._fetch(resort, days)
        if not data or not data.get("hourly"):
            return {}
        return summarize_hourly(
            data["hourly"], data.get("elevation"), resort.elevation_base_ft, resort.elevation_peak_ft
        )
