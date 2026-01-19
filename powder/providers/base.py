"""Base class for forecast providers."""

from abc import ABC, abstractmethod
from datetime import date

from ..forecast import DailyForecast
from ..resorts import SkiResort


class ForecastProvider(ABC):
    """Abstract base class for weather forecast providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the provider."""
        pass

    @abstractmethod
    def get_snowfall_forecast(
        self, resort: SkiResort, days: int = 7
    ) -> list[DailyForecast]:
        """
        Fetch snowfall forecast for a ski resort.

        Args:
            resort: The ski resort to get forecast for.
            days: Number of days to forecast (default 7).

        Returns:
            List of DailyForecast objects, one per day.
        """
        pass
