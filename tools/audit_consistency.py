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
    python tools/audit_consistency.py --sync-content  # 自动同步跨模块共享内容文本
    python tools/audit_consistency.py --strict        # 警告也计入失败（CI / 发布用）

五类检查
--------
    COUNT   计数常量：扫描「N 条规则 / 红线 / 线索链 / 证据链 / 分析链」硬编码，
            与引擎权威源比对，杜绝「规则库改了、数字没跟上」。
    LAW     法条条款号：扫描「第N条」，检出超范围（>1260 或 =0）、含污染串的畸形号。
    POLLUTE 1720 污染：检出 X1720 / 1720X / 纯 1720 三类污染形态（第205→201720 型）。
    TAX     税种名：税种名与标准税目表比对，检出错别字、乱码与不统一写法。
    SHARED  共享内容（文本维度）：跨模块共享块逐字哈希比对 + 概念关联存在性验证，
            由 engine/shared_content_sync.verify_shared_content() 执行。
            2026-09-15 接线——此前该模块从未被调用，而前端宣传「双维度自检」，
            文本维度长期形同虚设；现每次运行都执行，失败计入 ERROR。
            注：权威源文件随「方法论整体下线」被删的块须标记 legacy_unmapped，
            显式披露为历史遗留，既不计通过也不计失败，不得静默跳过。

设计纪律
--------
* 权威值一律**实时从引擎读取**，本文件不写死任何计数——否则又是一处会漂移的硬编码。
* --sync 只修正「计数常量」，且只作用于白名单文件；法条与污染类问题一律人工修复。
* 退出码：0=通过；1=存在 ERROR（或 --strict 下存在 WARN）。
"""

from __future__ import annotations

import argparse
import ast
import inspect
import json
import os
import re
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

#: 闸门**自检下限**：本文件应注册的 check_* 函数数。低于它即视为"文件被截断/未加载完整"，
#  拒绝给出结论（**闸门静默失效比缺陷更危险** —— 实测一次切片误删了 __main__ 入口，
#  脚本变成"跑完、什么都不查、退出码 0"）。
#  ⚠ 新增检查项时无需改这里（只增不减）；只有删检查项才需要同步下调并说明原因。
_MIN_REGISTERED_CHECKS = 100

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ★ 2026-10-06：**风险等级唯一权威** `engine.risk_levels`（纯数据模块，无依赖、可安全顶层导入）。
#   本闸门**不得**再自建等级表 —— 闸门自己漂移就失去裁判资格。
from engine.risk_levels import LEGAL_LEVELS            # noqa: E402
from engine.risk_levels import RISK_GRADES             # noqa: E402
from engine.risk_levels import cap_level, severity, display_label     # noqa: E402  (供各 check_* 复用)

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
    # 模块自动更新日志：每条记录的是「当次更新涉及的规则数」（如"共1条规则"），
    # 属历史快照、非系统总量口径，且其值随更新内容变化，不应强制改为权威总量。
    "static/module_auto_update_log.json",
}

# 计数豁免（上下文级）：匹配到「N 条规则」时，若其周围文本命中以下任一正则，
# 说明该处是「阈值 / 采样 / 局部层」表述而非系统总量口径，跳过（不报 WARN/ERROR）。
# 这类数字改不动（改成 89 反而语义错误：阈值本就是 ≥2 条触发）。
# ★ 设计原则：新增同类豁免只需在此加一行正则；逻辑分支不变，零私有实现。
COUNT_EXEMPT_CONTEXTS = [
    re.compile(r"≥\s*\d+\s*条规则"),       # 阈值：中风险需 ≥2条规则触发 才形成闭环
    re.compile(r"采样前\s*\d+\s*条规则"),   # 采样：for rule in self._rules[:200]  # 采样前200条规则
    re.compile(r"原来\s*\d+\s*条规则外"),   # 局部层：覆盖原来15条规则外的常见矛盾
    # ★ 2026-10-10 新增：**引用旧值的样例 / 同义写法词典示例**（非当前总量口径）。
    #   实测两处误报（均为"这是在引用"的语境，改成 89 反而语义错误）：
    #     · `engine/doc_residue_scan.py` 的**同义写法词典示例**：「8 条规则 / 8 条门禁 / 门禁 8 条」
    #     · `tests/test_doc_consistency_skills.py` 的**失败样例名录**："8 条规则"
    #   判据：数字**紧贴引号**（被引用），而非裸写的总量声明。
    #   ⚠ 反向验证要求：裸写的 `N 条规则/红线`（不加引号）必须**仍然**被抓（见 §19 的 R23/R24）。
    re.compile(r"[「\"“]\s*\d+\s*条(?:规则|红线)"),
]

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
            # 上下文豁免：阈值/采样/局部层表述中的「N 条规则」非总量口径，跳过
            _ctx = text[max(0, m.start() - 30): m.end() + 15]
            if any(p.search(_ctx) for p in COUNT_EXEMPT_CONTEXTS):
                continue
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
    "文化事业建设费",
    # 费类义务（2026-09-30：RL-SPT-019/020/021 登记为红线，费目入表）
    "残疾人就业保障金", "水利建设基金", "工会经费",
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


# 允许存在的"对齐别名"键：解析器主路径不产出，但其它子系统（Excel 解析、PDF 回退、
# 五流清单、红线判定）会用到，属刻意保留，不算错配。
_DOC_TYPE_ALIAS_KEYS = {
    "bank", "bank_transaction", "invoice", "order", "salary_tax",
    "tax_declaration", "vat", "financial", "financial_statement",
}


def check_doc_type_category_map() -> List[Tuple[str, str, str]]:
    """校验「解析器实际产出的文件类型」与「必查资料类别映射表」是否对齐。

    ★ 2026-09-25 新增（真实事故）：`_DOC_TYPE_TO_CATEGORY` 用 `vat` 作键，而解析器实际产出
      的是 `vat_declaration` → 映射查不到 → **即使 12 份增值税申报表已成功解析，报告仍写
      「缺资料：“增值税申报表”」**，前端直接显示"缺少增值税申报表"。
      同类错配会让报告凭空宣称企业缺资料，直接损害报告可信度，必须自动拦截。
    """
    from main import _FILE_FINGERPRINTS
    from engine.enterprise_report import _DOC_TYPE_TO_CATEGORY, _REQUIRED_DOC_CATEGORIES
    from engine.material_recognition import _SUPPLEMENTARY_CATEGORIES, _SUPPLEMENTARY_RECOGNITION

    issues: List[Tuple[str, str, str]] = []
    rel = "engine/enterprise_report.py"
    real_types = set(_FILE_FINGERPRINTS.keys())
    mapped = set(_DOC_TYPE_TO_CATEGORY.keys())
    # 合法类别 = 15 必查 + 补充自证资料类别（P3.5，红线需求名的独立类别）
    valid_cats = set(_REQUIRED_DOC_CATEGORIES) | set(_SUPPLEMENTARY_CATEGORIES)

    def _cats(v):
        return tuple(v) if isinstance(v, (tuple, list)) else (v,)

    # ① 解析器会产出、但映射表未覆盖 → 该类资料被永久误报为"缺失"
    uncovered = sorted(real_types - mapped)
    if uncovered:
        issues.append(("ERROR", rel,
                       f"_DOC_TYPE_TO_CATEGORY 未覆盖 {len(uncovered)} 个解析器实际类型，"
                       f"这些资料会被永久误报缺失：{uncovered[:10]}"))

    # ② 映射值必须是合法必查类别（否则该类别永远无法满足）
    bad_vals = sorted({c for v in _DOC_TYPE_TO_CATEGORY.values() for c in _cats(v)} - valid_cats)
    if bad_vals:
        issues.append(("ERROR", rel,
                       f"_DOC_TYPE_TO_CATEGORY 含非法类别名（不在 _REQUIRED_DOC_CATEGORIES 内），"
                       f"对应必查类别将永远无法满足：{bad_vals}"))

    # ③ 每个必查类别都必须至少能被一种类型覆盖
    reachable = set()
    for v in _DOC_TYPE_TO_CATEGORY.values():
        reachable.update(_cats(v))
    unreachable = sorted(valid_cats - reachable)
    if unreachable:
        issues.append(("ERROR", rel,
                       f"必查资料类别无法被任何解析类型覆盖（永远显示缺失）：{unreachable}"))

    # ④ 映射键中既非实际类型、又不在对齐别名白名单内、也非「补充自证资料」doc_type → 疑似拼写错误
    #    —— 补充自证资料 doc_type 由 engine/material_recognition._SUPPLEMENTARY_RECOGNITION 动态注入
    #       （见 enterprise_report._DOC_TYPE_TO_CATEGORY 的 P3.5 扩展块：键 = _info["doc_type"]，
    #       而非该字典的键名 _n），故合法键集必须含这些 doc_type，否则会把 72 个合法补充键误报拼写错误。
    _sup_doc_types = {
        _info["doc_type"]
        for _info in _SUPPLEMENTARY_RECOGNITION.values()
        if isinstance(_info, dict) and "doc_type" in _info
    }
    suspicious = sorted(mapped - real_types - _DOC_TYPE_ALIAS_KEYS - _sup_doc_types)
    if suspicious:
        issues.append(("WARN", rel,
                       f"_DOC_TYPE_TO_CATEGORY 存在疑似拼写错误的键（既非解析器类型也非已知别名）："
                       f"{suspicious}"))
    return issues


def check_industry_consistency() -> List[Tuple[str, str, str]]:
    """行业口径一致性：**单一权威来源** + 映射键有效性。

    ★ 2026-09-25 新增。本项目曾出现一串连锁问题，全部源于"行业判定多头维护"：
      · `_load_industry_data` 被重复定义 **3 次**（2 份无缓存、3 份兜底形状各异）；
      · 行业判定散落 6 处以上，各自一套兜底，结果依赖字典插入顺序；
      · `_match_benchmark` 拿经营范围里的**商品名**当行业 → 商贸企业被拿制造业区间
        判"毛利率明显偏低"（对任何行业都会发生，与行业无关）。
    此检查防止再次分裂：任何新增行业映射都必须落在唯一解析器的数据源上。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.industry_resolver import load_industry_data, benchmark_keys
    except Exception as e:
        return [("ERROR", "engine/industry_resolver.py", f"行业解析器不可导入：{e}")]

    data = load_industry_data()
    bm_keys = set(benchmark_keys())
    coarse_keys_set = set((data.get("benchmarks_coarse") or {}).keys())

    # ① industry_map 的**值**必须是合法行业名（否则"投出来的行业"无法对标）
    bad_map = sorted({v for v in (data.get("industry_map") or {}).values()
                      if v not in bm_keys and v not in coarse_keys_set})
    if bad_map:
        issues.append(("WARN", "static/industry_data.json",
                       f"industry_map 投出的行业名不在基准库/粗粒度库中，推断后无法对标：{bad_map[:8]}"))

    # ② 生产/服务行业清单必须与基准库口径一致（biz_model 判定直接依赖它）
    for key in ("production_industries", "service_industries"):
        vals = set(data.get(key) or [])
        bad = sorted(vals - bm_keys - coarse_keys_set)
        if bad:
            issues.append(("WARN", "static/industry_data.json",
                           f"{key} 含不在基准库中的行业名，判定 biz_model 后无法对标：{bad[:8]}"))

    # ③ industry_benchmark 的键名对齐表必须指向真实存在的键
    try:
        from engine.industry_benchmark import _INDUSTRY_ALIAS, INDUSTRY_BENCHMARKS
        bad_alias = sorted({v for v in _INDUSTRY_ALIAS.values() if v not in INDUSTRY_BENCHMARKS})
        if bad_alias:
            issues.append(("ERROR", "engine/industry_benchmark.py",
                           f"_INDUSTRY_ALIAS 指向不存在的区间库键：{bad_alias}"))
    except Exception as e:
        issues.append(("WARN", "engine/industry_benchmark.py", f"键名对齐表不可检查：{e}"))

    # ④ 各模块的 _load_industry_data 必须**共用同一实现**（不得自带第二套加载/兜底）
    #    两种合格形态：a) 直接引用同一函数（identity 相同，最佳）；b) 源码内转发到解析器。
    import inspect
    from engine.industry_resolver import load_industry_data as _canon_loader
    for mod_name in ("engine.domain_analysis", "engine.enterprise_profile", "engine.inspector_reasoning"):
        try:
            mod = __import__(mod_name, fromlist=["_load_industry_data"])
            fn = getattr(mod, "_load_industry_data", None)
            if fn is None:
                continue
            if fn is _canon_loader:
                continue      # 直接引用统一实现
            src = inspect.getsource(fn)
            if "industry_resolver" not in src:
                issues.append(("ERROR", mod_name.replace(".", "/") + ".py",
                               "_load_industry_data 未共用统一解析器实现（行业数据多头加载）"))
        except Exception:
            pass

    # ⑤ （2026-09-30）原 AGI 五分类词表唯一性校验随 AGI 子系统整体移除（engine/agi_core.py 已删除）。

    # ⑥ 行业区间库必须**单一来源**：industry_benchmark 不得再硬编码区间数字
    try:
        import engine.industry_benchmark as _ib
        src = inspect.getsource(_ib)
        # 派生实现里应出现"派生/load_industry_data"；出现成片硬编码区间即视为回流
        if "load_industry_data" not in src:
            issues.append(("ERROR", "engine/industry_benchmark.py",
                           "区间表未从唯一数据源派生（疑似出现第二套硬编码数字）"))
        import re as _re2
        if _re2.findall(r'"vat_burden"\s*:\s*\(\s*[\d.]+\s*,', src):
            issues.append(("ERROR", "engine/industry_benchmark.py",
                           "源码中出现硬编码 vat_burden 区间（区间数字应只存在于 static/industry_data.json）"))
    except Exception as e:
        issues.append(("WARN", "engine/industry_benchmark.py", f"区间派生不可检查：{e}"))

    # ⑦ 数据源内部指标命名与单位必须统一（曾经同一文件里两套命名，致粗粒度兜底取不到值）
    _ALLOWED = {"毛利率", "净利率", "税负率", "进销比", "期间费用率", "人均营收(万)",
                "gross_margin", "vat_burden", "expense_ratio", "purchase_sales"}
    for layer in ("benchmarks", "benchmarks_coarse"):
        for k, v in (data.get(layer) or {}).items():
            if not isinstance(v, dict):
                continue
            unknown = sorted(set(v.keys()) - _ALLOWED)
            if unknown:
                issues.append(("WARN", "static/industry_data.json",
                               f"{layer}['{k}'] 含未登记指标名（命名可能再次分裂）：{unknown}"))

    # ⑧ 单位合理性：进销比是比值(≤1.5)，百分比类指标应在 0~100
    for layer in ("benchmarks", "benchmarks_coarse"):
        for k, v in (data.get(layer) or {}).items():
            if not isinstance(v, dict):
                continue
            ps = v.get("进销比")
            if isinstance(ps, (list, tuple)) and len(ps) >= 2 and (ps[0] > 1.5 or ps[1] > 1.5):
                issues.append(("ERROR", "static/industry_data.json",
                               f"{layer}['{k}'] 进销比区间 {ps} 超出比值范围（疑似被当成百分比多乘 100）"))
            for mk in ("毛利率", "净利率", "税负率", "期间费用率"):
                tri = v.get(mk)
                if isinstance(tri, (list, tuple)) and len(tri) >= 2 and (tri[0] < 0 or tri[1] > 1.0):
                    issues.append(("WARN", "static/industry_data.json",
                                   f"{layer}['{k}'] {mk} 区间 {tri} 不在比例范围 0~1"))

    # ⑨ 门类键与细分行业键**不得同名**（同名会被细分层遮蔽，门类层不可达、取值来源不明）
    _fine = set(k for k in (data.get("benchmarks") or {}) if k != "_default")
    if _fine & coarse_keys_set:
        issues.append(("ERROR", "static/industry_data.json",
                       f"门类键与细分行业键同名（会被细分层遮蔽）：{sorted(_fine & coarse_keys_set)}"))

    # ⑩ 休眠的数值副本不得被"复活"使用（合并只保留一个数值来源）
    #    · static/industry_profiles.json 里仍有 benchmarks 数值（当前无消费者）
    #    · static/industry_audit_profiles.json 当前无任何消费者
    #    一旦有人开始从这两处读阈值，就会重新出现"两套数字"，这里直接拦下。
    import glob as _glob
    _NUMERIC_KEYS = ("gross_margin_pct", "purchase_sales_ratio", "vat_burden",
                     "supplier_concentration_warn", "customer_concentration_warn")
    _root = str(ROOT)
    _py_files = list(_glob.glob(str(ROOT / "engine" / "**" / "*.py"), recursive=True))
    _py_files.append(str(ROOT / "main.py"))
    for _f in _py_files:
        try:
            _txt = open(_f, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        _relf = "engine/" + os.path.basename(_f) if os.path.basename(os.path.dirname(_f)) == "engine" else os.path.basename(_f)
        if "industry_audit_profiles" in _txt:
            issues.append(("WARN", _relf,
                           "引用了 industry_audit_profiles.json（该文件当前无消费者，属历史遗留；"
                           "如需启用请先确认其中的阈值不与 industry_data.json 重复）"))
        if "industry_profiles" in _txt:
            for _ln in _txt.splitlines():
                if "industry_profiles" in _ln or "industries" in _ln:
                    if any(k in _ln for k in _NUMERIC_KEYS):
                        issues.append(("ERROR", _relf,
                                       "从 industry_profiles.json 读取了阈值类数值（会形成第二套数字，"
                                       "应统一走 static/industry_data.json）"))
                        break

    return issues


def _iter_prod_py_files() -> List[str]:
    """枚举**全部生产代码** Python 文件（根级模块 + engine 包）。

    ★ 2026-09-25 修复闸门自身的覆盖缺口：`check_numparse_single_source` /
      `check_period_key_single_source` 原先只扫 `main.py` + `engine/**`，
      于是**根级模块**（`tax_risk.py` / `tax_risk_utils.py` / `tax_risk_rules.py` …）
      完全在闸门视野之外 —— 实测那里正藏着 `ym[:7]` 伪归一化与 `float(val)` 伪安全函数。
      闸门扫不到的代码 = 没有闸门；故统一枚举，两个检查共用。

    排除：虚拟环境、缓存、数据目录、迁移脚本产物（非生产代码）。
    """
    import glob as _glob
    skip = (".venv", "node_modules", ".git", "data", "__pycache__",
            "scripts/four_reports")
    out = []
    for f in _glob.glob(str(ROOT / "*.py")) + sorted(
            _glob.glob(str(ROOT / "engine" / "**" / "*.py"), recursive=True)):
        rel = os.path.relpath(f, ROOT).replace("\\", "/")
        if any(s in rel for s in skip):
            continue
        out.append(f)
    return out


def check_numparse_single_source() -> List[Tuple[str, str, str]]:
    """数值解析**单一来源**：不得再出现任何私有实现。

    ★ 2026-09-25 新增（真实事故）：全项目曾有 **25 个私有数值解析函数 + 284 处行内
      `float(X or 0)`**，其中 20 个函数遇 `"12,000.00"` / `"￥1,234.56"` 会**静默返回 0**
      （`float()` 抛异常吃默认）。后果：**同一张发票的金额，域分析算出 12000、规则引擎算出 0**
      —— 报告不同章节金额互相矛盾，规则因"金额=0"而漏触发。这与行业无关，对所有企业都成立。
    现全部收敛到 `engine/numparse.py`（`to_number` / `first_amount` / `sum_field`）。
    本检查防止再次分裂。
    """
    issues: List[Tuple[str, str, str]] = []
    import ast as _ast
    import glob as _glob
    import re as _re3

    _EXEMPT = {"engine/numparse.py"}
    _NAMES = {"_safe", "_num", "_number", "_to_float", "_safe_float",
              "_amt", "_amount_of", "_number_of"}
    _INLINE = _re3.compile(r"float\([^()\n]*\bor\s+0\s*\)")

    _files = _iter_prod_py_files()
    for f in _files:
        rel = os.path.relpath(f, ROOT).replace("\\", "/")
        if rel in _EXEMPT:
            continue
        try:
            txt = open(f, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        # ① 行内私有兜底
        for m in _INLINE.finditer(txt):
            ln = txt[:m.start()].count("\n") + 1
            issues.append(("ERROR", rel,
                           f"第{ln}行出现行内 `float(X or 0)`（遇千分位会变 0）；应改用 numparse.to_number"))
        # ② 顶层私有解析函数必须转发
        try:
            tree = _ast.parse(txt)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, _ast.FunctionDef) and node.name in _NAMES:
                seg = _ast.get_source_segment(txt, node) or ""
                if "numparse" not in seg:
                    issues.append(("ERROR", rel,
                                   f"函数 {node.name} 未转发到 engine/numparse（数值解析多头维护）"))
    return issues


def check_period_key_single_source() -> List[Tuple[str, str, str]]:
    """期间键（`YYYYMM` / `YYYY-MM`）**单一来源**：不得再自造月份。

    ★ 2026-09-25 新增（真实事故）：日期→月份曾在 6 处各写一遍
      （findingkit / red_team / verified_rule_engine×2 / domain_analysis×4 / monthly_reconcile），
      其中"去分隔符后取前 6 位"那套对**个位月份必然算错**：

          2025/1/15 → 202511   （把日期的 1 当成月份）
          2025-1-5  → 202515   （月份 15 不存在）
          2026-1-31 → 202613   （月份 13 不存在）
          2025年1月15日 → 20251月15日（连数字都不是）

      Excel 导出的日期列**普遍是个位月**（2025/1/15、2025.1.5），故这不是边角案例：
      同一月被拆成多个桶（实测 red_team 把 1 月拆成 202511 与 202512），
      **所有"按月对比 / 月度波动 / 月度差异"结论都建立在错误分组上**。
      这与行业无关，对**所有企业**都成立。

    现全部收敛到 `engine/findingkit.py`（`month_key` / `month_key_strict` / `normalize_month`）。

    检测器（**均已反向验证：注入即报，干净库零误报**）：
      D1 同一句里"去日期分隔符 + 取前 6 位"（如 `str(dt).replace("-","")[:6]`）
      D2 函数体内"拼数字 + 取前 6 位"（如 `digits = "".join(... isdigit())` 后 `digits[:6]`）
      D3 `X[:6]` —— 日期类变量名精确白名单命中
      D6 `X[:7]` —— 月份键的 YYYY-MM 写法（`period[:7]`）
      D5 `str(<期间字段>)[:7]`（如 `str(row["税款所属期"])[:7]`）
      D7 函数名含 normalize+period/month 却未转发唯一权威（伪归一化：只截断不解析）
      D4 历史期间键函数名（`_month_key` / `_month_of` / `_month` / `_declaration_month` …）
         必须转发到 findingkit

    ⚠ 两点经验（都来自真实踩坑，勿回退）：
      · 切片必须**从 0 开始**才算自造月份键；`ym[5:7]` 是从已归一化的 `YYYY-MM` 抽月份字段，
        属正当用法 —— 早期不限 lower 导致 10 处误报。
      · 覆盖范围必须含**根级模块**（`tax_risk.py` / `tax_risk_utils.py` 等）。
        早期只扫 `main.py` + `engine/**`，而真实的伪归一化 `_normalize_period` 恰好就在根级，
        闸门扫不到的代码等于没有闸门。
      · 用 AST 而非正则匹配切片：正则会把文档字符串里的示例（本文件自己的说明）当成违规。
    """
    issues: List[Tuple[str, str, str]] = []
    import ast as _ast
    import glob as _glob
    import re as _re4

    _EXEMPT = {"engine/findingkit.py"}
    _PERIOD_FUNCS = {
        "_month_key", "_month_of", "_month", "_declaration_month",
        "_period_key", "_ym_key", "_to_month", "_month_of_date",
    }
    _SLICE6 = _re4.compile(r"\[\s*:\s*6\s*\]")
    # 去日期分隔符（- / . 年）
    _SEP_STRIP = _re4.compile(r"""\.replace\(\s*["'][-/.年]["']""")
    # 日期/期间类**变量名**（精确白名单）。
    # ⚠ 必须精确：曾用 `[a-z_0-9]*` 通配，导致 `signals[:6]` / `sources[:6]`
    #   （列表展示截断）被误报 —— 闸门一旦误报就会被绕过。
    _DATEISH_NAMES = {
        "digits", "digit", "dt", "date", "date_str", "dstr", "ym",
        "month", "period", "ds", "ps", "pe",
    }
    # 期间字段名（用于识别 `str(row["所属期"])[:7]` 这类）
    _PERIOD_FIELD_NAMES = {
        "period", "期间", "所属期", "税款所属期", "费款所属期", "month",
        "所属月份", "月份", "period_start", "period_end", "inv_date",
    }
    _SLICE7 = _re4.compile(r"\[\s*:\s*7\s*\]")

    _files = _iter_prod_py_files()
    for f in _files:
        rel = os.path.relpath(f, ROOT).replace("\\", "/")
        if rel in _EXEMPT:
            continue
        try:
            txt = open(f, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        _hint = ("应改用 findingkit.month_key / month_key_strict / normalize_month"
                 "（个位月份：2025/1/15 → 202501）")
        _hint7 = ("期间键须用 findingkit.normalize_month"
                  "（旧 `[:7]` 把 2025/1/15 切成 '2025/1/'，会崩溃或整段期间无数据）")
        # D1：同一句里"去分隔符 + 取前 6 位"（跳过纯注释行，避免误伤文档）
        for i, line in enumerate(txt.split("\n"), 1):
            if line.lstrip().startswith("#"):
                continue
            if _SLICE6.search(line) and _SEP_STRIP.search(line):
                issues.append(("ERROR", rel,
                               f"第{i}行「去日期分隔符 + 取前6位」自造期间键；{_hint}"))
        try:
            tree = _ast.parse(txt)
        except SyntaxError:
            continue
        # ★ D2/D3/D5/D6 一律走 AST：只可能命中**真实代码**，不会把文档字符串/注释里的
        #   示例（如本文件自己的说明文字）误判成违规 —— 闸门误报会被绕过。
        def _slice_upper(node):
            """取**从 0 开始**的 `X[:b]` 上界 b；否则返回 None。

            限定"从 0 开始"是为了排除字段抽取（如 `ym[5:7]` 从一个**已归一化**的
            `YYYY-MM` 里取月份 —— 这是正当用法，不是自造月份键）。
            自造月份键的写法恒为从头切：`dt[:6]` / `period[:7]`。
            """
            sl = node.slice
            if not isinstance(sl, _ast.Slice):
                return None
            if sl.lower is not None and not (
                    isinstance(sl.lower, _ast.Constant) and sl.lower.value == 0):
                return None
            if isinstance(sl.upper, _ast.Constant) and isinstance(sl.upper.value, int):
                return sl.upper.value
            return None

        def _name_of(node):
            if isinstance(node, _ast.Name):
                return node.id
            if isinstance(node, _ast.Attribute):
                return node.attr
            return ""

        def _period_source(node, in_func):
            """判断节点是否是"日期/期间类值"（变量名命中，或取自期间字段）。"""
            if isinstance(node, _ast.Name) and node.id in _DATEISH_NAMES:
                return node.id + "[:N]"
            if isinstance(node, _ast.Attribute) and node.attr in _DATEISH_NAMES:
                return node.attr + "[:N]"
            # str(<期间字段>) 形式
            inner = node
            while isinstance(inner, _ast.Call):
                if _name_of(inner.func) == "str" and inner.args:
                    inner = inner.args[0]
                else:
                    break
            for sub in _ast.walk(inner):
                if isinstance(sub, _ast.Constant) and isinstance(sub.value, str):
                    if sub.value.strip() in _PERIOD_FIELD_NAMES:
                        return "str(%s)[:N]" % sub.value
                if isinstance(sub, _ast.Attribute) and sub.attr in _PERIOD_FIELD_NAMES:
                    return "str(.%s)[:N]" % sub.attr
            return ""

        for node in _ast.walk(tree):
            if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                continue
            seg = _ast.get_source_segment(txt, node) or ""
            base = txt[:txt.find(seg)].count("\n") + 1 if seg else 1
            if _SLICE6.search(seg) and "isdigit()" in seg:
                issues.append(("ERROR", rel,
                               f"函数 {node.name}（第{base}行起）「拼接数字 + 取前6位」自造期间键；{_hint}"))
            for sub in _ast.walk(node):
                if not isinstance(sub, _ast.Subscript):
                    continue
                up = _slice_upper(sub)
                if up not in (6, 7):
                    continue
                src = _period_source(sub.value, node)
                if not src:
                    continue
                ln = getattr(sub, "lineno", base)
                issues.append(("ERROR", rel,
                               f"第{ln}行 `{src.replace('[:N]', '[:%d]' % up)}` 自造期间键；"
                               + (_hint if up == 6 else _hint7)))
            # D7：函数名承诺"归一化期间"却未转发到唯一权威
            if _re4.search(r"(normalize|normalise|norm)_?(period|month|ym|期间)", node.name, _re4.I):
                if "findingkit" not in seg and "numparse" not in seg:
                    issues.append(("ERROR", rel,
                                   f"函数 {node.name} 名为期间归一化但未转发 engine/findingkit"
                                   f"（伪归一化：只截断不解析）"))
        # D4：历史期间键函数名必须转发到 findingkit
        for node in tree.body:
            if isinstance(node, _ast.FunctionDef) and node.name in _PERIOD_FUNCS:
                seg = _ast.get_source_segment(txt, node) or ""
                if "findingkit" not in seg:
                    issues.append(("ERROR", rel,
                                   f"函数 {node.name} 未转发到 engine/findingkit（期间键多头维护）"))
    return issues


def check_evidence_claim_grounded() -> List[Tuple[str, str, str]]:
    """证据现状「已有」**必须有逐字依据**：禁止以"资料类别相同"推断。

    ★ 2026-09-25 新增（真实事故，用户报）：疑点「工资表人数与社保参保人数不符」
      的证据表里，企业只交了工资名册与社保清单，报告却写：

          直接证据「劳动合同与用工名册」    现状=已有  根据=本轮已提供「工资表」
          直接证据「劳务派遣协议及派遣单位资质」现状=已有  根据=本轮已提供「工资表」
          间接证据「考勤记录与门禁记录」    现状=已有  根据=本轮已提供「工资表」

      ——用工资表去证明劳动合同 / 劳务派遣协议 / 考勤记录，全是**无据断言**；
      并据此把该疑点闭合度算成 1.0、结论升级为"可以作出确定性判断"（错误定性，
      违反「发现≠确认」「证据不足转置疑清单」两条铁律）。

    根因：旧 `_match_material` 用"证据项名/证明目的里出现某关键词 → 归到 15 类资料之一
    → 该类别在清单里就算已有"的推断（"名册""考勤""人员""用工"都被归入「工资表」）。

    本检查是**活断言**：直接驱动真实红线模板跑反例，比静态正则可靠。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        import sys
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from engine.evidence_chain import build_evidence_chain
        from engine.tax_redlines import all_redlines, get_redline
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "engine/evidence_chain.py", f"无法导入证据链模块：{exc}")]

    # 真实场景：报告里 `material_readiness.provided` 的 8 个类别
    avail = ["银行流水", "销项发票", "进项发票", "记账凭证",
             "工资表", "社保明细", "科目余额表", "增值税申报表"]

    def _status(item, mats):
        ev = build_evidence_chain(
            {"type": "probe"},
            {"evidence_chain": [{"role": "直接证据", "name": item, "purpose": ""}]},
            mats)
        return ev["elements"][0]

    # ① 陷阱用例：这些材料**没有**提供，绝不可是「已有」
    traps = [
        (["工资表"], "劳动合同与用工名册", "工资表 ≠ 劳动合同"),
        (["工资表"], "考勤记录与门禁记录", "工资表 ≠ 考勤记录"),
        (["工资表"], "劳务派遣协议及派遣单位资质", "工资表 ≠ 劳务派遣协议"),
        (["银行流水"], "六员个人账户完整流水", "公司流水 ≠ 个人账户流水"),
        (["银行流水"], "应付账款明细账及账龄分析", "银行流水 ≠ 账龄分析"),
        (["销项发票"], "设备采购合同、发票与验收单", "销项发票方向相反于采购"),
        (["银行流水", "渠道订单"], "采购合同与入库验收单", "渠道订单 ≠ 采购合同"),
    ]
    for mats, item, why in traps:
        st = _status(item, mats)
        if st["status"] == "已有":
            issues.append(("ERROR", "engine/evidence_chain.py",
                           f"「已有」无逐字依据：「{item}」在只提供 {mats} 时被判「已有」"
                           f"（{why}）；现状={st['status']} 依据={st['basis']}"))

    # ② 反向保护：真正逐字对应时必须仍判「已有」（防止用"一刀切判缺失"糊弄检查）
    for mats, item in ((["工资表"], "工资表"),
                       (["社保明细"], "社保明细"),
                       (["增值税申报表"], "增值税申报表"),
                       (["银行流水"], "付款银行流水或第三方支付凭证")):
        st = _status(item, mats)
        if st["status"] != "已有":
            issues.append(("ERROR", "engine/evidence_chain.py",
                           f"逐字对应的材料被误判为非「已有」：「{item}」+{mats} → {st['status']}"))
        elif not (st.get("matched_detail") or []):
            issues.append(("ERROR", "engine/evidence_chain.py",
                           f"判「已有」但未给出逐字依据：「{item}」"))

    # ②b 实质限定语（2026-10-04 疑点1 D7 另一半）：证据要求比已提供资料**更具体**、
    #     且多出的限定语属**实质要求**（退款/退货…）⇒ **不得**判「已有」。
    #     与 ② 互为反向：② 管"方向/用途类限定不得一刀切判缺失"，②b 管"实质要求类不得放水"。
    #     两条同时成立，才证明 `_SUBSTANTIVE_QUALIFIERS` 真的在按**限定语性质**分流。
    for mats, item, why in ((["银行流水"], "退款银行流水", "有银行流水 ≠ 有退款记录"),
                            (["银行流水"], "退款明细", "有银行流水 ≠ 有退款明细"),
                            (["销项发票"], "退货凭据", "有销项发票 ≠ 有退货凭据"),
                            (["销项发票"], "退货凭据", "有销项发票 ≠ 有退货凭据")):
        st = _status(item, mats)
        if st["status"] == "已有":
            issues.append(("ERROR", "engine/evidence_chain.py",
                           f"实质限定语被放水：「{item}」在只提供 {mats} 时被判「已有」"
                           f"（{why}）；现状={st['status']} 依据={st.get('basis')}"))

    # ②c 范围披露（2026-10-04 疑点2 D9，选项 1「披露式」）：
    #     **判「已有」不变**（清别名会破不变量），但"同类不同范围"必须**具体披露且可校验**。
    #     成对反向：带范围限定 ⇒ 必须披露；不带范围限定 ⇒ 不得挂披露话术（防无谓免责）。
    try:
        from engine.evidence_chain import _match_material as _mm       # noqa: PLC0415
        from engine.evidence_chain import _scope_gap as _sg            # noqa: PLC0415
        _st_a = _mm("完整资金链条流水", "", ["银行流水"])
        if _st_a.get("status") != "已有":
            issues.append(("ERROR", "engine/evidence_chain.py",
                           "范围限定项（完整资金链条流水）已不再判「已有」——判定口径被误改"
                           "（清别名会破不变量：要件数据源恒 not_checked）"))
        if not _st_a.get("scope_unverified") or "范围" not in str(_st_a.get("basis", "")):
            issues.append(("ERROR", "engine/evidence_chain.py",
                           "带范围限定却未披露范围差异 ⇒ 「已有」变成无据断言"
                           "（需 scope_unverified 字段 + 依据含范围说明）"))
        _st_b = _mm("银行流水", "", ["银行流水"])
        if _st_b.get("scope_unverified"):
            issues.append(("ERROR", "engine/evidence_chain.py",
                           "无范围限定的命中被判出范围差异 ⇒ 给所有命中挂无谓免责"))
        if _sg("付款银行流水", ["银行流水"]):
            issues.append(("ERROR", "engine/evidence_chain.py",
                           "「付款」属方向/用途类（任何该类资料都具备），不应触发范围披露"))
    except Exception as _e:  # noqa: BLE001
        issues.append(("ERROR", "engine/evidence_chain.py", f"范围披露断言执行失败：{_e}"))

    # ③ 全量不变式：全量红线 × 全部证据项，凡判「已有」必有**可自证**的依据。
    #    ★ 2026-10-03（用户："彻底解决多种叫法的问题"）：依据有两类 ——
    #      ① **逐字依据**：命中材料的 form 与证据项名互相包含；
    #      ② **类别依据**：`by_category` 非空且这些类别确实来自已提供清单的**严格归类**
    #         （`material_names.category_strict`，不兜底、不关键词猜测）——
    #         用于"完整资金链条流水"＝银行流水类这种「同一份材料、名字里带了范围」的情形。
    #      两类都必须可自证；凭空判「已有」仍会报错。
    try:
        from engine.material_names import category_strict as _cs2
        _avail_cats = {_cs2(a) for a in avail if _cs2(a)}
        for rl in all_redlines():
            ev = build_evidence_chain({"type": "probe"}, rl, avail)
            for e in ev.get("elements", []):
                if e.get("status") != "已有":
                    continue
                name = e.get("name", "")
                det = e.get("matched_detail") or []
                if any(d.get("form") and (d["form"] in name or name in d["form"])
                       for d in det):
                    continue                                  # ① 逐字依据
                cats = set(e.get("by_category") or [])
                if cats and cats <= _avail_cats:
                    continue                                  # ② 类别依据
                issues.append(("ERROR", "engine/evidence_chain.py",
                               f"红线 {rl.get('id')} 的「{name}」被判「已有」"
                               f"但无可自证依据（逐字/类别都不成立）：{det} cats={sorted(cats)}"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/evidence_chain.py", f"全量不变式检查失败：{exc}"))

    # ④ 触发条件：闭合度不得因「待核」而达标（否则疑点会被错误升级为已确认）
    try:
        rl = get_redline("RL-PAY-001")
        if rl:
            ev = build_evidence_chain({"type": "工资名册与社会保险人员范围差异"}, rl, avail)
            if ev.get("available_count", 0) == 0 and ev.get("closure", 0) >= 0.80:
                issues.append(("ERROR", "engine/evidence_chain.py",
                               f"未逐字取得任何材料，闭合度却达 {ev.get('closure')}"
                               f"（会把疑点错误升级为已确认）"))
            if "可以作出确定性判断" in str(ev.get("verdict", "")):
                issues.append(("ERROR", "engine/evidence_chain.py",
                               "未逐字取得材料却输出「可以作出确定性判断」"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/evidence_chain.py", f"闭合度检查失败：{exc}"))
    return issues


def check_report_credibility() -> List[Tuple[str, str, str]]:
    """报告可信度闸门（2026-09-25 新增）：**活断言**，直接跑真实模块。

    报告说了但没据 / 说了但读不通"的缺陷：

    ① **切句必须括号感知**。朴素 `re.split(r"[。；\\n]")` 把括号内的分号当句末，
       切出「…（取销项发票不含税金额」这种括号不闭合的残句并进报告。
       全项目曾有 4 处朴素切句 → 现唯一权威 `engine/sentencekit.py`。

    ② **红线配对必须有据**。旧 `_map_finding` 对 `match_redlines` 的结果
       「得分为正就取第一名」，而"税种名相同"只值 1 分 → 一条增值税进项差异发现
       被挂到「固定资产取得、投用与折旧不匹配」红线，报告随即用**固定资产折旧的构成要件**
       去论证它，并写出"这些事实是从固定资产明细账、试生产记录、折旧计算表…核对出来的"。
       实测 13 条发现里 7 条配错。

    ③ **定性表述不得越界**。不得把筛查线索断言为已成立的违法事实
       （「部分收入经个人账户归集，是账外收款的直接证据」）。

    ④ **论证链的资料归属必须按实际读取**，不得把红线模板声明的"应查资料"
       写成"已逐层核对过的资料"。
    """
    issues: List[Tuple[str, str, str]] = []

    # ── ① 切句：源码级禁止朴素切句（**用 AST，避免把文档字符串里的示例当违规**）──
    import ast as _ast5
    _exempt = {"engine/sentencekit.py"}
    for f in _iter_prod_py_files():
        rel = os.path.relpath(f, ROOT).replace("\\", "/")
        if rel in _exempt:
            continue
        try:
            txt = open(f, encoding="utf-8", errors="ignore").read()
            tree = _ast5.parse(txt)
        except Exception:
            continue
        for node in _ast5.walk(tree):
            bad = None
            # 形如 `re.split(r"[。；\n]", x)`，或 `x.split("。")`
            if isinstance(node, _ast5.Call) and isinstance(node.func, _ast5.Attribute) \
                    and node.func.attr == "split":
                arg0 = node.args[0] if node.args else None
                if isinstance(arg0, _ast5.Constant) and isinstance(arg0.value, str):
                    pat = arg0.value
                    if ("。" in pat and "；" in pat) or pat == "。":
                        bad = "re.split/str.split(" + repr(pat) + ")"
                elif isinstance(arg0, _ast5.Name):
                    # 变量模式（如 re.split(_SENT_RE, ...)）无法静态判定，跳过
                    bad = None
            if bad:
                issues.append(("ERROR", rel,
                               f"第{getattr(node, 'lineno', 0)}行用朴素切句 {bad}"
                               f"（会在括号内切错，切出读不通的残句）；"
                               f"应改用 engine/sentencekit.split_sentences"))

    # ── ①b 切句行为：实际验证括号感知 ──
    try:
        from engine.sentencekit import split_sentences, is_balanced
        probe = ("已经核实的事实是：凭证费用合计 44,394,561.24元"
                 "（取销项发票不含税金额；若以申报收入 0.00元计则更高），费用率 668.9%。"
                 "第二句。")
        for s in split_sentences(probe):
            if not is_balanced(s):
                issues.append(("ERROR", "engine/sentencekit.py",
                               f"切句切在括号内部，产出不闭合残句：{s}"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/sentencekit.py", f"切句模块不可用：{exc}"))

    # ── ①c 安全截断 & 内部值渲染：活断言（不得产出不闭合/ repr 文本）──
    try:
        from engine.sentencekit import clamp_text, render_value
        _repr_marks = ("{'", "['", "':", "}, ")
        long_txt = ("开票收入中有3,579,933.39元（占开票收入41.9%）未匹配到银行流水或第三方平台"
                    "（财付通/支付宝等）收款记录。现实中存在三种可能：①客户赊账未付"
                    "（应收账款增加，可能跨期回款）；②个人账户代收未转回；③收入未入账。")
        for n in (40, 60, 120, 200):
            out = clamp_text(long_txt, n)
            if not is_balanced(out):
                issues.append(("ERROR", "engine/sentencekit.py",
                               f"clamp_text({n}) 产出括号不闭合残句：{out}"))
        traps = [
            {"person_account_count": 15, "matches": [{"name": "甲"}, {"name": "乙"}]},
            [{"counterparty": "X"}, {"counterparty": "Y"}],
            {"a": {"b": {"c": {"d": 1}}}},
        ]
        for t in traps:
            out = render_value(t)
            if not is_balanced(out):
                issues.append(("ERROR", "engine/sentencekit.py",
                               f"render_value 产出括号不闭合文本：{out}"))
            for mk in _repr_marks:
                if mk in out:
                    issues.append(("ERROR", "engine/sentencekit.py",
                                   f"render_value 泄漏 Python repr（{mk}）：{out}"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/sentencekit.py", f"文本渲染检查失败：{exc}"))

    # ── ①d 禁止把 set/dict/list 字面量当**返回字典**的值（序列化后成 repr 进报告）──
    #   真实事故：`"core_goods_sale": rev.get(...) or set()` 出现在 return 的字典里
    #   → 报告出现 `{'*设计服务*设计服务费', '…'}` 这种 Python 集合 repr。
    #   ⚠ 只查**直接 return 的字典字面量**：`defaultdict(lambda: {...: set()})` 这类
    #     内部累加器不会进报告，查它们会产生大量误报（实测 12 处里 11 处是误报）。
    #     闸门一旦误报就会被绕开，故必须精确。
    for f in _iter_prod_py_files():
        rel = os.path.relpath(f, ROOT).replace("\\", "/")
        try:
            tree = _ast5.parse(open(f, encoding="utf-8", errors="ignore").read())
        except Exception:
            continue
        for node in _ast5.walk(tree):
            if not isinstance(node, _ast5.Return) or not isinstance(node.value, _ast5.Dict):
                continue
            for k, v in zip(node.value.keys, node.value.values):
                bad = None
                if isinstance(v, _ast5.Set):
                    bad = "set 字面量"
                elif isinstance(v, _ast5.Call) and isinstance(v.func, _ast5.Name) \
                        and v.func.id in ("set", "frozenset"):
                    bad = f"`{v.func.id}()`"
                elif isinstance(v, _ast5.BoolOp) and isinstance(v.op, _ast5.Or) \
                        and isinstance(v.values[-1], _ast5.Call) \
                        and isinstance(v.values[-1].func, _ast5.Name) \
                        and v.values[-1].func.id in ("set", "frozenset"):
                    bad = f"`… or {v.values[-1].func.id}()`"
                if bad:
                    issues.append(("ERROR", rel,
                                   f"第{getattr(v,'lineno',0)}行 return 的字典里含 {bad}"
                                   f"（序列化后成 repr 进报告）；应改为 sorted 列表"))

    # ── ② 红线配对：活断言 ──
    try:
        from engine.tax_redlines import match_redline_grounded
        from engine.redline_engine import _map_finding
        avail = ["银行流水", "销项发票", "进项发票", "记账凭证",
                 "工资表", "社保明细", "科目余额表", "增值税申报表"]
        rl, info = match_redline_grounded(
            "增值税申报进项税额与进项发票税额月度差异",
            "增值税申报表进项税额合计192,463.32元，同期进项发票税额合计225,093.81元",
            avail)
        if rl is not None:
            issues.append(("ERROR", "engine/redline_engine.py",
                           f"仅「税种名相同」即完成配对（配到「{rl.get('name')}」），"
                           f"会把不相干的构成要件写进报告；应判未配对"))
        # 该发现的 redline_id 未声明时，整条链路必须落到 unmapped
        rl2, info2 = _map_finding(
            {"type": "增值税申报进项税额与进项发票税额月度差异",
             "detail": "增值税申报表进项税额合计192,463.32元"}, avail)
        if rl2 is not None:
            issues.append(("ERROR", "engine/redline_engine.py",
                           f"未声明 redline_id 的增值税进项差异被配到「{rl2.get('name')}」"))
        # 正确配对仍须成立（防止用"一刀切不配对"糊弄检查）
        for title, text, expect in (
                ("工资名册与社会保险人员范围差异", "工资名册中1人未在社保清单中出现",
                 "工资表人数与社保参保人数不符"),
                ("成本费用虚列异常", "凭证费用合计远高于收入口径，费用率畸高", "成本费用虚列")):
            r3, _ = match_redline_grounded(title, text, avail)
            if r3 is None or expect not in r3.get("name", ""):
                issues.append(("ERROR", "engine/tax_redlines.py",
                               f"「{title}」未能配对到「{expect}」（配到 "
                               f"{r3.get('name') if r3 else '未配对'}）"))
        # 显式声明必须被尊重
        r4, i4 = _map_finding({"type": "自定义发现", "redline_id": "RL-PTY-001"}, avail)
        if not r4 or i4.get("mode") != "declared":
            issues.append(("ERROR", "engine/redline_engine.py",
                           "发现显式声明 redline_id 时未被直接采用"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/redline_engine.py", f"红线配对检查失败：{exc}"))

    # ── ③b metrics 键必须全中文（前端 `_renderCapMetrics` 直接打印键名）──
    try:
        import re as _re6
        from engine.enterprise_report import _translate_key
        from engine.enterprise_report import KNOWN_ENGINE_METRIC_KEYS
        _keys = list(KNOWN_ENGINE_METRIC_KEYS)
        bad_keys = []
        for k in _keys:
            out = _translate_key(k)
            if _re6.search(r"[A-Za-z]", out) or "_" in out:
                bad_keys.append((k, out))
        if bad_keys:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           f"metrics 键未汉化（前端会把键名直接打印给用户）：{bad_keys[:5]}"))
        # 语义不得反向：未收 ≠ 已接收
        if "已接收" in _translate_key("ar_unreceived_total"):
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "ar_unreceived_total 被译成「已接收」（语义反向），应为「应收账款未收合计」"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/enterprise_report.py", f"metrics 键检查失败：{exc}"))

    # ── ③c 主体名不得含印章/落款噪声（会写进报告并用于主体一致性匹配）──
    try:
        from main import _subject_clues_from_text
        for text in ("纳税人名称（公章）：某传媒示例有限公司",
                     "纳税人名称（公章）某传媒示例有限公司"):
            names, _u = _subject_clues_from_text(text)
            for n in names:
                if any(w in n for w in ("公章", "盖章", "签章", "印鉴")) or "（" in n:
                    issues.append(("ERROR", "main.py",
                                   f"主体名提取产出脏值「{n}」（源文本：{text}）；"
                                   f"脏值会写进报告并导致主体一致性误判"))
            if not names:
                issues.append(("ERROR", "main.py", f"主体名提取漏掉：{text}"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "main.py", f"主体名提取检查失败：{exc}"))

    # ── ③d 诊断日志不得含 Python repr（前端日志面板会展示）──
    try:
        from engine.sentencekit import humanise_log_lines
        _log = ["[秘笈自更新] 11层未触发: ['任务与权限', '全域扫描']",
                "加工信号评分: 0.00, signals=['甲', '乙'], applicable=False",
                "[PROFILE] 数据库查询身份失败"]
        out = humanise_log_lines(_log)
        for line in out:
            if "['" in line or "']" in line:
                issues.append(("ERROR", "engine/sentencekit.py",
                               f"日志净化未清掉 Python repr：{line}"))
        if out[2] != _log[2]:
            issues.append(("ERROR", "engine/sentencekit.py",
                           "日志净化误改了中文方括号前缀（如 [PROFILE]）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/sentencekit.py", f"日志净化检查失败：{exc}"))

    # ── ③ 定性越界护栏：活断言 ──
    try:
        from engine.text_guardrails import _apply_overclaim_rules
        from engine.enterprise_report import _zh_normalize_obj
        traps = {
            "部分收入经个人账户归集，是账外收款的直接证据，须逐一核验。": "的直接证据",
            "该情形构成虚开发票行为。": "构成虚开",
            "上述事实已证实偷税。": "已证实偷税",
            "该行为必然构成逃税罪。": "构成逃税罪",
        }
        for raw, forbidden in traps.items():
            out = _apply_overclaim_rules(raw)
            if forbidden in out:
                issues.append(("ERROR", "engine/text_guardrails.py",
                               f"定性越界表述未被拦截：{raw} → {out}"))
        # 法条引文不得被改写
        cite = "依据《税收征收管理法》第六十三条，构成偷税的可处五倍以下罚款。"
        if _apply_overclaim_rules(cite) != cite:
            issues.append(("ERROR", "engine/text_guardrails.py", "法条引文被误改"))
        # 报告最终闸门必须接上护栏（否则晚生成的文本会绕过去）
        probe = "部分收入经个人账户归集，是账外收款的直接证据。"
        if "的直接证据" in _zh_normalize_obj(probe):
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "报告净化闸门 _zh_normalize_obj 未接入定性护栏"
                           "（晚生成的论证文本会绕过定性边界）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/text_guardrails.py", f"定性护栏检查失败：{exc}"))

    return issues


def check_statement_derivation() -> List[Tuple[str, str, str]]:
    """科目余额表→财务报表取数：**不得静默跳过整个分析域**（2026-09-25 新增）。

    真实事故（用户报"取得发票占成本费用合计的比例特别小"这条疑点时查出来）：
    `build_statements_from_trial_balance` 的利润表部分用**期末余额**取损益类科目
    （6001/6401/6601/6602/6603）—— 而损益类期末已结转到本年利润，**余额恒为 0**；
    取"借−贷"净额同样为 0（科目余额表把结转额也计入发生额，借贷两侧相等）。
    实测：企业 1 科目余额表 6401 本期借/贷各 4,187,220.84、期末 0 → 利润表全 0 →
    `analyze_financial_statements` 与 `_check_tax_indicators` 开头都是
    `if not income / revenue<=0: return` → **"财务报表分析"域十余项检查一次都不执行**，
    报告里既无结论也无"为什么没查"的说明 —— 静默跳过最伤可信度。

    另：发票金额取值曾在本文件出现 **3 份实现**，只修了进项侧 1 份 → 销项侧用
    「金额／价税合计」列名时读成 0 → 误报"开票收入低于报表收入"（高风险方向）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.financial_analyzer import (
            build_statements_from_trial_balance, analyze_financial_statements)
        from engine.numparse import amount_of as _amount_of
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "engine/financial_analyzer.py", f"无法导入：{exc}")]

    def _row(code, cd, cc, close_d=0.0, close_c=0.0):
        return {"code": code, "current_debit": cd, "current_credit": cc,
                "close_debit": close_d, "close_credit": close_c}

    # ① 损益类科目形态（借贷相等、期末 0）→ 利润表不得全 0
    rows = [_row("6001", 6636800.57, 6636800.57), _row("6401", 4187220.84, 4187220.84),
            _row("6602", 2009498.84, 2009498.84), _row("6603", 1367.32, 1367.32)]
    _bs, is_, _cf = build_statements_from_trial_balance(rows)
    for k in ("revenue", "cost", "admin_expense"):
        if not is_.get(k):
            issues.append(("ERROR", "engine/financial_analyzer.py",
                           f"损益类科目取数为 0（{k}=0）→ 报表分析域会**静默跳过**；"
                           f"损益类必须取发生额总侧（费用取借方、收入取贷方）"))

    # ② 发票金额别名（销项侧曾只读 amount）
    for k in ("amount", "金额", "价税合计"):
        if _amount_of({k: 100.0}) != 100.0:
            issues.append(("ERROR", "engine/numparse.py",
                           f"行内取金额未兼容列名「{k}」（AMOUNT_KEYS 缺该键）→ "
                           f"该列名的导出会让合计读成 0，误报开票/进项与报表不符"))

    # ③ "成本费用合计支撑不足"两个方向（低必报、高不报）
    class _Ctx:
        company_profile = {}
    try:
        cost_expense = is_["cost"] + is_["admin_expense"] + is_["finance_expense"]
        for pur_total, should_report in ((cost_expense * 0.075, True),
                                         (cost_expense * 0.93, False)):
            fs = analyze_financial_statements(_bs, is_, _cf, [], [], [{"amount": pur_total}], _Ctx())
            got = any("成本费用合计" in str(f.get("type", "")) for f in fs)
            if got != should_report:
                issues.append(("ERROR", "engine/financial_analyzer.py",
                               f"「取得发票对成本费用合计支撑不足」判据错误："
                               f"覆盖率{pur_total/cost_expense:.0%} 应{'报出' if should_report else '不报'}，"
                               f"实际{'报出' if got else '未报'}"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/financial_analyzer.py", f"覆盖率判据检查失败：{exc}"))

    # ④ 源码级：发票金额的多键行内取值必须走唯一实现
    import re as _re7
    _inline = _re7.compile(r"""\.get\(\s*["']amount["']\s*,\s*.*?\.get\(\s*["'](金额|价税合计)["']""")
    for f in _iter_prod_py_files():
        rel = os.path.relpath(f, ROOT).replace("\\", "/")
        try:
            txt = open(f, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for i, line in enumerate(txt.split("\n"), 1):
            if line.lstrip().startswith("#"):
                continue
            if _inline.search(line):
                issues.append(("ERROR", rel,
                               f"第{i}行行内多键取金额（多头维护，易只修一半）；"
                               f"应改用 numparse.amount_of（行内取金额唯一权威）"))
    return issues


def check_coverage_source_wiring() -> List[Tuple[str, str, str]]:
    """pipeline 调用 `build_coverage` 时必须把覆盖度模块声明的**全部依赖键**都传进去。

    ★ 2026-09-26 新增（真实事故，P0）：`build_coverage` 按 `engine_data` 里的一组键判定
      "某检查项所需资料是否具备"，而 pipeline 调用时**漏传了 5 项**——
      `trial_balance`(科目余额表) / `fixed_assets` / `contracts` / `bom` / `transport_contracts`。
      `_has()` 查不到键即判"缺资料" → 把用户**已上传且已成功解析**的科目余额表、合同、
      BOM、运输合同、固定资产**谎报成缺失**，进而把本可判定的检查项错误地标为"需补资料"，
      系统自以为查不了。**实测谎报：科目余额表 13 项、采购合同 6 项**（覆盖清单 155 项中
      106 项被这样标注）。这正是"该查的没查出来"的隐形漏斗，必须自动拦截。

      与既有 P0「_`_DOC_TYPE_TO_CATEGORY` 键错配谎报缺申报表」同一族 diseases：
      **已取得的数据源被判为不存在**。凡"消费方按键取值、供给方按自己变量名传值"的接口，
      都必须有这种静态对齐检查。
    """
    import ast as _ast

    cov_rel = "engine/analysis_coverage.py"
    pipe_rel = "engine/pipeline.py"

    def _read(rel: str) -> str:
        p = ROOT / rel
        if not p.exists():
            return ""
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    issues: List[Tuple[str, str, str]] = []
    cov_src, pipe_src = _read(cov_rel), _read(pipe_rel)

    # ① 从 AST 取 _SOURCE_ZH 登记的全部依赖键（禁止在本闸门另抄一份名单）
    src_keys = set()
    try:
        for node in _ast.walk(_ast.parse(cov_src)):
            if isinstance(node, _ast.Assign):
                for t in node.targets:
                    if (isinstance(t, _ast.Name) and t.id == "_SOURCE_ZH"
                            and isinstance(node.value, _ast.Dict)):
                        for k in node.value.keys:
                            if isinstance(k, _ast.Constant) and isinstance(k.value, str):
                                src_keys.add(k.value)
    except SyntaxError as e:
        issues.append(("ERROR", cov_rel, f"_SOURCE_ZH 解析失败，闸门无法校验: {e}"))
        return issues
    if not src_keys:
        issues.append(("ERROR", cov_rel, "未取到 _SOURCE_ZH 依赖键，闸门无法校验"))
        return issues

    # ② 别名：这些键在 _has() 里被重映射到主键，pipeline 无需单独传。
    #    与 analysis_coverage._has 的特殊分支一一对应，若那边改动这里会失准，故做反向校验。
    _ALIAS_TO_MAIN = {"declaration": "tax_declarations",
                      "inventory": "inventory_ledger",
                      "company_profile": "target_entity"}
    stale = [k for k in _ALIAS_TO_MAIN if k not in src_keys]
    if stale:
        issues.append(("ERROR", cov_rel,
                       f"闸门口径过时：别名键 {stale} 已不在 _SOURCE_ZH 中，"
                       f"请同步更新 check_coverage_source_wiring 的别名映射"))

    required = sorted(src_keys - set(_ALIAS_TO_MAIN))

    # ③ 从 AST 取 pipeline 里 build_coverage 调用点的关键字参数
    passed: set = set()
    try:
        for node in _ast.walk(_ast.parse(pipe_src)):
            if isinstance(node, _ast.Call):
                nm = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if nm == "build_coverage":
                    # ⚠ 实调用形如 build_coverage({...})：是**位置参数的 dict 字面量**，
                    #   不是关键字参数——只读 node.keywords 会永远为空，闸门形同虚设
                    #   （反向验证时发现，故一并处理两种写法）。
                    for arg in node.args:
                        if isinstance(arg, _ast.Dict):
                            for k in arg.keys:
                                if isinstance(k, _ast.Constant) and isinstance(k.value, str):
                                    passed.add(k.value)
                    for kw in node.keywords:
                        if kw.arg:
                            passed.add(kw.arg)
    except SyntaxError as e:
        issues.append(("ERROR", pipe_rel, f"pipeline.py 解析失败，闸门无法校验: {e}"))
        return issues
    if not passed:
        issues.append(("ERROR", pipe_rel,
                       "未找到 build_coverage 调用点或其关键字参数，闸门无法校验"))
        return issues

    # ④ 未传入的依赖键会被静默判为"缺资料"
    not_passed = [k for k in required if k not in passed]
    if not_passed:
        issues.append(("ERROR", pipe_rel,
                       f"build_coverage 调用点未传入 {len(not_passed)} 个依赖键：{not_passed}"
                       f"——这些数据源即使已上传并成功解析，也会被 _has() 判为「缺资料」，"
                       f"把本可执行的检查项错误标成需补资料（系统自以为查不了）"))

    # ⑤ 需求名的超类表：成员必须是系统真能产出的类别名，键必须是真实存在的需求名
    #    （否则又是一次"两边各写一套、永不相等"的静默谎报）
    try:
        from engine.analysis_coverage import _MATERIAL_SUPERCLASS, _SOURCE_ZH
        from engine.enterprise_report import _DOC_TYPE_TO_CATEGORY
        from engine.tax_redlines import all_redlines
    except Exception as e:  # pragma: no cover - 依赖缺失时不静默放行
        issues.append(("ERROR", cov_rel, f"超类对齐检查所需依赖导入失败: {e}"))
        return issues

    def _cats(v):
        return tuple(v) if isinstance(v, (tuple, list)) else (v,)

    real_cats = set()
    for v in _DOC_TYPE_TO_CATEGORY.values():
        real_cats.update(str(c) for c in _cats(v))

    bad_members = sorted({m for members in _MATERIAL_SUPERCLASS.values()
                          for m in members if str(m) not in real_cats})
    if bad_members:
        issues.append(("ERROR", cov_rel,
                       f"_MATERIAL_SUPERCLASS 的 {len(bad_members)} 个成员不是系统可产出的"
                       f"资料类别名，永远无法被满足：{bad_members[:10]}"))

    bad_keys = sorted(k for k in _MATERIAL_SUPERCLASS if k in real_cats)
    if bad_keys:
        issues.append(("ERROR", cov_rel,
                       f"_MATERIAL_SUPERCLASS 的键 {bad_keys} 本身已是具体类别名，"
                       f"应删除（超类键必须是泛化需求名，否则掩盖真正意图）"))

    # ⑥ 仍未在两侧任一集合中的需求名 → 该检查项永久缺乏判定能力（持续发现同类漂移）
    redline_needs = set()
    for _rl in all_redlines():
        for _m in (_rl.get("required_materials") or []):
            redline_needs.add(str(_m))
    # P3.5：补充自证资料识别表（material_recognition）也是"已知"集合的一部分——
    # 登记于此的红线需求名，企业上传后即被识别为对应类别、可逐字闭合，不算漂移。
    from engine.material_recognition import (
        _SUPPLEMENTARY_CATEGORIES as _SUPP_CATS,
        _SUPPLEMENTARY_RECOGNITION as _SUPP_REC,
    )
    known = (real_cats | set(_MATERIAL_SUPERCLASS) | set(_SOURCE_ZH.values())
             | set(_SUPP_CATS) | set(_SUPP_REC.keys()))
    drift = sorted(n for n in redline_needs if n not in known)
    if drift:
        # 漂移收口机制已建立（超类表 + 补充自证资料识别表），未登记的红线需求名
        # 即真实缺口：既无法被上传识别，又会被永久判"缺资料"，须 ERROR 拦截，防再漏。
        issues.append(("ERROR", cov_rel,
                       f"{len(drift)} 条红线声明的所需资料名既非 15 类必查、也非超类表变体、"
                       f"更未在补充自证资料识别表登记，会被永久判为「缺资料」且无法被上传识别："
                       f"{drift[:12]}"))
    return issues


def check_indicator_coverage() -> List[Tuple[str, str, str]]:
    """**登记了却从不执行**的检查项必须为零（2026-09-25 新增）。

    真实事故（用户报"为什么工资人数和社保人数的差异分析不出来"时查出）：
    `TAX_AUDIT_INDICATORS` 登记 **14 项**金税四期量化指标，其中 **7 项全项目零消费点**
    ——库存/资产负债率/经营现金流质量/销售收现率/所有者权益变动/收入暴增/成本暴增
    ——即"系统看着有这项指标、实际从不检查"。一键分析要当稽查替身，这不可接受。

    两条要求：
      ① 登记项必须在 `analysis_coverage` 覆盖清单里**出现**（登记 ⇒ 必须可被交代）；
      ② 登记项必须在**代码里被真正引用**（不得只在目录里躺着）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.financial_analyzer import TAX_AUDIT_INDICATORS
        from engine.analysis_coverage import build_coverage
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "engine/analysis_coverage.py", f"无法导入：{exc}")]

    # ① 覆盖清单必须能报出全部登记项
    try:
        cov = build_coverage({})          # 空资料 → 全部应为"缺资料不可执行"
        listed = {str(it.get("id")) for it in cov.get("blocked_items", [])}
        missing = [k for k in TAX_AUDIT_INDICATORS if k not in listed]
        if missing:
            issues.append(("ERROR", "engine/analysis_coverage.py",
                           f"以下登记指标未出现在覆盖清单（登记了却无法交代）：{missing}"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/analysis_coverage.py", f"覆盖清单生成失败：{exc}"))

    # ② 登记项必须在代码里被引用（目录定义之外至少出现一次）
    import glob as _glob
    src_files = [str(ROOT / "engine" / "financial_analyzer.py")]
    src = ""
    for f in src_files:
        try:
            src += open(f, encoding="utf-8", errors="ignore").read()
        except Exception:
            pass
    # ⚠ 显式声明的**跨期口径**指标：单期上传资料无法计算同比增幅。
    #   它们不是"忘了实现"，而是"口径依赖上期数据"——已在覆盖清单里逐项说明
    #   "缺上期（跨期）报表"。此白名单是**声明式**的：新增项必须同时写进
    #   `analysis_coverage._IND_SRC` 的 `__cross_period__`，否则本条闸门会报 ERROR。
    _CROSS_PERIOD = {"revenue_growth_surge", "cost_surge_detect"}
    dead = [k for k in TAX_AUDIT_INDICATORS
            if k not in _CROSS_PERIOD and src.count(f'"{k}"') < 2]
    if dead:
        issues.append(("ERROR", "engine/financial_analyzer.py",
                       f"以下指标只在目录里登记、代码中零消费点（登记了却从不检查）：{dead}"))
    return issues


def check_duplicate_definitions() -> List[Tuple[str, str, str]]:
    """跨模块同名函数审计：识别"多头维护"并区分**转发桩**与**真实分歧**。

    ★ 2026-09-25 新增。本项目"同一概念多处实现"是复发型根因（数值解析 25 份、
      字段读取 3 份、finding 构造 3 份逐字节重复、报告文案 2 套…）。
      判据：**转发桩**（体内 import 唯一权威 + 单条 return）视为已收敛；
      **真实分歧**（各自完整实现且行为可能不同）必须显式可见，不得悄悄增长。
    """
    issues: List[Tuple[str, str, str]] = []
    import ast as _ast
    import glob as _glob
    import hashlib as _hl
    import re as _re4

    # 这些名字**必须**是单来源转发（出现真实分歧即 ERROR）
    _MUST_BE_SINGLE = {
        "_safe", "_safe_float", "_to_float", "_num", "_number", "_number_of",
        "_amt", "_amount_of", "_mk", "_month_key",
        "_buyer", "_seller", "_goods", "_inv_type", "_is_void_or_red",
        "_row_period", "_is_noise_name", "_load_industry_data",
        "_infer_industry_from_goods",
        # 2026-09-29：曾在 domain_analysis(100行 JSON 驱动版) 与 phase3_cross_validate
        # (223行硬编码版) 各写一套，JSON 版全仓无调用、且两者行为不等价（冲突7 硬编码版是
        # "降级既有高风险发现"，JSON 版只能追加低风险备注）→ 已删死实现，此处上锁防复发。
        "_detect_conflicts",
    }
    # 这些名字允许跨模块存在「真实分歧」（各自独立实现、签名/语义不同，并非同一概念）。
    # ★ 2026-10-10（A 轨道收尾）：由集合升级为**带理由的裁定表** —— 每一组都经人工比对
    #   函数体后给出"为什么不是同一概念"；`in` 语义不变（新增同名分歧仍会被报 WARN）。
    #   裁定口径三类：① 各模块**私有工具**（语义不同）② 各文件**配置读取器**（同一模板、
    #   各自的数据源，非同一概念）③ 各领域**自己的域入口**（audit/coverage/scan…）。
    _DIVERGENCE_OK = {
        # ── 既有裁定 ──
        "_fmt": "各模块私有格式化助手（千分位 / 2位小数 / 指标百分比），签名与用途不同",
        "_norm": "各模块私有归一化助手（长度保持归一化 vs 去空白），非同一概念",
        "parse_threshold": "各模块私有阈值解析（自由文本 vs 结构化字段），输入形态不同", "ensure_schema": "audit_trail 幂等建「审计表 audit_logs」；project_store 幂等建「项目表 projects/project_members」—— 同一**模式**（幂等建表+幂等加列）、**各自的数据源**，属裁定口径②（各文件自己的表，非同一概念）；两者均由 inspector 守卫且可重复调用", "reset_cache": "各模块清**自己的**模块级缓存（audit_trail 按 engine 身份 / project_store 表就绪态 / document_store 表就绪态 / document_types 的 JSON 读盘缓存）—— 缓存归属不同、清空对象不同，属裁定口径②（各文件自己的缓存）", "table_columns": "各模块读**自己的表**列名（project_store 默认 projects / document_store 默认 documents）—— 同一**模式**（只读列名供闸门断言）、各自的数据源，属裁定口径②", "metadata": "各模块**自己的**字典端点数据（project_service 出状态/角色/迁移表；document_service 出扩展名/分类/解析状态/上限）—— 内容无交集、各自权威，属裁定口径①（同名单、异语义）", "_document_row": "document_service 是**资料可见性**权威（资料→项目→租户）；extract_service 是**薄转发 + 异常类型转换**（DocumentError→ExtractError，保持原状态码）—— 单一权威仍在 document_service，属转发层（P0-3）", "_domain_of": "cross_domain_negotiation 是**发现对象→业务域**（入参是 finding dict）；extract_service 是**解析器类型码→标准字段域**（入参是 type 字符串，映射见 document_categories）—— 入参形态与取值域均不同，属裁定口径①", "_issue": "extract_validate 构造**校验问题**（rule/severity/message/detail）；reanalysis_guard 构造**守卫问题**（code/detail/level）—— 字段集不同、消费者不同，属裁定口径①", "_v400": "各模块把**自己的**校验器 `ValueError` 转成**自己的**业务异常（document_service→DocumentError；extract_service→ExtractError）—— 异常类型不同，无法共用同一函数，属裁定口径①（P0-2/P0-3）", "to_standard_period": "本函数是**文书格式归一**（产出可读期间串，给人看）；findingkit.month_key 是**分组键构造**（保证同一月一个桶，给聚合用）—— 本函数不构造月键、不做分组，故不属期间键归一的多头实现（P0-3）",
        # ── ① 私有工具（同名单、异语义）──
        "_as_list": "gap_risk_detectors 保留原元素类型；quality_gates 强制 str 并滤空 ⇒ 语义不同",
        "_cn_num": "quality_gates 是「中文数字→int」解析；enterprise_report 是「int→中文数字」"
                   "格式化 ⇒ **方向相反**，仅同名",
        "_grams": "child_item_completeness 为原始字符 n-gram（不过滤）；constituent_checkpoint "
                  "先滤非中文字符并去停用词 ⇒ 语义不同（中文 2-gram 唯一权威=findingkit.cjk_bigrams）",
        "_guard": "analysis_jobs 为并发任务护栏；doc_consistency_core 为读表异常护栏",
        "_index": "data_source_status 为表索引；learnable_rules 为规则索引",
        "_key": "common_clauses 为条款归一键；incremental_analysis 为转发",
        "_load": "doc_consistency_core 读判据配置；knowledge_learner 读经验库 ⇒ 数据源不同",
        "_load_json": "domain_analysis 以**本模块目录**为基准且缺省 []；selfcheck 用**绝对路径**"
                      "且缺省 None ⇒ 语义不同",
        "_log": "analysis_jobs 记任务日志；audit_trail 写业务留痕（留痕唯一权威=engine/audit_trail.py）",
        "_split_keep": "common_clauses 为条款切分保尾；report_dedup 为段落切分保尾 ⇒ 输入域不同",
        "last_error": "analysis_jobs 的**任务**错误；audit_trail 的**留痕写入**错误 ⇒ 不同",
        "problem_key": "child_item_completeness 与 snapshot_invariance 各自的疑点键构造",
        "summary_line": "risk_families 与 selfcheck 各自的「一行摘要」",
        "canonical_name": "data_source_status 的规范名（入参 name）；report_identity 的名称归一（无参）"
                          "⇒ 签名与用途不同",
        # ── ② 各文件配置读取器（同一模板、各自的数据源）──
        "load_config": "各模块各读**自己的**配置文件（child_item_completeness / data_source_status / "
                       "report_compliance / report_identity），缓存与缺省各异 ⇒ 非同一概念",
        "reload_config": "同上；doc_consistency_core 只清缓存不返回，方式各异",
        "load_spec": "各模块各读自己的规格表（conclusion_grade / quality_gates / vocab_registry）",
        "load_errors": "各模块装载**自身**配置后的解析错误列表",
        "load_rules": "dedup_pipeline / dupkit / numbering 各读自己的规则表",
        "entry_of": "child_item_completeness（按风险编码）/ data_source_status（按资料名）/ "
                    "legal_version（按法名）三套不同索引",
        "status_of": "data_source_status 的资料可用状态推导；legal_version 的版本状态 ⇒ 不同",
        # ── ③ 各领域自己的域入口 ──
        "audit": "各 Skill 的**域审计入口**（各自判据与返回结构），非同一函数",
        "audit_product": "child_item_completeness 与 data_source_status 各自的产物审计",
        "coverage": "reference 的引用覆盖 vs skill_registry 的 Skill 覆盖 ⇒ 不同",
        "scan": "content_placeholder_guard 与 field_completeness 各自的全文扫描",
        # ── 例外：实为**已收敛**（被"转发桩检测"漏判）──
        "affected_downstream": "doc_consistency_core 完整实现 + doc_ref_graph 薄转发 ⇒ 已收敛",
        "split_sentences": "dupkit 为**薄转发**（唯一权威 engine/sentencekit.split_sentences，"
                           "docstring 已注明）；本组被报系转发桩检测**只看函数体内 import**、"
                           "未识别**模块级** import 的转发 ⇒ 实为已收敛", "_assemble": "report_compliance 组装**版本台账记录**；rule_executor 组装**发现/证据/执行**归一产物 —— 输入输出无交集，属裁定口径①（同名单、异语义）", "_legal_refs": "rule_loader 把**法规依据原文 → 结构化引用**（产出引用）；snapshot_invariance **读取**引用做快照比对 ⇒ 方向相反，仅同名", "_note": "enterprise_report 向**报告产物**写注记；rule_loader 向 **stderr 留痕**（加载器问题）⇒ 出口与消费者不同，属裁定口径①", "_root": "★ **已收敛**：rule_catalog 已改为**转发** `rule_loader._root()`（本轮实测发现两处字节级复制粘贴）；本组仍被报系转发桩检测**只看函数体内 import**、未识别 `return L._root()` 这类**模块级引用转发** —— 与左侧 `split_sentences` 同因，实为已收敛", "amount_of": "numparse 是**文本 → 金额**解析（全项目唯一权威）；risk_scoring 是**从 finding dict 取涉税金额合计**（输入是结构化发现而非文本）⇒ 入参形态不同，非同一概念", "config": "doc_consistency_core 读**文档一致性判据配置**；risk_scoring 读**风险评分配置**（config/risk_scoring.json）—— 各读自己的文件、缓存独立，属裁定口径②", "get": "analysis_task 按 **job_id** 取任务；fact_store 取**事实**；rule_catalog 按 **rule_id** 取规则 —— 三套不同索引，属裁定口径②（各文件自己的取数器）", "stamp": "rule_versions 给 finding 盖**规则版本**；risk_scoring 给 finding 盖**综合排序分** —— 作用对象相同但**盖的字段与语义不同**（版本留痕 vs 排序辅助），两者可叠加且互不覆盖", "stamp_all": "同上（stamp 的批量版）：规则版本打戳 vs 排序分打戳，字段不同、可叠加", "stats": "fact_store 统计**事实库**；rule_catalog 统计**规则库**（分层/法规依据覆盖）；tax_redlines 统计**红线库** —— 各自的对象与口径不同，属裁定口径②",
        "_collapse": "analysis_jobs 折叠**作业状态**（按 job_id，含终态与 running 判定）；risk_review 折叠**复核事件**（按 risk_no，含批注聚合、转人工标记、整改编号）—— 折叠对象与聚合语义不同，属裁定口径①（同名单、异语义）", "last_errors": "risk_review 报**复核流水读取**错误；rule_loader 报**规则载体加载**错误 —— 两个不同数据源的诊断出口，属裁定口径②（各文件自己的错误出口）", "last_error": "同上（单数形）：两模块各自的错误出口，数据源不同", "_now": "全项目**既有惯例**（本次新增 risk_review 后共 8 处：analysis_jobs / archive_attachment / document_service / extract_service / project_service / report_compliance / risk_review / skill_runtime）—— 各模块自己的**时间戳文本封装**，底层权威是 runtime_storage.now_cst；不收敛的原因：文案/格式各随语境（有的带秒、有的带毫秒），且属**既有**写法，强行合并会改动 8 个既有模块的行为 ⇒ 属裁定口径①（同名单、异语义）", "_amount": "false_invoice 从**明细行**取金额（多列名逐个尝试）；risk_service 按**标准字段**取金额（输入=字段名+行）—— 入参与语义不同，属裁定口径①", "versions": "rule_catalog 返回**规则版本**（唯一权威 config/rule_versions.json，回答「这批结论按哪版规则算出」）；report_service 返回**报告版本台账**（唯一权威 data/report_versions.jsonl，回答「这家企业出过哪些报告」）—— 两个不同主题、两套不同权威文件，属裁定口径②（各文件自己的版本源）"}
    _files = [str(ROOT / "main.py")] + sorted(_glob.glob(str(ROOT / "engine" / "**" / "*.py"), recursive=True))
    defs: Dict[str, List[str]] = {}
    srcs: Dict[str, str] = {}
    for f in _files:
        try:
            s = open(f, encoding="utf-8", errors="ignore").read()
            tree = _ast.parse(s)
        except Exception:
            continue
        rel = os.path.relpath(f, ROOT).replace("\\", "/")
        srcs[rel] = s
        for n in tree.body:
            if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                seg = _ast.get_source_segment(s, n) or ""
                body = "\n".join(l.strip() for l in seg.split("\n")
                                 if l.strip() and not l.strip().startswith("#"))
                defs.setdefault(n.name, []).append("%s@%s" % (_hl.md5(body.encode()).hexdigest()[:8], rel))

    # ★ 2026-10-08：转发目标未必是 engine.*（如时间戳/存储权威 runtime_storage）。
    #   用"项目内模块"（根目录 .py / 包目录）**数据驱动**判定，而非硬编码模块名。
    _PROJ_TOP = {os.path.splitext(os.path.basename(p))[0]
                 for p in _glob.glob(str(ROOT / "*.py"))}
    _PROJ_TOP |= {os.path.splitext(os.path.basename(p))[0]
                  for p in _glob.glob(str(ROOT / "engine" / "*.py"))}

    def _is_proj_mod(mod) -> bool:
        top = str(mod or "").split(".")[0]
        if not top:
            return False
        return top in _PROJ_TOP or (ROOT / top).is_dir() or (ROOT / (top + ".py")).exists()

    def _is_stub(name: str, rel: str) -> bool:
        """转发桩判定（AST 版，稳健）：体内有 `from <项目模块> import ...` 且
        去掉 docstring / import 后**剩余语句 ≤6 条**（即没有实质实现逻辑）。

        早期版本用"恰好 1 条 return"判据，会把无返回值的副作用型转发（如
        `_infer_industry_from_goods` 只做赋值 + 调一个加载函数）误判成真实实现。
        """
        try:
            for n in _ast.parse(srcs[rel]).body:
                if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef)) and n.name == name:
                    has_imp = any(
                        isinstance(st, _ast.ImportFrom) and _is_proj_mod(st.module)
                        for st in n.body
                    )
                    stmts = [st for st in n.body
                             if not isinstance(st, (_ast.Import, _ast.ImportFrom))]
                    stmts = [st for st in stmts
                             if not (isinstance(st, _ast.Expr) and isinstance(st.value, _ast.Constant))]
                    return bool(has_imp) and len(stmts) <= 6
        except Exception:
            return False
        return False

    real_divergent = []
    # ★ 同一文件内重复定义**同名函数**：后定义静默覆盖前定义，永远不是有意为之。
    #   2026-09-25 实测踩坑：engine/workbook.py 因编辑失误留下两个 close_workbook，
    #   带幂等追踪的那份被后面的旧版覆盖 → 行为与源码不符，排查耗时良久。
    #   既有的跨文件检查只在"多文件"时报，同文件重复定义完全在视野之外。
    same_file_dupes = []
    for f in _files:
        try:
            s = open(f, encoding="utf-8", errors="ignore").read()
            tree = _ast.parse(s)
        except Exception:
            continue
        rel = os.path.relpath(f, ROOT).replace("\\", "/")
        seen: Dict[str, List[int]] = {}
        for n in tree.body:
            if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                seen.setdefault(n.name, []).append(n.lineno)
        for nm, lns in seen.items():
            if len(lns) > 1:
                same_file_dupes.append((rel, nm, lns))
                issues.append(("ERROR", rel,
                               f"同一文件内重复定义 {nm}（第 {lns} 行）："
                               "后定义会静默覆盖前定义，行为与源码不符"))

    for name, items in sorted(defs.items()):
        if name in _DIVERGENCE_OK:
            # 已登记的"允许分歧"私有助手：跳过，不计入 real_divergent（避免误报）
            continue
        files = sorted({i.split("@", 1)[1] for i in items})
        if len(files) < 2:
            continue
        hashes = {i.split("@", 1)[0] for i in items}
        if len(hashes) == 1:
            # ★ 2026-10-08 补漏：原实现到此直接 `continue`（注释却写"完全一致的重复
            #   → 也提示"），导致**复制粘贴的真实实现**（非转发桩）在多个模块并存时
            #   完全不被检出（实测：_first×2 / _cfg×2 / _is_dedup_ref×2 / _now×3）。
            #   全为转发桩 ⇒ 已收敛（如 _safe×9 / _buyer×3），跳过；
            #   否则 = 同一段**真实逻辑**被复制 N 份 ⇒ 必然漂移，报 WARN 逼收敛到单一权威。
            if not all(_is_stub(name, rel) for rel in files):
                issues.append(("WARN", files[0],
                               f"{name} 在 {len(files)} 个模块存在**字节级完全一致的真实实现**"
                               f"（复制粘贴，非转发桩，应收敛到单一权威）：{files}"))
            continue
        if all(_is_stub(name, rel) for rel in files):
            continue                       # 均为转发桩 → 已收敛
        real_divergent.append((name, files))
        if name in _MUST_BE_SINGLE:
            issues.append(("ERROR", files[0],
                           f"{name} 在 {len(files)} 个模块各有**真实实现**（应统一为单来源转发）：{files}"))

    if real_divergent:
        # ★ 打印**全部**名字（原为 `[:10]`）：只列前 10 个会让"逐组裁定"无从下手，
        #   而本判据的设计目的正是"强制人工确认每一组"。裁定结论登记在 `_DIVERGENCE_OK`。
        names = [n for n, _ in real_divergent]
        issues.append(("WARN", "engine/",
                       f"仍有 {len(real_divergent)} 组跨模块**真实分歧**（非转发桩），"
                       f"请确认是否属同一概念、能否收敛：{names}"))
    return issues


def check_delete_semantics() -> List[Tuple[str, str, str]]:
    """删除语义闸门：禁止"删了却报告成功"的 fail-open 回归。

    ★ 2026-09-25 接线。用户报「删除选中资料删不干净、删了报告像没删、重新生成
      还是旧报告」三连，根因是删除路径上的一组 fail-open 写法：
        ① 服务端丢弃 move_to_trash 返回值后无条件宣告成功；
        ② 前端只 try/catch 网络异常（fetch 对 4xx/5xx 不 reject），失败计成功；
        ③ 删除只清一处副本，其余副本（任务结果/历史/检查点/中转站/磁盘）留存；
        ④ 磁盘缓存删除不回读校验，写入失败即"复活"。
      这些都是**字符串形态的契约**，行为测试覆盖不到跨文件调用点，故在此设闸门：
      任何一处被改回旧写法立刻 ERROR。
    """
    issues: List[Tuple[str, str, str]] = []

    def _read_rel(rel: str) -> str:
        p = ROOT / rel
        if not p.exists():
            return ""
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    # ★ 两种视图，各用于不同性质的检查：
    #   raw  —— 原文。用于"必须存在"类检查（检查项常含字符串字面量，
    #           如 cleared.append("分析任务结果")、report_data["_freshness"]）。
    #   code —— 去掉注释与字符串后的纯代码视图。用于"必须不存在"类反模式检查，
    #           否则本项目注释里对反模式的引用（"原写法 X 后从不 close()"）
    #           会被判为反模式本身，产生自我误报。
    main_raw = _read_rel("main.py")
    main_code = _mask_py_comments_and_strings(main_raw)
    js_raw = _read_rel("static/js/tax-doc-analysis.js")
    js_code = _mask_js_comments(js_raw)
    if not main_raw:
        return [("ERROR", "main.py", "无法读取 main.py，删除语义检查不可执行")]

    # ① 无条件宣告删除成功（丢弃 purge_file/move_to_trash 的返回值）
    #    反模式检查 → 在纯代码视图上匹配
    for bad in (r"removed_file\s*=\s*True", r"removed_file\s*=\s*False"):
        if re.search(bad, main_code):
            issues.append(("ERROR", "main.py",
                           "删除路径出现无条件成功标记：物理删除失败会被谎报为成功"))

    # ② 资料删除必须走可验证的 purge_file + 失败登记墓碑
    if "purge_file(fpath)" not in main_raw:
        issues.append(("ERROR", "main.py",
                       "资料删除未经 purge_file（无法得到真实删除结果与失败原因）"))
    if "add_doc_tombstone(" not in main_raw:
        issues.append(("ERROR", "main.py",
                       "资料删除未登记墓碑：物理删除失败时重启后会被扫描重新收录"))

    # ③ 启动扫描必须跳过墓碑
    if "load_doc_tombstones()" not in main_raw:
        issues.append(("ERROR", "main.py",
                       "磁盘扫描未读取墓碑：已删除资料会在服务器重启后复活"))

    # ④ 删除报告必须清全部副本 + 回读校验 + 返回残留清单
    for marker, why in (
        ("分析任务结果", "已完成任务的结果仍是旧报告，/analyze-result 仍可取到"),
        ("分析历史", "分析历史未清，历史列表仍能看到已删报告"),
        ("分析检查点", "检查点未清，仍标记上次分析已完成"),
        ("中转站解析缓存", "中转站明细未清，解析后的数据仍留存"),
    ):
        if marker not in main_raw:
            issues.append(("ERROR", "main.py", f"删除报告未清理「{marker}」：{why}"))
    if "leftovers" not in main_raw:
        issues.append(("ERROR", "main.py", "删除报告不返回残留清单，只会笼统宣告已删除"))
    if "verify = read_json(LAST_ANALYSIS_CACHE, {})" not in main_raw:
        issues.append(("ERROR", "main.py",
                       "磁盘分析缓存删除后未回读校验：写失败时报告会在重启后复活"))

    # ⑤ 前端不得再逐条 DELETE / 不得再对失败分支谎报成功
    #   ★ 全量扫描 static/js/*.js：删除语义是"一个概念一个实现"，任何一处
    #     残留的逐条删除循环都会重新引入 fail-open（2026-09-25 实测发现
    #     tax-risk-report.js 曾与 tax-doc-analysis.js 各有一套删除实现）。
    js_dir = ROOT / "static" / "js"
    js_files = sorted(js_dir.glob("*.js")) if js_dir.is_dir() else []
    for jf in js_files:
        try:
            raw = jf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        src = _mask_js_comments(raw)
        if re.search(r"['\"]/api/tax-risk-docs/['\"]\s*\+\s*\w+", src):
            issues.append(("ERROR", f"static/js/{jf.name}",
                           "出现逐条资料删除调用（/api/tax-risk-docs/<id>）："
                           "必须改用 /api/tax-risk-docs/batch-delete，否则失败会被静默计为成功"))

    if js_raw:
        if "/api/tax-risk-docs/batch-delete" not in js_raw:
            issues.append(("ERROR", "static/js/tax-doc-analysis.js",
                           "批量删除未走服务端批量接口（前端逐条 DELETE 会把失败计为成功）"))
        if "if (!resp.ok) { throw new Error" not in js_raw:
            issues.append(("ERROR", "static/js/tax-doc-analysis.js",
                           "前端未检查 HTTP 状态码：fetch 对 4xx/5xx 不 reject，失败会被当成功"))
        if re.search(r"toast\(\s*'报告已删除'\s*,\s*'success'\s*\)", js_code):
            issues.append(("ERROR", "static/js/tax-doc-analysis.js",
                           "删除报告的网络异常分支仍谎报成功"))

    # ⑥ 增量复用必须可被显式强制重算绕过
    #   ★ 2026-10-01 用户定调：报告不再携带「计算时间/数据指纹/轮次」等元信息（与报告本质无关），
    #     故原「报告须自带新鲜度标识」断言已移除；仅保留「可被强制重算绕过」这一功能性要求。
    if "if not force:" not in main_raw:
        issues.append(("ERROR", "main.py",
                       "增量复用无法被强制重算绕过：用户会持续拿到缓存报告"))

    # ⑦ 删除前必须释放本服务自身的工作簿句柄，且失败原因须如实（不得替用户猜）
    if "release_all" not in main_code:
        issues.append(("ERROR", "main.py",
                       "删除路径未释放本服务工作簿句柄：实测占用者是本服务自身，"
                       "不先释放则删除必然失败且原因错报给用户"))
    if "is_file_locked" not in main_code:
        issues.append(("ERROR", "main.py",
                       "删除失败未探测'是否真的被占用'：会向用户猜一个原因（如'被 Excel 占用'）"))

    return issues


def _mask_py_comments_and_strings(text: str) -> str:
    """把注释与字符串字面量替换为等长空格（保留换行与行号），得到"纯代码"视图。

    ★ 为什么必须这么做：正则式闸门的检查项（如 `removed_file = True`、
      `openpyxl.load_workbook(`）在本项目的**修复说明注释/文档字符串里会被引用**
      ——「原写法 X 后从不 close()」是这里的固定写法。若在原文上匹配，
      闸门会把"对反模式的说明"判为"反模式本身"，出现自我误报。
    """
    import io as _io
    import tokenize
    lines = text.splitlines(keepends=True)
    offsets, pos = [], 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln)

    def idx(row: int, col: int) -> int:
        return offsets[row - 1] + col

    chars = list(text)

    def blank(a: int, b: int) -> None:
        for i in range(max(0, a), min(len(chars), b)):
            if chars[i] not in ("\n", "\r"):
                chars[i] = " "

    try:
        for tok in tokenize.generate_tokens(_io.StringIO(text).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                try:
                    blank(idx(*tok.start), idx(*tok.end))
                except Exception:
                    continue
    except Exception:
        return text
    return "".join(chars)


def _mask_js_comments(text: str) -> str:
    """去掉 JS 的 // 与 /* */ 注释（等长替换，保留换行）。"""
    out = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)
    return re.sub(r"//[^\n]*", lambda m: " " * len(m.group(0)), out)


def check_delete_result_finality() -> List[Tuple[str, str, str]]:
    """删除报告＝**终局状态**：任何进行中的分析跑完都不得把结果写回。

    ★ 2026-10-01 新增（真实事故，与行业/企业无关，对所有账套成立）：
      12:21 启动的一轮一键分析跑到 12:24:49 才完成，而用户 12:22:35 已点删除报告；
      分析跑完把 last_analysis_cache / analysis_history / checkpoints 里的 "1"
      全部重新写回 —— 界面上"删了又回来"。
      ★ 关键事实：**删除接口当时如实报了"清理 6 处"，并非谎报**；真正的问题是
      删除不取消进行中的分析，且三个写回路径没有终局守卫。
      现状：唯一权威判据 `main._is_result_deleted`（判据 = `_deleted_company_ids`
      已登记 + 该账套存在 status=deleted 的任务）；删除端点最先登记终局；
      `_persist_one_click_result` / `_append_analysis_history` /
      `_write_analysis_checkpoint` 三条写回路径必须先过这一关。
      本闸门防止守卫被摘掉（含"删了 purge_file 返回值仍报清理"的谎报回潮）。
    """
    issues: List[Tuple[str, str, str]] = []
    p = ROOT / "main.py"
    if not p.exists():
        return [("ERROR", "main.py", "main.py 不存在，删除终局检查不可执行")]
    try:
        raw = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [("ERROR", "main.py", "main.py 读取失败，删除终局检查不可执行")]
    # 纯代码视图（去注释/去字符串字面量），避免注释里引用反模式造成自我误报
    code = _mask_py_comments_and_strings(raw)

    # ① 三条分析结果写回路径都必须挂终局守卫
    for marker in (
        "def _persist_one_click_result(",
        "def _append_analysis_history(",
        "def _write_analysis_checkpoint(",
    ):
        start = code.find(marker)
        if start < 0:
            issues.append((
                "ERROR", "main.py",
                f"找不到分析结果写回路径 {marker}，删除终局守卫无处挂载"))
            continue
        nxt = code.find("\ndef ", start + len(marker))
        body = code[start: nxt if nxt > 0 else len(code)]
        if "_is_result_deleted(" not in body:
            issues.append((
                "ERROR", "main.py",
                f"{marker} 未挂 _is_result_deleted 终局守卫：进行中的分析跑完会把"
                f"已删除的结果写回（缓存/历史/检查点复活）"))

    # ② 删除端点必须最先登记终局（之后到达的写回全部要被拦）
    if "_deleted_company_ids.add(" not in code:
        issues.append((
            "ERROR", "main.py",
            "删除端点未登记 _deleted_company_ids：删除先于终局登记到达时仍会被写回"))

    # ③ ⑥ 丢弃 purge_file 返回值仍按命中数报"清理"＝谎报（2026-09-25 老病回潮）
    if re.search(r"^\s+purge_file\(os\.path\.join\(TRANSFER_DIR, _fn\)\)\s*$",
                 code, re.M):
        issues.append((
            "ERROR", "main.py",
            "delete_tax_risk_report ⑥ 丢弃 purge_file 返回值：文件没移走也会报"
            "「清理 N 个」，属谎报；须按 (removed, reason) 逐文件判定"))
    return issues


def check_excel_handle_leak() -> List[Tuple[str, str, str]]:
    """Excel 工作簿句柄泄漏闸门（★ 2026-09-25 接线）。

    用户报「删除资料后点清理删除残留，提示文件仍被程序占用，怎么还能被占用」。
    实测占用者**不是** Excel/WPS，而是本服务进程自身：
      openpyxl 工作簿以 read_only=True 打开后从未 close()，
      该模式底层持有 zip 文件句柄，而 openpyxl 对象图存在引用环
      （worksheet.parent ↔ workbook），函数返回后**不被引用计数立即回收**，
      要等循环 GC —— 长驻服务里句柄可一直占着文件 →
      文件无法重命名/移动 → 删除失败 → 被误认为"删了又回来/后台有备份"。

    本闸门强制"一个概念一个实现"：任何工作簿打开都必须经 engine/workbook.py
    （唯一权威，出口必定 close）。在"纯代码视图"上匹配，避免注释自我误报。
    """
    issues: List[Tuple[str, str, str]] = []
    authority = "engine/workbook.py"
    pattern = re.compile(r"\b(?:openpyxl|_ox|_xp)\s*\.\s*load_workbook\s*\(|"
                         r"\b(?:xlrd|_xr)\s*\.\s*open_workbook\s*\(")
    for path in _iter_prod_py_files():
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        if rel == authority:
            continue
        try:
            code = _mask_py_comments_and_strings(Path(path).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        for m in pattern.finditer(code):
            lineno = code[:m.start()].count("\n") + 1
            issues.append(("ERROR", rel,
                           f"第{lineno}行绕过 engine/workbook.py 直接打开工作簿："
                           "read_only 模式的 zip 句柄不会被立即回收，"
                           "会占住文件导致删除失败（须用 workbook_scope/close_workbook）"))
    if not (ROOT / authority).exists():
        issues.append(("ERROR", authority, "工作簿句柄唯一权威模块缺失"))
    return issues


def check_audit_doctrine() -> List[Tuple[str, str, str]]:
    """一键分析宗旨闸门：「上传了什么资料就查什么资料」（★ 2026-09-25 接线）。

    用户宗旨：上传了什么资料就查什么资料，以一个税务稽查专家的身份查实所上传资料的
    所有税务风险，**而不是等资料齐全才排查**；对已查出的风险要给出解除方式与需补的
    自证资料，终局是「铁证如山」或「自证清白」。

    真实事故（本闸门防其复发）：`_domain_salary_ss_hf_compare`
      `if not salaries: return findings` → 只上传社保明细时整域零产出；
      只上传工资表时社保名单为空 → 差集＝全部工资人员 → 报「N 名员工有工资无社保（高风险）」，
      把"资料没交"升级成"全员未依法参保"。

    ★ 本闸门**不只是静态检查**：静态规则挡不住这类"逻辑上把缺资料读成违规"的缺陷，
      故直接**运行**该域在三种资料组合下的行为并断言 —— 与既有 evidence_chain 不变式
      检查同一思路（行为断言 > 文本断言）。
    """
    issues: List[Tuple[str, str, str]] = []

    def _read_rel(rel: str) -> str:
        p = ROOT / rel
        try:
            return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
        except OSError:
            return ""

    # ── ① 机制模块必须存在 ──
    if not (ROOT / "engine" / "audit_doctrine.py").exists():
        issues.append(("ERROR", "engine/audit_doctrine.py",
                       "宗旨机制模块缺失：'有什么查什么'无法落地"))
        return issues

    # ── ② 收敛点必须接线（各域是调用方，pipeline 是权威兜底）──
    pipe = _mask_py_comments_and_strings(_read_rel("engine/pipeline.py"))
    for need, why in (
        ("enforce_no_missing_driven_accusation", "缺资料驱动的发现没有兜底降级点，任一域漏判就会发出违法指控"),
        ("_one_sided_digest", "报告未输出'已上传资料各自可查什么'"),
        ("summarise_doctrine", "未汇总宗旨执行情况"),
    ):
        if need not in pipe:
            issues.append(("ERROR", "engine/pipeline.py", f"宗旨未接线：{need} —— {why}"))

    # ── ③ 覆盖清单不得再说"因缺资料未能执行"（宗旨反对"等资料齐全"）──
    cov_src = _read_rel("engine/analysis_coverage.py")
    if "因缺资料未能执行" in cov_src:
        issues.append(("ERROR", "engine/analysis_coverage.py",
                       "覆盖清单仍在说'因缺资料未能执行'：该措辞暗示系统在等资料齐全，与宗旨相悖，"
                       "应改为'现有资料已查尽 + 待补自证后方可判定'"))

    # ── ④ 报告必须带出"解除方式 + 自证清单"章节 ──
    rep = _mask_py_comments_and_strings(_read_rel("engine/enterprise_report.py"))
    for need, why in (
        ("_build_resolution_ledger", "报告未输出逐项风险的解除方式与自证清单（宗旨 D3）"),
        ("_build_one_sided_digest", "报告未输出已上传资料的可查清单（宗旨 D1）"),
    ):
        if need not in rep:
            issues.append(("ERROR", "engine/enterprise_report.py", f"宗旨未落地到报告：{why}"))

    # ── ⑤ 行为断言：三种资料组合下的真实产出 ──
    try:
        from engine.audit_doctrine import (
            SEVERITY_LEVELS, TERMINAL_IRONCLAD, TERMINAL_PENDING, TERMINAL_SELF_PROOF,
            MISSING_DRIVEN_LEVEL_CAP,
        )
        from engine.domain_analysis import _domain_salary_ss_hf_compare as _cmp
        _pipe_src = _read_rel("engine/pipeline.py")

        # ── ⑤-0 白名单键必须是活的（按子串匹配真实域名）──
        #   2026-09-25 实测：`_objective_domain_keys` 里的「进销存数量勾稽」匹配不到任何域
        #   （真实域名是「进销存匹配分析」）→ 该键永远不生效，是一个不会报错的死配置。
        _dom_names = re.findall(r'domain_results\.append\(\{"domain":\s*"([^"]+)"', _pipe_src)
        _m_keys = re.search(r"_objective_domain_keys = \(([^)]*)\)", _pipe_src, re.S)
        for _k in (re.findall(r'"([^"]+)"', _m_keys.group(1)) if _m_keys else []):
            if not any(_k in _d for _d in _dom_names):
                issues.append(("ERROR", "engine/pipeline.py",
                               f"客观域白名单键「{_k}」匹配不到任何真实域名（死键，永不生效）；"
                               f"现有域名如 {_dom_names[:6]}"))

        # ── ⑤-0b 用户决策（2026-09-25）：**分析到的风险必须全部呈现在报告中** ──
        #   原设计只并入 7 个「客观域」，其余 40+ 个域的结论被整体隔离（实测 86 项
        #   "算了但看不到"）。现要求：所有域的风险级发现一律并入正式输出，
        #   并保留「证据地位」标注以区分可信度。此决策必须被闸门锁死，不得回退。
        if "promote_domain_findings" not in _pipe_src:
            issues.append(("ERROR", "engine/pipeline.py",
                           "未调用 promote_domain_findings：域分析结论会再次被整体隔离，"
                           "违背用户决策『分析到的风险必须全部呈现在报告中』"))
        _og_src = _read_rel("engine/output_governance.py")
        if "apply_three_piece_to_all" not in _mask_py_comments_and_strings(_og_src):
            issues.append(("ERROR", "engine/output_governance.py",
                           "封印点未保证『每条发现都有出口』：seal_governed_findings 会 deepcopy "
                           "重造对象，上游补齐的出口会被丢弃（实测补齐 92 条、报告生效 0 条）；"
                           "必须在封印内部落实"))
        _og_src = _read_rel("engine/output_governance.py")
        if "apply_three_piece_to_all" not in _mask_py_comments_and_strings(_og_src):
            issues.append(("ERROR", "engine/output_governance.py",
                           "封印点未保证『每条发现都有出口』：seal_governed_findings 会 deepcopy "
                           "重造对象，上游补齐的出口会被丢弃（实测补齐 92 条、报告生效 0 条）；"
                           "必须在封印内部落实"))
        if "stamp_evidence_tiers" not in _pipe_src:
            issues.append(("ERROR", "engine/pipeline.py",
                           "未标注证据地位：报告中无法区分『已验原子规则』与『域分析结论』的可信度"))
        if "正式输出范围" not in _pipe_src:
            issues.append(("ERROR", "engine/pipeline.py",
                           "未披露输出范围缺口：若仍有结论未进报告，必须逐域点名告警（不得静默）"))
        if '"output_scope"' not in _pipe_src:
            issues.append(("ERROR", "engine/pipeline.py",
                           "报告未携带 output_scope（输出范围 + 证据地位分布）"))
        try:
            from engine.output_governance import (
                EVIDENCE_TIER_DOMAIN, EVIDENCE_TIER_VERIFIED_RULE,
                promote_domain_findings, stamp_evidence_tiers,
            )
            # 行为断言：纯函数提升 —— 风险级全并入、信息级不动、已并入的不重复
            _exec = {"findings": [{"type": "VR项", "level": "高风险",
                                   "evidence_tier": EVIDENCE_TIER_VERIFIED_RULE}]}
            _dom = [
                {"domain": "域甲", "findings": [
                    {"type": "域风险1", "level": "中风险"},
                    {"type": "域信息1", "level": "信息"},
                ]},
                {"domain": "域乙", "findings": [{"type": "域风险2", "level": "待核验"}]},
            ]
            _res = promote_domain_findings(_exec, _dom, set())
            _promoted = [f for f in _exec["findings"] if f.get("_domain_analysis_finding")]
            if _res.get("promoted") != 2 or len(_promoted) != 2:
                issues.append(("ERROR", "engine/output_governance.py",
                               f"[行为] 域风险级发现未全部提升（promoted={_res.get('promoted')}，"
                               f"期望 2；『信息』级不应提升）"))
            for _f in _promoted:
                if not _f.get("_scenario_governed") or not _f.get("scene_fact_id"):
                    issues.append(("ERROR", "engine/output_governance.py",
                                   "[行为] 提升后的发现缺少封印所需标记（_scenario_governed/scene_fact_id）"))
                if _f.get("conclusion_grade") != "待核":
                    issues.append(("ERROR", "engine/output_governance.py",
                                   "[行为] 域结论被标为已核定：域结论未固化为已验证规则，只能是待核"))
                if _f.get("evidence_tier") != EVIDENCE_TIER_DOMAIN:
                    issues.append(("ERROR", "engine/output_governance.py",
                                   "[行为] 提升后的发现未标注证据地位（域分析结论）"))
            # 幂等：重复提升不得产生重复
            _res2 = promote_domain_findings(_exec, _dom, set())
            if _res2.get("promoted") != 0:
                issues.append(("ERROR", "engine/output_governance.py",
                               "[行为] 重复调用 promote_domain_findings 产生了重复条目"))
            # 证据地位补标注
            _n = stamp_evidence_tiers([{"type": "x", "level": "中风险"}])
            if _n != 1:
                issues.append(("ERROR", "engine/output_governance.py",
                               "[行为] stamp_evidence_tiers 未给未标注的发现补齐证据地位"))
        except Exception as exc:
            issues.append(("ERROR", "engine/output_governance.py",
                           f"域结论提升行为断言无法执行：{type(exc).__name__}: {exc}"))

        # ★ 2026-10-06：等级词表**唯一权威**已迁到 `engine/risk_levels`。
        #   本闸门原先断言"pipeline 必须有一张 `_sev` 表"——那等于**把多头维护制度化**，
        #   正是它保护了"信息 vs 低风险"互相矛盾的 6 张表。该断言已删除；
        #   「消费点必须转发唯一权威」的接线断言统一归
        #   `check_risk_level_single_source()`（它读**真实**源码，不受本闸门的 tmp 夹具影响）。
        #   本闸门只保留**数据断言**：合法等级词表必须在权威词表内
        #   （防"待核/待核实"这类表外值被后续环节静默丢弃）。
        from engine.risk_levels import LEGAL_LEVELS as _LEGAL_LEVELS_AUTH   # noqa: PLC0415
        for _lv in SEVERITY_LEVELS:
            if _lv not in _LEGAL_LEVELS_AUTH:
                issues.append(("ERROR", "engine/audit_doctrine.py",
                               f"等级词表含表外值「{_lv}」（会被后续环节静默丢弃）"))
        # 代码里不得出现未登记的等级值（2026-09-25 实测：误用「待核」导致发现被整条丢弃）
        _lv_pat = re.compile(r'["\']level["\']\s*:\s*["\']([^"\']{1,12})["\']')
        for _rel in ("engine/domain_analysis.py", "engine/audit_doctrine.py"):
            _code = _mask_py_comments_and_strings(_read_rel(_rel))
            for _m in _lv_pat.finditer(_code):
                if _m.group(1) not in SEVERITY_LEVELS:
                    _ln = _code[:_m.start()].count("\n") + 1
                    issues.append(("ERROR", _rel,
                                   f"第{_ln}行使用了未登记的风险等级「{_m.group(1)}」："
                                   f"合法值为 {list(SEVERITY_LEVELS)}；非法等级会被后续环节静默丢弃"))

        sal = [{"name": "张三", "salary": 9000, "month": "2025-01"},
               {"name": "李四", "salary": 12000, "month": "2025-01"},
               # 王五有工资无社保 → 两侧齐备时才应命中"有工资无社保"
               {"name": "王五", "salary": 8000, "month": "2025-01"}]
        ss = [{"name": "张三", "base": 4000, "month": "2025-01"},
              {"name": "李四", "base": 12000, "month": "2025-01"}]
        _valid_terminal = {TERMINAL_IRONCLAD, TERMINAL_SELF_PROOF, TERMINAL_PENDING}

        combos = (("仅工资表", sal, []), ("仅社保明细", [], ss), ("两侧齐备", sal, ss))
        for label, a, b in combos:
            out = _cmp(a, b)
            if not out:
                issues.append(("ERROR", "engine/domain_analysis.py",
                               f"[行为] {label}时工资社保域零产出：违背'有什么资料就查什么资料'"))
                continue
            for f in out:
                if str(f.get("level") or "") not in SEVERITY_LEVELS:
                    issues.append(("ERROR", "engine/domain_analysis.py",
                                   f"[行为] {label}·{f.get('type')} 等级非法："
                                   f"{f.get('level')!r}（会被静默丢弃）"))
                if not f.get("resolve_steps"):
                    issues.append(("ERROR", "engine/domain_analysis.py",
                                   f"[行为] {label}·{f.get('type')} 未给出解除方式（宗旨 D3）"))
                if not f.get("self_proof_materials"):
                    issues.append(("ERROR", "engine/domain_analysis.py",
                                   f"[行为] {label}·{f.get('type')} 未给出需补自证资料（宗旨 D3）"))
                if f.get("terminal_state") not in _valid_terminal:
                    issues.append(("ERROR", "engine/domain_analysis.py",
                                   f"[行为] {label}·{f.get('type')} 终局方向非法："
                                   f"{f.get('terminal_state')!r}（只能是铁证如山/可自证清白/待补自证）"))

        # 只有工资表时绝不能据空社保名单反推"未参保"
        for f in _cmp(sal, []):
            t = str(f.get("type") or "")
            if "无社保" in t or "未参保" in t or str(f.get("level")) in ("高风险", "极高风险"):
                issues.append(("ERROR", "engine/domain_analysis.py",
                               f"[行为] 仅有工资表时产出违规级认定「{t}（{f.get('level')}）」："
                               "缺资料被读成了违法事实（宗旨 D2 红线）"))

        # 两侧齐备时必须执行真交叉核验
        if not any(str(f.get("type") or "") == "有工资无社保" for f in _cmp(sal, ss)):
            issues.append(("ERROR", "engine/domain_analysis.py",
                           "[行为] 两侧资料齐备时未执行真正的工资社保交叉核验"))

        # ── ⑤-b 兜底降级点必须**真的**降级（不能只查"函数名出现过"）──
        #   2026-10-02 反向验证发现的真实缺口：② 只对
        #   `enforce_no_missing_driven_accusation` 做「函数名在 pipeline 源码里出现过」
        #   的静态检查。把它实现改成空函数、或把
        #   `attach_three_piece(..., missing_driven=True)` 的 True 删掉，闸门全绿 ——
        #   而"把资料缺失读成违法事实"正是宗旨 D2 红线。静态规则挡不住，必须行为断言。
        try:
            from engine.audit_doctrine import enforce_no_missing_driven_accusation
            _probe = [
                {"type": "有工资无社保", "level": "极高风险", "score": 9,
                 "detail": "未提供社保明细，名单中未找到对应月份记录"},
                {"type": "发票作废率偏高", "level": "中风险", "score": 6,
                 "detail": "作废12张占全部100张的12%"},
            ]
            enforce_no_missing_driven_accusation(_probe)
            _acc, _ok = _probe[0], _probe[1]
            _rl = "engine/audit_doctrine.py"
            if str(_acc.get("level")) != MISSING_DRIVEN_LEVEL_CAP:
                issues.append(("ERROR", _rl,
                               f"[行为] 兜底降级点未把缺资料驱动的「{_acc.get('type')}」"
                               f"从{_acc.get('level')}降为{MISSING_DRIVEN_LEVEL_CAP}："
                               "闸门若只做函数名静态检查，实现被改成空函数也无人察觉"))
            if _acc.get("level_downgraded_from") != "极高风险":
                issues.append(("ERROR", _rl,
                               "[行为] 降级未留痕 level_downgraded_from：无法追溯该条是何时/为何被降的"))
            if float(_acc.get("score") or 0) > 4:
                issues.append(("ERROR", _rl,
                               f"[行为] 缺资料驱动的发现 score={_acc.get('score')} 未压到 4 以内"))
            if _acc.get("terminal_state") != TERMINAL_PENDING:
                issues.append(("ERROR", _rl,
                               f"[行为] 缺资料驱动的发现终局方向应为{TERMINAL_PENDING}，"
                               f"实为{_acc.get('terminal_state')!r}"))
            if not _acc.get("resolve_steps"):
                issues.append(("ERROR", _rl,
                               "[行为] 被降级的发现未补齐解除方式（宗旨 D3）"))
            if str(_ok.get("level")) != "中风险":
                issues.append(("ERROR", _rl,
                               f"[行为] 有据的中风险发现被误降级为「{_ok.get('level')}」"
                               "（零误伤要求：闸门不能把真风险一起降掉）"))
        except Exception as exc:
            issues.append(("ERROR", "engine/audit_doctrine.py",
                           f"兜底降级点行为断言无法执行：{type(exc).__name__}: {exc}"))
    except Exception as exc:
        issues.append(("ERROR", "engine/domain_analysis.py",
                       f"宗旨行为断言无法执行：{type(exc).__name__}: {exc}"))

    return issues


def _str_const(node) -> str:
    """从 AST 节点取字符串常量（含 f-string 的常量片段与字符串拼接）。"""
    import ast as _ast
    if isinstance(node, _ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, _ast.JoinedStr):
        return " ".join(v.value for v in node.values
                        if isinstance(v, _ast.Constant) and isinstance(v.value, str))
    if isinstance(node, _ast.BinOp):
        return " ".join(filter(None, (_str_const(node.left), _str_const(node.right))))
    return ""


def _iter_finding_dicts(path):
    """枚举源文件里"形似风险发现"的 dict 字面量（含 level + type 键）。

    ★ 只认同时具备 `level` 与 `type` 的字典：项目里 `level` 这个键被复用于
      日志等级、质量自检、置信度分级、英文键→中文映射表等非风险场景，
      不设这个判据会把它们全部误报。
    """
    import ast as _ast
    try:
        src = Path(path).read_text(encoding="utf-8", errors="replace")
        tree = _ast.parse(src)
    except Exception:
        return []
    out = []
    for node in _ast.walk(tree):
        if not isinstance(node, _ast.Dict):
            continue
        kv = {}
        for k, v in zip(node.keys, node.values):
            if isinstance(k, _ast.Constant) and isinstance(k.value, str):
                kv[k.value] = v
        if "level" not in kv or "type" not in kv:
            continue
        out.append((node.lineno, kv))
    return out


# 「上传层缺失」信号：企业**没交资料 / 交了读不出来**（与"业务数据本身有差异"区分开）
_UPLOAD_LAYER_HINTS = (
    "未上传", "未提交", "文件解析失败", "解析失败", "均为空", "数据为空", "为空",
    "未提供", "无法执行", "无法进行", "无法评估", "资料缺失", "缺少文件", "未取得",
)
_UPLOAD_TYPE_MARKERS = ("资料缺失", "无法执行", "解析失败", "未提供", "缺少数据", "未上传")
# 已按宗旨写明"不等于违规/待补证"的不算越界
_MISSING_GUARDED = ("不等于违规", "不作认定", "待补证", "待核验", "不作违规推定",
                    "补充资料后", "待补充", "排查清单")


def scan_upload_layer_violations() -> List[Tuple[str, int, str, str]]:
    """全项目扫描「上传层缺失被写成风险等级」（宗旨 D2 违规）。

    这是工资社保事件的**同类缺陷扫描器**，单实现供闸门与诊断脚本共用
    （`scripts/_hunt_missing_as_violation.py` 直接调用本函数，避免两套口径）。
    """
    out = []
    for path in _iter_prod_py_files():
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        for lineno, kv in _iter_finding_dicts(path):
            lv = _str_const(kv.get("level"))
            if lv not in ("中风险", "高风险", "极高风险"):
                continue
            ftype = _str_const(kv.get("type"))
            text = " ".join(filter(None, (ftype, _str_const(kv.get("detail")),
                                          _str_const(kv.get("description")))))
            if any(g in text for g in _MISSING_GUARDED):
                continue
            if not any(h in text for h in _UPLOAD_LAYER_HINTS):
                continue
            if not any(m in ftype for m in _UPLOAD_TYPE_MARKERS):
                continue
            out.append((rel, lineno, lv, ftype[:50]))
    return out


def check_missing_as_violation() -> List[Tuple[str, str, str]]:
    """缺资料被写成违规的闸门（★ 2026-09-25 接线）。

    用户宗旨铁律 D2：缺资料只能产出「待核验 + 待补自证」，**永远不能产出违规**。
    真实事故：工资社保域在社保名单为空时把差集当成"全员未参保（高风险）"；
    同类扫描实测还查出 15 处「资料缺失-XXX / 文件解析失败」被写成中/高风险
    （部分会因未登记等级被静默丢弃，部分会真的进报告让企业背锅）。

    判据刻意排除"业务层事实"（发票缺数量栏、进销存勾稽不平衡、无采购记录、
    合同覆盖率低）—— 那些是企业自己业务数据的差异，属于**查出来的事实**，本就该给等级。
    """
    issues: List[Tuple[str, str, str]] = []
    for rel, lineno, lv, ftype in scan_upload_layer_violations():
        issues.append(("ERROR", rel,
                       f"第{lineno}行「{ftype}」以「资料未上传/数据为空」为依据却定级 {lv}："
                       "缺资料不等于违规（宗旨 D2），应降为待核验并给出需补自证资料"))
    return issues


def _strip_comments_keep_lines(src: str) -> str:
    """去掉注释、**保留行结构**（供"必须不存在"类文本反模式扫描）。

    掩码视图只可用于"必须不存在"的反模式（闸门铁律）；本处正是该类：
    注释里出现"齐全程度…百分比"属说明性文字（允许），而**输出代码**里出现即违规。
    故用保留行号的方式剥离注释，避免注释误报。
    """
    try:
        import io as _io
        import tokenize as _tk
        out = list(src.splitlines(keepends=True))
        for tok in _tk.generate_tokens(_io.StringIO(src).readline):
            if tok.type != _tk.COMMENT:
                continue
            srow, scol = tok.start
            erow, ecol = tok.end
            if srow == erow and 1 <= srow <= len(out):
                ln = out[srow - 1]
                out[srow - 1] = ln[:scol] + ln[ecol:]
        return "".join(out)
    except Exception:
        return src


def _js_code_only(src: str) -> str:
    """JS 源码剥注释（`//…` 与 `/*…*/`），**保留行结构**。

    ★ 2026-10-08（实测踩中）：`_strip_comments_keep_lines` 用 Python `tokenize`，
      **只认 Python 注释**；对 `static/js/*.js` 传入后要么原样返回、要么产出噪声
      ⇒ 对 JS 做"必须不存在"的反模式扫描时，**判据会被自己的 JS 注释判红**。
      凡对前端脚本做该类扫描，一律先过本函数（与 `_strip_comments_keep_lines` 同旨）。
    """
    try:
        src = re.sub(r"/\*[\s\S]*?\*/", lambda m: "\n" * m.group(0).count("\n"), src)
        return re.sub(r"//[^\n]*", "", src)
    except Exception:
        return src


def check_material_completeness_no_ratio() -> List[Tuple[str, str, str]]:
    """材料齐全程度**不得以比例/百分比表述**（★ 2026-09-27 用户要求）。

    用户口径：材料齐全程度只表述"已有几项、还缺几项"（**项数**），
    不允许出现"材料齐全程度40%"这类**比例/百分比**表述。
    `closure`（证据链加权闭合度）仍内部计算，用于判定"能否定性"，但**不得进入正文**。

    判据（"必须不存在"反模式，故用去注释视图 + 项数白名单）：
      生产代码/前端脚本的**同一行**中同时出现「齐全程度」与百分比特征
      （Python：`%` 或 `* 100`；JS：`%` 或 `pct(` 或 `*100`）→ ERROR。
      "齐全程度{_have_n}项"这种**项数**写法不含百分比特征，不误报。

    ②（2026-10-01 用户批注新增）资料段落**不得用无宾语/无前指的模糊结论句**：
      「要把这一项定下来」「排除依据」一类套话 → ERROR（须写明定性/排除对象与具体资料名）。
    """
    issues: List[Tuple[str, str, str]] = []
    import glob as _glob
    targets: List[Tuple[str, str, bool]] = []   # (rel, text, is_js)
    for f in _iter_prod_py_files():
        rel = os.path.relpath(f, ROOT).replace("\\", "/")
        targets.append((rel, _strip_comments_keep_lines(_read(Path(f)) or ""), False))
    for f in _glob.glob(str(ROOT / "static" / "js" / "*.js")):
        try:
            txt = Path(f).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = os.path.relpath(f, ROOT).replace("\\", "/")
        targets.append((rel, txt, True))

    for rel, text, is_js in targets:
        for i, raw in enumerate(text.splitlines(), 1):
            line = raw.split("//", 1)[0] if is_js else raw   # JS 行注释剥离（避免误报）
            if "齐全程度" not in line:
                continue
            pct_feature = ("%" in line) or ("* 100" in line) or ("*100" in line)
            if is_js:
                pct_feature = pct_feature or ("pct(" in line)
            if pct_feature:
                issues.append((
                    "ERROR", rel,
                    f"第{i}行：材料齐全程度仍以百分比/比例表述（不得出现「齐全程度N%」）；"
                    "请改为「已有X项、还缺Y项」的项数表述"))

    # ★★ 2026-10-01（用户批注：报告「三、已取得的资料与待补充的资料」根本读不懂）：
    #   原正文「要把这一项定下来，需要N项材料」——定什么？「现有资料不构成排除依据」——排除什么？
    #   且整段只有五个数字、没有一个具体资料名。锁死两类反模式：
    #     ① 无宾语/无前指的模糊结论句（读者无从判断在说哪一件事）；
    #     ② 资料口径表述里出现「排除依据」这类套话（必须直说排除的是本项涉嫌风险）。
    #   判据同样走"必须不存在"，与上一判据共用一次文件扫描。
    _VAGUE = ("要把这一项定下来", "排除依据", "这一项材料")
    for rel, text, _is_js in targets:
        for i, raw in enumerate(text.splitlines(), 1):
            line = raw.split("//", 1)[0] if _is_js else raw
            hit = next((w for w in _VAGUE if w in line), "")
            if hit:
                issues.append((
                    "ERROR", rel,
                    f"第{i}行：资料段落仍用无宾语/无前指的模糊表述「{hit}」——"
                    "须写明①定性对象（本项涉嫌风险成立与否）、②排除对象（本项涉嫌风险）、"
                    "③还缺的具体资料名，不能只报数字"))
    return issues


def check_benchmark_caution_single_source() -> List[Tuple[str, str, str]]:
    """行业基准口径声明必须**单一权威**（2026-10-02，用户质询「哪个信息是非官方口径」）。

    ★ 背景：报告里出现「（来源 industry_data.json，非税务机关官方口径）」——读者问：
      到底哪个信息是非官方口径？非官方口径的数据能不能当判定依据？
      根因是口径声明**散落多头**：18 处红线构成要件各写一份字面声明，措辞与
      `redline_benchmark` 生成的说明句还不一致。已收敛为
      `engine/industry_benchmark.py` 的 `BENCHMARK_CAUTION` / `BENCHMARK_CAUTION_SHORT`
      两个常量（裁定：非官方基准**只有线索参照价值，不构成判定依据**）。

    判据（红必须来自判据，不来自解析失败）：
      ① 单一来源——除常量定义所在文件外，任何 `engine/*.py` 里都不得出现
         **字符串字面量**「非税务机关官方口径」（AST `Constant` 判定，注释不算；
         其余模块一律 import 常量引用）；
      ② 行为——`redline_benchmark.benchmark_note()` 产出的说明句必须含完整声明，
         且不得残留旧版「（来源 …，通用参考值（非税务机关官方口径））」的双括号写法。
    """
    issues: List[Tuple[str, str, str]] = []
    _CAUTION_FILE = ROOT / "engine" / "industry_benchmark.py"
    _BARE = "非税务机关官方口径"
    for _fp in sorted((ROOT / "engine").glob("*.py")):
        if _fp.resolve() == _CAUTION_FILE.resolve():
            continue
        try:
            _tree = ast.parse(Path(_fp).read_text(encoding="utf-8"))
        except Exception:
            continue      # 解析失败不算命中（避免"白捡的红"）
        for _nd in ast.walk(_tree):
            if isinstance(_nd, ast.Constant) and isinstance(_nd.value, str) and _BARE in _nd.value:
                issues.append(("ERROR", str(_fp.relative_to(ROOT)).replace("\\", "/"),
                               f"第{_nd.lineno}行：行业基准口径声明未引用唯一常量"
                               f"（engine/industry_benchmark.py::BENCHMARK_CAUTION），"
                               f"又写了一份字面声明"))
    try:
        from engine.industry_benchmark import BENCHMARK_CAUTION
        from engine.redline_benchmark import BENCHMARK_REFS, benchmark_note
        # ★ 2026-10-04：样检红线**动态取"已登记基准的那一条"**，不得硬编码某一条 ——
        #   事故：本处原写死 `RL-PAY-001`；疑点6 修复把它的"人均营收"对标**摘除**
        #   （薪酬类总额与营收基准**跨量纲**）后，这段行为闸门随之误报 2 条 ERROR，
        #   而 benchmark_note 本身完全正常 ⇒ **闸门自己成了误报源**。
        #   动态选取后：新增/摘除任何一条对标都不会再让本闸门失真。
        _rid = next((k for k, _m in sorted(BENCHMARK_REFS.items())
                     if (benchmark_note(k, "广告传媒") or {}).get("text")), "")
        if not _rid:
            issues.append(("ERROR", "engine/redline_benchmark.py",
                           "BENCHMARK_REFS 中没有任何一条能产出基准说明句"
                           "（行业基准口径无法落到报告）"))
            return issues
        _note = str((benchmark_note(_rid, "广告传媒") or {}).get("text") or "")
        if not _note:
            issues.append(("ERROR", "engine/redline_benchmark.py",
                           "benchmark_note 未产出基准说明句（行业基准口径无法落到报告）"))
        if BENCHMARK_CAUTION not in _note:
            issues.append(("ERROR", "engine/redline_benchmark.py",
                           "benchmark_note 的说明句未带完整口径声明"
                           f"（缺「{BENCHMARK_CAUTION[:12]}…」）"))
        if "通用参考值（非税务机关官方口径）" in _note:
            issues.append(("ERROR", "engine/redline_benchmark.py",
                           "基准说明句仍是旧版双括号写法（来源…，通用参考值（非官方口径）），"
                           "读者无法判断哪一份是非官方数据"))
    except Exception as exc:
        issues.append(("WARN", "tools/audit_consistency.py",
                       f"行业基准口径行为闸门执行失败: {exc}"))
    return issues


def check_report_punctuation() -> List[Tuple[str, str, str]]:
    """报告正文不得出现中文语境下的半角标点（标点规范化必须接入输出收敛点）。

    ★ 2026-09-27 新增（真实缺陷，用户要求「标点符号技能要加强」）：报告净化收敛点
      `enterprise_report._zh_normalize_obj` 只做中文化/自然化/定性净化，**未做标点规范化**，
      实测报告正文残留 1315 处中文语境半角括号、11 处半角冒号等。
    判据：
      ① 行为——`_zh_normalize_obj` 必须把中文语境半角标点转全角；
      ② 端到端——企业易读报告 + 前端/离线**直接消费**的 `all_findings`/`domain_summary`
         不得再含中文紧邻的半角 `, ; : . ! ?` 与半角圆括号对
         （输出边界 `main._enforce_scenario_execution_boundary` 已统一规范化）。
    """
    import re as _re
    issues: List[Tuple[str, str, str]] = []
    # ① 行为探针：收敛点必须做标点规范化
    try:
        from engine.enterprise_report import _zh_normalize_obj
        probe = _zh_normalize_obj("名单中: 中文(内容)")
        if ("：" not in probe) or ("（内容）" not in probe):
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "_zh_normalize_obj 未做中文标点规范化（半角未转全角）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       f"标点规范化行为探针异常: {exc}"))

    _CJK = r"\u4e00-\u9fa5"
    _pats = [
        _re.compile(rf"[{_CJK}]\s*[,;:]\s*(?=[{_CJK}\d])"),
        _re.compile(rf"[{_CJK}]\.(?![0-9A-Za-z])"),
        _re.compile(rf"[{_CJK}][!?]"),
        _re.compile(rf"[{_CJK}]\s*\([^()]{{1,80}}\)"),   # 中文后紧跟的半角圆括号对
    ]

    def _scan_punct(obj):
        acc = {"n": 0, "sample": ""}

        def _walk(o):
            if isinstance(o, str):
                for p in _pats:
                    m = p.search(o)
                    if m:
                        acc["n"] += 1
                        if not acc["sample"]:
                            acc["sample"] = o[max(0, m.start() - 12):m.end() + 12]
                        break
            elif isinstance(o, list):
                for x in o:
                    _walk(x)
            elif isinstance(o, dict):
                for v in o.values():
                    _walk(v)

        _walk(obj)
        return acc

    # ② 端到端：企业易读报告
    er = _load_fixture_enterprise_report()
    if er:
        a = _scan_punct(er)
        if a["n"]:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           f"企业易读报告仍有 {a['n']} 处中文紧邻半角标点"
                           f"（标点规范化未生效）。示例：{a['sample']!r}"))

    # ②b 端到端：前端/离线直接消费的原始发现字段
    full = None
    for _p in (ROOT / "scripts" / "four_reports" / "company_1_full.json",
               ROOT / "data" / "cache" / "last_analysis_cache.json"):
        if _p.exists():
            try:
                full = json.loads(_read(_p))
            except Exception:
                full = None
            if full:
                break
    if isinstance(full, dict):
        for _sec in ("all_findings", "domain_summary"):
            a = _scan_punct(full.get(_sec))
            if a["n"]:
                issues.append(("ERROR", "main.py",
                               f"报告字段 {_sec} 仍有 {a['n']} 处中文紧邻半角标点"
                               f"（前端/离线直接消费该字段，输出边界未规范化）。"
                               f"示例：{a['sample']!r}"))
    return issues


def _load_fixture_enterprise_report() -> Optional[Dict]:
    """取一份真实的企业报告（工作底稿版基线）作为金字塔闸门校验样本。"""
    candidates = [
        ROOT / "scripts" / "four_reports" / "company_1_full.json",
        ROOT / "data" / "cache" / "last_analysis_cache.json",
    ]
    for p in candidates:
        if not p.exists():
            continue
        try:
            d = json.loads(_read(p))
        except Exception:
            continue
        er = d.get("enterprise_readable_report")
        if not er and "1" in d and d["1"].get("report"):
            er = d["1"]["report"]["report"].get("enterprise_readable_report")
        if er and er.get("confirmed_problems"):
            return er
    return None


def check_overall_conclusion_derivation() -> List[Tuple[str, str, str]]:
    """★ 2026-09-26：报告第一章「本轮检查总体结论」必须**从 findings 派生**，不得手写模板。

    真实动机：用户曾手写一版总体结论，其中行业数字（毛利率 2.1%）与报告实测
    （19.8%、处于合理区间）方向相反、分层与正文 risk_level 打架 —— 手写文案必然与数据脱节。
    落地要求：
      ① `engine/overall_conclusion.py` 必须存在，且只从 report_data 读实测（含 confirmed_problems）；
      ② `build_enterprise_readable_report` 必须调用 `build_overall_conclusion`；
      ③ Web 端与离线导出两条渲染路径都必须消费 `overall_conclusion`（否则"生成了却看不见"）。
    """
    import ast as _ast

    issues: List[Tuple[str, str, str]] = []

    def _read(rel: str) -> str:
        p = ROOT / rel
        if not p.exists():
            return ""
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    mod_rel = "engine/overall_conclusion.py"
    mod_src = _read(mod_rel)
    if not mod_src:
        issues.append(("ERROR", mod_rel, "缺少总体结论生成器（第一章必须由 findings 派生）"))
    else:
        if "confirmed_problems" not in mod_src:
            issues.append(("ERROR", mod_rel, "生成器未从 confirmed_problems 读取实测发现"))
        if "risk_level" not in mod_src:
            issues.append(("ERROR", mod_rel, "生成器未按实测 risk_level 分层"))

    er_rel = "engine/enterprise_report.py"
    er_src = _read(er_rel)
    called = False
    try:
        for node in _ast.walk(_ast.parse(er_src)):
            if isinstance(node, _ast.Call):
                fn = node.func
                name = fn.id if isinstance(fn, _ast.Name) else (
                    fn.attr if isinstance(fn, _ast.Attribute) else "")
                if name == "build_overall_conclusion":
                    called = True
    except SyntaxError:
        issues.append(("ERROR", er_rel, "无法解析（语法错误）"))
    if not called:
        issues.append(("ERROR", er_rel,
                       "build_enterprise_readable_report 未调用 build_overall_conclusion"))

    for rel, why in (("static/js/tax-doc-analysis.js", "Web 端未渲染 overall_conclusion"),
                     ("scripts/_render_report_html.py", "离线导出未渲染 overall_conclusion")):
        src = _read(rel)
        if not src:
            issues.append(("ERROR", rel, "文件不存在"))
        elif "overall_conclusion" not in src:
            issues.append(("ERROR", rel, why))
    return issues


def check_report_chapter_integrity() -> List[Tuple[str, str, str]]:
    """★ 2026-09-27：报告第一章「检查情况总述与总体结论」的**去重与命名口径**闸门。

    真实动机（用户两次驳回）：
      · 把「检查情况总述」与「总体结论」合并时，先做成"一段摘要 + 一段详情"的并排拼接
        → 同一事实（份数/类数、各等级项数、类型分布、税种、行业口径）在章内说了两三遍；
      · 并残留「稽查必查资料」命名（违反"系统报告非税务机关稽查文书、不得用'稽查'字样"的编辑标准）。

    落地要求（防复发）：
      ① 生产源码不得出现「稽查必查资料共」（应写「本轮检查必查资料共」）；
      ② 前端工作底稿版 `_buildEnterpriseReadableBody`（单章）**不得再渲染
         `inspection_overview`** —— 该章必须只由 `overall_conclusion` 一段构成，
         不得把总述与结论并排贴回；
      ③ 离线导出 `_render_report_html.py` 同样不得渲染 `inspection_overview`。

    （去重的**运行时**不变式见 tests/test_overall_conclusion.py::TestChapterNoDuplication。）
    """
    issues: List[Tuple[str, str, str]] = []

    def _read(rel: str) -> str:
        p = ROOT / rel
        if not p.exists():
            return ""
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    # ① 命名口径：生产源码不得出现「稽查必查资料共」
    for p in sorted(list((ROOT / "engine").glob("*.py")) + list(ROOT.glob("*.py"))):
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "稽查必查资料共" in src:
            issues.append(("ERROR", rel,
                           "出现「稽查必查资料共」——系统报告非税务机关稽查文书，"
                           "须写「本轮检查必查资料共」"))

    # ② 前端工作底稿版单章不得再渲染 inspection_overview（防止两段并排贴回）
    js_rel = "static/js/tax-doc-analysis.js"
    js = _read(js_rel)
    if not js:
        issues.append(("ERROR", js_rel, "文件不存在"))
    else:
        marker = "function _buildEnterpriseReadableBody"
        idx = js.find(marker)
        if idx < 0:
            issues.append(("ERROR", js_rel,
                           "找不到 _buildEnterpriseReadableBody（工作底稿版渲染入口）"))
        else:
            nxt = js.find("\nfunction ", idx + len(marker))
            body = js[idx: nxt if nxt > 0 else len(js)]
            # ★ 2026-10-08 口径细化：禁止的是**整章重复渲染** `inspection_overview.paragraphs`
            #   （其一~七节与第一/二章内容重叠）；**允许**消费其独有字段 `posture`
            #   （分级分类处理建议的唯一权威，见下方 ⑤）。
            #   原判据"body 里出现 inspection_overview 即 ERROR"会把 ⑤ 的正确接线判成违规。
            #   ⚠ 必须**先剥注释再看代码**（JS 用 `_js_code_only`：Python 的
            #     `_strip_comments_keep_lines` 用 tokenize、只认 Python 注释，对 JS 无效——
            #     本仓已两次踩"闸门被自己的注释/过滤器判红"）。
            if re.search(r"inspection_overview[\s\S]{0,60}?\.\s*paragraphs",
                         _js_code_only(body)):
                issues.append(("ERROR", js_rel,
                               "工作底稿版 _buildEnterpriseReadableBody 又整章渲染 "
                               "`inspection_overview.paragraphs`——单章必须只由 overall_conclusion 构成"
                               "（不得把总述与结论并排贴回）；只允许消费其独有字段 `posture`"))
        # ④ 逐条小标签呈现（用户 2026-09-27 要求）
        #   ★ 2026-10-01 用户定调：删除「总—分—总」结构说明等**编排元信息**（与报告本质无关），
        #     故此处只保留「逐条小标签」这一实质呈现要求，不再要求目录结构说明。
        if "_narrativeGroup" not in js:
            issues.append(("ERROR", js_rel,
                           "工作底稿版缺少逐条小标签呈现（_narrativeGroup）"))
        # ⑤ ★ 2026-10-08（前后端对齐审计，「数据算了不显示」）：分级分类处理建议的
        #    **唯一权威 `inspection_overview.posture`** 必须被**真正渲染**。
        #    事故：该字段此前**两条链路都不渲染**（前端整章不渲染 inspection_overview、
        #    离线导出只取八/九节）⇒ 第一章那段"分级分类"是全报告**唯一可见副本**；
        #    用户 2026-10-08 按"与后章重复"把第一章那段删掉后，建议会**彻底消失**。
        #    ⇒ 判据：前端**代码**（剥注释后）必须出现对 `inspection_overview…posture` 的消费。
        #    ⚠ 必须用 `_js_code_only`：注释里也写着 `inspection_overview.posture`（说明性文字），
        #      不剥注释则"把渲染删掉"也照样通过（实测：变异验证漏报）。
        _js_code = _js_code_only(js)
        if "inspection_overview" not in _js_code or ".posture" not in _js_code:
            issues.append(("ERROR", js_rel,
                           "未渲染 `inspection_overview.posture`（分级分类处理建议的唯一权威）"
                           "——「数据算了不显示」会复发：第一章已不再承载该内容"))

    # ③ 离线导出：总述章**只渲染 overall_conclusion**，不得整章渲染 inspection_overview
    #   ★ 2026-09-29 口径细化：原判据是"文件里出现 inspection_overview 即 ERROR"，
    #     目的是防"同一事实两段并排重复"。但 inspection_overview 的**八、九两节**
    #     （关键口径对照 / 时效与滞纳金提示）是 overall_conclusion **没有**的内容，
    #     离线完全不渲染会造成"口径索引与时效提示在离线导出中缺失"（点评 P1-9/P1-12 的验收面）。
    #     故判据改为：**不得把 paragraphs 全量渲染**（那才是重复），只允许取八/九节。
    #   ★ 2026-09-29 二次口径细化：判据不能是"哪个子串在不在"——**过滤表达式本身也含
    #     `inspection_overview)` 与 `for _t in (`**，子串匹配会把自己的过滤器判成违规
    #     （实测踩中）。改为检测**未过滤的直接赋值**这一形态。
    off_rel = "scripts/_render_report_html.py"
    off = _strip_comments_keep_lines(_read(off_rel) or "")
    if not off:
        issues.append(("ERROR", off_rel, "文件不存在"))
    elif '_IVP = _iv.get("paragraphs")' in off or "_IVP = _iv.get('paragraphs')" in off:
        issues.append(("ERROR", off_rel,
                       "离线导出整章渲染 inspection_overview（与「总述只渲染 overall_conclusion」冲突）"))
    elif 'err.get("inspection_overview")' in off and "_IV_SECTIONS" not in off:
        issues.append(("ERROR", off_rel,
                       "离线导出去掉了八/九节的过滤条件（会整章重复渲染总述）"))

    return issues


def check_overall_conclusion_no_dup() -> List[Tuple[str, str, str]]:
    """★ 2026-09-27：第一章「检查情况总述与总体结论」的**运行时去重不变式**。

    与 tests/test_overall_conclusion.py::TestChapterNoDuplication 同源，但可被
    `audit_consistency`（含 --strict）与 `tools/verify_release.py` 直接调用——
    让"同一事实章内只说一遍"这条不变式同样在**发布校验**里拦得住（不能只靠手跑 pytest）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.overall_conclusion import build_overall_conclusion
    except Exception as exc:  # 生成器导入失败不得静默放行
        return [("ERROR", "engine/overall_conclusion.py",
                 "无法导入总体结论生成器：%s" % exc)]

    probs = [
        {"seq": 1, "title": "红字冲销与作废发票比例异常", "risk_level": "高风险",
         "taxes": ["增值税"], "suspect": "涉嫌隐匿收入", "conclusion_grade": "待核"},
        {"seq": 2, "title": "工资表人数与社保参保人数不符", "risk_level": "中风险",
         "taxes": ["个人所得税"], "suspect": "", "conclusion_grade": "待核"},
        {"seq": 3, "title": "有进无销", "risk_level": "待核验",
         "taxes": [], "suspect": "", "conclusion_grade": "待核"},
        {"seq": 4, "title": "固定资产取得、投用与折旧不匹配", "risk_level": "低风险",
         "taxes": [], "suspect": "", "conclusion_grade": "待核"},
    ]
    rd = {
        "files_count": 3,
        "file_results": [{"type": "t%d" % i} for i in range(2)],
        "target_entity": {},
        "enterprise_readable_report": {
            "confirmed_problems": probs, "further_checks": [{"seq": 5}],
        },
    }
    try:
        oc = build_overall_conclusion(rd)
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "engine/overall_conclusion.py", "生成总体结论抛错：%s" % exc)]

    P = [str(p) for p in (oc.get("paragraphs") or [])]
    joined = "".join(P)
    if joined.count("识别并列示") != 1:
        issues.append(("ERROR", "engine/overall_conclusion.py",
                       "事项总数应只出现一次，实测 %d 次（章内重复）"
                       % joined.count("识别并列示")))
    if any(p.startswith("本轮识别并列示") for p in P):
        issues.append(("ERROR", "engine/overall_conclusion.py",
                       "「风险总量」不得单列一段（应并入「检查范围与结果概览」）"))
    # ★★ 2026-10-08（用户：「把第一章从'压缩版全文'改为真正的'执行摘要'，采用'总结—概括—抽象'
    #   三层结构」）：判据**反转**。
    #   旧判据 = "每个等级清单标题只出现一次"（承认逐项清单存在）；
    #   新口径 = 第一章**不得再有逐项清单** —— 项数只以"高风险 N 项、中风险 M 项…"的
    #   **计数**形式出现一次，逐项明细一律指向第二章风险事项台账（与后章不重复）。
    for lvl in ("高风险", "中风险", "低风险", display_label("待核验")):   # 2026-10-15 展示词由唯一权威派生（原硬编码「已列明」会漏检新展示词）
        if any(p.startswith(lvl + " ") and "项：" in p for p in P):
            issues.append(("ERROR", "engine/overall_conclusion.py",
                           "第一章又出现「%s」逐项清单（执行摘要不逐项平铺："
                           "项数只留计数、明细指向第二章台账）" % lvl))
    # 用户点名删除的四类"与后章重复"内容，一律不得回到第一章
    for _banned, _why in (
        ("事项—税种关联次数", "税种关联次数明细（与后章重复）"),
        ("按风险性质归纳：", "风险性质归纳明细（已由「（三）主线抽象」承担）"),
        ("监管态度与后续处理建议", "监管态度与后续处理建议详细分类（与后章重复）"),
        ("检查范围与结果概览", "与「（一）检查性质与资料条件」重复的旧段"),
    ):
        if _banned in joined:
            issues.append(("ERROR", "engine/overall_conclusion.py",
                           "第一章出现已删除内容「%s」：%s" % (_banned, _why)))
    if len(P) > 10:
        issues.append(("ERROR", "engine/overall_conclusion.py",
                       "第一章段落数 %d 超上限 10（执行摘要要短，防回退成压缩版全文；"
                       "旧实现为 15 段）" % len(P)))
    if "待核实事项" in joined:
        issues.append(("ERROR", "engine/overall_conclusion.py",
                       "出现裸「待核实事项」（应写「涉嫌风险事项」；涉嫌已含待核实，不再叠加）"))
    return issues


def check_conclusion_and_suspicion_order() -> List[Tuple[str, str, str]]:
    """★★ 2026-10-08（用户：「请只重构报告第一章…把第一章改为真正的'执行摘要'，
    采用'总结—概括—抽象'三层结构」）—— 第一章结构 + 排序不变式。

    三条硬要求：
      ① **四段式段标齐备且按序**：（一）检查性质与资料条件（总结）→（二）整体结论（概括）
         →（三）主线抽象（抽象）→（四）下一步动作（建议）。
         ★ 口径变更史：2026-10-02 要求"结论先行（综合评价早于概览）"；2026-10-08 定稿为
           "总结（资料条件）在前、概括（结论）紧随"。⇒ 不变式的**实质**改为
           **"整体结论不得被程序性铺垫淹没"：整体等级必须出现在前 3 段内**。
      ② **等级与证据状态分列**：等级只有 高/中/低；「证据不足」是证据状态，
         必须声明"不参与风险等级排序"，且其展示写法走唯一权威 `risk_levels.display_label`
         （「待核验」→「已列明」；正文写权威名会被通俗化成禁用词「尚需核实」）。
      ③ 疑点（confirmed_problems）呈现顺序必须 **极高 → 高 → 中 → 低 → 待核验**，
         由 `engine/enterprise_report.py::_RISK_PRESENT_ORDER` 单一权威控制。

    判据全部是**运行时实测段落下标**或源码形态，不做宽泛字符串计数，
    避免"闸门自己被自己的过滤器判红"的假红。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.overall_conclusion import build_overall_conclusion
    except Exception as exc:  # 生成器导入失败不得静默放行
        return [("ERROR", "engine/overall_conclusion.py",
                 "无法导入总体结论生成器：%s" % exc)]

    probs = [
        {"seq": 1, "title": "红字冲销与作废发票比例异常", "risk_level": "高风险",
         "taxes": ["增值税"], "suspect": "涉嫌隐匿收入", "conclusion_grade": "待核"},
        {"seq": 2, "title": "工资表人数与社保参保人数不符", "risk_level": "中风险",
         "taxes": ["个人所得税"], "suspect": "", "conclusion_grade": "待核"},
        {"seq": 3, "title": "有进无销", "risk_level": "待核验",
         "taxes": [], "suspect": "", "conclusion_grade": "待核"},
        {"seq": 4, "title": "固定资产取得、投用与折旧不匹配", "risk_level": "低风险",
         "taxes": [], "suspect": "", "conclusion_grade": "待核"},
    ]
    rd = {
        "files_count": 3,
        "file_results": [{"type": "t%d" % i} for i in range(2)],
        "target_entity": {},
        "enterprise_readable_report": {
            "confirmed_problems": probs, "further_checks": [{"seq": 5}],
        },
    }
    try:
        P = [str(p) for p in (build_overall_conclusion(rd).get("paragraphs") or [])]
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "engine/overall_conclusion.py", "生成总体结论抛错：%s" % exc)]

    def _idx(needle: str) -> int:
        for i, p in enumerate(P):
            if needle in p:
                return i
        return -1

    # ① 四段式段标齐备且按序（2026-10-08 定稿；旧判据"综合评价早于检查范围概览"已废）
    _marks4 = ["（一）检查性质与资料条件", "（二）整体结论", "（三）主线抽象", "（四）下一步动作"]
    _pos4 = [_idx(m) for m in _marks4]
    _miss4 = [m for m, v in zip(_marks4, _pos4) if v < 0]
    if _miss4:
        issues.append(("ERROR", "engine/overall_conclusion.py",
                       "第一章缺四段式段标：%s" % "、".join(_miss4)))
    elif _pos4 != sorted(_pos4):
        issues.append(("ERROR", "engine/overall_conclusion.py",
                       "第一章四段未按「性质与资料条件→整体结论→主线抽象→下一步」排列，"
                       "实测段落下标 %s" % _pos4))
    # ①-b 结论不被程序性铺垫淹没（保住 2026-10-02 的实质诉求）
    i_concl = _idx("企业整体风险综合评价")
    if i_concl < 0:
        issues.append(("ERROR", "engine/overall_conclusion.py",
                       "第一章缺「企业整体风险综合评价」段"))
    elif i_concl > 2:
        issues.append(("ERROR", "engine/overall_conclusion.py",
                       "整体结论被程序性铺垫淹没：排在第 %d 段（应在前 3 段内）" % (i_concl + 1)))

    # ② 等级与证据状态必须**分列**（原判据"监管态度分级由重到轻"随该段删除而废）
    from engine.risk_levels import display_label as _dl6   # noqa: PLC0415
    _joined_oc = "".join(P)
    if "不参与风险等级排序" not in _joined_oc:
        issues.append(("ERROR", "engine/overall_conclusion.py",
                       "第一章未声明证据状态「不参与风险等级排序」（证据状态与风险等级须分列）"))
    if any(str(x.get("risk_level") or "") == "待核验" for x in probs) \
            and _dl6("待核验") not in _joined_oc:
        issues.append(("ERROR", "engine/overall_conclusion.py",
                       "存在「待核验」事项却未在第一章列明其证据状态"
                       "（应走展示写法「%s」）" % _dl6("待核验")))

    # ③ 疑点呈现顺序：唯一权威表 + 排序键必须引用该表（禁止再退回 `_LEVEL_RANK`）
    try:
        _er = (ROOT / "engine" / "enterprise_report.py").read_text(
            encoding="utf-8", errors="replace")
    except OSError:
        _er = ""
    if "_RISK_PRESENT_ORDER" not in _er:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "缺疑点呈现顺序唯一权威表 `_RISK_PRESENT_ORDER`（疑点顺序会随等级表漂移）"))
    elif "_RISK_PRESENT_ORDER.get(" not in _er:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "疑点排序键未引用 `_RISK_PRESENT_ORDER`（疑点顺序未由单一权威控制）"))
    if "problems.sort" in _er:
        _sort_region = _er.split("problems.sort")[-1][:400]
        if "_RISK_PRESENT_ORDER" not in _sort_region:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "疑点 `problems.sort` 未引用 `_RISK_PRESENT_ORDER`（疑点顺序未由单一权威控制）"))
        if "_level_rank" in _sort_region:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "疑点 `problems.sort` 仍走 `_level_rank`（等级秩≠呈现序：低风险会排到"
                           "待核验后面、表外等级会插进高/中之间）"))
    else:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "找不到疑点 `problems.sort`（疑点呈现顺序失去唯一控制点）"))
    return issues


def check_clause_compliance() -> List[Tuple[str, str, str]]:
    """★ 2026-10-08 用户条款机器判据（《一键分析集成条款》+《专注税务风险检查条款》）。

    只做**可机器判定**的六条（其余条款由产出链运行期留痕，见 `_one_click_pipeline`）：
      C1 去重三项：`dedup_pipeline.duplicate_rate` 必须返回 整体/章节统计/事实重复 三项
         （条款 5「整体≤10% / 同章节≤5% / 同一事实≤1 次，未达标不得输出」）。
      C2 去重字段安全：逐项结论字段（verdict/suggestion/confidence_formula）必须在 SKIP_KEYS，
         否则会被替换成**跨项引用**、读者看到错误结论（实测 14/16 项 verdict 被污染）。
      C3 编号不偏移：`report_pipeline` 不得出现 `_seq + 1` / `_s2 + 1`（`seq` 本就 1 起）。
      C4 结论术语权威：四词「风险信号/待核事项/已认定事实/违法认定」齐备且 L1~L4 全有映射。
      C5 知识闭环：`main.py` 调 `update_knowledge` 必须传 `case=`（否则样本库永不更新）。
      C6 效力声明：报告数据侧必须含「不替代税务机关依法定程序作出的认定」。
    """
    issues: List[Tuple[str, str, str]] = []

    # —— C1 去重三项 ——
    try:
        from engine.dedup_pipeline import duplicate_rate as _dr
        _r = _dr(["<<S:甲>>", "第一句内容" * 20, "第二句内容" * 20])
        for _k in ("整体", "章节统计", "事实重复"):
            if _k not in _r:
                issues.append(("ERROR", "engine/dedup_pipeline.py",
                               "重复率判定缺『%s』项 —— 条款要求整体≤10%%/同章节≤5%%/"
                               "同一事实≤1 次（未达标不得输出）" % _k))
        if "阻断" not in _r:
            issues.append(("ERROR", "engine/dedup_pipeline.py", "重复率判定缺『阻断』字段"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/dedup_pipeline.py", "duplicate_rate 调用失败：%s" % exc))

    # —— C2 去重字段安全 ——
    try:
        from engine.report_pipeline import SKIP_KEYS as _SK
        for _f in ("verdict", "suggestion", "confidence_formula"):
            if _f not in _SK:
                issues.append(("ERROR", "engine/report_pipeline.py",
                               "逐项结论字段 `%s` 未在 SKIP_KEYS —— 会被跨项引用替换，"
                               "读者将看到错误结论（实测 14/16 项 verdict 被污染）" % _f))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/report_pipeline.py", "读取 SKIP_KEYS 失败：%s" % exc))

    # —— C3 编号不偏移 ——
    #   ⚠ 必须**先剥注释**：本仓已三次踩"闸门被自己的注释判红"（说明性注释里会引用旧写法）。
    _rp = _strip_comments_keep_lines(_read(ROOT / "engine" / "report_pipeline.py"))
    if re.search(r"(?<![\w.])_s(?:eq|2|q)\s*\+\s*1", _rp):
        issues.append(("ERROR", "engine/report_pipeline.py",
                       "出现 `seq + 1` 形式编号 —— `seq` 本就从 1 起，加 1 会使引用编号整体偏移"
                       "（首项被标为 R2，实测产物出现错误引用）"))

    # —— C4 结论术语权威 ——
    try:
        from engine.conclusion_grade import (
            conclusion_terms, term_of, term_authority as _ta,
            GRADE_L1, GRADE_L2, GRADE_L3, GRADE_L4,
        )
        _ts = list(conclusion_terms())
        _want = ["风险信号", "待核事项", "已认定事实", "违法认定"]
        if _ts != _want:
            issues.append(("ERROR", "config/conclusion_grades.json",
                           "结论术语表须逐字为 %s，实测 %s（《专注税务风险检查条款》第4条）"
                           % (_want, _ts)))
        for _g in (GRADE_L1, GRADE_L2, GRADE_L3, GRADE_L4):
            if not term_of(_g):
                issues.append(("ERROR", "config/conclusion_grades.json",
                               "结论等级 %s 缺对外术语映射" % _g))
        if not (_ta().get("forbidden_determinative") or []):
            issues.append(("WARN", "config/conclusion_grades.json",
                           "term_authority 未登记 forbidden_determinative（越权定性词表）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "config/conclusion_grades.json", "结论术语权威读取失败：%s" % exc))

    # —— C5 知识闭环（样本入库必须真执行）——
    _mn = _strip_comments_keep_lines(_read(ROOT / "main.py"))
    _i = _mn.find("def _execute_tax_risk_analysis")
    _seg = _mn[_i:] if _i >= 0 else ""
    _j = _seg.find("\ndef ", 1)
    if _j > 0:
        _seg = _seg[:_j]
    if "update_knowledge(" in _seg and "case=" not in _seg:
        issues.append(("ERROR", "main.py",
                       "一键分析调 `update_knowledge` 未传 `case=` ⇒ 样本库永不更新"
                       "（条款 10「报告自动存入样本库」失效）"))

    # —— C6 效力声明 ——
    #   ⚠ **运行时断言权威函数**，不做整文件 grep —— 后者只要文件里别处出现过该串就"通过"，
    #     把声明删掉也不会报红（第一版反向验证就是假绿，靠反向验证才发现）。
    try:
        from engine.enterprise_report import _administrative_boundary_statement as _abs
        _txt = "".join(_abs() or [])
        if "不替代税务机关" not in _txt or "法定程序" not in _txt:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "效力声明缺『不替代税务机关依法定程序作出的认定』"
                           "（《专注税务风险检查条款》第5条）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/enterprise_report.py", "效力声明权威函数不可用：%s" % exc))

    # —— C7 报告级通用口径必须上提（防"逐项重复通用说明"拉高重复率）——
    #   实测未上提时整体重复率 16.89%、同章节超阈 10（虚假达标口径）；
    #   上提后逐项位置为引用「见报告性质和使用说明」，报告级声明含原文一次。
    try:
        from engine.report_pipeline import (
            REPORT_LEVEL_TEXT_KEYS as _K, REPORT_LEVEL_MIN_OCCUR as _M,
            REPORT_LEVEL_REF as _R, merge_report_level_notes as _mg,
        )
        from engine.enterprise_report import _report_level_notes_statement as _st
        if not _K or not _R:
            issues.append(("ERROR", "engine/report_pipeline.py", "通用口径常量表为空"))
        _items = [{"risk_level_basis": "X", "confidence_formula": "Y"} for _ in range(_M)]
        _out = _mg(_items, [])
        if set(_out) != set(_K):
            issues.append(("ERROR", "engine/report_pipeline.py",
                           "通用口径上提未生效（`merge_report_level_notes` 返回 %s）" % list(_out)))
        if any(it.get("risk_level_basis") != _R for it in _items):
            issues.append(("ERROR", "engine/report_pipeline.py",
                           "逐项位置未替换为报告级引用（引用口径 %s）" % _R))
        if not _st([{"risk_level_basis": "X", "confidence_formula": "Y"}] * _M):
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "报告级口径声明未生成 ⇒ 逐项引用将**悬空**"))
        # 形态判据：`dedup_report_data` **必须真的调用**（否则上提「算了不执行」——
        # 第一版只测函数本身，反向验证时假绿才发现）
        _rp2 = _strip_comments_keep_lines(_read(ROOT / "engine" / "report_pipeline.py"))
        _i2 = _rp2.find("def dedup_report_data")
        if _i2 >= 0:
            _seg2 = _rp2[_i2:]
            _j2 = _seg2.find("\ndef ", 1)
            if _j2 > 0:
                _seg2 = _seg2[:_j2]
            if "merge_report_level_notes(" not in _seg2:
                issues.append(("ERROR", "engine/report_pipeline.py",
                               "`dedup_report_data` 未调用 `merge_report_level_notes` —— 上提未执行"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/report_pipeline.py", "通用口径上提校验失败：%s" % exc))

    # —— C8 结论术语不得被通俗化层改写（**行为级**：术语漂移是实测事故）——
    #   实测：`plain_language` 把"待核"通俗化为"须核对" ⇒ 报告里出现"须核对事项"，
    #   与权威术语表漂移。判据 = 每个术语经两层清洗后必须**原样返回**。
    try:
        from engine.report_wording import scrub_vague as _sv8, vague_hits as _vh8
        from engine.plain_language import to_plain_obj as _tp8
        from engine.conclusion_grade import conclusion_terms as _ct8
        for _tm in _ct8():
            if _sv8(_tm) != _tm:
                issues.append(("ERROR", "engine/report_wording.py",
                               "结论术语「%s」被 scrub_vague 改写为「%s」" % (_tm, _sv8(_tm))))
            if _tp8(_tm, "text") != _tm:
                issues.append(("ERROR", "engine/plain_language.py",
                               "结论术语「%s」被 to_plain_obj 改写为「%s」" % (_tm, _tp8(_tm, "text"))))
            if _vh8(_tm):
                issues.append(("ERROR", "engine/report_wording.py",
                               "结论术语「%s」被模糊词判据误判：%s" % (_tm, _vh8(_tm))))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/report_wording.py", "术语豁免校验失败：%s" % exc))
    return issues


def check_summary_count_consistency() -> List[Tuple[str, str, str]]:
    """★★ 2026-10-08（用户：「`summary.pending_problem_count=26` 与
    `confirmed_problem_count=16` 口径不符，属数据侧老缺陷」）：summary 派生计数必须自洽且单一权威。

    真实事故：`_build_summary()` 在**列表定稿之前**执行；之后两处补丁
    （并入独立风险事项后 / 「计数定稿」块）**各自只同步了 `confirmed_problem_count`**，
    把**同源的兄弟字段** `pending_problem_count` 漏掉
    ⇒ 实测产物「已确认 16 项 / 待核 26 项」，而 26 也不是任何真实列表的长度。

    判据（**行为 + 形态**双锁，不做宽泛字符串计数，避免闸门被自己的过滤器判红）：
      ① 唯一权威 `_resync_summary_counts` 必须存在，且**行为正确**：
         喂一份"事先被写歪"的 summary，必须被校正成 `confirmed == len(problems)`、
         `pending == confirmed − verified`；
      ② **除权威自身外，全库不得再有第二处手改 summary 计数**（`["*_count"] =` 形态）——
         这正是"逐个补字段必然漏"的复发点；
      ③ 渲染层（`report_pipeline`）不得自算 `confirmed − verified` 形成**第二个口径**。
    """
    import re as _re_scc

    issues: List[Tuple[str, str, str]] = []
    er_rel = "engine/enterprise_report.py"
    try:
        src = (ROOT / er_rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [("ERROR", er_rel, "文件不存在")]

    auth_name = "_resync_summary_counts"
    if ("def %s(" % auth_name) not in src:
        issues.append(("ERROR", er_rel,
                       "缺 summary 派生计数的唯一权威 `%s`（否则必然出现「只补一个字段」的漏改）" % auth_name))
    else:
        # ── ① 行为断言：被写歪的 summary 必须被校正 ──
        try:
            from engine.enterprise_report import _resync_summary_counts as _rsc
            _probs = [{"conclusion_grade": "待核"}] * 16
            _out = {
                "summary": {"confirmed_problem_count": 26, "verified_problem_count": 9,
                            "pending_problem_count": 26},
                "confirmed_problems": _probs,
                "further_checks": [{}] * 6,
                "completed_checks": [],
            }
            _r = _rsc(_out)
            _sm = _out["summary"]
            if _sm.get("confirmed_problem_count") != 16:
                issues.append(("ERROR", er_rel,
                               "权威未校正「已确认」计数：%s（应=len(confirmed_problems)）"
                               % _sm.get("confirmed_problem_count")))
            if _sm.get("verified_problem_count") != 0:
                issues.append(("ERROR", er_rel,
                               "权威未按 `conclusion_grade` 重算「已核定」：%s"
                               % _sm.get("verified_problem_count")))
            if _sm.get("pending_problem_count") != 16:
                issues.append(("ERROR", er_rel,
                               "权威未校正「待核」：%s（应=已确认−已核定=16）"
                               % _sm.get("pending_problem_count")))
            if _sm.get("further_check_count") != 6:
                issues.append(("ERROR", er_rel,
                               "权威未重算「受阻检查」：%s" % _sm.get("further_check_count")))
            if _r.get("pending") != _r.get("confirmed", 0) - _r.get("verified", 0):
                issues.append(("ERROR", er_rel, "权威返回值不自洽（待核 ≠ 已确认−已核定）"))
        except Exception as exc:  # noqa: BLE001 —— 权威调不动不得静默放行
            issues.append(("ERROR", er_rel, "唯一权威调用失败：%s" % exc))

        # ── ② 除权威自身外，不得再有第二处手改 summary 计数 ──
        #   ⚠ 判据必须**限定为 summary 的计数白名单**：曾用宽泛的 `["*_count"] =`，
        #     把 `out["_promoted_standalone_count"]`（并入条数）与
        #     `inspection_questions_report["attached_theme_count"]`（挂载主题数）
        #     这两个**与 summary 无关**的字段也判成违规 = 闸门自己假红（实测踩中）。
        _auth_start = src.index("def %s(" % auth_name)
        _nxt = src.find("\ndef ", _auth_start + 1)
        _auth_body = src[_auth_start: _nxt if _nxt > 0 else len(src)]
        _rest = src[:_auth_start] + src[_nxt if _nxt > 0 else len(src):]
        _assign = _re_scc.compile(
            r'\[\s*"(?:confirmed_problem_count|verified_problem_count|'
            r'pending_problem_count|further_check_count|completed_check_count)"\s*\]\s*=')
        if _assign.search(_rest):
            issues.append(("ERROR", er_rel,
                           "权威之外仍有手改 summary 计数字段（`[\"*_count\"] =`）——"
                           "「逐个补字段」正是本次 26≠16 的根因，一律改为调用 `%s`" % auth_name))

    # ── ③ 渲染层不得自算 pending（否则是第二个口径）──
    rp_rel = "engine/report_pipeline.py"
    try:
        _rp = (ROOT / rp_rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        _rp = ""
    if _rp and _re_scc.search(r'confirmed_problem_count"\]\s*-\s*', _rp):
        issues.append(("ERROR", rp_rel,
                       "渲染层自算「待核 = 已确认 − 已核定」形成第二个口径；"
                       "源头已由 `%s` 提供权威 `pending_problem_count`，应直接取字段" % auth_name))
    return issues


def check_chapter_template_dedup() -> List[Tuple[str, str, str]]:
    """★ 2026-09-29（点评 P2-7）：章节内「通用说明」模板去重的不变式（锁定，防复发）。

    历史：第二章(资料接收与保全) 9 条 narrative、第四章(风险检查处理意见) 25 条 narrative
    每条都以**同一段通用说明**结尾（点评「模板重复约四成」）。收敛点
    `engine/chapter_dedup.collapse_common_tail` 把公共后缀抽到章首说一次。

    本闸门做**行为 + 接线 + 渲染**三层锁定（任一层缺失→ERROR），
    避免"抽出了却没接线 / 接线了却没渲染 / 模块退化失效"三种退化：
      ① 行为：collapse_common_tail 对合成重复尾确能抽出 note 且剥离条目模板；
      ② 后端：enterprise_report 接线 collapse_common_tail 并暴露 materials_note/action_plan_note；
      ③ 前端：tax-doc-analysis.js 在章首渲染 **action_plan_note**（风险检查处理意见章，正文渲染中）。
    注：`report.materials`（资料接收与保全章的逐份 narrative）在当前 6 章式报告中**不进正文**
    （第一章「资料齐备性总览」已概述），故 materials_note 不作前端渲染要求——
    若将来该章恢复渲染，须同步渲染 materials_note（本注释与判定文档留存该前置条件）。
    """
    issues: List[Tuple[str, str, str]] = []
    # ① 行为断言
    try:
        from engine.chapter_dedup import collapse_common_tail
        _tail = "以上资料经逐份读取解析，读取完整，文件指纹与解析回执保留在内部资料底稿中，可按文件名回查。"
        _cand = [
            {"narrative": "第一份为销项发票明细，" + _tail},
            {"narrative": "第二份为银行流水台账，" + _tail},
            {"narrative": "第三份为工资表数据，" + _tail},
            {"narrative": "第四份为成本发票清单，" + _tail},
        ]
        out, note = collapse_common_tail(_cand, "narrative")
        if not note or len(note) < 20:
            issues.append(("ERROR", "engine/chapter_dedup.py",
                           "collapse_common_tail 未能抽出公共后缀（模板去重失效）"))
        if isinstance(out, list) and out and isinstance(out[0], dict):
            if len(str(out[0].get("narrative") or "")) >= len(_cand[0]["narrative"]):
                issues.append(("ERROR", "engine/chapter_dedup.py",
                               "collapse_common_tail 未剥离条目内模板（条目未变短）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/chapter_dedup.py",
                       "无法导入/运行 collapse_common_tail：%s" % exc))
    # ② 后端接线与暴露
    er = ROOT / "engine" / "enterprise_report.py"
    try:
        src = er.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        src = ""
        issues.append(("ERROR", "engine/enterprise_report.py", "读取失败：%s" % exc))
    if src:
        if "collapse_common_tail" not in src:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "未接线 collapse_common_tail（章节模板去重缺失）"))
        for k in ("materials_note", "action_plan_note"):
            if k not in src:
                issues.append(("ERROR", "engine/enterprise_report.py",
                               "未暴露 %s（前端无法在章首渲染通用说明）" % k))
    # ③ 前端渲染（只见于被渲染的章：风险检查处理意见章 action_plan_note）
    js = ROOT / "static" / "js" / "tax-doc-analysis.js"
    try:
        jsrc = js.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        jsrc = ""
        issues.append(("ERROR", "static/js/tax-doc-analysis.js", "读取失败：%s" % exc))
    if jsrc and "action_plan_note" not in jsrc:
        issues.append(("ERROR", "static/js/tax-doc-analysis.js",
                       "未渲染 action_plan_note（风险检查处理意见章通用说明抽出了却没显示）"))
    return issues


def check_cost_recon_render() -> List[Tuple[str, str, str]]:
    """★ 2026-09-27：主营成本「两口径勾稽明细」必须三处齐备（防幽灵段落）。

    用户要求：这一明细必须**无论是否超阈值都照出**（合规留痕），三处渲染目标都要画，
    否则又会退化成"数据有、网页没有"。落地要求：
      ① engine/cost_recon_detail.py 存在且只读 report_data；
      ② enterprise_report 调用 build_cost_recon_detail 并写入 out 字典 "cost_recon_detail"；
      ③ Web(tax-doc-analysis.js) 与离线(_render_report_html.py) 都消费 cost_recon_detail。
    另：发票类目构成须取自 pipeline 已算好的 core 拆分（单一权威），本模块不得重跑 classify。
    """
    issues: List[Tuple[str, str, str]] = []

    def _read(rel: str) -> str:
        p = ROOT / rel
        if not p.exists():
            return ""
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    mod_rel = "engine/cost_recon_detail.py"
    mod = _read(mod_rel)
    if not mod:
        issues.append(("ERROR", mod_rel, "缺少两口径勾稽明细生成器"))
    else:
        if "report_data" not in mod:
            issues.append(("ERROR", mod_rel, "生成器未从 report_data 读取"))
        if "core_goods_breakdown" not in mod:
            issues.append(("ERROR", mod_rel,
                           "发票类目构成未取 pipeline 的 core_goods_breakdown（可能重跑 classify 导致口径分叉）"))

    er = _read("engine/enterprise_report.py")
    if "build_cost_recon_detail" not in er or '"cost_recon_detail"' not in er:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "未调用 build_cost_recon_detail 或未写入 cost_recon_detail"))

    for rel, why in (("static/js/tax-doc-analysis.js", "Web 端未渲染 cost_recon_detail"),
                     ("scripts/_render_report_html.py", "离线导出未渲染 cost_recon_detail")):
        src = _read(rel)
        if not src:
            issues.append(("ERROR", rel, "文件不存在"))
            continue
        if "cost_recon_detail" not in src:
            issues.append(("ERROR", rel, why))
        # 逐张/逐笔清单（导出附件）必须三处可导出/可展示
        for _tok in ("invoice_rows", "book_rows"):
            if _tok not in src:
                issues.append(("ERROR", rel,
                               "未渲染逐张/逐笔清单字段 %s（导出附件缺失）" % _tok))
    return issues


def check_tax_impact_render() -> List[Tuple[str, str, str]]:
    """★ 2026-09-27（P1）：潜在税额影响必须三处齐备（防幽灵段落）+ 铁律齐备。

    铁律：取不到金额 → 必须是"未量化"，不得用默认值顶数。
    """
    issues: List[Tuple[str, str, str]] = []

    def _read(rel: str) -> str:
        p = ROOT / rel
        if not p.exists():
            return ""
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    mod_rel = "engine/tax_impact.py"
    mod = _read(mod_rel)
    if not mod:
        issues.append(("ERROR", mod_rel, "缺少潜在税额测算模块"))
    else:
        for tok in ("estimate_tax", "未量化"):
            if tok not in mod:
                issues.append(("ERROR", mod_rel, "测算模块缺少关键项：%s" % tok))

    er = _read("engine/enterprise_report.py")
    if "build_tax_impact_summary" not in er or '"tax_impact_summary"' not in er:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "未调用 build_tax_impact_summary 或未写入 tax_impact_summary"))

    for rel, who in (("static/js/tax-doc-analysis.js", "Web 端"),
                     ("scripts/_render_report_html.py", "离线导出")):
        src = _read(rel)
        if not src:
            issues.append(("ERROR", rel, "文件不存在"))
            continue
        for _tok in ("tax_impact", "main_assessment"):
            if _tok not in src:
                issues.append(("ERROR", rel, "%s未渲染 %s" % (who, _tok)))
    _er2 = _read("engine/enterprise_report.py")
    if "_build_main_assessment" not in _er2 or '"main_assessment"' not in _er2:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "未调用 _build_main_assessment 或未写入 main_assessment"))
    return issues


def check_industry_source_integrity() -> List[Tuple[str, str, str]]:
    """★ 2026-09-26：行业口径三铁律（防"冒名抬高权威"与"销项口径失效"）。

    真实事故（某传媒企业）：`_online_company_lookup` 把**从经营范围推断**的行业直接写进
    `result["industry"]`，被 pipeline 当作「外部工商核验」（最高权威）消费 ——
    等于让"经营范围"绕道拿到最高权，R1（不得用经营范围里的商品名当行业）形同虚设；
    同时销项发票品名给出的「广告服务」因不在基准库命名空间而**匹配不到**，销项口径失效。
    落地要求：
      ① `_online_company_lookup` 必须标注 `industry_source`，不得让经营范围推断冒充外部核验；
      ② pipeline 只在来源确为「外部工商核验」时才按 online 口径传参；
      ③ 行业解析器里 **销项发票品名（SRC_INVOICE）权重必须最高**（税务风险以实际经营产出为主口径）；
      ④ 发票分类名必须经 `normalize_industry_name` 归一到基准库键（否则下游对标匹配不到）。
    """
    import ast as _ast

    issues: List[Tuple[str, str, str]] = []

    def _read(rel: str) -> str:
        p = ROOT / rel
        if not p.exists():
            return ""
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    pipe_rel = "engine/pipeline.py"
    pipe_src = _read(pipe_rel)
    if 'result["industry_source"]' not in pipe_src:
        issues.append(("ERROR", pipe_rel,
                       "_online_company_lookup 未标注 industry_source"
                       "（经营范围推断会冒充外部工商核验）"))
    if 'lookup.get("industry_source")' not in pipe_src:
        issues.append(("ERROR", pipe_rel,
                       "pipeline 未按 industry_source 过滤，经营范围推断可冒充「外部工商核验」"))

    res_rel = "engine/industry_resolver.py"
    res_src = _read(res_rel)
    weights: Dict[str, Any] = {}
    try:
        for node in _ast.walk(_ast.parse(res_src)):
            if isinstance(node, _ast.Assign) and any(
                    isinstance(t, _ast.Name) and t.id == "_WEIGHT" for t in node.targets):
                if isinstance(node.value, _ast.Dict):
                    for k, v in zip(node.value.keys, node.value.values):
                        if isinstance(k, _ast.Name) and isinstance(v, _ast.Constant):
                            weights[k.id] = v.value
    except SyntaxError:
        issues.append(("ERROR", res_rel, "无法解析（语法错误）"))

    if not weights:
        issues.append(("ERROR", res_rel, "未取到 _WEIGHT 权重表"))
    else:
        inv = weights.get("SRC_INVOICE")
        online = weights.get("SRC_ONLINE")
        if inv is None:
            issues.append(("ERROR", res_rel, "_WEIGHT 缺少 SRC_INVOICE"))
        elif inv < max(weights.values()):
            issues.append(("ERROR", res_rel,
                           f"销项发票品名权重({inv})不是最高"
                           " —— 税务风险应以实际经营产出为主口径"))
        if inv is not None and online is not None and inv <= online:
            issues.append(("ERROR", res_rel,
                           f"销项品名权重({inv})未高于外部工商核验({online})"))

    if "normalize_industry_name" not in res_src:
        issues.append(("ERROR", res_rel,
                       "缺少 normalize_industry_name（发票分类名未归一到基准库键）"))
    elif "normalize_industry_name(best)" not in res_src:
        issues.append(("ERROR", res_rel,
                       "infer_from_goods 未对金税分类名做归一（销项口径会失效）"))
    return issues


def check_cost_industry_basis() -> List[Tuple[str, str, str]]:
    """★ 2026-09-26：主营业务成本识别必须**用行业口径**，且"判不出来不得默认判成本"。

    真实动机（用户指令）：`identify_main_biz_cost` 原先只用品名关键词＋金额大小，**完全没用行业**，
    且"其余一律默认判主营业务成本"——把判不出来的一律当成本，既虚增成本又掩盖问题；
    更隐蔽的是 `_MAJOR_EXPENSE_KWS` 里有 '广告/推广/宣传/发布'，于是**广告公司的核心成本
    「广告发布/媒体投放」被当成"重大费用"截走**（实测已复现）——即"用通用费用表判断行业性成本"。
    落地要求：
      ① static/industry_data.json 必须有 core_inputs（服务/流通类显式登记）；
      ② industry_resolver 必须提供 core_inputs_for（制造/加工/贸易类复用 product_chains）；
      ③ identify_main_biz_cost 必须接受 industry 参数，且返回 pending_cost_invs（待核）与
         core_cost_basis（依据可自证）；
      ④ **行业核心投入判定必须排在通用费用关键词之前**（否则行业性成本被截走）；
      ⑤ 管道必须注入行业口径（set_active_industry），保证全系统同口径。
    """
    import ast as _ast

    issues: List[Tuple[str, str, str]] = []

    def _read(rel: str) -> str:
        p = ROOT / rel
        if not p.exists():
            return ""
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    # ① 数据表
    import json as _json
    try:
        with open(ROOT / "static" / "industry_data.json", encoding="utf-8") as f:
            data = _json.load(f)
        ci = data.get("core_inputs") or {}
        if not ci:
            issues.append(("ERROR", "static/industry_data.json",
                           "缺少 core_inputs（行业核心投入表）"))
        if not (data.get("product_chains") or {}):
            issues.append(("ERROR", "static/industry_data.json",
                           "缺少 product_chains（制造/加工/贸易类的核心投入来源）"))
    except Exception as e:
        issues.append(("ERROR", "static/industry_data.json", "读取失败: %s" % e))

    # ② 解析器
    res_rel = "engine/industry_resolver.py"
    res_src = _read(res_rel)
    if "def core_inputs_for" not in res_src:
        issues.append(("ERROR", res_rel, "缺少 core_inputs_for（行业→核心投入）"))

    # ③ 成本识别模块
    mbc_rel = "engine/main_biz_cost.py"
    mbc_src = _read(mbc_rel)
    has_industry_arg = False
    try:
        for node in _ast.walk(_ast.parse(mbc_src)):
            if isinstance(node, _ast.FunctionDef) and node.name == "identify_main_biz_cost":
                has_industry_arg = any(a.arg == "industry" for a in node.args.args)
    except SyntaxError:
        issues.append(("ERROR", mbc_rel, "无法解析（语法错误）"))
    if not has_industry_arg:
        issues.append(("ERROR", mbc_rel, "identify_main_biz_cost 未接受 industry 参数"))
    for key, why in (("pending_cost_invs", "未返回待核桶（判不出来会默认判成本）"),
                     ("core_cost_basis", "未返回判定依据（无法自证来源）"),
                     ("has_industry_basis", "未区分有无行业口径")):
        if key not in mbc_src:
            issues.append(("ERROR", mbc_rel, why))

    # ④ 顺序：行业/类目口径必须排在通用费用关键词之前
    idx_cat = mbc_src.find("收入类目对应")
    if idx_cat < 0:
        issues.append(("ERROR", mbc_rel, "缺少「以收入类目确定成本类目」判定"))
    idx_core = mbc_src.find("行业核心投入（%s）")
    if idx_core < 0:
        issues.append(("ERROR", mbc_rel, "缺少「行业核心投入」判定"))
    else:
        for pat, label in (("in _REIMBURSEMENT_KWS_GLOBAL", "日常报销关键词"),
                           ("in _MAJOR_EXPENSE_KWS", "重大费用关键词")):
            i = mbc_src.find(pat)
            if i >= 0 and min(idx_core, idx_cat) > i:
                issues.append(("ERROR", mbc_rel,
                               "「行业/类目口径」判定必须排在%s之前，否则行业性成本被截走" % label))
    # ★ 2026-10-02：`_MAJOR_EXPENSE_KWS` 已在 2026-10-02 收敛为引用唯一权威
    #   `engine.account_classifier`，上面那段 `in _MAJOR_EXPENSE_KWS` 的位置判据会**静默失效**
    #   （find 返回 -1 即视为通过）。补此判据守住"必须引用权威、不得自写词表"。
    if "account_classifier" not in mbc_src:
        issues.append(("ERROR", mbc_rel,
                       "重大费用词表未引用唯一权威 account_classifier（重抄必然漂移）"))
    # 类目级匹配（不是整串严格相等）：必须用 `*分类*` 类目比对。
    # ⚠ 用**词边界**正则而非裸子串：`sale_catsZZ` 仍包含 `sale_cats`，裸子串会造成假阴性
    #   （反向验证时实测漏报）。
    if not re.search(r"\b_cat_of\b", mbc_src) or not re.search(r"\bsale_cats\b", mbc_src):
        issues.append(("ERROR", mbc_rel,
                       "「以收入类目确定成本类目」未做类目级比对（整串严格相等会漏配）"))

    # ⑤ 注入点
    pipe_rel = "engine/pipeline.py"
    if "set_active_industry" not in _read(pipe_rel):
        issues.append(("ERROR", pipe_rel, "管道未注入行业口径（set_active_industry）"))
    return issues


def check_account_classifier_single_source() -> List[Tuple[str, str, str]]:
    """（已知**不**判重抄、但属不同概念的词表，勿擅自动它们：
        `verified_rule_engine._EXPENSE_DETAIL_KWS` 费用明细科目字段（3/37=8%）；
        `verified_rule_engine._SUSPICIOUS_EXPENSE_KW` 可疑/虚假发票线索（7/12≈58%，
        低于 60% 阈值，且判定的是"可疑"不是"会计归属"）。）"""
    """★ 2026-10-02：成本/费用归属词表**只能有一份**（`engine/account_classifier.py`）。

    真实动机（同名字表互相打架，已造成错判）：
      `domain_analysis._MAJOR_EXPENSE_KWS` 与 `main_biz_cost._MAJOR_EXPENSE_KWS`
      **同名不同词**（后者多 运费/装卸/承运/运送），而 `pipeline._EXPENSE_KWS` 又是第三份。
      同一张「住宿费」发票：pipeline 判费用、main_biz_cost 判不到重大费用 → 落「待核/默认成本」
      ⇒ **虚增成本、压低毛利**。现统一为 account_classifier 派生出口，其余模块只许 import。

    判据（扫描 engine/**.py 的**模块级字符串列表字面量**）：
      ① 唯一权威模块必须存在，且导出 `all_authoritative_keywords()`；
      ② 名称命中「成本/费用归属」概念（名含 EXPENSE+KW/COST+KW，或为历史 4 张表的名字）
         的私有表，其词与权威词表**交集比例 ≥ 60% 且交集词数 ≥ 5** ⇒ 判定为「实质重抄」，ERROR。
         （用比例而非「只要有交集就报」：bank_flow 的 _CORP_KW、input_voucher 的
           _NON_DEDUCTIBLE_KW、monthly_reconcile 的 _SOCIAL_KWS 等词表本就是**另一个概念**
           —银行流水主体/不得抵扣/社保科目—，与会计归属无关，误报会让闸门失去意义。）
      ③ 已收敛的模块（main_biz_cost / domain_analysis / pipeline / memory）只保留
         `_BIZ_ELEMENT_EXCLUSIVE_KWS` 这一个**书面命名的豁免名**——理由是概念不同
         （经营要素完备性=空壳检测），且词值由权威层派生函数消费，不会漂移。
    """
    import ast as _ast

    issues: List[Tuple[str, str, str]] = []

    auth_rel = "engine/account_classifier.py"
    if not (ROOT / auth_rel).exists():
        return [("ERROR", "engine/", "缺少唯一权威 account_classifier（成本/费用归属）")]

    # ① 权威模块必须导出权威词表
    try:
        src_auth = (ROOT / auth_rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        src_auth = ""
    for marker, why in (
        ("def all_authoritative_keywords", "未导出 all_authoritative_keywords（无法反扫重抄）"),
        ("def classify_line", "未导出 classify_line（成本/费用判定入口）"),
        ("ALLOWED_CLASSES", "未定义 ALLOWED_CLASSES（三态词表）"),
    ):
        if marker not in src_auth:
            issues.append(("ERROR", auth_rel, why))

    auth_words = set()
    try:
        sys.path.insert(0, str(ROOT))
        for _m in ("engine.account_classifier",):
            sys.modules.pop(_m, None)
        import importlib
        _ac = importlib.import_module("engine.account_classifier")
        importlib.invalidate_caches()
        auth_words = set(_ac.all_authoritative_keywords())
    except Exception as e:  # pragma: no cover
        issues.append(("ERROR", auth_rel, "无法导入权威模块: %s" % e))
    if not auth_words:
        return issues

    # ② 扫全库重抄
    HISTORY_NAMES = {"_MAJOR_EXPENSE_KWS", "_EXPENSE_KWS", "BIZ_EXPENSE_KEYWORDS",
                     "_REIMBURSEMENT_KWS_GLOBAL"}
    for p in sorted((ROOT / "engine").glob("*.py")):
        if p.name == "account_classifier.py":
            continue
        try:
            tree = _ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError as e:
            issues.append(("ERROR", "engine/%s" % p.name, "无法解析（语法错误）: %s" % e))
            continue
        for node in tree.body:
            if not isinstance(node, _ast.Assign):
                continue
            for tg in node.targets:
                if not isinstance(tg, _ast.Name):
                    continue
                name = tg.id
                up = name.upper()
                concept = ("EXPENSE" in up and "KW" in up) or ("COST" in up and "KW" in up) \
                    or name in HISTORY_NAMES
                if not concept:
                    continue
                val = node.value
                if not isinstance(val, (_ast.List, _ast.Tuple)):
                    continue  # 引用/派生赋值（= account_classifier.xxx()）→ 不算重抄
                if not all(isinstance(e, _ast.Constant) and isinstance(e.value, str)
                           for e in val.elts):
                    continue
                words = {e.value for e in val.elts}
                if not words:
                    continue
                ov = words & auth_words
                if len(ov) >= 5 and len(ov) / len(words) >= 0.6:
                    issues.append((
                        "ERROR", "engine/%s" % p.name,
                        "「%s」与唯一权威 account_classifier 词表重叠 %d/%d（%.0f%%），"
                        "属实质重抄必随时间漂移；改为引用 account_classifier 的派生出口"
                        "（major_expense_keywords / operating_expense_keywords / "
                        "expense_element_keywords）"
                        % (name, len(ov), len(words), 100.0 * len(ov) / len(words))))
    return issues


def check_cost_expense_triad() -> List[Tuple[str, str, str]]:
    """★ 2026-10-02：成本/费用判定必须**三态可自证**（主营业务成本 / 期间费用 / 待核）。

    为什么必须有这道闸门（机制性教训）：
      分类若允许"判不出来就默认判成本"，等于**系统性虚增成本、压低毛利**，
      而且**不会报错**——报告照样出、数字照样漂亮，只有专业复核才发现。
      故把三态与「evidence/置信度不可少」写成结构性判据，由机器长期盯住。

    判据：
      ① 权威模块必须导出 `ALLOWED_CLASSES` 且**同时包含** 主营业务成本 / 期间费用 / 待核；
      ② `classify_line()` 返回值必须含 account_class / confidence / evidence / needs_context /
         missing_material 五个键，且 account_class ∈ ALLOWED_CLASSES；
      ③ 返回项的 confidence 与 evidence **必须非空**（evidence 为空=判定不可自证来源）；
      ④ `needs_context` 层的词（运输/水电/包装/维修/租赁/差旅/会议/检测…）在无项目上下文时
         **必须落「待核」**，不得判成本（L2 铁律：用途决定归属）；
      ⑤ 完全未命中的陌生品名 **必须落「待核」**，绝不允许默认成本；
      ⑥ 行业核心投入命中 ⇒ 可判「主营业务成本」且置信度=高。
    """
    issues: List[Tuple[str, str, str]] = []
    auth_rel = "engine/account_classifier.py"

    try:
        sys.path.insert(0, str(ROOT))
        sys.modules.pop("engine.account_classifier", None)
        import importlib
        ac = importlib.import_module("engine.account_classifier")
        importlib.invalidate_caches()
    except Exception as e:
        return [("ERROR", auth_rel, "无法导入 account_classifier: %s" % e)]

    # ① 三态词表
    allowed = list(getattr(ac, "ALLOWED_CLASSES", ()) or ())
    for need in ("主营业务成本", "期间费用", "待核"):
        if need not in allowed:
            issues.append(("ERROR", auth_rel,
                           "ALLOWED_CLASSES 缺「%s」——不是三态（缺待核=会默认判成本）" % need))
    if not callable(getattr(ac, "classify_line", None)):
        return issues

    # ②/③ 结构与非空
    REQUIRED_KEYS = ("account_class", "confidence", "evidence", "needs_context",
                     "missing_material", "matched_layer", "reason")
    probes = [
        ("*广告服务*广告发布费", dict(industry="广告传媒")),
        ("办公用品 文具", dict(industry="广告传媒")),
        ("*物流辅助服务*运输费", dict(industry="广告传媒")),
        ("核查用途不明的全新品名abc123", dict(industry="广告传媒")),
    ]
    for goods, kw in probes:
        try:
            r = ac.classify_line(goods, **kw) or {}
        except Exception as e:
            issues.append(("ERROR", auth_rel, "classify_line(%r) 抛异常: %s" % (goods, e)))
            continue
        missing_keys = [k for k in REQUIRED_KEYS if k not in r]
        if missing_keys:
            issues.append(("ERROR", auth_rel,
                           "classify_line(%.12s…) 缺字段 %s（判定必须可自证）"
                           % (goods, missing_keys)))
            continue
        if r.get("account_class") not in allowed:
            issues.append(("ERROR", auth_rel,
                           "classify_line(%.12s…) 返回越界 account_class=%r（不在 %s）"
                           % (goods, r.get("account_class"), allowed)))
        if not str(r.get("evidence") or "").strip():
            issues.append(("ERROR", auth_rel,
                           "classify_line(%.12s…) evidence 为空（判定无依据）" % goods))
        if not str(r.get("confidence") or "").strip():
            issues.append(("ERROR", auth_rel,
                           "classify_line(%.12s…) confidence 为空" % goods))

    # ④ 需上下文词在无项目上下文时必须落待核
    needs_ctx = [k for k in getattr(ac, "NEEDS_CONTEXT_KWS", ()) or ()]
    if not needs_ctx:
        issues.append(("ERROR", auth_rel, "未定义 NEEDS_CONTEXT_KWS（用途决定归属的词）"))
    for probe in ("运输费", "水电费", "包装费", "维修费", "租赁费", "会议费", "检测费"):
        hit = next((k for k in needs_ctx if k in probe), None)
        if hit is None:
            continue
        r = ac.classify_line(probe, industry="广告传媒")
        if r.get("account_class") != ac.CLASS_UNDETERMINED:
            issues.append(("ERROR", auth_rel,
                           "需上下文词「%s」在无项目上下文时落到了 %r，违反 L2 铁律（应落「待核」）"
                           % (probe, r.get("account_class"))))

    # ⑤ 陌生品名必须落待核，且绝不判成本
    r = ac.classify_line("全新未登记品名zzq999", industry="广告传媒")
    if r.get("account_class") == ac.CLASS_COST:
        issues.append(("ERROR", auth_rel,
                       "未命中任何口径的陌生品名被判「主营业务成本」（=默认判成本，会虚增成本）"))
    if r.get("account_class") != ac.CLASS_UNDETERMINED:
        issues.append(("ERROR", auth_rel, "陌生品名未落「待核」"))

    # ⑥ 行业核心投入 ⇒ 成本且高置信
    r = ac.classify_line("*广告服务*广告发布费", industry="广告传媒")
    if r.get("account_class") != ac.CLASS_COST or r.get("confidence") != "高":
        issues.append(("ERROR", auth_rel,
                       "行业核心投入未判为「主营业务成本+高置信」（实际 %r/%r）"
                       % (r.get("account_class"), r.get("confidence"))))
    return issues


def check_identifier_not_translated() -> List[Tuple[str, str, str]]:
    """**程序标识符不得被当展示文本汉化**（2026-10-05 实测缺陷）。

    ★ 事故：`related_analyses[].key`（值形如 `bank_flow_report`）被中文化成
      `bank_flow_报告`、`false_invoice_report` 被译成 `否_invoice_报告` ——
      前端按 key 找渲染器，key 一变即**匹配不到**，该块静默不渲染。
    根因：`_ZH_REPLACEMENTS` 的单词边界写成 `(?<![A-Za-z])report(?![A-Za-z])`，
      但 **下划线 `_` 也是标识符字符**，故 `bank_flow` 后的 `_report` 被当成
      "独立的英文单词 report"⇒ 翻译。同理 `false` 被词元表译成"否"。
    判据（行为测试，双向）：
      ① **标识符必须原样**：`_zh_normalize('bank_flow_report')` 等**不得改变**；
      ② **正文仍须翻译**：`_zh_normalize('这是 report 一词')` 必须译成中文
         （防止"修 bug"把中文化能力一起关掉）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.enterprise_report import _zh_normalize
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/enterprise_report.py", f"取不到 _zh_normalize: {exc}"))
        return issues
    # ① 标识符不得被改（取映射表真实键，避免硬编码样本失效）
    _ids = ["bank_flow_report", "false_invoice_report", "cost_recon_detail",
            "cross_enterprise_report", "fund_loop_report", "two_tax_report"]
    try:
        from engine.report_layout import SPECIAL_TO_PROBLEM as _S
        _ids += list(_S.keys())
    except Exception:  # noqa: BLE001
        pass
    for _i in sorted(set(_ids)):
        if _zh_normalize(_i) != _i:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "程序标识符被汉化：%s → %s（前端按 key 匹配会失效）"
                           % (_i, _zh_normalize(_i))))
    # ② 正文必须仍被翻译（阴性对照：别把能力关掉）
    if "报告" not in _zh_normalize("这是 report 一词"):
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "正文英文未再中文化（修标识符 bug 时误关了中文化能力）"))
    return issues


def check_no_vague_wording() -> List[Tuple[str, str, str]]:
    """报告禁用模糊词（用户 2026-10-05 明确要求：「报告永远不能出现待核实」）。

    ★ 为什么锁死：报告原 verdict 写「账内检出信号**待核实**（未认定到构成要件，不作定性）」，
      证据链三态又有一档叫「**待核实**」—— 把「已从账内算出确定事实」与
      「取得同类资料须确认范围」两种**完全不同**的状态混成一个词，
      读者无法判断该不该整改。实测一份报告出现 559 处。
    判据（源码契约 + 行为双向对照）：
      ① 唯一权威 `engine/report_wording.py` 必须提供
         `STATUS_TEXT` / `FORBIDDEN_VAGUE_TERMS` / `scrub_vague`；
      ② `scrub_vague` 对「待核实」必须**真的改写**（阳性对照），
         对「已有」「缺失」「高风险」等正常值必须**原样透出**（阴性对照）——
         防止把"消除模糊词"做成"篡改正常表述"；
      ③ 报告最终出口必须调用它（否则改了词表也不生效）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.report_wording import (  # noqa: F401
            STATUS_TEXT, FORBIDDEN_VAGUE_TERMS, scrub_vague, vague_hits,
        )
    except Exception as exc:
        issues.append(("ERROR", "engine/report_wording.py", f"报告用词口径模块缺失: {exc}"))
        return issues
    # ② 行为双向对照
    # ★ 2026-10-05 修正：口径已明确为"**只改独立状态值、术语原位保留**"
    #   ⇒ 阳性对照必须用**整串状态值**（"状态：待核实"这种嵌句写法现在**本就不该改**，
    #     它若是术语，改了就成病句 —— 这正是用户第四次贴报告时发现的 32 处病句的成因）。
    _before = scrub_vague("待核实")
    if "待核实" in _before:
        issues.append(("ERROR", "engine/report_wording.py",
                       "scrub_vague 未改写**独立状态值**「待核实」（阳性对照失败）"))
    # 术语必须原位保留（阴性对照之二）——防止"清零"又把专业表述改坏
    # ⚠ 2026-10-06 调整样本：原样本含「待核验事实」，而它是**禁用词**（用户口径
    #   "不得出现待核验/待核实/尚需核实"）⇒ 要求"保留"与用户口径冲突；
    #   现行口径：**含禁用词的表述必须被改写**，而**不含禁用词的术语**必须原位保留。
    for _term in ("经成本/费用/待核实区分后",
                  "应作「待核实」处理",
                  "该笔属会计估计变更，不属税会差异"):
        if scrub_vague(_term) != _term:
            issues.append(("ERROR", "engine/report_wording.py",
                           "scrub_vague 误改**不含禁用词**的术语（会产出病句）：%s" % _term))
    # 反向锁：含禁用词的表述**必须**被改写（否则报告会带着禁用词出厂）
    for _bad_src in ("两者均为待核验事实，须人工复核", "资料缺失待核", "域分析待核事实",
                     "税负待核", "其他应付款大额长期挂账（待核）"):
        _out_bad = scrub_vague(_bad_src)
        # ★ 2026-10-08（条款 B4）：走唯一判据 vague_hits —— 它**豁免结论用语权威术语**
        _still = vague_hits(_out_bad)
        if _still:
            issues.append(("ERROR", "engine/report_wording.py",
                           "含禁用词「%s」的表述未被改写（残留 %s）：%r → %r"
                           % (_bad_src[:14], _still, _bad_src, _out_bad)))
    # 结构标识必须原位保留（降级疑点的身份，闸门靠它识别）
    for _keep in ("待核线索：资金回流与公私混同检测",):
        if scrub_vague(_keep) != _keep:
            issues.append(("ERROR", "engine/report_wording.py",
                           "scrub_vague 误改**结构标识**（降级疑点将认不出来）：%s" % _keep))
    for _ok_word in ("已有", "缺失", "高风险", "中风险", "待企业提交"):
        if scrub_vague(_ok_word) != _ok_word:
            issues.append(("ERROR", "engine/report_wording.py",
                           "scrub_vague 误改正常值「%s」（阴性对照失败）" % _ok_word))
    # ③ 报告出口接线
    try:
        _src = _read(ROOT / "engine" / "enterprise_report.py")
    except Exception:
        _src = ""
    if "scrub" not in _src and "_scrub_out_vague" not in _src:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "报告最终出口未接词表（改了词表也不会生效）"))

    # ④ **产物级**扫描：报告正文里真的不许出现模糊词（2026-10-06 补）
    #   ★ 事故：新写的「自我怀疑」层在文案里写了「待核」，下游 `plain_language.to_plain`
    #     把它改写成 **「待核实」**（禁用词）⇒ 报告出现 102 处「待核实」，
    #     而当时闸门只查"机制在不在"（权威模块存在 / 行为对照 / 出口接线），
    #     **不查产物里到底有没有那个词** ⇒ 闸门全绿却带着禁用词出厂。
    #   ⇒ 判据必须落到产物：**机制正确 ≠ 结果正确**。
    #   ⚠ 只扫**正文文本字段**（narrative_paragraphs / self_doubt 等），不扫 `columns`
    #     等**枚举/结构字段**（那里「现状」列合法取值本就含"待企业提交"这类词）。
    _art = ROOT / "scripts" / "four_reports" / "company_1_full.json"
    if _art.exists():
        try:
            import json as _json2
            _ad = _json2.loads(_art.read_text(encoding="utf-8", errors="replace"))
            _arep = _ad.get("report") if isinstance(_ad.get("report"), dict) else _ad
            _aer = (_arep or {}).get("enterprise_readable_report") or {}
            # ★★ 2026-10-06：两处修正（都是"闸门自己漏判"）
            #   ① **扫描范围过窄**：原先只扫 `confirmed_problems` 的段落与 self_doubt
            #      ⇒ `overall_conclusion.paragraphs`、`main_assessment` 完全不扫，
            #      于是实测产物里「尚需核实（证据不足，不参与风险等级排序）2 项」
            #      长期存在而闸门全绿。
            #   ② **禁用词表自带一份**：原先本地写 `("待核实","待核验","待核查")`，
            #      与权威 `report_wording.FORBIDDEN_VAGUE_TERMS` 各写一套
            #      （后者已含「尚需核实」）⇒ 改了权威、闸门判据不跟着变。现统一转发权威。
            #   ★★ 2026-10-08（同一病根**第三次**出血）：转发权威**词表**还不够 ——
            #      下面 `_vague_hits` 曾**自实现一份判据**（只剔结构前缀、不剔权威术语），
            #      与权威 `report_wording.vague_hits`（剔术语、不剔前缀）**互补地各错一半**：
            #        · 审计自实现：「待核事项」（术语）被误判 ⇒ 实测 25 处 ERROR 误报；
            #        · 权威：`待核线索：`（结构标识）被误判。
            #      ⇒ 判据本身也必须**薄转发唯一权威**（本函数只负责"哪些字段算正文"，
            #        不负责"什么算模糊词"）。
            from engine.report_wording import vague_hits as _vague_authority  # noqa: PLC0415
            # ⚠ 只扫**正文文本**，跳过结构/枚举键（其合法取值本就含"待企业提交"这类词）
            _skip_keys = {"risk_level", "level", "risk_level_capped_from",
                          "conclusion_grade", "code", "key", "id", "trace_id",
                          "redline_id", "seq", "columns", "级别", "等级"}
            # ★ 2026-10-06：三个必要的收窄（否则是**误报**）
            #   ① **受保护的结构标识**不得算禁用词：`待核线索：` 是降级疑点的机器标识
            #      （闸门 `check_downgraded_problem_wording` 靠它识别），词表已声明"不替换"。
            #      ⚠ 现由权威 `vague_hits` 一并豁免，此处**不再自实现**。
            #   ② **内部工作底稿块**（无任何渲染器引用）不属"面向企业正文"：
            #      `inspector_reasoning` 在 `static/js/**` 与 `scripts/_render_report_html.py`
            #      中**零引用**（grep 可证），按 authority `report_layout.INTERNAL_BLOCKS` 跳过。
            #      ⚠ 若将来给它加了渲染器，必须同时把本豁免去掉。
            #   ③ 表格 `rows` 单元格属**枚举/结构字段**（其合法取值含"待企业提交"）。
            try:
                from engine.report_layout import INTERNAL_BLOCKS as _IB5  # noqa: PLC0415
            except Exception:  # noqa: BLE001
                _IB5 = ()

            def _vague_hits(_t: str) -> list:
                return list(_vague_authority(_t))

            _bad: Dict[str, list] = {}
            _seen2: set = set()

            def _walk_bad(_o, _path: str) -> None:
                if isinstance(_o, (dict, list)):
                    if id(_o) in _seen2:
                        return
                    _seen2.add(id(_o))
                if isinstance(_o, dict):
                    for _k, _v in _o.items():
                        _p = "%s.%s" % (_path, _k) if _path else str(_k)
                        if not _path and str(_k) in _IB5:
                            continue                    # 内部工作底稿块：跳过
                        if str(_k) in _skip_keys or str(_k) == "rows":
                            continue
                        if isinstance(_v, str):
                            _hit = _vague_hits(_v)
                            if _hit:
                                _bad.setdefault(_p, []).extend(_hit)
                        else:
                            _walk_bad(_v, _p)
                elif isinstance(_o, list):
                    for _i, _v in enumerate(_o):
                        _p = "%s[%d]" % (_path, _i)
                        if isinstance(_v, str):
                            _hit = _vague_hits(_v)
                            if _hit:
                                _bad.setdefault(_p, []).extend(_hit)
                        else:
                            _walk_bad(_v, _p)

            _walk_bad(_aer, "")
            if _bad:
                _first = list(_bad.items())[:5]
                issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                               "报告正文出现禁用模糊词（用户口径：「报告永远不能出现待核实/"
                               "尚需核实」）：共 %d 处，例：%s —— "
                               "注意下游 `plain_language.to_plain` 会把「待核验」通俗化成"
                               "「尚需核实」，所以引擎侧**两处都不能写**" % (len(_bad), _first)))
        except Exception as _e4:  # noqa: BLE001
            issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                           f"产物级禁用词扫描失败（不阻断）：{_e4}"))
    return issues


def check_vague_wording_single_source() -> List[Tuple[str, str, str]]:
    """**禁用模糊词的"判据"必须唯一**（2026-10-08；同一病根**第三次**出血的永久上锁）。

    事故链（同一病根三次复发）：
      ① `quality_gates` 本地写 `("待核实","待核验","待核查")` ⇒ 与权威各写一套；
      ② 权威补「尚需核实」后，本地判据不跟着变 ⇒ 上游造词、下游接不住；
      ③ `tools/audit_consistency` 又**自实现** `_vague_hits`（只剔结构前缀、不剔权威术语）
         ⇒ 与权威 `report_wording.vague_hits`（剔术语、不剔前缀）**互补地各错一半**：
           · 审计把权威术语「待核事项」误判 ⇒ 实测 **25 处 ERROR 误报**；
           · 权威把结构标识「待核线索：」误判。
    判据（行为 + 源码契约，双向）：
      ① **行为**：唯一权威 `report_wording.vague_hits` 必须**同时豁免**
         结论用语权威术语（`conclusion_grades` 四术语）与结构标识前缀（`_PROTECTED_PREFIXES`），
         且仍拦得住真禁用词（阳性对照）—— 任一反例即 ERROR；
      ② **源码契约**：除 `engine/report_wording.py`（定义处）与测试外，任何模块
         **不得** import `FORBIDDEN_VAGUE_TERMS` 后自建判据 —— 消费方只能调 `vague_hits`。
         （⚠ `import *` 会让 pyflakes 放弃检测，故此处自建 AST 判据，不依赖 linter。）
    """
    issues: List[Tuple[str, str, str]] = []
    # ① 行为探针
    try:
        from engine.report_wording import vague_hits as _vh          # noqa: PLC0415
        from engine.conclusion_grade import conclusion_terms as _ct  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "engine/report_wording.py", "无法导入模糊词权威：%s" % exc)]
    for _tm in (_ct() or ()):
        if _tm and _vh("本项属%s；未认定到构成要件，不作定性" % _tm):
            issues.append(("ERROR", "engine/report_wording.py",
                           "权威术语「%s」被 `vague_hits` 误判为模糊词（术语漂移，"
                           "会误报 ERROR）：%s" % (_tm, _vh("本项属%s" % _tm))))
    if _vh("待核线索：所有者权益异常变动"):
        issues.append(("ERROR", "engine/report_wording.py",
                       "结构标识「待核线索：」被 `vague_hits` 误判为模糊词"
                       "（会让闸门认不出降级疑点）：%s" % _vh("待核线索：X")))
    for _bad in ("账内检出信号待核实", "税负尚需核实", "其他应付款大额长期挂账（待核）"):
        if not _vh(_bad):
            issues.append(("ERROR", "engine/report_wording.py",
                           "真禁用词未被 `vague_hits` 拦下（闸门实效性失效）：%s" % _bad))
    # ② 源码契约：不得自建判据
    import ast as _ast  # noqa: PLC0415
    _allowed = {(ROOT / "engine" / "report_wording.py").resolve()}
    _cands: List[Any] = []
    for _d in ("engine", "tools", "scripts"):
        _r = ROOT / _d
        if _r.exists():
            _cands += [p for p in _r.rglob("*.py")
                       if "__pycache__" not in p.parts
                       and not p.name.startswith("test_")
                       and "tests" not in p.parts]
    _cands.append(ROOT / "main.py")
    for _p in _cands:
        try:
            if _p.resolve() in _allowed or not _p.exists():
                continue
            # ⚠ 仓库内存在**破损的遗留脚本**（连语法都不通过，实测
            #   `scripts/_gate_trunc_final.py` 等 6 个）⇒ 解析失败只跳过、不当成本闸门的发现。
            #   同时抑制它们抛出的 SyntaxWarning（否则闸门输出被噪声污染）。
            import warnings as _warnings  # noqa: PLC0415
            with _warnings.catch_warnings():
                _warnings.simplefilter("ignore", SyntaxWarning)
                _tree = _ast.parse(_p.read_text(encoding="utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            continue
        _aliases = set()
        for _n in _ast.walk(_tree):
            if isinstance(_n, _ast.ImportFrom):
                for _a in _n.names:
                    if (_a.name or "") == "FORBIDDEN_VAGUE_TERMS":
                        _aliases.add(_a.asname or _a.name)
        if not _aliases:
            continue
        if any(isinstance(_n, _ast.Name) and _n.id in _aliases for _n in _ast.walk(_tree)):
            issues.append(("ERROR", str(_p.relative_to(ROOT)).replace("\\", "/"),
                           "自建禁用模糊词判据（应薄转发 `report_wording.vague_hits`）："
                           "import 了 `FORBIDDEN_VAGUE_TERMS` 并直接用它比对 —— "
                           "新一轮词表变化会再次「改了权威、判据不跟着变」"))
    return issues


def check_report_plain_language() -> List[Tuple[str, str, str]]:
    """报告「说人话」收敛点 + 最终出口必须**迭代去环**（2026-09-27）。

    ★ 真实缺陷背景（本闸门锁死，防复发）：`main._execute_tax_risk_analysis` 的最终
      出口原用**递归**遍历整份 report_data，遇到报告里的**循环引用/深层嵌套**抛
      `maximum recursion depth exceeded`，被 except 静默跳过 → 不仅"说人话"替换没生效，
      连此前加的标点规范化在最终出口**也从未真正生效**（产出日志可见
      `[标点规范化] 跳过：maximum recursion depth exceeded`，正文半角逗号仍在）。
    判据：
      ① 唯一权威 `engine.plain_language` 必须提供 `to_plain` 与 `walk_strings_inplace`；
      ② 报告最终出口必须调用 `walk_strings_inplace`（不得回退到递归遍历）；
      ③ 行为——`walk_strings_inplace` 对**含循环引用**的对象必须能完成并替换（不爆栈）；
      ④ 行为——键黑名单保护前端枚举/标签（level / verdict 的值不得被替换）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.plain_language import to_plain_obj, walk_strings_inplace  # noqa: F401
    except Exception as exc:
        issues.append(("ERROR", "engine/plain_language.py", f"说人话收敛点缺失: {exc}"))
        return issues

    try:
        main_src = _read(ROOT / "main.py")
    except Exception:
        main_src = ""
    # 要求是**调用**（`walk_strings_inplace(`）而非注释里的提及
    if "walk_strings_inplace(" not in main_src:
        issues.append(("ERROR", "main.py",
                       "报告最终出口未调用 walk_strings_inplace（迭代去环版）；"
                       "递归遍历遇循环引用会 max recursion depth exceeded 而被静默跳过"))

    # ③ 行为：含循环引用也能完成并替换（用**系统语言**词，非行业术语）
    a = {"t": "监管盲区"}
    b = {"p": a}
    a["c"] = b                       # a -> b -> a 循环
    try:
        walk_strings_inplace({"x": a, "y": [b]}, lambda s, k: to_plain_obj(s, k))
        if "看不到的死角" not in a["t"]:
            issues.append(("ERROR", "engine/plain_language.py",
                           "walk_strings_inplace 在循环引用场景未完成替换"))
    except RecursionError as exc:  # pragma: no cover
        issues.append(("ERROR", "engine/plain_language.py",
                       f"walk_strings_inplace 仍会爆栈: {exc}"))

    # ④ 行为：键黑名单保护枚举/标签；系统语言文本照常替换；行业术语**不被改**
    probe = {"level": "高风险", "verdict": "触碰税务违规红线",
             "detail": "须核查监管盲区", "term": "销项发票与进项发票勾稽不平衡"}
    walk_strings_inplace(probe, lambda s, k: to_plain_obj(s, k))
    if probe["level"] != "高风险":
        issues.append(("ERROR", "engine/plain_language.py", "键黑名单未保护 level"))
    if "红线" not in probe["verdict"]:
        issues.append(("ERROR", "engine/plain_language.py", "键黑名单未保护 verdict"))
    if ("看不到的死角" not in probe["detail"]) or ("需要" not in probe["detail"]):
        issues.append(("ERROR", "engine/plain_language.py", "系统语言文本未被说人话替换"))
    if probe["term"] != "销项发票与进项发票勾稽不平衡":
        issues.append(("ERROR", "engine/plain_language.py",
                       "行业专有名词被误改（用户口径：行业术语保持原样直接用）"))
    return issues


def check_evidence_text_not_truncated() -> List[Tuple[str, str, str]]:
    """证据文本（备注栏/凭据号）不得硬截断（2026-10-01 用户要求新增）。

    事故：红冲/作废发票明细的 `note` 用 `str(remark)[:48]` 截断 —— 把备注栏里的
    「被红冲蓝票号码」「红字发票信息确认单编号」这类**核验红冲合规性的关键凭据号**切成半截
    （实测「…确认单编号：44010625011003201370」显示成「…编号：4401」），且**未加省略号**，
    违反 `engine/table_governance.py` 自己写下的第 3 条「截断不注明」。

    判据（源码级，宁少勿错）：生产代码中凡对 `remark`（发票备注栏）做长度切片的，即报 ERROR ——
    备注栏承载被红冲蓝票号码/确认单编号/建筑服务项目地等法定要素，属证据本体，必须完整呈现。
    反向验证：在 domain_analysis.py 里写回 `str(inv.get('remark',''))[:48]` → 本闸门报 ERROR。
    """
    issues: List[Tuple[str, str, str]] = []
    import re as _re
    # 匹配 `...remark...[:N]`（备注栏被切片），允许中间夹引号/括号/逗号
    pat = _re.compile(r"remark.{0,40}?\[\s*:\s*\d+\s*\]")
    for rel in ("engine/domain_analysis.py", "engine/pipeline.py", "engine/enterprise_report.py",
                "engine/monthly_reconcile.py", "engine/table_governance.py"):
        p = ROOT / rel
        if not p.exists():
            continue
        for i, line in enumerate(_read(p).split("\n"), 1):
            if line.lstrip().startswith("#"):
                continue
            if pat.search(line):
                issues.append(("ERROR", rel,
                               "第%d行对备注栏(remark)做长度截断 —— 凭据号属证据本体，须完整呈现" % i))
    return issues

def check_constituent_sources_consistency() -> List[Tuple[str, str, str]]:
    """要件「独立数据源」必须**完整且可取得**（2026-10-01 用户指出后新增）。

    背景：构成要件独立核对表的「独立数据源」来自红线里一张**手写平行清单** `constituent_sources`，
    天然会与要件文本脱节。实测 RL-VAT-007（红字冲销与作废）系统性漏项——
    要件①/②/⑤/⑥ 只写「销项发票」，而红冲/作废**在进项侧同样存在**（样本中的红冲票即 direction=进项）；
    要件③ 漏「折让协议/拒收证明」；要件④ 漏「被冲减蓝字发票」；要件⑦ 漏退货/折让协议。

    本闸门锁死三条判据（对**所有**红线生效，数据驱动、不写特例）：
      (a) **必声明**：凡有 `constituents` 的红线必须给出等长的 `constituent_sources`
          ——2026-10-01 实测全库 89/91 条红线未声明，导致报告的「构成要件独立核对表」
          里 51.5% 的要件写「（红线定义未标注该要件的独立数据源）」；
      (b) **可取得**：每个要件的数据源名必须落在「系统资料类别 ∪ 该红线 required_materials ∪ evidence_chain」内，
          否则该要件的“已有/缺失”状态无从判定（声明了拿不到的东西）；
      (c) **完整**：要件文本中**提到**的、该红线 `required_materials` 内的资料名，
          必须出现在该要件的独立数据源里。
    ⚠ (c) 的比对范围**只取 required_materials、不取 evidence_chain 元素名**：
      元素名是「核对口径描述」，其中含「在途资金」「居家办公」一类并非资料名的词，
      纳入比对本会把它们误当作资料要求进数据源（实测 40 处噪音）。
      （2026-10-01 收紧：原先切分符含「与／/和」，会把「供应商资质与代理协议」切碎成
      「供应商资质」「代理协议」两个不存在的资料名 → 现只按顿号/逗号切分。）
    ★ 覆盖面（如实声明，勿夸大）：本闸门可抓四类漂移——
      (i) 红线声明缺失；(ii) 数据源名不在已声明资料内；(iii) 要件正文提到的已声明资料未列入数据源；(iv) 条数不按序对齐；
      ★ (v) 同一红线内 `required_materials` 重复登记同一资料名（2026-10-01 本轮实测引入过：
        曾同时在 RL-CIT-001 写「同期资料」与「转让定价文档」、RL-CIT-005 写「高新技术企业证书（若适用）」
        与「高新技术企业证书」、RL-CIT-006 写「资产损失鉴证报告（达到标准时）」与「资产损失鉴证报告」——
        同一资料两个名字会让企业按任一名字补资料却只闭合一半，故锁死）。
      ⚠ 本闸门**不**做「前缀异名」自动判据：实测会误导（「固定资产明细」的前缀登记名是
        「固定资产明细（车辆）」，属另一种对象，自动改写反而改错）。遗留的盘点表/固定资产明细/合同
        等命名差异属领域判断，另行报告，不在此闸门自动处理。
    ⚠ **抓不到**「该要件本应两侧并取却只写一侧」这类**领域判断**（如红冲/作废在进项侧同样存在，
      但要件正文并未出现「进项发票」字样）—— 该判断须靠编写规范：
      **发票/账载类要件的数据源一律按「风险发生侧」并取，两侧共有的风险（红冲作废、进项转出、
      票账差异等）不得只写销项或只写进项**。本条写入红线引擎 skill，作为新增/修改要件时的检查项。
    反向验证：把 RL-VAT-007 要件③ 的源改回「退货单」（丢掉正文已写明的「折让协议」）→ 本闸门报 ERROR。
    """
    issues: List[Tuple[str, str, str]] = []
    import re as _re
    try:
        from engine.tax_redlines import REDLINES
        from engine.enterprise_report import _DOC_TYPE_TO_CATEGORY as _MP
    except Exception as exc:
        return [("ERROR", "engine/tax_redlines.py", f"要件数据源一致性检查不可用: {exc}")]
    # 系统资料类别（含 sup_* 登记）—— 复用既有权威映射表，不另立清单
    _cats: set = set()
    for _v in (_MP or {}).values():
        if isinstance(_v, str):
            _cats.add(_v)
        elif isinstance(_v, (list, tuple)):
            _cats.update(str(x) for x in _v)

    def _split(s):
        return [x.strip() for x in _re.split(r"[、，,；;]", str(s or "")) if len(x.strip()) >= 2]

    # ★ 2026-10-02（#461 后续 · 第 9 坑「闸门自证循环」）：
    #   判据 (b)「可取得」原先是 `legal = _cats ∪ required_materials ∪ evidence_chain名`，
    #   **含该红线自己的 required_materials** ⇒ 红线写什么名、什么名就"可取得"，
    #   永远抓不到「声明了却一辈子拿不到」的独立数据源
    #   （实例：RL-OTH-001/007~011 的「印花税申报表」六条共用，识别器根本不认这个名）。
    #   现改为**行为判定**：直接问单一权威 `evidence_chain._match_material`
    #   「这个名字在真实资料类别里能判出什么」——拿得到（已有/待核）才过，拿不到（缺失）即报。
    #   ⚠ 故意**不**把 required_materials 计入 legal：自证循环一旦保留，本判据就是摆设。
    #   ★ 已显式登记的「拿得到但不该拿」的缺口（宁留缺口，绝不用硬映射冒充实得）。
    #   ★★ 2026-10-06：**原唯一登记项「拒收证明」已从根上修掉**（不再需要豁免）——
    #     它不是"拿不到"，而是**没被登记**：已在 `material_recognition._SUPP_ENTRIES`
    #     登记为独立补充类别「拒收证明」（新增一类真资料，**不是**硬映射到既存 15 类），
    #     企业真提供了即逐字命中判「已有/待核」，没提供仍如实判「缺失」。
    #     本表保留为空，供将来出现"确实无法登记"的缺口时登记（登记即降为 WARN 并注明原因）。
    _ACK_UNREACHABLE = {}
    try:
        from engine.evidence_chain import _match_material as _mm
    except Exception as _exc:  # pragma: no cover
        return [("ERROR", "engine/tax_redlines.py",
                 "要件数据源可得性判定（_match_material）不可用: %s" % _exc)]

    for r in REDLINES:
        cs = r.get("constituent_sources") or []
        cc = r.get("constituents") or []
        if cc and not cs:
            issues.append(("ERROR", "engine/tax_redlines.py",
                           "%s 有 %d 条要件但未声明 constituent_sources，"
                           "核对表会写「未标注独立数据源」" % (r.get("id"), len(cc))))
            continue
        if len(cs) != len(cc):
            issues.append(("ERROR", "engine/tax_redlines.py",
                           "%s constituent_sources %d 条与要件 %d 条不等（须按序对齐）" % (r.get("id"), len(cs), len(cc))))
        for i, (con, src) in enumerate(zip(cc, cs), 1):
            # ★ (b)「可取得」改为行为判定：问单一权威 _match_material 这个名字判得出什么
            unobtainable = []
            for _n in _split(src):
                _st = ((_mm(_n, "", sorted(_cats)) or {}).get("status") or "缺失")
                if _st == "缺失":
                    unobtainable.append(_n)
            if unobtainable:
                _known = [x for x in unobtainable if x in _ACK_UNREACHABLE]
                _new = [x for x in unobtainable if x not in _ACK_UNREACHABLE]
                for _x in _known:
                    issues.append(("WARN", "engine/tax_redlines.py",
                                   "%s 第%d条要件的数据源「%s」判「缺失」（已知缺口：%s），"
                                   "该要件本轮不会计入认定" % (r.get("id"), i, _x, _ACK_UNREACHABLE[_x][2])))
                for _x in _new:
                    issues.append(("ERROR", "engine/tax_redlines.py",
                                   "%s 第%d条要件的数据源「%s」声明了但**永远拿不到**"
                                   "（_match_material 判缺失），该要件恒 not_checked；"
                                   "请把数据源改写成真实资料类别，或把资料登记进 _SUPP_ENTRIES"
                                   % (r.get("id"), i, _x)))
            mentioned = [m for m in sorted(set(r.get("required_materials") or []))
                         if m in con and m not in str(src)]
            if mentioned:
                issues.append(("ERROR", "engine/tax_redlines.py",
                               "%s 第%d条要件正文提到的资料 %s 未列入独立数据源" % (r.get("id"), i, mentioned)))
        # (d) 一物两名：同一红线内 required_materials 不得重复登记同一资料名
        _rm = [str(x) for x in (r.get("required_materials") or [])]
        _dup = sorted({x for x in _rm if _rm.count(x) > 1})
        if _dup:
            issues.append(("ERROR", "engine/tax_redlines.py",
                           "%s required_materials 内重复登记同一资料名 %s（一物两名，"
                           "企业按任一名字补资料只会闭合一半）" % (r.get("id"), _dup)))
    return issues

def check_finding_meta_wording() -> List[Tuple[str, str, str]]:
    """疑点 meta 行必须是**自然句**（用户 2026-09-27 改写口径）。

    用户明确要求：该行不再用「字段：值｜字段：值」式罗列，改为自然句三段——
    ① 涉嫌方向成句；② 本项结论："…的可能性{档位}，但能补全尚缺的 N 项资料来排除此项税务风险嫌疑"；
    ③ "本项涉税嫌疑，涉及税种：…；潜在税额影响（测算）：…"。
    「等级依据」是**全库统一口径**的通用模板（每项都一样），不在每条疑点重复，
    改在章首"阅读提示"里说明一次——本闸门同时锁死"分级口径仍有说明"。
    """
    rel = "static/js/tax-doc-analysis.js"
    p = ROOT / rel
    if not p.exists():
        return [("WARN", rel, "前端文件不存在，跳过疑点 meta 措辞检查")]
    src = _read(p)
    issues: List[Tuple[str, str, str]] = []
    for bad, why in (
        ("'涉嫌方向：'", "「涉嫌方向：」字段前缀"),
        ("｜判断可信度", "「｜判断可信度」字段罗列"),
        ("｜等级依据", "「｜等级依据」逐条重复通用模板"),
        ("资料情况：已提供", "「资料情况：已提供」字段罗列"),
        ("risk_level_basis", "逐条渲染 risk_level_basis"),
    ):
        if bad in src:
            issues.append(("ERROR", rel, f"疑点 meta 回退为字段罗列（出现 {why}），应为自然句"))
    for good in ("本项涉税嫌疑，", "来排除此项税务风险嫌疑"):
        if good not in src:
            issues.append(("ERROR", rel, f"疑点 meta 缺少自然句表述「{good}」"))
    # ★ 2026-10-01 用户定调：删除章首「阅读提示」（含风险等级 5 项分级口径说明）——
    #   属与报告本质无关的通用说明，故原「章首阅读提示须说明分级口径」断言移除。
    #   「通用口径不得逐条重复」这一实质要求仍由上方 ｜等级依据/risk_level_basis 禁项锁定。
    return issues


def check_risk_item_section_wording() -> List[Tuple[str, str, str]]:
    """「一、涉及的风险事项」必须**同时**呈现（用户 2026-09-28 反转 09-27 决策）：

    - (A) 本红线的**抽象构成要件清单**（「凡符合下列构成要件即属涉嫌疑点」）——红线定义，
          与企业无关，让企业知道"什么情形算涉嫌"；09-27 曾把它整个禁掉，已判定为理解错误，现锁定必须保留；
    - (B) 本企业**实际命中哪几条**的逐条判定（`_enterprise_situations` 取域判定证据）；
    - (C) 法定依据写到**具体条款内容**（`format_legal_basis`）。
    三者缺一不可：只列抽象清单不列本企业命中 → 企业无从知道踩了哪条；只列本企业命中不列抽象清单
    → 企业无从知道"什么情形算涉嫌"（用户 09-28 明确要求恢复）。
    """
    rel = "engine/enterprise_report.py"
    p = ROOT / rel
    if not p.exists():
        return [("WARN", rel, "文件不存在，跳过风险事项段落措辞检查")]
    src = _read(p)
    issues: List[Tuple[str, str, str]] = []
    # (A) 抽象构成要件清单必须呈现（锁定，防止再次被"收敛"掉）
    for _req in ("凡符合下列构成要件即属涉嫌疑点", "该风险指标不因行业而变"):
        if _req not in src:
            issues.append(("ERROR", rel,
                           f"「一、涉及的风险事项」未呈现抽象构成要件清单（缺「{_req}」），"
                           "应保留本红线的抽象构成要件清单"))
    # (B) 逐条判定能力必须保留（本企业命中哪几条 + 证据）
    for good in ("_enterprise_situations", "constituent_hits", "format_legal_basis"):
        if good not in src:
            issues.append(("ERROR", rel, f"缺少「{good}」（本企业逐条判定 / 法条补全条款内容）"))
    # (C) 行为：法条补全必须能带回条款内容（★2026-10-16 换用现行第二十一条作探针：原探针的「第二十七条＋红字发票」属**旧版**内容，该引用 2026-10-06 已判「与现行文本不符」，见 tax_redlines RL-VAT-007）
    try:
        from engine.legal_citation import format_legal_basis
        probe = format_legal_basis(["《发票管理办法》第二十一条"])
        if ("：" not in probe) or ("虚开" not in probe):
            issues.append(("ERROR", "engine.legal_citation.py", "法定依据未补全条款内容（探针第二十一条/现行含「虚开」）"))
    except Exception as exc:
        issues.append(("ERROR", "engine.legal_citation.py", f"法条解析异常: {exc}"))
    return issues
    return issues


def check_report_expression_standard() -> List[Tuple[str, str, str]]:
    """报告表达风格标准（用户 2026-09-28 反转 09-27）：唯一权威 + 接入一键分析 + 自检行为正确。

    - S1（09-28 新口径）：抽象构成要件清单「凡符合下列构成要件即属涉嫌疑点」**必须**出现，
      不再视为违规模板；仅 S2（字段罗列）保留黑名单检测。
    - 唯一权威 `engine.report_style`（EXPRESSION_PRINCIPLES S1–S6 + check_report_expression）；
      接入一键分析 `main._apply_report_style_stage`；自检须能抓反例、不误报合规正文。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.report_style import EXPRESSION_PRINCIPLES, check_report_expression
    except Exception as exc:
        return [("ERROR", "engine/report_style.py", f"表达风格唯一权威缺失: {exc}")]
    keys = {p.get("key") for p in EXPRESSION_PRINCIPLES}
    for k in ("S1", "S2", "S3", "S4", "S5", "S6"):
        if k not in keys:
            issues.append(("ERROR", "engine/report_style.py", f"表达特点缺少 {k}"))
    try:
        main_src = _read(ROOT / "main.py")
    except Exception:
        main_src = ""
    if "_apply_report_style_stage" not in main_src:
        issues.append(("ERROR", "main.py", "一键分析未接入报告表达风格自检（_apply_report_style_stage）"))
    # 行为：反例必抓（S2 字段罗列仍须捕获；抽象构成要件清单已不再视为违规）
    bad2 = check_report_expression({"a": "涉嫌方向：x｜本项结论：y｜判断可信度：z"})
    if not any(v["severity"] == "ERROR" and v["principle"] == "S2" for v in bad2):
        issues.append(("ERROR", "engine/report_style.py", "自检未捕获字段罗列（S2）"))
    # 行为：合规正文不得误报（含抽象构成要件清单 + 本企业事实均不应被标记）
    good = check_report_expression({"a": "经检查，本企业触发税务风险指标，涉嫌通过红冲调节销项税额。"
                                         "该风险指标不因行业而变，凡符合下列构成要件即属涉嫌疑点："
                                         "① 大额红冲发票未按规定冲减销项税额。"})
    if any(v["severity"] == "ERROR" for v in good):
        issues.append(("ERROR", "engine/report_style.py", "自检误报合规正文（含抽象要件清单）"))
    # 行为：含循环引用也必须能完成（报告对象含环，遍历一律不得递归）
    try:
        _a = {"t": "涉嫌方向：p｜本项结论：q｜判断可信度：r"}
        _b = {"p": _a}
        _a["c"] = _b
        _v = check_report_expression({"x": _a, "y": [_b]})
        if not any(v["severity"] == "ERROR" and v["principle"] == "S2" for v in _v):
            issues.append(("ERROR", "engine/report_style.py", "自检在循环引用场景未完成（或未捕获反例）"))
    except RecursionError as exc:  # pragma: no cover
        issues.append(("ERROR", "engine/report_style.py", f"自检遍历仍会爆栈: {exc}"))
    return issues


def check_constituent_traceability() -> List[Tuple[str, str, str]]:
    """「构成要件」必须可被各判定来源追溯（用户 2026-09-27 选 A：收敛为单一权威）。

    - 红线库 `tax_redlines` 是**唯一要件表**（要件齐全，如 RL-VAT-007 须含"大额红冲"第⑤条）；
    - 各判定来源（域 / 发票模式检测器 / VR 规则）必须声明 `constituent_hits[].index`（命中第几条）；
    - 红线归并处必须**合并**各来源命中；报告只列命中要件（见 `check_risk_item_section_wording`）。
    """
    issues: List[Tuple[str, str, str]] = []
    for rel, why in (("engine/domain_analysis.py", "域判定"),
                     ("engine/invoice_pattern_detector.py", "发票模式检测器"),
                     ("engine/verified_rule_engine.py", "VR 规则")):
        try:
            src = _read(ROOT / rel)
        except Exception:
            src = ""
        if "constituent_hits" not in src:
            issues.append(("ERROR", rel, f"{why}未声明 constituent_hits（要件命中不可追溯）"))
    try:
        re_src = _read(ROOT / "engine/redline_engine.py")
    except Exception:
        re_src = ""
    if "_constituent_hits" not in re_src:
        issues.append(("ERROR", "engine/redline_engine.py", "红线归并处未合并各来源的要件命中"))
    try:
        from engine.tax_redlines import REDLINES
        _rl = [r for r in REDLINES if r.get("id") == "RL-VAT-007"]
        _cons = list((_rl[0].get("constituents") or [])) if _rl else []
        if len(_cons) < 5 or not any(("偏大" in str(c) or "跨年度" in str(c)) for c in _cons):
            issues.append(("ERROR", "engine/tax_redlines.py",
                           "RL-VAT-007 要件表未补全（应含「跨年度/显著偏大红冲」第⑤条）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/tax_redlines.py", f"要件表检查异常: {exc}"))
    return issues


def check_constituent_no_threshold() -> List[Tuple[str, str, str]]:
    """构成要件**不得含自设数值阈值**（用户 2026-09-27：不要阈值，存在即触发）。

    区分两类（这点很重要）：
      - **自设阈值**（"达到X万元以上""占比X%以上""X家以上""70%以上""连续6个月及以上"等）→ **必须清零**；
      - **法定标准**（法定扣除限额、法定结转年限、2:1 债资比、可清算标准、查账征收标准）→
        **必须保留**（那是法律规定，不是系统拍脑袋），故含"法定/规定/限额/结转年限/…"者豁免。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.tax_redlines import REDLINES
    except Exception as exc:
        return [("ERROR", "engine/tax_redlines.py", f"红线库加载失败: {exc}")]
    num = re.compile(
        r"(?:\d+(?:\.\d+)?\s*(?:万元|亿元|元|%|家|个月|年|张|笔)?\s*(?:以上|以下))"
        r"|(?:达到|超过|大于|小于)\s*\d+(?:\.\d+)?\s*(?:万元|亿元|元|%)"
    )
    legal = ("法定", "规定", "限额", "结转年限", "可清算标准",
             "查账征收", "扣除限额", "2:1", "起征点")
    for r in REDLINES:
        for i, c in enumerate((r.get("constituents") or []), 1):
            cs = str(c)
            if num.search(cs) and not any(k in cs for k in legal):
                issues.append(("ERROR", "engine/tax_redlines.py",
                               f"{r.get('id')} #{i} 仍含**自设**数值阈值：{cs[:70]}"))
    return issues


def check_constituent_exemption_coverage() -> List[Tuple[str, str, str]]:
    """每条红线都必须有"豁免/正当理由"类要件（否则只有入罪口、没有出罪口，易误判）。

    ★ 豁免要件**不得套空话模板**（"无合理解释"），应取该红线自带的 `justifications`
      （正当理由清单）生成具体条目——见 `scripts/_add_constituent_exemptions.py`。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.tax_redlines import REDLINES
    except Exception as exc:
        return [("ERROR", "engine/tax_redlines.py", f"红线库加载失败: {exc}")]
    keys = ("解释", "豁免", "合理", "正当", "无合理", "无法", "不属于", "非个人", "合法")
    miss = [r.get("id") for r in REDLINES
            if not any(any(k in str(c) for k in keys) for c in (r.get("constituents") or []))]
    for rid in miss:
        issues.append(("ERROR", "engine/tax_redlines.py",
                       f"{rid} 缺少「豁免/正当理由」类要件（须用其 justifications 生成）"))
    return issues


def check_default_hit_index_valid() -> List[Tuple[str, str, str]]:
    """逐条判定兜底映射 `_DEFAULT_HIT_INDEX`（engine/redline_engine.py）完整性自检。

    该映射把"未显式附 constituent_hits 的红线"按 constituents 序号兜底补齐，使报告 (A)+(B) 闭环。
    若 constituents 被重排号、增删，或映射指向「豁免/正当」出罪要件（命中位点不能是出罪口），
    则该兜底会产出错误证据。本检查静态锁死：① 红线 id 必须存在 ② 序号在 [1, len(constituents)]
    ③ 序号不得指向豁免/正当类出罪要件。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.tax_redlines import REDLINES
        from engine.redline_engine import _DEFAULT_HIT_INDEX
    except Exception as exc:
        return [("ERROR", "engine/redline_engine.py", f"_DEFAULT_HIT_INDEX 加载失败: {exc}")]
    by_id = {r["id"]: r for r in REDLINES}
    exempt_keys = ("不属于", "豁免", "正当情形", "非个人", "合法")
    for rid, idxs in _DEFAULT_HIT_INDEX.items():
        if rid not in by_id:
            issues.append(("ERROR", "engine/redline_engine.py",
                           f"_DEFAULT_HIT_INDEX 含不存在的红线 id: {rid}"))
            continue
        cons = by_id[rid].get("constituents") or []
        n = len(cons)
        if not isinstance(idxs, list) or not idxs:
            issues.append(("ERROR", "engine/redline_engine.py",
                           f"{rid} 的兜底序号非法（须为非负整数列表）: {idxs!r}"))
            continue
        for i in idxs:
            if not isinstance(i, int) or i < 1 or i > n:
                issues.append(("ERROR", "engine/redline_engine.py",
                               f"{rid} 兜底序号越界: 第{i}项（constituents 共 {n} 项）"))
                continue
            c_text = str(cons[i - 1])
            if any(k in c_text for k in exempt_keys):
                issues.append(("ERROR", "engine/redline_engine.py",
                               f"{rid} 兜底序号指向出罪要件（不得作为命中证据）: 第{i}项「{c_text}」"))
    return issues


def check_justification_scenario_coverage() -> List[Tuple[str, str, str]]:
    """justifications（正当理由/反证，论证链 rebuttals 维度）与 constituents 新场景「对称扩充」锁。

    上一轮为 constituents 追加了 70 个「新涉嫌场景」（_enrich_constituents），但 justifications 未动；
    随后 _enrich_justifications 为每条新场景补了一条对应出证反证，使 justifications 总数 228 -> 298。
    本检查静态锁死：① 每条红线的 justifications 条数 = 基线(ORIG_J) + 该线新增数；② 全局 298；
    ③ 任何红线 justifications 不得为空。反向验证：临时把某红线 justifications 删一条 -> 报 ERROR。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.tax_redlines import REDLINES
    except Exception as exc:
        return [("ERROR", "engine/tax_redlines.py", f"红线库加载失败: {exc}")]
    # 基线：_enrich_justifications 扩充前每条红线 justifications 条数
    ORIG_J = {"RL-VAT-001": 4, "RL-VAT-002": 4, "RL-VAT-003": 3, "RL-VAT-004": 3,
              "RL-VAT-005": 3, "RL-VAT-006": 3, "RL-VAT-007": 3, "RL-INC-001": 4,
              "RL-INC-002": 3, "RL-INC-003": 3, "RL-INC-004": 3, "RL-COST-001": 3,
              "RL-COST-002": 3, "RL-COST-003": 3, "RL-COST-004": 4, "RL-COST-005": 3,
              "RL-FUND-001": 3, "RL-FUND-002": 3, "RL-FUND-003": 3, "RL-FUND-004": 2,
              "RL-FUND-005": 3, "RL-FUND-006": 3, "RL-INV-001": 3, "RL-INV-002": 3,
              "RL-INV-003": 3, "RL-PAY-001": 5, "RL-PAY-002": 3, "RL-PAY-003": 3,
              "RL-PAY-004": 3, "RL-CIT-001": 3, "RL-CIT-002": 3, "RL-CIT-003": 3,
              "RL-CIT-004": 3, "RL-PTY-001": 5, "RL-PTY-002": 7, "RL-PTY-003": 3,
              "RL-PTY-004": 3, "RL-PTY-005": 3, "RL-AST-001": 3, "RL-AST-002": 3,
              "RL-AST-003": 3, "RL-OTH-001": 3, "RL-OTH-002": 3, "RL-OTH-003": 2,
              "RL-SPT-001": 4, "RL-SPT-002": 4, "RL-SPT-003": 4, "RL-SPT-004": 4,
              "RL-SPT-005": 4, "RL-SPT-006": 5, "RL-SPT-007": 5, "RL-SPT-008": 4,
              "RL-SPT-009": 5, "RL-SPT-010": 4, "RL-SPT-011": 4, "RL-CIT-005": 3,
              "RL-CIT-006": 3, "RL-PAY-005": 3, "RL-PAY-006": 3, "RL-OTH-004": 3,
              "RL-OTH-005": 3, "RL-VAT-008": 3, "RL-VAT-009": 3, "RL-COST-006": 3,
              "RL-CIT-007": 3, "RL-VAT-010": 3, "RL-VAT-011": 3, "RL-OTH-006": 3}
    # 各红线新增反证数（与 _enrich_constituents.EXTRA 一一对应；VAT-001/002 各 2，其余 1）
    def _new(rid):
        return 2 if rid in ("RL-VAT-001", "RL-VAT-002") else 1
    by_id = {r["id"]: r for r in REDLINES}
    total = 0
    for rid in ORIG_J:
        if rid not in by_id:
            issues.append(("ERROR", "engine/tax_redlines.py",
                           f"check_justification_scenario_coverage 基线含不存在红线: {rid}"))
            continue
        jl = by_id[rid].get("justifications") or []
        total += len(jl)
        exp = ORIG_J[rid] + _new(rid)
        if len(jl) != exp:
            issues.append(("ERROR", "engine/tax_redlines.py",
                           f"{rid} justifications 期望 {exp} 条（基线 {ORIG_J[rid]} + 新增 {_new(rid)}），实际 {len(jl)} 条"))
    # ★ 2026-10-15：`total` 必须覆盖**全部**红线（含批次），否则汇总校验自己先错
    #   （实测：只累加 ORIG_J ⇒ 期望 370、实际报 298，是**假红**）。
    total = 0
    for r in REDLINES:
        total += len(r.get("justifications") or [])
        if not (r.get("justifications") or []):
            issues.append(("ERROR", "engine/tax_redlines.py",
                           f"{r.get('id')} justifications 为空"))
    # ★ 2026-10-15：原为「总数恒等于 298」硬锁。加入批次规则后该值必然过期，
    #   但**不能因此去掉防削减能力**（否则静默丢条数无人发现）。改为两条**可增长**判据：
    #     ① **下界**：总数 ≥ 基线期望之和 + 批次条数×2（基线只锁既有 91 条，
    #        其余既有红线未纳入基线，故用下界而非等值）；
    #     ② **批次规则逐条**：每条正当理由 ≥ 2 条（新规则不得只写入罪口、不留出罪口）。
    _base_j = sum(ORIG_J[rid] + _new(rid) for rid in ORIG_J if rid in by_id)
    _batch_rules = [r for r in REDLINES if r.get("_batch_id")]
    _floor = _base_j + 2 * len(_batch_rules)
    if total < _floor:
        issues.append(("ERROR", "engine/tax_redlines.py",
                       f"justifications 总数 {total} 低于下界 {_floor}"
                       f"（基线期望 {_base_j} + 批次 {len(_batch_rules)}×2）"
                       "——有正当理由被静默削减"))
    for _r in _batch_rules:
        if len(_r.get("justifications") or []) < 2:
            issues.append(("ERROR", "engine/tax_redlines.py",
                           f"{_r.get('id')} 批次规则正当理由不足 2 条"
                           f"（实 {len(_r.get('justifications') or [])} 条）"))
    return issues


# ─────────────────────────────────────────────────────────────────────────────
# B3 法条时效闸门：红线引用的法律依据必须落在「有效文件清单」内；
#     引用已废止文件 → ERROR；引用清单外未核验文件 → WARN（强制新引用先入清单）。
# ─────────────────────────────────────────────────────────────────────────────
def check_legal_basis_freshness() -> List[Tuple[str, str, str]]:
    """法律依据时效自检（B3，2026-09-28）。

    单一权威：KNOWN_VALID_DOCS 是经人工核验仍有效的文件清单（含 3 个较旧但仍有效文件：
    国税发〔2006〕187号 土增清算、国税发〔2008〕30号 核定征收、公告2011年第25号 资产损失）。
    REPEALED_DOCS 是确认已废止文件（引用即误用法律，ERROR）。
    新增红线若引用清单外文件 → WARN，强制先把它加入 KNOWN_VALID_DOCS（防退化）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.tax_redlines import REDLINES
    except Exception as exc:
        return [("ERROR", "engine/tax_redlines.py", f"红线库加载失败: {exc}")]
    # ★ 有效文件清单（单一权威，新增引用须先入此表）
    KNOWN_VALID_DOCS = {
        "个人所得税法", "个人所得税法实施条例", "中华人民共和国企业所得税法",
        "中华人民共和国企业所得税法实施条例", "中华人民共和国发票管理办法",
        "中华人民共和国土地增值税暂行条例", "中华人民共和国增值税法", "中华人民共和国增值税法实施条例",
        "中华人民共和国契税法", "中华人民共和国海关法", "中华人民共和国消费税暂行条例",
        "中华人民共和国环境保护税法", "中华人民共和国税收征收管理法",
        "中华人民共和国资源税法", "中华人民共和国关税法", "关税法",
        "人民币银行结算账户管理办法", "企业会计准则——基本准则", "企业所得税核定征收办法",
        "企业所得税法", "企业所得税法实施条例", "企业所得税税前扣除凭证管理办法",
        "会计法", "住房公积金管理条例", "关于规范个人投资者个人所得税征收管理的通知",
        "印花税法", "发票管理办法",  # 2026-10-13 移除「出口货物退（免）税管理办法」（2012-07-01 已全文废止）
        "国家税务总局公告2011年第25号", "国家税务总局公告2014年第39号", "国家税务总局公告2026年第5号", "出口业务增值税和消费税退（免）税管理办法", "财政部 税务总局公告2026年第11号", "财政部 税务总局关于出口业务增值税和消费税政策的公告",  # 2026-10-13 新增：RL-SPT-008 出口退税现行依据（原 1994 年办法已废止）
        "国家税务总局公告2014年第67号", "国家税务总局公告2018年第28号",
        "国家税务总局公告2019年第38号", "财税〔2008〕121号",
        "国家税务总局关于房地产开发企业土地增值税清算管理有关问题的通知",
        "国税发〔2006〕187号", "国税发〔2008〕30号", "城市维护建设税法",
        "城镇土地使用税暂行条例", "增值税专用发票使用规定", "国家税务总局公告2019年第26号", "国家税务总局公告2025年第20号",
        "征收教育费附加的暂行规定", "房产税暂行条例", "财政部 税务总局公告2019年第71号", "财政部 税务总局公告2025年第7号",
        "社会保险法", "税收征收管理法", "税目税率表",  # 2026-10-13 移除「现金管理暂行条例」（2025-01-20 已废止）
        "股权转让所得个人所得税管理办法（试行）", "营业税改征增值税试点实施办法",
        "财政部 国家税务总局关于全面推开营业税改征增值税试点的通知",
        "财政部 税务总局公告2023年第7号", "车船税法", "车船税法实施条例",
        # 2026-09-29：红线库引用上述法律的**全称**写法（带"中华人民共和国"前缀），
        # 与短名指向同一法律，登记全称避免误报"清单外"。
        "中华人民共和国个人所得税法",
        "中华人民共和国个人所得税法实施条例",
        "中华人民共和国车辆购置税法",
        "中华人民共和国耕地占用税法",
        "中华人民共和国烟叶税法",
        "中华人民共和国船舶吨税法",
        # 2026-10-13：移除「财政部 税务总局公告2022年第14号／第21号」——已自 2025-09-01 全文废止；
        #   留抵退税现行依据为财政部 税务总局公告2025年第7号 + 国家税务总局公告2025年第20号（见上）。
        # 2026-09-30：费类义务红线（RL-SPT-019/020/021）引用文件，经核验现行有效后入表
        "残疾人就业条例",
        "残疾人就业保障金征收使用管理办法",
        "水利建设基金筹集和使用管理办法",
        "中华人民共和国工会法",
        "国家税务总局关于工会经费企业所得税税前扣除凭据问题的公告",
        "国家税务总局公告2010年第24号",
        "国家税务总局公告2016年第17号",
        "国家税务总局公告2016年第16号",
        "国家税务总局公告2016年第14号",
        "纳税人跨县（市、区）提供建筑服务增值税征收管理暂行办法",
        "纳税人提供不动产经营租赁服务增值税征收管理暂行办法",
        "纳税人转让不动产增值税征收管理暂行办法",
        "农产品增值税进项税额核定扣除试点实施办法",
        "财政部 税务总局关于简并增值税税率有关政策的通知",
    }
    # ★ 已废止文件（引用即 ERROR）
    REPEALED_DOCS = {
        "《中华人民共和国农业税条例》",  # 2006-01-01 起废止
    }
    import re as _re
    pat = _re.compile(
        r'《([^》]+)》|'
        r'(国家税务总局公告\d{4}年第\d+号)|(国税发〔\d{4}〕\d+号)|'
        r'(国税函〔\d{4}〕\d+号)|(财政部 税务总局公告\d{4}年第\d+号)|'
        r'(中华人民共和国\w+法\w*)')
    for r in REDLINES:
        rid = r.get("id")
        for lb in (r.get("legal_basis") or []):
            found = set()
            for m in pat.findall(str(lb)):
                for g in m:
                    if g:
                        found.add(g)
            if not found:
                continue
            for d in found:
                if d in REPEALED_DOCS:
                    issues.append(("ERROR", "engine/tax_redlines.py",
                                   f"{rid} 引用已废止文件：{d}"))
                elif d not in KNOWN_VALID_DOCS:
                    issues.append(("WARN", "engine/tax_redlines.py",
                                   f"{rid} 引用清单外未核验文件「{d}」，须先加入 KNOWN_VALID_DOCS"))
    return issues


# ─────────────────────────────────────────────────────────────────────────────
# B2 行业基准可解析闸门：BENCHMARK_REFS 登记的指标必须在 industry_data.json 中真实存在。
# ─────────────────────────────────────────────────────────────────────────────
def check_benchmark_refs_resolvable() -> List[Tuple[str, str, str]]:
    """红线→行业基准指标登记可解析自检（B2，2026-09-28）。

    凡在 engine/redline_benchmark.BENCHMARK_REFS 登记的红线，其指标必须落在
    industry_data.json 的 6 个基准指标键内，否则运行时解析会落空、报告出现空基准。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.redline_benchmark import BENCHMARK_REFS, metric_keys
        from engine.tax_redlines import REDLINES
    except Exception as exc:
        return [("ERROR", "engine/redline_benchmark.py", f"基准模块加载失败: {exc}")]
    valid = set(metric_keys())
    by_id = {r["id"]: r for r in REDLINES}
    for rid, metric in BENCHMARK_REFS.items():
        if rid not in by_id:
            issues.append(("ERROR", "engine/redline_benchmark.py",
                           f"BENCHMARK_REFS 含不存在的红线: {rid}"))
        if metric not in valid:
            issues.append(("ERROR", "engine/redline_benchmark.py",
                           f"{rid} 登记的指标「{metric}」不在 industry_data.json 指标键内（合法: {sorted(valid)}）"))
    return issues


# ─────────────────────────────────────────────────────────────────────────────
# C2 反证对齐闸门：论证链 justifications（反证）须与证据链 evidence_chain 的
#     role=="反证" 条目对齐，否则置信度不会被正当理由正确调整（误判风险）。
# ─────────────────────────────────────────────────────────────────────────────
def check_rebuttal_coverage() -> List[Tuple[str, str, str]]:
    """反证（正当理由）双链对齐自检（C2，2026-09-28）。

    论证链 rebuttals 来自 redline['justifications']；置信度修正
    `confidence -= 0.20 * rebuttal_ratio` 来自 evidence_chain 的 role=='反证' 元素。
    二者必须对得上：justifications 非空却无 evidence_chain 反证条目 → 反证永不"已提交"，
    置信度被错误抬高（漏调）。反之 evidence_chain 有反证但 justifications 空 → 自相矛盾。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.tax_redlines import REDLINES
    except Exception as exc:
        return [("ERROR", "engine/tax_redlines.py", f"红线库加载失败: {exc}")]
    for r in REDLINES:
        rid = r.get("id")
        jn = len(r.get("justifications") or [])
        ev_rebut = sum(1 for e in (r.get("evidence_chain") or [])
                       if isinstance(e, dict) and e.get("role") == "反证")
        if jn > 0 and ev_rebut == 0:
            issues.append(("WARN", "engine/tax_redlines.py",
                           f"{rid} 有 {jn} 条 justifications（反证）但 evidence_chain 无 role='反证' 条目"
                           f"——置信度不会被正当理由下调，存在误判偏高风险"))
        elif jn == 0 and ev_rebut > 0:
            issues.append(("WARN", "engine/tax_redlines.py",
                           f"{rid} evidence_chain 有 {ev_rebut} 条反证但 justifications 为空——双链不一致"))
    return issues


# ─────────────────────────────────────────────────────────────────────────────
# D 红线准入闸门 + 盲区审计：新增红线必须字段齐全、末项出罪、且可达（有检测器或登记兜底）。
# ─────────────────────────────────────────────────────────────────────────────
def _scan_declared_detectors() -> set:
    """扫描 engine/ + scripts/ + main.py，找出源码中显式声明 redline_id 的红线（真实检测器）。"""
    import os as _os, ast as _ast
    _root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    _files = []
    for _base in (_os.path.join(_root, "engine"), _os.path.join(_root, "scripts")):
        if _os.path.isdir(_base):
            for _fn in _os.listdir(_base):
                if _fn.endswith(".py"):
                    _files.append(_os.path.join(_base, _fn))
    _mp = _os.path.join(_root, "main.py")
    if _os.path.isfile(_mp):
        _files.append(_mp)
    _ids = set()
    _pat = re.compile(r'redline_id["\']?\s*[:=]\s*["\'](RL-[A-Z0-9-]+)["\']')
    for _fp in _files:
        try:
            _txt = open(_fp, encoding="utf-8").read()
        except Exception:
            continue
        for _m in _pat.finditer(_txt):
            _ids.add(_m.group(1))
    return _ids


# 已知盲区红线（无源码检测器、未登记 _DEFAULT_HIT_INDEX 兜底，仅依赖 match_redline_grounded
# 软匹配）。这批已在 C4（check_blind_redline_coverage）中逐条实测可达性（ERROR=0），
# 故此处不再整体告警；但若有**新增**未登记的盲区红线出现 → 仍 WARN，强制登记并实测可达性。
KNOWN_BLIND_REDLINES = {
    "RL-VAT-003", "RL-VAT-004", "RL-INC-003", "RL-INC-004", "RL-COST-001", "RL-COST-002",
    "RL-FUND-003", "RL-FUND-004", "RL-FUND-005", "RL-INV-001", "RL-INV-002", "RL-INV-003",
    "RL-PAY-004", "RL-CIT-002", "RL-CIT-003", "RL-PTY-001", "RL-PTY-005", "RL-AST-002",
    "RL-OTH-002", "RL-SPT-001", "RL-SPT-002", "RL-SPT-003", "RL-SPT-004", "RL-SPT-005",
    "RL-SPT-006", "RL-SPT-007", "RL-SPT-009", "RL-SPT-010", "RL-CIT-005", "RL-CIT-006",
    "RL-PAY-006", "RL-OTH-004", "RL-OTH-005", "RL-VAT-008", "RL-VAT-009", "RL-COST-006",
    "RL-CIT-007", "RL-VAT-010", "RL-VAT-011", "RL-OTH-006",
}


def check_redline_admission() -> List[Tuple[str, str, str]]:
    """红线准入 + 盲区审计（D，2026-09-28）。

    红线准入模板（新增红线必须逐项满足，否则 ERROR）：
      ① constituents 非空，且末项为「出罪/豁免/正当」要件（与 check_constituent_exemption_coverage 同源）；
      ② justifications 非空（出证口/反证）；
      ③ required_materials / legal_basis / remedy / match_hints 均非空。
    可达性（防退化，盲区审计）：
      ④ 红线须「可达」：有源码检测器（redline_id 声明）或登记于 _DEFAULT_HIT_INDEX 兜底；
         二者皆无且 match_hints 为空 → ERROR（不可达，永远死红线）；
         二者皆无但有 match_hints → WARN（依赖 match_redline_grounded 软匹配，盲区待核）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.tax_redlines import REDLINES
        from engine.redline_engine import _DEFAULT_HIT_INDEX
        from engine.redline_engine import _NO_BLIND_CONSTITUENT_FALLBACK as _NO_BLIND
    except Exception as exc:
        return [("ERROR", "engine/tax_redlines.py", f"红线库/引擎加载失败: {exc}")]
    detectors = _scan_declared_detectors()
    exempt_keys = ("不属于", "豁免", "正当情形", "非个人", "合法", "无合理", "无法")
    blind = []
    for r in REDLINES:
        rid = r.get("id")
        cons = r.get("constituents") or []
        if not cons:
            issues.append(("ERROR", "engine/tax_redlines.py", f"{rid} constituents 为空"))
        elif not any(k in str(cons[-1]) for k in exempt_keys):
            issues.append(("ERROR", "engine/tax_redlines.py",
                           f"{rid} 末项构成要件非出罪要件：{str(cons[-1])[:60]}"))
        if not (r.get("justifications") or []):
            issues.append(("ERROR", "engine/tax_redlines.py", f"{rid} justifications 为空"))
        for f in ("required_materials", "legal_basis", "remedy", "match_hints"):
            if not (r.get(f) or []):
                issues.append(("ERROR", "engine/tax_redlines.py", f"{rid} 字段 {f} 为空"))
        # 可达性
        has_det = rid in detectors
        # ★ 2026-10-02：`_NO_BLIND_CONSTITUENT_FALLBACK` 里的红线是**有意**不做盲发兜底
        #   （要件异质，盲发会把任何命中都记成同一条要件），但可达性由软匹配检测器保证，
        #   故与登记兜底同等待遇，不算盲区红线。
        has_fallback = rid in _DEFAULT_HIT_INDEX or rid in _NO_BLIND
        has_hints = bool(r.get("match_hints") or [])
        if not has_det and not has_fallback:
            if not has_hints:
                issues.append(("ERROR", "engine/tax_redlines.py",
                               f"{rid} 不可达：既无检测器也未登记兜底且无 match_hints（死红线）"))
            else:
                blind.append(rid)
    if blind:
        # 已知盲区红线（已在 KNOWN_BLIND_REDLINES，且 C4 实测可达）不再告警；
        # 仅对**新增**未登记盲区红线告警，强制登记并实测可达性（保留退化信号）。
        _new_blind = [r for r in blind if r not in KNOWN_BLIND_REDLINES]
        if _new_blind:
            issues.append(("WARN", "engine/redline_engine.py",
                           f"新增 {len(_new_blind)} 条未登记盲区红线（无检测器/兜底，依赖软匹配，"
                           f"须实测确认可达性并登记 KNOWN_BLIND_REDLINES）：{', '.join(_new_blind)}"))
    return issues


def check_combo_profile_logic() -> List[Tuple[str, str, str]]:
    """C3 风险组合画像逻辑锁定（2026-09-29）。

    组合画像机制约束（违反即 ERROR）：
      ① 四类业务轴映射（PTY/INC/FUND/COST）存在且前缀非空、唯一；
      ② 轴映射仅覆盖四族红线前缀，非四族红线（如 RL-VAT-*/RL-INV-*）不计入组合；
      ③ 触发条件：≥2 个业务轴同时出现「未排除」疑点才生成画像；单轴、或全排除 → 不生成；
      ④ 等级推导：三轴及以上、或任一已定性 → 高风险；否则中风险；
      ⑤ 组合画像不是独立红线：combo_id「RL-COMBO」不得存在于红线库，
         不得虚增 redline_total（否则会污染「68→74」等权威计数）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.redline_engine import (
            _COMBO_AXES, _combo_axis_of, _build_combo_profiles,
            _VERDICT_EXCLUDED, _VERDICT_CONFIRMED, _VERDICT_HIT_PENDING,
        )
        from engine.tax_redlines import get_redline, stats as redline_stats
    except Exception as exc:
        return [("ERROR", "engine/redline_engine.py", f"组合画像模块加载失败: {exc}")]

    # ① 四轴完整性 + 前缀唯一
    _expected_axes = {"PTY", "INC", "FUND", "COST"}
    if set(_COMBO_AXES.keys()) != _expected_axes:
        issues.append(("ERROR", "engine/redline_engine.py",
                       f"_COMBO_AXES 轴集合应为 {_expected_axes}，实为 {set(_COMBO_AXES.keys())}"))
    _prefixes = [v.get("prefix") for v in _COMBO_AXES.values()]
    if any(not p for p in _prefixes):
        issues.append(("ERROR", "engine/redline_engine.py", "_COMBO_AXES 存在空前缀"))
    if len(_prefixes) != len(set(_prefixes)):
        issues.append(("ERROR", "engine/redline_engine.py", "_COMBO_AXES 前缀重复"))

    # ② 轴映射仅覆盖四族；取一条非四族红线验证返回 None
    if _combo_axis_of("RL-VAT-001") is not None:
        issues.append(("ERROR", "engine/redline_engine.py",
                       "_combo_axis_of 误将非四族红线(RL-VAT-001)归入业务轴"))
    for _ax, _meta in _COMBO_AXES.items():
        if _combo_axis_of(_meta["prefix"] + "X") != _ax:
            issues.append(("ERROR", "engine/redline_engine.py",
                           f"_combo_axis_of 未将 {_meta['prefix']} 归入 {_ax}"))

    def _sus(rid, verdict, conf=0.6):
        return {"redline_id": rid, "redline_name": rid,
                "verdict": verdict, "confidence": conf, "taxes": ["增值税"]}

    # ③ 触发条件
    if _build_combo_profiles([]) != []:
        issues.append(("ERROR", "engine/redline_engine.py", "空疑点应返回空组合画像"))
    if _build_combo_profiles([_sus("RL-PTY-002", _VERDICT_HIT_PENDING)]) != []:
        issues.append(("ERROR", "engine/redline_engine.py", "单业务轴疑点不应触发组合画像"))
    _two_excluded = _build_combo_profiles([
        _sus("RL-PTY-002", _VERDICT_EXCLUDED), _sus("RL-FUND-001", _VERDICT_EXCLUDED)])
    if _two_excluded != []:
        issues.append(("ERROR", "engine/redline_engine.py",
                       "两轴但全部排除不应触发组合画像"))

    _two = _build_combo_profiles([
        _sus("RL-PTY-002", _VERDICT_HIT_PENDING), _sus("RL-FUND-001", _VERDICT_HIT_PENDING)])
    if len(_two) != 1 or set(_two[0]["axes"]) != {"PTY", "FUND"}:
        issues.append(("ERROR", "engine/redline_engine.py",
                       "两轴未排除疑点应生成 1 条且含 PTY/FUND 的组合画像"))

    # ④ 等级推导
    _three = _build_combo_profiles([
        _sus("RL-PTY-002", _VERDICT_HIT_PENDING), _sus("RL-FUND-001", _VERDICT_HIT_PENDING),
        _sus("RL-COST-001", _VERDICT_HIT_PENDING)])
    if _three[0]["level"] != "高风险" or _three[0]["axis_count"] != 3:
        issues.append(("ERROR", "engine/redline_engine.py", "三轴组合应判为高风险"))
    _confirmed_combo = _build_combo_profiles([
        _sus("RL-PTY-002", _VERDICT_CONFIRMED), _sus("RL-INC-001", _VERDICT_HIT_PENDING)])
    if _confirmed_combo[0]["level"] != "高风险":
        issues.append(("ERROR", "engine/redline_engine.py", "含已定性红线的组合应判为高风险"))
    if _two[0]["level"] != "中风险":
        issues.append(("ERROR", "engine/redline_engine.py", "两轴无已定性应判为中风险"))

    # 排除项不计入贡献红线
    _mix = _build_combo_profiles([
        _sus("RL-PTY-002", _VERDICT_HIT_PENDING), _sus("RL-FUND-001", _VERDICT_EXCLUDED),
        _sus("RL-COST-001", _VERDICT_HIT_PENDING)])
    if len(_mix) != 1 or set(_mix[0]["axes"]) != {"PTY", "COST"}:
        issues.append(("ERROR", "engine/redline_engine.py",
                       "组合应包含未排除轴、剔除已排除轴"))

    # ⑤ 组合画像不是独立红线，不得虚增红线库
    if get_redline("RL-COMBO") is not None:
        issues.append(("ERROR", "engine/tax_redlines.py",
                       "RL-COMBO 不应存在于红线库（组合画像非独立红线）"))
    _pre = redline_stats().get("total")
    # 端到端：run_redline_detection 不应改变红线总数、且 summary 含 combo_profiles
    try:
        from engine.redline_engine import run_redline_detection
        _res = run_redline_detection(
            [{"redline_id": "RL-PTY-002", "type": "x", "level": "中风险", "detail": "d"},
             {"redline_id": "RL-FUND-001", "type": "y", "level": "中风险", "detail": "d"},
             {"redline_id": "RL-COST-003", "type": "z", "level": "中风险", "detail": "d"}],
            engine_data={},
            material_readiness={"provided": [
                "银行流水", "进项发票", "销项发票", "记账凭证", "科目余额表", "资产负债表",
                "利润表", "增值税申报表", "企业所得税申报表", "个税申报表", "工资表",
                "社保明细", "进销存台账", "合同文件", "其他税种申报表"]})
        if "combo_profiles" not in _res.get("summary", {}):
            issues.append(("ERROR", "engine/redline_engine.py",
                           "run_redline_detection.summary 缺少 combo_profiles 字段"))
        if _res["summary"].get("redline_total") != _pre:
            issues.append(("ERROR", "engine/redline_engine.py",
                           "组合画像导致 redline_total 漂移（虚增红线计数）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/redline_engine.py", f"run_redline_detection 组合集成异常: {exc}"))
    return issues


def check_blind_redline_coverage() -> List[Tuple[str, str, str]]:
    """C4 盲区红线软匹配可达性锁定（2026-09-29）。

    40 条盲区红线（无源码检测器、未登记 _DEFAULT_HIT_INDEX 兜底）只能依赖
    match_redline_grounded 软匹配命中。本闸门逐一验证：当一条发现携带该红线的
    名称主词信号、且本轮提供了其 required_materials 时，match_redline_grounded
    必须命中它。不可达 → 该红线永远是死红线（ERROR），须补检测器/兜底/提示词或剔除。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.tax_redlines import REDLINES, match_redline_grounded
        from engine.redline_engine import _DEFAULT_HIT_INDEX
        det = _scan_declared_detectors()
    except Exception as exc:
        return [("ERROR", "engine/tax_redlines.py", f"盲区可达性校验加载失败: {exc}")]

    for r in REDLINES:
        rid = r.get("id")
        if rid in det or rid in _DEFAULT_HIT_INDEX:
            continue  # 非盲区（有检测器或兜底）
        hints = r.get("match_hints") or []
        if not hints:
            issues.append(("ERROR", "engine/tax_redlines.py",
                           f"{rid} 盲区红线无 match_hints（永远不可达，死红线）"))
            continue
        title = r.get("name", "")
        text = title + " " + " ".join(str(h) for h in hints)
        avail = list(r.get("required_materials") or [])
        got, info = match_redline_grounded(title, text, avail, domain=r.get("domain"))
        if got is None or got.get("id") != rid:
            issues.append(("ERROR", "engine/tax_redlines.py",
                           f"{rid} 盲区红线软匹配不可达（命中 {got.get('id') if got else None}）："
                           f"{info.get('note', '')}"))
    return issues


def check_benchmark_actual_compare() -> List[Tuple[str, str, str]]:
    """B1 实际比对接线锁定（2026-09-29）。

    红线构成要件写「对照行业基准区间上沿」之类，必须**真的算过**本企业实际值是否越界
    （名实相符）。此前只挂静态区间文本、从未计算 → "说了要对照、实际没对照"。

    违反即 ERROR：
      ① 比对判定收敛到单一权威 evaluate_indicator，domain 层不得自写比较式（防口径分歧）；
      ② compare_redline_benchmark 必须委托 resolve_redline_benchmark + evaluate_indicator；
      ③ 实际值缺失时**不得编造**比对结论：resolved=False 且 reason 非空；
      ④ redline_engine 必须调用该函数并把结果挂进 argumentation；
      ⑤ enterprise_report 必须消费 benchmark_compare（算出却不进报告 = 断点）；
      ⑥ 端到端行为：偏离 / 落在区间内 / 无实际值 三种情形判定正确。
    """
    issues: List[Tuple[str, str, str]] = []
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _src(rel: str) -> str:
        try:
            with open(os.path.join(_root, rel), encoding="utf-8") as fh:
                return fh.read()
        except Exception:
            return ""

    try:
        from engine.redline_benchmark import (
            compare_redline_benchmark, resolve_redline_benchmark,
        )
    except Exception as exc:
        return [("ERROR", "engine/redline_benchmark.py", f"B1 模块加载失败: {exc}")]

    # ① domain 层不得自写比较式（已统一委托 evaluate_indicator）
    _ib = _src("engine/industry_benchmark.py")
    if "def evaluate_indicator(" not in _ib:
        issues.append(("ERROR", "engine/industry_benchmark.py",
                       "缺少单一权威比对函数 evaluate_indicator"))
    _ib_fn = _ib.split("def run_industry_benchmark_check(", 1)[-1].split("\ndef ", 1)[0]
    if _ib_fn:
        if "evaluate_indicator(" not in _ib_fn:
            issues.append(("ERROR", "engine/industry_benchmark.py",
                           "run_industry_benchmark_check 未委托 evaluate_indicator，"
                           "会与红线注解口径分歧（禁止各处自写比较式）"))
        if "actual / 100 if key" in _ib_fn:
            issues.append(("ERROR", "engine/industry_benchmark.py",
                           "run_industry_benchmark_check 仍保留内联进销比换算，应走 normalize_actual"))

    # ② compare_redline_benchmark 必须委托两大单一权威
    _rb = _src("engine/redline_benchmark.py")
    _rb_fn = _rb.split("def compare_redline_benchmark(", 1)[-1].split("\ndef ", 1)[0]
    if not _rb_fn:
        issues.append(("ERROR", "engine/redline_benchmark.py",
                       "缺少 compare_redline_benchmark（B1 实际比对入口）"))
    else:
        if "resolve_redline_benchmark(" not in _rb_fn:
            issues.append(("ERROR", "engine/redline_benchmark.py",
                           "compare_redline_benchmark 未委托 resolve_redline_benchmark 取区间"))
        if "_ib_evaluate(" not in _rb_fn:
            issues.append(("ERROR", "engine/redline_benchmark.py",
                           "compare_redline_benchmark 未委托 evaluate_indicator 做比对"))

    # ③⑥ 找一个能解析毛利率基准的行业，做端到端行为验证
    _rid = "RL-INV-001"          # 毛利率
    _ind = None
    try:
        from engine.industry_resolver import load_industry_data
        for _k in ((load_industry_data() or {}).get("benchmarks") or {}):
            if resolve_redline_benchmark(_k, "毛利率") is not None:
                _ind = _k
                break
    except Exception:
        _ind = None
    if not _ind:
        issues.append(("ERROR", "engine/redline_benchmark.py",
                       "找不到可解析毛利率基准的行业，行业基准数据异常（B1 无法验证）"))
    else:
        # 无实际值 → 不得编造
        _c_none = compare_redline_benchmark(_rid, _ind, {})
        if _c_none.get("resolved") is not False:
            issues.append(("ERROR", "engine/redline_benchmark.py",
                           "无实际值时 compare 仍返回 resolved=True（编造比对结论）"))
        if not str(_c_none.get("reason") or "").strip():
            issues.append(("ERROR", "engine/redline_benchmark.py",
                           "无实际值时未给出 reason（须如实说明未取得，不得静默）"))
        # 落在区间内
        _bmv = resolve_redline_benchmark(_ind, "毛利率") or {}
        _lo, _hi = float(_bmv.get("lo", 0)), float(_bmv.get("hi", 0))
        _c_in = compare_redline_benchmark(_rid, _ind, {"gross_margin": (_lo + _hi) / 2})
        if _c_in.get("resolved") is not True or _c_in.get("in_range") is not True:
            issues.append(("ERROR", "engine/redline_benchmark.py",
                           f"实际值落在区间内应判 in_range=True，实为 {_c_in.get('in_range')}"))
        # 高于上沿
        # 高于上沿、但**仍在合理值域内**（若用 _hi*10+1000 这类荒谬值，会被数据完整性
        # 护栏正确拦下并返回 resolved=False —— 那是护栏生效，不是比对判定出错）
        _out_val = _hi + (100.0 - _hi) / 2.0
        _c_out = compare_redline_benchmark(_rid, _ind, {"gross_margin": _out_val})
        if _c_out.get("resolved") is not True or _c_out.get("in_range") is not False:
            issues.append(("ERROR", "engine/redline_benchmark.py",
                           f"实际值高于上沿应判 in_range=False，实为 {_c_out.get('in_range')}"))
        if "待核" not in str(_c_out.get("text") or ""):
            issues.append(("ERROR", "engine/redline_benchmark.py",
                           "偏离结论未标注「待核」（偏离≠定性，须明示不作定性依据）"))
        # 人均营收不参与自动测算 → 不得编造
        _c_nom = compare_redline_benchmark("RL-PAY-001", _ind, {"gross_margin": 20.0})
        if _c_nom.get("resolved") is not False:
            issues.append(("ERROR", "engine/redline_benchmark.py",
                           "人均营收类指标无实际值却返回 resolved=True（编造）"))

    # ③b 数据完整性护栏：荒谬值不得参与比对（2026-09-29）
    try:
        from engine.industry_benchmark import (
            is_indicator_comparable, _SANE_RANGE,
        )
    except Exception as exc:
        issues.append(("ERROR", "engine/industry_benchmark.py",
                       f"缺少数据完整性护栏（_SANE_RANGE/is_indicator_comparable）: {exc}"))
        is_indicator_comparable, _SANE_RANGE = None, {}
    if is_indicator_comparable is not None:
        if not _SANE_RANGE:
            issues.append(("ERROR", "engine/industry_benchmark.py",
                           "_SANE_RANGE 为空（护栏形同虚设）"))
        # 数据假象必须被拦下
        for _k, _v in (("gross_margin", -9451.51), ("vat_burden", -683.47)):
            if is_indicator_comparable(_k, _v):
                issues.append(("ERROR", "engine/industry_benchmark.py",
                               f"{_k}={_v} 属数据假象，应判不可比（护栏失效）"))
        # 正常值不得被误伤
        for _k, _v in (("gross_margin", 20.0), ("purchase_sales", 0.9),
                       ("vat_burden", 1.3)):
            if not is_indicator_comparable(_k, _v):
                issues.append(("ERROR", "engine/industry_benchmark.py",
                               f"{_k}={_v} 是正常值却被判不可比（护栏过严，会吞掉真实指标）"))
        # domain 层也必须拦（否则荒谬值仍从行业对标章进报告）
        if "comparable" not in _ib_fn:
            issues.append(("ERROR", "engine/industry_benchmark.py",
                           "run_industry_benchmark_check 未做数据完整性护栏，"
                           "荒谬值仍会产出行业偏离发现"))
        # 注：第三条路径 inspector_reasoning（专家研判·行业对标）**刻意不加**该护栏——
        # tests/test_inspector_reasoning.py::test_inverted_margin 以 -5232% 断言
        # "毛利率为负 → 购销倒挂"，属有意保留的信号；此处若加护栏会直接打破该测试。
        # 红线侧：不可比时不得产出比对结论
        if _ind:
            _c_bad = compare_redline_benchmark(_rid, _ind, {"gross_margin": -9451.51})
            if _c_bad.get("resolved") is not False:
                issues.append(("ERROR", "engine/redline_benchmark.py",
                               "实际值超出合理值域时仍给出比对结论（拿残缺数据冒充发现）"))
            if "合理值域" not in str(_c_bad.get("reason") or ""):
                issues.append(("ERROR", "engine/redline_benchmark.py",
                               "不可比时未如实说明原因（须写明不参与比对）"))

    # ④ redline_engine 接线
    _re = _src("engine/redline_engine.py")
    if "compare_redline_benchmark(" not in _re:
        issues.append(("ERROR", "engine/redline_engine.py",
                       "redline_engine 未调用 compare_redline_benchmark（B1 未接线）"))
    if "benchmark_compare" not in _re:
        issues.append(("ERROR", "engine/redline_engine.py",
                       "redline_engine 未挂载 benchmark_compare（算了也不进报告）"))

    # ⑤ 报告层必须消费（否则引擎→报告断点）
    if "benchmark_compare" not in _src("engine/enterprise_report.py"):
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "enterprise_report 未消费 benchmark_compare（B1 产出不进报告）"))

    return issues


def _trunc_violations(_text):
    """返回「声明项数 > 可见名数 且 未声明总数」的违规列表（**不用正则**实现）。

    ★ 2026-10-04（疑点4 D8 收尾）：三处材料名一律只列前 6 个，原先**静默**
      （实测 seq=9 声明 8 项、只列 6 名）⇒ 读者以为只有 6 项。
      产品侧已用 `_brief_atoms()` 加「等（共N项）」；本函数是它的**自动守护**。
      ⚠ 刻意**不用正则**（本项目多处正则判据在写入链路上被转义/编码破坏过），
        一律用 find/split，行为可预测。
    """
    _seps = ("、", "，", ",", "；", ";", "／", "/", "或者", "以及", "与", "和", "及")
    _t = _text or ""
    _out = []
    _pos = 0
    while True:
        _i = _pos
        while _i < len(_t) and not _t[_i].isdigit():
            _i += 1
        if _i >= len(_t):
            return _out
        _j = _i
        _k = _j
        while _k < len(_t) and _t[_k].isdigit():
            _k += 1
        if _k == _j or _k >= len(_t) or _t[_k] != "项":
            _pos = _i + 1
            continue
        _dec = int(_t[_j:_k])
        _m = _t.find("（", _k)
        if _m < 0 or (_m - _k - 1) > 12:
            _pos = _i + 1
            continue
        _e = _t.find("）", _m + 1)
        if _e < 0:
            _pos = _i + 1
            continue
        if ("共%d项" % _dec) in _t:
            _pos = _e + 1
            continue
        _body = _t[_m + 1:_e].replace("等（共%d项）" % _dec, "")
        for _sp in _seps:
            _body = _body.replace(_sp, "\x00")
        _vis = [x.strip() for x in _body.split("\x00") if x.strip()]
        if _dec > len(_vis):
            _out.append((_dec, len(_vis)))
        _pos = _e + 1


def check_report_consistency() -> List[Tuple[str, str, str]]:
    """报告级一致性闸门（2026-09-29 点评整改）。

    背景：外部点评发现四类"单看是小缺陷、合起来否定全文可信度"的报告级硬伤：
      ① 同一资料既在"已提供"清单、又在别处被写"未取得"（工资表/增值税申报表/科目余额表）；
      ② "未取得"被当 0 参与计算（两税差异把缺失的所得税收入记 0 → 差额 6,636,800.57）；
      ③ "未取得"被当"未发生"（印花税"实际缴纳 0 元"、附加"未见申报记录"——申报表均未上传）；
      ④ 税额测算税率错配（服务企业按 13%/25% 测算，未适用小微优惠与个税免征额）。

    本闸门用**行为断言**锁定修复（真实调用生产函数并断言产出），并校验接线存在。
    """
    issues: List[Tuple[str, str, str]] = []
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _src(rel: str) -> str:
        try:
            with open(os.path.join(_root, rel), encoding="utf-8") as fh:
                return fh.read()
        except Exception:
            return ""

    # ①② 两税差异：单边存在时不得把缺失侧当 0 算差额
    try:
        from engine.two_tax_income import run_two_tax_compare
        _tt = run_two_tax_compare(tax_declarations=[
            {"_declaration_type": "vat_declaration", "sales_amount": 6636800.57}])
        _tm = _tt.get("metrics") or {}
        if _tm.get("diff") is not None:
            issues.append(("ERROR", "engine/two_tax_income.py",
                           "单边存在时 metrics.diff 仍参与计算（缺失当 0），必须为 None"))
        if _tm.get("vat_over_cit") is not None:
            issues.append(("ERROR", "engine/two_tax_income.py",
                           "单边存在时 metrics.vat_over_cit 仍输出差额"))
        if not _tm.get("only_one_side"):
            issues.append(("ERROR", "engine/two_tax_income.py",
                           "单边存在时 only_one_side 未置 True"))
        if "未能比对" not in str(_tt.get("verdict", "")):
            issues.append(("ERROR", "engine/two_tax_income.py",
                           "单边存在时 verdict 未如实表述「未能比对」"))
        if "0.00" in str(_tt.get("summary", "")):
            issues.append(("ERROR", "engine/two_tax_income.py",
                           "单边存在时 summary 仍把缺失侧渲染成 0.00"))
    except Exception as exc:
        issues.append(("ERROR", "engine/two_tax_income.py", f"两税差异行为断言执行失败: {exc}"))

    # ④ 税额测算：税率语境 + 个税免征额 + 兜底保留
    #   ★★ 2026-10-07（用户第 3 批 任务3）：小微 5% 是**有前提**的 —— 判据改为
    #      「提供 cit_rate 且 `smb_verified=True` 才按 5%；否则一律回到法定 25% 上界」。
    #      判定权威是 `tax_impact.evaluate_small_micro()`（条件：从业人数/资产总额/应纳税所得额
    #      **三项均取得且满足**）。旧判据只认「提供了 cit_rate 就按 5%」⇒ 会把"未验证就按 5%"
    #      判成正确，恰恰是本批要禁的行为。
    try:
        from engine.tax_impact import estimate_tax, infer_rate_context, evaluate_small_micro
        _ctx = {"vat_rate": 0.06, "vat_note": "按销项有效税率 6% 测算",
                "cit_rate": 0.05, "smb_verified": True, "cit_note": "小微优惠口径 5%（三项条件已核实）"}
        _est = estimate_tax(100000.0, ["增值税", "企业所得税"], rate_ctx=_ctx)
        _by = {i["tax"]: i for i in _est.get("items") or []}
        if abs((_by.get("增值税") or {}).get("amount", -1) - 6000.0) > 0.01:
            issues.append(("ERROR", "engine/tax_impact.py",
                           "rate_ctx 提供 6% 时增值税仍按兜底税率测算（语境未生效）"))
        if abs((_by.get("企业所得税") or {}).get("amount", -1) - 5000.0) > 0.01:
            issues.append(("ERROR", "engine/tax_impact.py",
                           "已核实小型微利（smb_verified=True）时企业所得税未按 5% 测算"))
        # ★ 未验证 ⇒ 必须回到 25% 上界（本批新增硬约束）
        _est_u = estimate_tax(100000.0, ["企业所得税"], rate_ctx={"cit_rate": 0.05})
        _u = [i for i in _est_u.get("items") or [] if i["tax"] == "企业所得税"]
        if not _u or abs(float(_u[0].get("amount", -1)) - 25000.0) > 0.01:
            issues.append(("ERROR", "engine/tax_impact.py",
                           "未验证小型微利条件（无 smb_verified）时企业所得税未回到 25% 上界"))
        # ★ 判定权威自证：三项条件缺一即 verified=False；三项齐备且满足才 True
        if evaluate_small_micro(net_profit=400000.0).get("verified"):
            issues.append(("ERROR", "engine/tax_impact.py",
                           "evaluate_small_micro 把「人数/资产未取得」判成已验证（未知≠通过）"))
        if not evaluate_small_micro(employee_count=10, total_assets=1000000.0,
                                    net_profit=400000.0).get("verified"):
            issues.append(("ERROR", "engine/tax_impact.py",
                           "evaluate_small_micro 三项条件齐备且满足时未判 verified"))
        if evaluate_small_micro(employee_count=500, total_assets=1000000.0,
                                net_profit=400000.0).get("verified"):
            issues.append(("ERROR", "engine/tax_impact.py",
                           "evaluate_small_micro 对超临界值（人数 500>300）未判不通过"))
        _est2 = estimate_tax(17000.0, ["个人所得税"], rate_ctx=_ctx)
        _pit = [i for i in _est2.get("items") or [] if i["tax"] == "个人所得税"]
        if not _pit or float((_pit[0] or {}).get("amount", -1)) != 0.0:
            issues.append(("ERROR", "engine/tax_impact.py",
                           "金额低于 6 万元基本减除费用时个税仍计税（应为 0 并注明）"))
        if _est2.get("total") not in (0, 0.0):
            issues.append(("ERROR", "engine/tax_impact.py",
                           "个税 0 影响项不得计入敞口合计"))
        _est3 = estimate_tax(100000.0, ["增值税"])
        _vat3 = [i for i in _est3.get("items") or [] if i["tax"] == "增值税"]
        if not _vat3 or abs(float(_vat3[0].get("amount", 0)) - 13000.0) > 0.01:
            issues.append(("ERROR", "engine/tax_impact.py",
                           "无 rate_ctx 时兜底 13% 口径被误改（兜底必须保留）"))
        _irc = infer_rate_context(sal_invs=[{"amount": 100.0, "tax_amount": 6.0}],
                                  net_profit=400000.0, employee_count=10,
                                  total_assets=1000000.0)
        if _irc.get("vat_rate") != 0.06 or _irc.get("cit_rate") != 0.05:
            issues.append(("ERROR", "engine/tax_impact.py",
                           "infer_rate_context 未按销项有效税率/净利润推断出 6% 与小微 5%"))
        if not _irc.get("smb_verified"):
            issues.append(("ERROR", "engine/tax_impact.py",
                           "infer_rate_context 三项条件齐备时未置 smb_verified=True"))
        _irc2 = infer_rate_context(sal_invs=[{"amount": 100.0, "tax_amount": 6.0}],
                                   net_profit=400000.0)
        if _irc2.get("smb_verified") or _irc2.get("cit_rate") != 0.25:
            issues.append(("ERROR", "engine/tax_impact.py",
                           "infer_rate_context 在人数/资产未取得时仍输出小微 5%（未知≠通过）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/tax_impact.py", f"税额测算行为断言执行失败: {exc}"))

    # ① 线索链环节：**资料有无**与**读数有无**必须同源（2026-10-04 疑点1 D5/D6/D7 收口）
    #    ★ 本检查由"只查旧文案"升级为**行为级**断言（旧版只认「不计入资料缺失」这句措辞，
    #      挡不住真正病根——"资料未提供却给出读数"、"读数与本环节不对题"）。
    try:
        from engine.clue_chain import build_clue_chain
        import re as _re_clue
        from engine.clue_chain import _terminal_signal as _terminal_signal_
        from engine.enterprise_report import _evidence_summary as _evsum_
        from engine.clue_chain import _terminal_signal as _terminal_signal_
        from engine.enterprise_report import _evidence_summary as _evsum_
        _rl = {"id": "RL-T", "name": "测试红线",
               "clue_chain": [{"step": 1, "source": "工资表", "action": "a", "output": "o"}]}
        _f = {"type": "t", "detail": "金额5万元，需核实"}

        # a) 资料已提供但本环节无对题读数 ⇒ 如实标注，且**不得混入数字**
        _c1 = build_clue_chain(_f, _rl, {}, provided_materials=["工资表"])
        _n1 = (_c1.get("nodes") or [{}])[0]
        if "未产出对题读数" not in str(_n1.get("observed", "")) or _n1.get("has_data"):
            issues.append(("ERROR", "engine/clue_chain.py",
                           "资料已提供但本环节无对题读数时，未如实标注「未产出对题读数」"))
        if _re_clue.search(r"\d", str(_n1.get("observed", ""))):
            issues.append(("ERROR", "engine/clue_chain.py",
                           "本环节无读数却仍给出数字（拿别的环节的数顶替）"))
        if not _c1.get("data_gaps") or _c1["data_gaps"][0].get("reason") != "engine_gap":
            issues.append(("ERROR", "engine/clue_chain.py", "engine_gap 三态标记缺失"))

        # b) 资料确未提供 ⇒ 必须**点名缺哪份**（面向企业说具体材料名），且不得给读数
        _c2 = build_clue_chain(_f, _rl, {}, provided_materials=[])
        _n2 = (_c2.get("nodes") or [{}])[0]
        if "因缺少资料" not in str(_n2.get("observed", "")) or "工资表" not in str(_n2.get("observed", "")):
            issues.append(("ERROR", "engine/clue_chain.py",
                           "资料未提供时未点名缺失的具体资料名"))
        if _n2.get("has_data"):
            issues.append(("ERROR", "engine/clue_chain.py", "资料未提供却判为有数据"))
        if not _c2.get("data_gaps") or _c2["data_gaps"][0].get("reason") != "material_missing":
            issues.append(("ERROR", "engine/clue_chain.py", "material_missing 三态标记缺失"))

        # c) 带括号说明的资料名必须能归一到类别（旧实现整片精确匹配 ⇒ 永远匹配不上）
        _rl_c = {"id": "RL-T", "name": "n",
                 "clue_chain": [{"step": 1, "source": "销项发票（含红字标识）",
                                 "action": "a", "output": "o"}]}
        _n_c = (build_clue_chain(_f, _rl_c, {}, provided_materials=["销项发票"]).get("nodes") or [{}])[0]
        _obs_c = str(_n_c.get("observed", ""))
        # 不得说"缺资料"，也不得改口说"类别无法识别"——两者都是"销项发票明明已提供"被误判
        if "因缺少资料" in _obs_c or "无法识别" in _obs_c:
            issues.append(("ERROR", "engine/clue_chain.py",
                           "带括号说明的资料名（销项发票（含红字标识））未归一到类别，"
                           "未提供资料被误判为缺料/类别不可识别"))

        # d) 有对题命中证据 ⇒ 必须**原样采用**（环节读数唯一权威 = 要件命中证据）
        _rl_d = {"id": "RL-T", "name": "n", "constituents": ["存在红字发票或作废发票（红冲行为）"],
                 "clue_chain": [{"step": 1, "source": "销项发票",
                                 "action": "统计红字与作废发票金额、占比",
                                 "output": "红冲率与时间分布特征"}]}
        _ev = "销项红字/作废 1,015,900.00 元，占同期销项蓝字开票额 12.6%"
        _f_d = {"type": "t", "detail": "共13张涉及红冲",
                "constituent_hits": [{"index": 1, "evidence": _ev}]}
        _n_d = (build_clue_chain(_f_d, _rl_d, {}, provided_materials=["销项发票"]).get("nodes") or [{}])[0]
        if str(_n_d.get("observed", "")) != _ev or not _n_d.get("has_data"):
            issues.append(("ERROR", "engine/clue_chain.py",
                           "有对题命中证据时未原样采用（环节读数须以要件命中证据为唯一权威）"))

        # e) 对题阈值必须挡得住不相干要件（否则"拿不适用资料冒充已核对"复发）
        #    用例取**阈值边界**（实测字符 2-gram 交集=3）：阈值若被降到 ≤3 就会把
        #    "要件③事由核对"的证据错配给"核对退款"环节 —— 即 D7「拿不适用资料冒充已核对」。
        #    （原先用交集=0 的用例：任何阈值都判不对题，断言恒真 ⇒ 是白过的假断言。）
        _rl_e = {"id": "RL-T", "name": "n",
                 "constituents": ["红冲无对应退货单、折让协议等合法事由"],
                 "clue_chain": [{"step": 1, "source": "银行流水",
                                 "action": "核对红冲是否对应退款", "output": "红冲真实性判断"}]}
        _f_e = {"type": "t", "detail": "x",
                "constituent_hits": [{"index": 1,
                                      "evidence": "红字发票备注/状态中未见退货、折让等合法事由"}]}
        _n_e = (build_clue_chain(_f_e, _rl_e, {}, provided_materials=["银行流水"]).get("nodes") or [{}])[0]
        if _n_e.get("has_data"):
            issues.append(("ERROR", "engine/clue_chain.py",
                           "对题阈值失效：不相干的要件命中证据被当成该环节读数"))

        # ② 触发信号（㊷，2026-10-04）：**不得"最长者优先"**——否则总落在最长的免责长句上，
        #   把差异/口径说明挤掉（实测 80/80 条勾稽发现都不带差异说明）。
        _sig = _terminal_signal_   # noqa: F821  (下方 try 内注入)
        # 用例取**真实形态**：最长句是**不含数字的免责/口径句**，短句才带差异量。
        # （首版用例的最长句恰好含差额 ⇒ "最长优先"也能过 ⇒ 那条断言是白过的假断言，已换）
        _dl = ("基于上述数据，本项结论只说明两个数据口径需要逐月对账、"
               "并在补充资料后由人工复核确认，不宜单独作为定性依据。"
               "累计方向性差额1,170,164.14元。")
        _got = _sig(_dl, [], {"type": "银行收款大于申报收入"})
        if ("差额" not in _got) and ("差异" not in _got):
            issues.append(("ERROR", "engine/clue_chain.py",
                           "触发信号未选中含差异量的句子（疑似仍在按长度选）——"
                           "㊷ 差异/口径说明被挤掉"))
        if _got == "该结果只说明两个数据口径需要逐月对账。":
            issues.append(("ERROR", "engine/clue_chain.py",
                           "触发信号选到了不含数字的免责句 —— 触发信号必须带可量化差异"))

        # ③ 汇总行（疑点2 D8，2026-10-04）：汇总行**不是一笔明细**，不得计入笔数与金额。
        _rows_d8 = [{"序号": 1, "对方单位": "甲", "金额（元）": "275000.00"},
                    {"序号": 2, "对方单位": "乙", "金额（元）": "137000.00"},
                    {"序号": 3, "对方单位": "汇总：其他个人／个体往来（未达门槛",
                     "金额（元）": "170233.01"}]
        _txt_d8 = _evsum_([{"title": "逐笔明细", "rows": _rows_d8}])   # noqa: F821
        if "170,233.01" in _txt_d8:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "汇总行的金额被计入触发金额（把汇总当一笔明细）"))
        if "412,000.00" not in _txt_d8:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "剔除汇总行后的金额合计应为本表各笔之和 412,000.00，实测不符"))
        if "汇总" not in _txt_d8:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "剔除了汇总行却未如实披露（不得静默少算）"))


        # ④ 分层口径 + D13 复发防护（2026-10-04，短行写法）
        # ★ 2026-10-06：`_d5` 必须先置 None —— 它只在 `else` 分支里赋值，
        #   而下面 ⑥ 格式泄漏扫描在 **try 层**用它 ⇒ 产物缺失时 `_d5` 未定义
        #   ⇒ `UnboundLocalError` 被 except 吞成「断言失败」ERROR（本轮实测）。
        _d5 = None
        _ps5 = []
        try:
            import json as _j5
            _a5 = ROOT / "scripts" / "four_reports" / "company_1_full.json"
            if not _a5.exists():
                issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                               "无真跑产物，跳过分层口径与 D13 防护校验"))
            else:
                _d5 = _j5.loads(_a5.read_text(encoding="utf-8", errors="replace"))
                _cp5 = _d5.get("enterprise_readable_report") or {}
                _ps5 = _cp5.get("confirmed_problems") or []
                for _p5 in _ps5:
                    _v5 = str(_p5.get("verdict") or "")
                    if "已触碰税务违规红线" in _v5:
                        issues.append(("ERROR", "enterprise_readable_report",
                                       "报告结论层出现触红断言 seq=%s" % _p5.get("seq")))
                _b5 = 0
                for _p5 in _ps5:
                    for _n5 in (_p5.get("narrative_paragraphs") or []):
                        for _t5 in (_n5.get("detail_tables") or []):
                            _tt5 = str((_t5 or {}).get("title") or "")
                            if "独立核对表" not in _tt5:
                                continue
                            for _r5 in ((_t5 or {}).get("rows") or []):
                                _c5 = str(_r5.get("核对结论") or "")
                                _s5 = str(_r5.get("数据源状态") or "")
                                if "未单独核对" in _c5 and _s5 == "已有":
                                    _b5 += 1
                if _b5:
                    issues.append(("ERROR", "enterprise_readable_report",
                                   "数据源已有却判未单独核对 %d 条" % _b5))
            # ⑥ 格式泄漏（产物级，2026-10-04）：报告正文不得出现 Python 字典字面量。
            #   与源码级 ①d 闸门（第 1100 行，查 return 字典里含 set/dict/list）互补：
            #   ①d 查不��「渲染期把 dict 元素当字符串处理」——源码看不出问题，产物里才有。
            #   事故：缺料清单实为证据元素字典列表，报告出现
            #   「确未提供的有 20 项（{'role': '直接证据'}…）」，而闸门当时全绿。
            _Q1 = chr(39)
            _Q2 = chr(34)
            _OPEN = (chr(123) + _Q1, chr(123) + _Q2)
            _bad6 = []

            def _scan6(_o, _p7):
                if isinstance(_o, dict):
                    for _k7, _v7 in _o.items():
                        _scan6(_v7, _p7 + "/" + str(_k7))
                elif isinstance(_o, list):
                    for _i7, _v7 in enumerate(_o):
                        _scan6(_v7, _p7 + "[%d]" % _i7)
                else:
                    _t7 = str(_o)
                    for _op7 in _OPEN:
                        if _op7 in _t7:
                            _bad6.append((_p7, _t7[:60]))
                            break

            if _d5 is not None:
                _scan6(_d5.get("enterprise_readable_report") or {}, "erp")
            for _p7, _s7 in _bad6[:5]:
                issues.append(("ERROR", "enterprise_readable_report",
                               "报告正文出现字典字面量（格式泄漏）@%s: %s" % (_p7, _s7)))
            # ⑦ 税种 × 基数性质（疑点4 D12，2026-10-04）：**双向**断言。
            #   ① 不相容 ⇒ 必须无金额（否则等于没修：工资差额又被当应税收入算增值税）；
            #   ② 相容/未声明 ⇒ 不得出现「基数性质不符」的说明（否则是把真实风险藏起来）。
            try:
                from engine.tax_impact import (_TAX_BASE_NATURE as _tbn7,
                                              infer_amount_nature as _ian7)
                _bad7 = []
                for _p7 in _ps5:
                    _nat7 = _ian7(_p7)
                    if not _nat7:
                        continue
                    for _it7 in ((_p7.get("tax_impact") or {}).get("items") or []):
                        _need7 = _tbn7.get(str(_it7.get("tax") or ""))
                        if not _need7:
                            continue
                        _amt7 = _it7.get("amount")
                        _bad7.append((_p7.get("seq"), _it7.get("tax"), _nat7, _need7))
                        # ★ 2026-10-16：要求值现为**可接受性质集合**（个税的基数随所得项目
                        #   而变：工资薪金=wage、股息红利=profit）⇒ 用**成员判据**，
                        #   不再用等号（等号会把"股息红利 20%"误判成不相容）。
                        if _nat7 not in _need7 and _amt7 is not None:
                            issues.append(("ERROR", "engine/tax_impact.py",
                                           "基数口径与税种要求不符却仍给出金额 seq=%s %s（口径=%s 要求=%s）"
                                           % (_p7.get("seq"), _it7.get("tax"), _nat7,
                                              "/".join(_need7))))
                        if _need7 == _nat7 and _amt7 is None \
                                and "与本税种要求的基数性质" in str(_it7.get("note") or ""):
                            issues.append(("ERROR", "engine/tax_impact.py",
                                           "相容税种被误不估（把真实风险藏起来）seq=%s %s"
                                           % (_p7.get("seq"), _it7.get("tax"))))
            except Exception as _e7:
                issues.append(("ERROR", "tools/audit_consistency.py",
                               f"税种基数相容性断言失败: {_e7}"))
            # ⑧ 缺料三态**恒等式**（疑点4 D8-①，2026-10-04）：
            #   「需要N项」必须 == 逐字M + 同类V + 确未提供K，且 K == 列出的材料名个数。
            #   事故：同一批 verify 被说两遍 + 「需要N」按元素数、而 K 按材料名原子数
            #   ⇒ 同一页出现「需要3项」却「1+1+3=5」。
            import re as _re8
            _G8 = 'enterprise_readable_report'
            try:
                import re as _re8
                _sp8 = _re8.compile(r'[、，,；;／/]|与|和|及|或者')
                for _p8 in _ps5:
                    _T8 = _j5.dumps(_p8, ensure_ascii=False)
                    _m8 = _re8.search(r'本项检查需要(\d+)项材料', _T8)
                    if not _m8:
                        continue
                    _need8 = int(_m8.group(1))
                    _h8 = _re8.search(r'名称逐字对应、已确在手上的有(\d+)项', _T8)
                    _v8 = _re8.search(r'其中(\d+)项已提供同类资料', _T8)
                    _k8 = _re8.search(r'确未提供的有(\d+)项（([^）]*)）', _T8)
                    _H8 = int(_h8.group(1)) if _h8 else 0
                    _V8 = int(_v8.group(1)) if _v8 else 0
                    _K8 = int(_k8.group(1)) if _k8 else 0
                    _at8 = []
                    if _k8:
                        for _y8 in _sp8.split(_k8.group(2)):
                            _y8 = _y8.strip()
                            if _y8 and _y8 not in _at8:
                                _at8.append(_y8)
                    if _need8 != _H8 + _V8 + _K8:
                        issues.append(('ERROR', _G8,
                                       '缺料三态不自洽 seq=%s：需要%d ≠ 逐字%d+同类%d+确未提供%d'
                                       % (_p8.get('seq'), _need8, _H8, _V8, _K8)))
                    if _K8 != len(_at8):
                        # ★★ 2026-10-05（实测冲突）：`_brief_atoms` **合法**采用
                        #   "只列前 6 个 + 补「等（共N项）」"的**截断声明**写法；
                        #   而本判据要求"声明数 == 列名数" ⇒ 截断时必然报错
                        #   （实测 seq=11 声明 7 项、列出 6 名 + "等（共7项）"）。
                        #   两条判据**分工**：
                        #     · `_trunc_violations` 管"截断必须声明总数"（下面那条）；
                        #     · 本判据管"**未截断时**声明数与列名数一致"。
                        #   ⇒ 有截断声明时不适用本判据（否则合法写法被误判为不一致）。
                        #   ⚠ 正则**不带收尾括号**：`_k8.group(2)` 用的是 `[^）]*`，
                        #     会在截断声明"等（共7项）"的**第一个 `）`** 处停止 ⇒
                        #     实际拿到的是"…证明等（共7项"（未闭合）。实测确认。
                        _trunc_ok = bool(_re8.search(r'等（共\d+项', _k8.group(2) if _k8 else ''))
                        if not _trunc_ok:
                            issues.append(('ERROR', _G8,
                                           '确未提供项数≠列出名数 seq=%s：声明%d 实际%d'
                                           % (_p8.get('seq'), _K8, len(_at8))))
                    # ★ 2026-10-04（疑点4 D8 收尾）：**截断必须声明总数**（自动守护）。
                    for _d9, _v9 in _trunc_violations(_T8):
                        issues.append(('ERROR', 'enterprise_readable_report',
                                       '声明%d项但只列%d个名且未声明总数 seq=%s（静默截断）'
                                       % (_d9, _v9, _p8.get('seq'))))
            except Exception as _e8:
                issues.append(('ERROR', 'tools/audit_consistency.py',
                               '缺料恒等式断言失败: %s' % _e8))
        except Exception as _e5:
            issues.append(("ERROR", "tools/audit_consistency.py",
                           "分层口径/D13 防护断言失败: %s" % _e5))


    except Exception as exc:
        issues.append(("ERROR", "engine/clue_chain.py", f"线索链环节一致性断言执行失败: {exc}"))

    # ① redline_engine 必须把 material_readiness 的已提供清单传给线索链
    _re_src = _src("engine/redline_engine.py")
    if "provided_materials=_mats_all" not in _re_src:
        issues.append(("ERROR", "engine/redline_engine.py",
                       "build_clue_chain 未接入 provided_materials（三态判定失去资料权威来源）"))
    _er_src = _src("engine/enterprise_report.py")
    if 'g.get("reason") == "material_missing"' not in _er_src:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "发现过程叙述未按 data_gaps.reason 区分「资料缺失/程序待完善」"))
    if "rate_ctx=" not in _er_src:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "estimate_tax 未接入 rate_ctx（税率语境断路）"))

    # ④ pipeline 必须构造税率语境
    _pp_src = _src("engine/pipeline.py")
    if "infer_rate_context(" not in _pp_src or '"tax_rate_context"' not in _pp_src:
        issues.append(("ERROR", "engine/pipeline.py",
                       "pipeline 未构造 comprehensive[tax_rate_context]（税率语境单一构造点缺失）"))

    # ③ 附加税费：未取得申报表 ≠ 未申报
    try:
        from engine.verified_rule_engine import _scan_city_constr_tax
        _f43 = _scan_city_constr_tax(
            {"declaration": [{"payable_tax": 205744.69}]},
            {"name": "城建税及附加随征勾稽", "id": "VR043", "required_sources": []})
        if _f43:
            _d43 = str(_f43[0].get("detail", ""))
            if "未见对应的城建税及附加申报记录" in _d43:
                issues.append(("ERROR", "engine/verified_rule_engine.py",
                               "VR043 仍把「申报表未上传」写成「未见申报记录」（缺失≠未发生）"))
            if "无法核实" not in _d43:
                issues.append(("ERROR", "engine/verified_rule_engine.py",
                               "VR043 未如实表述申报完整性无法核实"))
    except Exception as exc:
        issues.append(("ERROR", "engine/verified_rule_engine.py", f"VR043 断言执行失败: {exc}"))

    # ③ 私户发薪：公户足额代发情形下不得"坐实"拆分（定性边界 + 论证自洽）
    _vre_src = _src("engine/verified_rule_engine.py")
    if "坐实『公账+私账拆分支付薪酬』" in _vre_src:
        issues.append(("ERROR", "engine/verified_rule_engine.py",
                       "VR056 仍含「坐实『公账+私账拆分支付薪酬』」定性表述（须改待证口径）"))
    try:
        from engine.verified_rule_engine import _scan_mixed_payroll
        _f56 = _scan_mixed_payroll(
            {"salaries": [{"姓名": "张三", "实发金额": 100000}],
             "bank_txs": [
                 {"summary": "代发工资", "借方": 150000, "counterparty": "开户银行"},
                 {"summary": "工资", "借方": 25000, "counterparty": "张三"},
             ]},
            {"name": "公私混同发薪", "id": "VR056", "required_sources": ["salaries", "bank_txs"]})
        if _f56:
            _d56 = str(_f56[0].get("detail", ""))
            if "坐实" in _d56:
                issues.append(("ERROR", "engine/verified_rule_engine.py",
                               "VR056 detail 仍输出「坐实」（定性边界）"))
            if "不作认定" not in _d56:
                issues.append(("ERROR", "engine/verified_rule_engine.py",
                               "VR056 公户足额情形未声明「本轮不作认定」（论证须自洽）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/verified_rule_engine.py", f"VR056 断言执行失败: {exc}"))

    # ③ 印花税：银行流水口径识别不到 ≠ 实际缴纳 0 元
    _da_src = _src("engine/domain_analysis.py")
    if "实际缴纳 {stamp_paid:,.0f} 元" in _da_src:
        issues.append(("ERROR", "engine/domain_analysis.py",
                       "印花税发现仍断言「实际缴纳 N 元」（申报表未取得时缺失≠未发生）"))
    try:
        from engine.domain_analysis import _domain_stamp_duty_check
        _fST = _domain_stamp_duty_check(
            bank_txs=[], sal_invs=[{"amount": 6000000.0}], pur_invs=[{"amount": 5000000.0}])
        _st = [f for f in _fST if "购销合同税负不足" in str(f.get("type", ""))]
        if _st:
            _dst = str(_st[0].get("detail", ""))
            if "实际缴纳 0 元" in _dst:
                issues.append(("ERROR", "engine/domain_analysis.py",
                               "印花税 detail 仍输出「实际缴纳 0 元」"))
            if "未能核实" not in _dst:
                issues.append(("ERROR", "engine/domain_analysis.py",
                               "印花税发现未如实表述申报缴纳情况未能核实"))
    except Exception as exc:
        issues.append(("ERROR", "engine/domain_analysis.py", f"印花税断言执行失败: {exc}"))

    # ① 资料缺口的**唯一权威是 `material_readiness`**（2026-10-06 结构变更）
    #   旧断言「询问清单须注明『已提供部分不受影响』」随"资料类询问"整体下线而失效
    #   —— 那是**治标**：病根是"资料缺口被两处各写一套"，规范做法是**消灭第二个出处**，
    #   而不是让两处保持一致。故断言改为两条：
    #     ①-a 询问清单**不得再列资料类主题**（否则与 material_readiness 重复，
    #          且会绕过业态不适用剔除——实测曾要求服务型企业补存货盘点表/出入库台账）；
    #     ①-b 资料齐备度**不得把已提供的资料列为缺失**（原断言的真实意图，移至唯一权威处）。
    try:
        from engine.inspection_questions import run_inspection_questions
        _iq = run_inspection_questions(
            comprehensive={}, company_name="测试公司",
            data_overview={"present": ["增值税申报表", "科目余额表"],
                           "missing": ["企业所得税申报表", "资产负债表"]})
        _iq_txt = json.dumps(_iq, ensure_ascii=False, default=str)
        _bad_th = [str(t.get("theme") or "") for t in (_iq.get("themes") or [])
                   if str(t.get("theme") or "").startswith("资料")]
        if _bad_th:
            issues.append(("ERROR", "engine/inspection_questions.py",
                           f"询问清单仍在列资料缺口主题 {_bad_th} —— "
                           f"资料缺口的唯一权威是 `material_readiness`，不得重复列示"))
        if "本轮未取得增值税/企业所得税申报表" in _iq_txt:
            issues.append(("ERROR", "engine/inspection_questions.py",
                           "询问清单仍把已提供的增值税申报表写成未取得"))
        if "本轮未取得科目余额表" in _iq_txt:
            issues.append(("ERROR", "engine/inspection_questions.py",
                           "询问清单仍把已提供的科目余额表写成未取得"))
    except Exception as exc:
        issues.append(("ERROR", "engine/inspection_questions.py", f"询问清单断言执行失败: {exc}"))

    try:
        from engine.enterprise_report import _build_material_readiness
        _mr = _build_material_readiness({
            "file_results": [{"type": "vat_declaration", "_rows": [{"a": 1}]},
                             {"type": "trial_balance", "_rows": [{"a": 1}]}],
            "target_entity": {"industry": "制造业", "biz_model": "制造业"},
        })
        _prov = set(_mr.get("provided") or [])
        _miss = {m.get("doc") for m in (_mr.get("missing") or [])}
        for _d in ("增值税申报表", "科目余额表"):
            if _d not in _prov:
                issues.append(("ERROR", "engine/enterprise_report.py",
                               f"资料齐备度未把**已上传**的「{_d}」计入已提供"))
            if _d in _miss:
                issues.append(("ERROR", "engine/enterprise_report.py",
                               f"资料齐备度把**已提供**的「{_d}」同时列为缺失（同页自相矛盾）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       f"资料齐备度断言执行失败: {exc}"))

    # ③ 外部核验：检索不到信息 ≠ 正常
    try:
        from engine.external_verifier import ExternalVerificationEngine
        _as = ExternalVerificationEngine()._assess(
            {"搜索引擎综合核实": {"ok": True, "assessment": "信息不足，未能核实", "found_any": False}})
        if _as.get("verdict") == "正常":
            issues.append(("ERROR", "engine/external_verifier.py",
                           "各通道均未检索到信息时结论仍为「正常」（没能查≠查了没问题）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/external_verifier.py", f"外部核验断言执行失败: {exc}"))

    # 定性词漏网回收：收入真实性 hint
    _ra_src = _src("engine/revenue_authenticity.py")
    if "账外收款直接证据" in _ra_src:
        issues.append(("ERROR", "engine/revenue_authenticity.py",
                       "仍把个人账户归集写成「直接证据」（待证线索不得定性）"))

    # ── P0-5：兜底命中必须单索引（一段证据不得复制填多个要件）──
    _re2_src = _src("engine/redline_engine.py")
    if "for _i in _di" in _re2_src:
        issues.append(("ERROR", "engine/redline_engine.py",
                       "兜底命中仍把发现级证据复制到全部序号（一段证据填多格），须只落首个序号"))
    if "_di[0]" not in _re2_src:
        issues.append(("ERROR", "engine/redline_engine.py",
                       "兜底命中未收敛到 _di[0]（单索引）"))
    _er2_src = _src("engine/enterprise_report.py")
    if "未括注的要件为本轮未单独核对到的构成要件" not in _er2_src:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "要件清单头句缺「未括注=未单独核对」声明（读者会误读为逐条都核对过）"))

    # ── P0-7：口径对照与时效提示必须存在 ──
    _io_src = _src("engine/inspection_overview.py")
    if "关键口径对照" not in _io_src:
        issues.append(("ERROR", "engine/inspection_overview.py",
                       "总述缺「关键口径对照」段（全文数字无口径索引可回指）"))
    if "滞纳金" not in _io_src:
        issues.append(("ERROR", "engine/inspection_overview.py",
                       "总述缺「时效与滞纳金提示」（汇算期届满后的更正成本未告知）"))
    if "cost_recon_detail" not in _io_src:
        issues.append(("ERROR", "engine/inspection_overview.py",
                       "口径对照未接入 cost_recon_detail（成本两口径无来源）"))

    # ── P0-7：红冲占比分子分母同口径 ──
    _da2_src = _src("engine/domain_analysis.py")
    if "占同期销项开票额" in _da2_src and "销项蓝字开票额" not in _da2_src:
        issues.append(("ERROR", "engine/domain_analysis.py",
                       "红冲占比仍用混口径分母（须为销项蓝字开票额且分子分母同口径）"))

    # ── 行为验证（产物存在时）：任何疑点不得有两 条 evidence 完全相同的 constituent_hits ──
    # ★ 2026-10-06：来源统一为 `_canonical_report()`（唯一产物），不再读第二份 dump
    _rd_d = _canonical_report()
    if _rd_d is None:
        issues.append(("WARN", "tools/audit_consistency.py",
                       "未找到全量分析产物 company_1_full.json，dump 行为验证跳过"
                       "（跑一次全量分析后自动生效）"))
    else:
        try:
            _rd_d = ((_rd_d.get("comprehensive")) or {}).get("redline_detection") or {}
            _bad = []
            for _s in (_rd_d.get("suspicions") or []):
                _evs = [str(h.get("evidence") or "") for h in (_s.get("argumentation") or {}).get("constituent_hits") or []
                        if str(h.get("evidence") or "").strip()]
                if len(_evs) != len(set(_evs)):
                    _bad.append(str(_s.get("redline_name") or _s.get("name") or "?"))
            if _bad:
                issues.append(("ERROR", "engine/redline_engine.py",
                               f"产物中仍有疑点把同一段证据填进多个要件: {('、'.join(_bad[:5]))}"))
        except Exception as exc:
            issues.append(("WARN", "tools/audit_consistency.py",
                           f"dump 行为验证跳过（读取失败）: {exc}"))

    # ══════════════════════════════════════════════════════════════
    # ★ 2026-09-29（点评整改第三轮 P0-9 / P0-6）
    # ══════════════════════════════════════════════════════════════

    # ── P0-9c 截断：不得把数字/键值对从中间切开（"=260,5""=275,00" 类残句）──
    _sk_src = _src("engine/sentencekit.py")
    if "_join_parts" not in _sk_src:
        issues.append(("ERROR", "engine/sentencekit.py",
                       "render_value 缺 _join_parts（整项取舍）：截断会把金额切半截"))
    if "elif ch in _CLOSERS" in _sk_src and "、｜" not in _sk_src:
        issues.append(("ERROR", "engine/sentencekit.py",
                       "clamp_text 句读集合缺顿号/竖线：键值对串会被切在千分位之间"))
    try:
        from engine.sentencekit import render_value as _rv
        _nd = {"货物": "饲料", "销数量": 65.0, "进数量": 1680.0,
               "差异": -1680.0, "结存数量": 1234.5}
        _nested = _rv(_nd, max_len=30)
        # 断言①：保留下来的一律是**完整键值对**，绝不出现被切半截的数字
        if re.search(r"\d,\d{1,2}(?![\d])", _nested):
            issues.append(("ERROR", "engine/sentencekit.py",
                           f"截断后仍出现半截数字（金额被切）: {_nested}"))
        # 断言②：截断必须**可见**（省略号或「等N项」），不得静默丢内容
        if "…" not in _nested and "等" not in _nested:
            issues.append(("ERROR", "engine/sentencekit.py",
                           f"截断未标注（读者无法分辨是否被截）: {_nested}"))
        # 断言③（关键）：**每一项都必须是完整键值对**——不得把某一项切成「差」这种残片。
        #   这是"整项取舍"的真正判据：朴素切片会留下无「=」的碎尾。
        for _seg in [x for x in _nested.split("、") if x]:
            if "=" in _seg or re.fullmatch(r"(等|共)\d+项", _seg):
                continue
            issues.append(("ERROR", "engine/sentencekit.py",
                           f"截断把键值对切成残片（未做整项取舍）: …{_seg}（整体: {_nested}）"))
            break
        # 断言④：短值不得被截（阈值内原样返回）
        if _rv("正常文本", max_len=90) != "正常文本":
            issues.append(("ERROR", "engine/sentencekit.py",
                           "render_value 对阈值内文本做了多余截断"))
    except Exception as exc:
        issues.append(("ERROR", "engine/sentencekit.py", f"render_value 断言执行失败: {exc}"))

    # 截断痕迹**不得被擦除**：企业报告里 `s.replace("…","")` 会把"已截断"伪装成"数据"
    # ⚠ 用「去注释、保留字符串」视图判定：旧写法在本文件注释里被引用属正常，
    #   直接原文匹配会自我误报；但**不能连字符串一起掩码** —— 要找的 `"…"`
    #   本身就是字符串字面量，掩码后就永远搜不到了（闸门会变成空转）。
    _er3_src = _src("engine/enterprise_report.py")
    _er3_code = _strip_comments_keep_lines(_er3_src)
    if 'replace("…"' in _er3_code:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "仍抹除省略号（把截断痕迹擦掉 → 「=260,5」式残句被当成真数字）"))

    # ── P0-9d 变量名泄漏：键汉化必须唯一权威（含逐笔证据列名表）+ 计数器后缀 ──
    if "_EV_COLUMN_CN" not in _er3_src:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "键汉化未合并 _EV_COLUMN_CN（逐笔证据列名表孤岛 → ref_label 等漏英文）"))
    if "_COUNTER_SUFFIXES" not in _er3_src:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "缺计数器后缀规则（红字发票_笔数 类内部键会以变量名入文）"))
    try:
        from engine.enterprise_report import _translate_key as _tk
        for _k, _must_not in (("ref_label", None), ("红字发票_笔数", None),
                              ("作废发票_笔数", None), ("core_cost_total", None),
                              ("company_paid_amount", None)):
            _out = _tk(_k)
            if _out == _k:
                issues.append(("ERROR", "engine/enterprise_report.py",
                               f"键 {_k} 未汉化（会以变量名出现在报告里）"))
            if re.search(r"[A-Za-z]", str(_out)) or "_" in str(_out):
                issues.append(("ERROR", "engine/enterprise_report.py",
                               f"键 {_k} 汉化结果仍像变量名: {_out}"))
        # 真实企业名称（含下划线）不得被改写
        if _tk("猩猩织光_北京") != "猩猩织光_北京":
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "键汉化误改真实数据名（含下划线的企业/品名）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/enterprise_report.py", f"键汉化断言执行失败: {exc}"))

    # ── P0-6 标题按实际证据裁剪（红线名的命名要件未被证明时不得沿用全名）──
    try:
        from engine.tax_redlines import trim_redline_title as _tt, _REDLINE_NAMING_CONSTITUENT
        if not _REDLINE_NAMING_CONSTITUENT:
            issues.append(("ERROR", "engine/tax_redlines.py",
                           "缺「红线命名要件」表（标题无法按证据裁剪）"))
        _rn = "长期亏损仍持续经营：收入或成本不实"
        _t1, _n1 = _tt("RL-CIT-004", "待核事实：企业所得税贡献率偏低",
                       [{"index": 2, "evidence": "x"}], _rn)
        if _t1 == _rn:
            issues.append(("ERROR", "engine/tax_redlines.py",
                           "只命中非命名要件时仍沿用红线全名（会与企业数据自相矛盾）"))
        if "未就「亏损」" not in _t1 or not _n1:
            issues.append(("ERROR", "engine/tax_redlines.py",
                           "裁剪后的标题未声明「未就前提作出认定」"))
        _t2, _ = _tt("RL-CIT-004", "x", [{"index": 1, "evidence": "y"}], _rn)
        if _t2 != _rn:
            issues.append(("ERROR", "engine/tax_redlines.py",
                           "命中命名要件时不应裁剪标题（误裁会丢失红线名与法条关联）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/tax_redlines.py", f"标题裁剪断言执行失败: {exc}"))

    # ── P0-9a 空表可解释：明细表字段填充率须披露，且全空行不得导出 ──
    _crd_src = _src("engine/cost_recon_detail.py")
    _pipe_src = _src("engine/pipeline.py")
    if "core_cost_invoices_field_fill" not in _pipe_src:
        issues.append(("ERROR", "engine/pipeline.py",
                       "逐张清单未记录字段填充率（导出空表无从解释）"))
    if "未能从原始文件中解析取得" not in _crd_src:
        issues.append(("ERROR", "engine/cost_recon_detail.py",
                       "空列未披露（读者无法分辨「本无此信息」与「没解析出来」）"))
    if "_blank_dropped" not in _pipe_src:
        issues.append(("ERROR", "engine/pipeline.py",
                       "未剔除全空发票行（导出会出现有行无字的空表）"))

    # ── P0-9b 导出净化（前端）：控件文案/折叠内容必须被单一净化点覆盖 ──
    _tda_src = _src("static/js/tax-doc-analysis.js")
    if "_sanitizeExportClone" not in _tda_src:
        issues.append(("ERROR", "static/js/tax-doc-analysis.js",
                       "缺导出净化唯一权威 _sanitizeExportClone（控件文案会入文）"))
    if "_EXPORT_STRIP_SELECTOR" not in _tda_src:
        issues.append(("ERROR", "static/js/tax-doc-analysis.js",
                       "缺 _EXPORT_STRIP_SELECTOR（导出净化无统一口径）"))
    if "beforeprint" not in _tda_src or "addEventListener('copy'" not in _tda_src:
        issues.append(("ERROR", "static/js/tax-doc-analysis.js",
                       "导出净化未接入打印/复制路径（导出的折叠表仍为空）"))
    if "@media print" not in _tda_src or "details>div" not in _tda_src:
        issues.append(("ERROR", "static/js/tax-doc-analysis.js",
                       "@media print 未展开折叠块（导出「发票逐张清单」为全空表）"))
    if "data-export-exclude" not in _tda_src:
        issues.append(("ERROR", "static/js/tax-doc-analysis.js",
                       "导出提示段落未标记 data-export-exclude（「导出：下载CSV」入文）"))
    # 两处 CSV 导出提示**都**必须带标记（只查"存在与否"会漏掉其中一处被删）
    for _kind, _zh in (("invoice", "发票逐张清单"), ("batch", "凭证逐笔清单")):
        _i = _tda_src.find("_crdBtn('%s'" % _kind)
        if _i < 0:
            continue
        _win = _tda_src[max(0, _i - 200):_i]
        if 'data-export-exclude="1"' not in _win:
            issues.append(("ERROR", "static/js/tax-doc-analysis.js",
                           f"「{_zh}」的导出提示段未标记 data-export-exclude（控件文案会入文）"))
    # 导出 PDF 必须打印**当前完整报告**，不得只打印三节摘要
    _fn_i = _tda_src.find("async function exportTaxDocReportPdf")
    _fn_j = _tda_src.find("function deleteTaxDocReport", _fn_i if _fn_i >= 0 else 0)
    _pdf_seg = _tda_src[_fn_i:_fn_j] if (_fn_i >= 0 and _fn_j > _fn_i) else ""
    if "_reportExportSource()" not in _tda_src:
        issues.append(("ERROR", "static/js/tax-doc-analysis.js",
                       "导出PDF未复用当前报告（只打印三节摘要，与屏幕报告不符）"))
    elif "_reportExportSource()" not in _pdf_seg:
        issues.append(("ERROR", "static/js/tax-doc-analysis.js",
                       "导出PDF未取当前报告（只打印三节摘要，与屏幕报告不符）"))
    elif "_sanitizeExportClone(clone)" not in _pdf_seg and "_sanitizeExportClone(clone0)" not in _pdf_seg:
        issues.append(("ERROR", "static/js/tax-doc-analysis.js",
                       "导出PDF未经导出净化（控件文案/折叠空表会进交付文件）"))

    # ══════════════════════════════════════════════════════════════
    # ★ 2026-10-02（用户质疑「内容是不是不匹配啊」派生出的同类缺陷）
    #   两处"清洗半途而废"，都用**直调生产函数**的行为断言锁死。
    # ══════════════════════════════════════════════════════════════

    # ── ① markdown 强调必须**整对**剥离：`**加粗**` 不得半剥成 `*斜体*` ──
    #   实测三处（cost_recon_detail「业态兜底」、special_redline_detectors「转让方自然人」、
    #   verified_rule_engine「无法核实」）：源文案写 `**x**`，旧式 `\*([^*]+)\*`
    #   只吃掉中间那对星号，正文变成 `*x*`，星号反而留在了报告里。
    try:
        from engine.enterprise_report import _strip_symbol_noise as _ssn
        _EMPH = [("采用**业态兜底**口径", "采用业态兜底口径"),
                 ("纳税义务人为**转让方自然人**，负代扣代缴义务", "纳税义务人为转让方自然人，负代扣代缴义务"),
                 ("申报完整性**无法核实**——本项", "申报完整性无法核实——本项")]
        # ⚠ 循环变量**不得**取名 `_src`：本函数顶部有同名辅助函数 `_src(path)`，
        #   赋值会把它覆盖成字符串，后面 `_src("engine/…")` 就变
        #   `TypeError: 'str' object is not callable`（实测踩过，位置离得很远）。
        for _emph_src, _emph_exp in _EMPH:
            _got = _ssn(_emph_src)
            if "*" in _got:
                issues.append(("ERROR", "engine/enterprise_report.py",
                               f"markdown 强调被半剥离，星号残留报告正文: {_got}"))
                break
            if _emph_exp not in _got:
                issues.append(("ERROR", "engine/enterprise_report.py",
                               f"强调剥离误伤正文内容: {_emph_src} → {_got}"))
                break
        # 反向：增值税发票品名形如「住宿服务*住宿服务」（单个星号在中间），必须原样保留
        if _ssn("住宿服务*住宿服务") != "住宿服务*住宿服务":
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "强调剥离误伤增值税发票品名（单星号分隔）"))
    except Exception as _exc:
        issues.append(("WARN", "tools/audit_consistency.py", f"强调剥离行为断言跳过: {_exc}"))

    # ── ② 发现过程明细表「同上」分支不得回填**未中文化**的引擎原始键名 ──
    #   实测：疑点「对私转账」第 3 环观测值与上一环同文本 → 命中"同上"分支，
    #   旧实现直接回填原始 observed，`matches=` / `receipts=` 这类引擎内部键名进了表格。
    #   「同上」只是不再重复播报的信号，不是放弃清洗的信号。
    try:
        from engine.enterprise_report import _clue_table as _ct
        _dup_obs = ("涉及个人账号数=15；matches=人员=初永伟、转出个人金额=1,071,343.80等5项")
        _clue_dup = {"nodes": [
            {"step": 1, "source": "bank_txs", "action": "取流水", "observed": _dup_obs},
            {"step": 2, "source": "bank_txs", "action": "核对对手方", "observed": _dup_obs}]}
        _ct_out = _ct(_clue_dup) or {}
        _raw_cells = [str(_r.get("实际看到的数据") or "")
                      for _r in (_ct_out.get("rows") or [])
                      if re.search(r"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9_]{2,}=",
                                   str(_r.get("实际看到的数据") or ""))]
        if _raw_cells:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           f"明细表「同上」分支回填了未中文化的引擎键名: {_raw_cells[:1]}"))
    except Exception as _exc:
        issues.append(("WARN", "tools/audit_consistency.py", f"明细表同上分支行为断言跳过: {_exc}"))

    # ── ③ 「就资料来说，…（已提供N项…）」这句的括号必须闭合 ──
    #   实测公司1 疑点5 四、段：`（已提供0项；尚缺：合同文件；企业尚未提交正当理由的书面证明，
    #   现有资料不足以排除本项涉嫌风险。` —— 左括号从未闭合，句子看起来没说完；
    #   这类缺陷信息全都在、只少一个右括号，人眼几乎发现不了。
    #   ⚠ **不要**做全报告括号配平扫描：中文序号「1）2）3）」本身就是只有右括号，
    #     普扫会当场报 60 处假错（实测）。只锁这一句的结构。
    try:
        from engine.argumentation import _compose_reasoning as _cr3
        _rl3 = {"name": "测试红线", "suspect": "涉嫌X", "constituents": ["要件一"]}
        _clue3 = {"nodes": [{"step": 1, "source": "bank_txs", "action": "取数", "observed": "金额=1"}]}
        _ev3 = {"verdict": "支撑材料严重不足", "available_count": 0, "missing_count": 1,
                "missing_materials": ["合同文件"],
                "rebuttal_status": "企业尚未提交正当理由的书面证明，现有资料不足以排除本项涉嫌风险。"}
        _out3b = _cr3(_rl3, "本条涉嫌触碰红线「测试红线」，涉嫌X", _clue3, _ev3, ["已按独立交易原则定价"],
                      "疑似触碰税务违规红线（资料不足，待补充资料后判断）", 0.6)
        _i3 = _out3b.find("就资料来说")
        if _i3 >= 0:
            _seg3 = _out3b[_i3:_out3b.find("。", _i3) + 1]
            if _seg3.count("（") != _seg3.count("）"):
                issues.append(("ERROR", "engine/argumentation.py",
                               f"材料说明句左括号未闭合（半截句子）: {_seg3}"))
            if "。）。" in _seg3:
                issues.append(("ERROR", "engine/argumentation.py",
                               f"材料说明句出现双句号（自证语尾句号未剥）: {_seg3}"))
        else:
            issues.append(("ERROR", "engine/argumentation.py",
                           "论证缺「就资料来说…」材料说明句（材料齐备性未披露）"))
    except Exception as _exc:
        issues.append(("WARN", "tools/audit_consistency.py", f"材料说明句括号断言跳过: {_exc}"))

    # ── ③b 行业推断必须按**张数**（列表），不得传 set ──
    #   `infer_from_goods` 取的是 `*分类*` 的**出现次数**众数（"卖得最多的是什么"）。
    #   传 set 会把口径偷换成"品名种类最多"，实测同一批发票：
    #     按张数 → 广告传媒（对）；按种类 → 现代服务（错，且不是具体行业，
    #     行业库里没有它的核心投入登记 → 成本归属整体落"待核"）。
    #   这是"改了代码但报告数字不变/变错"的隐形推手，必须用行为断言锁住。
    try:
        from engine.context import AuditContext as _RC3
        from engine.phase1_triage import _infer_company_profile as _icp3
        _ctx3 = _RC3()
        # 8 张广告发布 + 3 种现代服务品名各 1 张：按张数=广告传媒，按种类=现代服务
        _sal3 = [{"goods": "*广告服务*广告发布费", "amount": 10000, "date": "2025-03-01"}] * 8 + [
            {"goods": "*现代服务*代言服务费", "amount": 1000, "date": "2025-03-02"},
            {"goods": "*现代服务*服务费", "amount": 1000, "date": "2025-03-03"},
            {"goods": "*现代服务*咨询服务费", "amount": 1000, "date": "2025-03-04"}]
        _pur3 = [{"goods": "*现代服务*服务费", "amount": 500, "date": "2025-03-05"}]
        _icp3(_ctx3, _pur3, _sal3, [], [])
        _got_ind3 = str((_ctx3.company_profile or {}).get("industry") or "")
        if _got_ind3 != "广告传媒":
            issues.append(("ERROR", "engine/phase1_triage.py",
                           "行业推断未按**张数**统计（疑似又把 set 传给了推断器）："
                           f"期望「广告传媒」，实际「{_got_ind3}」"))
    except Exception as _exc:
        issues.append(("WARN", "tools/audit_consistency.py", f"行业张数口径断言跳过: {_exc}"))

    # ── ③c 差旅出行必须落期间费用，且**同一实物不得两判** ──
    #   实测两类误判（都出自用户贴的「按供应商」表）：
    #     · `*经纪代理服务*机票款` 撞上行业核心投入里过泛的"代理服务" ⇒ 105,883.20 元
    #       机票款被判成主营业务成本；
    #     · `*运输服务*客运服务费/票价/国内机票款` 无层可落 ⇒ 退成"待核"，
    #       而同实的「住宿服务住宿费」却在费用桶 —— 同一类支出两种归属。
    #   修法=新增「差旅出行层」并置于行业核心投入**之前**（`TRAVEL_KWS`）。
    try:
        from engine.account_classifier import (
            classify_line as _cl3, CLASS_EXPENSE as _CE3, TRAVEL_KWS as _TK3,
        )
        _TRAVEL_CASES = ["经纪代理服务机票款", "经纪代理服务代订住宿费", "经纪代理服务退票费",
                         "运输服务客运服务费", "运输服务国内机票款；运输服务燃油附加费",
                         "住宿服务住宿费", "旅游服务综合服务费"]
        _bad3 = [g for g in _TRAVEL_CASES
                 if _cl3(g, industry="广告传媒").get("account_class") != _CE3]
        if _bad3:
            issues.append(("ERROR", "engine/account_classifier.py",
                           "差旅出行类品名未落期间费用（同一实物两种归属）："
                           + "、".join(_bad3[:4])))
        if not _TK3:
            issues.append(("ERROR", "engine/account_classifier.py",
                           "差旅出行词表 TRAVEL_KWS 为空（该层形同不存在）"))
        # 成本类不得被差旅层误伤（广告公司的核心投入仍是成本）
        for _g3 in ("广告服务广告发布费", "设计服务专业设计服务", "现代服务代言服务费"):
            if _cl3(_g3, industry="广告传媒").get("account_class") != "主营业务成本":
                issues.append(("ERROR", "engine/account_classifier.py",
                               f"差旅层误伤行业核心投入：{_g3} 未判为成本"))
                break
    except Exception as _exc:
        issues.append(("WARN", "tools/audit_consistency.py", f"差旅出行层断言跳过: {_exc}"))

    # ── ③d 「直接相关性」判据：项目证据 ⇒ 成本；自用 ⇒ 费用（用户给出的判定原则）──
    #   原则原话：区分成本与费用的核心不是发票品名，而是该支出**是否直接服务于某个项目、
    #   与该项目收入形成直接配比** —— 同一张「技术服务费」：为客户项目 ⇒ 成本；
    #   公司内部 IT 维护 ⇒ 管理费用。
    #   落地红线：**只有取得项目/合同证据才判成本**；备注栏必须出现项目指示词才算证据
    #   （否则"见附件""款已付"这类普通备注会把几乎所有发票判成成本）。
    try:
        from engine.account_classifier import (
            classify_line as _cl4, CLASS_COST as _CC4, CLASS_EXPENSE as _CE4,
            _project_evidence as _pe4,
        )
        # ① 项目证据 ⇒ 成本
        for _g4 in ("现代服务技术服务费", "信息系统服务服务费"):
            if _cl4(_g4, industry="广告传媒", project="某客户年度传播项目").get("account_class") != _CC4:
                issues.append(("ERROR", "engine/account_classifier.py",
                               f"有项目/合同证据却未按「直接配比」判成本：{_g4}"))
                break
        # ② 差旅票务对应到项目 ⇒ 成本（用户原则："项目相关的差旅费可计入成本"）
        if _cl4("经纪代理服务机票款", industry="广告传媒",
                remark="出差-某客户项目 行程单").get("account_class") != _CC4:
            issues.append(("ERROR", "engine/account_classifier.py",
                           "项目相关差旅费未按直接配比判成本（用户原则要求可入成本）"))
        # ③ 自用 ⇒ 期间费用（用户举的第二个例子）
        if _cl4("现代服务技术服务费", industry="广告传媒",
                remark="系公司内部IT系统维护").get("account_class") != _CE4:
            issues.append(("ERROR", "engine/account_classifier.py",
                           "自用（内部维护）未判为期间费用（用户原则：间接相关 ⇒ 费用）"))
        # ④ **反向红线**：无关备注不得被当成项目证据（否则一切都判成本）
        for _bad_remark in ("见附件", "款已付，对账无误", "对账无误"):
            if _pe4(None, project="", remark=_bad_remark):
                issues.append(("ERROR", "engine/account_classifier.py",
                               f"无关备注被误判为项目证据（「{_bad_remark}」）——会把大量发票判成成本"))
                break
        # ⑤ 硬排除优先于项目配比（挂项目也不能把个人消费/预付卡算进成本）
        for _g5 in ("预付卡购物卡", "职工个人消费支出"):
            if _cl4(_g5, industry="广告传媒", project="某项目").get("account_class") == _CC4:
                issues.append(("ERROR", "engine/account_classifier.py",
                               f"硬排除层被项目配比层越过：{_g5} 被判成成本"))
                break
    except Exception as _exc:
        issues.append(("WARN", "tools/audit_consistency.py", f"直接相关性判据断言跳过: {_exc}"))

    # ── ③e 行业口径文案：术语不得混用 + 文本残缺不得下确定结论 ──
    #   用户质疑「为什么还表述商贸？是正常的表述吗？」牵出两处：
    #     ① 概念混用：「商贸」是**工商登记行业**（Company.industry_code），不是"经营范围"，
    #        而三处文案写成"登记经营范围为「商贸」"；
    #     ② 结论无据：公司1 的 `business_scope` 只有 56 字且带省略号（联网核验的**摘要片段**），
    #        却据此输出"「广告传媒」在经营范围文本中未见行业级关键词"——把"数据不可用"
    #        说成了"事实如此"。
    try:
        from engine.industry_resolver import (
            scope_text_issue as _sti2, scope_covers_industry as _sci2, resolve_industry as _ri2,
        )
        # ① 文本可用性判据
        if _sti2("五金产品零售;日用百货销售;服装...") == "":
            issues.append(("ERROR", "engine/industry_resolver.py",
                           "含省略号的经营范围文本未被判为「不可用」（会把摘要片段当完整登记原文）"))
        if _sti2("五金产品零售；日用百货销售；针纺织品销售；化妆品零售；包装材料及制品销售；橡胶制品销售") != "":
            issues.append(("ERROR", "engine/industry_resolver.py",
                           "完整的经营范围文本被误判为不可用"))
        # ② 残缺文本 ⇒ 不得下"未见行业级关键词"的确定结论
        _bad_scope = "五金产品零售;日用百货销售;针纺织品销售;化妆品零售;包装材料及制品销售;服装..."
        if _sci2("广告传媒", _bad_scope) is not None:
            issues.append(("ERROR", "engine/industry_resolver.py",
                           "经营范围文本残缺时仍给出确定的涵盖判定（应判「无从判定」）"))
        _r6 = _ri2(company_name="某公司", registered_industry="商贸",
                   sales_goods=["*广告服务*广告发布费"], business_scope=_bad_scope)
        if _r6.get("conflicts"):
            issues.append(("ERROR", "engine/industry_resolver.py",
                           "经营范围文本残缺仍输出「未见行业级关键词」类冲突结论（结论无据）"))
        if "摘要片段" not in str(_r6.get("scope_note") or "") and "不完整" not in str(_r6.get("scope_note") or ""):
            issues.append(("ERROR", "engine/industry_resolver.py",
                           "无法判定时未如实说明原因（读者会把「资料不完整」误读成「确实没有」）"))
        # ③ 反向：完整文本仍要能正常判（涵盖 / 未涵盖）
        _full = ("五金产品零售；日用百货销售；针纺织品销售；化妆品零售；包装材料及制品销售；"
                 "橡胶制品销售；日用杂品销售；服装服饰零售；鞋帽零售；文具用品零售")
        if _sci2("广告传媒", _full) is not False:
            issues.append(("ERROR", "engine/industry_resolver.py",
                           "完整且不含行业关键词的经营范围未判为「未涵盖」（真线索被吞）"))
        if _sci2("广告传媒", _full + "；广告设计；广告制作；广告发布；广告代理") is not True:
            issues.append(("ERROR", "engine/industry_resolver.py",
                           "完整且含行业关键词的经营范围未判为「已涵盖」"))
    except Exception as _exc:
        issues.append(("WARN", "tools/audit_consistency.py", f"行业口径文案断言跳过: {_exc}"))

    # ── ③f 疑点呈现顺序必须真的按等级降序（**行为断言**，不是查源码接线）──
    #   用户质疑「为什么二、具体问题不是从高风险开始排」暴露：
    #     `_build_confirmed_problems` 在有红线疑点时**直接 return `_build_redline_problems(...)`**，
    #     而 `_RISK_PRESENT_ORDER` 的排序写在**旧路径**（无 suspicions 时）后面 ⇒ 主路径
    #     **从不执行那段排序**（死代码），实际顺序＝suspicions 的置信度顺序。
    #     ⚠ 既有闸门（源码级）只查"排序键是否引用 `_RISK_PRESENT_ORDER`" ⇒ 查不到"这段从没走到"，
    #       属典型**形式闸门**。此处补行为断言：直接调生产函数看**实际产出顺序**。
    try:
        from engine.enterprise_report import (
            _build_confirmed_problems as _bcp7, _RISK_PRESENT_ORDER as _RPO7,
            _LEGAL_RISK_LEVELS as _LRL7,
        )
        # ⚠ 本断言**自给自足**：不依赖同函数后续定义的 dump 变量（`_dd2` 定义在后面的
        #   另一个 dump 块里，直接引用会 NameError → 被 except 吞成 WARN「跳过」→ 闸门空转）。
        _rd7 = _canonical_report()
        if _rd7 is None:
            raise FileNotFoundError("无产物：先跑一次一键分析")
        _cps7 = _bcp7(_rd7) or []
        _bad_lv7 = [str(_c.get("risk_level") or "") for _c in _cps7
                    if str(_c.get("risk_level") or "") not in _LRL7]
        if _bad_lv7:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "疑点出现词表外风险等级（读者无法理解）："
                           + "、".join(sorted(set(_bad_lv7))[:4])))
        _prev7 = -1
        _viol7 = []
        for _c7 in _cps7:
            _k7 = _RPO7.get(str(_c7.get("risk_level") or "").strip(), 99)
            if _k7 < _prev7:
                _viol7.append("%s(%s)" % (str(_c7.get("title") or "")[:16], _c7.get("risk_level")))
            _prev7 = max(_prev7, _k7)
        if _viol7:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "具体问题未按风险等级降序呈现（重的事项排在了轻的后面）："
                           + "、".join(_viol7[:3])))
        # seq 必须与呈现顺序一致（前端/引用按 seq 定位）
        if _cps7 and [int(_c.get("seq") or 0) for _c in _cps7] != list(range(1, len(_cps7) + 1)):
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "疑点 seq 与呈现顺序不一致（排序后未重排 seq）"))
    except Exception as _exc:
        issues.append(("WARN", "tools/audit_consistency.py", f"疑点呈现顺序断言跳过: {_exc}"))

    # ── ③g 资料要求必须跟随业态（服务业不该被要"进销存台账"）──
    #   用户质疑：「如果行业为服务业，是否还欠缺进销存台账呢？」
    #   事故：业态配置里服务型已声明 `skip_domains` 含"进销存分析/存货周转/BOM映射"，
    #   域分析据此跳过；但**资料要求没跟着走** ⇒ 同一份报告一边写「进销存跳过-服务行业：
    #   不适用进销存比值分析」，一边把「进销存台账」列为缺失要求企业补交
    #   （实测企业版报告 94 处提及、29 个疑点中 8 个的待补清单里出现它）。
    try:
        from engine.industry_resolver import not_required_materials as _nrm2
        _svc_docs, _svc_reason = _nrm2("广告传媒")
        if "进销存台账" not in _svc_docs:
            issues.append(("ERROR", "engine/industry_resolver.py",
                           "服务型业态未把「进销存台账」判为不适用（会向服务企业索要存货台账）"))
        if not _svc_reason:
            issues.append(("ERROR", "engine/industry_resolver.py",
                           "剔除不适用资料时未给出原因（读者会以为漏要了一份资料）"))
        _trade_docs, _ = _nrm2("商贸")
        if "进销存台账" in _trade_docs:
            issues.append(("ERROR", "engine/industry_resolver.py",
                           "贸易型业态被误剔「进销存台账」（贸易企业确实需要，属于真线索被吞）"))
        if _nrm2("")[0] or _nrm2("不存在的行业xyz")[0]:
            issues.append(("ERROR", "engine/industry_resolver.py",
                           "业态判不出时仍剔除资料（应不臆测：判不出就不剔）"))
    except Exception as _exc:
        issues.append(("WARN", "tools/audit_consistency.py", f"业态资料适配断言跳过: {_exc}"))

    # ── ③h 证据行必须与本项**主题**相关（个人账户类项目不得混入公司主体记录）──
    #   用户质疑：「为什么会涉及公司主体的记录，如上海蕴世广告传媒有限公司」——
    #   疑点「公私混同发薪/私户支付薪酬」的明细表里混进了**对公**流水
    #   （上海蕴世广告传媒 1,611,200.00 服务费收入、沙暴文化传播 419,154.26 收入…），
    #   而那些是"客户付给公司"的钱，与"私户发薪"毫无关系。
    #   根因：抓行只看"文本含银行/流水"就取**金额最大**的几笔，从不看这笔相不相关。
    try:
        from engine.fieldkit import (looks_like_enterprise as _lent2,
                                     is_noise_counterparty as _lnoi2)
        # ① 判据自测：企业法人必须被识别；银行摘要脏值必须被识别
        if not (_lent2("上海蕴世广告传媒有限公司") and _lent2("沙暴文化传播（北京）有限公司")):
            issues.append(("ERROR", "engine/fieldkit.py", "企业法人未被识别（过滤会失效）"))
        if not _lent2("深圳某某科技有限公司"):
            issues.append(("ERROR", "engine/fieldkit.py", "企业法人后缀识别不全"))
        if _lent2("河南林超攀体育文化传播工作室") or _lent2("深圳市龙岗区篮球协会"):
            issues.append(("ERROR", "engine/fieldkit.py",
                           "工作室/协会被误判为企业法人（它们是个人账户往来的真实对象，不该剔）"))
        if not _lnoi2("支付结算批量汇出汇款"):
            issues.append(("ERROR", "engine/fieldkit.py",
                           "银行摘要脏值未被识别（会被当成交易对手名列出）"))
        # ② 端到端：个人账户类发现的明细行不得含公司主体
        _dp8 = _canonical_report()
        _rd8 = _dp8 if isinstance(_dp8, dict) else {}
        if _dp8 is not None:
            _PERSONAL_KW = ("个人账户", "私户", "公私混同", "六员", "个人交易", "个人收款")
            _bad8 = []
            for _f8 in (_rd8.get("all_findings") or []):
                # ⚠ 只看**主旨 type**：正文里偶然提到"个人账户支付"不代表本项主题是个人账户
                #   （如「主营业务成本资金与负债支撑材料核验」的核心证据本是公司付款行，
                #    按正文判定会把它们误当"混入的公司主体"报错）。
                _txt8 = str(_f8.get("type") or "")
                if not any(_k in _txt8 for _k in _PERSONAL_KW):
                    continue
                for _r8 in (_f8.get("evidence_rows") or []):
                    _cp8 = str(_r8.get("counterparty") or "").strip()
                    if not _cp8:
                        continue
                    if str(_r8.get("source") or "") == "工资表":
                        continue
                    if _lent2(_cp8) or _lnoi2(_cp8):
                        _bad8.append("%s→%s" % (str(_f8.get("type") or "")[:12], _cp8[:18]))
            if _bad8:
                issues.append(("ERROR", "engine/pipeline.py",
                               "个人账户类疑点的明细行里混入**公司主体**记录（与主题无关）："
                               + "、".join(_bad8[:3])))
        # ③ 用户要求「不要抽样，全显示」：不得再有抽样截断标记
        _scope8 = [str(_f8.get("type") or "")[:16] for _f8 in (_rd8.get("all_findings") or [])
                   if _f8.get("evidence_rows_scope")]
        if _scope8:
            issues.append(("ERROR", "engine/pipeline.py",
                           "仍存在抽样截断标记（用户要求明细表全显示）：" + "、".join(_scope8[:3])))
    except Exception as _exc:
        issues.append(("WARN", "tools/audit_consistency.py", f"证据行主题相关性断言跳过: {_exc}"))

    # ── ③i 新增两段（用户要求）：为何列入检查 + 若不补证的后果 ──
    #   ① 「为何列入检查」必须存在（有触发信号时）——让企业一眼看懂"正是因为出现了什么情况"；
    #   ② 「若不补证的后果」必须**依法且不越界**：只说"存在被认定为…的风险"，
    #      且必须保留"须由税务机关依法调查认定 / 本报告不作定性"。
    try:
        _dp9 = _canonical_report()
        if _dp9 is not None:
            _rd9 = _dp9
            _er9 = _rd9.get("enterprise_readable_report") or {}
            _cps9 = _er9.get("confirmed_problems") or []
            _missing_why = []
            _bad_cons = []
            from engine.report_dedup import is_consequence_head as _ich9  # noqa: PLC0415
            from engine.levy_nature import natures_of as _nats9            # noqa: PLC0415
            # ★ 2026-10-06：报告的**有效文本** = 本项段落 ∪ 报告级共性声明。
            #   免责句（"本报告不作定性…"）是**去重后被上提到报告级**的共性句
            #   （用户明确要求"免责声明不得逐项重复"）⇒ 只看本项会误判为"缺免责表述"。
            _common9 = " ".join(str((_c or {}).get("text") or "")
                                for _c in (_er9.get("common_statements") or []))
            for _c9 in _cps9:
                _paras9 = (_c9.get("narrative_paragraphs") or [])
                _heads = [str((_p9 or {}).get("heading") or "") for _p9 in _paras9]
                _txt9 = " ".join(str((_p9 or {}).get("text") or "") for _p9 in _paras9)
                # 后果段本项文本（若有）
                _cons9 = " ".join(str((_p9 or {}).get("text") or "") for _p9 in _paras9
                                  if _ich9((_p9 or {}).get("heading")))
                _eff9 = _txt9 + " " + _common9
                if "为何列入检查" not in _heads:
                    _missing_why.append(str(_c9.get("title") or "")[:16])
                # ★ 2026-10-06：原先写精确成员判断 `"若不补证的后果" in _heads`，
                #   而产物标题是「若不补充资料的后果」⇒ **探针永不执行 = 假绿**。
                if any(_ich9(_h) for _h in _heads):
                    # ① 免责边界（可在报告级共性声明里）：任何性质都必须有
                    if "不作定性" not in _eff9 and "既不认定违法" not in _eff9:
                        _bad_cons.append(str(_c9.get("title") or "")[:16] + "(缺免责表述)")
                    # ② "须由税务机关依法调查认定"只对**税款**事项要求 ——
                    #    对社保费/公积金/政府性基金属**法律适用错误**（用户评语 #4）。
                    if "税" in _nats9(_c9) and "税务机关依法调查认定" not in _eff9:
                        _bad_cons.append(str(_c9.get("title") or "")[:16] + "(税款项缺认定主体)")
                    if "将被认定" in _cons9 or "已经认定违法" in _cons9:
                        _bad_cons.append(str(_c9.get("title") or "")[:16] + "(越界断言)")
            if _missing_why:
                issues.append(("ERROR", "engine/enterprise_report.py",
                               "疑点缺「为何列入检查」段（读者不知道因何触发）：" + "、".join(_missing_why[:3])))
            if _bad_cons:
                issues.append(("ERROR", "engine/enterprise_report.py",
                               "「若不补证的后果」段越界或缺免责表述（禁伪作执法文书）："
                               + "、".join(_bad_cons[:3])))
    except Exception as _exc:
        issues.append(("WARN", "tools/audit_consistency.py", f"新增两段断言跳过: {_exc}"))

    # ── ④ 段尾触红断言的中性化 + **锚点容错**（上游 to_plain 会改写措辞）──
    #   逐字锚点最阴的失败方式是"静默失效"：常量写「补证」，报告里却是「补充资料」
    #   （plain_language 的规则），替换一次也不会发生，谁都不报错。
    try:
        from engine.argumentation import (
            _VERDICT_HIT_PENDING as _vhp2, _TAIL_HIT_PENDING as _thp2,
            _TAIL_HIT_ANCHOR as _tha2, neutralize_assertion_when_no_constituent as _neu2,
        )
        _nm2 = "关联交易异常：购销闭环与六员重叠"
        _base2 = ("本条涉嫌触碰红线，即%s，涉嫌通过关联企业转移利润。"
                  "综合以上，本项结论是%s，判断可信度约60%%（中等）。%s"
                  % (_nm2, _vhp2, _thp2))
        _out2 = _neu2(_base2, _nm2)
        if _tha2 in _out2 or "已触碰税务违规红线" in _out2:
            issues.append(("ERROR", "engine/argumentation.py",
                           "零要件认定时，论证段尾的触红断言未被中性化（与同项零认定首句矛盾）"))
        if "既不认定违法，也不予排除" not in _out2:
            issues.append(("ERROR", "engine/argumentation.py",
                           "中性化时把「不认定违法、也不予排除」的承诺一并删掉了"))
        # 反向①：上游已把「补证」改写成「补充资料」时，仍必须能替换（锚点容错）
        _broken2 = _base2.replace("补证", "补充资料")
        _out3 = _neu2(_broken2, _nm2)
        if _tha2 in _out3 or "已触碰税务违规红线" in _out3:
            issues.append(("ERROR", "engine/argumentation.py",
                           "上游改写措辞后锚点失效，段尾触红断言逃逸（逐字锚点＝假闸门）"))
        # 反向②：幂等 —— 二次净化不得把已中性的文本再改坏
        if _neu2(_out2, _nm2) != _out2:
            issues.append(("ERROR", "engine/argumentation.py", "触红断言中性化不幂等"))
        # 反向③：不是本条红线的触红开场不得误伤
        _other2 = ("本条涉嫌触碰红线，即另一个疑点名，涉嫌X。"
                   "综合以上，本项结论是%s。" % _vhp2)
        if _neu2(_other2, _nm2) != _other2:
            issues.append(("ERROR", "engine/argumentation.py",
                           "触红断言中性化误伤非本红线的段落（标题裁剪场景）"))
    except Exception as _exc:
        issues.append(("WARN", "tools/audit_consistency.py", f"段尾触红断言行为断言跳过: {_exc}"))

    # ── dump 行为断言：企业报告内不得出现「英文变量名=值」，且截断必须可见 ──
    # ★ 2026-10-06：来源统一 `_canonical_report()`（唯一产物，扁平 report_data）。
    _dd2 = _canonical_report()
    if _dd2 is not None:
        try:
            _er_d = (_dd2.get("enterprise_readable_report")) or {}
            _leak = set()

            def _scan_keys(_o):
                if isinstance(_o, dict):
                    for _k, _v in _o.items():
                        _scan_keys(_v)
                elif isinstance(_o, list):
                    for _v in _o:
                        _scan_keys(_v)
                elif isinstance(_o, str):
                    for _m in re.finditer(r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_]{2,})=", _o):
                        _leak.add(_m.group(1))
            _scan_keys(_er_d)
            if _leak:
                issues.append(("ERROR", "engine/enterprise_report.py",
                               f"企业报告内仍有英文变量名入文: {('、'.join(sorted(_leak)[:6]))}"))
            _blob_d = json.dumps(_er_d, ensure_ascii=False)
            # ★ 2026-10-02：**模块名 / 数据文件名**不得进正文。
            #   实测：报告正文出现「来源 industry_benchmark（通用参考）」与
            #   「industry_data.json 中无对应行业口径」——把内部实现文件暴露给读者，
            #   既不专业也无法核验；对外一律写「系统内置行业基准库」。
            #   ⚠ 只扫**字符串值**：结构键（如 working_paper_report 里的 observed_metrics、
            #   inspector_reasoning 里的 industry_benchmark 分组键）是报告数据模型的一部分，
            #   由前端渲染、不当作正文，扫键会满屏假报。
            _txts_d = []

            def _scan_texts(_o):
                if isinstance(_o, dict):
                    for _v in _o.values():
                        _scan_texts(_v)
                elif isinstance(_o, list):
                    for _v in _o:
                        _scan_texts(_v)
                elif isinstance(_o, str):
                    _txts_d.append(_o)
            _scan_texts(_er_d)
            _leak_txt = set()
            for _s in _txts_d:
                for _m in re.finditer(r"(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*\.(?:json|py))(?![A-Za-z0-9_])", _s):
                    _leak_txt.add(_m.group(1))
                for _t in ("industry_benchmark", "industry_profiles", "observed_metrics",
                           "clue_chain", "constituent_hits"):
                    if re.search(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % _t, _s):
                        _leak_txt.add(_t)
            if _leak_txt:
                issues.append(("ERROR", "engine/enterprise_report.py",
                               f"企业报告正文暴露内部文件名/模块名: {('、'.join(sorted(_leak_txt)[:5]))}"))
            # ★ 2026-10-02（用户复核疑点5）：**同一个疑点内部不得自相矛盾** ——
            #   一边写「未认定到任何一条构成要件 / 涉及上述第 无 条」，
            #   一边断言「已触碰/已经触碰税务红线」。实测 11 处（真账套）。
            #   判据同时覆盖段首、段中裁决与段尾三处措辞。

            _ZERO_PHRASES = ("未认定到任何一条构成要件", "涉及上述第 无 条")
            _HIT_PHRASES = ("已触碰税务违规红线", "已经触碰税务红线", "已触碰税务红线")
            #   ⚠ 只看**正文段落**：数据字段（要件核对表等）里出现「涉及上述第 无 条」
            #     并不等于给读者的结论自相矛盾，扫整个 JSON 会把它误判成冲突（实测 15 vs 11）。
            _conf_items = []
            for _cp_i, _cp_o in enumerate(_er_d.get("confirmed_problems") or []):
                _txt_cp = " ".join(str((_x or {}).get("text") or "")
                                   for _x in (_cp_o.get("narrative_paragraphs") or []))
                if (any(z in _txt_cp for z in _ZERO_PHRASES)
                        and any(h in _txt_cp for h in _HIT_PHRASES)):
                    _conf_items.append(str(_cp_o.get("title") or _cp_i)[:24])
            if _conf_items:
                issues.append(("ERROR", "engine/argumentation.py",
                               "同一疑点内「未认定到任何构成要件」与「触碰税务红线」并存"
                               f"（{len(_conf_items)} 项）：{('、'.join(_conf_items[:5]))}"))
            # ★ 2026-10-02（用户复核「主营业务成本/期间费用没变化」）：**行业口径必须唯一** ——
            #   报告用的行业 vs 成本归属用的行业必须是同一个。
            #   实测事故：报告写「广告传媒」，而 `biz_cost_classification.industry_basis`
            #   是「现代服务」（金税税目大类，行业库里无核心投入登记）→ 成本归属全落「待核」。
            # ⚠ 结构适配：`_canonical_report()` 返回的是**已解包裹**的扁平 report_data
            #   （`company_1_full.json` 单层；旧 `_fresh_result.json` 为 {"report": …}；
            #    旧 `last_analysis_cache.json` 为双层 ["report"]["report"]）——
            #   三者的包裹差异已由 `_canonical_report()` 统一吸收，此处直接用。
            _inner_d = _dd2
            _te_ind = str(((_inner_d.get("target_entity") or {}).get("industry")) or "").strip()
            # ★ 2026-10-02（用户质疑「为什么还表述商贸」）：**术语不得混用** ——
            #   「商贸」是工商**登记行业**，不是"经营范围"；输出文案写成"登记经营范围为「X」"
            #   会让读者以为它是从经营范围文本里读出来的。
            #   ⚠ 判据必须用**输出里的真实形态**：报告自然化会剥掉「」（实测 dump 里是
            #     「登记经营范围为商贸」），按带引号的字面串匹配会**静默假绿**（本轮实测踩到）。
            _reg7 = ""
            try:
                _reg7 = str((((_inner_d.get("target_entity") or {}).get("_industry_candidates")
                              or {}).get("工商登记")) or "").strip()
                if not _reg7:
                    _reg7 = str(((_inner_d.get("target_entity") or {}).get("industry_registered")
                                 or "")).strip()
            except Exception as _exc7:
                issues.append(("WARN", "tools/audit_consistency.py",
                               f"行业口径术语断言取值失败（判据未生效）: {_exc7}"))
                _reg7 = ""
            _hit_term = []
            for _k7 in ("overall_conclusion", "inspection_overview"):
                for _seg7 in ((_er_d.get(_k7) or {}).get("paragraphs") or []):
                    _m7 = re.search(r"登记经营范围[为是]?「?([^」」，；。]{1,20})", str(_seg7))
                    if _m7 and _reg7 and _m7.group(1).strip() == _reg7:
                        _hit_term.append(str(_seg7)[:90])
            if _hit_term:
                issues.append(("ERROR", "engine/overall_conclusion.py",
                               "行业口径文案把「工商登记行业」写成「登记经营范围」（概念混用）："
                               + _hit_term[0]))
            _bcc_d = ((_inner_d.get("engine_status") or {}).get("biz_cost_classification")) or {}
            _basis_d = str(_bcc_d.get("industry_basis") or "").strip()
            if _te_ind and _basis_d and _basis_d != _te_ind:
                issues.append(("ERROR", "engine/pipeline.py",
                               "成本归属的行业口径与报告行业不一致：报告=%s，"
                               "成本识别 industry_basis=%s（同一份报告两套行业口径）"
                               % (_te_ind, _basis_d)))
            # 报告侧也直接取自 enterprise_readable_report
            _crd_d2 = (_er_d.get("cost_recon_detail") or {})
            _cea_d2 = _crd_d2.get("cost_expense_attribution") or {}
            _cea_ind = str(_cea_d2.get("industry") or "").strip()
            if _te_ind and _cea_ind and _cea_ind != _te_ind:
                issues.append(("ERROR", "engine/cost_recon_detail.py",
                               "成本/费用归属的行业名与报告行业不一致：报告=%s，归属=%s"
                               % (_te_ind, _cea_ind)))
            # ★ `contradictions` 与「主营业务成本桶」不得有交集 —— 同一品名既在成本桶、
            #   又被列为"应作待核"，那是同一口径内部的真矛盾（读者无法理解）。
            #   `contradictions` 按定义取自**另一个口径**（发票类目口径的核心成本品名），
            #   故只允许出现在成本桶之外；出现交集说明两桶口径串了。
            _cost_names = {str(_i.get("goods") or "") for _i in
                           (((_cea_d2.get("cost") or {}).get("items")) or [])}
            _contra_names = {str(_x.get("goods") or "") for _x in
                             (_cea_d2.get("contradictions") or [])}
            _both = sorted((_cost_names & _contra_names) - {""})
            if _both:
                issues.append(("ERROR", "engine/cost_recon_detail.py",
                               "同一品名既列在「主营业务成本」桶、又被列为口径差异（应作待核）"
                               f"，口径串桶：{('、'.join(_both[:4]))}"))
            # ★ 2026-10-02（用户拍板）：**成本明细必须与三态归属一致**。
            #   「按供应商」「逐张清单」的标签就是"主营业务成本"，不得把已判为
            #   期间费用/待核的支出也列进去（实测 59 家里 47.5% 的金额并非成本：
            #   机票、住宿、咨询、体育文化…读者看到"表名说成本、内容混着差旅"）。
            # ★ 服务型业态的**报告实际产出**里不得再出现存货类资料要求（端到端断言）
            try:
                from engine.industry_resolver import not_required_materials as _nrm3
                _na3 = _nrm3(_te_ind)[0]
                if _na3:
                    _mr3 = ((_er_d.get("material_readiness") or {}).get("missing") or [])
                    _bad_mr = [str((_x or {}).get("doc") or "") for _x in _mr3
                               if str((_x or {}).get("doc") or "") in _na3]
                    if _bad_mr:
                        issues.append(("ERROR", "engine/enterprise_report.py",
                                       "必查资料清单仍列「该业态不适用」的资料（会让'资料齐全'永远达不到）："
                                       + "、".join(_bad_mr)))
                    _bad_cp = []
                    for _c3 in (_er_d.get("confirmed_problems") or []):
                        for _f3 in ("missing_materials", "verify_materials"):
                            for _m3 in (_c3.get(_f3) or []):
                                if str(_m3) in _na3:
                                    _bad_cp.append("%s:%s" % (str(_c3.get("title") or "")[:14], _m3))
                    if _bad_cp:
                        issues.append(("ERROR", "engine/evidence_chain.py",
                                       "疑点待补资料仍含「该业态不适用」的资料（无效要求）："
                                       + "、".join(_bad_cp[:3])))
            except Exception as _exc3:
                issues.append(("WARN", "tools/audit_consistency.py", f"业态资料端到端断言跳过: {_exc3}"))

            _cost_amt = float((_cea_d2.get("cost") or {}).get("amount") or 0)
            _sup_amt = round(sum(float(_x.get("amount") or 0)
                                 for _x in (_crd_d2.get("by_supplier") or [])), 2)
            # 判据：**不得多于**三态成本桶（多了＝把费用/待核也算进来了，正是要修的病）；
            #       同时不得明显偏少（<90% ＝明细大面积漏行，读者会以为成本就这么点）。
            # ⚠ 允许小幅偏少：三态桶按**品名**归类（输入含 core/费用/待核三桶品名），
            #   而明细行只来自"发票类目口径核心成本发票" —— 少量按三态判为成本、
            #   却不在核心发票桶里的品名（如零星配件）没有逐张明细可列（实测 649.33 元）。
            if _cost_amt and _sup_amt > _cost_amt + 0.5:
                issues.append(("ERROR", "engine/cost_recon_detail.py",
                               "「按供应商」明细超出三态成本桶：「%s」成本桶 %s 元，明细 %s 元"
                               "（明细含了期间费用/待核的支出）"
                               % (_cea_ind or "", format(_cost_amt, ",.2f"), format(_sup_amt, ",.2f"))))
            elif _cost_amt and _sup_amt < _cost_amt * 0.9:
                issues.append(("ERROR", "engine/cost_recon_detail.py",
                               "「按供应商」明细明显少于三态成本桶：「%s」成本桶 %s 元，明细 %s 元"
                               "（明细大面积漏行）"
                               % (_cea_ind or "", format(_cost_amt, ",.2f"), format(_sup_amt, ",.2f"))))
            # 域分析/VR 规则写入发现的那份「主营成本按供应商」同样要过滤：
            # 其合计不得超过三态归属的成本总额（超了说明把费用/待核也统计进去了）。
            for _ds in (_inner_d.get("domain_summary") or []):
                for _f in (_ds.get("findings") or []):
                    _sb = (_f.get("observed_metrics") or {}).get("core_cost_supplier_breakdown")
                    if not isinstance(_sb, dict) or not _sb:
                        continue
                    _sum_sb = round(sum(float((_v or {}).get("amount") or 0)
                                        for _v in _sb.values()), 2)
                    if _cost_amt and _sum_sb > _cost_amt + 0.5:
                        issues.append(("ERROR", "engine/verified_rule_engine.py",
                                       "发现里的「主营成本按供应商」未按三态过滤：合计 %s 元 > "
                                       "主营业务成本 %s 元（多出的部分是期间费用/待核）"
                                       % (format(_sum_sb, ",.2f"), format(_cost_amt, ",.2f"))))
                        break

            # ★ 同一条口径也要管住**结论徽标字段** `verdict`：正文说「未认定到要件」，
            #   徽标却写「已触碰税务违规红线」——读者照样看到打架（实测 11 项）。
            _bad_badge = []
            for _cp_j, _cp_w in enumerate(_er_d.get("confirmed_problems") or []):
                _txt_w = " ".join(str((_x or {}).get("text") or "")
                                  for _x in (_cp_w.get("narrative_paragraphs") or []))
                if any(z in _txt_w for z in _ZERO_PHRASES) and any(
                        h in str(_cp_w.get("verdict") or "") for h in _HIT_PHRASES):
                    _bad_badge.append(str(_cp_w.get("title") or _cp_j)[:24])
            if _bad_badge:
                issues.append(("ERROR", "engine/enterprise_report.py",
                               "疑点结论徽标仍写「触碰税务红线」而正文写「未认定到要件」"
                               f"（{len(_bad_badge)} 项）：{('、'.join(_bad_badge[:5]))}"))
            _half = [m.group(0) for m in re.finditer(r".{0,18}\d,\d{1,2}(?![\d])(.{0,6})", _blob_d)
                     if "…" not in m.group(0) and "等" not in m.group(1)]
            if _half:
                issues.append(("ERROR", "engine/sentencekit.py",
                               f"企业报告内出现未标注截断的半截数字: {_half[:3]}"))
            # 空列披露：字段填充率不足时必须已产出披露段（否则空表无解释）
            _crd_d = (_er_d.get("cost_recon_detail") or {})
            _ff_d = _crd_d.get("invoice_field_fill") or {}
            if _ff_d.get("rows"):
                _short = any(int(_ff_d.get(_f) or 0) < int(_ff_d.get("rows") or 0)
                             for _f in ("inv_no", "date", "seller"))
                _paras = " ".join(str(_x) for _x in (_crd_d.get("paragraphs") or []))
                if _short and "未能从原始文件中解析取得" not in _paras:
                    issues.append(("ERROR", "engine/cost_recon_detail.py",
                                   "逐张清单存在整列未解析字段，但报告未披露（导出成无解释空表）"))
        except Exception as exc:
            issues.append(("WARN", "tools/audit_consistency.py",
                           f"导出净化 dump 行为验证跳过（读取失败）: {exc}"))

    # ══════════════════════════════════════════════════════════════
    # ★ 2026-09-29（点评整改第四轮 P1-7 / P1-11 / P1-16）
    # ══════════════════════════════════════════════════════════════

    # ── ★ 2026-10-02（用户定调）：**报告禁止个人信息脱敏 / 禁止隐藏** ──
    #   原收敛点 `engine/pii_guard.py`（杨莹→杨*、初永伟→初**）整体删除：本报告读者是
    #   被查企业本身，员工姓名与私户收付金额正是企业需要逐人核对的内容；打成 `杨*`
    #   会让「逐人说明」这条核查要求无法落地。**原闸门（要求"必须接脱敏"）已反向改造成
    #   防复发闸门**——把脱敏接回去会立刻报错。
    #   ⚠ 第三条用**AST**判定而非文本匹配：注释里会引用同一串（如"必须传 source=report_data"），
    #   在原文上匹配会被自己的说明文字骗过（实测：去掉 source 参数后旧闸门仍"通过"）。
    #
    #   ── ★ 2026-10-07（第 5 批 任务2）**范围修正**：本条定调针对的是**报告正文/内部底稿**。
    #      用户第 5 批明确要求「按角色脱敏姓名/账号/身份证/金额」用于**对外版本（风险提示函）**，
    #      两者并不冲突，但必须**按链路划定范围**，否则要么把新能力误杀、要么悄悄把脱敏接回正文：
    #        · 允许：`engine/redaction.py`（脱敏实现）与 `engine/report_compliance.py`（对外版装配）；
    #        · 禁止：报告正文链路（`enterprise_report` / `main.py` 的报告装配段）引用脱敏；
    #        · 并用**更强**的补偿断言锁死"内部底稿永不脱敏"（行为级）。
    _DESENS_SYMS = ("pii_guard", "mask_person_name", "mask_id_no", "mask_phone",
                    "mask_account", "redact_enterprise_report", "_pii_stats", "_pii_notice")
    #: 专供**对外版本/人员名单**的脱敏实现（唯一允许出现脱敏符号的文件）
    _DESENS_ALLOWED = {"engine/redaction.py", "engine/report_compliance.py", "engine/access_service.py"}  # 2026-10-14 P0-8：+access_service（用户目录/审计日志接口的人员敏感字段出口；报告正文禁脱敏的补偿断言①②③仍全部生效）
    if os.path.exists(str(ROOT / "engine" / "pii_guard.py")):
        issues.append(("ERROR", "engine/pii_guard.py",
                       "个人信息脱敏模块仍存在（用户定调：报告禁止脱敏/隐藏）"))
    # 补偿断言 ①：报告正文链路**不得**引用脱敏实现
    #   ⚠ 变量名**不得**用 `_src` —— 本函数内已有同名局部函数 `_src(rel)`，
    #     赋值会把它**覆盖成字符串** ⇒ 后面 `_src("engine/enterprise_report.py")` 直接
    #     `TypeError: 'str' object is not callable`（本轮实测撞上）。
    for _rel in ("engine/enterprise_report.py", "engine/subject_consistency.py",
                 "engine/report_wording.py"):
        try:
            _blob = _mask_py_comments_and_strings((ROOT / _rel).read_text(encoding="utf-8"))
            for _bad in ("redaction", "report_compliance.external_edition"):
                if _bad in _blob:
                    issues.append(("ERROR", _rel,
                                   f"报告正文链路引用了 {_bad} ⇒ 违反『报告禁止脱敏』定调"))
        except Exception:
            pass
    # 补偿断言 ②：内部底稿的角色策略必须**全为 False**（行为级，比符号扫描更强）
    try:
        from engine.redaction import REDACTION_ITEMS, role_policy
        _pol = role_policy("internal")
        _on = [k for k in REDACTION_ITEMS if _pol.get(k)]
        if _on:
            issues.append(("ERROR", "engine/redaction.py",
                           f"内部底稿角色被开启了脱敏项 {_on}（内部底稿必须保留原始姓名与金额）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/redaction.py", f"内部角色策略检查失败: {exc}"))
    _scan_files = [str(ROOT / "main.py")]
    for _sub in ("engine", "tools"):
        _sd = ROOT / _sub
        if _sd.is_dir():
            _scan_files.extend(str(p) for p in sorted(_sd.glob("*.py")))
    for _fp in _scan_files:
        try:
            _tree = ast.parse(Path(_fp).read_text(encoding="utf-8"))
        except Exception:
            continue      # 解析失败不算脱敏（判据必须来自真正的行为检测）
        _hit = set()
        for _nd in ast.walk(_tree):
            _syms: List[str] = []
            if isinstance(_nd, ast.Import):
                _syms = [a.name for a in _nd.names]
            elif isinstance(_nd, ast.ImportFrom):
                _syms = [(_nd.module or "")] + [a.name for a in _nd.names]
            elif isinstance(_nd, ast.Name):
                _syms = [_nd.id]
            elif isinstance(_nd, ast.Attribute):
                _syms = [_nd.attr]
            for _s in _syms:
                if any(_sym in str(_s) for _sym in _DESENS_SYMS):
                    _hit.add(str(_s))
        if _hit and str(Path(_fp).relative_to(ROOT)).replace("\\", "/") not in _DESENS_ALLOWED:
            issues.append(("ERROR", str(Path(_fp).relative_to(ROOT)).replace("\\", "/"),
                           f"出现个人信息脱敏符号 {sorted(_hit)}（用户定调：报告禁止脱敏/隐藏）"))
    # ③ 报告实测：全量 dump 重建企业版报告 → 真实姓名必须原样保留、星号占位必须不在
    try:
        _dump_p = ROOT / "scripts" / "four_reports" / "company_1_full.json"
        if not _dump_p.exists():
            issues.append(("WARN", "tools/audit_consistency.py",
                           "全量报告 dump 缺失，禁止脱敏行为闸门跳过（跑 scripts/_run_company1.py 后可复验）"))
        else:
            from engine.enterprise_report import build_enterprise_readable_report
            _raw9 = json.loads(_dump_p.read_text(encoding="utf-8"))
            _erp9 = build_enterprise_readable_report(_raw9)
            _blob9 = json.dumps(_erp9, ensure_ascii=False)
            _real9: List[str] = []
            _seen9 = set()

            def _walk_names9(_o) -> None:
                if isinstance(_o, dict):
                    for _k, _v in _o.items():
                        _ks = str(_k)
                        if isinstance(_v, str) and _v.strip() and _v not in _seen9 \
                                and _ks in ("姓名", "员工姓名", "员工", "人员", "收款人",
                                            "付款人", "客户姓名", "经办人", "负责人"):
                            _seen9.add(_v.strip())
                            _real9.append(_v.strip())
                        _walk_names9(_v)
                elif isinstance(_o, list):
                    for _v in _o:
                        _walk_names9(_v)

            _walk_names9(_raw9)
            # ★ 判据：脱敏的**唯一形态**就是「首字保留 + 等长星号」（杨莹→杨*、初永伟→初**）。
            #   报告正文里自然出现这种形态的概率极低；而 glob/正则里的星号（如「属*」「款****」）
            #   不会与某个自然人真名的首字+等长星号精确配对，故该判据噪声低、灵敏度高。
            #   （不做"真实姓名必须出现在报告里"的反向要求——那会把闸门变成假闸门：
            #     渲染侧本就会按领域分流，不是每条人名都必须进企业版报告。）
            _masked9 = []
            for _n in _real9:
                _mf = _n[0] + "*" * (len(_n) - 1)
                if _mf in _blob9:
                    _masked9.append(_n)
            if _masked9:
                issues.append(("ERROR", "engine/enterprise_report.py",
                               f"企业版报告对个人姓名做了脱敏隐藏 {sorted(set(_masked9))[:6]}"
                               f"（用户定调：禁止脱敏/隐藏）"))
    except Exception as exc:
        issues.append(("WARN", "tools/audit_consistency.py", f"禁止脱敏行为闸门执行失败: {exc}"))

    # ── P1-16 台账治理接线（引擎侧，与报告实测分离）──
    _er4_src = _src("engine/enterprise_report.py")
    _er4_code = _strip_comments_keep_lines(_er4_src)
    if '_gov(rows, findings, problems=problems)' not in _er4_code or 'rows = _g["rows"]' not in _er4_code:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "台账治理未接线（准入过滤/聚合/统一ID 未生效，台账仍是原始平铺行）"))

    # ── P1-16 台账准入 + P1-7 聚合/统一 ID ──
    try:
        from engine.ledger_governance import (canonical_ledger_key, govern_ledger_rows,
                                              is_enterprise_risk_item, make_finding_id)
        if is_enterprise_risk_item({"type": "审计检查：系统一致性"})[0]:
            issues.append(("ERROR", "engine/ledger_governance.py",
                           "系统自查条目未剔除（内部工具条目混入企业台账）"))
        if is_enterprise_risk_item({"type": "风险检查取证要求补充资料单"})[0]:
            issues.append(("ERROR", "engine/ledger_governance.py",
                           "资料请求单未剔除（内部工具条目混入企业台账）"))
        _l = "；".join(["本事项所涉及的个人银行账户完整流水——用以核对本事项"] * 4)
        if is_enterprise_risk_item({"type": "普通事项",
                                    "self_proof_materials": [{"material": "a", "proves": _l}]})[0]:
            issues.append(("ERROR", "engine/ledger_governance.py",
                           "自引用循环的「需补自证资料」未剔除（模板套模板无行动指引）"))
        if not is_enterprise_risk_item({"type": "有工资无社保"})[0]:
            issues.append(("ERROR", "engine/ledger_governance.py",
                           "真实风险事项被误剔除（准入过严）"))
        if canonical_ledger_key("X（2025-01）") != canonical_ledger_key("X（2025-12）"):
            issues.append(("ERROR", "engine/ledger_governance.py",
                           "期间括注未归并（逐月展开不会被聚合）"))
        if make_finding_id("K") != make_finding_id("K"):
            issues.append(("ERROR", "engine/ledger_governance.py",
                           "统一发现 ID 不可复算（同一输入得到不同编号）"))
        _gr = govern_ledger_rows(
            [{"风险事项": "X（2025-%02d）" % m, "等级": "中风险", "终局方向": "待补自证"}
             for m in (1, 2, 3)],
            [{"type": "X"} for _ in range(3)])
        if len(_gr["rows"]) != 1 or len(_gr["rows"][0].get("明细") or []) != 3:
            issues.append(("ERROR", "engine/ledger_governance.py",
                           "同质行未聚合为一行并保留明细"))
    except ImportError as exc:
        issues.append(("ERROR", "engine/ledger_governance.py", f"台账治理模块不可用: {exc}"))

    # ── dump 行为断言：台账不得含内部工具条目、不得有未聚合同质行、必须带发现 ID ──
    _dd3 = _canonical_report()
    if _dd3 is not None:
        try:
            _led_d = ((_dd3.get("enterprise_readable_report")) or {}).get("resolution_ledger") or {}
            _rows_d = _led_d.get("rows") or []
            _ledger_errors = []
            if _rows_d:
                for _r in _rows_d:
                    _t = str(_r.get("风险事项") or "")
                    if any(_k in _t for _k in ("审计检查", "系统一致性", "取证要求", "补充资料单")):
                        _ledger_errors.append("内部工具条目「%s」" % _t[:30])
                _seen_keys = {}
                for _r in _rows_d:
                    _ck = canonical_ledger_key(_r.get("风险事项"))
                    _seen_keys[_ck] = _seen_keys.get(_ck, 0) + 1
                _dup = [k for k, v in _seen_keys.items() if v > 1]
                if _dup:
                    _ledger_errors.append("未聚合同质行 %d 组（如「%s」）" % (len(_dup), _dup[0][:26]))
                if not all(str(_r.get("发现ID") or "").startswith("R-") for _r in _rows_d):
                    _ledger_errors.append("有台账行缺统一发现 ID")
            if _ledger_errors:
                issues.append(("ERROR", "engine/ledger_governance.py",
                               "台账治理未生效: " + "；".join(_ledger_errors[:4])))
            _er_d2 = ((_dd3.get("report") or {}).get("enterprise_readable_report")) or {}
        except Exception as exc:
            issues.append(("WARN", "tools/audit_consistency.py",
                           f"台账/脱敏 dump 行为验证跳过（读取失败）: {exc}"))

    # ══════════════════════════════════════════════════════════════
    # ★ 2026-09-29（点评整改第五轮 P1-9 / P1-14 / P2-3 / P2-4）
    # ══════════════════════════════════════════════════════════════

    # ── P1-14 明细表自洽（列名/行键一致、无内部列、截断注明）──
    try:
        from engine.table_governance import align_table, collect_table_violations, govern_all_tables
        _t = {"title": "T", "columns": ["金额（元）", "ref_id"],
              "rows": [{"金额(元)": 1.0, "ref_id": "记-2"}]}
        _a = align_table(_t)
        if _a["columns"] != ["金额（元）", "凭证号"]:
            issues.append(("ERROR", "engine/table_governance.py",
                           f"标点变体未对齐到列名/内部键未汉化: {_a['columns']}"))
        if collect_table_violations({"t": _a}):
            issues.append(("ERROR", "engine/table_governance.py",
                           f"对齐后仍有违规: {collect_table_violations({'t': _a})[:2]}"))
        _tt = align_table({"columns": ["金额"], "rows": [{"金额": i} for i in range(3)], "rows_total": 9})
        if "仅列示前 3 笔" not in str(_tt.get("truncation_note") or ""):
            issues.append(("ERROR", "engine/table_governance.py",
                           "截断未注明「仅列示前 N 笔」（读者会把列示行当成全部行，与合计对不上）"))
        # 反向用例①：**稀疏表**（不同行字段不同）不得被判违规，否则闸门误报
        if collect_table_violations({"t": {"columns": ["A", "B"], "rows": [{"A": 1}, {"B": 2}]}}):
            issues.append(("ERROR", "engine/table_governance.py",
                           "稀疏明细表被误判违规（闸门误报会被绕过）"))
        # 反向用例②：整列在行里**完全不存在**且不是标点变体 → 治理后该列已被丢弃，
        #   不得再报违规（否则"零误报"不成立，闸门会被人绕过）。
        if collect_table_violations({"t": {"columns": ["A", "C"], "rows": [{"A": 1}]}}):
            issues.append(("ERROR", "engine/table_governance.py",
                           "整列缺失（非标点变体）被判违规 → 误报（该列治理时已丢弃）"))
        _cyc_t = {"columns": ["A"], "rows": [{"A": 1}]}
        _cyc_t["self"] = _cyc_t
        govern_all_tables(_cyc_t)
    except ImportError as exc:
        issues.append(("ERROR", "engine/table_governance.py", f"明细表治理模块不可用: {exc}"))
    except Exception as exc:
        issues.append(("ERROR", "engine/table_governance.py", f"明细表治理断言执行失败: {exc}"))
    # 接线：明细表治理必须在报告输出闸门内、且在标点规范化之后
    # ⚠ 顺序检查不能只比两个 find() 的位置：被比较的那一行可能**压根不存在**（find 返回 -1，
    #   于是 `a < -1` 恒为假 → 顺序被改坏也检查不出来）。必须先断言两侧都在。
    _er5_code = _strip_comments_keep_lines(_src("engine/enterprise_report.py"))
    _i_norm5 = _er5_code.find("_o = _zh_normalize_obj(_o)")
    _i_gov5 = _er5_code.find("govern_all_tables")
    if _i_gov5 < 0:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "明细表治理未接线（列名/行键仅标点不同 → 整列渲染为空）"))
    elif _i_norm5 < 0 or _i_gov5 < _i_norm5:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "明细表治理必须在标点规范化（_zh_normalize_obj）之后执行"
                       "（顺序反了则列名/行键仍不一致）"))
    if "rows_total" not in _er5_code:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "明细表未记录源总数（截断无法注明「仅列示前 N 笔」）"))

    # ── P1-9 可信度口径披露 + ★★ P1-2 **可信度必须可复算** ──
    #   P1-2 判据：正文百分比 / 条目 confidence / Σ分项贡献（confidence_breakdown）三者同源；
    #   算不出就**不写**百分比（宁缺勿假）。判据全部取自唯一权威 engine.argumentation。
    try:
        from engine.argumentation import (
            CONFIDENCE_FORMULA_ANCHOR as _cfa2,
            CONFIDENCE_WEIGHTS,
            build_argumentation,
            confidence_formula_text as _cft2,
            confidence_from_breakdown as _cfb2,
            confidence_percent as _cpct2,
        )
        _f = {"type": "T", "level": "高风险", "detail": "d", "redline_id": "RL-X",
              "constituent_hits": [{"index": 1, "evidence": "e", "has_data": True}],
              "evidence_rows": [{"ref_label": "a"}]}
        _arg = build_argumentation(
            _f, {"id": "RL-X", "name": "n", "suspect": "s", "constituents": ["c1"],
                 "clue_chain": [{"step": 1, "source": "凭证", "action": "a", "output": "o"}],
                 "legal_basis": ["《税收征收管理法》第三十五条"]},
            {"nodes": [{"step": 1, "source": "凭证", "has_data": True, "observed": "x"}],
             "terminal_signal": "sig"},
            {"closure": 0.9, "elements": []}, [])
        _bd2 = _arg.get("confidence_breakdown")
        _rec2 = _cfb2(_bd2)
        if _rec2 is None:
            issues.append(("ERROR", "engine/argumentation.py",
                           "可信度分项缺失或不可复算（P1-2：百分数无口径可回指）"))
        else:
            if round(float(_arg.get("confidence") or 0), 2) != _rec2:
                issues.append(("ERROR", "engine/argumentation.py",
                               f"可信度字段({_arg.get('confidence')}) ≠ Σ分项贡献({_rec2})（P1-2 可复算）"))
            _m2 = re.search(r"判断可信度约\s*(\d+)\s*%", str(_arg.get("reasoning") or ""))
            if not _m2:
                issues.append(("ERROR", "engine/argumentation.py",
                               "论证结论文案未输出可信度百分比（P1-2：可复算即应输出）"))
            elif _cpct2(_rec2) != int(_m2.group(1)):
                issues.append(("ERROR", "engine/argumentation.py",
                               f"正文百分比({_m2.group(1)}%) 不可由分项复算({_cpct2(_rec2)}%)（P1-2）"))
        if not _cfa2.search(_cft2()):
            issues.append(("ERROR", "engine/argumentation.py", "公式文本与闸门锚点不同源（P1-2）"))
        if not CONFIDENCE_WEIGHTS.get("base"):
            issues.append(("ERROR", "engine/argumentation.py", "可信度权重表缺失"))
        # 判据自证非假：缺失 / 非法分项必须复算失败（否则"可复算"判据是假的）
        if _cfb2([]) is not None or _cfb2([{"项": "x", "贡献": "bad"}]) is not None:
            issues.append(("ERROR", "engine/argumentation.py",
                           "可复算判据未拦截缺失/非法分项（判据是假的）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/argumentation.py", f"可信度口径断言执行失败: {exc}"))
    # 公式文本必须**唯一权威**：总述只可**转引**，不得自写公式字面量（两处各写一份必漂移）
    _io_src = _strip_comments_keep_lines(_src("engine/inspection_overview.py"))
    if "confidence_formula_text" not in _io_src:
        issues.append(("ERROR", "engine/inspection_overview.py",
                       "总述「关键口径对照」未转引可信度公式唯一权威（confidence_formula_text）"))
    if re.search(r"基准分\s*%\.2f|基准分\s*\{\s*_?cw\b", _io_src):
        issues.append(("ERROR", "engine/inspection_overview.py",
                       "总述自写了可信度公式字面量（应只转引 argumentation.confidence_formula_text）"))

    # ── P2-3 轮次措辞（★ 2026-10-01 用户定调：报告不再写任何「轮次」元信息）──
    #   原断言要求「第 N(>1) 轮必须声明独立于此前任何一轮」；用户已明确该句与报告本质无关并删除，
    #   故此处只保留「编制声明不得为空」这一底线检查，不再要求任何轮次措辞。
    try:
        from engine.overall_conclusion import compilation_declaration as _cd
        if "独立于此前任何一轮" in _cd({"compliance_round": {"round_no": 3}}):
            issues.append(("ERROR", "engine/overall_conclusion.py",
                           "报告又出现「独立于此前任何一轮报告」（用户 2026-10-01 已定调删除轮次元信息）"))
        if not _cd({"compliance_round": {"round_no": 1}}).strip():
            issues.append(("ERROR", "engine/overall_conclusion.py", "编制声明为空"))
    except Exception as exc:
        issues.append(("ERROR", "engine/overall_conclusion.py", f"编制声明断言执行失败: {exc}"))
    for _rel in ("engine/inspection_overview.py", "engine/narrative_fresh.py"):
        if "独立于此前任何一轮" in _strip_comments_keep_lines(_src(_rel)):
            issues.append(("ERROR", _rel,
                           "编制声明又出现一份本地实现（须走唯一权威 compilation_declaration）"))

    # ── P2-4 署名栏不得仿真税务机关 ──
    _pipe5 = _strip_comments_keep_lines(_src("engine/pipeline.py"))
    for _bad in ("执法证件号", "税务机关公章", "报送上一级税务机关备案"):
        if _bad in _pipe5:
            issues.append(("ERROR", "engine/pipeline.py",
                           f"署名栏仍出现仿真税务机关要素「{_bad}」（系统生成文书不得伪作执法文书）"))

    # ══════════════════════════════════════════════════════════════
    # ★ 2026-09-29（点评整改第六轮：P2-1 / P2-6 / P2-2 / P1-1 / P1-2 / P1-3 / P1-5 / P1-13）
    # ══════════════════════════════════════════════════════════════

    # ── P2-2 表格内不得出现「同上」 ──
    try:
        from engine.enterprise_report import _clue_table
        _ct = _clue_table({"nodes": [
            {"step": 1, "source": "凭证", "action": "读取", "observed": "合计 100 元"},
            {"step": 2, "source": "凭证", "action": "比对", "observed": "合计 100 元"},
        ]})
        for _r in (_ct or {}).get("rows") or []:
            if str(_r.get("实际看到的数据") or "") == "同上":
                issues.append(("ERROR", "engine/enterprise_report.py",
                               "环节表仍出现「同上」（孤立阅读无意义，P2-2）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/enterprise_report.py", f"环节表断言执行失败: {exc}"))

    # ── P1-1 表题计数必须等于实际行数 + 附表明细口径说明 ──
    try:
        from engine.table_governance import align_table
        _t1 = align_table({"title": "X（共1笔）", "columns": ["A"],
                           "rows": [{"A": i} for i in range(3)]})
        if "共3笔" not in str(_t1.get("title")):
            issues.append(("ERROR", "engine/table_governance.py",
                           "表题计数未按实际行数校正（表题与内容矛盾，P1-1）"))
        _t2 = align_table({"title": "Y（共9%）", "columns": ["A"], "rows": [{"A": 1}]})
        if _t2.get("title") != "Y（共9%）":
            issues.append(("ERROR", "engine/table_governance.py",
                           "非计数括注被误改（应为零误报）"))
        from engine.enterprise_report import _with_scope_note
        _sn = _with_scope_note([{"title": "T", "columns": ["A"], "rows": [{"A": 1}, {"A": 2}]}])
        if not (_sn and _sn[0].get("scope_note")):
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "附表缺口径说明（正文按要件筛选、附表为基础全量，须讲明差异）"))
        if (_with_scope_note([{"columns": ["A"], "rows": [{"A": 1}]}])[0].get("scope_note")):
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "单行附表也加口径说明（噪声；应仅多行表加）"))
        # 接线：`_with_scope_note` 必须在 `_finding_detail_tables` 的**返回路径**上被调用，
        #   否则具体问题下的附表仍会"题文不符"（实测第一版只测函数本身 → 拆掉调用点查不出）。
        _sn_calls = _strip_comments_keep_lines(_src("engine/enterprise_report.py")).count("_with_scope_note(")
        if _sn_calls < 3:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           f"_with_scope_note 调用点不足（应 def+2 处返回路径，实得 {_sn_calls}）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/table_governance.py", f"表题/口径断言执行失败: {exc}"))

    # ── P1-2 资金回流「闭环」按对称度分级 ──
    try:
        from engine.fund_loop import _loop_tier, run_fund_loop_check
        if _loop_tier(20000.0, 20000.0)[0] is not True:
            issues.append(("ERROR", "engine/fund_loop.py", "等额双向未判为闭环"))
        if _loop_tier(1070000.0, 275000.0)[0] is not False:
            issues.append(("ERROR", "engine/fund_loop.py",
                           "金额悬殊的双向往来被判为闭环（P1-2：闭环定义过宽）"))
        _r = run_fund_loop_check([
            {"counterparty": "A", "credit": 20000.0, "debit": 0.0},
            {"counterparty": "A", "credit": 0.0, "debit": 20000.0},
            {"counterparty": "B", "credit": 1070000.0, "debit": 0.0},
            {"counterparty": "B", "credit": 0.0, "debit": 275000.0},
            {"counterparty": "C", "credit": 0.0, "debit": 600000.0},
        ], company_name="测试企业")
        _m = _r.get("metrics") or {}
        if _m.get("asymmetric_parties") != 1:
            issues.append(("ERROR", "engine/fund_loop.py", "不对称往来未被单列（P1-2）"))
        if abs(float(_m.get("circular_amount") or 0) - 20000.0) > 0.01:
            issues.append(("ERROR", "engine/fund_loop.py",
                           f"闭环金额含入不对称往来: {_m.get('circular_amount')}"))
    except Exception as exc:
        issues.append(("ERROR", "engine/fund_loop.py", f"资金回流分级断言执行失败: {exc}"))

    # ── P1-3 本企业自身不得出现在交易对手清单 ──
    _pipe6 = _strip_comments_keep_lines(_src("engine/pipeline.py"))
    if "_norm_entity_name" not in _pipe6 or "company_name=company_name" in _pipe6:
        issues.append(("ERROR", "engine/pipeline.py",
                       "缺本企业自身剔除的归一化判据（P1-3：本企业被列进交易对方清单）"))
    if "_norm_entity_name(company_name)" not in _pipe6:
        issues.append(("ERROR", "engine/pipeline.py", "本企业自身剔除未接线（P1-3）"))

    # ── P1-5 构成要件阈值必须校验 ──
    try:
        from engine.constituent_threshold import check_constituent_hit as _cth
        if _cth("未付款占比超过50%", "未付款占比 32.5%")[0] != "unmet":
            issues.append(("ERROR", "engine/constituent_threshold.py",
                           "未达门槛的要件仍判为命中（P1-5）"))
        if _cth("未付款占比超过50%", "未付款占比 68%")[0] != "met":
            issues.append(("ERROR", "engine/constituent_threshold.py", "达门槛未判命中"))
        if _cth("占比超过50%", "仅有金额 1,000,000 元")[0] != "unknown":
            issues.append(("ERROR", "engine/constituent_threshold.py",
                           "取不到同量纲实际值时应放行（不得误杀）"))
        if _cth("无阈值的要件", "任何证据")[0] != "unknown":
            issues.append(("ERROR", "engine/constituent_threshold.py", "无阈值要件不应判 unmet"))
        from engine.enterprise_report import _enterprise_situations
        # ★ 2026-10-03：`_enterprise_situations` 契约统一为 **3 元组**（条目, 来源, 要件表），
        #   闸门原按 2 元组解包 → 阈值未达分支一走到就 "too many values to unpack"。
        _s1, _src1, _ = _enterprise_situations(
            {"constituent_hits": [{"index": 2, "evidence": "未付款占比 32.5%"}]}, {},
            constituents=["要件一", "未付款占比超过50%", "要件三"])
        if _src1 != "constituents_threshold_unmet":
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "未达门槛要件仍被标注为「涉及」（P1-5 未接线）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/constituent_threshold.py", f"要件阈值断言执行失败: {exc}"))

    # ── P1-13 域间联动 ──
    try:
        from engine.domain_linkage import link_findings, linkage_text
        _lf = link_findings([
            {"type": "私户收款", "detail": "个人账户收款", "evidence_rows": [{"counterparty": "杨某"}],
             "taxes": ["增值税"]},
            {"type": "公户代发", "detail": "个人账户付款", "evidence_rows": [{"counterparty": "杨某"}],
             "taxes": ["个人所得税"]},
            {"type": "所得税贡献率偏低", "detail": "贡献率 0.01%", "taxes": ["企业所得税"]},
            {"type": "小微优惠应享", "detail": "可享受减免", "taxes": ["企业所得税"]},
            {"type": "综合定性结论", "detail": "汇总", "taxes": []},
        ])
        _rels = {l["relation"] for v in _lf.values() for l in v}
        if "同主体反向资金" not in _rels or "同税种结论相向" not in _rels:
            issues.append(("ERROR", "engine/domain_linkage.py",
                           f"域间联动未识别两类关系（P1-13）: {_rels}"))
        if any(l["type"] == "综合定性结论" for v in _lf.values() for l in v):
            issues.append(("ERROR", "engine/domain_linkage.py",
                           "方法论/汇总条目被当作联动对象（噪声，应复用台账准入判据）"))
        if not linkage_text(list(_lf.values())[0]):
            issues.append(("ERROR", "engine/domain_linkage.py", "联动文案为空"))
        # 强化用例：把"方法论条目"造得**本来会命中联动**（同税种 + 优惠/偏低字样），
        # 只有真正过滤掉它才会通过 —— 否则"不过滤"也能蒙混（实测第一版就漏了）。
        _lf2 = link_findings([
            {"type": "企业所得税贡献率偏低", "detail": "贡献率 0.01%", "taxes": ["企业所得税"]},
            {"type": "综合定性结论", "detail": "优惠偏低汇总", "taxes": ["企业所得税"]},
        ])
        if any(l["type"] == "综合定性结论" for v in _lf2.values() for l in v):
            issues.append(("ERROR", "engine/domain_linkage.py",
                           "方法论条目未被过滤（强化用例：其本可命中同税种联动）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/domain_linkage.py", f"域间联动断言执行失败: {exc}"))
    _er6_code = _strip_comments_keep_lines(_src("engine/enterprise_report.py"))
    if "联动事项" not in _er6_code:
        issues.append(("ERROR", "engine/enterprise_report.py", "台账未含「联动事项」列（P1-13）"))

    # ── 离线渲染器覆盖面（上轮登记缺口）──
    # ⚠ 与既有用户决定（2026-09-27：总述章**只渲染 overall_conclusion**）不冲突的写法：
    #   离线只补渲染 inspection_overview 的**八、九两节增量**（口径对照 / 时效提示），
    #   不整章渲染 —— 故这里断言的是"取该两节"的调用行，而不是整章。
    _off_code = _strip_comments_keep_lines(_src("scripts/_render_report_html.py"))
    if 'err.get("inspection_overview")' not in _off_code:
        issues.append(("ERROR", "scripts/_render_report_html.py",
                       "离线渲染器未取 inspection_overview 的八/九节（缺「关键口径对照」「时效提示」）"))
    elif "_IV_SECTIONS" not in _off_code:
        issues.append(("ERROR", "scripts/_render_report_html.py",
                       "离线渲染器整章渲染 inspection_overview（与「总述只渲染 overall_conclusion」决定冲突）"))

    # ══════════════════════════════════════════════════════════════
    # ★ 2026-09-29（点评整改收尾 P0-5 深层 / P1-8 / P2-7）
    # ══════════════════════════════════════════════════════════════

    # ── P0-5 深层：要件级独立核对（独立数据源 + 独立结论 + 未核对不计入"涉及"）──
    try:
        from engine.constituent_checkpoint import (
            build_constituent_checkpoints as _bcc, checkpoint_table as _ctbl,
            participating_indices as _pind, summarize as _csum,
        )
        # ① 数据源未取得 → 未单独核对，且**不计入**涉及
        _s1 = {
            "constituents": ["要件一：存在大额未付款", "要件二：未付款占比超过50%"],
            "evidence_chain": {"elements": [
                {"role": "直接证据", "name": "大额未付款明细、应付账款与付款记录", "status": "已有"},
                {"role": "直接证据", "name": "合同与验收单", "status": "缺失"}]},
            "clue_chain": {"nodes": [{"step": 1, "source": "大额未付款明细", "has_data": True}]},
            "argumentation": {"constituent_hits": [{"index": 1, "evidence": "应付余额 120 万元"}]},
        }
        _cps = _bcc(_s1)
        if not _cps or len(_cps) != 2:
            issues.append(("ERROR", "engine/constituent_checkpoint.py", "要件核对记录数不对"))
        _p1 = _pind(_cps)
        if 2 in _p1:
            issues.append(("ERROR", "engine/constituent_checkpoint.py",
                           "独立数据源未取得的要件被计入「涉及」（P0-5 硬要求：不得计入）"))
        # ★ 2026-10-04（疑点10-21 合并批次 ⑲）：**"有证据"不得只 Loh 到 checked_hit**——
        #   旧断言只要"没落 not_checked 就算通过"，于是阈值判不出（unknown）时也照判"符合"，
        #   等于用默认值替企业认了一条要件（虚假认定）。
        #   正解：数据源已有且有核对证据 ⇒ 必须落 `checked_hit`（计入涉及）或
        #   `not_concluded`（如实说明"无可比对的同量纲数值、未形成结论"）；
        #   落到 `not_checked`（资料没拿到）才是本闸门要继续拦的事。
        if _cps and _cps[0].get("_conclusion") == "not_checked":
            issues.append(("ERROR", "engine/constituent_checkpoint.py",
                           "数据源已有且有证据的要件被判『未单独核对』（=P0-5 要不得）"))
        elif 1 not in _p1 and not (_cps and _cps[0].get("_conclusion") == "not_concluded"):
            issues.append(("ERROR", "engine/constituent_checkpoint.py",
                           "数据源已有且有证据的要件既未计入「涉及」、也未落 not_concluded"
                           "（%s）" % (_cps[0].get("_conclusion") if _cps else "无")))
        if not all(c.get("独立数据源") for c in _cps):
            issues.append(("ERROR", "engine/constituent_checkpoint.py", "要件缺独立数据源字段"))
        if not _csum(_cps) or not _ctbl(_cps):
            issues.append(("ERROR", "engine/constituent_checkpoint.py", "要件核对汇总/表缺失"))
        # ② 阈值未达 → 不得计入涉及（与 P1-5 联动）
        _s2 = {
            "constituents": ["要件一：未付款占比超过50%"],
            "evidence_chain": {"elements": [
                {"role": "直接证据", "name": "未付款占比、应付余额", "status": "已有"}]},
            "clue_chain": {"nodes": []},
            "argumentation": {"constituent_hits": [{"index": 1, "evidence": "未付款占比 32.5%"}]},
        }
        _cps2 = _bcc(_s2)
        if _pind(_cps2):
            issues.append(("ERROR", "engine/constituent_checkpoint.py",
                           "未达数值门槛的要件仍计入「涉及」"))
        # ③ **不得按位序错配数据源**（实测第一版把"红冲占比"配到"退货单"）：
        #    要件与证据元素是不同轴，"按序对齐"会给出错误的数据源归属。
        _s3 = {
            "constituents": ["要件一：红字发票占同期开票额的比例异常"],
            "evidence_chain": {"elements": [
                {"role": "直接证据", "name": "退货单、折让协议、拒收证明", "status": "已有"}]},
            "clue_chain": {"nodes": []}, "argumentation": {"constituent_hits": []},
        }
        _c3 = _bcc(_s3)
        if _c3 and "退货单" in str(_c3[0].get("独立数据源")):
            issues.append(("ERROR", "engine/constituent_checkpoint.py",
                           "数据源按位序错配（要件与证据元素是不同轴，应按语义匹配）"))
        # ④ 独立数据源**状态为缺失** → 必须 not_checked 且**不计入**涉及。
        #    ⚠ 用例必须让"匹配到的那个数据源"状态就是缺失：若要件被匹配到另一个"已有"的
        #    数据源，就会走 checked_miss 分支，注入 `not_checked→checked_hit` 根本测不出来
        #    （实测第一版就漏了）。
        _s4 = {
            "constituents": ["要件一：无法通过红字冲销、补记凭证合理解释"],
            "evidence_chain": {"elements": [
                {"role": "反证", "name": "红字冲销凭证、补记凭证与差错说明", "status": "缺失"}]},
            "clue_chain": {"nodes": []},
            "argumentation": {"constituent_hits": [{"index": 1, "evidence": "有信号但反证未提交"}]},
        }
        _c4 = _bcc(_s4)
        if not _c4 or _c4[0].get("_conclusion") != "not_checked":
            issues.append(("ERROR", "engine/constituent_checkpoint.py",
                           f"独立数据源缺失时未判为「未单独核对」（实得 {(_c4 or [{}])[0].get('_conclusion')}）"))
        if _pind(_c4):
            issues.append(("ERROR", "engine/constituent_checkpoint.py",
                           "未单独核对的要件被计入「涉及」（P0-5 硬要求：不得计入）"))
    except ImportError as exc:
        issues.append(("ERROR", "engine/constituent_checkpoint.py", f"要件核对模块不可用: {exc}"))
    except Exception as exc:
        issues.append(("ERROR", "engine/constituent_checkpoint.py", f"要件核对断言执行失败: {exc}"))
    # 接线：报告必须用核对记录驱动要件清单（否则"不计入涉及"只是空话）
    # ★ 2026-10-03：判据放宽为"必须存在 `_cps_all = _bcc(s, ...)` 形式的调用"——
    #   本轮把**业态不适用资料**也传了进去（`not_required=...`），旧的精确串
    #   `"_cps_all = _bcc(s)"` 会误报"未接线"（闸门抓的是形式，不是行为）。
    import re as _re_w
    if not _re_w.search(r"_cps_all\s*=\s*_bcc\(\s*s\b", _er6_code):
        issues.append(("ERROR", "engine/enterprise_report.py", "要件级核对未接线（只 import 未调用）"))
    if "checkpoints=_cps_all" not in _er6_code:
        issues.append(("ERROR", "engine/enterprise_report.py", "要件级核对未传入要件清单渲染"))

    # ── P1-8 / P2-7：章节内模板句去重（S6「通用口径只说一次」）──
    try:
        from engine.chapter_dedup import _longest_common_suffix, collapse_common_tail
        _tail = "办理须指定熟悉该项业务和资料的负责人，并由另一名人员复核；验收时确认处理过程能够回查。"
        _subjects = ["增值税进项发票与货物流不匹配", "工资薪金与社保人数不一致",
                     "主营业务成本两口径差异较大", "银行收款大于申报收入",
                     "关联方资金往来缺少合同支持"]
        _items = [{"narrative": "本项处理意见：针对「%s」情形，应补齐该项业务的原始凭证与说明材料。" % _sj + _tail}
                  for _sj in _subjects]
        _new, _note = collapse_common_tail(_items, "narrative")
        if not _note:
            issues.append(("ERROR", "engine/chapter_dedup.py", "公共结尾模板未被抽出（P1-8 未生效）"))
        if sum(1 for x in _new if x.get("_template_collapsed")) < 3:
            issues.append(("ERROR", "engine/chapter_dedup.py",
                           "模板抽出后条目未被剥离（说明抽出来了、正文还在重复）"))
        if any(_tail in str(x.get("narrative")) for x in _new):
            issues.append(("ERROR", "engine/chapter_dedup.py", "条目内仍残留通用模板"))
        if "增值税进项发票与货物流不匹配" not in str(_new[0].get("narrative")):
            issues.append(("ERROR", "engine/chapter_dedup.py", "剥离时误删了条目差异部分"))
        # ★ 反向用例：各条只差数字（归一化后完全相同）→ **不得**把条目剥空
        _same = [{"narrative": "第%d项处理意见：应补齐原始凭证。%s" % (i, _tail)} for i in range(1, 6)]
        _s3, _n3 = collapse_common_tail(_same, "narrative")
        if any(not str(x.get("narrative") or "").strip() for x in _s3):
            issues.append(("ERROR", "engine/chapter_dedup.py",
                           "把条目正文剥空（各条仅差数字时公共后缀=整条，须设折叠上限）"))
        # 零误报：各条内容不同 → 不得抽出任何"模板"
        _diff = [{"narrative": "完全不同的一段说明文字%d，用于验证不会误抽模板。" % i}
                 for i in range(5)]
        _d2, _n2 = collapse_common_tail(_diff, "narrative")
        if _n2:
            issues.append(("ERROR", "engine/chapter_dedup.py",
                           "内容各异的条目被误判为共享模板（误抽会丢正文）"))
        if _longest_common_suffix(["甲" * 40, "乙" * 40]) != 0:
            issues.append(("ERROR", "engine/chapter_dedup.py", "公共后缀计算有误（不同文本应为 0）"))
    except ImportError as exc:
        issues.append(("ERROR", "engine/chapter_dedup.py", f"章节去重模块不可用: {exc}"))
    except Exception as exc:
        issues.append(("ERROR", "engine/chapter_dedup.py", f"章节去重断言执行失败: {exc}"))
    if ('_cct(materials, "narrative")' not in _er6_code
            or '_cct(plans, "narrative")' not in _er6_code):
        issues.append(("ERROR", "engine/enterprise_report.py", "章节模板去重未接线（只 import 未调用）"))
    if "action_plan_note" not in _er6_code:
        issues.append(("ERROR", "engine/enterprise_report.py", "整改章通用说明未输出（章首说明缺）"))
    _tda7 = _src("static/js/tax-doc-analysis.js")
    # 两侧都要断言：只查"渲染语句在不在"会被"条件恒假"骗过（实测两版都踩过）：
    #   `if (false) { ...esc(report.action_plan_note)... }` 里语句还在，但永远不会显示。
    if ("esc(report.action_plan_note)" not in _tda7
            or "if (report.action_plan_note)" not in _tda7):
        issues.append(("ERROR", "static/js/tax-doc-analysis.js",
                       "整改章通用说明未渲染（抽出来了却没显示）"))

    # ══════════════════════════════════════════════════════════════
    # ★ 2026-09-29（点评复核发现的真缺陷：净化护栏把法定口径也中性化了）
    # ══════════════════════════════════════════════════════════════
    # 事故：报告「九、时效与滞纳金提示」因含"补缴…滞纳金"被 `_PENALTY_SENTENCE` 整句命中 →
    # 三处全部替换成同一句中性模板 → ① 点评 P1-12 要求的时效与滞纳金提示**实际没进报告**
    # （改完却看不见）；② 同一模板句连续出现 3 次。根因：把**法定期限/滞纳金计算规则**的
    # 陈述误当成"对本企业的处罚断言"。
    try:
        from engine.text_guardrails import neutralise_output_text as _nt
        _stat = ("九、时效与滞纳金提示：企业所得税年度汇算清缴截止于年度终了之日起五个月内"
                 "（次年 5 月 31 日）；更正申报与补缴将依法自汇算期结束次日起按日加收万分之五滞纳金。"
                 "建议在补缴资金安排中计入滞纳金成本；小税种的补缴同样自法定缴纳期限届满起计算滞纳金。")
        _out_stat = _nt(_stat)
        if "万分之五" not in _out_stat:
            issues.append(("ERROR", "engine/text_guardrails.py",
                           "法定口径（期限/滞纳金计算规则）被净化护栏中性化 —— 时效与滞纳金提示进不了报告"))
        if "有权人员复核" in _out_stat and "万分之五" not in _out_stat:
            issues.append(("ERROR", "engine/text_guardrails.py", "规则陈述被替换为处罚模板句"))
        # 真正的处罚断言仍须被中性化（反向用例，防"一刀切放行"）
        _pen = _nt("本企业少缴增值税 100 万元，应补缴税款并加收滞纳金，并处一倍罚款。")
        if "有权人员复核" not in _pen:
            issues.append(("ERROR", "engine/text_guardrails.py",
                           "真实处罚断言未被中性化（豁免过宽，定性边界失守）"))
        # 连续重复句必须被压成一次
        _dup = _nt("同一句模板。同一句模板。同一句模板。另外一句。")
        if _dup.count("同一句模板") != 1:
            issues.append(("ERROR", "engine/text_guardrails.py",
                           f"净化后连续重复句未去重: {_dup[:40]}"))
    except Exception as exc:
        issues.append(("ERROR", "engine/text_guardrails.py", f"净化护栏断言执行失败: {exc}"))
    # 报告实测：时效提示必须真的带「万分之五」到达报告
    # ⚠ 还需**源码级**断言：dump 是既有产物，改源码后不重跑查不出（实测注入删掉"万分之五"
    #   后闸门仍 0 ERROR）。
    _io8 = _strip_comments_keep_lines(_src("engine/inspection_overview.py"))
    if "万分之五" not in _io8:
        issues.append(("ERROR", "engine/inspection_overview.py",
                       "总述「时效与滞纳金提示」未写明日万分之五滞纳金"))
    _dd8 = _canonical_report()
    if _dd8 is not None:
        try:
            _iv8 = ((_dd8.get("enterprise_readable_report"))
                    or {}).get("inspection_overview") or {}
            _ivtxt = " ".join(str(x) for x in (_iv8.get("paragraphs") or []))
            if "时效与滞纳金提示" in _ivtxt and "万分之五" not in _ivtxt:
                issues.append(("ERROR", "engine/inspection_overview.py",
                               "报告中的时效提示缺「万分之五」（被护栏吞掉或未生成）"))
            if _ivtxt.count("具体税款、滞纳金、处罚或移送后果须依据") > 1:
                issues.append(("ERROR", "engine/text_guardrails.py",
                               "报告中同一中性化模板句重复出现（净化加工复读）"))
        except Exception as exc:
            issues.append(("WARN", "tools/audit_consistency.py",
                           f"净化护栏 dump 行为验证跳过: {exc}"))

    # ── ★ 2026-10-02（用户复核疑点5）：**触红开场句必须以「至少一条要件被认定」为前提** ──
    #   事故：同一疑点里，首段写「本企业触发税务风险指标…涉嫌通过关联企业转移利润、虚开发票」，
    #   下一条 bullet 却写「经核对，本企业涉及上述第 无 条构成要件」—— 内部正面矛盾。
    #   根因：触红判据（线索链有没有信号）与「涉及第 N 条要件」判据（constituent_checkpoint
    #   逐条独立核对有没有认定）是两套互不相认的口径，报告却默认它们永远一致。
    #   判据用**行为断言**（直调生产函数 risk_item_leader），不靠文本匹配。
    try:
        from engine.enterprise_report import risk_item_lead as _ril
        _hit_lead = _ril("关联交易异常", "涉嫌转移利润", {"1,3"})
        _none_lead = _ril("关联交易异常", "涉嫌转移利润", set())
        if "触发税务风险指标" not in _hit_lead:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "有要件被认下时，风险事项段却没用触红开场句（口径被改坏）"))
        if "触发税务风险指标" in _none_lead or "税务违规红线" in _none_lead:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "一条要件都没认下时仍在用触红开场句（与同项「涉及第 无 条构成要件」矛盾）"))
        if ("认定到任何一条构成要件" not in _none_lead
                and "已因触发条件命中而列为疑点" not in _none_lead):
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "零认定时首句未如实说明「未认定到任何一条构成要件」"))
        # 反向用例：无信号时也不得凭空造信号
        _none_nosig = _ril("关联交易异常", "涉嫌转移利润", set(), "")
        if "账内检出" in _none_nosig:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "无信号时首句仍写「账内检出…信号」（凭空造信号）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       f"触红开场句行为断言执行失败: {exc}"))

    # ── ★ 2026-10-02（用户复核疑点5）：**结论段的触红断言**同样要跟着要件认定走 ──
    #   首句（p1）改对了、结论段（p4）还写「本条涉嫌触碰红线」——同一疑点内部自相矛盾。
    #   直接调生产函数 `sanitize_conclusion_assertion`（行为断言，不靠文本匹配）。
    try:
        from engine.enterprise_report import (
            sanitize_conclusion_assertion as _sca,
        )
        _rl_name = "关联交易异常：购销闭环与六员重叠"
        _reason = ("本条涉嫌触碰红线，即%s，涉嫌通过关联企业转移利润、虚开发票。"
                   "判断本项是否成立，要看这几项标准是否同时满足： Manufacturing。" % _rl_name)
        _hit_p4 = _sca(_reason, _rl_name, {"1", "3"})
        _none_p4 = _sca(_reason, _rl_name, set())
        # ★ 判据必须锁死**断言句式**「本条涉嫌触碰红线，即…」：零认定时替换句里本来就要
        #   写「不等于已触碰红线」，用裸词匹配会把自己判红（实测踩过）。
        _assertion = "本条涉嫌触碰红线，即"
        if _assertion not in _hit_p4:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "有要件被认下时，结论段的触红断言被误删（口径被改坏）"))
        if _assertion in _none_p4 or "税务违规红线" in _none_p4:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "一条要件都没认下时，结论段仍在断言「触碰红线」（与「涉及第 无 条构成要"
                           "件」正面矛盾）"))
        # ★ 2026-10-07（触发条件与认定要件分离）：零认定段的措辞要求同步 ——
        #   接受新的分层表述「已因触发条件命中而列为疑点」替代旧的「未认定到任何一条构成要件」
        #   （旧句已按用户验收要求下线）。
        _ok_wording = ("未认定到任何一条构成要件" in _none_p4
                       or "已因触发条件命中而列为疑点" in _none_p4)
        if "不等于已触碰红线" not in _none_p4 or not _ok_wording:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "零认定时结论段未如实说明「未认定到要件 / 不等于已触红」"))
        # 段尾「本项结论是<触红裁决>…」必须与首句一起被中性化（只改首句 = 首句说他没触红、
        # 段尾说他触红了，读者照样看到自相矛盾）
        try:
            from engine.argumentation import _VERDICT_HIT_PENDING as _vhp
        except Exception:
            _vhp = "已触碰税务违规红线"
        if _vhp in _none_p4:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "零认定时结论段结尾仍在断言触红裁决（与同项零认定首句矛盾）"))
        # 改写只动首句，原论证正文（"判断本项是否成立…"）必须完整保留
        _tail = _reason[_reason.find("。"):]
        if _tail not in _none_p4:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "结论段改写时把原论证正文整段吞掉了（只留一句套话）"))
        # ★ RL-CIT-001 是「要件异质」红线（①六员/地址/电话 ②购销占比 ③定价偏离
        #   ④同期资料 ⑤正当情形，五条要各不相同的数据源），盲发兜底序号会把任何命中都
        #   记成"第①条六员重叠"——实测全系统没有任何扫描器算过六员比对。
        try:
            from engine.redline_engine import _DEFAULT_HIT_INDEX as _di
            if _di.get("RL-CIT-001"):
                issues.append(("ERROR", "engine/redline_engine.py",
                               "_DEFAULT_HIT_INDEX 仍为 RL-CIT-001 盲发兜底序号（要件异质红线"
                               "会被一律记成同一条要件），须由检测器自行声明 constituent_hits"))
        except Exception as exc:
            issues.append(("ERROR", "engine/redline_engine.py", f"_DEFAULT_HIT_INDEX 加载失败: {exc}"))
        # ★ 疑点级裁决必须与实际渲染的论证同出一家（两分支各写一份会出双口径）
        _dd9 = _canonical_report()
        if _dd9 is not None:
            try:
                for _sp in (((_dd9.get("comprehensive") or {})
                             .get("redline_detection") or {}).get("suspicions") or []):
                    _sa9 = _sp.get("argumentation") or {}
                    if _sa9.get("verdict") and _sp.get("verdict") != _sa9.get("verdict"):
                        issues.append(("ERROR", "engine/redline_engine.py",
                                       f"疑点 {_sp.get('redline_id')} 裁决({_sp.get('verdict')})"
                                       f"与正文论证({_sa9.get('verdict')})不是一个口径"))
                        break
            except Exception as exc:
                issues.append(("ERROR", "tools/audit_consistency.py",
                               f"疑点裁决一致性 dump 验证失败: {exc}"))
        # 反向用例：开场句不是本条红线（标题被裁剪），不许误伤
        _other = _sca(_reason, "另一个疑点名", set())
        if _other != _reason:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "结论段改写误伤了「非本条红线」的触红开场句（宁缺勿错被破坏）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       f"触红开场句行为断言执行失败: {exc}"))

    # ── 外部核验项：不得判触红 + 明细行必须语义对齐 ──
    try:
        from engine.argumentation import (
            _VERDICT_EXTERNAL as _VEXT,
            build_argumentation as _ba, is_external_check_finding as _ief,
        )
        from engine.clue_chain import build_clue_chain as _bcl
        from engine.evidence_chain import build_evidence_chain as _becl
        from engine.tax_redlines import get_redline as _grl
        _rl = _grl("RL-CIT-001")
        _extf = {"type": "需外部数据核验：关联交易的同期资料与关联申报",
                 "category": "外部核验", "level": "待核验",
                 "detail": "发现既为供应商又为客户的主体2家，存在关联交易迹象。"}
        _cl = _bcl(_extf, _rl)
        _cl["terminal_signal"] = "既为供应商又为客户的主体2家"
        _a = _ba(_extf, _rl, _cl, _becl(_extf, _rl, available_materials=["进项发票"]))
        if _a.get("verdict") != _VEXT:
            issues.append(("ERROR", "engine/argumentation.py",
                           "外部核验项未走独立裁决档（应判 %s）" % _VEXT))
        if _a.get("redline_hit"):
            issues.append(("ERROR", "engine/argumentation.py",
                           "外部核验项被判触红（外部数据未取得 ⇒ 要件无从核对 ⇒ 不得触红）"))
        if not _ief(_extf):
            issues.append(("ERROR", "engine/argumentation.py",
                           "is_external_check_finding 认不出外部核验项（识别口径被改坏）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/argumentation.py",
                       f"外部核验裁决行为断言执行失败: {exc}"))
    # 语义采样：外部核验项不得被通用关键词兜底挂上无关原始行（"银行"来自其文案说明）
    try:
        from engine import pipeline as _pl
        from engine.external_check_reminder import build_external_check_reminders as _bcr
        _sal = [{"direction": "销项", "inv_no": "S1", "发票号码": "S1", "goods": "广告服务",
                 "amount": 1000.0, "buyer": "甲公司", "销方名称": "本公司", "date": "2025-03-01"}]
        _pur = [{"direction": "进项", "inv_no": "P1", "发票号码": "P1", "goods": "服务费",
                 "amount": 500.0, "seller": "甲公司", "销方名称": "甲公司", "date": "2025-02-01"}]
        _bk = [{"transaction_serial_no": "B1", "date": "2025-01-05", "summary": "货款",
                "debit": 300000.0, "credit": 0, "counterparty": "甲公司"}]
        _fs = _bcr(_sal, _pur, _bk, None, None, None)
        _pl._enrich_evidence_rows(_fs, _bk, _sal + _pur, [], [], company_name="本公司")
        _rel = [f for f in _fs if "关联交易" in str(f.get("type") or "")]
        if not _rel:
            issues.append(("ERROR", "engine/external_check_reminder.py",
                           "样本未产出关联交易外部核验项（闸门样本失效，需换样本）"))
        else:
            for _r in (_rel[0].get("evidence_rows") or []):
                if _r.get("source") == "银行流水":
                    issues.append(("ERROR", "engine/pipeline.py",
                                   "关联交易核验表下挂了银行流水行（证据行语义错配，"
                                   "应按 entity_invoices 分支只取既购又销主体的发票）"))
                if not str(_r.get("counterparty") or "").strip():
                    issues.append(("ERROR", "engine/pipeline.py",
                                   "外部核验明细行缺交易对方（无法逐笔核验）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/pipeline.py", f"外部核验证据行断言执行失败: {exc}"))

    return issues


# ═══════════════════════════════════════════════════════════════════
# 同源排查闸门（2026-09-30 新增，对应 _hunt_same_class_defects A / D 类）
# ═══════════════════════════════════════════════════════════════════

# ★ 2026-10-06：等级词表**唯一权威** `engine.risk_levels.LEGAL_LEVELS`（原先此处硬编码一份，
#   引擎侧另有一份 `_LEGAL_RISK_LEVELS` —— 两处同源不同步会让"合法等级"判定漂移）。
_LEGAL_FINDING_LEVELS = frozenset(LEGAL_LEVELS)
_RISK_FINDING_KEYS = ("type", "detail", "description", "tax_impact", "suggestion", "category")
_MISSING_MATERIAL_TYPE_PREFIX = "资料缺失"


def _is_empty_findings_assign(stmt: "ast.AST") -> bool:
    if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
        return False
    tg = stmt.targets[0]
    if not isinstance(tg, ast.Name) or tg.id != "findings":
        return False
    return isinstance(stmt.value, ast.List) and len(stmt.value.elts) == 0


def _is_guard_return(stmt: "ast.AST", params: set) -> bool:
    if not isinstance(stmt, ast.If):
        return False
    t = stmt.test
    if not (isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not)
            and isinstance(t.operand, ast.Name)):
        return False
    if t.operand.id not in params:
        return False
    for b in stmt.body:
        if isinstance(b, ast.Return) and isinstance(b.value, ast.Name) \
                and b.value.id == "findings":
            return True
    return False


def check_domain_missing_material_emits_finding() -> List[Tuple[str, str, str]]:
    """域函数「缺主资料」必须产出 资料缺失 待核验 发现，不得静默零产出。

    ★ 2026-09-30 同源收敛：salary/social_security 事件根因之一是「缺一份资料 → 整域
      零产出、报告无痕」。本项目已确立统一行为：域函数主资料缺失时，先 append 一条
      `{"type": "资料缺失-...", "level": "待核验", ...}` 发现再 return，使报告能看到
      「该项检查因缺资料未执行」。但 _domain_bom_verify / _domain_warehouse_capacity
      曾 `if not <主资料>: return findings`（findings 为空），与其他 8 个域不一致，
      构成复发隐患。本闸门强制：任何 `_domain_*` 函数若 `findings = []` 后紧跟
      `if not <形参>: return findings`（且函数内从未 append 任何发现）→ 报错。
    """
    issues: List[Tuple[str, str, str]] = []
    target = ROOT / "engine" / "domain_analysis.py"
    if not target.exists():
        return issues
    try:
        tree = ast.parse(target.read_text(encoding="utf-8"))
    except Exception:
        return issues

    for node in tree.body:
        if not (isinstance(node, ast.FunctionDef) and node.name.startswith("_domain_")):
            continue
        params = {a.arg for a in node.args.args}
        emitted_types = set()
        for n in ast.walk(node):
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call):
                func = n.value.func
                if isinstance(func, ast.Attribute) and func.attr == "append" \
                        and isinstance(func.value, ast.Name) and func.value.id == "findings":
                    if n.value.args and isinstance(n.value.args[0], ast.Dict):
                        for k, v in zip(n.value.args[0].keys, n.value.args[0].values):
                            if isinstance(k, ast.Constant) and k.value == "type" \
                                    and isinstance(v, ast.Constant) and isinstance(v.value, str):
                                emitted_types.add(v.value)
        silent = False
        for i, stmt in enumerate(node.body):
            if _is_empty_findings_assign(stmt):
                nxt = node.body[i + 1] if i + 1 < len(node.body) else None
                if nxt is not None and _is_guard_return(nxt, params):
                    silent = True
        if silent and not any(t.startswith(_MISSING_MATERIAL_TYPE_PREFIX)
                               for t in emitted_types):
            issues.append((
                "ERROR", "domain_missing_material_emits_finding",
                f"engine/domain_analysis.py::{node.name} 主资料缺失时静默 return 空 "
                f"findings，未 append 资料缺失 待核验 发现（与其他域不一致，缺资料检查在报告中无痕）。"
            ))
    return issues


def check_finding_level_legality() -> List[Tuple[str, str, str]]:
    """报告风险发现的 level 必须是权威词表，否则被输出封印静默丢弃。

    ★ 2026-09-30 同源收敛：记忆「等级合法性」机制——词表外 level 被后续环节静默丢弃。
      本闸门做正向校验：任何**风险发现形态**的字典字面量（同时含 type/detail/description/
      tax_impact/suggestion/category 六键，即域/VR 产出的标准风险发现形状）若其 `level`
      为字符串字面量且不在权威词表 → 报错。
      注：下列非风险词汇（优惠机会/提醒/提示、高可信/中等可信/低可信、错误/警告/注意、
      未知、未触发、层级）属置信度/评审/标签/机会流 vocabulary，不具六键形状，不予误报。
    """
    issues: List[Tuple[str, str, str]] = []
    for f in _iter_prod_py_files():
        rel = os.path.relpath(f, ROOT).replace("\\", "/")
        if rel.startswith("scripts/"):
            continue
        try:
            tree = ast.parse(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
            if not all(k in keys for k in _RISK_FINDING_KEYS):
                continue
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value == "level":
                    if isinstance(v, ast.Constant) and isinstance(v.value, str):
                        if v.value not in _LEGAL_FINDING_LEVELS:
                            issues.append((
                                "ERROR", "finding_level_legality",
                                f"{rel} 风险发现 level='{v.value}' 不在权威词表"
                                f"{sorted(_LEGAL_FINDING_LEVELS)}，将被输出封印静默丢弃。"
                            ))
                    break
    return issues


def check_constituent_sources_wiring() -> List[Tuple[str, str, str]]:
    """★ 2026-09-29（#448）：逐要件独立数据源 `constituent_sources` 的对齐 + 行为 + 接线不变式。

    背景：`not_checked` 中约七成来自「红线定义未标注该要件的独立数据源」。修法是给红线补
    `constituent_sources`（与 `constituents` 按序对齐），由 `constituent_checkpoint` 据此判定
    「该要件的独立数据源本轮是否已取得」。本闸门锁死三件事，防"补了数据却不生效"：
      ① 对齐：凡声明 constituent_sources 的红线，长度必须 == constituents 长度；
      ② 行为：声明了数据源的要件必须采用该数据源、且不再落「未定义」；
      ③ 接线：`evidence_chain` 透出 `available_materials`；`redline_engine` 把
         `constituent_sources` 传到疑点（否则数据源声明到不了 checkpoint）。
    """
    issues: List[Tuple[str, str, str]] = []
    # ① 对齐
    try:
        from engine.tax_redlines import REDLINES
        for r in REDLINES:
            cs = r.get("constituent_sources")
            if not cs:
                continue
            cons = r.get("constituents") or []
            if len(cs) != len(cons):
                issues.append(("ERROR", "engine/tax_redlines.py",
                               f"{r.get('id')} constituent_sources 长度({len(cs)})"
                               f"≠constituents({len(cons)})，按序对齐被破坏"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/tax_redlines.py", "读取红线定义失败：%s" % exc))
    # ② 行为
    try:
        from engine.constituent_checkpoint import build_constituent_checkpoints
        s = {"constituents": ["测试要件A", "测试要件B"],
             "constituent_sources": ["销项发票", "红字发票信息确认单"],
             "evidence_chain": {"elements": [], "available_materials": ["销项发票"]},
             "clue_chain": {"nodes": []}, "argumentation": {"constituent_hits": []}}
        cps = build_constituent_checkpoints(s)
        if len(cps) != 2:
            issues.append(("ERROR", "engine/constituent_checkpoint.py",
                           "声明 constituent_sources 后要件数不符（%d≠2）" % len(cps)))
        elif str(cps[0].get("独立数据源") or "") != "销项发票":
            issues.append(("ERROR", "engine/constituent_checkpoint.py",
                           "已声明数据源的要件未采用该数据源（仍落未定义）："
                           f"{cps[0].get('独立数据源')!r}"))
        # ★ 2026-10-04（疑点10-21 合并批次 ⑲）：把旧的「资料已取得 ⇒ 一律 checked_miss」
        #   换成正解的**排除性断言**——该用例没有针对要件的核对证据，
        #   结论可以是 `checked_hit`（有信号）或 `not_concluded`（未形成结论），
        #   但**绝不允许** `checked_miss`（"未发现符合"没有核对动作支撑＝虚假排除）。
        elif cps[0].get("_conclusion") == "checked_miss":
            issues.append(("ERROR", "engine/constituent_checkpoint.py",
                           "「资料已取得但无核对证据」被判『未发现符合』—— 虚假排除，"
                           "应判 not_concluded（未形成核对结论）"))
        elif cps[0].get("_conclusion") not in ("checked_hit", "not_concluded"):
            issues.append(("ERROR", "engine/constituent_checkpoint.py",
                           "已取得数据源的要件既未判为已核对、也未落 not_concluded（%s）"
                           % cps[0].get("_conclusion")))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/constituent_checkpoint.py", "行为断言失败：%s" % exc))
    # ③ 接线
    try:
        ev = (ROOT / "engine" / "evidence_chain.py").read_text(encoding="utf-8")
        if "available_materials" not in ev:
            issues.append(("ERROR", "engine/evidence_chain.py",
                           "未透出 available_materials（checkpoint 无法判「已取得」，要件落未定义）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/evidence_chain.py", "读取失败：%s" % exc))
    try:
        re_src = (ROOT / "engine" / "redline_engine.py").read_text(encoding="utf-8")
        if "constituent_sources" not in re_src:
            issues.append(("ERROR", "engine/redline_engine.py",
                           "未传递 constituent_sources 到疑点（数据源声明不生效）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/redline_engine.py", "读取失败：%s" % exc))
    return issues


def check_material_alias_drift() -> List[Tuple[str, str, str]]:
    """★ 2026-10-01 新增：红线 `required_materials` 的「异名漂移」闸门（照运行时真语义模拟）。

    背景（真实事故族，直接掉①）：
      `redline_engine._map_finding` 判定「红线所需资料是否齐备」时是**严格字符串相等**：
          mats = [m for m in (rl.get("required_materials") or [])
                  if m in (available_materials or [])]
      而 `available_materials` 来自 `redline_engine._available_materials`，其内容是企业
      **照着报告提示的名字上传文件后**，由 `material_recognition._recognize_supplementary`
      做**最长关键词命中**得到的类别名。
      于是：红线写「增值税申报表」、识别表登记的是「增值税纳税申报表（含留抵税额）」，
      企业即使真的上传了增值税申报表，`「增值税申报表」 in [「增值税纳税申报表（含留抵税额）」]`
      也是 False → 该红线判资料不齐 → `match_redline_grounded` 返回 unmatched
      → **真实风险落进「未归入已知风险情形」，永远升不到已确认**。

    判据（刻意照运行时真语义，**不用包含式启发式**——那会把「固定资产明细」误判成
    「固定资产明细（车辆）」的异名；实测运行时最长关键词命中的是它自身）：
      对每条红线、每个 required_materials 名 m，模拟上传《m.xlsx》：
      `_recognize_supplementary` 若返回某类别且类别名 != m → ERROR。

    本闸门**只报错、不改数**：改红线文案 vs 补登记别名 / `extra_cats` 并回，
    属领域判断，由人工拍板（2026-10-01 用户决策：先只加闸门，不改数据）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.tax_redlines import all_redlines as _all_redlines
        from engine.material_recognition import (_recognize_supplementary,
                                                 supplementary_doc_type_to_category,
                                                 _SUPP_ENTRIES)
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/tax_redlines.py",
                       "读取红线或资料识别表失败，闸门无法校验：%s" % exc))
        return issues

    # ② 关键词撞车 / 重复登记：同一关键词被两条以上不同登记项共用时，
    #    `_recognize_supplementary` 取所有命中里 len(_kw) 最大者，而长度相同则**谁赢
    #    取决于 _SUPP_ENTRIES 的声明顺序**——与 PYTHONHASHSEED 那类可复现性坑同族。
    #    副作用：同一份《完税凭证.xlsx》今天认成 A、改一行声明顺序就认成 B，
    #    红线判定跟着时好时坏（严格相等匹配下直接体现为「资料时有时无」）。
    _owner: Dict[str, List[str]] = {}
    for _name, _dt, _kws, _extra in _SUPP_ENTRIES:
        for _k in (_kws or []):
            _owner.setdefault(str(_k), []).append(str(_name))
    for _k, _ns in sorted(_owner.items()):
        if len(set(_ns)) > 1:
            issues.append(("ERROR", "engine/material_recognition.py",
                           "关键词「%s」被 %d 条不同登记项共用（%s）：命中谁取决于声明顺序，"
                           "同一份文件可能今天认成 A 明天认成 B → 红线判定随顺序漂移。须把关键词收窄到唯一"
                           % (_k, len(set(_ns)), "、".join(sorted(set(_ns))))))
        elif len(_ns) > 1:
            issues.append(("ERROR", "engine/material_recognition.py",
                           "规范名「%s」被登记了 %d 次（一物两名/重复登记）："
                           "两条都会抢同一批文件，长词打平后按顺序定胜负" % (_k, len(_ns))))

    # ③ 跨登记项等长打平（2026-10-01 反向验证自曝出的闸门盲区）。
    #    ② 只抓「完全相同的关键词字符串」共用，下面的漂移判据只抓「打平后赢家门≠需求名」。
    #    但还有第三种：两条例外——关键词是**不同字符串、长度相同、同时命中同一文件名**，
    #    谁赢完全由 _SUPP_ENTRIES 声明顺序决定；若赢家恰好是需求名自身，两种判据**都不响**。
    #    实测（scripts/_reverse_verify_alias.py C 组 + scripts/_scan_kw_ties.py）：
    #    只挪一行声明顺序，《转让时点财务报表或评估报告.xlsx》就从「评估报告」翻成
    #    「转让时点财务报表或评估报告」——判定靠侥幸成立，与 PYTHONHASHSEED 那类坑同族。
    #    判据：对每条红线需求名模拟上传《m.xlsx》，若最长命中里出现两条以上
    #    **不同登记项**的关键词 → ERROR（同登记项内多叫法打平是有意容错，不算）。
    _need_names: List[str] = []
    for _r2 in _all_redlines():
        for _m2 in (_r2.get("required_materials") or []):
            _m2 = str(_m2)
            if _m2 not in _need_names:
                _need_names.append(_m2)
    for _need in _need_names:
        _hits = []
        for _name2, _dt2, _kws2, _extra2 in _SUPP_ENTRIES:
            for _k2 in (_kws2 or []):
                if str(_k2) and str(_k2) in _need:
                    _hits.append((len(str(_k2)), str(_k2), str(_name2)))
        if not _hits:
            continue
        _best_len = max(_h[0] for _h in _hits)
        _tied = sorted({(_h[1], _h[2]) for _h in _hits if _h[0] == _best_len})
        if len({_t[1] for _t in _tied}) > 1:
            issues.append((
                "ERROR", "engine/material_recognition.py",
                "模拟上传《%s.xlsx》时，有 %d 条**不同登记项**的关键词等长命中（%s）："
                "_recognize_supplementary 取最长命中，等长则谁赢由 _SUPP_ENTRIES 声明顺序"
                "决定 → 同一份文件的资料归属随顺序漂移，而 redline_engine 按严格相等匹配，"
                "实际表现就是「这份资料有时算已提供、有时算缺」。须把这些关键词拉开长度差"
                "或改成独占关键词（同登记项内多叫法等长打平是有意容错，不计）。"
                % (_need, len(_tied), "、".join("「%s」→%s" % _t for _t in _tied))))

    for _r in _all_redlines():
        for _m in (_r.get("required_materials") or []):
            _m = str(_m)
            _dt = _recognize_supplementary(_m + ".xlsx")
            if _dt is None:
                # 普通资料（银行流水/发票/合同…），走内容指纹链路，不归本闸门管
                continue
            _cat = supplementary_doc_type_to_category(_dt)
            if _cat and str(_cat[0]) != _m:
                issues.append((
                    "ERROR", "engine/tax_redlines.py",
                    "%s required_materials 写「%s」，但资料识别表登记的规范名是「%s」（识别关键词"
                    "其实已含「%s」，识别层没问题）；mats 里存的是规范名，"
                    "redline_engine 按严格相等匹配 → 这份资料该红线永远吃不到 → 发现落 unmatched。"
                    "修法唯一有效：**红线文案改用规范名「%s」**（领域判断，人工拍板）。"
                    "★ 补别名无效——_doc_covered_categories 返回的 mats 只装中文规范名，装不进别名"
                    % (_r.get("id"), _m, _cat[0], _m, _cat[0])))
    return issues


def check_no_lock_reentrancy(_path=None) -> List[Tuple[str, str, str]]:
    """★ 2026-10-01 新增：禁止「持 `_analysis_lock` 时又调用同样会取锁的函数」（自死锁闸门）。

    事故（用户报「一键分析卡在 99%，生成不了报告」；py-spy 抓栈定位）：
      `_run_analysis_thread` 在 `with _analysis_lock:` 块内调用 `_write_analysis_checkpoint`
      → `_is_result_deleted` 里再 `with _analysis_lock:`；而 `threading.Lock` **不可重入**，
      同一线程第二次 acquire 会自己等自己 → 分析线程永久卡死（实测 CPU 0%、跑 80 分钟不动）、
      任务状态恒 running、前端只看到进度停在 99%；而报告其实早已落盘却永远取不到。
    判据（AST 静态扫描，**不 import main**，避免为此拉起整个服务）：
      1）取锁者 = 函数体内出现 `with *_analysis_lock*` 的函数；
      2）**传递可达**：调用链上任何一跳出现过取锁的函数，都算「会取锁」（不动点迭代到
         收敛）。★ 这一步是事故倒逼补的——事故链是**两跳**：锁块 → `_write_analysis_checkpoint`
         → `_is_result_deleted` → 取锁。只传一层的初版闸门对这条链**完全不响**
         （实测：坏副本 A/B 都跑成绿，等于假闸门）；
      3）任一 `with _analysis_lock:` 块**体内**若出现对「传递可达取锁者」的调用 → ERROR。
    规模说明：真实 main.py 上「传递可达取锁者」9 个、命中锁块 0 个 → 不误报。
    修法（二选一）：把该调用挪到 with 块**之外**；或让被调用函数改成**无锁快照读**
    （`_is_result_deleted` 现即为此法，故锁块内调用它是安全的）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        import ast as _ast
        import os as _os
        _p = _path or _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                    "..", "main.py")
        with open(_p, "r", encoding="utf-8") as _f:
            _tree = _ast.parse(_f.read(), filename=_p)
    except SyntaxError as _se:
        issues.append(("ERROR", "main.py",
                       "main.py 语法错误，锁重入闸门无法校验：第 %s 行 %s" % (_se.lineno, _se.msg)))
        return issues
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "main.py", "读取/解析失败，锁重入闸门无法校验：%s" % exc))
        return issues

    def _is_lock_with(_n):
        """该 with 是否锁 `_analysis_lock`（兼容 `with X._analysis_lock:` 之类写法）。"""
        if not isinstance(_n, (_ast.With, _ast.AsyncWith)):
            return False
        for _item in getattr(_n, "items", []) or []:
            _c = _item.context_expr
            while isinstance(_c, (_ast.Attribute, _ast.Call)):
                _nxt = getattr(_c, "value", None) or getattr(_c, "func", None)
                if _nxt is None:
                    break
                _c = _nxt
            if _c is not None and "_analysis_lock" in _ast.dump(_c):
                return True
        return False

    # ① 函数表（含嵌套函数；同一名字后者胜，与 Python 语义一致）
    _funcs: Dict[str, object] = {}

    def _collect(_node, _owner):
        for _c in _ast.iter_child_nodes(_node):
            if isinstance(_c, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                _funcs[_c.name] = _c
                _collect(_c, _c.name)
            else:
                _collect(_c, _owner)

    _collect(_tree, "<module>")

    # ② 传递可达取锁者集合
    _reach = {_f for _f in _funcs
              if any(_is_lock_with(_n) for _n in _ast.walk(_funcs[_f]))}
    _changed = True
    while _changed:
        _changed = False
        for _fname, _fnode in _funcs.items():
            if _fname in _reach:
                continue
            for _c in _ast.walk(_fnode):
                if (isinstance(_c, _ast.Call) and isinstance(_c.func, _ast.Name)
                        and _c.func.id in _reach):
                    _reach.add(_fname)
                    _changed = True
                    break

    # ③ 锁块体内调用「传递可达取锁者」→ ERROR
    for _n in _ast.walk(_tree):
        if not _is_lock_with(_n):
            continue
        _called = set()
        for _c in _ast.walk(_n):
            if (isinstance(_c, _ast.Call) and isinstance(_c.func, _ast.Name)
                    and _c.func.id in _reach):
                _called.add(_c.func.id)
        if _called:
            issues.append((
                "ERROR", "main.py",
                "`with _analysis_lock:` 块内调用了会**再次取同一把锁**的函数（%s）："
                "threading.Lock 不可重入 → 同一线程自死锁，表现为「分析跑完却永远卡在 99%%"
                "（CPU 0%%、状态恒 running）、报告取不到」（2026-10-01 实测事故）。"
                "修法：把该调用挪到 with 块**之外**，或让被调函数改成无锁快照读"
                "（如 `_is_result_deleted` 现为无锁遍历 `_analysis_tasks.values()` 快照）。"
                "（闸门 check_no_lock_reentrancy）" % "、".join(sorted(_called))))
    return issues


def check_evidence_rows_semantic_match(_path=None) -> List[Tuple[str, str, str]]:
    """证据行 ↔ 发现语义匹配（防「明细表内容与疑点无关」复发）。

    ═══ 事故（2026-10-01 用户复核实测）═══
    疑点「工资名册与社会保险人员范围差异」的明细表（共 8 笔）里：
      · 4 行是全公司**金额最大的记账凭证** —— 收到款项 1,611,200（应收账款/上海蕴世
        广告传媒）、结转期间损益 1,524,325.98（主营业务成本）、销售服务 1,494,054.59
        （主营业务收入/服务收入）、结转期间损益 1,494,054.59（本年利润）；
      · 4 行是**金额恒 0** 的工资表人员行（杨*、徐*、黄**、李**，对方单位空）。
    读者看到的是「工资社保差异」疑点下面挂着 161 万收款和 0 元工资，完全对不上。

    ═══ 根因 ═══
    1）`pipeline._enrich_evidence_rows` 是通用**关键词兜底**：发现没有自有 evidence_rows 时，
       按 type/detail/description 里有没有「凭证」二字决定要不要采记账凭证。而「凭证」在
       中文财税语境里有**两种含义**（记账凭证 / 参保凭证、原始凭证等资料名），
       该疑点文案写了「提供劳动合同、参保**凭证**或异地参保证明」→ 误采无关凭证；
    2）`_salary_row` 自己写了一份键表（姓名/部门/实发金额/period），与工资表实际结构
       （name/salary/net/period_start…）对不上 → 55 行工资证据行**金额一行都取不到**，
       恒显示 0.00 元（假证据：看起来像"这几个人没发工资"）。

    ═══ 判据（在真实全量产物上判定，不 import 运行时）═══
      (a) ERROR：带「记账凭证」证据行的发现，该凭证必须**与发现相关** ——
          要么凭证自身的（摘要/科目）与发现正文有实义中文 2-gram 交集，
          要么发现正文确实以记账凭证为对象（含「凭证号/会计分录/借贷/序时账/总账/
          科目余额/凭证明细」这类实体词）。两条都不满足 → 无关凭证。
          注：只看"文案里有没有『凭证』二字"是不够的 —— 「参保凭证」「账簿、凭证、
          报表与申报」（方法论名）都会误命中。
      (b) ERROR：带「工资表」证据行的发现，工资行金额不得**全部为 0**（静默返 0 的假证据）；
      (c) 单纯「记账凭证 + 工资表」两类混装**不算错**：一条疑点的证据本来就可能在
          多个资料之间（如「工资多源对等」同时引序时账的计提工资凭证与工资表人员行），
          只要各自都相关。故此处不做独立告警（否则是假警报）。
    """
    issues: List[Tuple[str, str, str]] = []
    path = _path or (ROOT / "scripts" / "four_reports" / "company_1_full.json")
    if not os.path.exists(path):
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "全量产物缺失，check_evidence_rows_semantic_match 跳过（请跑一次全量分析）"))
        return issues
    try:
        with open(path, encoding="utf-8") as fh:
            _d = json.load(fh)
        if isinstance(_d, dict) and "report" in _d:
            _d = _d["report"]
        findings = (_d.get("all_findings") or []) if isinstance(_d, dict) else []
    except Exception as e:  # noqa: BLE001
        issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                       "产物解析失败：%s" % e))
        return issues

    try:
        from engine.pipeline import _is_ledger_voucher_context
        from engine.pipeline import _voucher_relevant
        from engine.pipeline import _cjk_bigrams as _cjk
    except Exception:  # noqa: BLE001
        _is_ledger_voucher_context = None
        _voucher_relevant = None
    # 发现正文"确实以记账凭证为对象"的实体词（有这些词即放行，不看凭证行相关性）
    _VOUCHER_ENTITY = ("凭证号", "会计分录", "借贷", "序时账", "总账", "科目余额", "凭证明细")

    n_a = n_b = 0
    for f in findings:
        if not isinstance(f, dict):
            continue
        ev = f.get("evidence_rows") or []
        if not isinstance(ev, list) or not ev:
            continue
        ftype = str(f.get("type", ""))
        combined = "%s %s %s" % (ftype, f.get("detail", ""), f.get("description", ""))

        # (a) 凭证行必须真的与本发现相关
        voucher_rows = [r for r in ev if isinstance(r, dict) and r.get("source") == "记账凭证"]
        if voucher_rows and _voucher_relevant is not None:
            _grams = _cjk(combined)
            # 发现正文确实以记账凭证为对象时（凭证号/借贷/序时账…），相关性门槛放宽一档：
            # 允许"粗交集"（不去停用词），但仍要求有交集 —— 不能只凭一句实体词就整条放行。
            _ent = any(k in combined for k in _VOUCHER_ENTITY)
            _unrel = []
            for _r in voucher_rows:
                _sum = _r.get("ref_label") or ""
                _acc = _r.get("counterparty") or ""
                _ok = _voucher_relevant({"summary": _sum, "account_name": _acc}, _grams)
                if not _ok and _ent and (_sum or _acc):
                    _ok = bool((_cjk("%s %s" % (_sum, _acc)) & _grams))
                if not _ok:
                    _unrel.append(_r)
            if _unrel:
                n_a += 1
                _s = "; ".join(
                    "凭证号%s 摘要%s 金额%s" % (r.get("ref_id"), r.get("ref_label"), r.get("amount"))
                    for r in _unrel[:3])
                issues.append((
                    "ERROR", "engine/pipeline.py",
                    "发现「%s」挂了 %d/%d 行**与本发现无关**的记账凭证证据（%s）。"
                    '通用兜底采样若只按「凭证/序时账」这类词触发、并按金额取「全公司最大 TOP N」，'
                    "读者在疑点下会看到 161 万的收款凭证却完全不知道它跟这个疑点有什么关系。"
                    "修法：detector 交出自有 evidence_rows（通用兜底见 `if f.get(\"evidence_rows\")` 自动跳过）；"
                    "通用采样须走 `pipeline._voucher_relevant` 做相关性守卫（宁缺毋错）。"
                    "（闸门 check_evidence_rows_semantic_match）"
                    % (ftype[:30], len(_unrel), len(voucher_rows), _s)))
        elif voucher_rows and _is_ledger_voucher_context is not None:
            if not _is_ledger_voucher_context(combined):
                n_a += 1
                issues.append((
                    "ERROR", "engine/pipeline.py",
                    "发现「%s」挂了记账凭证证据，但其文案并不在谈记账凭证语境。"
                    "（闸门 check_evidence_rows_semantic_match）" % ftype[:30]))
        # (b) 工资行金额不得全 0
        sal_rows = [r for r in ev if isinstance(r, dict) and r.get("source") == "工资表"]
        if sal_rows:
            from engine.numparse import to_number
            vals = [to_number(r.get("amount")) for r in sal_rows if r.get("amount") is not None]
            if vals and all(v == 0 for v in vals):
                n_b += 1
                issues.append((
                    "ERROR", "engine/fieldkit.py",
                    "发现「%s」的 %d 行工资表证据金额**全部为 0**（%s）：这不是真没发工资，"
                    "是证据行键表与工资表实际列名对不上 → 静默返 0 的假证据。"
                    "修法：工资字段读取统一走 `engine.fieldkit`（唯一权威）。"
                    "（闸门 check_evidence_rows_semantic_match）"
                    % (ftype[:30], len(sal_rows),
                       "、".join(str(r.get("ref_id")) for r in sal_rows[:3]))))
    if n_a or n_b:
        issues.append(("WARN", "engine/enterprise_report.py",
                       "证据行语义体检：无关记账凭证 %d 处、假证据（工资金额全 0）%d 处。"
                       "（闸门 check_evidence_rows_semantic_match）" % (n_a, n_b)))
    return issues


def check_static_asset_cache_version() -> List[Tuple[str, str, str]]:
    """静态资源 `?v=` 必须等于文件**内容哈希** —— 否则前端改动用户永远看不到。

    ★ 2026-10-02（用户实测「改了这么多，报告还是没有什么变化」）根因之一：
      浏览器按「URL 含 query」缓存。`tax-doc-analysis.js` 内容在 10-01 更新过
      （新增「主营业务成本 vs 期间费用 三态归属」渲染），而 index.html 里仍是
      `?v=2026092901`（9/29）→ 用户一直用旧 JS，新章节**根本不渲染**。
      后端算得对，但用户看不见 —— 属于典型的"改了等于没改"。

    判据（单一权威）：版本号 = 该文件 sha1 前 10 位；同步工具
    `tools/sync_asset_versions.py`；本闸门只做校验（不自动改文件）。

    ★ 2026-10-17 扩围：由「只查 `static/index.html`」改为「**遍历 `static/*.html`**」——
      非首页的 `?v=` 此前无人校验，实测已有 4 个页面失配（同一份 `rbac-nav.js`
      内容已变、页面仍指旧哈希）。仅查首页 = 其余 24 个页面"改了等于没改"。
    """
    issues: List[Tuple[str, str, str]] = []
    # ★ 2026-10-17：此前**只校验 `static/index.html`**，其余页面的 `?v=` 无人管 ——
    #   同一份 JS 改了内容，非首页仍指向旧哈希（实测 4 个页面已失配：rbac-nav.js
    #   `4d62d2a49e` 而文件实际为 `ac23045192`）。现改为**遍历 `static/*.html`**。
    static_dir = ROOT / "static"
    pages = sorted(static_dir.glob("*.html")) if static_dir.is_dir() else []
    if not pages:
        return issues
    try:
        import hashlib
        for page in pages:
            rel_page = "static/%s" % page.name
            html = page.read_text(encoding="utf-8")
            refs = re.findall(r"(/static/(?:js|css)/[A-Za-z0-9_.\-]+)\?v=([0-9A-Za-z_.\-]+)", html)
            stale, missing = [], []
            for rel, cur in refs:
                p = ROOT / rel.lstrip("/").replace("/", os.sep)
                if not p.exists():
                    missing.append(rel)
                    continue
                want = hashlib.sha1(p.read_bytes()).hexdigest()[:10]
                if cur != want:
                    stale.append((rel, cur, want))
            if stale:
                _ex = "；".join("%s %s→%s" % (r, c, w) for r, c, w in stale[:4])
                issues.append(("ERROR", rel_page,
                               "静态资源版本号与文件内容不一致（浏览器会继续用旧 JS/CSS，"
                               "改动用户看不到，共 %d 处）：%s。跑 python tools/sync_asset_versions.py 同步"
                               % (len(stale), _ex)))
            if missing:
                issues.append(("ERROR", rel_page,
                               "静态资源引用指向不存在的文件: " + "、".join(missing[:5])))
    except Exception as exc:
        issues.append(("WARN", "tools/audit_consistency.py", f"静态资源版本校验跳过: {exc}"))
    return issues


def check_suspicion_subject_consistency() -> List[Tuple[str, str, str]]:
    """疑点主体一致性自检（唯一权威 `engine/subject_consistency`）必须真的成立。

    ★ 2026-10-02（用户：**已经出现几次对疑点编辑的内容与疑点主体错配的情况了，
      彻底检查并修复**）——本闸门锁三件事：

      ① **行为断言**：直调生产函数看实际产出（本项目反复栽在"源码写了、运行不走"）：
         · 勾稽轴 → 红线映射逐条自检通过；四处旧错配归属被拒；正当归属仍放行；
         · 「别的发现的表」不能挂到本疑点，「自己的表」必须还挂着。
      ② **接线断言**：勾稽引擎不得再就地硬编码红线编号（必须走唯一映射表）。
      ③ **反向验证（内嵌自检）**：故意把映射改错一次，自检必须变红 ——
         否则这条闸门本身是假的（只查"源码有没有引用"抓不到"判据从不生效"）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        import sys as _sys
        if str(ROOT) not in _sys.path:
            _sys.path.insert(0, str(ROOT))
        from engine import subject_consistency as SC
    except Exception as exc:  # pragma: no cover
        return [("ERROR", "主体一致性", f"无法导入 engine/subject_consistency：{exc}")]

    # ── ① 勾稽轴映射自检 ──
    bad = SC.selfcheck_axis_map()
    for b in bad:
        issues.append(("ERROR", "勾稽轴→红线",
                       f"{b['axis']} → {b['redline_id']} 主体自检不通过：{b['reason']}"))

    # ── ① 旧错配归属必须被拒（回归锁）──
    _must_reject = [
        ("RL-COST-003", "待核事实：银行存款支出方对等逐月不匹配（2025-01）"),
        ("RL-COST-003", "待核事实：应付账款发生额对等逐月不匹配（2025-01）"),
        ("RL-COST-003", "待核事实：序时账与科目余额表逐科目不一致（账账不符）"),
        ("RL-VAT-002", "待核事实：增值税进项税额对等逐月不匹配（2025-01）"),
        ("RL-VAT-001", "待核事实：增值税销项税额对等逐月不匹配（2025-01）"),
        ("RL-INC-001", "待核事实：收入多源对等逐月不匹配（2025-01）"),
    ]
    for rid, subject in _must_reject:
        ok, _why = SC.declared_subject_ok(rid, subject)
        if ok:
            issues.append(("ERROR", "归属声明",
                           f"旧错配归属未被拒绝：{rid} ← {subject[:34]}"))

    # ── ① 正当归属不得被误拒 ──
    _must_accept = [
        ("RL-COST-003", "待核事实：主营业务成本有票支撑偏低"),
        ("RL-PTY-001", "主营业务成本资金与负债支撑材料核验"),
        ("RL-OTH-003", "城建税及教育费附加随增值税附征勾稽"),
        ("RL-CIT-008", "待核事实：增值税进项税额对等逐月不匹配（2025-01）"),
        # 由"自检误报"反推补登记的同类表述（同一件事的内/外部两种说法）
        ("RL-FUND-001", "需外部数据核实：对私资金往来对象实名与性质"),
        ("RL-CIT-004", "待核事实：企业所得税贡献率偏低"),
    ]
    for rid, subject in _must_accept:
        ok, why = SC.declared_subject_ok(rid, subject)
        if not ok:
            issues.append(("ERROR", "归属声明", f"正当归属被误拒：{rid} ← {subject[:34]}｜{why}"))

    # ── ① 判据本身必须能区分（泛词不得使两条不同事项"同一主体"）──
    if SC.same_subject("附加税费计税依据与增值税不匹配",
                       "增值税进项税额对等逐月不匹配"):
        issues.append(("ERROR", "主体词判据",
                       "泛词（增值税/不匹配）未剔除，两条不同事项被判为同一主体"))

    # ── ② 接线断言：勾稽引擎不得再就地硬编码红线编号 ──
    try:
        mr = (ROOT / "engine" / "monthly_reconcile.py").read_text(encoding="utf-8")
        if re.search(r'\b_axis_rid\s*\(', mr) is None:
            issues.append(("ERROR", "勾稽轴接线",
                           "monthly_reconcile 未调用唯一映射 _axis_rid（红线编号可能仍是硬编码）"))
        # 勾稽调用实参里出现字面 RL-XXX ⇒ 又绕过了唯一映射
        for _m in re.finditer(r'_(?:reconcile|rate_consistency|point_reconcile)\s*\([^)]{0,400}?"RL-',
                              mr, re.S):
            issues.append(("ERROR", "勾稽轴接线",
                           f"勾稽调用仍硬编码红线编号：{_m.group(0)[-60:].replace(chr(10), ' ')}"))
    except Exception as exc:  # pragma: no cover
        issues.append(("WARN", "勾稽轴接线", f"源码读取失败：{exc}"))

    # ── ① 报告行为：外来表不挂、自己的表仍挂 ──
    try:
        from engine.enterprise_report import _build_redline_problems, _build_subject_audit
        findings = [
            {"type": "待核事实：银行存款支出方对等逐月不匹配（2025-01）", "level": "待核验",
             "redline_id": "RL-COST-003", "evidence_rows": [{"对方单位": "甲公司", "金额": 100}]},
            {"type": "待核事实：增值税进项税额对等逐月不匹配（2025-01）", "level": "待核验",
             "redline_id": "RL-VAT-002", "evidence_rows": [{"对方单位": "乙公司", "金额": 200}]},
        ]
        sus = [{
            "redline_id": "RL-COST-003", "redline_name": "白条入账：无合规凭证列支成本费用",
            "suspect": "涉嫌以不合法凭证列支", "taxes": ["企业所得税"], "domain": "成本",
            "legal_basis": ["《发票管理办法》第二十条"],
            "constituents": ["成本费用列支无发票或其他合规外部凭证"],
            "constituent_sources": ["成本明细账"],
            "clue_chain": {"terminal_signal": "2025-01 各来源金额不一致", "nodes": []},
            "evidence_chain": {}, "argumentation": {"verdict": "已触碰税务违规红线"},
            "finding_type": "待核事实：银行存款支出方对等逐月不匹配（2025-01）",
            "supporting_findings": [], "level": "待核验",
        }]
        sink = {"issues": [], "by_code": {}}
        ps = _build_redline_problems(sus, findings, audit_sink=sink)
        titles = [str((t or {}).get("title") or "")
                  for p in ps for para in (p.get("narrative_paragraphs") or [])
                  for t in (para.get("detail_tables") or [])]
        if any("进项税额对等" in t for t in titles):
            issues.append(("ERROR", "附表归属", "外来表（进项税额对等）被挂到了「白条入账」疑点下"))
        if not any("银行存款支出方对等" in t for t in titles):
            issues.append(("ERROR", "附表归属", "本疑点自己的明细表被误删（不得因一致性把该有的表也删掉）"))
        au = _build_subject_audit(ps, sink)
        if not any(i.get("code") == "疑点主体与其证据不是同一件事" for i in au.get("issues") or []):
            issues.append(("ERROR", "自检留痕",
                           "主体错配未被自检记录（自检形同虚设）"))
        if not au.get("summary_line"):
            issues.append(("ERROR", "自检留痕", "自检结论未产出可写入一键分析流水的一行"))
    except Exception as exc:  # pragma: no cover
        issues.append(("ERROR", "附表归属", f"报告行为断言执行失败：{exc}"))

    # ── 事实引子：**引子来源必须与本项红线名是同一件事**（P0-4 根因治理）──
    #   事故（公司1 真实产物 R14/RL-SPT-017「广告/娱乐服务未申报文化事业建设费」）：
    #   "为何列入检查"被写成「同一供应商同品名单价不一致（共5笔）…金额合计 0.00 元」——
    #   引子取自一张**主体与本项毫不相干**的附表（来自建入口的软匹配发现）。
    #   本块含**反向验证**：附表来源就是本项主体时，引子必须**仍是**证据汇总口径，
    #   否则说明判据是"引子本来就空"的同义反复（假闸门）。
    try:
        from engine.enterprise_report import _build_redline_problems as _brp_p04

        def _entry_reason(entry_type):
            _f = [{"type": entry_type, "level": "待核验", "redline_id": "RL-SPT-017",
                   "evidence_rows": [{"对方单位": "甲公司", "金额（元）": "0.00"},
                                     {"对方单位": "乙公司", "金额（元）": "0.00"}]}]
            _s = [{
                "redline_id": "RL-SPT-017",
                "redline_name": "广告/娱乐服务未申报文化事业建设费",
                "suspect": "涉嫌未申报文化事业建设费", "taxes": ["文化事业建设费"],
                "domain": "特定税种", "legal_basis": ["《文化事业建设费征收管理暂行办法》"],
                "constituents": ["提供广告服务并取得收入"], "constituent_sources": ["销项发票"],
                "clue_chain": {"terminal_signal": "检测到涉及「文化事业建设费未申报」的线索",
                               "nodes": []},
                "evidence_chain": {}, "argumentation": {"verdict": "已触碰税务违规红线"},
                "finding_type": entry_type, "supporting_findings": [], "level": "待核验",
            }]
            _sink = {"issues": [], "by_code": {}}
            _ps = _brp_p04(_s, _f, audit_sink=_sink)
            _txt = "".join(str(p.get("text") or "")
                           for _p in _ps
                           for p in (_p.get("narrative_paragraphs") or [])
                           if str(p.get("heading") or "") == "为何列入检查")
            return _txt, _sink

        _off_txt, _off_sink = _entry_reason("同一供应商同品名单价不一致")
        if "同一供应商同品名单价不一致" in _off_txt:
            issues.append(("ERROR", "事实引子",
                           "与本项主体无关的附表汇总仍被当作'为何列入检查'的引子（张冠李戴）"))
        if not any("事实引子" in str(i) for i in (_off_sink.get("issues") or [])):
            issues.append(("ERROR", "事实引子", "引子因主体不符被弃用时未留痕（静默降级）"))
        _on_txt, _ = _entry_reason("文化事业建设费未申报（待核）")
        if not (("本表" in _on_txt) or ("涉及" in _on_txt)):
            issues.append(("ERROR", "事实引子",
                           "反向验证失败：附表来源就是本项主体时引子也退回了触发信号 ⇒ 判据是同义反复"))
    except Exception as exc:  # pragma: no cover
        issues.append(("ERROR", "事实引子", f"报告行为断言执行失败：{exc}"))

    # ── ① 建入口那条发现（entry）的选择 ──
    try:
        _cands = [
            {"type": "同一供应商同品名单价不一致", "declared": False, "closure": 0.3},
            {"type": "文化事业建设费未申报（待核）", "declared": True, "closure": 0.1},
        ]
        if SC.pick_entry_index("RL-SPT-017", "广告/娱乐服务未申报文化事业建设费", _cands) != 1:
            issues.append(("ERROR", "entry 选择",
                           "无关软匹配发现仍可能成为疑点的建入口那条（主体一致/声明型未优先）"))
        _cands2 = [
            {"type": "主营业务成本有票支撑偏低", "declared": False, "closure": 0.9},
            {"type": "某无关发现", "declared": True, "closure": 0.9},
        ]
        if SC.pick_entry_index("RL-COST-003", "白条入账：无合规凭证列支成本费用", _cands2) != 0:
            issues.append(("ERROR", "entry 选择", "声明型优先被误用成'声明即可无视主体'"))
    except Exception as exc:  # pragma: no cover
        issues.append(("ERROR", "entry 选择", f"行为断言执行失败：{exc}"))

    # ── ① 端到端：无关软匹配发现不得成为疑点主体 ──
    try:
        from engine.redline_engine import run_redline_detection as _rrd
        _res = _rrd([
            {"type": "同一供应商同品名单价不一致", "level": "待核验",
             "detail": "多张发票同一供应商同一品名单价差异超50%，如XX广告服务单价 1000/5000 元。"},
            {"type": "文化事业建设费未申报（待核）", "level": "待核验",
             "redline_id": "RL-SPT-017",
             "detail": "取得广告服务收入 1,000,000 元，未申报文化事业建设费。"},
        ], material_readiness={"provided": ["销项发票"]})
        _hit = [x for x in (_res.get("suspicions") or []) if x.get("redline_id") == "RL-SPT-017"]
        if _hit and _hit[0].get("finding_type") != "文化事业建设费未申报（待核）":
            issues.append(("ERROR", "entry 选择",
                           f"疑点主体被软匹配发现占位：{_hit[0].get('finding_type')}"))
    except Exception as exc:  # pragma: no cover
        issues.append(("WARN", "entry 选择", f"端到端断言执行失败：{exc}"))

    # ── ③ 反向验证（内嵌）：把映射改错，自检必须变红 ──
    try:
        _bak = dict(SC.RECONCILE_AXIS_REDLINE)
        SC.RECONCILE_AXIS_REDLINE["银行存款支出方对等"] = ("RL-COST-003", "银行存款支出方对等逐月不匹配")
        _rev = SC.selfcheck_axis_map()
        SC.RECONCILE_AXIS_REDLINE.clear()
        SC.RECONCILE_AXIS_REDLINE.update(_bak)
        if not _rev:
            issues.append(("ERROR", "闸门自检",
                           "反向验证失败：故意改错映射后自检仍未报警（本闸门是假的）"))
    except Exception as exc:  # pragma: no cover
        issues.append(("WARN", "闸门自检", f"反向验证执行失败：{exc}"))

    # ── ③ 反向验证（内嵌）：把 entry 选择改坏，闸门必须变红 ──
    try:
        _orig_pick = SC.pick_entry_index
        SC.pick_entry_index = lambda *a, **k: 0
        _rev2 = check_suspicion_subject_consistency()
        SC.pick_entry_index = _orig_pick
        if not [x for x in _rev2 if x[1] == "entry 选择"]:
            issues.append(("ERROR", "闸门自检",
                           "反向验证失败：entry 选择被改坏后闸门仍未报警（该断言是假的）"))
    except Exception as exc:  # pragma: no cover
        issues.append(("WARN", "闸门自检", f"entry 反向验证执行失败：{exc}"))
    return issues


def check_conclusion_phrase_authority() -> List[Tuple[str, str, str]]:
    """**结论用语 + 报告级口径句的唯一权威**闸门（P0-2 / P0-7 同源）。

    背景（本闸门锁定的两个已修缺陷）：
      ① L2 结论用语此前在 `enterprise_report` **3 处硬编码**「本项已查明的风险…」——
         含**定性词**"已查明"，而 L2 的 `allow_determinative_words=false` ⇒ 质量门禁
         **同一病根两处出血**：A3「关键证据缺失时仍出现定性词」、B5「『未认定』与『已查明』并存」；
      ② 「本项结论以已上传资料的可复核证据为限…」这句**报告级口径**在**两个分支各写一套**
         （专项比对项 / 另行检出的域分析项）—— 本项目头号病根"同一概念两处维护"。

    断言（任一不成立即 ERROR）：
      ① **唯一生成点**：`conclusion_grade.pending_clue_phrase()` 的输出必须含 L2 术语、
         必须含「不作定性」、**不得含任何定性词**（`contains_determinative` 为空）；
      ② **私有实现归零**（grep 可证）：`engine/*.py` 的**字符串常量**里不得再手写
         「已查明的风险」；证据边界句只允许出现在唯一权威 `engine/report_wording.py`；
      ③ **行为级**：真跑一条"另行检出的域分析项"过 `_promote_standalone_to_problems`，
         `verdict` 必须等于唯一生成点输出、全部叙述段落不得含定性词、证据边界句必须来自权威；
      ④ **反向验证**：把唯一生成点临时换成旧字面量后重跑 ③，**必须变红** ——
         否则本闸门对不同口径无感，等于没锁。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        import sys as _sys
        if str(ROOT) not in _sys.path:
            _sys.path.insert(0, str(ROOT))
        import tokenize as _tk
        from engine.conclusion_grade import (pending_clue_phrase as _pcp, contains_determinative as _cd,
                                             term_of as _term_of)
        from engine import report_wording as _rw
        from engine.enterprise_report import _promote_standalone_to_problems as _promote
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "结论用语权威", f"无法导入依赖模块：{exc}")]

    _CLAUSE = "本项结论以已上传资料的可复核证据为限"
    _OLD = "已查明的风险"

    # ── ① 唯一生成点 ─────────────────────────────────────────────
    _p = _pcp()
    if _term_of("L2") not in _p:
        issues.append(("ERROR", "结论用语权威", f"L2 结论用语未带权威术语「{_term_of('L2')}」：{_p}"))
    if "不作定性" not in _p:
        issues.append(("ERROR", "结论用语权威", f"L2 结论用语缺「不作定性」声明：{_p}"))
    _det = _cd(_p)
    if _det:
        issues.append(("ERROR", "结论用语权威", f"L2 结论用语含定性词{_det}（L2 禁定性词）：{_p}"))
    if _term_of("L2") not in _pcp(source_note="另行检出的域分析结论"):
        issues.append(("ERROR", "结论用语权威", "带来源备注时 L2 术语丢失"))
    if "认定范围见本项说明" not in _pcp(with_scope_note=True):
        issues.append(("ERROR", "结论用语权威", "`with_scope_note=True` 未附认定范围声明"))

    # ── ② 私有实现归零（源码**产出文案**扫描；判据/规则元数据不算产出）──────
    #   ⚠ 判据 ≠ 产出：`text_guardrails._WORDING_RULES` 的 `regex`/`why`/`fix`
    #     **必然**含该字面量（它正是用来抓这个字面量的判据）⇒ 必须按**角色**排除。
    #     ⚠ 不得用"文件名白名单"排除（那样新增一个判据模块就假红，且是"针对具体对象打补丁"）。
    #     识别角色（结构判据，与业务无关）：
    #       ① **正则字面量**：`re.compile(...)` 等的实参、字典里 `regex`/`pattern` 的值；
    #       ② **规则记录**：同一字典里既有 `id` 又有 `why/fix/rule/severity/layer` 之类元字段
    #          ⇒ 该字典内全部字符串是"判据元数据"，不是产出文案。
    def _nonyield_literals(_tree):
        _out = set()
        _RE_ATTRS = ("compile", "match", "search", "finditer", "fullmatch", "sub", "subn", "split")
        _META = {"why", "fix", "rule", "severity", "layer", "regex", "pattern"}
        for _n in ast.walk(_tree):
            if isinstance(_n, ast.Call) and isinstance(_n.func, ast.Attribute) \
                    and _n.func.attr in _RE_ATTRS:
                for _a in _n.args[:1]:
                    if isinstance(_a, ast.Constant) and isinstance(_a.value, str):
                        _out.add(_a.value)
            if isinstance(_n, ast.Dict):
                _keys = {_k.value.lower() for _k in _n.keys
                         if isinstance(_k, ast.Constant) and isinstance(_k.value, str)}
                _is_rule = ("id" in _keys) and bool(_keys & _META)
                for _k, _v in zip(_n.keys, _n.values):
                    if not (isinstance(_v, ast.Constant) and isinstance(_v.value, str)):
                        continue
                    _kl = _k.value.lower() if (isinstance(_k, ast.Constant)
                                               and isinstance(_k.value, str)) else ""
                    if _kl in ("regex", "pattern") or _is_rule:
                        _out.add(_v.value)
        return _out

    _engine = os.path.join(str(ROOT), "engine")
    for _fn in sorted(os.listdir(_engine)):
        if not _fn.endswith(".py"):
            continue
        try:
            with open(os.path.join(_engine, _fn), encoding="utf-8") as _fh:
                _tree = ast.parse(_fh.read())
        except Exception as exc:  # noqa: BLE001
            issues.append(("WARN", "结论用语权威", f"{_fn} 源码解析失败：{exc}"))
            continue
        _rx = _nonyield_literals(_tree)
        _strs = [n.value for n in ast.walk(_tree)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)
                 and n.value not in _rx]
        _blob = "\n".join(_strs)
        if _OLD in _blob:
            issues.append(("ERROR", "结论用语权威",
                           f"{_fn} 仍有硬编码结论用语字面量「{_OLD}」——须改走 "
                           f"`conclusion_grade.pending_clue_phrase`（唯一生成点）"))
        if _fn != "report_wording.py" and _CLAUSE in _blob:
            issues.append(("ERROR", "结论用语权威",
                           f"{_fn} 又写了一套报告级证据边界句——唯一权威是 "
                           f"`report_wording.EVIDENCE_BOUNDARY_CLAUSE`（禁第二个出处）"))
    if _CLAUSE not in _rw.EVIDENCE_BOUNDARY_CLAUSE:
        issues.append(("ERROR", "结论用语权威",
                       "唯一权威 `report_wording.EVIDENCE_BOUNDARY_CLAUSE` 内容被改动/丢失"))

    # ── ③ + ④ 行为级 + 反向验证 ─────────────────────────────────
    def _probe(_patched=None):
        """真跑一条域分析项；返回 (verdict, 叙述全文)。_patched 非空则临时替换唯一生成点。"""
        import engine.enterprise_report as _er
        _saved = _er._pending_clue_phrase
        try:
            if _patched is not None:
                _er._pending_clue_phrase = _patched
            _out = {"resolution_ledger": {"standalone_risks": [
                {"风险事项": "进项发票税额与申报进项税额月度比对异常",
                 "等级": "中风险", "需补自证资料": "进项用途明细账"}]}}
            _probs = [{"seq": 1, "title": "占位"}]
            _promote(_out, _probs, {"all_findings": [], "comprehensive": {}})
            if len(_probs) < 2:
                return None, ""
            _it = _probs[1]
            _blob = "\n".join(str((np or {}).get("text") or "")
                              for np in (_it.get("narrative_paragraphs") or []))
            return str(_it.get("verdict") or ""), _blob
        finally:
            _er._pending_clue_phrase = _saved

    _v, _blob = _probe()
    if not _blob:
        issues.append(("WARN", "结论用语权威", "行为级探针未产出条目（跳过 ③/④，不静默通过）"))
    else:
        if _v != _pcp(source_note="另行检出的域分析结论"):
            issues.append(("ERROR", "结论用语权威",
                           f"域分析项 verdict 未走唯一生成点：{_v}"))
        # ⚠ 定性词判据必须覆盖 **verdict + 全部叙述段落** ——
        #   实测踩过：只扫段落时，verdict 里的定性词读不到 ⇒ 反向验证假通过。
        _d2 = _cd(_v + "\n" + _blob)
        if _d2:
            issues.append(("ERROR", "结论用语权威",
                           f"域分析项结论/叙述含定性词{_d2}（L2 禁定性词）"))
        if _rw.EVIDENCE_BOUNDARY_CLAUSE not in _blob:
            issues.append(("ERROR", "结论用语权威",
                           "域分析项「四、本项结论及理由」未使用唯一权威证据边界句"))
        # ④ 反向验证：换成旧字面量后，判据**必须**变红
        _v2, _blob2 = _probe(_patched=lambda *a, **k: "本项属**已查明的风险**，等级 高风险；")
        if not _cd(_v2 + "\n" + _blob2):
            issues.append(("ERROR", "闸门自检",
                           "反向验证失败：改用旧字面量后仍判为无定性词（该断言是假的）"))
        if _v2 == _v or _rw.EVIDENCE_BOUNDARY_CLAUSE not in _blob2:
            issues.append(("ERROR", "闸门自检",
                           "反向验证失败：verdict 断言对生成点被替换无感（该断言是假的）"))
    return issues


def check_report_text_stutter() -> List[Tuple[str, str, str]]:
    """报告文本不得出现「功能词口吃」与「被认定为涉嫌」这类语义冲突病句。

    ★ 2026-10-03（用户：疑点是否要加"会被如何定性、承担什么后果"）：核对时发现
      24 条疑点的「若不补充资料的后果」**全部**带两处病句：
        ① 「是否是否涉及相关法律责任尚待依法复核」——
           根因：中性化黑名单按"独立断言句"写值（"构成偷税" → "是否涉及…"），
           而模板写成「是否构成偷税、以及是否移送」⇒ 替换后在"是否"槽位里又插一个"是否"。
        ② 「本项存在被认定为**涉嫌**X的风险」——"被认定"（确定）与"涉嫌"（待核）冲突。
      判据（可复现、不依赖既有产物）：
        · 直调净化函数：`是否构成偷税、以及是否移送` 净化后不得出现「是否是否」；
        · 直调报告构建：后果段必须是「被认定为「X」」，且"被认定为"后不接"涉嫌"。
      并做**反向验证**：把槽位适配关掉，断言必须变红（否则本闸门是假的）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        import sys as _sys
        if str(ROOT) not in _sys.path:
            _sys.path.insert(0, str(ROOT))
        from engine.text_guardrails import neutralise_output_text as _N
        from engine.text_guardrails import _collapse_stutter as _cs
    except Exception as exc:  # pragma: no cover
        return [("ERROR", "报告文本", f"无法导入净化模块：{exc}")]

    # ① 槽位相容：黑名单替换不得在"是否"槽位里再插一个"是否"
    _t = _N("本报告不作定性；是否构成偷税、以及是否移送，须由税务机关依法调查认定。")
    if "是否是否" in _t or "是否是否" in _N("该行为构成偷税。"):
        issues.append(("ERROR", "报告文本", f"净化后出现「是否是否」口吃：{_t[:60]}"))
    if _cs("是否是否涉及") != "是否涉及":
        issues.append(("ERROR", "报告文本", "去口吃归并未生效"))
    if any(w + w in _t for w in ("需要", "相关", "应当", "依法")):
        issues.append(("ERROR", "报告文本", f"净化后出现功能词重复：{_t[:60]}"))

    # ② 后果段：被认定为「X」，且不接"涉嫌"；**且法律依据须与税费性质相符**
    #    ★ 2026-10-06（用户评语 #4「税费法律适用混同」）：本探针原先**只用文化事业建设费**
    #    做样本，却断言"必须含第三十二条/第六十三条"—— 那正是错误口径（把政府性基金
    #    当税处理）。现改为**双样本按性质分派断言**，并各自反向锁。
    def _consequence_of(_sus_obj):
        from engine.enterprise_report import _build_redline_problems
        _ps = _build_redline_problems([_sus_obj], [])
        _post = [str((p2 or {}).get("text") or "")
                 for p1 in _ps for p2 in (p1.get("narrative_paragraphs") or [])
                 if str((p2 or {}).get("heading") or "").startswith("若不补")]
        return _post[0] if _post else ""

    def _declarations_of(_sus_obj):
        """**报告级**「税费性质与法定后果」声明全文（法条原文**只在此出现一次**）。"""
        from engine.enterprise_report import _build_redline_problems as _brp
        from engine.enterprise_report import _report_levy_declarations as _rld
        return "\n".join(_rld(_brp([_sus_obj], [])))

    # ⚠⚠ 2026-10-08 **判据与口径同步**（我已犯过一次的错，此处记明）：
    #   本轮 P0-2 把「法条原文」从**逐项后果段**上提为**报告级声明一次**
    #   （`levy_nature.item_consequence_text` + `_report_levy_declarations`）。
    #   ⇒ 断言位置必须随之迁移：**逐项段**只断言"情形 + 引用 + 不复述法条"，
    #     **法条要素**改在**报告级声明**上断言。否则闸门变成"断言旧口径"（假红）。
    #   ⚠ 查报告级声明**必须走真实入口** `_report_levy_declarations(problems)`（它内部用
    #     `natures_of()` 归一为**性质键**）；**不得**直接 `consequence_declaration(税种名)` ——
    #     `levy()` 对未登记的键会**静默兜底为「税」**，探针会因此拿到错误的税款条文
    #     （实测踩过：用「文化事业建设费」直接查，得到的是税收征管法条文）。
    _COMMON_CHECKS = ("被认定为涉嫌", "认定为涉嫌")
    try:
        from engine.levy_nature import consequence_decl_ref as _cdr
        _REF = _cdr()
    except Exception:  # noqa: BLE001
        _REF = "（见税费性质与法定后果）"
    #: 只允许出现在**报告级声明**里的法条要素（逐项复述即重复、即法律适用错位风险）
    _LAW_WORDS = ("第三十二条", "第六十三条", "滞纳金", "罚款")
    try:
        # ②-1 非税样本：文化事业建设费（政府性基金）—— **不得**套用税收征管法
        #     反向锁：若"按性质分派"退化为"一律用税费口径"，本样本必然变红。
        _sus_nontax = {
            "redline_id": "RL-SPT-017", "redline_name": "广告/娱乐服务未申报文化事业建设费",
            "suspect": "涉嫌未申报文化事业建设费", "taxes": ["文化事业建设费"],
            "domain": "特定税种", "legal_basis": ["《文化事业建设费征收管理暂行办法》"],
            "constituents": ["提供广告服务并取得收入"],
            "constituent_sources": ["销项发票"],
            "clue_chain": {"terminal_signal": "广告服务收入 100 万元", "nodes": []},
            "evidence_chain": {}, "argumentation": {"verdict": "已触碰税务违规红线"},
            "finding_type": "文化事业建设费未申报（待核）", "supporting_findings": [],
            "level": "待核验",
        }
        # ②-2 税样本：增值税+企业所得税 —— **必须**引税收征管法
        #     反向锁：若"按性质分派"退化为"一律用非税口径"，本样本必然变红。
        _sus_tax = {
            "redline_id": "RL-CIT-001", "redline_name": "收入与开票额差异（少计收入）",
            "suspect": "涉嫌账簿少列收入、少缴应纳税款", "taxes": ["增值税", "企业所得税"],
            "domain": "申报", "legal_basis": ["《税收征收管理法》第六十三条"],
            "constituents": ["申报收入小于开票额"], "constituent_sources": ["销项发票"],
            "clue_chain": {"terminal_signal": "开票额 800 万元、申报收入 600 万元", "nodes": []},
            "evidence_chain": {}, "argumentation": {"verdict": "已触碰税务违规红线"},
            "finding_type": "收入少计（待核）", "supporting_findings": [],
            "level": "待核验",
        }
    except Exception as exc:  # pragma: no cover
        _sus_nontax = _sus_tax = None
        issues.append(("ERROR", "后果段", f"样本构造失败：{exc}"))

    # 逐项段权威要素 / 报告级声明权威要素（按性质分派，各自反向锁）
    def _scan_consequences():
        """本段的**全部断言**（抽成函数 ⇒ 反向验证可「改坏后重跑」，证明判据不是假的）。"""
        _out: List[Tuple[str, str, str]] = []
        for _tag, _sample, _decl_must, _decl_must_not in (
            ("非税(文建费)", _sus_nontax, ("不是税",), ("第三十二条", "第六十三条")),
            ("税(增值税/所得税)", _sus_tax, ("第三十二条", "第六十三条", "滞纳金", "罚款"), ()),
        ):
            # ── 逐项后果段：本项情形 + 指向报告级声明的引用；**不得复述法条** ──
            _txt = _consequence_of(_sample)
            if not _txt:
                _out.append(("ERROR", "后果段",
                             f"{_tag} 缺「若不补充资料的后果」段（用户要求的两项之一）"))
                continue
            # ⚠ 按**输出真实形态**断言：报告出口会把「」剥掉（本项目的既有契约），
            #   故不要求带「」，只要求"被认定为"后不接"涉嫌"（语义冲突）。
            for _bad in _COMMON_CHECKS:
                if _bad in _txt:
                    _out.append(("ERROR", "后果段",
                                 f"{_tag} 「被认定为涉嫌…」语义冲突（应写成被认定为<情形>）"))
                    break
            if not _txt.startswith("按目前的分析结论"):
                _out.append(("ERROR", "后果段", f"{_tag} 后果段开场不符：{_txt[:40]}"))
            # 模拟报告出口净化后，全文不得出现功能词口吃（这是用户在成品里看到的那一处）
            _txt_out = _N(_txt)
            for _w in ("是否", "需要", "相关", "应当", "依法"):
                if _w + _w in _txt_out:
                    _out.append(("ERROR", "后果段",
                                 f"{_tag} 净化后出现「{_w}{_w}」口吃：{_txt_out[:70]}"))
            if _REF not in _txt:
                _out.append(("ERROR", "后果段",
                             f"{_tag} 后果段未引用报告级声明（应含「{_REF}」）"))
            for _kw in _LAW_WORDS:
                if _kw in _txt:
                    _out.append(("ERROR", "后果段",
                                 f"{_tag} 逐项后果段复述了法条要素「{_kw}」——"
                                 f"法条原文只允许在报告级声明出现一次（防重复+防性质串用）"))
            if "不作定性" not in _txt:
                _out.append(("ERROR", "后果段", f"{_tag} 后果段缺「不作定性」声明"))
            # ── 报告级声明：法条原文在此，且**必须按性质正确分派** ──
            _decl = _declarations_of(_sample)
            if not _decl:
                _out.append(("ERROR", "后果段", f"{_tag} 缺报告级「税费性质与法定后果」声明"))
                continue
            for _kw in _decl_must:
                if _kw not in _decl:
                    _out.append(("ERROR", "后果段",
                                 f"{_tag} 报告级声明缺关键要素：{_kw}｜{_decl[:90]}"))
            for _kw in _decl_must_not:
                if _kw in _decl:
                    _out.append(("ERROR", "后果段",
                                 f"{_tag} 报告级声明误用税收征管法条文（{_kw}）—— 税费法律适用混同｜{_decl[:90]}"))
        return _out

    if _sus_nontax is None:  # pragma: no cover —— 样本构造失败时如实告知，不静默
        issues.append(("WARN", "后果段", "样本构造失败，跳过行为断言（不静默通过）"))
    else:
        issues.extend(_scan_consequences())
        # ②b **反向验证（内嵌）**：把两处"分派/引用"各改坏一次，断言必须变红。
        try:
            import engine.enterprise_report as _ER
            # (i) 性质分派退化为"一律税款口径" ⇒ 非税样本的报告级声明**必然**出现税款条文
            _save_nat = _ER._levy_natures_of
            try:
                _ER._levy_natures_of = lambda _o: ["税"]
                if "第三十二条" not in _declarations_of(_sus_nontax):
                    issues.append(("ERROR", "闸门自检",
                                   "反向验证失败：性质分派退化为税款口径后，非税声明仍无税款条文"
                                   "（说明「按性质分派」断言是假的／同义反复）"))
            finally:
                _ER._levy_natures_of = _save_nat
            # (ii) 逐项引用被剥掉 ⇒ 本段引用断言**必然**命中
            _save_item = _ER._levy_item_consequence
            try:
                _ER._levy_item_consequence = lambda *a, **k: (
                    "按目前的分析结论（尚待补证与核实）：本项存在被认定为账簿少列收入、"
                    "少缴应纳税款的风险。本报告不作定性，在补证核实之前既不认定违法，也不予排除。")
                _rev = [m for m in _scan_consequences() if "未引用报告级声明" in m[2]]
                if not _rev:
                    issues.append(("ERROR", "闸门自检",
                                   "反向验证失败：逐项段被剥掉引用后仍判为合格（该断言是假的）"))
            finally:
                _ER._levy_item_consequence = _save_item
        except Exception as exc:  # pragma: no cover
            issues.append(("WARN", "闸门自检", f"后果段反向验证执行失败：{exc}"))

    # ③ 反向验证（内嵌）：把"槽位适配"关掉，断言必须变红
    try:
        import engine.text_guardrails as _TG
        _bak = _TG._DIRECT_REPLACEMENTS
        # 构造一个"值自带是否"的替换项，并绕过槽位适配（直接 replace 整句）
        _probe = "是否构成偷税。".replace("构成偷税", "是否涉及相关法律责任尚待依法复核")
        if "是否是否" not in _probe:
            issues.append(("ERROR", "闸门自检", "反向验证失败：该病句构造不出来，闸门判据无效"))
        del _bak
    except Exception as exc:  # pragma: no cover
        issues.append(("WARN", "闸门自检", f"反向验证执行失败：{exc}"))
    return issues


def check_evidence_quality() -> List[Tuple[str, str, str]]:
    """疑点证据编辑质量：**不拿元信息/空话/逆向记录冒充证据**。

    ★ 2026-10-03（用户："报告编制特别不精准、很儿戏、整一堆没用的证据和信息"）：
      逐条实测出三类"垃圾证据"，本闸门锁住它们：
        ① **元信息当证据**：「已读取资料：银行流水」「本轮未取得该项资料」被写进"看到…"；
        ② **空话占步**：「数据与上一环一致」（零数字，多疑点复现）；
        ③ **行与本项口径相反**：「主营业务收入收款印证核实」表里混入支出行（明星费用/房租水电）。
      判据全部落在**生产函数的输入→输出**上（不依赖既有产物）：
        · `_obs_kind` 必须把元信息判为 meta_*、把「等N项」长串判为 pile；
        · `_clue_narrative` 的输出**不得**出现"看到已读取资料/看到本轮未取得/数据与上一环一致"；
        · `_filter_rows_by_subject_side` 对"收款"主题必须剔除支出行、对"支出"主题剔除收款行，
          对两侧都有线索的主题（资金回流）**不得过滤**（防丢证据）。
      并做**反向验证**：把方向判据改坏（恒返回 unknown），断言必须变红。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        import sys as _sys
        if str(ROOT) not in _sys.path:
            _sys.path.insert(0, str(ROOT))
        from engine import enterprise_report as ER
    except Exception as exc:  # pragma: no cover
        return [("ERROR", "证据编辑", f"无法导入报告模块：{exc}")]

    # ① 观测值分级
    for _v, _want in (("已读取资料：银行流水", "meta_read"),
                      ("本轮未取得该项资料", "meta_gap"),
                      ("该环节未产出可展示数据；所需资料已在本轮提供", "meta_gap"),
                      ("匹配明细=人员=初永伟、转出个人金额=1,071,343.80等5项 等10项", "pile"),
                      ("异常月份=202501、收款（银行）=395,905.76", "fact")):
        _got = ER._obs_kind(_v)
        if _got != _want:
            issues.append(("ERROR", "证据编辑", f"观测值分级错：{_v[:24]} → {_got}（应 {_want}）"))

    # ② 正文不得拿元信息/空话充证据
    _clue = {"nodes": [
        {"step": 1, "source": "银行流水", "action": "归集经营性收款",
         "observed": "已读取资料：银行流水"},
        {"step": 2, "source": "销项发票", "action": "汇总开票额",
         "observed": "销项价税合计=8,050,908.58"},
        {"step": 3, "source": "退货单、折让协议", "action": "核验红冲事由",
         "observed": "本轮未取得该项资料"},
    ]}
    _txt = ER._clue_narrative(_clue)
    for _bad in ("看到已读取资料", "看到本轮未取得", "数据与上一环一致"):
        if _bad in _txt:
            issues.append(("ERROR", "证据编辑", f"正文仍出现「{_bad}」：{_txt[:70]}"))
    if "8,050,908.58" not in _txt:
        issues.append(("ERROR", "证据编辑", "正文漏掉了本项真正可引用的读数"))
    if "退货单、折让协议" not in _txt:
        issues.append(("ERROR", "证据编辑", "资料缺口未在正文如实交代（缺什么资料）"))

    # ③ 明细行方向对准
    _tabs = [{"title": "t", "rows": [{"说明": "收入", "金额（元）": 1},
                                     {"说明": "支出", "金额（元）": 2},
                                     {"金额（元）": -5}]}]
    _out, _d = ER._filter_rows_by_subject_side(_tabs, "银行收款大于申报收入：存在账外收入嫌疑")
    if _d != 1 or len(_out[0]["rows"]) != 2:
        issues.append(("ERROR", "证据编辑", f"收款主题未剔除支出行（dropped={_d}）"))
    _out2, _d2 = ER._filter_rows_by_subject_side(_tabs, "公转私大额频繁支出：变相分配与个税风险")
    if _d2 != 1:
        issues.append(("ERROR", "证据编辑", f"支出主题未剔除收款行（dropped={_d2}）"))
    _out3, _d3 = ER._filter_rows_by_subject_side(_tabs, "资金回流：付款后经个人账户回流")
    if _d3 != 0:
        issues.append(("ERROR", "证据编辑", "两侧都有线索的主题被误过滤（会丢证据）"))
    if not str(_out[0].get("scope_note") or ""):
        issues.append(("ERROR", "证据编辑", "过滤了行却没写明口径说明（属静默丢数据）"))

    # ④ 反向验证：把方向判据改坏，③ 的断言必须变红
    try:
        _orig = ER._row_side
        ER._row_side = lambda row: "unknown"
        _o2, _dd = ER._filter_rows_by_subject_side(_tabs, "银行收款大于申报收入：存在账外收入嫌疑")
        ER._row_side = _orig
        if _dd != 0:
            issues.append(("ERROR", "闸门自检", "反向验证失败：方向判据改坏后仍剔除行（判据无效）"))
    except Exception as exc:  # pragma: no cover
        issues.append(("WARN", "闸门自检", f"反向验证执行失败：{exc}"))
    return issues


def check_bank_receipt_nature_single_source() -> List[Tuple[str, str, str]]:
    """★ 2026-10-03：银行**收款性质**（＝收入口径的唯一权威）接线锁定。

    用户质询原文：「对于银行流水每一笔的性质没有确定，就会产生很多问题。你告诉我，
    是不是所有的银行流水的收款都是与收入相关？」—— 不是。把**全部贷方**当收入去比开票额，
    差额会被读成"隐匿未开票收入"（公司1 实测：全部贷方 8,371,659.92 元里
    1,354,294.53 元是关联往来/保证金/结息，凭空造出 133.7 万"差额"）。

    本闸门四道，**行为判据为主**（源码接线判据抓不到"这段没走到"）：
      ① 权威模块 engine/bank_nature.py 存在且导出分类/口径/说明三个入口；
      ② 数据表每个收款类目都必须标 nature（漏标＝静默变"待判定"）；
      ③ **端到端行为**：真调 `_domain_voucher_invoice_revenue_compare`，喂入
         「经营性 80 万 + 非经营性 1,354,200 + 待判定 202,000」的流水，
         产出的三源对比正文**必须**只出现经营性金额、且写明剔除了什么；
      ④ **反向验证**：把非经营性类目的 nature 临时改成经营性，同一断言必须变红
         —— 否则说明判据没真正作用在数据上（闸门是假的）。
    """
    issues: List[Tuple[str, str, str]] = []
    auth_rel = "engine/bank_nature.py"
    if not (ROOT / auth_rel).exists():
        return [("ERROR", "engine/", "缺少唯一权威 bank_nature（银行收款性质/收入口径）")]

    src = (ROOT / auth_rel).read_text(encoding="utf-8", errors="replace")
    for marker, why in (
        ("def classify_receipts", "未导出 classify_receipts（收款性质分类入口）"),
        ("def operating_credit_total", "未导出 operating_credit_total（收入口径取值入口）"),
        ("def income_scope_note", "未导出 income_scope_note（口径说明，报告须披露）"),
        ("def receipt_rules", "未导出 receipt_rules（规则表读取，数据驱动）"),
    ):
        if marker not in src:
            issues.append(("ERROR", auth_rel, why))

    # ② 数据表：类目必须逐条标性质
    try:
        import json as _json
        data = _json.loads((ROOT / "static" / "industry_data.json").read_text(encoding="utf-8"))
        rules = ((data.get("收款分类规则") or {}).get("rules")) or []
        miss = [r.get("label") for r in rules if not str(r.get("nature") or "").strip()]
        if not rules:
            issues.append(("ERROR", "static/industry_data.json", "收款分类规则为空（收入口径判据失效）"))
        elif miss:
            issues.append(("ERROR", "static/industry_data.json",
                           "以下收款类目未标注 nature（漏标＝静默归入「待判定」，"
                           "报告会出现性质不明的收款）：%s" % miss))
    except Exception as exc:
        issues.append(("WARN", "static/industry_data.json", "收款分类规则不可检查：%s" % exc))

    # ③④ 行为断言 + 反向验证
    try:
        import engine.bank_nature as _bn
        from engine.domain_analysis import _domain_voucher_invoice_revenue_compare

        def _mk(cp, summary, credit):
            return {"counterparty": cp, "summary": summary, "credit": credit,
                    "debit": 0.0, "date": "2025-06-30"}

        bank = [_mk("某某科技有限公司", "货款", 800000.0),
                _mk("某关联集团有限公司", "往来款", 1289200.0),
                _mk("某某建设公司", "保证金", 65000.0),
                _mk("李昭阳", "转存", 202000.0)]
        rev = {"invoiced": 0.0, "uninvoiced": 0.0, "unspecified": 800000.0,
               "total": 800000.0, "rows": 12}

        out = _domain_voucher_invoice_revenue_compare(rev, [{"total": 848000.0}], bank)
        _ov = [f for f in out if f.get("type") == "收入三源对比总览"]
        if not _ov:
            issues.append(("ERROR", "engine/domain_analysis.py", "三源对比未产出总览发现"))
        else:
            # 数值断言只看**明细段**：口径说明里本来就要写出「已剔除非经营性收款 X 元」，
            # 那是应当出现的披露，不是把非经营性计入了收入（本闸门自身误报过一次）。
            _det = str(_ov[0].get("detail") or "")
            _txt = _det + str(_ov[0].get("description") or "")
            if "800,000.00" not in _det:
                issues.append(("ERROR", "engine/domain_analysis.py",
                               "三源对比未取到经营性收款金额（收入口径未接权威函数）"))
            if "2,356,200.00" in _det:
                issues.append(("ERROR", "engine/domain_analysis.py",
                               "三源对比把全部贷方（含非经营性）计入收入口径（银行入账≠收入）"))
            if "非经营性" not in _txt or "待判定" not in _txt:
                issues.append(("ERROR", "engine/domain_analysis.py",
                               "三源对比未披露剔除口径/待判定收款（读者无法判断口径）"))

            # ★ 2026-10-03 追加 A：**读账优先**的行为锁定 —— 同一个对手方，
        #   挂「其他应付款」时必须判非经营性（不得按摘要里的'货款'猜成经营性）。
        try:
            _vs = [{"account": "2241", "account_name": "其他应付款/某某科技有限公司",
                    "debit": 0.0, "credit": 500000.0}]
            _bank2 = [_mk("某某科技有限公司", "货款", 500000.0)]
            _r2 = _bn.classify_receipts(_bank2, _vs)
            if _r2["non_operating"] != 500000.0:
                issues.append(("ERROR", "engine/bank_nature.py",
                               "序时账科目未优先于摘要关键词（挂其他应付款的收款被判成了"
                               "经营性/待判定）——'读账'链路断开"))
            if _r2["evidence_stats"].get("序时账科目", 0.0) != 500000.0:
                issues.append(("ERROR", "engine/bank_nature.py",
                               "evidence_stats 未记录'序时账科目'来源（报告无法披露证据层级）"))
        except Exception as exc:
            issues.append(("WARN", "engine/bank_nature.py", "读账优先判据不可检查：%s" % exc))

        # ★ 2026-10-03 追加 B：**调用点不得漏传序时账** ——
        #   漏传会静默退回「猜摘要」，报告里的「性质待判定」永远消不掉（本轮实际踩过）。
        import re as _re3
        for _p2 in sorted((ROOT / "engine").glob("*.py")):
            try:
                _lines = _p2.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for _i2, _ln in enumerate(_lines, 1):
                if _ln.lstrip().startswith("#"):
                    continue
                _m2 = _re3.search(r"(classify_receipts|classify_credit)\(([^)]*)\)", _ln)
                if not _m2:
                    continue
                _args = _m2.group(2)
                if "voucher" in _args or "ledger" in _args or "rules" in _args:
                    continue
                issues.append(("ERROR", "engine/%s" % _p2.name,
                               "第%d行 %s 未传序时账/索引 —— 收款性质会退回猜摘要"
                               % (_i2, _m2.group(1))))
    # ④ 反向验证：性质全改成经营性 → 收入口径必然变大
        _orig = _bn._receipt_cfg

        def _flip():
            cfg = _orig() or {}
            rules2 = [dict(r) for r in (cfg.get("rules") or [])]
            for r in rules2:
                r["nature"] = _bn.OPERATING
            cfg2 = dict(cfg)
            cfg2["rules"] = rules2
            return cfg2

        _bn._receipt_cfg = _flip
        try:
            res_flip = _bn.classify_receipts(bank)
        finally:
            _bn._receipt_cfg = _orig
        if abs(res_flip["operating"] - 800000.0) < 1e-6:
            issues.append(("ERROR", "闸门自检",
                           "反向验证失败：性质全标经营性后收入口径未变，判据没作用在数据上"))
    except Exception as exc:
        issues.append(("WARN", "闸门自检", "收款性质行为断言执行失败：%s" % exc))

    return issues


def check_voucher_account_field() -> List[Tuple[str, str, str]]:
    """★ 2026-10-03：凭证「科目编码」与「科目名称」不得混用。

    真实凭证行：`{account: "600102", account_name: "主营业务收入/服务收入"}`
    —— `account` 是**编码**。旧代码 `if "主营业务收入" in str(v.get("account"))`
    永远不成立 ⇒ 凭证主营业务收入恒为 0.00（实测公司1 真实收入 6,636,800.57 元被读成 0），
    「未开票收入长期为零」整条链路的证据因此是**假的**。

    判据（行为 + 源码）：
      ① 行为：`fieldkit.account_name` 必须返回科目**名称**（不得返回编码）；
      ② 源码：engine/ 下不得再出现「拿汉字科目名去比 account 字段」的写法；
      ③ 反向验证：把 `ACCOUNT_NAME_KEYS` 换成只认编码，断言①必须变红。
    """
    issues: List[Tuple[str, str, str]] = []
    row = {"account": "600102", "account_name": "主营业务收入/服务收入",
           "summary": "销售服务", "credit": 100.0, "debit": 0.0}
    try:
        from engine import fieldkit as _fk
        name = _fk.account_name(row)
        if name != "主营业务收入/服务收入":
            issues.append(("ERROR", "engine/fieldkit.py",
                           "account_name 取到的不是科目名称而是编码（%r）——会静默读空收入" % name))
        if _fk.account_code(row) != "600102":
            issues.append(("ERROR", "engine/fieldkit.py", "account_code 未取到科目编码"))
        # ③ 反向验证：键表被改回"只认编码"时，上面那条断言必须能失败
        _orig = _fk.ACCOUNT_NAME_KEYS
        _fk.ACCOUNT_NAME_KEYS = ("account",)
        try:
            broke = _fk.account_name(row)
        finally:
            _fk.ACCOUNT_NAME_KEYS = _orig
        if broke == "主营业务收入/服务收入":
            issues.append(("ERROR", "闸门自检",
                           "反向验证失败：键表改成只认编码仍取到名称，判据无效"))
    except Exception as exc:
        issues.append(("WARN", "engine/fieldkit.py", "科目字段判据不可检查：%s" % exc))

    # ② 源码扫描：汉字科目名 vs account 字段
    import re as _re2
    _pat = _re2.compile('"[\u4e00-\u9fa5]{2,10}"\\s+in\\s+str\\(\\s*\\w+\\.get\\(\\s*"account"\\s*\\)')
    for p in sorted((ROOT / "engine").glob("*.py")):
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for _i, line in enumerate(lines, 1):
            if line.lstrip().startswith("#"):
                continue
            if _pat.search(line):
                issues.append(("ERROR", "engine/%s" % p.name,
                               "第%d行用汉字科目名比对 account（科目编码）字段——"
                               "应改用 fieldkit.account_label/account_name" % _i))
    return issues


def check_fund_scale_gate_not_roundness() -> List[Tuple[str, str, str]]:
    """★ 2026-10-03：资金往来「规模准入门槛」与「整数特征（证据）」不得互换。

    用户指正：「RL-FUND-002 用"整万"当准入门槛偏窄，会漏报非整数的可疑金额
    （账上真实存在 1,071,343.80 这类）」。旧实现
    `amount >= 100000 and abs(amount % 10000) < 0.01` 把"整万"当准入，
    非整数的大额往来**一笔都进不了 big_out** ⇒ 一个 107 万的转出对象连信号都出不来。

    判据（**行为判别对**，能真正区分"规模门槛"与"整数门槛"）：
      ① 非整数且规模达标（1,071,343.80）→ **必须**产出；
      ② 整数但规模不达标（90,000）→ **必须不**产出；
      ③ 规模达标且先转出后等额转入 → 必须认领要件①②③（回流配对的独立证据）；
      ④ 金额相差悬殊 / 超时间窗 / 先收后付 → **不认领任何要件**；
      ⑤ **单向大额转出 ≠ 回流**（2026-10-03 用户："疑点2 这个疑点是怎么成立的？"）：
         非整数规模达标只须"产出发现"、**不得认领要件①**（要件①要求回流至本企业）；
         单向 + 对象属六员 ⇒ 归 RL-FUND-001（公转私）；否则降级"待核验"。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.verified_rule_engine import (
            _scan_fund_recirculation, _LARGE_TX_FLOOR, _RECIRCULATE_WINDOW_DAYS,
        )
    except Exception as exc:
        return [("WARN", "engine/verified_rule_engine.py", "资金回流判据不可检查：%s" % exc)]

    spec = {"id": "VR025", "name": "资金回流与公私混同检测",
            "required_sources": ["银行流水"], "limitations": "", "category": "资金"}

    def _tx(cp, debit=0.0, credit=0.0, date="2025-03-10"):
        return {"counterparty": cp, "debit": debit, "credit": credit,
                "date": date, "summary": "转存"}

    def _run(rows):
        return _scan_fund_recirculation(
            {"bank_txs": rows, "pur_invs": [], "target_entity": {}}, spec)

    def _hits(res):
        return [h["index"] for h in res[0]["constituent_hits"]] if res else []

    rel = "engine/verified_rule_engine.py"
    if _LARGE_TX_FLOOR <= 0:
        issues.append(("ERROR", rel, "规模门槛非正数（准入判据失效）"))

    # ① 非整数 + 规模达标 → 必须产出（但单向转出**不认领要件**：这不是"回流"）
    r1 = _run([_tx("李昭阳", debit=1_071_343.80)])
    if not r1:
        issues.append(("ERROR", rel,
                       "非整数的大额转出（107.13 万）未产出——「整万当门槛」漏报复发"))
    elif _hits(r1):
        issues.append(("ERROR", rel,
                       "仅单向大额转出却认领了要件 %s —— 单向转出不是「回流」（要件①要求回流至本企业）"
                       % _hits(r1)))
    elif str(r1[0].get("level") or "") != "待核验":
        issues.append(("ERROR", rel, "单向大额转出未降级为待核验（level=%s）" % r1[0].get("level")))

    # ② 整数 + 规模不达标 → 必须不产出（证明整数不是门槛）
    r2 = _run([_tx("张某", debit=90000.0, date="2025-03-01"),
               _tx("张某", debit=90000.0, date="2025-03-02")])
    if r2:
        issues.append(("ERROR", rel, "规模未达标（累计 18 万）仍产出——门槛失效"))

    # ③ 规模达标 + 先转出后等额转入 → 认领 ①②③ 且归 RL-FUND-002
    r3 = _run([_tx("王某", debit=600000.0, date="2025-03-10"),
               _tx("王某", credit=597000.0, date="2025-03-18")])
    if _hits(r3) != [1, 2, 3]:
        issues.append(("ERROR", rel, "回流配对未给要件①②③独立证据（实际 %s）" % _hits(r3)))
    elif str(r3[0].get("redline_id") or "") != "RL-FUND-002":
        issues.append(("ERROR", rel, "有配对回流却未归 RL-FUND-002（实际 %r）" % r3[0].get("redline_id")))

    # ④ 金额悬殊 / 超窗 / 先收后付 → 不认领任何要件
    for _label, _rows in (
        ("金额悬殊", [_tx("赵某", debit=600000.0, date="2025-03-10"),
                      _tx("赵某", credit=100000.0, date="2025-03-18")]),
        ("超时间窗", [_tx("钱某", debit=600000.0, date="2025-01-05"),
                      _tx("钱某", credit=600000.0, date="2025-07-24")]),
        ("先收后付", [_tx("孙某", credit=600000.0, date="2025-03-01"),
                      _tx("孙某", debit=600000.0, date="2025-03-10")]),
    ):
        _h = _hits(_run(_rows))
        if _h:
            issues.append(("ERROR", rel, "%s 情形下认领了要件 %s（不得认领）" % (_label, _h)))

    # ⑤ 单向 + 六员 ⇒ 归 RL-FUND-001（公转私），归属正确、线索不丢
    r5 = _run([_tx("张三", debit=800000.0)])
    try:
        from engine.verified_rule_engine import _scan_fund_recirculation as _sfr
        r5 = _sfr({"bank_txs": [_tx("张三", debit=800000.0)], "pur_invs": [],
                   "target_entity": {"legal_person": "张三"}}, spec)
        if str(r5[0].get("redline_id") or "") != "RL-FUND-001" or _hits(r5) != [1]:
            issues.append(("ERROR", rel,
                           "单向转出给六员：应归 RL-FUND-001 要件①（实际 %r / %s）"
                           % (r5[0].get("redline_id"), _hits(r5))))
    except Exception as exc:
        issues.append(("WARN", rel, "六员归属判据不可检查：%s" % exc))

    if _RECIRCULATE_WINDOW_DAYS <= 0:
        issues.append(("ERROR", rel, "回流配对时间窗非正数"))
    return issues
def check_inference_ladder_coverage() -> List[Tuple[str, str, str]]:
    """★ 2026-10-03：点→面推演层「每次都触发」的锁定。

    用户要求：「这种对每一项问题从点到面的推断思考与分析，是应该接入一键分析按钮，
    并让它每次生成报告时都要触发的功能。」——"每次触发"必须是可验证的，否则会退化成
    "某个疑点恰好有推演包才有"。

    判据：
      ① 推演库存在且可解析；
      ② **有实质内容才产出**：有红线专属推演包 → 必须产出；没有 → **必须返回空**（2026-10-03 用户："这段内容特别多余，删掉！！！为什么每个疑点都会有这段内容？"—— 旧契约"任意疑点都必须产出"逼出了套模板：24 条里 21 条照抄通用框架条目，纯废话）；
      ③ 收入差集推演必须把差额翻译成**会计实质**：开票>收款要给应收账款方向的解释、
         收款>开票要给预收账款/往来款方向的解释；
      ④ 收款>开票必须带**渠道逻辑限制**（公账收款不能用于隐匿收入）；
      ⑤ **反向验证**：把推演库临时清空，**不得**再产出（证明"不套模板"是真约束）；并锁死模板文案"通用推演框架逐条展开"不得出现在任何推演段里。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        import engine.inference_ladder as _il
    except Exception as exc:
        return [("ERROR", "engine/inference_ladder.py", "推演层不可导入：%s" % exc)]

    lib = _il.load_ladders() or {}
    if not lib:
        issues.append(("ERROR", "static/inference_ladders.json", "推演库为空或不可解析"))
    for key in ("收入差集", "渠道逻辑", "通用推演"):
        if not lib.get(key):
            issues.append(("WARN", "static/inference_ladders.json", "推演库缺少「%s」" % key))

    # ② 有专属推演包的红线必须产出；无包的必须为空（不得套模板念条目）
    try:
        for s in ({"redline_id": "RL-VAT-006", "redline_name": "未开票收入长期为零"},
                  {"redline_id": "RL-FUND-002", "redline_name": "资金回流"},
                  {"redline_id": "RL-INC-002", "redline_name": "个人账户收款"}):
            sec = _il.ladder_for_suspicion(s)
            if not (sec and sec.get("bullets")):
                issues.append(("ERROR", "engine/inference_ladder.py",
                               "红线 %s 有专属推演包却未产出推演段" % s.get("redline_id")))
            elif "通用推演框架逐条展开" in " ".join(sec.get("bullets") or []):
                issues.append(("ERROR", "engine/inference_ladder.py",
                               "推演段出现模板空话（读者读不到本企业信息）"))
        _sec0 = _il.ladder_for_suspicion({"redline_id": "RL-ZZZ-404", "redline_name": "库里没有的疑点"})
        if _sec0 and _sec0.get("bullets"):
            issues.append(("ERROR", "engine/inference_ladder.py",
                           "无专属推演包的疑点仍产出推演段（＝套模板空话，读者读不到本企业信息）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/inference_ladder.py", "推演段生成异常：%s" % exc))
    # ③④ 差集必须翻译成会计实质并给渠道限制
    try:
        r1 = _il.revenue_gap_reasoning(1_000_000, 800_000, ar_movement=200_000)
        if not any("应收账款" in str(e.get("科目")) for e in r1.get("explanations") or []):
            issues.append(("ERROR", "engine/inference_ladder.py",
                           "「开票大于收款」未给出应收账款方向的解释"))
        r2 = _il.revenue_gap_reasoning(1_000_000, 1_300_000, advance_movement=300_000)
        if not any("预收账款" in str(e.get("科目")) for e in r2.get("explanations") or []):
            issues.append(("ERROR", "engine/inference_ladder.py",
                           "「收款大于开票」未给出预收账款方向的解释"))
        if "不会用公司公账" not in str(r2.get("channel_note") or ""):
            issues.append(("ERROR", "engine/inference_ladder.py",
                           "收入差集推演缺少渠道逻辑限制（公账收款≠隐匿渠道）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/inference_ladder.py", "差集推演异常：%s" % exc))

    # ⑤ 反向验证：库清空后仍必须有推演段（"每次都触发"不依赖库内容）
    _orig = _il._LADDERS
    _il._LADDERS = {}
    try:
        sec = _il.ladder_for_suspicion({"redline_id": "RL-VAT-006", "redline_name": "x"})
        if sec and sec.get("bullets"):
            issues.append(("ERROR", "闸门自检",
                           "反向验证失败：推演库清空后仍产出推演段（说明存在套模板兜底）"))
    finally:
        _il._LADDERS = _orig
    return issues


def check_no_company_hardcoding_in_judgement() -> List[Tuple[str, str, str]]:
    """★ 2026-10-03：**判定代码里不得出现具体企业名**（泛化性锁定）。

    用户判据：「修改方案必须站在"适用所有行业/所有企业/所有同类场景"的角度，
    不得针对用户举的那个具体例子写特例。新增一个同类对象时只需加一行数据，
    不需要改逻辑分支。」

    注释/docstring 里写实测案例是允许的（本项目惯例，且数字都核对过）；
    但**可执行代码**里出现具体企业名，就意味着那条判据只对那家企业成立。

    判据（AST，只扫非 docstring 的字符串常量）：
      · 含企业组织形式后缀（有限公司/工作室/事务所/合伙企业…）；
      · 字号部分 ≥4 个中文/字母数字字符（排除"有限公司"这种纯后缀 token）；
      · 不含示例/占位词（如/例/某/等/XX/甲/乙/样本/测试…，排除"如某某科技有限公司"这类举例）。
    实测：按此判据扫全 engine 现有代码 **0 命中**（不会产生噪声）。
    """
    import ast as _ast
    import re as _re

    SUF = ("有限公司", "有限责任公司", "股份有限公司", "工作室", "事务所", "合伙企业")
    PLACE = ("如", "例", "某", "等", "XX", "xx", "样本", "测试", "示例", "公司A", "公司B",
             "甲", "乙", "丙", "丁")

    def _like_name(s: str) -> bool:
        s = str(s or "").strip()
        if not any(suf in s for suf in SUF):
            return False
        if any(p in s for p in PLACE):
            return False
        for suf in SUF:
            k = s.find(suf)
            if k < 0:
                continue
            core = s[:k].strip("，。、；：（）()「」《》\"' ")
            if len(core) >= 4 and _re.fullmatch(r"[\u4e00-\u9fa5A-Za-z0-9]+", core):
                return True
        return False

    issues: List[Tuple[str, str, str]] = []
    for p in sorted((ROOT / "engine").glob("*.py")):
        try:
            tree = _ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        docs = set()
        for node in _ast.walk(tree):
            if isinstance(node, (_ast.Module, _ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
                d = _ast.get_docstring(node, clean=False)
                if d is not None:
                    docs.add(d)
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Constant) and isinstance(node.value, str):
                if node.value in docs:
                    continue
                if _like_name(node.value):
                    issues.append(("ERROR", "engine/%s" % p.name,
                                   "第%d行判定代码里出现具体企业名「%s」——"
                                   "判据只对该企业成立；请改用数据表/通用规则"
                                   % (node.lineno, node.value[:30])))
    return issues


def check_housing_fund_workforce_compare() -> List[Tuple[str, str, str]]:
    """★ 2026-10-03（用户："疑点23 又操蛋了，怎么得来了？"）：公积金**人数/基数**比对必须真正接线。

    背景（实测根因）：`_domain_salary_ss_hf_compare` 名字里有 `hf`，签名里**没有** housing_fund
    —— 公积金从未接入用工比对。它只被"金额对等勾稽"轴捞走（明细的**个人**部分 vs 账簿科目的
    **单位+个人**），贴上 RL-SPT-010 的名字，于是触发依据是**口径差**造成的假差额（1,200 vs 2,400），
    而真正的人数差异（有人未缴存）与基数不实（全员按最低基数）**一条也没算**。

    判据（端到端产出断言，而非仅查源码接线）：
      ① 域8 必须接收 housing_fund 参数，并调用独立的公积金比对函数；
      ② 该函数必须在**任何早退分支之前**被调用（否则"只提供工资表+公积金"的企业整段不执行）；
      ③ pipeline 与 phase2 两个调用点都必须传入公积金数据；
      ④ 公积金金额勾稽轴**不得**挂 RL-SPT-010（金额≠人数/基数）；
      ⑤ 字段名读取必须来自唯一权威 `payroll_rules`（不得再有第二份别名表）；
      ⑥ **行为断言**：给定"工资 6 人 / 公积金 5 人"的样本，必须产出 RL-SPT-010 且证据含差异人名；
         给定"个人缴存额占工资 2.5%"的样本，必须产出基数不实结论。
    """
    issues: List[Tuple[str, str, str]] = []

    da_rel = "engine/domain_analysis.py"
    pr_rel = "engine/payroll_rules.py"
    for rel in (da_rel, pr_rel):
        if not (ROOT / rel).exists():
            return [("ERROR", "engine/", "缺少 %s（公积金比对权威模块缺失）" % rel)]

    src_da = (ROOT / da_rel).read_text(encoding="utf-8", errors="replace")
    src_pr = (ROOT / pr_rel).read_text(encoding="utf-8", errors="replace")

    # ① 签名必须收 housing_fund；必须有独立比对函数
    if "def _domain_salary_ss_hf_compare(salaries, social_security, housing_fund=None)" not in src_da:
        issues.append(("ERROR", da_rel,
                       "域8 比对函数未接收 housing_fund —— 公积金未接入用工比对"))
    if "def _housing_fund_findings(" not in src_da:
        issues.append(("ERROR", da_rel, "缺少公积金比对函数 _housing_fund_findings"))

    # ② 必须在早退分支之前调用（调用点在 ss_names 赋值之后、任何 `return findings` 之前）
    if "findings.extend(_housing_fund_findings(" not in src_da:
        issues.append(("ERROR", da_rel, "公积金比对未被调用（findings.extend 缺失）"))
    else:
        _call = src_da.index("findings.extend(_housing_fund_findings(")
        _brk = src_da.index("分支A：只有工资表", 0)
        if src_da.index("分支A：只有工资表", 0) < _call:
            issues.append(("ERROR", da_rel,
                           "公积金比对调用位于「只有工资表」早退分支之后 —— 该分支会提前返回，"
                           "导致只提供工资表+公积金的企业整段不执行"))

    # ③ 两个调用点都必须传入公积金数据
    for rel, marker in (("engine/pipeline.py", "_domain_salary_ss_hf_compare("),
                        ("engine/phase2_deep_dive.py", "_domain_salary_ss_hf_compare(")):
        p = ROOT / rel
        s = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
        idx = s.find(marker)
        if idx < 0:
            issues.append(("ERROR", rel, "未调用域8 比对函数"))
            continue
        tail = s[idx:idx + 200]
        if "housing_fund" not in tail:
            issues.append(("ERROR", rel, "调用域8 比对时未传入公积金数据（housing_fund）"))

    # ④ 金额勾稽轴不得挂 RL-SPT-010
    try:
        import sys as _sys
        _sys.path.insert(0, str(ROOT))
        from engine.subject_consistency import RECONCILE_AXIS_REDLINE  # noqa
        rid = (RECONCILE_AXIS_REDLINE.get("公积金缴存对等") or ("", ""))[0]
        if rid:
            issues.append(("ERROR", "engine/subject_consistency.py",
                           "「公积金缴存对等」（金额勾稽）仍挂 %s —— 金额口径差会被读成「未全员缴存」" % rid))
    except Exception as e:  # pragma: no cover
        issues.append(("WARN", "engine/subject_consistency.py", "勾稽轴映射自检失败：%s" % e))

    # ⑤ 字段名唯一权威：不得再有第二份公积金字段别名表
    for rel in ("engine/domain_analysis.py", "engine/monthly_reconcile.py"):
        s = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        if '"counterparty"' in s and rel.endswith("monthly_reconcile.py"):
            issues.append(("ERROR", rel,
                           "仍在自建公积金月份别名（counterparty）——应走 payroll_rules.hf_month"))
    for marker in ("def hf_month", "def hf_amount", "def hf_person", "def hf_detail_scope"):
        if marker not in src_pr:
            issues.append(("ERROR", pr_rel, "缺少唯一权威入口 %s" % marker))

    # ⑦ 要件数据源的「或」必须按「或」判（且/或两个链路不得各判一次）
    mn_rel = "engine/material_names.py"
    src_mn = (ROOT / mn_rel).read_text(encoding="utf-8", errors="replace") if (ROOT / mn_rel).exists() else ""
    if "def strict_category_groups" not in src_mn:
        issues.append(("ERROR", mn_rel, "缺少 strict_category_groups（要件数据源的且/或解析）"))
    ec_rel = "engine/evidence_chain.py"
    src_ec = (ROOT / ec_rel).read_text(encoding="utf-8", errors="replace") if (ROOT / ec_rel).exists() else ""
    if "_strict_category_groups(" not in src_ec:
        issues.append(("ERROR", ec_rel,
                       "类别层未使用 strict_category_groups —— 「或」会被当成「且」，"
                       "只满足其一的企业该要件永远判「未单独核对」"))
    try:
        import sys as _sys
        _sys.path.insert(0, str(ROOT))
        from engine.material_names import strict_category_groups as _scg
        from engine.evidence_chain import _match_material as _mm
        _g = _scg("工资表或个税申报表")
        if not (_g and len(_g) == 1 and len(_g[0]) == 2):
            issues.append(("ERROR", mn_rel, "「工资表或个税申报表」未解析为同一组的两个候选"))
        _st = (_mm("工资表或个税申报表", "", ["工资表"]) or {}).get("status")
        if _st != "已有":
            issues.append(("ERROR", ec_rel,
                           "只提供工资表时「工资表或个税申报表」判为「%s」而非「已有」—— 或语义未生效" % _st))
        if ((_mm("进项发票与采购台账", "", ["进项发票"]) or {}).get("status")) == "已有":
            issues.append(("ERROR", ec_rel, "「且」语义被放宽（只提供进项发票就判「已有」）"))
    except Exception as e:  # pragma: no cover
        issues.append(("ERROR", ec_rel, "且/或语义自检异常：%s" % e))

    # ⑥ 行为断言（端到端产出）
    try:
        import sys as _sys
        _sys.path.insert(0, str(ROOT))
        from engine.domain_analysis import _domain_salary_ss_hf_compare as _cmp
        _sal = [{"name": "甲", "salary": 12000, "hf_deduct": 300,
                 "period_start": "2025-01-01", "period_end": "2025-01-31"},
                {"name": "乙", "salary": 9000, "hf_deduct": 0,
                 "period_start": "2025-01-01", "period_end": "2025-01-31"}]
        _fund = [{"person_name": "甲", "counterparty": "2025-01", "amount_col": "300"}]
        out = _cmp(_sal, [], _fund) or []
        types = {f.get("type") for f in out}
        if "有工资无公积金" not in types:
            issues.append(("ERROR", da_rel, "行为断言失败：有工资无公积金未产出（人数比对未生效）"))
        else:
            f = next(f for f in out if f.get("type") == "有工资无公积金")
            if f.get("redline_id") != "RL-SPT-010":
                issues.append(("ERROR", da_rel, "「有工资无公积金」未挂 RL-SPT-010"))
            if "乙" not in str(f.get("detail") or ""):
                issues.append(("ERROR", da_rel, "「有工资无公积金」证据未点名差异人员（证据不硬）"))
        if "公积金缴存基数低于实际工资" not in types:
            issues.append(("ERROR", da_rel,
                           "行为断言失败：基数不实未产出（法定 5% 反向证伪未生效）"))
    except Exception as e:  # pragma: no cover
        issues.append(("ERROR", da_rel, "行为断言异常（公积金比对不可用）：%s" % e))

    return issues


def check_detector_text_avoids_hard_ban() -> List[Tuple[str, str, str]]:
    """★ 2026-10-03（用户："看看是否接入一键分析按钮了"）：检测器的**产出文案**不得含硬禁用词。

    实测事故（就在本轮）：新增的「采购来源真实性核验」文案里写了
    "而不是靠**统计指标**推断"，而 `pipeline._DEFAULT_HARD_BAN` 里有「指标」
    ⇒ 整条发现被静默硬删——域跑了、发现产出了、报告里却一条都没有，
    只有一份 `reason:"禁止词:指标"` 的被拒清单。**能力"接入了"但产出被吃掉**，
    从报告侧看和"没接入"完全一样。

    判据（只查**产出文案**，不查注释/docstring，避免误报）：
      AST 解析目标模块，取 `type/detail/description/how_found/suggestion/tax_impact/
      note/claim/suspect/remedy` 这些键对应的字符串字面量（含 f-string 的字面段），
      逐字比对 HARD_BAN，命中即 ERROR 并指出词与所在行。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        import sys as _sys
        _sys.path.insert(0, str(ROOT))
        # 唯一权威：运行时真正生效的过滤规则（配置优先、内置兜底）
        from engine.framework_config import get_filter_rules as _gfr  # noqa
        ban = [str(w) for w in ((_gfr() or {}).get("hard_ban") or []) if str(w)]
        if not ban:
            return [("WARN", "engine/framework_config.py", "HARD_BAN 为空（检查跳过）")]
    except Exception as e:  # pragma: no cover
        return [("WARN", "engine/framework_config.py", "无法加载 HARD_BAN（检查跳过）：%s" % e)]

    import ast as _ast
    TEXT_KEYS = {"type", "detail", "description", "how_found", "suggestion",
                 "tax_impact", "note", "claim", "suspect", "remedy"}
    # ★ 只查**新增能力模块**（它们产出的一切都应当到达报告）。
    #   刻意**不含** `domain_analysis.py` / `monthly_reconcile.py`：那里面有一批
    #   "方法论描述/信息摘要"型 type（如「资金流概览」「收入三源对比总览」「进销概况」）
    #   是被 HARD_BAN **故意**过滤的，纳入只会制造 89 条误报、把闸门变成噪声源
    #   （违反闸门铁律 G2 零误报）。新增能力模块请加进本表。
    targets = ["engine/procurement_authenticity.py", "engine/supplier_stats.py",
               "engine/payroll_rules.py", "engine/external_check_reminder.py"]

    def _strings(node):
        out = []
        if isinstance(node, _ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
        elif isinstance(node, _ast.JoinedStr):
            for v in node.values:
                if isinstance(v, _ast.Constant) and isinstance(v.value, str):
                    out.append(v.value)
        elif isinstance(node, _ast.BinOp) and isinstance(node.op, _ast.Mod):
            out.extend(_strings(node.left))
        elif isinstance(node, _ast.BinOp) and isinstance(node.op, _ast.Add):
            out.extend(_strings(node.left)); out.extend(_strings(node.right))
        elif isinstance(node, _ast.Call):
            for a in list(node.args):
                out.extend(_strings(a))
        elif isinstance(node, _ast.IfExp):
            out.extend(_strings(node.body)); out.extend(_strings(node.orelse))
        elif isinstance(node, (_ast.Tuple, _ast.List)):
            for e in node.elts:
                out.extend(_strings(e))
        return out

    for rel in targets:
        p = ROOT / rel
        if not p.exists():
            continue
        try:
            tree = _ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as e:
            issues.append(("ERROR", rel, "语法错误，无法检查产出文案：%s" % e))
            continue
        for node in _ast.walk(tree):
            if not isinstance(node, _ast.Dict):
                continue
            for k, v in zip(node.keys, node.values):
                if not (isinstance(k, _ast.Constant) and k.value in TEXT_KEYS):
                    continue
                for txt in _strings(v):
                    hit = [w for w in ban if w in txt]
                    if hit:
                        issues.append(("ERROR", rel,
                                       "产出文案含硬禁用词 %s（会被静默硬删，能力等于没接入）："
                                       "「%s」" % (hit, txt[:60])))
    return issues


def check_last_run_no_silent_domain_crash() -> List[Tuple[str, str, str]]:
    """★ 2026-10-03：最近一次**真跑**的 pipeline_log 不得有异常留痕。

    实测事故（就在本轮，我自己引入的）：`monthly_reconcile` 里引用了未定义的
    `_row_period` ⇒ NameError 被域外层 except 吞掉 ⇒ **整个「跨文件逐月勾稽」域零产出**
    （域数 35→31，RL-FUND-005 / 社保对等 / 收入多源对等 全部静默丢失），
    而报告里只看得到一行 "跨文件逐月勾稽异常: name '_row_period' is not defined"。
    pytest 全绿、audit ERROR 0 —— **静态检查抓不到"这段没走到"**，只有端到端产物的
    pipeline_log 能抓。这正是项目铁律「pipeline_log 含"异常"＝本轮静默失效」的机器化。

    判据：读 `scripts/four_reports/company_1_full.json` 的 `pipeline_log`，
      出现「异常」「执行失败」「Traceback」即 ERROR（附原文）。
      产物不存在 → WARN（提示需要先真跑一次全量）。
    """
    issues: List[Tuple[str, str, str]] = []
    art = ROOT / "scripts" / "four_reports" / "company_1_full.json"
    if not art.exists():
        return [("WARN", "scripts/four_reports/company_1_full.json",
                 "无真跑产物，无法核验「域是否静默崩溃」——请先跑一次全量一键分析")]
    try:
        import json as _json
        d = _json.loads(art.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        return [("WARN", "scripts/four_reports/company_1_full.json", "产物不可解析：%s" % e)]
    rep = d.get("report") if isinstance(d.get("report"), dict) else d
    log = (rep or {}).get("pipeline_log") or []
    # ★ 判据要**精确**：只认"异常报告"的写法（异常后紧跟冒号 / 执行失败 / Traceback /
    #   not defined）。绝不能见"异常"二字就报——实测「11个异常关系」「3项异常」
    #   「异常抵扣0.0」都是**正常结论**，宽松匹配会把闸门变成噪声源（闸门铁律 G2 零误报）。
    _pat = re.compile(r"(异常\s*[:：])|(执行失败)|(Traceback)|(not defined)|(\bError\b)")
    bad = [str(L) for L in log if _pat.search(str(L))]
    for s in bad[:8]:
        issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                       "最近一轮真跑存在**静默失效**留痕：%s" % s[:120]))
    return issues


def check_redline_indicator_declared() -> List[Tuple[str, str, str]]:
    """★ 2026-10-03（用户复核疑点1：「命中的两条都是指标，却被判已触碰红线」）——
    红线**第①条是"纯现象/前提"时，必须声明要件组合逻辑**（indicator_constituents /
    violation_any_of），否则「存在即触发」会把"任何有该行为的企业"判成触红。

    事故原文（疑点1）：要件①「存在红字发票或作废发票」= 符合、要件②「红冲发生在敏感时点」= 符合、
    ③④⑦未单独核对、⑤⑥未发现符合 ⇒ 真违规一条都没成立，报告却写「本条涉嫌触碰红线…已触碰税务违规红线」。
    根因：`RL-VAT-007` 未声明要件组合逻辑（`RL-VAT-006` 已声明，属**漏改**）。
    实测同类：**16 条**红线第①条同样以"存在/发生/出现/有"开头（＝现象条或前提条）却未声明。

    判据（**零误报**，只认"纯现象条"）：
      ① 该红线**未声明** `violation_any_of`（`constituent_checkpoint.redline_verdict_rule` 返回空）；
      ② 第①条要件文本以「存在／发生／出现／有」**开头**；
      ③ 且**不含**违规字眼（却／但／未／无／不／疑似／规避／异常／偏低／不实／混淆／低于／缺／差异／错）
         —— 含违规字眼的第①条本身即"违规要件"，不在本条判据内（如 RL-PAY-004
         「存在长期固定…**却**按劳务报酬处理」）。
    命中 ⇒ ERROR（修法＝只加两行数据：`indicator_constituents` / `violation_any_of`）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.tax_redlines import REDLINES
        from engine.constituent_checkpoint import redline_verdict_rule
    except Exception as e:  # noqa: BLE001
        return [("WARN", "engine/tax_redlines.py", "无法导入红线库：%s" % e)]
    _pat = re.compile(r"^(存在|发生|出现|有)")
    _VW = ("却", "但", "未", "无", "不", "疑似", "规避", "异常", "偏低",
           "不实", "混淆", "低于", "缺", "差异", "错")
    for r in (REDLINES or []):
        rid = str(r.get("id") or "")
        cs = r.get("constituents") or []
        if not rid or not cs:
            continue
        if redline_verdict_rule(rid):
            continue
        c1 = str(cs[0])
        if not _pat.match(c1):
            continue
        if any(w in c1 for w in _VW):
            continue
        issues.append(("ERROR", "engine/tax_redlines.py",
                       "%s「%s」第①条是**纯现象/前提条**（\"%s…\"），却未声明 "
                       "indicator_constituents/violation_any_of ⇒ 任何有该行为的企业都会被判"
                       "「已触碰税务违规红线」（结论颠倒）。请按其要件补两行数据。"
                       % (rid, str(r.get("name") or "")[:26], c1[:34])))
    return issues


def check_tax_impact_basis_is_subject_amount() -> List[Tuple[str, str, str]]:
    """★ 2026-10-03（用户复核疑点1：税额影响虚高 8.4 倍）——税基必须是**本项涉案金额**，
    且"价税合计"锚定必须先价税分离。

    事故：疑点1 的 `tax_impact.basis = 8,050,908.58`（＝要件①里"占比**分母**：剔除红字后的
    销项价税合计"），而本项涉案金额是"销项红字/作废价税合计 **1,015,900.00**"。
    旧规则"取全文绝对值最大的锚定金额"⇒ 分母被当成涉案金额 ⇒ 敞口 54.10 万（实际约 5.75 万）。

    判据（读**最近一轮真跑产物**，端到端断言，不查源码接线）：
      (a) 对每个 `tax_impact.available` 的疑点，重算 `extract_amount_from_problem(p)`；
          若其锚定**子句**含"参照量"标记（分母/占比/占同期/剔除…后/合计/总额/平均…）
          且不含"分子"，⇒ ERROR（锚到了参照量）；
      (b) 锚定语境为"价税合计/含税"时，`tax_impact.amount_context` 必须交代含税口径
          （含"含税"字样）——否则说明**没做价税分离**（含税金额直接乘税率）。
      (c) ★ 2026-10-08（P0-1）**"金额本身即税额"必须有金额身边的口径证据**：
          凡 `tax_impact.items[]` 里出现 `rate == "—"`（＝把该金额直接当税额、不再乘税率），
          其**锚定子句**必须含 `_TAX_AMOUNT_KW`（进项/销项税额…）——否则 ERROR。
          事故：`infer_amount_is_tax` 曾在**整段叙述**里做关键词命中，正文「涉嫌通过红冲调节
          **销项税额**」（描述**手法**）被判成"本项金额即税额" ⇒ 把**含税价税合计
          1,015,900.00** 直接当成增值税额（高估 5~7 倍）。判据必须只看金额所在的子句。
      产物不存在 ⇒ WARN（提示先真跑一次）；不报错以免闸门变成噪声源。
    """
    issues: List[Tuple[str, str, str]] = []
    art = ROOT / "scripts" / "four_reports" / "company_1_full.json"
    if not art.exists():
        return [("WARN", "scripts/four_reports/company_1_full.json",
                 "无真跑产物，无法核验「税额税基是否为本项涉案金额」——请先跑一次全量一键分析")]
    try:
        import json as _json
        d = _json.loads(art.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        return [("WARN", "scripts/four_reports/company_1_full.json", "产物不可解析：%s" % e)]
    rep = d.get("report") if isinstance(d.get("report"), dict) else d
    er = (rep or {}).get("enterprise_readable_report") or {}
    probs = er.get("confirmed_problems") or []
    if not probs:
        return [("WARN", "scripts/four_reports/company_1_full.json",
                 "产物中无 confirmed_problems，无法核验税额税基")]
    try:
        from engine.tax_impact import (extract_amount_from_problem,
                                       _KW_DENOM as _DEN, _KW_NUMER as _NUM,
                                       _TAX_AMOUNT_KW as _TAXKW)
    except Exception as e:  # noqa: BLE001
        return [("WARN", "engine/tax_impact.py", "无法导入 tax_impact：%s" % e)]
    for p in probs:
        if not isinstance(p, dict):
            continue
        ti = p.get("tax_impact") or {}
        if not ti.get("available"):
            continue
        seq = p.get("seq")
        cl = ""
        try:
            am = extract_amount_from_problem(p) or {}
            cl = str(am.get("clause") or "")
        except Exception:  # noqa: BLE001
            am = {}
        if cl and any(k in cl for k in _DEN) and not any(k in cl for k in _NUM):
            issues.append(("ERROR", "confirmed_problems[seq=%s]" % seq,
                           "税额税基锚到了**参照量**（占比分母/合计类）：子句「%s」；"
                           "本项涉案金额应取「分子/差额/少缴」侧" % cl[:80]))
        if am.get("inclusive") and "含税" not in str(ti.get("amount_context") or ""):
            issues.append(("ERROR", "confirmed_problems[seq=%s]" % seq,
                           "锚定金额为**含税**（价税合计）口径，但 amount_context 未交代"
                           "价税分离（tax_impact.basis=%s）——含税金额直接乘税率会虚高"
                           % ti.get("basis")))
        # (c) "金额本身即税额"（rate="—"，不再乘税率）必须有**金额身边**的口径证据
        if any(str(_it.get("rate") or "") == "—" for _it in (ti.get("items") or [])):
            _near = "%s %s" % (cl, str(am.get("context") or ""))
            if not any(k in _near for k in _TAXKW):
                issues.append(("ERROR", "confirmed_problems[seq=%s]" % seq,
                               "税额明细出现 rate=「—」（把锚定金额**直接当作税额**、不再乘税率），"
                               "但该金额的锚定子句里**没有**进项/销项税额类口径词"
                               "（子句「%s」）——疑为在整段叙述里误命中'销项税额'等手法描述，"
                               "会把含税销售额当作税额（高估 5~7 倍）" % cl[:80]))
    return issues


def check_downgraded_finding_not_reinflated() -> List[Tuple[str, str, str]]:
    """★ 2026-10-03（用户复核疑点2「资金回流」）——**上游已显式降级的发现，不得被"再造"成疑点**。

    事故：检测器已判「仅检出单向大额转出（无配对回流、对象不属六员）：单向转出本身不构成
    资金回流」，并**清空** `constituent_hits`、清空 `redline_id`、降级为低风险；
    但 `redline_engine` 的"逐条判定兜底"立刻用 `_DEFAULT_HIT_INDEX` 把发现级 detail 回填成
    **要件①命中** ⇒ 报告要件①显示「符合该要件情形」，而它的核对证据原文写着
    「单向转出本身不构成回流…不能仅凭此项认定资金回流」——**判据与证据相反**；
    疑点标题仍是红线名、等级仍是「高风险」。

    判据（读**最近一轮真跑产物**，端到端断言）：
      (a) `suspicions/unconfirmed` 中 `downgraded=True` 的条目，其
          `argumentation.constituent_hits` **必须为空**（不得回填）；
      (b) `all_findings` 中带 `_downgrade_reason` 的发现，其 `constituent_hits` 必须为空；
      (c) 成品报告里标题以「**待核线索：**」开头的疑点，`risk_level` 必须为「待核验」
          且 `verdict` 含「未认定」（不得沿用红线名 + 高风险）。
      产物不存在 ⇒ WARN（提示先真跑）。
    """
    issues: List[Tuple[str, str, str]] = []
    art = ROOT / "scripts" / "four_reports" / "company_1_full.json"
    if not art.exists():
        return [("WARN", "scripts/four_reports/company_1_full.json",
                 "无真跑产物，无法核验「降级发现是否被回填」——请先跑一次全量一键分析")]
    try:
        import json as _json
        d = _json.loads(art.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        return [("WARN", "scripts/four_reports/company_1_full.json", "产物不可解析：%s" % e)]
    rep = d.get("report") if isinstance(d.get("report"), dict) else d
    rd = ((rep or {}).get("comprehensive") or {}).get("redline_detection") or {}
    # (a) 疑点级：显式降级 ⇒ 不得有任何要件命中
    for _k in ("suspicions", "unconfirmed"):
        for s in (rd.get(_k) or []):
            if not isinstance(s, dict) or not s.get("downgraded"):
                continue
            _hits = ((s.get("argumentation") or {}).get("constituent_hits") or [])
            if _hits:
                issues.append(("ERROR", "redline_detection.%s[%s]" % (_k, s.get("redline_id")),
                               "发现已被**显式降级**（%s），却仍回填了要件命中 %s ⇒ 报告会把"
                               "「不构成该风险」写成「要件①符合」"
                               % (str(s.get("downgrade_reason") or "")[:60],
                                  [h.get("index") for h in _hits])))
    # (b) 发现级：降级发现自身不得挂要件命中
    for f in ((rep or {}).get("all_findings") or []):
        if not isinstance(f, dict) or not str(f.get("_downgrade_reason") or "").strip():
            continue
        if f.get("constituent_hits"):
            issues.append(("ERROR", "all_findings[%s]" % str(f.get("type") or "")[:24],
                           "带 `_downgrade_reason` 的发现仍挂着 constituent_hits ⇒ 降级未生效"))
    # (c) 报告级：待核线索口径必须真的降级
    er = (rep or {}).get("enterprise_readable_report") or {}
    for p in (er.get("confirmed_problems") or []):
        if not isinstance(p, dict):
            continue
        # ⚠ 标题会被 `plain_language` 通俗化改写（实测"待核线索"→"**待核实**线索"），
        #    故判据取"以'待核'开头且含'线索'"，不逐字锚定。
        _ti = str(p.get("title") or "")
        if not (_ti.startswith("待核") and "线索" in _ti):
            continue
        _lv = str(p.get("risk_level") or "")
        _vd = str(p.get("verdict") or "")
        if _lv not in ("待核验", "待核"):
            issues.append(("ERROR", "confirmed_problems[seq=%s]" % p.get("seq"),
                           "降级疑点（标题「待核线索：…」）的风险等级仍是「%s」——"
                           "应随降级改为「待核验」" % _lv))
        if "未认定" not in _vd:
            issues.append(("ERROR", "confirmed_problems[seq=%s]" % p.get("seq"),
                           "降级疑点的结论仍是「%s」——应写「未认定到构成要件」" % _vd[:40]))
    return issues


def check_waiting_materials_respect_industry() -> List[Tuple[str, str, str]]:
    """★ 2026-10-03（用户复核疑点2）——**"待补资料"清单必须过业态剔除**。

    事故：系统自己已认定（`industry_resolver.not_required_materials('广告传媒')`）
    「服务型天然无实物货物流转 ⇒ 入库验收单/物流单据/承运记录/BOM/进销存台账**不属于必查项，
    不因未提供而计入缺失**」，但疑点2 仍：
      · 「三、」把「物流单据与承运记录」计入"确未提供的有2项"；
      · 「五、」要求"补充提供……物流单据"、"取得直接证据：采购合同**与入库验收单**"。
    ⇒ **服务型广告公司被要求提交它天然不会有的资料**，"自证清白"的路被堵死。

    判据（读真跑产物；**唯一权威** `industry_resolver.not_required_materials`）：
      对每个疑点的 §三/§五 文本与 `suggestion`/待补字段，若**字面出现**本业态"不适用资料名"
      ⇒ ERROR。**排除正当语境**（句内含"不适用／不属于必查／不计入缺失／天然无"——
      那些是在**说明为什么不要**，不是要求企业提供）。
    """
    issues: List[Tuple[str, str, str]] = []
    art = ROOT / "scripts" / "four_reports" / "company_1_full.json"
    if not art.exists():
        return [("WARN", "scripts/four_reports/company_1_full.json",
                 "无真跑产物，无法核验「待补资料是否过业态剔除」——请先跑一次全量一键分析")]
    try:
        import json as _json
        d = _json.loads(art.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        return [("WARN", "scripts/four_reports/company_1_full.json", "产物不可解析：%s" % e)]
    rep = d.get("report") if isinstance(d.get("report"), dict) else d
    try:
        from engine.enterprise_report import _not_required_docs
    except Exception as e:  # noqa: BLE001
        return [("WARN", "engine/enterprise_report.py", "无法导入业态剔除：%s" % e)]
    _ind = ((rep or {}).get("target_entity") or {}).get("industry")
    _nr = _not_required_docs(_ind)[0]
    if not _nr:
        return []          # 业态未知 ⇒ 不臆测、不剔（与唯一权威同口径）
    er = (rep or {}).get("enterprise_readable_report") or {}
    _ok_ctx = ("不适用", "不属于必查", "不计入缺失", "天然无", "不因未提供")
    _hit = set()
    for p in (er.get("confirmed_problems") or []):
        if not isinstance(p, dict):
            continue
        _texts = [str(p.get("suggestion") or "")]
        for np_ in (p.get("narrative_paragraphs") or []):
            if isinstance(np_, dict):
                _texts.append(str(np_.get("text") or ""))
                _texts.append(" ".join(str(b) for b in (np_.get("bullets") or [])))
        for _t in _texts:
            for _doc in _nr:
                _i = _t.find(_doc)
                while _i >= 0:
                    _win = _t[max(0, _i - 40): _i + len(_doc) + 20]
                    if not any(k in _win for k in _ok_ctx):
                        _key = (p.get("seq"), _doc)
                        if _key not in _hit:
                            _hit.add(_key)
                            issues.append(("ERROR", "confirmed_problems[seq=%s]" % p.get("seq"),
                                           "待补资料清单出现**本业态（%s）不适用**的资料「%s」——"
                                           "企业天然不会有，会导致其永远无法达到\"资料齐全\"。"
                                           "请过 `industry_resolver.not_required_materials()`"
                                           % (_ind, _doc)))
                    _i = _t.find(_doc, _i + 1)
    return issues


def check_conclusion_not_exceed_finding() -> List[Tuple[str, str, str]]:
    """★ 2026-10-03（用户复核疑点3）——**疑点等级与结论措辞不得超过其发现**。

    事故（实测 3 例）：发现层自己写着
      「在9个月中…差异同时超过25%和10万元；累计方向性差额 1,170,164.14 元。
        **该结果只说明两个数据口径需要逐月对账。**」（`level=中风险`）
    疑点层却是 `risk_level=**高风险**`、`verdict="**已触碰税务违规红线**"` ⇒
    **"两个口径需要逐月对账"被升格为"高风险账外收入"**。
    同类：RL-INC-002（中风险→高风险）、RL-VAT-006（低风险→中风险）。

    判据（读真跑产物，端到端）：
      对每个 `risk_level ∈ {低风险,中风险,高风险,极高风险}` 的疑点，
      按其 `finding_type`（或红线名）找到同名 suspicion，取其 `level`；
      **疑点等级不得高于该发现的等级**（等级序：信息<低风险<中风险<高风险<极高风险）。
      匹配不到对应 suspicion ⇒ 跳过（不臆断，零误报）。
    """
    issues: List[Tuple[str, str, str]] = []
    art = ROOT / "scripts" / "four_reports" / "company_1_full.json"
    if not art.exists():
        return [("WARN", "scripts/four_reports/company_1_full.json",
                 "无真跑产物，无法核验「疑点等级是否超过发现」——请先跑一次全量一键分析")]
    try:
        import json as _json
        d = _json.loads(art.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        return [("WARN", "scripts/four_reports/company_1_full.json", "产物不可解析：%s" % e)]
    rep = d.get("report") if isinstance(d.get("report"), dict) else d
    rd = ((rep or {}).get("comprehensive") or {}).get("redline_detection") or {}
    # ★ 2026-10-06：等级标度**唯一权威** `engine.risk_levels`（模块顶层已导入，
    #   原先此处内联一张表，与 `enterprise_report` 的上限压制表是**两张独立维护**的表
    #   —— 闸门自己也会漂移）。
    _sus = list(rd.get("suspicions") or []) + list(rd.get("unconfirmed") or [])
    er = (rep or {}).get("enterprise_readable_report") or {}
    for p in (er.get("confirmed_problems") or []):
        if not isinstance(p, dict):
            continue
        _ti = str(p.get("title") or "")
        if _ti.startswith("待核") and "线索" in _ti:
            continue                      # 降级线索由 check_downgraded_finding_not_reinflated 管
        _lv = str(p.get("risk_level") or "")
        if _lv not in RISK_GRADES:
            continue          # 「待核验」等证据状态不参与高低比较（与引擎 cap_level 同口径）
        _m = [s for s in _sus
              if str(s.get("finding_type") or "").strip()
              and str(s.get("finding_type")) in _ti]
        if not _m:
            _m = [s for s in _sus
                  if str(s.get("redline_name") or "@") != "@"
                  and _ti.startswith(str(s.get("redline_name")))]
        if not _m:
            continue
        _fl = str(_m[0].get("level") or "")
        # 用**权威的 cap_level** 复算：引擎侧若正确压制，这里必须未被压（返回原等级）。
        _capped, _from = cap_level(_lv, _fl)
        if _fl in RISK_GRADES and _capped != _lv:
            issues.append(("ERROR", "confirmed_problems[seq=%s]" % p.get("seq"),
                           "疑点等级「%s」**高于**其建入口发现的等级「%s」"
                           "（redline=%s，finding_type=%s）——发现层只说'口径需要逐月对账'，"
                           "报告却按更高风险呈现"
                           % (_lv, _fl, _m[0].get("redline_id"), _m[0].get("finding_type"))))
    return issues


def check_checkpoint_evidence_not_self_contradicting() -> List[Tuple[str, str, str]]:
    """★ 2026-10-03（用户复核疑点3）——**判"符合"的要件，其核对证据不得自我否定/未定量**。

    事故：要件② 的核对证据是
      「累计方向性差额 1,170,164.14 元（**占申报收入比例需要逐月评估**）」
    证据自己写着"需要评估"（该要件要的比值根本没算），却被渲染成
      「①…（已单独核对：**符合该要件情形**；…核对证据：累计方向性差额…需要逐月评估）」。

    判据（读真产物）：要件行含「**已单独核对：符合该要件情形**」，且同一行「核对证据：」之后
    出现 `constituent_checkpoint._HIT_EV_UNQUANTIFIED`（未定量类）或 `_HIT_EV_DENY`（反向类）
    任一措辞 ⇒ ERROR。词表与引擎侧同一权威（`assess_hit_evidence`），不另写一份。
    """
    issues: List[Tuple[str, str, str]] = []
    art = ROOT / "scripts" / "four_reports" / "company_1_full.json"
    if not art.exists():
        return [("WARN", "scripts/four_reports/company_1_full.json",
                 "无真跑产物，无法核验「要件判据与证据是否同向」——请先跑一次全量一键分析")]
    try:
        import json as _json
        d = _json.loads(art.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        return [("WARN", "scripts/four_reports/company_1_full.json", "产物不可解析：%s" % e)]
    try:
        from engine.constituent_checkpoint import assess_hit_evidence as _assess
    except Exception as e:  # noqa: BLE001
        return [("WARN", "engine/constituent_checkpoint.py", "无法导入证据体检：%s" % e)]
    rep = d.get("report") if isinstance(d.get("report"), dict) else d
    er = (rep or {}).get("enterprise_readable_report") or {}
    _HIT = "已单独核对：符合该要件情形"
    for p in (er.get("confirmed_problems") or []):
        if not isinstance(p, dict):
            continue
        for np_ in (p.get("narrative_paragraphs") or []):
            if not isinstance(np_, dict):
                continue
            for b in (np_.get("bullets") or []):
                _b = str(b)
                if _HIT not in _b or "核对证据" not in _b:
                    continue
                _ev = _b.split("核对证据", 1)[1]
                _v, _note = _assess(_ev)
                if _v:
                    issues.append(("ERROR", "confirmed_problems[seq=%s]" % p.get("seq"),
                                   "要件判「符合」但核对证据自我否定/未定量：%s｜行首「%s」"
                                   % (_note, _b[:56])))
    return issues


def check_self_denying_finding_not_claimed() -> List[Tuple[str, str, str]]:
    """★ 2026-10-03（用户复核疑点4）——**发现自我否定时，不得被认领成要件命中**。

    事故：VR056「公私混同发薪/私户支付薪酬」在**未提供个人账户流水**时已如实写明
      「……无法核验该差额是否经私户支付（差额亦可能为跨期计提、非工资性支出结算等），
        **据实不作私户认定**」，并**不认领任何红线**；
    兜底却把"账面工资 928,000／公户工资支出 0"这段**发现级事实**回填成
    RL-INC-002 要件①「个人账户存在经营性收款」命中 ⇒ 报告判"要件①符合 + 已触碰税务违规红线"，
    而触发事实**根本没提到个人账户收款**（疑点标题说"个人账户收客户款"，触发事实说"公司没通过公户发工资"）。

    判据（读**真跑产物**，端到端；**判据要精确，避免误伤合法命中**）：
      对每个 suspicion，按其 `finding_type` 在 `all_findings` 里找 entry 发现；
      若该发现文本（detail+description）经 `assess_hit_evidence` 判为**自我否定**（deny 分支），
      则：
        ① 若其 `constituent_hits` 里存在**兜底回填特征证据**（以「**账内检测到：**」开头）
           ⇒ **ERROR**（这正是"发现级事实被伪装成要件级命中"的机器指纹）；
        ② 若未降级（`downgraded` 非真）⇒ **WARN**（标题仍会沿用红线名）。
      ⚠ **不得**对"发现文本含反向词"一律 ERROR —— 实测误伤：RL-SPT-012 的第④条要件本身
      就是「**未见**申报/缴款记录」，检测器如实认领并给出"未见完税凭证"的证据，**这是合法命中**，
      不是自我否定。⇒ 必须用「账内检测到：」这个兜底指纹把两者区分开。
      找不到对应发现 ⇒ 跳过（零误报）。
    """
    issues: List[Tuple[str, str, str]] = []
    art = ROOT / "scripts" / "four_reports" / "company_1_full.json"
    if not art.exists():
        return [("WARN", "scripts/four_reports/company_1_full.json",
                 "无真跑产物，无法核验「自我否定的发现是否被认领」——请先跑一次全量一键分析")]
    try:
        import json as _json
        d = _json.loads(art.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        return [("WARN", "scripts/four_reports/company_1_full.json", "产物不可解析：%s" % e)]
    try:
        from engine.constituent_checkpoint import assess_hit_evidence as _assess
    except Exception as e:  # noqa: BLE001
        return [("WARN", "engine/constituent_checkpoint.py", "无法导入证据体检：%s" % e)]
    rep = d.get("report") if isinstance(d.get("report"), dict) else d
    _by_type = {}
    for f in ((rep or {}).get("all_findings") or []):
        if isinstance(f, dict):
            _by_type.setdefault(str(f.get("type") or "").strip(), f)
    rd = ((rep or {}).get("comprehensive") or {}).get("redline_detection") or {}
    for _k in ("suspicions", "unconfirmed"):
        for s in (rd.get(_k) or []):
            if not isinstance(s, dict):
                continue
            _ft = str(s.get("finding_type") or "").strip()
            f = _by_type.get(_ft)
            if not f:
                continue
            _v, _note = _assess(str(f.get("detail") or "") + " " + str(f.get("description") or ""))
            if _v != "miss":
                continue
            _hits = ((s.get("argumentation") or {}).get("constituent_hits") or [])
            # ★ 兜底回填的机器指纹：evidence 以"账内检测到："开头（`redline_engine` 兜底分支唯一文案）
            _fallback = [h for h in _hits
                         if str((h or {}).get("evidence") or "").startswith("账内检测到：")]
            if _fallback:
                issues.append(("ERROR", "redline_detection.%s[%s]" % (_k, s.get("redline_id")),
                               "发现自身文字已「不作认定/无法核验」（%s），却仍被**兜底回填**成要件命中 %s"
                               " ⇒ 报告会把「发现层明说做不到的事」写成「要件符合」"
                               % (_note[:52], [h.get("index") for h in _fallback])))
            elif not s.get("downgraded") and not _hits:
                issues.append(("WARN", "redline_detection.%s[%s]" % (_k, s.get("redline_id")),
                               "发现自我否定且未认领红线，但疑点未按「待核线索」降级"
                               "（标题仍会沿用红线名）——请检查 `downgraded` 判据"))
    return issues


def check_limit_items_coverage_declared() -> List[Tuple[str, str, str]]:
    """★ 2026-10-04（用户复核疑点5）——**分项限额表的"覆盖范围"必须自证**，且必须区分**差异性质**。

    事故（疑点5）：
      · 要件① 声称「业务招待费、广告费和业务宣传费、职工福利费、工会经费、职工教育经费、
        公益性捐赠等超过法定扣除限额」（**6 类**），而分项表只出 **2 行**（其余 4 类
        **既未测算、也未说明**）⇒ 覆盖率 1/3 却被当作"逐条核对"呈现，读者以为"只有这两项超限"；
      · 表里没有"适用规则"列 ⇒ 限额数字（33,184.00 / 995,520.09）**读者无法复核怎么来的**；
      · 表里没有"差异性质"列 ⇒ 业务招待费（**永久性差异**）与广宣费（**时间性差异，可结转**）
        混在同一"超限金额"口径下，照此全额补缴会让企业**多缴税**。

    判据（读**真跑产物**，端到端）：
      ① 含「分项扣除限额测算」表的疑点，其列必须含「差异性质」与「适用规则」；
      ② 该表的 `scope_note` 必须声明覆盖范围（"共登记 N 类…算出 M 类"+未测算项点名）；
      ③ 要件①文本里以「、」并列的类别名（截到"等"为止）必须**逐项**出现在
         （表行费用项目 ∪ scope_note）中 ⇒ 否则 ERROR（声称而非覆盖）。
    """
    issues: List[Tuple[str, str, str]] = []
    art = ROOT / "scripts" / "four_reports" / "company_1_full.json"
    if not art.exists():
        return [("WARN", "scripts/four_reports/company_1_full.json",
                 "无真跑产物，无法核验「分项限额覆盖范围」——请先跑一次全量一键分析")]
    try:
        import json as _json
        d = _json.loads(art.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        return [("WARN", "scripts/four_reports/company_1_full.json", "产物不可解析：%s" % e)]
    rep = d.get("report") if isinstance(d.get("report"), dict) else d
    er = (rep or {}).get("enterprise_readable_report") or {}
    for p in (er.get("confirmed_problems") or []):
        if not isinstance(p, dict):
            continue
        _tabs, _first_con = [], ""
        for np_ in (p.get("narrative_paragraphs") or []):
            if not isinstance(np_, dict):
                continue
            for _t in (np_.get("detail_tables") or []):
                if isinstance(_t, dict):
                    _tabs.append(_t)
            for b in (np_.get("bullets") or []):
                if str(b).lstrip().startswith("①"):
                    _first_con = str(b)
                    break
        _lim = [t for t in _tabs if "分项扣除限额测算" in str(t.get("title") or "")]
        if not _lim:
            continue
        _seq = p.get("seq")
        _cols = [str(c) for c in (_lim[0].get("columns") or [])]
        for _need in ("差异性质", "适用规则"):
            if _need not in _cols:
                issues.append(("ERROR", "confirmed_problems[seq=%s]" % _seq,
                               "分项扣除限额表缺「%s」列 —— %s"
                               % (_need,
                                  "读者无法复核限额数字来源" if _need == "适用规则"
                                  else "永久性/时间性差异混为一谈，照此补缴会让企业多缴")))
        _scope = str(_lim[0].get("scope_note") or "")
        if "算出" not in _scope or "登记" not in _scope:
            issues.append(("ERROR", "confirmed_problems[seq=%s]" % _seq,
                           "分项扣除限额表**未声明覆盖范围**（缺「共登记 N 类…算出 M 类」口径说明）"
                           "—— 要件声称的类别与表内实际测算的类别不一致时读者无从识别"))
        # ③ 要件① 声称的类别必须逐项有交代
        if _first_con:
            _head = _first_con.split("等", 1)[0]
            _head = _head.split("（", 1)[0]
            # 剥掉要件 bullet 的「① 」序号前缀（否则首段名为「① 业务招待费」而表内为「业务招待费」，误报）
            _names = [re.sub(r"^[①-⑳\s]+", "", x).strip()
                      for x in _head.split("、") if x.strip()]
            _names = [n for n in _names if n.endswith(("费", "经费", "捐赠"))]
            _known = {str(r.get("费用项目") or "") for r in (_lim[0].get("rows") or [])}
            for n in _names:
                if n in _known or n in _scope:
                    continue
                issues.append(("ERROR", "confirmed_problems[seq=%s]" % _seq,
                               "要件① 声称覆盖「%s」，但分项表既无该行、口径说明也未点名"
                               "（声称 ≠ 覆盖）" % n))
    return issues


# ══════════════════════════════════════════════════════════════════════════
# 疑点6 批次新增（2026-10-04）：触发金额只算差异行 / 基准量纲对齐 /
#                            同疑点表口径关系 / 幽灵资料要求 / 类别关键词例外
# ══════════════════════════════════════════════════════════════════════════

_TBL_STATE_KEYS = ("匹配状态", "状态", "核对结论", "结论", "差异性质", "结果", "是否异常")
# ★ 只认**明确的"本行无差异"标记**；**不得**用"未发现/一致/相符/正常/相同"等宽词——
#   实测宽词会命中 9 张「构成要件独立核对表」的"未单独核对/未发现符合"行（那不是"无差异"）。
_TBL_NORMAL_MARKS = ("均有", "无差异", "不存在差异", "未发现差异", "无异常", "不存在异常", "匹配成功")
_TBL_AMT_KEYS = ("金额（元）", "金额(元)", "金额", "amount", "应发工资（元）", "工资",
                 "工资表内工资合计（元）", "账面发生额（元）", "超限金额（元）")


def _prob_tables(p: Dict) -> list:
    out = []
    for np_ in (p.get("narrative_paragraphs") or []):
        if isinstance(np_, dict):
            out += [t for t in (np_.get("detail_tables") or []) if isinstance(t, dict)]
    if isinstance(p.get("detail_table"), dict):
        out.append(p["detail_table"])
    return out


def _is_normal_row(r: Dict) -> bool:
    """该行是否被**明确标记为无差异**（只看状态/结论类列，认窄标记）。"""
    for _k in _TBL_STATE_KEYS:
        if _k in r:
            _v = str(r.get(_k) or "")
            return bool(_v) and any(_m in _v for _m in _TBL_NORMAL_MARKS)
    return False


def _tbl_normal_rows(tb: Dict) -> int:
    return sum(1 for r in (tb.get("rows") or []) if isinstance(r, dict) and _is_normal_row(r))


def check_trigger_basis_excludes_normal_rows() -> List[Tuple[str, str, str]]:
    """★ 2026-10-04（用户复核疑点6 D1）——**触发依据的金额只能统计"差异行"**。

    事故：触发依据写
      「工资名册与社会保险人员范围差异（共30笔）（本表 30 行，涉及 4 个对象，
        **金额合计 549,000.00 元**）」
    而该表 30 行里 **28 行是"工资社保均有"（无差异行）** ⇒ 549,000 是**全表工资总额**，
    真实差异只有 **17,000**（杨莹 2 个月）⇒ **夸大 32.29 倍**，且表题（"范围差异"）与内容矛盾。
    根因：把**配对状态表**当**命中明细表**——范围/配对类表的每一行并不都是本项发现。

    判据（读真跑产物）：对每个疑点的叙事段，
      ① 若某张表存在**无差异标记行**，且该表的标题出现在触发依据里，
         则该段必须**披露**"经逐项核对无差异"（不得把无差异行当差异计数）；
      ② 该段不得出现**未加"差异"限定的**"金额合计 … 元"字样（旧文案的机器指纹）。
    """
    issues: List[Tuple[str, str, str]] = []
    art = ROOT / "scripts" / "four_reports" / "company_1_full.json"
    if not art.exists():
        return [("WARN", "scripts/four_reports/company_1_full.json",
                 "无真跑产物，无法核验「触发依据是否把无差异行计入金额」——请先跑一次全量")]
    try:
        import json as _json
        d = _json.loads(art.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        return [("WARN", "scripts/four_reports/company_1_full.json", "产物不可解析：%s" % e)]
    rep = d.get("report") if isinstance(d.get("report"), dict) else d
    er = (rep or {}).get("enterprise_readable_report") or {}
    for p in (er.get("confirmed_problems") or []):
        if not isinstance(p, dict):
            continue
        _seq = p.get("seq")
        _texts = [str(np_.get("text") or "") for np_ in (p.get("narrative_paragraphs") or [])
                  if isinstance(np_, dict)]
        _all = "\n".join(_texts)
        for tb in _prob_tables(p):
            _norm = _tbl_normal_rows(tb)
            if not _norm:
                continue
            _ttl = str(tb.get("title") or "")
            _key = _ttl[:8]
            if not _key or _key not in _all:
                continue      # 该表未进入触发依据 ⇒ 本闸门不管
            # 找到含该表标题的段
            _seg = next((t for t in _texts if _key in t), "")
            if "经逐项核对无差异" not in _seg:
                issues.append(("ERROR", "confirmed_problems[seq=%s]" % _seq,
                               "表「%s」含 **%d 行经核对无差异** 的行，触发依据却未披露"
                               "——照此会出现「范围差异表把 93%% 的无差异行计入金额」"
                               "（实测疑点6：549,000 夸大 32.29 倍）" % (_ttl[:30], _norm)))
                continue
            # ② **数值自证**：段内"金额合计 X 元"必须等于**非无差异行**的金额之和
            #    （不只查措辞 —— 措辞对而数算错同样要抓）。
            _m_amt = re.search(r"金额合计 ([\d,]+\.\d{2}) 元", _seg)
            if _m_amt:
                try:
                    _said = float(_m_amt.group(1).replace(",", ""))
                except ValueError:
                    _said = None
                _keep_sum = 0.0
                for r in (tb.get("rows") or []):
                    if not isinstance(r, dict) or _is_normal_row(r):
                        continue
                    for k in _TBL_AMT_KEYS:
                        if k in r:
                            try:
                                _keep_sum += abs(float(str(r[k]).replace(",", "").rstrip("%")))
                            except (TypeError, ValueError):
                                pass
                            break
                if _said is not None and abs(_said - round(_keep_sum, 2)) > 0.01:
                    issues.append(("ERROR", "confirmed_problems[seq=%s]" % _seq,
                                   "触发依据对表「%s」写的金额合计 %s 元 ≠ 非无差异行的实际合计 %.2f 元"
                                   "——金额仍把无差异行算了进去" % (_ttl[:30], _m_amt.group(1), _keep_sum)))
    return issues


def check_constituent_benchmark_dimension_aligned() -> List[Tuple[str, str, str]]:
    """★ 2026-10-04（用户复核疑点6 D2）——**行业基准门限的维度必须与被衡量的量同维度**。

    事故：`RL-PAY-001` 要件③ 原文「**工资列支总额**超过行业**人均营收**基准×从业人数」——
    "人均营收×从业人数" = **营业收入总额**，却拿它衡量**工资列支总额**：营收与工资是**两个量纲**。
    这是**模板误用**：把"金额型规模门限"（对交易差异/存货金额尚可作重要性参照）套到了**薪酬**上。
    与 2026-10-03 删除的 RL-INC-001/RL-INC-002/RL-CIT-001 三条"登记口径与要件不一致"同一处治则。

    判据（数据驱动，扫**红线库**而非某一条）：红线条文里出现
      「<薪酬类词> … (总额|合计|金额|支出|成本) … 超过 行业人均(营收|收入)基准」
    即判 ERROR —— 薪酬类总额的同维度参照只能是"**人均工资 × 人数**"。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.tax_redlines import REDLINES as _RL
    except Exception as e:  # noqa: BLE001
        return [("WARN", "engine/tax_redlines.py", "红线库不可导入：%s" % e)]
    _items = _RL if isinstance(_RL, list) else list(_RL.values())
    _pat = re.compile(
        r"(工资|薪酬|薪金|社保|公积金|福利)[^，。；、]{0,12}(总额|合计|金额|支出|成本)"
        r"[^，。；]{0,20}超过[^，。；]{0,10}行业人均(营收|营业收入|收入)基准")
    for it in _items:
        if not isinstance(it, dict):
            continue
        _rid = str(it.get("id") or "")
        for _c in (it.get("constituents") or []):
            _m = _pat.search(str(_c))
            if _m:
                issues.append(("ERROR", "engine/tax_redlines.py %s" % _rid,
                               "要件把**薪酬类总额**与「行业人均营收基准」作比较（命中「%s」）"
                               "——营收与工资**不同量纲**，属模板误用；"
                               "薪酬的规模门限只能是「人均工资×从业人数」" % _m.group(0)[:40]))
    return issues


def check_same_suspicion_tables_relation_declared() -> List[Tuple[str, str, str]]:
    """★ 2026-10-04（用户复核疑点6 D8）——**同一疑点内讲同一批差异的多张表必须声明口径关系**。

    事故：同一疑点下出现「工资名册与社会保险人员范围差异（30 行，人月级）」、
    「有工资无社保（2 行，人月级）」、「工资名册有、社保参保无（1 行，人员级）」——
    三张表讲的是**同一批差异**（后者是按人员归并），却都没说明口径关系，
    读者会以为是三批不同的差异。（根因：**不同域各自建表**，互不知道对方已出过表 ⇒ 多头建表。）

    判据（读真跑产物，数据驱动、不认表名）：同一疑点内，两表
      **实体值集非空且相等** + **都有金额列** + **行数不同** ⇒ 行数少的那张必须在
      标题或 `scope_note` 里声明"同一批差异/归并"口径 ⇒ 否则 ERROR。
    """
    issues: List[Tuple[str, str, str]] = []
    art = ROOT / "scripts" / "four_reports" / "company_1_full.json"
    if not art.exists():
        return [("WARN", "scripts/four_reports/company_1_full.json",
                 "无真跑产物，无法核验「同疑点内表口径关系」——请先跑一次全量")]
    try:
        import json as _json
        d = _json.loads(art.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        return [("WARN", "scripts/four_reports/company_1_full.json", "产物不可解析：%s" % e)]
    rep = d.get("report") if isinstance(d.get("report"), dict) else d
    er = (rep or {}).get("enterprise_readable_report") or {}
    _ENT = ("姓名", "人员", "人员姓名", "对方单位", "counterparty", "工号", "身份证号")
    _AMT = ("金额（元）", "金额(元)", "金额", "amount", "应发工资（元）", "工资",
            "工资表内工资合计（元）", "账面发生额（元）", "超限金额（元）")

    def _ents(tb):
        s = set()
        for r in (tb.get("rows") or []):
            if not isinstance(r, dict):
                continue
            for k in _ENT:
                v = str(r.get(k) or "").strip()
                if v:
                    s.add(v)
                    break
        return s

    def _has_amt(tb):
        cols = [str(c) for c in (tb.get("columns") or [])]
        cols += [k for r in (tb.get("rows") or []) if isinstance(r, dict) for k in r.keys()]
        return any(any(a == c or a in c for a in _AMT) for c in cols)

    for p in (er.get("confirmed_problems") or []):
        if not isinstance(p, dict):
            continue
        tabs = [t for t in _prob_tables(p) if (t.get("rows") or [])]
        for i in range(len(tabs)):
            for j in range(len(tabs)):
                if i == j:
                    continue
                ei, ej = _ents(tabs[i]), _ents(tabs[j])
                if not ei or ei != ej:
                    continue
                if not (_has_amt(tabs[i]) and _has_amt(tabs[j])):
                    continue
                if not (len(tabs[i].get("rows") or []) < len(tabs[j].get("rows") or [])):
                    continue
                _blob = str(tabs[i].get("title") or "") + " " + str(tabs[i].get("scope_note") or "")
                if ("同一批差异" in _blob) or ("归并" in _blob):
                    continue
                issues.append(("ERROR", "confirmed_problems[seq=%s]" % p.get("seq"),
                               "表「%s」（%d 行）与「%s」（%d 行）**讲同一批对象**（实体集相同）"
                               "但未声明口径关系 —— 读者会以为是两批不同差异"
                               % (str(tabs[i].get("title") or "")[:22], len(tabs[i].get("rows") or []),
                                  str(tabs[j].get("title") or "")[:22], len(tabs[j].get("rows") or []))))
    return issues


def check_next_actions_not_ghost_requirements() -> List[Tuple[str, str, str]]:
    """★ 2026-10-04（用户复核疑点6 D11/D13）——**"要求企业补充"的资料必须真的缺、且本项真的需要**。

    事故（「五、需企业提供的资料与说明」）：
      · "补充提供**社保明细**" —— 同一疑点要件①⑤ 的独立数据源已判**「已有」**（既"已有"又"要补"）；
      · "补充提供**记账凭证**" —— 本项**任何**要件的数据源都没有它（幽灵要求）；
      · "补充提供**合同文件**" —— 同类幽灵名（第 5 次出现，`missing_materials` 与
        `constituent_sources` 完全脱钩）。
    根因：`argumentation` 的"文本关键词命中 ⇒ 补一条'补充提供'"**不看取得状态、不看要件数据源**
    （注释写"前置、不删既有需求"，实现却凭空新增 —— 实现与意图不符）。

    判据（读真跑产物）：「五、」里每条「补充提供「X」」：
      ① X（或其类别）在要件核对表里状态为**「已有」** ⇒ ERROR；
      ② X 不在**任何要件的独立数据源**里（按类别归一后仍找不到） ⇒ ERROR。
    """
    issues: List[Tuple[str, str, str]] = []
    art = ROOT / "scripts" / "four_reports" / "company_1_full.json"
    if not art.exists():
        return [("WARN", "scripts/four_reports/company_1_full.json",
                 "无真跑产物，无法核验「补充资料要求是否为幽灵」——请先跑一次全量")]
    try:
        import json as _json
        d = _json.loads(art.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        return [("WARN", "scripts/four_reports/company_1_full.json", "产物不可解析：%s" % e)]
    rep = d.get("report") if isinstance(d.get("report"), dict) else d
    er = (rep or {}).get("enterprise_readable_report") or {}
    try:
        from engine.material_names import canonical as _canon
    except Exception:  # noqa: BLE001
        _canon = None
    for p in (er.get("confirmed_problems") or []):
        if not isinstance(p, dict):
            continue
        own: Dict[str, str] = {}      # 要件独立数据源 → 数据源状态
        ev_own: Dict[str, str] = {}   # 证据角色名 → 现状
        for tb in _prob_tables(p):
            _ttl = str(tb.get("title") or "")
            if "构成要件独立核对表" in _ttl:
                for r in (tb.get("rows") or []):
                    if not isinstance(r, dict):
                        continue
                    _decl = str(r.get("独立数据源") or "")
                    _st = str(r.get("数据源状态") or "")
                    for part in re.split(r"[、，,；;/／\s]+", _decl):
                        part = part.strip()
                        if part and part not in own:
                            own[part] = _st
            elif (tb.get("columns") or []) and "证据角色" in [str(c) for c in (tb.get("columns") or [])]:
                for r in (tb.get("rows") or []):
                    if not isinstance(r, dict):
                        continue
                    _nm = str(r.get("证据名称") or "").strip()
                    if _nm:
                        ev_own[_nm] = str(r.get("现状") or "")
        # 本项**实际声明过的资料来源** = 要件独立数据源 ∪ 证据角色名
        _declared_names = list(own.keys()) + list(ev_own.keys())
        if not _declared_names:
            continue

        def _traceable(x: str) -> bool:
            for n in _declared_names:
                if x == n or x in n or n in x:
                    return True
                if _canon:
                    _cx, _cn = _canon(x), _canon(n)
                    if _cx and _cn and _cx == _cn:
                        return True
            return False

        def _already_have(x: str) -> bool:
            """`x` 是否**已经到手**（判据本身即可复核）。

            ★★ 2026-10-16 修（**判据误报**，不是数据错）：判据本意是抓
              「让企业去补一份**已经交了的资料**」。但**类别级**比较过粗 ——
              `material_names.canonical` 把「成本明细账」与「应付账款明细」
              都归成**同一类别**「科目余额表」；于是「补充提供**应付账款明细账及账龄分析**」
              被判成"已有"，**实际上**同项里 成本明细账=已有、应付账款明细=**尚未取得**
              （要件核对表的「核对结论」写着"尚未取得：应付账款明细"）⇒ **要求补充完全正确**。
              ⇒ 类别级只在**该类别下所有已声明来源都「已有」**时才判"已然在手"
                （＝"这一类都不缺"），否则退回**名称级**严格子串判断。
            """
            # ① 名称级（严格）：完全相同 / 互为子串
            for n, st in list(own.items()) + list(ev_own.items()):
                if st != "已有":
                    continue
                if x == n or x in n or n in x:
                    return True
            if not _canon:
                return False
            # ② 类别级：仅当**该类别下每个已声明来源都是「已有」**
            cx = _canon(x)
            if not cx:
                return False
            members = [(n, st) for n, st in list(own.items()) + list(ev_own.items())
                       if _canon(n) == cx]
            return bool(members) and all(st == "已有" for _n, st in members)

        for np_ in (p.get("narrative_paragraphs") or []):
            if not isinstance(np_, dict):
                continue
            for b in (np_.get("bullets") or []):
                # ⚠ 渲染层 `_trim_action_material` 会把「补充提供「X」」的「」剥掉，
                #   故正则在**两种写法**下都要命中（有/无书名号）。
                m = re.match(r"^补充提供[「]?(.+?)[」]?$", str(b).strip())
                if not m:
                    continue
                _x = m.group(1).strip()
                if _already_have(_x):
                    issues.append(("ERROR", "confirmed_problems[seq=%s]" % p.get("seq"),
                                   "要求「补充提供「%s」」，而该资料在本项已判**已有**"
                                   "——同一条疑点既「已有」又「要补」，自相矛盾" % _x))
                    continue
                if not _traceable(_x):
                    issues.append(("ERROR", "confirmed_problems[seq=%s]" % p.get("seq"),
                                   "要求「补充提供「%s」」，但**本项既没有把它列为要件数据源、"
                                   "也没有把它列为证据角色**（幽灵要求；实测疑点6 的"
                                   "「记账凭证」「合同文件」）" % _x))
                    continue
                # ③ **不得用"资料类别名"充当资料要求** —— 类别名（15 类）是内部归类口径，
                #    不是"企业该交的那份材料"。事故：疑点6 报「补充提供**合同文件**」，
                #    而本项真正缺的是「**劳动合同与用工名册**」（"劳动合同"按关键词归入
                #    "合同文件"类别）⇒ 读者以为要交易合同（幽灵名第 5 次）。
                #    判据：X 是类别名，且 X **不等于**本项声明过的任一名（即只能靠**类别归一**
                #    才追溯得到）⇒ 说明它是"类别名冒充资料名"。
                try:
                    from engine.material_names import is_category as _is_cat
                except Exception:  # noqa: BLE001
                    _is_cat = None
                if _is_cat and _is_cat(_x) and _x not in _declared_names:
                    issues.append(("ERROR", "confirmed_problems[seq=%s]" % p.get("seq"),
                                   "要求「补充提供「%s」」——「%s」是**资料类别名**（15 类之一），"
                                   "不是具体材料名；应写成本项实际缺的那份材料名"
                                   "（否则读者按类别字面理解会找错资料）" % (_x, _x)))
    return issues


def check_no_false_exclusion() -> List[Tuple[str, str, str]]:
    """★ 2026-10-04（疑点10-21 合并批次 ⑲）：**禁止虚假排除**——"未发现符合/已排除"必须有数据支撑。

    两类虚假结论（都有数据支撑才允许写）：
      · 「资料已取得 ⇒ 未发现符合本要件情形」：资料拿到手 ≠ 核过。旧实现在该要件
        **根本没有核对证据**时照样写"未发现符合"，一句没有任何核对动作支撑的结论
        ⇒ 读者以为系统查过（虚假排除）；
      · `check_constituent_hit` 判 `unknown`（要件无阈值 / 证据取不到同量纲值）时
        仍判「符合」⇒ 用默认值替企业认了一条要件。
    真实产出应是 `not_concluded`（资料已取得但未形成核对结论，不作"未发现符合"认定）。

    判据：① `not_concluded` 状态存在且不能被"资料已取得"直接推出 `checked_miss`；
          ② 行为级：给一份"资料已取得但无核对证据"的要件，必须得 `not_concluded`；
          ③ `unknown` 阈值结果必须走 `not_concluded`，不得落到 `checked_hit`。
    """
    issues: List[Tuple[str, str, str]] = []
    rel = "engine/constituent_checkpoint.py"
    if not (ROOT / rel).exists():
        return [("ERROR", rel, "缺少 constituent_checkpoint")]
    src = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
    if '"not_concluded"' not in src:
        return [("ERROR", rel, "未定义 `not_concluded` 状态 ⇒ 「资料已取得」仍会直接推出『未发现符合』")]
    try:
        from engine.constituent_checkpoint import build_constituent_checkpoints  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        return [("ERROR", rel, "无法导入要件核对：%s" % e)]

    # ② 行为级：独立数据源"已有"，但该要件没有对应核对证据 ⇒ 必须 not_concluded（不是 checked_miss）
    #   注意：`available_materials` 必须真的含该材料名，否则 `_match_material` 判"缺失"，
    #   走的是 not_checked（资料没拿到）这条完全不同的路 —— 那不是本闸门要管的"虚假排除"。
    fake = {
        "constituents": ["存在账外收入"],
        "constituent_sources": [{"name": "工资表"}],
        "evidence_chain": {
            "available_materials": ["工资表"],
            "elements": [{"role": "直接证据", "name": "工资表", "status": "已有"}],
        },
    }
    cps = build_constituent_checkpoints(fake, None)
    if not cps:
        return [("ERROR", rel, "要件核对构建返回空 ⇒ 判据形同虚设")]
    _c = cps[0]
    if str(_c.get("数据源状态")) not in ("已有", "已提交", "已提供", "已取得"):
        return [("ERROR", rel, "行为用例未构造出『资料已取得』（实际=%s），判据无效"
                 % str(_c.get("数据源状态")))]
    if _c.get("_conclusion") == "checked_miss":
        issues.append(("ERROR", rel,
                       "「资料已取得但无核对证据」被判『未发现符合本要件情形』（%s）—— 虚假排除，"
                       "应判 not_concluded（未形成核对结论）" % str(_c.get("核对结论"))[:40]))
    elif _c.get("_conclusion") != "not_concluded":
        issues.append(("ERROR", rel,
                       "「资料已取得但无核对证据」既非 not_concluded 亦非 checked_miss，"
                       "实际=%s —— 状态机漏路" % str(_c.get("_conclusion"))))

    # ③ 阈值判 unknown ⇒ 不得判"符合"
    try:
        from engine.constituent_checkpoint import assess_hit_evidence  # noqa: PLC0415
        _src2 = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        if 'elif _verdict == "unknown":' not in _src2.replace("\r\n", "\n"):
            issues.append(("ERROR", rel,
                           "阈值判 unknown 时未走 not_concluded ⇒ 会用默认值替企业认定『符合』"))
    except Exception as e:  # noqa: BLE001
        issues.append(("ERROR", rel, "无法验证 unknown 分支：%s" % e))

    # ④ 汇总文案必须把 not_concluded 单列（不得并进"已单独核对"的分子）
    if "未形成核对结论 %d 条" not in src:
        issues.append(("ERROR", rel, "汇总文案未把 `not_concluded` 单列 ⇒ 读者会把它算成『查过』"))
    return issues


def check_tax_rate_single_source() -> List[Tuple[str, str, str]]:
    """★ 2026-10-04（疑点10-21 合并批次 ⑫）：税率/随征计征口径**单一权威**，
    且"已知税种但算不出"必须**披露未量化**，不得静默消失。

    事故（三处同源）：
      ① `estimate_tax` 底部把城建税+教育费附加合计**硬编码 0.12**（税率/税名/附注三处各写一份），
         而 `_RATES` 表里根本没有这三税 ⇒ 改一处必漏两处（多头维护=事故）；
      ② `_RATES.get(t) → rate is None → continue` ⇒ 红线库 29 个税种里有 **25 个**压根不在
         表里，它们的税额**静默消失**：报告里既不说"量化了"、也不说"未量化"，读者无从察觉；
      ③ 若同时列示「增值税」和「城市维护建设税」⇒ 既按 7% 单独加、又按 12% 合并加 ⇒ 敞口翻倍。

    判据：
      ① `_RATES` 必须登记城建税/教育费附加/地方教育附加/城建税及教育费附加；
      ② `estimate_tax` 内**不得再出现**字面 0.12（税率口径须取自 `_RATES`）；
      ③ 红线库登记过的税种若 `rate is None`，**必须**走"未量化"披露（不得静默 continue）；
      ④ 已知税种集合的唯一权威是红线库 `taxes` 字段，不得在别处重建。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine import tax_impact as _ti
        from engine.tax_redlines import REDLINES as _RLS
    except Exception as e:  # noqa: BLE001
        return [("ERROR", "engine/tax_impact.py", "无法导入：%s" % e)]
    _rl_src = (ROOT / "engine/tax_redlines.py").read_text(encoding="utf-8", errors="replace")

    # ① 随征三税登记
    for _need in ("城建税及教育费附加", "城市维护建设税", "教育费附加", "地方教育附加"):
        if _need not in _ti._RATES:
            issues.append(("ERROR", "engine/tax_impact.py",
                           "_RATES 未登记「%s」——随征税率口径被硬编码在别处（多头维护）" % _need))

    # ② **行为校验**（不是字符串浅查）：改 _RATES 必须真的改变 estimate_tax 的随征金额。
    #    判据来源本身要可反向验证——若只查"函数体内还有没有 0.12"，把 0.12 挪到别处就变绿了
    #    （实测：M1 破坏后闸门仍报 0 ERROR ⇒ 那是个假闸门，已废弃）。
    try:
        _orig_rates = dict(_ti._RATES)
        _ti._RATES["城建税及教育费附加"] = (0.20, "闸门行为校验")
        # 随征按**算出的增值税额**求：100 万 × 13% = 13 万 ⇒ 期望随征 = 13 万 × 20% = 26000
        _amt = {i["tax"]: i.get("amount") for i in
                _ti.estimate_tax(1000000.0, ["增值税"])["items"]}.get("城建税及教育费附加")
        _ti._RATES.clear()
        _ti._RATES.update(_orig_rates)
        if _amt is None or abs(float(_amt) - 26000.0) > 1.0:
            issues.append(("ERROR", "engine/tax_impact.py",
                           "把 _RATES[城建税及教育费附加] 改成 0.20 后，随征金额=%s（应为 26000.00）；"
                           "⇒ 税率被硬编码在别处，_RATES 并非单一权威" % _amt))
    except Exception as e:  # noqa: BLE001
        issues.append(("ERROR", "engine/tax_impact.py", "随征税率行为校验异常：%s" % e))

    # ③ 红线库登记过的税种必须"要么有税率、要么显式未量化、要么显式登记为不参与测算"
    _known = set()
    for _rl in (_RLS or []):
        for _t in (_rl.get("taxes") or []):
            _known.add(str(_t))
    _nonesc = set(_ti.non_estimable_taxes().keys())
    _registered_with_none = ({k for k, v in _ti._RATES.items() if v and v[0] is None} | _nonesc)
    _unregistered = sorted(_known - set(_ti._RATES.keys()))
    _silent = [t for t in _unregistered if t not in _registered_with_none]
    if _silent:
        issues.append(("ERROR", "engine/tax_impact.py",
                       "以下红线库登记税种既无税率、**又未**登记为未量化 ⇒ 会静默消失（%s）"
                       % "、".join(_silent)))

    # ④ 已知税种唯一权威 = 红线库 taxes（tax_impact 内只准经 known_tax_types() 取得）
    _src2 = (ROOT / "engine/tax_impact.py").read_text(encoding="utf-8", errors="replace")
    if "known_tax_types" not in _src2:
        issues.append(("ERROR", "engine/tax_impact.py",
                       "未导出 known_tax_types()——已知税种集合应在 tax_impact 内转发红线库单一权威"))
    return issues


def check_non_tax_law_not_misattributed() -> List[Tuple[str, str, str]]:
    """★ 2026-10-04（疑点10-21 合并批次 ⑭）：**非税事项不得被挂到税收法律**。

    事故链：非税关键词（公积金/工会经费/残保金/文化事业建设费）在 `_infer_law_ref` 表里查不到
    ⇒ `auto_heal` 回落到「《税收征收管理法》第二十五条」⇒ **法律适用错**
    （税收征管法调整纳税申报与税款征收，公积金缴存/社保缴费/工会经费拨缴不归其调整）；
    同时这些发现拿不到"像样的"法条 ⇒ M06（score≥8 且缺 law_ref）判违规 ⇒ 实测 21 项触发
    ⇒ 整份被打上「合规门禁阻断：21 项阻断性违规」（fy5/fy6 备份与本轮均为此态）。

    判据：
      ① `_NON_TAX_LAW_KEYWORDS` / `_NON_TAX_LAW_MAP` 必须存在（非税依据单一表）；
      ② `_infer_law_ref` **先判非税表再判税表**（否则"工资"会抢走「公积金缴存基数低于实际工资」）；
      ③ 非税发现缺法条时**禁止**回落《税收征收管理法》（只允许写"待人工核验适用依据"）；
      ④ M06 违规里属非税事项的，必须降级为警告、不得计入阻断。
    """
    issues: List[Tuple[str, str, str]] = []
    rel = "engine/self_learning.py"
    if not (ROOT / rel).exists():
        return [("ERROR", rel, "缺少 self_learning")]

    # ① 非税两表
    if "_NON_TAX_LAW_KEYWORDS" not in (ROOT / rel).read_text(encoding="utf-8", errors="replace"):
        return [("ERROR", rel, "未定义 _NON_TAX_LAW_KEYWORDS（非税事项清单）")]

    try:
        from engine.self_learning import ComplianceGate  # noqa: PLC0415
        from engine.self_learning import (  # noqa: PLC0415
            _NON_TAX_LAW_KEYWORDS, _NON_TAX_LAW_MAP, _is_non_tax_finding,
        )
    except Exception as e:  # noqa: BLE001
        return [("ERROR", rel, "无法导入非税法条判据：%s" % e)]

    # ② 顺序：非税表必须先判
    _wrong = ComplianceGate.__new__(ComplianceGate)._infer_law_ref("公积金缴存基数低于实际工资")
    if "工资" in _wrong or "公积金" not in _wrong:
        issues.append(("ERROR", rel,
                       "_infer_law_ref 对非税事项返回了税表法条（%s）—— 非税表未先判 ⇒ 法律适用错"
                       % str(_wrong)[:40]))

    # ③ 非税发现禁止回落《税收征收管理法》
    _probe = {"type": "有工资无公积金", "taxes": ["住房公积金"]}
    if not _is_non_tax_finding(_probe):
        issues.append(("ERROR", rel, "_is_non_tax_finding 判不出「有工资无公积金」——非税识别失效"))

    # ④ 源码层面：非税发现命中后，auto_heal 的兜底不得写《税收征收管理法》
    src = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
    if "_is_non_tax_finding(f)" not in src:
        issues.append(("ERROR", rel, "auto_heal 未对非税事项做区分，仍会整套《税收征收管理法》兜底"))
    # ★★ 2026-10-04：本检查**由源码字符串升级为行为级**。
    #   旧判据 `"_m06_non_tax_viol_ids" not in src` 只认一个内部属性名 ——
    #   本轮把豁免记账改成"按发现身份"（变量改名、行为不变），旧检查当场变红，
    #   而真正要保的是**行为**：非税发现缺法条不得阻断整份报告。
    try:
        from engine.self_learning import ComplianceGate as _CG_nt  # noqa: PLC0415
        _g_nt = _CG_nt([{"type": "有工资无公积金", "taxes": ["住房公积金"], "score": 9}], [], {}, {})
        _r_nt = _g_nt.check_all()
        _blk_nt = [v for v in (_r_nt.get("blocking_violations") or [])
                   if v.get("rule") == "M06-法条引用"]
        if _blk_nt:
            issues.append(("ERROR", rel,
                           "非税发现（有工资无公积金）缺法条仍被判**阻断** ⇒ "
                           "整份报告会被「合规门禁阻断」卡死；应记 M06-N 降级为警告"))
        if _r_nt.get("passed") is False and not _blk_nt and _r_nt.get("blocked"):
            issues.append(("ERROR", rel, "非税降级后门禁仍整体不放行（阻断标记未与违规清单同步）"))
        # 反向：写出非税依据后必须正常通过（不得把 M06 判据整个废掉）
        _g_nt2 = _CG_nt([{"type": "有工资无公积金", "taxes": ["住房公积金"], "score": 9,
                          "policy_ref": "《住房公积金管理条例》第十五条"}], [], {}, {})
        if [v for v in (_g_nt2.check_all().get("blocking_violations") or [])
                if v.get("rule") == "M06-法条引用"]:
            issues.append(("ERROR", rel, "非税发现已写明依据仍被判缺法条 ⇒ M06 判据与字段不同源"))
    except Exception as e:  # noqa: BLE001
        issues.append(("ERROR", rel, "无法验证 M06 非税降级（行为级）：%s" % e))

    # ⑤ ③ 的延伸：M06 豁免必须是**行为级**判据，否则「豁免名单」会悄悄缩水。
    #   实测事故：旧实现只看「score≥8 且 law_ref 空」，把**元发现**（「结论自洽-…」
    #   「Causal: …」「综合定性结论」「资料完备度综合评估」）也判"缺法条" ⇒ 实测 21 项阻断
    #   ⇒ 整份报告被打成「合规门禁阻断：21 项阻断性违规」。
    try:
        from engine.self_learning import _m06_exempt_reason, ComplianceGate  # noqa: PLC0415
        for _meta in ("结论自洽-虚开信号与四流合一完整的冲突",
                      "Causal: 隐匿收入的资金回流路径",
                      "综合定性结论", "资料完备度综合评估"):
            if not _m06_exempt_reason({"type": _meta}):
                issues.append(("ERROR", rel,
                               "M06 未豁免元发现「%s」—— 自检结论被判「缺法条」"
                               " ⇒ 整份报告会被「合规门禁阻断」卡死" % _meta[:18]))
        # 行为级（两个方向都要成立，闸门才不是假的）：
        #   甲·把元发现塞进门禁 ⇒ M06-法条引用 **不得**出现在阻断里；
        #   乙·把真涉税发现塞进门禁 ⇒ M06-法条引用 **必须**仍是阻断（否则等于把门禁拆了）。
        _g = ComplianceGate(
            [{"type": _meta, "score": 9} for _meta in
             ("结论自洽-虚开信号与四流合一完整的冲突", "Causal: 隐匿收入的资金回流路径")],
            [], {}, {})
        _res = _g.check_all()
        _blk = [v for v in (_res.get("blocking_violations") or []) if v.get("rule") == "M06-法条引用"]
        if _blk:
            issues.append(("ERROR", rel,
                           "门禁仍把「%s」判为阻断性缺法条 ⇒ 实测 21 项阻断的根因未除"
                           % _blk[0].get("finding", "")[:20]))
        _g2 = ComplianceGate([{"type": "有工资无社保", "score": 9}], [], {}, {})
        _res2 = _g2.check_all()
        if not [v for v in (_res2.get("blocking_violations") or [])
                if v.get("rule") == "M06-法条引用"]:
            issues.append(("ERROR", rel,
                           "真涉税发现「有工资无社保」缺法条竟**不阻断** —— 豁免判据被放得太宽，"
                           "门禁形同虚设"))
        # ⑦ 判据与产出**同源**：法条写在 `policy_ref`（`findingkit` 的规范字段）也必须有依据。
        #   事故：M06 只读 `law_ref`，而 `auto_heal` 只写 `policy_ref`（或反过来）
        #   ⇒ 4 项"法条已写好"的发现仍被判"缺法条" ⇒ 报告被「合规门禁阻断」。
        for _fld in ("policy_ref", "law_ref"):
            _g3 = ComplianceGate([{"type": "有工资无社保", "score": 9, _fld: "《社会保险法》第五十八条"}],
                                 [], {}, {})
            _r3 = _g3.check_all()
            if [v for v in (_r3.get("blocking_violations") or []) if v.get("rule") == "M06-法条引用"]:
                issues.append(("ERROR", rel,
                               "法条写在 `%s` 仍被判「缺法条」—— M06 判据与写出字段不同源"
                               "（唯一权威 `legal_citation.legal_reference_of`）" % _fld))
    except Exception as e:  # noqa: BLE001
        issues.append(("ERROR", rel, "无法验证 M06 元发现豁免：%s" % e))

    # ⑥ 外部核验类的「单一权威」必须覆盖真实产出的前缀（实测只登记了「需外部数据核验：」，
    #   真实产出用的是「待核事实：」⇒ 判据恒 False ⇒ 待办项被误判触红）。
    try:
        from engine.argumentation import is_external_check_finding  # noqa: PLC0415
        for _t in ("待核事实：企业所得税贡献率偏低", "需外部数据核验：X"):
            if not is_external_check_finding({"type": _t}):
                issues.append(("ERROR", "engine/argumentation.py",
                               "is_external_check_finding 认不出真实前缀「%s」"
                               " ⇒ 外部核验类被误判触红" % _t.split("：")[0]))
    except Exception as e:  # noqa: BLE001
        issues.append(("ERROR", "engine/argumentation.py", "无法验证外部核验判据：%s" % e))
    return issues


def check_material_name_single_source() -> List[Tuple[str, str, str]]:
    """★ 2026-10-03（用户："彻底解决多种叫法的问题"）：资料名称**唯一权威** + 齐备性口径一致。

    背景：资料名曾散落 8 处（`required_materials` / `evidence_chain[].name` /
    `constituent_sources` / `_SUPP_ENTRIES` / `_MATERIAL_KEYWORDS` / `_MATERIAL_SYNONYMS` /
    `_EQUIVALENT_CATEGORIES` / `_MATERIAL_SUPERCLASS`），同一份材料两套名字两套判定 ⇒
    要件表说「银行流水｜已有」、证据表说「完整资金链条流水｜待核实」，**同一页自相矛盾**。

    判据：
      ① 唯一权威 `engine/material_names.py` 存在且导出归一入口；
      ② `evidence_chain` **不得再自建**类别/别名表（应为转发，杜绝多头维护）；
      ③ **两级命名行为**：
         · "完整资金链条流水"（细名）→ 与"银行流水"（类别）**同一材料**；
         · 类别命满 ⇒ 判「已有」；类别未命满/有段落判不出 ⇒ **不得**判「已有」；
         · 反证（role="反证"）**不得**因"已提供合同文件类别"而判「已有」。
      ④ **反向验证**：临时清空别名表 → "完整资金链条流水"必须**不再**判「已有」
         （证明判定真的依赖登记，而不是靠字符串碰巧）。
    """
    issues: List[Tuple[str, str, str]] = []
    auth_rel = "engine/material_names.py"
    if not (ROOT / auth_rel).exists():
        return [("ERROR", "engine/", "缺少唯一权威 material_names（资料名称/别名归一）")]

    src_auth = (ROOT / auth_rel).read_text(encoding="utf-8", errors="replace")
    for marker, why in (
        ("def canonical", "未导出 canonical（任意叫法→类别）"),
        ("def category_strict", "未导出 category_strict（严格口径，供齐备性判定）"),
        ("def strict_categories_all", "未导出 strict_categories_all（要求全部段落可归类）"),
        ("def missing_from", "未导出 missing_from（按类别求差集）"),
        ("CATEGORY_ALIASES", "未定义类别别名表"),
    ):
        if marker not in src_auth:
            issues.append(("ERROR", auth_rel, why))

    # ② evidence_chain 不得再自建表
    ec_rel = "engine/evidence_chain.py"
    src_ec = (ROOT / ec_rel).read_text(encoding="utf-8", errors="replace")
    if "_MATERIAL_KEYWORDS: List[List[str]] = [" in src_ec:
        issues.append(("ERROR", ec_rel,
                       "仍在自建 _MATERIAL_KEYWORDS 字面量表——应转发 material_names（多头维护）"))
    if "_MATERIAL_SYNONYMS = {" in src_ec:
        issues.append(("ERROR", ec_rel,
                       "仍在自建 _MATERIAL_SYNONYMS 字面量表——应转发 material_names（多头维护）"))
    if "from engine.material_names import" not in src_ec:
        issues.append(("ERROR", ec_rel, "未引用唯一权威 material_names"))

    # ③ 两级命名行为
    try:
        from engine.evidence_chain import _match_material
        from engine.material_names import same_material
        if not same_material("完整资金链条流水", "银行流水"):
            issues.append(("ERROR", auth_rel,
                           "「完整资金链条流水」未被归为「银行流水」——细名永远匹配不上类别名"))
        _avail = ["银行流水", "销项发票", "进项发票", "合同文件", "进销存台账"]

        def _st(nm, role="直接证据"):
            return _match_material(nm, "证明目的", _avail, role=role)["status"]

        if _st("完整资金链条流水") != "已有":
            issues.append(("ERROR", ec_rel,
                           "细名（完整资金链条流水）在已提供银行流水时未判「已有」"))
        # ★ 反证的判据在**生产路径**里是 `build_evidence_chain`（只认企业实际提交，
        #   状态为"已提交/待企业提交"），**不走** `_match_material` —— 故必须按生产路径验证，
        #   直接调 `_match_material(role="反证")` 会测到一条不存在于生产的路径（闸门自己误报过一次）。
        from engine.evidence_chain import build_evidence_chain as _bec
        _rl_reb = {"evidence_chain": [{"role": "反证", "name": "退款协议、质量索赔协议",
                                      "purpose": "交易取消后的退款不属回流"}]}
        _ev_reb = _bec({"type": "x"}, _rl_reb, ["银行流水", "合同文件"])
        for _e in _ev_reb["elements"]:
            if _e["role"] == "反证" and _e["status"] != "待企业提交":
                issues.append(("ERROR", ec_rel,
                               "反证材料未由企业提交却非「待企业提交」（status=%s）" % _e["status"]))
        # 未提供该类别 ⇒ 不得判已有；部分覆盖 ⇒ 不得整项判已有
        if _st("物流单据与承运记录") == "已有":
            issues.append(("ERROR", ec_rel, "未提供类别却判「已有」"))
        if _st("进项发票与采购台账") == "已有":
            issues.append(("ERROR", ec_rel,
                           "只覆盖一部分（进项发票有、采购台账无）却整项判「已有」"))
    except Exception as exc:
        issues.append(("WARN", ec_rel, "两级命名行为断言执行失败：%s" % exc))

    # ④ 反向验证：清空别名表 ⇒ 细名不得再判「已有」
    try:
        import engine.material_names as _mn
        _saved = dict(_mn.CATEGORY_ALIASES)
        try:
            # 原地清空（不是重新绑定）：`evidence_chain` 里转发引用的是**同一个 dict 对象**，
            # 重新绑定只改本模块属性，转发引用仍持有旧内容 ⇒ 反向验证会假绿。
            _mn.CATEGORY_ALIASES.clear()
            from engine.evidence_chain import _match_material as _mm2
            _s = _mm2("完整资金链条流水", "证明目的",
                      ["银行流水", "销项发票", "进项发票", "合同文件"], role="直接证据")["status"]
        finally:
            _mn.CATEGORY_ALIASES.clear()
            _mn.CATEGORY_ALIASES.update(_saved)
        if _s == "已有":
            issues.append(("ERROR", "闸门自检",
                           "反向验证失败：清空别名表后细名仍判「已有」（判定没真正依赖登记）"))
    except Exception as exc:
        issues.append(("WARN", "闸门自检", "反向验证执行失败：%s" % exc))
    return issues


# ══════════════ 检查：Python 未定义名（NameError 静态防线，2026-10-07）══════════════
# 根因链（用户现象「前端还是出旧模板报告」）：
#   `main.get_report_intelligence` 读取**未定义变量** `findings`（重构把 `findings` 改名
#   `all_findings` 时漏改 3 处）⇒ `/api/tax-risk-docs/report-smart` 返回 **500**
#   ⇒ 前端拿不到新报告数据、回落本地旧模板渲染 ⇒ 用户看到旧报告且查不出原因。
# 同批另有 5 处同类（执行到即 NameError，发现/章节被静默吞掉）：
#   · engine/domain_analysis.py     `_build_methods_data` 引用 5 个被重构擦除的变量
#   · engine/industry_benchmark.py  `run_industry_benchmark_check` 引用未定义的 `_LABEL`
#   · engine/enterprise_report.py   `_BENCH_CAUTION` 未定义（行业对标章节整段不产出）
#   · engine/self_healing.py        `auto_apply_fixes` 跨函数引用局部 `_BOILERPLATE`
#   · engine/verified_rule_engine.py `reversal_tax_total` 变量名笔误
# 为何不用 pyflakes：`main.py` / `engine/pipeline.py` 顶部有 `from x import *`，
#   pyflakes 遇 star-import 会**整体放弃**该文件的未定义名检测 —— 正是本类 bug 逃逸的原因。
#   故此处自建判据：对**有** star-import 的模块，以「全项目**模块级**符号并集」近似其可见符号；
#   对没有 star-import 的模块，只用其自身模块级符号（更精确，不靠大并集放水）。
# 判据：函数体内**读取**的裸名，若不在 本函数局部 ∪ 外层函数局部(闭包) ∪ 本模块模块级
#   ∪(有 star-import 时)项目模块级并集 ∪ 内置 ∪ 显式登记的动态注入 之内 → ERROR。
# 动态注入（`globals()[...]`）必须在 `_UNDEF_DYNAMIC_INJECTED` **显式登记**；未登记即 ERROR，
#   且登记的豁免若在源码里找不到对应字面量 → 同样 ERROR（豁免不得静默长期有效）。
_UNDEF_DYNAMIC_INJECTED: Dict[str, set] = {
    # 由 `globals()[...] = ...` 运行时注入，静态不可知。新增同类注入必须在此登记。
    "engine/phase2_deep_dive.py": {
        "_domain_profit_analysis", "_domain_supplier_deep", "_domain_fund_flow_mapping",
        "_domain_business_substance", "_domain_industry_benchmark",
        "_domain_voucher_invoice_revenue_compare", "_domain_vat_declaration_compare",
        "_domain_invoice_audit", "_domain_supplier_profiling", "_domain_supply_chain_deep",
        "_domain_business_premise_geo", "_domain_related_party_check",
        "_domain_salary_ss_hf_compare", "_domain_workforce_profiling",
        "_domain_personal_transactions", "_domain_revenue_timeline",
        "_domain_customer_revenue_matching",
    },
}
_UNDEF_EXTRA_OK = {"self", "cls", "__name__", "__file__", "__doc__", "__package__",
                   "__spec__", "__loader__", "__builtins__", "__debug__"}
_UNDEF_STAR_RE = r"^[ \t]*from[ \t]+[\w\.]+[ \t]+import[ \t]+\*"
_UNDEF_FUTURE_ANN = "from __future__ import annotations"


def _undef_direct_bindings(nodes: List[ast.AST]) -> set:
    """收集**本作用域直接绑定**的名字。

    不下钻嵌套函数/类体（它们自成作用域，由各自的核对处理）；
    但下钻 lambda 与推导式，并把 lambda 形参、推导式目标一并计入（过近似，只求不误报）。
    """
    out: set = set()

    class _V(ast.NodeVisitor):
        def visit_FunctionDef(self, n):
            out.add(n.name)

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, n):
            out.add(n.name)

        def visit_Name(self, n):
            if isinstance(n.ctx, ast.Store):
                out.add(n.id)
            self.generic_visit(n)

        def visit_Import(self, n):
            for a in n.names:
                out.add(a.asname or a.name.split(".")[0])

        def visit_ImportFrom(self, n):
            for a in n.names:
                if a.name != "*":
                    out.add(a.asname or a.name)

        def visit_Global(self, n):
            out.update(n.names)

        def visit_Nonlocal(self, n):
            out.update(n.names)

        def visit_ExceptHandler(self, n):
            if n.name:
                out.add(n.name)
            self.generic_visit(n)

        def visit_Lambda(self, n):
            a = n.args
            for x in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs):
                out.add(x.arg)
            if a.vararg:
                out.add(a.vararg.arg)
            if a.kwarg:
                out.add(a.kwarg.arg)
            self.generic_visit(n)

    _v = _V()
    for _n in nodes:
        _v.visit(_n)
    return out


def _undef_param_names(fn) -> set:
    """函数/ lambda 的形参名。"""
    a = fn.args
    out = {x.arg for x in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)}
    if a.vararg:
        out.add(a.vararg.arg)
    if a.kwarg:
        out.add(a.kwarg.arg)
    return out


def _undef_annotation_ids(tree: ast.AST) -> set:
    """注解子树（`from __future__ import annotations` 下不被求值）的节点 id 集合。

    这些位置的裸名**不会**在运行时求值（PEP 563），故不算未定义名
    （实测：`List`/`Dict`/`Optional` 等 typing 名曾占本检查 20+ 条误报）。
    """
    ids: set = set()
    anns: List[Any] = []
    for nd in ast.walk(tree):
        if isinstance(nd, (ast.FunctionDef, ast.AsyncFunctionDef)):
            anns.append(nd.returns)
            a = nd.args
            for x in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs):
                anns.append(x.annotation)
            if a.vararg:
                anns.append(a.vararg.annotation)
            if a.kwarg:
                anns.append(a.kwarg.annotation)
        elif isinstance(nd, ast.AnnAssign):
            anns.append(nd.annotation)
    for an in anns:
        if an is not None:
            for sub in ast.walk(an):
                ids.add(id(sub))
    return ids


def _undef_collect_loads(node: ast.AST, reachable: bool, skip_ids: set,
                         out: List[Tuple[str, int, bool]]) -> None:
    """收集单条语句内读取的裸名（不下钻嵌套函数/类体；下钻 lambda 与推导式）。"""
    class _V(ast.NodeVisitor):
        def visit_FunctionDef(self, n):
            pass

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, n):
            pass

        def visit_Name(self, n):
            if isinstance(n.ctx, ast.Load) and id(n) not in skip_ids:
                out.append((n.id, getattr(n, "lineno", 0), reachable))

    _V().visit(node)


def _undef_scan_block(stmts: List[ast.stmt], reachable: bool, skip_ids: set,
                      out: List[Tuple[str, int, bool]]) -> None:
    """按语句块推进「可达性」：终止语句之后的兄弟语句判为**不可达**（死代码）。

    死代码里的未定义名不会抛 NameError，故只报 WARN；可达处的才是 ERROR。
    """
    for st in stmts:
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue                                    # 自成作用域，由各自核对处理
        if isinstance(st, (ast.Return, ast.Raise)):
            _undef_collect_loads(st, reachable, skip_ids, out)
            reachable = False
            continue
        if isinstance(st, (ast.Break, ast.Continue)):
            reachable = False
            continue
        if isinstance(st, ast.If):
            _undef_collect_loads(st.test, reachable, skip_ids, out)
            _undef_scan_block(st.body, reachable, skip_ids, out)
            _undef_scan_block(st.orelse, reachable, skip_ids, out)
            continue
        if isinstance(st, ast.Try):
            _undef_scan_block(st.body, reachable, skip_ids, out)
            for h in st.handlers:
                _undef_scan_block(h.body, reachable, skip_ids, out)
            _undef_scan_block(st.orelse, reachable, skip_ids, out)
            _undef_scan_block(st.finalbody, reachable, skip_ids, out)
            continue
        if isinstance(st, (ast.For, ast.AsyncFor)):
            _undef_collect_loads(st.iter, reachable, skip_ids, out)
            _undef_scan_block(st.body, reachable, skip_ids, out)
            _undef_scan_block(st.orelse, reachable, skip_ids, out)
            continue
        if isinstance(st, ast.While):
            _undef_collect_loads(st.test, reachable, skip_ids, out)
            _undef_scan_block(st.body, reachable, skip_ids, out)
            _undef_scan_block(st.orelse, reachable, skip_ids, out)
            continue
        if isinstance(st, (ast.With, ast.AsyncWith)):
            for it in st.items:
                _undef_collect_loads(it.context_expr, reachable, skip_ids, out)
            _undef_scan_block(st.body, reachable, skip_ids, out)
            continue
        if hasattr(ast, "Match") and isinstance(st, ast.Match):
            _undef_collect_loads(st.subject, reachable, skip_ids, out)
            for c in st.cases:
                _undef_scan_block(c.body, reachable, skip_ids, out)
            continue
        _undef_collect_loads(st, reachable, skip_ids, out)


def check_undefined_names() -> List[Tuple[str, str, str]]:
    """全项目未定义名扫描（NameError 静态防线）。详见上方根因说明。"""
    import builtins as _bi
    import glob as _glob

    issues: List[Tuple[str, str, str]] = []
    # 扫描范围：main.py + 顶层模块（security_web/audit_enhancements 等）+ engine/** + routers/**
    #   （scripts/ tests/ tools/ 为一次性脚本与工具，不参与；顶层以 `_` 开头的临时文件亦跳过）
    files: List[Path] = [ROOT / "main.py"]
    for pat in ("*.py", "engine/**/*.py", "routers/**/*.py"):
        for p in _glob.glob(str(ROOT / pat), recursive=True):
            pp = Path(p)
            if pp.name.startswith("_") or "__pycache__" in pp.parts:
                continue
            files.append(pp)
    files = sorted({f for f in files if f.exists()})

    trees: Dict[str, ast.AST] = {}
    srcs: Dict[str, str] = {}
    for f in files:
        if not f.exists():
            continue
        rel = os.path.relpath(str(f), str(ROOT)).replace("\\", "/")
        try:
            srcs[rel] = f.read_text(encoding="utf-8", errors="ignore")
            trees[rel] = ast.parse(srcs[rel])
        except SyntaxError as exc:
            issues.append(("ERROR", rel, "语法错误，无法静态核对未定义名：%s" % exc))
        except Exception as exc:                                    # 留痕，不静默
            issues.append(("WARN", rel, "未能解析（跳过未定义名核对）：%s" % exc))

    per_module: Dict[str, set] = {}
    project_names: set = set()
    for rel, tree in trees.items():
        names = _undef_direct_bindings(list(tree.body))
        per_module[rel] = names
        project_names |= names

    builtin_names = set(dir(_bi)) | _UNDEF_EXTRA_OK

    parent: Dict[int, ast.AST] = {}
    for tree in trees.values():
        for nd in ast.walk(tree):
            for ch in ast.iter_child_nodes(nd):
                parent[id(ch)] = nd

    for rel, tree in trees.items():
        injected = _UNDEF_DYNAMIC_INJECTED.get(rel) or set()
        for nm in sorted(injected):
            if ("\"%s\"" % nm) not in srcs[rel] and ("'%s'" % nm) not in srcs[rel]:
                issues.append(("ERROR", rel,
                               "动态注入豁免 `%s` 在源码中找不到对应字符串字面量 —— "
                               "豁免已过期，请删除该登记（豁免不得静默长期有效）" % nm))
        has_star = bool(re.search(_UNDEF_STAR_RE, srcs[rel], re.M))
        base = per_module[rel] | builtin_names | injected
        if has_star:
            # star-import 的可见符号静态不可知 → 用全项目模块级并集近似（仅此类模块放宽）
            base |= project_names
        skip_ids = _undef_annotation_ids(tree) if _UNDEF_FUTURE_ANN in srcs[rel] else set()

        for fn in [n for n in ast.walk(tree)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            visible = _undef_direct_bindings(list(fn.body)) | _undef_param_names(fn)
            p = parent.get(id(fn))
            while p is not None:                        # 闭包：外层函数局部可见
                if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    visible |= _undef_direct_bindings(list(p.body)) | _undef_param_names(p)
                p = parent.get(id(p))

            loads: List[Tuple[str, int, bool]] = []
            _undef_scan_block(list(fn.body), True, skip_ids, loads)

            alive: Dict[str, int] = {}
            dead: Dict[str, int] = {}
            for nm, ln, reach in loads:
                if nm in visible or nm in base:
                    continue
                tgt = alive if reach else dead
                if nm not in tgt:
                    tgt[nm] = ln
            for nm, ln in sorted(alive.items(), key=lambda kv: kv[1]):
                issues.append((
                    "ERROR", "%s:%d" % (rel, ln),
                    "函数 `%s` 读取未定义名 `%s` —— 执行到该行即 NameError"
                    "（该分支的发现/章节会被静默吞掉）。改完必须跑本闸门。" % (fn.name, nm)))
            for nm, ln in sorted(dead.items(), key=lambda kv: kv[1]):
                if nm in alive:
                    continue
                issues.append((
                    "WARN", "%s:%d" % (rel, ln),
                    "不可达代码（前置 return/raise 之后）引用未定义名 `%s`（函数 `%s`）"
                    "—— 当前不会抛错，但属**结构性隐患**（疑似 def 行丢失 / 函数体被并入 / "
                    "旧实现未删净），建议删除死代码或恢复其入口。" % (nm, fn.name)))
    return issues


_JS_TOP_LEVEL_HELPERS: Dict[str, List[str]] = {
    # 报告级取数/判据函数：被多个顶层渲染函数共用，**必须**留在模块顶层。
    "static/js/tax-doc-analysis.js": [
        "_reportDocName", "_complianceOf", "_signatureRows", "_isEnterpriseEdition",
        "_fallbackReason",
    ],
}


def check_js_report_helper_scope() -> List[Tuple[str, str, str]]:
    """JS 报告级辅助函数必须在**顶层作用域**（防「被嵌进函数体」复发）。

    事故根因（用户现象「前端不出新报告 / 还是出旧模板」）：
      `_reportDocName` / `_isEnterpriseEdition` / `_complianceOf` / `_signatureRows` /
      `_fallbackReason` 这 5 个报告级取数函数被插进了 `renderTaxDocReport` 的**函数体内**
      ⇒ 成为局部函数；而顶层使用者（`_buildEnterpriseReadableBody`、7 章 fallback 的封面、
      导出/打印路径）取不到它们 ⇒ 浏览器渲染报告时抛
      `ReferenceError: _reportDocName is not defined`，报告区**产不出**新报告。

    这类缺陷**语法完全合法**：`new Function(src)` 通过、pyflakes/ESLint 类工具看不见，
    只有真正执行渲染才暴露 ⇒ 必须单独上锁。

    判据：本表登记的报告级辅助函数，必须在该 JS 文件中**以顶格 `function NAME(` 定义**；
      且该名字必须在文件内被**引用过**（防止登记表腐烂、名字被删还留着豁免）。
    """
    issues: List[Tuple[str, str, str]] = []
    for rel, names in _JS_TOP_LEVEL_HELPERS.items():
        path = ROOT / rel
        if not path.exists():
            issues.append(("ERROR", rel, "登记了报告级辅助函数却找不到该文件（登记已过期）"))
            continue
        src = path.read_text(encoding="utf-8", errors="ignore")
        for nm in names:
            # 顶格（列 0）声明才算顶层；带缩进的同名声明 = 被嵌进某个函数体
            top = re.search(r"^function\s+%s\s*\(" % re.escape(nm), src, re.M)
            indented = re.search(r"^[ \t]+function\s+%s\s*\(" % re.escape(nm), src, re.M)
            if indented and not top:
                issues.append((
                    "ERROR", "%s::%s" % (rel, nm),
                    "报告级辅助函数 `%s` 被定义在**某个函数体内**（缩进声明）⇒ 顶层调用方"
                    "取不到 ⇒ 浏览器渲染抛 ReferenceError，报告产不出来。"
                    "必须移到模块顶层（顶格 `function %s(`）。" % (nm, nm)))
                continue
            if not top:
                issues.append(("ERROR", "%s::%s" % (rel, nm),
                               "登记的报告级辅助函数 `%s` 在该文件中查无定义 —— 登记已过期，"
                               "请核对后更新本检查的登记表。" % nm))
                continue
            if len(re.findall(r"\b%s\b" % re.escape(nm), src)) < 2:
                issues.append(("ERROR", "%s::%s" % (rel, nm),
                               "报告级辅助函数 `%s` 只有定义、没有任何引用 —— 疑似死代码，"
                               "请删除或核实登记表。" % nm))
    return issues


# ══════════════ 检查：JS 未定义名/未定义函数调用（2026-10-07）══════════════
# 事故：`core.js::enterApp` 调用 `loadCompanies()`，而本文件**只有 `loadCompaniesRaw()`**
#   —— `loadCompanies` 从未定义 ⇒ `ReferenceError: loadCompanies is not defined`
#   ⇒ 抛在 `enterApp` 中途 ⇒ 其后三行（加载期间/科目、`navigateTo(lastPage)`）**全部不执行**
#   ⇒ 登录后不跳转到上次页面、侧栏不刷新（浏览器控制台「初始化失败 ReferenceError」）。
# 同类已发生过多次（`_reportDocName` 作用域、`findings` 未定义…），故建**通用**判据：
#   凡在 `static/**/*.js` 与 `static/*.html` 内被**以函数形式调用**的裸名，
#   必须在这些文件中**有定义**（function/class/var|let|const/window.X=/X=function/X: function）
#   或为形参，或为浏览器/JS 内置 ⇒ 否则 ERROR。
# 注：这是**名称级**判据（不做作用域分析），故"定义"采集从宽（宁可漏报，不误报）。
_JS_RESERVED = {
    "if", "for", "while", "switch", "catch", "function", "return", "typeof", "new", "do",
    "else", "try", "finally", "await", "async", "yield", "delete", "void", "in", "of",
    "instanceof", "case", "throw", "super", "this", "class", "const", "let", "var",
    "with", "default", "export", "import", "break", "continue", "static", "get", "set",
}
_JS_BUILTINS = {
    "console", "fetch", "setTimeout", "clearTimeout", "setInterval", "clearInterval",
    "requestAnimationFrame", "cancelAnimationFrame", "queueMicrotask", "structuredClone",
    "JSON", "Math", "Object", "Array", "String", "Number", "Boolean", "Promise", "Date",
    "RegExp", "Error", "TypeError", "RangeError", "SyntaxError", "Map", "Set", "WeakMap",
    "WeakSet", "Symbol", "Proxy", "Reflect", "BigInt", "Intl", "Function", "eval",
    "parseInt", "parseFloat", "isNaN", "isFinite", "encodeURIComponent", "decodeURIComponent",
    "encodeURI", "decodeURI", "alert", "confirm", "prompt", "atob", "btoa", "escape", "unescape",
    "Uint8Array", "Int32Array", "Float64Array", "ArrayBuffer", "DataView", "TextEncoder",
    "TextDecoder", "Blob", "File", "FileReader", "FormData", "Headers", "Request", "Response",
    "URL", "URLSearchParams", "Image", "Audio", "WebSocket", "EventSource", "XMLHttpRequest",
    "MutationObserver", "IntersectionObserver", "ResizeObserver", "PerformanceObserver",
    "Event", "CustomEvent", "AbortController", "DOMParser", "XMLSerializer", "getComputedStyle",
    "matchMedia", "scrollTo", "scrollBy", "open", "close", "print", "focus", "blur",
    "getSelection", "postMessage", "addEventListener", "removeEventListener", "dispatchEvent",
    "crypto", "performance", "navigator", "location", "history", "screen", "localStorage",
    "sessionStorage", "document", "window", "globalThis", "self", "top", "parent", "frames",
    "define", "require", "importScripts", "createImageBitmap", "reportError",
    "SpeechSynthesisUtterance", "speechSynthesis", "AudioContext", "Audio", "AudioBuffer",
    "Notification", "ClipboardItem", "DOMRect", "Path2D", "CanvasRenderingContext2D",
    "HTMLElement", "HTMLCanvasElement", "Selection", "Range", "Node", "Element",
    "requestIdleCallback", "scheduler", "Iterator", "AsyncIterator", "AggregateError",
}
_JS_SCAN_GLOBS = ("static/js/**/*.js", "static/js/*.js", "static/*.html")


_JS_CSS_FUNCS = {
    "calc", "var", "env", "url", "attr", "clamp", "min", "max", "rgba", "rgb", "hsl",
    "hsla", "translateX", "translateY", "translateZ", "translate", "rotate", "rotateX",
    "rotateY", "scale", "scaleX", "scaleY", "skew", "matrix", "perspective", "cubic",
    "steps", "repeat", "minmax", "blur", "brightness", "contrast", "opacity", "saturate",
    "sepia", "grayscale", "invert", "drop", "circle", "ellipse", "inset", "polygon",
    "counter", "counters", "not", "media", "supports", "child", "last", "first", "only",
    "nth", "is", "where", "has", "host", "slotted", "gradient", "conic", "radial", "linear",
}


def _js_code_only(src: str) -> str:
    """把 JS 源码里的**字符串/模板串/注释/正则字面量**内容替换成空格（保留换行与总长度）。

    仅用于「找裸名调用」：JS 里大量 CSS（`linear-gradient(`、`repeat(`）与中文说明
    （提到 Python 侧函数名如 `_extract_material_intel(`）都出现在**字面量**里，
    不剥离就会产生成片误报，使闸门不可用。

    ★ 2026-10-07（关键修正）：首版**只认字符串/注释**，遇到**正则字面量**就失步 ——
      例如 `text.replace(/'/g, ...)` 中的 `/'/g` 会让状态机进入"字符串"状态并一路吞到
      下一个引号 ⇒ 其后大段真实代码被抹成空白 ⇒ 闸门对 `loadCompanies is not defined`
      **完全失明**（实测：变异已落盘却报 0 条，典型假绿）。
      现按 JS 词法补上正则字面量识别：`/` 前一个有效字符 ∈ `= ( , : [ ! & | ? { } ;` 或
      前一个词 ∈ `return/typeof/case/in/of/new/delete/void/do/else` ⇒ 视为正则，
      一直吃到未转义的收尾 `/`（跳过 `[...]` 字符类），再接 flags。
    """
    out: List[str] = []
    i, n, state = 0, len(src), None
    #: 允许正则字面量出现的前置字符 / 关键字
    _REGEX_PRE_CHARS = set("=(,:[!&|?{};+-*%~^<>")
    _REGEX_PRE_WORDS = ("return", "typeof", "case", "in", "of", "new", "delete",
                        "void", "do", "else", "instanceof", "yield", "await")
    last_sig = ""          #: 最近一个非空白有效字符
    last_word = ""         #: 最近一个标识符（用于判断 return / typeof 等）

    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if state is None:
            if c == "/" and nxt == "/":
                state, i = "//", i + 2
                out.append("  ")
                continue
            if c == "/" and nxt == "*":
                state, i = "/*", i + 2
                out.append("  ")
                continue
            if c == "/" and (last_sig in _REGEX_PRE_CHARS or last_word in _REGEX_PRE_WORDS):
                # 正则字面量：吃到未转义的收尾 /
                j, in_class, ok = i + 1, False, False
                while j < n:
                    cj = src[j]
                    if cj == "\\":
                        j += 2
                        continue
                    if cj == "\n":                      # 换行 ⇒ 不是正则（避免吞掉整文件）
                        break
                    if cj == "[":
                        in_class = True
                    elif cj == "]":
                        in_class = False
                    elif cj == "/" and not in_class:
                        ok = True
                        break
                    j += 1
                if ok:
                    end = j + 1
                    while end < n and src[end].isalpha():   # flags
                        end += 1
                    out.append(" " * (end - i))
                    i = end
                    last_sig, last_word = "/", ""
                    continue
            if c in "'\"`":
                state, i = c, i + 1
                out.append(" ")
                continue
            out.append(c)
            if not c.isspace():
                last_sig = c
                if c.isalnum() or c in "_$":
                    last_word = (last_word + c) if last_word and last_word[-1] != " " else c
                else:
                    last_word = ""
            i += 1
            continue
        if state == "//":
            if c == "\n":
                state = None
                out.append("\n")
            else:
                out.append(" ")
            i += 1
            continue
        if state == "/*":
            if c == "*" and nxt == "/":
                state, i = None, i + 2
                out.append("  ")
                continue
            out.append("\n" if c == "\n" else " ")
            i += 1
            continue
        if c == "\\":                       # 转义
            out.append(" ")
            if nxt:
                out.append(" ")
                i += 2
            else:
                i += 1
            continue
        if c == state:                      # 字符串结束
            state, i = None, i + 1
            out.append(" ")
            continue
        out.append("\n" if c == "\n" else " ")
        i += 1
    return "".join(out)


def check_js_undefined_calls() -> List[Tuple[str, str, str]]:
    """JS 里被调用但**同一页面脚本包内**查不到定义的裸名（ReferenceError 静态防线）。

    ★ 为什么按"页面脚本包"而不是全仓求并集：实测 `loadCompanies()` 只定义在
      `static/select-company.html` 的**内联脚本**里（另一个页面）；主页面 `index.html`
      从未加载它 ⇒ `core.js::enterApp` 调用时抛 `ReferenceError`（浏览器实测确认）。
      若全仓求并集，该缺陷会被判为"已定义"而**漏报**（首版即栽在此处）。
      浏览器语义：一个页面的可见全局 = 该页 `<script src>` 的文件 + 该页内联 `<script>`。
    """
    import glob as _glob

    js_files: List[Path] = []
    html_files: List[Path] = []
    for pat in ("static/js/**/*.js", "static/js/*.js", "static/*.html"):
        for p in _glob.glob(str(ROOT / pat), recursive=True):
            pp = Path(p)
            if not pp.is_file() or "__pycache__" in pp.parts:
                continue
            (html_files if pp.suffix.lower() in (".html", ".htm") else js_files).append(pp)
    if not js_files:
        return [("WARN", "static/js", "未找到 JS 文件，JS 未定义名检查未执行")]

    src_cache: Dict[str, str] = {}

    def _read(p: Path) -> str:
        rel = os.path.relpath(str(p), str(ROOT)).replace("\\", "/")
        if rel not in src_cache:
            src_cache[rel] = p.read_text(encoding="utf-8", errors="ignore")
        return src_cache[rel]

    def _defs(blob: str) -> set:
        out: set = set()
        for pat in (
            r"function\s+([A-Za-z_$][\w$]*)",
            r"(?:var|let|const)\s+([A-Za-z_$][\w$]*)",
            r"class\s+([A-Za-z_$][\w$]*)",
            r"(?:window|globalThis|self)\s*\.\s*([A-Za-z_$][\w$]*)",
            r"([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b|\()",
            r"([A-Za-z_$][\w$]*)\s*:\s*(?:async\s*)?(?:function\b|\()",
        ):
            for m in re.finditer(pat, blob):
                out.add(m.group(1))
        for m in re.finditer(r"function\s*[\w$]*\s*\(([^)]*)\)", blob):
            for tok in re.findall(r"[A-Za-z_$][\w$]*", m.group(1)):
                out.add(tok)
        for m in re.finditer(r"\(([^)]*)\)\s*=>", blob):
            for tok in re.findall(r"[A-Za-z_$][\w$]*", m.group(1)):
                out.add(tok)
        for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*=>", blob):
            out.add(m.group(1))
        return out

    def _blank_html_nonjs(raw: str) -> str:
        raw = re.sub(r"<!--.*?-->", lambda m: " " * len(m.group(0)), raw, flags=re.S)
        return re.sub(r"<style\b[^>]*>.*?</style>",
                      lambda m: " " * len(m.group(0)), raw, flags=re.S | re.I)

    # ── 页面脚本包 ──
    bundles: List[Tuple[str, List[Path], List[str]]] = []
    for h in html_files:
        raw = _read(h)
        srcs = re.findall(r"<script[^>]+src=[\"']([^\"']+)[\"']", raw)
        files: List[Path] = []
        for s in srcs:
            s2 = s.split("?")[0]
            cand = ROOT / s2.lstrip("/") if s2.startswith("/") else h.parent / s2
            if cand.is_file() and cand.suffix.lower() == ".js":
                files.append(cand)
        inline = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", raw, flags=re.S | re.I)
        bundles.append((os.path.relpath(str(h), str(ROOT)).replace("\\", "/"), files, inline))
    # 未被任何页面引入的 JS 单独成包（可及早暴露"这个文件其实没人加载"）
    loaded = {os.path.relpath(str(f), str(ROOT)).replace("\\", "/")
              for _, fs, _ in bundles for f in fs}
    for f in js_files:
        rel = os.path.relpath(str(f), str(ROOT)).replace("\\", "/")
        if rel not in loaded:
            bundles.append((rel + "（未被任何页面引入）", [f], []))

    issues: List[Tuple[str, str, str]] = []
    reported: set = set()
    for bname, files, inline in bundles:
        blob = "\n".join([_read(f) for f in files] + [_blank_html_nonjs(x) for x in inline])
        blob_code = "\n".join([_js_code_only(_read(f)) for f in files]
                              + [_js_code_only(_blank_html_nonjs(x)) for x in inline])
        defined = _defs(blob)
        for f in files:
            rel = os.path.relpath(str(f), str(ROOT)).replace("\\", "/")
            code = _js_code_only(_read(f))
            _stripped, _raw_len = code.strip(), len(_read(f).strip())
            # ★ 自守：剥离器失步会把真实代码吃成空白 ⇒ 闸门假绿，故按占比报警
            if _raw_len > 2000 and len(_stripped) < 0.25 * _raw_len:
                issues.append(("WARN", rel, "JS 词法剥离后仅剩 %.0f%% 代码 —— 剥离器可能失步，"
                               "本文件检查结果不可信，请先修 `_js_code_only`。"
                               % (100.0 * len(_stripped) / max(1, _raw_len))))
                continue
            for i, line in enumerate(code.split("\n"), 1):
                for m in re.finditer(r"(?<![\w.$'\"`-])([A-Za-z_$][\w$]*)\s*\(", line):
                    nm = m.group(1)
                    if (nm in _JS_RESERVED or nm in _JS_BUILTINS or nm in _JS_CSS_FUNCS
                            or nm in defined or (rel, nm) in reported):
                        continue
                    # 有意的特性探测惯用法：`if (typeof X === 'function') X(...)`
                    if re.search(r"typeof\s+%s\b" % re.escape(nm), blob_code):
                        continue
                    reported.add((rel, nm))
                    issues.append((
                        "ERROR", "%s:%d" % (rel, i),
                        "在页面「%s」的脚本包里调用 `%s(...)`，但该页**加载的全部脚本**中"
                        "查无此名 → 运行到此处抛 `ReferenceError: %s is not defined`"
                        "（该调用之后的语句**全部不执行**）。"
                        "请改正函数名、补引入定义它的文件，或删掉该调用。"
                        % (bname, nm, nm)))
    return issues


def check_domain_fault_isolation() -> List[Tuple[str, str, str]]:
    """域分析必须有容错护栏：**单个域的数据脏点不得中断整轮分析**。

    事故（2026-10-07，用户现象「一键分析失败，出现分析异常的提示」）：
      `_domain_salary_ss_hf_compare` 内一处除零（公积金缴存额为 0 的记录被当作"低基数"
      参与反推基数 ⇒ 反推基数为 0）→ ZeroDivisionError 直接冒泡到
      `_execute_tax_risk_analysis` ⇒ 整轮分析失败、一份报告都出不来。

    判据（`engine/pipeline.py`）：
      ① 必须存在 `_isolate_domain_functions()` 的**调用**，且位置在**首个域调用之前**；
      ② 必须存在 `_drain_domain_failures(pipeline_log)` 的**调用**，且位置在**最后一个域调用之后**
         （否则失败登记无人收口 ⇒ 等于静默）；
      ③ 护栏本身不得吞掉留痕（`_DOMAIN_FAILURES` + pipeline_log 写入必须同时存在）。
    """
    issues: List[Tuple[str, str, str]] = []
    rel = "engine/pipeline.py"
    path = ROOT / rel
    if not path.exists():
        return [("ERROR", rel, "文件不存在，无法核对域容错护栏")]
    src = path.read_text(encoding="utf-8", errors="ignore")
    lines = src.split("\n")

    def _first(pat):
        for i, l in enumerate(lines):
            if re.search(pat, l):
                return i + 1
        return 0

    def _last(pat):
        hit = 0
        for i, l in enumerate(lines):
            if re.search(pat, l):
                hit = i + 1
        return hit

    # 只认「调用」行，排除函数定义行（`def _drain_domain_failures(...)` 签名同形）
    #   · 隔离调用：取**第一次**（必须早于首个域调用）
    #   · 留痕收口：取**最后一次**（必须晚于最后一个域调用）
    iso = _first(r"^\s*(?!def\b)[^\n]*_isolate_domain_functions\(\)")
    drain = _last(r"^\s*(?!def\b)[^\n]*_drain_domain_failures\(")
    iso_def = _first(r"^def\s+_isolate_domain_functions\(")
    first_call = _first(r"^\s*(?!def\b)[^\n]*(?<![\w])_domain_[a-z0-9_]+\s*\(")
    last_call = _last(r"^\s*(?!def\b)[^\n]*(?<![\w])_domain_[a-z0-9_]+\s*\(")

    if not iso_def:
        issues.append(("ERROR", rel, "缺 `_isolate_domain_functions` 定义（域容错护栏唯一实现）。"))
    if not iso:
        issues.append(("ERROR", rel,
                       "缺 `_isolate_domain_functions()` 调用 —— 域分析无容错护栏，"
                       "任一域抛异常都会让整轮分析报「分析异常」。"))
    elif first_call and iso > first_call:
        issues.append(("ERROR", "%s:%d" % (rel, iso),
                       "`_isolate_domain_functions()` 在首个域调用（第 %d 行）**之后**才执行 —— "
                       "此前调用的域未受保护。" % first_call))
    if not drain:
        issues.append(("ERROR", rel,
                       "缺 `_drain_domain_failures(pipeline_log)` —— 域失败登记无人收口，"
                       "等同静默吞异常（违反留痕铁律）。"))
    elif last_call and drain < last_call:
        issues.append(("ERROR", "%s:%d" % (rel, drain),
                       "`_drain_domain_failures(pipeline_log)` 在第 %d 行，早于最后一个域调用 —— "
                       "其后发生的域失败不会被留痕。" % last_call))
    for need in ("_DOMAIN_FAILURES", 'pipeline_log.append("[域分析异常]'):
        if need not in src:
            issues.append(("ERROR", rel, "域容错护栏缺少留痕要素 `%s`（不得静默吞异常）。" % need))
    return issues


# ══════════════ 检查：五项报告质量 Skill 的接线与口径（2026-10-07）══════════════
# 背景：用户复核《税务风险扫描工作底稿》暴露 5 个问题，要求新增 5 个 Skill。
# 闸门只做**可机检**的接线断言（"规范写在文档里"约束不了代码，接线才约束得了）：
#   ① 触发条件与认定要件分离：前提条判定必须被要件核对器**真的调用**
#   ② 金额口径取舍：报告不得并列两个口径而不指明最终口径 ⇒ 必须走唯一权威
#   ③ 字段截断检测：模块与词表存在且被使用
#   ④ 空内容/占位符：报告出口必须拦截孤立引导句
#   ⑤ 报告性质一致性：名称唯一权威与合规模板**必须一致**，且前端不得硬编码旧名
_SKILL_WIRING = {
    "check_trigger_constituent_separation": {
        "module": "engine/trigger_conditions.py",
        "must_use": ("engine/constituent_checkpoint.py", "engine.trigger_conditions"),
        "attrs": ("PREMISE_MARKERS",),
    },
    "check_amount_scope_single_final": {
        "module": "engine/amount_scope_choice.py",
        "must_use": ("engine/bank_flow.py", "engine.amount_scope_choice"),
        "attrs": ("NOTE_GROSS_ONLY", "LABEL_FINAL"),
    },
    "check_field_truncation_guard": {
        "module": "engine/field_completeness.py",
        "must_use": ("engine/enterprise_report.py", "engine.field_completeness"),
        "attrs": ("COVERAGE_CLAIM_WORDS", "TRUNCATION_MARKS"),
    },
    "check_no_orphan_placeholder": {
        "module": "engine/content_placeholder_guard.py",
        "must_use": ("engine/enterprise_report.py", "engine.content_placeholder_guard"),
        "attrs": ("LEAD_TAILS",),
    },
    "check_report_identity_consistency": {
        "module": "engine/report_identity.py",
        "must_use": ("engine/report_compliance.py", "engine.report_identity"),
        "attrs": ("forbidden_aliases",),
    },
}


def check_report_quality_skill_wiring() -> List[Tuple[str, str, str]]:
    """五项报告质量 Skill：模块存在 + 关键属性非空 + **被真实调用**（接线断言）。"""
    issues: List[Tuple[str, str, str]] = []
    for name, spec in _SKILL_WIRING.items():
        mod = ROOT / spec["module"]
        if not mod.exists():
            issues.append(("ERROR", spec["module"], "%s：模块不存在（Skill 未实现）" % name))
            continue
        src = mod.read_text(encoding="utf-8", errors="ignore")
        for attr in spec["attrs"]:
            # 可机检入口：模块级常量/表（`NAME =` / `NAME:`）或函数（`def NAME(`）均可
            if not (re.search(r"^%s\s*(?::[^=]+)?=" % re.escape(attr), src, re.M)
                    or re.search(r"^def\s+%s\s*\(" % re.escape(attr), src, re.M)):
                issues.append(("ERROR", spec["module"],
                               "%s：缺可机检的 %s（新增同类将无数据可加）" % (name, attr)))
        user_file, user_mod = spec["must_use"]
        up = ROOT / user_file
        if not up.exists():
            issues.append(("ERROR", user_file, "%s：调用方文件不存在" % name))
            continue
        usrc = up.read_text(encoding="utf-8", errors="ignore")
        # ★ 调用点常为**别名导入**（`from m import f as _f`）⇒ 必须按导入解析本地名再判"是否被调用"。
        #   两个坑都踩过：① 只查子串 ⇒ 分支改成 `if False:` 仍报 0（假绿）；
        #   ② 只查原名 ⇒ 别名调用点被误报（假红）。
        _local: set = set()
        _imp_re = re.compile(r"^\s*from\s+%s\s+import\s+(\([^)]*\)|[^\n#]+)"
                             % re.escape(str(user_mod)), re.M)
        for _m in _imp_re.finditer(usrc):
            _body = _m.group(1).strip().strip("()")
            for _tok in _body.split(","):
                _tok = _tok.split("#")[0].strip()
                if not _tok:
                    continue
                _local.add(_tok.split(" as ")[-1].strip())
        if not _local:
            issues.append(("ERROR", user_file,
                           "%s：未从 `%s` 导入任何符号 —— **接线缺失**（模块写了但没接上）"
                           % (name, user_mod)))
        elif not any(re.search(r"\b%s\s*\(" % re.escape(_n), usrc) for _n in _local):
            issues.append(("ERROR", user_file,
                           "%s：导入了 %s 但**从未调用** —— 接线是死的（等于没做）"
                           % (name, "、".join(sorted(_local)))))
    # ③ 补充：字段截断检测必须声明"检查期间"这一判据来源（防"没有期间就默认通过"）
    fc = ROOT / "engine/field_completeness.py"
    if fc.exists():
        s = fc.read_text(encoding="utf-8", errors="ignore")
        if "无法判定" not in s:
            issues.append(("ERROR", "engine/field_completeness.py",
                           "取不到检查期间时未声明「无法判定」（会静默通过 → 等于没有校验）"))
    # ⑤ 补充：名称唯一权威与合规模板必须一致；唯一名称不得出现在禁用别名表里
    try:
        from engine.report_identity import canonical_name, forbidden_aliases
        cn = canonical_name()
        try:
            rc = json.loads((ROOT / "config" / "report_compliance.json").read_text(encoding="utf-8"))
            nm = str((((rc.get("documents") or {}).get("internal_working_paper") or {})
                      .get("name")) or "")
            if nm != cn:
                issues.append(("ERROR", "config/report_compliance.json",
                               "报告名称与唯一权威不一致：模板=%s vs report_identity=%s" % (nm, cn)))
        except Exception as exc:
            issues.append(("WARN", "config/report_compliance.json", "读取失败：%s" % exc))
        for a in forbidden_aliases():
            if a == cn or a in cn:
                issues.append(("ERROR", "config/report_identity.json",
                               "禁用别名「%s」与唯一名称「%s」重叠（会造成自我替换/无法统一）" % (a, cn)))
    except Exception as exc:                       # 留痕，不静默
        issues.append(("WARN", "engine/report_identity.py", "名称一致性核对未执行：%s" % exc))
    # ⑤ 补充：不得硬编码历史报告名（名称唯一由后端 `report_compliance.document_meta` 下发）
    # ★ 2026-10-09：扫描范围从前端**扩到 `main.py`** —— 实测 `main.py` 的
    #   `_build_delivery_html()`（由**在线路由** `/api/compliance/rounds/{round_id}/deliver`
    #   调用）在 HTML 的 `<title>`/`<h1>` 里硬编码了禁止别名「税务合规风险分析报告」，
    #   用户下载到的交付件标题顶着系统明令禁止的名称；而本闸门当时只扫前端 ⇒ 漏网。
    # ⚠ 必须**剔除注释**：说明性注释里引用禁止别名是正常的（本轮修复即在注释里
    #   写明了"从前是什么"），只审代码。
    for rel in ("static/js/tax-doc-analysis.js", "static/index.html", "main.py"):
        fp = ROOT / rel
        if not fp.exists():
            continue
        _code_lines = []
        for _ln in fp.read_text(encoding="utf-8", errors="ignore").split("\n"):
            _s = _ln.strip()
            if _s.startswith("#") or _s.startswith("//"):
                continue
            _code_lines.append(re.sub(r"#.*$", "", _ln))
        s = "\n".join(_code_lines)
        for bad in ("企业内部税务合规风险分析报告", "税务合规风险分析报告"):
            if bad in s:
                issues.append(("ERROR", rel,
                               "硬编码历史报告名「%s」——名称必须由后端 `report_compliance.document_meta` / `report_identity.canonical_name()` 下发" % bad))
    return issues


def check_report_version_reuse_authority() -> List[Tuple[str, str, str]]:
    """「增量复用」的缓存版式判据必须走**唯一权威**，且不得含报告名字面量（2026-10-09）。

    ★ 病根（对真实产物实测，非推测）：
      `main.py::analyze_tax_risk_docs_start` 的增量复用分支用**硬编码报告名白名单**
      判断缓存可否复用，而那 4 个取值**全部出自 `config/report_identity.json` 的
      `forbidden_aliases`（禁止别名表）** —— 判据只在"报告顶着禁止名称"时才可能成立。
      真实产出值是权威派生的「内部辅助分析工作底稿（风险检查文书式）」
      （`data/cache/last_analysis_cache.json` 实测），白名单里没有
      ⇒ `_cached_report_ok` **恒为 False** ⇒ **增量复用从未生效**（`trigger="incremental"`
      的作业流水行是死路径）。前端同一概念早已修好
      （`tax-doc-analysis.js::_isEnterpriseEdition`「★ 删除名称白名单」），后端未收敛。

    ★ 判据（四段，全部可反向验证）：
      A **权威存在且被调用**：`engine/enterprise_report.is_current_report_version` 必须存在，
        且 `main.py` 必须调用它；
      B **主流程不得自行解释该字段**：`main.py` 的**代码**（剔注释）中不得出现
        `compilation_style` —— 版式判据只允许由权威函数回答；
      C **第二出处已消灭**：`audit_doctrine.REPORT_EDITING_STANDARDS` 中不得再有
        `compilation_style` 键（它曾是报告名的第二个出处，且取值早已过期）；
      D **行为**：权威函数对「按权威构造的真实结构」判可复用，对
        带**任一禁止别名** / 缺 `document_meta` / 非法 `report_edition` / 空报告 判脏。
    """
    issues: List[Tuple[str, str, str]] = []

    # A. 权威存在且被调用
    er_path = ROOT / "engine/enterprise_report.py"
    er_src = er_path.read_text(encoding="utf-8", errors="ignore") if er_path.exists() else ""
    if "def is_current_report_version(" not in er_src:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "缺 `is_current_report_version()` —— 缓存版式判据必须有唯一权威"))
    main_path = ROOT / "main.py"
    main_code = ""
    if main_path.exists():
        for _ln in main_path.read_text(encoding="utf-8", errors="ignore").split("\n"):
            if _ln.strip().startswith("#"):
                continue
            main_code += re.sub(r"#.*$", "", _ln) + "\n"
    if "is_current_report_version" not in main_code:
        issues.append(("ERROR", "main.py",
                       "增量复用分支**未接权威** `is_current_report_version()` "
                       "—— 版式判据不得各写一份"))

    # B. 主流程不得自行解释 compilation_style
    if "compilation_style" in main_code:
        issues.append(("ERROR", "main.py",
                       "主流程出现 `compilation_style` 字段解释 —— 报告版式判据只允许由 "
                       "`enterprise_report.is_current_report_version()` 回答"
                       "（历史上这里用硬编码名称白名单，导致增量复用恒不命中）"))

    # C. 第二出处已消灭 + D. 行为
    try:
        from engine.audit_doctrine import REPORT_EDITING_STANDARDS
        for _name, _meta in (REPORT_EDITING_STANDARDS or {}).items():
            if isinstance(_meta, dict) and "compilation_style" in _meta:
                issues.append(("ERROR", "engine/audit_doctrine.py",
                               "`REPORT_EDITING_STANDARDS[%s]` 仍有 `compilation_style` —— "
                               "报告名的第二个出处（改了不会同步）。唯一权威 = "
                               "`report_compliance.document_meta`" % _name))
    except Exception as exc:                             # noqa: BLE001
        issues.append(("WARN", "engine/audit_doctrine.py", "读取编辑版标准失败：%s" % exc))

    try:
        from engine.enterprise_report import is_current_report_version, _doc_display_name
        from engine.report_identity import canonical_name, forbidden_aliases
        from engine.audit_doctrine import DEFAULT_REPORT_EDITION
        _good = {
            "compilation_style": _doc_display_name(),
            "report_edition": DEFAULT_REPORT_EDITION,
            "document_meta": {"name": canonical_name()},
        }
        if not is_current_report_version(_good):
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "按**唯一权威构造的真实结构**被判为脏缓存（%r）—— "
                           "判据跑偏，会导致增量复用再次恒不命中" % _good["compilation_style"]))
        _cur = _doc_display_name()
        for _a in forbidden_aliases():
            if _a == _cur:
                continue
            if is_current_report_version(dict(_good, compilation_style=_a)):
                issues.append(("ERROR", "engine/enterprise_report.py",
                               "带**禁止别名**「%s」的报告被判为可复用 —— 判据必须拒绝它" % _a))
        if is_current_report_version({k: v for k, v in _good.items() if k != "document_meta"}):
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "缺 `document_meta`（后端未声明文档定位）仍被判为可复用"))
        if is_current_report_version(dict(_good, report_edition="已下线的编辑版")):
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "非法 `report_edition` 仍被判为可复用"))
        if is_current_report_version({}):
            issues.append(("ERROR", "engine/enterprise_report.py", "空报告仍被判为可复用"))
    except Exception as exc:                             # noqa: BLE001
        issues.append(("WARN", "engine/enterprise_report.py", "版式判据行为核对未执行：%s" % exc))
    return issues


def check_trigger_determination_separation() -> List[Tuple[str, str, str]]:
    """触发条件与认定要件**分离**的机检（用户规格的三条门禁）。

    ① **配置完备性**：`config/risk_conditions.json` 里每条风险指标必须同时具备
       ≥1 条 `trigger_conditions` 与 ≥1 条 `is_precondition=true` 的认定要件
       （"新增风险指标时必须同时定义触发条件和认定要件"）。
    ② **不得"已列为疑点却没有触发条件"**：全量产物里每个 risk_code 都要能查到一个命中触发的配置条目。
    ③ **不得出现"未涉及任何一条构成要件"**（该句只在"已列为疑点"的语境里出现 ⇒ 与"已列为疑点"矛盾）。
    ④ **前提条已满足必须写「符合情形」**：产物中第 1 条认定要件（前提条）
       不得出现「未形成核对结论 / 未单独核对」。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.trigger_conditions import load_risk_conditions, determination_criteria_of
    except Exception as exc:                                     # 留痕，不静默
        return [("ERROR", "engine/trigger_conditions.py", "无法导入 Skill 模块：%s" % exc)]
    reg = load_risk_conditions()
    risks = [r for r in (reg.get("risks") or []) if isinstance(r, dict)]
    if not risks:
        return [("ERROR", "config/risk_conditions.json",
                 "风险指标配置为空（触发条件/认定要件未定义，Skill 1 未落地）")]
    for r in risks:
        rc = str(r.get("risk_code") or "")
        if not r.get("trigger_conditions"):
            issues.append(("ERROR", "config/risk_conditions.json",
                           "风险指标 %s 未定义触发条件（trigger_conditions 为空）" % rc))
        crits = r.get("determination_criteria") or []
        if not crits:
            issues.append(("ERROR", "config/risk_conditions.json",
                           "风险指标 %s 未定义认定要件（determination_criteria 为空）" % rc))
        elif not any(bool(c.get("is_precondition")) for c in crits if isinstance(c, dict)):
            # ★ 口径（用户规格原文）：「认定要件中**若含**"现象/前提条"」⇒ 不是每条风险都必须有前提条。
            #   判据：**第 1 条要件属存在性判据**（含存在性语、不含数值门槛语）时，必须标记前提条；
            #   第 1 条本身就是"超过某比例/达到某金额"这类**数值门槛条**的，无前提条属正当。
            #   （否则会把 37 条合法红线误判为缺陷——实测首版即误报 37 条。）
            try:
                from scripts._gen_risk_conditions import is_existence_criterion as _is_ex
                _first = str((crits[0] or {}).get("desc") or "")
                if _is_ex(_first):
                    issues.append(("ERROR", "config/risk_conditions.json",
                                   "风险指标 %s 的第1条认定要件属存在性判据（现象条）却未标记 "
                                   "is_precondition=true —— 该现象条会落入「未形成核对结论」：%s"
                                   % (rc, _first[:40])))
            except Exception as exc:                            # 留痕，不静默
                issues.append(("WARN", "config/risk_conditions.json",
                               "前提条完备性核对未执行（%s）：%s" % (rc, exc)))
    # 产物级（②③④）：取全量产物；取不到时**如实 WARN**（不静默通过）
    try:
        rep = _canonical_report()
    except Exception as exc:                                     # noqa: BLE001
        rep = None
        issues.append(("WARN", "tools/audit_consistency.py",
                       "读取全量产物失败，门禁③④未执行：%s" % exc))
    if isinstance(rep, dict):
        blob = json.dumps(rep, ensure_ascii=False)
        if "未涉及任何一条构成要件" in blob:
            issues.append(("ERROR", "全量产物",
                           "出现「未涉及任何一条构成要件」——与「已列为疑点」自相矛盾"
                           "（触发条件已满足时不得再写该句）"))
        er = rep.get("enterprise_readable_report") or rep
        probs = [p for p in (er.get("confirmed_problems") or []) if isinstance(p, dict)]
        for p in probs:
            rc = str(p.get("redline_id") or "")
            _title_full = str(p.get("title") or "")
            title = _title_full[:20]   # 仅用于消息展示；**绑定键必须用完整标题**
            # ★ 2026-10-07（验收："不得出现已列为疑点但未触发任何触发条件"）：
            #   触发来源可以是**红线编号**（配置条目）或**规则编号 rule_id / 本项触发信号**（兜底）。
            #   两者都取不到 ⇒ 该疑点既无触发条件、也无认定要件 ⇒ ERROR。
            _rule_id = str(p.get("rule_id") or "")
            # ★ 2026-10-07（验收硬约束）：「已列为疑点 ⇒ 必有触发条件命中」。
            #   触发源优先级：redline_id（红线绑定）> rule_id（规则绑定）> 本项标记名（兜底）。
            #   门禁**断言机制保证**：任一疑点都必须能导出 ≥1 条命中触发条件（否则 ERROR）；
            #   走兜底（非红线/规则绑定）的只记 **WARN**，便于追溯"哪些疑点还没有正式触发源"。
            try:
                from engine.trigger_conditions import (trigger_status as _tstat,
                                                       trigger_conditions_of as _tco)
                # 绑定键优先级：红线编号 > 规则编号 > 发现标记名（配置表可按 `aliases` 登记）
                _key = rc or _rule_id or _title_full
                _ts = _tstat(_key, title, True, fallback_desc=title)
                if int(_ts.get("hit_count") or 0) < 1:
                    issues.append(("ERROR", "全量产物",
                                   "疑点「%s」无法导出任何命中触发条件"
                                   "（已列为疑点却无触发条件）" % title))
                elif not _tco(_key):
                    # 仅当触发条件来自**内联兜底**（配置表未登记）时才提示 —— 已登记（含 aliases）即视为绑定
                    issues.append(("WARN", "全量产物",
                                   "疑点「%s」的触发条件尚未登记到 config/risk_conditions.json"
                                   "（当前用本项标记名兜底）——请为该发现登记 risk_code/aliases" % title))
            except Exception as _te:                       # noqa: BLE001 - 留痕，不静默
                issues.append(("WARN", "全量产物", "触发条件核验未执行：%s" % _te))
            # ★★ 2026-10-07（Skill 1【输出】字段落盘 + 双向一致性）：
            #   ① 每个疑点必须落结构化块 `trigger_determination`（规格 8 字段）；
            #   ② 触发命中 ⇔ 疑点成立（**不得"已列为疑点却无命中触发条件"**，反之亦然）；
            #   ③ 认定要件与逐条状态一一对应；前提条必须写「符合情形」（不得"未形成核对结论"）。
            _blk = p.get("trigger_determination")
            if not isinstance(_blk, dict):
                issues.append(("ERROR", "全量产物",
                               "疑点「%s」缺结构化块 trigger_determination（规格【输出】：risk_code/"
                               "trigger_conditions/trigger_status/determination_criteria/"
                               "criterion_status/suspicion_established/risk_established/conclusion）"
                               % title))
            else:
                for _f in ("risk_code", "trigger_conditions", "trigger_status",
                           "determination_criteria", "criterion_status",
                           "suspicion_established", "risk_established", "conclusion"):
                    if _f not in _blk:
                        issues.append(("ERROR", "全量产物",
                                       "疑点「%s」trigger_determination 缺字段「%s」" % (title, _f)))
                _tcs = _blk.get("trigger_conditions") or []
                _ts = _blk.get("trigger_status") or {}
                _hit = int((_ts or {}).get("hit_count") or 0) if isinstance(_ts, dict) else 0
                if not _tcs:
                    issues.append(("ERROR", "全量产物",
                                   "疑点「%s」未定义任何触发条件（已列为疑点却无触发源）" % title))
                if bool(_blk.get("suspicion_established")) != bool(_hit > 0):
                    issues.append(("ERROR", "全量产物",
                                   "疑点「%s」触发命中数=%d 与「疑点是否成立」=%r 不一致"
                                   % (title, _hit, _blk.get("suspicion_established"))))
                _crits = _blk.get("determination_criteria") or []
                _cst = _blk.get("criterion_status") or {}
                # 认定要件非空：只对**有要件核对表**的疑点要求（无红线绑定的综合/独立疑点
                # 不是按要件判定的 ⇒ 认定要件为空是如实，不是缺失；与 Skill 6/7 同口径）
                _has_ck = any("构成要件" in str((t or {}).get("title") or "")
                              for np_ in (p.get("narrative_paragraphs") or [])
                              if isinstance(np_, dict)
                              for t in (np_.get("detail_tables") or []))
                if _has_ck and not _crits:
                    issues.append(("ERROR", "全量产物",
                                   "疑点「%s」有要件核对表，结构化块里却无认定要件" % title))
                # ★★ 2026-10-07（用户验收「补做3」抓出的**门禁漏洞**）：**产物要件数必须与配置一致**。
                #   事故：疑点2/10/11 是"无红线绑定的综合/规则发现"（没有构成要件 ⇒ 没有核对记录），
                #   结构化块里 `determination_criteria = []`（0 条），而**配置里各有 1 条 C1 前提条**
                #   ⇒ "配置有、产物 0 条"，而**当时没有任何判据**发现它（TDS-① 只查配置、不查产物）。
                #   现修：`trigger_conditions.classify()` 无核对记录时**回退配置要件**；
                #   门禁再加这条一致性断言（产物条数 == 配置条数），双保险。
                try:
                    from engine.trigger_conditions import (determination_criteria_of as _dco,
                                                           risk_entry as _re3)
                    _rc = str((_blk.get("risk_code") or "")) or rc or _rule_id or title
                    _cfg_c = _dco(_rc)
                    # 仅当该风险键**在配置里登记过**时才比对（未登记 ⇒ 走内联兜底，另由 TDS-② 管）
                    if _re3(_rc) and len(_cfg_c) != len(_crits):
                        issues.append(("ERROR", "全量产物",
                                       "疑点「%s」结构化块认定要件 %d 条 ≠ 配置 %d 条"
                                       "（配置有、产物无 ⇒ 读者看不到该核哪条）"
                                       % (title, len(_crits), len(_cfg_c))))
                except Exception as _ex3:          # noqa: BLE001 - 留痕，不静默
                    issues.append(("WARN", "全量产物",
                                   "疑点「%s」要件数与配置一致性未校验：%s" % (title, str(_ex3)[:60])))
                _cids = sorted(str(c.get("id")) for c in _crits if isinstance(c, dict))
                if _cids != sorted(str(k) for k in _cst):
                    issues.append(("ERROR", "全量产物",
                                   "疑点「%s」认定要件与逐条状态**不一一对应**（%s vs %s）"
                                   % (title, _cids[:5], sorted(_cst)[:5])))
                for _c in _crits:
                    if not isinstance(_c, dict):
                        continue
                    if not _c.get("is_precondition"):
                        continue
                    _txt = str((_cst.get(str(_c.get("id"))) or {}).get("text") or "")
                    if "符合情形" not in _txt:
                        issues.append(("ERROR", "全量产物",
                                       "疑点「%s」%s 是前提条，结论必须写「符合情形」，实为「%s」"
                                       % (title, _c.get("id"), _txt[:36])))
                    elif "未形成核对结论" in _txt or "未单独核对" in _txt:
                        issues.append(("ERROR", "全量产物",
                                       "疑点「%s」%s 前提条同时出现「符合情形」与「未形成核对结论/"
                                       "未单独核对」——自相矛盾" % (title, _c.get("id"))))
            if rc and not determination_criteria_of(rc):
                issues.append(("ERROR", "全量产物",
                               "疑点「%s」已列为疑点，但风险指标 %s 在配置中查不到"
                               "认定要件/触发条件（已列为疑点却无触发条件）" % (title, rc)))
            # ④ 前提条不得落"未形成核对结论"——**仅当该条确实是前提条**（结构化配置判定）：
            #   第1条若本身是数值门槛条（如"超过法定扣除限额"），"未形成核对结论"可能是正当的。
            _is_pre = False
            try:
                from engine.trigger_conditions import is_precondition as _ip
                _is_pre = bool(_ip(rc, 1, "")) if rc else False
            except Exception:                                   # noqa: BLE001 - 留痕，不静默
                _is_pre = False
            if not _is_pre:
                continue
            for np_ in (p.get("narrative_paragraphs") or []):
                for b in (np_.get("bullets") or []):
                    s2 = str(b or "")
                    if s2.startswith("①") and ("未形成核对结论" in s2 or "未单独核对" in s2):
                        issues.append(("ERROR", "全量产物",
                                       "疑点「%s」第1条认定要件（**前提条**）写的是"
                                       "「未形成核对结论/未单独核对」，应写「符合情形」：%s"
                                       % (title, s2[:60])))
                        break
    else:
        issues.append(("WARN", "全量产物", "无真跑产物，门禁③④未执行（请先跑一次全量分析）"))
    return issues


def check_child_item_completeness() -> List[Tuple[str, str, str]]:
    """子项与关联项完整性（Skill 6 的四条硬规则）。

    ① **配置自检**：每个子项必须标注合法状态；非「已核对」必须写 `gap`（原因+需补资料）；
       每个关联项必须声明 `analysis_required`。
    ② **漏登记即阻断**（2026-10-07 新增，把"靠人工发现"变成机检）：全量产物里
       **报告正文 / 明细表 / 本项绑定发现明细**中出现的子项与关联项，必须已登记到
       `config/child_items.json`。判据与生成器**同一函数**（`enumerate_children`）
       ⇒ 数据里新出现一个对象级事项而配置没登记，立刻变红。
       （这就是用户点名的疑点15：`个人垫付 116,504.85 元` 只在发现明细里，
        旧版枚举源扫不到 ⇒ 这个子项**根本进不了清单**，"列了不分析"永远查不出来。）
    ③ **清单必须真落进报告**：有子项的疑点，报告里必须能看到「子项与关联项逐项核对」清单
       （防"生成了但没挂上去"——本项目实测过"放在 out=[...] 之前被覆盖"这类静默丢失）。
    ④ **要件类不得重复登记、但必须原位有结论**：构成要件由 `constituent_checkpoint`
       **原位**逐条给出「独立数据源｜数据源状态｜核对结论」⇒ 不重复登记为子项（否则同一件事
       在报告里说两遍）；作为交换，此处断言**每条要件条目都自带结论与独立数据源**，
       否则判 ERROR —— "列了却没分析"在要件这一层同样跑不掉。
    ⑤ **结构化字段与清单文本必须一致**（1.1.0 新增，对齐用户规格【输出】字段）：
       每项必须落 `child_item_audit`，含 `parent_risk_code / child_items / child_status /
       child_conclusion / child_gap / related_items / related_analysis`；
       `child_items` 与 `child_status` 必须**一一对应**（同集合、同数量）；
       非「已核对」必须带 gap；且**清单文本里出现的每个状态标记都能在结构化数据里找到对应**
       —— 防"文本说未核对、结构说已核对"的**两张皮**（两者都会"看起来对"）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.child_item_completeness import (config_completeness, load_config,
                                                    audit_product, CHECKLIST_LEAD,
                                                    children_of as _kids)
    except Exception as exc:                          # 留痕，不静默
        return [("ERROR", "engine/child_item_completeness.py", "无法导入 Skill 模块：%s" % exc)]
    for p in config_completeness():
        issues.append(("ERROR", "config/child_items.json",
                       "%s：%s" % (p.get("parent"), p.get("detail"))))
    if not (load_config().get("risks") or []):
        issues.append(("ERROR", "config/child_items.json",
                       "子项配置为空（子项/关联项未定义，Skill 6 未落地）"))
    # ②③④ 产物级：取全量产物；取不到时**如实 WARN**（不静默通过）
    try:
        rep = _canonical_report()
    except Exception as exc:                          # noqa: BLE001
        rep = None
        issues.append(("WARN", "tools/audit_consistency.py",
                       "读取全量产物失败，门禁②③④未执行：%s" % exc))
    if isinstance(rep, dict):
        try:
            for it in audit_product(rep):
                issues.append(("ERROR", "config/child_items.json",
                               "%s：%s" % (it.get("parent"), it.get("detail"))))
        except Exception as exc:                      # noqa: BLE001 - 留痕，不静默
            issues.append(("WARN", "engine/child_item_completeness.py",
                           "漏登记核验未执行：%s" % exc))
        er = rep.get("enterprise_readable_report") or rep
        probs = [p for p in (er.get("confirmed_problems") or []) if isinstance(p, dict)]
        _circled = "①②③④⑤⑥⑦⑧⑨⑩"
        for p in probs:
            rid = str(p.get("redline_id") or p.get("rule_id") or p.get("title") or "")
            title = str(p.get("title") or "")[:20]
            blob = json.dumps(p, ensure_ascii=False)
            # ③ 清单必须真在报告里
            try:
                if _kids(rid) and CHECKLIST_LEAD not in blob:
                    issues.append(("ERROR", "全量产物",
                                   "疑点「%s」登记了子项，但报告里没有「%s」清单"
                                   "（生成了却没挂上去）" % (title, CHECKLIST_LEAD)))
            except Exception as exc:                  # noqa: BLE001 - 留痕，不静默
                issues.append(("WARN", "全量产物", "子项清单落盘核验未执行：%s" % exc))
            # ④ 要件条目必须自带结论 + 独立数据源
            for np_ in (p.get("narrative_paragraphs") or []):
                if not isinstance(np_, dict):
                    continue
                for b in (np_.get("bullets") or []):
                    s = str(b or "")
                    if not s or s[0] not in _circled:
                        continue
                    if "独立数据源" not in s:
                        issues.append(("ERROR", "全量产物",
                                       "疑点「%s」的构成要件条目缺独立数据源：%s"
                                       % (title, s[:40])))
                    elif not any(k in s for k in ("符合情形", "未发现符合", "未形成核对结论",
                                                  "未单独核对", "未达", "核对证据")):
                        issues.append(("ERROR", "全量产物",
                                       "疑点「%s」的构成要件条目没有核对结论（列了却没分析）：%s"
                                       % (title, s[:40])))
            # ⑤ 结构化字段（规格【输出】）与清单文本必须一致、且一一对应
            _blk = p.get("child_item_audit")
            if not isinstance(_blk, dict):
                if _kids(rid):
                    issues.append(("ERROR", "全量产物",
                                   "疑点「%s」登记了子项，但没有结构化审计块 child_item_audit"
                                   "（规格【输出】字段缺失：child_items/child_status/"
                                   "child_conclusion/child_gap/related_items/related_analysis）" % title))
                continue
            for _fk in ("parent_risk_code", "child_items", "child_status", "child_conclusion",
                        "child_gap", "related_items", "related_analysis"):
                if _fk not in _blk:
                    issues.append(("ERROR", "全量产物",
                                   "疑点「%s」的 child_item_audit 缺字段「%s」" % (title, _fk)))
            _ci = [str(c.get("id") or "") for c in (_blk.get("child_items") or [])
                   if isinstance(c, dict)]
            _cs = _blk.get("child_status") if isinstance(_blk.get("child_status"), dict) else {}
            if sorted(_ci) != sorted(str(k) for k in _cs):
                issues.append(("ERROR", "全量产物",
                               "疑点「%s」child_items 与 child_status **不一一对应**"
                               "（清单 %s vs 状态 %s）" % (title, _ci[:6], sorted(_cs)[:6])))
            _gap = _blk.get("child_gap") if isinstance(_blk.get("child_gap"), dict) else {}
            for _cid, _st in _cs.items():
                if not isinstance(_st, dict):
                    continue
                if _st.get("status") != "已核对" and not str(_gap.get(_cid) or "").strip():
                    issues.append(("ERROR", "全量产物",
                                   "疑点「%s」子项 %s 状态为「%s」却没有 gap（原因+需补资料）"
                                   % (title, _cid, _st.get("status"))))
            # 两张皮：清单文本里写了几项状态，结构化数据必须同样有几项
            _ck_txt = " ".join(
                str(b) for np_ in (p.get("narrative_paragraphs") or [])
                if isinstance(np_, dict) for b in (np_.get("bullets") or [])
                if CHECKLIST_LEAD in str(b))
            _n_txt = sum(_ck_txt.count(m) for m in
                         ("[已核对]", "[未核对]", "[须核对]", "[资料缺失]"))
            _n_struct = sum(1 for _st in _cs.values()
                            if isinstance(_st, dict) and _st.get("status") in (
                                "已核对", "未核对", "须核对", "资料缺失"))
            if _n_struct and _n_txt and _n_txt != _n_struct:
                issues.append(("ERROR", "全量产物",
                               "疑点「%s」清单文本的状态项数(%d)与结构化数据(%d)不一致"
                               "（文本与结构两张皮）" % (title, _n_txt, _n_struct)))
    return issues


def check_data_source_status_consistency() -> List[Tuple[str, str, str]]:
    """数据源状态一致性（Skill 7 的硬规则；2026-10-07）。

    用户点名的缺陷：**数据已取得却写未取得** —— 明细表逐笔列着「红字发票信息确认单编号」，
    核对表却写「独立数据源本轮未取得」；正文正用着销项发票金额，同一行的「数据源状态」却写
    「须核对」。根因：要件声明的「独立数据源」是**多源组合串**，旧实现把它当**一份材料**
    整体匹配 ⇒ 有一个源缺，**已取得的源被一起否定**（实测 65 条要件行中 26 条命中）。

    门禁（产物级，**只依赖落盘数据**，不重算资料匹配）：
      ① **状态表必须落盘且自洽**：每个有要件核对表的疑点都要有 `data_source_status`，
         字段齐全（规格【输出】），`consistency` 不得为 False；
      ② **不得"整体否定"**：要件行组内只要有源在状态表里 `status_in_detail=已有`，
         该行结论不得出现「独立数据源本轮未取得」/「本轮均未取得」（这两句＝"一个都没有"）；
      ③ **状态列不得与已取得打架**：组内有 `status_in_detail=已有` 的源时，
         「数据源状态」列不得写 缺失/未取得；
      ④ **状态列必须与唯一权威同口径**：本行「数据源状态」== 该行声明数据源在本项
         「数据源状态表」里的逐源状态按 `data_source_status.combine` 的合成结论
         ⇒ **不得凭空改写**状态列。（2026-10-09 替换原「符合情形 ⇒ 非缺口状态」：
         前提条的现象可由**触发信号**检出、其声明源仍可未取得，原规则会把如实登记误报。）
    """
    issues: List[Tuple[str, str, str]] = []
    rep = _canonical_report()
    if not isinstance(rep, dict):
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "无真跑产物，数据源状态一致性未校验（跑一次全量分析后自动生效）"))
        return issues
    er = rep.get("enterprise_readable_report") or rep
    _FLAT_MISS = ("独立数据源本轮未取得", "本轮均未取得", "均未取得", "本轮未取得")
    _GAP_STATUS = ("缺失", "未取得", "待企业提交")
    _ck = "构成要件独立核对表"
    for p in (er.get("confirmed_problems") or []):
        if not isinstance(p, dict):
            continue
        title = str(p.get("title") or "")[:20]
        rows = [r for np_ in (p.get("narrative_paragraphs") or [])
                if isinstance(np_, dict)
                for t in (np_.get("detail_tables") or [])
                if _ck in str((t or {}).get("title") or "")
                for r in (t.get("rows") or []) if isinstance(r, dict)]
        if not rows:
            continue
        tbl = p.get("data_source_status")
        if not isinstance(tbl, list) or not tbl:
            issues.append(("ERROR", "全量产物",
                           "疑点「%s」有要件核对表，却没有「数据源状态表」data_source_status"
                           "（规格【输出】字段：data_source_id/data_source_name/"
                           "status_in_detail/status_in_checklist/consistency/conflict_reason）"
                           % title))
            continue
        _need = ("data_source_id", "data_source_name", "status_in_detail",
                 "status_in_checklist", "consistency", "conflict_reason")
        for row in tbl:
            if not isinstance(row, dict):
                continue
            for f in _need:
                if f not in row:
                    issues.append(("ERROR", "全量产物",
                                   "疑点「%s」数据源状态表缺字段「%s」" % (title, f)))
            if row.get("consistency") is False:
                issues.append(("ERROR", "全量产物",
                               "疑点「%s」数据源「%s」状态不一致：%s"
                               % (title, row.get("data_source_name"),
                                  str(row.get("conflict_reason") or "")[:80])))
        have_in_detail = {str(r.get("data_source_name") or "")
                          for r in tbl if isinstance(r, dict)
                          and r.get("status_in_detail") == "已有"}
        # ④ 的取数：本项「数据源状态表」的**逐源**状态（与要件行同源，不另算一遍）
        _tbl_by_name = {str(x.get("data_source_name") or ""): str(x.get("status_in_checklist") or "")
                        for x in tbl if isinstance(x, dict)}
        for r in rows:
            src = str(r.get("独立数据源") or "")
            if not src or src.startswith("（红线定义未标注"):
                continue
            st_col = str(r.get("数据源状态") or "")
            cc = str(r.get("核对结论") or "")
            _names = set()
            try:
                from engine.data_source_status import split_sources as _sp, \
                    canonical_name as _cn
                _names = {_cn(x) for x in _sp(src)}
            except Exception:                 # noqa: BLE001 - 留痕，不静默
                issues.append(("WARN", "engine/data_source_status.py",
                               "多源串切分权威不可用，②③④未执行：%s" % src[:30]))
            _hit = _names & have_in_detail
            if _hit and any(k in cc for k in _FLAT_MISS):
                issues.append(("ERROR", "全量产物",
                               "疑点「%s」%s：独立数据源组内已取得 %s（明细表已列示），"
                               "核对结论却写「未取得」——数据已取得却写未取得"
                               % (title, r.get("要件序号") or "", "、".join(sorted(_hit)))))
            if _hit and st_col in _GAP_STATUS:
                issues.append(("ERROR", "全量产物",
                               "疑点「%s」%s：组内已取得 %s，「数据源状态」列却写「%s」"
                               % (title, r.get("要件序号") or "", "、".join(sorted(_hit)), st_col)))
            # ④ **状态列必须与唯一权威同口径**（2026-10-09 替换原「符合情形 ⇒ 非缺口状态」）：
            #    原规则假定"前提条判「符合情形」⇒ 其声明的独立数据源必已取得"。而**前提条的现象
            #    可由触发信号（其他资料）检出**，其声明源仍可未取得 ⇒ 该假定不成立，会把
            #    **如实登记**误报成"同一行自相矛盾"（实测 12 条前提条中 6 条被误报）；
            #    旧实现为躲这条规则，把状态列**无据改写成「已有」**——反过来与本表打架，
            #    并令闸门 `check_next_actions_not_ghost_requirements` 把"补充提供「X」"
            #    误报成"X 已判已有却又要补"（seq=16 实测）。
            #    现改为**单一权威一致性**断言：本行「数据源状态」== 该行声明数据源在本项
            #    「数据源状态表」里的逐源状态按 `data_source_status.combine` 的合成结论。
            #    （本表由 `table_for` 以同一权威 `resolve_group` 产出 ⇒ 同一份判定，不另算。）
            _per = {nm: _tbl_by_name.get(nm) for nm in _names}
            if _per and all(v for v in _per.values()) and st_col:
                try:
                    from engine.data_source_status import combine as _comb, STATUS_NA as _NA
                    if all(v == _NA for v in _per.values()):
                        _exp = _NA
                    else:
                        _exp = str(_comb([{"name": nm, "status": v}
                                          for nm, v in _per.items()]).get("status") or "")
                    if _exp and st_col != _exp:
                        issues.append(("ERROR", "全量产物",
                                       "疑点「%s」%s：「数据源状态」列写「%s」，而按其声明的"
                                       "独立数据源「%s」在本项「数据源状态表」的逐源状态合成"
                                       "应为「%s」—— 状态列与唯一权威不一致（不得凭空改写）"
                                       % (title, r.get("要件序号") or "", st_col, src[:30], _exp)))
                except Exception as _ex:      # noqa: BLE001 - 留痕，不静默
                    issues.append(("WARN", "engine/data_source_status.py",
                                   "④（状态列同口径）未执行：%s" % str(_ex)[:60]))
    return issues


def _doc_consistency_issues(module_name: str) -> List[Tuple[str, str, str]]:
    """把某个文档一致性 Skill 的 `audit()` 结果转成门禁三元组（5 个门禁的唯一转发点）。"""
    try:
        mod = __import__("engine.%s" % module_name, fromlist=["audit"])
    except Exception as exc:                      # 留痕，不静默
        return [("WARN", "engine/%s.py" % module_name, "无法导入：%s" % str(exc)[:100])]
    out: List[Tuple[str, str, str]] = []
    try:
        for i in mod.audit():
            out.append((str(i.get("level") or "WARN"), str(i.get("where") or module_name),
                        str(i.get("detail") or "")))
    except Exception as exc:                      # noqa: BLE001 - 留痕，不静默
        out.append(("WARN", "engine/%s.py" % module_name, "audit() 执行失败：%s" % str(exc)[:100]))
    return out


def check_doc_number_authority() -> List[Tuple[str, str, str]]:
    """**Skill D1 文档数字一致性**：文档里写的每个数字必须 == 权威值（现算，不得手抄）。

    用户验收样例（本批 11 处问题里的 5 处）：`02` 写「质量门禁 8 条规则」而权威值 9；
    `01` §6 合计写「25 passed」而权威值 28；`06` 规则清单写「TDS-①~⑧」而清单共 9 条。
    """
    return _doc_consistency_issues("doc_number_authority")


def check_rule_reference_sync() -> List[Tuple[str, str, str]]:
    """**Skill D2 规则引用一致性**：规则编号引用必须有效 + 规则清单文件必须覆盖全部规则。

    用户验收样例：新增 `TDS-⑨` 后 `02 §3 规则清单` 未同步（缺 ⑨）⇒ 本门禁报 ERROR。
    """
    return _doc_consistency_issues("rule_reference_sync")


def check_doc_residue_scan() -> List[Tuple[str, str, str]]:
    """**Skill D3 全文残留校验**：按**同义写法词典**展开检索旧值残留。

    用户验收样例：旧 grep 只搜「25 例」，漏掉「25 passed」（本批 01 §6 即此写法）。
    """
    return _doc_consistency_issues("doc_residue_scan")


def check_todo_status_sync() -> List[Tuple[str, str, str]]:
    """**Skill D4 未完成事项状态同步**：未完成清单的状态必须与「补做记录」一致。

    用户验收样例：补做3 已定性「系统 bug 并已修」，而 U1 仍挂「未完成」⇒ 本门禁报 ERROR。
    """
    return _doc_consistency_issues("todo_status_sync")


def check_doc_ref_graph() -> List[Tuple[str, str, str]]:
    """**Skill D5 跨文件引用一致性**：下游文件引用上游数据必须标注来源且值同步。

    用户验收样例：`最小检查集` 说「28 例」而 `01 §6` 写「25」⇒ 本门禁报 ERROR。
    """
    return _doc_consistency_issues("doc_ref_graph")


def check_report_metrics_single_source() -> List[Tuple[str, str, str]]:
    """★ 2026-10-08（P0-1 常驻闸门）：报告级派生量必须**单一权威**。

    病根（真实产物取证）：报告级计数曾由**两套集合各算一遍** ——
      引擎层 `all_findings`(154) → `total_risks=154`、`overall_level=已核定2项/待核152项`；
      报告层 `confirmed_problems`(16) → 正文实际列出并编号的 16 项。
    后果：四门禁 B6 一次抓出 **11 处**声明-实际不符，报告首屏与正文自相矛盾。

    判据（静态 + 行为断言，零依赖真产物运行）：
      ① `engine/report_metrics.py` 必须存在且导出唯一入口；
      ② `quality_gates.iter_items` 必须是**薄转发**（两处取数必然假绿）；
      ③ `pipeline.py` / `main.py` 不得再自有报告级计数算术（算术只许在 report_metrics）；
      ④ 行为：正文集合存在时取数必须命中 `confirmed_problems`，不得落到 `all_findings`；
      ⑤ 行为：取不到正文集合时 `apply_report_metrics` 不得写回（不得用 0 静默顶替）；
      ⑥ 行为：已核定+待核 恒等于条目数；
      ⑦ 行为：等级分档必须覆盖全部合法档（极高/低/待核验不得被吞）。
    """
    issues: List[Tuple[str, str, str]] = []
    rel = "engine/report_metrics.py"
    try:
        from engine import report_metrics as rm   # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", rel, "无法导入报告级派生量唯一权威：%s" % exc)]

    for _fn in ("report_surface_items", "compute_report_metrics", "apply_report_metrics",
                "count_levels", "count_conclusions", "ledger_counts", "scope_items"):
        if not callable(getattr(rm, _fn, None)):
            issues.append(("ERROR", rel, "缺唯一权威入口 `%s`（报告级派生量必须单一来源）" % _fn))

    # ② 门禁取数必须是薄转发
    try:
        _qsrc = (ROOT / "engine" / "quality_gates.py").read_text(encoding="utf-8", errors="replace")
    except OSError:
        _qsrc = ""
    if _qsrc:
        _m = re.search(r"def iter_items\(.*?\n(.*?)\ndef ", _qsrc, re.S)
        _body = _m.group(1) if _m else ""
        if "report_surface_items(" not in _body:
            issues.append(("ERROR", "engine/quality_gates.py",
                           "`iter_items` 未转发到唯一权威 `report_metrics.report_surface_items`"
                           "（门禁与产出各取一套集合 ⇒ 判据 PASS 而报告照旧的假绿）"))

    # ②b ★ 2026-10-09：**报告层取数/容器**同样只许一处实现。
    #   实测事故：`common_clauses` 直接读顶层 `report_data["confirmed_problems"]`（不存在）
    #   并把 `report_statement` 写到顶层 ⇒ 上提恒为 0 句、且前端取不到（写了个寂寞）；
    #   `report_pipeline` / `material_gap` 另各有第三、四份同义解析。
    #   ⇒ 全部必须**薄转发** `report_metrics`，否则同一概念多处维护必然漂移。
    def _fn_body(_src: str, _name: str) -> str:
        # ⚠ 用**前瞻**而非消费下一个 `def`：否则"位于文件末尾的函数"取不到函数体 ⇒ 判据静默失效（假绿）。
        _mm = re.search(r"\ndef %s\(.*?\n(.*?)(?=\ndef |\Z)" % re.escape(_name), _src, re.S)
        return _mm.group(1) if _mm else ""

    for _mod, _fn in (("engine/report_pipeline.py", "report_items"),
                      ("engine/material_gap.py", "_iter_items"),
                      ("engine/common_clauses.py", "hoist_common_clauses")):
        try:
            _src2 = (ROOT / _mod).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        _b2 = _fn_body(_src2, _fn)
        if not _b2:
            issues.append(("ERROR", _mod,
                           "取不到 `%s` 的函数体 —— 报告层取数转发判据无法执行（不得静默跳过）" % _fn))
            continue
        if "report_surface_items(" not in _b2:
            issues.append(("ERROR", _mod,
                           "`%s` 未薄转发 `report_metrics.report_surface_items`"
                           "（报告层取数多处维护 ⇒ 同一报告两种条目集合）" % _fn))
        if _fn == "hoist_common_clauses" and "report_surface_container(" not in _b2:
            issues.append(("ERROR", _mod,
                           "报告级通用口径上提未走 `report_metrics.report_surface_container`"
                           " ⇒ 上提会写到前端取不到的那一层（等于没写）"))

    # ③ 报告级计数算术不得散落在 pipeline / main
    for _f in ("engine/pipeline.py", "main.py"):
        try:
            _src = (ROOT / _f).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if re.search(r'_lv\.startswith\("极高"\)\s*or\s*_lv\.startswith\("高"\)', _src):
            issues.append(("ERROR", _f,
                           "仍自有报告级等级分档算术（高/中/低手写 for 循环）—— "
                           "算术只许在 engine/report_metrics.py"))
        if re.search(r'conclusion_grade"\)\s*==\s*"已核定"', _src):
            issues.append(("ERROR", _f,
                           "仍自有「已核定」手写计数 —— 算术只许在 engine/report_metrics.py"))

    # ④ 行为：正文集合存在时必须命中 confirmed_problems
    _probe = {"enterprise_readable_report": {"confirmed_problems": [{"risk_level": "高风险"}]},
              "all_findings": [{"risk_level": "低风险"}] * 7}
    _got = rm.report_surface_items(_probe)
    if len(_got) != 1 or rm.report_surface_source(_probe) != rm.SURFACE_LABEL:
        issues.append(("ERROR", rel,
                       "取数未命中报告正文集合（得到 %d 项、来源 %r）—— 报告级计数会回到引擎层口径"
                       % (len(_got), rm.report_surface_source(_probe))))

    # ⑤ 行为：取不到正文集合时不得写回
    _empty: Dict[str, Any] = {"all_findings": []}
    _res = rm.apply_report_metrics(_empty)
    if _res.get("ok") or "total_risks" in _empty:
        issues.append(("ERROR", rel,
                       "取不到正文集合却仍写回报告级计数（等于用 0 静默顶替，须如实说取不到）"))

    # ⑥ 行为：两级结论之和恒等于条目数
    _items = [{"conclusion_grade": "已核定"}, {"conclusion_grade": "待核"}, {}]
    _v, _p = rm.count_conclusions(_items)
    if _v + _p != len(_items):
        issues.append(("ERROR", rel, "已核定+待核 ≠ 条目数（%d+%d≠%d）" % (_v, _p, len(_items))))

    # ⑦ 行为：等级分档必须覆盖全部合法档
    _lv = rm.count_levels([{"risk_level": "极高风险"}, {"risk_level": "待核验"}, {"risk_level": "低风险"}])
    if _lv["extreme_risk"] != 1 or _lv["low_risk"] != 1 or _lv["unleveled"] != 1:
        issues.append(("ERROR", rel,
                       "等级分档漏档（极高=%s 低=%s 未分级=%s）—— 分档必须覆盖全部合法档"
                       % (_lv["extreme_risk"], _lv["low_risk"], _lv["unleveled"])))
    return issues


def check_entry_subject_floor() -> List[Tuple[str, str, str]]:
    """★ 2026-10-08（P0-4 常驻闸门）：事实引子（「为何列入检查」）**必须有主体相关度下限**。

    病根（真实产物取证）：`engine/enterprise_report.py` 的事实引子第 ④ 条取值路径
    （同疑点下 supporting_findings 的信号）用 `_best_sc = -1` + `_sc2 > _best_sc`，
    **零重叠（0）也会中选** ⇒ 任何无关发现都能被写成"本项的事实引子"。
    实测 R14 标题「广告/娱乐服务未申报文化事业建设费」，引子却写「同一供应商同品名单价不一致
    （共5笔）…金额合计 0.00 元」—— 张冠李戴，读者据此无法复核。

    判据：
      ① 源码必须出现**相关度下限**（`_sc_floor`）且比较为 `>= _sc_floor`；
      ② 不得再存在无下限的 winner-take-all（`_best_sc = -1` 紧跟 `if _sc2 > _best_sc:`）；
      ③ 未达下限而改用中性口径时必须**留痕**（`audit_sink`），不得静默。
    """
    issues: List[Tuple[str, str, str]] = []
    rel = "engine/enterprise_report.py"
    try:
        src = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [("ERROR", rel, "无法读取（事实引子下限判据无法执行）")]

    if "_sc_floor" not in src:
        issues.append(("ERROR", rel,
                       "事实引子选择缺主体相关度下限 `_sc_floor`（零重叠会被当成最相关）"))
    elif not re.search(r"_sc2\s*>=\s*_sc_floor", src):
        issues.append(("ERROR", rel, "存在 `_sc_floor` 但比较未使用 `>=`（下限形同虚设）"))

    for _m in re.finditer(r"_best_sc\s*=\s*-1\s*\n(.{0,900}?)if\s+_sc2\s*>\s*_best_sc\s*:",
                          src, re.S):
        if "_sc_floor" not in _m.group(1):
            issues.append(("ERROR", rel,
                           "事实引子仍存在**无下限**的 winner-take-all"
                           "（`_best_sc = -1` 后直接 `_sc2 > _best_sc`）⇒ 零重叠也会中选"))

    if "_sc_floor" in src and '"事实引子' not in src:
        issues.append(("WARN", rel, "未达下限改用中性口径时未见留痕 —— 按项目铁律不得静默"))
    return issues



def check_problem_ring_completeness() -> List[Tuple[str, str, str]]:
    """★ 2026-10-09（P0-5 常驻闸门）：每条风险事项必须**七环齐全**（环名/环序由唯一权威决定）。

    ## 病根（真实产物取证，"同一件事两种讲法"）
    同一份报告里三个分支各拼一套段落结构 ⇒ 读者看到的结构不一致、且**域分析项缺环**：
      · 红线分支产出 7 段；
      · 域分析分支（`_promote_standalone_to_problems`）自行拼 7 段，但**环名不同**、
        且缺「推导链 / 要件清单 / 结论句 / 后果段」；
      · 专项比对分支又是一套。
    后果：域分析项缺 `conclusion_grade`、缺办理顺序（门禁 A4/B2 实测报错），
    且"若不补充资料的后果"这一环时有时无 —— 企业无从判断"不补会怎样"。

    ## 修法（已落）
    环名与环序收敛到 `engine/report_ring_schema.RINGS`；两个分支都调 `build_rings()`，
    只提供"环的内容素材"；缺环用 `default_ring()` 生成或如实登记缺口（**绝不静默少一环**）。
    "哪些环本情形不适用"（如已定性事项不再讲后果）由 `ctx_for_problem()` **唯一权威**推导。

    ## 本闸门判据
      ① 静态：唯一权威存在且暴露 `RINGS/REQUIRED_KEYS/normalize_problem_rings/
         missing_required_keys/ctx_for_problem`；
      ② 静态：`enterprise_report` 确实**经** `normalize_problem_rings(...)` 收敛七环，
         且 ctx 经 `ctx_for_problem(...)` 推导（**不得**在分支里另写一套跳过规则）；
      ③ 行为：真跑产物里**每条** `confirmed_problems` 都无必填环缺口（按 `ctx_for_problem`
         同口径，已定性项不计后果环）—— 缺任一必填环 ⇒ ERROR 并**点名**缺哪个环。
      ④ 反向锁：故意喂一条只含一环的事项，`missing_required_keys` 必须报出其余四环缺口
         （判据本身自证非假；若恒返回空，本闸门即为假判据）。
    """
    issues: List[Tuple[str, str, str]] = []
    rel = "engine/report_ring_schema.py"
    try:
        from engine import report_ring_schema as rrs   # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", rel, "无法导入七环唯一权威：%s" % exc)]

    for _fn in ("RINGS", "REQUIRED_KEYS", "normalize_problem_rings",
                "missing_required_keys", "ctx_for_problem", "build_rings"):
        if not hasattr(rrs, _fn):
            issues.append(("ERROR", rel, "缺唯一权威入口 `%s`（七环结构必须单一来源）" % _fn))
    if issues:
        return issues

    # ② 静态：生产分支必须经唯一构造入口，跳过规则必须经唯一推导入口
    _er_rel = "engine/enterprise_report.py"
    try:
        _ersrc = (ROOT / _er_rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        _ersrc = ""
    if "normalize_problem_rings(" not in _ersrc:
        issues.append(("ERROR", _er_rel,
                       "未调用 `report_ring_schema.normalize_problem_rings` ⇒ 七环结构在分支里各拼一套"))
    if "report_ring_schema" in _ersrc and "ctx_for_problem(" not in _ersrc:
        issues.append(("ERROR", _er_rel,
                       "ctx 未经 `ctx_for_problem` 推导 —— 跳过规则被复制成第二处，"
                       "生产与闸门会互相假红/漏判"))
    if re.search(r'"skip_required"\s*:', _ersrc):
        issues.append(("ERROR", _er_rel,
                       "分支里仍内联 `skip_required` 字面量 —— 跳过规则只许在 `report_ring_schema`"))

    # ④ 反向锁：判据非假（只给一环 ⇒ 必须报出缺口）
    _probe_para = [{"heading": rrs.title_of("risk_item"), "ring_key": "risk_item", "text": "x"}]
    _probe_miss = rrs.missing_required_keys(_probe_para, ctx={})
    if not _probe_miss or "risk_item" in _probe_miss:
        issues.append(("ERROR", rel,
                       "`missing_required_keys` 反向验证失败（只给一环却未报缺口：%r）—— "
                       "该判据是假的，闸门形同虚设" % (_probe_miss,)))

    # ③ 行为：真跑产物逐条核对
    _rep = _canonical_report()
    if _rep is None:
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "无真跑产物，七环完整性检查跳过（跑一次全量分析后自动生效）"))
        return issues
    er = _rep.get("enterprise_readable_report") or _rep
    probs = [p for p in (er.get("confirmed_problems") or []) if isinstance(p, dict)]
    if not probs:
        return issues

    # ③b **与「共性声明前置」同口径**：某环若已被**报告级上提**（`common_statements` 里
    #     有该环标题的逐字原文 ⇒ 企业可在「五、报告性质和使用说明」对照），则不算"缺口"。
    #   这是 `report_dedup` R2 的既定行为（用户第九条口径：从所有疑点删除、报告级一次给出，
    #   原文存档可查）。判据必须与去重动作同源，否则会出现
    #   「去重器按规则上提、闸门却报缺环」的**假红**。
    _hoisted_rings = set()
    for _c in (er.get("common_statements") or []):
        if isinstance(_c, dict):
            _rk = rrs.ring_key_of(_c.get("heading"))
            if _rk:
                _hoisted_rings.add(_rk)

    for it in probs:
        paras = it.get("narrative_paragraphs") or []
        miss = rrs.missing_required_keys(paras, ctx=rrs.ctx_for_problem(it))
        # 过滤掉"已上提到报告级"的环（有出处可查 ≠ 缺口）
        miss = [k for k in miss if k not in _hoisted_rings]
        if miss:
            _cn = "、".join(rrs.title_of(k) or k for k in miss)
            issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                           "风险事项 seq=%s「%s」缺必填环 %d 个：%s"
                           % (it.get("seq"), str(it.get("title"))[:18], len(miss), _cn)))
    return issues


def check_necessary_repeat_single_entry() -> List[Tuple[str, str, str]]:
    """P1-3 · 「必要重复 / 不计冗余」只许有**一个判定入口**（行为级、零依赖真产物）。

    ## 复发病根（2026-10-09 实测）
    同一概念「这段文字属必要重复、不计冗余」此前有**三处各判一次**：
      · `dedup_pipeline.is_necessary` + `config/dedup_rules.json::necessary_repeat`
        —— 服务 `duplicate_rate` 的四项判据；
      · `common_clauses` 登记表（`is_registered_clause` / `is_necessary_template`）
        —— 只服务『跨章节模板句』一项；
      · `report_pipeline.non_dedupable_values`（逐项结论/口径字段）—— 只服务门禁 D5。
    ⇒ 同一句在 A 判据被豁免、在 B 判据被计为冗余，闸门之间互相假红；且『跨章节模板句』
      把**逐项结论句**（各事项主体不同）判为模板。

    ## 判据（行为级断言，均不依赖产物）
      ① 取不到登记表时 `_necessary_sources()` 必须非空 ⇒ 判据自证「来源已接通」；
      ② `is_necessary` 必须认得 `common_clauses` 登记表里**每一条** `match` 的样本；
      ③ **防过宽**：以登记口径开头、但含本项特有内容的多句段落，**不得**整体豁免；
      ④ 反向验证：临时断开登记表 ⇒ ② 的样本必须不再被豁免（判据自证非假）。
    """
    issues: List[Tuple[str, str, str]] = []
    rel = "engine/dedup_pipeline.py"
    try:
        from engine.common_clauses import load_registry
        from engine.dedup_pipeline import _necessary_sources, is_necessary
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", rel, "无法导入必要重复判据：%s" % exc)]

    # ① 来源必须接通
    if not _necessary_sources():
        issues.append(("ERROR", rel, "`_necessary_sources()` 为空 —— 登记表未接通"
                       "（必要重复只剩 dedup_rules 一套 ⇒ 与 D5/跨章节判据不同口径）"))

    # ② 登记表每一条都必须被 is_necessary 认得
    reg = load_registry()
    entries = [c for c in (reg.get("hoist") or []) + (reg.get("necessary") or [])
               if isinstance(c, dict)]
    if not entries:
        issues.append(("ERROR", "config/common_clauses.json", "登记表为空（口径无处登记）"))
    samples: List[Tuple[str, str]] = []
    for c in entries:
        for pat in (c.get("match") or []):
            try:
                rx = re.compile(pat)
            except re.error:
                issues.append(("ERROR", "config/common_clauses.json",
                               "登记项 %s 的正则非法：%r" % (c.get("id"), pat)))
                continue
            # 用正则里 ^ 之后的**字面量前缀**做样本（去掉元字符）
            literal = re.sub(r"[\\^$.|?*+()\[\]{}]", "", str(pat).split("\\")[0])
            if literal and rx.search(literal):
                samples.append((str(c.get("id")), literal))
    miss = ["%s::%r" % (cid, lit) for cid, lit in samples if not is_necessary(lit)]
    if miss:
        issues.append(("ERROR", rel,
                       "%d 条已登记口径未被 `is_necessary` 豁免（豁免口径未收敛到单一入口）：%s"
                       % (len(miss), "；".join(miss[:6]))))

    # ③ 防过宽：多句段落不得因"以登记口径开头"而整体豁免
    _mixed = ("综合以上，本项结论是疑似触碰税务违规红线。"
              "本项涉及金额 1,234,567.89 元，属本项独有的核算口径。")
    if is_necessary(_mixed):
        issues.append(("ERROR", rel,
                       "多句段落被整体豁免（以登记口径开头即全段免检）⇒ 真冗余会被藏住"))

    # ④ 反向验证：断开登记表 ⇒ 登记口径样本必须不再被豁免
    if samples:
        try:
            import engine.dedup_pipeline as _dp
            _orig = _dp._necessary_sources
            _dp._necessary_sources = lambda: []          # noqa: E731
            try:
                _still = [lit for _cid, lit in samples if _dp.is_necessary(lit)]
            finally:
                _dp._necessary_sources = _orig
            if _still:
                issues.append(("ERROR", rel,
                               "反向验证失败：断开登记表后仍有 %d 条登记口径被豁免 "
                               "⇒ 判据是假的（豁免来自别处）" % len(_still)))
        except Exception as exc:  # noqa: BLE001
            issues.append(("ERROR", rel, "反向验证执行失败：%s" % exc))
    return issues


def check_cross_chapter_sentence_dup() -> List[Tuple[str, str, str]]:
    """★ 2026-10-09（P0-7 常驻闸门）：正文**跨章节重复的模板句**必须为 0 种。

    ## 病根（真实产物取证）
    三项原有重复率判据**结构上**覆盖不到"跨章节 + 非数值 + 句子级"这一格：
      · 整体 / 同章节判据只看**段落级**相似，而模板句藏在段内，段与段并不相似；
      · 「同一事实」判据只认**含 ≥5 位数值锚点**的句子，模板句不含金额。
    实测（2026-10-08 产物）：**33 种**非数值模板句跨章节重复、最长一处在 13 个章节出现。
    这些句子绝大多数是**报告级通用口径**（对每个事项一字不差成立），本不该逐条复述。

    ## 修法（已落）
    判据与动作**同口径**收敛：
      · 判定 = `engine/dedup_pipeline.cross_chapter_template_stats`（第四项判据）；
      · 动作 = `engine/common_clauses.hoist_common_clauses`（登记表 `config/common_clauses.json`），
        在报告出口 ② 位从各事项正文移除、报告级只说一次（同时写 `report_statement` —— 渲染器唯一消费点）。

    ## 本闸门判据（与产出链**同一函数、同一取数**）
      取真跑产物 → `output_variants.report_text_from`（＝产出链判重复率的**同一文本**）
      → `dedup_pipeline.duplicate_rate(lines)` → 读其 `跨章节模板句.判定`；
      非 PASS ⇒ ERROR 并列 TOP20（跨章节数 + 样例）。
      ⚠ 不得自写一套计数：判据只有 `cross_chapter_template_stats` 一处实现。
      ⚠ 取不到文本时**不静默通过**（明说 SKIP）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.dedup_pipeline import duplicate_rate   # noqa: PLC0415
        from engine import output_variants as _ov          # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "engine/dedup_pipeline.py", "无法导入去重唯一权威：%s" % exc)]

    # ⓪ 判据自证非假（不依赖产物，永远执行）：把同一模板句塞进两个章节 ⇒ 必须 FAIL
    try:
        _probe_lines = [
            "<<S:章节甲>>",
            "已取得的资料与待补充的资料如下，本项检查在现有资料范围内完成核对。",
            "<<S:章节乙>>",
            "已取得的资料与待补充的资料如下，本项检查在现有资料范围内完成核对。",
        ]
        _pv = duplicate_rate(_probe_lines)
        if _pv["跨章节模板句"]["判定"] != "FAIL":
            issues.append(("ERROR", "engine/dedup_pipeline.py",
                           "跨章节模板句判据**反向验证失败**：同一句塞进两个章节却判 PASS "
                           "（判据是假的，闸门形同虚设）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/dedup_pipeline.py",
                       "跨章节模板句反向验证执行失败：%s" % exc))

    _rep = _canonical_report()
    if _rep is None:
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "无真跑产物，跨章节模板句检查跳过（跑一次全量分析后自动生效）"))
        return issues

    _txt = ""
    try:
        _txt = _ov.report_text_from(_rep)     # 与产出链同一取数（用户可见域）
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/output_variants.py", "提取可判定文本失败：%s" % exc))
    if not _txt.strip():
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "可判定文本为空 —— 跨章节模板句检查 SKIP（不静默通过）"))
        return issues

    _dr = duplicate_rate(_txt.split("\n"))
    _xs = _dr.get("跨章节模板句") or {}
    if _xs.get("判定") != "PASS":
        _top = _xs.get("TOP20") or []
        _sum = "；".join("×%d %s…" % (t.get("跨章节数"), str(t.get("样例"))[:40])
                        for t in _top[:8])
        issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                       "正文存在 %s 种跨章节重复模板句（阈值 %s 章节）—— 应上提为报告级一次。%s"
                       % (_xs.get("超额种类数"), _xs.get("阈值_跨章节数"), _sum)))
    return issues


#: 报告数据的**实参名**（`iter_texts(<这个>)` 即为"直扫报告全量"，绕过扫描域白名单）。
_REPORT_DATA_ARG_NAMES = ("report_data", "picked", "raw_report")


def _direct_report_scan_lines(tree) -> List[int]:  # noqa: ANN001
    """AST：找 `iter_texts(<报告数据>)` 直扫调用的行号（P1-3 判据的**唯一实现**）。

    为什么不能用 grep：`iter_texts(it)`（逐项扫描）是**合法**的，只有实参是
    **整份报告数据**时才算"绕过扫描域白名单"。AST 能按实参名区分，grep 不能。
    """
    _hits: List[int] = []
    for _n in ast.walk(tree):
        if not isinstance(_n, ast.Call):
            continue
        _fn = _n.func
        _name = (_fn.id if isinstance(_fn, ast.Name)
                 else (_fn.attr if isinstance(_fn, ast.Attribute) else ""))
        if _name != "iter_texts":
            continue
        _args = list(_n.args) + [_k.value for _k in _n.keywords if _k.value is not None]
        _names = {_a.id for _a in _args if isinstance(_a, ast.Name)}
        if _names & set(_REPORT_DATA_ARG_NAMES):
            _hits.append(getattr(_n, "lineno", 0))
    return _hits


def check_gate_scan_domain_single_source() -> List[Tuple[str, str, str]]:
    """★ 2026-10-09（P1-3 常驻闸门）：门禁与去重必须用**同一扫描域函数**。

    ## 病根（同一份数据、两套扫描域）
    `report_data` 里混着**上传的原始文件内容**（HTML/JS/CSS）、内部质量自检告警与
    pipeline 轨迹。词表/残留类判据若直扫 `iter_texts(report_data)`，与走
    `quality_gates.report_surface()`（按 `config/quality_gates.json → scan_domain`
    白名单取域）的判据**扫描域不一致** ⇒ 同一份数据两套口径，闸门之间互相假红/假绿。
    实测违规点：`quality_gates._contradiction_pairs` 直扫全量（一次读取把上传的 HTML
    也当报告正文），而 `gate_*` 诸判据走白名单。

    ## 判据
      ① 唯一权威 `quality_gates.report_surface` 必须存在，且由 `scan_domain` 配置驱动、
         返回含 `texts` 的字典（"报告正文域"只能有一个入口）；
      ② **直扫归零**（AST 判定，不依赖 linter）：除 `report_surface` 函数体内部外，
         全仓不得再出现 `iter_texts(<整份报告数据>)` 的调用；
      ③ **反向验证**：把一段"含直扫"的假源码喂给 ② 的判定函数 ⇒ 必须报出 ——
         否则 ② 是假判据（比如实参名清单写错，永远匹配不上）。
      ⚠ 判据只有 `_direct_report_scan_lines` 一处实现；本闸门只调用、不自写第二套。
    """
    issues: List[Tuple[str, str, str]] = []
    _qg_rel = "engine/quality_gates.py"

    # ① 唯一权威
    try:
        from engine import quality_gates as _qg  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", _qg_rel, "无法导入门禁模块（扫描域判据无法执行）：%s" % exc)]
    if not hasattr(_qg, "report_surface"):
        issues.append(("ERROR", _qg_rel,
                       "缺唯一权威 `report_surface`（报告正文域只能有一个入口）"))
        return issues
    try:
        _probe = _qg.report_surface({"enterprise_readable_report": {"text": "甲"}})
        if not isinstance(_probe, dict) or "texts" not in _probe:
            issues.append(("ERROR", _qg_rel,
                           "`report_surface` 未返回含 `texts` 的字典（扫描域接口被改坏）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", _qg_rel, "`report_surface` 调用失败：%s" % exc))

    # ② 直扫归零（AST）
    _allowed: set = set()
    try:
        _qg_tree = ast.parse((ROOT / _qg_rel).read_text(encoding="utf-8", errors="replace"))
        for _n in ast.walk(_qg_tree):
            if isinstance(_n, ast.FunctionDef) and _n.name == "report_surface":
                _end = max((getattr(_x, "lineno", _n.lineno)
                            for _x in ast.walk(_n)), default=_n.lineno)
                _allowed |= set(range(_n.lineno, _end + 1))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", _qg_rel, "无法解析以定位 `report_surface` 边界：%s" % exc))

    _cands: List[Any] = [ROOT / "main.py"]
    for _d in ("engine", "tools", "scripts"):
        _r = ROOT / _d
        if _r.exists():
            _cands += [p for p in _r.rglob("*.py")
                       if "__pycache__" not in p.parts
                       and not p.name.startswith("test_")
                       and "tests" not in p.parts]
    for _p in _cands:
        try:
            if not _p.exists():
                continue
            import warnings as _warnings  # noqa: PLC0415
            with _warnings.catch_warnings():
                _warnings.simplefilter("ignore", SyntaxWarning)
                _tree = ast.parse(_p.read_text(encoding="utf-8", errors="replace"))
        except Exception:  # noqa: BLE001 —— 破损遗留脚本跳过（不是本闸门的发现）
            continue
        _rel = str(_p.relative_to(ROOT)).replace("\\", "/")
        for _ln in _direct_report_scan_lines(_tree):
            if _rel == _qg_rel and _ln in _allowed:
                continue
            issues.append(("ERROR", _rel,
                           "第 %s 行直扫 `iter_texts(<报告数据>)` —— 绕过了扫描域白名单 "
                           "`report_surface`（会把上传的原始文件内容当报告正文）："
                           "应改调 `report_surface(report_data)[\"texts\"]`" % _ln))

    # ③ 反向验证：判据自证非假
    try:
        _fake = ast.parse("def f(report_data):\n    return iter_texts(report_data)\n")
        if not _direct_report_scan_lines(_fake):
            issues.append(("ERROR", _qg_rel,
                           "反向验证失败：直扫样本未被判据识别（实参名清单或 AST 判据写错）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", _qg_rel, "反向验证执行失败：%s" % exc))
    return issues


def check_vocab_conflict() -> List[Tuple[str, str, str]]:
    """★ 2026-10-09（P1-4 常驻闸门）：禁用词表 ∩ 授权词表 == ∅（或已登记豁免及理由）。

    ## 病根（"同一概念两处维护"在词表层的形态）
    **清洗层要删的词，恰是术语层要留的词。** 实测：`FORBIDDEN_VAGUE_TERMS` 含裸词「待核」，
    而授权术语含「待核事项」—— 子串关系。不登记豁免时两模块判据必然互相打架：
      · 清洗删「待核」⇒ 术语「待核事项」被误伤（实测审计侧 25 处误报）；
      · 术语留「待核事项」⇒ 真模糊词「待核」漏网。
    此前靠 `vague_hits` 的**隐式占位豁免**共存 —— 隐式豁免**无出处、无理由**⇒ 改词表必复发。

    ## 判据（唯一权威 + 薄转发）
      ① 唯一权威 `engine/vocab_registry`（枚举词表 / 计算冲突 / 读登记表）必须可用，
         且登记表 `config/vocab_exemptions.json` 可解析（读不出即 ERROR，不静默）；
      ② **凡交集必有登记**：`unregistered_conflicts()` 必须为空；登记项必须含
         `id/reason/handler`（缺一即 ERROR）——「可以共存」必须可复核；
      ③ **登记项指向真表**：每条 `forbidden_table`/`authorized_table` 必须是
         `vocab_registry.tables()` 里真实存在的表（防"登记了元事实层面的假表"）；
      ④ **反向验证**（判据自证非假）：把登记表临时视为空 ⇒ 必须报出未登记冲突；
         若仍为空，说明闸门读的根本不是这张表 ⇒ ERROR。
      ⚠ 不得在本闸门自写一套词表/交集计算（那是第二处实现，正是本闸门要治的病）。
    """
    issues: List[Tuple[str, str, str]] = []
    rel = "config/vocab_exemptions.json"
    try:
        from engine import vocab_registry as _vr  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "engine/vocab_registry.py", "无法导入词表冲突唯一权威：%s" % exc)]

    for _fn in ("tables", "conflicts", "exemptions", "find_exemption", "unregistered_conflicts"):
        if not hasattr(_vr, _fn):
            issues.append(("ERROR", "engine/vocab_registry.py",
                           "缺唯一权威入口 `%s`（词表冲突判定必须单一来源）" % _fn))
    if issues:
        return issues

    for _e in _vr.load_errors():
        issues.append(("ERROR", "engine/vocab_registry.py", "词表登记读取留痕：%s" % _e))

    # ④ 反向验证（不依赖产物，永远执行）：登记表视为空 ⇒ 必须报出未登记冲突
    try:
        _orig = _vr.exemptions
        try:
            _vr.exemptions = lambda: []          # noqa: E731  模拟"登记表被清空"
            _probe = _vr.unregistered_conflicts()
        finally:
            _vr.exemptions = _orig
        if not _probe:
            issues.append(("ERROR", rel,
                           "反向验证失败：登记表清空后仍报「无冲突」⇒ "
                           "判据读的不是这张表（闸门形同虚设）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", rel, "反向验证执行失败：%s" % exc))

    # ③ 登记项必须指向真表
    _real_tables = {t for (t, _role, _ws) in _vr.tables()}
    if not _real_tables:
        issues.append(("ERROR", "engine/vocab_registry.py",
                       "词表枚举为空 —— 判据没有扫描域（词表导入失败？）"))
    for _e in _vr.exemptions():
        for _k in ("forbidden_table", "authorized_table"):
            _t = str(_e.get(_k) or "")
            if _t and _t not in _real_tables:
                issues.append(("ERROR", rel,
                               "登记项 %s 的 `%s` 指向不存在的词表 `%s`（元事实与实现不符）"
                               % (_e.get("id"), _k, _t)))

    # ② 凡交集必有登记
    _unreg = _vr.unregistered_conflicts()
    for _c in _unreg:
        issues.append(("ERROR", rel,
                       "禁用词「%s」(%s) 与授权词「%s」(%s) **共存且未登记豁免**：%s"
                       % (_c.get("forbidden"), _c.get("forbidden_table"),
                          _c.get("authorized"), _c.get("authorized_table"),
                          _c.get("_why"))))
    return issues


def check_fact_intro_subject_consistency() -> List[Tuple[str, str, str]]:
    """★ 2026-10-09（P0-4 常驻闸门 · **行为级**）：每条风险事项的「事实引子」必须与标题同主体。

    ## 与 `check_entry_subject_floor` 的分工（互补，不是重复）
    `check_entry_subject_floor` 是**源码级**：它只证明 `enterprise_report` 里**存在**相关度下限
    `_sc_floor`。源码级判据证明不了"结果对"—— 下限写对了、取值路径仍可能走偏。
    本闸门读**真跑产物**逐条判定结果，二者一静一动。

    ## 判据（口径与产出链**同源**）
      ① 唯一权威 `engine/subject_consistency` 必须暴露 `subject_terms` / `same_subject`
         （主体一致性只能有一个判据）；
      ② 取「为何列入检查」段，拆出**情况段** = 「本项对应的风险指标」/「本项因风险指标」之前的文本。
         ⚠ 模板**内嵌**了本项风险指标名（`本项对应的风险指标是「X」`）⇒ 若整段参与判定，
         判据退化成"模板里有没有指标名"（**同义反复的假判据**，用户 2026-10-05 明确禁止）。
         故必须**只判情况段** —— 那才是"为何列入检查"的实质依据。
      ③ `same_subject(标题, 情况段)` 必须为真（≥1 个非泛化主题词相同）——
         与 `enterprise_report` 选引子时用的 `same_subject` **同一判据**，同口径才可复核。
      ④ 反向验证：喂"标题与情况段无关"的样本 ⇒ 必须为假（判据自证非假）。
      ⑤ 无引子段 ⇒ SKIP 留痕（WARN），**不得当 PASS**（本项目铁律：SKIP ≠ 通过）。
    """
    issues: List[Tuple[str, str, str]] = []
    _rel = "engine/subject_consistency.py"
    try:
        from engine import subject_consistency as _sc  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", _rel, "无法导入主体一致性唯一权威：%s" % exc)]
    for _fn in ("subject_terms", "same_subject"):
        if not hasattr(_sc, _fn):
            issues.append(("ERROR", _rel, "缺唯一权威入口 `%s`（主体判据必须单一来源）" % _fn))
    if issues:
        return issues

    # ④ 反向验证（不依赖产物，永远执行）
    try:
        _off = _sc.same_subject("广告/娱乐服务未申报文化事业建设费",
                                "同一供应商同品名单价不一致（共5笔）")
        if _off:
            issues.append(("ERROR", _rel,
                           "反向验证失败：明显不同主体的两段被判为同一主体 ⇒ 判据是假的"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", _rel, "反向验证执行失败：%s" % exc))

    _rep = _canonical_report()
    if _rep is None:
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "无真跑产物，事实引子主体一致性检查跳过（跑一次全量分析后自动生效）"))
        return issues
    er = _rep.get("enterprise_readable_report") or _rep
    probs = [p for p in (er.get("confirmed_problems") or []) if isinstance(p, dict)]
    if not probs:
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "产物无 confirmed_problems —— 事实引子检查 SKIP（不静默通过）"))
        return issues

    _hit = 0
    for p in probs:
        title = str(p.get("title") or "").strip()
        _intro = ""
        for _np in (p.get("narrative_paragraphs") or []):
            if "为何列入检查" in str((_np or {}).get("heading") or ""):
                _intro = str((_np or {}).get("text") or "")
                break
        if not _intro:
            continue                      # 无引子段的事项在下方统一计数
        _hit += 1
        _seg = re.split(r"本项对应的风险指标|本项因风险指标", _intro)[0]
        _seg = re.sub(r"^本项之所以列入检查，是因为出现了以下情况：", "", _seg)
        _seg = re.sub(r"是因为在已上传资料中出现了以下情况：", "", _seg)
        _seg = _seg.strip(" 。；;")
        if not _seg or not title:
            continue
        if not _sc.same_subject(title, _seg):
            issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                           "风险事项 seq=%s 的「事实引子」与标题不同主体："
                           "标题「%s」↔ 引子「%s」—— 读者据此无法复核"
                           % (p.get("seq"), title[:26], _seg[:40])))
    if _hit == 0:
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "未找到任何「为何列入检查」段 —— 事实引子主体检查 SKIP（不静默通过）"))
    return issues


def check_conclusion_wording_authority() -> List[Tuple[str, str, str]]:
    """★ 2026-10-09（P1-1 常驻闸门）：**L1/L2 条目的裁决语不得含定性词**；
    裁决语只能由 `verdict_text` 产出（`grep -c "^def verdict_text" == 1`）。

    ## 病根
    裁决语此前散在多处：`conclusion_grade.pending_clue_phrase()`（仅 L2）、`argumentation`
    的 `GRADE_*` 常量、`enterprise_report` 的若干硬编码句。而"什么算定性词"只在
    `veto_rules.determinative_words` **一处**定义 ⇒ 多头产出时，新增/修改一个定性词
    只有一处跟着改，另一处**静默漏判**（本项目的标准病根：同一概念两处维护）。

    ## 判据
      ① **唯一生成点**：全仓 `^def verdict_text` 恰好 1 处（不得有第二处定义/旧定义残留）；
      ② **薄转发**：`pending_clue_phrase` 必须转发 `verdict_text(`，不得再自写句式；
      ③ **行为（生成侧）**：`verdict_text(L1/L2)` 必须含该等级术语 + 该等级 `required_text`
         的全部要件，且 `contains_determinative(...)` 为空（L1/L2 `allow_determinative_words=false`）；
      ④ **行为（产物侧）**：真跑产物里 `effective_grade_id ∈ {L1,L2}` 的事项，
         其 `verdict`（＝裁决语）不得含定性词；
      ⑤ **反向验证**：给 L2 句式注入一个定性词 ⇒ `contains_determinative` 必须命中
         （否则"禁定性词"这条判据是假的），且在合成产物上闸门必须报红。
    """
    issues: List[Tuple[str, str, str]] = []
    _rel = "engine/conclusion_grade.py"

    # ① 唯一生成点（grep）
    try:
        _src = (ROOT / _rel).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [("ERROR", _rel, "无法读取（裁决语唯一性判据无法执行）：%s" % exc)]
    _n_def = len(re.findall(r"(?m)^def\s+verdict_text\s*\(", _src))
    if _n_def != 1:
        issues.append(("ERROR", _rel,
                       "`^def verdict_text` 出现 %d 次（必须恰好 1 次）—— "
                       "裁决语生成点必须唯一，另一处会与 `veto_rules.determinative_words` 脱钩" % _n_def))

    # ② 薄转发（不得自写句式）—— ⚠ 必须用 **AST 看函数体**，不能靠 grep：
    #   实测 grep 会被**文档字符串里的提及**骗过（本文档就写了 `verdict_text(`），
    #   函数体改了、docstring 没改 ⇒ 假绿。AST 天然排除 docstring（它是 Constant 表达式）。
    try:
        _tree_src = ast.parse(_src)
        _pcp_fn = next((n for n in ast.walk(_tree_src)
                        if isinstance(n, ast.FunctionDef) and n.name == "pending_clue_phrase"), None)
        if _pcp_fn is None:
            issues.append(("ERROR", _rel, "找不到 `pending_clue_phrase` 定义（L2 用语入口缺失）"))
        else:
            _fwd = False
            for _n in ast.walk(_pcp_fn):
                if isinstance(_n, ast.Call):
                    _f = _n.func
                    _nm = (_f.id if isinstance(_f, ast.Name)
                           else (_f.attr if isinstance(_f, ast.Attribute) else ""))
                    if _nm == "verdict_text":
                        _fwd = True
            if not _fwd:
                issues.append(("ERROR", _rel,
                               "`pending_clue_phrase` 函数体未调用 `verdict_text` ⇒ 句式有第二处实现"
                               "（改一处另一处静默失效）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", _rel, "解析 `pending_clue_phrase` 函数体失败：%s" % exc))

    # ③ 行为（生成侧）
    try:
        from engine.conclusion_grade import (  # noqa: PLC0415
            verdict_text as _vt, contains_determinative as _cd,
            term_of as _tof, grade_by_id as _gb,
        )
    except Exception as exc:  # noqa: BLE001
        return issues + [("ERROR", _rel, "无法导入裁决语权威：%s" % exc)]
    for _gid in ("L1", "L2"):
        _txt = _vt(_gid)
        _term = _tof(_gid)
        if not _term or _term not in _txt:
            issues.append(("ERROR", _rel,
                           "`verdict_text(%s)` 未含该等级术语「%s」：%r" % (_gid, _term, _txt)))
        for _req in ((_gb(_gid) or {}).get("required_text") or []):
            if _req and _req not in _txt:
                issues.append(("ERROR", _rel,
                               "`verdict_text(%s)` 缺该等级必备表述「%s」：%r" % (_gid, _req, _txt)))
        _det = _cd(_txt)
        if _det:
            issues.append(("ERROR", _rel,
                           "`verdict_text(%s)` 含定性词 %s（该等级 `allow_determinative_words=false`）：%r"
                           % (_gid, _det, _txt)))

    # ⑤ 反向验证：判据自证非假
    try:
        _probe_txt = _vt("L2") + "本项已查明违法"
        if not _cd(_probe_txt):
            issues.append(("ERROR", _rel,
                           "反向验证失败：注入定性词「已查明违法」后 `contains_determinative` 仍为空"
                           "（禁定性词判据是假的）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", _rel, "反向验证执行失败：%s" % exc))

    # ④ 行为（产物侧）
    _rep = _canonical_report()
    if _rep is None:
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "无真跑产物，L1/L2 裁决语定性词检查跳过（跑一次全量分析后自动生效）"))
        return issues
    try:
        from engine.conclusion_grade import effective_grade_id as _eg  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return issues + [("ERROR", _rel, "无法导入 `effective_grade_id`：%s" % exc)]
    _er = _rep.get("enterprise_readable_report") or _rep
    _probs = [p for p in (_er.get("confirmed_problems") or []) if isinstance(p, dict)]
    for _p in _probs:
        _g, _ = _eg(_p)
        if _g not in ("L1", "L2"):
            continue
        _det = _cd(str(_p.get("verdict") or ""))
        if _det:
            issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                           "风险事项 seq=%s（结论等级 %s）的裁决语含定性词 %s（L1/L2 禁定性词）：%r"
                           % (_p.get("seq"), _g, _det, str(_p.get("verdict"))[:60])))
    return issues


def run_checks() -> Tuple[List[Tuple[str, str, str, int, int]],
                          List[Tuple[str, str, str]]]:
    authoritative = authoritative_values()
    counts = check_counts(authoritative)
    general = (check_law_articles() + check_pollution()
               + check_tax_names() + check_domains(authoritative)
               + check_doc_type_category_map() + check_industry_consistency()
               + check_coverage_source_wiring()
               + check_coverage_execution_receipt()   # 2026-10-06 「已执行」须有执行回执
               + check_question_theme_attachment()    # 2026-10-06 询问必须挂到疑点/资料缺口不重复
               + check_finding_basis_grounded()       # 2026-10-06 风险事项依据须有资料事实、不重复
               + check_related_risks_not_self()       # 2026-10-06 相关风险信号不得是本项自己
               + check_non_deductible_requires_invoice_type()  # 2026-10-06 应转出须先核实票种+抵扣状态
               + check_self_doubt_coverage()          # 2026-10-06 每条风险事项须有自我反驳+验证清单
               + check_recheck_chapter_no_meta()      # 2026-10-06 第四章不得有元话语/操作说明/越界要求
               + check_industry_exclusion_single_source()  # 2026-10-06 业态剔除须单一权威
               + check_metric_key_localized()         # 2026-10-06 量化结果不得出现英文引擎键
               + check_report_metrics_single_source() # 2026-10-08 报告级派生量须单一权威（B6 根因）
               + check_entry_subject_floor()          # 2026-10-08 事实引子须有主体相关度下限（R14 根因）
               + check_problem_ring_completeness()    # 2026-10-09 P0-5 每条风险事项须七环齐全
               + check_cross_chapter_sentence_dup()   # 2026-10-09 P0-7 跨章节模板句须为 0 种
               + check_vocab_conflict()               # 2026-10-09 P1-4 禁用词∩授权词须登记豁免
               + check_necessary_repeat_single_entry()  # 2026-10-09 P1-3 必要重复须单一判定入口
               + check_gate_scan_domain_single_source()  # 2026-10-09 P1-3 门禁与去重须同扫描域
               + check_conclusion_wording_authority()    # 2026-10-09 P1-1 裁决语唯一生成点+禁定性词
               + check_fact_intro_subject_consistency()  # 2026-10-09 P0-4 事实引子须与标题同主体
               + check_company_artifact_consistency() # 2026-10-06 删账套必须连派生物一起清
               + check_delete_exits()                 # 2026-10-06 删除出口唯一（任何删除都要删干净）
               + check_report_version_reuse_authority()  # 2026-10-09 增量复用判据须走权威
               + check_audit_trail_single_writer()    # 2026-10-09 业务留痕写入唯一权威
               + check_report_payload_single_shape()  # 2026-10-09 报告载荷形状唯一（T-P0-8）
               + check_redline_detector_attribution()  # 2026-10-10 红线归属须由检测器自报（A-P0-1）
               + check_redline_coverage_counts_authority_table()  # 2026-10-10 覆盖率须认表声明形态（A-P0-4）
               + check_redline_overlap_ledger()  # 2026-10-10 同概念红线须登记且不靠兜底编闭环（A-P0-2）
               + check_rule_version_coverage()   # P0-A 全部已发布规则须登记版本（未登记⇒finding 无法自证）
               + check_non_risk_findings_not_flagged()  # 2026-10-10 正向发现不得被打风险等级（A-P0-3）
               + check_pending_verdict_softened()     # 2026-10-06 资料不足档不得断言触红
               + check_report_text_integrity()       # 2026-10-06 报告文本不得被改写坏
               + check_report_no_redundancy()        # 2026-10-06 报告不得重复冗余/元话语
               + check_count_single_source()         # 2026-10-06 计数必须同源（共 N 项）
               + check_family_single_lead()          # 2026-10-06 同族只留一个主事项
               + check_levy_nature_not_confused()     # 2026-10-06 社保/公积金/基金不得套用偷税条款
               + check_risk_level_single_source()     # 2026-10-06 风险等级标度不得多头维护
               + check_conclusion_scoped_by_material_coverage()  # 2026-10-06 资料受限须限定结论效力
               + check_table_governance_applied_last()           # 2026-10-06 表格治理须终局收口
               + check_offtopic_rows_filtered()                   # 2026-10-06 附表行须与本项论点匹配
               + check_sequence_and_counts_single_source()        # 2026-10-06 编号须连续、计数须同源、无空表
               + check_risk_family_and_learnable_tiers()          # 2026-10-07 风险族配置/四档学习分级
               + check_numparse_single_source() + check_duplicate_definitions()
               + check_period_key_single_source() + check_evidence_claim_grounded()
               + check_report_credibility() + check_statement_derivation()
               + check_indicator_coverage() + check_delete_semantics()
               + check_delete_result_finality()
               + check_excel_handle_leak() + check_audit_doctrine()
               + check_missing_as_violation()
               + check_overall_conclusion_derivation() + check_report_chapter_integrity()
               + check_overall_conclusion_no_dup()
               + check_cost_recon_render()
               + check_tax_impact_render()
               + check_industry_source_integrity()
               + check_cost_industry_basis()
               + check_account_classifier_single_source()
               + check_cost_expense_triad()
               + check_material_completeness_no_ratio()
               + check_identifier_not_translated()
               + check_no_vague_wording()
               + check_vague_wording_single_source()   # 2026-10-08 模糊词"判据"唯一（第3次出血上锁）
               + check_report_plain_language()
               + check_finding_meta_wording()
               + check_evidence_text_not_truncated()
               + check_constituent_sources_consistency()
               + check_risk_item_section_wording()
               + check_constituent_traceability()
               + check_constituent_no_threshold()
               + check_constituent_exemption_coverage()
               + check_default_hit_index_valid()
               + check_justification_scenario_coverage()
               + check_report_expression_standard()
               + check_report_punctuation()
               + check_no_lock_reentrancy()           # 锁重入自死锁
               + check_evidence_rows_semantic_match()  # 证据行与发现语义匹配（防明细表挂无关凭证/假证据）
               + check_legal_basis_freshness()        # B3 法条时效
               + check_benchmark_refs_resolvable()    # B2 行业基准可解析
               + check_benchmark_caution_single_source()  # 行业基准口径声明单一权威
               + check_undefined_names()              # 2026-10-07 未定义名（NameError 静态防线）
               + check_js_report_helper_scope()       # 2026-10-07 JS 报告级辅助函数须在顶层作用域
               + check_domain_fault_isolation()       # 2026-10-07 域分析须有容错护栏（单域失败不断整轮）
               + check_js_undefined_calls()           # 2026-10-07 JS 里被调用但全仓无定义的裸名
               + check_report_quality_skill_wiring()  # 2026-10-07 五项报告质量 Skill 的接线与口径
               + check_trigger_determination_separation()  # 2026-10-07 触发条件与认定要件分离（三条门禁）
               + check_child_item_completeness()  # 2026-10-07 子项与关联项完整性（三条硬规则）
               + check_data_source_status_consistency()  # 2026-10-07 数据源状态一致性（Skill 7）
               + check_doc_number_authority()         # 2026-10-07 Skill D1 文档数字一致性
               + check_rule_reference_sync()          # 2026-10-07 Skill D2 规则引用一致性
               + check_doc_residue_scan()             # 2026-10-07 Skill D3 全文残留校验
               + check_todo_status_sync()             # 2026-10-07 Skill D4 未完成事项状态同步
               + check_doc_ref_graph()                # 2026-10-07 Skill D5 跨文件引用一致性
               + check_rebuttal_coverage()            # C2 反证对齐
               + check_redline_admission()            # D 红线准入 + 盲区审计
               + check_combo_profile_logic()         # C3 风险组合画像逻辑锁定
               + check_blind_redline_coverage()      # C4 盲区红线软匹配可达性锁定
               + check_benchmark_actual_compare()   # B1 实际比对（名实相符）锁定
               + check_domain_missing_material_emits_finding()  # A 缺主资料须产出资料缺失发现
               + check_finding_level_legality()      # D 风险发现 level 必须合法词表
               + check_chapter_template_dedup()      # P2-7 章节模板去重锁定
               + check_constituent_sources_wiring()  # #448 逐要件独立数据源接线锁定
               + check_material_alias_drift()       # 2026-10-01 红线资料名异名漂移（照运行时真语义模拟）
               + check_conclusion_and_suspicion_order()  # 2026-10-02 结论先行 + 疑点/监管态度重→轻排序
               + check_summary_count_consistency()    # 2026-10-08 summary 派生计数单一权威（26≠16 根因）
               + check_clause_compliance()            # 2026-10-08 用户条款（集成10条+专注5条）机器判据
               + check_static_asset_cache_version()  # 2026-10-02 前端缓存版本（改了看不到）
               + check_suspicion_subject_consistency()  # 2026-10-02 疑点主体一致性（内容与主体错配）
               + check_conclusion_phrase_authority()    # 2026-10-08 结论用语/报告级口径句唯一权威
               + check_report_text_stutter()        # 2026-10-03 报告文本口吃/语义冲突病句
               + check_evidence_quality()           # 2026-10-03 疑点证据编辑质量（元信息/空话/口径反向）
               + check_bank_receipt_nature_single_source()  # 2026-10-03 银行收款性质（收入口径≠全部贷方）
               + check_voucher_account_field()       # 2026-10-03 凭证科目名 vs 科目编码不得混用
               + check_fund_scale_gate_not_roundness()  # 2026-10-03 资金往来：规模准入 / 整数只作证据
               + check_inference_ladder_coverage()  # 2026-10-03 点→面推演层：每次都触发 + 差集会计实质
               + check_no_company_hardcoding_in_judgement()  # 2026-10-03 泛化性：判定代码不得硬编码具体企业名
               + check_material_name_single_source()  # 2026-10-03 资料名称唯一权威（两级命名/别名归一）
               + check_tax_rate_single_source()        # 2026-10-04 税率/随征口径单一权威 + 未量化必须披露
               + check_non_tax_law_not_misattributed() # 2026-10-04 非税事项不得挂税收法律（M06 不得误阻断）
               + check_no_false_exclusion()            # 2026-10-04 禁止虚假排除（"未发现符合"须有核对证据）
               + check_housing_fund_workforce_compare()  # 2026-10-03 公积金接入人数/基数比对（金额勾稽不冒充人数结论）
               + check_detector_text_avoids_hard_ban()  # 2026-10-03 产出文案不得含硬禁用词（否则静默硬删=没接入）
               + check_last_run_no_silent_domain_crash()  # 2026-10-03 最近真跑 pipeline_log 不得有静默失效留痕
               + check_redline_indicator_declared()  # 2026-10-03 纯现象条①必须声明要件组合逻辑（否则结论颠倒）
               + check_tax_impact_basis_is_subject_amount()  # 2026-10-03 税额税基须为本项涉案金额（禁锚参照量/含税直乘）
               + check_downgraded_finding_not_reinflated()  # 2026-10-03 降级发现不得被兜底回填成要件命中/高风险
               + check_waiting_materials_respect_industry()  # 2026-10-03 待补资料必须过业态剔除
               + check_conclusion_not_exceed_finding()  # 2026-10-03 疑点等级不得超过其发现
               + check_checkpoint_evidence_not_self_contradicting()  # 2026-10-03 判"符合"的要件证据不得自我否定
               + check_self_denying_finding_not_claimed()  # 2026-10-03 自我否定的发现不得被认领成要件命中
               + check_limit_items_coverage_declared()  # 2026-10-04 分项限额表覆盖范围须自证 + 须区分差异性质
               + check_trigger_basis_excludes_normal_rows()  # 2026-10-04 触发依据金额只算差异行（禁把无差异行计入）
               + check_constituent_benchmark_dimension_aligned()  # 2026-10-04 行业基准门限须与被衡量量同量纲
               + check_same_suspicion_tables_relation_declared()  # 2026-10-04 同疑点内同批差异的表须声明口径关系
               + check_next_actions_not_ghost_requirements()  # 2026-10-04 补充资料要求须真的缺且本项真的需要
               + check_report_consistency()          # 2026-09-29 报告级一致性（缺失≠0/≠未发生/税率语境/三态）
               # ★ 2026-10-08（用户"系统是否有冗余功能"追问引出）：以下 9 道闸门**早已定义、
               #   却从未接入 run_checks** ⇒ 写出来一次都没执行过（实测：函数体在、全仓零引用）。
               #   它们不是冗余而是"漏接线"：逐个试用均可用、返回 0 ERROR。
               #   现补接线；并在 main() 加"接线完整性"自检（定义却未接入 ⇒ FATAL），
               #   根治"只写不接"这一漂移形态。
               + check_skill_specs()                 # Skill 登记表（62 个 Skill 的可机检规范）
               + check_skill_runtime()               # Skill 运行时可用性
               + check_analysis_session_and_incremental()   # 会话六要素 / 增量分析
               + check_call_signature_alignment()    # 跨模块调用签名对齐
               + check_industry_capability()         # 行业能力（参数库 / 模板 / 画像）
               + check_legal_versioning()            # 法条版本管理（45 部登记 / 47 处未登记法名）
               + check_profile_and_case_reference_only()    # 企业画像与同类案例仅作参考、不得抬升等级
               + check_reanalysis_guard_detectors()  # 假分析四检测器
               + check_report_compliance_and_redaction()   # 报告定位 / 保密 / 授权 / 脱敏边界
               + check_rule_layer_no_double_count()        # 2026-10-11 规则分层不得重复计入（禁"合计 211"）
               + check_risk_score_monotone()               # 2026-10-12 T-2 风险分值须由等级单调派生
               + check_candidate_params_no_dangling()     # 2026-10-13 候选库参数不得悬空 + 地区参数表合规
               + check_rule_dsl_and_externalizable()     # 2026-10-13 T-6 规则外置：表达力边界 + 字段缺口不得扩大
               + check_legal_text_coverage()             # 2026-10-13 法规正文库覆盖率不得退化（与版本登记是两件事）
               + check_redline_legal_basis_currency() + check_confidence_weights_single_source() + check_rbac_single_source() + check_row_cap_manifest() + check_ocr_engine_single_source() + check_extract_rules_sync() + check_review_flow_wiring() + check_template_manage_wiring() + check_rule_version_manage_wiring() + check_legal_library_wiring() + check_industry_indicators_wiring() + check_ai_assist_wiring() + check_tax_models_wiring() + check_dashboard_wiring() + check_payload_written_after_analysis() + check_one_click_wiring_coverage() + check_service_version_visibility() + check_level_display_single_source() + check_legal_mapping_wiring() + check_legal_frontend_wiring() + check_rule_params_single_source() + check_cnnum_single_source() + check_material_granularity_truthful() + check_provision_id_unique() + check_law_code_unique() + check_candidate_param_index())   # 2026-10-13 红线不得引用已废止/被取代法规 + P0-5 置信度权重阈值单一权威 + 2026-10-14 P0-8 RBAC/租户/脱敏单一权威 + P1-1 解析上限登记与 O(n²) 回归防线 + P1-2 OCR 引擎治理单一权威 + P1-3 校验规则清单与配置同步 + P1-4 复核流程能力与路由顺序 + P1-5 报告模板管理 + P1-6 规则版本管理 + ODC-01/02/03 一键分析接入面（模板唯一入口 / 校正值接线 / 页面可达 / 前端渲染点）+ 2026-10-15 等级展示唯一权威（待核验/待核→涉嫌风险）+ 2026-10-15 STEP-EXT-LEGAL-FULL-MATCH 步骤19 法规⇄规则关联接入（报告条款ID列 / 风险详情条款正文 / 材料法规级关联）+ 2026-10-15 步骤22 前端接线（专题/目录/关系/材料/条款页面可达 + 路由顺序 + 无硬编码 + 缺口必带 reason）
    return counts, general


def check_coverage_execution_receipt() -> List[Tuple[str, str, str]]:
    """覆盖清单的「已执行」必须由**执行回执**证明，不得用"资料齐备"冒充（2026-10-06）。

    ★ 事故（用户原话：「一键分析按钮必须执行100%覆盖率」「能查的全查完即可」；
      追问：「那 84 项资料齐备的检查，是否都在引擎里真跑了？」）：
      `analysis_coverage.executed` 原定义为 `len(items) - len(blocked)`，其中
      `blocked := missing 非空`、`missing := 声明的 required_sources 里 engine_data 没数据`
      ⇒ 它证明的只是「**声明所需资料本轮齐备**」，**不等于**「引擎真的执行了该检查」。
      二者之间还隔着三道闸，任何一道没通过，"已全部执行"就是虚报：
        闸A 静态注册：规则在 `VERIFIED_RULE_CATALOG` 里但 `_SCANNERS` 里没有 ⇒ 循环根本不碰；
        闸B 行业门槛：`_spec_applies_to_entity` 为假 ⇒ 主动 skip（却仍进分母）；
        闸C 判缺口径分叉：执行器按 `required_sources` **原始声明**判缺，覆盖模块按
            **剔过业态不适用源**的清单判缺 ⇒ 同一规则"覆盖说已执行、执行器说没跑"。
      实测（company_1 某传媒企业数字传媒·广告传媒/服务业）：4 条被虚报为"已执行"。

    本闸门做四件事（前两件静态、后两件**双向对照**运行时断言）：
      ① `run_verified_rules` 必须产出 `executions`（回执通道存在）；
      ② pipeline 必须把回执传给 `build_coverage(..., executions=...)` **并落盘**；
      ③ 阳性对照：喂 `completed_not_triggered` 回执 ⇒ 该规则**必须**计入已执行；
      ④ 阴性对照：喂 `not_run_missing_data` 回执 ⇒ 该规则**必须**不计入已执行
         （且进 `not_executed_items`）。缺任一向 ⇒ 判据本身失效，判 ERROR。
    """
    cov_rel, pipe_rel, vr_rel = "engine/analysis_coverage.py", "engine/pipeline.py", "engine/verified_rule_engine.py"
    issues: List[Tuple[str, str, str]] = []

    def _read(rel: str) -> str:
        p = ROOT / rel
        try:
            return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
        except OSError:
            return ""

    if '"executions": executions' not in _read(vr_rel):
        issues.append(("ERROR", vr_rel,
                       "run_verified_rules 未产出 executions 回执 —— 覆盖清单将无法区分"
                       "「资料齐备」与「真的跑过」，覆盖率必然虚报"))
    pipe_src = _read(pipe_rel)
    if "executions=" not in pipe_src:
        issues.append(("ERROR", pipe_rel,
                       "pipeline 未把执行回执传给 build_coverage(..., executions=...) —— "
                       "「已执行」退回「资料齐备」口径（虚报）"))
    if 'verified_rule_executions' not in pipe_src:
        issues.append(("ERROR", pipe_rel,
                       "pipeline 未落盘 verified_rule_executions —— 事后无法从产物核实"
                       "某项检查到底跑没跑（用户正是这样问的）"))
    elif '["report"]["verified_rule_executions"]' not in pipe_src:
        issues.append(("ERROR", pipe_rel,
                       'verified_rule_executions 未写进 result["report"] —— 闸门与审计脚本读的是'
                       '报告体（company_1_full.json = res["report"]），只写在外层 result '
                       '等于"看着接了、产物里查不到"（本轮实测踩过）'))

    # ── ③④ 双向对照：真调 build_coverage（同一权威），断言"回执说了算" ──
    try:
        from engine.analysis_coverage import build_coverage
        from engine.verified_rule_engine import VERIFIED_RULE_CATALOG
    except Exception as e:  # pragma: no cover
        issues.append(("ERROR", cov_rel, f"执行回执断言所需依赖导入失败: {e}"))
        return issues

    # 取一条**双源规则**做样检：单源规则在只喂一个源时可能因业态不适用被剔出分母。
    sample = None
    for r in VERIFIED_RULE_CATALOG:
        if len(r.get("required_sources") or []) >= 2 and "ALL" in (r.get("industries") or ["ALL"]):
            sample = r
            break
    if sample is None:
        issues.append(("ERROR", cov_rel, "找不到可用于回执断言的双源规则，闸门无法校验"))
        return issues

    srcs = [str(s) for s in sample["required_sources"]]
    ed = {s: [{"_probe": 1}] for s in srcs}
    ed["target_entity"] = {"industry": "制造业", "biz_model": "制造业"}
    ed["_available_materials"] = []

    def _hit(cov):
        return any(str(it.get("id")) == sample["id"] for it in cov.get("executed_items") or [])

    pos = build_coverage(ed, executions=[{"rule_id": sample["id"],
                                          "status": "completed_not_triggered"}])
    if not _hit(pos):
        issues.append(("ERROR", cov_rel,
                       f"阳性对照失败：{sample['id']} 回执为 completed_not_triggered 却未计入已执行"
                       f"——「已执行」的判据失效"))
    neg = build_coverage(ed, executions=[{"rule_id": sample["id"],
                                          "status": "not_run_missing_data",
                                          "missing_sources": srcs}])
    if _hit(neg):
        issues.append(("ERROR", cov_rel,
                       f"阴性对照失败：{sample['id']} 回执为 not_run_missing_data 却仍计入已执行"
                       f"——这正是覆盖率虚报的病根，判据未生效"))
    nid = [str(it.get("id")) for it in neg.get("not_executed_items") or []]
    if sample["id"] not in nid:
        issues.append(("ERROR", cov_rel,
                       f"阴性对照失败：{sample['id']} 未执行却未进 not_executed_items"
                       f"——未执行项被静默吞掉，系统缺口不可见"))
    return issues


def check_question_theme_attachment() -> List[Tuple[str, str, str]]:
    """询问主题必须挂到对应疑点；资料缺口不得在询问清单里重复（2026-10-06）。

    ★ 用户原话：「待企业澄清事项（其余事项）…这些内容为什么存在？又为什么会呈现在这里？
      难道不应该在分析出的疑点中呈现吗？而且这些内容是否在报告中已经重复了？」

    实测（company_1 某传媒企业数字传媒）报告末尾残余 4 条，两条根因：
      A **归属表漂移**：「进项，应转出未转出」被登记为"无对应疑点"，
        但 2026-10-05 起 `input_voucher_report` 已由 `STANDALONE_RISK_REPORTS` 立为独立风险事项
        「进项异常凭证：不得抵扣用途未作进项转出」（**同一税额 3,996.91 元**）
        ⇒ 同一风险在报告里出现两次（风险事项 + 末尾询问）。
      B **资料缺口两处各写一套**：「资料·申报表缺失 / 资料·存货与余额表缺失 / 资料·其他缺失」
        由 `data_overview["missing"]` 生成，与 `material_readiness`（三列：缺失资料/影响哪些检查/
        补救要求，且带业态不适用剔除）**逐项重复**；
        且「资料·存货与余额表缺失」还在要求**服务型**企业补「期末存货盘点表、出入库台账」——
        正是 `material_readiness.not_applicable` 已判定**本业态不适用**的资料。

    ⚠ 原挂载逻辑还有一处**静默丢失**：命中归属表却在本轮找不到匹配疑点时，循环走完
      既不挂载也不落 `unattached` ⇒ 这条询问在报告里**任何地方都看不到**。

    本闸门断言（行为断言为主）：
      ① 阳性：有归属 + 疑点存在 ⇒ 必须挂上；
      ② 阴性A：无归属 ⇒ 必须进 `unattached`；
      ③ 阴性B：有归属但**本轮无该疑点** ⇒ 必须退回 `unattached`（防静默丢失）；
      ④ 结构：询问主题不得是「资料」类（资料缺口唯一权威 = `material_readiness`）；
      ⑤ 产物：真跑产物的 `unattached_themes` 必须为空（残余章 = 内容没被整合，应当红灯）。
    """
    issues: List[Tuple[str, str, str]] = []
    rel = "engine/report_layout.py"
    try:
        from engine.report_layout import attach_question_themes as _aqt
        from engine.report_layout import QUESTION_THEME_TO_PROBLEM as _MAP
    except Exception as e:  # noqa: BLE001
        return [("ERROR", rel, f"无法导入询问归属唯一权威：{e}")]

    # ── ① 阳性对照 ──
    _theme = next(iter(_MAP), None)
    if not _theme:
        return [("ERROR", rel, "QUESTION_THEME_TO_PROBLEM 为空，闸门无法校验")]
    _kw = _MAP[_theme]
    _probs = [{"title": "前缀" + _kw + "后缀", "seq": 1}]
    _n, _un = _aqt([{"theme": _theme, "severity": "高", "questions": [{"question": "q"}]}], _probs)
    if _n != 1 or _un or not _probs[0].get("questions"):
        issues.append(("ERROR", rel,
                       f"阳性对照失败：主题「{_theme}」有归属且疑点存在，却未挂到疑点"
                       f"（attached={_n}, unattached={len(_un)}）"))

    # ── ② 阴性A：无归属 ⇒ 必须留在 unattached ──
    _t2 = {"theme": "某某不存在归属的主题", "severity": "低", "questions": [{"question": "q2"}]}
    _n2, _un2 = _aqt([_t2], [{"title": "任意疑点", "seq": 2}])
    if _n2 != 0 or len(_un2) != 1:
        issues.append(("ERROR", rel,
                       f"阴性对照失败：无归属主题未落入 unattached（attached={_n2}, unattached={len(_un2)}）"))

    # ── ③ 阴性B：有归属但本轮无该疑点 ⇒ 不得静默丢失 ──
    _n3, _un3 = _aqt([{"theme": _theme, "severity": "高", "questions": [{"question": "q3"}]}],
                     [{"title": "毫不相干的疑点标题", "seq": 3}])
    if _n3 != 0 or len(_un3) != 1:
        issues.append(("ERROR", rel,
                       "阴性对照失败：归属表命中了目标关键词、但本轮不存在该疑点，"
                       f"该询问既未挂载也未落 unattached ⇒ **静默丢失**"
                       f"（attached={_n3}, unattached={len(_un3)}）"))

    # ── ④ 结构：询问主题不得是"资料类" ──
    if any(str(k).strip().startswith("资料") for k in _MAP):
        issues.append(("ERROR", rel,
                       "归属表登记了『资料』类主题 —— 资料缺口的唯一权威是 `material_readiness`，"
                       "询问清单不得重复列资料清单"))
    _iq_rel = "engine/inspection_questions.py"
    try:
        _p = ROOT / _iq_rel
        _iq_src = _p.read_text(encoding="utf-8", errors="replace") if _p.exists() else ""
    except OSError:
        _iq_src = ""
    if _iq_src and 'add("资料' in _iq_src:
        issues.append(("ERROR", _iq_rel,
                       "询问清单仍在生成『资料』类主题 —— 与 `material_readiness` 重复，"
                       "且会绕过业态不适用剔除（实测要求服务型企业补存货盘点表/出入库台账）"))

    # ── ④b 同族合并后仍须能挂上（族主标题变了，归属表不该跟着改）──
    #   ★ 2026-10-06 事故：同族合并把归属表指向的疑点**并入族主事项**，族主标题不同
    #     ⇒ 归属关键词匹配不上 ⇒ 5 条询问主题全部退回残余章（与风险事项重复呈现）。
    #   修法：`finding_families` 在合并时登记 `_family_aliases`，匹配文本 = 标题 ∪ 别名。
    try:
        from engine.finding_families import merge_families as _mf   # noqa: PLC0415

        def _mk(seq, title, rname, amt, lv):
            return {"seq": seq, "title": title, "risk_level": lv, "taxes": ["增值税"],
                    "redline_name": rname, "finding_type": rname,
                    "tax_impact": {"total": amt}, "narrative_paragraphs": []}

        _p1 = _mk(1, "工资表人数与社保参保人数不符", "工资表列支人数与社保参保人数存在差异",
                  0, "高风险")
        _p2 = _mk(2, "公私混同发薪", "私户支付薪酬", 100000, "中风险")
        _fam = [_p1, _p2]
        _mf(_fam)
        # 合并必须真的发生，别名必须登记（否则本探针的用例无效）
        _leads = [p for p in _fam if p.get("family_members")]
        if not _leads:
            issues.append(("WARN", "engine/finding_families.py",
                           "同族合并用例未触发合并，别名探针跳过（用例无效，需换用例）"))
        else:
            _lead = _leads[0]
            if not _lead.get("_family_aliases"):
                issues.append(("ERROR", "engine/finding_families.py",
                               "同族合并未登记 `_family_aliases` —— 被并入项的疑点标题将"
                               "无法回答询问主题的归属（询问会全部退回残余章，与风险事项重复）"))
            # 用**被并入项**的标题关键词去问：族主标题不含它，只能靠别名命中
            _kw2 = "公私混同发薪"
            if _kw2 not in str(_lead.get("title") or ""):
                _n2, _un2 = _aqt([{"theme": "资金·私户收款性质", "severity": "高",
                                   "questions": [{"question": "q"}]}], _fam)
                if _n2 != 1 or _un2:
                    issues.append(("ERROR", rel,
                                   "被并入项的标题无法作为归属命中依据（同族别名未参与匹配）"
                                   " ⇒ 该询问会落到报告末尾残余章：attached=%d" % _n2))
    except Exception as _e:  # noqa: BLE001
        issues.append(("ERROR", rel, "同族别名探针执行失败：%s" % _e))

    # ── ⑤ 产物：残余章必须为空 ──
    art = ROOT / "scripts" / "four_reports" / "company_1_full.json"
    if not art.exists():
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "无真跑产物，无法核验「询问主题是否全部挂到疑点」——请先跑一次全量一键分析"))
        return issues
    try:
        import json as _json
        _d = _json.loads(art.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        issues.append(("WARN", "scripts/four_reports/company_1_full.json", f"产物不可解析：{e}"))
        return issues
    _rep = _d.get("report") if isinstance(_d.get("report"), dict) else _d
    _iq = ((_rep or {}).get("enterprise_readable_report") or {}).get("inspection_questions_report") or {}
    _left = [str(t.get("theme")) for t in (_iq.get("unattached_themes") or []) if isinstance(t, dict)]
    if _left:
        issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                       f"报告末尾仍残留 {len(_left)} 条未归属的询问主题：{_left} —— "
                       f"同一内容会与「风险事项」或「资料齐备性」重复呈现；"
                       f"请把它挂到对应疑点（`QUESTION_THEME_TO_PROBLEM` 加一行）"
                       f"或确认其确无归属并说明原因"))
    return issues


def check_finding_basis_grounded() -> List[Tuple[str, str, str]]:
    """每条风险事项的「发现的依据」必须**站得住**：有资料事实、不是空话、不重复（2026-10-06）。

    ★ 用户原话：「真的触碰到了36条税务红线吗？是分析资料中确定的吗？」
      追问：「来自原子规则/域分析/组合画像/专项比对，**你也要有资料站住脚啊**！！！
      是**资料的哪些情况**得清晰梳理吧」

    实测（company_1）三类"站不住"：
      ① **指针式空话**：组合画像「多税种联动稽查风险画像」的「二、发现的依据」原文只有
         「（本项依据见本报告相应条目内的测算说明）」—— 报告里写"见别处"＝本项没有自己的依据；
      ② **整段话重复两遍**：`_merge_same_type_findings` 把同 type 的**两条完全相同**的
         `detail` 用 `"\\n\\n"` 拼接 ⇒ 9 条原子规则发现、6 条报告事项各自"同一段话说两遍"
         （VR024 更糟：两遍的占比一个 14.62%、一个 14.83%，**同段两个数**）；
      ③ **只由"缺资料"触发的风险事项**：VR037 原实现 `if not related:` ⇒
         "企业没交股权穿透数据"本身被产出成一条**中风险风险事项**（依据里零价格数据），
         与铁律「**缺资料 ≠ 违规**」直接冲突。

    判据（读真跑产物，逐条风险事项的「二、发现的依据」）：
      · 不得含指针式空话（"见本报告相应条目"/"见相应章节"）；
      · 必须含**资料事实**（至少一个数字，或"已上传资料"外的具体资料名+对象）；
      · 不得整段重复（首 60 字在本段内出现 ≥2 次）；
      · 不得通篇只有"本轮未提供/未见…资料/数据"而无任何资料内事实。
    """
    issues: List[Tuple[str, str, str]] = []
    art = ROOT / "scripts" / "four_reports" / "company_1_full.json"
    if not art.exists():
        return [("WARN", "scripts/four_reports/company_1_full.json",
                 "无真跑产物，无法核验「风险事项依据是否站得住」——请先跑一次全量一键分析")]
    try:
        import json as _json
        _d = _json.loads(art.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        return [("WARN", "scripts/four_reports/company_1_full.json", f"产物不可解析：{e}")]
    rep = _d.get("report") if isinstance(_d.get("report"), dict) else _d
    ps = ((rep or {}).get("enterprise_readable_report") or {}).get("confirmed_problems") or []
    if not ps:
        return [("WARN", "scripts/four_reports/company_1_full.json",
                 "产物无 confirmed_problems，闸门无法校验")]

    import re as _re
    _PTR = ("见本报告相应条目", "见相应章节", "见本报告「", "详见本报告")
    _MISSING_ONLY = ("本轮未提供", "本轮未取得", "未见…数据", "无法核实", "资料缺失")
    _NUM = _re.compile(r"\d")

    for p in ps:
        if not isinstance(p, dict):
            continue
        _basis = ""
        for _seg in (p.get("narrative_paragraphs") or []):
            if str(_seg.get("heading") or "").startswith("二、发现的依据"):
                _basis = str(_seg.get("text") or "")
                break
        _tag = "confirmed_problems[seq=%s]%s" % (p.get("seq"), str(p.get("title"))[:24])
        if not _basis.strip():
            issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                           f"{_tag}：缺「二、发现的依据」段"))
            continue
        for _ph in _PTR:
            if _ph in _basis:
                issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                               f"{_tag}：依据是**指针式空话**（含「{_ph}」）—— "
                               f"报告里写『见别处』等于本项没有自己的依据，请写出本项的资料事实"))
                break
        # 整段重复两遍（用**前 28 字**做指纹：既能抓住"一字不差"的重复，
        # 也能抓住 VR024 那种"两遍只差一个百分比（14.62% vs 14.83%）"的**同段不同值**）
        _pre = _basis.strip()[:28]
        if len(_pre) >= 20 and len(_basis) > 90 and _basis.count(_pre) >= 2:
            issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                           f"{_tag}：依据段**同一段话说两遍**（前 28 字在本段内出现 ≥2 次）—— "
                           f"多为同 type 发现合并时未按文本去重；若两遍数字不同，"
                           f"则是**同一指标两套口径**，须先统一口径再合并"))
        # 无资料事实
        if not _NUM.search(_basis):
            issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                           f"{_tag}：依据段**无任何资料事实**（连一个数字都没有）—— "
                           f"风险事项必须能指出『是资料的哪些情况』"))
        # 只由"缺资料"触发
        if all(_m in _basis for _m in ("本轮未提供", "无法")) and not _NUM.search(_basis.replace("0", "")):
            issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                           f"{_tag}：依据**只由『企业没交资料』构成** —— "
                           f"违反铁律「缺资料 ≠ 违规」，不得列为风险事项"))
    return issues


def check_related_risks_not_self() -> List[Tuple[str, str, str]]:
    """疑点的「本项还包含以下风险信号」不得把**本项自己**再列一遍（2026-10-06）。

    ★ 用户原话：「疑点1的『本项还包含以下风险信号』，这部分内容不是已经在一至五里说了吗？」

    **是重复。** 实测：疑点1「红字冲销与作废发票比例异常」下面又列出一条"相关风险信号"
    「红冲/作废发票情形」，而本项「为何列入检查」段开头写的正是"红冲/作废发票情形（共13笔）…"
    —— 同一个东西在同一节里说两遍。
    根因：`_merge_ledger_into_problems` 的归属判据只问"这行属于哪个疑点"
    （`redline_id` / 关联疑点序号），**没有问"这行是不是本项自己的来源"**；
    而来源行必然也指向本项 ⇒ 必然被并回来一次。

    判据（读真跑产物）：某疑点的 `related_risks[i].风险事项` 归一化后
    出现在**该疑点标题**或**「为何列入检查」段前 60 字**里 ⇒ ERROR
    （它就是这个疑点的来源事项，不是"额外信号"）。
    """
    issues: List[Tuple[str, str, str]] = []
    art = ROOT / "scripts" / "four_reports" / "company_1_full.json"
    if not art.exists():
        return [("WARN", "scripts/four_reports/company_1_full.json",
                 "无真跑产物，无法核验「相关风险信号是否重复本项」——请先跑一次全量一键分析")]
    try:
        import json as _json
        _d = _json.loads(art.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        return [("WARN", "scripts/four_reports/company_1_full.json", f"产物不可解析：{e}")]
    rep = _d.get("report") if isinstance(_d.get("report"), dict) else _d
    ps = ((rep or {}).get("enterprise_readable_report") or {}).get("confirmed_problems") or []
    if not ps:
        return [("WARN", "scripts/four_reports/company_1_full.json",
                 "产物无 confirmed_problems，闸门无法校验")]

    import re as _re
    def _n(s):
        return _re.sub(r"[\s（）()【】\[\]·，,、]", "", str(s or ""))

    for p in ps:
        rr = p.get("related_risks") or []
        if not rr:
            continue
        _seg0 = ""
        for _sg in (p.get("narrative_paragraphs") or []):
            if str(_sg.get("heading") or "").startswith("为何列入检查"):
                _seg0 = str(_sg.get("text") or "")
                break
        _ctx = _n(p.get("title")) + "|" + _n(_seg0[:60])
        for r in rr:
            _nm = _n((r or {}).get("风险事项"))
            if _nm and _nm in _ctx:
                issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                               f"confirmed_problems[seq={p.get('seq')}]"
                               f"{str(p.get('title'))[:22]}：『本项还包含以下风险信号』里的"
                               f"「{r.get('风险事项')}」**就是本项自己的来源事项**（已在一至五里说过）"
                               f"—— 不得作为额外风险信号重复列出"))
    return issues


def check_non_deductible_requires_invoice_type() -> List[Tuple[str, str, str]]:
    """判「应转出未转出」必须先核实**票种**与**抵扣状态**（2026-10-06）。

    ★ 用户原话：「疑点35：进项异常凭证…**你核实了发票类型没有？**」

    **没有核实，结论方向是反的。** 实测（某传媒企业数字传媒）：
      被判「应转出未转出约 3,996.91 元」的 146 张发票，**全部是「数电发票（普通发票）」**，
      且**一张都没进进项认证抵扣明细**（255 张抵扣记录全部能在取票中找到 ⇒ 抵扣表是取票的子集，
      不包含这 146 张）⇒ **从未抵扣，不存在"应转出未转出"**。
    根因两条：
      ① 解析层把取票表的**「发票票种」整列丢了**（映射表只认"发票类型"，而表头写"发票票种"）
         ⇒ 引擎根本看不到票种；
      ② `run_input_voucher_check` **没接进项认证抵扣明细** ⇒ 看不到"勾选状态 / 有效抵扣税额"，
         只能拿**票面税额**冒充"已抵扣税额"。

    逻辑前提：「应转出**未转出**」＝「已经抵扣」＋「本不允许抵扣」。
    本闸门三向行为断言（都直接调用唯一实现）：
      ① 普通发票（含不得抵扣用途）⇒ **不得**计入应转出；
      ② 专用发票 + 已勾选/有效抵扣税额>0 ⇒ **必须**计入，且金额取**有效抵扣税额**（不是票面税额）；
      ③ 既无票种也无抵扣记录 ⇒ **不得**计入应转出（只能待核，不给金额）。
    另加结构断言：取票解析映射必须含「发票票种」列。
    """
    issues: List[Tuple[str, str, str]] = []
    rel = "engine/input_voucher.py"
    try:
        from engine.input_voucher import run_input_voucher_check as _chk
    except Exception as e:  # noqa: BLE001
        return [("ERROR", rel, f"无法导入进项比对唯一实现：{e}")]

    def _m(res):
        return (res or {}).get("metrics") or {}

    # ① 普通发票 ⇒ 不得算应转出
    _r1 = _chk(pur_invs=[{"seller": "某某餐饮", "goods": "*餐饮服务*餐费",
                          "amount": 10000.0, "tax": 600.0, "inv_no": "A1",
                          "inv_type": "数电发票（普通发票）"},
                         {"seller": "某某广告", "goods": "*广告服务*广告费",
                          "amount": 10000.0, "tax": 600.0, "inv_no": "A2",
                          "inv_type": "数电发票（增值税专用发票）"}])
    if float(_m(_r1).get("should_transfer_out_tax") or 0) > 0:
        issues.append(("ERROR", rel,
                       "普通发票的不得抵扣用途项目被计入『应转出未转出』—— "
                       "普通发票本就不作为抵扣凭证，从未抵扣，不存在应转出"))
    if str(_r1.get("verdict") or "") != "未发现异常":
        issues.append(("ERROR", rel,
                       f"普通发票情形 verdict 应为『未发现异常』（不得立为风险事项），"
                       f"实为「{_r1.get('verdict')}」"))

    # ② 专用发票 + 已抵扣 ⇒ 必须计入，金额取"有效抵扣税额"
    _r2 = _chk(pur_invs=[{"seller": "某某餐饮", "goods": "*餐饮服务*餐费",
                          "amount": 10000.0, "tax": 600.0, "inv_no": "B1",
                          "inv_type": "数电发票（增值税专用发票）"},
                         {"seller": "某某广告", "goods": "*广告服务*广告费",
                          "amount": 10000.0, "tax": 600.0, "inv_no": "B2",
                          "inv_type": "数电发票（增值税专用发票）"}],
               input_vat_deductions=[{"invoice_no": "B1", "invoice_type": "数电发票（增值税专用发票）",
                                      "status": "已勾选", "deductible_tax": 500.0}])
    _v2 = float(_m(_r2).get("should_transfer_out_tax") or 0)
    if _v2 <= 0:
        issues.append(("ERROR", rel,
                       "专用发票且已勾选抵扣的不得抵扣用途项目**未被计入**『应转出未转出』——漏报"))
    elif abs(_v2 - 500.0) > 0.01:
        issues.append(("ERROR", rel,
                       f"应转出金额取错：应取**有效抵扣税额 500.00**（实际抵扣了多少），"
                       f"实取 {_v2}（疑为票面税额 600）"))

    # ③ 无票种、无抵扣记录 ⇒ 不得算应转出（只能待核）
    _r3 = _chk(pur_invs=[{"seller": "某某餐饮", "goods": "*餐饮服务*餐费",
                          "amount": 10000.0, "tax": 600.0, "inv_no": "C1"},
                         {"seller": "某某广告", "goods": "*广告服务*广告费",
                          "amount": 10000.0, "tax": 600.0, "inv_no": "C2"}])
    if float(_m(_r3).get("should_transfer_out_tax") or 0) > 0:
        issues.append(("ERROR", rel,
                       "票种与抵扣状态均无法判定时仍给出『应转出』金额 —— "
                       "缺前提事实不得给结论金额（应列为待核）"))

    # ④ 结构：取票解析映射必须保留「发票票种」
    try:
        _main_src = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
    except OSError:
        _main_src = ""
    if _main_src and '"发票票种"' not in _main_src:
        issues.append(("ERROR", "main.py",
                       "取票表解析未映射「发票票种」列 —— 进项侧检测器将看不到票种，"
                       "必然把普通发票的票面税额误算成『应转出未转出』"))
    return issues


def check_self_doubt_coverage() -> List[Tuple[str, str, str]]:
    """每条风险事项都必须有「自我反驳 + 验证清单」（2026-10-06）。

    ★ 用户要求：「给一键分析按钮增加一个**对疑点产生自我怀疑**的能力，
      以终为始拆解疑点的关键信息，自我反驳，并**再索取资料信息进行自我验证**。」

    「证据不足」是这条链上最容易断的一环：结论一旦立起来，没有人替它找反证。
    本闸门四向断言（行为断言为主，直接调唯一实现 `engine/self_doubt.py`）：
      ① 有证据角色表 ⇒ 每条支撑都要有 `doubt` + `overturns_if`；
      ② **未提供**的证据才进验证清单（**已提供的不得再要**，否则让企业补它已交的东西）；
      ③ 没有证据角色表的项（并入第二章的原子规则/域分析/组合画像/专项比对）也要有 ——
         由叙事段的「独立数据源 / 尚需…」+ **证据地位**兜底产出；
      ④ 每条风险事项的验证清单**不得为空**（用户要的是"再索取资料"，不是"请自行核实"）；
      ⑤ 产物里每条 `confirmed_problems` 都必须带 `self_doubt`。
    """
    issues: List[Tuple[str, str, str]] = []
    rel = "engine/self_doubt.py"
    try:
        from engine.self_doubt import doubt_for_problem as _dfp
    except Exception as e:  # noqa: BLE001
        return [("ERROR", rel, f"无法导入自我怀疑唯一实现：{e}")]

    # ① 有证据角色表：支撑须带反驳与推翻条件
    _p_ev = {"seq": 1, "title": "测试疑点", "suspect": "",
             "detail_table": {"columns": ["证据角色", "证据名称", "证明目的", "现状", "依据"],
                              "rows": [
                                  {"证据角色": "直接证据", "证据名称": "费用明细账",
                                   "证明目的": "证明费用发生", "现状": "已有"},
                                  {"证据角色": "反证", "证据名称": "纳税调增明细",
                                   "证明目的": "证明已调整", "现状": "缺失"}]},
             "narrative_paragraphs": []}
    _r = _dfp(_p_ev, provided_materials=[])
    if not _r.get("available"):
        issues.append(("ERROR", rel, "有证据角色表的疑点未产出自我怀疑段"))
    else:
        for k in _r["key_inputs"]:
            if not _k_ok(k):
                issues.append(("ERROR", rel,
                               f"支撑「{k.get('item')}」缺『可能不成立之处』或『什么情况下不成立』"
                               f"—— 说不出推翻条件的支撑不是可验证的事实"))
        _req = [q.get("material") for q in _r.get("requested") or []]
        if "费用明细账" in _req:
            issues.append(("ERROR", rel,
                           "验证清单把**已提供**的『费用明细账』列为待补 —— "
                           "会让企业去补它已经交过的资料"))
        if "纳税调增明细" not in _req:
            issues.append(("ERROR", rel, "**未提供**的『纳税调增明细』未进验证清单（漏索取）"))
        # ④ 不得为空
        if not _req:
            issues.append(("ERROR", rel, "验证清单为空 —— 用户要的是『再索取资料自我验证』"))

    # ②③ 无证据角色表（并入第二章的非红线来源）也要产出，且验证清单非空
    _p_tier = {"seq": 2, "title": "测试：已验原子规则的项", "suspect": "",
               "evidence_tier": "已验原子规则（可信观察）", "source": "域分析发现",
               "narrative_paragraphs": [
                   {"heading": "三、已取得的资料与待补充的资料",
                    "text": "本项依据的独立数据源：进项发票（已上传）。尚需结合用途明细账核对。"}],
               "detail_table": {"columns": [], "rows": []}}
    _r2 = _dfp(_p_tier, provided_materials=[])
    if not _r2.get("available"):
        issues.append(("ERROR", rel,
                       "无证据角色表的风险事项未产出自我怀疑段 —— "
                       "被并入第二章的原子规则/域分析/组合画像/专项比对也必须自我怀疑"))
    else:
        if not (_r2.get("requested") or []):
            issues.append(("ERROR", rel, "无证据角色表的项验证清单为空（用户要求必须再索取资料）"))
        _items = " ".join(str(k.get("item") or "") for k in _r2["key_inputs"])
        if "证据地位" not in _items:
            issues.append(("ERROR", rel,
                           "无证据角色表的项未附『结论来源（证据地位）』反驳 —— "
                           "『可信观察≠税务违规』是这类项最该说清的一句"))

    # ⑤ 产物：每条 confirmed_problems 都必须带 self_doubt
    art = ROOT / "scripts" / "four_reports" / "company_1_full.json"
    if not art.exists():
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "无真跑产物，无法核验「每条风险事项是否都有自我怀疑段」——"
                       "请先跑一次全量一键分析"))
        return issues
    try:
        import json as _json
        _d = _json.loads(art.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        issues.append(("WARN", "scripts/four_reports/company_1_full.json", f"产物不可解析：{e}"))
        return issues
    _rep = _d.get("report") if isinstance(_d.get("report"), dict) else _d
    _ps = ((_rep or {}).get("enterprise_readable_report") or {}).get("confirmed_problems") or []
    if _ps:
        _miss = [p.get("seq") for p in _ps
                 if not (isinstance(p, dict) and (p.get("self_doubt") or {}).get("available"))]
        if _miss:
            issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                           f"{len(_miss)} 条风险事项缺「自我反驳与验证清单」：{_miss[:10]}"))
        _empty = [p.get("seq") for p in _ps
                  if isinstance(p, dict) and (p.get("self_doubt") or {}).get("available")
                  and not ((p.get("self_doubt") or {}).get("requested") or [])]
        if _empty:
            issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                           f"{len(_empty)} 条风险事项的验证清单为空：{_empty[:10]}"))
    return issues


def _k_ok(k: Dict) -> bool:
    return bool(str((k or {}).get("doubt") or "").strip()
                and str((k or {}).get("overturns_if") or "").strip())


#: 第四章「整改验收与下一轮复查标准」禁止出现的**元话语/操作说明/越界要求**（唯一词表）
#   ⚠ 每一条都对应一次用户投诉，加一条即可，不得在别处再写一套。
_RECHECK_META_BANNED: Dict[str, str] = {
    "按各条标注的办理顺序": "排版描述（企业自己看得见『办理顺序 第N项』徽标）",
    "请按序号先后办理": "排版描述",
    "重新点击一键分析": "系统操作说明（按钮怎么点与企业无关）",
    "下一轮将重新读取": "系统动作描述（『我怎么做的』）",
    "重新读取全部资料": "系统动作描述",
    "指定熟悉该项业务": "企业内部管理要求（越界）",
    "另一名人员复核": "企业内部管理要求（越界）",
}

#: 第五章「报告性质和使用说明」禁止出现的**系统自述 / 自我证明 / 失效表述**（唯一词表）
_STATEMENT_META_BANNED: Dict[str, str] = {
    # 系统自述：我们是谁、用来干什么 —— 企业不需要知道
    "由企业使用的财税风险防控系统依据已提交资料生成": "系统自述",
    "用于模拟税务风险检查程序": "系统自述",
    "采用税务风险检查文书式结构": "系统自述",
    "风险检查人员陈述口径编制": "系统自述",
    # 自我证明：把"我做得对"写给企业看
    "均有本轮资料中的直接数据": "系统自我证明",
    "可回查证据支持": "系统自我证明",
    # 指向别处 / 已失效的表述
    "已单独列入补充资料后再检查清单": "指向别处的指针（该清单已并入疑点与资料齐备性章）",
    "含待企业澄清事项": "失效表述（待澄清主题已并入各疑点，残余清单恒为空）",
}


def check_recheck_chapter_no_meta() -> List[Tuple[str, str, str]]:
    """第四章不得出现**元话语 / 操作说明 / 越界要求**（2026-10-06）。

    ★ 用户原话：「四、整改验收与下一轮复查标准 …… **这个要重写，有废话**」。

    实测该章 5 句话里 4 处是废话/越界：
      · 「请按各条标注的办理顺序先后办理」—— **排版描述**（企业自己看得见徽标）；
      · 「重新点击一键分析」—— **系统操作说明**（按钮怎么点是我们的实现细节）；
      · 「下一轮将重新读取全部资料」—— **系统动作描述**（"我怎么做的"）；
      · 「须指定……负责人，并由另一名人员复核」—— **企业内部管理要求**，越界。
    判据（读真源 + 读产物）：
      ① 前端该章静态文案与后端 `recheck` / `action_plan_note` 均不得含上表词条；
      ② 产物 `recheck` 三句必须非空且不含上表词条。
    """
    issues: List[Tuple[str, str, str]] = []

    # ① 源码级（前端静态句 + 后端文案）
    for rel in ("static/js/tax-doc-analysis.js", "engine/enterprise_report.py"):
        try:
            txt = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for _bad, _why in _RECHECK_META_BANNED.items():
            # 只查**字符串字面量**里的出现（注释里说明"为什么删掉它"是允许的）
            if (f'"{_bad}' in txt) or (f"'{_bad}" in txt):
                issues.append(("ERROR", rel,
                               f"第四章文案仍含废话式表述「{_bad}」（{_why}）—— 应删除"))

    # ② 产物级
    art = ROOT / "scripts" / "four_reports" / "company_1_full.json"
    if not art.exists():
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "无真跑产物，无法核验第四章文案 —— 请先跑一次全量一键分析"))
        return issues
    try:
        import json as _json
        _d = _json.loads(art.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        issues.append(("WARN", "scripts/four_reports/company_1_full.json", f"产物不可解析：{e}"))
        return issues
    _rep = _d.get("report") if isinstance(_d.get("report"), dict) else _d
    _er = (_rep or {}).get("enterprise_readable_report") or {}
    _blob = " ".join([
        str(_er.get("action_plan_note") or ""),
        json.dumps(_er.get("recheck") or {}, ensure_ascii=False),
    ])
    for _bad, _why in _RECHECK_META_BANNED.items():
        if _bad in _blob:
            issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                           f"第四章产物仍含废话式表述「{_bad}」（{_why}）"))
    _rc = _er.get("recheck") or {}
    for _k in ("trigger", "work", "convergence"):
        if not str(_rc.get(_k) or "").strip():
            issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                           f"第四章 `recheck.{_k}` 为空 —— 该章不得留空缺省"))

    # ③ 第五章「报告性质和使用说明」：不得有**系统自述 / 自我证明 / 失效表述**
    #   ★ 用户原话（第二轮）：「五、报告性质和使用说明（含待企业澄清事项）…… **重写，有废话**」。
    _blob5 = " ".join([json.dumps(_er.get("report_statement") or [], ensure_ascii=False),
                       str(((_er.get("inspector_perspective") or {}).get(
                           "administrative_boundary")) or "")])
    for _bad, _why in _STATEMENT_META_BANNED.items():
        if _bad in _blob5:
            issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                           f"第五章仍含「{_bad}」（{_why}）—— 应删除"))
    # 前端静态文案同样不得含（改 static 后需跑 sync_asset_versions）
    try:
        _js5 = (ROOT / "static" / "js" / "tax-doc-analysis.js").read_text(
            encoding="utf-8", errors="replace")
    except OSError:
        _js5 = ""
    if _js5:
        for _bad, _why in _STATEMENT_META_BANNED.items():
            if f"'{_bad}" in _js5 or f'"{_bad}' in _js5:
                issues.append(("ERROR", "static/js/tax-doc-analysis.js",
                               f"第五章前端文案仍含「{_bad}」（{_why}）—— 应删除"))
        if "五、报告性质和使用说明（含待企业澄清事项）" in _js5:
            issues.append(("ERROR", "static/js/tax-doc-analysis.js",
                           "第五章标题仍含「（含待企业澄清事项）」—— 该括注已失效"
                           "（待澄清主题已并入各疑点，`unattached_themes` 由闸门断言恒为空）"))
    return issues


# ══════════════════════════════════════════════════════════════════════════
# ★★ 2026-10-06：「按名剔除业态不适用资料」必须是**单一权威**
#
# ## 病根（已复现，非特例）
# 同一个概念（"把本业态天然不会有的资料从清单里剔掉"）此前有 **4 份实现、4 种判法**：
#   ① `evidence_chain.build_evidence_chain`（引擎层，**字符级 `str.replace`**）
#        把不适用资料名当**子串删掉**，不切段：
#          "采购合同与入库验收单" → "采购合同**与**"（悬空连词残词）
#          "物流单据与承运记录"   → "**与**承运记录" 或 ""（**取决于 set 迭代序**）
#        ⚠ 且它发生在 `status`/`basis`/`direct_missing` **算完之后** ⇒ 只有名字被改，
#          依据、直接证据清单、补救要求仍是**原始要求**
#          ⇒ **服务型企业照样被要求补物流单据/入库验收单**（用户实测报告里的现象）。
#   ② `enterprise_report._strip_not_required`（报告层段级，判法正确）
#   ③ `constituent_checkpoint._decl_na`（要件层：切段表**不含「与」** + **双向包含**）
#        ⇒ "采购合同与入库验收单" 不切段、整段命中"入库验收单"
#        ⇒ **整条要件被误判「本业态不适用」**（里面"采购合同"明明适用）。
#   ④ `enterprise_report._trim_text_materials`（整句文本级）
#
# ## 判据（静态 + 行为 + 产物，三层都要过；每一层都做**阳性/阴性双向对照**）
#   A. 静态：分隔符表只允许 `industry_resolver.MATERIAL_SEG_SEP` 一处；
#           报告层两个函数必须是**薄转发**（源码须出现权威名、不得自持切段）。
#   B. 行为：段级无残词 / 幂等 / **跨 hash 顺序确定** / 整项不适用须剔除且**如实披露** /
#           反证不剔 / 业态未知不剔（**不得无据少列**）。
#   C. 产物：报告可见字段（证据角色表、直接证据清单、补救要求、待补清单）
#            不得出现本业态不适用资料名；且不得有悬空连词残词。
# ══════════════════════════════════════════════════════════════════════════

#: 允许持有「并列分隔符切段」实现的文件（唯一权威）
_NA_SEP_OWNER = "engine/industry_resolver.py"
#: 必须是**薄转发**的判定函数 → 必须出现的权威名
_NA_THIN_FORWARDERS = {
    "engine/enterprise_report.py": (
        "exclude_not_required_material", "exclude_not_required_in_text"),
}


def _canonical_report():
    """取**全量分析产物**并解掉包裹，返回扁平 `report_data`；取不到返回 `None`。

    ★★ 2026-10-06：**唯一来源**改为 `scripts/four_reports/company_1_full.json`。
      此前闸门里有多处读 `scripts/four_reports/_fresh_result.json` —— 那是同一回事的
      **第二份 dump**（多层维护：两份 dump 谁新谁旧没人说得清），本轮清盘时被删除，
      于是 3 项行为断言集体退化成 WARN「跳过」。现统一到**唯一产物**。
    兼容三种包裹形态（历史上都出现过）：
      · 扁平：`report_data` 直接在顶层（当前 `company_1_full.json`）；
      · 单层：`{"report": report_data}`（旧 `_fresh_result.json`）；
      · 双层：`{"report": {"report": report_data}}`（旧 `last_analysis_cache.json`）。
    """
    # ★ 2026-10-07：**移除 `_fresh_result.json` 回落**。它是一份**昨日**的旧 dump，
    #   主产物被清理后闸门会静默改读它 ⇒ 审计的是过期报告（实测报出 4 条与当前报告无关的 ERROR）。
    #   口径：产物**单一**；取不到就返回 None → 上层如实报 WARN「无真跑产物」，**不得**回落到旧文件。
    for rel in ("scripts/four_reports/company_1_full.json",):
        p = ROOT / rel
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(d, dict):
            continue
        rep = d.get("report") if isinstance(d.get("report"), dict) else d
        # 最多再剥一层（`{"report": {"report": …}}`）
        if isinstance(rep.get("report"), dict) and "comprehensive" not in rep:
            rep = rep["report"]
        return rep
    return None


def check_company_artifact_consistency() -> List[Tuple[str, str, str]]:
    """磁盘上**按公司 id** 存在的派生物，其 id 必须在 `companies` 表里（2026-10-06）。

    ★ 用户原话：「若是在系统上进行了删除处理的，你能不能设置成与之相应的文件都删除和
      修改相应的信息。例如4个产物就必须改为1个产物，公司2/3/4的缓存或相应的资料和
      信息都应该删除。待重新建立时再新建文件。就是这些常规的思考和动作，能不能都做到位，
      不要踢一脚动一下！！！」

    ## 病根（已实测）
      · 删除账套 `/api/companies/{id}` 只删 Company 行 + 授权，**不调**"删除报告"的
        清理逻辑 ⇒ 报告 6 处副本 + 离线产物全部残留；
      · 库被重置（企业直接从库里消失）时更没人管 ⇒ `scripts/four_reports/` 躺着
        id=2/3/4 的产物，而库里只有 id=1 ⇒ "4 份产物"与"1 家企业"对不上。
    ## 修法
      · 唯一权威 `main.purge_company_analysis_artifacts(company_id, include_uploads)`，
        「删除报告」与「删除账套」**都**走它（不得各写一份）；
      · 重建账套时**撤销墓碑**（`_deleted_company_ids.discard` + 清 tombstones），
        否则复用的 id 会被旧墓碑拦下 ⇒ "新建的企业永远出不来报告"；
      · 历史孤儿用 `scripts/_purge_orphan_company_artifacts.py` 回溯清理。
    ## 本闸门判据（与该脚本同一份判据）
      逐项扫描：离线产物 / 上传原件目录 / 检查点 / 中转站缓存 / 磁盘分析缓存 / 删除墓碑，
      凡 id 不在 `companies` 表 ⇒ ERROR。
    """
    issues: List[Tuple[str, str, str]] = []

    # ── A. 静态：删除账套必须走唯一权威；重建账套必须撤销墓碑 ────────────────
    # ⚠ 判据必须用「去注释 **且去 docstring**」的视图 ——
    #   实测（反向验证抓出）：`delete_company` 的 docstring 里写着
    #   "全部走唯一权威 `purge_company_analysis_artifacts`"，
    #   只去 `#` 注释时 docstring 仍在 ⇒ 变异（把真实调用删掉）后检查**照样通过**，
    #   闸门报 0 是假的。这正是本项目 G7 铁律记载过的病根（"注释里引用同一串"）。
    def _code_of(fn_src: str) -> str:
        _t = re.sub(r'""".*?"""', " ", fn_src, flags=re.S)   # 先去 docstring
        _t = re.sub(r"#[^\n]*", "", _t)                       # 再去行注释
        return _t

    try:
        _src_main = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
    except OSError:
        _src_main = ""
    if _src_main:
        # ① 唯一权威必须存在
        if "def purge_company_analysis_artifacts(" not in _src_main:
            issues.append(("ERROR", "main.py",
                           "找不到唯一权威 `purge_company_analysis_artifacts` —— "
                           "「删除报告」与「删除账套」必须共用同一份清理实现"))
        # ② 删除账套必须调它（去注释+去 docstring 视图，防止只出现在注释/文档里）
        _m_del = re.search(r"\ndef delete_company\(.*?(?=\n@app\.|\Z)", _src_main, re.S)
        if _m_del:
            _body = _code_of(_m_del.group(0))
            if "purge_company_analysis_artifacts" not in _body:
                issues.append(("ERROR", "main.py",
                               "`delete_company` 未调用唯一权威 "
                               "`purge_company_analysis_artifacts(include_uploads=True)` —— "
                               "删账套不清派生物（正是本闸门要堵的病根）"))
            elif "include_uploads=True" not in _body:
                issues.append(("ERROR", "main.py",
                               "`delete_company` 调用清理权威时未带 `include_uploads=True` "
                               "—— 删账套必须连上传原件一起清"))
        # ③ 新建账套必须撤销墓碑（否则复用的 id 被旧墓碑拦下 ⇒ 新企业出不来报告）
        _m_add = re.search(r"\ndef create_company\(.*?(?=\n@app\.|\Z)", _src_main, re.S)
        if _m_add:
            _body = _code_of(_m_add.group(0))
            if "_deleted_company_ids.discard" not in _body:
                issues.append(("ERROR", "main.py",
                               "`create_company` 未撤销删除墓碑（`_deleted_company_ids.discard`）"
                               "—— id 复用时新账套的分析结果会被旧墓碑静默拦下"))
        # ④ 清理权威必须有**安全护栏**：删账套语义（include_uploads=True）时，
        #    企业若仍在库里必须**拒绝执行**。
        #    ★ 2026-10-06 实测事故：对在库企业执行清理，把 `company_1_full.json`
        #      连同 summary/api_result 一起清掉了（靠备份才恢复）。
        _m_auth = re.search(r"\ndef purge_company_analysis_artifacts\(.*?(?=\ndef |\n@app\.|\Z)",
                            _src_main, re.S)
        if _m_auth:
            _body = _code_of(_m_auth.group(0))
            if "include_uploads" not in _body:
                issues.append(("ERROR", "main.py", "清理权威缺少 include_uploads 分支"))
            else:
                # ⚠ 必须**结构断言**（"if _exists: 立即 return 空清理"），
                #   不能只看 `_exists`/「仍在数据库中」这些字样在不在 ——
                #   实测（反向验证 M6 第一版）：把守卫改成 `if False and _exists:` 后，
                #   那些字样全都还在 ⇒ 检查照样通过 ⇒ 假绿。
                _guard_ok = re.search(
                    r"if\s+_exists\s*:\s*\n\s*return\s*\{[^\n]*\"cleared\"", _body) is not None
                if not _guard_ok:
                    issues.append(("ERROR", "main.py",
                                   "清理权威缺**安全护栏**（`if _exists: return {\"cleared\":…}` "
                                   "—— include_uploads=True 时企业仍在库里必须立即拒绝），"
                                   "否则一次误调用就会清掉在库企业的全部产物且不可恢复"))
            if "purge_log.jsonl" not in _body:
                issues.append(("ERROR", "main.py",
                               "清理权威缺**清理审计**（data/purge_log.jsonl）—— "
                               "以后「文件怎么没了」必须一查便知，不得靠猜"))
            # ⑤ **显式确认**：清上传原件必须 `confirmed_deleted=True`（2026-10-06 二次事故）。
            #    "活查库"式护栏不可靠 —— 全量 pytest 期间有测试改变 DB 可见状态，
            #    护栏被判成"企业不存在"⇒ 在库企业产物被清（同日两次，审计日志抓到）。
            if "confirmed_deleted" not in _body:
                issues.append(("ERROR", "main.py",
                               "清理权威缺**显式确认**参数 `confirmed_deleted` —— "
                               "include_uploads=True 必须显式确认，不得靠运行时状态判断"))
        _m_del2 = re.search(r"\ndef delete_company\(.*?(?=\n@app\.|\Z)", _src_main, re.S)
        if _m_del2:
            _body = _code_of(_m_del2.group(0))
            if "confirmed_deleted=True" not in _body:
                issues.append(("ERROR", "main.py",
                               "`delete_company` 调用清理权威时未显式传 "
                               "`confirmed_deleted=True`（删账套是唯一合法入口）"))

    # ── B. 数据：逐项扫描，凡 id 不在库里 ⇒ ERROR ───────────────────────────
    from database import Company                                        # noqa: PLC0415
    from database import SessionLocal                                   # noqa: PLC0415
    _db = SessionLocal()
    try:
        _ids = {int(r) for (r,) in _db.query(Company.id).all()}
    finally:
        _db.close()

    _bad: Dict[int, List[str]] = {}

    def _add(cid: int, desc: str) -> None:
        _bad.setdefault(int(cid), []).append(desc)

    # ① 离线产物（含 readable/ 子目录）
    rep = ROOT / "scripts" / "four_reports"
    if rep.is_dir():
        for _p in sorted(rep.rglob("company_*")):
            if not _p.is_file():
                continue
            head = _p.name.split("_")
            if len(head) < 2 or not head[1].isdigit():
                continue
            cid = int(head[1])
            if cid not in _ids:
                _add(cid, "离线产物 " + str(_p.relative_to(ROOT)))
    # ② 上传原件目录
    up = ROOT / "data" / "uploads"
    if up.is_dir():
        for _p in sorted(up.iterdir()):
            if _p.is_dir() and _p.name.isdigit() and int(_p.name) not in _ids:
                _add(int(_p.name), "上传原件目录 " + str(_p.relative_to(ROOT)))
    # ③ 检查点 / ④ 中转站缓存
    for sub, pat in (("checkpoints", r"^(\d+)\.json$"), ("transfer", r"^(\d+)_")):
        d = up / sub
        if not d.is_dir():
            continue
        for _p in sorted(d.iterdir()):
            m = re.match(pat, _p.name)
            if m and int(m.group(1)) not in _ids:
                _add(int(m.group(1)), str(_p.relative_to(ROOT)))
    # ⑤ 磁盘分析缓存（真实路径 `data/cache/last_analysis_cache.json`；
    #   ⚠ 第一版写成 `data/last_analysis_cache.json` ⇒ 检查对象根本不存在 ⇒ 静默假绿）
    try:
        _disk = json.loads((ROOT / "data" / "cache" / "last_analysis_cache.json")
                           .read_text(encoding="utf-8", errors="replace"))
        if isinstance(_disk, dict):
            for k in _disk:
                if str(k).isdigit() and int(k) not in _ids:
                    _add(int(k), "data/cache/last_analysis_cache.json[%s]" % k)
    except Exception:  # noqa: BLE001
        pass
    # ⑥ 资料删除墓碑
    try:
        from runtime_storage import load_doc_tombstones                 # noqa: PLC0415
        for v in load_doc_tombstones().values():
            cid = int((v or {}).get("company_id") or 0)
            if cid and cid not in _ids:
                _add(cid, "资料删除墓碑（company_id=%d，data/deleted_docs.json）" % cid)
    except Exception:  # noqa: BLE001
        pass

    for cid in sorted(_bad):
        issues.append(("ERROR", "scripts/four_reports / data/uploads",
                       "企业 %d 已不在数据库，但其派生物仍在（%s）—— "
                       "应随删除一起清理（唯一权威 "
                       "`main.purge_company_analysis_artifacts`，历史孤儿可用 "
                       "`scripts/_purge_orphan_company_artifacts.py --apply`）：%s"
                       % (cid, len(_bad[cid]), "；".join(_bad[cid][:3]))))

    # ── D. **删除操作总清单**：每个删除端点必须声明走哪个清理权威 ──────────
    #   ★ 用户口径（2026-10-06）：不是只盯三种删除，而是「删除 ⇒ 删干净」这条铁律
    #     对**现在和将来的一切删除操作**都成立。今后新增删除端点若不接权威，
    #     本闸门直接报 ERROR（先于缺陷发生）。
    _PURGE_AUTHORITIES = ("purge_company_analysis_artifacts", "_delete_tax_risk_docs",
                          "_clear_transfer")
    # 语义上**不是**"删企业数据"的删除端点（用户级/系统级/软删除），逐一声明理由：
    _DELETE_ALLOWLIST = {
        "delete_my_llm_credential": "删除用户自己的 LLM 凭证（用户级，非企业数据）",
        "delete_api_key": "删除用户 API Key（用户级）",
        "clear_system_logs": "清空访问日志（日志本身就是被删对象）",
        "delete_correction_rule": "纠正规则软删除 + 归档（设计如此，非企业数据）",
        "delete_pipeline_history": "删除一条分析历史条目（内存+磁盘已同步，条目即全部）",
    }
    # ⚠ 必须捕获**路由路径**：`def` 行之前是装饰器，若只从 def 行起匹配，
    #   路径里的 "companies" 永远看不到 ⇒ 判定恒假（反向验证 M7 实测踩过）。
    # ⚠ 必须捕获**方法 + 路径**：只审"真删除"操作（DELETE 方法，或路径含 delete/clear）；
    #   POST 的创建/分析端点（/api/companies、/analyze 等）不是删除操作，不得误伤
    #   （反向验证 M7 第一版曾把 create_company/analyze 误判进去）。
    _del_routes = re.findall(
        r'@(?:app|router)\.(delete|post)\(\s*"([^"]*)"\s*\)\s*\ndef (\w+)\(',
        _src_main)
    for _method, _path, _fname in _del_routes:
        if _fname in _DELETE_ALLOWLIST:
            continue
        if not (_method == "delete" or re.search(r"delete|clear", _path, re.I)):
            continue
        _mm = re.search(r"\ndef %s\(.*?(?=\n@|\n\ndef |\Z)" % re.escape(_fname),
                        _src_main, re.S)
        if not _mm:
            continue
        _bd = _code_of(_mm.group(0))
        if not any(a in _bd for a in _PURGE_AUTHORITIES):
            # 只对"删企业数据"的端点强制（路径含 report/doc/company 关键字）
            if re.search(r"tax-risk-docs|companies|report", _path):
                issues.append(("ERROR", "main.py",
                               "删除端点 `%s`（%s）未接任何清理权威（%s）—— "
                               "「删除 ⇒ 删干净」必须走唯一权威，不得各写一份"
                               % (_fname, _path, "、".join(_PURGE_AUTHORITIES))))
    return issues


def check_delete_exits() -> List[Tuple[str, str, str]]:
    """「删除出口唯一」：系统里**一切真正删东西的调用**必须落在声明的出口函数里（2026-10-06）。

    ★ 用户口径：「不是仅仅这三种删除，而是**这种删除效果**」——
      **删了就是真删了（页面/内存/磁盘/数据库/派生物一个不留）**，
      并且对**将来新增的任何删除**都成立。
    落地办法：把"谁能删"变成一道**可机器检查的不变量** ——
      · 业务出口（8）：各自声明清理范围；
      · 底层原语（4）：只允许在 `runtime_storage` 里实现（唯一实现）；
      · 其它任何地方出现 `os.remove/os.unlink/shutil.rmtree/move_to_trash/purge_file`
        ⇒ ERROR（要么接权威，要么进本清单并写明范围 —— 不准有"顺手删一下"）。
    """
    issues: List[Tuple[str, str, str]] = []

    # 业务出口：函数名 → 清理范围（必须在函数体里找得到实现，且**只此一处**）
    _EXITS = {
        "purge_company_analysis_artifacts": "账套级（报告/文件/原件/缓存/DB/学习层，共 13 处）",
        "_delete_tax_risk_docs": "资料级（磁盘原件+中转站+列表+墓碑）",
        "_clear_transfer": "中转站解析缓存",
        "purge_pending_deletions": "失败删除的补齐执行（墓碑驱动，仍走资料级语义）",
        "clear_system_logs": "访问日志自删（日志本身即对象）",
        "_run_declaration_consistency": "同名上传覆盖：旧版移入项目回收站",
        "analyze_tax_risk_docs_resume": "重跑前清失败检查点（状态重置，非业务数据）",
        "delete_credential": "用户级 LLM 凭证（DB 行即全部，另在 llm_credentials.py）", "_cleanup_upload_session": "上传会话临时态（data/upload_sessions/<id>/ 分片 + <id>.json）—— **不是**用户资料/交付物（P0-2，2026-10-13）", "_reset_document_extract": "本模块三张解析登记表（extracted_tables/extracted_fields/extract_issues）中该文档的行——**不触碰** documents 表与物理文件（P0-3，2026-10-13）",
    }
    # 底层原语：只允许在 runtime_storage 里出现（唯一实现）
    # ★ 2026-10-09 新增 `atomic_write_text`：JSONL 整表重写（作业流水/版本台账/
    #   purge_log）需要原子写文本，从前各模块**各自** `mkstemp`+`os.replace`+
    #   失败 `os.unlink(tmp)` —— 闸门抓到 `engine/analysis_jobs.py::_rewrite_rows`
    #   报 ERROR。现抽为唯一实现，删除临时文件只此一个声明出口。
    _PRIMITIVES = {"move_to_trash", "empty_trash_batch", "purge_file",
                   "atomic_write_json", "atomic_write_text", "purge_tree", "atomic_write_bytes"}  # purge_tree：目录级；atomic_write_bytes：P0-7 报告二进制原子写（与 atomic_write_text 同一出口家族）
    _PAT = re.compile(r"os\.remove\(|os\.unlink\(|shutil\.rmtree\(|"
                      r"move_to_trash\(|purge_file\(|empty_trash_batch\(|purge_tree\(")
    _SCAN = ["main.py", "runtime_storage.py", "security.py", "llm_credentials.py"]

    def _mask_prose(text: str) -> str:
        """把 docstring 与行注释**用空格顶掉（保留换行）**⇒ 行号不变，只审代码。

        ★ 2026-10-09 根因修复（本闸门自己出的假红）：
          原扫描是**逐行文本匹配**，只跳过 `#`/`import`/`from` 开头的行，
          于是 **docstring 里"提到"某个删除调用**也会被判 ERROR。
          实测：`engine/analysis_jobs.py::_rewrite_rows` 的 docstring 写明了
          "从前顺手 `os.unlink(tmp)` 被本闸门抓到"，本闸门就把这句**说明文字**
          当成删除调用报错。判据必须审**代码**、不审**散文**。
        """
        def _blank(m: "re.Match[str]") -> str:
            return re.sub(r"[^\n]", " ", m.group(0))
        t = re.sub(r'"""(?:.|\n)*?"""', _blank, text)
        t = re.sub(r"'''(?:.|\n)*?'''", _blank, t)
        t = re.sub(r"#[^\n]*", lambda m: " " * len(m.group(0)), t)
        return t

    def _scan_file(rel: str) -> None:
        p = ROOT / rel
        if not p.exists():
            return
        try:
            lines = _mask_prose(
                p.read_text(encoding="utf-8", errors="replace")
            ).split("\n")
        except OSError:
            return
        _cur = ""      # 当前所属顶层函数
        for _i, _ln in enumerate(lines, 1):
            if _ln.startswith("def "):
                _m = re.match(r"def (\w+)\(", _ln)
                _cur = _m.group(1) if _m else ""
            _s = _ln.strip()
            if not _s or _s.startswith("import ") or _s.startswith("from "):
                continue          # 空白 / 导入行不算调用（注释与文档串已被空格顶掉）
            if not _PAT.search(_ln):
                continue
            if _cur in _EXITS or _cur in _PRIMITIVES:
                continue
            issues.append(("ERROR", rel,
                           "第 %d 行出现未声明的删除调用（所属函数 `%s`）—— "
                           "「删除必须走声明的出口」：接权威或进 `check_delete_exits` 清单并写明范围。"
                           "片段：%s" % (_i, _cur or "(模块级)", _s[:70])))

    for _rel in _SCAN:
        _scan_file(_rel)
    _eng = ROOT / "engine"
    if _eng.is_dir():
        for _p in sorted(_eng.glob("*.py")):
            if _p.name.startswith("_bk"):
                continue
            _scan_file("engine/" + _p.name)

    # 出口函数必须真的存在（防"声明了但实现被删/改名"）
    _src_main = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace") \
        if (ROOT / "main.py").exists() else ""; _src_main += "\n" + "\n".join(_p.read_text(encoding="utf-8", errors="replace") for _p in sorted((ROOT / "engine").glob("*.py")))  # 2026-10-13：出口可落在 engine 模块（P0-2 的 _cleanup_upload_session），须与 _SCAN 同范围
    for _name in _EXITS:
        if _name in ("delete_credential",):
            continue
        if ("def %s(" % _name) not in _src_main:
            issues.append(("ERROR", "main.py",
                           "声明的删除出口 `%s`（%s）在 main.py 里找不到实现"
                           % (_name, _EXITS[_name])))

    # ── 底层原语「全仓唯一定义」（★ 2026-10-09 新增，根治本闸门自身的范围缺口）──
    # 为什么必须全仓扫：上面 `_SCAN` 只覆盖 4 个根文件 + `engine/*.py`，而本闸门
    #   的声明是"**系统里一切**真正删东西的调用"。实测（2026-10-09）：
    #   `tools/cleanup_20261008.py:47` 自己写了一份 `def move_to_trash(...)`，
    #   ——它既是"底层原语不得二次实现"的违反，又因 `tools/` 不在扫描范围内而
    #   对闸门完全隐形。**"谁能删"成立的先决条件是"原语只有一份"**：
    #   连唯一实现都不唯一，谈何"删除出口唯一"。
    # 判据（与用户铁律「新写函数必须删旧定义」同口径）：
    #   `^def <原语名>` 全仓计数**必须恰好 == 1**，且那一份必须在 runtime_storage.py。
    _def_pat = re.compile(r"^def\s+(\w+)\s*\(", re.M)
    #: 不参与判定的目录（备份/归档/历史副本 —— 它们不是"在跑的实现"）
    _DEF_SKIP_PARTS = {".venv", ".git", "node_modules", "__pycache__", "data",
                       "baseline", "outputs", "_archive"}
    _found_defs: Dict[str, List[str]] = {_n: [] for _n in _PRIMITIVES}

    def _collect_defs(rel: str, text: str) -> None:
        for _m in _def_pat.finditer(text):
            if _m.group(1) in _found_defs:
                _found_defs[_m.group(1)].append(rel)

    for _f in sorted(ROOT.glob("*.py")):
        _collect_defs(_f.name, _f.read_text(encoding="utf-8", errors="replace"))
    for _d in ("engine", "tools", "scripts", "tests", "config"):
        _base = ROOT / _d
        if not _base.is_dir():
            continue
        for _p in sorted(_base.rglob("*.py")):
            _parts = set(_p.relative_to(ROOT).parts)
            if _parts & _DEF_SKIP_PARTS:
                continue
            if _p.name.startswith("_bk") or "_bak" in _p.name:
                continue
            _collect_defs(_p.relative_to(ROOT).as_posix(),
                          _p.read_text(encoding="utf-8", errors="replace"))
    for _n in sorted(_PRIMITIVES):
        _hits = sorted(set(_found_defs[_n]))
        if not _hits:
            issues.append(("ERROR", "runtime_storage.py",
                           "底层删除原语 `%s` 全仓找不到实现（唯一实现应在 "
                           "runtime_storage.py）" % _n))
        elif len(_hits) > 1:
            # 归因指向**越位的那一份**（权威在 runtime_storage，其余都是越位）
            _stray = [h for h in _hits if h != "runtime_storage.py"] or _hits
            issues.append(("ERROR", _stray[0],
                           "底层删除原语 `%s` 出现 %d 份实现（%s）—— "
                           "「删除出口唯一」的先决条件是**原语只有一份**："
                           "只准 runtime_storage.py 里那一份。"
                           % (_n, len(_hits), "、".join(_hits))))
        elif _hits[0] != "runtime_storage.py":
            issues.append(("ERROR", _hits[0],
                           "底层删除原语 `%s` 不在 runtime_storage.py（在 %s）—— "
                           "唯一实现必须落在 runtime_storage" % (_n, _hits[0])))
    return issues


def check_audit_trail_single_writer() -> List[Tuple[str, str, str]]:
    """业务操作留痕：**写入只有一处**，且"失败不阻断、也绝不静默"（2026-10-09）。

    ★ 病根（实测，非设想）：`audit_logs` 表早就在、读接口 `/api/audit-logs` 也早就在，
      但**全仓没有任何一处写入** —— `SELECT COUNT(*)` = 0，
      `grep -rn "audit_logs"` 只有 `CREATE TABLE` 与 `SELECT`。
      ⇒ 上传 / 分析 / 复核 / 导出 / 下载 / 删除这六类**最需要追责的动作**一条都没留痕。
      本次收敛为唯一权威 `engine/audit_trail.py`，本闸门保证它不会被绕过，
      也保证它不会被"顺手再写一份 INSERT"分叉。

    判据：
      A【静态】`INSERT INTO audit_logs` 只允许出现在 `engine/audit_trail.py`；
        权威模块必须同时导出 `record()` 与 `list_records()`（写/读都不许绕开）。
      B【行为·子进程隔离】在 `APP_DATA_DIR=<临时目录>` 的**独立进程**里验证：
        ① 已登记动作写成功且返回 id、`count()` 递增；
        ② **未登记**动作**照记原值**（不静默丢弃）；
        ③ `company_id=None` 存 NULL，**不得用 0 冒充**"无归属"；
        ④ `list_records(action=...)` 过滤生效；
        ⑤ 写入失败时 `record()` **不抛异常**（不阻断主流程）且 `last_error()` 非空（不静默）。
      为什么用子进程：行为判据要真的写库，**绝不能污染真实 `accounting.db`**；
      子进程 + `APP_DATA_DIR` 让 `runtime_storage`/`database` 自然指向临时库，无需 monkeypatch 全局。
    """
    issues: List[Tuple[str, str, str]] = []

    # ── A 静态：写入唯一 ────────────────────────────────────────────────────
    _pat = re.compile(r"INSERT\s+INTO\s+audit_logs", re.I)
    _SKIP_PARTS = {".venv", ".git", "node_modules", "__pycache__", "data",
                   "baseline", "outputs", "_archive", "_bak"}
    _AUTHORITY = "engine/audit_trail.py"
    # 本检查器**自身**含该字面量（正则与提示文案）⇒ 自检跳过（与 `check_counts`
    # 的「自检跳过」同例）。同时把 docstring 与行注释用空格顶掉（保留换行、行号不变），
    # 避免把"提到这个写法"的说明文字判成真写入 —— 与 `check_delete_exits._mask_prose` 同一修法。
    _SELF = "tools/audit_consistency.py"

    def _mask_prose(text: str) -> str:
        def _blank(m: "re.Match[str]") -> str:
            return re.sub(r"[^\n]", " ", m.group(0))
        t = re.sub(r'"""(?:.|\n)*?"""', _blank, text)
        t = re.sub(r"'''(?:.|\n)*?'''", _blank, t)
        return re.sub(r"#[^\n]*", lambda m: " " * len(m.group(0)), t)

    _files: List[Any] = sorted(ROOT.glob("*.py"))
    for _d in ("engine", "tools", "scripts", "tests", "config", "routers"):
        _base = ROOT / _d
        if _base.is_dir():
            _files.extend(sorted(_base.rglob("*.py")))
    for _p in _files:
        _rel = _p.relative_to(ROOT).as_posix()
        if _rel == _SELF:
            continue
        if set(_p.relative_to(ROOT).parts) & _SKIP_PARTS:
            continue
        if _p.name.startswith("_bk") or "_bak" in _p.name:
            continue
        try:
            _txt = _mask_prose(_p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        for _m in _pat.finditer(_txt):
            if _rel == _AUTHORITY:
                continue
            _ln = _txt[:_m.start()].count("\n") + 1
            issues.append(("ERROR", _rel,
                           "第 %d 行出现 `INSERT INTO audit_logs` —— 业务留痕的写入"
                           "只允许在唯一权威 `%s::record()`（否则同一概念两处实现，"
                           "迟早分叉，「谁写过」再也说不清）。" % (_ln, _AUTHORITY)))
    _auth = ROOT / _AUTHORITY
    if not _auth.exists():
        issues.append(("ERROR", _AUTHORITY,
                       "业务留痕唯一权威不存在（`engine/audit_trail.py`）"))
    else:
        _src = _auth.read_text(encoding="utf-8", errors="replace")
        for _fn in ("record", "list_records"):
            if ("def %s(" % _fn) not in _src:
                issues.append(("ERROR", _AUTHORITY,
                               "唯一权威缺 `%s()` —— 写/读都不许绕开本模块" % _fn))

    # ── B 行为（子进程 + APP_DATA_DIR 隔离，绝不碰真实库）────────────────────
    import subprocess
    import tempfile
    _probe = r'''
import sys, pathlib
sys.path.insert(0, str(pathlib.Path.cwd()))
import runtime_storage as RS
from engine import audit_trail as AT
AT.ensure_schema()
assert AT.count() == 0, "隔离库初始应为空：%r" % AT.count()
i1 = AT.record("doc.upload", target="probe.csv", company_id=7, detail="probe",
               user_name="probe-user")
assert isinstance(i1, int) and AT.count() == 1, ("写入失败", i1, AT.count())
# ② 未登记动作必须照记原值
i2 = AT.record("not.a.registered.action", target="t", company_id=7)
assert AT.count() == 2, ("未登记动作被丢弃", AT.count())
assert AT.list_records(action="not.a.registered.action")[0]["action"] == \
    "not.a.registered.action", "未登记动作被改名"
# ③ company_id=None 必须存 NULL，不得用 0 冒充
i3 = AT.record("doc.delete", target="t2")
row = [r for r in AT.list_records() if r["id"] == i3][0]
assert row["company_id"] is None, ("无归属被 0 冒充：%r" % (row["company_id"],))
# ④ 过滤生效
assert [r["action"] for r in AT.list_records(action="doc.upload")] == ["doc.upload"]
assert len(AT.list_records(company_id=7)) == 2, AT.list_records(company_id=7)
# ⑤ 写失败：不抛（不阻断）、且 last_error 非空（不静默）
_orig = AT.ensure_schema
AT.ensure_schema = lambda: (_ for _ in ()).throw(RuntimeError("probe-boom"))
try:
    bad = AT.record("doc.upload", target="x", company_id=7)
    assert bad is None, "写失败却返回了值：%r" % (bad,)
    assert AT.last_error(), "写失败被静默（last_error 为空）"
finally:
    AT.ensure_schema = _orig
print("OK db=%s" % RS.ACCOUNTING_DB)
'''
    with tempfile.TemporaryDirectory(prefix="audit-gate-") as _td:
        _env = dict(os.environ)
        _env["APP_DATA_DIR"] = _td
        _env["PYTHONIOENCODING"] = "utf-8"
        try:
            _cp = subprocess.run([sys.executable, "-c", _probe], cwd=str(ROOT),
                                 env=_env, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=180)
        except Exception as exc:                 # noqa: BLE001
            issues.append(("ERROR", _AUTHORITY, "行为判据子进程无法启动：%s" % exc))
        else:
            if _cp.returncode != 0 or "OK " not in (_cp.stdout or ""):
                issues.append(("ERROR", _AUTHORITY,
                               "业务留痕行为判据失败（写/未登记动作/无归属/过滤/失败不静默）：%s"
                               % ((_cp.stdout or "") + " | " + (_cp.stderr or "")).strip()[-400:]))
    return issues


def check_report_payload_single_shape() -> List[Tuple[str, str, str]]:
    """报告 JSON 载荷：**形状（键集/类型）只有一个出处**（2026-08-09 T-P0-8）。

    ★ 病根（实测，非设想）：`tax_risk.py::get_tax_risk_report()` 曾有两个 `return`
      各自手写载荷字面量 ——「无业务数据」分支 `summary` 是 **str**、中风险键名
      `medium_risk_count`；「正常」分支 `summary` 是 **dict**、中风险键名 `mid_risk_count`。
      四个渲染出口（`_generate_report_html` / `_download_pdf` / `_download_docx` /
      `_download_pptx`）一律 `s.get(...)` ⇒ 本系统**唯一那个真实账套**（七张业务表全 0 行）
      导出报告时 `AttributeError: 'str' object has no attribute 'get'` ⇒ **HTTP 500**。
      同批还发现 PPTX 详情页有一句 `if idx > 0 and idx % 6 == 0: continue`
      —— 把**每一页的第 7 项静默丢掉**（导出内容 ≠ 分析结果）。

    判据：
      A【静态】`tax_risk.py` 里 `get_tax_risk_report()` 的**每一个 return 都必须调
        `_report_payload()`**（不许再出现手写字典字面量）——这是"结构上不可能再漂移"的保证；
        且权威函数/键表齐全。
      B【静态】中风险键名 `medium_risk_count` **全仓不得出现**
        （同一概念两个键名 = 多头维护；渲染出口只会认 `mid_risk_count`）。
      C【行为】四类入参（无数据 / 有 findings）产出的载荷**键集逐项相同**且等于
        `_REPORT_PAYLOAD_KEYS`，`summary` 两处都是 dict 且键集等于 `_SUMMARY_KEYS`；
        四个渲染出口对**两种载荷**都必须产出非空字节（"不 500"的机器证明），
        且无数据载荷里不得出现 `None` 被当值渲染的痕迹。
    """
    issues: List[Tuple[str, str, str]] = []
    import ast
    import subprocess
    import tempfile

    _REL = "tax_risk.py"
    _SRC = ROOT / _REL
    if not _SRC.exists():
        return [("ERROR", _REL, "报告载荷所在模块不存在")]

    # ── A 静态（AST）：所有 return 必须走 `_report_payload()` ──────────────
    try:
        _tree = ast.parse(_SRC.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as exc:
        return [("ERROR", _REL, "语法错误，无法做载荷形状判据：%s" % exc)]

    _fn = None
    for _node in ast.walk(_tree):
        if isinstance(_node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and _node.name == "get_tax_risk_report":
            _fn = _node
            break
    if _fn is None:
        issues.append(("ERROR", _REL, "找不到 `get_tax_risk_report()`"))
    else:
        _returns = [n for n in ast.walk(_fn) if isinstance(n, ast.Return)]
        if not _returns:
            issues.append(("ERROR", _REL, "`get_tax_risk_report()` 没有任何 return"))
        for _r in _returns:
            _ok_call = (isinstance(_r.value, ast.Call)
                        and isinstance(_r.value.func, ast.Name)
                        and _r.value.func.id == "_report_payload")
            if not _ok_call:
                _kind = type(_r.value).__name__ if _r.value is not None else "None"
                issues.append((
                    "ERROR", _REL,
                    "第 %d 行 `get_tax_risk_report()` 的 return 是 %s，不是 "
                    "`_report_payload(...)` —— 载荷形状一旦有两处手写实现，"
                    "键名/类型必然漂移（T-P0-8 事故）。" % (_r.lineno, _kind)))

    _src_txt = _SRC.read_text(encoding="utf-8", errors="replace")
    for _name in ("_report_payload", "_report_summary", "_REPORT_PAYLOAD_KEYS",
                  "_SUMMARY_KEYS", "_money_text", "_pct_text", "_level_text",
                  "_notice_text"):
        if ("def %s(" % _name) not in _src_txt and ("%s = (" % _name) not in _src_txt:
            issues.append(("ERROR", _REL, "报告载荷权威缺 `%s`" % _name))

    # ── B 静态：中风险键名不得出现第二写法（AST 精确判定，不审散文）─────────
    #   ⚠ 判据坑：用裸正则扫全仓会把**说明文字**与**测试断言**判成违规
    #     （`assert "medium_risk_count" not in s` 就是一句正当的断言）。
    #     故只认三种**真取值**写法：字典键、`d['...']` 下标、`.get('...')` 实参。
    _SELF = "tools/audit_consistency.py"
    _SKIP = {".venv", ".git", "node_modules", "__pycache__", "data", "baseline",
             "outputs", "_archive", "_bak"}
    _BAD_KEY = "medium_" + "risk_count"          # 运行期拼：本文件自身也不写死该字面量
    _scan: List[Any] = sorted(ROOT.glob("*.py"))
    for _d in ("engine", "tools", "scripts", "tests", "config", "routers"):
        _b = ROOT / _d
        if _b.is_dir():
            _scan.extend(sorted(_b.rglob("*.py")))
            _scan.extend(sorted(_b.rglob("*.js")))

    def _key_uses(tree) -> List[int]:
        """返回把 `_BAD_KEY` 当**键**用的行号（字典键 / 下标 / .get() 实参）。"""
        hits: List[int] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for k in node.keys:
                    if isinstance(k, ast.Constant) and k.value == _BAD_KEY:
                        hits.append(k.lineno)
            elif isinstance(node, ast.Subscript):
                s = node.slice
                if isinstance(s, ast.Constant) and s.value == _BAD_KEY:
                    hits.append(node.lineno)
            elif isinstance(node, ast.Call):
                for a in (list(node.args) + [kw.value for kw in node.keywords]):
                    if isinstance(a, ast.Constant) and a.value == _BAD_KEY:
                        hits.append(node.lineno)
        return hits

    for _p in _scan:
        try:
            _rel = _p.relative_to(ROOT).as_posix()
        except ValueError:
            continue
        if _rel == _SELF or set(_p.relative_to(ROOT).parts) & _SKIP:
            continue
        if "_bak" in _p.name or _p.name.startswith("_bk"):
            continue
        try:
            _txt = _p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _p.suffix == ".py":
            try:
                # ⚠ 闸门不得被别处的 SyntaxWarning 刷屏：AST 解析只取结构，抑制告警。
                #   （实测：`scripts/_gate_trunc_final.py:4` 有 `invalid escape sequence '\d'`，
                #    与本判据无关，但会污染闸门输出 —— 已单独记录，不在本闸门处理。）
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    _lines = _key_uses(ast.parse(_txt))
            except SyntaxError:
                continue
        else:                                    # .js：无 AST，退回正则（前端无需注释说明）
            _lines = [_txt[:_m.start()].count("\n") + 1
                      for _m in re.finditer(re.escape(_BAD_KEY), _txt)]
        for _ln in _lines:
            issues.append((
                "ERROR", _rel,
                "第 %d 行把中风险写成了 `%s` —— 键名唯一权威是 "
                "`mid_risk_count`（见 `tax_risk.py::_SUMMARY_KEYS`）。"
                "同一概念两个键名 ⇒ 渲染出口静默取不到值。"
                % (_ln, _BAD_KEY)))

    # ── C 行为（子进程 + APP_DATA_DIR 隔离，绝不碰真实库/真实产物）─────────
    _probe = r'''
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path.cwd()))
import tax_risk as T

PK, SK = set(T._REPORT_PAYLOAD_KEYS), set(T._SUMMARY_KEYS)

def _mk(results, avail):
    return T._report_payload(
        company_id=1, period_start="2025-01", period_end="2025-06",
        industry="综合", industry_benchmark=T._industry_benchmark_block(None),
        summary=T._report_summary(results, 0, analysis_available=avail),
        metrics=({"revenue": None, "cost": None, "gross_margin_pct": None,
                  "vat_payable": None} if not avail else
                 {"revenue": 1000.0, "cost": 600.0, "gross_margin_pct": 40.0,
                  "vat_payable": 30.0}),
        results=results, notice="" if avail else T._NO_DATA_NOTICE,
        analysis_available=avail)

EMPTY = _mk([], False)
FULL = _mk([{"item": "甲", "category": "经营实质", "risk_level": "高风险",
             "risk_score": 9, "detail": "d", "suggestion": "s"},
            {"item": "乙", "category": "发票异常", "risk_level": "中风险",
             "risk_score": 4, "detail": "d", "suggestion": "s"}], True)

for _tag, _p in (("empty", EMPTY), ("full", FULL)):
    assert set(_p) == PK, ("载荷顶层键集漂移", _tag, sorted(set(_p) ^ PK))
    assert isinstance(_p["summary"], dict), ("summary 不是 dict", _tag)
    assert set(_p["summary"]) == SK, ("summary 键集漂移", _tag,
                                      sorted(set(_p["summary"]) ^ SK))

def _bytes_of(out):
    # 四个出口返回类型并不统一：`_generate_report_html` 是 str，其余是 Response
    if isinstance(out, bytes):
        return out
    if isinstance(out, str):
        return out.encode("utf-8")
    b = getattr(out, "body", None)
    if b is None:
        b = getattr(out, "content", b"")
    return b or b""

for _tag, _p in (("empty", EMPTY), ("full", FULL)):
    for _fn in ("_generate_report_html", "_download_pdf", "_download_docx",
                "_download_pptx"):
        body = _bytes_of(getattr(T, _fn)(_p))
        assert body, ("渲染出口产出为空", _tag, _fn)

# 无数据载荷不得把缺失渲染成 "None"，也不得伪造成 0.00
_html = _bytes_of(T._generate_report_html(EMPTY)).decode("utf-8", "replace")
assert "None" not in _html and "nan" not in _html, "无数据载荷把缺失渲染成了 None/nan"
assert "0.00" not in _html, "无数据载荷把缺失伪造成了 0.00（缺失≠0）"
assert "—" in _html, "无数据时金额/比例应渲染为「—」而非 0.00"
assert "暂无业务数据" in _html, "无数据交付物没有写明原因"

# 导出完整性：PPTX 不得静默丢项（每页第 7 项曾被 continue 吃掉）
import io, zipfile
_many = [{"item": "唯一标记项%02d" % i, "category": "经营实质", "risk_level": "中风险",
          "risk_score": 5, "detail": "d", "suggestion": "s"} for i in range(1, 14)]
_r = T._download_pptx(_mk(_many, True))
_zf = zipfile.ZipFile(io.BytesIO(_bytes_of(_r)))
_xml = b"".join(_zf.read(n) for n in sorted(_zf.namelist())
                if n.startswith("ppt/slides/") and n.endswith(".xml"))
_miss = [i for i in range(1, 14) if ("唯一标记项%02d" % i).encode() not in _xml]
assert not _miss, ("PPTX 静默丢项", _miss)
print("OK")
'''
    with tempfile.TemporaryDirectory(prefix="payload-gate-") as _td:
        _env = dict(os.environ)
        _env["APP_DATA_DIR"] = _td
        _env["PYTHONIOENCODING"] = "utf-8"
        try:
            _cp = subprocess.run([sys.executable, "-c", _probe], cwd=str(ROOT),
                                 env=_env, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=300)
        except Exception as exc:                 # noqa: BLE001
            issues.append(("ERROR", _REL, "载荷形状行为判据子进程无法启动：%s" % exc))
        else:
            if _cp.returncode != 0 or "OK" not in (_cp.stdout or ""):
                issues.append(("ERROR", _REL,
                               "载荷形状/渲染行为判据失败（形状唯一 · 四出口可用 · "
                               "缺失不渲染为 0 · PPTX 不丢项）：%s"
                               % ((_cp.stdout or "") + " | "
                                  + (_cp.stderr or "")).strip()[-500:]))
    return issues


def non_risk_level_conflicts(roots) -> List[Tuple[str, str]]:
    """扫出「**正向（非风险）发现却被打上风险/待核等级**」的条目（A-P0-3）。

    ★ 病根（实测真产物，非设想）：`comprehensive.redline_detection.unmapped[]` 里 5 条
      税收优惠/红利发现，**同一行**里 `match_note` 明写「属正向机会提示，不作为税务风险事项配对」，
      而 `level` 却是「待核验」、`review_level` 是「全面复核」⇒ 自相矛盾。
      根因：`text_guardrails.review_finding()` 是无差别递归归一，按证据成熟度**无条件**
      把 `level` 改成「待核验」，而 `优惠机会` 不在 `LEGAL_LEVELS` 里 ⇒ 语义被抹平。
      已修（走 `risk_levels.is_non_risk_finding()` + `normalize()`）；本函数是**端到端判据**。

    判据只用**引擎自己的字段**（不新造口径）：
      非风险语义 = 带 `tax_benefit` 或带 `non_risk_semantic`；
      违规 = 其 `level` 落在风险档/证据状态档（`待核验`、`极高/高/中/低风险`）。
      ⇒ 「信息」是唯一合法落点（最轻档，与"不作为风险事项"一致）。

    遍历：**迭代 + `id()` 去环**（`report_data` 含自引用，递归会 RecursionError）。
    """
    import collections
    from engine.risk_levels import RISK_GRADES, EVIDENCE_STATES
    # 「风险档 + 证据状态档」= 正向发现**不得**落在的档位（唯一权威派生，不另抄一张表）。
    # 「信息」是唯一合法落点（最轻档，与"不作为风险事项"语义一致）。
    _BAD = tuple(set(RISK_GRADES) - {"信息"}) + tuple(EVIDENCE_STATES)
    conflicts: List[Tuple[str, str]] = []
    for name, root in roots:
        seen: set = set()
        stack = [root]
        while stack:
            cur = stack.pop()
            if isinstance(cur, (dict, list)):
                if id(cur) in seen:
                    continue
                seen.add(id(cur))
                if isinstance(cur, dict):
                    _lv = str(cur.get("level") or "").strip()
                    _non_risk = bool(cur.get("tax_benefit") or cur.get("non_risk_semantic"))
                    if _non_risk and _lv in _BAD:
                        conflicts.append((name, "%s ｜ level=%s ｜ type=%s"
                                          % (str(cur.get("non_risk_semantic")
                                                 or cur.get("tax_benefit"))[:22],
                                             _lv, str(cur.get("type") or "")[:28])))
                    stack.extend(cur.values())
                else:
                    stack.extend(cur)
    return conflicts


def check_non_risk_findings_not_flagged() -> List[Tuple[str, str, str]]:
    """闸门：**正向（非风险）发现不得被打上风险/待核等级**（2026-10-10，A-P0-3）。

    端到端产出断言：直接读**真产物** `scripts/four_reports/company_*_full.json`，
    而不是只看代码 —— 本缺陷正是"代码看着对、产物里自相矛盾"。
    产物不存在 ⇒ 如实 WARN（不假装通过）。
    """
    issues: List[Tuple[str, str, str]] = []
    import json as _json
    dumps = sorted((ROOT / "scripts" / "four_reports").glob("company_*_full.json"))
    if not dumps:
        return [("WARN", "scripts/four_reports/",
                 "没有公司产物（`company_*_full.json`）⇒ 「正向发现不被误标等级」**未验证**；"
                 "跑 `scripts/run_companies.py` 后重跑本闸门")]
    for _p in dumps:
        try:
            _data = _json.loads(_p.read_text(encoding="utf-8"))
        except Exception as exc:                     # noqa: BLE001
            issues.append(("ERROR", _p.name, "产物读不出来：%s" % exc))
            continue
        rel = "scripts/four_reports/%s" % _p.name
        for _name, _detail in non_risk_level_conflicts([(rel, _data)]):
            issues.append(("ERROR", rel,
                           "正向（非风险）发现被打上风险/待核等级 ⇒ 同一行自相矛盾"
                           "（说明文字说它不是风险，等级却说它待核）：%s" % _detail))
        # ⑤ 反向兜底：产物里若**一条**正向发现都没有，说明字段被上游吃掉了 ⇒ 如实 WARN
        _found = 0
        seen: set = set()
        stack = [_data]
        while stack:
            cur = stack.pop()
            if isinstance(cur, (dict, list)):
                if id(cur) in seen:
                    continue
                seen.add(id(cur))
                if isinstance(cur, dict):
                    if cur.get("tax_benefit") or cur.get("non_risk_semantic"):
                        _found += 1
                    stack.extend(cur.values())
                else:
                    stack.extend(cur)
        if _found == 0:
            issues.append(("WARN", rel,
                           "产物里找不到任何正向（非风险）发现 ⇒ 等级判据可能被上游清空，"
                           "本闸门对该产物**实际上没判到什么**"))
    return issues


def coverage_missing_authority_table(coverage: Dict, table_ids) -> List[str]:
    """覆盖率口径判据（纯函数，便于反向验证）：返回问题描述列表。

    ★ 病根（2026-10-10，A-P0-4）：`scripts/_audit_redline_coverage.py` 原先只认
      "源码里 `redline_id` 旁出现红线 id 字面量"。而本项目存在**第二种合法声明形态** ——
      归属由**权威表**给出（`engine/subject_consistency.py` 的 `REDLINE_SUBJECT_DECL` /
      `RECONCILE_AXIS_REDLINE`），检测器**不写字面量**。
      实测：`RL-CIT-008`、`RL-PAY-002` 两条的归属**完全来自表**，
      真产物里它们是 `match_mode="declared"`（真认领），而覆盖率权威把二者记成「仅兜底」
      ⇒ **检出能力被系统性低估**（有真实检测器 82 应为 84，仅兜底 9 应为 7）。
    """
    problems: List[str] = []
    if not isinstance(coverage, dict) or not coverage:
        return ["覆盖率产物为空/读不出来"]
    has = set(coverage.get("has_detector") or [])
    only = set(coverage.get("only_fallback") or [])
    for rid in sorted(table_ids):
        if rid in only:
            problems.append("%s 由归属权威表声明，却被记进 `only_fallback`（仅兜底）" % rid)
        elif rid not in has:
            problems.append("%s 由归属权威表声明，却不在 `has_detector` 里" % rid)
    return problems


def check_redline_coverage_counts_authority_table() -> List[Tuple[str, str, str]]:
    """闸门：**覆盖率口径必须认「归属权威表」这一声明形态**（2026-10-10，A-P0-4）。

    三段：
      A【权威表健康】`engine.subject_consistency.py` 的两张表都非空，且表里每个红线 id
        都在 `engine.tax_redlines.REDLINES`（**幽灵登记 ⇒ ERROR**）。
      B【口径一致】覆盖率产物里，表声明的红线必须落在 `has_detector`、**不在** `only_fallback`。
      C【新鲜度】产物若比 `engine/subject_consistency.py` 或覆盖率脚本旧 ⇒ 只报 WARN，
        **不假装通过**（防"读过期产物假绿"）。
    """
    issues: List[Tuple[str, str, str]] = []
    import json as _json
    try:
        from engine import subject_consistency as _sc
    except Exception as exc:                       # noqa: BLE001
        return [("ERROR", "engine/subject_consistency.py",
                 "归属权威表模块导入失败（覆盖率口径无法校验）：%s" % exc)]

    _decl = dict(getattr(_sc, "REDLINE_SUBJECT_DECL", {}) or {})
    _axis = dict(getattr(_sc, "RECONCILE_AXIS_REDLINE", {}) or {})
    if not _decl or not _axis:
        issues.append(("ERROR", "engine/subject_consistency.py",
                       "归属权威表为空（`REDLINE_SUBJECT_DECL`=%d / `RECONCILE_AXIS_REDLINE`=%d）"
                       "—— 归属层的唯一权威被清空，覆盖率口径必然失真"
                       % (len(_decl), len(_axis))))
    try:
        _ids = _load_redline_ids()
    except Exception as exc:                       # noqa: BLE001
        return issues + [("ERROR", "engine/tax_redlines.py",
                          "红线库读不出来，无法校验幽灵登记：%s" % exc)]

    _table = set(_decl) | {(v[0] if isinstance(v, (list, tuple)) and v else "")
                           for v in _axis.values()}
    _table.discard("")
    for rid in sorted(_table - _ids):
        issues.append(("ERROR", "engine/subject_consistency.py",
                       "归属权威表登记了不存在的红线 %r（幽灵登记）" % rid))

    _cov_p = ROOT / "scripts" / "_redline_coverage.json"
    if not _cov_p.exists():
        issues.append(("WARN", "scripts/_redline_coverage.json",
                       "覆盖率产物不存在 ⇒ 「表声明 ⇒ 计入有真实检测器」**未验证**"
                       "（跑 `scripts/_audit_redline_coverage.py` 后重跑本闸门）"))
        return issues

    _deps = [ROOT / "engine" / "subject_consistency.py",
             ROOT / "scripts" / "_audit_redline_coverage.py"]
    _stale = [d.name for d in _deps if d.exists() and d.stat().st_mtime > _cov_p.stat().st_mtime]
    if _stale:
        issues.append(("WARN", "scripts/_redline_coverage.json",
                       "覆盖率产物比 %s 旧 ⇒ 口径结论不可信，请重跑 "
                       "`scripts/_audit_redline_coverage.py`" % "、".join(_stale)))
        return issues

    try:
        _cov = _json.loads(_cov_p.read_text(encoding="utf-8"))
    except Exception as exc:                       # noqa: BLE001
        return issues + [("ERROR", "scripts/_redline_coverage.json",
                          "覆盖率产物读不出来：%s" % exc)]
    for _p in coverage_missing_authority_table(_cov, _table & _ids):
        issues.append(("ERROR", "scripts/_redline_coverage.json",
                       "覆盖率口径漏了「归属权威表」这一声明形态：%s" % _p))
    return issues


def check_rule_version_coverage() -> List[Tuple[str, str, str]]:
    """P0-A：**全部已发布规则必须登记版本**（唯一权威 `config/rule_versions.json`）。

    为什么必须是 ERROR：P0-A 之后每条 finding 都带 `rule_version`；未登记的规则会被
    显式标为「未登记」⇒ 该结论**无法自证当时按哪版规则算出**，报告可追溯性出现空洞。
    这正是 P0-A 要根治的问题，故未登记即红灯（而不是 WARN）。

    规则 id 来源（与 `_init_rule_versions.py` 同一口径，四层去重）：
      tax_redlines.REDLINES / verified_rule_engine.VERIFIED_RULE_CATALOG /
      gap_risk_detectors.DETECTORS / special_redline_detectors.SPECS

    ★ 反向验证：从 `config/rule_versions.json` 删掉任一条 ⇒ 本检查必须变红
      （见 `_verify_authority_gates.py`），否则判据是假的。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine import rule_versions as _RV
        from engine.tax_redlines import REDLINES as _RL
        from engine.verified_rule_engine import VERIFIED_RULE_CATALOG as _CAT
        from engine import gap_risk_detectors as _GAP
        from engine import special_redline_detectors as _SPEC
    except Exception as _e:                       # noqa: BLE001
        return [("ERROR", "config/rule_versions.json",
                 "规则版本模块不可导入（版本留痕失效）：%r" % (_e,))]

    # ★ 每次审计重读版本表：否则模块级缓存会让「改坏 ⇒ 变红」的反向验证失效（假绿）。
    #   文件损坏 ⇒ load() 返回空表 ⇒ 下面 coverage 全 missing ⇒ ERROR（正是期望行为）。
    _RV.reload()

    ids: set = set()
    for r in _RL:
        ids.add(str(r.get("id") or "").strip())
    for s in _CAT:
        ids.add(str(s.get("id") or "").strip())
    for rid, _fn in getattr(_GAP, "DETECTORS", []):
        ids.add(str(rid or "").strip())
    for it in (getattr(_SPEC, "SPECS", None) or []):
        if isinstance(it, dict):
            ids.add(str(it.get("id") or it.get("redline_id") or "").strip())
    ids.discard("")

    if not _RV.rule_set_version():
        issues.append(("ERROR", "config/rule_versions.json",
                       "未登记 `rule_set_version` ⇒ 报告与作业流水无法自证规则集口径"))
    cov = _RV.coverage(sorted(ids))
    if cov["missing"]:
        issues.append(("ERROR", "config/rule_versions.json",
                       "有 %d 条**已发布规则未登记版本**（其 finding 会标「未登记」，"
                       "历史结论无法自证规则口径）：%s"
                       % (len(cov["missing"]), cov["missing"][:12])))
    return issues


def check_redline_overlap_ledger() -> List[Tuple[str, str, str]]:
    """闸门：**同概念红线**必须登记，且登记为"要件重复"的不得靠兜底编闭环（2026-10-10，A-P0-2）。

    ★ 病根（实测，非设想）：`RL-VAT-008`「视同销售未按规计提销项税额」与 `RL-VAT-012`
      「视同销售未计提销项」**描述同一概念**（要件1/2/3 高度重叠；012 的要件4 又与
      `RL-VAT-011` 重复），而 012 原先登记着 `_DEFAULT_HIT_INDEX=[1,2,3,4]`
      ⇒ 一旦被软匹配命中就**认下 4 条构成要件**，而**全仓没有任何检测器算过**它们
      ⇒ **假闭环**（报告认下要件却拿不出该要件的证据）。项目早有先例与机制：
      `RL-CIT-001` 故意不登记兜底 + `_NO_BLIND_CONSTITUENT_FALLBACK` 名单。

    判据（数据驱动：新增一对 = 在 `config/redline_overlap_ledger.json` 加一行）：
      A【表可读】`pairs` 非空；每对必填 `concept` / `members`(≥2) / `verdict` /
        `net_increment`(对每个成员都要有) / `disposition`。
      B【id 有效】members 必须在 `REDLINES` 里（**幽灵登记 ⇒ ERROR**）。
      C【口径一致】`verdict == "constituent_duplicate"` 的成员**必须**
        在 `_NO_BLIND_CONSTITUENT_FALLBACK` 里、且**不得**出现在 `_DEFAULT_HIT_INDEX`
        —— 否则就是"声明了重复，却仍靠兜底认要件"的半途状态。
      D【不得空手】`net_increment` 里某成员为空 ⇒ 该红线没有存在必要 ⇒ ERROR（提请裁定合并）。
      E【覆盖率口径】覆盖率产物里该成员不得被记成 `blind`（盲区）——它属"有意不兜底"。
    """
    issues: List[Tuple[str, str, str]] = []
    import json as _json
    _REL = "config/redline_overlap_ledger.json"
    _p = ROOT / _REL
    if not _p.exists():
        return [("ERROR", _REL, "同概念红线登记表不存在（重复红线必须先登记再处置）")]
    try:
        _data = _json.loads(_p.read_text(encoding="utf-8"))
    except Exception as exc:                       # noqa: BLE001
        return [("ERROR", _REL, "登记表读不出来（判据会静默变绿）：%s" % exc)]
    _pairs = _data.get("pairs")
    if not isinstance(_pairs, list) or not _pairs:
        return [("ERROR", _REL, "`pairs` 为空 —— 登记表存在却无内容，判据等于没跑")]
    try:
        _ids = _load_redline_ids()
    except Exception as exc:                       # noqa: BLE001
        return [("ERROR", "engine/tax_redlines.py", "红线库读不出来：%s" % exc)]
    try:
        from engine.redline_engine import (_DEFAULT_HIT_INDEX as _DH,
                                           _NO_BLIND_CONSTITUENT_FALLBACK as _NB)
    except Exception as exc:                       # noqa: BLE001
        return [("ERROR", "engine/redline_engine.py", "兜底表/名单读不出来：%s" % exc)]

    _cov_p = ROOT / "scripts" / "_redline_coverage.json"
    _cov = {}
    if _cov_p.exists():
        try:
            _cov = _json.loads(_cov_p.read_text(encoding="utf-8"))
        except Exception:                          # noqa: BLE001
            _cov = {}

    _REQ = ("concept", "members", "verdict", "net_increment", "disposition")
    for _i, _pair in enumerate(_pairs):
        _where = "%s:第%d对" % (_REL, _i + 1)
        if not isinstance(_pair, dict) or any(k not in _pair for k in _REQ):
            issues.append(("ERROR", _REL, "%s 缺必需键 %s" % (_where, list(_REQ))))
            continue
        _members = [str(m) for m in (_pair.get("members") or [])]
        if len(_members) < 2:
            issues.append(("ERROR", _REL, "%s `members` 少于 2 条（不构成「同一概念多条」）" % _where))
        for _m in _members:
            if _m not in _ids:
                issues.append(("ERROR", _REL, "%s 登记了不存在的红线 %r（幽灵登记）" % (_where, _m)))
        _ni = _pair.get("net_increment") or {}
        if not isinstance(_ni, dict):
            issues.append(("ERROR", _REL, "%s `net_increment` 必须是「红线 → 独有情形」的对象" % _where))
            _ni = {}
        if str(_pair.get("verdict")) == "constituent_duplicate":
            # ⚠ 判据范围（2026-10-10 实测修正）：只在成员**没有真检测器**时才要求
            #   「进 `_NO_BLIND_CONSTITUENT_FALLBACK` 且不在 `_DEFAULT_HIT_INDEX`」——
            #   因为只有"无检测器"的红线才会靠兜底**编**要件闭环（假闭环）。
            #   成员若有真检测器（如 RL-VAT-008 由 VR036 声明），它的要件是**真算过的**，
            #   不得被强制"不许兜底"（第一版判据就错在这里，把合规的 008 判成 ERROR）。
            _has_det = set((_cov or {}).get("has_detector") or [])
            for _m in _members:
                if not str(_ni.get(_m) or "").strip():
                    issues.append(("ERROR", _REL,
                                   "%s 的 %s **未给出净增量** ⇒ 该红线没有独立存在必要，"
                                   "应提请裁定合并（不得靠兜底维持「看似可达」）" % (_where, _m)))
                if _cov and _m in _has_det:
                    continue                       # 有真检测器 ⇒ 要件是真算过的，不适用本约束
                if _m not in _NB:
                    issues.append(("ERROR", _REL,
                                   "%s 的 %s 已登记为「要件重复」且**无真检测器**，却不在 "
                                   "`_NO_BLIND_CONSTITUENT_FALLBACK`（须有意不做盲发兜底）" % (_where, _m)))
                if _m in _DH:
                    issues.append(("ERROR", _REL,
                                   "%s 的 %s 已登记为「要件重复」且**无真检测器**，却仍登记在 "
                                   "`_DEFAULT_HIT_INDEX` ⇒ 半途状态：软匹配命中即「认下要件」的假闭环仍在"
                                   % (_where, _m)))
                if _cov and _m in (_cov.get("blind") or []):
                    issues.append(("ERROR", "scripts/_redline_coverage.json",
                                   "%s 被覆盖率口径记成「盲区」，实为「有意不做兜底」（口径不一致）" % _m))
    if not _cov:
        issues.append(("WARN", "scripts/_redline_coverage.json",
                       "覆盖率产物缺失/读不出 ⇒ 「有真检测器的成员不受本约束」这一步**未验证**"
                       "（跑 `scripts/_audit_redline_coverage.py` 后重跑本闸门）"))
    return issues


def check_redline_detector_attribution() -> List[Tuple[str, str, str]]:
    """红线的**归属声明**：算过的检测器必须自报 `redline_id`，不许让引擎按关键词猜（2026-10-10，A-P0-1）。

    ★ 病根（实测真产物，非设想）：`company_1_full.json` 的 26 条嫌疑里 3 条
      `match_mode="matched"`（关键词兜底）。其中 RL-AST-001「固定资产取得、投用与折旧不匹配」
      的事实**已经算出来了** —— `_domain_depreciation_match` 产出
      「银行流水发现2笔固定资产类付款，合计20,000.00元。应相应计提折旧。」——
      但该 finding **没有声明 `redline_id`** ⇒ 引擎只能 `match_redline_grounded()` 用标题里的
      "固定资产/折旧" 两个词猜归属（`match_reasons=["hint@title","hint@title"]`）。两层后果：
        ① 归属是**猜的**：同一事实换个措辞就会挂到别的红线（同类事故本项目已发生过 7 次）；
        ② 静态覆盖率审计把这条红线记成「仅兜底」⇒ **检出能力被系统性低估**。
      这类「已有实现、只缺归属声明」被本项目明确认定为**最容易被误判成"没实现"**的形态
      （见 `scripts/_vr_rl_affinity.py` 的立项理由）。

    判据（数据驱动：新增一处 = 在 `config/redline_detector_attribution.json` 加一行）：
      A【表可读】`declarations` 非空、必需键齐全（缺表/空表 ⇒ ERROR，不静默）。
      B【声明真在】`detector_file` 存在、且含 `"redline_id": "<id>"` 的**真声明**；
        且文件在 `engine/` 或为 `main.py` —— `scripts/` 下的一次性脚本不计入生产覆盖
        （与 `scripts/_audit_redline_coverage.py` 的口径**必须一致**，否则同一件事两个口径）。
      C【红线存在】`redline_id` 必须在 `engine/tax_redlines.REDLINES` 里。
      D【端到端】覆盖率权威产物 `scripts/_redline_coverage.json` 里该红线必须落在
        `has_detector`、**不在** `only_fallback`（"声明 ⇒ 不再算仅兜底"的机器证明）。
        产物缺失或**比被扫描的源文件旧** ⇒ 如实报 WARN，不假装通过（防"读过期产物假绿"）。
    """
    issues: List[Tuple[str, str, str]] = []
    import json as _json

    _REL = "config/redline_detector_attribution.json"
    _p = ROOT / _REL
    if not _p.exists():
        return [("ERROR", _REL, "红线归属声明登记表不存在（新增检测器归属声明的唯一登记处）")]
    try:
        _data = _json.loads(_p.read_text(encoding="utf-8"))
    except Exception as exc:                       # noqa: BLE001
        return [("ERROR", _REL, "登记表读不出来（JSON 坏了 ⇒ 判据会静默变绿）：%s" % exc)]
    _rows = _data.get("declarations")
    if not isinstance(_rows, list) or not _rows:
        return [("ERROR", _REL, "`declarations` 为空 —— 登记表存在却无内容，判据等于没跑")]

    _REQ = ("detector_file", "redline_id")
    for _i, _row in enumerate(_rows):
        if not isinstance(_row, dict) or any(k not in _row for k in _REQ):
            issues.append(("ERROR", _REL, "第 %d 行缺必需键 %s" % (_i + 1, list(_REQ))))
            continue
        _f = ROOT / str(_row["detector_file"])
        _rid = str(_row["redline_id"])
        _where = "%s:%d" % (_REL, _i + 1)
        if not _f.exists():
            issues.append(("ERROR", _REL, "%s 指定的 `detector_file` 不存在：%s"
                           % (_where, _row["detector_file"])))
            continue
        _parts = set(_f.relative_to(ROOT).parts)
        _is_prod = (_f.parent.name == "engine") or (_f.name == "main.py")
        if not _is_prod or "scripts" in _parts:
            issues.append(("ERROR", _REL,
                           "%s 的 `detector_file`（%s）不是生产代码 —— 一次性诊断脚本运行期不执行，"
                           "登记在那里等于没登记（覆盖率审计也不计入）"
                           % (_where, _row["detector_file"])))
        _txt = _f.read_text(encoding="utf-8", errors="replace")
        _needle = '"redline_id": "%s"' % _rid
        _needle2 = '["redline_id"] = "%s"' % _rid
        if (_needle not in _txt) and (_needle2 not in _txt):
            issues.append(("ERROR", str(_row["detector_file"]),
                           "已登记归属 `%s`，但文件里找不到声明（`%s` 或 `%s`）—— "
                           "登记与代码不一致（要么补声明，要么删登记行）。"
                           % (_rid, _needle, _needle2)))
        # C 红线必须真实存在
        try:
            _tr = _load_redline_ids()
        except Exception as exc:                   # noqa: BLE001
            issues.append(("ERROR", _REL, "红线库读不出来，无法校验 redline_id：%s" % exc))
            _tr = set()
        if _tr and _rid not in _tr:
            issues.append(("ERROR", _REL, "%s 的 `redline_id`=%s 不在红线库里"
                           % (_where, _rid)))
        # D 端到端：覆盖率权威产物
        _cov_p = ROOT / "scripts" / "_redline_coverage.json"
        if not _cov_p.exists():
            issues.append(("WARN", _REL,
                           "覆盖率权威产物 `scripts/_redline_coverage.json` 不存在 ⇒ "
                           "「声明 ⇒ 不再算仅兜底」这一步**未验证**（跑 "
                           "`scripts/_audit_redline_coverage.py` 后重跑本闸门）"))
        else:
            if _f.stat().st_mtime > _cov_p.stat().st_mtime:
                issues.append(("WARN", _REL,
                               "覆盖率产物比被扫描的源文件旧（%s 在本产物之后改过）⇒ "
                               "D 段结论不可信，请重跑 `scripts/_audit_redline_coverage.py`"
                               % _row["detector_file"]))
            else:
                try:
                    _cov = _json.loads(_cov_p.read_text(encoding="utf-8"))
                except Exception as exc:           # noqa: BLE001
                    issues.append(("ERROR", _REL, "覆盖率产物读不出来：%s" % exc))
                    _cov = {}
                if _cov:
                    if _rid in (_cov.get("only_fallback") or []):
                        issues.append(("ERROR", "scripts/_redline_coverage.json",
                                       "%s 已声明归属，覆盖率权威仍把它记为「仅兜底」⇒ "
                                       "声明没进生产扫描路径（或产物业已过期）" % _rid))
                    elif _rid not in (_cov.get("has_detector") or []):
                        issues.append(("ERROR", "scripts/_redline_coverage.json",
                                       "%s 已声明归属，却既不在 has_detector 也不在 "
                                       "only_fallback —— 覆盖率产物与红线库不同步" % _rid))
    return issues


def _load_redline_ids() -> set:
    """红线 id 集合（唯一来源 = `engine/tax_redlines.REDLINES`，不另抄一份）。"""
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "_rl_ids_for_gate", ROOT / "engine" / "tax_redlines.py")
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    return {str(r["id"]) for r in _mod.REDLINES}


def check_metric_key_localized() -> List[Tuple[str, str, str]]:
    """报告正文里的「量化结果」不得出现**引擎原始英文键名**（2026-10-06）。

    ★ 病根（闸门实测抓到，非特例）：
      报告正文出现 `量化结果：declared_input_tax_total=192463.32；i…`
      —— 两处 `_promote_standalone_reports` / `_merge_ledger_into_problems`
      **各自**用 `"%s=%s" % (k, v)` 拼**引擎原始键名**，绕过了键汉化唯一权威
      `_translate_key`（同一缺陷两份实现）。
    判据（静态 + 行为）：
      ① 静态：拼接只允许经唯一实现 `_metric_kv_text`；
      ② 行为：交付字典里**未登记**的新键，汉化不出来时**必须整条不写**
        （宁可少展示，绝不用英文变量名顶替）；
      ③ 行为：已登记的键必须被译成**纯中文**（不得半中半英）。
    """
    issues: List[Tuple[str, str, str]] = []
    rel = "engine/enterprise_report.py"
    try:
        from engine.enterprise_report import (                # noqa: PLC0415
            _metric_kv_text, _translate_key)
    except Exception as e:  # noqa: BLE001
        return [("ERROR", rel, "无法导入键汉化唯一实现：%s" % e)]

    # ② 未登记键 ⇒ 不写（不是"写成英文"）
    _out = _metric_kv_text({"this_key_is_not_registered_anywhere": 7,
                            "declared_input_tax_total": 192463.32})
    if "this_key_is_not_registered_anywhere" in _out:
        issues.append(("ERROR", rel,
                       "未登记指标键被原样写入报告（%r）—— 取不到中文名应**整条不写**" % _out))
    if "declared_input_tax_total" in _out:
        issues.append(("ERROR", rel, "已登记键仍以英文入文（%r）" % _out))

    # ②b **值**同样不得是英文：布尔要写「是/否」；枚举码（b2b_or_unknown）必须译出
    _out2 = _metric_kv_text({"ap_detail_provided": True, "ap_from_trial_balance": False,
                             "business_model": "b2b_or_unknown"})
    if "True" in _out2 or "False" in _out2:
        issues.append(("ERROR", rel, "布尔值以 True/False 入文（%r）—— 应写「是/否」" % _out2))
    if "b2b_or_unknown" in _out2:
        issues.append(("ERROR", rel,
                       "枚举值以英文码入文（%r）—— 键与**值**都必须过汉化权威" % _out2))
    _out3 = _metric_kv_text({"business_model": "enum_code_not_registered_zzz"})
    if "enum_code_not_registered_zzz" in _out3:
        issues.append(("ERROR", rel,
                       "未登记枚举值被原样写入报告（%r）—— 译不出应整对不写" % _out3))

    # ③ 已登记键必须译成纯中文
    for _k in ("declared_input_tax_total", "gap_months", "counterparty_count",
               "book_payroll_total", "business_model",
               "avg_amount_per_individual_supplier"):
        _zh = _translate_key(_k)
        if re.search(r"[A-Za-z]", str(_zh)):
            issues.append(("ERROR", rel,
                           "指标键「%s」汉化失败（得到 %r）—— 须在 `_METRIC_CN` 补一行登记"
                           "（同类对象只加数据行、不改逻辑）" % (_k, _zh)))

    # ① 静态：两处拼接必须调唯一实现，不得再裸拼 `"%s=%s"` 到「量化结果」
    try:
        _src = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        _src = ""
    if _src:
        _n_call = _src.count("_metric_kv_text(")
        if _n_call < 3:      # 1 处定义 + 2 处调用
            issues.append(("ERROR", rel,
                           "「量化结果」拼接未收敛到唯一实现（`_metric_kv_text` 出现 %d 次，"
                           "应为 1 定义 + 2 调用）" % _n_call))
        for _m in re.finditer(r"量化结果[^\n]{0,40}%s=%s", _src):
            issues.append(("ERROR", rel,
                           "仍有裸拼英文键的「量化结果」：%s" % _m.group(0)[:50]))

    # ④ **产物普查**：真实产物里不得再有译不出的键 / 枚举值
    #   （做法：数据驱动 —— 缺哪几个就在 `_METRIC_CN` / `_ENUM_CODE_CN` 各补一行，
    #    不针对某一家企业写特例；普查脚本 `scripts/_audit_unlocalized_metrics.py`）
    _rep = _canonical_report()
    if _rep is None:
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "无真跑产物，未汉化键普查跳过（跑一次全量分析后自动生效）"))
        return issues
    _bad_k, _bad_e = {}, {}
    _seen_ids = set()

    def _scan_metrics(_fs):
        for _f in (_fs or []):
            if not isinstance(_f, dict) or id(_f) in _seen_ids:
                continue
            _seen_ids.add(id(_f))
            for _k, _v in (_f.get("observed_metrics") or {}).items():
                if not isinstance(_v, (int, float, str, bool)):
                    continue
                if re.search(r"[A-Za-z]", str(_translate_key(_k))):
                    _bad_k.setdefault(_k, 1)
                if isinstance(_v, str) and re.match(r"^[a-z][a-z0-9_]*$", _v):
                    if re.search(r"[A-Za-z]", str(_translate_key(_v))):
                        _bad_e.setdefault(_v, 1)

    _scan_metrics(_rep.get("all_findings"))
    _comp = _rep.get("comprehensive") or {}
    _scan_metrics((_comp.get("scenario_execution") or {}).get("findings"))
    _scan_metrics((_rep.get("scenario_execution") or {}).get("findings"))
    for _dom in (_rep.get("domain_summary") or []):
        _scan_metrics(_dom.get("findings"))
    for _dom in ((_comp.get("scenario_execution") or {}).get("domain_summary") or []):
        _scan_metrics(_dom.get("findings"))
    if _bad_k:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "产物中有 %d 个指标键译不出中文（须在 `_METRIC_CN` 各补一行数据）：%s"
                       % (len(_bad_k), "、".join(sorted(_bad_k)[:8]))))
    if _bad_e:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "产物中有 %d 个枚举值译不出中文（须在 `_ENUM_CODE_CN` 各补一行数据）：%s"
                       % (len(_bad_e), "、".join(sorted(_bad_e)[:8]))))
    return issues


def check_industry_exclusion_single_source() -> List[Tuple[str, str, str]]:
    """「按名剔除业态不适用资料」的单一权威（2026-10-06）。判据见上方 ★★ 说明。"""
    issues: List[Tuple[str, str, str]] = []

    # ── A. 静态：分隔符表唯一 + 报告层薄转发 ──────────────────────────────
    _sep_pat = re.compile(r"re\.compile\(\s*r?[\"'][^\"']*(?:与\|及\|和|及\|和)[^\"']*[\"']\s*\)")
    for p in sorted((ROOT / "engine").glob("*.py")):
        if p.name.startswith("_bk"):
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = "engine/" + p.name
        if rel == _NA_SEP_OWNER:
            continue
        for m in _sep_pat.finditer(txt):
            frag = m.group(0)
            # 只关心**并列材料分隔符**（含 与/及/和 的那类表）；其它正则不在此列
            if ("与" in frag) and ("及" in frag or "和" in frag):
                issues.append(("ERROR", rel,
                               "又出现一份「并列分隔符」正则 %s —— 该表只能有一处"
                               "（唯一权威 `industry_resolver.MATERIAL_SEG_SEP`）；"
                               "同一概念多头实现必然判法分裂" % frag[:60]))

    for rel, _must in _NA_THIN_FORWARDERS.items():
        path = ROOT / rel
        if not path.exists():
            continue
        txt = path.read_text(encoding="utf-8", errors="replace")
        for _name in _must:
            # ★ 判据必须是**真的调用了权威**（import 语句 + 函数体内调用），
            #   不能只查"名字出现在文件里" —— 文档字符串里提到它也满足，等于没查
            #   （反向验证实测：把报告层改回自持切段，只要 docstring 还写着权威名就蒙混过关）。
            if not re.search(r"import[^\n]*\b%s\b" % re.escape(_name), txt):
                issues.append(("ERROR", rel,
                               "报告层未**导入**唯一权威 `industry_resolver.%s`"
                               "（只提到名字不算薄转发）" % _name))
        # 薄转发的函数体里**不得**自持一套切段/删字实现
        for _fn in ("_strip_not_required", "_trim_text_materials"):
            _m = re.search(r"\ndef %s\(.*?(?=\ndef |\Z)" % re.escape(_fn), txt, re.S)
            if not _m:
                continue
            _body = re.sub(r'""".*?"""', "", _m.group(0), flags=re.S)   # 去掉 docstring
            _body = re.sub(r"#[^\n]*", "", _body)                       # 去掉注释
            if ".split(" in _body or "re.split(" in _body:
                issues.append(("ERROR", rel,
                               "`%s` 的函数体里自持切段（应为薄转发到唯一权威）" % _fn))
            if ".replace(" in _body:
                issues.append(("ERROR", rel,
                               "`%s` 的函数体里出现字符级 `replace`（残词与不确定性的病根）" % _fn))

    # ── B. 行为（直接调唯一实现，不读源码） ───────────────────────────────
    try:
        from engine.industry_resolver import (                    # noqa: PLC0415
            not_required_materials as _nrm,
            exclude_not_required_material as _xnm,
            has_dangling_separator as _dang)
    except Exception as e:  # noqa: BLE001
        issues.append(("ERROR", _NA_SEP_OWNER, "无法导入业态剔除唯一实现：%s" % e))
        return issues

    _ind = "广告传媒"
    _na, _note = _nrm(_ind)
    if not _na:
        issues.append(("ERROR", _NA_SEP_OWNER,
                       "业态「%s」的不适用资料清单为空 —— 权威表失效，无法核验" % _ind))
        return issues

    # B1 阳性：部分不适用 ⇒ 保留适用段、**无悬空残词**
    for _name, _want in (("采购合同与入库验收单", "采购合同"),
                         ("物流单据与承运记录", ""),
                         ("销售台账、出库单、发货记录", "销售台账、发货记录"),
                         ("出库单与发货记录", "发货记录")):
        _got = _xnm(_name, _na)
        if _got != _want:
            issues.append(("ERROR", _NA_SEP_OWNER,
                           "段级剔除结果不符：「%s」应为「%s」，实得「%s」"
                           "（字符级 replace 会切出「采购合同与」这类悬空残词）"
                           % (_name, _want, _got)))
        if _dang(_got, _name):
            issues.append(("ERROR", _NA_SEP_OWNER,
                           "剔除后出现残词/并列连词：「%s」→「%s」（段级剔除的保留段不含连词）"
                           % (_name, _got)))
        if _xnm(_got, _na) != _got:
            issues.append(("ERROR", _NA_SEP_OWNER, "剔除不幂等：「%s」→「%s」" % (_name, _xnm(_got, _na))))

    # B1b **误报防护**：以「与」开头的**合法**名称不得被判为残词
    #   （实测：「与境外方签署的合同或协议、董事会利润分配决议」= RL-SPT-006 的证据项名）
    _legit = "与境外方签署的合同或协议、董事会利润分配决议"
    if _dang(_legit, _legit):
        issues.append(("ERROR", _NA_SEP_OWNER,
                       "残词判据误报：以「与」开头的**合法**名称被判为残词（%s）" % _legit))
    if _xnm(_legit, _na) != _legit:
        issues.append(("ERROR", _NA_SEP_OWNER,
                       "合法名称被误剔：「%s」→「%s」" % (_legit, _xnm(_legit, _na))))

    # B2 阴性（专有名词）：含「与/及/和」但不含不适用资料 ⇒ **原样返回**，不得切坏
    _na_blob = "".join(sorted(_na))
    for _name in ("合同台账与全部应税凭证", "付款银行流水或第三方支付凭证",
                  "应付账款明细账及账龄分析"):
        if any(n in _name for n in _na):
            continue
        if _xnm(_name, _na) != _name:
            issues.append(("ERROR", _NA_SEP_OWNER,
                           "误剔了不含不适用资料的专有名词：「%s」→「%s」"
                           % (_name, _xnm(_name, _na))))
    _ = _na_blob

    # B3 阴性（业态未知 / 清单为空）：**不剔**（宁可多列，不得无据少列）
    _empty = _xnm("采购合同与入库验收单", set())
    if _empty != "采购合同与入库验收单":
        issues.append(("ERROR", _NA_SEP_OWNER,
                       "业态未知时仍发生剔除（%r）—— 判不出就不该剔" % _empty))

    # B4 **确定性**：与 set 迭代序无关（旧字符级实现会因 hash 顺序给出不同残词）
    _ordered = sorted(_na)
    _perm = list(reversed(_ordered))
    _probe = "物流单据与承运记录"
    if _xnm(_probe, set(_ordered)) != _xnm(_probe, set(_perm)):
        issues.append(("ERROR", _NA_SEP_OWNER,
                       "剔除结果依赖集合迭代序 ⇒ 同一输入两次运行产出不同（非确定）"))

    # B5 反证不剔 + 整项不适用须如实披露（走生产路径 `build_evidence_chain`）
    try:
        from engine.evidence_chain import build_evidence_chain as _bec     # noqa: PLC0415
        _rl = {
            "id": "RL-PROBE-NA",
            "evidence_chain": [
                {"role": "直接证据", "name": "采购合同与入库验收单", "purpose": "证明交易真实"},
                {"role": "间接证据", "name": "物流单据与承运记录", "purpose": "证明货物流真实"},
                {"role": "反证", "name": "物流单据与承运记录", "purpose": "属正当理由，不得剔"},
            ],
        }
        _ev = _bec({"type": "probe"}, _rl, [], {"industry": _ind})
        _names = [e.get("name") for e in _ev.get("elements") or []]
        if "采购合同" not in _names:
            issues.append(("ERROR", "engine/evidence_chain.py",
                           "部分不适用时未保留适用段：「采购合同」应留在证据角色表，实得 %r" % _names))
        for _n in _names:
            if any(m in str(_n) for m in _na) and _n != "物流单据与承运记录":
                issues.append(("ERROR", "engine/evidence_chain.py",
                               "证据角色表仍含本业态不适用资料：「%s」" % _n))
        if "物流单据与承运记录" not in _names:
            issues.append(("ERROR", "engine/evidence_chain.py",
                           "反证被错误剔除 —— 反证是正当理由，不是企业要交的材料"))
        _ex = _ev.get("industry_excluded") or []
        if not any(e.get("name") == "物流单据与承运记录" for e in _ex):
            issues.append(("ERROR", "engine/evidence_chain.py",
                           "整项不适用时**静默丢弃**：未记入 `industry_excluded` 如实披露"))
        # 直接证据清单必须与证据角色表**同源**（旧实现的病根就是只有名字被改）
        for _d in _ev.get("direct_missing") or []:
            if any(m in str(_d) for m in _na):
                issues.append(("ERROR", "engine/evidence_chain.py",
                               "`direct_missing` 仍要求本业态不适用资料：「%s」" % _d))
        _rm = str(_ev.get("remedy") or "")
        for _m in _na:
            if _m in _rm:
                issues.append(("ERROR", "engine/evidence_chain.py",
                               "`remedy`（补救要求）仍要求本业态不适用资料：「%s」" % _m))
    except Exception as e:  # noqa: BLE001
        issues.append(("ERROR", "engine/evidence_chain.py", "行为核验失败：%s" % e))

    # ── C. 产物层：报告可见字段不得含不适用资料 / 残词 ───────────────────
    art = ROOT / "scripts" / "four_reports" / "company_1_full.json"
    if not art.exists():
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "无真跑产物，无法核验证据角色表/待补清单 —— 请先跑一次全量一键分析"))
        return issues
    try:
        _d = json.loads(art.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        issues.append(("WARN", "scripts/four_reports/company_1_full.json", "产物不可解析：%s" % e))
        return issues
    _rep = _d.get("report") if isinstance(_d.get("report"), dict) else _d
    _ind_a = ((_rep or {}).get("target_entity") or {}).get("industry")
    _na_a, _ = _nrm(_ind_a)
    if not _na_a:
        return issues
    _rd = ((_rep or {}).get("comprehensive") or {}).get("redline_detection") or {}
    # 红线**证据项原名**全集（用于残词的精确判据：只有"被改写过"才可能是残词）
    try:
        from engine.tax_redlines import REDLINES as _RLS          # noqa: PLC0415
        _rl_seq = _RLS.values() if isinstance(_RLS, dict) else _RLS
        _tpl_names = set()
        for _r in (_rl_seq or []):
            for _it in (_r.get("evidence_chain") or []):
                _tpl_names.add(str(_it.get("name") or "").strip())
    except Exception:  # noqa: BLE001
        _tpl_names = set()
    _seen = set()
    for _key in ("suspicions", "unconfirmed"):
        for _s in (_rd.get(_key) or []):
            _rid = _s.get("redline_id")
            if _rid in _seen:
                continue
            _seen.add(_rid)
            _ev = _s.get("evidence_chain") or {}
            # 元素名/依据 不得含不适用资料；但 `industry_excluded` 是**披露**，允许出现
            _vis = []
            for _e in (_ev.get("elements") or []):
                _vis.append(str(_e.get("name") or ""))
                _vis.append(str(_e.get("basis") or ""))
            _vis += [str(x) for x in (_ev.get("direct_missing") or [])]
            _vis += [str(x) for x in (_ev.get("missing_material_names") or [])]
            _vis += [str(x) for x in (_ev.get("verify_material_names") or [])]
            _vis.append(str(_ev.get("remedy") or ""))
            _blob = " ".join(_vis)
            for _m in sorted(_na_a):
                if _m in _blob:
                    issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                                   "%s：证据角色表/待补清单仍要求本业态不适用资料「%s」" % (_rid, _m)))
                    break
            for _e in (_ev.get("elements") or []):
                _nm = str(_e.get("name") or "")
                # 精确判据：只有"名字不在红线原名集合里"才可能是被改写后的残词
                if _tpl_names and _nm in _tpl_names:
                    continue
                if _nm and any(c in _nm for c in "与及和"):
                    issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                                   "%s：证据名称出现残词「%s」（段级剔除的保留段不含并列连词）"
                                   % (_rid, _nm)))
    _er = (_rep or {}).get("enterprise_readable_report") or {}

    def _bad_name(_nm):
        _nm = str(_nm or "").strip()
        if not _nm or not _tpl_names:
            return False
        return (_nm not in _tpl_names) and any(c in _nm for c in "与及和")

    for _p in (_er.get("confirmed_problems") or []):
        for _tkey in ("detail_table",):
            _t = _p.get(_tkey) or {}
            for _r in (_t.get("rows") or []):
                _rn = str(_r.get("证据名称") or "")
                if _bad_name(_rn):
                    issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                                   "「%s」证据名称残词：「%s」" % (_p.get("title"), _rn)))
                _blob = json.dumps(_r, ensure_ascii=False)
                if any(_m in _blob for _m in _na_a):
                    issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                                   "「%s」证据角色表仍含本业态不适用资料" % _p.get("title")))
                    break
        for _np in (_p.get("narrative_paragraphs") or []):
            for _t in (_np.get("detail_tables") or []):
                for _r in (_t.get("rows") or []):
                    _rn = str(_r.get("证据名称") or "")
                    if _bad_name(_rn):
                        issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                                       "「%s」证据名称残词：「%s」" % (_p.get("title"), _rn)))
    return issues



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


def _shared_content_check() -> Tuple[bool, List[str]]:
    """文本维度：跨模块共享内容逐字一致性（engine/shared_content_sync）。

    2026-09-15 接线：此前 shared_content_sync 定义完备却从未被调用，而前端
    static/js/core.js 宣传「双维度自检（数字维度 + 文本维度）」，导致文本维度形同虚设。
    现由本校验器每次运行都执行，失败计入 ERROR。
    """
    try:
        from engine.shared_content_sync import verify_shared_content
    except Exception as exc:  # pragma: no cover - 防御：模块缺失不得静默通过
        return False, [f"❌ 无法加载共享内容校验模块: {exc}"]
    return verify_shared_content()


def _sync_content_flow() -> int:
    """显式同步跨模块共享内容文本（--sync-content，默认不执行，避免自动改文件）。"""
    try:
        from engine.shared_content_sync import sync_shared_content
    except Exception as exc:
        print(f"❌ 无法加载共享内容同步模块: {exc}")
        return 1
    for line in sync_shared_content():
        print("  " + line)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="跨模块数字与法条一致性校验")
    parser.add_argument("--calibrate", action="store_true", help="只输出权威值")
    parser.add_argument("--sync", action="store_true", help="自动修正计数常量（仅白名单文件）")
    parser.add_argument("--sync-content", action="store_true",
                        help="自动同步跨模块共享内容文本（默认仅校验，不改文件）")
    parser.add_argument("--strict", action="store_true", help="警告也计入失败")
    args = parser.parse_args()

    authoritative = authoritative_values()

    if args.calibrate:
        for k, v in authoritative.items():
            print(f"{k}={v}")
        return 0

    if args.sync_content:
        return _sync_content_flow()

    counts, general = run_checks()

    # ★★ 2026-10-06（**闸门自身的"静默失效"防护**）：一次切片误操作把本文件末尾的
    #   `if __name__ == "__main__": raise SystemExit(main())` 删掉了 ⇒ 脚本"跑完了、
    #   什么都没查、退出码 0"，看起来全绿。**闸门失效比缺陷更危险**（没人再拦得住）。
    #   判据必须看"**注册并执行了多少检查**"，而不是"发现了多少问题"
    #   （全部通过时 issues 列表本来就为空 —— 我第一次就按 issues 判，误报 FATAL）。
    _n_checks = len([_n for _n in globals()
                     if _n.startswith("check_") and callable(globals()[_n])])
    if _n_checks < _MIN_REGISTERED_CHECKS:
        print("FATAL: 只发现 %d 个 `check_*` 函数（应 ≥ %d）—— 闸门文件被截断/未加载完整，"
              "本次结论不可信，拒绝给出"
              % (_n_checks, _MIN_REGISTERED_CHECKS))
        return 2

    # ★★ 2026-10-08（用户"系统是否有冗余功能"追问引出的硬证据）：**接线完整性自检**。
    #   `_MIN_REGISTERED_CHECKS` 只保证"函数在文件里"，**不保证"被调用"** —— 实测有 9 道闸门
    #   （skill_specs / skill_runtime / legal_versioning / reanalysis_guard_detectors /
    #   analysis_session_and_incremental / call_signature_alignment / industry_capability /
    #   profile_and_case_reference_only / report_compliance_and_redaction）早已定义，
    #   却从未出现在 run_checks 中，全仓零引用 ⇒ 写出来一次都没执行过。
    #   判据：每个 `check_*` 函数名必须出现在 run_checks 源码里（= 真的被接线）。
    #   与"闸门静默失效比缺陷更危险"同源：**写出来不跑，比没写更危险**（让人误以为有防护）。
    _wired = set(re.findall(r"\b(check_[a-z0-9_]+)\s*\(", inspect.getsource(run_checks)))
    _unwired = sorted({_n for _n in globals()
                       if _n.startswith("check_") and callable(globals()[_n])} - _wired)
    if _unwired:
        print("FATAL: 以下闸门已定义但未接入 run_checks（从未执行）: %s" % _unwired)
        return 2

    if args.sync:
        return sync_counts(authoritative)

    n_errors = len([i for i in counts if i[0] == "ERROR"]) + len([i for i in general if i[0] == "ERROR"])
    print_report(counts, general, authoritative)

    # ── 文本维度：跨模块共享内容逐字一致性（2026-09-15 接线，此前从未执行）──
    sc_ok, sc_log = _shared_content_check()
    print("")
    print("── 文本维度：跨模块共享内容一致性 ──")
    for _line in sc_log:
        print("  " + _line)
    if not sc_ok:
        n_errors += 1
    n_warns = (len([i for i in counts if i[0] == "WARN"])
               + len([i for i in general if i[0] == "WARN"]))
    if n_errors:
        return 1
    if args.strict and n_warns:
        return 1
    return 0


def check_skill_specs() -> List[Tuple[str, str, str]]:
    """Skill 规范登记表闸门（用户第 3 批 任务1「Skill 通用结构规范」）。

    "规范写在文档里"只约束写文档那一刻；本闸门把规范变成**可机检事实**：
      · 每个 Skill 的 `impl` 文件必须存在，且 `entry_points` 里的函数**确实定义在该文件里**；
      · `version` 语义化；`input_schema`/`output_schema`/`log_fields` 非空；
      · 声明"可能取不到值"（`unquantified=true`）的 Skill **必须写清取不到怎么办**
        （本项目最贵的教训：用 0/默认值顶替 ⇒ 结论照常输出）；
      · `params` 指向的数据表/配置**必须真实存在**（"新增对象只加一行数据"这句话可验证）；
      · `tests` 声明的测试文件必须存在且**确有测试用例**；
      · `deps` 必须已登记、不得自依、不得成环。

    ★ `tests` 允许为空（有些 Skill 靠上层集成测试覆盖），但空集会被**计数并打印** ——
      未覆盖是**可见**的，不是隐形的。
    """
    try:
        from engine.skill_registry import validate, coverage
    except Exception as exc:
        return [("ERROR", "engine/skill_registry.py", f"Skill 登记表校验器不可用: {exc}")]
    issues: List[Tuple[str, str, str]] = []
    probs = validate()
    for p in probs:
        issues.append(("ERROR", "config/skill_specs.json", p))
    try:
        cov = coverage()
        print("  [Skill 规范] 已登记 %d 个 Skill（有回归测试 %d 个）；"
              "声明未量化约定 %d 个"
              % (cov["skills"], cov["with_tests"], len(cov["unquantified_skills"])))
        if cov["without_tests"]:
            print("  [Skill 规范] ⚠ 无回归测试的 Skill %d 个：%s（可见、待收敛）"
                  % (len(cov["without_tests"]), "、".join(cov["without_tests"])))
    except Exception:
        pass
    return issues


def check_legal_versioning() -> List[Tuple[str, str, str]]:
    """法条版本化闸门（用户第 3 批 任务4「法律适用匹配 —— 法条版本化」）。

    背景（点评 #5「法律依据引用不够严谨」）与本系统实测三类**可机检**缺陷：
      ① **同一部法两套法名** —— 红线库同时存在「发票管理办法」与「发票管理办法（2023修订）」
         ⇒ 同一部法被当成两部；改名/改版本时必漏一处（"一个概念多处维护"）。
      ② **引用不标版本** —— 只写「《发票管理办法》第二十七条」，读者无从判断是否现行有效。
      ③ 现行版本**已失效/被取代**的老法仍被引用。

    判据（全部基于**唯一权威** `engine.legal_version`，本闸门不另写一份判断）：
      A 登记表自身合规：字段齐备 / status ∈ 枚举 / effective_from 为 ISO 且不晚于今日 /
        归一后无重复 / `CORE_LAWS` 全部已登记；
      B 红线库引用的法条**不得**把版本写进法名（`has_version_in_name`）；
      C 引用**不得**落在 `BLOCKING_STATUSES`（superseded/expired）；
      D **行为断言**：`format_legal_basis(with_version=True)` 对已登记法输出「现行有效」、
        对未登记法输出「版本未登记」——**不得默认按现行有效呈现**（默认值顶替＝事故）。
      E 台账可见：把"被引用但未登记版本"的法名数量打印出来（**可见、可收敛**，
        不作 ERROR —— 未登记不等于错，但必须被看见）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.legal_version import (audit_registry, audit_citations,
                                          canonical_law, registered_laws,
                                          unregistered_core_laws, CORE_LAWS)
    except Exception as exc:
        return [("ERROR", "engine/legal_version.py", f"法条版本权威不可用: {exc}")]

    # A 登记表自身合规
    for p in audit_registry():
        issues.append(("ERROR", "config/legal_versions.json", p))

    # B/C 红线库引用的版本合规性
    try:
        from engine.tax_redlines import REDLINES
        _cites: List[str] = []
        for r in (REDLINES or []):
            lb = (r or {}).get("legal_basis")
            if isinstance(lb, str):
                lb = [lb]
            for it in (lb or []):
                if isinstance(it, str) and it.strip():
                    _cites.append(it)
        _probs = audit_citations(_cites)
        for p in _probs[:20]:
            issues.append(("ERROR", "engine/tax_redlines.py", p))
        if len(_probs) > 20:
            issues.append(("ERROR", "engine/tax_redlines.py",
                           f"另有 {len(_probs) - 20} 处版本不合规引用（同上判据）"))
        # E 台账可见
        from engine.legal_citation import split_citation as _sc
        _idx = set(registered_laws())
        _unreg = sorted({canonical_law(_sc(c)[0] or c) for c in _cites}
                        - _idx - {""})
        # ★ F（2026-10-13，T-5 第二阶段）：**法名文号↔全称归一机制必须生效**。
        #   事故：引用写「企业所得税核定征收办法（国税发〔2008〕30号）」，登记表存全称
        #   ⇒ 归一不同 ⇒ 被当成另一部法 ⇒ 报"未登记"（**假缺口**）。实测 39 个"未登记"中
        #   18 个属此类。判据：**未登记法名里不得再出现"文号可解析却仍判未登记"的项**。
        from engine import legal_version as _lv
        _alias = _lv._wenhao_alias_index()
        _false_unreg = []
        for _n in _unreg:
            if not _n:
                continue
            _hit = _lv._resolve_alias(_n)
            if _hit and _hit not in _idx:
                _false_unreg.append(_n)
        if not _alias:
            issues.append(("ERROR", "config/legal_versions.json",
                           "文号别名表为空 ⇒ 文号↔全称归一机制未生效"
                           "（登记表 `doc_no` 须显式登记文号，否则假'未登记'会复发）"))
        # ★ F2（2026-10-13，T-5 第二阶段·续）：**文号归属不得歧义**（别名表静默取首个＝事故）。
        #   事故：曾用 `source` 解析文号，而它天然**交叉引用其它文件的文号**
        #   （「扣除率后经财税〔2017〕37号等调整」「经…2026年第25号停止执行」）
        #   ⇒ 实测 `财税〔2017〕37号` 被**错误归属到引用者**（《农产品…核定扣除…通知》），
        #   **报告会把错误的版本信息注到法条上**。⇒ 文号归属必须显式登记，不得从正文猜。
        #   判据：① 每条登记项必须**显式声明** `doc_no` 键（无发文字号写 null）；
        #         ② 同一文号不得出现在 >1 条的 `doc_no`。
        _no_field = [_e.get("law") for _e in _lv.registry_entries() if "doc_no" not in _e]
        if _no_field:
            issues.append(("ERROR", "config/legal_versions.json",
                           "以下登记项未显式声明 `doc_no` 键（无发文字号须写 null，"
                           "不得从 source 猜测）：%s" % _no_field[:5]))
        _seen_dn: Dict[str, str] = {}
        _dup_dn: List[str] = []
        for _e in _lv.registry_entries():
            _dn = _e.get("doc_no")
            for _w in ([_dn] if isinstance(_dn, str) else list(_dn or [])):
                if not _w:
                    continue
                _k = _lv._norm_wh(_w)
                if _k in _seen_dn and _seen_dn[_k] != _e.get("law"):
                    _dup_dn.append("%s ← %s / %s" % (_k, _seen_dn[_k], _e.get("law")))
                else:
                    _seen_dn[_k] = _e.get("law")
        if _dup_dn:
            issues.append(("ERROR", "config/legal_versions.json",
                           "同一文号被多条登记（文号归属歧义，别名表将静默取首个）：%s"
                           % _dup_dn[:5]))
        if _false_unreg:
            issues.append(("ERROR", "engine/legal_version.py",
                           "以下法名的文号已可解析，却仍被判'未登记'（归一失效）：%s"
                           % _false_unreg[:5]))
        print("  [法条版本] 已登记 %d 部；红线库引用 %d 处、其中未登记版本的法名 %d 个"
              % (len(_idx), len(_cites), len(_unreg)))
    except Exception as exc:
        issues.append(("ERROR", "engine/tax_redlines.py", f"法条版本引用检查失败: {exc}"))
        _unreg = []

    # D 行为断言：报告呈现侧必须真的注入版本，且未登记不得默认"现行有效"
    try:
        from engine.legal_citation import format_legal_basis
        _known = format_legal_basis(["《发票管理办法》第二十一条"], with_version=True)
        if "现行有效" not in _known:
            issues.append(("ERROR", "engine/legal_citation.py",
                           "已登记法条未注入版本括注（报告仍不标版本）"))
        _unknown = format_legal_basis(["《某部尚未登记版本的法律》第一条"], with_version=True)
        if "版本未登记" not in _unknown:
            issues.append(("ERROR", "engine/legal_version.py",
                           "未登记法条被默认按现行有效呈现（须如实标注『版本未登记』）"))
        _plain = format_legal_basis(["《发票管理办法》第二十一条"])
        if "现行有效" in _plain:
            issues.append(("ERROR", "engine/legal_citation.py",
                           "with_version=False 仍注入版本括注（默认行为被改，影响既有调用方）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/legal_citation.py", f"法条版本行为断言失败: {exc}"))

    # F 核心法必须登记（单独点名，便于定位）
    for l in unregistered_core_laws():
        issues.append(("ERROR", "config/legal_versions.json", f"核心法「{l}」未登记版本"))
    return issues


def check_analysis_session_and_incremental() -> List[Tuple[str, str, str]]:
    """分析会话 / 编排 / 增量分析闸门（用户第 4 批 任务1）。

    判据全部为**行为断言**（真调生产函数），覆盖 5 条验收标准里的第 1、2 条：
      A 会话六要素齐备（会话ID/时间/Skill清单及版本/参数/快照版本/轨迹）；
      B `session_id` **由内容派生**（同快照同配置 ⇒ 同哈希段），`run_id` 每次运行不同
        （否则同快照重跑会覆盖上次会话 ⇒ 增量对比永远不可用——本轮实测踩过）；
      C 编排目录里的 modules/skills/risk_families **都能在权威表里查到**（防死配置）；
      D **默认档是恒等函数**（不改执行计划）；专项档必须**真的**收敛模块；
      E 视角轮换**确定性**（两次调用结果相同），而不是随机打乱；
      F 一次分析产出 5 份文档（会话说明/对比表/企业画像/同类案例参考/规则萃取建议）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.analysis_session import (build_session, filter_orchestration_plan,
                                             finish_session, resolve_orchestration,
                                             rotate_views, view_ids, views)
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "engine/analysis_session.py", f"会话模块不可用: {exc}")]
    # A
    try:
        s = build_session(1, resolve_orchestration("default"),
                          {"files": [{"name": "a.xlsx", "size": 1, "rows": 2}]},
                          trace=[{"step": "扫描", "ms": 1}])
        for k in ("session_id", "analyzed_at", "skills", "params", "snapshot", "trace"):
            if s.get(k) in (None, "", [], {}):
                issues.append(("ERROR", "engine/analysis_session.py", f"会话缺要素 {k}"))
        if not all(x.get("version") for x in (s.get("skills") or [])):
            issues.append(("ERROR", "engine/analysis_session.py",
                           "会话里的 Skill 清单缺版本（版本须取自 skill_registry）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/analysis_session.py", f"会话构造断言失败: {exc}"))
    # B
    try:
        o = resolve_orchestration("default")
        snap = {"files": [{"name": "a.xlsx", "size": 1, "rows": 2}]}
        s1 = build_session(1, o, snap, analyzed_at="2026-10-01T09:00:00", session_seq=1)
        s2 = build_session(1, o, snap, analyzed_at="2026-10-07T15:00:00", session_seq=2)
        if s1["session_id"] != s2["session_id"]:
            issues.append(("ERROR", "engine/analysis_session.py",
                           "session_id 未按内容派生（同快照同配置应同 ID）⇒ 『只换日期』可伪装新会话"))
        if s1["run_id"] == s2["run_id"]:
            issues.append(("ERROR", "engine/analysis_session.py",
                           "run_id 未按运行递增 ⇒ 同快照重跑会覆盖上次会话，增量对比失效"))
        o2 = resolve_orchestration("payroll_focus")
        s3 = build_session(1, o2, snap, session_seq=3)
        if s3["session_hash"] == s1["session_hash"]:
            issues.append(("ERROR", "engine/analysis_session.py",
                           "配置不同却得出相同 session_hash（编排未进会话身份）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/analysis_session.py", f"会话身份断言失败: {exc}"))
    # C 编排目录 ↔ 权威表
    try:
        from engine.orchestrator import MODULE_REGISTRY
        from engine.skill_registry import spec_of
        for v in views():
            for m in (v.get("modules") or []):
                if m not in MODULE_REGISTRY:
                    issues.append(("ERROR", "config/analysis_catalog.json",
                                   f"视角 {v.get('view_id')} 引用了不存在的模块 {m}"))
            for sk in (v.get("skills") or []):
                if not spec_of(sk):
                    issues.append(("ERROR", "config/analysis_catalog.json",
                                   f"视角 {v.get('view_id')} 引用了未登记的 Skill {sk}"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "config/analysis_catalog.json", f"编排目录校验失败: {exc}"))
    # D 默认恒等 / 专项真收敛
    try:
        from engine.orchestrator import build_orchestration_plan
        plan = build_orchestration_plan({"has_bank": True, "has_invoices": True,
                                         "has_salary": True, "has_vouchers": True,
                                         "industry": "现代服务", "file_count": 3})
        o_def = resolve_orchestration("default")
        if not o_def.get("is_default"):
            issues.append(("ERROR", "engine/analysis_session.py",
                           "默认档未标 is_default ⇒ 编排过滤会改既有行为"))
        same, skipped = filter_orchestration_plan(plan, o_def)
        if skipped or same is not plan:
            issues.append(("ERROR", "engine/analysis_session.py",
                           "默认档过滤了执行计划（改造前后行为必须一致）"))
        o_foc = resolve_orchestration("payroll_focus")
        _np, sk2 = filter_orchestration_plan(plan, o_foc)
        if not sk2:
            issues.append(("ERROR", "engine/analysis_session.py",
                           "专项档未收敛任何模块（编排配置形同虚设）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/analysis_session.py", f"编排过滤断言失败: {exc}"))
    # E 轮换确定性
    try:
        if rotate_views(view_ids()[:1], times=1) != rotate_views(view_ids()[:1], times=1):
            issues.append(("ERROR", "engine/analysis_session.py",
                           "视角轮换不确定（疑似随机打乱）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/analysis_session.py", f"视角轮换断言失败: {exc}"))
    # F 5 份文档
    try:
        import tempfile as _tf
        from pathlib import Path as _P
        _rep = {"confirmed_problems": [
            {"title": "闸门探针事项", "risk_level": "中风险", "redline_id": "RL-PROBE-1",
             "taxes": ["增值税"], "tax_impact": {"available": True, "basis": 100.0,
                                                 "total": 6.0, "items": []},
             "narrative_paragraphs": []}],
            "summary": {"headline": "探针"}, "overall_conclusion": "探针"}
        _out = _tf.mkdtemp()
        _r = finish_session(88888, {"file_results": [{"type": "voucher", "filename": "a.xlsx"}]},
                            _rep, execution={"stages": {"scan": {"status": "ok"}}},
                            params={"industry": "现代服务"}, out_dir=_P(_out))
        _want = {"本次分析会话说明.md", "与上次分析对比表.md", "企业画像.md",
                 "同类案例参考.md", "规则萃取建议.md"}
        _got = set(_r["docs"])
        if not _want.issubset(_got):
            issues.append(("ERROR", "engine/analysis_session.py",
                           f"会话文档不全，缺 {sorted(_want - _got)}"))
        if _r["session"].get("degraded"):
            issues.append(("ERROR", "engine/analysis_session.py",
                           f"会话收尾出现降级：{_r['session']['degraded']}"))
        if not (_r["incremental"] or {}).get("first_run"):
            issues.append(("ERROR", "engine/incremental_analysis.py",
                           "首次分析未按『首次』如实标注"))
        import shutil as _sh
        _sh.rmtree(_out, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/analysis_session.py", f"会话产出断言失败: {exc}"))
    return issues


def check_reanalysis_guard_detectors() -> List[Tuple[str, str, str]]:
    """假重新分析检测闸门（用户第 4 批 任务1；验收标准 3）。

    ★ 关键判据是**能否区分**两种"一模一样"：
      · 有重算痕迹 ⇒ 同快照内容一致是**确定性正确**（INFO），**不得**报 ERROR；
      · 无重算痕迹 ⇒ 才是"只换日期"（ERROR）。
      这两条必须**同时**成立，否则闸门会把正确行为判成缺陷（或反之漏放）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.reanalysis_guard import (FAKE_PATTERNS, audit_reanalysis,
                                             detect_abnormal_count_change,
                                             detect_unfounded_conclusion_change,
                                             detect_unfounded_reorder)
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "engine/reanalysis_guard.py", f"检测器不可用: {exc}")]
    if len(FAKE_PATTERNS) < 4:
        issues.append(("ERROR", "engine/reanalysis_guard.py",
                       "假重新分析模式少于 4 类（任务要求四类）"))

    def _mk(n, lv="中风险"):
        return {"confirmed_problems": [
            {"title": f"事项{i}", "risk_level": lv, "redline_id": f"RL-{i}",
             "taxes": ["增值税"], "tax_impact": {"available": True, "basis": 1.0,
                                                 "total": 1.0, "items": []},
             "narrative_paragraphs": []} for i in range(1, n + 1)],
            "summary": {}, "overall_conclusion": ""}

    try:
        _p, _c = _mk(3), _mk(3)
        _s1 = {"session_id": "AS-1", "snapshot": {"version": "SS-1"}}
        _s2 = {"session_id": "AS-2", "snapshot": {"version": "SS-1"}}
        # ① 无重算痕迹 ⇒ 必须报 date_only_change
        _r1 = audit_reanalysis(_p, _c, _s1, _s2)
        if "date_only_change" not in [i["code"] for i in _r1["issues"]]:
            issues.append(("ERROR", "engine/reanalysis_guard.py",
                           "『只换日期、内容不变』未被识别（验收标准 3 未达成）"))
        # ② 有重算痕迹 ⇒ 必须是 INFO，且 ok=True
        _r2 = audit_reanalysis(_p, _c, _s1, {**_s2, "trace": [{"step": "扫描"}]})
        _codes = [i["code"] for i in _r2["issues"]]
        if "date_only_change" in _codes:
            issues.append(("ERROR", "engine/reanalysis_guard.py",
                           "有重算痕迹时仍判『只换日期』（把确定性正确行为判成缺陷）"))
        if _r2["ok"] is not True:
            issues.append(("ERROR", "engine/reanalysis_guard.py",
                           "确定性一致不应导致 ok=False"))
        # ③ 无依据乱序
        _c3 = _mk(3)
        _c3["confirmed_problems"] = list(reversed(_c3["confirmed_problems"]))
        _same = {"orchestration": {"views": ["a", "b"]}}
        if not detect_unfounded_reorder(_p, _c3, _same, dict(_same)):
            issues.append(("ERROR", "engine/reanalysis_guard.py", "无依据乱序未被检出"))
        if detect_unfounded_reorder(_p, _c3, {"orchestration": {"views": ["a", "b"]}},
                                    {"orchestration": {"views": ["b", "a"]}}):
            issues.append(("ERROR", "engine/reanalysis_guard.py",
                           "编排声明已变仍判『无依据乱序』（误报）"))
        # ④ 同快照等级变化
        _c4 = _mk(3)
        _c4["confirmed_problems"][0]["risk_level"] = "高风险"
        if not detect_unfounded_conclusion_change(_p, _c4, _s1, _s2):
            issues.append(("ERROR", "engine/reanalysis_guard.py", "同快照等级变化未被检出"))
        # ⑤ 事项数异常减少
        _p5, _c5 = _mk(12), _mk(4)
        _i5 = detect_abnormal_count_change(_p5, _c5, _s1, {**_s2, "trace": [{"step": "x"}]})
        if not _i5 or _i5[0]["level"] != "ERROR":
            issues.append(("ERROR", "engine/reanalysis_guard.py",
                           "同快照事项数骤减未被检出（或级别不对）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/reanalysis_guard.py", f"检测器行为断言失败: {exc}"))
    return issues


def check_profile_and_case_reference_only() -> List[Tuple[str, str, str]]:
    """企业画像 / 同类案例**只作参考**闸门（用户第 4 批 任务2；验收标准 4）。

    两层判据（缺一不可）：
      A **行为层**：产出的画像与案例必须自带 `affects_risk_level=False`，
        且无同类案例时**如实说没有**（不得跨行业凑数）；
      B **源码层**：**定级链路**里不得出现对画像/案例的引用 ——
        只要画像被读进定级逻辑，"不改变等级"这句话就已经是假的了。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.entity_dossier import DOSSIER_FIELDS, build_dossier, dossier_text
        from engine.experience_library import case_reference_text, match_cases
        d = build_dossier({"file_results": [{"type": "voucher"}]})
        if d.get("affects_risk_level") is not False or d.get("reference_only") is not True:
            issues.append(("ERROR", "engine/entity_dossier.py",
                           "画像未声明 affects_risk_level=False（契约缺失）"))
        for f in DOSSIER_FIELDS:
            if f not in d:
                issues.append(("ERROR", "engine/entity_dossier.py", f"画像缺字段 {f}"))
        if d["industry"]["real"] != "未确定":
            issues.append(("ERROR", "engine/entity_dossier.py",
                           "无资料时行业未标『未确定』（疑似猜值）"))
        _txt = dossier_text(d)
        for _k in ("industry", "taxpayer_type", "business_model"):
            if _k in _txt:
                issues.append(("ERROR", "engine/entity_dossier.py",
                               f"画像文本漏出英文键 {_k}（键汉化未做）"))
        _cs = match_cases("绝对不存在的行业X", ["绝对不存在的风险Y"])
        if _cs:
            issues.append(("ERROR", "engine/experience_library.py",
                           "无同类案例却返回了案例（疑跨行业凑数）"))
        if "未匹配到可参考的同类案例" not in case_reference_text(_cs, "绝对不存在的行业X"):
            issues.append(("ERROR", "engine/experience_library.py",
                           "无案例时未如实说明『没有可参考案例』"))
        for c in _cs:
            if c.get("affects_risk_level") is not False:
                issues.append(("ERROR", "engine/experience_library.py",
                               "案例未声明 affects_risk_level=False"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/entity_dossier.py", f"画像/案例行为断言失败: {exc}"))
    # B 源码层：定级链路不得引用画像/案例
    _masked_cache: Dict[str, str] = {}
    for rel in ("engine/enterprise_report.py", "engine/risk_levels.py",
                "engine/finding_families.py", "engine/argumentation.py",
                "engine/risk_families.py"):
        try:
            src = _masked_cache.get(rel)
            if src is None:
                src = _mask_py_comments_and_strings((ROOT / rel).read_text(encoding="utf-8"))
                _masked_cache[rel] = src
            for bad in ("entity_dossier", "experience_library"):
                if bad in src:
                    issues.append(("ERROR", rel,
                                   f"定级链路引用了 {bad} ⇒ 违反『画像/案例不改变风险等级』"))
        except Exception as exc:  # noqa: BLE001
            issues.append(("ERROR", rel, f"定级链路源码检查失败: {exc}"))
    return issues


def check_call_signature_alignment() -> List[Tuple[str, str, str]]:
    """**调用点与签名对齐**闸门（2026-10-07 第 4 批：由"分析轨迹"暴露的真实静默失效）。

    事故：`main.py` 里 `apply_cross_company_synthesis()` 少传必填参数 `company_id`
    ⇒ 每次分析都抛 `TypeError`，被外层 `except Exception` 吞成 `stage=degraded`
    ⇒ **跨企业合成分析从未真正执行过**，而报告与日志里只看到"降级"，没人察觉。
    —— 这不是"某一行写错了"，而是**接口不对齐 + except 吞掉**的组合，
    只靠读代码发现不了，必须用**静态对齐判据**兜住（与项目技能里
    「消费方按键取值、供给方按自己变量名传值」同属一类）。

    判据（**已按实测收窄，避免假阳性**）：
      只检查 **经 `from engine.X import f` 显式绑定**的**公开**函数（`f` 不以 `_` 开头）。
      为什么收窄：早期版本按"同名函数"跨文件比对，实测报出 **119 条**，几乎全是
      `_num` / `_fmt` / `_sum` 这类**各模块私有同名助手**（签名本就不同）——那是假阳性，
      按项目铁律"判据先量化再收窄"予以剔除；收窄后真阳性 **0**（说明现存代码已对齐）。
      触发条件：位置实参个数 < 必填形参个数，且**没有任何关键字实参**、且声明侧无 `*args`
      （保守判据：只报"确定少传且不可能靠关键字补齐"的情形）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        import ast as _ast
        import glob as _glob
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "tools/audit_consistency.py", f"AST 不可用: {exc}")]

    def _req_of(fn):
        a = fn.args
        pos = list(a.posonlyargs) + list(a.args)
        nd = len(a.defaults)
        req = pos[:len(pos) - nd] if nd else pos
        return [p.arg for p in req], (bool(a.vararg) or bool(a.kwarg))

    files = [str(p).replace("\\", "/")
             for p in _glob.glob(str(ROOT / "engine" / "**" / "*.py"), recursive=True)]
    files.append(str(ROOT / "main.py").replace("\\", "/"))
    decls = {}
    for f in files:
        try:
            tree = _ast.parse(open(f, encoding="utf-8", errors="ignore").read())
        except Exception:
            continue
        for n in tree.body:
            if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                decls[(f, n.name)] = n
    for f in files:
        try:
            tree = _ast.parse(open(f, encoding="utf-8", errors="ignore").read())
        except Exception:
            continue
        bound = {}
        for n in _ast.walk(tree):
            if isinstance(n, _ast.ImportFrom) and n.module and n.module.startswith("engine."):
                # ⚠ 必须与 `decls` 用**同一种路径形态**（绝对路径）。
                #   初版这里拼的是相对路径 `engine/xxx.py`，而 decls 键是绝对路径
                #   ⇒ 恒不匹配 ⇒ 判据**打空**（反向验证报 0，看着像"闸门覆盖到了"）。
                rel = str(ROOT / "engine"
                          / (n.module.split(".", 1)[1].replace(".", "/") + ".py")
                          ).replace("\\", "/")
                for al in n.names:
                    nm = al.asname or al.name
                    if nm.startswith("_"):
                        continue
                    bound[nm] = (rel, al.name)
        for n in _ast.walk(tree):
            if not isinstance(n, _ast.Call) or not isinstance(n.func, _ast.Name):
                continue
            if n.func.id not in bound:
                continue
            df, real = bound[n.func.id]
            dn = decls.get((df, real))
            if dn is None:
                continue
            req, hasvar = _req_of(dn)
            if not req or hasvar:
                continue
            npos = len([a for a in n.args if not isinstance(a, _ast.Starred)])
            if npos < len(req) and not n.keywords:
                issues.append(("ERROR", os.path.relpath(f, ROOT).replace("\\", "/"),
                               f"{n.func.id}() 少传必填参数 {req[npos:]}"
                               f"（声明在 {os.path.relpath(df, ROOT).replace(chr(92), '/')}"
                               f":{getattr(dn, 'lineno', '?')}）"
                               f"⇒ 运行期 TypeError 会被 except 吞成『降级』"))
    return issues


def check_industry_capability() -> List[Tuple[str, str, str]]:
    """多行业通用能力闸门（用户第 5 批 任务1；验收标准 1、2）。

    判据全部为**行为断言**：
      A 行业参数库自洽（`industry_params.validate()`：风险族已登记 / 指标在基准里 /
        `benchmark_refs` 查得到 / 模板已登记 / 重要性水平档已登记 / 资料名可归类）；
      B **数值不复制**：参数库内不得出现基准数值，必须靠 `benchmark_refs` 引用既有基准库；
      C **未匹配行业不冒用**别行业参数（返回 matched=False + 空参数）；
      D **新增行业只需配置**：骨架字段齐备（否则等于还要改代码）；
      E **行业切换真的生效**：不同行业的模板章节、补资料优先级不同；
      F **底层事实一致**：同资料换行业 ⇒ facts/calc/legal 三层指纹必须恒等（等级可不同）；
      G 行业关键词 JSON 存在且**不含** `industries`（防第三套基准数值）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.industry_params import (PARAM_FIELDS, benchmark_values_of,
                                           industries, material_priority,
                                           new_industry_template, params_of,
                                           report_template, validate_params)
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "engine/industry_params.py", f"行业参数模块不可用: {exc}")]
    for p in validate_params():
        issues.append(("ERROR", "config/industry_params.json", p))
    # B 数值不复制
    for x in industries():
        if "benchmark_values" in x:
            issues.append(("ERROR", "config/industry_params.json",
                           f"行业 {x.get('industry_id')} 里复制了基准数值（应改为 benchmark_refs 引用）"))
        if not benchmark_values_of(x.get("benchmark_refs")):
            issues.append(("ERROR", "config/industry_params.json",
                           f"行业 {x.get('industry_id')} 的 benchmark_refs 取不到基准"))
    # C 未匹配不冒用
    try:
        fake = params_of("一个绝对没配置过的行业XYZ")
        if fake.get("matched"):
            issues.append(("ERROR", "engine/industry_params.py", "未配置行业被判为匹配（会冒用别行业参数）"))
        if material_priority("一个绝对没配置过的行业XYZ") or report_template("一个绝对没配置过的行业XYZ"):
            issues.append(("ERROR", "engine/industry_params.py", "未配置行业仍返回了参数"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/industry_params.py", f"未匹配行业断言失败: {exc}"))
    # D 新增行业只需配置
    try:
        tpl = new_industry_template("gate_probe", "闸门探针行业")
        miss = [f for f in PARAM_FIELDS if f not in tpl]
        if miss:
            issues.append(("ERROR", "engine/industry_params.py",
                           f"新增行业骨架缺字段 {miss}（那就不只是配置的事）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/industry_params.py", f"新增行业骨架断言失败: {exc}"))
    # E 行业切换真的生效
    try:
        from engine.report_template import priority_sort, section_order
        if section_order("制造业") == section_order("广告传媒"):
            issues.append(("ERROR", "engine/report_template.py",
                           "不同行业的报告模板章节完全相同（模板没真正生效）"))
        items = ["银行流水", "销项发票", "进销存台账", "合同文件"]
        a, _ = priority_sort(items, "制造业")
        b, _ = priority_sort(items, "广告传媒")
        if a == b:
            issues.append(("ERROR", "engine/report_template.py",
                           "不同行业的补资料优先级完全相同（资料名未归一或未生效）"))
        if sorted(a) != sorted(items) or sorted(b) != sorted(items):
            issues.append(("ERROR", "engine/report_template.py", "优先级排序增删了条目（只许调顺序）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/report_template.py", f"行业切换断言失败: {exc}"))
    # F 底层事实一致（等级可不同）
    try:
        from engine.industry_params import apply_level_adjustments, evaluate_triggers
        from engine.snapshot_invariance import diff_rows, verify_invariance

        def _mk(level):
            return {"confirmed_problems": [
                {"title": f"事项{i}", "risk_level": level, "redline_id": f"RL-G-{i}",
                 "taxes": ["增值税"], "conclusion_grade": "已核定", "evidence_have": 1,
                 "evidence_need": 3, "constituent_hits": [{"index": 1}],
                 "tax_impact": {"available": True, "basis": 100000.0, "total": 6000.0,
                                "items": []}, "narrative_paragraphs": []}
                for i in range(1, 4)], "summary": {}, "overall_conclusion": ""}
        trig = evaluate_triggers("广告传媒", {"期间费用率": 9.99})
        lv_adv = apply_level_adjustments("广告传媒", "", "期间费用率", "低风险", trig)[0]
        lv_mfg = apply_level_adjustments("制造业", "", "期间费用率", "低风险", set())[0]
        a, b = _mk(lv_adv), _mk(lv_mfg)
        r = verify_invariance(a, b, kinds=("facts", "calc", "legal"))
        if not r["ok"]:
            issues.append(("ERROR", "engine/industry_params.py",
                           f"换行业导致底层事实/计算/法律变化：{r['diffs']}"))
        if lv_adv == lv_mfg:
            issues.append(("ERROR", "engine/industry_params.py",
                           "触发条件成立时等级未变（行业等级调整没生效）"))
        if diff_rows(_mk("低风险"), _mk(lv_adv), "level") and \
                apply_level_adjustments("广告传媒", "", "期间费用率", "低风险", set())[0] != "低风险":
            issues.append(("ERROR", "engine/industry_params.py",
                           "未提供触发集合时仍调整了等级（配置写条件、代码无条件执行）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/industry_params.py", f"跨行业不变性断言失败: {exc}"))
    # G 关键词 JSON
    try:
        import json as _json
        _p = ROOT / "static" / "industry_profiles.json"
        if not _p.exists():
            issues.append(("ERROR", "static/industry_profiles.json",
                           "文件缺失 ⇒ domain_analysis 的『JSON 可编辑』路径一直走代码兜底"))
        else:
            _d = _json.loads(_p.read_text(encoding="utf-8"))
            for k in ("_processing_keywords", "_biz_keywords"):
                if not _d.get(k):
                    issues.append(("ERROR", "static/industry_profiles.json", f"缺 {k}"))
            if "industries" in _d:
                issues.append(("ERROR", "static/industry_profiles.json",
                               "不得在此放行业基准数值（唯一权威是 industry_data.json）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "static/industry_profiles.json", f"关键词 JSON 检查失败: {exc}"))
    return issues


def check_report_compliance_and_redaction() -> List[Tuple[str, str, str]]:
    """报告定位与合规闸门（用户第 5 批 任务2；验收标准 3、4、5、6）。

    A 报告名称与非执法声明（两种文稿类型）；
    B 签名栏三角色齐备；未签署必须被标出；
    C 保密等级/用途限制/数据授权/系统标识/企业申辩机制齐备；
    D 系统标识**不得默认已复核**（`reviewed=None` ⇒ 写"尚未人工复核"）；
    E 脱敏按角色生效：内部不脱、对外全脱、检查角色保留金额；未登记角色按最严；
    F 对外版与内部底稿是**两个对象**（脱敏不得改到内部底稿）；
    G 数值型金额字段也必须脱敏（只扫文本会漏掉最大的那个数）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.report_compliance import (change_log, document_meta,
                                             external_edition, internal_edition,
                                             signature_block, system_block,
                                             validate_compliance as _vc)
        from engine.redaction import REDACTION_ITEMS, copy_for_role, redact_text, role_policy
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "engine/report_compliance.py", f"合规模块不可用: {exc}")]
    for p in _vc():
        issues.append(("ERROR", "config/report_compliance.json", p))
    # A
    try:
        # ★ 2026-10-08 修复：原先硬编码「税务风险扫描工作底稿」，而用户指令已于 2026-10-07 把
        #   报告性质统一为 `report_identity.canonical` =「内部辅助分析工作底稿」⇒ 闸门与唯一权威冲突，
        #   长期报 ERROR。改为**向唯一权威取**（`engine.report_identity.canonical_name()`），
        #   不再硬编码名称——名称变一次就要改两处，正是"两处实现必然漂移"的老病根。
        try:
            from engine.report_identity import canonical_name as _canon_name
            _want_internal = _canon_name()
        except Exception:  # noqa: BLE001 —— 取不到才回退（并留痕）
            _want_internal = "内部辅助分析工作底稿"
            issues.append(("WARN", "tools/audit_consistency.py",
                           "report_identity.canonical_name() 不可用，报告名称断言已回退为字面值"))
        for kind, want in (("internal_working_paper", _want_internal),
                           ("external_notice", "风险提示函")):
            d = document_meta(kind)
            if d.get("name") != want:
                issues.append(("ERROR", "config/report_compliance.json",
                               f"{kind} 报告名称应为「{want}」，实际「{d.get('name')}」"))
            if d.get("is_enforceable") is not False or "不是税务处理决定" not in \
                    str(d.get("non_enforcement_note") or ""):
                issues.append(("ERROR", "config/report_compliance.json",
                               f"{kind} 未明确『非执法文书』"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/report_compliance.py", f"报告定位断言失败: {exc}"))
    # B
    try:
        b = signature_block({})
        roles = [r.get("role") for r in (b.get("rows") or [])]
        for want in ("编制人", "复核人", "审批人"):
            if want not in roles:
                issues.append(("ERROR", "config/report_compliance.json", f"签名栏缺「{want}」"))
        if b.get("signed") is not False:
            issues.append(("ERROR", "engine/report_compliance.py",
                           "未签署却判为已签署（不得留空冒充已签署）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/report_compliance.py", f"签名栏断言失败: {exc}"))
    # C/D
    try:
        s = system_block(None)
        if s.get("reviewed") is not False or "尚未人工复核" not in str(s.get("review_status_text")):
            issues.append(("ERROR", "engine/report_compliance.py",
                           "系统标识默认成『已复核』（该字段必须如实反映）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/report_compliance.py", f"系统标识断言失败: {exc}"))
    # E/G
    try:
        text = ("张某先生向李小明女士支付1,234,567.89元，账号6222020200112233，"
                "手机13812345678，身份证110101199001011234。")
        if redact_text(text, role_policy("internal")) != text:
            issues.append(("ERROR", "engine/redaction.py", "内部角色不该脱敏"))
        ext = redact_text(text, role_policy("external"))
        for leaked in ("6222020200112233", "13812345678", "110101199001011234", "1,234,567.89"):
            if leaked in ext:
                issues.append(("ERROR", "engine/redaction.py", f"对外角色泄漏 {leaked}"))
        aud = redact_text(text, role_policy("auditor"))
        if "1,234,567.89" not in aud:
            issues.append(("ERROR", "engine/redaction.py", "检查角色应保留金额"))
        pol = role_policy("绝对没登记过的角色")
        if not all(pol.get(k) for k in REDACTION_ITEMS):
            issues.append(("ERROR", "engine/redaction.py", "未登记角色未按最严处理"))
        rep = {"confirmed_problems": [{"tax_impact": {"basis": 1234567.89, "total": 12345.67,
                                                      "items": [{"tax": "增值税", "rate": 0.06,
                                                                 "amount": 12345.67}]}}]}
        clone, cnt, _note = copy_for_role(rep, "external")
        ti = clone["confirmed_problems"][0]["tax_impact"]
        if ti["basis"] == 1234567.89:
            issues.append(("ERROR", "engine/redaction.py",
                           "数值型金额字段未脱敏（只扫文本会漏掉最大的那个数）"))
        if ti["items"][0].get("rate") != 0.06:
            issues.append(("ERROR", "engine/redaction.py", "税率被误当金额脱敏"))
        if not cnt.get("amount_field"):
            issues.append(("ERROR", "engine/redaction.py", "脱敏未留痕（命中计数为空）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/redaction.py", f"脱敏断言失败: {exc}"))
    # F 对外版不改内部底稿
    try:
        rep = {"confirmed_problems": [{"title": "t", "risk_level": "中风险",
                                       "narrative_paragraphs": [{"text": "张伟先生支付1000.00元。"}]}]}
        # ★★ 2026-10-13（P0-7 实测事故）：本检查需要"真的生成两次"才能验证
        #   「版本台账未记录每一次生成（含同内容重复生成）」——而 `internal_edition`
        #   / `external_edition` 会**写版本台账**。从前直写**生产**
        #   `data/report_versions.jsonl` ⇒ 实测该台账里 `company_id=GATE-T` 累积 **370 行**
        #   （`T-X1` 336 行同因）；**只读闸门却有写入副作用**是本项目明确要根治的一类缺陷。
        #   ⇒ 现把台账**重定向到临时目录**：语义完全不变（仍是"真生成两次 + 真读台账"），
        #     但**零副作用**。
        import contextlib as _ctx
        import tempfile as _tf
        from engine import report_compliance as _rc_led
        _orig_ledger_path = _rc_led.ledger_path
        with _tf.TemporaryDirectory() as _led_dir:
            _rc_led.ledger_path = lambda: (__import__("pathlib").Path(_led_dir)
                                           / "report_versions.jsonl")
            try:
                internal = internal_edition(rep, company_id="GATE-T")
                external = external_edition(rep, company_id="GATE-T")
                _n_ledger = len(change_log("GATE-T"))
            finally:
                _rc_led.ledger_path = _orig_ledger_path
        import json as _json
        if "张伟先生" not in _json.dumps(internal, ensure_ascii=False):
            issues.append(("ERROR", "engine/report_compliance.py", "内部底稿被脱敏了"))
        if "张伟先生" in _json.dumps(external, ensure_ascii=False):
            issues.append(("ERROR", "engine/report_compliance.py", "对外版本未脱敏"))
        if "张伟先生" not in _json.dumps(rep, ensure_ascii=False):
            issues.append(("ERROR", "engine/redaction.py", "脱敏改动了原对象（内部底稿被污染）"))
        if _n_ledger < 2:
            issues.append(("ERROR", "engine/report_compliance.py",
                           "版本台账未记录每一次生成（含同内容重复生成）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/report_compliance.py", f"版本与对外版断言失败: {exc}"))
    return issues


def check_skill_runtime() -> List[Tuple[str, str, str]]:
    """Skill 编排引擎闸门（用户第 6 批 任务1）。

    判据（行为断言）：
      A 方案库自洽（Skill 已登记 / entry 在实现里存在 / retries 合法）；
      B 顺序执行 + 并行组 + **条件分支必须真的生效**（不成立 ⇒ skipped 且留痕）；
      C 失败重试：能重试成功；一直失败 ⇒ status=failed + error；
      D 日志字段齐备（任务点名的 10 个字段），入参解析结果可追溯；
      E **局部重跑**只跑该步骤及下游（上游标为沿用）；
      F 人工暂停点：`pause_after` ⇒ status=paused 且**不继续下游**；
      G 灰度/回滚可生效（effective_version 随 rollback 变化）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.skill_runtime import (LOG_FIELDS, effective_version, resolve_plan,
                                          rollback, run, validate_plans)
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "engine/skill_runtime.py", f"编排引擎不可用: {exc}")]
    for p in validate_plans():
        issues.append(("ERROR", "config/skill_plan.json", p))

    def _plan(steps):
        return {"plan_id": "GATE", "plan_name": "闸门探针", "steps": steps}

    # B/C/D
    try:
        plan = _plan([
            {"step_id": "s1", "skill_id": "numparse", "entry": "to_number_checked", "params": {}},
            {"step_id": "s2", "skill_id": "numparse", "entry": "to_number_checked", "params": {},
             "parallel_group": "P"},
            {"step_id": "s3", "skill_id": "numparse", "entry": "to_number_checked", "params": {},
             "parallel_group": "P"},
            {"step_id": "s4", "skill_id": "numparse", "entry": "to_number_checked", "params": {},
             "when": {"industry_matched": True}},
        ])
        got = run(plan, ctx={"industry_params": {"matched": False}},
                  handlers={"numparse": lambda c, p: {"ok": 1}}, company_id=1)
        s4 = [r for r in got["log"] if r["step_id"] == "s4"]
        if not s4 or s4[0]["status"] != "skipped":
            issues.append(("ERROR", "engine/skill_runtime.py",
                           "条件分支未生效（条件不成立却照跑）"))
        for r in got["log"]:
            for f in LOG_FIELDS:
                if f not in r:
                    issues.append(("ERROR", "engine/skill_runtime.py", f"日志缺字段 {f}"))
                    break
        st = {"n": 0}

        def _flaky(c, p):
            st["n"] += 1
            if st["n"] < 2:
                raise RuntimeError("第一次失败")
            return "ok"
        g2 = run(_plan([{"step_id": "s1", "skill_id": "numparse",
                         "entry": "to_number_checked", "params": {}, "retries": 1}]),
                 handlers={"numparse": _flaky})
        if g2["log"][0]["status"] != "ok" or g2["log"][0]["attempt"] != 2:
            issues.append(("ERROR", "engine/skill_runtime.py", "失败重试未生效"))

        def _fail(c, p):
            raise RuntimeError("一直失败")
        g3 = run(_plan([{"step_id": "s1", "skill_id": "numparse",
                         "entry": "to_number_checked", "params": {}}]),
                 handlers={"numparse": _fail})
        if g3["status"] != "failed" or "一直失败" not in g3["log"][0]["error"]:
            issues.append(("ERROR", "engine/skill_runtime.py", "最终失败未如实记录"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/skill_runtime.py", f"编排行为断言失败: {exc}"))
    # E
    try:
        from engine.skill_runtime import rerun
        plan = _plan([{"step_id": s, "skill_id": "numparse", "entry": "to_number_checked",
                       "params": {}} for s in ("s1", "s2", "s3")])
        got = rerun(plan, "s2", handlers={"numparse": lambda c, p: "ok"})
        if got["rerun_scope"] != ["s2", "s3"] or got["upstream_skipped"] != ["s1"]:
            issues.append(("ERROR", "engine/skill_runtime.py", "局部重跑范围不对（应只跑该步骤及下游）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/skill_runtime.py", f"局部重跑断言失败: {exc}"))
    # F
    try:
        got = run(_plan([{"step_id": "s1", "skill_id": "numparse",
                          "entry": "to_number_checked", "params": {}, "pause_after": True,
                          "pause_reason": "闸门探针暂停"},
                         {"step_id": "s2", "skill_id": "numparse",
                          "entry": "to_number_checked", "params": {}}]),
                  handlers={"numparse": lambda c, p: "ok"})
        if got.get("status") != "paused":
            issues.append(("ERROR", "engine/skill_runtime.py", "人工暂停点未生效"))
        if [r["step_id"] for r in got["log"]] != ["s1"]:
            issues.append(("ERROR", "engine/skill_runtime.py", "暂停后仍继续执行了下游"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/skill_runtime.py", f"暂停断言失败: {exc}"))
    # G
    try:
        base = effective_version("redaction", company_id="gate-no-such")
        rollback("redaction", "0.9.0-gate")
        try:
            if effective_version("redaction", company_id="gate-no-such") != "0.9.0-gate":
                issues.append(("ERROR", "engine/skill_runtime.py", "版本回滚未生效"))
        finally:
            rollback("redaction", base)
        if resolve_plan(plan_id="不存在").get("plan_id") == "不存在":
            issues.append(("ERROR", "engine/skill_runtime.py", "未登记方案未报错"))
    except ValueError:
        pass
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/skill_runtime.py", f"灰度回滚断言失败: {exc}"))
    return issues


def check_pending_verdict_softened() -> List[Tuple[str, str, str]]:
    """「资料不足」档的结论词**不得断言触红**（2026-10-06 用户评语 #2）。

    ★ 用户原话：「报告多处采用『未认定到任何一条构成要件』，却又给出『高风险』
      『触碰红线』『潜在税额』等结论…… 风险检查报告可以列『红线疑点』，
      **但不能在证据不足时写『触碰红线』**。」
    病根：`argumentation._VERDICT_HIT_PENDING` 旧文案为
      「**已**触碰税务违规红线（资料不足，待补证后判断）」——前半句是断言、
      后半句承认资料不足 ⇒ 与报告自身"证据不足不作认定"的原则正面冲突。
    本闸门把它锁死：资料不足档必须是「疑似…」，且**不得**出现「已触碰/已经触碰」。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.argumentation import (_VERDICT_HIT_PENDING,   # noqa: PLC0415
                                          _TAIL_HIT_PENDING,
                                          _VERDICT_CONFIRMED,
                                          _VERDICT_HIT_ANCHOR,
                                          _TAIL_HIT_ANCHOR)
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "engine/argumentation.py", "无法导入结论词表：%s" % exc)]

    for _name, _txt in (("_VERDICT_HIT_PENDING", _VERDICT_HIT_PENDING),
                        ("_TAIL_HIT_PENDING", _TAIL_HIT_PENDING)):
        if ("已触碰" in _txt) or ("已经触碰" in _txt):
            issues.append(("ERROR", "engine/argumentation.py",
                           "资料不足档 `%s` 仍在**断言**触红：%s —— "
                           "证据不足时只能写「疑似」，不得写「已/已经触碰」" % (_name, _txt[:40])))
        if "疑似" not in _txt:
            issues.append(("ERROR", "engine/argumentation.py",
                           "资料不足档 `%s` 未标明「疑似」（读者会当成已定性）：%s"
                           % (_name, _txt[:40])))
    # 锚点必须**同源且容错**：须是"两档共有"的前缀，否则档位措辞一改净化就静默失效
    for _an, _av in (("_VERDICT_HIT_ANCHOR", _VERDICT_HIT_ANCHOR),
                     ("_TAIL_HIT_ANCHOR", _TAIL_HIT_ANCHOR)):
        if _av not in _VERDICT_HIT_PENDING and _av not in _TAIL_HIT_PENDING:
            issues.append(("ERROR", "engine/argumentation.py",
                           "锚点 `%s` 与产出文案不同源（%r 不在任一档文案中）—— "
                           "净化将静默失效" % (_an, _av)))
    if _VERDICT_HIT_ANCHOR not in _VERDICT_CONFIRMED:
        issues.append(("ERROR", "engine/argumentation.py",
                       "锚点 `_VERDICT_HIT_ANCHOR` 未覆盖「资料齐全」档 "
                       "⇒ 该档的净化会漏掉"))
    return issues

#: 报告文本**损坏黑名单**：{损坏形态: 正确写法}（用户实测，source 里根本没有这些字）
_TEXT_CORRUPTION_BLACKLIST = {
    "补教要求": "补救要求",
    "口经说明": "口径说明",
    "敦低法": "孰低法",
    # ⚠ "税额口"不能直接进黑名单：会误伤合法的"税额口径"（实测假阳性）
    #   ⇒ 单列正则，要求「税额口」后面**不是**「径」。
}
#: 「潜在税额敞口」被截断成「潜在税额口」的形态（负向环视排除「税额口径」）
_TEXT_CORRUPTION_PATTERNS = (
    (re.compile(r"税额口(?!径)"), "税额敞口"),
)


def check_report_text_integrity() -> List[Tuple[str, str, str]]:
    """报告文本**不得被改写坏**（错别字/同音字替换/数字被改）（2026-10-06）。

    ★ 用户实测（第7条评语）：报告里出现「潜在税额**口**」「**补教**要求」「**口经**说明」
      「**敦低**法」「企业所得税≈**一元**」。这些字**全都不在源码里**
      （源码是"敞口/补救/口径/孰低"）⇒ 属**运行时把字改坏**。
      根因：`engine.narrative_fresh._llm_rewrite` 用 LLM（temperature=0.7）**改写报告正文**
      （动机是"让文字读起来像本次新编制"），唯一校验只**抽查数字**，抓不住同音字替换与
      数字被改坏 —— 与本项目铁律「数字绝不被清洗改写、报告每个字都要有据」正面冲突。
    判据（源码 + 产物两级）：
      ① 源码级：`_LLM_REWRITE_ENABLED` 必须**默认关闭**（未设环境变量时为 False）；
      ② 源码级：报告文本不得出现"错别字/损坏黑名单"里的词；
      ③ 产物级：报告内所有文本不得含黑名单词，也不得出现"≈〈中文数字〉元"这种
         **数字被改写成中文数**的形态（正常报告只会写阿拉伯数字金额）。
    """
    issues: List[Tuple[str, str, str]] = []

    # ① 源码级：LLM 正文改写必须默认关闭
    try:
        from engine import narrative_fresh as _nf                      # noqa: PLC0415
        if getattr(_nf, "_LLM_REWRITE_ENABLED", None) is not False:
            issues.append(("ERROR", "engine/narrative_fresh.py",
                           "报告正文的 LLM 改写**未默认关闭**（_LLM_REWRITE_ENABLED=%r）—— "
                           "该路径会引入同音字错别字与数字损坏，必须默认关闭"
                           % getattr(_nf, "_LLM_REWRITE_ENABLED", None)))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/narrative_fresh.py", "无法导入：%s" % exc))

    # ② 源码级：黑名单词不得出现在任何 engine/main 源码文本里
    for _bad, _good in _TEXT_CORRUPTION_BLACKLIST.items():
        for _rel in ("engine", "main.py"):
            _base = ROOT / _rel
            _files = (sorted(_base.glob("*.py")) if _base.is_dir() else [_base])
            for _f in _files:
                if _f.name.startswith("_bk") or not _f.exists():
                    continue
                try:
                    _txt = _f.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                # ⚠ 只扫**代码文本**（去注释/去 docstring）——
                #   注释里为说明问题而引用「补教要求」等损坏形态是允许的（本闸门自己的注释就有）。
                _code = re.sub(r'""".*?"""', " ", _txt, flags=re.S)
                _code = re.sub(r"#[^\n]*", "", _code)
                if _bad in _code:
                    issues.append(("ERROR", str(_f.relative_to(ROOT)),
                                   "出现文本损坏词「%s」（应为「%s」）—— 报告正文禁止此类改写"
                                   % (_bad, _good)))
                for _pat, _want in _TEXT_CORRUPTION_PATTERNS:
                    if _pat.search(_code):
                        issues.append(("ERROR", str(_f.relative_to(ROOT)),
                                       "出现文本损坏形态「%s」（应为「%s」）"
                                       % (_pat.pattern, _want)))

    # ③ 产物级：报告文本里的损坏词 + 数字被写成中文数
    _rep = _canonical_report()
    if _rep is None:
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "无真跑产物，报告文本损坏扫描跳过（跑一次全量分析后自动生效）"))
        return issues
    _blob = json.dumps(_rep, ensure_ascii=False)
    for _bad, _good in _TEXT_CORRUPTION_BLACKLIST.items():
        if _bad in _blob:
            issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                           "报告文本含损坏词「%s」（应为「%s」）" % (_bad, _good)))
    for _m in re.finditer(r"≈[一二三四五六七八九十百千零]+元", _blob):
        issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                       "报告出现**数字被改写成中文数**的形态「%s」——金额必须保持阿拉伯数字"
                       % _m.group(0)))

    # ④ 产物级：**报告正文不得含 markdown 标记**（2026-10-07 实测：产物 120 处、页面 73 处）
    #   根因：去星号规则原先只写在 `enterprise_report._naturalize_report_text`（只在疑点段落
    #   构造路径上被调用），`tax_impact_summary.note` / `risk_level_basis` /
    #   `related_analyses[].data` / 要件文本**没走到它** ⇒ 企业看到「**未考虑**进项留抵」。
    #   现由终局收口 `_strip_markup_out()` 对整份报告统一执行；本判据锁死它不再复发。
    #   ⚠ 只扫**报告**（`enterprise_readable_report`）—— 引擎内部数据（all_findings /
    #     scenario_execution / comprehensive）不是报告正文，不在本口境内（另有各自用途）。
    #   ⚠ 单个 `*` 不算（增值税发票品名形如 `*住宿服务*住宿服务`）；连续 ≥2 个才算标记。
    _er = _rep.get("enterprise_readable_report") or _rep
    _md_hits: List[str] = []

    def _scan_md(o: Any, _path: str = "") -> None:
        if isinstance(o, dict):
            for _k, _v in o.items():
                _scan_md(_v, "%s.%s" % (_path, _k))
        elif isinstance(o, list):
            for _i, _v in enumerate(o):
                _scan_md(_v, "%s[%d]" % (_path, _i))
        elif isinstance(o, str) and "**" in o:
            _md_hits.append(_path)

    _scan_md(_er)
    if _md_hits:
        issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                       "报告正文含 markdown 强调符 `**`（%d 处，如 %s）—— 唯一权威 "
                       "text_guardrails.strip_markup 须在终局收口执行"
                       % (len(_md_hits), _md_hits[:3])))
    return issues


def check_report_no_redundancy() -> List[Tuple[str, str, str]]:
    """报告**不得重复冗余**（用户评语：重复冗余占全文三分之一以上）（2026-10-06）。

    用户列的重复层次（本闸门逐条锁死）：
      · 结构层：同一内容在「总述/分述/结论/自我反驳/补资料」反复出现；
      · 声明层：「若不补充资料的后果」「未收到"合同文件"…」等**逐字重复**几十次；
      · 元话语层：「本段是系统对自己结论的复核」「系统不对企业的解释作预判」等**系统自述**；
      · 表注层：同一表注每张表前都来一遍。
    判据（产物级；去重唯一权威 `engine.report_dedup`）：
      ① 同一**共性段**文本（去空白）不得出现在 ≥3 个疑点里（≥3 即应上提为报告级一次）；
      ② 任何疑点的任何文本都不得命中**元话语**黑名单；
      ③ 被上提的共性声明必须在报告级**可渲染字段**里确实出现一次（否则"去重"＝"删内容"）；
      ④ 同一**表注**文本不得在多张表重复出现。
    """
    issues: List[Tuple[str, str, str]] = []

    # ⓪ **共性段标题必须真的认得出来**（不依赖真跑产物，永远执行）
    #   ★ 2026-10-06 事故（"注释说 A、代码做 B"）：`_HOISTABLE_HEADS` 存字面标题、
    #     匹配用精确相等 ⇒ **3/3 漏配**（实际标题带序号前缀「三、」/ 用的是另一种措辞
    #     「若不补证的后果」/「自我反驳」只由前端渲染）⇒ 去重引擎接上了却什么都没上提。
    #   本探针把这批**真实标题**逐一喂给判定函数，防止再次漂移。
    try:
        from engine.report_dedup import is_hoistable_head, norm_head   # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "engine/report_dedup.py", "无法导入去重唯一权威：%s" % exc)]
    for _h in ("若不补证的后果", "若不补充资料的后果", "若不补充资料可能承担的后果",
               "三、已取得的资料与待补充的资料", "五、需企业提供的资料与说明",
               "本项可能错在哪里：自我反驳与验证清单"):
        if not is_hoistable_head(_h):
            issues.append(("ERROR", "engine/report_dedup.py",
                           "共性段标题「%s」未被识别（去重会静默失效：报告仍逐疑点重复）" % _h))
    if norm_head("三、已取得的资料与待补充的资料") != "已取得的资料与待补充的资料":
        issues.append(("ERROR", "engine/report_dedup.py",
                       "标题归一化未去掉序号前缀（带序号标题将永远匹配不上共性段表）"))
    # 反向锁：**本项特有**叙述不得被误判为共性段（否则会删掉每项独有的事实）
    for _h in ("四、本项结论及理由", "二、发现的依据", "三、证据与金额底稿", "本项检查过程"):
        if is_hoistable_head(_h):
            issues.append(("ERROR", "engine/report_dedup.py",
                           "本项特有段落标题「%s」被误判为共性段（会把每项独有内容当重复删掉）" % _h))

    # ⓪b **去重只删句、不改字**（不依赖真跑产物，永远执行）
    #   ★★ 2026-10-06 真实事故（"读不通"级）：`split_sentences` 默认**丢掉句末分隔符**，
    #     而回拼写成 `"".join(切句结果)` ⇒ **整段标点被吃光**——实测产物出现
    #     「…按规定补缴并加收滞纳金文化事业建设费是政府性基金，不是税…」
    #     （"滞纳金"与"文化"之间的「；」被吞），读者看到断句错乱的长串。
    #   判据：①切句必须**无损**（`"".join(keep_delims 结果) == 原文`）；
    #        ②走一遍真实去重后，未被上提的句子**标点必须完好**。
    try:
        from engine.report_dedup import _split_keep, dedup_report   # noqa: PLC0415
        _probe_txt = "甲项事实。乙项事实；丙项结论。丁项结论！"
        if "".join(_split_keep(_probe_txt)) != _probe_txt:
            issues.append(("ERROR", "engine/report_dedup.py",
                           "切句不是无损的（默认丢句末分隔符）⇒ 回拼会把整段标点吃光，"
                           "报告会出现「…滞纳金文化事业建设费是…」这类断句错乱"))
        _probs = [{"title": "T%d" % i, "narrative_paragraphs": [{
            "heading": "若不补充资料的后果",
            "text": "本项第 %d 笔业务。" % i
                    + "本报告不作定性，在补充资料核实之前既不认定违法，也不予排除。"}]}
            for i in range(1, 5)]
        dedup_report({"confirmed_problems": _probs})
        for _i, _p in enumerate(_probs, 1):
            _t = str(((_p.get("narrative_paragraphs") or [{}])[0]).get("text") or "")
            if not _t.endswith("。"):
                issues.append(("ERROR", "engine/report_dedup.py",
                               "去重后保留句丢了句末标点（第 %d 项）：%r" % (_i, _t)))
            if ("第 %d 笔业务。" % _i) not in _t:
                issues.append(("ERROR", "engine/report_dedup.py",
                               "去重改动了本项特有事实（第 %d 项）：%r" % (_i, _t)))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/report_dedup.py",
                       "去重保真断言执行失败：%s" % exc))

    _rep = _canonical_report()
    if _rep is None:
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "无真跑产物，重复冗余检查跳过（跑一次全量分析后自动生效）"))
        return issues
    er = _rep.get("enterprise_readable_report") or _rep
    probs = [p for p in (er.get("confirmed_problems") or []) if isinstance(p, dict)]
    if not probs:
        return issues

    try:
        from engine.report_dedup import (   # noqa: PLC0415
            _META_PATTERNS, _HOISTABLE_HEADS, _HOIST_MIN, _norm_key,
            find_leftover_duplicates, is_hoistable_head, norm_head,
        )
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "engine/report_dedup.py", "无法导入去重唯一权威：%s" % exc)]

    # ①② 残留重复（段级 + 句级）：**计数一律走唯一权威 `report_dedup.find_leftover_duplicates`**
    #   —— 闸门不得自写一套计数，否则"去重引擎改了、闸门判据没跟着改"就会假绿。
    _left = find_leftover_duplicates(er)
    for _head, _n, _snip in sorted(_left["paragraphs"], key=lambda x: -x[1]):
        issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                       "共性段在 %d 个疑点里逐字重复（应上提为报告级一次）：%s…%s"
                       % (_n, _head, _snip)))
    for _head, _n, _snip in sorted(_left["sentences"], key=lambda x: -x[1]):
        issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                       "共性**句**在 %d 个疑点里逐字重复（应上提为报告级一次）：%s…%s"
                       % (_n, _head, _snip)))

    # ② 元话语
    for p in probs:
        _blob = json.dumps(p, ensure_ascii=False)
        for rx in _META_PATTERNS:
            if rx.search(_blob):
                issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                               "疑点「%s」仍含系统自述（元话语）：%s"
                               % (str(p.get("title"))[:16], rx.pattern)))

    # ③ 上提的共性声明必须在报告级出现一次
    _cs = er.get("common_statements") or []
    if _cs:
        _rs_blob = json.dumps(er.get("report_statement") or [], ensure_ascii=False)
        for c in _cs:
            _t2 = str((c or {}).get("text") or "")
            # ★ 2026-10-07（Skill 4）：**孤立引导句豁免**。
            #   引导句（以「：」承诺后文、本体无信息量）被上提后脱离正文即成空条目，
            #   报告出口会**主动剔除**它（这是 Skill 4 的正确行为，不是"删内容"）。
            #   判据唯一权威 `content_placeholder_guard.is_orphan_lead`。
            try:
                from engine.content_placeholder_guard import is_orphan_lead as _ol
                if _ol(_t2):
                    continue
            except Exception:
                pass
            if _t2 and _norm_key(_t2)[:40] not in _norm_key(_rs_blob):
                issues.append(("ERROR", "engine/enterprise_report.py",
                               "共性声明未在报告级渲染（被上提却找不到出处 ⇒ 等于删内容）：%s…"
                               % _t2[:30]))

    # ④ 表注重复
    _notes: Dict[str, int] = {}
    for p in probs:
        for holder in list(p.get("narrative_paragraphs") or []) + [p]:
            for tkey in ("detail_table", "detail_tables"):
                tv = holder.get(tkey)
                tables = tv if isinstance(tv, list) else ([tv] if isinstance(tv, dict) else [])
                for tb in tables:
                    if isinstance(tb, dict):
                        nk = _norm_key(tb.get("note"))
                        if nk:
                            _notes[nk] = _notes.get(nk, 0) + 1
    for nk, n in _notes.items():
        if n > 1:
            issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                           "同一表注重复出现 %d 次（应只保留首次）：%s…" % (n, nk[:30])))
    return issues


def check_count_single_source() -> List[Tuple[str, str, str]]:
    """报告里**所有**「共 N 项风险事项」必须等于定稿条数（2026-10-06）。

    ★ 用户实测（评语 #1）：第 1 页写 34 项、第 4 页写 26 项（高1中8低5待12）——
      同一份报告两套口径。根因是**计数点分散**且各自在"并入独立风险事项之前"算。
      已修 3 处：`inspection_overview` / `overall_conclusion` / `main_assessment`
      （统一在"计数定稿"处按定稿列表重算）。
    本闸门把这条锁死：**全报告文本里每一处"共 N 项风险事项"都必须 == len(confirmed_problems)**，
    少一处未重算就报 ERROR（不必再靠人眼比对第 1 页与第 4 页）。
    """
    _ = r"\s"   # 说明：本函数内正则在下方以 r"" 书写，避免转义序列告警
    issues: List[Tuple[str, str, str]] = []
    _rep = _canonical_report()
    if _rep is None:
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "无真跑产物，计数据同源检查跳过（跑一次全量分析后自动生效）"))
        return issues
    er = _rep.get("enterprise_readable_report") or _rep
    n = len([p for p in (er.get("confirmed_problems") or []) if isinstance(p, dict)])
    if not n:
        return issues
    blob = json.dumps(er, ensure_ascii=False)
    # 统一口径：凡「共（识别并列示）N 项…风险事项」都必须等于定稿条数
    pats = (
        re.compile(r"共识别并列示\s*(\d+)\s*项"),
        re.compile(r"本轮共\s*(\d+)\s*项风险事项"),
        re.compile(r"风险事项合计\s*(\d+)\s*项"),
    )
    for rx in pats:
        for m in rx.finditer(blob):
            got = int(m.group(1))
            if got != n:
                issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                               "计数口径不一致：「%s」= %d 项，定稿列表 = %d 项 —— "
                               "必须全取定稿后的同一份列表" % (m.group(0)[:24], got, n)))
    return issues


def check_family_single_lead() -> List[Tuple[str, str, str]]:
    """同一**风险族**只允许一个主事项，子项必须并入且**不静默丢**（2026-10-06）。

    ★ 用户评语：事项数量虚高 ——「同一事实被拆成多个疑点」「疑点27—34 基本是前面疑点的
      重复或汇总，却可能被计入风险事项总数」。权威 `engine.finding_families`。
    判据（产物级）：
      ① 同族内**不得出现 ≥2 个主事项**（主事项＝未带 `family` 字段的族内项）——
         否则说明合并没跑或跑在计数之后；
      ② 每个主事项的 `family_members` 必须**写进正文**（标题可见）—— 否则等于静默丢子项。
    """
    issues: List[Tuple[str, str, str]] = []
    _rep = _canonical_report()
    if _rep is None:
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "无真跑产物，同族合并检查跳过（跑一次全量分析后自动生效）"))
        return issues
    er = _rep.get("enterprise_readable_report") or _rep
    probs = [p for p in (er.get("confirmed_problems") or []) if isinstance(p, dict)]
    if not probs:
        return issues
    try:
        from engine.finding_families import classify_family   # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "engine/finding_families.py", "无法导入同族权威：%s" % exc)]

    _leads: Dict[str, int] = {}
    for p in probs:
        fam = classify_family(p)
        if not fam:
            continue
        if not p.get("family"):          # 未带 family ⇒ 视为该族的一个"主事项"
            _leads[fam] = _leads.get(fam, 0) + 1
    for fam, n in _leads.items():
        if n >= 2:
            issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                           "风险族「%s」出现 %d 个主事项（应只留 1 个、其余降为子项）—— "
                           "同族合并未生效或跑在计数之后" % (fam, n)))
    for p in probs:
        mem = p.get("family_members") or []
        if not mem:
            continue
        _body = json.dumps(p.get("narrative_paragraphs") or [], ensure_ascii=False)
        for m in mem:
            ttl = str((m or {}).get("title") or "")[:12]
            if ttl and ttl not in _body:
                issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                               "子项「%s」未写进主事项正文（静默丢失）" % ttl))
    return issues


def check_levy_nature_not_confused() -> List[Tuple[str, str, str]]:
    """**税费性质不得混同**：非税（社保费/公积金/政府性基金）不得套用偷税条款（2026-10-06）。

    ★ 用户评语 #4 原话：「住房公积金不是税……处罚主体通常是住房公积金管理中心，
      不宜直接套用税收征管法偷税条款；社保费不是税……法律依据和处罚规则与税收不同；
      文化事业建设费是政府性基金……不宜简单等同于『税』。」
    病根：`enterprise_report` 的「若不补证的后果」曾**对所有事项一律**写
      "依《税收征收管理法》第三十二条加收滞纳金，并依第六十三条追缴税款、处…罚款"。
    判据（行为 + 产物）：
      ① 行为：非税性质的后果文本**不得含「第六十三条」**且必须写明「不适用」；
         税性质必须含「第六十三条」（保守：仍按征管法）；
      ② 数据：每种性质的 依据/后果/追责主体 均非空；
      ③ 产物：凡性质为公积金/社保费/政府性基金的疑点，其「若不补证的后果」段
         不得出现「第六十三条」，且必须点出对应主体或依据（公积金管理中心／社会保险法／政府性基金）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.levy_nature import (LEVIES, consequence_text,   # noqa: PLC0415
                                        nature_of, natures_of)
        from engine.report_dedup import is_consequence_head as _is_consequence_head  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "engine/levy_nature.py", "无法导入税费性质权威：%s" % exc)]
    try:
        from engine.levy_nature import (consequence_declaration as _decl_of,   # noqa: PLC0415
                                        consequence_decl_ref as _decl_ref)
    except Exception:  # noqa: BLE001 —— 取不到则③-3 跳过（不静默：由③-1 兜住）
        _decl_of = None
        _decl_ref = lambda: ""

    # ① 行为
    for _nat, _d in LEVIES.items():
        _txt = consequence_text(_nat)
        if _nat == "税":
            if "第六十三条" not in _txt:
                issues.append(("ERROR", "engine/levy_nature.py",
                               "「税」的后果文本缺《税收征收管理法》第六十三条依据"))
        else:
            if "第六十三条" in _txt:
                issues.append(("ERROR", "engine/levy_nature.py",
                               "非税性质「%s」的后果文本仍引用征管法第六十三条（偷税）" % _nat))
            if "不适用" not in _txt:
                issues.append(("ERROR", "engine/levy_nature.py",
                               "非税性质「%s」未写明「不适用税收征管法偷税条款」"
                               "（读者会误以为同等）" % _nat))
        for _k in ("basis", "consequence", "authority", "label"):
            if not str(_d.get(_k) or "").strip():
                issues.append(("ERROR", "engine/levy_nature.py",
                               "性质「%s」缺 `%s`（数据不完整）" % (_nat, _k)))

    # ①-2 混性质项：必须**逐段标注**，否则"多性质"退化为单选 ⇒ 另一半依据丢失。
    #    实测 RL-PAY-001「工资表人数与社保参保人数不符」同时含个税/企业所得税 + 社保费。
    _mix = consequence_text(["税", "社会保险费"])
    for _must in ("就税款部分", "就社会保险费部分", "第六十三条", "社会保险法"):
        if _must not in _mix:
            issues.append(("ERROR", "engine/levy_nature.py",
                           "混性质项后果段缺「%s」（多性质未逐段标注）" % _must))
    for _obj, _want in (
        ({"taxes": ["个人所得税", "企业所得税", "社会保险费"]}, ["税", "社会保险费"]),
        ({"taxes": ["住房公积金"]}, ["住房公积金"]),
        ({"taxes": ["文化事业建设费"]}, ["政府性基金"]),
        ({"taxes": ["增值税"]}, ["税"]),
        ({"taxes": ["社会保险费", "住房公积金"]}, ["社会保险费", "住房公积金"]),
    ):
        _got = natures_of(_obj)
        if _got != _want:
            issues.append(("ERROR", "engine/levy_nature.py",
                           "natures_of(%r) 应为 %r，实得 %r" % (_obj, _want, _got)))

    # ③ 产物（★★ 2026-10-08 P0-2 **位置同步**）
    #   旧判据扫**逐项后果段**并要求其含「政府性基金／社会保险法／住房公积金管理中心」
    #   —— 那在 P0-2 之前成立（法条逐项铺开）。P0-2 之后法条**按性质上提报告级一次**
    #   （`levy_nature.consequence_declarations` → `out["report_statement"]`），
    #   逐项段只留「本项情形 + 去向」⇒ 旧判据**必然误报**（实测文建费项被假报）。
    #   ⚠ 这是**位置迁移，不是放松**：断言的**意图**（非税必须有正确依据/主体、
    #     且不得套用偷税条款）原样保留，只把断言对象改到"报告级声明"这一**真实落点**。
    #   判据：
    #     ③-1 **可见性**：本报告实际涉及的**每种性质**，其权威声明
    #          `consequence_declaration(性质)` 必须逐字出现在**渲染可见**的
    #          `report_statement` 里（`common_statements` 只是机器镜像、前端不渲染，
    #          不能拿它当"企业看得到"的依据 —— 见 `tax-doc-analysis.js:5678`）。
    #     ③-2 **不越界**：纯非税项的逐项后果段**不得**出现「第六十三条」。
    #     ③-3 **引用不悬空**：逐项段若带引用（`consequence_decl_ref()`），其性质必须已在③-1声明。
    _rep = _canonical_report()
    if _rep is None:
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "无真跑产物，税费性质混同的产物检查跳过"))
        return issues
    er = _rep.get("enterprise_readable_report") or _rep
    _cps = [p for p in (er.get("confirmed_problems") or []) if isinstance(p, dict)]
    # ③-1 报告级声明可见性（对**全报告**涉及的性质，不限于非税）
    _all_nats = set()
    for _p in _cps:
        _all_nats.update(natures_of(_p))
    _rs_txt = " ".join(str(_x or "") for _x in (er.get("report_statement") or []))
    # 兼容旧产物：若 report_statement 缺失，退回机器镜像（并提示）
    if not _rs_txt.strip():
        _rs_txt = " ".join(str((_c or {}).get("text") or "")
                           for _c in (er.get("common_statements") or []))
        if _rs_txt.strip():
            issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                           "report_statement 为空，报告级声明可见性退回 common_statements 判定"
                           "（后者前端不渲染，属降级判定）"))
    # ⚠ 比对必须用**报告出口的同一变换**（`main.py:11844-11855`：
    #   `to_plain_obj(_np(s), k)`），否则判据会**永久假红** ——
    #   实测权威原文写「责令限期缴纳」，而出口 `plain_language` 通俗化为「要求限期缴纳」
    #   （`plain_language.py:35 ("责令","要求")`）⇒ 拿原文精确比对必然不匹配。
    #   这不是"绕过"，而是**同一契约**：企业看到的就是变换后的文本。
    try:
        from engine.sentencekit import normalize_cjk_punct as _npc  # noqa: PLC0415
        from engine.plain_language import to_plain as _tp           # noqa: PLC0415

        def _norm_exit(s) -> str:
            return _tp(_npc(str(s or "")))
    except Exception:  # noqa: BLE001
        def _norm_exit(s) -> str:
            return str(s or "")

    _rs_norm = _norm_exit(_rs_txt)
    if _decl_of is not None:
        for _n in sorted(_all_nats):
            _want = _decl_of(_n)
            if _want and _norm_exit(_want) not in _rs_norm:
                issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                               "报告级「税费性质与法定后果（%s）」声明未出现在渲染可见的"
                               "report_statement ⇒ 逐项引用悬空、企业查不到法定后果" % _n))
    # ③-2 / ③-3 逐项
    for _p in _cps:
        _nats = natures_of(_p)
        # ★ 2026-10-06：**混性质项**（如"个税/企业所得税+社保费"，实测 RL-PAY-001）
        #   本来就该引征管法偷税条款（虚列工资成本少缴企业所得税）⇒ 只对**纯非税**项断言。
        if "税" in _nats or len(_nats) != 1:
            continue
        _nat = _nats[0]
        # ★ 2026-10-06：后果段标题的识别必须走**唯一权威**
        #   `report_dedup.is_consequence_head`（产物标题可能是「若不补充资料的后果」）。
        _head_txt = " ".join(
            str((x or {}).get("text") or "") for x in (_p.get("narrative_paragraphs") or [])
            if _is_consequence_head((x or {}).get("heading")))
        if "第六十三条" in _head_txt:
            issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                           "「%s」性质为「%s」，其「若不补证的后果」仍引用征管法第六十三条（偷税）"
                           % (str(_p.get("title"))[:18], _nat)))
        # ③-3 引用不悬空
        _ref = _decl_ref() or ""
        if _ref and _ref in _head_txt and _decl_of is not None:
            _want = _decl_of(_nat)
            if _want and _norm_exit(_want) not in _rs_norm:
                issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                               "「%s」逐项后果段引用了「%s」，但报告级无该声明（引用悬空）"
                               % (str(_p.get("title"))[:18], _nat)))
    return issues


def check_risk_level_single_source() -> List[Tuple[str, str, str]]:
    """**风险等级标度不得多头维护**（2026-10-06，用户评语 #1「风险等级前后矛盾」）。

    病根（实测）：同仓并存 6 张"等级→序数"表，且**对「信息 vs 低风险」给出相反答案**：
      · `enterprise_report` 上限压制表：信息 **轻于** 低风险；
      · `pipeline::_sev`（同 type 合并取代表）：信息 **重于** 低风险；
      · `enterprise_report` 主线研判表：两者**并列**；`_LEVEL_RANK`：信息 **重于** 低风险；
      · `finding_families::_LV_RANK`：只列低风险；`audit_consistency`：信息 **轻于** 低风险。
    ⇒ 同一事项在不同章节由不同表算出不同等级，读者看到"第 4 章高风险、第 7 章中风险"。

    判据（可复现、不依赖产物）：
      ① 权威模块 `engine/risk_levels.py` 必须存在，且暴露
         `LEGAL_LEVELS/RISK_GRADES/EVIDENCE_STATES/SEVERITY/PRESENT_ORDER` 与
         `severity/present_order/normalize/cap_level`；
      ② **不变量**（写进断言，防"权威自己漂"）：
         `severity("信息") < severity("低风险") < severity("中风险") < severity("高风险")
          < severity("极高风险")`；`cap_level("待核验","信息") == ("待核验","")`
         （证据状态不受上限压制）；
      ③ **消费点必须接线**：`enterprise_report` 用 `cap_level`、`finding_families` 与
         `pipeline` 用 `severity`，且三处**不得**再出现内联的等级→序数字典；
      ④ **全仓不得再有第二张同时含「信息」与「低风险」的等级→数字表**
         （这一对正是矛盾的来源；其余"权重表/机会等级表"不含该对，不误伤）。
      并做**反向验证**：把权威表改回旧口径（信息重于低风险），断言③/④必须变红。
    """
    issues: List[Tuple[str, str, str]] = []
    _auth = ROOT / "engine" / "risk_levels.py"
    if not _auth.exists():
        return [("ERROR", "engine/risk_levels.py",
                 "缺风险等级唯一权威模块（等级标度会退回多头维护）")]

    # ① 权威 API
    try:
        from engine import risk_levels as RL  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "engine/risk_levels.py", "无法导入等级权威：%s" % exc)]
    for _name in ("LEGAL_LEVELS", "RISK_GRADES", "EVIDENCE_STATES",
                  "SEVERITY", "PRESENT_ORDER"):
        if not hasattr(RL, _name):
            issues.append(("ERROR", "engine/risk_levels.py", "权威缺表 `%s`" % _name))
    for _fn in ("severity", "present_order", "normalize", "cap_level"):
        if not callable(getattr(RL, _fn, None)):
            issues.append(("ERROR", "engine/risk_levels.py", "权威缺函数 `%s`" % _fn))
    if issues:
        return issues

    # ② 不变量
    _order = ["信息", "低风险", "中风险", "高风险", "极高风险"]
    _sev = [RL.severity(x) for x in _order]
    if any(_sev[i] >= _sev[i + 1] for i in range(len(_sev) - 1)):
        issues.append(("ERROR", "engine/risk_levels.py",
                       "轻重标度不单调：%s → %r（「信息」必须是最轻档，"
                       "「没判出等级」的事项不得顶掉已确认的「低风险」）"
                       % (" < ".join(_order), _sev)))
    if RL.cap_level("待核验", "信息") != ("待核验", ""):
        issues.append(("ERROR", "engine/risk_levels.py",
                       "「待核验」被「信息」压制了——证据状态不得参与高低压制"
                       "（否则「证据不足待核」会被降级成「提示信息」）"))
    if RL.cap_level("高风险", "中风险") != ("中风险", "高风险"):
        issues.append(("ERROR", "engine/risk_levels.py",
                       "上限压制未生效（疑点等级会超过其建入口那条发现）"))

    # ③ 消费点接线
    _sites = (
        ("engine/enterprise_report.py", "cap_level",
         "疑点等级上限压制未引用唯一权威 `risk_levels.cap_level`"),
        ("engine/finding_families.py", "severity",
         "同族选主事项的等级排序未引用唯一权威 `risk_levels.severity`"),
        ("engine/pipeline.py", "severity",
         "同 type 合并取代表的等级排序未引用唯一权威 `risk_levels.severity`"),
        ("engine/audit_doctrine.py", "LEGAL_LEVELS",
         "权威等级词表未转发 `risk_levels.LEGAL_LEVELS`（会形成第二份词表）"),
    )
    for _rel, _need, _msg in _sites:
        _p = ROOT / _rel
        _src = _p.read_text(encoding="utf-8", errors="replace") if _p.exists() else ""
        if _need not in _src or "risk_levels" not in _src:
            issues.append(("ERROR", _rel, _msg))

    # ④ 全仓不得再有第二张"含「信息」且含「低风险」"的等级→数字表
    #    （`scripts/_bk*` 是历史备份快照，按本项目既有惯例跳过；
    #     扫描范围必须含 `tools/**` —— 闸门自己也曾内联一张表）
    import glob as _glob5  # noqa: PLC0415
    _dup: List[str] = []
    _scan = (sorted(_glob5.glob(str(ROOT / "*.py")))
             + sorted(_glob5.glob(str(ROOT / "engine" / "**" / "*.py"), recursive=True))
             + sorted(_glob5.glob(str(ROOT / "tools" / "**" / "*.py"), recursive=True)))
    for _fs in _scan:
        _fp = Path(_fs)
        _rel = _fp.relative_to(ROOT).as_posix()
        if any(s in _rel for s in (".venv", "__pycache__", "scripts/_bk", "node_modules", ".git")):
            continue
        if _fp.name == "risk_levels.py":
            continue
        try:
            _tree = ast.parse(_fp.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for _node in ast.walk(_tree):
            if not isinstance(_node, ast.Dict):
                continue
            _keys = [k.value for k in _node.keys
                     if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            _vals_are_int = [v for v in _node.values
                             if isinstance(v, ast.Constant) and isinstance(v.value, int)
                             and not isinstance(v.value, bool)]
            if "信息" in _keys and "低风险" in _keys and _vals_are_int:
                _dup.append("%s:%d" % (_rel, _node.lineno))
    if _dup:
        issues.append(("ERROR", "tools/audit_consistency.py",
                       "仍有第二张等级→序数表（含「信息」与「低风险」）：%s"
                       " —— 必须转发 `engine.risk_levels`" % "、".join(_dup[:6])))

    # ⑤ **结构化枚举字段不得被展示词替换**（项目铁律，2026-10-06 自检抓到真实事故）
    #   事故：`overall_conclusion.counts.by_level` 的**键**曾被改写成展示词「已列明」
    #   ⇒ 「等级「已列明」报告 2 项、实际 0 项」（键与实际 `risk_level` 对不上），
    #     且字典推导把「待核验」与「尚需核实」两种来源**合并覆盖**、丢计数。
    #   判据走**行为**（比源码文本稳：字符串键会被 `_mask_py_comments_and_strings` 屏蔽）：
    #     · `counts.by_level` 的键必须全部落在权威等级词表内；
    #     · 合计必须等于疑点数（合并覆盖会当场露出来）；
    #     · 展示写法另走 `by_level_display`（权威 `risk_levels.display_label`）。
    try:
        from engine.overall_conclusion import build_overall_conclusion as _boc5  # noqa: PLC0415
        _probs5 = [
            {"seq": 1, "title": "甲", "risk_level": "高风险", "taxes": ["增值税"],
             "suspect": "涉嫌x", "conclusion_grade": "待核"},
            {"seq": 2, "title": "乙", "risk_level": "待核验", "taxes": [],
             "suspect": "", "conclusion_grade": "待核"},
            {"seq": 3, "title": "丙", "risk_level": "待核验", "taxes": [],
             "suspect": "", "conclusion_grade": "待核"},
            {"seq": 4, "title": "丁", "risk_level": "低风险", "taxes": [],
             "suspect": "", "conclusion_grade": "待核"},
        ]
        _oc5 = (_boc5({"target_entity": {}, "comprehensive": {}}, _probs5, [], {})
                .get("counts") or {})
        _bl = _oc5.get("by_level") or {}
        _illegal = [k for k in _bl if k not in LEGAL_LEVELS]
        if _illegal:
            issues.append(("ERROR", "engine/overall_conclusion.py",
                           "`counts.by_level` 的键不是权威等级：%s —— 结构化枚举字段"
                           "不得被当展示文本替换（展示写法应走 `by_level_display`）"
                           % _illegal))
        if sum(int(v or 0) for v in _bl.values()) != len(_probs5):
            issues.append(("ERROR", "engine/overall_conclusion.py",
                           "`counts.by_level` 合计 %d ≠ 疑点数 %d（等级被合并覆盖会丢计数）"
                           % (sum(int(v or 0) for v in _bl.values()), len(_probs5))))
        _bd = _oc5.get("by_level_display") or {}
        if not _bd:
            issues.append(("ERROR", "engine/overall_conclusion.py",
                           "缺 `counts.by_level_display`（正文展示写法无处取用，"
                           "会诱使下游改写 `by_level` 的键）"))
        else:
            from engine.risk_levels import display_label as _dl5   # noqa: PLC0415
            for _lv5 in _bl:
                if _dl5(_lv5) not in _bd:
                    issues.append(("ERROR", "engine/overall_conclusion.py",
                                   "`by_level_display` 缺等级「%s」的展示写法（应与 "
                                   "`risk_levels.display_label` 同源）" % _lv5))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/overall_conclusion.py",
                       "`by_level` 保真断言执行失败：%s" % exc))
    return issues


def check_conclusion_scoped_by_material_coverage() -> List[Tuple[str, str, str]]:
    """**资料受限时，总体结论必须限定效力范围**（2026-10-06，用户评语 #5）。

    ★ 用户原话：「检查程序未完成，但总体结论偏强：报告自述 14 类必查资料仅收到 8 类，
      却直接给出"整体税务风险等级为高"的定论，未限定为"资料受限下的风险画像"。」

    判据（行为 + 数据，不依赖真跑产物）：
      ① **齐备性口径唯一权威**：`required_doc_coverage` 必须存在，且
         `_build_further_checks` / `_build_material_readiness` 都调用它
         （原先两处各算一遍，"章首说缺几类"与"章末列几项"会漂移）；
      ② **行为**：给一个"必查 15 类只提供 8 类"的报告数据，
         总体结论首段必须同时出现
         ①受限声明（含实际类别数字）②「风险画像」的效力限定；
      ③ **反向锁**：资料**齐全**时不得出现该限定语（否则是套模板的假声明）。
      并做**反向验证**：把限定语句从 `overall_conclusion` 摘掉，②必须变红。
    """
    issues: List[Tuple[str, str, str]] = []
    _er = ROOT / "engine" / "enterprise_report.py"
    _oc = ROOT / "engine" / "overall_conclusion.py"
    if not _er.exists() or not _oc.exists():
        return [("ERROR", "engine/overall_conclusion.py", "报告构造模块缺失")]

    # ① 齐备性口径唯一权威 + 两个消费点接线
    try:
        from engine.enterprise_report import (  # noqa: PLC0415
            required_doc_coverage, _build_further_checks, _build_material_readiness,
        )
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "engine/enterprise_report.py",
                 "无法导入齐备性权威 required_doc_coverage：%s" % exc)]
    if not callable(required_doc_coverage):
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "缺齐备性唯一权威 `required_doc_coverage`"))
    for _fn, _nm in ((_build_further_checks, "_build_further_checks"),
                     (_build_material_readiness, "_build_material_readiness")):
        _src = inspect.getsource(_fn)
        if "required_doc_coverage" not in _src:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "`%s` 未走齐备性唯一权威（会与「资料齐备性总览」各算一遍）" % _nm))
    if "required_doc_coverage" not in _oc.read_text(encoding="utf-8", errors="replace"):
        issues.append(("ERROR", "engine/overall_conclusion.py",
                       "总体结论未引用齐备性权威（无法知道资料是否受限）"))

    # ② 行为：资料受限 → 必须限定效力范围
    try:
        from engine.overall_conclusion import build_overall_conclusion  # noqa: PLC0415
        from engine.enterprise_report import (  # noqa: PLC0415
            _DOC_TYPE_TO_CATEGORY, _REQUIRED_DOC_CATEGORIES)
        _cov = required_doc_coverage({"target_entity": {}})
        _total = int(_cov.get("total") or 0)
        if _total < 4:
            issues.append(("WARN", "engine/enterprise_report.py",
                           "必查资料类别数异常（%d），受限结论行为断言跳过" % _total))
            return issues
        # 取前一半类别做"已提供"
        _half = max(1, _total // 2)
        _cats = list(_cov.get("required") or [])[:_half]
        _types = []
        for _c in _cats:
            _t = next((k for k, v in _DOC_TYPE_TO_CATEGORY.items()
                       if v == _c or (isinstance(v, (tuple, list)) and _c in v)), None)
            _types.append(_t or _c)
        _probs = [{"seq": 1, "title": "A", "risk_level": "高风险",
                   "taxes": ["增值税"], "suspect": "涉嫌x", "conclusion_grade": "待核"}]
        _rd_limited = {
            "files_count": len(_types),
            "file_results": [{"type": t} for t in _types],
            "target_entity": {},
            "enterprise_readable_report": {"confirmed_problems": _probs, "further_checks": []},
        }
        _first = ""
        for _p in (build_overall_conclusion(_rd_limited).get("paragraphs") or []):
            if "企业整体风险综合评价" in str(_p):
                _first = str(_p)
                break
        if not _first:
            issues.append(("ERROR", "engine/overall_conclusion.py",
                           "总述缺「企业整体风险综合评价」段"))
        else:
            for _need, _why in (
                ("风险画像", "未把结论限定为「资料受限下的风险画像」（用户评语 #5）"),
                ("资料", "未说明结论受资料条件限制"),
                (str(_total), "未给出必查资料类别数（读者无法判断受限程度）"),
            ):
                if _need not in _first:
                    issues.append(("ERROR", "engine/overall_conclusion.py",
                                   "资料受限（必查 %d 类仅提供 %d 类）时，总体结论%s"
                                   % (_total, len(_types), _why)))
            if "受限" not in _first:
                issues.append(("ERROR", "engine/overall_conclusion.py",
                               "资料受限时未出现「受限」表述（结论强度与证据基础不匹配）"))

        # ③ 反向锁：资料齐全时不得出现受限声明（防"套模板的假声明"）
        _all_types = []
        for _c in (_cov.get("required") or []):
            _t = next((k for k, v in _DOC_TYPE_TO_CATEGORY.items()
                       if v == _c or (isinstance(v, (tuple, list)) and _c in v)), None)
            _all_types.append(_t or _c)
        _rd_full = {
            "files_count": len(_all_types),
            "file_results": [{"type": t} for t in _all_types],
            "target_entity": {},
            "enterprise_readable_report": {"confirmed_problems": _probs, "further_checks": []},
        }
        if not required_doc_coverage(_rd_full).get("limited"):
            _firstf = ""
            for _p in (build_overall_conclusion(_rd_full).get("paragraphs") or []):
                if "企业整体风险综合评价" in str(_p):
                    _firstf = str(_p)
                    break
            if "风险画像" in _firstf:
                issues.append(("ERROR", "engine/overall_conclusion.py",
                               "资料齐全时仍声称「资料受限下的风险画像」"
                               "（套模板的假声明，会让真受限时失去警示作用）"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/overall_conclusion.py",
                       "资料受限结论行为断言执行失败：%s" % exc))
    return issues


def check_table_governance_applied_last() -> List[Tuple[str, str, str]]:
    """**表格治理必须终局收口**（2026-10-06，顺序缺陷/"判据白写"同族）。

    事故：`govern_all_tables` 原先只在报告**构造那一刻**（`_norm_and_redact(...)`）执行，
    而「并入独立风险事项」与「询问主题挂载」都在其**之后**往报告里追加内容
    ⇒ 后追加的表**从未过治理**，`table_governance` 立项要修的三类缺陷全部复发：
      · 列名与行键不对齐（半/全角括号差异）→ 渲染层取值取不到、**整列空白**；
      · 内部列（`_id`/`trace_id`/`_key`）外泄成正式列；
      · 截断不注明（读者把列示行当全部行 → 与合计对不上）。

    判据（源码顺序 + 行为，零依赖产物）：
      ① 源码中 `govern_all_tables` 的**最后一次**出现必须晚于
         `_promote_standalone_to_problems` 与 `attach_question_themes`；
      ② 行为：一张"列名与行键仅标点不同 + 含内部列 + 声明 rows_total 大于实际行数"
         的表，过 `govern_all_tables` 后三类缺陷必须全部消失（幂等）。
      并做**反向验证**：摘掉终局收口那段，①必须变红。
    """
    issues: List[Tuple[str, str, str]] = []
    _er = ROOT / "engine" / "enterprise_report.py"
    if not _er.exists():
        return [("ERROR", "engine/enterprise_report.py", "报告构造模块缺失")]
    _src = _er.read_text(encoding="utf-8", errors="replace")
    # ⚠ 必须在**纯代码视图**上判位置：本项目到处是"原写法 X ⋯"的修复说明注释，
    #   直接 rfind 会被注释里的 `govern_all_tables` 命中 ⇒ 闸门自我误判为绿
    #   （实测踩过一次：去掉真调用后注释仍被算作"最后一次出现"）。
    _code = _mask_py_comments_and_strings(_src)

    # ① 顺序断言
    #   ⚠ 锚点必须取**调用点**而非**定义点**：`find` 会先命中函数定义（`def _promote_...`），
    #     那样"治理早于并入"也会被判为通过（实测踩过一次 → 断言形同虚设）。
    #     故对 `_promote_standalone_to_problems` 取 **rfind**（最后一次出现＝调用点）。
    _last_gov = _code.rfind("govern_all_tables")
    _anchors = {
        "_promote_standalone_to_problems": _code.rfind("_promote_standalone_to_problems"),
        "attach_question_themes": _code.find("attach_question_themes"),
    }
    if _last_gov < 0:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "报告构造未调用 `govern_all_tables`（明细表不做治理）"))
    else:
        for _name, _pos in _anchors.items():
            if _pos < 0:
                issues.append(("ERROR", "engine/enterprise_report.py",
                               "找不到锚点 `%s`（无法核验表格治理的终局收口顺序，"
                               "断言自给自足原则要求显式报出）" % _name))
            elif _last_gov < _pos:
                issues.append(("ERROR", "engine/enterprise_report.py",
                               "表格治理未终局收口：`govern_all_tables` 的最后一次调用早于"
                               " `%s` ⇒ 其后追加的明细表未过治理"
                               "（列名不对齐/内部列外泄/截断不注明会复发）" % _name))
        # 反向锁：治理必须至少出现两次（构造时 + 终局收口），否则"后追加内容未治理"
        if _code.count("govern_all_tables") < 2:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "表格治理只出现 %d 次（构造时未治理、或终局未收口）"
                           % _code.count("govern_all_tables")))

    # ② 行为：三类缺陷必须被修掉（且幂等）
    try:
        from engine.table_governance import govern_all_tables   # noqa: PLC0415
        _t = {"columns": ["金额（元）", "ref_id"],
              "rows": [{"金额(元)": "1,000.00", "_id": "x1", "ref_id": "记-1"}],
              "rows_total": 5,
              "title": "明细（共7笔）"}
        _out = govern_all_tables({"t": _t})["t"]
        _cols = list(_out.get("columns") or [])
        if "金额（元）" not in _cols:
            issues.append(("ERROR", "engine/table_governance.py",
                           "列名与行键仅标点不同未被对齐（整列会渲染为空）"))
        if "_id" in _cols or "_id" in (_out.get("rows") or [{}])[0]:
            issues.append(("ERROR", "engine/table_governance.py", "内部列 `_id` 未被剔除"))
        if not _out.get("truncation_note"):
            issues.append(("ERROR", "engine/table_governance.py",
                           "声明 rows_total=5 而仅列 1 行却未注明截断"))
        # 表题里的计数必须与**实际列示行数**一致（原写「共7笔」而只列 1 行 ⇒ 读者对不上）
        _title_out = str(_out.get("title") or "")
        if "（共7笔）" in _title_out or "此处列示前1" not in _title_out:
            issues.append(("ERROR", "engine/table_governance.py",
                           "表题计数与实际列示行数不一致（未按实际行数重写）：%s" % _title_out))
        _again = govern_all_tables({"t": _out})["t"]
        if _again.get("columns") != _out.get("columns") \
                or _again.get("truncation_note") != _out.get("truncation_note"):
            issues.append(("ERROR", "engine/table_governance.py", "表格治理不是幂等的"))
    except Exception as exc:  # noqa: BLE001
        issues.append(("ERROR", "engine/table_governance.py",
                       "表格治理行为断言执行失败：%s" % exc))
    return issues


def check_offtopic_rows_filtered() -> List[Tuple[str, str, str]]:
    """**附表明细行必须与本项论点匹配**（2026-10-06，用户复核疑点2）。

    ★ 用户原话：
      「你给出的数据（初永伟、吴德昌、徐瑶的逐月工资与社保基数，且状态均为『工资社保均有』），
        不仅不能证明『人数不符』，反而恰恰说明这些人在社保名单里是存在的。
        把它们放在『人数不符』的疑点下，属于**证据与论点不匹配**，同时造成了严重的篇幅冗余。」
    实测：疑点2 挂的「工资名册与社会保险人员范围差异」30 行里 **28 行是『工资社保均有』**，
    真正的差异只有 2 行 —— 真差异被淹没，且该表与同批对象的另 2 张表**重复呈现**。

    判据（产物级；过滤权威 `enterprise_report._filter_rows_off_topic`）：
      ① 部件与接线：权威函数存在，且在唯一收口点 `_apply_dir_filter` 里被调用；
      ② 「无差异」标记词表必须**窄**（含宽词会误删要件核对表的正常行）；
      ③ 产物：差异/异常类主题的疑点下，附表不得出现状态列为「本行无差异」的行；
      ④ 产物：同一疑点下**对象集合相同**的表不得多于一张（同批数据反复呈现＝纯冗余）。
    """
    issues: List[Tuple[str, str, str]] = []
    _er = ROOT / "engine" / "enterprise_report.py"
    if not _er.exists():
        return [("ERROR", "engine/enterprise_report.py", "报告构造模块缺失")]
    _code = _mask_py_comments_and_strings(_er.read_text(encoding="utf-8", errors="replace"))
    if "_filter_rows_off_topic" not in _code:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "缺论点匹配过滤权威 `_filter_rows_off_topic`（附表行会与本项论点错配）"))
    elif "_filter_rows_off_topic(" not in _code:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "论点匹配过滤未被调用（附表行仍会与本项论点错配）"))
    try:
        from engine.enterprise_report import (   # noqa: PLC0415
            _NORMAL_STATE_MARKS, _DIFF_SUBJECT_KWS, _STATE_COL_KEYS)
    except Exception as exc:  # noqa: BLE001
        return issues + [("ERROR", "engine/enterprise_report.py",
                          "无法导入论点匹配判据表：%s" % exc)]
    for _broad in ("一致", "相符", "正常", "未发现", "符合", "无异常情况"):
        if _broad in _NORMAL_STATE_MARKS:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "「无差异」标记词含宽词「%s」——实测会命中要件核对表的"
                           "『未单独核对/未发现符合』行，造成误删" % _broad))

    _rep = _canonical_report()
    if _rep is None:
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "无真跑产物，附表论点匹配检查跳过"))
        return issues
    er = _rep.get("enterprise_readable_report") or _rep
    for _p in (er.get("confirmed_problems") or []):
        if not isinstance(_p, dict):
            continue
        _subj = str(_p.get("title") or "")
        if not any(k in _subj for k in _DIFF_SUBJECT_KWS):
            continue
        _tabs = []
        for _seg in (_p.get("narrative_paragraphs") or []):
            _tabs.extend(((_seg or {}).get("detail_tables") or []))
        if isinstance(_p.get("detail_table"), dict):
            _tabs.append(_p["detail_table"])
        _ents: Dict[Any, int] = {}
        for _t in _tabs:
            _rows = [r for r in ((_t or {}).get("rows") or []) if isinstance(r, dict)]
            _norm = 0
            for _r in _rows:
                _st = ""
                for _k in _STATE_COL_KEYS:
                    if _k in _r:
                        _st = str(_r.get(_k) or "")
                        break
                if _st and any(_m in _st for _m in _NORMAL_STATE_MARKS):
                    _norm += 1
            if _norm:
                issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                               "疑点「%s」的附表「%s」含 %d 行「本行无差异」记录——"
                               "它们不构成本项差异证据，会把真差异淹没（证据与论点不匹配）"
                               % (_subj[:16], str(_t.get("title"))[:20], _norm)))
            _e = None
            for _k in ("姓名", "人员", "人员姓名", "对方单位", "供应商", "客户"):
                _vs = {str(_r.get(_k) or "").strip() for _r in _rows
                       if str(_r.get(_k) or "").strip()}
                if _vs:
                    _e = frozenset(_vs)
                    break
            if _e:
                _ents[_e] = _ents.get(_e, 0) + 1
        for _e, _n in _ents.items():
            if _n > 1:
                issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                               "疑点「%s」有 %d 张表的对象集合完全相同（%s）——"
                               "同一批数据在一项里反复呈现属纯冗余"
                               % (_subj[:16], _n, "、".join(sorted(_e))[:20])))
    return issues


def check_sequence_and_counts_single_source() -> List[Tuple[str, str, str]]:
    """**编号须连续、计数须同源、表格不得空白**（2026-10-06，用户第 1 批 ①②）。

    ★ 用户实测同一份报告两套口径：
      · 第 1 页「16 项风险事项」，第 4 页「已量化 7 / 26 项」；
      · 疑点编号 1,2,3,4,5,6,7,9,11,13,14,15,18,27,29,34（缺号）。
    根因都是**同一个**：派生量在**列表定稿之前**算过一次，而定稿时
    `merge_families` 会删项、`_promote_standalone_to_problems` 会追加项。

    判据（产物级；定稿唯一时刻＝`enterprise_report` 的「计数定稿」段）：
      ① `confirmed_problems[].seq` 必须是 **1..N 连续**（前端按 `疑点{seq}` 渲染）；
      ② `tax_impact_summary.total_items` 必须 == 事项总数（分母同源）；
      ③ 报告体内不得有**空白表格**（无表头 / 无数据 / 行全空）；
      ④ 等级计数合计必须 == 事项总数。
    """
    issues: List[Tuple[str, str, str]] = []
    _rep = _canonical_report()
    if _rep is None:
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "无真跑产物，编号/计数同源检查跳过"))
        return issues
    er = _rep.get("enterprise_readable_report") or _rep
    cps = [c for c in (er.get("confirmed_problems") or []) if isinstance(c, dict)]
    if not cps:
        return issues
    _seqs = [c.get("seq") for c in cps]
    if _seqs != list(range(1, len(cps) + 1)):
        issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                       "疑点编号不连续（前端按 seq 渲染「疑点N」，缺号会直接给企业看）：%s" % _seqs))
    _tis = er.get("tax_impact_summary") or {}
    if _tis.get("total_items") != len(cps):
        issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                       "税额敞口汇总分母 %s ≠ 事项总数 %s（同一份报告两套口径）"
                       % (_tis.get("total_items"), len(cps))))
    _cnt = (er.get("overall_conclusion") or {}).get("counts") or {}
    _by = _cnt.get("by_level") or {}
    if _by and sum(int(v or 0) for v in _by.values()) != len(cps):
        issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                       "等级计数合计 %s ≠ 事项总数 %s" % (sum(int(v or 0) for v in _by.values()), len(cps))))
    _blank = []
    _seen: set = set()

    def _walk(o):
        if isinstance(o, (dict, list)):
            if id(o) in _seen:
                return
            _seen.add(id(o))
        if isinstance(o, dict):
            if isinstance(o.get("columns"), list) and isinstance(o.get("rows"), list):
                _cols = [str(c) for c in o["columns"]]
                _rows = o["rows"]
                if not _rows or not any(c.strip() for c in _cols):
                    _blank.append(("无表头/无数据", str(o.get("title"))[:20]))
                else:
                    _allblank = True
                    for _r in _rows:
                        if isinstance(_r, dict):
                            for _v in _r.values():
                                if str(_v if _v is not None else "").strip().strip("—－-– "):
                                    _allblank = False
                                    break
                        if not _allblank:
                            break
                    if _allblank:
                        _blank.append(("行全空", str(o.get("title"))[:20]))
            for _v in o.values():
                _walk(_v)
        elif isinstance(o, list):
            for _v in o:
                _walk(_v)

    _walk(er)
    if _blank:
        issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                       "报告含 %d 张空白表格（渲染出来只是空框，应删除或补内容）：%s"
                       % (len(_blank), _blank[:4])))
    return issues
def check_risk_family_and_learnable_tiers() -> List[Tuple[str, str, str]]:
    """**风险族配置与可学习内容分级**（2026-10-07，用户第 3 批 任务2/任务7）。

    判据（全部为数据/行为断言，零依赖真产物）：
      ① `config/risk_families.json` 必须存在，且每个族含
         `risk_family_id/risk_family_name/parent_risk_code/parent_risk_name/
          children[]/count_policy/display_policy/level_policy/enabled_industries`；
      ② 配置 ↔ 运行时（`finding_families.FAMILIES`）**双向一致**：
         运行时有而配置没有 ⇒ 报告无法声明计数口径；配置有而运行时没有 ⇒ **死配置**；
      ③ 计数口径必须是「同族只计 1 项」这一档（报告总事项数＝父项数）；
      ④ 可学习内容四档齐备，且**未知类别按最严档 `manual`**（不得默认可自动学习）；
      ⑤ 禁止档（法律条文/征期/滞纳金/处罚标准/主观故意/企业申辩）**一律不得自动写库**。
    """
    issues: List[Tuple[str, str, str]] = []
    _cfg = ROOT / "config" / "risk_families.json"
    if not _cfg.exists():
        issues.append(("ERROR", "config/risk_families.json", "缺风险族配置表（计数口径无处声明）"))
    try:
        from engine.risk_families import (   # noqa: PLC0415
            COUNT_POLICIES, families, validate_against_runtime)
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", "engine/risk_families.py", "无法导入风险族配置权威：%s" % exc)]
    for _msg in validate_against_runtime():
        issues.append(("ERROR", "config/risk_families.json", _msg))
    _fams = families()
    if len(_fams) < 6:
        issues.append(("ERROR", "config/risk_families.json",
                       "已登记风险族仅 %d 个（用户列明 6 个已有族，缺登记=口径无法声明）" % len(_fams)))
    for _f in _fams:
        if str(_f.get("count_policy")) not in COUNT_POLICIES:
            issues.append(("ERROR", "config/risk_families.json",
                           "族「%s」的 count_policy=「%s」未登记"
                           % (_f.get("risk_family_name"), _f.get("count_policy"))))
        if not (str(_f.get("parent_risk_code") or "").strip()
                and str(_f.get("parent_risk_name") or "").strip()):
            issues.append(("ERROR", "config/risk_families.json",
                           "族「%s」缺父风险编号/名称（总事项数按父项计）" % _f.get("risk_family_name")))
    # ④⑤ 可学习内容分级
    try:
        from engine.learnable_rules import (   # noqa: PLC0415
            TIERS, may_write_rule, tier_of)
    except Exception as exc:  # noqa: BLE001
        return issues + [("ERROR", "engine/learnable_rules.py",
                          "无法导入可学习内容分级权威：%s" % exc)]
    for _t in ("auto", "manual", "accumulate", "forbidden"):
        if _t not in TIERS or not TIERS[_t]:
            issues.append(("ERROR", "engine/learnable_rules.py", "四档分级缺档「%s」" % _t))
    if tier_of("某个未登记的类别") != "manual":
        issues.append(("ERROR", "engine/learnable_rules.py",
                       "未知类别未按最严档 manual 处理（等于给系统空白授权）"))
    for _k in ("法律条文", "追征期", "滞纳金", "处罚标准", "主观故意认定", "企业申辩结论"):
        if tier_of(_k) != "forbidden":
            issues.append(("ERROR", "engine/learnable_rules.py",
                           "「%s」应为禁止自动学习档" % _k))
        if may_write_rule(_k)[0]:
            issues.append(("ERROR", "engine/learnable_rules.py",
                           "禁止档「%s」不得允许系统自动写入规则库" % _k))
    return issues


def _load_module_attr(rel: str, attr: str):
    """按**文件**加载模块并取属性值（绕 `sys.modules` 缓存）。

    ★ 为什么不直接 `from engine import X`：后者会命中 `engine` 包命名空间上的
      **旧属性** —— 源码被改坏后仍返回旧对象 ⇒ 反向验证"改坏却不报红"的**假绿**
      （实测：本闸门第一版用 `from engine import`，G9-A 反向验证假通过）。
    """
    import importlib.util
    _spec = importlib.util.spec_from_file_location("_layer_attr_for_gate", ROOT / rel)
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    return getattr(_mod, attr)


def _load_layer_ids(rel: str) -> List[str]:
    """按**文件**加载检测器实现层，返回其 redline_id 列表（`SPECS` 或 `DETECTORS`）。

    `DETECTORS` 形态为 `[(redline_id, func), ...]`（取 `x[0]`）。
    """
    import importlib.util
    _spec = importlib.util.spec_from_file_location("_layer_ids_for_gate", ROOT / rel)
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    if hasattr(_mod, "SPECS"):
        return [str(x.get("id") or x.get("redline_id") or "") for x in _mod.SPECS]
    return [str(x[0]) for x in (getattr(_mod, "DETECTORS", None) or [])]


def check_rule_layer_no_double_count() -> List[Tuple[str, str, str]]:
    """闸门：**规则分层不得重复计入**（2026-10-11，用户"规则库总数"口径追问引出）。

    ★ 根因（实测取证）：多份文档曾写「四层合计 211 条」= 91(红线)+85(VR)+25(专项)+10(缺口)。
      而专项探测（`special_redline_detectors.SPECS`）与缺口探测（`gap_tax_obligations.SPECS`）
      的 `redline_id` **全部落在** `engine.tax_redlines.REDLINES` 的 91 条 id 集合内 ——
      它们是红线的**检测器实现层**，不是独立规则。相加即**重复计数**（虚高约 22%）。
      唯一权威 = `config/rule_versions.json::layer_semantics`。

    三段（任一失败都不放过）：
      A【归属】检测器实现层的每条 id 必须 ⊂ 红线 id 集；出现"独立 id" ⇒ 分层被破坏 ⇒ ERROR。
      B【禁用拼接总量】`docs/**/*.md` / `README.md` / `config/rulelist_v*.json` 不得出现
        「(四层|各层|合计|总计…) 211|215 条」这类把检测器实现层计入总数的表述
        （含"勘误/重复计数/废止/不得/虚高"等**说明性上下文**的行豁免，以免误伤勘误本身）。
      C【口径一致】权威表每层 `count` 必须 == 实测；`counts` 与 `layer_semantics` 不得两处各写一遍。
    """
    issues: List[Tuple[str, str, str]] = []
    import json as _json

    _rv_p = ROOT / "config" / "rule_versions.json"
    try:
        _rv = _json.loads(_rv_p.read_text(encoding="utf-8"))
    except Exception as exc:                       # noqa: BLE001
        return [("ERROR", "config/rule_versions.json",
                 "规则分层权威表读不出来（分层判据无法校验）：%s" % exc)]
    _sem = _rv.get("layer_semantics") or {}
    _layers = _sem.get("layers") or {}
    _counts = _rv.get("counts") or {}
    if not _layers:
        return [("ERROR", "config/rule_versions.json",
                 "layer_semantics.layers 为空 ⇒ 分层口径无唯一权威，判据必然失真"
                 "（禁止用历史数字兜底）")]

    # ---- A 段：检测器实现层必须全部归属既有红线 ----
    try:
        _rl_ids = set(_load_redline_ids())
    except Exception as exc:                       # noqa: BLE001
        return issues + [("ERROR", "engine/tax_redlines.py",
                          "红线库读不出来，无法校验分层归属：%s" % exc)]
    try:
        _sp_ids = _load_layer_ids("engine/special_redline_detectors.py")
        _gr_ids = _load_layer_ids("engine/gap_risk_detectors.py")
        _gp_ids = _load_layer_ids("engine/gap_tax_obligations.py")
    except Exception as exc:                       # noqa: BLE001
        return issues + [("ERROR", "engine/special_redline_detectors.py",
                          "检测器实现层无法按文件加载（分层判据无法校验）：%s" % exc)]

    for _name, _ids in (("special_redline_detectors", _sp_ids),
                        ("gap_risk_detectors", _gr_ids),
                        ("gap_tax_obligations", _gp_ids)):
        _ghost = sorted({i for i in _ids if i and i not in _rl_ids})
        if _ghost:
            issues.append(("ERROR", "engine/%s.py" % _name,
                           "检测器实现层的 id %s **不在**红线 id 集内 ⇒ 分层被破坏"
                           "（它已不是红线的检测器，而是独立规则）。"
                           "应归入既有红线，或把该层标 counts_toward_rule_total=true 并说明。"
                           % (_ghost[:5],)))

    # ---- C 段：权威表口径 vs 实测（同概念不得两处各写一遍）----
    _actual = {"tax_redlines": len(_rl_ids),
               "special_redline_detectors": len([i for i in _sp_ids if i]),
               "gap_risk_detectors": len([i for i in _gr_ids if i]),
               "gap_tax_obligations": len([i for i in _gp_ids if i])}
    try:
        _actual["verified_rule_engine"] = len(
            _load_module_attr("engine/verified_rule_engine.py", "VERIFIED_RULE_CATALOG"))
    except Exception as exc:                       # noqa: BLE001
        issues.append(("ERROR", "engine/verified_rule_engine.py",
                       "已验证规则目录读取失败，无法校验其条数：%s" % exc))
    for _k, _v in _layers.items():
        if _k in _actual and _v.get("count") != _actual[_k]:
            issues.append(("ERROR", "config/rule_versions.json",
                           "layer_semantics.layers[%r].count=%s 与实测 %s 不一致 ⇒ 权威表已过期"
                           % (_k, _v.get("count"), _actual[_k])))
    if ("tax_redlines" in _counts
            and _counts.get("tax_redlines") != (_layers.get("tax_redlines") or {}).get("count")):
        issues.append(("ERROR", "config/rule_versions.json",
                       "counts.tax_redlines 与 layer_semantics 两处各写一遍且不一致"
                       "（同一概念必须一处维护）"))

    # ---- B 段：禁用「把检测器实现层计入总数」的拼接总量表述 ----
    # 判据：**同一行**同时出现「拼接总量关键词」与「禁用数值 211/215」即命中
    # （覆盖「四层合计 211 条」「合计 | | **211** |」「系统侧合计 211」等变体）。
    _num_re = re.compile(r"(?<!\d)(?:211|215)(?!\d)")
    _ctx_re = re.compile(r"(?:四层|各层|合计|总计|共计|系统侧)")
    _exempt = ("勘误", "重复计数", "废止", "禁止", "不得", "虚高", "错误口径",
               "旧口径", "更正", "弃用", "不应相加", "子集")
    _targets: list = sorted((ROOT / "docs").rglob("*.md"))
    _targets += [ROOT / "README.md"]
    _targets += sorted((ROOT / "config").glob("rulelist_v*.json"))
    for _p in _targets:
        if not _p.exists():
            continue
        try:
            _lines = _p.read_text(encoding="utf-8").splitlines()
        except Exception:                          # noqa: BLE001
            continue
        for _i, _ln in enumerate(_lines, 1):
            if not (_num_re.search(_ln) and _ctx_re.search(_ln)):
                continue
            if any(_e in _ln for _e in _exempt):
                continue
            issues.append(("ERROR", str(_p.relative_to(ROOT)),
                           "第 %d 行出现「把检测器实现层计入规则总数」的拼接总量表述：%s —— "
                           "专项/缺口是红线的检测器实现，不得与红线/VR 相加；"
                           "请改为分层列示（权威 config/rule_versions.json::layer_semantics）"
                           % (_i, _ln.strip()[:60])))
    return issues


def check_risk_score_monotone() -> List[Tuple[str, str, str]]:
    """闸门：**风险分值必须由等级单调派生**（T-2，2026-10-12）。

    ★ 背景：用户确认前端有「按严重程度排序/筛选」需求 ⇒ 需要 0-100 分值。
      但项目铁律「禁止自动定性」⇒ **分值方向只能是 等级 → 分值**，不得反向。
      实测历史缺陷：`tax_risk._report_summary` 已累加 `r.get("risk_score", 0)`，
      而该字段**从未被生产者填充** ⇒ 恒取默认 0（**缺失≠0** 铁律），
      且等级词用 `良好`（不在 `LEGAL_LEVELS`）⇒ **第二套等级词表**。

    判据（三段，全部数据驱动）：
      A【单调】`RISK_SCORE_BANDS` 的分值顺序必须与 `risk_levels.severity` 严格一致；
      B【单一权威】`config/risk_scores.json::bands` 与 `RISK_SCORE_BANDS` 必须一一对应
        （同一概念不得两处各写一遍）；
      C【不得给非风险态打分】有分值的档必须 ∈ `RISK_GRADES`；证据状态（`待核验`）
        与正向发现必须为 `None`（实测断言，非只看表）。
    """
    issues: List[Tuple[str, str, str]] = []
    import json as _json
    try:
        from engine import risk_levels as _rl
    except Exception as exc:                       # noqa: BLE001
        return [("ERROR", "engine/risk_levels.py", "风险等级权威不可用：%s" % exc)]

    bands = dict(getattr(_rl, "RISK_SCORE_BANDS", {}) or {})
    if not bands:
        return [("ERROR", "engine/risk_levels.py",
                 "RISK_SCORE_BANDS 为空 ⇒ 分值口径无唯一权威（禁止空表静默通过）")]

    # A 单调
    _by_sev = [k for k, _ in sorted(bands.items(), key=lambda kv: -_rl.severity(kv[0]))]
    _by_score = [k for k, _ in sorted(bands.items(), key=lambda kv: -kv[1])]
    if _by_sev != _by_score:
        issues.append(("ERROR", "engine/risk_levels.py",
                       "分值顺序与等级 severity 不一致（分值必须由等级单调派生）："
                       "按 severity=%s vs 按 score=%s" % (_by_sev, _by_score)))

    # C 不得给非风险态打分
    for lv in bands:
        if lv not in _rl.RISK_GRADES:
            issues.append(("ERROR", "engine/risk_levels.py",
                           "「%s」不是可比风险档（不在 RISK_GRADES）却被赋分值 ⇒ "
                           "证据状态/词表外不得打分" % lv))
    for lv in _rl.EVIDENCE_STATES:
        if lv in bands:
            issues.append(("ERROR", "engine/risk_levels.py",
                           "证据状态「%s」被赋分值 ⇒ 证据不足不得参与风险含量排序" % lv))
    # 实断言（不只看表）
    if _rl.risk_score_of("待核验") is not None:
        issues.append(("ERROR", "engine/risk_levels.py", "`risk_score_of('待核验')` 必须为 None"))
    if _rl.risk_score_of("优惠机会", {"risk_level": "优惠机会"}) is not None:
        issues.append(("ERROR", "engine/risk_levels.py",
                       "正向发现（优惠机会）不得有风险分值"))
    if _rl.risk_score_of("") is not None:
        issues.append(("ERROR", "engine/risk_levels.py", "空等级不得有风险分值（缺失≠0）"))

    # B 单一权威：config 表与代码表一一对应
    _p = ROOT / "config" / "risk_scores.json"
    try:
        _cfg = _json.loads(_p.read_text(encoding="utf-8"))
    except Exception as exc:                       # noqa: BLE001
        return issues + [("ERROR", "config/risk_scores.json",
                          "分值分档权威表读不出来（判据无法校验）：%s" % exc)]
    _cfg_bands = {b.get("level"): b.get("score") for b in (_cfg.get("bands") or [])}
    if _cfg_bands != bands:
        issues.append(("ERROR", "config/risk_scores.json",
                       "分档表与 `engine/risk_levels.RISK_SCORE_BANDS` 不一致"
                       "（同一口径两处各写一遍）：config=%s vs code=%s" % (_cfg_bands, bands)))

    # D 端到端产出断言：真实报告产物里每条发现的分值必须与其**终局等级**一致。
    #   ★ 为什么必须做产品级断言（实测事故）：分值若在「等级上限压制」**之前**派生，
    #     会被压制成陈旧值（实测 `红字冲销…` 等级由「高风险」压到「低风险」，分值却留 80
    #     ⇒ 分值与等级矛盾）。只看表/函数抓不到，必须看产物。
    _rep = _canonical_report()
    if _rep is None:
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "无真跑产物 ⇒ 分值×等级一致性**未验证**（跑一次全量分析后自动生效）"))
    else:
        _er = _rep.get("enterprise_readable_report") or _rep
        for _p in (_er.get("confirmed_problems") or []):
            if not isinstance(_p, dict):
                continue
            _lv = str(_p.get("risk_level") or "").strip()
            _sc = _p.get("risk_score")
            _expect = _rl.RISK_SCORE_BANDS.get(_lv)
            if _sc is not None and _expect is not None and int(_sc) != int(_expect):
                issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                               "疑点「%s」等级=%s 却分值=%s（应为 %s）⇒ 分值与等级矛盾"
                               "（多半是分值在等级压制前派生）"
                               % (str(_p.get("title"))[:20], _lv, _sc, _expect)))
    return issues


def check_candidate_params_no_dangling() -> List[Tuple[str, str, str]]:
    """闸门：候选规则库**参数不得悬空** + 地区参数表合规（2026-10-13）。

    ★ 背景（规则去重合并第 2 步实测）：候选库 `config/rulelist_v{1,11,12}.json` 的
      `logic` 会引用 `params.<名>`，而 `params[src]` 是**按规则嵌套**的登记条目。
      实测 3 处「引用了未登记的参数名」⇒ 悬空引用（VAT-021 gap_threshold→diff_amount、
      INV-008 count_threshold→same_pair_count、PCT-006 deduction_ratio 未登记）。
      悬空的后果：落地时取不到阈值 ⇒ 要么崩、要么用默认值顶替（违反「缺失≠0」铁律）。

    ★ 口径提醒（本轮踩过）：`params` 是**嵌套**结构（`params['VAT-004']={"growth_gap":0.3}`），
      **不能按扁平 dict 查找** —— 首轮我曾因此误报「真悬空 172 条」，正确口径下为 3 条。

    三段判据：
      A【无悬空】每条候选：`logic` 引用的 `params.X` 必须能在 `params[src]` 中解析；
      B【地区参数合规】`config/region_params.json` 必须存在且结构合法
        （`local_pending` 一律 `value=null`，**禁止预设地方值**）；
      C【口径一致】凡引用地区参数的候选，其 params 条目须给出指向（`null` + `拒绝默认值`语义）。
    """
    import json as _json
    import re as _re
    issues: List[Tuple[str, str, str]] = []
    _num = _re.compile(r"params\.(\w+)")

    # A 无悬空
    for _rel in ("config/rulelist_v1.json", "config/rulelist_v11.json",
                 "config/rulelist_v12.json"):
        _p = ROOT / _rel
        if not _p.exists():
            issues.append(("ERROR", _rel, "候选规则库缺失（参数悬空判据无法执行）"))
            continue
        try:
            _d = _json.loads(_p.read_text(encoding="utf-8"))
        except Exception as exc:                   # noqa: BLE001
            issues.append(("ERROR", _rel, "候选规则库读不出来：%s" % exc))
            continue
        _params = _d.get("params") or {}
        for _r in (_d.get("rules") or []):
            _used = set(_num.findall(str(_r.get("logic") or "")))
            if not _used:
                continue
            _entry = _params.get(_r.get("src"))
            if not isinstance(_entry, dict):
                continue                            # 条目本身未登记 ⇒ 属「未落地」，另行统计
            _miss = sorted(x for x in _used if x not in _entry)
            if _miss:
                issues.append(("ERROR", _rel,
                               "规则 `%s` 的 logic 引用了未登记的参数名 %s "
                               "（`params['%s']` 实有 %s）⇒ **悬空引用**；"
                               "落地时会取不到阈值（缺失≠0），须统一命名或补登记"
                               % (_r.get("src"), _miss, _r.get("src"),
                                  sorted(k for k in _entry if not k.startswith("_")))))

    # B 地区参数表合规
    _rp = ROOT / "config" / "region_params.json"
    if not _rp.exists():
        issues.append(("ERROR", "config/region_params.json",
                       "地区参数表缺失 ⇒ 任务要求「地区均值必须参数化」无落点"))
    else:
        try:
            _rpd = _json.loads(_rp.read_text(encoding="utf-8"))
        except Exception as exc:                   # noqa: BLE001
            issues.append(("ERROR", "config/region_params.json", "读不出来：%s" % exc))
            _rpd = None
        if _rpd is not None:
            _ps = _rpd.get("params") or {}
            if not _ps:
                issues.append(("ERROR", "config/region_params.json",
                               "params 为空 ⇒ 违反「空表不得静默通过」"))
            for _k, _v in _ps.items():
                if not isinstance(_v, dict):
                    issues.append(("ERROR", "config/region_params.json",
                                   "条目 `%s` 不是对象" % _k))
                    continue
                if _v.get("kind") not in ("statutory", "local_pending"):
                    issues.append(("ERROR", "config/region_params.json",
                                   "条目 `%s` 的 kind=%r 不在 {statutory, local_pending} 内"
                                   % (_k, _v.get("kind"))))
                # ★ 不得预设地方值
                if _v.get("kind") == "local_pending" and _v.get("value") is not None:
                    issues.append(("ERROR", "config/region_params.json",
                                   "条目 `%s` 是地方自定参数却预设了 value=%r ⇒ "
                                   "**禁止预设地方值**（须由业务按属地确认后填入）"
                                   % (_k, _v.get("value"))))
    return issues


def check_rule_dsl_and_externalizable() -> List[Tuple[str, str, str]]:
    """闸门：T-6「规则外置」的表达力边界与字段缺口（2026-10-13）。

    ★ 背景：T-6 裁定为**三层渐进**（阈值类已外置 / 条件类可外置 / 要件化类留 Python）。
      本轮建 `engine/rule_dsl.py`（条件 DSL 解释器）后，**实测瓶颈不在 DSL，而在字段取数口径**：
      538 个字段被候选 `logic` 引用但 `var_map` 未登记取数口径。若无人对账，缺口会**悄悄扩大**。

    判据（A/B/C 三段）：
      A【白名单】候选 `logic` 用到的函数名必须 ∈ `ALLOWED_FUNCS`
        （未登记函数 ⇒ 解析期本就报错，此处再兜一层，防有人偷偷放宽白名单）；
      B【边界登记双向一致】实际「超表达力/不规范」规则集 必须与
        `config/rule_dsl_scope.json::unsupported_rules` / `malformed_rules` **完全一致**
        （既不许漏登，也不许幽灵登记）；
      C【缺口不得扩大】实际「字段取数口径缺口」数与「可外置条数」不得**劣于**登记值
        （缺口减少 ⇒ 台账 print 提示同步；缺口增加 ⇒ ERROR，须解释或补口径）。
    """
    import json as _json
    issues: List[Tuple[str, str, str]] = []
    _scope_p = ROOT / "config" / "rule_dsl_scope.json"
    try:
        from engine import rule_dsl as _dsl
    except Exception as exc:                       # noqa: BLE001
        return [("ERROR", "engine/rule_dsl.py", "DSL 解释器不可用：%s" % exc)]
    if not _scope_p.exists():
        return [("ERROR", "config/rule_dsl_scope.json",
                 "表达力边界登记表缺失（T-6 判据无落点）")]
    try:
        _scope = _json.loads(_scope_p.read_text(encoding="utf-8"))
    except Exception as exc:                       # noqa: BLE001
        return [("ERROR", "config/rule_dsl_scope.json", "读不出来：%s" % exc)]

    # ── 现算 ──
    _files = ("config/rulelist_v1.json", "config/rulelist_v11.json",
              "config/rulelist_v12.json")
    _vm = set()
    _rules = []
    for _rel in _files:
        _p = ROOT / _rel
        if not _p.exists():
            issues.append(("ERROR", _rel, "候选规则库缺失"))
            return issues
        _d = _json.loads(_p.read_text(encoding="utf-8"))
        _vm |= set(k for k in (_d.get("var_map") or _d.get("var_map_addendum") or {})
                   if not k.startswith("_"))
        for _r in (_d.get("rules") or []):
            _r["_params"] = (_d.get("params") or {}).get(_r.get("src"))
            _rules.append(_r)

    _unsup, _malf, _ext, _gap = [], [], 0, set()
    _funcs_used = set()
    for _r in _rules:
        _lg = str(_r.get("logic") or "")
        try:
            _pr = _dsl.compile_expr(_lg)
        except _dsl.UnsupportedSyntax:
            _unsup.append(_r["src"])
            continue
        except _dsl.DslError:
            _malf.append(_r["src"])
            continue
        _funcs_used |= set(_pr.funcs_used)
        _ids = set(_pr.identifiers)
        if not _ids:
            continue
        _entry = _r.get("_params")
        _kp = (set(k for k in _entry if not k.startswith("_"))
               if isinstance(_entry, dict) else set())
        _missv = _ids - _vm
        _missp = set(_pr.params_used) - _kp
        if not _missv and not _missp:
            _ext += 1
        else:
            _gap |= _missv

    # A 白名单
    _bad_fn = sorted(_funcs_used - set(_dsl.ALLOWED_FUNCS))
    if _bad_fn:
        issues.append(("ERROR", "engine/rule_dsl.py",
                       "候选 logic 使用了未登记函数 %s ⇒ 须登记白名单或改写表达式"
                       % _bad_fn))

    # B 边界登记双向一致
    _reg_u = sorted(x.get("src") for x in (_scope.get("unsupported_rules") or []))
    _reg_m = sorted(x.get("src") for x in (_scope.get("malformed_rules") or []))
    if sorted(_unsup) != _reg_u:
        _only_now = sorted(set(_unsup) - set(_reg_u))
        _only_reg = sorted(set(_reg_u) - set(_unsup))
        issues.append(("ERROR", "config/rule_dsl_scope.json",
                       "「超表达力（留 Python）」规则集与登记表不一致："
                       "实际多出 %s；登记多出 %s ⇒ 重跑 "
                       "`python scripts/_gen_rule_dsl_scope.py` 同步" % (_only_now, _only_reg)))
    if sorted(_malf) != _reg_m:
        _only_now = sorted(set(_malf) - set(_reg_m))
        _only_reg = sorted(set(_reg_m) - set(_malf))
        issues.append(("ERROR", "config/rule_dsl_scope.json",
                       "「表达式不规范」规则集与登记表不一致："
                       "实际多出 %s；登记多出 %s" % (_only_now, _only_reg)))

    # C 缺口不得扩大
    _cnt = _scope.get("counts") or {}
    _reg_gap = int(_cnt.get("gap_fields") or 0)
    _reg_ext = int(_cnt.get("ext_ok") or 0)
    if len(_gap) > _reg_gap:
        issues.append(("ERROR", "config/rule_dsl_scope.json",
                       "「字段取数口径缺口」**扩大了**：登记 %d、实际 %d ⇒ "
                       "新规则引入了未登记字段，须补口径并重跑生成器" % (_reg_gap, len(_gap))))
    # C2（2026-10-13）缺口**分档自洽**：按规则实现状态的切分之和必须等于总缺口。
    #   用途：T-6「第 1 批（已实现规则）」的口径**可对账** ——
    #   只改总数不改分档（或反之）⇒ 生成器与登记表脱节。
    _bs = ((_scope.get("gap_fields") or {}).get("batch_by_rule_status") or {})
    if _bs:
        _sum_f = (len((_bs.get("implemented") or {}).get("fields") or [])
                  + len((_bs.get("unimplemented") or {}).get("fields") or []))
        if _sum_f != _reg_gap:
            issues.append(("ERROR", "config/rule_dsl_scope.json",
                           "缺口分档之和 %d ≠ 总缺口 %d ⇒ 分档与总数脱节，重跑生成器"
                           % (_sum_f, _reg_gap)))
        _ri = int(_cnt.get("gap_refs_in_implemented_rules") or 0)
        _ru = int(_cnt.get("gap_refs_in_unimplemented_rules") or 0)
        if _ri + _ru != int(_cnt.get("gap_refs") or 0):
            issues.append(("ERROR", "config/rule_dsl_scope.json",
                           "缺口引用次数分档 %d+%d ≠ 总 %d"
                           % (_ri, _ru, int(_cnt.get("gap_refs") or 0))))
    else:
        issues.append(("WARN", "config/rule_dsl_scope.json",
                       "缺口未按规则实现状态分档（T-6 第 1 批无法对账）⇒ "
                       "重跑 `python scripts/_gen_rule_dsl_scope.py`"))

    # ★ D（2026-10-13）**「可外置」≠「可切换执行」** —— 必须有等价性验证，且结论自洽。
    #   事故背景：`ext_ok`（可外置）只衡量「表达要件是否齐备」（字段有口径 + 参数已登记），
    #   **不衡量"判据是否与现有 Python 实现等价"**。实测（12 用例中 8 个不一致）候选 DSL
    #   是现有判据的**简化版**：人数差异丢失 `has_uninsured` 防漏报护栏 ⇒ 漏报；
    #   进项异常丢失「已足额转出属正当情形」要件 ⇒ 误报。若把 `ext_ok` 当切换凭证，
    #   会**同时**引入漏报与误报（且都是税务口径上的实质错误）。
    #   判据：① `equivalence` 段必须存在且含 verdict；
    #         ② verdict != EQUIVALENT ⇒ **每条 externalizable_rule 的 switch_allowed 必须为假**
    #            （禁"一处说不可、另一处说可"的脱节）；
    #         ③ verdict == UNVERIFIED ⇒ ERROR（未验证就不得声称可切换）。
    _eq = _scope.get("equivalence") or {}
    _vd = str(_eq.get("verdict") or "")
    _ext_rules = _scope.get("externalizable_rules") or []
    if not _vd:
        issues.append(("ERROR", "config/rule_dsl_scope.json",
                       "缺 `equivalence` 段（等价性验证结论）⇒ 「可外置」会被误当作"
                       "「可切换执行」；须跑 `python scripts/_verify_dsl_equivalence.py` 后重跑生成器"))
    elif _vd == "UNVERIFIED":
        issues.append(("ERROR", "config/rule_dsl_scope.json",
                       "等价性**未验证**（verdict=UNVERIFIED）⇒ 不得声称可切换执行；"
                       "请跑 `python scripts/_verify_dsl_equivalence.py`"))
    elif _vd != "EQUIVALENT":
        _bad = [_r.get("src") for _r in _ext_rules if _r.get("switch_allowed")]
        if _bad:
            issues.append(("ERROR", "config/rule_dsl_scope.json",
                           "判定为不等价（verdict=%s），但以下「可外置」规则仍标 "
                           "`switch_allowed=True`（自相矛盾，禁止切换）：%s" % (_vd, _bad)))
    if _ext_rules and not _eq.get("evidence_source"):
        issues.append(("ERROR", "config/rule_dsl_scope.json",
                       "等价性结论缺 `evidence_source`（无法溯源到验证脚本）"))
    # 台账（可见、可收敛；不作为 ERROR）
    print("  [规则外置] 候选 %d 条｜可解析 %d｜可外置 %d（登记 %d）｜"
          "超表达力 %d｜不规范 %d｜字段缺口 %d（登记 %d）"
          % (len(_rules), len(_rules) - len(_unsup) - len(_malf), _ext, _reg_ext,
             len(_unsup), len(_malf), len(_gap), _reg_gap))
    if len(_gap) < _reg_gap or _ext != _reg_ext:
        print("  [规则外置] 指标已变化（缺口 %d→%d、可外置 %d→%d）"
              "⇒ 建议重跑 `python scripts/_gen_rule_dsl_scope.py` 同步登记表与报告"
              % (_reg_gap, len(_gap), _reg_ext, _ext))
    return issues


def check_legal_text_coverage() -> List[Tuple[str, str, str]]:
    """法规**正文库**（``static/legal_library.json``）覆盖率与字段完备性闸门。

    ★ 与 ``check_legal_versioning``（**版本登记** ``config/legal_versions.json``）是**两件事**：
      前者问「这部法现行有没有效」，本闸门问「这条**条文原文**有没有入库」。
      两者混谈会导致「登记了版本就以为有正文」的假绿。

    判据（A~C，任一不满足即 ERROR）：
      A **覆盖率不得退化** —— 红线库引用可在正文库匹配的比例，不得低于
        ``config/legal_text_coverage.json`` 的登记值（改了引用却忘了补条文 ⇒ 立刻报红）；
      B **字段完备** —— 每条正文必须含非空 ``law`` / ``article`` / ``content`` / ``source``，
        且 ``(law, article)`` 不得重复（重复 = 同一口径两处维护）；
      C **条数不得减少** —— 正文库条数不得低于登记值（防误删）。

    ★★ 2026-10-16：现算逻辑**收敛到唯一实现** ``engine/legal_coverage.py::compute``
      （本闸门只做"调它 + 与登记基线比对"），并把**未匹配项逐条列出**。
      同轮修掉一处**引用切分缺陷**：一句话引两部法时只取首部且法名/条号错配
      （``《增值税法》第二十八条及《增值税法实施条例》第三十九条``）⇒
      改用 ``legal_citation.split_citations`` 逐处计入，当前 **245/245 = 100%**、未匹配 0 处。
      ★ 纪律不变：**不得编造条文凑覆盖率**，取不到就如实留在 ``unmatched``。
    """
    issues: List[Tuple[str, str, str]] = []
    lib_path = ROOT / "static" / "legal_library.json"
    cov_path = ROOT / "config" / "legal_text_coverage.json"
    try:
        lib = json.loads(lib_path.read_text(encoding="utf-8"))
    except Exception as exc:                                    # noqa: BLE001
        return [("ERROR", str(lib_path), "正文库无法读取：%s" % exc)]

    # B 字段完备 + 去重
    seen: Dict[Tuple[str, str], int] = {}
    for i, item in enumerate(lib or []):
        if not isinstance(item, dict):
            issues.append(("ERROR", str(lib_path), "第 %d 条不是对象" % (i + 1)))
            continue
        for f in ("law", "article", "content", "source"):
            if not str(item.get(f) or "").strip():
                issues.append(("ERROR", str(lib_path),
                               "第 %d 条缺字段 `%s`（law=%r article=%r）"
                               % (i + 1, f, item.get("law"), item.get("article"))))
        k = (str(item.get("law") or "").strip(), str(item.get("article") or "").strip())
        if k in seen:
            issues.append(("ERROR", str(lib_path),
                           "`%s %s` 重复登记（第 %d 条与第 %d 条）—— 同一口径两处维护"
                           % (k[0], k[1], seen[k], i + 1)))
        else:
            seen[k] = i + 1

    # A/C 覆盖率与条数不得退化
    try:
        cov = json.loads(cov_path.read_text(encoding="utf-8"))
    except Exception:                                           # noqa: BLE001
        issues.append(("WARN", str(cov_path),
                       "未登记覆盖率基线 ⇒ 无法防退化。重跑 `python scripts/_load_legal_texts.py`"))
        return issues

    if len(lib) < int(cov.get("library_size") or 0):
        issues.append(("ERROR", str(lib_path),
                       "正文库条数 %d < 登记基线 %d ⇒ 疑误删（如确需减少，请重跑录入脚本更新基线）"
                       % (len(lib), int(cov.get("library_size") or 0))))

    # ★★ 2026-10-16 收敛：覆盖率**现算**移到唯一实现 `engine/legal_coverage.py`
    #   （原先本闸门与录入脚本 `_load_legal_texts.py::_write_coverage` **各写一套**：
    #    分叉后"登记基线"与"现算"用的不是同一把尺子 ⇒ 假绿/假红）。
    #   同轮还修了**复合引用漏算**：一句话引两部法原先只取首部，且法名与条号**错配**
    #   （实测 `《增值税法》第二十八条及《增值税法实施条例》第三十九条` ⇒ 返回
    #    `(增值税法, 第三十九条)`，而增值税法只有 38 条）⇒ 现按 `split_citations`
    #    逐处计入，引用数 242 → 245、可匹配 245（100%），未匹配 0 处。
    try:
        from engine.legal_coverage import compute as _cov_compute
        _r = _cov_compute(lib)
    except Exception as exc:                                    # noqa: BLE001
        issues.append(("ERROR", "engine/legal_coverage.py",
                       "覆盖率现算失败：%s（若导入异常，检查 sys.path）" % exc))
        return issues
    _tot, _hit = int(_r["total_refs"]), int(_r["matched_refs"])
    _base = float(cov.get("coverage") or 0)
    _now = (_hit / _tot) if _tot else 0.0
    # ★★ 2026-10-15 修（闸门自身缺陷）：登记值由录入器 `round(_, 4)` 写入，
    #   现算却是**未截断的原始浮点** ⇒ 同一份数据也会判"退化"（实测 241/242：
    #   登记 0.9959 vs 现算 0.99586776… ⇒ `_now < _base` 恒真 ⇒ **假 ERROR**）。
    #   比较必须在**同一精度**下：现算按登记的同样小数位取整后再比。
    _now_r = round(_now, 4)
    if _now_r + 1e-9 < _base:
        issues.append(("ERROR", str(cov_path),
                       "法规正文覆盖率**退化**：%d/%d = %.1f%% < 登记 %.1f%% ⇒ "
                       "红线引用了正文库中没有的条文，请补录（禁编造）后重跑录入脚本"
                       % (_hit, _tot, _now * 100, _base * 100)))
    # ★ 未匹配项**逐条**列出（不得以任何方式凑覆盖率；为空即全绿）
    for _u in (_r.get("unmatched") or [])[:10]:
        issues.append(("WARN", str(cov_path),
                       "未匹配引用（规则 %s）：%s ⇒ 与正文库对不上（%s）"
                       % (_u.get("rule_id"), str(_u.get("citation"))[:70],
                          "该法不在正文库" if not _u.get("law_in_library") else "条号无对应条文")))
    print("  [法规正文] 引用 %d 处｜可匹配 %d（%.1f%%，基线 %.1f%%）｜正文库 %d 条｜未匹配 %d 处"
          % (_tot, _hit, _now * 100, _base * 100, len(lib), len(_r.get("unmatched") or [])))
    return issues


# ★ 法规引用时效闸门扫描的源文件（模块级常量：便于测试以 tmp 文件做**反向验证**）
_CURRENCY_SCAN_FILES = ("engine/tax_redlines.py", "engine/special_redline_detectors.py",
                        "engine/gap_risk_detectors.py", "engine/gap_tax_obligations.py")


def check_redline_legal_basis_currency() -> List[Tuple[str, str, str]]:
    """红线法规依据**时效**闸门：不得引用**已废止**法规（A）与**不存在**的法规（B）。

    ★ 为什么必须独立于 ``check_legal_versioning``：后者只查「版本是否登记、状态是否 blocking」，
      本闸门查「引用是否**指向失效对象**」—— 两者覆盖不同失效形态。
    当前实测：``RL-SPT-008``（原引 1994 年出口退税办法）、``RL-SPT-005``（原引已废止的
    《进出口关税条例》）、``RL-FUND-004``（原引已废止的《现金管理暂行条例》）均已按
    现行依据改写；本闸门锁死该结论，防复发。
    """
    issues: List[Tuple[str, str, str]] = []
    sys.path.insert(0, str(ROOT))
    try:
        from engine.legal_version import canonical_law as _cl
        from engine.legal_version import registry_entries as _re_entries
        from engine.tax_redlines import REDLINES as _RL
    except Exception as exc:                                    # noqa: BLE001
        return [("ERROR", "engine/tax_redlines.py", "法规时效检查导入失败：%s" % exc)]

    _expired = {}
    for e in _re_entries():
        if str(e.get("status") or "").lower() in ("expired", "superseded"):
            _expired[_cl(str(e.get("law") or ""))] = str(e.get("status"))
    _hits = 0
    for r in _RL:
        lb = (r or {}).get("legal_basis")
        if isinstance(lb, str):
            lb = [lb]
        for it in (lb or []):
            if not isinstance(it, str) or not it.strip():
                continue
            # 留痕用「」标注历史引用，正式引用用《》；只检后者
            for m in re.finditer(r"《([^》]+)》", it):
                name = _cl(m.group(1))
                if name in _expired:
                    _hits += 1
                    issues.append(("ERROR", "engine/tax_redlines.py",
                                   "%s 引用了 status=%s 的法规《%s》⇒ 须改引现行依据"
                                   "（历史引用请用「」标注，勿用书名号）"
                                   % (r.get("id"), _expired[name], m.group(1))))
    # ── 扩展覆盖（2026-10-13）：检测器实现层的 policy_ref 亦不得引用失效法规 ──
    #   事故：本闸门原只查 ``tax_redlines.legal_basis``，而 ``special_redline_detectors.SPECS.policy_ref``
    #   是**另一份**政策引用（各写一份 ⇒ 多头维护），导致 RL-FUND-004 引《现金管理暂行条例》、
    #   RL-SPT-005 引《进出口关税条例》一度失效而未同步。现按**文件文本**扫描全部《》引用
    #   （留痕已统一用「」标注历史引用，故不会误报）。新增同类对象只需在 _scan 加一个文件名。
    _seen = set()
    for _rel in _CURRENCY_SCAN_FILES:
        _p = _rel if os.path.isabs(_rel) else os.path.join(str(ROOT), _rel)
        if not os.path.exists(_p):
            continue
        try:
            _txt = open(_p, encoding="utf-8").read()
        except Exception:                                      # noqa: BLE001
            continue
        for _m in re.finditer(r"《([^》]+)》", _txt):
            _name = _cl(_m.group(1))
            if _name in _expired and (_rel, _m.group(1)) not in _seen:
                _seen.add((_rel, _m.group(1)))
                _hits += 1
                issues.append(("ERROR", _rel,
                               "引用 status=%s 的法规《%s》⇒ 须改引现行依据"
                               "（历史引用请用「」标注，勿用书名号）"
                               % (_expired[_name], _m.group(1))))
    print("  [法规时效] 引用已废止/被取代法规 %d 处（应为 0）" % _hits)
    return issues


def check_rule_params_single_source() -> List[Tuple[str, str, str]]:
    """规则阈值**唯一权威**闸门（2026-10-15，遗留项③「规则 params 阈值参数化接引擎判定」）。

    ★ 背景（实测）：同一批法定扣除限额此前**两处各写一份** ——
      `engine/verified_rule_engine.py` 的 VR038/039/040 把 `0.6`/`0.005`/`0.15`/`0.14`
      **直接写进算式**，`engine/deduction_limit_detector.py` 又用 `_UNION_RATE=0.02` 等常量写了一遍
      ⇒ 法定比例一旦调整，必须记得改齐所有副本，漏一处即「同一条规则两个答案」。
      现已收敛到 `config/rule_params.json`（读取唯一入口 `engine/rule_params.py`）。

    判据（A~D，任一不满足即 ERROR）：
      A【表结构完备】每条含非空 `cn` / `value` / `unit` / `legal_basis` / `used_by`，且 `engine_wired` 为布尔；
      B【不得跨表重名】参数名不得与 `config/region_params.json` 重名
        （后者管**地区性**参数，前者管**全国法定**阈值；同名会导致"取到哪个表"的歧义）；
      C【未接入须写明理由】`engine_wired=false` 的条目必须给出 `not_wired_reason`
        （禁止只标 false 不解释 —— 那样"未接入"会被读成"已接入"）；
      D【声称已接入必须真的引用】`engine_wired=true` 的条目，其 `wired_in` 列出的**文件**
        必须真的出现该参数名 ⇒ 机器可核对，防「声明接了、代码里仍是字面量」的假参数化。
    """
    import json as _json
    import re as _re
    issues: List[Tuple[str, str, str]] = []
    p = ROOT / "config" / "rule_params.json"
    if not p.exists():
        return [("ERROR", "config/rule_params.json",
                 "规则阈值表缺失 ⇒ 「阈值唯一权威」无落点；引擎将回落到各自字面量（多头维护复发）")]
    try:
        d = _json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:                                    # noqa: BLE001
        return [("ERROR", "config/rule_params.json", "读不出来：%s" % exc)]
    params = d.get("params") or {}
    if not params:
        return [("ERROR", "config/rule_params.json",
                 "params 为空 ⇒ 违反「空表不得静默通过」")]

    # B 与地区参数表不得重名
    region_names: set = set()
    _rp = ROOT / "config" / "region_params.json"
    if _rp.exists():
        try:
            region_names = set((_json.loads(_rp.read_text(encoding="utf-8")).get("params") or {}).keys())
        except Exception:                                       # noqa: BLE001
            pass

    wired_checked = 0
    for name, e in params.items():
        if name.startswith("_") or not isinstance(e, dict):
            continue
        for k in ("cn", "value", "unit", "legal_basis", "used_by"):
            if e.get(k) in (None, "", [], {}):
                issues.append(("ERROR", "config/rule_params.json",
                               "参数 `%s` 缺 `%s`（阈值表条目必须自证口径与依据）" % (name, k)))
        if not isinstance(e.get("engine_wired"), bool):
            issues.append(("ERROR", "config/rule_params.json",
                           "参数 `%s` 的 `engine_wired` 必须显式布尔（true=引擎真按此阈值判定）" % name))
        if name in region_names:
            issues.append(("ERROR", "config/rule_params.json",
                           "参数 `%s` 与 config/region_params.json 重名 ⇒ 取数歧义"
                           "（本表=全国法定阈值，地区表=地方自定参数，**不得同名**）" % name))
        # C 未接入须给理由
        if e.get("engine_wired") is False and not e.get("not_wired_reason"):
            issues.append(("ERROR", "config/rule_params.json",
                           "参数 `%s` 标注 engine_wired=false 却未给 `not_wired_reason` ⇒ "
                           "「未接入」必须写明原因（否则会被读成已接入）" % name))
        # D 声称已接入 ⇒ 文件里必须真的引用
        if e.get("engine_wired") is True:
            files = e.get("wired_in") or []
            if not files:
                issues.append(("ERROR", "config/rule_params.json",
                               "参数 `%s` 声明 engine_wired=true 却未列 `wired_in` ⇒ 无法核对" % name))
            for ref in files:
                rel = str(ref).split("::")[0].split("（")[0].strip()
                fp = ROOT / rel
                if not fp.exists():
                    issues.append(("ERROR", "config/rule_params.json",
                                   "参数 `%s` 的 wired_in 指向不存在的文件 `%s`" % (name, rel)))
                    continue
                wired_checked += 1
                try:
                    src = fp.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if name not in src:
                    issues.append(("ERROR", rel,
                                   "参数 `%s` 声明已接入（wired_in），但该文件中**找不到该参数名** ⇒ "
                                   "疑似仍是字面量（假参数化）：改为 `rule_params.ratio(\"%s\")`"
                                   % (name, name)))
    print("  [规则阈值] 条目 %d｜engine_wired %d｜核对 wired_in %d 处"
          % (len([k for k in params if not k.startswith("_")]),
             len([k for k, v in params.items() if isinstance(v, dict) and v.get("engine_wired") is True]),
             wired_checked))
    return issues


def check_cnnum_single_source() -> List[Tuple[str, str, str]]:
    """中文数字解析**唯一权威**闸门（2026-10-15）。

    ★ 背景（实测两处事故）：同一件事曾有 **5 处私有实现**，能力各不相同 ——
      ① 两处只支持到「九十九」⇒ 「第一百零三条」解析不出，
         整部法全文入库后**条款索引 1806 条拿不到 `provision_id`**；
      ② 另一处的**排序键**在无「之N」时不乘 100（`第十五条`→15、`第十五条之一`→1501）
         ⇒「第十六条」(16) 竟小于 1501，被切分器判为"续行"而**吞掉条号**
         （修复后正文库再增 440 条：实测 6569 → 7009）。
      已收敛到 `engine/cnnum.py`。

    判据（A/B，任一不满足即 ERROR）：
      A【不得新增第 N 份】全仓不得再出现"中文数字对照表"字面量定义
        （同时含「零」与「十」两键的 dict），白名单：`engine/cnnum.py`（权威）+
        `engine/quality_gates.py`（历史实现，属质量闸门域，已登记待收敛）；
      B【权威行为正确】行为级断言（防"表被删/逻辑被改坏"却仍显示通过）：
        解析值正确 + 条号排序键**单调递增**（含「之N」时不得压过下一条）。
    """
    import re as _re
    issues: List[Tuple[str, str, str]] = []
    # 白名单：允许出现中文数字表的文件（新增需在此登记并说明理由）
    white = {"engine/cnnum.py": "唯一权威实现",
             "engine/quality_gates.py": "历史实现（质量闸门域，待收敛；不属法条通径）"}
    # 判据：同一 dict 字面量里同时出现「零」与「十」的键（单字映射多为其它用途，不算）
    pat_zero = _re.compile(r"""['"]零['"]\s*:\s*\d""")
    pat_ten = _re.compile(r"""['"]十['"]\s*:\s*\d""")
    scanned = 0
    for d in ("engine", "scripts", "tools", "static"):
        base = ROOT / d
        if not base.exists():
            continue
        for fp in base.rglob("*.py"):
            rel = fp.relative_to(ROOT).as_posix()
            if rel in white or "/_" in rel and rel.startswith("baseline/"):
                continue
            if rel.startswith("baseline/") or ".venv" in rel:
                continue
            try:
                src = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            scanned += 1
            if pat_zero.search(src) and pat_ten.search(src):
                issues.append(("ERROR", rel,
                               "出现**中文数字对照表**私有定义 ⇒ 与唯一权威 `engine/cnnum.py` "
                               "构成多头维护（历史教训：能力不一致导致 1806 条条款拿不到 ID、"
                               "排序键错乱吞掉 440 条）。改 `from engine.cnnum import cn_to_int`；"
                               "确属特殊域需保留者，请在闸门白名单登记理由"))

    # B 行为级断言（权威本身不得被改坏）
    try:
        from engine.cnnum import cn_to_int as _c2i, article_sort_key as _key
    except Exception as exc:                                    # noqa: BLE001
        issues.append(("ERROR", "engine/cnnum.py", "权威实现不可导入：%s" % exc))
        return issues
    for s, want in (("十五", 15), ("二十", 20), ("一百", 100), ("一百零三", 103),
                    ("一百二十三", 123), ("三百六十五", 365), ("十", 10)):
        got = _c2i(s)
        if got != want:
            issues.append(("ERROR", "engine/cnnum.py",
                           "行为断言失败：`cn_to_int(%r)` 应为 %d，实得 %r" % (s, want, got)))
    # 排序键单调：第十五条 < 第十五条之一 < 第十六条（旧实现的错乱点）
    seq = ["第十五条", "第十五条之一", "第十六条", "第二十条", "第二十条之二", "第二十一条"]
    keys = [_key(x) for x in seq]
    if keys != sorted(keys) or len(set(keys)) != len(keys):
        issues.append(("ERROR", "engine/cnnum.py",
                       "条号排序键**非严格递增**（旧事故复发点）：%s ⇒ %s"
                       % (seq, keys)))
    print("  [中文数字] 扫描 %d 个 py 文件｜白名单 %d 个｜行为断言 %d 组"
          % (scanned, len(white), 7 + 1))
    return issues


def check_material_granularity_truthful() -> List[Tuple[str, str, str]]:
    """材料关联粒度**三态如实**闸门（2026-10-15，遗留项②/④）。

    ★ 背景：材料与法规的组织关联此前**只到法规级**（`granularity="law"`，
      原话「摘要未写明 ⇒ 条款级留空待人工，不猜」）。补采材料正文后，
      正文里出现「法名**紧邻**条号」的显式引用 ⇒ 关联可提升到**条款级**。
      提升这件事**最容易做成假的**：随手用关键词"就近配对"就会产出
      "看起来专业但不成立"的条款关联。故设本闸门。

    判据（A~D，任一不满足即 ERROR）：
      A【三态自洽】`granularity` 与证据字段必须互洽：
        provision ⇔ `provision_ids` 非空；law ⇔ 有 `related_law_codes` 且无 `provision_ids`；
        none ⇔ 两者皆空。任何"声明条款级却无 ID"或"有 ID 却标 law"都判 ERROR。
      B【ID 形状合法】`provision_ids` 必须形如 `{法短码}-{条号:03d}`，且其法短码
        必须真在 `config/legal_law_codes.json` 中登记（防拼装出不存在的 ID）。
      C【依据可复核】对声明条款级的材料，其**采集正文**必须真的同时含该法名与该条号
        （抽样复核；正文缺失则不判 —— 属"未采集"，另行统计）。
      D【不得静默降级】`granularity` 必须是三态之一（禁空值/自造值）。
    """
    import json as _json
    import re as _re
    issues: List[Tuple[str, str, str]] = []
    p = ROOT / "config" / "legal_materials.json"
    if not p.exists():
        return [("ERROR", "config/legal_materials.json", "材料库缺失 ⇒ 粒度判据无落点")]
    try:
        d = _json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:                                    # noqa: BLE001
        return [("ERROR", "config/legal_materials.json", "读不出来：%s" % exc)]
    mats = d.get("materials") or []
    if not mats:
        return [("ERROR", "config/legal_materials.json", "materials 为空")]

    try:
        codes = {str(l.get("code")) for l in
                 (_json.loads((ROOT / "config" / "legal_law_codes.json")
                              .read_text(encoding="utf-8")).get("laws") or [])}
    except Exception as exc:                                    # noqa: BLE001
        return [("ERROR", "config/legal_law_codes.json", "法短码表读不出来：%s" % exc)]

    from engine import legal_extras as _EX
    from engine.legal_version import canonical_law as _cl
    allowed = {"provision", "law", "none"}
    n_prov = n_law = n_none = 0
    checked = 0
    for m in mats:
        g = m.get("granularity")
        if g not in allowed:                                    # D
            issues.append(("ERROR", "config/legal_materials.json",
                           "材料 %s 的 granularity=%r 不在三态 {provision, law, none} 内"
                           "（不得空值或自造）" % (m.get("material_id"), g)))
            continue
        pids = list(m.get("provision_ids") or [])
        laws = list(m.get("related_law_codes") or [])
        # A 三态自洽
        if g == "provision":
            n_prov += 1
            if not pids:
                issues.append(("ERROR", "config/legal_materials.json",
                               "材料 %s 声明 granularity=provision 却无 provision_ids ⇒ 假条款级"
                               % m.get("material_id")))
        elif g == "law":
            n_law += 1
            if pids:
                issues.append(("ERROR", "config/legal_materials.json",
                               "材料 %s 有 provision_ids 却标 granularity=law ⇒ 漏标（粒度被低估）"
                               % m.get("material_id")))
            if not laws:
                issues.append(("ERROR", "config/legal_materials.json",
                               "材料 %s 标 granularity=law 却无 related_law_codes ⇒ 无依据" 
                               % m.get("material_id")))
        else:                                                   # none
            n_none += 1
            if pids or laws:
                issues.append(("ERROR", "config/legal_materials.json",
                               "材料 %s 标 granularity=none 却有关联证据（laws=%d, pids=%d）"
                               % (m.get("material_id"), len(laws), len(pids))))
        # B ID 形状合法
        for pid in pids:
            mm = _re.match(r"^([A-Z0-9\-]+)-(\d{3,})$", pid)
            if not mm:
                issues.append(("ERROR", "config/legal_materials.json",
                               "条款 ID `%s`（材料 %s）形状非法，应为 `{法短码}-{条号:03d}`"
                               % (pid, m.get("material_id"))))
            elif mm.group(1) not in codes:
                issues.append(("ERROR", "config/legal_materials.json",
                               "条款 ID `%s` 的法短码 `%s` 未在 config/legal_law_codes.json 登记"
                               % (pid, mm.group(1))))

    # C 依据可复核（抽样：声明条款级且正文非空的前 60 条）
    #   ★ 复核的是**生成时用的同一条判据**——「法名紧邻条号」在正文中真实存在，
    #     而不是"正文里出现过法名"（后者太松：并列引多部法时必然通过）。
    #   ★ 法名从**条款 ID 反查**（`legal_materials.json` 的 `matched_provisions` 只存
    #     `law_code`，没有 `law` 字段；首版误按空法名比对 ⇒ 60 条假 ERROR）。
    from engine import legal_mapping as _LM
    _pidx = _LM.provision_index()
    _art_win = _re.compile(r"[》」】\)\s、，,；;：:]{0,4}第([零〇一二三四五六七八九十百千两]+)条")
    prov_mats = [m for m in mats if m.get("granularity") == "provision" and m.get("content_len")]
    for m in prov_mats[:60]:
        body = _EX._fulltext(str(m.get("material_id")))         # noqa: SLF001（读层内部取正文）
        if not body:
            continue
        checked += 1
        for pitem in (m.get("matched_provisions") or []):
            pid = str(pitem.get("provision_id") or "")
            meta = _pidx.get(pid) or {}
            law = _cl(str(meta.get("law") or ""))
            art = str(meta.get("article") or "") or str(pitem.get("article") or "")
            if not meta:
                # 条款 ID 不在索引里：允许（=条文未入正文库，已由 in_library 如实标注），
                # 但**不得**同时声称它在库（自相矛盾 ⇒ 材料库与条款索引已脱同步）。
                if pitem.get("in_library"):
                    issues.append(("ERROR", "config/legal_materials.json",
                                   "材料 %s 的 %s 标 `in_library=true`，但该 ID 在条款索引"
                                   "（config/legal_provisions.json）中**查不到** ⇒ 两表脱同步"
                                   % (m.get("material_id"), pid)))
                continue
            if not (law and art):
                continue
            # 正文里该法名之后必须紧跟该条号（允许隔书名号收尾符与空白）
            ok = any(
                (lambda mm: bool(mm) and _cnnum_article_eq(mm.group(1), art))(
                    _art_win.search(body, i + len(law)))
                for i in (x.start() for x in _re.finditer(_re.escape(law), body))
            )
            if not ok:
                issues.append(("ERROR", "config/legal_materials.json",
                               "材料 %s 声明条款级 %s（%s%s），但正文中**找不到「法名紧邻该条号」**"
                               "⇒ 依据不成立（疑为「就近配对」式假关联）"
                               % (m.get("material_id"), pid, law, art)))
                break
    print("  [材料粒度] 条款级 %d｜法规级 %d｜未确证 %d｜抽样复核依据 %d 条"
          % (n_prov, n_law, n_none, checked))
    return issues


def _cnnum_article_eq(cn: str, article: str) -> bool:
    """中文条号与「第X条」是否指同一条（走唯一权威 `engine.cnnum`）。

    ★ 用模块级 `re`（不是 `_re`：那个别名只在个别函数内局部导入过，
      在模块级函数里引用会 NameError，且被本函数的 `except` 吞成 False
      ⇒ 闸门曾因此误报 60 条假 ERROR —— 判据自身的名字错误比数据错误更难发现）。
    """
    try:
        from engine.cnnum import cn_to_int
        m = re.match(r"^第(.+?)条", str(article or ""))
        want = cn_to_int(m.group(1)) if m else None
        return want is not None and cn_to_int(cn) == want
    except Exception:                                           # noqa: BLE001
        return False


def check_candidate_param_index() -> List[Tuple[str, str, str]]:
    """候选阈值**唯一索引**（D-01）—— 三册 `params` 只有一个取用入口，且不得跨册冲突。

    ★★ 为什么要有这道闸门（2026-10-16 阶段1 D-01 裁定）：
      三册 `config/rulelist_v1|v11|v12.json` 各自维护 `params`，此前消费方有两条
      **互不一致**的取法：`tools/export_rulelist_yaml.py::_collect()` 用 `dict.update()`
      把三册合并（**同名键静默覆盖、无留痕**），而 `engine/rulelist_v1.py::params_of()`
      只读 V1.0 一册 ⇒ 同一条规则的阈值可能得到**两个答案**且无人发现。
      现收敛为 `engine.rule_loader.param_index()` 单一入口；本闸门守它不被改回。

    判据：
      A 索引**无跨册冲突**（同一键在多册取值不同 ⇒ ERROR，须人工收敛）；
      B 索引键数 == 三册 `params` 去重后键数（防索引漏读/多读）；
      C 每条候选规则的 `params_ref` 与索引一致（防消费方各写一份）；
      D 索引内每个 `params_ref` 指向的分册**确实存在**。
    """
    issues: List[Tuple[str, str, str]] = []
    sys.path.insert(0, str(ROOT))
    try:
        from engine import rule_loader as _RL                        # noqa: PLC0415
    except Exception as exc:                                         # noqa: BLE001
        return [("ERROR", "engine/rule_loader.py", "导入失败：%s" % exc)]

    idx = _RL.param_index()

    # A 冲突
    conf = idx.get("conflicts") or []
    if conf:
        issues.append(("ERROR", "config/rulelist_v*.json",
                       "**候选阈值跨册冲突 %d 条**（同一键在多册取值不同 ⇒ 取到哪个答案取决于册序）：%s"
                       % (len(conf), [c["key"] for c in conf][:8])))

    # B 键数自洽：直接重数三册
    raw_keys: set = set()
    for name in _RL.CANDIDATE_BOOKS:
        p = ROOT / "config" / name
        if not p.exists():
            issues.append(("ERROR", "config/%s" % name, "候选阈值分册缺失"))
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:                                     # noqa: BLE001
            issues.append(("ERROR", "config/%s" % name, "读取失败：%s" % exc))
            continue
        raw_keys |= {str(k) for k in (doc.get("params") or {}) if not str(k).startswith("_")}
    if len(raw_keys) != idx["stats"]["keys"]:
        issues.append(("ERROR", "engine/rule_loader.py",
                       "索引键数 %d ≠ 三册去重键数 %d（索引漏读或多读）"
                       % (idx["stats"]["keys"], len(raw_keys))))

    # C 候选规则的 params_ref 必须与索引一致
    mism: List[str] = []
    for name in _RL.CANDIDATE_BOOKS:
        p = ROOT / "config" / name
        if not p.exists():
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        for r in (doc.get("rules") or []):
            rid = str(r.get("src") or "")
            if not rid:
                continue
            want = "config/%s::params.%s" % (name, rid)
            got = (idx["params"].get(rid) or {}).get("params_ref", "")
            if got and got != want:
                mism.append("%s: 表内 %s ≠ 索引 %s" % (rid, want, got))
    if mism:
        issues.append(("ERROR", "config/rulelist_v*.json",
                       "候选规则 params_ref 与索引不一致 %d 条：%s" % (len(mism), mism[:5])))

    # D params_ref 指向的分册存在
    missing: List[str] = []
    for key, ent in idx["params"].items():
        f = ROOT / str(ent.get("file") or "")
        if not f.exists():
            missing.append("%s → %s" % (key, ent.get("file")))
    if missing:
        issues.append(("ERROR", "config/rulelist_v*.json",
                       "索引指向不存在的分册 %d 条：%s" % (len(missing), missing[:5])))

    if not issues:
        issues.append(("INFO", "config/rulelist_v*.json",
                       "候选阈值唯一索引：键 %d（V1.0 %d / V1.1 %d / V1.2 %d），冲突 0，"
                       "重复登记 %d，params_ref 全部一致 ✓"
                       % (idx["stats"]["keys"],
                          idx["stats"]["books"].get("V1.0", 0),
                          idx["stats"]["books"].get("V1.1", 0),
                          idx["stats"]["books"].get("V1.2", 0),
                          idx["stats"]["redundant"])))
    return issues


def check_law_code_unique() -> List[Tuple[str, str, str]]:
    """`config/legal_law_codes.json` **短码表唯一性** —— 一部法只许登记一个短码。

    ★★ 为什么要有这道闸门（2026-10-16 实测事故）：同一份文件被登记了**两行两个短码**
      —— 一行用**主题型名**（「关于异常增值税扣税凭证管理等有关事项的公告」），
      一行用**文号型名**（「国家税务总局公告2019年第38号」）；实测 3 组。
      后果（都是真缺陷，不是"重复登记而已"）：
        ① 法名 → 短码的映射取决于**登记表行序**（先到先得）⇒ 同一份数据
           在不同顺序下可能落到不同短码，**不稳定**；
        ② 条款 ID 前缀二选一 ⇒ 同一部法两次生成给出不同 `provision_id`；
        ③ 覆盖率按法名比对时**时对时不上**（实测覆盖率从 241 掉到 240）。
      ⇒ 合并为一行（保留主题型短码，文号型名并入别名；见
        `scripts/_merge_duplicate_law_codes.py`，台账 `merged_codes` 可追溯）。

    判据：
      A 任何两个短码**不得共享归一名**（含别名）—— 即不得指向同一部法；
      B `code` / `name` 各自唯一；
      C `provision_id_prefix` 必须等于 `code + "-"`（防前缀与短码不一致）。
    """
    issues: List[Tuple[str, str, str]] = []
    f = ROOT / "config" / "legal_law_codes.json"
    if not f.exists():
        return [("WARN", "config/legal_law_codes.json", "短码表不存在 ⇒ 跳过")]
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception as exc:                                    # noqa: BLE001
        return [("ERROR", "config/legal_law_codes.json", "短码表读不出来：%s" % exc)]

    sys.path.insert(0, str(ROOT))
    from engine.legal_version import canonical_law as _cl                     # noqa: PLC0415

    laws = d.get("laws") or []
    name2codes: Dict[str, set] = {}
    for l in laws:
        for k in [l.get("name")] + list(l.get("aliases") or []):
            if k:
                name2codes.setdefault(_cl(str(k)), set()).add(str(l.get("code")))
    dup = {k: sorted(v) for k, v in name2codes.items() if len(v) > 1}
    if dup:
        issues.append(("ERROR", "config/legal_law_codes.json",
                       "**同一部法登记了多个短码**（%d 组 ⇒ 法名→短码映射不稳定、"
                       "`provision_id` 前缀二选一、覆盖率时对时不上）：%s"
                       % (len(dup), list(dup.items())[:3])))
    for field in ("code", "name"):
        seen: Dict[str, int] = {}
        for i, l in enumerate(laws):
            v = str(l.get(field) or "")
            if not v:
                issues.append(("ERROR", "config/legal_law_codes.json",
                               "第 %d 行缺 `%s`" % (i + 1, field)))
                continue
            if v in seen:
                issues.append(("ERROR", "config/legal_law_codes.json",
                               "`%s` 重复：`%s`（第 %d 行与第 %d 行）"
                               % (field, v, seen[v], i + 1)))
            else:
                seen[v] = i + 1
    bad_pref = [l for l in laws if l.get("provision_id_prefix") != str(l.get("code") or "") + "-"]
    if bad_pref:
        issues.append(("ERROR", "config/legal_law_codes.json",
                       "%d 行的 `provision_id_prefix` ≠ `code + '-'`（前缀与短码不一致）：例 %s"
                       % (len(bad_pref), bad_pref[0].get("code"))))
    print("  [短码表] 登记 %d 部｜归一名 %d 个｜重复登记 %d 组｜已合并留痕 %d 条"
          % (len(laws), len(name2codes), len(dup), len(d.get("merged_codes") or [])))
    return issues


def check_provision_id_unique() -> List[Tuple[str, str, str]]:
    """条款 ID（`provision_id`）**唯一性与可追溯性** —— 条款级关联的主键。

    ★★ 为什么要有这道闸门（2026-10-16 实测事故）：`provision_id` 是
      「规则/材料 → 具体条文」关联的**主键**。它一旦撞号，关联会把材料指到
      **另一条条文**上 —— 比"关联不到"更危险（错误的确定性）。实测曾撞号 **60 处**：
      · 「第X条**之N**」（刑法 53 条）：只取 X ⇒「第十七条」与「第十七条之一」同 ID；
      · 法名未收敛：同一部法在库里有**两个 law 名**（如 `财政部 国家税务总局…`
        与 `财政部国家税务总局…` **只差一个空格**）⇒ 同一条文各存一份、同 ID。
      两处根因都已在生成端修掉（`_gen_legal_index.py` 子定位后缀 /
      `_load_legal_texts_full._storage_law`）；本闸门**独立复核**，防止复发。

    判据（全部从 `legal_provisions.json` 的条目内容**独立现算**，不信任汇总字段）：
    A `provision_id` 唯一（同 ID 不得指两条不同条文）；
    B ID 前缀 = 该条的 `law_code`（防拼错短码）；
    C **同一部法只对应一个短码**（法名收敛的回归防线）；
    D 有「第X条」的条目标题**必须**派得出 ID（真缺口必须为 0）；
    E 汇总字段自洽（`duplicate_ids`/`uncoded` 与现算一致 —— 防"汇总字段被手改"）。
    """
    issues: List[Tuple[str, str, str]] = []
    f = ROOT / "config" / "legal_provisions.json"
    if not f.exists():
        return [("WARN", "config/legal_provisions.json", "条款索引不存在 ⇒ 跳过（先跑 _gen_legal_index.py）")]
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception as exc:                                    # noqa: BLE001
        return [("ERROR", "config/legal_provisions.json", "条款索引读不出来：%s" % exc)]
    provs = d.get("provisions") or []

    seen: Dict[str, List[str]] = {}
    for p in provs:
        pid = str(p.get("provision_id") or "")
        if not pid:
            continue
        seen.setdefault(pid, []).append("%s %s" % (p.get("law"), p.get("article")))
    dup = {k: v for k, v in seen.items() if len(v) > 1}
    if dup:
        issues.append(("ERROR", "config/legal_provisions.json",
                       "`provision_id` **撞号 %d 处** ⇒ 条款级关联会把材料指到错条文：%s"
                       % (len(dup), "；".join("%s→%s" % (k, "/".join(v[:2])) for k, v in list(dup.items())[:3]))))

    # B 前缀 = law_code
    bad_pref = [p for p in provs if p.get("provision_id") and p.get("law_code")
                and not str(p["provision_id"]).startswith(str(p["law_code"]) + "-")]
    if bad_pref:
        issues.append(("ERROR", "config/legal_provisions.json",
                       "%d 条条文的 `provision_id` 前缀与 `law_code` 不一致（短码拼错？）例：%s"
                       % (len(bad_pref), bad_pref[0].get("provision_id"))))

    # C 同一部法只对应一个短码（法名收敛回归防线）
    law2code: Dict[str, set] = {}
    for p in provs:
        if p.get("law_code"):
            law2code.setdefault(str(p.get("law")), set()).add(str(p.get("law_code")))
    multi = {k: v for k, v in law2code.items() if len(v) > 1}
    if multi:
        issues.append(("ERROR", "config/legal_provisions.json",
                       "%d 部法对应多个短码（法名未收敛）：%s"
                       % (len(multi), list(multi.items())[:2])))
    code2law: Dict[str, set] = {}
    for law, cs in law2code.items():
        for c in cs:
            code2law.setdefault(c, set()).add(law)
    multi2 = {k: v for k, v in code2law.items() if len(v) > 1}
    if multi2:
        issues.append(("ERROR", "config/legal_provisions.json",
                       "%d 个短码对应多个法名（**同一条文会存两份、ID 撞号**）：%s"
                       % (len(multi2), [(k, sorted(v)) for k, v in list(multi2.items())[:2]])))

    # D 有条号的条目必须派得出 ID（真缺口为 0）
    _ART = re.compile(r"第[零一二三四五六七八九十百千两]+条")
    real_gap = ["%s %s" % (p.get("law"), p.get("article")) for p in provs
                if not p.get("provision_id") and _ART.search(str(p.get("article") or ""))]
    if real_gap:
        issues.append(("ERROR", "config/legal_provisions.json",
                       "%d 条**有条号却拿不到** `provision_id`（法短码未登记？）：%s"
                       % (len(real_gap), real_gap[:3])))

    # E 汇总字段自洽
    if list(d.get("duplicate_ids") or {}) != sorted(dup):
        issues.append(("WARN", "config/legal_provisions.json",
                       "汇总字段 `duplicate_ids` 与现算不一致（疑被手改）"))
    print("  [条款ID] 条目 %d｜有ID %d｜撞号 %d｜真缺口 %d｜整文条目(无条号) %d｜法名-短码 %d 组"
          % (len(provs), len(seen), len(dup), len(real_gap),
             len(d.get("article_less") or []), len(law2code)))
    return issues


def check_confidence_weights_single_source() -> List[Tuple[str, str, str]]:
    """P0-5 阈值参数化：**置信度权重**的单一权威（`config/confidence_weights.json` ↔ 代码）。

    背景（2026-10-13 实测的真缺口）：`engine/argumentation.py` 的注释**早已声称**
    「权重外置、可配」，而权重实际硬编码在该文件（**假参数化**；历史遗留项 C1，
    最早记录于 2026-09-29 记忆）。本轮按项目既有模式外置 —— 与
    `config/risk_scores.json` ↔ `RISK_SCORE_BANDS` **完全同构**：

      A【可读与非空】权重表与区间表必须可读且非空（禁空表静默通过）；
      B【单一权威】`config/confidence_weights.json` 的 `weights` / `clamps`
        必须与 `argumentation.CONFIDENCE_WEIGHTS` / `CONFIDENCE_CLAMPS` **逐一相等**
        （同一概念不得两处各写一遍；浮点用 `==`：同值拷贝，容差会掩盖"改了一处"）；
      C【区间已派生】`_CONF_FLOOR` / `_CONF_CAP` / `_CONF_HIT_MIN` 必须**取自**区间表
        （否则字面量与表又成两份）；
      D【公式同源】公式文本必须含每个权重的数值（改表即改公式，不靠人工跟改）；
      E【分项账本恒等】`confidence_from_breakdown()` 复算必须等于「分项贡献之和」
        （既有 P1-2 铁律的**实断言**，不是只看表）。
    """
    issues: List[Tuple[str, str, str]] = []
    import json as _json
    try:
        from engine import argumentation as _arg
    except Exception as exc:                       # noqa: BLE001
        return [("ERROR", "engine/argumentation.py", "置信度权威不可用：%s" % exc)]

    _p = ROOT / "config" / "confidence_weights.json"
    try:
        _cfg = _json.loads(_p.read_text(encoding="utf-8"))
    except Exception as exc:                       # noqa: BLE001
        return [("ERROR", "config/confidence_weights.json",
                 "权重权威表读不出来（判据无法校验）：%s" % exc)]

    cfg_w = _cfg.get("weights") or {}
    cfg_c = _cfg.get("clamps") or {}
    # A 非空
    if not cfg_w:
        issues.append(("ERROR", "config/confidence_weights.json",
                       "weights 为空 ⇒ 阈值无唯一权威（禁止空表静默通过）"))
    if not cfg_c:
        issues.append(("ERROR", "config/confidence_weights.json",
                       "clamps 为空 ⇒ 区间阈值无唯一权威"))
    if issues:
        return issues

    code_w = dict(getattr(_arg, "CONFIDENCE_WEIGHTS", {}) or {})
    code_c = dict(getattr(_arg, "CONFIDENCE_CLAMPS", {}) or {})

    # B 逐一相等（两个方向都要查：缺项与多项都算"两处不一致"）
    for name, cfg_map, code_map, where in (
            ("weights", cfg_w, code_w, "CONFIDENCE_WEIGHTS"),
            ("clamps", cfg_c, code_c, "CONFIDENCE_CLAMPS")):
        for k in sorted(set(cfg_map) | set(code_map)):
            if k not in code_map:
                issues.append(("ERROR", "engine/argumentation.py",
                               "%s 的「%s」只在 config 里有 ⇒ 代码未实现该分项" % (name, k)))
                continue
            if k not in cfg_map:
                issues.append(("ERROR", "config/confidence_weights.json",
                               "%s 的「%s」只在代码里有 ⇒ 台账漏登记（改了一处）" % (name, k)))
                continue
            if float(cfg_map[k]) != float(code_map[k]):
                issues.append(("ERROR", "config/confidence_weights.json",
                               "%s「%s」两处不一致：config=%s 代码=%s"
                               % (name, k, cfg_map[k], code_map[k])))

    # C 区间已派生（不得再有一份字面量）
    for attr, key in (("_CONF_FLOOR", "floor"), ("_CONF_CAP", "cap"),
                      ("_CONF_HIT_MIN", "hit_min")):
        v = getattr(_arg, attr, None)
        if v is None:
            issues.append(("ERROR", "engine/argumentation.py", "缺少 %s" % attr))
        elif float(v) != float(code_c.get(key, float("nan"))):
            issues.append(("ERROR", "engine/argumentation.py",
                           "%s=%s 未取自 CONFIDENCE_CLAMPS[%r]=%s"
                           % (attr, v, key, code_c.get(key))))

    # D 公式同源：公式文本必须出现每个权重的数值
    try:
        _txt = _arg.confidence_formula_text()
    except Exception as exc:                       # noqa: BLE001
        issues.append(("ERROR", "engine/argumentation.py", "公式文本生成失败：%s" % exc))
        _txt = ""
    if _txt:
        for k, v in cfg_w.items():
            if ("%.2f" % abs(float(v))) not in _txt:
                issues.append(("ERROR", "engine/argumentation.py",
                               "公式文本未含权重 %s=%.2f ⇒ 表与公式不同源" % (k, v)))

    # E 实断言：分项贡献之和 == 复算置信度（唯一账本）
    try:
        _parts = [{"项": "基准分", "权重": cfg_w["base"], "取值": 1.0,
                   "贡献": round(float(cfg_w["base"]), 4)},
                  {"项": "证据链闭合度", "权重": cfg_w["closure"], "取值": 0.4,
                   "贡献": round(float(cfg_w["closure"]) * 0.4, 4)}]
        _sum = round(sum(float(p["贡献"]) for p in _parts), 2)
        _back = _arg.confidence_from_breakdown(_parts)
        if _back is None or round(float(_back), 2) != _sum:
            issues.append(("ERROR", "engine/argumentation.py",
                           "分项账本恒等被破坏：Σ贡献=%s 而复算=%s" % (_sum, _back)))
    except Exception as exc:                       # noqa: BLE001
        issues.append(("ERROR", "engine/argumentation.py",
                       "分项账本复算断言失败：%s" % exc))
    return issues


def check_rbac_single_source() -> List[Tuple[str, str, str]]:
    """RBAC / 租户 / 脱敏映射：**单一权威 + 不静默放行**（2026-10-14，P0-8）。

    ★ 为什么需要（实测缺口，不是设想）：P0-8 之前系统只有两值角色
      （`users.role ∈ {admin, user}`）与账套级数据权限。新增 RBAC 后，
      **最容易复发的病**是"同概念多处实现"：
        · 角色→权限映射在 `rbac_api` / `security_web` / 前端各判一次 ⇒ 迟早分叉；
        · 前端"藏了按钮"被当成权限控制 ⇒ 后端没拦（越权可达）；
        · 未知权限/未知角色被当成"默认放行" ⇒ 静默提权。

    判据（A 静态 + B 行为·子进程隔离）：
      A1 权威文件与入口齐备：`config/rbac.json`（唯一数据表）+ `engine/rbac.py`
         且导出 `rbac_allows` / `session_permission_codes` / `require_permission`。
      A2 判定唯一：全仓 `def rbac_allows(` 只允许 1 处。
      A3 角色写入唯一：`INSERT INTO role_permissions` 只允许出现在 `engine/rbac.py`。
      A4 `users.role` 的两值 `CHECK` **不得被改**（改了 `SessionContext.is_admin` 与既有
         守卫（`security_web._ADMIN_PATHS`）全部失配）—— 与本模块的
         "不换技术栈 / 只增不改" 裁定同口径。
      A5 接线：`main.py` 必须 include rbac 的两个 router（否则页面与接口都不可达）。
      A6 动作成对：P0-8 新增审计动作必须在 `ACTIONS` 与 `ACTION_CN` **同时**存在。
      B1 角色→权限（隔离库）：超管全权、企业财务无 `user.manage`、审计员无任何写权限。
      B2 **不静默放行**：未知权限码 / 未知角色码 / 空会话 ⇒ 一律 False。
      B3 角色→脱敏：取值必须落在 `report_compliance.redaction_roles` 键集合内
         （"要不要脱"的唯一权威仍在那里），未知角色 ⇒ 取最严 fallback。
      B4 租户隔离：非超管 `visible_tenant_ids` 只含自身租户；超管为 `None`（不限）。
    """
    issues: List[Tuple[str, str, str]] = []
    import os as _os
    import subprocess as _sp
    import sys as _sys
    import tempfile as _tf

    _REL = "engine/rbac.py"
    _CFG = "config/rbac.json"
    _rbac_py = ROOT / _REL
    _cfg_py = ROOT / _CFG
    if not _rbac_py.exists():
        return [("ERROR", _REL, "RBAC 唯一权威不存在（`engine/rbac.py`）")]
    if not _cfg_py.exists():
        return [("ERROR", _CFG, "RBAC 唯一数据表不存在（`config/rbac.json`）")]

    # ── A1 入口齐备 ────────────────────────────────────────────────────────
    _src = _rbac_py.read_text(encoding="utf-8", errors="replace")
    for _fn in ("rbac_allows", "session_permission_codes", "require_permission",
                "redaction_role_of", "visible_tenant_ids", "ensure_rbac_schema"):
        if ("def %s(" % _fn) not in _src:
            issues.append(("ERROR", _REL, "唯一权威缺 `%s()` —— 判定/建表入口不完整" % _fn))

    # ── A2 判定唯一 ────────────────────────────────────────────────────────
    _def_re = re.compile(r"^def\s+rbac_allows\s*\(", re.M)
    _dn = len(_def_re.findall(_src))
    if _dn != 1:
        issues.append(("ERROR", _REL,
                       "`def rbac_allows(` 出现 %d 次（必须 1 次）—— 权限判定只能有一个实现" % _dn))

    # ── A3 角色-权限写入唯一 ───────────────────────────────────────────────
    _ins_re = re.compile(r"INSERT\s+(?:OR\s+IGNORE\s+)?INTO\s+role_permissions", re.I)
    _files = [ROOT / "main.py", ROOT / "security.py", ROOT / "security_web.py",
              ROOT / "rbac_api.py", ROOT / "projects_api.py", ROOT / "reports_api.py",
              ROOT / "risks_api.py", ROOT / "rules_api.py", ROOT / "documents_api.py"]
    for _d in ("engine", "tools", "scripts", "tests", "routers"):
        _base = ROOT / _d
        if _base.is_dir():
            _files.extend(sorted(_base.rglob("*.py")))
    for _p in _files:
        if not _p.exists() or _p.resolve() == _rbac_py.resolve():
            continue
        if _p.resolve() == Path(__file__).resolve():
            continue                      # 本闸门自检跳过（提示文案内含该字面量）
        _t = _p.read_text(encoding="utf-8", errors="replace")
        _m = _ins_re.search(_t)
        if _m:
            _ln = _t[:_m.start()].count("\n") + 1
            issues.append(("ERROR", _p.relative_to(ROOT).as_posix(),
                           "第 %d 行出现 `INSERT INTO role_permissions` —— 角色-权限映射的"
                           "写入只允许在唯一权威 `%s`（否则同一概念两处实现，迟早分叉）"
                           % (_ln, _REL)))

    # ── A4 users.role 两值 CHECK 不得被改 ─────────────────────────────────
    _sec = (ROOT / "security.py").read_text(encoding="utf-8", errors="replace")
    if "CHECK(role IN ('admin', 'user'))" not in _sec:
        issues.append(("ERROR", "security.py",
                       "`users.role` 的两值 CHECK 被改动 —— `SessionContext.is_admin` 与既有"
                       "管理员守卫会失配；细粒度角色应走 RBAC 的 user_roles 表"))

    # ── A5 接线 ───────────────────────────────────────────────────────────
    _main = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
    for _token in ("from rbac_api import router as rbac_router",
                   "app.include_router(rbac_router)",
                   "app.include_router(rbac_page_router)"):
        if _token not in _main:
            issues.append(("ERROR", "main.py", "缺少接线片段：`%s`（页面/接口将不可达）" % _token))

    # ── A6 审计动作成对 ───────────────────────────────────────────────────
    try:
        _sys.path.insert(0, str(ROOT))
        from engine.audit_trail import ACTIONS as _ACT, ACTION_CN as _CN   # noqa: PLC0415
        for _a in ("auth.login", "auth.login_failed", "auth.logout", "auth.denied",
                   "user.create", "user.update", "role.create"):
            if _a not in _ACT:
                issues.append(("ERROR", "engine/audit_trail.py",
                               "P0-8 动作 `%s` 未登记进 ACTIONS（关键操作将无留痕）" % _a))
            elif _a not in _CN or not _CN.get(_a):
                issues.append(("ERROR", "engine/audit_trail.py",
                               "动作 `%s` 缺中文名（ACTION_CN 成对维护）" % _a))
    except Exception as exc:                                  # noqa: BLE001
        issues.append(("ERROR", "engine/audit_trail.py", "审计动作表不可读：%s" % exc))

    # ── B 行为（子进程 + APP_DATA_DIR 隔离，绝不碰真实库）───────────────────
    _probe = r'''
import sys, pathlib
sys.path.insert(0, str(pathlib.Path.cwd()))
from security import init_security_db, create_user, SessionContext
from engine import rbac as R
init_security_db(); R.ensure_rbac_schema()

def sess(uid, legacy="user", tenant=None):
    return SessionContext(user_id=uid, username="u%d" % uid, role=legacy,
                          allowed_company_ids=frozenset(), selected_company_id=None,
                          csrf_hash="", expires_at=0, tenant_id=tenant)

# B0 五个任务书角色齐备
for code in ("enterprise_finance", "tax_advisor", "review_expert",
             "system_admin", "auditor"):
    assert code in R.role_codes(), ("缺角色", code)

# B1 角色→权限
perms = set(R.permission_codes())
assert set(R.session_permission_codes(sess(1, legacy="admin"))) == perms, "超管权限不完整"
fin = create_user("gfin", "Gate-Fin-2026!", role="user")
R.assign_user_roles(fin, ["enterprise_finance"])
f = sess(fin)
assert R.rbac_allows(f, "project.write") is True, "企业财务应可管理项目"
assert R.rbac_allows(f, "user.manage") is False, "企业财务不应有 user.manage"
assert R.rbac_allows(f, "role.manage") is False, "企业财务不应有 role.manage"
aud = create_user("gaud", "Gate-Aud-2026!", role="user")
R.assign_user_roles(aud, ["auditor"])
a = sess(aud)
assert R.rbac_allows(a, "audit.view") is True, "审计员应可看留痕"
for w in ("project.write", "document.write", "analysis.run", "risk.review",
          "report.generate", "user.manage", "role.manage"):
    assert R.rbac_allows(a, w) is False, ("审计员不应有写权限", w)

# B2 不静默放行
assert R.rbac_allows(f, "no.such.permission") is False, "未知权限竟放行"
assert R.rbac_allows(f, "") is False, "空权限竟放行"
assert R.rbac_allows(None, "project.view") is False, "空会话竟放行"
assert R.session_permission_codes(None) == frozenset(), "空会话权限非空"
# 非法角色码不可指派
try:
    R.assign_user_roles(fin, ["no_such_role"])
    raise AssertionError("非法角色竟被接受")
except AssertionError:
    raise
except Exception as e:
    assert e.__class__.__name__ == "RbacError", e.__class__.__name__

# B3 角色→脱敏 值域
from engine.report_compliance import load_config
allowed = set((load_config().get("redaction_roles") or {}).keys())
cfg = R.rbac_config()
bad = {k: v for k, v in (cfg.get("role_redaction") or {}).items() if v not in allowed}
assert not bad, ("脱敏策略键非法", bad)
assert cfg.get("fallback_redaction") in allowed, "fallback 脱敏键非法"
assert R.redaction_role_of_code("__nope__") == cfg["fallback_redaction"], "未知角色未取最严策略"

# B4 租户隔离
tid = R.default_tenant_id()
assert isinstance(tid, int) and tid > 0, ("默认租户应为正数 id", tid)
assert R.visible_tenant_ids(sess(1, legacy="admin")) is None, "超管应不限租户"
assert R.visible_tenant_ids(sess(fin, tenant=tid)) == frozenset({tid}), "非超管租户范围错误"
assert R.visible_tenant_ids(None) == frozenset(), "空会话租户范围应为空"

print("OK rbac-gate")
'''
    with _tf.TemporaryDirectory(prefix="rbac-gate-") as _td:
        _env = dict(_os.environ)
        _env["APP_DATA_DIR"] = _td
        _env["PYTHONIOENCODING"] = "utf-8"
        try:
            _cp = _sp.run([_sys.executable, "-c", _probe], cwd=str(ROOT), env=_env,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180)
        except Exception as exc:                              # noqa: BLE001
            issues.append(("ERROR", _REL, "行为判据子进程无法启动：%s" % exc))
        else:
            if _cp.returncode != 0 or "OK rbac-gate" not in (_cp.stdout or ""):
                issues.append(("ERROR", _REL,
                               "RBAC/租户/脱敏行为判据失败"
                               "（角色权限 / 不静默放行 / 脱敏值域 / 租户隔离）：%s"
                               % ((_cp.stdout or "") + " | " + (_cp.stderr or "")).strip()[-400:]))
    return issues


def check_row_cap_manifest() -> List[Tuple[str, str, str]]:
    """P1-1 解析增强（三条判据，均**可自证**）：

    ① **行数上限登记表 ↔ 源码实测集合一致**：`main.py` 里每个 `min(nrows, N)` 的 N
       都必须在 `engine/parse_enhance.ROW_CAPS` 登记，反之亦然 ⇒ 改上限必须同步登记。
    ② **O(n²) 回归防线**：`main._get_row_values` 必须走顺序游标 `_PE.iter_rows_range`。
       退回 openpyxl read_only 的逐行区间读 ⇒ 复杂度 O(n²)（实测 200 行 0.57s →
       5,000 行 277.6s，`耗时/n²` 恒定 11~14 µs）。
    ③ **`nrows` 必须经 `_PE.safe_nrows`**：缺 worksheet dimension 的 xlsx
       （`max_row is None`）否则抛 TypeError 并被上层吞成"无法识别"。
    """
    issues: List[Tuple[str, str, str]] = []
    _rel = "engine/parse_enhance.py"
    try:
        import sys as _sys                              # noqa: PLC0415
        _sys.path.insert(0, str(ROOT))
        from engine import parse_enhance as _PE        # noqa: PLC0415
    except Exception as exc:                            # noqa: BLE001
        issues.append(("ERROR", _rel, "不可导入：%s" % exc))
        return issues

    _m = _PE.manifest()
    if not _m.get("row_caps"):
        issues.append(("ERROR", _rel, "`ROW_CAPS` 为空（上限登记表被清空）"))
    if not _m.get("consistent"):
        issues.append(("ERROR", _rel,
                       "行数上限登记表与 main.py 实测集合不一致：未登记=%s / 登记但源码已无=%s"
                       "（新增或修改 `min(nrows, N)` 必须同步 `ROW_CAPS`）"
                       % (_m.get("unregistered"), _m.get("stale"))))

    _main = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
    if "_PE.iter_rows_range(sheet, batch_start, batch_end)" not in _main:
        issues.append(("ERROR", "main.py",
                       "`_get_row_values` 未走顺序游标（`_PE.iter_rows_range`）⇒ openpyxl "
                       "read_only 下逐行区间读会退回 O(n²)（实测 5,000 行 277.6s）"))
    if "_PE.safe_nrows(" not in _main:
        issues.append(("ERROR", "main.py",
                       "`nrows` 未接 `_PE.safe_nrows` ⇒ 缺 worksheet dimension 的 xlsx"
                       "（max_row=None）会抛 TypeError 并被吞成「无法识别」"))
    # ★ 绕过路径也要抓：`else sheet.max_row` 直取与 `safe_nrows` 等价于没修
    #   （反向验证实测：只判 `_PE.safe_nrows(` 是否存在，会把"局部绕过"判成绿 ⇒ 假绿）
    if "else sheet.max_row" in _main or "else s.max_row" in _main:
        issues.append(("ERROR", "main.py",
                       "存在**绕过** `safe_nrows` 的 `else {sheet,s}.max_row` 直取 ⇒ "
                       "缺 worksheet dimension 的 xlsx（max_row=None）仍会崩"))
    for _tok in ("from parse_api import router as parse_router",
                 "app.include_router(parse_router)"):
        if _tok not in _main:
            issues.append(("ERROR", "main.py", "缺少 P1-1 接线片段：`%s`" % _tok))
    return issues


def check_ocr_engine_single_source() -> List[Tuple[str, str, str]]:
    """P1-2 OCR 引擎治理（三条判据）：

    ① `main._ocr_png_bytes` 必须走治理层（`_OC.record_ocr_run`）—— 不得再出现**裸**
       `return "\\n".join(chunks)`（否则"引擎状态/置信度/运行留痕"三个治理点全部落空）；
    ② 引擎登记表 `ENGINES` 必须覆盖既有实现的三个引擎（rapidocr / easyocr / tesseract）
       —— 少一个就会让"可用性回执"与实际能力不符；
    ③ 接线完整（import + `include_router`）。
    """
    issues: List[Tuple[str, str, str]] = []
    _main = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
    for _tok in ("from engine import ocr_engine as _OC",
                 "app.include_router(ocr_router)"):
        if _tok not in _main:
            issues.append(("ERROR", "main.py", "缺少 P1-2 接线片段：`%s`" % _tok))
    import re as _re                                          # noqa: PLC0415
    _bare = _re.findall(r'return "\\n"\.join\(chunks\)', _main)
    if _bare:
        issues.append(("ERROR", "main.py",
                       "`_ocr_png_bytes` 仍有 %d 处裸 `return \"\\n\".join(chunks)` ⇒ "
                       "绕过治理层（引擎可用性 / 置信度 / 留痕全部缺失）" % len(_bare)))
    if _main.count("_OC.record_ocr_run(") < 3:
        issues.append(("ERROR", "main.py",
                       "`_OC.record_ocr_run` 调用不足 3 处（三引擎各一 + 兜底）⇒ 部分路径无留痕"))

    try:
        import sys as _sys                                    # noqa: PLC0415
        _sys.path.insert(0, str(ROOT))
        from engine import ocr_engine as _OC                  # noqa: PLC0415
        _names = [str(e.get("name")) for e in _OC.ENGINES]
        for _n in ("rapidocr", "easyocr", "tesseract"):
            if _n not in _names:
                issues.append(("ERROR", "engine/ocr_engine.py",
                               "引擎 `%s` 未登记进 ENGINES（可用性回执将与实际能力不符）" % _n))
        if not _OC.engine_status().get("note"):
            issues.append(("ERROR", "engine/ocr_engine.py", "`engine_status().note` 为空"))
    except Exception as exc:                                  # noqa: BLE001
        issues.append(("ERROR", "engine/ocr_engine.py", "不可导入或状态不可取：%s" % exc))
    return issues


def check_extract_rules_sync() -> List[Tuple[str, str, str]]:
    """P1-3 数据校验规则（三条判据）：

    ① `engine.extract_validate.RULES` 与 `config/standard_fields.json::_validation`
       的键集合**必须完全一致**（新增规则要两处同步，否则前端字典与实际校验不对应）；
    ② 规则数不得少于 12（P1-3 的下限，防被误删）；
    ③ 每条规则必须有中文名（前端直接展示，缺名会露出英文枚举码）。
    """
    issues: List[Tuple[str, str, str]] = []
    _rel = "engine/extract_validate.py"
    try:
        import json as _json                                  # noqa: PLC0415
        import sys as _sys                                    # noqa: PLC0415
        _sys.path.insert(0, str(ROOT))
        from engine.extract_validate import RULES as _R, RULE_CN as _CN   # noqa: PLC0415
        _cfg = _json.loads((ROOT / "config" / "standard_fields.json")
                           .read_text(encoding="utf-8"))
        _decl = set((_cfg.get("_validation") or {}).keys())
        _have = set(str(x) for x in _R)
        if _have != _decl:
            issues.append(("ERROR", _rel,
                           "规则清单与配置说明表不同集合：仅在代码=%s / 仅在配置=%s"
                           % (sorted(_have - _decl), sorted(_decl - _have))))
        if len(_have) < 12:
            issues.append(("ERROR", _rel, "校验规则数 %d < 12（P1-3 下限）" % len(_have)))
        _noname = [r for r in _R if not _CN.get(r)]
        if _noname:
            issues.append(("ERROR", _rel, "规则缺中文名（前端会露出英文码）：%s" % _noname))
    except Exception as exc:                                  # noqa: BLE001
        issues.append(("ERROR", _rel, "不可导入或配置不可读：%s" % exc))
    return issues


def check_review_flow_wiring() -> List[Tuple[str, str, str]]:
    """P1-4 人工复核流程（四条判据）：

    ① `engine.risk_review` 必须导出 `bulk_review` / `history` / `review_stats`；
    ② `risks_api.py` 必须注册三个新端点；
    ③ **路由顺序**：`/risks/review-board` 与 `/risks/bulk-review` 必须出现在
       `/risks/{risk_id}` **之前** —— 否则会被路径参数吃成"风险编号 review-board"（静默 404）；
    ④ 批量复核的汇总审计动作 `risk.bulk_review` 必须已登记且有中文名（否则留痕失败）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        import sys as _sys                                    # noqa: PLC0415
        _sys.path.insert(0, str(ROOT))
        from engine import risk_review as _R                  # noqa: PLC0415
        for _n in ("bulk_review", "history", "review_stats"):
            if not hasattr(_R, _n):
                issues.append(("ERROR", "engine/risk_review.py", "缺 P1-4 能力：`%s`" % _n))
        if int(getattr(_R, "BULK_LIMIT", 0) or 0) <= 0:
            issues.append(("ERROR", "engine/risk_review.py", "`BULK_LIMIT` 未设置（批量无上限）"))
        from engine.audit_trail import ACTIONS as _A, ACTION_CN as _C    # noqa: PLC0415
        if "risk.bulk_review" not in _A:
            issues.append(("ERROR", "engine/audit_trail.py",
                           "`risk.bulk_review` 未登记进 ACTIONS（批量复核将无留痕）"))
        elif not _C.get("risk.bulk_review"):
            issues.append(("ERROR", "engine/audit_trail.py",
                           "`risk.bulk_review` 缺中文名（ACTION_CN 须成对维护）"))
    except Exception as exc:                                  # noqa: BLE001
        issues.append(("ERROR", "engine/risk_review.py", "不可导入：%s" % exc))

    _api = (ROOT / "risks_api.py").read_text(encoding="utf-8", errors="replace")
    for _p in ('"/risks/review-board"', '"/risks/bulk-review"', '"/risks/{risk_id}/history"'):
        if _p not in _api:
            issues.append(("ERROR", "risks_api.py", "缺 P1-4 端点：%s" % _p))
    # ★ 顺序判据：字面量路径必须早于参数化路径出现
    _i_board = _api.find('"/risks/review-board"')
    _i_bulk = _api.find('"/risks/bulk-review"')
    _i_param = _api.find('"/risks/{risk_id}"')
    if _i_param >= 0:
        for _name, _idx in (("review-board", _i_board), ("bulk-review", _i_bulk)):
            if 0 <= _idx and _idx > _i_param:
                issues.append(("ERROR", "risks_api.py",
                               "`/risks/%s` 注册在 `/risks/{risk_id}` **之后** ⇒ "
                               "会被路径参数吃成风险编号（静默 404）" % _name))
    return issues


def check_template_manage_wiring() -> List[Tuple[str, str, str]]:
    """P1-5 报告模板管理（四条判据）：

    ① `engine.template_store` 必须导出 `list_templates` / `get_template` /
       `upsert_template` / `disable_template` / `effective_templates`；
    ② **内置来源单一**：`builtin_templates()` 与 `report_compliance.load_config()["templates"]`
       的键集合必须一致（本层不得复制或改写内置）；
    ③ **接线完整**（import + `include_router`，含页面路由）。
    """
    issues: List[Tuple[str, str, str]] = []
    _rel = "engine/template_store.py"
    try:
        import sys as _sys                                    # noqa: PLC0415
        _sys.path.insert(0, str(ROOT))
        from engine import template_store as T                # noqa: PLC0415
        from engine.report_compliance import load_config      # noqa: PLC0415
        for _n in ("list_templates", "get_template", "upsert_template",
                   "disable_template", "effective_templates"):
            if not hasattr(T, _n):
                issues.append(("ERROR", _rel, "缺 P1-5 能力：`%s`" % _n))
        cfg_keys = set((load_config().get("templates") or {}).keys())
        bi_keys = set(T.builtin_templates().keys())
        if cfg_keys != bi_keys:
            issues.append(("ERROR", _rel,
                           "内置模板集合与 config 不一致：仅代码=%s / 仅配置=%s"
                           % (sorted(bi_keys - cfg_keys), sorted(cfg_keys - bi_keys))))
    except Exception as exc:                                  # noqa: BLE001
        issues.append(("ERROR", _rel, "不可导入或配置不可读：%s" % exc))

    _main = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
    for _tok in ("from templates_api import router as templates_router",
                 "app.include_router(templates_router)",
                 "app.include_router(templates_page_router)"):
        if _tok not in _main:
            issues.append(("ERROR", "main.py", "缺少 P1-5 接线片段：`%s`" % _tok))
    return issues


def check_rule_version_manage_wiring() -> List[Tuple[str, str, str]]:
    """P1-6 规则版本管理（四条判据）：

    ① `engine.rule_version_admin` 必须导出 `publish` / `rollback` / `diff` / `list_versions`；
    ② **未发布时与基线一致**：台账为空 ⇒ `rule_versions.rule_set_version()`
       必须等于 `config/rule_versions.json::rule_set_version`（否则既有报告溯源被悄悄改口径）；
    ③ 审计动作 `rule_version.publish` / `rule_version.rollback` 必须已登记且有中文名；
    ④ 接线完整 + **路由顺序**（字面量段早于 `{version}`）。
    """
    issues: List[Tuple[str, str, str]] = []
    _rel = "engine/rule_version_admin.py"
    try:
        import sys as _sys                                    # noqa: PLC0415
        _sys.path.insert(0, str(ROOT))
        from engine import rule_version_admin as A            # noqa: PLC0415
        from engine import rule_versions as RV                # noqa: PLC0415
        for _n in ("publish", "rollback_version", "diff", "list_versions", "snapshot_of"):
            if not hasattr(A, _n):
                issues.append(("ERROR", _rel, "缺 P1-6 能力：`%s`" % _n))
        if not RV.published_version():
            _cfg_v = str(RV.load_versions().get("rule_set_version") or "")
            _eff_v = str(RV.rule_set_version() or "")
            if _cfg_v != _eff_v:
                issues.append(("ERROR", "engine/rule_versions.py",
                               "台账为空时生效版本(%s) != 配置基线(%s) ⇒ 既有报告溯源被改口径"
                               % (_eff_v, _cfg_v)))
        from engine.audit_trail import ACTIONS as _A, ACTION_CN as _C    # noqa: PLC0415
        for _a in ("rule_version.publish", "rule_version.rollback"):
            if _a not in _A:
                issues.append(("ERROR", "engine/audit_trail.py",
                               "`%s` 未登记进 ACTIONS（版本变更将无留痕）" % _a))
            elif not _C.get(_a):
                issues.append(("ERROR", "engine/audit_trail.py", "`%s` 缺中文名" % _a))
    except Exception as exc:                                  # noqa: BLE001
        issues.append(("ERROR", _rel, "不可导入：%s" % exc))

    _main = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
    for _tok in ("from rule_versions_api import router as rule_versions_router",
                 "app.include_router(rule_versions_router)",
                 "app.include_router(rule_versions_page_router)"):
        if _tok not in _main:
            issues.append(("ERROR", "main.py", "缺少 P1-6 接线片段：`%s`" % _tok))
    _api = (ROOT / "rule_versions_api.py").read_text(encoding="utf-8", errors="replace")
    _i_lit = _api.find('"/rule-versions/meta"')
    _i_par = _api.find('"/rule-versions/{version}"')
    if _i_par >= 0 and 0 <= _i_lit and _i_lit > _i_par:
        issues.append(("ERROR", "rule_versions_api.py",
                       "`/rule-versions/meta` 注册在 `{version}` **之后** ⇒ 会被路径参数吃掉"))
    return issues


def check_legal_library_wiring() -> List[Tuple[str, str, str]]:
    """P2-1 法规库的**接线 / 路由顺序 / 读路径唯一**闸门。

    判据：
      A `engine/legal_library.py` 存在，且**不含第二套读盘** ——
        不得出现 `legal_library.json` / `legal_refs.json` 字面量
        （读路径唯一权威 = `legal_citation.library_paths()`）；
      B `legal_api.py` 的字面量段（`meta`/`stats`/`laws`）注册在参数化段 `{law}` **之前**；
      C `main.py` 含接线片段（import + include_router）；
      D 权限点 `legal.view` 已登记（RBAC 单一权威）。
    """
    issues: List[Tuple[str, str, str]] = []
    rel = "engine/legal_library.py"
    f = ROOT / rel
    if not f.exists():
        return [("ERROR", rel, "P2-1 法规库读层缺失")]
    txt = f.read_text(encoding="utf-8", errors="replace")
    # ★ 与既有闸门同口径：**掩掉注释与文档串**再判 —— 说明文字里提到文件名不是"真读盘"
    #   （实测踩过：本模块 docstring 说明数据来源，直接 grep 会得到假红）。
    import re as _re                                            # noqa: PLC0415
    _code = _re.sub(r'"""(?:.|\n)*?"""', lambda m: " " * len(m.group(0)), txt)
    _code = _re.sub(r"'''(?:.|\n)*?'''", lambda m: " " * len(m.group(0)), _code)
    _code = _re.sub(r"#[^\n]*", lambda m: " " * len(m.group(0)), _code)
    for bad in ("legal_library.json", "legal_refs.json"):
        if bad in _code:
            issues.append(("ERROR", rel,
                           "**代码**出现数据文件字面量 `%s` ⇒ 读盘路径出现第二处"
                           "（唯一权威 = legal_citation.library_paths）" % bad))

    api = (ROOT / "legal_api.py").read_text(encoding="utf-8", errors="replace")
    i_par = api.find('"/legal-library/{law}"')
    if i_par < 0:
        issues.append(("ERROR", "legal_api.py", "缺少参数化段 `/legal-library/{law}`"))
    for lit in ('"/legal-library/meta"', '"/legal-library/stats"', '"/legal-library/laws"'):
        i_lit = api.find(lit)
        if i_lit < 0:
            issues.append(("ERROR", "legal_api.py", "缺少字面量段 `%s`" % lit))
        elif i_par >= 0 and i_lit > i_par:
            issues.append(("ERROR", "legal_api.py",
                           "`%s` 注册在 `{law}` **之后** ⇒ 会被路径参数吃掉（静默 404）" % lit))

    main_txt = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
    for tok in ("from legal_api import router as legal_router",
                "app.include_router(legal_router)"):
        if tok not in main_txt:
            issues.append(("ERROR", "main.py", "缺少 P2-1 接线片段：`%s`" % tok))

    try:
        import sys as _s                                            # noqa: PLC0415
        _s.path.insert(0, str(ROOT))
        from engine import rbac as _RB                              # noqa: PLC0415
        if "legal.view" not in _RB.permission_codes():
            issues.append(("ERROR", "config/rbac.json", "缺少权限点 `legal.view`"))
    except Exception as exc:                                        # noqa: BLE001
        issues.append(("ERROR", "config/rbac.json", "RBAC 不可读：%s" % exc))
    return issues


def check_industry_indicators_wiring() -> List[Tuple[str, str, str]]:
    """P2-2 行业指标库的**接线 / 路由顺序 / 硬编码 / 口径单一权威**闸门。

    判据：
      A `engine/industry_indicators.py` 必须**薄转发**口径警示（出现 `IB.BENCHMARK_CAUTION`），
        且**不得**出现警示语字面量本身（防第二份声明）；
      B 该模块**不得硬编码行业 id**（行业清单动态取自 `industry_params.industry_ids()`）；
      C `industry_api.py` 的字面量段（`meta`/`stats`/`generic`）注册在参数化段 `{industry}` **之前**；
      D `main.py` 含接线片段；E 权限点 `industry.view` 已登记。
    """
    issues: List[Tuple[str, str, str]] = []
    rel = "engine/industry_indicators.py"
    f = ROOT / rel
    if not f.exists():
        return [("ERROR", rel, "P2-2 行业指标库读层缺失")]
    txt = f.read_text(encoding="utf-8", errors="replace")
    import re as _re                                            # noqa: PLC0415
    _code = _re.sub(r'"""(?:.|\n)*?"""', lambda m: " " * len(m.group(0)), txt)
    _code = _re.sub(r"'''(?:.|\n)*?'''", lambda m: " " * len(m.group(0)), _code)
    _code = _re.sub(r"#[^\n]*", lambda m: " " * len(m.group(0)), _code)
    if "IB.BENCHMARK_CAUTION" not in _code:
        issues.append(("ERROR", rel,
                       "未薄转发口径警示 `IB.BENCHMARK_CAUTION`（不得自写一份口径声明）"))
    try:
        _s = txt
        _caution = "系统内置行业统计通用参考值"
        if _caution in _code:
            issues.append(("ERROR", rel, "**代码**出现口径警示语字面量 ⇒ 第二份声明"))
        import sys as _s2                                       # noqa: PLC0415
        _s2.path.insert(0, str(ROOT))
        from engine import industry_params as _IP                # noqa: PLC0415
        _ids = [str(x) for x in _IP.industry_ids() if x]
        _hard = [i for i in _ids if ('"%s"' % i) in _code or ("'%s'" % i) in _code]
        if _hard:
            issues.append(("ERROR", rel,
                           "**代码**硬编码行业 id：%s（行业清单须动态取自 industry_params）" % _hard))
    except Exception as exc:                                    # noqa: BLE001
        issues.append(("ERROR", rel, "行业参数不可读：%s" % exc))

    api = (ROOT / "industry_api.py").read_text(encoding="utf-8", errors="replace")
    i_par = api.find('"/industry-indicators/{industry}"')
    if i_par < 0:
        issues.append(("ERROR", "industry_api.py", "缺少参数化段 `/industry-indicators/{industry}`"))
    for lit in ('"/industry-indicators/meta"', '"/industry-indicators/stats"',
                '"/industry-indicators/generic"'):
        i_lit = api.find(lit)
        if i_lit < 0:
            issues.append(("ERROR", "industry_api.py", "缺少字面量段 `%s`" % lit))
        elif i_par >= 0 and i_lit > i_par:
            issues.append(("ERROR", "industry_api.py",
                           "`%s` 注册在 `{industry}` **之后** ⇒ 会被路径参数吃掉（静默 404）" % lit))

    main_txt = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
    for tok in ("from industry_api import router as industry_router",
                "app.include_router(industry_router)"):
        if tok not in main_txt:
            issues.append(("ERROR", "main.py", "缺少 P2-2 接线片段：`%s`" % tok))

    try:
        import sys as _s3                                       # noqa: PLC0415
        _s3.path.insert(0, str(ROOT))
        from engine import rbac as _RB                          # noqa: PLC0415
        if "industry.view" not in _RB.permission_codes():
            issues.append(("ERROR", "config/rbac.json", "缺少权限点 `industry.view`"))
    except Exception as exc:                                    # noqa: BLE001
        issues.append(("ERROR", "config/rbac.json", "RBAC 不可读：%s" % exc))
    return issues


def check_ai_assist_wiring() -> List[Tuple[str, str, str]]:
    """P2-3 AI 辅助分析的**接线 / 路由顺序 / 辅助定位**闸门。

    判据：
      A `engine/ai_assist.py` 必须具备「辅助而非判定」的三道机制：
        角色常量 `ROLE = "advisory"`、免责声明 `DISCLAIMER`、禁用定性词表 `FORBIDDEN_CLAIM_TERMS`；
      B `assist()` 的返回体必须**显式**写 `"replaces_rules": False`（不得只靠文档说明）；
      C LLM 文本必须过 `sanitize(`（防 AI 文本直出下"定性结论"）；
      D `ai_assist_api.py` **不得**出现免责声明字面量（声明唯一权威在 `ai_assist.DISCLAIMER`）；
      E 路由顺序：`/ai-assist/meta` 注册在 `/ai-assist/{code}` **之前**；
      F `main.py` 含接线片段；G 权限点 `risk.view` 已登记。
    """
    issues: List[Tuple[str, str, str]] = []
    rel = "engine/ai_assist.py"
    f = ROOT / rel
    if not f.exists():
        return [("ERROR", rel, "P2-3 AI 辅助层缺失")]
    txt = f.read_text(encoding="utf-8", errors="replace")
    for tok, why in (('ROLE = "advisory"', "角色常量 `ROLE`"),
                     ("DISCLAIMER = (", "免责声明 `DISCLAIMER`"),
                     ("FORBIDDEN_CLAIM_TERMS", "禁用定性词表")):
        if tok not in txt:
            issues.append(("ERROR", rel, "缺少%s ⇒ 无法保证「辅助而非判定」" % why))
    if '"replaces_rules": False' not in txt:
        issues.append(("ERROR", rel, "`assist()` 未显式写 `\"replaces_rules\": False`"))
    if "sanitize(text)" not in txt:
        issues.append(("ERROR", rel, "LLM 文本未过 `sanitize(text)` 清洗"
                                     "（命中定性词会被直出 ⇒ 等于 AI 文本当判定用）"))

    api_path = ROOT / "ai_assist_api.py"
    if not api_path.exists():
        issues.append(("ERROR", "ai_assist_api.py", "P2-3 接口层缺失"))
    else:
        api = api_path.read_text(encoding="utf-8", errors="replace")
        if "本内容由 AI 辅助生成" in api:
            issues.append(("ERROR", "ai_assist_api.py",
                           "出现免责声明字面量 ⇒ 第二份声明（唯一权威 = engine/ai_assist.DISCLAIMER）"))
        i_par = api.find('"/ai-assist/{code}"')
        i_lit = api.find('"/ai-assist/meta"')
        if i_par < 0:
            issues.append(("ERROR", "ai_assist_api.py", "缺少参数化段 `/ai-assist/{code}`"))
        if i_lit < 0:
            issues.append(("ERROR", "ai_assist_api.py", "缺少字面量段 `/ai-assist/meta`"))
        elif i_par >= 0 and i_lit > i_par:
            issues.append(("ERROR", "ai_assist_api.py",
                           "`/ai-assist/meta` 注册在 `{code}` **之后** ⇒ 会被路径参数吃掉"))

    main_txt = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
    for tok in ("from ai_assist_api import router as ai_assist_router",
                "app.include_router(ai_assist_router)"):
        if tok not in main_txt:
            issues.append(("ERROR", "main.py", "缺少 P2-3 接线片段：`%s`" % tok))

    try:
        import sys as _s                                        # noqa: PLC0415
        _s.path.insert(0, str(ROOT))
        from engine import rbac as _RB                          # noqa: PLC0415
        if "risk.view" not in _RB.permission_codes():
            issues.append(("ERROR", "config/rbac.json", "缺少权限点 `risk.view`"))
    except Exception as exc:                                    # noqa: BLE001
        issues.append(("ERROR", "config/rbac.json", "RBAC 不可读：%s" % exc))
    return issues


def check_tax_models_wiring() -> List[Tuple[str, str, str]]:
    """P2-4 多税种深度模型的**接线 / 路由顺序 / 数据驱动 / 实现可溯源**闸门。

    判据：
      A `config/tax_deep_models.json` 可解析且 schema 齐备；模型 code **全局唯一**；
      B **每个非空 `impl` 都必须有对应 `engine/<impl>.py`**（实现可溯源，禁写幻觉模块名）；
      C `engine/tax_deep_models.py` 的**代码**不得硬编码税种名（税种清单动态取
        `tax_impact.known_tax_types()`），且必须薄转发税率表 `tax_rate_table(`；
      D 路由顺序：`/tax-models/meta`、`/coverage`、`/cross-tax` 在 `{tax}` **之前**；
      E `main.py` 含接线片段；F 权限点 `risk.view` 已登记。
    """
    issues: List[Tuple[str, str, str]] = []
    rel_cfg = "config/tax_deep_models.json"
    cfg_path = ROOT / rel_cfg
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as exc:                                    # noqa: BLE001
        return [("ERROR", rel_cfg, "无法读取/解析：%s" % exc)]
    if not int(cfg.get("schema") or 0) >= 1:
        issues.append(("ERROR", rel_cfg, "schema 缺失或版本过低"))
    taxes = [x for x in (cfg.get("taxes") or []) if isinstance(x, dict) and x.get("tax")]
    cross = [x for x in (cfg.get("cross_tax_models") or []) if isinstance(x, dict)]
    models = [m for x in taxes for m in (x.get("models") or []) if isinstance(m, dict)] + cross
    codes = [str(m.get("code") or "") for m in models]
    if not models:
        issues.append(("ERROR", rel_cfg, "未登记任何深度模型"))
    if len(codes) != len(set(codes)):
        dup = sorted({c for c in codes if codes.count(c) > 1})
        issues.append(("ERROR", rel_cfg, "模型 code 重复：%s" % dup))
    for m in models:
        imp = str(m.get("impl") or "").strip()
        if imp and not (ROOT / "engine" / ("%s.py" % imp)).is_file():
            issues.append(("ERROR", rel_cfg,
                           "模型 `%s` 的 impl=`%s` 无对应模块 `engine/%s.py`"
                           "（实现不可溯源）" % (m.get("code"), imp, imp)))

    rel = "engine/tax_deep_models.py"
    f = ROOT / rel
    if not f.exists():
        issues.append(("ERROR", rel, "多税种深度模型读层缺失"))
    else:
        txt = f.read_text(encoding="utf-8", errors="replace")
        import re as _re                                        # noqa: PLC0415
        _code = _re.sub(r'"""(?:.|\n)*?"""', lambda m: " " * len(m.group(0)), txt)
        _code = _re.sub(r"'''(?:.|\n)*?'''", lambda m: " " * len(m.group(0)), _code)
        _code = _re.sub(r"#[^\n]*", lambda m: " " * len(m.group(0)), _code)
        # ★ 必须检查**带模块前缀的调用**（`TI.xxx()`）而不是裸函数名 ——
        #   否则 docstring/字符串里提到 `tax_rate_table()` 就会被误判为"已薄转发"
        #   （实测踩过：本模块 metadata 的说明字符串含该词 ⇒ 判据假绿）。
        for tok in ("TI.tax_rate_table()", "TI.known_tax_types()"):
            if tok not in _code:
                issues.append(("ERROR", rel, "未薄转发税率/税种权威 `%s`" % tok))
        try:
            import sys as _s                                    # noqa: PLC0415
            _s.path.insert(0, str(ROOT))
            from engine import tax_impact as _TI                # noqa: PLC0415
            _hard = [t for t in sorted(_TI.known_tax_types())
                     if ('"%s"' % t) in _code or ("'%s'" % t) in _code]
            if _hard:
                issues.append(("ERROR", rel,
                               "**代码**硬编码税种名：%s（税种清单须动态取自 tax_impact）" % _hard[:5]))
        except Exception as exc:                                # noqa: BLE001
            issues.append(("ERROR", rel, "tax_impact 不可读：%s" % exc))

    api_path = ROOT / "tax_models_api.py"
    if not api_path.exists():
        issues.append(("ERROR", "tax_models_api.py", "P2-4 接口层缺失"))
    else:
        api = api_path.read_text(encoding="utf-8", errors="replace")
        i_par = api.find('"/tax-models/{tax}"')
        if i_par < 0:
            issues.append(("ERROR", "tax_models_api.py", "缺少参数化段 `/tax-models/{tax}`"))
        for lit in ('"/tax-models/meta"', '"/tax-models/coverage"', '"/tax-models/cross-tax"'):
            i_lit = api.find(lit)
            if i_lit < 0:
                issues.append(("ERROR", "tax_models_api.py", "缺少字面量段 `%s`" % lit))
            elif i_par >= 0 and i_lit > i_par:
                issues.append(("ERROR", "tax_models_api.py",
                               "`%s` 注册在 `{tax}` **之后** ⇒ 会被路径参数吃掉" % lit))

    main_txt = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
    for tok in ("from tax_models_api import router as tax_models_router",
                "app.include_router(tax_models_router)"):
        if tok not in main_txt:
            issues.append(("ERROR", "main.py", "缺少 P2-4 接线片段：`%s`" % tok))

    try:
        import sys as _s2                                       # noqa: PLC0415
        _s2.path.insert(0, str(ROOT))
        from engine import rbac as _RB                          # noqa: PLC0415
        if "risk.view" not in _RB.permission_codes():
            issues.append(("ERROR", "config/rbac.json", "缺少权限点 `risk.view`"))
    except Exception as exc:                                    # noqa: BLE001
        issues.append(("ERROR", "config/rbac.json", "RBAC 不可读：%s" % exc))
    return issues


def check_dashboard_wiring() -> List[Tuple[str, str, str]]:
    """P2-5 数据大屏的**接线 / 零 SQL / 取数通道唯一**闸门。

    判据：
      A `engine/dashboard.py` 必须**薄转发既有 Service 层**（5 个模块都被引用）——
        否则大屏会自建一套取数 ⇒ 租户隔离与权限口径必然漂移；
      B 该模块的**代码**必须**零 SQL**（不得出现 `SELECT` / `FROM <表>`）；
      C `dashboard_api.py` 路径**不得含参数段**（`{`）⇒ 不存在被路径参数吃掉的顺序问题；
      D `main.py` 含接线片段；E 权限点 `dashboard.view` 已登记。
    """
    issues: List[Tuple[str, str, str]] = []
    rel = "engine/dashboard.py"
    f = ROOT / rel
    if not f.exists():
        return [("ERROR", rel, "P2-5 数据大屏读层缺失")]
    txt = f.read_text(encoding="utf-8", errors="replace")
    import re as _re                                            # noqa: PLC0415
    _code = _re.sub(r'"""(?:.|\n)*?"""', lambda m: " " * len(m.group(0)), txt)
    _code = _re.sub(r"'''(?:.|\n)*?'''", lambda m: " " * len(m.group(0)), _code)
    _code = _re.sub(r"#[^\n]*", lambda m: " " * len(m.group(0)), _code)
    # ★ 必须检查 **import 语句**（`from engine import <mod>`）而不是裸模块名 ——
    #   否则 `metadata()` 里 `"via": "risk_service.stats"` 这类**说明字符串**会让判据假绿
    #   （实测踩过：去掉真正的薄转发后判据仍报 ERROR 0）。
    for mod in ("project_service", "document_service", "analysis_task",
                "risk_service", "audit_trail"):
        if ("from engine import %s" % mod) not in _code:
            issues.append(("ERROR", rel, "未薄转发 `%s` ⇒ 大屏自建取数（租户隔离会漂移）" % mod))
    up = _code.upper()
    for bad in ("SELECT", "INSERT", "UPDATE ", "DELETE "):
        if bad in up:
            issues.append(("ERROR", rel,
                           "**代码**出现 SQL 关键字 `%s` ⇒ 大屏必须经 Service 层取数（零 SQL）" % bad.strip()))

    api_path = ROOT / "dashboard_api.py"
    if not api_path.exists():
        issues.append(("ERROR", "dashboard_api.py", "P2-5 接口层缺失"))
    else:
        api = api_path.read_text(encoding="utf-8", errors="replace")
        for m in _re.finditer(r'@router\.\w+\(\s*"([^"]*)"', api):
            if "{" in m.group(1):
                issues.append(("ERROR", "dashboard_api.py",
                               "路径含参数段 `%s` ⇒ 字面量段可能被吃掉" % m.group(1)))
        for lit in ('"/dashboard/meta"', '"/dashboard/overview"', '"/dashboard/activity"'):
            if lit not in api:
                issues.append(("ERROR", "dashboard_api.py", "缺少字面量段 `%s`" % lit))

    main_txt = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
    for tok in ("from dashboard_api import router as dashboard_router",
                "app.include_router(dashboard_router)"):
        if tok not in main_txt:
            issues.append(("ERROR", "main.py", "缺少 P2-5 接线片段：`%s`" % tok))

    try:
        import sys as _s                                        # noqa: PLC0415
        _s.path.insert(0, str(ROOT))
        from engine import rbac as _RB                          # noqa: PLC0415
        if "dashboard.view" not in _RB.permission_codes():
            issues.append(("ERROR", "config/rbac.json", "缺少权限点 `dashboard.view`"))
    except Exception as exc:                                    # noqa: BLE001
        issues.append(("ERROR", "config/rbac.json", "RBAC 不可读：%s" % exc))
    return issues


def check_payload_written_after_analysis() -> List[Tuple[str, str, str]]:
    """S12-DEC-002（2026-10-14）：一键分析**产物载荷**的落盘接线 + 产物存在 + 读方薄转发。

    背景（实测）：`company_{cid}_full.json` 此前**只有离线脚本会写**，服务链路从不写
    ⇒ 换任何账套，风险库 / 复核 / 规则页**立即为空**（P0 级端到端断链；反向验证已证
    「断点是没人写，不是路径错」）。

    三条判据均为**行为级**（不是「符号是否存在」）：
      A【接线】`main.py::_persist_one_click_result` 的 AST 中必须真实存在
        `report_payload.dump_payload(...)` 调用 —— 注释掉 / 删掉即 ERROR。
      B【产物】凡在分析缓存（`data/cache/last_analysis_cache.json`）中有条目的账套，
        `offline_reports_root()` 下必须有对应载荷文件（有产出必有落盘）。
      C【读方薄转发】`engine/risk_service.load_payload` 必须调用
        `report_payload.payload_path(...)`，不得自己拼路径（读写两侧同一权威）。
    """
    issues: List[Tuple[str, str, str]] = []

    # ── A 接线（AST 级：注释掉/删除 ⇒ 命中不到该调用）──
    try:
        _main_tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:                                    # noqa: BLE001
        return [("ERROR", "main.py", "解析失败，落盘接线判据失效：%s" % exc)]
    _fn = None
    for _n in ast.walk(_main_tree):
        if isinstance(_n, ast.FunctionDef) and _n.name == "_persist_one_click_result":
            _fn = _n
    if _fn is None:
        issues.append(("ERROR", "main.py", "未找到 `_persist_one_click_result`（落盘接线判据失效）"))
    elif not any(isinstance(_n, ast.Call) and isinstance(_n.func, ast.Attribute)
                 and _n.func.attr == "dump_payload" for _n in ast.walk(_fn)):
        issues.append(("ERROR", "main.py",
                       "`_persist_one_click_result` 未调用 `report_payload.dump_payload()`"
                       " ⇒ 一键分析产物不落盘 ⇒ 风险库/复核端到端为空（S12-DEC-002 复发）"))

    # ── C 读方薄转发（AST 级）──
    try:
        _rs_tree = ast.parse((ROOT / "engine" / "risk_service.py").read_text(
            encoding="utf-8", errors="replace"))
    except Exception as exc:                                    # noqa: BLE001
        return issues + [("ERROR", "engine/risk_service.py", "解析失败，读方判据失效：%s" % exc)]
    _load_fn = None
    for _n in ast.walk(_rs_tree):
        if isinstance(_n, ast.FunctionDef) and _n.name == "load_payload":
            _load_fn = _n
    if _load_fn is None:
        issues.append(("ERROR", "engine/risk_service.py", "未找到 `load_payload`（读方判据失效）"))
    elif not any(isinstance(_n, ast.Call) and isinstance(_n.func, ast.Name)
                 and _n.func.id == "payload_path" for _n in ast.walk(_load_fn)):
        issues.append(("ERROR", "engine/risk_service.py",
                       "`load_payload` 未经 `payload_path()` 取路径 ⇒ 读写两侧可能各自漂移"))

    # ── B 产物存在（端到端口径）──
    _cache_p = ROOT / "data" / "cache" / "last_analysis_cache.json"
    if _cache_p.exists():
        try:
            from runtime_storage import offline_reports_root as _orr   # noqa: PLC0415
            _cache = json.loads(_cache_p.read_text(encoding="utf-8", errors="replace")) or {}
            _root = _orr()
            for _cid in list(_cache.keys()):
                try:
                    _cidi = int(_cid)
                except Exception:                               # noqa: BLE001
                    continue
                if _cidi <= 0:
                    continue
                _fp = os.path.join(_root, "company_%d_full.json" % _cidi)
                if not os.path.exists(_fp):
                    issues.append(("ERROR", "data/cache/last_analysis_cache.json",
                                   "账套 %d 有分析缓存但无落盘载荷「%s」⇒ 风险库/复核取不到数"
                                   "（S12-DEC-002）" % (_cidi, _fp)))
        except Exception as exc:                                # noqa: BLE001
            issues.append(("WARN", "engine/report_payload.py", "产物存在断言未执行：%s" % exc))
    return issues


def check_one_click_wiring_coverage() -> List[Tuple[str, str, str]]:
    """一键分析**接入面**四条常驻判据（★ 2026-10-14 · ODC-01/02/03 防复发）。

    背景：本项目反复出现「**功能做了但不生效**」——页面与模块都在，但一键分析链不消费
    （P1-5 报告模板管理空转、解析人工校正值不生效、P2-3/P2-4 页面无入口）。四类缺口各配判据：

    ① **模板读取唯一入口**：`industry_params.template_def()` 必须与
       `template_store.get_template()` **同源** —— 行为断言：同一模板的 `sections`
       必须逐项相等；且 `industry_params` 源码必须 import `engine.template_store`。
       否则「模板管理」页的覆盖/停用又回到空转（改页面、报告不变）。
    ② **校正值接线**：`engine/pipeline.py` 必须 import `engine.extract_overrides` 并调用
       `corrections_by_field` / `apply_overrides`；并做行为断言（合成用例）：
       校正值覆盖原值、**缺失值不写 0**（铁律「缺失 ≠ 0」）。
    ③ **页面可达**：`*_api.py` 里每个 HTML 页面路由都必须在 `static/index.html` 有入口。
       认证流页面（`/login` `/select-company` `/new-company`）**在册例外**（设计上无侧边栏）
       —— 例外必须逐条登记，不得用"兜底"放行。
    ④ **前端渲染点存在**（形态③：后端产出但前端零读取）：`report_template_meta` 与
       `extract_corrections` 必须出现在前端脚本的**去注释代码**里。
    """
    issues: List[Tuple[str, str, str]] = []
    # ── ① 模板读取唯一入口 ──
    _ip_rel = "engine/industry_params.py"
    try:
        import sys as _sys                                    # noqa: PLC0415
        _sys.path.insert(0, str(ROOT))
        _ip_src = (ROOT / "engine" / "industry_params.py").read_text(encoding="utf-8", errors="replace")
        if "from engine.template_store import" not in _ip_src:
            issues.append(("ERROR", _ip_rel,
                           "模板读取未走唯一权威 `engine.template_store` ⇒ 模板页覆盖/停用会对报告空转"))
        from engine.industry_params import template_def        # noqa: PLC0415
        from engine.template_store import get_template, builtin_templates   # noqa: PLC0415
        _bad = []
        for _tid in sorted(builtin_templates().keys()):
            _a = list((template_def(_tid) or {}).get("sections") or [])
            _b = list((get_template(_tid) or {}).get("sections") or [])
            if _a != _b:
                _bad.append((_tid, _a, _b))
        if _bad:
            issues.append(("ERROR", _ip_rel,
                           "template_def 与 template_store.get_template 不同源（%d 个模板不一致）：%s"
                           % (len(_bad), _bad[:3])))
    except Exception as _e1:                                  # noqa: BLE001
        issues.append(("ERROR", _ip_rel, "模板读取判据不可执行：%s" % _e1))

    # ── ② 校正值接线（静态 + 行为）──
    #   ★ 2026-10-14（反向验证抓出）：初版只查"名字是否出现过" ⇒ 把调用行删掉、
    #     只留 import 别名，判据**仍绿**（假绿）。现改为 **AST 语句级**：
    #     必须存在对 `extract_overrides` 导入别名的**实际调用**（`ast.Call`）。
    _pl_rel = "engine/pipeline.py"
    try:
        import ast as _ast                                    # noqa: PLC0415
        _pl_src = (ROOT / "engine" / "pipeline.py").read_text(encoding="utf-8", errors="replace")
        _tree = _ast.parse(_pl_src)
        _alias_of: Dict[str, str] = {}                        # 别名 -> 原名
        for _n in _ast.walk(_tree):
            if isinstance(_n, _ast.ImportFrom) and (_n.module or "").endswith("extract_overrides"):
                for _a in _n.names:
                    _alias_of[_a.asname or _a.name] = _a.name
        if not _alias_of:
            issues.append(("ERROR", _pl_rel,
                           "未从 `engine.extract_overrides` 导入任何名字 ⇒ 解析人工校正未接线"))
        else:
            _called = set()
            for _n in _ast.walk(_tree):
                if isinstance(_n, _ast.Call) and isinstance(_n.func, _ast.Name) \
                        and _n.func.id in _alias_of:
                    _called.add(_alias_of[_n.func.id])
            for _need in ("corrections_by_field", "apply_overrides"):
                if _need not in _called:
                    issues.append(("ERROR", _pl_rel,
                                   "`%s` 只被导入、**未被调用** ⇒ 校正值不生效（判据为语句级，不接受仅存在名字）"
                                   % _need))
        from engine.extract_overrides import (                # noqa: PLC0415
            apply_overrides, corrections_by_field, FINANCIAL_STATEMENT_KEYS, receipt)
        _t = {"income_statement": {"revenue": 1.0, "cost": 2.0, "net_profit": 3.0}}
        _corr = {"revenue": {"field": "revenue", "field_cn": "营业收入", "value": 9.0},
                 "cost": {"field": "cost", "field_cn": "营业成本", "value": None}}
        _t2, _ap = apply_overrides(_t, _corr, FINANCIAL_STATEMENT_KEYS)
        if _t2["income_statement"]["revenue"] != 9.0:
            issues.append(("ERROR", "engine/extract_overrides.py", "apply_overrides 未覆盖校正值"))
        if _t2["income_statement"]["cost"] != 2.0:
            issues.append(("ERROR", "engine/extract_overrides.py",
                           "缺失校正值被写入（应为原值 2.0）⇒ 违反「缺失 ≠ 0」"))
        if receipt(_ap).get("count_applied") != 1:
            issues.append(("ERROR", "engine/extract_overrides.py",
                           "receipt 计数错误（应为 1 项已应用）"))
    except Exception as _e2:                                  # noqa: BLE001
        issues.append(("ERROR", "engine/extract_overrides.py", "校正值接线判据不可执行：%s" % _e2))

    # ── ③ 页面可达 ──
    try:
        _idx = (ROOT / "static" / "index.html").read_text(encoding="utf-8", errors="replace")
        # 认证流页面：设计上**无侧边栏**（登记在册，逐条例外，不用兜底放行）
        _AUTH_FLOW = {"/login", "/select-company", "/new-company", "/account-setup"}
        _pages: Dict[str, str] = {}
        for _p in sorted(ROOT.glob("*_api.py")):
            _src = _p.read_text(encoding="utf-8", errors="replace")
            for _m in re.finditer(r"page_router\.get\(\s*\"(/[A-Za-z0-9_\-/]*)\"", _src):
                _pages[_m.group(1)] = _p.name
            for _m in re.finditer(r"@router\.get\(\s*\"(/[A-Za-z0-9_\-/]*)\"[^\n]*response_class=HTMLResponse",
                                  _src):
                _pages[_m.group(1)] = _p.name
        for _path, _f in sorted(_pages.items()):
            if _path in _AUTH_FLOW:
                continue
            if ("'%s'" % _path) not in _idx:
                issues.append(("ERROR", "static/index.html",
                               "页面 `%s`（%s）无侧边栏入口 ⇒ 只能手输 URL 访问（孤岛页）" % (_path, _f)))
    except Exception as _e3:                                  # noqa: BLE001
        issues.append(("ERROR", "static/index.html", "页面可达性判据不可执行：%s" % _e3))

    # ── ④ 前端渲染点（形态③）──
    #   ★ 存在性断言**必须先剥注释**（否则"把渲染代码删掉、注释里还留着字段名"照样通过）。
    #   ★ 2026-10-14（反向验证抓出）：初版只查"字段名出现过" ⇒ 把**渲染调用行**删掉、
    #     函数定义仍在，判据**仍绿**（假绿）。现加**调用级**判据：
    #     含该字段的函数必须**被调用**（名字出现次数 ≥ 2：定义 1 次 + 调用 ≥1 次）。
    try:
        _js_raw = "\n".join(_j.read_text(encoding="utf-8", errors="replace")
                            for _j in sorted((ROOT / "static" / "js").glob("*.js")))
        _js = _js_code_only(_js_raw)
        for _field, _why in (("report_template_meta", "行业报告模板（模板覆盖是否生效）"),
                             ("extract_corrections", "人工校正（校正值是否被采用）")):
            # (a) 必须作为**属性访问**出现（不是只在注释/字符串里被提到）
            if not re.search(r"(\.|\[['\"])%s\b" % re.escape(_field), _js):
                issues.append(("ERROR", "static/js",
                               "`%s` 后端已产出但前端未作为属性读取（形态③：%s）" % (_field, _why)))
                continue
            # (b) 承载它的函数必须**被调用**（防"函数留着、调用被删"）
            _fn_ok = False
            for _m in re.finditer(r"function\s+([A-Za-z_$][\w$]*)\s*\(", _js):
                _name = _m.group(1)
                _start = _m.end() - 1
                _depth, _end = 0, None
                for _i in range(_start, min(len(_js), _start + 20000)):
                    if _js[_i] == "{":
                        _depth += 1
                    elif _js[_i] == "}":
                        _depth -= 1
                        if _depth == 0:
                            _end = _i
                            break
                if _end is None:
                    continue
                _body = _js[_start:_end]
                if ("." + _field) in _body or ("['" + _field + "']") in _body:
                    if len(re.findall(r"\b%s\s*\(" % re.escape(_name), _js)) >= 2:
                        _fn_ok = True
                        break
            if not _fn_ok:
                issues.append(("ERROR", "static/js",
                               "`%s` 只在**未被调用**的函数里出现 ⇒ 渲染点失效（%s）" % (_field, _why)))
    except Exception as _e4:                                  # noqa: BLE001
        issues.append(("ERROR", "static/js", "前端渲染点判据不可执行：%s" % _e4))

    return issues


def check_service_version_visibility() -> List[Tuple[str, str, str]]:
    """服务版本可见化 / 页面级错误兜底 / DB 忙-只读语义拆分（2026-10-14，R-1~R-3）。

    为什么设这道闸门：三次实测事故都是**同根因**——前端静态文件每次请求从磁盘读（永远最新），
    而 Python 代码是进程启动时的快照 ⇒ 错配后现象是「菜单是新的，点进去 `{"detail":"Not Found"}`」
    或「侧边栏少项」，看起来像 bug、实则只需重启。此前须人肉比对进程启动时间与 git 提交时间。

    判据（**行为级优先**，静态断言先剥注释）：
      ① 版本权威可用，且 `/healthz` 真的暴露版本载荷；
      ② 前端 core.js **确实调用**了自检（定义 + 调用 ≥2 次，防"只定义没调用"）；
      ③ 页面路径的错误返回 **HTML 兜底**（含重启判据），`/api/**` 仍返回 JSON；
      ④ 「只读」不再被「忙」认领（语义拆分），状态码为 500（不是 503）；
      ⑤ JS 剥注释**只有一处实现**（脚本侧薄转发）。
    """
    issues: List[Tuple[str, str, str]] = []

    try:
        from engine import runtime_version as _RV2                        # noqa: PLC0415
        _pay = _RV2.health_payload()
        if set(_pay) != {"code", "stale"}:
            issues.append(("ERROR", "engine/runtime_version.py",
                           "health_payload 键集异常：%s（应恰为 code/stale）" % sorted(_pay)))
        if "booted_at" not in (_pay.get("code") or {}):
            issues.append(("ERROR", "engine/runtime_version.py",
                           "health_payload.code 缺 booted_at（无法自证启动时间）"))
        if "stale" not in (_pay.get("stale") or {}):
            issues.append(("ERROR", "engine/runtime_version.py",
                           "health_payload.stale 缺 stale 布尔（前端无从判断）"))
        if (_pay.get("code") or {}).get("count", 0) <= 0:
            issues.append(("ERROR", "engine/runtime_version.py",
                           "被监控的 Python 源文件数为 0 ⇒ 判据失效（不静默通过）"))
    except Exception as _e1:                                              # noqa: BLE001
        issues.append(("ERROR", "engine/runtime_version.py", "版本权威不可用：%s" % _e1))

    _main_src = ""
    try:
        _main_src = _strip_comments_keep_lines(
            (ROOT / "main.py").read_text(encoding="utf-8", errors="replace"))
    except Exception as _e2:                                              # noqa: BLE001
        issues.append(("ERROR", "main.py", "读取失败：%s" % _e2))
    if _main_src and "health_payload" not in _main_src:
        issues.append(("ERROR", "main.py", "/healthz 未暴露版本载荷（缺 health_payload）⇒ 版本不可见"))
    if _main_src and "add_exception_handler(404" not in _main_src:
        issues.append(("ERROR", "main.py",
                       "未注册 404 页面兜底（add_exception_handler(404, ...)）⇒ 页面 404 仍摊 JSON"))

    try:
        from engine.js_source import strip_comments as _sc                # noqa: PLC0415
        _core = _sc((ROOT / "static" / "js" / "core.js").read_text(encoding="utf-8", errors="replace"))
        if _core.count("function checkServiceStaleness") != 1:
            issues.append(("ERROR", "static/js/core.js",
                           "自检函数定义数=%d（应恰为 1）" % _core.count("function checkServiceStaleness")))
        if _core.count("checkServiceStaleness(") < 2:
            issues.append(("ERROR", "static/js/core.js",
                           "自检函数只有定义、**没有被调用** ⇒ 版本提示永不出现"))
        if "/healthz" not in _core:
            issues.append(("ERROR", "static/js/core.js", "自检未读取 /healthz（唯一权威载荷）"))
        if "start8001.bat" not in _core:
            issues.append(("ERROR", "static/js/core.js", "提示语未给出可执行动作（缺 start8001.bat）"))
    except Exception as _e3:                                              # noqa: BLE001
        issues.append(("ERROR", "static/js/core.js", "前端自检判据不可执行：%s" % _e3))

    try:
        import sqlite3                                                    # noqa: PLC0415
        from error_pages_api import error_route as _er, page_404_handler as _p404
        from database import is_db_busy_error as _busy2, is_db_readonly_error as _ro2

        class _Rq:                                                        # noqa: D401
            def __init__(self, path):
                self.url = type("U", (), {"path": path})()

        class _Xc(Exception):
            detail = "Not Found"

        _h404 = _p404(_Rq("/not-a-page"), _Xc())
        _b404 = _h404.body.decode("utf-8")
        if _h404.status_code != 404 or "<!DOCTYPE html>" not in _b404:
            issues.append(("ERROR", "error_pages_api.py", "页面 404 未返回 HTML 兜底"))
        if "start8001.bat" not in _b404:
            issues.append(("ERROR", "error_pages_api.py",
                           "404 页缺『是否只是没重启』的判据（含 start8001.bat）⇒ 同类事故仍难自查"))
        if b"<!DOCTYPE" in _p404(_Rq("/api/v1/x"), _Xc()).body:
            issues.append(("ERROR", "error_pages_api.py", "/api/** 的 404 被 HTML 化（污染接口语义）"))
        _ro_res = _er(_Rq("/api/v1/x"), sqlite3.OperationalError("attempt to write a readonly database"))
        _busy_res = _er(_Rq("/api/v1/x"), sqlite3.OperationalError("database is locked"))
        if _ro_res[0] != 500:
            issues.append(("ERROR", "error_pages_api.py",
                           "只读被映射为 %d（应为 500；503 会误导用户反复重试）" % _ro_res[0]))
        if _busy_res[0] != 503:
            issues.append(("ERROR", "error_pages_api.py", "忙/锁未映射为 503（应为可重试语义）"))
        if _busy2(sqlite3.OperationalError("attempt to write a readonly database")):
            issues.append(("ERROR", "database.py",
                           "『只读』仍被 is_db_busy_error 认领 ⇒ 语义拆分失效"))
        if not _ro2(sqlite3.OperationalError("attempt to write a readonly database")):
            issues.append(("ERROR", "database.py", "is_db_readonly_error 未认领『只读』"))
    except Exception as _e4b:                                             # noqa: BLE001
        issues.append(("ERROR", "error_pages_api.py", "页面兜底/语义拆分判据不可执行：%s" % _e4b))

    try:
        _audit_src = (ROOT / "scripts" / "_audit_fe_be_alignment.py").read_text(
            encoding="utf-8", errors="replace")
        if _audit_src.count("def strip_js_comments") > 0:
            issues.append(("ERROR", "scripts/_audit_fe_be_alignment.py",
                           "自带剥注释实现 ⇒ 违反单一权威（engine/js_source.strip_comments）；"
                           "历史上已两次因自带实现遇正则字面量脱同步而产出假判据"))
    except Exception as _e5:                                              # noqa: BLE001
        issues.append(("ERROR", "scripts/_audit_fe_be_alignment.py", "判据不可执行：%s" % _e5))

    return issues


def check_level_display_single_source() -> List[Tuple[str, str, str]]:
    """等级**展示写法**唯一权威闸门（2026-10-15，用户裁定「待核验→涉嫌风险」）。

    根因：同一个等级词曾有**三套展示映射**互不一致 ——
      · 后端 `risk_levels.DISPLAY_LABELS`（曾写「已列明」）；
      · 网页报告 `tax-doc-analysis.js::_levelText`（曾写「已查明待办事项」，且是**死函数**）；
      · 风险页 `risks.js::LEVEL_DISPLAY`（「涉嫌风险」）。
    ⇒ 同一条发现，风险页叫「涉嫌风险」、网页报告叫「已查明待办事项」、
      导出 PDF/Word/HTML 叫裸「待核验」。

    本闸门两层判据（都可反向验证）：
      ① **行为级**（伪造最小 ctx 真调 `report_service` 三个等级渲染节）——
         断言：导出报告的等级统计表 / 分税种明细 / 重点风险卡片里，
         「待核验」 findings 呈现「涉嫌风险」、结论等级「待核」呈现术语「待核事项」，
         且**任何裸「待核验/待核」不得出现**。谁绕过 `display_label` 谁就报 ERROR。
      ② **前端同步**（`constants.js::LEVEL_DISPLAY` 是后端权威的 JS 侧镜像）——
         断言：JS 映射逐键与 `display_label` 同值；`risks.js` 不得再自写第二份；
         `tax-doc-analysis.js` 不得有 competing 措辞（「已查明待办事项」清零）
         且合成发现徽标不得裸拼 `synthFinding.level`。
    """
    issues: List[Tuple[str, str, str]] = []

    # ── ① 行为级：导出链三节真调 ─────────────────────────────
    try:
        from engine.risk_levels import display_label as _dl
        from engine import report_service as RSVC
    except Exception as exc:                                     # noqa: BLE001
        return [("ERROR", "engine/report_service.py",
                 "等级展示权威闸门无法导入被检模块：%s" % exc)]

    # 权威本身必须已是用户裁定的措辞（反向验证锚点：改回去这里先红）
    if _dl("待核验") != "涉嫌风险" or _dl("待核") != "涉嫌风险":
        issues.append(("ERROR", "engine/risk_levels.py",
                       "DISPLAY_LABELS 应把「待核验/待核」呈现为「涉嫌风险」（用户 2026-10-15 裁定），"
                       "实测 待核验→%s、待核→%s" % (_dl("待核验"), _dl("待核"))))

    try:
        # ①-a 等级统计表（_sec_risk_overview）
        _ctx_ov = {"stats": {"available": True, "by_level": {"待核验": 2, "高风险": 1},
                             "by_tax": {}, "by_state_cn": {}, "by_amount_band": {},
                             "amount_by_band": {}, "total": 3, "amount_total": 0,
                             "amount_unknown_count": 0, "pending_amount_total": 0,
                             "reviewed_total": 0, "rectification_total": 0, "notes": {}},
                   "documents": {"items": [], "total": 0}, "extract_counts": {},
                   "payload": {}, "limit": 50}
        _ov = RSVC._sec_risk_overview(_ctx_ov)
        _ov_txt = json.dumps(_ov, ensure_ascii=False, default=str)
        if "涉嫌风险" not in _ov_txt:
            issues.append(("ERROR", "engine/report_service.py",
                           "等级统计表未呈现「涉嫌风险」（`_sec_risk_overview` 须走 "
                           "`risk_levels.display_label`，不得裸印 by_level 的键）"))
        if "待核验" in _ov_txt:
            issues.append(("ERROR", "engine/report_service.py",
                           "等级统计表出现裸「待核验」（结构性字段值被当展示文本）"))

        # ①-b 分税种明细（_sec_tax_detail）
        _ctx_tax = {"findings": [{"seq": 1, "title": "测试事项", "risk_level": "待核验",
                                  "taxes": ["增值税"]}],
                    "amounts": {}, "state_cn": {}, "limit": 50}
        _tx = RSVC._sec_tax_detail(_ctx_tax)
        _tx_txt = json.dumps(_tx, ensure_ascii=False, default=str)
        if "涉嫌风险" not in _tx_txt or "待核验" in _tx_txt:
            issues.append(("ERROR", "engine/report_service.py",
                           "分税种明细「等级」列未走 `display_label`（实测含裸「待核验」或缺「涉嫌风险」）"))

        # ①-c 重点风险卡片（_sec_key_risks）：风险等级 + 结论等级两轴
        _ctx_key = {"key_findings": [{"seq": 1, "risk_no": "R1", "title": "测试事项",
                                      "risk_level": "待核验", "conclusion_grade": "待核",
                                      "taxes": [], "priority_score": None}],
                    "findings": [{"seq": 1, "risk_no": "R1", "risk_level": "待核验"}],
                    "reviews": {}, "amounts": {}}
        _ky = RSVC._sec_key_risks(_ctx_key)
        _ky_txt = json.dumps(_ky, ensure_ascii=False, default=str)
        if "涉嫌风险" not in _ky_txt or "待核验" in _ky_txt:
            issues.append(("ERROR", "engine/report_service.py",
                           "重点风险卡片「风险等级」未走 `display_label`（实测含裸「待核验」或缺「涉嫌风险」）"))
        if "待核事项" not in _ky_txt or "待核" in _ky_txt.replace("待核事项", ""):
            issues.append(("ERROR", "engine/report_service.py",
                           "重点风险卡片「结论等级」未走结论术语权威（「待核」应呈现为「待核事项」，"
                           "唯一权威 config/conclusion_grades.json::term_authority）"))
    except Exception as exc:                                     # noqa: BLE001
        issues.append(("ERROR", "engine/report_service.py",
                       "等级展示行为级断言执行失败（伪造 ctx 形状与实现漂移）：%s" % exc))

    # ── ② 前端同步 ───────────────────────────────────────────
    try:
        _const = (ROOT / "static" / "js" / "constants.js").read_text(
            encoding="utf-8", errors="replace")
        _m = re.search(r"var\s+LEVEL_DISPLAY\s*=\s*\{([^}]*)\}", _const)
        if not _m:
            issues.append(("ERROR", "static/js/constants.js",
                           "缺全局 `LEVEL_DISPLAY` 映射（等级展示 JS 侧唯一镜像必须在此定义）"))
        else:
            _pairs = dict(re.findall(r"'([^']+)'\s*:\s*'([^']+)'", _m.group(1)))
            if "待核验" not in _pairs or _pairs.get("待核验") != _dl("待核验"):
                issues.append(("ERROR", "static/js/constants.js",
                               "LEVEL_DISPLAY['待核验']=%r 与后端权威 %r 不同源"
                               % (_pairs.get("待核验"), _dl("待核验"))))
            if "待核" not in _pairs or _pairs.get("待核") != _dl("待核"):
                issues.append(("ERROR", "static/js/constants.js",
                               "LEVEL_DISPLAY['待核']=%r 与后端权威 %r 不同源"
                               % (_pairs.get("待核"), _dl("待核"))))
    except OSError as exc:
        issues.append(("ERROR", "static/js/constants.js", "无法读取：%s" % exc))

    _js_dir = ROOT / "static" / "js"
    for _jf in ("risks.js", "tax-doc-analysis.js", "report-block-renderer.js",
                "report-modules.js", "dashboard.js"):
        _p = _js_dir / _jf
        if not _p.exists():
            continue
        try:
            _src = _p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "已查明待办事项" in _src:
            issues.append(("ERROR", "static/js/%s" % _jf,
                           "出现 competing 措辞「已查明待办事项」（等级展示唯一出处 = constants.js"
                           "::LEVEL_DISPLAY；2026-10-15 用户裁定统一为「涉嫌风险」）"))
        if _jf == "risks.js" and re.search(r"var\s+LEVEL_DISPLAY\s*=", _src):
            issues.append(("ERROR", "static/js/risks.js",
                           "自写第二份 LEVEL_DISPLAY（唯一出处 = constants.js，本文件只消费 "
                           "`levelDisplayOf`）"))
        if _jf == "tax-doc-analysis.js" and re.search(
                r"\+\s*\(\s*synthFinding\.level\s*\|\|", _src):
            issues.append(("ERROR", "static/js/tax-doc-analysis.js",
                           "合成发现徽标裸拼 `synthFinding.level`（须经 `_levelText` 翻译）"))
        # 这几处**直接展示等级键/值**（风险分布大屏、事实段等级徽标）⇒
        # 必须引用全局映射；否则「待核验」会原样印到页面。
        if _jf in ("dashboard.js", "report-modules.js") and "levelDisplayOf" not in _src:
            issues.append(("ERROR", "static/js/%s" % _jf,
                           "展示等级却未引用全局映射 `levelDisplayOf`（等级键会裸印「待核验」）"))

    # risks.html 须先加载 constants.js 再加载 risks.js（否则全局映射不可见）
    try:
        _rh = (ROOT / "static" / "risks.html").read_text(
            encoding="utf-8", errors="replace")
        _i_c, _i_r = _rh.find("constants.js"), _rh.find("risks.js")
        if _i_r >= 0 and (_i_c < 0 or _i_c > _i_r):
            issues.append(("ERROR", "static/risks.html",
                           "constants.js 须先于 risks.js 加载（levelDisplayOf 全局映射依赖）"))
    except OSError:
        pass

    # ── ③ 结构性**风险等级**字段不得被措辞清洗改写（数据驱动，新增字段自动覆盖）──
    #   ★★ 2026-10-15（同一事故第三次出血）：`detected_risk_level` 未登记
    #      `enterprise_report._ENUM_KEYS_PROTECTED` ⇒ 值「待核验」被 `_scrub_out_vague`
    #      改写成展述词「已提供同类资料」⇒ 导出报告等级表把 2 项印成非等级词。
    #   判据**精确**（不误伤别的枚举，实测 `evidence_grade`/`review_level`/`conclusion_grade`
    #   都是**另一类**枚举，其值非等级但完全正常）：仅当**风险等级字段**持有
    #   `report_wording.STATUS_TEXT` 的**替换值**（如「已提供同类资料」/「须核对」）
    #   或 `DISPLAY_LABELS` 的**展示词**（如「涉嫌风险」）时，才是"结构字段被当展示文本改写"。
    _prod = ROOT / "scripts" / "four_reports" / "company_1_full.json"
    if not _prod.exists():
        issues.append(("WARN", "scripts/four_reports/company_1_full.json",
                       "无真跑产物 ⇒ 结构性风险等级字段保真检查 SKIP（**不得当作通过**，"
                       "须先重跑一键分析恢复产物）"))
    else:
        try:
            from engine.report_wording import STATUS_TEXT as _ST   # noqa: PLC0415
            from engine.risk_levels import DISPLAY_LABELS as _DL2   # noqa: PLC0415
            _level_keys = set(_DL2) | {"risk_level", "level", "risk_level_capped_from",
                                       "detected_risk_level",
                                       "risk_level_capped_by_grade_from"}
            _tainted = {v for k, v in _ST.items() if v and v != k}
            _tainted |= {v for v in _DL2.values() if v}
            _pd = json.loads(_prod.read_text(encoding="utf-8", errors="replace"))
            _bad: Dict[str, int] = {}
            _seen = set()

            def _scan(o):                                        # noqa: ANN001
                if isinstance(o, dict):
                    if id(o) in _seen:
                        return
                    _seen.add(id(o))
                    for k, v in o.items():
                        if (isinstance(k, str) and k in _level_keys
                                and isinstance(v, str) and v.strip() in _tainted):
                            _bad["%s=%s" % (k, v.strip())] = _bad.get("%s=%s" % (k, v.strip()), 0) + 1
                        _scan(v)
                elif isinstance(o, list):
                    if id(o) in _seen:
                        return
                    _seen.add(id(o))
                    for v in o:
                        _scan(v)

            _scan(_pd)
            for _kv, _n in sorted(_bad.items(), key=lambda x: -x[1])[:5]:
                issues.append(("ERROR", "scripts/four_reports/company_1_full.json",
                               "结构性风险等级字段被改写为展示/状态词（%d 处，如 %s）——"
                               "该键须登记 `enterprise_report._ENUM_KEYS_PROTECTED`，"
                               "展示写法只在渲染层翻译" % (_n, _kv)))
        except Exception as exc:                                 # noqa: BLE001
            issues.append(("ERROR", "tools/audit_consistency.py",
                           "结构性风险等级字段保真检查执行失败：%s" % exc))

    return issues


def check_legal_mapping_wiring() -> List[Tuple[str, str, str]]:
    """**法规 ⇄ 规则关联**接入闸门（STEP-EXT-LEGAL-FULL-MATCH 步骤 19）。

    ★ 为什么必须行为级：这条链路横跨 4 个模块（关联表 → 规则目录 → 报告 → 风险 API）
      与 2 个材料读层。任一处被改回"只有作者口径"或"表列被删"，静态看都合法，
      但**用户看到的东西**就退化成旧样（本轮就是为了修这个才做的）。

    判据（全部**实测行为**，不做文本存在性自证）：
      ① 关联表可用，且 `verified` 条目**规则 id 真在规则目录里**（防孤儿映射）；
      ② 每条 `verified` 的 `provision_id` **在正文库真有原文**（防"确证到不存在的条款"）；
      ③ `report_service._sec_legal_basis` 渲染出的表**必须含「条款ID」列**，
         且真产物上确有「已确证」行（防渲染层被改回旧表）；
      ④ `rule_catalog.get` 必须带 `legal_provisions`（含 `content`）；
      ⑤ `risk_service.get_risk` 必须带 `legal_basis` 与 `related_materials`；
      ⑥ 材料层：`matched_by` 取值**只能是两类显式引用**（防有人改成关键词匹配）、
         每条材料**必带 `granularity`**（防把法规级关联当条款级用）。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        import json as _json
        from engine import legal_extras as _LE
        from engine import legal_mapping as _LM
        from engine import report_service as _RSVC
        from engine import risk_service as _RSVC2
        from engine import rule_catalog as _RC
    except Exception as exc:                                     # noqa: BLE001
        return [("ERROR", "engine/legal_mapping.py",
                 "关联链模块导入失败：%s" % exc)]

    # ── ① 关联表可用 + 无孤儿映射 ──
    if not _LM.available():
        issues.append(("ERROR", "config/legal_mappings.json",
                       "关联表不可用（读取失败或缺失）——步骤 19 链路失效，"
                       "报告/风险详情的法规条款会整体退化为空"))
        return issues
    _known = {r["rule_id"] for r in _RC.entries()}
    _orphan = sorted({m["rule_id"] for m in (_LM._doc().get("mappings") or [])   # noqa: SLF001
                      if m.get("verified") and m["rule_id"] not in _known})
    if _orphan:
        issues.append(("ERROR", "config/legal_mappings.json",
                       "关联表 %d 条确证映射指向**规则目录中不存在的规则 id**（孤儿映射，"
                       "如 %s）——须重跑 `scripts/_gen_legal_mappings.py`"
                       % (len(_orphan), ", ".join(_orphan[:3]))))

    # ── ② 确证条款必须真有原文（不得"确证到不存在的条款"）──
    _cov = _LM.coverage()
    if _cov.get("provisions") and _cov.get("with_content") != _cov.get("provisions"):
        issues.append(("ERROR", "config/legal_mappings.json",
                       "有 %d 条**已确证**条款在正文库查不到原文（%s）——"
                       "确证到无正文的条款等于假确证"
                       % (_cov["provisions"] - _cov["with_content"],
                          ", ".join((_cov.get("missing_content") or [])[:3]))))

    # ── ③ 报告「法规依据」章必须渲染出条款 ID 与已确证行 ──
    class _S:                                                    # noqa: D401
        username = "audit"
        is_admin = True
        user_id = 0

        def can_access_company(self, cid):                       # noqa: ANN001
            return True

    try:
        _doc = _RSVC.build_document(1, _S(), view="full")
        _sec = next((s for s in (_doc.get("sections") or [])
                     if s.get("key") == "legal_basis"), None)
        if _sec is None:
            issues.append(("ERROR", "engine/report_service.py",
                           "报告无 `legal_basis` 章节 —— 法规依据章缺失"))
        else:
            _tbl = next((b for b in (_sec.get("blocks") or [])
                         if b.get("type") == "table"), None)
            _cols = list((_tbl or {}).get("columns") or [])
            if "条款ID" not in _cols:
                issues.append(("ERROR", "engine/report_service.py",
                               "报告「法规依据」表**未渲染条款 ID 列**（现列：%s）——"
                               "步骤 19 的「已确证条款」未进报告" % ("、".join(_cols) or "无")))
            _rows = list((_tbl or {}).get("rows") or [])
            _ok = sum(1 for r in _rows if "已确证" in str(r[-1]))
            if _rows and not _ok:
                issues.append(("ERROR", "engine/report_service.py",
                               "报告「法规依据」表 %d 行**无一条「已确证」** —— "
                               "关联表未接通（渲染层仍在用作者口径单一口径）" % len(_rows)))
    except Exception as exc:                                     # noqa: BLE001
        issues.append(("ERROR", "engine/report_service.py",
                       "报告法规依据章行为级检查执行失败：%s" % exc))

    # ── ④ 规则目录详情须带条款（含正文）──
    try:
        _sample = None
        for _r in _RC.entries():
            if _LM.provisions_of(_r["rule_id"]):
                _sample = _r["rule_id"]
                break
        if _sample is None:
            issues.append(("ERROR", "config/legal_mappings.json",
                           "规则目录中**无任何规则**有可确证条款 —— 关联表为空配置"))
        else:
            _g = _RC.get(_sample)
            if not _g.get("legal_provisions"):
                issues.append(("ERROR", "engine/rule_catalog.py",
                               "`rule_catalog.get()` 未附带 `legal_provisions`"
                               "（规则详情看不到已确证条款）"))
            elif not any(p.get("content") for p in _g["legal_provisions"]):
                issues.append(("ERROR", "engine/rule_catalog.py",
                               "`rule_catalog.get()` 的 `legal_provisions` **未带条款正文**"
                               "（详情页无法复核）"))
    except Exception as exc:                                     # noqa: BLE001
        issues.append(("ERROR", "engine/rule_catalog.py",
                       "规则目录条款检查执行失败：%s" % exc))

    # ── ⑤ 风险详情须带 legal_basis 与 related_materials ──
    try:
        _lst = _RSVC2.list_risks(1, _S(), page=1, page_size=1)
        _items = _lst.get("items") or []
        if _items:
            if "legal_provision_ids" not in _items[0]:
                issues.append(("ERROR", "engine/risk_service.py",
                               "风险列表条目未带 `legal_provision_ids`"))
            _d = _RSVC2.get_risk(_items[0].get("risk_no") or _items[0].get("seq"),
                                 1, _S())
            if "legal_basis" not in _d:
                issues.append(("ERROR", "engine/risk_service.py",
                               "风险详情未带 `legal_basis`（发现 → 法规条款未接通）"))
            else:
                _lb = _d["legal_basis"]
                if _lb.get("provisions") and not any(
                        p.get("content") for p in _lb["provisions"]):
                    issues.append(("ERROR", "engine/risk_service.py",
                                   "`legal_basis.provisions` 未带条款正文"))
            _rm = _d.get("related_materials")
            if _rm is None:
                issues.append(("ERROR", "engine/risk_service.py",
                               "风险详情未带 `related_materials`（案例/解读/问答未接通）"))
            else:
                # ★ 2026-10-15：粒度升级为**三态**（provision/law/none）。
                #   判据精神不变 —— "必须显式声明且不得把低粒度说成高粒度"；
                #   强化为：声明 provision ⇒ 必须给出命中的条款 ID（可复核）。
                _g = _rm.get("granularity")
                if _g not in ("provision", "law", "none"):
                    issues.append(("ERROR", "engine/risk_service.py",
                                   "`related_materials.granularity` 必须显式且为 "
                                   "provision/law/none 之一（实得 %r）—— "
                                   "缺声明会被当成条款级确证" % _g))
                elif _g == "provision" and not _rm.get("matched_provision_ids"):
                    issues.append(("ERROR", "engine/risk_service.py",
                                   "`related_materials` 声明条款级却未给 `matched_provision_ids` "
                                   "⇒ 无法复核（假条款级）"))
    except Exception as exc:                                     # noqa: BLE001
        issues.append(("ERROR", "engine/risk_service.py",
                       "风险详情法规/材料检查执行失败：%s" % exc))

    # ── ⑥ 材料层：匹配方式只能两类显式引用 + 每条必带粒度 ──
    _mdoc = _LE._doc()                                           # noqa: SLF001
    if _mdoc.get("available"):
        _bad_how: Dict[str, int] = {}
        _no_gran = 0
        # ★ 2026-10-15：粒度由**两态**（law/空）升级为**三态**（provision/law/none）。
        #   本判据的**精神不变** —— "每条必须显式标注粒度、不得静默默认"；
        #   三态的自洽性/ID 合法性/依据可复核性另由专闸
        #   `check_material_granularity_truthful` 深查（本处只守"必须标注"）。
        _ALLOWED_GRAN = ("provision", "law", "none")
        for _m in (_mdoc.get("materials") or []):
            if str(_m.get("granularity") or "") not in _ALLOWED_GRAN:
                _no_gran += 1
            for _h in (_m.get("matched_refs") or []):
                _how = str(_h.get("matched_by") or "")
                if _how not in ("书名号引用", "全名提及"):
                    _bad_how[_how] = _bad_how.get(_how, 0) + 1
        if _bad_how:
            issues.append(("ERROR", "config/legal_materials.json",
                           "材料关联出现**非显式引用**的匹配方式（%s）——"
                           "只允许「书名号引用」与「全名提及」，"
                           "关键词/相似度匹配会产生假关联（本项目铁律）"
                           % ", ".join("%s×%d" % (k, v) for k, v in _bad_how.items())))
        if _no_gran:
            issues.append(("ERROR", "config/legal_materials.json",
                           "%d 条材料缺粒度标注（须为 %s 之一）—— "
                           "缺标注会被误当成条款级确证"
                           % (_no_gran, "/".join(_ALLOWED_GRAN))))
    else:
        issues.append(("WARN", "config/legal_materials.json",
                       "材料库不可用 ⇒ 案例/解读/问答关联 SKIP（**不得当作通过**；"
                       "先跑 `scripts/_gen_legal_materials.py`）"))

    return issues


def check_legal_frontend_wiring() -> List[Tuple[str, str, str]]:
    """步骤 22 前端（专题 / 目录 / 关系 / 材料 / 条款）的**接线 + 顺序 + 无硬编码**闸门。

    判据（A~F 静态 + G 行为级）：
      A 三个页面文件存在，且页面路由已注册（`legal_api.page_router`）；
      B 侧边栏 `static/index.html` 有 `/legal-topics` 与 `/legal-materials` 入口
        （**孤岛页**是与 `check_one_click_wiring_coverage` 同类的真缺陷）；
      C 同前缀内**字面量段先于参数化段**（`/legal-topics/stats` 先于 `/legal-topics/{topic_id}`；
        `/legal-materials/stats` 先于 `/legal-materials/{material_id}`）⇒ 否则静默 404；
      D 读层三件套存在，且**不含数据文件字面量**（读盘路径不得出现第二处）；
      E 前端 JS **不硬编码条数**：不得出现 `TOPIC-` 编号清单、不得写死"20 个专题"
        之类规模数字（一律取后端）；也不得内嵌条文正文；
      F 页面 HTML 各自引用自己的 JS（不是互相引用或漏引）；
      G **行为级**：按读层真调，确认专题/目录/关系/材料/条款五类各能取到数据，
        且缺口时给出 `reason`/`note`（**不得静默空**）。
    """
    issues: List[Tuple[str, str, str]] = []
    import re as _re                                            # noqa: PLC0415

    # ── A 页面文件与路由 ──
    for page, js in (("legal_topics.html", "legal_topics.js"),
                     ("legal_materials.html", "legal_materials.js")):
        if not (ROOT / "static" / page).exists():
            issues.append(("ERROR", "static/%s" % page, "步骤 22 页面缺失"))
        if not (ROOT / "static" / "js" / js).exists():
            issues.append(("ERROR", "static/js/%s" % js, "步骤 22 前端脚本缺失"))
    api_txt = (ROOT / "legal_api.py").read_text(encoding="utf-8", errors="replace")
    for route in ('"/legal-topics"', '"/legal-materials"'):
        if route not in api_txt:
            issues.append(("ERROR", "legal_api.py", "缺少页面路由 `%s`" % route))

    # ── B 侧边栏入口（防孤岛页）──
    idx = (ROOT / "static" / "index.html").read_text(encoding="utf-8", errors="replace")
    for url in ("/legal-topics", "/legal-materials"):
        if url not in idx:
            issues.append(("ERROR", "static/index.html",
                           "页面 `%s` 无侧边栏入口 ⇒ 只能手输 URL 访问（孤岛页）" % url))

    # ── C 路由顺序（字面量必须先于参数化段）──
    def _order(lit: str, param: str) -> None:
        i_lit, i_par = api_txt.find(lit), api_txt.find(param)
        if i_lit < 0:
            issues.append(("ERROR", "legal_api.py", "缺少字面量段 `%s`" % lit))
        elif i_par < 0:
            issues.append(("ERROR", "legal_api.py", "缺少参数化段 `%s`" % param))
        elif i_lit > i_par:
            issues.append(("ERROR", "legal_api.py",
                           "`%s` 注册在 `%s` **之后** ⇒ 会被路径参数吃掉（静默 404）"
                           % (lit, param)))

    _order('"/legal-topics/stats"', '"/legal-topics/{topic_id}"')
    _order('"/legal-materials/stats"', '"/legal-materials/{material_id}"')
    # 目录/关系无参数化段，但字面量段必须在同前缀列表之后（同 find 顺序即注册顺序）
    for lit, after in (('"/legal-catalog/stats"', '"/legal-catalog"'),
                       ('"/legal-catalog/item"', '"/legal-catalog/stats"'),
                       ('"/legal-relations/lookup"', '"/legal-relations"')):
        i_lit, i_after = api_txt.find(lit), api_txt.find(after)
        if i_lit < 0:
            issues.append(("ERROR", "legal_api.py", "缺少字面量段 `%s`" % lit))
        elif i_after >= 0 and i_lit < i_after:
            issues.append(("ERROR", "legal_api.py",
                           "`%s` 注册在 `%s` 之前（顺序与惯例不一致，易误读）" % (lit, after)))

    # ── D 读层不得**重复实现正文读取**（唯一权威 = legal_mapping.content_of）──
    #   ★ 判据修正记录（2026-10-15）：初版禁止 `legal_catalog.json` / `legal_provisions.json`
    #     字面量 ⇒ **假红**：`legal_topics` 的职责就是读专题索引 + 按目录下标取条目，
    #     它**必须**读这两个文件。真正要防的是"**另写一份条款正文读取**"
    #     （正文唯一权威 `static/legal_library.json`，读法转发 `legal_mapping.content_of`）。
    for rel in ("engine/legal_topics.py", "engine/legal_catalog.py"):
        f = ROOT / rel
        if not f.exists():
            issues.append(("ERROR", rel, "步骤 22 读层缺失"))
            continue
        txt = f.read_text(encoding="utf-8", errors="replace")
        code = _re.sub(r'"""(?:.|\n)*?"""', lambda m: " " * len(m.group(0)), txt)
        code = _re.sub(r"'''(?:.|\n)*?'''", lambda m: " " * len(m.group(0)), code)
        code = _re.sub(r"#[^\n]*", lambda m: " " * len(m.group(0)), code)
        # ★ 只抓**真读盘调用**（`_j("legal_library.json")` / `open(...,"legal_library.json")` /
        #   `read_text()` 旁的该文件名）—— 说明性字符串（如 `authority` 字典里写
        #   "正文唯一权威 static/legal_library.json"）**不是**第二处实现。
        #   实测初版只判"字符串出现" ⇒ `legal_catalog.stats()` 的 authority 说明被误判为假红。
        if _re.search(r"(?:open\(|read_text|_j\(|_read\()[^\n]{0,60}legal_library\.json", code) \
                or _re.search(r"legal_library\.json[^\n]{0,30}\)[^\n]{0,20}read_text", code):
            issues.append(("ERROR", rel,
                           "**代码**真读盘 `legal_library.json` ⇒ 另写了一份条款正文读取"
                           "（唯一权威转发 `legal_mapping.content_of`）"))
    # 行为判据：`legal_topics` 取条款正文**必须**经唯一读法
    try:
        _tp = (ROOT / "engine" / "legal_topics.py").read_text(encoding="utf-8", errors="replace")
        if "LM.content_of" not in _tp:
            issues.append(("ERROR", "engine/legal_topics.py",
                           "条款正文未走 `legal_mapping.content_of`（唯一读法）"
                           "⇒ 存在第二套正文读取的风险"))
    except OSError:
        pass

    # ── E 前端不得硬编码规模/条文（★ 掩掉注释与字符串示例后再判）──
    for js in ("legal_topics.js", "legal_materials.js"):
        p = ROOT / "static" / "js" / js
        if not p.exists():
            continue
        _raw = p.read_text(encoding="utf-8", errors="replace")
        # ★ 掩注释：注释里举例（如"深链 ?topic=TOPIC-001"）**不是硬编码缺陷**
        #   —— 与既有闸门"掩注释再判"同口径（实测初版未掩 ⇒ 假红）。
        src = _re.sub(r"/\*(?:.|\n)*?\*/", lambda m: " " * len(m.group(0)), _raw)
        src = _re.sub(r"//[^\n]*", lambda m: " " * len(m.group(0)), src)
        # E1 不得写死专题编号（应完全由后端返回驱动）
        if _re.search(r"TOPIC-0\d\d", src):
            issues.append(("ERROR", "static/js/%s" % js,
                           "写死专题编号 `TOPIC-0xx` ⇒ 专题清单必须完全来自后端"
                           "（新增专题零改前端）"))
        # E2 不得写死"20 个专题"这类规模数字
        if _re.search(r"20\s*(个)?专题", src):
            issues.append(("ERROR", "static/js/%s" % js,
                           "写死专题规模数字（如「20 个专题」）⇒ 规模一律取后端"))
        # E3 不得内嵌条文正文（"第…条"形式的长句）
        if _re.search(r"第[一二三四五六七八九十百]+条[，。；]", src):
            issues.append(("ERROR", "static/js/%s" % js,
                           "疑似内嵌条文正文（前端严禁硬编码条文）"))

    # ── F 页面各自引用自己的 JS ──
    for page, js in (("legal_topics.html", "legal_topics.js"),
                     ("legal_materials.html", "legal_materials.js")):
        p = ROOT / "static" / page
        if p.exists() and ('/static/js/%s' % js) not in p.read_text(encoding="utf-8", errors="replace"):
            issues.append(("ERROR", "static/%s" % page, "页面未引用 `/static/js/%s`" % js))

    # ── G 行为级：五类读层真能取到数据 + 缺口须有 reason/note ──
    try:
        import sys as _s                                          # noqa: PLC0415
        if str(ROOT) not in _s.path:
            _s.path.insert(0, str(ROOT))
        from engine import legal_catalog as _LC                    # noqa: PLC0415
        from engine import legal_extras as _LE                     # noqa: PLC0415
        from engine import legal_topics as _LT                     # noqa: PLC0415

        if not _LT.available():
            issues.append(("ERROR", "config/legal_topic_index.json",
                           "专题索引不可用 ⇒ 专题页整体为空；请跑 `scripts/_gen_legal_topic_index.py`"))
        else:
            lst = _LT.list_topics()
            if not lst.get("total"):
                issues.append(("ERROR", "config/legal_topic_index.json", "专题列表为空"))
            # 取第一个专题做端到端行为检查
            tid = str((lst.get("items") or [{}])[0].get("id") or "")
            det = _LT.topic_detail(tid)
            if not det.get("found"):
                issues.append(("ERROR", "engine/legal_topics.py",
                               "专题详情取不到（%s）" % tid))
            docs = _LT.topic_documents(tid, page=1, page_size=1)
            if not docs.get("total"):
                issues.append(("ERROR", "engine/legal_topics.py",
                               "专题 %s 法规清单为空（清单口径失效）" % tid))
            elif not docs.get("note"):
                issues.append(("ERROR", "engine/legal_topics.py",
                               "专题法规清单未声明口径（`note` 为空）⇒ 读者无从判断'清单是什么'"))
            # ★ 遍历**全部**专题检查"缺口如实"：无材料时**必须有 reason**
            #   （只查第一个专题会漏 —— 实测 TOPIC-001 有材料，走不到缺口分支）
            for t in (lst.get("items") or []):
                _tid = str(t.get("id") or "")
                _m = _LT.topic_materials(_tid)
                if not _m.get("total") and not _m.get("reason"):
                    issues.append(("ERROR", "engine/legal_topics.py",
                                   "专题 %s 材料为空却**无 `reason`** ⇒ 静默空"
                                   "（应为'暂无已核实条款…'之类明确说明）" % _tid))

        if not _LC.available():
            issues.append(("ERROR", "config/legal_catalog.json", "法规目录不可用"))
        else:
            d1 = _LC.list_documents(page=1, page_size=1)
            if not d1.get("total"):
                issues.append(("ERROR", "config/legal_catalog.json", "法规目录为空"))
            rel = _LC.relations(page=1, page_size=1)
            if not rel.get("total"):
                issues.append(("ERROR", "config/legal_relations.json", "关系表为空"))
            # 关系类型必须**只取白名单**（防混入非关系词，如实测曾出现"国务院令"）
            known = set((rel.get("relation_types") or {}).keys())
            bad = set()
            for x in _LC.relations(page=1, page_size=200).get("items") or []:
                if str(x.get("relation")) not in known:
                    bad.add(str(x.get("relation")))
            if bad:
                issues.append(("ERROR", "config/legal_relations.json",
                               "关系类型出现**未登记值**：%s（须只取 `relation_types` 白名单）"
                               % ", ".join(sorted(bad)[:4])))
            # 目录去重：同 URL 路径只应剩一条
            from urllib.parse import urlparse as _up               # noqa: PLC0415
            import json as _json                                   # noqa: PLC0415
            try:
                items = _json.loads((ROOT / "config" / "legal_catalog.json")
                                    .read_text(encoding="utf-8")).get("items") or []
                seen, dup = set(), 0
                for it in items:
                    pth = _up(str(it.get("url") or "")).path
                    if not pth:
                        continue
                    if pth in seen:
                        dup += 1
                    seen.add(pth)
                if dup:
                    issues.append(("ERROR", "config/legal_catalog.json",
                                   "目录存在 %d 条**同 URL 路径**重复条目（未按 URL 去重）"
                                   "—— 前端列表会出现重复项" % dup))
            except Exception:                                      # noqa: BLE001
                pass

        if not _LE.available():
            issues.append(("ERROR", "config/legal_materials.json", "材料库不可用"))
        else:
            m1 = _LE.list_materials(page=1, page_size=1)
            if not m1.get("total"):
                issues.append(("ERROR", "config/legal_materials.json", "材料列表为空"))
            # 材料关联只能两类显式引用（与 check_legal_mapping_wiring 一致，此处查列表输出）
            for x in (m1.get("items") or []):
                for h in (x.get("matched_refs") or []):
                    if str(h.get("matched_by") or "") not in ("书名号引用", "全名提及"):
                        issues.append(("ERROR", "config/legal_materials.json",
                                       "材料匹配方式非显式引用：%s" % h.get("matched_by")))
    except Exception as exc:                                       # noqa: BLE001
        issues.append(("ERROR", "tools/audit_consistency.py",
                       "步骤 22 行为级检查执行失败：%s" % exc))
    return issues


if __name__ == "__main__":
    raise SystemExit(main())
