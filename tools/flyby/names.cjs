// List every named feature (all vector-tile layers) near a point, optionally filtered by a
// regex: how to find a resort's runs, bowls, lifts and lodges for hand-crafting a route.
// usage: node tools/flyby/names.cjs <playwright path> <url> <lng> <lat> [regex] [radiusKm=3.5]
const { chromium } = require(process.argv[2]);
const [url, lng, lat] = [process.argv[3], Number(process.argv[4]), Number(process.argv[5])];
const re = process.argv[6] ? new RegExp(process.argv[6], 'i') : null;
const radiusKm = Number(process.argv[7] || 3.5);
const LAYERS = ['aerodrome_label', 'aeroway', 'boundary', 'building', 'housenumber', 'landcover', 'landuse',
  'mountain_peak', 'park', 'place', 'poi', 'transportation', 'transportation_name', 'water', 'water_name', 'waterway'];

(async () => {
  const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1200 } });
  await page.goto(url);
  await page.waitForFunction(() => window.__powder && window.__powder.markerCount() > 0, undefined, { timeout: 90000 });
  // Several z14 views so every tile around the point has been loaded
  const offsets = [[0, 0], [0.012, 0], [-0.012, 0], [0, 0.009], [0, -0.009], [0.012, 0.009], [-0.012, 0.009], [0.012, -0.009], [-0.012, -0.009]];
  const found = new Map();
  for (const [dx, dy] of offsets) {
    await page.evaluate(([x, y]) => window.__map.jumpTo({ center: [x, y], zoom: 14.2, pitch: 0, bearing: 0 }), [lng + dx, lat + dy]);
    await page.waitForFunction(() => window.__map.loaded() && window.__map.areTilesLoaded(), undefined, { timeout: 45000 }).catch(() => {});
    await page.waitForTimeout(900);
    const rows = await page.evaluate(([layers, lng0, lat0, radius]) => {
      const out = [];
      for (const layer of layers) {
        let feats = [];
        try { feats = window.__map.querySourceFeatures('openmaptiles', { sourceLayer: layer }); } catch (e) { continue; }
        for (const f of feats) {
          const name = f.properties.name || f.properties['name:en'];
          if (!name) continue;
          const g = f.geometry;
          const c = g.type === 'Point' ? g.coordinates : g.type === 'LineString' ? g.coordinates[Math.floor(g.coordinates.length / 2)]
            : g.type === 'MultiLineString' ? g.coordinates[0][0] : g.type === 'Polygon' ? g.coordinates[0][0] : null;
          if (!c) continue;
          const dxk = (c[0] - lng0) * 111.32 * Math.cos(lat0 * Math.PI / 180), dyk = (c[1] - lat0) * 110.54;
          if (Math.hypot(dxk, dyk) > radius) continue;
          out.push([name, layer, f.properties.class || '', f.properties.subclass || '', +c[0].toFixed(5), +c[1].toFixed(5)]);
        }
      }
      return out;
    }, [LAYERS, lng, lat, radiusKm]);
    for (const r of rows) found.set(r.join('|'), r);
  }
  const rows = [...found.values()].filter(r => !re || re.test(r[0])).sort((a, b) => a[0].localeCompare(b[0]));
  for (const r of rows) console.log(r.join(' | '));
  console.log(`-- ${rows.length} named features`);
  await browser.close();
})();
