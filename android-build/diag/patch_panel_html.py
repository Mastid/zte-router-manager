# -*- coding: utf-8 -*-
"""给 panel.html 增加：点设备 → 详情（实时上下行 + 累计流量 + 迷你曲线）+ 单设备限速"""
import io

P = "panel.html"
s = io.open(P, encoding="utf-8").read()

if "dvSpark" in s:
    print("already patched")
    raise SystemExit

def sub(old, new, why):
    global s
    assert old in s, "not found: " + why
    s = s.replace(old, new, 1)

# ---------- 1. 样式 ----------
sub("""  .hidden{display:none!important}""",
    """  .hidden{display:none!important}
  .dev{cursor:pointer;border-radius:10px;transition:background .12s}
  .dev:active{background:#f3f6fb}
  .dev .n em.limtag{
    font-style:normal;font-size:10px;font-weight:600;color:var(--warn);
    background:var(--warn-soft);padding:1px 5px;border-radius:5px;margin-left:5px;vertical-align:1px;
  }
  .chev{color:#c2ccd9;font-size:18px;line-height:1;margin-left:2px;flex:0 0 auto}
  #dvSpark{width:100%;height:66px;display:block;margin:4px 0 8px}
  .info{font-size:11.5px;color:var(--muted)}""",
    "css")

# ---------- 2. 弹层结构 ----------
sub("""<div class="toast" id="toast"></div>""",
    """<!-- 设备详情 / 限速 -->
<div class="mask hidden" id="devSheet">
  <div class="sheet">
    <h3 id="dvName">设备</h3>
    <p class="sub2" id="dvSub">—</p>
    <div class="kv" id="dvKv"></div>

    <div class="rates" style="margin-top:14px">
      <div class="rate"><div class="k">↓ 当前下载</div><div class="v" id="dvDown">—</div></div>
      <div class="rate"><div class="k">↑ 当前上传</div><div class="v" id="dvUp">—</div></div>
    </div>
    <svg id="dvSpark" viewBox="0 0 300 66" preserveAspectRatio="none"></svg>
    <div class="info" id="dvTotal">—</div>

    <div style="border-top:1px solid var(--line);margin:16px 0 12px"></div>
    <div class="card-h"><h2>限速</h2><span class="ext" id="dvLimitNow">—</span></div>
    <div class="field">
      <label>下行上限（Mbps）</label>
      <input type="number" inputmode="decimal" min="0" step="1" id="dvDownLimit" placeholder="0 表示不限">
    </div>
    <div class="field">
      <label>上行上限（Mbps）</label>
      <input type="number" inputmode="decimal" min="0" step="1" id="dvUpLimit" placeholder="0 表示不限">
    </div>
    <div class="note" id="dvNote">填 0 表示不限速；保存后对这台设备立即生效。</div>
    <div class="err" id="dvErr"></div>
    <div class="sheet-btns">
      <button class="btn2" id="dvClose">关闭</button>
      <button class="btn2 pri" id="dvSaveLimit">保存限速</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>""",
    "markup")

# ---------- 3. 设备行可点击 ----------
sub("""    return `<div class="dev">
      <div class="av">${(nm || '?').trim().slice(0, 1).toUpperCase()}</div>
      <div class="dev-main">
        <div class="n">${nm}</div>
        <div class="s">${c.mac} · ${wireless ? '无线' : c.iface || '有线'}</div>
      </div>
      <div class="dev-r">
        <div class="ip num">${c.ip}</div>
        <div class="t">${c.online}</div>
      </div>
    </div>`;
  }).join('')""",
    """    const lim = LIMITS && LIMITS[String(c.mac || '').toUpperCase()];
    return `<div class="dev" data-mac="${c.mac}">
      <div class="av">${(nm || '?').trim().slice(0, 1).toUpperCase()}</div>
      <div class="dev-main">
        <div class="n">${nm}${lim ? ' <em class="limtag">限速</em>' : ''}</div>
        <div class="s">${c.mac} · ${wireless ? '无线' : c.iface || '有线'}</div>
      </div>
      <div class="dev-r">
        <div class="ip num">${c.ip}</div>
        <div class="t">${c.online}</div>
      </div>
      <div class="chev">›</div>
    </div>`;
  }).join('')""",
    "device row")

sub("""  $('#devCount').textContent = d.clients.length + ' 台';""",
    """  $('#devList').querySelectorAll('.dev').forEach((el) => {
    el.onclick = () => openDev(el.dataset.mac);
  });
  $('#devCount').textContent = d.clients.length + ' 台';""",
    "bind row click")

sub("""let LAST = null;
let EDIT_BAND = '2.4G';""",
    """let LAST = null;
let EDIT_BAND = '2.4G';
let LIMITS = null;          // {MAC: {up, down, inst}}
let LIMIT_ENABLE = null;    // 路由器全局 QoS 是否开启
let DEV_MAC = null;
let DEV_TIMER = null;
let DEV_HIST = [];""",
    "state vars")

# ---------- 4. 逻辑 ----------
sub("""async function load(silent) {""",
    """// ---------- 设备详情 / 实时流量 / 限速 ----------
function fmtKbps(k) {
  k = Number(k) || 0;
  if (k <= 0) return '0<small>Kbps</small>';
  if (k < 1000) return Math.round(k) + '<small>Kbps</small>';
  const m = k / 1000;
  return (m >= 100 ? m.toFixed(0) : m.toFixed(1)) + '<small>Mbps</small>';
}

function fmtBytes(b) {
  b = Number(b) || 0;
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
  return (i === 0 ? Math.round(b) : b.toFixed(b >= 100 ? 0 : 1)) + ' ' + u[i];
}

function fmtSpan(sec) {
  sec = Math.max(0, Math.round(Number(sec) || 0));
  const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60);
  if (d) return d + ' 天 ' + h + ' 小时';
  if (h) return h + ' 小时 ' + m + ' 分';
  return m + ' 分钟';
}

function drawSpark() {
  const el = document.getElementById('dvSpark');
  if (!el) return;
  const W = 300, H = 66, PAD = 6;
  if (!DEV_HIST.length) { el.innerHTML = ''; return; }
  let max = 100;
  DEV_HIST.forEach((p) => { max = Math.max(max, p.d, p.u); });
  const n = Math.max(DEV_HIST.length, 2);
  const step = (W - 2) / (n - 1);
  const y = (v) => (H - PAD) - (v / max) * (H - PAD * 2);
  const poly = (key, color, fill) => {
    const pts = DEV_HIST.map((p, i) => (1 + i * step).toFixed(1) + ',' + y(p[key]).toFixed(1)).join(' ');
    let out = `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>`;
    if (fill) {
      const area = `1,${H - PAD} ` + pts + ` ${(1 + (DEV_HIST.length - 1) * step).toFixed(1)},${H - PAD}`;
      out = `<polygon points="${area}" fill="${color}" opacity=".10"/>` + out;
    }
    return out;
  };
  el.innerHTML =
    `<line x1="0" y1="${H - PAD}" x2="${W}" y2="${H - PAD}" stroke="#e6eaf1" stroke-width="1"/>` +
    poly('u', '#0f8a5f', false) + poly('d', '#0b63c5', true);
}

function showLimitNow() {
  const r = LIMITS && LIMITS[String(DEV_MAC || '').toUpperCase()];
  if (r && (r.up || r.down)) {
    $('#dvLimitNow').textContent = '已限速 ↓' + (r.down || 0) + ' / ↑' + (r.up || 0) + ' Mbps';
  } else {
    $('#dvLimitNow').textContent = '未限速';
  }
  if (LIMIT_ENABLE === false) {
    $('#dvNote').textContent = '注意：路由器全局 QoS 未开启，限速规则可能不生效（可在路由器网页端“网络优化/QoS”里打开）。';
  } else {
    $('#dvNote').textContent = '填 0 表示不限速；保存后对这台设备立即生效。';
  }
}

async function loadLimits(force) {
  if (LIMITS && !force) return LIMITS;
  try {
    const { data } = await api('/api/limits');
    if (data && data.ok) {
      LIMITS = data.rules || {};
      LIMIT_ENABLE = !!data.enable;
    } else {
      LIMITS = {};
      LIMIT_ENABLE = null;
    }
  } catch (e) {
    LIMITS = {};
  }
  if (LAST) render(LAST);
  return LIMITS;
}

function openDev(mac) {
  if (!mac) return;
  DEV_MAC = String(mac).toUpperCase();
  DEV_HIST = [];
  const c = (LAST && LAST.clients.find((x) => String(x.mac).toUpperCase() === DEV_MAC)) || {};
  $('#dvName').textContent = c.alias || c.name || DEV_MAC;
  $('#dvSub').textContent = DEV_MAC;
  $('#dvKv').innerHTML = '';
  $('#dvDown').innerHTML = '—';
  $('#dvUp').innerHTML = '—';
  $('#dvTotal').textContent = '读取中…';
  $('#dvSpark').innerHTML = '';
  $('#dvErr').textContent = '';
  $('#dvLimitNow').textContent = '读取中…';
  const r = LIMITS && LIMITS[DEV_MAC];
  $('#dvDownLimit').value = r && r.down ? r.down : '';
  $('#dvUpLimit').value = r && r.up ? r.up : '';
  $('#devSheet').classList.remove('hidden');
  BUSY = true;                     // 详情页打开时暂停列表轮询，别抢同一个会话令牌
  showLimitNow();
  loadLimits(true).then(showLimitNow);
  refreshDev();
  clearInterval(DEV_TIMER);
  DEV_TIMER = setInterval(refreshDev, 3000);
}

function closeDev() {
  clearInterval(DEV_TIMER);
  DEV_TIMER = null;
  DEV_MAC = null;
  $('#devSheet').classList.add('hidden');
  BUSY = false;
}

async function refreshDev() {
  if (!DEV_MAC) return;
  const { data } = await api('/api/device?mac=' + encodeURIComponent(DEV_MAC));
  if (!data || !data.ok) {
    $('#dvTotal').textContent = '读取失败' + (data && data.error ? '：' + data.error : '');
    return;
  }
  $('#dvDown').innerHTML = fmtKbps(data.down);
  $('#dvUp').innerHTML = fmtKbps(data.up);
  $('#dvTotal').textContent = '累计 ↓ ' + fmtBytes(data.rx) + ' · ↑ ' + fmtBytes(data.tx) +
    (data.online ? ' · 在线 ' + fmtSpan(data.online) : '');
  $('#dvKv').innerHTML = [
    ['IP 地址', data.ip || '—'],
    ['接入方式', data.type || '—'],
    ['厂商 / 型号', data.vendor || '—'],
  ].map((kv) => `<div><div class="k">${kv[0]}</div><div class="v">${kv[1]}</div></div>`).join('');
  DEV_HIST.push({ d: Number(data.down) || 0, u: Number(data.up) || 0 });
  if (DEV_HIST.length > 40) DEV_HIST.shift();
  drawSpark();
}

async function saveLimit() {
  if (!DEV_MAC) return;
  const up = Math.max(0, Number($('#dvUpLimit').value || 0));
  const down = Math.max(0, Number($('#dvDownLimit').value || 0));
  if (!isFinite(up) || !isFinite(down)) return ($('#dvErr').textContent = '请填写 0 或正数');
  const name = $('#dvName').textContent;
  const tip = (up || down)
    ? `确认给「${name}」限速？\\n下行 ${down || '不限'} Mbps，上行 ${up || '不限'} Mbps。`
    : `确认取消「${name}」的限速？`;
  if (!confirm(tip)) return;
  const btn = $('#dvSaveLimit');
  btn.disabled = true; btn.textContent = '保存中…';
  $('#dvErr').textContent = '';
  try {
    const { data } = await api('/api/limit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mac: DEV_MAC, up: up, down: down }),
    });
    if (!data || !data.ok) {
      $('#dvErr').textContent = (data && data.error) || '保存失败';
      return;
    }
    toast((up || down) ? '已设置限速' : '已取消限速');
    await loadLimits(true);
    showLimitNow();
  } finally {
    btn.disabled = false; btn.textContent = '保存限速';
  }
}

async function load(silent) {""",
    "device js")

# ---------- 5. 事件绑定 ----------
sub("""$('#sheet').addEventListener('click', (e) => { if (e.target.id === 'sheet') closeEdit(); });""",
    """$('#sheet').addEventListener('click', (e) => { if (e.target.id === 'sheet') closeEdit(); });
$('#dvClose').onclick = closeDev;
$('#dvSaveLimit').onclick = saveLimit;
$('#devSheet').addEventListener('click', (e) => { if (e.target.id === 'devSheet') closeDev(); });""",
    "bind sheet")

open(P, "wb").write(s.encode("utf-8"))
print("patched panel.html", len(s))
