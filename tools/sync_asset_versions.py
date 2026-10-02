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
# 引用形如 /static/js/xxx.js?v=2026092901（也兼容 css）
_REF = re.compile(r"(/static/(?:js|css)/[A-Za-z0-9_.\-]+)\?v=([0-9A-Za-z_.\-]+)")


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
    if not os.path.isfile(INDEX):
        print("[sync_asset_versions] 找不到 %s" % INDEX)
        return 1
    with open(INDEX, "rb") as fh:
        raw = fh.read()
    html = raw.decode("utf-8")

    rows = scan(html)
    stale = [(r, c, w) for r, c, w in rows if w and c != w]
    missing = [r for r, _c, w in rows if not w]

    for rel, cur, want in stale:
        print("  更新 %s  %s → %s" % (rel, cur, want))
    for rel in missing:
        print("  !! 引用指向不存在的文件: %s" % rel)

    if check_only:
        if stale or missing:
            print("[sync_asset_versions] 不同步：%d 处版本号过期 / %d 处文件缺失"
                  "（跑 python tools/sync_asset_versions.py 修复）" % (len(stale), len(missing)))
            return 1
        print("[sync_asset_versions] 全部同步（%d 个资源）" % len(rows))
        return 0

    if not stale and not missing:
        print("[sync_asset_versions] 无需更新（%d 个资源已同步）" % len(rows))
        return 0

    def _sub(m):
        want = asset_version(m.group(1))
        return "%s?v=%s" % (m.group(1), want) if want else m.group(0)

    new_html = _REF.sub(_sub, html)
    # 行尾保持原样（index.html 是 bare-LF）
    with open(INDEX, "wb") as fh:
        fh.write(new_html.encode("utf-8"))
    print("[sync_asset_versions] 已写回 %s（更新 %d 处）" % (INDEX, len(stale)))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
