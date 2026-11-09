/**
 * Mountain Cams links in the resort panel (webcamsHtml in the real app.js).
 */
import { describe, it, expect, beforeEach } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const WEB = path.resolve(__dirname, '../../../powder/web');
const appSource = fs.readFileSync(path.join(WEB, 'js/app.js'), 'utf8');

function loadApp() {
  const module = { exports: {} };
  new Function('module', appSource)(module);
  return module.exports;
}

const { webcamsHtml, showDetail, setResortData } = loadApp();

function render(html) {
  const div = document.createElement('div');
  div.innerHTML = html;
  return div;
}

const NORTHSTAR_URL = 'https://www.northstarcalifornia.com/the-mountain/mountain-conditions/mountain-cams.aspx';
const northstarCams = [{ label: 'Mountain cams', url: NORTHSTAR_URL }];

describe('webcamsHtml', () => {
  it('is empty when a resort has no webcams', () => {
    expect(webcamsHtml({ name: 'X' })).toBe('');
    expect(webcamsHtml({ name: 'X', webcams: [] })).toBe('');
    expect(webcamsHtml(null)).toBe('');
  });

  it('renders one link per page, opening in a new tab', () => {
    const el = render(webcamsHtml({ webcams: [
      ...northstarCams,
      { label: 'Snow stake', url: 'https://example.com/stake' },
    ] }));
    const links = el.querySelectorAll('.cams-links a');
    expect(links).toHaveLength(2);
    expect(links[0].getAttribute('href')).toBe(NORTHSTAR_URL);
    expect(links[0].textContent).toContain('Mountain cams');
    expect(links[0].querySelector('.cams-host').textContent).toContain('northstarcalifornia.com');
    for (const a of links) {
      expect(a.getAttribute('target')).toBe('_blank');
      expect(a.getAttribute('rel')).toBe('noopener noreferrer');
    }
  });

  it('escapes labels and drops anything that is not https', () => {
    const el = render(webcamsHtml({ webcams: [
      { label: '<b>Peak</b> "cam"', url: 'https://example.com/a' },
      { label: 'Script', url: 'javascript:alert(1)' },
      { label: 'Plain http', url: 'http://example.com/b' },
      { label: '', url: 'https://example.com/c' },
    ] }));
    const links = el.querySelectorAll('.cams-links a');
    expect(links).toHaveLength(1);
    expect(links[0].querySelector('b')).toBeNull();
    expect(links[0].textContent).toContain('<b>Peak</b> "cam"');
  });
});

describe('detail panel', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <aside id="side-panel" class="side-panel" data-snap="peek">
        <button id="panel-collapse" aria-expanded="true"></button>
        <div class="panel-content">
          <div id="list-content" class="tab-content"><div id="list-summary"></div><div id="resort-list"></div></div>
          <div id="details-content" class="tab-content hidden"><span id="detail-back-label"></span><div id="detail-content"></div></div>
        </div>
      </aside>
      <button id="panel-reopen" hidden></button>
      <select id="snow-filter"><option value="forecast">f</option></select>`;
  });

  it('shows the cam links after the forecast table', () => {
    const resort = { name: 'Northstar', country: 'US', region: 'CA', total_snowfall_inches: 0,
      daily_forecasts: [], historical_snowfall: [], webcams: northstarCams };
    setResortData([resort]);
    showDetail(resort);
    const content = document.getElementById('detail-content');
    const table = content.querySelector('.forecast-table');
    const cams = content.querySelector('.detail-cams');
    expect(cams).not.toBeNull();
    expect(table.compareDocumentPosition(cams) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('has no cams section for a resort without links', () => {
    const resort = { name: 'Elsewhere', country: 'US', region: 'CA', total_snowfall_inches: 0,
      daily_forecasts: [], historical_snowfall: [] };
    setResortData([resort]);
    showDetail(resort);
    expect(document.querySelector('#detail-content .detail-cams')).toBeNull();
  });
});
