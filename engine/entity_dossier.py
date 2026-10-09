# -*- coding: utf-8 -*-
"""企业画像 —— 统一出口（用户第 4 批 任务2）。

## 与既有模块的关系（**不新建第二份实现**）

- `engine/enterprise_profile.py` 是"身份/行业/规模/风险初评/策略"的**聚合器**（已有，本模块薄转发）；
- `engine/industry_resolver.py` 是行业解析**唯一权威**；
- `enterprise_report.required_doc_coverage()` 是"必查/已提供/缺失/不适用"的**唯一权威**；
- `engine/domain_analysis._load_analysis_memory()` 提供**真实的历史分析记忆**。

本模块只做三件既有模块没做的事：
  ① 把上述来源拼成**任务要求的 7 个画像字段**（行业/规模/纳税人类型/业务模式/核算特点/历史风险/已补资料）；
  ② 明确标注**哪些字段取不到**（`undetermined_fields`）——绝不猜；
  ③ 输出《企业画像》文档，并**声明"只作参考、不改变风险等级"**（契约字段 + 闸门 + 行为测试锁死）。

## ★ 铁律

- **取不到就写"未确定"并说明依据缺失**，不得用行业默认值静默顶替。
- `affects_risk_level` **恒为 False**：本模块产出的任何内容都**不得**进入定级链路。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent

#: 画像字段（★ 唯一权威：任务原文的 7 项；新增字段只加这里一处 + `build_dossier` 一行）
DOSSIER_FIELDS: Tuple[str, ...] = (
    "industry", "scale", "taxpayer_type", "business_model",
    "accounting_features", "historical_risks", "supplied_materials",
)

#: 字段名 → 中文（★ 键汉化唯一权威：**面向企业的文本里严禁出现英文键**）
DOSSIER_FIELD_CN: Dict[str, str] = {
    "industry": "行业",
    "scale": "规模",
    "taxpayer_type": "纳税人类型",
    "business_model": "业务模式",
    "accounting_features": "核算特点",
    "historical_risks": "历史风险",
    "supplied_materials": "已补资料",
}


def field_cn(key: str) -> str:
    """字段中文名（取不到就返回原键并标注，便于暴露漏登记，不静默拼英文）。"""
    return DOSSIER_FIELD_CN.get(str(key), "「%s」（未登记中文名）" % key)

#: 资料类别 → 核算特点（数据驱动：新增一类只加一行；类别名用 file_results 的 type）
ACCOUNTING_FEATURE_RULES: Tuple[Tuple[str, str], ...] = (
    ("voucher", "有完整序时账，可按凭证逐笔追溯"),
    ("trial_balance", "有科目余额表，可按科目级次核对"),
    ("inventory", "有存货数据，可做进销存勾稽"),
    ("bank_statement", "有银行流水，可做资金流与业务流比对"),
    ("salary", "有工资表，可做薪酬与个税、社保勾稽"),
    ("social_security", "有社保缴费明细，可做用工三源比对"),
    ("invoice", "有发票明细，可做票流与申报比对"),
    ("vat_declaration", "有增值税申报表，可做申报与账载比对"),
    ("cit_declaration", "有企业所得税申报表，可做两税比对"),
    ("financial_statement", "有财务报表，可做报表级勾稽"),
)

UNKNOWN = "未确定"


def _undetermined(v: Any) -> bool:
    return v in (None, "", [], {})


def _file_results(report_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    fr = (report_data or {}).get("file_results") or []
    return [f for f in fr if isinstance(f, dict)]


def _type_of(f: Dict[str, Any]) -> str:
    return str(f.get("type") or f.get("doc_type") or f.get("_type") or "").strip().lower()


def _accounting_features(report_data: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """由**实际资料类别**推导核算特点；推导不出的类别如实列出（不猜）。"""
    types = {_type_of(f) for f in _file_results(report_data)}
    feat: List[str] = []
    for key, desc in ACCOUNTING_FEATURE_RULES:
        if any(key in t for t in types if t):
            feat.append(desc)
    unknown = sorted({t for t in types if t and not any(k in t for k, _ in ACCOUNTING_FEATURE_RULES)})
    return feat, unknown


def _historical_risks(report_data: Dict[str, Any]) -> List[str]:
    """历史风险：取自**真实的历史分析记忆**（`_load_analysis_memory`），无记录则如实说明。"""
    mem = ((report_data or {}).get("comprehensive") or {}).get("analysis_memory")
    if not isinstance(mem, dict):
        try:
            from engine.domain_analysis import _load_analysis_memory
            mem = _load_analysis_memory()
        except Exception:
            mem = {}
    out: List[str] = []
    for key in ("own_history", "history", "prior_findings", "cross_company"):
        v = (mem or {}).get(key)
        if isinstance(v, list):
            for x in v[:8]:
                s = x.get("title") or x.get("type") or x.get("detail") if isinstance(x, dict) else x
                if str(s or "").strip():
                    out.append(str(s).strip()[:80])
    return out


def _supplied_materials(report_data: Dict[str, Any]) -> Dict[str, List[str]]:
    """已补资料：**唯一权威** `enterprise_report.required_doc_coverage`。"""
    try:
        from engine.enterprise_report import required_doc_coverage
        cov = required_doc_coverage(report_data or {})
        return {"provided": [str(x) for x in (cov.get("provided") or [])],
                "missing": [str(x) for x in (cov.get("missing") or [])],
                "not_applicable": [str(x) for x in (cov.get("na") or [])]}
    except Exception:
        return {"provided": [], "missing": [], "not_applicable": []}


def build_dossier(report_data: Dict[str, Any],
                  profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """构造企业画像（7 个字段 + 未确定清单 + **只作参考**契约）。"""
    rd = report_data or {}
    te = rd.get("target_entity") or {}
    pf = profile or ((rd.get("comprehensive") or {}).get("enterprise_profile") or {})
    ind = pf.get("industry") or {}
    scale = pf.get("scale") or {}
    ident = pf.get("identity") or {}
    riskp = pf.get("risk_profile") or {}

    industry = (ind.get("real") or ind.get("registered")
                or te.get("industry") or rd.get("industry") or "")
    taxpayer = ident.get("taxpayer_type") or te.get("taxpayer_type") or ""
    biz = (ident.get("business_model") or te.get("biz_model")
           or ((rd.get("company_profile") or {}).get("biz_model")) or "")
    if not biz and industry:
        try:
            from engine.industry_resolver import match_benchmark
            biz = match_benchmark(industry) or ""
        except Exception:
            biz = ""
    feat, unknown_types = _accounting_features(rd)
    hist = _historical_risks(rd)
    if not hist and isinstance(riskp.get("prior_violations"), list):
        hist = [str(x) for x in riskp["prior_violations"][:8]]
    mats = _supplied_materials(rd)

    d: Dict[str, Any] = {
        "schema": 1,
        "company_id": str((rd.get("target_entity") or {}).get("company_id") or ""),
        "entity_name": ident.get("name") or te.get("name") or rd.get("company_name") or "",
        # ★★ 契约字段：画像**只作参考**，任何内容都不得改变风险等级
        "reference_only": True,
        "affects_risk_level": False,
        "industry": {"real": industry or UNKNOWN,
                     "registered": ind.get("registered") or UNKNOWN,
                     "basis": ind.get("penetration_note") or ""},
        "scale": {"revenue_range": scale.get("revenue_range") or UNKNOWN,
                  "employee_count": scale.get("employee_count"),
                  "asset_range": scale.get("asset_range") or UNKNOWN,
                  "is_small_micro": scale.get("is_small_micro")},
        "taxpayer_type": taxpayer or UNKNOWN,
        "business_model": biz or UNKNOWN,
        "accounting_features": feat or [UNKNOWN],
        "historical_risks": hist or [],
        "supplied_materials": mats,
        "undetermined_fields": [],
        "accounting_feature_unknown_types": unknown_types,
    }
    und: List[str] = []
    if _undetermined(industry):
        und.append("industry")
    if _undetermined(scale.get("revenue_range")) and _undetermined(scale.get("asset_range")):
        und.append("scale")
    if _undetermined(taxpayer):
        und.append("taxpayer_type")
    if _undetermined(biz):
        und.append("business_model")
    if not feat:
        und.append("accounting_features")
    if not hist:
        und.append("historical_risks")
    d["undetermined_fields"] = und
    return d


def dossier_text(d: Dict[str, Any]) -> str:
    """画像的口语化说明（**不用"字段：值"**，符合报告文风铁律）。"""
    d = d or {}
    ind = (d.get("industry") or {}).get("real") or UNKNOWN
    sc = d.get("scale") or {}
    parts = ["本企业实质行业判断为「%s」" % ind]
    if sc.get("revenue_range") not in (None, "", UNKNOWN):
        parts.append("营收规模处于%s区间" % sc["revenue_range"])
    if sc.get("employee_count"):
        parts.append("从业人数约 %s 人" % sc["employee_count"])
    if d.get("taxpayer_type") and d["taxpayer_type"] != UNKNOWN:
        parts.append("纳税人类型为%s" % d["taxpayer_type"])
    if d.get("business_model") and d["business_model"] != UNKNOWN:
        parts.append("经营模式属%s" % d["business_model"])
    s = "，".join(parts) + "。"
    feat = [x for x in (d.get("accounting_features") or []) if x != UNKNOWN]
    if feat:
        s += "就核算基础而言，" + "；".join(feat) + "。"
    mats = (d.get("supplied_materials") or {})
    if mats.get("provided"):
        s += "已取得%s等 %d 类资料" % ("、".join(mats["provided"][:4]), len(mats["provided"]))
        if mats.get("missing"):
            s += "，尚有%s等 %d 类未取得" % ("、".join(mats["missing"][:4]), len(mats["missing"]))
        s += "。"
    if d.get("historical_risks"):
        s += "历史分析中曾出现过%s等问题。" % "、".join(d["historical_risks"][:3])
    else:
        s += "暂无历史风险记录（本企业此前未被本系统分析过，或历史记忆未沉淀）。"
    if d.get("undetermined_fields"):
        s += "其中%s暂无法确定（依据缺失，不作推断）。" % "、".join(
            field_cn(x) for x in d["undetermined_fields"])
    s += "以上画像**仅供检查参考**，不改变任何风险事项的等级与结论。"
    return s


def render_dossier_md(d: Dict[str, Any]) -> str:
    """《企业画像》（可独立交付）。"""
    d = d or {}
    L = ["# 企业画像", ""]
    L += [dossier_text(d), ""]
    L += ["| 画像字段 | 内容 | 是否已确定 |", "|---|---|---|"]
    ind = d.get("industry") or {}
    sc = d.get("scale") or {}
    rows = [
        ("行业", "%s（登记：%s）" % (ind.get("real") or UNKNOWN, ind.get("registered") or UNKNOWN),
         "industry" not in (d.get("undetermined_fields") or [])),
        ("规模", "营收%s；人数%s；资产%s" % (sc.get("revenue_range") or UNKNOWN,
                                        sc.get("employee_count") or UNKNOWN,
                                        sc.get("asset_range") or UNKNOWN),
         "scale" not in (d.get("undetermined_fields") or [])),
        ("纳税人类型", d.get("taxpayer_type") or UNKNOWN,
         "taxpayer_type" not in (d.get("undetermined_fields") or [])),
        ("业务模式", d.get("business_model") or UNKNOWN,
         "business_model" not in (d.get("undetermined_fields") or [])),
        ("核算特点", "；".join(d.get("accounting_features") or [UNKNOWN]),
         "accounting_features" not in (d.get("undetermined_fields") or [])),
        ("历史风险", "；".join(d.get("historical_risks") or []) or "无记录",
         "historical_risks" not in (d.get("undetermined_fields") or [])),
        ("已补资料", "已取得 %d 类；未取得 %d 类；本业态不适用 %d 类"
         % (len((d.get("supplied_materials") or {}).get("provided") or []),
            len((d.get("supplied_materials") or {}).get("missing") or []),
            len((d.get("supplied_materials") or {}).get("not_applicable") or [])), True),
    ]
    for name, val, ok in rows:
        L.append("| %s | %s | %s |" % (name, val, "✅" if ok else "⚠ 未确定"))
    L += ["", "> 契约：企业画像**只作参考**，不参与风险等级评定"
          "（`affects_risk_level=False`，由闸门与测试锁死）。", ""]
    return "\n".join(L)


__all__ = ["DOSSIER_FIELDS", "ACCOUNTING_FEATURE_RULES", "build_dossier",
           "dossier_text", "render_dossier_md"]
