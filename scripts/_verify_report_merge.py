# -*- coding: utf-8 -*-
"""两项需求的结果级验收（真 Chrome、真登录、真输入、真点页签）。

## 需求 1：工商信息**自动**添加（不手动）

判据：在「稽查项目管理」的新建项目表单里，**只填企业全称**（不点任何按钮），
输入停顿后工商字段应**自动**被填入 / 或自动给出"未查到"的可见说明。

## 需求 2：资料风险分析报告并入报告生成与导出，并删除该模块

判据四组：
  · 侧边栏**没有**「资料风险分析报告」入口；
  · `/reports` 默认页签是「分析报告」，且报告正文容器存在并**渲染出内容**；
  · 报告正文里能看到报告级元素（如"报告"字样/章节标题），证明渲染真跑了；
  · `navigateTo('tax-doc-analysis')` 深链**重定向到 `/reports`**（不落到首页）。

用法：
    python scripts/_verify_report_merge.py --base http://127.0.0.1:8001
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_audit_ui", "shots")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8001")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default=os.environ.get("APP_ADMIN_PASSWORD", ""),
                    help="管理员口令（缺省取环境变量 APP_ADMIN_PASSWORD；不硬编码进仓库）")
    args = ap.parse_args(argv)
    os.makedirs(OUT, exist_ok=True)

    from playwright.sync_api import sync_playwright

    res, errs = [], []

    def rec(task, name, got, expect, ok=None):
        ok = (got == expect) if ok is None else bool(ok)
        res.append({"task": task, "check": name, "got": got, "expect": expect, "ok": ok})
        print("%s [%s] %-50s got=%r" % ("OK  " if ok else "FAIL", task, name, got))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": 1500, "height": 1000}, locale="zh-CN")
        page = ctx.new_page()
        page.on("console", lambda m: errs.append(("console", m.text)) if m.type == "error" else None)
        page.on("pageerror", lambda e: errs.append(("pageerror", str(e))))
        page.on("dialog", lambda d: d.accept())

        # ── 登录 ──
        page.goto(args.base + "/login", wait_until="networkidle")
        page.fill("#username", args.user)
        page.fill("#password", args.password)
        page.click("#submit")
        page.wait_for_timeout(3500)

        # ══════════ 需求 2-A：侧边栏不再有该入口 ══════════
        nav = page.evaluate("""() => Array.from(document.querySelectorAll('.nav-item'))
            .map(e => (e.dataset.page || '') + '|' + (e.textContent||'').trim())""")
        rec("需求2", "侧边栏无「资料风险分析报告」入口",
            any("资料风险分析报告" in x for x in nav), False)
        rec("需求2", "侧边栏无 data-page=tax-doc-analysis",
            any(x.startswith("tax-doc-analysis|") for x in nav), False)

        # ══════════ 需求 2-B：/reports 默认页签 + 报告正文渲染 ══════════
        page.goto(args.base + "/reports", wait_until="networkidle")
        page.wait_for_timeout(5000)
        active_tab = page.evaluate("""() => {
            var t = document.querySelector('.tabs .tab.active'); return t ? t.textContent.trim() : '(无)'; }""")
        rec("需求2", "/reports 默认页签", active_tab, "分析报告")
        pane_visible = page.evaluate("""() => {
            var p = document.getElementById('pane-analysis');
            return !!p && (p.offsetParent !== null || p.getClientRects().length > 0); }""")
        rec("需求2", "分析报告面板可见", pane_visible, True)
        area_exists = page.evaluate("() => !!document.getElementById('tda-report-area')")
        rec("需求2", "报告正文容器存在", area_exists, True)
        area_text = page.evaluate(
            "() => { var a=document.getElementById('tda-report-area'); return a ? (a.innerText||'').trim() : ''; }")
        rec("需求2", "报告正文非空（已渲染）", len(area_text) > 200, True)
        rec("需求2", "正文含报告级内容", ("报告" in area_text), True)
        # 渲染器必须已就绪（未加载时会显示错误提示）
        rec("需求2", "未出现「渲染器未加载」",
            "报告渲染器未加载" in area_text, False)
        # 三层依赖是否都得手（这是 dom-utils 方案是否成立的直接证据）
        deps = page.evaluate("""() => ({
            escHtml: typeof escHtml, escapeHtml: typeof escapeHtml,
            toast: typeof toast, levelDisplayOf: typeof levelDisplayOf,
            renderTaxDocReport: typeof renderTaxDocReport })""")
        rec("需求2", "报告渲染依赖全部就绪", deps,
            {"escHtml": "function", "escapeHtml": "function", "toast": "function",
             "levelDisplayOf": "function", "renderTaxDocReport": "function"})
        # 账套接线（导出/缓存/删除报告需要）
        cid = page.evaluate("() => window.currentCompanyId")
        rec("需求2", "currentCompanyId 已接线（非 0）", bool(cid), True)
        page.screenshot(path=os.path.join(OUT, "merge_1_reports_analysis_tab.png"), full_page=True)

        # ══════════ 需求 2-C：页签可切换（并入后原功能仍在） ══════════
        page.click('#tab-history'); page.wait_for_timeout(1500)
        hist_visible = page.evaluate("""() => {
            var p = document.getElementById('pane-history');
            return !!p && (p.offsetParent !== null || p.getClientRects().length > 0); }""")
        rec("需求2", "「报告列表」页签仍可用", hist_visible, True)
        page.click('#tab-analysis'); page.wait_for_timeout(1200)
        back = page.evaluate("""() => {
            var p = document.getElementById('pane-analysis');
            return !!p && (p.offsetParent !== null || p.getClientRects().length > 0); }""")
        rec("需求2", "切回「分析报告」正常", back, True)

        # ══════════ 需求 2-D：深链重定向 ══════════
        page.goto(args.base + "/", wait_until="networkidle")
        page.wait_for_timeout(2500)
        page.evaluate("() => navigateTo('tax-doc-analysis')")
        page.wait_for_timeout(3000)
        rec("需求2", "深链 navigateTo('tax-doc-analysis') 落到 /reports",
            "/reports" in page.url, True)

        # ══════════ 需求 1：工商信息自动查填 ══════════
        page.goto(args.base + "/projects", wait_until="networkidle")
        page.wait_for_timeout(2500)
        # 打开新建项目表单
        page.click("#btn-new")
        page.wait_for_timeout(1200)
        # 状态指示器存在且**不是按钮**
        tag = page.evaluate("""() => {
            var e = document.getElementById('btn-fetch-bizinfo');
            return e ? e.tagName.toLowerCase() + '|' + (e.getAttribute('role')||'') : '(缺)'; }""")
        rec("需求1", "查填入口不是按钮（role=status）", tag, "span|status")
        # 清空工商字段，确保"自动填入"可观测（若原本就有值，无法判断是自动填的还是残留）
        page.evaluate("""() => {
            ['tid','legal_representative','registered_address','company_type',
             'registration_status','business_scope'].forEach(function(k){
                var e = document.getElementById('pf-'+k); if (e) e.value = '';
            });
        }""")
        # ★ 只填企业全称，不点任何按钮
        page.fill("#pf-name", "深圳海更数字传媒有限公司")
        # 等自动触发（防抖 700ms + 查询）
        filled = None
        for _ in range(40):
            page.wait_for_timeout(400)
            filled = page.evaluate("""() => {
                var out = {};
                ['tid','legal_representative','registered_address','company_type',
                 'registration_status','business_scope','registered_capital','established_date']
                  .forEach(function(k){ var e=document.getElementById('pf-'+k); out[k] = e ? (e.value||'') : null; });
                var st = document.getElementById('btn-fetch-bizinfo');
                out._state = st ? (st.getAttribute('data-state')||'') : '';
                out._note = (document.getElementById('bizinfo-note')||{}).textContent || '';
                return out; }""")
            if filled and (filled.get("tid") or filled.get("_state") in ("ok", "none")):
                break
        got_filled = [k for k, v in (filled or {}).items()
                      if not k.startswith("_") and v]
        rec("需求1", "未点按钮即自动填入工商字段", bool(got_filled), True)
        rec("需求1", "统一社会信用代码自动填入",
            bool((filled or {}).get("tid")), True)
        rec("需求1", "状态指示器已更新", (filled or {}).get("_state"), "ok")
        print("      填入的字段：%s" % got_filled)
        print("      状态文案：%r" % (filled or {}).get("_note", "")[:90])
        page.screenshot(path=os.path.join(OUT, "merge_2_biz_auto_fill.png"))

        # ══════════ 无与本次改动相关的报错 ══════════
        RELATED = ("dom-utils", "renderTaxDoc", "currentCompanyId", "scheduleBizAuto",
                   "fetchBizInfo", "reports.js", "escHtml", "toast is not",
                   "tda-report-area")
        related = [e for e in errs
                   if any(k in e[1] for k in RELATED)
                   or (e[0] == "pageerror" and "favicon" not in e[1])]
        rec("负向", "无与本次改动相关的报错", related[:3], [])
        noise = [e for e in errs if e not in related]
        if noise:
            print("      （既有噪声 %d 条，与本轮无关，不判红）: %s" % (len(noise), noise[:2]))
        browser.close()

    failed = [r for r in res if not r["ok"]]
    print("\n==== 合计 %d 项，失败 %d 项 ====" % (len(res), len(failed)))
    for f in failed:
        print("  FAIL %s / %s: got=%r expect=%r" % (f["task"], f["check"], f["got"], f["expect"]))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())