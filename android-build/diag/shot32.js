// v2.8 玻璃视觉：登录页 + 概览（浅/深 × 手机/桌面）
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe';
const OUT = path.resolve(__dirname, '../out/shots32');
fs.mkdirSync(OUT, { recursive: true });
const URL = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';

async function login(page, dark) {
  await page.goto(URL, { waitUntil: 'load' });
  if (dark) {
    await page.evaluate(() => {
      localStorage.setItem('zte_theme', 'dark');
      document.documentElement.setAttribute('data-theme', 'dark');
    });
  }
  await page.waitForTimeout(250);
  await page.evaluate(() => show('login'));
  await page.waitForTimeout(650);
}

async function home(page) {
  await page.evaluate(async () => { show('main'); await load(); });
  await page.waitForTimeout(900);
}

async function boot(page, dark) {
  await page.goto(URL, { waitUntil: 'load' });
  if (dark) {
    await page.evaluate(() => {
      localStorage.setItem('zte_theme', 'dark');
      document.documentElement.setAttribute('data-theme', 'dark');
    });
  }
  await page.waitForTimeout(250);
}

(async () => {
  const browser = await chromium.launch({ executablePath: EXE });

  // 手机浅色
  let page = await (await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true })).newPage();
  await login(page);
  await page.screenshot({ path: path.join(OUT, 'mob-login.png') });
  await boot(page);
  await page.evaluate(() => show('login'));
  await home(page);
  await page.screenshot({ path: path.join(OUT, 'mob-home.png') });
  await page.evaluate(() => window.scrollTo(0, 430));
  await page.waitForTimeout(200);
  await page.screenshot({ path: path.join(OUT, 'mob-home-2.png') });

  // 手机深色
  const dctx = await browser.newContext({
    viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 2, colorScheme: 'dark',
  });
  const dark = await dctx.newPage();
  await login(dark, true);
  await dark.screenshot({ path: path.join(OUT, 'dk-login.png') });
  await home(dark);
  await dark.screenshot({ path: path.join(OUT, 'dk-home.png') });

  // 桌面浅色
  const desk = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await boot(desk);
  await desk.evaluate(async () => { show('main'); await load(); });
  await desk.waitForTimeout(900);
  await desk.screenshot({ path: path.join(OUT, 'desk-home.png') });

  // 桌面深色
  const dd = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark' })).newPage();
  await boot(dd, true);
  await dd.evaluate(async () => { show('main'); await load(); });
  await dd.waitForTimeout(900);
  await dd.screenshot({ path: path.join(OUT, 'desk-home-dark.png') });

  await browser.close();
  console.log('ok', fs.readdirSync(OUT).join(','));
})();
