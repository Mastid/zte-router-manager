# -*- coding: utf-8 -*-
"""给 ZteClient 增加：设备详情（实时速率）、限速查询、限速设置"""
import io

P = "app/src/com/xiaoya/zterouter/ZteClient.java"
s = io.open(P, encoding="utf-8").read()
if "public synchronized String deviceJson(" in s:
    print("already patched")
    raise SystemExit

BLOCK = '''    // ---------------- 终端详情 / 限速 ----------------

    private String fetchText(String path) throws IOException, NotLogged {
        ensure();
        Resp r = req(path, null, 15);
        if (dead(r.body)) {
            trace("读数据被拒 " + path + " status=" + r.status);
            logged = false;
            pwdCache.clear();
            if (!relogin()) throw new NotLogged();
            r = req(path, null, 15);
            if (dead(r.body)) {
                logged = false;
                throw new NotLogged();
            }
        }
        return r.body == null ? "" : r.body;
    }

    private static double nzNum(String s) {
        try {
            return Double.parseDouble((s == null ? "" : s.trim()).replace(",", ""));
        } catch (Exception e) {
            return 0;
        }
    }

    private static boolean succ(String txt) {
        String e = xmlField(txt, "IF_ERRORSTR");
        return e != null && e.toUpperCase().startsWith("SUCC");
    }

    /** 单设备详情：实时上下行（Kbps）+ 累计流量（Byte）+ 在线时长（秒） */
    public synchronized String deviceJson(String mac) {
        String m = mac == null ? "" : mac.trim().toUpperCase();
        if (m.isEmpty()) return "{\\"ok\\":false,\\"error\\":\\"缺少 MAC 地址\\"}";
        try {
            String txt = fetchText("/?_type=vueData&_tag=localnet_lan_detailinfo_lua_no_update_sess&MACAddress="
                    + enc(m) + "&_=" + System.currentTimeMillis());
            Map<String, String> d = first(groups(txt), "OBJ_LANINFO_BYMAC");
            if (d.isEmpty()) {
                trace("设备详情解析失败 " + cut(txt, 160));
                return "{\\"ok\\":false,\\"error\\":\\"设备详情解析失败\\",\\"raw\\":" + jstr(cut(txt, 200)) + "}";
            }
            return "{\\"ok\\":true,\\"mac\\":" + jstr(m)
                    + ",\\"ip\\":" + jstr(pick(d.get("IPAddress"), d.get("IPv4Addr")))
                    + ",\\"up\\":" + Math.round(nzNum(d.get("UploadSpeed")))
                    + ",\\"down\\":" + Math.round(nzNum(d.get("DownloadSpeed")))
                    + ",\\"rx\\":" + Math.round(nzNum(d.get("BytesReceived")))
                    + ",\\"tx\\":" + Math.round(nzNum(d.get("BytesSent")))
                    + ",\\"online\\":" + Math.round(nzNum(d.get("OnlineTimes")))
                    + ",\\"active\\":" + ("1".equals(pick(d.get("Active"), "1")))
                    + ",\\"type\\":" + jstr(nz(d.get("DisplayedType")))
                    + ",\\"vendor\\":" + jstr(nz(d.get("DisplayedVendor")))
                    + ",\\"ts\\":" + (System.currentTimeMillis() / 1000) + "}";
        } catch (NotLogged e) {
            return "{\\"ok\\":false,\\"logged\\":false,\\"error\\":\\"NOT_LOGGED\\"}";
        } catch (Exception e) {
            return "{\\"ok\\":false,\\"error\\":" + jstr(msg(e)) + "}";
        }
    }

    /** 全部限速规则 + 全局 QoS 开关（对外单位 Mbps） */
    public synchronized String limitsJson() {
        try {
            Map<String, List<Map<String, String>>> g = groups(
                    fetchText("/?_type=vueData&_tag=localnet_qosdyn_lua&_=" + System.currentTimeMillis()));
            Map<String, String> glob = first(g, "OBJ_QOSDYN_ID");
            boolean enable = "1".equals(nz(glob.get("Enable")));
            StringBuilder rules = new StringBuilder("{");
            int n = 0;
            for (Map<String, String> r : list(g, "OBJ_QOS_BCRULE_ID")) {
                String mac = nz(r.get("MACDev")).trim().toUpperCase();
                if (mac.isEmpty()) continue;
                if (n++ > 0) rules.append(',');
                rules.append(jstr(mac)).append(":{\\"i\\":").append(jstr(nz(r.get("_InstID"))))
                        .append(",\\"u\\":").append(Math.round(nzNum(r.get("BandwithRateMaxUp")) / 1000.0))
                        .append(",\\"d\\":").append(Math.round(nzNum(r.get("BandwithRateMaxDown")) / 1000.0))
                        .append('}');
            }
            rules.append('}');
            return "{\\"ok\\":true,\\"enable\\":" + enable + ",\\"rules\\":" + rules + "}";
        } catch (NotLogged e) {
            return "{\\"ok\\":false,\\"logged\\":false,\\"error\\":\\"NOT_LOGGED\\"}";
        } catch (Exception e) {
            return "{\\"ok\\":false,\\"error\\":" + jstr(msg(e)) + "}";
        }
    }

    private String ruleInst(String mac) {
        try {
            Map<String, Object> o = asMap(MiniJson.parse(
                    fetchText("/?_type=vuejsonData&_tag=localnet_qosdyn_rulebymac&_InstID=" + enc(mac))));
            Object arr = o.get("OBJ_QOS_BCRULE_BYMAC");
            if (arr instanceof List) {
                List<?> l = (List<?>) arr;
                if (!l.isEmpty()) {
                    String vn = nz(str(asMap(l.get(0)).get("ViewName"))).trim();
                    if (!vn.isEmpty()) return vn;
                }
            }
        } catch (Exception ignored) {
        }
        return null;
    }

    /** 设置限速：{"mac":"..","up":Mbps,"down":Mbps}，两者都为 0 = 取消限速 */
    public synchronized String setLimitJson(String bodyJson) {
        String mac;
        long up, down;
        try {
            Map<String, Object> o = asMap(MiniJson.parse(bodyJson));
            mac = nz(str(o.get("mac"))).trim().toUpperCase();
            up = Math.max(0, Math.round(num(o.get("up"))));
            down = Math.max(0, Math.round(num(o.get("down"))));
        } catch (Exception e) {
            return "{\\"ok\\":false,\\"error\\":\\"参数错误\\"}";
        }
        if (mac.isEmpty()) return "{\\"ok\\":false,\\"error\\":\\"缺少 MAC 地址\\"}";
        String path = "/?_type=vueData&_tag=localnet_qosdyn_bandwithrule_lua";
        try {
            String inst = ruleInst(mac);
            String txt;
            if (up == 0 && down == 0) {
                if (inst == null) return "{\\"ok\\":true,\\"cleared\\":true}";
                LinkedHashMap<String, String> f = new LinkedHashMap<String, String>();
                f.put("IF_ACTION", "Delete");
                f.put("_InstID", inst);
                txt = ax(path, f, 15);
                boolean ok = succ(txt);
                if (!ok) trace("取消限速失败 " + cut(txt, 200));
                return "{\\"ok\\":" + ok + ",\\"cleared\\":true,\\"error\\":"
                        + (ok ? "null" : jstr(pick(xmlField(txt, "IF_ERRORSTR"), "路由器拒绝了这次修改"))) + "}";
            }
            LinkedHashMap<String, String> f = new LinkedHashMap<String, String>();
            f.put("MACDev", mac);
            f.put("BandwithRateMaxUp", String.valueOf(up * 1000));
            f.put("BandwithRateMaxDown", String.valueOf(down * 1000));
            f.put("UserName", mac);
            f.put("IF_ACTION", "Apply");
            f.put("_InstID", inst == null ? "-1" : inst);
            txt = ax(path, f, 15);
            boolean ok = succ(txt);
            if (!ok) trace("设置限速失败 " + cut(txt, 200));
            return "{\\"ok\\":" + ok + ",\\"up\\":" + up + ",\\"down\\":" + down
                    + ",\\"inst\\":" + jstr(inst == null ? "-1" : inst)
                    + ",\\"error\\":" + (ok ? "null" : jstr(pick(xmlField(txt, "IF_ERRORSTR"), "路由器拒绝了这次修改")))
                    + "}";
        } catch (NotLogged e) {
            return "{\\"ok\\":false,\\"logged\\":false,\\"error\\":\\"NOT_LOGGED\\"}";
        } catch (Exception e) {
            return "{\\"ok\\":false,\\"error\\":" + jstr(msg(e)) + "}";
        }
    }

'''

anchor = "    private String apiAll() throws IOException, NotLogged {"
assert anchor in s
s = s.replace(anchor, BLOCK + anchor, 1)

io.open(P, "wb").write(s.encode("utf-8"))
print("patched ZteClient", len(s))
