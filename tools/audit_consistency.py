#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""跨模块数字与法条一致性校验器（P1-3 重建）。

背景
----
原 tools/audit_consistency.py（--sync / --calibrate）于 commit 4074d4cf 随安全
整改被误删。此后硬编码的计数常量与法条条款号失去自动校验闸门，酿成「1720 字符串
污染」：一次失败的全局替换把数字污染成「去末位 + 1720」（刑法第205条 → 第201720条、
42条 → 41720条等约 110 处）。污染虽已修复，但同类事故缺少闸门仍会再次发生。

本模块重建该闸门，并被 tools/verify_release.py 调用。

用法
----
    python tools/audit_consistency.py                 # 报告模式：列出全部不一致
    python tools/audit_consistency.py --calibrate     # 只输出权威值（供人工抄录）
    python tools/audit_consistency.py --sync          # 自动修正「计数常量」类不一致
    python tools/audit_consistency.py --strict        # 警告也计入失败（CI / 发布用）

四类检查
--------
    COUNT   计数常量：扫描「N 条规则 / 红线 / 线索链 / 证据链 / 分析链」硬编码，
            与引擎权威源比对，杜绝「规则库改了、数字没跟上」。
    LAW     法条条款号：扫描「第N条」，检出超范围（>1260 或 =0）、含污染串的畸形号。
    POLLUTE 1720 污染：检出 X1720 / 1720X / 纯 1720 三类污染形态（第205→201720 型）。
    TAX     税种名：税种名与标准税目表比对，检出错别字、乱码与不统一写法。

设计纪律
--------
* 权威值一律**实时从引擎读取**，本文件不写死任何计数——否则又是一处会漂移的硬编码。
* --sync 只修正「计数常量」，且只作用于白名单文件；法条与污染类问题一律人工修复。
* 退出码：0=通过；1=存在 ERROR（或 --strict 下存在 WARN）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ══════════════ 权威源：全部实时读取，禁止在此写死计数 ══════════════


def authoritative_values() -> Dict[str, int]:
    """从引擎权威源实时读取计数。任何一项读取失败都必须显式报错，
    绝不用历史数字兜底——兜底就是下一次污染的开始。"""
    from engine.fact_rules import governance_inventory
    from engine.tax_redlines import stats
    from engine.verified_rule_engine import VERIFIED_RULE_CATALOG

    inv = governance_inventory()
    return {
        "rules": int(inv["rules"]),
        "clue_paths": int(inv["clue_paths"]),
        "evidence_plans": int(inv["evidence_plans"]),
        "analysis_plans": int(inv["analysis_plans"]),
        "modules": int(inv["canonical_modules"]),
        "redlines": int(stats()["total"]),
        "verified_rules": int(len(VERIFIED_RULE_CATALOG)),
    }


# 计数常量的中文标签 → 权威键
COUNT_LABELS: Dict[str, str] = {
    "规则": "rules",
    "红线": "redlines",
    "线索链": "clue_paths",
    "证据链": "evidence_plans",
    "分析链": "analysis_plans",
    "原子规则": "verified_rules",
}

# 匹配「89 条规则」「红线 53 条」「规则=89」等写法
COUNT_PATTERN = re.compile(
    r"(?:(?P<n1>\d+)\s*条(?P<lbl1>规则|红线|线索链|证据链|分析链|原子规则))"
    r"|(?:(?P<lbl2>规则|红线|线索链|证据链|分析链|原子规则)\s*(?:=\s*)?(?P<n2>\d+)\s*条)"
)

# 历史上出现过、现已确定为错值的计数（按标签分列）。命中即 ERROR——这是最硬的闸门。
KNOWN_STALE: Dict[str, set] = {
    "rules": {1720, 1608, 41720, 201720},
    "redlines": {42, 1720, 41720},
    "clue_paths": {437, 1215, 1720, 41720},
    "evidence_plans": {781, 22, 1720, 41720},
    "analysis_plans": {48, 6, 1720, 41720},
    "verified_rules": {1720, 41720},
}
# 超过权威值 2 倍的声明视为「严重虚高」——排除「1 条规则」这类子集表述，
# 又能抓住 234 条证据链（权威 25）、1720 条规则（权威 89）这类明显过时口径。
INFLATION_FACTOR = 2

# 「规则」一词在本系统有歧义：权威目录规则(89) 与已验证原子规则(69) 都叫规则，
# 且存在「采样前200条规则」这类非总量表述。故该标签仅在命中已知错值时判 ERROR，
# 其余差异一律 WARN，交由人工判断。
AMBIGUOUS_LABELS = {"规则"}

# 计数检查整文件跳过：已确认的死代码，其内数字不再代表任何现行口径。
# static/js/rewrite_steps.py —— 一次性改写脚本，硬编码他人机器绝对路径、
# 全项目零引用，其中 1505/391/740/234 为已退役链资产的旧口径。
COUNT_SKIP_FILES = {
    "static/js/rewrite_steps.py",
}

# ══════════════ 扫描范围 ══════════════

SCAN_SUFFIXES = {".py", ".md", ".json", ".js", ".html", ".txt"}
SCAN_DIRS = ["engine", "tools", "static", "reports", "tests"]
# 不参与文本扫描的目录/文件（含运行期产物与第三方资源）
SCAN_EXCLUDE_PARTS = {
    "data", "node_modules", "__pycache__", ".git", ".venv",
    "uploads", "cache", "migrations",
}

# --sync 仅作用于这些文件（其余一律人工修复，避免重演 1720 事故）
SYNC_ALLOWLIST = {
    "engine/memory.py",
    "static/methodology_canonical_catalog.json",
}


def iter_scan_files() -> List[Path]:
    files: List[Path] = []
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in SCAN_SUFFIXES:
                continue
            rel = p.relative_to(ROOT)
            if any(part in SCAN_EXCLUDE_PARTS for part in rel.parts):
                continue
            files.append(p)
    return sorted(files)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


# ══════════════ 检查 1：计数常量 ══════════════


def check_counts(authoritative: Dict[str, int]) -> List[Tuple[str, str, str, int, int]]:
    """返回 [(级别, 文件相对路径, 标签, 文中值, 权威值), ...]"""
    issues: List[Tuple[str, str, str, int, int]] = []
    for path in iter_scan_files():
        text = _read(path)
        if not text:
            continue
        rel = _rel(path)
        if rel in COUNT_SKIP_FILES:
            continue
        if rel == "tools/audit_consistency.py" or set(rel.split("/")) & POLLUTION_SKIP_PARTS:
            continue  # 自检跳过 + 历史文档按时点快照处理
        for m in COUNT_PATTERN.finditer(text):
            label = m.group("lbl1") or m.group("lbl2")
            num = int(m.group("n1") or m.group("n2"))
            key = COUNT_LABELS.get(label or "")
            if not key:
                continue
            truth = authoritative[key]
            if num == truth:
                continue
            if num in KNOWN_STALE.get(key, set()):
                level = "ERROR"  # 命中历史错值：确定性错误
            elif num > truth * INFLATION_FACTOR and label not in AMBIGUOUS_LABELS:
                level = "ERROR"  # 严重虚高：过时的旧口径
            else:
                level = "WARN"   # 近值差异/歧义标签：供人工判断
            issues.append((level, rel, label, num, truth))
    return issues


# ══════════════ 检查 2：法条条款号 ══════════════

LAW_ARTICLE_PATTERN = re.compile(r"第\s*([0-9０-９]{1,7})\s*条")
# 已知法律的最大条数（超出即告警；表可扩展，未知法律不做该判定）
LAW_MAX_ARTICLE: Dict[str, int] = {
    "刑法": 452, "民法典": 1260, "税收征收管理法": 94, "企业所得税法": 60,
    "个人所得税法": 22, "增值税暂行条例": 28, "消费税暂行条例": 20,
    "土地增值税暂行条例": 15, "契税法": 23, "资源税法": 17,
    "环境保护税法": 28, "会计法": 52, "公司法": 266,
    "发票管理办法": 45, "住房公积金管理条例": 47,
}
# 任何法都不可能出现的条款号上界（民法典 1260 条为国内单行法上限）
ARTICLE_HARD_MAX = 1260


def check_law_articles() -> List[Tuple[str, str, str]]:
    """返回 [(级别, 文件相对路径, 说明), ...]"""
    issues: List[Tuple[str, str, str]] = []
    for path in iter_scan_files():
        text = _read(path)
        if not text:
            continue
        rel = _rel(path)
        if rel == "tools/audit_consistency.py":
            continue  # 本工具文档串中举例污染样本，跳过自检
        if set(rel.split("/")) & POLLUTION_SKIP_PARTS:
            continue  # 事故复盘报告会引用污染样本，属正常记述
        for m in LAW_ARTICLE_PATTERN.finditer(text):
            raw = m.group(1).translate(str.maketrans("０１２３４５６７８９", "0123456789"))
            if "1720" in raw:
                issues.append(("ERROR", rel, f"条款号含 1720 污染串：第{raw}条"))
                continue
            try:
                num = int(raw)
            except ValueError:
                issues.append(("ERROR", rel, f"条款号非数字：第{raw}条"))
                continue
            if num == 0:
                issues.append(("ERROR", rel, "条款号为 0：第0条"))
            elif num > ARTICLE_HARD_MAX:
                issues.append(("ERROR", rel, f"条款号超出单行法上限({ARTICLE_HARD_MAX})：第{num}条"))
        # 已知法律的条数上界判定（告警级，避免表不准造成误报拦截）
        for law, limit in LAW_MAX_ARTICLE.items():
            for m in re.finditer(re.escape(law) + r"\s*第?\s*([0-9]{1,5})\s*条", text):
                num = int(m.group(1))
                if num > limit:
                    issues.append(("WARN", rel, f"{law}第{num}条 超出已知上限 {limit}"))
    return issues


# ══════════════ 检查 3：1720 污染形态 ══════════════

# 三类形态：X1720（末位被替换）、1720X（首位被替换）、纯 1720（个位数被替换）
POLLUTION_PATTERNS = [
    re.compile(r"\d1720\b"),      # 第205条 → 第201720条 中的 201720
    re.compile(r"\b1720\d"),      # 1720X 形态
    re.compile(r"(?<![0-9])1720(?![0-9])"),  # 纯 1720（个位数污染）
]
# 允许出现 1720 的「文件 + 上下文特征」白名单：这些文件是把 1720 当作**检测目标**或
# 纯巧合（CSS 颜色），不是被污染的文本，误报会淹没真实污染。
POLLUTION_ALLOWLIST = {
    ("static/login.html", "#172033"),              # CSS 颜色巧合
    ("engine/report_standards.py", "_MALFORMED"),  # 运行时过滤畸形条款的护栏正则
    ("engine/report_standards.py", r"\d*1720"),    # 同上
    ("tools/verify_release.py", '"1720" not in'),  # 发布门禁自身断言
    ("tools/audit_consistency.py", "污染"),         # 本工具说明性文字
    ("tools/audit_consistency.py", "1720"),        # 本工具正则与说明
}
# 整目录跳过：历史审计报告是**时点快照**，会引用当时的旧计数与污染样本，
# 属正常记述；闸门只卡「现行代码与数据」，不改写历史文档。
POLLUTION_SKIP_PARTS = {"reports"}
# 整文件跳过：1720 在其中是**检测目标**而非被污染文本（护栏正则）
POLLUTION_SKIP_FILES = {
    "engine/report_standards.py",   # _MALFORMED_POLICY_RE 运行时过滤畸形条款号
    "static/id_remap.json",         # 旧规则 id → 新 id 映射表，1720 是合法旧 id
    "static/tax_agi_override.json", # 规则 id 命名（audit_rules_1720_*），非计数
}
# 允许出现 1720 的数字上下文：时间戳小数位（19.811720）、版本号等，属巧合
_NUMERIC_TOKEN_RE = re.compile(r"[0-9.]+")


def _is_numeric_coincidence(text: str, start: int, end: int) -> bool:
    """命中处若落在含小数点的长数字串（时间戳/浮点）内，判为巧合。"""
    left = start
    while left > 0 and (text[left - 1].isdigit() or text[left - 1] == "."):
        left -= 1
    right = end
    while right < len(text) and (text[right].isdigit() or text[right] == "."):
        right += 1
    token = text[left:right]
    return "." in token or len(token) > 7


def _rel(path: Path) -> str:
    """统一为正斜杠相对路径，避免 Windows 分隔符导致白名单失配。"""
    return str(path.relative_to(ROOT)).replace("\\", "/")


def check_pollution() -> List[Tuple[str, str, str]]:
    issues: List[Tuple[str, str, str]] = []
    for path in iter_scan_files():
        rel = _rel(path)
        if rel in POLLUTION_SKIP_FILES:
            continue
        if set(rel.split("/")) & POLLUTION_SKIP_PARTS:
            continue
        text = _read(path)
        if not text:
            continue
        for pat in POLLUTION_PATTERNS:
            for m in pat.finditer(text):
                if _is_numeric_coincidence(text, m.start(), m.end()):
                    continue
                snippet = text[max(0, m.start() - 18):m.end() + 12].replace("\n", " ")
                if any(rel == f and token in snippet for f, token in POLLUTION_ALLOWLIST):
                    continue
                issues.append(("ERROR", rel, f"疑似 1720 污染：…{snippet.strip()}…"))
    return issues


# ══════════════ 检查 4：税种名 ══════════════

# 标准税目表（与 tax_redlines.taxes 比对，检出错别字/不统一写法）
# 注：附加费、进口环节税、规费并非独立税种，但属合法申报口径，一并认可。
CANONICAL_TAXES = {
    "增值税", "消费税", "企业所得税", "个人所得税", "资源税",
    "城市维护建设税", "房产税", "印花税", "城镇土地使用税",
    "土地增值税", "车船税", "船舶吨税", "车辆购置税", "关税",
    "契税", "耕地占用税", "烟叶税", "环境保护税", "出口退税",
    "社会保险费", "住房公积金",
    "教育费附加", "地方教育附加",
    "进口环节增值税", "进口环节消费税", "进口环节关税",
}


def check_tax_names() -> List[Tuple[str, str, str]]:
    from engine.tax_redlines import REDLINES

    issues: List[Tuple[str, str, str]] = []
    for r in REDLINES:
        for tax in r.get("taxes", []) or []:
            if not isinstance(tax, str) or not tax.strip():
                issues.append(("ERROR", "engine/tax_redlines.py",
                               f"{r.get('id')} 税种名为空或非字符串"))
            elif tax.strip() not in CANONICAL_TAXES:
                # 告警而非错误：新增税种/附加费属正常扩展，但需人眼确认不是错别字
                issues.append(("WARN", "engine/tax_redlines.py",
                               f"{r.get('id')} 税种名不在标准税目表：{tax!r}（如属新增口径请补入 CANONICAL_TAXES）"))
    return issues


# ══════════════ 汇总与输出 ══════════════


def check_domains(authoritative: Dict[str, int]) -> List[Tuple[str, str, str]]:
    """域名一致性：tax_redlines.DOMAIN_ORDER 必须覆盖 REDLINES 实际出现的全部域。"""
    from engine.tax_redlines import REDLINES, DOMAIN_ORDER

    issues: List[Tuple[str, str, str]] = []
    actual = {r.get("domain") for r in REDLINES}
    missing = sorted(actual - set(DOMAIN_ORDER))
    if missing:
        issues.append(("ERROR", "engine/tax_redlines.py",
                       f"DOMAIN_ORDER 未覆盖实际存在的域：{missing}"))
    stale = sorted(set(DOMAIN_ORDER) - actual)
    if stale:
        issues.append(("WARN", "engine/tax_redlines.py",
                       f"DOMAIN_ORDER 含无红线残留域：{stale}"))
    return issues


def run_checks() -> Tuple[List[Tuple[str, str, str, int, int]],
                          List[Tuple[str, str, str]]]:
    authoritative = authoritative_values()
    counts = check_counts(authoritative)
    general = (check_law_articles() + check_pollution()
               + check_tax_names() + check_domains(authoritative))
    return counts, general


def print_report(counts, general, authoritative) -> int:
    errors = [i for i in counts if i[0] == "ERROR"] + [i for i in general if i[0] == "ERROR"]
    warns = [i for i in counts if i[0] == "WARN"] + [i for i in general if i[0] == "WARN"]

    print("=" * 78)
    print("跨模块数字与法条一致性校验")
    print("=" * 78)
    print("\n【权威值】（实时取自引擎，非本文件硬编码）")
    for k, v in authoritative.items():
        print(f"  {k:<16} = {v}")

    print("\n【COUNT 计数常量】")
    if not counts:
        print("  ✓ 全部一致")
    for lvl, rel, label, got, truth in counts:
        print(f"  {lvl}  {rel}: 「{label}」文中 {got} ≠ 权威 {truth}")

    for title, items in (("LAW/POLLUTE/TAX/DOMAIN 其他检查", general),):
        print(f"\n【{title}】")
        if not items:
            print("  ✓ 未发现问题")
        for lvl, rel, msg in items:
            print(f"  {lvl:<5} {rel}: {msg}")

    print("\n" + "-" * 78)
    print(f"ERROR {len(errors)} 项 | WARN {len(warns)} 项")
    print("-" * 78)
    return len(errors)


def sync_counts(authoritative: Dict[str, int]) -> int:
    """只修正计数常量，且只作用于 SYNC_ALLOWLIST 中的文件。

    法条条款号与 1720 污染一律人工修复——自动改写文本正是当年事故的成因。
    """
    changed = 0
    for rel in sorted(SYNC_ALLOWLIST):
        path = ROOT / rel
        if not path.exists():
            continue
        text = _read(path)
        if not text:
            continue
        original = text

        def _sub(m: re.Match) -> str:
            # changed 定义在 sync_counts 作用域内，嵌套函数须用 nonlocal；
            # 原写 global 会 NameError（--sync 模式从未真正跑通过，2026-09-12 修复）
            nonlocal changed
            label = m.group("lbl1") or m.group("lbl2")
            num_raw = m.group("n1") or m.group("n2")
            key = COUNT_LABELS.get(label or "")
            if not key:
                return m.group(0)
            truth = authoritative[key]
            if int(num_raw) == truth:
                return m.group(0)
            changed += 1
            if m.group("lbl1"):
                return f"{truth}条{label}"
            return f"{label} {truth} 条"

        text = COUNT_PATTERN.sub(_sub, text)
        if text != original:
            path.write_text(text, encoding="utf-8")
            print(f"  已同步 {rel}")
    print(f"共修正 {changed} 处计数常量")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="跨模块数字与法条一致性校验")
    parser.add_argument("--calibrate", action="store_true", help="只输出权威值")
    parser.add_argument("--sync", action="store_true", help="自动修正计数常量（仅白名单文件）")
    parser.add_argument("--strict", action="store_true", help="警告也计入失败")
    args = parser.parse_args()

    authoritative = authoritative_values()

    if args.calibrate:
        for k, v in authoritative.items():
            print(f"{k}={v}")
        return 0

    counts, general = run_checks()

    if args.sync:
        return sync_counts(authoritative)

    n_errors = len([i for i in counts if i[0] == "ERROR"]) + len([i for i in general if i[0] == "ERROR"])
    print_report(counts, general, authoritative)
    n_warns = (len([i for i in counts if i[0] == "WARN"])
               + len([i for i in general if i[0] == "WARN"]))
    if n_errors:
        return 1
    if args.strict and n_warns:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
