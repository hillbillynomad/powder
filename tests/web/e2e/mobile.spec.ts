/**
 * E2E tests for mobile responsiveness (iPhone 13)
 */
import { test, expect, devices } from '@playwright/test';

test.use({ ...devices['iPhone 13'] });

test.describe('Mobile Layout', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('#map');
  });

  test('page loads on mobile', async ({ page }) => {
    await expect(page).toHaveTitle(/Powder/);
  });

  test('menu toggle is visible on mobile', async ({ page }) => {
    const menuToggle = page.locator('#menu-toggle');
    await expect(menuToggle).toBeVisible();
  });

  test('filter drawer opens on mobile', async ({ page }) => {
    const menuToggle = page.locator('#menu-toggle');
    const filterDrawer = page.locator('#filter-drawer');

    await menuToggle.click();
    await expect(filterDrawer).toHaveClass(/visible/);
  });

  test('map is visible on mobile', async ({ page }) => {
    // On mobile, the map container should be visible
    const map = page.locator('#map');
    await expect(map).toBeVisible();

    const box = await map.boundingBox();
    // Map should have some reasonable size
    expect(box?.width).toBeGreaterThan(100);
    expect(box?.height).toBeGreaterThan(100);
  });
});

test.describe('Mobile Interactions', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    try {
      await page.waitForSelector('.leaflet-interactive', { timeout: 5000 });
    } catch {
      test.skip(true, 'No forecast data available');
    }
  });

  test('tapping marker opens detail (no hover on mobile)', async ({ page }) => {
    // On mobile, tap should go straight to detail (no hover popup)
    // Use dispatchEvent for cross-browser compatibility with Leaflet markers
    const marker = page.locator('.leaflet-interactive').first();
    await marker.dispatchEvent('click');

    // Detail content should be visible
    const detailContent = page.locator('#detail-content');
    await expect(detailContent).toBeVisible({ timeout: 5000 });
  });
});
