# End-to-End (E2E) Tests

Live API tests that validate Powder works correctly with real weather services. These tests hit actual APIs and are marked as `slow`.

## Overview

| Test File | Tests | Description |
|-----------|-------|-------------|
| `test_live_api.py` | 10 | Live weather API validation |

## Running E2E Tests

```bash
# All E2E tests
poetry run pytest -m e2e

# Skip slow tests (default in most runs)
poetry run pytest -m "not slow"

# E2E with verbose output
poetry run pytest -m e2e -v

# Specific provider
poetry run pytest tests/e2e/test_live_api.py::TestNWSLive
```

## Test Coverage

### Provider Tests

Each weather provider is tested against live APIs:

| Provider | Test Class | Resort Used | Max Days |
|----------|------------|-------------|----------|
| Open-Meteo | `TestOpenMeteoLive` | Park City (US) | 16 |
| ECMWF | `TestECMWFLive` | Park City (US) | 10 |
| NWS | `TestNWSLive` | Park City (US) | 7 |
| ICON | `TestICONLive` | Chamonix (FR) | 7 |
| JMA | `TestJMALive` | Niseko (JP) | 7 |
| BOM | `TestBOMLive` | Perisher (AU) | 7 |

### Tests Performed

**Forecast Data**
- Returns valid forecast data
- Source field matches provider name
- Snowfall values are non-negative
- Dates are proper `datetime.date` objects

**Historical Data** (Open-Meteo only)
- Archive API returns data
- Historical records are properly formatted

**NWS Grid Lookup**
- Two-step API works (grid point → forecast)
- Grid coordinates are valid integers

**Cross-Provider Consistency**
- All providers return consistent date formats
- All providers return numeric snowfall values
- Providers handle long forecast range requests gracefully

## Test Resorts

Tests use real resort coordinates:

```python
PARK_CITY = SkiResort(
    name="Park City",
    country="US",
    latitude=40.6514,
    longitude=-111.508,
    ...
)

CHAMONIX = SkiResort(
    name="Chamonix",
    country="FR",
    latitude=45.9237,
    longitude=6.8694,
    ...
)

NISEKO = SkiResort(
    name="Niseko",
    country="JP",
    latitude=42.8048,
    longitude=140.6874,
    ...
)

PERISHER = SkiResort(
    name="Perisher",
    country="AU",
    latitude=-36.4069,
    longitude=148.4061,
    ...
)
```

## Caching Behavior

Unlike unit tests, E2E tests **enable caching** to reduce API load:

```python
@pytest.fixture(autouse=True)
def enable_cache_for_e2e():
    """Enable caching for e2e tests to reduce API load."""
    import powder.cache as cache_module
    cache_module._cache_enabled = True
    yield
```

This helps:
- Avoid rate limiting from weather APIs
- Speed up repeated test runs
- Reduce network traffic during development

## Potential Failures

E2E tests may fail due to external factors:

| Reason | Handling |
|--------|----------|
| Rate limiting | Wait and retry, or use caching |
| Network issues | Check connectivity |
| API outages | Skip test, check API status |
| Format changes | Update parser, report issue |
| No snow data | Tests handle empty results gracefully |

## Markers

E2E tests use:
- `@pytest.mark.e2e` - All E2E tests
- `@pytest.mark.slow` - Slow/live tests

Exclude from normal test runs:
```bash
pytest -m "not slow"
```

## When to Run E2E Tests

- **Before releases** - Validate all APIs still work
- **After provider changes** - Confirm parsing still works
- **Debugging API issues** - Isolate provider problems
- **Periodically** - Catch API changes early

## Adding New E2E Tests

1. Create test in `tests/e2e/`
2. Add both `@pytest.mark.e2e` and `@pytest.mark.slow` markers
3. Use appropriate resort for the provider's region
4. Handle cases where API returns no data

Example:
```python
@pytest.mark.e2e
@pytest.mark.slow
class TestNewProviderLive:
    def test_forecast_returns_data(self):
        provider = NewProvider()
        forecasts = provider.get_snowfall_forecast(RESORT, days=3)

        # May return empty if no snow, so check conditionally
        if forecasts:
            assert all(f.source == "NewProvider" for f in forecasts)
            assert all(f.snowfall_inches >= 0 for f in forecasts)
```
