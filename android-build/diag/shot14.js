const { chromium } = require('playwright');
const path = require('path');
const OUT = 'C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/shots14';
const PREVIEW = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';

async function open(browser, dark) {
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 }, deviceScaleFactor: 2,
    colorScheme: dark ? 'dark' : 'light', isMobile: true, hasTouch: true,
  });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push(String(e)));
  await page.goto(PREVIEW, { waitUntil: 'load' });
  await page.waitForTimeout(250);
  await page.evaluate(async () => { show('main'); await load(); });
  await page.waitForTimeout(900);
  return { ctx, page, errs };
}

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe',
  });
  let { ctx, page, errs } = await open(browser, false);

  // 设备列表的频段标签
  console.log('clients =', await page.evaluate(() =>
    [...document.querySelectorAll('#devList > *')].slice(0, 8)
      .map((e) => e.innerText.replace(/\n/g, ' ').slice(0, 90)).join(' ;; ')));
  await page.evaluate(() => document.getElementById('devList').scrollIntoView({ block: 'center' }));
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(OUT, '01-clients.png') });

  // WiFi 页 + 管理卡片
  await page.evaluate(() => go('wifi'));
  await page.waitForTimeout(1200);
  console.log('wmCard =', await page.evaluate(() => {
    const c = document.getElementById('wmCard');
    if (!c) return 'MISSING';
    const r = c.getBoundingClientRect();
    return r.width + 'x' + r.height;
  }));
  console.log('wmList =', await page.evaluate(() =>
    [...document.querySelectorAll('#wmList .mrow')].map((r) =>
      r.dataset.wm + '=' + (r.querySelector('.mt i') ? r.querySelector('.mt i').innerText.trim() : '?')).join(' | ')));
  await page.evaluate(() => document.getElementById('wmCard').scrollIntoView({ block: 'center' }));
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(OUT, '02-wifi.png') });

  // 信道弹层
  await page.evaluate(() => { const r = document.querySelector('[data-wm="ch"]'); r && r.click(); });
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(OUT, '03-ch.png') });
  await page.evaluate(() => document.getElementById('chClose').click());
  await page.waitForTimeout(300);

  // 信号强度弹层
  await page.evaluate(() => { const r = document.querySelector('[data-wm="sg"]'); r && r.click(); });
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(OUT, '04-sg.png') });
  await page.evaluate(() => document.getElementById('sgClose').click());
  await page.waitForTimeout(300);

  // 定时关闭弹层
  await page.evaluate(() => { const r = document.querySelector('[data-wm="tm"]'); r && r.click(); });
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(OUT, '05-tm.png') });

  if (errs.length) console.log('ERR:', errs.join(' | '));
  await ctx.close();

  // 深色：WiFi 页
  ({ ctx, page, errs } = await open(browser, true));
  await page.evaluate(() => go('wifi'));
  await page.waitForTimeout(1200);
  await page.evaluate(() => document.getElementById('wmCard').scrollIntoView({ block: 'center' }));
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(OUT, '06-wifi-dark.png') });
  if (errs.length) console.log('ERR dark:', errs.join(' | '));
  await ctx.close();
  await browser.close();
  console.log('done');
})();
