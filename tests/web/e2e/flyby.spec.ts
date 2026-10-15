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
    await expect(toggle).toContainText('Pause');
    expect(await page.evaluate(() => window.__powder.layerVisibility('base-sat'))).toBe('visible');
    expect(await page.evaluate(() => window.__powder.layerVisibility('trails-lift-labels'))).toBe('visible');
    await page.waitForFunction(() => window.__powder.hasTerrain(), undefined, { timeout: 20000 });

    // The user's own layer choices are not overwritten by the tour
    const saved = await page.evaluate(() => localStorage.getItem('powder.layerPrefs'));
    expect(saved === null || !JSON.parse(saved).threeD).toBe(true);

    // Pause / resume from the button
    await toggle.click();
    await expect(toggle).toContainText('Fly over');
    expect(await page.evaluate(() => window.__powder.flyby()!.playing)).toBe(false);
    await toggle.click();
    await expect(toggle).toContainText('Pause');

    // Leaving the resort stops the tour, hides the button and restores the 2D map
    await page.locator('#detail-back').click();
    await expect(toggle).toBeHidden();
    expect(await page.evaluate(() => window.__powder.flyby()!.hasTour)).toBe(false);
    await page.waitForFunction(() => !window.__powder.hasTerrain(), undefined, { timeout: 10000 });
  });

  test('touching the map hands control back to the user', async ({ page }) => {
    await page.locator('#search-input').fill('snowbird');
    await page.locator('#search-input').press('Enter');
    await page.waitForFunction(() => window.__powder.flyby()?.playing, undefined, { timeout: 20000 });

    // A press on the map surface (no click: that could land on the resort bubble and close it;
    // no wheel: mobile WebKit has none)
    await page.locator('#map .maplibregl-canvas-container').dispatchEvent('pointerdown');
    await expect(page.locator('#flyby-toggle')).toContainText('Fly over');
  });

  test('resorts without a tour fly in as before, with no flyover button', async ({ page }) => {
    await page.locator('#search-input').fill('chamonix');
    await page.locator('#search-input').press('Enter');
    await expect(page.locator('#detail-content')).toContainText(/Chamonix/i);
    await page.waitForTimeout(1000);
    await expect(page.locator('#flyby-toggle')).toBeHidden();
  });
});
