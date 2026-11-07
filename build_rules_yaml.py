#!/usr/bin/env python3
"""
生成独立的 Clash 规则 YAML（只含 rules 段，可直接并入任意配置）

来源:
    ios_noir_shield.conf        完整版
    ios_noir_shield_lite.conf   最小集

产物:
    <stem>.rules.yaml   形如：
                         rules:
                           - DOMAIN-SUFFIX,tenpay.com,DIRECT
                         ...
                         用于客户端「覆写 / Mixins / 自定义配置」，
                         或手工粘进订阅配置的 rules: 下方。

用法: python build_rules_yaml.py
"""
import re
from pathlib import Path

HERE = Path(__file__).parent
RULE_RE = re.compile(r"^(DOMAIN(?:-SUFFIX|-KEYWORD)?),([^,\s]+),([A-Z-]+)\s*(?:#.*)?$")
CLASH_ACTION = {"REJECT": "REJECT", "REJECT-DROP": "REJECT",
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


def render(label, rules):
    direct = [r for r in rules if r[2] == "DIRECT"]
    rej = [r for r in rules if r[2] != "DIRECT"]
    out = [
        "#" + "=" * 58,
        f"#  iOS-NOIR Shield · {label} · Clash 规则（独立文件）",
        "#" + "=" * 58,
        "#",
        "#  用法一：并入现有配置 —— 把下面 rules: 起的整段，替换或合并进",
        "#          你配置里的 rules: 段，且必须排在 MATCH / GEOIP 兜底之前。",
        "#  用法二：客户端覆写/Mixins —— 整份文件作为规则补丁加载。",
        "#",
        "#  顺序不可调整：前 %d 条 DIRECT 是支付保护区，必须在所有 REJECT 之前，" % len(direct),
        "#  否则微信聊天、扫码支付、小程序会被一起断掉。",
        "#",
        f"#  共 {len(rules)} 条：支付保护 {len(direct)} / 拦截 {len(rej)}",
        "#",
        "#  动作用 REJECT（全内核兼容）。若确认客户端是 mihomo / Stash 内核，",
        "#  可把 shuzilm.cn、online-metrix.net 两行改成 REJECT-DROP。",
        "#",
        "#  若你的配置里已有 DOMAIN-KEYWORD,umeng,REJECT，",
        "#  可删掉本文件里 umeng 的两行，避免重复。",
        "#",
        "rules:",
    ]
    for rtype, domain, action, note in direct:
        out.append(f"  - {rtype},{domain},DIRECT")
    out.append("  # ── 运营商免密取号网关 ──")
    for rtype, domain, action, note in rej[:3]:
        out.append(f"  - {rtype},{domain},{CLASH_ACTION[action]}")
    out.append("  # ── 数字联盟指纹 / JSPatch 热更新后门 / ThreatMetrix 行为探针 ──")
    for rtype, domain, action, note in rej[3:6]:
        out.append(f"  - {rtype},{domain},{CLASH_ACTION[action]}")
    out.append("  # ── 遥测：秒针 / 穿山甲 / 友盟 ──")
    for rtype, domain, action, note in rej[6:]:
        out.append(f"  - {rtype},{domain},{CLASH_ACTION[action]}")
    return "\n".join(out) + "\n"


def main():
    for name, label in TARGETS:
        src = HERE / name
        if not src.exists():
            continue
        rules = parse(src)
        out = HERE / f"{src.stem}.rules.yaml"
        out.write_text(render(label, rules), encoding="utf-8")
        print(f"■ {out.name:<36} {len(rules)} 条")


if __name__ == "__main__":
    main()
