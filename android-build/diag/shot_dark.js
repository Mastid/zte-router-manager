const { chromium } = require('playwright');
const path = require('path');
const PREVIEW = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe';
const OUT = path.resolve(__dirname, '../out/shots-pages');
(async () => {
  const browser = await chromium.launch({ executablePath: EXE });
  for (const [name, vp, mobile] of [['dk-desk', { width: 1440, height: 900 }, false], ['dk-mob', { width: 390, height: 844 }, true]]) {
    const ctx = await browser.newContext({ viewport: vp, isMobile: mobile, deviceScaleFactor: mobile ? 2 : 1, colorScheme: 'dark' });
    const page = await ctx.newPage();
    await page.goto(PREVIEW, { waitUntil: 'load' });
    await page.waitForTimeout(300);
    await page.evaluate(() => { localStorage.setItem('zte_theme', 'dark'); document.documentElement.setAttribute('data-theme','dark'); });
    await page.evaluate(async () => { show('main'); await load(); });
    await page.waitForTimeout(900);
    for (const t of ['home','net','dev','set']) {
      await page.evaluate((t) => document.querySelector(`[data-tab="${t}"]`).click(), t);
      await page.waitForTimeout(600);
      await page.screenshot({ path: path.join(OUT, `${name}-${t}.png`) });
    }
    await ctx.close();
  }
  await browser.close();
  console.log('ok');
})();
