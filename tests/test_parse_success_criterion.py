# -*- coding: utf-8 -*-
"""解析成功判定：**空内容不得判 success**（MQ2-D3）—— 单测 + 端到端线索。

背景（阶段 2 S5-04 实测）：
  · 非财税资料 `.txt` 解析后 `parse_status=success`、`doc_type` 为空；
  · 内容损坏的 `.xlsx` 解析后 `success`，但 `row_count=0`、字段 0。
根因：`parse_document()` 只判 `if not parse_error:` —— **把「无错误」当成了「解析成功」**。

修复：判定收敛为 `extract_service._parse_ok(tables, parse_error)`
      = 「无解析错误」**且**「至少一张表有数据行」。

本文件验：
  ① 判定函数六种边界（空表 / 0 行 / 有行 / 有行但有错 / rows=None / tables=None）；
  ② **反向验证**：旧的"只看 parse_error"写法必须在空内容上给出 True（证明修复点确是它）；
  ③ 端到端线索：`_flow_to_failed` 存在且走状态机合法边（不在函数内自造状态表）。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.extract_service import _parse_ok  # noqa: E402

SRC = (ROOT / "engine" / "extract_service.py").read_text(encoding="utf-8")


def test_empty_tables_is_not_ok() -> None:
    """① 无表 + 无错误 ⇒ **不是**成功（旧实现会判成功 —— 这就是缺陷）。"""
    assert _parse_ok([], "") is False
    assert _parse_ok(None, "") is False


def test_zero_row_table_is_not_ok() -> None:
    """① 有表但 0 行 ⇒ 不是成功（损坏 xlsx 的实际形态）。"""
    assert _parse_ok([{"rows": []}], "") is False
    assert _parse_ok([{"rows": None}], "") is False
    assert _parse_ok([{"rows": []}, {"rows": []}], "") is False


def test_non_empty_rows_is_ok() -> None:
    """① 至少一张表有数据行 ⇒ 成功（**不得误伤正常文件**）。"""
    assert _parse_ok([{"rows": [{"a": 1}]}], "") is True
    assert _parse_ok([{"rows": []}, {"rows": [{"x": 1}]}], "") is True


def test_parse_error_always_not_ok() -> None:
    """① 有解析错误 ⇒ 永不成功，即使碰巧有行。"""
    assert _parse_ok([{"rows": [{"a": 1}]}], "解析器报错") is False
    assert _parse_ok([], "解析器报错") is False


def test_reverse_old_criterion_would_pass() -> None:
    """② **反向验证**：旧判据 `not parse_error` 在两个真实空内容场景上**都判成功**。

    若这里断言失败，说明"只看 parse_error"其实已经能挡住空内容 ⇒ 修复点不在这，
    本文件的 ① 组断言也就失去了意义。
    """
    old = lambda tables, parse_error: not parse_error            # noqa: E731
    assert old([], "") is True, "旧判据在'无表'场景应为 True（缺陷现场）"
    assert old([{"rows": []}], "") is True, "旧判据在'0 行'场景应为 True（缺陷现场）"
    # 而新判据必须把它挡住
    assert _parse_ok([], "") is False
    assert _parse_ok([{"rows": []}], "") is False


def test_replacement_wired_in_parse_document() -> None:
    """③ 判定必须真的**接在** parse_document 上（不是只加了个没人用的函数）。"""
    m = re.search(r"\ndef parse_document\(", SRC)
    assert m, "找不到 parse_document"
    nxt = re.search(r"\ndef [a-z_]+", SRC[m.end():])
    body = SRC[m.start(): m.end() + (nxt.start() if nxt else len(SRC))]
    assert "_parse_ok(tables, parse_error)" in body, "parse_document 未使用 _parse_ok 判定"
    assert "if not parse_error:\n            _flow_to_success" not in body, (
        "parse_document 仍在用「只看 parse_error」的旧判据流转 success")


def test_failed_flow_uses_state_machine() -> None:
    """③ 置 failed 必须走状态机**合法边**（`PARSE_STATUS_FLOW`），不在函数内自造迁移表。"""
    assert "def _flow_to_failed(" in SRC
    seg = SRC[SRC.index("def _flow_to_failed("):]
    seg = seg[: seg.find("\ndef ", 5)]
    assert "PARSE_STATUS_FLOW" in seg, "_flow_to_failed 未引用状态机唯一权威"
    assert "_sps(int(document_id), \"failed\"" in seg, "_flow_to_failed 未真正置 failed"

    from engine.document_types import PARSE_STATUS_FLOW as FLOW
    assert "failed" in FLOW.get("pending", ()), "状态机缺少 pending→failed 合法边"
    assert "failed" in FLOW.get("parsing", ()), "状态机缺少 parsing→failed 合法边"
