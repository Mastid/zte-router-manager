const { chromium } = require('playwright');
const path = require('path');
const OUT = 'C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/shots11';
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
  await page.waitForTimeout(800);
  return { ctx, page, errs };
}

(async () => {
  const browser = await chromium.launch();
  let { ctx, page, errs } = await open(browser, false);
  console.log('grid =', await page.evaluate(() =>
    [...document.querySelectorAll('#portGrid .port')].map((p) =>
      p.dataset.port + '[fw=' + p.querySelector('.p-nm').textContent + '] ' + p.querySelector('.p-st').textContent)));
  await page.evaluate(() => document.getElementById('sysCard').scrollIntoView({ block: 'center' }));
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(OUT, '70-ports.png') });

  for (const nm of ['LAN1', 'LAN2', 'LAN3']) {
    await page.evaluate((n) => { closePort(); openPort(n); }, nm);
    await page.waitForTimeout(600);
    console.log(nm, '->', await page.evaluate(() =>
      document.getElementById('ptName').textContent + ' / ' + document.getElementById('ptBadge').innerText.trim()
      + ' || ' + document.getElementById('ptBody').innerText.replace(/\n/g, ' | ').slice(0, 200)));
    await page.screenshot({ path: path.join(OUT, '7' + nm.slice(-1) + '-' + nm + '.png') });
  }
  if (errs.length) console.log('ERR:', errs.join(' | '));
  await ctx.close();

  ({ ctx, page, errs } = await open(browser, true));
  await page.evaluate(() => { closePort(); openPort('LAN1'); });
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(OUT, '75-lan1-dark.png') });
  if (errs.length) console.log('ERR dark:', errs.join(' | '));
  await ctx.close();
  await browser.close();
  console.log('done');
})();
