"""等面板登录后，把可能含 CPU/内存字段的固件接口批量拉一遍，结果存 logs/probe_cpu.json"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8900"
TAGS = [
    "vue_loadprevent_data",
    "vue_dev_info_data",
    "vue_home_device_data",
    "vue_managdiag",
    "vue_net_lua",
    "vue_manage_lua",
    "vue_topo_data",
    "vue_nowversion_lua",
    "vue_internet_eth_data",
    "vue_wifi",
]


def jget(url):
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except Exception as e:
        return {"ok": False, "error": str(e)}


def main():
    deadline = time.time() + 900
    while time.time() < deadline:
        st = jget(BASE + "/api/state")
        if st.get("logged"):
            break
        time.sleep(2)
    else:
        print("timeout: never logged in")
        return
    print("logged in, probing", len(TAGS), "tags")
    out = {}
    for t in TAGS:
        r = jget(BASE + "/api/_tag?tag=" + t)
        keys = r.get("keys") or []
        hit = [k for k in keys if any(s in k.lower() for s in ("cpu", "mem", "ram", "load"))]
        out[t] = {"len": r.get("len"), "hit": hit, "keys": keys[:120],
                  "head": (r.get("head") or "")[:1500], "error": r.get("error")}
        print(t, "len=", r.get("len"), "命中=", hit)
    with open("logs/probe_cpu.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("saved logs/probe_cpu.json")


if __name__ == "__main__":
    main()
