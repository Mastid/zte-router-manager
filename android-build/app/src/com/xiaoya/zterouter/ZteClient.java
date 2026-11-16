package com.xiaoya.zterouter;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.CookieHandler;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.HttpCookie;
import java.net.URI;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.cert.X509Certificate;
import java.security.spec.X509EncodedKeySpec;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import javax.net.ssl.HostnameVerifier;
import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSession;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;

/**
 * 中兴家用路由器（ZXSLC SR7110 / 巡天系列）协议客户端。
 *
 * 纯 Java 实现，不含 Android 依赖，可先在桌面 JVM 上验证，再原样打进 APK。
 * 协议要点：
 *  - 全部走 HTTPS（自签证书，需信任所有证书），REST 风格：/?_type=xxx&_tag=yyy
 *  - 登录：取 logintoken → sha256(明文密码 + logintoken) → POST login_entry
 *  - 会话：SID_HTTPS_ cookie + 每次响应轮换的 x_xsrf_token（作为 _sessionTOKEN 放在表单末尾）
 *  - WiFi 密码：AES-CBC 零填充，key=SHA256(token)，iv=SHA256(逆序 token)[:16]
 *  - 提交密码：随机数 a/b 做 AES，随机数用固件内置 RSA 公钥加密后放 encode 字段
 */
public class ZteClient {

    public static final String ADMIN_USER = "admin";
    private static final String UA =
            "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) "
                    + "Chrome/126.0.0.0 Mobile Safari/537.36";

    /** 固件内置 RSA 公钥（DER base64），用于加密两段 AES 随机数 */
    private static final String RSA_PUB_DER =
            "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAodPTerkUVCYmv28SOfRV"
          + "7UKHVujx/HjCUTAWy9l0L5H0JV0LfDudTdMNPEKloZsNam3YrtEnq6jqMLJV4ASb"
          + "1d6axmIgJ636wyTUS99gj4BKs6bQSTUSE8h/QkUYv4gEIt3saMS0pZpd90y6+B/9"
          + "hZxZE/RKU8e+zgRqp1/762TB7vcjtjOwXRDEL0w71Jk9i8VUQ59MR1Uj5E8X3WIc"
          + "fYSK5RWBkMhfaTRM6ozS9Bqhi40xlSOb3GBxCmliCifOJNLoO9kFoWgAIw5hkSIb"
          + "GH+4Csop9Uy8VvmmB+B3ubFLN35qIa5OG5+SDXn4L7FeAA5lRiGxRi8tsWrtew8w"
          + "nwIDAQAB";

    private static SSLSocketFactory TRUST_ALL;

    private String host;
    /** 局域网地址（家里 Wi-Fi 直连）与远程地址（外网隧道/DDNS），留空表示没有 */
    private String hostLocal = "192.168.5.1";
    private String hostRemote = "";
    /** 当前用的是哪一条：lan / remote；custom 表示用户手动填的单一地址 */
    private String hostKind = "lan";
    private long hostPickerAt = 0;
    private final Map<String, String> cookies = new LinkedHashMap<String, String>();
    private final Map<String, String> pwdCache = new HashMap<String, String>();
    private String token;
    private String adminPwd;
    private boolean logged;
    private String error;
    /** 被别的设备（电脑面板等）抢走管理员会话后的冷却期，期间不再自动重登去互踢 */
    private long noFightUntil;
    /** 恢复出来的会话是否已经验过一次（冷启动只验一次，别每次刷新都多打一个请求） */
    private boolean checked;
    /** 上一次登录顶掉的设备 / 当前占着名额没顶成的设备 */
    private String kickedIp = "", kickedMac = "";
    private long kickedAt;
    private String pendingIp = "", pendingMac = "";

    public static final String VER = "1.1";
    /** 会话令牌的携带方式，登录后自动挑选可用的那个 */
    private static final String[] MODES = {"cookie", "cm", "query", "header"};
    private String sendMode = "cookie";
    private CookieManager cm;
    /** 最近几百行往返轨迹，出错时在手机上直接看 */
    private final StringBuilder trace = new StringBuilder();

    public ZteClient(String host) {
        this.host = cleanHost(host, "192.168.5.1");
        this.hostLocal = this.host;
        this.hostKind = "custom";
    }

    /** 把用户输入的地址规范化：去掉协议头、路径、末尾斜杠；保留端口与 IPv6 方括号 */
    public static String cleanHost(String h, String def) {
        if (h == null) return def;
        String s = h.trim();
        if (s.isEmpty()) return def;
        s = s.replaceFirst("(?i)^https?://", "");
        int slash = s.indexOf('/');
        if (slash > 0) s = s.substring(0, slash);
        if (s.endsWith("/")) s = s.substring(0, s.length() - 1);
        return s;
    }

    public String getHost() {
        return host;
    }

    public String getHostKind() {
        return hostKind;
    }

    /**
     * 配置双地址。prefer 为上次生效的那条（lan/remote），冷启动时先试它，能省一次探测。
     */
    public synchronized void setCandidates(String local, String remote, String prefer) {
        hostLocal = cleanHost(local, "192.168.5.1");
        hostRemote = cleanHost(remote, "");
        if (hostRemote.isEmpty()) {
            host = hostLocal;
            hostKind = "lan";
            return;
        }
        boolean useRemote = "remote".equals(prefer);
        host = useRemote ? hostRemote : hostLocal;
        hostKind = useRemote ? "remote" : "lan";
    }

    /** 探测某个地址是否可达（只要能连上并返回 HTTP 响应即可，未登录返回登录页也算通） */
    public static boolean reach(String h, int timeoutMs) {
        if (h == null || h.isEmpty()) return false;
        HttpsURLConnection c = null;
        try {
            c = (HttpsURLConnection) new URL("https://" + h + "/").openConnection();
            c.setSSLSocketFactory(trustAll());
            c.setHostnameVerifier(new HostnameVerifier() {
                public boolean verify(String x, SSLSession s) { return true; }
            });
            c.setRequestMethod("GET");
            c.setConnectTimeout(timeoutMs);
            c.setReadTimeout(timeoutMs);
            c.setInstanceFollowRedirects(false);
            c.setRequestProperty("User-Agent", UA);
            c.setRequestProperty("Accept-Encoding", "identity");
            int code = c.getResponseCode();
            return code > 0 && code < 500;
        } catch (Throwable t) {
            return false;
        } finally {
            if (c != null) try { c.disconnect(); } catch (Exception ignore) {}
        }
    }

    /** 局域网优先、外网兜底；两条都不通就保留原来的地址，让上层报可读的错误 */
    private void autoPick() {
        hostPickerAt = System.currentTimeMillis();
        if (hostRemote == null || hostRemote.isEmpty()) return;
        String first = "remote".equals(hostKind) ? hostRemote : hostLocal;
        String second = "remote".equals(hostKind) ? hostLocal : hostRemote;
        if (reach(first, 3500)) {
            host = first;
            hostKind = first.equals(hostRemote) ? "remote" : "lan";
            return;
        }
        if (reach(second, 5000)) {
            host = second;
            hostKind = second.equals(hostRemote) ? "remote" : "lan";
            trace("首选地址不通，已切到 " + hostKind + "：" + host);
            return;
        }
        host = first;
        hostKind = first.equals(hostRemote) ? "remote" : "lan";
    }

    /** 供界面查询/修改连接方式 */
    public synchronized String connJson() {
        return "{\"ok\":true,\"local\":" + jstr(hostLocal) + ",\"remote\":" + jstr(hostRemote)
                + ",\"host\":" + jstr(host) + ",\"kind\":" + jstr(hostKind) + "}";
    }

    /** body: {"local":"...","remote":"..."} */
    public synchronized String setConnJson(String body) {
        Map<String, Object> m = asMap(MiniJson.parse(body == null ? "{}" : bodyJsonSafe(body)));
        String lo = cleanHost(str(m.get("local")), "192.168.5.1");
        String re = cleanHost(str(m.get("remote")), "");
        setCandidates(lo, re, "");
        // 换了地址，旧会话对不上号，但记住的密码要留着，下次自动重登
        dropSession();
        return connJson();
    }

    private static String bodyJsonSafe(String s) {
        String t = s == null ? "" : s.trim();
        return t.startsWith("{") ? t : "{}";
    }

    /** 只丢会话，不清密码（换地址/被顶掉时用） */
    public synchronized void dropSession() {
        cookies.clear();
        token = null;
        logged = false;
        errClear();
        checked = false;
    }

    private void errClear() {
        error = null;
    }

    /** 手动触发一次选路（界面上点“测试连接”） */
    public synchronized String pickJson() {
        autoPick();
        return "{\"ok\":true,\"host\":" + jstr(host) + ",\"kind\":" + jstr(hostKind)
                + ",\"localOk\":" + reach(cleanHost(hostLocal, "192.168.5.1"), 2500) + "}";
    }

    // ---------------- 对外接口（返回 JSON 字符串，供 WebView 调用） ----------------

    public synchronized String stateJson() {
        // App 被清后台 / Activity 重建后，这里是页面问“登录了吗”的第一站：
        // 先确认从本地恢复的会话还能用，不行就用记住的密码静默登回去，
        // 免得每次切出去再回来都要用户重新输密码。
        if (!checked) {
            checked = true;
            // 有远程地址时先选路：在家走局域网（快），在外面自动走隧道
            if (!hostRemote.isEmpty()) autoPick();
            if (logged) {
                if (!alive()) {
                    trace("恢复出来的会话已失效，改用记住的密码重登");
                    logged = false;
                    if (adminPwd != null && !adminPwd.isEmpty() && !login(adminPwd)) {
                        if (error != null && error.contains("密码不正确")) adminPwd = null;
                    }
                }
            } else if (adminPwd != null && !adminPwd.isEmpty()) {
                trace("冷启动自动登录");
                if (!login(adminPwd) && error != null && error.contains("密码不正确")) {
                    adminPwd = null;          // 密码变了就别再拿它试，免得触发路由器锁定
                }
            }
        }
        return "{\"logged\":" + logged + ",\"error\":" + jstr(error) + ",\"host\":" + jstr(host)
                + ",\"kind\":" + jstr(hostKind) + ",\"remote\":" + jstr(hostRemote)
                + ",\"ver\":" + jstr(VER) + ",\"mode\":" + jstr(sendMode) + "}";
    }

    public synchronized String loginJson(String pwd) {
        kickedIp = "";
        kickedMac = "";
        kickedAt = 0;
        pendingIp = "";
        pendingMac = "";
        String lastErr = null;
        for (int attempt = 1; attempt <= 3; attempt++) {
            boolean ok = login(pwd);
            if (ok) {
                return "{\"ok\":true,\"logged\":true,\"error\":null,\"kicked\":" + kickedJson() + "}";
            }
            lastErr = error;
            // 密码类错误重试只会触发锁定，绝不重试
            if (error != null && error.contains("密码不正确")) {
                break;
            }
            if (attempt < 3) {
                logoutNow();                       // 把刚占下的会话名额还回去
                try {
                    Thread.sleep(attempt == 1 ? 5000L : 12000L);
                } catch (InterruptedException ie) {
                    break;
                }
            }
        }
        return "{\"ok\":false,\"logged\":false,\"error\":" + jstr(lastErr) + "}";
    }

    /** 刚顶掉的设备信息（30 秒内有效），给界面提示用 */
    private String kickedJson() {
        if (kickedIp.isEmpty() && kickedMac.isEmpty()) return "null";
        if (System.currentTimeMillis() - kickedAt > 30000L) return "null";
        return "{\"ip\":" + jstr(kickedIp) + ",\"mac\":" + jstr(kickedMac) + "}";
    }

    /** 手动「重新登录」：先退掉自己这边，再强制接管（顶掉其它设备的管理会话） */
    public synchronized String reloginForce() {
        String pwd = adminPwd;
        if (pwd == null || pwd.isEmpty()) {
            return "{\"ok\":false,\"needPwd\":true,\"error\":\"需要重新输入管理员密码\"}";
        }
        try {
            logoutNow();
        } catch (Exception ignored) {
        }
        logged = false;
        token = null;
        checked = false;
        noFightUntil = 0;
        kickedIp = "";
        kickedMac = "";
        kickedAt = 0;
        trace("---- 手动重新登录并接管 ----");
        if (!login(pwd)) {
            return "{\"ok\":false,\"error\":" + jstr(error) + "}";
        }
        return "{\"ok\":true,\"error\":null,\"kicked\":" + kickedJson() + "}";
    }

    public synchronized String allJson() {
        try {
            return apiAll();
        } catch (NotLogged e) {
            return "{\"logged\":false,\"error\":\"NOT_LOGGED\",\"detail\":" + jstr(error) + "}";
        } catch (Exception e) {
            return "{\"logged\":" + logged + ",\"error\":" + jstr(msg(e)) + "}";
        }
    }

    public synchronized String wifiPwdJson(String band) {
        try {
            return "{\"band\":" + jstr(band) + ",\"pwd\":" + jstr(wifiPwd(band)) + ",\"error\":null}";
        } catch (NotLogged e) {
            return "{\"logged\":false,\"error\":\"NOT_LOGGED\"}";
        } catch (Exception e) {
            return "{\"error\":" + jstr(msg(e)) + "}";
        }
    }

    public synchronized String saveWifiJson(String bodyJson) {
        try {
            Map<String, Object> body = asMap(MiniJson.parse(bodyJson == null ? "{}" : bodyJson));
            setWifi(body);
            return "{\"ok\":true}";
        } catch (NotLogged e) {
            return "{\"logged\":false,\"error\":\"NOT_LOGGED\"}";
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":" + jstr(msg(e)) + "}";
        }
    }

    public synchronized String rebootJson() {
        try {
            return reboot();
        } catch (NotLogged e) {
            return "{\"logged\":false,\"error\":\"NOT_LOGGED\"}";
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":" + jstr(msg(e)) + "}";
        }
    }

    /** 连通性自检：只请求公开的登录令牌接口，不需要密码 */
    public synchronized String probeJson() {
        try {
            long t0 = System.currentTimeMillis();
            Resp r = req("/?_type=loginsceneData&_tag=login_token_json", null, 12);
            long ms = System.currentTimeMillis() - t0;
            Map<String, Object> m = asMap(MiniJson.parse(r.body));
            String lt = str(m.get("logintoken"));
            String sess = str(m.get("_sessionToken"));
            StringBuilder sb = new StringBuilder();
            sb.append("{\"status\":").append(r.status);
            sb.append(",\"ms\":").append(ms);
            sb.append(",\"hasLogintoken\":").append(lt != null && !lt.isEmpty());
            sb.append(",\"logintokenLen\":").append(lt == null ? 0 : lt.length());
            sb.append(",\"sessionLen\":").append(sess == null ? 0 : sess.length());
            sb.append(",\"cookieCount\":").append(cookies.size());
            sb.append(",\"cookies\":").append(jstr(cookies.keySet().toString()));
            sb.append(",\"bodyHead\":").append(jstr(r.body.length() > 160 ? r.body.substring(0, 160) : r.body));
            sb.append('}');
            return sb.toString();
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":" + jstr(msg(e)) + "}";
        }
    }

    /**
     * 诊断用（不需要密码）：报告网络是否可达、令牌是否取到、当前会话令牌的携带方式，
     * 以及最近一次登录/读取的原始往返轨迹。用于在手机上定位"登录后被踢回登录页"的确切原因。
     */
    public synchronized String diagJson() {
        StringBuilder sb = new StringBuilder(2048);
        sb.append('{');
        int st = 0;
        long ms = 0;
        int tokLen = 0;
        String ck = cookies.keySet().toString();
        String head = "";
        boolean reach = true;
        String netErr = null;
        try {
            long t0 = System.currentTimeMillis();
            Resp r = req("/?_type=loginsceneData&_tag=login_token_json", null, 10);
            ms = System.currentTimeMillis() - t0;
            st = r.status;
            head = cut(r.body, 120);
            try {
                Map<String, Object> m = asMap(MiniJson.parse(r.body));
                String lt = str(m.get("logintoken"));
                tokLen = lt == null ? 0 : lt.length();
            } catch (Exception ignored) {
            }
            ck = cookies.keySet().toString();
        } catch (Throwable t) {
            reach = false;
            netErr = msg(t);
        }
        sb.append("\"ok\":true");
        sb.append(",\"ver\":").append(jstr(VER));
        sb.append(",\"host\":").append(jstr(host));
        sb.append(",\"reach\":").append(reach);
        sb.append(",\"netError\":").append(jstr(netErr));
        sb.append(",\"httpsStatus\":").append(st);
        sb.append(",\"ms\":").append(ms);
        sb.append(",\"tokenLen\":").append(tokLen);
        sb.append(",\"cookies\":").append(jstr(ck));
        sb.append(",\"bodyHead\":").append(jstr(head));
        sb.append(",\"logged\":").append(logged);
        sb.append(",\"mode\":").append(jstr(sendMode));
        sb.append(",\"lastError\":").append(jstr(error));
        sb.append(",\"trace\":").append(jstr(trace.toString()));
        sb.append('}');
        return sb.toString();
    }

    /**
     * 登录成功后校验会话：依次尝试三种令牌携带方式，选中能读到数据的那个。
     * 有些机型/系统上 HttpURLConnection 会丢掉手写的 Cookie 头，靠这一步自动兜住。
     */
    private boolean handshake() {
        for (String m : MODES) {
            sendMode = m;
            if ("cm".equals(m)) {
                try {
                    installCookieManager();
                    seedCookies();
                } catch (Exception e) {
                    trace("CookieManager 准备失败 " + msg(e));
                }
            }
            try {
                Resp r = req("/?_type=vueData&_tag=vue_home_device_data", null, 12);
                boolean d = dead(r.body);
                trace("校验 mode=" + m + " status=" + r.status + (d ? " 被拒" : " 通过")
                        + " len=" + (r.body == null ? 0 : r.body.length())
                        + (d ? " head=" + cut(r.body, 60) : ""));
                if (!d && r.status == 200) {
                    trace("会话可用，令牌携带方式=" + m);
                    if (!"cm".equals(m)) CookieHandler.setDefault(null);
                    return true;
                }
            } catch (Exception e) {
                trace("校验 mode=" + m + " 异常 " + msg(e));
            }
        }
        sendMode = "cookie";
        CookieHandler.setDefault(null);
        return false;
    }

    private void trace(String s) {
        trace.append(s).append('\n');
        if (trace.length() > 8000) trace.delete(0, trace.length() - 8000);
    }

    private static String cut(String s, int n) {
        if (s == null) return "";
        return s.length() <= n ? s : s.substring(0, n) + "…";
    }

    /** 主动登出：归还管理员会话名额（这个固件同时在线的管理员会话数量很少） */
    public synchronized void logoutNow() {
        if (!logged) return;
        try {
            LinkedHashMap<String, String> f = new LinkedHashMap<String, String>();
            f.put("_sessionTOKEN", token == null ? "" : token);
            req("/?_type=loginData&_tag=logout_entry", f, 8);
            trace("已主动登出，归还会话名额");
        } catch (Exception ignored) {
        }
        logged = false;
    }

    public synchronized void forget() {
        logoutNow();
        pwdCache.clear();
        cookies.clear();
        token = null;
        logged = false;
        adminPwd = null;
        checked = true;          // 用户主动退出：不要再拿旧密码自动登回去
    }

    // ---------------- 会话持久化：清理后台后不用重登 ----------------

    public synchronized void setSavedPwd(String pwd) {
        if (pwd != null && !pwd.isEmpty()) adminPwd = pwd;
    }

    /** 只导出会话凭据；密码由调用方单独加密保存，不混在同一个字段里 */
    public synchronized String exportSession() {
        StringBuilder sb = new StringBuilder(160);
        sb.append("{\"token\":").append(jstr(token));
        sb.append(",\"mode\":").append(jstr(sendMode));
        sb.append(",\"logged\":").append(logged);
        sb.append(",\"cookies\":{");
        boolean first = true;
        for (Map.Entry<String, String> e : cookies.entrySet()) {
            if (!first) sb.append(',');
            first = false;
            sb.append(jstr(e.getKey())).append(':').append(jstr(e.getValue()));
        }
        sb.append("}}");
        return sb.toString();
    }

    public synchronized void importSession(String json) {
        if (json == null || json.trim().isEmpty()) return;
        try {
            Map<String, Object> m = asMap(MiniJson.parse(json));
            String t = str(m.get("token"));
            if (t != null && !t.isEmpty() && !"null".equals(t)) token = t;
            String md = str(m.get("mode"));
            if (md != null && !md.isEmpty() && !"null".equals(md)) sendMode = md;
            Object ck = m.get("cookies");
            if (ck instanceof Map) {
                for (Map.Entry<String, Object> e : asMap(ck).entrySet()) {
                    String v = str(e.getValue());
                    if (v != null && !"null".equals(v)) cookies.put(e.getKey(), v);
                }
            }
            logged = isTrue(m.get("logged"));
        } catch (Exception e) {
            trace("恢复会话失败 " + msg(e));
        }
    }

    /** 轻量探活：读一个很小的数据接口，判断现有会话还能不能用 */
    public synchronized boolean alive() {
        try {
            Resp r = req("/?_type=vueData&_tag=vue_home_device_data", null, 6);
            return r.body != null && !dead(r.body);
        } catch (Exception e) {
            trace("探活失败 " + msg(e));
            return false;
        }
    }

    /**
     * 界面发现会话掉了（被顶掉 / 超时）时调用：
     * 能用记住的密码登回去就登，实在不行才让用户输密码。
     */
    public synchronized String resumeJson() {
        checked = true;
        if (logged && alive()) {
            return "{\"ok\":true,\"logged\":true}";
        }
        logged = false;
        if (adminPwd == null || adminPwd.isEmpty()) {
            return "{\"ok\":false,\"logged\":false,\"needPwd\":true,\"error\":\"需要重新输入密码\"}";
        }
        trace("会话掉线，自动重登");
        boolean ok = login(adminPwd);
        if (!ok && error != null && error.contains("密码不正确")) adminPwd = null;
        return "{\"ok\":" + ok + ",\"logged\":" + ok + ",\"error\":" + jstr(ok ? null : error) + "}";
    }

    // ---------------- 登录 ----------------

    private boolean login(String pwd) {
        // 固件对登录做一次性令牌校验：取令牌与提交之间只要被别的请求插进来，
        // 就会返回 e_csrf_check_fail（页面过期）。这里整轮重试一次即可。
        for (int i = 0; i < 2; i++) {
            boolean ok = loginOnce(pwd);
            if (ok) return true;
            boolean csrf = error != null && (error.contains("csrf")
                    || error.contains("页面过期") || error.contains("1452"));
            if (!csrf) return false;
            trace("登录被判定令牌过期，重取令牌重试 " + (i + 1));
            try {
                Thread.sleep(350);
            } catch (InterruptedException ignored) {
            }
        }
        return false;
    }

    private boolean loginOnce(String pwd) {
        cookies.clear();
        token = null;
        logged = false;
        trace("---- 登录开始 host=" + host + " ----");
        try {
            Resp r = req("/?_type=loginsceneData&_tag=login_token_json", null, 12);
            trace("取令牌 status=" + r.status + " len=" + (r.body == null ? 0 : r.body.length())
                    + " cookie=" + cookies.keySet());
            Object o = MiniJson.parse(r.body);
            Map<String, Object> info = asMap(o);
            String lt = str(info.get("logintoken"));
            String sess = str(info.get("_sessionToken"));
            if (lt == null || lt.isEmpty()) {
                error = "取登录令牌失败，路由器没有返回预期内容";
                trace("取令牌失败 body=" + cut(r.body, 120));
                return false;
            }
            LinkedHashMap<String, String> f = new LinkedHashMap<String, String>();
            f.put("Username", ADMIN_USER);
            f.put("Password", sha256Hex(pwd + lt));
            f.put("action", "login");
            f.put("Frm_Logintoken", "");
            f.put("captchaCode", "");
            f.put("_sessionTOKEN", sess == null ? "" : sess);

            Resp r2 = req("/?_type=loginData&_tag=login_entry", f, 15);
            trace("登录应答 status=" + r2.status + " body=" + cut(r2.body, 160));
            Map<String, Object> res = asMap(MiniJson.parse(r2.body));

            if (isTrue(res.get("login_need_refresh"))) {
                String st = str(res.get("sess_token"));
                token = (st == null || st.isEmpty()) ? sess : st;
                logged = true;
                checked = true;
                error = null;
                adminPwd = pwd;
                pwdCache.clear();
                // 关键：确认这个会话真的能读数据，否则界面会“刚进主页就被弹回登录”。
                // 若被别的设备占着，claimSession() 会先把它顶下线（login_preempt）。
                if (!claimSession() || !handshake()) {
                    adminPwd = null;
                    String et = str(res.get("loginErrType"));
                    String em = str(res.get("loginErrMsg"));
                    boolean busy = (et != null && et.contains("preempt")) || pendingIp.length() > 0;
                    if (busy) noFightUntil = System.currentTimeMillis() + 90000L;
                    logoutNow();               // 会话没建成，主动归还名额（须在 logged=false 之前）
                    if (pendingIp.length() > 0) {
                        error = "路由器上还有别的管理员会话（" + pendingIp
                                + " 登录着），接管没成功；点「重新登录」可以再顶一次";
                    } else if (busy) {
                        error = "路由器提示 e_exceed_max_user_preemption（管理员会话被占满/被顶掉）。"
                                + "点「重新登录」可以顶掉对方；仍不行就等 1–2 分钟再试，"
                                + "或者重启路由器。";
                    } else {
                        error = "登录已被路由器接受，但随即读不到数据（会话未建立"
                                + (et == null || et.isEmpty() ? "" : "：" + et + " " + em) + "）。"
                                + "可点下方“诊断信息”查看详情。";
                    }
                    trace("会话校验全部失败，放弃本次登录 errType=" + et);
                    return false;
                }
                return true;
            }
            double lock = num(res.get("lockingTime"));
            String msg = (str(res.get("loginErrMsg")) + " " + str(res.get("loginErrType"))).trim().toLowerCase();
            if (lock > 0) {
                error = String.format("尝试次数过多，已临时锁定，请等待 %d 秒后再试", (int) lock);
            } else if (msg.contains("preempt")) {
                noFightUntil = System.currentTimeMillis() + 90000L;
                error = "路由器上还有其他管理员会话（例如电脑面板正在登录），请先退出那边再试";
            } else if (msg.contains("error") || msg.contains("password") || msg.contains("userpass")) {
                error = "密码不正确，可查看路由器背面标签";
            } else {
                String raw = r2.body == null ? "" : r2.body;
                if (raw.length() > 100) raw = raw.substring(0, 100);
                error = "登录失败：" + (msg.isEmpty() ? raw : msg);
            }
            return false;
        } catch (Exception e) {
            error = "连接路由器失败：" + msg(e);
            trace("登录异常 " + e);
            return false;
        }
    }

    private boolean relogin() {
        if (adminPwd == null) return false;
        if (System.currentTimeMillis() < noFightUntil) {
            // 刚被其他设备接管：不抢会话，让对方的登录能正常完成
            error = "管理员会话已被其他设备接管，请稍后重试";
            return false;
        }
        return login(adminPwd);
    }

    // ---------------- HTTP ----------------

    private static class Resp {
        int status;
        String body;
    }

    private static class NotLogged extends Exception {
        NotLogged() { super("NOT_LOGGED"); }
    }

    private Resp req(String path, LinkedHashMap<String, String> form, int timeoutSec) throws IOException {
        // 部分系统上 HttpURLConnection 会忽略手写的 Cookie 头，于是额外支持把一次性令牌
        // 放进查询串或请求头（固件对 GET 的兼容行为），由 handshake() 挑出可用的那种。
        String[] extraHeaders = null;
        String tok = token;
        if (form == null && tok != null && !tok.isEmpty()) {
            if ("query".equals(sendMode)) {
                path = path + (path.indexOf('?') >= 0 ? "&" : "?") + "_sessionTOKEN=" + enc(tok);
            } else if ("header".equals(sendMode)) {
                extraHeaders = new String[]{"_sessionTOKEN", tok, "x_xsrf_token", tok};
            }
        }
        HttpsURLConnection c = (HttpsURLConnection) new URL("https://" + host + path).openConnection();
        c.setSSLSocketFactory(trustAll());
        c.setHostnameVerifier(new HostnameVerifier() {
            public boolean verify(String h, SSLSession s) { return true; }
        });
        c.setConnectTimeout(8000);
        c.setReadTimeout(Math.max(6, timeoutSec) * 1000);
        c.setRequestProperty("User-Agent", UA);
        c.setRequestProperty("Accept", "application/json, text/plain, */*");
        c.setRequestProperty("Accept-Encoding", "identity");   // 否则 HttpURLConnection 默认要 gzip
        c.setRequestProperty("Referer", "https://" + host + "/");
        c.setRequestProperty("X-Requested-With", "XMLHttpRequest");
        if (!cookies.isEmpty() && !"cm".equals(sendMode)) {
            c.setRequestProperty("Cookie", cookieHeader());
        }
        if (extraHeaders != null) {
            for (int i = 0; i + 1 < extraHeaders.length; i += 2) {
                c.setRequestProperty(extraHeaders[i], extraHeaders[i + 1]);
            }
        }
        if (form == null) {
            c.setRequestProperty("Content-Type", "text/xml; charset=utf-8");
        } else {
            if (token != null && !token.isEmpty() && !form.containsKey("_sessionTOKEN")) {
                form.put("_sessionTOKEN", token);
            }
            c.setDoOutput(true);
            c.setRequestMethod("POST");
            c.setRequestProperty("Content-Type", "application/x-www-form-urlencoded");
            byte[] out = urlencode(form).getBytes(StandardCharsets.UTF_8);
            c.setFixedLengthStreamingMode(out.length);
            OutputStream os = c.getOutputStream();
            try {
                os.write(out);
            } finally {
                os.close();
            }
        }
        Resp r = new Resp();
        r.status = c.getResponseCode();
        String t = c.getHeaderField("x_xsrf_token");
        if (t != null && !t.isEmpty()) {
            token = t;
        }
        storeCookies(c.getHeaderFields());
        InputStream is = r.status >= 400 ? c.getErrorStream() : c.getInputStream();
        r.body = is == null ? "" : readAll(is);
        c.disconnect();
        return r;
    }

    private static SSLSocketFactory trustAll() {
        if (TRUST_ALL != null) return TRUST_ALL;
        try {
            TrustManager[] tm = new TrustManager[]{new X509TrustManager() {
                public void checkClientTrusted(X509Certificate[] c, String a) { }
                public void checkServerTrusted(X509Certificate[] c, String a) { }
                public X509Certificate[] getAcceptedIssuers() { return new X509Certificate[0]; }
            }};
            SSLContext ctx = SSLContext.getInstance("TLS");
            ctx.init(null, tm, new SecureRandom());
            TRUST_ALL = ctx.getSocketFactory();
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
        return TRUST_ALL;
    }

    /** 官方推荐姿势：让系统 CookieManager 负责收发 Cookie（可绕过某些机型丢弃手写头的问题） */
    private void installCookieManager() {
        if (cm == null) {
            cm = new CookieManager(null, CookiePolicy.ACCEPT_ALL);
        }
        CookieHandler.setDefault(cm);
    }

    /** 把已经拿到的 Cookie 灌进 CookieManager */
    private void seedCookies() throws Exception {
        cm.getCookieStore().removeAll();      // 清掉上一次会话的旧 SID，避免重复 Cookie 打架
        URI u = new URI("https://" + host + "/");
        for (Map.Entry<String, String> e : cookies.entrySet()) {
            HttpCookie ck = new HttpCookie(e.getKey(), e.getValue());
            ck.setPath("/");
            ck.setVersion(0);
            cm.getCookieStore().add(u, ck);
        }
    }

    private String cookieHeader() {
        StringBuilder sb = new StringBuilder();
        for (Map.Entry<String, String> e : cookies.entrySet()) {
            if (sb.length() > 0) sb.append("; ");
            sb.append(e.getKey()).append('=').append(e.getValue());
        }
        return sb.toString();
    }

    private void storeCookies(Map<String, List<String>> headers) {
        if (headers == null) return;
        for (Map.Entry<String, List<String>> e : headers.entrySet()) {
            if (e.getKey() == null) continue;
            if (!"set-cookie".equalsIgnoreCase(e.getKey())) continue;
            for (String v : e.getValue()) {
                if (v == null) continue;
                int semi = v.indexOf(';');
                String pair = semi >= 0 ? v.substring(0, semi) : v;
                int eq = pair.indexOf('=');
                if (eq <= 0) continue;
                cookies.put(pair.substring(0, eq).trim(), pair.substring(eq + 1).trim());
            }
        }
    }

    private static String readAll(InputStream is) throws IOException {
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        int n;
        try {
            while ((n = is.read(buf)) > 0) bos.write(buf, 0, n);
        } finally {
            is.close();
        }
        return new String(bos.toByteArray(), StandardCharsets.UTF_8);
    }

    private static String urlencode(LinkedHashMap<String, String> form) {
        StringBuilder sb = new StringBuilder();
        for (Map.Entry<String, String> e : form.entrySet()) {
            if (sb.length() > 0) sb.append('&');
            sb.append(enc(e.getKey())).append('=').append(enc(e.getValue() == null ? "" : e.getValue()));
        }
        return sb.toString();
    }

    private static String enc(String s) {
        try {
            return URLEncoder.encode(s, "UTF-8");
        } catch (Exception e) {
            return s;
        }
    }

    // ---------------- 会话与业务 ----------------

    private void ensure() throws NotLogged {
        if (!logged) throw new NotLogged();
    }

    private static boolean dead(String body) {
        String head = body == null ? "" : body.trim();
        String low = head.length() > 300 ? head.substring(0, 300).toLowerCase() : head.toLowerCase();
        // 被别的设备顶掉时固件给的是 LOGIN_PREEMPT_ID 页，不是登录页，同样算掉线
        return low.startsWith("<!doctype") || low.contains("<html")
                || (body != null && body.contains("SessionTimeout"))
                || (body != null && body.contains("LOGIN_PREEMPT_ID"));
    }

    /** 从 XML 里取字段值（preempt_sessid / preempt_ip 之类） */
    private static String xmlVal(String body, String tag) {
        if (body == null) return "";
        java.util.regex.Matcher m = java.util.regex.Pattern
                .compile("<" + tag + ">([^<]*)</" + tag + ">").matcher(body);
        return m.find() ? m.group(1).trim() : "";
    }

    /** 读用户信息页：被别人占着时返回 LOGIN_PREEMPT_ID 页，空闲返回 null */
    private String preemptPage() throws IOException {
        LinkedHashMap<String, String> f = new LinkedHashMap<String, String>();
        f.put("IF_ACTION", "Apply");
        f.put("IsAutoShowWizard", "0");
        Resp r = req("/?_type=hiddenData&_tag=vue_userif_data", f, 10);
        String b = r.body == null ? "" : r.body;
        return b.contains("LOGIN_PREEMPT_ID") ? b : null;
    }

    /** 强制接管：让占着管理员名额的那台设备下线（固件 login_preempt） */
    private boolean takeOver(String sessid) {
        if (sessid == null || sessid.isEmpty()) return false;
        try {
            LinkedHashMap<String, String> f = new LinkedHashMap<String, String>();
            f.put("preempt_sessid", sessid);
            f.put("action", "preempt");
            req("/?_type=loginData&_tag=login_preempt", f, 10);
            return preemptPage() == null;
        } catch (Exception e) {
            trace("接管失败 " + msg(e));
            return false;
        }
    }

    /** 登录后确认会话真的归自己：被手机 App / 别的管理页占着就顶掉对方 */
    private boolean claimSession() {
        try {
            String pre = preemptPage();
            if (pre == null) return true;
            String ip = xmlVal(pre, "preempt_ip");
            String mac = xmlVal(pre, "preempt_mac");
            String sid = xmlVal(pre, "preempt_sessid");
            trace("会话被占 ip=" + ip + " mac=" + mac);
            if (!takeOver(sid)) {
                // 一次性令牌刚轮换过会失败，换个新令牌再接管一次
                try {
                    req("/?_type=vueData&_tag=vue_home_device_data", null, 8);
                } catch (Exception ignored) {
                }
                String again = preemptPage();
                if (again == null) return true;
                if (!takeOver(xmlVal(again, "preempt_sessid"))) {
                    pendingIp = ip;
                    pendingMac = mac;
                    trace("接管失败，名额仍在 " + ip);
                    return false;
                }
            }
            kickedIp = ip;
            kickedMac = mac;
            kickedAt = System.currentTimeMillis();
            pendingIp = "";
            pendingMac = "";
            trace("已接管管理会话，顶掉 " + (ip.isEmpty() ? mac : ip));
            return true;
        } catch (Exception e) {
            trace("claimSession 异常 " + msg(e));
            return false;
        }
    }

    /** 带自动重登的业务 GET */
    private Map<String, List<Map<String, String>>> fetch(String path) throws IOException, NotLogged {
        ensure();
        Resp r = req(path, null, 15);
        if (r.status == 404) {
            // 这台固件对不存在的 tag 返回 404 页，页里还带 SessionTimeout 字样。
            // 404 只说明「接口没这个 tag」，绝不能当成会话失效（会把后续请求全带死）
            trace("接口不存在(404) " + path);
            return new LinkedHashMap<String, List<Map<String, String>>>();
        }
        if (dead(r.body)) {
            trace("读数据被拒 " + path + " status=" + r.status + " head=" + cut(r.body, 80));
            logged = false;
            pwdCache.clear();
            if (!relogin()) throw new NotLogged();
            r = req(path, null, 15);
            if (r.status == 404) {
                trace("接口不存在(404) " + path);
                return new LinkedHashMap<String, List<Map<String, String>>>();
            }
            if (dead(r.body)) {
                logged = false;
                throw new NotLogged();
            }
        }
        return groups(r.body);
    }

    // ================= 防蹭网 / 网络设置 =================
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
            // 规则读取口径以固件前端 chunk 为准（chunks/4.js getAclRules）：
            //   GET /?_type=vuejsonData&_tag=aclrule_data → OBJ_ACLCFG_ID[]，每条带 ACLPolicy(Ban/Allow)
            // 策略兜底：hiddenData&_tag=vue_macfilterrule_data 的 OBJ_WLANAP_ID.ACLPolicy
            // （注意 vueData 类型是 404，之前用错类型导致整个会话被误判掉线）
            java.util.List<Map<String, String>> src = new java.util.ArrayList<Map<String, String>>();
            String rulesNote = "";
            String aclTxt = "";
            try {
                aclTxt = fetchText("/?_type=vuejsonData&_tag=aclrule_data&_=" + System.currentTimeMillis());
                Object parsed = null;
                try {
                    parsed = MiniJson.parse(aclTxt);
                } catch (Exception pe) {
                    trace("aclrule_data 不是 JSON head=" + cut(aclTxt, 200));
                }
                Object arr = parsed instanceof Map ? asMap(parsed).get("OBJ_ACLCFG_ID") : null;
                for (Object it : jlist(arr)) {
                    Map<String, Object> m = asMap(it);
                    Map<String, String> c = new LinkedHashMap<String, String>();
                    for (Map.Entry<String, Object> en : m.entrySet()) c.put(en.getKey(), str(en.getValue()));
                    src.add(c);
                }
                trace("aclrule_data 规则数=" + src.size() + " head=" + cut(aclTxt, 160));
            } catch (NotLogged e) {
                rulesNote = "会话已失效";
                trace("aclrule_data NOT_LOGGED");
            } catch (Exception e) {
                rulesNote = "读取失败：" + msg(e);
                trace("aclrule_data 失败 " + msg(e));
            }

            String apPol = "";
            try {
                Map<String, List<Map<String, String>>> mf = fetch("/?_type=hiddenData&_tag=vue_macfilterrule_data&_="
                        + System.currentTimeMillis());
                for (Map<String, String> it : list(mf, "OBJ_WLANAP_ID")) {
                    String pol = nz(it.get("ACLPolicy")).trim();
                    if (!pol.isEmpty()) { apPol = pol; break; }
                }
                if (src.isEmpty()) {
                    java.util.List<Map<String, String>> xml = list(mf, "OBJ_ACLCFG_ID");
                    if (!xml.isEmpty()) {
                        src.addAll(xml);
                        trace("aclrule_data 为空，改用 macfilterrule XML 的 " + xml.size() + " 条规则");
                    }
                }
                trace("macfilterrule AP策略=" + (apPol.isEmpty() ? "(空)" : apPol)
                        + " 规则数=" + list(mf, "OBJ_ACLCFG_ID").size());
            } catch (Exception e) {
                trace("macfilterrule 读取失败 " + msg(e));
            }
            if (src.isEmpty() && rulesNote.isEmpty()) {
                rulesNote = aclTxt == null || aclTxt.isEmpty()
                        ? "接口没有返回数据（固件可能不支持）" : "路由器返回的名单是空的";
            }
            java.util.HashSet<String> seenMac = new java.util.HashSet<String>();
            for (Map<String, String> r : src) {
                String mac = up(str(r.get("MACAddress")));
                if (mac.isEmpty() || !seenMac.add(mac)) continue;
                String pol = nz(str(r.get("ACLPolicy"))).trim();
                if (pol.isEmpty()) pol = apPol;
                if (pol.isEmpty()) pol = mode == 2 ? "Allow" : "Ban";
                pol = pol.substring(0, 1).toUpperCase(Locale.US) + pol.substring(1).toLowerCase(Locale.US);
                if (rules.length() > 1) rules.append(',');
                rules.append("{\"inst\":").append(jstr(nz(str(r.get("_InstID")))))
                        .append(",\"mac\":").append(jstr(mac))
                        .append(",\"name\":").append(jstr(pick(nz(str(r.get("DisplayedName"))), nz(str(r.get("Name"))))))
                        .append(",\"policy\":").append(jstr(pol)).append('}');
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
                    + ",\"rulesNote\":" + jstr(rulesNote)
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
            // DHCP 服务器开关以自身字段为准；Dhcp4sBridgePolicyEnable 只是桥接下放行 DHCP 报文的策略，
            // 关掉 DHCP 后它一般仍是 1，以前用「或」拼起来会一直显示已开启
            String swKey = "";
            String swVal = "";
            for (String k : new String[]{"ServerEnable", "DHCPEnable", "DHCPServerEnable", "DHCPServer"}) {
                String v = nz(dh.get(k));
                if (!v.isEmpty()) { swKey = k; swVal = v; break; }
            }
            String bridge = nz(bd.get("Dhcp4sBridgePolicyEnable"));
            if (bridge.isEmpty()) bridge = nz(bd.get("Dhcp4sBridgePolicy"));
            if (bridge.isEmpty()) bridge = nz(bd.get("BridgePolicyEnable"));
            String dhcpOn = "null";
            if (!swKey.isEmpty()) {
                dhcpOn = ("1".equals(swVal) || "true".equalsIgnoreCase(swVal) || "on".equalsIgnoreCase(swVal)) ? "true" : "false";
            } else if (!bridge.isEmpty()) {
                swKey = "Dhcp4sBridgePolicyEnable";
                dhcpOn = "1".equals(bridge) ? "true" : "false";
            }
            return "{\"ok\":true,\"ip\":" + jstr(pick(nz(br.get("IPAddr")), nz(dh.get("IPRouters"))))
                    + ",\"mask\":" + jstr(nz(br.get("SubMask")))
                    + ",\"dhcpOn\":" + dhcpOn
                    + ",\"dhcpField\":" + jstr(swKey)
                    + ",\"dhcpFields\":{\"ServerEnable\":" + jstr(nz(dh.get("ServerEnable")))
                    + ",\"Dhcp4sBridgePolicyEnable\":" + jstr(bridge) + "}"
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
            Map<String, Object> df = asMap(cur.get("dhcpFields"));
            String bridgeNow = nz(str(df.get("Dhcp4sBridgePolicyEnable")));
            f.put("Dhcp4sBridgePolicyEnable", bridgeNow.isEmpty() ? "1" : bridgeNow);
            String sw = nz(str(cur.get("dhcpField")));
            boolean swIsSwitch = "ServerEnable".equals(sw) || "DHCPEnable".equals(sw)
                    || "DHCPServerEnable".equals(sw) || "DHCPServer".equals(sw);
            if (!swIsSwitch) sw = "ServerEnable";
            boolean swKnown = b.get("dhcpOn") instanceof Boolean;
            if (swKnown) f.put(sw, Boolean.TRUE.equals(b.get("dhcpOn")) ? "1" : "0");
            String txt = ax("/?_type=vueData&_tag=addr_manager_data", f, 20);
            String es = nz(xmlField(txt, "IF_ERRORSTR"));
            if (!es.toUpperCase().startsWith("SUCC") && swKnown) {
                // 个别固件不认这个字段：去掉再存一次，别把局域网设置一起拖挂
                f.remove(sw);
                txt = ax("/?_type=vueData&_tag=addr_manager_data", f, 20);
                es = nz(xmlField(txt, "IF_ERRORSTR"));
                if (es.toUpperCase().startsWith("SUCC")) {
                    return "{\"ok\":true,\"ip\":" + jstr(ip) + ",\"mask\":" + jstr(mask)
                            + ",\"needRelogin\":" + (!ip.equals(str(cur.get("ip"))))
                            + ",\"warn\":\"路由器没接受 DHCP 开关字段，局域网其他设置已保存\"}";
                }
            }
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

    private String ax(String path, LinkedHashMap<String, String> form, int timeoutSec)
            throws IOException, NotLogged {
        ensure();
        String body = null;
        for (int attempt = 0; attempt < 3; attempt++) {
            Resp r = req(path, form, timeoutSec);
            if (dead(r.body)) {
                logged = false;
                pwdCache.clear();
                if (!relogin()) throw new NotLogged();
                continue;
            }
            body = r.body;
            if (attempt < 2 && "1452".equals(xmlField(body, "IF_ERRORID"))) {
                continue;   // 一次性令牌被抢，换新令牌重试
            }
            break;
        }
        if (body == null) throw new IOException("路由器校验会话令牌失败（页面过期），请重试");
        return body;
    }

    // ---------------- 终端详情 / 限速 ----------------

    private String fetchText(String path) throws IOException, NotLogged {
        ensure();
        Resp r = req(path, null, 15);
        if (r.status == 404) {
            trace("接口不存在(404) " + path);   // 404≠掉线，别把会话带死
            return "";
        }
        if (dead(r.body)) {
            trace("读数据被拒 " + path + " status=" + r.status);
            logged = false;
            pwdCache.clear();
            if (!relogin()) throw new NotLogged();
            r = req(path, null, 15);
            if (r.status == 404) {
                trace("接口不存在(404) " + path);
                return "";
            }
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

    /** 单设备详情：MAC/IP/IPv6/掩码/网关/DNS/接入端口/最近连接 + 实时速率 */
    public synchronized String deviceJson(String mac) {
        String m = mac == null ? "" : mac.trim().toUpperCase();
        if (m.isEmpty()) return "{\"ok\":false,\"error\":\"缺少 MAC 地址\"}";
        try {
            String txt = fetchText("/?_type=vueData&_tag=localnet_lan_detailinfo_lua_no_update_sess&MACAddress="
                    + enc(m) + "&_=" + System.currentTimeMillis());
            Map<String, String> d = first(groups(txt), "OBJ_LANINFO_BYMAC");
            if (d.isEmpty()) {
                trace("设备详情解析失败 " + cut(txt, 160));
                return "{\"ok\":false,\"error\":\"设备详情解析失败\",\"raw\":" + jstr(cut(txt, 200)) + "}";
            }
            // 终端列表补 IPv6 / 接入口 / 最近连接（5 秒缓存，轮询不增加请求）
            Map<String, String> c = new LinkedHashMap<String, String>();
            try {
                for (Map<String, String> x : list(clientsRaw(), "OBJ_CLIENTS_ID")) {
                    if (up(nz(x.get("MACAddress"))).equals(m)) { c = x; break; }
                }
            } catch (Exception ignored) {
            }
            Map<String, String> net = lanNet();
            boolean d1 = !nz(net.get("dns1")).isEmpty();
            boolean d2 = !nz(net.get("dns2")).isEmpty();
            String dns = (d1 ? jstr(net.get("dns1")) : "") + (d1 && d2 ? "," : "") + (d2 ? jstr(net.get("dns2")) : "");
            return "{\"ok\":true,\"mac\":" + jstr(m)
                    + ",\"ip\":" + jstr(pick(pick(d.get("IPAddress"), d.get("IPv4Addr")), nz(c.get("IPAddress"))))
                    + ",\"mask\":" + jstr(nz(net.get("mask")))
                    + ",\"gw\":" + jstr(pick(nz(net.get("gw")), nz(net.get("ip"))))
                    + ",\"dns\":[" + dns + "]"
                    + ",\"ipv6\":" + ipv6Arr(c)
                    + ",\"port\":" + jstr(portNameOf(nz(c.get("Interface"))))
                    + ",\"band\":" + jstr("802.11".equals(nz(c.get("InterfaceType")))
                            ? nz(bandMap().get(m)) : "")
                    + ",\"iface\":" + jstr(nz(c.get("InterfaceType")))
                    + ",\"last\":" + jstr(nz(c.get("LastConnection")))
                    + ",\"up\":" + Math.round(nzNum(d.get("UploadSpeed")))
                    + ",\"down\":" + Math.round(nzNum(d.get("DownloadSpeed")))
                    + ",\"rx\":" + Math.round(nzNum(d.get("BytesReceived")))
                    + ",\"tx\":" + Math.round(nzNum(d.get("BytesSent")))
                    + ",\"online\":" + Math.round(nzNum(d.get("OnlineTimes")))
                    + ",\"active\":" + ("1".equals(pick(d.get("Active"), "1")))
                    + ",\"type\":" + jstr(nz(d.get("DisplayedType")))
                    + ",\"vendor\":" + jstr(nz(d.get("DisplayedVendor")))
                    + ",\"ts\":" + (System.currentTimeMillis() / 1000) + "}";
        } catch (NotLogged e) {
            return "{\"ok\":false,\"logged\":false,\"error\":\"NOT_LOGGED\"}";
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":" + jstr(msg(e)) + "}";
        }
    }

    /** 全部限速规则 + 全局 QoS 开关（对外单位 Mbps） */
    // ---------- 系统状态：CPU / 内存（候选接口+字段名探测） ----------
    // 网口连接状态走 vue_eth_portname&GET_TYPE=WANSTATUS（免登录接口，登录后同样可用）
    private static final String[] SYS_SRC = {
            "/?_type=vueData&_tag=vue_home_device_data",
            "/?_type=hiddenData&_tag=vue_dev_info_data",
            "/?_type=vueData&_tag=vue_dev_info_data",
            "/?_type=hiddenData&_tag=vueinfo_data",
            "/?_type=hiddenData&_tag=vue_userif_data",
            "/?_type=vueData&_tag=vue_topo_data&Action=SET",
            "/?_type=hiddenScene&_tag=initial_info_json",
            "/?_type=vueData&_tag=homestate_data",
            "/?_type=hiddenData&_tag=vue_managdiagLed_data",
    };
    private static final String[] CPU_KEYS = {"cpurate", "cpuusage", "cpuload", "cpuutil",
            "cpupersent", "cpupercent", "cpupercentage", "cpuratio", "cpuloadrate", "cpuloadavg"};
    private static final String[] MEM_KEYS = {"memrate", "memusage", "memusedrate", "mempercent",
            "memutil", "memoryrate", "memoryusage", "memorypercent", "memuserate",
            "ramusage", "ramrate", "memratio", "memoryutil"};
    /** 字段名含这些词的（核数/总量/频率等）不是利用率，排除 */
    private static final String[] PCT_SKIP = {"total", "size", "num", "core", "count", "free",
            "max", "min", "speed", "freq", "frequence", "name", "type", "temp", "vol"};

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
        Matcher fm = Pattern.compile("<([A-Za-z0-9_]+)>([^<]*)</\\1>", Pattern.DOTALL).matcher(xml);
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

    /** 在摊平字段里挑百分比（0~100），排除核数/总量/频率等干扰字段 */
    private static Double pctPick(Map<String, String> d, String[] keys) {
        Double best = null;
        int bestExact = 2;
        for (Map.Entry<String, String> e : d.entrySet()) {
            String kl = e.getKey().toLowerCase().replace("_", "").replace("-", "");
            boolean skip = false;
            for (String s : PCT_SKIP) {
                if (kl.contains(s)) { skip = true; break; }
            }
            if (skip) continue;
            boolean hit = false;
            boolean exact = false;
            for (String k : keys) {
                if (kl.contains(k)) { hit = true; exact = kl.equals(k); break; }
            }
            if (!hit) continue;
            Double n = null;
            try {
                n = Double.valueOf(e.getValue().replace("%", "").trim());
            } catch (Exception ignored) {
            }
            if (n == null || n.doubleValue() < 0 || n.doubleValue() > 100) continue;
            int ex = exact ? 0 : 1;
            if (best == null || ex < bestExact) {
                best = n;
                bestExact = ex;
            }
        }
        return best;
    }

    private String sysCache = null;       // 10 秒轮询，别每次都探测一轮
    private long sysCacheAt = 0;
    private boolean sysCacheMiss = false;
    private String sysHitPath = null;

    /** 机身丝印 ←→ 固件端口名 对齐表（实测本机 LAN1/LAN2 与丝印相反，见 panel.py 同名说明） */
    static String portLabel(String fw) {
        String f = up(nz(fw));
        if ("ETH_WAN".equals(f) || "WAN".equals(f)) return "WAN";
        if ("LAN1".equals(f)) return "LAN2";
        if ("LAN2".equals(f)) return "LAN1";
        return nz(fw);
    }

    /** XML 的每个 Instance 摊平为一个 map（vueData 响应里 OBJ 下的实例列表） */
    private static List<Map<String, String>> xmlInstances(String xml) {
        List<Map<String, String>> out = new ArrayList<Map<String, String>>();
        Matcher im = Pattern.compile("<Instance>(.*?)</Instance>", Pattern.DOTALL).matcher(xml);
        while (im.find()) {
            List<String> names = findAll(im.group(1), "<ParaName>(.*?)</ParaName>");
            List<String> vals = findAll(im.group(1), "<ParaValue>(.*?)</ParaValue>");
            Map<String, String> row = new LinkedHashMap<String, String>();
            for (int i = 0; i < names.size() && i < vals.size(); i++)
                row.put(names.get(i).trim(), unescape(vals.get(i)).trim());
            if (!row.isEmpty()) out.add(row);
        }
        return out;
    }

    /** 官方网口状态页的速率映射：0=AUTO，1..6 → 10/100/1000/2500/5000/10000 Mbps */
    private static final String[] ETH_SPEEDS = {"AUTO", "10", "100", "1000", "2500", "5000", "10000"};

    private static String ethSpeed(String v) {
        try {
            int n = (int) Double.parseDouble(nz(v).trim());
            if (n >= 0 && n < ETH_SPEEDS.length) return ETH_SPEEDS[n];
            // 这台固件两种口径混用：编码值 0..6，或直接给 Mbps（100/1000/2500…）
            if (n == 10 || n == 100 || n == 1000 || n == 2500 || n == 5000 || n == 10000) {
                return String.valueOf(n);
            }
        } catch (Exception ignore) { }
        return "";
    }

    /** 扫对象里任意 *speed* 字段（固件字段名不同也能兜住）；skipMax 时跳过最高速率 */
    private static String speedAny(Map<String, String> m, boolean skipMax) {
        if (m == null) return "";
        for (Map.Entry<String, String> e : m.entrySet()) {
            String k = up(nz(e.getKey()));
            if (!k.contains("SPEED")) continue;
            if (skipMax && k.contains("MAX")) continue;
            String s = ethSpeed(e.getValue());
            if (!s.isEmpty() && !"AUTO".equals(s)) return s;
        }
        return "";
    }

    private static Map<String, String> asStrMap(Map<String, Object> m) {
        Map<String, String> out = new LinkedHashMap<String, String>();
        for (Map.Entry<String, Object> e : m.entrySet()) out.put(e.getKey(), nz(str(e.getValue())));
        return out;
    }

    /** 登录后读 vue_internet_ethport_data（官方网口状态页同款），返回 {_InstID: map}；失败返回空 */
    private Map<String, Map<String, String>> ethportSpeed() {
        Map<String, Map<String, String>> out = new LinkedHashMap<String, Map<String, String>>();
        try {
            Resp r = req("/?_type=vueData&_tag=vue_internet_ethport_data", null, 8);
            if (r.status == 200 && r.body != null) {
                for (Map<String, String> m : xmlInstances(r.body)) {
                    if (!m.containsKey("EthPortStatus")) continue;
                    String inst = nz(str(m.get("_InstID")));
                    if (inst.isEmpty()) continue;
                    Map<String, String> row = new LinkedHashMap<String, String>();
                    row.put("speed", ethSpeed(str(m.get("EthPortSpeed"))));
                    row.put("max", ethSpeed(str(m.get("EthPortMaxSpeed"))));
                    row.put("up", nz(str(m.get("EthPortSendRate"))));
                    row.put("down", nz(str(m.get("EthPortRecvRate"))));
                    out.put(inst, row);
                }
            }
        } catch (Exception ignore) { }
        return out;
    }

    /** 每口标称速率能力（initial_info_json.DeviceSummary，免登录可读）：
     *  "W-2.5-WAN,E-2.5-LAN1,E-1-LAN2,E-1-LAN3" → {WAN:2500, LAN1:2500, LAN2:1000, LAN3:1000} */
    private Map<String, String> portCaps() {
        Map<String, String> out = new LinkedHashMap<String, String>();
        try {
            String body = fetchText("/?_type=hiddenScene&_tag=initial_info_json");
            Matcher mm = Pattern.compile("\"DeviceSummary\"\\s*:\\s*\"([^\"]+)\"").matcher(nz(body));
            if (mm.find()) {
                for (String tok : mm.group(1).split(",")) {
                    String[] parts = tok.trim().split("-");
                    if (parts.length != 3) continue;
                    try {
                        int mbps = (int) Math.round(Double.parseDouble(parts[1]) * 1000);
                        if (mbps > 0) out.put(up(parts[2]), String.valueOf(mbps));
                    } catch (Exception ignore) { }
                }
            }
        } catch (Exception ignore) { }
        return out;
    }

    /** 网口列表：名称/固件别名/接口名/WAN/连线标志/设备数 */
    private List<Map<String, String>> portList() throws IOException {
        List<Map<String, String>> out = new ArrayList<Map<String, String>>();
        Resp r = req("/?_type=vuejsonData&_tag=vue_eth_portname&GET_TYPE=WANSTATUS", null, 8);
        if (r.status != 200 || r.body == null) return out;
        Map<String, Object> doc = asMap(MiniJson.parse(r.body));
        Map<String, Object> data = asMap(doc.get("data"));
        if (data.isEmpty()) data = doc;
        Map<String, Map<String, String>> stMap = new LinkedHashMap<String, Map<String, String>>();
        for (Object x : jlist(data.get("OBJ_ETHPORT_STATE_ID"))) {
            Map<String, Object> m = asMap(x);
            Map<String, String> row = new LinkedHashMap<String, String>();
            for (Map.Entry<String, Object> en : m.entrySet()) {
                row.put(en.getKey(), nz(str(en.getValue())));
            }
            stMap.put(nz(str(m.get("_InstID"))), row);
        }
        Map<String, Map<String, String>> spd = ethportSpeed();
        java.util.TreeMap<String, Map<String, String>> sorted =
                new java.util.TreeMap<String, Map<String, String>>();
        Map<String, String> caps = portCaps();   // 每口标称速率，一次取回全列表共用
        for (Object x : jlist(data.get("OBJ_ETHPORT_INFO_ID"))) {
            Map<String, Object> m = asMap(x);
            String alias = nz(str(m.get("EthPortAliasName")));
            String ifn = nz(str(m.get("ETHPortIFName")));
            // WanType：1=WAN1（机身 WAN 口）、2=WAN2（被切成第二个 WAN 的 LAN 口）、-1=普通 LAN
            int wanType = -1;
            try { wanType = (int) Double.parseDouble(nz(str(m.get("WanType")))); } catch (Exception ignore) { }
            boolean wan = wanType == 1 || up(alias).startsWith("ETH_WAN");
            String fw = wan ? "WAN" : (alias.isEmpty() ? ifn : alias);
            String name = wan ? "WAN" : portLabel(fw);
            String stv = stMap.containsKey(nz(str(m.get("_InstID"))))
                    ? nz(str(stMap.get(nz(str(m.get("_InstID")))).get("EthPortStatus"))) : "";
            int ord = wan ? 0 : 99;
            Matcher nm = Pattern.compile("(\\d+)$").matcher(name);
            if (nm.find()) ord = Integer.parseInt(nm.group(1));
            Map<String, String> p = new LinkedHashMap<String, String>();
            p.put("name", name);
            p.put("fw", fw);
            p.put("if", ifn);
            p.put("wan", wan ? "1" : "0");
            p.put("wanType", String.valueOf(wanType));
            // 官方口径（chunks/3.js 网口状态页）：EthPortStatus 1=未连接，0=已连接
            boolean known = stv != null && !stv.isEmpty();
            p.put("link", known && "0".equals(stv) ? "1" : "0");
            p.put("linkKnown", known ? "1" : "0");
            p.put("has", "1");
            p.put("devs", "0");
            Map<String, String> srow = spd.get(nz(str(m.get("_InstID"))));
            // 速率兜底链：ethport_data → 同一份 WANSTATUS 响应里的 INFO / STATE 字段。
            // 这台固件 ethport_data 的 EthPortSpeed 常报 0(AUTO)，但 INFO 里带着真实值
            String inst = nz(str(m.get("_InstID")));
            Map<String, String> sItem = stMap.get(inst);
            Map<String, String> infoStr = asStrMap(m);
            String spdVal = srow == null ? "" : nz(srow.get("speed"));
            String maxVal = srow == null ? "" : nz(srow.get("max"));
            if (spdVal.isEmpty() || "AUTO".equals(spdVal)) {
                spdVal = firstSpeed(nz(str(m.get("EthPortSpeed"))),
                        sItem == null ? "" : nz(sItem.get("EthPortSpeed")));
                if (spdVal.isEmpty()) spdVal = speedAny(infoStr, true);
                if (spdVal.isEmpty() && sItem != null) spdVal = speedAny(sItem, true);
            }
            if (maxVal.isEmpty() || "AUTO".equals(maxVal)) {
                maxVal = firstSpeed(nz(str(m.get("EthPortMaxSpeed"))),
                        sItem == null ? "" : nz(sItem.get("EthPortMaxSpeed")));
                if (maxVal.isEmpty()) maxVal = speedAny(infoStr, false);
                if (maxVal.isEmpty() && sItem != null) maxVal = speedAny(sItem, false);
            }
            if ((maxVal.isEmpty() || "AUTO".equals(maxVal)) && !spdVal.isEmpty()) maxVal = spdVal;
            // 最后兜一层：口的标称速率能力（initial_info_json.DeviceSummary）。
            // 官方 App 网口状态页显示的 LAN「1000Mbps」就是这份数据——这台固件
            // 的 Web 接口里找不到任何 LAN 协商速率字段（诊断输出已确认）。
            if (maxVal.isEmpty() || "AUTO".equals(maxVal)) {
                // DeviceSummary 用的是机身丝印名，优先按校正后的 name 对齐
                String cap = caps.get(up(name));
                if (cap == null || cap.isEmpty()) cap = caps.get(up(fw));
                if (cap != null && !cap.isEmpty()) maxVal = cap;
            }
            if (srow != null) p.putAll(srow);
            if (!spdVal.isEmpty()) p.put("speed", spdVal);
            if (!maxVal.isEmpty()) p.put("max", maxVal);
            sorted.put(String.format(Locale.US, "%02d-%s", ord, name), p);
        }
        // WAN 口最后兜一层：首页 WANSpeed（与「连接详情 → 协商速率」同源）
        String wanHint = null;
        for (Map<String, String> prow : sorted.values()) {
            if (!"1".equals(nz(prow.get("wan")))) continue;
            String cur = nz(prow.get("speed"));
            if (!cur.isEmpty() && !"AUTO".equals(cur)) break;
            if (wanHint == null) wanHint = wanSpeedHint();
            if (!wanHint.isEmpty()) prow.put("speed", wanHint);
            break;
        }
        out.addAll(sorted.values());
        return out;
    }

    /** 从两个候选值里取第一个有效速率（0/AUTO 视为无效） */
    private static String firstSpeed(String a, String b) {
        String s = ethSpeed(a);
        if (!s.isEmpty() && !"AUTO".equals(s)) return s;
        s = ethSpeed(b);
        return (!s.isEmpty() && !"AUTO".equals(s)) ? s : "";
    }

    /** WAN 口协商速率兜底：首页 WANSpeed（「连接详情」卡用的就是它） */
    private String wanSpeedHint() {
        try {
            Map<String, String> basic = first(
                    fetch("/?_type=vueData&_tag=vue_home_device_data"), "OBJ_HOME_BASICINFO_ID");
            String v = nz(basic.get("WANSpeed"));
            if (v.isEmpty()) return "";
            try {
                return String.valueOf((int) Double.parseDouble(v));
            } catch (Exception ignore) {
                return v;
            }
        } catch (Exception e) {
            return "";
        }
    }

    /** 网口字段诊断：这台固件对每个口到底上报了哪些字段（速率读不到时排查用） */
    public synchronized String portsRawJson() {
        try {
            Resp r = req("/?_type=vuejsonData&_tag=vue_eth_portname&GET_TYPE=WANSTATUS", null, 8);
            Map<String, Object> doc = (r.body == null || r.body.isEmpty())
                    ? new LinkedHashMap<String, Object>() : asMap(MiniJson.parse(r.body));
            Map<String, Object> data = asMap(doc.get("data"));
            if (data.isEmpty()) data = doc;
            StringBuilder sb = new StringBuilder("{\"ok\":true,\"info\":");
            sb.append(briefList(data.get("OBJ_ETHPORT_INFO_ID")));
            sb.append(",\"state\":").append(briefList(data.get("OBJ_ETHPORT_STATE_ID")));
            sb.append(",\"ethport\":{");
            boolean first = true;
            for (Map.Entry<String, Map<String, String>> e : ethportSpeed().entrySet()) {
                if (!first) sb.append(',');
                first = false;
                sb.append(jstr(e.getKey())).append(":{");
                boolean f2 = true;
                for (Map.Entry<String, String> kv : e.getValue().entrySet()) {
                    if (!f2) sb.append(',');
                    f2 = false;
                    sb.append(jstr(kv.getKey())).append(':').append(jstr(nz(kv.getValue())));
                }
                sb.append('}');
            }
            sb.append("},\"caps\":{");
            boolean fc = true;
            for (Map.Entry<String, String> e : portCaps().entrySet()) {
                if (!fc) sb.append(',');
                fc = false;
                sb.append(jstr(e.getKey())).append(':').append(jstr(e.getValue()));
            }
            sb.append("},\"wanSpeed\":").append(jstr(wanSpeedHint())).append('}');
            return sb.toString();
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":" + jstr(msg(e)) + "}";
        }
    }

    /** 把一组对象压成 JSON：只留短字段，方便在手机上直接看 */
    private static String briefList(Object arr) {
        StringBuilder sb = new StringBuilder("[");
        for (Object x : jlist(arr)) {
            Map<String, Object> m = asMap(x);
            if (sb.length() > 1) sb.append(',');
            sb.append('{');
            boolean first = true;
            for (Map.Entry<String, Object> e : m.entrySet()) {
                String v = nz(str(e.getValue()));
                if (v.length() > 24) continue;
                if (!first) sb.append(',');
                sb.append(jstr(e.getKey())).append(':').append(jstr(v));
                first = false;
            }
            sb.append('}');
        }
        return sb.append(']').toString();
    }

    /** 这台有线设备是否接在这个网口上：优先用 Interface（eth1/eth2/eth3）精确匹配 */
    private static boolean onPort(Map<String, String> c, Map<String, String> port) {
        String pif = up(nz(port.get("if")));
        String cif = up(nz(c.get("port")));
        if (!cif.isEmpty() && !pif.isEmpty()) return cif.equals(pif);
        String s = up(nz(c.get("iface")));
        if (s.isEmpty() || s.contains("802.11") || s.contains("WLAN") || s.contains("WIFI")) return false;
        String nm = up(nz(port.get("name")));
        String fw = up(nz(port.get("fw")));
        if (!nm.isEmpty() && s.contains(nm)) return true;
        if (!fw.isEmpty() && s.contains(fw)) return true;
        return !pif.isEmpty() && s.contains(pif);
    }

    private String clientCache = null;       // 终端列表 5 秒缓存（设备详情 3 秒轮询共用）
    private long clientCacheAt = 0;

    private Map<String, List<Map<String, String>>> clientsRaw() throws IOException, NotLogged {
        long now = System.currentTimeMillis();
        if (clientCache != null && now - clientCacheAt < 5000) return groups(clientCache);
        String txt = fetchText("/?_type=vueData&_tag=vue_client_data&_=" + now);
        clientCache = txt;
        clientCacheAt = now;
        return groups(txt);
    }

    /** MAC → 2.4G / 5G（localnet_lan_info_lua 的 Band：1=2.4G，2=5G），20 秒缓存 */
    private String bandCache = null;
    private long bandCacheAt = 0;

    private Map<String, String> bandMap() {
        long now = System.currentTimeMillis();
        if (bandCache != null && now - bandCacheAt < 20000) return parseBands(bandCache);
        try {
            String txt = fetchText("/?_type=vueData&_tag=localnet_lan_info_lua&_=" + now);
            bandCache = txt;
            bandCacheAt = now;
            return parseBands(txt);
        } catch (Exception e) {
            return new LinkedHashMap<String, String>();
        }
    }

    private static Map<String, String> parseBands(String txt) {
        Map<String, String> out = new LinkedHashMap<String, String>();
        try {
            for (List<Map<String, String>> items : groups(txt).values()) {
                for (Map<String, String> it : items) {
                    String mac = up(nz(it.get("MACAddress")));
                    String band = nz(it.get("Band")).trim();
                    if (!mac.isEmpty() && ("1".equals(band) || "2".equals(band))) {
                        out.put(mac, "1".equals(band) ? "2.4G" : "5G");
                    }
                }
            }
        } catch (Exception ignored) {
        }
        return out;
    }

    /** 路由器这边的局域网参数（掩码/网关/DNS/DHCP 池），失败返回空 map */
    private Map<String, String> lanNet() {
        try {
            Map<String, List<Map<String, String>>> g =
                    groups(fetchText("/?_type=vueData&_tag=addr_manager_data&_=" + System.currentTimeMillis()));
            Map<String, String> br = first(g, "OBJ_BRGRP_ID");
            Map<String, String> dh = first(g, "OBJ_DHCPHOST_ID");
            Map<String, String> o = new LinkedHashMap<String, String>();
            o.put("ip", pick(nz(br.get("IPAddr")), nz(dh.get("IPRouters"))));
            o.put("mask", nz(br.get("SubMask")));
            o.put("gw", pick(nz(dh.get("IPRouters")), nz(br.get("IPAddr"))));
            o.put("dns1", nz(dh.get("DNSServer1")));
            o.put("dns2", nz(dh.get("DNSServer2")));
            o.put("min", nz(dh.get("MinAddress")));
            o.put("max", nz(dh.get("MaxAddress")));
            return o;
        } catch (Exception e) {
            return new LinkedHashMap<String, String>();
        }
    }

    /** 终端拿到的 IPv6 地址数组：全局地址排前面，去掉 :: 和重复项，最多 3 个 */
    private static String ipv6Arr(Map<String, String> c) {
        String raw = nz(c.get("IPV6Addr")) + ";" + nz(c.get("IPV6GuaAddr"));
        List<String> out = new ArrayList<String>();
        for (String x : raw.split("[;,]")) {
            String s = x.trim();
            if (s.isEmpty() || s.equals("::") || out.contains(s)) continue;
            out.add(s);
        }
        java.util.Collections.sort(out, new java.util.Comparator<String>() {
            public int compare(String a, String b) {
                boolean x = a.toLowerCase().startsWith("fe80"), y = b.toLowerCase().startsWith("fe80");
                if (x != y) return x ? 1 : -1;
                return Integer.compare(a.length(), b.length());
            }
        });
        if (out.size() > 3) out = out.subList(0, 3);
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < out.size(); i++) {
            if (i > 0) sb.append(',');
            sb.append(jstr(out.get(i)));
        }
        return sb.append(']').toString();
    }

    /** eth2 → 机身丝印 LAN1（查网口表，失败就原样返回接口名） */
    private String portNameOf(String ifn) {
        String w = nz(ifn).trim();
        if (w.isEmpty()) return "";
        try {
            for (Map<String, String> p : portList()) {
                if (nz(p.get("if")).equalsIgnoreCase(w)) return nz(p.get("name"));
            }
        } catch (Exception ignored) {
        }
        return w;
    }

    /** 有线设备（排除无线） */
    private List<Map<String, String>> wiredClients() throws IOException, NotLogged {
        Map<String, List<Map<String, String>>> cl = clientsRaw();
        List<Map<String, String>> out = new ArrayList<Map<String, String>>();
        for (Map<String, String> c : list(cl, "OBJ_CLIENTS_ID")) {
            String iface = nz(c.get("InterfaceType"));
            if (iface.contains("802.11")) continue;
            Map<String, String> x = new LinkedHashMap<String, String>();
            String nm = nz(c.get("HostName"));
            x.put("name", nm.isEmpty() ? "未知设备" : nm);
            x.put("alias", nz(c.get("AliasName")));
            x.put("ip", nz(c.get("IPAddress")));
            x.put("mac", nz(c.get("MACAddress")));
            x.put("iface", iface);
            x.put("port", nz(c.get("Interface")));   // eth1/eth2/eth3：真正接在哪个口
            x.put("last", nz(c.get("LastConnection")));
            x.put("up", nz(c.get("UpRate")));
            x.put("down", nz(c.get("DownRate")));
            x.put("online", fmtDur(c.get("OnlineDuration")));
            out.add(x);
        }
        return out;
    }

    private static String clientJson(Map<String, String> c, String portName) {
        return "{\"name\":" + jstr(c.get("name")) + ",\"alias\":" + jstr(c.get("alias"))
                + ",\"ip\":" + jstr(c.get("ip")) + ",\"mac\":" + jstr(c.get("mac"))
                + ",\"iface\":" + jstr(c.get("iface")) + ",\"portName\":" + jstr(portName)
                + ",\"ipv6\":" + ipv6Arr(c) + ",\"last\":" + jstr(c.get("last"))
                + ",\"up\":" + jstr(c.get("up"))
                + ",\"down\":" + jstr(c.get("down")) + ",\"online\":" + jstr(c.get("online")) + "}";
    }

    /** 网口详情：WAN 口返回连接的网络，LAN 口返回接在上面的有线设备 */
    public synchronized String portJson(String name) {
        try {
            String want = nz(name).trim().toUpperCase();
            List<Map<String, String>> ports = portList();
            Map<String, String> port = null;
            for (Map<String, String> p : ports) {
                if (want.equals(nz(p.get("name")).toUpperCase())) { port = p; break; }
            }
            if (port == null) return "{\"ok\":false,\"error\":\"没有这个网口\"}";
            boolean link = "1".equals(port.get("link"));

            if ("1".equals(port.get("wan"))) {
                Map<String, List<Map<String, String>>> home =
                        fetch("/?_type=vueData&_tag=vue_home_device_data");
                Map<String, String> basic = first(home, "OBJ_HOME_BASICINFO_ID");
                // 连线用网口的官方口径（EthPortStatus），联网状态文案用 WANStatus
                String wanSpd = nz(port.get("speed")), wanMax = nz(port.get("max"));
                Map<String, List<Map<String, String>>> net =
                        fetch("/?_type=vueData&_tag=vue_internet_data");
                Map<String, String> w = first(net, "OBJ_ETHWANCPPP_ID");
                String ip = nz(w.get("IPAddress"));
                boolean priv = ip.startsWith("10.") || ip.startsWith("192.168.")
                        || ip.startsWith("172.16.") || ip.startsWith("172.17.")
                        || ip.startsWith("172.18.") || ip.startsWith("172.19.")
                        || ip.startsWith("172.2") || ip.startsWith("172.30.")
                        || ip.startsWith("172.31.");
                return "{\"ok\":true,\"name\":" + jstr(port.get("name")) + ",\"link\":" + link
                        + ",\"wan\":true"
                        + ",\"speed\":" + jstr(wanSpd) + ",\"max\":" + jstr(wanMax)
                        + ",\"net\":{"
                        + "\"status\":" + jstr(nz(basic.get("WANStatus")))
                        + ",\"type\":" + jstr(nz(w.get("WANCName")))
                        + ",\"conn\":" + jstr(nz(w.get("ConnType")))
                        + ",\"ip\":" + jstr(ip)
                        + ",\"mask\":" + jstr(nz(w.get("SubnetMask")))
                        + ",\"gw\":" + jstr(pick(nz(w.get("DefaultGateway")), nz(basic.get("DefaultGateway"))))
                        + ",\"dns\":" + jstr(pick(nz(w.get("DNSServers")), nz(w.get("DNS"))))
                        + ",\"user\":" + jstr(nz(w.get("UserName")))
                        + ",\"speed\":" + jstr(!wanSpd.isEmpty() ? wanSpd : nz(basic.get("WANSpeed")))
                        + ",\"uptime\":" + jstr(fmtDur(w.get("UpTime")))
                        + ",\"up\":" + jstr(nz(basic.get("WANUpRate")))
                        + ",\"down\":" + jstr(nz(basic.get("WANDownRate")))
                        + ",\"private\":" + priv
                        + "},\"clients\":[]}";
            }

            List<Map<String, String>> wired = wiredClients();
            boolean known = false;
            for (Map<String, String> p : ports) {
                for (Map<String, String> c : wired) {
                    if (onPort(c, p)) { known = true; break; }
                }
                if (known) break;
            }
            StringBuilder arr = new StringBuilder("[");
            int n = 0;
            for (Map<String, String> c : wired) {
                if (known && !onPort(c, port)) continue;
                if (n++ > 0) arr.append(',');
                arr.append(clientJson(c, known ? nz(port.get("name")) : portNameOf(c.get("port"))));
            }
            arr.append(']');
            // 连线状态优先用官方口径（EthPortStatus）；没有该数据时退回“有设备即连接”
            boolean knownLink = "1".equals(port.get("linkKnown"));
            link = knownLink ? "1".equals(port.get("link")) : n > 0;
            Map<String, String> net = lanNet();
            StringBuilder nb = new StringBuilder(",\"net\":{\"ip\":").append(jstr(nz(net.get("ip"))))
                    .append(",\"mask\":").append(jstr(nz(net.get("mask"))))
                    .append(",\"gw\":").append(jstr(pick(nz(net.get("gw")), nz(net.get("ip")))))
                    .append(",\"dns\":[");
            boolean d1 = !nz(net.get("dns1")).isEmpty();
            nb.append(d1 ? jstr(net.get("dns1")) : "");
            if (d1 && !nz(net.get("dns2")).isEmpty()) nb.append(',');
            nb.append(nz(net.get("dns2")).isEmpty() ? "" : jstr(net.get("dns2")))
                    .append("],\"min\":").append(jstr(nz(net.get("min"))))
                    .append(",\"max\":").append(jstr(nz(net.get("max")))).append('}');
            return "{\"ok\":true,\"name\":" + jstr(port.get("name")) + ",\"link\":" + link
                    + ",\"wan\":false"
                    + ",\"speed\":" + jstr(nz(port.get("speed"))) + ",\"max\":" + jstr(nz(port.get("max")))
                    + ",\"exact\":" + known + ",\"wiredTotal\":" + wired.size()
                    + ",\"clients\":" + arr + nb + "}";
        } catch (NotLogged e) {
            return "{\"ok\":false,\"logged\":false,\"error\":\"NOT_LOGGED\"}";
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":" + jstr(msg(e)) + "}";
        }
    }

    /** 概览系统状态：每个网口的连线情况 + CPU 负载 / 内存占用（尽力探测） */
    /** 外网实时计数器：只打一次 home_device_data，给前端 1 秒轮询（别用 all，太重） */
    public synchronized String netJson() {
        try {
            Map<String, String> basic =
                    first(fetch("/?_type=vueData&_tag=vue_home_device_data"), "OBJ_HOME_BASICINFO_ID");
            StringBuilder sb = new StringBuilder(200);
            sb.append("{\"ok\":true,\"status\":").append(jstr(nz(basic.get("WANStatus"))));
            sb.append(",\"up\":").append(jstr(nz(basic.get("WANUpRate"))));
            sb.append(",\"down\":").append(jstr(nz(basic.get("WANDownRate"))));
            sb.append(",\"speed\":").append(jstr(nz(basic.get("WANSpeed"))));
            sb.append(",\"ts\":").append(System.currentTimeMillis()).append('}');
            return sb.toString();
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":" + jstr(msg(e)) + "}";
        }
    }

    public synchronized String sysStatJson() {
        long now = System.currentTimeMillis();
        if (sysCache != null && now - sysCacheAt < (sysCacheMiss ? 30000 : 4000)) {
            return sysCache;
        }

        // 1) 网口：名称 + 状态。连线直接用官方口径（EthPortStatus：0=已连接、1=未连接，
        //    与官方 App「网口状态」页一致，匿名接口即可拿到）；设备归属只算“N 台”角标；
        //    WAN 口的联网文案另取 WANStatus。
        StringBuilder ports = new StringBuilder("[");
        String portErr = null;
        List<Map<String, String>> plist = new ArrayList<Map<String, String>>();
        try {
            plist = portList();
        } catch (Exception e) {
            portErr = msg(e);
        }
        if (!plist.isEmpty()) {
            try {
                Map<String, List<Map<String, String>>> cl =
                        fetch("/?_type=vueData&_tag=vue_client_data");
                List<Map<String, String>> wired = new ArrayList<Map<String, String>>();
                for (Map<String, String> c : list(cl, "OBJ_CLIENTS_ID")) {
                    String it = nz(c.get("InterfaceType"));
                    if (it.contains("802.11")) continue;
                    Map<String, String> x = new LinkedHashMap<String, String>();
                    x.put("iface", it);
                    x.put("port", nz(c.get("Interface")));
                    wired.add(x);
                }
                for (Map<String, String> p : plist) {
                    if ("1".equals(p.get("wan"))) continue;
                    int dn = 0;
                    for (Map<String, String> c : wired) {
                        if (onPort(c, p)) dn++;
                    }
                    p.put("devs", String.valueOf(dn));
                }
                Map<String, String> basic = first(
                        fetch("/?_type=vueData&_tag=vue_home_device_data"), "OBJ_HOME_BASICINFO_ID");
                String wst = up(nz(basic.get("WANStatus")));
                if (!wst.isEmpty()) {
                    for (Map<String, String> p : plist) {
                        if ("1".equals(p.get("wan"))) p.put("wanStatus", wst);
                    }
                }
            } catch (Exception ignored) {
            }
        }
        for (Map<String, String> p : plist) {
            if (ports.length() > 1) ports.append(',');
            ports.append("{\"name\":").append(jstr(p.get("name")))
                    .append(",\"if\":").append(jstr(p.get("if")))
                    .append(",\"wan\":").append("1".equals(p.get("wan")))
                    .append(",\"link\":").append("1".equals(p.get("link")))
                    .append(",\"linkKnown\":").append("1".equals(p.get("linkKnown")))
                    .append(",\"has\":").append("1".equals(p.get("has")))
                    .append(",\"devs\":").append(p.get("devs"))
                    .append(",\"speed\":").append(jstr(nz(p.get("speed"))))
                    .append(",\"max\":").append(jstr(nz(p.get("max"))))
                    .append('}');
        }
        ports.append(']');

        // 2) CPU / 内存：候选接口逐个探测，命中后记住
        String cpu = "null", mem = "null", cpuKey = "", memKey = "", src = null, reason = null;
        List<String> order = new ArrayList<String>(java.util.Arrays.asList(SYS_SRC));
        if (sysHitPath != null) {
            order.remove(sysHitPath);
            order.add(0, sysHitPath);
        }
        for (String path : order) {
            try {
                Resp r = req(path, null, 10);
                if (r.status != 200 || r.body == null || dead(r.body)) continue;
                Map<String, String> d = flatKv(r.body);
                if (d.isEmpty()) continue;
                Double c = pctPick(d, CPU_KEYS);
                Double m = pctPick(d, MEM_KEYS);
                if (c == null && m == null) continue;
                if (c != null) {
                    cpu = String.valueOf(Math.round(c.doubleValue()));
                    cpuKey = pctKey(d, CPU_KEYS);
                }
                if (m != null) {
                    mem = String.valueOf(Math.round(m.doubleValue()));
                    memKey = pctKey(d, MEM_KEYS);
                }
                src = path;
                sysHitPath = path;
                break;
            } catch (Exception ignored) {
            }
        }
        if (src == null && !logged) reason = "登录后读取";
        else if (src == null) reason = "这台固件没有在网页接口中提供 CPU/内存数据";

        StringBuilder out = new StringBuilder("{\"ok\":true,\"ports\":").append(ports)
                .append(",\"cpu\":").append(cpu).append(",\"mem\":").append(mem);
        if (!cpuKey.isEmpty()) out.append(",\"cpuKey\":").append(jstr(cpuKey));
        if (!memKey.isEmpty()) out.append(",\"memKey\":").append(jstr(memKey));
        if (src != null) out.append(",\"src\":").append(jstr(src));
        if (reason != null) out.append(",\"reason\":").append(jstr(reason));
        if (portErr != null) out.append(",\"portErr\":").append(jstr(portErr));
        sysCache = out.append('}').toString();
        sysCacheAt = now;
        sysCacheMiss = (src == null);
        return sysCache;
    }

    // ---------- WiFi 管理：信道 / 信号强度 / Wi-Fi5 兼容网络 / 定时关闭 ----------
    private static class WifiParts {
        Map<String, Map<String, String>> radios = new LinkedHashMap<String, Map<String, String>>();
        Map<String, Map<String, String>> sets = new LinkedHashMap<String, Map<String, String>>();
        Map<String, Map<String, String>> aps = new LinkedHashMap<String, Map<String, String>>();
    }

    private WifiParts wifiParts() throws IOException, NotLogged {
        WifiParts p = new WifiParts();
        for (List<Map<String, String>> items : fetch("/?_type=vueData&_tag=wifiAP_data").values()) {
            for (Map<String, String> it : items) {
                String inst = nz(it.get("_InstID")).trim();
                if (inst.startsWith("DEV.WIFI.RD")) p.radios.put(inst, it);
                if (it.containsKey("AutoChannelEnabled") || it.containsKey("Channel")) p.sets.put(inst, it);
                if (inst.startsWith("DEV.WIFI.AP")) p.aps.put(inst, it);
            }
        }
        return p;
    }

    private static String sigLevel(String pe, String tx) {
        String k = nz(pe).trim() + "_" + nz(tx).trim();
        if ("1_100%".equals(k)) return "0";
        if ("0_100%".equals(k)) return "1";
        if ("0_20%".equals(k)) return "2";
        return "0";
    }

    private static String wfResult(String txt, String okMsg) {
        String code = "SUCC";
        Matcher m = Pattern.compile("<IF_ERRORSTR>(.*?)</IF_ERRORSTR>").matcher(nz(txt));
        if (m.find()) code = m.group(1).trim();
        if (!code.isEmpty() && !"SUCC".equals(code)) {
            return "{\"ok\":false,\"error\":" + jstr("路由器拒绝：" + code) + "}";
        }
        return "{\"ok\":true,\"msg\":" + jstr(okMsg) + "}";
    }

    /** WiFi 管理页数据：每个频段信道/信号 + 兼容网络 + 定时关闭 */
    public synchronized String wifiMgrJson() {
        try {
            WifiParts p = wifiParts();
            String[][] map = {{"2.4G", "DEV.WIFI.RD1", "DEV.WIFI.AP1"}, {"5G", "DEV.WIFI.RD2", "DEV.WIFI.AP5"}};
            StringBuilder bands = new StringBuilder("[");
            for (int i = 0; i < map.length; i++) {
                String band = map[i][0], rd = map[i][1], ap = map[i][2];
                Map<String, String> s = p.sets.containsKey(rd) ? p.sets.get(rd) : new LinkedHashMap<String, String>();
                Map<String, String> r = p.radios.containsKey(rd) ? p.radios.get(rd) : new LinkedHashMap<String, String>();
                Map<String, String> a = p.aps.containsKey(ap) ? p.aps.get(ap) : new LinkedHashMap<String, String>();
                String pe = pick(nz(s.get("PowerEnhance")), nz(r.get("PowerEnhance")));
                String tx = pick(nz(s.get("TxPower")), nz(r.get("TxPower")));
                String ch = nz(s.get("Channel")).trim();
                boolean auto = "1".equals(nz(s.get("AutoChannelEnabled")).trim())
                        || ch.isEmpty() || "NULL".equalsIgnoreCase(ch) || "AUTO".equalsIgnoreCase(ch);
                if (i > 0) bands.append(',');
                bands.append("{\"band\":").append(jstr(band))
                        .append(",\"level\":").append(sigLevel(pe, tx))
                        .append(",\"pe\":").append(jstr(pe)).append(",\"tx\":").append(jstr(tx))
                        .append(",\"channel\":").append(jstr(auto ? "" : ch))
                        .append(",\"auto\":").append(auto)
                        .append(",\"inuse\":").append(jstr(nz(a.get("ChannelInUsed"))))
                        .append(",\"bw\":").append(jstr(nz(s.get("BandWidth"))))
                        .append(",\"std\":").append(jstr(nz(s.get("Standard"))))
                        .append(",\"on\":").append("1".equals(pick(pick(nz(r.get("RadioStatus")), nz(s.get("RadioStatus"))), "1")))
                        .append('}');
            }
            bands.append(']');

            StringBuilder ch24 = new StringBuilder("["), ch5 = new StringBuilder("[");
            int n24 = 0, n5 = 0;
            try {
                for (Map<String, String> it : list(fetch("/?_type=vueData&_tag=wlanConfig_data&_="
                        + System.currentTimeMillis()), "OBJ_CHANNEL_ID")) {
                    String band = nz(it.get("Band")).trim();
                    String num = pick(pick(nz(it.get("Channel")), nz(it.get("ChanNum"))), nz(it.get("ChannelNum"))).trim();
                    if (!num.matches("\\d+")) continue;
                    if ("2.4G".equals(band)) {
                        if (n24++ > 0) ch24.append(',');
                        ch24.append(jstr(num));
                    } else if ("5G".equals(band)) {
                        if (n5++ > 0) ch5.append(',');
                        ch5.append(jstr(num));
                    }
                }
            } catch (Exception ignored) {
            }
            if (n24 == 0) for (int i = 1; i <= 13; i++) { if (i > 1) ch24.append(','); ch24.append(jstr(String.valueOf(i))); }
            if (n5 == 0) {
                String[] d = {"36", "40", "44", "48", "149", "153", "157", "161", "165"};
                for (int i = 0; i < d.length; i++) { if (i > 0) ch5.append(','); ch5.append(jstr(d[i])); }
            }
            ch24.append(']');
            ch5.append(']');

            boolean force = false;
            StringBuilder cpItems = new StringBuilder("[");
            int cn = 0;
            try {
                List<Map<String, String>> arr = list(fetch("/?_type=vueData&_tag=vue_wifi_merger&_="
                        + System.currentTimeMillis()), "OBJ_WLANAP_ID");
                for (Map<String, String> it : arr) {
                    if (it.containsKey("ForceWiFi")) { force = "1".equals(nz(it.get("ForceWiFi")).trim()); break; }
                }
                String[][] wants = {{"2.4G", "AP3"}, {"5G", "AP7"}};
                for (String[] w : wants) {
                    for (Map<String, String> it : arr) {
                        if (up(nz(it.get("_InstID"))).endsWith(w[1])) {
                            if (cn++ > 0) cpItems.append(',');
                            cpItems.append("{\"band\":").append(jstr(w[0]))
                                    .append(",\"inst\":").append(jstr(nz(it.get("_InstID"))))
                                    .append(",\"ssid\":").append(jstr(nz(it.get("ESSID"))))
                                    .append(",\"on\":").append("1".equals(nz(it.get("Enable"))))
                                    .append(",\"hidden\":").append("1".equals(nz(it.get("ESSIDHideEnable")))).append('}');
                            break;
                        }
                    }
                }
            } catch (Exception ignored) {
            }
            cpItems.append(']');

            boolean tOn = false;
            String tStart = "23:00", tEnd = "07:00";
            try {
                Map<String, List<Map<String, String>>> t = groups(fetchText(
                        "/?_type=hiddenData&_tag=vue_internet_advanced_rftimer_data&_=" + System.currentTimeMillis()));
                Map<String, String> cfg = first(t, "OBJ_WLANTIMECFG_ID");
                Map<String, String> one = first(t, "OBJ_WLANTIME_ID");
                tOn = "1".equals(nz(cfg.get("TimerEnable")).trim());
                if (!nz(one.get("TimeStartHour")).isEmpty()) {
                    tStart = String.format(Locale.US, "%02d:%02d",
                            (int) nzNum(one.get("TimeStartHour")), (int) nzNum(one.get("TimeStartMin")));
                }
                if (!nz(one.get("TimeEndHour")).isEmpty()) {
                    tEnd = String.format(Locale.US, "%02d:%02d",
                            (int) nzNum(one.get("TimeEndHour")), (int) nzNum(one.get("TimeEndMin")));
                }
            } catch (Exception ignored) {
            }

            String mode = "", mesh = "0";
            try {
                Map<String, String> env = first(fetch("/?_type=vueData&_tag=vue_home_device_data"), "OBJ_GLOBAL_ENV");
                mode = nz(env.get("curWorkMode"));
                mesh = nz(env.get("MeshEnable"));
            } catch (Exception ignored) {
            }

            return "{\"ok\":true,\"bands\":" + bands
                    + ",\"channels\":{\"2.4G\":" + ch24 + ",\"5G\":" + ch5 + "}"
                    + ",\"compat\":{\"force\":" + force + ",\"items\":" + cpItems + "}"
                    + ",\"timer\":{\"on\":" + tOn + ",\"start\":" + jstr(tStart)
                    + ",\"end\":" + jstr(tEnd) + "}"
                    + ",\"mode\":" + jstr(mode) + ",\"mesh\":" + jstr(mesh) + "}";
        } catch (NotLogged e) {
            return "{\"ok\":false,\"logged\":false,\"error\":\"NOT_LOGGED\"}";
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":" + jstr(msg(e)) + "}";
        }
    }

    public synchronized String wifiMgrSetJson(String bodyJson) {
        try {
            Map<String, Object> b = asMap(MiniJson.parse(bodyJson == null ? "{}" : bodyJson));
            String action = nz(str(b.get("action"))).trim();
            if ("channel".equals(action) || "signal".equals(action)) {
                String band = nz(str(b.get("band"))).trim().toUpperCase();
                if (!"2.4G".equals(band) && !"5G".equals(band)) return "{\"ok\":false,\"error\":\"频段不对\"}";
                WifiParts p = wifiParts();
                String rd = "2.4G".equals(band) ? "DEV.WIFI.RD1" : "DEV.WIFI.RD2";
                Map<String, String> s = p.sets.get(rd);
                if (s == null) return "{\"ok\":false,\"error\":" + jstr("这台固件没有提供 " + band + " 的信道/功率配置") + "}";
                Map<String, String> r = p.radios.containsKey(rd) ? p.radios.get(rd) : new LinkedHashMap<String, String>();
                boolean auto = "1".equals(nz(s.get("AutoChannelEnabled")).trim());
                String ch = nz(s.get("Channel")).trim();
                String std = nz(s.get("Standard"));
                String bw = pick(nz(s.get("BandWidth")), "Auto");
                int level = Integer.parseInt(sigLevel(pick(nz(s.get("PowerEnhance")), nz(r.get("PowerEnhance"))),
                        pick(nz(s.get("TxPower")), nz(r.get("TxPower")))));
                if ("channel".equals(action)) {
                    Object au = b.get("auto");
                    boolean isAuto = Boolean.TRUE.equals(au) || "true".equals(String.valueOf(au));
                    if (isAuto) {
                        auto = true;
                        ch = "NULL";
                    } else {
                        String c = nz(str(b.get("channel"))).trim();
                        if (!c.matches("\\d+")) return "{\"ok\":false,\"error\":\"信道要填数字\"}";
                        auto = false;
                        ch = c;
                    }
                    String nbw = nz(str(b.get("bw"))).trim();
                    if (!nbw.isEmpty()) bw = nbw;
                } else {
                    try {
                        level = (int) Double.parseDouble(str(b.get("level")));
                    } catch (Exception e) {
                        return "{\"ok\":false,\"error\":\"信号强度取值不对\"}";
                    }
                    if (level < 0 || level > 2) return "{\"ok\":false,\"error\":\"信号强度取值不对\"}";
                }
                String[] pv = {"1", "100%", "0"};
                if (level == 1) pv = new String[]{"0", "100%", "1"};
                else if (level == 2) pv = new String[]{"0", "20%", "2"};
                LinkedHashMap<String, String> f = new LinkedHashMap<String, String>();
                f.put("IF_ACTION", "Apply");
                f.put("_InstID", rd);
                f.put("Band", pick(nz(s.get("Band")), band));
                f.put("Channel", auto ? "NULL" : ch);
                f.put("AutoChannelEnabled", auto ? "1" : "0");
                f.put("Standard", std);
                f.put("PowerEnhance", pv[0]);
                f.put("TxPower", pv[1]);
                f.put("WlanRate", pv[2]);
                f.put("RadioStatus", pick(pick(nz(s.get("RadioStatus")), nz(r.get("RadioStatus"))), "1"));
                if (!std.isEmpty() && !"b,g".equals(std)) f.put("BandWidth", bw);
                return wfResult(ax("/?_type=vueData&_tag=wlanConfig_data", f, 25),
                        band + " 已保存，Wi-Fi 会短暂中断几秒");
            }

            if ("compatpwd".equals(action)) {
                String band = nz(str(b.get("band"))).trim().toUpperCase();
                if (!"2.4G".equals(band) && !"5G".equals(band)) band = "2.4G";
                String sfx = "5G".equals(band) ? "AP7" : "AP3";
                String inst = "";
                List<Map<String, String>> arr = list(fetch("/?_type=vueData&_tag=vue_wifi_merger&_="
                        + System.currentTimeMillis()), "OBJ_WLANAP_ID");
                for (Map<String, String> it : arr) {
                    if (up(nz(it.get("_InstID"))).endsWith(sfx)) {
                        inst = nz(it.get("_InstID_PSK")).trim();
                        if (inst.isEmpty()) inst = nz(it.get("_InstID")).trim() + ".PSK1";
                        break;
                    }
                }
                if (inst.isEmpty()) {
                    return "{\"ok\":false,\"error\":" + jstr("没找到 " + band + " 兼容网络实例") + "}";
                }
                String pwd = wifiPwdInst(inst, "cp" + band);
                if (pwd.isEmpty()) {
                    return "{\"ok\":true,\"band\":" + jstr(band) + ",\"pwd\":\"\",\"hasPwd\":false"
                            + ",\"error\":" + jstr("路由器没有返回 " + band + " 兼容网络的密码") + "}";
                }
                return "{\"ok\":true,\"band\":" + jstr(band)
                        + ",\"pwd\":" + jstr(pwd) + ",\"hasPwd\":true,\"inst\":" + jstr(inst) + "}";
            }

            if ("compat".equals(action)) {
                Object fo = b.get("force");
                boolean force = Boolean.TRUE.equals(fo) || "true".equals(String.valueOf(fo));
                List<Object> items = jlist(b.get("items"));
                List<Map<String, String>> arr = list(fetch("/?_type=vueData&_tag=vue_wifi_merger&_="
                        + System.currentTimeMillis()), "OBJ_WLANAP_ID");
                String a1 = rand16(), b1 = rand16();
                LinkedHashMap<String, String> f = new LinkedHashMap<String, String>();
                f.put("IF_ACTION", "Apply");
                f.put("SubmitFlag", "SSIDIY");
                f.put("ForceWiFi", force ? "1" : "0");
                String[][] map = {{"2.4G", "I", "AP3"}, {"5G", "Y", "AP7"}};
                boolean keyed = false;
                for (String[] m : map) {
                    Map<String, Object> given = null;
                    for (Object o : items) {
                        Map<String, Object> m2 = asMap(o);
                        if (m[0].equals(nz(str(m2.get("band"))).trim())) { given = m2; break; }
                    }
                    Map<String, String> old = new LinkedHashMap<String, String>();
                    for (Map<String, String> it : arr) {
                        if (up(nz(it.get("_InstID"))).endsWith(m[2])) { old = it; break; }
                    }
                    String ssid = old.containsKey("ESSID") ? nz(old.get("ESSID")) : "";
                    boolean on = "1".equals(nz(old.get("Enable")));
                    String pwd = "";
                    boolean hidden = "1".equals(nz(old.get("ESSIDHideEnable")));
                    if (given != null) {
                        String v = nz(str(given.get("ssid"))).trim();
                        if (!v.isEmpty()) ssid = v;
                        Object ov = given.get("on");
                        on = Boolean.TRUE.equals(ov) || "true".equals(String.valueOf(ov));
                        pwd = nz(str(given.get("pwd"))).trim();
                        Object hv = given.get("hidden");
                        if (hv != null) hidden = Boolean.TRUE.equals(hv) || "true".equals(String.valueOf(hv));
                    }
                    if (!ssid.isEmpty() && (ssid.length() < 1 || ssid.length() > 32)) {
                        return "{\"ok\":false,\"error\":" + jstr(m[0] + " 兼容网络名称需为 1–32 个字符") + "}";
                    }
                    if (!pwd.isEmpty() && (pwd.length() < 8 || pwd.length() > 63)) {
                        return "{\"ok\":false,\"error\":" + jstr(m[0] + " 兼容网络密码需为 8–63 位") + "}";
                    }
                    if (on && force && pwd.isEmpty()) {
                        return "{\"ok\":false,\"error\":" + jstr(m[0] + " 兼容网络要填密码（8 位以上）才能开启") + "}";
                    }
                    f.put("ESSID" + m[1], ssid);
                    f.put("Enable" + m[1], on ? "1" : "0");
                    f.put("ESSIDHideEnable" + m[1], hidden ? "1" : "0");
                    for (String k : new String[]{"BeaconType", "WPAAuthMode", "WPAEncryptType"}) {
                        if (!nz(old.get(k)).isEmpty()) f.put(k + m[1], nz(old.get(k)));
                    }
                    if (!nz(old.get("11iAuthMode")).isEmpty()) f.put("11iAuthMode" + m[1], nz(old.get("11iAuthMode")));
                    if (!nz(old.get("11iEncryptType")).isEmpty()) f.put("11iEncryptType" + m[1], nz(old.get("11iEncryptType")));
                    if (!pwd.isEmpty()) {
                        String enc;
                        try {
                            enc = encPara(pwd, a1, b1);
                        } catch (Exception e) {
                            return "{\"ok\":false,\"error\":\"密码加密失败\"}";
                        }
                        f.put("KeyPassphrase" + m[1], enc);
                        f.put("HideKeyPassphrase" + m[1], enc);
                        f.put("_InstID_PSK" + m[1], pick(nz(old.get("_InstID")), "DEV.WIFI." + m[2]) + ".PSK1");
                        keyed = true;
                    }
                }
                if (keyed) {
                    try {
                        f.put("encode", encKey(a1, b1));
                    } catch (Exception ignored) {
                    }
                }
                return wfResult(ax("/?_type=vueData&_tag=vue_wifi_merger", f, 25), "Wi-Fi5 兼容网络已保存");
            }

            if ("timer".equals(action)) {
                Object to = b.get("on");
                boolean on = Boolean.TRUE.equals(to) || "true".equals(String.valueOf(to));
                String[] st = hmPick(str(b.get("start")), "23:00");
                String[] et = hmPick(str(b.get("end")), "07:00");
                if (st == null || et == null) return "{\"ok\":false,\"error\":\"时间要填成 23:00 这样\"}";
                LinkedHashMap<String, String> f = new LinkedHashMap<String, String>();
                f.put("TimeStartHour", st[0]);
                f.put("TimeStartMin", st[1]);
                f.put("TimeEndHour", et[0]);
                f.put("TimeEndMin", et[1]);
                f.put("TimerEnable", on ? "1" : "0");
                f.put("IF_ACTION", "Apply");
                f.put("_InstID", "");
                return wfResult(ax("/?_type=hiddenData&_tag=vue_internet_advanced_rftimer_data", f, 20),
                        "Wi-Fi 定时关闭已保存");
            }
            return "{\"ok\":false,\"error\":\"未知操作\"}";
        } catch (NotLogged e) {
            return "{\"ok\":false,\"logged\":false,\"error\":\"NOT_LOGGED\"}";
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":" + jstr(msg(e)) + "}";
        }
    }

    private static String[] hmPick(String v, String d) {
        String s = nz(v).trim().isEmpty() ? d : nz(v).trim();
        Matcher m = Pattern.compile("^(\\d{1,2}):(\\d{2})$").matcher(s);
        if (!m.find()) return null;
        int h = Integer.parseInt(m.group(1)), mi = Integer.parseInt(m.group(2));
        if (h > 23 || mi > 59) return null;
        return new String[]{String.valueOf(h), String.valueOf(mi)};
    }

    private static String pctKey(Map<String, String> d, String[] keys) {
        for (Map.Entry<String, String> e : d.entrySet()) {
            String kl = e.getKey().toLowerCase().replace("_", "").replace("-", "");
            boolean skip = false;
            for (String s : PCT_SKIP) {
                if (kl.contains(s)) { skip = true; break; }
            }
            if (skip) continue;
            for (String k : keys) {
                if (kl.equals(k)) return e.getKey();
            }
        }
        return "";
    }

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
                rules.append(jstr(mac)).append(":{\"i\":").append(jstr(nz(r.get("_InstID"))))
                        .append(",\"u\":").append(Math.round(nzNum(r.get("BandwithRateMaxUp")) / 1000.0))
                        .append(",\"d\":").append(Math.round(nzNum(r.get("BandwithRateMaxDown")) / 1000.0))
                        .append('}');
            }
            rules.append('}');
            return "{\"ok\":true,\"enable\":" + enable + ",\"rules\":" + rules + "}";
        } catch (NotLogged e) {
            return "{\"ok\":false,\"logged\":false,\"error\":\"NOT_LOGGED\"}";
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":" + jstr(msg(e)) + "}";
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
            return "{\"ok\":false,\"error\":\"参数错误\"}";
        }
        if (mac.isEmpty()) return "{\"ok\":false,\"error\":\"缺少 MAC 地址\"}";
        String path = "/?_type=vueData&_tag=localnet_qosdyn_bandwithrule_lua";
        try {
            String inst = ruleInst(mac);
            String txt;
            if (up == 0 && down == 0) {
                if (inst == null) return "{\"ok\":true,\"cleared\":true}";
                LinkedHashMap<String, String> f = new LinkedHashMap<String, String>();
                f.put("IF_ACTION", "Delete");
                f.put("_InstID", inst);
                txt = ax(path, f, 15);
                boolean ok = succ(txt);
                if (!ok) trace("取消限速失败 " + cut(txt, 200));
                return "{\"ok\":" + ok + ",\"cleared\":true,\"error\":"
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
            return "{\"ok\":" + ok + ",\"up\":" + up + ",\"down\":" + down
                    + ",\"inst\":" + jstr(inst == null ? "-1" : inst)
                    + ",\"error\":" + (ok ? "null" : jstr(pick(xmlField(txt, "IF_ERRORSTR"), "路由器拒绝了这次修改")))
                    + "}";
        } catch (NotLogged e) {
            return "{\"ok\":false,\"logged\":false,\"error\":\"NOT_LOGGED\"}";
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":" + jstr(msg(e)) + "}";
        }
    }

    private String apiAll() throws IOException, NotLogged {
        Map<String, List<Map<String, String>>> home = fetch("/?_type=vueData&_tag=vue_home_device_data");
        Map<String, String> env = first(home, "OBJ_GLOBAL_ENV");
        Map<String, String> basic = first(home, "OBJ_HOME_BASICINFO_ID");

        Map<String, List<Map<String, String>>> net = fetch("/?_type=vueData&_tag=vue_internet_data");
        Map<String, String> wan = first(net, "OBJ_ETHWANCPPP_ID");

        Map<String, List<Map<String, String>>> wifiRaw = fetch("/?_type=vueData&_tag=wifiAP_data");
        Map<String, Map<String, String>> psk = new HashMap<String, Map<String, String>>();
        for (Map<String, String> x : list(wifiRaw, "OBJ_WLANPSK_ID")) {
            psk.put(nz(x.get("_InstID_PSK")), x);
        }
        List<Map<String, String>> wifi = new ArrayList<Map<String, String>>();
        for (Map<String, String> ap : list(wifiRaw, "OBJ_WLANAP_ID")) {
            String inst = nz(ap.get("_InstID"));
            String band = bandOf(inst);
            Map<String, String> p = psk.get(inst + ".PSK1");
            if (p == null) p = psk.get(inst + ".PSK");
            if (p == null) p = new HashMap<String, String>();
            Map<String, String> w = new LinkedHashMap<String, String>();
            w.put("band", band);
            w.put("ssid", nz(ap.get("ESSID")));
            w.put("on", "1".equals(ap.get("Enable")) ? "1" : "0");
            w.put("enc", nz(ap.get("BeaconType")));
            String auth = ap.get("11iAuthMode");
            if (auth == null || auth.isEmpty()) auth = ap.get("WPAAuthMode");
            w.put("auth", nz(auth));
            w.put("max", nz(ap.get("MaxUserNum")));
            w.put("hidden", "1".equals(ap.get("ESSIDHideEnable")) ? "1" : "0");
            w.put("hasPwd", p.get("KeyPassphrase") != null && !p.get("KeyPassphrase").isEmpty() ? "1" : "0");
            wifi.add(w);
        }
        // 2.4G 排前
        List<Map<String, String>> sortedWifi = new ArrayList<Map<String, String>>();
        for (Map<String, String> w : wifi) if ("2.4G".equals(w.get("band"))) sortedWifi.add(w);
        for (Map<String, String> w : wifi) if (!"2.4G".equals(w.get("band"))) sortedWifi.add(w);

        Map<String, List<Map<String, String>>> cl = fetch("/?_type=vueData&_tag=vue_client_data");
        List<Map<String, String>> clients = new ArrayList<Map<String, String>>();
        for (Map<String, String> c : list(cl, "OBJ_CLIENTS_ID")) {
            Map<String, String> x = new LinkedHashMap<String, String>();
            String name = c.get("HostName");
            if (name == null || name.trim().isEmpty()) name = "未知设备";
            String iface = nz(c.get("InterfaceType"));
            Map<String, String> bands = bandMap();
            String macUp = up(nz(c.get("MACAddress")));
            x.put("band", iface.contains("802.11") ? nz(bands.get(macUp)) : "");
            x.put("name", name);
            x.put("alias", nz(c.get("AliasName")));
            x.put("ip", nz(c.get("IPAddress")));
            x.put("mac", nz(c.get("MACAddress")));
            x.put("iface", iface);
            x.put("port", iface.contains("802.11") ? "" : portNameOf(nz(c.get("Interface"))));
            x.put("up", nz(c.get("UpRate")));
            x.put("down", nz(c.get("DownRate")));
            x.put("online", fmtDur(c.get("OnlineDuration")));
            clients.add(x);
        }

        int wired = 0;
        for (Map<String, String> c : clients) {
            if (!nz(c.get("iface")).contains("802.11")) wired++;
        }

        StringBuilder sb = new StringBuilder(4096);
        sb.append("{\"logged\":true,\"dev\":{");
        sb.append("\"name\":").append(jstr(pick(basic.get("DevName"), pick(env.get("WEBTitle"), "中兴路由器")))).append(',');
        sb.append("\"model\":").append(jstr(nz(env.get("WEBTitle")))).append(',');
        sb.append("\"fw\":").append(jstr(nz(env.get("SoftwareVer")))).append(',');
        sb.append("\"ip\":").append(jstr(pick(basic.get("Br0IP"), host))).append(',');
        sb.append("\"mac\":").append(jstr(nz(basic.get("Br0MAC")))).append(',');
        sb.append("\"mesh\":").append("1".equals(env.get("MeshEnable")));
        sb.append("},\"wan\":{");
        sb.append("\"status\":").append(jstr(nz(basic.get("WANStatus")))).append(',');
        sb.append("\"up\":").append(jstr(nz(basic.get("WANUpRate")))).append(',');
        sb.append("\"down\":").append(jstr(nz(basic.get("WANDownRate")))).append(',');
        sb.append("\"speed\":").append(jstr(nz(basic.get("WANSpeed")))).append(',');
        sb.append("\"ip\":").append(jstr(nz(wan.get("IPAddress")))).append(',');
        sb.append("\"uptime\":").append(jstr(fmtDur(wan.get("UpTime")))).append(',');
        sb.append("\"user\":").append(jstr(nz(wan.get("UserName")))).append(',');
        sb.append("\"type\":").append(jstr(nz(wan.get("WANCName")))).append(',');
        sb.append("\"conn\":").append(jstr(nz(wan.get("ConnType"))));
        sb.append("},\"wifi\":[");
        for (int i = 0; i < sortedWifi.size(); i++) {
            Map<String, String> w = sortedWifi.get(i);
            if (i > 0) sb.append(',');
            sb.append("{\"band\":").append(jstr(w.get("band")));
            sb.append(",\"ssid\":").append(jstr(w.get("ssid")));
            sb.append(",\"on\":").append("1".equals(w.get("on")));
            sb.append(",\"enc\":").append(jstr(w.get("enc")));
            sb.append(",\"auth\":").append(jstr(w.get("auth")));
            sb.append(",\"max\":").append(jstr(w.get("max")));
            sb.append(",\"hidden\":").append("1".equals(w.get("hidden")));
            sb.append(",\"hasPwd\":").append("1".equals(w.get("hasPwd")));
            sb.append('}');
        }
        sb.append("],\"clients\":[");
        for (int i = 0; i < clients.size(); i++) {
            Map<String, String> c = clients.get(i);
            if (i > 0) sb.append(',');
            sb.append("{\"name\":").append(jstr(c.get("name")));
            sb.append(",\"alias\":").append(jstr(c.get("alias")));
            sb.append(",\"ip\":").append(jstr(c.get("ip")));
            sb.append(",\"mac\":").append(jstr(c.get("mac")));
            sb.append(",\"iface\":").append(jstr(c.get("iface")));
            sb.append(",\"port\":").append(jstr(c.get("port")));
            sb.append(",\"band\":").append(jstr(c.get("band")));
            sb.append(",\"up\":").append(jstr(c.get("up")));
            sb.append(",\"down\":").append(jstr(c.get("down")));
            sb.append(",\"online\":").append(jstr(c.get("online")));
            sb.append('}');
        }
        sb.append("],\"count\":").append(jstr(pick(basic.get("AccessDevNum"), String.valueOf(clients.size()))));
        sb.append(",\"wired\":").append(wired);
        sb.append(",\"wireless\":").append(clients.size() - wired);
        sb.append(",\"ts\":").append(System.currentTimeMillis() / 1000);
        sb.append('}');
        return sb.toString();
    }

    private String wifiPwd(String band) throws IOException, NotLogged {
        return wifiPwdInst("5G".equals(band) ? "DEV.WIFI.AP5.PSK1" : "DEV.WIFI.AP1.PSK1", band);
    }

    /** 按 PSK 实例读密码：主 SSID 是 AP1/AP5，兼容网络是 AP3/AP7 */
    private String wifiPwdInst(String inst, String cacheKey) throws IOException, NotLogged {
        ensure();
        if (pwdCache.containsKey(cacheKey)) return pwdCache.get(cacheKey);
        String body = null;
        String usedTok = "";
        for (int attempt = 0; attempt < 2; attempt++) {
            sleep(320);                       // 路由器对连续读密码敏感
            usedTok = token == null ? "" : token;   // 必须用发请求那一刻的令牌解密
            LinkedHashMap<String, String> f = new LinkedHashMap<String, String>();
            f.put("IF_ACTION", "GetPassword");
            f.put("ACTION_TYPE", "wlanPassword");
            f.put("_InstID_PASS", inst);
            f.put("PASSTYPE", "PSK");
            f.put("_sessionTOKEN", usedTok);
            Resp r = req("/?_type=vueData&_tag=vuecfg_data", f, 15);
            if (!dead(r.body)) {
                body = r.body;
                break;
            }
            logged = false;
            pwdCache.clear();
            if (attempt == 0 && relogin()) continue;
            throw new NotLogged();
        }
        Map<String, String> item = null;
        for (Map<String, String> it : list(groups(body), "OBJ_WLANPSK_ID")) {
            if (inst.equals(it.get("_InstID")) || inst.equals(it.get("_InstID_PSK"))
                    || inst.equals(it.get("_InstID_PASS"))) {
                item = it;
                break;
            }
        }
        if (item == null) {
            List<Map<String, String>> all = list(groups(body), "OBJ_WLANPSK_ID");
            if (all.size() == 1) item = all.get(0);
        }
        String raw = item == null ? null : item.get("KeyPassphrase");
        if (raw == null || raw.isEmpty()) {
            pwdCache.put(cacheKey, "");
            return "";
        }
        String pwd;
        try {
            pwd = decPara(raw, usedTok, reverse(usedTok));
        } catch (Exception e) {
            throw new IOException("密码解密失败，请重新登录后再试");
        }
        for (int i = 0; i < pwd.length(); i++) {
            char ch = pwd.charAt(i);
            if (ch < 32 || ch > 126) throw new IOException("密码解密失败（会话令牌不匹配），请重新登录");
        }
        pwdCache.put(cacheKey, pwd);
        return pwd;
    }

    private void setWifi(Map<String, Object> body) throws IOException, NotLogged {
        ensure();
        Map<String, List<Map<String, String>>> raw = fetch("/?_type=vueData&_tag=wifiAP_data");
        Map<String, String> env = first(raw, "OBJ_GLOBAL_ENV");
        Map<String, Map<String, String>> aps = new HashMap<String, Map<String, String>>();
        for (Map<String, String> a : list(raw, "OBJ_WLANAP_ID")) aps.put(nz(a.get("_InstID")), a);
        Map<String, Map<String, String>> setting = new HashMap<String, Map<String, String>>();
        for (Map<String, String> s : list(raw, "OBJ_WLANSETTING_ID")) setting.put(nz(s.get("_InstID")), s);
        Map<String, String> mlo = first(raw, "OBJ_MLO_ID");
        Map<String, String> dual = first(raw, "OBJ_DUALBANDSYNC_ID");

        Map<String, String> ap1 = aps.get("DEV.WIFI.AP1");
        Map<String, String> ap5 = aps.get("DEV.WIFI.AP5");
        if (ap1 == null || ap5 == null) throw new IOException("没有读到无线配置");

        String cur1 = wifiPwd("2.4G");
        String cur5 = wifiPwd("5G");

        Map<String, Object> b1 = asMap(body.get("2.4G"));
        Map<String, Object> b5 = asMap(body.get("5G"));

        String essid1 = pick(str(b1.get("ssid")), nz(ap1.get("ESSID"))).trim();
        String essid5 = pick(str(b5.get("ssid")), nz(ap5.get("ESSID"))).trim();
        String pwd1 = pick(str(b1.get("pwd")), cur1);
        String pwd5 = pick(str(b5.get("pwd")), cur5);
        boolean on1 = b1.containsKey("on") ? isTrue(b1.get("on")) : "1".equals(ap1.get("Enable"));
        boolean on5 = b5.containsKey("on") ? isTrue(b5.get("on")) : "1".equals(ap5.get("Enable"));

        if ((pwd1 == null || pwd1.isEmpty()) && on1)
            throw new IOException("读不到 2.4G 当前密码，请手动填写后保存（不允许留空）");
        if ((pwd5 == null || pwd5.isEmpty()) && on5)
            throw new IOException("读不到 5G 当前密码，请手动填写后保存（不允许留空）");

        if (essid1.length() < 1 || essid1.length() > 32) throw new IOException("2.4G 名称需为 1–32 个字符");
        if (essid5.length() < 1 || essid5.length() > 32) throw new IOException("5G 名称需为 1–32 个字符");
        if (!pwd1.isEmpty() && (pwd1.length() < 8 || pwd1.length() > 63)) throw new IOException("2.4G 密码需为 8–63 位");
        if (!pwd5.isEmpty() && (pwd5.length() < 8 || pwd5.length() > 63)) throw new IOException("5G 密码需为 8–63 位");
        if (!allAscii(pwd1)) throw new IOException("2.4G 密码只能用英文字母、数字和英文符号");
        if (!allAscii(pwd5)) throw new IOException("5G 密码只能用英文字母、数字和英文符号");

        String a = rand16();
        String b = rand16();
        String e1, e5, ek;
        try {
            e1 = encPara(pwd1, a, b);
            e5 = encPara(pwd5, a, b);
            ek = encKey(a, b);
        } catch (Exception ex) {
            throw new IOException("密码加密失败：" + msg(ex));
        }

        LinkedHashMap<String, String> form = new LinkedHashMap<String, String>();
        form.put("IF_ACTION", "Apply");
        form.put("DualBandSync", pick(nz(dual.get("DualBandSync")), "0"));
        form.put("Enable1", on1 ? "1" : "0");
        form.put("ESSID1", essid1);
        form.put("_InstID1", "DEV.WIFI.AP1");
        form.put("_WLANCONIG1", "Y");
        form.put("_WEPCONIG1", "N");
        form.put("_PSKCONIG1", "Y");
        form.put("KeyPassphrase1", e1);
        form.put("WEPKey1", e1);
        form.put("_InstID_PSK1", "DEV.WIFI.AP1.PSK1");
        putAp(form, "1", ap1);
        form.put("Enable5", on5 ? "1" : "0");
        form.put("ESSID5", essid5);
        form.put("_InstID5", "DEV.WIFI.AP5");
        form.put("_WLANCONIG5", "Y");
        form.put("_WEPCONIG5", "N");
        form.put("_PSKCONIG5", "Y");
        form.put("KeyPassphrase5", e5);
        form.put("WEPKey5", e5);
        form.put("_InstID_PSK5", "DEV.WIFI.AP5.PSK1");
        putAp(form, "5", ap5);
        form.put("MLOEnable", pick(nz(mlo.get("MLOEnable")), "0"));
        form.put("encode", ek);
        form.put("PowerEnhance1", pick(nz(get(setting, "DEV.WIFI.RD1", "PowerEnhance")), "1"));
        form.put("TxPower1", pick(nz(get(setting, "DEV.WIFI.RD1", "TxPower")), "100%"));
        form.put("PowerEnhance5", pick(nz(get(setting, "DEV.WIFI.RD2", "PowerEnhance")), "1"));
        form.put("TxPower5", pick(nz(get(setting, "DEV.WIFI.RD2", "TxPower")), "100%"));
        form.put("Band1", "2.4GHz");
        form.put("Band5", "5GHz");
        form.put("_InstID_Frq1", "DEV.WIFI.RD1");
        form.put("_InstID_Frq5", "DEV.WIFI.RD2");

        String txt = ax("/?_type=vueData&_tag=wifi_advancedssid_data", form, 25);
        String err = xmlField(txt, "IF_ERRORSTR");
        if (err != null && !err.isEmpty()
                && !"SUCC".equalsIgnoreCase(err) && !"SUCCESS".equalsIgnoreCase(err) && !"OK".equalsIgnoreCase(err)) {
            throw new IOException("路由器拒绝修改：" + err);
        }
        if ((err == null || err.isEmpty()) && !txt.contains("<ajax_response")) {
            throw new IOException("路由器返回异常：" + (txt.length() > 100 ? txt.substring(0, 100) : txt));
        }
        pwdCache.clear();
    }

    private static void putAp(LinkedHashMap<String, String> form, String sfx, Map<String, String> ap) {
        form.put("BeaconType" + sfx, pick(nz(ap.get("BeaconType")), "11iandWPA3"));
        form.put("WEPAuthMode" + sfx, pick(nz(ap.get("WEPAuthMode")), "SharedAuthentication"));
        form.put("WEPEncryptionLevel" + sfx, pick(nz(ap.get("WEPEncryptionLevel")), "40-bit"));
        form.put("WEPKeyIndex" + sfx, pick(nz(ap.get("WEPKeyIndex")), "1"));
        form.put("WPAAuthMode" + sfx, pick(nz(ap.get("WPAAuthMode")), "PSKAuthentication"));
        form.put("WPAEncryptType" + sfx, pick(nz(ap.get("WPAEncryptType")), "AESEncryption"));
        form.put("11iAuthMode" + sfx, pick(nz(ap.get("11iAuthMode")), "PSKAuthentication"));
        form.put("11iEncryptType" + sfx, pick(nz(ap.get("11iEncryptType")), "AESEncryption"));
        form.put("ESSIDHideEnable" + sfx, pick(nz(ap.get("ESSIDHideEnable")), "0"));
        form.put("WEPEncryptionLevel_Bit" + sfx, pick(nz(ap.get("WEPEncryptionLevel_Bit")), "40-bit"));
    }

    private String reboot() throws IOException, NotLogged {
        ensure();
        String lastErr = null;
        String lastId = null;
        for (int attempt = 0; attempt < 3; attempt++) {
            LinkedHashMap<String, String> f = new LinkedHashMap<String, String>();
            f.put("IF_ACTION", "Restart");
            String txt = ax("/?_type=vueData&_tag=vue_derestart_data", f, 15);
            String err = xmlField(txt, "IF_ERRORSTR");
            String id = xmlField(txt, "IF_ERRORID");
            if (err == null || err.isEmpty() || "SUCC".equalsIgnoreCase(err)
                    || "SUCCESS".equalsIgnoreCase(err) || "OK".equalsIgnoreCase(err)) {
                return "{\"ok\":true,\"attempts\":" + (attempt + 1) + "}";
            }
            lastErr = err;
            lastId = id;
            if (err.contains("系统忙")) {
                sleep(5000);
                continue;
            }
            break;
        }
        return "{\"ok\":false,\"error\":" + jstr("路由器拒绝重启：" + lastErr + "（错误码 " + (lastId == null ? "无" : lastId) + "）") + "}";
    }

    // ---------------- 加解密 ----------------

    public static String sha256Hex(String s) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] d = md.digest(s.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder(d.length * 2);
            for (byte x : d) sb.append(Character.forDigit((x >> 4) & 0xf, 16)).append(Character.forDigit(x & 0xf, 16));
            return sb.toString();
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    private static byte[] sha256(String s) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(s.getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    /** AES-CBC 零填充 + Base64，key=SHA256(a)，iv=SHA256(b) 前 16 字节 */
    public static String encPara(String text, String a, String b) throws Exception {
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        int pad = (16 - data.length % 16) % 16;
        if (pad > 0) {
            byte[] tmp = new byte[data.length + pad];
            System.arraycopy(data, 0, tmp, 0, data.length);
            data = tmp;
        }
        Cipher c = Cipher.getInstance("AES/CBC/NoPadding");
        c.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(sha256(a), "AES"),
                new IvParameterSpec(slice(sha256(b), 16)));
        return b64e(c.doFinal(data));
    }

    public static String decPara(String b64, String a, String b) throws Exception {
        byte[] raw = b64d(b64);
        Cipher c = Cipher.getInstance("AES/CBC/NoPadding");
        c.init(Cipher.DECRYPT_MODE, new SecretKeySpec(sha256(a), "AES"),
                new IvParameterSpec(slice(sha256(b), 16)));
        byte[] p = c.doFinal(raw);
        int end = p.length;
        while (end > 0 && p[end - 1] == 0) end--;
        return new String(p, 0, end, StandardCharsets.UTF_8);
    }

    /** RSA(PKCS1v15) 加密 "a+b"，把两段 AES 随机数交给路由器 */
    public static String encKey(String a, String b) throws Exception {
        byte[] der = b64d(RSA_PUB_DER);
        PublicKey pub = java.security.KeyFactory.getInstance("RSA")
                .generatePublic(new X509EncodedKeySpec(der));
        Cipher c = Cipher.getInstance("RSA/ECB/PKCS1Padding");
        c.init(Cipher.ENCRYPT_MODE, pub);
        return b64e(c.doFinal((a + "+" + b).getBytes(StandardCharsets.UTF_8)));
    }

    private static String rand16() {
        SecureRandom r = new SecureRandom();
        StringBuilder sb = new StringBuilder(16);
        for (int i = 0; i < 16; i++) sb.append(r.nextInt(10));
        return sb.toString();
    }

    // ================= 网络工具：优化 / 排查 / 测速 =================

    /** 测速节点：{key, 名称, 分类, 握手探测用的 host, 镜像目录（空=固定直链）} */
    private static final String[][] SPEED_NODES = {
            {"ustc", "中科大", "教育网", "mirrors.ustc.edu.cn",
             "https://mirrors.ustc.edu.cn/ubuntu-releases/24.04/"},
            {"tuna", "清华 TUNA", "教育网", "mirrors.tuna.tsinghua.edu.cn",
             "https://mirrors.tuna.tsinghua.edu.cn/ubuntu-releases/24.04/"},
            {"nju", "南京大学", "教育网", "mirror.nju.edu.cn",
             "https://mirror.nju.edu.cn/ubuntu-releases/24.04/"},
            {"huawei", "华为云", "公有云", "mirrors.huaweicloud.com",
             "https://mirrors.huaweicloud.com/ubuntu-releases/24.04/"},
            {"cf", "Cloudflare", "国际", "speed.cloudflare.com", ""},
    };
    private static final String SPEED_FALLBACK = "https://speed.cloudflare.com/__down?bytes=30000000";
    private static final int SPEED_MAX_BYTES = 20 * 1024 * 1024;
    private static final long SPEED_MAX_MS = 7000;

    /** 外部 HTTP 文本（列镜像目录用），最多读 maxBytes */
    private String httpText(String url, int timeoutMs, int maxBytes) throws IOException {
        HttpsURLConnection c = (HttpsURLConnection) new URL(url).openConnection();
        c.setSSLSocketFactory(trustAll());
        c.setHostnameVerifier(new HostnameVerifier() {
            public boolean verify(String x, SSLSession s) { return true; }
        });
        c.setConnectTimeout(timeoutMs);
        c.setReadTimeout(timeoutMs);
        c.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 13) Chrome/120 Mobile Safari/537.36");
        try {
            int code = c.getResponseCode();
            if (code >= 400) throw new IOException("HTTP " + code);
            InputStream in = c.getInputStream();
            java.io.ByteArrayOutputStream bo = new java.io.ByteArrayOutputStream();
            byte[] b = new byte[8192];
            int n, got = 0;
            while (got < maxBytes && (n = in.read(b)) > 0) {
                bo.write(b, 0, n);
                got += n;
            }
            in.close();
            return new String(bo.toByteArray(), StandardCharsets.UTF_8);
        } finally {
            c.disconnect();
        }
    }

    /** 下载测速：返回 [bps, bytes, ms]。http/https 都支持（自定义地址可能是 http） */
    private double[] speedMeasure(String url) throws IOException {
        java.net.HttpURLConnection c = (java.net.HttpURLConnection) new URL(url).openConnection();
        if (c instanceof HttpsURLConnection) {
            ((HttpsURLConnection) c).setSSLSocketFactory(trustAll());
            ((HttpsURLConnection) c).setHostnameVerifier(new HostnameVerifier() {
                public boolean verify(String x, SSLSession s) { return true; }
            });
        }
        c.setConnectTimeout(6000);
        c.setReadTimeout(6000);
        c.setRequestProperty("Range", "bytes=0-" + (SPEED_MAX_BYTES - 1));
        c.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 13) Chrome/120 Mobile Safari/537.36");
        long t0 = System.currentTimeMillis();
        long got = 0;
        try {
            int code = c.getResponseCode();
            if (code >= 400) throw new IOException("HTTP " + code);
            InputStream in = c.getInputStream();
            byte[] b = new byte[65536];
            int n;
            while (true) {
                if (System.currentTimeMillis() - t0 > SPEED_MAX_MS || got >= SPEED_MAX_BYTES) break;
                n = in.read(b);
                if (n <= 0) break;
                got += n;
            }
            in.close();
        } finally {
            c.disconnect();
        }
        long ms = Math.max(150, System.currentTimeMillis() - t0);
        return new double[]{got * 8.0 / (ms / 1000.0), (double) got, (double) ms};
    }

    private static String pickIso(String page) {
        Matcher m = Pattern.compile("(ubuntu-[0-9][\\w.\\-]*live-server-amd64\\.iso)").matcher(page == null ? "" : page);
        String best = "";
        while (m.find()) if (m.group(1).compareTo(best) > 0) best = m.group(1);
        return best;
    }

    public synchronized String speedTestJson(String arg) {
        String custom = "", node = "";
        try {
            Map<String, Object> o = asMap(MiniJson.parse(
                    arg == null || arg.trim().isEmpty() ? "{}" : arg));
            custom = nz(str(o.get("url"))).trim();
            node = nz(str(o.get("node"))).trim();
        } catch (Exception ignored) {
        }
        java.util.List<String[]> tries = new ArrayList<String[]>();
        if (!custom.isEmpty()) {
            tries.add(new String[]{custom, "自定义地址", "custom"});
        } else {
            java.util.List<String[]> order = new ArrayList<String[]>();
            if (!node.isEmpty() && !"auto".equals(node)) {
                for (String[] n : SPEED_NODES) if (n[0].equals(node)) order.add(n);
                for (String[] n : SPEED_NODES) if (!n[0].equals(node)) order.add(n);
            } else {
                order.addAll(fastestNodes());
            }
            for (String[] n : order) {
                if (n[4].isEmpty()) {           // Cloudflare：固定直链
                    tries.add(new String[]{SPEED_FALLBACK, n[1], n[0]});
                    continue;
                }
                try {
                    String page = httpText(n[4], 6000, 600000);
                    String iso = pickIso(page);
                    if (!iso.isEmpty()) tries.add(new String[]{n[4] + iso, n[1], n[0]});
                } catch (Exception e) {
                    trace("镜像目录失败 " + n[4] + " " + msg(e));
                }
            }
            if (tries.isEmpty()) tries.add(new String[]{SPEED_FALLBACK, "Cloudflare 测速节点", "cf"});
        }
        String err = "";
        for (String[] t : tries) {
            try {
                double[] r = speedMeasure(t[0]);
                if (r[1] < 200 * 1024) { err = t[1] + " 数据太少"; continue; }
                double mbps = r[0] / 1e6;
                String grade = mbps >= 100 ? "很快" : mbps >= 30 ? "正常" : mbps >= 10 ? "偏慢" : "很慢";
                return "{\"ok\":true,\"mbps\":" + Math.round(mbps * 100) / 100.0
                        + ",\"bytes\":" + (long) r[1]
                        + ",\"seconds\":" + Math.round(r[2] / 10) / 100.0
                        + ",\"source\":" + jstr(t[1])
                        + ",\"node\":" + jstr(t.length > 2 ? t[2] : "")
                        + ",\"nodeName\":" + jstr(t[1])
                        + ",\"url\":" + jstr(t[0])
                        + ",\"grade\":" + jstr(grade) + "}";
            } catch (Exception e) {
                err = t[1] + " 失败：" + msg(e);
                trace("测速失败 " + t[1] + " " + msg(e));
            }
        }
        return "{\"ok\":false,\"error\":" + jstr(err.isEmpty() ? "所有测速源都不可用，可以手工填一个下载地址" : err) + "}";
    }

    /** 并发量各节点握手延迟（ms，0=失败），用来挑最近节点 */
    private int[] nodeLatency() {
        final int n = SPEED_NODES.length;
        final int[] ms = new int[n];
        Thread[] ts = new Thread[n];
        for (int i = 0; i < n; i++) {
            final int k = i;
            ts[i] = new Thread(new Runnable() {
                public void run() {
                    try {
                        ms[k] = tlsMs(SPEED_NODES[k][3], 443, 2500);
                    } catch (Exception e) {
                        ms[k] = 0;
                    }
                }
            });
            ts[i].setDaemon(true);
            ts[i].start();
        }
        for (int i = 0; i < n; i++) {
            try { ts[i].join(3000); } catch (InterruptedException ignored) {}
        }
        return ms;
    }

    private static Integer[] sortByLatency(final int[] ms) {
        Integer[] idx = new Integer[ms.length];
        for (int i = 0; i < idx.length; i++) idx[i] = i;
        java.util.Arrays.sort(idx, new java.util.Comparator<Integer>() {
            public int compare(Integer a, Integer b) {
                boolean oa = ms[a] > 0, ob = ms[b] > 0;
                if (oa != ob) return oa ? -1 : 1;
                return (ms[a] == 0 ? 99999 : ms[a]) - (ms[b] == 0 ? 99999 : ms[b]);
            }
        });
        return idx;
    }

    private java.util.List<String[]> fastestNodes() {
        int[] ms = nodeLatency();
        java.util.List<String[]> out = new ArrayList<String[]>();
        for (Integer i : sortByLatency(ms)) out.add(SPEED_NODES[i]);
        return out;
    }

    /** 前端节点列表：按握手延迟排序 */
    public synchronized String speedNodesJson() {
        int[] ms = nodeLatency();
        Integer[] idx = sortByLatency(ms);
        String best = "";
        for (Integer i : idx) {
            if (ms[i] > 0) { best = SPEED_NODES[i][0]; break; }
        }
        StringBuilder sb = new StringBuilder("{\"ok\":true,\"best\":");
        sb.append(jstr(best)).append(",\"nodes\":[");
        boolean first = true;
        for (Integer i : idx) {
            if (!first) sb.append(",");
            first = false;
            sb.append("{\"key\":").append(jstr(SPEED_NODES[i][0]))
              .append(",\"name\":").append(jstr(SPEED_NODES[i][1]))
              .append(",\"tag\":").append(jstr(SPEED_NODES[i][2]))
              .append(",\"ms\":").append(ms[i])
              .append(",\"ok\":").append(ms[i] > 0 ? "true" : "false").append("}");
        }
        return sb.append("]}").toString();
    }

    /** 上级光猫：读 WAN 网关 + 探测管理页；arg 可带 {"ip":"192.168.1.1[:8080]"} 指定地址 */
    public synchronized String ontJson(String arg) {
        String manual = "";
        if (arg != null) {
            java.util.regex.Matcher mm = java.util.regex.Pattern
                    .compile("\"ip\"\\s*:\\s*\"([^\"]*)\"").matcher(arg);
            if (mm.find()) manual = mm.group(1).trim();
            if (manual.length() == 0 && arg.trim().matches("^[0-9.]+(:[0-9]+)?$")) {
                manual = arg.trim();
            }
        }
        int mport = 0;
        if (manual.indexOf(':') > 0) {
            String[] seg = manual.split(":");
            manual = seg[0].trim();
            try { mport = Integer.parseInt(seg[1].trim()); } catch (Exception ignored) {}
        }

        String gw = "", ip = "", conn = "", dns = "", werr = "";
        try {
            Map<String, List<Map<String, String>>> g = fetch("/?_type=vueData&_tag=vue_internet_data&_="
                    + System.currentTimeMillis());
            Map<String, String> it = new LinkedHashMap<String, String>();
            for (List<Map<String, String>> rows0 : g.values()) {
                for (Map<String, String> x : rows0) {
                    if (x.containsKey("ConnStatus") || x.containsKey("IPAddress")) { it = x; break; }
                }
                if (!it.isEmpty()) break;
            }
            gw = nz(it.get("GateWay")).trim();
            ip = nz(it.get("IPAddress")).trim();
            conn = nz(it.get("ConnType")).trim();
            dns = nz(it.get("DNS1")).trim();
        } catch (Exception e) {
            werr = msg(e);
        }
        if (werr.length() > 0 && manual.length() == 0) {
            return "{\"ok\":false,\"logged\":false,\"error\":"
                    + jstr("需要先登录路由器才能读取") + "}";
        }

        boolean pppoe = conn.toLowerCase().contains("pppoe");
        boolean gwPriv = isPrivateIp(gw);
        String mode = pppoe ? "bridge" : (gwPriv ? "route" : "unknown");

        java.util.List<String> cands = new ArrayList<String>();
        if (manual.length() > 0) {
            cands.add(manual);
        } else {
            // 桥接拨号时网关是运营商 BRAS（公网地址），探它只会白等超时
            if (gw.length() > 0 && !"0.0.0.0".equals(gw) && (!pppoe || gwPriv)) cands.add(gw);
            String[] def = {"192.168.1.1", "192.168.0.1", "192.168.100.1", "192.168.2.1"};
            for (String d : def) {
                if (!cands.contains(d)) cands.add(d);
            }
        }
        final java.util.List<String> targets = cands;
        final String gwf = gw;

        // 同一个端口的所有地址并发试；哪一轮有命中就停，避免逐个等超时
        final java.util.List<String[]> rows = new ArrayList<String[]>();
        int[] ports = mport > 0 ? new int[]{mport} : new int[]{80, 443, 8080};
        for (int port : ports) {
            final int pt = port;
            final java.util.List<String[]> hit =
                    java.util.Collections.synchronizedList(new ArrayList<String[]>());
            java.util.List<Thread> ts = new ArrayList<Thread>();
            for (final String cand : targets) {
                Thread t = new Thread(new Runnable() {
                    public void run() {
                        try {
                            int ms = tcpMs(cand, pt, 900);
                            hit.add(new String[]{cand, String.valueOf(pt), String.valueOf(ms),
                                    cand.equals(gwf) ? "1" : "0"});
                        } catch (Exception ignored) {
                        }
                    }
                });
                t.setDaemon(true);
                ts.add(t);
                t.start();
            }
            for (Thread t : ts) {
                try { t.join(); } catch (Exception ignored) {}
            }
            if (!hit.isEmpty()) {
                rows.addAll(hit);
                break;
            }
        }
        java.util.Collections.sort(rows, new java.util.Comparator<String[]>() {
            public int compare(String[] a, String[] b) {
                int g1 = b[3].compareTo(a[3]);
                if (g1 != 0) return g1;
                int p = ("80".equals(a[1]) ? 0 : 1) - ("80".equals(b[1]) ? 0 : 1);
                if (p != 0) return p;
                return Integer.parseInt(a[2]) - Integer.parseInt(b[2]);
            }
        });

        StringBuilder cd = new StringBuilder("[");
        for (int i = 0; i < rows.size() && i < 4; i++) {
            if (i > 0) cd.append(",");
            cd.append(candJson(rows.get(i)));
        }
        cd.append("]");
        String best = rows.isEmpty() ? "null" : candJson(rows.get(0));

        String note = "";
        if (rows.isEmpty()) {
            if (manual.length() > 0) {
                note = "这个地址没响应。确认手机现在就接在光猫这一侧（光猫 LAN 口或光猫自带 Wi-Fi），"
                        + "端口也要对上，比如改过端口的写 192.168.1.1:8080。";
            } else if (pppoe) {
                note = "光猫现在跟路由器一起做桥接拨号，它的管理页只对「光猫自己的 LAN 口 / 光猫 Wi-Fi」"
                        + "开放，从路由器后面的手机是进不去的——这是正常现象，不是故障。";
            } else {
                note = "光猫看着是路由模式，但管理页没回应：可能改过管理端口，或在光猫里关掉了 LAN 侧 "
                        + "Web 管理。记得地址的话填到下面再探一次。";
            }
        }
        return "{\"ok\":true,\"wan\":{\"ip\":" + jstr(ip) + ",\"gw\":" + jstr(gw)
                + ",\"conn\":" + jstr(conn) + ",\"dns\":" + jstr(dns) + "}"
                + ",\"pppoe\":" + (pppoe ? "true" : "false")
                + ",\"mode\":" + jstr(mode)
                + ",\"manual\":" + (manual.length() > 0 ? "true" : "false")
                + ",\"reachable\":" + (rows.isEmpty() ? "false" : "true")
                + ",\"best\":" + best + ",\"candidates\":" + cd
                + ",\"note\":" + jstr(note) + ",\"hint\":" + jstr(note) + "}";
    }

    // ================= 网口实况 / 双 WAN / 管理员密码 =================

    /** 取某个标签块里的全部 Instance；_lua 系列的 Instance 是平铺字段，没有 ParaName 时按平铺解析 */
    private static List<Map<String, String>> tagInstances(String xml, String tag) {
        List<Map<String, String>> out = new ArrayList<Map<String, String>>();
        if (xml == null) return out;
        int i = xml.indexOf("<" + tag + ">");
        if (i < 0) return out;
        int j = xml.indexOf("</" + tag + ">", i);
        if (j < 0) return out;
        String body = xml.substring(i, j + tag.length() + 3);
        List<Map<String, String>> rows = xmlInstances(body);
        if (!rows.isEmpty()) return rows;
        Matcher fm = Pattern.compile("<([A-Za-z0-9_]+)>([^<]*)</\\1>", Pattern.DOTALL).matcher(body);
        Map<String, String> row = new LinkedHashMap<String, String>();
        while (fm.find()) row.put(fm.group(1), unescape(fm.group(2)).trim());
        if (!row.isEmpty()) out.add(row);
        return out;
    }

    private static Map<String, String> firstTag(String xml, String tag) {
        List<Map<String, String>> l = tagInstances(xml, tag);
        return l.isEmpty() ? new LinkedHashMap<String, String>() : l.get(0);
    }

    private static String respErr(String body) {
        if (body == null) return "路由器没有返回结果";
        Matcher m = Pattern.compile("<IF_ERRORSTR>(.*?)</IF_ERRORSTR>", Pattern.DOTALL).matcher(body);
        if (!m.find()) return "";
        String v = m.group(1).trim();
        return (v.isEmpty() || "SUCC".equalsIgnoreCase(v) || "OK".equalsIgnoreCase(v)) ? "" : v;
    }

    private static String argStr(String arg, String key) {
        if (arg == null) return "";
        Matcher m = Pattern.compile("\"" + key + "\"\\s*:\\s*\"([^\"]*)\"").matcher(arg);
        return m.find() ? m.group(1) : "";
    }

    private static int argInt(String arg, String key, int dflt) {
        if (arg == null) return dflt;
        Matcher m = Pattern.compile("\"" + key + "\"\\s*:\\s*(-?[0-9]+)").matcher(arg);
        try { return m.find() ? Integer.parseInt(m.group(1)) : dflt; } catch (Exception e) { return dflt; }
    }

    /** 网口实况：插线 / 速率 / 实时流量 / 接入设备（含离线） */
    public synchronized String portsLiveJson() {
        List<Map<String, String>> ports;
        try {
            ports = portList();
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":" + jstr(msg(e)) + "}";
        }
        List<Map<String, String>> devs = new ArrayList<Map<String, String>>();
        try {
            String txt = fetchText("/?_type=vueData&_tag=localnet_lan_info_lua&_=" + System.currentTimeMillis());
            for (Map<String, String> m : tagInstances(txt, "OBJ_LAN_INFO_ID")) {
                if (nz(str(m.get("MACAddress"))).isEmpty()) continue;
                Map<String, String> d = new LinkedHashMap<String, String>();
                d.put("mac", nz(str(m.get("MACAddress"))).toUpperCase());
                d.put("ip", nz(str(m.get("IPAddress"))));
                d.put("name", pick(pick(nz(str(m.get("HostName"))), nz(str(m.get("DevName")))), "未知设备"));
                d.put("port", nz(str(m.get("Interface"))));
                d.put("iface", nz(str(m.get("InterfaceType"))));
                d.put("active", "1".equals(str(m.get("Active"))) ? "1" : "0");
                d.put("last", nz(str(m.get("LastConnection"))));
                devs.add(d);
            }
        } catch (Exception ignore) { }

        StringBuilder rows = new StringBuilder("[");
        int wiredOn = 0, wiredAll = 0;
        for (Map<String, String> d : devs) {
            String it = up(nz(d.get("iface")));
            if (it.contains("802.11") || it.contains("WLAN") || it.contains("WIFI")) continue;
            wiredAll++;
            if ("1".equals(d.get("active"))) wiredOn++;
        }
        for (int i = 0; i < ports.size(); i++) {
            Map<String, String> p = ports.get(i);
            int online = 0, offline = 0;
            StringBuilder dl = new StringBuilder("[");
            boolean dfirst = true;
            for (Map<String, String> d : devs) {
                if (!onPort(d, p)) continue;
                boolean act = "1".equals(d.get("active"));
                if (act) online++; else offline++;
                if (!dfirst) dl.append(",");
                dfirst = false;
                dl.append("{\"name\":").append(jstr(d.get("name")))
                  .append(",\"ip\":").append(jstr(d.get("ip")))
                  .append(",\"active\":").append(act ? "true" : "false")
                  .append(",\"last\":").append(jstr(d.get("last"))).append("}");
            }
            dl.append("]");
            boolean busy = online > 0;
            if (!busy) {
                double u = num(p.get("up")), dn = num(p.get("down"));
                busy = (u + dn) > 1024;
            }
            if (i > 0) rows.append(",");
            rows.append("{\"name\":").append(jstr(p.get("name")))
                .append(",\"wan\":").append("1".equals(p.get("wan")) ? "true" : "false")
                .append(",\"link\":").append("1".equals(p.get("link")) ? "true" : "false")
                .append(",\"linkKnown\":").append("1".equals(p.get("linkKnown")) ? "true" : "false")
                .append(",\"speed\":").append(jstr(p.get("speed")))
                .append(",\"max\":").append(jstr(p.get("max")))
                .append(",\"upText\":").append(jstr(p.get("up")))
                .append(",\"downText\":").append(jstr(p.get("down")))
                .append(",\"online\":").append(online)
                .append(",\"offline\":").append(offline)
                .append(",\"devs\":").append(online + offline)
                .append(",\"busy\":").append(busy ? "true" : "false")
                .append(",\"devList\":").append(dl).append("}");
        }
        rows.append("]");
        return "{\"ok\":true,\"ports\":" + rows
                + ",\"wired\":{\"online\":" + wiredOn + ",\"total\":" + wiredAll + "}"
                + ",\"at\":" + (System.currentTimeMillis() / 1000) + "}";
    }

    /** 双 WAN 现状：WAN1 主口 + WAN2 端口与状态 + 可选的 LAN 口 */
    public synchronized String dualwanJson() {
        try {
            Resp eth = req("/?_type=hiddenData&_tag=vue_internet_eth_data&_=" + System.currentTimeMillis(), null, 10);
            if (eth.status != 200 || eth.body == null || eth.body.indexOf("OBJ_DUALWAN_BASIC_ID") < 0) {
                // 本机（BE5100 Pro+ 这类）没有老款的双 WAN 表，改为「固定 WAN1 + 旁边的口当 WAN2」
                return dualwanFixedJson();
            }
            Map<String, String> basic = firstTag(eth.body, "OBJ_DUALWAN_BASIC_ID");
            Map<String, String> wanlan0 = firstTag(eth.body, "OBJ_WANLAN_ID");
            Map<String, String> lb = firstTag(eth.body, "OBJ_DUALWAN_LOADBALANCE_ID");
            Map<String, String> mal = firstTag(eth.body, "OBJ_DUALWAN_MAL_TRSF_ID");
            Map<String, String> dw = new LinkedHashMap<String, String>();
            try {
                Resp r2 = req("/?_type=vueData&_tag=vue_dualwan_data&_=" + System.currentTimeMillis(), null, 10);
                dw = firstTag(r2.body == null ? "" : r2.body, "ID_WAN_COMFIG");
            } catch (Exception ignore) { }

            List<Map<String, String>> ports = portList();
            int main = 0, sec = 1;
            try { main = (int) Double.parseDouble(pick(nz(wanlan0.get("WANSelect")), "0")); } catch (Exception ignore) { }
            try { sec = (int) Double.parseDouble(pick(nz(basic.get("SecWanLink")), "1")); } catch (Exception ignore) { }
            boolean w2on = "1".equals(str(dw.get("Enable")));

            StringBuilder ps = new StringBuilder("[");
            for (int i = 0; i < ports.size(); i++) {
                Map<String, String> p = ports.get(i);
                if (i > 0) ps.append(",");
                ps.append("{\"idx\":").append(i)
                  .append(",\"name\":").append(jstr(p.get("name")))
                  .append(",\"wan\":").append("1".equals(p.get("wan")) ? "true" : "false")
                  .append(",\"link\":").append("1".equals(p.get("link")) ? "true" : "false")
                  .append(",\"speed\":").append(jstr(p.get("speed")))
                  .append(",\"isMain\":").append(i == main ? "true" : "false")
                  .append(",\"isSec\":").append(i == sec ? "true" : "false").append("}");
            }
            ps.append("]");

            String w1name = main >= 0 && main < ports.size() ? nz(ports.get(main).get("name")) : "WAN";
            String w2name = sec >= 0 && sec < ports.size() ? nz(ports.get(sec).get("name")) : "";
            boolean w1link = main >= 0 && main < ports.size() && "1".equals(ports.get(main).get("link"));
            boolean w2link = sec >= 0 && sec < ports.size() && "1".equals(ports.get(sec).get("link"));
            String status = nz(str(dw.get("ConnStatus")));
            if (!w2on) status = "未启用";
            return "{\"ok\":true,\"supported\":true"
                    + ",\"wan1\":{\"idx\":" + main + ",\"name\":" + jstr(w1name)
                    + ",\"link\":" + (w1link ? "true" : "false")
                    + ",\"speed\":" + jstr(main >= 0 && main < ports.size() ? nz(ports.get(main).get("speed")) : "") + "}"
                    + ",\"wan2\":{\"idx\":" + sec + ",\"name\":" + jstr(w2name)
                    + ",\"link\":" + (w2link ? "true" : "false")
                    + ",\"enabled\":" + (w2on ? "true" : "false")
                    + ",\"status\":" + jstr(status)
                    + ",\"type\":" + jstr(pick(nz(str(dw.get("WANCTYPE"))), nz(str(dw.get("TransType")))))
                    + ",\"ip\":" + jstr(nz(str(dw.get("IPAddress")))) + "}"
                    + ",\"loadBalance\":{\"enabled\":" + ("1".equals(str(lb.get("lbEnable"))) ? "true" : "false")
                    + ",\"wan1\":" + jstr(pick(nz(str(lb.get("FirWanLoadRatio"))), "1"))
                    + ",\"wan2\":" + jstr(pick(nz(str(lb.get("SecWanLoadRatio"))), "1")) + "}"
                    + ",\"failover\":" + ("1".equals(str(mal.get("MalSwitch"))) ? "true" : "false")
                    + ",\"ports\":" + ps + ",\"canSwitch\":true,\"note\":\"\"}";
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":" + jstr(msg(e)) + "}";
        }
    }

    /** WAN2 是否启用：WANLIST 里出现非主 WAN 的连接即视为启用（免登录可读） */
    private boolean wan2InList() {
        try {
            Resp r = req("/?_type=vuejsonData&_tag=vue_eth_portname&GET_TYPE=WANLIST&_="
                    + System.currentTimeMillis(), null, 8);
            if (r.status != 200 || r.body == null || r.body.startsWith("<")) return false;
            Map<String, Object> doc = asMap(MiniJson.parse(r.body));
            Map<String, Object> data = asMap(doc.get("data"));
            if (data.isEmpty()) data = doc;
            for (Object x : jlist(data.get("OBJ_WANC_INFO_ID"))) {
                if (!"1".equals(nz(str(asMap(x).get("IsMainWAN"))))) return true;
            }
        } catch (Exception ignore) { }
        return false;
    }

    /**
     * 本机口径的双 WAN：物理只有一个 WAN 口，
     * WAN2 = WAN1 旁边那个网口（固件文案「WAN2（LAN1）」），启用后该口 WanType 变 2。
     * 这里只读展示，不改配置（写入口径还没验证，避免把宽带配置打坏）。
     */
    private String dualwanFixedJson() {
        List<Map<String, String>> ports;
        try {
            ports = portList();
        } catch (Exception e) {
            ports = new ArrayList<Map<String, String>>();
        }
        Map<String, String> dw = new LinkedHashMap<String, String>();
        try {
            Resp r2 = req("/?_type=vueData&_tag=vue_dualwan_data&_=" + System.currentTimeMillis(), null, 10);
            if (r2.body != null && r2.body.indexOf("ID_WAN_COMFIG") >= 0) {
                dw = firstTag(r2.body, "ID_WAN_COMFIG");
            }
        } catch (Exception ignore) { }
        if (dw == null) dw = new LinkedHashMap<String, String>();

        int i1 = -1, i2 = -1;
        for (int i = 0; i < ports.size(); i++) {
            Map<String, String> p = ports.get(i);
            if (i1 < 0 && "1".equals(p.get("wan"))) i1 = i;
            if (i2 < 0 && "2".equals(nz(p.get("wanType")))) i2 = i;
        }
        boolean preset = false;
        if (i2 < 0) {                                  // 还没启用：WAN2 就是 WAN1 旁边的 LAN1
            for (int i = 0; i < ports.size(); i++) {
                if ("LAN1".equalsIgnoreCase(nz(ports.get(i).get("name")))) { i2 = i; break; }
            }
            preset = true;
        }
        boolean enabled = "1".equals(str(dw.get("Enable"))) || wan2InList();

        StringBuilder ps = new StringBuilder("[");
        for (int i = 0; i < ports.size(); i++) {
            Map<String, String> p = ports.get(i);
            if (i > 0) ps.append(',');
            ps.append("{\"idx\":").append(i)
              .append(",\"name\":").append(jstr(nz(p.get("name"))))
              .append(",\"wan\":").append("1".equals(p.get("wan")) ? "true" : "false")
              .append(",\"wanType\":").append(nz(p.get("wanType")).isEmpty() ? "-1" : nz(p.get("wanType")))
              .append(",\"link\":").append("1".equals(p.get("link")) ? "true" : "false")
              .append(",\"linkKnown\":").append("1".equals(p.get("linkKnown")) ? "true" : "false")
              .append(",\"speed\":").append(jstr(nz(p.get("speed"))))
              .append(",\"max\":").append(jstr(nz(p.get("max"))))
              .append(",\"isMain\":").append(i == i1 ? "true" : "false")
              .append(",\"isSec\":").append(i == i2 ? "true" : "false").append('}');
        }
        ps.append(']');

        Map<String, String> p1 = i1 >= 0 ? ports.get(i1) : new LinkedHashMap<String, String>();
        Map<String, String> p2 = i2 >= 0 ? ports.get(i2) : new LinkedHashMap<String, String>();
        String status = enabled ? pick(nz(str(dw.get("ConnStatus"))), "已启用") : "未启用";
        return "{\"ok\":true,\"supported\":true,\"flavor\":\"fixed\",\"canSwitch\":false"
                + ",\"wan1\":{\"idx\":" + i1 + ",\"name\":" + jstr(pick(nz(p1.get("name")), "WAN"))
                + ",\"link\":" + ("1".equals(p1.get("link")) ? "true" : "false")
                + ",\"speed\":" + jstr(nz(p1.get("speed")))
                + ",\"max\":" + jstr(nz(p1.get("max")))
                + ",\"locked\":true}"
                + ",\"wan2\":{\"idx\":" + i2 + ",\"name\":" + jstr(pick(nz(p2.get("name")), "LAN1"))
                + ",\"link\":" + ("1".equals(p2.get("link")) ? "true" : "false")
                + ",\"speed\":" + jstr(nz(p2.get("speed")))
                + ",\"max\":" + jstr(nz(p2.get("max")))
                + ",\"enabled\":" + (enabled ? "true" : "false")
                + ",\"preset\":" + (preset ? "true" : "false")
                + ",\"locked\":true"
                + ",\"status\":" + jstr(status)
                + ",\"type\":" + jstr(pick(nz(str(dw.get("WANCTYPE"))), nz(str(dw.get("TransType")))))
                + ",\"ip\":" + jstr(nz(str(dw.get("IPAddress")))) + "}"
                + ",\"loadBalance\":{\"enabled\":false,\"wan1\":\"1\",\"wan2\":\"1\"}"
                + ",\"failover\":false,\"ports\":" + ps
                + ",\"note\":\"这台机器的物理 WAN 只有一个（WAN1），WAN2 是把 WAN1 旁边那个网口切过去当第二个 WAN 用。\"}";
    }

    /** 把某个 LAN 口切成 WAN2：整表回填，只改 SecWanLink */
    public synchronized String dualwanSetJson(String arg) {
        try {
            Resp dwchk = req("/?_type=hiddenData&_tag=vue_internet_eth_data&_=" + System.currentTimeMillis(), null, 10);
            if (dwchk.status != 200 || dwchk.body == null || dwchk.body.indexOf("OBJ_DUALWAN_BASIC_ID") < 0) {
                return "{\"ok\":false,\"error\":\"这台机器的物理 WAN 只有一个（WAN1），WAN2 是把 WAN1 旁边那个网口切过去用，不能在口之间挑；请到路由器原版管理页的「双 WAN」里设置\"}";
            }
            List<Map<String, String>> ports = portList();
            // 两个物理 WAN 口设置：main=WAN1 口，sec/port/idx=WAN2 口，可以只给其中一个
            int newMain = argInt(arg, "main", -1);
            String wantMain = argStr(arg, "main");
            int target = argInt(arg, "sec", argInt(arg, "port", argInt(arg, "idx", -1)));
            String want = argStr(arg, "sec");
            if (want.length() == 0) want = argStr(arg, "port");
            if (want.length() == 0) want = argStr(arg, "idx");
            if (newMain < 0 && wantMain.length() > 0) {
                for (int i = 0; i < ports.size(); i++) {
                    if (wantMain.equalsIgnoreCase(nz(ports.get(i).get("name")))) { newMain = i; break; }
                }
            }
            if (target < 0 && want.length() > 0) {
                for (int i = 0; i < ports.size(); i++) {
                    if (want.equalsIgnoreCase(nz(ports.get(i).get("name")))) { target = i; break; }
                }
            }
            if (newMain >= ports.size()) newMain = -1;
            if (target >= ports.size()) target = -1;
            if (target < 0 && newMain < 0) {
                return "{\"ok\":false,\"error\":\"请选择要设置的 WAN 口端口\",\"logged\":true}";
            }
            if (target >= 0 && newMain >= 0 && target == newMain) {
                return "{\"ok\":false,\"error\":\"WAN1 和 WAN2 不能用同一个口\",\"logged\":true}";
            }
            if (target >= 0 && "1".equals(ports.get(target).get("wan"))) {
                return "{\"ok\":false,\"error\":\"WAN 口（光纤口）只能当 WAN1，不能同时当 WAN2\",\"logged\":true}";
            }

            Resp eth = req("/?_type=hiddenData&_tag=vue_internet_eth_data&_=" + System.currentTimeMillis(), null, 10);
            if (eth.status != 200 || eth.body == null || eth.body.indexOf("OBJ_DUALWAN_BASIC_ID") < 0) {
                return "{\"ok\":false,\"error\":\"这台固件没有返回双 WAN 配置\",\"logged\":true}";
            }
            Map<String, String> basic = firstTag(eth.body, "OBJ_DUALWAN_BASIC_ID");
            Map<String, String> wanlan0 = firstTag(eth.body, "OBJ_WANLAN_ID");
            Map<String, String> lb = firstTag(eth.body, "OBJ_DUALWAN_LOADBALANCE_ID");
            Map<String, String> mal = firstTag(eth.body, "OBJ_DUALWAN_MAL_TRSF_ID");
            Resp r2 = req("/?_type=vueData&_tag=vue_dualwan_data&_=" + System.currentTimeMillis(), null, 10);
            Map<String, String> dw = firstTag(r2.body == null ? "" : r2.body, "ID_WAN_COMFIG");
            if (dw.isEmpty()) {
                return "{\"ok\":false,\"error\":\"读不到 WAN2 配置，先刷新一下再试\",\"logged\":true}";
            }

            int main = 0, oldSec = 1;
            try { main = (int) Double.parseDouble(pick(nz(wanlan0.get("WANSelect")), "0")); } catch (Exception ignore) { }
            try { oldSec = (int) Double.parseDouble(pick(nz(basic.get("SecWanLink")), "1")); } catch (Exception ignore) { }
            boolean enabled = "1".equals(str(dw.get("Enable")));
            if (target == main && target >= 0 && (newMain < 0 || newMain == main)) {
                return "{\"ok\":false,\"error\":\"这个口正在当 WAN1，先把 WAN1 换到别的口\",\"logged\":true}";
            }
            if (newMain == oldSec && newMain >= 0 && target < 0 && enabled) {
                return "{\"ok\":false,\"error\":\"这个口正在当 WAN2，先把 WAN2 换到别的口\",\"logged\":true}";
            }
            if ((target < 0 || target == oldSec) && (newMain < 0 || newMain == main) && enabled) {
                return "{\"ok\":true,\"changed\":false,\"sec\":" + oldSec + ",\"main\":" + main
                        + ",\"name\":" + jstr(nz(ports.get(oldSec).get("name")))
                        + ",\"msg\":\"端口设置没有变化\",\"logged\":true}";
            }

            String wct = "dhcp/static", mode = "DHCP", wname = "DHCP_2";
            String wanctype = nz(str(dw.get("WANCTYPE"))).toLowerCase();
            String tt = nz(str(dw.get("TransType"))).toLowerCase();
            String at = nz(str(dw.get("Addressingtype"))).toLowerCase();
            if ("bridge".equals(wanctype)) { wct = "bridge"; mode = "bridge"; wname = "Bridge_2"; }
            else if (tt.contains("pppoe")) { wct = "pppoe"; mode = "pppoe"; wname = "PPPoE_2"; }
            else if (at.contains("static") || tt.contains("static")) { wct = "dhcp/static"; mode = "Static"; wname = "Static_2"; }

            // WAN2 已配好（尤其 PPPoE）时，保存要带账号密码；读不到密码绝不硬提交，免得把宽带账号打坏
            LinkedHashMap<String, String> extra = new LinkedHashMap<String, String>();
            if (enabled && "pppoe".equals(wct)) {
                String user = nz(str(dw.get("UserName")));
                String pwd = "";
                try {
                    Resp pr = req("/?_type=vueData&_tag=vue_dualwan_data&IF_OP=GetPassword&_InstID_PASS="
                            + nz(str(dw.get("_InstID"))) + "&PASSTYPE=PPP&_=" + System.currentTimeMillis(), null, 10);
                    pwd = nz(str(firstTag(pr.body == null ? "" : pr.body, "OBJ_ETHWANCPPP_ID").get("Password")));
                } catch (Exception ignore) { }
                if (user.isEmpty() || pwd.isEmpty()) {
                    return "{\"ok\":false,\"logged\":true,\"error\":\"WAN2 现在是 PPPoE 拨号，路由器没有把宽带密码交出来。"
                            + "为了不把账号打坏，这里不硬改端口：请先在原版管理页把「双 WAN」关掉，或直接在原版页面里换口。\"}";
                }
                String a = rand16(), b = rand16();
                extra.put("UserName", user);
                extra.put("Password", encPara(pwd, a, b));
                extra.put("PPPoEServiceName", nz(str(dw.get("PPPoEServiceName"))));
                extra.put("encode", encKey(a, b));
            } else if (enabled && "Static".equals(mode)) {
                extra.put("IPAddress", nz(str(dw.get("IPAddress"))));
                extra.put("SubnetMask", nz(str(dw.get("SubnetMask"))));
                extra.put("GateWay", nz(str(dw.get("GateWay"))));
                extra.put("Addressingtype", "Static");
                extra.put("DNS1", pick(nz(str(dw.get("DNS1"))), "0.0.0.0"));
                extra.put("DNS2", pick(nz(str(dw.get("DNS2"))), "0.0.0.0"));
            } else if (enabled && "DHCP".equals(mode)) {
                extra.put("DNSOverrideAllowedv4", "0".equals(str(dw.get("DNSOverrideAllowedv4"))) ? "0" : "1");
            }

            int finalMain = newMain >= 0 ? newMain : main;
            int finalSec = target >= 0 ? target : oldSec;

            LinkedHashMap<String, String> f = new LinkedHashMap<String, String>();
            f.put("IF_ACTION", "Apply");
            f.put("Enable", enabled ? "1" : "0");
            f.put("_InstID", nz(str(dw.get("_InstID"))));
            f.put("WANC_TYPE", wct);
            f.put("WANCName", wname);
            f.put("mode", mode);
            f.put("TypeFlag", "0");
            f.put("WANSelect", String.valueOf(finalMain));
            f.put("SecWanLink", String.valueOf(finalSec));
            f.put("Mode", pick(nz(str(basic.get("Mode"))), "0"));
            f.put("LANViewName", nz(str(basic.get("LANViewName"))));
            f.put("DevIp", nz(str(basic.get("DevIp"))));
            f.put("BindEnable", pick(nz(str(basic.get("BindEnable"))), "0"));
            f.put("lbEnable", pick(nz(str(lb.get("lbEnable"))), "0"));
            f.put("FirWanLoadRatio", pick(nz(str(lb.get("FirWanLoadRatio"))), "1"));
            f.put("SecWanLoadRatio", pick(nz(str(lb.get("SecWanLoadRatio"))), "1"));
            f.put("MalSwitch", pick(nz(str(mal.get("MalSwitch"))), "0"));
            f.put("IsDns", pick(nz(str(mal.get("IsDns"))), "1"));
            f.put("TriggerTime", pick(nz(str(mal.get("TriggerTime"))), "3"));
            f.put("ReCoverTime", pick(nz(str(mal.get("ReCoverTime"))), "3"));
            f.put("IntervalTime", pick(nz(str(mal.get("IntervalTime"))), "10"));
            f.put("Dest", pick(nz(str(mal.get("Dest"))), "www.zte.com.cn"));
            f.putAll(extra);

            Resp r = req("/?_type=vueData&_tag=vue_dualwan_data&_=" + System.currentTimeMillis(), f, 20);
            String err = respErr(r.body);
            if (r.status != 200 || err.length() > 0) {
                return "{\"ok\":false,\"logged\":true,\"error\":\"路由器拒绝了这次修改（"
                        + (err.length() > 0 ? err : ("HTTP " + r.status)) + ")\"}";
            }

            // 复查：要改的字段真的变了才算成功
            int nowSec = -1, nowMain = -1;
            try {
                Resp chk = req("/?_type=hiddenData&_tag=vue_internet_eth_data&_=" + System.currentTimeMillis(), null, 10);
                Map<String, String> cb = firstTag(chk.body == null ? "" : chk.body, "OBJ_DUALWAN_BASIC_ID");
                Map<String, String> cw = firstTag(chk.body == null ? "" : chk.body, "OBJ_WANLAN_ID");
                nowSec = (int) Double.parseDouble(pick(nz(cb.get("SecWanLink")), "-1"));
                nowMain = (int) Double.parseDouble(pick(nz(cw.get("WANSelect")), "-1"));
            } catch (Exception ignore) { }
            String secName = nz(ports.get(finalSec).get("name"));
            String mainName = nz(ports.get(finalMain).get("name"));
            if (target >= 0 && nowSec != target) {
                return "{\"ok\":false,\"logged\":true,\"error\":\"路由器没有接受 WAN2 换口（仍是 "
                        + (nowSec >= 0 && nowSec < ports.size() ? nz(ports.get(nowSec).get("name")) : String.valueOf(nowSec))
                        + " 口）。这台固件可能要求在原版管理页里改，或有 IPTV/端口绑定占着这个口。\"}";
            }
            if (newMain >= 0 && nowMain != newMain) {
                return "{\"ok\":false,\"logged\":true,\"error\":\"路由器没有接受 WAN1 换口（仍是 "
                        + (nowMain >= 0 && nowMain < ports.size() ? nz(ports.get(nowMain).get("name")) : String.valueOf(nowMain))
                        + " 口）。这台固件可能要求在原版管理页里改。\"}";
            }
            String msg = "";
            if (newMain >= 0) msg = "WAN1 已设为 " + mainName + " 口";
            if (target >= 0) msg = (msg.length() > 0 ? msg + "、" : "") + "WAN2 已设为 " + secName + " 口";
            return "{\"ok\":true,\"changed\":true,\"sec\":" + finalSec + ",\"main\":" + finalMain
                    + ",\"name\":" + jstr(secName) + ",\"enabled\":" + (enabled ? "true" : "false")
                    + ",\"msg\":" + jstr(msg.length() > 0 ? msg : "已应用") + ",\"logged\":true}";
        } catch (Exception e) {
            return "{\"ok\":false,\"logged\":true,\"error\":" + jstr(msg(e)) + "}";
        }
    }

    /** 修改管理员（后台登录）密码 */
    public synchronized String adminPwdJson(String arg) {
        try {
            String old = argStr(arg, "old");
            String nw = argStr(arg, "new");
            if (old.isEmpty()) return "{\"ok\":false,\"error\":\"请输入当前密码\",\"logged\":true}";
            if (nw.length() < 6) return "{\"ok\":false,\"error\":\"新密码至少 6 位\",\"logged\":true}";
            if (nw.length() > 63) return "{\"ok\":false,\"error\":\"新密码最长 63 位\",\"logged\":true}";
            if (nw.equals(old)) return "{\"ok\":false,\"error\":\"新密码和当前密码一样\",\"logged\":true}";

            String user = "admin";
            try {
                String txt = fetchText("/?_type=vueData&_tag=user_info_data&_=" + System.currentTimeMillis());
                String u = nz(str(firstTag(txt, "OBJ_USERINFO_ID").get("Username")));
                if (!u.isEmpty()) user = u;
            } catch (Exception ignore) { }

            String a = rand16(), b = rand16();
            LinkedHashMap<String, String> f = new LinkedHashMap<String, String>();
            f.put("IF_ACTION", "Apply");
            f.put("_InstID", "IGD.AU1");
            f.put("Username", user);
            f.put("Right", "1");
            f.put("Password", encPara(old, a, b));
            f.put("NewPassword", encPara(nw, a, b));
            f.put("encode", encKey(a, b));
            Resp r = req("/?_type=vueData&_tag=user_info_data&_=" + System.currentTimeMillis(), f, 20);
            String err = respErr(r.body);
            if (r.status != 200 || err.length() > 0) {
                String low = err.toLowerCase();
                if (low.contains("pwd") || low.contains("pass") || low.contains("auth")) {
                    return "{\"ok\":false,\"logged\":true,\"error\":\"当前密码不对，路由器拒绝了这次修改\"}";
                }
                return "{\"ok\":false,\"logged\":true,\"error\":\"修改失败（"
                        + (err.length() > 0 ? err : ("HTTP " + r.status)) + ")\"}";
            }
            adminPwd = nw;   // 记住新密码，掉线自动重登才不会用旧的
            return "{\"ok\":true,\"user\":" + jstr(user) + ",\"msg\":\"管理员密码已修改\",\"logged\":true}";
        } catch (NotLogged nl) {
            throw new RuntimeException("NOT_LOGGED");
        } catch (Exception e) {
            return "{\"ok\":false,\"logged\":true,\"error\":" + jstr(msg(e)) + "}";
        }
    }

    private static String candJson(String[] r) {
        boolean dflt = "80".equals(r[1]) || "443".equals(r[1]);
        String url = ("443".equals(r[1]) ? "https://" : "http://") + r[0]
                + (dflt ? "" : ":" + r[1]);
        return "{\"ip\":" + jstr(r[0]) + ",\"port\":" + r[1] + ",\"ms\":" + r[2]
                + ",\"isGw\":" + ("1".equals(r[3]) ? "true" : "false")
                + ",\"url\":" + jstr(url) + "}";
    }

    /** TCP + TLS 握手耗时（带 SNI），比请求页面更接近真实首包延迟 */
    private static int tlsMs(String host, int port, int timeoutMs) throws IOException {
        long t0 = System.currentTimeMillis();
        java.net.Socket s = new java.net.Socket();
        try {
            s.connect(new java.net.InetSocketAddress(host, port), timeoutMs);
            javax.net.ssl.SSLSocket ss = (javax.net.ssl.SSLSocket)
                    trustAll().createSocket(s, host, port, true);
            try {
                ss.startHandshake();
            } finally {
                try { ss.close(); } catch (Exception ignored) {}
            }
        } finally {
            try { s.close(); } catch (Exception ignored) {}
        }
        return (int) (System.currentTimeMillis() - t0);
    }

    private static int chNum(String s) {
        try {
            return (int) Math.round(Double.parseDouble(nz(s).trim()));
        } catch (Exception e) {
            return 0;
        }
    }

    /** 扫描周边 AP：返回 {ssid, channel, rssi, band} 列表；固件不支持时返回空并给原因 */
    private String scanApsJson(StringBuilder errOut, java.util.List<String[]> out) {
        String last = "固件未提供无线扫描接口";
        String[][] q = {{"vue_scanap_data", "vueData"}, {"netwlanscan_data", "hiddenData"}};
        for (String[] t : q) {
            try {
                Map<String, List<Map<String, String>>> g = fetch("/?_type=" + t[1] + "&_tag=" + t[0]
                        + "&_=" + System.currentTimeMillis());
                for (List<Map<String, String>> items : g.values()) {
                    for (Map<String, String> it : items) {
                        int ch = chNum(pick(it.get("Channel"), it.get("ChanNum")));
                        if (ch <= 0) continue;
                        String ssid = pick(pick(nz(it.get("SSID")), nz(it.get("ESSID"))), nz(it.get("WlanName")));
                        int rssi = chNum(pick(pick(it.get("RSSI"), it.get("Signal")), nz(it.get("SignalStrength"))));
                        if (rssi == 0) rssi = -100;
                        out.add(new String[]{ssid, String.valueOf(ch), String.valueOf(rssi)});
                    }
                }
                if (!out.isEmpty()) return "";
                last = "接口返回里没有可解析的 AP 信息";
            } catch (Exception e) {
                last = msg(e);
            }
        }
        return last;
    }

    private static int chScore(int ch, java.util.List<String[]> aps, String band) {
        double total = 0;
        for (String[] a : aps) {
            int c = chNum(a[1]);
            boolean is24 = c <= 14;
            if (!band.equals(is24 ? "2.4G" : "5G")) continue;
            int rssi = chNum(a[2]);
            if (is24) {
                if (Math.abs(c - ch) <= 4) total += Math.max(1, rssi + 100);
            } else if (c == ch) {
                total += Math.max(1, rssi + 100);
            }
        }
        return (int) Math.round(total);
    }

    public synchronized String optimizeJson() {
        try {
            Map<String, Object> wm = asMap(MiniJson.parse(wifiMgrJson()));
            if (!"true".equals(String.valueOf(wm.get("ok")))) {
                return "{\"ok\":false,\"error\":" + jstr(nz(str(wm.get("error")))) + "}";
            }
            java.util.List<String[]> aps = new ArrayList<String[]>();
            StringBuilder scanErr = new StringBuilder();
            String err = scanApsJson(scanErr, aps);

            StringBuilder bands = new StringBuilder("[");
            StringBuilder rec = new StringBuilder("[");
            StringBuilder tips = new StringBuilder("[");
            int nTips = 0;
            for (Object o : jlist(wm.get("bands"))) {
                Map<String, Object> b = asMap(o);
                String band = nz(str(b.get("band")));
                int now = chNum(pick(nz(str(b.get("inuse"))), nz(str(b.get("channel")))));
                boolean auto = "true".equals(String.valueOf(b.get("auto")));
                String bw = nz(str(b.get("bw")));
                if (bands.length() > 1) bands.append(',');
                bands.append("{\"band\":").append(jstr(band))
                        .append(",\"channel\":").append(now)
                        .append(",\"auto\":").append(auto)
                        .append(",\"bw\":").append(jstr(bw))
                        .append(",\"std\":").append(jstr(nz(str(b.get("std")))))
                        .append(",\"on\":").append("true".equals(String.valueOf(b.get("on"))))
                        .append(",\"level\":").append(jstr(nz(str(b.get("level")))))
                        .append('}');

                java.util.List<Integer> cand = new ArrayList<Integer>();
                Map<String, Object> chs = asMap(wm.get("channels"));
                for (Object c : jlist(chs.get(band))) {
                    int v = chNum(str(c));
                    if (v > 0) cand.add(v);
                }
                if (cand.isEmpty()) {
                    if ("2.4G".equals(band)) { cand.add(1); cand.add(6); cand.add(11); }
                    else { cand.add(36); cand.add(44); cand.add(149); cand.add(157); }
                }
                int best = cand.get(0), bestScore = Integer.MAX_VALUE;
                for (int c : cand) {
                    int s = chScore(c, aps, band);
                    if (s < bestScore) { bestScore = s; best = c; }
                }
                int nowScore = now > 0 ? chScore(now, aps, band) : 0;
                boolean worth = now > 0 && now != best && (nowScore - bestScore) >= 20;
                if (rec.length() > 1) rec.append(',');
                rec.append("{\"band\":").append(jstr(band))
                        .append(",\"channel\":").append(best)
                        .append(",\"score\":").append(bestScore)
                        .append(",\"nowChannel\":").append(now)
                        .append(",\"nowScore\":").append(nowScore)
                        .append(",\"worth\":").append(worth).append('}');

                if (auto) {
                    if (nTips++ > 0) tips.append(',');
                    tips.append("{\"level\":\"ok\",\"text\":").append(jstr(band + " 用自动信道，路由器会自己躲开干扰")).append('}');
                }
                if ("2.4G".equals(band) && bw.startsWith("40")) {
                    if (nTips++ > 0) tips.append(',');
                    tips.append("{\"level\":\"warn\",\"text\":")
                            .append(jstr("2.4G 用了 40MHz 频宽，邻居多时更容易卡；改成 20MHz 通常更稳")).append('}');
                }
            }
            bands.append(']');
            rec.append(']');

            if (nTips++ > 0) tips.append(',');
            tips.append("{\"level\":\"").append(aps.isEmpty() ? "warn" : "ok").append("\",\"text\":")
                    .append(jstr(aps.isEmpty()
                            ? "这台固件没提供周边 Wi-Fi 扫描（" + (err.isEmpty() ? "接口不可用" : err) + "），只给通用建议"
                            : "扫描到 " + aps.size() + " 个周边 Wi-Fi，已按信道拥挤度给出推荐"))
                    .append('}');
            tips.append(']');

            StringBuilder apJson = new StringBuilder("[");
            int cnt = 0;
            for (String[] a : aps) {
                if (cnt >= 12) break;
                if (cnt++ > 0) apJson.append(',');
                int ch = chNum(a[1]);
                apJson.append("{\"ssid\":").append(jstr(a[0]))
                        .append(",\"channel\":").append(ch)
                        .append(",\"rssi\":").append(chNum(a[2]))
                        .append(",\"band\":").append(jstr(ch <= 14 ? "2.4G" : "5G")).append('}');
            }
            apJson.append(']');

            return "{\"ok\":true,\"bands\":" + bands + ",\"rec\":" + rec
                    + ",\"scan\":{\"ok\":" + !aps.isEmpty() + ",\"total\":" + aps.size()
                    + ",\"aps\":" + apJson + ",\"err\":" + jstr(err) + "}"
                    + ",\"tips\":" + tips + "}";
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":" + jstr(msg(e)) + "}";
        }
    }

    /** 私网地址判断：桥接/路由模式的区分要看网关是不是内网 */
    private static boolean isPrivateIp(String ip) {
        String s0 = nz(ip).trim();
        String[] p = s0.split("\\.");
        if (p.length != 4) return false;
        try {
            int a = Integer.parseInt(p[0]), b = Integer.parseInt(p[1]);
            return a == 10 || (a == 172 && b >= 16 && b <= 31) || (a == 192 && b == 168)
                    || (a == 100 && b >= 64 && b <= 127);
        } catch (Exception e) {
            return false;
        }
    }

    private static int tcpMs(String host, int port, int timeoutMs) throws IOException {
        long t0 = System.currentTimeMillis();
        java.net.Socket s = new java.net.Socket();
        try {
            s.connect(new java.net.InetSocketAddress(host, port), timeoutMs);
        } finally {
            try { s.close(); } catch (Exception ignored) {}
        }
        return (int) (System.currentTimeMillis() - t0);
    }

    private static String diagItem(String k, String name, String level, String detail, String tip, boolean comma) {
        return (comma ? "," : "") + "{\"k\":" + jstr(k) + ",\"name\":" + jstr(name)
                + ",\"level\":" + jstr(level) + ",\"detail\":" + jstr(detail)
                + ",\"tip\":" + jstr(tip) + "}";
    }

    public synchronized String netDiagJson() {
        StringBuilder items = new StringBuilder("[");
        int n = 0, bad = 0, warn = 0;

        // 1) 到路由器
        try {
            long t0 = System.currentTimeMillis();
            Resp r = req("/?_type=loginsceneData&_tag=login_token_json", null, 6);
            int ms = (int) (System.currentTimeMillis() - t0);
            boolean ok = r.status == 200 && ms < 1500;
            if (!ok) warn++;
            items.append(diagItem("router", "手机到路由器", ok ? "ok" : "warn",
                    "响应 " + ms + " ms（HTTP " + r.status + "）",
                    ok ? "" : "延迟偏高，看看 Wi-Fi 信号格数或换成 5G 频段", n++ > 0));
        } catch (Exception e) {
            bad++;
            items.append(diagItem("router", "手机到路由器", "bad", "连不上：" + msg(e),
                    "确认手机连着这台路由的 Wi-Fi", n++ > 0));
        }

        // 2) 宽带连接
        try {
            Map<String, List<Map<String, String>>> g = fetch("/?_type=vueData&_tag=vue_internet_data&_="
                    + System.currentTimeMillis());
            Map<String, String> it = new LinkedHashMap<String, String>();
            for (List<Map<String, String>> rows : g.values()) {
                for (Map<String, String> x : rows) {
                    if (x.containsKey("ConnStatus") || x.containsKey("IPAddress")) { it = x; break; }
                }
                if (!it.isEmpty()) break;
            }
            String cs = nz(it.get("ConnStatus")).trim();
            String ip = nz(it.get("IPAddress")).trim();
            String gw = nz(it.get("GateWay")).trim();
            String dns1 = nz(it.get("DNS1")).trim();
            String ct = nz(it.get("ConnType")).trim();
            boolean ok = (!ip.isEmpty() && !"0.0.0.0".equals(ip))
                    || cs.toLowerCase().startsWith("connect") || "up".equalsIgnoreCase(cs);
            if (!ok) bad++;
            items.append(diagItem("wan", "宽带连接", ok ? "ok" : "bad",
                    "状态 " + (cs.isEmpty() ? "未知" : cs) + " · 类型 " + (ct.isEmpty() ? "-" : ct)
                            + " · IP " + (ip.isEmpty() ? "-" : ip) + " · 网关 " + (gw.isEmpty() ? "-" : gw)
                            + " · DNS " + (dns1.isEmpty() ? "-" : dns1),
                    ok ? "" : "路由器没拿到公网地址：检查光猫电源/网线，或在「网络」页重新拨号", n++ > 0));
        } catch (Exception e) {
            warn++;
            items.append(diagItem("wan", "宽带连接", "warn", "读取失败：" + msg(e), "登录后点「重新检测」", n++ > 0));
        }

        // 3) 域名解析
        try {
            long t0 = System.currentTimeMillis();
            java.net.InetAddress.getAllByName("www.baidu.com");
            int ms = (int) (System.currentTimeMillis() - t0);
            boolean ok = ms < 800;
            if (!ok) warn++;
            items.append(diagItem("dns", "域名解析", ok ? "ok" : "warn",
                    "www.baidu.com 解析耗时 " + ms + " ms",
                    ok ? "" : "解析偏慢，可在「局域网」里把 DNS 改成 223.5.5.5", n++ > 0));
        } catch (Exception e) {
            bad++;
            items.append(diagItem("dns", "域名解析", "bad", "解析失败：" + msg(e),
                    "能连 Wi-Fi 但网页打不开、微信还能发消息，多半是 DNS 问题", n++ > 0));
        }

        // 4) 外网连通
        try {
            int ms = tcpMs("mirrors.aliyun.com", 443, 3000);
            boolean ok = ms < 400;
            if (!ok) warn++;
            items.append(diagItem("inet", "外网连通", ok ? "ok" : "warn",
                    "连 mirrors.aliyun.com:443 耗时 " + ms + " ms",
                    ok ? "" : "外网延迟偏高，可能是运营商线路问题", n++ > 0));
        } catch (Exception e) {
            bad++;
            items.append(diagItem("inet", "外网连通", "bad", "连不上外网：" + msg(e),
                    "Wi-Fi 正常但上不了网，常见是宽带欠费或光猫故障", n++ > 0));
        }

        // 5) 局域网
        try {
            Map<String, Object> lan = asMap(MiniJson.parse(lanJson()));
            String dh = String.valueOf(lan.get("dhcpOn"));   // true / false / null
            boolean known = "true".equals(dh) || "false".equals(dh);
            boolean ok = "true".equals(dh);
            if (known && !ok) warn++;
            items.append(diagItem("lan", "局域网", !known ? "ok" : (ok ? "ok" : "warn"),
                    "地址 " + pick(nz(str(lan.get("ip"))), "-") + " · DHCP "
                            + (!known ? "状态未知" : (ok ? "已开启" : "未开启"))
                            + " · 地址池 " + pick(nz(str(lan.get("min"))), "-") + "-" + pick(nz(str(lan.get("max"))), "-"),
                    (known && !ok) ? "DHCP 关着的话，新设备得手动配 IP 才能上网" : "", n++ > 0));
        } catch (Exception e) {
            warn++;
            items.append(diagItem("lan", "局域网", "warn", "读取失败：" + msg(e), "", n++ > 0));
        }

        items.append(']');
        String summary;
        if (bad > 0) summary = bad + " 项异常" + (warn > 0 ? "、" + warn + " 项需留意" : "");
        else if (warn > 0) summary = warn + " 项需留意";
        else summary = "各项都正常";
        return "{\"ok\":true,\"items\":" + items + ",\"summary\":" + jstr(summary)
                + ",\"ts\":" + (System.currentTimeMillis() / 1000) + "}";
    }

    // ---------------- XML / 工具 ----------------

    public static Map<String, List<Map<String, String>>> groups(String text) {
        Map<String, List<Map<String, String>>> out = new LinkedHashMap<String, List<Map<String, String>>>();
        if (text == null) return out;
        Matcher m = Pattern.compile("<(OBJ_[A-Z0-9_]+)>(.*?)</\\1>", Pattern.DOTALL).matcher(text);
        while (m.find()) {
            List<Map<String, String>> items = new ArrayList<Map<String, String>>();
            Matcher im = Pattern.compile("<Instance>(.*?)</Instance>", Pattern.DOTALL).matcher(m.group(2));
            while (im.find()) {
                String block = im.group(1);
                List<String> names = findAll(block, "<ParaName>(.*?)</ParaName>");
                List<String> vals = findAll(block, "<ParaValue>(.*?)</ParaValue>");
                Map<String, String> item = new LinkedHashMap<String, String>();
                int n = Math.min(names.size(), vals.size());
                for (int i = 0; i < n; i++) item.put(names.get(i).trim(), unescape(vals.get(i)));
                items.add(item);
            }
            if (items.isEmpty()) {
                Matcher fm = Pattern.compile("<([A-Za-z0-9_]+)>([^<]*)</\\1>", Pattern.DOTALL)
                        .matcher(m.group(2));
                Map<String, String> flat = new LinkedHashMap<String, String>();
                while (fm.find()) flat.put(fm.group(1), unescape(fm.group(2)));
                if (!flat.isEmpty()) items.add(flat);
            }
            List<Map<String, String>> cur = out.get(m.group(1));
            if (cur == null) out.put(m.group(1), items);
            else cur.addAll(items);
        }
        return out;
    }

    private static List<String> findAll(String s, String regex) {
        List<String> out = new ArrayList<String>();
        Matcher m = Pattern.compile(regex, Pattern.DOTALL).matcher(s);
        while (m.find()) out.add(m.group(1));
        return out;
    }

    public static String xmlField(String text, String tag) {
        if (text == null) return null;
        Matcher m = Pattern.compile("<" + tag + ">(.*?)</" + tag + ">", Pattern.DOTALL).matcher(text);
        return m.find() ? unescape(m.group(1)) : null;
    }

    private static String unescape(String s) {
        if (s == null || s.indexOf('&') < 0) return s;
        StringBuilder sb = new StringBuilder(s.length());
        for (int i = 0; i < s.length(); i++) {
            char ch = s.charAt(i);
            if (ch != '&') { sb.append(ch); continue; }
            int semi = s.indexOf(';', i);
            if (semi < 0 || semi - i > 10) { sb.append(ch); continue; }
            String ent = s.substring(i + 1, semi);
            if (ent.equals("amp")) sb.append('&');
            else if (ent.equals("lt")) sb.append('<');
            else if (ent.equals("gt")) sb.append('>');
            else if (ent.equals("quot")) sb.append('"');
            else if (ent.equals("apos")) sb.append('\'');
            else if (ent.startsWith("#x") || ent.startsWith("#X")) {
                try { sb.append((char) Integer.parseInt(ent.substring(2), 16)); } catch (Exception e) { sb.append('&').append(ent).append(';'); }
            } else if (ent.startsWith("#")) {
                try { sb.append((char) Integer.parseInt(ent.substring(1))); } catch (Exception e) { sb.append('&').append(ent).append(';'); }
            } else {
                sb.append('&').append(ent).append(';');
            }
            i = semi;
        }
        return sb.toString();
    }

    private static String fmtDur(String sec) {
        if (sec == null || sec.trim().isEmpty()) return "—";
        long s;
        try {
            s = (long) Double.parseDouble(sec.trim());
        } catch (Exception e) {
            return "—";
        }
        long d = s / 86400, h = (s % 86400) / 3600, m = (s % 3600) / 60;
        if (d > 0) return d + " 天 " + h + " 小时";
        if (h > 0) return h + " 小时 " + m + " 分";
        return m + " 分钟";
    }

    private static String bandOf(String inst) {
        if (inst.endsWith("AP1")) return "2.4G";
        if (inst.endsWith("AP5")) return "5G";
        return inst;
    }

    private static Map<String, String> first(Map<String, List<Map<String, String>>> g, String key) {
        List<Map<String, String>> l = g.get(key);
        return (l == null || l.isEmpty()) ? new LinkedHashMap<String, String>() : l.get(0);
    }

    private static List<Map<String, String>> list(Map<String, List<Map<String, String>>> g, String key) {
        List<Map<String, String>> l = g.get(key);
        return l == null ? new ArrayList<Map<String, String>>() : l;
    }

    private static String get(Map<String, Map<String, String>> m, String key, String field) {
        Map<String, String> x = m.get(key);
        return x == null ? null : x.get(field);
    }

    private static String reverse(String s) {
        return new StringBuilder(s).reverse().toString();
    }

    private static byte[] slice(byte[] a, int n) {
        byte[] out = new byte[Math.min(n, a.length)];
        System.arraycopy(a, 0, out, 0, out.length);
        return out;
    }

    private static boolean allAscii(String s) {
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c < 32 || c > 126) return false;
        }
        return true;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object o) {
        if (o instanceof Map) return (Map<String, Object>) o;
        return new LinkedHashMap<String, Object>();
    }

    private static String str(Object o) {
        return o == null ? null : String.valueOf(o);
    }

    private static double num(Object o) {
        if (o instanceof Number) return ((Number) o).doubleValue();
        try { return Double.parseDouble(String.valueOf(o)); } catch (Exception e) { return 0; }
    }

    private static boolean isTrue(Object o) {
        if (o instanceof Boolean) return (Boolean) o;
        String s = String.valueOf(o);
        return "true".equalsIgnoreCase(s) || "1".equals(s);
    }

    private static String nz(String s) {
        return s == null ? "" : s;
    }

    private static String pick(String a, String b) {
        return (a == null || a.isEmpty()) ? (b == null ? "" : b) : a;
    }

    private static String msg(Throwable e) {
        String cn = e.getClass().getSimpleName();
        String m = e.getMessage();
        String raw = (m == null || m.isEmpty()) ? cn : m;
        // 常见网络错误翻成人话，并带上排查方向
        String low = raw.toLowerCase();
        if (e instanceof java.net.SocketTimeoutException || low.contains("timeout")) {
            return "连接超时：地址能连上但没有回应，多半不是路由器的管理地址（检查是否填成别的设备的 IP）";
        }
        if (low.contains("connection refused")) {
            return "连接被拒绝：这个地址上没有开启管理服务，检查 IP 和端口";
        }
        if (low.contains("unreachable") || low.contains("network is unreachable")) {
            return "网络不可达：手机当前网络到不了这个地址（在外面请配置远程地址）";
        }
        if (low.contains("unknownhost") || low.contains("no address")) {
            return "域名解析失败：检查地址拼写";
        }
        if (low.contains("ssl") || low.contains("handshake")) {
            return "加密握手失败：地址可能不是路由器的管理页面";
        }
        return raw;
    }

    private static void sleep(long ms) {
        try { Thread.sleep(ms); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
    }

    public static String jstr(String s) {
        if (s == null) return "null";
        StringBuilder sb = new StringBuilder(s.length() + 16);
        sb.append('"');
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"': sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\n': sb.append("\\n"); break;
                case '\r': sb.append("\\r"); break;
                case '\t': sb.append("\\t"); break;
                default:
                    if (c < 0x20) sb.append(String.format("\\u%04x", (int) c));
                    else sb.append(c);
            }
        }
        sb.append('"');
        return sb.toString();
    }

    // ---------------- Base64（不依赖 Android API） ----------------

    private static final char[] B64 =
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/".toCharArray();

    public static String b64e(byte[] in) {
        StringBuilder sb = new StringBuilder((in.length + 2) / 3 * 4);
        int i = 0;
        while (i + 2 < in.length) {
            int n = ((in[i] & 0xff) << 16) | ((in[i + 1] & 0xff) << 8) | (in[i + 2] & 0xff);
            sb.append(B64[(n >> 18) & 63]).append(B64[(n >> 12) & 63])
              .append(B64[(n >> 6) & 63]).append(B64[n & 63]);
            i += 3;
        }
        int rem = in.length - i;
        if (rem == 1) {
            int n = (in[i] & 0xff) << 16;
            sb.append(B64[(n >> 18) & 63]).append(B64[(n >> 12) & 63]).append("==");
        } else if (rem == 2) {
            int n = ((in[i] & 0xff) << 16) | ((in[i + 1] & 0xff) << 8);
            sb.append(B64[(n >> 18) & 63]).append(B64[(n >> 12) & 63])
              .append(B64[(n >> 6) & 63]).append('=');
        }
        return sb.toString();
    }

    public static byte[] b64d(String s) {
        if (s == null) return new byte[0];
        String t = s.replaceAll("\\s", "");
        int pad = 0;
        while (t.endsWith("=")) { t = t.substring(0, t.length() - 1); pad++; }
        ByteArrayOutputStream bos = new ByteArrayOutputStream(t.length() * 3 / 4 + 3);
        int buf = 0, bits = 0;
        for (int i = 0; i < t.length(); i++) {
            int v = index(t.charAt(i));
            if (v < 0) continue;
            buf = (buf << 6) | v;
            bits += 6;
            if (bits >= 8) {
                bits -= 8;
                bos.write((buf >> bits) & 0xff);
            }
        }
        return bos.toByteArray();
    }

    private static int index(char c) {
        if (c >= 'A' && c <= 'Z') return c - 'A';
        if (c >= 'a' && c <= 'z') return c - 'a' + 26;
        if (c >= '0' && c <= '9') return c - '0' + 52;
        if (c == '+') return 62;
        if (c == '/') return 63;
        return -1;
    }

    // ---------------- 极简 JSON 解析（只用于表单入参） ----------------

    public static class MiniJson {
        private final String s;
        private int i;

        private MiniJson(String s) { this.s = s; }

        public static Object parse(String s) {
            MiniJson p = new MiniJson(s == null ? "" : s);
            p.ws();
            Object v = p.value();
            return v;
        }

        private void ws() {
            while (i < s.length() && Character.isWhitespace(s.charAt(i))) i++;
        }

        private Object value() {
            ws();
            if (i >= s.length()) return null;
            char c = s.charAt(i);
            if (c == '{') return obj();
            if (c == '[') return arr();
            if (c == '"') return str();
            if (s.startsWith("true", i)) { i += 4; return Boolean.TRUE; }
            if (s.startsWith("false", i)) { i += 5; return Boolean.FALSE; }
            if (s.startsWith("null", i)) { i += 4; return null; }
            int st = i;
            while (i < s.length() && "-+.eE0123456789".indexOf(s.charAt(i)) >= 0) i++;
            try { return Double.valueOf(s.substring(st, i)); } catch (Exception e) { return null; }
        }

        private Map<String, Object> obj() {
            Map<String, Object> m = new LinkedHashMap<String, Object>();
            i++; // {
            ws();
            if (i < s.length() && s.charAt(i) == '}') { i++; return m; }
            while (i < s.length()) {
                ws();
                if (i >= s.length() || s.charAt(i) != '"') break;
                String k = str();
                ws();
                if (i < s.length() && s.charAt(i) == ':') i++;
                m.put(k, value());
                ws();
                if (i < s.length() && s.charAt(i) == ',') { i++; continue; }
                if (i < s.length() && s.charAt(i) == '}') { i++; }
                break;
            }
            return m;
        }

        private List<Object> arr() {
            List<Object> l = new ArrayList<Object>();
            i++;
            ws();
            if (i < s.length() && s.charAt(i) == ']') { i++; return l; }
            while (i < s.length()) {
                l.add(value());
                ws();
                if (i < s.length() && s.charAt(i) == ',') { i++; continue; }
                if (i < s.length() && s.charAt(i) == ']') { i++; }
                break;
            }
            return l;
        }

        private String str() {
            StringBuilder sb = new StringBuilder();
            i++; // "
            while (i < s.length()) {
                char c = s.charAt(i++);
                if (c == '"') break;
                if (c == '\\' && i < s.length()) {
                    char e = s.charAt(i++);
                    switch (e) {
                        case 'n': sb.append('\n'); break;
                        case 'r': sb.append('\r'); break;
                        case 't': sb.append('\t'); break;
                        case 'b': sb.append('\b'); break;
                        case 'f': sb.append('\f'); break;
                        case 'u':
                            if (i + 4 <= s.length()) {
                                sb.append((char) Integer.parseInt(s.substring(i, i + 4), 16));
                                i += 4;
                            }
                            break;
                        default: sb.append(e);
                    }
                } else {
                    sb.append(c);
                }
            }
            return sb.toString();
        }
    }
}
