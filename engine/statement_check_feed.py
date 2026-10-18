# -*- coding: utf-8 -*-
"""上传报表勾稽结果的**唯一取数口**（GAP-16，2026-10-18）。

问题
----
`engine/extract_validate.py` 对**用户上传的那张财务报表**做 1 元容差勾稽
（`rule="cross_check"`：资产总计 ≠ 负债合计 + 所有者权益合计 ⇒ 记异常），
结果落在 `extract_issues` 表里 —— 但**一键分析从不读它**（实测：用户传了一张
不平的资产负债表，报告里毫无反应）。分析链里的 `_check_balance_sheet_balance`
勾稽的是「**科目余额表反推出来的三表**」，与用户上传的报表是两回事。

口径
----
· 本模块只做**取数 + 转成发现**，判据本身仍在 `extract_validate`（唯一权威）；
· **只取 `status='open'`** 的异常（人工已处理的自然不再提示）；
· 找不到表 / 库不可用 ⇒ 返回空列表，**不伪造**（"没有异常"与"读不到"都如实：
  后者由 `readable` 字段区分）；
· 该发现属**报表技术性错误**（硬算式），不是税务定性 ⇒ 等级"涉嫌风险"、
  结论分级"已核定"，依据写《税收征收管理法》第二十五条（如实报送财务会计报表），
  并显式标注 `legal_basis_status`，不冒充红线。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

#: 报表勾稽不平的**依据**（属报送义务，不是"少缴税"的定性依据）
LAW_REF = "《税收征收管理法》第二十五条"

#: 等级：报表自身不平是硬错误，但只影响"数据可信度"，不直接等于少缴税
#: ★ 必须是 `engine.risk_levels.LEGAL_LEVELS` 里的**结构性等级**词。
#:   **不能写「涉嫌风险」** —— 那是"待核验"的**展示名**（`DISPLAY_LABELS`），
#:   写进 `level` 属词表外，会被 `seal_governed_findings` **静默丢弃**。
#:   与既有同源判据保持一致：`financial_analyzer._check_balance_sheet_balance`
#:   对"资产负债表不平衡"给的是「高风险」，同一事实两处不得给不同等级。
LEVEL = "高风险"


def _engine_or_none(engine: Any = None) -> Any:
    if engine is not None:
        return engine
    try:
        from database import engine as _e                # noqa: PLC0415
        return _e
    except Exception:                                    # noqa: BLE001
        return None


def open_cross_checks(company_id: Any, engine: Any = None) -> Tuple[List[Dict[str, Any]], bool]:
    """该账套下**未处理**的报表勾稽异常。返回 `(items, readable)`。

    `readable=False` 表示"读不到"（表不存在/库不可用），调用方应把它当作
    **未知**而不是"没有异常"。
    """
    eng = _engine_or_none(engine)
    if eng is None:
        return [], False
    try:
        cid = int(company_id)
    except Exception:                                    # noqa: BLE001
        return [], False
    try:
        from sqlalchemy import text as _text              # noqa: PLC0415
        with eng.connect() as conn:
            # 表是**按需建**的（未用过解析功能就没有）⇒ 先判存在，否则会抛
            # `no such table` 被静默吃掉，看起来像"没有异常"。
            has = conn.execute(_text(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='extract_issues'"
            )).first()
            if not has:
                return [], True
            rows = conn.execute(_text(
                "SELECT id, document_id, project_id, table_id, rule, severity, message, "
                "detail_json, created_at FROM extract_issues "
                "WHERE company_id=:c AND rule='cross_check' AND status='open' "
                "ORDER BY document_id, id"), {"c": cid}).all()
    except Exception:                                    # noqa: BLE001
        return [], False
    out: List[Dict[str, Any]] = []
    import json as _json                                 # noqa: PLC0415
    for r in rows:
        m = dict(r._mapping)
        try:
            detail = _json.loads(m.get("detail_json") or "{}")
        except Exception:                                # noqa: BLE001
            detail = {}
        out.append({"id": m.get("id"), "document_id": m.get("document_id"),
                    "project_id": m.get("project_id"), "table_id": m.get("table_id"),
                    "message": str(m.get("message") or ""), "detail": detail,
                    "created_at": str(m.get("created_at") or "")})
    return out, True


def finding_from_cross_check(item: Dict[str, Any], idx: int = 1) -> Dict[str, Any]:
    """把一条 `cross_check` 异常转成**报告可用**的发现（已打封印标）。"""
    d = item.get("detail") or {}
    assets = d.get("assets")
    liab = d.get("liabilities")
    eq = d.get("equity")
    diff = d.get("diff")

    def _n(v: Any) -> str:
        try:
            return "{:,.2f}".format(float(v))
        except Exception:                                # noqa: BLE001
            return "—"

    msg = str(item.get("message") or "").strip()
    if assets is None or liab is None or eq is None:
        body = msg or "上传的财务报表自身勾稽不平"
    else:
        body = ("上传的资产负债表不平：资产总计 %s 元 ≠ 负债合计 %s 元 + 所有者权益合计 %s 元，"
                "差额 %s 元（容差 1 元）" % (_n(assets), _n(liab), _n(eq), _n(diff)))
    return {
        "type": "上传报表勾稽不平",
        "fact_id": "UPLOAD-XCHECK-%d" % int(idx),
        "scene_fact_id": "UPLOAD-XCHECK-%d" % int(idx),
        "level": LEVEL,
        "score": 6,
        "detail": body,
        "description": body,
        "source": "上传资料解析校验（extract_validate.cross_check，1 元容差）",
        "law_ref": LAW_REF,
        "legal_basis_status": "报送义务依据（非少缴税定性依据）",
        "tax_impact": "报表基础数据自相矛盾 ⇒ 由该表派生的所有财务比率与规模判断均不可信；"
                      "须先更正报表再据以分析。",
        "suggestion": "① 核对资产总计、负债合计、所有者权益合计三处取数是否来自同一期间、"
                      "同一口径；② 更正后重新上传该报表；③ 若差异属未结转损益或漏填科目，"
                      "一并补充科目余额表以便复核。",
        "conclusion_grade": "已核定",
        "conclusion_scope_note": "核定范围限于该表三项合计数的算术关系；成立无须补充核实，"
                                 "推翻须更正报表本身。",
        "final_answer": "核定结论：该财务报表三项合计不自洽，属报表编制错误，须更正后重报。",
        "category": "资料校验",
        "domain": "上传报表勾稽",
        "independent_sources": ["上传的财务报表（原件）"],
        "evidence": [{"type": "上传报表", "ref": "document_id=%s" % item.get("document_id"),
                      "detail": msg}],
        "document_id": item.get("document_id"),
        "project_id": item.get("project_id"),
        "_scenario_governed": True,
        "_uploaded_statement_check": True,
        "_level_locked": True,
    }


def collect_findings(company_id: Any, engine: Any = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """取该账套全部上传报表勾稽发现 + 取数回执（供 `pipeline_log` / 报告声明）。"""
    items, readable = open_cross_checks(company_id, engine)
    out = [finding_from_cross_check(it, i) for i, it in enumerate(items, 1)]
    receipt = {"readable": readable, "count": len(out),
               "note": ("读取失败（库/表不可用）⇒ 本项**未参与**" if not readable
                        else ("未发现上传报表勾稽异常" if not out else "已并入 %d 项" % len(out)))}
    return out, receipt


__all__ = ["open_cross_checks", "finding_from_cross_check", "collect_findings",
           "LAW_REF", "LEVEL"]
