"""Unit tests for ICONProvider (European regional model)."""

import pytest
import responses
from datetime import date

from powder.providers.icon import ICONProvider


@pytest.fixture
def provider():
    """Create ICONProvider instance."""
    return ICONProvider()


@pytest.mark.unit
@pytest.mark.providers
class TestICONProvider:
    """Tests for ICONProvider."""

    def test_provider_name(self, provider):
        """Test provider name property."""
        assert provider.name == "ICON"

    @responses.activate
    def test_get_snowfall_forecast_success(
        self, provider, european_resort, open_meteo_response
    ):
        """Test successful forecast fetch for European resort."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/dwd-icon",
            json=open_meteo_response,
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(european_resort, days=7)

        assert len(forecasts) == 7
        assert all(f.source == "ICON" for f in forecasts)

    @responses.activate
    def test_forecast_days_capped_at_7(self, provider, european_resort):
        """Test that forecast_days is capped at 7 for ICON."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/dwd-icon",
            json={"daily": {"time": [], "snowfall_sum": []}},
            status=200,
        )

        provider.get_snowfall_forecast(european_resort, days=16)

        request = responses.calls[0].request
        assert "forecast_days=7" in request.url

    @responses.activate
    def test_uses_dwd_icon_endpoint(self, provider, european_resort):
        """Test that DWD ICON endpoint is used."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/dwd-icon",
            json={"daily": {"time": [], "snowfall_sum": []}},
            status=200,
        )

        provider.get_snowfall_forecast(european_resort, days=7)

        assert "dwd-icon" in responses.calls[0].request.url

    @responses.activate
    def test_handles_api_error(self, provider, european_resort):
        """Test graceful handling of API errors."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/dwd-icon",
            status=500,
        )

        forecasts = provider.get_snowfall_forecast(european_resort, days=7)

        assert forecasts == []

    @responses.activate
    def test_cm_to_inches_conversion(self, provider, european_resort):
        """Test centimeters to inches conversion."""
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/dwd-icon",
            json={
                "daily": {
                    "time": ["2024-01-15"],
                    "snowfall_sum": [25.4],  # 10 inches
                }
            },
            status=200,
        )

        forecasts = provider.get_snowfall_forecast(european_resort, days=1)

        assert forecasts[0].snowfall_inches == pytest.approx(10.0, abs=0.1)
