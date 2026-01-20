/**
 * E2E tests for tablet responsiveness (iPad Mini)
 */
import { test, expect, devices } from '@playwright/test';

test.use({ ...devices['iPad Mini'] });

test.describe('Tablet Layout', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('#map');
  });

  test('page loads on tablet', async ({ page }) => {
    await expect(page).toHaveTitle(/Powder/);
  });

  test('side panel is visible on tablet', async ({ page }) => {
    const panel = page.locator('#side-panel');
    await expect(panel).toBeVisible();
  });
});
