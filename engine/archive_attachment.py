# -*- coding: utf-8 -*-
"""归档结构回填 —— **C 归档规范性门禁（§3.3）的唯一产出源**。

为什么需要这一层
----------------
归档束原本只在**独立入口** `/api/workpaper/generate` 产出
（`engine/workpaper_generator.build_archive_bundle`），一键分析链**从不回填**
⇒ C 门禁在一键分析产物上恒报 C1/C2/C5/C7/C8（编号 / 七类索引 / 签署栏 / 审计轨迹全缺），
`formal_workpaper_allowed` 永久为假（指令《报告质量全量治理》P1-5）。

本模块只做**回填**（把归档结构写进 `report_data["enterprise_readable_report"]`），
不新造任何判据与编号：

* 编号 —— 只经唯一权威 `engine/numbering`（**绝不自行拼接**）；
* 索引 —— 只经唯一权威 `engine/workpaper_generator.build_archive_bundle`；
* 签署栏 —— 消费 `engine/report_compliance.signature_block` 已写入的块（不覆盖签署人）；
* 审计轨迹 —— 四要素（谁/何时/改了什么/为什么改）**取不到就如实写"未采集"**，不填默认值。

铁律：① **幂等**（已有编号不再重号；重复调用安全）；② 取不到即如实登记 `indexes_missing`；
③ 失败**留痕**（返回 `ok=False` + error），绝不静默通过。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine import numbering as nb
from engine import quality_gates as qg
from engine import workpaper_generator as _wpg

__all__ = ["attach_archive_structure", "build_audit_trail", "VERSION"]

VERSION = "1.0.0"

#: 审计轨迹四要素之外的可追溯版本位（取不到写空串，不臆造）
_TRAIL_VERSION_FIELDS = ("source_data_version", "rule_version", "template_version", "skill_version")


def _now() -> str:
    """北京时间戳（唯一权威 `runtime_storage.now_cst`）。"""
    from runtime_storage import now_cst
    return now_cst()


def _resolve_cc_period(report_data: Dict[str, Any], company_code: Any, period: Any):
    """企业代码 / 期间归一 —— **别名解析交给 `numbering.NumberingService`**（单一权威）。

    报告里企业代码/期间有多个存放点（`identity.taxpayer_id` / `anchoring.credit_code` /
    `target_entity.uscc` / `report_data.company_code`）。本函数只负责**汇成一份候选字典**，
    具体取哪个键、怎么归一（去空格/大写/取期间月键）由 `numbering` 的别名表决定 ——
    避免在此另立一套"取哪个字段"的口径。
    """
    er = report_data.get("enterprise_readable_report")
    er = er if isinstance(er, dict) else {}
    ident = er.get("identity") if isinstance(er.get("identity"), dict) else {}
    anch = report_data.get("anchoring") if isinstance(report_data.get("anchoring"), dict) else {}
    te = report_data.get("target_entity") if isinstance(report_data.get("target_entity"), dict) else {}

    if company_code:
        cc: Any = company_code
    else:
        _CC_KEYS = ("unified_social_credit_code", "uscc", "credit_code", "taxpayer_id",
                    "company_code", "company_id")
        merged_cc: Dict[str, Any] = {}
        for src in (ident, anch, te, report_data):
            if isinstance(src, dict):
                for k in _CC_KEYS:
                    if src.get(k) and k not in merged_cc:
                        merged_cc[k] = src[k]
        cc = merged_cc

    if period:
        pd_: Any = period
    else:
        _P_KEYS = ("inspection_period", "period", "check_period", "期间")
        merged_p: Dict[str, Any] = {}
        for k in _P_KEYS:
            if report_data.get(k):
                merged_p.setdefault(k, report_data[k])
        # ⚠ `anchoring.period` 是资料份数描述（如"102份资料"）**不是期间**，故不并入
        for src in (ident, te):
            if isinstance(src, dict):
                for k in _P_KEYS:
                    if src.get(k) and k not in merged_p:
                        merged_p[k] = src[k]
        pd_ = merged_p
    return cc, pd_


def build_audit_trail(workpaper_no: str, *, operator: str = "", reason: str = "一键分析生成",
                      report_data: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """构造审计轨迹（≥1 条）。四要素齐备；身份/版本取不到即**如实写"未采集"**，不填默认值。"""
    rd = report_data if isinstance(report_data, dict) else {}
    _op = str(operator or "").strip() or "未提供操作人（系统自动分析，本次未采集操作人身份）"
    entry: Dict[str, Any] = {
        "at": _now(),
        "operator": _op,
        "action": "生成工作底稿",
        "target": str(workpaper_no or ""),
        "before": "",
        "after": "本轮扫描结果定稿并登记归档结构",
        "reason": str(reason or ""),
    }
    # 版本位（取不到写空串，宁缺勿假）
    gen = None
    er = rd.get("enterprise_readable_report")
    if isinstance(er, dict):
        gen = er.get("generated_date")
    entry["source_data_version"] = str(rd.get("report_fingerprint") or rd.get("analysis_fingerprint") or gen or "")
    lv = rd.get("_legal_versions") if isinstance(rd.get("_legal_versions"), dict) else {}
    entry["rule_version"] = str(lv.get("summary") or "")
    tpl = rd.get("report_template_meta") if isinstance(rd.get("report_template_meta"), dict) else {}
    entry["template_version"] = str(tpl.get("template_id") or tpl.get("id") or "")
    try:
        entry["skill_version"] = str(_wpg.SKILL_VERSION)
    except Exception:  # noqa: BLE001 —— 取不到即空串（不在审计轨迹里造版本号）
        entry["skill_version"] = ""
    return [entry]


def attach_archive_structure(report_data: Any, *, company_code: Any = "", period: Any = "",
                             version: int = 1, operator: str = "") -> Dict[str, Any]:
    """把归档结构（底稿号 / 风险编号 / 证据编号 / 七类索引 / 审计轨迹）回填进报告成品对象。

    幂等：已有编号不再重号；`audit_trail` 已有内容不覆盖。
    """
    if not isinstance(report_data, dict):
        return {"ok": False, "error": "report_data 不是 dict"}
    err = report_data.get("enterprise_readable_report")
    if not isinstance(err, dict):
        return {"ok": False, "error": "无 enterprise_readable_report，归档结构无从挂载"}

    cc, pd_ = _resolve_cc_period(report_data, company_code, period)
    svc = nb.NumberingService(cc, pd_)
    items = qg.iter_items(report_data)

    # ── C1 总底稿号（WB-TR-<企业代码>-<期间>-<版本>）──────────────────────────
    wp = str(err.get("workpaper_no") or report_data.get("workpaper_no") or svc.workpaper_no(version))
    err["workpaper_no"] = wp
    report_data["workpaper_no"] = wp

    # ── C2 逐项风险编号（WB-R-…；幂等）──────────────────────────────────────
    risk_n = 0
    for i, it in enumerate(items, 1):
        if isinstance(it, dict):
            if not (it.get("risk_no") or it.get("编号")):
                it["risk_no"] = svc.make("risk", i)
            risk_n += 1

    # ── C3 证据编号（WB-EV-…；幂等）────────────────────────────────────────
    ev_total = ev_new = 0
    for it in items:
        chain = it.get("evidence_chain") if isinstance(it, dict) and isinstance(it.get("evidence_chain"), dict) else {}
        for e in (chain.get("elements") or []):
            if not isinstance(e, dict):
                continue
            ev_total += 1
            if not e.get("evidence_no"):
                ev_new += 1
                e["evidence_no"] = svc.make("evidence", ev_total)
            if it.get("risk_no"):
                e.setdefault("risk_no", it["risk_no"])

    # ── C5 七类索引（唯一权威 build_archive_bundle）─────────────────────────
    try:
        bundle = _wpg.build_archive_bundle(report_data, company_code=cc, period=pd_, version=version)
        err["indexes"] = bundle.get("indexes") or {}
        missing = list(bundle.get("indexes_missing") or [])
    except Exception as exc:  # noqa: BLE001 —— 索引构建失败必须留痕（C5 会报红，不静默）
        err["indexes"] = {}
        missing = ["indexes: 构建失败 %s" % str(exc)[:120]]
        bundle = {}

    # ── C8 审计轨迹（已有内容不覆盖）───────────────────────────────────────
    _trail = err.get("audit_trail")
    if not isinstance(_trail, list) or not _trail:
        err["audit_trail"] = build_audit_trail(wp, operator=operator, report_data=report_data)

    return {
        "ok": True,
        "workpaper_no": wp,
        "company_code": svc.company_code,
        "period": svc.period,
        "items": len(items),
        "risk_numbered": risk_n,
        "evidence_total": ev_total,
        "evidence_newly_numbered": ev_new,
        "indexes": {k: len(v) for k, v in (err.get("indexes") or {}).items()},
        "indexes_missing": missing,
        "audit_entries": len(err.get("audit_trail") or []),
        "numbering_errors": list(svc.errors),
    }
