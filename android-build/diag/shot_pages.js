const { chromium } = require('playwright');
const path = require('path');
const PREVIEW = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe';
const OUT = path.resolve(__dirname, '../out/shots-pages');
require('fs').mkdirSync(OUT, { recursive: true });
const TABS = ['home','net','wifi','dev','set'];
(async () => {
  const browser = await chromium.launch({ executablePath: EXE });
  for (const [name, vp, mobile] of [['desk', { width: 1440, height: 900 }, false], ['mob', { width: 390, height: 844 }, true]]) {
    const ctx = await browser.newContext({ viewport: vp, isMobile: mobile, deviceScaleFactor: mobile ? 2 : 1 });
    const page = await ctx.newPage();
    await page.goto(PREVIEW, { waitUntil: 'load' });
    await page.waitForTimeout(300);
    await page.evaluate(async () => { show('main'); await load(); });
    await page.waitForTimeout(900);
    for (const t of TABS) {
      await page.evaluate((t) => document.querySelector(`[data-tab="${t}"]`).click(), t);
      await page.waitForTimeout(700);
      await page.screenshot({ path: path.join(OUT, `${name}-${t}.png`), fullPage: false });
    }
    await ctx.close();
  }
  await browser.close();
  console.log('ok');
})();
