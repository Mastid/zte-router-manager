// v2.5 接管会话：设置卡片新行、登录页说明、顶号提示
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe';
const PAGE = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';
const OUT = path.resolve(__dirname, '../out/shots29');
fs.mkdirSync(OUT, { recursive: true });

async function boot(browser, width, height, isMobile, dark) {
  const ctx = await browser.newContext({ viewport: { width, height }, isMobile: !!isMobile });
  const page = await ctx.newPage();
  await page.goto(PAGE, { waitUntil: 'load' });
  await page.waitForTimeout(300);
  await page.evaluate(async (dark) => {
    if (dark) {
      localStorage.setItem('zte_theme', 'dark');
      document.documentElement.setAttribute('data-theme', 'dark');
    }
    show('main');
    await load();
  }, dark);
  await page.waitForTimeout(700);
  return page;
}

(async () => {
  const browser = await chromium.launch({ executablePath: EXE });

  // 桌面：设置页维护卡
  let page = await boot(browser, 1440, 900, false, false);
  await page.evaluate(() => document.querySelector('[data-tab="set"]').click());
  await page.waitForTimeout(600);
  const card = await page.$('#pgSet section.card:last-of-type');
  await card.scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  await card.screenshot({ path: path.join(OUT, 'desk-maint.png') });
  await page.screenshot({ path: path.join(OUT, 'desk-set.png'), fullPage: true });

  // 点击「重新登录」→ 顶号提示
  await page.evaluate(() => document.querySelector('#btnTakeover').click());
  await page.waitForTimeout(400);
  const toastTxt = await page.evaluate(() => {
    const t = document.querySelector('.toast');
    return t ? t.textContent : '(no toast)';
  });
  console.log('toast:', toastTxt);
  await page.screenshot({ path: path.join(OUT, 'desk-toast.png') });
  await page.context().close();

  // 手机：维护卡
  page = await boot(browser, 390, 844, true, false);
  await page.evaluate(() => document.querySelector('[data-tab="set"]').click());
  await page.waitForTimeout(600);
  const mcard = await page.$('#pgSet section.card:last-of-type');
  await mcard.scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  await mcard.screenshot({ path: path.join(OUT, 'mob-maint.png') });
  await page.evaluate(() => document.querySelector('#btnTakeover').click());
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(OUT, 'mob-toast.png') });
  await page.context().close();

  // 深色：维护卡
  page = await boot(browser, 1440, 900, false, true);
  await page.evaluate(() => document.querySelector('[data-tab="set"]').click());
  await page.waitForTimeout(600);
  const dcard = await page.$('#pgSet section.card:last-of-type');
  await dcard.scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  await dcard.screenshot({ path: path.join(OUT, 'dk-maint.png') });
  await page.context().close();

  // 登录页文案
  page = await boot(browser, 390, 844, true, false);
  await page.evaluate(() => show('login'));
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(OUT, 'mob-login.png') });
  await page.context().close();

  await browser.close();
  console.log('done');
})();
