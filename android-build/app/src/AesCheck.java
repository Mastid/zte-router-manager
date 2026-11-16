import com.xiaoya.zterouter.ZteClient;

public class AesCheck {
    public static void main(String[] a) throws Exception {
        String tok = "311233939794289858975993";
        String pw = "XiaoYa_5G_pass!";
        String enc = ZteClient.encPara(pw, tok, new StringBuilder(tok).reverse().toString());
        System.out.println("java enc: " + enc);
        System.out.println("java dec: " + ZteClient.decPara(enc, tok, new StringBuilder(tok).reverse().toString()));
    }
}
