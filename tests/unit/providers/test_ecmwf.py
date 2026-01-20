"""Unit tests for ECMWFProvider."""

import pytest
import responses
from datetime import date

from powder.providers.ecmwf import ECMWFProvider


@pytest.fixture
def provider():
    """Create ECMWFProvider instance."""
    return ECMWFProvider()


@pytest.mark.unit
@pytest.mark.providers
class TestECMWFProvider:
    """Tests for ECMWFProvider."""

    def test_provider_name(self, provider):
        """Test provider name property."""
        assert provider.name == "ECMWF"

    @responses.activate
    def test_get_snowfall_forecast_success(
        self, provider, sample_resort, open_meteo_response
    ):
        """Test successful forecast fetch."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/ecmwf",
            json=open_meteo_response,
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(sample_resort, days=7)

        assert len(forecasts) == 7
        assert all(f.source == "ECMWF" for f in forecasts)

    @responses.activate
    def test_forecast_days_capped_at_10(self, provider, sample_resort):
        """Test that forecast_days is capped at 10."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/ecmwf",
            json={"daily": {"time": [], "snowfall_sum": []}},
            status=200,
        )

        provider.get_snowfall_forecast(sample_resort, days=16)

        request = responses.calls[0].request
        assert "forecast_days=10" in request.url

    @responses.activate
    def test_uses_ecmwf_endpoint(self, provider, sample_resort):
        """Test that ECMWF endpoint is used."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/ecmwf",
            json={"daily": {"time": [], "snowfall_sum": []}},
            status=200,
        )

        provider.get_snowfall_forecast(sample_resort, days=7)

        assert "ecmwf" in responses.calls[0].request.url

    @responses.activate
    def test_handles_api_error(self, provider, sample_resort):
        """Test graceful handling of API errors."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/ecmwf",
            status=500,
        )

        forecasts = provider.get_snowfall_forecast(sample_resort, days=7)

        assert forecasts == []

    @responses.activate
    def test_cm_to_inches_conversion(self, provider, sample_resort):
        """Test centimeters to inches conversion."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/ecmwf",
            json={
                "daily": {
                    "time": ["2024-01-15"],
                    "snowfall_sum": [10.0],
                }
            },
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(sample_resort, days=1)

        assert forecasts[0].snowfall_inches == pytest.approx(3.9, abs=0.1)
