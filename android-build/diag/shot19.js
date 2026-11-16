const { chromium } = require('playwright');
const PREVIEW = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';
const OUT = 'C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/shots19';
(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe',
  });
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.goto(PREVIEW, { waitUntil: 'load' });
  await page.waitForTimeout(250);
  await page.evaluate(async () => { show('main'); await load(); });
  await page.waitForTimeout(900);
  const openSheet = async (id) => {
    await page.evaluate((sid) => document.getElementById(sid).classList.remove('hidden'), id);
    await page.waitForTimeout(400);
  };
  // Wi-Fi5 兼容网络
  await page.evaluate(() => go('wifi'));
  await page.waitForTimeout(500);
  await page.evaluate(() => document.querySelector('[data-wm="cp"]').click());
  await page.waitForTimeout(500);
  await page.screenshot({ path: OUT + '/01-cp.png' });
  await page.evaluate(() => document.getElementById('cpClose').click());
  // 定时关闭
  await page.evaluate(() => document.querySelector('[data-wm="tm"]').click());
  await page.waitForTimeout(500);
  await page.screenshot({ path: OUT + '/02-tm.png' });
  await page.evaluate(() => document.getElementById('tmClose').click());
  // 静态 IP 绑定
  await page.evaluate(() => go('sys'));
  await page.waitForTimeout(500);
  await openSheet('bindSheet');
  await page.screenshot({ path: OUT + '/03-bind.png' });
  await page.evaluate(() => document.getElementById('bdCancel').click());
  // 主页整体
  await page.evaluate(() => go('main'));
  await page.waitForTimeout(700);
  await page.screenshot({ path: OUT + '/04-home.png', fullPage: false });
  await browser.close();
  console.log('done');
})();
