# -*- coding: utf-8 -*-
"""把「返回主界面 / 返回首页」链接统一指向**首页总览**（2026-10-18）。

## 为什么需要本脚本

用户需求：「按返回主界面也是显示首页总览页面」。清点后发现两处缺陷：

  ① **指向死链**：8 个页面写的是 `href="/index"`，而系统**没有 `/index` 路由**
     （实测 302→/login、带会话后 404）⇒ 点「返回主界面」是**坏链接**；
  ② **指向"上次页面"**：其余 13 个页面写 `href="/"`，而 `GET /` 会读
     `localStorage.lastPage` 把用户送回上次停留的内页 ⇒ 点了「返回主界面」
     却停在别的页面，与按钮文字不符。

## 做法（单一权威）

**唯一权威 = 本文的 `HOME_HREF`**（`/?page=home`）。`navbar` 文案与目标页的一一对应
关系**不由本脚本猜测**：只认「链接文字含『返回主界面』或『返回首页』，且 href 是
`/` 或 `/index`(或带 `/index.html`)」这一种形态，逐页替换成 `HOME_HREF`。

`/?page=home` 的语义见 `static/js/core.js::_resolveLandingPage()`：它是一次性
「主动导航」信号（落地后即被 `history.replaceState` 抹掉），因此
**点返回 = 一定看到首页总览**，而**按 F5 = 仍停当前页**（两条需求互不打架）。

用法：
    python scripts/_wire_home_links.py            # 注入（幂等）
    python scripts/_wire_home_links.py --check    # 只检查，需要改动则返回 1
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "static")

#: ★ 唯一权威：所有「返回主界面 / 返回首页」的目标地址
HOME_HREF = "/?page=home"

#: 需要处理的链接文字（同时用于闸门判据）
BACK_TEXTS = ("返回主界面", "返回首页")

#: 「返回」链接可以接受的**当前**写法（/ 或 /index 家族）。带别的路径的链接
#: （如 `/select-company`、`/login`）不属于「返回主界面」，一律不动。
_OLD_HREFS = ('"/"', "'/'", '"/index"', "'/index'", '"/index.html"', "'/index.html'")

#: 匹配：`<a ... href="X" ...>文字</a>`（文字里含「返回…」其一）
_A_TAG = re.compile(r"<a\b[^>]*>.*?</a>", re.S | re.I)
_HREF_ATTR = re.compile(r"""href\s*=\s*(['"])([^'"]*)\1""", re.I)


def _pages() -> list:
    if not os.path.isdir(STATIC):
        return []
    return sorted(
        os.path.join(STATIC, n) for n in os.listdir(STATIC) if n.endswith(".html")
    )


def _fix_html(html: str) -> tuple:
    """把「返回主界面 / 返回首页」链接的 href 换成 `HOME_HREF`。

    返回 `(新 html, 改动列表)`；改动列表元素为 `(原 href, 文字)`。
    只改**确实是返回类链接**且**原 href 属于允许的旧写法**的锚点。
    """
    changed = []

    def _repl(m: re.Match) -> str:
        tag = m.group(0)
        if not any(t in tag for t in BACK_TEXTS):
            return tag
        # 取本锚点的 href（取第一个；返回类链接只有一个）
        hm = _HREF_ATTR.search(tag)
        if not hm:
            return tag
        old = hm.group(2)
        if old not in ("/", "/index", "/index.html"):
            return tag
        new_tag = (
            tag[:hm.start()]
            + 'href="%s"' % HOME_HREF
            + tag[hm.end():]
        )
        changed.append((old, "返回主界面/返回首页"))
        return new_tag

    return _A_TAG.sub(_repl, html), changed


def main(argv: list) -> int:
    check_only = "--check" in argv
    total = 0
    stale = []
    for path in _pages():
        rel = "static/%s" % os.path.basename(path)
        # ★ 读写都用 newline="" —— 原样保留行尾（本仓 HTML 为 CRLF；用默认的
        #   通用换行会把整份文件静默改成 LF，产生全文件 diff、掩盖真实改动）。
        with open(path, "r", encoding="utf-8", newline="") as fh:
            html = fh.read()
        new_html, changed = _fix_html(html)
        if not changed:
            continue
        total += len(changed)
        if check_only:
            stale.append((rel, changed))
            continue
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(new_html)
        print("[已改] %s：%d 处 → %s" % (rel, len(changed), HOME_HREF))

    if check_only:
        if stale:
            print("需要同步的页面（共 %d 处）：" % total)
            for rel, changed in stale:
                print("  · %s: %s" % (rel, changed))
            print("\n跑 `python scripts/_wire_home_links.py` 同步。")
            return 1
        print("全部页面的「返回主界面」链接均指向 %s（%d 处已检查）" % (
            HOME_HREF, sum(1 for _ in _pages())))
        return 0

    print("\n完成：%d 处链接已指向 %s" % (total, HOME_HREF) if total else "已完成：无需改动")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))