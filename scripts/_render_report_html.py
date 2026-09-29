# -*- coding: utf-8 -*-
"""把分析结果 JSON 渲染为可直接阅读的自包含 HTML 报告。

用法：python scripts/_render_report_html.py [结果JSON] [输出HTML]
默认读取 scripts/four_reports/company_1_api_result.json
"""
import json, os, sys, html, datetime

REPO = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(REPO)
import sys as _sys
if REPO not in _sys.path:
    _sys.path.insert(0, REPO)

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


def _ledger_table(led, threshold=16):
    """全部风险事项台账表格：自动隐藏整列为空的列；短列（最长内容<=阈值）不换行。
    与前端 tax-doc-analysis._renderResolutionLedger 的两条规则一致。"""
    rows = led.get("rows") or []
    if not rows:
        return ""
    cols = list(led.get("columns") or ["风险事项", "等级", "证据地位", "终局方向", "解除方式", "需补自证资料"])
    # 隐藏整列为空的列（用户要求：每列都要有信息，否则不显示）
    def _has_content(c):
        for r in rows:
            v = r.get(c)
            if v is not None and str(v).strip():
                return True
        return False
    cols = [c for c in cols if _has_content(c)]
    if not cols:
        return ""
    # 短列（最长内容<=阈值）不换行；长列允许换行
    def _short(c):
        mx = 0
        for r in rows:
            L = len(str(r.get(c) or ""))
            if L > mx:
                mx = L
        return mx <= threshold
    short = {c: _short(c) for c in cols}
    head = "<tr>" + "".join(
        "<th%s>%s</th>" % ((' style="white-space:nowrap"' if short[c] else ''), E(c)) for c in cols
    ) + "</tr>"
    parts = []
    for r in rows:
        tds = []
        for c in cols:
            v = r.get(c)
            if c == "证据地位":
                sv = str(v or "")
                cls = "info" if "已验原子规则" in sv else ("warn" if "域分析结论" in sv else "")
                tds.append('<td><span class="pill %s">%s</span></td>' % (cls, E(sv or "—")))
            elif c == "风险事项":
                # ★ 2026-09-29（P1-7）：聚合行在事项名下方给出**明细**（期间/批次逐条展开），
                #   折叠块在导出时由净化逻辑展开（与前端一致）。
                cell = E(v or "—")
                _det = r.get("明细") or []
                if _det:
                    sub = "".join(
                        "<tr><td>%s</td><td>%s</td><td>%s</td></tr>"
                        % (E(d.get("期间/批次") or "—"), E(d.get("等级") or "—"),
                           E(tr(d.get("解除方式") or "—", 80)))
                        for d in _det)
                    cell += ('<details style="margin-top:6px"><summary style="cursor:pointer;color:#1d4ed8;'
                             'font-size:12px">明细（%d 项）</summary>'
                             '<table style="margin-top:4px"><tr><th>期间/批次</th><th>等级</th>'
                             '<th>解除方式</th></tr>%s</table></details>' % (len(_det), sub))
                tds.append("<td>%s</td>" % cell)
            else:
                nw = ' style="white-space:nowrap"' if short[c] else ''
                tds.append("<td%s>%s</td>" % (nw, E(v or "—")))
        parts.append("<tr>" + "".join(tds) + "</tr>")
    return "<table>" + head + "".join(parts) + "</table>"


raw = json.load(open(SRC, encoding="utf-8"))
rep = raw.get("report") or {}
te = rep.get("target_entity") or {}
err = rep.get("enterprise_readable_report") or raw.get("enterprise_readable_report") or {}
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
# ★ 2026-09-29（点评整改 P2-5 / P1-11）：文书性质与个人信息保护标识必须**在封面出现**，
#   不能只在文末写一句。外部点评指出原文书易被误当作税务机关文书，且个人信息脱敏无任何标识。
P.append('<div class="docnotice" style="margin:10px 0 16px;padding:10px 14px;border:1px solid #f59e0b;'
         'background:#fffbeb;border-radius:8px;font-size:12.5px;line-height:1.75;color:#7c2d12">'
         '<div style="font-weight:700;margin-bottom:4px">文书性质声明</div>'
         '本文书由企业税务风险检查系统自动生成，是**检查工作底稿与风险提示**，'
         '不是税务机关出具的税务文书，不具备税务处理、行政处罚或强制执行效力；'
         '所列事项均为待核实事实，任何处理决定须由有权机关依法作出。</div>'.replace('**', ''))
if err.get("_pii_notice"):
    P.append('<div class="piinotice" style="margin:0 0 16px;padding:10px 14px;border:1px solid #0ea5e9;'
             'background:#f0f9ff;border-radius:8px;font-size:12.5px;line-height:1.75;color:#0c4a6e">'
             '<div style="font-weight:700;margin-bottom:4px">个人信息保护标识 · 内部资料</div>%s</div>'
             % E(err.get("_pii_notice")))
P.append('<dl class="kv">')
for label, val in (("被查单位", te.get("name")), ("统一社会信用代码", te.get("uscc")),
                   ("法定代表人", te.get("legal_person") or te.get("legal_representative")),
                   ("经营模式", te.get("biz_model")),
                   ("经营范围", tr(te.get("business_scope"), 180))):
    if val:
        P.append("<dt>%s</dt><dd>%s</dd>" % (E(label), esc_lines(val)))
P.append("<dt>资料份数</dt><dd>%s 份（%s）</dd>" % (E(rep.get("files_count")), E(dist_txt)))
P.append("</dl></div>")

# ── 决策层摘要（3 分钟版）+ 计数映射表（★ 2026-09-29 点评整改 P2-1 / P2-6）──
#   与 Web 端 `_executiveBriefHtml` 同源（同一份 `executive_brief` 数据），只呈现不改写。
_eb = err.get("executive_brief") or {}
if _eb.get("available"):
    P.append('<section><h2><span class="n">摘要</span>%s</h2>' % E(_eb.get("title") or "决策层摘要（3 分钟版）"))
    P.append('<p class="muted">结论先行 · 只讲重点 · 不改结论（只做选择与重排，数值均转引正文）</p>')
    if _eb.get("one_line"):
        P.append('<p><strong>一句话结论：</strong>%s</p>' % E(_eb["one_line"]))
    _mets = _eb.get("metrics") or []
    if _mets:
        P.append('<div style="display:flex;flex-wrap:wrap;gap:10px;margin:10px 0 14px">')
        for _m in _mets:
            P.append('<div style="min-width:150px;flex:1 1 150px;border:1px solid #e2e8f0;'
                     'border-radius:6px;padding:8px 12px;background:#f8fafc">'
                     '<div style="font-size:12px;color:#475569;margin-bottom:4px">%s</div>'
                     '<div style="font-size:14px;font-weight:700;color:#1e3a8a;word-break:break-all">%s</div>'
                     '</div>' % (E(_m.get("名称")), E(_m.get("数值"))))
        P.append('</div>')
    _top = _eb.get("top_items") or []
    if _top:
        P.append('<p><strong>最需要先处理的事项</strong></p>')
        P.append('<table><tr><th style="width:56px">项</th><th>风险事项</th>'
                 '<th style="width:88px">等级</th><th style="width:150px">潜在敞口</th>'
                 '<th>下一步（企业要做的事）</th></tr>')
        for _t in _top:
            P.append('<tr><td>第%s项</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
                     % (E(_t.get("seq")), E(_t.get("标题")), E(_t.get("等级")),
                        E(_t.get("敞口")), E(_t.get("企业要做的事"))))
        P.append('</table>')
    _cm = _eb.get("counts_map") or []
    if _cm:
        P.append('<p><strong>计数映射表（每个数字是什么口径、彼此什么关系）</strong></p>')
        P.append('<table><tr><th style="width:190px">口径</th><th style="width:110px">数值</th>'
                 '<th>来源</th><th>与其他数字的关系</th></tr>')
        for _r in _cm:
            P.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
                     % (E(_r.get("口径")), E(_r.get("数值")), E(_r.get("来源")), E(_r.get("关系"))))
        P.append('</table>')
    _acts = _eb.get("actions") or []
    if _acts:
        P.append('<p><strong>下一步动作</strong></p><ul>')
        for _a in _acts:
            P.append('<li>%s</li>' % E(_a))
        P.append('</ul>')
    _bnd = _eb.get("boundary") or []
    if _bnd:
        P.append('<div style="font-size:12.5px;color:#7c2d12;background:#fffbeb;'
                 'border:1px solid #f59e0b;border-radius:6px;padding:8px 12px;line-height:1.9">')
        for _b in _bnd:
            P.append('<div>· %s</div>' % E(_b))
        P.append('</div>')
    if _eb.get("note"):
        P.append('<p class="muted">%s</p>' % E(_eb["note"]))
    P.append('</section>')

# ── 检查情况总述的**增量节**：关键口径对照（八）/ 时效与滞纳金提示（九）──
# ★ 2026-09-29：此处**只渲染 inspection_overview 的八、九两节**，不整章渲染。
#   原因：用户 2026-09-27 已定「检查情况总述与总体结论」章**只渲染 overall_conclusion**
#   （避免同一事实两段并排重复），该决定由 `check_report_structure` 闸门锁定。
#   但八、九两节是 overall_conclusion 里**没有**的口径索引与时效提示，
#   此前离线导出完全缺失（Web 正常）→ 属渲染器覆盖面缺口，故以"只补增量"的方式修复。
_iv = err.get("inspection_overview") or {}
# 只取八、九两节（`_IV_SECTIONS` 为闸门识别的"已过滤"标记，勿改名）
_IV_SECTIONS = ("八、", "九、")
_ivp = [_t for _t in (_iv.get("paragraphs") or []) if str(_t).startswith(_IV_SECTIONS)]
if _ivp:
    P.append('<section><h2><span class="n">附录</span>关键口径对照与时效提示</h2>')
    for _t in _ivp:
        P.append("<p>%s</p>" % E(_t))
    P.append('</section>')

# ── 一、检查情况总述与总体结论（单章：由 overall_conclusion 统一生成，每件事只说一遍）──
P.append('<section><h2><span class="n">一</span>本轮检查情况总述与总体结论</h2>')
lvl = rep.get("overall_level") or "未形成风险事项"
_lv = "ok" if ("未形成" in str(lvl) or "无" in str(lvl)) else ("danger" if rep.get("high_risk") else "warn")
P.append('<p><span class="pill %s">%s</span>'
         '<span class="pill info">共 %s 项</span>'
         '<span class="pill info">高 %s / 中 %s / 低 %s</span></p>'
         % (_lv, E(lvl), E(rep.get("total_risks")), E(rep.get("high_risk")),
            E(rep.get("mid_risk")), E(rep.get("low_risk"))))
# ★ 2026-09-27：单章只渲染从 findings 实测派生的「总体结论」（已吸收原检查情况总述的
#   定调句 / 纳税遵从看法 / 监管态度 / 边界声明），不再并排贴两段。
#   有 overall_conclusion 用它；否则回退 summary_text（兼容旧缓存）。
_oc = err.get("overall_conclusion") or {}
_ocp = _oc.get("paragraphs") or []
if _ocp:
    for _t in _ocp:
        P.append("<p>%s</p>" % E(_t))
elif rep.get("summary_text"):
    P.append("<p>%s</p>" % esc_lines(rep["summary_text"]))
P.append("</section>")

# ── 二、主体与资料 ──
P.append('<section><h2><span class="n">二</span>主体一致性</h2>')
if sc.get("mismatched_count"):
    P.append('<div class="note"><strong>已剔除 %s 份主体与账套不一致的资料</strong>（未参与任何结论）：<br>%s</div>'
             % (E(sc["mismatched_count"]),
                "<br>".join("· " + E(m.get("file")) + "　" + E(m.get("reason")) for m in (sc.get("mismatched") or [])[:10])))
else:
    _subj = sc.get("account_subject") or te.get("name") or ""
    if _subj:
        P.append('<p><span class="pill ok">主体一致</span>本账套「%s」的资料主体校验通过。</p>' % E(_subj))
    else:
        P.append('<p><span class="pill ok">主体一致</span>已上传资料的归属主体校验通过（主体名称未提供）。</p>')
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

def _cost_recon_block(crd):
    """主营业务成本两口径勾稽明细（阈值内也照出，合规留痕；含逐张/逐笔清单）。"""
    if not isinstance(crd, dict) or not crd.get("available"):
        return ""
    out = ['<h3>主营业务成本两口径勾稽明细</h3>']
    for _p in (crd.get("paragraphs") or []):
        out.append("<p>%s</p>" % E(_p))
    _g = crd.get("by_goods") or []
    if _g:
        out.append('<p class="muted">① 发票类目口径构成（按品名/类目，逐类小计）</p>')
        out.append("<table><tr><th>品名/类目</th><th>张数</th><th>金额(元)</th></tr>")
        for _r in _g[:30]:
            out.append("<tr><td>%s</td><td>%s</td><td>%s</td></tr>"
                       % (E(tr(_r.get("goods"), 60)), E(_r.get("count")),
                          E("{:,.2f}".format(float(_r.get("amount") or 0)))))
        out.append("<tr><td><strong>合计</strong></td><td><strong>%s</strong></td>"
                   "<td><strong>%s</strong></td></tr>"
                   % (E(crd.get("invoice_count") or 0),
                      E("{:,.2f}".format(float(crd.get("invoice_total") or 0)))))
        out.append("</table>")
    _ir = crd.get("invoice_rows") or []
    if _ir:
        out.append('<p class="muted">① 附：主营业务成本类发票逐张清单（%d 张）</p>' % len(_ir))
        out.append("<table><tr><th>发票号码</th><th>开票日期</th><th>销售方</th><th>品名</th>"
                   "<th>金额(元)</th><th>税额(元)</th></tr>")
        for _r in _ir[:500]:
            out.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                       % (E(_r.get("inv_no")), E(_r.get("date")), E(tr(_r.get("seller"), 40)),
                          E(tr(_r.get("goods"), 60)),
                          E("{:,.2f}".format(float(_r.get("amount") or 0))),
                          E("{:,.2f}".format(float(_r.get("tax") or 0)))))
        out.append("</table>")
    _v = crd.get("by_voucher") or []
    if _v:
        out.append('<p class="muted">② 账面口径构成（序时账 6401 本期借方发生额，按凭证号归集）</p>')
        out.append("<table><tr><th>凭证号</th><th>摘要</th><th>金额(元)</th></tr>")
        for _r in _v[:60]:
            out.append("<tr><td>%s</td><td>%s</td><td>%s</td></tr>"
                       % (E(_r.get("voucher_no")), E(tr(_r.get("summary"), 40)),
                          E("{:,.2f}".format(float(_r.get("amount") or 0)))))
        out.append("<tr><td><strong>合计</strong></td><td></td>"
                   "<td><strong>%s</strong></td></tr>"
                   % E("{:,.2f}".format(float(crd.get("book_total") or 0))))
        out.append("</table>")
    _br = crd.get("book_rows") or []
    if _br:
        out.append('<p class="muted">② 附：主营业务成本账面凭证逐笔清单（%d 笔）</p>' % len(_br))
        out.append("<table><tr><th>月份</th><th>凭证号</th><th>摘要</th><th>借方金额(元)</th></tr>")
        for _r in _br[:1000]:
            out.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                       % (E(_r.get("month")), E(_r.get("voucher_no")), E(tr(_r.get("summary"), 40)),
                          E("{:,.2f}".format(float(_r.get("amount") or 0)))))
        out.append("</table>")
    return "".join(out)


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
    P.append('<p class="muted">本台账依据本轮上传资料，逐条列示经分析查出的全部风险事项'
             '（共 %s 项）。证据地位仅表示结论的取得方式（即可信度来源），不代表风险本身的大小。</p>'
             % E(_led.get("total") or len(_led_rows)))
    P.append(_ledger_table(_led))
    if _led.get("excluded_internal_note"):
        P.append('<p class="muted">%s</p>' % E(_led["excluded_internal_note"]))
    if _led.get("evidence_tier_note"):
        P.append('<p class="muted">%s</p>' % E(_led["evidence_tier_note"]))
    # ★ 2026-09-27：主营业务成本两口径勾稽明细（阈值内也照出，合规留痕）
    P.append(_cost_recon_block(err.get("cost_recon_detail") or {}))
    P.append("</section>")

# ── 五、待核事实与发现 ──
P.append('<section><h2><span class="n">五</span>待核事实与发现</h2>')
# ★ 2026-09-27（P2）：章首主线研判（最可能的 2–3 个方向，结论先行）
_ma = err.get("main_assessment") or {}
if _ma.get("available") and _ma.get("paragraph"):
    P.append('<div class="note">%s</div>' % E(_ma["paragraph"]))
# ★ 2026-09-27（P1）：本轮潜在税额敞口汇总（测算）
_ts = err.get("tax_impact_summary") or {}
if _ts.get("total_items"):
    _bt = "；".join("%s %s 元" % (E(x.get("tax")), E("{:,.2f}".format(float(x.get("amount") or 0))))
                    for x in (_ts.get("by_tax") or []))
    P.append('<div class="note"><strong>本轮潜在税额敞口（测算）</strong>：%s<br>已量化 %s / %s 项。%s</div>'
             % ((E("合计约 {:,.2f} 元（{}）".format(float(_ts.get("total") or 0), _bt))
                 if _ts.get("total") else E("暂无可量化金额")),
                E(_ts.get("quantified") or 0), E(_ts.get("total_items") or 0),
                E(_ts.get("note") or "")))
if findings:
    lv_order = {"极高风险": 0, "高风险": 1, "中风险": 2, "低风险": 3}
    for f in sorted(findings, key=lambda x: lv_order.get(str(x.get("level")), 9))[:60]:
        P.append('<div class="card"><div class="t">【%s】%s</div>'
                 % (E(f.get("level") or "未分级"), E(f.get("type") or "")))
        for lab, key in (("事实", "detail"), ("描述", "description"), ("依据", "policy_ref"),
                         ("发现方式", "how_found"), ("解除方式", "resolve_steps")):
            v = f.get(key)
            if isinstance(v, list):
                v = "；".join(str(x) for x in v)
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

# ══════════════════════════════════════════════════════════════════════════
# 金字塔原理编辑版（2026-09-26）：对工作底稿版的只读结构化重组离线渲染。
# 仅当企业报告载荷含 pyramid_edition 时产出第二份 HTML（不改写基线那份）。
# ══════════════════════════════════════════════════════════════════════════
_pe = err.get("pyramid_edition") or {}
if not _pe:
    # 离线样本若未含派生结构，则现场只读重算（不改写输入），保证两种版式都可离线导出。
    try:
        from engine.pyramid_edition import build_pyramid_edition
        _pe = build_pyramid_edition(err) or {}
    except Exception:
        _pe = {}
if _pe and _pe.get("groups"):
    _co2 = E(te.get("name") or "未知主体")
    _id2 = err.get("identity") or {}
    _scqa = _pe.get("scqa") or {}
    _Q = []
    _Q.append('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
              '<meta name="viewport" content="width=device-width,initial-scale=1">'
              '<title>金字塔原理编辑版 - ' + _co2 + '</title>'
              '<style>' + P[0].split("<style>", 1)[-1].split("</style>")[0] +
              '</style></head><body><div class="wrap">')
    _Q.append('<div class="cover"><h1>涉税风险检查工作报告</h1><div class="sub">'
              '（金字塔原理编辑版 · 同一检查结论的结构化重组）<br>'
              '被检查企业：' + E(_id2.get("subject_name") or "未填写") + '<br>'
              '统一社会信用代码：' + E(_id2.get("taxpayer_id") or "未填写") + '<br>'
              '检查期间：' + E(_id2.get("period") or "以本轮资料记载期间为准") + '<br>'
              '检查轮次：第' + E(_id2.get("analysis_round") or 1) + '轮<br>生成时间：' + E(gen) + '</div>')
    # ★ 2026-09-29（P2-5 / P1-11）：两份编辑版都必须在封面出现文书性质与个人信息标识
    _Q.append('<div style="margin:10px 0 16px;padding:10px 14px;border:1px solid #f59e0b;'
              'background:#fffbeb;border-radius:8px;font-size:12.5px;line-height:1.75;color:#7c2d12">'
              '<div style="font-weight:700;margin-bottom:4px">文书性质声明</div>'
              '本文书由企业税务风险检查系统自动生成，是检查工作底稿与风险提示，'
              '不是税务机关出具的税务文书，不具备税务处理、行政处罚或强制执行效力。</div>')
    if err.get("_pii_notice"):
        _Q.append('<div style="margin:0 0 16px;padding:10px 14px;border:1px solid #0ea5e9;'
                  'background:#f0f9ff;border-radius:8px;font-size:12.5px;line-height:1.75;color:#0c4a6e">'
                  '<div style="font-weight:700;margin-bottom:4px">个人信息保护标识 · 内部资料</div>%s</div>'
                  % E(err.get("_pii_notice")))
    _Q.append('</div>')          # 关闭封面 div（标识块嵌在封面内，随封面成一个区块）
    # SCQA
    _Q.append('<section><h2>开篇：结论先行（SCQA）</h2>'
              '<p><strong>情境（S）：</strong>' + E(_scqa.get("situation") or "") + '</p>'
              '<p><strong>冲突（C）：</strong>' + E(_scqa.get("complication") or "") + '</p>'
              '<p><strong>问题（Q）：</strong>' + E(_scqa.get("question") or "") + '</p>'
              '<p><strong>回答（A · 本轮核心结论）：</strong>' + E(_scqa.get("answer") or "") + '</p></section>')
    # 分组
    _Q.append('<section><h2>一、风险分组结论（按维度 MECE 分组）</h2>')
    _prob_by_seq = {str(p.get("seq")): p for p in (err.get("confirmed_problems") or [])}
    for gi, g in enumerate(_pe.get("groups") or []):
        _Q.append('<h3>%d、%s（最高等级：%s）</h3>' % (gi + 1, E(g.get("dimension")), E(g.get("max_level") or "")))
        _Q.append('<p style="background:#f8fafc;border-left:3px solid #2563eb;padding:8px 12px">%s</p>'
                  % E(g.get("umbrella") or ""))
        _Q.append("<ul>")
        for s in (g.get("seqs") or []):
            p = _prob_by_seq.get(str(s)) or {}
            _title = (_pe.get("action_titles") or {}).get(str(s)) or p.get("title") or ("第%s项" % s)
            _sus = tr(p.get("suspect"), 120)
            _Q.append("<li><strong>【%s】%s</strong>%s</li>"
                      % (E(p.get("risk_level") or "未分级"), E(_title),
                         (" — " + _sus) if _sus else ""))
        _Q.append("</ul>")
    _Q.append("</section>")
    # 台账基座
    _led = err.get("resolution_ledger") or {}
    if _led.get("rows"):
        _Q.append('<section><h2>二、全部风险事项台账与解除/自证清单（基座）</h2>'
                  '<p>本台账依据本轮上传资料，逐条列示经分析查出的全部风险事项（共 %s 项），'
                  '证据地位仅表示结论的取得方式（即可信度来源），不代表风险本身的大小。</p>'
                  % E(_led.get("total") or len(_led.get("rows") or [])))
        _Q.append(_ledger_table(_led))
        _Q.append("</section>")
    _Q.append('<div class="foot">本「金字塔原理编辑版」与「税务稽查专家工作底稿版」基于同一份检查结论生成，'
              '分组与排序仅改变呈现方式，未增删任何风险事项，也未改变金额、结论、判定与等级。</div>')
    _Q.append("</div></body></html>")
    _OUT2 = OUT.replace(".html", "_pyramid.html")
    with open(_OUT2, "w", encoding="utf-8") as f:
        f.write("\n".join(_Q))
    print("已生成(金字塔版):", _OUT2, os.path.getsize(_OUT2), "bytes")
