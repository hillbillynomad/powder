# Resort Data

## Schema
```json
{
  "name": "Resort Name",
  "state": "XX",
  "latitude": 40.0000,
  "longitude": -111.0000,
  "elevation_ft": 8000,
  "avg_snowfall_inches": 350,
  "pass_type": "EPIC" | "IKON" | null
}
```

## Fields
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| name | string | yes | Resort display name |
| state | string | yes | 2-letter state code |
| latitude | float | yes | Decimal degrees (for forecasts + future map) |
| longitude | float | yes | Decimal degrees (negative for west) |
| elevation_ft | int | yes | Base elevation in feet |
| avg_snowfall_inches | int | no | Average annual snowfall |
| pass_type | string | no | "EPIC", "IKON", or null for independent |

## Selection Criteria
- Major US ski resorts only (>10 chairlifts)
- 43 resorts across 13 states

## Data Sources
- Coordinates: Resort websites, Google Maps
- Elevation: Resort websites, USGS
- Avg snowfall: Resort marketing, OnTheSnow.com
- Pass affiliations: epicpass.com, ikonpass.com

## Adding Resorts
Add entries to `resorts.json`. Required fields: name, state, latitude, longitude, elevation_ft.
