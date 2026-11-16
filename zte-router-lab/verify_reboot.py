# -*- coding: utf-8 -*-
"""重启路由器真机验证：记录基线 → 触发重启 → 探测掉线与恢复 → 输出时间线"""
import json
import ssl
import time
import urllib.error
import urllib.request
import hashlib

B = "http://127.0.0.1:8900"
GW = "https://192.168.5.1/"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def api(path, method="GET", body=None, timeout=45):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        B + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def sig(s):
    return hashlib.sha256((s or "").encode()).hexdigest()[:10]


def probe(timeout=2.0):
    """探测路由器管理页是否可访问；返回 (ok, 说明)"""
    t0 = time.time()
    try:
        req = urllib.request.Request(GW, headers={"User-Agent": "reboot-check"})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            body = r.read(4096)
            return True, "%d/%.0fms" % (r.status, (time.time() - t0) * 1000 if body else 0)
    except Exception as e:
        return False, type(e).__name__


print("=" * 60)
print("一、重启前基线")
st, d0 = api("/api/all")
if st != 200:
    print("读取失败:", st, d0)
    print("→ 面板会话已失效，请先在 http://127.0.0.1:8900/ 登录一次再运行本脚本")
    raise SystemExit(1)
wifi0 = [(w["band"], w["ssid"], w["on"], w["enc"], w.get("hidden")) for w in d0["wifi"]]
pwd0 = {}
for b in ("2.4G", "5G"):
    _, v = api("/api/wifi/pwd?band=" + b)
    pwd0[b] = v.get("pwd") or ""
print("  型号      :", d0["dev"]["name"], "/", d0["dev"]["model"], d0["dev"]["fw"])
print("  WAN 在线  :", d0["wan"]["uptime"], "| IP", d0["wan"]["ip"], "|", d0["wan"]["type"])
print("  WiFi      :", wifi0)
print("  密码指纹  :", {k: sig(v) for k, v in pwd0.items()})
print("  在线设备  :", len(d0["clients"]), "（有线 %s / 无线 %s）" % (d0["wired"], d0["wireless"]))
ok, note = probe()
print("  管理页    :", "可访问" if ok else "不可访问", note)

print()
print("二、发起重启")
t_req = time.time()
st, res = api("/api/reboot", "POST", {}, timeout=60)
print("  接口返回  :", st, res)
if not res.get("ok"):
    print("重启请求未被接受，终止验证")
    raise SystemExit(2)

print()
print("三、探测掉线与恢复（每 1.5 秒一次，最长 4 分钟）")
down_at = None
up_at = None
fails = 0
last = None
deadline = time.time() + 240
while time.time() < deadline:
    ok, note = probe(timeout=2.0)
    el = time.time() - t_req
    if not ok:
        fails += 1
        if down_at is None:
            down_at = time.time()
            print("  %6.1fs  路由器已断开（%s）" % (el, note))
    else:
        if down_at is not None and up_at is None:
            up_at = time.time()
            print("  %6.1fs  管理页恢复响应（%s）" % (el, note))
            break
        if last != "up":
            print("  %6.1fs  仍在线，等待掉线…" % el)
            last = "up"
    time.sleep(1.5)

print()
print("四、结论")
if up_at is None and down_at is not None:
    print("  掉线时间  : 请求后 %.1f 秒" % (down_at - t_req))
    print("  恢复时间  : 4 分钟内未恢复（可能仍在启动，需继续观察）")
elif down_at is None:
    print("  ✗ 未观察到掉线——重启请求可能未真正生效")
    print("  失败次数  :", fails)
else:
    print("  掉线时间  : 请求后 %.1f 秒" % (down_at - t_req))
    print("  恢复时间  : 请求后 %.1f 秒" % (up_at - t_req))
    print("  中断时长  : 约 %.0f 秒" % (up_at - down_at))

# 等页面稳定后再确认一次内容
for _ in range(20):
    ok, note = probe()
    if ok:
        break
    time.sleep(3)
try:
    req = urllib.request.Request(GW, headers={"User-Agent": "reboot-check"})
    with urllib.request.urlopen(req, timeout=6, context=ctx) as r:
        html = r.read().decode("utf-8", "replace")
    import re
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    print("  恢复后页面:", (m.group(1).strip() if m else "(无标题)"), "| 长度", len(html))
except Exception as e:
    print("  恢复后页面: 读取失败", e)

print()
print("五、重启后核对（等面板自动重登，最多 3 分钟）")
print("  ", api("/api/state")[1])
d1 = None
for i in range(20):
    st2, d1 = api("/api/all", timeout=45)
    if st2 == 200:
        break
    d1 = None
    time.sleep(9)
if d1:
    wifi1 = [(w["band"], w["ssid"], w["on"], w["enc"], w.get("hidden")) for w in d1["wifi"]]
    pwd1 = {}
    for b in ("2.4G", "5G"):
        pwd1[b] = api("/api/wifi/pwd?band=" + b)[1].get("pwd") or ""
    print("  WAN 在线  :", d1["wan"]["uptime"], "| IP", d1["wan"]["ip"])
    print("  WiFi      :", wifi1)
    print("  密码指纹  :", {k: sig(v) for k, v in pwd1.items()})
    print("  在线设备  :", len(d1["clients"]))
    print("  配置未丢  :", wifi0 == wifi1)
    print("  密码未变  :", pwd0 == pwd1)
    print("  在线时长归零:", d1["wan"]["uptime"] != d0["wan"]["uptime"],
          "(%s → %s)" % (d0["wan"]["uptime"], d1["wan"]["uptime"]))
else:
    print("  面板未能自动重登（需要手动登录一次）")
