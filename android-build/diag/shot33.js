// v2.8.5 修复验证：冷启动（不点任何 tab）网口实况应自动加载，不再卡「读取中」
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe';
const OUT = path.resolve(__dirname, '../out/shots33');
fs.mkdirSync(OUT, { recursive: true });
const URL = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';

(async () => {
  const browser = await chromium.launch({ executablePath: EXE });
  const page = await (await browser.newContext({
    viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 2,
  })).newPage();
  // 在页面脚本执行前就接管 fetch，让 init() 走真实冷启动路径
  await page.addInitScript(() => {
    const SAMPLE = { dev: { name: '客厅巡天', model: 'ZXSLC SR7110', fw: 'V1.0.0.4B8.8000', mac: '2C:70:4F:63:73:41', ip: '192.168.5.1' }, wan: { status: 'Connected', down: '86.42Mbps', up: '12.08Mbps', ip: '112.96.173.204', type: 'PPPoE', user: '0755****8821', uptime: '3 天 7 小时', speed: '1000' }, wired: 4, wireless: 4, count: 8 };
    const PORTS = { ok: true, ports: [
      { name: 'WAN', wan: true, link: true, linkKnown: true, speed: '1000', max: '2500', upText: '', downText: '', online: 0, devs: 0 },
      { name: 'LAN1', wan: false, link: true, linkKnown: true, speed: '', max: '2500', upText: '1.2 KB/s', downText: '34.6 KB/s', online: 1, devs: 2 },
      { name: 'LAN2', wan: false, link: false, linkKnown: true, speed: '', max: '1000', online: 0, devs: 0 },
      { name: 'LAN3', wan: false, link: true, linkKnown: true, speed: '', max: '1000', upText: '', downText: '', online: 0, devs: 1 }
    ], wired: { online: 2, total: 4 } };
    window.fetch = async function (u) {
      const p = String(u);
      let body = {};
      if (p.indexOf('/api/state') === 0) body = { logged: true, host: '192.168.5.1' };
      else if (p.indexOf('/api/all') === 0) body = SAMPLE;
      else if (p.indexOf('/api/ports') === 0) body = PORTS;
      return { status: 200, json: async () => body };
    };
  });
  await page.goto(URL, { waitUntil: 'load' });
  await page.waitForTimeout(1800);
  const res = await page.evaluate(() => ({
    mainShown: !document.querySelector('#viewMain').classList.contains('hidden'),
    plTag: document.querySelector('#plTag').textContent,
    rows: document.querySelectorAll('#plList .prow').length,
    stuck: document.querySelector('#plList').textContent.includes('读取中'),
    firstRow: (document.querySelector('#plList .prow .pnm') || {}).textContent || '',
  }));
  console.log(JSON.stringify(res, null, 2));
  if (!res.mainShown) throw new Error('main 视图没显示');
  if (res.stuck || res.rows === 0) throw new Error('网口实况仍卡在读取中/没有渲染端口行');
  await page.evaluate(() => document.querySelector('#portLiveCard').scrollIntoView({ block: 'center' }));
  await page.waitForTimeout(250);
  await page.screenshot({ path: path.join(OUT, 'cold-start-ports.png') });
  console.log('OK: 冷启动网口实况自动加载，端口行数=' + res.rows + '，角标=' + res.plTag);
  await browser.close();
})().catch((e) => { console.error('FAIL:', e.message); process.exit(1); });
