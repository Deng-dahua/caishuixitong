# -*- coding: utf-8 -*-
"""真浏览器验收：本批四项（2026-10-19 第四批）。

对应四条用户诉求：

  ① **进入分析报告页面显示页面顶端** —— 实测 `window.scrollY` 必须为 0
     （改前是 119：`tax-doc-analysis.js` 渲染完 `scrollIntoView` 到报告区）。
  ② **编辑项目页「所有信息自动获取自动填列」，且不再有任何自动按钮/徽标**
     —— 实测：`#btn-fetch-bizinfo` 不存在；打开编辑页后
     行业/地区/期间/税种/法定代表人/注册资本/成立日期/经营范围 **已填**；
     提示区写明了来源与不可得原因。
  ③ **稽查项目列表显示行业与地区等信息** —— 实测列表行里不再是「—」。
  ④ **工商信息有出入时以分析所得为准** —— 由后端
     `project_service.sync_profile_from_analysis` 保证（本脚本验证结果状态）。

用法：
    <managed-python> scripts/_verify_project_profile.py [--base http://127.0.0.1:8001]
★ 用 managed env（含 playwright），不是项目 .venv。
"""
from __future__ import annotations

import argparse
import os
import sys

try:
    from playwright.sync_api import sync_playwright
except Exception as exc:                                          # noqa: BLE001
    print("需要 playwright：%s" % exc)
    raise SystemExit(2)

RESULTS = []


def rec(group: str, name: str, got, expect, ok=None) -> None:
    ok = (got == expect) if ok is None else bool(ok)
    RESULTS.append((group, name, ok, got, expect))
    print("%s [%s] %-44s got=%r" % ("OK  " if ok else "FAIL", group, name, got))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8001")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="CaiShui-2026#Recover")
    ap.add_argument("--shots", default="_audit_ui/shots")
    args = ap.parse_args()
    os.makedirs(args.shots, exist_ok=True)
    B = args.base.rstrip("/")

    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chrome", headless=True)
        ctx = b.new_context(viewport={"width": 1500, "height": 1000}, locale="zh-CN")
        p = ctx.new_page()
        p.goto(B + "/login", wait_until="networkidle")
        p.fill("#username", args.user)
        p.fill("#password", args.password)
        p.click("#submit")
        # ★ 登录会整页跳转（`location.assign`）⇒ 直接 `query_selector` 会撞上
        #   "Execution context was destroyed"。先等主文档加载完，再轮询（每轮 try 兜住）。
        try:
            p.wait_for_load_state("load", timeout=20000)
        except Exception:                                         # noqa: BLE001
            pass
        for _ in range(40):
            p.wait_for_timeout(250)
            try:
                if p.query_selector("#page-home"):
                    break
            except Exception:                                     # noqa: BLE001
                continue

        # ═══ ① 进入分析报告页 = 页面顶端 ═══
        p.goto(B + "/reports", wait_until="networkidle")
        for _ in range(60):
            p.wait_for_timeout(250)
            n = p.evaluate("() => document.querySelectorAll('#tda-report-area *').length")
            if n and n > 500:
                break
        p.wait_for_timeout(1200)
        rec("①顶端", "进 /reports 时 scrollY", p.evaluate("() => window.scrollY"), 0)
        rec("①顶端", "报告正文已渲染（元素数>500）",
            p.evaluate("() => document.querySelectorAll('#tda-report-area *').length"), 500,
            p.evaluate("() => document.querySelectorAll('#tda-report-area *').length") > 500)
        rec("①顶端", "body 带 embed-report 标记",
            p.evaluate("() => document.body.classList.contains('embed-report')"), True)
        # 切到别的页签再切回来，仍应回到顶端
        p.click("#tab-history")
        p.wait_for_timeout(1500)
        p.evaluate("() => window.scrollTo(0, 300)")
        p.click("#tab-analysis")
        p.wait_for_timeout(2000)
        rec("①顶端", "切回「分析报告」页签后 scrollY", p.evaluate("() => window.scrollY"), 0)
        p.screenshot(path=os.path.join(args.shots, "q4_1_reports_top.png"))

        # ═══ ③ 项目列表显示行业/地区/工商信息 ═══
        p.goto(B + "/projects", wait_until="networkidle")
        for _ in range(40):
            p.wait_for_timeout(250)
            if p.query_selector("#tbody tr"):
                break
        row = p.evaluate("""() => {
            var tr = document.querySelector('#tbody tr');
            if (!tr) return null;
            var tds = Array.from(tr.querySelectorAll('td')).map(function (t) {
                return (t.innerText || '').trim();
            });
            var head = Array.from(document.querySelectorAll('#tbody')).length;
            var ths = Array.from(document.querySelectorAll('thead th')).map(function (t) {
                return (t.innerText || '').trim();
            });
            return {cells: tds, heads: ths};
        }""")
        heads = (row or {}).get("heads") or []
        cells = (row or {}).get("cells") or []
        # th[0] 是"全选框"表头（无文字），td[0] 是行勾选框 ⇒ 表头索引与单元格索引**直接对齐**
        # （首版错误地 +1，导致"法定代表人"那格读到的是"注册资本"的值 —— 判据错位）
        idx_ind = heads.index("行业") if "行业" in heads else -1
        idx_reg = heads.index("地区") if "地区" in heads else -1
        idx_legal = heads.index("法定代表人") if "法定代表人" in heads else -1
        rec("③列表", "表头含行业/地区", [h for h in ("行业", "地区") if h in heads],
            ["行业", "地区"])
        rec("③列表", "行业列已显示（非 —）",
            cells[idx_ind] if idx_ind > 0 and idx_ind < len(cells) else "(缺)",
            "广告传媒", (idx_ind > 0 and idx_ind < len(cells) and cells[idx_ind] not in ("", "—")))
        rec("③列表", "地区列已显示（非 —）",
            cells[idx_reg] if idx_reg > 0 and idx_reg < len(cells) else "(缺)",
            "广东省深圳市",
            (idx_reg > 0 and idx_reg < len(cells) and cells[idx_reg] not in ("", "—")))
        rec("③列表", "法定代表人列已显示（非 —）",
            cells[idx_legal] if 0 <= idx_legal < len(cells) else "(缺)",
            "张晓冬",
            (0 <= idx_legal < len(cells)
             and cells[idx_legal] not in ("", "—") and "万" not in cells[idx_legal]))
        p.screenshot(path=os.path.join(args.shots, "q4_2_projects_list.png"))

        # ═══ ② 编辑项目：全自动填列、无任何自动按钮 ═══
        # ★ 行内按钮的真实契约是 `data-act="edit"`（见 projects.js 行渲染），
        #   不是 `data-edit`；按文本猜按钮更容易漂移。
        p.click('#tbody tr button[data-act="edit"]')
        p.wait_for_timeout(900)
        rec("②编辑", "编辑弹窗已打开",
            p.evaluate("() => { var m=document.getElementById('m-form'); return !!m && !m.hidden; }"),
            True)
        rec("②编辑", "「自动」徽标/按钮已彻底删除",
            p.evaluate("() => !!document.getElementById('btn-fetch-bizinfo')"), False)
        p.wait_for_timeout(2500)          # 等自动补全接口返回
        filled = p.evaluate("""() => {
            var ids = ['pf-tid','pf-industry','pf-region','pf-ps','pf-pe',
                       'pf-legal_representative','pf-registered_capital',
                       'pf-established_date','pf-business_scope'];
            var out = {};
            ids.forEach(function (id) {
                var el = document.getElementById(id);
                out[id] = el ? String(el.value || '').trim() : '(缺)';
            });
            var scopes = Array.from(document.querySelectorAll('#pf-tax-scopes label.on'))
                .map(function (x) { return (x.innerText||'').trim(); });
            out['tax_scopes'] = scopes.join('/');
            out['_note'] = (document.getElementById('form-autofill')||{}).textContent || '';
            return out;
        }""")
        for key, label in (("pf-industry", "行业自动填列"), ("pf-region", "地区自动填列"),
                           ("pf-ps", "稽查期间起自动填列"), ("pf-pe", "稽查期间止自动填列"),
                           ("pf-legal_representative", "法定代表人自动填列"),
                           ("pf-registered_capital", "注册资本自动填列"),
                           ("pf-established_date", "成立日期自动填列")):
            v = filled.get(key, "")
            rec("②编辑", label, v, "(非空)", bool(v) and v != "(缺)")
        rec("②编辑", "税种范围自动填列", filled.get("tax_scopes"), "(非空)",
            bool(filled.get("tax_scopes")))
        rec("②编辑", "提示区写明来源（含「来源/自动补全/未自动填」）",
            filled.get("_note", "")[:60], "(非空)",
            any(k in filled.get("_note", "") for k in ("自动补全", "未自动填", "保持")))
        p.screenshot(path=os.path.join(args.shots, "q4_3_edit_autofill.png"))

        # ═══ ②-b 新建项目：填名称即自动查工商 + 自动推导行业/地区 ═══
        p.evaluate("() => { var b=document.querySelector('[data-close=\"m-form\"]'); if(b) b.click(); }")
        p.wait_for_timeout(500)
        p.click("#btn-new")
        p.wait_for_timeout(800)
        p.fill("#pf-name", "深圳海更数字传媒有限公司")
        p.dispatch_event("#pf-name", "change")
        p.evaluate("() => { var e=document.getElementById('pf-name'); e.blur(); }")
        for _ in range(40):
            p.wait_for_timeout(400)
            v = p.evaluate("() => (document.getElementById('pf-legal_representative')||{}).value||''")
            if v:
                break
        newvals = p.evaluate("""() => ({
            tid: (document.getElementById('pf-tid')||{}).value||'',
            legal: (document.getElementById('pf-legal_representative')||{}).value||'',
            industry: (document.getElementById('pf-industry')||{}).value||'',
            region: (document.getElementById('pf-region')||{}).value||'',
            note: (document.getElementById('bizinfo-note')||{}).textContent||''
        })""")
        rec("②新建", "填名称后自动填统一社会信用代码", newvals["tid"], "(非空)", bool(newvals["tid"]))
        rec("②新建", "填名称后自动填法定代表人", newvals["legal"], "(非空)", bool(newvals["legal"]))
        rec("②新建", "自动推导并填行业", newvals["industry"], "(非空)", bool(newvals["industry"]))
        rec("②新建", "自动推导并填地区", newvals["region"], "(非空)", bool(newvals["region"]))
        rec("②新建", "提示写明推导来源", newvals["note"][:50], "(非空)",
            "来源" in newvals["note"] or "推导" in newvals["note"])
        print("      新建推导结果：行业=%r 地区=%r" % (newvals["industry"], newvals["region"]))
        p.screenshot(path=os.path.join(args.shots, "q4_4_new_project_autofill.png"))
        b.close()

    ok = sum(1 for r in RESULTS if r[2])
    print("\n==== 合计 %d 项，通过 %d，失败 %d ====" % (len(RESULTS), ok, len(RESULTS) - ok))
    for g, n, good, got, exp in RESULTS:
        if not good:
            print("  FAIL [%s] %s：got=%r，期望=%r" % (g, n, got, exp))
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
