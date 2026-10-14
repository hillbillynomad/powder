/**
 * E2E tests for filter functionality
 */
import { test, expect } from '@playwright/test';
import { waitForMarkers, markerCount, clickFirstMarker } from './helpers';

test.describe('Filter Controls', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('#map');

    // Open the menu
    await page.locator('#menu-toggle').click();
    await expect(page.locator('#menu-panel')).toHaveClass(/visible/);
  });

  test('snowfall filter is present', async ({ page }) => {
    const snowFilter = page.locator('#snow-filter');
    await expect(snowFilter).toBeVisible();
  });

  test('snowfall filter has correct options', async ({ page }) => {
    const snowFilter = page.locator('#snow-filter');
    const options = snowFilter.locator('option');

    // Should have 3 options: forecast, historical, total
    await expect(options).toHaveCount(3);
  });
});

test.describe('Filter Functionality with Data', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    try {
      await waitForMarkers(page, 5000);
    } catch {
      test.skip(true, 'No forecast data available');
    }

    // Open the menu
    await page.locator('#menu-toggle').click();
  });

  test('country, region and pass filters are gone', async ({ page }) => {
    for (const id of ['#country-filter', '#region-filter', '#pass-filter', '#filter-badge']) {
      await expect(page.locator(id)).toHaveCount(0);
    }
  });
});
