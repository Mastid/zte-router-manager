// v2.9.0 验证：概览「外网连接」卡是否 1 秒实时刷新（速率变化 + 曲线增长 + 实时指示 + 峰值）
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const EXE = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe';
const OUT = path.resolve(__dirname, '../out/shots34');
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
    let seq = 0;
    window.fetch = async function (u) {
      const p = String(u);
      let body = {};
      if (p.indexOf('/api/state') === 0) body = { logged: true, host: '192.168.5.1' };
      else if (p.indexOf('/api/net') === 0) {
        seq += 1;
        body = { ok: true, status: 'Connected', speed: '1000',
                 down: (40 + seq * 3.5).toFixed(2) + 'Mbps',
                 up: (6 + seq * 0.9).toFixed(2) + 'Mbps', ts: Date.now() };
      } else if (p.indexOf('/api/all') === 0) body = SAMPLE;
      else if (p.indexOf('/api/ports') === 0) body = { ok: true, ports: [], wired: { online: 0, total: 0 } };
      return { status: 200, json: async () => body };
    };
  });
  await page.goto(URL, { waitUntil: 'load' });
  await page.waitForTimeout(1200);

  const first = await page.evaluate(() => ({
    down: document.querySelector('#rateDown').textContent.trim(),
    up: document.querySelector('#rateUp').textContent.trim(),
    live: document.querySelector('#netLive').className,
    liveTxt: document.querySelector('#netLiveTxt').textContent,
    lines: document.querySelectorAll('#wanSpark polyline').length,
    area: document.querySelectorAll('#wanSpark polygon').length,
    peak: document.querySelector('#wanPeak').textContent.trim(),
    win: document.querySelector('#sparkWindow').textContent,
  }));
  await page.waitForTimeout(3200);
  const second = await page.evaluate(() => ({
    down: document.querySelector('#rateDown').textContent.trim(),
    up: document.querySelector('#rateUp').textContent.trim(),
    peak: document.querySelector('#wanPeak').textContent.trim(),
    win: document.querySelector('#sparkWindow').textContent,
    pts: (document.querySelector('#wanSpark polyline') || {})
      .getAttribute ? (document.querySelector('#wanSpark polyline').getAttribute('points') || '').split(' ').length : 0,
  }));

  console.log('T+1.2s:', JSON.stringify(first));
  console.log('T+4.4s:', JSON.stringify(second));

  if (first.down === second.down) throw new Error('速率 3 秒内没有变化，实时轮询没跑起来');
  if (first.lines !== 2 || first.area !== 1) throw new Error('曲线没画出来（polyline=' + first.lines + ' polygon=' + first.area + '）');
  if (/off/.test(first.live)) throw new Error('实时指示处于断开状态');
  if (!/[MG]/.test(first.peak)) throw new Error('峰值没渲染：' + first.peak);
  if (second.pts < 3) throw new Error('曲线采样点太少：' + second.pts);

  await page.evaluate(() => document.querySelector('.hero').scrollIntoView({ block: 'start' }));
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(OUT, 'net-live.png') });
  console.log('OK: 实时刷新生效（' + first.down + ' → ' + second.down + '），曲线点=' + second.pts);
  await browser.close();
})().catch((e) => { console.error('FAIL:', e.message); process.exit(1); });
