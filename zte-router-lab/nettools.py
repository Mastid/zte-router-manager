# -*- coding: utf-8 -*-
"""网络工具（网络优化 / 网络排查 / 网络测速 / 上级光猫）。

以模块形式挂在 panel.py 上：panel.py 里 `import nettools; nettools.bind(globals())`，
这里通过 P[...] 调用面板已有的路由器访问函数，避免循环导入。
"""
import re
import socket
import ssl
import time
import urllib.request

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


# ---------------- 网络测速 ----------------

SPEED_MAX_BYTES = 20 * 1024 * 1024     # 最多下 20MB
SPEED_MAX_SECONDS = 7                  # 最多跑 7 秒
UA = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"

FALLBACK_URL = "https://speed.cloudflare.com/__down?bytes=30000000"

# 测速节点。idx 是发行版目录（iso 文件名里的版本号会变，运行时现场找）；
# host 用来量握手延迟（比请求页面更准，也不受镜像的反爬策略影响）。
NODES = [
    {"key": "ustc", "name": "中科大", "tag": "教育网", "host": "mirrors.ustc.edu.cn",
     "idx": "https://mirrors.ustc.edu.cn/ubuntu-releases/24.04/"},
    {"key": "tuna", "name": "清华 TUNA", "tag": "教育网", "host": "mirrors.tuna.tsinghua.edu.cn",
     "idx": "https://mirrors.tuna.tsinghua.edu.cn/ubuntu-releases/24.04/"},
    {"key": "nju", "name": "南京大学", "tag": "教育网", "host": "mirror.nju.edu.cn",
     "idx": "https://mirror.nju.edu.cn/ubuntu-releases/24.04/"},
    {"key": "huawei", "name": "华为云", "tag": "公有云", "host": "mirrors.huaweicloud.com",
     "idx": "https://mirrors.huaweicloud.com/ubuntu-releases/24.04/"},
    {"key": "cf", "name": "Cloudflare", "tag": "国际", "host": "speed.cloudflare.com",
     "url": FALLBACK_URL},
]


def _ext_open(url, timeout=8, range_bytes=0):
    hd = {"User-Agent": UA, "Accept": "*/*"}
    if range_bytes:
        hd["Range"] = "bytes=0-%d" % (range_bytes - 1)
    rq = urllib.request.Request(url, headers=hd)
    return urllib.request.urlopen(rq, timeout=timeout, context=ssl._create_unverified_context())


def _probe_ms(url, timeout=5.0):
    """取 1KB 测首字节延迟，作为节点远近的参考。"""
    t0 = time.time()
    with _ext_open(url, timeout=timeout, range_bytes=2048) as r:
        r.read(1024)
    return int((time.time() - t0) * 1000)


def _mirror_iso(idx):
    """列镜像目录挑最新的 server iso，返回完整直链。"""
    try:
        with _ext_open(idx, timeout=6) as r:
            page = r.read(600000).decode("utf-8", "ignore")
        names = sorted(set(re.findall(r"(ubuntu-[0-9][\w.\-]*live-server-amd64\.iso)", page)))
        if names:
            return idx + names[-1]          # 24.04.5 排在 24.04.3 之后，取最新
    except Exception:
        pass
    return ""


def _node_test_url(n):
    """节点的测速直链：镜像要现场解析 iso，Cloudflare 用固定接口。"""
    if n.get("idx"):
        return _mirror_iso(n["idx"])
    return n.get("url") or ""


def _speed_measure(url):
    t0 = time.time()
    got = 0
    with _ext_open(url, timeout=8, range_bytes=SPEED_MAX_BYTES) as r:
        while True:
            if time.time() - t0 > SPEED_MAX_SECONDS or got >= SPEED_MAX_BYTES:
                break
            chunk = r.read(65536)
            if not chunk:
                break
            got += len(chunk)
    sec = max(0.15, time.time() - t0)
    return got * 8.0 / sec, got, sec


def api_speednodes(body=None):
    """并发探测各节点握手延迟，按快慢排序（前端用来选节点）。

    用 TCP+TLS 握手而不是请求页面：镜像对脚本请求常回 403/429，
    但网络远近不受影响，握手时间照样准。
    """
    import concurrent.futures as _cf

    def one(n):
        t0 = time.time()
        try:
            s = socket.create_connection((n["host"], 443), 3.0)
            try:
                ctx = ssl._create_unverified_context()
                # 必须带 server_hostname（SNI），否则部分站点直接拒握手
                ctx.wrap_socket(s, server_hostname=n["host"])
            finally:
                s.close()
            ms = int((time.time() - t0) * 1000)
            return {"key": n["key"], "name": n["name"], "tag": n.get("tag", ""),
                    "ms": ms, "ok": True}
        except Exception as e:
            return {"key": n["key"], "name": n["name"], "tag": n.get("tag", ""),
                    "ms": 0, "ok": False, "err": str(e)[:60]}

    try:
        with _cf.ThreadPoolExecutor(max_workers=len(NODES)) as ex:
            rows = list(ex.map(one, NODES))
    except Exception as e:
        return {"ok": False, "error": str(e), "nodes": []}
    rows.sort(key=lambda r: (not r["ok"], r["ms"] or 99999))
    best = next((r["key"] for r in rows if r["ok"]), "")
    return {"ok": True, "nodes": rows, "best": best}


def _run_speed(url, name, key):
    try:
        bps, got, sec = _speed_measure(url)
        if got < 200 * 1024:
            return {"ok": False, "error": "%s 只返回了 %d KB，换下一个节点" % (name, got // 1024)}
        return {"ok": True, "mbps": round(bps / 1e6, 2), "bytes": got,
                "seconds": round(sec, 2), "source": name, "node": key,
                "nodeName": name, "url": url,
                "grade": ("很快" if bps >= 100e6 else "正常" if bps >= 30e6
                          else "偏慢" if bps >= 10e6 else "很慢")}
    except Exception as e:
        return {"ok": False, "error": "%s 失败：%s" % (name, e)}


def api_speedtest(body=None):
    """body: {node: key|auto, url: 自定义直链}"""
    body = body or {}
    custom = (body.get("url") or "").strip()
    want = (body.get("node") or "auto").strip()

    if custom:
        return _run_speed(custom, "自定义地址", "custom")

    # 指定了节点就先用它；auto 或该节点不可用时，按实测延迟从近到远排
    if want and want != "auto":
        head = [n for n in NODES if n["key"] == want]
        order = head + [n for n in NODES if n["key"] != want]
    else:
        rank = {}
        try:
            for r in api_speednodes()["nodes"]:
                rank[r["key"]] = (0 if r["ok"] else 1, r["ms"] or 99999)
        except Exception:
            rank = {}
        order = sorted(NODES, key=lambda n: rank.get(n["key"], (1, 99999)))

    err = ""
    for n in order:
        url = _node_test_url(n)
        if not url:
            err = "%s 暂时不可用（镜像目录没列出来）" % n["name"]
            continue
        r = _run_speed(url, n["name"], n["key"])
        if r.get("ok"):
            return r
        err = r.get("error") or err
    return {"ok": False, "error": err or "所有测速节点都不可用，可以手工填一个下载地址"}


# ---------------- 上级光猫 ----------------

# 光猫常见的管理地址（桥接/路由模式下不一定能直接访问，探测后给结论）
ONT_CANDIDATES = ["192.168.1.1", "192.168.0.1", "192.168.100.1", "192.168.2.1"]
ONT_PORTS = (80, 443, 8080)          # 光猫管理页基本是 80/443，少数改到 8080
ONT_TABLE = [("192.168.1.1", "电信 / 移动最常见"),
             ("192.168.0.1", "联通最常见"),
             ("192.168.100.1", "部分光猫 / 桥接后"),
             ("192.168.2.1", "部分华为、中兴")]


def _is_private(ip):
    p = (ip or "").strip().split(".")
    if len(p) != 4:
        return False
    try:
        a, b = int(p[0]), int(p[1])
    except Exception:
        return False
    return (a == 10 or (a == 172 and 16 <= b <= 31)
            or (a == 192 and b == 168) or (a == 100 and 64 <= b <= 127))


def _split_addr(s):
    """'192.168.1.1' / '192.168.1.1:8080' / 'http://192.168.1.1/' → (ip, port)"""
    s = (s or "").strip()
    m = re.match(r"^(?:https?://)?([0-9A-Za-z_.\-]+)(?::(\d{1,5}))?", s)
    if not m:
        return "", 0
    ip = m.group(1)
    if not re.match(r"^\d+\.\d+\.\d+\.\d+$", ip):
        return "", 0
    return ip, _num(m.group(2), 0)


def _wan_info():
    txt = _f("_raw_get", "/?_type=vueData&_tag=vue_internet_data&_=%d" % _now_ms())
    cand = _items_with(txt, ["ConnStatus"]) or _items_with(txt, ["IPAddress"]) or [{}]
    it = cand[0]
    return {"ip": (it.get("IPAddress") or "").strip(),
            "gw": (it.get("GateWay") or "").strip(),
            "conn": (it.get("ConnType") or "").strip(),
            "dns": (it.get("DNS1") or "").strip()}


def api_ont(body=None):
    """读 WAN 网关 → 并发探测光猫管理页，并给出「为什么进不去 / 怎么才能进去」。

    body: {ip: "192.168.1.1[:8080]"}。指定地址时只探这一个，且不依赖登录状态
    （手机上先去连光猫 Wi-Fi/网线，再回来探这个地址）。
    """
    body = body or {}
    manual, mport = _split_addr(body.get("ip") or "")

    wan = {"ip": "", "gw": "", "conn": "", "dns": ""}
    err = ""
    try:
        wan = _wan_info()
    except Exception as e:
        err = ("需要先登录路由器才能读取" if "NOT_LOGGED" in str(e)
               else ("读取宽带信息失败：%s" % e))
    if not manual and err:
        return {"ok": False, "logged": False, "error": err, "table": ONT_TABLE}

    pppoe = "pppoe" in (wan["conn"] or "").lower()
    gw = (wan["gw"] or "").strip()
    mode = "bridge" if pppoe else ("route" if gw and _is_private(gw) else "unknown")

    targets = []
    if manual:
        targets.append(manual)
    else:
        # 桥接拨号时网关是运营商的 BRAS（公网地址），探它没意义，还会白等超时
        if gw and gw != "0.0.0.0" and (not pppoe or _is_private(gw)):
            targets.append(gw)
        for ip in ONT_CANDIDATES:
            if ip not in targets:
                targets.append(ip)

    jobs = [(ip, p) for ip in targets for p in ([mport] if mport else ONT_PORTS)]

    def one(j):
        ip, port = j
        try:
            ms = _tcp_ms(ip, port, 1.1)
        except Exception:
            return None
        tail = "" if port in (80, 443) else (":%d" % port)
        return {"ip": ip, "port": port, "ms": ms, "isGw": ip == gw,
                "url": ("https://" if port == 443 else "http://") + ip + tail}

    rows = []
    try:
        import concurrent.futures as _cf
        with _cf.ThreadPoolExecutor(max_workers=min(12, max(1, len(jobs)))) as ex:
            rows = [r for r in ex.map(one, jobs) if r]
    except Exception:
        rows = []

    # 网关优先，其次 80 端口（光猫管理页基本都是 http），同条件比延迟
    rows.sort(key=lambda r: (not r["isGw"], r["port"] != 80, r["ms"]))
    best = rows[0] if rows else None

    if rows:
        note = ""
    elif manual:
        note = ("这个地址没响应。确认手机现在就接在光猫这一侧（光猫 LAN 口或光猫自带 Wi-Fi），"
                "端口也要对上，比如改过端口的写 192.168.1.1:8080。")
    elif pppoe:
        note = ("光猫现在跟路由器一起做桥接拨号，它的管理页只对「光猫自己的 LAN 口 / 光猫 Wi-Fi」"
                "开放，从路由器后面的手机是进不去的——这是正常现象，不是故障。")
    else:
        note = ("光猫看着是路由模式，但管理页没回应：可能改过管理端口，或在光猫里关掉了 LAN 侧 "
                "Web 管理。记得地址的话填到下面再探一次。")

    return {"ok": True, "wan": wan, "pppoe": pppoe, "mode": mode,
            "manual": bool(manual), "reachable": bool(rows), "best": best,
            "candidates": rows[:4], "note": note, "hint": note,
            "table": ONT_TABLE, "tried": len(jobs)}


# ---------------- 网络排查 ----------------

def _tcp_ms(host, port=443, timeout=3.0):
    t0 = time.time()
    s = socket.create_connection((host, port), timeout)
    try:
        s.close()
    except Exception:
        pass
    return int((time.time() - t0) * 1000)


def _items_with(txt, keys):
    """挑出同时含这些字段的条目；兼容 Instance/ParaName 与直接标签两种写法"""
    out = []
    if "<OBJ_" in (txt or ""):
        for items in (_f("groups", txt) or {}).values():
            for it in items:
                if all(k in it for k in keys):
                    out.append(it)
    if out:
        return out
    for block in re.findall(r"<Instance>(.*?)</Instance>", txt or "", re.S):
        it = dict(re.findall(r"<([A-Za-z0-9_]+)>([^<]*)</\1>", block))
        if all(k in it for k in keys):
            out.append(it)
    return out


def api_netdiag():
    items = []

    # 1) 本机 → 路由器
    try:
        t0 = time.time()
        st, _ = _f("req", "/?_type=loginsceneData&_tag=login_token_json", timeout=6)
        ms = int((time.time() - t0) * 1000)
        ok = st == 200 and ms < 1500
        items.append({"k": "router", "name": "手机到路由器", "level": "ok" if ok else "warn",
                      "detail": "响应 %d ms（HTTP %s）" % (ms, st),
                      "tip": "" if ok else "延迟偏高，看看 Wi-Fi 信号格数或换成 5G 频段"})
    except Exception as e:
        items.append({"k": "router", "name": "手机到路由器", "level": "bad",
                      "detail": "连不上：%s" % e, "tip": "确认手机连着这台路由的 Wi-Fi"})

    # 2) 路由器 WAN
    try:
        wan = _wan_info()
        ok = (wan["ip"] not in ("", "0.0.0.0")) or wan["conn"].lower().startswith("pppoe")
        items.append({"k": "wan", "name": "宽带连接", "level": "ok" if ok else "bad",
                      "detail": "类型 %s · IP %s · 网关 %s · DNS %s"
                                % (wan["conn"] or "-", wan["ip"] or "-",
                                   wan["gw"] or "-", wan["dns"] or "-"),
                      "tip": "" if ok else "路由器没拿到公网地址：检查光猫电源/网线，或在「网络」页重新拨号"})
    except Exception as e:
        notlogin = "NOT_LOGGED" in str(e)
        items.append({"k": "wan", "name": "宽带连接", "level": "warn",
                      "detail": "需要先登录路由器才能读取" if notlogin else ("读取失败：%s" % e),
                      "tip": "登录后点「重新检测」" if notlogin else ""})

    # 3) DNS
    try:
        t0 = time.time()
        socket.getaddrinfo("www.baidu.com", 443)
        ms = int((time.time() - t0) * 1000)
        ok = ms < 800
        items.append({"k": "dns", "name": "域名解析", "level": "ok" if ok else "warn",
                      "detail": "www.baidu.com 解析耗时 %d ms" % ms,
                      "tip": "" if ok else "解析偏慢，可在「局域网」里把 DNS 改成 223.5.5.5"})
    except Exception as e:
        items.append({"k": "dns", "name": "域名解析", "level": "bad",
                      "detail": "解析失败：%s" % e,
                      "tip": "能连 Wi-Fi 但网页打不开、微信还能发消息，多半是 DNS 问题"})

    # 4) 外网连通
    try:
        ms = _tcp_ms("mirrors.aliyun.com", 443)
        ok = ms < 400
        items.append({"k": "inet", "name": "外网连通", "level": "ok" if ok else "warn",
                      "detail": "连 mirrors.aliyun.com:443 耗时 %d ms" % ms,
                      "tip": "" if ok else "外网延迟偏高，可能是运营商线路问题"})
    except Exception as e:
        items.append({"k": "inet", "name": "外网连通", "level": "bad",
                      "detail": "连不上外网：%s" % e,
                      "tip": "Wi-Fi 正常但上不了网，常见是宽带欠费或光猫故障"})

    # 5) 局域网
    try:
        lan = _f("api_lan")
        dhcp = lan.get("dhcpOn")          # True / False / None(读不到)
        ok = dhcp is not False            # 未知时不误报成“已关闭”
        items.append({"k": "lan", "name": "局域网", "level": "ok" if ok else "warn",
                      "detail": "网关 %s · DHCP %s · 地址池 %s–%s"
                                % (lan.get("ip") or "-",
                                   "已开启" if dhcp is True else ("已关闭" if dhcp is False else "状态未知"),
                                   lan.get("min") or "-", lan.get("max") or "-"),
                      "tip": "" if ok else "DHCP 关了的话新设备要手动设 IP 才能上网"})
    except Exception as e:
        notlogin = "NOT_LOGGED" in str(e)
        items.append({"k": "lan", "name": "局域网", "level": "warn",
                      "detail": "需要先登录路由器才能读取" if notlogin else ("读取失败：%s" % e),
                      "tip": ""})

    bad = [i for i in items if i["level"] == "bad"]
    warn = [i for i in items if i["level"] == "warn"]
    if bad:
        summary = "发现 %d 项异常、%d 项需留意：%s" % (len(bad), len(warn), bad[0]["name"])
    elif warn:
        summary = "%d 项需留意，其余正常" % len(warn)
    else:
        summary = "全部正常，网络状况不错"
    return {"ok": True, "items": items, "summary": summary}


# ---------------- 网络优化 ----------------

DEFAULT_CH_24 = [str(i) for i in range(1, 14)]
DEFAULT_CH_5 = ["36", "40", "44", "48", "149", "153", "157", "161", "165"]


def _num(s, d=0):
    try:
        return int(float(str(s).strip()))
    except Exception:
        return d


def _band_of_ch(ch):
    n = _num(ch, 0)
    return "2.4G" if 0 < n <= 14 else "5G"


def _scan_aps():
    """周边 Wi-Fi 扫描：固件裁剪了该页面就返回空 + 原因。"""
    paths = [
        "/?_type=vueData&_tag=vue_scanap_data&_=%d",
        "/?_type=hiddenData&_tag=netwlanscan_data&_=%d",
        "/?_type=vueData&_tag=wlan_scanap_data&_=%d",
    ]
    err = ""
    for p in paths:
        try:
            txt = _f("_raw_get", p % _now_ms())
        except Exception as e:
            err = str(e)
            continue
        if not txt or "<OBJ_" not in txt:
            continue
        rows = []
        for items in (_f("groups", txt) or {}).values():
            for it in items:
                ssid = (it.get("SSID") or it.get("ESSID") or it.get("WlanName") or "").strip()
                rssi = _num(it.get("RSSI") or it.get("Signal") or it.get("SignalStrength")
                            or it.get("Rssi"), -100)
                ch = (it.get("Channel") or it.get("ChanNum") or it.get("ChannelNum") or "").strip()
                if not ch and not ssid:
                    continue
                rows.append({"ssid": ssid, "channel": ch or "-",
                             "band": _band_of_ch(ch), "rssi": rssi})
        if rows:
            return {"aps": rows, "err": ""}
    return {"aps": [], "err": err or "固件没提供周边 Wi-Fi 扫描接口"}


def _congestion(band, ch, aps):
    """信道拥挤度：2.4G 按 ±4 邻道重叠计权，5G 只看同信道。分数越大越挤。"""
    score = 0
    c = _num(ch, 0)
    for a in aps:
        ac = _num(a.get("channel"), 0)
        if not ac:
            continue
        w = max(1, 100 + int(a.get("rssi") or -100))       # -90dBm→10, -30dBm→70
        if band == "2.4G":
            if abs(ac - c) <= 4:
                score += w * (1.0 - abs(ac - c) * 0.15)
        else:
            if ac == c:
                score += w
    return int(score)


def api_optimize():
    try:
        wm = _f("api_wifimgr")
    except Exception as e:
        notlogin = "NOT_LOGGED" in str(e)
        return {"ok": False, "logged": not notlogin,
                "error": "需要先登录路由器" if notlogin else ("读取无线信息失败：%s" % e)}

    bands = wm.get("bands") or []
    scan = _scan_aps()
    aps = scan.get("aps") or []
    rec, tips = [], []

    for b in bands:
        band = b.get("band") or ""
        cur = (b.get("channel") or "").strip()
        if band == "2.4G":
            cands = DEFAULT_CH_24
        else:
            cands = sorted(set(DEFAULT_CH_5 + [a["channel"] for a in aps
                                               if a["band"] == band and _num(a["channel"], 0)]),
                           key=lambda x: _num(x, 0))
        scores = {c: _congestion(band, c, aps) for c in cands}
        best = min(scores, key=lambda c: scores[c]) if scores else ""
        rec.append({"band": band, "nowChannel": cur or "自动",
                    "channel": best, "score": min(100, scores.get(best, 0)),
                    "nowScore": min(100, scores.get(cur, 0)) if cur else None})

        if band == "2.4G" and "40" in (b.get("bw") or ""):
            tips.append({"level": "warn",
                         "text": "2.4G 用了 40MHz 频宽，容易和邻居互相干扰，改成 20MHz 更稳"})
        if best and cur and scores.get(cur, 0) - scores.get(best, 0) >= 20:
            tips.append({"level": "warn",
                         "text": "%s 建议从 %s 换到 %s 信道（拥挤度 %d → %d）"
                                 % (band, cur, best, scores.get(cur, 0), scores.get(best, 0))})
        elif best:
            tips.append({"level": "ok", "text": "%s 当前信道已经比较空，不用动" % band})

    if aps:
        tips.append({"level": "ok", "text": "扫描到 %d 个周边 Wi-Fi，已按信号强度算进拥挤度" % len(aps)})
    else:
        tips.append({"level": "warn",
                     "text": "没有周边 Wi-Fi 扫描数据（%s），下面的建议是按通用规则给的" % scan.get("err", "")})
    if not bands:
        return {"ok": False, "error": "没读到无线信道信息"}
    return {"ok": True, "bands": bands, "rec": rec, "scan": scan, "tips": tips}


# ---------------- 路由器侧 ping（备用深度项） ----------------

def api_ping(host="", iface=""):
    """走固件的 ping 诊断接口：POST IF_ACTION=PingDiagnosis，再轮询 PingAck。"""
    host = (host or "").strip() or "www.baidu.com"
    tag = "/?_type=vueData&_tag=ping_diag_data&_=%d" % _now_ms()
    try:
        _f("req", tag, {"IF_ACTION": "PingDiagnosis", "HostName": host,
                        "IF_ACTION_MODE": "1", "Interface": iface or ""}, 8)
    except Exception as e:
        return {"ok": False, "error": "发送诊断请求失败：%s" % e}
    for _ in range(12):
        time.sleep(1)
        try:
            txt = _f("_raw_get", tag)
        except Exception:
            continue
        rows = _items_with(txt, ["PingAck"]) or []
        if not rows:
            continue
        ack = (rows[0].get("PingAck") or "").strip()
        if ack and ack.upper() != "NULL":
            return {"ok": True, "host": host, "ack": ack, "raw": rows[0]}
    return {"ok": False, "error": "路由器没有返回诊断结果（固件可能不支持）"}
