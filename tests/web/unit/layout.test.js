/**
 * Layout / panel-state tests that run against the real app.js and style.css
 * (not copies). jsdom has no layout engine, so scroll/size behaviour itself is
 * covered by the Playwright specs; here we guard the logic and CSS invariants.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const WEB = path.resolve(__dirname, '../../../powder/web');
const appSource = fs.readFileSync(path.join(WEB, 'js/app.js'), 'utf8');
const css = fs.readFileSync(path.join(WEB, 'css/style.css'), 'utf8');

function loadApp() {
  const module = { exports: {} };
  new Function('module', appSource)(module);
  return module.exports;
}

function setupDom() {
  document.body.innerHTML = `
    <aside id="side-panel" class="side-panel" data-snap="peek">
      <button id="panel-collapse" aria-expanded="true"></button>
      <button class="panel-tab active" data-tab="top10"></button>
      <button class="panel-tab" data-tab="details"></button>
      <div id="top10-content" class="tab-content"></div>
      <div id="details-content" class="tab-content hidden"><div id="detail-content"></div></div>
    </aside>
    <button id="panel-reopen" hidden></button>
    <select id="snow-filter"><option value="forecast">f</option></select>`;
}

const resort = {
  name: 'Test Mountain', country: 'US', region: 'UT',
  total_snowfall_inches: 10, daily_forecasts: [], historical_snowfall: [],
};

describe('computeMinZoom', () => {
  const { computeMinZoom } = loadApp();

  it('fits the whole globe in a desktop window (limited by height)', () => {
    // 900px tall -> globe may be ~810px -> log2(pi*0.9*900/512) = 2.3 -> 2.0
    expect(computeMinZoom(1900, 900)).toBe(2);
  });

  it('fits the whole globe on a phone in portrait (limited by width)', () => {
    // 390px wide -> log2(pi*0.9*390/512) = 1.1 -> 1.0
    expect(computeMinZoom(390, 600)).toBe(1);
  });

  it('is orientation independent', () => {
    expect(computeMinZoom(844, 390)).toBe(computeMinZoom(390, 844));
  });

  it('never goes negative and survives a zero-size container', () => {
    expect(computeMinZoom(10, 10)).toBe(0);
    expect(computeMinZoom(0, 0)).toBe(1);
  });
});

describe('marker radius expression', () => {
  const { buildRadiusExpression, zoomScaleAt } = loadApp();

  it('scales at 0.1x the zoom rate, anchored at MIN_ZOOM', () => {
    expect(zoomScaleAt(1)).toBe(1);
    expect(zoomScaleAt(11)).toBeCloseTo(2, 10); // +10 zoom levels -> 2^(0.1*10)
  });

  it('is a top-level zoom interpolate (the only place MapLibre allows zoom)', () => {
    const expr = buildRadiusExpression();
    expect(expr.slice(0, 3)).toEqual(['interpolate', ['linear'], ['zoom']]);
    // stops come in (zoom, output) pairs and zoom is strictly ascending
    const zooms = expr.slice(3).filter((_, i) => i % 2 === 0);
    expect(zooms).toEqual([...zooms].sort((a, b) => a - b));
    expect(new Set(zooms).size).toBe(zooms.length);
    expect(expr[4]).toEqual(['*', ['get', 'r'], zoomScaleAt(0)]);
  });
});

describe('resortToFeature', () => {
  const { resortToFeature } = loadApp();

  it('emits GeoJSON in [lng, lat] order with the index and radius', () => {
    const f = resortToFeature({ latitude: 39.6, longitude: -106.4 }, 7, 12.5, false);
    expect(f.geometry.coordinates).toEqual([-106.4, 39.6]);
    expect(f.properties).toEqual({ idx: 7, r: 12.5, ring: false });
  });
});

describe('layer preferences', () => {
  const app = loadApp();

  beforeEach(() => localStorage.clear());

  it('defaults to satellite with labels and trails, terrain off', () => {
    expect(app.loadLayerPrefs()).toEqual({ mode: 'sat', labels: true, terrain: false, threeD: false, trails: true });
  });

  it('round-trips through localStorage', () => {
    const prefs = { mode: 'topo', labels: false, terrain: true, threeD: true, trails: false };
    app.saveLayerPrefs(prefs);
    expect(app.loadLayerPrefs()).toEqual(prefs);
  });

  it('ignores corrupt or hostile stored values', () => {
    localStorage.setItem('powder.layerPrefs', '{"mode":"<script>","terrain":"yes","labels":false,"x":1}');
    expect(app.loadLayerPrefs()).toEqual({ mode: 'sat', labels: false, terrain: false, threeD: false, trails: true });
    localStorage.setItem('powder.layerPrefs', 'not json');
    expect(app.loadLayerPrefs().mode).toBe('sat');
  });

  it('survives unavailable storage', () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
    expect(() => app.loadLayerPrefs()).not.toThrow();
    spy.mockRestore();
  });
});

describe('layer visibility rules', () => {
  const { isLayerVisible } = loadApp();
  const prefs = (over) => ({ mode: 'sat', labels: true, terrain: false, threeD: false, trails: true, ...over });

  it('shows exactly one base map', () => {
    expect([isLayerVisible('base-sat', prefs()), isLayerVisible('base-topo', prefs()), isLayerVisible('osm-water', prefs())])
      .toEqual([true, false, false]);
    expect([isLayerVisible('base-sat', prefs({ mode: 'map' })), isLayerVisible('osm-water', prefs({ mode: 'map' }))])
      .toEqual([false, true]);
    expect(isLayerVisible('base-topo', prefs({ mode: 'topo' }))).toBe(true);
  });

  it('draws the label overlay only on satellite with labels enabled', () => {
    expect(isLayerVisible('lbl-label_city', prefs())).toBe(true);
    expect(isLayerVisible('lbl-label_city', prefs({ labels: false }))).toBe(false);
    expect(isLayerVisible('lbl-label_city', prefs({ mode: 'map' }))).toBe(false); // Map mode has its own labels
    expect(isLayerVisible('lbl-label_city', prefs({ mode: 'topo' }))).toBe(false);
  });

  it('terrain toggle drives hillshade and contours; trails toggle drives lifts and pistes', () => {
    for (const id of ['terrain-hillshade', 'terrain-contours-major']) {
      expect(isLayerVisible(id, prefs())).toBe(false);
      expect(isLayerVisible(id, prefs({ terrain: true }))).toBe(true);
    }
    for (const id of ['trails-pistes', 'trails-lifts']) {
      expect(isLayerVisible(id, prefs())).toBe(true);
      expect(isLayerVisible(id, prefs({ trails: false }))).toBe(false);
    }
  });

  it('never hides the resort bubbles or background', () => {
    expect(isLayerVisible('resorts', prefs({ mode: 'topo', trails: false }))).toBe(true);
    expect(isLayerVisible('background', prefs())).toBe(true);
  });
});

describe('buildMapStyle', () => {
  const { buildMapStyle, buildLabelOverlayLayers } = loadApp();
  const prefs = { mode: 'sat', labels: true, terrain: false, threeD: false, trails: true };
  const vector = {
    sprite: 'https://example.test/sprite',
    glyphs: 'https://example.test/{fontstack}/{range}.pbf',
    layers: [
      { id: 'background', type: 'background' },
      { id: 'water', type: 'fill', source: 'openmaptiles', 'source-layer': 'water' },
      { id: 'label_city', type: 'symbol', source: 'openmaptiles', 'source-layer': 'place', layout: { 'text-field': '{name}' } },
      { id: 'poi_r1', type: 'symbol', source: 'openmaptiles', 'source-layer': 'poi' },
      { id: 'road_shield_us', type: 'symbol', source: 'openmaptiles', 'source-layer': 'transportation_name' },
    ],
  };

  it('is a globe style with unique layer ids', () => {
    const style = buildMapStyle(vector, prefs);
    expect(style.projection).toEqual({ type: 'globe' });
    const ids = style.layers.map(l => l.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('references only sources that exist', () => {
    const style = buildMapStyle(vector, prefs);
    for (const layer of style.layers) {
      if (layer.source) expect(style.sources).toHaveProperty(layer.source);
    }
  });

  it('works without the vector style (raster modes only)', () => {
    const style = buildMapStyle(null, prefs);
    expect(style.layers.some(l => l.id.startsWith('osm-'))).toBe(false);
    expect(style.sources.openmaptiles).toBeUndefined();
    expect(style.layers.map(l => l.id)).toContain('base-sat');
  });

  it('sets initial visibility from preferences', () => {
    const style = buildMapStyle(vector, { ...prefs, mode: 'topo' });
    const vis = Object.fromEntries(style.layers.map(l => [l.id, l.layout.visibility]));
    expect(vis['base-topo']).toBe('visible');
    expect(vis['base-sat']).toBe('none');
    expect(vis['osm-water']).toBe('none');
    expect(vis['osm-background']).toBe('none'); // Liberty's own land colour only belongs to Map mode
  });

  it('label overlay keeps place names and drops icons, shields and POIs', () => {
    const labels = buildLabelOverlayLayers(vector.layers);
    expect(labels.map(l => l.id)).toEqual(['lbl-label_city']);
    expect(labels[0].paint['text-color']).toBe('#ffffff');
  });
});

describe('nextPanelState', () => {
  const { nextPanelState } = loadApp();

  it('toggles open <-> collapsed (single open height in both layouts)', () => {
    expect(nextPanelState('peek')).toBe('collapsed');
    expect(nextPanelState('full')).toBe('collapsed');
    expect(nextPanelState('collapsed')).toBe('peek');
  });
});

describe('side panel state', () => {
  let app;
  beforeEach(() => {
    setupDom();
    localStorage.clear();
    vi.stubGlobal('requestAnimationFrame', () => 0);
    app = loadApp();
  });

  const panel = () => document.getElementById('side-panel');
  const reopen = () => document.getElementById('panel-reopen');

  it('collapsing shows the reopen handle and expanding hides it', () => {
    app.setPanelState('collapsed');
    expect(panel().classList.contains('collapsed')).toBe(true);
    expect(reopen().hidden).toBe(false);
    expect(document.getElementById('panel-collapse').getAttribute('aria-expanded')).toBe('false');

    app.reopenPanel();
    expect(panel().classList.contains('collapsed')).toBe(false);
    expect(reopen().hidden).toBe(true);
  });

  it('hideDetail returns to Top 10 and never collapses the panel', () => {
    app.showDetail(resort);
    expect(document.getElementById('details-content').classList.contains('hidden')).toBe(false);
    app.hideDetail();
    expect(document.getElementById('top10-content').classList.contains('hidden')).toBe(false);
    expect(panel().classList.contains('collapsed')).toBe(false);
  });

  it('showDetail reopens a collapsed panel', () => {
    app.setPanelState('collapsed');
    app.showDetail(resort);
    expect(app.getPanelState()).not.toBe('collapsed');
    expect(reopen().hidden).toBe(true);
  });

  it('open height is identical on load and after collapse/reopen', () => {
    const open = () => { expect(css).toMatch(/flex:\s*0 0 52%/); expect(css).not.toMatch(/data-snap="full"\]\s*\{\s*flex-basis/); };
    open();
    app.togglePanelCollapse();
    app.togglePanelCollapse();
    expect(app.getPanelState()).toBe('peek');
  });

  it('reopen handle is visible iff the panel is collapsed (never unrecoverable)', () => {
    const actions = [
      () => app.togglePanelCollapse(),
      () => app.showDetail(resort),
      () => app.hideDetail(),
      () => app.setPanelState('collapsed'),
      () => app.reopenPanel(),
    ];
    for (let i = 0; i < 200; i++) {
      actions[(i * 7 + (i >> 2)) % actions.length]();
      expect(reopen().hidden).toBe(app.getPanelState() !== 'collapsed');
    }
  });

  it('persists and restores state, tolerating unavailable storage', () => {
    app.setPanelState('full');
    expect(localStorage.getItem('powder.panelState')).toBe('full');

    setupDom();
    const fresh = loadApp();
    fresh.restorePanelState();
    expect(fresh.getPanelState()).toBe('full');

    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
    const another = loadApp();
    expect(() => another.restorePanelState()).not.toThrow();
    expect(another.getPanelState()).toBe('peek');
    spy.mockRestore();
  });
});

describe('CSS invariants (app shell must not be scrollable)', () => {
  function rule(selector) {
    const re = new RegExp('(^|\\})\\s*' + selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s*\\{([^}]*)\\}', 'm');
    const m = css.match(re);
    return m ? m[2] : null;
  }

  it.each(['.main-container', '.content-wrapper', '.map-wrapper'])(
    '%s uses overflow: clip, not a scroll container', (sel) => {
      const body = rule(sel);
      expect(body).not.toBeNull();
      expect(body).toMatch(/overflow:\s*clip/);
      expect(body).not.toMatch(/overflow(-[xy])?:\s*(hidden|auto|scroll)/);
    });

  it('body has a fixed viewport height rather than min-height: 100vh', () => {
    expect(rule('body')).toMatch(/height:\s*100dvh/);
    expect(css).not.toMatch(/min-height:\s*100vh/);
  });

  it('#map has no fixed min-height that can overflow its container', () => {
    expect(rule('#map')).not.toMatch(/min-height:\s*\d+px/);
  });

  it('bottom-sheet media query matches BOTTOM_PANEL_QUERY in app.js', () => {
    const q = appSource.match(/BOTTOM_PANEL_QUERY = '([^']+)'/)[1];
    expect(css).toContain(`@media ${q}`);
  });
});

describe('share links', () => {
  const { parseShareParams, buildShareUrl } = loadApp();
  const base = 'https://example.test/powder/';
  const prefs = { mode: 'sat', labels: true, terrain: true, threeD: false, trails: true };

  it('round-trips camera, layers, filters and resort', () => {
    const state = {
      camera: { lat: 39.60512, lng: -106.37549, zoom: 13.456, bearing: 29.6, pitch: 41.2 },
      prefs: { mode: 'topo', labels: false, terrain: true, threeD: true, trails: false },
      filters: { snow: 'total' },
      resort: 'Vail',
    };
    const parsed = parseShareParams(new URL(buildShareUrl(base, state)).search);
    expect(parsed.camera).toEqual({ lat: 39.6051, lng: -106.3755, zoom: 13.46, bearing: 30, pitch: 41 });
    expect(parsed.prefs).toEqual({ mode: 'topo', labels: false, terrain: true, threeD: true, trails: false });
    expect(parsed.filters).toEqual({ snow: 'total' });
    expect(parsed.resort).toBe('Vail');
  });

  it('omits default filters, zero bearing/pitch and the camera when the map is unavailable', () => {
    const url = buildShareUrl(base, { camera: null, prefs, filters: { snow: 'forecast' }, resort: null });
    const q = new URL(url).searchParams;
    expect([...q.keys()].sort()).toEqual(['3d', 'base', 'labels', 'terrain', 'trails']);
  });

  it('encodes resort names with spaces and special characters safely', () => {
    const url = buildShareUrl(base, { camera: null, prefs, filters: {}, resort: 'Zakopane (Kasprowy Wierch) & Co' });
    expect(parseShareParams(new URL(url).search).resort).toBe('Zakopane (Kasprowy Wierch) & Co');
  });

  it('drops malformed or out-of-range values instead of trusting them', () => {
    const parsed = parseShareParams('?lat=abc&lng=999&z=-4&base=<script>&labels=maybe&snow=x');
    expect(parsed.camera).toBeNull();
    expect(parsed.prefs).toEqual({});
    expect(parsed.filters).toEqual({});
    expect(parseShareParams('').camera).toBeNull();
  });

  it('clamps nothing silently: pitch beyond 85 and zoom beyond max are rejected, defaults apply', () => {
    const parsed = parseShareParams('?lat=10&lng=20&z=99&p=120');
    expect(parsed.camera).toEqual({ lat: 10, lng: 20, zoom: 4, bearing: 0, pitch: 0 });
  });

  it('requires both lat and lng for a camera', () => {
    expect(parseShareParams('?lat=10').camera).toBeNull();
    expect(parseShareParams('?lng=10').camera).toBeNull();
  });

  it('rejects overlong text values', () => {
    expect(parseShareParams('?resort=' + 'x'.repeat(500)).resort).toBeNull();
  });
});
