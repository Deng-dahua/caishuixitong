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
    from engine.material_recognition import _SUPPLEMENTARY_CATEGORIES

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

    # ④ 映射键中既非实际类型、又不在对齐别名白名单内 → 疑似拼写错误
    suspicious = sorted(mapped - real_types - _DOC_TYPE_ALIAS_KEYS)
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

    # ⑤ AGI 五分类词表不得再自持一份（唯一来源＝industry_resolver.UNIVERSAL_CATEGORIES）
    try:
        import engine.agi_core as _ac
        src = inspect.getsource(_ac)
        if '"生产型": {' in src and "industry_resolver" not in src.split('"生产型": {')[0][-400:]:
            issues.append(("ERROR", "engine/agi_core.py",
                           "经营模式五分类词表出现第二份定义（应引用 industry_resolver.UNIVERSAL_CATEGORIES）"))
    except Exception:
        pass

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

    # ③ 全量不变式：68 条红线 × 全部证据项，凡判「已有」必有逐字依据
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

    # ⑥ 增量复用必须可被显式强制重算绕过，且报告须自带新鲜度标识
    if "if not force:" not in main_raw:
        issues.append(("ERROR", "main.py",
                       "增量复用无法被强制重算绕过：用户会持续拿到缓存报告"))
    if 'report_data["_freshness"]' not in main_raw:
        issues.append(("ERROR", "main.py",
                       "报告未携带计算时间/数据指纹，用户无法自证拿到的是新结果"))

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


def check_pyramid_edition_preserves_content() -> List[Tuple[str, str, str]]:
    """金字塔原理编辑版内容保真闸门（2026-09-26）。

    防回退铁律：金字塔版是工作底稿版的只读结构化重组，不得：
      · 增删发现 / 改金额 / 改结论 / 改判定 / 改等级；
      · 在 umbrella / 行动标题里引入新事实、新定性；
      · 污染输入对象（build 必须纯只读）。
    校验：对一份真实企业报告跑 build_pyramid_edition + pyramid_preserves_content，
    并核对 engine/audit_doctrine.REPORT_EDITING_STANDARDS 两份标准齐备、含「只读/禁引新事实」约束。
    """
    issues: List[Tuple[str, str, str]] = []
    try:
        from engine.audit_doctrine import REPORT_EDITING_STANDARDS
        from engine.pyramid_edition import build_pyramid_edition, pyramid_preserves_content
    except Exception as exc:
        return [("ERROR", "engine/pyramid_edition.py",
                 f"无法导入金字塔模块（闸门本身不可用）: {exc}")]

    # ① 两份系统级编辑标准齐备 + 含只读/禁引新事实约束
    if set(REPORT_EDITING_STANDARDS.keys()) != {"税务稽查专家工作底稿版", "金字塔原理编辑版"}:
        issues.append(("ERROR", "engine/audit_doctrine.py",
                       "REPORT_EDITING_STANDARDS 必须恰好包含两份标准"
                       "（税务稽查专家工作底稿版 / 金字塔原理编辑版）"))
    _pyr = REPORT_EDITING_STANDARDS.get("金字塔原理编辑版", {})
    _joined = " ".join(_pyr.get("constraints") or [])
    if "只读转换" not in _joined or "禁引新事实" not in _joined:
        issues.append(("ERROR", "engine/audit_doctrine.py",
                       "金字塔原理编辑版约束必须写明「只读转换」与「禁引新事实」"))

    er = _load_fixture_enterprise_report()
    if not er:
        return issues + [("WARN", "engine/pyramid_edition.py",
                          "未找到可用企业报告样本，跳过金字塔内容保真行为校验")]
    # ② 输入对象在 build 前后不得被污染（纯只读）。
    #    ★ 2026-09-27 修正（闸门自身缺陷，非被测代码问题）：真实报告在组装时会
    #    **内嵌** pyramid_edition（engine/enterprise_report.py `out["pyramid_edition"]=...`），
    #    故夹具 er 本就含该键；若仍断言"输入不得含 pyramid_edition"，闸门必然误报 ERROR
    #    （实测 2026-09-27 重生成 company_1_full.json 后暴露）。正解：在**去掉内嵌产物**的
    #    深拷贝上测纯度 —— 既不误报，也不改动夹具本身。
    import copy as _copy
    _base = _copy.deepcopy(er)
    _base.pop("pyramid_edition", None)
    _before_keys = set(_base.keys())
    _before_snapshot = _copy.deepcopy(_base)
    try:
        pe = build_pyramid_edition(_base)
    except Exception as exc:
        return issues + [("ERROR", "engine/pyramid_edition.py",
                         f"build_pyramid_edition 抛出异常: {exc}")]
    if ("pyramid_edition" in _base or set(_base.keys()) != _before_keys
            or _base != _before_snapshot):
        issues.append(("ERROR", "engine/pyramid_edition.py",
                       "build_pyramid_edition 污染了输入对象（非只读）"))

    # ③ 内容保真（不增删发现 / MECE / umbrella 仅现有字段 / 行动标题仅[等级]+title）
    ok, reasons = pyramid_preserves_content(_base, pe)
    if not ok:
        for rs in reasons:
            issues.append(("ERROR", "engine/pyramid_edition.py",
                           "金字塔版越界：" + rs))
    # ④ 派生计数自洽
    if pe.get("preserved_counts", {}).get("confirmed_problems") != len(_base.get("confirmed_problems") or []):
        issues.append(("ERROR", "engine/pyramid_edition.py",
                       "preserved_counts.confirmed_problems 与基线不一致"))
    return issues


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
        # ④ 用户 2026-09-27：工作底稿版要有「总—分—总」结构呈现（逐条小标签 + 目录结构说明）
        for _tok in ("_narrativeGroup", "总—分—总"):
            if _tok not in js:
                issues.append(("ERROR", js_rel,
                               "工作底稿版缺少「总—分—总」结构呈现（%s）" % _tok))

    # ③ 离线导出不得渲染 inspection_overview
    off_rel = "scripts/_render_report_html.py"
    off = _read(off_rel)
    if not off:
        issues.append(("ERROR", off_rel, "文件不存在"))
    elif "inspection_overview" in off:
        issues.append(("ERROR", off_rel,
                       "离线导出仍在渲染 inspection_overview——该章须只渲染 overall_conclusion"))

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
    if "按以下5项综合评定" not in src:
        issues.append(("ERROR", rel, "章首阅读提示未说明风险等级分级口径（5项综合评定）"))
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
        has_fallback = rid in _DEFAULT_HIT_INDEX
        has_hints = bool(r.get("match_hints") or [])
        if not has_det and not has_fallback:
            if not has_hints:
                issues.append(("ERROR", "engine/tax_redlines.py",
                               f"{rid} 不可达：既无检测器也未登记兜底且无 match_hints（死红线）"))
            else:
                blind.append(rid)
    if blind:
        issues.append(("WARN", "engine/redline_engine.py",
                       f"盲区红线（无检测器/兜底，依赖 match_redline_grounded 软匹配，须实测确认能命中）"
                       f"共 {len(blind)} 条：{', '.join(blind)}"))
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

    # ── P1-11 个人信息脱敏（唯一收敛点 + 不得有后门）──
    # ⚠ 用「去注释」视图判定接线：本文件/被检查文件的**注释里会引用同一串**
    #   （如"必须传 source=report_data"），在原文上匹配会被自己的说明文字骗过
    #   ——实测：去掉调用里的 source 参数后闸门仍"通过"。
    _er4_src = _src("engine/enterprise_report.py")
    _er4_code = _strip_comments_keep_lines(_er4_src)
    if "redact_enterprise_report" not in _er4_code:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "企业版报告未接入个人信息脱敏（员工姓名/私户金额会原样对外）"))
    if "_rg(_o, source=report_data)" not in _er4_code:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "脱敏未按约定传 source=report_data（人名清单只能从源数据收集，否则正文中的姓名漏脱敏）"))
    #  Pyramid 必须从**已脱敏的 out** 派生（旧顺序 / 用未脱敏的 problems 都会成为后门）
    if 'out["pyramid_edition"] = build_pyramid_edition' not in _er4_code:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "金字塔版未在脱敏后派生（会成为绕开个人信息脱敏的后门）"))
    if 'out.get("confirmed_problems") or problems' not in _er4_code:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "金字塔版派生源不是已脱敏内容（用未脱敏的 problems → 真实姓名从金字塔版泄漏）"))
    # P1-16/P1-7 接线：台账治理必须真的把治理结果写回 rows
    if '_gov(rows, findings, problems=problems)' not in _er4_code or 'rows = _g["rows"]' not in _er4_code:
        issues.append(("ERROR", "engine/enterprise_report.py",
                       "台账治理未接线（准入过滤/聚合/统一ID 未生效，台账仍是原始平铺行）"))
    try:
        from engine.pii_guard import (mask_account, mask_id_no, mask_person_name,
                                      mask_phone, redact_enterprise_report)
        # ① 脱敏算法本身
        if mask_person_name("杨莹") != "杨*":
            issues.append(("ERROR", "engine/pii_guard.py", "姓名脱敏规则异常"))
        if "*" not in mask_id_no("440301199001011234") or "4403011990" in mask_id_no("440301199001011234"):
            issues.append(("ERROR", "engine/pii_guard.py", "证件号脱敏不足（保留了可识别片段）"))
        if not mask_phone("13812345678").endswith("5678") or "*" not in mask_phone("13812345678"):
            issues.append(("ERROR", "engine/pii_guard.py", "手机号脱敏规则异常"))
        if "*" not in mask_account("6222021234567890123"):
            issues.append(("ERROR", "engine/pii_guard.py", "银行账号脱敏规则异常"))
        # ② 端到端：正文里的姓名（只在源数据出现的）也必须脱敏；企业名不得被改
        _rep_p = {"identity": {"organization": {"名称": "深圳海更数字传媒有限公司"}},
                  "p": [{"text": "收款人 杨莹 收到 670,000 元。"}]}
        _src_p = {"rows": [{"counterparty": "杨莹"}, {"counterparty": "深圳海更数字传媒有限公司"}]}
        _out_p = redact_enterprise_report(_rep_p, source=_src_p)
        _blob_p = json.dumps(_out_p, ensure_ascii=False)
        if "杨莹" in _blob_p:
            issues.append(("ERROR", "engine/pii_guard.py", "正文中的姓名未脱敏（只在源数据出现的人名）"))
        if "深圳海更数字传媒有限公司" not in _blob_p:
            issues.append(("ERROR", "engine/pii_guard.py", "企业/单位名被误脱敏（姓名子串规则失效）"))
        if not _out_p.get("_pii_notice"):
            issues.append(("ERROR", "engine/pii_guard.py", "缺「内部资料」个人信息标识（_pii_notice）"))
        # ③ 幂等
        if redact_enterprise_report(_out_p, source=_src_p)["p"][0]["text"] != _out_p["p"][0]["text"]:
            issues.append(("ERROR", "engine/pii_guard.py", "脱敏不幂等（重复调用会继续改写）"))
        # ④ 循环引用不得导致静默失效（真实 report_data 含环，曾把脱敏整体吞掉）
        _cyc = {"identity": {}, "姓名": "张三"}
        _cyc["self"] = _cyc
        _co = redact_enterprise_report(_cyc, source=_cyc)
        if "*" not in str(_co.get("姓名")):
            issues.append(("ERROR", "engine/pii_guard.py", "循环引用下脱敏失效（真实数据会静默跳过）"))
    except ImportError as exc:
        issues.append(("ERROR", "engine/pii_guard.py", f"个人信息脱敏模块不可用: {exc}"))
    except Exception as exc:
        issues.append(("ERROR", "engine/pii_guard.py", f"个人信息脱敏行为断言执行失败: {exc}"))

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
            if _er_d2 and not _er_d2.get("_pii_notice"):
                issues.append(("ERROR", "engine/pii_guard.py",
                               "企业报告缺「内部资料」个人信息标识（_pii_notice）"))
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

    # ── P2-3 轮次措辞：第 1 轮不得称"独立于此前任何一轮" ──
    try:
        from engine.overall_conclusion import compilation_declaration as _cd
        if "独立于此前任何一轮" in _cd({"compliance_round": {"round_no": 1}}):
            issues.append(("ERROR", "engine/overall_conclusion.py",
                           "第1轮仍写「独立于此前任何一轮报告」（第1轮无此前轮，自相矛盾）"))
        if "独立于此前任何一轮" not in _cd({"compliance_round": {"round_no": 3}}):
            issues.append(("ERROR", "engine/overall_conclusion.py",
                           "第N(>1)轮缺「独立于此前任何一轮报告」声明"))
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
    if "非税务机关文书" not in _pipe5:
        issues.append(("ERROR", "engine/pipeline.py",
                       "署名栏未声明「非税务机关文书」（生成性质与署名不符）"))

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
               + check_excel_handle_leak() + check_audit_doctrine()
               + check_missing_as_violation() + check_pyramid_edition_preserves_content()
               + check_overall_conclusion_derivation() + check_report_chapter_integrity()
               + check_overall_conclusion_no_dup()
               + check_cost_recon_render()
               + check_tax_impact_render()
               + check_industry_source_integrity()
               + check_cost_industry_basis()
               + check_material_completeness_no_ratio()
               + check_report_plain_language()
               + check_finding_meta_wording()
               + check_risk_item_section_wording()
               + check_constituent_traceability()
               + check_constituent_no_threshold()
               + check_constituent_exemption_coverage()
               + check_default_hit_index_valid()
               + check_justification_scenario_coverage()
               + check_report_expression_standard()
               + check_report_punctuation()
               + check_legal_basis_freshness()        # B3 法条时效
               + check_benchmark_refs_resolvable()    # B2 行业基准可解析
               + check_rebuttal_coverage()            # C2 反证对齐
               + check_redline_admission()            # D 红线准入 + 盲区审计
               + check_combo_profile_logic()         # C3 风险组合画像逻辑锁定
               + check_blind_redline_coverage()      # C4 盲区红线软匹配可达性锁定
               + check_benchmark_actual_compare()   # B1 实际比对（名实相符）锁定
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
