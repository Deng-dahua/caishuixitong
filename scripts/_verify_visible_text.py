# -*- coding: utf-8 -*-
"""页面**可见文案**残留检查：markdown 记号 / 未渲染的 HTML 标记（真 Chrome，逐页扫）。

## 为什么需要它（而不是只靠审计闸门）
审计闸门 `check_no_markdown_leak_in_html` 只能做**静态**扫描（它不能起浏览器），
它覆盖 `static/*.html` 与 `static/js/*.js` 的字符串字面量。
但本轮实测发现：**星号还会从"后端下发的文案"漏进来**，例如
  · `engine/industry_indicators.py` 的 `note`
  · `engine/rule_version_admin.py` 的 `note`
  · `engine/consent.py` 的条款 `body`
  · `engine/report_views.py` 的视图 `desc`
这些在源码里以中文字符串出现，静态判据**无法区分"会不会渲染"**（很多是内部说明），
而**唯一可靠的判据就是"页面上到底显示了什么"** ⇒ 必须有浏览器型验收。

## 判据（两类）
  ① 可见文本里出现成对 `**`（markdown 加粗记号被原样显示）；
  ② 可见文本里出现**未渲染的 HTML 标记字面量**（`<b>` / `<strong>` 等タグ名本身），
     这常见于"该处用 `textContent`/`esc()` 渲染，却传了 HTML 标记"的场景
     （尖括号被转义或直接显示，比星号更难看）。

★ 排除 `script` / `style` 节点 —— 它们是**代码**不是**显示文本**。
  （首版把内联 `<script>` 的源码当成"可见文本"，对 `/users` 误报了 1 处。）

★ `/audit-logs` 的**历史留痕**不在本判据的修复范围（但**仍报出来**）：
  审计日志是 **append-only** 设计，早期写入的记录里若含 `**`（那是当时源码里的文案），
  事后改源码**不会**回改历史行。本脚本如实报出，但**不当成"当前代码有缺陷"** ——
  判断依据是"用一条**新**动作产生的新记录里还有没有"（本仓用 `delete_reports` 验证过：
  新记录已无 `**`）。若要连历史一起清，须走审计日志自身的治理流程（超出本脚本职责）。

用法：
    python scripts/_verify_visible_text.py [--base http://127.0.0.1:8001]
"""
from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: 逐页扫描清单（覆盖侧边栏全部独立页；新增页面应登记到此）
PAGES = [
    "/projects", "/documents", "/analysis", "/rules", "/risks", "/reports",
    "/users", "/roles", "/audit-logs", "/recycle", "/backup", "/consent",
    "/report-templates", "/rule-versions", "/legal-library", "/legal-topics",
    "/legal-materials", "/industry-indicators", "/dashboard", "/ai-assist",
    "/tax-models",
]

#: ★ 这些页面显示的是**数据库里的历史行**（而非当前源码生成的文案）。
#:   审计日志是 append-only 的：事后修好源码**不会回改历史行**，
#:   所以此处命中只作"历史留痕"提示，不判为当前代码缺陷。
#:   （源码层面的判据在 tools/audit_consistency.py::check_no_markdown_leak_in_html。）
HISTORICAL_ONLY = {"/audit-logs"}

#: 未渲染 HTML 标记的字面量（尖括号 + 常见标签名）
_RAW_TAG = re.compile(
    r"<(?:\/?)(?:b|strong|i|em|br|p|div|span|code|ul|li|table|tr|td|th)\b[^>]{0,40}>",
    re.I)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8001")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default=os.environ.get("APP_ADMIN_PASSWORD", ""),
                    help="管理员口令（缺省取环境变量 APP_ADMIN_PASSWORD；不硬编码进仓库）")
    args = ap.parse_args(argv)

    from playwright.sync_api import sync_playwright

    fails = []
    notes = []          # 历史留痕类提示（不算当前代码缺陷）
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": 1500, "height": 1000}, locale="zh-CN")
        page = ctx.new_page()
        page.goto(args.base + "/login", wait_until="networkidle")
        page.fill("#username", args.user)
        page.fill("#password", args.password)
        page.click("#submit")
        page.wait_for_timeout(4000)

        for url in PAGES:
            page.goto(args.base + url, wait_until="networkidle")
            page.wait_for_timeout(3000)
            found = page.evaluate("""() => {
                const out = {stars: [], tags: []};
                document.querySelectorAll('*').forEach(function (e) {
                    const tg = e.tagName;
                    // ★ 排除代码节点：它们不是"显示文本"
                    if (tg === 'SCRIPT' || tg === 'STYLE') { return; }
                    if (e.children.length) { return; }        // 只看叶子
                    const t = e.textContent || '';
                    if (t.indexOf('**') !== -1) {
                        out.stars.push(t.trim().slice(0, 90));
                    }
                    const m = t.match(/<(?:\\/?)(?:b|strong|i|em|br|p|div|span|code|ul|li|table|tr|td|th)\\b[^>]{0,40}>/i);
                    if (m) { out.tags.push(t.trim().slice(0, 90)); }
                });
                return out;
            }""")
            hit = bool(found["stars"] or found["tags"])
            # ★ 区分「当前代码有缺陷」与「历史数据里存着旧文本」：
            #   `/audit-logs` 显示的是 **数据库里的历史行**（append-only，事后改源码
            #   不会回改历史行）⇒ 它命中**不构成"当前代码有缺陷"的证据**，归入提示。
            #   否则这条会永久红着，把真正的回归掩盖掉（"假判据/常红判据"同样有害）。
            #   注意：这只排除"这一页的显示结果"，不排除"审计文案源码"——
            #   源码层面的判据由 tools/audit_consistency.py 的
            #   check_no_markdown_leak_in_html 负责（它扫 .html 与 .js 字面量）。
            if hit and url in HISTORICAL_ONLY:
                notes.append((url, found))
                mark = "· "
            elif hit:
                mark = "★ "
                fails.append((url, found))
            else:
                mark = "  "
            print("%s%-24s ** = %d  未渲染标记 = %d"
                  % (mark, url, len(found["stars"]), len(found["tags"])))
            for s in found["stars"][:2]:
                print("      [**] %r" % s)
            for s in found["tags"][:2]:
                print("      [tag] %r" % s)
        browser.close()

    print("\n==== 扫描 %d 页：异常 %d 页，历史留痕提示 %d 页 ===="
          % (len(PAGES), len(fails), len(notes)))
    if notes:
        print("   历史留痕（append-only 数据行，源码已修、不回改历史）：")
        for url, _f in notes:
            print("     · %s —— 判据覆盖：源码层由审计闸门负责；可另跑一次新动作验证新记录无 **" % url)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())