// v1.31：系统设置里的网络工具（网络优化 / 网络排查 / 网络测速）
const { chromium } = require('playwright');
const path = require('path');
const PREVIEW = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe';
const OUT = path.resolve(__dirname, '../out/shots24');
require('fs').mkdirSync(OUT, { recursive: true });
(async () => {
  const browser = await chromium.launch({ executablePath: EXE });
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push('PAGEERROR ' + e.message));
  await page.goto(PREVIEW, { waitUntil: 'load' });
  await page.waitForTimeout(300);
  await page.evaluate(async () => { show('main'); await load(); document.querySelector('[data-tab="set"]').click(); });
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(OUT, '01-set-page.png') });

  // 网络优化
  await page.evaluate(() => document.getElementById('btnOpt').click());
  await page.waitForTimeout(1500);
  await (await page.$('#optSheet .sheet')).screenshot({ path: path.join(OUT, '02-opt.png') });
  const opt = await page.evaluate(() => document.getElementById('optBody').innerText.slice(0, 400));
  console.log('OPT>>', opt.replace(/\n/g, ' | '));

  // 网络排查
  await page.evaluate(() => { document.getElementById('optClose').click(); document.getElementById('btnNd').click(); });
  await page.waitForTimeout(1500);
  await (await page.$('#ndSheet .sheet')).screenshot({ path: path.join(OUT, '03-netdiag.png') });
  const nd = await page.evaluate(() => document.getElementById('ndBody').innerText.slice(0, 400));
  console.log('ND>>', nd.replace(/\n/g, ' | '));

  // 网络测速
  await page.evaluate(() => { document.getElementById('ndClose').click(); document.getElementById('btnSt').click(); });
  await page.waitForTimeout(300);
  await page.evaluate(() => document.getElementById('stGo').click());
  await page.waitForTimeout(1500);
  await (await page.$('#stSheet .sheet')).screenshot({ path: path.join(OUT, '04-speed.png') });
  const sp = await page.evaluate(() => ({
    num: document.getElementById('stNum').textContent,
    body: document.getElementById('stBody').innerText.replace(/\n/g, ' | '),
  }));
  console.log('SPEED>>', JSON.stringify(sp));

  // 深色
  await page.evaluate(() => { document.documentElement.dataset.theme = 'dark'; document.getElementById('stClose').click(); document.getElementById('btnSt').click(); document.getElementById('stGo').click(); });
  await page.waitForTimeout(1200);
  await (await page.$('#stSheet .sheet')).screenshot({ path: path.join(OUT, '05-speed-dark.png') });

  console.log('ERRS>>', errs.length ? errs.join(' ; ') : 'none');
  await browser.close();
})();
