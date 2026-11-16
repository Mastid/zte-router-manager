# -*- coding: utf-8 -*-
"""panel.html：底部 dock 分页（概览/Wi-Fi/设备/防蹭网/设置）+ 新增两个页面与弹层"""
import io

P = r"C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/zte-router-lab/panel.html"
h = io.open(P, encoding="utf-8").read()

# ---------------- 1. 追加样式 ----------------
CSS = r"""
  /* ---------- 分页 ---------- */
  .wrap{padding-bottom:94px}
  .page{animation:pg .18s ease-out}
  @keyframes pg{from{opacity:.45;transform:translateY(5px)}}

  /* ---------- 底部 dock ---------- */
  .dock{
    position:fixed;bottom:0;left:50%;transform:translateX(-50%);width:100%;max-width:760px;z-index:40;
    display:flex;padding:7px 6px calc(7px + env(safe-area-inset-bottom));
    background:var(--hdr);backdrop-filter:saturate(160%) blur(14px);
    -webkit-backdrop-filter:saturate(160%) blur(14px);border-top:1px solid var(--hdrline);
  }
  .dock button{
    flex:1;display:flex;flex-direction:column;align-items:center;gap:3px;background:none;border:none;
    font:inherit;font-size:10px;color:var(--faint);padding:4px 0 3px;cursor:pointer;border-radius:10px;
  }
  .dock button svg{width:21px;height:21px;stroke:currentColor;fill:none;stroke-width:1.7;
    stroke-linecap:round;stroke-linejoin:round;transition:transform .15s}
  .dock button.on{color:var(--brand)}
  .dock button.on svg{transform:translateY(-1px) scale(1.04)}
  .dock button:active{background:var(--soft)}

  /* ---------- 选项行 ---------- */
  .opt{
    display:flex;align-items:center;gap:11px;padding:11px;margin-bottom:8px;
    border:1px solid var(--line);border-radius:13px;background:var(--soft);cursor:pointer;transition:.15s;
  }
  .opt:last-child{margin-bottom:0}
  .opt.on{border-color:var(--brand);background:var(--brand-soft)}
  .oi{
    width:34px;height:34px;border-radius:11px;display:grid;place-items:center;flex:0 0 auto;
    font-size:14px;font-weight:700;background:var(--card);color:var(--muted);border:1px solid var(--line);
  }
  .opt.on .oi{background:var(--brand);color:#fff;border-color:transparent}
  .ot{flex:1;min-width:0}
  .ot b{display:block;font-size:13px;font-weight:600}
  .ot span{display:block;font-size:11px;color:var(--muted);margin-top:1px;line-height:1.5}
  .tick{font-size:13px;color:var(--brand);font-weight:700;min-width:14px;text-align:right}

  /* ---------- 名单行 ---------- */
  .srow{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--line)}
  .srow:last-child{border-bottom:none;padding-bottom:2px}
  .srow .sm{min-width:0;flex:1}
  .srow .sm b{display:block;font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .srow .sm span{display:block;font-size:10.5px;color:var(--faint);margin-top:2px;letter-spacing:.1px}
  .mini{
    font:inherit;font-size:11.5px;font-weight:600;padding:6px 11px;border-radius:9px;flex:0 0 auto;
    border:1px solid var(--line);background:var(--card);color:var(--brand);cursor:pointer;
  }
  .mini.danger{color:var(--err);border-color:rgba(201,64,63,.3)}
  .mini.ok{color:var(--ok);border-color:rgba(15,138,95,.3)}
  .mini[disabled]{opacity:.5}
  .tagline{display:inline-flex;align-items:center;gap:5px;font-size:11px;color:var(--muted)}

  /* ---------- 表单补充 ---------- */
  select{
    width:100%;font:inherit;padding:12px 14px;border:1px solid var(--line);border-radius:12px;
    background:var(--soft);color:var(--text);appearance:none;outline:none;
  }
  select:focus{border-color:var(--brand)}
  details.adv{margin-top:6px;border-top:1px dashed var(--line);padding-top:10px}
  details.adv summary{font-size:12px;color:var(--muted);cursor:pointer;list-style:none;padding:2px 0}
  details.adv summary::-webkit-details-marker{display:none}
  details.adv summary:before{content:"▸ ";color:var(--faint)}
  details.adv[open] summary:before{content:"▾ "}
"""
anchor = "  .hidden{display:none!important}"
assert anchor in h
h = h.replace(anchor, CSS + anchor, 1)

# ---------------- 2. 主界面改成 5 个页面 + dock ----------------
MAIN = """<!-- 主界面 -->
<div class="wrap hidden" id="viewMain">
  <header>
    <div class="logo">Z</div>
    <div class="h-main">
      <h1 id="devName">连接中…</h1>
      <div class="meta" id="devMeta">—</div>
    </div>
    <div class="icon-btn" id="btnRefresh" title="刷新">
      <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor"><path d="M12 5V2L7 6l5 4V7a5 5 0 11-5 5H5a7 7 0 107-7z"/></svg>
    </div>
  </header>

  <!-- 概览 -->
  <div class="page" id="pgHome">
    <section class="hero">
      <div class="hero-h">
        <span class="hero-t">外网连接</span>
        <span class="badge" id="wanBadge"><span class="dot"></span>已连接</span>
      </div>
      <div class="rates">
        <div class="rate"><div class="k">↓ 下行速率</div><div class="v" id="rateDown">—</div></div>
        <div class="rate"><div class="k">↑ 上行速率</div><div class="v" id="rateUp">—</div></div>
      </div>
      <svg id="wanSpark" viewBox="0 0 300 42" preserveAspectRatio="none" aria-hidden="true"></svg>
      <div class="hero-foot">
        <div><span>WAN IP</span><b class="num" id="wanIp">—</b></div>
        <div><span>拨号方式</span><b id="wanType">—</b></div>
      </div>
    </section>

    <section class="card">
      <div class="card-h"><h2>连接详情</h2><span class="ext" id="runTime">—</span></div>
      <div class="kv">
        <div><div class="k">宽带账号</div><div class="v" id="wanUser">—</div></div>
        <div><div class="k">协商速率</div><div class="v" id="wanSpeed">—</div></div>
        <div><div class="k">局域网网关</div><div class="v num" id="lanIp">—</div></div>
        <div><div class="k">在线时长</div><div class="v" id="wanUptime">—</div></div>
      </div>
    </section>
  </div>

  <!-- Wi-Fi -->
  <div class="page hidden" id="pgWifi">
    <section class="card">
      <div class="card-h"><h2>无线网络</h2><span class="ext" id="wifiCount">—</span></div>
      <div class="wifi-grid" id="wifiGrid"></div>
    </section>
    <div class="note">改名称或密码会让该频段的设备断开，需要用新密码重连；有线连接不受影响。</div>
  </div>

  <!-- 设备 -->
  <div class="page hidden" id="pgDev">
    <section class="card">
      <div class="card-h"><h2>在线设备</h2><span class="ext" id="devCount">—</span></div>
      <div id="devList"></div>
    </section>
    <div class="note">点任意设备可查看实时速率、累计流量并设置限速；右上角的「禁」可直接拉黑。</div>
  </div>

  <!-- 防蹭网 -->
  <div class="page hidden" id="pgSec">
    <section class="card">
      <div class="card-h"><h2>防蹭网模式</h2><span class="ext" id="secModeNow">—</span></div>
      <div id="secModes">
        <div class="opt" data-mode="0">
          <div class="oi">密</div>
          <div class="ot"><b>密码接入</b><span>知道 Wi-Fi 密码即可上网，最省事</span></div>
          <div class="tick"></div>
        </div>
        <div class="opt" data-mode="1">
          <div class="oi">授</div>
          <div class="ot"><b>授权接入</b><span>新设备要你点「允许」才能上网</span></div>
          <div class="tick"></div>
        </div>
        <div class="opt" data-mode="2">
          <div class="oi">白</div>
          <div class="ot"><b>白名单接入</b><span>只有名单里的设备能连，最严格</span></div>
          <div class="tick"></div>
        </div>
      </div>
      <div class="err" id="secTip" style="text-align:left"></div>
    </section>

    <section class="card hidden" id="secPendCard">
      <div class="card-h"><h2>待授权设备</h2><span class="ext" id="secPendCount">—</span></div>
      <div id="secPendList"></div>
    </section>

    <section class="card">
      <div class="card-h"><h2 id="secListTitle">名单</h2><span class="ext" id="secListCount">—</span></div>
      <div id="secRuleList"></div>
      <div class="note" id="secListNote">黑名单里的设备无法连接 Wi-Fi。</div>
    </section>
  </div>

  <!-- 设置 -->
  <div class="page hidden" id="pgSet">
    <section class="card">
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

    <section class="card">
      <div class="card-h"><h2>静态 IP 绑定</h2><span class="ext" id="bindCount">—</span></div>
      <div id="bindList"></div>
      <button class="btn2" id="btnBindAdd" style="width:100%;margin-top:12px">添加绑定</button>
    </section>

    <section class="card">
      <div class="card-h"><h2>路由器维护</h2><span class="ext">谨慎操作</span></div>
      <div class="maint">
        <div class="maint-l">
          <b>重启路由器</b>
          <span>所有设备断网约 1–2 分钟，宽带配置不会丢失</span>
        </div>
        <button class="btn2 danger sm" id="btnReboot">重启</button>
      </div>
    </section>

    <div class="foot" id="foot"></div>
  </div>

  <nav class="dock">
    <button data-tab="home" class="on">
      <svg viewBox="0 0 24 24"><path d="M3.5 10.6 12 3.8l8.5 6.8V20a.8.8 0 0 1-.8.8h-4.4v-6h-6.6v6H4.3a.8.8 0 0 1-.8-.8z"/></svg>
      <span>概览</span>
    </button>
    <button data-tab="wifi">
      <svg viewBox="0 0 24 24"><path d="M2.6 8.6a15 15 0 0 1 18.8 0"/><path d="M5.8 12.2a10 10 0 0 1 12.4 0"/><path d="M9 15.8a5 5 0 0 1 6 0"/><circle cx="12" cy="19" r="1.1" fill="currentColor" stroke="none"/></svg>
      <span>Wi-Fi</span>
    </button>
    <button data-tab="dev">
      <svg viewBox="0 0 24 24"><rect x="3.2" y="4.2" width="11.2" height="9.2" rx="1.6"/><path d="M6.6 19.6h5.2"/><rect x="16.6" y="9.8" width="4.2" height="10" rx="1.4"/></svg>
      <span>设备</span>
    </button>
    <button data-tab="sec">
      <svg viewBox="0 0 24 24"><path d="M12 3.4 19 6v5.6c0 4.3-2.9 7.3-7 9-4.1-1.7-7-4.7-7-9V6z"/><path d="m9.2 12.2 2.1 2.1 3.6-4"/></svg>
      <span>防蹭网</span>
    </button>
    <button data-tab="set">
      <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3.1"/><path d="M12 3.2v2.2M12 18.6v2.2M4.8 12H2.6M21.4 12h-2.2M6.9 6.9 5.3 5.3M18.7 18.7l-1.6-1.6M17.1 6.9l1.6-1.6M5.3 18.7l1.6-1.6"/></svg>
      <span>设置</span>
    </button>
  </nav>
</div>

"""
a = h.index("<!-- 主界面 -->")
b = h.index("<!-- 修改 WiFi -->")
h = h[:a] + MAIN + h[b:]

# ---------------- 3. 设备详情里加「禁止上网 / 固定 IP」 ----------------
old = """    <div class="sheet-btns">
      <button class="btn2" id="dvClose">关闭</button>
      <button class="btn2 pri" id="dvSaveLimit">保存限速</button>
    </div>"""
new = """    <div class="divider"></div>
    <div class="kv2">
      <button class="btn2" id="dvBlock">禁止上网</button>
      <button class="btn2" id="dvBind">固定 IP</button>
    </div>

    <div class="sheet-btns">
      <button class="btn2" id="dvClose">关闭</button>
      <button class="btn2 pri" id="dvSaveLimit">保存限速</button>
    </div>"""
assert old in h
h = h.replace(old, new, 1)

# ---------------- 4. 新增两个弹层 ----------------
SHEETS = """<!-- 局域网设置 -->
<div class="mask hidden" id="lanSheet">
  <div class="sheet">
    <h3>局域网设置</h3>
    <p class="sub2">保存后立即生效，已连接的设备会重新获取地址</p>
    <div class="row" style="padding-top:0">
      <div class="lbl">DHCP 服务<small>自动给设备分配 IP；关闭后需手动配置</small></div>
      <label class="sw"><input type="checkbox" id="lnDhcp"><i></i></label>
    </div>
    <div class="kv2">
      <div class="field"><label>地址池开始</label><input id="lnMin" placeholder="192.168.5.2"></div>
      <div class="field"><label>地址池结束</label><input id="lnMax" placeholder="192.168.5.254"></div>
      <div class="field"><label>首选 DNS</label><input id="lnDns1" placeholder="留空=运营商分配"></div>
      <div class="field"><label>备用 DNS</label><input id="lnDns2" placeholder="可留空"></div>
    </div>
    <div class="field"><label>租期<em style="font-style:normal;color:var(--faint)">　分钟，-1 表示永久</em></label>
      <input id="lnLease" inputmode="numeric" placeholder="120"></div>
    <details class="adv">
      <summary>高级：路由器自身地址</summary>
      <div class="kv2" style="margin-top:10px">
        <div class="field"><label>IP 地址</label><input id="lnIp" placeholder="192.168.5.1"></div>
        <div class="field"><label>子网掩码</label><input id="lnMask" placeholder="255.255.255.0"></div>
      </div>
      <div class="note">改路由器地址会让当前连接立刻断开，之后要用新地址重新打开面板。</div>
    </details>
    <div class="err" id="lnErr"></div>
    <div class="sheet-btns">
      <button class="btn2" id="lnCancel">取消</button>
      <button class="btn2 pri" id="lnSave">保存</button>
    </div>
  </div>
</div>

<!-- 静态绑定 -->
<div class="mask hidden" id="bindSheet">
  <div class="sheet">
    <h3>静态 IP 绑定</h3>
    <p class="sub2">把这台设备的 MAC 固定到一个 IP，重启后也不会变</p>
    <div class="field"><label>选择在线设备</label><select id="bdPick"></select></div>
    <div class="field"><label>设备名称</label><input id="bdName" maxlength="32"></div>
    <div class="field"><label>MAC 地址</label><input id="bdMac" placeholder="AA:BB:CC:DD:EE:FF" autocomplete="off"></div>
    <div class="field"><label>固定 IP</label><input id="bdIp" placeholder="192.168.5.50" autocomplete="off"></div>
    <div class="note">IP 要在局域网网段内，并且落在 DHCP 地址池之外，避免和自动分配撞车。</div>
    <div class="err" id="bdErr"></div>
    <div class="sheet-btns">
      <button class="btn2" id="bdCancel">取消</button>
      <button class="btn2 pri" id="bdSave">保存</button>
    </div>
  </div>
</div>

"""
anchor2 = '<div class="toast" id="toast"></div>'
assert anchor2 in h
h = h.replace(anchor2, SHEETS + anchor2, 1)

io.open(P, "w", encoding="utf-8", newline="\n").write(h)
print("ok", len(h))
