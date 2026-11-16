const { chromium } = require('playwright');
const path = require('path');

const OUT = 'C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/shots8';
const APP = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/app/assets/index.html';
const CONN = { ok: true, local: '192.168.5.1', remote: 'soft-piano-limit-delta.trycloudflare.com', host: '192.168.5.1', kind: 'lan' };

async function open(browser, dark, vp) {
  const ctx = await browser.newContext({
    viewport: vp || { width: 390, height: 844 }, deviceScaleFactor: 2,
    colorScheme: dark ? 'dark' : 'light', isMobile: true, hasTouch: true,
  });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push(String(e)));
  await page.addInitScript((conn) => {
    window.Z = {
      invoke: function (id, m) {
        let body = { ok: true };
        if (m === 'state') body = { logged: false, host: '192.168.5.1', kind: 'lan', remote: conn.remote };
        else if (m === 'conn') body = conn;
        setTimeout(function () { window.__cb(id, JSON.stringify(body)); }, 0);
      },
      sysTheme: function () { return 'light'; },
    };
  }, CONN);
  await page.goto(APP, { waitUntil: 'load' });
  await page.waitForTimeout(700);
  return { page, ctx, errs };
}

(async () => {
  const browser = await chromium.launch();

  let { page, ctx, errs } = await open(browser, false);
  await page.screenshot({ path: path.join(OUT, '40-login-light.png') });
  console.log('mark svg =', await page.evaluate(() => !!document.querySelector('.mark svg')));
  console.log('tip =', await page.evaluate(() => document.querySelector('.login-card .tip').innerText.replace(/\n/g, ' / ')));
  console.log('hostTip =', await page.evaluate(() => (document.getElementById('hostTip') || {}).innerText || 'NONE'));

  // 密码显示/隐藏 + 错误提示
  await page.fill('#pwd', 'admin12345');
  await page.click('#btnEye');
  await page.waitForTimeout(250);
  console.log('type after eye =', await page.getAttribute('#pwd', 'type'), '| eye on =', await page.evaluate(() => document.getElementById('btnEye').classList.contains('on')));
  await page.screenshot({ path: path.join(OUT, '41-login-eye.png') });
  await page.click('#btnEye');
  await page.waitForTimeout(150);

  await page.evaluate(() => { document.getElementById('loginErr').textContent = '密码不正确，可查看路由器背面标签'; });
  await page.waitForTimeout(200);
  await page.screenshot({ path: path.join(OUT, '42-login-err.png') });
  if (errs.length) console.log('ERR:', errs.join(' | '));
  await ctx.close();

  // 深色
  ({ page, ctx, errs } = await open(browser, true));
  await page.fill('#pwd', 'admin12345');
  await page.screenshot({ path: path.join(OUT, '43-login-dark.png') });
  if (errs.length) console.log('ERR dark:', errs.join(' | '));
  await ctx.close();

  // 小屏（iPhone SE 尺寸）检查是否溢出
  ({ page, ctx, errs } = await open(browser, false, { width: 320, height: 568 }));
  const ov = await page.evaluate(() => {
    const c = document.querySelector('.login-card');
    const r = c.getBoundingClientRect();
    return { h: Math.round(r.height), top: Math.round(r.top), bottom: Math.round(r.bottom), vh: window.innerHeight, scroll: document.documentElement.scrollHeight };
  });
  console.log('small screen', JSON.stringify(ov));
  await page.screenshot({ path: path.join(OUT, '44-login-small.png') });
  await ctx.close();

  await browser.close();
  console.log('done');
})();
