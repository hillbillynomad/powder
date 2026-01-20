# Python Unit Tests

Fast, isolated unit tests for Powder's core Python modules. These tests use mocked HTTP responses and run without network access.

## Overview

| Module | Test File | Tests | Description |
|--------|-----------|-------|-------------|
| `powder/forecast.py` | `test_forecast.py` | 14 | Forecast data structures and averaging |
| `powder/resorts.py` | `test_resorts.py` | 27 | Resort loading, filtering, elevation |
| `powder/cache.py` | `test_cache.py` | 6 | HTTP caching functionality |
| `powder/providers/*` | `providers/*.py` | 60+ | Weather API providers |

## Running Unit Tests

```bash
# All unit tests
poetry run pytest -m unit

# Parallel execution (recommended)
poetry run pytest -m unit -n auto

# With coverage
poetry run pytest -m unit --cov=powder --cov-report=html

# Specific module
poetry run pytest tests/unit/test_forecast.py
poetry run pytest tests/unit/test_resorts.py -v
```

## Test Categories

### Forecast Tests (`test_forecast.py`)

Tests the core forecast data structures and aggregation logic:

- **DailyForecast** - Immutable forecast data for a single day
- **ForecastResult** - Collection of forecasts from a provider
- **calculate_avg_forecasts()** - Averaging across multiple providers

Key scenarios:
- Empty forecast handling
- Single vs multiple provider averaging
- Date sorting and alignment
- Edge cases (no overlap, partial data)

### Resort Tests (`test_resorts.py`)

Tests resort data loading and filtering:

- **SkiResort dataclass** - Resort attributes (name, location, elevation)
- **load_resorts()** - Loading from JSON
- **filter_resorts()** - Country, state, region, pass filtering
- **Elevation calculations** - Base, peak, vertical drop

Key scenarios:
- Filtering by country code (US, FR, JP, etc.)
- US state filtering
- Region filtering (Alps, Rockies, etc.)
- Pass filtering (EPIC, IKON)
- Partial name matching
- Elevation vertical calculation

### Cache Tests (`test_cache.py`)

Tests the HTTP caching module:

- **enable_cache() / disable_cache()** - Cache control
- **get_cached_session()** - Session management
- **Cache isolation** - Test independence

### Provider Tests (`providers/`)

Each weather provider has its own test file:

| Provider | Test File | API Pattern |
|----------|-----------|-------------|
| Open-Meteo | `test_open_meteo.py` | Single endpoint, daily data |
| ECMWF | `test_ecmwf.py` | Single endpoint, daily data |
| NWS | `test_nws.py` | Two-step: grid lookup → forecast |
| ICON | `test_icon.py` | Single endpoint, daily data |
| JMA | `test_jma.py` | Single endpoint, daily data |
| BOM | `test_bom.py` | Single endpoint, daily data |

## Mocking Strategy

### HTTP Mocking with `responses`

All HTTP requests are mocked using the `responses` library:

```python
import responses

@responses.activate
def test_provider_fetch():
    responses.add(
        responses.GET,
        "https://api.example.com/forecast",
        json={"temperature": 20, "snow": 5},
        status=200
    )

    result = provider.fetch_forecast(resort)
    assert result.forecasts[0].snow_cm == 5
```

### Time Mocking with `freezegun`

Date-dependent tests use `freezegun`:

```python
from freezegun import freeze_time

@freeze_time("2024-01-15")
def test_forecast_dates():
    result = provider.fetch_forecast(resort)
    assert result.forecasts[0].date == date(2024, 1, 15)
```

### Cache Isolation

All tests automatically disable caching via the autouse fixture in `conftest.py`:

```python
@pytest.fixture(autouse=True)
def disable_cache_for_tests():
    """Disable HTTP caching for all tests."""
    import powder.cache as cache_module
    cache_module._cache_enabled = False
    yield
```

## Markers

Unit tests use these pytest markers:

- `@pytest.mark.unit` - All unit tests
- `@pytest.mark.forecast` - Forecast-related tests
- `@pytest.mark.resorts` - Resort data tests
- `@pytest.mark.elevation` - Elevation calculation tests
- `@pytest.mark.providers` - Weather provider tests
- `@pytest.mark.cache` - Cache module tests

Combine markers for targeted runs:
```bash
pytest -m "unit and providers"
pytest -m "unit and not slow"
```

## Adding New Unit Tests

1. Create test file in appropriate location
2. Add `@pytest.mark.unit` marker
3. Add additional category markers as needed
4. Use fixtures from `conftest.py`
5. Mock all HTTP requests with `responses`

Example:
```python
import pytest
import responses

@pytest.mark.unit
@pytest.mark.forecast
class TestNewFeature:
    @responses.activate
    def test_something(self, sample_resort):
        # Test implementation
        pass
```
