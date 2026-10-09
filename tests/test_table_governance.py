# -*- coding: utf-8 -*-
"""**表格治理**的测试（`engine/table_governance`）。

背景（2026-09-29 点评整改 P1-14 + 2026-10-06 顺序缺陷）：企业版报告里所有明细表的
唯一规范化点。立项要修的三类静默缺陷：
  ① 列名与行键**仅标点不同**（半/全角括号）→ 渲染层按列名取值取不到 → **整列空白**；
  ② **内部列**（`_id`/`_key`/`trace_id`）外泄成正式列；
  ③ **截断不注明** → 读者把列示行当全部行 → 与合计对不上。

2026-10-06 追加事故：该规范化点原先只在**报告构造那一刻**执行，
而「并入独立风险事项」「询问主题挂载」都在其**之后**追加内容
⇒ 后追加的表从未过治理，三类缺陷全部复发。修法＝**终局收口**。
"""
from __future__ import annotations

import inspect


class TestAlignTable:
    def test_punct_only_column_mismatch_is_aligned(self):
        from engine.table_governance import align_table
        t = {"columns": ["金额（元）"], "rows": [{"金额(元)": "1,000.00"}]}
        out = align_table(t)
        assert out["columns"] == ["金额（元）"], out["columns"]
        assert out["rows"][0]["金额（元）"] == "1,000.00", "对齐后取值必须取得到"

    def test_internal_columns_removed(self):
        from engine.table_governance import align_table
        t = {"columns": ["金额（元）", "trace_id", "_key"],
             "rows": [{"金额（元）": 1, "trace_id": "T1", "_key": "k"}]}
        out = align_table(t)
        assert "trace_id" not in out["columns"] and "_key" not in out["columns"]
        assert all(k not in ("trace_id", "_key") for k in out["rows"][0])

    def test_empty_named_column_removed(self):
        """空表头（列名为空/纯空白）不得作为正式列渲染。"""
        from engine.table_governance import align_table, is_internal_col
        assert is_internal_col("") and is_internal_col("   ")
        t = {"columns": ["金额（元）", ""], "rows": [{"金额（元）": 1, "": "x"}]}
        out = align_table(t)
        assert "" not in out["columns"], out["columns"]

    def test_truncation_noted(self):
        from engine.table_governance import align_table
        t = {"columns": ["A"], "rows": [{"A": 1}], "rows_total": 5}
        out = align_table(t)
        assert out.get("truncation_note"), "声明 5 行却只列 1 行必须注明截断"

    def test_title_count_rewritten_to_actual_rows(self):
        from engine.table_governance import align_table
        t = {"columns": ["A"], "rows": [{"A": 1}], "rows_total": 5,
             "title": "明细（共7笔）"}
        out = align_table(t)
        assert "（共7笔）" not in out["title"], out["title"]
        assert "此处列示前1" in out["title"], out["title"]

    def test_idempotent(self):
        from engine.table_governance import align_table
        t = {"columns": ["金额（元）", "trace_id"],
             "rows": [{"金额(元)": 1, "trace_id": "T"}], "rows_total": 3}
        a = align_table(t)
        b = align_table(a)
        assert a["columns"] == b["columns"]
        assert a.get("truncation_note") == b.get("truncation_note")

    def test_extra_row_keys_kept_as_columns(self):
        """反向锁：行里多出的键不得被删（不丢信息），应追加为列。"""
        from engine.table_governance import align_table
        t = {"columns": ["A"], "rows": [{"A": 1, "备注": "x"}]}
        out = align_table(t)
        assert "备注" in out["columns"], out["columns"]
        assert out["rows"][0]["备注"] == "x"


class TestTerminalGovernance:
    """★ 2026-10-06 顺序缺陷：治理必须在**报告定稿处**再收口一次。"""

    def test_builder_governs_after_all_appends(self):
        from engine import enterprise_report as ER
        src = inspect.getsource(ER)
        # 报告构造器源码中，`govern_all_tables` 必须出现≥2 次（构造时 + 终局收口）
        assert src.count("govern_all_tables") >= 2, \
            "表格治理未终局收口（后追加的明细表将不过治理）"
        # 且最后一次调用必须位于并入/挂载之后
        last = src.rfind("govern_all_tables")
        for anchor in ("_promote_standalone_to_problems", "attach_question_themes"):
            assert src.rfind(anchor) < last, \
                "`govern_all_tables` 的最后一次调用早于 `%s`" % anchor

    def test_govern_all_tables_recurses_and_is_cycle_safe(self):
        from engine.table_governance import govern_all_tables
        t = {"columns": ["A"], "rows": [{"A": 1}]}
        obj = {"deep": [{"t": t}]}
        obj["deep"][0]["self"] = obj            # 故意造环
        out = govern_all_tables(obj)
        assert out["deep"][0]["t"]["columns"] == ["A"]
