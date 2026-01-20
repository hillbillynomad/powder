"""Shared pytest fixtures for Powder tests."""

import json
from datetime import date
from pathlib import Path

import pytest

from powder.forecast import DailyForecast
from powder.resorts import SkiResort

# Path to fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ============================================================================
# Session-level fixtures for cache management
# ============================================================================


@pytest.fixture(autouse=True)
def disable_cache_for_tests():
    """Disable HTTP caching for all tests to ensure isolation."""
    import powder.cache as cache_module

    # Store original state
    original_session = cache_module._session
    original_enabled = cache_module._cache_enabled

    # Reset and disable cache
    cache_module._session = None
    cache_module._cache_enabled = False

    yield

    # Restore original state
    cache_module._session = original_session
    cache_module._cache_enabled = original_enabled


# ============================================================================
# Resort Fixtures
# ============================================================================


@pytest.fixture
def sample_resort() -> SkiResort:
    """A sample US resort for testing."""
    return SkiResort(
        name="Test Mountain",
        country="US",
        region="UT",
        latitude=40.6514,
        longitude=-111.5080,
        elevation_base_ft=6800,
        elevation_peak_ft=10026,
        lift_count=41,
        avg_snowfall_inches=355,
        pass_type="EPIC",
        timezone="America/Denver",
    )


@pytest.fixture
def european_resort() -> SkiResort:
    """A sample European resort for testing."""
    return SkiResort(
        name="Chamonix",
        country="FR",
        region="Haute-Savoie",
        latitude=45.9237,
        longitude=6.8694,
        elevation_base_ft=3396,
        elevation_peak_ft=12605,
        lift_count=49,
        pass_type=None,
        timezone="Europe/Paris",
    )


@pytest.fixture
def japanese_resort() -> SkiResort:
    """A sample Japanese resort for testing."""
    return SkiResort(
        name="Niseko",
        country="JP",
        region="Hokkaido",
        latitude=42.8048,
        longitude=140.6874,
        elevation_base_ft=656,
        elevation_peak_ft=4291,
        lift_count=38,
        pass_type="EPIC",
        timezone="Asia/Tokyo",
    )


@pytest.fixture
def australian_resort() -> SkiResort:
    """A sample Australian resort for testing."""
    return SkiResort(
        name="Perisher",
        country="AU",
        region="NSW",
        latitude=-36.4069,
        longitude=148.4061,
        elevation_base_ft=5577,
        elevation_peak_ft=6886,
        lift_count=47,
        pass_type="EPIC",
        timezone="Australia/Sydney",
    )


@pytest.fixture
def sample_resorts(sample_resort, european_resort, japanese_resort) -> list[SkiResort]:
    """List of sample resorts for filtering tests."""
    return [
        sample_resort,
        european_resort,
        japanese_resort,
        SkiResort(
            name="Vail",
            country="US",
            region="CO",
            latitude=39.6403,
            longitude=-106.3742,
            elevation_base_ft=8120,
            elevation_peak_ft=11570,
            lift_count=31,
            pass_type="EPIC",
            timezone="America/Denver",
        ),
        SkiResort(
            name="Deer Valley",
            country="US",
            region="UT",
            latitude=40.6375,
            longitude=-111.4783,
            elevation_base_ft=6570,
            elevation_peak_ft=9570,
            lift_count=21,
            pass_type="IKON",
            timezone="America/Denver",
        ),
    ]


@pytest.fixture
def sample_resorts_path(tmp_path, sample_resorts) -> Path:
    """Create a temporary resorts JSON file."""
    resorts_file = tmp_path / "resorts.json"
    data = {
        "resorts": [
            {
                "name": r.name,
                "country": r.country,
                "region": r.region,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "elevation_base_ft": r.elevation_base_ft,
                "elevation_peak_ft": r.elevation_peak_ft,
                "lift_count": r.lift_count,
                "pass_type": r.pass_type,
                "timezone": r.timezone,
            }
            for r in sample_resorts
        ]
    }
    resorts_file.write_text(json.dumps(data, indent=2))
    return resorts_file


# ============================================================================
# Forecast Fixtures
# ============================================================================


@pytest.fixture
def sample_daily_forecasts() -> list[DailyForecast]:
    """Sample daily forecasts from multiple providers."""
    return [
        DailyForecast(date=date(2024, 1, 15), snowfall_inches=5.0, source="Open-Meteo"),
        DailyForecast(date=date(2024, 1, 15), snowfall_inches=4.0, source="ECMWF"),
        DailyForecast(date=date(2024, 1, 15), snowfall_inches=6.0, source="NWS"),
        DailyForecast(date=date(2024, 1, 16), snowfall_inches=2.0, source="Open-Meteo"),
        DailyForecast(date=date(2024, 1, 16), snowfall_inches=3.0, source="ECMWF"),
    ]


# ============================================================================
# API Response Fixtures
# ============================================================================


@pytest.fixture
def open_meteo_response() -> dict:
    """Sample Open-Meteo API response."""
    return {
        "latitude": 40.625,
        "longitude": -111.5,
        "generationtime_ms": 0.5,
        "utc_offset_seconds": -25200,
        "timezone": "America/Denver",
        "daily": {
            "time": [
                "2024-01-15",
                "2024-01-16",
                "2024-01-17",
                "2024-01-18",
                "2024-01-19",
                "2024-01-20",
                "2024-01-21",
            ],
            "snowfall_sum": [5.0, 0.0, 2.5, 10.0, 0.0, 1.5, 0.0],  # centimeters
        },
    }


@pytest.fixture
def open_meteo_empty_response() -> dict:
    """Open-Meteo response with no snowfall data."""
    return {
        "latitude": 40.625,
        "longitude": -111.5,
        "daily": {
            "time": [],
            "snowfall_sum": [],
        },
    }


@pytest.fixture
def open_meteo_null_values_response() -> dict:
    """Open-Meteo response with null values."""
    return {
        "daily": {
            "time": ["2024-01-15", "2024-01-16", "2024-01-17"],
            "snowfall_sum": [None, 5.0, None],
        },
    }


@pytest.fixture
def nws_grid_response() -> dict:
    """Sample NWS grid point API response."""
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-111.508, 40.6514]},
        "properties": {
            "gridId": "SLC",
            "gridX": 97,
            "gridY": 175,
            "forecast": "https://api.weather.gov/gridpoints/SLC/97,175/forecast",
        },
    }


@pytest.fixture
def nws_forecast_response() -> dict:
    """Sample NWS gridpoints forecast API response."""
    return {
        "type": "Feature",
        "properties": {
            "snowfallAmount": {
                "uom": "wmoUnit:mm",
                "values": [
                    {"validTime": "2024-01-15T06:00:00+00:00/PT6H", "value": 10.0},
                    {"validTime": "2024-01-15T12:00:00+00:00/PT6H", "value": 15.0},
                    {"validTime": "2024-01-15T18:00:00+00:00/PT6H", "value": 5.0},
                    {"validTime": "2024-01-16T00:00:00+00:00/PT6H", "value": 0.0},
                    {"validTime": "2024-01-16T06:00:00+00:00/PT6H", "value": 25.0},
                    {"validTime": "2024-01-16T12:00:00+00:00/PT6H", "value": 12.0},
                ],
            },
        },
    }


@pytest.fixture
def nws_forecast_empty_response() -> dict:
    """NWS response with no snowfall data."""
    return {
        "type": "Feature",
        "properties": {
            "snowfallAmount": {
                "uom": "wmoUnit:mm",
                "values": [],
            },
        },
    }


# ============================================================================
# Helper Functions
# ============================================================================


def load_fixture(filename: str) -> dict:
    """Load a JSON fixture file."""
    fixture_path = FIXTURES_DIR / "api_responses" / filename
    with open(fixture_path) as f:
        return json.load(f)
