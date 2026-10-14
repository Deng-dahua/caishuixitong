# -*- coding: utf-8 -*-
"""报告载荷（`company_{cid}_full.json`）的**读写路径唯一权威**。

## 为什么需要它（2026-10-14，收口批次 S12-DEC-002）

一键分析产出报告后，**服务自身从不落盘**该载荷 —— 全仓只有离线脚本
`scripts/_rerun_company1.py` 会写。实测后果：

| 判据 | 结论 |
|---|---|
| 写入方 | **生产代码 0 处**（仅离线脚本 1 处） |
| 读取方 | `engine/risk_service.py` · `rules_api.py` 等 —— 即 P0-5/P0-6 的**唯一数据源** |
| 反向验证 | 按读取方期望形状写入 ⇒ `available` 立即变 `True` ⇒ **断点是「没人写」，不是「路径错」** |

⇒ 换任何账套 ⇒ 风险页/复核/规则页**立即为空**；删除该文件 ⇒ 永久为空；
隔离实例（设 `APP_DATA_DIR`）⇒ 必然为空。本模块把「路径 + 落盘」收敛为**唯一实现**，
由服务链路（`main._persist_one_click_result`）与离线脚本共用。

## 不变量（不得各自再写一份）

1. **路径唯一**：目录取 `runtime_storage.offline_reports_root()`（跟随 `APP_DATA_DIR` 隔离，
   不写死产物目录 —— 写死会在隔离实例里越界读/写生产产物）。
2. **落盘唯一**：`runtime_storage.atomic_write_json`（fsync + 原子替换）。
3. **落盘不抛异常**：返回结构体 `{"ok": bool, ...}`。理由 —— 落盘失败**不得**把
   已成功的分析判为失败（与 `_persist_one_click_result` 的"写回失败不影响结果"同一口径）。
4. **不写空载荷**：`report` 为空/非 dict ⇒ 拒绝落盘（避免把正式产物截成空文件，
   与 2026-10-06 事故同源）。

## 与读取方的关系

`engine/risk_service.load_payload()` 的路径**薄转发**到本模块 `payload_path()`，
⇒ 读写两侧同一份字面量，不会各自漂移。
"""
from __future__ import annotations

import os
from typing import Any, Dict

__all__ = ["PAYLOAD_SUFFIX", "payload_filename", "payload_path", "dump_payload"]

#: 载荷文件名模板 —— **全仓唯一字面量处**（读取方经 `payload_path()` 复用）
PAYLOAD_SUFFIX = "company_%d_full.json"


def payload_filename(company_id: Any) -> str:
    """载荷**文件名**（不含目录）。"""
    return PAYLOAD_SUFFIX % int(company_id)


def payload_path(company_id: Any) -> str:
    """载荷**绝对路径**唯一权威。

    目录取 `offline_reports_root()` —— 该函数明确要求派生物目录跟随
    `APP_DATA_DIR`，故在**调用时**解析（模块 import 期环境变量可能尚未设置）。
    """
    from runtime_storage import offline_reports_root      # noqa: PLC0415
    return os.path.join(offline_reports_root(), payload_filename(company_id))


def dump_payload(company_id: Any, report: Any, *, indent: int = 1) -> Dict[str, Any]:
    """把报告载荷**原子落盘**；异常**不外抛**。

    返回：`{"ok": True, "path": str, "bytes": int}` 或 `{"ok": False, "error": str}`。
    """
    if not isinstance(report, dict) or not report:
        return {"ok": False, "error": "载荷为空或非 dict，拒绝落盘（不写空文件）"}
    try:
        from runtime_storage import atomic_write_json     # noqa: PLC0415
        path = payload_path(company_id)
        atomic_write_json(path, report, indent=indent)
        try:
            size = os.path.getsize(path)
        except OSError:
            size = -1
        return {"ok": True, "path": path, "bytes": size}
    except Exception as exc:                              # noqa: BLE001
        return {"ok": False, "error": str(exc)}
