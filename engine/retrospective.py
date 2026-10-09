# -*- coding: utf-8 -*-
"""四步复盘与规则萃取（用户第 3 批 任务7「自我复盘与规则萃取」）。

## 为什么要有这一层

本项目的缺陷有**极强的复发倾向**（用户原话：「同一个错误犯几次！！！」）。当前
`self_learning`（规则沉淀）/`rule_gate`（入库闸门）/`evolution`（演进）各自可用，但
**"个案 → 模式 → 萃取 → 入库"这条链没有产出物**：一次事故修完就结束了，
下次同类事故发生时没人知道"这是第几次"。

本模块补齐这条链，并把**四类可学习内容分级**（`learnable_rules`）接进入库环节。

## 四步（每步一份产出）

| 步 | 名称 | 产出 |
|---|---|---|
| 1 | 个案复盘 | `01_复盘记录.md` |
| 2 | 模式识别 | `02_模式识别报告.md`（同一 `pattern_signature` 复发 ≥ `PATTERN_MIN_COUNT` ⇒ 升级为「模式」） |
| 3 | 规则萃取 | `03_规则萃取建议.md`（每条建议带 `tier`，未知层级默认 `manual`） |
| 4 | 入库 + 回归 | `04_规则入库记录.md`、`05_回归测试报告.md` |

机器可读副本：`retrospective.json`。

## 铁律

- **不臆造**：没有事件就如实写"本轮无新增事件"，**不生成假记录**。
- **留痕**：事件以 append-only JSONL 落 `data/retrospective/events.jsonl`；
  规则入库写 `data/retrospective/learned_rules.jsonl`（含"未入库"的拒绝理由）。
- **入库受 `learnable_rules.guard_rule_write` 约束**：`forbidden`/`manual`/`accumulate`
  一律**不得**由系统自动写入，只能记为"待人工确认"。
- **模式不可跨签名合并**：聚类键就是 `pattern_signature`，字符不同即不同模式
  （避免把两件事归成一件）。
"""
from __future__ import annotations

import json
import os
from datetime import date as _date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
_BASE = _ROOT / "data" / "retrospective"
_EVENTS = _BASE / "events.jsonl"
_RULES = _BASE / "learned_rules.jsonl"

#: 复发多少次算"模式"（≥2 ⇒ 同一错误犯过两次以上）
PATTERN_MIN_COUNT = 2

#: 模式签名登记表（★ 单一权威：新增一类复发根因**只加一行**）。
#:   key   = 签名（写进事件）
#:   value = (中文名, 判据说明, 建议规则层级 tier, 建议验收方式)
PATTERN_SIGNATURES: Dict[str, Tuple[str, str, str, str]] = {
    "unknown_treated_as_pass": (
        "未知即通过（缺数据被当成满足条件）",
        "某个前置条件取不到数据时，实现按 True/通过处理，而不是按『未验证』处理",
        "manual",
        "构造『条件缺一项』的输入，断言按上界/未量化处理，且闸门反向验证可捕获",
    ),
    "single_concept_multi_impl": (
        "同一概念多处实现（多头维护）",
        "同一业务概念在 ≥2 处各写一份判断，口径漂移后必然不一致",
        "manual",
        "grep 全仓消费点，断言『唯一权威 + 薄转发』，并加跨模块一致性测试",
    ),
    "doc_says_a_code_does_b": (
        "注释/文档说 A、代码做 B",
        "函数 docstring 声称的口径与实现逐字不符（含注释里写旧口径）",
        "auto",
        "读 docstring 声称的口径 → 逐字核对实现；对不上的用例必须失败",
    ),
    "count_single_source_missing": (
        "计数/编号/等级没有唯一收口点",
        "同一批事项的数量在 >1 处各自计算，出现分子分母不同源",
        "manual",
        "端到端断言『总数 = 各等级之和 = 分类合计』，且只在定稿点算一次",
    ),
    "report_text_anchor_drift": (
        "报告文案改动导致金额锚定漂移",
        "为改文案而注入的文字含金额锚点词，使税额测算选到别的数",
        "manual",
        "改动前后做 tax_impact 全量 diff，变值项数必须为 0",
    ),
    "silent_swallow": (
        "异常/条件被静默吞掉",
        "except 不留痕、`continue` 静默跳过某一类对象，产出里查不到",
        "auto",
        "断言每个跳过分支都留痕（≥warning）且产出可追溯",
    ),
    "existence_as_violation": (
        "把存在性描述当成违规成立",
        "红线首条要件是『是否存在…』，结果『存在』即被判触碰红线",
        "manual",
        "红线必须声明 `indicator_constituents` / `violation_any_of` 并加行为测试",
    ),
    "gate_ineffective_mutation": (
        "反向验证的变异打在非判定分支上",
        "为验证闸门而注入的变异未改变被断言的量，导致『变红失败』被误读为覆盖不到",
        "auto",
        "变异后先断言被检查量确实改变，再断言闸门变红",
    ),
    "rule_from_point": (
        "从点到面抽象出的规则（首次出现）",
        "一条个案发现满足四条抽象门槛（根因通用/可机检判据/可复发/有可执行验收），"
        "上升为通用规则；本签名用于记录『该规则第几次被提出』",
        "manual",
        "规则必须可配置（params_ref）+ 可测试（acceptance 会失败）+ 可版本化，且经人工确认后入库",
    ),
}


def _today(s: Optional[str] = None) -> str:
    return str(s or _date.today().isoformat())


def _esc(s: Any) -> str:
    return str(s if s is not None else "").replace("\n", " ").strip()


def _ensure_dir() -> None:
    _BASE.mkdir(parents=True, exist_ok=True)


def normalize_signature(sig: Any) -> str:
    """复发签名归一（★ 唯一权威）：**未登记 ⇒ `unclassified`**。

    ★ 为什么归一必须在**聚类处**也做一次（不能只在 `record_event` 做）：
      签名打错一个字（如 `unknown_treated_pass`）会自成一组 ⇒ 该模式**永远达不到
      复发阈值** ⇒ 规则**静默不产出**。这正是本项目最怕的"静默丢"。
    """
    s = str(sig or "").strip()
    return s if s in PATTERN_SIGNATURES else "unclassified"


# ── 事件台账（append-only）──────────────────────────────────────────────────────

def record_event(ev: Dict[str, Any]) -> Dict[str, Any]:
    """登记一条复盘事件（append-only）。返回补齐默认字段后的事件。

    必填：`symptom`（现象）、`pattern_signature`（复发签名，须在 `PATTERN_SIGNATURES` 内）。
    缺/错的 `pattern_signature` ⇒ 归入 `"unclassified"`（**不猜**，报告如实显示未归类）。
    """
    ev = dict(ev or {})
    ev.setdefault("date", _today())
    ev.setdefault("source", "manual")
    ev.setdefault("module", "")
    ev.setdefault("root_cause", "")
    ev.setdefault("fix", "")
    ev.setdefault("severity", "mid")
    ev.setdefault("evidence", [])
    ev["pattern_signature"] = normalize_signature(ev.get("pattern_signature"))
    ev.setdefault("id", "EV-%s-%04d" % (_today(ev.get("date")).replace("-", ""),
                                        len(load_events()) + 1))
    _ensure_dir()
    with open(_EVENTS, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return ev


def load_events() -> List[Dict[str, Any]]:
    if not _EVENTS.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in _EVENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        if isinstance(o, dict):
            out.append(o)
    return out


# ── 第 2 步：模式识别 ──────────────────────────────────────────────────────────

def cluster_patterns(events: Iterable[Dict[str, Any]],
                     min_count: int = PATTERN_MIN_COUNT) -> List[Dict[str, Any]]:
    """按 `pattern_signature` 聚类；复发 ≥ `min_count` ⇒ `promoted=True`（升级为模式）。

    ★ 聚类键就是签名本身：**不做相似度合并**（否则会把两件事归成一件）。
    """
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for e in (events or []):
        if not isinstance(e, dict):
            continue
        buckets.setdefault(normalize_signature(e.get("pattern_signature")), []).append(e)
    out: List[Dict[str, Any]] = []
    for sig, evs in buckets.items():
        meta = PATTERN_SIGNATURES.get(sig)
        out.append({
            "pattern_signature": sig,
            "pattern_name": meta[0] if meta else "未归类事件（须人工补充签名）",
            "judge": meta[1] if meta else "",
            "tier": meta[2] if meta else "manual",
            "acceptance": meta[3] if meta else "",
            "count": len(evs),
            "promoted": (sig != "unclassified" and len(evs) >= min_count),
            "modules": sorted({_esc(e.get("module")) for e in evs if e.get("module")}),
            "events": evs,
        })
    out.sort(key=lambda c: (-c["count"], c["pattern_signature"]))
    return out


# ── 第 3 步：规则萃取 ──────────────────────────────────────────────────────────

def extract_rule_proposals(clusters: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把**升级为模式**的聚类转成规则萃取建议（未升级的只作参考，不产出规则）。"""
    try:
        from engine.learnable_rules import tier_of, may_write_rule
    except Exception:
        tier_of = lambda _c: "manual"          # noqa: E731
        may_write_rule = lambda _c: False      # noqa: E731
    props: List[Dict[str, Any]] = []
    for c in (clusters or []):
        if not c.get("promoted"):
            continue
        decl = str(c.get("tier") or "manual")
        real = tier_of(decl)
        # ★ `may_write_rule` 返回 (可否, 原因) —— 取 [0]，不能直接 bool(元组)
        #   （元组非空 ⇒ bool 恒 True，会把"须人工确认"误判成"可自动写入"）。
        _w = may_write_rule(real)
        props.append({
            "rule_id": "RR-%s" % c["pattern_signature"].upper().replace("_", "-"),
            "from_pattern": c["pattern_signature"],
            "pattern_name": c["pattern_name"],
            "declared_tier": decl,
            "tier": real,
            "writable": bool(_w[0] if isinstance(_w, tuple) else _w),
            "tier_note": (_w[1] if isinstance(_w, tuple) else ""),
            "judge": c.get("judge") or "",
            "acceptance": c.get("acceptance") or "",
            "evidence": sorted({str(x) for e in c["events"]
                                for x in (e.get("evidence") or [])}),
            "occurrences": c["count"],
        })
    return props


# ── 第 4 步：入库（受四档分级守卫约束）──────────────────────────────────────────

def commit_rules(proposals: Iterable[Dict[str, Any]], dry_run: bool = False
                 ) -> Dict[str, List[Dict[str, Any]]]:
    """把建议规则入档：**可自动写入的档位才写**；其余记为待人工确认（含理由）。

    返回 {"committed": [...], "rejected": [...], "pending_manual": [...]}。
    """
    committed: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    pending: List[Dict[str, Any]] = []
    try:
        from engine.learnable_rules import guard_rule_write, TIER_NOTE
    except Exception:
        guard_rule_write = None
        TIER_NOTE = {}
    for p in (proposals or []):
        rec = dict(p)
        if guard_rule_write is None:
            rec["reason"] = "learnable_rules 不可用，拒绝写入"
            rejected.append(rec)
            continue
        try:
            guard_rule_write(rec.get("tier") or "manual")
        except PermissionError as exc:
            rec["reason"] = str(exc)
            if str(rec.get("tier")) == "forbidden":
                rejected.append(rec)
            else:
                rec["reason"] = "%s（%s）" % (
                    rec.get("reason"), TIER_NOTE.get(str(rec.get("tier")), ""))
                pending.append(rec)
            continue
        if dry_run:
            rec["reason"] = "dry-run：未实际写入"
            committed.append(rec)
            continue
        _ensure_dir()
        with open(_RULES, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        rec["reason"] = "已写入 data/retrospective/learned_rules.jsonl"
        committed.append(rec)
    return {"committed": committed, "rejected": rejected, "pending_manual": pending}


# ── 第 5 步：回归测试报告（只记录"已执行过什么"，不在这里跑测试）────────────────

def regression_report(events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """从事件的 `evidence` 汇总回归项；**如实标注是否有可执行证据**。"""
    rows: List[Dict[str, Any]] = []
    for e in (events or []):
        for ev in (e.get("evidence") or []):
            s = str(ev)
            rows.append({
                "event_id": e.get("id"), "case": s,
                "kind": ("test" if "::" in s or s.endswith(".py") else
                         "gate" if "audit" in s or "闸门" in s else "manual"),
                "has_executable": bool("::" in s or s.endswith(".py")),
            })
    return rows


# ── 产出：5 份文档 ────────────────────────────────────────────────────────────

def _md_events(events: List[Dict[str, Any]]) -> str:
    L = ["# 01 复盘记录（第 1 步：个案）", ""]
    if not events:
        L += ["本轮无新增事件（**不生成假记录**）。", ""]
        return "\n".join(L)
    L += ["| 事件号 | 日期 | 来源 | 模块 | 现象 | 根因 | 处置 | 复发签名 | 严重度 |",
          "|---|---|---|---|---|---|---|---|---|"]
    for e in events:
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            _esc(e.get("id")), _esc(e.get("date")), _esc(e.get("source")),
            _esc(e.get("module")), _esc(e.get("symptom")), _esc(e.get("root_cause")),
            _esc(e.get("fix")), _esc(e.get("pattern_signature")), _esc(e.get("severity"))))
    L.append("")
    return "\n".join(L)


def _md_patterns(clusters: List[Dict[str, Any]]) -> str:
    L = ["# 02 模式识别报告（第 2 步：模式）", "",
         "判据：同一 `pattern_signature` 复发 ≥ %d 次 ⇒ 升级为**模式**（可产出规则）。" % PATTERN_MIN_COUNT, ""]
    if not clusters:
        L += ["本轮无事件，无模式。", ""]
        return "\n".join(L)
    L += ["| 签名 | 模式名 | 复发次数 | 是否升级 | 涉及模块 |", "|---|---|---|---|---|"]
    for c in clusters:
        L.append("| %s | %s | %d | %s | %s |" % (
            c["pattern_signature"], c["pattern_name"], c["count"],
            "✅ 已升级" if c["promoted"] else "未达阈值（仅作参考）",
            "、".join(c.get("modules") or []) or "—"))
    L.append("")
    for c in clusters:
        if not c.get("promoted"):
            continue
        L += ["## 模式：%s（%d 次）" % (c["pattern_name"], c["count"]), "",
              "判据：" + (c.get("judge") or "—"), ""]
    return "\n".join(L)


def _md_proposals(props: List[Dict[str, Any]]) -> str:
    L = ["# 03 规则萃取建议（第 3 步：萃取）", "",
         "每条建议带 `tier`（四档可学习内容分级，唯一权威 `engine.learnable_rules`）；"
         "**未知层级默认 `manual`**。", ""]
    if not props:
        L += ["本轮无达阈值模式，无可萃取规则。", ""]
        return "\n".join(L)
    L += ["| 建议规则号 | 来源模式 | 层级 | 可自动写入 | 验收方式 |", "|---|---|---|---|---|"]
    for p in props:
        L.append("| %s | %s | %s | %s | %s |" % (
            p["rule_id"], p["pattern_name"], p["tier"],
            "✅" if p["writable"] else "❌ 须人工确认", _esc(p.get("acceptance"))))
    L.append("")
    return "\n".join(L)


def _md_commit(res: Dict[str, List[Dict[str, Any]]]) -> str:
    L = ["# 04 规则入库记录（第 4 步：入库）", ""]
    for key, title in (("committed", "已入库"), ("pending_manual", "待人工确认"),
                       ("rejected", "拒绝入库")):
        rows = res.get(key) or []
        L += ["## %s（%d 条）" % (title, len(rows)), ""]
        if not rows:
            L += ["无。", ""]
            continue
        for r in rows:
            L.append("- `%s`（%s）：%s" % (r.get("rule_id"), r.get("tier"), r.get("reason")))
        L.append("")
    L += ["台账：`data/retrospective/learned_rules.jsonl`（append-only，含拒绝理由）。", ""]
    return "\n".join(L)


def _md_regression(rows: List[Dict[str, Any]]) -> str:
    L = ["# 05 回归测试报告（第 5 步：回归）", ""]
    if not rows:
        L += ["本轮无可执行回归项。", ""]
        return "\n".join(L)
    L += ["| 事件号 | 回归项 | 类型 | 是否可执行 |", "|---|---|---|---|"]
    for r in rows:
        L.append("| %s | %s | %s | %s |" % (r.get("event_id"), _esc(r.get("case")),
                                            r.get("kind"),
                                            "✅" if r.get("has_executable") else "⚠ 须人工复核"))
    n_noexec = len([r for r in rows if not r.get("has_executable")])
    L += ["", "说明：**仅有可执行回归项才算真回归**；本表 %d 项中 %d 项无可执行用例，"
          "须人工复核（不得默认已覆盖）。" % (len(rows), n_noexec), ""]
    return "\n".join(L)


def run_retrospective(events: Optional[List[Dict[str, Any]]] = None,
                      as_of: Optional[str] = None,
                      out_dir: Optional[Path] = None,
                      dry_run: bool = False) -> Dict[str, Any]:
    """跑完整四步 + 回归，产出 5 份文档与机器可读副本。

    返回 {"dir": str, "files": {名: 路径}, "clusters": [...], "proposals": [...], "commit": {...}}
    """
    evs = [e for e in (events if events is not None else load_events()) if isinstance(e, dict)]
    clusters = cluster_patterns(evs)
    props = extract_rule_proposals(clusters)
    commit = commit_rules(props, dry_run=dry_run)
    reg = regression_report(evs)

    d = Path(out_dir) if out_dir else (_BASE / _today(as_of))
    d.mkdir(parents=True, exist_ok=True)
    files = {
        "01_复盘记录.md": _md_events(evs),
        "02_模式识别报告.md": _md_patterns(clusters),
        "03_规则萃取建议.md": _md_proposals(props),
        "04_规则入库记录.md": _md_commit(commit),
        "05_回归测试报告.md": _md_regression(reg),
    }
    for name, text in files.items():
        (d / name).write_text(text, encoding="utf-8")
    summary = {
        "as_of": _today(as_of), "events": len(evs),
        "clusters": [{k: v for k, v in c.items() if k != "events"} for c in clusters],
        "proposals": props,
        "commit": {k: len(v) for k, v in commit.items()},
        "regression": reg,
    }
    (d / "retrospective.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"dir": str(d), "files": {k: str(d / k) for k in files},
            "clusters": clusters, "proposals": props, "commit": commit}


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="四步复盘与规则萃取（任务7）")
    ap.add_argument("--events", help="事件 JSON 数组文件（默认读 data/retrospective/events.jsonl）")
    ap.add_argument("--out", help="产出目录（默认 data/retrospective/<日期>/）")
    ap.add_argument("--as-of", dest="as_of", help="复盘基准日 YYYY-MM-DD")
    ap.add_argument("--dry-run", action="store_true", help="只算不写规则台账")
    a = ap.parse_args(argv)
    evs = None
    if a.events:
        evs = json.loads(Path(a.events).read_text(encoding="utf-8"))
    r = run_retrospective(events=evs, as_of=a.as_of,
                          out_dir=Path(a.out) if a.out else None, dry_run=a.dry_run)
    print("复盘产出目录：%s" % r["dir"])
    print("模式 %d 个；建议规则 %d 条；入库 %s" % (
        len([c for c in r["clusters"] if c.get("promoted")]),
        len(r["proposals"]), r["commit"] and
        {k: len(v) for k, v in r["commit"].items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
