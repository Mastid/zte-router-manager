const { chromium } = require('playwright');
const path = require('path');
const OUT = path.resolve(__dirname, '../out/shots27');
require('fs').mkdirSync(OUT, { recursive: true });
const URL = process.env.PWA_URL || 'http://127.0.0.1:8901/?t=cdbe2a';

(async () => {
  const browser = await chromium.launch({ executablePath: 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe' });
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true,
    deviceScaleFactor: 3, userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
  });
  const page = await ctx.newPage();
  await page.goto(URL, { waitUntil: 'load' });
  await page.waitForTimeout(1200);
  const meta = await page.evaluate(() => ({
    manifest: !!document.querySelector('link[rel="manifest"]'),
    touch: (document.querySelector('link[rel="apple-touch-icon"]') || {}).href || '',
    standalone: matchMedia('(display-mode: standalone)').matches,
    title: document.title,
  }));
  console.log(JSON.stringify(meta));
  await page.screenshot({ path: path.join(OUT, 'ios-first-open.png') });
  // 检查图标与 manifest 实际可达
  const res = await page.evaluate(async () => {
    const a = await fetch('/pwa/icon-180.png');
    const b = await fetch('/manifest.webmanifest');
    return [a.status, b.status];
  });
  console.log('assets', res.join('/'));
  await browser.close();
  console.log('ok');
})();
