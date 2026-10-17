# -*- coding: utf-8 -*-
"""清理隔离实例中的测试项目（S1 复用固定 USCC，须先移除同名项目）。

★ 安全铁律（2026-10-17 事故后确立）：
  1. 删物理文件前**逐条**确认路径归属「哪个环境」；
  2. 用 `os.path.realpath` + `os.path.commonpath` 做**规范化**校验，不用字符串前缀
     （前缀法在跨目录/大小写/转义下会失效 —— 本轮就被它挡了一次，属判据本身太脆）；
  3. 只在**隔离根目录内**删除；一旦越界立即中止，不做任何删除。
"""
from __future__ import annotations

import os
import sqlite3
import sys

ISOL_ROOT = r"C:\Users\Administrator\WorkBuddy\2026-08-04-21-37-33\_scenario_sim"
PROD_ROOT = r"C:\Users\Administrator\WorkBuddy\2026-08-04-21-37-33\caishuixitong\data"
DB = os.path.join(ISOL_ROOT, "data", "accounting.db")

TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 39


def _inside(path: str, root: str) -> bool:
    """规范化后判断 path 是否位于 root 之内（含 root 本身）。"""
    if not path:
        return False
    try:
        p = os.path.realpath(path)
        r = os.path.realpath(root)
        return os.path.commonpath([p, r]) == r
    except (ValueError, OSError):
        return False


def main() -> int:
    if not os.path.isfile(DB):
        print("找不到隔离库:", DB)
        return 2
    conn = sqlite3.connect(DB)
    rows = list(conn.execute(
        "select id, original_name, storage_path from documents where project_id=?", (TARGET,)))
    print("项目 %d 的资料: %d 条" % (TARGET, len(rows)))

    prod_hits = [p for _, _, p in rows if _inside(p, PROD_ROOT)]
    iso_hits = [p for _, _, p in rows if _inside(p, ISOL_ROOT)]
    outside = [p for _, _, p in rows if not _inside(p, ISOL_ROOT)]
    print("  在隔离目录内: %d | 在生产目录内: %d | 二者之外: %d"
          % (len(iso_hits), len(prod_hits), len(outside)))
    if prod_hits:
        print("  ❌ 存在指向**生产目录**的记录 ⇒ 中止，不做任何删除：")
        for p in prod_hits[:5]:
            print("     ", p)
        return 3
    if outside:
        print("  ❌ 存在无法判定归属的路径 ⇒ 中止（不猜、不删）：")
        for p in outside[:5]:
            print("     ", p)
        return 3

    # 只删数据库行（文件随后按规范化校验结果逐个删）
    for table in ("extracted_tables", "extracted_fields", "document_pages", "extract_issues"):
        cols = [r[1] for r in conn.execute("pragma table_info(%s)" % table)]
        if "document_id" in cols:
            n = conn.execute(
                "delete from %s where document_id in "
                "(select id from documents where project_id=?)" % table, (TARGET,)).rowcount
            print("  %-18s 删 %d 行" % (table, n))
    for table in ("reports", "project_members", "documents"):
        cols = [r[1] for r in conn.execute("pragma table_info(%s)" % table)]
        if "project_id" in cols:
            n = conn.execute("delete from %s where project_id=?" % table, (TARGET,)).rowcount
            print("  %-18s 删 %d 行" % (table, n))
    conn.execute("delete from projects where id=?", (TARGET,))
    conn.commit()

    removed = 0
    for _, _name, path in rows:
        if path and _inside(path, ISOL_ROOT) and os.path.isfile(path):
            os.remove(path)
            removed += 1
    print("  已删隔离目录内文件: %d" % removed)
    print("剩余项目:", list(conn.execute("select id, code, taxpayer_id from projects")))
    print("剩余资料:", list(conn.execute("select project_id, count(*) from documents group by project_id")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
