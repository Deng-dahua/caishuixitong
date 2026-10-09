# -*- coding: utf-8 -*-
"""文档数字一致性（Skill D1）—— 薄转发到唯一核心 `doc_consistency_core`。

职责：① 文档中每个数字必须有唯一权威来源；② 权威值必须**现算**（脚本/配置实测），不得手抄；
③ 报告生成前校验"文档数字 == 权威值"；④ 不一致时阻断生成（门禁 ERROR）。

唯一权威映射（数据表 `config/doc_consistency.json` 的 `numbers[].authority.kind`）：
  · `config_count`    → `config/*.json` 实测（如 risk_conditions.json 的条数/求和/计数）
  · `pytest_collect`  → `pytest --collect-only` 实测（测试用例数）
  · `file_count`      → `ls docs/第0X批/` 实测（交付物份数）
  · `product_count`   → 全量产物实测（疑点数）
  · `catalog_count`   → 规则清单条数

输入：文档路径 + 数字位置（`claims[].file/regex`）+ 权威源（`authority`）。
输出：逐个数字的一致性结果与不一致清单（`{"level","where","detail"}`）。

★ 实现说明：**核心逻辑全部在 `engine/doc_consistency_core.py`**（唯一实现）；
本模块只是该领域判据的**薄转发 + 数据表键名声明** —— 避免 5 个 Skill 各写一遍取数与比对
（本项目铁律：同一概念一处实现）。
"""
from __future__ import annotations

from typing import Any, Dict, List

from engine import doc_consistency_core as core

VERSION = "1.0.0"
CONFIG_PATH = "config/doc_consistency.json"
DATA_KEY = "numbers"


def audit() -> List[Dict[str, Any]]:
    """本 Skill 的判据（返回 `[{"level","where","detail"}]`；ERROR = 阻断生成）。

    四条：① 每个数字 == 权威值（现算）；② **文档自洽** —— 分项加总 == 合计 == 权威值
    （实测：只抓单值的正则抓不到"分项 31 而合计 28"这类自相矛盾 ⇒ 必须单列判据）；
    ③ **同文件内部自洽** —— 同一指标的多个单值必须相等（实测：`05` §2 写 62.04s 而文末写 214.90s）；
    ④ **元判据** —— 文档里出现的"指标短语 + 数字"必须已被某条 claims 覆盖
    （实测：6 处不一致里 5 处是"**元事实没有权威**"⇒ 写什么都不校验）。
    """
    return (core.check_numbers() + core.check_sums() + core.check_consistency()
            + core.check_meta_coverage() + core.check_deliverable_naming())


__all__ = ["VERSION", "CONFIG_PATH", "DATA_KEY", "audit"]