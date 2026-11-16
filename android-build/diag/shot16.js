const { chromium } = require('playwright');
const path = require('path');
const OUT = 'C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/shots16';
const PREVIEW = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe',
  });
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 }, deviceScaleFactor: 2,
    isMobile: true, hasTouch: true,
  });
  const page = await ctx.newPage();
  await page.goto(PREVIEW, { waitUntil: 'load' });
  await page.waitForTimeout(250);
  await page.evaluate(async () => { show('main'); await load(); });
  await page.waitForTimeout(900);

  // 概览
  await page.screenshot({ path: path.join(OUT, '01-home.png'), fullPage: true });
  for (const [k, f] of [['net', '02-net'], ['wifi', '03-wifi'], ['dev', '04-dev'], ['sys', '05-sys']]) {
    await page.evaluate((x) => go(x), k);
    await page.waitForTimeout(900);
    await page.screenshot({ path: path.join(OUT, f + '.png'), fullPage: true });
  }

  // 设备详情
  await page.evaluate(() => go('dev'));
  await page.waitForTimeout(600);
  console.log('dev rows =', await page.evaluate(() => document.querySelectorAll('#devList > *').length));
  await page.evaluate(() => { const r = document.querySelector('#devList > *'); r && r.click(); });
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT, '06-devdetail.png') });
  await ctx.close();
  await browser.close();
  console.log('done');
})();
