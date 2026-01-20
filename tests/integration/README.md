# Integration Tests

Integration tests verify that Powder's components work together correctly. These tests use mocked HTTP responses but test real interactions between modules.

## Overview

| Test File | Tests | Description |
|-----------|-------|-------------|
| `test_cli.py` | 18 | CLI workflow tests |

## Running Integration Tests

```bash
# All integration tests
poetry run pytest -m integration

# Parallel execution
poetry run pytest -m integration -n auto

# With verbose output
poetry run pytest -m integration -v

# Specific test class
poetry run pytest tests/integration/test_cli.py::TestFetchAllForecasts
```

## Test Coverage

### CLI Workflows (`test_cli.py`)

Tests the complete CLI workflows from argument parsing to output:

**Forecast Fetching**
- `TestFetchHistoricalSnowfall` - Historical data from Open-Meteo Archive
- `TestFetchAllForecasts` - Multi-provider forecast collection
  - US resorts: Open-Meteo + ECMWF + NWS
  - European resorts: Open-Meteo + ECMWF + ICON
  - Japanese resorts: Open-Meteo + ECMWF + JMA
  - Australian resorts: Open-Meteo + ECMWF + BOM

**Display & Output**
- `TestDisplayForecasts` - Console output formatting
- `TestListResorts` - Resort listing with filters

**Data Export**
- `TestBuildResortForecastData` - JSON structure building
- `TestExportJson` - File export for web UI

**Main Entry Point**
- `TestMain` - CLI argument parsing and execution
  - `--list` command
  - `--country` filter
  - `--no-cache` flag
  - `--export-json` command

## Regional Provider Selection

Integration tests verify the correct provider selection based on resort location:

| Region | Providers Used | Test Method |
|--------|---------------|-------------|
| United States | Open-Meteo, ECMWF, NWS | `test_fetches_global_providers_for_us_resort` |
| Europe | Open-Meteo, ECMWF, ICON | `test_fetches_icon_for_european_resort` |
| Japan | Open-Meteo, ECMWF, JMA | `test_fetches_jma_for_japanese_resort` |
| Australia/NZ | Open-Meteo, ECMWF, BOM | `test_fetches_bom_for_australian_resort` |

## Mocking Strategy

Integration tests mock all external HTTP APIs but allow real interactions between internal modules:

```python
def mock_all_api_endpoints():
    """Add mock responses for all API endpoints."""
    # Open-Meteo forecast
    responses.add(
        responses.GET,
        "https://api.open-meteo.com/v1/forecast",
        json=SAMPLE_FORECAST_RESPONSE,
        status=200,
    )
    # ECMWF
    responses.add(
        responses.GET,
        "https://api.open-meteo.com/v1/ecmwf",
        json=SAMPLE_FORECAST_RESPONSE,
        status=200,
    )
    # NWS (two-step)
    responses.add_callback(
        responses.GET,
        "https://api.weather.gov/points/...",
        callback=lambda req: (200, {}, json.dumps(NWS_GRID_RESPONSE)),
    )
    # ... etc
```

## Fixtures Used

From `conftest.py`:
- `sample_resort` - Park City, US (tests NWS provider)
- `european_resort` - Chamonix, France (tests ICON provider)
- `japanese_resort` - Niseko, Japan (tests JMA provider)
- `australian_resort` - Perisher, Australia (tests BOM provider)
- `sample_resorts` - List of 5 diverse resorts

## Markers

Integration tests use:
- `@pytest.mark.integration` - All integration tests
- `@pytest.mark.cli` - CLI-specific tests

Run both:
```bash
pytest -m "integration and cli"
```

## Adding New Integration Tests

1. Create test in `tests/integration/`
2. Add `@pytest.mark.integration` marker
3. Mock all HTTP endpoints with `responses`
4. Test component interactions, not just individual functions

Example:
```python
@pytest.mark.integration
@pytest.mark.cli
class TestNewWorkflow:
    @responses.activate
    def test_workflow(self, sample_resort):
        mock_all_api_endpoints()

        # Test interaction between multiple components
        data = build_resort_forecast_data(sample_resort)
        assert data["name"] == sample_resort.name
```
