# -*- coding: utf-8 -*-
"""等面板登录后自动跑一次令牌诊断，结果写入 logs/probe.txt"""
import json
import time
import urllib.error
import urllib.request

B = "http://127.0.0.1:8900"
OUT = "logs/probe.txt"


def get(p, t=25):
    r = urllib.request.urlopen(B + p, timeout=t)
    return json.loads(r.read().decode())


def post(p, body=None, t=150):
    req = urllib.request.Request(
        B + p,
        data=json.dumps(body or {}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        r = urllib.request.urlopen(req, timeout=t)
        return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"raw": "unparsable"}


def log(msg):
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg)


open(OUT, "w", encoding="utf-8").close()
log("等待登录…")

deadline = time.time() + 900
while time.time() < deadline:
    try:
        if get("/api/state", t=6).get("logged"):
            break
    except Exception:
        pass
    time.sleep(2)
else:
    log("超时：一直没有登录")
    raise SystemExit(0)

log("已登录，读取改前配置…")
before = None
for _ in range(10):
    try:
        d = get("/api/all", t=20)
        before = [(w["band"], w["ssid"], w["on"], w["enc"]) for w in d["wifi"]]
        break
    except Exception as e:
        log("  读取失败 %s，重试" % e)
        time.sleep(2)

log("改前: %s" % (before,))
log("开始诊断令牌携带位置…")
st, res = post("/api/_probe")
log("诊断返回: %s %s" % (st, json.dumps(res, ensure_ascii=False)))

for i in range(16):
    time.sleep(3)
    try:
        d = get("/api/all", t=12)
        after = [(w["band"], w["ssid"], w["on"], w["enc"]) for w in d["wifi"]]
        log("改后: %s" % (after,))
        log("配置一致: %s | 客户端 %d" % (before == after, len(d["clients"])))
        break
    except Exception:
        log("  等待无线恢复 %d" % (i + 1))
log("完成")
