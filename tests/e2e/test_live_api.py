"""End-to-end tests with live APIs.

These tests hit real weather APIs and are marked as 'slow'.
Run them selectively with: pytest -m e2e

Note: These tests may fail due to:
- Rate limiting from APIs
- Network issues
- Temporary API outages
- API response format changes
"""

import pytest
from datetime import date

from powder.providers import (
    OpenMeteoProvider,
    ECMWFProvider,
    NWSProvider,
    ICONProvider,
    JMAProvider,
    BOMProvider,
)
from powder.resorts import PARK_CITY, SkiResort


# Sample resorts for different regions
CHAMONIX = SkiResort(
    name="Chamonix",
    country="FR",
    region="Haute-Savoie",
    latitude=45.9237,
    longitude=6.8694,
    elevation_base_ft=3396,
    timezone="Europe/Paris",
)

NISEKO = SkiResort(
    name="Niseko",
    country="JP",
    region="Hokkaido",
    latitude=42.8048,
    longitude=140.6874,
    elevation_base_ft=656,
    timezone="Asia/Tokyo",
)

PERISHER = SkiResort(
    name="Perisher",
    country="AU",
    region="NSW",
    latitude=-36.4069,
    longitude=148.4061,
    elevation_base_ft=5577,
    timezone="Australia/Sydney",
)


@pytest.fixture(autouse=True)
def enable_cache_for_e2e():
    """Enable caching for e2e tests to reduce API load."""
    import powder.cache as cache_module
    cache_module._cache_enabled = True
    cache_module._session = None
    yield


@pytest.mark.e2e
@pytest.mark.slow
class TestOpenMeteoLive:
    """Live tests for Open-Meteo API."""

    def test_forecast_returns_data(self):
        """Test that Open-Meteo returns forecast data."""
        provider = OpenMeteoProvider()
        forecasts = provider.get_snowfall_forecast(PARK_CITY, days=3)

        assert len(forecasts) > 0
        assert all(f.source == "Open-Meteo" for f in forecasts)
        assert all(f.snowfall_inches >= 0 for f in forecasts)
        assert all(isinstance(f.date, date) for f in forecasts)

    def test_forecast_includes_past_days(self):
        """Test that Open-Meteo returns historical data via past_days parameter."""
        provider = OpenMeteoProvider()
        forecasts = provider.get_snowfall_forecast(PARK_CITY, days=7)

        # With past_days=14, we should get more days than just the forecast_days
        # The response should include both historical (past) and forecast (future) data
        assert len(forecasts) > 7  # Should include 14 past days + 7 forecast days


@pytest.mark.e2e
@pytest.mark.slow
class TestECMWFLive:
    """Live tests for ECMWF API."""

    def test_forecast_returns_data(self):
        """Test that ECMWF returns forecast data."""
        provider = ECMWFProvider()
        forecasts = provider.get_snowfall_forecast(PARK_CITY, days=3)

        assert len(forecasts) > 0
        assert all(f.source == "ECMWF" for f in forecasts)
        assert all(f.snowfall_inches >= 0 for f in forecasts)


@pytest.mark.e2e
@pytest.mark.slow
class TestNWSLive:
    """Live tests for NWS API (US only)."""

    def test_forecast_returns_data_for_us_resort(self):
        """Test that NWS returns forecast data for US resorts."""
        provider = NWSProvider()
        forecasts = provider.get_snowfall_forecast(PARK_CITY, days=3)

        # NWS may not always have snow data, but should return something
        if forecasts:
            assert all(f.source == "NWS" for f in forecasts)
            assert all(f.snowfall_inches >= 0 for f in forecasts)

    def test_grid_point_lookup_works(self):
        """Test that NWS grid point lookup works."""
        provider = NWSProvider()
        grid_info = provider._get_grid_point(PARK_CITY.latitude, PARK_CITY.longitude)

        # Should return grid info for US coordinates
        assert grid_info is not None
        grid_id, grid_x, grid_y = grid_info
        assert grid_id is not None
        assert isinstance(grid_x, int)
        assert isinstance(grid_y, int)


@pytest.mark.e2e
@pytest.mark.slow
class TestICONLive:
    """Live tests for ICON API (Europe)."""

    def test_forecast_returns_data_for_european_resort(self):
        """Test that ICON returns forecast data for European resorts."""
        provider = ICONProvider()
        forecasts = provider.get_snowfall_forecast(CHAMONIX, days=3)

        assert len(forecasts) > 0
        assert all(f.source == "ICON" for f in forecasts)
        assert all(f.snowfall_inches >= 0 for f in forecasts)


@pytest.mark.e2e
@pytest.mark.slow
class TestJMALive:
    """Live tests for JMA API (Japan)."""

    def test_forecast_returns_data_for_japanese_resort(self):
        """Test that JMA returns forecast data for Japanese resorts."""
        provider = JMAProvider()
        forecasts = provider.get_snowfall_forecast(NISEKO, days=3)

        assert len(forecasts) > 0
        assert all(f.source == "JMA" for f in forecasts)
        assert all(f.snowfall_inches >= 0 for f in forecasts)


@pytest.mark.e2e
@pytest.mark.slow
class TestBOMLive:
    """Live tests for BOM API (Australia/NZ)."""

    def test_forecast_returns_data_for_australian_resort(self):
        """Test that BOM returns forecast data for Australian resorts."""
        provider = BOMProvider()
        forecasts = provider.get_snowfall_forecast(PERISHER, days=3)

        assert len(forecasts) > 0
        assert all(f.source == "BOM" for f in forecasts)
        assert all(f.snowfall_inches >= 0 for f in forecasts)


@pytest.mark.e2e
@pytest.mark.slow
class TestProviderConsistency:
    """Cross-provider consistency tests."""

    def test_all_providers_return_same_date_format(self):
        """Test that all providers return consistent date objects."""
        providers = [
            (OpenMeteoProvider(), PARK_CITY),
            (ECMWFProvider(), PARK_CITY),
            (ICONProvider(), CHAMONIX),
            (JMAProvider(), NISEKO),
            (BOMProvider(), PERISHER),
        ]

        for provider, resort in providers:
            forecasts = provider.get_snowfall_forecast(resort, days=3)
            if forecasts:
                for f in forecasts:
                    assert isinstance(f.date, date), f"{provider.name} returned non-date"
                    assert isinstance(f.snowfall_inches, (int, float)), f"{provider.name} returned non-numeric snowfall"

    def test_providers_handle_long_forecast_range(self):
        """Test providers handle requests for long forecast ranges."""
        providers = [
            (OpenMeteoProvider(), 16, PARK_CITY),  # Max 16 days
            (ECMWFProvider(), 10, PARK_CITY),  # Max 10 days
            (ICONProvider(), 7, CHAMONIX),  # Max 7 days
            (JMAProvider(), 7, NISEKO),  # Max 7 days
            (BOMProvider(), 7, PERISHER),  # Max 7 days
        ]

        for provider, max_days, resort in providers:
            forecasts = provider.get_snowfall_forecast(resort, days=30)

            # Should return data, capped at provider's max
            if forecasts:
                assert len(forecasts) <= max_days + 1, f"{provider.name} returned too many days"
