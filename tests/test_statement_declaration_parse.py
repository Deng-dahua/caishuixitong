# -*- coding: utf-8 -*-
"""GAP-15 报表 / 申报表结构化（2026-10-18）。

原差距：资产负债表被判 `expense_detail`（本轮实测同源问题：被判 `invoice`）；
12 份增值税申报表 PDF 共 55 行、**0 个标准字段**。

三条根因（都在"结构化"这一层）：
  ① 结构模式表**没有报表模式** ⇒ 结构阶段只能瞎猜（invoice 85%），
     再被交叉验证"默认信任结构"覆写成错的；
  ② 表格画像里**两处独立剔除"合计/小计"行**（采样一处、计数一处，口径不一致），
     而财务报表的核心行恰恰就是「资产总计/负债合计」⇒ total_rows 剩 2 行，
     报表模式因 min_rows 被直接排除；
  ③ 报表的**字段名在单元格值里**（"资产总计"），不在列名上 ⇒ 通用解析取不到；
     横向双栏还会把左右两组金额**错配**（货币资金 1,250,000 变成短期借款 300,000）。

修复：
  · `_STRUCTURAL_PATTERNS` 增 `financial_statement`（与科目余额表靠 `has_code` 硬分流）；
  · 表格画像的采样与计数**统一为同一把尺**（不再剔汇总行，交给具体解析器）；
  · `extract_service._pivot_statement_sheet` 把纵向/横向双栏报表透视成
    `{报表项目名: 金额}` 一行；
  · `extract_service._extract_declaration_lines` 按**行次**（`config/declaration_lines.json`
    唯一权威）抽申报表，且只从**主表页**抽（附列资料页行次与主表撞号）。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine.extract_service import (                                  # noqa: E402
    _declaration_specs, _extract_declaration_lines, _parse_file,
    _registered_names, STATEMENT_TYPES)
from engine.standard_fields import value_from_row                     # noqa: E402


def _xlsx(rows, name):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    p = os.path.join(tempfile.mkdtemp(prefix="gap15_"), name)
    wb.save(p)
    return p


BS_HORIZONTAL = [
    ["资产", "期末余额", "年初余额", "负债和所有者权益", "期末余额", "年初余额"],
    ["货币资金", 1250000.00, 980000.00, "短期借款", 300000.00, 300000.00],
    ["应收账款", 2400000.00, 2100000.00, "应付账款", 1800000.00, 1600000.00],
    ["存货", 1500000.00, 1400000.00, "负债合计", 2100000.00, 1900000.00],
    ["资产总计", 5150000.00, 4480000.00, "所有者权益合计", 3050000.00, 2580000.00],
]
BS_VERTICAL = [
    ["项目", "行次", "期末余额", "年初余额"],
    ["货币资金", 1, 1250000.00, 980000.00],
    ["应收账款", 4, 2400000.00, 2100000.00],
    ["资产总计", 30, 5150000.00, 4480000.00],
    ["负债合计", 45, 2100000.00, 1900000.00],
    ["所有者权益合计", 60, 3050000.00, 2580000.00],
]
IS_VERTICAL = [
    ["项目", "行次", "本期金额", "上期金额"],
    ["一、营业收入", 1, 8000000.00, 7200000.00],
    ["减：营业成本", 2, 5000000.00, 4600000.00],
    ["四、净利润", 30, 1487500.00, 1258000.00],
]
TB = [
    ["科目编码", "科目名称", "期初借方", "期初贷方", "本期借方", "本期贷方", "期末借方", "期末贷方"],
    ["1001", "库存现金", 1000, 0, 500, 200, 1300, 0],
    ["6401", "主营业务成本", 0, 0, 60000, 0, 60000, 0],
]


def _first(path, ext=".xlsx"):
    tables, err = _parse_file(path, ext, os.path.basename(path))
    assert tables, "未产出任何表（err=%r）" % err
    t = tables[0]
    rows = t.get("rows") or [{}]
    got = {n: value_from_row(n, rows[0]) for n in _registered_names(rows, t.get("doc_type"))}
    return t, got


class StatementRecognitionTests(unittest.TestCase):
    """① 类型识别：报表必须判成报表，且科目余额表不被抢走。"""

    def test_balance_sheet_horizontal_is_statement(self):
        t, _ = _first(_xlsx(BS_HORIZONTAL, "资产负债表2024.xlsx"))
        self.assertEqual(t.get("doc_type"), "financial_statement", t.get("doc_type"))

    def test_balance_sheet_vertical_is_statement(self):
        t, _ = _first(_xlsx(BS_VERTICAL, "资产负债表_纵向.xlsx"))
        self.assertEqual(t.get("doc_type"), "financial_statement", t.get("doc_type"))

    def test_income_statement_is_statement(self):
        t, _ = _first(_xlsx(IS_VERTICAL, "利润表2024.xlsx"))
        self.assertEqual(t.get("doc_type"), "financial_statement", t.get("doc_type"))

    def test_trial_balance_not_taken_by_statement_pattern(self):
        """反例：科目余额表有"科目编码"列 ⇒ 不得被报表模式抢走（靠 has_code 硬分流）。"""
        t, got = _first(_xlsx(TB, "科目余额表2024.xlsx"))
        self.assertEqual(t.get("doc_type"), "trial_balance", t.get("doc_type"))
        self.assertEqual(got.get("account_code"), "1001")


class StatementPivotTests(unittest.TestCase):
    """② 报表取数：三个关键数必须**数值正确**，且勾稽成立。"""

    def test_horizontal_amounts_not_crossed(self):
        """横向双栏曾把左组金额配到右组项目上（货币资金→短期借款）⇒ 现在必须各就各位。"""
        t, got = _first(_xlsx(BS_HORIZONTAL, "资产负债表2024.xlsx"))
        self.assertEqual(t.get("source"), "statement-pivot")
        self.assertEqual(got.get("total_assets"), 5150000.0)
        self.assertEqual(got.get("total_liabilities"), 2100000.0)
        self.assertEqual(got.get("total_equity"), 3050000.0)
        # 勾稽：资产 = 负债 + 所有者权益（报表自身必须平）
        self.assertAlmostEqual(got["total_assets"],
                               got["total_liabilities"] + got["total_equity"], places=2)

    def test_vertical_ordinal_column_not_taken_as_amount(self):
        """纵向报表有「行次」列（1/4/30/45/60）；若被当金额取走，
        total_assets 会变成 30 而不是 5,150,000 —— 这是必须挡住的具体错法。"""
        _, got = _first(_xlsx(BS_VERTICAL, "资产负债表_纵向.xlsx"))
        self.assertEqual(got.get("total_assets"), 5150000.0)
        self.assertEqual(got.get("total_liabilities"), 2100000.0)
        self.assertEqual(got.get("total_equity"), 3050000.0)
        self.assertNotEqual(got.get("total_assets"), 30.0)

    def test_income_statement_fields(self):
        _, got = _first(_xlsx(IS_VERTICAL, "利润表2024.xlsx"))
        self.assertEqual(got.get("revenue"), 8000000.0)
        self.assertEqual(got.get("cost"), 5000000.0)
        self.assertEqual(got.get("net_profit"), 1487500.0)


class DeclarationLinesTests(unittest.TestCase):
    """③ 申报表：按**行次**抽，认不出表种/行次不猜。"""

    SPEC_TEXT = "\n".join([
        "项 目 栏次 本月数 本年累计",
        "（一）按适用税率计税销售额 1 245,827.02 245,827.02 0.00 0.00",
        "销项税额 11 14,749.62 14,749.62 0.00 0.00",
        "进项税额 12 12,686.10 12,686.10 0.00 0.00",
        "应抵扣税额合计 17=12+13-14-15+16 12,686.10 —— 0.00 ——",
        "应纳税额 19=11-18 2,063.52 2,063.52 0.00 0.00",
        "期末留抵税额 20=17-18 0.00 0.00 0.00 ——",
    ])

    def _spec(self):
        specs = _declaration_specs()
        self.assertIn("vat_general", specs, "行次映射表缺失 vat_general")
        return specs["vat_general"]

    def test_lines_extracted_by_line_number(self):
        out = _extract_declaration_lines(self.SPEC_TEXT, self._spec(), "vat_general")
        self.assertIsNotNone(out)
        row = out["rows"][0]
        self.assertEqual(row.get("taxable_amount"), 245827.02)
        self.assertEqual(row.get("output_tax"), 14749.62)
        self.assertEqual(row.get("input_tax"), 12686.10)
        self.assertEqual(row.get("tax_payable"), 2063.52)
        self.assertEqual(row.get("credit_carryforward"), 0.0)
        # 17 行带公式「=12+13-14-15+16」也必须能取到
        self.assertEqual(row.get("deductible_total"), 12686.10)
        # 字段数（不含中文别键）
        self.assertGreaterEqual(len([k for k in row if not any(
            "\u4e00" <= c <= "\u9fff" for c in k)]), 6)

    def test_tax_type_filled_from_spec(self):
        """申报域 `tax_type` 是必填项；由表种直接确定，不从正文猜。"""
        row = _extract_declaration_lines(self.SPEC_TEXT, self._spec(), "vat_general")["rows"][0]
        self.assertEqual(row.get("tax_type"), "增值税")

    def test_line_not_in_map_is_skipped_not_guessed(self):
        """行次 99 不在映射表 ⇒ 跳过（**不按项目名猜字段**）。"""
        txt = "某个不在表里的项目 99 12345.67 12345.67"
        self.assertIsNone(_extract_declaration_lines(txt, self._spec(), "vat_general"))

    def test_label_mismatch_is_recorded(self):
        """行次对、项目名不对 ⇒ 仍按行次取值，但**如实记录**不一致（不静默）。"""
        txt = "完全无关的名称 11 100.00 100.00"
        out = _extract_declaration_lines(txt, self._spec(), "vat_general")
        self.assertEqual(out["rows"][0].get("output_tax"), 100.0)
        self.assertEqual(len(out["_declaration"]["label_mismatch"]), 1)

    def test_config_is_the_only_authority(self):
        """行次映射必须来自配置文件（不得在代码里写死行次含义）。"""
        self.assertTrue(os.path.exists(
            os.path.join(ROOT, "config", "declaration_lines.json")))
        specs = _declaration_specs()
        self.assertIn("lines", specs["vat_general"])
        self.assertIn("11", specs["vat_general"]["lines"])
        self.assertEqual(specs["vat_general"]["lines"]["11"]["field"], "output_tax")


_REAL_PDF = os.path.join(
    ROOT, "data", "uploads", "1",
    "1_103_增值税及附加税费申报表_一般纳税人适用_2025-01-01-2025-01-31_.pdf")


class DeclarationRealPdfTests(unittest.TestCase):
    """④ 真实申报表 PDF（`data/` 不入库，缺失则跳过并如实说明）。"""

    def test_real_vat_pdf_yields_fields(self):
        if not os.path.exists(_REAL_PDF):
            self.skipTest("真实申报表样例不存在（data/ 不入库）：%s" % _REAL_PDF)
        tables, err = _parse_file(_REAL_PDF, ".pdf", os.path.basename(_REAL_PDF))
        self.assertTrue(tables, err)
        t = tables[0]
        self.assertEqual(t.get("doc_type"), "vat_declaration")
        self.assertEqual(t.get("source"), "declaration-lines")
        row = t["rows"][0]
        self.assertEqual(row.get("tax_type"), "增值税")
        self.assertEqual(row.get("output_tax"), 14749.62)
        self.assertEqual(row.get("input_tax"), 12686.10)
        self.assertEqual(row.get("tax_payable"), 2063.52)
        # 附列资料页与主表行次撞号 ⇒ 必须已被"只抽主表页"挡掉
        decl = t.get("_declaration") or {}
        self.assertEqual(decl.get("label_mismatch"), [], decl.get("label_mismatch"))
        self.assertLess(decl.get("main_pages") or 0, decl.get("pages") or 0,
                        "主表页过滤未生效：%s" % decl)


class StatementTypesContractTests(unittest.TestCase):
    def test_statement_types_declared(self):
        for t in ("financial_statement", "financial_statements", "balance_sheet",
                  "income_statement", "cash_flow_statement", "equity_statement"):
            self.assertIn(t, STATEMENT_TYPES)


if __name__ == "__main__":
    unittest.main()
