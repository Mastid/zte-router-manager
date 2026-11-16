const { chromium } = require('playwright');
const path = require('path');
const PREVIEW = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';
const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe';
const OUT = path.resolve(__dirname, '../out/shots-pages');
(async () => {
  const browser = await chromium.launch({ executablePath: EXE });
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push(e.message));
  await page.goto(PREVIEW, { waitUntil: 'load' });
  await page.waitForTimeout(300);
  await page.evaluate(async () => { show('main'); await load(); });
  await page.waitForTimeout(700);
  await page.evaluate(() => document.querySelector('[data-tab="set"]').click());
  await page.waitForTimeout(400);
  // 深色
  await page.evaluate(() => setTheme('dark'));
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(OUT, 'tg-1-dark.png') });
  // 切回浅色（复现用户操作）
  await page.evaluate(() => setTheme('light'));
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(OUT, 'tg-2-light.png') });
  // 校验：卡片标题颜色 & 可见性
  const info = await page.evaluate(() => {
    const h = [...document.querySelectorAll('#pgSet .card-h h2')];
    return h.slice(0, 4).map((el) => {
      const cs = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      return { text: el.textContent.trim(), color: cs.color, w: Math.round(r.width), vis: cs.visibility, disp: cs.display };
    });
  });
  console.log(JSON.stringify(info, null, 1));
  console.log('errors:', errs);
  await browser.close();
})();
