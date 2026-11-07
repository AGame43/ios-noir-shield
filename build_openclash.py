#!/usr/bin/env python3
"""
生成 OpenClash（Clash / mihomo 内核）用的规则片段

来源:
    ios_noir_shield.conf        完整版
    ios_noir_shield_lite.conf   最小集

产物:
    <stem>.openclash.txt   可直接贴进 OpenClash「覆写设置 → 自定义规则」的片段
                           注意：此处把保护区也写成 Clash 规则，因为 Clash 的
                           rule-provider 只能表达“域名集合”，动作由 RULE-SET 指定，
                           写不出 DIRECT 与 REJECT 混排，所以保护区必须进主规则。

用法: python build_openclash.py
"""
import re
from pathlib import Path

HERE = Path(__file__).parent
RULE_RE = re.compile(r"^(DOMAIN(?:-SUFFIX|-KEYWORD)?),([^,\s]+),([A-Z-]+)\s*(?:#.*)?$")
CLASH_ACTION = {"REJECT": "REJECT", "REJECT-DROP": "REJECT-DROP",
                "REJECT-TINYGIF": "REJECT", "DIRECT": "DIRECT"}
TARGETS = [("ios_noir_shield_lite.conf", "最小集"), ("ios_noir_shield.conf", "完整版")]


def parse(path: Path):
    rules, in_rule, note = [], False, ""
    for raw in path.read_text(encoding="utf-8").splitlines():
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
                note = c
            continue
        if not line:
            continue
        m = RULE_RE.match(line)
        if not m:
            raise ValueError(f"{path.name}: 无法解析 {line!r}")
        rtype, domain, action = m.groups()
        rules.append((rtype, domain, action, note))
        note = ""
    return rules


def render(name, label, rules):
    direct = [r for r in rules if r[2] == "DIRECT"]
    rej = [r for r in rules if r[2] != "DIRECT"]
    out = [
        "#" + "=" * 60,
        f"#  iOS-NOIR Shield · {label} · OpenClash 自定义规则片段",
        "#" + "=" * 60,
        "#",
        "#【贴哪里】OpenClash → 覆写设置 → 规则设置 → 自定义规则",
        "#  （部分版本该项在“常规设置”页底部；贴完点「应用配置」）",
        "#  这些规则会被插到订阅规则之前，因此不用管订阅里的 MATCH 在哪。",
        "#",
        "#【顺序不能调整】保护区必须在拦截之前。Clash 从上往下匹配，",
        "#  若把 REJECT 放前面，微信支付会被一起断掉。",
        "#",
        f"#  合计 {len(rules)} 条：支付保护 {len(direct)} / 拦截 {len(rej)}",
        "#",
        "#【前提：DNS 必须被 OpenClash 接管】",
        "#  纯域名规则依赖 Clash 自己解析出域名。若路由器放行 53 端口直连外部",
        "#  DNS，手机自己查 8.8.8.8 就会拿到真实 IP，规则可能不命中。",
        "#  推荐 全局设置 → 运行模式 = Fake-IP；并在 DHCP 里把 DNS 下发为路由器地址。",
        "#",
        "#【切到移动网络后无效】路由器规则只管 Wi-Fi 下的设备。",
        "#  用蜂窝数据时，App 依然能取号 —— 那需要靠 iOS-NOIR 的 .mobileconfig。",
        "#",
        "#" + "-" * 26 + " 规则开始 " + "-" * 26,
    ]
    for rtype, domain, action, note in direct:
        out.append(f"{rtype},{domain},DIRECT")
    for rtype, domain, action, note in rej:
        if note:
            out.append(f"# {note}")
        out.append(f"{rtype},{domain},{CLASH_ACTION[action]}")
    out += [
        "#" + "-" * 26 + " 规则结束 " + "-" * 26,
        "#",
        "# 注：REJECT-DROP 只有 mihomo / Clash.Meta 内核支持。",
        "# 若你的 OpenClash 用的是旧版 Clash Premium 或启动报“unsupported rule”，",
        "# 把两处 REJECT-DROP 改成 REJECT 即可（区别只是对端会立刻收到 reset）。",
        "#",
        "# 若还想让苹果服务走本地，在保护区后面追加（与上面同段即可）：",
        "# DOMAIN-SUFFIX,apple-relay.apple.com,DIRECT",
        "# DOMAIN-SUFFIX,mask.icloud.com,DIRECT",
        "# DOMAIN-SUFFIX,mask-h2.icloud.com,DIRECT",
        "# 完整清单见 apple_local.qx.txt，把 host-suffix 换成 DOMAIN-SUFFIX、",
        "# direct 换成 DIRECT 即可。",
    ]
    return "\n".join(out) + "\n"


def main():
    for name, label in TARGETS:
        src = HERE / name
        if not src.exists():
            continue
        rules = parse(src)
        out = HERE / f"{src.stem}.openclash.txt"
        out.write_text(render(name, label, rules), encoding="utf-8")
        d = sum(1 for r in rules if r[2] == "DIRECT")
        print(f"■ {out.name:<40} {len(rules):>3} 条（保护 {d} / 拦截 {len(rules) - d}）")


if __name__ == "__main__":
    main()
