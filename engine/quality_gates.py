# -*- coding: utf-8 -*-
"""四道质量门禁总控 —— 证据链闭合度 / 逻辑一致性 / 归档规范性 / 模板整洁度。

WB-TRISK-2026-001 §六 的唯一实现。判据表 = `config/quality_gates.json`。

设计原则（与本项目既有约定一致）
--------------------------------
1. **判据数据驱动**：新增判据只改 `config/quality_gates.json`，本模块只提供谓词。
2. **SKIP ≠ PASS**（policy.skip_is_not_pass）：取不到数据必须报 SKIP 并写明原因；SKIP 计入未通过。
   绝不用默认值静默顶替 —— 这正是「看起来全绿其实没查」的病根。
3. **结构化优先**：能落到字段级比对的，不做文本比对。文本比对误报率高（实测：近似金额对
   11 组里 10 组是逐笔明细的正常差异），只用于模板整洁与渲染层。
4. **不修改入参**：门禁只读，产出 `GateFinding` / `GateResult`，修复由调用方或 `autofix` 决定。

分层
----
- `layer="data"`   ：作用于 `report_data`（结构化事实层），渲染前执行。
- `layer="render"` ：作用于导出物文本（HTML/PDF/Word），`render_text` 传入时执行，否则 SKIP。
- `layer="both"`   ：两层都查。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from engine import conclusion_grade as cg
from engine import numbering as nb
from engine import report_metrics as rm
from engine import risk_levels
from engine.fact_store import FactStore, get_store, KIND_AMOUNT, KIND_COUNT

__all__ = [
    "GateFinding", "GateResult",
    "gate_evidence_closure", "gate_logic_consistency", "gate_archive_spec", "gate_template_hygiene",
    "run_all_gates", "render_gate_report", "attach_to_report", "load_spec", "load_errors", "VERSION",
]

VERSION = "1.0.0"
_ROOT = Path(__file__).resolve().parent.parent
_CFG = _ROOT / "config" / "quality_gates.json"
_CACHE: Optional[Dict[str, Any]] = None
_LOAD_ERRORS: List[str] = []


def load_spec() -> Dict[str, Any]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    try:
        with open(_CFG, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict) or not data.get("gates"):
            _LOAD_ERRORS.append(f"{_CFG} 缺 gates 键")
            data = {}
    except Exception as exc:  # noqa: BLE001 —— 留痕后置空，由门禁自身报 SKIP
        _LOAD_ERRORS.append(f"读 {_CFG} 失败：{exc}")
        data = {}
    _CACHE = data
    return _CACHE


def load_errors() -> List[str]:
    load_spec()
    return list(_LOAD_ERRORS)


def gate_def(gate_id: str) -> Dict[str, Any]:
    for g in load_spec().get("gates") or []:
        if g.get("id") == gate_id:
            return g
    return {}


def _check_meta(gate_id: str, check_id: str) -> Dict[str, Any]:
    for c in gate_def(gate_id).get("checks") or []:
        if c.get("id") == check_id:
            return c
    return {"id": check_id, "severity": "ERROR", "layer": "data", "rule": "", "fix": ""}


# ---------------------------------------------------------------- 结果对象
@dataclass
class GateFinding:
    gate: str
    check_id: str
    severity: str
    layer: str
    message: str
    fix: str = ""
    sample: Any = None
    count: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate": self.gate, "check_id": self.check_id, "severity": self.severity,
            "layer": self.layer, "message": self.message, "fix": self.fix,
            "sample": self.sample, "count": self.count,
        }


@dataclass
class GateResult:
    gate: str
    code: str
    cn: str
    status: str = "PASS"                       # PASS / FAIL / SKIP
    findings: List[GateFinding] = field(default_factory=list)
    skips: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> List[GateFinding]:
        return [f for f in self.findings if f.severity == "ERROR"]

    @property
    def warns(self) -> List[GateFinding]:
        return [f for f in self.findings if f.severity == "WARN"]

    @property
    def passed(self) -> bool:
        # ★ SKIP 不计通过（policy.skip_is_not_pass）
        return self.status == "PASS" and not self.errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate": self.gate, "code": self.code, "cn": self.cn, "status": self.status,
            "passed": self.passed,
            "errors": len(self.errors), "warns": len(self.warns),
            "skips": list(self.skips), "stats": self.stats,
            "findings": [f.to_dict() for f in self.findings],
        }


def _err(res: GateResult, gate_id: str, cid: str, msg: str, sample: Any = None, count: int = 1) -> None:
    meta = _check_meta(gate_id, cid)
    res.findings.append(GateFinding(
        gate=gate_id, check_id=cid, severity=str(meta.get("severity") or "ERROR"),
        layer=str(meta.get("layer") or "data"), message=msg,
        fix=str(meta.get("fix") or ""), sample=sample, count=count,
    ))


# ---------------------------------------------------------------- 取数工具
def iter_items(report_data: Any) -> List[Dict[str, Any]]:
    """取报告主体条目（**唯一权威** = `report_metrics.report_surface_items`）。

    ★ 2026-10-08（P0-1）：本函数原来自带一套取数顺序，与产出端各取一套集合，
    造成"门禁判 A 集合、报告渲染 B 集合"的假绿/假红。现收敛为**薄转发**：
    取数口径只有一处（`engine/report_metrics.py`），门禁与产出天然同源。
    """
    return rm.report_surface_items(report_data)


def iter_texts(obj: Any, *, depth: int = 0, limit_depth: int = 14, out: Optional[List[str]] = None,
               char_limit: int = 3000000) -> List[str]:
    """递归收集所有字符串（迭代式，去环）。**不静默截断**：超限即停并追加标记。"""
    out = [] if out is None else out
    stack: List[Tuple[Any, int]] = [(obj, 0)]
    seen: set = set()
    trunc = False
    total = 0
    while stack:
        cur, d = stack.pop()
        if d > limit_depth:
            continue
        if isinstance(cur, str):
            total += len(cur)
            if total > char_limit:
                trunc = True
                break
            out.append(cur)
        elif isinstance(cur, dict):
            if id(cur) in seen:
                continue
            seen.add(id(cur))
            for v in cur.values():
                stack.append((v, d + 1))
        elif isinstance(cur, (list, tuple)):
            if id(cur) in seen:
                continue
            seen.add(id(cur))
            for v in cur:
                stack.append((v, d + 1))
    if trunc:
        out.append(f"<<TRUNCATED: 收集到 {total} 字符超过上限 {char_limit}，词表类判据未覆盖全部文本>>")
    return out


# ---------------------------------------------------------------- 报告正文域
#: 分节标记（`output_variants.report_text_from` 注入，仅供判定，**不是**用户可见文本）
_SECTION_MARK_RE = re.compile(r"^<<S:.*?>>$")


def report_surface(report_data: Any) -> Dict[str, Any]:
    """★报告正文域（scan_domain）—— 词表/残留/重复类判据的**唯一扫描范围**。

    ★★ 2026-10-09（P1-3 根因治理）：**扫描域必须与产出同口径**。

    旧实现按 `include_top_keys` 白名单取 `enterprise_readable_report` **全域** ——
    但该对象里混着前端**从不渲染**的深层块（`working_paper_report` / `resolution_ledger`，
    实测 `static/js/tax-doc-analysis.js` 零引用）⇒ 门禁在"用户根本看不到的字段"上判红
    （D5 实测 189 种重复段落中有 87 种只落在这些不渲染字段；D 门禁因此长期 FAIL）。
    同时 `report_data` 里还混着**上传的原始文件内容**（HTML/JS/CSS）与内部自检告警
    （实测 7314 处「未替换变量」全部来自一份上传的 HTML）。

    现收敛为**唯一权威 = 报告正文投影** `output_variants.report_text_from()`
    （与去重判据同源；用户铁律「用户可见域＝`report_text_from()`」）。新增可见字段时
    只需改投影一处，门禁与去重自动同口径 —— 不再维护第二份字段白名单。
    """
    spec = (load_spec().get("scan_domain") or {})
    char_limit = int(spec.get("max_chars") or 3000000)

    if not isinstance(report_data, dict):
        return {"texts": iter_texts(report_data, char_limit=char_limit), "sources": ["<non-dict>"],
                "truncated": False, "excluded_keys": []}

    from engine.output_variants import report_text_from
    cleaned: List[str] = []
    dropped = 0
    for ln in report_text_from(report_data).split("\n"):
        s = ln.strip()
        if not s:
            continue
        if _SECTION_MARK_RE.match(s):      # 分节标记仅供判定，不入扫描域
            dropped += 1
            continue
        cleaned.append(s)
    return {"texts": cleaned,
            "sources": ["<projection:output_variants.report_text_from>"],
            "truncated": False, "excluded_keys": [],
            "dropped_strings": dropped}


_AMOUNT_RE = re.compile(r"(?<![\d,])(\d{1,3}(?:,\d{3})+\.\d{2}|\d{2,}\.\d{2})(?![\d,])")


def _amounts(text: str) -> List[float]:
    vals: List[float] = []
    for m in _AMOUNT_RE.finditer(text or ""):
        try:
            vals.append(float(m.group(1).replace(",", "")))
        except Exception:  # noqa: BLE001
            continue
    return vals


# ================================================================ 门禁 A
def gate_evidence_closure(report_data: Any, *, renders: Optional[Dict[str, Any]] = None) -> GateResult:
    """证据链闭合度门禁（§3.1）。一票否决 + 闭合度阈值 + 替代程序。"""
    res = GateResult("A", "evidence_closure", "证据链闭合度门禁")
    items = iter_items(report_data)
    if not items:
        res.status = "SKIP"
        res.skips.append("取不到报告主体条目（confirmed_problems/findings 均为空或不存在）")
        return res

    alt = _load_alt_library()
    veto_items: List[Dict[str, Any]] = []
    zero_evidence_high: List[Dict[str, Any]] = []
    unclosed_high: List[Dict[str, Any]] = []
    det_hits: List[Dict[str, Any]] = []
    no_alt: List[Any] = []
    closure_bad: List[Dict[str, Any]] = []
    illegal_level: List[Dict[str, Any]] = []

    for it in items:
        a = cg.analyze_item(it)
        lvl_n = a.get("risk_level_normalized")
        trig = {h.get("id") for h in (a.get("veto_triggers") or [])}
        # A5 等级词表
        if a.get("illegal_level_word"):
            illegal_level.append({"seq": a["seq"], "raw": a["illegal_level_word"], "normalized": lvl_n})
        if a.get("veto_applies"):
            veto_items.append({
                "seq": a["seq"], "title": a.get("title"), "triggers": sorted(trig),
                "closure": a.get("closure"), "evidence_have": a.get("evidence_have"),
                "evidence_need": a.get("evidence_need"),
            })
            # A1：完全无证据（V1/V5）却带 中风险及以上
            if trig & {"V1", "V5"} and risk_levels.severity(lvl_n) >= risk_levels.severity("中风险"):
                zero_evidence_high.append({"seq": a["seq"], "risk_level": it.get("risk_level"),
                                           "closure": a.get("closure"), "have": a.get("evidence_have"),
                                           "triggers": sorted(trig)})
            # A9：闭合度已登记但未达阈值（V2）却带 中风险及以上
            if "V2" in trig and risk_levels.severity(lvl_n) >= risk_levels.severity("中风险"):
                unclosed_high.append({"seq": a["seq"], "risk_level": it.get("risk_level"),
                                      "closure": a.get("closure")})
        # A3 定性词（有否决触发时）
        if a.get("veto_applies") and a.get("determinative_words_hit"):
            det_hits.append({"seq": a["seq"], "words": a["determinative_words_hit"]})
        # A2 L3 门槛
        gid = str(it.get("conclusion_grade") or "").strip()
        if gid == cg.GRADE_L3 or a.get("conclusion_grade_mapped") == cg.GRADE_L3:
            cl = a.get("closure")
            if cl is None or float(cl) < cg.min_closure():
                closure_bad.append({"seq": a["seq"], "closure": cl})
        # A7 替代程序
        miss = it.get("missing_material_names") or []
        if miss:
            blob = json.dumps(it, ensure_ascii=False)
            if not any(any(x in blob for x in _alts_for(m, alt)) for m in _as_list(miss)):
                no_alt.append({"seq": a["seq"], "missing": miss})

    if illegal_level:
        _err(res, "A", "A5", f"{len(illegal_level)} 项风险等级为表外词（合法词表：{'/'.join(cg.legal_levels())}）",
             sample=illegal_level, count=len(illegal_level))
    if zero_evidence_high:
        _err(res, "A", "A1",
             f"{len(zero_evidence_high)} 项**无任何证据**（closure=0 / evidence_have=0）却仍带 中风险及以上等级",
             sample=zero_evidence_high, count=len(zero_evidence_high))
    if unclosed_high:
        _err(res, "A", "A9",
             f"{len(unclosed_high)} 项证据链未闭合（closure<{cg.min_closure()}）却仍带 中风险及以上等级",
             sample=unclosed_high, count=len(unclosed_high))
    if det_hits:
        _err(res, "A", "A3", f"{len(det_hits)} 项在关键证据缺失时仍出现定性词", sample=det_hits, count=len(det_hits))
    if closure_bad:
        _err(res, "A", "A2", f"{len(closure_bad)} 项结论等级为 L3 但闭合度低于 {cg.min_closure()}",
             sample=closure_bad, count=len(closure_bad))
    no_grade = [it.get("seq") for it in items if not str(it.get("conclusion_grade") or "").strip()]
    if no_grade:
        _err(res, "A", "A4", f"{len(no_grade)} 项未登记 conclusion_grade", sample=no_grade, count=len(no_grade))
    if no_alt:
        _err(res, "A", "A7", f"{len(no_alt)} 项存在资料缺口但未给出登记表内的具体替代资料名",
             sample=no_alt, count=len(no_alt))

    # ---- A6 证据状态词表（五态）——与 engine/data_source_status.STATUSES_ALL 同源
    legal_status, bad_status, status_total = _evidence_status_audit(items)
    if bad_status:
        _err(res, "A", "A6",
             f"{len(bad_status)} 处证据状态为表外词（合法：{'/'.join(legal_status)}）",
             sample=bad_status, count=len(bad_status))
    elif status_total == 0:
        res.skips.append("A6：报告内无证据状态字段（evidence_chain.elements[].status），状态词表未执行")

    # ---- A8 closure 必须进入会话摘要（跨轮可比）—— §3.1「前后版本对比」
    digest_fields, digest_err = _digest_fields()
    if digest_err:
        res.skips.append(f"A8：{digest_err}")
    elif "closure" not in digest_fields:
        _err(res, "A", "A8",
             "closure 未进入会话摘要字段（DIGEST_FIELDS），闭合度无法跨轮对比",
             sample={"digest_fields": sorted(digest_fields)})

    res.stats = {
        "items": len(items),
        "veto_triggered": len(veto_items),
        "zero_evidence_high": len(zero_evidence_high),
        "unclosed_high": len(unclosed_high),
        "closure_zero": sum(1 for it in items if (it.get("closure") in (0, 0.0))),
        "closure_unregistered": sum(1 for it in items if it.get("closure") is None),
        "max_closure": max((float(it["closure"]) for it in items if it.get("closure") is not None), default=None),
    }
    res.status = "FAIL" if res.errors else "PASS"
    return res


_ALT_CACHE: Optional[Dict[str, Any]] = None


def _evidence_status_audit(items: Sequence[Dict[str, Any]]) -> Tuple[List[str], List[Dict[str, Any]], int]:
    """A6：校验证据状态词是否属于五态词表。

    唯一权威 = `engine/data_source_status.STATUSES_ALL`（已有/缺失/须核对/待企业提交/本业态不适用）。
    找不到 `evidence_chain.elements[].status` 时返回 total=0，由调用方报 SKIP（不静默通过）。
    """
    try:
        from engine import data_source_status as dss
        legal = list(dss.STATUSES_ALL)
    except Exception as exc:  # noqa: BLE001
        load_errors().append(f"读 data_source_status.STATUSES_ALL 失败：{exc}")
        return [], [], 0
    legal_set = set(legal)
    bad: List[Dict[str, Any]] = []
    total = 0
    for it in items:
        ch = it.get("evidence_chain")
        if not isinstance(ch, dict):
            continue
        for e in (ch.get("elements") or []):
            if not isinstance(e, dict):
                continue
            st = e.get("status")
            if st in (None, ""):
                continue
            total += 1
            if str(st) not in legal_set:
                bad.append({"seq": it.get("seq"), "status": st, "name": e.get("name")})
    return legal, bad, total


def _digest_fields() -> Tuple[set, str]:
    """取会话摘要字段集（唯一权威 = engine/snapshot_invariance.DIGEST_FIELDS）。取不到返回原因。"""
    try:
        from engine import snapshot_invariance as si
    except Exception as exc:  # noqa: BLE001
        return set(), f"无法导入 engine/snapshot_invariance.py：{exc}"
    fields = getattr(si, "DIGEST_FIELDS", None)
    if not fields:
        return set(), "snapshot_invariance.DIGEST_FIELDS 为空或不存在"
    return {str(f) for f in fields}, ""


def _load_alt_library() -> Dict[str, Any]:
    global _ALT_CACHE
    if _ALT_CACHE is not None:
        return _ALT_CACHE
    try:
        with open(_ROOT / "config" / "alternative_evidence.json", "r", encoding="utf-8") as fh:
            _ALT_CACHE = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        load_errors().append(f"读 alternative_evidence.json 失败：{exc}")
        _ALT_CACHE = {}
    return _ALT_CACHE


def _as_list(v: Any) -> List[str]:
    if isinstance(v, list):
        return [str(x) for x in v if x]
    return [str(v)] if v else []


def _alts_for(material: str, alt: Dict[str, Any]) -> List[str]:
    cats = alt.get("categories") or {}
    for name, spec in cats.items():
        if name in material:
            return list(spec.get("alternatives") or [])
    return []


# ================================================================ 门禁 B
def gate_logic_consistency(report_data: Any, *, company_code: Any = "", period: Any = "",
                           facts: Optional[FactStore] = None) -> GateResult:
    """逻辑一致性门禁（§3.2）。结构化声明计数 + 编号 + 结论/等级 + 闭合度自洽 + 相反断言。"""
    res = GateResult("B", "logic_consistency", "逻辑一致性门禁")
    if not isinstance(report_data, dict):
        res.status = "SKIP"
        res.skips.append("report_data 不是 dict")
        return res
    items = iter_items(report_data)
    if not items:
        res.status = "SKIP"
        res.skips.append("取不到报告主体条目")
        return res

    # ---- B1 声明计数 vs 实际盘点（零误报：全部可复算）
    declared_vs_actual: List[Dict[str, Any]] = []
    n = len(items)
    _cmp_count(declared_vs_actual, "total_risks", report_data.get("total_risks"), n)
    lvl_counts: Dict[str, int] = {}
    for it in items:
        lv, _ = cg.normalize_level(it.get("risk_level"))
        lvl_counts[lv] = lvl_counts.get(lv, 0) + 1
    for key, lv in (("high_risk", "高风险"), ("mid_risk", "中风险"), ("low_risk", "低风险")):
        _cmp_count(declared_vs_actual, key, report_data.get(key), lvl_counts.get(lv, 0))
    ov = str(report_data.get("overall_level") or "")
    # ★ 2026-10-08（P0-1 判据修正）：`overall_level` 是**结论成熟度摘要**
    #   （「已认定事实X项／待核事项Y项」），判据应为「X = 已给最终答案的条数、Y = n − X」，
    #   **不是**「两个数各自都等于 n」（旧判据把 X、Y 分别与 n 比 ⇒ 必然假红）。
    # ★★ 2026-10-09（P1-4 收尾）：回读**必须与产出同源** `report_metrics.parse_conclusion_counts`
    #   —— 旧实现硬写正则 `(已核定|待核)\s*(\d+)\s*项`，产出侧一改词（本次改为权威术语
    #   「已认定事实/待核事项」）就**静默失配**（既不报错也不校验 = 门禁空转）。
    _ovc: Dict[str, int] = rm.parse_conclusion_counts(ov)
    if _ovc:
        _ver_actual = sum(1 for it in items if rm.is_verified_conclusion(it))
        for _key, _exp in (("verified", _ver_actual), ("pending", n - _ver_actual)):
            if _key in _ovc and _ovc[_key] != _exp:
                declared_vs_actual.append({"field": f"overall_level[{_key}]",
                                           "declared": _ovc[_key], "actual": _exp,
                                           "raw": _clip(ov)})
    elif ov:
        # ★★ 不得静默跳过：取值存在、却读不到计数 ⇒ 如实登记"该条未执行"（既不报绿也不报红）。
        #   触发场景：产物是**旧措辞**（本次改词前的落盘），或该字段被写成风险等级标签
        #   （`pipeline` 引擎阶段确实会写 `overall_level=composite_level`，两种语义挤一个字段）。
        res.skips.append(
            "B9：`overall_level` 取值 %r 不在结论成熟度摘要口径内（权威产出见 "
            "`report_metrics.conclusion_count_phrase`）⇒ 结论计数比对未执行" % _clip(ov, 60))
    # 等级标签类（「高风险X项」等）仍按等级计数比对
    for m in re.finditer(r"(极高风险|高风险|中风险|低风险)\s*(\d+)\s*项", ov):
        label, val = m.group(1), int(m.group(2))
        exp = {"极高风险": sum(1 for it in items if rm.normalize_item_level(it) == "极高风险")}.get(label)
        if exp is None:
            exp = lvl_counts.get(label, 0)
        if val != exp:
            declared_vs_actual.append({"field": f"overall_level[{label}]", "declared": val, "actual": exp,
                                       "raw": _clip(ov)})
    err = report_data.get("enterprise_readable_report") if isinstance(report_data.get("enterprise_readable_report"), dict) else {}
    ledger = err.get("resolution_ledger") if isinstance(err.get("resolution_ledger"), dict) else {}
    # ★ 2026-10-08（P0-1 判据修正）：台账**有自己的覆盖范围**（引擎检出明细），
    #   与报告正文条目集合**本就不是一个集合**。正确判据 = 拿台账声明的 scope
    #   重算一遍再比，而不是一律拿它跟报告正文项数 n 比（旧判据把 6 个正常值判成错）。
    _lscope = str(ledger.get("scope") or "").strip()
    if _lscope:
        _sitems = rm.scope_items(report_data, _lscope)
        _lexp = rm.ledger_counts(_sitems)
        for key in ("ironclad", "self_provable", "pending", "with_resolve", "with_self_proof"):
            if ledger.get(key) is not None:
                _cmp_count(declared_vs_actual, f"resolution_ledger.{key}[scope={_lscope}]",
                           ledger.get(key), _lexp.get(key, 0))
        # 声明了 scope ⇒ 声明的范围本身必须可复算（防止"声明归声明、数是拍脑袋"）
        if ledger.get("scope_total") is not None or ledger.get("scope") is not None:
            _cmp_count(declared_vs_actual, f"resolution_ledger.scope_total[scope={_lscope}]",
                       ledger.get("scope_total"), len(_sitems))
        # `total` 是台账治理**聚合后**的行数：只校验它与 rows 长度一致（口径自洽）
        _tot = ledger.get("total")
        _nrows = len(ledger.get("rows") or [])
        if _tot is not None and isinstance(_tot, int) and _tot != _nrows:
            declared_vs_actual.append({"field": "resolution_ledger.total↔rows",
                                       "declared": _tot, "actual": _nrows})
    else:
        # 未声明覆盖范围 ⇒ 沿用"与报告正文同口径"的严格判据，并提示补声明
        for key in ("total", "ironclad", "self_provable", "pending", "with_resolve", "with_self_proof"):
            if ledger.get(key) is not None:
                _cmp_count(declared_vs_actual, f"resolution_ledger.{key}", ledger.get(key), n)
    if declared_vs_actual:
        _err(res, "B", "B6",
             f"{len(declared_vs_actual)} 处声明计数与实际盘点不一致（同一事实必须单一来源）",
             sample=declared_vs_actual, count=len(declared_vs_actual))

    # ---- B2 编号连续性
    nb_svc = nb.NumberingService(company_code, period)
    seqs = [(it.get("seq") if isinstance(it.get("seq"), int) else None) for it in items]
    order_raw = [it.get("办理顺序") for it in items]
    order_seq = [nb_svc.parse(_cn_to_plain(x)) or nb_svc.seq_of(x) or _cn_num(x) for x in order_raw]
    cont = nb.validate_continuity(order_seq, total=n, label="办理顺序")
    if cont:
        _err(res, "B", "B2", f"编号不连续：{len(cont)} 处问题",
             sample=[c.to_dict() for c in cont], count=len(cont))
    seq_cont = nb.validate_continuity([s for s in seqs if s is not None], total=n, label="seq")
    if seq_cont:
        _err(res, "B", "B2", f"seq 编号不连续：{len(seq_cont)} 处问题",
             sample=[c.to_dict() for c in seq_cont], count=len(seq_cont))
    if any(s is None for s in seqs):
        _err(res, "B", "B2", f"{sum(1 for s in seqs if s is None)} 项未编号", sample=None,
             count=sum(1 for s in seqs if s is None))

    # ---- B3/B5 结论等级 × 风险等级
    #   ★★ 2026-10-09（P0-5 同口径收敛）：**门禁与产出必须同一判据**。
    #   事故：产出侧 `conclusion_grade.cap_level_for_grade` 用 `effective_grade_id`
    #   （把结论用语「待核」映射为 L2 ⇒ 照压）；本门禁却取**原始字段**
    #   `conclusion_grade_declared`（="待核"，非 L 级 ⇒ 视为"未登记" ⇒ 永不报），
    #   且阈值写死「≥高风险」（宽于产出：中风险不查）。两处口径不同源 ⇒
    #   「压制未生效」会被静默放行（判据空转）。现统一读 `effective_grade_id` +
    #   `allowed_levels`：允许集合非空且实际等级不在其中 ⇒ 判冲突（与产出完全同源）。
    conflicts: List[Dict[str, Any]] = []
    for it in items:
        a = cg.analyze_item(it)
        gid, _reg = cg.effective_grade_id(it)
        lv = a.get("risk_level_normalized")
        allow = cg.allowed_levels(gid) if gid else ()
        if allow and lv and lv not in allow:
            conflicts.append({"seq": a["seq"], "grade": gid, "risk_level": it.get("risk_level"),
                              "allowed": list(allow)})
    if conflicts:
        _err(res, "B", "B3",
             f"{len(conflicts)} 项风险等级超出其结论等级允许的档位（同源判据 `allowed_levels`）",
             sample=conflicts, count=len(conflicts))

    # ---- B4 高风险不得与『可能性低』并存（除非声明按潜在影响定级）
    prob_conflict: List[Dict[str, Any]] = []
    for it in items:
        lv, _ = cg.normalize_level(it.get("risk_level"))
        if risk_levels.severity(lv) < risk_levels.severity("高风险"):
            continue
        blob = "\n".join(iter_texts(it))
        if "可能性低" not in blob:
            continue
        if any(k in blob for k in ("按潜在影响定级", "按潜在税额定级", "定级依据")):
            continue          # 已声明定级依据 ⇒ 允许
        prob_conflict.append({"seq": it.get("seq"), "risk_level": it.get("risk_level"),
                              "text": _first_ctx(blob, ["可能性低"])})
    if prob_conflict:
        _err(res, "B", "B4",
             f"{len(prob_conflict)} 项同时出现高风险与『可能性低』且未声明定级依据",
             sample=prob_conflict, count=len(prob_conflict))

    # ---- B5 定性口径冲突：「未认定」与「已查明」同项并存
    mixed: List[Dict[str, Any]] = []
    for it in items:
        blob = "\n".join(iter_texts(it))
        if ("未认定" in blob or "不作认定" in blob or "不作定性" in blob) and ("已查明" in blob or "已认定" in blob):
            mixed.append({"seq": it.get("seq"),
                          "已查明片段": _first_ctx(blob, ["已查明", "已认定"]),
                          "未认定片段": _first_ctx(blob, ["未认定", "不作认定", "不作定性"])})
    if mixed:
        _err(res, "B", "B5", f"{len(mixed)} 项同一事项内并存『未认定』与『已查明』（结论自相矛盾）",
             sample=mixed, count=len(mixed))

    # ---- B6b closure 与 (closure_num/closure_den) 自洽
    # ★★ 2026-10-09（P0-6）：闭合度**只能有一个口径**（`evidence_chain` 的**权数**）。
    #   旧判据拿 `evidence_have/need`（**材料项数**）复算权数闭合度 ⇒ 判据本身口径错
    #   （实测 seq4 closure=0.38（权数 3/8）被算成 1/4=0.25）⇒ 4 项**假红**。
    #   现改为：有 `closure_num/closure_den`（权数）就用它复算；缺失时退回
    #   `evidence_chain.elements` 由唯一权威重算；两者都拿不到才用 have/need（旧口径兜底）。
    closure_bad: List[Dict[str, Any]] = []
    for it in items:
        c = it.get("closure")
        if c is None:
            continue
        num, den, basis_src = it.get("closure_num"), it.get("closure_den"), "closure_num/den"
        if num is None or not den:
            try:
                from engine.evidence_chain import closure_basis as _cb2
                _pk = _cb2(it.get("evidence_chain")) if (it.get("evidence_chain") or {}).get("elements") else None
            except Exception:  # noqa: BLE001
                _pk = None
            if _pk:
                num, den, basis_src = _pk["num"], _pk["den"], "evidence_chain.elements"
        if num is None or not den:
            h, need = it.get("evidence_have"), it.get("evidence_need")
            if h is None or not need:
                continue
            num, den, basis_src = h, need, "evidence_have/need(兜底)"
        calc = round(min(1.0, float(num) / float(den)), 2)
        if abs(calc - float(c)) > 0.02:
            closure_bad.append({"seq": it.get("seq"), "closure": c,
                                "basis": basis_src, "num": num, "den": den, "calc": calc})
    if closure_bad:
        _err(res, "B", "B9", f"{len(closure_bad)} 项 closure 与闭合度分子/分母不自洽（闭合度必须由唯一权威重算）",
             sample=closure_bad, count=len(closure_bad))

    # ---- B7 同一事实多处表述相反（结构化：同对象「已/未 + 取得/验证」）
    contra = _contradiction_pairs(report_data)
    if contra:
        _err(res, "B", "B7", f"{len(contra)} 处同一事实在不同章节表述相反", sample=contra, count=len(contra))

    # ---- B8 事实库冲突（新管线：已登记事实本身冲突）
    store = facts or get_store(report_data) if isinstance(report_data, dict) else facts
    if isinstance(store, FactStore):
        cf = store.conflicts()
        if cf:
            _err(res, "B", "B1", f"事实库存在 {len(cf)} 组同键不同值（未声明口径分组）",
                 sample=[c.to_dict() for c in cf], count=len(cf))
    else:
        res.skips.append("事实库未挂载（B1 事实级冲突未执行；正向登记为必做项，见 §3.2）")

    res.stats = {"items": n, "declared_vs_actual": len(declared_vs_actual),
                 "numbering_issues": len(cont) + len(seq_cont), "level_conflicts": len(conflicts),
                 "closure_self_inconsistent": len(closure_bad), "contradictions": len(contra),
                 "level_counts": lvl_counts}
    res.status = "FAIL" if res.errors else "PASS"
    return res


def _clip(s: Any, n: int = 160) -> str:
    s = str(s or "")
    return s if len(s) <= n else s[:n] + "…"


def _first_ctx(blob: str, words: Sequence[str], span: int = 60) -> str:
    for w in words:
        i = blob.find(w)
        if i >= 0:
            return _clip(blob[max(0, i - span): i + span])
    return ""


def _cmp_count(bucket: List[Dict[str, Any]], field: str, declared: Any, actual: int) -> None:
    if declared is None or declared == "":
        return
    try:
        d = int(declared)
    except Exception:  # noqa: BLE001
        bucket.append({"field": field, "declared": declared, "actual": actual, "why": "非整数，无法比对"})
        return
    if d != actual:
        bucket.append({"field": field, "declared": d, "actual": actual})


_CN_DIGITS = {"〇": 0, "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9}


def _cn_num(s: Any) -> Optional[int]:
    """中文数字 → int（支持 一~二十）。解析不出返回 None（不默认 0）。"""
    t = str(s or "").strip()
    if not t:
        return None
    if t.isdigit():
        return int(t)
    if t == "十":
        return 10
    if t.startswith("十"):
        d = _CN_DIGITS.get(t[1:2])
        return 10 + d if d is not None else None
    if "十" in t:
        a, _, b = t.partition("十")
        da = _CN_DIGITS.get(a)
        db = _CN_DIGITS.get(b) if b else 0
        if da is not None and db is not None:
            return da * 10 + db
        return None
    return _CN_DIGITS.get(t)


def _cn_to_plain(s: Any) -> str:
    n = _cn_num(s)
    return str(n) if n is not None else str(s or "")


#: 需要做「已/未 + 动作」相反断言比对的对象词（可配置化时迁到 config）
_CONTRA_OBJECTS = [
    ("从业人数", ("取得", "验证")),
    ("资产总额", ("取得", "验证")),
    ("应纳税所得额", ("取得", "验证")),
    ("利润总额", ("取得", "验证")),
    ("工资薪金总额", ("取得", "验证")),
]


def _contradiction_pairs(report_data: Any) -> List[Dict[str, Any]]:
    """同一对象在不同章节出现『已X』与『未X』两套断言 ⇒ 记录。

    ★ 2026-10-09（P1-3）：扫描域必须与报告层诸判据**同一权威** ——
      旧实现直扫 `iter_texts(report_data)`，把**上传的原始文件内容**（HTML/JS/CSS）
      也当报告正文 ⇒ 与 `report_surface` 白名单口径不一致（同一份数据两套扫描域，
      闸门之间会互相假红）。现统一走 `report_surface`。
    """
    blob = "\n".join(report_surface(report_data).get("texts") or [])
    out: List[Dict[str, Any]] = []
    for obj, actions in _CONTRA_OBJECTS:
        for act in actions:
            pos = re.search(rf"{re.escape(obj)}[^。；\n]{{0,12}}已{act}", blob)
            neg = re.search(rf"未{act}[^。；\n]{{0,14}}{re.escape(obj)}|{re.escape(obj)}[^。；\n]{{0,12}}未{act}", blob)
            if pos and neg:
                out.append({"object": obj, "action": act,
                            "positive": _clip(pos.group(0)), "negative": _clip(neg.group(0))})
    return out


# ================================================================ 门禁 C
def gate_archive_spec(report_data: Any, *, company_code: Any = "", period: Any = "",
                      render_text: str = "", spec: Optional[Dict[str, Any]] = None) -> GateResult:
    """归档规范性门禁（§3.3）。编号/索引/页眉页脚/签署/审计轨迹/导出包。"""
    res = GateResult("C", "archive_spec", "归档规范性门禁")
    if not isinstance(report_data, dict):
        res.status = "SKIP"
        res.skips.append("report_data 不是 dict")
        return res
    spec = spec if isinstance(spec, dict) else _load_archive_spec()
    items = iter_items(report_data)
    err = report_data.get("enterprise_readable_report") if isinstance(report_data.get("enterprise_readable_report"), dict) else {}

    # C1 总底稿编号
    nb_svc = nb.NumberingService(company_code, period)
    wp = report_data.get("workpaper_no") or err.get("workpaper_no")
    if not wp:
        _err(res, "C", "C1", "缺总底稿编号（WB-TR-<企业代码>-<期间>-<版本>）",
             sample=f"应为：{nb_svc.workpaper_no(1)}")
    elif nb_svc.parse(wp) is None:
        _err(res, "C", "C1", f"总底稿编号格式不合规：{wp!r}")

    # C2/C3/C4 各类编号
    no_risk = [it.get("seq") for it in items if not (it.get("risk_no") or it.get("编号"))]
    if no_risk:
        _err(res, "C", "C2", f"{len(no_risk)} 项风险事项缺风险编号（WB-R-…）", sample=no_risk, count=len(no_risk))
    ev_total = 0
    ev_no = 0
    for it in items:
        for e in (it.get("evidence_chain") or {}).get("elements") or [] if isinstance(it.get("evidence_chain"), dict) else []:
            ev_total += 1
            if e.get("evidence_no"):
                ev_no += 1
    if ev_total and ev_no < ev_total:
        _err(res, "C", "C3", f"证据缺编号：{ev_total - ev_no}/{ev_total} 条无 WB-EV 编号")
    elif ev_total == 0:
        res.skips.append("C3：报告内无 evidence_chain.elements，证据编号未执行")

    # C5 七类索引
    have_idx = set((err.get("indexes") or {}).keys()) if isinstance(err.get("indexes"), dict) else set()
    missing_idx = [i.get("id") for i in (spec.get("indexes") or []) if i.get("required") and i.get("id") not in have_idx]
    if missing_idx:
        _err(res, "C", "C5", f"缺 {len(missing_idx)} 类必需索引：{missing_idx}", sample=missing_idx,
             count=len(missing_idx))

    # C6 页眉页脚（渲染层）
    if not render_text:
        res.skips.append("C6：未提供导出物文本（render_text），页眉页脚/页码未执行")
    else:
        rl = spec.get("render_layer") or {}
        foot = (spec.get("footer") or {}).get("render") or ""
        has_page = bool(re.search(r"第\s*\d+\s*页|page\s*\d+", render_text)) or ("counter(page" in render_text)
        has_total = bool(re.search(r"共\s*\d+\s*页", render_text))
        if (spec.get("footer") or {}).get("required") and not (has_page and has_total):
            _err(res, "C", "C6", "导出物缺页脚（页码/总页数）", sample={"footer_render": _clip(foot)})
        if (spec.get("header") or {}).get("required") and not re.search(r"底稿编号", render_text):
            _err(res, "C", "C6", "导出物缺页眉（未见『底稿编号』字段）")

    # C7 签署栏
    sig = err.get("signature_block") if isinstance(err.get("signature_block"), dict) else {}
    need_roles = [r.get("cn") for r in (spec.get("signature_block") or {}).get("roles") or []]
    blob_sig = json.dumps(sig, ensure_ascii=False)
    miss_roles = [r for r in need_roles if r and r not in blob_sig]
    if miss_roles or not sig:
        _err(res, "C", "C7", f"复核签署栏不完整，缺：{miss_roles or '整个 signature_block'}")

    # C8 审计轨迹
    trail = err.get("audit_trail") or report_data.get("audit_trail")
    if not isinstance(trail, list) or not trail:
        _err(res, "C", "C8", "缺审计轨迹（谁/何时/改了什么/为什么改）")

    # C9 导出包
    pkg = report_data.get("export_package")
    if not isinstance(pkg, dict) or not pkg.get("members"):
        _err(res, "C", "C9", "缺归档导出包声明（PDF/Word/Excel/证据附件包/索引/版本对比）")

    # C10 附件可回查（附件号 + 页码范围 + 来源文件 + 哈希）
    atts = err.get("attachment_index") or err.get("attachments") or []
    if not isinstance(atts, list) or not atts:
        _err(res, "C", "C10", "缺附件索引，附件不可回查（需 附件号/页码范围/来源文件/哈希）")
    else:
        bad_att = [a for a in atts if isinstance(a, dict) and not all(
            a.get(k) for k in ("attachment_no", "pages", "source_file", "sha256"))]
        if bad_att:
            _err(res, "C", "C10", f"{len(bad_att)}/{len(atts)} 个附件缺回查要素",
                 sample=bad_att[:3], count=len(bad_att))

    res.stats = {"items": len(items), "evidence_total": ev_total, "evidence_numbered": ev_no,
                 "indexes_present": sorted(have_idx), "indexes_missing": missing_idx}
    res.status = "FAIL" if res.errors else ("PASS" if not res.skips else "PASS")
    return res


_ARCHIVE_CACHE: Optional[Dict[str, Any]] = None


def _load_archive_spec() -> Dict[str, Any]:
    global _ARCHIVE_CACHE
    if _ARCHIVE_CACHE is not None:
        return _ARCHIVE_CACHE
    try:
        with open(_ROOT / "config" / "archive_spec.json", "r", encoding="utf-8") as fh:
            _ARCHIVE_CACHE = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        load_errors().append(f"读 archive_spec.json 失败：{exc}")
        _ARCHIVE_CACHE = {}
    return _ARCHIVE_CACHE


# ================================================================ 门禁 D
#: ★界面交互残留词 —— **只收"整词短语"**，不收单字词。
#  实测教训：单收「导出/复制/展开」会命中正当业务表述（"社保经办机构导出明细"、
#  "疑似复制粘贴"、"展开分析"）与上传文件里的 HTML（`展开</span>`），造成 800+ 假红。
_UI_RESIDUE = (
    "下载 CSV", "下载CSV", "下载 csv", "点击展开", "展开全部", "收起",
    "复制链接", "导出：", "导出:", "导出CSV", "导出 PDF", "导出PDF",
    "127.0.0.1", "localhost:", "http://127.", "点击查看", "查看更多",
)
#: Markdown 残留 —— 不含 `__`（JS/CSS 变量名与 Dunder 名会误伤）
_MD_RESIDUE = ("**", "##", "|---", "- [ ]", "```")
_VAR_RE = re.compile(r"(?<![{\w])\{[^{}\n]{1,24}\}(?![}\w])|\{\{[^{}\n]{1,40}\}\}|<[A-Za-z_\u4e00-\u9fa5]{2,20}>")
_LEAD_TAILS = ("需要：", "如下：", "包括：", "分别是：", "具体为：", "明细如下：", "如下所示：")


def gate_template_hygiene(report_data: Any, *, render_text: str = "",
                          duplicate_threshold: int = 2) -> GateResult:
    """模板整洁度门禁（§3.4）。UI 残留 / 空模板 / 未替换变量 / Markdown / 重复 / 空表 / 目录。

    ★扫描域 = `report_surface(report_data)` ∪ `render_text`。绝不直接扫整个 `report_data`。
    """
    res = GateResult("D", "template_hygiene", "模板整洁度门禁")
    surface = report_surface(report_data) if report_data is not None else {"texts": [], "sources": [], "truncated": False}
    data_texts: List[str] = list(surface.get("texts") or [])
    # ★渲染物按行拆段：导出物里"段落"以换行分隔，不拆会把整篇当一个段落 ⇒ 重复度判据恒不触发
    render_paras: List[str] = []
    if render_text:
        render_paras = [ln for ln in render_text.split("\n")]
    prose_texts: List[str] = data_texts + render_paras
    all_texts = data_texts + render_paras
    res.stats = {"surface_sources": surface.get("sources"), "data_texts": len(data_texts),
                 "data_chars": sum(len(t) for t in data_texts), "render_supplied": bool(render_text),
                 "excluded_keys": len(surface.get("excluded_keys") or []),
                 "dropped_nonprose": surface.get("dropped_strings", 0)}
    if surface.get("truncated"):
        _err(res, "D", "D0", "扫描域超过 max_chars 上限，词表类判据未覆盖全部正文（禁止静默截断）")
    if not all_texts:
        res.status = "SKIP"
        res.skips.append("报告正文域与 render_text 均为空")
        return res
    blob = "\n".join(all_texts)

    # D1 UI 残留
    ui_hits = {w: blob.count(w) for w in _UI_RESIDUE if blob.count(w)}
    if ui_hits:
        _err(res, "D", "D1", f"残留界面交互词：{ui_hits}", sample=ui_hits, count=len(ui_hits))

    # D2 孤立引导句（唯一判据 `content_placeholder_guard.is_orphan_block`）：
    #   ★★ 2026-10-09 真实假红：原判据只看"文本块末尾是否跟着内容"，而报告里
    #   「五、需企业提供的资料与说明」段的**正文**是引导句「要把这一项查清楚，需要：」，
    #   补件清单在**同段 `bullets` / `detail_table`** 里（前端确实渲染它们）
    #   ⇒ 只看正文必然误判"其后无内容"（实测 13 处全为假红）。
    #   修法：① 结构层逐段判（带**载荷感知**）——有载荷的引导句不算孤立；
    #         ② 平坦文本层（render_text 行 / 顶层条目）**继承**结构层结论，
    #            已在结构层判为"有载荷"的同一文本不再重复判（同一概念只判一次）。
    from engine.content_placeholder_guard import is_orphan_block, is_orphan_lead
    from engine.report_dedup import cmp_key
    orphan: List[str] = []
    paid_keys: set = set()
    try:
        for _it in iter_items(report_data):
            if not isinstance(_it, dict):
                continue
            for _p in (_it.get("narrative_paragraphs") or []):
                if not isinstance(_p, dict):
                    continue
                _t = _p.get("text")
                if not isinstance(_t, str) or not is_orphan_lead(_t):
                    continue
                if is_orphan_block(_t, _p):
                    orphan.append(_clip(_t))
                else:
                    paid_keys.add(cmp_key(_t))
    except Exception as _d2e:     # noqa: BLE001 —— 不得静默：判据未执行必须可见
        _err(res, "D", "D2", "孤立引导句判据未执行（结构层遍历失败）：%s" % str(_d2e)[:120])
    for t in prose_texts:
        for tail in _LEAD_TAILS:
            for m in re.finditer(re.escape(tail), t):
                rest = t[m.end():].strip()
                if not rest:
                    if cmp_key(t) in paid_keys:
                        continue      # 同段载荷已承载内容 ⇒ 非空模板
                    orphan.append(_clip(t[max(0, m.start() - 30): m.end()]))
    if orphan:
        _err(res, "D", "D2", f"{len(orphan)} 处孤立引导句（『…：』位于段末、其后无内容）",
             sample=orphan[:6], count=len(orphan))

    # D3 未替换变量（仅针对"像模板变量"的形态：短、无空格、含中文或小写标识符）
    var_hits: List[str] = []
    for t in all_texts:
        for m in _VAR_RE.finditer(t):
            tok = m.group(0)
            inner = tok.strip("{}<>")
            if len(inner) > 24 or re.search(r"[;:{}()\[\]=/\\]", inner):
                continue          # 代码/样式片段，不是模板变量
            if re.fullmatch(r"[\d\W_]+", inner):
                continue          # 纯数字/符号
            var_hits.append(tok)
    if var_hits:
        _err(res, "D", "D3", f"{len(var_hits)} 处未替换变量", sample=sorted(set(var_hits))[:8], count=len(var_hits))

    # D4 Markdown 残留
    md_hits = {w: blob.count(w) for w in _MD_RESIDUE if blob.count(w)}
    if md_hits:
        _err(res, "D", "D4", f"残留 Markdown 语法：{md_hits}", sample=md_hits, count=len(md_hits))

    # D5 重复段落
    #   ★★ 2026-10-09（P1-3 判据同口径）：**逐项结论/口径字段属"必要重复"**。
    #   铁律「逐项结论字段不可参与去重」（见 `report_pipeline.SKIP_KEYS`）⇒ 判据口径必须与
    #   去重同口径：这些字段的取值即便在多个事项里字面相同，其**归属主体不同**
    #   （R3 的结论 ≠ R2 的结论），不得计为冗余。负责把"一边规定不许去重、一边判它重复"
    #   的自相矛盾判据消灭（实测 D5 长期 FAIL 的真因之一：4 种剩余重复全部来自
    #   `verdict` / `tax_impact.note`）。豁免集由唯一权威
    #   `report_pipeline.non_dedupable_values` 给出（与去重白/黑名单同源）。
    #   ★★ 2026-10-09（P1-3 补齐）：**语料与豁免都须与去重同口径** ——
    #     ① 语料 = `prose_texts`（排除 `<<T>>` 记录行取值；去重侧同规则见 `split_sections`）；
    #     ② 豁免补入去重侧的**必要重复唯一判据** `dedup_pipeline.is_necessary`
    #        （明细表数据行 / 近纯引用块 / 必要模板）。缺 ② 时实测会把
    #        `cost_recon_detail` 的**判定理由列**（逐行相同）当作 92 处段落重复 ⇒ 假红。
    from collections import Counter
    try:
        from engine.report_pipeline import non_dedupable_values as _ndv
        from engine.dupkit import norm as _dnorm
        from engine.dedup_pipeline import is_necessary as _is_nec
        _exempt = _ndv(report_data)
    except Exception as _e5:  # noqa: BLE001 —— 取不到豁免集**不得静默**（会虚报重复）
        _exempt, _dnorm, _is_nec = set(), (lambda _s: _s), (lambda _s: False)
        res.findings.append(GateFinding(
            gate="D", check_id="D5", severity="WARN", layer="data",
            message="D5 必要重复豁免集未取到（判据退化为不去豁免）：%s" % str(_e5)[:120],
            fix="检查 report_pipeline.non_dedupable_values 与 report_metrics.report_surface_items"))
    ne = [t.strip() for t in prose_texts
          if len(t.strip()) > 25 and _dnorm(t.strip()) not in _exempt and not _is_nec(t.strip())]
    dup = [(t, c) for t, c in Counter(ne).items() if c > duplicate_threshold]
    if dup:
        dup_sorted = sorted(dup, key=lambda x: -x[1])
        _err(res, "D", "D5", f"{len(dup)} 种段落重复超过 {duplicate_threshold} 次",
             sample=[{"text": _clip(t, 80), "times": c} for t, c in dup_sorted[:6]], count=len(dup))

    # D6 只有标题无正文（数据层：章节列表 + 空正文）
    empty_sec: List[Any] = []
    if isinstance(report_data, dict):
        for key in ("_report_chapters", "report_chapters"):
            chs = report_data.get(key)
            if isinstance(chs, list):
                for c in chs:
                    if isinstance(c, dict) and not any(
                        str(c.get(k) or "").strip() for k in ("body", "content", "paragraphs", "text")
                    ):
                        empty_sec.append(c.get("id") or c.get("title"))
    if empty_sec:
        _err(res, "D", "D6", f"{len(empty_sec)} 个章节只有标题无正文", sample=empty_sec, count=len(empty_sec))

    # D9 空表 / 空表头（渲染层）
    if render_text:
        tables = _parse_render_tables(render_text)
        bad = [t for t in tables if not any(str(c).strip() for c in t[0]) or all(
            not any(str(c).strip() for c in r) for r in t[1:])]
        if bad:
            _err(res, "D", "D9", f"{len(bad)} 张空表头/全空表格", sample=bad[:3], count=len(bad))
    else:
        res.skips.append("D9：未提供导出物文本，空表检测未执行")

    # D10 目录 vs 正文标题
    if render_text:
        toc, heads = _toc_and_heads(render_text)
        if toc:
            mismatch = [t for t in toc if not any(h.startswith(t[:8]) for h in heads)]
            if mismatch:
                _err(res, "D", "D10", f"目录 {len(mismatch)} 项与正文标题不一致", sample=mismatch[:5],
                     count=len(mismatch))
        else:
            res.skips.append("D10：未识别到目录行，目录一致性未执行")
    else:
        res.skips.append("D10：未提供导出物文本，目录一致性未执行")

    # D7 术语统一（复用既有唯一权威，不自造词表）
    vague_hits = _vague_term_hits(all_texts)
    if vague_hits:
        _err(res, "D", "D7", f"{len(vague_hits)} 处使用被禁用的模糊/不确定措辞",
             sample=vague_hits[:8], count=len(vague_hits))

    # D8 金额/日期格式统一
    fmt = _format_audit(all_texts)
    if fmt["bad_amount"] or fmt["bad_date"]:
        _err(res, "D", "D8",
             f"格式不统一：金额未千分位两位小数 {fmt['bad_amount']} 处；日期格式异常 {fmt['bad_date']} 处",
             sample={"amount_samples": fmt["amount_samples"], "date_samples": fmt["date_samples"]},
             count=fmt["bad_amount"] + fmt["bad_date"])

    # D11 可信度百分比可复算（P1-2）
    #   铁律：正文每处「判断可信度约 X%」必须能由**同源分项明细**复算出来；算不出就不许写
    #   （宁缺勿假，禁静默给数）。三处必须同源：正文百分比 / 条目 `confidence` / `Σ分项贡献`。
    #   同时：出现百分比 ⇒ 可见域必须披露**同源公式**（否则百分数无公式可回指）。
    #   判据全部取自唯一权威 `engine.argumentation`（复算/百分比/公式文本/锚点），
    #   本模块**不自写**任何数值口径。
    _n_pct = 0
    try:
        from engine.argumentation import (
            CONFIDENCE_FORMULA_ANCHOR as _CFA,
            confidence_from_breakdown as _cfb,
            confidence_percent as _cpct,
        )
        _pct_re = re.compile(r"判断可信度约\s*(\d+)\s*%")
        _conf_bad: List[Any] = []
        for _it in iter_items(report_data):
            if not isinstance(_it, dict):
                continue
            _pcts: set = set()
            for _t in iter_texts(_it, limit_depth=6):
                for _m in _pct_re.finditer(_t or ""):
                    _pcts.add(int(_m.group(1)))
            if not _pcts:
                continue
            _n_pct += len(_pcts)
            _ttl = _clip(_it.get("title") or _it.get("type") or "（无标题）", 40)
            _rec = _cfb(_it.get("confidence_breakdown"))
            if _rec is None:
                _conf_bad.append({"title": _ttl, "问题": "有百分比但无分项依据（不可复算，应不写）",
                                  "正文%": sorted(_pcts)})
                continue
            _cv = _it.get("confidence")
            if isinstance(_cv, (int, float)) and round(float(_cv), 2) != _rec:
                _conf_bad.append({"title": _ttl, "问题": "条目 confidence 与分项之和不等",
                                  "confidence": _cv, "Σ贡献": _rec})
            _exp = _cpct(_rec)
            for _x in sorted(_pcts):
                if _exp != _x:
                    _conf_bad.append({"title": _ttl, "问题": "正文百分比不可由分项复算",
                                      "正文%": _x, "复算%": _exp})
        if _conf_bad:
            _err(res, "D", "D11",
                 f"{len(_conf_bad)} 处可信度不可复算（正文百分比/confidence/Σ分项三方不一致或缺失）",
                 sample=_conf_bad[:6], count=len(_conf_bad))
        if _n_pct:
            _vis = blob + "\n"
            if isinstance(report_data, dict):
                _rs = report_data.get("report_statement")
                if isinstance(_rs, list):
                    _vis += "\n".join(str(x) for x in _rs)
                _er = report_data.get("enterprise_readable_report")
                if isinstance(_er, dict) and isinstance(_er.get("report_statement"), list):
                    _vis += "\n" + "\n".join(str(x) for x in _er["report_statement"])
            if not _CFA.search(_vis):
                _err(res, "D", "D11",
                     "报告出现「判断可信度约X%」但可见域未披露同源可信度公式"
                     "（百分数无公式可回指；公式文本应含「可信度 = 基准分」）")
    except Exception as _d11e:      # noqa: BLE001 —— 判据未执行必须可见，不得静默
        _err(res, "D", "D11", "可信度可复算判据未执行：%s" % str(_d11e)[:120])

    res.stats.update({"texts": len(all_texts), "ui": len(ui_hits), "markdown": len(md_hits),
                      "duplicate_kinds": len(dup), "vars": len(var_hits),
                      "orphan_leads": len(orphan), "conf_pct": _n_pct})
    res.status = "FAIL" if res.errors else "PASS"
    return res


def _vague_term_hits(texts: Sequence[str]) -> List[str]:
    """D7：模糊/不确定措辞。词表复用既有唯一权威，本模块不自造。

    权威 = `engine/report_wording.FORBIDDEN_VAGUE_TERMS`（取不到则返回空并由门禁 SKIP 提示）。
    """
    try:
        from engine import report_wording as rw
        _hits_fn = getattr(rw, "vague_hits", None)
        terms = list(getattr(rw, "FORBIDDEN_VAGUE_TERMS", ()) or ())
    except Exception as exc:  # noqa: BLE001
        load_errors().append(f"读 report_wording 模糊词权威失败：{exc}")
        return []
    if not terms:
        return []
    out: List[str] = []
    for t in texts:
        # ★ 2026-10-08（条款 B4）：走 `report_wording.vague_hits` —— 它**豁免结论用语权威术语**
        #   （术语含「待核事项」，裸子串扫描会把它误判为模糊词）。
        _h = _hits_fn(t) if callable(_hits_fn) else [w for w in terms if w and w in t]
        for term in _h:
            out.append(f"{term} :: {_clip(t, 70)}")
    return out


_AMOUNT_LOOSE = re.compile(r"(?<![\d,.])(\d{4,})(\.\d{1,2})?(?![\d,%])")
_DATE_RE = re.compile(r"\d{4}[-/年]\d{1,2}([-/月]\d{1,2}日?)?|\d{6}|\d{8}")


def _format_audit(texts: Sequence[str]) -> Dict[str, Any]:
    """D8：金额须千分位+两位小数；日期须 YYYY-MM-DD / YYYYMM / YYYYMMDD 等既定形态。"""
    bad_amount, bad_date = 0, 0
    a_samples: List[str] = []
    d_samples: List[str] = []
    for t in texts:
        for m in _AMOUNT_LOOSE.finditer(t):
            if "." not in (m.group(2) or ""):
                continue          # 整数（年份/笔数）不参与金额格式判定
            tok = m.group(0)
            if not re.fullmatch(r"\d{1,3}(,\d{3})+\.\d{2}", tok):
                bad_amount += 1
                if len(a_samples) < 5:
                    a_samples.append(tok)
        for m in _DATE_RE.finditer(t):
            tok = m.group(0)
            if re.fullmatch(r"\d{8}", tok) and not re.match(r"^(19|20)\d{2}[01]\d[0-3]\d$", tok):
                bad_date += 1
                if len(d_samples) < 5:
                    d_samples.append(tok)
    return {"bad_amount": bad_amount, "bad_date": bad_date,
            "amount_samples": a_samples, "date_samples": d_samples}


def _parse_render_tables(text: str) -> List[List[List[str]]]:
    """从导出物文本解析表格（本实现约定：表头行 + 以 '|' 分隔的行）。"""
    tables: List[List[List[str]]] = []
    cur: List[List[str]] = []
    for line in text.split("\n"):
        if line.count("|") >= 2:
            cur.append([c.strip() for c in line.split("|")])
        elif cur:
            if len(cur) > 1:
                tables.append(cur)
            cur = []
    if len(cur) > 1:
        tables.append(cur)
    return tables


def _toc_and_heads(text: str) -> Tuple[List[str], List[str]]:
    toc: List[str] = []
    for line in text.split("\n"):
        if len(re.findall(r"[一二三四五六七八九十]、", line)) >= 3:
            toc = [x.strip() for x in re.split(r"(?=[一二三四五六七八九十]、)", line) if x.strip()]
            break
    heads: List[str] = []
    for line in text.split("\n"):
        s = line.strip()
        if re.match(r"^[一二三四五六七八九十]+、", s) and len(s) < 60:
            heads.append(re.sub(r"^[一二三四五六七八九十]+、", "", s))
    return toc, heads


# ================================================================ 总控
def run_all_gates(
    report_data: Any,
    *,
    company_code: Any = "",
    period: Any = "",
    render_text: str = "",
    facts: Optional[FactStore] = None,
    spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """跑四道门禁并汇总。**未全部通过不得生成正式底稿。**"""
    spec = spec if isinstance(spec, dict) else load_spec()
    results = [
        gate_evidence_closure(report_data),
        gate_logic_consistency(report_data, company_code=company_code, period=period, facts=facts),
        gate_archive_spec(report_data, company_code=company_code, period=period, render_text=render_text),
        gate_template_hygiene(report_data, render_text=render_text),
    ]
    policy = spec.get("policy") or {}
    all_pass = all(r.passed for r in results)
    # 引擎自身的契约健康度（配置读不出/词表不一致 ⇒ 门禁本身不可信）
    self_errors: List[str] = []
    self_errors += load_errors()
    self_errors += cg.load_errors()
    self_errors += nb.load_errors()
    self_errors += cg.vocab_consistency()
    self_errors += cg.verdict_vocab_consistency()
    self_errors += [f"veto 触发项未实现：{i}" for i in cg.veto_trigger_coverage()]

    return {
        "schema": "caishuixitong.quality_gates.result/1",
        "engine_version": VERSION,
        "policy": policy,
        "all_passed": all_pass,
        "formal_output_allowed": bool(all_pass and not self_errors),
        "on_fail": policy.get("on_fail", ""),
        "self_check_errors": self_errors,
        "gates": [r.to_dict() for r in results],
        "summary": {
            "total_errors": sum(len(r.errors) for r in results),
            "total_warns": sum(len(r.warns) for r in results),
            "total_skips": sum(len(r.skips) for r in results),
            "failed_gates": [r.gate for r in results if not r.passed],
            "skipped_gates": [r.gate for r in results if r.status == "SKIP"],
        },
    }


_REPORT_FIX_ORDER = ("A", "B", "C", "D")


def attach_to_report(
    report_data: Dict[str, Any],
    *,
    company_code: Any = "",
    period: Any = "",
    render_text: str = "",
    facts: Optional[FactStore] = None,
) -> Dict[str, Any]:
    """把四道门禁挂到 `report_data` 上，并落 `formal_workpaper_allowed` 标志。

    这是「未通过质量门禁的报告不得进入正式归档」（§5.5/§十）的**唯一接线点**。
    只新增字段、不改动既有字段语义（`release_status` 等由既有链路负责）。

    返回门禁结果 dict；调用方可用 `formal_workpaper_allowed` 决定是否允许导出正式版。
    """
    if not isinstance(report_data, dict):
        return {}
    try:
        company_code = company_code or (
            report_data.get("company_code")
            or (report_data.get("anchoring") or {}).get("unified_social_credit_code")
        )
        period = period or (report_data.get("inspection_period") or report_data.get("period"))
        res = run_all_gates(report_data, company_code=company_code, period=period,
                            render_text=render_text, facts=facts)
        report_data["_quality_gates_v2"] = res
        allowed = bool(res.get("formal_output_allowed"))
        # ★ 2026-10-09（P1-5 接线顺序）：`formal_workpaper_allowed` **只降不升**。
        #   本函数被移到报告**最终出口之后**（与产出同口径）执行，而链路上游
        #   （最终去重收敛的 `阻断`、产出链 20 项自检、法规版本阻塞）已可能置 False。
        #   若这里直接赋值 `= allowed`，门禁通过会把上游的 False **翻回 True**
        #   ⇒「未通过不得出正式稿」被架空。故改为**累加约束**：false 一律落 False。
        if not allowed:
            report_data["formal_workpaper_allowed"] = False
        else:
            report_data.setdefault("formal_workpaper_allowed", True)
        report_data["_quality_gates_summary"] = res.get("summary")
        if not allowed:
            report_data["automatic_determination_allowed"] = False
        return res
    except Exception as exc:  # noqa: BLE001 —— 留痕，绝不静默
        report_data["_quality_gates_v2"] = {
            "all_passed": False, "formal_output_allowed": False,
            "error": f"门禁执行异常：{exc!r}",
        }
        report_data["formal_workpaper_allowed"] = False
        return report_data["_quality_gates_v2"]


def render_gate_report(result: Dict[str, Any], *, max_items: int = 5) -> str:
    """把门禁结果渲染为《质量门禁报告》（问题位置/类型/修复建议）。"""
    L: List[str] = []
    L.append("# 质量门禁报告")
    L.append("")
    L.append(f"- 引擎版本：{result.get('engine_version')}")
    L.append(f"- 四道门禁全部通过：{'是' if result.get('all_passed') else '**否**'}")
    L.append(f"- 允许生成正式底稿：{'是' if result.get('formal_output_allowed') else '**否**'}")
    if result.get("on_fail"):
        L.append(f"- 未通过时的处理：{result['on_fail']}")
    sc = result.get("summary") or {}
    L.append(f"- ERROR {sc.get('total_errors', 0)} / WARN {sc.get('total_warns', 0)} / SKIP {sc.get('total_skips', 0)}")
    if result.get("self_check_errors"):
        L.append("")
        L.append("## 引擎自检（未通过则门禁结论本身不可信）")
        for e in result["self_check_errors"]:
            L.append(f"- [ERROR] {e}")
    for g in sorted(result.get("gates") or [], key=lambda x: _REPORT_FIX_ORDER.index(x.get("gate", "D")) if x.get("gate") in _REPORT_FIX_ORDER else 9):
        L.append("")
        L.append(f"## 门禁{g.get('gate')} · {g.get('cn')} —— {g.get('status')}"
                 f"（ERROR {g.get('errors')} / WARN {g.get('warns')}）")
        for f in (g.get("findings") or [])[:max_items * 4]:
            L.append(f"- [{f.get('severity')}] {f.get('check_id')} {f.get('message')}")
            if f.get("fix"):
                L.append(f"    - 修复建议：{f['fix']}")
            if f.get("sample") not in (None, [], {}):
                L.append(f"    - 位置/样例：{_clip(json.dumps(f['sample'], ensure_ascii=False), 320)}")
        for s in g.get("skips") or []:
            L.append(f"- [SKIP] {s}")
    return "\n".join(L)
