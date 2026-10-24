/**
 * E2E tests for resort flyover tours (powder/web/js/flyby.js + tours/*.json)
 */
import { test, expect } from '@playwright/test';
import { waitForMarkers } from './helpers';

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
    expect(await page.evaluate(() => window.__powder.flybyTime())).toBeLessThan(2);

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
