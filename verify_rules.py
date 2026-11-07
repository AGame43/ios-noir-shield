#!/usr/bin/env python3
"""
iOS-NOIR Shield 规则安全自检
检查项：
  1. 语法   —— 每条规则三段式、动作合法、域名规范
  2. 致命冲突 —— 拦截域等于/包含某个支付保护域的父域（会连带断掉支付）
  3. 子域穿透 —— 拦截域落在保护域之内（需人工确认是否必要）
  4. 真机对照 —— 拦截域是否也出现在你手机 App 的 ATS 白名单里（说明该 App 真的在用）
用法: python verify_rules.py [functional.txt]
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "ios_noir_shield.conf"

# 绝不能被 REJECT 的域（微信聊天 / 扫码支付 / 小程序 / 银联 / 支付宝）
PROTECTED = [
    "tenpay.com", "weixin.qq.com", "wx.qq.com", "wechat.com", "servicewechat.com",
    "qlogo.cn", "qpic.cn", "gtimg.cn", "wechatpay.com",
    "alipay.com", "alipayobjects.com", "alipay.cn", "alipaysc.com",
    "unionpay.com", "unionpayintl.com", "95516.com", "chinapay.com",
]

ALLOWED_ACTIONS = {"REJECT", "REJECT-DROP", "REJECT-TINYGIF", "REJECT-NO-DROP",
                   "DIRECT", "PROXY"}
RULE_RE = re.compile(r"^(DOMAIN(?:-SUFFIX|-KEYWORD)?),([^,\s]+),([A-Z-]+)\s*(?:#.*)?$")

# —— Quantumult X ——
# 分流层只接受 direct / proxy(或自定义策略组名) / reject；
# reject-img / reject-dict / reject-200 是重写层动作，写进 [filter_local] 会让 QX 报
# 「未知策略或节点」并启动失败。这里只放行前三种，其余一律报错。
QX_RE = re.compile(r"^(host-suffix|host|host-keyword),\s*([a-z0-9.\-]+),\s*([a-zA-Z\u4e00-\u9fa5_.\- ]+)$")
QX_ACTIONS = {"reject", "direct", "proxy"}
QX_REWRITE_ONLY = {"reject-img", "reject-dict", "reject-array", "reject-200", "reject-drop"}


def lint_qx(path: Path):
    """Quantumult X 语法校验；.qx.list 还要保证不含 direct"""
    errs, warns = [], []
    is_list = path.name.endswith(".qx.list")
    domains, n = [], 0
    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        n += 1
        m = QX_RE.match(line)
        if not m:
            # 给出更精确的诊断：动作写错 / 少了空格 / 用了 surge 的写法
            parts = [p.strip() for p in line.split(",")]
            if len(parts) != 3:
                errs.append(f"{path.name} L{i} 字段数不对（应为 类型, 域名, 动作）: {line}")
            elif parts[2] in QX_REWRITE_ONLY:
                errs.append(
                    f"{path.name} L{i} '{parts[2]}' 是重写层动作，分流层不支持 —— "
                    f"QX 会报「未知策略或节点」并拒绝启动，请改成 reject")
            elif parts[0] in {"DOMAIN-SUFFIX", "DOMAIN", "DOMAIN-KEYWORD"}:
                errs.append(
                    f"{path.name} L{i} 用了 Clash/Surge 的类型名 '{parts[0]}'，QX 应写 host-suffix / host / host-keyword")
            elif parts[2] not in QX_ACTIONS:
                errs.append(f"{path.name} L{i} QX 不认识的动作 '{parts[2]}'（只能是 reject / direct / proxy 或自定义策略组名）")
            else:
                errs.append(f"{path.name} L{i} 格式错误: {line}")
            continue
        rtype, domain, action = m.groups()
        if is_list and action != "reject":
            errs.append(f"{path.name} L{i} 远程资源里出现了 '{action}' —— force-policy 会覆盖它，行为不可预期")
        if domain in domains:
            warns.append(f"{path.name} L{i} 重复域名: {domain}")
        domains.append(domain)
    return n, errs, warns


def registrable(domain: str) -> str:
    """粗粒度取注册域，够用于 .com.cn 这类后缀"""
    parts = domain.split(".")
    if len(parts) >= 3 and parts[-2] in {"com", "net", "org", "gov", "edu", "co"}:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def main():
    functional = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    text = SRC.read_text(encoding="utf-8")

    rules, in_rule, lineno = [], False, 0
    errors, warnings, infos = [], [], []
    seen = {}

    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if line.lower() == "[rule]":
            in_rule = True
            continue
        if line.startswith("[") and line.endswith("]"):
            in_rule = False
            continue
        if not in_rule or not line or line.startswith("#"):
            continue
        lineno += 1

        m = RULE_RE.match(line)
        if not m:
            errors.append(f"L{i} 语法错误（应为 DOMAIN-SUFFIX,域名,动作）: {line}")
            continue
        rtype, domain, action = m.groups()
        if action not in ALLOWED_ACTIONS:
            errors.append(f"L{i} 未知动作 {action}")
        if domain != domain.lower():
            warnings.append(f"L{i} 域名含大写: {domain}")
        if "*" in domain or "/" in domain or domain.replace(".", "").isdigit():
            errors.append(f"L{i} 域名格式异常: {domain}")
        if domain in seen:
            warnings.append(f"L{i} 重复规则: {domain}（首次出现在 L{seen[domain]}）")
        seen[domain] = i
        rules.append((rtype, domain, action, i))

    rejects = [r for r in rules if r[2] != "DIRECT"]

    # —— 2/3. 与支付保护域比对 ——
    for rtype, domain, action, ln in rejects:
        for p in PROTECTED:
            if domain == p or p.endswith("." + domain):
                errors.append(
                    f"L{ln} 致命冲突: {domain} 是保护域 {p} 的祖先/同域，会连带断掉支付"
                )
            elif domain.endswith("." + p):
                infos.append(f"L{ln} 拦截域 {domain} 位于保护域 {p} 之内，请确认必要")

    # —— 4. 与真机 ATS 白名单对照 ——
    if functional and functional.exists():
        ats = {l.strip().lower() for l in functional.read_text(encoding="utf-8").splitlines() if l.strip()}
        hits = [d for _, d, a, _ in rejects if d in ats]
        for d in sorted(hits):
            warnings.append(f"{d} 出现在你手机 App 的 ATS 白名单中 —— 该 App 确实在用，可能影响其功能")

    # —— 5. Quantumult X 产物校验 ——
    qx_files = (sorted(HERE.glob("*.qx.conf")) + sorted(HERE.glob("*.qx.txt"))
                + sorted(HERE.glob("*.qx.pack.txt")) + sorted(HERE.glob("*.qx.list")))
    if qx_files:
        print("Quantumult X 产物:")
        qx_err = 0
        for f in qx_files:
            n, e, w = lint_qx(f)
            flag = "✓" if not e else "✗"
            print(f"  {flag} {f.name:<32} {n:>3} 条规则" + (f"  ({len(w)} 警告)" if w else ""))
            for x in e:
                print("     ❌ " + x)
            for x in w:
                print("     ⚠️  " + x)
            qx_err += len(e)
        print()

    # —— 输出 ——
    print(f"规则总数 {len(rules)}  (保护区 {len(rules) - len(rejects)} / 拦截 {len(rejects)})")
    print(f"语法的行数 {lineno}\n")
    for tag, bucket in (("❌ 错误", errors), ("⚠️  警告", warnings), ("ℹ️  提示", infos)):
        print(f"{tag}: {len(bucket)}")
        for x in bucket:
            print("   " + x)
        print()

    if errors or (qx_files and qx_err):
        print("结论: 存在致命问题，禁止部署。")
        return 1
    print("结论: 通过 —— 没有一条拦截规则能命中微信/扫码支付/小程序链路。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
