# -*- coding: utf-8 -*-
"""把分析结果 JSON 渲染为可直接阅读的自包含 HTML 报告。

用法：python scripts/_render_report_html.py [结果JSON] [输出HTML]
默认读取 scripts/four_reports/company_1_api_result.json
"""
import json, os, sys, html, datetime

REPO = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(REPO)

SRC = sys.argv[1] if len(sys.argv) > 1 else "scripts/four_reports/company_1_api_result.json"
OUT = sys.argv[2] if len(sys.argv) > 2 else "scripts/four_reports/company_1_report.html"

E = lambda s: html.escape(str(s if s is not None else ""), quote=True)


def tr(s, n=600):
    s = str(s if s is not None else "").strip()
    return s if len(s) <= n else s[:n] + "…"


def esc_lines(s):
    return "<br>".join(E(x) for x in str(s or "").split("\n"))


def money(v):
    try:
        if v is None or v == "":
            return "—"
        return "{:,.2f}".format(float(v))
    except Exception:
        return E(v)


raw = json.load(open(SRC, encoding="utf-8"))
rep = raw.get("report") or {}
te = rep.get("target_entity") or {}
err = rep.get("enterprise_readable_report") or {}
sc = rep.get("subject_check") or {}
rm = rep.get("reconciliation_matrix") or {}
dr = rep.get("document_requests") or []
mw = rep.get("manual_worksheets") or []
fr = rep.get("file_results") or []
findings = rep.get("all_findings") or []
ds = rep.get("domain_summary") or []
chapters = rep.get("_report_chapters") or {}

from collections import Counter
type_dist = dict(Counter((x.get("type") or "未知") for x in fr))
TYPE_CN = {
    "vat_declaration": "增值税申报表", "cit_declaration": "企业所得税申报表",
    "bank": "银行流水", "bank_statement": "银行流水", "salary": "工资表",
    "social_security": "社保明细", "purchase_invoice": "进项发票", "sales_invoice": "销项发票",
    "invoice_universal": "发票", "voucher": "记账凭证", "trial_balance": "科目余额表",
    "subject_mismatch": "主体不符(已剔除)", "generic_data": "其他资料",
}
dist_txt = "、".join("%s %d 份" % (TYPE_CN.get(k, k), v) for k, v in type_dist.items()) or "无"

P = []
_co = E(te.get("name") or "未知主体")
P.append("""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>涉税风险分析报告 - """ + _co + """</title>
<style>
:root{--ink:#1f2937;--ink2:#4b5563;--ink3:#6b7280;--line:#e5e7eb;--bg:#f7f8fa;--card:#ffffff;
--brand:#1d4ed8;--warn:#b45309;--warnbg:#fff9ec;--danger:#b91c1c;--ok:#166534;--okbg:#f0fdf4}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font-family:"Microsoft YaHei","PingFang SC","Hiragino Sans GB","Source Han Sans SC",system-ui,sans-serif;
line-height:1.75;font-size:14px}
.wrap{max-width:960px;margin:0 auto;padding:28px 22px 60px}
.cover{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:30px 32px;margin-bottom:18px;
box-shadow:0 1px 2px rgba(0,0,0,.04)}
.cover h1{margin:0 0 4px;font-size:25px;letter-spacing:.5px}
.cover .sub{color:var(--ink3);font-size:13px;margin-bottom:20px}
.kv{display:grid;grid-template-columns:130px 1fr;gap:8px 14px;font-size:13.5px}
.kv dt{color:var(--ink3)}
.kv dd{margin:0;color:var(--ink)}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:22px 26px;margin-bottom:16px;
box-shadow:0 1px 2px rgba(0,0,0,.04)}
h2{font-size:17px;margin:0 0 14px;padding-bottom:9px;border-bottom:2px solid var(--brand);display:inline-block}
h2 .n{color:var(--brand);margin-right:6px}
h3{font-size:14.5px;margin:18px 0 8px;color:var(--ink)}
p{margin:8px 0}
.muted{color:var(--ink3);font-size:13px}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12.5px;margin-right:6px}
.pill.ok{background:var(--okbg);color:var(--ok);border:1px solid #bbf7d0}
.pill.warn{background:var(--warnbg);color:var(--warn);border:1px solid #fde68a}
.pill.danger{background:#fef2f2;color:var(--danger);border:1px solid #fecaca}
.pill.info{background:#eff6ff;color:var(--brand);border:1px solid #bfdbfe}
.note{background:var(--warnbg);border-left:3px solid var(--warn);padding:11px 14px;border-radius:0 8px 8px 0;
color:#7c4a03;font-size:13px;margin:10px 0}
.empty{background:#f9fafb;border:1px dashed var(--line);border-radius:8px;padding:14px 16px;color:var(--ink3);font-size:13px}
table{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0}
th,td{border:1px solid var(--line);padding:7px 10px;text-align:left;vertical-align:top}
th{background:#f3f4f6;font-weight:600;color:var(--ink2);white-space:nowrap}
td.mono{font-family:Consolas,Menlo,monospace;font-size:12px}
ul{margin:8px 0 8px 20px;padding:0}
li{margin:4px 0}
.card{border:1px solid var(--line);border-radius:9px;padding:13px 15px;margin:10px 0;background:#fcfcfd}
.card .t{font-weight:600;margin-bottom:4px}
.badge{font-size:12px;padding:1px 8px;border-radius:4px;background:#eef2ff;color:#3730a3;margin-left:6px}
details{margin:8px 0;border:1px solid var(--line);border-radius:8px;padding:8px 12px;background:#fcfcfd}
summary{cursor:pointer;font-weight:600;font-size:13.5px}
.foot{color:var(--ink3);font-size:12.5px;text-align:center;margin-top:22px;line-height:1.9}
@media print{body{background:#fff}.cover,section{box-shadow:none;break-inside:avoid}}
</style></head><body><div class="wrap">""")

# ── 封面 ──
gen = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
P.append('<div class="cover"><h1>涉税风险分析报告</h1>'
         '<div class="sub">系统自动生成 · 分析与核验工作底稿 · %s</div>' % E(gen))
P.append('<dl class="kv">')
for label, val in (("被查单位", te.get("name")), ("统一社会信用代码", te.get("uscc")),
                   ("法定代表人", te.get("legal_person") or te.get("legal_representative")),
                   ("经营模式", te.get("biz_model")),
                   ("经营范围", tr(te.get("business_scope"), 180))):
    if val:
        P.append("<dt>%s</dt><dd>%s</dd>" % (E(label), esc_lines(val)))
P.append("<dt>资料份数</dt><dd>%s 份（%s）</dd>" % (E(rep.get("files_count")), E(dist_txt)))
P.append("</dl></div>")

# ── 一、总体结论 ──
P.append('<section><h2><span class="n">一</span>总体结论</h2>')
lvl = rep.get("overall_level") or "未形成待核事实"
_lv = "ok" if ("未形成" in str(lvl) or "无" in str(lvl)) else ("danger" if rep.get("high_risk") else "warn")
P.append('<p><span class="pill %s">%s</span>'
         '<span class="pill info">共 %s 项</span>'
         '<span class="pill info">高 %s / 中 %s / 低 %s</span></p>'
         % (_lv, E(lvl), E(rep.get("total_risks")), E(rep.get("high_risk")),
            E(rep.get("mid_risk")), E(rep.get("low_risk"))))
if rep.get("summary_text"):
    P.append("<p>%s</p>" % esc_lines(rep["summary_text"]))
P.append("</section>")

# ── 二、主体与资料 ──
P.append('<section><h2><span class="n">二</span>主体一致性</h2>')
if sc.get("mismatched_count"):
    P.append('<div class="note"><strong>已剔除 %s 份主体与账套不一致的资料</strong>（未参与任何结论）：<br>%s</div>'
             % (E(sc["mismatched_count"]),
                "<br>".join("· " + E(m.get("file")) + "　" + E(m.get("reason")) for m in (sc.get("mismatched") or [])[:10])))
else:
    P.append('<p><span class="pill ok">主体一致</span>本账套「%s」的资料主体校验通过。</p>' % E(sc.get("account_subject") or te.get("name")))
if sc.get("note"):
    P.append('<p class="muted">%s</p>' % E(sc["note"]))
P.append("</section>")

# ── 三、资料缺口与勾稽 ──
P.append('<section><h2><span class="n">三</span>资料缺口与勾稽</h2>')

# 必查资料齐备性（15 类）—— 就是报告区"缺增值税申报表"那句的出处
_mr = err.get("material_readiness") or {}
if _mr:
    P.append('<h3>必查资料齐备性</h3>')
    P.append('<p>%s</p>' % E(_mr.get("summary_text") or ""))
    _prov = _mr.get("provided") or []
    _miss = _mr.get("missing") or []
    P.append('<p><strong>已提供（%d 类）：</strong>%s</p>'
             % (len(_prov), E("、".join(_prov)) if _prov else "无"))
    if _miss:
        P.append("<table><tr><th>缺失资料</th><th>因此无法检查的风险</th><th>补什么能查清</th></tr>")
        for m0 in _miss:
            P.append("<tr><td>%s</td><td>%s</td><td>%s</td></tr>"
                     % (E(m0.get("doc")), E("、".join(m0.get("uncheckable_risks") or [])[:160]),
                        tr(m0.get("remedy"), 200)))
        P.append("</table>")
    else:
        P.append('<p><span class="pill ok">资料齐全</span></p>')

if rm:
    P.append('<h3>勾稽矩阵</h3><p class="muted">缺失项 %s 项，差异项 %s 项。</p>'
             % (E(rm.get("missing_count")), E(rm.get("diff_count"))))
    pairs = rm.get("pairs") or []
    if pairs:
        P.append("<table><tr><th>勾稽关系</th><th>状态</th><th>说明</th></tr>")
        for p0 in pairs[:20]:
            P.append("<tr><td>%s</td><td>%s</td><td>%s</td></tr>"
                     % (E(p0.get("left")), E(p0.get("status")), tr(p0.get("note") or p0.get("detail"), 160)))
        P.append("</table>")
if dr:
    P.append("<h3>需补充资料清单</h3>")
    for d in dr[:12]:
        _flow = str(d.get("flow") or "")
        P.append('<div class="card"><div class="t">%s <span class="badge">%s</span></div>'
                 % (E(_flow), E(d.get("status"))))
        if d.get("missing_items"):
            P.append("<div><strong>缺失：</strong>%s</div>" % E("、".join(d["missing_items"][:10])))
        if d.get("impact"):
            P.append('<div class="muted">影响：%s</div>' % tr(d["impact"], 300))
        P.append("</div>")
if not rm and not dr:
    P.append('<div class="empty">本期未生成资料缺口与勾稽结论。</div>')

# 申报表逐期数据（已解析内容，直接体现 PDF 读取成果）
_decls = [d for d in (rep.get("tax_declarations") or []) if isinstance(d, dict)]
if _decls:
    _decls = sorted(_decls, key=lambda d: str(d.get("period") or ""))
    P.append('<h3>已解析申报表逐期数据（%d 期）</h3>' % len(_decls))
    P.append("<table><tr><th>所属期</th><th>销售额</th><th>销项税额</th><th>进项税额</th><th>应补(退)税额</th></tr>")
    for d in _decls:
        P.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                 % (E(d.get("period") or "—"), money(d.get("sales_amount")),
                    money(d.get("sales_tax")), money(d.get("input_tax")), money(d.get("payable_tax"))))
    P.append("</table>")
P.append("</section>")

# ── 四、全部风险事项台账（含证据地位）──
_led = err.get("resolution_ledger") or {}
_led_rows = _led.get("rows") or []
if _led_rows:
    P.append('<section><h2><span class="n">四</span>全部风险事项台账与解除/自证清单</h2>')
    _tiers = _led.get("evidence_tiers") or {}
    if _tiers:
        _th = " ".join('<span class="pill info">%s：%s 项</span>' % (E(k), E(v))
                       for k, v in _tiers.items() if v)
        P.append("<p>%s</p>" % _th)
    _led_cols = _led.get("columns") or ["风险事项", "等级", "证据地位", "终局方向", "解除方式", "需补自证资料"]
    P.append('<p class="muted">本台账逐条列示系统依据本轮上传资料分析出的全部风险事项'
             '（共 %s 项），证据地位仅表示结论的取得方式，不代表风险大小。</p>'
             % E(_led.get("total") or len(_led_rows)))
    P.append("<table><tr><th>%s</th></tr>" % "</th><th>".join(E(c) for c in _led_cols))
    for r in _led_rows:
        P.append("<tr>")
        for c in _led_cols:
            v = r.get(c)
            if c == "证据地位":
                sv = str(v or "")
                cls = "info" if "已验原子规则" in sv else ("warn" if "域分析结论" in sv else "")
                P.append('<td><span class="pill %s">%s</span></td>' % (cls, E(sv or "—")))
            else:
                P.append("<td>%s</td>" % E(v or "—"))
        P.append("</tr>")
    P.append("</table>")
    if _led.get("evidence_tier_note"):
        P.append('<p class="muted">%s</p>' % E(_led["evidence_tier_note"]))
    P.append("</section>")

# ── 五、待核事实与发现 ──
P.append('<section><h2><span class="n">五</span>待核事实与发现</h2>')
if findings:
    lv_order = {"极高风险": 0, "高风险": 1, "中风险": 2, "低风险": 3}
    for f in sorted(findings, key=lambda x: lv_order.get(str(x.get("level")), 9))[:60]:
        P.append('<div class="card"><div class="t">【%s】%s</div>'
                 % (E(f.get("level") or "未分级"), E(f.get("type") or "")))
        for lab, key in (("事实", "detail"), ("描述", "description"), ("依据", "policy_ref"),
                         ("发现方式", "how_found"), ("建议", "suggestion")):
            v = f.get(key)
            if v:
                P.append("<div><strong>%s：</strong>%s</div>" % (E(lab), tr(v, 700)))
        P.append("</div>")
else:
    P.append('<div class="empty">本期<b>未形成任何待核事实或风险发现</b>。'
             '原因：当前账套仅有增值税申报表，缺少发票、银行流水、工资、社保、凭证等可比对资料，'
             '域分析无交叉验证数据源。补充上述资料后重新分析即可产出结论。</div>')
P.append("</section>")

# ── 六、业务域分析 ──
P.append('<section><h2><span class="n">六</span>业务域分析</h2>')
if ds:
    P.append("<table><tr><th>业务域</th><th>发现数</th></tr>")
    for d in ds:
        P.append("<tr><td>%s</td><td>%s</td></tr>" % (E(d.get("domain")), len(d.get("findings") or [])))
    P.append("</table>")
else:
    P.append('<div class="empty">本期未运行到产生结论的业务域（数据不足以支撑交叉验证）。</div>')
P.append("</section>")

# ── 七、报告边界与声明 ──
P.append('<section><h2><span class="n">七</span>报告边界与声明</h2><dl class="kv">')
for lab, key in (("覆盖范围", "scope"), ("使用限制", "limitations"),
                 ("结论表达规则", "conclusion_policy"), ("发布边界", "release_boundary")):
    if rep.get(key):
        P.append("<dt>%s</dt><dd>%s</dd>" % (E(lab), esc_lines(rep[key])))
P.append("</dl></section>")

# ── 附一：文件解析明细 ──
P.append('<section><h2><span class="n">附</span>资料解析明细</h2>')
if fr:
    P.append("<table><tr><th>文件</th><th>识别类型</th><th>解析动作</th></tr>")
    for x in fr:
        acts = "；".join(str(a) for a in (x.get("actions") or [])[:3])
        P.append('<tr><td>%s</td><td>%s</td><td class="mono">%s</td></tr>'
                 % (E(x.get("file")), E(TYPE_CN.get(x.get("type"), x.get("type"))), tr(acts, 240)))
    P.append("</table>")
else:
    P.append('<div class="empty">无</div>')
P.append("</section>")

# ── 附二：人工核查工作底稿 ──
if mw:
    P.append('<section><h2><span class="n">附</span>人工核查工作底稿（系统不能自动完成，须人工执行）</h2>')
    for w in mw[:12]:
        P.append('<details><summary>%s　%s</summary>' % (E(w.get("worksheet_id")), E(w.get("topic"))))
        if w.get("system_reason"):
            P.append('<p class="muted">为何须人工：%s</p>' % E(w["system_reason"]))
        if w.get("objective"):
            P.append("<p><strong>目标：</strong>%s</p>" % E(w["objective"]))
        if w.get("steps"):
            P.append("<ul>%s</ul>" % "".join("<li>%s</li>" % tr(s, 300) for s in w["steps"][:8]))
        P.append("</details>")
    P.append("</section>")

P.append('<div class="foot">本报告由「财税风险防控系统 AGI版」自动生成，属分析与核验工作底稿，'
         '不替代现场检查、外部调查、当事人陈述申辩、审理审签或其他法定程序。<br>'
         '行政定性权保留于人工，系统不替代有权机关作出处罚决定。<br>生成时间：%s</div>' % E(gen))
P.append("</div></body></html>")

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(P))
print("已生成:", OUT, os.path.getsize(OUT), "bytes")
