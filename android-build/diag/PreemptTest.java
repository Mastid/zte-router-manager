import com.xiaoya.zterouter.ZteClient;

/** 桌面验证登录接管（login_preempt）：
 *  free     userif 正常             → 直接登录成功，无 kicked
 *  preempt  userif 先给占位页        → 自动顶掉 192.168.5.23 后登录成功 */
public class PreemptTest {
    public static void main(String[] a) throws Exception {
        String mode = a.length > 0 ? a[0] : "free";
        ZteClient c = new ZteClient("127.0.0.1:18443");
        String login = c.loginJson("test123");
        System.out.println("LOGIN  " + login);
        boolean ok = login.contains("\"ok\":true");
        if ("preempt".equals(mode)) {
            ok &= login.contains("192.168.5.23");
        } else {
            ok &= login.contains("\"kicked\":null");
        }
        // 登录后要能正常读数据
        String sec = c.securityJson();
        ok &= sec.contains("\"ok\":true");
        System.out.println("SEC    " + sec.substring(0, Math.min(120, sec.length())) + "…");
        System.out.println(ok ? "PASS " + mode : "FAIL " + mode);
        if (!ok) System.exit(1);
    }
}
