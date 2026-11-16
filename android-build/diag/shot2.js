const { chromium } = require('playwright');
const path = require('path');

const OUT = 'C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/shots2';
const PREVIEW = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';

(async () => {
  const browser = await chromium.launch();

  async function boot(opts = {}) {
    const ctx = await browser.newContext({
      viewport: opts.viewport || { width: 390, height: 844 },
      deviceScaleFactor: 2,
      colorScheme: opts.dark ? 'dark' : 'light',
      isMobile: true, hasTouch: true,
    });
    const page = await ctx.newPage();
    const errs = [];
    page.on('pageerror', (e) => errs.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error' && !/file:\/\/\/C:\/api/.test(m.text())) errs.push(m.text()); });
    await page.goto(PREVIEW, { waitUntil: 'load' });
    await page.waitForTimeout(500);
    await page.evaluate(async () => { show('main'); await load(); });
    await page.waitForTimeout(300);
    return { ctx, page, errs };
  }

  async function shot(name, opts = {}) {
    const { ctx, page, errs } = await boot(opts);
    if (opts.tab) {
      await page.click(`.dock button[data-tab="${opts.tab}"]`);
      await page.waitForTimeout(600);
    }
    if (opts.before) await opts.before(page);
    await page.screenshot({ path: path.join(OUT, name + '.png'), fullPage: !!opts.full });
    if (errs.length) console.log(name, 'ERR:', errs.join(' | '));
    await ctx.close();
  }

  await shot('01-home', { full: true });
  await shot('02-wifi', { tab: 'wifi', full: true });
  await shot('03-dev', { tab: 'dev', full: true });
  await shot('04-sec', { tab: 'sec', full: true });
  await shot('05-sec-dark', { tab: 'sec', dark: true, full: true });
  await shot('06-set', { tab: 'set', full: true });
  await shot('07-lan-sheet', {
    tab: 'set',
    before: async (p) => { await p.click('#btnLanEdit'); await p.waitForTimeout(400); },
  });
  await shot('08-bind-sheet', {
    tab: 'set',
    before: async (p) => { await p.click('#btnBindAdd'); await p.waitForTimeout(400); },
  });
  await shot('09-devsheet', {
    tab: 'dev',
    before: async (p) => { await p.locator('.dev').nth(0).click(); await p.waitForTimeout(900); },
  });
  await shot('10-desktop', { viewport: { width: 920, height: 1000 }, full: true });

  await browser.close();
  console.log('done');
})();
