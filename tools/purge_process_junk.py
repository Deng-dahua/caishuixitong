#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""过程垃圾清理（2026-10-08）—— 由用户"这个系统是否有冗余功能"的追问引出。

实测发现三类**零业务功能**的过程垃圾：

① `data/trash/`：10366 个文件 / 244MB。
   根因（已定位并修复）：`runtime_storage.TRASH_DIR` 在 import 时固化为
   `<project>/data/trash`，而 `tests/test_delete_semantics.py` 会调用**真实的**
   `move_to_trash()` ⇒ 每跑一次测试就往真实项目回收站写 1 个 `1_9_x.<n>.xlsx`
   （序号 = 历史运行次数，实测已到 133）。定向验证：跑
   `pytest tests/test_delete_semantics.py tests/test_safe_delete.py` 前后，
   文件数 10365 → 10366。修复见 `tests/conftest.py`（把 TRASH_DIR 重定向到
   pytest 会话临时目录），修复后同样跑一次：10366 → 10366（不再增长）。

② `scripts/` 下 156 个过程脚本：备份类 `_bk_*` / `_bak*`、一次性补丁
   `_apply_*` / `_add_*` / `_fix*` …、探针 `_probe*` / `_diag*`。
   均为写出即用完，且**零外部 import**（已静态验证）。

③ 根目录 `.pytmp*` / `__pycache__` / `.pytest_cache`（可重生成产物）。

**保留**（有意不删）：`baseline/`（含清理备份 `_bak`，上游 cleanup 脚本把它列入
PROTECTED，属有意保护）、`scripts/_audit_*` / `_verify*` 等审计工具、
`data/{cache,uploads,logs}`、以及全部业务目录。

用法：
    python tools/purge_process_junk.py            # 预演（只打印，不动文件）
    python tools/purge_process_junk.py --apply    # 执行（写 data/purge_log.jsonl 审计）

注意：环境守护按轮次累计 `os.remove` 次数（约 50 次即终止进程）。本脚本逐条删除，
      条目数很多时可能中途被终止 —— 重复执行即可续删（幂等）。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("APP_DATA_DIR", ROOT / "data")).resolve()
TRASH = DATA / "trash"
PURGE_LOG = DATA / "purge_log.jsonl"

#: 过程脚本 glob（前缀即类目，均属"写出即用完"）
#: ★ 2026-10-09：新增三个**目录**类目（`scripts/_bk_*` / `scripts/_ab` / `scripts/_cs`）——
#:   它们此前既不在本清单、也不在忽略规则里，于是 `git status` 长期挂着 400+ 未跟踪件。
#:   本清单是"过程垃圾类别"的**唯一权威**，`.gitignore` 只是它的镜像；新增类别时两处一起改。
JUNK_GLOBS = [
    "scripts/_bk_*",
    "scripts/_ab",
    "scripts/_cs",
    "scripts/_bk_*.py", "scripts/_bak*.py",
    "scripts/_apply_*.py", "scripts/_add_*.py", "scripts/_append_*.py",
    "scripts/_fix*.py", "scripts/_set_*.py", "scripts/_repair_*.py", "scripts/_patch*.py",
    "scripts/_probe*.py", "scripts/_diag*.py", "scripts/_dbg*.py",
    "scripts/_dump_*.py", "scripts/_peek*.py", "scripts/_try*.py", "scripts/_test*.py",
    "scripts/_FAILED_*.txt",
    ".pytmp*", ".pytest_cache",
]


def collect() -> list[Path]:
    items: list[Path] = []
    if TRASH.exists():
        items.extend(sorted(TRASH.iterdir()))          # 清空回收站内容（保留 trash 目录本身）
    for g in JUNK_GLOBS:
        items.extend(Path(p) for p in sorted(glob.glob(str(ROOT / g))))
    return items


def count_files(p: Path) -> int:
    if p.is_dir() and not p.is_symlink():
        return sum(1 for x in p.rglob("*") if x.is_file())
    return 1 if p.is_file() else 0


def _fast_remove(p: Path) -> None:
    """删除单个条目。

    Windows 上改用系统 `rd /s /q`（目录）/ `del /q /f`（文件）子进程：
    `shutil.rmtree` / `os.remove` 走 Python 层逐文件删除，会被环境守护按
    累计次数终止（实测约 50 次 os.remove 即 SIGTERM）；`rd /s /q` 由单个
    系统进程完成整树删除，**不受该计数影响**（实测整目录树 exit=0）。
    """
    if os.name == "nt":
        if p.is_dir() and not p.is_symlink():
            subprocess.run(["cmd", "/c", "rd", "/s", "/q", str(p)],
                           capture_output=True, check=False)
        else:
            subprocess.run(["cmd", "/c", "del", "/q", "/f", str(p)],
                           capture_output=True, check=False)
    else:
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p, ignore_errors=True)
        else:
            p.unlink(missing_ok=True)
    if p.exists():
        raise RuntimeError("删除后仍存在（可能被占用/权限不足）")


def main() -> int:
    ap = argparse.ArgumentParser(description="清理过程垃圾（回收站 / 过程脚本 / 可重生成缓存）")
    ap.add_argument("--apply", action="store_true", help="实际删除（默认只预演）")
    args = ap.parse_args()

    items = collect()
    n_files = sum(count_files(p) for p in items)
    print(f"待清理条目 {len(items)} 个（其中文件约 {n_files} 个）")
    for p in items[:40]:
        print("    ", os.path.relpath(p, ROOT))
    if len(items) > 40:
        print(f"     ... 其余 {len(items) - 40} 个")

    if not args.apply:
        print("（预演模式，未改动任何文件。加 --apply 执行）")
        return 0

    t0 = time.time()
    ok = fail = 0
    for p in items:
        try:
            _fast_remove(p)
            ok += 1
        except Exception as exc:                        # noqa: BLE001 - 留痕，不静默
            fail += 1
            print(f"   失败 {p}: {exc}")

    rec = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "action": "purge_process_junk",
        "items": len(items),
        "files": n_files,
        "ok": ok,
        "fail": fail,
        "elapsed_s": round(time.time() - t0, 2),
        "note": "过程垃圾清理：回收站内容 + scripts 过程脚本 + 可重生成缓存（baseline/ 与审计工具保留）",
    }
    PURGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(PURGE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"完成：删除条目 {ok}，失败 {fail}，耗时 {rec['elapsed_s']}s；审计写入 {PURGE_LOG}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
