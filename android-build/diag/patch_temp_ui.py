# -*- coding: utf-8 -*-
"""概览页加入路由器外观图 + 机身温度"""
import io

P = "panel.html"
h = io.open(P, encoding="utf-8").read()

# ---------------- 1. CSS ----------------
CSS_ANCHOR = "  /* ---------- 弹层 ---------- */"
CSS = '''  /* ---------- 路由器外观 + 温度 ---------- */
  :root{
    --rt-hi:#fdfefe; --rt-body:#eef3f9; --rt-ant:#e7eef6; --rt-ant2:#f6fafe;
    --rt-line:#dde5f0; --rt-led:#2fa36b; --rt-shadow:rgba(15,26,38,.10); --rt-brand:#a9b6c4;
  }
  @media (prefers-color-scheme:dark){
    :root{
      --rt-hi:#2c3947; --rt-body:#212c38; --rt-ant:#253140; --rt-ant2:#2f3c4c;
      --rt-line:#31404f; --rt-led:#3ecf8e; --rt-shadow:rgba(0,0,0,.42); --rt-brand:#5d6e81;
    }
  }
  .rtx-body{display:flex;align-items:center;gap:6px;margin-top:1px}
  .rtx-pic{flex:1 1 auto;min-width:0}
  .rt-svg{width:100%;height:auto;display:block}
  .rt-svg .g-hi{stop-color:var(--rt-hi)}
  .rt-svg .g-body{stop-color:var(--rt-body)}
  .rt-svg .g-a1{stop-color:var(--rt-ant2)}
  .rt-svg .g-a2{stop-color:var(--rt-ant)}
  .rt-svg .led{animation:rtblink 3.2s ease-in-out infinite}
  .rt-svg .led2{animation:rtblink 3.2s ease-in-out .5s infinite}
  @keyframes rtblink{0%,100%{opacity:1}55%{opacity:.28}}
  .rtx-side{flex:0 0 106px;text-align:center}
  .ring-wrap{position:relative;width:90px;height:90px;margin:0 auto;cursor:pointer}
  .ring-svg{width:90px;height:90px;display:block;transform:rotate(-90deg)}
  .ring-bg{fill:none;stroke:var(--line);stroke-width:6}
  .ring{fill:none;stroke-width:6;stroke-linecap:round;stroke:var(--brand);
    transition:stroke-dashoffset .55s cubic-bezier(.4,0,.2,1), stroke .3s}
  .ring.lv0{stroke:var(--ok)}
  .ring.lv1{stroke:#d9a13c}
  .ring.lv2{stroke:#dd7a3c}
  .ring.lv3{stroke:var(--err)}
  .ring-c{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}
  .ring-c b{font-size:23px;font-weight:680;letter-spacing:-.7px;line-height:1;font-variant-numeric:tabular-nums}
  .ring-c i{font-style:normal;font-size:10.5px;color:var(--faint);margin-top:2px}
  .ring-t{font-size:10.5px;color:var(--muted);margin-top:6px;white-space:nowrap}
  .rtx-metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:13px;padding-top:12px;border-top:1px solid var(--line)}
  .rtx-metrics div{text-align:center;min-width:0}
  .rtx-metrics span{display:block;font-size:10.5px;color:var(--faint);margin-bottom:2px;white-space:nowrap}
  .rtx-metrics b{display:block;font-size:12.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

'''
assert CSS_ANCHOR in h
h = h.replace(CSS_ANCHOR, CSS + CSS_ANCHOR, 1)

# ---------------- 2. HTML ----------------
HTML_ANCHOR = '  <div class="page" id="pgHome">'
HTML = '''  <div class="page" id="pgHome">
    <section class="card">
      <div class="card-h"><h2>我的路由器</h2><span class="ext" id="rtModel">—</span></div>
      <div class="rtx-body">
        <div class="rtx-pic">
          <svg class="rt-svg" viewBox="0 0 240 152" role="img" aria-label="路由器外观">
            <defs>
              <linearGradient id="rtBodyG" x1="0" y1="0" x2="0" y2="1">
                <stop class="g-hi" offset="0"/>
                <stop class="g-body" offset="1"/>
              </linearGradient>
              <linearGradient id="rtAntG" x1="0" y1="0" x2="0" y2="1">
                <stop class="g-a1" offset="0"/>
                <stop class="g-a2" offset="1"/>
              </linearGradient>
            </defs>
            <ellipse cx="120" cy="138" rx="74" ry="6.5" fill="var(--rt-shadow)"/>
            <g fill="url(#rtAntG)" stroke="var(--rt-line)" stroke-width="1">
              <rect x="49" y="14" width="10" height="70" rx="5" transform="rotate(-13 54 84)"/>
              <rect x="74" y="8" width="10" height="76" rx="5" transform="rotate(-5 79 84)"/>
              <rect x="156" y="8" width="10" height="76" rx="5" transform="rotate(5 161 84)"/>
              <rect x="181" y="14" width="10" height="70" rx="5" transform="rotate(13 186 84)"/>
            </g>
            <rect x="41" y="74" width="158" height="52" rx="15" fill="url(#rtBodyG)" stroke="var(--rt-line)"/>
            <path d="M56 74h128a15 15 0 0 1 15 15v2H41v-2a15 15 0 0 1 15-15z" fill="var(--rt-hi)" opacity=".85"/>
            <text x="120" y="101" text-anchor="middle" font-size="11.5" font-weight="700"
                  letter-spacing="2.2" fill="var(--rt-brand)">ZTE</text>
            <g fill="var(--rt-led)">
              <circle class="led" cx="108" cy="114" r="2.2"/>
              <circle class="led2" cx="120" cy="114" r="2.2"/>
              <circle cx="132" cy="114" r="2.2" opacity=".35"/>
            </g>
            <g stroke="var(--rt-line)" stroke-width="1.6" stroke-linecap="round" opacity=".75">
              <path d="M53 96h9M53 103h9M178 96h9M178 103h9"/>
            </g>
          </svg>
        </div>
        <div class="rtx-side">
          <div class="ring-wrap" id="rtxRing" title="点按刷新温度">
            <svg class="ring-svg" viewBox="0 0 90 90">
              <circle class="ring-bg" cx="45" cy="45" r="38"/>
              <circle id="rtRing" class="ring" cx="45" cy="45" r="38" stroke-dasharray="238.8" stroke-dashoffset="238.8"/>
            </svg>
            <div class="ring-c"><b id="tempVal">—</b><i>°C</i></div>
          </div>
          <div class="ring-t" id="tempState">机身温度</div>
        </div>
      </div>
      <div class="rtx-metrics">
        <div><span>CPU 负载</span><b class="num" id="rtCpu">—</b></div>
        <div><span>内存占用</span><b class="num" id="rtMem">—</b></div>
        <div><span>在线设备</span><b class="num" id="rtClients">—</b></div>
      </div>
    </section>
'''
assert HTML_ANCHOR in h
h = h.replace(HTML_ANCHOR, HTML, 1)

# ---------------- 3. JS：渲染 + 加载 ----------------
JS_ANCHOR = "async function load(silent) {"
JS = '''// ---------- 机身温度（固件不保证暴露，失败时显示「不可读」并可点按重试） ----------
const RING_LEN = 238.8;
let tempAt = 0;

function tempLv(c) { return c < 50 ? 0 : c < 65 ? 1 : c < 78 ? 2 : 3; }
const TEMP_TXT = ['温度正常', '略微偏温', '温度偏高', '温度过热'];

function renderTemp(d) {
  const ring = $('#rtRing');
  const c = d && typeof d.c === 'number' ? d.c : null;
  if (c === null) {
    $('#tempVal').textContent = '—';
    $('#tempState').textContent = (d && d.reason) ? '未提供温度' : '读取中…';
    ring.setAttribute('class', 'ring');
    ring.style.strokeDashoffset = RING_LEN;
  } else {
    const lv = tempLv(c);
    $('#tempVal').textContent = Math.round(c);
    $('#tempState').textContent = TEMP_TXT[lv];
    ring.setAttribute('class', 'ring lv' + lv);
    ring.style.strokeDashoffset = (RING_LEN * (1 - Math.min(c, 100) / 100)).toFixed(1);
  }
  const has = (v) => v !== null && v !== undefined && v !== '';
  $('#rtCpu').textContent = has(d && d.cpu) ? d.cpu + '%' : '—';
  $('#rtMem').textContent = has(d && d.mem) ? d.mem + '%' : '—';
}

async function loadTemp(force) {
  try {
    const { status, data } = await api('/api/temp' + (force ? '?force=1' : ''));
    if (status === 401) return;
    tempAt = Date.now();
    renderTemp(data || {});
  } catch (e) {
    $('#tempState').textContent = '读取失败';
  }
}

'''
assert JS_ANCHOR in h
h = h.replace(JS_ANCHOR, JS + JS_ANCHOR, 1)

# 刷新时同步温度
OLD = """    if (data.error) throw new Error(data.error);
    render(data);"""
NEW = """    if (data.error) throw new Error(data.error);
    render(data);
    if (Date.now() - tempAt > 25000) loadTemp();"""
assert OLD in h
h = h.replace(OLD, NEW, 1)

# 概览卡片里的设备数与型号
OLD2 = """  $('#devName').textContent = d.dev.name;"""
NEW2 = """  $('#devName').textContent = d.dev.name;
  $('#rtModel').textContent = d.dev.model || '—';
  $('#rtClients').textContent = (d.clients || []).length + ' 台';"""
assert OLD2 in h
h = h.replace(OLD2, NEW2, 1)

# 手动刷新按钮 → 强制重读温度
OLD3 = "$('#btnRefresh').onclick = () => load();"
NEW3 = "$('#btnRefresh').onclick = () => { loadTemp(true); load(); };"
assert OLD3 in h
h = h.replace(OLD3, NEW3, 1)

# 点温度环重试
OLD4 = "$('#btnReboot').onclick = reboot;"
NEW4 = """$('#rtxRing').onclick = () => loadTemp(true);
$('#btnReboot').onclick = reboot;"""
assert OLD4 in h
h = h.replace(OLD4, NEW4, 1)

io.open(P, "wb").write(h.encode("utf-8"))
print("ok", len(h))
