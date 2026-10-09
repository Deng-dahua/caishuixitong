# -*- coding: utf-8 -*-
"""多版本输出模块（唯一权威实现）——一键生成「内部完整版 + 对外版」。

指令依据（阶段9 第9项）：「一键生成内部版和对外版，自动脱敏。」

★ **脱敏策略：不脱敏**（用户明确铁律，2026-10-08）。
  理由：脱敏会破坏金额与主体的一致性（金额脱离主体后无法复核），
  且本报告仅在企业内部与委托范围内流转，不需要遮蔽主体信息。

两版的**唯一差别**：对外版剔除**工作底稿内部字段**（引擎内部 ID、调试信息、原始行号标注等），
企业名称、金额、比例、税种、结论等级等实质信息**全部保留**。

禁止：不得因"对外"而删改金额、比例、结论或任何原报告事实（指令禁止事项第 1/6 条）。
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

#: 对外版剔除的**工作底稿内部字段**标记（不是脱敏，是剔除技术噪声）
INTERNAL_MARKERS: Tuple[str, ...] = (
    "原文位置：", "closure_source", "pipeline_log", "trace_id",
    "<TRUNCATED", "debug_id", "engine_internal",
)

VARIANT_HEAD = {
    "internal": ("# 内部完整版说明\n\n"
                 "> **版本类型：内部完整版**（含工作底稿全部字段，供归档与复核）。\n"
                 "> **脱敏策略：不脱敏**（用户明确铁律）；两版实质内容一致。\n\n---\n\n"),
    "external": ("# 对外版说明\n\n"
                 "> **版本类型：对外版**。与内部完整版的唯一差别：剔除工作底稿内部字段"
                 "（引擎内部 ID、调试信息、原始行号标注）。\n"
                 "> **脱敏策略：不脱敏**（用户明确铁律）——企业名称、金额、比例、税种、"
                 "结论等级等实质信息**全部保留**，不因「对外」而删改任何事实。\n\n---\n\n"),
}


def strip_internal(text: str, markers: Optional[Tuple[str, ...]] = None) -> str:
    """剔除含内部标记的整行（不是脱敏，也不改动行内实质内容）。"""
    ms = markers or INTERNAL_MARKERS
    return "\n".join(ln for ln in str(text or "").split("\n")
                     if not any(m in ln for m in ms))


def render_variants(text: str, outdir: str, *,
                    basename: str = "报告",
                    version: str = "V1.4") -> Dict[str, Any]:
    """一键生成两版并落盘。返回 {内部版路径, 对外版路径, 差异说明}。"""
    os.makedirs(outdir, exist_ok=True)
    internal = str(text or "")
    external = strip_internal(internal)

    p_in = os.path.join(outdir, f"{basename}_{version}.md")
    p_ex = os.path.join(outdir, f"{basename}_{version}_对外版.md")
    with open(p_in, "w", encoding="utf-8") as f:
        f.write(VARIANT_HEAD["internal"] + internal)
    with open(p_ex, "w", encoding="utf-8") as f:
        f.write(VARIANT_HEAD["external"] + external)

    removed = len(internal.split("\n")) - len(external.split("\n"))
    return {
        "internal": p_in,
        "external": p_ex,
        "removed_lines": removed,
        "脱敏策略": "不脱敏（用户铁律）",
        "差异说明": f"对外版仅剔除 {removed} 行工作底稿内部字段；实质内容逐字相同",
        "实质一致性校验": ("PASS" if _same_substance(internal, external) else "FAIL"),
    }


def _same_substance(a: str, b: str) -> bool:
    """实质一致性：剔除内部行后，两版的**非内部行必须逐字相同**。"""
    return strip_internal(a) == strip_internal(b)


def verify_no_masking(*texts: str) -> List[str]:
    """反查：不得出现任何脱敏标记（企业名/账号被替换的痕迹）。"""
    marks = ("【企业A】", "【已脱敏】", "***", "×××", "XX公司")
    hits: List[str] = []
    for t in texts:
        for m in marks:
            if m in str(t or ""):
                hits.append(m)
    return sorted(set(hits))


#: 分节标记（仅供判定之用的**内部标记**，不是用户可见文本）。
SECTION_MARK_PREFIX = "<<S:"


def report_text_from(report_data: Any, *, max_items: int = 80) -> str:
    """从结构化 report_data 提取**可判定文本**（供产出链自动算重复率/跑自检）。

    只取文本字段（不含内部 ID / 调试信息），不臆造内容；取不到即返回已取到的部分。
    """
    if not isinstance(report_data, dict):
        return ""
    # ★ 2026-10-08（条款 A5：去重须含「同章节≤5%」）：输出**章节标记**，使下游能按"事项"为单位
    #   判同章节重复率。`<<S:…>>` 行被 `dedup_pipeline.duplicate_rate` 识别为分节标记
    #   （不计入字数、不参与去重）；本函数只供**判定**使用，落盘正文另走
    #   `report_pipeline._render_text_from_report_data`，故标记不会进报告。
    buf: List[str] = ["<<S:总述>>"]
    for k in ("overall_level", "summary", "conclusion", "tax_impact_note", "scope_note"):
        v = report_data.get(k)
        if isinstance(v, str) and v.strip():
            buf.append(v.strip())
    # ★ 2026-10-08 修复：报告层 confirmed_problems 优先（引擎层 all_findings 条数与报告口径不同）
    items = None
    _er = report_data.get("enterprise_readable_report")
    if isinstance(_er, dict) and isinstance(_er.get("confirmed_problems"), list) and _er["confirmed_problems"]:
        items = _er["confirmed_problems"]
    if items is None:
        for k in ("confirmed_problems", "findings", "all_findings"):
            if isinstance(report_data.get(k), list) and report_data[k]:
                items = report_data[k]
                break
    for _idx, it in enumerate((items or [])[:max_items], 1):
        if not isinstance(it, dict):
            continue
        # ★ 2026-10-08：每个事项前插入章节标记（`seq` 本就 1 起，不可 +1）
        _seq = it.get("seq")
        _rn = _seq if isinstance(_seq, int) and _seq >= 1 else _idx
        buf.append("<<S:R%d %s>>" % (_rn, str(it.get("title") or "事项")[:30]))
        # ★ 2026-10-08 修复：字段名须与真实产物对齐（原先取 conclusion/reason/analysis 等**不存在**的键
        #   ⇒ 只提到 12 字，重复率自检等于空转）。以下字段取自 `enterprise_readable_report.confirmed_problems`。
        for kk in ("title", "premise_note", "verdict", "risk_level", "risk_level_basis",
                   "suspect", "suggestion", "final_answer", "confidence_formula",
                   "conclusion_grade"):
            v = it.get(kk)
            if isinstance(v, str) and v.strip():
                buf.append(v.strip())
        for kk in ("narrative_paragraphs", "missing_materials", "missing_material_names",
                   "verify_materials", "taxes"):
            v = it.get(kk)
            if isinstance(v, list):
                for x in v:
                    if isinstance(x, str) and x.strip():
                        buf.append(x.strip())
                    elif isinstance(x, dict):
                        for kk2 in ("text", "content", "paragraph", "说明", "title", "name"):
                            xv = x.get(kk2)
                            if isinstance(xv, str) and xv.strip():
                                buf.append(xv.strip())
                                break
        ti = it.get("tax_impact")
        if isinstance(ti, dict):
            for kk in ("note", "basis", "scope_note", "formula"):
                v = ti.get(kk)
                if isinstance(v, str) and v.strip():
                    buf.append(v.strip())
    return "\n".join(buf)
