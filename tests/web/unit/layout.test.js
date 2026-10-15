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
      <button class="panel-mode active" data-mode="view">In view <span id="view-count"></span></button>
      <button class="panel-mode" data-mode="top10">Top 10</button>
      <button class="panel-mode" data-mode="search" hidden>Search <span id="search-count"></span></button>
      <div class="panel-content">
        <div id="list-content" class="tab-content">
          <div id="list-summary"></div><div id="resort-list"></div>
        </div>
        <div id="details-content" class="tab-content hidden">
          <span id="detail-back-label"></span><div id="detail-content"></div>
        </div>
      </div>
    </aside>
    <button id="panel-reopen" hidden></button>
    <input id="search-input"><button id="search-clear" hidden></button>
    <select id="snow-filter"><option value="forecast">f</option></select>`;
}

const resort = {
  name: 'Test Mountain', country: 'US', region: 'UT',
  total_snowfall_inches: 10, daily_forecasts: [], historical_snowfall: [],
};

describe('searchResorts', () => {
  const { searchResorts } = loadApp();
  const resorts = ['Park City', 'Deer Valley', 'Big Sky', "Val d'Isère", 'Snowbird', 'Valle Nevado']
    .map(name => ({ name }));
  const names = (q, limit) => searchResorts(resorts, q, limit).map(r => r.name);

  it('matches case-insensitively anywhere in the name', () => {
    expect(names('VALLEY')).toEqual(['Deer Valley']);
    expect(names('bird')).toEqual(['Snowbird']);
  });

  it('ranks name-prefix, then word-prefix, then substring matches', () => {
    expect(names('val')).toEqual(["Val d'Isère", 'Valle Nevado', 'Deer Valley']);
  });

  it('ignores accents', () => {
    expect(names('isere')).toEqual(["Val d'Isère"]);
  });

  it('returns nothing for blank or unmatched queries and honours the limit', () => {
    expect(names('   ')).toEqual([]);
    expect(names('zermatt')).toEqual([]);
    expect(names('a', 2)).toHaveLength(2);
  });
});

describe('filterInView', () => {
  const { filterInView, angularDistance } = loadApp();
  const at = (name, latitude, longitude) => ({ name, latitude, longitude });
  // Flat stand-in projection: 10px per degree around the centre
  const view = (lat, lng, width = 400, height = 300) => ({
    center: { lat, lng }, width, height,
    project: ([x, y]) => ({ x: width / 2 + (x - lng) * 10, y: height / 2 - (y - lat) * 10 }),
  });

  it('measures great-circle distance in degrees', () => {
    expect(angularDistance(0, 0, 0, 90)).toBeCloseTo(90, 6);
    expect(angularDistance(40, -111, 40, -111)).toBeCloseTo(0, 4);
    expect(angularDistance(90, 0, -90, 0)).toBeCloseTo(180, 6);
  });

  it('keeps resorts inside the map box and drops those outside it', () => {
    const resorts = [at('Alta', 40.6, -111.6), at('Vail', 39.6, -106.4), at('Chamonix', 45.9, 6.9)];
    expect(filterInView(resorts, view(40.5, -111.5, 60, 60)).map(r => r.name)).toEqual(['Alta']);
    expect(filterInView(resorts, view(40, -109, 1000, 400)).map(r => r.name)).toEqual(['Alta', 'Vail']);
  });

  it('drops resorts round the back of the globe even if they project on screen', () => {
    const everywhere = { center: { lat: 37.5, lng: -119.5 }, width: 400, height: 300, project: () => ({ x: 10, y: 10 }) };
    const names = filterInView([at('Mammoth', 37.6, -119.0), at('Thredbo', -36.5, 148.3)], everywhere).map(r => r.name);
    expect(names).toEqual(['Mammoth']);
  });
});

describe('side panel list modes and search', () => {
  let app;
  const resorts = [
    { name: 'Alta', country: 'US', region: 'UT', latitude: 40.6, longitude: -111.6, total_snowfall_inches: 4 },
    { name: 'Snowbird', country: 'US', region: 'UT', latitude: 40.6, longitude: -111.7, total_snowfall_inches: 9 },
    { name: 'Niseko', country: 'JP', region: 'Hokkaido', latitude: 42.8, longitude: 140.7, total_snowfall_inches: 20 },
  ];
  const listNames = () => [...document.querySelectorAll('#resort-list .resort-item .name')].map(n => n.textContent);
  const modeButton = (mode) => document.querySelector(`.panel-mode[data-mode="${mode}"]`);

  beforeEach(() => {
    setupDom();
    localStorage.clear();
    vi.stubGlobal('requestAnimationFrame', () => 0);
    app = loadApp();
    app.setResortData(resorts);
  });

  it('defaults to In view, sorted by snowfall', () => {
    app.renderList();
    expect(app.getListMode()).toBe('view');
    expect(listNames()).toEqual(['Niseko', 'Snowbird', 'Alta']);
  });

  it('Top 10 ranks resorts worldwide', () => {
    app.setListMode('top10');
    expect(modeButton('top10').classList.contains('active')).toBe(true);
    expect(document.querySelector('#resort-list .rank').textContent).toBe('#1');
  });

  it('typing switches to search results; clearing goes back to the previous mode', () => {
    app.setListMode('top10');
    const input = document.getElementById('search-input');
    input.value = 'snow';
    app.onSearchInput();
    expect(app.getListMode()).toBe('search');
    expect(modeButton('search').hidden).toBe(false);
    expect(listNames()).toEqual(['Snowbird']);

    app.clearSearch({ focus: false });
    expect(app.getListMode()).toBe('top10');
    expect(modeButton('search').hidden).toBe(true);
  });

  it('search summary escapes the query', () => {
    const input = document.getElementById('search-input');
    input.value = '<img src=x>';
    app.onSearchInput();
    expect(document.getElementById('list-summary').innerHTML).not.toContain('<img');
    expect(document.getElementById('list-summary').textContent).toContain('No resorts match');
  });

  it('switching mode closes open details', () => {
    app.showDetail(resorts[0]);
    app.setListMode('top10');
    expect(document.getElementById('details-content').classList.contains('hidden')).toBe(true);
  });
});

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

  it('can add a fixed pixel margin for the selection ring', () => {
    expect(buildRadiusExpression(3)[4]).toEqual(['+', ['*', ['get', 'r'], zoomScaleAt(0)], 3]);
  });
});

describe('resortToFeature', () => {
  const { resortToFeature } = loadApp();

  it('emits GeoJSON in [lng, lat] order with the index, radius and name', () => {
    const f = resortToFeature({ name: 'Vail', latitude: 39.6, longitude: -106.4 }, 7, 12.5, false);
    expect(f.geometry.coordinates).toEqual([-106.4, 39.6]);
    expect(f.properties).toEqual({ idx: 7, r: 12.5, ring: false, name: 'Vail' });
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

  it('terrain toggle drives hillshade and contours; trails toggle drives lifts and resort names', () => {
    for (const id of ['terrain-hillshade', 'terrain-contours-major']) {
      expect(isLayerVisible(id, prefs())).toBe(false);
      expect(isLayerVisible(id, prefs({ terrain: true }))).toBe(true);
    }
    for (const id of ['trails-resort-names', 'trails-lifts']) {
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

  it('hideDetail returns to the list and never collapses the panel', () => {
    app.showDetail(resort);
    expect(document.getElementById('details-content').classList.contains('hidden')).toBe(false);
    expect(document.getElementById('list-content').classList.contains('hidden')).toBe(true);
    app.hideDetail();
    expect(document.getElementById('list-content').classList.contains('hidden')).toBe(false);
    expect(document.getElementById('details-content').classList.contains('hidden')).toBe(true);
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

  it('search input is at least 16px so iOS does not zoom the page on focus', () => {
    expect(rule('.search-input')).toMatch(/font-size:\s*16px/);
  });

  it('bottom-sheet media query matches BOTTOM_PANEL_QUERY in app.js', () => {
    const q = appSource.match(/BOTTOM_PANEL_QUERY = '([^']+)'/)[1];
    expect(css).toContain(`@media ${q}`);
  });
});

describe('link preview card', () => {
  const html = fs.readFileSync(path.join(WEB, 'index.html'), 'utf8');
  const meta = (attr, key) => (html.match(new RegExp(`<meta ${attr}="${key}" content="([^"]*)"`)) || [])[1];

  it('points og:image and twitter:image at the bundled still image by absolute URL', () => {
    const image = meta('property', 'og:image');
    expect(image).toMatch(/^https:\/\/.+\/img\/share-card\.png$/);
    expect(meta('name', 'twitter:image')).toBe(image);
    expect(fs.existsSync(path.join(WEB, 'img/share-card.png'))).toBe(true);
    expect(meta('name', 'twitter:card')).toBe('summary_large_image');
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

  it('a flyover link carries the resort and fly=1 but no camera', () => {
    const url = buildShareUrl(base, { camera: null, prefs, filters: {}, resort: 'Snowbird', fly: true });
    const q = new URL(url).searchParams;
    expect(q.get('resort')).toBe('Snowbird');
    expect(q.get('fly')).toBe('1');
    expect(q.has('lat')).toBe(false);
    const parsed = parseShareParams(new URL(url).search);
    expect(parsed.fly).toBe(true);
    expect(parsed.camera).toBeNull();
  });

  it('fly only counts alongside a resort', () => {
    expect(parseShareParams('?fly=1').fly).toBe(false);
    expect(parseShareParams('?resort=Alta&fly=0').fly).toBe(false);
    expect(parseShareParams('?resort=Alta').fly).toBe(false);
  });

  it('requires both lat and lng for a camera', () => {
    expect(parseShareParams('?lat=10').camera).toBeNull();
    expect(parseShareParams('?lng=10').camera).toBeNull();
  });

  it('rejects overlong text values', () => {
    expect(parseShareParams('?resort=' + 'x'.repeat(500)).resort).toBeNull();
  });
});
