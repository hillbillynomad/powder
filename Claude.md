# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Powder is a Python CLI + static web UI that tracks forecasted snowfall at ~215 ski resorts worldwide. It fetches forecasts from multiple weather providers, averages them per day, and also surfaces 14 days of historical snowfall.

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
poetry run powder --export-overlays         # Generate powder/web/data/overlays/ (GFS weather frames, ~20s)

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
├── overlays.py       # Hourly GFS temp / snow depth / new snow grids for the web weather overlay
├── providers/        # ForecastProvider implementations — see providers/MODELS.md
│   ├── base.py       # Abstract ForecastProvider (.name, .get_snowfall_forecast)
│   ├── open_meteo.py # GFS (16d forecast + 14d historical via past_days) — global
│   ├── ecmwf.py      # ECMWF IFS (10d) — global
│   ├── nws.py        # NWS Blend (7d) — US only, two-step API (grid + forecast)
│   ├── icon.py       # DWD ICON (7d) — Europe
│   ├── jma.py        # JMA (7d) — Japan
│   └── bom.py        # BOM (7d) — Australia/NZ
├── data/resorts.json # 216 resorts; schema in data/README.md
└── web/              # Static MapLibre globe UI + sw.js tile cache; web/data/ is gitignored (generated)
```

### Key design points

- **Provider routing is country-driven** (`cli.py:fetch_all_forecasts`). Every resort gets the two global providers (Open-Meteo/GFS, ECMWF). Regional providers are added based on `resort.country`: NWS for `US`, ICON for countries in `EUROPEAN_COUNTRIES`, JMA for `JP`, BOM for `AU`/`NZ`. When adding a regional provider, wire it in here and add a corresponding country check.
- **Forecast aggregation is a simple per-day mean** across whatever providers returned data for that date (`forecast.py:ForecastResult.from_forecasts`). Missing providers for a date don't break aggregation — any provider with data contributes.
- **Historical + forecast share one Open-Meteo call** via `past_days=14` (no separate archive API). Don't reintroduce a split.
- **HTTP cache is global module state** in `cache.py`. `set_cache_enabled(False)` (called by `--no-cache`) resets the lazily-built session. Tests auto-disable caching via the `disable_cache_for_tests` autouse fixture in `tests/conftest.py`.
- **Weather overlays are separate from resort forecasts** (`overlays.py`, `--export-overlays`). They byte-range-read single GRIB2 fields (via each file's `.idx`) from NOAA's free GFS mirror on AWS, decode with `eccodes` (`eccodeslib` supplies the C library off Windows), and write one 8-bit grayscale PNG per field per hour on a 0.5 degree grid (24h back to ~72h ahead) plus `manifest.json` describing the value encodings. Each run gets its own directory so frames are immutable. GFS snow depth has a missing-value sentinel over ocean (masked to 0); density = WEASD/SNOD; new snow = 24h depth gain. The deploy step is `continue-on-error`.
- **`SkiResort` keeps backward-compat aliases** (`elevation_ft`, `state`, plus dual field-name support in `load_resorts`). Don't remove them without checking `data/resorts.json` and downstream JSON consumers.

### Web UI data flow

`--export-json` writes `powder/web/data/forecasts.json`; `web/js/app.js` reads it directly. There is no backend — the UI is fully static.

The map is a MapLibre GL JS globe (`projection: globe`) built in `app.js:buildMapStyle`. All tile sources live in the `MAP_SOURCES` constant and are free / key-less: Esri imagery (Satellite), OpenFreeMap vectors (Map mode + label overlay), OpenTopoMap (Topo), AWS Terrarium DEM (hillshade, 3D relief, and `maplibre-contour` feet contours). Layer ids are grouped by prefix (`base-*`, `osm-*`, `lbl-*`, `terrain-*`, `trails-*`) and `isLayerVisible` is the single source of truth for what each toggle shows. Resorts are a GeoJSON `circle` layer (no DOM markers); e2e tests use the `window.__powder` / `window.__map` hooks. `powder/web/sw.js` is a service worker that caches tiles; it is skipped under automated browsers unless `?sw=1`. Three view modes (`Powder on the Way`, `Recent Powder`, `Total Recent + Forecast`) are computed client-side from forecast + historical days in the same JSON.

The weather overlay lives in `web/js/weather.js` (pure helpers are unit-tested) and is wired in from `app.js`. It is a Weather section in the ☰ menu, off by default; when on, a time bar (play / hourly slider / legend) appears and starts at the current hour, following "now" while the page is open. Frames are decoded from the grayscale PNGs, coloured through a LUT and reprojected to Web Mercator in `web/js/weather-worker.js` (OffscreenCanvas → PNG blob), then shown via a MapLibre `image` source (`wx-*` ids, skipped by `applyLayerPrefs`). Don't switch to a `canvas` source: it renders black on the globe. Clicking the map (not a resort) while an overlay is on shows depth / density / new snow / temperature at that point.

Resort flyover tours live in `web/js/flyby.js` (pure helpers are unit-tested) with one JSON per resort in `web/tours/<slug>.json`, listed in `web/tours/index.json`. Selecting a resort that has a tour flies into a looping low-altitude flight: waypoints are camera positions in real metres above sea level (scaled by the terrain exaggeration at runtime), smoothed with a closed Catmull-Rom spline. Tours fly "like a bird": the camera faces its direction of travel (heading from a look-ahead chord so turns start early), tilted down by each point's `pitch`, banking slightly into turns, applied per frame via `calculateCameraOptionsFromCameraLngLatAltRotation`; points with a `target` use look-at mode (`calculateCameraOptionsFromTo`) instead. Resort bubbles are hidden during a tour. While flying, `centerClampedToGround` is off and the camera aims at authored, splined `ground` heights (not live terrain): MapLibre otherwise re-clamps the centre to the terrain as DEM tiles load, which shook the camera on a tour's first pass. Keep the aim point on the surface (a floating centre stops imagery tiles loading). The tour forces satellite, 3D relief and lift names without saving them over the user's layer prefs, and restores them when the resort is closed; any map gesture pauses it. Tours are generated by `tools/flyby/`: `harvest.cjs` caches each resort's lifts/lodges/peaks from the app's own vector tiles (`node tools/flyby/harvest.cjs <playwright path>`, needs `powder/web` served on :8000), `lifts.py` stitches them into lifts, and `auto_tour.py` writes `web/tours/*.json` + `index.json` for every resort (`poetry run python tools/flyby/auto_tour.py [slug ...]`). Precedence per resort: a hand-crafted spec `tools/flyby/specs/<slug>.json` (waypoints + pitch, built by `author_tour.py`) > curated lift picks in `tools/flyby/picks.json` (`{slug: {up, down, run_limit, side}}` naming the famous lifts) > an automatic racetrack along the best lift near the resort marker > an orbit of the highest point (skipped on flat ground). Review any tour with `node tools/flyby/review.cjs ...` + `tools/flyby/contact_sheet.py`.

## Testing notes

- Provider unit tests use the `responses` library to mock HTTP; date-sensitive tests use `freezegun`. NWS requires two-step mocking (grid point → forecast).
- Live-API tests are marked `slow` and `e2e`; they hit real providers and are skipped by default with `-m "not slow"`.
- See `docs/TESTING.md` for the full testing guide and `tests/conftest.py` for shared fixtures (`sample_resort`, `european_resort`, `japanese_resort`, `open_meteo_response`, etc.).

## Constraints

- Python 3.12+
- Free / open-source dependencies only; no API keys
