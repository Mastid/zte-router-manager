# -*- coding: utf-8 -*-
"""按用户要求重排 dock：概览 / 网络 / WiFi 设置 / 在线设备 / 系统设置"""
import io

P = r"C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/zte-router-lab/panel.html"
h = io.open(P, encoding="utf-8").read()

# 1) pgSec -> pgNet
h = h.replace('<!-- 防蹭网 -->\n  <div class="page hidden" id="pgSec">',
              '<!-- 网络：防蹭网 + 局域网 -->\n  <div class="page hidden" id="pgNet">', 1)
assert 'id="pgNet"' in h

# 2) 局域网卡片从「系统设置」搬到「网络」页
LAN_CARD = """    <section class="card">
      <div class="card-h"><h2>局域网</h2><span class="ext" id="lanState">—</span></div>
      <div class="kv">
        <div><div class="k">路由器地址</div><div class="v num" id="lanIp2">—</div></div>
        <div><div class="k">子网掩码</div><div class="v num" id="lanMask">—</div></div>
        <div><div class="k">DHCP 服务</div><div class="v" id="lanDhcp">—</div></div>
        <div><div class="k">地址池</div><div class="v num" id="lanPool">—</div></div>
        <div><div class="k">DNS</div><div class="v num" id="lanDns">—</div></div>
        <div><div class="k">租期</div><div class="v" id="lanLease">—</div></div>
      </div>
      <button class="btn2" id="btnLanEdit" style="width:100%;margin-top:14px">修改局域网设置</button>
    </section>

"""
assert LAN_CARD in h
h = h.replace(LAN_CARD, "", 1)

# 插到「名单」卡片之后（pgNet 结尾）
old_tail = """      <div class="note" id="secListNote">黑名单里的设备无法连接 Wi-Fi。</div>
    </section>
  </div>"""
new_tail = """      <div class="note" id="secListNote">黑名单里的设备无法连接 Wi-Fi。</div>
    </section>

""" + LAN_CARD + """  </div>"""
assert old_tail in h
h = h.replace(old_tail, new_tail, 1)

# 3) 系统设置页顶部加一段说明，避免只剩两个卡片显得空
old_set = """  <!-- 设置 -->
  <div class="page hidden" id="pgSet">"""
new_set = """  <!-- 系统设置 -->
  <div class="page hidden" id="pgSet">"""
assert old_set in h
h = h.replace(old_set, new_set, 1)

# 4) dock 重排
a = h.index('  <nav class="dock">')
b = h.index('  </nav>') + len('  </nav>')
DOCK = """  <nav class="dock">
    <button data-tab="home" class="on">
      <svg viewBox="0 0 24 24"><path d="M3.5 10.6 12 3.8l8.5 6.8V20a.8.8 0 0 1-.8.8h-4.4v-6h-6.6v6H4.3a.8.8 0 0 1-.8-.8z"/></svg>
      <span>概览</span>
    </button>
    <button data-tab="net">
      <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.6"/><path d="M3.4 12h17.2"/><path d="M12 3.4c2.4 2.4 3.6 5.4 3.6 8.6s-1.2 6.2-3.6 8.6c-2.4-2.4-3.6-5.4-3.6-8.6S9.6 5.8 12 3.4z"/></svg>
      <span>网络</span>
    </button>
    <button data-tab="wifi">
      <svg viewBox="0 0 24 24"><path d="M2.6 8.6a15 15 0 0 1 18.8 0"/><path d="M5.8 12.2a10 10 0 0 1 12.4 0"/><path d="M9 15.8a5 5 0 0 1 6 0"/><circle cx="12" cy="19" r="1.1" fill="currentColor" stroke="none"/></svg>
      <span>WiFi 设置</span>
    </button>
    <button data-tab="dev">
      <svg viewBox="0 0 24 24"><rect x="3.2" y="4.2" width="11.2" height="9.2" rx="1.6"/><path d="M6.6 19.6h5.2"/><rect x="16.6" y="9.8" width="4.2" height="10" rx="1.4"/></svg>
      <span>在线设备</span>
    </button>
    <button data-tab="set">
      <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3.1"/><path d="M12 3.2v2.2M12 18.6v2.2M4.8 12H2.6M21.4 12h-2.2M6.9 6.9 5.3 5.3M18.7 18.7l-1.6-1.6M17.1 6.9l1.6-1.6M5.3 18.7l1.6-1.6"/></svg>
      <span>系统设置</span>
    </button>
  </nav>"""
h = h[:a] + DOCK + h[b:]

# 5) JS：tab 映射与加载
old_js = """const TAB_IDS = { home: 'pgHome', wifi: 'pgWifi', dev: 'pgDev', sec: 'pgSec', set: 'pgSet' };"""
new_js = """const TAB_IDS = { home: 'pgHome', net: 'pgNet', wifi: 'pgWifi', dev: 'pgDev', set: 'pgSet' };"""
assert old_js in h
h = h.replace(old_js, new_js, 1)

old_go = """  if (tab === 'sec') loadSecurity();
  if (tab === 'set') loadLan();"""
new_go = """  if (tab === 'net') { loadSecurity(); loadLan(); }
  if (tab === 'set') loadLan();"""
assert old_go in h
h = h.replace(old_go, new_go, 1)

# 拉黑后跳转的页面
h = h.replace("""    closeDev();
    go('sec');""", """    closeDev();
    go('net');""", 1)

io.open(P, "w", encoding="utf-8", newline="\n").write(h)
print("ok", len(h))
