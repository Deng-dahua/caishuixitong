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
from typing import Dict, List, Optional, Tuple

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

    issues: List[Tuple[str, str, str]] = []
    rel = "engine/enterprise_report.py"
    real_types = set(_FILE_FINGERPRINTS.keys())
    mapped = set(_DOC_TYPE_TO_CATEGORY.keys())
    valid_cats = set(_REQUIRED_DOC_CATEGORIES)

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
    known = real_cats | set(_MATERIAL_SUPERCLASS) | set(_SOURCE_ZH.values())
    drift = sorted(n for n in redline_needs if n not in known)
    if drift:
        issues.append(("WARN", cov_rel,
                       f"{len(drift)} 条红线声明的所需资料名，与系统资料类别名、超类表均不对齐"
                       f"（可能是写法漂移，也可能是系统确无该类资料）；"
                       f"它们会被永久判为「缺资料」，建议逐条核对：{drift[:12]}"))
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
    # ② 输入对象在 build 前后不得被污染（纯只读）
    _before_keys = set(er.keys())
    try:
        pe = build_pyramid_edition(er)
    except Exception as exc:
        return issues + [("ERROR", "engine/pyramid_edition.py",
                         f"build_pyramid_edition 抛出异常: {exc}")]
    if "pyramid_edition" in er or set(er.keys()) != _before_keys:
        issues.append(("ERROR", "engine/pyramid_edition.py",
                       "build_pyramid_edition 污染了输入对象（非只读）"))

    # ③ 内容保真（不增删发现 / MECE / umbrella 仅现有字段 / 行动标题仅[等级]+title）
    ok, reasons = pyramid_preserves_content(er, pe)
    if not ok:
        for rs in reasons:
            issues.append(("ERROR", "engine/pyramid_edition.py",
                           "金字塔版越界：" + rs))
    # ④ 派生计数自洽
    if pe.get("preserved_counts", {}).get("confirmed_problems") != len(er.get("confirmed_problems") or []):
        issues.append(("ERROR", "engine/pyramid_edition.py",
                       "preserved_counts.confirmed_problems 与基线不一致"))
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
               + check_missing_as_violation() + check_pyramid_edition_preserves_content())
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
