// Render stills along a resort's tour in the real app (satellite, 3D, lift names), for review.
// usage: node tools/flyby/review.cjs <playwright path> <url> <resort name> <out dir> [frames=8] [span seconds=whole loop]
// Poses come from the tour's own birdPose()/poseAt(), so the stills match the live flight.
const fs = require('fs');
const path = require('path');
const { chromium } = require(process.argv[2]);
const [url, resort, outDir] = [process.argv[3], process.argv[4], process.argv[5]];
const frames = Number(process.argv[6] || 8);
const span = Number(process.argv[7] || 0);
const start = Number(process.argv[8] || 0); // first sample time (seconds)
const viewport = process.env.VIEW ? { width: Number(process.env.VIEW.split('x')[0]), height: Number(process.env.VIEW.split('x')[1]) } : { width: 1280, height: 800 };
const settleMs = Number(process.env.SETTLE || 1200); // sample only the first `span` seconds (e.g. the intro)

(async () => {
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport });
  page.on('pageerror', e => console.log('pageerror', e.message));
  await page.goto(url);
  await page.waitForFunction(() => window.__powder && window.__powder.markerCount() > 0, undefined, { timeout: 90000 });
  await page.fill('#search-input', resort);
  await page.press('#search-input', 'Enter');
  await page.waitForFunction(() => window.__powder.flyby() && window.__powder.flyby().hasTour, undefined, { timeout: 30000 });
  await page.waitForTimeout(1500);
  await page.click('#flyby-toggle').catch(() => {}); // pause: we position the camera ourselves
  await page.evaluate(() => window.__map.stop());
  const slug = await page.evaluate((n) => window.PowderFlyby.slugify(n), resort);
  const info = await page.evaluate(async (slug) => {
    const tour = await (await fetch(`tours/${slug}.json`)).json();
    window.__tour = tour;
    return { seconds: window.PowderFlyby.tourDuration(tour) };
  }, slug);
  console.log(`${resort}: ${info.seconds.toFixed(1)} s loop`);
  for (let i = 0; i < frames; i++) {
    const s = start + ((span || info.seconds) * i) / frames;
    await page.evaluate((s) => {
      const t = window.__tour, F = window.PowderFlyby, m = window.__map, L = window.maplibregl, ex = 1.4;
      const b = F.birdPose(t, s);
      const cam = [b.camera[0], b.camera[1], b.camera[2] * ex];
      const drop = b.ground === undefined ? null : cam[2] - b.ground * ex;
      const dist = drop === null ? 1500 : Math.max(300, drop / Math.cos(b.pitch * Math.PI / 180));
      let aim = F.lookPoint(cam, b.bearing, b.pitch, dist);
      let roll = b.roll;
      if (t.points.some(p => p.orbit)) { // mixed tour: blend the aim toward the orbit target like the app
        const w = F.orbitWeight(t, s), tg = F.poseAt(t, s).target;
        aim = aim.map((v, k) => v + ((k === 2 ? tg[2] * ex : tg[k]) - v) * w);
        roll *= 1 - w;
      }
      const o = m.calculateCameraOptionsFromTo(new L.LngLat(cam[0], cam[1]), cam[2], new L.LngLat(aim[0], aim[1]), aim[2]);
      m.setCenterClampedToGround(false);
      m.jumpTo({ ...o, roll });
    }, s);
    await page.waitForFunction(() => window.__map.loaded() && window.__map.areTilesLoaded(), undefined, { timeout: 40000 }).catch(() => {});
    await page.waitForTimeout(settleMs);
    await page.screenshot({ path: path.join(outDir, `t${String(Math.round(s)).padStart(3, '0')}.png`) });
  }
  await browser.close();
})();
