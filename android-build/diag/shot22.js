// v1.27：WiFi5 兼容网络状态/密码 + 网络页黑名单
const { chromium } = require('playwright');
const path = require('path');
const PREVIEW = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe';
const OUT = path.resolve(__dirname, '../out/shots22');
require('fs').mkdirSync(OUT, { recursive: true });
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

  // Wi-Fi 页的兼容网络行
  await page.evaluate(() => { document.querySelector('[data-tab="wifi"]').click(); });
  await page.waitForTimeout(300);
  console.log('wmCp:', await page.evaluate(() => document.getElementById('wmCp').textContent));
  await (await page.$('#pgWifi')).screenshot({ path: path.join(OUT, '01-wifi.png') });

  // 兼容网络弹层
  await page.evaluate(() => { document.querySelector('[data-tab="wifi"]').click(); document.querySelector('[data-wm="cp"]').click(); });
  await page.waitForTimeout(500);
  await (await page.$('#cpSheet .sheet')).screenshot({ path: path.join(OUT, '02-cp-sheet.png') });
  const cp = await page.evaluate(() => ({
    force: document.getElementById('cpForce').checked,
    rows: [...document.querySelectorAll('#cpBody [data-cpband]')].map((el) => ({
      band: el.dataset.cpband,
      st: el.querySelector('.cpst').textContent,
      ssid: el.querySelector('[data-cpssid]').value,
      pwdType: el.querySelector('[data-cppwd]').type,
      pwdLen: el.querySelector('[data-cppwd]').value.length,
    })),
  }));
  console.log('compat:', JSON.stringify(cp));

  // 点显示密码
  await page.evaluate(() => document.querySelector('#cpBody [data-cpshow]').click());
  await page.waitForTimeout(200);
  await (await page.$('#cpSheet .sheet')).screenshot({ path: path.join(OUT, '03-cp-pwd.png') });

  // 网络页黑名单
  await page.evaluate(() => { document.getElementById('cpClose').click(); document.querySelector('[data-tab="net"]').click(); });
  await page.waitForTimeout(1500);
  await page.evaluate(() => document.getElementById('secBanCard').scrollIntoView({ block: 'center' }));
  await page.waitForTimeout(300);
  await (await page.$('#pgNet')).screenshot({ path: path.join(OUT, '04-net.png'), fullPage: true });
  const ban = await page.evaluate(() => ({
    hidden: document.getElementById('secBanCard').classList.contains('hidden'),
    count: document.getElementById('secBanCount').textContent,
    rows: [...document.querySelectorAll('#secBanList .srow')].map((r) => r.innerText.replace(/\n/g, ' | ')),
  }));
  console.log('banned:', JSON.stringify(ban));
  console.log(errs.length ? errs.join('\n') : '无 JS 报错');
  await browser.close();
})();
