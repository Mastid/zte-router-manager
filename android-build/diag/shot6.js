const { chromium } = require('playwright');
const path = require('path');
const OUT = 'C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/shots6';
const PREVIEW = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, colorScheme: 'light',
    isMobile: true, hasTouch: true,
  });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push(String(e)));
  await page.goto(PREVIEW, { waitUntil: 'load' });
  await page.waitForTimeout(300);
  await page.evaluate(async () => { show('main'); await load(); });
  await page.waitForTimeout(500);

  // 模拟：网页占用管理员会话 / App 会话被顶掉
  await page.evaluate(() => {
    window.__origFetch = window.fetch;
    window.fetch = async (u, o) => {
      if (String(u).indexOf('/api/all') === 0) {
        return { status: 401, json: async () => ({ logged: false, error: 'NOT_LOGGED' }) };
      }
      return window.__origFetch(u, o);
    };
    window.zcall = async () => JSON.stringify({
      ok: false, logged: false,
      error: '路由器提示 e_exceed_max_user_preemption（管理员会话被占满/被顶掉）。请确认电脑上的管理页面已关闭',
    });
    RESUME_AT = 0;
  });
  await page.evaluate(() => load());
  await page.waitForTimeout(600);
  console.log('login visible after drop =', await page.evaluate(() => !document.getElementById('viewLogin').classList.contains('hidden')));
  console.log('recon visible =', await page.evaluate(() => document.getElementById('recon').classList.contains('show')));
  console.log('recon text =', await page.evaluate(() => document.getElementById('reconMsg').textContent));
  await page.screenshot({ path: path.join(OUT, '20-recon.png') });

  // 模拟：路由器空闲了，自动重连成功
  await page.evaluate(() => {
    window.fetch = window.__origFetch;
    window.zcall = async () => JSON.stringify({ ok: true, logged: true });
    RESUME_AT = 0;
  });
  await page.evaluate(() => load());
  await page.waitForTimeout(700);
  console.log('recon hidden after resume =', await page.evaluate(() => !document.getElementById('recon').classList.contains('show')));
  await page.screenshot({ path: path.join(OUT, '21-resumed.png') });

  if (errs.length) console.log('ERR:', errs.join(' | '));
  await browser.close();
  console.log('done');
})();
