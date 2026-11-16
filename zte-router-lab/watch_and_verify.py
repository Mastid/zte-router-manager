# -*- coding: utf-8 -*-
"""等面板登录成功后，自动跑重启验证并把结果写到 logs/reboot-verify.txt"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "logs", "reboot-verify.txt")
B = "http://127.0.0.1:8900"


def logged():
    try:
        with urllib.request.urlopen(B + "/api/all", timeout=40) as r:
            return r.status == 200
    except Exception:
        return False


print("等待登录（最长 20 分钟）…", flush=True)
deadline = time.time() + 1200
ok = False
while time.time() < deadline:
    if logged():
        ok = True
        break
    time.sleep(3)

if not ok:
    print("超时：未检测到登录", flush=True)
    sys.exit(1)

print("检测到登录，3 秒后开始重启验证（会断网 1-2 分钟）", flush=True)
time.sleep(3)

with open(OUT, "w", encoding="utf-8") as f:
    p = subprocess.run([sys.executable, os.path.join(BASE, "verify_reboot.py")],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
    txt = p.stdout.decode("utf-8", "replace")
    f.write(txt)
print(txt, flush=True)
print("结果已保存:", OUT, flush=True)
