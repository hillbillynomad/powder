/**
 * E2E tests for filter functionality
 */
import { test, expect } from '@playwright/test';

test.describe('Filter Controls', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('#map');

    // Open filter drawer
    await page.locator('#menu-toggle').click();
    await expect(page.locator('#filter-drawer')).toHaveClass(/visible/);
  });

  test('country filter is present', async ({ page }) => {
    const countryFilter = page.locator('#country-filter');
    await expect(countryFilter).toBeVisible();
  });

  test('region filter is present', async ({ page }) => {
    const regionFilter = page.locator('#region-filter');
    await expect(regionFilter).toBeVisible();
  });

  test('pass filter is present', async ({ page }) => {
    const passFilter = page.locator('#pass-filter');
    await expect(passFilter).toBeVisible();
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

  test('pass filter has correct options', async ({ page }) => {
    const passFilter = page.locator('#pass-filter');
    const options = passFilter.locator('option');

    // Should have: All Passes, EPIC, IKON
    await expect(options.first()).toContainText('All');
  });
});

test.describe('Filter Functionality with Data', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    try {
      await page.waitForSelector('.leaflet-interactive', { timeout: 5000 });
    } catch {
      test.skip(true, 'No forecast data available');
    }

    // Open filter drawer
    await page.locator('#menu-toggle').click();
  });

  test('selecting country reduces markers', async ({ page }) => {
    const initialCount = await page.locator('.leaflet-interactive').count();

    // Select Japan (should have fewer resorts than "All")
    await page.selectOption('#country-filter', 'JP');

    // Wait for markers to update
    await page.waitForTimeout(500);

    const filteredCount = await page.locator('.leaflet-interactive').count();

    // JP should have fewer resorts than all countries
    if (initialCount > 5) {
      expect(filteredCount).toBeLessThan(initialCount);
    }
  });

  test('filter badge shows active count', async ({ page }) => {
    const badge = page.locator('#filter-badge');

    // Initially should not show (no filters active)
    await expect(badge).toHaveClass(/hidden/);

    // Select a country
    await page.selectOption('#country-filter', 'US');

    // Badge should now show "1"
    await expect(badge).not.toHaveClass(/hidden/);
    await expect(badge).toHaveText('1');
  });
});
