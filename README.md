# Powder

Ski resort snowfall forecast tracker. Aggregates forecasts from multiple weather models and displays the average prediction, plus 14 days of historical snowfall data.

## Features

- **CLI** - Query forecasts by resort, country, region, or pass type
- **Web UI** - Interactive world map with bubble visualization and Top 10 sidebar
- **165 Resorts** - Ski resorts across 25 countries (10+ lifts each)
- **Regional Weather Models** - Best-in-class models for each region
- **Historical Data** - 14 days of past snowfall from Open-Meteo Archive
- **No API Keys** - All data sources are free and open

## Installation

```bash
# Requires Python 3.12+
poetry install
```

## CLI Usage

```bash
# List all resorts
poetry run powder --list

# List resorts by country
poetry run powder --list --country JP

# Get forecasts for a specific resort
poetry run powder --resort "Chamonix"

# Filter by country
poetry run powder --country FR

# Filter by country and region
poetry run powder --country US --state CO

# Filter by pass type
poetry run powder --pass EPIC

# Combine filters
poetry run powder --country US --state UT --pass IKON

# Bypass cache for fresh data
poetry run powder --no-cache --resort "Niseko"
```

### Example Output

```
============================================================
  Snowfall Forecast: Chamonix Mont-Blanc, Haute-Savoie, FR
  Elevation: 3,396 - 12,605 ft (9,209' vert)
============================================================

Date              Avg   Open-Meteo    ECMWF     ICON
----------------------------------------------------
Mon 01/20        2.1"       1.8"      2.5"     2.0"
Tue 01/21        4.3"       3.9"      4.8"     4.2"
...
----------------------------------------------------
Total:       12.5"
```

## Web UI

Interactive world map showing resorts with forecasted snowfall as blue bubbles. Bubble size is proportional to total predicted snowfall.

### Generate Data & Launch

```bash
# Export forecast data to JSON
poetry run powder --export-json

# Serve the web UI
cd powder/web && python -m http.server 8000

# Open http://localhost:8000
```

### Features

- **World Map** - Global view with all 165 resorts
- **Bubble Map** - Blue circles sized by snowfall amount
- **Top 10 Sidebar** - Highest snowfall resorts (updates with filters)
- **Hover** - Quick view of resort name and snowfall total
- **Click** - Detailed daily breakdown with all weather models
- **Filters**:
  - *Country* - Filter by country (auto-zooms to selection)
  - *Region* - Filter by state/province/region
  - *Pass* - EPIC, IKON, or Independent
  - *Snowfall* - Forecast, Recent, or Total view

### Snowfall View Modes

- **Powder on the Way** - Upcoming forecast only
- **Recent Powder** - Past 14 days of historical snowfall
- **Total Recent + Forecast** - Combined view

## Supported Countries

| Region | Countries |
|--------|-----------|
| North America | US (43), Canada (10) |
| Europe | France (14), Austria (14), Switzerland (12), Italy (11), Germany (5), Norway (5), Spain (3), Finland (3), Sweden (3), Andorra (2), Bulgaria (2), Poland (2), Czech Republic, Romania, Slovenia, Slovakia |
| Asia | Japan (12), South Korea (3), China (5) |
| Oceania | Australia (5), New Zealand (2) |
| South America | Argentina (3), Chile (2) |

## Project Structure

```
powder/
├── cli.py              # CLI entry point
├── forecast.py         # Data models, average calculation
├── resorts.py          # Resort dataclass, filtering
├── cache.py            # HTTP response caching (12hr TTL)
├── providers/
│   ├── base.py         # Abstract ForecastProvider
│   ├── open_meteo.py   # GFS model via Open-Meteo (global)
│   ├── ecmwf.py        # ECMWF via Open-Meteo (global)
│   ├── nws.py          # National Weather Service (US only)
│   ├── icon.py         # DWD ICON via Open-Meteo (Europe)
│   ├── jma.py          # JMA via Open-Meteo (Japan)
│   ├── bom.py          # BOM via Open-Meteo (Australia/NZ)
│   └── MODELS.md       # Weather model documentation
├── data/
│   ├── resorts.json    # Resort coordinates and metadata
│   └── README.md       # Data schema documentation
└── web/
    ├── index.html      # Map page
    ├── css/style.css   # Styling
    ├── js/app.js       # Leaflet map + interactions
    └── data/           # Generated forecast JSON

tests/
├── conftest.py         # Shared pytest fixtures
├── fixtures/           # Mock API responses, sample data
├── unit/               # Python unit tests (pytest)
├── integration/        # Python integration tests (pytest)
├── e2e/                # Python live API tests (pytest)
└── web/                # Web UI tests (Vitest + Playwright)

docs/
└── TESTING.md          # Complete testing documentation
```

## Weather Models

### Global Models (All Resorts)

| Model | Source | Range | Resolution | Update Frequency |
|-------|--------|-------|------------|------------------|
| GFS | Open-Meteo | 16 days | 25km | Every 6 hours |
| ECMWF | Open-Meteo | 10 days | 9km | Every 12 hours |

### Regional Models (Better Accuracy)

| Model | Provider | Region | Range | Resolution |
|-------|----------|--------|-------|------------|
| NWS Blend | weather.gov | US only | 7 days | 2.5km |
| ICON | Open-Meteo | Europe | 7 days | 2-11km |
| JMA | Open-Meteo | Japan | 7 days | 20km |
| BOM | Open-Meteo | Australia/NZ | 7 days | 6km |

The average of all available models is used as the final forecast. This reduces individual model bias and improves overall accuracy.

### Historical Data

| Source | Range | Resolution | Delay |
|--------|-------|------------|-------|
| Open-Meteo Archive | 14 days | 9km | ~5 days |

See [providers/MODELS.md](powder/providers/MODELS.md) for detailed model documentation.

## Testing

Powder has comprehensive test coverage with 75% minimum threshold enforced.

### Quick Start

```bash
# Run all Python tests
poetry run pytest

# Run tests in parallel
poetry run pytest -n auto

# Run with coverage report
poetry run pytest --cov=powder --cov-report=html
```

### Test Categories

| Category | Command | Description |
|----------|---------|-------------|
| Unit | `pytest -m unit` | Fast, isolated tests |
| Integration | `pytest -m integration` | Component interaction |
| E2E (Live API) | `pytest -m e2e` | Tests against real APIs |
| Providers | `pytest -m providers` | Weather API providers |
| Skip Slow | `pytest -m "not slow"` | Skip live API tests |

### Web UI Tests

```bash
cd tests/web
npm install
npm test                 # Unit tests (Vitest)
npm run test:e2e        # E2E tests (Playwright)
```

See [docs/TESTING.md](docs/TESTING.md) for complete testing documentation.

## Caching

API responses are cached for 12 hours in `~/.cache/powder/http_cache.sqlite`. Use `--no-cache` to bypass.

## Adding Resorts

Edit `powder/data/resorts.json`:

```json
{
  "name": "New Resort",
  "country": "FR",
  "region": "Savoie",
  "latitude": 45.5000,
  "longitude": 6.5000,
  "elevation_base_ft": 4000,
  "elevation_peak_ft": 10000,
  "lift_count": 25,
  "timezone": "Europe/Paris",
  "avg_snowfall_inches": 300,
  "pass_type": null
}
```

Required fields: `name`, `country`, `region`, `latitude`, `longitude`, `elevation_base_ft`

Optional: `elevation_peak_ft` (enables vertical drop calculation in UI)

## License

MIT
