# -*- coding: utf-8 -*-
"""网口 / 双 WAN / 管理员密码。

以模块形式挂在 panel.py 上：`import lanwan; lanwan.bind(globals())`，
内部通过 P[...] 调用面板已有的路由器访问函数，避免循环导入。

真实口径全部逆向自固件前端（chunks/3.js、chunks/1.js、chunks/4.js）：

* 网口插线 + 协商速率 + 实时流量
    GET /?_type=vueData&_tag=vue_internet_ethport_data
    OBJ_ETHPORT_INFO_ID  → EthPortAliasName / EthPortSpeed / EthPortMaxSpeed / ETHPortIFName
    OBJ_ETHPORT_STATE_ID → EthPortStatus（1=未连接，0=已连接）/ EthPortSendRate / EthPortRecvRate

* 设备在线 / 离线
    GET /?_type=vueData&_tag=localnet_lan_info_lua → OBJ_LAN_INFO_ID（Active=1 在线）

* 双 WAN
    GET  /?_type=hiddenData&_tag=vue_internet_eth_data
         OBJ_DUALWAN_BASIC_ID → BindEnable / SecWanLink / Mode / LANViewName / DevIp
         OBJ_WANLAN_ID        → LAN_name / WANSelect（主 WAN 口）
         OBJ_DUALWAN_LOADBALANCE_ID / OBJ_DUALWAN_MAL_TRSF_ID
    GET  /?_type=vueData&_tag=vue_dualwan_data → ID_WAN_COMFIG（Enable / ConnStatus / WANCTYPE …）
    POST /?_type=vueData&_tag=vue_dualwan_data（整表回填，只把 SecWanLink 换成新口）

* 管理员密码
    GET  /?_type=vueData&_tag=user_info_data → OBJ_USERINFO_ID[0].Username
    POST 同 tag：Password / NewPassword 走 AES(encodePara)，encode=RSA("r+l")
"""
import json
import re
import time

P = {}


def bind(g):
    P.update(g)


def _f(name, *a, **kw):
    fn = P.get(name)
    if not fn:
        raise RuntimeError("panel 缺少 %s" % name)
    return fn(*a, **kw)


def _now_ms():
    return int(time.time() * 1000)


def _num(v, d=0.0):
    try:
        return float(str(v).strip() or d)
    except Exception:
        return d


def _str(v):
    return (str(v) if v is not None else "").strip()


# ---------------- 网口 ----------------

def _lan_devices():
    """全部登记过的终端（含离线）：OBJ_LAN_INFO_ID"""
    try:
        txt = _f("_raw_get", "/?_type=vueData&_tag=localnet_lan_info_lua&_=%d" % _now_ms())
    except Exception:
        return [], ""
    # 注意：这里必须用 _insts —— groups() 只认 ParaName/ParaValue 包装，
    # 而 _lua 系列接口的 Instance 是平铺字段，用 groups 会解析成空表
    items = _f("_insts", txt, "OBJ_LAN_INFO_ID") or []
    out = []
    for it in items:
        mac = _str(it.get("MACAddress")).upper()
        if not mac:
            continue
        up_rate = _str(it.get("UpRate"))
        down_rate = _str(it.get("DownRate"))
        out.append({
            "mac": mac,
            "ip": _str(it.get("IPAddress")),
            "name": _str(it.get("HostName")) or _str(it.get("DevName")) or "未知设备",
            "alias": _str(it.get("AliasName")),
            "port": _str(it.get("Interface")),
            "iface": _str(it.get("InterfaceType")),
            "active": _str(it.get("Active")) == "1",
            "last": _str(it.get("LastConnection")).replace("  ", " "),
            "up": up_rate,
            "down": down_rate,
            "online": _str(it.get("OnlineDuration")),
        })
    return out, ""


def _port_of(dev, p):
    """这台设备是否接在这个网口上（与 panel._on_port 同口径）"""
    try:
        return bool(_f("_on_port", dev, p))
    except Exception:
        pass
    pif = _str(p.get("if")).lower()
    cif = _str(dev.get("port")).lower()
    return bool(pif) and pif == cif


def api_ports():
    """网口实况：每个口插不插网线、协商速率、实时流量、在用设备数、在线/离线设备"""
    ports = _f("read_ports") or []
    devs, err = _lan_devices()
    rows = []
    for p in ports:
        acc = [d for d in devs if _port_of(d, p)]
        on = [d for d in acc if d["active"]]
        off = [d for d in acc if not d["active"]]
        up, down = p.get("up"), p.get("down")
        up_txt = _str(p.get("upText"))
        down_txt = _str(p.get("downText"))
        rate_busy = (_num(up) + _num(down)) > 1024  # 数值口径兜底
        for t0 in (up_txt, down_txt):
            if t0 and _num(re.sub(r"[^\d.]", "", t0)) > 0:
                rate_busy = True
        busy = bool(on) or rate_busy
        rows.append({
            "name": p.get("name", ""),
            "wan": bool(p.get("wan")),
            "link": bool(p.get("link")),
            "linkKnown": p.get("linkKnown", True) is not False,
            "speed": p.get("speed", ""),
            "max": p.get("max", ""),
            "up": up,
            "down": down,
            "upText": up_txt,
            "downText": down_txt,
            "online": len(on),
            "offline": len(off),
            "devs": len(acc),
            "busy": busy,
            "devList": [{"name": d["alias"] or d["name"], "ip": d["ip"], "mac": d["mac"],
                         "active": d["active"], "last": d["last"], "up": d["up"],
                         "down": d["down"], "online": d["online"]} for d in acc],
        })
    wired_on = sum(1 for d in devs if d["active"] and "802.11" not in (d.get("iface") or ""))
    wired_all = sum(1 for d in devs if "802.11" not in (d.get("iface") or ""))
    return {
        "ok": True,
        "ports": rows,
        "wired": {"online": wired_on, "total": wired_all},
        "err": err,
        "at": int(time.time()),
    }


# ---------------- 双 WAN ----------------

ETH_URL = "/?_type=hiddenData&_tag=vue_internet_eth_data&_=%d"
DW_URL = "/?_type=vueData&_tag=vue_dualwan_data&_=%d"


def _port_index(ports):
    """端口序号口径与固件一致：WAN=0，LAN1..LANn 依次往后"""
    out = {}
    for i, p in enumerate(ports):
        out[i] = p
    return out


def _dual_cfg():
    """读双 WAN 配置骨架（eth_data）"""
    txt = _f("_raw_get", ETH_URL % _now_ms())
    if not txt:
        raise RuntimeError("路由器没有返回双 WAN 配置（可能这台固件不支持双 WAN）")
    basic = (_f("_insts", txt, "OBJ_DUALWAN_BASIC_ID") or [{}])[0]
    wanlan = _f("_insts", txt, "OBJ_WANLAN_ID") or []
    lb = (_f("_insts", txt, "OBJ_DUALWAN_LOADBALANCE_ID") or [{}])[0]
    mal = (_f("_insts", txt, "OBJ_DUALWAN_MAL_TRSF_ID") or [{}])[0]
    return {"basic": basic, "wanlan": wanlan, "lb": lb, "mal": mal, "raw": txt}


def _wan2_state():
    """读 WAN2 连接状态（vue_dualwan_data）"""
    txt = _f("_raw_get", DW_URL % _now_ms())
    head = (txt or "").lstrip()[:300].lower()
    if not txt or "<html" in head or "<!doctype" in head:
        return {}   # 只有整页登录 HTML 才算没读到；XML 片段（<Inst …）是正常响应
    inst = (_f("_insts", txt, "ID_WAN_COMFIG") or [{}])[0]
    return inst


WANLIST_URL = "/?_type=vuejsonData&_tag=vue_eth_portname&GET_TYPE=WANLIST&_=%d"


def _local_dw():
    """本机口径的 WAN2 配置：vue_dualwan_data → ID_WAN_COMFIG（读不到返回空）"""
    try:
        return _wan2_state()
    except Exception:
        return {}


def _wanlist():
    """WAN 连接列表（免登录可读）：OBJ_WANC_INFO_ID[{IsMainWAN, IPIFID}]

    WAN2 启用时这里会多一条 IsMainWAN=0 的记录——用它判断双 WAN 开没开，
    比只读需要登录的 vue_dualwan_data 更稳。
    """
    try:
        st, txt = _f("req", WANLIST_URL % _now_ms(), timeout=8)
        if st != 200 or not txt or txt.lstrip()[:1] == "<":
            return []
        data = (json.loads(txt).get("data") or {})
        return data.get("OBJ_WANC_INFO_ID") or []
    except Exception:
        return []


def _type_of(cfg):
    """把当前 WAN2 配置翻译成固件保存时用的 (WANC_TYPE, mode, WANCName)"""
    wct = _str(cfg.get("WANCTYPE")).lower()
    tt = _str(cfg.get("TransType")).lower()
    at = _str(cfg.get("Addressingtype")).lower()
    if wct == "bridge":
        return "bridge", "bridge", "Bridge_2"
    if "pppoe" in tt:
        return "pppoe", "pppoe", "PPPoE_2"
    if "static" in at or "static" in tt:
        return "dhcp/static", "Static", "Static_2"
    return "dhcp/static", "DHCP", "DHCP_2"


def api_dualwan():
    """双 WAN 现状。

    两种固件口径：
    * 老款：OBJ_DUALWAN_BASIC_ID.SecWanLink + OBJ_WANLAN_ID.WANSelect（口可自由指定）
    * 本机（BE5100 Pro+ 这类）：物理只有一个 WAN 口，固件文案叫「WAN2（LAN1）」——
      WAN2 就是 WAN1 旁边那个网口，WAN2 一旦启用，该口的 WanType 会从 -1 变成 2。
      这两种口径的读法完全不同，所以先探老口径，探不到就走本机口径。
    """
    ports = _f("read_ports") or []
    by_idx = _port_index(ports)
    try:
        cfg = _dual_cfg()
    except Exception:
        cfg = {"basic": {}, "wanlan": [], "lb": {}, "mal": {}, "raw": ""}
    if not cfg.get("basic"):
        return _api_dualwan_local(ports, by_idx)
    return _api_dualwan_legacy(cfg, ports, by_idx)


def _api_dualwan_local(ports, by_idx):
    """本机口径：WAN1 = 机身 WAN 口（固定），WAN2 = WAN1 旁边的网口（可被设成第二 WAN）"""
    wl = _wanlist()
    dw = _local_dw()

    w1 = next((p for p in ports if p.get("wan")), None)
    # WAN2 的目标口：优先「固件已经把它标成 WAN2」的那个口；
    # 还没启用时就是 WAN1 旁边的 LAN1（与固件文案「WAN2（LAN1）」一致）
    w2 = next((p for p in ports if p.get("wanType") == 2), None)
    preset = False
    if w2 is None:
        w2 = next((p for p in ports if _str(p.get("name")).upper() == "LAN1"), None)
        preset = True

    idx_of = {id(p): i for i, p in by_idx.items()}
    w1_idx = idx_of.get(id(w1)) if w1 else None
    w2_idx = idx_of.get(id(w2)) if w2 else None

    sec_links = [x for x in wl if _str(x.get("IsMainWAN")) != "1"]
    enabled = bool(sec_links) or _str(dw.get("Enable")) == "1"
    status_map = {
        "Connected": "已连接", "Demand": "按需连接", "Unconfigured": "未配置",
        "Connecting": "正在连接", "Authenticating": "正在认证",
        "Disconnected": "已断开", "Registering": "注册中",
    }
    st = status_map.get(_str(dw.get("ConnStatus")), _str(dw.get("ConnStatus")))

    return {
        "ok": True,
        "supported": True,
        "flavor": "fixed",          # 前端据此画「固定口」形态，不给选口
        "canSwitch": False,          # 写入口径还没验证过，先只读，避免把宽带配置打坏
        "wan1": {
            "idx": w1_idx,
            "name": (w1 or {}).get("name", "WAN"),
            "link": bool((w1 or {}).get("link")),
            "speed": (w1 or {}).get("speed", ""),
            "max": (w1 or {}).get("max", ""),
            "locked": True,
        },
        "wan2": {
            "idx": w2_idx,
            "name": (w2 or {}).get("name", "LAN1"),
            "link": bool((w2 or {}).get("link")),
            "speed": (w2 or {}).get("speed", ""),
            "max": (w2 or {}).get("max", ""),
            "enabled": enabled,
            "preset": preset,        # True = 还没启用，只是「可以变成 WAN2」的那个口
            "locked": True,
            "status": ("已启用" if enabled else "未启用") + ("·" + st if st else ""),
            "type": _str(dw.get("WANCTYPE")) or _str(dw.get("TransType")),
            "ip": _str(dw.get("IPAddress")),
        },
        "loadBalance": {"enabled": False, "wan1": "1", "wan2": "1"},
        "failover": False,
        "ports": [{
            "idx": i,
            "name": p.get("name", ""),
            "wan": bool(p.get("wan")),
            "wanType": p.get("wanType"),
            "link": bool(p.get("link")),
            "linkKnown": p.get("linkKnown", True) is not False,
            "speed": p.get("speed", ""),
            "isMain": p is w1,
            "isSec": p is w2,
        } for i, p in by_idx.items()],
        "note": "这台机器的物理 WAN 只有一个（WAN1），WAN2 是把 WAN1 旁边那个网口切过去当第二个 WAN 用。",
    }


def _api_dualwan_legacy(cfg, ports, by_idx):
    """老款固件：口可以在两个槽位里自由指定"""
    basic = cfg["basic"]
    wanlan = cfg["wanlan"]
    dw = _wan2_state()

    try:
        sec = int(float(_str(basic.get("SecWanLink")) or 1))
    except Exception:
        sec = 1
    try:
        main = int(float(_str((wanlan[0] or {}).get("WANSelect")) or 0))
    except Exception:
        main = 0

    wan2_on = _str(dw.get("Enable")) == "1"
    ports_out = []
    for i, p in by_idx.items():
        ports_out.append({
            "idx": i,
            "name": p.get("name", ""),
            "wan": bool(p.get("wan")),
            "link": bool(p.get("link")),
            "linkKnown": p.get("linkKnown", True) is not False,
            "speed": p.get("speed", ""),
            "isMain": i == main,
            "isSec": i == sec,
        })

    status_map = {
        "Connected": "已连接", "Demand": "按需连接", "Unconfigured": "未配置",
        "Connecting": "正在连接", "Authenticating": "正在认证",
        "Disconnected": "已断开", "Registering": "注册中",
    }
    w2_status = status_map.get(_str(dw.get("ConnStatus")), _str(dw.get("ConnStatus")))
    w1 = next((x for x in ports_out if x["isMain"]), None) or \
         next((x for x in ports_out if x["wan"]), None)
    w2 = by_idx.get(sec)

    return {
        "ok": True,
        "supported": True,
        "flavor": "legacy",
        "wan1": {
            "idx": main,
            "name": (w1 or {}).get("name", ""),
            "link": bool((w1 or {}).get("link")),
            "speed": (w1 or {}).get("speed", ""),
            "locked": False,
        },
        "wan2": {
            "idx": sec,
            "name": (w2 or {}).get("name", ""),
            "link": bool((w2 or {}).get("link")),
            "speed": (w2 or {}).get("speed", ""),
            "enabled": wan2_on,
            "locked": False,
            "status": "未启用" if not wan2_on else (w2_status or "已启用"),
            "type": _str(dw.get("WANCTYPE")) or _str(dw.get("TransType")),
            "ip": _str(dw.get("IPAddress")),
        },
        "loadBalance": {
            "enabled": _str(cfg["lb"].get("lbEnable")) == "1",
            "wan1": _str(cfg["lb"].get("FirWanLoadRatio")) or "1",
            "wan2": _str(cfg["lb"].get("SecWanLoadRatio")) or "1",
        },
        "failover": _str(cfg["mal"].get("MalSwitch")) == "1",
        "ports": ports_out,
        "canSwitch": True,
        "note": "",
    }


def _set_error(txt):
    m = re.search(r"<IF_ERRORSTR>(.*?)</IF_ERRORSTR>", txt or "", re.S)
    v = (m.group(1) if m else "").strip()
    return "" if v in ("SUCC", "OK", "") else v


def _resolve_port(raw, by_idx, what="网口"):
    """按名字（LAN1 / WAN）或序号定位端口索引"""
    raw = _str(raw)
    if not raw:
        return None
    for i, p in by_idx.items():
        if raw.upper() in (_str(p.get("name")).upper(), _str(p.get("fw")).upper()):
            return i
    try:
        i = int(float(raw))
    except Exception:
        raise ValueError("没有这个%s" % what)
    if i not in by_idx:
        raise ValueError("没有这个%s" % what)
    return i


def api_dualwan_set(body=None):
    """两个物理 WAN 口设置：可同时指定 WAN1（WANSelect）与 WAN2（SecWanLink）。

    body: {"main": 端口序号/名字, "sec": 端口序号/名字}
    兼容旧口径 {"port": ...} / {"idx": ...}（只切 WAN2）。
    其余字段整表原样回填，只改这两个口。
    """
    body = body or {}
    # 注意：端口序号 0（WAN 口）是假值，不能走 or 链
    raw_sec = body.get("sec")
    if raw_sec is None:
        raw_sec = body.get("port")
    if raw_sec is None:
        raw_sec = body.get("idx")
    raw_sec = _str(raw_sec)
    raw_main = _str(body.get("main"))
    if not raw_sec and not raw_main:
        raise ValueError("请选择要设置的 WAN 口端口")
    ports = _f("read_ports") or []
    by_idx = _port_index(ports)

    cfg = _dual_cfg()
    basic, wanlan, lb, mal = cfg["basic"], cfg["wanlan"], cfg["lb"], cfg["mal"]
    if not basic:
        # 本机口径：WAN2 = WAN1 旁边那个口，没有「换到别的口」这回事
        raise ValueError("这台机器的物理 WAN 只有一个（WAN1），WAN2 是把 WAN1 旁边那个网口切过去用，"
                         "不能在别的口之间挑。请到路由器原版管理页的「双 WAN」里开启/关闭。")
    dw = _wan2_state()
    if not dw:
        raise ValueError("读不到 WAN2 配置，先刷新一下再试")

    try:
        cur_main = int(float(_str((wanlan[0] or {}).get("WANSelect")) or 0))
    except Exception:
        cur_main = 0
    try:
        old_sec = int(float(_str(basic.get("SecWanLink")) or 1))
    except Exception:
        old_sec = 1

    target = _resolve_port(raw_sec, by_idx, "WAN2 网口") if raw_sec else None
    new_main = _resolve_port(raw_main, by_idx, "WAN1 网口") if raw_main else None

    if target is not None:
        if by_idx[target].get("wan"):
            raise ValueError("WAN 口（光纤口）只能当 WAN1，不能同时当 WAN2")
        if target == new_main:
            raise ValueError("WAN1 和 WAN2 不能用同一个口")
        # 只要这次把 WAN1 挪走，WAN2 就可以接管它原来的口（互换是允许的）
        if target == cur_main and (new_main is None or new_main == cur_main):
            raise ValueError("这个口正在当 WAN1，先把 WAN1 换到别的口")
    if new_main is not None:
        if new_main == target:
            raise ValueError("WAN1 和 WAN2 不能用同一个口")
        # 同理：WAN1 想用 WAN2 现在的口，必须这次同时把 WAN2 挪走
        if new_main == old_sec and target is None and _str(dw.get("Enable")) == "1":
            raise ValueError("这个口正在当 WAN2，先把 WAN2 换到别的口")

    # 全都没变就直接返回
    sec_same = target is None or (target == old_sec)
    main_same = new_main is None or (new_main == cur_main)
    if sec_same and main_same and _str(dw.get("Enable")) == "1":
        name = by_idx.get(old_sec, {}).get("name", "")
        return {"ok": True, "changed": False, "sec": old_sec, "main": cur_main,
                "name": name, "msg": "端口设置没有变化"}

    enabled = _str(dw.get("Enable")) == "1"
    wct, mode, wname = _type_of(dw)
    final_main = new_main if new_main is not None else cur_main
    final_sec = target if target is not None else old_sec

    payload = {
        "IF_ACTION": "Apply",
        "Enable": "1" if enabled else "0",
        "_InstID": _str(dw.get("_InstID")),
        "WANC_TYPE": wct,
        "WANCName": wname,
        "mode": mode,
        "TypeFlag": "0",
        "WANSelect": final_main,
        "SecWanLink": final_sec,
        "Mode": _str(basic.get("Mode")) or "0",
        "LANViewName": _str(basic.get("LANViewName")),
        "DevIp": _str(basic.get("DevIp")),
        "BindEnable": _str(basic.get("BindEnable")) or "0",
        "lbEnable": _str(lb.get("lbEnable")) or "0",
        "FirWanLoadRatio": _str(lb.get("FirWanLoadRatio")) or "1",
        "SecWanLoadRatio": _str(lb.get("SecWanLoadRatio")) or "1",
        "MalSwitch": _str(mal.get("MalSwitch")) or "0",
        "IsDns": _str(mal.get("IsDns")) or "1",
        "TriggerTime": _str(mal.get("TriggerTime")) or "3",
        "ReCoverTime": _str(mal.get("ReCoverTime")) or "3",
        "IntervalTime": _str(mal.get("IntervalTime")) or "10",
        "Dest": _str(mal.get("Dest")) or "www.zte.com.cn",
    }

    # WAN2 已经配好（尤其 PPPoE）时，保存会把账号密码一起带上；
    # 读不到密码就绝不硬提交，否则会把用户的宽带账号打坏。
    if enabled:
        user = _str(dw.get("UserName"))
        pwd = ""
        try:
            txt = _f("_raw_get", "/?_type=vueData&_tag=vue_dualwan_data&IF_OP=GetPassword"
                                    "&_InstID_PASS=%s&PASSTYPE=PPP&_=%d"
                                    % (_str(dw.get("_InstID")), _now_ms()))
            pwd = _str((_f("_insts", txt, "OBJ_ETHWANCPPP_ID") or [{}])[0].get("Password"))
        except Exception:
            pwd = ""
        if wct == "pppoe":
            if not user or not pwd:
                raise ValueError("WAN2 现在是 PPPoE 拨号，路由器没有把宽带密码交出来。"
                                 "为了不把账号打坏，这里不硬改端口：请先在原版管理页把「双 WAN」关掉，"
                                 "或直接在原版页面里换口。")
            r, l = _f("rand16"), _f("rand16")
            payload.update({
                "UserName": user,
                "Password": _f("enc_para", pwd, r, l),
                "PPPoEServiceName": _str(dw.get("PPPoEServiceName")),
                "encode": _f("enc_key", r, l),
            })
        elif mode == "Static":
            payload.update({
                "IPAddress": _str(dw.get("IPAddress")),
                "SubnetMask": _str(dw.get("SubnetMask")),
                "GateWay": _str(dw.get("GateWay")),
                "Addressingtype": "Static",
                "DNS1": _str(dw.get("DNS1")) or "0.0.0.0",
                "DNS2": _str(dw.get("DNS2")) or "0.0.0.0",
            })
        elif mode == "DHCP":
            payload["DNSOverrideAllowedv4"] = "0" if _str(dw.get("DNSOverrideAllowedv4")) == "0" else "1"

    st, txt = _f("req", DW_URL % _now_ms(), payload, timeout=20)
    err = _set_error(txt)
    if st != 200 or err:
        raise RuntimeError("路由器拒绝了这次修改（%s）" % (err or ("HTTP %s" % st)))

    # 复查：要改的字段真的变了才算成功
    try:
        after = _dual_cfg()
        now_sec = int(float(_str(after["basic"].get("SecWanLink")) or -1))
        now_main = int(float(_str((after["wanlan"][0] or {}).get("WANSelect")) or -1))
    except Exception:
        now_sec = now_main = -1
    sec_name = by_idx.get(final_sec, {}).get("name", "")
    main_name = by_idx.get(final_main, {}).get("name", "")
    if target is not None and now_sec != target:
        raise RuntimeError("路由器没有接受 WAN2 换口（仍在 %s 口）。"
                           "这台固件可能要求在原版管理页里改，或者有 IPTV/端口绑定占着这个口。"
                           % (by_idx.get(now_sec, {}).get("name", now_sec)))
    if new_main is not None and now_main != new_main:
        raise RuntimeError("路由器没有接受 WAN1 换口（仍在 %s 口）。"
                           "这台固件可能要求在原版管理页里改。"
                           % (by_idx.get(now_main, {}).get("name", now_main)))
    parts = []
    if new_main is not None:
        parts.append("WAN1 已设为 %s 口" % main_name)
    if target is not None:
        parts.append("WAN2 已设为 %s 口" % sec_name)
    return {"ok": True, "changed": True, "sec": final_sec, "main": final_main,
            "name": sec_name, "enabled": enabled,
            "msg": "、".join(parts) if parts else "已应用"}


# ---------------- 管理员密码 ----------------

def api_admin_pwd(body=None):
    """修改管理员（后台登录）密码"""
    body = body or {}
    old = body.get("old") or ""
    new = body.get("new") or ""
    if not old:
        raise ValueError("请输入当前密码")
    if len(new) < 6:
        raise ValueError("新密码至少 6 位")
    if len(new) > 63:
        raise ValueError("新密码最长 63 位")
    if new == old:
        raise ValueError("新密码和当前密码一样")

    txt = _f("_raw_get", "/?_type=vueData&_tag=user_info_data&_=%d" % _now_ms())
    info = (_f("_insts", txt, "OBJ_USERINFO_ID") or [{}])[0]
    user = _str(info.get("Username")) or "admin"

    r, l = _f("rand16"), _f("rand16")
    payload = {
        "IF_ACTION": "Apply",
        "_InstID": "IGD.AU1",
        "Username": user,
        "Right": "1",
        "Password": _f("enc_para", old, r, l),
        "NewPassword": _f("enc_para", new, r, l),
        "encode": _f("enc_key", r, l),
    }
    st, res = _f("req", "/?_type=vueData&_tag=user_info_data&_=%d" % _now_ms(),
                 payload, timeout=20)
    err = _set_error(res)
    if st != 200 or err:
        low = err.lower()
        if "pwd" in low or "pass" in low or "auth" in low:
            raise ValueError("当前密码不对，路由器拒绝了这次修改")
        raise RuntimeError("修改失败（%s）" % (err or ("HTTP %s" % st)))

    # 改完密码，面板内存里的密码要跟着换，否则掉线后自动重登会用旧密码
    try:
        S = P.get("S")
        if isinstance(S, dict):
            S["pwd"] = new
    except Exception:
        pass
    return {"ok": True, "user": user, "msg": "管理员密码已修改"}
