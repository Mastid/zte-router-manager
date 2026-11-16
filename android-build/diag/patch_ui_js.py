# -*- coding: utf-8 -*-
"""panel.html：分页切换 + 防蹭网 + 网络设置的交互逻辑"""
import io

P = r"C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/zte-router-lab/panel.html"
h = io.open(P, encoding="utf-8").read()

JS = r"""
// ================= 分页（底部 dock） =================
let TAB = 'home';
const TAB_IDS = { home: 'pgHome', wifi: 'pgWifi', dev: 'pgDev', sec: 'pgSec', set: 'pgSet' };

function go(tab) {
  if (!TAB_IDS[tab]) tab = 'home';
  TAB = tab;
  Object.keys(TAB_IDS).forEach((k) => {
    const el = document.getElementById(TAB_IDS[k]);
    if (el) el.classList.toggle('hidden', k !== tab);
  });
  document.querySelectorAll('.dock button').forEach((b) => {
    b.classList.toggle('on', b.dataset.tab === tab);
  });
  window.scrollTo({ top: 0, behavior: 'smooth' });
  if (tab === 'sec') loadSecurity();
  if (tab === 'set') loadLan();
}
document.querySelectorAll('.dock button').forEach((b) => {
  b.onclick = () => go(b.dataset.tab);
});

// ================= 防蹭网 =================
let SEC = null;

async function loadSecurity() {
  $('#secTip').textContent = '';
  try {
    const { status, data } = await api('/api/security');
    if (status === 401 || (data && data.logged === false)) { show('login'); return; }
    if (!data || !data.ok) { $('#secTip').textContent = (data && data.error) || '读取失败'; return; }
    SEC = data;
    renderSec(data);
  } catch (e) {
    $('#secTip').textContent = '读取失败：' + (e && e.message ? e.message : e);
  }
}

function renderSec(d) {
  const mode = Number(d.mode) || 0;
  $('#secModeNow').textContent = d.modeName || '';
  document.querySelectorAll('#secModes .opt').forEach((el) => {
    const on = Number(el.dataset.mode) === mode;
    el.classList.toggle('on', on);
    el.querySelector('.tick').textContent = on ? '✓' : '';
  });

  const pend = d.pending || [];
  $('#secPendCard').classList.toggle('hidden', mode !== 1);
  $('#secPendCount').textContent = pend.length ? pend.length + ' 台' : '无';
  $('#secPendList').innerHTML = pend.length ? pend.map((p) => `
    <div class="srow">
      <div class="sm"><b>${p.name || '未知设备'}</b><span>${p.mac}${p.time ? ' · ' + p.time : ''}</span></div>
      <button class="mini ok" data-act="allow" data-inst="${p.inst}">允许</button>
      <button class="mini danger" data-act="deny" data-inst="${p.inst}">拒绝</button>
    </div>`).join('') : '<div class="empty">暂无待授权设备</div>';

  const allow = d.allowed || [];
  const rules = d.rules || [];
  const isWhite = mode === 2;
  const rows = mode === 1 ? allow : rules.filter((r) => (isWhite ? r.policy === 'Allow' : r.policy === 'Ban'));
  $('#secListTitle').textContent = mode === 1 ? '已授权设备' : (isWhite ? '白名单' : '黑名单');
  $('#secListCount').textContent = rows.length + ' 条';
  $('#secListNote').textContent = mode === 1
    ? '这些设备已经通过授权，可以正常上网。'
    : (isWhite ? '只有名单内的设备能连 Wi-Fi，名单外的会被拒绝。' : '黑名单内的设备无法连接 Wi-Fi。');
  $('#secRuleList').innerHTML = rows.map((r) => `
    <div class="srow">
      <div class="sm"><b>${r.name || '未知设备'}</b><span>${r.mac}</span></div>
      <button class="mini danger" data-del="${r.inst}">${mode === 1 ? '取消授权' : '移出'}</button>
    </div>`).join('') || `<div class="empty">${mode === 1 ? '还没有授权任何设备' : '名单是空的'}</div>`;

  document.querySelectorAll('#secPendList [data-act]').forEach((b) => {
    b.onclick = () => authAct(b.dataset.inst, b.dataset.act === 'allow' ? 2 : 1);
  });
  document.querySelectorAll('#secRuleList [data-del]').forEach((b) => {
    b.onclick = () => (mode === 1 ? authAct(b.dataset.del, 3) : aclDel(b.dataset.del));
  });
}

async function setSecMode(m) {
  if (SEC && Number(SEC.mode) === m) return;
  if (m === 2 && !confirm('切到「白名单接入」后，不在名单里的设备会立刻断网。\n建议先把家里要用的设备加进白名单。仍要切换？')) return;
  $('#secTip').textContent = '切换中…';
  try {
    const { data } = await api('/api/security/mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: m }),
    });
    if (!data || !data.ok) {
      $('#secTip').textContent = (data && data.error) || '切换失败';
      await loadSecurity();
      return;
    }
    $('#secTip').textContent = '';
    toast('已切换到' + (data.modeName || '新模式'));
    await loadSecurity();
  } catch (e) {
    $('#secTip').textContent = '切换失败：' + e;
  }
}

async function aclDel(inst) {
  if (!inst) return;
  if (!confirm('把这台设备移出名单？移出后它可以重新连接。')) return;
  try {
    const { data } = await api('/api/security/acl', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ op: 'del', inst }),
    });
    if (!data || !data.ok) { toast((data && data.error) || '操作失败'); return; }
    toast('已移出名单');
    await loadSecurity();
  } catch (e) { toast('操作失败：' + e); }
}

async function authAct(inst, action) {
  if (!inst) return;
  try {
    const { data } = await api('/api/security/auth', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ inst, action }),
    });
    if (!data || !data.ok) { toast((data && data.error) || '操作失败'); return; }
    toast(action === 2 ? '已允许上网' : action === 1 ? '已拒绝' : '已取消授权');
    await loadSecurity();
  } catch (e) { toast('操作失败：' + e); }
}

// ================= 网络设置 =================
let LAN = null;

async function loadLan() {
  $('#lanState').textContent = '';
  try {
    const { status, data } = await api('/api/lan');
    if (status === 401 || (data && data.logged === false)) { show('login'); return; }
    if (!data || !data.ok) { $('#lanState').textContent = (data && data.error) || '读取失败'; return; }
    LAN = data;
    renderLan(data);
  } catch (e) {
    $('#lanState').textContent = '读取失败：' + (e && e.message ? e.message : e);
  }
}

function renderLan(d) {
  $('#lanIp2').textContent = d.ip || '—';
  $('#lanMask').textContent = d.mask || '—';
  $('#lanDhcp').textContent = d.dhcpOn ? '已开启' : '已关闭';
  $('#lanPool').textContent = (d.min && d.max) ? (d.min + ' – ' + d.max) : '—';
  $('#lanDns').textContent = [d.dns1, d.dns2].filter((x) => x && x !== '0.0.0.0').join(' / ') || '运营商分配';
  $('#lanLease').textContent = d.leaseForever ? '永久' : (d.lease ? d.lease + ' 分钟' : '—');
  $('#lanState').textContent = d.dhcpOn ? 'DHCP 已开启' : 'DHCP 已关闭';

  const binds = d.binds || [];
  $('#bindCount').textContent = binds.length + ' 条';
  $('#bindList').innerHTML = binds.map((b) => `
    <div class="srow">
      <div class="sm"><b>${b.name || '未命名设备'}</b><span>${b.mac} → ${b.ip}</span></div>
      <button class="mini danger" data-bdel="${b.inst}" data-name="${b.name || ''}" data-ip="${b.ip}" data-mac="${b.mac}">删除</button>
    </div>`).join('') || '<div class="empty">还没有静态绑定</div>';
  document.querySelectorAll('#bindList [data-bdel]').forEach((btn) => {
    btn.onclick = () => delBind(btn.dataset.bdel, btn.dataset);
  });
}

function openLanEdit() {
  if (!LAN) { toast('还没有读到局域网配置'); return; }
  $('#lnDhcp').checked = !!LAN.dhcpOn;
  $('#lnMin').value = LAN.min || '';
  $('#lnMax').value = LAN.max || '';
  $('#lnDns1').value = (LAN.dns1 && LAN.dns1 !== '0.0.0.0') ? LAN.dns1 : '';
  $('#lnDns2').value = (LAN.dns2 && LAN.dns2 !== '0.0.0.0') ? LAN.dns2 : '';
  $('#lnLease').value = LAN.lease || '';
  $('#lnIp').value = LAN.ip || '';
  $('#lnMask').value = LAN.mask || '';
  $('#lnErr').textContent = '';
  $('#lanSheet').classList.remove('hidden');
}

async function saveLan() {
  const body = {
    dhcpOn: $('#lnDhcp').checked,
    min: $('#lnMin').value.trim(),
    max: $('#lnMax').value.trim(),
    dns1: $('#lnDns1').value.trim(),
    dns2: $('#lnDns2').value.trim(),
    lease: $('#lnLease').value.trim(),
    ip: $('#lnIp').value.trim(),
    mask: $('#lnMask').value.trim(),
  };
  const ipChanged = LAN && body.ip && body.ip !== LAN.ip;
  if (ipChanged && !confirm('路由器地址将从 ' + LAN.ip + ' 改成 ' + body.ip + '。\n保存后当前连接会立刻断开，需要用新地址重新打开。继续？')) return;
  const btn = $('#lnSave');
  btn.disabled = true; btn.textContent = '保存中…';
  $('#lnErr').textContent = '';
  try {
    const { data } = await api('/api/lan/set', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    if (!data || !data.ok) { $('#lnErr').textContent = (data && data.error) || '保存失败'; return; }
    $('#lanSheet').classList.add('hidden');
    if (data.needRelogin) {
      alert('路由器地址已改为 ' + data.ip + '。\n请把设备接到新网段后，用新地址重新打开面板。');
    } else {
      toast('已保存');
    }
    await loadLan();
  } finally {
    btn.disabled = false; btn.textContent = '保存';
  }
}

function openBind(mac, name, ip) {
  const list = (LAST && LAST.clients) ? LAST.clients : [];
  $('#bdPick').innerHTML = '<option value="">手动输入 MAC</option>' + list.map((c) => {
    const nm = (c.alias || c.name || c.mac).replace(/"/g, '&quot;');
    return `<option value="${c.mac}" data-ip="${c.ip || ''}" data-name="${nm}">${nm} · ${c.ip}</option>`;
  }).join('');
  $('#bdName').value = name || '';
  $('#bdMac').value = mac || '';
  $('#bdIp').value = ip || '';
  $('#bdErr').textContent = '';
  if (mac) {
    Array.from($('#bdPick').options).forEach((o, i) => { if (i && o.value === mac) $('#bdPick').selectedIndex = i; });
  }
  $('#bindSheet').classList.remove('hidden');
}

async function saveBind() {
  const mac = $('#bdMac').value.trim().toUpperCase();
  const ip = $('#bdIp').value.trim();
  const name = $('#bdName').value.trim();
  if (!/^([0-9A-F]{2}:){5}[0-9A-F]{2}$/.test(mac)) return ($('#bdErr').textContent = 'MAC 地址格式不对，例如 A4:83:E7:1B:22:90');
  if (!/^\d{1,3}(\.\d{1,3}){3}$/.test(ip)) return ($('#bdErr').textContent = 'IP 地址格式不对');
  const btn = $('#bdSave');
  btn.disabled = true; btn.textContent = '保存中…';
  $('#bdErr').textContent = '';
  try {
    const { data } = await api('/api/bind', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mac, ip, name }),
    });
    if (!data || !data.ok) { $('#bdErr').textContent = (data && data.error) || '绑定失败'; return; }
    $('#bindSheet').classList.add('hidden');
    toast('已绑定 ' + ip);
    await loadLan();
  } finally {
    btn.disabled = false; btn.textContent = '保存';
  }
}

async function delBind(inst, ds) {
  if (!inst) return;
  if (!confirm('删除这条静态绑定？删除后该设备会恢复自动分配 IP。')) return;
  try {
    const { data } = await api('/api/bind', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ op: 'del', inst, name: ds.name, ip: ds.ip, mac: ds.mac, gateway: LAN ? LAN.gateway : '' }),
    });
    if (!data || !data.ok) { toast((data && data.error) || '删除失败'); return; }
    toast('已删除绑定');
    await loadLan();
  } catch (e) { toast('删除失败：' + e); }
}
"""

anchor = "(async function init() {"
assert anchor in h
h = h.replace(anchor, JS + "\n" + anchor, 1)

# 绑定
OLD_BIND = "$('#devSheet').addEventListener('click', (e) => { if (e.target.id === 'devSheet') closeDev(); });"
NEW_BIND = OLD_BIND + """
document.querySelectorAll('#secModes .opt').forEach((el) => {
  el.onclick = () => setSecMode(Number(el.dataset.mode));
});
$('#btnLanEdit').onclick = openLanEdit;
$('#lnCancel').onclick = () => $('#lanSheet').classList.add('hidden');
$('#lnSave').onclick = saveLan;
$('#lanSheet').addEventListener('click', (e) => { if (e.target.id === 'lanSheet') $('#lanSheet').classList.add('hidden'); });
$('#btnBindAdd').onclick = () => openBind('', '', '');
$('#bdCancel').onclick = () => $('#bindSheet').classList.add('hidden');
$('#bindSheet').addEventListener('click', (e) => { if (e.target.id === 'bindSheet') $('#bindSheet').classList.add('hidden'); });
$('#bdSave').onclick = saveBind;
$('#bdPick').onchange = () => {
  const o = $('#bdPick').selectedOptions[0];
  if (!o || !o.value) return;
  $('#bdMac').value = o.value;
  $('#bdName').value = o.dataset.name || '';
  if (o.dataset.ip) $('#bdIp').value = o.dataset.ip;
};
$('#dvBlock').onclick = async () => {
  if (!DEV_MAC) return;
  const nm = $('#dvName').textContent;
  if (!confirm('把「' + nm + '」加入黑名单？\\n它会立刻断开 Wi-Fi，直到你把它移出黑名单。')) return;
  try {
    const { data } = await api('/api/security/acl', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mac: DEV_MAC, policy: 'Ban', name: nm }),
    });
    if (!data || !data.ok) { toast((data && data.error) || '操作失败'); return; }
    toast('已禁止上网');
    closeDev();
    go('sec');
  } catch (e) { toast('操作失败：' + e); }
};
$('#dvBind').onclick = () => {
  if (!DEV_MAC) return;
  const c = (LAST && LAST.clients.find((x) => String(x.mac).toUpperCase() === DEV_MAC)) || {};
  openBind(DEV_MAC, c.alias || c.name || '', c.ip || '');
};"""
assert OLD_BIND in h
h = h.replace(OLD_BIND, NEW_BIND, 1)

OLD_ESC = "document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closeEdit(); closeDev(); } });"
NEW_ESC = """document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  closeEdit(); closeDev();
  $('#lanSheet').classList.add('hidden');
  $('#bindSheet').classList.add('hidden');
});"""
assert OLD_ESC in h
h = h.replace(OLD_ESC, NEW_ESC, 1)

io.open(P, "w", encoding="utf-8", newline="\n").write(h)
print("ok", len(h))
