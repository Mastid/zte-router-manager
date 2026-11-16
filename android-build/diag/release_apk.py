#!/usr/bin/env python3
"""自动发布 APK 到 GitHub Release。

用法：
    python release_apk.py            # 检测最新 APK，有新版本就发 Release
    python release_apk.py --check    # 只检查是否有新版本，不发布

行为：
1. 在 android-build/ 里找最新的 ZTE-RouterManager-v*.apk
2. 和 GitHub 上最新的 Release 比版本；相同则退出（无新版本）
3. 升级点取自仓库根目录 CHANGELOG.md 里对应版本的段落；没有就用 git log
4. 创建 Release 并上传 APK
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ANDROID = os.path.dirname(HERE)
ROOT = os.path.dirname(ANDROID)
REPO = "Mastid/zte-router-manager"
TOKEN_FILE = os.path.join(ANDROID, ".github_token")


def get_token():
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        return tok.strip()
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, encoding="utf-8") as f:
            return f.read().strip()
    print("NO_TOKEN: 没有 GITHUB_TOKEN 环境变量，也没有 %s" % TOKEN_FILE)
    sys.exit(2)


def api(method, path, token, payload=None, ctype="application/vnd.github+json", timeout=30):
    url = path if path.startswith("http") else "https://api.github.com" + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "token " + token)
    req.add_header("Accept", "application/vnd.github+json")
    if data:
        req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode()
            return r.status, (json.loads(body) if body.strip().startswith(("{", "[")) else {})
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def newest_apk():
    cands = []
    for n in os.listdir(ANDROID):
        m = re.match(r"ZTE-RouterManager-v([\d.]+)\.apk$", n)
        if m:
            cands.append((os.path.getmtime(os.path.join(ANDROID, n)), m.group(1), n))
    if not cands:
        print("NO_APK: android-build 里没有 ZTE-RouterManager-v*.apk")
        sys.exit(1)
    cands.sort()
    return cands[-1][1], cands[-1][2]


def existing_tags(token):
    st, rels = api("GET", "/repos/%s/releases?per_page=100" % REPO, token)
    if st != 200:
        print("API_ERR: 拉 releases 失败 %s %s" % (st, rels.get("message")))
        sys.exit(3)
    return {r.get("tag_name", "") for r in rels}


def changelog_notes(ver):
    """CHANGELOG.md 里取 '## v<ver>' 段落；没有就返回 None"""
    path = os.path.join(ROOT, "CHANGELOG.md")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^##\s+v%s(\s|（|$)" % re.escape(ver), ln.strip()):
            start = i
            break
    if start is None:
        return None
    out = [lines[start]]
    for ln in lines[start + 1:]:
        if ln.startswith("## "):
            break
        out.append(ln)
    return "\n".join(out).strip()


def gitlog_notes(ver):
    try:
        log = subprocess.run(
            ["git", "log", "--pretty=%h %s", "-12"], cwd=ROOT,
            capture_output=True, text=True, timeout=10).stdout.strip()
        return "自动生成自最近提交：\n\n" + log
    except Exception:
        return "版本 v%s" % ver


def main():
    check_only = "--check" in sys.argv
    token = get_token()
    ver, apk_name = newest_apk()
    tags = existing_tags(token)
    if "v%s" % ver in tags:
        print("NO_NEW: 最新 APK 是 v%s，GitHub 上已有该版本的 Release，无需发布" % ver)
        return
    if check_only:
        print("NEW_VERSION: v%s（%s）尚未发布" % (ver, apk_name))
        return

    notes = changelog_notes(ver) or gitlog_notes(ver)
    st, rel = api("POST", "/repos/%s/releases" % REPO, token, {
        "tag_name": "v%s" % ver,
        "target_commitish": "main",
        "name": "v%s" % ver,
        "body": notes,
        "draft": False,
        "prerelease": False,
    })
    if st not in (200, 201):
        print("REL_ERR: %s %s" % (st, rel.get("message")))
        sys.exit(4)
    rid = rel["id"]
    print("RELEASE_OK: %s" % rel.get("html_url"))

    apk_path = os.path.join(ANDROID, apk_name)
    url = "https://uploads.github.com/repos/%s/releases/%d/assets?name=%s" % (
        REPO, rid, apk_name)
    data = open(apk_path, "rb").read()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", "token " + token)
    req.add_header("Content-Type", "application/vnd.android.package-archive")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            asset = json.loads(r.read().decode())
        print("ASSET_OK: %s（%d bytes）" % (asset.get("name"), asset.get("size", 0)))
        print("DOWNLOAD: %s" % asset.get("browser_download_url"))
    except urllib.error.HTTPError as e:
        print("ASSET_ERR: %s %s" % (e.code, e.read().decode()[:300]))
        sys.exit(5)


if __name__ == "__main__":
    main()
