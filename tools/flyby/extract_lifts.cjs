// Pull aerialway lines + named peaks around a resort from the app's own vector tiles.
// usage: node extract.cjs <playwright path> <url> <lng> <lat> <out.json>
const fs = require('fs');
const { chromium } = require(process.argv[2]);
const [url, lng, lat, out] = [process.argv[3], Number(process.argv[4]), Number(process.argv[5]), process.argv[6]];

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  await page.goto(url);
  await page.waitForFunction(() => window.__powder && window.__powder.markerCount() > 0, undefined, { timeout: 60000 });
  await page.evaluate(([lng, lat]) => window.__map.jumpTo({ center: [lng, lat], zoom: 13.2, pitch: 0, bearing: 0 }), [lng, lat]);
  await page.waitForFunction(() => window.__map.loaded() && window.__map.areTilesLoaded(), undefined, { timeout: 60000 });
  await page.waitForTimeout(3000);
  const data = await page.evaluate(() => {
    const m = window.__map;
    const lifts = {};
    for (const f of m.querySourceFeatures('openmaptiles', { sourceLayer: 'transportation', filter: ['==', ['get', 'class'], 'aerialway'] })) {
      const key = f.id || JSON.stringify(f.geometry.coordinates[0]);
      const coords = f.geometry.type === 'LineString' ? [f.geometry.coordinates] : f.geometry.coordinates;
      (lifts[key] = lifts[key] || { id: f.id, props: f.properties, parts: [] }).parts.push(...coords);
    }
    const names = m.querySourceFeatures('openmaptiles', { sourceLayer: 'transportation_name', filter: ['==', ['get', 'class'], 'aerialway'] })
      .map(f => ({ name: f.properties.name, subclass: f.properties.subclass, coords: f.geometry.type === 'LineString' ? f.geometry.coordinates : f.geometry.coordinates.flat() }));
    const peaks = m.querySourceFeatures('openmaptiles', { sourceLayer: 'mountain_peak' })
      .map(f => ({ name: f.properties.name, ele: f.properties.ele, coord: f.geometry.coordinates }));
    return { lifts: Object.values(lifts), names, peaks };
  });
  fs.writeFileSync(out, JSON.stringify(data, null, 1));
  console.log('lifts', data.lifts.length, 'named pieces', data.names.length, 'peaks', data.peaks.length);
  await browser.close();
})();
