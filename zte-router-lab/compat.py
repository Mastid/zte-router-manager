# -*- coding: utf-8 -*-
"""
中兴路由器兼容层
================

目标：一套代码适配中兴家用/商用路由器的多个固件族，而不是只认
ZXSLC SR7110 / 巡天 BE5100 这一台。

三个概念
--------
1. **固件族（family）**：决定「怎么说话」——URL 形态、令牌、登录方式。
2. **资源（resource）**：我们想拿到的业务数据（设备信息/无线/终端/端口/双 WAN…），
   每族下有一组候选接口，按顺序探测，谁通就用谁（结果缓存）。
3. **机型画像（profile）**：认出来的具体型号带来的差异（单 WAN 口、三频、
   登录即顶号…），用于前端决定显示什么、禁用什么。

设计原则
--------
- **探测优先，注册表只做提示**：不靠型号字符串硬猜能力，能探测就以探测结果为准。
- **失败可回退**：候选接口逐个试，全不通就标记该能力不可用，界面降级而不是报错。
- **一切可诊断**：探测过程写日志，前端能一键导出报告，未知机型发来报告即可补适配。
"""
import json
import os
import re
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "logs", "compat.json")
PROBE_LOG = os.path.join(BASE_DIR, "logs", "compat.log")

# ---------------------------------------------------------------- 固件族

FAMILY_VUE = "vue"        # 新固件：?_type=vueData&_tag=…（巡天/问天/AX/BE 系列）
FAMILY_GOFORM = "goform"  # 老固件：/goform/goform_get_cmd_process（MF/AC/E/部分 ZXHN）
FAMILY_LUCI = "luci"      # OpenWrt 定制：/cgi-bin/luci/
FAMILY_UNKNOWN = "unknown"

FAMILY_INFO = {
    FAMILY_VUE: {
        "label": "新固件（vue 接口）",
        "desc": "巡天 / 问天 / AX / BE 系列，?_type=vueData&_tag=… 接口体系",
        "login": "logintoken + sha256(密码+token)",
    },
    FAMILY_GOFORM: {
        "label": "经典固件（goform 接口）",
        "desc": "MF / AC / E 系列及部分 ZXHN 光猫，goform_get_cmd_process 接口",
        "login": "goform_set_cmd_process + base64 密码（实验性）",
    },
    FAMILY_LUCI: {
        "label": "OpenWrt 定制（luci 接口）",
        "desc": "部分企业/定制机型，/cgi-bin/luci/ 接口",
        "login": "luci 会话（暂未适配，仅识别）",
    },
    FAMILY_UNKNOWN: {
        "label": "未识别",
        "desc": "接口特征与已知三家都不符，需要抓包补适配",
        "login": "未知",
    },
}

# ---------------------------------------------------------------- 资源候选

# 每个资源一组候选，按「最可能」到「兜底」排序；probe 是命中判据（响应里应出现的标记）
VUE = "vueData"
VUEJ = "vuejsonData"
HID = "hiddenData"
SCN = "hiddenScene"

RESOURCES = {
    # 设备基础信息（型号、运行时长、WAN 状态）
    "device": {
        "label": "设备信息",
        "cands": [
            {"family": FAMILY_VUE, "type": VUE, "tag": "vue_home_device_data", "probe": "OBJ_"},
            {"family": FAMILY_VUE, "type": VUE, "tag": "vue_home_device_data_no_update_sess", "probe": "OBJ_"},
            {"family": FAMILY_VUE, "type": VUE, "tag": "vue_dev_info_data", "probe": "OBJ_"},
            {"family": FAMILY_VUE, "type": VUE, "tag": "homestate_data", "probe": "OBJ_"},
        ],
    },
    # 软件版本 / 硬件型号
    "version": {
        "label": "版本与型号",
        "cands": [
            {"family": FAMILY_VUE, "type": SCN, "tag": "initial_info_json", "probe": "WEBTitle"},
            {"family": FAMILY_VUE, "type": VUE, "tag": "vue_nowversion_lua", "probe": "OBJ_"},
            {"family": FAMILY_VUE, "type": VUE, "tag": "vue_version_fallback_data", "probe": "OBJ_"},
            {"family": FAMILY_GOFORM, "cmd": "cr_version,wa_inner_version,web_version,Language"},
        ],
    },
    # 无线 SSID / 状态
    "wifi": {
        "label": "无线状态",
        "cands": [
            {"family": FAMILY_VUE, "type": VUE, "tag": "wifiAP_data", "probe": "OBJ_WLANAP_ID"},
            {"family": FAMILY_VUE, "type": VUE, "tag": "ssid_data", "probe": "OBJ_"},
            {"family": FAMILY_VUE, "type": VUE, "tag": "netwlanap_data", "probe": "OBJ_"},
            {"family": FAMILY_VUE, "type": VUE, "tag": "vue_wifissid_data", "probe": "OBJ_"},
        ],
    },
    # 外网 / WAN 连接
    "wan": {
        "label": "外网连接",
        "cands": [
            {"family": FAMILY_VUE, "type": VUE, "tag": "vue_internet_data", "probe": "OBJ_"},
            {"family": FAMILY_VUE, "type": VUE, "tag": "vuecfg_data", "probe": "OBJ_"},
            {"family": FAMILY_VUE, "type": VUE, "tag": "vue_internet_wan_select_data", "probe": "OBJ_"},
        ],
    },
    # 在线终端
    "clients": {
        "label": "在线终端",
        "cands": [
            {"family": FAMILY_VUE, "type": VUE, "tag": "vue_client_data", "probe": "OBJ_"},
            {"family": FAMILY_VUE, "type": VUE, "tag": "localnet_lan_detailinfo_lua", "probe": "OBJ_"},
            {"family": FAMILY_VUE, "type": VUE, "tag": "vue_landevice_data", "probe": "OBJ_"},
            {"family": FAMILY_VUE, "type": VUE, "tag": "accessdev_data", "probe": "OBJ_"},
            {"family": FAMILY_VUE, "type": VUE, "tag": "vue_hosts_data", "probe": "OBJ_"},
        ],
    },
    # 物理网口
    "ports": {
        "label": "物理网口",
        "cands": [
            {"family": FAMILY_VUE, "type": VUEJ, "tag": "vue_eth_portname",
             "extra": "GET_TYPE=WANSTATUS", "probe": "OBJ_ETHPORT"},
            {"family": FAMILY_VUE, "type": VUEJ, "tag": "vue_eth_portname",
             "extra": "GET_TYPE=WANLIST", "probe": "OBJ_"},
            {"family": FAMILY_VUE, "type": VUE, "tag": "vue_eth_port_data", "probe": "OBJ_"},
            {"family": FAMILY_VUE, "type": VUE, "tag": "vue_landevice_data", "probe": "OBJ_"},
        ],
    },
    # 双 WAN（老款有完整表，新款只有开关）
    "dualwan": {
        "label": "双 WAN",
        "cands": [
            {"family": FAMILY_VUE, "type": HID, "tag": "vue_internet_eth_data", "probe": "OBJ_DUALWAN_BASIC_ID"},
            {"family": FAMILY_VUE, "type": VUE, "tag": "vue_dualwan_data", "probe": "ID_WAN_COMFIG"},
            {"family": FAMILY_VUE, "type": HID, "tag": "vue_dualwan_data", "probe": "ID_WAN_COMFIG"},
        ],
    },
    # 系统负载（CPU / 内存）
    "sysstat": {
        "label": "系统负载",
        "cands": [
            {"family": FAMILY_VUE, "type": VUE, "tag": "vue_sys_info_data", "probe": "OBJ_"},
            {"family": FAMILY_VUE, "type": VUE, "tag": "vue_managdiag", "probe": "OBJ_"},
            {"family": FAMILY_VUE, "type": VUE, "tag": "vueinfo_data", "probe": "OBJ_"},
        ],
    },
    # 中兴原厂 Mesh：组网状态（OBJ_LISTAPTOPO_ID / OBJ_WLAN_STA_STATUS_PROFILE_ID）
    "mesh": {
        "label": "Mesh 状态",
        "cands": [
            {"family": FAMILY_VUE, "type": VUEJ, "tag": "vue_meshstatus_json",
             "extra": "_reqstatus=1", "probe": "OBJ_"},
            {"family": FAMILY_VUE, "type": VUEJ, "tag": "vue_meshstatus_json_no_update_sess",
             "extra": "_reqstatus=1", "probe": "OBJ_"},
            {"family": FAMILY_VUE, "type": VUE, "tag": "vue_meshstatus_data", "probe": "OBJ_"},
        ],
    },
    # 中兴原厂 Mesh：拓扑列表（GetALLAP，apData.MGET_INST_NUM + AP 实例）
    "topo": {
        "label": "Mesh 拓扑",
        "cands": [
            {"family": FAMILY_VUE, "type": VUE, "tag": "vue_topo_data",
             "extra": "Action=GetALLAP", "probe": "MGET_INST_NUM"},
            {"family": FAMILY_VUE, "type": VUE, "tag": "vue_topo_data", "probe": "OBJ_"},
        ],
    },
}

# ---------------------------------------------------------------- 机型画像
# 说明：这里只提供「提示」，真正的能力以探测结果为准。
# 匹配方式：型号字符串包含 key 即命中（不区分大小写），先长后短。

MODELS = [
    # ---- 巡天 / 问天系列（新固件） ----
    {"key": "BE7200", "name": "巡天 BE7200 Pro+", "family": FAMILY_VUE,
     "bands": 3, "quirks": ["preempt_on_login"], "note": "三频 Wi-Fi 7"},
    {"key": "BE6500", "name": "巡天 BE6500 Pro", "family": FAMILY_VUE,
     "bands": 3, "quirks": [], "note": "三频 Wi-Fi 7"},
    {"key": "BE5100", "name": "巡天 BE5100 Pro+", "family": FAMILY_VUE,
     "bands": 2, "quirks": ["wan2_fixed", "preempt_on_login"], "note": "单 WAN 口，WAN2 借用 LAN1"},
    {"key": "AX5400", "name": "巡天 AX5400 Pro", "family": FAMILY_VUE,
     "bands": 2, "quirks": ["preempt_on_login"], "note": ""},
    {"key": "AX3000", "name": "巡天 AX3000", "family": FAMILY_VUE,
     "bands": 2, "quirks": ["wan2_fixed", "preempt_on_login"], "note": "单 WAN 口机型"},
    {"key": "AX1500", "name": "巡天 AX1500", "family": FAMILY_VUE,
     "bands": 2, "quirks": ["wan2_fixed"], "note": ""},
    {"key": "SR7110", "name": "ZXSLC SR7110", "family": FAMILY_VUE,
     "bands": 2, "quirks": ["wan2_fixed"], "note": "BE5100 Pro+ 的硬件型号"},
    # ---- 经典固件（goform） ----
    {"key": "MC801", "name": "5G CPE MC801A", "family": FAMILY_GOFORM, "bands": 2,
     "quirks": ["goform_only"], "note": "5G CPE，接口为 goform"},
    {"key": "MC888", "name": "5G CPE MC888", "family": FAMILY_GOFORM, "bands": 2,
     "quirks": ["goform_only"], "note": ""},
    {"key": "MF", "name": "便携路由（MF 系列）", "family": FAMILY_GOFORM, "bands": 1,
     "quirks": ["goform_only"], "note": "随身 Wi-Fi"},
    {"key": "AC30", "name": "AC1200（AC 系列）", "family": FAMILY_GOFORM, "bands": 2,
     "quirks": ["goform_only"], "note": ""},
    {"key": "E2633", "name": "E2633", "family": FAMILY_VUE, "bands": 2, "quirks": [], "note": ""},
    {"key": "E2603", "name": "E2603", "family": FAMILY_VUE, "bands": 2, "quirks": [], "note": ""},
    {"key": "ZXHN", "name": "ZXHN 光猫", "family": FAMILY_GOFORM, "bands": 2,
     "quirks": ["goform_only", "isp_locked"], "note": "运营商定制光猫，多数接口被裁剪"},
]

# ---------------------------------------------------------------- 状态

S = {
    "family": None,
    "resolved": {},     # resource -> cand
    "caps": {},         # resource -> bool
    "model": {},        # dev / web / sw
    "profile": None,
    "at": 0,
    "probed": False,    # 是否跑过完整探测
    "notes": [],
}
_LOADED = False


def _log(msg):
    try:
        os.makedirs(os.path.dirname(PROBE_LOG), exist_ok=True)
        with open(PROBE_LOG, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def load():
    """读取上次的探测结果（跨进程启动复用，避免每次开机都重新探测）"""
    global _LOADED
    if _LOADED:
        return S
    _LOADED = True
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            d = json.load(f)
        S.update({k: d.get(k) for k in ("family", "resolved", "caps", "model", "profile", "at", "probed")
                  if k in d})
    except Exception:
        pass
    return S


def save():
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({k: S[k] for k in ("family", "resolved", "caps", "model", "profile", "at", "probed")},
                      f, ensure_ascii=False, indent=1)
    except Exception as e:
        _log("保存失败 %s" % e)


# ---------------------------------------------------------------- 路径构造

def cand_path(c):
    """候选接口 → 请求路径（GET）"""
    fam = c.get("family")
    if fam == FAMILY_VUE:
        p = "/?_type=%s&_tag=%s" % (c.get("type") or VUE, c.get("tag") or "")
        if c.get("extra"):
            p += "&" + c["extra"]
        return p
    if fam == FAMILY_GOFORM:
        return "/goform/goform_get_cmd_process?isTest=false&cmd=%s&multi_data=1" % (c.get("cmd") or "")
    if fam == FAMILY_LUCI:
        return c.get("path") or "/cgi-bin/luci/"
    return c.get("path") or "/"


def path(res, fallback_tag=None):
    """资源 → 当前已解析的路径；未解析时用第一个候选"""
    c = (S.get("resolved") or {}).get(res)
    if not c and fallback_tag:
        c = {"family": FAMILY_VUE, "type": VUE, "tag": fallback_tag}
    if not c:
        cands = (RESOURCES.get(res) or {}).get("cands") or []
        c = cands[0] if cands else {"family": FAMILY_VUE, "type": VUE, "tag": ""}
    return cand_path(c)


def cand(res):
    return (S.get("resolved") or {}).get(res)


# ---------------------------------------------------------------- 识别

_GOFORM_JUNK = re.compile(r"<\s*(html|!doctype|head)", re.I)


def _looks_json(txt):
    t = (txt or "").strip()
    return t.startswith("{") or t.startswith("[")


def _looks_xml(txt):
    t = (txt or "").lstrip()
    return t.startswith("<") and not _GOFORM_JUNK.match(t)


def sniff_login_page(html_text):
    """免登录：从登录页 HTML 猜固件族（不用登录，也不产生会话）

    判据全部来自登录页静态特征，宁可判不出也不乱判：
      * 新固件：/jquery/static/js/app.*.js、g_sessionTmpToken、_type=loginscene
      * 经典固件：goform / getpage.gch / wa_inner_version
      * OpenWrt 定制：luci / cgi-bin/luci
    """
    t = html_text or ""
    low = t.lower()
    if not low.strip():
        return None
    vue_hits = 0
    for k in ("/jquery/static/js/app.", "g_sessiontmptoken", "g_sessiontoken",
              "_type=loginscene", "logintoken", "login_entry", "vue"):
        if k in low:
            vue_hits += 1
    if vue_hits >= 1:
        return FAMILY_VUE
    if "goform" in low or "getpage.gch" in low or "wa_inner_version" in low:
        return FAMILY_GOFORM
    if "luci" in low:
        return FAMILY_LUCI
    return None


def detect(get, logged=False):
    """跑一轮探测。

    get(path) -> (status, text)：由调用方注入（panel.py 的 req），避免循环依赖。
    logged=False 时只做免登录探测（登录页 + 少量公开接口），不覆盖已有缓存结论。
    """
    load()
    notes = []
    t0 = time.time()

    # 1) 登录页特征
    try:
        st, home = get("/")
        if st == 200:
            fam = sniff_login_page(home)
            if fam and (not S.get("family") or S.get("family") == FAMILY_UNKNOWN):
                S["family"] = fam
                notes.append("登录页特征判定：%s" % FAMILY_INFO[fam]["label"])
    except Exception as e:
        notes.append("读登录页失败：%s" % e)

    if not logged:
        S["notes"] = notes
        return S

    # 2) 已登录：逐资源探候选，谁先返回有效内容就用谁
    resolved, caps = {}, {}
    for res, meta in RESOURCES.items():
        got = None
        for c in meta["cands"]:
            p = cand_path(c)
            try:
                st, txt = get(p)
            except Exception as e:
                _log("%s %s 异常 %s" % (res, p, e))
                continue
            if st == 404 or st != 200 or not txt:
                _log("%s %s -> HTTP %s" % (res, p, st))
                continue
            probe = c.get("probe")
            if probe and probe not in txt:
                _log("%s %s -> 200 但无标记 %s" % (res, p, probe))
                continue
            if not _looks_json(txt) and not _looks_xml(txt):
                continue
            got = c
            _log("%s 命中 %s %s" % (res, p, c.get("tag") or c.get("cmd")))
            break
        if got:
            resolved[res] = got
            caps[res] = True
        else:
            caps[res] = False
            _log("%s 全部候选不可用" % res)

    # 3) 固件族：以「设备信息」命中的族为准，其次看哪个族有任何资源命中
    fams = [c.get("family") for c in resolved.values()]
    if FAMILY_VUE in fams:
        S["family"] = FAMILY_VUE
    elif FAMILY_GOFORM in fams:
        S["family"] = FAMILY_GOFORM
    elif not S.get("family"):
        S["family"] = FAMILY_UNKNOWN

    S["resolved"] = resolved
    S["caps"] = caps
    S["at"] = int(time.time())
    S["probed"] = True
    S["notes"] = notes
    _log("探测完成 family=%s 命中 %d/%d 耗时 %.1fs"
         % (S["family"], sum(1 for v in caps.values() if v), len(caps), time.time() - t0))
    save()
    return S


# ---------------------------------------------------------------- 机型画像

def match_model(*texts):
    """按型号字符串匹配注册表（先长后短，避免 AX3000 Pro 被 AX3000 抢）"""
    blob = " ".join([t for t in texts if t]).upper()
    if not blob.strip():
        return None
    for m in sorted(MODELS, key=lambda x: -len(x["key"])):
        if m["key"].upper() in blob:
            return dict(m)
    return None


def set_model(dev="", web="", sw=""):
    """记录机型信息并刷新画像（登录后调用）"""
    load()
    if dev:
        S["model"]["dev"] = dev
    if web:
        S["model"]["web"] = web
    if sw:
        S["model"]["sw"] = sw
    prof = match_model(dev, web)
    if prof:
        S["profile"] = {k: prof.get(k) for k in ("key", "name", "family", "bands", "quirks", "note")}
        # 注册表只做提示：若实际探测到的族与注册表不一致，以实测为准
        if prof.get("family") and S.get("family") in (None, FAMILY_UNKNOWN):
            S["family"] = prof["family"]
    save()
    return S["profile"]


def quirks():
    return set((S.get("profile") or {}).get("quirks") or [])


def has_quirk(q):
    return q in quirks()


# ---------------------------------------------------------------- 报告

def label():
    """人类可读的一句话机型描述"""
    m = S.get("model") or {}
    dev = (m.get("dev") or "").strip()
    web = (m.get("web") or "").strip()
    if dev and web and web.upper() not in dev.upper():
        return "%s · %s" % (dev, web)
    return dev or web or ""


def report(include_caps=True):
    """给前端/诊断用的兼容性报告"""
    load()
    fam = S.get("family") or FAMILY_UNKNOWN
    fi = FAMILY_INFO.get(fam, FAMILY_INFO[FAMILY_UNKNOWN])
    prof = S.get("profile") or {}
    caps = []
    if include_caps:
        for res, meta in RESOURCES.items():
            ok = bool((S.get("caps") or {}).get(res))
            c = (S.get("resolved") or {}).get(res) or {}
            via = ""
            if c:
                via = c.get("tag") or c.get("cmd") or c.get("path") or ""
            caps.append({"res": res, "label": meta["label"], "ok": ok, "via": via,
                         "hint": "" if ok else "该机型没有对应接口，相关功能会自动隐藏"})
    return {
        "ok": True,
        "family": fam,
        "familyLabel": fi["label"],
        "familyDesc": fi["desc"],
        "familyLogin": fi["login"],
        "model": S.get("model") or {},
        "label": label(),
        "profile": prof,
        "quirks": sorted(quirks()),
        "probed": bool(S.get("probed")),
        "at": S.get("at") or 0,
        "caps": caps,
        "notes": S.get("notes") or [],
    }


def reset():
    """清掉缓存，下次探测重来"""
    global _LOADED
    S.update({"family": None, "resolved": {}, "caps": {}, "at": 0, "probed": False, "notes": []})
    _LOADED = True
    try:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
    except Exception:
        pass
