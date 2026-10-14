/**
 * Unit tests for the weather overlay helpers in powder/web/js/weather.js (the real file).
 */
import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const WEB = path.resolve(__dirname, '../../../powder/web');
const source = fs.readFileSync(path.join(WEB, 'js/weather.js'), 'utf8');

function loadWeather() {
  const module = { exports: {} };
  new Function('module', source)(module);
  return module.exports;
}

const W = loadWeather();
const GRID = { ni: 720, nj: 361, lat0: 90, lon0: -180, step: 0.5 };
const TEMP = { kind: 'linear', offset: -80, scale: 0.8 };
const DEPTH = { kind: 'sqrt', max: 200 };

// Codes for a grid where every cell holds the same code
const filled = (code) => new Uint8Array(GRID.ni * GRID.nj).fill(code);

describe('decodeCode', () => {
  it('decodes linear and sqrt encodings (mirrors powder/overlays.py)', () => {
    expect(W.decodeCode(TEMP, 0)).toBe(-80);
    expect(W.decodeCode(TEMP, 140)).toBeCloseTo(32);
    expect(W.decodeCode(DEPTH, 0)).toBe(0);
    expect(W.decodeCode(DEPTH, 255)).toBe(200);
    expect(W.decodeCode(DEPTH, 128)).toBeCloseTo(200 * (128 / 255) ** 2);
  });
});

describe('interpolateStops / buildLut', () => {
  const stops = [[0, [0, 0, 0, 0]], [10, [100, 200, 50, 255]]];

  it('clamps outside the stops and blends between them', () => {
    expect(W.interpolateStops(stops, -5)).toEqual([0, 0, 0, 0]);
    expect(W.interpolateStops(stops, 50)).toEqual([100, 200, 50, 255]);
    expect(W.interpolateStops(stops, 5)).toEqual([50, 100, 25, 127.5]);
  });

  it('builds a 256-entry RGBA table indexed by code', () => {
    const lut = W.buildLut({ kind: 'linear', offset: 0, scale: 10 / 255 }, stops);
    expect(lut).toHaveLength(256 * 4);
    expect([...lut.slice(0, 4)]).toEqual([0, 0, 0, 0]);
    expect([...lut.slice(255 * 4)]).toEqual([100, 200, 50, 255]);
  });

  it('makes bare ground transparent for the snow overlays', () => {
    const { depth, fresh } = W.OVERLAYS;
    expect(W.buildLut(DEPTH, depth.stops)[3]).toBe(0);
    expect(W.buildLut({ kind: 'sqrt', max: 60 }, fresh.stops)[3]).toBe(0);
  });
});

describe('nearestFrameIndex', () => {
  const frames = ['2026-10-14T10:00:00Z', '2026-10-14T11:00:00Z', '2026-10-14T12:00:00Z']
    .map(time => ({ time }));

  it('picks the hour closest to now', () => {
    expect(W.nearestFrameIndex(frames, Date.parse('2026-10-14T11:20:00Z'))).toBe(1);
    expect(W.nearestFrameIndex(frames, Date.parse('2026-10-14T11:40:00Z'))).toBe(2);
  });

  it('clamps to the ends of the range', () => {
    expect(W.nearestFrameIndex(frames, Date.parse('2026-10-01T00:00:00Z'))).toBe(0);
    expect(W.nearestFrameIndex(frames, Date.parse('2026-11-01T00:00:00Z'))).toBe(2);
  });
});

describe('frameLabel', () => {
  const now = Date.parse('2026-10-14T19:00:00Z');
  const hours = (h) => now + h * 3600 * 1000;

  it('labels the time in the given zone and relative to now', () => {
    expect(W.frameLabel(now, now, 'America/Los_Angeles')).toEqual({ when: 'Wed Oct 14, 12 PM', rel: 'now' });
    expect(W.frameLabel(hours(5), now, 'UTC').rel).toBe('+5h');
    expect(W.frameLabel(hours(-3), now, 'UTC').rel).toBe('-3h');
    expect(W.frameLabel(hours(48), now, 'UTC').rel).toBe('+2d');
    expect(W.frameLabel(hours(-27), now, 'UTC').rel).toBe('-1d 3h');
    // Crosses midnight in the viewer's zone: the date moves with it
    expect(W.frameLabel(hours(12), now, 'America/Los_Angeles').when).toBe('Thu Oct 15, 12 AM');
  });
});

describe('mercatorLookup', () => {
  it('maps the image centre to the equator and Greenwich, edges to +-85 degrees', () => {
    const size = 512;
    const { rows, cols } = W.mercatorLookup(GRID, size);
    // Rows straddling the middle sit either side of the equator (row 180 = 0 degrees)
    expect(rows[size / 2 - 1]).toBeLessThan(180);
    expect(rows[size / 2]).toBeGreaterThan(180);
    expect((rows[size / 2 - 1] + rows[size / 2]) / 2).toBeCloseTo(180, 5);
    // Top row is ~85 N: (90 - 85) / 0.5 = row 10
    expect(rows[0]).toBeGreaterThan(9.5);
    expect(rows[0]).toBeLessThan(10.5);
    // Columns span the whole grid, wrapping at the antimeridian
    expect(cols[0]).toBeCloseTo(0.703, 2);
    expect(cols[size - 1]).toBeCloseTo(719.3, 1);
  });
});

describe('renderCodes', () => {
  it('colours every output pixel through the LUT', () => {
    const lut = new Uint8ClampedArray(256 * 4);
    lut.set([10, 20, 30, 40], 7 * 4);
    const size = 16;
    const out = new Uint8ClampedArray(size * size * 4);
    W.renderCodes(filled(7), GRID, lut, W.mercatorLookup(GRID, size), out);
    for (let p = 0; p < out.length; p += 4) {
      expect([...out.slice(p, p + 4)]).toEqual([10, 20, 30, 40]);
    }
  });

  it('blends across the antimeridian instead of reading past the row', () => {
    const codes = filled(0);
    for (let y = 0; y < GRID.nj; y++) codes[y * GRID.ni] = 200; // column 0 = 180 W
    const lut = new Uint8ClampedArray(256 * 4);
    for (let c = 0; c < 256; c++) lut[c * 4] = c;
    const size = 1024;
    const out = new Uint8ClampedArray(size * size * 4);
    W.renderCodes(codes, GRID, lut, W.mercatorLookup(GRID, size), out);
    const row = size / 2;
    const first = out[(row * size) * 4];
    const last = out[(row * size + size - 1) * 4];
    expect(first).toBeGreaterThan(0); // near 180 W, next to the hot column
    expect(last).toBeGreaterThan(0); // near 180 E, wraps to the same column
  });
});

describe('sampleGrid', () => {
  it('reads the cell under a point, bilinear or nearest', () => {
    const codes = filled(0);
    // lat 66, lng -150 -> row (90-66)/0.5 = 48, col (-150+180)/0.5 = 60
    codes[48 * GRID.ni + 60] = 140; // 32 F
    expect(W.sampleGrid(codes, GRID, TEMP, 66, -150, false)).toBeCloseTo(32);
    expect(W.sampleGrid(codes, GRID, TEMP, 66, -150, true)).toBeCloseTo(32);
    // Half a cell east: bilinear blends with the -80 F neighbour, nearest snaps
    expect(W.sampleGrid(codes, GRID, TEMP, 66, -149.75, false)).toBeCloseTo((32 - 80) / 2);
    expect(W.sampleGrid(codes, GRID, TEMP, 66, -149.9, true)).toBeCloseTo(32);
  });

  it('wraps longitudes and clamps latitudes', () => {
    const codes = filled(0);
    codes[48 * GRID.ni + 60] = 140;
    expect(W.sampleGrid(codes, GRID, TEMP, 66, 210, true)).toBeCloseTo(32);
    expect(Number.isFinite(W.sampleGrid(codes, GRID, TEMP, 95, 0, false))).toBe(true);
    expect(Number.isFinite(W.sampleGrid(codes, GRID, TEMP, -95, 179.9, false))).toBe(true);
  });
});

describe('readoutHtml', () => {
  const values = { temp_f: 26.4, depth_in: 5.74, new_in: 0.04, density: 162 };

  it('leads with the active overlay and lists the rest', () => {
    const html = W.readoutHtml('depth', values, '66.01, -150.00');
    expect(html).toMatch(/wx-readout-title">Snow depth</);
    expect(html).toMatch(/wx-readout-value">5.7 in</);
    expect(html).toContain('162 kg/m³');
    expect(html).toContain('26°F');
    expect(html).toContain('<b>0 in</b>'); // trace new snow reads as zero
  });

  it('omits density where there is no snowpack', () => {
    const html = W.readoutHtml('temp', { ...values, depth_in: 0, density: 0 }, '');
    expect(html).toMatch(/wx-readout-value">26°F</);
    expect(html).not.toContain('kg/m³');
  });
});

describe('legend helpers', () => {
  const stops = W.OVERLAYS.temp.stops;

  it('places ticks on the evenly spaced stop scale', () => {
    expect(W.legendTickPosition(stops, stops[0][0])).toBe(0);
    expect(W.legendTickPosition(stops, stops[stops.length - 1][0])).toBe(100);
    expect(W.legendTickPosition(stops, 32)).toBeCloseTo((4 / (stops.length - 1)) * 100);
  });

  it('builds a CSS gradient through every stop', () => {
    const css = W.legendGradient(stops);
    expect(css.startsWith('linear-gradient(90deg,')).toBe(true);
    expect(css.match(/rgba\(/g)).toHaveLength(stops.length);
  });
});
