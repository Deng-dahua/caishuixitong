# -*- coding: utf-8 -*-
"""未完成事项状态同步（Skill D4）—— 薄转发到唯一核心。

职责：① 未完成清单每一项必须有状态字段；② 状态 ∈ 未开始/进行中/已修复/待决策/不阻断；
③ 补做完成后状态自动同步；④ 状态未同步 ⇒ 阻断生成。

机制：每项唯一 ID（U1…Un）；「补做记录」里写「U1 已修复」时，
未完成清单里 U1 的状态必须已是「已修复」，否则 ERROR（双向一致）。

★ 实现说明：**核心逻辑全部在 `engine/doc_consistency_core.py`**（唯一实现）；
本模块只是该领域判据的**薄转发 + 数据表键名声明** —— 避免 5 个 Skill 各写一遍取数与比对
（本项目铁律：同一概念一处实现）。
"""
from __future__ import annotations

from typing import Any, Dict, List

from engine import doc_consistency_core as core

VERSION = "1.0.0"
CONFIG_PATH = "config/doc_consistency.json"
DATA_KEY = "todo"


def audit() -> List[Dict[str, Any]]:
    """本 Skill 的判据（返回 `[{"level","where","detail"}]`；ERROR = 阻断生成）。

    两条：① 未完成清单每项必须有状态，且与「状态同步声明」一致；
    ② **文档结构自洽** —— 同一表格每行列数必须等于表头列数
    （实测：`08` 表头 5 列 / 数据 6 列 ⇒ 渲染整体串列，Markdown 与任何语法检查都不报）。
    """
    return core.check_todo_status() + core.check_tables()


def sync_status(completed_ids=()) -> dict:
    """补做完成后把状态同步进未完成清单（Skill 4 的"自动更新"能力）。

    返回 `{id: {"from": 旧状态, "to": "已修复"}}`；**只报告应改项**，改动由文档维护者确认
    （本 Skill 不替人改文档：清单里还有"原因/需要什么输入"等人工内容，自动改写有风险）。
    """
    todos = core.parse_todo_table()
    out = {}
    for tid in completed_ids:
        cur = str((todos.get(str(tid)) or {}).get("状态") or "")
        if cur and cur != "已修复":
            out[str(tid)] = {"from": cur, "to": "已修复"}
    return out

__all__ = ["VERSION", "CONFIG_PATH", "DATA_KEY", "audit"]
