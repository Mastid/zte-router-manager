# -*- coding: utf-8 -*-
"""去掉温度圆环、CPU/内存指标，概览卡片只保留路由器外观 + 运行状态"""
import io

P = "panel.html"
h = io.open(P, encoding="utf-8").read()

# ---------- 1. HTML：删掉温度环那一列 ----------
OLD_SIDE = '''        <div class="rtx-side">
          <div class="ring-wrap" id="rtxRing" title="点按刷新温度">
            <svg class="ring-svg" viewBox="0 0 90 90">
              <circle class="ring-bg" cx="45" cy="45" r="38"/>
              <circle id="rtRing" class="ring" cx="45" cy="45" r="38" stroke-dasharray="238.8" stroke-dashoffset="238.8"/>
            </svg>
            <div class="ring-c"><b id="tempVal">—</b><i>°C</i></div>
          </div>
          <div class="ring-t" id="tempState">机身温度</div>
        </div>
'''
assert OLD_SIDE in h
h = h.replace(OLD_SIDE, "", 1)

# ---------- 2. HTML：指标行改为状态行 ----------
OLD_M = '''      <div class="rtx-metrics">
        <div><span>CPU 负载</span><b class="num" id="rtCpu">—</b></div>
        <div><span>内存占用</span><b class="num" id="rtMem">—</b></div>
        <div><span>在线设备</span><b class="num" id="rtClients">—</b></div>
      </div>'''
NEW_M = '''      <div class="rtx-foot">
        <span class="badge" id="rtState"><span class="dot"></span>运行中</span>
        <span class="rtx-c"><b class="num" id="rtClients">—</b> 台设备在线</span>
      </div>'''
assert OLD_M in h
h = h.replace(OLD_M, NEW_M, 1)

# ---------- 3. CSS ----------
OLD_CSS = '''  .rtx-body{display:flex;align-items:center;gap:6px;margin-top:1px}
  .rtx-pic{flex:1 1 auto;min-width:0}'''
NEW_CSS = '''  .rtx-body{margin-top:2px}
  .rtx-pic{max-width:302px;margin:0 auto}'''
assert OLD_CSS in h
h = h.replace(OLD_CSS, NEW_CSS, 1)

# 删掉环形与指标样式
import re
start = h.index("  .rtx-side{flex:0 0 106px;text-align:center}")
end = h.index("  /* ---------- 弹层 ---------- */")
NEW_TAIL = '''  .rtx-foot{
    display:flex;align-items:center;justify-content:space-between;gap:10px;
    margin-top:10px;padding-top:11px;border-top:1px solid var(--line);
    font-size:11.5px;color:var(--muted);
  }
  .rtx-foot .badge{font-size:11px}
  .rtx-c b{font-weight:660;color:var(--text);margin-right:2px;font-size:12.5px}

'''
h = h[:start] + NEW_TAIL + h[end:]

# ---------- 4. JS：移除温度逻辑 ----------
js_start = h.index("// ---------- 机身温度")
js_end = h.index("async function load(silent) {")
h = h[:js_start] + h[js_end:]

OLD_LOOP = """    render(data);
    if (Date.now() - tempAt > 25000) loadTemp();"""
NEW_LOOP = "    render(data);"
assert OLD_LOOP in h
h = h.replace(OLD_LOOP, NEW_LOOP, 1)

OLD_R = "$('#btnRefresh').onclick = () => { loadTemp(true); load(); };"
NEW_R = "$('#btnRefresh').onclick = () => load();"
assert OLD_R in h
h = h.replace(OLD_R, NEW_R, 1)

OLD_RING = "$('#rtxRing').onclick = () => loadTemp(true);\n"
assert OLD_RING in h
h = h.replace(OLD_RING, "", 1)

# 设备数只留数字
OLD_C = "  $('#rtClients').textContent = (d.clients || []).length + ' 台';"
NEW_C = "  $('#rtClients').textContent = String((d.clients || []).length);"
assert OLD_C in h
h = h.replace(OLD_C, NEW_C, 1)

io.open(P, "wb").write(h.encode("utf-8"))
print("ok", len(h))
