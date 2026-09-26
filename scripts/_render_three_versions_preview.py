# -*- coding: utf-8 -*-
"""离线三版预览：把 company_1_full.json 的 enterprise_readable_report 渲染为
自包含 HTML（决策版 / 执行版 / 底稿版 + 顶部切换），供不开服务器直接审阅。

用法：python scripts/_render_three_versions_preview.py
输出：scripts/four_reports/three_versions_preview.html
"""
import json, os, html, datetime

REPO = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(REPO)
SRC = "scripts/four_reports/company_1_full.json"
OUT = "scripts/four_reports/three_versions_preview.html"

raw = json.load(open(SRC, encoding="utf-8"))
er = raw.get("enterprise_readable_report") or {}
rep = raw  # 顶层 report_data（执行版需要 all_findings / resolution_ledger 等）

E = lambda s: html.escape(str(s if s is not None else ""), quote=True)

def money(v):
    try:
        if v is None or v == "":
            return "—"
        return "{:,.2f}".format(float(v))
    except Exception:
        return E(v)

def lvl_color(lv):
    if lv == "高风险": return "#c92a2a"
    if lv == "中风险": return "#e67700"
    if lv == "低风险": return "#2b8a3e"
    return "#64748b"

# ───────── 决策版 ─────────
def render_boss(boss):
    if not boss: return '<div class="empty">无决策版数据</div>'
    h = []
    h.append('<div class="badge-box" style="border-color:#1e3a8a;background:#eff6ff;color:#1e3a8a">'
             '📊 ' + E(boss.get("variant", "管理层决策版"))
             + '　本报告为决策版：只给结论、量化敞口、待决策事项与行动路线，不含检查程序与原始证据。</div>')
    h.append('<div class="conclude">' + E(boss.get("one_line_conclusion", "")) + '</div>')
    es = boss.get("executive_summary") or {}
    h.append('<h2>一、执行摘要</h2>')
    if es.get("headline"): h.append('<p>' + E(es["headline"]) + '</p>')
    if es.get("key_points"):
        h.append('<ul>' + "".join("<li>%s</li>" % E(p) for p in es["key_points"]) + '</ul>')
    ro = boss.get("risk_overview") or {}
    h.append('<h2>二、风险事项总览（量化敞口）</h2>')
    if ro.get("exposure_note"): h.append('<p class="muted">' + E(ro["exposure_note"]) + '</p>')
    rows = ro.get("rows") or []
    if rows:
        cols = ro.get("columns") or ["风险事项", "等级", "定性", "涉及金额（潜在最大）", "证据成熟度/概率评估", "是否触发预警规则", "责任部门/人"]
        h.append('<table><thead><tr>' + "".join("<th>%s</th>" % E(c) for c in cols) + '</tr></thead><tbody>')
        for rw in rows:
            h.append('<tr>'
                + '<td>' + E(rw.get("type", "")) + '</td>'
                + '<td style="color:%s;font-weight:600">' % lvl_color(rw.get("level")) + E(rw.get("level", "")) + '</td>'
                + '<td>' + E(rw.get("grade", "")) + '</td>'
                + '<td class="r">' + E(rw.get("exposure_text", "")) + '</td>'
                + '<td>' + E(rw.get("probability", "")) + '</td>'
                + '<td>' + E(rw.get("triggered_redline", "")) + '</td>'
                + '<td>' + E(rw.get("owner", "")) + '</td></tr>')
        h.append('</tbody></table>')
    if ro.get("total_exposure_max") is not None:
        h.append('<p class="money">合计潜在最大敞口：' + money(ro["total_exposure_max"])
                 + '元（仅列可提取的最大可识别金额；最佳/最小估计需概率输入，未提供）</p>')
    top5 = boss.get("top5") or []
    if top5:
        h.append('<h2>三、重大风险 TOP5</h2><ol>')
        for t in top5:
            h.append('<li><b>' + E(t.get("type", "")) + '</b>　<span class="muted">' + E(t.get("level", "")) + '·' + E(t.get("grade", "")) + '</span>　' + E(t.get("exposure_text", ""))
                     + '<div class="muted">' + E(t.get("why", "")) + '</div></li>')
        h.append('</ol>')
    rm = boss.get("remediation_roadmap") or {}
    h.append('<h2>四、整改路线图</h2>')
    for k in ("d7", "d30", "d60", "d90"):
        sec = rm.get(k) or {}
        items = sec.get("items") or []
        if not items: continue
        h.append('<h3>' + E(sec.get("label", k)) + '</h3><ul>' + "".join("<li>%s</li>" % E(it) for it in items) + '</ul>')
    dn = boss.get("decisions_needed") or []
    if dn:
        h.append('<h2>五、需管理层决策事项</h2>')
        for d in dn:
            h.append('<div class="card" style="border-color:#fed7aa;background:#fff7ed">'
                + '<b>' + E(d.get("item", "")) + '</b>'
                + '<div class="muted">背景：' + E(d.get("context", "")) + '</div>'
                + '<div>决策请求：' + E(d.get("ask", "")) + '</div></div>')
    al = boss.get("audit_limitations") or {}
    h.append('<h2>六、检查受限说明</h2>')
    h.append('<p>受限资料类别 ' + E(str(al.get("missing_doc_count", 0))) + ' 项；待核实疑点 ' + E(str(al.get("pending_suspicion_count", 0))) + ' 项。' + E(al.get("note", "")) + '</p>')
    md = al.get("missing_docs") or []
    if md: h.append('<ul>' + "".join("<li>%s</li>" % E(d) for d in md) + '</ul>')
    rn = boss.get("report_nature") or []
    if rn:
        h.append('<h2>七、报告性质与适用边界</h2><ul>' + "".join("<li>%s</li>" % E(t) for t in rn) + '</ul>')
    ai = boss.get("appendix_index") or []
    if ai:
        h.append('<h2>八、附录索引</h2><table><thead><tr><th>章节</th><th>说明</th></tr></thead><tbody>')
        for a in ai:
            h.append('<tr><td>' + E(a.get("chapter", "")) + '</td><td>' + E(a.get("desc", "")) + '</td></tr>')
        h.append('</tbody></table>')
    return "\n".join(h)

# ───────── 底稿版 ─────────
def _wp_raw(v):
    if isinstance(v, str): return E(v)
    try: return '<pre class="raw">' + E(json.dumps(v, ensure_ascii=False, indent=1)) + '</pre>'
    except Exception: return E(str(v))

def render_wp_item(it, n):
    h = ['<div class="card"><div class="wp-head">'
         + '<span class="muted">#' + str(n) + '</span> <b>' + E(it.get("type", "")) + '</b>'
         + ' <span class="pill">' + E(it.get("level", "")) + '</span>'
         + (' <span class="pill2">' + E(it.get("conclusion_grade", "")) + '</span>' if it.get("conclusion_grade") else '')
         + (' <span class="muted">' + E(it.get("redline_id", "")) + '</span>' if it.get("redline_id") else '')
         + (' <span class="muted">证据地位：' + E(it.get("evidence_tier", "")) + '</span>' if it.get("evidence_tier") else '')
         + '</div>']
    if it.get("category"):
        h.append('<div class="muted">分类：' + E(it.get("category", ""))
                 + (('　证据成熟度：' + E(it.get("evidence_maturity", ""))) if it.get("evidence_maturity") else '') + '</div>')
    if it.get("detail"): h.append('<p class="detail">' + E(it.get("detail")).replace("\n", "<br>") + '</p>')
    om = it.get("observed_metrics")
    if isinstance(om, dict) and om:
        h.append('<div><b>量化指标：</b>' + "；".join(E(k) + "=" + E(str(v)) for k, v in om.items()) + '</div>')
    if it.get("how_found"): h.append('<div class="muted">发现方式：' + E(it.get("how_found")) + '</div>')
    ers = it.get("evidence_rows") or []
    if ers:
        h.append('<div><b>逐笔证据（%d 条）：</b></div><table><thead><tr><th>来源</th><th>交易对方</th><th>金额</th><th>日期</th><th>说明</th></tr></thead><tbody>' % len(ers))
        for rw in ers:
            amt = money(rw.get("amount")) if rw.get("amount") is not None else ""
            h.append('<tr><td>' + E(rw.get("source", "")) + '</td><td>' + E(rw.get("counterparty", "")) + '</td>'
                     + '<td class="r">' + amt + '</td><td>' + E(rw.get("date", "")) + '</td><td>' + E(rw.get("note", "")) + '</td></tr>')
        h.append('</tbody></table>')
    if it.get("self_proof_materials"): h.append('<div><b>自证资料：</b>' + _wp_raw(it.get("self_proof_materials")) + '</div>')
    if it.get("resolve_steps"): h.append('<div><b>解除方式：</b>' + _wp_raw(it.get("resolve_steps")) + '</div>')
    laws = it.get("laws") or []
    if laws:
        h.append('<div><b>法规依据：</b></div><ul>' + "".join("<li>%s</li>" % E(l if isinstance(l, str) else json.dumps(l, ensure_ascii=False)) for l in laws) + '</ul>')
    if it.get("terminal_state"): h.append('<div class="muted">终局方向：' + E(it.get("terminal_state")) + '</div>')
    if it.get("trace_id"): h.append('<div class="trace">trace_id：' + E(str(it.get("trace_id"))) + '</div>')
    h.append('</div>')
    return "\n".join(h)

def render_wp(wp):
    if not wp: return '<div class="empty">无底稿版数据</div>'
    h = ['<div class="badge-box" style="border-color:#334155;background:#f1f5f9;color:#334155">'
         + '🗂 ' + E(wp.get("variant", "底稿版")) + '　' + E(wp.get("note", ""))
         + '　全量发现 ' + E(str(wp.get("all_findings_count", 0))) + ' 项。'
         + (('　' + E(wp.get("inspection_questions_ref", ""))) if wp.get("inspection_questions_ref") else '')
         + (('　' + E(wp.get("reconciliation_ref", ""))) if wp.get("reconciliation_ref") else '')
         + '</div>']
    for cat in (wp.get("by_category") or []):
        h.append('<h2>' + E(cat.get("category", "未分类")) + '（' + str(cat.get("count", 0)) + ' 项）</h2>')
        for i, it in enumerate(cat.get("items") or [], 1):
            h.append(render_wp_item(it, i))
    return "\n".join(h)

# ───────── 执行版（Python 静态渲染 enterprise_readable_report 主要章节）─────────
def render_exec(er, rep):
    h = []
    h.append('<div class="badge-box" style="border-color:#047857;background:#ecfdf5;color:#065f46">'
             + '📋 执行版（企业整改执行版）　' + E(er.get("report_variant", ""))
             + '　整改任务清单 + 逐项底稿 + 补证模板与询问清单。</div>')
    sm = er.get("summary") or {}
    if sm.get("headline"):
        h.append('<h2>一、总体结论</h2><p>' + E(sm.get("headline")) + '</p>')
    probs = er.get("confirmed_problems") or []
    if probs:
        h.append('<h2>二、确认的具体问题（整改任务清单，按等级×金额）</h2>')
        h.append('<table><thead><tr><th>序</th><th>问题</th><th>等级</th><th>定性</th><th>处理建议</th></tr></thead><tbody>')
        for p in probs:
            sug = p.get("suggestion") or ""
            sug = (sug[:160] + "…") if len(sug) > 160 else sug
            h.append('<tr><td>' + E(str(p.get("seq", ""))) + '</td>'
                + '<td>' + E(p.get("title", "")) + '</td>'
                + '<td style="color:%s;font-weight:600">' % lvl_color(p.get("risk_level") or p.get("level")) + E(p.get("risk_level") or p.get("level", "")) + '</td>'
                + '<td>' + E(p.get("conclusion_grade", "")) + '</td>'
                + '<td>' + E(sug) + '</td></tr>')
        h.append('</tbody></table>')
    led = er.get("resolution_ledger") or {}
    lrows = led.get("rows") or []
    if lrows:
        h.append('<h2>三、全部风险事项台账（解除方式 / 自证资料 / 终局方向）</h2>')
        cols = led.get("columns") or ["风险事项", "等级", "证据地位", "终局方向", "解除方式", "需补自证资料"]
        h.append('<table><thead><tr>' + "".join("<th>%s</th>" % E(c) for c in cols) + '</tr></thead><tbody>')
        for r in lrows:
            h.append('<tr>' + "".join("<td>%s</td>" % E(r.get(c, "")) for c in cols) + '</tr>')
        h.append('</tbody></table>')
    mr = er.get("material_readiness") or {}
    if mr:
        h.append('<h2>四、必查资料齐备性</h2><p>' + E(mr.get("summary_text", "")) + '</p>')
        miss = mr.get("missing") or []
        if miss:
            h.append('<table><thead><tr><th>缺失资料</th><th>无法检查的风险</th><th>补什么能查清</th></tr></thead><tbody>')
            for m0 in miss:
                hm = "、".join(m0.get("uncheckable_risks") or [])[:160]
                h.append('<tr><td>' + E(m0.get("doc", "")) + '</td><td>' + E(hm) + '</td><td>' + E(str(m0.get("remedy", ""))[:200]) + '</td></tr>')
            h.append('</tbody></table>')
    iq = er.get("inspection_questions_report") or {}
    if iq:
        h.append('<h2>五、风险检查询问清单（摘要）</h2>')
        qs = iq.get("questions") or []
        if qs:
            h.append('<ul>' + "".join("<li>%s</li>" % E(q.get("question") if isinstance(q, dict) else q) for q in qs[:30]) + '</ul>')
        else:
            h.append('<p class="muted">（本章含询问清单，详见系统在线报告）</p>')
    return "\n".join(h)

# ───────── 组装 HTML ─────────
boss_html = render_boss(er.get("boss_decision_report"))
wp_html = render_wp(er.get("working_paper_report"))
exec_html = render_exec(er, rep)

doc = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>三版税务风险报告预览 - {co}</title>
<style>
:root{{--ink:#1f2937;--ink2:#4b5563;--ink3:#6b7280;--line:#e5e7eb;--bg:#f7f8fa;--card:#fff;
--brand:#1d4ed8;--warn:#b45309;--ok:#166534}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:"Microsoft YaHei","PingFang SC",system-ui,sans-serif;line-height:1.75;font-size:14px}}
.wrap{{max-width:1000px;margin:0 auto;padding:24px 20px 60px}}
.switch{{position:sticky;top:0;z-index:10;display:flex;gap:8px;background:#fff;border:1px solid var(--line);
border-radius:10px;padding:10px 12px;margin-bottom:16px;flex-wrap:wrap;align-items:center;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
.switch .lbl{{font-size:12px;color:var(--ink3);margin-right:4px}}
.switch button{{cursor:pointer;border:1px solid #cbd5e1;background:#fff;border-radius:8px;padding:8px 14px;
font-family:inherit;display:flex;flex-direction:column;align-items:flex-start;gap:2px}}
.switch button b{{font-size:13px}}
.switch button span{{font-size:11px;color:var(--ink3)}}
.switch button.on{{border-color:var(--brand);background:#eff6ff}}
.switch button.on b{{color:var(--brand)}}
.ver{{display:none}}
.ver.on{{display:block}}
.badge-box{{border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:0 0 14px;font-size:12px}}
.conclude{{border-left:4px solid #c92a2a;background:#fff5f5;padding:12px 16px;margin:0 0 18px;border-radius:6px;font-size:14px;color:#7f1d1d}}
section,.sec{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 24px;margin-bottom:16px;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
h2{{font-size:17px;margin:0 0 14px;padding-bottom:9px;border-bottom:2px solid var(--brand);display:inline-block}}
h3{{font-size:14.5px;margin:18px 0 8px;color:var(--ink)}}
p{{margin:8px 0}}
.muted{{color:var(--ink3);font-size:13px}}
.money{{font-size:13px;color:#7f1d1d}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0}}
th,td{{border:1px solid var(--line);padding:7px 10px;text-align:left;vertical-align:top}}
th{{background:#f3f4f6;font-weight:600;color:var(--ink2);white-space:nowrap}}
td.r{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
ul{{margin:8px 0 8px 20px;padding:0}} li{{margin:4px 0}}
.card{{border:1px solid var(--line);border-radius:9px;padding:12px 14px;margin:10px 0;background:#fcfcfd}}
.pill{{font-size:11px;color:#fff;background:#475569;border-radius:4px;padding:1px 6px}}
.pill2{{font-size:11px;color:#fff;background:#0ea5e9;border-radius:4px;padding:1px 6px}}
.wp-head{{font-size:13px;margin-bottom:4px}}
.detail{{font-size:12px;margin:6px 0;white-space:pre-wrap}}
.raw{{white-space:pre-wrap;font-size:11px;margin:2px 0;background:#f9fafb;border:1px solid var(--line);border-radius:6px;padding:8px}}
.trace{{font-size:10px;color:#94a3b8}}
.empty{{background:#f9fafb;border:1px dashed var(--line);border-radius:8px;padding:14px;color:var(--ink3);font-size:13px}}
.foot{{color:var(--ink3);font-size:12.5px;text-align:center;margin-top:22px;line-height:1.9}}
</style></head><body><div class="wrap">
<div class="switch"><span class="lbl">报告版本：</span>
<button data-v="boss" class="on" onclick="sw('boss')"><b>管理层决策版（默认）</b><span>结论·量化·决策</span></button>
<button data-v="exec" onclick="sw('exec')"><b>执行版（整改）</b><span>任务·底稿·补证</span></button>
<button data-v="wp" onclick="sw('wp')"><b>底稿版（检查组）</b><span>全量证据·法规</span></button>
</div>
<div id="v-boss" class="ver on"><section>{boss}</section></div>
<div id="v-exec" class="ver"><section>{exec}</section></div>
<div id="v-wp" class="ver"><section>{wp}</section></div>
<div class="foot">离线预览 · 数据来源 company_1_full.json · 生成时间 {gen}</div>
</div>
<script>
function sw(v){{
  ['boss','exec','wp'].forEach(function(x){{
    document.getElementById('v-'+x).classList.toggle('on', x===v);
    var b=document.querySelector('.switch button[data-v="'+x+'"]'); if(b) b.classList.toggle('on', x===v);
  }});
}}
</script></body></html>"""

co = E((rep.get("target_entity") or {}).get("name") or "未知主体")
gen = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
out = doc.format(co=co, boss=boss_html, exec=exec_html, wp=wp_html, gen=gen)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(out)
print("已生成:", OUT, os.path.getsize(OUT), "bytes")
