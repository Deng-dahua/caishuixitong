# -*- coding: utf-8 -*-
"""一次性清理脚本（2026-10-08）—— 由 AI 生成，**请由你手动执行**。

为什么需要你手动执行：
    AI 工具层有「批量删除守护」（`SAFE_DELETE_BULK_GUARD`）：单次删除超过 50 个文件会被强制终止。
    这是**在你自己的应用内操作不受限制**的安全机制（见 `start8001.bat` 的注释）。
    所以剩余的批量清理必须由你本地执行。

用法（在项目根目录）：
    ./.venv/Scripts/python.exe tools/cleanup_20261008.py            # 预演（只打印，不动文件）
    ./.venv/Scripts/python.exe tools/cleanup_20261008.py --apply    # 实际执行

安全保证：
  · **移入回收站 `data/trash/`，不做物理删除**（除「清空回收站」这一步，那是你已确认的）；
  · 备份已在 `baseline/_bak/cleanup_20261008_1239/`（382 个脚本 + trash 清单 + 清理清单）；
  · 排除一切项目必需目录（.venv / .workbuddy / engine / config / static / tests / tools / docs /
    baseline/V1.0 / data/cache / scripts/four_reports / data/logs/access.jsonl）。
"""
from __future__ import annotations

import glob
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
TRASH = os.path.join(ROOT, "data", "trash")
APPLY = "--apply" in sys.argv

#: 绝不能动的路径（命中即跳过）
PROTECTED = (
    ".venv", ".workbuddy", "engine", "config", "static", "tests", "tools", "docs",
    "baseline/V1.0", "baseline/_bak", "data/cache", "scripts/four_reports",
    "data/logs/access.jsonl", "data/uploads", "data/accounting.db",
)

#: 说明：`.pytmp*`（pytest 临时目录）与 `__pycache__`/`.pytest_cache` 均属"可重生成产物"，
#: 已在 .gitignore 中声明，删除无副作用 —— 故纳入 A 类清理范围。


def protected(p: str) -> bool:
    rel = os.path.relpath(p, ROOT).replace("\\", "/")
    return any(rel == k or rel.startswith(k + "/") for k in PROTECTED)


def _relocate(p: str, report: list) -> None:
    """把条目移入回收站（预演时只登记、不动文件）。

    ★ 2026-10-09 收敛（根因：本闸门外的「第二份实现」）：
      本文件原来自己写了一份 `def move_to_trash(...)`（同名同概念），而 `move_to_trash` 是
      `check_delete_exits` 声明的**底层删除原语 —— 只准在 `runtime_storage` 里
      实现（唯一实现）**。两份实现已经分叉：本文件把回收站硬编码为
      `<ROOT>/data/trash`，权威用 `runtime_storage.TRASH_DIR`（随 `APP_DATA_DIR`
      走，隔离实例才不会越界写真实项目）。
      现一律**委托唯一权威**；本文件只保留自己的外围逻辑（`protected()` 白名单与
      预演报告），**不再自带任何删除/移动实现**。
    """
    if not os.path.exists(p) or protected(p):
        return
    if APPLY:
        from runtime_storage import move_to_trash as _mv
        _mv(p)
    report.append(f"  [{'已移入' if APPLY else '待移入'}] {os.path.relpath(p, ROOT)}")


def main() -> int:
    print(f"=== 清理{'执行' if APPLY else '预演'}（{'--apply' if APPLY else '只打印'}）=== ")
    os.makedirs(TRASH, exist_ok=True)
    report: list[str] = []

    # ── D：清空回收站（你已确认；这是唯一物理删除步骤）
    items = sorted(os.listdir(TRASH))
    print(f"\n[D] 清空回收站 data/trash：{len(items)} 项")
    for name in items:
        p = os.path.join(TRASH, name)
        if APPLY:
            try:
                shutil.rmtree(p) if os.path.isdir(p) and not os.path.islink(p) else os.remove(p)
            except Exception as exc:  # noqa: BLE001
                print(f"   失败 {name}: {exc}")
        else:
            print(f"  [待删] {name}")
    print(f"[D] 回收站清空{'完成' if APPLY else '（预演）'}")

    # ── B：调试日志 → 回收站
    print("\n[B] 调试日志 → 回收站")
    for pat in ("scripts/_*.log", "scripts/_*.out", "data/logs/_*.out", "data/logs/_*.txt"):
        for f in sorted(glob.glob(os.path.join(ROOT, pat))):
            if os.path.isfile(f):
                _relocate(f, report)

    # ── C：临时文件 → 回收站
    print("\n[C] 临时文件 → 回收站")
    for rel in ("_tmp_docx", "_page_now.html", "server.err", "server.log", "cookies_tmp.txt"):
        _relocate(os.path.join(ROOT, rel), report)

    # ── G：一次性脚本 scripts/_*.py → 回收站
    print("\n[G] 一次性脚本 scripts/_*.py → 回收站")
    for f in sorted(glob.glob(os.path.join(ROOT, "scripts", "_*.py"))):
        if os.path.isfile(f):
            _relocate(f, report)

    # ── A：python 缓存与测试临时目录 → 回收站
    print("\n[A] __pycache__ / .pytest_cache / .pytmp* → 回收站")
    # .pytmp*：pytest 夹具（tmp_path 类）为每个用例建的临时目录。
    # 证据：.gitignore:61 已列 `.pytmp/` 并注明"可重生成，不进版本库"；git 跟踪数 0；跑测试即重建。
    for d in sorted(glob.glob(os.path.join(ROOT, ".pytmp*"))):
        _relocate(d, report)
    for d in sorted(glob.glob(os.path.join(ROOT, "**", "__pycache__"), recursive=True)):
        if os.path.isdir(d) and ".venv" not in d:
            _relocate(d, report)
    for d in (".pytest_cache",):
        _relocate(os.path.join(ROOT, d), report)

    print(f"\n[B/C/G/A] 共 {len(report)} 项")
    if not APPLY:
        print("（预演模式，未改动任何文件。加 --apply 执行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
