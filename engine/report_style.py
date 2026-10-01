# -*- coding: utf-8 -*-
"""报告表达风格 —— 单一权威（用户 2026-09-27 两次亲笔改写提炼）。

★ 表达特点（适用**每条风险事项与全报告正文**，不只某一章）：

  S1 每条风险事项**同时**说清"什么情形算涉嫌"与"本企业踩了哪条"
     —— 先列本红线的抽象构成要件清单（「凡符合下列构成要件即属涉嫌疑点」，红线定义、与企业无关），
        再列本企业实际核对到的情况/数据；二者并存，缺一不可（只列通用清单→企业不知踩了哪条；
        只列本企业情况→企业不知什么情形算涉嫌）。
     落地：`engine/enterprise_report.py::_build_redline_problems`。

  S2 成句叙述，不堆字段
     —— 不用「字段：值｜字段：值」式罗列，写成完整的自然句（有主语、有分寸、可通读）。
     反例：「涉嫌方向：…｜本项结论：…｜判断可信度：…｜等级依据：…｜资料情况：…」。
     落地：`static/js/tax-doc-analysis.js`（疑点 meta 三段自然句）。

  S3 有分寸、不越界
     —— 写"涉嫌 / 可能性较高 / 待核实"，不断言"已认定违法"（定性护栏另有唯一权威 `text_guardrails`）。

  S4 给出可行动的出口
     —— 每条风险都要告诉企业"补什么资料即可排除 / 需要提供什么"（出口由 `audit_doctrine.attach_three_piece` 保证）。

  S5 依据可核实
     —— 法定依据写到"具体哪一条 + 什么内容"。
     落地：`engine/legal_citation.py::format_legal_basis` + `static/legal_library.json`。

  S6 通用口径只说一次
     —— 与具体企业无关的通用说明**不得逐条重复**（用户 2026-10-01 进一步定调：
     连章首「阅读提示」这类通用说明也从报告中删除，报告只呈现本企业的风险分析）。
     落地：`tools/audit_consistency.py::check_finding_meta_wording`（禁「｜等级依据」「risk_level_basis」逐条重复）。
本模块是**唯一权威**：`EXPRESSION_PRINCIPLES` 是标准的唯一文本；`check_report_expression()`
对**已生成报告**做自检，供一键分析"常驻自检"与发布闸门（`audit_consistency`）复用。
"""
from __future__ import annotations

from typing import Any, Dict, Iterator, List, Tuple

EXPRESSION_PRINCIPLES: List[Dict[str, str]] = [
    {"key": "S1", "name": "抽象要件清单与本企业情况并存",
     "rule": "每条风险事项先列本红线的抽象构成要件清单（凡符合下列构成要件即属涉嫌疑点），"
             "再列本企业实际核对到的情况/数据；二者缺一不可。",
     "landing": "engine/enterprise_report.py::_build_redline_problems"},
    {"key": "S2", "name": "成句叙述，不堆字段",
     "rule": "不用「字段：值｜字段：值」罗列，写成完整自然句。",
     "landing": "static/js/tax-doc-analysis.js（疑点 meta 三段自然句）"},
    {"key": "S3", "name": "有分寸、不越界",
     "rule": "写涉嫌 / 可能性较高 / 待核实，不断言已认定违法。",
     "landing": "engine/text_guardrails.py（定性护栏，唯一权威）"},
    {"key": "S4", "name": "给出可行动的出口",
     "rule": "每条风险都告诉企业补什么资料即可排除 / 需要提供什么。",
     "landing": "engine/audit_doctrine.py::attach_three_piece"},
    {"key": "S5", "name": "依据可核实",
     "rule": "法定依据写到具体哪一条 + 什么内容。",
     "landing": "engine/legal_citation.py::format_legal_basis"},
    {"key": "S6", "name": "通用口径只说一次",
     "rule": "与具体企业无关的通用说明在章首说明一次，不逐条重复。",
     "landing": "tools/audit_consistency.py::check_finding_meta_wording（禁逐条重复通用口径）"},
]

# —— 自检规则（低误报：只认明确的、可判定的反例）——
# ★ 2026-09-28（用户反转 09-27）：抽象构成要件清单「凡符合下列构成要件即属涉嫌疑点」
#   现**必须**出现在每条风险事项中（红线定义、与企业无关，让企业知道"什么情形算涉嫌"），
#   不再视为违规模板。故 S1 不再按短语黑名单拦截；抽象清单的存在由源码闸门
#   `check_risk_item_section_wording` 锁定。S2（字段罗列）仍保留黑名单检测。
_GENERIC_BOILERPLATE = ()
_FIELD_LIST_LABELS = ("涉嫌方向", "本项结论", "判断可信度", "等级依据", "资料情况")


def _walk_strings(root: Any, path: str = "") -> Iterator[Tuple[str, str]]:
    """迭代 + id() 去环地遍历报告，产出 (路径, 字符串)。

    ★ 必须迭代去环：报告对象含**循环引用**，递归遍历会抛
      `maximum recursion depth exceeded`（本会话已踩两次：最终出口 `_norm_punct`、本自检）。
      凡对**整份 report_data** 的遍历，一律不许用递归。
    """
    seen = set()
    stack = [(root, path)]
    while stack:
        o, p = stack.pop()
        if isinstance(o, str):
            yield p, o
        elif isinstance(o, dict):
            if id(o) in seen:
                continue
            seen.add(id(o))
            for k, v in o.items():
                stack.append((v, f"{p}/{k}"))
        elif isinstance(o, list):
            if id(o) in seen:
                continue
            seen.add(id(o))
            for i, v in enumerate(o):
                stack.append((v, f"{p}[{i}]"))


def check_report_expression(report_data: Any) -> List[Dict[str, Any]]:
    """对已生成报告自检表达特点，返回违规项（severity=ERROR/WARN，principle=S1..S6）。

    ERROR：明确的、可判定的反例（字段罗列 S2）——发布闸门要求为 0。
    ★ 2026-09-28：抽象构成要件清单（「凡符合下列构成要件即属涉嫌疑点」）已不再视为违规，
      现为本报告每条风险事项的**必需**内容（红线定义），由源码闸门 check_risk_item_section_wording 锁定。
    WARN：需要补全但可先放行的（如法定依据尚缺条款内容）。
    """
    out: List[Dict[str, Any]] = []
    seen = set()
    for path, s in _walk_strings(report_data):
        if not isinstance(s, str) or len(s) < 8:
            continue
        for t in _GENERIC_BOILERPLATE:                     # S1
            if t in s and ("S1", t) not in seen:
                seen.add(("S1", t))
                out.append({"severity": "ERROR", "principle": "S1", "path": path,
                            "message": f"出现通用模板语「{t}」（应陈述本企业实际核对到的情况）"})
        if "｜" in s and sum(1 for lb in _FIELD_LIST_LABELS if lb in s) >= 2:   # S2
            k = ("S2", s[:40])
            if k not in seen:
                seen.add(k)
                out.append({"severity": "ERROR", "principle": "S2", "path": path,
                            "message": "正文用「｜」罗列多个字段（应改成自然句）"})
    # S5：报告里出现的法定依据是否都已补全条款内容（触发的才查，避免噪音）
    try:
        from engine.legal_citation import resolve_citation
        items = set()
        for _p, s in _walk_strings(report_data):
            if isinstance(s, str) and s.startswith("《") and ("条" in s):
                items.add(s.strip())
        lacking = sorted({i for i in items if ("：" not in resolve_citation(i))})
        # 只报"引用到达条款号、但缺内容"的（裸法名单独提示）
        lacking = [x for x in lacking if any(ch.isdigit() or ch in "一二三四五六七八九十" for ch in x)]
        if lacking:
            out.append({"severity": "WARN", "principle": "S5", "path": "legal_basis",
                        "message": f"报告中有 {len(lacking)} 条法定依据尚未补全条款内容"
                                   f"（如 {lacking[0][:40]}）；请补入 static/legal_library.json"})
    except Exception:
        pass
    return out


def expression_summary() -> List[str]:
    """返回表达特点的人类可读清单（供日志/文档/skill 引用）。"""
    return [f'{p["key"]} {p["name"]}：{p["rule"]}' for p in EXPRESSION_PRINCIPLES]
