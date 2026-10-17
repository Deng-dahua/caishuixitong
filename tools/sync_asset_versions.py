# -*- coding: utf-8 -*-
"""把 `static/index.html` 里静态资源的 `?v=` 同步为**文件内容哈希**。

为什么需要它（根因，2026-10-02 用户实测）
----------------------------------------
浏览器按「URL（含 query）」做缓存键。前端 JS 改动后如果 `?v=` 没变，浏览器
**永远不会重新下载**那份 JS —— 后端算得再对，用户页面上也看不见。

实测事故：`tax-doc-analysis.js` 的内容在 2026-10-01 20:50 更新过（新增了
「主营业务成本 vs 期间费用 三态归属」渲染），但 index.html 里仍是
`?v=2026092901`（9/29）→ 用户在 9/29 之后访问过，就一直用旧 JS，
**新章节根本不渲染**。用户反馈「改了这么多，报告还是没有什么变化」。

用手工维护的日期串一定会再犯（人记不住，且改动前后没任何提示）。
故改为**内容哈希**：文件内容一变，`?v=` 必然变；配合闸门
`audit_consistency.check_static_asset_cache_version`（v 必须等于哈希，
否则 ERROR），把「忘了同步」从"靠记性"变成"机器拦"。

用法
----
    python tools/sync_asset_versions.py           # 同步
    python tools/sync_asset_versions.py --check   # 只检查（CI/闸门用），不一致返回 1
"""
from __future__ import annotations

import hashlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "static", "index.html")
#: ★ 2026-10-17：此前**只同步 `static/index.html`**，其余页面里的 `?v=` 是**硬编码**的，
#: 于是同一份 JS 改了内容，非首页仍指向旧哈希（浏览器按含 query 的 URL 缓存 ⇒ "改了等于没改"
#: 会在非首页复现）。现改为**遍历 `static/*.html` 全部页面**。
STATIC_DIR = os.path.join(ROOT, "static")
# 引用形如 /static/js/xxx.js?v=2026092901（也兼容 css）
# ⚠ 只匹配**已带 `?v=`** 的引用：注释里提到的路径（如"机制权威 = /static/js/rbac-nav.js"）
#   不应被追加版本号。
_REF = re.compile(r"(/static/(?:js|css)/[A-Za-z0-9_.\-]+)\?v=([0-9A-Za-z_.\-]+)")


def target_pages():
    """需要同步的页面 = `static/*.html`（按名称排序，输出可复现）。"""
    if not os.path.isdir(STATIC_DIR):
        return []
    return sorted(
        os.path.join(STATIC_DIR, n)
        for n in os.listdir(STATIC_DIR)
        if n.endswith(".html")
    )


def asset_version(rel_path: str) -> str:
    """资源版本 = 文件内容 sha1 前 10 位（缺文件返回空串，由闸门另行报错）。"""
    p = os.path.join(ROOT, rel_path.lstrip("/").replace("/", os.sep))
    if not os.path.isfile(p):
        return ""
    with open(p, "rb") as fh:
        return hashlib.sha1(fh.read()).hexdigest()[:10]


def scan(html: str):
    """返回 [(引用路径, 当前 v, 应为 v)]；缺失文件时 应为 v 为空串。"""
    out = []
    for m in _REF.finditer(html):
        rel, cur = m.group(1), m.group(2)
        out.append((rel, cur, asset_version(rel)))
    return out


def main(argv) -> int:
    check_only = "--check" in argv
    pages = target_pages()
    if not pages:
        print("[sync_asset_versions] 找不到 %s 下的页面" % STATIC_DIR)
        return 1

    total_rows = 0
    total_stale = 0
    total_missing = 0
    changed_files = 0

    for path in pages:
        with open(path, "rb") as fh:
            raw = fh.read()
        html = raw.decode("utf-8")

        rows = scan(html)
        total_rows += len(rows)
        stale = [(r, c, w) for r, c, w in rows if w and c != w]
        missing = [r for r, _c, w in rows if not w]
        total_stale += len(stale)
        total_missing += len(missing)
        if not rows:
            continue
        rel_page = os.path.relpath(path, ROOT).replace(os.sep, "/")
        for rel, cur, want in stale:
            print("  更新 %s  %s  %s → %s" % (rel_page, rel, cur, want))
        for rel in missing:
            print("  !! %s 引用指向不存在的文件: %s" % (rel_page, rel))
        if stale and not check_only:
            def _sub(m):
                want = asset_version(m.group(1))
                return "%s?v=%s" % (m.group(1), want) if want else m.group(0)
            new_html = _REF.sub(_sub, html)
            # 行尾保持原样（逐字节回写，不改 CRLF/LF）
            with open(path, "wb") as fh:
                fh.write(new_html.encode("utf-8"))
            changed_files += 1

    if check_only:
        if total_stale or total_missing:
            print("[sync_asset_versions] 不同步：%d 处版本号过期 / %d 处文件缺失"
                  "（跑 python tools/sync_asset_versions.py 修复）" % (total_stale, total_missing))
            return 1
        print("[sync_asset_versions] 全部同步（%d 个页面 / %d 个资源引用）"
              % (len(pages), total_rows))
        return 0

    if not total_stale and not total_missing:
        print("[sync_asset_versions] 无需更新（%d 个页面 / %d 个资源引用已同步）"
              % (len(pages), total_rows))
        return 0
    print("[sync_asset_versions] 已写回 %d 个页面" % changed_files)
    return 1 if total_missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
