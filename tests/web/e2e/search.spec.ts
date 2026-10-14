/**
 * E2E tests for the header resort search (results are listed in the side panel)
 */
import { test, expect } from '@playwright/test';
import { waitForMarkers } from './helpers';

test.describe('Resort search', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await waitForMarkers(page);
  });

  test('typing lists matches in the panel; Enter flies to the top result', async ({ page }) => {
    const input = page.locator('#search-input');
    await input.fill('chamonix');

    const searchMode = page.locator('.panel-mode[data-mode="search"]');
    await expect(searchMode).toBeVisible();
    await expect(searchMode).toHaveClass(/active/);
    await expect(page.locator('#resort-list .resort-item').first()).toContainText(/Chamonix/i);

    await input.press('Enter');
    await expect(page.locator('#details-content')).not.toHaveClass(/hidden/);
    await expect(page.locator('#detail-content')).toContainText(/Chamonix/i);
    await expect(page.locator('#detail-back')).toContainText('Search results');

    // Camera ends up centred on the resort
    await page.waitForFunction(() => !window.__map.isMoving(), undefined, { timeout: 20000 });
    const center = await page.evaluate(() => window.__map.getCenter());
    expect(center.lat).toBeCloseTo(45.9, 0);
    expect(center.lng).toBeCloseTo(6.9, 0);

    // Back returns to the results
    await page.locator('#detail-back').click();
    await expect(page.locator('#list-content')).not.toHaveClass(/hidden/);
    await expect(searchMode).toHaveClass(/active/);
  });

  test('shows an empty state; Escape clears the search back to In view', async ({ page }) => {
    const input = page.locator('#search-input');
    await input.fill('zzznotaresort');
    await expect(page.locator('#list-summary')).toContainText('No resorts match');

    await input.press('Escape');
    await expect(input).toHaveValue('');
    await expect(page.locator('.panel-mode[data-mode="search"]')).toBeHidden();
    await expect(page.locator('.panel-mode[data-mode="view"]')).toHaveClass(/active/);
  });

  test('clear button empties the box and returns to the previous list', async ({ page }) => {
    const input = page.locator('#search-input');
    const clear = page.locator('#search-clear');
    await expect(clear).toBeHidden();

    await page.locator('.panel-mode[data-mode="top10"]').click();
    await input.fill('chamonix');
    await expect(clear).toBeVisible();

    await clear.click();
    await expect(input).toHaveValue('');
    await expect(clear).toBeHidden();
    await expect(page.locator('.panel-mode[data-mode="top10"]')).toHaveClass(/active/);
  });

  test('In view is one click away while searching', async ({ page }) => {
    await page.locator('#search-input').fill('alta');
    await page.locator('.panel-mode[data-mode="view"]').click();
    await expect(page.locator('#list-summary')).toContainText(/on the map/);
    // The query is kept, so its tab stays available
    await expect(page.locator('.panel-mode[data-mode="search"]')).toBeVisible();
  });
});
