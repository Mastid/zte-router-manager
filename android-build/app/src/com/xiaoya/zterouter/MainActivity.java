package com.xiaoya.zterouter;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.DialogInterface;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.net.ConnectivityManager;
import android.net.NetworkInfo;
import android.os.Build;
import android.os.Bundle;
import android.os.SystemClock;
import android.text.InputType;
import android.util.Base64;
import android.util.DisplayMetrics;
import android.view.KeyEvent;
import android.webkit.JsPromptResult;
import android.webkit.JsResult;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;

import org.json.JSONObject;

import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.util.Collections;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 单页外壳：界面用内置 HTML（复用已在电脑上验证过的面板），
 * 网络与加密走 ZteClient（纯 Java，已在桌面 JVM 上验证过加解密）。
 */
public class MainActivity extends Activity {

    private WebView web;
    private ZteClient client;
    private SharedPreferences prefs;
    private long appStartMs;

    @SuppressLint({"SetJavaScriptEnabled", "AddJavascriptInterface"})
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        appStartMs = SystemClock.elapsedRealtime();
        prefs = getSharedPreferences("router", MODE_PRIVATE);
        client = new ZteClient("192.168.5.1");
        // 双地址：家里 Wi-Fi 直连 + 外网隧道地址，启动时自动选通的那个
        client.setCandidates(
                prefs.getString("hostLocal", prefs.getString("host", "192.168.5.1")),
                prefs.getString("hostRemote", ""),
                prefs.getString("hostKind", "lan"));
        // 清理后台 / Activity 重建后把上次的会话与密码接回来，
        // 页面问 /api/state 时会自动校验并静默重登，不用用户再输密码。
        client.importSession(prefs.getString("session", ""));
        client.setSavedPwd(unpack(prefs.getString("pwd", "")));

        web = new WebView(this);
        web.setBackgroundColor(isNight() ? 0xFF0C1219 : 0xFFF4F6FA);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(true);
        try {
            // file:// 页面下脚本可能被当作不透明源，这两项可避免存储类 API 抛 SecurityError
            s.setAllowFileAccessFromFileURLs(true);
            s.setAllowUniversalAccessFromFileURLs(true);
        } catch (Throwable ignored) {
        }
        s.setLoadsImagesAutomatically(true);
        s.setSupportZoom(false);
        s.setUseWideViewPort(true);
        s.setLoadWithOverviewMode(false);
        s.setTextZoom(100);

        web.setWebViewClient(new WebViewClient());
        web.setWebChromeClient(new Chrome());
        web.addJavascriptInterface(new Bridge(), "Z");

        try {
            WebView.setWebContentsDebuggingEnabled(true);   // 方便 chrome://inspect 调试
        } catch (Throwable ignored) {
        }

        setContentView(web);
        web.loadUrl("file:///android_asset/index.html");
    }

    /**
     * 返回键：先交给页面「返回上一级」（关弹层 → 回上一个页面），
     * 页面已经在首页时再退出应用。页面侧 window.__back() 同步返回 true/false。
     */
    private boolean backPending = false;

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK && web != null) {
            if (backPending) return true;          // 连按只处理一次，避免重复退出
            backPending = true;
            web.evaluateJavascript(
                    "(function(){try{return window.__back?window.__back():false}catch(e){return false}})()",
                    new ValueCallback<String>() {
                        @Override
                        public void onReceiveValue(String v) {
                            backPending = false;
                            if (!"true".equals(v)) finish();
                        }
                    });
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    /** 手机切换深色/浅色时（manifest 已声明 configChanges=uiMode，不会重建 Activity） */
    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        super.onConfigurationChanged(newConfig);
        boolean dark = isNight();
        if (web != null) {
            web.setBackgroundColor(dark ? 0xFF0C1219 : 0xFFF4F6FA);
            // 页面自己判断是"跟随系统"还是手动指定，这里只负责通知
            web.evaluateJavascript("window.__sysTheme && window.__sysTheme()", null);
        }
    }

    private boolean isNight() {
        int mode = getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK;
        return mode == Configuration.UI_MODE_NIGHT_YES;
    }

    /**
     * 路由器密码要留在本地才能"清理后台后不用重登"。
     * SharedPreferences 本来就在应用私有目录，这里再叠一层异或+Base64，
     * 挡住用备份/文件管理器直接翻出明文的情况。
     */
    private static String pack(String s) {
        if (s == null || s.isEmpty()) return "";
        try {
            byte[] b = s.getBytes("UTF-8");
            for (int i = 0; i < b.length; i++) b[i] ^= (byte) (0x37 + (i * 7) % 251);
            return Base64.encodeToString(b, Base64.NO_WRAP);
        } catch (Exception e) {
            return "";
        }
    }

    private static String unpack(String s) {
        if (s == null || s.isEmpty()) return "";
        try {
            byte[] b = Base64.decode(s, Base64.NO_WRAP);
            for (int i = 0; i < b.length; i++) b[i] ^= (byte) (0x37 + (i * 7) % 251);
            return new String(b, "UTF-8");
        } catch (Exception e) {
            return "";
        }
    }

    /** 手机型号、系统、屏幕、内核、网络、本机 IP —— 系统设置里的「本机信息」 */
    private String sysInfoJson() {
        JSONObject out = new JSONObject();
        try {
            JSONObject app = new JSONObject();
            try {
                PackageInfo pi = getPackageManager().getPackageInfo(getPackageName(), 0);
                app.put("ver", pi.versionName == null ? "" : pi.versionName);
                app.put("code", String.valueOf(pi.versionCode));
            } catch (PackageManager.NameNotFoundException ignored) {
            }
            app.put("pkg", getPackageName());
            out.put("app", app);

            JSONObject ph = new JSONObject();
            ph.put("brand", cap(Build.BRAND));
            ph.put("model", Build.MODEL == null ? "" : Build.MODEL);
            ph.put("android", Build.VERSION.RELEASE == null ? "" : Build.VERSION.RELEASE);
            ph.put("sdk", Build.VERSION.SDK_INT);
            DisplayMetrics dm = getResources().getDisplayMetrics();
            ph.put("screen", dm.widthPixels + "×" + dm.heightPixels + " · " + dm.densityDpi + "dpi");
            ph.put("engine", engineOf(WebSettings.getDefaultUserAgent(this)));
            if (Build.SUPPORTED_ABIS != null && Build.SUPPORTED_ABIS.length > 0) {
                ph.put("abi", Build.SUPPORTED_ABIS[0]);
            }
            ph.put("net", netText());
            ph.put("ip", localIp());
            ph.put("uptime", spanText((SystemClock.elapsedRealtime() - appStartMs) / 1000));
            out.put("phone", ph);

            JSONObject host = new JSONObject();
            host.put("kind", "手机 App");
            host.put("client", prefs.getString("host", "192.168.5.1"));
            out.put("host", host);

            out.put("ok", true);
            out.put("ts", System.currentTimeMillis() / 1000);
        } catch (Throwable t) {
            try {
                out.put("ok", false);
                out.put("error", String.valueOf(t));
            } catch (Throwable ignored) {
            }
        }
        return out.toString();
    }

    private static String cap(String s) {
        if (s == null || s.isEmpty()) return "";
        return Character.toUpperCase(s.charAt(0)) + s.substring(1);
    }

    private static String engineOf(String ua) {
        if (ua == null) return "WebView";
        Matcher m = Pattern.compile("Chrome/(\\d+)").matcher(ua);
        return m.find() ? ("Chrome " + m.group(1)) : "WebView";
    }

    private static String spanText(long sec) {
        long d = sec / 86400, h = (sec % 86400) / 3600, mi = (sec % 3600) / 60;
        if (d > 0) return d + " 天 " + h + " 小时";
        if (h > 0) return h + " 小时 " + mi + " 分";
        return mi + " 分钟";
    }

    private String netText() {
        try {
            ConnectivityManager cm = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
            NetworkInfo ni = cm.getActiveNetworkInfo();
            if (ni == null || !ni.isConnected()) return "离线";
            if (ni.getType() == ConnectivityManager.TYPE_WIFI) return "Wi-Fi";
            if (ni.getType() == ConnectivityManager.TYPE_MOBILE) {
                String sub = ni.getSubtypeName();
                return sub == null || sub.isEmpty() ? "移动数据" : "移动数据 " + sub;
            }
            String name = ni.getTypeName();
            return name == null ? "其他" : name;
        } catch (Throwable e) {
            return "未知";
        }
    }

    /** 优先取 wlan0 的 IPv4，没有就取第一个非回环地址 */
    private String localIp() {
        try {
            String fallback = "";
            List<NetworkInterface> all = Collections.list(NetworkInterface.getNetworkInterfaces());
            for (NetworkInterface ni : all) {
                if (!ni.isUp() || ni.isLoopback()) continue;
                for (InetAddress a : Collections.list(ni.getInetAddresses())) {
                    if (a.isLoopbackAddress() || a instanceof Inet6Address) continue;
                    String ip = a.getHostAddress();
                    if (ip == null) continue;
                    if (ni.getName() != null && ni.getName().startsWith("wlan")) return ip;
                    if (fallback.isEmpty()) fallback = ip;
                }
            }
            return fallback;
        } catch (Throwable e) {
            return "";
        }
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            web.removeJavascriptInterface("Z");
            web.destroy();
        }
        super.onDestroy();
    }

    /**
     * 页面里的 alert / confirm / prompt 必须由这里接管，
     * 默认实现直接返回 false，会导致"保存""重启"这类二次确认永远拿不到"确定"。
     */
    private class Chrome extends WebChromeClient {

        @Override
        public boolean onJsAlert(WebView v, String url, String message, final JsResult r) {
            new AlertDialog.Builder(MainActivity.this)
                    .setMessage(message)
                    .setPositiveButton("知道了", new DialogInterface.OnClickListener() {
                        public void onClick(DialogInterface d, int i) { r.confirm(); }
                    })
                    .setOnCancelListener(new DialogInterface.OnCancelListener() {
                        public void onCancel(DialogInterface d) { r.cancel(); }
                    })
                    .show();
            return true;
        }

        @Override
        public boolean onJsConfirm(WebView v, String url, String message, final JsResult r) {
            new AlertDialog.Builder(MainActivity.this)
                    .setMessage(message)
                    .setPositiveButton("确定", new DialogInterface.OnClickListener() {
                        public void onClick(DialogInterface d, int i) { r.confirm(); }
                    })
                    .setNegativeButton("取消", new DialogInterface.OnClickListener() {
                        public void onClick(DialogInterface d, int i) { r.cancel(); }
                    })
                    .setOnCancelListener(new DialogInterface.OnCancelListener() {
                        public void onCancel(DialogInterface d) { r.cancel(); }
                    })
                    .show();
            return true;
        }

        @Override
        public boolean onJsPrompt(WebView v, String url, String message, String defaultValue,
                                  final JsPromptResult r) {
            final EditText et = new EditText(MainActivity.this);
            et.setInputType(InputType.TYPE_CLASS_TEXT);
            et.setText(defaultValue == null ? "" : defaultValue);
            et.setSelection(et.getText().length());
            new AlertDialog.Builder(MainActivity.this)
                    .setMessage(message)
                    .setView(et)
                    .setPositiveButton("确定", new DialogInterface.OnClickListener() {
                        public void onClick(DialogInterface d, int i) {
                            r.confirm(et.getText().toString());
                        }
                    })
                    .setNegativeButton("取消", new DialogInterface.OnClickListener() {
                        public void onClick(DialogInterface d, int i) { r.cancel(); }
                    })
                    .setOnCancelListener(new DialogInterface.OnCancelListener() {
                        public void onCancel(DialogInterface d) { r.cancel(); }
                    })
                    .show();
            return true;
        }
    }

    /**
     * JS 侧：Z.invoke(id, method, arg)
     * 所有网络请求放在后台线程，结果通过 evaluateJavascript 回调回页面。
     */
    private class Bridge {

        /** 页面 <head> 里同步调用：系统是否深色。同步返回，避免深色手机先白闪一下。 */
        @android.webkit.JavascriptInterface
        public String sysTheme() {
            return isNight() ? "dark" : "light";
        }

        @android.webkit.JavascriptInterface
        public void invoke(final int id, final String method, final String arg) {
            new Thread(new Runnable() {
                public void run() {
                    String out;
                    try {
                        out = dispatch(method, arg);
                        afterCall(method, arg, out);
                    } catch (Throwable t) {
                        out = "{\"ok\":false,\"error\":" + ZteClient.jstr(String.valueOf(t)) + "}";
                    }
                    final String js = "window.__cb(" + id + ", " + JSONObject.quote(out) + ")";
                    runOnUiThread(new Runnable() {
                        public void run() {
                            if (web != null) web.evaluateJavascript(js, null);
                        }
                    });
                }
            }).start();
        }

        /**
         * 每次原生调用结束后把会话写回本地：
         * 路由器每次响应都会轮换令牌，所以拿到新令牌就要立刻存，不能只在登录时存一次。
         */
        private void afterCall(String method, String arg, String out) {
            try {
                if ("logout".equals(method)) {
                    prefs.edit().remove("session").remove("pwd").apply();
                    return;
                }
                if ("state".equals(method) || "diag".equals(method)
                        || "sysinfo".equals(method) || "theme".equals(method)) {
                    return;
                }
                if ("login".equals(method)) {
                    if (out == null || !out.contains("\"ok\":true")) return;
                    prefs.edit().putString("pwd", pack(arg)).apply();
                } else if (out == null || out.contains("\"logged\":false")) {
                    return;                      // 没登进去就别把废会话存下来
                }
                prefs.edit().putString("session", client.exportSession()).apply();
            } catch (Throwable ignored) {
            }
        }

        private String dispatch(String method, String arg) {
            if ("state".equals(method)) return client.stateJson();
            if ("resume".equals(method)) return client.resumeJson();
            if ("all".equals(method)) return client.allJson();
            if ("theme".equals(method)) return "{\"ok\":true,\"dark\":" + isNight() + "}";
            if ("sysinfo".equals(method)) return sysInfoJson();
            if ("login".equals(method)) return client.loginJson(arg);
            if ("wifiPwd".equals(method)) return client.wifiPwdJson(arg);
            if ("saveWifi".equals(method)) return client.saveWifiJson(arg);
            if ("reboot".equals(method)) return client.rebootJson();
            if ("diag".equals(method)) return client.diagJson();
            if ("device".equals(method)) return client.deviceJson(arg);
            if ("limits".equals(method)) return client.limitsJson();
            if ("setLimit".equals(method)) return client.setLimitJson(arg);
            if ("security".equals(method)) return client.securityJson();
            if ("securityMode".equals(method)) return client.securityModeJson(arg);
            if ("securityAcl".equals(method)) return client.aclJson(arg);
            if ("securityAuth".equals(method)) return client.securityAuthJson(arg);
            if ("lan".equals(method)) return client.lanJson();
            if ("lanSet".equals(method)) return client.lanSetJson(arg);
            if ("bind".equals(method)) return client.bindJson(arg);
            if ("sysStat".equals(method)) return client.sysStatJson();
            if ("net".equals(method)) return client.netJson();
            if ("port".equals(method)) return client.portJson(arg);
            if ("wifimgr".equals(method)) return client.wifiMgrJson();
            if ("optimize".equals(method)) return client.optimizeJson();
            if ("netdiag".equals(method)) return client.netDiagJson();
            if ("speedtest".equals(method)) return client.speedTestJson(arg);
            if ("speednodes".equals(method)) return client.speedNodesJson();
            if ("ont".equals(method)) return client.ontJson(arg);
            if ("relogin".equals(method)) return client.reloginForce();
            if ("ports".equals(method)) return client.portsLiveJson();
            if ("portsraw".equals(method)) return client.portsRawJson();
            if ("dualwan".equals(method)) return client.dualwanJson();
            if ("dualwanset".equals(method)) return client.dualwanSetJson(arg);
            if ("adminpwd".equals(method)) return client.adminPwdJson(arg);
            if ("openUrl".equals(method)) {
                // 光猫管理页这种外部地址交给系统浏览器
                try {
                    android.content.Intent it = new android.content.Intent(
                            android.content.Intent.ACTION_VIEW,
                            android.net.Uri.parse(arg == null ? "" : arg.trim()));
                    it.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK);
                    MainActivity.this.startActivity(it);
                    return "{\"ok\":true}";
                } catch (Throwable t) {
                    return "{\"ok\":false,\"error\":" + ZteClient.jstr(String.valueOf(t)) + "}";
                }
            }
            if ("wifimgrSet".equals(method)) return client.wifiMgrSetJson(arg);
            if ("conn".equals(method)) return client.connJson();
            if ("pick".equals(method)) {
                String r = client.pickJson();
                prefs.edit().putString("hostKind", client.getHostKind()).apply();
                return r;
            }
            if ("setConn".equals(method)) {
                String r = client.setConnJson(arg);
                JSONObject o;
                try { o = new JSONObject(r); } catch (Exception e) { o = new JSONObject(); }
                prefs.edit()
                        .putString("hostLocal", o.optString("local", "192.168.5.1"))
                        .putString("hostRemote", o.optString("remote", ""))
                        .putString("host", o.optString("host", "192.168.5.1"))
                        .putString("hostKind", o.optString("kind", "lan"))
                        .putString("session", "")
                        .apply();
                return r;
            }
            if ("setHost".equals(method)) {
                String h = arg == null ? "" : arg.trim();
                if (h.isEmpty()) return "{\"ok\":false,\"error\":\"地址不能为空\"}";
                String lo = ZteClient.cleanHost(h, "192.168.5.1");
                client.setCandidates(lo, prefs.getString("hostRemote", ""), "");
                prefs.edit().putString("hostLocal", lo).putString("host", lo)
                        .putString("hostKind", "lan").putString("session", "").apply();
                return "{\"ok\":true,\"host\":" + ZteClient.jstr(lo) + "}";
            }
            if ("logout".equals(method)) {
                client.forget();
                return "{\"ok\":true}";
            }
            return "{\"ok\":false,\"error\":" + ZteClient.jstr("未知方法 " + method) + "}";
        }
    }
}
