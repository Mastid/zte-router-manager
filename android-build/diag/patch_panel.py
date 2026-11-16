# -*- coding: utf-8 -*-
"""给 panel.py 追加：设备详情 / 限速查询 / 限速设置 三个接口（幂等，重复执行不会重复插入）"""
import io

P = "panel.py"
s = io.open(P, encoding="utf-8").read()
if "def api_device(" in s:
    print("already patched")
    raise SystemExit

NEW = '''# ---------- 终端详情 / 限速（厂端接口：localnet_lan_detailinfo_lua / localnet_qosdyn_*） ----------

DEV_LOG = os.path.join(BASE_DIR, "logs", "device.log")


def _log_raw(tag, txt):
    try:
        os.makedirs(os.path.dirname(DEV_LOG), exist_ok=True)
        with open(DEV_LOG, "a", encoding="utf-8") as f:
            f.write("%s [%s] %s\\n" % (time.strftime("%H:%M:%S"), tag, (txt or "")[:3000]))
    except Exception:
        pass


def _raw_get(path):
    """取原始响应文本（fetch 只返回解析后的分组，这里需要原文兜底排查）"""
    ensure()
    st, txt = req(path)
    if st != 200 or _dead(txt):
        S["logged"] = False
        if _relogin():
            st, txt = req(path)
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


def api_device(mac):
    """单个终端的详情 + 实时速率（速率单位 Kbps，累计流量单位 Byte）"""
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
    return {
        "ok": True,
        "mac": mac,
        "ip": d.get("IPAddress") or d.get("IPv4Addr") or "",
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


def reboot():'''

assert "def reboot():" in s
s = s.replace("def reboot():", NEW, 1)

OLD_ROUTE = '''        if p == "/api/wifi/pwd":
            band = (q.get("band") or ["2.4G"])[0]
            self._guard(lambda: {"ok": True, "pwd": get_wifi_pwd(band)})
            return'''
assert OLD_ROUTE in s
s = s.replace(OLD_ROUTE, OLD_ROUTE + '''
        if p == "/api/device":
            mac = (q.get("mac") or [""])[0]
            self._guard(lambda: api_device(mac))
            return
        if p == "/api/limits":
            self._guard(api_limits)
            return''', 1)

OLD_POST = '''        if p == "/api/reboot":
            self._guard(reboot)
            return'''
assert OLD_POST in s
s = s.replace(OLD_POST, OLD_POST + '''
        if p == "/api/limit":
            self._guard(lambda: set_limit(data))
            return''', 1)

open(P, "wb").write(s.encode("utf-8"))
print("patched, chars:", len(s))
