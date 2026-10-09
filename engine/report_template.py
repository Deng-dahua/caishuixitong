# -*- coding: utf-8 -*-
"""行业报告模板装配（用户第 5 批 任务1「行业切换时模板自动匹配」）。

## 与既有模块的分工

- `engine/audit_doctrine.REPORT_EDITING_STANDARDS` 决定**编辑版**（"税务稽查专家工作底稿版"）——
  那是"报告是给谁看的、按什么标准编制"的基线，**本模块不改它**。
- 本模块做的是**在基线之上按行业装配呈现**：章节集合与顺序、行业对标章节是否呈现、
  补资料按行业优先级排序、以及"本次按哪个行业模板呈现"的声明。
- 报告**名称与合规要素**由 `engine.report_compliance` 负责（任务2），两者不重叠。

## 铁律

- **只改呈现，不改事实**：由 `engine.snapshot_invariance.verify_invariance` 断言四类指纹恒等。
- 行业匹配不上 ⇒ **按通用结构呈现**并如实说明，不冒用别行业模板。
- 补资料排序只改**顺序**，不增删条目（增删由 `evidence_chain` / `industry_resolver` 决定）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

#: 通用（无行业）章节顺序；行业模板 sections 只允许**重排/筛选**这里列出的章节。
#: ⚠ 行业专属章节（如制造业「投入产出与存货」）也必须先登记在这里，
#:   否则 `validate()` 会报"模板章节不在 BASE_SECTIONS"——这是**故意**的：
#:   让"新增一个章节"这件事必须显式发生，而不是悄悄出现在某个模板里。
BASE_SECTIONS: Tuple[str, ...] = (
    "报告定位与合规声明",
    "风险事项",
    "行业指标对标",
    "投入产出与存货",
    "收款完整性与申报比对",
    "跨期收入与往来账龄",
    "证据现状与需补资料",
    "结论与建议",
    "签名与版本记录",
)


def template_of(industry: str) -> Dict[str, Any]:
    """取该行业报告模板（唯一来源 `engine.industry_params.report_template`，薄转发）。"""
    try:
        from engine.industry_params import report_template
        return report_template(industry) or {}
    except Exception:
        return {}


#: **恒在**的合规章节（位置固定：分别置于首、尾）；不受行业模板影响
REQUIRED_SECTIONS: Tuple[str, ...] = ("报告定位与合规声明", "签名与版本记录")


def section_order(industry: str) -> List[str]:
    """本次呈现的**章节顺序**。

    ★ 口径修正（本轮）：行业模板**决定呈现哪些章节**（可以不含某章节），
      `BASE_SECTIONS` 只作**合法章节白名单**（供 `validate()` 用），**不作补齐来源**。
      —— 初版把 BASE 里"模板没提的章节"全补回去，结果"按行业换模板"在章节上**毫无差别**
      （实测：广告传媒与制造业的章节顺序几乎一样），模板形同虚设。
      唯二例外是**合规必需章节**（`REQUIRED_SECTIONS`），任何模板都必须带上。
    """
    tpl = template_of(industry)
    if not tpl:
        return list(BASE_SECTIONS)
    mid = [str(x) for x in (tpl.get("sections") or [])]
    out: List[str] = []
    for s in (REQUIRED_SECTIONS[0],) + tuple(mid) + (REQUIRED_SECTIONS[-1],):
        if s and s not in out:
            out.append(s)
    return out


def template_note(industry: str) -> str:
    """模板匹配说明（自然句，匹配不上要如实说）。"""
    tpl = template_of(industry)
    if not tpl:
        return ("本次未匹配到行业报告模板（行业：%s）⇒ 按通用结构呈现；"
                "如需行业模板，请在 config/industry_params.json 为该行业配置 report_template。"
                % (str(industry or "未确定")))
    return "本次按「%s」呈现（行业：%s）：章节顺序为%s；重点为%s。" % (
        tpl.get("label") or tpl.get("template_id"), str(industry or ""),
        "、".join(section_order(industry)), tpl.get("emphasis") or "—")


def priority_sort(items: Any, industry: str) -> Tuple[List[str], str]:
    """按行业**补资料优先级**排序（**只重排，不增删**）；未列出的保持原相对顺序。"""
    names = [str(x) for x in (items or [])]
    try:
        from engine.industry_params import priority_rank
        rank = priority_rank(industry)
    except Exception:
        rank = {}
    if not rank:
        return names, ("未匹配到行业资料优先级（行业：%s）⇒ 保持原顺序（不冒用别行业顺序）。"
                       % str(industry or "未确定"))
    # ★ 必须先**归一**再查表：行业参数里写「购销存台账」，报告里写「进销存台账」；
    #   参数里写「合同」，报告里写「合同文件」——不归一就会永远"查不到"，
    #   排序看起来"生效了"其实一次都没命中（实测：制造业与广告传媒排出来完全一样）。
    try:
        from engine.material_names import canonical as _canon
    except Exception:
        _canon = lambda x: str(x)          # noqa: E731
    rk = {_canon(k): v for k, v in rank.items()}
    big = len(rk) + 100
    ordered = sorted(names, key=lambda n: (rk.get(_canon(n), big), names.index(n)))
    if ordered == names:
        return ordered, "本行业资料优先级与现有顺序一致。"
    return ordered, "已按「%s」行业的补资料优先级重排（只调顺序，不增删条目）。" % str(industry or "")


def apply_template(report: Dict[str, Any], industry: str,
                   materials: Optional[List[str]] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """把行业模板装配到报告上：写 `report_template_meta` 与（可选的）补资料排序说明。

    返回 `(新报告, 装配说明)`；**不改动任何风险事项的内容**。
    """
    if not isinstance(report, dict):
        return report, {}
    tpl = template_of(industry)
    ordered_materials: List[str] = []
    mat_note = ""
    if materials:
        ordered_materials, mat_note = priority_sort(materials, industry)
    note = template_note(industry)
    meta = {
        "industry": str(industry or ""),
        "matched": bool(tpl),
        "template_id": tpl.get("template_id") or "",
        "template_label": tpl.get("label") or "",
        "sections": section_order(industry),
        "emphasis": tpl.get("emphasis") or "",
        "material_priority": ordered_materials,
        "material_priority_note": mat_note,
        "note": note,
    }
    out = dict(report)
    out["report_template_meta"] = meta
    return out, meta


def validate_templates() -> List[str]:
    """校验：每个已配置行业的报告模板都存在，且模板章节都能落到 `BASE_SECTIONS` 里。"""
    probs: List[str] = []
    try:
        from engine.industry_params import industries, report_template, validate as _vip
    except Exception as exc:  # noqa: BLE001
        return ["industry_params 不可用：%s" % exc]
    for x in industries():
        iid = str(x.get("industry_id"))
        tid = str(x.get("report_template") or "")
        if not tid:
            probs.append("行业 %s 未配置 report_template" % iid)
            continue
        if not report_template(x.get("label") or iid):
            probs.append("行业 %s 的模板 %s 取不到（配置与模板表不同源）" % (iid, tid))
    try:
        from engine.report_compliance import load_config
        for tid, tpl in ((load_config().get("templates") or {})).items():
            for s in (tpl.get("sections") or []):
                if str(s) not in BASE_SECTIONS:
                    probs.append("模板 %s 的章节「%s」不在 BASE_SECTIONS 里（需同步登记）" % (tid, s))
    except Exception:
        pass
    return probs


__all__ = ["BASE_SECTIONS", "REQUIRED_SECTIONS", "template_of", "section_order", "template_note",
           "priority_sort", "apply_template", "validate_templates"]
