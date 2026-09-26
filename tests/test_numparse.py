"""统一数值解析（engine/numparse.py）回归测试。

★ 这组测试直接对应「按适用所有行业和企业的解决方法」的要求：
  不论哪个模块、哪类企业，**同一段金额文本必须解析出同一个数**。
  （历史事故：同一张发票的金额，域分析算出 12000、规则引擎算出 0。）
"""
import unittest

from engine.numparse import (
    AMOUNT_KEYS, amount_of, first_amount, parse_ratio, sum_field,
    to_number, to_number_checked,
)

# 真实税务数据里常见的"难缠"金额写法
CASES = [
    ("12,000.00", 12000.0),
    ("￥1,234.56", 1234.56),
    ("1,234.56元", 1234.56),
    ("  12,000.00  ", 12000.0),
    ("１２３４．５６", 1234.56),          # 全角
    ("(1,234.00)", -1234.0),             # 会计式负数
    ("（2,000）", -2000.0),
    ("1.2万", 12000.0),                  # 中文数量级
    ("3亿", 300000000.0),
    ("金额:12000.00", 12000.0),           # 带前缀
    ("6%", 6.0),                         # 百分号按数值（比例请用 parse_ratio）
    ("0", 0.0),
    ("0.00", 0.0),
    (1234.5, 1234.5),
    (-99, -99.0),
]
NULLS = [None, "", "   ", "-", "--", "——", "/", "无", "nan", "N/A"]


class TestToNumber(unittest.TestCase):
    def test_common_formats(self):
        for raw, expect in CASES:
            with self.subTest(raw=raw):
                self.assertAlmostEqual(to_number(raw), expect, places=4)

    def test_nulls_return_default(self):
        for raw in NULLS:
            with self.subTest(raw=raw):
                self.assertEqual(to_number(raw), 0.0)
                self.assertEqual(to_number(raw, default=-1.0), -1.0)

    def test_never_raises(self):
        for weird in [object(), [], {}, b"12", "abc", "None", float("nan"), float("inf")]:
            try:
                to_number(weird)
            except Exception as e:  # noqa: BLE001
                self.fail(f"to_number({weird!r}) 抛异常: {e}")

    def test_checked_distinguishes_zero_from_failure(self):
        """N1：必须能区分"真的 0"与"解析失败"。"""
        v, ok = to_number_checked("0")
        self.assertEqual((v, ok), (0.0, True))
        v, ok = to_number_checked("0.00")
        self.assertEqual(ok, True)
        v, ok = to_number_checked("")          # 空 → 未解析
        self.assertEqual(ok, False)
        v, ok = to_number_checked("abc")
        self.assertEqual(ok, False)


class TestFirstAmount(unittest.TestCase):
    def test_key_priority(self):
        self.assertEqual(first_amount({"价税合计": "1,200.00"}), 1200.0)
        # amount 优先于 价税合计
        self.assertEqual(first_amount({"amount": "100", "价税合计": "200"}), 100.0)

    def test_skips_zero_valued_field(self):
        self.assertEqual(first_amount({"amount": "0", "金额": "¥2,500.00"}), 2500.0)

    def test_absolute_by_default(self):
        self.assertEqual(first_amount({"amount": "-1,000.00"}), 1000.0)
        self.assertEqual(first_amount({"amount": "-1,000.00"}, absolute=False), -1000.0)

    def test_non_dict_and_empty(self):
        self.assertEqual(first_amount(None), 0.0)
        self.assertEqual(first_amount("x"), 0.0)
        self.assertEqual(first_amount({}), 0.0)

    def test_amount_of_keeps_zero(self):
        self.assertEqual(amount_of({"amount": "0"}), 0.0)
        self.assertEqual(amount_of({"amount": "￥500"}), 500.0)

    def test_sum_field_counts_each_field_once(self):
        rows = [{"amount": "1,000.00", "价税合计": "1,130.00"},
                {"amount": "500", "价税合计": "565"}]
        self.assertEqual(sum_field(rows), 1500.0)   # 只按 amount 计一次

    def test_amount_keys_is_single_source(self):
        self.assertIn("amount", AMOUNT_KEYS)
        self.assertIn("价税合计", AMOUNT_KEYS)


class TestParseRatio(unittest.TestCase):
    def test_percent_and_plain(self):
        self.assertAlmostEqual(parse_ratio("6%"), 0.06)
        self.assertAlmostEqual(parse_ratio("0.06"), 0.06)
        self.assertIsNone(parse_ratio(None))
        self.assertIsNone(parse_ratio(""))


class TestCrossModuleConsistency(unittest.TestCase):
    """★ 核心：同一金额文本，在任何模块都必须得到同一个数。

    这条断言把"全系统金额口径一致"锁死 —— 历史上 25 个私有实现里
    有 20 个会把 "12,000.00" 读成 0，导致报告自相矛盾。
    """

    RAW = "12,000.00"

    def _modules(self):
        import importlib
        out = {}
        for mod_name, fn_name in [
            ("engine.domain_analysis", "_number"),
            ("engine.verified_rule_engine", "_number"),
            ("engine.business_model", "_number"),
            ("engine.bank_flow", "_safe"),
            ("engine.fund_loop", "_safe"),
            ("engine.input_voucher", "_safe"),
            ("engine.false_invoice", "_safe"),
            ("engine.two_tax_income", "_safe"),
            ("engine.structure_mismatch_detector", "_safe"),
            ("engine.invoice_pattern_detector", "_safe"),
            ("engine.deduction_limit_detector", "_safe"),
            ("engine.external_check_reminder", "_safe"),
            ("engine.ap_aging", "_to_float"),
            ("engine.ar_aging", "_to_float"),
            ("engine.chain_executor", "_safe_float"),
            ("engine.threshold_scanner", "_safe_float"),
            ("engine.revenue_authenticity", "_number"),
            ("engine.export_rebate_crosscheck", "_num"),
            ("engine.monthly_reconcile", "_num"),
            ("engine.red_team", "_num"),
            ("engine.industry_benchmark", "_num"),
            ("engine.fund_matching", "_number_of"),
        ]:
            try:
                mod = importlib.import_module(mod_name)
                out[mod_name] = getattr(mod, fn_name)
            except Exception:  # noqa: BLE001
                continue
        return out

    def test_all_modules_agree_on_thousands_separator(self):
        mods = self._modules()
        self.assertGreaterEqual(len(mods), 15, "可检查的模块过少，测试可能失效")
        for name, fn in mods.items():
            with self.subTest(module=name):
                self.assertAlmostEqual(
                    fn(self.RAW), 12000.0, places=4,
                    msg=f"{name} 对 '12,000.00' 解析错误（应为 12000.0）")

    def test_all_modules_agree_on_currency_symbol(self):
        for name, fn in self._modules().items():
            with self.subTest(module=name):
                self.assertAlmostEqual(fn("￥1,234.56"), 1234.56, places=4)

    def test_all_amount_extractors_agree(self):
        from engine.invoice_pattern_detector import _amt as a1
        from engine.structure_mismatch_detector import _amt as a2
        from engine.domain_analysis import _amount_of as a3
        from engine.fund_matching import _amount_of as a4
        inv = {"价税合计": "￥1,200.00"}     # 只有价税合计
        for fn in (a1, a2, a3, a4):
            self.assertAlmostEqual(fn(inv), 1200.0, places=4,
                                   msg=f"{fn.__module__}.{fn.__name__} 取值不一致")


class TestNoPrivateImplementations(unittest.TestCase):
    def test_no_inline_float_or_zero(self):
        """源码中不得再出现行内 `float(X or 0)`。"""
        import glob
        import os
        import re
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pat = re.compile(r"float\([^()\n]*\bor\s+0\s*\)")
        hits = []
        for f in glob.glob(os.path.join(root, "engine", "**", "*.py"), recursive=True):
            if f.endswith("numparse.py"):
                continue
            txt = open(f, encoding="utf-8", errors="ignore").read()
            for m in pat.finditer(txt):
                hits.append("%s:%d" % (os.path.basename(f), txt[:m.start()].count("\n") + 1))
        self.assertEqual(hits, [], f"仍有行内私有兜底：{hits[:5]}")


if __name__ == "__main__":
    unittest.main()
