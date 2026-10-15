// Harvest lift lines, stations, lodges and peaks around every resort from the app's own
// OpenFreeMap vector tiles, so route generation needs no extra data source.
//
// usage (powder/web served on :8000):
//   node tools/flyby/harvest.cjs <playwright path> [http://localhost:8000/] [only-slug ...]
// Writes tools/flyby/cache/<slug>.json (skips resorts already cached; delete to refresh).
const fs = require('fs');
const path = require('path');
const { chromium } = require(process.argv[2]);
const url = process.argv[3] || 'http://localhost:8000/';
const only = new Set(process.argv.slice(4));

const ROOT = path.resolve(__dirname, '../..');
const OUT = path.join(__dirname, 'cache');
const RADIUS_KM = 5.5;

// Keep in step with slugify() in powder/web/js/flyby.js
const slugify = (name) => String(name || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
  .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const raw = JSON.parse(fs.readFileSync(path.join(ROOT, 'powder/data/resorts.json'), 'utf8'));
  const resorts = (raw.resorts || raw).filter(r => !only.size || only.has(slugify(r.name)));

  const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1200 } });
  await page.goto(url);
  await page.waitForFunction(() => window.__powder && window.__powder.markerCount() > 0, undefined, { timeout: 90000 });
  // Satellite mode draws no vector layers, so ask for the labelled map style's sources only
  // (querySourceFeatures reads the tiles regardless of layer visibility)
  let done = 0, skipped = 0, failed = [];
  for (const r of resorts) {
    const slug = slugify(r.name);
    const file = path.join(OUT, `${slug}.json`);
    if (fs.existsSync(file)) { skipped++; continue; }
    try {
      // Lifts and names at z13 over a wide view; lodges/restaurants only appear in z14 tiles
      const settle = async () => {
        await page.waitForFunction(() => window.__map.loaded() && window.__map.areTilesLoaded(), undefined, { timeout: 45000 }).catch(() => {});
        await page.waitForTimeout(1000);
      };
      const goto = (z) => page.evaluate(([lng, lat, z]) => window.__map.jumpTo({ center: [lng, lat], zoom: z, pitch: 0, bearing: 0 }), [r.longitude, r.latitude, z]);
      await goto(13.0);
      await settle();
      const data = await page.evaluate(([lng0, lat0, radiusKm]) => {
        const m = window.__map;
        const near = (c) => {
          const dx = (c[0] - lng0) * 111.32 * Math.cos(lat0 * Math.PI / 180);
          const dy = (c[1] - lat0) * 110.54;
          return Math.hypot(dx, dy) <= radiusKm;
        };
        const q = (layer, filter) => {
          try { return m.querySourceFeatures('openmaptiles', { sourceLayer: layer, filter }); } catch (e) { return []; }
        };
        const lines = new Map();
        for (const f of q('transportation', ['==', ['get', 'class'], 'aerialway'])) {
          const parts = f.geometry.type === 'LineString' ? [f.geometry.coordinates] : f.geometry.coordinates;
          for (const part of parts) {
            if (!part.some(near)) continue;
            const key = JSON.stringify(part[0].map(v => +v.toFixed(5)));
            lines.set(key, { subclass: f.properties.subclass || null, coords: part.map(c => [+c[0].toFixed(5), +c[1].toFixed(5)]) });
          }
        }
        const names = [];
        const seenName = new Set();
        for (const f of q('transportation_name', ['==', ['get', 'class'], 'aerialway'])) {
          const coords = f.geometry.type === 'LineString' ? f.geometry.coordinates : f.geometry.coordinates.flat();
          if (!f.properties.name || !coords.some(near)) continue;
          const key = f.properties.name + JSON.stringify(coords[0].map(v => +v.toFixed(4)));
          if (seenName.has(key)) continue;
          seenName.add(key);
          names.push({ name: f.properties.name, subclass: f.properties.subclass || null,
            coords: coords.map(c => [+c[0].toFixed(5), +c[1].toFixed(5)]) });
        }
        const peaks = new Map();
        for (const f of q('mountain_peak', null)) {
          const c = f.geometry.coordinates;
          if (!near(c) || !f.properties.name) continue;
          peaks.set(f.properties.name, { name: f.properties.name, ele: f.properties.ele || null, coord: [+c[0].toFixed(5), +c[1].toFixed(5)] });
        }
        return { lifts: [...lines.values()], liftNames: names, peaks: [...peaks.values()] };
      }, [r.longitude, r.latitude, RADIUS_KM]);
      await goto(14.2);
      await settle();
      data.pois = await page.evaluate(([lng0, lat0, radiusKm]) => {
        const out = new Map();
        for (const f of window.__map.querySourceFeatures('openmaptiles', { sourceLayer: 'poi' })) {
          const c = f.geometry.type === 'Point' ? f.geometry.coordinates : null;
          if (!c || !f.properties.name) continue;
          const dx = (c[0] - lng0) * 111.32 * Math.cos(lat0 * Math.PI / 180), dy = (c[1] - lat0) * 110.54;
          if (Math.hypot(dx, dy) > radiusKm) continue;
          out.set(f.properties.name, { name: f.properties.name, class: f.properties.class || null,
            subclass: f.properties.subclass || null, coord: [+c[0].toFixed(5), +c[1].toFixed(5)] });
        }
        return [...out.values()];
      }, [r.longitude, r.latitude, RADIUS_KM]);
      fs.writeFileSync(file, JSON.stringify({ resort: r.name, slug, latitude: r.latitude, longitude: r.longitude, ...data }));
      done++;
      console.log(`${done + skipped}/${resorts.length} ${slug}: ${data.lifts.length} lift lines, ${data.liftNames.length} named, ${data.pois.length} pois, ${data.peaks.length} peaks`);
    } catch (e) {
      failed.push(slug);
      console.log(`FAILED ${slug}: ${String(e.message).split('\n')[0]}`);
    }
  }
  console.log(JSON.stringify({ harvested: done, alreadyCached: skipped, failed }));
  await browser.close();
})();
