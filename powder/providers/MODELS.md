# Weather Forecast Models Documentation

This document describes the underlying weather models used by each provider in the Powder
application, their strengths, weaknesses, and optimal use cases for ski resort snowfall forecasting.

## Current Providers and Their Models

### Global Models (Used for All Resorts)

#### 1. Open-Meteo (GFS Model)
**File:** `open_meteo.py`
**Model:** NOAA GFS (Global Forecast System)
**API:** https://open-meteo.com/en/docs

| Attribute | Value |
|-----------|-------|
| Resolution | 0.25° (~25km) |
| Forecast Range | Up to 16 days |
| Historical Range | 14 days (via `past_days` parameter) |
| Update Frequency | Every 6 hours |
| Coverage | Global |

**Strengths:**
- Long forecast range (16 days)
- Frequent updates (4x daily)
- Good for overall snow trends and 7-10 day planning
- Free, no API key required
- Single API call provides both historical and forecast data (no gaps)

**Weaknesses:**
- Coarse resolution struggles with mountain topography
- Often under-predicts snow amounts in complex terrain
- Trails ECMWF accuracy by ~1 day

**Best For:** Days 4-10 forecasts, general trend identification

##### Historical Data via past_days

The Forecast API supports a `past_days` parameter (up to 16 days) that returns recent historical
data alongside the forecast. Powder uses `past_days=14` to provide 14 days of historical snowfall
in the same API call as the forecast data. This approach:

- Eliminates gaps between historical and forecast data
- Reduces API calls (one request instead of two)
- Provides continuous 30-day coverage (-14 days to +16 days)

---

#### 2. Open-Meteo (ECMWF Model)
**File:** `ecmwf.py`
**Model:** ECMWF IFS (Integrated Forecasting System)
**API:** https://open-meteo.com/en/docs/ecmwf-api

| Attribute | Value |
|-----------|-------|
| Resolution | 9km (0.1°) |
| Forecast Range | Up to 10 days |
| Update Frequency | Every 12 hours |
| Coverage | Global |

**Strengths:**
- Consistently rated most accurate global model
- Better orographic (mountain) precipitation handling than GFS
- Higher resolution captures terrain effects better
- Free via Open-Meteo

**Weaknesses:**
- Less frequent updates than GFS (2x vs 4x daily)
- Shorter max range than GFS (10 vs 16 days)

**Best For:** Days 3-7 forecasts, mountain terrain accuracy

---

### Regional Models (Used Based on Resort Location)

#### 3. NWS (National Weather Service) - US Only
**File:** `nws.py`
**Model:** GFS + NWS Blend
**API:** https://api.weather.gov

| Attribute | Value |
|-----------|-------|
| Resolution | ~2.5km grid points |
| Forecast Range | ~7 days |
| Update Frequency | Every 6 hours |
| Coverage | United States only |

**Strengths:**
- Official US government source (authoritative)
- Blends multiple models for improved accuracy
- Higher resolution grid points than raw GFS
- Free, no API key required

**Weaknesses:**
- US coverage only
- API can be slow/unreliable at times
- Limited to ~7 day forecasts

**Best For:** US ski resorts, official/authoritative data

---

#### 4. DWD ICON - Europe
**File:** `icon.py`
**Model:** DWD ICON (German Weather Service)
**API:** https://open-meteo.com/en/docs/dwd-api

| Attribute | Value |
|-----------|-------|
| Resolution | 2.2-11km (nested grids) |
| Forecast Range | Up to 7 days |
| Update Frequency | Every 6 hours |
| Coverage | Global (highest resolution in Europe) |

**Strengths:**
- Exceptional resolution for Alpine terrain (2.2km in Europe)
- Superior valley wind and orographic detail
- Best model for European mountain forecasts
- Free via Open-Meteo

**Weaknesses:**
- Highest resolution limited to Europe
- 7-day max range

**Best For:** European ski resorts, especially Alps

**Used For Countries:** AD, AT, BG, CH, CZ, DE, ES, FI, FR, IT, NO, PL, RO, SE, SI, SK

---

#### 5. JMA - Japan
**File:** `jma.py`
**Model:** JMA GSM (Japan Meteorological Agency)
**API:** https://open-meteo.com/en/docs/jma-api

| Attribute | Value |
|-----------|-------|
| Resolution | 20km |
| Forecast Range | Up to 7 days |
| Update Frequency | Every 6 hours |
| Coverage | Global (optimized for Asia-Pacific) |

**Strengths:**
- Tuned for Japan's unique weather patterns
- Better handling of Sea of Japan effect snow
- Official Japanese government model
- Free via Open-Meteo

**Weaknesses:**
- Coarser resolution than ICON
- Limited advantage outside Japan

**Best For:** Japanese ski resorts

**Used For Countries:** JP

---

#### 6. BOM - Australia/New Zealand
**File:** `bom.py`
**Model:** BOM ACCESS (Australian Bureau of Meteorology)
**API:** https://open-meteo.com/en/docs/bom-api

| Attribute | Value |
|-----------|-------|
| Resolution | 6km |
| Forecast Range | Up to 7 days |
| Update Frequency | Every 6 hours |
| Coverage | Australia, New Zealand, surrounding region |

**Strengths:**
- Best model for Southern Hemisphere mountain terrain
- High resolution for Australian Alps
- Official Australian government model
- Free via Open-Meteo

**Weaknesses:**
- Limited coverage outside Oceania
- Fewer ski resorts in coverage area

**Best For:** Australian and New Zealand ski resorts

**Used For Countries:** AU, NZ

---

## Model Selection by Region

| Resort Country | Models Used |
|----------------|-------------|
| United States | Open-Meteo (GFS), ECMWF, NWS |
| Canada | Open-Meteo (GFS), ECMWF |
| European countries | Open-Meteo (GFS), ECMWF, ICON |
| Japan | Open-Meteo (GFS), ECMWF, JMA |
| Australia, New Zealand | Open-Meteo (GFS), ECMWF, BOM |
| Other (China, Korea, South America) | Open-Meteo (GFS), ECMWF |

---

## Model Comparison for Mountain Snowfall

| Model | Mountain Accuracy | Best Range | Update Freq | Resolution |
|-------|-------------------|------------|-------------|------------|
| ECMWF | ★★★★☆ | Days 3-7 | 12 hours | 9km |
| ICON | ★★★★★ | Days 1-5 | 6 hours | 2-11km |
| GFS | ★★★☆☆ | Days 4-10 | 6 hours | 25km |
| NWS Blend | ★★★★☆ | Days 1-5 | 6 hours | 2.5km |
| JMA | ★★★☆☆ | Days 1-5 | 6 hours | 20km |
| BOM | ★★★★☆ | Days 1-5 | 6 hours | 6km |

### Why Model Diversity Matters

Taking the **average** of forecasts from different models provides:
1. **Reduced bias** - Each model has systematic biases; combining them cancels out
2. **Better uncertainty handling** - When models disagree, confidence is lower
3. **Improved skill** - Multi-model ensembles consistently outperform single models

### Regional Model Benefits

Using regional models (ICON, JMA, BOM) in addition to global models provides:
1. **Higher resolution** - Better terrain representation
2. **Local expertise** - Tuned for regional weather patterns
3. **Data redundancy** - If one model fails, others still contribute

---

## Mountain-Specific Considerations

### Challenges with Coarse Models
- **Topography smoothing:** A 25km grid cell averages elevations, so a 10,000ft peak
  might be represented as 7,000ft in the model
- **Orographic lift:** Fine-scale uplift on windward slopes is missed
- **Valley effects:** Cold air pooling and temperature inversions require <5km resolution

### Calibrated against reported snowfall (November 2026)

`tools/calibrate/` hindcasts the app's method on archived model runs (Open-Meteo
historical-forecast API, identical to what the live API served) for 46 resorts in California,
Colorado, Utah, Wyoming, Montana and Canada, and compares Nov-Apr season totals with what the
resorts reported to OnTheSnow (2022-23 to 2025-26, skipping seasons with incomplete reports).

What it found, with the mid-mountain request and Kuchera ratio below:

| Model (mid-mountain) | California | Canada | Colorado | Montana | Utah |
|---|---|---|---|---|---|
| GFS + ECMWF average | +20% | -25% | -43% | -42% | -46% |
| ECMWF alone | +35% | +1% | -13% | -6% | -30% |
| ECMWF + GEM | +8% | -10% | -8% | +11% | -23% |

GFS has a third to a half of ECMWF's water in the interior ranges. No single snow-ratio
formula fixed both California (dense, intense storms: too high) and Utah (too low), because
Montana and Utah share temperatures and storm rates but sit on opposite sides. So the shipped
model is: a temperature x storm-rate snow ratio (`snow_ratio`), plus a bias factor per
provider and region (`powder/data/snow_calibration.json`, provider default elsewhere).
Leave-one-resort-out (a resort with no history): median |error| 19%, median bias per region
within ±13%. What's left is mostly steady per resort, from how each one measures and reports:
neighbours disagree by 40-80% (Northstar vs Heavenly, Big White vs Fernie) every season. So
resorts with reported history also get their own factor (`resorts` in the table,
`tools/calibrate/resort_factors.py`, 0.5-1.8). Held out one season at a time:

| Region | resort-seasons | median bias | median abs error | within 20% |
|---|---|---|---|---|
| California | 30 | -4% | 12% | 70% |
| Canada | 46 | +3% | 13% | 65% |
| Colorado | 41 | +0% | 9% | 85% |
| Montana | 11 | +9% | 17% | 64% |
| Utah | 21 | -8% | 12% | 71% |
| Wyoming | 4 | -0% | 19% | 50% |
| All | 153 | +0% | 12% | 72% |

Outside the reported regions, GFS and GEM are tied per country (or US state / Canadian
province) to ECMWF's season snowfall (`tools/calibrate/anchor.py`), since ECMWF's own global
factor against the reports is ~1.0.

### How Powder corrects for this

Checked against OpenSnow and snow-forecast.com for the California resorts in November 2026,
the raw model numbers ran 1.5-2.5x low, for two reasons we now correct
(`providers/open_meteo_common.py`, `providers/nws.py`):

- **Forecast elevation.** Resort coordinates sit at the base lodge. Every Open-Meteo request
  (GFS, ECMWF, ICON, JMA, BOM) passes `elevation` = mid-mountain, so the downscaled temperature
  and the rain/snow split are for the skiing rather than the parking lot. NWS has no elevation
  parameter, so we ask for the grid cell of a nearby point at about mid-mountain: a ring of
  candidates out to 3 km, ranked by one call to Open-Meteo's elevation API (`|elevation - mid|`
  plus 150 ft per km of distance), falling back to the resort point.
- **Snow-to-liquid ratio.** Open-Meteo's `snowfall` is frozen water x 7 (cm = mm x 0.7) whatever
  the temperature. We turn it back into water and apply
  `0.84 x kuchera(T) x rate^-0.31`, clamped 5-25:1: `kuchera` is 12:1 at 28 °F, +0.92 per °C
  colder, -2 per °C warmer (hourly mid-mountain 2 m temperature), and `rate` is the snow water
  over the surrounding 6 hours in mm/h (heavy storms pack denser snow). Constants fitted by
  `tools/calibrate/optimize.py`. NWS amounts already include NWS's own ratio and are used as is.

Borderline storms (snow at 31-34 °F, such as Southern California) still come out low: the
models' own rain/snow split calls most of it rain.

### Recommendations for Ski Resort Forecasts
1. Use **regional models** where available (ICON for Europe, NWS for US)
2. Use **ECMWF** as primary global model (best mountain accuracy)
3. Use **GFS** for extended range (days 7-16)
4. Average all available models for final forecast

---

## References

- [Open-Meteo Documentation](https://open-meteo.com/en/docs)
- [NWS API Documentation](https://www.weather.gov/documentation/services-web-api)
- [ECMWF Model Overview](https://www.ecmwf.int/en/forecasts/documentation-and-support)
- [NOAA GFS Documentation](https://www.ncei.noaa.gov/products/weather-climate-models/global-forecast)
- [DWD ICON Documentation](https://www.dwd.de/EN/ourservices/nwp_forecast_data/nwp_forecast_data.html)
- [JMA Numerical Weather Prediction](https://www.jma.go.jp/jma/en/Activities/nwp.html)
- [BOM ACCESS Model](http://www.bom.gov.au/nwp/doc/access/NWPData.shtml)
