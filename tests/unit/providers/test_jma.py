"""Unit tests for JMAProvider (Japanese regional model)."""

import pytest
import responses
from datetime import date

from powder.providers.jma import JMAProvider


@pytest.fixture
def provider():
    """Create JMAProvider instance."""
    return JMAProvider()


@pytest.mark.unit
@pytest.mark.providers
class TestJMAProvider:
    """Tests for JMAProvider."""

    def test_provider_name(self, provider):
        """Test provider name property."""
        assert provider.name == "JMA"

    @responses.activate
    def test_get_snowfall_forecast_success(
        self, provider, japanese_resort, open_meteo_response
    ):
        """Test successful forecast fetch for Japanese resort."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/jma",
            json=open_meteo_response,
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(japanese_resort, days=7)

        assert len(forecasts) == 7
        assert all(f.source == "JMA" for f in forecasts)

    @responses.activate
    def test_forecast_days_capped_at_7(self, provider, japanese_resort):
        """Test that forecast_days is capped at 7 for JMA."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/jma",
            json={"daily": {"time": [], "snowfall_sum": []}},
            status=200,
        )

        provider.get_snowfall_forecast(japanese_resort, days=16)

        request = responses.calls[0].request
        assert "forecast_days=7" in request.url

    @responses.activate
    def test_uses_jma_endpoint(self, provider, japanese_resort):
        """Test that JMA endpoint is used."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/jma",
            json={"daily": {"time": [], "snowfall_sum": []}},
            status=200,
        )

        provider.get_snowfall_forecast(japanese_resort, days=7)

        assert "/jma" in responses.calls[0].request.url

    @responses.activate
    def test_handles_api_error(self, provider, japanese_resort):
        """Test graceful handling of API errors."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/jma",
            status=500,
        )

        forecasts = provider.get_snowfall_forecast(japanese_resort, days=7)

        assert forecasts == []

    @responses.activate
    def test_cm_to_inches_conversion(self, provider, japanese_resort):
        """Test centimeters to inches conversion."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/jma",
            json={
                "daily": {
                    "time": ["2024-01-15"],
                    "snowfall_sum": [50.8],  # 20 inches
                }
            },
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(japanese_resort, days=1)

        assert forecasts[0].snowfall_inches == pytest.approx(20.0, abs=0.1)

    @responses.activate
    def test_uses_resort_timezone(self, provider, japanese_resort):
        """Test that resort's timezone is passed to API."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/jma",
            json={"daily": {"time": [], "snowfall_sum": []}},
            status=200,
        )

        provider.get_snowfall_forecast(japanese_resort, days=7)

        request = responses.calls[0].request
        assert "Asia" in request.url and "Tokyo" in request.url
