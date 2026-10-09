# -*- coding: utf-8 -*-
"""全文残留校验（Skill D3）—— 薄转发到唯一核心。

职责：① grep 关键词必须覆盖所有可能写法；② 维护**同义写法词典**（`config/doc_synonyms.json`）；
③ 检索时自动展开为全部变体；④ 未在词典中的写法 ⇒ 记为校验漏洞（WARN，要求补词典）。

词典示例（本批实际登记）：「25 例 / 25例 / 25 passed / 25tests / 25 用例」；
「8 条规则 / 8 条门禁 / 门禁 8 条」；「55.94s / 55.94 秒」。
⚠ 区间/并列形态（「55.94–86.36s」）**不算残留**（允许的浮动区间写法）。
输出：展开后的 grep 命令（`expand_grep()`）+ 残留清单。

★ 实现说明：**核心逻辑全部在 `engine/doc_consistency_core.py`**（唯一实现）；
本模块只是该领域判据的**薄转发 + 数据表键名声明** —— 避免 5 个 Skill 各写一遍取数与比对
（本项目铁律：同一概念一处实现）。
"""
from __future__ import annotations

from typing import Any, Dict, List

from engine import doc_consistency_core as core

VERSION = "1.0.0"
CONFIG_PATH = "config/doc_consistency.json"
DATA_KEY = "residue"


def audit() -> List[Dict[str, Any]]:
    """本 Skill 的判据（返回 `[{"level","where","detail"}]`；ERROR = 阻断生成）。"""
    return core.check_residue() + core.check_snapshot_records()


def expand_grep(stale_id: str = "") -> str:
    """输出**展开同义写法**后的 grep 命令（Skill 3 的输出要求：展开后命令 + 残留清单）。"""
    syn = core.synonyms()
    items = [s for s in (syn.get("stale_values") or []) if isinstance(s, dict)]
    if stale_id:
        items = [s for s in items if str(s.get("id")) == stale_id]
    globs = " ".join(str(g) for g in ((syn.get("scan_scope") or {}).get("include_globs") or []))
    pats = ["、".join(str(v) for v in (s.get("variants") or [])) for s in items]
    return "grep -rnE \"%s\" %s" % ("|".join("(%s)" % p for p in pats if p), globs)

__all__ = ["VERSION", "CONFIG_PATH", "DATA_KEY", "audit"]
