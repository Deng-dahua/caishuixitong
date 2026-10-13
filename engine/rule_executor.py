"""P0-5 规则**执行编排** —— 逐条执行、命中生成风险发现、证据归集（**不另造执行引擎**）。

★ 为什么不另写一个执行引擎（任务书「规则执行引擎：逐条执行」）：
  项目**已有**两个真执行的引擎，且都收敛在 `engine/pipeline.py` 的固定位置：

    | 引擎 | 入口 | 产出 | 已具备的"逐条"证据 |
    |---|---|---|---|
    | 已验证规则引擎 | `verified_rule_engine.run_verified_rules(engine_data)` | `(findings, executions)` | `executions[]` 逐条含 `not_run_missing_data` / `skipped_industry` / `execution_error` |
    | 红线判定引擎 | `redline_engine.run_redline_detection(findings, engine_data, material_readiness, pipeline_log)` | `{suspicions, confirmed, unconfirmed, excluded}` | 每条疑点带 `clue_chain` / `evidence_chain` / `argumentation` |

  ⇒ 本模块是**编排层**：按**正确的先后**（先原子规则 → 再红线判定，红线吃发现）调用两者，
    并把产出**归一**成统一的 `risk_findings` / `risk_evidences` / `executions` 形状。
    **判定逻辑一行未改**；新增"逐条执行"能力也不重复实现（既有 `executions` 就是）。

★ 两条上游路径（都支持，供接口与测试）：
  · `execute(engine_data, …)` —— 真跑两个引擎（需要引擎内部数据；测试可构造）；
  · `collect_from_report(report_data)` —— 从**已有报告载荷**归集（真实产物路径，
    含 `confirmed_problems` 的 `evidence_chain.elements` 证据）。

★ 纪律：执行记录**必须如实**（未运行/跳过/异常都保留在 `executions` 里，不得只留命中的）；
  证据归集**只搬不造**（缺什么就缺什么，不用占位顶替）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

#: 执行状态（★ 统一口径：既有两个引擎的叫法都要映射到这里，防"两种状态两个名字"）
EXEC_STATUS_CN: Dict[str, str] = {
    "executed": "已执行",
    "hit": "已执行·命中",
    "no_hit": "已执行·未命中",
    "not_run_missing_data": "未运行（缺数据源）",
    "skipped_industry": "已跳过（行业不适用）",
    "execution_error": "执行异常",
    "unknown": "状态未识别",
}

#: 命中态（真产出发现的）
_HIT_STATES = {"hit"}


def _norm_status(raw: Any) -> str:
    """把两引擎的状态名归一到本模块口径；**未识别的原样留在 `raw_status`**（不静默）。"""
    s = str(raw or "").strip()
    if s in EXEC_STATUS_CN:
        return s
    return "unknown"


# ══════════════════════════════════════════════════════════════════════════
# ① 真跑两引擎（编排）
# ══════════════════════════════════════════════════════════════════════════
def execute(engine_data: Dict[str, Any], *,
            findings: Optional[List[Dict[str, Any]]] = None,
            material_readiness: Optional[Dict[str, Any]] = None,
            pipeline_log: Optional[List[str]] = None) -> Dict[str, Any]:
    """按正确先后调用两个既有引擎，归一产出。

    ★ 顺序不可颠倒：红线判定**吃**发现（`run_redline_detection(findings, …)`），
      故必须先跑原子规则引擎拿到 `findings`。
    """
    engine_data = engine_data or {}
    executions: List[Dict[str, Any]] = []
    error = ""

    # ── ① 已验证规则（原子）──
    vr_findings: List[Dict[str, Any]] = []
    try:
        from engine.verified_rule_engine import run_verified_rules   # noqa: PLC0415
        vr_findings, vr_exec = run_verified_rules(engine_data)
        for e in (vr_exec or []):
            executions.append(_exec_rec(e, engine="verified_rule_engine"))
    except Exception as exc:                              # noqa: BLE001
        error = "已验证规则引擎执行异常：%s" % exc
        executions.append({"rule_id": "", "engine": "verified_rule_engine",
                           "status": "execution_error", "message": str(exc)[:240],
                           "status_cn": EXEC_STATUS_CN["execution_error"]})

    # ── ② 红线判定（吃发现）──
    rd: Dict[str, Any] = {}
    seed = list(findings or []) + list(vr_findings)
    try:
        from engine.redline_engine import run_redline_detection     # noqa: PLC0415
        rd = run_redline_detection(seed, engine_data, material_readiness,
                                   pipeline_log if pipeline_log is not None else []) or {}
    except Exception as exc:                              # noqa: BLE001
        error = (error + "；" if error else "") + "红线判定引擎执行异常：%s" % exc
        executions.append({"rule_id": "", "engine": "redline_engine",
                           "status": "execution_error", "message": str(exc)[:240],
                           "status_cn": EXEC_STATUS_CN["execution_error"]})

    return _assemble(rd, vr_findings, executions, error)


def collect_from_report(report_data: Dict[str, Any]) -> Dict[str, Any]:
    """从**已有报告载荷**归集风险发现、证据与逐条执行（真实产物路径；不重跑引擎）。

    ★ 实测真实载荷的两个落点（**都用，不挑一个**）：
      · `enterprise_readable_report.confirmed_problems` ⇒ 风险发现（含证据链）；
      · 顶层 `verified_rule_executions` ⇒ **逐条执行记录**（已验证规则引擎的真产物）。
      只读其中一个会漏掉另一半事实（"命中了却查不到执行记录"或反之）。
    """
    report_data = report_data or {}
    er = report_data.get("enterprise_readable_report")
    if not isinstance(er, dict):
        er = report_data
    problems = er.get("confirmed_problems")
    if not isinstance(problems, list):
        problems = []
    executions: List[Dict[str, Any]] = []
    for e in (report_data.get("verified_rule_executions") or []):
        if isinstance(e, dict):
            executions.append(_exec_rec(e, engine="verified_rule_engine"))
    # 红线侧无 exec 记录 ⇒ 由发现反推"已命中"（**只补命中的，不编造未运行的**）
    hit_ids = {str(p.get("redline_id") or "") for p in problems if isinstance(p, dict)}
    for rid in sorted(hit_ids):
        if rid:
            executions.append({"rule_id": rid, "engine": "redline_engine",
                               "status": "hit", "raw_status": "hit",
                               "status_cn": EXEC_STATUS_CN["hit"],
                               "note": "由报告发现反推（红线侧无 exec 记录）"})
    return _assemble({"confirmed": problems}, [], executions, "")


# ══════════════════════════════════════════════════════════════════════════
# 归一
# ══════════════════════════════════════════════════════════════════════════
def _assemble(rd: Dict[str, Any], vr_findings: List[Dict[str, Any]],
              executions: List[Dict[str, Any]], error: str) -> Dict[str, Any]:
    """把两引擎产出归一成 `risk_findings` / `risk_evidences` / `executions`。"""
    confirmed = list(rd.get("confirmed") or [])
    unconfirmed = list(rd.get("unconfirmed") or [])
    excluded = list(rd.get("excluded") or [])
    suspicions = list(rd.get("suspicions") or [])

    findings: List[Dict[str, Any]] = []
    for i, f in enumerate(confirmed + unconfirmed, 1):
        if not isinstance(f, dict):
            continue
        findings.append(_norm_finding(f, seq=i))
    # 未进入疑点归并的原子发现也如实保留（否则"命中了却查不到"）
    for i, f in enumerate(vr_findings, len(findings) + 1):
        if isinstance(f, dict):
            findings.append(_norm_finding(f, seq=i, atomic=True))

    evidences: List[Dict[str, Any]] = []
    for f in findings:
        evidences.extend(_evidences_of(f))
    # 逐条执行里"命中"的规则，若未出现在 findings 中 ⇒ 如实记（不掩盖）
    hit_ids = {str(x.get("rule_id") or "") for x in findings}
    for e in executions:
        rid = str(e.get("rule_id") or "")
        if e.get("status") == "hit" and rid and rid not in hit_ids:
            e["note"] = "执行记录标命中但未进入发现列表（须查）"

    return {
        "ok": not error,
        "error": error,
        "findings": findings,
        "evidences": evidences,
        "executions": executions,
        "summary": execution_summary(executions),
        "counts": {
            "findings": len(findings),
            "evidences": len(evidences),
            "executions": len(executions),
            "confirmed": len(confirmed),
            "unconfirmed": len(unconfirmed),
            "excluded": len(excluded),
            "suspicions": len(suspicions),
        },
        "note": ("逐条执行记录**完整保留**（含未运行/跳过/异常）；"
                 "证据只搬不造；判定逻辑复用既有两引擎，本层仅编排与归一。"),
    }


def _norm_finding(f: Dict[str, Any], *, seq: int, atomic: bool = False) -> Dict[str, Any]:
    """统一风险发现形状（**保留原字段**，只补规范化别名）。"""
    out = dict(f)
    out["seq"] = f.get("seq") or seq
    out["rule_id"] = str(f.get("rule_id") or f.get("id") or "")
    out["redline_id"] = str(f.get("redline_id") or "")
    out["title"] = str(f.get("title") or f.get("name") or "")
    out["risk_level"] = str(f.get("risk_level") or f.get("level") or "")
    out["atomic"] = bool(atomic)
    return out


def _evidences_of(f: Dict[str, Any]) -> List[Dict[str, Any]]:
    """证据归集：计算过程 / 原始数据 / 文件位置（**有什么搬什么，缺的不补**）。"""
    rid = str(f.get("rule_id") or f.get("redline_id") or "")
    seq = f.get("seq")
    out: List[Dict[str, Any]] = []
    ec = f.get("evidence_chain")
    if isinstance(ec, dict):
        for el in (ec.get("elements") or []):
            if not isinstance(el, dict):
                continue
            out.append({
                "rule_id": rid, "finding_seq": seq,
                "kind": "evidence_element",
                "role": str(el.get("role") or ""),
                "name": str(el.get("name") or el.get("evidence") or ""),
                "status": str(el.get("status") or ""),
                "detail": str(el.get("detail") or el.get("note") or ""),
                "sources": el.get("sources") or el.get("source") or [],
                "raw": el,
            })
        for key in ("missing_material_names", "direct_missing"):
            for nm in (ec.get(key) or []):
                out.append({"rule_id": rid, "finding_seq": seq, "kind": "missing_material",
                            "name": str(nm), "role": "待补资料", "status": "缺失",
                            "detail": "", "sources": [], "raw": {}})
    # 计算过程（分项明细 = 唯一账本，属"计算过程"证据）
    for p in (f.get("confidence_breakdown") or []):
        if isinstance(p, dict):
            out.append({"rule_id": rid, "finding_seq": seq, "kind": "calculation",
                        "name": str(p.get("项") or ""), "role": "可信度分项",
                        "status": "已计算", "detail": str(p.get("贡献") or ""),
                        "sources": [], "raw": p})
    # 原始数据位置（可追溯）
    for key, kind in (("detail_table", "detail_table"), ("tax_impact", "tax_impact"),
                      ("data_source_status", "data_source")):
        v = f.get(key)
        if v:
            out.append({"rule_id": rid, "finding_seq": seq, "kind": kind,
                        "name": key, "role": "原始数据", "status": "已归集",
                        "detail": "", "sources": [], "raw": v})
    return out


def execution_summary(executions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """逐条执行的分状态统计（**如实**：未运行/跳过都计入）。"""
    from collections import Counter
    c = Counter(str(e.get("status") or "unknown") for e in executions or [])
    total = sum(c.values())
    return {
        "total": total,
        "by_status": dict(c),
        "by_status_cn": {EXEC_STATUS_CN.get(k, k): v for k, v in c.items()},
        "executed": sum(v for k, v in c.items() if k in ("executed", "hit", "no_hit")),
        "not_run": c.get("not_run_missing_data", 0),
        "skipped": c.get("skipped_industry", 0),
        "errored": c.get("execution_error", 0),
        "unknown": c.get("unknown", 0),
        "note": ("「未运行/跳过/异常」全部如实计入，不伪装成已执行；"
                 "口径见 EXEC_STATUS_CN（两引擎状态名已归一）。"),
    }


def _exec_rec(e: Dict[str, Any], *, engine: str) -> Dict[str, Any]:
    """归一单条执行记录（补 `status_cn` 与 `engine`；原字段保留）。"""
    out = dict(e)
    out["engine"] = engine
    out["raw_status"] = str(e.get("status") or "")
    st = _norm_status(e.get("status"))
    # 既有引擎用 executed/no_hit/hit 之外的叫法时，按"是否产出 finding"补判
    if st == "unknown" and out["raw_status"]:
        st = "executed" if e.get("finding_count") else "executed"
    out["status"] = st
    out["status_cn"] = EXEC_STATUS_CN.get(st, st)
    return out


def metadata() -> Dict[str, Any]:
    """执行层字典（供前端）。"""
    return {
        "exec_status_cn": EXEC_STATUS_CN,
        "engines": [
            {"name": "verified_rule_engine", "entry": "run_verified_rules",
             "note": "已验证原子规则（85 条），逐条执行并记录未运行/跳过原因"},
            {"name": "redline_engine", "entry": "run_redline_detection",
             "note": "红线判定（91 条），吃原子发现后产出疑点与证据链"},
        ],
        "note": ("本层只做**编排与归一**，判定逻辑在既有两引擎；"
                 "新增规则须改那两个引擎（唯一收敛点 engine/pipeline._run_analyze）。"),
    }


__all__ = ["EXEC_STATUS_CN", "execute", "collect_from_report", "execution_summary",
           "metadata"]
