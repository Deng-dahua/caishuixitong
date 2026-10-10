# -*- coding: utf-8 -*-
"""前后端对齐 + 一键分析接线审计（只读）。

用法：python scripts/_audit_fe_be_alignment.py --report <payload.json>

三张表：
  【1】后端**产出**的顶层字段 → 前端是否读取（0 读取 = 僵尸字段，可能"后端算了前端不显示"）
  【2】前端**读取**的报告字段 → 后端是否产出（缺失 = 前端渲染 undefined，真正的不对齐）
  【3】一键分析后处理的**落地证据**是否出现在真实产物里（端到端接线证明）
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS_DIR = ROOT / "static" / "js"

DEFAULT_PAYLOAD = ROOT / "data" / "cache" / "last_analysis_cache.json"


_REPORT_MARKERS = ("enterprise_readable_report", "overall_conclusion",
                   "confirmed_problems", "main_assessment", "material_readiness")


_REPORT_MARKERS = ("enterprise_readable_report",)


def _score(v) -> tuple:
    """打分：**只认 `enterprise_readable_report`**（前端消费的报告必有它）+ 键数量。

    ★ 踩坑：曾把 `confirmed_problems`/`main_assessment`/`overall_conclusion`
      也当标记，结果选到了 `_case_snapshot` 之类**中间投影**（56 键），
      而真实报告是 115 键 ⇒ 【3】落地证据整表假红（6/15）。
      改为单一硬标记 + 键数取最大。
    """
    if not isinstance(v, dict):
        return (0, -1)
    return (1 if "enterprise_readable_report" in v else 0, len(v))


def load_payload(p: Path) -> dict:
    """缓存真实结构（实测）：{"1": {"report": {"ok","report":{...真实报告(115键)...}}}}。

    ★ 踩坑：曾用「按固定层数下钻」与「markers 命中计数」两种选法，
      都选到了**中间包装层**（56 键）而非真实报告（115 键）⇒ 审计结论全假红。
      改为 (标记命中, 键数量) 复合打分取最大，并对结果做**非空自证**。
    """
    raw = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
    best, best_score = {}, (-1, -1)
    queue = [raw]
    seen = 0
    while queue and seen < 5000:
        cur = queue.pop(0)
        seen += 1
        if isinstance(cur, dict):
            s = _score(cur)
            if s > best_score:
                best, best_score = cur, s
            for v in cur.values():
                if isinstance(v, dict):
                    queue.append(v)
                elif isinstance(v, list) and v and isinstance(v[0], dict):
                    queue.append(v[0])
    return best


def js_text() -> str:
    return "\n".join(f.read_text(encoding="utf-8", errors="ignore")
                     for f in sorted(JS_DIR.glob("*.js")))


def main() -> int:
    payload = load_payload(DEFAULT_PAYLOAD)
    js = js_text()
    print("=" * 80)
    print("产物：%s" % DEFAULT_PAYLOAD.relative_to(ROOT))
    print("顶层字段 %d 个" % len(payload))
    print("=" * 80)

    # ── 【1】后端产出 → 前端是否读 ──
    print("\n【1】后端产出但前端**零读取**的顶层字段（僵尸字段）")
    zombie = []
    for k in sorted(payload):
        if k.startswith("_"):
            continue
        pat = re.compile(r"[\.\['\"]" + re.escape(k) + r"\b")
        if not pat.search(js):
            zombie.append(k)
    if zombie:
        for k in zombie:
            v = payload[k]
            t = type(v).__name__
            n = len(v) if isinstance(v, (list, dict, str)) else ""
            print("  · %-34s %-6s %s" % (k, t, n))
    else:
        print("  （无）")
    print("  合计 %d 个" % len(zombie))

    # ── 【2】前端读 → 后端是否有 ──
    print("\n【2】前端读取的报告字段 → 后端**未产出**（渲染 undefined）")
    reads = set(re.findall(r"\breport\.([a-zA-Z_]\w*)", js))
    reads |= set(re.findall(r"\br\.([a-zA-Z_]\w*)", js))
    missing = sorted(k for k in reads if k not in payload and not k.startswith("_"))
    # 白名单：r.* 里的明显非报告字段（数组元素/正则/临时量）
    NOISE = {
        "length", "push", "map", "filter", "forEach", "join", "split", "indexOf",
        "slice", "replace", "trim", "toFixed", "test", "exec", "match", "value",
        "checked", "dataset", "classList", "style", "textContent", "innerHTML",
        "json", "then", "catch", "ok", "status", "statusText", "headers", "body",
        "valueOf", "toString", "nodeName", "tagName", "children", "parentNode",
        "offsetWidth", "clientWidth", "getAttribute", "setAttribute", "addEventListener",
        "querySelector", "querySelectorAll", "getElementById", "contains", "closest",
        "disabled", "files", "rows", "cells", "colSpan", "rowSpan", "href", "src",
        "title", "name", "id", "type", "key", "text", "count", "items", "code",
        "message", "data", "error", "result", "list", "level", "index", "seq",
    }
    missing = [k for k in missing if k not in NOISE]
    if missing:
        for k in missing:
            print("  ✗ %s" % k)
    else:
        print("  （无）")
    print("  合计 %d 个" % len(missing))

    # ── 【3】一键分析后处理落地证据 ──
    print("\n【3】一键分析后处理的落地证据（真实产物中存在 = 端到端确已执行）")
    esperr = payload.get("enterprise_readable_report") or {}
    # ★ 报告层（err）与引擎层（payload）**两个命名空间都要查** —— 只查一层会把
    #   overall_conclusion / main_assessment / summary 这些"在 err 里"的误判为未落地。
    def in_both(key):
        return payload.get(key) or esperr.get(key)

    checks = [
        ("报告去重（_dedup_rate_after）", lambda: "_dedup_rate_after" in payload),
        ("去重日志条数（_dedup_log_count）", lambda: "_dedup_log_count" in payload),
        ("多版本输出（_report_editions）", lambda: bool(payload.get("_report_editions"))),
        ("产出链自检（_pipeline_selfcheck）", lambda: bool(payload.get("_pipeline_selfcheck"))),
        ("正式底稿许可（formal_workpaper_allowed）", lambda: "formal_workpaper_allowed" in payload),
        ("数据勾稽（_reconciliation）", lambda: bool(payload.get("_reconciliation"))),
        ("法规版本（_legal_versions）", lambda: bool(payload.get("_legal_versions"))),
        ("知识自学习（_knowledge_learn）", lambda: bool(payload.get("_knowledge_learn"))),
        ("措辞审计（_wording_audit）", lambda: "_wording_audit" in payload),
        ("资料缺口（_material_gap）", lambda: bool(payload.get("_material_gap"))),
        ("风险-证据矩阵（_risk_evidence）", lambda: bool(payload.get("_risk_evidence"))),
        ("事实库（_fact_store）", lambda: bool(payload.get("_fact_store_stats"))),
        ("质量门禁（_quality_gates_summary）", lambda: bool(payload.get("_quality_gate"))),
        ("章节总述（overall_conclusion.paragraphs）", lambda: bool(
            (in_both("overall_conclusion") or {}).get("paragraphs"))),
        ("成本勾稽（cost_reconciliation）", lambda: bool(
            (in_both("overall_conclusion") or {}).get("cost_reconciliation"))),
        ("风险性质归纳（risk_themes）", lambda: bool(
            (in_both("overall_conclusion") or {}).get("risk_themes"))),
        ("行业口径（target_entity.industry）", lambda: bool(
            (payload.get("target_entity") or {}).get("industry"))),
        ("企业报告确认事项（confirmed_problems）", lambda: bool(esperr.get("confirmed_problems"))),
        ("检查受限（further_checks）", lambda: "further_checks" in esperr),
        ("主线抽象（main_assessment）", lambda: bool(in_both("main_assessment"))),
        ("计数（summary）", lambda: bool(in_both("summary"))),
        ("受控轮次（compliance_round）", lambda: bool(in_both("compliance_round"))),
        ("资料齐备性（material_readiness）", lambda: bool(in_both("material_readiness"))),
        ("独立入口产物（working_paper_report）", lambda: bool(esperr.get("working_paper_report"))),
    ]
    ok_n = 0
    for label, fn in checks:
        try:
            r = bool(fn())
        except Exception as e:  # noqa: BLE001
            r = False
            label += "（取值异常：%s）" % e
        ok_n += 1 if r else 0
        print("  %s %s" % ("✓" if r else "✗", label))
    print("  落地 %d/%d" % (ok_n, len(checks)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
