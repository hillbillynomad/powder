/**
 * E2E tests for mobile responsiveness (iPhone 13)
 */
import { test, expect, devices } from '@playwright/test';
import { waitForMarkers, clickFirstMarker } from './helpers';

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

  test('menu opens on mobile and fits inside the map', async ({ page }) => {
    await page.locator('#menu-toggle').click();
    const panel = page.locator('#menu-panel');
    await expect(panel).toHaveClass(/visible/);

    const box = (await panel.boundingBox())!;
    const map = (await page.locator('#map').boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(map.x);
    expect(box.x + box.width).toBeLessThanOrEqual(map.x + map.width + 1);
    expect(box.y + box.height).toBeLessThanOrEqual(map.y + map.height + 1);
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
      await waitForMarkers(page, 5000);
    } catch {
      test.skip(true, 'No forecast data available');
    }
  });

  test('tapping marker opens detail (no hover on mobile)', async ({ page }) => {
    await clickFirstMarker(page);

    // Detail content should be visible
    const detailContent = page.locator('#detail-content');
    await expect(detailContent).toBeVisible({ timeout: 5000 });
  });
});
