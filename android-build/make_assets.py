# -*- coding: utf-8 -*-
"""把网页面板 panel.html 转成 App 内置页面：
   - fetch 调用换成原生桥（异步回调，界面不卡）
   - 去掉 sessionStorage 依赖（file:// 页面下可能抛 SecurityError，表现为"登录后弹回登录页"）
   - 登录失败/被踢回登录页时自动展开诊断信息
   - 文案改为手机场景
"""
import io
import os
import re

SRC = r"C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/zte-router-lab/panel.html"
DST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "assets", "index.html")

html = io.open(SRC, encoding="utf-8").read()
n_edit = 0


def sub(old, new, why=""):
    global html, n_edit
    assert old in html, "没找到片段，页面结构可能变了：%s / %s" % (why, old[:60])
    html = html.replace(old, new, 1)
    n_edit += 1


# ---------------- 1. fetch → 原生桥 ----------------
OLD_API = """async function api(path, opts) {
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  return { status: r.status, data };
}"""

NEW_API = """// ---------- 原生桥：所有请求走 Android 端 HTTPS，避免 CORS 与跨域 ----------
let __seq = 0;
const __pending = {};
window.__cb = function (id, raw) {
  const fn = __pending[id];
  if (!fn) return;
  delete __pending[id];
  fn(raw);
};
function zcall(method, arg) {
  return new Promise((resolve) => {
    const id = ++__seq;
    __pending[id] = resolve;
    try {
      Z.invoke(id, method, arg === undefined || arg === null ? '' : String(arg));
    } catch (e) {
      delete __pending[id];
      resolve(JSON.stringify({ ok: false, error: '原生调用失败：' + e }));
    }
  });
}
function jparse(s, fb) {
  try { return JSON.parse(s); } catch (e) { return fb; }
}

async function api(path, opts) {
  const o = opts || {};
  let raw = '';
  try {
    if (path === '/api/state') raw = await zcall('state');
    else if (path === '/api/all') raw = await zcall('all');
    else if (path === '/api/net') raw = await zcall('net');
    else if (path === '/api/sysinfo') raw = await zcall('sysinfo');
    else if (path === '/api/logout') raw = await zcall('logout');
    else if (path === '/api/diag') raw = await zcall('diag');
    else if (path === '/api/model') raw = await zcall('model');
    else if (path === '/api/limits') raw = await zcall('limits');
    else if (path.indexOf('/api/sysstat') === 0) raw = await zcall('sysStat');
    else if (path === '/api/ports/raw') raw = await zcall('portsraw');
    else if (path.indexOf('/api/ports') === 0) raw = await zcall('ports');
    else if (path.indexOf('/api/dualwan') === 0) raw = await zcall(o.method === 'POST' ? 'dualwanset' : 'dualwan', o.body || '{}');
    else if (path.indexOf('/api/adminpwd') === 0) raw = await zcall('adminpwd', o.body || '{}');
    else if (path.indexOf('/api/port') === 0) {
      let nm = '';
      (path.split('?')[1] || '').split('&').forEach(function (kv) {
        const p = kv.split('=');
        if (p[0] === 'name') nm = decodeURIComponent(p[1] || '');
      });
      raw = await zcall('port', nm);
    }
    else if (path === '/api/limit') raw = await zcall('setLimit', o.body || '{}');
    else if (path === '/api/security') raw = await zcall('security');
    else if (path === '/api/security/mode') raw = await zcall('securityMode', o.body || '{}');
    else if (path === '/api/security/acl') raw = await zcall('securityAcl', o.body || '{}');
    else if (path === '/api/security/auth') raw = await zcall('securityAuth', o.body || '{}');
    else if (path === '/api/lan') raw = await zcall('lan');
    else if (path === '/api/lan/set') raw = await zcall('lanSet', o.body || '{}');
    else if (path === '/api/bind') raw = await zcall('bind', o.body || '{}');
    else if (path.indexOf('/api/device') === 0) {
      let mac = '';
      (path.split('?')[1] || '').split('&').forEach(function (kv) {
        const p = kv.split('=');
        if (p[0] === 'mac') mac = decodeURIComponent(p[1] || '');
      });
      raw = await zcall('device', mac);
    }
    else if (path === '/api/wifimgr') raw = await zcall('wifimgr');
    else if (path === '/api/optimize') raw = await zcall('optimize');
    else if (path === '/api/netdiag') raw = await zcall('netdiag');
    else if (path === '/api/speedtest') raw = await zcall('speedtest', o.body || '{}');
    else if (path === '/api/speednodes') raw = await zcall('speednodes');
    else if (path === '/api/ont') raw = await zcall('ont', o.body || '{}');
    else if (path === '/api/wifimgr/set') raw = await zcall('wifimgrSet', o.body || '{}');
    else if (path.indexOf('/api/wifi/pwd') === 0) {
      const q = (path.split('?')[1] || '');
      let band = '5G';
      q.split('&').forEach(function (kv) {
        const p = kv.split('=');
        if (p[0] === 'band') band = decodeURIComponent(p[1] || '');
      });
      raw = await zcall('wifiPwd', band);
    } else if (path === '/api/login') {
      const body = jparse(o.body || '{}', {});
      raw = await zcall('login', body.password || '');
    } else if (path === '/api/relogin') {
      raw = await zcall('relogin');
    } else if (path === '/api/wifi') {
      raw = await zcall('saveWifi', o.body || '{}');
    } else if (path === '/api/reboot') {
      raw = await zcall('reboot');
    } else {
      raw = JSON.stringify({ ok: false, error: '未知接口 ' + path });
    }
  } catch (e) {
    raw = JSON.stringify({ ok: false, error: '调用失败：' + e });
  }
  const data = jparse(raw, { ok: false, error: '返回内容无法解析：' + String(raw).slice(0, 120) });
  let status = 200;
  if (data && (data.logged === false || data.error === 'NOT_LOGGED')) status = 401;
  return { status: status, data: data };
}"""
sub(OLD_API, NEW_API, "api()")

# ---------------- 2. 登录流程：不依赖 WebView 存储，出错要说出来 ----------------
sub("""  if (!pwd) return ($('#loginErr').textContent = '请输入管理员密码');
  btn.disabled = true;
  if (txt) txt.textContent = '接管中…';""",
    """  if (btn.disabled) return;   // 防止连点/回车造成两次并发登录互相顶掉会话
  if (!pwd) return ($('#loginErr').textContent = '请输入管理员密码');
  btn.disabled = true;
  if (txt) txt.textContent = '接管中…（最长约 30 秒）';""",
    "doLogin guard")
sub("""    if (!data.ok) {
      $('#loginErr').textContent = data.error || '登录失败';
      return;
    }
    sessionStorage.setItem('zte_pwd', pwd);
    show('main');
    await load();
    loadPortLive(); startPortLive();   // 登录后默认就在概览页，网口实况/实时速率要主动拉一次
    startNetLive();
    const k = data.kicked;
    if (k && (k.ip || k.mac)) {
      toast('已接管管理会话，' + (k.ip || k.mac) + ' 的登录已下线');
    }
  } finally {
    btn.disabled = false;
    if (txt) txt.textContent = '登录';
  }""",
    """    if (!data.ok) {
      $('#loginErr').textContent = data.error || '登录失败';
      showDiag(true);
      return;
    }
    PWD_MEM = pwd;
    show('main');
    await load();
    loadPortLive(); startPortLive();   // 登录后默认就在概览页，网口实况/实时速率要主动拉一次
    startNetLive();
    const k = data.kicked;
    if (k && (k.ip || k.mac)) {
      toast('已接管管理会话，' + (k.ip || k.mac) + ' 的登录已下线');
    }
  } catch (e) {
    $('#loginErr').textContent = '登录出错：' + (e && e.message ? e.message : e);
    showDiag(true);
  } finally {
    btn.disabled = false;
    if (txt) txt.textContent = '登录';
  }""",
    "doLogin")
sub("""    await api('/api/logout', { method: 'POST' });
    sessionStorage.removeItem('zte_pwd');
    if (window.resetNav) window.resetNav();
    show('login');""",
    """    await api('/api/logout', { method: 'POST' });
    PWD_MEM = '';
    if (window.resetNav) window.resetNav();
    show('login');""",
    "logout")
# savedPwd() 在 App 里不读 sessionStorage（file:// 下可能 SecurityError），改读内存
sub("""function savedPwd() {
  try { return sessionStorage.getItem('zte_pwd') || ''; } catch (e) { return ''; }
}""",
    """function savedPwd() {
  return typeof PWD_MEM !== 'undefined' ? PWD_MEM : '';
}""",
    "savedPwd")

# ---------------- 3. 被弹回登录页时给出原因并展开诊断 ----------------
sub("""    if (status === 401 || data.logged === false) {
      // 先试着静默重登；重连中保持当前界面，不弹回登录页
      if (await handleDrop(data)) { return load(true); }
      return;
    }""",
    """    if (status === 401 || data.logged === false) {
      // 先试着静默重登；重连中保持当前界面，不弹回登录页
      if (await handleDrop(data)) { return load(true); }
      showDiag(true);
      return;
    }""",
    "load 401")

# ---------------- 4. 登录页加"诊断信息"入口 ----------------
sub("""    <div class="err" id="loginErr"></div>""",
    """    <div class="err" id="loginErr"></div>
    <button class="btn2" id="btnDiag" style="width:100%;font-size:12.5px;padding:9px;margin-top:2px">连不上？查看诊断信息</button>
    <pre id="diagBox" style="display:none"></pre>""",
    "diagnostics ui")

html = html.replace(
    "密码只发给你家里的路由器，不经过任何服务器。<br>电脑需与本路由处于同一网络。",
    "密码只发给你家里的路由器，不经过任何服务器。<br>手机需连接到该路由的 Wi-Fi。<br>登录后会一直保持登录，直到手动退出。")

# 诊断文本样式
sub("""  .hidden{display:none!important}""",
    """  .hidden{display:none!important}
  /* 远程访问是电脑面板的能力，App 里不显示这张卡 */
  #rmCard{display:none!important}
  #diagBox{
    margin:10px 0 0;padding:10px;border:1px solid var(--line);border-radius:10px;background:#f8fafd;
    font:10.5px/1.55 ui-monospace,Menlo,Consolas,monospace;color:#3b4a5c;white-space:pre-wrap;
    word-break:break-all;max-height:230px;overflow:auto;-webkit-user-select:text;user-select:text;
  }""",
    "diag css")

# 登录页底部加一行路由器地址，点击可修改
old_tip = """    <p class="tip">密码只发给你家里的路由器，不经过任何服务器。<br>登录会自动接管管理会话，其他设备上已登录的管理页会被下线。</p>"""
new_tip = old_tip + """
    <p class="tip host-tip" id="hostTip" style="margin-top:6px">路由器地址 <b id="hostVal">192.168.5.1</b>，点击修改</p>"""
sub(old_tip, new_tip, "host tip")

# ---------------- 4b. 连接设置弹层（局域网 + 外网双地址） ----------------
CONN_SHEET = """
<div class="mask hidden" id="connSheet">
  <div class="sheet">
    <h3>连接设置</h3>
    <p class="sub2">在家连路由器 Wi-Fi 走局域网；在外面自动走远程地址</p>
    <div class="field">
      <label>局域网地址 <button type="button" id="cnUseDef">恢复默认</button></label>
      <input id="cnLocal" placeholder="192.168.5.1" autocomplete="off" spellcheck="false">
    </div>
    <div class="field">
      <label>远程地址（外网）</label>
      <input id="cnRemote" placeholder="例如 abcd-1234.trycloudflare.com" autocomplete="off" spellcheck="false">
    </div>
    <div class="note">远程地址来自电脑端面板「系统设置 → 远程访问」：点一下“开启远程通道”，把生成的地址复制过来粘贴即可。留空则只连局域网。</div>
    <div class="err" id="cnErr"></div>
    <div class="sheet-btns">
      <button class="btn2" id="cnCancel">取消</button>
      <button class="btn2 pri" id="cnSave">保存并重连</button>
    </div>
  </div>
</div>
"""
sub('<div class="toast" id="toast"></div>', CONN_SHEET + '\n<div class="toast" id="toast"></div>', "conn sheet")

CONN_CARD = """    <section class="card">
      <div class="card-h"><h2>连接方式</h2><span class="ext" id="connTag">—</span></div>
      <div class="maint">
        <div class="maint-l"><b id="connHost">—</b><span id="connDesc">正在检测当前网络</span></div>
        <button class="btn2 sm" id="btnConn">设置</button>
      </div>
    </section>

"""
sub('  <div class="page hidden" id="pgSet">\n', '  <div class="page hidden" id="pgSet">\n' + CONN_CARD, "conn card")

# ---------------- 5. 页尾脚本：地址修改 + 诊断 + 兜底错误提示 ----------------
# 注意：panel.html 的 <head> 里还有一段主题引导脚本，所以不能用第一个 </script> 当锚点
TAIL_CODE = """
// ---------- 路由器地址 ----------
var PWD_MEM = '';
(async function () {
  try {
    const st = jparse(await zcall('state'), {});
    if (st && st.host) document.getElementById('hostVal').textContent = st.host;
  } catch (e) {}
  connRefresh();
})();
document.getElementById('hostTip').addEventListener('click', function () { connOpen(); });

// ---------- 连接设置：局域网 + 外网双地址 ----------
var CONN = null;
function connPaint(st) {
  if (!st) return;
  var isRemote = st.kind === 'remote';
  var hv = document.getElementById('hostVal');
  if (hv) hv.textContent = st.host + (st.remote ? (isRemote ? ' · 外网' : ' · 局域网') : '');
  var tag = document.getElementById('connTag');
  if (tag) tag.textContent = !st.remote ? '局域网' : (isRemote ? '外网远程' : '局域网直连');
  var ch = document.getElementById('connHost');
  if (ch) ch.textContent = st.host;
  var cd = document.getElementById('connDesc');
  if (cd) {
    cd.textContent = isRemote
      ? '正在通过外网远程地址访问路由器'
      : (st.remote ? '当前在家中，直连路由器（更省流量）' : '只配置了局域网地址');
  }
}
async function connRefresh() {
  if (typeof zcall !== 'function') return;
  try {
    CONN = jparse(await zcall('conn'), null);
    if (CONN) connPaint(CONN);
  } catch (e) {}
}
function connOpen() {
  if (typeof zcall !== 'function') { toast('网页版地址由电脑端程序决定'); return; }
  var s = CONN || {};
  document.getElementById('cnLocal').value = s.local || '192.168.5.1';
  document.getElementById('cnRemote').value = s.remote || '';
  document.getElementById('cnErr').textContent = '';
  document.getElementById('connSheet').classList.remove('hidden');
}
function connClose() {
  var m = document.getElementById('connSheet');
  if (m) m.classList.add('hidden');
}
document.getElementById('cnCancel').onclick = connClose;
document.getElementById('cnUseDef') && (document.getElementById('cnUseDef').onclick = function () {
  document.getElementById('cnLocal').value = '192.168.5.1';
});
document.getElementById('btnConn') && (document.getElementById('btnConn').onclick = connOpen);
document.getElementById('cnSave').onclick = async function () {
  var lo = (document.getElementById('cnLocal').value || '').trim() || '192.168.5.1';
  var re = (document.getElementById('cnRemote').value || '').trim();
  var err = document.getElementById('cnErr');
  if (re && !/^[A-Za-z0-9.\\-:\\[\\]]+$/.test(re)) { err.textContent = '远程地址只能填域名或 IP，可带端口'; return; }
  var btn = document.getElementById('cnSave');
  btn.disabled = true;
  err.textContent = '正在保存…';
  var r = jparse(await zcall('setConn', JSON.stringify({ local: lo, remote: re })), {});
  btn.disabled = false;
  if (!r || r.ok === false) { err.textContent = (r && r.error) || '保存失败'; return; }
  connPaint(r);
  connClose();
  toast(re ? '已保存，正在选择可用线路…' : '已保存');
  setTimeout(function () { location.reload(); }, 500);
};

// ---------- 诊断 ----------
var DIAG_BUSY = false;
async function showDiag() {
  const box = document.getElementById('diagBox');
  if (!box || DIAG_BUSY) { if (box) box.style.display = 'block'; return; }
  DIAG_BUSY = true;
  box.style.display = 'block';
  box.textContent = '诊断中…';
  try {
    const d = jparse(await zcall('diag'), null);
    if (!d) { box.textContent = '诊断返回异常'; return; }
    const lines = [];
    lines.push('版本 ' + (d.ver || '?') + ' · 地址 ' + d.host + ' · iPhone/安卓 ' + navigator.userAgent.slice(0, 40));
    lines.push('HTTPS ' + (d.reach ? '可达（' + d.httpsStatus + '，' + d.ms + 'ms）' : '不可达') +
               (d.netError ? ' 原因：' + d.netError : ''));
    lines.push('登录令牌 ' + (d.tokenLen ? '已取到 ' + d.tokenLen + ' 位' : '未取到') +
               ' · Cookie ' + d.cookies);
    lines.push('登录态 ' + d.logged + ' · 令牌携带方式 ' + d.mode);
    if (d.lastError) lines.push('最近错误：' + d.lastError);
    lines.push('--- 往返轨迹 ---');
    lines.push(d.trace && d.trace.length ? d.trace : '（无记录，说明登录请求还没走到路由器）');
    box.textContent = lines.join('\\n');
  } catch (e) {
    box.textContent = '诊断失败：' + e;
  } finally {
    DIAG_BUSY = false;
  }
}
document.getElementById('btnDiag').onclick = function () { showDiag(); };

// 任何脚本错误都摆到明面上，别再"静默弹回登录页"
window.onerror = function (m, s, l) {
  const box = document.getElementById('diagBox');
  if (box) {
    box.style.display = 'block';
    box.textContent = '页面脚本错误：' + m + '（第 ' + l + ' 行），请截图反馈';
  }
  return false;
};
window.addEventListener('unhandledrejection', function (e) {
  const box = document.getElementById('diagBox');
  const r = e && e.reason;
  if (box) {
    box.style.display = 'block';
    box.textContent = '未处理的脚本错误：' + (r && r.message ? r.message : r) + '，请截图反馈';
  }
});

"""

_i = html.rfind("</script>")
assert _i > 0, "没找到页尾 </script>"
html = html[: _i] + TAIL_CODE + html[_i:]
n_edit += 1

os.makedirs(os.path.dirname(DST), exist_ok=True)
io.open(DST, "w", encoding="utf-8", newline="\n").write(html)
print("written", DST, len(html), "chars, edits:", n_edit)
print("api 替换成功:", "zcall('all')" in html, "| sessionStorage 残留:", "sessionStorage" in html)
