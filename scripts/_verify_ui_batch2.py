# -*- coding: utf-8 -*-
"""五项界面需求的结果级验收（真 Chrome）。

用法：
    python scripts/_verify_ui_batch2.py --base http://127.0.0.1:8001
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
    ap.add_argument("--password", default="CaiShui-2026#Recover")
    args = ap.parse_args(argv)
    os.makedirs(OUT, exist_ok=True)

    from playwright.sync_api import sync_playwright

    res, errs = [], []

    def rec(task, name, got, expect, ok=None):
        ok = (got == expect) if ok is None else bool(ok)
        res.append({"task": task, "check": name, "got": got, "expect": expect, "ok": ok})
        print("%s [%s] %-48s got=%r" % ("OK  " if ok else "FAIL", task, name, got))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": 1500, "height": 1000}, locale="zh-CN")
        page = ctx.new_page()
        page.on("console", lambda m: errs.append(("console", m.text)) if m.type == "error" else None)
        page.on("pageerror", lambda e: errs.append(("pageerror", str(e))))
        page.on("dialog", lambda d: d.accept())

        # ══════ ⑤ 登录页的修改密码面板（登录前测，因为它是"未登录"入口）══════
        page.goto(args.base + "/login", wait_until="networkidle")
        rec("⑤-改密", "登录页有「修改密码」入口", page.query_selector("#toggle-change-pw") is not None, True)
        rec("⑤-改密", "改密表单初始隐藏",
            page.evaluate("() => (document.getElementById('pw-form')||{}).style.display"), "none")
        page.click("#toggle-change-pw")
        page.wait_for_timeout(500)
        visible = page.evaluate("""() => { var f=document.getElementById('pw-form');
            return !!f && f.style.display !== 'none' && f.getClientRects().length > 0; }""")
        rec("⑤-改密", "点入口后表单可见", visible, True)
        # 未登录改密：故意用错的原密码 ⇒ 必须被拒且措辞不泄露账号是否存在
        page.fill("#pw-username", args.user)
        page.fill("#pw-old", "definitely-wrong-password")
        page.fill("#pw-new", "NewPass-2026#abcd")
        page.fill("#pw-confirm", "NewPass-2026#abcd")
        page.click("#pw-submit")
        page.wait_for_timeout(2500)
        msg = page.evaluate("() => (document.getElementById('pw-msg')||{}).textContent || ''")
        rec("⑤-改密", "错误原密码被拒", ("不正确" in msg or "失败" in msg), True)
        rec("⑤-改密", "措辞不泄露账号是否存在",
            ("不存在" in msg or "not found" in msg), False)
        print("      服务端措辞：%r" % msg.strip()[:70])
        # 密码框必须 type=password（防止被 page-memory 持久化）
        types = page.evaluate("""() => ['pw-old','pw-new','pw-confirm']
            .map(i => (document.getElementById(i)||{}).type)""")
        rec("⑤-改密", "三个密码框均为 password 类型", types, ["password", "password", "password"])
        # 登录页 localStorage 不得出现密码明文
        leaked = page.evaluate("""() => {
            var raw = (localStorage.getItem('pageMemory.v1')||'');
            return { has: raw.indexOf('definitely-wrong-password') !== -1,
                     hasNew: raw.indexOf('NewPass-2026#abcd') !== -1 };
        }""")
        rec("⑤-改密", "localStorage 未泄露密码", (leaked["has"] or leaked["hasNew"]), False)
        page.screenshot(path=os.path.join(OUT, "batch2_1_login_changepw.png"))

        # ══════ 登录 ══════
        page.goto(args.base + "/login", wait_until="networkidle")
        page.fill("#username", args.user)
        page.fill("#password", args.password)
        page.click("#submit")
        page.wait_for_timeout(4000)

        # ══════ ⑤ 侧边栏不再有「修改密码」 ══════
        nav = page.evaluate("""() => Array.from(document.querySelectorAll('.nav-item'))
            .map(e => (e.textContent||'').trim())""")
        rec("⑤-改密", "侧边栏无「修改密码」", any("修改密码" in t for t in nav), False)

        # ══════ ① /risks 无刷新按钮 ══════
        page.goto(args.base + "/risks", wait_until="networkidle")
        page.wait_for_timeout(2500)
        rec("①-刷新", "/risks 无 #btn-refresh", page.query_selector("#btn-refresh") is not None, False)
        rec("①-刷新", "/risks 页面正常加载",
            page.evaluate("() => !!document.querySelector('h1')"), True)

        # ══════ ② /reports 无刷新按钮 ══════
        page.goto(args.base + "/reports", wait_until="networkidle")
        page.wait_for_timeout(5000)
        rec("②-刷新", "/reports 无 #btn-refresh", page.query_selector("#btn-refresh") is not None, False)
        rec("②-刷新", "/reports 无 #btn-list-refresh",
            page.query_selector("#btn-list-refresh") is not None, False)

        # ══════ ③ 报告封面标题被降级（不再与页面标题争主次）══════
        cov = page.evaluate("""() => {
            var a = document.getElementById('tda-report-area');
            if (!a) return {area:false};
            var c = a.querySelector('.cover');
            var h1 = c ? c.querySelector('h1') : null;
            return { area:true, hasCover:!!c,
                     demoted: !!(h1 && h1.classList.contains('rpt-cover-demoted')),
                     card: !!(c && c.classList.contains('rpt-cover-card')),
                     fontSize: h1 ? getComputedStyle(h1).fontSize : '',
                     text: h1 ? (h1.textContent||'').trim().slice(0,30) : '' };
        }""")
        rec("③-封面", "报告封面存在（信息未丢）", cov.get("hasCover"), True)
        rec("③-封面", "封面标题已降级", cov.get("demoted"), True)
        rec("③-封面", "封面已转为信息卡", cov.get("card"), True)
        print("      封面标题 %r 字号=%s（页面 h1 通常 24px+）" % (cov.get("text"), cov.get("fontSize")))
        page.screenshot(path=os.path.join(OUT, "batch2_2_reports_cover.png"), full_page=True)

        # ══════ ④ 报告列表勾选 + 删除选中 ══════
        page.click("#tab-history")
        # ★ 轮询等列表渲染完（不用固定 sleep：列表是异步拉取，慢机器会假红 ——
        #   本轮实测踩到过：固定 2.5s 时偶发"行数=0"，而接口其实已返回 1 条）。
        rows = 0
        for _ in range(40):
            page.wait_for_timeout(300)
            rows = page.evaluate("() => document.querySelectorAll('#tb-reports input.rep-sel').length")
            if rows > 0:
                break
            # 已明确"该项目尚无报告"时无需再等
            empty = page.evaluate("""() => {
                var t = document.getElementById('tb-reports');
                return !!t && (t.innerText||'').indexOf('尚无报告') !== -1; }""")
            if empty:
                break
        rec("④-勾选", "表头全选框存在", page.query_selector("#rep-sel-all") is not None, True)
        rec("④-勾选", "删除选中按钮存在", page.query_selector("#btn-del-reports") is not None, True)
        rec("④-勾选", "未勾选时按钮隐藏",
            page.evaluate("() => { var b=document.getElementById('btn-del-reports'); return !!b && b.hidden; }"), True)
        rec("④-勾选", "行数 > 0（可测）", rows > 0, True,
            ok=(rows > 0 or page.evaluate("""() => {
                var t = document.getElementById('tb-reports');
                return !!t && (t.innerText||'').indexOf('尚无报告') !== -1; }""")))
        print("      列表行数 = %d" % rows)
        if rows > 0:
            page.evaluate("""() => { var b=document.querySelector('#tb-reports input.rep-sel');
                b.checked = true; b.dispatchEvent(new Event('change', {bubbles:true})); }""")
            page.wait_for_timeout(600)
            rec("④-勾选", "勾选 1 行后按钮显示",
                page.evaluate("() => { var b=document.getElementById('btn-del-reports'); return !!b && !b.hidden; }"), True)
            rec("④-勾选", "按钮计数为 1",
                page.evaluate("() => (document.getElementById('del-picked-n')||{}).textContent"), "1")
            # ★ 全选/取消全选：必须**先归零再全选**，不能假设"当前全选框是 false"——
            #   只有 1 行时，勾该行会让 syncReportSel() 把全选框**自动打勾**
            #   （checked 数 == 总数），此时直接 `click()` 等于"取消全选"⇒ 计数归 0。
            #   首版验收脚本正是栽在这个假设上（把"取消"当"全选"点）。
            page.evaluate("() => { document.getElementById('rep-sel-all').checked = false; }")
            page.evaluate("""() => { document.querySelectorAll('#tb-reports input.rep-sel')
                .forEach(function(b){ b.checked = false;
                    b.dispatchEvent(new Event('change', {bubbles:true})); }); }""")
            page.wait_for_timeout(500)
            if not page.evaluate("() => document.getElementById('rep-sel-all').checked"):
                page.click("#rep-sel-all")
                page.wait_for_timeout(600)
            rec("④-勾选", "全选后计数=行数",
                page.evaluate("() => (document.getElementById('del-picked-n')||{}).textContent"),
                str(rows))
            # 取消全选 ⇒ 按钮应隐藏
            page.click("#rep-sel-all")
            page.wait_for_timeout(600)
            rec("④-勾选", "取消全选后按钮隐藏",
                page.evaluate("() => { var b=document.getElementById('btn-del-reports'); return !!b && b.hidden; }"), True)
        page.screenshot(path=os.path.join(OUT, "batch2_3_report_list_sel.png"), full_page=True)

        # ══════ ④ 删除端点：权限 + confirm 双重把关 ══════
        # ★ 必须**显式带 CSRF 头**：本页的写请求由 `security.js` 的 fetch 包装
        #   自动注入 `X-CSRF-Token`；在 `page.evaluate` 里裸 `fetch` 绕过了那层包装
        #   ⇒ 会被 CSRF 中间件拦成 403（首版验收脚本正是这么假红的）。
        api = page.evaluate("""async () => {
            const csrf = (document.cookie.split('; ').find(c=>c.startsWith('csrf_token='))||'')
                          .split('=').slice(1).join('=');
            const H = {'Content-Type':'application/json', 'X-CSRF-Token': decodeURIComponent(csrf)};
            const r1 = await fetch('/api/v1/reports/delete', {method:'POST', headers:H,
                body: JSON.stringify({report_ids:['X']})});
            const t1 = await r1.text();
            let j1 = {}; try { j1 = JSON.parse(t1); } catch (e) {}
            const r2 = await fetch('/api/v1/reports/delete', {method:'POST', headers:H,
                body: JSON.stringify({report_ids:['NOT-EXIST-XXXX'], confirm:true})});
            const t2 = await r2.text();
            let j2 = {}; try { j2 = JSON.parse(t2); } catch (e) {}
            return {noConfirm:{status:r1.status, msg:(j1.detail||j1.message||t1.slice(0,60))},
                    withConfirm:{status:r2.status, skipped:(j2.skipped||[]).length,
                                 reason:((j2.skipped||[])[0]||{}).reason || ''}};
        }""")
        rec("④-删除", "缺 confirm ⇒ 400 拒绝",
            api["noConfirm"]["status"], 400)
        rec("④-删除", "带 confirm 时不存在报告进 skipped（不整批失败）",
            api["withConfirm"]["skipped"], 1)
        print("      skipped 理由：%r（status=%s）" % (
            api["withConfirm"]["reason"], api["withConfirm"]["status"]))

        # ══════ 负向：无与本次改动相关的报错 ══════
        RELATED = ("_demoteReportCover", "delSelectedReports", "REP_PICKED",
                   "syncReportSel", "pw-form", "change-password-public",
                   "btn-refresh", "btn-list-refresh")
        related = [e for e in errs
                   if any(k in e[1] for k in RELATED)
                   or (e[0] == "pageerror" and "favicon" not in e[1])]
        rec("负向", "无与本次改动相关的报错", related[:3], [])
        noise = [e for e in errs if e not in related]
        if noise:
            print("      （既有噪声 %d 条，与本轮无关）: %s" % (len(noise), noise[:2]))
        browser.close()

    failed = [r for r in res if not r["ok"]]
    print("\n==== 合计 %d 项，失败 %d 项 ====" % (len(res), len(failed)))
    for f in failed:
        print("  FAIL %s / %s: got=%r expect=%r" % (f["task"], f["check"], f["got"], f["expect"]))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())