# -*- coding: utf-8 -*-
"""给 panel.py 增加：防蹭网（acl*）/ 局域网 DHCP（addr_manager）/ 静态 IP 绑定（static_bindAddr）"""
import io

P = r"C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/zte-router-lab/panel.py"
s = io.open(P, encoding="utf-8").read()

FUNCS = r'''
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
    rules = []
    try:
        rd = _jget("/?_type=vuejsonData&_tag=aclrule_data&_=%d" % _now_ms())
        for r in (rd.get("OBJ_ACLCFG_ID") or []):
            mac = (r.get("MACAddress") or "").strip().upper()
            if not mac:
                continue
            rules.append({
                "inst": r.get("_InstID") or "",
                "mac": mac,
                "name": r.get("DisplayedName") or r.get("Name") or "",
                "policy": r.get("ACLPolicy") or "",
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
    return {
        "ok": True,
        "ip": br.get("IPAddr") or dh.get("IPRouters") or "",
        "mask": br.get("SubMask") or "",
        "dhcpOn": _on(dh.get("ServerEnable")) or _on(bd.get("Dhcp4sBridgePolicyEnable")),
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
        "Dhcp4sBridgePolicyEnable": "0" if dhcp_on is False else "1",
    }
    txt = ax("/?_type=vueData&_tag=addr_manager_data", form, timeout=20)
    ok = (xml_field(txt, "IF_ERRORSTR") or "").upper().startswith("SUCC")
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


def reboot():'''

assert "def reboot():" in s
s = s.replace("def reboot():", FUNCS, 1)

# 路由：GET
old = '''        if p == "/api/limits":
            self._guard(api_limits)
            return'''
new = '''        if p == "/api/limits":
            self._guard(api_limits)
            return
        if p == "/api/security":
            self._guard(api_security)
            return
        if p == "/api/lan":
            self._guard(api_lan)
            return'''
assert old in s
s = s.replace(old, new, 1)

# 路由：POST
old2 = '''        if p == "/api/limit":
            self._guard(lambda: set_limit(data))
            return'''
new2 = '''        if p == "/api/limit":
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
            return'''
assert old2 in s
s = s.replace(old2, new2, 1)

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok", len(s))
