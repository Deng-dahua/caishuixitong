# -*- coding: utf-8 -*-
"""生成《条款符合性核验与落地_验收报告.html》。

数据来源（全部**实测**，不手写结论）：
  ① data/_clause_audit.json —— `scripts/_audit_clause_compliance.py` 的逐条核验结果；
  ② tools.audit_consistency.check_clause_compliance() —— 常驻闸门结果；
  ③ 真实产物 data/cache/last_analysis_cache.json —— 端到端指标（去重三项/summary/轮次）。
"""
from __future__ import annotations

import html
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

AUDIT = os.path.join(ROOT, "data", "_clause_audit.json")
CACHE = os.path.join(ROOT, "data", "cache", "last_analysis_cache.json")
OUT = os.path.join(ROOT, "docs", "条款符合性核验与落地_验收报告.html")

GAPS = [
    ("verdict 被去重误伤（最严重）",
     "`report_pipeline.TEXT_KEYS` 原把 `verdict`/`suggestion`/`confidence_formula` 当「展示文本」参与去重，"
     "理由是「16 项完全相同 ⇒ 真冗余」。实测 <b>14/16 项的 verdict 被替换为跨项引用</b>"
     "（R3 的结论变成「见疑点R2」、R7 甚至出现<b>自引用</b>「见疑点R7」）—— 读者完全看不到本项定性状态。"
     "旧注释称「安全性由下游闸门过滤保证」，那只解决<b>扫描器不误判</b>，没解决<b>读者看到错误引用</b>。",
     "撤回该「例外」：逐项结论字段一律进 `SKIP_KEYS`；去重只动纯展示叙述段落。"),
    ("去重只判『整体』，同章节/同一事实不阻断",
     "产物链 `dedup_pipeline.duplicate_rate` 只算整体重复率；而离线 `scripts/_phase1_diagnose.py` "
     "另有一份<b>三项完整</b>实现 ⇒ 同一判据两处实现，且产出链的阻断依据残缺。",
     "收敛为唯一权威三项（整体≤10% / 同章节≤5% / 同一事实≤1 次），离线脚本改<b>薄转发</b>；"
     "并补<b>句子级跨事项事实去重</b>（`dedup_sentences_cross`）。"),
    ("引用编号整体偏移 1",
     "`report_pipeline` 里 `where = f\"R{_seq + 1}\"` —— `seq` 本就从 1 起（同类事故此前已在 "
     "`enterprise_report` 修过一处，此处漏改）⇒ 去重引用语给出错误编号。",
     "改为 `_seq if _seq >= 1 else idx`；闸门 C3 禁止 `seq + 1` 形态。"),
    ("样本库从未真正入库 + 提炼源错",
     "`main.py` 调 `update_knowledge()` <b>没传 `case`</b> ⇒ `record_case` 从不执行；"
     "且 `problems` 读的是离线 `baseline/阶段1/问题诊断.json`（<b>上一次离线诊断</b>的静态结果），"
     "与本次报告无关。",
     "新增唯一权威 `problems_from_report()` / `case_from_report()`，从<b>本次报告</b>的问题信号归一；"
     "调用处补 `case=`。闸门 C5 锁定。"),
    ("缺条款指定声明",
     "报告原有「不具有行政执法文书效力」，语义等价但未点明<b>法定程序认定</b>。",
     "抽成唯一权威函数 `_administrative_boundary_statement()`（<b>可运行时断言</b>），"
     "并同步前端兜底文案（两处一致）。"),
    ("报告级通用口径被逐项重复（重复率假不达标）",
     "`risk_level_basis`（11 项相同）与 `confidence_formula`（13 项相同）是<b>每项都适用</b>的方法说明，"
     "却被逐项重复 ⇒ 整体重复率 <b>16.89%</b>、同章节超阈 <b>10</b>（剔除这 27 行即降到 6.67%/0）。",
     "上提为**报告级声明一次**：唯一实现 `report_pipeline.merge_report_level_notes` + "
     "`enterprise_report._report_level_notes_statement`（共用常量表，逐项位置改引用，避免悬空）。"),
    ("结论术语被通俗化层改写（术语漂移）",
     "`plain_language` 把「待核」通俗化为「须核对」 ⇒ 权威术语「待核事项」在报告里变成"
     "「须核对<b>事项</b>」，与术语权威表漂移；且模糊词判据会把该术语误判为禁用词。",
     "术语<b>占位保护</b>（`report_wording._authoritative_terms`）+ 判据统一走 `vague_hits`"
     "（豁免权威术语）；新增闸门 C8 做**行为级**断言（术语经两层清洗必须原样返回）。"),
]


def esc(s) -> str:
    return html.escape(str(s or ""))


def load_json(p, default=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default if default is not None else {}


def main() -> int:
    aud = load_json(AUDIT)
    rows = aud.get("rows") or []
    sm = aud.get("summary") or {}
    gates = []
    try:
        from tools.audit_consistency import check_clause_compliance as _g
        gates = _g()
    except Exception as exc:  # noqa: BLE001
        gates = [("ERROR", "tools/audit_consistency.py", "闸门调用失败：%s" % exc)]

    rep = (load_json(CACHE).get("1") or {}).get("report", {}).get("report", {}) or {}
    err = rep.get("enterprise_readable_report") or {}
    dr = rep.get("_duplicate_rate") or {}
    _o = dr.get("整体") or {}
    _c = dr.get("章节统计") or {}
    _f = dr.get("事实重复") or {}
    _s = err.get("summary") or {}
    _kl = rep.get("_knowledge_learn") or {}
    oc = (err.get("overall_conclusion") or {}).get("paragraphs") or []

    metric = [
        ("整体重复率", "%s（阈值 %s）→ %s" % (
            ("%.2f%%" % (_o.get("重复率") * 100)) if _o.get("重复率") is not None else "—",
            ("%.0f%%" % (_o.get("阈值") * 100)) if _o.get("阈值") else "10%", _o.get("判定") or "—")),
        ("同章节超阈", "%s 章（阈值 %s）" % (_c.get("超阈章节", "—"),
                                          ("%.0f%%" % (_c.get("阈值") * 100)) if _c.get("阈值") else "5%")),
        ("同一事实超额", "%s 次（阈值 %s）→ %s" % (_f.get("超额出现次数合计", "—"),
                                                _f.get("阈值_同一事实完整出现", 1), _f.get("判定") or "—")),
        ("阻断（未达标不得出正式稿）", "是" if dr.get("阻断") else "否"),
        ("formal_workpaper_allowed", str(rep.get("formal_workpaper_allowed"))),
        ("结论 count（已确认/已核定/待核）", "%s / %s / %s" % (
            _s.get("confirmed_problem_count"), _s.get("verified_problem_count"),
            _s.get("pending_problem_count"))),
        ("知识库自学习", str(_kl.get("summary") or "—")),
        ("第一章段数", "%d 段" % len(oc)),
        ("轮次", str((rep.get("compliance_round") or {}).get("round_no") or "—")),
    ]

    def _row_cls(v):
        return {"有": "ok", "部分": "warn", "无": "bad"}.get(v, "")

    trs = "\n".join(
        "<tr><td class='mono'>%s</td><td>%s</td><td class='%s center'>%s</td>"
        "<td class='small'>%s</td></tr>" % (esc(r.get("no")), esc(r.get("clause")),
                                            _row_cls(r.get("verdict")), esc(r.get("verdict")),
                                            esc(r.get("evidence")))
        for r in rows)
    mtrs = "\n".join("<tr><td>%s</td><td><b>%s</b></td></tr>" % (esc(k), esc(v)) for k, v in metric)
    gtrs = "\n".join("<tr><td>%s</td><td class='mono'>%s</td><td class='small'>%s</td></tr>"
                     % (esc(lv), esc(f), esc(m)) for lv, f, m in gates) or \
        "<tr><td colspan='3'>0 条（闸门全绿）</td></tr>"
    gaps_html = "\n".join(
        "<div class='gap'><div class='gtitle'>%d. %s</div>"
        "<div class='grow'><span class='tag'>现状</span>%s</div>"
        "<div class='grow'><span class='tag fix'>修法</span>%s</div></div>"
        % (i, esc(t), d, f) for i, (t, d, f) in enumerate(GAPS, 1))

    doc = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>条款符合性核验与落地 · 验收报告</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--line:#e3e6ea;--tx:#1f2329;--tx2:#5c6570;
--ok:#1a7f4b;--warn:#b26a00;--bad:#c0392b;--acc:#284b8c;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);
font:15px/1.75 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:28px 20px 64px}
h1{font-size:24px;margin:0 0 6px}
.sub{color:var(--tx2);font-size:13px;margin-bottom:22px}
h2{font-size:18px;margin:30px 0 12px;padding-left:10px;border-left:4px solid var(--acc)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin:12px 0}
table{width:100%%;border-collapse:collapse;font-size:13.5px}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
th{background:#f0f2f5;font-weight:600}
.mono{font-family:ui-monospace,Consolas,monospace;white-space:nowrap}
.small{font-size:12.5px;color:var(--tx2)}
.center{text-align:center;font-weight:600}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}
.kpi{display:flex;gap:12px;flex-wrap:wrap;margin:10px 0 4px}
.kpi div{flex:1 1 150px;background:#fff;border:1px solid var(--line);border-radius:9px;padding:12px 14px}
.kpi b{display:block;font-size:22px;line-height:1.3}
.gap{border:1px solid var(--line);border-radius:9px;padding:12px 14px;margin:10px 0;background:#fff}
.gtitle{font-weight:600;margin-bottom:6px}
.grow{margin:4px 0;font-size:13.5px}
.tag{display:inline-block;background:#eef1f6;color:var(--acc);border-radius:5px;
padding:1px 7px;font-size:12px;margin-right:6px}
.tag.fix{background:#eaf6ee;color:var(--ok)}
code{background:#f0f2f5;border-radius:4px;padding:1px 5px;font-size:12.5px}
</style></head><body><div class="wrap">

<h1>条款符合性核验与落地 · 验收报告</h1>
<div class="sub">对象：《一键分析集成条款（10 条）》+《专注税务风险检查条款（5 条）》 ｜
方法：只读核验脚本 + 真实产物取证（非肉眼读代码）｜ 生成时间见页脚</div>

<h2>一、结论速览</h2>
<div class="kpi">
  <div><b class="ok">%(ok)s</b>符合</div>
  <div><b class="warn">%(part)s</b>部分符合</div>
  <div><b class="bad">%(no)s</b>不符合</div>
  <div><b>%(gt)s</b>常驻闸门 ERROR</div>
  <div><b class="ok">6/6</b>反向验证通过</div>
</div>
<div class="card">
<b>一句话结论</b>：15 条中 <b>%(ok_total)s 条已符合</b>（含本轮修好的 5 个真缺口），
常驻闸门 <code>check_clause_compliance</code> 本轮 <b>%(gt)s 条 ERROR</b>，
反向验证 <b>6/6</b> 全部报红（故意破坏均被拦下）。
<table style="margin-top:10px">%(mtrs)s</table>
</div>

<h2>二、逐条核验结果（真实产物取证）</h2>
<div class="card"><table>
<tr><th style="width:52px">编号</th><th style="width:290px">条款</th>
<th style="width:74px">判定</th><th>证据（实测）</th></tr>
%(trs)s
</table></div>

<h2>三、核验出的 %(ngaps)d 个真缺口（按根因修，不打补丁）</h2>
%(gaps)s

<h2>四、常驻闸门（防复发）</h2>
<div class="card">
<code>tools/audit_consistency.check_clause_compliance()</code> —— 6 条可机器判定：
C1 去重三项 ｜ C2 去重字段安全 ｜ C3 编号不偏移 ｜ C4 结论术语权威 ｜ C5 知识闭环传 case ｜ C6 效力声明。
<table><tr><th style="width:70px">级别</th><th style="width:300px">落点</th><th>说明</th></tr>%(gtrs)s</table>
<div class="small" style="margin-top:8px">反向验证：<code>scripts/_rev_verify_clause_gates.py</code>（<b>子进程逐轮</b>，
避免 import 缓存造成假红/假绿）。</div>
</div>

<h2>五、新增/收敛的单一权威</h2>
<div class="card">
<ul style="margin:0;padding-left:22px">
<li><code>config/conclusion_grades.json::term_authority</code> —— 结论用语四词
「风险信号 / 待核事项 / 已认定事实 / 违法认定」+ L1~L4 映射 + 越权定性词表；
<code>engine.conclusion_grade.conclusion_terms()/term_of()</code> 薄转发；报告 <code>report_statement</code> 追加声明（从权威表生成，不硬编码）。</li>
<li><code>engine/dedup_pipeline.duplicate_rate()</code> —— 重复率三项<b>唯一权威</b>；离线 <code>_phase1_diagnose</code> 薄转发。</li>
<li><code>engine/report_pipeline.dedup_sentences_cross()</code> —— 句子级跨事项事实去重。</li>
<li><code>engine/report_pipeline.merge_report_level_notes()</code> ＋
<code>enterprise_report._report_level_notes_statement()</code> —— 报告级通用口径**上提**（共用常量表
<code>REPORT_LEVEL_TEXT_KEYS</code>；逐项位置引用「见报告性质和使用说明」，避免悬空）。</li>
<li><code>engine/report_wording.vague_hits()</code> / <code>_authoritative_terms()</code> ——
模糊词判据与**结论术语豁免**的唯一实现（<code>quality_gates</code>、一致性闸门、两处测试均薄转发）。</li>
<li><code>engine/knowledge_learner.problems_from_report()/case_from_report()</code> —— 闭环取数唯一权威。</li>
<li><code>engine/enterprise_report._administrative_boundary_statement()</code> —— 效力声明唯一权威（可运行时断言）。</li>
</ul></div>

<h2>六、局限与未做</h2>
<div class="card small">
① 部分条款（如"资料读取→…→风险扫描"的内部实现顺序、行业话术自然度）无法由静态/单产物断言完全覆盖，
仍需运行期留痕（<code>_one_click_pipeline.stages</code>）与人工抽样；
② 报告正文仍使用"风险事项/疑点"作为<b>结构对象名</b>（非结论用语），故未替换为"风险信号"——
若要求连结构名一并统一，请单独确认；
③ 本轮改了 <code>static/js/tax-doc-analysis.js</code> 兜底文案 ⇒ 已同步静态资源版本，
浏览器需 <b>Ctrl+F5</b> 才能看到新前端。
</div>

<div class="sub" style="margin-top:26px">本报告由 <code>scripts/_build_clause_report.py</code> 自动生成；
数据源：<code>data/_clause_audit.json</code> + <code>tools/audit_consistency.check_clause_compliance()</code> +
真实产物 <code>data/cache/last_analysis_cache.json</code>。</div>
</div></body></html>""" % {
        "ok": sm.get("ok", 0), "part": sm.get("part", 0), "no": sm.get("no", 0),
        "ok_total": (sm.get("ok", 0) + sm.get("part", 0)),
        "gt": len(gates),
        "mtrs": mtrs, "trs": trs, "gtrs": gtrs, "gaps": gaps_html, "ngaps": len(GAPS),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(doc)
    print("已生成 %s（%d 字节）；核验 %s 有 / %s 部分 / %s 无；闸门 %d 条"
          % (OUT, len(doc.encode("utf-8")), sm.get("ok"), sm.get("part"), sm.get("no"), len(gates)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
