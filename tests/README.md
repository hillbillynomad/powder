# Powder Test Suite

Comprehensive automated testing for the Powder ski resort snowfall forecast tracker.

## Overview

| Test Type | Tool | Location | Coverage Target |
|-----------|------|----------|-----------------|
| Python Unit Tests | pytest | `unit/` | 75% (enforced) |
| Python Integration Tests | pytest | `integration/` | 75% (enforced) |
| Python E2E Tests | pytest | `e2e/` | Live API validation |
| Web Unit Tests | Vitest | `web/unit/` | 75% (enforced) |
| Web E2E Tests | Playwright | `web/e2e/` | Browser automation |

## Quick Start

### Python Tests

```bash
# Install test dependencies
poetry install --with test

# Run all tests
poetry run pytest

# Run in parallel (faster)
poetry run pytest -n auto

# Run with coverage
poetry run pytest --cov=powder --cov-report=html

# Run specific category
poetry run pytest -m unit
poetry run pytest -m providers
poetry run pytest -m "not slow"
```

### Web Tests

```bash
cd tests/web

# Install dependencies
npm install

# Run unit tests
npm test

# Run E2E tests
npx playwright install  # First time only
npm run test:e2e
```

## Directory Structure

```
tests/
├── README.md               # This file
├── conftest.py             # Shared pytest fixtures and configuration
│
├── fixtures/               # Test data files
│   ├── api_responses/      # Mock JSON responses for weather APIs
│   │   ├── open_meteo_forecast.json
│   │   ├── nws_grid_point.json
│   │   └── nws_forecast.json
│   └── resorts_sample.json # Sample resort data for testing
│
├── unit/                   # Python unit tests (fast, isolated)
│   ├── README.md           # Unit test documentation
│   ├── test_forecast.py    # Forecast aggregation tests
│   ├── test_resorts.py     # Resort data and filtering tests
│   ├── test_cache.py       # HTTP caching tests
│   └── providers/          # Weather provider tests
│       ├── test_open_meteo.py
│       ├── test_ecmwf.py
│       ├── test_nws.py
│       ├── test_icon.py
│       ├── test_jma.py
│       └── test_bom.py
│
├── integration/            # Python integration tests
│   ├── README.md           # Integration test documentation
│   └── test_cli.py         # CLI workflow tests
│
├── e2e/                    # Python end-to-end tests (live APIs)
│   ├── README.md           # E2E test documentation
│   └── test_live_api.py    # Live API validation
│
└── web/                    # Web UI tests (JavaScript)
    ├── README.md           # Web test documentation
    ├── package.json        # npm dependencies
    ├── unit/               # Vitest unit tests
    │   ├── vitest.config.js
    │   ├── setup.js
    │   └── app.test.js
    ├── e2e/                # Playwright E2E tests
    │   ├── map.spec.ts
    │   ├── filters.spec.ts
    │   ├── detail_panel.spec.ts
    │   └── mobile.spec.ts
    └── playwright.config.ts
```

## Test Markers (pytest)

Tests are organized with markers for selective execution:

| Marker | Description | Example |
|--------|-------------|---------|
| `unit` | Fast, isolated tests | `pytest -m unit` |
| `integration` | Component interaction | `pytest -m integration` |
| `e2e` | Live API tests | `pytest -m e2e` |
| `slow` | Long-running tests | `pytest -m "not slow"` |
| `providers` | Weather API providers | `pytest -m providers` |
| `forecast` | Forecast calculations | `pytest -m forecast` |
| `resorts` | Resort data/filtering | `pytest -m resorts` |
| `elevation` | Elevation calculations | `pytest -m elevation` |
| `cli` | CLI commands | `pytest -m cli` |
| `cache` | HTTP caching | `pytest -m cache` |

Combine markers: `pytest -m "unit and providers"`

## Coverage Requirements

Both Python and JavaScript code enforce a **75% minimum coverage threshold**:

- **Python**: Configured in `pyproject.toml` (`fail_under = 75`)
- **JavaScript**: Configured in `web/unit/vitest.config.js` (`thresholds`)

Current coverage: ~96% (Python)

## Key Testing Concepts

### Mocking Strategy

- **HTTP requests**: Mocked with `responses` library (no real API calls in unit tests)
- **Time/dates**: Mocked with `freezegun` for deterministic date testing
- **Cache isolation**: Automatically disabled for all tests via `conftest.py`

### Fixtures

Common fixtures in `conftest.py`:
- `sample_resort`, `european_resort`, `japanese_resort`, `australian_resort`
- `sample_resorts` (list of 5 resorts for filtering tests)
- `open_meteo_response`, `nws_grid_response`, `nws_forecast_response`

## Adding New Tests

1. **Unit tests**: Add to `unit/` with `@pytest.mark.unit` marker
2. **Integration tests**: Add to `integration/` with `@pytest.mark.integration` marker
3. **Provider tests**: Add to `unit/providers/` with `@pytest.mark.providers` marker
4. **Web tests**: Add to `web/unit/` (Vitest) or `web/e2e/` (Playwright)

See [docs/TESTING.md](../docs/TESTING.md) for complete documentation.
