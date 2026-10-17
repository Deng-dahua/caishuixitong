# -*- coding: utf-8 -*-
"""回收站服务层（H-04，2026-10-17）。

为什么单列一层
--------------
① **删除原语必须可被闸门核到**：`tools/audit_consistency.check_delete_exits` 会校验
   「声明过的出口函数是否真的存在」，其扫描范围是 `main.py` + `engine/*.py`。
   把清空逻辑放在根目录的 `*_api.py` 里，闸门就核不到实现（本轮实测报 ERROR）。
   更合理的是本来就该：**API 薄、逻辑在 engine**。
② 还原/清空都是"动文件"的操作，集中一处更好做边界检查（目标必须在 `DATA_DIR` 内）。

全部动作都走权威原语：移动用 `shutil.move`，**删除只用** `runtime_storage.empty_trash_batch`
（已在 `check_delete_exits` 登记，见 `_EXITS["empty_trash"]`）。
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime_storage import DATA_DIR, TRASH_DIR, empty_trash_batch

#: 文件名形如 `1_100_xxx.xlsx` ⇒ 首段是账套 id（上传命名口径）
_COMPANY_PREFIX = re.compile(r"^(\d{1,9})_")

#: 单批清理硬上限（环境守护对单轮删除有累计上限，一次清太多会终止服务）
MAX_BATCH = 20


class TrashError(Exception):
    """回收站操作的业务错误（带 HTTP 语义状态码，由 API 层原样转发）。"""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def company_of(name: str) -> Optional[int]:
    """从文件名推断账套 id（推不出返回 None —— **不猜**）。"""
    m = _COMPANY_PREFIX.match(name or "")
    if not m:
        return None
    cid = int(m.group(1))
    return cid if 0 < cid < 10 ** 9 else None


def assert_inside(path: Path) -> Path:
    """写操作硬护栏：目标必须在 `DATA_DIR` 内（2026-10-17 事故后的统一要求）。"""
    root = Path(DATA_DIR).resolve()
    target = Path(path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise TrashError("拒绝写入：目标不在数据目录内", 400) from None
    return target


def _safe_name(name: str) -> str:
    """只取 basename，阻断 `../` 之类的路径逃逸。"""
    base = Path(str(name or "")).name
    if not base or base in (".", ".."):
        raise TrashError("文件名无效", 400)
    return base


def listing() -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    if TRASH_DIR.is_dir():
        entries = sorted(TRASH_DIR.iterdir(),
                         key=lambda x: -x.stat().st_mtime if x.exists() else 0)
        for p in entries:
            if not p.is_file():
                continue
            st = p.stat()
            cid = company_of(p.name)
            items.append({
                "name": p.name,
                "bytes": st.st_size,
                "mtime": st.st_mtime,
                "company_id": cid,
                "restore_to": ("uploads/%s/" % cid) if cid else "restored/",
            })
    return {
        "dir": str(TRASH_DIR),
        "count": len(items),
        "total_bytes": sum(i["bytes"] for i in items),
        "items": items,
        "note": ("回收站是**平铺**存放的（原始路径未记录）⇒ 还原时按文件名首段推断账套目录；"
                 "推断不出就放到 `data/restored/`，不会猜错位置覆盖别人。"),
    }


def restore_one(name: str) -> Dict[str, Any]:
    """把回收站里的一个文件放回 `uploads/<账套>/`（推不出账套则 `restored/`）。"""
    base = _safe_name(name)
    src = TRASH_DIR / base
    if not src.is_file():
        raise TrashError("回收站里没有该文件：%s" % name, 404)
    cid = company_of(base)
    dest_dir = assert_inside((DATA_DIR / "uploads" / str(cid)) if cid else (DATA_DIR / "restored"))
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / base
    counter = 1
    while dest.exists():
        dest = dest_dir / ("%s.%d%s" % (Path(base).stem, counter, Path(base).suffix))
        counter += 1
    shutil.move(str(src), str(dest))
    return {
        "name": base,
        "restored_to": str(dest),
        "note": ("已放回 %s。若这是资料原件，请在「资料管理」页确认其登记状态；"
                 "还原**不会**自动重建数据库登记。" % dest_dir.name),
    }


def empty_trash(confirm: bool = False, max_files: int = MAX_BATCH) -> Dict[str, Any]:
    """分批物理清理回收站。**必须显式确认**，单批 ≤ `MAX_BATCH`。

    ★ 这是声明过的删除出口（`check_delete_exits._EXITS["empty_trash"]`）：
      范围**仅** `TRASH_DIR` 内的文件；不触碰 uploads / 数据库 / 报告。
    """
    if not confirm:
        raise TrashError("清空回收站不可撤销，请显式确认（confirm=true）", 409)
    batch = max(1, min(int(max_files or MAX_BATCH), MAX_BATCH))
    removed = empty_trash_batch(batch)
    left = len([p for p in TRASH_DIR.iterdir() if p.is_file()]) if TRASH_DIR.is_dir() else 0
    return {
        "removed": removed,
        "left": left,
        "batch_limit": batch,
        "note": ("已物理清理 %d 个（本批上限 %d）。仍有 %d 个时请再次调用；"
                 "不要一次性清太多 —— 环境守护会因单轮删除过多终止服务。"
                 % (removed, batch, left)),
    }


__all__ = ["TrashError", "company_of", "assert_inside", "listing",
           "restore_one", "empty_trash", "MAX_BATCH"]
