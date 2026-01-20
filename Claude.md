# Powder - Ski Resort Snowfall Forecast Tracker

Python CLI + Web UI that tracks forecasted snowfall at ski resorts worldwide. Collects forecasts from multiple weather models (with regional providers for better accuracy) and uses the average as the final forecast. Also displays 14-day historical snowfall.

## Project Status
- [x] CLI with multi-resort support
- [x] Web UI with interactive map
- [x] Historical snowfall data (14 days)
- [x] Global resort coverage (165 resorts, 25 countries)
- [x] Regional weather providers (ICON for Europe, JMA for Japan, BOM for Australia/NZ)
- [x] Base/peak elevation and vertical drop for all resorts

## Quick Start
```bash
poetry install
poetry run powder --list              # List all 165 resorts
poetry run powder --country FR        # Forecasts for French resorts
poetry run powder --country US --state UT  # Forecasts for Utah
poetry run powder --pass EPIC         # Forecasts for EPIC pass resorts
poetry run powder --resort "Chamonix" # Single resort forecast
poetry run powder --export-json       # Generate data for web UI
```

## Web UI
```bash
poetry run powder --export-json       # Generate forecast data
cd powder/web && python -m http.server 8000
# Open http://localhost:8000
```

Features: Blue bubble map (size = snowfall), hover tooltips, click for daily detail, country/region/pass/snowfall filters, Top 10 sidebar.

### Snowfall Filter Options
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
│   ├── ecmwf.py        # ECMWF IFS (10 days) - Global
│   ├── nws.py          # NWS Blend (7 days) - US only
│   ├── icon.py         # DWD ICON (7 days) - Europe
│   ├── jma.py          # JMA (7 days) - Japan
│   └── bom.py          # BOM (7 days) - Australia/NZ
├── data/           # Resort configuration (see data/README.md)
│   └── resorts.json    # 165 global ski resorts (25 countries)
└── web/            # Static web UI
    ├── index.html      # Map page with Leaflet
    ├── css/style.css   # Dark theme styling
    ├── js/app.js       # Map rendering, interactions, Top 10 sidebar
    └── data/           # Generated forecasts.json (gitignored)
```

## Key Files
- `powder/providers/MODELS.md` - Weather model documentation
- `powder/data/README.md` - Resort data schema and sources
- `scripts/README.md` - Data collection and maintenance scripts

## Constraints
- Python 3.12+
- Free/open source libraries only
- No API keys required
