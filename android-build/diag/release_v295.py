# -*- coding: utf-8 -*-
"""手动发 Release：创建 v2.9.5 Release + 上传 APK 资产（token 从 .github_token 或参数）"""
import json
import sys
import urllib.request

TOKEN = sys.argv[1] if len(sys.argv) > 1 else ""
if not TOKEN:
    try:
        TOKEN = open("android-build/.github_token", encoding="utf-8").read().strip()
    except Exception:
        pass
if not TOKEN:
    print("NO_TOKEN")
    sys.exit(1)

REPO = "Mastid/zte-router-manager"
VER = sys.argv[2] if len(sys.argv) > 2 else "v2.9.6"
APK = "android-build/ZTE-RouterManager-%s.apk" % (VER,)

notes = []
f = False
for line in open("CHANGELOG.md", encoding="utf-8"):
    if line.startswith("## " + VER):
        f = True
        continue
    if f and line.startswith("## "):
        break
    if f:
        notes.append(line.rstrip())
body = "\n".join(notes).strip()


def api(url, data=None, ctype="application/json", method=None):
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Content-Type", ctype)
    req.add_header("User-Agent", "release-script")
    return urllib.request.urlopen(req, timeout=60).read()


# 已有同名 Release 就复用（404 = 还没发过）
try:
    rel = json.loads(api("https://api.github.com/repos/%s/releases/tags/%s" % (REPO, VER)))
    rid = rel.get("id")
    print("REUSE_RELEASE id=%s" % rid)
except urllib.error.HTTPError as e:
    if e.code != 404:
        raise
    rel = json.loads(api(
        "https://api.github.com/repos/%s/releases" % REPO,
        json.dumps({
            "tag_name": VER, "target_commitish": "main", "name": VER,
            "body": body, "draft": False, "prerelease": False,
        }).encode("utf-8")))
    rid = rel.get("id")
    print("RELEASE_OK id=%s" % rid)

data = open(APK, "rb").read()
url = ("https://uploads.github.com/repos/%s/releases/%d/assets"
       "?name=ZTE-RouterManager-%s.apk" % (REPO, rid, VER))
asset = json.loads(api(url, data, "application/vnd.android.package-archive"))
if asset.get("browser_download_url"):
    print("ASSET_OK " + asset["browser_download_url"])
else:
    print("ASSET_ERR " + json.dumps(asset)[:300])
