"""Unit tests for OpenMeteoProvider with mocked HTTP responses."""

import pytest
import responses
from datetime import date

from powder.providers.open_meteo import OpenMeteoProvider
from powder.resorts import SkiResort


@pytest.fixture
def provider():
    """Create OpenMeteoProvider instance."""
    return OpenMeteoProvider()


@pytest.mark.unit
@pytest.mark.providers
class TestOpenMeteoProvider:
    """Tests for OpenMeteoProvider."""

    def test_provider_name(self, provider):
        """Test provider name property."""
        assert provider.name == "Open-Meteo"

    @responses.activate
    def test_get_snowfall_forecast_success(
        self, provider, sample_resort, open_meteo_response
    ):
        """Test successful forecast fetch with mocked response."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/forecast",
            json=open_meteo_response,
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(sample_resort, days=7)

        assert len(forecasts) == 7
        assert all(f.source == "Open-Meteo" for f in forecasts)
        assert forecasts[0].date == date(2024, 1, 15)

    @responses.activate
    def test_cm_to_inches_conversion(self, provider, sample_resort):
        """Test centimeters to inches conversion accuracy."""
        # 10 cm should convert to ~3.9 inches
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/forecast",
            json={
                "daily": {
                    "time": ["2024-01-15"],
                    "snowfall_sum": [10.0],  # 10 cm
                }
            },
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(sample_resort, days=1)

        assert len(forecasts) == 1
        # 10 cm * 0.393701 = 3.93701, rounded to 3.9
        assert forecasts[0].snowfall_inches == pytest.approx(3.9, abs=0.1)

    @responses.activate
    def test_conversion_precision(self, provider, sample_resort):
        """Test various conversion values."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/forecast",
            json={
                "daily": {
                    "time": ["2024-01-15", "2024-01-16", "2024-01-17"],
                    "snowfall_sum": [2.54, 25.4, 0.254],  # 1 inch, 10 inches, 0.1 inches
                }
            },
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(sample_resort, days=3)

        assert forecasts[0].snowfall_inches == pytest.approx(1.0, abs=0.1)
        assert forecasts[1].snowfall_inches == pytest.approx(10.0, abs=0.1)
        assert forecasts[2].snowfall_inches == pytest.approx(0.1, abs=0.1)

    @responses.activate
    def test_handles_null_snowfall_values(
        self, provider, sample_resort, open_meteo_null_values_response
    ):
        """Test handling of null/None snowfall values."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/forecast",
            json=open_meteo_null_values_response,
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(sample_resort, days=3)

        assert len(forecasts) == 3
        assert forecasts[0].snowfall_inches == 0.0  # None becomes 0
        assert forecasts[1].snowfall_inches == pytest.approx(2.0, abs=0.1)  # 5 cm
        assert forecasts[2].snowfall_inches == 0.0  # None becomes 0

    @responses.activate
    def test_handles_empty_response(
        self, provider, sample_resort, open_meteo_empty_response
    ):
        """Test handling of empty response."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/forecast",
            json=open_meteo_empty_response,
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(sample_resort, days=7)

        assert forecasts == []

    @responses.activate
    def test_handles_api_error(self, provider, sample_resort):
        """Test graceful handling of API errors."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/forecast",
            status=500,
        )

        forecasts = provider.get_snowfall_forecast(sample_resort, days=7)

        assert forecasts == []

    @responses.activate
    def test_handles_network_timeout(self, provider, sample_resort):
        """Test handling of network timeout."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/forecast",
            body=Exception("Connection timeout"),
        )

        forecasts = provider.get_snowfall_forecast(sample_resort, days=7)

        assert forecasts == []

    @responses.activate
    def test_handles_missing_daily_key(self, provider, sample_resort):
        """Test handling of response missing 'daily' key."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/forecast",
            json={"latitude": 40.0, "longitude": -111.0},  # No 'daily' key
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(sample_resort, days=7)

        assert forecasts == []

    @responses.activate
    def test_passes_correct_parameters(self, provider, sample_resort):
        """Test that correct parameters are passed to API."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/forecast",
            json={"daily": {"time": [], "snowfall_sum": []}},
            status=200,
        )

        provider.get_snowfall_forecast(sample_resort, days=10)

        request = responses.calls[0].request
        assert f"latitude={sample_resort.latitude}" in request.url
        assert f"longitude={sample_resort.longitude}" in request.url
        assert "daily=snowfall_sum" in request.url
        assert "forecast_days=10" in request.url
        # URL encoding converts / to %2F
        assert "timezone=America" in request.url
        assert "Denver" in request.url

    @responses.activate
    def test_uses_resort_timezone(self, provider):
        """Test that resort's timezone is used in API call."""
        resort = SkiResort(
            name="Test",
            country="FR",
            region="Savoie",
            latitude=45.0,
            longitude=6.0,
            elevation_base_ft=5000,
            timezone="Europe/Paris",
        )

        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/forecast",
            json={"daily": {"time": [], "snowfall_sum": []}},
            status=200,
        )

        provider.get_snowfall_forecast(resort, days=7)

        request = responses.calls[0].request
        assert "timezone=Europe%2FParis" in request.url or "timezone=Europe/Paris" in request.url


@pytest.mark.unit
@pytest.mark.providers
class TestOpenMeteoWithPastDays:
    """Tests for OpenMeteoProvider with past_days parameter."""

    @responses.activate
    def test_includes_past_days_parameter(self, provider, sample_resort):
        """Test that past_days=14 is included in API request."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/forecast",
            json={"daily": {"time": [], "snowfall_sum": []}},
            status=200,
        )

        provider.get_snowfall_forecast(sample_resort, days=16)

        request = responses.calls[0].request
        assert "past_days=14" in request.url
