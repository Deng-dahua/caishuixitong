# -*- coding: utf-8 -*-
"""真 Chrome 验收：新建项目弹窗**只是工商登记信息**，且只有企业名称可填。

判据全部落在**用户能看见/能操作**的层面（不是"我改了这个文件"）：
  ① 点「＋ 新建项目」后，弹窗标题 = 新建项目；
  ② 可见的分区标题只有「企业工商登记信息」，**没有**「稽查要素」；
  ③ 稽查要素容器 `#sect-audit` 在新建态**实际不可见**（不是仅 hidden 属性写了但被 CSS 顶掉）；
  ④ 除企业名称外，其余工商字段**只读**（disabled），用户点不进去改；
  ⑤ 企业名称可编辑，且是唯一必填（标签上有 *）；
  ⑥ 页面提示写明"点保存时自动加载"。

★ 不创建任何项目（不改真实数据），只验表单形态；保存链路由
  `scripts/_verify_new_project_name_only.py`（含 Node 桩真跑 + 后端 temp 库）覆盖。

用法：
  <managed python> scripts/_verify_new_project_browser.py --password '<管理员口令>'
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8001")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default=os.environ.get("APP_ADMIN_PASSWORD", ""))
    a = ap.parse_args(argv)
    if not a.password:
        print("缺少口令：--password 或环境变量 APP_ADMIN_PASSWORD")
        return 2

    from playwright.sync_api import sync_playwright

    fails = []
    oks = []

    def check(name, cond, extra=""):
        (oks if cond else fails).append(name + (("  ‹%s›" % extra) if extra and not cond else ""))
        print(("  ✅ " if cond else "  ❌ ") + name + (("  → " + extra) if extra and not cond else ""))

    with sync_playwright() as pw:
        br = pw.chromium.launch(channel="chrome", headless=True)
        ctx = br.new_context(viewport={"width": 1500, "height": 1000}, locale="zh-CN")
        page = ctx.new_page()
        page.goto(a.base + "/login", wait_until="networkidle")
        page.fill("#username", a.user)
        page.fill("#password", a.password)
        page.click("#submit")
        page.wait_for_timeout(3500)

        # 进项目页（SPA 内页；直接访问深链，落点逻辑会自动留在该页）
        page.goto(a.base + "/projects", wait_until="networkidle")
        page.wait_for_timeout(2500)

        btn = page.query_selector("#btn-new")
        check("项目页有「＋ 新建项目」按钮", btn is not None)
        if btn is None:
            br.close()
            print("\n无法继续：按钮不存在")
            return 1
        btn.click()
        page.wait_for_timeout(900)

        # ① 弹窗打开且标题正确
        vis = page.evaluate("""() => {
            const m = document.getElementById('m-form');
            if (!m) return null;
            const cs = getComputedStyle(m);
            return {shown: !m.hidden && cs.display !== 'none',
                    title: (document.getElementById('form-title')||{}).textContent || ''};
        }""")
        check("点按钮后弹窗打开", bool(vis and vis["shown"]), str(vis))
        check("弹窗标题 = 新建项目", bool(vis and vis["title"].strip() == "新建项目"),
              str(vis and vis["title"]))

        # ② 可见分区标题只有工商登记信息
        sects = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('#m-form .sect')).map(function(e){
                const cs = getComputedStyle(e);
                const box = e.getBoundingClientRect();
                return {text: (e.textContent||'').trim(),
                        visible: cs.display !== 'none' && cs.visibility !== 'hidden'
                                 && box.width > 0 && box.height > 0};
            });
        }""")
        vis_sects = [s["text"] for s in sects if s["visible"]]
        check("可见分区只有 1 个", len(vis_sects) == 1, str(vis_sects))
        check("该分区是企业工商登记信息", any("工商登记信息" in t for t in vis_sects), str(vis_sects))
        check("「稽查要素」分区未显示", not any("稽查要素" in t for t in vis_sects), str(vis_sects))

        # ③ 稽查要素容器实际不可见（含 CSS 兜底）
        audit = page.evaluate("""() => {
            const e = document.getElementById('sect-audit');
            if (!e) return {missing: true};
            const cs = getComputedStyle(e);
            const box = e.getBoundingClientRect();
            return {hiddenAttr: !!e.hidden, display: cs.display, visibility: cs.visibility,
                    w: box.width, h: box.height,
                    visible: !e.hidden && cs.display !== 'none' && cs.visibility !== 'hidden'
                             && box.width > 0 && box.height > 0};
        }""")
        check("稽查要素容器存在", not audit.get("missing"), str(audit))
        check("稽查要素容器实际不可见", bool(audit) and not audit.get("visible"), str(audit))

        # ④ 工商字段只读 / ⑤ 名称可编辑
        states = page.evaluate("""() => {
            const ids = ['name','tid','legal_representative','registered_capital',
                         'established_date','registration_status','company_type',
                         'registered_address','business_scope'];
            const out = {};
            ids.forEach(function(k){
                const e = document.getElementById('pf-' + k);
                out[k] = e ? {disabled: !!e.disabled, readOnly: !!e.readOnly,
                              value: e.value, tag: e.tagName} : null;
            });
            return out;
        }""")
        check("企业名称可编辑", bool(states.get("name")) and not states["name"]["disabled"],
              str(states.get("name")))
        others = ["tid", "legal_representative", "registered_capital", "established_date",
                  "registration_status", "company_type", "registered_address", "business_scope"]
        bad = [k for k in others if not states.get(k) or not states[k]["disabled"]]
        check("其余 8 项工商字段均为只读（disabled）", not bad, str(bad))
        check("这些字段初始为空（等保存时加载，不是预填假值）",
              all((states.get(k) or {}).get("value", "") == "" for k in others),
              str({k: (states.get(k) or {}).get("value") for k in others}))

        # ⑤ 唯一必填：名称标签带 *
        stars = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('#m-form label').forEach(function(l){
                const e = l.querySelector('input,select,textarea');
                if (!e) return;
                const cs = getComputedStyle(l);
                const box = l.getBoundingClientRect();
                const visible = cs.display !== 'none' && box.width > 0 && box.height > 0;
                if (!visible) return;
                if ((l.textContent||'').indexOf('*') !== -1) out.push(e.id);
            });
            return out;
        }""")
        check("可见字段中只有「企业名称」标了必填 *", stars == ["pf-name"], str(stars))

        # ⑥ 提示文案
        hint = page.evaluate("""() => (document.getElementById('biz-hint')||{}).textContent || ''""")
        check("提示写明「只需填企业名称、点保存时自动加载」",
              ("只需填写" in hint or "只需要填写" in hint) and "自动加载" in hint, hint.strip()[:80])

        br.close()

    print("\n" + "=" * 70)
    print("通过 %d 项 | 失败 %d 项" % (len(oks), len(fails)))
    if fails:
        print("失败项：")
        for f in fails:
            print("  - " + f)
        return 1
    print("全部通过：新建项目弹窗只呈现工商登记信息，只有企业名称需要人工填写。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
