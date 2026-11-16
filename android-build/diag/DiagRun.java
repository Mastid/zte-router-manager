import com.xiaoya.zterouter.ZteClient;

/** 桌面诊断：不带密码，只报告可达性/令牌/轨迹 */
public class DiagRun {
    public static void main(String[] a) throws Exception {
        String host = a.length > 0 ? a[0] : "192.168.5.1";
        ZteClient c = new ZteClient(host);
        System.out.println(c.diagJson());
    }
}
