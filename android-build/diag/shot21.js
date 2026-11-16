// 设备图标：按厂家信息自动换品牌图标
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PREVIEW = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe';
const OUT = path.resolve(__dirname, '../out/shots21');
fs.mkdirSync(OUT, { recursive: true });

(async () => {
  const browser = await chromium.launch({ executablePath: EXE });
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push('PAGEERROR ' + e.message));
  await page.goto(PREVIEW, { waitUntil: 'load' });
  await page.waitForTimeout(300);
  await page.evaluate(async () => { show('main'); await load(); });
  await page.waitForTimeout(900);

  await page.evaluate(() => document.getElementById('devList').scrollIntoView());
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(OUT, '01-devs.png') });

  const rows = await page.evaluate(() => [...document.querySelectorAll('#devList .dev')].map((d) => ({
    name: d.querySelector('.n').innerText,
    sub: d.querySelector('.s').innerText.replace(/\n/g, ' '),
    kind: d.querySelector('.av').className,
    svg: !!d.querySelector('.av svg'),
    title: d.querySelector('.av').getAttribute('title') || '',
  })));
  console.log(JSON.stringify(rows, null, 1));

  await page.evaluate(() => document.documentElement.dataset.theme = 'dark');
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(OUT, '02-devs-dark.png') });

  // 详情页头像
  await page.evaluate(() => { document.documentElement.dataset.theme = 'light'; openDev('A4:83:E7:1B:22:90'); });
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(OUT, '03-dev-detail.png') });
  const dv = await page.evaluate(() => ({ cls: document.getElementById('dvAv').className, svg: !!document.querySelector('#dvAv svg') }));
  console.log('detail', JSON.stringify(dv));

  console.log(errs.length ? errs.join('\n') : '无 JS 报错');
  await browser.close();
})();
