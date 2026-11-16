// 截取「网口实况」「双 WAN」「修改管理员密码」三块新界面
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe';
const OUT = path.resolve(__dirname, '../out/shots30');
fs.mkdirSync(OUT, { recursive: true });
const URL = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';

async function boot(page) {
  await page.goto(URL, { waitUntil: 'load' });
  await page.waitForTimeout(300);
  await page.evaluate(async () => { show('main'); await load(); });
  await page.evaluate(() => document.querySelector('[data-tab="set"]').click());
  await page.waitForTimeout(900);
}

(async () => {
  const browser = await chromium.launch({ executablePath: EXE });

  // 手机浅色
  let page = await (await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true })).newPage();
  await boot(page);
  const cards = page.locator('#portLiveCard');
  await cards.scrollIntoViewIfNeeded();
  await page.waitForTimeout(200);
  await cards.screenshot({ path: path.join(OUT, 'mob-ports.png') });
  await page.locator('#dwCard').screenshot({ path: path.join(OUT, 'mob-dualwan.png') });

  // 点选一个备用口，看提示与按钮态
  await page.locator('#dwChips .dwchip[data-idx="3"]').click();
  await page.waitForTimeout(250);
  await page.locator('#dwCard').screenshot({ path: path.join(OUT, 'mob-dualwan-pick.png') });

  // 改密弹层
  await page.locator('#dwCard').scrollIntoViewIfNeeded();
  await page.evaluate(() => openAdmPwd());
  await page.waitForTimeout(350);
  await page.screenshot({ path: path.join(OUT, 'mob-pwd-sheet.png') });
  await page.evaluate(() => { $('#apOld').value = 'oldpass'; $('#apNew').value = 'abc'; $('#apNew2').value = 'abc'; });
  await page.evaluate(() => submitAdmPwd());
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(OUT, 'mob-pwd-err.png') });

  // 深色
  const dctx = await browser.newContext({
    viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 2, colorScheme: 'dark',
  });
  const dark = await dctx.newPage();
  await dark.goto(URL, { waitUntil: 'load' });
  await dark.evaluate(() => {
    localStorage.setItem('zte_theme', 'dark');
    document.documentElement.setAttribute('data-theme', 'dark');
  });
  await dark.waitForTimeout(200);
  await dark.evaluate(async () => { show('main'); await load(); });
  await dark.evaluate(() => document.querySelector('[data-tab="set"]').click());
  await dark.waitForTimeout(900);
  await dark.locator('#portLiveCard').screenshot({ path: path.join(OUT, 'dk-ports.png') });
  await dark.locator('#dwCard').screenshot({ path: path.join(OUT, 'dk-dualwan.png') });

  // 桌面双列
  const desk = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await boot(desk);
  await desk.locator('#portLiveCard').scrollIntoViewIfNeeded();
  await desk.waitForTimeout(250);
  await desk.screenshot({ path: path.join(OUT, 'desk-set.png'), fullPage: true });

  await browser.close();
  console.log('ok', fs.readdirSync(OUT).join(','));
})();
