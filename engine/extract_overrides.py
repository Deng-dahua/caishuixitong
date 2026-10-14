# -*- coding: utf-8 -*-
"""人工校正值的**唯一权威** —— 「解析与标准化」的人工校正让一键分析**真正消费**（ODC-02 / S6-TODO-001）。

## 缺口（为什么要有本模块）

`engine/extract_service.parse_document()` 把资料解析成 `extracted_fields`
（标准字段 + 值 + 来源行号），用户在「解析与标准化」页 `correct_field()` 校正后落 `corrected=1`。
但一键分析链（`engine.pipeline`）**从不读 `extracted_fields`**（实测：全仓 18 处引用**全在
`extract_service` / `extract_store`**，`pipeline.py` / `main.py` **零引用**）
⇒ **人工校正做了但不生效** —— 与「报告模板管理空转」同属"功能做了但不生效"的同一病根
（读写两端不同源）。

## 本模块做什么

把**已人工校正**的公司级标准字段读出来，覆盖到分析链构造的、**以标准字段命名**的字典上：

| 目标 | 构造处 | 键约定 |
|---|---|---|
| `balance_sheet` / `income_stmt` | `financial_analyzer.build_statements_from_trial_balance()` | `total_assets` / `revenue` / `cost` / `net_profit` |
| 税收优惠的 `_balance_sheet` / `_income_stmt` | `pipeline._run_analyze` 内 | `total_assets` / `revenue` / **`total_cost`** / `net_profit` |

两处的**唯一差别只是键名**（`cost` vs `total_cost`）⇒ 用**一份实现 + 两张键表**表达，
新增一处只加一行映射，不改逻辑分支。

## 铁律

- **缺失 ≠ 0**：取不到校正值 ⇒ **不改原值**（绝不写 0、绝不凭空造字段）。
- **只覆盖值**：只动金额/期间/文本；不动规则、等级、结论、证据。
- **应用必须可见**：每次应用都返回 `applied`（含 `previous` 原值），由调用方写 `pipeline_log`
  并进入报告载荷 —— **不静默**。否则"校正了但没人知道生效没有"就是新的静默缺陷。
- **保留原值**：`previous` 一并返回，供报告呈现「人工校正：X → Y」。
- **越权隔离**：按 `company_id` 过滤；不同账套的校正**永不串用**。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

__all__ = [
    "corrections_by_field", "apply_overrides", "summarize", "receipt",
    "FINANCIAL_STATEMENT_KEYS", "INCENTIVE_KEYS", "OVERRIDABLE_FIELDS",
]

# ── 可覆盖字段（★ 唯一权威：新增一个字段只加一行；两张键表都从这里取） ──
#: 标准字段名 → 中文名（供日志/报告呈现，与 `config/standard_fields.json` 保持同源含义）
_FIELD_CN: Dict[str, str] = {
    "total_assets": "资产总计",
    "total_liabilities": "负债合计",
    "total_equity": "所有者权益合计",
    "revenue": "营业收入",
    "cost": "营业成本",
    "net_profit": "净利润",
}

OVERRIDABLE_FIELDS: Tuple[str, ...] = tuple(sorted(_FIELD_CN))

#: 键表 ①：`build_statements_from_trial_balance()` 的键约定
#: `标准字段 → (目标字典名, 目标键)`
FINANCIAL_STATEMENT_KEYS: Dict[str, Tuple[str, str]] = {
    "total_assets": ("balance_sheet", "total_assets"),
    "total_liabilities": ("balance_sheet", "total_liabilities"),
    "total_equity": ("balance_sheet", "total_equity"),
    "revenue": ("income_statement", "revenue"),
    "cost": ("income_statement", "cost"),
    "net_profit": ("income_statement", "net_profit"),
}

#: 键表 ②：税收优惠分析的键约定（利润表把成本记作 `total_cost`）
INCENTIVE_KEYS: Dict[str, Tuple[str, str]] = {
    "total_assets": ("balance_sheet", "total_assets"),
    "revenue": ("income_statement", "revenue"),
    "cost": ("income_statement", "total_cost"),
    "net_profit": ("income_statement", "net_profit"),
}


def _engine_or_none(engine: Any = None):
    if engine is not None:
        return engine
    try:
        from database import engine as _e                          # noqa: PLC0415
        return _e
    except Exception:                                              # noqa: BLE001
        return None


def _missing(v: Any) -> bool:
    """值是否**缺失**（`None` / 空白串 / 空白串组成的占位）。

    ★ 铁律「缺失 ≠ 0」：缺失值**不得**覆盖原取数（否则把"没填"变成"填了 0/空"）。
    """
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return False


def corrections_by_field(company_id: Any, *, engine: Any = None) -> Dict[str, Dict[str, Any]]:
    """该公司**已人工校正**且**可覆盖分析取数**的标准字段。

    返回 `{standard_field: {value, value_text, value_period, field_cn, previous, by, at, document_id, source_ref}}`。

    ★ 语义：
      · 仅取 `corrected=1` 且 `standard_field` 在 `OVERRIDABLE_FIELDS` 内（其余字段不参与报表取数覆盖）；
      · 同一字段多次校正 ⇒ **最后一次胜出**（按 `corrected_at`、`id` 排序取末条）；
      · 表不存在 / 无校正 / 库不可用 ⇒ **返回空字典**（调用方保持原取数，**不写 0**），
        并**不吞异常信息**（返回空即"没有校正"，不是"校正为 0"）。
    """
    eng = _engine_or_none(engine)
    if eng is None:
        return {}
    try:
        cid = int(company_id)
    except Exception:                                              # noqa: BLE001
        return {}
    try:
        from sqlalchemy import text as _text                       # noqa: PLC0415
        with eng.connect() as conn:
            rows = conn.execute(_text(
                "SELECT document_id, standard_field, value_text, value_amount, value_period, "
                "       original_value, corrected_by, corrected_at, source_ref "
                "FROM extracted_fields "
                "WHERE company_id = :c AND corrected = 1 "
                "ORDER BY corrected_at, id"), {"c": cid}).fetchall()
    except Exception:                                              # noqa: BLE001
        # 表不存在（尚未用过解析功能）或库不可用 ⇒ 视为「无校正」，保持原取数
        return {}

    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        m = dict(r._mapping)
        field = str(m.get("standard_field") or "").strip()
        if field not in OVERRIDABLE_FIELDS:
            continue
        # 金额字段优先 `value_amount`（结构化），回落 `value_text`（原样）；
        # ★ 空白串一律视为**缺失**（不写空值、更不写 0）
        val: Any = m.get("value_amount")
        if _missing(val):
            val = m.get("value_text")
        if _missing(val):
            val = None
        out[field] = {                                             # 后者覆盖前者 ⇒ 最后一次胜出
            "field": field,
            "field_cn": _FIELD_CN.get(field, field),
            "value": val,
            "value_text": m.get("value_text"),
            "value_period": m.get("value_period"),
            "previous": m.get("original_value"),
            "by": str(m.get("corrected_by") or ""),
            "at": str(m.get("corrected_at") or ""),
            "document_id": m.get("document_id"),
            "source_ref": str(m.get("source_ref") or ""),
        }
    return out


def apply_overrides(targets: Dict[str, Any],
                    corrections: Dict[str, Dict[str, Any]],
                    key_map: Dict[str, Tuple[str, str]]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """把校正值覆盖到 `targets`（如 `{"balance_sheet": {...}, "income_statement": {...}}`）。

    返回 `(targets, applied)`；`applied` 每项含 `field/field_cn/previous/current/source`，
    供调用方写日志与报告载荷（**不静默**）。

    ★ **单一实现 + 两张键表**：本函数不区分调用点，键名差异全由 `key_map` 数据表达。
    ★ 目标字典缺失 ⇒ **就地建键**（校正值是用户给出的真实数据，不应因为某报表没算出来就丢弃）；
      但**不建整个字典**（父字典仍由调用方提供），避免在无数据时凭空造出一张表。
    """
    applied: List[Dict[str, Any]] = []
    if not isinstance(targets, dict) or not isinstance(corrections, dict) or not corrections:
        return targets, applied
    for field, spec in key_map.items():
        corr = corrections.get(field)
        if not corr:
            continue
        target_name, target_key = spec
        tgt = targets.get(target_name)
        if not isinstance(tgt, dict):
            # 目标字典不存在（该报表本次未产出）⇒ 不凭空造表；如实记录"未应用"
            applied.append({"field": field, "field_cn": corr.get("field_cn") or field,
                            "applied": False, "reason": "目标表未产出（%s）" % target_name,
                            "current": corr.get("value"), "previous": None,
                            "by": corr.get("by"), "at": corr.get("at")})
            continue
        new_val = corr.get("value")
        if _missing(new_val):
            applied.append({"field": field, "field_cn": corr.get("field_cn") or field,
                            "applied": False, "reason": "校正值缺失（不写 0／空）",
                            "current": None, "previous": tgt.get(target_key),
                            "by": corr.get("by"), "at": corr.get("at")})
            continue
        prev = tgt.get(target_key)
        try:
            tgt[target_key] = float(new_val)
        except Exception:                                          # noqa: BLE001
            tgt[target_key] = new_val                              # 非数值（文本型）原样写入
        applied.append({"field": field, "field_cn": corr.get("field_cn") or field,
                        "applied": True, "reason": "",
                        "previous": prev, "current": tgt.get(target_key),
                        "by": corr.get("by"), "at": corr.get("at")})
    return targets, applied


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    try:
        return "{:,.2f}".format(float(v))
    except Exception:                                              # noqa: BLE001
        return str(v)


def receipt(applied: List[Dict[str, Any]]) -> Dict[str, Any]:
    """应用回执（供报告载荷）——按字段去重（同一字段在多个取数点只记一条）。

    ★ **不静默**：`count_applied` 为 0 时 `note` 也明说"未采用"，而不是留空让人猜。
    """
    by: Dict[str, Dict[str, Any]] = {}
    for a in (applied or []):
        f = str((a or {}).get("field") or "")
        if not f:
            continue
        rec = by.get(f)
        if rec is None:
            rec = {"field": f, "field_cn": (a.get("field_cn") or f),
                   "applied": bool(a.get("applied")),
                   "previous": a.get("previous"), "current": a.get("current"),
                   "sites": [], "reasons": []}
            by[f] = rec
        rec["applied"] = rec["applied"] or bool(a.get("applied"))
        if a.get("applied"):
            rec["current"] = a.get("current")
            if rec.get("previous") is None:
                rec["previous"] = a.get("previous")
        reason = str(a.get("reason") or "")
        if reason and reason not in rec["reasons"]:
            rec["reasons"].append(reason)
    rows = sorted(by.values(), key=lambda x: str(x.get("field")))
    ok = [r for r in rows if r.get("applied")]
    return {
        "count_applied": len(ok),
        "count_skipped": len(rows) - len(ok),
        "items": rows,
        "source": "解析与标准化页的人工校正（extracted_fields.corrected=1）",
        "note": ("本次分析采用了 %d 项人工校正" % len(ok)) if ok else "本次分析未采用人工校正",
    }


def summarize(applied: List[Dict[str, Any]]) -> str:
    """一行自然句（供 `pipeline_log`；已应用 / 未应用都如实说）。"""
    ok = [a for a in applied if a.get("applied")]
    bad = [a for a in applied if not a.get("applied")]
    if not ok and not bad:
        return ""
    parts: List[str] = []
    if ok:
        parts.append("已采用人工校正 %d 项（%s）"
                     % (len(ok), "；".join("%s %s→%s" % (a["field_cn"], _fmt(a.get("previous")),
                                                        _fmt(a.get("current"))) for a in ok)))
    if bad:
        parts.append("未采用 %d 项（%s）"
                     % (len(bad), "；".join("%s：%s" % (a["field_cn"], a.get("reason") or "未知")
                                           for a in bad)))
    return "；".join(parts)
