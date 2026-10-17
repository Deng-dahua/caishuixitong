# -*- coding: utf-8 -*-
"""把 `page-memory.js`（H-01 记忆上次选择）注入所有业务页面（幂等）。

新增页面后跑一次即可：
    python scripts/_inject_page_memory.py            # 注入
    python scripts/_inject_page_memory.py --check     # 只检查（供 CI 用）

★ 为什么用脚本而不是逐页手写：26+ 个页面手工加一行必然漏；
  而 `tests/test_trash_and_memory.py` 有一条"所有页面都必须引入"的判据守着。
★ 结构断言：插入前后 `</body>` 数量不变、脚本只出现一次（防止把 HTML 写坏）。
"""
from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TAG = '<script src="/static/js/page-memory.js?v=0000000000" defer></script>'
#: 不需要记忆的页面（登录/注册/改密这类一次性表单，记住反而危险）
SKIP = {"login.html", "consent.html"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    missing, done = [], []
    for p in sorted((ROOT / "static").glob("*.html")):
        if p.name in SKIP:
            continue
        s = p.read_text(encoding="utf-8")
        if "page-memory.js" in s:
            continue
        if "</body>" not in s:
            missing.append(p.name + "(无 </body>)")
            continue
        missing.append(p.name)
        if args.check:
            continue
        i = s.index("</body>")
        s2 = s[:i] + "  " + TAG + "\n" + s[i:]
        assert s2.count("</body>") == s.count("</body>"), p.name
        assert s2.count("page-memory.js") == 1, p.name
        p.write_text(s2, encoding="utf-8")
        done.append(p.name)
    if args.check:
        if missing:
            print("未注入 page-memory.js 的页面：%s" % missing)
            return 1
        print("全部页面均已注入 ✅")
        return 0
    print("已注入 %d 个页面%s" % (len(done), ("：" + ", ".join(done)) if done else "（无变化）"))
    if missing and done:
        print("以下页面仍缺（可能无 </body>）：%s" % [m for m in missing if m not in done])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
