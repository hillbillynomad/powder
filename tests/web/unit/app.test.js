/**
 * Unit tests for pure functions from Powder web UI (app.js)
 *
 * These tests verify the pure utility functions used for:
 * - Bubble radius calculation
 * - Date formatting
 * - Snowfall filtering
 * - Chart data generation
 */

import { describe, it, expect, beforeEach } from 'vitest';

describe('getRadius', () => {
  it('returns MIN_RADIUS for zero snowfall', () => {
    expect(getRadius(0)).toBe(5);
  });

  it('returns MIN_RADIUS for negative snowfall', () => {
    expect(getRadius(-5)).toBe(5);
  });

  it('calculates correct radius for positive snowfall', () => {
    // radius = MIN_RADIUS + (totalInches / 2)
    expect(getRadius(10)).toBe(10); // 5 + (10/2) = 10
    expect(getRadius(20)).toBe(15); // 5 + (20/2) = 15
    expect(getRadius(40)).toBe(25); // 5 + (40/2) = 25
  });

  it('handles decimal values', () => {
    expect(getRadius(5.5)).toBe(7.75); // 5 + (5.5/2) = 7.75
  });
});

describe('formatDate', () => {
  it('formats YYYY-MM-DD to readable format', () => {
    const result = formatDate('2024-01-15');
    // Should contain day of week, month abbreviation, and day number
    expect(result).toMatch(/Mon/);
    expect(result).toMatch(/Jan/);
    expect(result).toMatch(/15/);
  });

  it('handles different months', () => {
    expect(formatDate('2024-12-31')).toMatch(/Dec/);
    expect(formatDate('2024-12-31')).toMatch(/31/);
  });

  it('handles leap year dates', () => {
    expect(formatDate('2024-02-29')).toMatch(/Feb/);
    expect(formatDate('2024-02-29')).toMatch(/29/);
  });
});

describe('getCountryName', () => {
  it('returns full country name for known codes', () => {
    expect(getCountryName('US')).toBe('United States');
    expect(getCountryName('FR')).toBe('France');
    expect(getCountryName('JP')).toBe('Japan');
    expect(getCountryName('CH')).toBe('Switzerland');
    expect(getCountryName('AU')).toBe('Australia');
  });

  it('returns code for unknown countries', () => {
    expect(getCountryName('XX')).toBe('XX');
    expect(getCountryName('ZZ')).toBe('ZZ');
  });

  it('handles all defined country codes', () => {
    const codes = ['AD', 'AR', 'AT', 'AU', 'BG', 'CA', 'CH', 'CL', 'CZ', 'DE',
                   'ES', 'FI', 'FR', 'IT', 'JP', 'KR', 'NO', 'NZ', 'PL', 'RO',
                   'SE', 'SI', 'SK', 'US'];
    for (const code of codes) {
      expect(getCountryName(code)).not.toBe(code);
    }
  });
});

describe('daysBetween', () => {
  it('calculates days between two dates', () => {
    expect(daysBetween('2024-01-15', '2024-01-10')).toBe(5);
    expect(daysBetween('2024-01-10', '2024-01-15')).toBe(-5);
  });

  it('returns 0 for same date', () => {
    expect(daysBetween('2024-01-15', '2024-01-15')).toBe(0);
  });

  it('handles month boundaries', () => {
    expect(daysBetween('2024-02-01', '2024-01-31')).toBe(1);
  });

  it('handles year boundaries', () => {
    expect(daysBetween('2024-01-01', '2023-12-31')).toBe(1);
  });

  it('handles leap year', () => {
    expect(daysBetween('2024-03-01', '2024-02-28')).toBe(2); // 2024 is leap year
  });
});

describe('getSnowfallForFilter', () => {
  const mockResort = {
    total_snowfall_inches: 10.5,
    total_historical_inches: 5.2,
  };

  it('returns forecast snowfall for "forecast" filter', () => {
    expect(getSnowfallForFilter(mockResort, 'forecast')).toBe(10.5);
  });

  it('returns historical snowfall for "historical" filter', () => {
    expect(getSnowfallForFilter(mockResort, 'historical')).toBe(5.2);
  });

  it('returns sum for "total" filter', () => {
    expect(getSnowfallForFilter(mockResort, 'total')).toBe(15.7);
  });

  it('defaults to forecast for unknown filter', () => {
    expect(getSnowfallForFilter(mockResort, 'unknown')).toBe(10.5);
  });

  it('handles missing values gracefully', () => {
    expect(getSnowfallForFilter({}, 'forecast')).toBe(0);
    expect(getSnowfallForFilter({}, 'historical')).toBe(0);
    expect(getSnowfallForFilter({}, 'total')).toBe(0);
  });

  it('handles partial data', () => {
    expect(getSnowfallForFilter({ total_snowfall_inches: 5 }, 'total')).toBe(5);
    expect(getSnowfallForFilter({ total_historical_inches: 3 }, 'total')).toBe(3);
  });
});

describe('getCumulativeChartData', () => {
  const today = '2024-01-15';

  it('combines historical and forecast data chronologically', () => {
    const resort = {
      historical_snowfall: [
        { date: '2024-01-10', snowfall_inches: 2 },
        { date: '2024-01-11', snowfall_inches: 3 },
      ],
      daily_forecasts: [
        { date: '2024-01-15', avg_inches: 4 },
        { date: '2024-01-16', avg_inches: 1 },
      ],
    };

    const data = getCumulativeChartData(resort, today);

    expect(data.length).toBe(4);
    expect(data[0].date).toBe('2024-01-10');
    expect(data[3].date).toBe('2024-01-16');
  });

  it('calculates cumulative snowfall correctly', () => {
    const resort = {
      historical_snowfall: [
        { date: '2024-01-10', snowfall_inches: 2 },
      ],
      daily_forecasts: [
        { date: '2024-01-15', avg_inches: 3 },
      ],
    };

    const data = getCumulativeChartData(resort, today);

    expect(data[0].cumulative).toBe(2);
    expect(data[1].cumulative).toBe(5); // 2 + 3
  });

  it('includes daily values', () => {
    const resort = {
      historical_snowfall: [
        { date: '2024-01-10', snowfall_inches: 5 },
      ],
      daily_forecasts: [],
    };

    const data = getCumulativeChartData(resort, today);

    expect(data[0].daily).toBe(5);
  });

  it('calculates dayOffset correctly', () => {
    const resort = {
      historical_snowfall: [
        { date: '2024-01-10', snowfall_inches: 1 }, // 5 days before today
      ],
      daily_forecasts: [
        { date: '2024-01-17', avg_inches: 2 }, // 2 days after today
      ],
    };

    const data = getCumulativeChartData(resort, today);

    expect(data[0].dayOffset).toBe(-5);
    expect(data[1].dayOffset).toBe(2);
  });

  it('handles empty data', () => {
    const resort = {
      historical_snowfall: [],
      daily_forecasts: [],
    };

    const data = getCumulativeChartData(resort, today);

    expect(data).toEqual([]);
  });

  it('handles missing arrays gracefully', () => {
    const data = getCumulativeChartData({}, today);
    expect(data).toEqual([]);
  });

  it('handles null values in snowfall', () => {
    const resort = {
      historical_snowfall: [
        { date: '2024-01-10', snowfall_inches: null },
      ],
      daily_forecasts: [],
    };

    const data = getCumulativeChartData(resort, today);

    expect(data[0].daily).toBe(0);
    expect(data[0].cumulative).toBe(0);
  });
});

describe('getElevationText', () => {
  it('formats full elevation with vertical drop', () => {
    const resort = {
      elevation_base_ft: 9000,
      elevation_peak_ft: 12000,
      vertical_drop_ft: 3000,
    };

    const text = getElevationText(resort);

    expect(text).toContain('9,000');
    expect(text).toContain('12,000');
    expect(text).toContain('3,000');
    expect(text).toContain('vert');
  });

  it('shows only base elevation when peak is missing', () => {
    const resort = {
      elevation_base_ft: 9000,
    };

    const text = getElevationText(resort);

    expect(text).toContain('9,000');
    expect(text).toContain('elev');
    expect(text).not.toContain('vert');
  });

  it('falls back to elevation_ft for legacy data', () => {
    const resort = {
      elevation_ft: 8500,
    };

    const text = getElevationText(resort);

    expect(text).toContain('8,500');
  });

  it('returns unknown for missing elevation', () => {
    const text = getElevationText({});
    expect(text).toBe('Elevation unknown');
  });
});

describe('getSourcesFromForecasts', () => {
  it('extracts unique sources from forecasts', () => {
    const forecasts = [
      { date: '2024-01-15', sources: { 'Open-Meteo': 1.5, 'ECMWF': 1.2 } },
      { date: '2024-01-16', sources: { 'Open-Meteo': 2.0, 'NWS': 1.8 } },
    ];

    const sources = getSourcesFromForecasts(forecasts);

    expect(sources).toContain('Open-Meteo');
    expect(sources).toContain('ECMWF');
    expect(sources).toContain('NWS');
    expect(sources.length).toBe(3);
  });

  it('returns sorted sources', () => {
    const forecasts = [
      { date: '2024-01-15', sources: { 'NWS': 1, 'ECMWF': 2, 'Open-Meteo': 3 } },
    ];

    const sources = getSourcesFromForecasts(forecasts);

    expect(sources).toEqual(['ECMWF', 'NWS', 'Open-Meteo']);
  });

  it('handles empty forecasts', () => {
    expect(getSourcesFromForecasts([])).toEqual([]);
    expect(getSourcesFromForecasts(null)).toEqual([]);
    expect(getSourcesFromForecasts(undefined)).toEqual([]);
  });

  it('handles forecasts without sources', () => {
    const forecasts = [
      { date: '2024-01-15' },
      { date: '2024-01-16', sources: {} },
    ];

    expect(getSourcesFromForecasts(forecasts)).toEqual([]);
  });
});
