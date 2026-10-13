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

  it('covers a phone in portrait', () => {
    // 390x600 -> world must be >= 600px -> zoom 1.5 (768px)
    expect(computeMinZoom(390, 600)).toBe(1.5);
  });

  it('covers a desktop window', () => {
    // 1900 px -> log2(1900/256) = 2.89 -> 3
    expect(computeMinZoom(1900, 900)).toBe(3);
  });

  it('is orientation independent', () => {
    expect(computeMinZoom(844, 390)).toBe(computeMinZoom(390, 844));
  });

  it('never goes negative and survives a zero-size container', () => {
    expect(computeMinZoom(100, 100)).toBe(0);
    expect(computeMinZoom(0, 0)).toBe(2);
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
