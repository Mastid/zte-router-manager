const { chromium } = require('playwright');
const path = require('path');

const PANEL = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/zte-router-lab/panel.html';
const PREVIEW = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';
const OUT = 'C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/shots';

(async () => {
  const browser = await chromium.launch();

  async function shot(file, name, opts = {}) {
    const ctx = await browser.newContext({
      viewport: opts.viewport || { width: 390, height: 844 },
      deviceScaleFactor: 2,
      colorScheme: opts.dark ? 'dark' : 'light',
      isMobile: !!opts.mobile,
      hasTouch: !!opts.mobile,
    });
    const page = await ctx.newPage();
    const errs = [];
    page.on('pageerror', (e) => errs.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
    await page.goto(file, { waitUntil: 'load' });
    await page.waitForTimeout(700);
    if (opts.before) await opts.before(page);
    await page.screenshot({ path: path.join(OUT, name + '.png'), fullPage: !!opts.full });
    if (errs.length) console.log(name, 'ERRORS:', errs.join(' | '));
    await ctx.close();
  }

  await shot(PANEL, '01-login', {});
  await shot(PREVIEW, '02-main', { full: true });
  await shot(PREVIEW, '03-main-dark', { dark: true, full: true });
  await shot(PREVIEW, '04-devsheet', {
    before: async (p) => {
      await p.evaluate(() => { LIMITS = { 'D8:9E:F3:4C:55:82': { up: 5, down: 20, inst: '1' } }; render(LAST); });
      await p.waitForTimeout(200);
      await p.locator('.dev').nth(2).click();
      await p.waitForTimeout(900);
    },
  });
  await shot(PREVIEW, '05-devsheet-dark', {
    dark: true,
    before: async (p) => {
      await p.evaluate(() => { LIMITS = { 'D8:9E:F3:4C:55:82': { up: 5, down: 20, inst: '1' } }; render(LAST); });
      await p.waitForTimeout(200);
      await p.locator('.dev').nth(2).click();
      await p.waitForTimeout(900);
    },
  });
  await shot(PREVIEW, '06-desktop', { viewport: { width: 920, height: 1000 }, full: true });
  await shot(PANEL, '07-wifisheet', {
    before: async (p) => {
      await p.evaluate(async () => {
        window.fetch = async (u) => ({ status: 200, json: async () => ({ logged: true }) });
        await load();
      }).catch(() => {});
    },
  });

  await browser.close();
  console.log('done');
})();
