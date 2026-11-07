#!/usr/bin/env python3
"""
两档规则的覆盖率 / 误伤面量化对比
- 覆盖率: 你手机上真实被标记的追踪域名, 有多少被规则命中
- 误伤面: 你手机上 App 在 Info.plist 里声明的 ATS 例外域名, 有多少会被规则命中
          (命中越多 = 越可能有 App 因为这条规则出现功能异常)
用法: python coverage_report.py
"""
import re
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE.parent / "noir-src" / "noir-out"
RULE_RE = re.compile(r"^(DOMAIN(?:-SUFFIX)?),([^,\s]+),([A-Z-]+)\s*(?:#.*)?$")

# 只保留「看起来像目标」的 ATS 条目（过滤掉 0.0.0.0/0、NSExceptionXxx 这类键名）
ATS_NOISE = {"NSExceptionAllowsInsecureHTTPLoads", "NSExceptionRequiresForwardSecrecy",
             "NSIncludesSubdomains", "localhost", "example.com"}


def load_rules(path: Path):
    rejects, in_rule = [], False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.lower() == "[rule]":
            in_rule = True
            continue
        if line.startswith("[") and line.endswith("]"):
            in_rule = False
            continue
        if not in_rule or not line or line.startswith("#"):
            continue
        m = RULE_RE.match(line)
        if m and m.group(3) != "DIRECT":
            rejects.append(m.group(2).lower())
    return rejects


def hit(domain: str, suffixes) -> bool:
    return any(domain == s or domain.endswith("." + s) for s in suffixes)


def main():
    trackers = [l.strip().lower() for l in (OUT / "domains-trackers.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
    ats = [l.strip().lower() for l in (OUT / "domains-functional.txt").read_text(encoding="utf-8").splitlines()
           if l.strip() and l.strip() not in ATS_NOISE and "." in l.strip() and not l.strip()[0].isdigit()]

    sets = {
        "最小集 (lite)": load_rules(HERE / "ios_noir_shield_lite.conf"),
        "完整版 (full)": load_rules(HERE / "ios_noir_shield.conf"),
        "官方原文": load_rules(HERE.parent / "noir-src" / "shields" / "ios_noir_shield.conf"),
    }

    print(f"样本: 真机追踪域名 {len(trackers)} 个 / App 声明在用(ATS)域名 {len(ats)} 个\n")
    print(f"{'规则集':<14}{'规则数':>6}{'追踪覆盖':>12}{'命中ATS(误伤面)':>16}")
    print("─" * 52)
    for name, suffixes in sets.items():
        cov = [t for t in trackers if hit(t, suffixes)]
        fp = [a for a in ats if hit(a, suffixes)]
        print(f"{name:<14}{len(suffixes):>6}{f'{len(cov)}/{len(trackers)}':>12}{f'{len(fp)}/{len(ats)}':>16}")

    print("\n【最小集漏掉的追踪域名】")
    lite = sets["最小集 (lite)"]
    print("  " + ", ".join(t for t in trackers if not hit(t, lite)) or "  (无)")

    print("\n【完整版会命中的 ATS 域名（=真的可能有 App 在用）】")
    full = sets["完整版 (full)"]
    for a in [a for a in ats if hit(a, full)]:
        print(f"  {a}")


if __name__ == "__main__":
    main()
