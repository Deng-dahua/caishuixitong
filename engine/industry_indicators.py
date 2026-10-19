# -*- coding: utf-8 -*-
"""行业指标库读层（P2-2）—— **唯一权威**「行业指标 / 基准区间浏览」取数口径。

设计原则（与任务书约束一致）
  ① **不硬编码行业与指标**：行业清单来自 `engine.industry_params`（`config/industry_params.json`），
     指标键/中文名/量纲来自 `engine.industry_benchmark`（`indicator_keys`/`indicator_label`/
     `indicator_unit`），基准区间来自 `industry_benchmark.resolve_benchmark`（后者又按
     实测校准 > 行业档案 > 通用参考 > 宽松兜底 的**既有优先级**解析）。本模块**零指标字面量**。
  ② **不新增第二套判定**：行业归属转发 `industry_params.resolve_industry_id`（其唯一权威
     仍是 `engine.industry_resolver`）；可比性转发 `industry_benchmark.is_indicator_comparable`。
  ③ **口径警示单一权威**：`BENCHMARK_CAUTION` 薄转发自 `industry_benchmark`，**不再写第二份**。
     任何"非官方口径"的提醒都指向它（闸门 `check_benchmark_caution_single_source` 已拦重复声明）。

本模块**只读**、不改引擎结论。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine import industry_benchmark as IB
from engine import industry_params as IP


def _indicators_of(industry_name: str) -> Dict[str, Any]:
    """解析某行业的指标清单（薄转发 `resolve_benchmark`，不另写优先级）。

    ★ 入参必须是**行业名（中文 label）**：`industry_benchmark.match_industry` 按**名称**匹配，
      传 industry_id（如 `manufacturing`）会匹配失败并落入"宽松兜底区间"
      ⇒ 页面会把兜底区间误当成该行业基准（实测踩过）。
    """
    matched, bench, source = IB.resolve_benchmark(industry_name)
    rows: List[Dict[str, Any]] = []
    for key in IB.indicator_keys():
        if key not in bench:
            continue
        low, high = bench[key]
        rows.append({
            "key": key,
            "label": IB.indicator_label(key),
            "unit": IB.indicator_unit(key),
            "low": low,
            "high": high,
        })
    return {"matched": matched, "source": source, "indicators": rows}


def metadata() -> Dict[str, Any]:
    """行业指标库字典（来源 / 口径警示 / 指标键 / 可比性说明）。"""
    return {
        "sources": IB.benchmark_sources(),
        "caution": IB.BENCHMARK_CAUTION,
        "caution_short": IB.BENCHMARK_CAUTION_SHORT,
        "indicator_keys": [{"key": k, "label": IB.indicator_label(k), "unit": IB.indicator_unit(k)}
                           for k in IB.indicator_keys()],
        "resolve_priority": ["实测校准", "行业档案", "通用参考表", "宽松兜底（未匹配到行业）"],
        "comparable_note": ("指标实际值是否参与比对由 `industry_benchmark.is_indicator_comparable` "
                            "裁定（数据完整性护栏）；超出合理值域的按「本轮数据异常」处理，"
                            "**不得**据此得出「高于/低于行业区间」的结论。"),
        "note": ("行业基准是**线索参照**，不是判定依据；行业清单与指标键均来自数据文件/权威模块，"
                 "本页不硬编码任何行业或指标。"),
    }


def industry_rows(q: Any = None) -> Dict[str, Any]:
    """行业清单（含每个行业的基准来源与指标区间）。"""
    kw = "".join(str(q or "").split())
    out: List[Dict[str, Any]] = []
    for item in IP.industries():
        iid = str(item.get("industry_id") or "").strip()
        label = str(item.get("label") or "").strip()
        if not iid:
            continue
        if kw and kw not in "".join(str(iid + label).split()):
            continue
        # ★ 传 **label**（名称）而非 industry_id（见 `_indicators_of` 说明）
        det = _indicators_of(label or iid)
        out.append({
            "industry_id": iid,
            "label": label,
            "subtypes": list(item.get("subtypes") or []),
            "benchmark_source": IB.benchmark_source(iid),
            "matched": det["matched"],
            "resolve_source": det["source"],
            "indicators": det["indicators"],
            "indicator_count": len(det["indicators"]),
        })
    out.sort(key=lambda x: (-x["indicator_count"], x["industry_id"]))
    return {"total": len(out), "items": out,
            "note": "指标区间为该行业**当前生效**的基准（按既有优先级解析得到）。"}


def industry_detail(industry: str) -> Optional[Dict[str, Any]]:
    """单行业详情（原始参数 + 指标区间 + 基准来源）。

    `industry` 可用 **industry_id 或 label**（转发 `resolve_industry_id`，不另写匹配）。
    """
    iid = IP.resolve_industry_id(industry) or str(industry or "").strip()
    raw = IP.raw_of(iid)
    # ★ 未登记的行业 ⇒ 如实 404（**不得**把"宽松兜底区间"包装成该行业的基准；
    #   兜底区间只在 `generic()` 里单列，口径不混）。
    if raw is None:
        return None
    label = str(raw.get("label") or industry)
    det = _indicators_of(label)
    return {
        "industry_id": iid,
        "label": label,
        "raw": raw,
        "matched": det["matched"],
        "resolve_source": det["source"],
        "benchmark_source": IB.benchmark_source(iid),
        "indicators": det["indicators"],
        "caution": IB.BENCHMARK_CAUTION,
        "note": ("`raw` 为该行业在 config/industry_params.json 中的**登记项原文**"
                 "（风险族/触发条件/资料优先/等级调整等）；本页只读不改。"),
    }


def generic() -> Dict[str, Any]:
    """未匹配到具体行业时使用的**宽松兜底区间**（如实单列，避免被当成某行业基准）。"""
    matched, bench, source = IB.resolve_benchmark("__no_such_industry__")
    rows = [{"key": k, "label": IB.indicator_label(k), "unit": IB.indicator_unit(k),
             "low": bench[k][0], "high": bench[k][1]} for k in IB.indicator_keys() if k in bench]
    return {"matched": matched, "source": source, "indicators": rows,
            "note": "该区间在「未匹配到行业」时使用（降低误报）；不得当作某一具体行业的基准。"}


def stats() -> Dict[str, Any]:
    """统计（行业数/指标数/行业来源分布/覆盖率）。"""
    rows = industry_rows()["items"]
    src_count: Dict[str, int] = {}
    no_ind: List[str] = []
    for x in rows:
        src_count[x["benchmark_source"]] = src_count.get(x["benchmark_source"], 0) + 1
        if not x["indicators"]:
            no_ind.append(x["industry_id"])
    all_keys = IB.indicator_keys()
    covered = set()
    for x in rows:
        covered.update(i["key"] for i in x["indicators"])
    return {
        "industries": len(rows),
        "indicator_keys": len(all_keys),
        "key_coverage": [{"key": k, "label": IB.indicator_label(k),
                          "industries": sum(1 for x in rows
                                            if any(i["key"] == k for i in x["indicators"]))}
                         for k in all_keys],
        "by_benchmark_source": [{"value": k, "industries": v} for k, v in sorted(src_count.items())],
        "industries_without_indicators": no_ind,
        "uncovered_keys": [k for k in all_keys if k not in covered],
        "caution": IB.BENCHMARK_CAUTION,
        "note": ("`uncovered_keys` 为在所有已登记行业中均无区间的指标键（需核对，"
                 "不等于错误）；`industries_without_indicators` 为无任何区间的行业。"),
    }


__all__ = ["metadata", "industry_rows", "industry_detail", "generic", "stats"]
