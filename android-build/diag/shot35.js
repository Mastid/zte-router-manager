// v2.9.1 验证：dock 选中块滑动 + 扣击涟漪 + 切页淡入
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe';
const OUT = path.resolve(__dirname, '../out/shots35');
fs.mkdirSync(OUT, { recursive: true });
const URL = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';

const probe = () => {
  const dock = document.querySelector('.dock');
  const pill = dock.querySelector('.dock-pill');
  const on = dock.querySelector('button.on');
  const pb = pill.getBoundingClientRect();
  const ob = on.getBoundingClientRect();
  return {
    tab: on.dataset.tab,
    ready: dock.classList.contains('ready'),
    opacity: getComputedStyle(pill).opacity,
    dx: +(pb.left - ob.left).toFixed(1),
    dy: +(pb.top - ob.top).toFixed(1),
    dw: +(pb.width - ob.width).toFixed(1),
    dh: +(pb.height - ob.height).toFixed(1),
    pageAnim: getComputedStyle(document.querySelector('.page:not(.hidden)')).animationName,
  };
};

(async () => {
  const browser = await chromium.launch({ executablePath: EXE });
  const page = await (await browser.newContext({
    viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2,
  })).newPage();
  await page.addInitScript(() => {
    const SAMPLE = { dev: { name: '客厅巡天', model: 'ZXSLC SR7110', fw: 'V1.0.0.4B8.8000', mac: '2C:70:4F:63:73:41', ip: '192.168.5.1' },
      wan: { status: 'Connected', down: '86.42Mbps', up: '12.08Mbps', ip: '112.96.173.204', type: 'PPPoE', user: '0755****8821', uptime: '3 天 7 小时', speed: '1000' },
      wifi: [], clients: [], wired: 0, wireless: 0, count: 0 };
    window.fetch = async function (u) {
      const p = String(u);
      let body = {};
      if (p.indexOf('/api/state') === 0) body = { logged: true, host: '192.168.5.1' };
      else if (p.indexOf('/api/all') === 0) body = SAMPLE;
      else if (p.indexOf('/api/net') === 0) body = { ok: true, status: 'Connected', down: '52.10Mbps', up: '9.30Mbps', speed: '1000', ts: Date.now() };
      else if (p.indexOf('/api/ports') === 0) body = { ok: true, ports: [], wired: { online: 0, total: 0 } };
      else if (p.indexOf('/api/security') === 0) body = { ok: true };
      else if (p.indexOf('/api/lan') === 0) body = { ok: true };
      return { status: 200, json: async () => body };
    };
  });
  await page.goto(URL, { waitUntil: 'load' });
  await page.waitForTimeout(900);

  const home = await page.evaluate(probe);
  console.log('初始:', JSON.stringify(home));
  if (!home.ready) throw new Error('dock 未进入 ready（滑块不会动画）');
  if (Math.abs(home.dx) > 1.5 || Math.abs(home.dy) > 1.5) throw new Error('滑块和当前 tab 没对齐：' + JSON.stringify(home));
  if (Math.abs(home.dw) > 1.5) throw new Error('滑块宽度不等于按钮宽度');
  if (home.opacity !== '1') throw new Error('滑块不可见 opacity=' + home.opacity);
  if (home.pageAnim !== 'pageFade') throw new Error('页面没有淡入动画：' + home.pageAnim);

  // 点「在线设备」：过程中应有涟漪，结束后滑块对齐新按钮
  await page.click('.dock button[data-tab="dev"]');
  const ripple = await page.evaluate(() => document.querySelectorAll('.dock-ripple').length);
  await page.waitForTimeout(140);
  const mid = await page.evaluate(() => {
    const pill = document.querySelector('.dock-pill').getBoundingClientRect();
    return { left: +pill.left.toFixed(1), top: +pill.top.toFixed(1) };
  });
  await page.screenshot({ path: path.join(OUT, 'dock-sliding.png'), clip: { x: 0, y: 700, width: 390, height: 144 } });
  await page.waitForTimeout(560);
  const dev = await page.evaluate(probe);
  console.log('点击后:', JSON.stringify(dev), '| ripple 节点:', ripple);
  if (!ripple) throw new Error('点击没有产生涟漪');
  if (dev.tab !== 'dev') throw new Error('tab 没切到 dev');
  if (Math.abs(dev.dx) > 1.5 || Math.abs(dev.dy) > 1.5) throw new Error('滑块没滑到目标按钮：' + JSON.stringify(dev));
  if (Math.abs(dev.dw) > 1.5) throw new Error('滑动后宽度不匹配');

  // 再点回概览，确认能滑回去
  await page.click('.dock button[data-tab="home"]');
  await page.waitForTimeout(700);
  const back = await page.evaluate(probe);
  console.log('回到概览:', JSON.stringify(back));
  if (back.tab !== 'home' || Math.abs(back.dx) > 1.5) throw new Error('滑块没滑回概览');

  // 宽屏：侧栏纵向也要对齐
  await page.setViewportSize({ width: 1280, height: 860 });
  await page.waitForTimeout(420);
  const wide = await page.evaluate(() => {
    const pill = document.querySelector('.dock-pill').getBoundingClientRect();
    const on = document.querySelector('.dock button.on').getBoundingClientRect();
    return { dx: +(pill.left - on.left).toFixed(1), dy: +(pill.top - on.top).toFixed(1), dw: +(pill.width - on.width).toFixed(1) };
  });
  console.log('宽屏侧栏:', JSON.stringify(wide));
  if (Math.abs(wide.dx) > 1.5 || Math.abs(wide.dy) > 1.5 || Math.abs(wide.dw) > 1.5) {
    throw new Error('宽屏侧栏滑块没对齐：' + JSON.stringify(wide));
  }
  await page.screenshot({ path: path.join(OUT, 'dock-desktop.png') });

  console.log('OK: 滑块滑动/涟漪/淡入/横竖屏对齐 全部通过（中间态 left=' + mid.left + ', top=' + mid.top + '）');
  await browser.close();
})().catch((e) => { console.error('FAIL:', e.message); process.exit(1); });
