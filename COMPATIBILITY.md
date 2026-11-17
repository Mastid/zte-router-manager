# 兼容性说明

中兴路由器固件分支非常多，同一份业务数据在不同机型上可能叫不同的接口名，甚至完全换一套协议。
本项目从 v2.9.9 起引入**兼容层**：不再写死某台机器的接口，而是先识别固件族，再按候选接口逐个探测，
谁能用就用谁，并把结果缓存下来。

---

## 一、支持范围

| 固件族 | 典型机型 | 状态 |
|---|---|---|
| 新固件（vue 接口） | 巡天 / 问天 / AX / BE 系列，如 BE5100 Pro+（SR7110）、BE7200、AX5400、AX3000、AX1500、E2633 | **完整支持**（登录、概览、Wi-Fi、终端、网口、双 WAN 等） |
| 经典固件（goform 接口） | MF / AC / E 系列，5G CPE（MC801A / MC888），部分 ZXHN 光猫 | **实验性**：可登录 + 读基础信息/在线终端；写操作暂未适配 |
| OpenWrt 定制（luci 接口） | 部分企业/定制机型 | 仅识别，功能未适配 |
| 其他 | — | 自动降级：能读到的照常显示，读不到的隐藏 |

> 「完整支持」指该族接口已在本项目实测通过；具体到某台机器，仍以面板里「系统设置 → 兼容性」的实测结果为准。

---

## 二、它是怎么工作的

```
登录页 HTML 特征 ──► 固件族（vue / goform / luci）
                        │
登录成功 ──► 逐资源探测候选接口 ──► 命中即缓存（下次直接复用）
                        │
              ┌─────────┴─────────┐
         支持的功能            不支持的资源
        正常显示               自动隐藏 / 置灰
```

### 资源与候选（节选）

| 资源 | 候选接口 |
|---|---|
| 设备信息 | `vue_home_device_data` → `vue_home_device_data_no_update_sess` → `vue_dev_info_data` → `homestate_data` |
| 无线状态 | `wifiAP_data` → `ssid_data` → `netwlanap_data` → `vue_wifissid_data` |
| 外网连接 | `vue_internet_data` → `vuecfg_data` → `vue_internet_wan_select_data` |
| 在线终端 | `vue_client_data` → `localnet_lan_detailinfo_lua` → `vue_landevice_data` → `accessdev_data` |
| 物理网口 | `vue_eth_portname&GET_TYPE=WANSTATUS` → `GET_TYPE=WANLIST` → `vue_eth_port_data` |
| 双 WAN | `vue_internet_eth_data` → `vue_dualwan_data` |

完整列表见 `zte-router-lab/compat.py` 的 `RESOURCES`。

### 机型画像（只做提示，能力以实测为准）

| 差异 | 影响的机型 | 表现 |
|---|---|---|
| `wan2_fixed` | BE5100 Pro+ / SR7110 / AX3000 / AX1500 | 机身只有一个 WAN 口，WAN2 是把旁边 LAN 口切过去 |
| `preempt_on_login` | AX3000 / BE5100 / BE7200 / AX5400 | 登录应答带 `e_exceed_max_user_preemption`，但会话其实是好的 |
| `goform_only` | MC801A / MC888 / MF / AC30 / ZXHN | 只有 goform 接口，没有 vue 接口 |
| `isp_locked` | 运营商定制光猫 | 大量接口被裁剪 |

---

## 三、遇到不支持的机型怎么办

1. 打开「系统设置 → 兼容性」，点 **重新检测**；
2. 点 **复制报告**，把内容发出来。报告包含：固件族、命中/未命中的接口名、机型与软件版本；
3. 若报告里「设备信息」等关键项全为未命中，需要抓一份浏览器 F12 的接口调用记录，才能补适配。

面板端也可以用接口直接取：

```bash
curl http://127.0.0.1:8900/api/compat            # 读报告
curl -X POST http://127.0.0.1:8900/api/compat    # 重新探测
```

点「重新检测」时，后端会清掉 `zte-router-lab/logs/compat.json` 并重新跑一遍候选探测。

---

## 四、已知限制

- **写操作不自动换接口**：改 Wi-Fi、改 LAN、改双 WAN 等写入仍走已验证的接口，避免写错字段打坏配置。
  某机型读得到但写不了时，界面会给出明确错误，不会静默失效。
- **经典固件写操作未适配**：goform 的 `goform_set_cmd_process` 各代参数名差异大，暂只做读取。
- **探测需要登录**：登录前只能凭登录页 HTML 猜固件族（不会产生会话）。
- **缓存位置**：`zte-router-lab/logs/compat.json`，换机或升级固件后点「重新检测」即可刷新。

---

## 五、文件位置

| 文件 | 作用 |
|---|---|
| `zte-router-lab/compat.py` | 兼容层核心：固件族、资源候选、机型画像、探测与缓存 |
| `zte-router-lab/panel.py` | 通过 `vget()/gget()/ports_path()` 接入兼容层；`/api/compat` 接口 |
| `zte-router-lab/panel.html` | 「系统设置 → 兼容性」卡片与报告复制 |
| `android-build/.../ZteClient.java` | App 端同款逻辑：`detectFamily() / resPath() / compatJson()` |
