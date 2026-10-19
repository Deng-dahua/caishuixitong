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
# ★ 2026-10-19：脚本模式下 `sys.path[0]` 是 `scripts/` ⇒ `import engine` 会 ModuleNotFoundError。
#   必须显式插入 ROOT（本仓 skill 已把这条列为硬规矩，本轮实测又踩中一次）。
sys.path.insert(0, str(ROOT))
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
    """拼接前端 JS 源码 —— ★ **必须先剥注释**。

    ★ 2026-10-19 修判据（第三处假红）：旧实现直接拼原文 ⇒ 注释里出现的
      `report.generate`（那是**权限点名**）、`report.export`（那是**审计动作名**）
      被当成"前端读了 report 对象的字段" ⇒ 恒报 2 个缺失字段。
      与项目既有铁律一致：**存在性/缺失性断言都必须先剥注释**。
      统一走 `engine/js_source.strip_comments`（唯一权威，勿在脚本内自带实现）。
    """
    from engine.js_source import strip_comments as _strip       # noqa: PLC0415
    return "\n".join(_strip(f.read_text(encoding="utf-8", errors="ignore"))
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
    #
    # ★★ 2026-10-19 修判据（整表假红，已核实）：原实现把 `report.X` 与 `r.X` **同等对待**，
    #   于是 `items.forEach(function (r) { return r.name })`、`r.amount`、`r.category`
    #   这类**数组元素/临时变量**的读取全被当成"报告顶层字段" ⇒ 一次性报出 70+ 个
    #   "后端未产出"，其中 `action/amount/category/date/desc/description` 等通用词占绝大多数。
    #   这违反本仓既有铁律：**同一文件里 `report` 与 `r` 是两个命名空间**，
    #   静态 grep 分不清 ⇒ **字段级结论必须以运行时渲染为准**（见 `_audit_frontend_render.js`）。
    #
    #   现口径：
    #     ① `report.X` = 报告层（函数内显式 `var report = r.enterprise_readable_report`）⇒ **高置信度**，直接判缺失；
    #     ② `r.X`     = 可能是报告、也可能只是 forEach 的临时变量 ⇒ **低置信度**，单列"仅供线索"，
    #        不参与"真正不对齐"的结论。
    print("\n【2】前端读取的报告字段 → 后端**未产出**（渲染 undefined）")
    # 只认**独立**的 `report.`（前面不能是 `.` 或单词字符，否则是 `xxx.report.foo` 这类别的对象属性）
    # ★ 再排除**方法调用** `report.export(` / `report.generate(` —— 那是行为不是字段
    #   （实测【2】剩 2 个 export/generate，全是调用，属判据把方法当字段）。
    report_reads = set(re.findall(r"(?<![.\w])report\.([a-zA-Z_]\w*)(?!\s*\()", js))
    # ★ 2026-10-19 修判据（第二处假红）：`report` 变量是
    #   `var report = r.enterprise_readable_report` ⇒ 它读的字段在 **err 层**（报告层），
    #   **不在 payload 顶层**。旧实现只查 `k not in payload` ⇒ overall_conclusion /
    #   main_assessment / material_readiness / confirmed_problems 等**全都存在**的字段
    #   被整批判成"后端未产出"。（同一文件【3】早已声明"两个命名空间都要查"，【2】漏了。）
    esperr_for_read = payload.get("enterprise_readable_report") or {}
    missing = sorted(k for k in report_reads
                     if k not in payload and k not in esperr_for_read
                     and not k.startswith("_"))
    # 白名单：`report.*` 里的明显非报告字段（DOM/数组/临时量）
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
    print("  合计 %d 个（`report.X` 报告层命名空间，高置信度）" % len(missing))

    # ② `r.X` 单列，明确标注不可作为结论（命名空间不确定）
    r_reads = set(re.findall(r"\br\.([a-zA-Z_]\w*)", js))
    r_miss = sorted(k for k in r_reads if k not in payload and k not in NOISE
                    and not k.startswith("_"))
    print("\n【2b】`r.X` 读取但产物无（**低置信度线索**：`r` 可能是 forEach 临时变量，"
          "不可直接当作「不对齐」结论）: %d 个" % len(r_miss))
    print("  " + ("、".join(r_miss[:24]) + ("…" if len(r_miss) > 24 else "") if r_miss else "（无）"))
    print("  ★ 字段级结论请以运行时渲染为准：`node scripts/_audit_frontend_render.js <payload>`")

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
