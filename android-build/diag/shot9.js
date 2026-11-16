const { chromium } = require('playwright');
const path = require('path');

const OUT = 'C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/shots9';
const PREVIEW = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';

async function card(browser, file, opts) {
  const ctx = await browser.newContext({
    viewport: opts.viewport || { width: 390, height: 844 },
    deviceScaleFactor: 2, colorScheme: opts.dark ? 'dark' : 'light',
    isMobile: true, hasTouch: true,
  });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push(String(e)));
  await page.goto(PREVIEW, { waitUntil: 'load' });
  await page.waitForTimeout(250);
  if (opts.noData) {
    await page.evaluate(() => {
      const orig = window.fetch;
      window.fetch = async (u, o) => {
        if (String(u).indexOf('/api/sysstat') === 0) {
          return { status: 200, json: async () => ({
            ok: true, cpu: null, mem: null,
            reason: '这台固件没有在网页接口中提供 CPU/内存数据',
            ports: [
              { name: 'WAN', if: 'eth0', wan: true, link: false, has: true },
              { name: 'LAN1', if: 'eth1', wan: false, link: true, has: true },
              { name: 'LAN2', if: 'eth2', wan: false, link: false, has: true },
              { name: 'LAN3', if: 'eth3', wan: false, link: false, has: true }
            ]
          }) };
        }
        return orig(u, o);
      };
    });
  }
  await page.evaluate(async () => { show('main'); await load(); });
  await page.waitForTimeout(800);
  const info = await page.evaluate(() => ({
    cpu: document.getElementById('cpuVal').textContent,
    mem: document.getElementById('memVal').textContent,
    note: document.getElementById('sysNote').textContent,
    ports: [...document.querySelectorAll('#portGrid .port')].map(
      (p) => p.querySelector('.p-nm').textContent + ':' + p.querySelector('.p-st').textContent),
    tip: document.getElementById('sysTip').classList.contains('hidden')
      ? '(hidden)' : document.getElementById('sysTip').textContent,
    overflow: (() => {
      const c = document.getElementById('sysCard');
      return c.scrollWidth > c.clientWidth + 1;
    })(),
  }));
  console.log(file, JSON.stringify(info, null, 0));
  await page.evaluate(() => document.getElementById('sysCard').scrollIntoView({ block: 'start' }));
  await page.waitForTimeout(350);
  await page.screenshot({ path: path.join(OUT, file) });
  if (errs.length) console.log('  ERR:', errs.join(' | '));
  await ctx.close();
}

(async () => {
  const browser = await chromium.launch();
  await card(browser, '50-sys-light.png', {});
  await card(browser, '51-sys-dark.png', { dark: true });
  await card(browser, '52-sys-nodata.png', { noData: true });
  await card(browser, '53-sys-small.png', { viewport: { width: 320, height: 568 } });
  await browser.close();
  console.log('done');
})();
