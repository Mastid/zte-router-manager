const { chromium } = require('playwright');
const path = require('path');

const OUT = 'C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/shots7';
const APP = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/app/assets/index.html';
const PREVIEW = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';

const CONN = { ok: true, local: '192.168.5.1', remote: 'soft-piano-limit-delta.trycloudflare.com', host: '192.168.5.1', kind: 'lan' };

async function appPage(browser, dark) {
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 }, deviceScaleFactor: 2,
    colorScheme: dark ? 'dark' : 'light', isMobile: true, hasTouch: true,
  });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push(String(e)));
  await page.addInitScript((conn) => {
    window.Z = {
      invoke: function (id, m, a) {
        let body = { ok: true };
        if (m === 'state') body = { logged: false, host: '192.168.5.1', kind: 'lan', remote: conn.remote };
        else if (m === 'conn') body = conn;
        setTimeout(function () { window.__cb(id, JSON.stringify(body)); }, 0);
      },
      sysTheme: function () { return 'light'; },
    };
  }, CONN);
  await page.goto(APP, { waitUntil: 'load' });
  await page.waitForTimeout(500);
  return { page, errs };
}

(async () => {
  const browser = await chromium.launch();

  // 1) 登录页（带地址行）
  let { page, errs } = await appPage(browser, false);
  await page.screenshot({ path: path.join(OUT, '30-login.png') });
  console.log('login hostVal =', await page.evaluate(() => document.getElementById('hostVal').textContent));

  // 2) 连接设置弹层
  await page.evaluate(() => document.getElementById('hostTip').click());
  await page.waitForTimeout(500);
  console.log('sheet open =', await page.evaluate(() => !document.getElementById('connSheet').classList.contains('hidden')));
  console.log('local =', await page.inputValue('#cnLocal'), '| remote =', await page.inputValue('#cnRemote'));
  await page.screenshot({ path: path.join(OUT, '31-conn-sheet.png') });
  if (errs.length) console.log('ERR login:', errs.join(' | '));
  await page.context().close();

  // 3) 深色下的连接设置
  ({ page, errs } = await appPage(browser, true));
  await page.waitForTimeout(300);
  await page.evaluate(() => document.getElementById('connSheet').classList.remove('hidden'));
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(OUT, '32-conn-dark.png') });
  if (errs.length) console.log('ERR dark:', errs.join(' | '));
  await page.context().close();

  // 4) 电脑面板的系统设置页（远程访问卡片）
  const ctx = await browser.newContext({ viewport: { width: 430, height: 932 }, deviceScaleFactor: 2 });
  const p2 = await ctx.newPage();
  const e2 = [];
  p2.on('pageerror', (e) => e2.push(String(e)));
  await p2.goto(PREVIEW, { waitUntil: 'load' });
  await p2.waitForTimeout(300);
  await p2.evaluate(async () => { show('main'); await load(); });
  await p2.waitForTimeout(400);
  await p2.evaluate(() => { document.querySelector('[data-tab="set"]').click(); });
  await p2.waitForTimeout(900);
  console.log('rm tag =', await p2.evaluate(() => document.getElementById('rmTag').textContent));
  console.log('rm info =', await p2.evaluate(() => document.getElementById('rmInfo').innerText.replace(/\n/g, ' / ')));
  await p2.evaluate(() => document.getElementById('rmCard').scrollIntoView({ block: 'center' }));
  await p2.waitForTimeout(200);
  await p2.screenshot({ path: path.join(OUT, '33-remote-card.png') });
  if (e2.length) console.log('ERR panel:', e2.join(' | '));
  await ctx.close();

  await browser.close();
  console.log('done');
})();
