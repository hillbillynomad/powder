# Resort Data

## Schema
```json
{
  "name": "Resort Name",
  "country": "FR",
  "region": "Savoie",
  "latitude": 45.5000,
  "longitude": 6.5000,
  "elevation_base_ft": 4000,
  "elevation_peak_ft": 10000,
  "lift_count": 25,
  "timezone": "Europe/Paris",
  "avg_snowfall_inches": 350,
  "pass_type": "EPIC" | "IKON" | null
}
```

## Fields
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| name | string | yes | Resort display name |
| country | string | yes | ISO 3166-1 alpha-2 country code (e.g., "US", "FR", "JP") |
| region | string | yes | State/province/region name (e.g., "Utah", "Savoie", "Hokkaido") |
| latitude | float | yes | Decimal degrees (for forecasts + map) |
| longitude | float | yes | Decimal degrees (negative for west) |
| elevation_base_ft | int | yes | Base/village elevation in feet |
| elevation_peak_ft | int | no | Summit/peak elevation in feet (enables vertical drop display) |
| lift_count | int | no | Total lifts (chairs, gondolas, trams, T-bars) |
| timezone | string | no | IANA timezone (e.g., "America/Denver", "Europe/Paris"). Defaults to "UTC" |
| avg_snowfall_inches | int | no | Average annual snowfall |
| pass_type | string | no | "EPIC", "IKON", or null for independent |

## Calculated Fields (in code)
| Field | Description |
|-------|-------------|
| vertical_drop_ft | `elevation_peak_ft - elevation_base_ft` (calculated at runtime, not stored) |

## Selection Criteria
- Ski resorts with 10+ lifts (chairs, gondolas, trams, T-bars)
- 165 resorts across 25 countries

## Coverage by Region

| Region | Countries | Resort Count |
|--------|-----------|--------------|
| North America | US, CA | 53 |
| Europe | FR, AT, CH, IT, DE, NO, ES, FI, SE, AD, BG, PL, CZ, RO, SI, SK | 73 |
| Asia | JP, KR, CN | 20 |
| Oceania | AU, NZ | 7 |
| South America | AR, CL | 5 |

## Country Codes
| Code | Country |
|------|---------|
| AD | Andorra |
| AR | Argentina |
| AT | Austria |
| AU | Australia |
| BG | Bulgaria |
| CA | Canada |
| CH | Switzerland |
| CL | Chile |
| CN | China |
| CZ | Czech Republic |
| DE | Germany |
| ES | Spain |
| FI | Finland |
| FR | France |
| IT | Italy |
| JP | Japan |
| KR | South Korea |
| NO | Norway |
| NZ | New Zealand |
| PL | Poland |
| RO | Romania |
| SE | Sweden |
| SI | Slovenia |
| SK | Slovakia |
| US | United States |

## Data Sources
- **Coordinates**: Resort websites, Google Maps, skiresort.info
- **Elevation (base/peak)**: Official resort websites, skiresort.info, OnTheSnow.com
- **Lift count**: skiresort.info, resort websites
- **Timezone**: Calculated from coordinates using timezonefinder
- **Avg snowfall**: Resort marketing, OnTheSnow.com
- **Pass affiliations**: epicpass.com, ikonpass.com

## Maintenance Scripts
See `scripts/README.md` for data collection and maintenance utilities.

## Adding Resorts

Add entries to `resorts.json`:

```json
{
  "name": "New Resort",
  "country": "CH",
  "region": "Valais",
  "latitude": 46.0207,
  "longitude": 7.7491,
  "elevation_base_ft": 5315,
  "elevation_peak_ft": 12739,
  "lift_count": 30,
  "timezone": "Europe/Zurich",
  "avg_snowfall_inches": null,
  "pass_type": null
}
```

Required fields: `name`, `country`, `region`, `latitude`, `longitude`, `elevation_base_ft`

Recommended: `elevation_peak_ft` (enables vertical drop display in UI)

## Weather Provider Selection

The weather providers used depend on the resort's country:

| Country | Providers |
|---------|-----------|
| US | Open-Meteo (GFS), ECMWF, NWS |
| European countries | Open-Meteo (GFS), ECMWF, ICON |
| JP | Open-Meteo (GFS), ECMWF, JMA |
| AU, NZ | Open-Meteo (GFS), ECMWF, BOM |
| Others | Open-Meteo (GFS), ECMWF |

See `providers/MODELS.md` for detailed model documentation.
