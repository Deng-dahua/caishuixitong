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
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

    # ③ 全量不变式：全量红线 × 全部证据项，凡判「已有」必有逐字依据
    try:
        for rl in all_redlines():
            ev = build_evidence_chain({"type": "probe"}, rl, avail)
            for e in ev.get("elements", []):
                if e.get("status") != "已有":
                    continue
                name = e.get("name", "")
                det = e.get("matched_detail") or []
                if not any(d.get("form") and (d["form"] in name or name in d["form"])
                           for d in det):
                    issues.append(("ERROR", "engine/evidence_chain.py",
                                   f"红线 {rl.get('id')} 的「{name}」被判「已有」"
                                   f"但命中称谓不在证据项名中：{det}"))
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
        for text in ("纳税人名称（公章）：深圳海更数字传媒有限公司",
                     "纳税人名称（公章）深圳海更数字传媒有限公司"):
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
    # 这些名字允许跨模块存在「真实分歧」（各自独立实现、签名/语义不同，并非同一概念）：
    #   _fmt          —— 各模块私有格式化助手，签名与用途不同（千分位 / 2位小数 / 指标百分比），
    #                   非"同一格式化函数"的多头实现，收敛反而会破坏各自语义。
    #   _norm         —— 各模块私有归一化助手，用途不同（长度保持归一化 vs 去空白），非同一概念。
    #   parse_threshold —— 各模块私有阈值解析，输入形态不同（自由文本 vs 结构化字段），非同一概念。
    # 新增同名真实分歧若不在本表 → 仍报 WARN，强制人工确认是否该收敛（防复发）。
    _DIVERGENCE_OK = {"_fmt", "_norm", "parse_threshold"}
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

    def _is_stub(name: str, rel: str) -> bool:
        """转发桩判定（AST 版，稳健）：体内有 `from engine... import ... as ...` 且
        去掉 docstring / import 后**剩余语句 ≤6 条**（即没有实质实现逻辑）。

        早期版本用"恰好 1 条 return"判据，会把无返回值的副作用型转发（如
        `_infer_industry_from_goods` 只做赋值 + 调一个加载函数）误判成真实实现。
        """
        try:
            for n in _ast.parse(srcs[rel]).body:
                if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef)) and n.name == name:
                    has_imp = any(
                        isinstance(st, _ast.ImportFrom) and (st.module or "").startswith("engine")
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
            continue                       # 完全一致的重复 → 也提示
        if all(_is_stub(name, rel) for rel in files):
            continue                       # 均为转发桩 → 已收敛
        real_divergent.append((name, files))
        if name in _MUST_BE_SINGLE:
            issues.append(("ERROR", files[0],
                           f"{name} 在 {len(files)} 个模块各有**真实实现**（应统一为单来源转发）：{files}"))

    if real_divergent:
        names = [n for n, _ in real_divergent]
        issues.append(("WARN", "engine/",
                       f"仍有 {len(real_divergent)} 组跨模块**真实分歧**（非转发桩），"
                       f"请确认是否属同一概念、能否收敛：{names[:10]}"))
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

        # 等级词表必须与 pipeline 的权威 _sev 逐字一致（防漂移）
        _pipe_src = _read_rel("engine/pipeline.py")
        if "_sev = {" in _pipe_src:
            for _lv in SEVERITY_LEVELS:
                if f'"{_lv}":' not in _pipe_src:
                    issues.append(("ERROR", "engine/pipeline.py",
                                   f"权威等级词表漂移：pipeline 的 _sev 缺少「{_lv}」"))
        elif len(_pipe_src) > 5000:
            issues.append(("ERROR", "engine/pipeline.py",
                           "未找到权威等级词表 _sev（被删除或改名）：等级判定失去权威源"))
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
        from engine.redline_benchmark import benchmark_note
        _note = str((benchmark_note("RL-PAY-001", "广告传媒") or {}).get("text") or "")
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
            if "inspection_overview" in body:
                issues.append(("ERROR", js_rel,
                               "工作底稿版 _buildEnterpriseReadableBody 又渲染了 inspection_overview——"
                               "单章必须只由 overall_conclusion 构成（不得把总述与结论并排贴回）"))
        # ④ 逐条小标签呈现（用户 2026-09-27 要求）
        #   ★ 2026-10-01 用户定调：删除「总—分—总」结构说明等**编排元信息**（与报告本质无关），
        #     故此处只保留「逐条小标签」这一实质呈现要求，不再要求目录结构说明。
        if "_narrativeGroup" not in js:
            issues.append(("ERROR", js_rel,
                           "工作底稿版缺少逐条小标签呈现（_narrativeGroup）"))

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
    for lvl in ("高风险", "中风险", "低风险"):
        n = len([p for p in P if p.startswith(lvl + " ") and "项：" in p])
        if n != 1:
            issues.append(("ERROR", "engine/overall_conclusion.py",
                           "%s 清单标题应只出现一次，实测 %d 次" % (lvl, n)))
    if "待核实事项" in joined:
        issues.append(("ERROR", "engine/overall_conclusion.py",
                       "出现裸「待核实事项」（应写「涉嫌风险事项」；涉嫌已含待核实，不再叠加）"))
    return issues


def check_conclusion_and_suspicion_order() -> List[Tuple[str, str, str]]:
    """★★ 2026-10-02（用户定调：一定是先说重要的信息）：**结论先行 + 重风险在前** 的不变式。

    两条硬要求（都出过事故，必须锁死）：
      ① 第一章总述**第一段结论**（企业整体风险综合评价）必须排在「检查范围与结果概览」之前；
         监管态度分级条款必须按 **重点关注(高) → 补证核实(中) → 待核验 → 限期补正资料 →
         提示提醒(低)** 由重到轻排列（原实现低风险排第一句）。
      ② 疑点（confirmed_problems）呈现顺序必须 **极高 → 高 → 中 → 低 → 待核验**，
         由 `engine/enterprise_report.py::_RISK_PRESENT_ORDER` 单一权威控制。

    判据全部是**运行时实测段落下标/条款下标**或源码形态，不做宽泛字符串计数，
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

    # ① 结论先行：综合评价段不得晚于「检查范围与结果概览」
    i_concl, i_overview = _idx("企业整体风险综合评价"), _idx("检查范围与结果概览")
    if i_concl < 0:
        issues.append(("ERROR", "engine/overall_conclusion.py",
                       "总述缺「企业整体风险综合评价」段"))
    elif i_overview < 0:
        issues.append(("ERROR", "engine/overall_conclusion.py",
                       "总述缺「检查范围与结果概览」段"))
    elif i_concl > i_overview:
        issues.append(("ERROR", "engine/overall_conclusion.py",
                       "未结论先行：「企业整体风险综合评价」排在第 %d 段，晚于「检查范围与结果概览」（第 %d 段）"
                       % (i_concl + 1, i_overview + 1)))

    # ② 监管态度分级：由重到轻（关注→补证→待核验→限期→提示）
    i_pos = _idx("监管态度与后续处理建议")
    if i_pos >= 0:
        body = P[i_pos]
        _order = ["重点关注：", "补证核实：", "待核验事项：", "限期补正资料：", "提示提醒："]
        _seen = [(k, body.find(k)) for k in _order]
        _miss = [k for k, v in _seen if v < 0]
        if _miss:
            issues.append(("ERROR", "engine/overall_conclusion.py",
                           "监管态度分级条款缺项：%s" % "、".join(_miss)))
        else:
            _pos_seq = [body.find(k) for k in _order]
            if _pos_seq != sorted(_pos_seq):
                issues.append(("ERROR", "engine/overall_conclusion.py",
                               "监管态度分级条款未按风险由重到轻排列（应为 重点关注→补证核实→"
                               "待核验事项→限期补正资料→提示提醒），实测下标序列 %s" % _pos_seq))

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

    真实事故（深圳海更）：`_online_company_lookup` 把**从经营范围推断**的行业直接写进
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
    #   ★ 已显式登记的「拿得到但不该拿」的缺口（宁留缺口，绝不用硬映射冒充实得）：
    _ACK_UNREACHABLE = {
        "拒收证明": ("RL-VAT-007", "2026-10-02",
                   "折让/退货的事由说明，与任何既存资料类别都不构成同一实物；"
                   "硬映射会把事实上没拿到的资料说成「已有」"),
    }
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
    # (C) 行为：法条补全必须能带回条款内容
    try:
        from engine.legal_citation import format_legal_basis
        probe = format_legal_basis(["《发票管理办法》第二十七条"])
        if ("：" not in probe) or ("红字发票" not in probe):
            issues.append(("ERROR", "engine/legal_citation.py",
                           "法定依据未补全条款内容（《发票管理办法》第二十七条）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/legal_citation.py", f"法条解析异常: {exc}"))
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
      - **法定标准**（法定扣除限额、法定结转年限、2:1 债资比、1000 元结算起点、可清算标准、查账征收标准）→
        **必须保留**（那是法律规定，不是系统拍脑袋），故含"法定/规定/限额/结转年限/结算起点/…"者豁免。
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
    legal = ("法定", "规定", "限额", "结转年限", "结算起点", "可清算标准",
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
    for r in REDLINES:
        if not (r.get("justifications") or []):
            issues.append(("ERROR", "engine/tax_redlines.py",
                           f"{r.get('id')} justifications 为空"))
    if total != 298:
        issues.append(("ERROR", "engine/tax_redlines.py",
                       f"justifications 总条数期望 298，实际 {total}"))
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
        "中华人民共和国土地增值税暂行条例", "中华人民共和国增值税暂行条例",
        "中华人民共和国契税法", "中华人民共和国海关法", "中华人民共和国消费税暂行条例",
        "中华人民共和国环境保护税法", "中华人民共和国税收征收管理法",
        "中华人民共和国资源税法", "中华人民共和国进出口关税条例",
        "人民币银行结算账户管理办法", "企业会计准则——基本准则", "企业所得税核定征收办法",
        "企业所得税法", "企业所得税法实施条例", "企业所得税税前扣除凭证管理办法",
        "会计法", "住房公积金管理条例", "关于规范个人投资者个人所得税征收管理的通知",
        "出口货物退（免）税管理办法", "印花税法", "发票管理办法",
        "国家税务总局公告2011年第25号", "国家税务总局公告2014年第39号",
        "国家税务总局公告2014年第67号", "国家税务总局公告2018年第28号",
        "国家税务总局公告2019年第38号", "财税〔2008〕121号",
        "国家税务总局关于房地产开发企业土地增值税清算管理有关问题的通知",
        "国税发〔2006〕187号", "国税发〔2008〕30号", "城市维护建设税法",
        "城镇土地使用税暂行条例", "增值税专用发票使用规定", "增值税暂行条例",
        "增值税暂行条例实施细则", "征收教育费附加的暂行规定", "房产税暂行条例",
        "现金管理暂行条例", "社会保险法", "税收征收管理法", "税目税率表",
        "股权转让所得个人所得税管理办法（试行）", "营业税改征增值税试点实施办法",
        "财政部 国家税务总局关于全面推开营业税改征增值税试点的通知",
        "财政部 税务总局公告2023年第7号", "车船税法", "车船税法实施条例",
        # 2026-09-29：红线库引用上述法律的**全称**写法（带"中华人民共和国"前缀），
        # 与短名指向同一法律，登记全称避免误报"清单外"。
        "中华人民共和国增值税暂行条例实施细则", "中华人民共和国个人所得税法",
        "中华人民共和国个人所得税法实施条例",
        "中华人民共和国车辆购置税法",
        "中华人民共和国耕地占用税法",
        "中华人民共和国烟叶税法",
        "中华人民共和国船舶吨税法",
        "财政部 税务总局公告2022年第14号",
        "财政部 税务总局公告2022年第21号",
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
    try:
        from engine.tax_impact import estimate_tax, infer_rate_context
        _ctx = {"vat_rate": 0.06, "vat_note": "按销项有效税率 6% 测算",
                "cit_rate": 0.05, "cit_note": "小微优惠口径 5%"}
        _est = estimate_tax(100000.0, ["增值税", "企业所得税"], rate_ctx=_ctx)
        _by = {i["tax"]: i for i in _est.get("items") or []}
        if abs((_by.get("增值税") or {}).get("amount", -1) - 6000.0) > 0.01:
            issues.append(("ERROR", "engine/tax_impact.py",
                           "rate_ctx 提供 6% 时增值税仍按兜底税率测算（语境未生效）"))
        if abs((_by.get("企业所得税") or {}).get("amount", -1) - 5000.0) > 0.01:
            issues.append(("ERROR", "engine/tax_impact.py",
                           "rate_ctx 提供小微 5% 时企业所得税仍按 25% 测算"))
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
                                  net_profit=400000.0)
        if _irc.get("vat_rate") != 0.06 or _irc.get("cit_rate") != 0.05:
            issues.append(("ERROR", "engine/tax_impact.py",
                           "infer_rate_context 未按销项有效税率/净利润推断出 6% 与小微 5%"))
    except Exception as exc:
        issues.append(("ERROR", "engine/tax_impact.py", f"税额测算行为断言执行失败: {exc}"))

    # ① 线索链三态：资料已提供的环节不得写"本轮未取得该项资料"
    try:
        from engine.clue_chain import build_clue_chain
        _rl = {"id": "RL-T", "name": "测试红线",
               "clue_chain": [{"step": 1, "source": "工资表", "action": "a", "output": "o"}]}
        _f = {"type": "t", "detail": "金额5万元，需核实"}
        _c1 = build_clue_chain(_f, _rl, {}, provided_materials=["工资表"])
        if "不计入资料缺失" not in str((_c1.get("nodes") or [{}])[0].get("observed", "")):
            issues.append(("ERROR", "engine/clue_chain.py",
                           "资料已提供但环节无数据时，仍写「本轮未取得该项资料」（与已提供清单矛盾）"))
        if not _c1.get("data_gaps") or _c1["data_gaps"][0].get("reason") != "engine_gap":
            issues.append(("ERROR", "engine/clue_chain.py",
                           "engine_gap 三态标记缺失"))
        _c2 = build_clue_chain(_f, _rl, {}, provided_materials=[])
        if str((_c2.get("nodes") or [{}])[0].get("observed", "")) != "本轮未取得该项资料":
            issues.append(("ERROR", "engine/clue_chain.py",
                           "资料确未提供时应保留「本轮未取得该项资料」"))
        if not _c2.get("data_gaps") or _c2["data_gaps"][0].get("reason") != "material_missing":
            issues.append(("ERROR", "engine/clue_chain.py",
                           "material_missing 三态标记缺失"))
    except Exception as exc:
        issues.append(("ERROR", "engine/clue_chain.py", f"线索链三态断言执行失败: {exc}"))

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

    # ① 询问清单：按实际缺失列示，不得把已提供的写成未取得
    try:
        from engine.inspection_questions import run_inspection_questions
        _iq = run_inspection_questions(
            comprehensive={}, company_name="测试公司",
            data_overview={"present": ["增值税申报表", "科目余额表"],
                           "missing": ["企业所得税申报表", "资产负债表"]})
        _iq_txt = json.dumps(_iq, ensure_ascii=False, default=str)
        if "本轮未取得增值税/企业所得税申报表" in _iq_txt:
            issues.append(("ERROR", "engine/inspection_questions.py",
                           "询问清单仍把已提供的增值税申报表写成未取得"))
            # 不得断言"科目余额表未取得"（它在 present 清单里）
        if "本轮未取得科目余额表" in _iq_txt:
            issues.append(("ERROR", "engine/inspection_questions.py",
                           "询问清单仍把已提供的科目余额表写成未取得"))
        if "已提供，相应申报勾稽不受影响" not in _iq_txt:
            issues.append(("ERROR", "engine/inspection_questions.py",
                           "询问清单未按实际缺失列示（应注明已提供部分不受影响）"))
    except Exception as exc:
        issues.append(("ERROR", "engine/inspection_questions.py", f"询问清单断言执行失败: {exc}"))

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

    # ── 行为验证（dump 存在时）：任何疑点不得有两 条 evidence 完全相同的 constituent_hits ──
    _dump = ROOT / "scripts" / "four_reports" / "_fresh_result.json"
    if _dump.exists():
        try:
            _dd = json.loads(_dump.read_text(encoding="utf-8"))
            _rd_d = (((_dd.get("report") or {}).get("comprehensive")) or {}).get("redline_detection") or {}
            _bad = []
            for _s in (_rd_d.get("suspicions") or []):
                _evs = [str(h.get("evidence") or "") for h in (_s.get("argumentation") or {}).get("constituent_hits") or []
                        if str(h.get("evidence") or "").strip()]
                if len(_evs) != len(set(_evs)):
                    _bad.append(str(_s.get("redline_name") or _s.get("name") or "?"))
            if _bad:
                issues.append(("ERROR", "engine/redline_engine.py",
                               f"dump 中仍有疑点把同一段证据填进多个要件: {('、'.join(_bad[:5]))}"))
        except Exception as exc:
            issues.append(("WARN", "tools/audit_consistency.py",
                           f"dump 行为验证跳过（读取失败）: {exc}"))
    else:
        issues.append(("WARN", "tools/audit_consistency.py",
                       "未找到 scripts/four_reports/_fresh_result.json，dump 行为验证跳过（跑一次全量分析后自动生效）"))

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
        _out3b = _cr3(_rl3, "本企业触碰红线「测试红线」，涉嫌X", _clue3, _ev3, ["已按独立交易原则定价"],
                      "已触碰税务违规红线（资料不足，待补证后判断）", 0.6)
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
        _dp7 = ROOT / "scripts" / "four_reports" / "_fresh_result.json"
        if not _dp7.exists():
            raise FileNotFoundError("无 dump：先跑一次一键分析")
        _dd7 = json.loads(_dp7.read_text(encoding="utf-8"))
        _rd7 = _dd7.get("report") or {}
        if "comprehensive" not in _rd7:
            _rd7 = _rd7.get("report") or {}
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

    # ── ④ 段尾触红断言的中性化 + **锚点容错**（上游 to_plain 会改写措辞）──
    #   逐字锚点最阴的失败方式是"静默失效"：常量写「补证」，报告里却是「补充资料」
    #   （plain_language 的规则），替换一次也不会发生，谁都不报错。
    try:
        from engine.argumentation import (
            _VERDICT_HIT_PENDING as _vhp2, _TAIL_HIT_PENDING as _thp2,
            _TAIL_HIT_ANCHOR as _tha2, neutralize_assertion_when_no_constituent as _neu2,
        )
        _nm2 = "关联交易异常：购销闭环与六员重叠"
        _base2 = ("本企业触碰红线，即%s，涉嫌通过关联企业转移利润。"
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
        _other2 = ("本企业触碰红线，即另一个疑点名，涉嫌X。"
                   "综合以上，本项结论是%s。" % _vhp2)
        if _neu2(_other2, _nm2) != _other2:
            issues.append(("ERROR", "engine/argumentation.py",
                           "触红断言中性化误伤非本红线的段落（标题裁剪场景）"))
    except Exception as _exc:
        issues.append(("WARN", "tools/audit_consistency.py", f"段尾触红断言行为断言跳过: {_exc}"))

    # ── dump 行为断言：企业报告内不得出现「英文变量名=值」，且截断必须可见 ──
    if _dump.exists():
        try:
            _dd2 = json.loads(_dump.read_text(encoding="utf-8"))
            _er_d = ((_dd2.get("report") or {}).get("enterprise_readable_report")) or {}
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
            # ⚠ 结构适配：`_fresh_result.json` 是**单层**（{"report": report_data}），
            #   而 `last_analysis_cache.json` 是**双层**（[cid]["report"]["report"]）。
            #   取错层级会让下面的判据全部拿到空值 → 闸门静默假绿（本轮实测踩过）。
            _inner_d = _dd2.get("report") or {}
            if "target_entity" not in _inner_d:
                _inner_d = _inner_d.get("report") or {}
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
    _DESENS_SYMS = ("pii_guard", "mask_person_name", "mask_id_no", "mask_phone",
                    "mask_account", "redact_enterprise_report", "_pii_stats", "_pii_notice")
    if os.path.exists(str(ROOT / "engine" / "pii_guard.py")):
        issues.append(("ERROR", "engine/pii_guard.py",
                       "个人信息脱敏模块仍存在（用户定调：报告禁止脱敏/隐藏）"))
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
        if _hit:
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
    if _dump.exists():
        try:
            _dd3 = json.loads(_dump.read_text(encoding="utf-8"))
            _led_d = (((_dd3.get("report") or {}).get("enterprise_readable_report")) or {}).get("resolution_ledger") or {}
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

    # ── P1-9 可信度口径披露 ──
    try:
        from engine.argumentation import CONFIDENCE_WEIGHTS, build_argumentation
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
        if not _arg.get("confidence_breakdown"):
            issues.append(("ERROR", "engine/argumentation.py",
                           "可信度缺分项依据（点评：百分数无口径披露）"))
        if "可信度 =" not in str(_arg.get("confidence_formula") or ""):
            issues.append(("ERROR", "engine/argumentation.py", "可信度缺公式文本"))
        if not CONFIDENCE_WEIGHTS.get("base"):
            issues.append(("ERROR", "engine/argumentation.py", "可信度权重表缺失"))
    except Exception as exc:
        issues.append(("ERROR", "engine/argumentation.py", f"可信度口径断言执行失败: {exc}"))
    if "反证已提交比例" not in _strip_comments_keep_lines(_src("engine/inspection_overview.py")):
        issues.append(("ERROR", "engine/inspection_overview.py",
                       "总述「关键口径对照」未披露可信度口径（全文百分数无公式可回指）"))

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
        _s1, _src1 = _enterprise_situations(
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
        if 1 not in _p1:
            issues.append(("ERROR", "engine/constituent_checkpoint.py",
                           "数据源已有且有证据的要件未计入「涉及」"))
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
    if "_cps_all = _bcc(s)" not in _er6_code:
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
    if _dump.exists():
        try:
            _dd8 = json.loads(_dump.read_text(encoding="utf-8"))
            _iv8 = (((_dd8.get("report") or {}).get("enterprise_readable_report"))
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
        if "认定到任何一条构成要件" not in _none_lead:
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
    #   首句（p1）改对了、结论段（p4）还写「本企业触碰红线」——同一疑点内部自相矛盾。
    #   直接调生产函数 `sanitize_conclusion_assertion`（行为断言，不靠文本匹配）。
    try:
        from engine.enterprise_report import (
            sanitize_conclusion_assertion as _sca,
        )
        _rl_name = "关联交易异常：购销闭环与六员重叠"
        _reason = ("本企业触碰红线，即%s，涉嫌通过关联企业转移利润、虚开发票。"
                   "判断本项是否成立，要看这几项标准是否同时满足： Manufacturing。" % _rl_name)
        _hit_p4 = _sca(_reason, _rl_name, {"1", "3"})
        _none_p4 = _sca(_reason, _rl_name, set())
        # ★ 判据必须锁死**断言句式**「本企业触碰红线，即…」：零认定时替换句里本来就要
        #   写「不等于已触碰红线」，用裸词匹配会把自己判红（实测踩过）。
        _assertion = "本企业触碰红线，即"
        if _assertion not in _hit_p4:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "有要件被认下时，结论段的触红断言被误删（口径被改坏）"))
        if _assertion in _none_p4 or "税务违规红线" in _none_p4:
            issues.append(("ERROR", "engine/enterprise_report.py",
                           "一条要件都没认下时，结论段仍在断言「触碰红线」（与「涉及第 无 条构成要"
                           "件」正面矛盾）"))
        if "不等于已触碰红线" not in _none_p4 or "未认定到任何一条构成要件" not in _none_p4:
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
        if _dump.exists():
            try:
                _dd9 = json.loads(_dump.read_text(encoding="utf-8"))
                for _sp in ((((_dd9.get("report") or {}).get("comprehensive") or {})
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

_LEGAL_FINDING_LEVELS = {"极高风险", "高风险", "中风险", "待核验", "信息", "低风险"}
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
        elif cps[0].get("_conclusion") not in ("checked_hit", "checked_miss"):
            issues.append(("ERROR", "engine/constituent_checkpoint.py",
                           "已取得数据源的要件未判为已核对（%s）" % cps[0].get("_conclusion")))
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
    """
    issues: List[Tuple[str, str, str]] = []
    index = ROOT / "static" / "index.html"
    if not index.exists():
        return issues
    try:
        import hashlib
        html = index.read_text(encoding="utf-8")
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
            issues.append(("ERROR", "static/index.html",
                           "静态资源版本号与文件内容不一致（浏览器会继续用旧 JS/CSS，"
                           "改动用户看不到，共 %d 处）：%s。跑 python tools/sync_asset_versions.py 同步"
                           % (len(stale), _ex)))
        if missing:
            issues.append(("ERROR", "static/index.html",
                           "静态资源引用指向不存在的文件: " + "、".join(missing[:5])))
    except Exception as exc:
        issues.append(("WARN", "tools/audit_consistency.py", f"静态资源版本校验跳过: {exc}"))
    return issues


def run_checks() -> Tuple[List[Tuple[str, str, str, int, int]],
                          List[Tuple[str, str, str]]]:
    authoritative = authoritative_values()
    counts = check_counts(authoritative)
    general = (check_law_articles() + check_pollution()
               + check_tax_names() + check_domains(authoritative)
               + check_doc_type_category_map() + check_industry_consistency()
               + check_coverage_source_wiring()
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
               + check_static_asset_cache_version()  # 2026-10-02 前端缓存版本（改了看不到）
               + check_report_consistency())        # 2026-09-29 报告级一致性（缺失≠0/≠未发生/税率语境/三态）
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


if __name__ == "__main__":
    raise SystemExit(main())
