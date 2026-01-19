# Weather Forecast Models Documentation

This document describes the underlying weather models used by each provider in the Powder
application, their strengths, weaknesses, and optimal use cases for ski resort snowfall forecasting.

## Current Providers and Their Models

### Global Models (Used for All Resorts)

#### 1. Open-Meteo (GFS Model + Historical Archive)
**File:** `open_meteo.py`
**Model:** NOAA GFS (Global Forecast System) for forecasts, ERA5 reanalysis for historical
**API:** https://open-meteo.com/en/docs

##### Forecast Data

| Attribute | Value |
|-----------|-------|
| Resolution | 0.25° (~25km) |
| Forecast Range | Up to 16 days |
| Update Frequency | Every 6 hours |
| Coverage | Global |

**Strengths:**
- Long forecast range (16 days)
- Frequent updates (4x daily)
- Good for overall snow trends and 7-10 day planning
- Free, no API key required

**Weaknesses:**
- Coarse resolution struggles with mountain topography
- Often under-predicts snow amounts in complex terrain
- Trails ECMWF accuracy by ~1 day

**Best For:** Days 4-10 forecasts, general trend identification

##### Historical Data (Archive API)

| Attribute | Value |
|-----------|-------|
| Resolution | 9km (0.1°) |
| Data Range | 14 days (configurable) |
| Data Delay | ~5 days |
| Coverage | Global |
| API Endpoint | `https://archive-api.open-meteo.com/v1/archive` |

**Strengths:**
- Based on ERA5 reanalysis (actual measured/assimilated data, not forecasts)
- Higher resolution than GFS forecasts
- Same API interface as forecast endpoint
- Free, no API key required

**Weaknesses:**
- ~5 day delay in data availability
- Reanalysis may differ from ground truth in complex terrain

**Best For:** "Recent Powder" view showing past snowfall

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
