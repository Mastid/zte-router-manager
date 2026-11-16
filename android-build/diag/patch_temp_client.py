# -*- coding: utf-8 -*-
"""ZteClient 加 tempJson()，MainActivity 加分发，make_assets 加映射"""
import io

# ---------- ZteClient ----------
P = "app/src/com/xiaoya/zterouter/ZteClient.java"
s = io.open(P, encoding="utf-8").read()

ANCHOR = "    public synchronized String limitsJson() {"

BLOCK = '''    // ---------- 机身温度 / 负载（固件未在网页界面暴露，按候选接口+字段名探测） ----------
    private static final String[] TEMP_SRC = {
            "/?_type=hiddenData&_tag=vue_dev_info_data",
            "/?_type=vueData&_tag=vue_dev_info_data",
            "/?_type=hiddenData&_tag=vueinfo_data",
            "/?_type=vueData&_tag=vue_dev_status_data",
            "/?_type=hiddenData&_tag=vue_managdiagLed_data",
            "/?_type=vueData&_tag=vue_home_device_data",
            "/?_type=vueData&_tag=vuecfg_data",
    };
    private static final String[] TEMP_KEYS = {"temperature", "cputemp", "chiptemp", "boardtemp",
            "systemp", "devtemp", "soc_temp", "temp", "tmp", "temperaturevalue", "cputemperature"};
    private static final String[] CPU_KEYS = {"cpurate", "cpuusage", "cpuload", "cpuutil", "cpu"};
    private static final String[] MEM_KEYS = {"memoryrate", "memrate", "memoryusage", "memusage", "memoryutil", "mem"};

    /** 把 XML 摊平成 {字段: 值}：兼容 Instance/ParaName 与直接字段两种写法 */
    private static Map<String, String> flatKv(String xml) {
        Map<String, String> out = new LinkedHashMap<String, String>();
        Matcher im = Pattern.compile("<Instance>(.*?)</Instance>", Pattern.DOTALL).matcher(xml);
        while (im.find()) {
            List<String> names = findAll(im.group(1), "<ParaName>(.*?)</ParaName>");
            List<String> vals = findAll(im.group(1), "<ParaValue>(.*?)</ParaValue>");
            for (int i = 0; i < names.size() && i < vals.size(); i++) {
                String k = names.get(i).trim();
                if (!out.containsKey(k)) out.put(k, unescape(vals.get(i)).trim());
            }
        }
        Matcher fm = Pattern.compile("<([A-Za-z0-9_]+)>([^<]*)</\\\\1>", Pattern.DOTALL).matcher(xml);
        while (fm.find()) {
            String k = fm.group(1);
            if (!out.containsKey(k)) out.put(k, unescape(fm.group(2)).trim());
        }
        return out;
    }

    private static String pickStr(Map<String, String> d, String[] keys) {
        Map<String, String> low = new LinkedHashMap<String, String>();
        for (Map.Entry<String, String> e : d.entrySet()) low.put(e.getKey().toLowerCase(), e.getValue());
        for (String k : keys) {
            String v = low.get(k);
            if (v != null && v.length() > 0) return v;
        }
        for (Map.Entry<String, String> e : low.entrySet()) {
            for (String k : keys) {
                if (e.getKey().startsWith(k) || e.getKey().endsWith(k)) {
                    if (e.getValue() != null && e.getValue().length() > 0) return e.getValue();
                }
            }
        }
        return null;
    }

    private static Double pickNum(Map<String, String> d, String[] keys) {
        String v = pickStr(d, keys);
        if (v == null) return null;
        try {
            return Double.valueOf(v.replace("%", "").trim());
        } catch (Exception e) {
            return null;
        }
    }

    private static String numOrNull(Double v) {
        if (v == null) return "null";
        return String.valueOf((long) Math.round(v.doubleValue()));
    }

    public synchronized String tempJson() {
        ensure();
        StringBuilder tried = new StringBuilder();
        String lastErr = null;
        for (String path : TEMP_SRC) {
            try {
                Resp r = req(path, null, 12);
                if (r.status != 200 || r.body == null || dead(r.body)) continue;
                Map<String, String> d = flatKv(r.body);
                Double t = pickNum(d, TEMP_KEYS);
                if (t != null && t.doubleValue() > 0 && t.doubleValue() < 130) {
                    return "{\\"ok\\":true,\\"c\\":" + String.format(Locale.US, "%.1f", t)
                            + ",\\"cpu\\":" + numOrNull(pickNum(d, CPU_KEYS))
                            + ",\\"mem\\":" + numOrNull(pickNum(d, MEM_KEYS))
                            + ",\\"uptime\\":" + jstr(pickStr(d, new String[]{"runningtime", "uptime", "sysuptime"}))
                            + ",\\"src\\":" + jstr(path) + "}";
                }
                if (tried.length() > 0) tried.append(',');
                tried.append("{\\"src\\":").append(jstr(path)).append(",\\"fields\\":").append(d.size()).append('}');
            } catch (NotLogged e) {
                return "{\\"ok\\":false,\\"logged\\":false,\\"error\\":\\"NOT_LOGGED\\"}";
            } catch (Exception e) {
                lastErr = msg(e);
            }
        }
        return "{\\"ok\\":true,\\"c\\":null,\\"reason\\":\\"这台固件没有通过网页接口暴露机身温度\\""
                + ",\\"error\\":" + jstr(lastErr) + ",\\"tried\\":[" + tried + "]}";
    }

'''

assert ANCHOR in s
s = s.replace(ANCHOR, BLOCK + ANCHOR, 1)

if "import java.util.Locale;" not in s:
    s = s.replace("import java.util.List;", "import java.util.List;\nimport java.util.Locale;", 1)

io.open(P, "wb").write(s.encode("utf-8"))
print("client ok")

# ---------- MainActivity ----------
P2 = "app/src/com/xiaoya/zterouter/MainActivity.java"
a = io.open(P2, encoding="utf-8").read()
OLD = '            if ("bind".equals(method)) return client.bindJson(arg);'
NEW = OLD + '\n            if ("temp".equals(method)) return client.tempJson();'
assert OLD in a
a = a.replace(OLD, NEW, 1)
io.open(P2, "wb").write(a.encode("utf-8"))
print("activity ok")

# ---------- make_assets ----------
P3 = "make_assets.py"
m = io.open(P3, encoding="utf-8").read()
OLD3 = "    else if (path === '/api/limits') raw = await zcall('limits');"
NEW3 = OLD3 + "\n    else if (path.indexOf('/api/temp') === 0) raw = await zcall('temp');"
assert OLD3 in m
m = m.replace(OLD3, NEW3, 1)
io.open(P3, "wb").write(m.encode("utf-8"))
print("assets ok")
