# -*- coding: utf-8 -*-
"""备份 / 恢复命令行（S-10 / D-02）。

    python scripts/backup_cli.py list                  # 列出现有备份
    python scripts/backup_cli.py create [--note 说明]  # 立即备份
    python scripts/backup_cli.py verify <目录名>       # 校验（重算 sha256 + 完整性）
    python scripts/backup_cli.py restore <目录名> --yes # 恢复（**必须先停服**）

为什么恢复要单独做 CLI 而不是放接口里
--------------------------------------
覆盖正在使用的 SQLite 文件会得到损坏库。恢复必须**停服**，而停服状态下
HTTP 接口本身也停了 ⇒ 只能由命令行完成。接口那边给的是"可执行命令"，不是假按钮。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import backup as BK   # noqa: E402


def _fmt(n) -> str:
    n = int(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f TB" % n


def cmd_list() -> int:
    s = BK.summary()
    print("备份目录：%s" % s["dir"])
    print("共 %d 份，合计 %s；间隔 %.0f 小时；保留 %d 份；当前%s"
          % (s["count"], _fmt(s["total_bytes"]), s["interval_hours"], s["keep"],
             "**需要备份**" if s["due"] else "已是最新"))
    if s["age_hours"] is not None:
        print("最近一份：%.1f 小时前" % s["age_hours"])
    for m in BK.list_backups():
        print("  %-28s %-12s %8s  %s%s"
              % (m.get("folder"), m.get("kind"), _fmt(m.get("bytes")),
                 m.get("created_at", ""), "  ⚠ 不完整" if m.get("damaged") else ""))
    return 0


def cmd_create(note: str) -> int:
    m = BK.create_backup("manual", note=note)
    print("已备份 → %s（%d 个文件，%s）"
          % (m["folder"], len(m["files"]), _fmt(sum(f["bytes"] for f in m["files"]))))
    print("完整性：%s" % m["integrity"])
    return 0


def cmd_verify(folder: str) -> int:
    v = BK.verify_backup(folder)
    print("备份：%s" % folder)
    for c in v.get("checked") or []:
        print("  %-28s %s" % (c.get("name"),
                              "sha256 ok" if c.get("sha256_ok") else
                              ("integrity=%s" % c.get("integrity", "?"))))
    if v.get("ok"):
        print("✅ 校验通过")
        return 0
    print("❌ 校验未通过：")
    for p in v.get("problems") or [v.get("reason")]:
        print("   -", p)
    return 2


def cmd_restore(folder: str, yes: bool, force: bool) -> int:
    if not yes:
        print("恢复会用备份覆盖当前数据库，且**必须先停服**。确认请加 --yes")
        return 1
    res = BK.restore_backup(folder, force=force)
    if not res.get("ok"):
        print("❌ 恢复未完成（阶段 %s）" % res.get("stage"))
        print("   原因：", res.get("reason") or res.get("diffs") or res.get("problems"))
        return 2
    print("✅ 恢复完成")
    print("   已还原：%s" % ", ".join(res.get("restored_files") or []))
    print("   后悔药：%s（如需回退，用这份 pre-restore 再恢复一次）" % res.get("safety_backup"))
    print("   恢复后完整性：%s" % res.get("after", {}).get("integrity"))
    print("   %s" % res.get("note", ""))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="财税系统备份/恢复")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p_create = sub.add_parser("create")
    p_create.add_argument("--note", default="命令行手动备份")
    p_verify = sub.add_parser("verify")
    p_verify.add_argument("folder")
    p_restore = sub.add_parser("restore")
    p_restore.add_argument("folder")
    p_restore.add_argument("--yes", action="store_true")
    p_restore.add_argument("--force", action="store_true", help="跳过「服务在跑」检查（不推荐）")
    args = ap.parse_args()

    if args.cmd == "list":
        return cmd_list()
    if args.cmd == "create":
        return cmd_create(args.note)
    if args.cmd == "verify":
        return cmd_verify(args.folder)
    return cmd_restore(args.folder, args.yes, args.force)


if __name__ == "__main__":
    raise SystemExit(main())
