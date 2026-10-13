/**
 * E2E regression tests for layout bugs: app shell scrolling away, map pan "jam",
 * and an unrecoverable collapsed side panel. Each test is a few lines on purpose.
 */
import { test, expect } from '@playwright/test';

async function load(page) {
  await page.goto('/');
  await page.waitForSelector('#map');
  await page.waitForFunction(() => (window as any).__map !== undefined);
}

test.describe('App shell', () => {
  test('cannot be scrolled out of view', async ({ page }) => {
    await load(page);
    await page.evaluate(() => {
      for (const sel of ['.main-container', '.content-wrapper', '.map-wrapper']) {
        const el = document.querySelector(sel) as HTMLElement;
        el.scrollLeft = 400;
        el.scrollTop = 400;
      }
      window.scrollTo(400, 400);
    });
    await page.waitForTimeout(100);

    const scroll = await page.evaluate(() =>
      ['.main-container', '.content-wrapper', '.map-wrapper'].map((s) => {
        const el = document.querySelector(s) as HTMLElement;
        return [el.scrollLeft, el.scrollTop];
      }).concat([[window.scrollX, window.scrollY]])
    );
    for (const [x, y] of scroll) {
      expect(x).toBe(0);
      expect(y).toBe(0);
    }

    const header = await page.locator('.header').boundingBox();
    const panel = await page.locator('#side-panel').boundingBox();
    expect(header!.y).toBeGreaterThanOrEqual(0);
    expect(panel!.x).toBeGreaterThanOrEqual(0);
    expect(panel!.y).toBeGreaterThanOrEqual(0);
  });

  test('document is never taller than the viewport', async ({ page }) => {
    await load(page);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollHeight - window.innerHeight
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});

test.describe('Map panning', () => {
  test('can pan to the southern hemisphere and stays within Mercator bounds', async ({ page }) => {
    await load(page);
    const result = await page.evaluate(async () => {
      const map = (window as any).__map;
      map.setView([30, 0], map.getMinZoom() + 1, { animate: false });
      // Pan in drag-sized steps (a single huge jump bypasses Leaflet's bounds clamp)
      for (let i = 0; i < 30; i++) map.panBy([0, 300], { animate: false });
      await new Promise((r) => setTimeout(r, 500)); // let maxBounds settle
      const b = map.getBounds();
      const mapEl = document.getElementById('map')!.getBoundingClientRect();
      return {
        south: b.getSouth(),
        north: b.getNorth(),
        mapBottom: mapEl.bottom,
        innerHeight: window.innerHeight,
      };
    });
    // Bounds reach (near) the southern limit and never exceed Mercator range
    expect(result.south).toBeLessThan(-30);
    // Small tolerance: Leaflet eases back inside maxBounds, so an edge frame can overshoot slightly
    expect(result.south).toBeGreaterThanOrEqual(-86);
    expect(result.north).toBeLessThanOrEqual(86);
    // The whole map must be on-screen, otherwise "south" is below the fold
    expect(result.mapBottom).toBeLessThanOrEqual(result.innerHeight + 1);
  });
});

test.describe('Side panel recovery', () => {
  test('collapsed panel can always be reopened', async ({ page }) => {
    await load(page);
    const panel = page.locator('#side-panel');
    const reopen = page.locator('#panel-reopen');

    await expect(reopen).toBeHidden();
    // On the bottom sheet the control cycles peek -> full -> collapsed
    const collapse = page.locator('#panel-collapse');
    for (let i = 0; i < 2; i++) {
      if (await panel.evaluate((el) => el.classList.contains('collapsed'))) break;
      await collapse.click();
      await page.waitForTimeout(400);
    }
    await expect(panel).toHaveClass(/collapsed/);
    await expect(reopen).toBeVisible();

    await reopen.click();
    await expect(panel).not.toHaveClass(/collapsed/);
    await expect(reopen).toBeHidden();
    const box = await panel.boundingBox();
    expect(box!.width).toBeGreaterThan(50);
    expect(box!.height).toBeGreaterThan(50);
  });

  test('deselecting a resort does not collapse the panel', async ({ page }) => {
    await load(page);
    await page.evaluate(() => (document.querySelector('.leaflet-container') as HTMLElement).click());
    await expect(page.locator('#side-panel')).not.toHaveClass(/collapsed/);
  });
});

test.describe('Responsive layout', () => {
  test('wide viewport: panel sits left of the map', async ({ page }) => {
    await page.setViewportSize({ width: 1200, height: 800 });
    await load(page);
    const panel = (await page.locator('#side-panel').boundingBox())!;
    const map = (await page.locator('#map').boundingBox())!;
    expect(panel.x + panel.width).toBeLessThanOrEqual(map.x + 1);
  });

  test('narrow viewport: panel becomes a bottom sheet that scrolls internally', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await load(page);
    const panel = (await page.locator('#side-panel').boundingBox())!;
    const map = (await page.locator('#map').boundingBox())!;
    expect(panel.y).toBeGreaterThanOrEqual(map.y + map.height - 1);
    expect(map.height).toBeGreaterThan(844 * 0.4);

    // Panel content scrolls on its own and never moves the page
    const after = await page.evaluate(() => {
      const c = document.querySelector('.panel-content') as HTMLElement;
      c.scrollTop = 10000;
      return { doc: document.scrollingElement!.scrollTop, headerTop: document.querySelector('.header')!.getBoundingClientRect().top };
    });
    expect(after.doc).toBe(0);
    expect(after.headerTop).toBe(0);
  });

  test('resizing across the breakpoint flips the layout live', async ({ page }) => {
    await page.setViewportSize({ width: 1200, height: 800 });
    await load(page);
    await page.setViewportSize({ width: 500, height: 900 });
    await page.waitForTimeout(500);
    const panel = (await page.locator('#side-panel').boundingBox())!;
    const map = (await page.locator('#map').boundingBox())!;
    expect(panel.y).toBeGreaterThanOrEqual(map.y + map.height - 1);
  });
});
