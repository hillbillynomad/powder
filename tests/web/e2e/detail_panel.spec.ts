/**
 * E2E tests for detail panel functionality
 */
import { test, expect } from '@playwright/test';
import { waitForMarkers, markerCount, clickFirstMarker } from './helpers';

test.describe('Side Panel', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('#map');
  });

  test('panel offers In view and Top 10, defaulting to In view', async ({ page }) => {
    const inView = page.locator('.panel-mode[data-mode="view"]');
    const topTen = page.locator('.panel-mode[data-mode="top10"]');

    await expect(inView).toBeVisible();
    await expect(topTen).toBeVisible();
    await expect(inView).toHaveClass(/active/);
    await expect(page.locator('.panel-mode[data-mode="search"]')).toBeHidden();
  });

  test('mode switching works', async ({ page }) => {
    const topTen = page.locator('.panel-mode[data-mode="top10"]');
    await topTen.click();
    await expect(topTen).toHaveClass(/active/);
    await expect(page.locator('#list-content')).not.toHaveClass(/hidden/);
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
      await waitForMarkers(page, 5000);
    } catch {
      test.skip(true, 'No forecast data available');
    }
  });

  test('clicking marker shows resort details', async ({ page }) => {
    await clickFirstMarker(page);

    // Detail header should show resort name
    const detailHeader = page.locator('.detail-header h2');
    await expect(detailHeader).toBeVisible({ timeout: 5000 });
  });

  test('detail shows elevation info', async ({ page }) => {
    await clickFirstMarker(page);

    // Wait for detail to load
    await page.waitForSelector('.detail-meta', { timeout: 5000 });

    const detailMeta = page.locator('.detail-meta');
    const text = await detailMeta.textContent();

    // Should contain "ft" for elevation
    expect(text).toMatch(/ft/);
  });

  test('detail shows forecast table', async ({ page }) => {
    await clickFirstMarker(page);

    // Wait for detail to load
    await page.waitForSelector('.forecast-table', { timeout: 5000 });

    const table = page.locator('.forecast-table');
    await expect(table).toBeVisible();
  });

  test('back bar returns from details to the list', async ({ page }) => {
    await clickFirstMarker(page);
    await expect(page.locator('#details-content')).not.toHaveClass(/hidden/);
    await expect(page.locator('#detail-back')).toContainText('In view');

    await page.locator('#detail-back').click();
    await expect(page.locator('#list-content')).not.toHaveClass(/hidden/);
  });
});

test.describe('Top 10 list', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    try {
      await waitForMarkers(page, 5000);
    } catch {
      test.skip(true, 'No forecast data available');
    }

    await page.locator('.panel-mode[data-mode="top10"]').click();
  });

  test('top 10 list is populated', async ({ page }) => {
    await page.waitForSelector('#resort-list .resort-item', { timeout: 5000 });

    const items = page.locator('#resort-list .resort-item');
    const count = await items.count();

    // Should have up to 10 items
    expect(count).toBeGreaterThan(0);
    expect(count).toBeLessThanOrEqual(10);
    await expect(items.first().locator('.rank')).toHaveText('#1');
  });

  test('clicking top 10 item focuses resort', async ({ page }) => {
    await page.waitForSelector('#resort-list .resort-item', { timeout: 5000 });

    await page.locator('#resort-list .resort-item').first().click();

    // Detail should show, with a way back to the Top 10
    const detailHeader = page.locator('.detail-header h2');
    await expect(detailHeader).toBeVisible({ timeout: 5000 });
    await expect(page.locator('#detail-back')).toContainText('Top 10');
  });
});

test.describe('In view list', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await waitForMarkers(page);
  });

  test('lists only the resorts on screen and follows the map', async ({ page }) => {
    const count = () => page.locator('#view-count').textContent().then(t => Number(t));
    await expect(page.locator('#view-count')).not.toBeEmpty();
    const globe = await count();
    expect(globe).toBeGreaterThan(0);

    // Zoom into Utah: far fewer resorts, and the list matches the count
    await page.evaluate(() => window.__map.jumpTo({ center: [-111.6, 40.6], zoom: 8 }));
    await expect.poll(count, { timeout: 15000 }).toBeLessThan(globe);
    const items = page.locator('#resort-list .resort-item');
    await expect.poll(async () => (await items.count()) === (await count())).toBe(true);
    await expect(items.first()).toContainText('United States');

    // Middle of the Pacific: nothing in view, with a link to the Top 10
    await page.evaluate(() => window.__map.jumpTo({ center: [-150, 0], zoom: 6 }));
    await expect(page.locator('#list-summary')).toContainText('No resorts in view', { timeout: 15000 });
    await page.locator('#list-summary [data-action="top10"]').click();
    await expect(page.locator('.panel-mode[data-mode="top10"]')).toHaveClass(/active/);
  });

  test('snowflake logo goes home: whole globe, In view, nothing selected', async ({ page }) => {
    await page.locator('#search-input').fill('chamonix');
    await page.locator('#search-input').press('Enter');
    await expect(page.locator('#details-content')).not.toHaveClass(/hidden/);

    await page.locator('#home-button').click();
    await expect(page.locator('#search-input')).toHaveValue('');
    await expect(page.locator('#list-content')).not.toHaveClass(/hidden/);
    await expect(page.locator('.panel-mode[data-mode="view"]')).toHaveClass(/active/);
    await page.waitForFunction(() => !window.__map.isMoving(), undefined, { timeout: 20000 });
    const zoom = await page.evaluate(() => window.__map.getZoom() - window.__map.getMinZoom());
    expect(zoom).toBeCloseTo(0, 1);
  });
});
