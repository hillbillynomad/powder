/**
 * Unit tests for powder/web/js/snow.js (the real file): model agreement, snow-quality labels
 * and the fresh-snow cover shown on flyovers.
 */
import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const source = fs.readFileSync(path.resolve(__dirname, '../../../powder/web/js/snow.js'), 'utf8');
const module = { exports: {} };
new Function('module', source)(module);
const S = module.exports;

describe('modelSpread', () => {
  it('needs at least two models', () => {
    expect(S.modelSpread({ 'Open-Meteo': 5 })).toBeNull();
    expect(S.modelSpread({})).toBeNull();
    expect(S.modelSpread(null)).toBeNull();
  });

  it('agrees when everyone says little or nothing', () => {
    expect(S.modelSpread({ 'Open-Meteo': 0, ECMWF: 0.8 }).level).toBe('agree');
  });

  it('agrees when the gap is small relative to the amount', () => {
    const s = S.modelSpread({ 'Open-Meteo': 10, ECMWF: 12, NWS: 11 });
    expect(s).toEqual({ lo: 10, hi: 12, n: 3, level: 'agree' });
  });

  it('is split when one model calls for far more', () => {
    expect(S.modelSpread({ 'Open-Meteo': 18, ECMWF: 4 }).level).toBe('split');
    expect(S.modelSpread({ 'Open-Meteo': 6, ECMWF: 0 }).level).toBe('split');
  });

  it('is mixed in between', () => {
    expect(S.modelSpread({ 'Open-Meteo': 10, ECMWF: 5 }).level).toBe('mixed');
    expect(S.modelSpread({ 'Open-Meteo': 3, ECMWF: 0 }).level).toBe('mixed'); // gap < 4
  });

  it('ignores non-numbers', () => {
    expect(S.modelSpread({ 'Open-Meteo': 4, ECMWF: null, NWS: 'x' })).toBeNull();
  });
});

describe('agreementSummary', () => {
  const days = [
    { date: '2026-01-02', sources: { 'Open-Meteo': 10, ECMWF: 2, NWS: 4 } },
    { date: '2026-01-01', sources: { 'Open-Meteo': 1, ECMWF: 1, NWS: 1 } },
    { date: '2026-01-03', sources: { 'Open-Meteo': 0, ECMWF: 0 } }, // NWS ran out
  ];

  it('counts agreeing days and ranges totals over models that cover every day', () => {
    const s = S.agreementSummary(days, 3);
    expect(s.days).toBe(3);
    expect(s.totalDays).toBe(3);
    expect(s.agreeDays).toBe(2);
    expect(s.totalLo).toBe(3); // ECMWF 1 + 2 + 0; NWS is left out (missing a day)
    expect(s.totalHi).toBe(11);
    expect(s.level).toBe('split');
  });

  it('only looks at the first N days in date order', () => {
    const s = S.agreementSummary(days, 1);
    expect(s.days).toBe(1);
    expect(s.totalLo).toBe(1);
    expect(s.level).toBe('agree');
  });

  it('skips single-model days when picking the window', () => {
    const s = S.agreementSummary([
      { date: '2026-01-01', sources: { 'Open-Meteo': 3 } },
      { date: '2026-01-02', sources: { 'Open-Meteo': 4, ECMWF: 4 } },
    ], 7);
    expect(s.days).toBe(1);
    expect(s.totalLo).toBe(4);
  });

  it('handles no data', () => {
    expect(S.agreementSummary([], 7)).toMatchObject({ totalDays: 0, totalLo: null, level: null });
    expect(S.agreementSummary(undefined).days).toBe(0);
  });
});

describe('modelTooltip', () => {
  it('uses model names', () => {
    expect(S.modelTooltip({ 'Open-Meteo': 18, ECMWF: 4 })).toBe('GFS 18″ · ECMWF 4″');
    expect(S.modelTooltip({ Other: 1 })).toBe('Other 1″');
  });
});

describe('qualityLabel', () => {
  it('calls the lightest snow champagne powder', () => {
    expect(S.qualityLabel('champagne').label).toBe('Champagne powder');
  });

  it('has a label and hint for every rating', () => {
    for (const q of ['champagne', 'powder', 'heavy', 'mixed', 'rain']) {
      expect(S.qualityLabel(q).hint.length).toBeGreaterThan(10);
    }
  });

  it('returns null for unknown or missing ratings', () => {
    expect(S.qualityLabel(null)).toBeNull();
    expect(S.qualityLabel('slush')).toBeNull();
  });
});

describe('bestDay', () => {
  it('picks the biggest rated day, skipping rain and unrated days', () => {
    const best = S.bestDay([
      { date: 'a', avg_inches: 20, conditions: { quality: 'rain' } },
      { date: 'b', avg_inches: 6, conditions: { quality: 'powder' } },
      { date: 'c', avg_inches: 9, conditions: { quality: 'champagne' } },
      { date: 'd', avg_inches: 30 },
    ]);
    expect(best.date).toBe('c');
  });

  it('returns null with nothing rated', () => {
    expect(S.bestDay([{ date: 'a', avg_inches: 3 }])).toBeNull();
    expect(S.bestDay(undefined)).toBeNull();
  });
});

describe('freshSnowCover', () => {
  const resort = {
    historical_snowfall: [
      { date: '2026-01-07', snowfall_inches: 20, conditions: { snow_line_ft: 1000 } }, // too old
      { date: '2026-01-08', snowfall_inches: 4, conditions: { snow_line_ft: 6200 } },
      { date: '2026-01-09', snowfall_inches: 3, conditions: { snow_line_ft: 5400 } },
    ],
    daily_forecasts: [
      { date: '2026-01-10', avg_inches: 1, conditions: { snow_line_ft: 7000 } },
      { date: '2026-01-11', avg_inches: 30, conditions: { snow_line_ft: 100 } }, // future
    ],
  };

  it('sums two past days plus today and takes the lowest snow line', () => {
    const c = S.freshSnowCover(resort, '2026-01-10');
    expect(c.inches72).toBe(8);
    expect(c.snowLineFt).toBe(5400);
    expect(c.opacity).toBeCloseTo(0.56);
  });

  it('counts a past day the export filed under forecasts', () => {
    const r = {
      historical_snowfall: [{ date: '2026-01-08', snowfall_inches: 3, conditions: { snow_line_ft: 0 } }],
      daily_forecasts: [
        { date: '2026-01-09', avg_inches: 2, conditions: { snow_line_ft: 500 } },
        { date: '2026-01-10', avg_inches: 1, conditions: {} },
      ],
    };
    expect(S.freshSnowCover(r, '2026-01-10').inches72).toBe(6);
  });

  it('caps opacity for big storms', () => {
    const big = { historical_snowfall: [{ date: '2026-01-09', snowfall_inches: 40, conditions: { snow_line_ft: 0 } }] };
    expect(S.freshSnowCover(big, '2026-01-10').opacity).toBe(0.7);
  });

  it('is null with too little snow or no snow line', () => {
    const light = { daily_forecasts: [{ date: '2026-01-10', avg_inches: 0.5, conditions: { snow_line_ft: 3000 } }] };
    expect(S.freshSnowCover(light, '2026-01-10')).toBeNull();
    const noLine = { historical_snowfall: [{ date: '2026-01-09', snowfall_inches: 5 }] };
    expect(S.freshSnowCover(noLine, '2026-01-10')).toBeNull();
    expect(S.freshSnowCover(null, '2026-01-10')).toBeNull();
  });

  it('crosses month boundaries', () => {
    expect(S.addDays('2026-03-01', -2)).toBe('2026-02-27');
  });
});

describe('lapseTempF', () => {
  it('cools about 3.6°F per 1,000 ft going up', () => {
    expect(S.lapseTempF(20, 8000, 9000)).toBeCloseTo(16.43, 1);
    expect(S.lapseTempF(20, 9000, 8000)).toBeCloseTo(23.57, 1);
  });
});

describe('todayIsoIn', () => {
  it('uses the resort time zone', () => {
    const t = Date.parse('2026-01-10T03:00:00Z');
    expect(S.todayIsoIn('America/Denver', t)).toBe('2026-01-09');
    expect(S.todayIsoIn('Asia/Tokyo', t)).toBe('2026-01-10');
  });

  it('falls back to UTC for a bad zone', () => {
    expect(S.todayIsoIn('Not/AZone', Date.parse('2026-01-10T03:00:00Z'))).toBe('2026-01-10');
  });
});

describe('freshSnowColor', () => {
  it('ramps from clear below the snow line to whiter with height, in metres', () => {
    const expr = S.freshSnowColor(3280.84, 0.5);
    expect(expr.slice(0, 3)).toEqual(['interpolate', ['linear'], ['elevation']]);
    expect(expr[3]).toBeCloseTo(900);
    expect(expr[4]).toBe('rgba(255, 255, 255, 0)');
    expect(expr[5]).toBeCloseTo(1100);
    expect(expr[6]).toBe('rgba(255, 255, 255, 0.15)');
    expect(expr[9]).toBeCloseTo(2000);
    expect(expr[10]).toBe('rgba(255, 255, 255, 0.5)');
  });
});
