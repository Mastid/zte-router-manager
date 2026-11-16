const { chromium } = require('playwright');
const path = require('path');
const PREVIEW = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe';
const OUT = path.resolve(__dirname, '../out/shots26');
require('fs').mkdirSync(OUT, { recursive: true });

(async () => {
  const browser = await chromium.launch({ executablePath: EXE });
  for (const [name, vp, mobile] of [['desk', { width: 1440, height: 1000 }, false],
                                    ['mob', { width: 390, height: 844 }, true]]) {
    const ctx = await browser.newContext({ viewport: vp, isMobile: mobile, deviceScaleFactor: mobile ? 2 : 1 });
    const page = await ctx.newPage();

    // 桥接现状（进不去）
    await page.goto(PREVIEW, { waitUntil: 'load' });
    await page.waitForTimeout(300);
    await page.evaluate(async () => { show('main'); await load(); });
    await page.waitForTimeout(600);
    await page.evaluate(() => document.querySelector('[data-tab="set"]').click());
    await page.waitForTimeout(400);
    await page.evaluate(() => document.querySelector('#btnOnt').click());
    await page.waitForTimeout(700);
    await page.evaluate(() => document.querySelector('#ontChips').scrollIntoView({ block: 'center' }));
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(OUT, `${name}-ont-bridge.png`) });

    // 指定地址探测（不可达）
    await page.evaluate(async () => { await loadOnt('192.168.1.1:8080'); });
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(OUT, `${name}-ont-manual.png`) });

    // 深色
    await page.evaluate(() => { document.documentElement.setAttribute('data-theme', 'dark'); if (window.glassRepaint) glassRepaint(); });
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join(OUT, `${name}-ont-dark.png`) });
    await ctx.close();

    // 路由模式可进
    const ctx2 = await browser.newContext({ viewport: vp, isMobile: mobile, deviceScaleFactor: mobile ? 2 : 1 });
    const p2 = await ctx2.newPage();
    await p2.goto(PREVIEW + '?ontok=1', { waitUntil: 'load' });
    await p2.waitForTimeout(300);
    await p2.evaluate(async () => { show('main'); await load(); });
    await p2.waitForTimeout(600);
    await p2.evaluate(() => document.querySelector('[data-tab="set"]').click());
    await p2.waitForTimeout(400);
    await p2.evaluate(() => document.querySelector('#btnOnt').click());
    await p2.waitForTimeout(700);
    await p2.evaluate(() => document.querySelector('#ontInfo').scrollIntoView({ block: 'center' }));
    await p2.waitForTimeout(300);
    await p2.screenshot({ path: path.join(OUT, `${name}-ont-ok.png`) });
    await ctx2.close();
  }
  await browser.close();
  console.log('ok');
})();
