import com.xiaoya.zterouter.ZteClient;

import java.io.BufferedReader;
import java.io.Console;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 桌面对照测试：
 *   java ZteTest offline <抓包目录>      —— 离线校验加解密与 XML 解析（不需要密码）
 *   java ZteTest live                    —— 真机全流程（会提示输入管理员密码）
 */
public class ZteTest {

    static StringWriter LOG = new StringWriter();
    static PrintWriter out = new PrintWriter(LOG, true);

    public static void main(String[] args) throws Exception {
        String mode = args.length > 0 ? args[0] : "offline";
        int code = 0;
        try {
            if ("offline".equals(mode)) {
                offline(args.length > 1 ? args[1] : ".");
            } else if ("probe".equals(mode)) {
                probe();
            } else {
                live();
            }
        } catch (Throwable t) {
            code = 1;
            out.println("异常: " + t);
            t.printStackTrace(out);
        }
        out.flush();
        String text = LOG.toString();
        System.out.println(text);
        try {
            PrintWriter f = new PrintWriter(new File("test-result.txt"), "UTF-8");
            f.print(text);
            f.close();
        } catch (Exception e) {
            System.out.println("写结果文件失败: " + e);
        }
        System.exit(code);
    }

    // ---------------- 离线校验 ----------------

    static void offline(String labDir) throws Exception {
        out.println("=== 1. 用真实抓包校验 AES/RSA ===");
        File cap = new File(labDir, "logs/capture.jsonl");
        if (!cap.exists()) {
            out.println("找不到抓包文件: " + cap.getAbsolutePath());
        } else {
            String body = readFile(cap);
            String line = null;
            for (String l : body.split("\n")) {
                if (l.contains("wifi_advancedssid_data")) line = l;
            }
            if (line == null) {
                out.println("抓包里没有 wifi_advancedssid_data");
            } else {
                @SuppressWarnings("unchecked")
                Map<String, Object> row = (Map<String, Object>) ZteClient.MiniJson.parse(line);
                String reqBody = String.valueOf(row.get("req_body"));
                LinkedHashMap<String, String> kv = parseForm(reqBody);
                String tok = kv.get("_sessionTOKEN");
                out.println("token 长度: " + (tok == null ? 0 : tok.length()));
                String p1 = ZteClient.decPara(kv.get("KeyPassphrase1"), tok, rev(tok));
                String p5 = ZteClient.decPara(kv.get("KeyPassphrase5"), tok, rev(tok));
                out.println("2.4G 解出长度: " + p1.length() + "  指纹: " + sig(p1));
                out.println("5G   解出长度: " + p5.length() + "  指纹: " + sig(p5));
                out.println("两频段一致: " + p1.equals(p5));
                out.println("纯可打印 ASCII: " + (p1.equals(asciiOnly(p1)) && p5.equals(asciiOnly(p5))));
                boolean rt1 = ZteClient.encPara(p1, tok, rev(tok)).equals(kv.get("KeyPassphrase1"));
                boolean rt5 = ZteClient.encPara(p5, tok, rev(tok)).equals(kv.get("KeyPassphrase5"));
                out.println("重加密与原文一致(2.4G/5G): " + rt1 + " / " + rt5);
                String ek = ZteClient.encKey("1234567890123456", "9876543210987654");
                out.println("RSA encode 长度: " + ZteClient.b64d(ek).length + " 字节（2048 位应为 256）");
            }
        }

        out.println();
        out.println("=== 2. XML 解析（用采集到的真实返回） ===");
        File wifi = new File(labDir, "logs/snapshot2/wifiAP_data.txt");
        File client = new File(labDir, "logs/snapshot2/vue_client_data.txt");
        if (wifi.exists()) {
            Map<String, List<Map<String, String>>> g = ZteClient.groups(readFile(wifi));
            out.println("wifiAP 分组: " + g.keySet());
            List<Map<String, String>> aps = g.get("OBJ_WLANAP_ID");
            out.println("AP 数量: " + (aps == null ? 0 : aps.size()));
            if (aps != null) {
                for (Map<String, String> a : aps) {
                    out.println("  " + a.get("_InstID") + " ESSID=" + a.get("ESSID")
                            + " Enable=" + a.get("Enable") + " Beacon=" + a.get("BeaconType"));
                }
            }
            List<Map<String, String>> psks = g.get("OBJ_WLANPSK_ID");
            out.println("PSK 实例: " + (psks == null ? 0 : psks.size()));
            if (psks != null) {
                for (Map<String, String> p : psks) {
                    out.println("  " + p.get("_InstID_PSK") + " 密文长度=" + len(p.get("KeyPassphrase")));
                }
            }
        } else {
            out.println("缺少 " + wifi.getAbsolutePath());
        }
        if (client.exists()) {
            Map<String, List<Map<String, String>>> g = ZteClient.groups(readFile(client));
            List<Map<String, String>> cs = g.get("OBJ_CLIENTS_ID");
            out.println("客户端数量: " + (cs == null ? 0 : cs.size()));
            if (cs != null && !cs.isEmpty()) {
                Map<String, String> c = cs.get(0);
                out.println("  示例: " + c.get("HostName") + " / " + c.get("IPAddress")
                        + " / " + c.get("MACAddress") + " / " + c.get("InterfaceType"));
            }
        }

        out.println();
        out.println("=== 3. JSON 解析（表单入参） ===");
        Object o = ZteClient.MiniJson.parse("{\"5G\":{\"ssid\":\"a b\",\"pwd\":\"p@ss\",\"on\":true}}");
        out.println("解析结果: " + o);
        out.println("SHA256 空串: " + ZteClient.sha256Hex(""));
        out.println("SHA256 abc : " + ZteClient.sha256Hex("abc"));
    }

    // ---------------- 连通性 ----------------

    static void probe() throws Exception {
        out.println("=== 连通性自检（不登录） ===");
        ZteClient c = new ZteClient(System.getProperty("zte.host", "192.168.5.1"));
        out.println(c.probeJson());
    }

    // ---------------- 联网全流程 ----------------

    static void live() throws Exception {
        String pwd = ask("请输入路由器管理员密码（输入不回显）: ");
        if (pwd == null || pwd.isEmpty()) {
            out.println("未输入密码，退出");
            return;
        }
        ZteClient c = new ZteClient(System.getProperty("zte.host", "192.168.5.1"));
        out.println("=== 1. 登录 ===");
        long t0 = System.currentTimeMillis();
        String r = c.loginJson(pwd);
        out.println("结果: " + r + "  耗时 " + (System.currentTimeMillis() - t0) + "ms");
        if (r.contains("\"ok\":false")) return;

        out.println();
        out.println("=== 2. 读取概览 ===");
        String all = c.allJson();
        out.println(trim(all, 900));

        out.println();
        out.println("=== 3. 读 WiFi 密码（两频段） ===");
        String a1 = c.wifiPwdJson("2.4G");
        String a5 = c.wifiPwdJson("5G");
        String p1 = jget(a1, "pwd");
        String p5 = jget(a5, "pwd");
        out.println("2.4G: 长度=" + p1.length() + " 指纹=" + sig(p1) + " 错误=" + jget(a1, "error"));
        out.println("5G  : 长度=" + p5.length() + " 指纹=" + sig(p5) + " 错误=" + jget(a5, "error"));
        out.println("连续两次一致: " + p1.equals(jget(c.wifiPwdJson("2.4G"), "pwd")));

        out.println();
        out.println("=== 4. 原值回填空保存（会短暂重启无线，约 10 秒） ===");
        long t1 = System.currentTimeMillis();
        String save = c.saveWifiJson("{}");
        out.println("结果: " + save + "  耗时 " + (System.currentTimeMillis() - t1) + "ms");

        out.println();
        out.println("=== 5. 保存后复核 ===");
        Thread.sleep(12000);
        String all2 = c.allJson();
        out.println(trim(all2, 900));
        out.println("2.4G 密码指纹是否不变: " + sig(jget(c.wifiPwdJson("2.4G"), "pwd")).equals(sig(p1)));
        out.println("5G   密码指纹是否不变: " + sig(jget(c.wifiPwdJson("5G"), "pwd")).equals(sig(p5)));

        out.println();
        out.println("=== 6. 重启接口（不发真实重启，只检查会否被拒） ===");
        out.println("跳过：避免再次断网，App 内可手动触发");
        out.println();
        out.println("全部完成");
    }

    // ---------------- 工具 ----------------

    static String ask(String prompt) {
        Console con = System.console();
        if (con != null) {
            char[] p = con.readPassword(prompt);
            return p == null ? null : new String(p);
        }
        System.out.print(prompt);
        try {
            BufferedReader br = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
            return br.readLine();
        } catch (Exception e) {
            return null;
        }
    }

    static String readFile(File f) throws Exception {
        FileInputStream in = new FileInputStream(f);
        byte[] b = new byte[(int) f.length()];
        int off = 0, n;
        while ((n = in.read(b, off, b.length - off)) > 0) off += n;
        in.close();
        return new String(b, 0, off, StandardCharsets.UTF_8);
    }

    static String field(String jsonLine, String key) {
        Matcher m = Pattern.compile("\"" + key + "\":\\s*\"((?:\\\\.|[^\"\\\\])*)\"").matcher(jsonLine);
        if (!m.find()) return "";
        return m.group(1).replace("\\\"", "\"").replace("\\n", "\n").replace("\\r", "\r")
                .replace("\\t", "\t").replace("\\\\", "\\");
    }

    static LinkedHashMap<String, String> parseForm(String s) throws Exception {
        LinkedHashMap<String, String> m = new LinkedHashMap<String, String>();
        if (s == null || s.isEmpty()) return m;
        for (String kv : s.split("&")) {
            int i = kv.indexOf('=');
            if (i < 0) continue;
            m.put(URLDecoder.decode(kv.substring(0, i), "UTF-8"),
                    URLDecoder.decode(kv.substring(i + 1), "UTF-8"));
        }
        return m;
    }

    static String rev(String s) {
        return new StringBuilder(s).reverse().toString();
    }

    static String sig(String s) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        byte[] d = md.digest(s.getBytes(StandardCharsets.UTF_8));
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 5; i++) sb.append(String.format("%02x", d[i]));
        return sb.toString();
    }

    static String asciiOnly(String s) {
        StringBuilder sb = new StringBuilder();
        for (char c : s.toCharArray()) if (c >= 32 && c <= 126) sb.append(c);
        return sb.toString();
    }

    static int len(String s) {
        return s == null ? 0 : s.length();
    }

    static String trim(String s, int n) {
        return s == null ? "" : (s.length() <= n ? s : s.substring(0, n) + " …");
    }

    static String jget(String json, String key) {
        Matcher m = Pattern.compile("\"" + key + "\":\\s*(\"((?:\\\\.|[^\"\\\\])*)\"|null|true|false)")
                .matcher(json == null ? "" : json);
        if (!m.find()) return "";
        String g = m.group(1);
        if (g == null || "null".equals(g)) return "";
        if (g.startsWith("\"")) return m.group(2);
        return g;
    }
}
