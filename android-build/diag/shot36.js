// v2.9.2 验证：「物理 WAN 口」卡应显示 WAN1（固定）+ WAN2（WAN1 旁边的网口），不再给自由选口
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe';
const OUT = path.resolve(__dirname, '../out/shots36');
fs.mkdirSync(OUT, { recursive: true });
const URL = 'file:///C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html';

(async () => {
  const browser = await chromium.launch({ executablePath: EXE });
  const page = await (await browser.newContext({
    viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 2,
  })).newPage();
  await page.addInitScript(() => {
    const SAMPLE = { dev: { name: '客厅巡天', model: 'ZXSLC SR7110', fw: 'V1.0.0.4B8.8000', mac: '2C:70:4F:63:73:41', ip: '192.168.5.1' },
      wan: { status: 'Connected', down: '86.42Mbps', up: '12.08Mbps', ip: '112.96.173.204', type: 'PPPoE', user: '0755****8821', uptime: '3 天 7 小时', speed: '1000' },
      wifi: [], clients: [], wired: 0, wireless: 0, count: 0 };
    const DW = { ok: true, supported: true, flavor: 'fixed', canSwitch: false,
      wan1: { idx: 0, name: 'WAN', link: true, speed: '1000', max: '2500', locked: true },
      wan2: { idx: 1, name: 'LAN1', link: true, speed: '', max: '2500', enabled: false, preset: true, locked: true, status: '未启用', type: '', ip: '' },
      loadBalance: { enabled: false, wan1: '1', wan2: '1' }, failover: false,
      note: '这台机器的物理 WAN 只有一个（WAN1），WAN2 是把 WAN1 旁边那个网口切过去当第二个 WAN 用。',
      ports: [] };
    window.fetch = async function (u) {
      const p = String(u);
      let body = {};
      if (p.indexOf('/api/state') === 0) body = { logged: true, host: '192.168.5.1' };
      else if (p.indexOf('/api/all') === 0) body = SAMPLE;
      else if (p.indexOf('/api/net') === 0) body = { ok: true, status: 'Connected', down: '52.10Mbps', up: '9.30Mbps', speed: '1000', ts: Date.now() };
      else if (p.indexOf('/api/dualwan') === 0) body = DW;
      else if (p.indexOf('/api/ports') === 0) body = { ok: true, ports: [], wired: { online: 0, total: 0 } };
      else if (p.indexOf('/api/lan') === 0) body = { ok: true };
      return { status: 200, json: async () => body };
    };
  });
  await page.goto(URL, { waitUntil: 'load' });
  await page.waitForTimeout(600);
  await page.click('.dock button[data-tab="set"]');
  await page.waitForTimeout(900);

  const r = await page.evaluate(() => {
    const card = document.querySelector('#dwCard');
    const chipsHidden = document.querySelector('#dwChips1').parentElement.classList.contains('hidden');
    const btnHidden = document.querySelector('#btnDwApply').classList.contains('hidden');
    return {
      tag: document.querySelector('#dwTag').textContent.trim(),
      rows: card.querySelectorAll('.dwrow').length,
      text: (document.querySelector('#dwBody').textContent || '').replace(/\s+/g, ' ').trim().slice(0, 220),
      chips: document.querySelectorAll('#dwChips1 .dwchip').length,
      chipsHidden, btnHidden,
      tip: document.querySelector('#dwTip').textContent.trim().slice(0, 80),
    };
  });
  console.log(JSON.stringify(r, null, 2));
  if (r.chipsHidden !== true || r.btnHidden !== true) throw new Error('固定形态下不应出现选口区/应用按钮');
  if (r.chips !== 0) throw new Error('仍渲染了选口 chips');
  if (r.rows !== 2) throw new Error('应正好两行（WAN1 / WAN2），实际 ' + r.rows);
  if (!/WAN1/.test(r.text) || !/WAN2/.test(r.text)) throw new Error('WAN1/WAN2 行没渲染');
  if (!/WAN1 旁边/.test(r.text)) throw new Error('WAN2 没标注「WAN1 旁边」');

  await page.evaluate(() => document.querySelector('#dwCard').scrollIntoView({ block: 'center' }));
  await page.waitForTimeout(260);
  await page.screenshot({ path: path.join(OUT, 'dw-card.png') });
  console.log('OK: 固定形态渲染正确（两行 + 无选口区）');
  await browser.close();
})().catch((e) => { console.error('FAIL:', e.message); process.exit(1); });
