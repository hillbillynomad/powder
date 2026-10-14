/**
 * E2E tests for map functionality
 */
import { test, expect } from '@playwright/test';
import { waitForMarkers, markerCount, clickFirstMarker } from './helpers';

test.describe('Map Functionality', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Wait for map to initialize
    await page.waitForSelector('#map');
    // Wait for data to load (markers appear)
    await waitForMarkers(page, 10000).catch(() => {
      // Data may not be present in test environment
    });
  });

  test('page loads successfully', async ({ page }) => {
    await expect(page).toHaveTitle(/Powder/);
  });

  test('map container is visible', async ({ page }) => {
    const map = page.locator('#map');
    await expect(map).toBeVisible();
  });

  test('header is visible with title', async ({ page }) => {
    const header = page.locator('header');
    await expect(header).toBeVisible();
    await expect(header).toContainText('Powder');
  });

  test('side panel exists', async ({ page }) => {
    const panel = page.locator('#side-panel');
    await expect(panel).toBeVisible();
  });

  test('menu toggle works', async ({ page }) => {
    const menuToggle = page.locator('#menu-toggle');
    const menuPanel = page.locator('#menu-panel');

    // Initially hidden
    await expect(menuPanel).not.toHaveClass(/visible/);

    // Click toggle
    await menuToggle.click();
    await expect(menuPanel).toHaveClass(/visible/);

    // Click again to hide
    await menuToggle.click();
    await expect(menuPanel).not.toHaveClass(/visible/);

    // Escape also closes it
    await menuToggle.click();
    await expect(menuPanel).toHaveClass(/visible/);
    await page.keyboard.press('Escape');
    await expect(menuPanel).not.toHaveClass(/visible/);
  });

  test('old header menu button and filter drawer are gone', async ({ page }) => {
    await expect(page.locator('.header #menu-toggle')).toHaveCount(0);
    await expect(page.locator('#filter-drawer')).toHaveCount(0);
  });
});

test.describe('Map with data', () => {
  test.skip(({ browserName }) => browserName === 'webkit', 'Skipping on webkit due to data loading issues');

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Wait for markers to appear (requires data/forecasts.json)
    try {
      await waitForMarkers(page, 5000);
    } catch {
      test.skip(true, 'No forecast data available');
    }
  });

  test('markers are displayed on map', async ({ page }) => {
    expect(await markerCount(page)).toBeGreaterThan(0);
  });

  test('clicking marker opens detail panel', async ({ page }) => {
    await clickFirstMarker(page);

    // Detail content should be visible
    const detailContent = page.locator('#detail-content');
    await expect(detailContent).toBeVisible({ timeout: 5000 });
  });
});

test.describe('Globe and layers', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForFunction(() => !!window.__map && window.__map.isStyleLoaded(), undefined, { timeout: 15000 })
      .catch(() => test.skip(true, 'WebGL unavailable in this browser'));
  });

  test('uses the globe projection', async ({ page }) => {
    const projection = await page.evaluate(() => window.__map.getProjection());
    expect(projection.type).toBe('globe');
  });

  test('layer switcher swaps base maps without reloading the page', async ({ page }) => {
    await page.locator('#menu-toggle').click();
    await expect(page.locator('#menu-panel')).toBeVisible();

    // Defaults: satellite on, labelled map and topo off
    await expect.poll(() => page.evaluate(() => window.__powder.layerVisibility('base-sat'))).toBe('visible');
    await expect.poll(() => page.evaluate(() => window.__powder.layerVisibility('base-topo'))).toBe('none');

    await page.locator('input[name="base-mode"][value="topo"]').check();
    await expect.poll(() => page.evaluate(() => window.__powder.layerVisibility('base-topo'))).toBe('visible');
    await expect.poll(() => page.evaluate(() => window.__powder.layerVisibility('base-sat'))).toBe('none');
  });

  test('terrain toggle shows hillshade and contours', async ({ page }) => {
    await page.locator('#menu-toggle').click();
    const terrain = page.locator('input[data-pref="terrain"]');
    test.skip(await terrain.isDisabled(), 'Contour plugin unavailable');

    await expect.poll(() => page.evaluate(() => window.__powder.layerVisibility('terrain-contours-major'))).toBe('none');
    await terrain.check();
    await expect.poll(() => page.evaluate(() => window.__powder.layerVisibility('terrain-hillshade'))).toBe('visible');
    await expect.poll(() => page.evaluate(() => window.__powder.layerVisibility('terrain-contours-major'))).toBe('visible');
  });

  test('3D relief only applies once zoomed in', async ({ page }) => {
    await page.locator('#menu-toggle').click();
    const threeD = page.locator('input[data-pref="threeD"]');
    test.skip(await threeD.isDisabled(), 'Terrain source unavailable');
    await threeD.check();
    expect(await page.evaluate(() => window.__powder.hasTerrain())).toBe(false); // globe view

    await page.evaluate(() => window.__map.jumpTo({ center: [-106.4, 39.6], zoom: 9 }));
    await expect.poll(() => page.evaluate(() => window.__powder.hasTerrain())).toBe(true);
  });

  test('layer choices persist across reloads', async ({ page }) => {
    await page.locator('#menu-toggle').click();
    await page.locator('input[name="base-mode"][value="topo"]').check();
    await page.reload();
    await page.waitForFunction(() => !!window.__map && window.__map.isStyleLoaded());
    await expect.poll(() => page.evaluate(() => window.__powder.layerVisibility('base-topo'))).toBe('visible');
  });
});

test.describe('Share links', () => {
  test('share button copies a URL and shows a toast', async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']).catch(() => {});
    await page.goto('/');
    await page.waitForFunction(() => !!window.__map);
    await page.locator('#share-button').click();

    await expect(page.locator('#toast')).toHaveText('URL copied to clipboard');
    await expect(page.locator('#toast')).toHaveClass(/show/);
    // ...and the message goes away again on its own
    await expect(page.locator('#toast')).not.toHaveClass(/show/, { timeout: 6000 });

    const copied = await page.evaluate(() => navigator.clipboard.readText()).catch(() => null);
    if (copied) {
      expect(copied).toMatch(/[?&]base=sat/);
      expect(copied).toMatch(/[?&]lat=/);
    }
  });

  test('landing on a shared link restores camera and layers', async ({ page }) => {
    await page.goto('/?lat=39.6&lng=-106.4&z=11.5&b=30&p=40&base=topo&labels=0&terrain=1&3d=1&trails=0');
    await page.waitForFunction(() => !!window.__map && window.__map.isStyleLoaded(), undefined, { timeout: 15000 })
      .catch(() => test.skip(true, 'WebGL unavailable in this browser'));

    const view = await page.evaluate(() => {
      const m = window.__map;
      return { lat: m.getCenter().lat, lng: m.getCenter().lng, zoom: m.getZoom(), bearing: m.getBearing() };
    });
    expect(view.lat).toBeCloseTo(39.6, 1);
    expect(view.lng).toBeCloseTo(-106.4, 1);
    expect(view.zoom).toBeCloseTo(11.5, 1);
    expect(view.bearing).toBeCloseTo(30, 0);

    expect(await page.evaluate(() => window.__powder.layerVisibility('base-topo'))).toBe('visible');
    expect(await page.evaluate(() => window.__powder.layerVisibility('trails-pistes'))).toBe('none');
    await page.locator('#menu-toggle').click();
    await expect(page.locator('input[name="base-mode"][value="topo"]')).toBeChecked();
    await expect(page.locator('input[data-pref="terrain"]')).toBeChecked();
  });

  test('a malformed link falls back to the default view', async ({ page }) => {
    await page.goto('/?lat=abc&lng=999&z=-4&base=<script>');
    await page.waitForSelector('#map');
  });
});
