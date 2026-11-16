# -*- coding: utf-8 -*-
"""v2.7 双 WAN 两口设置（api_dualwan_set）逻辑桩测试：
不连真路由器，用假 P 环境把各场景过一遍。
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", "zte-router-lab"))
sys.path.insert(0, LAB)
import lanwan  # noqa: E402

PASS = []
FAIL = []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name + (" | " + str(extra) if extra and not cond else ""))


# ---------- 固定骨架响应 ----------
ETH = """<Inst ID="OBJ_DUALWAN_BASIC_ID" _InstID="IGD.DW1">
<SecWanLink>1</SecWanLink><Mode>0</Mode><LANViewName>LAN1</LANViewName><DevIp>192.168.5.1</DevIp><BindEnable>0</BindEnable>
</Inst>
<Inst ID="OBJ_WANLAN_ID" _InstID="IGD.WL1"><LAN_name>LAN1</LAN_name><WANSelect>0</WANSelect></Inst>
<Inst ID="OBJ_DUALWAN_LOADBALANCE_ID" _InstID="IGD.LB1"><lbEnable>0</lbEnable><FirWanLoadRatio>1</FirWanLoadRatio><SecWanLoadRatio>1</SecWanLoadRatio></Inst>
<Inst ID="OBJ_DUALWAN_MAL_TRSF_ID" _InstID="IGD.ML1"><MalSwitch>0</MalSwitch><IsDns>1</IsDns><TriggerTime>3</TriggerTime><ReCoverTime>3</ReCoverTime><IntervalTime>10</IntervalTime><Dest>www.zte.com.cn</Dest></Inst>"""

DW_ON_DHCP = """<Inst ID="ID_WAN_COMFIG" _InstID="IGD.W2"><Enable>1</Enable><ConnStatus>Connected</ConnStatus>
<WANCTYPE>dhcp</WANCTYPE><TransType>DHCP</TransType><Addressingtype>DHCP</Addressingtype><IPAddress>10.2.3.4</IPAddress></Inst>"""

DW_OFF = DW_ON_DHCP.replace("<Enable>1</Enable>", "<Enable>0</Enable>")

PORTS = [
    {"name": "WAN", "fw": "WAN", "wan": True, "link": True, "speed": "1000", "up": 0, "down": 0, "upText": "0", "downText": "0"},
    {"name": "LAN1", "fw": "LAN1", "wan": False, "link": True, "speed": "1000", "up": 0, "down": 0, "upText": "0", "downText": "0"},
    {"name": "LAN2", "fw": "LAN2", "wan": False, "link": False, "speed": "", "up": 0, "down": 0, "upText": "0", "downText": "0"},
    {"name": "LAN3", "fw": "LAN3", "wan": False, "link": True, "speed": "100", "up": 0, "down": 0, "upText": "0", "downText": "0"},
]

last_payload = {}


def mk_state(dw_enable="1", main="0", sec="1"):
    eth = ETH.replace("<WANSelect>0</WANSelect>", "<WANSelect>%s</WANSelect>" % main)
    eth = eth.replace("<SecWanLink>1</SecWanLink>", "<SecWanLink>%s</SecWanLink>" % sec)
    dw = DW_ON_DHCP if dw_enable == "1" else DW_OFF
    return eth, dw


def bind_state(dw_enable="1", main="0", sec="1"):
    st = {"main": main, "sec": sec, "enable": dw_enable}
    applied = {}

    def eth_txt():
        return (ETH.replace("<WANSelect>0</WANSelect>", "<WANSelect>%s</WANSelect>" % st["main"])
                   .replace("<SecWanLink>1</SecWanLink>", "<SecWanLink>%s</SecWanLink>" % st["sec"]))

    def req(url, payload=None, timeout=20):
        if payload is not None:
            applied.update(payload)
            last_payload.clear()
            last_payload.update(payload)
            if str(payload.get("WANSelect", "")).strip():
                st["main"] = str(payload["WANSelect"])
            if str(payload.get("SecWanLink", "")).strip():
                st["sec"] = str(payload["SecWanLink"])
            if "Enable" in payload:
                st["enable"] = str(payload["Enable"])
            return 200, "<IF_ERRORSTR>SUCC</IF_ERRORSTR>"
        if "vue_internet_eth_data" in url:
            return 200, eth_txt()
        if "vue_dualwan_data" in url:
            dw = DW_ON_DHCP if st["enable"] == "1" else DW_OFF
            return 200, dw
        return 200, ""

    P = {
        "read_ports": lambda: [dict(p) for p in PORTS],
        "_raw_get": lambda url: req(url)[1],
        "req": req,
        "_insts": lambda txt, tag: parse_insts(txt, tag),
        "rand16": lambda: "0123456789abcdef",
        "enc_para": lambda s, a, b: "ENC(%s)" % s,
        "enc_key": lambda a, b: "KEY",
    }
    lanwan.bind(P)
    return applied


def parse_insts(txt, tag):
    out = []
    for m in re.finditer(r'<Inst ID="%s"[^>]*>(.*?)</Inst>' % re.escape(tag), txt, re.S):
        blk = m.group(1)
        d = {}
        for k, v in re.findall(r"<(\w+)>(.*?)</\1>", blk, re.S):
            d[k] = v
        out.append(d)
    return out


def call(body):
    return lanwan.api_dualwan_set(body)


# ---------- 场景 ----------
# 1) 旧口径：只给 port（LAN3 -> WAN2）
bind_state()
r = call({"port": "LAN3"})
check("1 旧口径切 WAN2", r.get("ok") and r.get("sec") == 3, r)
check("1 WANSelect 保持主口", last_payload.get("WANSelect") == 0 and last_payload.get("SecWanLink") == 3, last_payload)

# 2) 两口同时换：WAN1->LAN1, WAN2->LAN2
bind_state()
r = call({"main": 1, "sec": 2})
check("2 两口同换 ok", r.get("ok"), r)
check("2 payload", last_payload.get("WANSelect") == 1 and last_payload.get("SecWanLink") == 2, last_payload)
check("2 msg", "WAN1" in r.get("msg", "") and "WAN2" in r.get("msg", ""), r.get("msg"))

# 3) 只换 WAN1
bind_state()
r = call({"main": 2})
check("3 只换 WAN1", r.get("ok") and r.get("main") == 2 and last_payload.get("SecWanLink") == 1, (r, last_payload))

# 4) WAN2 选硬件 WAN 口 -> 拒绝
bind_state()
try:
    call({"sec": 0})
    check("4 WAN 口当 WAN2 拒绝", False)
except ValueError as e:
    check("4 WAN 口当 WAN2 拒绝", "WAN1" in str(e) or "WAN2" in str(e), e)

# 5) WAN1 选当前 WAN2 正在用的口 -> 拒绝
bind_state(dw_enable="1", main="0", sec="2")
try:
    call({"main": 2})
    check("5 WAN1 抢 WAN2 口拒绝", False)
except ValueError as e:
    check("5 WAN1 抢 WAN2 口拒绝", "WAN2" in str(e), e)

# 6) WAN2 抢 WAN1 口：单独换 -> 拒绝；同时挪走 WAN1 -> 允许（互换）
bind_state(main="2", sec="1")
try:
    call({"sec": 2})
    check("6 WAN2 抢 WAN1 口拒绝", False)
except ValueError as e:
    check("6 WAN2 抢 WAN1 口拒绝", "WAN1" in str(e), e)
bind_state(main="2", sec="1")
r = call({"sec": 2, "main": 1})
check("6b 互换允许", r.get("ok") and last_payload.get("WANSelect") == 1
      and last_payload.get("SecWanLink") == 2, (r, last_payload))

# 7) 两口选同一个 -> 拒绝
bind_state()
try:
    call({"main": 3, "sec": 3})
    check("7 同口拒绝", False)
except ValueError as e:
    check("7 同口拒绝", "同一个口" in str(e), e)

# 8) 完全没变化 -> changed False
bind_state(main="0", sec="1", dw_enable="1")
r = call({"main": 0, "sec": 1})
check("8 无变化", r.get("ok") and not r.get("changed"), r)

# 9) WAN2 未启用时也能换口
bind_state(dw_enable="0", main="0", sec="1")
r = call({"sec": "LAN2"})
check("9 未启用换口", r.get("ok") and r.get("sec") == 2 and last_payload.get("Enable") == "0", (r, last_payload))

# 10) PPPoE 且读不到密码 -> 拒绝（保护宽带账号）
eth, _ = mk_state()
dw_pppoe = DW_ON_DHCP.replace("<WANCTYPE>dhcp</WANCTYPE><TransType>DHCP</TransType><Addressingtype>DHCP</Addressingtype>",
                              "<WANCTYPE>pppoe</WANCTYPE><TransType>PPPoE</TransType><Addressingtype>PPPoE</Addressingtype>")
applied = {}


def req_pppoe(url, payload=None, timeout=20):
    if payload is not None:
        applied.update(payload)
        return 200, "<IF_ERRORSTR>SUCC</IF_ERRORSTR>"
    if "vue_internet_eth_data" in url:
        return 200, eth
    if "GetPassword" in url:
        return 200, ""  # 拿不到密码
    if "vue_dualwan_data" in url:
        return 200, dw_pppoe
    return 200, ""


lanwan.bind({"read_ports": lambda: [dict(p) for p in PORTS], "_raw_get": lambda url: req_pppoe(url)[1],
             "req": req_pppoe, "_insts": parse_insts, "rand16": lambda: "x",
             "enc_para": lambda s, a, b: "E", "enc_key": lambda a, b: "K"})
try:
    call({"sec": 2})
    check("10 PPPoE 无密码拒绝", False)
except ValueError as e:
    check("10 PPPoE 无密码拒绝", "PPPoE" in str(e), e)

print("PASS:", len(PASS))
for s in PASS:
    print("  ok", s)
if FAIL:
    print("FAIL:", len(FAIL))
    for s in FAIL:
        print("  xx", s)
    sys.exit(1)
print("ALL PASS")
