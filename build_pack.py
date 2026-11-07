#!/usr/bin/env python3
"""
把「拦截规则」与「苹果直连规则」合并成一份可直接粘贴的 QX 文本

来源（都是已有文件，不重复维护）:
    ios_noir_shield.conf       或  ios_noir_shield_lite.conf    [Rule] 段
    apple_local.qx.txt                                          host-suffix 行

产物:
    ios_noir_shield.qx.pack.txt
    ios_noir_shield_lite.qx.pack.txt

用法: python build_pack.py
"""
import re
from pathlib import Path

HERE = Path(__file__).parent
RULE_RE = re.compile(r"^(DOMAIN(?:-SUFFIX|-KEYWORD)?),([^,\s]+),([A-Z-]+)\s*(?:#.*)?$")
QX_ACTION = {"REJECT": "reject", "REJECT-TINYGIF": "reject",
             "REJECT-DROP": "reject", "DIRECT": "direct"}
QX_TYPE = {"DOMAIN-SUFFIX": "host-suffix", "DOMAIN": "host", "DOMAIN-KEYWORD": "host-keyword"}

TARGETS = [
    ("ios_noir_shield.conf", "完整版"),
    ("ios_noir_shield_lite.conf", "最小集"),
]


def parse_shield(path: Path):
    """返回 (direct 行, reject 行)，各自保持源文件顺序"""
    directs, rejects, in_rule, note = [], [], False, ""
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
        row = (QX_TYPE[rtype], domain, QX_ACTION[action], note)
        note = ""
        (directs if action == "DIRECT" else rejects).append(row)
    return directs, rejects


def parse_apple(path: Path):
    out, note = [], ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("#") or not line:
            c = line.lstrip("# ").strip()
            if c and not c.startswith("-") and not c.startswith("="):
                note = c
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3:
            continue
        out.append((parts[0], parts[1], parts[2], note))
        note = ""
    return out


def render(shield_name, label, directs, rejects, apple):
    total = len(directs) + len(rejects) + len(apple)
    out = [
        "#" + "=" * 60,
        f"#  iOS-NOIR Shield · {label} + 苹果本地直连 · Quantumult X 一体版",
        "#" + "=" * 60,
        "#",
        "#【怎么用】",
        "#  1. 小风车 → 配置文件 → 编辑 → 右上角箭头跳到 filter_local",
        "#  2. 把 规则开始 / 规则结束 之间的内容整段粘贴",
        "#  3. 必须在你的 final 行【之前】；原有同域规则建议先删掉，避免重复",
        "#  4. 保存 → 首页 VPN 开关关一次再打开",
        "#",
        "#【顺序不能乱】",
        "#  A 支付保护区 → B 拦截区 → C 苹果直连。QX 从上往下匹配，",
        "#  苹果那些域名与拦截清单没有交集，放最后只是为了让 8 条保护规则优先。",
        "#",
        "#【本文件不含 [filter_local] 标签行】不要补，否则重复段落会报错。",
        "#  分流层只认 direct / proxy / reject，reject-img 属重写层，写了会启动失败。",
        "#",
        f"#  合计 {total} 条：支付保护 {len(directs)} / 拦截 {len(rejects)} / 苹果直连 {len(apple)}",
        "#",
        "#" + "-" * 26 + " 规则开始 " + "-" * 26,
        "# ══════════ A. 支付保护区（必须最前）══════════",
    ]
    for t, d, a, n in directs:
        out.append(f"{t}, {d}, {a}")
    out.append("# ══════════ B. 拦截区（取号 / 指纹 / 后门 / 遥测）══════════")
    for t, d, a, n in rejects:
        if n:
            out.append(f"# {n}")
        out.append(f"{t}, {d}, {a}")
    out.append("# ══════════ C. 苹果服务走本地直连 ══════════")
    for t, d, a, n in apple:
        if n:
            out.append(f"# {n}")
        out.append(f"{t}, {d}, {a}")
    out += [
        "#" + "-" * 26 + " 规则结束 " + "-" * 26,
        "#",
        "# 说明：源头分别是 " + shield_name + " 与 apple_local.qx.txt，",
        "# 改规则请改源头，然后运行 python build_pack.py 重新生成本文件。",
    ]
    return "\n".join(out) + "\n"


def main():
    apple = parse_apple(HERE / "apple_local.qx.txt")
    for name, label in TARGETS:
        src = HERE / name
        if not src.exists():
            continue
        directs, rejects = parse_shield(src)
        stem = src.stem
        out = HERE / f"{stem}.qx.pack.txt"
        out.write_text(render(name, label, directs, rejects, apple), encoding="utf-8")
        print(f"■ {out.name:<38} 保护 {len(directs):>2} / 拦截 {len(rejects):>2} / 苹果 {len(apple):>2}"
              f"  = {len(directs) + len(rejects) + len(apple)} 条")


if __name__ == "__main__":
    main()
