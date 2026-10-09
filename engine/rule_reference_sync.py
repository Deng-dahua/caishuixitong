# -*- coding: utf-8 -*-
"""规则引用一致性（Skill D2）—— 薄转发到唯一核心。

职责：① 新增/修改一条门禁规则时，扫描所有引用该规则的文件；
② 引用清单 = 规则清单 / 自证段 / 失败样例 / 通过样例 / 回归报告 / 最小检查集 / 修订记录；
③ 任一引用处未同步 ⇒ 阻断生成。

机制：每条规则有唯一编号（`TDS-①`…`TDS-⑨`，见 `rule_catalog`）；
判据两条：**(a) 引用有效性** —— 文档里出现的每个规则编号必须在规则清单里（逐字符校验，
支持「TDS-⑤⑥⑦⑧」这种集合引用）；**(b) 覆盖完整性** —— `rule_catalog_files` 里的文件
必须完整列出全部规则（新增规则后未同步 ⇒ ERROR）。

★ 实现说明：**核心逻辑全部在 `engine/doc_consistency_core.py`**（唯一实现）；
本模块只是该领域判据的**薄转发 + 数据表键名声明** —— 避免 5 个 Skill 各写一遍取数与比对
（本项目铁律：同一概念一处实现）。
"""
from __future__ import annotations

from typing import Any, Dict, List

from engine import doc_consistency_core as core

VERSION = "1.0.0"
CONFIG_PATH = "config/doc_consistency.json"
DATA_KEY = "rules"


def audit() -> List[Dict[str, Any]]:
    """本 Skill 的判据（返回 `[{"level","where","detail"}]`；ERROR = 阻断生成）。"""
    return core.check_rules()


__all__ = ["VERSION", "CONFIG_PATH", "DATA_KEY", "audit"]
