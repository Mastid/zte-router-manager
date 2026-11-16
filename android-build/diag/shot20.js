// 概览页截图（浅色 / 深色），检查去掉 CPU/内存后的排版
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PREVIEW = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe';
const OUT = path.resolve(__dirname, '../out/shots20');
fs.mkdirSync(OUT, { recursive: true });

(async () => {
  const browser = await chromium.launch({ executablePath: EXE });
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 2,
  });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push('PAGEERROR ' + e.message));
  await page.goto(PREVIEW, { waitUntil: 'load' });
  await page.waitForTimeout(300);
  await page.evaluate(async () => { show('main'); await load(); });
  await page.waitForTimeout(1000);

  const shot = async (name, full) => {
    await page.screenshot({ path: path.join(OUT, name), fullPage: !!full });
    console.log('saved', name);
  };

  await shot('01-home.png', true);
  await shot('02-home-top.png', false);

  // 深色
  await page.evaluate(() => { document.documentElement.dataset.theme = 'dark'; });
  await page.waitForTimeout(400);
  await shot('03-home-dark.png', false);

  const info = await page.evaluate(() => ({
    cpu: !!document.getElementById('cpuVal'),
    mem: !!document.getElementById('memVal'),
    note: (document.getElementById('sysNote') || {}).textContent,
    ports: [...document.querySelectorAll('#portGrid .port')].map((p) => p.innerText.replace(/\n/g, ' ')),
    fw: (document.getElementById('rtFw') || {}).textContent,
  }));
  console.log(JSON.stringify(info, null, 1));
  console.log(errs.length ? errs.join('\n') : '无 JS 报错');
  await browser.close();
})();
