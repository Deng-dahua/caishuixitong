# -*- coding: utf-8 -*-
"""风险结果视图层 —— 列表 / 详情 / 统计（**只读**，不另建表、不改发现）。

## 数据来源（唯一）

风险发现**不是**另一张表：它读**真实产物载荷**
（`runtime_storage.offline_reports_root()` 下的 `company_{id}_full.json` 的
`enterprise_readable_report.confirmed_problems`），由 `engine/rule_executor.collect_from_report()`
归一（P0-5 已建立）。本模块**只做筛选/排序/分页/装配/统计**。

★ 收敛说明（2026-10-13，P0-6）：此前 `rules_api._findings_payload()` 自己实现了这份读盘逻辑；
  本轮把**读载荷的唯一实现**收到本模块 `load_payload()`，`rules_api` 改为薄转发
  ⇒ 两个页面（规则库 / 风险工作台）**同一份取数口径**，不会各自漂移。

## 缺失 ≠ 0

金额取不到（`tax_impact.available=false`）时**不按 0 元参与金额筛选**，
而是被排除并在结果里如实计数（`excluded_unknown_amount`）。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from engine import legal_extras as LE              # 案例/解读/问答材料读层（统一读路径）
from engine import legal_mapping as LM            # 法规⇄规则关联（唯一读路径；步骤 19）
from engine import risk_review as REVIEW
from engine import risk_scoring as SCORE
from engine import rule_executor as EXEC

__all__ = [
    "RiskServiceError", "load_payload", "collect", "company_of_project",
    "require_company",
    "list_risks", "get_risk", "stats", "period_of", "metadata",
    "SORTS", "SORT_CN",
]

#: 排序键（★ 唯一权威：新增一种排序只加这里一处）
SORTS: Tuple[str, ...] = ("priority", "seq", "amount", "level", "risk_no")

SORT_CN: Dict[str, str] = {
    "priority": "综合排序分",
    "seq": "事项序号",
    "amount": "涉税金额",
    "level": "风险等级",
    "risk_no": "风险编号",
}


class RiskServiceError(Exception):
    """视图层错误（`status` 为 HTTP 语义码，由 API 层转 `HTTPException`）。"""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = int(status)


# ══════════════════════════════════════════════════════════════════════════
# 取数（唯一实现）
# ══════════════════════════════════════════════════════════════════════════
def require_company(company_id: Any, session: Any) -> int:
    try:
        cid = int(company_id)
    except Exception:                                         # noqa: BLE001
        raise RiskServiceError("company_id 非法", 400) from None
    if cid <= 0:
        raise RiskServiceError("company_id 非法", 400)
    checker = getattr(session, "can_access_company", None)
    if callable(checker) and not checker(cid):
        # ★ 404（不是 403）：与 P0-1/P0-2 同一口径，不泄露存在性
        raise RiskServiceError("账套不存在或无权访问", 404)
    return cid


def load_payload(company_id: Any, session: Any) -> Dict[str, Any]:
    """读该账套的**真实产物载荷**。

    ★ 路径取唯一权威 `runtime_storage.offline_reports_root()`（不写死产物目录 —— 该函数
      明确要求派生物目录跟随 `APP_DATA_DIR`，写死会在隔离实例里越界读生产产物）。
    读不到 ⇒ `{available: False, reason: ...}`（**不返回编造的空列表**）。
    """
    cid = require_company(company_id, session)
    try:
        # ★ 2026-10-14（S12-DEC-002）：路径**薄转发**到唯一权威 `engine.report_payload`
        #   —— 此前本模块自己拼 `os.path.join(offline_reports_root(), "company_%d_full.json")`，
        #   与落盘方（`main._persist_one_click_result` → `report_payload.dump_payload`）
        #   各写一份字面量 ⇒ 读写两侧可能各自漂移。现收敛为同一处。
        from engine.report_payload import payload_path            # noqa: PLC0415
        path = payload_path(cid)
    except Exception as exc:                                      # noqa: BLE001
        return {"available": False, "reason": "载荷路径权威不可用：%s" % exc}
    if not os.path.exists(path):
        return {"available": False,
                "reason": "该账套尚未生成报告载荷（请先执行一键分析）",
                "path_hint": os.path.basename(path)}
    try:
        import json as _json                                      # noqa: PLC0415
        with open(path, encoding="utf-8") as fh:
            payload = _json.load(fh) or {}
    except Exception as exc:                                      # noqa: BLE001
        return {"available": False, "reason": "载荷读取失败：%s" % exc}
    return {"available": True, "payload": payload, "generated_at": _mtime(path)}


def _mtime(path: str) -> str:
    try:
        import datetime                                           # noqa: PLC0415
        return datetime.datetime.fromtimestamp(os.path.getmtime(path)).isoformat(
            timespec="seconds")
    except Exception:                                             # noqa: BLE001
        return ""


def collect(company_id: Any, session: Any) -> Dict[str, Any]:
    """归集发现/证据/执行 + 复核态。载荷不可用 ⇒ `available=False`（附原因）。"""
    got = load_payload(company_id, session)
    if not got.get("available"):
        return {"available": False, "reason": got.get("reason", ""),
                "generated_at": "", "findings": [], "evidences": [],
                "executions": [], "summary": EXEC.execution_summary([])}
    res = EXEC.collect_from_report(got["payload"])
    return {"available": True, "generated_at": got.get("generated_at", ""),
            "findings": res["findings"], "evidences": res["evidences"],
            "executions": res["executions"], "summary": res["summary"]}


def company_of_project(project_id: Any, session: Any, *, engine: Any = None) -> int:
    """项目 → 账套。**沿用 P0-1 项目可见性**（跨租户 ⇒ 404，不另立口径）。"""
    try:
        from engine import project_service as PSVC                 # noqa: PLC0415
    except Exception as exc:                                       # noqa: BLE001
        raise RiskServiceError("项目服务不可用：%s" % exc, 500) from exc
    try:
        proj = PSVC.get_project(project_id, session, engine=engine,
                                with_members=False, with_logs=False)
    except getattr(PSVC, "ProjectError") as exc:
        raise RiskServiceError(getattr(exc, "message", str(exc)),
                               int(getattr(exc, "status", 404))) from exc
    cid = int(proj.get("company_id") or 0)
    if cid <= 0:
        # ★ 2026-10-15 账套退役：自动绑定内部账套，不再拒绝
        from engine.project_service import ensure_company_for_project as _ensure   # noqa: PLC0415
        cid = _ensure(session, proj, engine=engine)
    return cid


# ══════════════════════════════════════════════════════════════════════════
# 期间 / 金额 / 等级辅助
# ══════════════════════════════════════════════════════════════════════════
def period_of(risk_no: Any) -> str:
    """从风险编号取期间（编号结构 `WB-R-{统一社会信用代码}-{期间}-{序号}`）。

    ★ 用唯一权威 `engine/numbering` 解析结构，不自行切字符串猜格式。
    """
    try:
        from engine.numbering import NumberingService, load_rules   # noqa: PLC0415
        ns = NumberingService("", "", rules=load_rules())
        parsed = ns.parse(risk_no) or {}
        body = str(parsed.get("body") or "")
        if not body:
            return ""
        parts = body.split(ns.connector)
        return parts[-1] if len(parts) >= 2 else ""
    except Exception:                                              # noqa: BLE001
        return ""


def _amount(f: Dict[str, Any]) -> Optional[float]:
    return SCORE.amount_of(f)


def _severity_key(f: Dict[str, Any]) -> int:
    """等级轻重标度 —— 取**唯一权威** `engine/risk_levels.SEVERITY`（不另立一套）。"""
    from engine.risk_levels import SEVERITY                        # noqa: PLC0415
    return int(SEVERITY.get(str(f.get("risk_level") or ""), -1))


# ══════════════════════════════════════════════════════════════════════════
# 列表
# ══════════════════════════════════════════════════════════════════════════
def _filter(findings: List[Dict[str, Any]], states: Dict[str, Dict[str, Any]], *,
            tax: str = "", level: str = "", state: str = "", period: str = "",
            amount_min: Any = None, amount_max: Any = None, q: str = "",
            reviewed: str = "") -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """筛选 + **如实计数**（被筛掉的量必须可见，不静默）。"""
    stats = {"input": len(findings), "excluded_unknown_amount": 0,
             "excluded_no_period": 0, "excluded_no_risk_no": 0}
    out: List[Dict[str, Any]] = []
    t = str(tax or "").strip()
    lv = str(level or "").strip()
    st = str(state or "").strip()
    pd = str(period or "").strip()
    kw = str(q or "").strip().lower()
    rv = str(reviewed or "").strip().lower()
    try:
        amin = float(amount_min) if amount_min not in (None, "") else None
    except Exception:                                              # noqa: BLE001
        raise RiskServiceError("amount_min 非法（须为数字）", 400) from None
    try:
        amax = float(amount_max) if amount_max not in (None, "") else None
    except Exception:                                              # noqa: BLE001
        raise RiskServiceError("amount_max 非法（须为数字）", 400) from None

    for f in findings:
        if lv and str(f.get("risk_level") or "") != lv:
            continue
        if t:
            taxes = [str(x) for x in (f.get("taxes") or [])]
            if not taxes:
                taxes = [str(f.get("tax") or "")] if f.get("tax") else []
            if t not in taxes:
                continue
        rn = str(f.get("risk_no") or "").strip()
        if pd:
            if not rn:
                stats["excluded_no_risk_no"] += 1
                continue
            got_pd = period_of(rn)
            if not got_pd:
                stats["excluded_no_period"] += 1
                continue
            if got_pd != pd:
                continue
        if st or rv:
            cur_state = (states.get(rn) or {}).get("state") if rn else None
            cur_state = cur_state or REVIEW.DEFAULT_STATE
            if st and cur_state != st:
                continue
            if rv in ("yes", "true", "1"):
                if not (states.get(rn) or {}).get("reviewed"):
                    continue
            elif rv in ("no", "false", "0"):
                if (states.get(rn) or {}).get("reviewed"):
                    continue
        if amin is not None or amax is not None:
            amt = _amount(f)
            if amt is None:
                stats["excluded_unknown_amount"] += 1
                continue
            if amin is not None and amt < amin:
                continue
            if amax is not None and amt > amax:
                continue
        if kw:
            hay = " ".join([str(f.get("title") or ""), str(f.get("rule_id") or ""),
                            str(f.get("redline_id") or ""), rn])
            if kw not in hay.lower():
                continue
        out.append(f)
    return out, stats


def _sort(findings: List[Dict[str, Any]], sort: str, order: str) -> List[Dict[str, Any]]:
    st = str(sort or "priority").strip()
    if st not in SORTS:
        raise RiskServiceError("未知排序键：%r（合法值：%s）"
                               % (st, "、".join(SORTS)), 400)
    desc = str(order or "desc").strip().lower() != "asc"

    def key(f: Dict[str, Any]):
        if st == "priority":
            sc = f.get("priority_score")
            return (sc is None, -(sc or 0))
        if st == "seq":
            return (False, int(f.get("seq") or 0))
        if st == "amount":
            amt = _amount(f)
            return (amt is None, -(amt or 0))
        if st == "level":
            return (False, -_severity_key(f))
        return (False, str(f.get("risk_no") or ""))

    ordered = sorted(findings, key=key)
    if not desc and st in ("seq", "risk_no"):
        ordered = sorted(findings, key=lambda f: key(f)[1])
    elif not desc:
        ordered = list(reversed(ordered))
    return ordered


def list_risks(company_id: Any, session: Any, *, tax: str = "", level: str = "",
               state: str = "", period: str = "", amount_min: Any = None,
               amount_max: Any = None, q: str = "", reviewed: str = "",
               sort: str = "priority", order: str = "desc",
               page: int = 1, page_size: int = 20,
               with_score: bool = True) -> Dict[str, Any]:
    """风险列表（筛选 + 排序 + 分页）。载荷不可用 ⇒ `available=False` + 原因。"""
    got = collect(company_id, session)
    if not got.get("available"):
        return {"available": False, "reason": got.get("reason", ""),
                "items": [], "total": 0, "page": 1, "page_size": 0,
                "generated_at": "", "filter_stats": {}, "review_summary": {}}
    states = REVIEW.states_of(company_id)
    items, fstats = _filter(got["findings"], states, tax=tax, level=level, state=state,
                            period=period, amount_min=amount_min, amount_max=amount_max,
                            q=q, reviewed=reviewed)
    if with_score:
        items = SCORE.stamp_all(items)
    items = _sort(items, sort, order)

    # ★ 2026-10-15（用户裁定）：每条补「检出等级」——
    #   封顶前的原始检出强度（capped_by_grade_from 即封顶前等级），
    #   旧载荷无需重析即时生效；呈现层据此明确「涉嫌风险」。
    for f in items:
        f["detected_risk_level"] = (f.get("risk_level_capped_by_grade_from")
                                    or f.get("risk_level") or "")
    # 复核态并入每条（列表也要能直接看到处置状态）
    for f in items:
        rn = str(f.get("risk_no") or "")
        cur = states.get(rn) or {}
        f["review_state"] = cur.get("state") or REVIEW.DEFAULT_STATE
        f["review_state_cn"] = REVIEW.STATE_CN.get(f["review_state"], f["review_state"])
        f["reviewed"] = bool(cur.get("reviewed"))
        f["manual_required"] = bool(cur.get("manual_required"))
        f["rectification_no"] = str(cur.get("rectification_no") or "")
        # ★ 金额由**后端**给出（唯一权威 `risk_scoring.amount_of`）⇒ 前端不再自行求和
        #   （否则"金额合计"会有第二份实现，前端口径漂移时无人发现）
        amt = _amount(f)
        f["tax_impact_amount"] = amt
        f["amount_known"] = amt is not None
        # ★ 2026-10-15（步骤 19）法规关联：列表只带**条款定位**（不带正文，控体积）；
        #   正文在详情接口给（`get_risk`）。缺失 ⇒ 空列表，如实（不伪造依据）。
        _lp = LM.provisions_of(f.get("rule_id") or f.get("redline_id"))
        f["legal_provision_ids"] = [p["provision_id"] for p in _lp if p["provision_id"]]
        f["legal_provisions_n"] = len(_lp)

    total = len(items)
    try:
        pg = max(1, int(page))
        ps = max(1, int(page_size))
    except Exception:                                              # noqa: BLE001
        pg, ps = 1, 20
    start = (pg - 1) * ps
    page_items = items[start:start + ps]

    # ★ 状态分布须以**全部发现**为分母（无复核记录的默认「待处理」也必须计入）。
    #   实测缺陷（2026-10-13）：原先只折叠 `states`（= 有事件的行）⇒ 未经复核的事项
    #   一条都不计，出现 `items[0].review_state=pending` 而 `by_state[pending]=0` 的自相矛盾。
    by_state = {s: 0 for s in REVIEW.REVIEW_STATES}
    reviewed_n = 0
    for f in got["findings"]:
        rn_f = str(f.get("risk_no") or "")
        cur_f = states.get(rn_f) or {}
        st_f = cur_f.get("state") or REVIEW.DEFAULT_STATE
        if st_f in by_state:
            by_state[st_f] += 1
        if cur_f.get("reviewed"):
            reviewed_n += 1
    return {
        "available": True, "company_id": int(company_id),
        "generated_at": got.get("generated_at", ""),
        "total": total, "page": pg, "page_size": ps,
        "pages": (total + ps - 1) // ps if total else 0,
        "items": page_items,
        "filter_stats": fstats,
        "review_summary": {"by_state": by_state,
                           "by_state_cn": {REVIEW.STATE_CN[s]: n
                                           for s, n in by_state.items()},
                           "reviewed_total": reviewed_n,
                           "reviewed_ratio": (round(reviewed_n
                                                    / float(len(got["findings"])), 4)
                                              if got["findings"] else 0.0),
                           "note": ("状态分布以**全部风险事项**为分母（未复核的计「待处理」）；"
                                    "筛选条件**不改变**该分布。")},
        "execution_summary": got["summary"],
        "sort": sort, "sort_cn": SORT_CN.get(sort, sort), "order": "asc" if order == "asc" else "desc",
        "note": ("发现读自真实产物载荷 `company_%d_full.json`；复核态读自 "
                 "`data/risk_reviews.jsonl`（append-only 折叠）。排序分只作排序、不改等级。"
                 % int(company_id)),
    }


# ══════════════════════════════════════════════════════════════════════════
# 详情
# ══════════════════════════════════════════════════════════════════════════
def _related_materials(finding: Dict[str, Any], *, limit: int = 5) -> Dict[str, Any]:
    """发现 → 相关官方材料（案例/解读/问答）。

    ★★ 粒度**两级优先**（2026-10-15 补采材料正文后升级）：
      ① 该规则**已确证条款**有**条款级**材料（材料正文出现「法名紧邻条号」且指该条款）
         ⇒ 返回它们并标 `granularity="provision"`；
      ② 无条款级命中 ⇒ **如实退回**法规级并标 `granularity="law"`。
      两级都**不等于**"该案例适用本条款" ⇒ 仅作参考线索，**不作定性依据**。
      这一点在 `note` 与每个 item 的 `granularity` 里都说清（防前端误用）。
    """
    rid = finding.get("rule_id") or finding.get("redline_id")
    provs = LM.provisions_of(rid)
    if not provs:
        return {"total": 0, "items": [], "law_codes": [], "granularity": "none",
                "note": "该规则**无可确证条款** ⇒ 无法定位相关材料（不猜）。"}
    codes: List[str] = []
    for p in provs:
        c = LE.law_code_of(p.get("provision_id"))
        if c and c not in codes:
            codes.append(c)
    seen, items, total = set(), [], 0
    exact_pids: List[str] = []
    for p in provs:                                             # ① 条款级优先
        pid = str(p.get("provision_id") or "")
        if not pid:
            continue
        got = LE.for_provision(pid, limit=limit)
        if got.get("granularity") == "provision":
            exact_pids.append(pid)
        if got.get("granularity") != "provision":
            continue                                            # 退回级的留给 ② 统一取
        total += int(got.get("total") or 0)
        for m in (got.get("items") or []):
            mid = m.get("material_id")
            if mid and mid not in seen:
                seen.add(mid)
                items.append(m)
    if not items:                                               # ② 如实退回法规级
        for c in codes:
            got = LE.for_law(c, limit=limit)
            total += int(got.get("total") or 0)
            for m in (got.get("items") or []):
                mid = m.get("material_id")
                if mid in seen:
                    continue
                seen.add(mid)
                items.append(m)
    items.sort(key=lambda m: str(m.get("published_at") or ""), reverse=True)
    gran = "provision" if exact_pids else "law"
    return {"total": total, "items": items[:limit], "law_codes": codes,
            "granularity": gran, "available": LE.available(),
            "matched_provision_ids": exact_pids,
            "note": ("材料与法规的关联**到条款级**（材料正文出现「法名紧邻条号」的显式引用，"
                     "且指向本规则已确证的条款）；仍**不代表个案适用本条款**"
                     "⇒ 仅作参考线索，不作定性依据。"
                     if gran == "provision" else
                     "材料与法规的关联**只到法规级**（材料显式引用了该法，但正文未出现"
                     "「法名紧邻本规则条款号」的写法）；**不代表其适用本条款**"
                     "⇒ 仅作参考线索，不作定性依据。")}


def _find(findings: List[Dict[str, Any]], risk_id: Any) -> Optional[Dict[str, Any]]:
    """按 `risk_no`（优先）或数字 `seq` 定位一条发现。"""
    s = str(risk_id or "").strip()
    if not s:
        return None
    for f in findings:
        if str(f.get("risk_no") or "").strip() == s:
            return f
    if s.isdigit():
        for f in findings:
            if int(f.get("seq") or 0) == int(s):
                return f
    return None


def get_risk(risk_id: Any, company_id: Any, session: Any, *,
             with_score: bool = True) -> Dict[str, Any]:
    """风险详情：发现 + 评分 + 证据链 + 规则 + 法规依据 + 建议 + 复核态与历史。

    「每个风险必须可解释、可追溯」⇒ 明细表（`detail_table` / `narrative_paragraphs`）
    与 `self_doubt`（自我怀疑清单）**原样带上**，不截断、不摘要。
    """
    got = collect(company_id, session)
    if not got.get("available"):
        raise RiskServiceError(got.get("reason", "载荷不存在"), 404)
    hit = _find(got["findings"], risk_id)
    if hit is None:
        raise RiskServiceError("风险事项不存在：%s（可能尚未分析或编号已变更）"
                               % str(risk_id), 404)
    rn = str(hit.get("risk_no") or "")
    f = SCORE.stamp(hit) if with_score else dict(hit)

    # 规则侧（版本 / 法规依据 / 层）—— 有则带上，无则**如实空**，绝不编造
    rule: Dict[str, Any] = {}
    for rid in (hit.get("rule_id"), hit.get("redline_id")):
        if not rid:
            continue
        try:
            from engine import rule_catalog as CAT                 # noqa: PLC0415
            rule = CAT.get(rid)
            break
        except Exception:                                          # noqa: BLE001
            continue

    evidences = [e for e in got["evidences"]
                 if int(e.get("finding_seq") or 0) == int(hit.get("seq") or 0)]
    cur = REVIEW.get(rn, company_id) if rn else dict(REVIEW._blank(""))

    def _i(v: Any) -> Optional[int]:
        """取整（载荷里 `evidence_have/need` 是**条数**，不是清单）。"""
        try:
            return int(v)
        except Exception:                                        # noqa: BLE001
            return None

    def _l(v: Any) -> List[Any]:
        return list(v) if isinstance(v, list) else []

    def _d(v: Any) -> Any:
        """原样透传（dict / list 都可能是；**不臆测形态、不改写**）。"""
        return v if isinstance(v, (dict, list)) else (v if v else {})

    return {
        "available": True,
        "company_id": int(company_id),
        "generated_at": got.get("generated_at", ""),
        "risk_id": rn or str(hit.get("seq") or ""),
        "risk_no": rn,
        "seq": int(hit.get("seq") or 0),
        "finding": f,
        "scoring": SCORE.score(hit),
        "evidences": evidences,
        "evidence_gap": {
            "have_count": _i(hit.get("evidence_have")),
            "need_count": _i(hit.get("evidence_need")),
            "direct_missing": str(hit.get("direct_missing") or ""),
            "missing_materials": _l(hit.get("missing_materials")),
            "missing_material_names": _l(hit.get("missing_material_names")),
            "verify_materials": _l(hit.get("verify_materials")),
            "note": ("`have_count` / `need_count` 是**条数**（载荷里本就是整数计数，"
                     "不是清单）；缺失资料为字符串原文，原样呈现不切分、不归纳。"),
        },
        "rule": ({"rule_id": rule.get("rule_id"), "name": rule.get("name"),
                  "layer": rule.get("layer"), "version": rule.get("version"),
                  "version_registered": rule.get("version_registered"),
                  "legal_basis_ref": rule.get("legal_basis_ref"),
                  "legal_basis_placeholder": bool(
                      any(x.get("placeholder") for x in (rule.get("legal_basis_ref") or []))),
                  "source_cn": rule.get("source_cn"),
                  "authority_cn": rule.get("authority_cn"),
                  # ★ 2026-10-15（步骤 19）**已确证**的法规条款（含条款正文，可复核）
                  "legal_provisions": LM.provisions_of(
                      rule.get("rule_id") or hit.get("redline_id"))} if rule else {}),
        "rule_found": bool(rule),
        # ★ 2026-10-15（步骤 19）风险发现 → 法规条款（条款 ID + 原文 + 来源），
        #   与 rule.legal_basis_ref（作者口径）**并列**、互不覆盖；查不到即空并说明原因。
        "legal_basis": LM.for_finding(hit),
        # ★ 相关官方材料（案例/解读/问答）—— **法规级**关联，参考线索，不作定性依据
        "related_materials": _related_materials(hit),
        "review": cur,
        "trace": {
            "risk_no": rn,
            "rule_id": str(hit.get("rule_id") or ""),
            "redline_id": str(hit.get("redline_id") or ""),
            "trace_id": str(hit.get("trace_id") or ""),
            # ★ 原样透传（载荷里 detail_table 是 {columns, rows}、trigger_determination /
            #   child_item_audit 是 dict；此处不假设形态，避免把结构改坏）
            "detail_table": _d(hit.get("detail_table")),
            "narrative_paragraphs": _l(hit.get("narrative_paragraphs")),
            "trigger_determination": _d(hit.get("trigger_determination")),
            "child_item_audit": _d(hit.get("child_item_audit")),
        },
        "self_doubt": _d(hit.get("self_doubt")),
        "suggestion": str(hit.get("suggestion") or ""),
        "note": ("规则未在目录中 ⇒ `rule_found=false`（不编造法规依据）。"
                 if not rule else
                 ("规则法规依据为**占位值**（候选未入库），前端须知为占位。"
                  if any(x.get("placeholder") for x in (rule.get("legal_basis_ref") or []))
                  else "")),
    }


# ══════════════════════════════════════════════════════════════════════════
# 统计
# ══════════════════════════════════════════════════════════════════════════
def stats(company_id: Any, session: Any) -> Dict[str, Any]:
    """风险统计（等级 / 税种 / 复核状态 / 金额分档 / 未处置金额）。"""
    got = collect(company_id, session)
    if not got.get("available"):
        return {"available": False, "reason": got.get("reason", "")}
    findings = got["findings"]
    states = REVIEW.states_of(company_id)

    by_level: Dict[str, int] = {}
    by_tax: Dict[str, int] = {}
    by_band: Dict[str, int] = {}
    band_amount: Dict[str, float] = {}
    bands = ((SCORE.config().get("bands") or {}).get("amount") or [])
    amount_total = 0.0
    amount_unknown = 0
    for f in findings:
        # ★ 2026-10-15（用户裁定）：统计按**检出等级**（封顶前），与呈现一致——
        #   未定性条目受控等级为"低风险"，若按它统计会把 2 高/9 中全部显示成"低"。
        lv = str(f.get("detected_risk_level")
                 or f.get("risk_level_capped_by_grade_from")
                 or f.get("risk_level") or "未标注")
        by_level[lv] = by_level.get(lv, 0) + 1
        taxes = [str(x) for x in (f.get("taxes") or [])] or (
            [str(f.get("tax"))] if f.get("tax") else ["未标注"])
        for t in taxes:
            by_tax[t] = by_tax.get(t, 0) + 1
        amt = _amount(f)
        if amt is None:
            amount_unknown += 1
            continue
        amount_total += amt
        label = "超出分档上限"
        for b in bands:
            mx = b.get("max")
            if mx is None or amt <= float(mx):
                label = str(b.get("label") or "")
                break
        by_band[label] = by_band.get(label, 0) + 1
        band_amount[label] = round(band_amount.get(label, 0.0) + amt, 2)

    by_state = {s: 0 for s in REVIEW.REVIEW_STATES}
    pending_amount = 0.0
    pending_amount_unknown = 0
    for f in findings:
        rn = str(f.get("risk_no") or "")
        st = (states.get(rn) or {}).get("state") or REVIEW.DEFAULT_STATE
        if st in by_state:
            by_state[st] += 1
        if st == REVIEW.DEFAULT_STATE:
            amt = _amount(f)
            if amt is None:
                pending_amount_unknown += 1
            else:
                pending_amount += amt

    reviewed = sum(1 for x in states.values() if x.get("reviewed"))
    return {
        "available": True, "company_id": int(company_id),
        "generated_at": got.get("generated_at", ""),
        "total": len(findings),
        "by_level": by_level,
        "by_tax": dict(sorted(by_tax.items(), key=lambda kv: -kv[1])),
        "by_state": by_state,
        "by_state_cn": {REVIEW.STATE_CN[s]: n for s, n in by_state.items()},
        "by_amount_band": by_band,
        "amount_by_band": band_amount,
        "amount_total": round(amount_total, 2),
        "amount_unknown_count": amount_unknown,
        "pending_amount_total": round(pending_amount, 2),
        "pending_amount_unknown_count": pending_amount_unknown,
        "reviewed_total": reviewed,
        "reviewed_ratio": round(reviewed / float(len(findings)), 4) if findings else 0.0,
        "rectification_total": len(REVIEW.rectifications(company_id)),
        "execution_summary": got["summary"],
        "notes": {
            "amount_unknown": ("金额取不到（`tax_impact.available=false`）的条数：%d —— "
                               "**未按 0 元计入金额合计**。" % amount_unknown),
            "pending_amount_unknown": ("待处理中金额取不到：%d 条，未计入待处理金额合计。"
                                       % pending_amount_unknown),
            "level_authority": "等级唯一权威 engine/risk_levels.py（5 档）；复核**不改等级**。",
            "state_authority": "处置状态唯一权威 engine/risk_review.py（5 态）。",
        },
    }


def metadata() -> Dict[str, Any]:
    """视图层字典（排序键 + 复核字典 + 口径说明）。"""
    from engine.risk_levels import LEGAL_LEVELS                     # noqa: PLC0415
    return {
        "sorts": [{"value": s, "label": SORT_CN[s]} for s in SORTS],
        "review": REVIEW.metadata(),
        # 等级候选取**唯一权威**（不硬编码一份，否则新增一档要改两处）
        "levels": [{"value": k, "label": k} for k in LEGAL_LEVELS],
        "amount_bands": [b.get("label") for b in
                         ((SCORE.config().get("bands") or {}).get("amount") or [])],
        "note": ("列表/详情/统计的数据来源 = 真实产物载荷（`rule_executor.collect_from_report`）"
                 "+ 复核事件流（`risk_review`）。本模块**不产生第三种事实**。"),
    }
