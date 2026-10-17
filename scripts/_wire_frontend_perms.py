# -*- coding: utf-8 -*-
"""按 `config/frontend_perms.json` 把前端权限门控**注入**页面（P0-8 扩展轮，2026-10-17）。

做两件事：
  ① 页面若缺 `rbac-nav.js` 引用 ⇒ 在 `</body>` 前插入（带**内容哈希** `?v=`）；
  ② 按表给指定 `id` 的元素补 `data-perm="<权限码>"` / `data-perm-admin="1"`。

★ 单一权威：表在 `config/frontend_perms.json`；本脚本只是"把表落到 HTML"的搬运工，
  不自行决定任何权限归属。检测口径见 `tests/test_frontend_perm_gate.py`（漂移闸门）。

用法：
    python scripts/_wire_frontend_perms.py            # 注入（幂等）
    python scripts/_wire_frontend_perms.py --check    # 只检查，需要改动则返回 1
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "config", "frontend_perms.json")
RBAC_JS = "js/rbac-nav.js"


def _asset_hash(rel: str) -> str:
    p = os.path.join(ROOT, "static", rel.replace("/", os.sep))
    if not os.path.isfile(p):
        return ""
    with open(p, "rb") as fh:
        return hashlib.sha1(fh.read()).hexdigest()[:10]


def _rbac_tag() -> str:
    v = _asset_hash(RBAC_JS)
    return '  <script src="/static/js/rbac-nav.js?v=%s" defer></script>' % v


def _ensure_include(html: str) -> tuple:
    """确保页面引用了 `rbac-nav.js`（带 `?v=`）。返回 (新 html, 是否改动)。"""
    if re.search(r"/static/js/rbac-nav\.js", html):
        return html, False
    tag = _rbac_tag()
    m = re.search(r"^[ \t]*</body>", html, re.M)
    if not m:
        return html + "\n" + tag + "\n", True
    return html[:m.start()] + tag + "\n" + html[m.start():], True


def _attr_for(entry: dict) -> str:
    if entry.get("admin"):
        return 'data-perm-admin="1"'
    return 'data-perm="%s"' % entry["perm"]


def _inject(html: str, element_id: str, attr: str) -> tuple:
    """给 `id="<element_id>"` 的标签补属性（幂等）。返回 (新 html, 状态)。

    状态 ∈ {"added", "already", "not_found", "ambiguous"}
    """
    tag_re = re.compile(r"<[a-zA-Z][^<>]*\bid=\"%s\"[^<>]*>" % re.escape(element_id))
    hits = list(tag_re.finditer(html))
    if not hits:
        return html, "not_found"
    if len(hits) > 1:
        return html, "ambiguous"
    tag = hits[0].group(0)
    key = attr.split("=")[0]
    if key in tag:
        return html, "already"
    new_tag = tag[:-1].rstrip() + " " + attr + ">"
    return html[:hits[0].start()] + new_tag + html[hits[0].end():], "added"


def main(argv) -> int:
    check_only = "--check" in argv
    cfg = json.loads(open(CONFIG, encoding="utf-8").read())
    pages = cfg["pages"]

    problems = []
    changed = 0
    added_attrs = 0

    for page, entries in sorted(pages.items()):
        path = os.path.join(ROOT, "static", page)
        if not os.path.isfile(path):
            problems.append("%s 不存在" % page)
            continue
        with open(path, "rb") as fh:
            raw = fh.read()
        html = raw.decode("utf-8")
        before = html

        html, inc = _ensure_include(html)
        if inc:
            print("  %s  ← 补 rbac-nav.js 引用" % page)

        for entry in entries:
            attr = _attr_for(entry)
            html, st = _inject(html, entry["id"], attr)
            if st == "added":
                print("  %s  #%s ← %s" % (page, entry["id"], attr))
                added_attrs += 1
            elif st == "already":
                pass
            elif st == "not_found":
                problems.append("%s: 未找到 id=%s（表中登记的入口不存在）" % (page, entry["id"]))
            elif st == "ambiguous":
                problems.append("%s: id=%s 出现多次（无法确定注入位置）" % (page, entry["id"]))

        if html != before:
            changed += 1
            if not check_only:
                with open(path, "wb") as fh:      # 逐字节回写，保行尾
                    fh.write(html.encode("utf-8"))

    for p in problems:
        print("  ⚠ " + p)

    if check_only:
        if changed or problems:
            print("[wire_frontend_perms] 需处理：%d 个页面待注入 / %d 个问题"
                  "（跑 python scripts/_wire_frontend_perms.py 修复）" % (changed, len(problems)))
            return 1
        print("[wire_frontend_perms] 已全部就位（%d 个页面 / %d 个入口）"
              % (len(pages), sum(len(v) for v in pages.values())))
        return 0

    print("[wire_frontend_perms] 完成：改动 %d 个页面，新增 %d 处属性，问题 %d 个"
          % (changed, added_attrs, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
