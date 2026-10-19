# -*- coding: utf-8 -*-
"""落点三条需求的结果级验收（真 Chrome、真登录、真点击、真刷新）。

判据取向（项目铁律）：**不断言"我改了 HTML/JS"，只断言"页面上看到什么、
点了会发生什么、刷新后停在哪"**。

对应三条需求：
  ① 登录后 → 直接看到「首页总览」（`#page-home` 可见且四块 KPI 已渲染）
  ② 任意内页点「返回主界面」→ 也看到「首页总览」
  ③ 内页刷新（F5）→ 仍停在该内页

另加两条负向判据（防"看起来对、其实假"）：
  · 落地首页总览后，地址栏的 `?page=` 必须**已被抹掉**（一次性信号），
    否则 F5 会被永久钉在首页，需求③形同虚设；
  · 首页总览不得与内页**同时可见**（容器 id 规则）。

用法：
    python scripts/_verify_home_landing.py
        [--base http://127.0.0.1:8001] [--user admin] [--password '...']
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
        print("%s [%s] %-52s got=%r" % ("OK " if ok else "FAIL", task, name, got))

    def visible_pages(page):
        """当前可见的内页容器 id 列表（读真实可见性，不读属性）。"""
        return page.evaluate(
            """() => Array.from(document.querySelectorAll('#content-area > [id^="page-"]'))
                 .filter(e => e.offsetParent !== null || e.getClientRects().length > 0)
                 .map(e => e.id)""")

    def query(page):
        """地址栏真实 `location.search`。

        ★ 必须读 `window.location.search`，**不能读 playwright 的 `page.url`**：
          `page.url` 在 `history.replaceState` 之后有缓存延迟（实测返回旧值），
          用它断言"参数已抹掉"会得到假结论（本轮验收脚本自己踩到）。
        """
        try:
            return page.evaluate("() => window.location.search")
        except Exception:
            return "(读取失败)"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": 1500, "height": 1000}, locale="zh-CN")
        page = ctx.new_page()
        page.on("console", lambda m: errs.append(("console", m.text)) if m.type == "error" else None)
        page.on("pageerror", lambda e: errs.append(("pageerror", str(e))))
        page.on("dialog", lambda d: d.accept())

        # ═══ ① 登录后 → 首页总览 ═══
        page.goto(args.base + "/login", wait_until="networkidle")
        page.fill("#username", args.user)
        page.fill("#password", args.password)
        page.click("#submit")
        # 轮询等待落地（不用固定 sleep：慢机器会假红）
        landed = False
        for _ in range(60):
            try:
                page.wait_for_timeout(250)
                if page.query_selector("#page-home"):
                    if "page-home" in visible_pages(page):
                        landed = True
                        break
            except Exception:
                pass
        rec("①-登录", "登录后可见页为首页总览", visible_pages(page), ["page-home"], landed)
        rec("①-登录", "URL 已抹掉一次性参数（`page=` 不在 search 里）",
            "page=" in query(page), False)
        # 四块 KPI 必须已渲染（不是空的 "—" 占位骨架都不算通过，但只要有值/控件即可）
        kpi_ok = page.evaluate("""() => {
            var ids = ['home-kpi-pending','home-kpi-overdue','home-kpi-docs','home-kpi-job'];
            return ids.every(function(i){ var e = document.getElementById(i); return !!e && (e.textContent||'').trim() !== ''; });
        }""")
        rec("①-登录", "四块 KPI 均有文本", kpi_ok, True)
        page.screenshot(path=os.path.join(OUT, "landing_1_login_home.png"))

        # ═══ ③ 内页刷新 → 仍停在该内页 ═══
        #   先切到「资料风险分析报告」（SPA 内页），再刷新
        page.click('.nav-item[data-page="tax-doc-analysis"]')
        page.wait_for_timeout(1200)
        before = visible_pages(page)
        rec("③-刷新", "切到内页后可见页", before, ["page-tax-doc-analysis"])
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(1500)
        after = visible_pages(page)
        rec("③-刷新", "F5 后仍停在该内页", after, ["page-tax-doc-analysis"])
        rec("③-刷新", "刷新后未被打回首页总览", "page-home" in after, False)

        # ═══ ② 内页点「返回主界面」→ 首页总览 ═══
        #   去一个**独立页**（/projects），点它顶栏的「返回主界面」
        page.goto(args.base + "/projects", wait_until="networkidle")
        link = page.query_selector('a:has-text("返回主界面"), a:has-text("返回首页")')
        rec("②-返回", "/projects 顶栏存在返回链接", link is not None, True)
        href = link.get_attribute("href") if link else None
        rec("②-返回", "返回链接目标", href, "/?page=home")
        if link:
            link.click()
            landed2 = False
            for _ in range(60):
                page.wait_for_timeout(250)
                try:
                    if "page-home" in visible_pages(page):
                        landed2 = True
                        break
                except Exception:
                    pass
            rec("②-返回", "点返回后可见页为首页总览", visible_pages(page), ["page-home"], landed2)
            rec("②-返回", "URL 已抹掉一次性参数（`page=` 不在 search 里）",
                "page=" in query(page), False)
        page.screenshot(path=os.path.join(OUT, "landing_2_back_home.png"))

        # ═══ 负向：首页总览不得与内页同时可见 ═══
        vis = visible_pages(page)
        rec("负向", "仅一个内页容器可见", len(vis), 1)

        # ═══ 负向：/index 兼容路由不再 404 ═══
        r = page.goto(args.base + "/index", wait_until="networkidle")
        rec("负向", "/index 最终可达（非 404）",
            (r.status if r else None) in (200,), True)
        rec("负向", "/index 最终落到首页总览",
            "page-home" in visible_pages(page), True)

        # ═══ 负向：无与本次改动相关的页面错误 ═══
        #   ★ 必须**分类**，不能笼统"有 console 错就红"：本页实测存在**既有噪声**
        #     （`favicon` 404、资料分析页自身的 `tda-file-list 元素不存在`），
        #     它们与本轮落点改动无关、"存在即红"会给出假结论。
        #   口径：只把**落点/路由类**错误当失败，其余如实列出但不判红。
        _RELATED = ("_resolveLandingPage", "_consumeLandingParam", "_readLandingParam",
                    "navigateTo", "lastPage", "page-home", "landing")
        related = [e for e in errs
                   if any(k in e[1] for k in _RELATED)
                   or (e[0] == "pageerror" and "favicon" not in e[1])]
        noise = [e for e in errs if e not in related]
        rec("负向", "无与本轮落点改动相关的报错", related[:3], [])
        if noise:
            print("      （既有噪声 %d 条，与本轮无关，不判红）: %s"
                  % (len(noise), noise[:2]))
        browser.close()

    failed = [r for r in res if not r["ok"]]
    print("\n==== 合计 %d 项，失败 %d 项 ====" % (len(res), len(failed)))
    if failed:
        for f in failed:
            print("  FAIL %s / %s: got=%r expect=%r" % (
                f["task"], f["check"], f["got"], f["expect"]))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())