# -*- coding: utf-8 -*-
"""给 ZteClient 增加 防蹭网 / 局域网 / 静态绑定 的实现（与 panel.py 对齐）"""
import io

P = r"C:/Users/Administrator/WorkBuddy/2026-11-14-19-52-51/android-build/app/src/com/xiaoya/zterouter/ZteClient.java"
s = io.open(P, encoding="utf-8").read()

JAVA = r'''    // ================= 防蹭网 / 网络设置 =================
    private static final String[] SEC_MODES = {"密码接入", "授权接入", "白名单接入"};

    private static List<Object> jlist(Object o) {
        List<Object> out = new ArrayList<Object>();
        if (o instanceof List) {
            for (Object x : (List<?>) o) out.add(x);
        }
        return out;
    }

    private static Map<String, Object> jfirst(Map<String, Object> m, String key) {
        Object v = m == null ? null : m.get(key);
        if (v instanceof Map) return asMap(v);
        if (v instanceof List) {
            List<Object> l = jlist(v);
            if (!l.isEmpty()) return asMap(l.get(0));
        }
        return new LinkedHashMap<String, Object>();
    }

    private static int jcode(String txt) {
        try {
            Map<String, Object> m = asMap(MiniJson.parse(txt));
            String c = str(m.get("code"));
            if (c == null || c.trim().isEmpty()) return 0;
            return Integer.parseInt(c.trim());
        } catch (Exception e) {
            return 0;
        }
    }

    private Map<String, Object> jget(String path) throws IOException, NotLogged {
        String txt = fetchText(path);
        try {
            Object o = MiniJson.parse(txt);
            if (o instanceof Map) return asMap(o);
        } catch (Exception ignored) {
        }
        trace("JSON 解析失败 " + path + " head=" + cut(txt, 80));
        return new LinkedHashMap<String, Object>();
    }

    private static String up(String s) {
        return s == null ? "" : s.trim().toUpperCase();
    }

    public synchronized String securityJson() {
        try {
            Map<String, Object> doc = jget("/?_type=vuejsonData&_tag=aclmode_data&_=" + System.currentTimeMillis());
            Map<String, Object> acc = jfirst(doc, "OBJ_ACCESSCONTROL_ID");
            int mode = 0;
            try {
                mode = (int) Math.round(nzNum(str(acc.get("AccControlMode"))));
            } catch (Exception ignored) {
            }
            if (mode < 0 || mode > 2) mode = 0;

            StringBuilder rules = new StringBuilder("[");
            Map<String, Object> rd = jget("/?_type=vuejsonData&_tag=aclrule_data&_=" + System.currentTimeMillis());
            for (Object it : jlist(rd.get("OBJ_ACLCFG_ID"))) {
                Map<String, Object> r = asMap(it);
                String mac = up(str(r.get("MACAddress")));
                if (mac.isEmpty()) continue;
                if (rules.length() > 1) rules.append(',');
                rules.append("{\"inst\":").append(jstr(nz(str(r.get("_InstID")))))
                        .append(",\"mac\":").append(jstr(mac))
                        .append(",\"name\":").append(jstr(pick(nz(str(r.get("DisplayedName"))), nz(str(r.get("Name"))))))
                        .append(",\"policy\":").append(jstr(nz(str(r.get("ACLPolicy"))))).append('}');
            }
            rules.append(']');

            StringBuilder pending = new StringBuilder("[");
            StringBuilder allowed = new StringBuilder("[");
            if (mode == 1) {
                Map<String, Object> ad = jget("/?_type=vuejsonData&_tag=aclauth_stadata&_=" + System.currentTimeMillis());
                for (Object it : jlist(ad.get("OBJ_ACLAUTH_STA"))) {
                    Map<String, Object> a = asMap(it);
                    boolean isPend = "1".equals(nz(str(a.get("AuthMode"))));
                    StringBuilder sb = isPend ? pending : allowed;
                    if (sb.length() > 1) sb.append(',');
                    sb.append("{\"inst\":").append(jstr(nz(str(a.get("_InstID")))))
                            .append(",\"mac\":").append(jstr(up(str(a.get("StaMac")))))
                            .append(",\"name\":").append(jstr(pick(nz(str(a.get("DisplayedName"))), nz(str(a.get("DevName"))))))
                            .append(",\"time\":").append(jstr(nz(str(a.get("ActiveTime"))))).append('}');
                }
            }
            pending.append(']');
            allowed.append(']');

            return "{\"ok\":true,\"mode\":" + mode
                    + ",\"modeName\":" + jstr(SEC_MODES[mode])
                    + ",\"localMac\":" + jstr(up(str(doc.get("LocalMacAddr"))))
                    + ",\"rules\":" + rules
                    + ",\"pending\":" + pending
                    + ",\"allowed\":" + allowed + "}";
        } catch (NotLogged e) {
            return "{\"ok\":false,\"logged\":false,\"error\":\"NOT_LOGGED\"}";
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":" + jstr(msg(e)) + "}";
        }
    }

    public synchronized String securityModeJson(String bodyJson) {
        try {
            Map<String, Object> b = asMap(MiniJson.parse(bodyJson == null ? "{}" : bodyJson));
            int m = (int) Math.round(nzNum(str(b.get("mode"))));
            if (m < 0 || m > 2) return "{\"ok\":false,\"error\":\"模式参数不对\"}";
            LinkedHashMap<String, String> f = new LinkedHashMap<String, String>();
            f.put("IF_ACTION", "Apply");
            f.put("AccControlMode", String.valueOf(m));
            String txt = ax("/?_type=vuejsonData&_tag=aclmode_data", f, 15);
            int code = jcode(txt);
            if (code == 12) {
                return "{\"ok\":false,\"code\":12,\"needConfirm\":true,"
                        + "\"error\":\"还有设备不在白名单里，切换后会立刻断网\"}";
            }
            if (code != 0) {
                trace("setmode " + code + " " + cut(txt, 120));
                return "{\"ok\":false,\"code\":" + code + ",\"error\":\"路由器拒绝（code " + code + "）\"}";
            }
            return "{\"ok\":true,\"mode\":" + m + ",\"modeName\":" + jstr(SEC_MODES[m]) + "}";
        } catch (NotLogged e) {
            return "{\"ok\":false,\"logged\":false,\"error\":\"NOT_LOGGED\"}";
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":" + jstr(msg(e)) + "}";
        }
    }

    public synchronized String aclJson(String bodyJson) {
        try {
            Map<String, Object> b = asMap(MiniJson.parse(bodyJson == null ? "{}" : bodyJson));
            String inst = nz(str(b.get("inst")));
            String op = nz(str(b.get("op")));
            LinkedHashMap<String, String> f = new LinkedHashMap<String, String>();
            if ("del".equals(op)) {
                if (inst.isEmpty()) return "{\"ok\":false,\"error\":\"缺少规则实例\"}";
                f.put("IF_ACTION", "Delete");
                f.put("_InstID", inst);
            } else {
                String mac = up(str(b.get("mac")));
                if (!mac.matches("^([0-9A-F]{2}:){5}[0-9A-F]{2}$")) {
                    return "{\"ok\":false,\"error\":\"MAC 地址格式不对\"}";
                }
                String policy = "allow".equalsIgnoreCase(nz(str(b.get("policy")))) ? "Allow" : "Ban";
                f.put("_InstID", "-1");
                f.put("IF_ACTION", "Apply");
                f.put("ACLPolicy", policy);
                String nm = nz(str(b.get("name")));
                f.put("Name", nm.isEmpty() ? mac : (nm.length() > 64 ? nm.substring(0, 64) : nm));
                f.put("MACAddress", mac);
                f.put("Interface", "DEV.WIFI.AP1");
                if ("Ban".equals(policy)) f.put("ACTION_TYPE", "DELAUTH");
            }
            String txt = ax("/?_type=vuejsonData&_tag=aclrule_data", f, 15);
            int code = jcode(txt);
            if (code != 0) {
                trace("acl " + code + " " + cut(txt, 120));
                return "{\"ok\":false,\"code\":" + code + ",\"error\":\"路由器拒绝（code " + code + "）\"}";
            }
            return "{\"ok\":true}";
        } catch (NotLogged e) {
            return "{\"ok\":false,\"logged\":false,\"error\":\"NOT_LOGGED\"}";
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":" + jstr(msg(e)) + "}";
        }
    }

    public synchronized String securityAuthJson(String bodyJson) {
        try {
            Map<String, Object> b = asMap(MiniJson.parse(bodyJson == null ? "{}" : bodyJson));
            String inst = nz(str(b.get("inst")));
            int act = (int) Math.round(nzNum(str(b.get("action"))));
            if (inst.isEmpty() || act < 1 || act > 3) return "{\"ok\":false,\"error\":\"参数不对\"}";
            LinkedHashMap<String, String> f = new LinkedHashMap<String, String>();
            f.put("_InstID", inst);
            f.put("IF_ACTION", "Apply");
            f.put("AuthAction", String.valueOf(act));
            String txt = ax("/?_type=vuejsonData&_tag=aclauth_stadata", f, 15);
            int code = jcode(txt);
            if (code != 0) {
                trace("auth " + code + " " + cut(txt, 120));
                return "{\"ok\":false,\"code\":" + code + ",\"error\":\"路由器拒绝（code " + code + "）\"}";
            }
            return "{\"ok\":true}";
        } catch (NotLogged e) {
            return "{\"ok\":false,\"logged\":false,\"error\":\"NOT_LOGGED\"}";
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":" + jstr(msg(e)) + "}";
        }
    }

    public synchronized String lanJson() {
        try {
            String txt = fetchText("/?_type=vueData&_tag=addr_manager_data&_=" + System.currentTimeMillis());
            Map<String, List<Map<String, String>>> g = groups(txt);
            Map<String, String> br = first(g, "OBJ_BRGRP_ID");
            Map<String, String> dh = first(g, "OBJ_DHCPHOST_ID");
            Map<String, String> bd = first(g, "OBJ_DHCP4SBRIDGE_ID");
            if (br.isEmpty() && dh.isEmpty()) {
                trace("局域网读取失败 " + cut(txt, 160));
                return "{\"ok\":false,\"error\":\"读不到局域网配置\"}";
            }
            StringBuilder binds = new StringBuilder("[");
            try {
                String bt = fetchText("/?_type=vueData&_tag=static_bindAddr_data&_=" + System.currentTimeMillis());
                for (Map<String, String> b : list(groups(bt), "OBJ_DHCPBIND_ID")) {
                    String mac = up(b.get("MACAddr"));
                    if (mac.isEmpty()) continue;
                    if (binds.length() > 1) binds.append(',');
                    binds.append("{\"inst\":").append(jstr(nz(b.get("_InstID"))))
                            .append(",\"name\":").append(jstr(nz(b.get("Name"))))
                            .append(",\"ip\":").append(jstr(nz(b.get("IPAddr"))))
                            .append(",\"mac\":").append(jstr(mac)).append('}');
                }
            } catch (Exception ignored) {
            }
            binds.append(']');
            String lease = nz(dh.get("LeaseTime"));
            boolean on = "1".equals(nz(dh.get("ServerEnable"))) || "1".equals(nz(bd.get("Dhcp4sBridgePolicyEnable")));
            return "{\"ok\":true,\"ip\":" + jstr(pick(nz(br.get("IPAddr")), nz(dh.get("IPRouters"))))
                    + ",\"mask\":" + jstr(nz(br.get("SubMask")))
                    + ",\"dhcpOn\":" + on
                    + ",\"gateway\":" + jstr(pick(nz(dh.get("IPRouters")), nz(br.get("IPAddr"))))
                    + ",\"min\":" + jstr(nz(dh.get("MinAddress")))
                    + ",\"max\":" + jstr(nz(dh.get("MaxAddress")))
                    + ",\"dns1\":" + jstr(nz(dh.get("DNSServer1")))
                    + ",\"dns2\":" + jstr(nz(dh.get("DNSServer2")))
                    + ",\"lease\":" + jstr(lease)
                    + ",\"leaseForever\":" + "-1".equals(lease)
                    + ",\"binds\":" + binds + "}";
        } catch (NotLogged e) {
            return "{\"ok\":false,\"logged\":false,\"error\":\"NOT_LOGGED\"}";
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":" + jstr(msg(e)) + "}";
        }
    }

    public synchronized String lanSetJson(String bodyJson) {
        try {
            Map<String, Object> b = asMap(MiniJson.parse(bodyJson == null ? "{}" : bodyJson));
            Map<String, Object> cur = asMap(MiniJson.parse(lanJson()));
            if (!Boolean.TRUE.equals(cur.get("ok"))) {
                return "{\"ok\":false,\"error\":" + jstr(nz(str(cur.get("error")))) + "}";
            }
            String ip = bodyOr(b, "ip", str(cur.get("ip")));
            String mask = bodyOr(b, "mask", str(cur.get("mask")));
            String lease = bodyOr(b, "lease", str(cur.get("lease")));
            if (!lease.isEmpty() && !lease.matches("^-?\\d+$")) {
                return "{\"ok\":false,\"error\":\"租期要填分钟数，或 -1 表示永久\"}";
            }
            LinkedHashMap<String, String> f = new LinkedHashMap<String, String>();
            f.put("_InstID_BRGRP", "IGD.LD1");
            f.put("DHCPBasic", "Both");
            f.put("IPAddr", ip);
            f.put("SubMask", mask);
            f.put("SubnetMask", mask);
            f.put("IPRouters", bodyOr(b, "gateway", pick(str(cur.get("gateway")), ip)));
            f.put("MinAddress", bodyOr(b, "min", str(cur.get("min"))));
            f.put("MaxAddress", bodyOr(b, "max", str(cur.get("max"))));
            f.put("DNSServer1", bodyOr(b, "dns1", str(cur.get("dns1"))));
            f.put("DNSServer2", bodyOr(b, "dns2", str(cur.get("dns2"))));
            f.put("LeaseTime", lease.isEmpty() ? "120" : lease);
            f.put("IF_ACTION", "Apply");
            f.put("Dhcp4sBridgePolicyEnable", Boolean.FALSE.equals(b.get("dhcpOn")) ? "0" : "1");
            String txt = ax("/?_type=vueData&_tag=addr_manager_data", f, 20);
            String es = nz(xmlField(txt, "IF_ERRORSTR"));
            if (!es.toUpperCase().startsWith("SUCC")) {
                trace("setlan " + cut(txt, 160));
                return "{\"ok\":false,\"error\":" + jstr(es.isEmpty() ? "路由器拒绝了这次修改" : es) + "}";
            }
            return "{\"ok\":true,\"ip\":" + jstr(ip) + ",\"mask\":" + jstr(mask)
                    + ",\"needRelogin\":" + (!ip.equals(str(cur.get("ip")))) + "}";
        } catch (NotLogged e) {
            return "{\"ok\":false,\"logged\":false,\"error\":\"NOT_LOGGED\"}";
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":" + jstr(msg(e)) + "}";
        }
    }

    public synchronized String bindJson(String bodyJson) {
        try {
            Map<String, Object> b = asMap(MiniJson.parse(bodyJson == null ? "{}" : bodyJson));
            String op = nz(str(b.get("op")));
            LinkedHashMap<String, String> f = new LinkedHashMap<String, String>();
            if ("del".equals(op)) {
                String inst = nz(str(b.get("inst")));
                if (inst.isEmpty()) return "{\"ok\":false,\"error\":\"缺少绑定实例\"}";
                f.put("IF_ACTION", "Delete");
                f.put("_InstID", inst);
                f.put("Name", nz(str(b.get("name"))));
                f.put("IPAddr", nz(str(b.get("ip"))));
                f.put("MACAddr", nz(str(b.get("mac"))));
                f.put("IPRouters", nz(str(b.get("gateway"))));
            } else {
                String mac = up(str(b.get("mac")));
                String ip = nz(str(b.get("ip"))).trim();
                if (!mac.matches("^([0-9A-F]{2}:){5}[0-9A-F]{2}$")) {
                    return "{\"ok\":false,\"error\":\"MAC 地址格式不对\"}";
                }
                if (!ip.matches("^\\d{1,3}(\\.\\d{1,3}){3}$")) {
                    return "{\"ok\":false,\"error\":\"IP 地址格式不对\"}";
                }
                String nm = nz(str(b.get("name")));
                String gw = "";
                try {
                    Map<String, Object> cur = asMap(MiniJson.parse(lanJson()));
                    gw = nz(str(cur.get("gateway")));
                } catch (Exception ignored) {
                }
                f.put("IF_ACTION", "Apply");
                f.put("_InstID", "-1");
                f.put("Name", nm.isEmpty() ? mac : (nm.length() > 64 ? nm.substring(0, 64) : nm));
                f.put("IPAddr", ip);
                f.put("MACAddr", mac);
                f.put("IPRouters", gw);
            }
            String txt = ax("/?_type=vueData&_tag=static_bindAddr_data", f, 15);
            String es = nz(xmlField(txt, "IF_ERRORSTR"));
            if (!es.toUpperCase().startsWith("SUCC")) {
                trace("bind " + cut(txt, 160));
                return "{\"ok\":false,\"error\":" + jstr(es.isEmpty() ? "路由器拒绝了这次操作" : es) + "}";
            }
            return "{\"ok\":true}";
        } catch (NotLogged e) {
            return "{\"ok\":false,\"logged\":false,\"error\":\"NOT_LOGGED\"}";
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":" + jstr(msg(e)) + "}";
        }
    }

    private static String bodyOr(Map<String, Object> b, String key, String fallback) {
        Object v = b == null ? null : b.get(key);
        if (v == null) return fallback == null ? "" : fallback;
        String s = String.valueOf(v).trim();
        return s.isEmpty() ? (fallback == null ? "" : fallback) : s;
    }

'''

anchor = "    private String ax(String path, LinkedHashMap<String, String> form, int timeoutSec)"
assert anchor in s
s = s.replace(anchor, JAVA + anchor, 1)

io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok", len(s))
