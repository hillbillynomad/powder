"""Snowfall forecast data models and calculations."""

from dataclasses import dataclass
from datetime import date
from statistics import mean
from typing import Optional


@dataclass
class DailyForecast:
    """Snowfall forecast for a single day."""
    date: date
    snowfall_inches: float
    source: str


@dataclass
class ForecastResult:
    """Aggregated forecast result with average calculation."""
    date: date
    forecasts: list[DailyForecast]
    avg_snowfall_inches: float

    @classmethod
    def from_forecasts(cls, target_date: date, forecasts: list[DailyForecast]) -> Optional["ForecastResult"]:
        """Create a ForecastResult from multiple forecasts for the same date."""
        if not forecasts:
            return None

        snowfall_values = [f.snowfall_inches for f in forecasts]
        avg_value = mean(snowfall_values)

        return cls(
            date=target_date,
            forecasts=forecasts,
            avg_snowfall_inches=avg_value,
        )


def calculate_avg_forecasts(
    all_forecasts: dict[date, list[DailyForecast]]
) -> list[ForecastResult]:
    """Calculate average forecasts across all sources for each date."""
    results = []
    for target_date in sorted(all_forecasts.keys()):
        forecasts = all_forecasts[target_date]
        result = ForecastResult.from_forecasts(target_date, forecasts)
        if result:
            results.append(result)
    return results
