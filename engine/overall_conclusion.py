# -*- coding: utf-8 -*-
"""「一、本轮检查总体结论」生成器 —— 唯一权威（2026-09-26）

用户要求（2026-09-26）：该章必须**从 findings 实测派生**，不得手写模板。
凡数字（收到资料数、风险项数、各等级计数）、点名清单、涉及税种、行业口径，
一律取实测；新增或减少一条发现时**无需改本模块**（只认数据，不认特例）。

表达口径（用户 2026-09-26 定调）：
  · 从既定资料分析出的风险，**事实层可以确认** —— "已确认存在事实差异或异常"；
    并指向具体涉嫌方向；**法律定性层待补外部证据**。
  · 结论词用「风险事项」；「待核实 / 待核验」只用于真实状态（资料不足、需人工复核）。
  · 风险等级与优先顺序 = 补证紧迫性与潜在税务影响，**不表示已认定违法**。

设计红线：
  · 本模块只**读** findings 与 target_entity / inspector_reasoning，不修改任何结论；
  · 涉嫌方向用**词表扫描真实 suspect 字段**得出，命不中就不写（不凭空罗列）；
  · 行业口径原样引用（含来源与冲突），不自造"某行业基准"表述。
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

# 分层顺序：按风险程度由重到轻（与 findings.risk_level 词表一致）
_TIER_ORDER = ["高风险", "中风险", "待核验", "低风险", "信息"]
_TIER_LABEL = {"信息": "提示性事项"}

# 涉嫌方向词表（**数据驱动**：只在真实 suspect 文本中出现时才列出，命不中不写）
_DIRECTION_VOCAB = [
    "隐匿收入", "隐瞒收入", "不入账的收入", "虚开发票", "接受虚开发票", "为他人代开",
    "虚列成本", "虚增成本", "虚列费用", "虚增税前扣除", "虚列人员", "虚增人员",
    "资金回流", "资金空转", "转移利润", "变相分配", "公私混同",
    "少缴税款", "少代扣代缴", "未代扣代缴", "拆分收入", "虚抵",
]


def _short_title(t: Any) -> str:
    """标题去掉「：后缀说明」，只留主事件名（点名用）。"""
    s = str(t or "").strip()
    for sep in ("：", ":"):
        if sep in s:
            s = s.split(sep)[0]
    return s.strip()


def _collect_directions(problems: List[dict], limit: int = 6) -> List[str]:
    """从真实 suspect 文本扫描出**实际出现**的涉嫌方向（命中即列，未命中不列）。"""
    c: Counter = Counter()
    for p in problems:
        s = str((p or {}).get("suspect") or "")
        if not s:
            continue
        for d in _DIRECTION_VOCAB:
            if d in s:
                c[d] += 1
    return [d for d, _ in c.most_common(limit)]


def build_overall_conclusion(report_data: Any,
                             problems: Optional[List[dict]] = None,
                             further: Optional[List[dict]] = None,
                             inspector_reasoning: Optional[dict] = None) -> Dict[str, Any]:
    """生成「本轮检查总体结论」。

    返回：
      {
        "paragraphs": [段落文本...],       # 直接可按顺序渲染的纯文本段落
        "tiers": [{"level","label","count","items":[...]}, ...],
        "tax_types": [{"name","count"}, ...],
        "industry": {"name","source","confidence","registered","benchmark_name",
                     "observations","candidates","benchmark_source"},
        "conflict": "登记口径≠实际口径"的说明（无则空串）,
        "counts": {...},
      }
    """
    rd = report_data if isinstance(report_data, dict) else {}
    err = rd.get("enterprise_readable_report") or {}
    if problems is None:
        problems = err.get("confirmed_problems") or []
    if further is None:
        further = err.get("further_checks") or []
    problems = [p for p in (problems or []) if isinstance(p, dict)]
    further = [f for f in (further or []) if isinstance(f, dict)]

    file_results = rd.get("file_results") or []
    files_count = rd.get("files_count") or len(file_results)
    types = {fr.get("type") for fr in file_results if isinstance(fr, dict)}
    cats = len([t for t in types if t])

    te = rd.get("target_entity") or {}

    # ── 分层（完全取实测 risk_level）──
    tiers: List[Dict[str, Any]] = []
    for lv in _TIER_ORDER:
        items = [p for p in problems if str(p.get("risk_level") or "") == lv]
        if items:
            tiers.append({
                "level": lv,
                "label": _TIER_LABEL.get(lv, lv),
                "count": len(items),
                "items": [_short_title(p.get("title")) for p in items],
            })

    # ── 涉及税种（取实测 taxes）──
    tc: Counter = Counter()
    for p in problems:
        for t in (p.get("taxes") or []):
            if t:
                tc[str(t)] += 1
    tax_types = [{"name": k, "count": v} for k, v in tc.most_common()]

    # ── 涉嫌方向（数据驱动）──
    directions = _collect_directions(problems)

    # ── 行业口径（原样引用，含来源与冲突）──
    ib: Dict[str, Any] = {}
    if isinstance(inspector_reasoning, dict):
        ib = inspector_reasoning.get("industry_benchmark") or {}
    try:
        cand = te.get("_industry_candidates") or {}
        if not isinstance(cand, dict):
            cand = {}
    except Exception:
        cand = {}
    ind = {
        "name": str(te.get("industry") or "").strip(),
        "source": str(te.get("_industry_source") or "").strip(),
        "confidence": str(te.get("_industry_confidence") or "").strip(),
        "registered": str(te.get("industry_registered") or "").strip(),
        "benchmark_name": str(ib.get("benchmark_name") or ""),
        "benchmark_source": str(ib.get("industry_source") or ""),
        "observations": ib.get("observations") or [],
        "candidates": cand,
    }
    reg = str(cand.get("工商登记") or ind["registered"] or "").strip()
    inv = str(cand.get("销项发票品名推断") or "").strip()
    conflict = ""
    if reg and inv and reg != inv:
        conflict = (f"本企业登记口径为「{reg}」，而销项发票品名推断的实际经营口径为「{inv}」，"
                    f"两者不一致，可能指向超范围经营或变名开票，已单独列为核查事项。")

    # ── 已核定 / 待定性 ──
    verified = sum(1 for p in problems if str(p.get("conclusion_grade") or "") == "已核定")
    pending = len(problems) - verified

    # ══════════ 组装段落 ══════════
    P: List[str] = []

    P.append(
        f"编制声明：本轮已重新读取全部资料（{files_count} 份，归为 {cats} 类）并重新计算，"
        f"以下为本轮复算结论，独立于此前任何一轮报告。"
    )

    # 行业与对标
    if ind["name"]:
        seg = (f"行业口径：本企业行业按「{ind['name']}」认定"
               f"（来源：{ind['source'] or '未标注'}，置信度：{ind['confidence'] or '未标注'}）。")
        obs = ind["observations"]
        if obs:
            o = obs[0] or {}
            seg += (f"对照该行业基准，本企业{o.get('metric', '')}{o.get('actual', '')}%"
                    f"（行业{o.get('benchmark', '')}），{o.get('direction', '')}。{o.get('why', '')}")
        if conflict:
            seg += conflict
        P.append(seg)

    # 风险总量与税种分布
    if problems:
        tax_txt = ""
        if tax_types:
            tax_txt = "涉及税种：" + "、".join(f"{t['name']}{t['count']}项" for t in tax_types[:6]) + "。"
        dir_txt = ""
        if directions:
            dir_txt = "已指向的具体涉嫌方向包括：" + "、".join(directions) + "等。"
        P.append(
            f"本轮检查共确认 {len(problems)} 项风险事项，均已确认存在事实差异或异常。"
            f"{tax_txt}{dir_txt}"
        )

    # 分层点名
    for t in tiers:
        P.append(f"{t['label']}{t['count']}项：" + "；".join(t["items"]) + "。")

    # 事实层 / 定性层 + 法律边界
    if problems:
        if verified > 0:
            grade_txt = f"其中账面对账已核定 {verified} 项，其余 {pending} 项需补充外部证据后完成法律定性。"
        else:
            grade_txt = f"本轮这 {len(problems)} 项均需补充外部证据后完成法律定性。"
        P.append(
            f"上述 {len(problems)} 项已逐项列明检查依据、涉嫌方向与需补资料；{grade_txt}"
            f"风险等级与优先顺序仅表示补证紧迫性与潜在税务影响，不表示已经认定违法。"
        )

    # 未完成
    if further:
        P.append(
            f"另有 {len(further)} 项因资料缺失、资料不完整或影响范围尚未查清，本轮暂不下结论；"
            f"这部分表示检查范围受限，不表示已经发生相应违法。"
        )

    # 下一步
    P.append(
        "请企业负责人先按上述风险程度与优先顺序组织处理，并按要求补齐资料；"
        "完成真实更正和资料补充后，发起新一轮全量复查，继续核对原问题是否处理完成，"
        "以及补充资料是否带出新的关联问题。"
    )

    return {
        "paragraphs": P,
        "tiers": tiers,
        "tax_types": tax_types,
        "directions": directions,
        "industry": ind,
        "conflict": conflict,
        "counts": {
            "files": files_count,
            "categories": cats,
            "total": len(problems),
            "verified": verified,
            "pending": pending,
            "further": len(further),
            "by_level": {t["level"]: t["count"] for t in tiers},
        },
    }
