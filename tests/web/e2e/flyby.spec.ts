/**
 * E2E tests for resort flyover tours (powder/web/js/flyby.js + tours/*.json)
 */
import { test, expect, type Page } from '@playwright/test';
import { waitForMarkers } from './helpers';

// Measure the camera before and after every call that can move it. A "cut" is one call that
// changes the view by a lot at once: an instant re-orientation, re-position or lurch in height.
// (The loop's and the glide's per-frame steps are small; the approach is a flyTo, whose animation
// is not an instant call.) Results collect in window.__cuts; window.__terrainOff counts 3D relief
// being switched off.
async function watchCameraCuts(page: Page, { forceRoll = false } = {}) {
  await page.evaluate((forceRoll) => {
    const m = (window as any).__map;
    const w: any = window;
    w.__cuts = [];
    w.__terrainOff = 0;
    const snap = () => {
      const ll = m.transform.getCameraLngLat(), c = m.getCenter(), z = m.getZoom(), p = m.getPitch();
      // the camera's own height above sea level: view-centre height plus the drop from camera to centre
      const mpp = 40075016.686 * Math.cos(c.lat * Math.PI / 180) / (512 * Math.pow(2, z));
      const alt = m.getCameraTargetElevation() + m.transform.cameraToCenterDistance * mpp * Math.cos(p * Math.PI / 180);
      return { lng: ll.lng, lat: ll.lat, z, p, b: m.getBearing(), alt };
    };
    for (const fn of ['jumpTo', 'setTerrain']) {
      const orig = m[fn].bind(m);
      m[fn] = (...a: any[]) => {
        const before = snap();
        const r = orig(...a);
        const after = snap();
        if (fn === 'setTerrain' && !a[0]) w.__terrainOff++;
        const dB = Math.abs(((after.b - before.b + 540) % 360) - 180);
        const dist = Math.hypot((after.lng - before.lng) * 111320 * Math.cos(before.lat * Math.PI / 180), (after.lat - before.lat) * 110540);
        const view = 40075016 * Math.cos(before.lat * Math.PI / 180) / (512 * Math.pow(2, Math.max(0, Math.min(before.z, after.z)))) * 800;
        const dAlt = Math.abs(after.alt - before.alt) / Math.max(1, Math.min(before.alt, after.alt));
        // far beyond any frame-to-frame step, even at software-rendering frame rates
        if (dB > 60 || Math.abs(after.p - before.p) > 40 || Math.abs(after.z - before.z) > 3 || dist > 5 * view || dAlt > 0.2) {
          w.__cuts.push({ fn, dB: Math.round(dB), dp: Math.round(after.p - before.p), dz: +(after.z - before.z).toFixed(2), screens: Math.round(dist / view), height: `${Math.round(before.alt)} -> ${Math.round(after.alt)} m` });
        }
        return r;
      };
    }
    if (forceRoll) { // report a banked camera
      const roll = m.getRoll.bind(m);
      m.getRoll = () => roll() || 8;
    }
  }, forceRoll);
}

test.describe('Resort flyover', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await waitForMarkers(page);
  });

  test('selecting a resort with a tour flies it in satellite + 3D with lift names', async ({ page }) => {
    await page.locator('#search-input').fill('snowbird');
    await page.locator('#search-input').press('Enter');

    await page.waitForFunction(() => window.__powder.flyby()?.playing, undefined, { timeout: 20000 });
    const toggle = page.locator('#flyby-toggle');
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAttribute('aria-label', 'Pause flyover');
    expect(await page.evaluate(() => window.__powder.layerVisibility('base-sat'))).toBe('visible');
    expect(await page.evaluate(() => window.__powder.layerVisibility('trails-lift-labels'))).toBe('visible');
    await page.waitForFunction(() => window.__powder.hasTerrain(), undefined, { timeout: 20000 });

    // The user's own layer choices are not overwritten by the tour
    const saved = await page.evaluate(() => localStorage.getItem('powder.layerPrefs'));
    expect(saved === null || !JSON.parse(saved).threeD).toBe(true);

    // Pause / resume from the button
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-label', 'Fly over');
    expect(await page.evaluate(() => window.__powder.flyby()!.playing)).toBe(false);
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-label', 'Pause flyover');

    // Leaving the resort stops the tour, hides the button and restores the 2D map
    await page.locator('#detail-back').click();
    await expect(toggle).toBeHidden();
    expect(await page.evaluate(() => window.__powder.flyby()!.hasTour)).toBe(false);
    await page.waitForFunction(() => !window.__powder.hasTerrain(), undefined, { timeout: 10000 });
  });

  test('the timeline shows progress and lets you jump around the flight', async ({ page }) => {
    await page.locator('#search-input').fill('snowbird');
    await page.locator('#search-input').press('Enter');
    await page.waitForFunction(() => window.__powder.flyby()?.playing, undefined, { timeout: 20000 });
    await expect(page.locator('#flyby-bar')).toBeVisible();
    await expect(page.locator('#flyby-time')).toHaveText(/^\d+:\d\d \/ \d+:\d\d$/);

    // Jump to the end, then back to the start, with the buttons
    await page.locator('#flyby-end').click();
    const nearEnd = await page.evaluate(() => ({ t: window.__powder.flybyTime(), d: window.__powder.flybyDuration() }));
    expect(nearEnd.t).toBeGreaterThan(nearEnd.d - 10);
    await page.locator('#flyby-restart').click();
    expect(await page.evaluate(() => window.__powder.flybyTime())).toBeLessThan(8);

    // Dragging the scrubber moves the flight there
    const target = await page.evaluate(() => Math.round(window.__powder.flybyDuration() * 10 * 0.5));
    await page.locator('#flyby-slider').fill(String(target));
    const t = await page.evaluate(() => window.__powder.flybyTime());
    expect(t).toBeGreaterThan(target / 10 - 1);
    expect(t).toBeLessThan(target / 10 + 3);
  });

  test('touching the map hands control back to the user', async ({ page }) => {
    await page.locator('#search-input').fill('snowbird');
    await page.locator('#search-input').press('Enter');
    await page.waitForFunction(() => window.__powder.flyby()?.playing, undefined, { timeout: 20000 });

    // A press on the map surface (no click: that could land on the resort bubble and close it;
    // no wheel: mobile WebKit has none)
    await page.locator('#map .maplibregl-canvas-container').dispatchEvent('pointerdown');
    await expect(page.locator('#flyby-toggle')).toHaveAttribute('aria-label', 'Fly over');
  });

  test('clicking or zooming the map pauses the flyover but keeps the timeline to resume from', async ({ page }) => {
    await page.locator('#search-input').fill('snowbird');
    await page.locator('#search-input').press('Enter');
    await page.waitForFunction(() => window.__powder.flyby()?.playing, undefined, { timeout: 20000 });
    await page.locator('#flyby-slider').fill(String(Math.round((await page.evaluate(() => window.__powder.flybyDuration())) * 4)));

    const box = (await page.locator('#map .maplibregl-canvas-container').boundingBox())!;
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 3);
    await page.mouse.dblclick(box.x + box.width / 2, box.y + box.height / 2);

    // Paused, but the bar, the resort and the position are all still there
    await expect(page.locator('#flyby-toggle')).toHaveAttribute('aria-label', 'Fly over');
    await expect(page.locator('#flyby-bar')).toBeVisible();
    await expect(page.locator('#detail-content')).toContainText('Snowbird');
    expect(await page.evaluate(() => window.__powder.flyby()!.hasTour)).toBe(true);
    const pausedAt = await page.evaluate(() => window.__powder.flybyTime());
    expect(pausedAt).toBeGreaterThan(10);

    // Resume carries on from the same place
    await page.locator('#flyby-toggle').click();
    await expect(page.locator('#flyby-toggle')).toHaveAttribute('aria-label', 'Pause flyover');
    await page.waitForTimeout(1500);
    expect(await page.evaluate(() => window.__powder.flybyTime())).toBeGreaterThan(pausedAt - 1);
  });

  test('flying from one flyover into another never cuts or teleports the camera', async ({ page }) => {
    await page.locator('#search-input').fill('snowbird');
    await page.locator('#search-input').press('Enter');
    await page.waitForFunction(() => window.__powder.flyby()?.playing, undefined, { timeout: 20000 });
    await page.waitForTimeout(1500);

    // Leaving a flyover while the camera is banked is what used to start the approach early
    await watchCameraCuts(page, { forceRoll: true });

    await page.locator('#search-input').fill('park city mountain');
    await page.locator('#search-input').press('Enter');
    await page.waitForFunction(() => window.__powder.flyby()?.resort === 'Park City Mountain', undefined, { timeout: 20000 });
    await page.waitForTimeout(9000);

    expect(await page.evaluate(() => (window as any).__cuts)).toEqual([]);
    // the flyover layers stayed on: 3D relief was never dropped and re-added in between
    expect(await page.evaluate(() => (window as any).__terrainOff)).toBe(0);
    expect(await page.evaluate(() => window.__powder.flyby()!.playing)).toBe(true);
  });

  test('wandering off a flyover and resuming it glides back without a cut', async ({ page }) => {
    // Aconcagua's ground is 5 km up: resuming used to drop the camera by that height in one frame
    await page.locator('#search-input').fill('aconcagua');
    await page.locator('#search-input').press('Enter');
    await page.waitForFunction(() => window.__powder.flyby()?.playing, undefined, { timeout: 20000 });
    await page.waitForTimeout(9000); // fly-in done, the loop is running

    // Drag the map a little to look around (the gesture pauses the flyover)
    const box = (await page.locator('#map .maplibregl-canvas-container').boundingBox())!;
    const [x, y] = [box.x + box.width / 2, box.y + box.height / 2];
    await page.mouse.move(x, y);
    await page.mouse.down();
    for (let i = 1; i <= 10; i++) await page.mouse.move(x - 25 * i, y - 8 * i);
    await page.mouse.up();
    await expect(page.locator('#flyby-toggle')).toHaveAttribute('aria-label', 'Fly over');
    await page.waitForTimeout(1000);

    await watchCameraCuts(page);
    await page.locator('#flyby-toggle').click();
    await page.waitForTimeout(8000);

    expect(await page.evaluate(() => (window as any).__cuts)).toEqual([]);
    expect(await page.evaluate(() => window.__powder.flyby()!.playing)).toBe(true);
  });

  test('resorts without a tour fly in as before, with no flyover button', async ({ page }) => {
    // Mont Tremblant's marker sits in a flat town with no lifts in the map data: no tour
    await page.locator('#search-input').fill('mont tremblant');
    await page.locator('#search-input').press('Enter');
    await expect(page.locator('#detail-content')).toContainText(/Tremblant/i);
    await page.waitForTimeout(1000);
    await expect(page.locator('#flyby-toggle')).toBeHidden();
  });

  test('sharing during a flyover copies a link that gives a friend the flyover', async ({ page, context, browserName }) => {
    if (browserName === 'chromium') await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    await page.locator('#search-input').fill('snowbird');
    await page.locator('#search-input').press('Enter');
    await page.waitForFunction(() => window.__powder.flyby()?.playing, undefined, { timeout: 20000 });

    await page.locator('#share-button').click();
    await expect(page.locator('#toast')).toHaveText('Flyover link copied: Snowbird');

    // Clipboard reads aren't available in every browser; build the same link if not
    const copied = await page.evaluate(() => navigator.clipboard.readText()).catch(() => null);
    const link = copied || '/?resort=Snowbird&fly=1';
    if (copied) {
      const q = new URL(copied).searchParams;
      expect(q.get('resort')).toBe('Snowbird');
      expect(q.get('fly')).toBe('1');
      expect(q.has('lat')).toBe(false);
      expect(q.get('3d')).toBe('0'); // the sharer's own settings, not the flyover's forced ones
    }

    // A friend opening it lands straight in the flyover
    const friend = await context.newPage();
    await friend.goto(link);
    await friend.waitForFunction(() => window.__powder?.flyby()?.playing, undefined, { timeout: 30000 });
    await expect(friend.locator('#detail-content')).toContainText('Snowbird');
    await expect(friend.locator('#flyby-toggle')).toHaveAttribute('aria-label', 'Pause flyover');
  });
});
