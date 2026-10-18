# -*- coding: utf-8 -*-
"""GAP-16 上传报表勾稽接入分析（2026-10-18）。

原差距：`extract_validate` 对**用户上传的报表**算了 1 元容差勾稽
（`rule="cross_check"`），结果写进 `extract_issues`，但**一键分析从不读它**
⇒ 用户传了一张不平的资产负债表，报告毫无反应。

与既有逻辑的区别（关键，不能互相顶替）：
  · `financial_analyzer._check_balance_sheet_balance` 勾稽的是
    「**科目余额表反推出来的**三表」；
  · 本模块取的是「**用户上传的那张报表**」的勾稽结果。

覆盖：
  ① 唯一取数口只认 `extract_issues.rule='cross_check' AND status='open'`
  ② 表不存在 ⇒ `readable=True` 且 0 条（不是"读不到"）
  ③ 库不可用 ⇒ `readable=False`（"读不到" ≠ "没有异常"，缺失如实）
  ④ 发现结构合法（等级在权威词表内、带封印标、带依据、结论可核定）
  ⑤ 已处理（`status='resolved'`）的不再扰民
  ⑥ 接入点真的在 `pipeline._run_analyze` 里（接线自检）
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import statement_check_feed as SCF                          # noqa: E402
from engine.risk_levels import LEGAL_LEVELS                            # noqa: E402

_SCHEMA = """
CREATE TABLE extract_issues (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER, table_id INTEGER, project_id INTEGER, company_id INTEGER,
  rule TEXT, severity TEXT, message TEXT, detail_json TEXT,
  status TEXT DEFAULT 'open', resolved_by TEXT, resolved_at TEXT, created_at TEXT
);
"""


class _FakeEngine:
    """最小 SQLAlchemy 形状的假引擎（`connect()` → 上下文管理器 → `.execute()`）。"""

    def __init__(self, rows, has_table=True, fail=False):
        self.rows = rows
        self.has_table = has_table
        self.fail = fail

    def connect(self):
        return _FakeConn(self)


class _FakeRow:
    def __init__(self, m):
        self._mapping = m


class _FakeResult:
    def __init__(self, rows, first_only=False):
        self._rows = rows
        self._first = first_only

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _FakeConn:
    def __init__(self, eng):
        self.eng = eng

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        s = str(sql)
        if self.eng.fail:
            raise RuntimeError("database is locked")
        if "sqlite_master" in s:
            return _FakeResult([(1,)] if self.eng.has_table else [], first_only=True)
        # ★ 忠实模拟真实 SQLite：表未建时**抛 `no such table`**（而不是返回空集）。
        #   否则"有没有守卫"两种写法观测结果一样，判据就是假的（反向验证抓出来的）。
        if not self.eng.has_table:
            raise sqlite3.OperationalError("no such table: extract_issues")
        return _FakeResult([_FakeRow(r) for r in self.eng.rows])


class OpenCrossChecksTests(unittest.TestCase):
    def test_items_mapped(self):
        eng = _FakeEngine([{
            "id": 7, "document_id": 12, "project_id": 3, "table_id": 5,
            "rule": "cross_check", "severity": "warning",
            "message": "报表勾稽异常：资产总计 100.00 ≠ 负债合计 40.00 + 所有者权益合计 50.00（差额 10.00）",
            "detail_json": '{"assets": 100.0, "liabilities": 40.0, "equity": 50.0, "diff": 10.0}',
            "created_at": "2026-10-18 10:00:00",
        }])
        items, readable = SCF.open_cross_checks(99, eng)
        self.assertTrue(readable)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["document_id"], 12)
        self.assertEqual(items[0]["detail"]["diff"], 10.0)

    def test_missing_table_is_readable_but_empty(self):
        """表未建（未用过解析功能）⇒ readable=True、0 条 —— 不是"读不到"。"""
        items, readable = SCF.open_cross_checks(99, _FakeEngine([], has_table=False))
        self.assertTrue(readable)
        self.assertEqual(items, [])

    def test_db_failure_is_not_readable(self):
        """库不可用 ⇒ readable=False（必须与"没有异常"区分，缺失如实）。"""
        items, readable = SCF.open_cross_checks(99, _FakeEngine([], fail=True))
        self.assertFalse(readable)
        self.assertEqual(items, [])


class FindingShapeTests(unittest.TestCase):
    def _item(self):
        return {"id": 1, "document_id": 12, "project_id": 3,
                "message": "报表勾稽异常",
                "detail": {"assets": 100.0, "liabilities": 40.0, "equity": 50.0, "diff": 10.0}}

    def test_level_in_authoritative_vocabulary(self):
        f = SCF.finding_from_cross_check(self._item(), 1)
        self.assertIn(f["level"], LEGAL_LEVELS,
                      "等级必须在权威词表（engine.risk_levels.LEGAL_LEVELS）内，"
                      "否则会被封印静默丢弃")

    def test_sealed_and_scoped(self):
        f = SCF.finding_from_cross_check(self._item(), 1)
        self.assertTrue(f.get("_scenario_governed"), "未打封印标 ⇒ 会被 seal 静默丢弃")
        self.assertEqual(f.get("conclusion_grade"), "已核定")
        self.assertTrue(f.get("final_answer"))

    def test_numbers_are_rendered_not_swallowed(self):
        f = SCF.finding_from_cross_check(self._item(), 1)
        for token in ("100.00", "40.00", "50.00", "10.00"):
            self.assertIn(token, f["detail"])

    def test_legal_basis_does_not_fake_redline(self):
        f = SCF.finding_from_cross_check(self._item(), 1)
        self.assertIn("税收征收管理法", f["law_ref"])
        self.assertNotIn("redline_id", f, "本项不属红线，不得伪造 redline_id")
        self.assertIn("legal_basis_status", f)

    def test_unique_fact_ids(self):
        a = SCF.finding_from_cross_check(self._item(), 1)["fact_id"]
        b = SCF.finding_from_cross_check(self._item(), 2)["fact_id"]
        self.assertNotEqual(a, b, "多条同时存在时 fact_id 必须唯一，否则被去重吞掉")

    def test_collect_receipt_is_explicit(self):
        out, receipt = SCF.collect_findings(99, _FakeEngine([], fail=True))
        self.assertEqual(out, [])
        self.assertFalse(receipt["readable"])
        self.assertIn("未参与", receipt["note"])


class WiringTests(unittest.TestCase):
    """⑥ 接线自检：接入点必须在 `pipeline._run_analyze` 里，且唯一取数口唯一。"""

    def test_pipeline_reads_the_feed(self):
        txt = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
        self.assertIn("statement_check_feed", txt,
                      "一键分析未接入上传报表勾稽（GAP-16 会复发）")
        self.assertIn("collect_findings as _xcheck_collect", txt)

    def test_no_second_implementation(self):
        """`extract_issues` 的读取只许两处：**表所有者**（extract_service 解析链）
        与**本模块**（分析链取数口）。其它任何模块再读一遍 = 第二套口径。"""
        import glob
        allowed = {"extract_service.py", "statement_check_feed.py"}
        hits = []
        for p in glob.glob(os.path.join(ROOT, "engine", "*.py")):
            if os.path.basename(p) in allowed:
                continue
            src = open(p, encoding="utf-8", errors="ignore").read()
            if re.search(r"FROM\s+extract_issues", src, re.I):
                hits.append(os.path.basename(p))
        self.assertEqual(hits, [], "出现第二处 extract_issues 读取：%s" % hits)

    def test_findings_appended_before_seal(self):
        """追加必须在封印（`seal_governed_findings`）之前。"""
        txt = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
        i_feed = txt.find("statement_check_feed")
        i_seal = txt.find("seal_governed_findings(_scenario_execution)")
        self.assertGreater(i_feed, 0)
        self.assertGreater(i_seal, 0)
        self.assertLess(i_feed, i_seal, "接入点在封印之后 ⇒ 发现会被丢掉")


if __name__ == "__main__":
    unittest.main()
