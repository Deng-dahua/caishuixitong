---
name: caishuixitong-report-render-sync
description: "Use when adding, renaming, moving, or removing any section, chapter, paragraph, or generated field in the caishuixitong tax-risk inspection report (税务稽查专家工作底稿版). Guarantees new report content is wired into all THREE render targets — backend enterprise_report.py, the offline HTML export _render_report_html.py, and the web frontend static/js/tax-doc-analysis.js (both the 工作底稿版 and 金字塔版 templates) — so it never becomes a \"ghost section\" (present in data / offline HTML but missing from the browser UI). Triggers: user asks to \"add a report section / new chapter / 新增报告段\", edits report text that must appear in the browser, or says a generated paragraph \"can't be seen in 一键分析\". Also run this checklist after any report-content change."
agent_created: true
---

# Caishuixitong Report Render Sync

## Overview

The caishuixitong report is rendered in three independent places. A new section that is
produced by the backend but rendered in only one or two of them becomes a **ghost section**:
it exists in the JSON and possibly the offline HTML, but the user cannot see it when they
run 一键分析 in the browser. This skill is the mandatory three-way sync + verification
checklist to prevent that. (Root cause found 2026-09-27: `inspection_overview` / 检查情况总述
was produced by the backend and rendered offline, but NO web template rendered it — invisible
in the browser until fixed.)

## The Three Render Targets

| # | Layer | File | Where / function | Notes |
|---|-------|------|------------------|-------|
| 1 | Backend data | `engine/enterprise_report.py` | `build_enterprise_report()` — add the field to the `out = _zh_normalize_obj({...})` dict (alongside `overall_conclusion`) | This is the single source of truth. All other layers read `r.enterprise_readable_report.(field)`. |
| 2 | Offline HTML export | `scripts/_render_report_html.py` | renders `err.get("(field)")` where `err = enterprise_readable_report` | Used for local/离线 verification. Mirrors the structure the user approved. |
| 3 | Web frontend | `static/js/tax-doc-analysis.js` | **TWO** functions must both render it (see below) | The only layer the user actually sees in 一键分析. |

### Frontend has TWO templates (both must be touched)

- `_buildEnterpriseReadableBody(r, dateStr)` — the default 工作底稿版 (compilation_style
  `涉税风险检查工作报告（风险检查文书式）`). Inside, `report = r.enterprise_readable_report`.
  Read the field as `report.(field)` and render it (e.g. map `paragraphs` to `p.i2` blocks).
- `_buildPyramidBody(r, dateStr)` — the 金字塔原理编辑版, selected when the user toggles the
  edition switch (`window._tdaReportEdition === 'pyramid'`). Also reads
  `report = r.enterprise_readable_report`. Render the same field here too (e.g. after the SCQA block).

Dispatch (in the same file, ~line 5931): `compilation_style` in
`['涉税风险检查工作报告（风险检查文书式）', '税务风险检查文书式报告', '内部税务风险检查员报告', '企业易读检查结果']`
→ `_buildPyramidBody` (if pyramid + `pyramid_edition` present) else `_buildEnterpriseReadableBody`.

## Checklist (run after ANY report-content change)

1. **Backend emits it** — confirm the field is in the `out` dict in `enterprise_report.py`.
2. **Offline renders it** — confirm `_render_report_html.py` reads and prints it.
3. **Frontend renders it (default template)** — add rendering in `_buildEnterpriseReadableBody`;
   update the TOC (`div.toc`) with an anchor if it is a new chapter; update the cover/opening
   box text if it is referenced there.
4. **Frontend renders it (pyramid template)** — add rendering in `_buildPyramidBody` as well.
5. **Server restarted** — uvicorn does NOT hot-reload. After editing `.py`, kill the old PID and
   restart (`APP_COOKIE_SECURE=0 ./.venv/Scripts/python.exe scripts/_start_uvicorn.py`); confirm
   port 8001 LISTENING before telling the user to re-run 一键分析.
6. **Browser cache** — tell the user to hard-refresh (Ctrl/Cmd+Shift+R) so the new `tax-doc-analysis.js` loads.

## Gotchas

- **Do NOT renumber chapters to insert a section.** Capability sub-sections are labeled with
  HARDCODED strings (`四之一…四之十一` in `_capOrder`), and their numbers already disagree with the
  inline comment ("置于第五章之内"). Renumbering the main chapters cascades into these broken labels.
  Instead, insert the new overview as a lead/引子 section BEFORE the first numbered chapter (e.g.
  `检查情况总述` before `一、本轮检查总体结论`), give it an `h2#...` and a TOC entry, and leave
  all existing `一…六` numbers untouched.
- **当前结构（2026-09-27 二次合并＝真正重写为单章）：** 工作底稿版(默认)的
  「检查情况总述与总体结论」是**单章**，由后端 `overall_conclusion` **统一生成**——它已吸收原
  `inspection_overview` 里独有的三块（企业整体风险综合评价定调句 / 对企业纳税遵从看法 / 监管态度与边界声明），
  每件事只说一遍，前端 `_buildEnterpriseReadableBody` 与离线 `_render_report_html.py` 都**只渲染
  `overall_conclusion` 这一段**，不再把两段并排贴。锚点 `h2#company-conclusion`，TOC 仅一条。
  `inspection_overview` 现在**仅用于金字塔版**的 `检查情况总述（总览）` 引子段（用户决策：金字塔版不合并）。
  验证要点：工作底稿版断言「一、检查情况总述与总体结论」「企业整体风险综合评价」「监管态度与后续处理建议」
  均来自 `overall_conclusion`；金字塔版断言「检查情况总述（总览）」来自 `inspection_overview`。
- **Read path**: inside both frontend functions `report = r.enterprise_readable_report`, so use
  `report.(field)`, NOT `r.(field)`. (When calling from a test harness, pass the TOP-LEVEL result
  that contains `enterprise_readable_report`.)
- **Stale data**: a previously dumped `_fresh_result.json` may predate the new field — regenerate it
  by running `scripts/_dump_fresh_result.py` (full analysis on a scratch account set) before checking.
- **Verify with real data, not assumptions**: a field "should be there" is not proof. Dump the real
  output and assert the key exists (see Verification).

## Verification (no browser needed)

### Step A — Backend actually emits the field
```bash
./.venv/Scripts/python.exe -c "import json; er=json.load(open('scripts/four_reports/_fresh_result.json',encoding='utf-8')).get('report',{}).get('enterprise_readable_report',{}); print('has inspection_overview?', 'inspection_overview' in er)"
```
If missing, regenerate with `scripts/_dump_fresh_result.py`, then re-check.

### Step B — Frontend actually renders it (bundled harness)
```bash
node .workbuddy/skills/caishuixitong-report-render-sync/scripts/verify_frontend_render.js \
  scripts/four_reports/_fresh_result.json "检查情况总述" "企业整体风险综合评价"
```
The harness loads `static/js/tax-doc-analysis.js` in a stubbed `vm` context (no browser),
feeds the real report JSON into `_buildEnterpriseReadableBody`, and asserts every supplied
substring appears in the produced HTML. Use `--pyramid` to also check `_buildPyramidBody`.
Exit code 0 + `ALL_FRONTEND_CHECKS_PASS` = safe to ship.

### Step C — Restart server + syntax
```bash
node --check static/js/tax-doc-analysis.js   # confirm no syntax break
# then restart uvicorn and:  curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001/
```

### Step D — 章节完整性闸门（改第一章后必跑）
```bash
./.venv/Scripts/python.exe -m tools.audit_consistency          # 须 ERROR 0
./.venv/Scripts/python.exe -m pytest tests/test_overall_conclusion.py -q
```
- `tools/audit_consistency.py::check_report_chapter_integrity()`（静态）：① 生产源码不得出现
  「稽查必查资料共」（应为「本轮检查必查资料共」）；② 工作底稿版 `_buildEnterpriseReadableBody`
  **不得再渲染 `inspection_overview`**（单章只由 `overall_conclusion` 构成，防止"摘要+详情"并排贴回）；
  ③ 离线导出不得渲染 `inspection_overview`。
- `tests/test_overall_conclusion.py::TestChapterNoDuplication`（运行时）：断言章内**同一事实只说一遍**
  （「识别并列示」出现 1 次；各等级清单标题 1 次；无裸「待核实事项」；含新段标记）。
- 两道闸门均已做**反向验证**（注入反模式→确认报错→复原）：注入 `稽查必查资料共`→audit ERROR；
  注入 `report.inspection_overview` 进工作底稿版→audit ERROR；注入重复的「本轮识别并列示」段→测试红。**改这一章后别忘跑这两条。**

**发布校验（--strict）**：`tools/verify_release.py` 直接调用 `audit_consistency.run_checks()`，
故凡接进 `run_checks` 的检查都会被发布校验覆盖。上面两道 + 下面这道 cost_recon 闸门都已在 `run_checks` 内。
**新增闸门务必接 `run_checks`**（只定义不接线 = 闸门从未运行）。

**单章相关闸门清单（都在 run_checks）**：
- `check_report_chapter_integrity()`：命名口径（禁「稽查必查资料共」）+ 工作底稿版/离线不得回贴 `inspection_overview`。
- `check_overall_conclusion_no_dup()`：运行时去重不变式（真调 `build_overall_conclusion` 断言不重复）。
- `check_cost_recon_render()`：主营成本「两口径勾稽明细」三处齐备 + 发票构成必须取自 `core_goods_breakdown`（不得重跑 classify）
  + **逐张/逐笔清单字段 `invoice_rows`/`book_rows` 必须在 Web 与离线都渲染**（导出附件，缺一即 ERROR）。
  该明细的导出附件（发票逐张 / 凭证逐笔）走**浏览器端 CSV**（`_crdDownloadCsv` + Blob，无需后端接口），
  数据来自 `pipeline.biz_cost_summary.core_cost_invoices` 与序时账 6401 逐笔。

## Resources

- `scripts/verify_frontend_render.js` — parameterized Node harness that proves a section is
  rendered in the web UI without launching a browser. Pass the report JSON path and one or more
  required substrings; add `--pyramid` to also verify the pyramid edition.
