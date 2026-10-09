# -*- coding: utf-8 -*-
"""跨文件引用一致性（Skill D5）—— 薄转发到唯一核心。

职责：① 下游文件引用上游数据时必须**标注来源**；② 上游数据变更时自动列出受影响的下游文件；
③ 下游未同步更新 ⇒ 阻断生成。

机制：`config/doc_consistency.json` 的 `ref_graph` = {上游: 下游列表, 数字}；
判据：该数字的 `claims` 必须覆盖每个下游文件且**实际命中**（未写 = 未标注来源 = ERROR）。
能力：`affected_downstream(上游文件)` 返回受影响下游清单（供"通知"用）。

★ 实现说明：**核心逻辑全部在 `engine/doc_consistency_core.py`**（唯一实现）；
本模块只是该领域判据的**薄转发 + 数据表键名声明** —— 避免 5 个 Skill 各写一遍取数与比对
（本项目铁律：同一概念一处实现）。
"""
from __future__ import annotations

from typing import Any, Dict, List

from engine import doc_consistency_core as core

VERSION = "1.0.0"
CONFIG_PATH = "config/doc_consistency.json"
DATA_KEY = "ref_graph"


def audit() -> List[Dict[str, Any]]:
    """本 Skill 的判据（返回 `[{"level","where","detail"}]`；ERROR = 阻断生成）。"""
    return core.check_ref_graph()


def affected_downstream(upstream_file: str) -> list:
    """上游文件变更 → 受影响的下游文件清单（Skill 5 的"通知"能力）。"""
    return core.affected_downstream(upstream_file)

__all__ = ["VERSION", "CONFIG_PATH", "DATA_KEY", "audit"]
