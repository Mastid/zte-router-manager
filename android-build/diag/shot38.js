// v2.9.4 网口实况 2 秒刷新验证（后置 mock：覆盖 make_preview 的注入）
const { chromium } = require('playwright');
const path = require('path');
const CHROME = 'C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1134/chrome-win/chrome.exe';
const PREVIEW = 'file:///' + path.resolve(__dirname, '../out/preview.html').replace(/\\/g, '/');

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME });
  const page = await (await browser.newContext({
    viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 2,
  })).newPage();
  await page.goto(PREVIEW, { waitUntil: 'load' });
  await page.waitForTimeout(800);
  // 页面自己的 mock 已就位后再覆盖 fetch：计数 /api/ports，其余透传原 mock
  await page.evaluate(() => {
    const orig = window.fetch;
    window.__portReqs = 0;
    window.__portTimes = [];
    window.fetch = async (u, o) => {
      const url = String(u);
      if (url.includes('/api/ports')) {
        window.__portReqs++;
        window.__portTimes.push(Math.round(performance.now()));
        return { status: 200, ok: true, json: async () => ({
          ok: true, seq: window.__portReqs,
          ports: [
            { name: 'WAN', wan: true, link: true, linkKnown: true, speed: '1000 Mbps', upText: '', downText: '', online: 0, devs: 0 },
            { name: 'LAN1', wan: false, link: true, linkKnown: true, speed: '', max: '最高 2500 Mbps', upText: '', downText: '', online: 1, devs: 1 },
            { name: 'LAN2', wan: false, link: false, linkKnown: true, speed: '', max: '', online: 0, devs: 0 },
            { name: 'LAN3', wan: false, link: true, linkKnown: true, speed: '', max: '最高 1000 Mbps', upText: '', downText: '', online: 0, devs: 0 },
          ], wired: { online: 3, total: 4 } }) };
      }
      return orig(u, o);
    };
  });
  // 重新触发概览页加载（进主界面、切走再切回，保证 startPortLive 用新 fetch）
  await page.evaluate(() => { show('main'); });
  await page.click('.dock button[data-tab="set"]');
  await page.waitForTimeout(300);
  await page.click('.dock button[data-tab="home"]');
  await page.waitForTimeout(5200);
  const reqs = await page.evaluate(() => window.__portReqs || 0);
  const times = await page.evaluate(() => (window.__portTimes || []).join(','));
  console.log('port requests in ~5.2s:', reqs, 'at(ms):', times);
  if (reqs < 3) { console.error('FAIL: 刷新没有加快'); process.exit(1); }
  // 间隔确实 ≈2s（相邻请求差值 <=3s）
  const gaps = await page.evaluate(() => {
    const t = window.__portTimes || [];
    const out = [];
    for (let i = 1; i < t.length; i++) out.push(t[i] - t[i - 1]);
    return out.join(',');
  });
  console.log('gaps(ms):', gaps, '(期望 ≈2000)');
  console.log('PASS: 网口实况 2 秒刷新生效');
  await browser.close();
})().catch((e) => { console.error('FAIL:', e.message); process.exit(1); });
