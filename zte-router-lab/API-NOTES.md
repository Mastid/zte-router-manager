# ZXSLC SR7110（中兴巡天 BE5100 Pro/Pro+）Web 接口记录

实测环境：https://192.168.5.1 ，固件前端 Vue SPA（`/jquery/static/js/app.c6761c8.js`）。
以下为 2026-11-14 从设备前端代码与实机响应中确认的结果。

## 基础

- 管理地址：`https://192.168.5.1/`（HTTP 80 也监听，同一套页面）
- 证书自签，需忽略校验
- 所有接口都是 `GET/POST https://192.168.5.1/?_type=<类型>&_tag=<标记>`
- POST 必须 `Content-Type: application/x-www-form-urlencoded`，且最后要拼 `_sessionTOKEN=<token>`
- GET 请求头习惯用 `Content-Type: text/xml; charset=utf-8`
- 会话 cookie：`SID_HTTPS_=...`（HttpOnly, Secure）
- 响应头 `x_xsrf_token` 会刷新 `_sessionToken`

## 登录

1. `GET /?_type=loginsceneData&_tag=login_token_json`

```json
{"_sessionToken":"936295765483421280419512","logintoken":"61825838"}
```

2. 计算 `Password = sha256(明文密码 + logintoken)`，十六进制小写

3. `POST /?_type=loginData&_tag=login_entry`

```
Username=admin&Password=<sha256>&action=login&Frm_Logintoken=&captchaCode=&_sessionTOKEN=<_sessionToken>
```

4. 响应字段：`sess_token`、`login_need_refresh`、`lockingTime`、`loginErrMsg`、`promptMsg`
   - `login_need_refresh` 为真 → 成功
   - `lockingTime != -1` → 已锁定（连续失败会锁 IP）
   - `loginErrMsg` 含 `input_userpass_error` → 密码错

5. 其他登录端点：`/?_type=loginData&_tag=autologin_entry`、`login_preempt`、`logout_entry`、
   `login_changepwd`、`/?_type=loginsceneData&_tag=login_token_json`

未登录访问业务接口时，返回 200 + 登录页 HTML（不是 401），需要靠内容判断。

## 关键数据接口

| 用途 | 接口 |
| --- | --- |
| 首页基础信息 | `/?_type=vueData&_tag=vue_home_device_data` |
| 客户端列表 | `/?_type=vueData&_tag=vue_client_data` |
| 局域网设备 | `/?_type=vueData&_tag=vue_landevice_data` |
| 无线设备 | `/?_type=vueData&_tag=vue_wlandevice_data` |
| 无线 SSID 配置 | `/?_type=vueData&_tag=vue_ssidconfig_data` |
| 无线总配置 | `/?_type=vueData&_tag=wifiAP_data` |
| WiFi 状态 | `/?_type=vueData&_tag=wiazrdWifi_data` |
| 上网/外网配置 | `/?_type=vueData&_tag=vue_internet_data` |
| 网络拓扑 | `/?_type=vueData&_tag=vue_topo_data` |
| 流量限速 | `/?_type=vueData&_tag=vue_loadprevent_data` |
| 设备重启 | `/?_type=vueData&_tag=vue_derestart_data` |
| 恢复出厂 | `/?_type=vueData&_tag=vue_dereset_data` |
| 版本/升级 | `/?_type=vueData&_tag=vue_nowversion_lua`、`vue_upgradequery_data` |
| 管理页读写 | `/?_type=vueData&_tag=vuecfg_data` (POST) |
| 用户信息 | `/?_type=hiddenData&_tag=vue_userif_data` |
| 初始信息 | `/?_type=hiddenScene&_tag=initial_info_json` |
| 家长控制 | `/?_type=vueData&_tag=vue_pctrl_group_data` |
| MAC 过滤 | `/?_type=hiddenData&_tag=vue_macfilterrule_data` |

业务接口返回 XML（前端用 x2js 转对象），JSON 类接口 tag 带 `_json` / `vuejsonData`。

## WiFi 密码读写的额外加密

- 读密码：`POST /?_type=vueData&_tag=vuecfg_data`，body 含
  `IF_ACTION=GetPassword&ACTION_TYPE=wlanPassword&_InstID_PASS=DEV.WIFI.AP1.PSK1&PASSTYPE=PSK`
- 返回的 `KeyPassphrase` 需要用 `_sessionToken` 及其反转串做 decode（`decodePara`）
- 2.4G 实例 `DEV.WIFI.AP1.PSK1`，5G 实例 `DEV.WIFI.AP5.PSK1`

## 写操作（实测自前端 `wifiConfigSet` / `restartSubmitBtn`）

### 重启

`POST /?_type=vueData&_tag=vue_derestart_data` + `IF_ACTION=Restart`
响应 `<IF_ERRORSTR>SUCC</IF_ERRORSTR>` 表示已受理，约 60–150 秒恢复。

**2026-11-14 真机实测（ZXSLC SR7110 / V1.0.0.4B8.8000）**：

| 观测项 | 实测值 |
| --- | --- |
| 接口返回 | `IF_ERRORSTR=SUCC`、`IF_ERRORID=0` |
| 开始掉线 | 请求后 3.5 秒 |
| 管理页恢复 | 请求后 59 秒（中断约 56 秒） |
| 重启后配置 | SSID / 开关 / 加密 / 密码指纹全部不变 |
| 重启后会话 | 旧 SID 立即失效，需重新登录（面板已能自动重登） |
| WAN | PPPoE 重新拨号，IP 会变（10.218.129.135 → 10.218.187.70） |

**坑：返回「系统忙，请稍后再试。」（`cmret_003` / `cmret_005`）**
只要路由器上还有另一个管理员会话（例如浏览器另开着一个 `https://192.168.5.1` 标签页），
重启会被拒绝，而且随后本会话会被踢掉（表现为 401 / 跳登录页）。
处理：先关掉其它后台标签页；面板实现为「系统忙」等 5 秒重试、最多 3 次。


### 改 WiFi（名称/密码/开关）

**正确接口：`POST /?_type=vueData&_tag=wifi_advancedssid_data`**，`IF_ACTION=Apply`。
（2026-11-14 由浏览器真实抓包确认，51 个字段一次性提交，未改的字段用当前值回填。）

| 字段 | 含义 |
| --- | --- |
| `DualBandSync` | 双频合一，取 `OBJ_DUALBANDSYNC_ID.DualBandSync` |
| `Enable1` / `Enable5` | 频段开关 1/0 |
| `ESSID1` / `ESSID5` | 名称 |
| `_InstID1=DEV.WIFI.AP1` / `_InstID5=DEV.WIFI.AP5` | 实例 |
| `_WLANCONIG1=Y` `_WEPCONIG1=N` `_PSKCONIG1=Y` | 固定值（WLAN 开启 / WEP 关闭 / PSK 开启） |
| `KeyPassphrase1` / `KeyPassphrase5` | AES 密文 |
| `WEPKey1` / `WEPKey5` | 实测与 KeyPassphrase 同值（前端如此复制） |
| `_InstID_PSK1=DEV.WIFI.AP1.PSK1` / `_InstID_PSK5=DEV.WIFI.AP5.PSK1` | PSK 实例 |
| `BeaconType` `WEPAuthMode` `WEPEncryptionLevel` `WEPKeyIndex` `WPAAuthMode` `WPAEncryptType` `11iAuthMode` `11iEncryptType` `ESSIDHideEnable` `WEPEncryptionLevel_Bit` | 每频段各一份，带 1/5 后缀，按当前值回填 |
| `MLOEnable` | WiFi7 MLO 开关 |
| `encode` | RSA 加密的 AES 随机数 |
| `PowerEnhance1/TxPower1`、`PowerEnhance5/TxPower5` | 发射功率，取 `OBJ_WLANSETTING_ID`（RD1/RD2） |
| `Band1=2.4GHz` / `Band5=5GHz`、`_InstID_Frq1=DEV.WIFI.RD1` / `_InstID_Frq5=DEV.WIFI.RD2` | 固定值 |
| `_sessionTOKEN` | 由请求层追加在末尾 |

成功返回 `<IF_ERRORID>0</IF_ERRORID><IF_ERRORSTR>SUCC</IF_ERRORSTR>`。

> ⚠️ 踩过的坑：`wiazrdAuthor_data`（`IF_ACTION=Apply&Wizard_Apply=ApplyALL`）是**安装向导**用的接口，
> 用同样的参数去提交会被判 `<IF_ERRORID>1452</IF_ERRORID>`「页面过期，请刷新后重试」。
> 这个错误码极易被误判成会话/令牌失效，实际是接口用错了。改 WiFi 必须走 `wifi_advancedssid_data`。

### 加密细节（`encodePara` / `encodeKey`）

- 随机取两串 16 位数字 a、b
- `KeyPassphrase = Base64(AES-256-CBC(key=SHA256(a), iv=SHA256(b)[:16], ZeroPadding))`
- `encode = Base64(RSA-PKCS1v15("a+b"))`，公钥内置于前端（已抄进 `panel.py`）

### 注意

- 会话 token 有两处来源：登录响应 `sess_token`，以及**每个响应头 `x_xsrf_token`**（前端每次都用后者覆盖）→ 必须同步更新，否则解密密码会失败
- POST 表单需带 `_sessionTOKEN`
- 未登录访问业务接口返回 200 + 登录页 HTML；会话超时返回 `<IF_ERRORSTR>SessionTimeout</IF_ERRORSTR>`，都要按内容判断

## 已实测确认

- 改名（`ESSID5`）→ 立即生效，密码指纹不变；再改回原名同样成功
- 空提交（全部按当前值回填）→ `SUCC`，前后配置与两频段密码完全一致，说明「只改名称不动密码」是安全的
- `GetPassword` 每次只返回**一个**实例（`_InstID` 即请求里的实例名），2.4G 与 5G 当前用的是同一个密码

## 待验证

- `vue_topo_data` 在本机返回 `{"agentlay1":[],"controllerData":[]}`（无 Mesh 子节点），组网拓扑需再多台设备才能验证
- `vue_derestart_data` 重启已于 2026-11-14 真机验证通过（见上表）

## Android/App 侧（v1.1）

- **现象**：手机 App 输入密码后"进主页又立刻弹回登录页"。
- **定位**：登录 POST 本身不需要 Cookie（`_sessionTOKEN` 在表单里），所以登录会成功；随后的业务 GET 只靠
  `SID_HTTPS_` Cookie 认会话——一旦 Cookie 没带上，路由器返回 200 + 登录页 HTML，被判定掉线 → 自动重登 → 仍被拒 → 界面弹回登录。
- **对策**：登录成功后立刻做一次会话校验（`handshake()`），按顺序试 4 种令牌携带方式，谁通用谁：
  1. `cookie` —— 手写 `Cookie` 头（桌面验证过，默认）
  2. `cm` —— 交给系统 `java.net.CookieManager` 收发 Cookie（绕开某些机型丢弃手写头）
  3. `query` —— 把 `_sessionTOKEN` 拼到查询串
  4. `header` —— 把 `_sessionTOKEN` / `x_xsrf_token` 放进请求头
- 4 种都失败时不再"静默弹回登录页"，而是把路由器原始响应和往返轨迹写到登录页的「诊断信息」里。
- App 内不再使用 `sessionStorage`（`file://` 页面下可能抛 SecurityError，导致登录成功后连主页都进不去）。
- WebView 的 `confirm()/prompt()` 必须由 `WebChromeClient` 接管，否则默认实现直接返回 false，
  「保存 WiFi」「重启」这类二次确认永远点不到"确定"。

### v1.2 补充（2026-11-14 晚）

- 手机诊断实锤：登录应答为 `{"login_need_refresh":true,"sess_token":...,"loginErrType":"e_exceed_max_user_preemption"}`。
  即"登录成功"与"会话超限/被顶掉"**同时出现**——反复测试留下的旧管理员会话堆满名额，新会话建立即被踢，读任何接口都是登录页。
- 应对：登录成功但会话校验失败时，先 `logout_entry` 主动登出归还名额，等 5s/12s 再自动重试（最多 3 次，密码错误绝不重试以免触发锁定）；
  `forget()`（退出登录/改地址）也主动登出。页面按钮防连点（disabled 判断），避免两次并发登录互相顶号。
- 若旧会话只能等空闲超时：等 2–3 分钟再登录一次，别连续点；实在不行断电重启路由器（会清空所有管理会话）。

## 单设备详情与限速（v1.3，接口来自厂端前端 app.c6761c8.js / 6.js）

> 前端资源可直接匿名下载：`/jquery/static/js/app.*.js`（2.1MB）+ `manifest.*.js` 里的 19 个懒加载 chunk，
> 里面就是全部 `_type/_tag` 与表单字段的权威出处。比抓包更快。

| 用途 | 请求 | 关键参数/字段 |
|---|---|---|
| 单机详情+实时速率 | `GET /?_type=vueData&_tag=localnet_lan_detailinfo_lua_no_update_sess&MACAddress=<MAC>` | `OBJ_LANINFO_BYMAC`：`UploadSpeed`/`DownloadSpeed`（Kbps）、`BytesReceived`/`BytesSent`（Byte）、`OnlineTimes`、`Active`、`DisplayedType`/`DisplayedVendor` |
| 全部限速规则 | `GET /?_type=vueData&_tag=localnet_qosdyn_lua` | `OBJ_QOSDYN_ID.Enable`（全局 QoS 开关 1/0）、`OBJ_QOS_BCRULE_ID[]`：`MACDev`、`_InstID`、`BandwithRateMaxUp/Down`（Kbps） |
| 查单机规则实例 | `GET /?_type=vuejsonData&_tag=localnet_qosdyn_rulebymac&_InstID=<MAC>` | `OBJ_QOS_BCRULE_BYMAC[0].ViewName`（无规则时为空） |
| 设置/取消限速 | `POST /?_type=vueData&_tag=localnet_qosdyn_bandwithrule_lua` | `MACDev`、`BandwithRateMaxUp`、`BandwithRateMaxDown`（Kbps）、`UserName=<MAC>`、`IF_ACTION=Apply/Delete`、`_InstID=<ViewName 或 -1>` |

- 单位换算：对外的 Mbps = Kbps / 1000（前端 `convertMbps2Kbps` 就是 ×1000）。
- 回复判定：`<IF_ERRORSTR>SUCC</IF_ERRORSTR>` 才算成功，失败值写进 `logs/device.log` 备查。
- 轮询用 `_no_update_sess` 变体，避免高频刷新把一次性会话令牌刷没。
- 全局 QoS 关闭时规则可能不生效，界面上要提示（`OBJ_QOSDYN_ID.Enable`）。

### v1.4：设备行点不开（前端 bug，与接口无关）

- `render()` 里先 `querySelectorAll('.dev').forEach(el => el.onclick=...)`，紧接着 `innerHTML = map(...)` 重建列表，
  绑上去的节点随即被丢弃 → 点击无任何反应。
- 修复：改用事件委托，在 `#devList` 上挂一次 click，逐级向上找 `[data-mac]`；列表怎么重建都不丢。
- `refreshDev()` 包 try/catch，并且 401/未登录时自动关弹层回登录页，不再静默失败。

### v1.5 界面重构

- 设计基调：CSS 变量驱动，浅/深主题各一份 token；蓝色渐变 hero 卡展示外网速率 + 60 点趋势线（pushWan/drawWanSpark）。
- 设备详情弹层限速输入新增预设 chips（.chips[data-t] + .chip[data-v]，点按直接填值）。
- drawSpark 不足 2 个采样点时显示「曲线采样中」占位文字。
- 截图验证工具：android-build/diag/make_preview.py（假数据副本）+ diag/shot.js（playwright chromium）。

## 防蹭网 + 网络设置（v1.6，接口来自厂端 bundle chunk4/6/1）

### 防蹭网（接入控制，vuejsonData 返回 JSON，code 0=成功、12=需二次确认）
| 用途 | 请求 | 关键字段 |
|---|---|---|
| 模式 | `GET/POST _tag=aclmode_data` | `OBJ_ACCESSCONTROL_ID[0].AccControlMode`：0 密码接入 / 1 授权接入 / 2 白名单；`LocalMacAddr`=路由器自己 |
| 名单 | `GET/POST _tag=aclrule_data` | `OBJ_ACLCFG_ID[]`：`_InstID`、`MACAddress`、`Name`、`ACLPolicy`（Ban/Allow）。加规则 `{_InstID:"-1",IF_ACTION:"Apply",ACLPolicy,Name,MACAddress,Interface:"DEV.WIFI.AP1"}`，黑名单带 `ACTION_TYPE:"DELAUTH"`（踢下线）；删除 `{IF_ACTION:"Delete",_InstID}` |
| 待授权 | `GET/POST _tag=aclauth_stadata` | `OBJ_ACLAUTH_STA[]`：`AuthMode` 1=申请/2=已授权、`StaMac`、`ActiveTime`；操作 `{_InstID,IF_ACTION:"Apply",AuthAction}` 1=禁止 2=允许 3=删除授权 |

### 网络设置（vueData 返回 XML）
| 用途 | 请求 | 关键字段 |
|---|---|---|
| 局域网/DHCP | `GET/POST _tag=addr_manager_data` | `OBJ_BRGRP_ID`（IPAddr/SubMask）、`OBJ_DHCPHOST_ID`（ServerEnable/Min/Max/DNSServer1/2/LeaseTime/IPRouters）；提交带 `_InstID_BRGRP:"IGD.LD1", DHCPBasic:"Both", SubnetMask`，DHCP 开关=`Dhcp4sBridgePolicyEnable`，租期 -1=永久 |
| 静态 IP 绑定 | `GET/POST _tag=static_bindAddr_data` | `OBJ_DHCPBIND_ID[]`（_InstID/Name/IPAddr/MACAddr/IPRouters）；增 `{IF_ACTION:"Apply",_InstID:"-1",...}`，删带齐四个字段 |

- 改路由器自身 IP 会立刻断开连接（面板提示重新打开）。
- 界面 dock 五页：概览 / 网络（防蹭网+局域网）/ WiFi 设置 / 在线设备 / 系统设置（静态绑定+重启+退出）。
- 设备详情弹层新增「禁止上网」（加黑名单并踢下线）与「固定 IP」（预填静态绑定表单）。

### v1.7 概览页：路由器外观 + 机身温度

- 厂商前端 bundle 里只有安全说明文案提到“温度”，没有任何温度接口/字段 → 温度不保证存在。
- `/api/temp`（panel.py `api_temp()`）按候选表探测并**记住命中项**（后续只打一个请求，20s 缓存）：
  `hiddenData/vue_dev_info_data`、`vueData/vue_dev_info_data`、`hiddenData/vueinfo_data`、
  `vueData/vue_dev_status_data`、`hiddenData/vue_managdiagLed_data`、`vue_home_device_data`、`vuecfg_data`。
- 字段匹配忽略大小写，命中关键词 temperature/cputemp/chiptemp/…/temp/tmp，且 0 < 值 < 130 才认；
  同时抓 CpuRate/CpuUsage、MemoryRate/MemoryUsage。探测明细（各接口的字段清单）回传在 `tried`，
  也写 `logs/temp.log`——登录后跑一次 `/api/temp?force=1` 就能确认固件到底有没有暴露。
- 概览页新增「我的路由器」卡：SVG 路由器插图（4 天线 + LED 呼吸动画，主题自适应）+
  温度圆环（<50 正常绿 / <65 偏温黄 / <78 偏高橙 / ≥78 过热红）+ CPU/内存/在线设备。
  读不到温度时显示「未提供温度」，点按圆环强制重试。
- Java 侧 `ZteClient.tempJson()` 同一套候选表；bridge `zcall('temp')`。

### v1.9 自动浅深色 + 设备详细信息

- **主题机制重构**：原来靠 `@media (prefers-color-scheme:dark)`，但 App 的 Activity 主题固定
  `Theme.Material.Light`，WebView 里 matchMedia 不一定反映手机夜间模式。现在 CSS 全部改为
  `html[data-theme="dark"]` 属性选择器（含 `color-scheme`，原生控件/滚动条跟随），由 JS 控制。
- **无闪避坑**：`<head>` 里内联一段引导脚本在首次绘制前定主题——App 里用**同步**原生接口
  `Z.sysTheme()`（Bridge 里新增的 `@JavascriptInterface` 方法，返回 dark/light），网页里退回
  `prefers-color-scheme`；用户选择存 `localStorage['zte_theme']`（auto/light/dark），全程 try/catch。
- 系统设置页新增「外观」分段按钮：跟随系统 / 浅色 / 深色；`paintTheme()` 同时刷新
  `<meta name=theme-color>`。手机切换深色模式时，`MainActivity.onConfigurationChanged`（manifest
  已含 `uiMode`，Activity 不重建）回调 `window.__sysTheme()`，网页版则监听媒体查询 change。
- WebView 底色也随夜间模式切换（`web.setBackgroundColor`），避免深色模式下开屏白底。
- **系统设置新增「路由器信息」「本机信息」两张卡**：
  - 路由器：型号/固件/MAC/管理地址/WAN 状态·IP·接入方式·已连时长·协商速率/在线设备数/频段状态，
    数据来自 `/api/all`（render 时同步刷新）。
  - 本机（App）：`/api/sysinfo`；Java `sysInfoJson()` 返回 App 版本(versionCode)、品牌型号、
    Android 版本+API、屏幕+dpi、WebView 内核版本、ABI、网络类型、wlan0 IPv4、App 运行时长；
    网页版由 Python `api_sysinfo()` 返回面板环境（Windows/Python 版本/面板地址/运行时长）。
  - 两张卡都有「复制」按钮（clipboard API 失败则退回 execCommand）。
- 桌面端注意：面板改代码后要重启 panel.py 才有 `/api/sysinfo`。

### v1.10 清后台不重登 / 会话被占不弹登录页

- **会话持久化**：ZteClient 新增 `exportSession()/importSession()`（token + 全部 Cookie + 令牌携带方式），
  MainActivity 每次原生调用后 `afterCall()` 都把最新会话写回 SharedPreferences（令牌每响应轮换，
  必须持续保存）；管理密码单独 `pack()`（异或+Base64）存 `pwd` 键，手动退出时一并清除。
- **冷启动自动登录**：`stateJson()` 首次调用时——恢复的会话先 `alive()` 探活（读 vue_home_device_data，
  6s 超时），失效就用记住的密码 `login()`；密码错（提示"密码不正确"）则清除密码不再自动尝试，防路由器锁定。
- **掉线兜底 resume**：原生 `resumeJson()`：先探活→不行自动重登→返回 `{ok, needPwd, error}`；
  前端 `handleDrop()`：ok=继续；needPwd=回登录页；其他=顶部琥珀色重连提示条（"管理会话被占用…正在自动重连"），
  **保持当前界面不弹回登录页**，10s 轮询 + 30s 节流持续重试，成功后提示条自动消失。
- 也就是说：清后台/切换界面回来=直接进主界面；电脑网页占用会话=App 显示"被占用，正在重连"，
  空闲后自动恢复；只有手动退出或没存过密码才需要重新输密码。
- make_assets 锚点更新：load 401 段已改为 handleDrop 版本；host-tip 文案加了"保持登录"说明。
- 桌面 JVM 验证过 export/import 往返（SessionTest），playwright 验证过断线不弹登录页+提示条+自动恢复。

### v1.10 清后台不重登 / 会话被占不弹登录页

- **会话持久化**：ZteClient 新增 `exportSession()/importSession()`（token + 全部 Cookie + 令牌携带方式），
  MainActivity 每次原生调用后 `afterCall()` 都把最新会话写回 SharedPreferences（令牌每响应轮换，
  必须持续保存）；密码单独 `pack()`（XOR+Base64）存 `pwd` 键，手动退出时一并清除。
- **冷启动自动登录**：`stateJson()` 首次调用时——恢复的会话先 `alive()` 探活（读 vue_home_device_data，
  6s 超时），失效就用记住的密码 `login()`；密码错（"密码不正确"）则清除密码不再自动尝试，防路由器锁定。
- **掉线兜底 resume**：原生 `resumeJson()`：先探活→不行自动重登→返回 `{ok, needPwd, error}`；
  前端 `handleDrop()`：ok=继续；needPwd=回登录页；其他=顶部琥珀色重连提示条（"管理会话被占用…正在自动重连"），
  **保持当前界面不弹回登录页**，10s 轮询 + 30s 节流持续重试，成功后提示条自动消失。
- 也就是说：清后台/切换界面回来=直接进主界面；电脑网页占用会话=App 显示"被占用，正在重连"，
  空闲后自动恢复；只有手动退出或没存过密码才需要重新输密码。
- make_assets 锚点更新：load 401 段已改为 handleDrop 版本；host-tip 文案加了"保持登录"说明。
- 桌面 JVM 验证过 export/import round-trip（SessionTest），playwright 验证过断线不弹登录页+提示条+自动恢复。

### v1.11 外网远程访问（不连家里 Wi-Fi 也能用）

**原理**：路由器固件没有 WAN 侧管理开关，所以由家里这台电脑做跳板——`cloudflared`
出站隧道把 `https://192.168.5.1` 映射到一个免费的公网域名（`*.trycloudflare.com`），
不需要公网 IP / 域名 / 路由器端口映射。手机在外面时 App 直连该域名，协议层与局域网完全一致。

实测：`GET https://<隧道域名>/?_type=loginsceneData&_tag=login_token_json` 返回与内网一致的 JSON。

- **面板新增「远程访问」卡片**（系统设置页）：一键开启/关闭隧道（`/api/remote/start|stop|status`），
  显示公网地址 + 一键复制。组件 `bin/cloudflared.exe`（53MB）已就位。
  cloudflared 参数：`tunnel --url https://192.168.5.1 --http-host-header 192.168.5.1 --no-tls-verify --no-autoupdate`，
  `--http-host-header` 让路由器看到正确的 Host，`--no-tls-verify` 忽略自签证书。
- **App 新增双地址自动选路**：
  - `ZteClient.setCandidates(local, remote, prefer)`：局域网地址 + 远程地址；`reach()` 探测（3.5s/5s 超时），
    冷启动 `stateJson()` 首次调用时 `autoPick()`：上次用的线路优先，不通自动切换。
  - `connJson()/setConnJson()/pickJson()` + Bridge `conn/setConn/pick`；prefs 键 `hostLocal/hostRemote/hostKind`。
  - 登录页地址行显示 `host · 局域网/外网`；系统设置新增「连接方式」卡片。
  - 连接设置弹层（connSheet）：局域网地址（带恢复默认）+ 远程地址，保存后 `dropSession()`（保留密码）并 reload。
- **错误提示汉化**：msg() 把 SocketTimeout/refused/unreachable/域名解析失败 翻译成排查建议
  （例如 192.168.1.112 超时 → “地址能连上但没有回应，多半不是路由器的管理地址”）。
- **限制**：电脑/面板关机则远程不可用；快速隧道每次重启面板会换域名，需在 App 连接设置里更新
  （固定域名需要 Cloudflare 账号建 named tunnel，后续可做）；路由器仍是单管理员会话，App 与电脑网页互顶的规则不变。

### v1.12 登录界面美化

- 背景：双层 radial 渐变 + 两个模糊光斑（蓝/绿）+ 细网格（radial mask 渐隐），全部用主题变量，深浅色自适应。
- 卡片：26px 圆角、入场动画（lgIn 上滑淡入）、顶部内高光（深色下调暗）。
- 品牌图标：62px 渐变方块 + WiFi 波 SVG（替换原字母 Z）+ 外圈 halo。
- 密码框：左侧锁图标、右侧显示/隐藏眼睛按钮（.on 态画斜线），50px 高。
- 登录按钮：50px 渐变 + 箭头（按下平移），文案改由 #btnLoginText 控制（避免 textContent 清掉内部 SVG）。
- tip 保持原文本（make_assets 锚点依赖）；App 里 doLogin 的 guard/finally 替换块同步更新。
- 小屏 320×568 验证：卡片完整，placeholder 缩短为"路由器背面标签密码"。
- 截图验证：浅色/深色/小屏/眼睛切换/错误提示，全部通过。

### v1.13 概览系统状态：CPU / 内存 / 每个网口

- **网口（真实数据，已实测）**：GET `/?_type=vuejsonData&_tag=vue_eth_portname&GET_TYPE=WANSTATUS`
  返回 `OBJ_ETHPORT_INFO_ID`（ETHPortIFName/EthPortAliasName/_InstID，带 WanType）
  + `OBJ_ETHPORT_STATE_ID`（EthPortStatus：1=已连线，0=未接线）。
  这台固件 4 口：ETH_WAN(eth0) + LAN1-3(eth1-3)。实测 LAN1=1（电脑所在口）、其余 0 → **1=连接，0=未接**。
  该接口未登录也通（登录页要显示 WAN 灯），所以会话被占用时网口照常显示。
- **CPU/内存**：固件语言包有“CPU 利用率/内存利用率”（systeminfo_010/032）但对应页面被裁，
  所有候选接口（home/dev_info/vueinfo/userif/topo/initial/homestate/managdiag）在未登录时 404 或登录页。
  只能登录后按字段名探测（pctPick：0~100、排除 total/num/core/freq 等干扰词），命中记住接口。
  若始终无数据，卡片明确显示「未提供」+ 说明，不造假数据。**待用户登录面板后看 logs/sysstat.log 验证**。
- 前端：概览新增「系统状态」卡——CPU/内存两个圆环仪表（≥60% 黄、≥85% 红），
  下方 WAN+LAN1-3 四个网口图（RJ45 外形 SVG，绿色=已连接、蓝色=WAN 已连接、灰色=未连接）。
  render() 末尾 loadSys() 随 10 秒轮询刷新；/api/sysstat 桌面端缓存：命中 4s / 未命中 60s。
- App 端：ZteClient.tempJson → sysStatJson（ports 解析 + pctPick 探测，命中 4s / miss 30s 缓存），
  Bridge 'temp' → 'sysStat'，make_assets 拦截 /api/sysstat → zcall('sysStat')。
- 坑：sysNote 右侧标注不能放长文本（会与标题重叠），改短文案「未提供」，详细说明放卡片底部 tip。

### v1.14 网口可点击：WAN 显示连接的网络，LAN 显示接入设备

- **重要发现（LAN3 不显示的原因）**：`OBJ_ETHPORT_STATE_ID.EthPortStatus` 从 bundle 逻辑看是
  “WAN 角色标志”（0 = 可作 WAN / 已接 WAN 线路判断），**不是物理插线状态**——用户 LAN3 有设备
  却一直是 0。因此端口状态改为两级判定：
  1) 优先用有线设备的 `InterfaceType` 归属（能匹配 LAN1/eth1 等写法 → 该口有设备必为已连接）；
  2) 无归属数据时回退 EthPortStatus。`ports[].devs` 记录每口设备数，概览网口图直接显示“N 台”。
- **`/api/port?name=LAN1`**：WAN 口返回 net{status/type/conn/ip/mask/gw/dns/user/speed/uptime/up/down/private}，
  private=拿到内网地址时前端提示双重 NAT；LAN 口返回 clients（能归属→只列该口，否则列全部有线
  设备并在弹层说明“固件不区分物理口”）、exact、wiredTotal、wireless。
- 前端：网口图可点（事件委托 data-port），新弹层 #portSheet——WAN 显示连接的网络（接入方式/
  IP/网关/DNS/宽带账号/协商速率/已连时长 + 实时上下行），LAN 显示设备列表，点设备转设备详情弹层。
- App 端：ZteClient 抽出 portList()/portMatch()/wiredClients()/clientJson() + portJson(name)，
  sysStatJson 复用 portList 并做同样的设备归属校正；Bridge 'port'；make_assets 拦截 /api/port?name=。
- 产物 Downloads/中兴路由管家-v1.14.apk（versionCode 15）。

### v1.15 网口归属修正：LAN1=台式电脑、LAN3=NAS

- **关键数据源**：`OBJ_CLIENTS_ID[].Interface`（eth1/eth2/eth3）才是设备真正接的口——
  实测台式电脑（192.168.5.13）= eth2、NAS（192.168.5.12）= eth3。
  之前只看 `InterfaceType`（有线统一是 "Ethernet"），匹配不上任何口，所以 LAN3 的设备显示不出来。
- **机身丝印对齐**：固件把台式电脑报在 eth2（别名 LAN2），但机身上它在 LAN1；NAS 的
  eth3/LAN3 与丝印一致。即这台固件的 LAN1/LAN2 与机身丝印相反 → `PORT_SWAP = {"LAN1":"LAN2","LAN2":"LAN1"}`
  （panel.py / ZteClient.portLabel），界面显示按丝印。若换机后对不上，把这张表清空即可。
- **EthPortStatus 彻底弃用**：实测 WAN 已联网（WANStatus=Connected）、NAS 在线 ping 通时，
  eth0 和 eth3 的 EthPortStatus 都是 0 —— 它既不是插线状态也不是 WAN 角色，只能当"有无这条数据"。
  连线判定改为：LAN 口 = 有设备归属（devs>0）；WAN 口 = `OBJ_HOME_BASICINFO_ID.WANStatus`。
  未登录拿不到设备数据时 `linkKnown=false`，前端网口显示"未知"（虚线框），不再误报绿色。
- `/api/port?name=`：LAN 口按 `Interface` 精确过滤设备（exact=true）；
  App 端 `wiredClients()` 同步携带 `port` 字段，`onPort()` 与 Python `_on_port()` 同逻辑。
- 预览截图验证：LAN1→台式电脑、LAN2→未连接、LAN3→NAS，浅色/深色均正常。
- 产物：Downloads/中兴路由管家-v1.15.apk（versionCode 16，签名不变可覆盖安装）。

### v1.16 LAN 设备的网络信息全量展示

- 需求：LAN 里能看到每台设备的 MAC、网络连接方式与全部网络信息。
- `/api/device?mac=`（设备详情）新增：mask/gw/dns[]/ipv6[]/port(丝印 LAN1)/iface/last，
  网关/掩码/DNS 来自 `addr_manager_data`（`_lan_net()` 60 秒缓存），IPv6 从
  `IPV6Addr/IPV6GuaAddr` 提取（全局地址排前、去 :: 和重复，最多 3 个），
  接入端口用 `Interface` 查网口表换算成丝印名；厂商/型号仍来自 detail 接口 DisplayedVendor。
- `/api/port?name=LANx` 客户端带 portName/ipv6/last，响应加 net{ip/mask/gw/dns/min/max/dhcpOn}，
  弹层底部显示“网段 · 网关 · DNS · DHCP 池”。
- 设备列表（/api/all + App allJson）clients 加 port 字段，列表标签显示“有线 · LAN1”。
- 前端：设备详情 kv 网格改为两列 + 通栏长值（MAC/IPv6/DNS 换行不截断，.kv .full），
  标题副行显示 “MAC · LAN1”；App 端 ZteClient 同步（clientsRaw 5 秒缓存、lanNet()、ipv6Arr、portNameOf）。
- 预览截图验证 LAN3 弹层与设备详情（浅色/深色）。
- 产物：Downloads/中兴路由管家-v1.16.apk（versionCode 17）。

### v1.17 设备频段显示 + WiFi 设置五项（对齐官方 App）

**1) 当前设备连的是 2.4G 还是 5G**

- 数据源：`/?_type=vueData&_tag=localnet_lan_info_lua` 里的 `Band` 字段（**1=2.4G，2=5G**），
  按 `MACAddress` 建表，20 秒缓存（`_band_map()` / Java `bandMap()`）。
  注意 `OBJ_CLIENTS_ID` 本身没有频段字段，别在 clients 里找。
- 前端：设备列表标签 `2.4G Wi-Fi` / `5G Wi-Fi`（无线且有 Band 时）；设备详情「连接方式」同文案，
  标题副行显示 `MAC · 5G`。有线设备仍显示 `有线 · LAN1`。

**2) WiFi 管理（六行卡片，读值全部来自固件实时接口）**

| 项 | 读 | 写 |
|---|---|---|
| Wi-Fi 设置（名称/密码/开关） | `wifiAP_data` → `OBJ_WLANAP_ID`（AP1/AP5） | 沿用 v1.9 的 `vue_wlanap` 流程 |
| 信道 / 频宽 | `wifiAP_data` 的 `*SETTING*`（`Channel`/`AutoChannelEnabled`/`BandWidth`）+ `AP*` 的 `ChannelInUsed` | `wlanConfig_data` POST |
| 信号强度（三档） | `PowerEnhance` + `TxPower` 反查档位 | `wlanConfig_data` POST |
| Wi-Fi5 兼容网络 | `vue_wifi_merger` → `OBJ_WLANAP_ID`（AP3=2.4G、AP7=5G、`ForceWiFi`） | `vue_wifi_merger` POST |
| 定时关闭 | `vue_internet_advanced_rftimer_data`（hiddenData）`OBJ_WLANTIMECFG_ID.TimerEnable` + `OBJ_WLANTIME_ID.TimeStart/End*` | 同接口 `IF_ACTION=Apply` |
| Wi-Fi 中继 | `vue_home_device_data.OBJ_GLOBAL_ENV.curWorkMode / MeshEnable` | **只读**（改工作模式会断连） |

- **信道/功率写入**：`POST /?_type=hiddenData&_tag=wlanConfig_data`，body 为
  `IF_ACTION=Apply,_InstID,<Band>,<Channel>,<AutoChannelEnabled>,<Standard>,<PowerEnhance>,<TxPower>,<WlanRate>,<RadioStatus>,<BandWidth>`。
  `_InstID` 用 `DEV.WIFI.RD1`（2.4G）/ `DEV.WIFI.RD2`（5G）；自动信道时 `Channel=0` 且 `AutoChannelEnabled=1`。
- **信号强度三档口径（必须照抄，值是三元组）**：
  | 档 | PowerEnhance | TxPower | 索引 |
  |---|---|---|---|
  | 强 | `1` | `100%` | 0 |
  | 标准 | `0` | `100%` | 1 |
  | 节能 | `0` | `20%` | 2 |
  反查用 `"%s_%s" % (pe, tx)` 映射，未知一律当「强」。
- **Wi-Fi5 兼容网络写入**：`POST /?_type=hiddenData&_tag=vue_wifi_merger`，关键字段
  `SubmitFlag=SSIDIY`、`ESSIDI/ESSIDY`、`EnableI/EnableY`、`KeyPassphraseI/Y`、
  `HideKeyPassphraseI/Y`、`_InstID_PSKI/_InstID_PSKY`、`ForceWiFi`、`ESSIDHideEnableI/Y`、
  `encode`（由 `enc_key(a,b)` 生成，**不是** `enc_para("")`）。
- **定时关闭写入**：`vue_internet_advanced_rftimer_data`，`TimeStartHour/Min`、`TimeEndHour/Min`（整数，
  不是 `HH:MM` 字符串）、`TimerEnable`、`IF_ACTION=Apply`。
- **写入校验**：固件回包里的 `<IF_ERRORSTR>` 非 `SUCC` 就抛错（`_wf_result`），
  前端弹层内红字提示，不再“点了没反应”。
- 接口：`GET /api/wifimgr` → `{bands[],channels{2.4G,5G},compat{force,items[]},timer{on,start,end},mode,mesh}`；
  `POST /api/wifimgr` → `{act:"radio"|"compat"|"timer", ...}`。
  App 端 Bridge `wifimgr` / `wifimgrSet`，`make_assets.py` 拦截 `/api/wifimgr[/set]`。

**3) 逆推方式**：信道/功率/兼容网络/定时这些字段不是猜的——从固件自带 Vue 前端
`/jquery/static/js/app.c6761c8.js` 及 18 个懒加载 chunk 里抄的 form 拼装逻辑，
和官方网页版管理后台提交的 body 完全一致。

- 产物：Downloads/中兴路由管家-v1.17.apk（versionCode 18，签名不变可覆盖安装）。

### v1.18 build.sh 漏生成页面修复

- **根因**：build.sh 一直没有「先跑 make_assets.py」步骤，v1.17 打包用的是 23:25 的旧
  app/assets/index.html（无 wmCard）→ App 里根本没有 Wi-Fi 管理卡片（电脑网页面板不受影响）。
- 修复：build.sh 第 0 步固定 `python make_assets.py`；解包 APK 验证 index.html 含 wmCard。
- 产物：Downloads/中兴路由管家-v1.18.apk（versionCode 19）。

### v1.19 网口状态对齐官方 App（EthPortStatus 真实语义）

- **官方「网口状态」页数据源（逆向固件前端 chunks/3.js，systeminfo_049~063）**：
  `GET /?_type=vueData&_tag=vue_internet_ethport_data`（需登录，XML，Instance/ParaName）。
  字段：`EthPortAliasName`（ETH_WAN→显示 WAN）、`EthPortStatus`、`EthPortSpeed`、
  `EthPortMaxSpeed`、`EthPortSendRate`、`EthPortRecvRate`、`EthPortUpStream`（1=上行口）。
- **关键更正：`EthPortStatus` 的真实语义是 1=未连接、0=已连接**（官方代码
  `portStatus = 1==st ? "未连接" : "已连接"`）。v1.13~v1.15 把它当"不可靠"弃用是理解反了。
  实测对照官方 App 截图（00:16）：eth0=0/WAN 已连、eth1=1/固件LAN1 未连接、
  eth2=0（台式机）、eth3=0（NAS），全部吻合。
- **速率映射**（speedArr=[10,100,1000,2500,5000,10000]）：0=AUTO，1..6 对应 Mbps；
  `changeSpeedNum`：0→"AUTO"，1..6→"N Mbps"，其他→"/"。
- **匿名数据源**：`vue_eth_portname&GET_TYPE=WANSTATUS` 未登录也返回
  OBJ_ETHPORT_STATE_ID（EthPortStatus），所以**未登录也能显示真实插线状态**（不再是"未知"）；
  速率字段只在登录后的 vue_internet_ethport_data 里有（`_ethport_speed()` 5 秒缓存，失败回退空）。
- 界面：网口方格显示「1000Mbps」（连接且无设备数时）、「N 台」、「未连接」；
  WAN 弹层「协商速率/最大速率」，LAN 弹层顶部「协商速率 X · 最大 Y」tip。
- 之前用设备归属推断 link 的逻辑保留但只算 devs 角标，不再覆盖官方状态；
  WANStatus 仅作联网文案（wanStatus 字段）。
- App 端（ZteClient）：portList() 同口径 + ethportSpeed()（新增 xmlInstances XML 逐实例解析）；
  portJson WAN/LAN 带 speed/max；sysStatJson ports 带 speed/max。
- 产物：Downloads/中兴路由管家-v1.19.apk（versionCode 20）。

### v1.20 去掉 Wi-Fi 管理里的「Wi-Fi 设置」行

- Wi-Fi 页顶部的频段卡片（修改按钮）已承担改名/改密码功能，`#wmList` 里 `data-wm="ssid"` 那行
  与其重复 → 删除（含点击分支里的滚动到 wifiGrid 逻辑）。
- Wi-Fi 管理卡片剩五行：Wi-Fi 信道 / 信号强度 / Wi-Fi5 兼容网络 / Wi-Fi 定时关闭 / Wi-Fi 中继。
- 产物：Downloads/中兴路由管家-v1.20.apk（versionCode 21）。

### v1.21 去掉「Wi-Fi 设置」行 + 全局圆角统一

- **Wi-Fi 管理**：删除 `#wmList` 里 `data-wm="ssid"` 行（顶部频段卡片已有修改按钮，功能重复），
  卡片剩五行：信道 / 信号强度 / Wi-Fi5 兼容网络 / 定时关闭 / 中继。
- **圆角**：用 Playwright 扫全 DOM 找「有背景/边框但圆角 <6px」的元素，直角只有
  底部 dock（全宽贴底、顶部直角）。改动：
  - dock 改悬浮圆角条（左右 12px、bottom 10px、radius 24px、阴影），`.wrap` 底部留白 94→104px；
  - `.mtag` 徽章 5px→8px、padding 2px 7px；
  - 其余元素（卡片 18px、sheet 22px、seg 13px、输入框 14px、chip/port/av/mi/opt）本已是圆角。
- 产物：Downloads/中兴路由管家-v1.21.apk（versionCode 22）。

## v1.22 圆角统一（真根因修复）

用户连续两轮反馈「所有方框改为带 R 角」，v1.21 只改了 dock/徽章没解决，本轮定位到真正根因：

1. **无 type 属性的 input 完全没有样式**。CSS 用的是 `input[type=text]` 等属性选择器，
   而页面里大量 `<input>` 没写 type（LAN 设置 lnMin/lnMax/lnDns1/lnDns2/lnLease/lnIp/lnMask、
   静态绑定 bdName/bdMac/bdIp、Wi-Fi5 兼容的 data-cpssid/data-cppwd），全部渲染成
   浏览器原生样式：窄宽度、直角、细灰边——这就是截图里的「方框」。
   修复：选择器改为
   `input:not([type=checkbox]):not([type=radio]):not([type=hidden]):not([type=submit]):not([type=button])`。
2. **静态绑定「选择在线设备」下拉 `#bdPick` 没套 `select.sel` 类**，安卓上是原生直角下拉。
   修复：HTML 加 `class="sel"`。
3. 顺带把全站圆角整体提档（占位符替换法防连锁）：5/6/8/9px→8/12，10→14，11/12→16，
   13/14→18px。输入框/按钮 18px、note 16px、select 14px、chip 12px。
4. 验证：Playwright 遍历全部页面+弹层扫描「有背景或边框但 min 圆角<10px」的元素，
   仅剩 header（贴顶）、sheet 底边（贴底设计）、分隔线行（非方框），均属有意为之。

教训：**属性选择器对「省略 type 的 input」不生效**（HTML 中 type 默认值是 text，但选择器
不匹配省略写法）；给弹层新增控件时要带上完整 class/type。预览截图用真实 mock 数据，
空 select 也要在 mock 里填充，否则看不出来是「没数据」还是「没样式」。

## v1.23 手势 / 返回键：返回上一级而不是退出应用

单页应用没有浏览器历史，原 `onKeyDown` 用 `web.canGoBack()` 判断永远为 false，按返回键直接退出。
改为页面自己维护层级，原生只做转发：

**页面侧（panel.html）**
- `NAV_STACK`：`go(tab)` 记录上一个访问过的 tab（最多 20 层）；`NAV_BACKING` 标志保证
  回退调用 go() 时不再入栈，避免「A→B→A」来回抖。
- `navBack()` 三级返回：① 关掉最上层可见 `.mask`（MASK_IDS 白名单，含 App 端注入的 connSheet）
  → ② 弹出 NAV_STACK 回到上一个页面 → ③ 已在首页返回 `false`。
- `window.__back = navBack` 供原生调用；`window.resetNav()` 在登出时清栈。
- 手势：document 级 touchstart/move/end，水平位移 ≥72px、纵向 ≤56px、|dy|<|dx|×0.8、
  900ms 内完成才判定为滑动；`.hscroll/.table-wrap/.tabs` 等横向容器内不触发。
  手势到首页**只停在首页，绝不退出**。

**原生侧（MainActivity.java）**
- `onKeyDown(BACK)` → `evaluateJavascript("window.__back?...")`，回调里 `"true"` 消费事件、
  否则 `finish()`；`backPending` 防止连按重复退出。
- 需要 `import android.webkit.ValueCallback`。

**注意**：`make_assets.py` 用字符串锚点替换 panel.html 的片段，改动被锚定的代码
（如 logout 块）必须同步更新脚本里的 old/new 字符串，否则构建在第 0 步就断言失败。

产物：Downloads/中兴路由管家-v1.23.apk（versionCode 24）。

## v1.24 登录报 e_csrf_check_fail（页面过期）的成因与修复

**现象**：面板登录时提示「登录失败：页面过期，请刷新后重试。 e_csrf_check_fail」。

**成因**（固件的一次性令牌机制）
- `login_token_json` 返回 `{logintoken, _sessionToken}` 并下发 cookie `SID_HTTPS_`（该响应**没有** `x_xsrf_token` 头）。
- 随后的 `login_entry` 必须带上**同一个** cookie + 刚刚拿到的 `_sessionToken`。只要这两步之间
  有任何别的请求走过同一个会话（前端轮询、其他接口、另一个管理员会话登录/重登），
  服务端就换发了新令牌 → 提交时用的是旧令牌 → `e_csrf_check_fail`。
- 这台固件同一时间只允许一个管理员会话。**手机 App 会自动重登（relogin）**，
  面板一登录就把 App 顶掉、App 立刻再登回来，两边互踢，令牌在中间作废 → 必然报 csrf。

**面板侧修复（panel.py）**
- `_login_once()` 把「取令牌 + 提交登录」整段放进 `with ROUTER:`，期间不允许任何其他请求插入。
- `login()` 最多重试 3 次：第 2 次改用响应头里换发的新令牌（有些固件 JSON 里的值可能已作废），
  每次重试前清 cookie。
- 错误分类：csrf/1452 → 「令牌已过期，已自动重试仍未通过」；preempt/exceed → 提示先在另一台设备退出。

**App 侧修复（ZteClient.java）**
- `login()` 外层加一轮重试（识别 csrf/页面过期/1452）。
- 新增 `noFightUntil` 冷却（90 秒）：一旦登录失败属于 `preempt`，期间 `relogin()` 直接返回 false，
  不再和电脑面板互踢。

产物：Downloads/中兴路由管家-v1.24.apk（versionCode 25）。

## v1.26 在线设备图标按厂家自动替换

- 厂家唯一权威来源：单机详情接口 `localnet_lan_detailinfo_lua_no_update_sess` 的
  `DisplayedVendor` / `DisplayedType`（`no_update_sess` 不轮换令牌，可逐台补查）。
- 后端新增 `POST /api/vendors`（body `{"macs":[...]}`）：
  先回磁盘缓存 `logs/vendors.json`（30 天 TTL，空结果 1 小时内不重查），
  缺的每轮最多现场查 8 台（串行走 ROUTER 锁），返回 `{map, left}`。
  `api_all` / `_clients_split` 的设备行附带缓存里的 `vendor` / `dtype`。
- 前端：`BRANDS`（70+ 品牌，色值 + 默认设备类型）+ `BRAND_RULES` 关键字表
  （短词如 hp/lg/tcl/zte 按整词匹配，避免 iPhone 误中 hp）；
  `kindOf()` 用设备名 / DisplayedType 判类型（手机/平板/笔记本/台式/电视/NAS/
  打印机/摄像头/手表/音箱/游戏机/灯/插座/IoT），`GLYPH` 提供对应线性图标。
  图标 = 类型图形 + 品牌配色浅底（`.av.brand`，`--bt/--btd` 双主题，
  深色下 `filter:brightness(1.35)` 提亮）。识别不到时退回首字母色块。
- 厂家补查流程 `resolveVendors()`：网页走 `/api/vendors`（最多 3 轮），
  App 端 `zcall('device', mac)` 逐台（每轮 4 台）；结果存 localStorage
  `zte_ven`（1 天内查过为空的不重试）。查到后 `repaintDevs()` 局部重绘列表与详情头像。
- 设备行副标题追加厂家短名（正则剥掉 Inc/Ltd/Co/Technologies 等后缀）。
- 产物：`ZTE-RouterManager-v1.26.apk`（versionCode 27）；
  截图验证 `android-build/out/shots21/`（浅色/深色/详情弹层）。

## v1.27 兼容网络状态/密码 + 网络页黑名单补全

- Wi-Fi5 兼容网络（对照固件 compatible 页 chunk2.js 逐字段核对）：
  - `OBJ_WLANAP_ID` 固定 4 条：[主2.4G, 兼容2.4G, 主5G, 兼容5G]，总开关取
    「兼容 2.4G」那条的 `ForceWiFi`（官方就是 s[1].ForceWiFi）；实例名 AP3/AP7，
    匹配不到时按数组位置 1/3 兜底，真值判断放宽（1/on/true…）。
  - 兼容 SSID 密码：PSK 实例是 `DEV.WIFI.AP3.PSK1` / `DEV.WIFI.AP7.PSK1`，
    用与主 SSID 相同的 GetPassword 通道（`_read_psk` 抽出复用），随
    `/api/wifimgr` 一起返回（读到就缓存）。弹层里密码框直接带值 +
    「显示当前密码」明文切换；留空保存=不改密码（不再强制要求填密码）。
  - 卡片行文案：已开启时显示「已开启 · SSID1 / SSID2」。
- 网络页黑名单（防蹭网）：
  - 旧逻辑在「授权接入」模式下只显示已授权设备，被拉黑的设备整个界面都看不到；
  - 现在授权/白名单模式下新增独立「黑名单」卡片（有 Ban 规则才显示），
    与已授权/白名单并列；名单行改为设备图标 + 名称 + 厂商 + MAC +
    在线/离线(+IP)，离线设备的名称/厂商经 /api/vendors 缓存补齐
    （`_vendor_of` 现在连带返回 DisplayedName/HostName 存进 vendors.json）。
  - `api_security` 的规则行补 `ip / vendor / dtype / online`。
- 产物：`ZTE-RouterManager-v1.27.apk`（versionCode 28）；
  截图 `out/shots22/`（兼容网络弹层、明文切换、网络页黑名单）。

## v1.28 兼容网络密码（App 端）+ 黑名单策略兜底

- 根因一（App 兼容密码）：Java `wifiMgrJson` 的 compat items 根本没有 pwd 字段，
  前端点「显示当前密码」只是切换 type，值一直是空 → App 里永远看不到密码。
  修复：抽出通用 `wifiPwdInst(inst, cacheKey)`，`wifimgrSet` 新增
  `{"action":"compatpwd","band":...}` 动作（按 merger 实例 AP3/AP7 取 PSK 实例名）；
  前端打开弹层时懒加载（`loadCpPwd`），读到直接填进密码框（圆点），
  「显示当前密码」只负责明文/密文切换；读不到时在实例提示行给出明确原因。
  网页端 `/api/wifimgr/set` 之前路由缺失（只有 POST /api/wifimgr），补上别名。
- 根因二（黑名单看不见）：`aclrule_data` 的规则条目**没有 ACLPolicy 字段**，
  策略挂在 AP 对象（`vue_macfilterrule_data` 的 OBJ_WLANAP_ID.ACLPolicy=Ban/Allow）。
  之前按 policy=="Ban" 过滤结果永远为空。修复：规则 policy 缺失时
  用 AP 对象的策略兜底，再兜底按模式（mode2=Allow，否则 Ban）；
  同一 MAC 在 2.4G/5G 各一条，去重。前端 `polOf()` 容错。
- `_read_psk` 加固：实例名精确匹配失败时，只有「唯一」条目能解出可打印密码才采用，
  避免张冠李戴；结果写入 `logs/pwd.log` 诊断日志。
- 未登录时 `_compat_info`/`_compat_pwd` 正确抛 NOT_LOGGED（不再吞成「固件未提供」）。
- 产物：`ZTE-RouterManager-v1.28.apk`（versionCode 29）；截图 `out/shots23/`。

## v1.29（2026-11-15）黑名单仍为 0 的真正根因：规则来源换主路

- 用户二次反馈黑名单还是 0 条。复查 `logs/snapshot2/vue_macfilterrule_data.txt`
  （真机抓包）发现：**`/?_type=vueData&_tag=vue_macfilterrule_data` 的一个响应里
  同时带 `OBJ_ACLCFG_ID`（2 条规则 fe:72:… / de:af:…）和 `OBJ_WLANAP_ID.ACLPolicy=Ban`**。
  而 v1.27/v1.28 都只从 `vuejsonData&_tag=aclrule_data` 取规则，真机上该 JSON
  拿不到数据 → rules 恒为空。
- 更隐蔽的坑：**这台固件对不存在的 tag 返回 404 页且正文含 `SessionTimeout`**，
  App 端 `fetchText.dead()` / 面板 `_raw_get` 会把它误判成会话失效，触发整套
  重登流程（还踢会话）。所以 JSON 的 aclrule_data 只能作兜底，不能作主请求。
- 修复（App `ZteClient.securityJson()` + 面板 `api_security()` 同步）：
  1. 主路 = `vueData&_tag=vue_macfilterrule_data`，一次请求同时拿规则 + AP 策略；
  2. XML 里没有 OBJ_ACLCFG_ID 时才试 `vuejsonData&_tag=aclrule_data`（异常仅记录）；
  3. 策略兜底链不变：规则 policy → AP policy → 按模式；同 MAC 去重。
- 桌面 JVM 端到端验证（`diag/fake_router.py` 假路由器 + `diag/SecTest.java`）：
  复刻真机行为（aclrule_data 返回 404+SessionTimeout，XML 带 2 条规则），
  `loginJson` 成功、`securityJson` 返回 2 条 Ban 规则、会话未被误杀 → PASS。
- 产物：`ZTE-RouterManager-v1.29.apk`（versionCode 30），解包校验 dex 含
  「黑名单规则来自 vue_macfilterrule_data」等新轨迹字符串。

## v1.30（2026-11-15）ACL 真正的读口 + 404 不再踢会话

用户第二份诊断轨迹给出的关键证据：
```
读数据被拒 /?_type=vueData&_tag=vue_macfilterrule_data status=404 head=<html>...
会话可用，令牌携带方式=cookie
macfilterrule 读取失败 NOT_LOGGED
aclrule_data 读取失败 NOT_LOGGED
```
→ v1.29 把 `vue_macfilterrule_data` 用 `vueData` 类型读是错的（真机 404），
且 404 页正文带 `SessionTimeout`，被 `dead()` 判成掉线 → `logged=false` →
后续 `aclrule_data` 连请求都没发出去。**v1.29 反而比 v1.28 更糟。**

从固件前端 chunk（`/jquery/static/js/4.<hash>.js` → `getAclRules/getAclMode`）核对到真实口径：

| 用途 | 请求 | 字段 |
|---|---|---|
| 名单读 | `GET /?_type=vuejsonData&_tag=aclrule_data` | `OBJ_ACLCFG_ID[]`，每条带 `ACLPolicy`(Ban/Allow)、`MACAddress`、`DisplayedName`、`_InstID`、`Interface` |
| 模式读 | `GET /?_type=vuejsonData&_tag=aclmode_data` | `OBJ_ACCESSCONTROL_ID[0].AccControlMode`、`LocalMacAddr` |
| 策略兜底 | `GET /?_type=hiddenData&_tag=vue_macfilterrule_data` | `OBJ_WLANAP_ID.ACLPolicy`（**hiddenData**，不是 vueData） |
| 批量写 | `POST /?_type=hiddenData&_tag=vue_macfilterbatch_data` | 备用 |

另外固件自身逻辑：`getAclMode()` 只在 mode=1/2 时才调 `getAclRules()`，
密码接入模式下网页端根本不展示名单——这也是「看起来什么都没有」的一部分原因。

修复：
1. `fetch()` / `fetchText()` 遇到 **HTTP 404 直接返回空**，不再当成会话失效
   （这是本轮最重要的健壮性修复，之前任何不存在的 tag 都会把整个会话带死）；
2. 规则读口改回固件口径 `vuejsonData&_tag=aclrule_data`；XML 只作兜底 + 取 AP 策略；
3. `securityJson` 增加 `rulesNote`：区分「路由器返回的名单是空的」与
   「接口没有返回数据（固件可能不支持）」，前端空态直接显示这句话；
4. 轨迹里新增 `aclrule_data 规则数=N head=...`、`macfilterrule AP策略=... 规则数=...`，
   下次用户发诊断就能一眼定位。

验证（桌面 JVM，`diag/fake_router.py` 三场景 + `diag/SecTest.java`）：
- real（aclrule_data 直给 2 条 Ban）→ rules=2 PASS
- fallback（aclrule_data 空、规则在 XML）→ rules=2 PASS
- broken（两个接口都 404 且带 SessionTimeout）→ ok:true、rules=[]、会话存活 PASS

产物：`ZTE-RouterManager-v1.30.apk`（versionCode 31）。

## v1.31（2026-11-15）系统设置新增「网络工具」三件套

入口：系统设置 → 网络工具（网络优化 / 网络排查 / 网络测速），三个独立弹层。

### 网络优化 `GET /api/optimize`（App: zcall 'optimize'）
- 当前信道/频宽/制式：复用已验证的 `api_wifimgr`（wifiConfig_data 的 Channel/AutoChannelEnabled +
  ChannelInUsed），不碰没验证过的接口。
- 周边 AP 扫描：按 `vueData&_tag=vue_scanap_data` → `hiddenData&_tag=netwlanscan_data` 顺序探测，
  字段容错（SSID/ESSID/WlanName、RSSI/Signal/SignalStrength、Channel/ChanNum）；
  固件裁剪掉该页面时如实提示「没提供周边 Wi-Fi 扫描」，退化为通用建议。
- 信道拥挤度：2.4G 按 ±4 重叠计权（rssi+100），5G 按同信道；推荐分最高的信道，
  与当前分差 ≥20 才标「值得换」。2.4G 用 40MHz 时提示改 20MHz。

### 网络排查 `GET /api/netdiag`（App: zcall 'netdiag'，登录前也能用）
依次检测：手机→路由器（login_token_json 耗时）、宽带连接（vue_internet_data 的
ConnStatus/IP/GateWay/DNS1/ConnType）、域名解析（getaddrinfo www.baidu.com）、
外网连通（TCP mirrors.aliyun.com:443）、局域网（api_lan）。
每项 ok/warn/bad + 一句话建议；未登录的项显示「需要先登录路由器才能读取」。
备而不用的深度项：`POST /api/ping` 走固件 `vueData&_tag=ping_diag_data`
（POST IF_ACTION=PingDiagnosis，轮询 OBJ_DEVPING_ID[0].PingAck 直到非 NULL），
来自固件 chunk 5.js 的 pingdiag 页面口径。

### 网络测速 `POST /api/speedtest`（App: zcall 'speedtest'）
- 原理：客户端下载测速（反映宽带+Wi-Fi 实际速度），最多 20MB / 7 秒，Range 请求。
- 测速源自动降级：现场列镜像目录挑最新 `ubuntu-*.iso`（版本号会变不能写死），
  顺序 = 中科大 → 清华 → 南大 → 华为云（华为对连续大流量会 429）→ Cloudflare __down。
  阿里云的 iso 302 到 CDN 会 502，不能用。
- 支持自定义直链（App/网页都留了输入框），http/https 都支持。
- 实测（本机）：华为云 210Mbps / 0.8s；Cloudflare 只有 2-3Mbps（国际链路，做兜底别做主力）。

### 验证
- Playwright mock 截图 `out/shots24/`（优化/排查/测速/深色）全部正常。
- 面板真网络实测：/api/netdiag、/api/speedtest 通过。
- 产物：`ZTE-RouterManager-v1.31.apk`（versionCode 32），dex 校验含
  optimizeJson/netDiagJson/speedTestJson 与镜像地址。

## v1.32（2026-11-15）网络工具三卡拆分

- 用户反馈三个工具挤在一张卡里太密。系统设置页把「网络工具」合并卡拆为
  三张独立卡片：网络优化（信道建议）/ 网络排查（一键自检）/ 网络测速（真实速度），
  每张带各自标题、说明与按钮，样式与「路由器维护」一致。
- 纯 UI 改动，接口与逻辑无变化。Playwright 截图 out/shots24/00-set-tools.png 确认。
- 产物：ZTE-RouterManager-v1.32.apk（versionCode 33）；面板 :8900 跑 1.32；备份 panel.keep-1.32.py。

## v1.33（2026-11-15）全站布局优化 + 玻璃拟态

用户要求「优化所有的面板布局」「加上虚化玻璃的特效」。

### 玻璃拟态（浅深两套）
- 背景换成多层彩色光斑（浅色：蓝/薄荷/淡紫/天蓝；深色：深蓝/青/紫），`background-attachment:fixed`。
- 新变量 `--glass / --glass-line / --glass-hi`；`.card` 改半透明 + `backdrop-filter:blur(22px) saturate(180%)` + 顶部 1px 内高光。
- 登录卡、底部弹层 `.sheet` 同步玻璃化（blur 28/30px）；顶栏、底部 dock 的磨砂加强到 blur 20/22px。
- hero（外网连接蓝卡）加白边 + 内高光，保持玻璃质感。

### 桌面双列（≥1040px）
- `.wrap` 加宽到 1120px；`.page` 变两列网格（row/col gap 16，顶对齐避免矮卡被拉伸出大片空白）。
- 首页：我的路由器 | 外网连接，网口状态 | 连接详情；WiFi 页：无线网络 | Wi-Fi 管理；
  网络页：模式/待授权/已授权/黑名单/局域网自动流式两列；设置页同。
- 在线设备列表 `#devList` 桌面双列网格；设置页末尾「路由器维护」铺满一行。
- dock 收窄到 520px；hover 时卡片阴影加深。手机端（<1040px）布局不变。

### 验证
- Playwright 浅/深 × 桌面/手机 × 5 页截图 out/shots-pages/（含 dk-* 深色组）全部正常。
- 产物 ZTE-RouterManager-v1.33.apk（versionCode 34），dex/html 校验含 --glass、blur(22px)、min-width:1040px。

## v2.0（2026-11-15）版本号 2.0

- 应用版本升为 2.0（versionCode 35），APK `ZTE-RouterManager-v2.0.apk`；
  面板 `APP_VER = "2.0"`；功能同 v1.33（玻璃拟态 + 桌面双列 + 三张网络工具卡）。
- 备份 panel.keep-2.0.py。

## v2.1（2026-11-15）桌面图标美化

- 重画应用图标（gen_icon2.py，无第三方库）：
  - 超椭圆 squircle 底 + 蓝(#3D9BF5)→深蓝(#0A3A86) 对角渐变 + 左上柔光 + 右下微反光 + 白色内描边；
  - 居中白色 Z，带 1.6% 偏移的柔和投影；3x 超采样抗锯齿（旧版 gen_icon.py 无 AA）；
  - 全密度：mdpi 48 / hdpi 72 / xhdpi 96 / xxhdpi 144 / xxxhdpi 192，另含圆形版 ic_launcher_round。
- Android 8.0+ 自适应图标：res/mipmap-anydpi-v26/ic_launcher(.round).xml
  → 背景 @drawable/ic_launcher_bg（矢量渐变 + 径向柔光，aapt:attr gradient），
    前景 @drawable/ic_launcher_fg（矢量白 Z，内容在中心 66dp 安全区）；
  圆/方/水滴遮罩都不会裁坏。Android 5~7 走 PNG。
- Manifest 增加 android:roundIcon。APK 校验：badging 各密度均指向 anydpi-v26 XML，5 档 PNG 齐全。
- 产物 ZTE-RouterManager-v2.1.apk（versionCode 36）；面板 APP_VER 同步 2.1；备份 panel.keep-2.1.py。

## v2.2（2026-11-15）修主题往返切换后玻璃卡文字消失

用户反馈：深色切回浅色后，设置页卡片只剩半透明底、文字全没了（截图证实：
卡外元素正常、卡内文字全消失）——Android WebView 对带 backdrop-filter 的
合成层在主题切换后沿用旧快照、不重绘的已知渲染 bug。

修复（panel.html）：
1. 新增 `glassRepaint()`：把所有 .card/.lg-card/.sheet/header/.dock 的
   backdrop-filter 临时置 none → 强制一次 layout → 再恢复，
   迫使合成层重建；`paintTheme()` 末尾调用（手动切换、跟随系统回调都会走到）。
2. 文字对比度加高：浅色 --text #0f1a26→#0a1420、--muted #6b7b8c→#5c6e80；
   深色 --text #e9eff7→#f0f5fb、--muted #94a4b6→#a3b2c4；--line/--soft/--faint 同步微调。
   选项块（--soft 背景）里的字现在明显更清楚。

验证：Playwright 深色→浅色往返切换，断言卡片标题 computed color 为深色、
visibility 可见、无 JS 报错；截图 out/shots-pages/tg-2-light.png 全部文字正常。
产物 ZTE-RouterManager-v2.2.apk（versionCode 37）；面板 APP_VER 同步 2.2；备份 panel.keep-2.2.py。

## v2.3（2026-11-15）测速节点可选 + 上级光猫

### 测速节点选择
- 节点表：中科大 / 清华 TUNA / 南京大学（教育网）+ 华为云（公有云）+ Cloudflare（国际兜底）。
- `GET /api/speednodes`（App: zcall 'speednodes'）：并发量各节点 **TCP+TLS 握手延迟**（带 SNI），
  按快慢排序返回 `{key,name,tag,ms,ok,best}`。不用 HTTP 探测的原因：
  镜像对脚本请求常回 403/429（ustc/tuna 403、nju 302、huawei 偶发 429），
  但网络远近不受影响；TLS 握手 5 节点并发 ~0.4s 完成。
  坑：`ssl.wrap_socket` 不带 server_hostname 会被部分站点以 TLSV1_UNRECOGNIZED_NAME 拒握手。
- `POST /api/speedtest {node, url}`：指定节点优先，auto 时按握手延迟排序逐个试；
  每个节点测速直链仍是现场列镜像目录取最新 ubuntu iso（阿里云 ISO 302→CDN 502 已剔除）。
  返回加 `node/nodeName`。前端测速弹层加「测速节点」下拉（自动/各节点+延迟），缓存 5 分钟，可「重测延迟」。
- Java 同步：SPEED_NODES 表 + nodeLatency()（并行线程）+ speedNodesJson() + speedTestJson 支持 node。

### 上级光猫
- `GET /api/ont`（App: zcall 'ont'）：读 vue_internet_data 的 WAN（IP/网关/拨号方式/DNS），
  探测 [WAN网关, 192.168.1.1, 192.168.0.1, 192.168.100.1, 192.168.2.1] 的 80/443（TCP 900ms），
  80 优先排序，返回 best + candidates + 提示（PPPoE 时网关是运营商 BRAS 不是光猫，给出直连建议）。
- 系统设置新增「上级光猫」卡：检测后显示网关/拨号方式/管理地址/响应，可达时给「打开光猫管理页」。
- 打开链接：网页 window.open；App 新增 openUrl 桥（ACTION_VIEW + NEW_TASK）。

### 事故与修复
- 期间 nettools.py 被一次 io.open(newline="\\n") 写空（open 先截断再因非法 newline 报错），
  __pycache__ 也被随后的 py_compile 覆盖。已按前端消费契约（panel.html 的 loadOpt/loadNd/runSpeed）
  完整重建 nettools.py：api_optimize/api_netdiag/api_speedtest/api_ping + 新增 api_speednodes/api_ont。
  教训：写文件一律用 Write/Edit 工具；py 原地改用临时 patch 脚本 + ast/py_compile 校验后再替换。
- 备份：panel.keep-2.3.py、nettools.keep-2.3.py。产物 ZTE-RouterManager-v2.3.apk（versionCode 38）。

## v2.4（2026-11-15）光猫卡重做：不可达不再是死胡同

用户反馈「检测不可达」。实测 LAN（192.168.5.x）里 192.168.1.1/0.0.1/100.1/2.1 全部超时
（8080/8443/23/7547 也不通）——PPPoE 桥接组网下从路由器后面确实进不了光猫管理页，属正常现象。
因此把卡片从「只报不可达」改成「说清为什么 + 给能操作的出路」。

### nettools.api_ont(body) 重写
- body 支持 {ip:"192.168.1.1[:8080]"}：指定地址时只探这一个，且**不依赖登录**
  （手机先连光猫 Wi-Fi/网线，再回来探）。
- 并发探测：ThreadPoolExecutor，端口 80/443/8080，超时 1.1s；桥接时跳过公网 BRAS 网关
  （私有网段判断 _is_private：10/172.16-31/192.168/100.64-127 CGNAT）。
- 新返回字段：mode（bridge/route/unknown）、note（分场景结论）、manual、tried、table。
- note 文案：桥接→"管理页只对光猫 LAN 口/光猫 Wi-Fi 开放，进不去是正常现象不是故障"；
  路由→"可能改过端口或关了 LAN 侧 Web 管理"；手动→"确认手机此刻接在光猫这一侧"。

### panel.py
- GET /api/ont 支持 ?ip=；POST /api/ont 透传 body。APP_VER 2.4。

### panel.html 光猫卡
- 卡内新增：手动地址输入框（#ontIp，支持 IP:端口，回车=探测）、常见地址 chips
  （192.168.1.1/0.0.1/100.1/2.1，点击即探）、「探测这个地址」按钮、#ontGuide 指引区。
- 结果语义化：标签 badge 显示 桥接模式/路由模式/可访问；标题「光猫管理页进不去，这是正常的」。
- ontGuide 步骤指引（.ont-guide CSS，圆圈序号）：桥接→网线插光猫 LAN 口/连光猫 Wi-Fi→
  开 192.168.1.1（电信/移动）或 192.168.0.1（联通）→看完接回路由器 WAN 口自动重拨；
  附"只想重启就断电 10 秒"。坑：#ontGuide 一开始漏挂 ont-guide class，样式全不生效。

### Java（versionCode 39 / versionName 2.4）
- ontJson(String arg)：arg 带 {"ip":"..."} 时手动探测（登录失败也放行）；
  按端口轮并发（80→443→8080，同轮全地址并发线程，命中即停）；
  isPrivateIp() 新增；candJson 对非 80/443 端口补 ：port；返回加 mode/note/manual。
- MainActivity：ont 分发改 ontJson(arg)；make_assets：zcall('ont', o.body)。

### 验证
- 真机网络：POST {ip:192.168.5.1} → reachable（22ms）；{ip:192.168.1.1} → 手动不可达文案。
- 模拟：PPPoE+公网网关→mode=bridge/note 正常解释；DHCP+私网网关→route，可达时 best.isGw=true。
- Playwright 截图 out/shots26/：桥接不可达（浅/深、桌面/手机）、手动探测、路由可达，全部正常。
- APK 解包校验：html 含 ontChips/探测这个地址/想进光猫；dex 含 ontJson/isPrivateIp。
- 备份 panel.keep-2.4.py、nettools.keep-2.4.py。产物 中兴路由管家-v2.4.apk（Downloads）。

## v2.5（2026-11-15）登录即接管：自动下线前面已登录的会话

用户要求「重新登录路由器后台，自动下线前面已经登录的会话」。从固件前端 app.c6761c8.js
确认了 preempt 真实口径：

- 登录成功后读 `/?_type=hiddenData&_tag=vue_userif_data`（POST IF_ACTION=Apply,
  IsAutoShowWizard=0）：账号被占时返回 `<LOGIN_PREEMPT_ID><Instance>`，字段
  `preempt_sessid / preempt_ip / preempt_mac / login_name`。
- 强制接管 = POST `/?_type=loginData&_tag=login_preempt`，form
  `{preempt_sessid, action:"preempt"}`；接管后 userif 恢复 `OBJ_USERIF_ID`。
- 另有 `cancelpreempt`（action=preempt_cancel），未用。
- logout_entry 现在带 `IF_LogOff:"1"`（与固件一致）。

### panel.py
- 新增 `_insts/_preempt_of/_preempt_msg/_userif/_take_over/_claim/_sess_log/_slog`（注意
  与已有安全日志 `_slog(tag,txt)` 重名，会话日志改叫 `_sess_log`）。
- `login(password, preempt=True)`：登录成功不再直接算完成，先 `_claim()` 确认会话真的
  生效；被占就自动顶掉对方（顶号最多两轮），返回 kicked 信息。
  - 接管成功：S["kick"]={ip,mac,name,at}，日志「已接管管理会话」。
  - preempt=False（后台静默重登）：不顶号，S["pending"] 记录占位者。
- `_relogin()`（掉线自动重登）：接管后 3 分钟内不再抢，避免和手机 App 互踢循环；
  S["error"] 会提示「点重新登录可以顶回来」。
- `relogin_force()`：手动重登——先 logout 还名额再 login+接管（更干净）。
- 路由：POST /api/relogin（手动接管）、/api/login 返回 kicked/pending、/api/state 返回
  kicked/pending。APP_VER 2.5。
- `_dead()` 增加 LOGIN_PREEMPT_ID 判定（被顶掉时固件给的不是登录页）。

### panel.html
- 登录按钮文案「接管中…」；登录提示说明会自动接管管理会话。
- doLogin POST 带 preempt:true；成功且有 kicked → toast「已接管管理会话，IP 的登录已下线」。
- 系统设置 → 路由器维护卡新增「接管管理会话」行（btnTakeover → /api/relogin），
  `.maint+.maint` 分隔线样式。
- init/handleDrop 回登录页时用 `savedPwd()` 预填密码（本次会话输过就不用再打）。

### Java（versionCode 40 / versionName 2.5）
- ZteClient：`preemptPage()/takeOver()/claimSession()`；loginOnce 成功后先 claimSession
  再 handshake；`dead()` 增加 LOGIN_PREEMPT_ID；loginJson 返回 kicked；
  `reloginForce()`；XML 字段解析 `xmlVal()`。
- MainActivity：zcall 分发增加 `relogin`；make_assets：/api/relogin → zcall('relogin')，
  savedPwd() 换成 PWD_MEM（App 里不碰 sessionStorage）。

### 验证
- Python 单测四场景（假 req）：空闲/被占自动顶掉/不顶/顶不掉 —— 全部符合预期。
- 假路由器（fake_router.py 扩展 preempt 模式 + PreemptTest.java）：
  free → kicked:null PASS；preempt → 自动顶掉 192.168.5.23 且登录后能读数据 PASS；
  SecTest real/fallback/broken 三场景回归 PASS。
- Playwright 截图 out/shots29/：维护卡新行（浅/深、桌面/手机）、接管 toast、登录页提示。
- APK 解包：html 含 btnTakeover/savedPwd/接管管理会话；dex 含 reloginForce/claimSession/
  takeOver/login_preempt/preempt_sessid。产物 Downloads/中兴路由管家-v2.5.apk。

## v2.6（2026-11-15）网口实况 / 双 WAN / 修改管理员密码

### 真实口径（逆向 chunks/1.js、3.js、4.js）
- 双 WAN 读：GET /?_type=hiddenData&_tag=vue_internet_eth_data
  OBJ_DUALWAN_BASIC_ID（BindEnable/SecWanLink/Mode/LANViewName/DevIp）、
  OBJ_WANLAN_ID（WANSelect=主口、LAN_name）、OBJ_DUALWAN_LOADBALANCE_ID、OBJ_DUALWAN_MAL_TRSF_ID；
  WAN2 状态：GET /?_type=vueData&_tag=vue_dualwan_data → ID_WAN_COMFIG（Enable/ConnStatus/WANCTYPE/TransType）。
- 切口：POST vue_dualwan_data 整表回填（IF_ACTION=Apply，Enable/_InstID/WANC_TYPE/WANCName/mode/
  TypeFlag/WANSelect/SecWanLink/Mode/LANViewName/DevIp/BindEnable/lbEnable/负载比/MalSwitch/
  IsDns/TriggerTime/ReCoverTime/IntervalTime/Dest），只把 SecWanLink 换成目标口；PPPoE 时必须带
  UserName/Password（AES encPara + encode=encKey），读不到密码就拒绝（避免打坏宽带账号）。
  端口号口径：WAN=0，LAN1..LANn 依次（固件 getPortIndexByName）。
- 改密：GET user_info_data → OBJ_USERINFO_ID[0].Username；POST 同 tag
  {IF_ACTION:Apply,_InstID:IGD.AU1,Username,Right:1,Password:enc(旧),NewPassword:enc(新),encode}。

### lanwan.py（新模块，bind(globals()) 挂 panel）
- api_ports()：网口实况（link/speed/速率原文/上下行流量/在线·离线设备数/busy/devList），
  设备来源 localnet_lan_info_lua → OBJ_LAN_INFO_ID（Active），归属复用 _on_port；
  有线汇总 wired{online,total}。
- api_dualwan()/api_dualwan_set(body)/api_admin_pwd(body) 如上。
- 路由：GET /api/ports、GET+POST /api/dualwan、POST /api/adminpwd。

### panel.py 修复
- _num_or_none 之前丢了定义 → _ethport_speed() 恒异常返回 {}，网口速率/流量整块失效；已补回。
- _ethport_speed 增加 upText/downText（固件该字段是 "12.34 KB/s" 带单位字符串，数值只判忙）。

### panel.html
- 系统设置新增「网口实况」卡（每口一行：圆点/速率/流量/状态 pill/在线·离线台数，5 秒轮询，
  点行打开原网口详情弹层）与「双 WAN」卡（WAN1/WAN2 两行 + LAN 口 chips + 应用按钮）。
- 文案口径：无链路显示「未接设备/没有链路/未接入」——只插一头网线检测不到，注释里说明。
- 路由器维护卡新增「修改管理员密码」行 + admPwdSheet 弹层（旧/新/确认，改成功后面板记住新密码）。
- go('set') 进入时 loadPortLive()+loadDualWan()+startPortLive()，离开即停轮询。

### Java（versionCode 41 / versionName 2.6）
- ZteClient：tagInstances/firstTag/respErr/argStr/argInt；portsLiveJson()、dualwanJson()、
  dualwanSetJson(arg)、adminPwdJson(arg)（成功后 adminPwd=新密码）。MainActivity 分发
  ports/dualwan/dualwanset/adminpwd；make_assets 桥接（/api/ports 需在 /api/port 之前匹配）。
- 构建坑：dualwanJson/dualwanSetJson 里 catch(NotLogged) 不可达（req 只抛 IOException）→ 删除。

### 验证
- Python 单测：网口设备归属（在线/离线）、双 WAN 读取与切换回填字段、切口后复查 SecWanLink、
  改密载荷 AES 可逆解出明文、参数校验。
- Playwright 截图 out/shots30/：网口实况（浅/深）、双 WAN（含选中态）、改密弹层（含校验报错）、
  桌面双列整页。
- SecTest real/fallback/broken 回归 PASS；APK 解包确认新界面与新方法已打入；面板 :8900 已重启 v2.6。

## v2.7（2026-11-15）物理 WAN 口两口设置 + 网口实况进概览

### panel.html
- 「网口实况」卡从系统设置移到概览页，紧跟「网口状态」卡；轮询 gate 从 TAB==='set' 改为
  TAB==='home'；go('home') 进入时 loadPortLive()+startPortLive()，离开即停。
- 「双 WAN」卡重做为「物理 WAN 口」：WAN1 主口 / WAN2 副口两个槽位各自一行 chips 选网口；
  DWSEL 换成 DW_W1/DW_W2；POST {main, sec}（可只给一个）。
  - WAN1 行：WAN2 正在启用时的那个口置灰「不可选」；当前口标「当前」。
  - WAN2 行：硬件 WAN 口（wan=true）与当前 WAN1 口置灰。
  - 提示行实时显示「准备应用：WAN1 → x，WAN2 → y」；按钮文案「应用端口设置」。

### lanwan.py — api_dualwan_set(body)
- body 支持 {"main":口, "sec":口}（兼容旧 {"port"/"idx"}）；可同时换两口（互换合法）。
- 校验：两口不能同口；WAN 口不能当 WAN2；sec 抢当前 WAN1、main 抢启用中的 WAN2 → 拒绝，
  但同一次请求里互换则放行。
- 坑：端口序号 0（WAN 口）在 Python 是假值，不能用 `or` 链取参数，必须判 None。
- payload：WANSelect=final_main、SecWanLink=final_sec，其余整表回填不变；复查两个字段都生效。

### Java（versionCode 42 / versionName 2.7）
- ZteClient.dualwanSetJson 同步支持 main/sec（argInt 数字 0 无此坑）；复查 nowSec+nowMain。

### 验证
- diag/test_dualwan27.py：14 场景全过（旧口径、两口同换、只换 WAN1、WAN 口当 WAN2 拒绝、
  抢口拒绝、互换放行、同口拒绝、无变化、未启用换口、PPPoE 无密码拒绝）。
- Playwright 截图 out/shots31/：概览网口状态+实况同屏、物理 WAN 口两口选择（含选中态/深色/桌面）。
- 面板 :8900 已运行 v2.7；APK → Downloads/中兴路由管家-v2.7.apk。
- 坑：build.sh 第 1 步 `rm -rf out` 会把截图/预览一起清掉，截图要在打包前或打包后重跑。

## v2.7.1（2026-11-15 真机反馈）固件不支持双 WAN 时优雅降级
- 真机（巡天 BE5100 Pro+）固件不返回 OBJ_DUALWAN_BASIC_ID → 卡片里 WAN1/WAN2 两行空壳、
  按钮还挂着。修复：renderDualWan 失败分支调 dwSlots(false)，把槽位/按钮/提示整块隐藏，
  只留「这台固件没有返回双 WAN 配置」+ 一句说明（有的固件要在原版管理页先开启双 WAN）；
  角标显示「不支持」。成功分支 dwSlots(true) 恢复。
- 验证：Playwright 模拟 ok:false 截图（shots31/dw-unsupported.png）+ 正常态回归（mob-dw2-pick）
  均正常；test_dualwan27.py 14 场景 ALL PASS。
- APK：versionCode 43 / versionName 2.7.1 → Downloads/中兴路由管家-v2.7.1.apk。

## v2.8（2026-11-16）玻璃视觉改版
- 概览去掉「网口状态」小方块卡（renderSys 只留 SYS_PORTS 数据给网口详情弹层用，
  portGrid 事件委托已删）；网口实况成为概览第一张数据卡。
- 登录页：玻璃卡升级（388px/圆角30/磨砂34px）、logo 外圈旋转 conic 光环、绿色「本机直连」
  安全提示条、玻璃输入框、带流光的渐变按钮、背景三色光晕。
- 概览：外网卡玻璃渐层 + 缓慢流光（heroSheen 11s）、内嵌玻璃 rate 块；所有选项（prow/dwrow/
  opt/wifi/wm-blk/maint/chip/dwchip/mini/btn2/linkbtn/icon-btn/input/select/seg）统一
  玻璃片（--tile 渐层 + gline2 边 + 内高光 + blur）；顶栏/dock/sheet/toast 同步玻璃化；
  浅深两套 token（--card-grad/--tile/--gline/--ghi）。
- #plNote 改中性脚注（原来用了橙色警示 .note）。
- 产物：versionCode 44 / versionName 2.8 → Downloads/中兴路由管家-v2.8.apk；
  截图 out/shots32/（登录/概览 × 浅深 × 手机桌面）。

## v2.8.1（2026-11-16）DHCP 状态显示修复
- 用户反馈：路由器 DHCP 已关闭，App 仍显示「已开启」。
- 根因：api_lan 里 dhcpOn = ServerEnable 或 Dhcp4sBridgePolicyEnable 任一为 1。
  Dhcp4sBridgePolicyEnable 是“桥接下放行 DHCP 报文的策略”，关掉 DHCP 服务器后它通常仍是 1，
  「或」起来就把关闭状态盖掉了。
- 修复（panel.py / nettools.py / ZteClient.java 三端同步）：
  - 新增 _dhcp_state(dh, bd)：以 DHCP 服务器自身开关为准，优先级 ServerEnable > DHCPEnable >
    DHCPServerEnable > DHCPServer；读不到才退回桥接策略字段；都没有返回 None（未知）。
  - api_lan/lanJson 额外返回 dhcpField（判定用的字段名）和 dhcpFields（相关原始字段，
    含 enable/switch/policy/server 关键字的短值字段，便于真机对不上时排查）。
  - 展示：None 显示「读取不到/DHCP 状态未知」，不再误报；局域网卡新增脚注，
    服务器开关与桥接策略不一致时解释两者区别。
  - 写入（set_lan/lanSetJson）：不再把桥接策略当开关写 0/1；改为按读到的字段名写
    ServerEnable 等，桥接策略保持原值；固件不认该字段时自动去掉重试并 warn。
  - openLanEdit：状态未知时禁用 DHCP 开关，保存时不提交 dhcpOn。
- 诊断脚本 diag/lanshot.js（fetch 覆盖 /api/lan 三场景截图 out/shots32/lan-dhcp-*.png）；
  panel._dhcp_state 6 场景单测全过；test_dualwan27 回归 ALL PASS。
- 产物：versionCode 45 / versionName 2.8.1 → Downloads/中兴路由管家-v2.8.1.apk。
- 注意：ServerEnable 是按通用 ZTE 口径猜的最优字段。若真机上仍显示不对，
  局域网卡的脚注/ /api/lan 的 dhcpFields 会露出固件真实字段名，照着补一行映射即可。

## v2.8.2（2026-11-16）概览设备数可点击
- 概览「我的路由器」卡里的「N 台设备在线」改为玻璃按钮（描边+模糊+按压回弹+›箭头），
  点击 go('dev') 跳到「在线设备」页；#rtClients 从 div 改为 button.rtx-num，数字 id 不变。
- 绑定：$('#rtClientsBtn').onclick = () => go('dev')（dock 绑定处后面，一次性）。
- 验证：preview 点击 8 台 → TAB home→dev、devCount 有数据；截图 shots32/rt-link-home.png、
  rt-link-jump.png。产物 versionCode 46 / 2.8.2 → Downloads/中兴路由管家-v2.8.2.apk。

## v2.8.3（2026-11-16）网口速率兜底
- 用户反馈：网口实况 WAN/LAN 全显示「速率未知」，而「连接详情 → 协商速率」有 1000M。
- 根因：速率只认 vue_internet_ethport_data 的 EthPortSpeed；这台固件该字段常报 0(AUTO)，
  而 WANSTATUS（vue_eth_portname）的 OBJ_ETHPORT_INFO_ID 里带真实值、首页 WANSpeed 也有。
- 修复（panel.py read_ports + ZteClient.portList 同口径）：
  速率兜底链 ethport_data → INFO.EthPortSpeed → STATE.EthPortSpeed → WAN 口再兜首页
  WANSpeed（与连接详情同源）；max 缺失时依次退到 EthPortMaxSpeed → speed。
  新增 _speed_of/_wan_speed_hint（8s 缓存）、firstSpeed/wanSpeedHint；state 改存整行字段。
- UI：没有协商速率但有 max 时显示「最高 X Mbps」，两者都没有才显示「速率未知」。
- 验证：python 单测（INFO 有值→1000/port；全缺→WANSpeed 兜底/wanbasic）；preview 截图
  shots32/pl-speed.png（WAN 1000 Mbps / LAN1 最高 1000 Mbps / LAN2 没有链路）。
  build.sh 编译时发现 Java 变量 r 与 Resp r 重名 → 改 prow。
- 产物：versionCode 47 / 2.8.3 → Downloads/中兴路由管家-v2.8.3.apk；面板 :8900 已重启。

## v2.8.4（2026-11-16）速率字段通用识别 + 网口诊断
- 用户反馈 LAN 仍是「速率未知」→ 说明 INFO/STATE 里根本没有 EthPortSpeed/EthPortMaxSpeed 的
  有效值（或字段名不同）。两层应对：
  1) 通用识别：_speed_of 同时认「编码值 0..6」和「直接 Mbps（10/100/1000/2500/5000/10000）」
     两种口径；_speed_any 扫对象里任意 *speed* 字段（字段名不同也能兜住，跳过 *max*）。
     Java ethSpeed/speedAny 同口径（speedAny 扫 INFO/STATE 任意 speed 键）。
  2) 诊断出口：网口实况卡头部加「诊断」按钮 → 展开 /api/ports/raw（panel.py api_ports_raw /
     ZteClient.portsRawJson / MainActivity portsraw / make_assets 桥），把 INFO、STATE、
     ethport_data、WANSpeed 的真实字段摊出来，真机对不上时一眼定位固件字段名。
  - 显示文案：没有协商速率但有 max → 「最高 X Mbps」；都没有 → 「速率未上报」。
- 坑：Java portsRawJson 里 catch(NotLogged) 不可达（req 只抛 IOException），删掉才能编译。
- 验证：python 单测（Mbps 直给 + 非标准字段名 EthPortLinkSpeed → 1000）；preview 截图
  shots32/pl-diag.png（诊断区可读）。产物 versionCode 48 / 2.8.4 → Downloads/中兴路由管家-v2.8.4.apk。

## v2.8.5（2026-11-16）
- 修复「网口实况」冷启动卡「读取中」：init()/doLogin 成功路径补 loadPortLive()+startPortLive()（此前只在 go('home') 触发）。
- make_assets.py doLogin sub 片段同步；build.sh version-code 49 / 2.8.5。
- 验证：diag/shot33.js（预注入 fetch mock 走真实 init 路径）；out/shots33/cold-start-ports.png。

## v2.8.6（2026-11-16）
- 网口速率真相：本机固件 Web 接口无 LAN 协商速率字段（INFO/STATE/ethport_data/抓包全查过）；官方 App 网口状态页的「1000Mbps」= 口的标称能力。
- 新增 GET /?_type=hiddenScene&_tag=initial_info_json（免登录）→ DeviceSummary "W-2.5-WAN,E-2.5-LAN1,E-1-LAN2,E-1-LAN3" → 每口标称 Mbps（WAN/LAN1 2500、LAN2/LAN3 1000，按丝印名）。
- panel.py `_port_caps()`（用 req，勿用 _raw_get）；read_ports max 兜底 `maxFrom:"caps"`；ZteClient.portCaps()；诊断加 caps。
- WAN 协商速率仍取 WANSpeed（登录态）。

## v2.9.0（2026-11-16）
- 新增 GET /api/net：外网实时速率（只读 vue_home_device_data 的 OBJ_HOME_BASICINFO_ID），返回 {ok,status,up,down,speed,ts}；服务端 1s 缓存合并；失败 {ok:false,error}（不抛 401）。
- 前端 1s 轮询 /api/net（NET_TIMER），与 /api/all 的 10s 全量刷新并存；pushWan 同秒节流防重复打点；曲线 120 点、峰值持久累计（WAN_PEAK）。
- APK：ZteClient.netJson() + MainActivity "net" + make_assets 桥。

## v2.9.1（2026-11-16）
- dock 过渡重构：.dock-pill 滑动选中块（取代按钮 on 态背景，三处 CSS 均改 background:none）+ dockRipple 涟漪 + :active 缩放 + 图标弹性 + .page 切页淡入（opacity-only）。
- JS：syncDockPill/queueDockPill/dockRipple（panel.html 分页区块）；go() 每次切 tab 触发滑动；show('main') 后无动画就位；ResizeObserver/resize/fonts.ready 重对准。

## v2.9.2（2026-11-16）
- 双 WAN 本机口径（fixed）：WAN1=机身 WAN 口锁定；WAN2=WAN1 旁边的网口（未启用→丝印 LAN1，启用→INFO WanType==2 那个口）。
- 读取：GET_TYPE=WANSTATUS 的 WanType（1/2/-1，匿名）；GET_TYPE=WANLIST 的 OBJ_WANC_INFO_ID（IsMainWAN，匿名，出现非 1 即已启用）；vue_dualwan_data→ID_WAN_COMFIG（登录，Enable/ConnStatus/IP）。
- api_dualwan 返回 flavor:"fixed"/"legacy"；fixed 时 canSwitch:false（只读）。写：legacy 口径不变；fixed 拒绝并提示去原版管理页。

## v2.9.3（2026-11-16）
- 设置页改两列磁贴布局：.tiles 网格 8 磁贴复用原按钮 id（btnSt/btnNd/btnOpt/btnReboot/btnTakeover/btnAdmPwd）+ tileOnt/tileRtCopy 新入口；删 4 张工具卡。
- reboot()/takeover() 兼容磁贴（.tile 不改 textContent，用 toast）；$('#admPwdDesc') 判空。

## v2.9.4（2026-11-16）
- /api/ports 服务端 1s 合并缓存（_cached portslive）；前端 2s 轮询（start 时立即一帧）。
- 设置页分组：外观/网络工具/路由器信息/网络管理/维护（.slabel），磁贴拆两组。
- 验证轮询注意：make_preview 的 fetch mock 后注入会覆盖 addInitScript 版，计数 mock 须后置。
