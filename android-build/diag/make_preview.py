# -*- coding: utf-8 -*-
"""造一个带假数据的面板副本，用于截图检查排版。"""
import io

SRC = r"C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/zte-router-lab/panel.html"
DST = r"C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/out/preview.html"

h = io.open(SRC, encoding="utf-8").read()

MOCK = """
<script>
const SAMPLE = {
  dev: { name: '客厅巡天', model: 'ZXSLC SR7110', fw: 'V1.0.0.4B8.8000', mac: '2C:70:4F:63:73:41', ip: '192.168.5.1', mesh: false },
  wan: { status: 'Connected', down: '86.42Mbps', up: '12.08Mbps', ip: '112.96.173.204', type: 'PPPoE', user: '0755****8821', uptime: '3 天 7 小时', speed: '1000' },
  wifi: [
    { band: '2.4G', ssid: 'XiaoYa', enc: 'WPA2-PSK', max: 32, on: true, hidden: false },
    { band: '5G', ssid: 'XiaoYa_5G', enc: 'WPA2/WPA3', max: 64, on: true, hidden: false }
  ],
  clients: [
    { mac: 'A4:83:E7:1B:22:90', name: 'MacBook Pro', ip: '192.168.5.23', iface: '802.11 5G', band: '5G', online: '2 小时 14 分', vendor: 'Apple, Inc.' },
    { mac: '3C:2E:F5:77:0A:11', name: 'iPhone 15', ip: '192.168.5.31', iface: '802.11 5G', band: '5G', online: '5 小时 02 分', vendor: 'Apple, Inc.' },
    { mac: 'D8:9E:F3:4C:55:82', name: '小米电视', ip: '192.168.5.40', iface: 'LAN', port: 'LAN2', online: '1 天 3 小时', vendor: 'Xiaomi Communications Co Ltd' },
    { mac: '00:1A:79:6B:33:04', name: '台式电脑', ip: '192.168.5.13', iface: 'LAN', port: 'LAN1', online: '3 天 7 小时', vendor: 'Intel Corporate' },
    { mac: 'F0:18:98:2D:66:AC', name: 'iPad Air', ip: '192.168.5.55', iface: '802.11 2.4G', band: '2.4G', online: '38 分钟', vendor: 'Apple, Inc.' },
    { mac: '24:5E:BE:11:22:33', name: '群晖 NAS', ip: '192.168.5.12', iface: 'LAN', port: 'LAN3', online: '5 天 02 小时', vendor: 'Synology Incorporated' },
    { mac: '7C:49:EB:1A:22:9F', name: 'HUAWEI Mate 60', ip: '192.168.5.66', iface: '802.11 5G', band: '5G', online: '1 小时 12 分', vendor: 'HUAWEI TECHNOLOGIES CO.,LTD' },
    { mac: '64:09:80:3A:11:7E', name: 'HP LaserJet M1136', ip: '192.168.5.70', iface: 'LAN', port: 'LAN2', online: '9 小时', vendor: 'HP Inc.' }
  ],
  wired: 4, wireless: 4, count: 8
};
const LIMITS_MOCK = { rules: { 'D8:9E:F3:4C:55:82': { up: 5, down: 20, inst: '1' } }, enable: true };
const SEC_MOCK = {
  ok: true, mode: 1, modeName: '授权接入', localMac: '2C:70:4F:63:73:41',
  rules: [
    { inst: '11', mac: 'D8:9E:F3:4C:55:82', name: '小米电视', policy: 'Ban',
      ip: '192.168.5.40', vendor: 'Xiaomi Communications Co Ltd', dtype: '电视', online: true },
    { inst: '12', mac: '7C:49:EB:1A:22:9F', name: '邻居的手机', policy: 'Ban',
      ip: '', vendor: 'HUAWEI TECHNOLOGIES CO.,LTD', dtype: '手机', online: false },
    { inst: '13', mac: '64:09:80:3A:11:7E', name: 'HP LaserJet M1136', policy: '',
      ip: '192.168.5.70', vendor: 'HP Inc.', dtype: '打印机', online: true }
  ],
  pending: [
    { inst: '21', mac: '7C:49:EB:1A:22:9F', name: '陌生设备', time: '2 分钟前' }
  ],
  allowed: [
    { inst: '31', mac: 'A4:83:E7:1B:22:90', name: 'MacBook Pro', time: '1 小时' },
    { inst: '32', mac: '3C:2E:F5:77:0A:11', name: 'iPhone 15', time: '3 小时' }
  ]
};
const LAN_MOCK = {
  ok: true, ip: '192.168.5.1', mask: '255.255.255.0', dhcpOn: true,
  min: '192.168.5.2', max: '192.168.5.254', dns1: '223.5.5.5', dns2: '119.29.29.29',
  lease: '120', leaseForever: false, gateway: '192.168.5.1',
  binds: [{ inst: '41', name: '小米电视', ip: '192.168.5.40', mac: 'D8:9E:F3:4C:55:82' }]
};
const OPT_MOCK = {
  ok: true,
  bands: [
    { band: '2.4G', channel: 6, auto: false, bw: '40MHz', std: '802.11be', on: true, level: 'good' },
    { band: '5G', channel: 149, auto: true, bw: '160MHz', std: '802.11be', on: true, level: 'good' }
  ],
  rec: [
    { band: '2.4G', channel: 11, score: 42, nowChannel: 6, nowScore: 188, worth: true },
    { band: '5G', channel: 149, score: 12, nowChannel: 149, nowScore: 12, worth: false }
  ],
  scan: {
    ok: true, total: 9, err: '',
    aps: [
      { ssid: 'ChinaNet-8f2a', channel: 6, rssi: -48, band: '2.4G' },
      { ssid: 'TP-LINK_5G_A1C0', channel: 149, rssi: -55, band: '5G' },
      { ssid: 'CMCC-Home', channel: 6, rssi: -61, band: '2.4G' },
      { ssid: 'Xiaomi_AX3000', channel: 11, rssi: -66, band: '2.4G' },
      { ssid: 'HUAWEI-9K2L', channel: 44, rssi: -70, band: '5G' },
      { ssid: '', channel: 1, rssi: -78, band: '2.4G' },
      { ssid: 'DIRECT-3F-HP', channel: 6, rssi: -82, band: '2.4G' },
      { ssid: 'Redmi_5G', channel: 157, rssi: -84, band: '5G' }
    ]
  },
  tips: [
    { level: 'warn', text: '2.4G 用了 40MHz 频宽，邻居多时更容易卡；改成 20MHz 通常更稳' },
    { level: 'ok', text: '扫描到 9 个周边 Wi-Fi，已按信道拥挤度给出推荐' }
  ]
};
const ND_MOCK = {
  ok: true, summary: '1 项需留意',
  items: [
    { k: 'router', name: '手机到路由器', level: 'ok', detail: '响应 24 ms（HTTP 200）', tip: '' },
    { k: 'wan', name: '宽带连接', level: 'ok',
      detail: '状态 Connected · 类型 PPPoE · IP 100.64.32.18 · 网关 100.64.0.1 · DNS 202.96.128.86', tip: '' },
    { k: 'dns', name: '域名解析', level: 'ok', detail: 'www.baidu.com 解析耗时 31 ms', tip: '' },
    { k: 'inet', name: '外网连通', level: 'ok', detail: '连 mirrors.aliyun.com:443 耗时 42 ms', tip: '' },
    { k: 'lan', name: '局域网', level: 'warn', detail: '地址 192.168.5.1 · DHCP 已开启 · 地址池 192.168.5.2-192.168.5.254',
      tip: '地址池只剩 12 个可用，设备多的话建议放宽到 .200' }
  ]
};
const SPEED_MOCK = {
  ok: true, mbps: 326.4, bytes: 20971520, seconds: 1.42,
  source: '清华镜像', url: 'https://mirrors.tuna.tsinghua.edu.cn/ubuntu-releases/24.04/ubuntu-24.04.5-live-server-amd64.iso',
  grade: '很快'
};
const SPEED_NODES_MOCK = {
  ok: true, best: 'tuna',
  nodes: [
    { key: 'tuna', name: '清华 TUNA', tag: '教育网', ms: 23, ok: true },
    { key: 'ustc', name: '中科大', tag: '教育网', ms: 31, ok: true },
    { key: 'nju', name: '南京大学', tag: '教育网', ms: 44, ok: true },
    { key: 'huawei', name: '华为云', tag: '公有云', ms: 58, ok: true },
    { key: 'cf', name: 'Cloudflare', tag: '国际', ms: 210, ok: true }
  ]
};
// 桥接拨号：光猫管理页从路由器后面进不去（真机现状）
const ONT_MOCK = {
  ok: true, reachable: false, pppoe: true, mode: 'bridge', manual: false,
  wan: { ip: '100.64.12.87', gw: '100.64.0.1', conn: 'PPPoE', dns: '202.96.128.86' },
  best: null, candidates: [], tried: 12,
  note: '光猫现在跟路由器一起做桥接拨号，它的管理页只对「光猫自己的 LAN 口 / 光猫 Wi-Fi」开放，从路由器后面的手机是进不去的——这是正常现象，不是故障。',
  hint: '光猫现在跟路由器一起做桥接拨号，它的管理页只对「光猫自己的 LAN 口 / 光猫 Wi-Fi」开放，从路由器后面的手机是进不去的——这是正常现象，不是故障。',
  table: [['192.168.1.1','电信 / 移动最常见'],['192.168.0.1','联通最常见'],['192.168.100.1','部分光猫 / 桥接后'],['192.168.2.1','部分华为、中兴']]
};
// 路由模式且可进（?ontok=1 时用）
const ONT_OK = {
  ok: true, reachable: true, pppoe: false, mode: 'route', manual: false,
  wan: { ip: '192.168.1.20', gw: '192.168.1.1', conn: 'DHCP', dns: '202.96.128.86' },
  best: { ip: '192.168.1.1', port: 80, ms: 3, isGw: true, url: 'http://192.168.1.1' },
  candidates: [
    { ip: '192.168.1.1', port: 80, ms: 3, isGw: true, url: 'http://192.168.1.1' },
    { ip: '192.168.1.1', port: 443, ms: 5, isGw: true, url: 'https://192.168.1.1' }
  ],
  note: '', hint: ''
};
const SYSSTAT_MOCK = {
  ok: true, cpu: 37, mem: 68, src: 'home',
  ports: [
    { name: 'WAN', fw: 'WAN', if: 'eth0', wan: true, link: true, linkKnown: true, has: true, devs: 0, speed: '1000', max: '1000' },
    { name: 'LAN1', fw: 'LAN2', if: 'eth2', wan: false, link: true, linkKnown: true, has: true, devs: 1, speed: '1000', max: '2500' },
    { name: 'LAN2', fw: 'LAN1', if: 'eth1', wan: false, link: false, linkKnown: true, has: true, devs: 0, speed: '', max: '1000' },
    { name: 'LAN3', fw: 'LAN3', if: 'eth3', wan: false, link: true, linkKnown: true, has: true, devs: 1, speed: '1000', max: '1000' }
  ]
};
const WIFIMGR_MOCK = {
  ok: true,
  bands: [
    { band: '2.4G', level: 0, pe: '1', tx: '100%', channel: '6', auto: false, inuse: '6',
      bw: '20MHz', std: '11b,g,n', on: true },
    { band: '5G', level: 1, pe: '0', tx: '100%', channel: '', auto: true, inuse: '149',
      bw: '80MHz', std: '11a,n,ac,ax', on: true }
  ],
  channels: {
    '2.4G': ['1','2','3','4','5','6','7','8','9','10','11','12','13'],
    '5G': ['36','40','44','48','149','153','157','161','165']
  },
  compat: { force: true, forceRaw: '1', found: 4, err: null, items: [
    { band: '2.4G', inst: 'DEV.WIFI.AP3', psk: 'DEV.WIFI.AP3.PSK1', ssid: 'ASUS_XiaoYa',
      on: true, hidden: false, hasPwd: true, pwd: 'old2g8888' },
    { band: '5G', inst: 'DEV.WIFI.AP7', psk: 'DEV.WIFI.AP7.PSK1', ssid: 'XiaoYa_5G-wifi5',
      on: false, hidden: false, hasPwd: true, pwd: 'old5g8888' }
  ] },
  timer: { on: true, start: '23:30', end: '07:00' },
  mode: '', mesh: '0'
};
const PORTS_MOCK = {
  ok: true, at: 0,
  wired: { online: 2, total: 3 },
  ports: [
    { name: 'WAN', wan: true, link: true, linkKnown: true, speed: '1000', max: '1000',
      up: 9800, down: 210000, upText: '9.8 KB/s', downText: '210.3 KB/s',
      online: 0, offline: 0, devs: 0, busy: true, devList: [] },
    { name: 'LAN1', wan: false, link: true, linkKnown: true, speed: '', max: '2500',
      up: 1200, down: 34000, upText: '1.2 KB/s', downText: '34.6 KB/s',
      online: 1, offline: 0, devs: 1, busy: true,
      devList: [{ name: 'DESKTOP-PC', ip: '192.168.5.20', mac: 'AA:BB:CC:00:00:01', active: true }] },
    { name: 'LAN2', wan: false, link: false, linkKnown: true, speed: '', max: '1000',
      up: null, down: null, upText: '', downText: '',
      online: 0, offline: 0, devs: 0, busy: false, devList: [] },
    { name: 'LAN3', wan: false, link: true, linkKnown: true, speed: '100', max: '1000',
      up: 0, down: 0, upText: '0 KB/s', downText: '0 KB/s',
      online: 0, offline: 1, devs: 1, busy: false,
      devList: [{ name: 'NAS-DS220', ip: '192.168.5.30', mac: 'AA:BB:CC:00:00:02', active: false, last: '2026-11-15 20:11' }] }
  ]
};

const DW_MOCK = {
  ok: true, supported: true, flavor: 'fixed', canSwitch: false,
  wan1: { idx: 0, name: 'WAN', link: true, speed: '1000', max: '2500', locked: true },
  wan2: { idx: 1, name: 'LAN1', link: true, speed: '', max: '2500', enabled: false,
          preset: true, locked: true, status: '未启用', type: '', ip: '' },
  loadBalance: { enabled: false, wan1: '1', wan2: '1' },
  failover: false,
  note: '这台机器的物理 WAN 只有一个（WAN1），WAN2 是把 WAN1 旁边那个网口切过去当第二个 WAN 用。',
  ports: [
    { idx: 0, name: 'WAN', wan: true, wanType: 1, link: true, linkKnown: true, speed: '1000', max: '2500', isMain: true, isSec: false },
    { idx: 1, name: 'LAN1', wan: false, wanType: -1, link: true, linkKnown: true, speed: '', max: '2500', isMain: false, isSec: true },
    { idx: 2, name: 'LAN2', wan: false, wanType: -1, link: false, linkKnown: true, speed: '', max: '1000', isMain: false, isSec: false },
    { idx: 3, name: 'LAN3', wan: false, wanType: -1, link: true, linkKnown: true, speed: '', max: '1000', isMain: false, isSec: false }
  ]
};

const SYS_MOCK = {
  ok: true,
  app: { name: '中兴路由管家', ver: '2.6', code: '41', pkg: 'com.xiaoya.zterouter' },
  phone: {
    brand: 'Xiaomi', model: '23127PN0CC', android: '14', sdk: 34,
    screen: '1220×2712 · 440dpi', engine: 'Chrome 130', abi: 'arm64-v8a',
    net: 'Wi-Fi', ip: '192.168.5.31', uptime: '12 分钟'
  },
  host: { kind: '手机 App', client: '192.168.5.1' }
};

window.fetch = async function (u, o) {
  const p = String(u);
  let body = {};
  if (p.indexOf('/api/state') === 0) body = { logged: true, host: '192.168.5.1' };
  else if (p.indexOf('/api/all') === 0) body = SAMPLE;
  else if (p.indexOf('/api/net') === 0) {
    const k = Math.floor(Date.now() / 1000);
    const dn = 42 + 26 * Math.abs(Math.sin(k / 3.1)) + 9 * Math.abs(Math.sin(k / 1.3));
    const upv = 8 + 7 * Math.abs(Math.sin(k / 4.7));
    body = { ok: true, status: 'Connected', speed: '1000',
             down: dn.toFixed(2) + 'Mbps', up: upv.toFixed(2) + 'Mbps', ts: Date.now() };
  }
  else if (p.indexOf('/api/temp') === 0) body = { ok: true, c: 56.4, cpu: 23, mem: 41, src: 'dev_info' };
  else if (p.indexOf('/api/ports') === 0) body = PORTS_MOCK;
  else if (p.indexOf('/api/dualwan') === 0) body = (o && String(o.method || '').toUpperCase() === 'POST')
    ? { ok: true, changed: true, sec: 3, name: 'LAN3', enabled: false, msg: 'WAN2 已切到 LAN3 口' }
    : DW_MOCK;
  else if (p.indexOf('/api/adminpwd') === 0) body = { ok: true, user: 'admin', msg: '管理员密码已修改' };
  else if (p.indexOf('/api/port') === 0) {
    const nm = decodeURIComponent(((p.split('name=')[1] || '').split('&')[0])).toUpperCase() || 'LAN1';
    const WIRED = [
      { name: 'DESKTOP-T9EPKIE', alias: '台式电脑', ip: '192.168.5.13', mac: '2C:F0:5D:EA:01:F9',
        iface: 'Ethernet', port: 'eth2', up: '18.4Kbps', down: '212.6Kbps', online: '2 天 11 小时', vendor: 'Intel Corporate' },
      { name: '', alias: 'NAS', ip: '192.168.5.12', mac: '00:E0:67:00:44:03',
        iface: 'Ethernet', port: 'eth3', up: '1.2Mbps', down: '3.8Mbps', online: '5 天 2 小时', vendor: 'Synology Incorporated' }
    ];
    if (nm === 'WAN') {
      body = { ok: true, name: 'WAN', link: true, wan: true, speed: '1000', max: '1000', clients: [], net: {
        status: 'Connected', type: 'PPPoE 拨号', conn: 'PPPoE', ip: '112.96.173.204',
        mask: '255.255.255.0', gw: '112.96.160.1', dns: '202.96.128.86,202.96.134.133',
        user: '0755****8821', speed: '1000', uptime: '3 天 7 小时',
        up: '12.08Mbps', down: '86.42Mbps', private: false } };
    } else {
      const portOf = { LAN1: 'eth2', LAN2: 'eth1', LAN3: 'eth3' };
      const mine = WIRED.filter(function (c) { return c.port === portOf[nm]; });
      const portSpd = { LAN1: '1000', LAN2: '', LAN3: '1000' };
      const portMax = { LAN1: '2500', LAN2: '1000', LAN3: '1000' };
      body = { ok: true, name: nm, link: mine.length > 0, wan: false, exact: true,
               speed: portSpd[nm] || '', max: portMax[nm] || '',
               wiredTotal: WIRED.length, clients: mine.map(function (c) {
                 return Object.assign({}, c, {
                   portName: nm, ipv6: ['2408:8256:d28b:94:a4ff:9e00:1122:3344', 'fe80::a436:c007:c8a9:3b8e'],
                   last: '2026-11-14 20:13:05'
                 });
               }),
               net: { ip: '192.168.5.1', mask: '255.255.255.0', gw: '192.168.5.1',
                      dns: ['202.96.128.86', '202.96.134.133'],
                      min: '192.168.5.2', max: '192.168.5.254', dhcpOn: true } };
    }
  }
  else if (p.indexOf('/api/wifimgr/set') === 0) {
    let req = {};
    try { req = JSON.parse((o && o.body) || '{}'); } catch (e) {}
    if (req.action === 'compatpwd') {
      const it = (WIFIMGR_MOCK.compat.items || []).filter(function (x) { return x.band === req.band; })[0];
      body = (it && it.pwd)
        ? { ok: true, band: req.band, pwd: it.pwd, hasPwd: true }
        : { ok: true, band: req.band, pwd: '', hasPwd: false,
            error: '路由器没有返回 ' + req.band + ' 兼容网络的密码（实例 ' + (it ? it.inst : '') + '）' };
    } else {
      body = { ok: true, msg: '已保存' };
    }
  }
  else if (p.indexOf('/api/wifimgr') === 0) body = WIFIMGR_MOCK;
  else if (p.indexOf('/api/sysstat') === 0) body = SYSSTAT_MOCK;
  else if (p.indexOf('/api/limits') === 0) body = Object.assign({ ok: true }, LIMITS_MOCK);
  else if (p.indexOf('/api/security') === 0) body = SEC_MOCK;
  else if (p.indexOf('/api/optimize') === 0) body = OPT_MOCK;
  else if (p.indexOf('/api/netdiag') === 0) body = ND_MOCK;
  else if (p.indexOf('/api/speedtest') === 0) {
    let b = {};
    try { b = JSON.parse((o && o.body) || '{}'); } catch (e) {}
    const hit = SPEED_NODES_MOCK.nodes.filter(function (x) { return x.key === b.node; })[0];
    body = Object.assign({}, SPEED_MOCK,
      { node: b.node || 'tuna', nodeName: (hit && hit.name) || '清华镜像' });
  }
  else if (p.indexOf('/api/speednodes') === 0) body = SPEED_NODES_MOCK;
  else if (p.indexOf('/api/ont') === 0) body = location.search.indexOf('ontok') >= 0 ? ONT_OK : ONT_MOCK;
  else if (p.indexOf('/api/lan/set') === 0) body = { ok: true, ip: '192.168.5.1' };
  else if (p.indexOf('/api/lan') === 0) body = LAN_MOCK;
  else if (p.indexOf('/api/bind') === 0) body = { ok: true };
  else if (p.indexOf('/api/device') === 0) {
    const mac = decodeURIComponent(((p.split('mac=')[1] || '').split('&')[0])).toUpperCase();
    const isNas = mac.indexOf('00:E0:67') === 0;
    body = { ok: true, mac: mac, ip: isNas ? '192.168.5.12' : '192.168.5.13',
      mask: '255.255.255.0', gw: '192.168.5.1', dns: ['202.96.128.86', '202.96.134.133'],
      ipv6: isNas ? ['fe80::a436:c007:c8a9:3b8e'] : ['2408:8256:d28b:94:a4ff:9e00:1122:3344', 'fe80::c038:39f9:f01:4be6'],
      port: isNas ? 'LAN3' : 'LAN1', iface: 'Ethernet', last: '2026-11-14 20:13:05',
      down: isNas ? 3800 : 680, up: isNas ? 1200 : 18, rx: 1234567890, tx: 345678901,
      online: 18120, active: true, type: '有线', vendor: isNas ? 'Synology · DiskStation' : 'Realtek · 2.5G 网卡' };
  }
  else if (p.indexOf('/api/relogin') === 0) body = {
    ok: true, error: null,
    kicked: location.search.indexOf('nokick') >= 0 ? null : { ip: '192.168.5.23', mac: 'AA:BB:CC:DD:EE:FF', at: 0 }
  };
  else if (p.indexOf('/api/sysinfo') === 0) body = SYS_MOCK;
  else if (p.indexOf('/api/remote/status') === 0) body = {
    ok: true, running: true, url: 'https://soft-piano-limit-delta.trycloudflare.com',
    target: 'https://192.168.5.1', err: null, ready: true, host: '192.168.5.1', log: []
  };
  else body = { ok: true };
  return { status: 200, json: async function () { return body; } };
};
</script>
"""

h = h.replace("</body>", MOCK + "\n</body>")
io.open(DST, "w", encoding="utf-8", newline="\n").write(h)
print("written", DST, len(h))
