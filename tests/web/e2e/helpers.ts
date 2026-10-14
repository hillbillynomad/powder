/**
 * Shared helpers for map-dependent e2e tests. Resort bubbles are drawn on a WebGL canvas
 * (MapLibre), so tests go through the window.__powder hooks instead of DOM selectors.
 */
import { Page } from '@playwright/test';

declare global {
  interface Window {
    __map: any;
    __powder: {
      markerCount(): number;
      revealFirstMarker(): { name: string; x: number; y: number } | null;
      firstMarkerRendered(): boolean;
      layerVisibility(id: string): string | null;
      hasTerrain(): boolean;
      weather(): { active: string; frame: number; followNow: boolean; frames: number; playing: boolean } | null;
      weatherReady(): Promise<boolean>;
      setWeatherFrame(index: number): void;
    };
  }
}

/** Resolves once the map is up and at least one resort bubble is displayed; rejects on timeout. */
export async function waitForMarkers(page: Page, timeout = 10000) {
  await page.waitForFunction(
    () => !!window.__powder && window.__powder.markerCount() > 0,
    undefined,
    { timeout }
  );
}

export async function markerCount(page: Page): Promise<number> {
  return page.evaluate(() => (window.__powder ? window.__powder.markerCount() : 0));
}

/** Click the first resort bubble with a real mouse event at its on-screen position. */
export async function clickFirstMarker(page: Page) {
  const point = await page.evaluate(() => window.__powder.revealFirstMarker());
  if (!point) throw new Error('No resort markers to click');
  // Software-rendered WebGL can take a while to draw the frame after the camera jump
  await page.waitForFunction(() => window.__powder.firstMarkerRendered(), undefined, { timeout: 20000 });
  await page.mouse.click(point.x, point.y);
}
