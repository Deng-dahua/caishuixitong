# -*- coding: utf-8 -*-
"""金字塔原理编辑版：对「税务稽查专家工作底稿版」的只读结构化重组。

═══════════════════════════════════════════════════════════════════════════════
设计纪律（来自 engine/audit_doctrine.REPORT_EDITING_STANDARDS「金字塔原理编辑版」）
═══════════════════════════════════════════════════════════════════════════════
1. 只读转换：绝不增删发现；不改金额、结论、判定、等级。
2. 新增的 umbrella（归纳句）/ 统领句 / 行动标题必须完全由现有字段组合，
   严禁引入新事实、新定性。
3. 可逆：从工作底稿版 + pyramid_edition 派生字段可无损还原工作底稿版。
4. 通用：分组键从已有字段（title / suspect / risk_level / taxes / trace_id）
   派生，不按企业硬编码。

本模块是纯函数式派生：输入企业报告（工作底稿版），返回一份新 dict，
**不修改**输入对象的任何字段。所有文字均来自输入对象既有字段的组合或固定模板。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from engine.audit_doctrine import (
    REPORT_EDITING_STANDARDS,
    DEFAULT_REPORT_EDITION,
)

# ─────────────────────────────────────────────────────────────────────────────
# 风险维度分组键（关键词数据表，可扩展；不按企业硬编码）
#   顺序即 MECE 桶的呈现顺序；末位 catch-all 兜底未命中项。
#   关键词只取自「已有字段的文本」（title / suspect / taxes / risk_level / …），
#   不使用任何企业专属名称。
# ─────────────────────────────────────────────────────────────────────────────
RISK_DIMENSION_MAP: List[Tuple[str, List[str]]] = [
    ("发票与进项合规", ["发票", "红冲", "作废", "进项", "销项", "虚开", "品名", "变名",
                   "异常凭证", "抵扣", "开票", "受票"]),
    ("收入与申报真实性", ["收入", "申报", "未开票", "视同销售", "两税", "增值税申报",
                     "销项", "隐瞒"]),
    ("成本与费用列支", ["成本", "费用", "虚列", "扣除", "折旧", "限额", "工资", "社保",
                    "人员", "发放", "列支"]),
    ("资金与公私混同", ["资金", "银行", "私户", "个人卡", "公私", "收款", "流水", "账户"]),
    ("印花税与财产税", ["印花税", "合同", "财产", "房产", "土地", "附加", "城建"]),
    ("资料完备与外部核验", ["资料", "外部", "工商", "核验", "完备", "主体", "一致性"]),
]
_CATCHALL = "其他综合风险"

# 严重度排序（与工作底稿版 _level_rank 语义一致；高 → 低）
_LEVEL_RANK = {"极高风险": 5, "高风险": 4, "中风险": 3, "待核验": 2, "信息": 1, "低风险": 0}

# umbrella 模板的固定连接词（非事实，仅用于组合现有数据）
_UMBRELLA_TEMPLATE = (
    "本组归集风险 {n} 项（其中高风险 {hi} 项、中风险 {mid} 项、其余 {low} 项），"
    "主要涉及税种：{taxes}。各事项的事实、金额、定性及解除路径详见下方台账。"
)


def _problem_corpus(p: Dict) -> str:
    """一条疑点的「现有字段文本 corpus」——umbrella / 行动标题只允许引用这些。"""
    return " ".join(str(p.get(k) or "") for k in
                   ("title", "suspect", "taxes", "risk_level", "final_answer",
                    "suggestion", "conclusion_grade", "redline_id", "trace_id"))


def _assign_dimension(p: Dict) -> str:
    """把一条疑点分配到第一个命中的 MECE 桶（关键词取自现有字段文本）。"""
    t = _problem_corpus(p)
    for name, kws in RISK_DIMENSION_MAP:
        if any(k in t for k in kws):
            return name
    return _CATCHALL


def _split_taxes(taxes: Any) -> List[str]:
    if not taxes:
        return []
    s = str(taxes).strip()
    # 兼容字段值本身是 Python list 的 repr（如 "['增值税','企业所得税']"）
    if s.startswith("[") and s.endswith("]"):
        try:
            import ast
            parsed = ast.literal_eval(s)
            if isinstance(parsed, (list, tuple)):
                s = "、".join(str(x) for x in parsed)
        except Exception:
            pass
    # 去除残留的引号/方括号
    s = s.replace("'", "").replace('"', "").replace("[", "").replace("]", "")
    parts = s.replace("、", "/").replace("，", "/").replace(",", "/").split("/")
    out = []
    for tx in parts:
        tx = tx.strip()
        if tx and tx not in out:
            out.append(tx)
    return out


def build_pyramid_edition(er: Dict) -> Dict[str, Any]:
    """从企业报告（工作底稿版）派生金字塔原理编辑版结构。

    纯只读：绝不修改 `er` 的任何字段，返回全新 dict。
    入参只需含 `confirmed_problems / summary / identity / resolution_ledger` 四个键。

    返回结构：
        edition, derived_from, principle,
        scqa{situation, complication, question, answer},
        groups[{dimension, umbrella, seqs, risk_levels, max_level, taxes}],
        ordered_seq[], action_titles{seq: 行动标题},
        ledger_basis{total, columns, statement},
        preserved_counts{confirmed_problems, groups}
    """
    if not isinstance(er, dict):
        return {}
    problems = list(er.get("confirmed_problems") or [])
    summary = er.get("summary") or {}
    identity = er.get("identity") or {}
    ledger = er.get("resolution_ledger") or {}

    # ── 严重度排序（高→低，同档按原 seq 倒序以稳定）──
    def _sev_key(p):
        return (_LEVEL_RANK.get(str(p.get("risk_level") or ""), 0),
                -(int(p.get("seq") or 0)))
    ordered = sorted(problems, key=_sev_key)
    ordered_seq = [int(p.get("seq") or 0) for p in ordered]

    # ── MECE 分组（关键词数据表，不按企业硬编码）──
    buckets: Dict[str, List[Dict]] = {}
    for p in problems:
        d = _assign_dimension(p)
        buckets.setdefault(d, []).append(p)
    group_order = [n for n, _ in RISK_DIMENSION_MAP]
    if _CATCHALL in buckets:
        group_order.append(_CATCHALL)

    groups: List[Dict[str, Any]] = []
    for d in group_order:
        items = buckets.get(d)
        if not items:
            continue
        items_sorted = sorted(items, key=_sev_key)
        levels = [str(p.get("risk_level") or "") for p in items_sorted]
        taxes: List[str] = []
        for p in items_sorted:
            for tx in _split_taxes(p.get("taxes")):
                if tx not in taxes:
                    taxes.append(tx)
        hi = sum(1 for lv in levels if lv in ("高风险", "极高风险"))
        mid = sum(1 for lv in levels if lv == "中风险")
        low = sum(1 for lv in levels if lv in ("待核验", "低风险", "信息"))
        # umbrella：固定模板 + 现有计数 + 现有税种，绝无新事实
        tax_txt = "、".join(taxes) if taxes else "综合税种"
        umbrella = _UMBRELLA_TEMPLATE.format(
            n=len(items_sorted), hi=hi, mid=mid, low=low, taxes=tax_txt)
        groups.append({
            "dimension": d,
            "umbrella": umbrella,
            "seqs": [int(p.get("seq") or 0) for p in items_sorted],
            "risk_levels": levels,
            "max_level": (max(levels, key=lambda lv: _LEVEL_RANK.get(lv, 0))
                          if levels else ""),
            "taxes": taxes,
        })

    # ── SCQA 开篇：全部由现有字段组合（禁引新事实）──
    headline = str(summary.get("headline") or "")
    kps = summary.get("key_points") or []
    answered = "；".join(str(k) for k in kps) if kps else headline
    scqa = {
        "situation": ("被查单位：%s（统一社会信用代码 %s）。检查所属期 %s，本轮为第 %s 次涉税风险分析。"
                      % (identity.get("subject_name", ""), identity.get("taxpayer_id", ""),
                         identity.get("period", ""), identity.get("analysis_round", 1))),
        "complication": ("本轮分析共接收涉税资料 %s 份，归并为 %s 类；经核查确认具体涉税风险 %s 项，"
                         "另有 %s 项因资料不完整暂无法判定，需补充资料后进一步检查。"
                         % (summary.get("received_material_count", 0),
                            summary.get("material_category_count", 0),
                            summary.get("confirmed_problem_count", 0),
                            summary.get("further_check_count", 0))),
        "question": "上述已确认风险的事实依据、涉税金额与法定处理方向为何？企业应如何逐项解除风险并完成自证？",
        # ★ 2026-09-26：不限制结论字数（用户要求结论部分高精准归纳、通俗易懂、不限字数）。
        #   此前 answered[:300] 会把"本轮核心结论"从中间截断，违背金字塔"结论先行"的完整性。
        "answer": (answered if answered else headline),
    }

    # ── 行动标题：完全由现有字段组合（[等级] + title），不改事实 ──
    action_titles: Dict[str, str] = {}
    for p in problems:
        seq = int(p.get("seq") or 0)
        action_titles[str(seq)] = "【%s】%s" % (
            p.get("risk_level") or "未分级", p.get("title") or "具体资料问题")

    return {
        "edition": "金字塔原理编辑版",
        "derived_from": DEFAULT_REPORT_EDITION,
        "principle": REPORT_EDITING_STANDARDS["金字塔原理编辑版"]["principle"],
        "scqa": scqa,
        "groups": groups,
        "ordered_seq": ordered_seq,
        "action_titles": action_titles,
        "ledger_basis": {
            "total": ledger.get("total") or len(ledger.get("rows") or []),
            "columns": ledger.get("columns") or [],
            "statement": ledger.get("statement") or "",
        },
        "preserved_counts": {
            "confirmed_problems": len(problems),
            "groups": len(groups),
        },
    }


def pyramid_preserves_content(er: Dict, pe: Dict) -> Tuple[bool, List[str]]:
    """内容保真自检（供一致性闸门与运行时验证复用）。

    返回 (ok, reasons)：任一不通过即说明金字塔版越界改写了内容。
    规则：
      A. 不增删发现：ordered_seq 覆盖全部疑点 seq，且数量一致、无重复。
      B. MECE：各组 seqs 并集 == 全部 seqs，且组间无重叠。
      C. umbrella 仅由现有字段组合：其税种部分必须来自疑点自身 taxes；
         其余为固定模板连接词 + 计数。
      D. 行动标题仅由 [等级] + title 组合，未引入新定性。
    """
    reasons: List[str] = []
    problems = list(er.get("confirmed_problems") or [])
    if not problems:
        return True, reasons  # 无内容可保真

    all_seqs = [int(p.get("seq") or 0) for p in problems]
    pe_seqs = list(pe.get("ordered_seq") or [])
    if sorted(pe_seqs) != sorted(all_seqs):
        reasons.append("ordered_seq 与 confirmed_problems 不一致（增删了发现）")
    if len(pe_seqs) != len(set(pe_seqs)):
        reasons.append("ordered_seq 存在重复 seq")

    # B. MECE
    group_seqs: List[int] = []
    seen: set = set()
    dup = False
    for g in (pe.get("groups") or []):
        for s in g.get("seqs") or []:
            if s in seen:
                dup = True
            seen.add(s)
            group_seqs.append(s)
    if dup:
        reasons.append("MECE 分组存在跨组重复 seq")
    if sorted(group_seqs) != sorted(all_seqs):
        reasons.append("MECE 分组未完整覆盖全部疑点 seq")

    # C. umbrella 只读自现有字段：税种 ⊆ 疑点自身 taxes
    seq_to_taxes: Dict[int, List[str]] = {}
    for p in problems:
        seq_to_taxes[int(p.get("seq") or 0)] = _split_taxes(p.get("taxes"))
    for g in (pe.get("groups") or []):
        member_taxes: set = set()
        for s in g.get("seqs") or []:
            member_taxes.update(seq_to_taxes.get(s, []))
        for tx in (g.get("taxes") or []):
            if tx not in member_taxes and tx != "综合税种":
                reasons.append("分组「%s」的 umbrella 税种 %s 不在其成员疑点的 taxes 中"
                               % (g.get("dimension"), tx))

    # D. 行动标题仅 [等级] + title
    title_by_seq = {str(int(p.get("seq") or 0)):
                    ("【%s】%s" % (p.get("risk_level") or "未分级",
                                  p.get("title") or "具体资料问题"))
                    for p in problems}
    for k, v in (pe.get("action_titles") or {}).items():
        if v != title_by_seq.get(k):
            reasons.append("行动标题 %s 非 [等级]+title 的既有组合" % k)

    return (len(reasons) == 0), reasons
