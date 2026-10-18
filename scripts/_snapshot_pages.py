# -*- coding: utf-8 -*-
"""GAP-A1 真实浏览器截图（2026-10-18）。

测评侧差距："本轮无浏览器截图（无 playwright、无法读图）⇒ 6.3 交互性等结论
只有 HTTP 证据"。

本脚本用 **playwright + chromium** 真开浏览器，对 5 个关键页面各出一张截图：
  ① 首页（总览）
  ② 稽查项目管理（列表 + 14 列）
  ③ 资料上传与管理
  ④ 风险工作台（风险列表）
  ⑤ 法规库

产物：`_audit_20261018/shots/*.png` + `_audit_20261018/shots/index.json`
（每张附：URL、HTTP 状态、页面标题、可见文字长度、截图字节数、耗时）。

★ 判据不止"文件存在"：
  · 每张图必须 > 10KB（空白页/纯错误页只有几 KB）；
  · 必须记录页面标题与可见文字长度（防"截了个 404 壳"）；
  · 登录失败或任一页面不可达 ⇒ 非零退出。

用法：
  python scripts/_snapshot_pages.py [--base http://127.0.0.1:8001]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_audit_20261018", "shots")

#: 要截图的页面（路径, 名称, 期望出现在页面里的字样之一）
#: ★ 路由必须与真实注册一致（`/legal` 是 404 —— 实测抓出来的；
#:   法规库页真实路径是 `legal_api` 的 `/legal-library`）。
#: 期望字样取**页面内真实存在**的文案，不写"大概应该有"的词。
PAGES = [
    ("/", "01_home", ["风险防控", "稽查"]),
    ("/projects", "02_projects", ["稽查项目管理", "企业名称"]),
    ("/documents", "03_documents", ["资料", "上传"]),
    ("/risks", "04_risks", ["风险"]),
    ("/legal-library", "05_legal", ["法规"]),
]


def _login(page, base: str, user: str, pwd: str) -> bool:
    page.goto(base + "/login", wait_until="networkidle", timeout=30000)
    page.fill("input[name='username'], #username, input[type='text']", user)
    page.fill("input[type='password'], #password", pwd)
    page.click("button[type='submit'], #login-btn, button")
    page.wait_for_timeout(2500)
    return "/login" not in page.url


def _pass_consent(page, base: str, out_dir: str) -> bool:
    """E-01 知情同意：首次登录会被引导到 `/consent`。

    ★ 这不是缺陷，是**设计**（`security_web.auth_me_handler` 的 `consent_required`）。
      截图脚本必须**如实走这一步**，并顺手把"告知页"也截一张作为合规证据；
      跳过它（例如直接改 cookie）得到的是"看起来很顺"的假截图。
    """
    if "/consent" not in page.url:
        return True
    shot = os.path.join(out_dir, "00_consent.png")
    page.screenshot(path=shot, full_page=True)
    print("✓ %-14s %s → 已截取（E-01 知情同意页）" % ("00_consent", page.url))
    # 按钮文案不是固定值 ⇒ 按语义找（勾选 + 确认/同意）
    for sel in ("input[type='checkbox']", "#consent-check", ".consent-check"):
        try:
            if page.locator(sel).count():
                page.locator(sel).first.check()
                break
        except Exception:                                     # noqa: BLE001
            continue
    # 按钮文案/交互不是固定的 ⇒ 先按**已知 id**（`static/consent.html` 的 `#btn-accept`），
    # 再按语义兜底；找不到就如实失败（不猜坐标点击）。
    # ★ 该页确认成功后**不跳转**（只就地提示并重载条款），所以判据不能看 URL 变没变，
    #   必须重新访问 `/` 看会不会**再被弹回** `/consent`（那才是"已确认"）。
    clicked = False
    for sel in ("#btn-accept", "button#accept", "button.btn"):
        try:
            if page.locator(sel).count():
                page.locator(sel).first.click()
                page.wait_for_timeout(2000)
                clicked = True
                break
        except Exception:                                     # noqa: BLE001
            continue
    if not clicked:
        for text in ("我已阅读并知悉", "我已知悉并同意", "确认", "同意并继续"):
            try:
                btn = page.get_by_role("button", name=text)
                if btn.count():
                    btn.first.click()
                    page.wait_for_timeout(2000)
                    clicked = True
                    break
            except Exception:                                 # noqa: BLE001
                continue
    page.goto(base + "/", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(1200)
    return "/consent" not in page.url


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8001")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="CaiShui-2026#Recover")
    ap.add_argument("--channel", default="chrome",
                    help="用系统已装的 chrome/msedge（playwright 自带内核版本可能未下载）")
    ap.add_argument("--headless", action="store_true", default=True)
    args = ap.parse_args(argv)

    from playwright.sync_api import sync_playwright
    os.makedirs(OUT, exist_ok=True)
    report = []

    with sync_playwright() as pw:
        # ★ 用**系统 Chrome**：① playwright 自带 chromium 版本可能未下载（实测 1248 缺失）；
        #   ② 用真实用户同款内核，截图才有代表性（headless_shell 的渲染差异会失真）。
        launch_kw = {"headless": bool(args.headless),
                     "args": ["--disable-dev-shm-usage"]}
        if args.channel:
            launch_kw["channel"] = args.channel
        browser = pw.chromium.launch(**launch_kw)
        ctx = browser.new_context(viewport={"width": 1500, "height": 1000},
                                  locale="zh-CN")
        page = ctx.new_page()
        t0 = time.time()
        if not _login(page, args.base, args.user, args.password):
            print("[FAIL] 登录失败：%s" % page.url)
            browser.close()
            return 2
        login_sec = round(time.time() - t0, 2)
        # E-01：首次登录必须过知情同意（不是缺陷，是设计）
        page.goto(args.base + "/", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1200)
        if not _pass_consent(page, args.base, OUT):
            print("[FAIL] 知情同意未通过：%s" % page.url)
            browser.close()
            return 2

        ok = True
        for path, name, expects in PAGES:
            rec = {"page": name, "path": path}
            t = time.time()
            try:
                resp = page.goto(args.base + path, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(1200)
                rec["http_status"] = resp.status if resp else None
                rec["title"] = page.title()
                text = page.inner_text("body")[:4000]
                rec["visible_text_len"] = len(text)
                shot = os.path.join(OUT, name + ".png")
                page.screenshot(path=shot, full_page=True)
                rec["bytes"] = os.path.getsize(shot) if os.path.exists(shot) else 0
                rec["missing_hints"] = [x for x in expects if x not in text]
                rec["elapsed_sec"] = round(time.time() - t, 2)
                if rec["http_status"] != 200:
                    rec["verdict"] = "HTTP %s" % rec["http_status"]
                    ok = False
                elif rec["bytes"] < 10240:
                    rec["verdict"] = "截图过小（疑空白页）"
                    ok = False
                elif rec["missing_hints"]:
                    rec["verdict"] = "页面缺预期字样：%s" % rec["missing_hints"]
                    ok = False
                else:
                    rec["verdict"] = "OK"
            except Exception as exc:                          # noqa: BLE001
                rec["verdict"] = "异常：%s" % exc
                rec["elapsed_sec"] = round(time.time() - t, 2)
                ok = False
            report.append(rec)
            print("%s %-14s %s → %s（%d B，%.1fs）"
                  % ("✓" if rec["verdict"] == "OK" else "✗", name,
                     path, rec["verdict"], rec.get("bytes") or 0,
                     rec.get("elapsed_sec") or 0))
        browser.close()

    meta = {"base": args.base, "login_sec": login_sec,
            "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "viewport": "1500x1000", "pages": report}
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    print("\n产物：%s" % OUT)
    print("结论：%s" % ("全部 OK" if ok else "存在失败项"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
