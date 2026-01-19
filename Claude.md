# Powder - Ski Resort Snowfall Forecast Tracker

Python CLI + Web UI that tracks forecasted snowfall at US ski resorts. Collects forecasts from 3 sources and uses the average as the final forecast. Also displays 14-day historical snowfall.

## Project Status
- [x] CLI with multi-resort support
- [x] Web UI with interactive map
- [x] Historical snowfall data (14 days)

## Quick Start
```bash
poetry install
poetry run powder --list              # List all resorts
poetry run powder --state UT          # Forecasts for Utah
poetry run powder --pass EPIC         # Forecasts for EPIC pass resorts
poetry run powder --resort "Vail"     # Single resort forecast
poetry run powder --export-json       # Generate data for web UI
```

## Web UI
```bash
poetry run powder --export-json       # Generate forecast data
cd powder/web && python -m http.server 8000
# Open http://localhost:8000
```

Features: Blue bubble map (size = snowfall), hover tooltips, click for daily detail, state/pass/view filters.

### View Filter Options
- **Powder on the Way** - Upcoming forecast snowfall only
- **Recent Powder** - Past 14 days of historical snowfall
- **Total Recent + Forecast** - Combined historical and forecast

## Architecture
```
powder/
├── cli.py          # CLI entry point, argument parsing, --export-json
├── forecast.py     # DailyForecast, ForecastResult, average calculation
├── resorts.py      # SkiResort dataclass, load/filter functions
├── cache.py        # HTTP caching (12hr TTL)
├── providers/      # Forecast data sources (see providers/MODELS.md)
│   ├── base.py     # Abstract ForecastProvider
│   ├── open_meteo.py   # GFS model (16 days) + Historical Archive (14 days)
│   ├── nws.py          # NWS Blend (7 days)
│   └── ecmwf.py        # ECMWF IFS (10 days)
├── data/           # Resort configuration (see data/README.md)
│   └── resorts.json    # Major US/CA ski resorts
└── web/            # Static web UI
    ├── index.html      # Map page with Leaflet
    ├── css/style.css   # Dark theme styling
    ├── js/app.js       # Map rendering, interactions
    └── data/           # Generated forecasts.json (gitignored)
```

## Key Files
- `powder/providers/MODELS.md` - Weather model documentation
- `powder/data/README.md` - Resort data schema and sources

## Constraints
- Python 3.12+
- Free/open source libraries only
- No API keys required
