# -*- coding: utf-8 -*-
"""
中兴路由管家 - 本地服务
适配 ZXSLC SR7110 / 巡天 BE5100 Pro(+) 新固件（?_type= / _tag= 接口体系）
"""
import base64
import hashlib
import html
import http.cookiejar
import json
import os
import platform
import re
import socket
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA

import compat          # 固件族探测 / 资源解析（多机型适配）

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOST = os.environ.get("ZTE_HOST", "192.168.5.1")
PORT = int(os.environ.get("ZTE_PORT", "8900"))
# ZTE_BIND=0.0.0.0 时手机/PWA 可从局域网访问；此时自动要求访问码保护
BIND = os.environ.get("ZTE_BIND", "127.0.0.1")
PWA_TOKEN = os.environ.get("ZTE_TOKEN", "")
if not PWA_TOKEN and BIND not in ("127.0.0.1", "localhost"):
    import secrets
    PWA_TOKEN = secrets.token_hex(3)
USER = "admin"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
JAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=CTX),
    urllib.request.HTTPCookieProcessor(JAR),
)

LOCK = threading.Lock()


def _lan_ip():
    try:
        s0 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s0.connect(("223.5.5.5", 80))
        ip = s0.getsockname()[0]
        s0.close()
        return ip
    except Exception:
        return ""


def _panel_addr():
    if BIND in ("127.0.0.1", "localhost"):
        return "http://127.0.0.1:%d/" % PORT
    ip = _lan_ip() or "0.0.0.0"
    url = "http://%s:%d/" % (ip, PORT)
    if PWA_TOKEN:
        url += "?t=" + PWA_TOKEN
    return url
# 路由器每次响应都会轮换一次性令牌，所有请求必须串行，否则并发会把令牌抢废（返回 1452 页面过期）
ROUTER = threading.RLock()
# pwd 只存在内存里，用于会话掉线后自动重登，退出即清空
S = {"logged": False, "token": None, "error": None, "at": 0, "pwd": None, "wpwd": {},
     # kick: 上一次成功顶掉的设备；pending: 当前占着名额没顶成的设备；claim: 用户主动登录过
     "kick": None, "pending": None, "preempt_at": 0, "claim": False}
# mode: 会话令牌的携带位置（body=固件行为）；last: 最近一次响应的头，仅用于诊断
G = {"mode": "body", "last": {}}
MODE_FILE = os.path.join(BASE_DIR, "token_mode.txt")


def save_mode(m):
    G["mode"] = m
    try:
        with open(MODE_FILE, "w", encoding="utf-8") as f:
            f.write(m)
    except Exception:
        pass


def load_mode():
    try:
        with open(MODE_FILE, encoding="utf-8") as f:
            m = f.read().strip()
        if m in ("body", "query", "header", "both"):
            G["mode"] = m
    except Exception:
        pass


load_mode()

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"

# 固件内置的 RSA 公钥（用于把 AES 随机数交给路由器）
RSA_PUB = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAodPTerkUVCYmv28SOfRV
7UKHVujx/HjCUTAWy9l0L5H0JV0LfDudTdMNPEKloZsNam3YrtEnq6jqMLJV4ASb
1d6axmIgJ636wyTUS99gj4BKs6bQSTUSE8h/QkUYv4gEIt3saMS0pZpd90y6+B/9
hZxZE/RKU8e+zgRqp1/762TB7vcjtjOwXRDEL0w71Jk9i8VUQ59MR1Uj5E8X3WIc
fYSK5RWBkMhfaTRM6ozS9Bqhi40xlSOb3GBxCmliCifOJNLoO9kFoWgAIw5hkSIb
GH+4Csop9Uy8VvmmB+B3ubFLN35qIa5OG5+SDXn4L7FeAA5lRiGxRi8tsWrtew8w
nwIDAQAB
-----END PUBLIC KEY-----"""


# ---------- 加解密 ----------

def _sha(t):
    return hashlib.sha256(t.encode("utf-8")).digest()


def enc_para(text, a, b):
    """AES-CBC(ZeroPadding) + Base64，key=SHA256(a)，iv=SHA256(b)[:16]"""
    data = text.encode("utf-8")
    pad = (16 - len(data) % 16) % 16
    data += b"\x00" * pad
    c = AES.new(_sha(a), AES.MODE_CBC, _sha(b)[:16])
    return base64.b64encode(c.encrypt(data)).decode()


def dec_para(b64, a, b):
    raw = base64.b64decode(b64)
    c = AES.new(_sha(a), AES.MODE_CBC, _sha(b)[:16])
    return c.decrypt(raw).rstrip(b"\x00").decode("utf-8", "replace")


def enc_key(a, b):
    """RSA(PKCS1v15) 加密 "a+b"，交给路由器还原 AES 的随机数"""
    pub = RSA.import_key(RSA_PUB)
    return base64.b64encode(PKCS1_v1_5.new(pub).encrypt(("%s+%s" % (a, b)).encode())).decode()


def rand16():
    return "".join(str(int(x)) for x in os.urandom(16))


# ---------- HTTP ----------

def _url(path):
    return "https://%s%s" % (HOST, path)


def req(path, data=None, timeout=12):
    with ROUTER:
        body = None
        headers = {
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://%s/" % HOST,
            "X-Requested-With": "XMLHttpRequest",
        }
        if data is None:
            headers["Content-Type"] = "text/xml; charset=utf-8"
        else:
            payload = dict(data)
            tok = S["token"] or ""
            mode = G.get("mode", "body")
            if tok:
                # 诊断用：token 可放在 body / 查询串 / 请求头，默认与固件一致放 body 末尾
                if mode in ("body", "both") and "_sessionTOKEN" not in payload:
                    payload["_sessionTOKEN"] = tok
                if mode == "query":
                    path = path + ("&" if "?" in path else "?") + "_sessionTOKEN=" + urllib.parse.quote(tok)
                if mode in ("header", "both"):
                    headers["_sessionTOKEN"] = tok
                    headers["x_xsrf_token"] = tok
            body = urllib.parse.urlencode(payload).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        r = urllib.request.Request(_url(path), data=body, headers=headers)
        try:
            resp = OPENER.open(r, timeout=timeout)
            G["last"] = dict(resp.headers)
            tok = resp.headers.get("x_xsrf_token")
            if tok:
                S["token"] = tok
            return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            G["last"] = dict(e.headers)
            return e.code, e.read().decode("utf-8", "replace")


# ---------- 兼容层：资源 → 实际接口路径 ----------

def _probe_get(path):
    """探测专用：不改会话状态，只回报 (status, text)"""
    try:
        return req(path, timeout=8)
    except Exception:
        return 0, ""


def _res_path(res, fallback_tag=None):
    """资源名 → 当前固件上可用的路径（依赖 compat 的探测缓存）"""
    return compat.path(res, fallback_tag)


def _goform_as_groups(res):
    """经典固件（goform）读取 → 包装成上层熟悉的 OBJ_ 结构。

    只做基础信息/版本/终端/外网四类；拿不到的字段留空，界面自然降级。
    这段属于「实验性适配」：不同代 goform 固件的 cmd 名有差异，缺失时返回空。
    """
    cmds = {
        "device": "deviceName,cr_version,wa_inner_version,web_version,Language,"
                  "uptime,wan_ipaddr,wan_connect_status,network_type,network_signalbar,station_num",
        "version": "deviceName,cr_version,wa_inner_version,web_version,Language",
        "clients": "station_list,lan_station_list,station_num",
        "wan": "wan_ipaddr,wan_connect_status,network_type,network_signalbar,ppp_status",
    }.get(res)
    if not cmds:
        return {}
    d = gget(cmds)
    if not d:
        return {}
    up = str(d.get("wan_connect_status", "")).strip() in ("1", "connected", "true")
    if res in ("device", "version"):
        basic = {
            "DevName": (d.get("deviceName") or "").strip(),
            "WANStatus": "1" if up else "0",
            "IPAddress": (d.get("wan_ipaddr") or "").strip(),
            "NetworkType": (d.get("network_type") or "").strip(),
            "SignalBar": (d.get("network_signalbar") or "").strip(),
            "UpTime": (d.get("uptime") or "").strip(),
            "SoftwareVer": (d.get("wa_inner_version") or d.get("cr_version") or "").strip(),
            "WebVer": (d.get("web_version") or "").strip(),
        }
        return {"OBJ_HOME_BASICINFO_ID": [basic], "OBJ_GLOBAL_ENV": [{"Source": "goform"}]}
    if res == "wan":
        return {"OBJ_ETHWANCPPP_ID": [{
            "ConnStatus": "1" if up else "0",
            "IPAddress": (d.get("wan_ipaddr") or "").strip(),
            "NetworkType": (d.get("network_type") or "").strip(),
        }]}
    if res == "clients":
        out = []
        raw = d.get("station_list") or d.get("lan_station_list") or ""
        try:
            arr = json.loads(raw) if isinstance(raw, str) and raw.strip().startswith("[") else []
        except Exception:
            arr = []
        for it in arr if isinstance(arr, list) else []:
            if not isinstance(it, dict):
                continue
            out.append({
                "MACAddress": it.get("mac_addr") or it.get("mac") or "",
                "HostName": it.get("hostname") or it.get("host_name") or "",
                "IPAddress": it.get("ip_addr") or it.get("ip") or "",
                "Interface": it.get("port") or "",
            })
        return {"OBJ_CLIENTS_ID": out} if out else {}
    return {}


def vget(res, fallback_tag=None):
    """按资源取 XML 分组（新固件）；该资源不可用时返回空字典，不抛异常。

    和老代码 fetch("/?_type=vueData&_tag=xxx") 等价，只是 tag 由兼容层挑。
    经典固件族（goform）走 JSON 接口，再翻译成同样的 OBJ_ 结构。
    """
    if compat.S.get("family") == compat.FAMILY_GOFORM:
        try:
            return _goform_as_groups(res)
        except Exception as e:
            _slog("goform 读 %s 失败 %s" % (res, e))
            return {}
    p = _res_path(res, fallback_tag)
    if not p or "_tag=&" in p or p.endswith("_tag="):
        return {}
    try:
        return fetch(p)
    except RuntimeError:
        raise
    except Exception as e:
        _slog("vget %s 失败 %s" % (res, e))
        return {}


def gget(cmds, timeout=10):
    """经典固件读取：/goform/goform_get_cmd_process 返回 JSON，转成 {cmd: value}"""
    path = ("/goform/goform_get_cmd_process?isTest=false&cmd=%s&multi_data=1"
            % urllib.parse.quote(cmds if isinstance(cmds, str) else ",".join(cmds)))
    try:
        st, txt = req(path, timeout=timeout)
    except Exception:
        return {}
    if st != 200 or not (txt or "").strip().startswith("{"):
        return {}
    try:
        d = json.loads(txt)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def gset(form, timeout=10):
    """经典固件写入：POST /goform/goform_set_cmd_process（实验性）"""
    body = dict(form)
    body.setdefault("isTest", "false")
    try:
        st, txt = req("/goform/goform_set_cmd_process", body, timeout=timeout)
        return st, txt
    except Exception as e:
        return 0, str(e)


def compat_run(logged=None):
    """跑一次探测（登录后才有意义；未登录只做免登录识别）"""
    if logged is None:
        logged = bool(S.get("logged"))
    r = compat.detect(_probe_get, logged=logged)
    if logged:
        _model_read()                       # 顺手把型号喂给画像
        compat.set_model(MODEL.get("dev", ""), MODEL.get("web", ""), MODEL.get("sw", ""))
    return r


def _compat_bootstrap():
    """登录成功后后台探测一次能力（不阻塞界面；失败只留日志，下次启动再试）"""
    if compat.S.get("probed"):
        return

    def run():
        try:
            compat_run(logged=True)
        except Exception as e:
            _slog("兼容探测失败 %s" % e)

    threading.Thread(target=run, daemon=True).start()


def api_compat():
    """兼容性报告：登录状态下若还没探测过，自动补一次（失败不影响返回）"""
    if S.get("logged") and not compat.S.get("probed"):
        try:
            compat_run()
        except Exception as e:
            _slog("兼容探测失败 %s" % e)
    elif not S.get("logged") and not compat.S.get("family"):
        # 未登录：只做登录页特征识别（很轻，一个 GET）
        try:
            compat_run(logged=False)
        except Exception as e:
            _slog("登录页识别失败 %s" % e)
    rep = compat.report()
    rep["model"] = {"dev": MODEL.get("dev", ""), "web": MODEL.get("web", ""),
                    "sw": MODEL.get("sw", "")}
    # 面板自身对某些机型的已知限制，直接告诉前端要怎么降级
    rep["limits"] = {
        "wan2Fixed": compat.has_quirk("wan2_fixed"),
        "preempt": compat.has_quirk("preempt_on_login"),
        "ispLocked": compat.has_quirk("isp_locked"),
        "goformOnly": compat.has_quirk("goform_only"),
    }
    return rep


def api_compat_redetect():
    """重新探测（用户换机 / 升级固件后用）"""
    compat.reset()
    r = compat_run()
    return {"ok": True, "report": api_compat(), "family": r.get("family")}


# ---------------------------------------------------------------- 中兴原厂 Mesh

# 拓扑 AP 实例字段 → 展示字段（各固件命名不一，逐个别名试）
_MESH_AP_KEYS = {
    "name": ("Alias", "APAlias", "DeviceName", "MeshDevName", "APName", "Name"),
    "mac": ("MACAddress", "APMac", "MeshDevMAC", "MAC", "Proof"),
    "ip": ("IPAddress", "APIP", "MeshDevIP", "IP"),
    "band": ("AccessType", "ConnectFreBand", "FreBand", "LinkFreBand", "Band"),
    "rate": ("LinkRate", "ConnectRate", "Rate", "Linkrate"),
    "rssi": ("RSSI", "APRSSI", "RSSIValue"),
    "role": ("TopologyType", "ApType", "Role", "DevType"),
}


def _mesh_ap_map(inst):
    out = {}
    for k, keys in _MESH_AP_KEYS.items():
        for key in keys:
            v = (inst.get(key) or "").strip()
            if v:
                out[k] = v
                break
    # 没映射到的字段原样带给前端（新固件字段名未知时也能看到东西）
    out["raw"] = {k: v for k, v in inst.items() if v not in ("", None)}
    return out


def _userif_env():
    """GET vue_userif_data（只读），取 OBJ_GLOBAL_ENV 里的 Mesh/角色字段"""
    try:
        st, txt = req("/?_type=hiddenData&_tag=vue_userif_data&_=%d"
                      % int(time.time() * 1000))
        if st != 200 or not txt or is_login_page(txt) or "OBJ_" not in txt:
            return {}
        g = groups(txt).get("OBJ_GLOBAL_ENV") or []
        return g[0] if g else {}
    except Exception as e:
        _slog("读 userif 失败 %s" % e)
        return {}


def _mesh_status_raw():
    """Mesh 状态：vuejsonData 可能回 JSON 也可能回 XML，两种都接"""
    try:
        d = vget("mesh")
        if d:
            return d
    except RuntimeError:
        raise
    except Exception as e:
        _slog("vget mesh 失败 %s" % e)
    try:
        st, txt = req(compat.path("mesh") + "&_=%d" % int(time.time() * 1000))
        txt = (txt or "").strip()
        if st == 200 and txt.startswith("{"):
            try:
                return json.loads(txt)
            except Exception:
                return {}
        if st == 200:
            return groups(txt)
    except Exception as e:
        _slog("读 mesh 状态失败 %s" % e)
    return {}


def _mesh_topo_raw():
    """Mesh 拓扑：GetALLAP 的 XML。返回 (MGET_INST_NUM, ap实例列表)"""
    try:
        st, txt = req(compat.path("topo") + "&_=%d" % int(time.time() * 1000))
        if st != 200 or not txt or "OBJ_" not in txt:
            return None, []
        m = re.search(r"<MGET_INST_NUM>(\d+)</MGET_INST_NUM>", txt)
        n = int(m.group(1)) if m else None
        g = groups(txt)
        insts = []
        for tag, lst in g.items():
            if tag.startswith("OBJ_AJAX") or tag.endswith("_GET_ID"):
                continue
            for inst in lst:
                insts.append(_mesh_ap_map(inst))
        return n, insts
    except RuntimeError:
        raise
    except Exception as e:
        _slog("读 mesh 拓扑失败 %s" % e)
        return None, []


def api_mesh():
    """中兴原厂 Mesh：状态 + 拓扑（只读）。

    组网/退网要配合固件配网向导（Wizard_Apply + ACTION_MESHTYPE），单独写容易把
    Wi-Fi 配置打坏，所以这里只做展示；固件返回什么就展示什么，字段名未知时也原样带出。
    """
    env = _userif_env()
    stat = _mesh_status_raw()
    top_list = stat.get("OBJ_LISTAPTOPO_ID") if isinstance(stat, dict) else None
    top = (top_list or [{}])[0]
    mlo_inst = (stat.get("OBJ_WLAN_STA_STATUS_PROFILE_ID") or [{}])[0] \
        if isinstance(stat, dict) else {}

    mesh_status = (top.get("MeshStatus") or "").strip()
    mlo = (mlo_inst.get("MLOStatus") or "").strip() == "1"
    mesh_enable = (env.get("MeshEnable") or "").strip()
    open_slave = (env.get("OpenAndSlave") or "").strip().lower() == "true"

    try:
        mget, aps = _mesh_topo_raw()
    except RuntimeError:
        raise
    except Exception:
        mget, aps = None, []

    enabled = mesh_status == "1" or mesh_enable == "1"
    if enabled:
        role = "slave" if open_slave else "master"
    else:
        role = "off"
    dev_num = None
    for cand in (top.get("t1905DevNum"), mget, len(aps) or None):
        try:
            if cand is not None and int(cand) > 0:
                dev_num = int(cand)
                break
        except (TypeError, ValueError):
            continue

    if role == "slave":
        role_label = "副路由（已并入其它网络）"
        note = "这台路由器被并入了别的 Mesh 网络（主路由是另一台设备）。"
    elif role == "master":
        role_label = "主路由"
        note = "已组网 %d 台设备%s。" % (dev_num or (len(aps) or 1),
                                        "，Wi-Fi 7 MLO 回程" if mlo else "")
    else:
        role_label = "未启用"
        note = ("这台路由器还没有组 Mesh。在原版管理页「MESH 组网配置」或中兴智慧生活 App "
                "里添加 Mesh 设备后，这里会显示组网拓扑（主/副路由、回程频段、信号强度）。")

    return {
        "ok": True,
        "supported": bool(env or stat or aps),   # userif 都读不到 → 该固件大概率无 Mesh
        "enabled": enabled,
        "role": role,
        "roleLabel": role_label,
        "devNum": dev_num,
        "accessType": (top.get("AccessType") or "").strip(),
        "mlo": mlo,
        "workMode": (env.get("curWorkMode") or "").strip(),
        "topoVer": (env.get("TopoPageVer") or "").strip(),
        "aps": aps,
        "note": note,
    }


# ---------------------------------------------------------------- 安全防护（防火墙 / 防攻击 / 安全日志）

# 固件 UI 级别值 ↔ 接口值（chunk4 逆向：3=高 6=中 9=低，线上值 High/Middle/Low）
_FW_LEVELS = ("High", "Middle", "Low")
_FW_LEVEL_CN = {"High": "高", "Middle": "中", "Low": "低"}


def _fw_level_of(raw):
    v = (raw or "").strip()
    return v if v in _FW_LEVELS else "High"


def _sec_fw_read():
    """读 security_firewall_data → OBJ_FWLEVEL_ID[0]"""
    d = vget("secfw")
    inst = (d.get("OBJ_FWLEVEL_ID") or [{}])[0]
    return inst or {}


def _sec_fw_write(form):
    txt = ax("/?_type=vueData&_tag=security_firewall_data", form, timeout=12)
    up = (txt or "").upper()
    if "SUCC" not in up and "OK" not in up and not _stale(txt):
        # 固件应答带 IF_ERRORSTR=SUCC；失败时抛错让前端显示
        m = re.search(r"IF_ERRORSTR>\s*([^<\s]+)", txt or "")
        err = m.group(1) if m else (txt or "")[:120]
        if err.upper() != "SUCC":
            raise ValueError("路由器拒绝了防火墙设置（%s）" % err)
    return txt


def api_secfw():
    """安全防护现状：IPv4/IPv6 防火墙级别、防攻击保护、安全日志（破解/攻击记录）"""
    fw = _sec_fw_read()
    dual = "Ipv4Enable" in fw          # 新固件有 IPv4/IPv6 双开关；旧固件只有 Level
    out = {
        "ok": True,
        "supported": bool(fw),
        "dual": dual,
        "antiAttack": (fw.get("AntiAttack") or "").strip() == "1",
    }
    if dual:
        out["ipv4Enable"] = (fw.get("Ipv4Enable") or "").strip() == "1"
        out["ipv6Enable"] = (fw.get("Ipv6Enable") or "").strip() == "1"
        out["ipv4Level"] = _fw_level_of(fw.get("Ipv4Level"))
        out["ipv6Level"] = _fw_level_of(fw.get("Ipv6Level"))
    else:
        out["level"] = _fw_level_of(fw.get("Level"))
    # 安全日志：开关 + 记录内容
    try:
        log = vget("seclog")
        inst = (log.get("OBJ_LOG_ID") or [{}])[0]
        out["secLogEnable"] = (inst.get("SecLogEnable") or "").strip() == "1"
        out["secLog"] = (inst.get("logStr") or "").replace("\r", "").strip()
    except Exception as e:
        _slog("读安全日志失败 %s" % e)
        out["secLogEnable"] = None
        out["secLog"] = ""
    out["secLogSupported"] = out["secLogEnable"] is not None
    return out


def api_secfw_set(body=None):
    """安全防护写入。body: {action: firewall|antiattack|seclog|seclog_refresh, ...}

    写防火墙走回填式：整表读出 → 只改请求的字段 → 原样提交，防止把另一半配置打掉。
    """
    body = body or {}
    act = (body.get("action") or "").strip()

    if act == "firewall":
        fw = _sec_fw_read()
        if not fw:
            raise ValueError("这台固件没有防火墙配置接口")
        dual = "Ipv4Enable" in fw
        form = {
            "IF_ACTION": "Apply",
            "_InstID": "IGD",
            "Level": "",
            "AntiAttack": "1" if (fw.get("AntiAttack") or "").strip() == "1" else "0",
            "Btn_cancel_FirewallConf": "",
            "Btn_apply_FirewallConf": "",
        }
        if dual:
            # 开关与级别分别回填：前端只传想改的项，其余保持现值
            form["Ipv4Enable"] = "1" if body.get("ipv4Enable",
                    (fw.get("Ipv4Enable") or "").strip() == "1") else "0"
            form["Ipv6Enable"] = "1" if body.get("ipv6Enable",
                    (fw.get("Ipv6Enable") or "").strip() == "1") else "0"
            form["Ipv4Level"] = _fw_level_of(body.get("ipv4Level") or fw.get("Ipv4Level"))
            form["Ipv6Level"] = _fw_level_of(body.get("ipv6Level") or fw.get("Ipv6Level"))
            # 固件规则：关掉的侧不提交级别
            if form["Ipv4Enable"] != "1":
                form["Ipv4Level"] = ""
            if form["Ipv6Enable"] != "1":
                form["Ipv6Level"] = ""
        else:
            form["Level"] = _fw_level_of(body.get("level") or fw.get("Level"))
        _sec_fw_write(form)
        return api_secfw()

    if act == "antiattack":
        fw = _sec_fw_read()
        if not fw:
            raise ValueError("这台固件没有防攻击保护接口")
        form = {
            "IF_ACTION": "Apply",
            "_InstID": "IGD",
            "Level": _fw_level_of(fw.get("Level")) if "Ipv4Enable" not in fw else "",
            "AntiAttack": "1" if body.get("enable") else "0",
            "Btn_cancel_FirewallConf": "",
            "Btn_apply_FirewallConf": "",
        }
        _sec_fw_write(form)
        return api_secfw()

    if act == "seclog":
        form = {
            "IF_ACTION": "Apply",
            "SecLogEnable": "1" if body.get("enable") else "0",
            "TOKEN_SECLOG_DOWNLOAD": S.get("token") or "",
        }
        ax("/?_type=vueData&_tag=seclogmgr_data", form, timeout=12)
        return api_secfw()

    if act == "seclog_refresh":
        txt = ax("/?_type=vueData&_tag=seclogmgr_data",
                 {"IF_ACTION": "Refresh"}, timeout=15)
        inst = (groups(txt).get("OBJ_LOG_ID") or [{}])[0]
        return {"ok": True, "secLog": (inst.get("logStr") or "").strip()}

    raise ValueError("未知的安全防护操作：%s" % (act or "空"))


def feel_token():
    """取一个新的一次性令牌（用只读业务接口，不能用登录接口，否则会顶掉当前会话）

    某些机型只有 *_no_update_sess 这类「不刷新会话」的接口，打它令牌不会变；
    这里依次试几个常规读接口，直到令牌真的换新为止。
    """
    with ROUTER:
        for res in ("device", "wan", "clients", "wifi"):
            before = S["token"]
            try:
                req(_res_path(res), timeout=8)
            except Exception:
                continue
            if S["token"] and S["token"] != before:
                break
        return S["token"]


def is_login_page(text):
    head = text.lstrip()[:300].lower()
    return head.startswith("<!doctype") or "<html" in head


def groups(text):
    out = {}
    for m in re.finditer(r"<(OBJ_[A-Z0-9_]+)>(.*?)</\1>", text, re.S):
        items = []
        insts = re.findall(r"<Instance>(.*?)</Instance>", m.group(2), re.S)
        for inst in insts:
            names = re.findall(r"<ParaName>(.*?)</ParaName>", inst, re.S)
            vals = re.findall(r"<ParaValue>(.*?)</ParaValue>", inst, re.S)
            items.append({k.strip(): html.unescape(v) for k, v in zip(names, vals)})
        if not insts:
            # 部分 _lua 页面把字段直接放在 OBJ 下，没有 Instance/ParaName 包装
            flat = dict(re.findall(r"<([A-Za-z0-9_]+)>([^<]*)</\1>", m.group(2), re.S))
            if flat:
                items.append({k: html.unescape(v) for k, v in flat.items()})
        out.setdefault(m.group(1), []).extend(items)
    return out


def xml_field(text, tag):
    m = re.search(r"<%s>(.*?)</%s>" % (tag, tag), text, re.S)
    return html.unescape(m.group(1)) if m else None


def _sess_log(msg):
    """会话事件留痕（顶号、掉线都写这里，出问题好回溯）"""
    try:
        with open(os.path.join(BASE_DIR, "logs", "session.log"), "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))
    except Exception:
        pass


def _insts(text, tag):
    """通用实例解析：<TAG><Instance>…</Instance></TAG>，兼容 ParaName/ParaValue 与平铺字段"""
    m = re.search(r"<%s>(.*?)</%s>" % (tag, tag), text, re.S)
    if not m:
        return []
    body = m.group(1)
    out = []
    for inst in re.findall(r"<Instance>(.*?)</Instance>", body, re.S):
        names = re.findall(r"<ParaName>(.*?)</ParaName>", inst, re.S)
        vals = re.findall(r"<ParaValue>(.*?)</ParaValue>", inst, re.S)
        if names:
            out.append({k.strip(): html.unescape(v) for k, v in zip(names, vals)})
        else:
            out.append({k: html.unescape(v) for k, v in
                        re.findall(r"<([A-Za-z0-9_]+)>([^<]*)</\1>", inst, re.S)})
    if not out:
        flat = dict(re.findall(r"<([A-Za-z0-9_]+)>([^<]*)</\1>", body, re.S))
        if flat:
            out.append({k: html.unescape(v) for k, v in flat.items()})
    return out


def _preempt_of(txt):
    """账号已在别处登录时，固件返回 LOGIN_PREEMPT_ID（带预占会话 id / IP / MAC）。

    「别处」可能是手机 App，也可能是上一次没退干净的管理页 —— 这正是要顶掉的对象。
    """
    if not txt or "LOGIN_PREEMPT_ID" not in txt:
        return None
    info = (_insts(txt, "LOGIN_PREEMPT_ID") or [{}])[0]
    sid = (info.get("preempt_sessid") or "").strip()
    if not sid:
        m = re.search(r'name="preempt_sessid"\s+value="?([^"\s/>]+)', txt)
        sid = m.group(1) if m else ""
    info["sessid"] = sid
    return info


def _preempt_msg(info, tried=True):
    who = ((info or {}).get("preempt_ip") or (info or {}).get("preempt_mac") or "").strip()
    name = ((info or {}).get("login_name") or USER or "admin").strip()
    if not info:
        return ("路由器上还有别的管理员会话（例如手机 App），%s"
                % ("接管没成功；稍等几秒再试，或先在那边退出登录" if tried
                   else "点「重新登录」可以顶掉它"))
    if not tried:
        return "路由器上还有别的管理员会话（%s 登录于 %s），点「重新登录」可以顶掉它" % (
            name, who or "另一台设备")
    return ("路由器上还有别的管理员会话（%s 登录于 %s），接管没成功；稍等几秒再试"
            % (name, who or "另一台设备"))


def _userif():
    """用户信息页：会话有效返回 OBJ_USERIF_ID，被别人占着返回 LOGIN_PREEMPT_ID"""
    st, txt = req("/?_type=hiddenData&_tag=vue_userif_data",
                  {"IF_ACTION": "Apply", "IsAutoShowWizard": "0"}, timeout=8)
    return txt or ""


def _take_over(sessid):
    """强制接管：把占着管理员名额的设备踢下线（固件 login_preempt），单次尝试"""
    if not sessid:
        return False
    try:
        req("/?_type=loginData&_tag=login_preempt",
            {"preempt_sessid": sessid, "action": "preempt"}, timeout=10)
    except Exception:
        return False
    return _preempt_of(_userif()) is None


def _claim(preempt=True):
    """登录后确认会话真的生效；被占着就按需接管。返回 (是否生效, 占位信息)"""
    info = _preempt_of(_userif())
    if info is None:
        return True, None
    S["pending"] = {"ip": info.get("preempt_ip") or "",
                    "mac": info.get("preempt_mac") or "",
                    "name": info.get("login_name") or "",
                    "at": int(time.time())}
    if not preempt:
        return False, info
    if not _take_over(info.get("sessid")):
        # 一次性令牌刚好轮换过就会失败，换新令牌拿最新的名额 id 再接管一次
        feel_token()
        again = _preempt_of(_userif()) or info
        if not _take_over(again.get("sessid")):
            return False, again
    kicked = {"ip": info.get("preempt_ip") or "",
              "mac": info.get("preempt_mac") or "",
              "name": info.get("login_name") or "",
              "at": int(time.time())}
    S["kick"] = kicked
    S["preempt_at"] = time.time()
    S["pending"] = None
    _sess_log("已接管管理会话，顶掉 %s（%s）" % (kicked["ip"] or "另一台设备", kicked["mac"] or "-"))
    return True, None


def _login_once(password, prefer_header=False):
    """跑一次完整登录：取一次性令牌 → 提交账号密码。

    整段必须独占 ROUTER：路由器每次响应都会换发新令牌，取令牌和提交登录之间
    只要插进任何一个别的请求（前端轮询、别的接口调用），提交时用的就是旧令牌，
    固件会直接返回 e_csrf_check_fail（「页面过期」）。
    返回 (是否成功, 错误文案, 是否值得重试)
    """
    with ROUTER:
        JAR.clear()
        S["token"] = None
        st, txt = req("/?_type=loginsceneData&_tag=login_token_json")
        try:
            info = json.loads(txt)
        except Exception:
            return False, "取登录令牌失败，路由器没有返回 JSON", True
        token = info.get("logintoken") or ""
        jtok = info.get("_sessionToken") or ""
        htok = S["token"] or ""
        # 正常用 JSON 里的 _sessionToken；若被判 e_csrf_check_fail，改用本次响应头里
        # 换发的新令牌再试一次（固件有时 JSON 里的值是上一轮已经作废的那个）
        sess = (htok or jtok) if (prefer_header and htok) else (jtok or htok)
        pwd = hashlib.sha256((password + token).encode("utf-8")).hexdigest()
        st, txt = req("/?_type=loginData&_tag=login_entry", {
            "Username": USER,
            "Password": pwd,
            "action": "login",
            "Frm_Logintoken": "",
            "captchaCode": "",
            "_sessionTOKEN": sess,
        })
    try:
        res = json.loads(txt)
    except Exception:
        return False, "登录响应异常：%s" % txt[:120], False

    if res.get("login_need_refresh"):
        # 拿到会话≠真的生效：可能被别的设备占着（返回 LOGIN_PREEMPT_ID），交给 _claim 确认
        S.update(token=res.get("sess_token") or sess, pwd=password, wpwd={})
        return True, None, False

    lock = res.get("lockingTime") or 0
    msg = ((res.get("loginErrMsg") or "") + " " + (res.get("loginErrType") or "")).strip()
    low = msg.lower()
    if lock and lock > 0:
        return False, "尝试次数过多，已临时锁定，请等待 %s 秒后再试" % lock, False
    if "csrf" in low or "1452" in low or "页面过期" in msg:
        return False, "登录令牌已过期（固件返回 e_csrf_check_fail），已自动重试仍未通过", True
    if "preempt" in low or "exceed" in low:
        return False, "路由器上还有别的管理员会话（例如手机 App），请先在那边退出或退出登录后重试", True
    if "error" in low or "password" in low or "userpass" in low:
        return False, "密码不正确，可查看路由器背面标签", False
    return False, "登录失败：%s" % (msg or txt[:100]), False


def _login_goform(password):
    """经典固件登录（实验性）：POST /goform/goform_set_cmd_process，goformId=LOGIN

    老款 MF / AC / E / ZXHN 系列用 base64(密码) 提交，成功返回 {"result":"0"}。
    这里只负责「能不能登上」，登不上就把原因带回去，不影响新固件的登录路径。
    """
    b64 = base64.b64encode(password.encode("utf-8")).decode("ascii")
    st, txt = gset({"goformId": "LOGIN", "password": b64})
    if st == 0:
        return False, "经典固件登录接口不可达"
    if st != 200:
        return False, "经典固件登录接口返回 HTTP %s" % st
    t = (txt or "").strip()
    if not t.startswith("{"):
        return False, "经典固件登录接口不存在（返回的不是 JSON）"
    try:
        res = json.loads(t)
    except Exception:
        return False, "经典固件登录应答无法解析"
    if str(res.get("result")) == "0":
        S.update(logged=True, error=None, at=time.time(), pwd=password, claim=True)
        compat.S["family"] = compat.FAMILY_GOFORM
        return True, None
    return False, "经典固件登录被拒（result=%s）" % res.get("result")


def login(password, preempt=True):
    """登录并确认会话生效：被别的设备占着时自动接管（把前面的会话顶下线）。

    preempt=False 只在后台静默重登时用，避免和手机 App 互相顶号。
    """
    with LOCK:
        last = "登录失败"
        rounds = 0
        while rounds < 3:
            rounds += 1
            ok, err, retry = _login_once(password, prefer_header=(rounds == 2))
            if not ok:
                # 新固件接口不存在时（返回登录页 HTML / 非 JSON），改试经典固件登录
                if err and ("没有返回 JSON" in err or "登录响应异常" in err) and rounds == 1:
                    gok, gerr = _login_goform(password)
                    if gok:
                        _sess_log("登录成功（经典固件 goform）")
                        _compat_bootstrap()
                        return True
                    last = gerr or err
                    S.update(logged=False, error=last)
                    return False
                last = err or last
                if not retry:
                    S.update(logged=False, error=last)
                    return False
                time.sleep(0.6)
                try:
                    JAR.clear()
                except Exception:
                    pass
                continue

            claimed, info = _claim(preempt=preempt)
            if not claimed:
                # 兜底：AX3000 等机型「登录即顶掉别人」时也带 preempt 提示，会话其实是好的；
                # 接管流程没走通不代表会话不可用，直接读一次数据定生死。
                try:
                    st2, txt2 = req(_res_path("device", "vue_home_device_data")
                                    + "&_=%d" % int(time.time() * 1000))
                    if st2 == 200 and txt2 and not _dead(txt2):
                        claimed = True
                        info = None
                        _sess_log("接管流程未走通，但会话实测可用（AX3000 口径），按登录成功处理")
                except Exception:
                    pass
            if claimed:
                S.update(logged=True, error=None, at=time.time(), pwd=password, claim=True)
                _sess_log("登录成功")
                _compat_bootstrap()
                return True
            last = _preempt_msg(info, tried=preempt)
            # 顶号最多走两轮，别把登录接口刷爆（固件名额释放有延迟，隔一下再抢）
            if not preempt or rounds >= 2:
                break
            time.sleep(0.8)
            try:
                JAR.clear()
            except Exception:
                pass
        S.update(logged=False, error=last)
        return False


def ensure():
    if not S["logged"]:
        raise RuntimeError("NOT_LOGGED")


def relogin_force(password=None):
    """手动「重新登录」：先退掉自己这边，再强行接管（顶掉其它设备）"""
    pwd = password or S.get("pwd") or ""
    if not pwd:
        return False, "需要重新输入管理员密码"
    # 主动登出，把自己的名额还回去，接着再抢一次，接管更干净
    try:
        req("/?_type=loginData&_tag=logout_entry",
            {"IF_LogOff": "1", "_sessionTOKEN": S["token"] or ""}, timeout=6)
    except Exception:
        pass
    try:
        JAR.clear()
    except Exception:
        pass
    S.update(logged=False, token=None, error=None, kick=None, pending=None)
    ok = login(pwd, preempt=True)
    if ok:
        return True, None
    return False, S.get("error") or "接管失败"


def _relogin():
    """会话被路由器踢掉时，用内存里的密码自动重登一次。

    刚接管过就 3 分钟内不再抢（否则会和手机 App 陷入互踢循环），
    让用户手动点「重新登录」来夺回。
    """
    pwd = S.get("pwd")
    if not pwd:
        return False
    preempt = (time.time() - float(S.get("preempt_at") or 0)) > 180
    ok = login(pwd, preempt=preempt)
    if not ok and S.get("pending") and not preempt:
        S["error"] = "会话被其他设备接管了，点「重新登录」可以顶回来"
    return ok


def _dead(txt):
    # 被别的设备顶掉时，固件给的不是登录页，而是 LOGIN_PREEMPT_ID 页，也要按掉线处理
    dead = is_login_page(txt) or "SessionTimeout" in txt or "LOGIN_PREEMPT_ID" in (txt or "")
    if dead:
        _sess_log("掉线（%s）" % ("登录页" if is_login_page(txt) else
                            ("被其他设备接管" if "LOGIN_PREEMPT_ID" in (txt or "") else "SessionTimeout")))
    return dead


def fetch(path, _retry=True):
    ensure()
    st, txt = req(path)
    if st == 404:
        # 404≠掉线：固件对不存在的 tag 会返回带 SessionTimeout 的 404 页面，
        # 按 _dead() 处理会误杀会话
        return {}
    if st != 200 or _dead(txt):
        S["logged"] = False
        if _retry and _relogin():
            return fetch(path, _retry=False)
        raise RuntimeError("NOT_LOGGED")
    return groups(txt)


def _stale(txt):
    """1452 = cmret_1452「页面过期」：一次性令牌被抢或已过期，换新令牌重试即可"""
    return "cmret_1452" in txt or "1452" in txt or "页面过期" in txt


def ax(path, form, timeout=12, _retry=True):
    """POST 业务接口：令牌过期换新重试；会话掉线自动重登并重试一次"""
    ensure()
    for attempt in range(3):
        st, txt = req(path, form, timeout=timeout)
        if _dead(txt):
            S["logged"] = False
            if _retry and _relogin():
                return ax(path, form, timeout=timeout, _retry=False)
            raise RuntimeError("NOT_LOGGED")
        if not _stale(txt):
            return txt
        if attempt < 2:
            feel_token()
    # 换了新令牌仍被判过期：说明会话本身已失效，重登后再试一次
    if _retry and _relogin():
        return ax(path, form, timeout=timeout, _retry=False)
    raise RuntimeError("路由器校验会话令牌失败（页面过期），请刷新页面后重试")


def fmt_dur(sec):
    try:
        sec = int(float(sec))
    except Exception:
        return "—"
    d, h, m = sec // 86400, sec % 86400 // 3600, sec % 3600 // 60
    if d:
        return "%d 天 %d 小时" % (d, h)
    if h:
        return "%d 小时 %d 分" % (h, m)
    return "%d 分钟" % m


def band_of(inst):
    if inst.endswith("AP1"):
        return "2.4G"
    if inst.endswith("AP5"):
        return "5G"
    return inst


# ---------- 设备信息（面板自身运行环境，手机端由原生层提供） ----------
APP_VER = "2.11.0"
START_TS = time.time()


def api_sysinfo():
    sec = int(time.time() - START_TS)
    return {
        "ok": True,
        "app": {"name": "中兴路由管家", "ver": APP_VER, "code": "web"},
        "host": {
            "kind": "电脑面板",
            "os": platform.platform(terse=True),
            "python": platform.python_version(),
            "addr": _panel_addr(),
            "uptime": fmt_dur(sec),
        },
        "phone": {},
        "ts": int(time.time()),
    }


# ---------- 业务 ----------

def read_wifi_raw():
    return vget("wifi", "wifiAP_data")


def _read_net():
    """外网实时计数器：只读一次 home_device_data，给 1 秒轮询用（比 /api/all 轻得多）"""
    home = vget("device", "vue_home_device_data")
    basic = (home.get("OBJ_HOME_BASICINFO_ID") or [{}])[0]
    return {
        "ok": True,
        "status": basic.get("WANStatus", ""),
        "up": basic.get("WANUpRate", ""),
        "down": basic.get("WANDownRate", ""),
        "speed": basic.get("WANSpeed", ""),
        "ts": int(time.time() * 1000),
    }


def api_net():
    """1 秒缓存合并：面板 + 手机同时轮询时只打一次路由器，避免把管理口刷到限速"""
    try:
        return _cached("netlive", 1.0, _read_net)
    except Exception as e:
        return {"ok": False, "error": str(e), "ts": int(time.time() * 1000)}


def api_all():
    home = vget("device", "vue_home_device_data")
    env = (home.get("OBJ_GLOBAL_ENV") or [{}])[0]
    basic = (home.get("OBJ_HOME_BASICINFO_ID") or [{}])[0]

    net = vget("wan", "vue_internet_data")
    wan = (net.get("OBJ_ETHWANCPPP_ID") or [{}])[0]

    wifi_raw = read_wifi_raw()
    psk = {x.get("_InstID_PSK", ""): x for x in wifi_raw.get("OBJ_WLANPSK_ID", [])}
    wifi = []
    for ap in wifi_raw.get("OBJ_WLANAP_ID", []):
        inst = ap.get("_InstID", "")
        band = band_of(inst)
        p = psk.get(inst + ".PSK1") or psk.get(inst + ".PSK") or {}
        wifi.append({
            "band": band,
            "ssid": ap.get("ESSID", ""),
            "on": ap.get("Enable") == "1",
            "enc": ap.get("BeaconType", ""),
            "auth": ap.get("11iAuthMode") or ap.get("WPAAuthMode") or "",
            "max": ap.get("MaxUserNum", ""),
            "hidden": ap.get("ESSIDHideEnable") == "1",
            "hasPwd": bool(p.get("KeyPassphrase")),
        })
    wifi.sort(key=lambda x: 0 if x["band"] == "2.4G" else 1)

    clients_raw = vget("clients", "vue_client_data")
    bands = _band_map()
    clients = []
    for c in clients_raw.get("OBJ_CLIENTS_ID", []):
        iface = c.get("InterfaceType", "")
        wireless = "802.11" in iface
        _v = VENDOR_DB.get((c.get("MACAddress") or "").upper()) or {}
        clients.append({
            "name": c.get("HostName") or "未知设备",
            "alias": c.get("AliasName") or "",
            "ip": c.get("IPAddress", ""),
            "mac": c.get("MACAddress", ""),
            "iface": iface,
            "band": bands.get((c.get("MACAddress") or "").upper(), "") if wireless else "",
            "port": "" if wireless else _port_name_of(c.get("Interface")),
            "up": c.get("UpRate", ""),
            "down": c.get("DownRate", ""),
            "online": fmt_dur(c.get("OnlineDuration")),
            "vendor": _v.get("vendor", ""),
            "dtype": _v.get("type", ""),
        })
    clients.sort(key=lambda x: [int(p) for p in (x["ip"].split(".") if x["ip"].count(".") == 3 else [999, 999, 999, 999])])

    wired = sum(1 for c in clients if "802.11" not in (c["iface"] or ""))
    return {
        "logged": True,
        "dev": {
            "name": basic.get("DevName") or env.get("WEBTitle") or "中兴路由器",
            "model": env.get("WEBTitle", ""),
            "fw": env.get("SoftwareVer", ""),
            "ip": basic.get("Br0IP", HOST),
            "mac": basic.get("Br0MAC", ""),
            "mesh": env.get("MeshEnable") == "1",
        },
        "wan": {
            "status": basic.get("WANStatus", ""),
            "up": basic.get("WANUpRate", ""),
            "down": basic.get("WANDownRate", ""),
            "speed": basic.get("WANSpeed", ""),
            "ip": wan.get("IPAddress", ""),
            "uptime": fmt_dur(wan.get("UpTime")),
            "user": wan.get("UserName", ""),
            "type": wan.get("WANCName", ""),
            "conn": wan.get("ConnType", ""),
            "gw": (wan.get("DefaultGateway") or wan.get("Gateway")
                   or basic.get("DefaultGateway") or ""),
            "dns": (wan.get("DNSServers") or wan.get("DNSServer")
                    or wan.get("DNS") or ""),
            "mask": wan.get("SubnetMask", ""),
        },
        "wifi": wifi,
        "clients": clients,
        "count": basic.get("AccessDevNum", str(len(clients))),
        "wired": wired,
        "wireless": len(clients) - wired,
        "ts": int(time.time()),
    }


def _slog_pwd(msg):
    """读密码的诊断日志（写 logs/pwd.log，出问题时好查固件到底返回了什么）"""
    try:
        with open(os.path.join(BASE_DIR, "logs", "pwd.log"), "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (time.strftime("%H:%M:%S"), msg))
    except Exception:
        pass


def _read_psk(inst, cache_key, use_cache=True):
    """
    按 PSK 实例读当前密码（主 SSID 与兼容网络的 PSK 实例名不同，逻辑一样）。
    关键：路由器是用「本次请求携带的 _sessionTOKEN」作为 AES 口令加密的，
    响应头里的 x_xsrf_token 是下一次用的新令牌，不能拿来解密。
    另外连续多次调用会触发路由器的保护机制，所以读到就缓存。
    """
    ensure()
    if use_cache and cache_key in S["wpwd"]:
        return S["wpwd"][cache_key]
    tok = S["token"] or ""
    form = {
        "IF_ACTION": "GetPassword",
        "ACTION_TYPE": "wlanPassword",
        "_InstID_PASS": inst,
        "PASSTYPE": "PSK",
    }
    for attempt in (0, 1):
        time.sleep(0.3)                 # 路由器对连续读密码敏感，稍作间隔
        tok = S["token"] or ""          # 必须用发请求那一刻的令牌解密
        form["_sessionTOKEN"] = tok
        st, txt = req("/?_type=vueData&_tag=vuecfg_data", form)
        if not _dead(txt):
            break
        S["logged"] = False
        if attempt == 0 and _relogin():
            continue
        raise RuntimeError("NOT_LOGGED")
    g = groups(txt)
    items = g.get("OBJ_WLANPSK_ID") or []

    def _valid(raw):
        if not raw:
            return ""
        try:
            v = dec_para(raw, tok, tok[::-1])
        except Exception:
            return ""
        if not v or any(ord(ch) < 32 or ord(ch) > 126 for ch in v):
            return ""
        return v

    # 1) 先按实例名精确匹配（返回里常同时带两个频段）
    hit = [it for it in items
           if inst in (it.get("_InstID"), it.get("_InstID_PSK"), it.get("_InstID_PASS"))]
    if not hit and len(items) == 1:
        hit = items
    got = [v for v in (_valid(it.get("KeyPassphrase")) for it in hit) if v]
    if len(got) == 1:
        S["wpwd"][cache_key] = got[0]
        return got[0]

    # 2) 匹配不到时把返回条目都试一遍：只有「唯一」能解出可打印密码才采用，
    #    多个都能解说明固件没按实例返回，宁可不显示也不能张冠李戴
    every = [v for v in (_valid(it.get("KeyPassphrase")) for it in items) if v]
    _slog_pwd("%s hit=%d got=%d every=%d keys=%s" % (
        inst, len(hit), len(got), len(every),
        ",".join(sorted({k for it in items for k in it.keys()}))[:300]))
    if not hit and len(every) == 1:
        S["wpwd"][cache_key] = every[0]
        return every[0]
    S["wpwd"][cache_key] = ""
    return ""


def get_wifi_pwd(band, use_cache=True):
    inst = "DEV.WIFI.AP5.PSK1" if band == "5G" else "DEV.WIFI.AP1.PSK1"
    return _read_psk(inst, band, use_cache)


def set_wifi(body):
    """
    修改 WiFi：名称 / 密码 / 开关。
    复用固件「无线设置」页的 ApplyALL 载荷，未改动的字段用当前值回填，
    避免路由器把没提交的项当成默认值。
    """
    ensure()
    raw = read_wifi_raw()
    env = (raw.get("OBJ_GLOBAL_ENV") or [{}])[0]
    aps = {a.get("_InstID"): a for a in raw.get("OBJ_WLANAP_ID", [])}
    psks = {p.get("_InstID_PSK", ""): p for p in raw.get("OBJ_WLANPSK_ID", [])}
    setting = {s.get("_InstID"): s for s in raw.get("OBJ_WLANSETTING_ID", [])}
    mlo = (raw.get("OBJ_MLO_ID") or [{}])[0]
    dual = (raw.get("OBJ_DUALBANDSYNC_ID") or [{}])[0]

    ap1, ap5 = aps.get("DEV.WIFI.AP1"), aps.get("DEV.WIFI.AP5")
    if not ap1 or not ap5:
        raise RuntimeError("没有读到无线配置")

    cur_pwd = {"2.4G": get_wifi_pwd("2.4G"), "5G": get_wifi_pwd("5G")}

    def pick(band, key, default=""):
        v = body.get(band) or {}
        return v.get(key, default)

    essid1 = pick("2.4G", "ssid", ap1.get("ESSID", "")).strip()
    essid5 = pick("5G", "ssid", ap5.get("ESSID", "")).strip()
    # 密码留空 = 保持原样（前端提示「留空则不修改」）
    pwd1 = (body.get("2.4G") or {}).get("pwd") or cur_pwd["2.4G"]
    pwd5 = (body.get("5G") or {}).get("pwd") or cur_pwd["5G"]
    on1 = 1 if pick("2.4G", "on", ap1.get("Enable") == "1") else 0
    on5 = 1 if pick("5G", "on", ap5.get("Enable") == "1") else 0

    # 读不到原密码又没手填时，绝不下发空密码，避免把加密方式改成开放网络
    if not pwd1 and on1:
        raise ValueError("读不到 2.4G 当前密码，请手动填写后保存（不允许留空）")
    if not pwd5 and on5:
        raise ValueError("读不到 5G 当前密码，请手动填写后保存（不允许留空）")

    for nm, s in (("2.4G", essid1), ("5G", essid5)):
        if s and not (1 <= len(s) <= 32):
            raise ValueError("%s 名称需为 1–32 个字符" % nm)
    for nm, p in (("2.4G", pwd1), ("5G", pwd5)):
        if p and not (8 <= len(p) <= 63):
            raise ValueError("%s 密码需为 8–63 位" % nm)
        if p and not all(32 <= ord(ch) < 127 for ch in p):
            raise ValueError("%s 密码只能用英文字母、数字和英文符号" % nm)

    a, b = rand16(), rand16()
    e1, e5 = enc_para(pwd1, a, b), enc_para(pwd5, a, b)

    def wr(suffix, ap):
        return {
            "_InstID" + suffix: "DEV.WIFI.AP" + ("1" if suffix == "1" else "5"),
            "_WLANCONIG" + suffix: "Y",
            "_WEPCONIG" + suffix: "N",
            "_PSKCONIG" + suffix: "Y",
            "BeaconType" + suffix: ap.get("BeaconType", "11iandWPA3"),
            "WEPAuthMode" + suffix: ap.get("WEPAuthMode", "SharedAuthentication"),
            "WEPEncryptionLevel" + suffix: ap.get("WEPEncryptionLevel", "40-bit"),
            "WEPKeyIndex" + suffix: ap.get("WEPKeyIndex", "1"),
            "WPAAuthMode" + suffix: ap.get("WPAAuthMode", "PSKAuthentication"),
            "WPAEncryptType" + suffix: ap.get("WPAEncryptType", "AESEncryption"),
            "11iAuthMode" + suffix: ap.get("11iAuthMode", "PSKAuthentication"),
            "11iEncryptType" + suffix: ap.get("11iEncryptType", "AESEncryption"),
            "ESSIDHideEnable" + suffix: ap.get("ESSIDHideEnable", "0"),
            "WEPEncryptionLevel_Bit" + suffix: ap.get("WEPEncryptionLevel_Bit", "40-bit"),
        }

    # 与固件「无线设置」页提交的字段一一对应（顺序也保持一致）
    form = {"IF_ACTION": "Apply", "DualBandSync": dual.get("DualBandSync", "0")}
    form.update({"Enable1": str(on1), "ESSID1": essid1})
    f1 = wr("1", ap1)
    form.update({"_InstID1": f1.pop("_InstID1"), "_WLANCONIG1": f1.pop("_WLANCONIG1"),
                 "_WEPCONIG1": f1.pop("_WEPCONIG1"), "_PSKCONIG1": f1.pop("_PSKCONIG1")})
    form.update({"KeyPassphrase1": e1, "WEPKey1": e1, "_InstID_PSK1": "DEV.WIFI.AP1.PSK1"})
    form.update(f1)
    form.update({"Enable5": str(on5), "ESSID5": essid5})
    f5 = wr("5", ap5)
    form.update({"_InstID5": f5.pop("_InstID5"), "_WLANCONIG5": f5.pop("_WLANCONIG5"),
                 "_WEPCONIG5": f5.pop("_WEPCONIG5"), "_PSKCONIG5": f5.pop("_PSKCONIG5")})
    form.update({"KeyPassphrase5": e5, "WEPKey5": e5, "_InstID_PSK5": "DEV.WIFI.AP5.PSK1"})
    form.update(f5)
    form.update({
        "MLOEnable": mlo.get("MLOEnable", "0"),
        "encode": enc_key(a, b),
        "PowerEnhance1": (setting.get("DEV.WIFI.RD1") or {}).get("PowerEnhance", "1"),
        "TxPower1": (setting.get("DEV.WIFI.RD1") or {}).get("TxPower", "100%"),
        "PowerEnhance5": (setting.get("DEV.WIFI.RD2") or {}).get("PowerEnhance", "1"),
        "TxPower5": (setting.get("DEV.WIFI.RD2") or {}).get("TxPower", "100%"),
        "Band1": "2.4GHz",
        "Band5": "5GHz",
        "_InstID_Frq1": "DEV.WIFI.RD1",
        "_InstID_Frq5": "DEV.WIFI.RD2",
    })
    # AES 载荷与 RSA 随机数与会话令牌无关，掉线重试也安全
    txt = ax("/?_type=vueData&_tag=wifi_advancedssid_data", form, timeout=25)
    err = xml_field(txt, "IF_ERRORSTR")
    if err and err.upper() not in ("SUCC", "SUCCESS", "OK"):
        raise RuntimeError("路由器拒绝修改：%s" % err)
    if not err and "<ajax_response" not in txt:
        raise RuntimeError("路由器返回异常：%s" % txt[:100])
    S["wpwd"].clear()
    return {"ok": True}


def probe_tag(tag):
    """诊断：原样拉一个固件接口，返回状态码和内容片段（找 CPU/内存等隐藏字段用）"""
    if not S.get("logged"):
        return {"ok": False, "error": "NOT_LOGGED"}
    path = "/?_type=vueData&_tag=" + urllib.parse.quote(tag or "")
    try:
        st, txt = req(path, timeout=10)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    keys = sorted(set(re.findall(r"<ParaName>([^<]+)</ParaName>", txt)))
    return {"ok": True, "tag": tag, "status": st, "len": len(txt or ""),
            "keys": keys[:400], "head": (txt or "")[:3000]}


def probe_modes():
    """诊断：用同样一份「原值回填」参数，依次改换令牌携带位置，找出路由器认可的方式"""
    out = []
    for m in ("body", "query", "header", "both"):
        G["mode"] = m
        try:
            r = set_wifi({})
            out.append({"mode": m, "ok": bool(r.get("ok"))})
            if r.get("ok"):
                break
        except Exception as e:
            out.append({"mode": m, "error": str(e)})
    res = {
        "results": out,
        "token_tail": (S.get("token") or "")[-6:],
        "token_headers": [k for k in (G.get("last") or {}) if "token" in k.lower()],
    }
    if out and out[-1].get("ok"):
        save_mode(G["mode"])
        res["chosen"] = G["mode"]
    else:
        G["mode"] = "body"
    return res


# ---------- 终端详情 / 限速（厂端接口：localnet_lan_detailinfo_lua / localnet_qosdyn_*） ----------

DEV_LOG = os.path.join(BASE_DIR, "logs", "device.log")


def _log_raw(tag, txt):
    try:
        os.makedirs(os.path.dirname(DEV_LOG), exist_ok=True)
        with open(DEV_LOG, "a", encoding="utf-8") as f:
            f.write("%s [%s] %s\n" % (time.strftime("%H:%M:%S"), tag, (txt or "")[:3000]))
    except Exception:
        pass


def _raw_get(path):
    """取原始响应文本（fetch 只返回解析后的分组，这里需要原文兜底排查）"""
    ensure()
    st, txt = req(path)
    if st == 404:
        # 404 只表示这个 tag 不存在；这台固件的 404 页正文带 SessionTimeout，
        # 早先按 _dead() 处理会把会话误判掉线、把后续请求全带死
        _slog("404", path)
        return ""
    if st != 200 or _dead(txt):
        S["logged"] = False
        if _relogin():
            st, txt = req(path)
            if st == 404:
                _slog("404", path)
                return ""
        else:
            raise RuntimeError("NOT_LOGGED")
        if _dead(txt):
            raise RuntimeError("NOT_LOGGED")
    return txt


def _fnum(v):
    try:
        return float(str(v).strip() or 0)
    except Exception:
        return 0.0


def _num_or_none(v):
    """数值字段解析：拿不到就返回 None（_ethport_speed 依赖它，缺了会让网口速率整块失效）"""
    try:
        return float(str(v).strip().rstrip("%"))
    except Exception:
        return None


# ---------- 机身温度 / 负载：固件未在网页界面暴露，按候选接口+字段名探测，命中后记住 ----------

# ---------- 系统状态：CPU 负载 / 内存占用 / 每个网口的连接情况 ----------
#
# 网口：GET /?_type=vuejsonData&_tag=vue_eth_portname&GET_TYPE=WANSTATUS
#   返回 OBJ_ETHPORT_INFO_ID（_InstID / ETHPortIFName / EthPortAliasName，WANSTATUS 时多 WanType）
#   和 OBJ_ETHPORT_STATE_ID（_InstID / EthPortStatus，实测不代表插线状态，见 read_ports）。
#   这个接口在未登录时也通（登录页要显示 WAN 灯），所以面板掉线时网口也照常显示。
# CPU / 内存：固件网页端没有独立接口（语言包里有“CPU 利用率/内存利用率”文案，但对应页面被裁掉），
#   只能按候选接口 + 字段名探测，命中后记住接口，之后只打那一个请求。

SYS_LOG = os.path.join(BASE_DIR, "logs", "sysstat.log")
PORTS_PATH = "/?_type=vuejsonData&_tag=vue_eth_portname&GET_TYPE=WANSTATUS"


def ports_path():
    """网口接口：优先用兼容层解析出来的路径，解析不到再退回本机实测路径"""
    p = compat.path("ports")
    if not p or p.endswith("_tag=") or "_tag=&" in p:
        return PORTS_PATH
    return p


# 机身丝印 ←→ 固件端口名 的对齐表。
# 实测这台 SR7110：机身 LAN1 口接的台式电脑，固件在 OBJ_CLIENTS_ID[].Interface 里报成
# eth2（别名 LAN2）；机身 LAN3 的 NAS 报 eth3（LAN3）。也就是固件的 LAN1/LAN2 与丝印相反，
# 这里把标签换回来，界面上显示的就与机身丝印一致。
PORT_SWAP = {"LAN1": "LAN2", "LAN2": "LAN1"}

SYS_SOURCES = [
    ("/?_type=vueData&_tag=vue_home_device_data", "home"),
    ("/?_type=hiddenData&_tag=vue_dev_info_data", "dev_info"),
    ("/?_type=hiddenData&_tag=vueinfo_data", "vueinfo"),
    ("/?_type=hiddenData&_tag=vue_userif_data", "userif"),
    ("/?_type=vueData&_tag=vue_topo_data&Action=SET", "topo"),
    ("/?_type=hiddenScene&_tag=initial_info_json", "initial"),
    ("/?_type=vueData&_tag=homestate_data", "homestate"),
    ("/?_type=hiddenData&_tag=vue_managdiagLed_data", "manag_diag"),
]

CPU_KEYS = ("cpurate", "cpuusage", "cpuload", "cpuutil", "cpupersent",
            "cpupercent", "cpupercentage", "cpuratio", "cpuloadrate", "cpuloadavg")
MEM_KEYS = ("memrate", "memusage", "memusedrate", "mempercent", "memutil",
            "memoryrate", "memoryusage", "memorypercent", "memuserate",
            "ramusage", "ramrate", "memratio", "memoryutil")
# 这些字段虽然含 cpu/mem，但说的是核心数、总量、频率，别当利用率
PCT_SKIP = ("total", "size", "num", "core", "count", "free", "max", "min",
            "speed", "freq", "frequence", "name", "type", "temp", "vol")


def _sys_log(tag, txt):
    try:
        os.makedirs(os.path.dirname(SYS_LOG), exist_ok=True)
        with open(SYS_LOG, "a", encoding="utf-8") as f:
            f.write("%s [%s] %s\n" % (time.strftime("%H:%M:%S"), tag, (txt or "")[:3000]))
    except Exception:
        pass


def _pct_pick(d, keys):
    """在摊平的字段里挑出百分比数值（0~100），返回 (值, 字段名)"""
    best = None
    for k, v in d.items():
        kl = k.lower().replace("_", "").replace("-", "")
        if any(s in kl for s in PCT_SKIP):
            continue
        if not any(x in kl for x in keys):
            continue
        n = _num_or_none(v)
        if n is None or n < 0 or n > 100:
            continue
        exact = 0 if kl in keys else 1
        if best is None or exact < best[0]:
            best = (exact, n, k)
    if not best:
        return None
    return best[1], best[2]


def _lan_num(name):
    m = re.search(r"(\d+)$", name or "")
    return int(m.group(1)) if m else 99


# 官方「网口状态」页（systeminfo_049）的字段口径，逆向自固件前端 chunks/3.js：
#   EthPortStatus: 1=未连接，0=已连接（官方代码 portStatus = 1==st ? "未连接" : "已连接"）
#   EthPortSpeed/EthPortMaxSpeed: 0=AUTO，1..6 → 10/100/1000/2500/5000/10000 Mbps
#   EthPortSendRate/EthPortRecvRate: 该口实时上/下行；EthPortUpStream: 1=上行口(WAN 方向)、0=下行口
ETH_SPEEDS = {0: "AUTO", 1: "10", 2: "100", 3: "1000", 4: "2500", 5: "5000", 6: "10000"}


def _port_caps():
    """每口标称速率能力 {端口名: "2500"}，来自 initial_info_json.DeviceSummary。

    格式如 "W-2.5-WAN,E-2.5-LAN1,E-1-LAN2,E-1-LAN3"：
    W=广域网口、E=以太网口，中段是速率档（2.5→2500、1→1000），尾段是固件口名。
    官方 App 网口状态页显示的 LAN「1000Mbps」就是这份数据（固件 Web 接口里
    找不到任何 LAN 协商速率字段，见诊断输出）。
    """
    def go():
        caps = {}
        try:
            # initial_info_json 免登录可读，不能用 _raw_get（前置 ensure 会拒绝未登录）
            _st, txt = req("/?_type=hiddenScene&_tag=initial_info_json", timeout=6)
            ds = ""
            m = re.search(r'"DeviceSummary"\s*:\s*"([^"]+)"', txt or "")
            if m:
                ds = m.group(1)
            for tok in ds.replace("，", ",").split(","):
                parts = [x.strip() for x in tok.strip().split("-") if x.strip()]
                if len(parts) != 3:
                    continue
                try:
                    mbps = int(round(float(parts[1]) * 1000))
                except Exception:
                    continue
                if mbps <= 0:
                    continue
                caps[parts[2].upper()] = str(mbps)
        except Exception:
            pass
        return caps
    try:
        return _cached("portcaps", 300, go)
    except Exception:
        return {}


def _ethport_speed():
    """登录后读 vue_internet_ethport_data（官方网口状态页同款），返回 {_InstID: {...}}"""
    def go():
        out = {}
        txt = _raw_get("/?_type=vueData&_tag=vue_internet_ethport_data&_=%d" % _now_ms())
        info = groups(txt)
        items = []
        for _g, arr in info.items():
            items.extend(arr)
        state = {}
        for it in items:
            inst = (it.get("_InstID") or "").strip()
            if not inst or "EthPortStatus" not in it:
                continue
            try:
                spd = int(float(it.get("EthPortSpeed") or 0))
                mx = int(float(it.get("EthPortMaxSpeed") or 0))
            except Exception:
                spd = mx = 0
            state[inst] = {
                # 固件有两种口径：0..6 编码值，或直接给 1000 这种 Mbps，统一交给 _speed_of
                "speed": _speed_of(it.get("EthPortSpeed")),
                "max": _speed_of(it.get("EthPortMaxSpeed")),
                "up": _num_or_none(it.get("EthPortSendRate")),
                "down": _num_or_none(it.get("EthPortRecvRate")),
                # 固件这两个字段本身就是 "12.34 KB/s" 这种带单位的字符串，
                # 数值只用于判断“有没有流量”，显示要保留原文
                "upText": (it.get("EthPortSendRate") or "").strip(),
                "downText": (it.get("EthPortRecvRate") or "").strip(),
                "upstream": (it.get("EthPortUpStream") or "").strip() == "1",
            }
        return state
    try:
        return _cached("ethspeed", 5, go)
    except Exception:
        return {}


def _speed_of(v):
    """EthPortSpeed 一类的取值 → "10"/"100"/"1000"

    这台固件有两种口径混着来：编码值（0=AUTO，1..6 → 10/100/1000/2500/5000/10000）
    和直接用 Mbps 的数值（1000、100 这种）。两种都认，0/AUTO 视为没上报。
    """
    s = str(v or "").strip()
    if not s:
        return ""
    try:
        n = int(float(s))
    except Exception:
        return ""
    if n in ETH_SPEEDS:
        return "" if ETH_SPEEDS[n] == "AUTO" else ETH_SPEEDS[n]
    if n in (10, 100, 1000, 2500, 5000, 10000):
        return str(n)
    return ""


def _speed_any(item, skip_max=True):
    """从对象里扫任意 *speed* 字段（固件字段名不同也能兜住）；skip_max 时跳过最高速率"""
    for k, v in (item or {}).items():
        lk = str(k).lower()
        if "speed" not in lk:
            continue
        if skip_max and "max" in lk:
            continue
        s = _speed_of(v)
        if s:
            return s
    return ""


def _wan_speed_hint():
    """WAN 协商速率兜底：首页 OBJ_HOME_BASICINFO_ID.WANSpeed（「连接详情」卡用的就是它）"""
    def go():
        try:
            home = vget("device", "vue_home_device_data")
            basic = (home.get("OBJ_HOME_BASICINFO_ID") or [{}])[0]
            v = str(basic.get("WANSpeed") or "").strip()
            try:
                return str(int(float(v)))
            except Exception:
                return v
        except Exception:
            return ""
    try:
        return _cached("wanspeed", 8, go)
    except Exception:
        return ""


def read_ports():
    """网口列表：[{name, fw, if, wan, link, linkKnown, devs}]，按 WAN、LAN1..LANn 排序

    name = 机身丝印名（已按 PORT_SWAP 校正），fw = 固件里的别名（LAN1/LAN2/LAN3），
    if = 接口名（eth1..eth3），设备归属就按 if 精确匹配。
    """
    st, txt = req(ports_path(), timeout=6)
    if st != 200:
        raise RuntimeError("网口状态接口返回 HTTP %s" % st)
    try:
        data = (json.loads(txt).get("data") or {})
    except Exception:
        raise RuntimeError("网口状态解析失败（原始响应已存 logs/sysstat.log）")
    info = data.get("OBJ_ETHPORT_INFO_ID") or []
    state = {}
    for x in data.get("OBJ_ETHPORT_STATE_ID") or []:
        state[x.get("_InstID", "")] = x
    out = []
    sp = _ethport_speed()
    for p in info:
        inst = p.get("_InstID", "")
        st_item = state.get(inst) or {}
        alias = (p.get("EthPortAliasName") or p.get("ETHPortIFName") or "").strip()
        # WanType：1=WAN1（机身 WAN 口）、2=WAN2（被设成第二个 WAN 的 LAN 口）、-1/空=普通 LAN
        try:
            wtv = int(float(str(p.get("WanType"))))
        except Exception:
            wtv = None
        wan = wtv == 1 or alias.upper().startswith("ETH_WAN")
        fw = "WAN" if wan else (alias or "LAN")
        name = fw if wan else PORT_SWAP.get(fw.upper(), fw)
        stv = str(st_item.get("EthPortStatus", ""))
        # 官方口径：1=未连接，0=已连接（逆向 chunks/3.js 的 portStatus 逻辑）
        link_known = stv != ""
        link = link_known and stv == "0"
        row = {
            "name": name,
            "fw": fw,
            "if": p.get("ETHPortIFName", ""),
            "wan": wan,
            "wanType": wtv,
            "link": link,
            "linkKnown": link_known,
            "has": True,
            "devs": 0,
        }
        spd = dict(sp.get(inst) or {})
        # 速率兜底链：ethport_data → 同一份 WANSTATUS 响应里的 INFO / STATE 字段。
        # 实测这台固件 ethport_data 的 EthPortSpeed 常报 0(AUTO)，但 INFO 里带着真实值，
        # 只认一个接口就会出现「网口实况速率未知、连接详情却有 1000」。
        if not spd.get("speed"):
            for src in (p, st_item):
                lab = _speed_any(src) or _speed_of(src.get("EthPortSpeed"))
                if lab:
                    spd["speed"] = lab
                    spd["speedFrom"] = "port"
                    break
        if not spd.get("max"):
            for src in (p, st_item):
                lab = _speed_any(src, skip_max=False) or _speed_of(src.get("EthPortMaxSpeed")) \
                    or _speed_of(src.get("EthPortSpeed"))
                if lab:
                    spd["max"] = lab
                    break
            # 最后兜一层：口的标称速率能力（DeviceSummary，按机身丝印名对齐），
            # 官方 App 网口状态页同款口径
            if not spd.get("max"):
                cap = _port_caps().get(name.upper()) or _port_caps().get(fw.upper())
                if cap:
                    spd["max"] = cap
                    spd["maxFrom"] = "caps"
        if spd:
            row.update(spd)
        out.append(row)
    # WAN 口最后再兜一层：首页 WANSpeed（和「连接详情 → 协商速率」同源）
    wan_row = next((r for r in out if r.get("wan")), None)
    if wan_row is not None and not wan_row.get("speed"):
        hint = _wan_speed_hint()
        if hint:
            wan_row["speed"] = hint
            wan_row["speedFrom"] = "wanbasic"
    out.sort(key=lambda x: (0 if x["wan"] else 1, _lan_num(x["name"])))
    return out


def api_sysstat(force=False):
    """概览用：CPU 负载、内存占用、每个网口是否插线"""
    now = time.time()
    cur = S.get("sys") or {}
    if cur:
        hit = cur.get("cpu") is not None or cur.get("mem") is not None
        ttl = 4 if (hit or not S.get("logged")) else 60
        if not force and cur.get("at") and now - cur["at"] < ttl:
            d = dict(cur)
            d["cached"] = True
            return d

    ports, perr = [], None
    try:
        ports = read_ports()
    except Exception as e:
        perr = str(e)
        _sys_log("ports-err", perr)

    # 连线状态现在直接采用官方口径（EthPortStatus：0=已连接、1=未连接，与官方 App 网口状态页一致）；
    # 设备归属只用于“N 台”角标；WAN 口额外取 WANStatus 显示联网文案。
    if ports and S.get("logged"):
        try:
            wired = _wired_clients()
            for p in ports:
                p["devs"] = sum(1 for c in wired if _on_port(c, p))
        except Exception:
            pass
        try:
            home = vget("device", "vue_home_device_data")
            basic = (home.get("OBJ_HOME_BASICINFO_ID") or [{}])[0]
            wst = (basic.get("WANStatus") or "").strip()
            if wst:
                for p in ports:
                    if p["wan"]:
                        p["wanStatus"] = wst
        except Exception:
            pass

    cpu = mem = None
    cpu_key = mem_key = ""
    src = None
    tried = []
    if S.get("logged"):
        order = list(SYS_SOURCES)
        last = cur.get("path")
        if last:                                   # 上次命中的接口优先
            order.sort(key=lambda x: 0 if x[0] == last else 1)
        for path, name in order:
            try:
                st, txt = req(path, timeout=8)
            except Exception as e:
                tried.append(name)
                continue
            if st != 200 or _dead(txt):
                tried.append(name)
                continue
            d = _kv_pairs(txt)
            if not d:
                tried.append(name)
                continue
            c = _pct_pick(d, CPU_KEYS)
            m = _pct_pick(d, MEM_KEYS)
            if not c and not m:
                tried.append(name)
                _sys_log("miss:" + name, ",".join(list(d)[:40]))
                continue
            src = name
            if c:
                cpu, cpu_key = int(round(c[0])), c[1]
            if m:
                mem, mem_key = int(round(m[0])), m[1]
            S["sys_path"] = path
            _sys_log("hit:" + name, "cpu=%s(%s) mem=%s(%s) 字段=%s"
                     % (cpu, cpu_key, mem, mem_key, ",".join(list(d)[:40])))
            break

    out = {
        "ok": True,
        "at": now,
        "ports": ports,
        "cpu": cpu,
        "mem": mem,
        "cpuKey": cpu_key,
        "memKey": mem_key,
        "src": src,
        "path": S.get("sys_path") if src else None,
        "tried": tried,
        "portErr": perr,
    }
    if cpu is None and mem is None:
        if not S.get("logged"):
            out["reason"] = "登录后读取"
        else:
            out["reason"] = "这台固件没有在网页接口中提供 CPU/内存数据"
    S["sys"] = out
    return out


def _on_port(c, p):
    """这台有线设备是否接在这个网口上。

    首选 OBJ_CLIENTS_ID[].Interface（eth1/eth2/eth3，实测准确：台式机 eth2、NAS eth3），
    没有该字段时退回 InterfaceType 里的 LAN1/eth1 字样匹配。
    """
    pif = (p.get("if") or "").strip().lower()
    cif = (c.get("port") or "").strip().lower()
    if cif and pif:
        return cif == pif
    s = (c.get("iface") or "").strip().upper()
    if not s or "802.11" in s or "WLAN" in s or "WIFI" in s:
        return False
    for nm in (p.get("name"), p.get("fw")):
        nm = (nm or "").strip().upper()
        if nm and nm in s:
            return True
    return bool(pif) and pif.upper() in s


# 轻量缓存：终端列表 5 秒、局域网配置 60 秒、网口表 15 秒
_CACHE = {}


def _cached(key, ttl, fn):
    now = time.time()
    cur = _CACHE.get(key)
    if cur and now - cur[0] < ttl:
        return cur[1]
    v = fn()
    _CACHE[key] = (now, v)
    return v


def _clients_raw():
    return _cached("clients", 5,
                   lambda: vget("clients", "vue_client_data")) or {}


def _lan_net():
    """路由器这边的局域网参数：网关/掩码/DNS/DHCP 池"""
    try:
        return _cached("lannet", 60, api_lan)
    except Exception:
        return {}


def _ipv6_list(c):
    """终端拿到的 IPv6 地址：全局地址排前面，去掉 :: 和重复项"""
    raw = (c.get("IPV6Addr") or "") + ";" + (c.get("IPV6GuaAddr") or "")
    out = []
    for x in raw.replace(",", ";").split(";"):
        x = x.strip()
        if not x or x == "::" or x in out:
            continue
        out.append(x)
    out.sort(key=lambda a: (a.lower().startswith("fe80"), len(a)))
    return out[:3]


def _port_name_of(ifn):
    """eth2 → 机身丝印 LAN1（走网口表，失败就原样返回接口名）"""
    ifn = (ifn or "").strip()
    if not ifn:
        return ""
    try:
        ports = _cached("ports", 15, read_ports)
    except Exception:
        ports = []
    for p in ports:
        if (p.get("if") or "").lower() == ifn.lower():
            return p.get("name") or ifn
    return ifn


def _clients_split():
    """全部在线设备拆成 (有线, 总数)；无线靠 InterfaceType 里的 802.11 识别"""
    try:
        raw = _clients_raw()
    except Exception:
        return [], 0
    wired, total = [], 0
    for c in raw.get("OBJ_CLIENTS_ID", []):
        total += 1
        iface = c.get("InterfaceType") or ""
        if "802.11" in iface:
            continue
        _v = VENDOR_DB.get((c.get("MACAddress") or "").upper()) or {}
        wired.append({
            "name": c.get("HostName") or "未知设备",
            "alias": c.get("AliasName") or "",
            "ip": c.get("IPAddress", ""),
            "mac": c.get("MACAddress", ""),
            "iface": iface,
            "port": c.get("Interface") or "",      # eth1 / eth2 / eth3：真正接在哪个口
            "ipv6": _ipv6_list(c),
            "last": (c.get("LastConnection") or "").replace("  ", " "),
            "up": c.get("UpRate", ""),
            "down": c.get("DownRate", ""),
            "online": fmt_dur(c.get("OnlineDuration")),
            "vendor": _v.get("vendor", ""),
            "dtype": _v.get("type", ""),
        })
    return wired, total


def _band_map():
    """MAC → 2.4G / 5G。取 localnet_lan_info_lua 里的 Band（1=2.4G，2=5G），20 秒缓存"""
    def go():
        txt = _raw_get("/?_type=vueData&_tag=localnet_lan_info_lua&_=%d" % _now_ms())
        out = {}
        for _g, items in groups(txt).items():
            for it in items:
                mac = (it.get("MACAddress") or "").strip().upper()
                band = (it.get("Band") or "").strip()
                if mac and band in ("1", "2"):
                    out[mac] = "2.4G" if band == "1" else "5G"
        return out
    try:
        return _cached("band", 20, go)
    except Exception:
        return {}


def _client_by_mac(mac):
    mac = (mac or "").strip().upper()
    for c in _clients_raw().get("OBJ_CLIENTS_ID", []):
        if (c.get("MACAddress") or "").strip().upper() == mac:
            return c
    return {}


def _wired_clients():
    return _clients_split()[0]


def api_port(name):
    """单个网口详情：WAN 口显示连接的网络，LAN 口显示接在上面的有线设备"""
    name = (name or "").strip().upper()
    if not name:
        raise ValueError("缺少网口名")
    ports = api_sysstat().get("ports") or []
    p = None
    for x in ports:
        if x["name"].upper() == name:
            p = x
            break
    if not p:
        raise ValueError("没有这个网口")

    if p["wan"]:
        data = api_all()
        wan = data.get("wan") or {}
        ip = wan.get("ip") or ""
        private = ip.startswith(("10.", "192.168.", "172.16.", "172.17.", "172.18.",
                                 "172.19.", "172.2", "172.30.", "172.31."))
        return {
            "ok": True, "name": p["name"], "link": p["link"], "wan": True,
            "speed": p.get("speed", ""), "max": p.get("max", ""),
            "rx": p.get("down"), "tx": p.get("up"),
            "net": {
                "status": wan.get("status", ""),
                "type": wan.get("type", ""),
                "conn": wan.get("conn", ""),
                "ip": ip,
                "mask": wan.get("mask", ""),
                "gw": wan.get("gw", ""),
                "dns": wan.get("dns", ""),
                "user": wan.get("user", ""),
                "speed": wan.get("speed", ""),
                "uptime": wan.get("uptime", ""),
                "up": wan.get("up", ""),
                "down": wan.get("down", ""),
                "private": private,
            },
            "clients": [],
        }

    wired, total = _clients_split()
    mine = [c for c in wired if _on_port(c, p)]
    # 固件不给端口归属时（Interface 缺失），退回“全部有线设备”
    iface_known = any(_on_port(c, x) for c in wired for x in ports)
    rows = []
    for c in (mine if iface_known else wired):
        r = dict(c)
        r["portName"] = p["name"] if iface_known else _port_name_of(c.get("port"))
        rows.append(r)
    net = _lan_net()
    return {
        "ok": True, "name": p["name"], "link": p["link"], "wan": False,
        "speed": p.get("speed", ""), "max": p.get("max", ""),
        "rx": p.get("down"), "tx": p.get("up"),
        "clients": rows,
        "exact": bool(iface_known),
        "wiredTotal": len(wired),
        "wireless": max(0, total - len(wired)),
        "net": {
            "ip": net.get("ip") or "",
            "mask": net.get("mask") or "",
            "gw": net.get("gateway") or net.get("ip") or "",
            "dns": [x for x in (net.get("dns1"), net.get("dns2")) if x],
            "min": net.get("min") or "",
            "max": net.get("max") or "",
            "dhcpOn": net.get("dhcpOn"),
        },
    }


def api_device(mac):
    """单个终端的全部网络信息：MAC/IP/IPv6/掩码/网关/DNS/接入端口 + 实时速率"""
    mac = (mac or "").strip().upper()
    if not mac:
        raise ValueError("缺少 MAC 地址")
    path = ("/?_type=vueData&_tag=localnet_lan_detailinfo_lua_no_update_sess"
            "&MACAddress=%s&_=%d" % (urllib.parse.quote(mac), int(time.time() * 1000)))
    txt = _raw_get(path)
    g = groups(txt) if "<OBJ_" in txt else {}
    d = (g.get("OBJ_LANINFO_BYMAC") or [{}])[0]
    if not d:
        _log_raw("device:" + mac, txt)
        raise ValueError("设备详情解析失败（原始响应已存 logs/device.log）")
    c = _client_by_mac(mac)
    net = _lan_net()
    return {
        "ok": True,
        "mac": mac,
        "ip": d.get("IPAddress") or d.get("IPv4Addr") or c.get("IPAddress") or "",
        "mask": net.get("mask") or "",
        "gw": net.get("gateway") or net.get("ip") or "",
        "dns": [x for x in (net.get("dns1"), net.get("dns2")) if x],
        "ipv6": _ipv6_list(c),
        "port": _port_name_of(c.get("Interface")),
        "band": _band_map().get(mac, "") if "802.11" in (c.get("InterfaceType") or "") else "",
        "iface": c.get("InterfaceType") or "",
        "last": (c.get("LastConnection") or "").replace("  ", " "),
        "up": int(round(_fnum(d.get("UploadSpeed")))),
        "down": int(round(_fnum(d.get("DownloadSpeed")))),
        "rx": int(round(_fnum(d.get("BytesReceived")))),
        "tx": int(round(_fnum(d.get("BytesSent")))),
        "online": int(round(_fnum(d.get("OnlineTimes")))),
        "active": (d.get("Active") or "1") == "1",
        "type": d.get("DisplayedType") or "",
        "vendor": d.get("DisplayedVendor") or "",
        "keys": ",".join(sorted(d.keys())[:40]),
        "ts": int(time.time()),
    }


# ---------- 厂商识别：给在线设备列表换品牌图标 ----------
#
# 厂家名称只有一个来源：单机详情接口
#   GET /?_type=vueData&_tag=localnet_lan_detailinfo_lua_no_update_sess&MACAddress=<MAC>
#   -> OBJ_LANINFO_BYMAC 里的 DisplayedVendor / DisplayedType
# 这个接口带 no_update_sess，不轮换会话令牌，可以放心逐个补（但仍排队走 ROUTER 锁）。
# 结果按 MAC 落盘缓存，30 天内不再重复请求：设备列表页首屏就能直接出图标。

VENDOR_FILE = os.path.join(BASE_DIR, "logs", "vendors.json")
VENDOR_TTL = 30 * 86400


def _vendor_load():
    try:
        with open(VENDOR_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _vendor_save():
    try:
        tmp = VENDOR_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(VENDOR_DB, f, ensure_ascii=False, indent=0, sort_keys=True)
        os.replace(tmp, VENDOR_FILE)
    except Exception:
        pass


VENDOR_DB = _vendor_load()


def _vendor_of(mac):
    """返回 (厂商, 设备类型, 设备名)，都可能是空串"""
    path = ("/?_type=vueData&_tag=localnet_lan_detailinfo_lua_no_update_sess"
            "&MACAddress=%s&_=%d" % (urllib.parse.quote(mac), int(time.time() * 1000)))
    txt = _raw_get(path)
    g = groups(txt) if "<OBJ_" in txt else {}
    d = (g.get("OBJ_LANINFO_BYMAC") or [{}])[0]
    if not d:
        raise ValueError("detail_empty")
    name = (d.get("DisplayedName") or d.get("HostName") or d.get("DevName") or "").strip()
    return ((d.get("DisplayedVendor") or "").strip(),
            (d.get("DisplayedType") or "").strip(), name)


def api_vendors(macs):
    """按 MAC 批量补厂商信息：先给缓存，缺的最多现场查 8 台，剩下的下次再来"""
    if not isinstance(macs, list):
        raise ValueError("需要 macs 列表")
    out, todo, seen = {}, [], set()
    now = time.time()
    for raw in macs[:64]:
        m = str(raw or "").strip().upper()
        if not m or m in seen:
            continue
        seen.add(m)
        rec = VENDOR_DB.get(m)
        if rec and (rec.get("ts") or 0) > now - VENDOR_TTL:
            out[m] = rec
        elif rec and not rec.get("vendor") and (rec.get("ts") or 0) > now - 3600:
            out[m] = rec          # 查过但厂家为空，1 小时内不重复查
        else:
            todo.append(m)
    for m in todo[:8]:
        try:
            vendor, dtype, dname = _vendor_of(m)
            out[m] = {"vendor": vendor, "type": dtype, "name": dname, "ts": int(now)}
        except RuntimeError:
            raise
        except Exception as e:
            out[m] = {"vendor": "", "type": "", "name": "", "ts": 0, "error": str(e)[:60]}
        VENDOR_DB[m] = out[m]
    if todo:
        _vendor_save()
    return {"ok": True, "map": out, "left": max(0, len(todo) - 8)}


# ---------- WiFi 管理：信道 / 信号强度 / Wi-Fi5 兼容网络 / 定时关闭 ----------
# 字段口径取自固件自带网页版（wlanConfig_data / vue_wifi_merger /
# vue_internet_advanced_rftimer_data），与官方 App 的这几项一一对应。

WF_RADIO = (("2.4G", "DEV.WIFI.RD1", "DEV.WIFI.AP1"), ("5G", "DEV.WIFI.RD2", "DEV.WIFI.AP5"))
WF_SIGNAL = {0: ("1", "100%", "0"), 1: ("0", "100%", "1"), 2: ("0", "20%", "2")}


def _signal_level(pe, tx):
    return {"1_100%": 0, "0_100%": 1, "0_20%": 2}.get(
        "%s_%s" % ((pe or "").strip(), (tx or "").strip()), 0)


def _wifi_parts():
    """wifiAP_data 里同时带 RD（射频功率）和 *SETTING*（信道/带宽/模式）"""
    raw = read_wifi_raw()
    radios, sets, aps = {}, {}, {}
    for items in raw.values():
        for it in items:
            inst = (it.get("_InstID") or "").strip()
            if inst.startswith("DEV.WIFI.RD"):
                radios[inst] = it
            if "AutoChannelEnabled" in it or "Channel" in it:
                sets[inst] = it
            if inst.startswith("DEV.WIFI.AP"):
                aps[inst] = it
    return radios, sets, aps


def _wf_result(txt, okmsg):
    m = re.search(r"<IF_ERRORSTR>(.*?)</IF_ERRORSTR>", txt or "")
    code = (m.group(1) if m else "SUCC").strip()
    if code and code != "SUCC":
        raise RuntimeError("路由器拒绝：%s" % code)
    return {"ok": True, "msg": okmsg}


CP_AP = (("2.4G", "AP3", 1), ("5G", "AP7", 3))


def _truthy(v):
    return str(v or "").strip().lower() in ("1", "on", "true", "enable", "enabled", "yes")


def _compat_info(with_pwd=False):
    """
    Wi-Fi5 兼容网络。字段口径与固件前端 compatible 页完全一致：
      OBJ_WLANAP_ID 是固定 4 条：[主2.4G, 兼容2.4G, 主5G, 兼容5G]，
      总开关取「兼容 2.4G」那条的 ForceWiFi（官方就是 s[1].ForceWiFi）。
    实例名正常是 DEV.WIFI.AP3 / AP7，取不到时按位置兜底，避免某版固件改名后整块空白。
    """
    out = {"force": False, "forceRaw": "", "items": [], "err": None, "found": 0}
    try:
        arr = fetch("/?_type=vueData&_tag=vue_wifi_merger&_=%d" % _now_ms()).get("OBJ_WLANAP_ID") or []
        out["found"] = len(arr)
        raw = ""
        for it in arr:
            if "ForceWiFi" in it:
                raw = it.get("ForceWiFi")
                if _truthy(raw):
                    break
        out["forceRaw"] = str(raw)
        out["force"] = _truthy(raw)
        for band, sfx, idx in CP_AP:
            node = {}
            for it in arr:
                if (it.get("_InstID") or "").upper().endswith(sfx):
                    node = it
                    break
            if not node and len(arr) > idx:
                node = arr[idx]
            if not node:
                continue
            inst = node.get("_InstID") or ""
            item = {
                "band": band, "inst": inst,
                "psk": node.get("_InstID_PSK") or (inst + ".PSK1" if inst else ""),
                "ssid": node.get("ESSID") or "",
                "on": _truthy(node.get("Enable")),
                "hidden": _truthy(node.get("ESSIDHideEnable")),
                "hasPwd": False,
            }
            if with_pwd and inst:
                try:
                    item["pwd"] = _read_psk(inst + ".PSK1", "cp" + band)
                    item["hasPwd"] = bool(item["pwd"])
                except Exception as e:
                    item["pwdErr"] = str(e)
            out["items"].append(item)
    except RuntimeError as e:
        if str(e) == "NOT_LOGGED":
            raise
        out["err"] = str(e)
    except Exception as e:
        out["err"] = str(e)
    return out


def api_wifimgr():
    """WiFi 管理：每个频段的信道 / 信号强度 + 兼容网络 + 定时关闭 + 当前模式"""
    radios, sets, aps = _wifi_parts()
    bands = []
    for name, rd, ap in WF_RADIO:
        s, r = sets.get(rd, {}), radios.get(rd, {})
        pe = s.get("PowerEnhance") or r.get("PowerEnhance")
        tx = s.get("TxPower") or r.get("TxPower")
        ch = (s.get("Channel") or "").strip()
        auto = (s.get("AutoChannelEnabled") or "") == "1" or ch.upper() in ("", "NULL", "AUTO")
        bands.append({
            "band": name,
            "level": _signal_level(pe, tx),
            "pe": pe or "", "tx": tx or "",
            "channel": "" if auto else ch,
            "auto": auto,
            "inuse": (aps.get(ap) or {}).get("ChannelInUsed") or "",
            "bw": s.get("BandWidth") or "",
            "std": s.get("Standard") or "",
            "on": (r.get("RadioStatus") or s.get("RadioStatus") or "1") == "1",
        })

    chans = {"2.4G": [], "5G": []}
    try:
        cfg = fetch("/?_type=vueData&_tag=wlanConfig_data&_=%d" % _now_ms())
        for it in (cfg.get("OBJ_CHANNEL_ID") or []):
            band = (it.get("Band") or "").strip()
            num = str(it.get("Channel") or it.get("ChanNum") or it.get("ChannelNum") or "").strip()
            if num.isdigit() and band in chans:
                chans[band].append(num)
    except Exception:
        pass
    if not chans["2.4G"]:
        chans["2.4G"] = [str(i) for i in range(1, 14)]
    if not chans["5G"]:
        chans["5G"] = ["36", "40", "44", "48", "149", "153", "157", "161", "165"]

    compat = _compat_info() if S.get("logged") else {"force": False, "items": [], "err": None}

    timer = {"on": False, "start": "23:00", "end": "07:00", "err": None}
    try:
        t = fetch("/?_type=hiddenData&_tag=vue_internet_advanced_rftimer_data&_=%d" % _now_ms())
        cfg = (t.get("OBJ_WLANTIMECFG_ID") or [{}])[0]
        one = (t.get("OBJ_WLANTIME_ID") or [{}])[0]
        timer["on"] = (cfg.get("TimerEnable") or "0") == "1"
        if (one.get("TimeStartHour") or "") != "":
            timer["start"] = "%02d:%02d" % (int(_fnum(one.get("TimeStartHour"))),
                                            int(_fnum(one.get("TimeStartMin"))))
        if (one.get("TimeEndHour") or "") != "":
            timer["end"] = "%02d:%02d" % (int(_fnum(one.get("TimeEndHour"))),
                                          int(_fnum(one.get("TimeEndMin"))))
    except Exception as e:
        timer["err"] = str(e)

    env = {}
    try:
        env = (vget("device", "vue_home_device_data").get("OBJ_GLOBAL_ENV") or [{}])[0]
    except Exception:
        pass
    return {"ok": True, "bands": bands, "channels": chans, "compat": compat,
            "timer": timer, "mode": env.get("curWorkMode") or "",
            "mesh": env.get("MeshEnable") or "0"}


def _set_radio(body, action):
    band = (body.get("band") or "2.4G").strip().upper()
    if band not in ("2.4G", "5G"):
        raise ValueError("频段不对")
    radios, sets, aps = _wifi_parts()
    rd = "DEV.WIFI.RD1" if band == "2.4G" else "DEV.WIFI.RD2"
    s, r = sets.get(rd) or {}, radios.get(rd) or {}
    if not s:
        raise RuntimeError("这台固件没有提供 %s 的信道/功率配置" % band)
    auto = (s.get("AutoChannelEnabled") or "0") == "1"
    ch = (s.get("Channel") or "").strip()
    level = _signal_level(s.get("PowerEnhance") or r.get("PowerEnhance"),
                          s.get("TxPower") or r.get("TxPower"))
    bw = s.get("BandWidth") or "Auto"
    std = s.get("Standard") or ""
    if action == "channel":
        if body.get("auto") is True:
            auto, ch = True, "NULL"
        else:
            c = str(body.get("channel") or "").strip()
            if not c.isdigit():
                raise ValueError("信道要填数字")
            auto, ch = False, c
        if body.get("bw"):
            bw = str(body.get("bw")).strip()
    else:
        try:
            level = int(body.get("level"))
        except Exception:
            raise ValueError("信号强度取值不对")
        if level not in WF_SIGNAL:
            raise ValueError("信号强度取值不对")
    pe, tx, rate = WF_SIGNAL[level]
    form = {
        "IF_ACTION": "Apply",
        "_InstID": rd,
        "Band": s.get("Band") or band,
        "Channel": "NULL" if auto else ch,
        "AutoChannelEnabled": "1" if auto else "0",
        "Standard": std,
        "PowerEnhance": pe, "TxPower": tx, "WlanRate": rate,
        "RadioStatus": s.get("RadioStatus") or r.get("RadioStatus") or "1",
    }
    if std and std != "b,g":
        form["BandWidth"] = bw
    txt = ax("/?_type=vueData&_tag=wlanConfig_data", form, timeout=25)
    what = "信道" if action == "channel" else "信号强度"
    return _wf_result(txt, "%s %s 已保存，Wi-Fi 会短暂中断几秒" % (band, what))


def _compat_pwd(band):
    """读取兼容网络当前密码（点「显示密码」时才读，和主 SSID 一样按需解密）"""
    if not S.get("logged"):
        raise RuntimeError("NOT_LOGGED")
    info = _compat_info()
    if info.get("err"):
        raise RuntimeError("固件未提供兼容网络配置")
    inst, psk = "", ""
    for it in info.get("items") or []:
        if it["band"] == band:
            inst, psk = it["inst"], it.get("psk") or ""
            break
    if not inst:
        raise RuntimeError("找不到 %s 兼容网络实例" % band)

    cands = [x for x in (psk, inst + ".PSK1") if x]
    seen, tried = set(), []
    for c in cands:
        if c in seen:
            continue
        seen.add(c)
        tried.append(c)
        pwd = _read_psk(c, "cp" + band, use_cache=False)
        if pwd:
            return {"ok": True, "band": band, "pwd": pwd, "hasPwd": True, "inst": c}
    _slog_pwd("compat %s 失败，试过 %s" % (band, ",".join(tried)))
    return {"ok": True, "band": band, "pwd": "", "hasPwd": False,
            "error": "路由器没有返回 %s 兼容网络的密码（实例 %s），可能这台固件把密码存在别处"
                     % (band, inst)}


def _set_compat(body):
    force = 1 if body.get("force") else 0
    given = {i.get("band"): i for i in (body.get("items") or [])}
    m = fetch("/?_type=vueData&_tag=vue_wifi_merger&_=%d" % _now_ms())
    arr = m.get("OBJ_WLANAP_ID") or []
    a, b = rand16(), rand16()
    form = {"IF_ACTION": "Apply", "SubmitFlag": "SSIDIY", "ForceWiFi": str(force)}
    for band, sfx, ap in (("2.4G", "I", "AP3"), ("5G", "Y", "AP7")):
        old = {}
        for it in arr:
            if (it.get("_InstID") or "").upper().endswith(ap):
                old = it
                break
        if not old:
            idx = 1 if ap == "AP3" else 3
            old = arr[idx] if len(arr) > idx else {}
        it = given.get(band) or {}
        ssid = (it.get("ssid") or old.get("ESSID") or "").strip()
        on = 1 if it.get("on", old.get("Enable") == "1") else 0
        if on and not force:
            on = 1
        pwd = (it.get("pwd") or "").strip()
        if ssid and not (1 <= len(ssid) <= 32):
            raise ValueError("%s 兼容网络名称需为 1–32 个字符" % band)
        if pwd and not (8 <= len(pwd) <= 63):
            raise ValueError("%s 兼容网络密码需为 8–63 位" % band)
        form["ESSID" + sfx] = ssid
        form["Enable" + sfx] = str(on)
        form["ESSIDHideEnable" + sfx] = "1" if it.get("hidden") else (
            "1" if (it.get("hidden") is None and old.get("ESSIDHideEnable") == "1") else "0")
        for k in ("BeaconType", "WPAAuthMode", "WPAEncryptType"):
            if old.get(k):
                form[k + sfx] = old.get(k)
        if old.get("11iAuthMode"):
            form["11iAuthMode" + sfx] = old.get("11iAuthMode")
        if old.get("11iEncryptType"):
            form["11iEncryptType" + sfx] = old.get("11iEncryptType")
        if pwd:
            enc = enc_para(pwd, a, b)
            form["KeyPassphrase" + sfx] = enc
            form["HideKeyPassphrase" + sfx] = enc
            form["_InstID_PSK" + sfx] = (old.get("_InstID") or ("DEV.WIFI." + ap)) + ".PSK1"
        elif on and force and not old.get("ESSID"):
            raise ValueError("%s 兼容网络要填密码（8 位以上）才能开启" % band)
    if form.get("KeyPassphraseI") or form.get("KeyPassphraseY"):
        form["encode"] = enc_key(a, b)   # 与官方一致：改动密码时带上本次加密密钥
    txt = ax("/?_type=vueData&_tag=vue_wifi_merger", form, timeout=25)
    return _wf_result(txt, "Wi-Fi5 兼容网络已保存")


def _set_rftimer(body):
    def hm(v, d):
        v = (v or d).strip()
        m = re.match(r"^(\d{1,2}):(\d{2})$", v)
        if not m:
            raise ValueError("时间要填成 23:00 这样")
        h, mi = int(m.group(1)), int(m.group(2))
        if h > 23 or mi > 59:
            raise ValueError("时间超出范围")
        return h, mi
    sh, sm = hm(body.get("start"), "23:00")
    eh, em = hm(body.get("end"), "07:00")
    form = {"TimeStartHour": sh, "TimeStartMin": sm, "TimeEndHour": eh, "TimeEndMin": em,
            "TimerEnable": 1 if body.get("on") else 0, "IF_ACTION": "Apply", "_InstID": ""}
    txt = ax("/?_type=hiddenData&_tag=vue_internet_advanced_rftimer_data", form, timeout=20)
    return _wf_result(txt, "Wi-Fi 定时关闭已保存")


def set_wifimgr(body):
    action = (body.get("action") or "").strip()
    if action in ("channel", "signal"):
        return _set_radio(body, action)
    if action == "compat":
        return _set_compat(body)
    if action == "timer":
        return _set_rftimer(body)
    if action == "compatpwd":
        return _compat_pwd(body.get("band") or "2.4G")
    raise ValueError("未知操作")


def api_limits():

    """全部限速规则 + 全局 QoS 开关（限速值 Mbps，路由内是 Kbps）"""
    txt = _raw_get("/?_type=vueData&_tag=localnet_qosdyn_lua&_=%d" % int(time.time() * 1000))
    g = groups(txt) if "<OBJ_" in txt else {}
    glob = (g.get("OBJ_QOSDYN_ID") or [{}])[0]
    rules = {}
    for r in g.get("OBJ_QOS_BCRULE_ID", []):
        mac = (r.get("MACDev") or "").strip().upper()
        if not mac:
            continue
        rules[mac] = {
            "inst": r.get("_InstID", ""),
            "up": int(round(_fnum(r.get("BandwithRateMaxUp")) / 1000.0)),
            "down": int(round(_fnum(r.get("BandwithRateMaxDown")) / 1000.0)),
        }
    if not g:
        _log_raw("limits", txt)
    return {"ok": True, "enable": (glob.get("Enable") or "0") == "1", "rules": rules}


def _rule_inst(mac):
    """查这个 MAC 已有规则实例名（有规则时接口返回 ViewName）"""
    try:
        txt = _raw_get("/?_type=vuejsonData&_tag=localnet_qosdyn_rulebymac&_InstID=%s"
                       % urllib.parse.quote(mac))
        info = json.loads(txt)
        arr = info.get("OBJ_QOS_BCRULE_BYMAC") or []
        if arr:
            return (arr[0].get("ViewName") or "").strip() or None
    except Exception:
        pass
    return None


def set_limit(body):
    """设置/取消单设备限速：up/down 单位 Mbps，都为 0 表示取消限速"""
    mac = (body.get("mac") or "").strip().upper()
    if not mac:
        raise ValueError("缺少 MAC 地址")
    up = max(0, int(round(_fnum(body.get("up")))))
    down = max(0, int(round(_fnum(body.get("down")))))
    inst = _rule_inst(mac)
    path = "/?_type=vueData&_tag=localnet_qosdyn_bandwithrule_lua"

    if up == 0 and down == 0:
        if not inst:
            return {"ok": True, "cleared": True, "enable": api_limits_safe()}
        txt = ax(path, {"IF_ACTION": "Delete", "_InstID": inst}, timeout=15)
        ok = (xml_field(txt, "IF_ERRORSTR") or "").upper().startswith("SUCC")
        if not ok:
            _log_raw("clear:" + mac, txt)
        return {"ok": ok, "cleared": True, "enable": api_limits_safe(),
                "error": None if ok else (xml_field(txt, "IF_ERRORSTR") or "路由器拒绝了这次修改")}

    form = {
        "MACDev": mac,
        "BandwithRateMaxUp": str(up * 1000),
        "BandwithRateMaxDown": str(down * 1000),
        "UserName": mac,
        "IF_ACTION": "Apply",
        "_InstID": inst or "-1",
    }
    txt = ax(path, form, timeout=15)
    ok = (xml_field(txt, "IF_ERRORSTR") or "").upper().startswith("SUCC")
    if not ok:
        _log_raw("set:" + mac, txt)
    return {"ok": ok, "up": up, "down": down, "inst": inst or "-1",
            "enable": api_limits_safe() if ok else None,
            "error": None if ok else (xml_field(txt, "IF_ERRORSTR") or "路由器拒绝了这次修改")}


def api_limits_safe():
    try:
        return api_limits().get("enable")
    except Exception:
        return None



# ---------- 防蹭网（接入控制 acl*）与网络设置（addr_manager / static_bindAddr） ----------
# 接口来自厂商前端 bundle：vuejsonData&_tag=aclmode_data / aclrule_data / aclauth_stadata
#                              vueData&_tag=addr_manager_data / static_bindAddr_data

SEC_LOG = os.path.join(BASE_DIR, "logs", "security.log")
MODE_NAMES = {0: "密码接入", 1: "授权接入", 2: "白名单接入"}


def _slog(tag, txt):
    try:
        os.makedirs(os.path.dirname(SEC_LOG), exist_ok=True)
        with open(SEC_LOG, "a", encoding="utf-8") as f:
            f.write("%s [%s] %s\n" % (time.strftime("%H:%M:%S"), tag, (txt or "")[:3000]))
    except Exception:
        pass


def _jget(path):
    """vuejsonData 接口返回 JSON；个别固件会包一层 XML，这里都兜住"""
    txt = _raw_get(path)
    try:
        return json.loads(txt)
    except Exception:
        g = groups(txt)
        if g:
            return g
        _slog("jsonfail:" + path, txt)
        raise ValueError("路由器返回的不是 JSON（原始响应已存 logs/security.log）")


def _first(d, key):
    v = (d or {}).get(key)
    if isinstance(v, dict):
        return v
    if isinstance(v, list) and v:
        return v[0]
    return {}


def _on(v):
    return str(v).strip() in ("1", "true", "True", "on")


def _code(txt):
    """vuejsonData 写入结果：code 0/缺省=成功，12=需要二次确认（白名单会踢掉设备）"""
    try:
        d = json.loads(txt)
    except Exception:
        return None, {}
    try:
        c = int(str(d.get("code", "0")))
    except Exception:
        c = 0
    return c, (d.get("data") or {})


def _now_ms():
    return int(time.time() * 1000)


def api_security():
    """防蹭网：模式 + 黑/白名单 + 待授权设备"""
    doc = _jget("/?_type=vuejsonData&_tag=aclmode_data&_=%d" % _now_ms())
    acc = _first(doc, "OBJ_ACCESSCONTROL_ID")
    try:
        mode = int(str(acc.get("AccControlMode", "0")).strip() or 0)
    except Exception:
        mode = 0
    # 固件把 ACL 策略挂在 AP 对象上（OBJ_WLANAP_ID.ACLPolicy），aclrule_data 的规则条目
    # 本身经常没有 ACLPolicy 字段 —— 之前按 policy=="Ban" 过滤，结果名单永远是空的
    ap_pol = ""
    mf_groups = {}
    try:
        # 固件口径：hiddenData（vueData 会 404）
        mf = _raw_get("/?_type=hiddenData&_tag=vue_macfilterrule_data&_=%d" % _now_ms())
        mf_groups = groups(mf) if "<OBJ_" in mf else {}
        for it in (mf_groups.get("OBJ_WLANAP_ID") or []):
            pol = (it.get("ACLPolicy") or "").strip()
            if pol:
                ap_pol = pol
                break
    except Exception as e:
        _slog("macfilterrule", str(e))

    # 规则读口以固件前端为准（chunks/4.js getAclRules）：vuejsonData&_tag=aclrule_data
    # → OBJ_ACLCFG_ID[]，每条带 ACLPolicy；XML 里若也有规则则作兜底
    src = []
    rules_note = ""
    try:
        rd = _jget("/?_type=vuejsonData&_tag=aclrule_data&_=%d" % _now_ms())
        src = list(rd.get("OBJ_ACLCFG_ID") or [])
    except Exception as e:
        rules_note = "读取失败：%s" % e
        _slog("aclrule", str(e))
    if not src:
        xml_rules = mf_groups.get("OBJ_ACLCFG_ID") or []
        if xml_rules:
            src = xml_rules
            _slog("aclrule", "aclrule_data 为空，改用 macfilterrule XML 的 %d 条" % len(xml_rules))
        elif not rules_note:
            rules_note = "路由器返回的名单是空的"

    rules = []
    try:
        for r in src:
            mac = (r.get("MACAddress") or "").strip().upper()
            if not mac or any(x["mac"] == mac for x in rules):
                continue        # 同一台设备会在 2.4G / 5G 各有一条，去重
            c = _client_by_mac(mac)
            v = VENDOR_DB.get(mac) or {}
            pol = (r.get("ACLPolicy") or "").strip() or ap_pol
            if not pol:
                pol = "Allow" if mode == 2 else "Ban"
            pol = pol[:1].upper() + pol[1:].lower()
            rules.append({
                "inst": r.get("_InstID") or "",
                "mac": mac,
                "name": (r.get("DisplayedName") or r.get("Name")
                         or (c.get("AliasName") if c else "")
                         or (c.get("HostName") if c else "")
                         or v.get("name") or ""),
                "policy": pol,
                "iface": r.get("Interface") or "",
                "ip": (c.get("IPAddress") if c else "") or "",
                "vendor": v.get("vendor") or "",
                "dtype": v.get("type") or "",
                "online": bool(c),
            })
    except Exception as e:
        _slog("aclrule", str(e))
    pending, allowed = [], []
    if mode == 1:
        try:
            ad = _jget("/?_type=vuejsonData&_tag=aclauth_stadata&_=%d" % _now_ms())
            for a in (ad.get("OBJ_ACLAUTH_STA") or []):
                it = {
                    "inst": a.get("_InstID") or "",
                    "mac": (a.get("StaMac") or "").strip().upper(),
                    "name": a.get("DisplayedName") or a.get("DevName") or "",
                    "time": a.get("ActiveTime") or "",
                }
                if str(a.get("AuthMode")) == "1":
                    pending.append(it)
                else:
                    allowed.append(it)
        except Exception as e:
            _slog("aclauth", str(e))
    return {
        "ok": True,
        "mode": mode,
        "modeName": MODE_NAMES.get(mode, "密码接入"),
        "localMac": (doc.get("LocalMacAddr") or "").strip().upper(),
        "rules": rules,
        "rulesNote": rules_note,
        "pending": pending,
        "allowed": allowed,
    }


def set_security_mode(body):
    try:
        m = int(body.get("mode"))
    except Exception:
        raise ValueError("模式参数不对")
    if m not in (0, 1, 2):
        raise ValueError("模式只能是 0（密码）/1（授权）/2（白名单）")
    txt = ax("/?_type=vuejsonData&_tag=aclmode_data",
             {"IF_ACTION": "Apply", "AccControlMode": str(m)}, timeout=15)
    code, extra = _code(txt)
    if code == 12:
        return {"ok": False, "code": 12, "needConfirm": True,
                "error": "还有 %s 台设备不在白名单里，切换后它们会立刻断网。请先把要用的设备加进白名单。"
                         % (extra.get("AclAllowNum") or "若干")}
    if code not in (0, None):
        _slog("setmode:%d" % m, txt)
        return {"ok": False, "code": code, "error": "路由器拒绝（code %s）" % code}
    return {"ok": True, "mode": m, "modeName": MODE_NAMES.get(m, "")}


def acl_add(body):
    mac = (body.get("mac") or "").strip().upper()
    if not re.match(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$", mac):
        raise ValueError("MAC 地址格式不对")
    policy = "Allow" if (body.get("policy") or "").lower() == "allow" else "Ban"
    form = {
        "_InstID": "-1", "IF_ACTION": "Apply", "ACLPolicy": policy,
        "Name": (body.get("name") or mac)[:64], "MACAddress": mac,
        "Interface": "DEV.WIFI.AP1",
    }
    if policy == "Ban":
        form["ACTION_TYPE"] = "DELAUTH"     # 加黑名单时顺手把已连上的踢下线
    txt = ax("/?_type=vuejsonData&_tag=aclrule_data", form, timeout=15)
    code, _ = _code(txt)
    if code not in (0, None):
        _slog("acladd:" + mac, txt)
        return {"ok": False, "error": "路由器拒绝（code %s）" % code}
    return {"ok": True, "mac": mac, "policy": policy}


def acl_del(body):
    inst = str(body.get("inst") or "").strip()
    if not inst:
        raise ValueError("缺少规则实例")
    txt = ax("/?_type=vuejsonData&_tag=aclrule_data",
             {"IF_ACTION": "Delete", "_InstID": inst}, timeout=15)
    code, _ = _code(txt)
    if code not in (0, None):
        _slog("acldel:" + inst, txt)
        return {"ok": False, "error": "路由器拒绝（code %s）" % code}
    return {"ok": True}


def auth_action(body):
    inst = str(body.get("inst") or "").strip()
    act = int(body.get("action") or 0)
    if not inst or act not in (1, 2, 3):
        raise ValueError("参数不对")
    txt = ax("/?_type=vuejsonData&_tag=aclauth_stadata",
             {"_InstID": inst, "IF_ACTION": "Apply", "AuthAction": str(act)}, timeout=15)
    code, _ = _code(txt)
    if code not in (0, None):
        _slog("auth:%s/%d" % (inst, act), txt)
        return {"ok": False, "error": "路由器拒绝（code %s）" % code}
    return {"ok": True}


_DHCP_SW_KEYS = ("ServerEnable", "DHCPEnable", "DHCPServerEnable", "DHCPServer")


def _dhcp_state(dh, bd):
    """判断 LAN DHCP 服务器是否真的在跑，返回 (on, 字段名, 原始字段表)。

    坑（v2.8.1）：原来写成 ServerEnable 或 Dhcp4sBridgePolicyEnable 任一为 1 就算开启。
    Dhcp4sBridgePolicyEnable 是“桥接模式下的 DHCP 报文放行策略”，不是 DHCP 服务器开关，
    关掉 DHCP 后它一般还是 1，于是面板一直显示“已开启”。
    现在以 DHCP 服务器自己的开关为准，读不到才退回桥接策略；都没有则返回 None（未知）。
    """
    d1 = dh or {}
    d2 = bd or {}
    fields = {}
    for k in _DHCP_SW_KEYS:
        v = d1.get(k)
        if v is not None and str(v).strip() != "":
            fields[k] = str(v).strip()
    for k in ("Dhcp4sBridgePolicyEnable", "Dhcp4sBridgePolicy", "BridgePolicyEnable"):
        v = d2.get(k)
        if v is not None and str(v).strip() != "":
            fields[k] = str(v).strip()
    # 附带其它和开关有关的字段，方便真机对不上时一眼看出固件用的是哪个名字
    for src in (d1, d2):
        for k, v in src.items():
            if k in fields or len(str(v)) > 8:
                continue
            if re.search(r"(?i)enable|switch|policy|server", k or ""):
                fields[k] = str(v).strip()
    for k in _DHCP_SW_KEYS:
        if k in fields:
            return _on(fields[k]), k, fields
    for k in ("Dhcp4sBridgePolicyEnable", "Dhcp4sBridgePolicy", "BridgePolicyEnable"):
        if k in fields:
            return _on(fields[k]), k, fields
    return None, "", fields


def api_lan():
    """局域网 + DHCP + 静态 IP 绑定"""
    txt = _raw_get("/?_type=vueData&_tag=addr_manager_data&_=%d" % _now_ms())
    g = groups(txt)
    br = _first(g, "OBJ_BRGRP_ID")
    dh = _first(g, "OBJ_DHCPHOST_ID")
    bd = _first(g, "OBJ_DHCP4SBRIDGE_ID")
    if not br and not dh:
        _slog("lan", txt)
        raise ValueError("读不到局域网配置（原始响应已存 logs/security.log）")
    binds = []
    try:
        bt = _raw_get("/?_type=vueData&_tag=static_bindAddr_data&_=%d" % _now_ms())
        for b in (groups(bt).get("OBJ_DHCPBIND_ID") or []):
            mac = (b.get("MACAddr") or "").strip().upper()
            if not mac:
                continue
            binds.append({
                "inst": b.get("_InstID") or "",
                "name": b.get("Name") or "",
                "ip": b.get("IPAddr") or "",
                "mac": mac,
            })
    except Exception as e:
        _slog("bindlist", str(e))
    lease = (dh.get("LeaseTime") or "").strip()
    dhcp_on, dhcp_field, dhcp_fields = _dhcp_state(dh, bd)
    return {
        "ok": True,
        "ip": br.get("IPAddr") or dh.get("IPRouters") or "",
        "mask": br.get("SubMask") or "",
        "dhcpOn": dhcp_on,
        "dhcpField": dhcp_field,
        "dhcpFields": dhcp_fields,
        "gateway": dh.get("IPRouters") or br.get("IPAddr") or "",
        "min": dh.get("MinAddress") or "",
        "max": dh.get("MaxAddress") or "",
        "dns1": dh.get("DNSServer1") or "",
        "dns2": dh.get("DNSServer2") or "",
        "lease": lease,
        "leaseForever": lease == "-1",
        "binds": binds,
    }


def set_lan(body):
    cur = api_lan()

    def pick(key, fallback):
        v = body.get(key)
        return fallback if v in (None, "") else str(v).strip()

    ip = pick("ip", cur["ip"])
    mask = pick("mask", cur["mask"])
    lease = pick("lease", cur["lease"])
    if lease not in ("-1", "") and not re.match(r"^\d+$", lease):
        raise ValueError("租期要填分钟数，或 -1 表示永久")
    dhcp_on = body.get("dhcpOn")
    # 真正控制 DHCP 服务器的字段（不是桥接策略），跟着读到的字段名走
    sw_key = cur.get("dhcpField") or "ServerEnable"
    if sw_key not in _DHCP_SW_KEYS:
        sw_key = "ServerEnable"
    bridge_now = (cur.get("dhcpFields") or {}).get("Dhcp4sBridgePolicyEnable")
    form = {
        "_InstID_BRGRP": "IGD.LD1",
        "DHCPBasic": "Both",
        "IPAddr": ip,
        "SubMask": mask,
        "SubnetMask": mask,
        "IPRouters": pick("gateway", cur["gateway"] or ip),
        "MinAddress": pick("min", cur["min"]),
        "MaxAddress": pick("max", cur["max"]),
        "DNSServer1": pick("dns1", cur["dns1"]),
        "DNSServer2": pick("dns2", cur["dns2"]),
        "LeaseTime": lease or cur["lease"] or "120",
        "IF_ACTION": "Apply",
        # 桥接策略保持原样：它管的是桥接下 DHCP 报文放行，不是服务器开关
        "Dhcp4sBridgePolicyEnable": "1" if bridge_now in (None, "") else bridge_now,
    }
    if dhcp_on is True or dhcp_on is False:
        form[sw_key] = "1" if dhcp_on else "0"
    txt = ax("/?_type=vueData&_tag=addr_manager_data", form, timeout=20)
    ok = (xml_field(txt, "IF_ERRORSTR") or "").upper().startswith("SUCC")
    if not ok and sw_key in form:
        # 个别固件不认这个字段：去掉它再存一次，别把局域网设置一起拖挂
        _slog("setlan-switch", txt)
        form.pop(sw_key, None)
        txt = ax("/?_type=vueData&_tag=addr_manager_data", form, timeout=20)
        ok = (xml_field(txt, "IF_ERRORSTR") or "").upper().startswith("SUCC")
        if ok:
            return {"ok": True, "ip": ip, "mask": mask, "needRelogin": ip != cur["ip"],
                    "warn": "路由器没接受 DHCP 开关字段，局域网其他设置已保存"}
    if not ok:
        _slog("setlan", txt)
        return {"ok": False, "error": xml_field(txt, "IF_ERRORSTR") or "路由器拒绝了这次修改"}
    return {"ok": True, "ip": ip, "mask": mask, "needRelogin": ip != cur["ip"]}


def bind_add(body):
    mac = (body.get("mac") or "").strip().upper()
    ip = (body.get("ip") or "").strip()
    name = (body.get("name") or mac).strip()[:64]
    if not re.match(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$", mac):
        raise ValueError("MAC 地址格式不对")
    if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
        raise ValueError("IP 地址格式不对")
    gateway = ""
    try:
        gateway = api_lan().get("gateway") or ""
    except Exception:
        pass
    form = {"IF_ACTION": "Apply", "_InstID": "-1", "Name": name,
            "IPAddr": ip, "MACAddr": mac, "IPRouters": gateway}
    txt = ax("/?_type=vueData&_tag=static_bindAddr_data", form, timeout=15)
    ok = (xml_field(txt, "IF_ERRORSTR") or "").upper().startswith("SUCC")
    if not ok:
        _slog("bindadd:" + mac, txt)
        return {"ok": False, "error": xml_field(txt, "IF_ERRORSTR") or "路由器拒绝了这次绑定"}
    return {"ok": True}


def bind_del(body):
    inst = str(body.get("inst") or "").strip()
    if not inst:
        raise ValueError("缺少绑定实例")
    form = {"IF_ACTION": "Delete", "_InstID": inst,
            "Name": body.get("name") or "", "IPAddr": body.get("ip") or "",
            "MACAddr": body.get("mac") or "", "IPRouters": body.get("gateway") or ""}
    txt = ax("/?_type=vueData&_tag=static_bindAddr_data", form, timeout=15)
    ok = (xml_field(txt, "IF_ERRORSTR") or "").upper().startswith("SUCC")
    if not ok:
        _slog("binddel:" + inst, txt)
        return {"ok": False, "error": xml_field(txt, "IF_ERRORSTR") or "路由器拒绝了这次操作"}
    return {"ok": True}


# ---------- 远程访问：把家里的路由器映射到一个公网地址 ----------
# 路由器固件没有「WAN 侧管理」开关，所以由这台电脑做跳板：
# cloudflared 建一条出站隧道，公网域名 → https://192.168.5.1，手机在外面直接连。
# 不需要公网 IP、不需要域名、不需要在路由器上开端口。

REMOTE = {"proc": None, "url": None, "err": None, "log": [], "at": 0, "target": None}
CF_BIN = os.path.join(BASE_DIR, "bin", "cloudflared.exe")
CF_URL_RE = re.compile(r"https://[a-z0-9][a-z0-9-]*\.trycloudflare\.com")


def cf_ready():
    try:
        return os.path.getsize(CF_BIN) > 20 * 1024 * 1024
    except Exception:
        return False


def _cf_pump(p):
    try:
        for raw in iter(p.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").rstrip()
            if not line:
                continue
            REMOTE["log"].append(line[:220])
            if len(REMOTE["log"]) > 80:
                del REMOTE["log"][0]
            m = CF_URL_RE.search(line)
            if m and not REMOTE["url"]:
                REMOTE["url"] = m.group(0)
                REMOTE["err"] = None
    except Exception:
        pass


def remote_status():
    p = REMOTE["proc"]
    alive = p is not None and p.poll() is None
    if not alive and REMOTE["url"]:
        REMOTE["err"] = "通道已断开，重新开启即可"
    return {
        "ok": True,
        "running": alive,
        "url": REMOTE["url"] if alive else None,
        "target": REMOTE["target"],
        "err": REMOTE["err"],
        "ready": cf_ready(),
        "host": HOST,
        "log": REMOTE["log"][-6:],
    }


def remote_start(target=None):
    st = remote_status()
    if st["running"]:
        return st
    if not cf_ready():
        raise RuntimeError("远程组件还没准备好：bin/cloudflared.exe 不完整（需要约 53MB）")
    tgt = (target or "").strip() or ("https://%s" % HOST)
    cmd = [CF_BIN, "tunnel", "--url", tgt, "--no-autoupdate",
           "--loglevel", "info", "--http-host-header", HOST]
    if tgt.lower().startswith("https://"):
        cmd.append("--no-tls-verify")
    flags = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW
    REMOTE.update(url=None, err=None, log=[], at=time.time(), target=tgt)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, creationflags=flags)
    REMOTE["proc"] = p
    threading.Thread(target=_cf_pump, args=(p,), daemon=True).start()
    for _ in range(60):          # 最多等 30 秒拿地址
        if REMOTE["url"] or p.poll() is not None:
            break
        time.sleep(0.5)
    if not REMOTE["url"]:
        if p.poll() is not None:
            REMOTE["err"] = "通道启动失败：" + (" / ".join(REMOTE["log"][-3:]) or "未知原因")
        else:
            REMOTE["err"] = "还在和 Cloudflare 握手，几秒后再刷新一次"
    return remote_status()


def remote_stop():
    p = REMOTE["proc"]
    if p is not None and p.poll() is None:
        try:
            p.terminate()
            for _ in range(25):
                if p.poll() is not None:
                    break
                time.sleep(0.1)
            if p.poll() is None:
                p.kill()
        except Exception:
            pass
    REMOTE.update(proc=None, url=None, err=None, target=None)
    return remote_status()


def reboot():
    """重启路由器。「系统忙」是设备瞬时状态（cmret_003/005），稍等重试即可。"""
    ensure()
    last_err, last_id, tries = None, None, 0
    for attempt in range(3):
        tries += 1
        txt = ax("/?_type=vueData&_tag=vue_derestart_data", {"IF_ACTION": "Restart"}, timeout=15)
        err = xml_field(txt, "IF_ERRORSTR")
        eid = xml_field(txt, "IF_ERRORID")
        _log_reboot(attempt + 1, err, eid, txt)
        if not err or err.upper() in ("SUCC", "SUCCESS", "OK"):
            return {"ok": True, "attempts": tries}
        last_err, last_id = err, eid
        # 系统忙 / 1452 令牌过期：换令牌后重试
        if "系统忙" in err:
            time.sleep(5)
            continue
        if eid and str(eid).strip() == "1452":
            feel_token()
            continue
        break
    raise RuntimeError("路由器拒绝重启：%s（错误码 %s）" % (last_err, last_id or "无"))


def _log_reboot(attempt, err, eid, raw):
    try:
        p = os.path.join(BASE_DIR, "logs", "reboot.log")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write("%s\t#%d\terr=%s\tid=%s\t%s\n" % (
                time.strftime("%Y-%m-%d %H:%M:%S"), attempt, err, eid,
                (raw or "")[:300].replace("\n", " ")))
    except Exception:
        pass


# ---------- 网络工具：优化 / 排查 / 测速（实现放 nettools.py，避免本文件继续膨胀） ----------
import nettools

nettools.bind(globals())


def api_optimize():
    return nettools.api_optimize()


def api_netdiag():
    return nettools.api_netdiag()


def api_speedtest(body=None):
    return nettools.api_speedtest(body)


def api_ping(body=None):
    body = body or {}
    return nettools.api_ping(body.get("host") or "", body.get("iface") or "")


# ---------- 网口 / 双 WAN / 管理员密码（实现放 lanwan.py） ----------
import lanwan

lanwan.bind(globals())


def api_port_status():
    # 前端 2 秒轮询：服务端做 1 秒合并缓存，多端同时刷也只打一次路由器
    return _cached("portslive", 1.0, lanwan.api_ports)


def api_ports_raw():
    """网口字段诊断：这台固件到底为每个口上报了哪些字段（真机排查速率显示用）"""
    st, txt = req(ports_path(), timeout=6)
    data = {}
    try:
        data = (json.loads(txt) or {}).get("data") or {}
    except Exception:
        data = {}
    def _brief(items):
        out = []
        for it in (items or []):
            row = {}
            for k, v in it.items():
                sv = str(v)
                if len(sv) <= 24:
                    row[k] = sv
            out.append(row)
        return out
    eth = {}
    try:
        eth = _ethport_speed() or {}
    except Exception:
        eth = {}
    return {
        "ok": True,
        "status": st,
        "info": _brief(data.get("OBJ_ETHPORT_INFO_ID")),
        "state": _brief(data.get("OBJ_ETHPORT_STATE_ID")),
        "ethport": eth,
        "wanSpeed": _wan_speed_hint(),
        "caps": _port_caps(),
    }


# ---------------- 机型自动识别 ----------------

MODEL_FILE = os.path.join(BASE_DIR, "logs", "model.json")
MODEL = {"dev": "", "web": "", "sw": "", "at": 0}


def _model_load():
    """启动时把上次识别到的机型读回来（登录页在登录前就要显示）"""
    try:
        with open(MODEL_FILE, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            for k in ("dev", "web", "sw"):
                MODEL[k] = (d.get(k) or "").strip()
            MODEL["at"] = int(d.get("at") or 0)
    except Exception:
        pass


def _model_read():
    """登录后现读机型：

    * DevName（vue_home_device_data_no_update_sess → OBJ_HOME_BASICINFO_ID）
      = 产品名，如「巡天BE5100 Pro+」
    * WEBTitle / SoftwareVer（hiddenScene → initial_info_json，登录后才有）
      = 硬件型号「ZXSLC SR7110」+ 软件版本
    """
    got = {}
    try:
        st, txt = req("/?_type=vueData&_tag=vue_home_device_data_no_update_sess&_=%d"
                      % int(time.time() * 1000), timeout=8)
        if st == 200 and txt and "OBJ_HOME_BASICINFO_ID" in txt:
            inst = (_insts(txt, "OBJ_HOME_BASICINFO_ID") or [{}])[0]
            got["dev"] = (inst.get("DevName") or "").strip()
    except Exception:
        pass
    try:
        st, txt = req("/?_type=hiddenScene&_tag=initial_info_json&_=%d"
                      % int(time.time() * 1000), timeout=8)
        data = (json.loads(txt).get("data") or {})
        got["web"] = (data.get("WEBTitle") or "").strip()
        got["sw"] = (data.get("SoftwareVer") or "").strip()
    except Exception:
        pass
    got = {k: v for k, v in got.items() if v}
    if got:
        MODEL.update(got)
        MODEL["at"] = int(time.time())
        try:
            with open(MODEL_FILE, "w", encoding="utf-8") as f:
                json.dump(MODEL, f, ensure_ascii=False)
        except Exception:
            pass
    return MODEL


def api_model():
    """机型（登录页展示用，不需要登录）：已登录就现读并更新缓存，否则返回上次识别结果"""
    if S.get("logged"):
        try:
            _model_read()
        except Exception:
            pass
    dev, web = MODEL.get("dev", ""), MODEL.get("web", "")
    label = " · ".join([x for x in (dev, web) if x])
    return {"ok": True, "label": label, "dev": dev, "web": web,
            "sw": MODEL.get("sw", ""), "at": MODEL.get("at", 0),
            "logged": bool(S.get("logged"))}


_model_load()
compat.load()          # 复用上次的接口探测结果（首次为空，登录后自动补）


def api_dualwan():
    return lanwan.api_dualwan()


def api_dualwan_save(body=None):
    return lanwan.api_dualwan_set(body)


def api_admin_pwd(body=None):
    return lanwan.api_admin_pwd(body)


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ZTEHome/1.0"

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def _file(self, name, ctype):
        p = os.path.join(BASE_DIR, name)
        if not os.path.exists(p):
            self._json({"error": "missing " + name}, 404)
            return
        with open(p, "rb") as f:
            b = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def _guard(self, fn):
        try:
            self._json(fn())
        except RuntimeError as e:
            code = 401 if str(e) == "NOT_LOGGED" else 400
            self._json({"ok": False, "logged": S["logged"], "error": str(e)}, code)
        except ValueError as e:
            self._json({"ok": False, "error": str(e)}, 400)
        except Exception as e:
            self._json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 500)

    def _pwa_ok(self):
        if not PWA_TOKEN:
            return True
        for kv in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = kv.strip().partition("=")
            if k == "zt_pwa" and v == PWA_TOKEN:
                return True
        return False

    def _pwa_gate(self, p, q):
        """绑到局域网时用访问码保护面板（带 ?t=访问码 种 cookie 后免输）。"""
        if self._pwa_ok():
            return False
        t = (q.get("t") or [""])[0]
        if t and t == PWA_TOKEN:
            self.send_response(302)
            self.send_header("Set-Cookie",
                             "zt_pwa=%s; Path=/; Max-Age=31536000; HttpOnly" % PWA_TOKEN)
            self.send_header("Location", p or "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        msg = ("需要访问码。电脑上用 run-lan.bat 启动时会打印带访问码的地址，"
               "手机直接打开那个地址即可。").encode("utf-8")
        self.send_response(403)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(msg)))
        self.end_headers()
        self.wfile.write(msg)
        return True

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        p, q = u.path, urllib.parse.parse_qs(u.query)
        if self._pwa_gate(p, q):
            return
        if p in ("/", "/index.html"):
            self._file("panel.html", "text/html; charset=utf-8")
            return
        if p in ("/manifest.webmanifest", "/manifest.json"):
            self._file(os.path.join("web", "manifest.webmanifest"),
                       "application/manifest+json; charset=utf-8")
            return
        if p.startswith("/pwa/") and p.endswith(".png"):
            self._file(os.path.join("web", os.path.basename(p)), "image/png")
            return
        if p == "/api/state":
            self._json({"logged": S["logged"], "error": S["error"],
                        "kicked": S.get("kick"), "pending": S.get("pending"),
                        # 兼容层摘要：前端登录页/设置页据此显示机型与固件族
                        "family": compat.S.get("family"),
                        "modelLabel": compat.label()})
            return
        if p == "/api/sysinfo":
            self._json(api_sysinfo())
            return
        if p == "/api/all":
            self._guard(api_all)
            return
        if p == "/api/net":
            # 外网实时速率：高频轮询，失败只回 ok:false，不抛 401（前端静默保留旧值）
            self._json(api_net())
            return
        if p == "/api/wifi/pwd":
            band = (q.get("band") or ["2.4G"])[0]
            self._guard(lambda: {"ok": True, "pwd": get_wifi_pwd(band)})
            return
        if p == "/api/device":
            mac = (q.get("mac") or [""])[0]
            self._guard(lambda: api_device(mac))
            return
        if p == "/api/limits":
            self._guard(api_limits)
            return
        if p == "/api/_tag":
            tag = (q.get("tag") or [""])[0]
            self._guard(lambda: probe_tag(tag))
            return
        if p == "/api/sysstat":
            force = (q.get("force") or ["0"])[0] in ("1", "true")
            try:                       # 网口部分不依赖登录，别用 _guard 挡住
                self._json(api_sysstat(force))
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)
            return
        if p == "/api/port":
            name = (q.get("name") or [""])[0]
            self._guard(lambda: api_port(name))
            return
        if p == "/api/wifimgr":
            self._guard(api_wifimgr)
            return
        if p == "/api/security":
            self._guard(api_security)
            return
        if p == "/api/lan":
            self._guard(api_lan)
            return
        if p == "/api/optimize":
            self._guard(api_optimize)
            return
        if p == "/api/netdiag":
            # 不依赖登录：登录页也能自查「到路由器 / DNS / 外网」
            try:
                self._json(api_netdiag())
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)
            return
        if p == "/api/speedtest":
            try:
                self._json(api_speedtest({"url": (q.get("url") or [""])[0],
                                          "node": (q.get("node") or ["auto"])[0]}))
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)
            return
        if p == "/api/speednodes":
            try:
                self._json(nettools.api_speednodes())
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)
            return
        if p == "/api/ont":
            ip = (q.get("ip") or [""])[0]
            self._guard(lambda: nettools.api_ont({"ip": ip}))
            return
        if p == "/api/ports/raw":
            self._guard(api_ports_raw)
            return
        if p == "/api/ports":
            self._guard(api_port_status)
            return
        if p == "/api/model":
            self._json(api_model())
            return
        if p == "/api/compat":
            # 兼容性报告：不强制登录（未登录只回缓存/免登录识别结果）
            try:
                self._json(api_compat())
            except Exception as e:
                self._json({"ok": False, "error": str(e)})
            return
        if p == "/api/mesh":
            try:
                self._guard(api_mesh)
            except RuntimeError as e:
                self._json({"ok": False, "error": str(e)})
            return
        if p == "/api/secfw":
            try:
                self._guard(api_secfw)
            except RuntimeError as e:
                self._json({"ok": False, "error": str(e)})
            return
        if p == "/api/dualwan":
            self._guard(api_dualwan)
            return
        if p == "/api/remote/status":
            self._json(remote_status())
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        p, q = u.path, urllib.parse.parse_qs(u.query)
        if self._pwa_gate(p, q):
            return
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            data = {}

        if p == "/api/login":
            S["kick"] = None
            ok = login(data.get("password", ""), preempt=bool(data.get("preempt", True)))
            self._json({"ok": ok, "error": S["error"], "kicked": S.get("kick") if ok else None,
                        "pending": S.get("pending") if not ok else None})
            return
        if p == "/api/compat":
            self._guard(lambda: api_compat_redetect())
            return
        if p == "/api/secfw":
            try:
                self._guard(lambda: api_secfw_set(data))
            except RuntimeError as e:
                self._json({"ok": False, "error": str(e)})
            return
        if p == "/api/dualwan":
            self._guard(lambda: api_dualwan_save(data))
            return
        if p == "/api/adminpwd":
            self._guard(lambda: api_admin_pwd(data))
            return
        if p == "/api/relogin":
            ok, err = relogin_force(data.get("password") or "")
            self._json({"ok": ok, "error": err, "kicked": S.get("kick") if ok else None,
                        "needPwd": (not ok and "密码" in (err or ""))})
            return
        if p == "/api/logout":
            try:
                req("/?_type=loginData&_tag=logout_entry",
                    {"IF_LogOff": "1", "_sessionTOKEN": S["token"] or ""}, timeout=6)
            except Exception:
                pass
            JAR.clear()
            S.update(logged=False, token=None, error=None, pwd=None, wpwd={},
                     kick=None, pending=None, preempt_at=0, claim=False)
            self._json({"ok": True})
            return
        if p == "/api/vendors":
            self._guard(lambda: api_vendors(data.get("macs") or []))
            return
        if p == "/api/wifi":
            self._guard(lambda: set_wifi(data))
            return
        if p in ("/api/wifimgr", "/api/wifimgr/set"):
            self._guard(lambda: set_wifimgr(data))
            return
        if p == "/api/_probe":
            self._guard(probe_modes)
            return
        if p == "/api/reboot":
            self._guard(reboot)
            return
        if p == "/api/limit":
            self._guard(lambda: set_limit(data))
            return
        if p == "/api/security/mode":
            self._guard(lambda: set_security_mode(data))
            return
        if p == "/api/security/acl":
            self._guard(lambda: acl_del(data) if data.get("op") == "del" else acl_add(data))
            return
        if p == "/api/security/auth":
            self._guard(lambda: auth_action(data))
            return
        if p == "/api/lan/set":
            self._guard(lambda: set_lan(data))
            return
        if p == "/api/bind":
            self._guard(lambda: bind_del(data) if data.get("op") == "del" else bind_add(data))
            return
        if p == "/api/speedtest":
            try:
                self._json(api_speedtest(data))
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)
            return
        if p == "/api/ping":
            self._guard(lambda: api_ping(data))
            return
        if p == "/api/ont":
            self._guard(lambda: nettools.api_ont(data))
            return
        if p == "/api/remote/start":
            self._guard(lambda: remote_start(data.get("target")))
            return
        if p == "/api/remote/stop":
            self._json(remote_stop())
            return
        self._json({"error": "not found"}, 404)


def install_cookie(name, value):
    c = http.cookiejar.Cookie(
        0, name, value, None, False, HOST, True, False, "/", True,
        False, None, False, None, None, {},
    )
    JAR.set_cookie(c)


def adopt_session():
    """调试用：从环境变量接管一个已登录会话，免去重复输密码"""
    sid = os.environ.get("ZTE_SID")
    tok = os.environ.get("ZTE_TOKEN")
    if sid:
        install_cookie("SID_HTTPS_", sid)
        install_cookie("_TESTCOOKIESUPPORT_HTTPS_", "1")
    if tok:
        S.update(logged=True, token=tok, error=None, at=time.time())


def main():
    adopt_session()
    try:
        srv = ThreadingHTTPServer((BIND, PORT), H)
    except OSError as e:
        if getattr(e, "errno", None) in (48, 98, 10048):
            print("面板已经在运行了： http://127.0.0.1:%d/" % PORT)
            print("（关掉原来那个黑窗口再重新运行即可）")
            return
        raise
    print("=" * 56)
    print(" 中兴路由管家")
    print(" 本机: http://127.0.0.1:%d/" % PORT)
    if BIND not in ("127.0.0.1", "localhost"):
        ip = _lan_ip() or "<本机IP>"
        print(" 手机/PWA: http://%s:%d/?t=%s" % (ip, PORT, PWA_TOKEN or "<访问码>"))
    print(" 目标: %s" % HOST)
    print(" Ctrl+C 退出")
    print("=" * 56)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
