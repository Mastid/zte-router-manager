import com.xiaoya.zterouter.ZteClient;

/** 桌面验证三种真机口径下的 securityJson：
 *  real     aclrule_data 直接给 2 条 Ban      → rules=2
 *  fallback aclrule_data 空、规则在 XML 里     → rules=2
 *  broken   两个接口都 404（带 SessionTimeout）→ ok:true 且 不掉登录态 */
public class SecTest {
    public static void main(String[] a) throws Exception {
        String mode = a.length > 0 ? a[0] : "real";
        ZteClient c = new ZteClient("127.0.0.1:18443");
        String login = c.loginJson("test123");
        System.out.println("LOGIN  " + login);
        String sec = c.securityJson();
        System.out.println("SEC    " + sec);
        boolean ok = sec.contains("\"ok\":true");
        if ("real".equals(mode) || "fallback".equals(mode)) {
            ok &= sec.contains("FE:72:15:9D:45:CD") && sec.contains("DE:AF:39:52:F8:F3");
            ok &= sec.contains("\"policy\":\"Ban\"");
        } else {
            ok &= sec.contains("\"rules\":[]");
            ok &= sec.contains("NOT_LOGGED") == false;
        }
        // 关键回归：任何场景下会话都不能被 404 踢掉
        String second = c.securityJson();
        System.out.println("SEC2   " + second);
        ok &= second.contains("\"ok\":true");
        System.out.println(ok ? "PASS " + mode : "FAIL " + mode);
        if (!ok) System.exit(1);
    }
}
