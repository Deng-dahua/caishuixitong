# -*- coding: utf-8 -*-
"""报告**视图**（4 种）与**导出格式**（4 种）—— 唯一权威。

## ★★ 与任务书「报告类型」的对应（**命名冲突的如实处理**）

任务书要求 4 种报告类型，并给出了名称：

| 任务书名称 | 本项目处理 |
|---|---|
| 标准税务风险分析报告 | → 视图 `full`（**全景**） |
| 分税种专项报告 | → 视图 `tax_specific`（**分税种专项**） |
| 管理层摘要报告 | → 视图 `management`（**管理层摘要**） |
| 税务自查报告 | → 视图 `self_check`（**税务自查**） |

**为什么不直接用任务书那四个名称**：本项目报告名有**唯一权威**
`config/report_identity.json::canonical` =「内部辅助分析工作底稿」，且该文件同时登记了
**15 个禁止别名**（`forbidden_aliases`），其中 **包含「分析报告」**。
实测（`report_identity.scan_names`）：任务书的第一个名称
**「标准税务风险分析报告」命中禁止别名**（因含「分析报告」子串）。
若照抄任务书名称，等于让系统产出**自己明令禁止的名称**（该项目历史上正因
「报告顶着禁止名称出厂」立过闸门 `check_report_identity_consistency`）。

**本模块的解法**（沿用**既有**的表述机制，不新造规则）：
  报告名 = `{canonical}（{视图标签}）`
  · 既有先例：`engine/enterprise_report._doc_display_name()` 正是
    `canonical + "（风险检查文书式）"`（版式后缀），实测真实产出为
    「内部辅助分析工作底稿（风险检查文书式）」——**加后缀是被既有机制认可的**；
  · 视图标签一律**不含**任何禁止别名（`verify_view_names()` 机器断言）；
  · 视图是**范围/粒度**维度（同一份底稿的不同裁剪），**不是**四份不同名称的报告
    ⇒ 报告名唯一权威仍是 `report_compliance.document_meta`。

## 视图与章节

12 个章节（任务书 §5 全含）。视图只决定**保留哪些章节 + 每节条数上限**；
被裁掉的章节**必须如实登记**（`omitted_sections` + 报告内「本视图未包含的章节」小节），
**不静默省略**。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# ── 章节（★ 唯一权威：新增一节只加这里一处 + SECTION_CN 一行）──────────────
SECTIONS: Tuple[str, ...] = (
    "cover",          # 封面
    "disclaimer",     # 免责声明
    "project",        # 项目概况
    "data_source",    # 数据来源
    "risk_overview",  # 风险总览
    "tax_detail",     # 分税种明细
    "key_risks",      # 重点风险
    "evidence",       # 证据链
    "legal_basis",    # 法规依据
    "rectification",  # 整改建议
    "review_record",  # 复核记录
    "attachments",    # 附件
)

SECTION_CN: Dict[str, str] = {
    "cover": "封面",
    "disclaimer": "免责声明",
    "project": "项目概况",
    "data_source": "数据来源",
    "risk_overview": "风险总览",
    "tax_detail": "分税种明细",
    "key_risks": "重点风险",
    "evidence": "证据链",
    "legal_basis": "法规依据",
    "rectification": "整改建议",
    "review_record": "复核记录",
    "attachments": "附件",
}

# ── 视图（★ 唯一权威）────────────────────────────────────────────────────
VIEWS: Tuple[str, ...] = ("full", "tax_specific", "management", "self_check")

#: 视图的**组织维度**（★ 唯一权威）：视图之间**必须**在这一维度上真正不同。
#: 2026-10-19 立：此前 `tax_specific` 与 `full` 的章节与上限**完全相同**，
#: 而 `VIEW_DESC` 却声称「按税种分组」—— 实测差异只有 4 行时间戳/水印。
#: 这是「声称 > 实际」的典型，故把「组织维度」显式登记，并配闸门
#: `verify_view_focus()`/`check_report_view_focus()` 断言其**真的不同**。
VIEW_FOCUS: Dict[str, str] = {
    "full": "severity",       # 按等级轻重 → 排序分（综合底稿）
    "tax_specific": "tax",    # **按税种**（税种为一级组织）
    "management": "severity",  # 管理层关心轻重，不关心税种细分
    "self_check": "tax",      # 企业自查同样按税种组织（保留明细，去掉逐条证据）
}

#: 组织维度的**中文标签**（唯一权威；前端只读 `focus_label`，不得自写文案）
FOCUS_LABEL: Dict[str, str] = {
    "severity": "按等级轻重组织",
    "tax": "按税种组织",
}

VIEW_LABEL: Dict[str, str] = {
    "full": "全景",
    "tax_specific": "分税种专项",
    "management": "管理层摘要",
    "self_check": "税务自查",
}

VIEW_DESC: Dict[str, str] = {
    "full": "全部 12 章节，逐条风险、逐条证据、逐条法规依据 —— 完整底稿视图。",
    "tax_specific": "以**税种为一级组织**：风险总览给出「税种×等级」交叉表，"
                    "分税种明细按税种逐个展开成**税种专项档案**（该税种的等级分布、"
                    "涉税金额小计与未取到金额条数、逐条明细、证据、法规依据与整改建议）。"
                    "与税种无关的章节（资料清单、跨税种综合排序）不在本视图内，已如实登记。",
    "management": "面向管理层的摘要视图：只保留概况、总览、重点风险与整改建议（每节条数受限），"
                  "明细类章节不在本视图内（已在报告内如实标注去向）。",
    "self_check": "面向企业自查的视图：保留概况、数据来源、总览、分税种明细与整改建议，"
                  "不含逐条证据链与逐条法规依据（已在报告内如实标注去向）。",
}

#: 各视图保留的章节（顺序即报告内顺序；`cover`/`disclaimer` 必含）
#: ★ 2026-10-19：`tax_specific` 不再与 `full` 完全相同 —— 去掉 `attachments`
#:   （资料清单是**项目级**清单，与"税种聚焦"无关），保留 `tax_detail`（税种组织载体）。
#:   `self_check` 是"税种组织 + 更窄范围"（去 key_risks/evidence/legal_basis，保留附件清单）。
VIEW_SECTIONS: Dict[str, Tuple[str, ...]] = {
    "full": SECTIONS,
    "tax_specific": ("cover", "disclaimer", "project", "data_source", "risk_overview",
                     "tax_detail", "key_risks", "evidence", "legal_basis",
                     "rectification", "review_record"),
    "management": ("cover", "disclaimer", "project", "risk_overview",
                   "key_risks", "rectification", "review_record"),
    "self_check": ("cover", "disclaimer", "project", "data_source", "risk_overview",
                   "tax_detail", "rectification", "attachments"),
}

#: 每节最多列出的条目数（`None` = 不限制）
VIEW_ITEM_LIMIT: Dict[str, Optional[int]] = {
    "full": None,
    "tax_specific": None,
    "management": 5,
    "self_check": None,
}

#: 重点风险（`key_risks`）最多取几条
KEY_RISK_LIMIT: int = 10

# ── 导出格式（★ 唯一权威）────────────────────────────────────────────────
FORMATS: Tuple[str, ...] = ("pdf", "docx", "xlsx", "html")

FORMAT_CN: Dict[str, str] = {
    "pdf": "PDF",
    "docx": "Word",
    "xlsx": "Excel",
    "html": "HTML",
}

FORMAT_MEDIA: Dict[str, str] = {
    "pdf": "application/pdf",
    "docx": ("application/vnd.openxmlformats-officedocument"
             ".wordprocessingml.document"),
    "xlsx": ("application/vnd.openxmlformats-officedocument"
             ".spreadsheetml.sheet"),
    "html": "text/html; charset=utf-8",
}

FORMAT_EXT: Dict[str, str] = {"pdf": ".pdf", "docx": ".docx",
                              "xlsx": ".xlsx", "html": ".html"}

#: 水印**嵌入方式**（唯一权威；如实声明，不夸大）
WATERMARK_METHOD: Dict[str, str] = {
    "pdf": "embedded-page-overlay",   # 逐页叠加（复用 engine/document_watermark）
    "docx": "embedded-header",        # 页眉（随文档走，打印可见）
    "xlsx": "embedded-header",        # Excel 页眉（打印/预览可见）
    "html": "embedded-css",           # 固定水印层（CSS，屏幕与打印均可见）
}


class ReportViewError(Exception):
    """视图层错误（`status` 为 HTTP 语义码，由 API 层转 `HTTPException`）。"""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = int(status)


# --------------------------------------------------------------------------
def name_of(view: Any) -> str:
    """报告名 = `{canonical}（{视图标签}）`（canonical 取唯一权威，含兜底）。"""
    v = _validate_view(view)
    try:
        from engine.report_compliance import document_meta      # noqa: PLC0415
        base = str((document_meta("internal_working_paper") or {}).get("name") or "").strip()
    except Exception:                                            # noqa: BLE001
        base = ""
    if not base:
        try:
            from engine.report_identity import canonical_name   # noqa: PLC0415
            base = str(canonical_name() or "").strip()
        except Exception:                                        # noqa: BLE001
            base = "内部辅助分析工作底稿"
    return "%s（%s）" % (base, VIEW_LABEL[v])


def _validate_view(view: Any) -> str:
    v = str(view or "").strip()
    if v not in VIEWS:
        raise ReportViewError(
            "未知报告视图：%r（合法值：%s）" % (v, "、".join(VIEWS)), 400)
    return v


def sections_of(view: Any) -> List[str]:
    """该视图保留的章节（按报告内顺序）。"""
    return list(VIEW_SECTIONS[_validate_view(view)])


def focus_of(view: Any) -> str:
    """该视图的**组织维度**（`tax` / `severity`）—— 见 `VIEW_FOCUS` 的说明。"""
    return VIEW_FOCUS[_validate_view(view)]


def is_tax_focused(view: Any) -> bool:
    """该视图是否**按税种组织**（决定 `tax_detail` 走「税种专项档案」还是「分组清单」）。"""
    return focus_of(view) == "tax"


def omitted_sections_of(view: Any) -> List[str]:
    """该视图**未包含**的章节（**如实登记**，供报告内标注与接口回执）。"""
    keep = set(VIEW_SECTIONS[_validate_view(view)])
    return [s for s in SECTIONS if s not in keep]


def item_limit_of(view: Any) -> Optional[int]:
    return VIEW_ITEM_LIMIT[_validate_view(view)]


def validate_format(fmt: Any) -> str:
    f = str(fmt or "").strip().lower()
    if f not in FORMATS:
        raise ReportViewError(
            "不支持的导出格式：%r（支持：%s）" % (f, "、".join(FORMATS)), 400)
    return f


def validate_formats(formats: Any) -> List[str]:
    """校验格式列表；空 ⇒ 全部 4 种。**去重且保持权威顺序**。"""
    if formats in (None, "", (), []):
        return list(FORMATS)
    if isinstance(formats, str):
        raw = [x for x in formats.replace("，", ",").split(",") if x.strip()]
    else:
        raw = list(formats)
    got = {validate_format(x) for x in raw}
    if not got:
        raise ReportViewError("格式列表为空", 400)
    return [f for f in FORMATS if f in got]


def verify_view_names() -> List[str]:
    """机器断言：视图名**必须以 canonical 开头且不含任何禁止别名**（供闸门调用）。

    返回问题列表（空 = 通过）。★ 这是"名称合规"的结果级判据：
    若有人把任务书原名直接塞进 `VIEW_LABEL`，本函数立刻报错。
    """
    issues: List[str] = []
    try:
        from engine.report_identity import (canonical_name,    # noqa: PLC0415
                                           forbidden_aliases, scan_names)
    except Exception as exc:                                   # noqa: BLE001
        return ["无法载入名称权威（report_identity）：%s" % exc]
    cn = canonical_name()
    for v in VIEWS:
        nm = name_of(v)
        if not nm.startswith(cn):
            issues.append("视图 %s 的名称未以唯一名称开头：%s" % (v, nm))
        hits = scan_names([nm])
        if hits:
            issues.append("视图 %s 的名称命中禁止别名 %s：%s"
                          % (v, [h.get("alias") for h in hits], nm))
        label = VIEW_LABEL[v]
        if label in forbidden_aliases():
            issues.append("视图标签「%s」本身是禁止别名" % label)
    return issues


def verify_view_focus() -> List[str]:
    """机器断言：视图之间**必须真的不同**（供闸门调用，2026-10-19 立）。

    ## 为什么必须有这条（事故）

    实测（`docs/核实_工商渠道与五类报告_20261019.md`）：`tax_specific` 与 `full`
    的 `VIEW_SECTIONS`/`VIEW_ITEM_LIMIT` **完全相同**，`VIEW_DESC` 却声称
    「按税种分组」；把报告名/时间戳/水印抹掉后，两者差异仅 **4 行** ——
    用户以为拿到了两份报告，实际是同一份。这是「声称 > 实际」的典型，
    而**单看某个视图的定义永远看不出**（必须**两两对比**）。

    ## 判据（结果级，两两对比）

      ① 任意两个视图，其 `(focus, sections, item_limit)` 三元组**不得完全相同**
         —— 否则就是"换个名字同一份内容"，必须报错；
      ② `focus == "tax"` 的视图**必须**保留 `tax_detail` 章（否则"按税种组织"
         没有承载章节，声明再次落空）；
      ③ `VIEW_FOCUS` 的键必须与 `VIEWS` 一一对应（新增视图漏登记 ⇒ 报错）。
    """
    issues: List[str] = []
    if set(VIEW_FOCUS) != set(VIEWS):
        issues.append("VIEW_FOCUS 与 VIEWS 不一致：缺 %s / 多 %s"
                      % (sorted(set(VIEWS) - set(VIEW_FOCUS)),
                         sorted(set(VIEW_FOCUS) - set(VIEWS))))
    seen: Dict[Tuple[str, Tuple[str, ...], Optional[int]], str] = {}
    for v in VIEWS:
        sig = (VIEW_FOCUS.get(v, ""), tuple(VIEW_SECTIONS.get(v) or ()),
               VIEW_ITEM_LIMIT.get(v))
        if sig in seen:
            issues.append("视图 %s 与 %s 的（组织维度/章节/上限）完全相同 —— "
                          "两个入口同一份内容（声称不同、实际相同）" % (v, seen[sig]))
        else:
            seen[sig] = v
        if VIEW_FOCUS.get(v) == "tax" and "tax_detail" not in (VIEW_SECTIONS.get(v) or ()):
            issues.append("视图 %s 声明按税种组织（focus=tax），却未保留 tax_detail 章" % v)
    return issues


def metadata() -> Dict[str, Any]:
    """字典（前端不硬编码标签）。"""
    return {
        "views": [{"value": v, "label": VIEW_LABEL[v], "desc": VIEW_DESC[v],
                   "focus": VIEW_FOCUS[v],
                   "focus_label": FOCUS_LABEL.get(VIEW_FOCUS[v], VIEW_FOCUS[v]),
                   "name": name_of(v),
                   "sections": [{"value": s, "label": SECTION_CN[s]}
                                for s in VIEW_SECTIONS[v]],
                   "omitted_sections": [{"value": s, "label": SECTION_CN[s]}
                                        for s in omitted_sections_of(v)],
                   "item_limit": VIEW_ITEM_LIMIT[v]} for v in VIEWS],
        "formats": [{"value": f, "label": FORMAT_CN[f],
                     "ext": FORMAT_EXT[f],
                     "watermark_method": WATERMARK_METHOD[f]} for f in FORMATS],
        "sections": [{"value": s, "label": SECTION_CN[s]} for s in SECTIONS],
        "key_risk_limit": KEY_RISK_LIMIT,
        "note": ("报告名 = `{唯一名称}（视图标签）`（既有机制即 canonical + 后缀，见 "
                 "`engine/enterprise_report._doc_display_name`）；视图是**范围/粒度**维度，"
                 "**不是**四份不同名称的报告。名称唯一权威："
                 "`engine/report_compliance.document_meta`。被裁掉的章节一律如实登记"
                 "（`omitted_sections`）并在报告内标注去向。"
                 "★ 视图还有**组织维度** `focus`（`tax`=按税种组织 / `severity`=按等级轻重）："
                 "`tax` 视图的「分税种明细」章是**税种专项档案**（逐税种给出等级分布、"
                 "金额口径、明细、法规依据、证据与整改建议）；`severity` 视图是分组清单。"
                 "两者**必须真的不同**（闸门 `verify_view_focus()` 两两断言）。"),
    }
