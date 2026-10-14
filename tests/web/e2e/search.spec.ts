/**
 * E2E tests for the header resort search
 */
import { test, expect } from '@playwright/test';
import { waitForMarkers } from './helpers';

test.describe('Resort search', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await waitForMarkers(page);
  });

  test('Enter lists matches and flies to the top result', async ({ page }) => {
    const input = page.locator('#search-input');
    await input.fill('chamonix');
    await input.press('Enter');

    const results = page.locator('#search-results .search-result');
    await expect(results.first()).toContainText(/Chamonix/i);
    await expect(page.locator('#details-content')).not.toHaveClass(/hidden/);
    await expect(page.locator('#detail-content')).toContainText(/Chamonix/i);

    // Camera ends up centred on the resort
    await page.waitForFunction(() => !window.__map.isMoving(), undefined, { timeout: 20000 });
    const center = await page.evaluate(() => window.__map.getCenter());
    expect(center.lat).toBeCloseTo(45.9, 0);
    expect(center.lng).toBeCloseTo(6.9, 0);
  });

  test('shows an empty state and closes on Escape', async ({ page }) => {
    const input = page.locator('#search-input');
    await input.fill('zzznotaresort');
    await input.press('Enter');

    const panel = page.locator('#search-results');
    await expect(panel).toBeVisible();
    await expect(panel).toContainText('No resorts found');

    await page.keyboard.press('Escape');
    await expect(panel).toBeHidden();
  });
});
