# -*- coding: utf-8 -*-
"""多税种深度模型登记表读层（P2-4）—— **唯一权威**「本系统对每个税种做哪些深度分析」。

设计原则（与任务书约束一致）
  ① **数据驱动**：模型清单来自 `config/tax_deep_models.json`（新增一个深度模型**只加一行**），
     代码里**没有**任何"税种 → 模型"的 if/else 分支；
  ② **税种清单不另立**：本系统分析的税种唯一权威 = 红线库 `taxes` 字段
     （`tax_impact.known_tax_types()`）；税率与"可否量化"口径唯一权威 = `tax_impact.tax_rate_table()`；
  ③ **未实现如实标注**：`impl` 为空的模型标 `implemented=false` + 理由，**不假装已实现**；
  ④ **可溯源**：`impl` 指向既有引擎模块，页面与闸门都可核对该模块文件是否存在。

本模块**只读**、不改引擎结论。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parent.parent
_CFG_PATH = _ROOT / "config" / "tax_deep_models.json"
_CACHE: Optional[Dict[str, Any]] = None

SEVERITIES = ("high", "medium", "low")
SEVERITY_CN = {"high": "高（线索强度）", "medium": "中（线索强度）", "low": "低（线索强度）"}


def _load() -> Dict[str, Any]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    try:
        d = json.loads(_CFG_PATH.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            d = {}
    except Exception:
        d = {}
    _CACHE = d
    return d


def reset_cache() -> None:
    global _CACHE
    _CACHE = None


def _impl_exists(impl: str) -> bool:
    if not impl:
        return False
    return (_ROOT / "engine" / ("%s.py" % impl)).is_file()


def _decorate_model(m: Dict[str, Any], *, tax: str = "", cross: bool = False) -> Dict[str, Any]:
    impl = str(m.get("impl") or "").strip()
    sev = str(m.get("severity") or "").strip()
    return {
        "code": str(m.get("code") or "").strip(),
        "label": str(m.get("label") or "").strip(),
        "tax": tax or "(跨税种)",
        "cross_tax": bool(cross),
        "focus": str(m.get("focus") or "").strip(),
        "data_required": str(m.get("data_required") or "").strip(),
        "impl": impl,
        "implemented": _impl_exists(impl),
        "impl_note": ("" if _impl_exists(impl)
                      else ("实现模块 `engine/%s.py` 不存在或未登记" % impl) if impl
                      else "尚未实现（登记为**待建**，不假装已实现）"),
        "severity": sev,
        "severity_cn": SEVERITY_CN.get(sev, sev),
    }


def _tax_rows() -> List[Dict[str, Any]]:
    return [x for x in (_load().get("taxes") or []) if isinstance(x, dict) and x.get("tax")]


def _cross_rows() -> List[Dict[str, Any]]:
    return [x for x in (_load().get("cross_tax_models") or []) if isinstance(x, dict)]


def metadata() -> Dict[str, Any]:
    """字典（表位置 / 字段说明 / 税种权威来源 / 线索强度说明）。"""
    from engine import tax_impact as TI                       # noqa: PLC0415
    return {
        "config": "config/tax_deep_models.json",
        "schema": _load().get("schema"),
        "version": _load().get("version"),
        "field_note": _load().get("field_note") or {},
        "severity_values": [{"value": s, "label": SEVERITY_CN[s]} for s in SEVERITIES],
        "tax_authority": ("本系统分析的税种唯一权威 = 红线库 `taxes` 字段"
                          "（engine.tax_impact.known_tax_types()）"),
        "rate_authority": "税率与「可否量化」口径唯一权威 = engine.tax_impact.tax_rate_table()",
        "taxes_in_scope_count": len(TI.known_tax_types()),
        "note": ("本表只登记「对某税种做哪些深度分析」与「实现落在哪个模块」；"
                 "**线索强度不是风险等级**，不得据此定性。"),
    }


def taxes() -> Dict[str, Any]:
    """税种 → 深度模型清单（含税率口径与量化能力，转发 tax_impact）。"""
    from engine import tax_impact as TI                       # noqa: PLC0415
    rate_tbl = TI.tax_rate_table()
    known = TI.known_tax_types()
    out: List[Dict[str, Any]] = []
    for row in _tax_rows():
        tax = str(row.get("tax"))
        models = [_decorate_model(m, tax=tax) for m in (row.get("models") or []) if isinstance(m, dict)]
        info = rate_tbl.get(tax) or {}
        out.append({
            "tax": tax,
            "in_scope": tax in known,
            "quantifiable": bool(info.get("quantifiable")),
            "default_rate": info.get("rate"),
            "rate_note": info.get("note") or "",
            "model_count": len(models),
            "implemented_count": sum(1 for m in models if m["implemented"]),
            "models": models,
        })
    out.sort(key=lambda x: (-x["model_count"], x["tax"]))
    return {"total": len(out), "items": out,
            "note": ("`quantifiable=false` 表示该税种**本轮取不到适用税率 ⇒ 未量化**"
                     "（不是错误，也不得用默认值顶替）。")}


def tax_detail(tax: str) -> Optional[Dict[str, Any]]:
    for x in taxes()["items"]:
        if x["tax"] == str(tax or "").strip():
            return x
    return None


def cross_tax() -> Dict[str, Any]:
    rows = [_decorate_model(m, cross=True) for m in _cross_rows()]
    return {"total": len(rows), "items": rows,
            "note": "跨税种模型针对同一事实牵连多税种的情形；不重复计入单税种模型数。"}


def coverage() -> Dict[str, Any]:
    """税种覆盖：**本系统分析的税种**（红线库权威）中有多少已登记深度模型。"""
    from engine import tax_impact as TI                       # noqa: PLC0415
    known = sorted(TI.known_tax_types())
    modeled = {str(x["tax"]) for x in _tax_rows()}
    covered = [t for t in known if t in modeled]
    missing = [t for t in known if t not in modeled]
    non_est = TI.non_estimable_taxes()
    rate_tbl = TI.tax_rate_table()
    no_rate = sorted(t for t, v in rate_tbl.items() if not v.get("quantifiable"))
    return {
        "taxes_in_scope": len(known),
        "taxes_with_models": len(covered),
        "coverage": round(len(covered) / len(known), 4) if known else 0.0,
        "taxes_without_models": missing,
        "non_estimable_taxes": sorted(non_est.keys()),
        "taxes_without_rate": no_rate,
        "note": ("`taxes_without_models` 为**本系统分析但尚未登记深度模型**的税种；"
                 "`taxes_without_rate` 为税率未登记（未量化）的税种 —— 二者都要如实展示，"
                 "不得用默认值或删税种声明来掩盖。"),
    }


def stats() -> Dict[str, Any]:
    ts = taxes()
    cx = cross_tax()
    all_models = [m for x in ts["items"] for m in x["models"]] + cx["items"]
    return {
        "taxes": ts["total"],
        "models": len(all_models),
        "cross_tax_models": cx["total"],
        "implemented": sum(1 for m in all_models if m["implemented"]),
        "pending": sum(1 for m in all_models if not m["implemented"]),
        "by_severity": [{"value": s, "label": SEVERITY_CN[s],
                         "count": sum(1 for m in all_models if m["severity"] == s)}
                        for s in SEVERITIES],
        "coverage": coverage(),
    }


__all__ = ["SEVERITIES", "SEVERITY_CN", "metadata", "taxes", "tax_detail",
           "cross_tax", "coverage", "stats", "reset_cache"]
