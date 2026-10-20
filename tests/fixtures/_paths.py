# -*- coding: utf-8 -*-
"""测试夹具（fixtures）路径的**单一权威**（2026-10-20 建立）。

## 为什么必须建它（实测事故，非设想）
2026-10-20 用户拍板清理 10-17 事故遗留的 company 1 幽灵账套 ⇒ 唯一权威
`main.purge_company_analysis_artifacts` 按「删除账套 = 真删干净」铁律清掉了
`scripts/four_reports/company_1_*.json`。结果 **33 项测试变红** —— 因为
**16 个测试套件硬编码依赖**该运行时产物目录：

    ROOT / "scripts" / "four_reports" / "company_1_full.json"

## 病根（架构坏味道）
`scripts/four_reports/` 是**生产运行时产物目录**（`runtime_storage.
offline_reports_root()` 管辖，且 `.gitignore` 已忽略），它会：
  · 随「删除账套」被清理（本次正是）；
  · 被其他运维动作清空；
  · 在**全新克隆的仓库**里根本不存在（gitignore）。
而测试却把它当成**夹具库** ⇒ 二者耦合，任何清理/新克隆都会让大批测试红。
这正是「判据不得依赖可变的运行时状态」的反面教材。

## 修法（用户 2026-10-20 选定：迁入 fixtures）
把这个样本**固化进版本库**：`tests/fixtures/company_1_full.json`
（35MB，`total_risks=24`，即清理前磁盘上那一版；来源 = `data/trash/`
里 36163599 字节那一份），并让所有测试**只从本模块取路径** ——
从此测试样本与生产目录**解耦**，清账套、新克隆都不再影响测试。

## 口径
  · `fixture_path(name)`：返回 `tests/fixtures/<name>`（唯一构造点）；
  · `offline_report(name="company_1_full.json")`：便捷取全量分析产物夹具；
  · 缺文件 ⇒ **明确抛错**（不静默返回空 ⇒ 否则又是"夹具没了测试假绿"）。
"""
from __future__ import annotations

from pathlib import Path

#: 夹具根目录（唯一权威）
FIXTURES = Path(__file__).resolve().parent


def fixture_path(name: str) -> Path:
    """取夹具文件的绝对路径；不存在 ⇒ 明确抛 `FileNotFoundError`。

    ★ 不返回 `None`、不返回空路径 —— 夹具缺失必须让测试**报错**，
      而不是变成"读到空数据 ⇒ 断言恒真 ⇒ 假绿"。
    """
    p = FIXTURES / str(name)
    if not p.is_file():
        raise FileNotFoundError(
            "测试夹具缺失：%s\n"
            "（夹具是版本库内固化的样本，不应缺失；若确需更新，见 "
            "tests/fixtures/README.md 的刷新口径）" % p)
    return p


def offline_report(name: str = "company_1_full.json") -> Path:
    """离线分析产物夹具（真实 `company_1_full.json` 的固化快照）。"""
    return fixture_path(name)