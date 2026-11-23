# Weather Forecast Models Documentation

This document describes the underlying weather models used by each provider in the Powder
application, their strengths, weaknesses, and optimal use cases for ski resort snowfall forecasting.

## Current Providers and Their Models

### Global Models (Used for All Resorts)

#### 1. Open-Meteo (GFS Model)
**File:** `open_meteo.py`
**Model:** NOAA GFS global (`gfs_global`), the same model for every day and every resort
**API:** https://open-meteo.com/en/docs

Not `gfs_seamless`: over the US that serves HRRR (3 km) for the first ~46 hours, and the archive
behind `past_days` and the calibration stores HRRR's first forecast hours, before its
precipitation has spun up: 1.4-4x less than HRRR forecasts a day ahead (Palisades 1.4x, Alta
2.2x, Vail 2.5x, Big Sky 4.2x, Dec-Mar 2025-26). Factors fitted on that archive (x1.3-3.7)
inflated every US and Canadian forecast by about a third. GFS global's archive is within ~15%
of its own 1-3 day forecasts. The GEM provider is pinned to `gem_global` for the same reason
(`gem_seamless` swaps in HRDPS and GEM regional, and HRDPS has no archive).

| Attribute | Value |
|-----------|-------|
| Resolution | 0.11-0.25° (~13-25km) |
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
Montana and Utah share temperatures and storm rates but sit on opposite sides. That first version (factors on each provider's own `snowfall`, the
GFS factors fitted on the HRRR archive) is replaced by the model below.

#### Shipped model (revised November 2026)

- **One underlying model per provider**: GFS global, ECMWF IFS, GEM global, the same for past
  days and forecast days, so the archive the factors are fitted on is what the app serves.
- **Snow water from precipitation**: precipitation x the share falling as snow, from the
  wet-bulb temperature at mid-mountain (temperature, humidity and the pressure of that height;
  Wang et al. 2019 sigmoid, 50% snow at +0.8 °C). Open-Meteo's `snowfall` is not used: each model
  splits rain and snow its own way, and the GFS archive has no `snowfall` at all.
- **Snow ratio** unchanged: `0.84 x kuchera(T) x rate^-0.31`, clamped 5-25:1.
- **A factor per provider and region** (US state / Canadian province with two or more reported
  resorts, else the provider default), fitted by `tools/calibrate/factors.py` on the exact
  provider code (`tools/calibrate/appmodel.py`). GFS's factors are now 0.73-1.20 (were 1.29-3.69).
  Elsewhere GFS and GEM are tied per country to ECMWF (`tools/calibrate/anchor.py`).
- **A small per-resort factor** (`tools/calibrate/resort_factors.py`): only for resorts with two
  or more complete reported seasons, shrunk toward 1 by n / (n + 1) and capped to 0.6-1.6
  (shipped 0.69-1.37, were 0.50-1.77). Part of a site factor absorbs the snow ratio's
  temperature error (against NWS observers, a whole-winter site factor misses by 30-60% in cold
  spells), so large factors amplify the error when the weather changes.

| Held-out score, per resort-season | median abs error | within 20% |
|---|---|---|
| No resort history (region factors, leave-one-resort-out per resort) | 15% (was 19%) | 63% |
| Leave-one-season-out, region factors only | 14% | 61% |
| Leave-one-season-out, + resort factor | 11% (was 12%) | 75% |
| Out of time (fit 2022-24, score 2024-26), region factors only | 19% | 54% |
| Out of time, + resort factor | 14% (was 15%) | 64% |

Out of time is the number to expect next season and the gate for a refit: refit once a year in
spring on the latest seasons, and ship only if it holds. Don't tune on a few weeks of weather.

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
- **Rain/snow split and snow-to-liquid ratio.** Snow water is the hourly precipitation times a
  wet-bulb snow fraction at mid-mountain (above). (Open-Meteo's `snowfall` would be frozen water
  x 7, whatever the temperature; it is only a fallback now.) We apply
  `0.84 x kuchera(T) x rate^-0.31`, clamped 5-25:1: `kuchera` is 12:1 at 28 °F, +0.92 per °C
  colder, -2 per °C warmer (hourly mid-mountain 2 m temperature), and `rate` is the snow water
  over the surrounding 6 hours in mm/h (heavy storms pack denser snow). Constants fitted by
  `tools/calibrate/optimize.py`. NWS amounts already include NWS's own ratio and are used as is.

Borderline storms (snow at 31-34 °F, such as Southern California) are now split by our own
wet-bulb rule at mid-mountain rather than the models' split at their grid-cell height, which
called most of them rain.

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
