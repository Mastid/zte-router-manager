const { chromium } = require('playwright');
const path = require('path');
const PREVIEW = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe';
const OUT = path.resolve(__dirname, '../out/shots25');
require('fs').mkdirSync(OUT, { recursive: true });
(async () => {
  const browser = await chromium.launch({ executablePath: EXE });
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push(e.message));
  await page.goto(PREVIEW, { waitUntil: 'load' });
  await page.waitForTimeout(300);
  await page.evaluate(async () => { show('main'); await load(); document.querySelector('[data-tab="set"]').click(); });
  await page.waitForTimeout(700);
  // 测速弹层：节点下拉
  await page.evaluate(() => document.getElementById('btnSt').click());
  await page.waitForTimeout(900);
  await page.screenshot({ path: path.join(OUT, '01-speed-nodes.png') });
  const opts = await page.evaluate(() => [...document.querySelectorAll('#stNodeSel option')].map((o) => o.textContent));
  console.log('options:', JSON.stringify(opts));
  // 选一个节点测速
  await page.selectOption('#stNodeSel', 'ustc');
  await page.evaluate(() => document.getElementById('stGo').click());
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(OUT, '02-speed-done.png') });
  const kv = await page.evaluate(() => document.querySelector('#stBody').innerText.replace(/\n/g, ' | '));
  console.log('result:', kv);
  // 关闭弹层，光猫卡片
  await page.evaluate(() => document.getElementById('stClose').click());
  await page.waitForTimeout(200);
  await page.evaluate(() => document.getElementById('btnOnt').click());
  await page.waitForTimeout(900);
  await page.evaluate(() => document.querySelector('#ontInfo').scrollIntoView({ block: 'center' }));
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(OUT, '03-ont.png') });
  const ont = await page.evaluate(() => document.querySelector('#pgSet').innerText.match(/上级光猫[\s\S]{0,220}/)[0]);
  console.log('ont:', ont.replace(/\n/g, ' | '));
  console.log('errors:', errs);
  await browser.close();
})();
