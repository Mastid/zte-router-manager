# -*- coding: utf-8 -*-
"""假路由器：按固件前端 chunk（chunks/4.js getAclRules）的真实口径复刻 ACL 接口。

接口口径（固件源码为准）：
- GET /?_type=vuejsonData&_tag=aclrule_data   → JSON OBJ_ACLCFG_ID[]，每条带 ACLPolicy(Ban/Allow)
- GET /?_type=vuejsonData&_tag=aclmode_data   → OBJ_ACCESSCONTROL_ID[0].AccControlMode
- GET /?_type=hiddenData&_tag=vue_macfilterrule_data → XML，OBJ_WLANAP_ID.ACLPolicy
- GET /?_type=vueData&_tag=vue_macfilterrule_data    → 404（类型不对，真机实测）

测试场景由 tls/mode.txt 控制，不用重启服务：
  real     aclrule_data 直接给 2 条 Ban 规则（正常路径）
  fallback aclrule_data 返回空数组，规则只在 macfilterrule 的 XML 里
  broken   aclrule_data 与 macfilterrule 都 404（必须不掉登录态）
"""
import os
import ssl
import socketserver
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))

MACFILTER_XML_FULL = (
    '<ajax_response_xml_root><IF_ERRORPARAM>SUCC</IF_ERRORPARAM><IF_ERRORTYPE>SUCC</IF_ERRORTYPE>'
    '<IF_ERRORSTR>SUCC</IF_ERRORSTR><IF_ERRORID>0</IF_ERRORID><OBJ_GLOBAL_ENV><Instance>'
    '<ParaName>SoftwareVer</ParaName><ParaValue>V1.0.0.4B8.8000</ParaValue></Instance></OBJ_GLOBAL_ENV>'
    '<OBJ_ACLCFG_ID><Instance><ParaName>_InstID</ParaName><ParaValue>DEV.ACL4</ParaValue>'
    '<ParaName>MACAddress</ParaName><ParaValue>fe:72:15:9d:45:cd</ParaValue>'
    '<ParaName>Name</ParaName><ParaValue>ACL4</ParaValue>'
    '<ParaName>Interface</ParaName><ParaValue>DEV.WIFI.AP1</ParaValue></Instance>'
    '<Instance><ParaName>_InstID</ParaName><ParaValue>DEV.ACL5</ParaValue>'
    '<ParaName>MACAddress</ParaName><ParaValue>de:af:39:52:f8:f3</ParaValue>'
    '<ParaName>Name</ParaName><ParaValue>ACL5</ParaValue>'
    '<ParaName>Interface</ParaName><ParaValue>DEV.WIFI.AP1</ParaValue></Instance></OBJ_ACLCFG_ID>'
    '<OBJ_WLANAP_ID><Instance><ParaName>_InstID</ParaName><ParaValue>DEV.WIFI.AP1</ParaValue>'
    '<ParaName>ESSIDHideEnable</ParaName><ParaValue>0</ParaValue>'
    '<ParaName>ACLPolicy</ParaName><ParaValue>Ban</ParaValue></Instance></OBJ_WLANAP_ID>'
    '</ajax_response_xml_root>')

MACFILTER_XML_POLICY_ONLY = (
    '<ajax_response_xml_root><IF_ERRORSTR>SUCC</IF_ERRORSTR>'
    '<OBJ_WLANAP_ID><Instance><ParaName>_InstID</ParaName><ParaValue>DEV.WIFI.AP1</ParaValue>'
    '<ParaName>ACLPolicy</ParaName><ParaValue>Ban</ParaValue></Instance></OBJ_WLANAP_ID>'
    '</ajax_response_xml_root>')

ACLRULE_JSON_2 = (
    '{"code":0,"OBJ_ACLCFG_ID":['
    '{"_InstID":"DEV.ACL4","MACAddress":"fe:72:15:9d:45:cd","Name":"ACL4",'
    '"Interface":"DEV.WIFI.AP1","ACLPolicy":"Ban","DisplayedName":""},'
    '{"_InstID":"DEV.ACL5","MACAddress":"de:af:39:52:f8:f3","Name":"ACL5",'
    '"Interface":"DEV.WIFI.AP1","ACLPolicy":"Ban","DisplayedName":""}]}')

ACLRULE_JSON_EMPTY = '{"code":0,"OBJ_ACLCFG_ID":[]}'

HOME_XML = ('<ajax_response_xml_root><IF_ERRORSTR>SUCC</IF_ERRORSTR>'
            '<OBJ_HOMEMETER_ID><Instance><ParaName>x</ParaName><ParaValue>1</ParaValue>'
            '</Instance></OBJ_HOMEMETER_ID></ajax_response_xml_root>')

ACL_404 = ('<html><head><title>404 Not Found</title></head><body><h2>404 Not Found</h2>'
           '<div style="display:none"><ajax_response_xml_root>'
           '<IF_ERRORSTR>SessionTimeout</IF_ERRORSTR></ajax_response_xml_root></div>'
           '</body></html>')

# mode=preempt：登录后第一遍 userif 返回 LOGIN_PREEMPT_ID（会话被 192.168.5.23 占着），
# 直到收到 action=preempt 的 login_preempt 才放行 —— 验证 App 端接管逻辑
PREEMPT_XML = ('<ajax_response_xml_root><LOGIN_PREEMPT_ID><Instance>'
               '<preempt_sessid>778899</preempt_sessid>'
               '<preempt_ip>192.168.5.23</preempt_ip>'
               '<preempt_mac>AA:BB:CC:DD:EE:FF</preempt_mac>'
               '<login_name>admin</login_name>'
               '</Instance></LOGIN_PREEMPT_ID></ajax_response_xml_root>')
USERIF_XML = ('<ajax_response_xml_root><OBJ_USERIF_ID><Instance>'
              '<ParaName>UserName</ParaName><ParaValue>admin</ParaValue>'
              '</Instance></OBJ_USERIF_ID></ajax_response_xml_root>')

STATE = {"preempted": False}


def mode():
    try:
        with open(os.path.join(HERE, 'tls', 'mode.txt')) as f:
            return f.read().strip() or 'real'
    except Exception:
        return 'real'


class H(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        b = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _q(self, key):
        """从 querystring 取值：首参带 '/?' 前缀，必须剥掉再比"""
        q = self.path.split('?', 1)[1] if '?' in self.path else ''
        for kv in q.split('&'):
            if kv.startswith(key + '='):
                return kv[len(key) + 1:]
        return ''

    def _tag(self):
        return self._q('_tag')

    def _type(self):
        return self._q('_type')

    def do_GET(self):
        t, ty, m = self._tag(), self._type(), mode()
        if t == 'login_token_json':
            self._send(200, '{"logintoken":"1234567890","_sessionToken":"999888777"}')
        elif t == 'vue_home_device_data':
            self._send(200, HOME_XML, 'text/xml')
        elif t == 'aclmode_data':
            self._send(200, '{"OBJ_ACCESSCONTROL_ID":[{"AccControlMode":"0"}],"LocalMacAddr":"aa:bb:cc:dd:ee:ff"}')
        elif t == 'aclrule_data':
            if m == 'broken':
                self._send(404, ACL_404, 'text/html')
            elif m == 'fallback':
                self._send(200, ACLRULE_JSON_EMPTY)
            else:
                self._send(200, ACLRULE_JSON_2)
        elif t == 'vue_macfilterrule_data':
            if m == 'broken':
                self._send(404, ACL_404, 'text/html')
            elif ty == 'hiddenData':
                self._send(200, MACFILTER_XML_FULL if m == 'fallback' else MACFILTER_XML_POLICY_ONLY, 'text/xml')
            else:
                # 真机实测：vueData 类型返回 404（含 SessionTimeout 字样）
                self._send(404, ACL_404, 'text/html')
        else:
            self._send(404, ACL_404, 'text/html')

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(n).decode('utf-8', 'replace')
        form = {}
        for kv in raw.split('&'):
            if '=' in kv:
                k, _, v = kv.partition('=')
                form[k] = v
        t = self._tag()
        if t == 'login_entry':
            self._send(200, '{"login_need_refresh":true,"sess_token":"7777777","loginErrType":""}')
        elif t == 'login_preempt':
            if form.get('action') == 'preempt' and form.get('preempt_sessid') == '778899':
                STATE["preempted"] = True
            self._send(200, '{"code":0}')
        elif t == 'vue_userif_data':
            busy = mode() == 'preempt' and not STATE["preempted"]
            self._send(200, PREEMPT_XML if busy else USERIF_XML, 'text/xml')
        else:
            self._send(200, '{"code":0}')


class TS(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == '__main__':
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(os.path.join(HERE, 'tls', 'cert.pem'), os.path.join(HERE, 'tls', 'key.pem'))
    srv = TS(('127.0.0.1', 18443), H)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    print('fake router https://127.0.0.1:18443 mode=%s' % mode())
    srv.serve_forever()
