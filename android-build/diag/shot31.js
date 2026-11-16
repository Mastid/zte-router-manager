// 截取 v2.7：概览页网口状态+网口实况同屏；设置页两个物理 WAN 口选择
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe';
const OUT = path.resolve(__dirname, '../out/shots31');
fs.mkdirSync(OUT, { recursive: true });
const URL = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';

async function boot(page, tab) {
  await page.goto(URL, { waitUntil: 'load' });
  await page.waitForTimeout(300);
  await page.evaluate(async () => { show('main'); await load(); });
  if (tab) {
    await page.evaluate((t) => go(t), tab);
    await page.waitForTimeout(900);
  }
}

(async () => {
  const browser = await chromium.launch({ executablePath: EXE });

  // 手机浅色 · 概览：网口状态 + 网口实况
  let page = await (await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true })).newPage();
  await boot(page, 'home');
  await page.locator('#sysCard').scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  const home = page.locator('#sysCard, #portLiveCard');
  await page.screenshot({ path: path.join(OUT, 'mob-home-ports.png'), fullPage: false });
  await page.evaluate(() => document.getElementById('portLiveCard').scrollIntoView({ block: 'center' }));
  await page.waitForTimeout(200);
  await page.screenshot({ path: path.join(OUT, 'mob-home-portlive.png') });

  // 手机浅色 · 设置页：物理 WAN 口两口选择
  await boot(page, 'set');
  await page.locator('#dwCard').scrollIntoViewIfNeeded();
  await page.waitForTimeout(200);
  await page.locator('#dwCard').screenshot({ path: path.join(OUT, 'mob-dw2.png') });

  // 选 WAN1=LAN3、WAN2=LAN2 看提示与按钮态
  await page.locator('#dwChips1 .dwchip[data-idx="3"]').click();
  await page.locator('#dwChips2 .dwchip[data-idx="2"]').click();
  await page.waitForTimeout(250);
  await page.locator('#dwCard').screenshot({ path: path.join(OUT, 'mob-dw2-pick.png') });

  // 点被禁用的 chip（WAN2 里的 WAN 口）确认不可选
  const disabled = page.locator('#dwChips2 .dwchip[data-idx="0"]');
  await page.locator('#dwChips2').scrollIntoViewIfNeeded();
  await page.waitForTimeout(150);
  await page.locator('#dwCard').screenshot({ path: path.join(OUT, 'mob-dw2-disabled.png') });

  // 手机深色 · 概览 + 物理口
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
  await dark.evaluate(() => go('home'));
  await dark.waitForTimeout(900);
  await dark.evaluate(() => document.getElementById('portLiveCard').scrollIntoView({ block: 'center' }));
  await dark.waitForTimeout(200);
  await dark.screenshot({ path: path.join(OUT, 'dk-home-portlive.png') });
  await dark.evaluate(() => go('set'));
  await dark.waitForTimeout(900);
  await dark.locator('#dwCard').screenshot({ path: path.join(OUT, 'dk-dw2.png') });

  // 桌面浅色：概览瀑布流（网口状态+实况同列）+ 设置页物理口
  const desk = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await boot(desk, 'home');
  await desk.waitForTimeout(400);
  await desk.screenshot({ path: path.join(OUT, 'desk-home.png') });
  await desk.evaluate(() => go('set'));
  await desk.waitForTimeout(900);
  await desk.locator('#dwCard').scrollIntoViewIfNeeded();
  await desk.waitForTimeout(250);
  await desk.screenshot({ path: path.join(OUT, 'desk-dw2.png') });

  await browser.close();
  console.log('ok', fs.readdirSync(OUT).join(','));
})();
