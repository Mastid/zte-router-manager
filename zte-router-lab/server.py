# -*- coding: utf-8 -*-
"""
中兴路由实验室 / ZTE Router Lab
--------------------------------------------------
用途：把中兴家用路由（192.168.5.1，HTTPS）的 Web 后台代理到本机，
     方便在电脑上正常登录使用，同时把每一条请求记录下来。
     这些记录就是后续做手机 App 的接口依据。

只监听 127.0.0.1，不对外网开放，不上传任何数据。
"""
import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "requests.jsonl")

LISTEN_PORT = 8899

STATE = {"scheme": "https", "host": "192.168.5.1", "port": 443}
LOG = []
LOCK = threading.Lock()
SEQ = [0]
SESSION = {"cookies": {}}
SNAP_DONE = [False]

SNAPSHOT_DIR = os.path.join(LOG_DIR, "snapshot")
SNAP_TAGS = [
    ("vueData", "vue_home_device_data"),
    ("vueData", "vue_client_data"),
    ("vueData", "vue_landevice_data"),
    ("vueData", "vue_wlandevice_data"),
    ("vueData", "vue_ssidconfig_data"),
    ("vueData", "wifiAP_data"),
    ("vueData", "wiazrdWifi_data"),
    ("vueData", "vue_internet_data"),
    ("vueData", "vue_topo_data"),
    ("vueData", "vue_loadprevent_data"),
    ("vueData", "vue_nowversion_lua"),
    ("vueData", "vue_pctrl_group_data"),
    ("hiddenData", "vue_userif_data"),
    ("hiddenData", "vue_macfilterrule_data"),
    ("hiddenScene", "initial_info_json"),
]

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

REQ_DROP = {
    "host", "connection", "accept-encoding", "content-length", "transfer-encoding",
    "proxy-connection", "upgrade", "keep-alive", "te", "trailer",
}
RESP_DROP = {
    "connection", "transfer-encoding", "content-encoding", "content-length",
    "keep-alive", "content-security-policy", "x-frame-options",
    "strict-transport-security", "public-key-pins",
}


def netloc():
    default = {"https": 443, "http": 80}[STATE["scheme"]]
    return STATE["host"] if STATE["port"] == default else "%s:%d" % (STATE["host"], STATE["port"])


def base_url():
    return "%s://%s" % (STATE["scheme"], netloc())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=SSL_CTX), NoRedirect()
)


def rewrite_urls(text):
    """把指向路由器的绝对地址改写成本地相对地址，保证所有流量继续走代理。"""
    for host in {STATE["host"], netloc(), base_url()}:
        text = text.replace("https://" + host, "")
        text = text.replace("http://" + host, "")
    return text


def record(entry):
    with LOCK:
        SEQ[0] += 1
        entry["id"] = SEQ[0]
        LOG.append(entry)
        if len(LOG) > 600:
            del LOG[:200]
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def forward(method, path, headers, body, timeout=20):
    url = base_url() + path
    req = urllib.request.Request(url, data=body if body else None, method=method)
    browser_cookie = ""
    for k, v in headers.items():
        lk = k.lower()
        if lk in REQ_DROP:
            continue
        if lk == "cookie":
            browser_cookie = v
            continue
        if lk in ("referer", "origin"):
            v = rewrite_urls(v) or base_url()
            if v.startswith("/"):
                v = base_url() + v
        req.add_header(k, v)
    merged = dict(SESSION["cookies"])
    for part in (browser_cookie or "").split(";"):
        if "=" in part:
            ck, cv = part.strip().split("=", 1)
            if ck:
                merged[ck] = cv
    if merged:
        req.add_header("Cookie", "; ".join("%s=%s" % (k, v) for k, v in merged.items()))
    req.add_header("Accept-Encoding", "identity")

    started = time.time()
    try:
        resp = OPENER.open(req, timeout=timeout)
        status, rhdrs, raw = resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        status, rhdrs, raw = e.code, e.headers, e.read()
    except Exception as e:
        return 0, [], ("UPSTREAM_ERROR: %s" % e).encode("utf-8"), int((time.time() - started) * 1000)

    ctype = (rhdrs.get("Content-Type") or "").lower()
    if ("text/html" in ctype or "javascript" in ctype or "json" in ctype) and raw:
        try:
            text = raw.decode("utf-8", "replace")
            new = rewrite_urls(text)
            if new != text:
                raw = new.encode("utf-8")
        except Exception:
            pass

    out = []
    for k, v in rhdrs.items():
        lk = k.lower()
        if lk in RESP_DROP:
            continue
        if lk == "location":
            v = rewrite_urls(v) or v
        elif lk == "set-cookie":
            m = re.match(r"\s*([^=]+)=([^;]*)", v)
            if m:
                SESSION["cookies"][m.group(1).strip()] = m.group(2).strip()
            v = re.sub(r";\s*Domain=[^;]*", "", v, flags=re.I)
            v = re.sub(r";\s*Secure", "", v, flags=re.I)
            v = re.sub(r";\s*SameSite=None", "; SameSite=Lax", v, flags=re.I)
        out.append((k, v))

    return status, out, raw, int((time.time() - started) * 1000)


PROBES = [
    ("/", "首页"),
    ("/?_type=loginData&_tag=login_entry", "登录入口(loginData)"),
    ("/?_type=vueData&_tag=vue_login_data", "登录数据(vueData)"),
    ("/?_type=menuView&_tag=statusMgr", "状态页(menuView)"),
    ("/?_type=menuData&_tag=devmgr_statusmgr_lua.lua", "设备状态(lua)"),
    ("/?_type=vueData&_tag=vue_client_data", "客户端列表(vueData)"),
    ("/cgi-bin/luci", "Luci 入口"),
    ("/goform/goform_get_cmd_process?isTest=false&cmd=LD", "CPE goform 接口"),
    ("/api/system/status", "REST 状态"),
]


def run_probe():
    def one(item):
        path, label = item
        t0 = time.time()
        try:
            status, hdrs, raw, ms = forward("GET", path, {"User-Agent": "zte-lab/1.0"}, None, timeout=6)
            ctype = ""
            for k, v in hdrs:
                if k.lower() == "content-type":
                    ctype = v
                    break
            snippet = raw[:220].decode("utf-8", "replace") if raw else ""
            snippet = re.sub(r"\s+", " ", snippet)
            return {
                "path": path, "label": label, "status": status,
                "ctype": ctype, "ms": ms, "snippet": snippet,
            }
        except Exception as e:
            return {"path": path, "label": label, "status": 0, "ctype": "", "ms": 0, "snippet": str(e)}

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(one, PROBES))
    for r in results:
        record({
            "t": time.strftime("%H:%M:%S"),
            "method": "PROBE",
            "path": r["path"],
            "status": r["status"],
            "ctype": r["ctype"],
            "ms": r["ms"],
            "tag": r["label"],
            "resp": r["snippet"][:160],
        })
    return results


def run_snapshot():
    """登录成功后自动把关键接口全抓一遍，存成原始响应。"""
    if SNAP_DONE[0]:
        return
    SNAP_DONE[0] = True
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    ok = 0
    for typ, tag in SNAP_TAGS:
        path = "/?_type=%s&_tag=%s" % (typ, tag)
        try:
            status, hdrs, raw, ms = forward(
                "GET", path, {"Content-Type": "text/xml; charset=utf-8"}, None, timeout=12
            )
        except Exception as e:
            status, raw, ms = 0, str(e).encode("utf-8"), 0
        try:
            with open(os.path.join(SNAPSHOT_DIR, "%s.txt" % tag), "w", encoding="utf-8") as f:
                f.write("PATH: %s\nSTATUS: %s\n\n" % (path, status))
                f.write(raw[:400000].decode("utf-8", "replace"))
        except Exception:
            pass
        if status == 200:
            ok += 1
        record({
            "t": time.strftime("%H:%M:%S"), "method": "SNAP", "path": path,
            "status": status, "ctype": "snapshot", "ms": ms, "size": len(raw),
            "resp": re.sub(r"\s+", " ", raw[:200].decode("utf-8", "replace")),
        })
    record({
        "t": time.strftime("%H:%M:%S"), "method": "SNAP",
        "path": "采集完成 %d/%d" % (ok, len(SNAP_TAGS)), "status": 200,
        "ctype": "info", "ms": 0, "size": 0, "resp": "",
    })


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ZTELab/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, status, body, ctype="text/plain; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or []):
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, status=200):
        self._send(status, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _handle(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = ("?" + parsed.query) if parsed.query else ""
        full_path = path + query

        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""

        if path == "/__ui":
            ui = os.path.join(BASE_DIR, "ui.html")
            with open(ui, "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
            return

        if path == "/__state":
            self._json(STATE)
            return

        if path == "/__target" and self.command == "POST":
            try:
                data = json.loads(body.decode("utf-8") or "{}")
                host = (data.get("host") or "").strip()
                host = re.sub(r"^https?://", "", host).split("/")[0]
                if ":" in host:
                    host, p = host.rsplit(":", 1)
                    data["port"] = int(p)
                STATE["host"] = host or STATE["host"]
                STATE["scheme"] = data.get("scheme") or STATE["scheme"]
                STATE["port"] = int(data.get("port") or STATE["port"])
                self._json({"ok": True, "state": STATE})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
            return

        if path == "/__probe":
            self._json({"results": run_probe(), "target": base_url()})
            return

        if path == "/__log":
            since = int(parsed.query.split("=")[-1]) if "since=" in parsed.query else 0
            with LOCK:
                items = [x for x in LOG if x["id"] > since]
            self._json({"items": items, "last": SEQ[0], "total": len(LOG)})
            return

        if path == "/__clear":
            with LOCK:
                LOG.clear()
            open(LOG_FILE, "w", encoding="utf-8").close()
            self._json({"ok": True})
            return

        # ---- 其余全部代理到路由器 ----
        hdrs = {k: v for k, v in self.headers.items()}
        status, rhdrs, raw, ms = forward(self.command, full_path, hdrs, body)

        ctype = "application/octet-stream"
        for k, v in rhdrs:
            if k.lower() == "content-type":
                ctype = v
                break

        record({
            "t": time.strftime("%H:%M:%S"),
            "method": self.command,
            "path": full_path,
            "status": status,
            "ctype": ctype,
            "ms": ms,
            "size": len(raw),
            "req": body[:300].decode("utf-8", "replace") if body else "",
            "resp": raw[:400].decode("utf-8", "replace") if raw else "",
        })

        # 写操作：完整记录请求头与请求体，用于核对令牌/加密参数
        if self.command == "POST" and "_type=" in full_path:
            try:
                with open(os.path.join(LOG_DIR, "capture.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "t": time.strftime("%H:%M:%S"),
                        "path": full_path,
                        "status": status,
                        "req_headers": hdrs,
                        "req_body": body.decode("utf-8", "replace"),
                        "resp": raw[:1500].decode("utf-8", "replace"),
                        "resp_headers": rhdrs,
                    }, ensure_ascii=False) + "\n")
            except Exception:
                pass

        if "login_entry" in full_path and status == 200 and not SNAP_DONE[0]:
            snippet = raw[:4000].decode("utf-8", "replace")
            if "sess_token" in snippet or "login_need_refresh" in snippet:
                threading.Thread(target=run_snapshot, daemon=True).start()

        self._send(status or 502, raw, ctype, rhdrs)

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_DELETE = _handle
    do_HEAD = _handle


def main():
    if len(sys.argv) > 1:
        STATE["host"] = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else LISTEN_PORT
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("=" * 58)
    print(" 中兴路由实验室已启动")
    print(" 面板地址: http://127.0.0.1:%d/__ui" % port)
    print(" 当前目标: %s" % base_url())
    print(" 日志文件: %s" % LOG_FILE)
    print(" 关闭窗口即停止。")
    print("=" * 58)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
