# -*- coding: utf-8 -*-
"""给 panel.py 加 /api/temp：探测机身温度（固件没在网页 UI 暴露，按候选表试，命中后记住）"""
import io

P = "panel.py"
s = io.open(P, encoding="utf-8").read()

ANCHOR = '''def api_device(mac):'''

BLOCK = '''# ---------- 机身温度 / 负载：固件未在网页界面暴露，按候选接口+字段名探测，命中后记住 ----------

TEMP_LOG = os.path.join(BASE_DIR, "logs", "temp.log")

TEMP_SOURCES = [
    ("/?_type=hiddenData&_tag=vue_dev_info_data", "dev_info"),
    ("/?_type=vueData&_tag=vue_dev_info_data", "dev_info.vue"),
    ("/?_type=hiddenData&_tag=vueinfo_data", "vueinfo"),
    ("/?_type=vueData&_tag=vue_dev_status_data", "dev_status"),
    ("/?_type=hiddenData&_tag=vue_managdiagLed_data", "manag_diag"),
    ("/?_type=vueData&_tag=vue_home_device_data", "home"),
    ("/?_type=vueData&_tag=vuecfg_data", "cfg"),
]

TEMP_KEYS = ("temperature", "cputemp", "chiptemp", "boardtemp", "systemp",
             "devtemp", "soc_temp", "temp", "tmp", "temperaturevalue", "cputemperature")
CPU_KEYS = ("cpurate", "cpuusage", "cpuload", "cpuutil", "cpurate", "cpu")
MEM_KEYS = ("memoryrate", "memrate", "memoryusage", "memusage", "memoryutil", "mem")
UP_KEYS = ("runningtime", "uptime", "sysuptime")


def _temp_log(tag, txt):
    try:
        os.makedirs(os.path.dirname(TEMP_LOG), exist_ok=True)
        with open(TEMP_LOG, "a", encoding="utf-8") as f:
            f.write("%s [%s] %s\\n" % (time.strftime("%H:%M:%S"), tag, (txt or "")[:4000]))
    except Exception:
        pass


def _flatten(o, out, prefix=""):
    if isinstance(o, dict):
        for k, v in o.items():
            _flatten(v, out, k)
    elif isinstance(o, list):
        for v in o:
            _flatten(v, out, prefix)
    else:
        if prefix and prefix not in out:
            out[prefix] = "" if o is None else str(o).strip()


def _kv_pairs(text):
    """把 XML（Instance/ParaName 或直接字段）或 JSON 摊平成 {字段名: 值}"""
    out = {}
    for inst in re.findall(r"<Instance>(.*?)</Instance>", text, re.S):
        names = re.findall(r"<ParaName>(.*?)</ParaName>", inst, re.S)
        vals = re.findall(r"<ParaValue>(.*?)</ParaValue>", inst, re.S)
        for k, v in zip(names, vals):
            out.setdefault(k.strip(), html.unescape(v).strip())
    for k, v in re.findall(r"<([A-Za-z0-9_]+)>([^<]*)</\\1>", text, re.S):
        out.setdefault(k, html.unescape(v).strip())
    t = text.lstrip()
    if t.startswith("{") or t.startswith("["):
        try:
            _flatten(json.loads(t), out)
        except Exception:
            pass
    return out


def _pick(d, keys):
    """按字段名（忽略大小写、允许包含）取值"""
    low = {k.lower(): v for k, v in d.items()}
    for k in keys:                       # 先精确
        if k in low and str(low[k]).strip() != "":
            return low[k]
    for k, v in low.items():             # 再模糊（如 CpuTemperatureValue）
        if any(k == x or k.endswith(x) or k.startswith(x) for x in keys):
            if str(v).strip() != "":
                return v
    return None


def _num_or_none(v):
    try:
        f = float(str(v).strip().rstrip("%"))
        return f
    except Exception:
        return None


def api_temp(force=False):
    """返回机身温度与负载。命中一次后记住接口，后续只打那一个请求。"""
    now = time.time()
    cur = S.get("temp") or {}
    if not force and cur.get("at") and now - cur["at"] < (20 if cur.get("c") is not None else 90):
        cur = dict(cur)
        cur["cached"] = True
        return cur

    order = list(TEMP_SOURCES)
    last = cur.get("path")
    if last:
        order.sort(key=lambda x: 0 if x[0] == last else 1)

    tried = []
    hit = None
    for path, name in order:
        try:
            txt = _raw_get(path)
        except Exception as e:
            tried.append({"src": name, "err": "%s: %s" % (type(e).__name__, e)})
            continue
        d = _kv_pairs(txt)
        t = _num_or_none(_pick(d, TEMP_KEYS))
        tried.append({"src": name, "fields": len(d), "keys": ",".join(list(d)[:16])})
        if t is not None and 0 < t < 130:
            hit = (path, name, d, t)
            break
        # 没有温度但拿到了 CPU/内存，先留作兜底
        if d and not hit and (_pick(d, CPU_KEYS) or _pick(d, MEM_KEYS)):
            hit = None

    if not hit:
        # 至少试一次 home，取 CPU/内存（有的固件放在首页对象里）
        out = {"ok": True, "c": None, "src": None, "at": now,
               "reason": "这台固件没有通过网页接口暴露机身温度", "tried": tried}
        S["temp"] = out
        return out

    path, name, d, t = hit
    cpu = _num_or_none(_pick(d, CPU_KEYS))
    mem = _num_or_none(_pick(d, MEM_KEYS))
    up = _pick(d, UP_KEYS)
    out = {
        "ok": True, "c": round(t, 1), "src": name, "path": path, "at": now,
        "cpu": None if cpu is None else int(round(cpu)),
        "mem": None if mem is None else int(round(mem)),
        "uptime": up or "",
        "tried": tried,
    }
    S["temp"] = out
    _temp_log("hit:" + name, "温度=%s 原始片段=%s" % (t, d))
    return out


'''

assert ANCHOR in s
s = s.replace(ANCHOR, BLOCK + ANCHOR, 1)

# 路由
OLD = '''        if p == "/api/limits":
            self._guard(api_limits)
            return'''
NEW = '''        if p == "/api/limits":
            self._guard(api_limits)
            return
        if p == "/api/temp":
            force = (q.get("force") or ["0"])[0] in ("1", "true")
            self._guard(lambda: api_temp(force))
            return'''
assert OLD in s
s = s.replace(OLD, NEW, 1)

io.open(P, "wb").write(s.encode("utf-8"))
print("patched")
