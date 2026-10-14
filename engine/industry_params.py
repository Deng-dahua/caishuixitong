# -*- coding: utf-8 -*-
"""行业参数库（用户第 5 批 任务1「多行业通用能力配置」的唯一权威）。

## 设计口径（为什么不把行业数值写进来）

系统里已经有两套既有行业数据：
  · `static/industry_data.json` —— 66 个细分行业 + 12 个门类**基准区间**（毛利率/净利率/税负率/
    进销比/人均营收/期间费用率），`engine/industry_benchmark.py` 与 `industry_resolver` 在读；
  · `engine/industry_resolver.py` —— 行业**归一与匹配**的唯一权威。

所以本模块**只做三件既有模块没做的事**：
  ① 登记"某行业适用哪些风险族/风险指标/哪套报告模板/什么重要性水平/补资料优先级"；
  ② 用 `benchmark_ref` **指向**既有基准库的键（**不复制数值**），并把该套基准的
     来源/版本/期间/口径/适用范围登记清楚（这就是"行业基准库管理"）；
  ③ 提供**新增行业的骨架**（`new_industry_template()`）—— **新增行业只加一条数据，不改代码**。

## 铁律

- 行业**归一**只走 `industry_resolver.normalize_industry_name` / `match_benchmark`，本模块不另写一份。
- `validate()` 是**可机检**的：风险族必须已登记、风险指标必须在该行业基准里存在、
  `benchmark_ref` 必须能在基准库里查到、报告模板必须已登记、重要性水平档位必须已登记、
  资料优先级里的每个材料名必须能被 `material_names` 归入 15 类之一（**否则该资料永远无法进入要件核对**）。
- 取不到 ⇒ 返回空/默认并如实标注，**不用别的行业的参数顶替**。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
_PARAMS = _ROOT / "config" / "industry_params.json"
_INDUSTRY_DATA = _ROOT / "static" / "industry_data.json"
_COMPLIANCE = _ROOT / "config" / "report_compliance.json"
_ANALYSIS_CATALOG = _ROOT / "config" / "analysis_catalog.json"

#: 行业参数必备字段（★ 唯一权威：新增字段只加这里一处 + `validate()` 一行）
PARAM_FIELDS: Tuple[str, ...] = (
    "industry_id", "label", "subtypes", "risk_families", "risk_indicators",
    "benchmark_refs", "benchmark_meta", "report_template", "materiality",
    "material_priority", "level_adjustments",
)

#: 可直接引用的基准表名（★ 唯一权威）
BENCHMARK_TABLES: Tuple[str, ...] = ("benchmarks", "benchmarks_coarse")

_CACHE: Optional[Dict[str, Any]] = None


def _read_json(p: Path, default: Any) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_params() -> Dict[str, Any]:
    global _CACHE
    if _CACHE is None:
        d = _read_json(_PARAMS, {})
        _CACHE = d if isinstance(d, dict) else {}
    return _CACHE


def industries() -> List[Dict[str, Any]]:
    return [x for x in (load_params().get("industries") or []) if isinstance(x, dict)]


def industry_ids() -> List[str]:
    return [str(x.get("industry_id")) for x in industries()]


def raw_of(industry_id: str) -> Optional[Dict[str, Any]]:
    for x in industries():
        if x.get("industry_id") == industry_id:
            return x
    return None


# ── 基准库（既有权威：static/industry_data.json）────────────────────────────────

def benchmark_table(name: str = "benchmarks") -> Dict[str, Any]:
    if name not in BENCHMARK_TABLES:
        return {}
    d = _read_json(_INDUSTRY_DATA, {})
    t = (d or {}).get(name) or {}
    return t if isinstance(t, dict) else {}


def benchmark_values(ref: Dict[str, Any]) -> Dict[str, Any]:
    """按**单个** `{table,key}` 取基准数值（唯一来源 = 既有基准库；取不到返回空，不猜）。"""
    if not isinstance(ref, dict):
        return {}
    t = benchmark_table(str(ref.get("table") or ""))
    v = t.get(str(ref.get("key") or ""))
    return v if isinstance(v, dict) else {}


def benchmark_values_of(refs: Any) -> Dict[str, Any]:
    """按**有序多来源**取基准数值：先命中先用，后项**只补缺失指标**。

    ★ 为什么不是单一来源：`benchmarks_coarse` 只有门类指标（毛利率/税负率/进销比/期间费用率），
      像「人均营收(万)」这类指标只存在于细分行业表 ⇒ 允许"门类基准 + 细分补充"，
      才能既保持门类口径、又不丢指标。**合并顺序即优先级**，写在配置里可复核。
    """
    if isinstance(refs, dict):
        refs = [refs]
    out: Dict[str, Any] = {}
    for r in (refs or []):
        for k, v in benchmark_values(r).items():
            out.setdefault(str(k), v)
    return out


def benchmark_meta(industry_id: str) -> Dict[str, Any]:
    """该行业所用基准的**来源/版本/期间/口径/适用范围**（缺项用默认，并列出实际引用的来源）。"""
    base = dict(load_params().get("benchmark_meta_default") or {})
    raw = raw_of(industry_id) or {}
    base.update({k: v for k, v in (raw.get("benchmark_meta") or {}).items() if v})
    refs = raw.get("benchmark_refs") or []
    if isinstance(refs, dict):
        refs = [refs]
    base["refs"] = [{"table": r.get("table"), "key": r.get("key")} for r in refs
                    if isinstance(r, dict)]
    base["registry_version"] = str(load_params().get("version") or "")
    return base


# ── 行业匹配（★ 归一走 industry_resolver，不另写一份）────────────────────────────

def _norm(name: str) -> str:
    try:
        from engine.industry_resolver import normalize_industry_name
        r = normalize_industry_name(str(name or ""))
        if r:
            return str(r)
    except Exception:
        pass
    return str(name or "").strip()


def resolve_industry_id(industry: str) -> str:
    """把行业名/简称解析成 `industry_id`；**匹配不上返回 ""**（不猜、不兜底到别行业）。"""
    key = _norm(industry)
    if not key:
        return ""
    # ① 精确 label / industry_id
    for x in industries():
        if key == str(x.get("industry_id")) or key == str(x.get("label")):
            return str(x.get("industry_id"))
    # ② 子类命中（长匹配优先，避免「广告」抢走「广告传媒」之外的语义）
    best = ""
    best_len = 0
    for x in industries():
        for st in (x.get("subtypes") or []):
            s = str(st)
            if s and s in key and len(s) > best_len:
                best, best_len = str(x.get("industry_id")), len(s)
    return best


def params_of(industry: str) -> Dict[str, Any]:
    """取行业参数；**匹配不上返回 `{"matched": False, ...}`** 并给出说明（不冒用别行业参数）。"""
    iid = resolve_industry_id(industry)
    if not iid:
        return {"matched": False, "industry_input": str(industry or ""),
                "industry_id": "", "label": "",
                "note": ("未匹配到已配置行业（已配置 %s）⇒ 本行业不套用任何行业参数，"
                         "按通用口径处理；如需支持，请在 config/industry_params.json 增加一条数据。"
                         % "、".join(x.get("label") or "" for x in industries()))}
    raw = dict(raw_of(iid) or {})
    raw["matched"] = True
    raw["industry_id"] = iid
    raw["industry_input"] = str(industry or "")
    raw["benchmark_values"] = benchmark_values_of(raw.get("benchmark_refs"))
    raw["benchmark_meta"] = benchmark_meta(iid)
    raw["not_required_materials"] = _not_required(industry)
    return raw


def _not_required(industry: str) -> List[str]:
    """本业态**不适用资料**——薄转发既有唯一权威 `industry_resolver.not_required_materials`。"""
    try:
        from engine.industry_resolver import not_required_materials
        s, _why = not_required_materials(industry)
        return sorted(str(x) for x in (s or []))
    except Exception:
        return []


def material_priority(industry: str) -> List[str]:
    """补资料优先级（行业核心资料在前）；取不到返回空列表（不冒用别行业顺序）。"""
    p = params_of(industry)
    return [str(x) for x in (p.get("material_priority") or [])] if p.get("matched") else []


def priority_rank(industry: str) -> Dict[str, int]:
    """资料名 → 优先级序号（未列出的排最后，保持稳定排序）。"""
    out: Dict[str, int] = {}
    for i, name in enumerate(material_priority(industry)):
        out[str(name)] = i
    return out


def level_adjustments(industry: str) -> List[Dict[str, Any]]:
    """行业级**等级调整档**（数据驱动；空列表 = 本行业不调整等级）。"""
    p = params_of(industry)
    return [a for a in (p.get("level_adjustments") or []) if isinstance(a, dict)] if p.get("matched") else []


def evaluate_triggers(industry: str, metrics: Optional[Dict[str, Any]] = None,
                      flags: Optional[Dict[str, bool]] = None) -> set:
    """评估行业等级调整的**触发条件**，返回**已成立**的 `adjust_id` 集合。

    `trigger` 三种形态（★ 唯一权威：新增一种只加 `_TRIGGER_KINDS` 一行）：
      · `{"kind":"above","bound":"high","metric":"毛利率"}` —— 指标高于行业区间上限；
      · `{"kind":"below","bound":"low","metric":"进销比"}` —— 指标低于行业区间下限；
      · `{"kind":"present"}` —— 由调用方按事实给出的布尔标志（`flags[adjust_id]`）。
    取不到指标值 / 判不出 ⇒ **不触发**（保守：宁可不动等级，也不无据升级）。
    """
    triggered: set = set()
    metrics = metrics or {}
    flags = flags or {}
    for a in level_adjustments(industry):
        aid = str(a.get("adjust_id") or "")
        tg = a.get("trigger") or {}
        kind = str(tg.get("kind") or "")
        if kind == "present":
            if bool(flags.get(aid)):
                triggered.add(aid)
            continue
        if kind not in ("above", "below"):
            continue
        metric = str(tg.get("metric") or (a.get("applies_to") or {}).get("indicator") or "")
        try:
            val = float(metrics.get(metric))
        except Exception:
            continue
        bm = benchmark_values_of((raw_of(resolve_industry_id(industry)) or {}).get("benchmark_refs"))
        rng = bm.get(metric)
        if not isinstance(rng, (list, tuple)) or len(rng) < 2:
            continue
        low, high = float(rng[0]), float(rng[1])
        if kind == "above" and val > high:
            triggered.add(aid)
        if kind == "below" and val < low:
            triggered.add(aid)
    return triggered


def apply_level_adjustments(industry: str, risk_family: str, indicator: str,
                            level: str, triggered: Optional[Iterable[str]] = None
                            ) -> Tuple[str, List[str]]:
    """按行业参数对**等级**做 floor/cap 调整，返回 `(新等级, 命中说明列表)`。

    ★★ `triggered` = 调用方**已评估成立**的 `adjust_id` 集合（见 `evaluate_triggers`）。
      **未提供 ⇒ 一律不调整**（保守口径）："条件成立"必须有可复核的评估过程，
      不得因为"配置里写了这个条件"就无条件升降级 —— 那正是"配置说 A、代码做 B"。
    """
    from engine.risk_levels import cap_level, present_order
    out = level
    hits: List[str] = []
    trig = set(str(x) for x in (triggered or []))
    for a in level_adjustments(industry):
        if str(a.get("adjust_id") or "") not in trig:
            continue
        at = a.get("applies_to") or {}
        if at.get("risk_family") and str(at["risk_family"]) != str(risk_family or ""):
            continue
        if at.get("indicator") and str(at["indicator"]) != str(indicator or ""):
            continue
        target = str(a.get("to_level") or "")
        if not target:
            continue
        act = str(a.get("action") or "")
        if act == "cap":
            new, why = cap_level(out, target)
        elif act == "floor":
            # floor：不得低于 target ⇒ 取"更严重"的那个
            new = target if present_order(target) < present_order(out) else out
            why = "行业下限：%s（%s）" % (target, a.get("reason") or "")
        else:
            continue
        if new != out:
            out = new
            hits.append("[%s] %s → %s；%s" % (a.get("adjust_id"), act, target,
                                              a.get("reason") or ""))
            if why:
                hits.append(why)
    return out, hits


def template_def(template_id: str) -> Dict[str, Any]:
    """模板定义的**唯一读取入口** —— 经 `engine.template_store`（有效模板 = 内置 ⊕ 台账覆盖）。

    ★ 2026-10-14（ODC-01 修复）：本函数此前在 `report_template()` 里**直读**
      `config/report_compliance.json::templates` ⇒ 「报告模板管理」（`engine/template_store`）
      的自定义 / 覆盖 / 停用**对实际报告不生效**（页面改了、报告章节顺序不变）。
      现统一由 `template_store` 收口：内置仍来自 `report_compliance`（本模块不复制），
      覆盖与停用走台账（`data/report_templates.jsonl`）。

    ★ 唯一权威不可用时：**如实回落**直读内置表 **并留痕**（不静默、不伪造模板）。
      取不到该模板 ⇒ 返回空 dict（由调用方按「未匹配」处理，**不冒用别行业模板**）。
    """
    tid = str(template_id or "").strip()
    if not tid:
        return {}
    try:
        from engine.template_store import get_template          # noqa: PLC0415
    except Exception as exc:                                    # noqa: BLE001
        import sys as _sys                                      # noqa: PLC0415
        print("[industry-params] template_store 不可用，回落直读内置模板表：%s" % exc,
              file=_sys.stderr, flush=True)
        t = ((_read_json(_COMPLIANCE, {}) or {}).get("templates") or {}).get(tid) or {}
        return dict(t) if t else {}
    t = get_template(tid)
    if not t:
        return {}
    return {
        "label": str(t.get("label") or tid),
        "sections": [str(x) for x in (t.get("sections") or [])],
        "emphasis": str(t.get("emphasis") or ""),
    }


def report_template(industry: str) -> Dict[str, Any]:
    """该行业匹配的报告模板（取不到返回空 dict，报告按通用结构呈现）。

    ★ 模板定义经 `template_def()`（唯一读取入口）⇒ 模板页的覆盖/停用**对报告生效**。
    """
    p = params_of(industry)
    if not p.get("matched"):
        return {}
    tid = str(p.get("report_template") or "")
    if not tid:
        return {}
    tpl = template_def(tid)
    if not tpl:
        return {}
    out = dict(tpl)
    out["template_id"] = tid
    out["industry_id"] = p.get("industry_id")
    return out


def materiality(industry: str) -> Dict[str, Any]:
    """重要性水平门槛（行业覆盖默认档）。"""
    p = params_of(industry)
    if p.get("matched") and isinstance(p.get("materiality"), dict):
        return dict(p["materiality"])
    return {}


# ── 校验（可机检）────────────────────────────────────────────────────────────

def validate_params() -> List[str]:
    """校验行业参数库；返回问题描述（空 = 合规）。**全部判据可机检**。"""
    probs: List[str] = []
    d = load_params()
    if int(d.get("schema") or 0) < 1:
        probs.append("industry_params.json schema 缺失或版本过低")
    try:
        from engine.risk_families import family_of
        known_fams = set()
        for x in (_read_json(_ROOT / "config" / "risk_families.json", {}) or {}).get("families", []) or []:
            known_fams.add(str(x.get("risk_family_id")))
    except Exception:
        known_fams = set()
    mt_levels = {str(m.get("level_id")) for m in (
        (_read_json(_ANALYSIS_CATALOG, {}) or {}).get("materiality_levels") or [])}
    # ★ 已登记模板 id = **有效模板**（内置 ⊕ 台账覆盖），经唯一权威 `template_store`
    #   —— 否则「模板页新建的自定义模板」会被本校验判成"未登记"（假红）。
    #   唯一权威不可用 ⇒ 回落读内置配置（不静默：与 `template_def` 同一策略）。
    try:
        from engine.template_store import list_templates as _lt   # noqa: PLC0415
        tpl_ids = {str(x.get("template_id")) for x in _lt(include_disabled=True)}
    except Exception:                                            # noqa: BLE001
        tpl_ids = set((( _read_json(_COMPLIANCE, {}) or {}).get("templates") or {}).keys())
    seen: Dict[str, int] = {}
    for i, x in enumerate(industries()):
        tag = "第 %d 条(%s)" % (i + 1, x.get("industry_id") or "无 id")
        for f in PARAM_FIELDS:
            if f not in x:
                probs.append("%s 缺字段 %s" % (tag, f))
        iid = str(x.get("industry_id") or "")
        if iid in seen:
            probs.append("industry_id 重复：%s" % iid)
        seen[iid] = i
        if not (x.get("subtypes") or []):
            probs.append("%s subtypes 为空（行业将无法被匹配到）" % tag)
        for fam in (x.get("risk_families") or []):
            if known_fams and str(fam) not in known_fams:
                probs.append("%s 引用了未登记的风险族 %s" % (tag, fam))
        refs = x.get("benchmark_refs")
        if isinstance(refs, dict):
            refs = [refs]
        if not refs:
            probs.append("%s 未声明 benchmark_refs（行业基准来源必须登记）" % tag)
        for ref in (refs or []):
            if str((ref or {}).get("table") or "") not in BENCHMARK_TABLES:
                probs.append("%s benchmark_refs.table 非法：%s" % (tag, (ref or {}).get("table")))
            elif not benchmark_values(ref):
                probs.append("%s benchmark_refs 在基准库中查不到：%s/%s"
                             % (tag, (ref or {}).get("table"), (ref or {}).get("key")))
        bv = benchmark_values_of(refs)
        if bv:
            for ind in (x.get("risk_indicators") or []):
                if str(ind) not in bv:
                    probs.append("%s 风险指标「%s」在该行业基准中不存在（无法对标）" % (tag, ind))
        tid = str(x.get("report_template") or "")
        if tpl_ids and tid not in tpl_ids:
            probs.append("%s 引用了未登记的报告模板 %s" % (tag, tid))
        ml = x.get("materiality") or {}
        if mt_levels and str(ml.get("level") or "") not in mt_levels:
            probs.append("%s materiality.level 未登记：%s" % (tag, ml.get("level")))
        if not isinstance(ml.get("amount_floor"), (int, float)):
            probs.append("%s materiality.amount_floor 非数值" % tag)
        for name in (x.get("material_priority") or []):
            try:
                # ⚠ 判据必须用 `categories_of`（**资料名 → 类别**的唯一权威）。
                #   初版误用 `category_strict`（它只认"类别名本身"），
                #   ⇒ 把「合同」「序时账（凭证）」这类**合法资料名**全判成"无法归类"（假阳性）。
                from engine.material_names import categories_of
                if not categories_of(str(name)):
                    probs.append("%s 补资料优先级里的「%s」无法归入任何资料类别（该资料进不了要件核对）"
                                 % (tag, name))
            except Exception:
                break
        for a in (x.get("level_adjustments") or []):
            tg = a.get("trigger") or {}
            if str(tg.get("kind") or "") not in ("above", "below", "present"):
                probs.append("%s 等级调整 %s 的 trigger.kind 非法（须 above|below|present）⇒ 条件无法被评估"
                             % (tag, a.get("adjust_id")))
            if str(tg.get("kind") or "") in ("above", "below"):
                metric = str(tg.get("metric") or (a.get("applies_to") or {}).get("indicator") or "")
                if not metric:
                    probs.append("%s 等级调整 %s 未指定用于比较的指标" % (tag, a.get("adjust_id")))
                elif bv and metric not in bv:
                    probs.append("%s 等级调整 %s 的比较指标「%s」不在该行业基准里（条件永不成立）"
                                 % (tag, a.get("adjust_id"), metric))
            if str(a.get("action") or "") not in ("cap", "floor"):
                probs.append("%s 等级调整 %s 的 action 非法（须 cap|floor）" % (tag, a.get("adjust_id")))
            if not str(a.get("to_level") or ""):
                probs.append("%s 等级调整 %s 未给 to_level" % (tag, a.get("adjust_id")))
            if not str(a.get("reason") or ""):
                probs.append("%s 等级调整 %s 未给理由（等级变动必须可解释）" % (tag, a.get("adjust_id")))
    # 基准元数据齐备
    for k in ("source", "period", "scope", "caveat"):
        if not str((d.get("benchmark_meta_default") or {}).get(k) or "").strip():
            probs.append("benchmark_meta_default 缺字段 %s（行业基准库管理要求登记来源/期间/口径/适用范围）" % k)
    return probs


def new_industry_template(industry_id: str = "new_industry",
                          label: str = "新行业") -> Dict[str, Any]:
    """**新增行业的骨架**（复制到 `config/industry_params.json` 的 industries 里填值即可，不改代码）。"""
    return {
        "industry_id": industry_id,
        "label": label,
        "subtypes": ["请填该行业的常见简称/关键词"],
        "risk_families": [],
        "risk_indicators": ["毛利率", "税负率"],
        "benchmark_refs": [{"table": "benchmarks", "key": "请填基准库中已有的行业键"}],
        "benchmark_meta": {"period": "请填", "note": ""},
        "report_template": "service_light",
        "materiality": {"level": "standard", "amount_floor": 100000},
        "material_priority": [],
        "level_adjustments": [],
        "_如何填充": ("① risk_families 填 config/risk_families.json 里的 risk_family_id；"
                    "② risk_indicators 必须在该行业基准里存在；"
                    "③ benchmark_refs[].key 必须能在 static/industry_data.json 里查到"
                    "（查不到就先把基准数据补进基准库，再引用）；"
                    "④ material_priority 里的材料名必须能被 material_names 归入 15 类之一。"
                    "填完跑 `engine.industry_params.validate()` 与闸门即可。"),
    }


def industry_summary_line() -> str:
    return "已配置行业 %d 个：%s（新增行业只需在 config/industry_params.json 增加一条数据）" % (
        len(industries()), "、".join(x.get("label") or "" for x in industries()))


__all__ = ["PARAM_FIELDS", "BENCHMARK_TABLES", "industries", "industry_ids",
           "raw_of", "load_params", "validate_params", "benchmark_table", "benchmark_values", "benchmark_values_of",
           "benchmark_meta", "evaluate_triggers",
           "resolve_industry_id", "params_of", "material_priority", "priority_rank",
           "level_adjustments", "apply_level_adjustments", "report_template",
           "materiality", "validate_params", "new_industry_template", "industry_summary_line"]
