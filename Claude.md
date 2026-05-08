# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Powder is a Python CLI + static web UI that tracks forecasted snowfall at ~165 ski resorts worldwide. It fetches forecasts from multiple weather providers, averages them per day, and also surfaces 14 days of historical snowfall.

## Common Commands

```bash
poetry install                              # Install deps (Python 3.12+, no API keys)

# CLI
poetry run powder --list                    # List all resorts
poetry run powder --country FR              # Forecasts for French resorts
poetry run powder --country US --state UT   # Filter by country + region
poetry run powder --pass EPIC               # Filter by pass type
poetry run powder --resort "Chamonix"       # Single resort
poetry run powder --no-cache --resort "Niseko"  # Bypass HTTP cache
poetry run powder --export-json             # Generate powder/web/data/forecasts.json

# Web UI (after --export-json)
cd powder/web && python -m http.server 8000

# Tests (Python — coverage gate is 75%, enforced in pyproject.toml)
poetry run pytest                           # All Python tests
poetry run pytest -n auto                   # Parallel (pytest-xdist)
poetry run pytest -m "not slow"             # Skip live-API tests
poetry run pytest -m unit                   # Markers: unit | integration | e2e | providers | forecast | resorts | elevation | cli | cache | slow
poetry run pytest tests/unit/test_forecast.py::TestForecastResult::test_from_forecasts_calculates_average  # Single test
poetry run pytest --cov=powder --cov-report=html  # HTML coverage report

# Tests (Web — Vitest unit + Playwright E2E)
cd tests/web && npm install
npm test                                    # Vitest unit tests
npm run test:e2e                            # Playwright (requires forecasts.json — run --export-json first)
```

## Architecture

```
powder/
├── cli.py            # Arg parsing, --export-json, fetch_all_forecasts (provider routing)
├── forecast.py       # DailyForecast, ForecastResult, calculate_avg_forecasts
├── resorts.py        # SkiResort dataclass, load_resorts, filter_resorts
├── cache.py          # Module-level requests_cache.CachedSession (12h TTL, sqlite)
├── providers/        # ForecastProvider implementations — see providers/MODELS.md
│   ├── base.py       # Abstract ForecastProvider (.name, .get_snowfall_forecast)
│   ├── open_meteo.py # GFS (16d forecast + 14d historical via past_days) — global
│   ├── ecmwf.py      # ECMWF IFS (10d) — global
│   ├── nws.py        # NWS Blend (7d) — US only, two-step API (grid + forecast)
│   ├── icon.py       # DWD ICON (7d) — Europe
│   ├── jma.py        # JMA (7d) — Japan
│   └── bom.py        # BOM (7d) — Australia/NZ
├── data/resorts.json # 165 resorts; schema in data/README.md
└── web/              # Static Leaflet UI; web/data/ is gitignored (generated)
```

### Key design points

- **Provider routing is country-driven** (`cli.py:fetch_all_forecasts`). Every resort gets the two global providers (Open-Meteo/GFS, ECMWF). Regional providers are added based on `resort.country`: NWS for `US`, ICON for countries in `EUROPEAN_COUNTRIES`, JMA for `JP`, BOM for `AU`/`NZ`. When adding a regional provider, wire it in here and add a corresponding country check.
- **Forecast aggregation is a simple per-day mean** across whatever providers returned data for that date (`forecast.py:ForecastResult.from_forecasts`). Missing providers for a date don't break aggregation — any provider with data contributes.
- **Historical + forecast share one Open-Meteo call** via `past_days=14` (no separate archive API). Don't reintroduce a split.
- **HTTP cache is global module state** in `cache.py`. `set_cache_enabled(False)` (called by `--no-cache`) resets the lazily-built session. Tests auto-disable caching via the `disable_cache_for_tests` autouse fixture in `tests/conftest.py`.
- **`SkiResort` keeps backward-compat aliases** (`elevation_ft`, `state`, plus dual field-name support in `load_resorts`). Don't remove them without checking `data/resorts.json` and downstream JSON consumers.

### Web UI data flow

`--export-json` writes `powder/web/data/forecasts.json`; `web/js/app.js` reads it directly. There is no backend — the UI is fully static. Three view modes (`Powder on the Way`, `Recent Powder`, `Total Recent + Forecast`) are computed client-side from forecast + historical days in the same JSON.

## Testing notes

- Provider unit tests use the `responses` library to mock HTTP; date-sensitive tests use `freezegun`. NWS requires two-step mocking (grid point → forecast).
- Live-API tests are marked `slow` and `e2e`; they hit real providers and are skipped by default with `-m "not slow"`.
- See `docs/TESTING.md` for the full testing guide and `tests/conftest.py` for shared fixtures (`sample_resort`, `european_resort`, `japanese_resort`, `open_meteo_response`, etc.).

## Constraints

- Python 3.12+
- Free / open-source dependencies only; no API keys
