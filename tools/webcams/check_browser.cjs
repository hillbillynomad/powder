// Recheck webcam pages that block plain HTTP clients, in a real browser.
// Called by check.py --browser:
//   node tools/webcams/check_browser.cjs <playwright path> <urls.json>
// Prints {url: {ok, detail}} as JSON. A page passes if it loads with status < 400 and,
// once its scripts have run, shows a cam: an iframe, a <video>, or a sizeable image.
const fs = require('fs');
const { chromium } = require(process.argv[2]);
const urls = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1400, height: 1000 }, locale: 'en-US' });
  const results = {};
  for (const url of urls) {
    const page = await context.newPage();
    try {
      const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
      const status = resp ? resp.status() : 0;
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
      // Lazy-loaded embeds appear on scroll
      await page.evaluate(async () => {
        for (let y = 0; y < document.body.scrollHeight; y += 800) {
          window.scrollTo(0, y);
          await new Promise(r => setTimeout(r, 150));
        }
      }).catch(() => {});
      const found = await page.evaluate(() => {
        const frames = [...document.querySelectorAll('iframe')].filter(f => {
          const r = f.getBoundingClientRect();
          return r.width >= 200 && r.height >= 100;
        }).length;
        const videos = document.querySelectorAll('video').length;
        const imgs = [...document.querySelectorAll('img')].filter(i => i.naturalWidth >= 320).length;
        return { frames, videos, imgs, title: document.title };
      });
      const ok = status > 0 && status < 400 && (found.frames + found.videos + found.imgs) > 0;
      results[url] = { ok, detail: `HTTP ${status}, ${found.frames} iframes, ${found.videos} videos, ${found.imgs} images, ${JSON.stringify(found.title.slice(0, 60))}` };
    } catch (e) {
      results[url] = { ok: false, detail: String(e.message || e).split('\n')[0] };
    }
    await page.close();
  }
  await browser.close();
  process.stdout.write(JSON.stringify(results));
})();
