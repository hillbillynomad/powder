/**
 * E2E tests for detail panel functionality
 */
import { test, expect } from '@playwright/test';

test.describe('Side Panel', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('#map');
  });

  test('panel has tab buttons', async ({ page }) => {
    const topTenTab = page.locator('.panel-tab[data-tab="top10"]');
    const detailsTab = page.locator('.panel-tab[data-tab="details"]');

    await expect(topTenTab).toBeVisible();
    await expect(detailsTab).toBeVisible();
  });

  test('tab switching works', async ({ page }) => {
    const topTenTab = page.locator('.panel-tab[data-tab="top10"]');
    const detailsTab = page.locator('.panel-tab[data-tab="details"]');
    const topTenContent = page.locator('#top10-content');
    const detailsContent = page.locator('#details-content');

    // Click Top 10 tab
    await topTenTab.click();
    await expect(topTenContent).not.toHaveClass(/hidden/);

    // Click Details tab
    await detailsTab.click();
    await expect(detailsContent).not.toHaveClass(/hidden/);
  });

  test('panel can be collapsed', async ({ page }) => {
    const collapseBtn = page.locator('#panel-collapse');
    const panel = page.locator('#side-panel');

    await expect(panel).not.toHaveClass(/collapsed/);

    await collapseBtn.click();

    await expect(panel).toHaveClass(/collapsed/);
  });
});

test.describe('Detail Panel with Data', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    try {
      await page.waitForSelector('.leaflet-interactive', { timeout: 5000 });
    } catch {
      test.skip(true, 'No forecast data available');
    }
  });

  test('clicking marker shows resort details', async ({ page }) => {
    // Click first marker using JavaScript dispatch for cross-browser compatibility
    const marker = page.locator('.leaflet-interactive').first();
    await marker.dispatchEvent('click');

    // Detail header should show resort name
    const detailHeader = page.locator('.detail-header h2');
    await expect(detailHeader).toBeVisible({ timeout: 5000 });
  });

  test('detail shows elevation info', async ({ page }) => {
    const marker = page.locator('.leaflet-interactive').first();
    await marker.dispatchEvent('click');

    // Wait for detail to load
    await page.waitForSelector('.detail-meta', { timeout: 5000 });

    const detailMeta = page.locator('.detail-meta');
    const text = await detailMeta.textContent();

    // Should contain "ft" for elevation
    expect(text).toMatch(/ft/);
  });

  test('detail shows forecast table', async ({ page }) => {
    const marker = page.locator('.leaflet-interactive').first();
    await marker.dispatchEvent('click');

    // Wait for detail to load
    await page.waitForSelector('.forecast-table', { timeout: 5000 });

    const table = page.locator('.forecast-table');
    await expect(table).toBeVisible();
  });
});

test.describe('Top 10 Panel', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    try {
      await page.waitForSelector('.leaflet-interactive', { timeout: 5000 });
    } catch {
      test.skip(true, 'No forecast data available');
    }

    // Switch to Top 10 tab
    await page.locator('.panel-tab[data-tab="top10"]').click();
  });

  test('top 10 list is populated', async ({ page }) => {
    await page.waitForSelector('.top-resort-item', { timeout: 5000 });

    const items = page.locator('.top-resort-item');
    const count = await items.count();

    // Should have up to 10 items
    expect(count).toBeGreaterThan(0);
    expect(count).toBeLessThanOrEqual(10);
  });

  test('clicking top 10 item focuses resort', async ({ page }) => {
    await page.waitForSelector('.top-resort-item', { timeout: 5000 });

    // Click first item
    await page.locator('.top-resort-item').first().click();

    // Detail should show
    const detailHeader = page.locator('.detail-header h2');
    await expect(detailHeader).toBeVisible({ timeout: 5000 });
  });
});
