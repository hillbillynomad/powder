"""Unit tests for the forecast module."""

import pytest
from datetime import date
from statistics import mean

from powder.forecast import DailyForecast, ForecastResult, calculate_avg_forecasts


@pytest.mark.unit
@pytest.mark.forecast
class TestDailyForecast:
    """Tests for DailyForecast dataclass."""

    def test_create_daily_forecast(self):
        """Test creating a DailyForecast instance."""
        forecast = DailyForecast(
            date=date(2024, 1, 15),
            snowfall_inches=5.5,
            source="Open-Meteo",
        )
        assert forecast.date == date(2024, 1, 15)
        assert forecast.snowfall_inches == 5.5
        assert forecast.source == "Open-Meteo"

    def test_forecast_with_zero_snowfall(self):
        """Test forecast with zero snowfall."""
        forecast = DailyForecast(
            date=date(2024, 1, 15),
            snowfall_inches=0.0,
            source="ECMWF",
        )
        assert forecast.snowfall_inches == 0.0

    def test_forecast_equality(self):
        """Test that two identical forecasts are equal."""
        forecast1 = DailyForecast(date=date(2024, 1, 15), snowfall_inches=5.0, source="NWS")
        forecast2 = DailyForecast(date=date(2024, 1, 15), snowfall_inches=5.0, source="NWS")
        assert forecast1 == forecast2


@pytest.mark.unit
@pytest.mark.forecast
class TestForecastResult:
    """Tests for ForecastResult and from_forecasts method."""

    def test_from_forecasts_calculates_average(self):
        """Test that from_forecasts correctly averages multiple forecasts."""
        forecasts = [
            DailyForecast(date=date(2024, 1, 15), snowfall_inches=4.0, source="Open-Meteo"),
            DailyForecast(date=date(2024, 1, 15), snowfall_inches=6.0, source="ECMWF"),
            DailyForecast(date=date(2024, 1, 15), snowfall_inches=5.0, source="NWS"),
        ]
        result = ForecastResult.from_forecasts(date(2024, 1, 15), forecasts)

        assert result is not None
        assert result.date == date(2024, 1, 15)
        assert result.avg_snowfall_inches == 5.0  # (4 + 6 + 5) / 3
        assert len(result.forecasts) == 3

    def test_from_forecasts_empty_returns_none(self):
        """Test that empty forecast list returns None."""
        result = ForecastResult.from_forecasts(date(2024, 1, 15), [])
        assert result is None

    def test_from_forecasts_single_source(self):
        """Test averaging with single source returns same value."""
        forecasts = [
            DailyForecast(date=date(2024, 1, 15), snowfall_inches=7.5, source="Open-Meteo"),
        ]
        result = ForecastResult.from_forecasts(date(2024, 1, 15), forecasts)

        assert result is not None
        assert result.avg_snowfall_inches == 7.5

    def test_from_forecasts_preserves_source_forecasts(self):
        """Test that source forecasts are preserved in result."""
        forecasts = [
            DailyForecast(date=date(2024, 1, 15), snowfall_inches=4.0, source="Open-Meteo"),
            DailyForecast(date=date(2024, 1, 15), snowfall_inches=6.0, source="ECMWF"),
        ]
        result = ForecastResult.from_forecasts(date(2024, 1, 15), forecasts)

        assert result is not None
        sources = [f.source for f in result.forecasts]
        assert "Open-Meteo" in sources
        assert "ECMWF" in sources

    def test_from_forecasts_all_zeros(self):
        """Test averaging when all sources report zero snowfall."""
        forecasts = [
            DailyForecast(date=date(2024, 1, 15), snowfall_inches=0.0, source="Open-Meteo"),
            DailyForecast(date=date(2024, 1, 15), snowfall_inches=0.0, source="ECMWF"),
        ]
        result = ForecastResult.from_forecasts(date(2024, 1, 15), forecasts)

        assert result is not None
        assert result.avg_snowfall_inches == 0.0

    def test_from_forecasts_mixed_values(self):
        """Test averaging with mixed values including zeros."""
        forecasts = [
            DailyForecast(date=date(2024, 1, 15), snowfall_inches=0.0, source="Open-Meteo"),
            DailyForecast(date=date(2024, 1, 15), snowfall_inches=10.0, source="ECMWF"),
        ]
        result = ForecastResult.from_forecasts(date(2024, 1, 15), forecasts)

        assert result is not None
        assert result.avg_snowfall_inches == 5.0  # (0 + 10) / 2


@pytest.mark.unit
@pytest.mark.forecast
class TestCalculateAvgForecasts:
    """Tests for calculate_avg_forecasts function."""

    def test_returns_sorted_by_date(self):
        """Test that results are sorted chronologically."""
        all_forecasts = {
            date(2024, 1, 17): [
                DailyForecast(date=date(2024, 1, 17), snowfall_inches=3.0, source="A")
            ],
            date(2024, 1, 15): [
                DailyForecast(date=date(2024, 1, 15), snowfall_inches=5.0, source="A")
            ],
            date(2024, 1, 16): [
                DailyForecast(date=date(2024, 1, 16), snowfall_inches=2.0, source="A")
            ],
        }
        results = calculate_avg_forecasts(all_forecasts)

        assert len(results) == 3
        assert results[0].date == date(2024, 1, 15)
        assert results[1].date == date(2024, 1, 16)
        assert results[2].date == date(2024, 1, 17)

    def test_handles_multiple_dates(self):
        """Test aggregation across multiple dates."""
        all_forecasts = {
            date(2024, 1, 15): [
                DailyForecast(date=date(2024, 1, 15), snowfall_inches=4.0, source="A"),
                DailyForecast(date=date(2024, 1, 15), snowfall_inches=6.0, source="B"),
            ],
            date(2024, 1, 16): [
                DailyForecast(date=date(2024, 1, 16), snowfall_inches=2.0, source="A"),
                DailyForecast(date=date(2024, 1, 16), snowfall_inches=4.0, source="B"),
            ],
        }
        results = calculate_avg_forecasts(all_forecasts)

        assert len(results) == 2
        assert results[0].avg_snowfall_inches == 5.0  # (4 + 6) / 2
        assert results[1].avg_snowfall_inches == 3.0  # (2 + 4) / 2

    def test_empty_dict_returns_empty_list(self):
        """Test that empty input returns empty list."""
        results = calculate_avg_forecasts({})
        assert results == []

    def test_skips_dates_with_empty_forecasts(self):
        """Test that dates with empty forecast lists are skipped."""
        all_forecasts = {
            date(2024, 1, 15): [
                DailyForecast(date=date(2024, 1, 15), snowfall_inches=5.0, source="A")
            ],
            date(2024, 1, 16): [],  # Empty list
        }
        results = calculate_avg_forecasts(all_forecasts)

        assert len(results) == 1
        assert results[0].date == date(2024, 1, 15)

    def test_handles_single_date_single_source(self):
        """Test with just one date and one source."""
        all_forecasts = {
            date(2024, 1, 15): [
                DailyForecast(date=date(2024, 1, 15), snowfall_inches=7.5, source="A")
            ],
        }
        results = calculate_avg_forecasts(all_forecasts)

        assert len(results) == 1
        assert results[0].avg_snowfall_inches == 7.5
