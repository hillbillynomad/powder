# Data Collection Scripts

Utilities for collecting and maintaining ski resort data.

## Scripts

### collect_global_resorts.py

Collects global ski resort data and outputs a JSON file compatible with the Powder app.

**What it does:**
- Contains curated resort data with verified base/peak elevations for all 165 resorts
- Includes lift counts, regions, and coordinates from official sources
- Calculates timezones from coordinates using `timezonefinder`
- Outputs to `powder/data/resorts_global.json`

**Data sources in `load_known_resorts()`:**
- Elevation data: Official resort websites, skiresort.info
- Lift counts: skiresort.info, OpenStreetMap
- Coordinates: Resort websites, Google Maps

**Usage:**
```bash
poetry install --with dev
python scripts/collect_global_resorts.py
```

**Output:** `powder/data/resorts_global.json`

### merge_resorts.py

Merges US/CA resorts (with snowfall and pass data) with global resorts into a single file.

**What it does:**
- Loads existing `resorts.json` (US/CA resorts with EPIC/IKON pass affiliations)
- Loads `resorts_global.json` (international resorts)
- Merges and deduplicates entries
- Supports both old (`elevation_ft`) and new (`elevation_base_ft`, `elevation_peak_ft`) field names
- Sorts by country, then by lift count descending

**Usage:**
```bash
python scripts/merge_resorts.py
```

**Output:** Overwrites `powder/data/resorts.json`

## Data Schema

Both scripts output JSON with the following resort structure:

```json
{
  "name": "Resort Name",
  "country": "CH",
  "region": "Valais",
  "latitude": 46.0207,
  "longitude": 7.7491,
  "elevation_base_ft": 5315,
  "elevation_peak_ft": 12739,
  "lift_count": 52,
  "avg_snowfall_inches": null,
  "pass_type": null,
  "timezone": "Europe/Zurich"
}
```

## Adding New Resorts

To add a new resort:

1. Add the resort data to `load_known_resorts()` in `collect_global_resorts.py`:
   ```python
   {"name": "New Resort", "lat": 46.0, "lon": 7.5, "lifts": 25,
    "region": "Valais", "base_elev": 5000, "peak_elev": 10000},
   ```

2. Run the collection script:
   ```bash
   python scripts/collect_global_resorts.py
   ```

3. If the resort has EPIC/IKON pass affiliation or US/CA avg snowfall data, also update `merge_resorts.py` and run:
   ```bash
   python scripts/merge_resorts.py
   ```

## Elevation Data Notes

- `elevation_base_ft`: Village/base area elevation where lifts start
- `elevation_peak_ft`: Summit elevation (highest skiable point)
- Vertical drop is calculated at runtime: `peak - base`

All elevations are in feet. When researching new resorts:
- Source from official resort websites first
- Cross-reference with skiresort.info or OnTheSnow
- Some resorts report lift base vs village base differently - use the lowest accessible ski lift base
