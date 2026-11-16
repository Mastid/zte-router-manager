const { chromium } = require('playwright');
const path = require('path');

const OUT = 'C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/shots10';
const PREVIEW = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';

async function open(browser, dark) {
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 }, deviceScaleFactor: 2,
    colorScheme: dark ? 'dark' : 'light', isMobile: true, hasTouch: true,
  });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push(String(e)));
  await page.goto(PREVIEW, { waitUntil: 'load' });
  await page.waitForTimeout(250);
  await page.evaluate(async () => { show('main'); await load(); });
  await page.waitForTimeout(700);
  return { ctx, page, errs };
}

(async () => {
  const browser = await chromium.launch();
  let { ctx, page, errs } = await open(browser, false);

  // 1) 概览：网口显示设备台数
  console.log('ports =', await page.evaluate(() =>
    [...document.querySelectorAll('#portGrid .port')].map((p) =>
      p.dataset.port + ':' + p.querySelector('.p-st').textContent)));
  await page.evaluate(() => document.getElementById('sysCard').scrollIntoView({ block: 'center' }));
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(OUT, '60-ports.png') });

  // 2) 点 LAN3（用户反馈有设备的口）
  await page.evaluate(() => {
    const el = [...document.querySelectorAll('#portGrid .port')].find((p) => p.dataset.port === 'LAN3');
    el.click();
  });
  await page.waitForTimeout(700);
  console.log('lan sheet open =', await page.evaluate(() =>
    !document.getElementById('portSheet').classList.contains('hidden')));
  console.log('lan title =', await page.evaluate(() =>
    document.getElementById('ptName').textContent + ' / ' + document.getElementById('ptBadge').textContent));
  console.log('lan body =', await page.evaluate(() =>
    document.getElementById('ptBody').innerText.replace(/\n/g, ' | ').slice(0, 260)));
  await page.screenshot({ path: path.join(OUT, '61-lan-sheet.png') });

  // 3) 点 WAN 口
  await page.evaluate(() => { closePort(); openPort('WAN'); });
  await page.waitForTimeout(700);
  console.log('wan body =', await page.evaluate(() =>
    document.getElementById('ptBody').innerText.replace(/\n/g, ' | ').slice(0, 300)));
  await page.screenshot({ path: path.join(OUT, '62-wan-sheet.png') });
  if (errs.length) console.log('ERR:', errs.join(' | '));
  await ctx.close();

  // 4) 深色下的 WAN 弹层
  ({ ctx, page, errs } = await open(browser, true));
  await page.evaluate(() => openPort('WAN'));
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(OUT, '63-wan-dark.png') });
  if (errs.length) console.log('ERR dark:', errs.join(' | '));
  await ctx.close();

  await browser.close();
  console.log('done');
})();
