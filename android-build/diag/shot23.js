// v1.28：兼容网络密码懒加载 + 黑名单策略兜底
const { chromium } = require('playwright');
const path = require('path');
const PREVIEW = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe';
const OUT = path.resolve(__dirname, '../out/shots23');
require('fs').mkdirSync(OUT, { recursive: true });
(async () => {
  const browser = await chromium.launch({ executablePath: EXE });
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push('PAGEERROR ' + e.message));
  await page.goto(PREVIEW, { waitUntil: 'load' });
  await page.waitForTimeout(300);
  await page.evaluate(async () => { show('main'); await load(); document.querySelector('[data-tab="wifi"]').click(); });
  await page.waitForTimeout(600);

  await page.evaluate(() => document.querySelector('[data-wm="cp"]').click());
  await page.waitForTimeout(1200);
  await (await page.$('#cpSheet .sheet')).screenshot({ path: path.join(OUT, '01-cp-sheet.png') });
  const cp = await page.evaluate(() => [...document.querySelectorAll('#cpBody [data-cpband]')].map((el) => ({
    band: el.dataset.cpband,
    st: el.querySelector('.cpst').textContent,
    ssid: el.querySelector('[data-cpssid]').value,
    pwdType: el.querySelector('[data-cppwd]').type,
    pwd: el.querySelector('[data-cppwd]').value,
    tip: el.querySelector('.cp-tip').textContent,
  })));
  console.log('compat:', JSON.stringify(cp, null, 1));

  await page.evaluate(() => document.querySelector('#cpBody [data-cpshow]').click());
  await page.waitForTimeout(200);
  await (await page.$('#cpSheet .sheet')).screenshot({ path: path.join(OUT, '02-cp-plain.png') });

  await page.evaluate(() => { document.getElementById('cpClose').click(); document.querySelector('[data-tab="net"]').click(); });
  await page.waitForTimeout(1500);
  const sec = await page.evaluate(() => ({
    mode: (typeof SEC !== 'undefined' && SEC) ? SEC.mode : null,
    title: document.getElementById('secListTitle').textContent,
    count: document.getElementById('secListCount').textContent,
    rows: [...document.querySelectorAll('#secRuleList .srow')].map((r) => r.innerText.replace(/\n/g, ' | ')),
    banShown: !document.getElementById('secBanCard').classList.contains('hidden'),
    banCount: document.getElementById('secBanCount').textContent,
    banRows: [...document.querySelectorAll('#secBanList .srow')].map((r) => r.innerText.replace(/\n/g, ' | ')),
  }));
  console.log('security:', JSON.stringify(sec, null, 1));
  await page.evaluate(() => document.getElementById('secListTitle').scrollIntoView({ block: 'center' }));
  await page.waitForTimeout(300);
  await (await page.$('#pgNet')).screenshot({ path: path.join(OUT, '03-net-list.png'), fullPage: true });

  await page.evaluate(() => document.documentElement.dataset.theme = 'dark');
  await page.waitForTimeout(300);
  await page.evaluate(() => document.querySelector('[data-tab="wifi"]').click());
  await page.waitForTimeout(400);
  await page.evaluate(() => document.querySelector('[data-wm="cp"]').click());
  await page.waitForTimeout(1200);
  await (await page.$('#cpSheet .sheet')).screenshot({ path: path.join(OUT, '04-cp-dark.png') });

  console.log(errs.length ? errs.join('\n') : '无 JS 报错');
  await browser.close();
})();
