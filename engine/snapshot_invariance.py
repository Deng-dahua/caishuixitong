# -*- coding: utf-8 -*-
"""数据快照与**四类不变性指纹**（用户第 4 批 任务1 验收标准的核心）。

## 验收标准原文

> 「同一数据快照，两次分析**可不同**，但**底层事实、计算结果、法律适用、评分规则必须一致**。」

这句话要能被**机器验证**，就必须先回答：什么叫"不同"、什么叫"必须一致"。
本模块把"必须一致"的那部分抽成 **4 类指纹**，把"可以不同"的那部分**显式排除**：

| 指纹 | 含义 | 覆盖字段（归一化后） |
|---|---|---|
| `facts` | 底层**事实** | 每项：标题 / 红线号 / 税种 / 结论档 / 要件证据计数 |
| `calc` | **计算结果** | 每项：锚定金额 / 各税种 (税率, 金额) / 合计 |
| `legal` | **法律适用** | 每项：引用的（法名, 条款号, 版本状态） |
| `level` | **风险等级评分** | 每项：（风险等级, 结论档, 裁决档）+ **评分规则版本** |

**显式排除（允许变化）**：会话 ID / 分析时间 / 措辞与变体 / 章节顺序 / 办理顺序 /
表格呈现 / 自我怀疑与自我反驳文案 / 可信度小数位（保留 2 位后归一）。

## 铁律

- 指纹只由**内容**决定，**不含时间戳、随机数、进程 ID**（否则同一快照也会漂）；
- 归一化必须**排序**（集合语义），否则顺序变化会误报为"事实变了"；
- **取不到就写 `__MISSING__`**，不用空串顶替（否则"字段丢了"和"字段为空"分不开）。
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

#: 四类"必须一致"的指纹名（★ 唯一权威：新增一类只加这里一处 + `_fingerprinters` 一行）
FINGERPRINT_KINDS: Tuple[str, ...] = ("facts", "calc", "legal", "level")

#: 取不到值时的占位（**不得**用空串：空串会与"真的为空"混淆）
MISSING = "__MISSING__"

#: 指纹里**允许变化**的字段名（写出来是为了让"排除了什么"可审计）
VOLATILE_FIELDS: Tuple[str, ...] = (
    "session_id", "analyzed_at", "generated_date", "report_edition", "trace_id",
    "narrative_paragraphs", "final_answer", "self_doubt", "办理顺序", "suggestion",
    "confidence", "confidence_breakdown", "confidence_formula", "report_fingerprint",
    "compilation_badge", "analysis_session",
)

_ART_RE = re.compile(r"《([^》]+)》\s*(第[一二三四五六七八九十百零〇\d]+条)?")
_VERSION_PAREN_RE = re.compile(
    r"[（(][^（）()]{0,20}?(?:修订|修正|年版|第[一二三四五六七八九十\d]+版)[^（）()]{0,20}?[）)]"
)


def _h(obj: Any) -> str:
    """稳定哈希：key 排序 + 紧凑分隔符（**不含时间/随机**）。"""
    s = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                   default=str)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def _n(v: Any) -> Any:
    return MISSING if v is None or v == "" else v


def problem_key(p: Dict[str, Any]) -> str:
    """一项风险事项的**稳定身份键**（跨两次分析保持同名）。

    ⚠ **刻意不用 `trace_id`**：它可能带轮次/时间成分 ⇒ 同快照也会漂，会造成假报"新增+消除"。
    取值优先级：`scene_fact_id` → `fact_id` → (`redline_id`｜`title`) → `title`。
    """
    if not isinstance(p, dict):
        return MISSING
    for k in ("scene_fact_id", "fact_id"):
        v = p.get(k)
        if v not in (None, ""):
            return str(v).strip()
    rid = str(p.get("redline_id") or "").strip()
    ttl = str(p.get("title") or p.get("redline_name") or p.get("finding_type") or "").strip()
    if rid or ttl:
        return (rid + "｜" + ttl) if rid else ttl
    return MISSING


def problems_of(obj: Any) -> List[Dict[str, Any]]:
    """从"报告对象 / report_data / 会话对象 / 会话摘要"里取出风险事项列表。

    ★ **唯一取数入口**（公开）：其余模块一律 `from engine.snapshot_invariance import problems_of`，
      不得再各写一份同名私有实现（那会被闸门判为"跨模块同名真实分歧"）。
    """
    if not isinstance(obj, dict):
        return []
    for path in (("confirmed_problems",), ("report", "confirmed_problems"),
                 ("enterprise_readable_report", "confirmed_problems")):
        cur: Any = obj
        ok = True
        for k in path:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False
                break
        if ok and isinstance(cur, list) and cur:
            return [p for p in cur if isinstance(p, dict)]
    for k in ("all_findings", "findings"):
        v = obj.get(k)
        if isinstance(v, list) and v:
            return [p for p in v if isinstance(p, dict)]
    return []


def _tax_impact(p: Dict[str, Any]) -> Dict[str, Any]:
    ti = p.get("tax_impact")
    if isinstance(ti, dict):
        return ti
    return {}


def _sorted_taxes(p: Dict[str, Any]) -> List[str]:
    t = p.get("taxes") or _tax_impact(p).get("taxes") or []
    if isinstance(t, str):
        t = [t]
    return sorted({str(x).strip() for x in t if str(x).strip()})


def _legal_refs(p: Dict[str, Any]) -> List[str]:
    """取该事项的**法律适用**（结构化字段优先，否则从"法定依据"文本解析）。

    归一化：去法名的**版本括注** + 只保留（法名, 条款号）+ 版本状态码 ⇒
    改一个版本注记的**措辞**不会误报"法律适用变了"，但**换法/换条款/换版本状态**会报。
    """
    from engine.legal_citation import legal_reference_of
    raw: List[str] = []
    ref = legal_reference_of(p)
    if ref:
        raw.append(str(ref))
    if not raw:
        for np in (p.get("narrative_paragraphs") or []):
            if not isinstance(np, dict):
                continue
            tail = str(np.get("tail") or "")
            if "法定依据" in tail:
                raw.append(tail)
                break
    out: List[str] = []
    for chunk in raw:
        text = _VERSION_PAREN_RE.sub("", chunk)
        for m in _ART_RE.finditer(text):
            law = re.sub(r"\s+", "", m.group(1) or "")
            art = re.sub(r"\s+", "", m.group(2) or "")
            out.append(law + ("#" + art if art else ""))
    if not out and raw:
        # 有依据但解析不出条款 ⇒ 如实记录"有依据但不可解析"，不静默当没有
        out.append("__UNPARSED__")
    return sorted(set(out))


def _version_status_codes(p: Dict[str, Any]) -> List[str]:
    """把该事项引用到的法的**版本状态**纳入法律适用指纹（状态变了必须报）。"""
    try:
        from engine.legal_version import status_of
    except Exception:
        return []
    codes = []
    for ref in _legal_refs(p):
        law = ref.split("#", 1)[0]
        if law and not law.startswith("__"):
            codes.append("%s=%s" % (law, status_of(law)))
    return sorted(set(codes))


def _fact_row(p: Dict[str, Any]) -> Dict[str, Any]:
    hits = p.get("constituent_hits") or p.get("indicator_hits") or []
    idxs: List[Any] = []
    if isinstance(hits, list):
        for hit in hits:
            if isinstance(hit, dict):
                idxs.append(_n(hit.get("index")))
            else:
                idxs.append(str(hit))
    return {
        "title": _n(str(p.get("title") or p.get("finding_type") or "").strip()),
        "redline_id": _n(str(p.get("redline_id") or "").strip()),
        "taxes": _sorted_taxes(p),
        "verdict_grade": _n(str(p.get("conclusion_grade") or p.get("verdict_grade") or "").strip()),
        "evidence_have": _n(p.get("evidence_have")),
        "evidence_need": _n(p.get("evidence_need")),
        "constituents": sorted(str(x) for x in idxs),
    }


def _calc_row(p: Dict[str, Any]) -> Dict[str, Any]:
    ti = _tax_impact(p)
    items = []
    for it in (ti.get("items") or []):
        if not isinstance(it, dict):
            continue
        items.append({
            "tax": _n(str(it.get("tax") or "").strip()),
            "rate": _n(it.get("rate")),
            "amount": _n(it.get("amount")),
        })
    items.sort(key=lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True))
    return {
        "basis": _n(ti.get("basis")),
        "total": _n(ti.get("total")),
        "available": bool(ti.get("available")) if ti else False,
        "items": items,
    }


def _level_row(p: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "risk_level": _n(str(p.get("risk_level") or p.get("level") or "").strip()),
        "verdict": _n(str(p.get("verdict") or "").strip()),
        "capped_from": _n(str(p.get("risk_level_capped_from") or "").strip()),
    }


def scoring_rule_version() -> str:
    """**评分规则版本**指纹：由权威模块的公开表算出（不另写一份规则）。

    覆盖 `engine.risk_levels`（等级序/严重度/展示标签/枚举）与
    `engine.argumentation`（裁决档词表）。**规则一改，本串必变** ⇒
    "评分规则没变"这句话就可被机器验证。
    """
    try:
        from engine import risk_levels as RL
        payload: Dict[str, Any] = {
            "LEGAL_LEVELS": list(getattr(RL, "LEGAL_LEVELS", ())),
            "RISK_GRADES": list(getattr(RL, "RISK_GRADES", ())),
            "EVIDENCE_STATES": list(getattr(RL, "EVIDENCE_STATES", ())),
            "SEVERITY": dict(getattr(RL, "SEVERITY", {})),
            "PRESENT_ORDER": dict(getattr(RL, "PRESENT_ORDER", {})),
            "DISPLAY_LABELS": dict(getattr(RL, "DISPLAY_LABELS", {})),
        }
    except Exception:
        payload = {"risk_levels": "unavailable"}
    try:
        from engine import argumentation as AR
        payload["VERDICTS"] = sorted(
            str(getattr(AR, _k)) for _k in dir(AR)
            if _k.startswith("_VERDICT") or _k.startswith("_NEUTRAL_HIT_VERDICT"))
    except Exception:
        payload["argumentation"] = "unavailable"
    return _h(payload)


def _rows(obj: Dict[str, Any], kind: str) -> Dict[str, Any]:
    fn = {"facts": _fact_row, "calc": _calc_row, "level": _level_row}.get(kind)
    out: Dict[str, Any] = {}
    for p in problems_of(obj):
        k = problem_key(p)
        if fn is not None:
            out[k] = fn(p)
        else:  # legal
            out[k] = {"refs": _legal_refs(p), "status": _version_status_codes(p)}
    return out


def fingerprint(obj: Dict[str, Any], kind: str) -> str:
    """取某一类指纹（`kind` ∈ `FINGERPRINT_KINDS`）。未知类别 ⇒ 抛错（**不静默**）。"""
    if kind not in FINGERPRINT_KINDS:
        raise ValueError("未知指纹类别：%s（合法值 %s）"
                         % (kind, list(FINGERPRINT_KINDS)))
    if kind == "level":
        return _h({"rows": _rows(obj, "level"), "rules": scoring_rule_version()})
    return _h(_rows(obj, kind))


def fingerprints(obj: Dict[str, Any]) -> Dict[str, str]:
    return {k: fingerprint(obj, k) for k in FINGERPRINT_KINDS}


def diff_rows(a: Dict[str, Any], b: Dict[str, Any], kind: str) -> List[str]:
    """逐项差异（用于把"不一致"定位到**哪一项、哪个字段**，而不是只报一个哈希不同）。"""
    ra, rb = _rows(a, kind), _rows(b, kind)
    out: List[str] = []
    for k in sorted(set(ra) | set(rb)):
        if k not in ra:
            out.append("＋新增：%s" % k)
        elif k not in rb:
            out.append("－缺失：%s" % k)
        elif ra[k] != rb[k]:
            out.append("≠ %s：%s → %s" % (k, json.dumps(ra[k], ensure_ascii=False)[:200],
                                          json.dumps(rb[k], ensure_ascii=False)[:200]))
    if kind == "level":
        sa, sb = scoring_rule_version(), scoring_rule_version()
        if sa != sb:
            out.append("≠ 评分规则版本变化：%s → %s" % (sa, sb))
    return out


def snapshot_version(files: Optional[Iterable[Any]] = None) -> str:
    """**数据快照版本**：由文件清单（名 + 大小 + 条数）排序后哈希，与时间无关。

    `files` 接受：`[{"name":…, "size":…, "rows":…}, …]` 或 `["文件名", …]`。
    **不含上传时间/路径**（同一份资料重新上传不应算"换了快照"）。
    """
    items: List[Any] = []
    for f in (files or []):
        if isinstance(f, dict):
            items.append([str(f.get("name") or f.get("filename") or ""),
                          f.get("size"), f.get("rows")])
        else:
            items.append([str(f), None, None])
    # 只按"名+大小+条数"去重排序：重名同大小视为同一份
    uniq = sorted({json.dumps(x, ensure_ascii=False) for x in items})
    return "SS-" + _h(uniq)


def verify_invariance(prev: Dict[str, Any], curr: Dict[str, Any],
                      kinds: Iterable[str] = FINGERPRINT_KINDS) -> Dict[str, Any]:
    """校验两次分析的四类指纹是否恒等（**验收标准 1 的唯一判据**）。

    返回 `{"ok": bool, "diffs": {kind: [描述…]}, "hashes": {"prev":…, "curr":…}}`。
    `ok=False` 即「同一快照却出现事实/计算/法律/评分变化」⇒ 必须人工确认是缺陷还是数据真变了。
    """
    kinds = list(kinds)
    for k in kinds:
        if k not in FINGERPRINT_KINDS:
            raise ValueError("未知指纹类别：%s" % k)
    diffs = {k: diff_rows(prev, curr, k) for k in kinds}
    return {
        "ok": all(not v for v in diffs.values()),
        "diffs": diffs,
        "hashes": {"prev": fingerprints(prev), "curr": fingerprints(curr)},
        "rules_version": scoring_rule_version(),
    }


def content_signature(report: Dict[str, Any]) -> str:
    """**报告内容签名**：把"用户能看到的内容"归一后哈希（用于"只换日期、内容不变"检测）。

    ★ 与四类指纹的区别：本签名**包含**叙述文本，
      但**剔除**会话/日期/指纹等易变字段 ⇒ 两次不同日期的分析若签名相同，
      就是"只换了日期"（见 `engine/reanalysis_guard`）。
    """
    return _content_signature(report)


#: 会话摘要保留的字段（★ 唯一权威：新增字段只加这里一处）。
#: 摘要是为了让"下一次分析"能对比上一次 —— 必须**足以复算出四类指纹**，
#: 由 `test_batch4_skills.py::test_digest_reproduces_fingerprints` 锁死。
DIGEST_FIELDS: Tuple[str, ...] = (
    "redline_id", "title", "finding_type", "risk_level", "level",
    "conclusion_grade", "verdict", "risk_level_capped_from", "taxes",
    "tax_impact", "evidence_have", "evidence_need", "constituent_hits",
    "indicator_hits", "missing_materials", "missing_material_names",
    # ★★ 2026-10-09（P0-6）：闭合度必须进摘要，否则"跨轮对比"看不到证据闭合的变化
    #   （门禁 A8 实测报红）。分子/分母同存，便于下游**同口径**复算。
    "closure", "closure_num", "closure_den",
)


def report_digest(report: Dict[str, Any]) -> Dict[str, Any]:
    """生成**会话摘要**（体量小、可落盘、能复算四类指纹 + 内容签名）。

    ★ 只保留 `DIGEST_FIELDS` + 「法定依据」所在的那一句（法律适用指纹需要它）；
      **不保留**整段叙述（体量与隐私）——但 `content_signature` 会一并存下，
      供下次分析做"只换日期"检测（无法从摘要重算，故直接存签名）。
    """
    probs: List[Dict[str, Any]] = []
    for p in problems_of(report):
        d = {k: p.get(k) for k in DIGEST_FIELDS if k in p}
        tails: List[str] = []
        for np in (p.get("narrative_paragraphs") or []):
            if isinstance(np, dict) and "法定依据" in str(np.get("tail") or ""):
                tails.append(str(np.get("tail")))
        d["narrative_paragraphs"] = [{"tail": t} for t in tails] if tails else []
        probs.append(d)
    digest = {
        "confirmed_problems": probs,
        "summary": {"headline": ((report or {}).get("summary") or {}).get("headline", "")},
        "overall_conclusion": str((report or {}).get("overall_conclusion") or "")[:4000],
        "content_signature": _content_signature(report),
        "fingerprints": fingerprints(report),
        "problems_count": len(probs),
        "rules_version": scoring_rule_version(),
    }
    return digest


def _content_signature(report: Dict[str, Any]) -> str:
    probs = problems_of(report)
    payload = []
    for p in probs:
        payload.append({
            "key": problem_key(p),
            "fact": _fact_row(p),
            "calc": _calc_row(p),
            "legal": _legal_refs(p),
            "level": _level_row(p),
            "text": re.sub(r"\s+", "", json.dumps(
                [str((np or {}).get("text") or "") + str((np or {}).get("tail") or "")
                 for np in (p.get("narrative_paragraphs") or []) if isinstance(np, dict)],
                ensure_ascii=False)),
        })
    payload.sort(key=lambda x: json.dumps(x["key"], ensure_ascii=False))
    extra = {
        "problems_n": len(probs),
        "summary": re.sub(r"\s+", "", json.dumps(
            ((report or {}).get("summary") or {}).get("headline", ""), ensure_ascii=False)),
        "overall": re.sub(r"\s+", "", str((report or {}).get("overall_conclusion") or ""))[:4000],
    }
    return "CS-" + _h({"rows": payload, "extra": extra})


__all__ = [
    "FINGERPRINT_KINDS", "VOLATILE_FIELDS", "MISSING", "DIGEST_FIELDS",
    "problem_key", "problems_of", "fingerprint", "fingerprints", "diff_rows",
    "scoring_rule_version", "snapshot_version", "verify_invariance",
    "content_signature", "report_digest",
]
