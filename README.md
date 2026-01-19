# Powder

Ski resort snowfall forecast tracker. Aggregates forecasts from three weather models (GFS, NWS, ECMWF) and displays the average prediction, plus 14 days of historical snowfall data.

## Features

- **CLI** - Query forecasts by resort, state, or pass type
- **Web UI** - Interactive map with bubble visualization
- **53 Resorts** - Major US and Canadian ski resorts
- **3 Weather Models** - GFS (16 days), NWS (7 days), ECMWF (10 days)
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

# Get forecasts for a specific resort
poetry run powder --resort "Park City"

# Filter by state
poetry run powder --state CO

# Filter by pass type
poetry run powder --pass EPIC

# Combine filters
poetry run powder --state UT --pass IKON

# Bypass cache for fresh data
poetry run powder --no-cache --resort "Vail"
```

### Example Output

```
============================================================
  Snowfall Forecast: Park City Mountain, UT
  Elevation: 6,900 ft
============================================================

Date              Avg      GFS      NWS    ECMWF
----------------------------------------------
Sun 01/19        0.0"     0.0"     0.0"     0.0"
Mon 01/20        2.1"     1.8"     2.5"     2.0"
Tue 01/21        4.3"     3.9"     4.8"     4.2"
...
----------------------------------------------
Total:       12.5"
```

## Web UI

Interactive map showing resorts with forecasted snowfall as blue bubbles. Bubble size is proportional to total predicted snowfall.

### Generate Data & Launch

```bash
# Export forecast data to JSON
poetry run powder --export-json

# Serve the web UI
cd powder/web && python -m http.server 8000

# Open http://localhost:8000
```

### Features

- **Bubble Map** - Blue circles sized by snowfall amount
- **Hover** - Quick view of resort name and snowfall total
- **Click** - Detailed daily breakdown with all three models
- **Filters** - Filter by state, pass type (EPIC/IKON), or view mode
- **View Modes**:
  - *Powder on the Way* - Upcoming forecast only
  - *Recent Powder* - Past 14 days of historical snowfall
  - *Total Recent + Forecast* - Combined view

## Project Structure

```
powder/
├── cli.py              # CLI entry point
├── forecast.py         # Data models, average calculation
├── resorts.py          # Resort dataclass, filtering
├── cache.py            # HTTP response caching (12hr TTL)
├── providers/
│   ├── base.py         # Abstract ForecastProvider
│   ├── open_meteo.py   # GFS model via Open-Meteo
│   ├── nws.py          # National Weather Service
│   ├── ecmwf.py        # ECMWF via Open-Meteo
│   └── MODELS.md       # Weather model documentation
├── data/
│   ├── resorts.json    # Resort coordinates and metadata
│   └── README.md       # Data schema documentation
└── web/
    ├── index.html      # Map page
    ├── css/style.css   # Styling
    ├── js/app.js       # Leaflet map + interactions
    └── data/           # Generated forecast JSON
```

## Data Sources

### Forecast Models

| Model | Source | Range | Resolution | Update Frequency |
|-------|--------|-------|------------|------------------|
| GFS | Open-Meteo | 16 days | 25km | Every 6 hours |
| NWS | weather.gov | 7 days | 2.5km | Every 6 hours |
| ECMWF | Open-Meteo | 10 days | 9km | Every 12 hours |

The average of all three models is used as the final forecast. This reduces individual model bias and improves overall accuracy.

### Historical Data

| Source | Range | Resolution | Delay |
|--------|-------|------------|-------|
| Open-Meteo Archive | 14 days | 9km | ~5 days |

Historical snowfall is retrieved from the Open-Meteo Archive API, which provides ERA5 reanalysis data. Note: There is approximately a 5-day delay in data availability.

See [providers/MODELS.md](powder/providers/MODELS.md) for detailed model documentation.

## Caching

API responses are cached for 12 hours in `~/.cache/powder/http_cache.sqlite`. Use `--no-cache` to bypass.

## Adding Resorts

Edit `powder/data/resorts.json`:

```json
{
  "name": "New Resort",
  "state": "XX",
  "latitude": 40.0000,
  "longitude": -111.0000,
  "elevation_ft": 8000,
  "avg_snowfall_inches": 300,
  "pass_type": "EPIC"
}
```

Required fields: `name`, `state`, `latitude`, `longitude`, `elevation_ft`

## License

MIT
