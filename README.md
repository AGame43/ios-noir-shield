# iOS-NOIR Shield

针对 iOS 与路由器场景的一套**精准分流拦截规则**：拦掉运营商免密取号、跨 App 设备指纹、热更新后门、行为生物探针与广告遥测，同时**不动微信聊天、扫码支付与小程序链路**。

规则只有一份源文件（`ios_noir_shield.conf` / `ios_noir_shield_lite.conf`），其余格式全部由脚本派生，避免多平台规则漂移。

## 为什么单独做这一套

上游 [arnold117/iOS-NOIR](https://github.com/arnold117/iOS-NOIR)（MIT）自带一份 `shields/ios_noir_shield.conf`，思路正确，但有五类规则会顺手伤到日常使用：

| 域名 | 官方做法 | 本项目的处理 |
|---|---|---|
| `is.snssdk.com`、`mssdk.bytedance.com` | 拦截 | 注释掉 —— 字节系设备激活入口，拦了抖音可能登录异常 |
| `ynuf.aliapp.org` | 拦截 | 注释掉 —— 阿里滑块验证资源，拦了淘宝/支付宝验证码加载不出 |
| `jpush.cn`、`getui.com`、`igexin.com`、`tpns.tencent.com` | 拦截 | 注释掉 —— 推送通道，拦了收不到通知 |
| `189.cn` 主站 | 整域拦截 | 收窄到 `open.e.189.cn`、`id.189.cn` 两个认证子域 |
| `*.snssdk.com` | 部分拦截 | 只拦 SDK 专属子域（`pglstatp`、`extlog`、`toblog`） |

## 两档规则

| 档位 | 拦截条数 | 追踪域名覆盖 | 误伤面 |
|---|---|---|---|
| `lite`（最小集） | 12 | 4 / 10 | **0** |
| 完整版 | 65 | 10 / 10 | 3 个域名有 App 在用（Nielsen 系，纯测量） |

最小集只保留“实质隐私伤害”四类：运营商取号、数字联盟指纹、JSPatch 后门、ThreatMetrix 探针。丢掉的六个是商业归因（AdMaster、国双、tanx、RTBAsia、udbac、联通 `mdn.open.wo.cn`）。

完整版多覆盖的遥测包括：秒针、友盟、穿山甲、腾讯灯塔/广点通、阿里埋点、神策、GrowingIO、TalkingData，以及小红书/美团/拼多多/B 站的专属埋点。

## 文件清单

命名规律：带 `_lite` 的是最小集，不带的是完整版；同名前缀 = 同一档规则的另一种格式。

| 文件 | 给谁用 |
|---|---|
| `*.conf` | Surge / Shadowrocket / Loon，复制 `[Rule]` 之后整段 |
| `*.module` | Surge / Shadowrocket 模块（可插拔，不覆盖主配置） |
| `*.clash.yaml` | mihomo / Clash Verge rule-provider（`behavior: domain`，仅含拦截项） |
| `*.rules.yaml` | 通用 Clash 规则片段，带 `rules:` 顶层键 |
| `*.openclash.txt` | OpenClash「覆写设置 → 规则设置 → 自定义规则」，保护区与拦截混排 |
| `*.qx.conf` | Quantumult X 本地 `[filter_local]` 片段（含标签行） |
| `*.qx.txt` | Quantumult X 手机粘贴版（无标签行，全注释安全） |
| `*.qx.pack.txt` | Quantumult X，拦截规则 + 苹果直连，一份粘贴到底 |
| `*.adguard.txt` | AdGuard Home 自定义过滤规则（`\|\|domain^`） |
| `*.list` | 纯域名清单（`+.domain`），DNS 黑名单用 |
| `apple_local.qx.txt` | 苹果服务走本地直连的 14 条（可选叠加） |

## 安装

### Quantumult X

小风车 → 配置文件 → 编辑 → 跳到 `[filter_local]` → 把 `ios_noir_shield_lite.qx.txt` 里「规则开始」到「规则结束」之间整段粘进去 → **必须在你的 `final` 行之前** → 保存 → 首页把 VPN 开关关一次再打开。

`.qx.conf` 带 `[filter_local]` 标签行，只能用于“整段替换”场景，不能直接贴（重复段落会报错）。`.qx.list` 只用于 `[filter_remote]` 远程订阅，**不要填 `force-policy`**。

### OpenClash

覆写设置 → 规则设置 → 自定义规则 → 粘贴 `ios_noir_shield_lite.openclash.txt` 的规则段 → 保存 → 运行状态重启。

前提：全局设置 → 运行模式 = **Fake-IP**；DNS 由 OpenClash 接管（`使用 Dnsmasq 转发` 或 `防火墙转发` 均可）。

### iOS Clash 系客户端

把 `*.rules.yaml` 导入规则库后，**还要在当前配置里选用它**——只导入不选用不会生效。或把规则并入配置的 `rules:` 顶部（`MATCH` 之前）。

### AdGuard Home

过滤器 → DNS 黑名单 → 添加黑名单列表 → 自定义列表 → 粘贴 `*.adguard.txt` → 检查更新。

注意 AdG 与 OpenClash 的「防火墙转发」抢 53 端口，二者只能选一个。

## 三个动作不是随便选的

| 目标 | 动作 | 原因 |
|---|---|---|
| 取号网关 | `REJECT` | 让 App 立刻收到连接重置，迅速改用短信验证码；用 DROP 会转圈 30 秒 |
| 指纹 / 后门 | `REJECT-DROP` | shuzilm、online-metrix 会检测“连接被重置”来判断自己被代理拦截；DROP 让它在超时中静默失败 |
| 遥测埋点 | `REJECT-TINYGIF` | 返回 1×1 透明图，SDK 认为上报成功不再重试；直接 REJECT 会引发重试风暴 |

注：Quantumult X 的分流层只有 `direct` / `proxy` / `reject` 三个动作，`reject-img` 属于重写层，写进 `[filter_local]` 会导致启动失败。生成的 QX 文件已统一退化为 `reject`。

## 14 条支付保护区

微信（`tenpay.com`、`weixin.qq.com`、`wx.qq.com`、`wechat.com`、`servicewechat.com`）、静态资源（`qlogo.cn`、`qpic.cn`、`gtimg.cn`）、支付宝（`alipay.com`、`alipayobjects.com`、`alipay.cn`）、银联（`unionpay.com`、`unionpayintl.com`、`95516.com`）。

这 14 条必须排在所有拦截规则之前。QX / OpenClash 都是从上往下匹配，顺序错了支付会被连带断掉。

## 脚本

```bash
# 从源文件生成全部平台格式
python build_variants.py

# 额外生成 OpenClash / 通用 rules.yaml / 合并苹果直连
python build_openclash.py
python build_rules_yaml.py
python build_pack.py

# 部署前自检：语法、动作合法性、支付误伤面
python verify_rules.py [你的 ATS 域名清单.txt]
```

`verify_rules.py` 会检查：三段式语法、动作名合法性（专门拦截 `reject-img` 这类重写层动作混入分流层）、拦截域是否等于或包含某个支付保护域的父域、以及拦截域是否出现在你手机 App 的 ATS 白名单里。

改规则流程始终是三步：改 `*.conf` → 跑生成脚本 → 跑 `verify_rules.py`。

## 已知限制

- **订阅会覆盖**：如果规则靠机场订阅配置生效，客户端更新订阅时会整份重写。请用客户端的「覆写 / Mixins / 自定义配置」，或每次更新后重新导入。
- **只在 Wi-Fi 下有效**：路由器层规则管不到蜂窝数据。出行时需要靠 iOS 端的加密 DNS 描述文件（见上游项目的 `shields/*.mobileconfig`）。
- **DoH / DoT 绕过**：安卓「私人 DNS」、App 内置 DoH 走 853/443 端口，端口级劫持抓不到。需要在 DNS 层封掉已知的 DoH 域名，或改用加密 DNS 描述文件。
- **三个域名有 App 在用**：`cr-nielsen.com`、`gentags.net`、`imrworldwide.com`。它们只做测量，拦截后不影响功能，但确实会出现在某些 App 的 ATS 白名单里。介意的话注释掉。
- **遥测会被重试**：拦截后 SDK 会重试几次才放弃，首屏可能略慢、耗电略增，这是换取“不被追踪”的代价。

## 来源与许可

规则思路与部分域名清单参考 [arnold117/iOS-NOIR](https://github.com/arnold117/iOS-NOIR)（MIT），在其基础上按“不误伤支付与聊天”的原则重写并量化验证。

本项目以 MIT 许可发布，见 [LICENSE](LICENSE)。

## 免责

仅供个人隐私防护与安全研究。规则全部基于公开的域名信息，不含任何破解、绕过付费或侵入他人设备的能力。使用前请自行验证不会影响你的关键业务，作者不对由此产生的任何后果负责。
