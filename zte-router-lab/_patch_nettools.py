# -*- coding: utf-8 -*-
"""一次性脚本：替换 nettools.py 里的测速段并追加光猫检测。"""
import io

p = "nettools.py"
s = io.open(p, encoding="utf-8").read()
start = s.index("# ---------------- 网络测速 ----------------")
end = s.index("# ---------------- 网络优化 ----------------")

new = r'''# ---------------- 网络测速 ----------------

SPEED_MAX_BYTES = 20 * 1024 * 1024     # 最多下 20MB
SPEED_MAX_SECONDS = 7                  # 最多跑 7 秒
UA = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"

FALLBACK_URL = "https://speed.cloudflare.com/__down?bytes=30000000"

# 测速节点。idx 是发行版目录（iso 文件名里的版本号会变，运行时现场找）；
# 高校镜像都支持 Range(206)，华为对连续大流量会 429，所以放后面。
NODES = [
    {"key": "ustc", "name": "中科大", "tag": "教育网",
     "idx": "https://mirrors.ustc.edu.cn/ubuntu-releases/24.04/"},
    {"key": "tuna", "name": "清华 TUNA", "tag": "教育网",
     "idx": "https://mirrors.tuna.tsinghua.edu.cn/ubuntu-releases/24.04/"},
    {"key": "nju", "name": "南京大学", "tag": "教育网",
     "idx": "https://mirror.nju.edu.cn/ubuntu-releases/24.04/"},
    {"key": "huawei", "name": "华为云", "tag": "公有云",
     "idx": "https://mirrors.huaweicloud.com/ubuntu-releases/24.04/"},
    {"key": "cf", "name": "Cloudflare", "tag": "国际", "url": FALLBACK_URL},
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
    """并发探测各节点首字节延迟，按快慢排序（前端用来选节点）。"""
    import concurrent.futures as _cf

    def one(n):
        url = n.get("idx") or n.get("url")
        try:
            ms = _probe_ms(url, 5.0)
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
    body = body or {}
    custom = (body.get("url") or "").strip()
    want = (body.get("node") or "auto").strip()

    if custom:
        return _run_speed(custom, "自定义地址", "custom")

    # 指定了节点就先用它；auto 或指定节点不可用时，按实测延迟从近到远排
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


def api_ont(body=None):
    """读取 WAN 网关并探测上级光猫的管理页是否可达。"""
    wan = {"ip": "", "gw": "", "conn": "", "dns": ""}
    try:
        txt = _f("_raw_get", "/?_type=vueData&_tag=vue_internet_data&_=%d" % _f("_now_ms"))
        cand = _items_with(txt, ["ConnStatus"]) or _items_with(txt, ["IPAddress"]) or [{}]
        it = cand[0]
        wan = {"ip": (it.get("IPAddress") or "").strip(),
               "gw": (it.get("GateWay") or "").strip(),
               "conn": (it.get("ConnType") or "").strip(),
               "dns": (it.get("DNS1") or "").strip()}
    except Exception as e:
        notlogin = "NOT_LOGGED" in str(e)
        return {"ok": False, "logged": not notlogin,
                "error": "需要先登录路由器才能读取" if notlogin else ("读取宽带信息失败：%s" % e)}

    pppoe = "pppoe" in (wan["conn"] or "").lower()
    ips, seen = [], set()
    for ip in (([wan["gw"]] if wan["gw"] else []) + ONT_CANDIDATES):
        ip = (ip or "").strip()
        if not ip or ip in ("0.0.0.0", "127.0.0.1") or ip in seen:
            continue
        # PPPoE 时 WAN 网关是运营商的 BRAS，不是光猫，但仍可以点开看看
        seen.add(ip)
        ips.append(ip)

    rows = []
    for ip in ips:
        for port in (80, 443):
            try:
                ms = _tcp_ms(ip, port, 1.0)
            except Exception:
                continue
            rows.append({"ip": ip, "port": port, "ms": ms,
                         "isGw": ip == wan["gw"],
                         "url": ("https://" if port == 443 else "http://") + ip})
    # 80 优先（光猫管理页基本都是 http），同端口再比延迟
    rows.sort(key=lambda r: (not r["isGw"], r["port"] != 80, r["ms"]))
    best = rows[0] if rows else None

    hint = ""
    if not rows:
        hint = ("路由器用 PPPoE 拨号时，光猫通常关掉了管理页或做了隔离："
                "可以把网线直接插到光猫 LAN 口、或连光猫自带 Wi-Fi 后再打开 192.168.1.1。"
                if pppoe else
                "没探测到光猫管理页，可能光猫只做桥接不开 WEB 管理，或管理地址不是常见的 192.168.1.1。")
    return {"ok": True, "wan": wan, "pppoe": pppoe,
            "reachable": bool(rows), "best": best,
            "candidates": rows[:4], "hint": hint}


'''

s = s[:start] + new + s[end:]
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("written", len(s))
