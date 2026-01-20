"""Unit tests for BOMProvider (Australian/NZ regional model)."""

import pytest
import responses
from datetime import date

from powder.providers.bom import BOMProvider


@pytest.fixture
def provider():
    """Create BOMProvider instance."""
    return BOMProvider()


@pytest.mark.unit
@pytest.mark.providers
class TestBOMProvider:
    """Tests for BOMProvider."""

    def test_provider_name(self, provider):
        """Test provider name property."""
        assert provider.name == "BOM"

    @responses.activate
    def test_get_snowfall_forecast_success(
        self, provider, australian_resort, open_meteo_response
    ):
        """Test successful forecast fetch for Australian resort."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/bom",
            json=open_meteo_response,
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(australian_resort, days=7)

        assert len(forecasts) == 7
        assert all(f.source == "BOM" for f in forecasts)

    @responses.activate
    def test_forecast_days_capped_at_7(self, provider, australian_resort):
        """Test that forecast_days is capped at 7 for BOM."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/bom",
            json={"daily": {"time": [], "snowfall_sum": []}},
            status=200,
        )

        provider.get_snowfall_forecast(australian_resort, days=16)

        request = responses.calls[0].request
        assert "forecast_days=7" in request.url

    @responses.activate
    def test_uses_bom_endpoint(self, provider, australian_resort):
        """Test that BOM endpoint is used."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/bom",
            json={"daily": {"time": [], "snowfall_sum": []}},
            status=200,
        )

        provider.get_snowfall_forecast(australian_resort, days=7)

        assert "/bom" in responses.calls[0].request.url

    @responses.activate
    def test_handles_api_error(self, provider, australian_resort):
        """Test graceful handling of API errors."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/bom",
            status=500,
        )

        forecasts = provider.get_snowfall_forecast(australian_resort, days=7)

        assert forecasts == []

    @responses.activate
    def test_cm_to_inches_conversion(self, provider, australian_resort):
        """Test centimeters to inches conversion."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/bom",
            json={
                "daily": {
                    "time": ["2024-01-15"],
                    "snowfall_sum": [2.54],  # 1 inch
                }
            },
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(australian_resort, days=1)

        assert forecasts[0].snowfall_inches == pytest.approx(1.0, abs=0.1)

    @responses.activate
    def test_handles_null_values(self, provider, australian_resort):
        """Test handling of null snowfall values."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/bom",
            json={
                "daily": {
                    "time": ["2024-01-15", "2024-01-16"],
                    "snowfall_sum": [None, 5.0],
                }
            },
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(australian_resort, days=2)

        assert len(forecasts) == 2
        assert forecasts[0].snowfall_inches == 0.0
        assert forecasts[1].snowfall_inches == pytest.approx(2.0, abs=0.1)

    @responses.activate
    def test_uses_resort_timezone(self, provider, australian_resort):
        """Test that resort's timezone is passed to API."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/bom",
            json={"daily": {"time": [], "snowfall_sum": []}},
            status=200,
        )

        provider.get_snowfall_forecast(australian_resort, days=7)

        request = responses.calls[0].request
        assert "Australia" in request.url and "Sydney" in request.url
