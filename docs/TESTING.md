# Powder Testing Guide

Comprehensive testing documentation for the Powder ski resort snowfall forecast tracker.

## Overview

Powder uses a multi-tier testing strategy:

| Test Type | Tool | Location | Speed |
|-----------|------|----------|-------|
| Python Unit Tests | pytest | `tests/unit/` | Fast |
| Python Integration Tests | pytest | `tests/integration/` | Medium |
| Python E2E (Live API) Tests | pytest | `tests/e2e/` | Slow |
| Web Unit Tests | Vitest | `tests/web/unit/` | Fast |
| Web E2E Tests | Playwright | `tests/web/e2e/` | Slow |

## Quick Start

### Run All Python Tests
```bash
poetry run pytest
```

### Run Python Tests in Parallel
```bash
poetry run pytest -n auto
```

### Run Web Unit Tests
```bash
cd tests/web
npm install
npm test
```

### Run Web E2E Tests
```bash
cd tests/web
npm install
npx playwright install
npm run test:e2e
```

## Test Categories (Python)

Tests are organized using pytest markers for selective execution:

### By Test Type

| Marker | Description | Command |
|--------|-------------|---------|
| `unit` | Fast isolated tests | `pytest -m unit` |
| `integration` | Component interaction | `pytest -m integration` |
| `e2e` | Live API tests | `pytest -m e2e` |
| `slow` | Slow tests (skip default) | `pytest -m "not slow"` |

### By Component

| Marker | Coverage | Command |
|--------|----------|---------|
| `providers` | Weather API providers | `pytest -m providers` |
| `forecast` | Forecast aggregation | `pytest -m forecast` |
| `resorts` | Resort data/filtering | `pytest -m resorts` |
| `elevation` | Elevation calculations | `pytest -m elevation` |
| `cli` | CLI commands | `pytest -m cli` |
| `cache` | HTTP caching | `pytest -m cache` |

### Combined Filters

```bash
# Unit tests for providers only
pytest -m "unit and providers"

# All tests except slow ones
pytest -m "not slow"

# Integration tests for CLI
pytest -m "integration and cli"
```

## Running Specific Tests

```bash
# Single test file
poetry run pytest tests/unit/test_forecast.py

# Single test class
poetry run pytest tests/unit/test_forecast.py::TestForecastResult

# Single test function
poetry run pytest tests/unit/test_forecast.py::TestForecastResult::test_from_forecasts_calculates_average

# Tests matching a pattern
poetry run pytest -k "nws"

# With verbose output
poetry run pytest -v

# Show print statements
poetry run pytest -s
```

## Parallel Execution

### Python Tests (pytest-xdist)

```bash
# Auto-detect CPU count
poetry run pytest -n auto

# Specific number of workers
poetry run pytest -n 4

# Distribute by file (faster for many small tests)
poetry run pytest -n auto --dist loadfile

# Distribute by test (better load balancing)
poetry run pytest -n auto --dist loadscope
```

### Web E2E Tests (Playwright)

```bash
# Run tests in parallel (default)
npx playwright test

# Specific number of workers
npx playwright test --workers=4

# Run specific browser only
npx playwright test --project=chromium
```

## Coverage

### Python Coverage

```bash
# Run with coverage report
poetry run pytest --cov=powder --cov-report=term-missing

# Generate HTML report
poetry run pytest --cov=powder --cov-report=html
# Open htmlcov/index.html

# Check coverage threshold (75% required)
poetry run pytest --cov=powder --cov-fail-under=75
```

### Web Coverage (Vitest)

```bash
cd tests/web
npm run test:coverage
```

## Mocking Strategy

### HTTP Mocking (responses library)

All provider tests use the `responses` library to mock HTTP calls:

```python
import responses

@responses.activate
def test_api_call():
    responses.add(
        responses.GET,
        "https://api.example.com/forecast",
        json={"data": "..."},
        status=200,
    )
    # Your test code here
```

### Time Mocking (freezegun)

Date-dependent tests use `freezegun`:

```python
from freezegun import freeze_time

@freeze_time("2024-01-15")
def test_date_calculation():
    # date.today() will return 2024-01-15
    pass
```

### Cache Isolation

Tests automatically disable caching via the `disable_cache_for_tests` fixture in `conftest.py`. This ensures test isolation.

## Test Fixtures

Common fixtures are defined in `tests/conftest.py`:

| Fixture | Description |
|---------|-------------|
| `sample_resort` | US resort (Park City style) |
| `european_resort` | French resort (Chamonix) |
| `japanese_resort` | Japanese resort (Niseko) |
| `australian_resort` | Australian resort (Perisher) |
| `sample_resorts` | List of 5 sample resorts |
| `sample_resorts_path` | Temp file with sample resort JSON |
| `open_meteo_response` | Sample Open-Meteo API response |
| `nws_grid_response` | Sample NWS grid point response |
| `nws_forecast_response` | Sample NWS forecast response |

## Adding New Tests

### Python Tests

1. Create test file in appropriate directory:
   - `tests/unit/` for isolated unit tests
   - `tests/integration/` for component interaction tests
   - `tests/e2e/` for live API tests

2. Add appropriate markers:
   ```python
   @pytest.mark.unit
   @pytest.mark.providers
   class TestMyProvider:
       pass
   ```

3. Use existing fixtures where possible

4. Mock external dependencies

### Web Tests

1. **Unit tests** (`tests/web/unit/`): Test pure JavaScript functions
2. **E2E tests** (`tests/web/e2e/`): Test browser interactions

## Directory Structure

```
tests/
├── conftest.py                  # Shared pytest fixtures
├── fixtures/
│   ├── api_responses/           # Mock API response JSON
│   └── resorts_sample.json      # Sample resort data
│
├── unit/                        # Python unit tests
│   ├── test_forecast.py
│   ├── test_resorts.py
│   ├── test_cache.py
│   └── providers/
│       ├── test_open_meteo.py
│       ├── test_ecmwf.py
│       ├── test_nws.py
│       ├── test_icon.py
│       ├── test_jma.py
│       └── test_bom.py
│
├── integration/                 # Python integration tests
│   └── test_cli.py
│
├── e2e/                         # Python E2E tests (live APIs)
│   └── test_live_api.py
│
└── web/                         # Web UI tests
    ├── package.json
    ├── unit/
    │   ├── vitest.config.js
    │   ├── setup.js
    │   └── app.test.js
    ├── e2e/
    │   ├── map.spec.ts
    │   ├── filters.spec.ts
    │   ├── detail_panel.spec.ts
    │   └── mobile.spec.ts
    └── playwright.config.ts
```

## Common Issues

### Cache Interference

If tests are returning cached data unexpectedly, ensure:
- The `disable_cache_for_tests` fixture is active (it's autouse)
- You're not running tests that share state in parallel

### NWS API Tests

NWS tests require two-step mocking (grid point + forecast). See `test_nws.py` for examples.

### Web E2E Tests Need Data

Playwright tests require `powder/web/data/forecasts.json`. Generate it first:
```bash
poetry run powder --export-json
```

### Slow Tests

To skip slow tests (live API):
```bash
poetry run pytest -m "not slow"
```

## Best Practices

1. **Keep tests isolated**: Each test should be independent
2. **Mock external services**: Don't hit real APIs in unit tests
3. **Use fixtures**: Leverage existing fixtures for common data
4. **Mark tests appropriately**: Use markers for categorization
5. **Test edge cases**: Include empty data, null values, errors
6. **Run tests before committing**: `poetry run pytest -m "not slow"`
