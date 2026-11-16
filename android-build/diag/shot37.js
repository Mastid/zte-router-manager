// v2.9.3 设置页磁贴布局验证
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const CHROME = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe';
const PREVIEW = 'file:///' + path.resolve(__dirname, '../out/preview.html').replace(/\\/g, '/');
const OUT = path.resolve(__dirname, '../out/shots37');
fs.mkdirSync(OUT, { recursive: true });

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 2,
  });
  const page = await ctx.newPage();
  // 页面脚本运行前就接管 fetch，走真实 init() 冷启动路径
  await page.addInitScript(() => {
    const json = (obj) => Promise.resolve({ status: 200, ok: true, json: async () => obj });
    window.fetch = async (u) => {
      const url = String(u);
      if (url.includes('/api/state')) return json({ logged: true, ok: true });
      if (url.includes('/api/all')) {
        return json({ ok: true, wan: { status: 'connected', down: 2400000, up: 310000, ip: '192.168.5.1', type: 'PPPoE' },
          clients: { online: 13, total: 18 }, wifi: {}, sys: {}, ports: { ok: true, ports: [], wired: { online: 3, total: 4 } },
          dualwan: { ok: true, supported: true, flavor: 'fixed', canSwitch: false,
            wan1: { idx: 0, name: 'WAN', link: true, speed: '1000' },
            wan2: { idx: 1, name: 'LAN1', link: false, enabled: false, status: '未启用', preset: true } },
          rtinfo: { model: '巡天 BE5100 Pro+', fw: 'V1.0.0' } });
      }
      if (url.includes('/api/ports')) return json({ ok: true, ports: [], wired: { online: 3, total: 4 } });
      if (url.includes('/api/net')) return json({ ok: true, status: 'connected', up: 310000, down: 2400000 });
      return json({ ok: true });
    };
  });
  await page.goto(PREVIEW, { waitUntil: 'load' });
  await page.waitForTimeout(900);
  await page.click('.dock button[data-tab="set"]');
  await page.waitForTimeout(700);
  await page.screenshot({ path: OUT + '/set-tiles-light.png' });

  // 暗色
  await page.evaluate(() => { document.documentElement.dataset.theme = 'dark'; });
  await page.waitForTimeout(300);
  await page.screenshot({ path: OUT + '/set-tiles-dark.png' });

  // 磁贴点击 → 测速弹层
  await page.evaluate(() => { document.documentElement.dataset.theme = 'light'; });
  await page.click('#btnSt');
  await page.waitForTimeout(600);
  const sheetOpen = await page.evaluate(() => !document.getElementById('stSheet').classList.contains('hidden'));
  console.log('speedtest sheet opens from tile:', sheetOpen);
  await page.keyboard.press('Escape');
  await page.click('#stClose').catch(() => {});
  await page.waitForTimeout(300);

  // 光猫磁贴滚动
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.click('#tileOnt');
  await page.waitForTimeout(700);
  const scrolled = await page.evaluate(() => window.scrollY > 100);
  console.log('ont tile scrolls to card:', scrolled, 'scrollY=', await page.evaluate(() => window.scrollY));

  // 宽屏（侧栏 dock）两列磁贴
  await page.setViewportSize({ width: 900, height: 800 });
  await page.waitForTimeout(500);
  await page.screenshot({ path: OUT + '/set-tiles-wide.png' });

  console.log('shots ->', OUT);
  await browser.close();
})().catch((e) => { console.error('FAIL:', e.message); process.exit(1); });
