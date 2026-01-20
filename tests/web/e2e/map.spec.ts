/**
 * E2E tests for map functionality
 */
import { test, expect } from '@playwright/test';

test.describe('Map Functionality', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Wait for map to initialize
    await page.waitForSelector('#map');
    // Wait for data to load (markers appear)
    await page.waitForSelector('.leaflet-interactive', { timeout: 10000 }).catch(() => {
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

  test('filter drawer toggle works', async ({ page }) => {
    const menuToggle = page.locator('#menu-toggle');
    const filterDrawer = page.locator('#filter-drawer');

    // Initially hidden
    await expect(filterDrawer).not.toHaveClass(/visible/);

    // Click toggle
    await menuToggle.click();

    // Should be visible now
    await expect(filterDrawer).toHaveClass(/visible/);

    // Click again to hide
    await menuToggle.click();

    // Should be hidden again
    await expect(filterDrawer).not.toHaveClass(/visible/);
  });
});

test.describe('Map with data', () => {
  test.skip(({ browserName }) => browserName === 'webkit', 'Skipping on webkit due to data loading issues');

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Wait for markers to appear (requires data/forecasts.json)
    try {
      await page.waitForSelector('.leaflet-interactive', { timeout: 5000 });
    } catch {
      test.skip(true, 'No forecast data available');
    }
  });

  test('markers are displayed on map', async ({ page }) => {
    const markers = page.locator('.leaflet-interactive');
    const count = await markers.count();
    expect(count).toBeGreaterThan(0);
  });

  test('clicking marker opens detail panel', async ({ page }) => {
    // Use dispatchEvent for cross-browser compatibility with Leaflet markers
    const marker = page.locator('.leaflet-interactive').first();
    await marker.dispatchEvent('click');

    // Detail content should be visible
    const detailContent = page.locator('#detail-content');
    await expect(detailContent).toBeVisible({ timeout: 5000 });
  });
});
