const { chromium } = require('playwright');
const path = require('path');

const OUT = 'C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/shots3';
const PREVIEW = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';

(async () => {
  const browser = await chromium.launch();

  async function shot(name, opts = {}) {
    const ctx = await browser.newContext({
      viewport: opts.viewport || { width: 390, height: 844 },
      deviceScaleFactor: 2,
      colorScheme: opts.dark ? 'dark' : 'light',
      isMobile: true, hasTouch: true,
    });
    const page = await ctx.newPage();
    const errs = [];
    page.on('pageerror', (e) => errs.push(String(e)));
    await page.goto(PREVIEW, { waitUntil: 'load' });
    await page.waitForTimeout(500);
    await page.evaluate(async () => { show('main'); await load(); });
    await page.waitForTimeout(600);
    if (opts.before) await opts.before(page);
    await page.screenshot({ path: path.join(OUT, name + '.png'), fullPage: !!opts.full });
    if (errs.length) console.log(name, 'ERR:', errs.join(' | '));
    await ctx.close();
  }

  await shot('01-home-light', { full: true });
  await shot('02-home-dark', { dark: true, full: true });
  await shot('03-temp-unknown', {
    before: async (p) => { await p.evaluate(() => renderTemp({ c: null, reason: '未暴露', cpu: null, mem: null })); await p.waitForTimeout(300); },
  });
  await shot('04-temp-hot', {
    before: async (p) => { await p.evaluate(() => renderTemp({ c: 79, cpu: 88, mem: 72 })); await p.waitForTimeout(700); },
  });
  await shot('05-temp-hot-dark', {
    dark: true,
    before: async (p) => { await p.evaluate(() => renderTemp({ c: 79, cpu: 88, mem: 72 })); await p.waitForTimeout(700); },
  });
  await shot('06-desktop', { viewport: { width: 920, height: 1000 }, full: true });

  await browser.close();
  console.log('done');
})();
