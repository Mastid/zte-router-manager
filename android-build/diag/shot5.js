const { chromium } = require('playwright');
const path = require('path');
const OUT = 'C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/shots5';
const PREVIEW = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';

(async () => {
  const browser = await chromium.launch();

  async function open(dark) {
    const ctx = await browser.newContext({
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: 2,
      colorScheme: dark ? 'dark' : 'light',
      isMobile: true, hasTouch: true,
    });
    const page = await ctx.newPage();
    const errs = [];
    page.on('pageerror', (e) => errs.push(String(e)));
    await page.goto(PREVIEW, { waitUntil: 'load' });
    await page.waitForTimeout(300);
    await page.evaluate(async () => { show('main'); await load(); });
    await page.waitForTimeout(500);
    await page.evaluate(async () => { go('set'); await loadSysInfo(); });
    await page.waitForTimeout(400);
    return { ctx, page, errs };
  }

  const a = await open(false);
  console.log('light =>', await a.page.evaluate(() => document.documentElement.dataset.theme));
  await a.page.screenshot({ path: path.join(OUT, '10-set-light.png'), fullPage: true });

  await a.page.click('#themeSeg button[data-mode="dark"]');
  await a.page.waitForTimeout(400);
  console.log('manual dark =>', await a.page.evaluate(() => document.documentElement.dataset.theme));
  await a.page.screenshot({ path: path.join(OUT, '11-set-manual-dark.png'), fullPage: true });

  await a.page.click('#themeSeg button[data-mode="light"]');
  await a.page.waitForTimeout(300);
  console.log('manual light =>', await a.page.evaluate(() => document.documentElement.dataset.theme));
  if (a.errs.length) console.log('ERR light:', a.errs.join(' | '));
  await a.ctx.close();

  const b = await open(true);
  console.log('dark =>', await b.page.evaluate(() => document.documentElement.dataset.theme));
  await b.page.screenshot({ path: path.join(OUT, '12-set-dark.png'), fullPage: true });
  await b.page.evaluate(() => go('home'));
  await b.page.waitForTimeout(400);
  await b.page.screenshot({ path: path.join(OUT, '13-home-dark.png'), fullPage: true });
  if (b.errs.length) console.log('ERR dark:', b.errs.join(' | '));
  await b.ctx.close();

  await browser.close();
  console.log('done');
})();
