/**
 * Vitest setup file - sets up global test environment
 */

// Mock Leaflet
globalThis.L = {
  map: () => ({
    setView: () => ({ on: () => {} }),
    fitBounds: () => {},
    panTo: () => {},
  }),
  tileLayer: () => ({ addTo: () => {} }),
  circleMarker: () => ({
    addTo: () => {},
    on: () => {},
    bindPopup: () => {},
  }),
  control: {
    zoom: () => ({ addTo: () => {} }),
  },
};

// Mock ApexCharts
globalThis.ApexCharts = class {
  constructor() {}
  render() { return Promise.resolve(); }
  destroy() {}
  updateOptions() {}
};

// Constants from app.js
globalThis.MIN_RADIUS = 5;
globalThis.COUNTRY_NAMES = {
  'AD': 'Andorra', 'AR': 'Argentina', 'AT': 'Austria', 'AU': 'Australia',
  'BG': 'Bulgaria', 'CA': 'Canada', 'CH': 'Switzerland', 'CL': 'Chile',
  'CZ': 'Czech Republic', 'DE': 'Germany', 'ES': 'Spain', 'FI': 'Finland',
  'FR': 'France', 'IT': 'Italy', 'JP': 'Japan', 'KR': 'South Korea',
  'NO': 'Norway', 'NZ': 'New Zealand', 'PL': 'Poland', 'RO': 'Romania',
  'SE': 'Sweden', 'SI': 'Slovenia', 'SK': 'Slovakia', 'US': 'United States'
};

// Pure functions extracted from app.js for testing
// These are exact copies of the functions from app.js

globalThis.getRadius = function(totalInches) {
  if (totalInches <= 0) return MIN_RADIUS;
  return MIN_RADIUS + (totalInches / 2);
};

globalThis.getCountryName = function(code) {
  return COUNTRY_NAMES[code] || code;
};

globalThis.formatDate = function(dateStr) {
  const date = new Date(dateStr + 'T00:00:00');
  return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
};

globalThis.daysBetween = function(date1, date2) {
  const d1 = new Date(date1 + 'T00:00:00');
  const d2 = new Date(date2 + 'T00:00:00');
  return Math.round((d1 - d2) / (1000 * 60 * 60 * 24));
};

globalThis.getSnowfallForFilter = function(resort, filterValue) {
  switch (filterValue) {
    case 'forecast': return resort.total_snowfall_inches || 0;
    case 'historical': return resort.total_historical_inches || 0;
    case 'total': return (resort.total_snowfall_inches || 0) + (resort.total_historical_inches || 0);
    default: return resort.total_snowfall_inches || 0;
  }
};

globalThis.getCumulativeChartData = function(resort, today) {
  const allDays = [];

  for (const h of resort.historical_snowfall || []) {
    allDays.push({ date: h.date, value: h.snowfall_inches || 0 });
  }
  for (const f of resort.daily_forecasts || []) {
    allDays.push({ date: f.date, value: f.avg_inches || 0 });
  }

  allDays.sort((a, b) => a.date.localeCompare(b.date));

  const points = [];
  let cumulative = 0;
  for (const day of allDays) {
    cumulative += day.value;
    points.push({
      date: day.date,
      dayOffset: daysBetween(day.date, today),
      daily: day.value,
      cumulative: cumulative
    });
  }

  return points;
};

globalThis.getElevationText = function(resort) {
  if (resort.elevation_peak_ft && resort.vertical_drop_ft) {
    return `${resort.elevation_base_ft.toLocaleString()} - ${resort.elevation_peak_ft.toLocaleString()} ft (${resort.vertical_drop_ft.toLocaleString()}' vert)`;
  } else if (resort.elevation_base_ft) {
    return `${resort.elevation_base_ft.toLocaleString()} ft elev`;
  } else if (resort.elevation_ft) {
    return `${resort.elevation_ft.toLocaleString()} ft elev`;
  }
  return 'Elevation unknown';
};

globalThis.getSourcesFromForecasts = function(dailyForecasts) {
  const sources = new Set();
  for (const forecast of dailyForecasts || []) {
    for (const source of Object.keys(forecast.sources || {})) {
      sources.add(source);
    }
  }
  return Array.from(sources).sort();
};
