# Weather Forecast Models Documentation

This document describes the underlying weather models used by each provider in the Powder
application, their strengths, weaknesses, and optimal use cases for ski resort snowfall forecasting.

## Current Providers and Their Models

### 1. Open-Meteo (GFS Model + Historical Archive)
**File:** `open_meteo.py`
**Model:** NOAA GFS (Global Forecast System) for forecasts, ERA5 reanalysis for historical
**API:** https://open-meteo.com/en/docs

#### Forecast Data

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

#### Historical Data (Archive API)

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

### 2. NWS (National Weather Service)
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

### 3. Open-Meteo (ECMWF Model)
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
- European-focused development (though globally accurate)
- Shorter max range than GFS (10 vs 16 days)

**Best For:** Days 3-7 forecasts, mountain terrain accuracy

---

## Model Comparison for Mountain Snowfall

| Model | Mountain Accuracy | Best Range | Update Freq | Resolution |
|-------|-------------------|------------|-------------|------------|
| ECMWF | ★★★★☆ | Days 3-7 | 12 hours | 9km |
| GFS | ★★★☆☆ | Days 4-10 | 6 hours | 25km |
| NWS Blend | ★★★★☆ | Days 1-5 | 6 hours | 2.5km |

### Why Model Diversity Matters

Taking the **median** of forecasts from different models provides:
1. **Reduced bias** - Each model has systematic biases; combining them cancels out
2. **Better uncertainty handling** - When models disagree, confidence is lower
3. **Improved skill** - Multi-model ensembles consistently outperform single models

---

## Other Available Models (Future Expansion)

### HRRR (High-Resolution Rapid Refresh)
- **Resolution:** 3km
- **Range:** 18-48 hours only
- **Best for:** Short-term (0-24hr) precision forecasts
- **Available via:** Open-Meteo
- **Note:** Excellent for "is it snowing right now?" but degrades quickly

### ICON (DWD German Model)
- **Resolution:** 2.2-11km
- **Range:** 10 days
- **Best for:** Alpine/European mountain terrain
- **Available via:** Open-Meteo
- **Note:** Superior valley wind and orographic detail

### NAM (North American Mesoscale)
- **Resolution:** 12km
- **Range:** 3.5 days
- **Best for:** Regional US detail
- **Available via:** Open-Meteo

---

## Mountain-Specific Considerations

### Challenges with Coarse Models
- **Topography smoothing:** A 25km grid cell averages elevations, so a 10,000ft peak
  might be represented as 7,000ft in the model
- **Orographic lift:** Fine-scale uplift on windward slopes is missed
- **Valley effects:** Cold air pooling and temperature inversions require <5km resolution

### Recommendations for Ski Resort Forecasts
1. Use **ECMWF** or **NWS** for primary forecasts (better resolution)
2. Use **GFS** for extended range (days 7-16)
3. Consider **HRRR** for day-of forecasts (if adding a 4th source)
4. Weight recent model runs higher than older ones

---

## References

- [Open-Meteo Documentation](https://open-meteo.com/en/docs)
- [NWS API Documentation](https://www.weather.gov/documentation/services-web-api)
- [ECMWF Model Overview](https://www.ecmwf.int/en/forecasts/documentation-and-support)
- [NOAA GFS Documentation](https://www.ncei.noaa.gov/products/weather-climate-models/global-forecast)
- [Model Comparison - Windy](https://windy.app/blog/ecmwf-vs-gfs-differences-accuracy.html)
