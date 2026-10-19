# -*- coding: utf-8 -*-
"""五项界面改造的**结果级验收**：真浏览器、真接口、断言 DOM 渲染结果。

判据取向（项目铁律）：**不断言"我改了 HTML/JS"，只断言"页面上看到什么、点了会发生什么"。**
每个 case 都给 `expect` 与实测值，失败即退出码 1。

用法（实例须已起在 --base，且账号可登录）：
    python scripts/_verify_ui_20261018.py --base http://127.0.0.1:8006 \
        --user uiuser --password 'Ui-Test-2026!'
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_audit_ui", "shots")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8006")
    ap.add_argument("--user", default="uiuser")
    ap.add_argument("--password", default="Ui-Test-2026!")
    args = ap.parse_args(argv)
    os.makedirs(OUT, exist_ok=True)

    from playwright.sync_api import sync_playwright

    res = []
    errs = []

    def rec(task, name, got, expect, ok=None):
        ok = (got == expect) if ok is None else bool(ok)
        res.append({"task": task, "check": name, "got": got, "expect": expect, "ok": ok})
        print("%s [%s] %-46s got=%r" % ("✓" if ok else "✗", task, name, got))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": 1500, "height": 1000}, locale="zh-CN")
        page = ctx.new_page()
        page.on("console", lambda m: errs.append(("console", m.text)) if m.type == "error" else None)
        page.on("pageerror", lambda e: errs.append(("pageerror", str(e))))
        page.on("dialog", lambda d: d.accept())      # confirm 一律同意

        # ── 登录 ──
        page.goto(args.base + "/login", wait_until="networkidle")
        page.fill("#username", args.user)
        page.fill("#password", args.password)
        page.click("#submit")
        page.wait_for_timeout(2200)
        if "/consent" in page.url:
            try:
                page.locator("#btn-accept").first.click()
                page.wait_for_timeout(1200)
            except Exception:                                     # noqa: BLE001
                pass

        # ══════════ 任务 1：项目列表勾选 + 删除选中 ══════════
        page.goto(args.base + "/projects", wait_until="networkidle")
        page.wait_for_timeout(1800)
        rec("1", "表头有全选框", page.locator("#sel-all").count(), 1)
        rec("1", "每行有勾选框", page.locator("#tbody input.proj-sel").count(),
            page.locator("#tbody tr").count())
        rec("1", "未勾选时按钮隐藏", page.locator("#btn-del-selected").is_visible(), False)
        # 勾第一行
        page.locator("#tbody input.proj-sel").first.check()
        page.wait_for_timeout(300)
        rec("1", "勾 1 行后按钮出现", page.locator("#btn-del-selected").is_visible(), True)
        rec("1", "按钮显示数量", page.locator("#btn-del-selected").inner_text(), "删除选中（1）")
        # 全选
        page.locator("#sel-all").check()
        page.wait_for_timeout(300)
        n_rows = page.locator("#tbody input.proj-sel").count()
        rec("1", "全选后按钮显示全部数量", page.locator("#btn-del-selected").inner_text(),
            "删除选中（%d）" % n_rows)
        page.screenshot(path=os.path.join(OUT, "t1_projects_checked.png"), full_page=True)
        page.locator("#sel-all").uncheck()
        page.wait_for_timeout(200)
        # ★ 先建一个**专用**项目再删它（避免把验收环境里的既有项目删掉 —— 上一版脚本
        #   就是这么把 fixture 删了的，属于验收脚本自身的破坏性缺陷）
        # ★ 名称与税号带时间戳：**同名/同税号会被后端判重而拒绝保存**，
        #   弹窗不关 ⇒ 后续点击全被遮罩拦截；而"已建"判据还会因**上次遗留的同名行**假绿
        #   （反向验证跑完后的"还原后仍红"就是这么来的，属验收脚本自身缺陷）。
        import time as _t2
        _st = _t2.strftime("%H%M%S")
        tmp_name = "批量删除验收专用%s有限公司" % _st
        rows_before = page.locator("#tbody tr").count()
        page.click("#btn-new")
        page.wait_for_timeout(600)
        page.fill("#pf-name", tmp_name)
        # ★ 税号**总长必须恰好 18**：输入框 maxlength=18 会把超出部分截掉，
        #   前缀过长会让时间戳被截成 2 位 ⇒ 跨分钟重跑撞号（实测踩过）。
        page.fill("#pf-tid", ("9144TMP%s" % _st).ljust(18, "0")[:18])
        page.fill("#pf-industry", "制造业")
        page.fill("#pf-region", "广东省深圳市")
        page.fill("#pf-ps", "2025-01-01")
        page.fill("#pf-pe", "2025-12-31")
        page.locator("#pf-tax-scopes label").first.click()
        page.click("#btn-save")
        page.wait_for_timeout(2500)
        rows_now = page.locator("#tbody tr").count()
        built = (tmp_name in page.locator("#tbody").inner_text()) and rows_now > rows_before
        rec("1", "专用项目已建（行数 +1 且名称出现）",
            (rows_before, rows_now, tmp_name in page.locator("#tbody").inner_text()),
            (rows_before, rows_before + 1, True), built)
        if not built:
            # ★ 失败必须**可见原因**，并关掉弹窗（否则遮罩会拦住后续所有点击 ⇒ 连环假红）
            err = page.locator("#form-msg").inner_text()
            print("    [debug] 建项目失败：%r" % err[:200])
            if page.locator("#m-form").is_visible():
                page.click("#m-form button[data-close]")
                page.wait_for_timeout(400)
        row = page.locator("#tbody tr", has_text=tmp_name).first
        row.locator("input.proj-sel").check()
        page.wait_for_timeout(200)
        rec("1", "按钮显示数量（勾 1 个）", page.locator("#btn-del-selected").inner_text(),
            "删除选中（1）")
        before = page.locator("#count").inner_text()
        page.locator("#btn-del-selected").click()
        page.wait_for_timeout(3000)
        after = page.locator("#count").inner_text()
        msg = page.locator("#msg").inner_text()
        rec("1", "删除后总数减少", (before, after), (before, after), before != after)
        rec("1", "结果逐条汇总（含成功数）", "删除完成" in msg, True)
        rec("1", "被删企业已不在列表", tmp_name in page.locator("#tbody").inner_text(), False)

        # ══════════ 任务 2：资料页删除「项目管理」按钮 ══════════
        page.goto(args.base + "/documents", wait_until="networkidle")
        page.wait_for_timeout(1800)
        top_links = page.locator(".topbar a").all_inner_texts()
        rec("2", "顶栏不再有「项目管理」", "项目管理" in top_links, False)
        rec("2", "顶栏保留「返回主界面」", "返回主界面" in top_links, True)

        # ══════════ 任务 3：解析能力已并入资料页 + 上传自动解析 ══════════
        # ★ 2026-10-20（用户裁定）：批量解析区块已整块删除（上传即自动解析）⇒
        #   判据随之更新为"该卡片已不存在"，**不是**删掉判据（信息量不减）。
        rec("3", "「批量解析」卡片已移除", page.locator("#btn-batch").count(), 0)
        rec("3", "有解析能力面板", page.locator("#cap-stats").count(), 1)
        cap_txt = page.locator("#cap-stats").inner_text().replace("\n", " ")
        rec("3", "能力面板已取到真实数字（含『标准字段』）", "标准字段" in cap_txt, True)
        rec("3", "上传区写明自动解析", "自动解析" in page.locator(".card").first.inner_text(), True)
        # 真的上传一个文件，看是否自动解析（不点任何「开始解析」按钮）
        # ★ 文件名与内容都带时间戳：系统有**查重**（同一 MD5 直接跳过上传），
        #   复用旧文件会命中"重复跳过"⇒ 队列里没有解析状态，判据会假红。
        import time as _t
        stamp = _t.strftime("%H%M%S")
        f = os.path.join(ROOT, "_audit_ui", "files", "upload_auto_%s.csv" % stamp)
        os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f, "w", encoding="utf-8-sig") as fh:
            fh.write("交易日期,对方户名,摘要,借方金额,贷方金额,交易余额\n"
                     "2025-02-11,东莞市恒达钢材有限公司,货款,88000.%s,0.00,726340.12\n"
                     % stamp[-3:])
        page.set_input_files("#picker", f)
        # ★ 轮询等待队列状态落定（固定 sleep 会假红：上传+解析是同步链路，耗时随环境浮动）
        q_txt = ""
        for _ in range(40):
            page.wait_for_timeout(500)
            q_txt = page.locator("#queue").inner_text()
            if ("已解析" in q_txt) or ("解析未成功" in q_txt) or ("失败" in q_txt):
                break
        print("    [debug] queue=%r" % q_txt[:200])
        rec("3", "上传队列显示自动解析结果",
            ("已解析" in q_txt) or ("解析未成功" in q_txt), True)
        rec("3", "自动解析成功", "已解析" in q_txt, True, "已解析" in q_txt)
        tbody = page.locator("#tbody").inner_text()
        rec("3", "新资料出现在清单", os.path.basename(f) in tbody, True)
        rec("3", "解析状态已是成功", "成功" in tbody, True)
        page.screenshot(path=os.path.join(OUT, "t3_documents.png"), full_page=True)

        # ── /extract 页面应已下线；侧边栏无该入口 ──
        page.goto(args.base + "/extract", wait_until="networkidle")
        body = page.inner_text("body")
        rec("3", "/extract 已不可用（不是资料解析页）", "选择资料并解析" in body, False)
        page.goto(args.base + "/", wait_until="networkidle")
        page.wait_for_timeout(1500)
        nav = page.inner_text("#sidebar") if page.locator("#sidebar").count() else page.inner_text("body")
        rec("3", "侧边栏无「资料解析与校正」", "资料解析与校正" in nav, False)

        # ══════════ 任务 4：分析任务「查看」按钮 ══════════
        page.goto(args.base + "/analysis", wait_until="networkidle")
        page.wait_for_timeout(2500)
        # 逐个项目找有任务的（下拉默认第一个，不一定有任务）
        picked = ""
        for opt in page.locator("#f-project option").all():
            val = opt.get_attribute("value")
            if not val:
                continue
            page.select_option("#f-project", val)
            page.wait_for_timeout(1600)
            if page.locator("#history a.job-view").count() > 0:
                picked = opt.inner_text()
                break
        rec("4", "找到有分析任务的项目", bool(picked), True)
        rec("4", "历史列表有「查看」链接", page.locator("#history a.job-view").count() > 0, True)
        before_id = page.locator("#cur-id").inner_text()
        before_card = page.locator("#cur-card").bounding_box()
        page.locator("#history a.job-view").first.click()
        page.wait_for_timeout(2200)
        after_id = page.locator("#cur-id").inner_text()
        rec("4", "点「查看」后当前任务被填充", (bool(before_id.strip()), bool(after_id.strip())),
            (False, True), (not before_id.strip()) and bool(after_id.strip()))
        rec("4", "被点的那一行高亮",
            page.locator("#history tr.row-active").count(), 1)
        rec("4", "无 JS 报错", [e for e in errs if e[0] == "pageerror"], [])
        page.screenshot(path=os.path.join(OUT, "t4_analysis.png"), full_page=True)

        # ══════════ 任务 5：规则库中文化 + 候选处置 ══════════
        page.goto(args.base + "/rules", wait_until="networkidle")
        page.wait_for_timeout(2500)
        layer_opts = page.locator("#f-layer option").all_inner_texts()
        english = [o for o in layer_opts
                   if o.strip() and not any("\u4e00" <= ch <= "\u9fff" for ch in o)]
        rec("5", "层下拉全部中文", english, [])
        rec("5", "层下拉含「税务红线库」", "税务红线库" in layer_opts, True)
        rec("5", "层下拉含「外部候选清单 v1.2」", "外部候选清单 v1.2" in layer_opts, True)
        # 表格首屏：严重度/版本/法规依据/入库处置
        rows = page.locator("#rule-rows tr")
        first = rows.first.inner_text()
        rec("5", "规则行不再出现英文严重度",
            [w for w in ("high", "medium", "low") if w in first.split()], [])
        page.locator("#f-disp").select_option("stale_status")
        page.click("button:has-text('搜索')")
        page.wait_for_timeout(2000)
        stale_txt = page.locator("#rule-rows").inner_text()
        rec("5", "按「清单状态过期」筛选有结果",
            page.locator("#rule-rows tr").count() > 0, True)
        rec("5", "处置列显示「清单状态过期」", "清单状态过期" in stale_txt, True)
        page.screenshot(path=os.path.join(OUT, "t5_rules_stale.png"), full_page=True)
        # 未入库候选
        page.locator("#f-disp").select_option("blocked")
        page.click("button:has-text('搜索')")
        page.wait_for_timeout(2000)
        b_txt = page.locator("#rule-rows").inner_text()
        rec("5", "「暂不能入库」筛选有结果并写明原因",
            ("暂不能入库" in b_txt) or ("缺数据源" in b_txt), True)
        # 全部候选（source=json）看版本/法规列是否仍有「未登记」
        page.locator("#f-disp").select_option("")
        page.locator("#f-source").select_option("json")
        page.click("button:has-text('搜索')")
        page.wait_for_timeout(2000)
        all_txt = page.locator("#rule-rows").inner_text()
        rec("5", "候选版本列不再是「未登记」", "未登记" in all_txt, False)
        rec("5", "候选法规依据列给出结论（已确定/待补映射/无对应规则）",
            any(k in all_txt for k in ("已确定", "待补映射", "无对应规则")), True)
        kpis = page.locator("#rule-kpis").inner_text().replace("\n", " ")
        rec("5", "KPI 显示候选处置汇总", "清单状态过期" in kpis, True)
        page.screenshot(path=os.path.join(OUT, "t5_rules_all.png"), full_page=True)

        browser.close()

    bad = [x for x in res if not x["ok"]]
    print("\n===== 汇总：%d 项检查，失败 %d 项 =====" % (len(res), len(bad)))
    for x in bad:
        print("  ✗ [任务%s] %s → got=%r" % (x["task"], x["check"], x["got"]))
    with open(os.path.join(OUT, "verify_ui.json"), "w", encoding="utf-8") as fh:
        json.dump({"checks": res, "failed": len(bad),
                   "console_errors": errs[:20]}, fh, ensure_ascii=False, indent=1)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
