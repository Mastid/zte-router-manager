const { chromium } = require('playwright');
const path = require('path');
const OUT = 'C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/shots15';
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
  const errs = [];
  page.on('pageerror', (e) => errs.push(String(e)));
  await page.goto(PREVIEW, { waitUntil: 'load' });
  await page.waitForTimeout(250);
  await page.evaluate(async () => { show('main'); await load(); });
  await page.waitForTimeout(900);
  console.log('ports =', await page.evaluate(() =>
    [...document.querySelectorAll('#portGrid .port')].map((p) =>
      p.dataset.port + ': ' + p.querySelector('.p-st').innerText.trim()
      + (p.classList.contains('on') ? ' [on]' : '')).join(' | ')));
  await page.evaluate(() => document.getElementById('sysCard').scrollIntoView({ block: 'center' }));
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(OUT, '01-ports.png') });

  // WAN 弹层
  await page.evaluate(() => openPort('WAN'));
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(OUT, '02-wan.png') });
  await page.evaluate(() => document.getElementById('ptClose').click());
  await page.waitForTimeout(300);

  // LAN1 弹层（丝印 LAN1，台式机）
  await page.evaluate(() => openPort('LAN1'));
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(OUT, '03-lan1.png') });
  await page.evaluate(() => document.getElementById('ptClose').click());
  await page.waitForTimeout(300);

  // LAN2 弹层（未连接）
  await page.evaluate(() => openPort('LAN2'));
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(OUT, '04-lan2.png') });

  if (errs.length) console.log('ERR:', errs.join(' | '));
  await ctx.close();
  await browser.close();
  console.log('done');
})();
