// Blink (cut) detector for flyover transitions.
//
// Every camera-changing map call (jumpTo, setTerrain, ...) is wrapped; the camera is measured just
// before and just after that one call, so a "cut" is a call whose own effect is large: an instant
// re-orientation or re-position. This does not depend on render timing, which in a headless browser
// is bursty. Smooth motion (a flyTo curve, the per-frame glide and loop steps) never produces a cut.
//
// usage: node tools/flyby/blink.cjs <playwright path> <url> <from: resort name | globe> <to: resort name>
//          [seconds after the search=22] [seconds to fly "from" first=8]
// env:   VIEW=800x500
//        PAUSE=1      pause the first tour (leaves the wings levelling) before switching
//        FORCEROLL=1  report a banked camera when the first tour is left (the case that used to teleport)
//        BACK=<s>     leave the first resort with the back button and wait <s> seconds before picking the next
//        CLICK=1      switch by clicking the destination's marker on the map instead of searching
//        TIMELINE=<s> print every call and frame for the first <s> seconds
// exit status 1 when a cut is found.
const fs = require('fs');
const path = require('path');
const { chromium } = require(process.argv[2]);
const [url, from, to] = [process.argv[3], process.argv[4], process.argv[5]];
const secs = Number(process.argv[6] || 22), warm = Number(process.argv[7] || 8);
const [vw, vh] = (process.env.VIEW || '800x500').split('x').map(Number);

(async () => {
  const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: vw, height: vh } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(url);
  await page.waitForFunction(() => window.__powder && window.__powder.markerCount() > 0, undefined, { timeout: 90000 });

  const data = JSON.parse(fs.readFileSync(path.join(__dirname, '../../powder/data/resorts.json'), 'utf8'));
  const dest = (data.resorts || data).find(x => x.name === to);
  const search = async (name) => {
    await page.fill('#search-input', name);
    await page.press('#search-input', 'Enter');
  };

  if (from !== 'globe') {
    await search(from);
    await page.waitForFunction(() => window.__powder.flyby() && window.__powder.flyby().playing, undefined, { timeout: 30000 });
    await page.waitForTimeout(warm * 1000);
    if (process.env.PAUSE) { await page.click('#flyby-toggle'); await page.waitForTimeout(300); }
    if (process.env.BACK) { await page.click('#detail-back'); await page.waitForTimeout(Number(process.env.BACK) * 1000); } // leave the resort with the back button, then pick another
  }

  if (process.env.CLICK && dest) {
    // what a user does: scroll the map out until the destination's marker is in view (pauses the flight)
    await page.mouse.move(vw / 2, vh / 2);
    for (let i = 0; i < Number(process.env.WHEELS || 25); i++) { await page.mouse.wheel(0, 400); await page.waitForTimeout(40); }
    await page.waitForTimeout(1500);
    // and levels the view so places off in the distance are on screen
    await page.evaluate(() => window.__map.easeTo({ pitch: 0, bearing: 0, roll: 0, duration: 300 }));
    await page.waitForTimeout(900);
  }

  await page.evaluate((forceRoll) => {
    const m = window.__map;
    window.__log = [];
    const t0 = performance.now();
    const snap = () => {
      const tr = m.transform, ll = tr.getCameraLngLat();
      const z = m.getZoom(), p = m.getPitch(), el = m.getCameraTargetElevation(), c = m.getCenter();
      // the camera's own height above sea level: view-centre height plus the drop from camera to centre
      const mpp = 40075016.686 * Math.cos(c.lat * Math.PI / 180) / (512 * Math.pow(2, z));
      const alt = el + tr.cameraToCenterDistance * mpp * Math.cos(p * Math.PI / 180);
      return { lng: ll.lng, lat: ll.lat, z, p, b: m.getBearing(), roll: m.getRoll ? m.getRoll() : 0, el, alt, terr: !!m.getTerrain(), cx: c.lng, cy: c.lat };
    };
    const where = () => String(new Error().stack).split('\n').slice(3, 5).map(s => s.trim().replace(/^at /, '').replace(/https?:\/\/[^/]+\//, '').replace(/ \(.*\)$/, '')).join(' < ');
    const cutting = ['jumpTo', 'setTerrain', 'setCenterClampedToGround', 'setPitch', 'setBearing', 'setZoom', 'setCenter', 'setRoll', 'setStyle'];
    for (const fn of cutting) {
      if (!m[fn]) continue;
      const orig = m[fn].bind(m);
      m[fn] = (...a) => {
        const before = snap();
        const r = orig(...a);
        const after = snap();
        window.__log.push({ k: 'cut', t: performance.now() - t0, what: fn, before, after, who: where() });
        return r;
      };
    }
    for (const fn of ['flyTo', 'easeTo']) {
      const orig = m[fn].bind(m);
      m[fn] = (...a) => { window.__log.push({ k: 'call', t: performance.now() - t0, what: fn, who: where() }); return orig(...a); };
    }
    if (forceRoll) { const real = m.getRoll.bind(m); m.getRoll = () => real() || 8; }
    m.on('render', () => window.__log.push({ k: 'frame', t: performance.now() - t0, s: snap() }));
  }, !!process.env.FORCEROLL);

  if (process.env.STRAY) {
    // Wander off the flyover with real gestures (each one pauses it), then press play to resume.
    // STRAY=still | pan | zoom | rotate | far (comma-separated to chain them)
    const cx = vw / 2, cy = vh / 2;
    for (const kind of process.env.STRAY.split(',')) {
      if (kind === 'still') { await page.click('#flyby-toggle'); }
      if (kind === 'pan') { await page.mouse.move(cx, cy); await page.mouse.down(); for (let i = 1; i <= 10; i++) { await page.mouse.move(cx - 25 * i, cy - 8 * i); await page.waitForTimeout(30); } await page.mouse.up(); }
      if (kind === 'zoom') { await page.mouse.move(cx, cy); for (let i = 0; i < 6; i++) { await page.mouse.wheel(0, 300); await page.waitForTimeout(60); } }
      if (kind === 'far') { await page.mouse.move(cx, cy); for (let i = 0; i < 25; i++) { await page.mouse.wheel(0, 400); await page.waitForTimeout(40); } }
      if (kind === 'rotate') { await page.mouse.move(cx, cy); await page.mouse.down({ button: 'right' }); for (let i = 1; i <= 10; i++) { await page.mouse.move(cx + 20 * i, cy - 5 * i); await page.waitForTimeout(30); } await page.mouse.up({ button: 'right' }); }
      await page.waitForTimeout(1200);
    }
    const st = await page.evaluate(() => window.__powder.flyby());
    if (st && st.playing) console.log('warning: the gestures did not pause the flyover');
    await page.evaluate(() => window.__log.push({ k: 'mark', t: 0, what: 'resume' }));
    await page.click('#flyby-toggle'); // resume
  } else if (process.env.CLICK && dest) {
    // find the destination on the zoomed-out map; pan there with a drag if it is off screen
    let pt = await page.evaluate((d) => { const p = window.__map.project([d.longitude, d.latitude]); const r = document.getElementById('map').getBoundingClientRect(); return { x: r.left + p.x, y: r.top + p.y, inside: p.x > 0 && p.y > 0 && p.x < r.width && p.y < r.height }; }, dest);
    if (!pt.inside) { console.log('destination marker is not on screen after zooming out; using the map centre'); }
    if (process.env.DEBUG) console.log('click at', JSON.stringify(pt), JSON.stringify(await page.evaluate(() => ({ z: window.__map.getZoom(), pitch: window.__map.getPitch(), fly: window.__powder.flyby() }))));
    await page.mouse.click(pt.x, pt.y);
    if (process.env.DEBUG) { await page.waitForTimeout(1500); console.log('after click', JSON.stringify(await page.evaluate(() => ({ fly: window.__powder.flyby(), detail: (document.querySelector('#detail-content h2, #detail-content .detail-name') || {}).textContent })))); }
  } else {
    await search(to);
  }
  await page.waitForTimeout(secs * 1000);
  const log = await page.evaluate(() => window.__log);
  await browser.close();

  const dist = (a, b) => Math.hypot((b.lng - a.lng) * 111320 * Math.cos(a.lat * Math.PI / 180), (b.lat - a.lat) * 110540);
  const cuts = [];
  for (const e of log.filter(x => x.k === 'cut')) {
    const a = e.before, b = e.after;
    const viewW = 40075016 * Math.cos(a.lat * Math.PI / 180) / (512 * Math.pow(2, Math.max(0, Math.min(a.z, b.z)))) * vw;
    const move = dist(a, b) / viewW;
    const dB = Math.abs(((b.b - a.b + 540) % 360) - 180), dP = Math.abs(b.p - a.p), dR = Math.abs(b.roll - a.roll), dZ = Math.abs(b.z - a.z);
    const dEl = Math.abs(b.el - a.el), toggled = a.terr !== b.terr;
    const reasons = [];
    // the per-frame glide and loop steps are legitimately bigger when frames are slow (headless runs
    // at ~5 fps; a user's 60 fps steps are 12x smaller), so they get a wider allowance
    const paced = /^(step|tick)/.test(e.who);
    const k = paced ? 2.5 : 1;
    if (move > 1.5 * k) reasons.push(`camera moved ${move > 100 ? '>100' : move.toFixed(1)} screens`);
    if (dB > 20 * k) reasons.push(`bearing ${dB.toFixed(0)} deg`);
    if (dP > 12 * k) reasons.push(`pitch ${dP.toFixed(0)} deg`);
    if (dR > 10 * k) reasons.push(`roll ${dR.toFixed(0)} deg`);
    if (dZ > 0.8 * k) reasons.push(`zoom ${dZ.toFixed(2)}`);
    // a one-call change in the camera's own height: a lurch toward or away from the ground
    const dAlt = Math.abs(b.alt - a.alt) / Math.max(1, Math.min(a.alt, b.alt));
    if (dAlt > (paced ? 0.2 : 0.15)) reasons.push(`camera height ${a.alt.toFixed(0)} -> ${b.alt.toFixed(0)} m (${(dAlt * 100).toFixed(0)}%)`);
    if (!paced && dEl > 0.25 * viewW) reasons.push(`${toggled ? `3D terrain turned ${b.terr ? 'on' : 'off'}: ` : ''}camera height ${a.el.toFixed(0)} -> ${b.el.toFixed(0)} m`);
    if (reasons.length) cuts.push({ e, reasons });
  }
  const t1 = log.filter(x => x.k === 'frame');
  console.log(`${from} -> ${to}${process.env.FORCEROLL ? ' (banked)' : ''}${process.env.PAUSE ? ' (paused first)' : ''}${process.env.CLICK ? ' (marker click)' : ''}${process.env.STRAY ? ` (stray: ${process.env.STRAY}, then resume)` : ''}: ${t1.length} frames, ${log.filter(x => x.k === 'cut').length} camera calls checked, page errors ${errors.length}, CUTS: ${cuts.length}`);
  for (const c of cuts) console.log(`  CUT at ${(c.e.t / 1000).toFixed(2)} s  ${c.e.what}  <- ${c.e.who}\n      ${c.reasons.join('; ')}`);

  if (process.env.STEPS) {
    // magnitude of every jumpTo, to read the landing (end of glide, start of loop) step by step
    const jumps = log.filter(x => x.k === 'cut' && x.what === 'jumpTo');
    const lo = Number(process.env.STEPS.split(',')[0]) * 1000, hi = Number(process.env.STEPS.split(',')[1]) * 1000;
    for (const e of jumps.filter(x => x.t >= lo && x.t <= hi)) {
      const a = e.before, b = e.after;
      const viewW = 40075016 * Math.cos(a.lat * Math.PI / 180) / (512 * Math.pow(2, Math.max(0, Math.min(a.z, b.z)))) * vw;
      console.log(`${(e.t / 1000).toFixed(2).padStart(6)} s  jumpTo <- ${e.who.split(' < ')[0].padEnd(8)} move ${(dist(a, b) / viewW).toFixed(3)} screens  bearing ${(((b.b - a.b + 540) % 360) - 180).toFixed(1).padStart(6)}  pitch ${(b.p - a.p).toFixed(1).padStart(5)}  roll ${(b.roll - a.roll).toFixed(1).padStart(5)}  zoom ${(b.z - a.z).toFixed(3).padStart(6)}  height ${(b.el - a.el).toFixed(0).padStart(5)} m  cam ${(100 * (b.alt - a.alt) / Math.max(1, a.alt)).toFixed(1).padStart(6)}%   now z${b.z.toFixed(2)} p${b.p.toFixed(0)} b${b.b.toFixed(0)} el${b.el.toFixed(0)}`);
    }
  }
  if (process.env.TIMELINE) {
    const until = Number(process.env.TIMELINE) * 1000;
    for (const e of log.filter(x => x.t <= until)) {
      if (e.k === 'frame') console.log(`${(e.t / 1000).toFixed(2).padStart(6)} s  frame z${e.s.z.toFixed(2)} p${e.s.p.toFixed(0)} b${e.s.b.toFixed(0)} roll${e.s.roll.toFixed(0)} el${Math.round(e.s.el)} terr${e.s.terr ? 1 : 0} c[${e.s.cx.toFixed(2)},${e.s.cy.toFixed(2)}]`);
      else if (e.k === 'call') console.log(`${(e.t / 1000).toFixed(2).padStart(6)} s  ${e.what.toUpperCase()}  <- ${e.who}`);
      else if (e.what !== 'jumpTo' || cuts.some(c => c.e === e)) console.log(`${(e.t / 1000).toFixed(2).padStart(6)} s  ${e.what}  <- ${e.who}`);
    }
  }
  process.exit(cuts.length ? 1 : 0);
})();
