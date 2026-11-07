#!/usr/bin/env python3
"""
iOS-NOIR Shield 多平台规则生成器
单一数据源（二选一）:
    ios_noir_shield.conf       → 完整版
    ios_noir_shield_lite.conf  → 最小集

派生产物:
    <src>.module              Surge / Shadowrocket 模块
    <src>.clash.yaml          mihomo / Clash Verge rule-provider (behavior: domain)
    <src>.list                AdGuard / 纯域名列表
    <src>.qx.conf             Quantumult X 本地 [filter_local] 片段
    <src>.qx.txt              Quantumult X 手机粘贴版（无标签行，全注释安全）
    <src>.qx.list             Quantumult X 远程资源 ([filter_remote])

用法: python build_variants.py
"""
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
SOURCES = ["ios_noir_shield.conf", "ios_noir_shield_lite.conf"]

RULE_RE = re.compile(r"^(DOMAIN(?:-SUFFIX|-KEYWORD)?),([^,\s]+),([A-Z-]+)\s*(?:#.*)?$")

# 绝不能被 reject 的域（微信聊天 / 扫码支付 / 小程序 / 银联 / 支付宝）
PROTECTED = [
    "tenpay.com", "weixin.qq.com", "wx.qq.com", "wechat.com", "servicewechat.com",
    "qlogo.cn", "qpic.cn", "gtimg.cn", "wechatpay.com",
    "alipay.com", "alipayobjects.com", "alipay.cn", "alipaysc.com",
    "unionpay.com", "unionpayintl.com", "95516.com", "chinapay.com",
]

# Surge 动作 → 各平台动作
CLASH_ACTION = {"REJECT": "REJECT", "REJECT-DROP": "REJECT-DROP",
                "REJECT-TINYGIF": "REJECT", "DIRECT": "DIRECT"}
# Quantumult X: 分流层只有 direct / proxy / reject 三个动作（外加自定义策略组名）。
# reject-img / reject-dict / reject-200 属于【重写层】动作，写进 [filter_local] 会报
# 「未知策略或节点」并导致 QX 无法启动，因此这里一律退化为 reject。
QX_ACTION = {"REJECT": "reject", "REJECT-TINYGIF": "reject",
             "REJECT-DROP": "reject", "DIRECT": "direct"}
QX_TYPE = {"DOMAIN-SUFFIX": "host-suffix", "DOMAIN": "host", "DOMAIN-KEYWORD": "host-keyword"}


def parse_conf(text: str):
    rules, in_rule, pending = [], False, ""
    for raw in text.splitlines():
        line = raw.strip()
        if line.lower() == "[rule]":
            in_rule = True
            continue
        if line.startswith("[") and line.endswith("]"):
            in_rule = False
            continue
        if not in_rule:
            continue
        if line.startswith("#"):
            c = line.lstrip("# ").strip()
            if c:
                pending = c
            continue
        if not line:
            continue
        m = RULE_RE.match(line)
        if not m:
            raise ValueError(f"无法解析的规则行: {line!r}")
        rtype, domain, action = m.groups()
        rules.append({"type": rtype, "domain": domain, "action": action, "note": pending})
        pending = ""
    return rules


def assert_safe(rules, label):
    """任何输出前统一校验：拦截动作不得命中支付保护域"""
    for r in rules:
        if r["action"] == "DIRECT":
            continue
        for p in PROTECTED:
            if r["domain"] == p or p.endswith("." + r["domain"]):
                raise SystemExit(f"[{label}] 致命冲突: {r['domain']} 会连带断掉保护域 {p}")


def to_module(rules, title, desc):
    out = [f"#!name={title}", f"#!desc={desc}", "#!system=ios", "", "[Rule]"]
    for r in rules:
        if r["note"]:
            out.append(f"# {r['note']}")
        out.append(f"{r['type']},{r['domain']},{r['action']}")
    return "\n".join(out) + "\n"


def to_clash_provider(rules):
    out = [
        "# mihomo / Clash Verge rule-provider  (behavior: domain)",
        "payload:",
    ]
    for r in rules:
        if r["action"] == "DIRECT":
            continue
        if r["note"]:
            out.append(f"  # {r['note']}")
        dom = f"+.{r['domain']}" if r["type"] == "DOMAIN-SUFFIX" else r["domain"]
        out.append(f"  - {dom}")
    out += [
        "",
        "# ── config.yaml 接入 ─────────────────────────────",
        "# rule-providers:",
        "#   noir-shield: {type: file, behavior: domain, format: yaml, path: ./ruleset/ios-noir-shield.yaml}",
        "# rules:",
        "#   - DOMAIN-SUFFIX,tenpay.com,DIRECT      # 保护区必须排最前",
        "#   - RULE-SET,noir-shield,REJECT",
        "#   - MATCH,🚀 节点选择",
    ]
    return "\n".join(out) + "\n"


def to_domain_list(rules):
    seen, out = set(), []
    for r in rules:
        if r["action"] == "DIRECT":
            continue
        d = ("+." if r["type"] == "DOMAIN-SUFFIX" else "") + r["domain"]
        if d not in seen:
            seen.add(d)
            out.append(d)
    return "\n".join(out) + "\n"


def to_adguard(rules, title):
    """AdGuard Home / AdGuard DNS 的自定义过滤规则
       语法 ||domain^ = 命中该域及其所有子域（等价于 DOMAIN-SUFFIX）。
       这里只输出拦截项：AdG 只做 DNS 层黑名单，无法表达“直连跳过”，
       保护区（微信/支付）本来就不该进黑名单，所以天然不受影响。"""
    out = [
        f"# {title} · AdGuard Home 自定义过滤规则",
        "# 用法: AdG 后台 → 过滤器 → DNS 黑名单 → 添加黑名单列表 → 自定义列表,",
        "#       把下面内容粘进去保存，然后点「检查更新」。",
        "# 语法: ||domain^ 命中该域及所有子域，等价 Clash 的 DOMAIN-SUFFIX。",
        "# 效果: DNS 层直接返回 0.0.0.0/NXDOMAIN，App 连尝试连接的机会都没有。",
        "# 注意: 这是全局生效，所有连到本路由的设备都会受影响。",
        "",
    ]
    seen = set()
    for r in rules:
        if r["action"] == "DIRECT" or r["domain"] in seen:
            continue
        seen.add(r["domain"])
        if r["note"]:
            out.append(f"# {r['note']}")
        if r["type"] == "DOMAIN-SUFFIX":
            out.append(f"||{r['domain']}^")
        elif r["type"] == "DOMAIN":
            out.append(f"|{r['domain']}^")
        else:
            out.append(f"/{r['domain'].replace('.', chr(92) + '.')}/")
    return "\n".join(out) + "\n"


def to_qx_conf(rules, title):
    out = [
        f"# {title} · Quantumult X 本地版",
        "# 用法: 粘贴进当前配置的 [filter_local] 段；确认你原有的 final 行仍在本段最末。",
        "# 纯 filter 层拦截 —— 不需要开启 MITM，也不需要安装/信任证书。",
        "#",
        "# 动作对应关系（QX 分流层只有三个动作，不要写 reject-img 之类）：",
        "#   REJECT         → reject   （直接阻断）",
        "#   REJECT-TINYGIF → reject   （QX 分流层无 1x1 图语义，退化处理）",
        "#   REJECT-DROP    → reject   （QX 分流层无 drop 语义，退化处理）",
        "",
        "[filter_local]",
    ]
    for r in rules:
        if r["note"]:
            out.append(f"# {r['note']}")
        out.append(f"{QX_TYPE[r['type']]}, {r['domain']}, {QX_ACTION[r['action']]}")
    return "\n".join(out) + "\n"


def to_qx_txt(rules, title, note_extra=""):
    """手机端「复制粘贴」专用 .txt
       与 .qx.conf 的唯一区别：不含 [filter_local] 标签行。
       原因：QX 一个配置里只允许出现一个 [filter_local]，把标签行一起粘进去
       会直接报「重复段落」而无法保存。
       所有说明性文字一律用 # 注释，确保整份文件全选粘贴也不会报错。"""
    bar = "#" + "=" * 60
    out = [
        bar,
        f"#  {title} · Quantumult X 粘贴版 (.txt)",
        bar,
        "#",
        "#【怎么用】",
        "#  1. QX 首页右下角小风车 → 配置文件 → 编辑",
        "#  2. 编辑器右上角箭头 → 跳到 filter_local",
        "#  3. 把下面标着 规则开始 / 规则结束 的两行之间内容整段粘进去",
        "#     位置必须在你的 final 行【之前】",
        "#  4. 保存 → 回首页把 VPN 开关关一次再打开",
        "#",
        "#【注意】",
        "#  · 本文件没有 [filter_local] 标签行，不要自己补，否则重复段落会报错",
        "#  · 分流层只认 direct / proxy / reject；reject-img 属于重写层，写了会启动失败",
        "#  · 纯 filter 层拦截，不需要开 MITM，不需要装证书",
        "#",
        f"# 共 {len(rules)} 条：保护区 {sum(1 for r in rules if r['action'] == 'DIRECT')} 条 / "
        f"拦截 {sum(1 for r in rules if r['action'] != 'DIRECT')} 条",
        "#",
        "#" + "-" * 26 + " 规则开始 " + "-" * 26,
    ]
    for r in rules:
        if r["note"]:
            out.append(f"# {r['note']}")
        act = QX_ACTION[r["action"]]
        out.append(f"{QX_TYPE[r['type']]}, {r['domain']}, {act}")
    out += [
        "#" + "-" * 26 + " 规则结束 " + "-" * 26,
        "#",
        "# ── 附：你原有配置里 107-114 行苹果规则的写法修正 ──",
        "# 原写法 DOMAIN-SUFFIX 是 Clash/Surge 的类型名，QX 不认、会被静默忽略。",
        "# 正确写法（逐行替换原来那 8 行，策略名与你配置里的策略组保持一致）：",
        "#   host-suffix, apple-relay.apple.com, Proxy",
        "# 若 Proxy 指 QX 内置代理，内置名是小写 proxy；若是自定义策略组则保留原名。",
    ]
    if note_extra:
        out += ["#", *[f"# {x}" for x in note_extra.splitlines()]]
    return "\n".join(out) + "\n"


def to_qx_list(rules, title):
    """远程资源专用：只含拦截项。绝不能包含 direct 行——
       因为 [filter_remote] 的 force-policy=reject 会覆盖资源内每一条的策略，
       保护区若混进来会被一起改成 reject，直接断掉支付。"""
    out = [
        f"# {title} · Quantumult X 远程资源",
        "#",
        "# 本文件所有动作均为 reject（QX 分流层只有 direct / proxy / reject 三个动作）。",
        "# 不含任何 direct 行 —— 因为 [filter_remote] 若填 force-policy，会覆盖文件内",
        "# 每一行的策略，一旦混进 direct 就会连同微信/支付一起断掉。",
        "# 保护区那 14 条 direct 请手动放在 [filter_local] 顶部。",
    ]
    seen = set()
    for r in rules:
        if r["action"] == "DIRECT" or r["domain"] in seen:
            continue
        seen.add(r["domain"])
        out.append(f"{QX_TYPE[r['type']]}, {r['domain']}, {QX_ACTION[r['action']]}")
    return "\n".join(out) + "\n"


DESC = {
    "ios_noir_shield.conf": ("🛡️ iOS-NOIR Shield · 完整版",
                             "65 条精准拦截，覆盖真机全部追踪域名；已排除微信与扫码支付链路"),
    "ios_noir_shield_lite.conf": ("🛡️ iOS-NOIR Shield · 最小集",
                                  "只拦文章点名的六类目标，误伤面为零，覆盖率约五成"),
}


def build(src_name: str):
    src = HERE / src_name
    rules = parse_conf(src.read_text(encoding="utf-8"))
    assert_safe(rules, src_name)

    stem = src.stem
    title, desc = DESC.get(src_name, (stem, ""))

    (HERE / f"{stem}.module").write_text(to_module(rules, title, desc), encoding="utf-8")
    (HERE / f"{stem}.clash.yaml").write_text(to_clash_provider(rules), encoding="utf-8")
    (HERE / f"{stem}.list").write_text(to_domain_list(rules), encoding="utf-8")
    (HERE / f"{stem}.adguard.txt").write_text(to_adguard(rules, title), encoding="utf-8")
    (HERE / f"{stem}.qx.conf").write_text(to_qx_conf(rules, title), encoding="utf-8")
    (HERE / f"{stem}.qx.txt").write_text(to_qx_txt(rules, title), encoding="utf-8")
    (HERE / f"{stem}.qx.list").write_text(to_qx_list(rules, title), encoding="utf-8")

    rej = [r for r in rules if r["action"] != "DIRECT"]
    print(f"\n■ {src_name}  →  共 {len(rules)} 条（保护区 {len(rules) - len(rej)} / 拦截 {len(rej)}）")
    for k, v in Counter(r["action"] for r in rej).most_common():
        print(f"    {k:<16} {v}")
    print(f"    产出: .module / .clash.yaml / .list / .adguard.txt / .qx.conf / .qx.txt / .qx.list")
    return len(rules), len(rej)


def main():
    total = 0
    for s in SOURCES:
        if not (HERE / s).exists():
            print(f"跳过（不存在）: {s}", file=sys.stderr)
            continue
        build(s)
        total += 1
    print(f"\n安全校验通过：{total} 个源文件的拦截规则均未触碰支付保护域。")


if __name__ == "__main__":
    main()
