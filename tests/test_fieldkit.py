"""字段读取/语义判定（engine/fieldkit.py）与 finding 构造（engine/findingkit.py）回归测试。

★ 对应「适用所有行业和企业」的要求：**同一张发票，在任何模块都必须得到相同的字段与结论**。
（历史事故：`_buyer` 3 份实现里有一份少认"购买方名称"别名；`_is_void_or_red` 2 份判据不同
 → 作废/红冲率在不同章节可能互相矛盾。）
"""
import unittest

from engine.findingkit import (
    FINDING_FIELDS, make_finding, month_key, month_key_strict, normalize_month,
)
from engine.fieldkit import (
    buyer_name, goods_name, invoice_status, invoice_type, is_noise_name,
    is_void_or_red, row_period, seller_name, tax_category,
)


class TestFieldAliases(unittest.TestCase):
    """F1：字段别名集中维护 —— 各导出模板的列名都要认。"""

    def test_buyer_aliases(self):
        for k in ("buyer", "购方名称", "购买方名称", "购买方", "购方"):
            self.assertEqual(buyer_name({k: "某某公司"}), "某某公司", k)

    def test_seller_aliases(self):
        for k in ("seller", "销方名称", "销售方名称", "销售方", "销方", "供应商名称"):
            self.assertEqual(seller_name({k: "某某公司"}), "某某公司", k)

    def test_goods_aliases(self):
        for k in ("goods", "货物或应税劳务名称", "商品名称", "开票项目", "服务名称"):
            self.assertEqual(goods_name({k: "*广告服务*发布费"}), "*广告服务*发布费", k)

    def test_blank_and_bad_input(self):
        for fn in (buyer_name, seller_name, goods_name, invoice_type, invoice_status):
            self.assertEqual(fn(None), "")
            self.assertEqual(fn({}), "")
            self.assertEqual(fn("x"), "")

    def test_tax_category(self):
        self.assertEqual(tax_category("*广告服务*广告发布费"), "广告服务")
        self.assertEqual(tax_category("无标记的品名"), "")


class TestVoidOrRed(unittest.TestCase):
    """F2：作废/红冲判定取**并集** —— 任一线索成立即为真。"""

    def test_by_invoice_type(self):
        self.assertTrue(is_void_or_red({"发票类型": "增值税专用发票（红冲）"}))
        self.assertTrue(is_void_or_red({"inv_type": "作废发票"}))

    def test_by_status(self):
        self.assertTrue(is_void_or_red({"发票状态": "已作废"}))
        self.assertTrue(is_void_or_red({"status": "负数发票"}))

    def test_by_explicit_flag(self):
        self.assertTrue(is_void_or_red({"is_void": "1"}))
        self.assertTrue(is_void_or_red({"is_red": "是"}))

    def test_by_negative_amount(self):
        # 红冲发票常以负数体现；且金额带千分位同样要认得出（依赖 numparse）
        self.assertTrue(is_void_or_red({"amount": "-1,234.00"}))
        self.assertTrue(is_void_or_red({"价税合计": "￥-500.00"}))

    def test_normal_invoice_false(self):
        inv = {"发票类型": "电子发票(普通发票)", "发票状态": "正常", "amount": "12,000.00"}
        self.assertFalse(is_void_or_red(inv))


class TestRowPeriod(unittest.TestCase):
    def test_formats(self):
        for raw in ("202501", "2025-01", "2025/01", "2025年1月", "2025.01", "20250115",
                    "2025/1/15", "2025-1-5", "2025年1月15日"):
            self.assertEqual(row_period({"所属期": raw}), "2025-01", raw)

    def test_invalid_month_rejected(self):
        self.assertEqual(row_period({"所属期": "202513"}), "")   # 13 月非法
        self.assertEqual(row_period({"所属期": "无"}), "")
        self.assertEqual(row_period({}), "")

    def test_alias_order(self):
        # 按 PERIOD_KEYS 顺序取第一个能解析出月份的字段
        self.assertEqual(row_period({"期间": "2025/3/1", "所属期": "202501"}), "2025-01")
        self.assertEqual(row_period({"期间": "无", "所属期": "2025/3/1"}), "2025-03")


class TestNoiseName(unittest.TestCase):
    def test_noise(self):
        for n in ("合计", "小计", "姓名", "序号", " 合计 ", "合计 ", "123"):
            self.assertTrue(is_noise_name(n), n)

    def test_real_names(self):
        for n in ("张三", "李四", "欧阳娜娜"):
            self.assertFalse(is_noise_name(n), n)


class TestFindingKit(unittest.TestCase):
    def test_make_finding_fields_stable(self):
        f = make_finding("类型", "中风险", 5, "细节", "描述", "发现方式", "影响",
                         "依据", "建议", "类别", "来源链", "RL-001", "指标", 1.5)
        self.assertEqual(set(f.keys()), set(FINDING_FIELDS))
        self.assertEqual(f["indicator_value"], 1.5)

    def test_month_key(self):
        for raw in ("20250115", "2025-01-15", "2025/1/15", "2025年1月15日"):
            self.assertEqual(month_key(raw), "202501", raw)

    def test_normalize_month(self):
        self.assertEqual(normalize_month("2025-01-15"), "2025-01")
        self.assertEqual(normalize_month("2025年1月"), "2025-01")
        self.assertEqual(normalize_month("202513"), "")
        self.assertEqual(normalize_month(""), "")


class TestMonthKeySingleDigitMonth(unittest.TestCase):
    """★ 根因回归：个位月份/个位日不得污染月份键。

    旧实现"去分隔符取前 6 位"：
      '2025/1/15' → '202511'（把日的 1 当月份）  '2025-1-5' → '202515'（月份 15 不存在）
      '2026-1-31' → '202613'                      '2025年1月15日' → '20251月15日'（非数字）
    """

    BAD_CASES = {
        "2025/1/15": "202501", "2025-1-5": "202501", "2025.1.15": "202501",
        "2025年1月15日": "202501", "2026-1-31": "202601", "2026/1/1": "202601",
        "2025-9-9": "202509", "2025-12-01": "202512", "20250115": "202501",
        "2025-01-15": "202501", "2026-01": "202601", "2026年1月": "202601",
    }

    def test_month_key_correct(self):
        for raw, want in self.BAD_CASES.items():
            got = month_key(raw)
            self.assertEqual(got, want, f"month_key({raw!r})")
            self.assertTrue(got.isdigit(), f"month_key({raw!r}) 应为纯数字年月，得到 {got!r}")

    def test_month_key_never_exceeds_12(self):
        """凡日期里带可解析的 `YYYY[-/.年]M`，结果必须是那个月（旧实现在这里给出 13/15）。"""
        for raw in self.BAD_CASES:
            got = month_key(raw)
            self.assertEqual(int(got[4:6]), int(self.BAD_CASES[raw][4:6]), f"month_key({raw!r}) = {got!r}")

    def test_invalid_month_falls_back_not_silently_valid(self):
        """非法月份（13 月）：宽口径保留旧兜底串，**严格口径必须判为不可信**。

        契约分工（刻意的）：
          · `month_key`        —— 宽口径，未知格式仍返回可分组串（保持历史行为，不抛异常）
          · `month_key_strict` —— 严格口径，只有可信 6 位 YYYYMM 才返回，否则空串
        "按月汇总金额/对比差异"这类**结论性**场景必须用 strict，防止凭空造出一个月。
        """
        self.assertEqual(month_key("2025-13"), "202513")   # 旧兜底（非月份，但可分组）
        self.assertEqual(month_key_strict("2025-13"), "")  # 严格口径拒绝
        self.assertEqual(month_key_strict("2025年13月"), "")

    def test_month_key_and_normalize_month_same_month(self):
        """两个期间权威必须同源：同一日期得到同一个月。"""
        for raw in self.BAD_CASES:
            mk = month_key(raw)
            nm = normalize_month(raw)
            self.assertEqual(mk[:4] + "-" + mk[4:6] if mk else "", nm, raw)

    def test_month_key_strict_rejects_unknown(self):
        self.assertEqual(month_key_strict("2025/1/15"), "202501")
        self.assertEqual(month_key_strict("1月"), "")      # 无年份 → 不可信
        self.assertEqual(month_key_strict(""), "")
        self.assertEqual(month_key_strict(None), "")

    def test_same_month_one_bucket(self):
        """同一月的不同写法必须落进**同一个**桶（旧实现会拆成 202511/202512）。"""
        keys = {month_key_strict(x) for x in
                ("2025/1/15", "2025-01-20", "2025.1.5", "20250128", "2025年1月31日")}
        self.assertEqual(keys, {"202501"})


class TestDateMonthConvergence(unittest.TestCase):
    """★ 6 处"日期→月份"实现收敛后，各模块必须给出一致的月份。"""

    def test_red_team_monthly_totals(self):
        from engine.red_team import _monthly_totals
        out = _monthly_totals([
            {"date": "2025/1/15", "total": 100},
            {"date": "2025-01-20", "total": 300},
            {"date": "2025年1月31日", "total": 1},
            {"date": "2025-02-03", "total": 200},
        ])
        self.assertEqual(out.get("202501"), 401.0, f"1 月被拆桶了：{out}")
        self.assertEqual(out.get("202502"), 200.0)

    def test_verified_rule_engine_month(self):
        from engine.verified_rule_engine import _month, _declaration_month
        for fn in (_month, _declaration_month):
            self.assertEqual(fn("2025/1/15"), "202501", fn.__name__)
            self.assertEqual(fn("2026年1月"), "202601", fn.__name__)
            self.assertEqual(fn("2025-01-15"), "202501", fn.__name__)
            self.assertEqual(fn("1月"), "", fn.__name__)     # 不可信 → 空串
            self.assertEqual(fn(""), "", fn.__name__)

    def test_monthly_reconcile_month_of(self):
        from engine.monthly_reconcile import _month_of
        self.assertEqual(_month_of("2026/1/15"), "2026-01")
        self.assertEqual(_month_of("2026年1月"), "2026-01")
        self.assertEqual(_month_of(""), None)
        self.assertEqual(_month_of("无"), None)

    def test_no_stripped_digits_slicing_left(self):
        """防回归：任何模块都不得再用"去分隔符/取全部数字 + 前 6 位"自造月份。"""
        import pathlib
        import re as _re
        root = pathlib.Path(__file__).resolve().parent.parent / "engine"
        offenders = []
        for path in root.rglob("*.py"):
            src = path.read_text(encoding="utf-8", errors="ignore")
            for m in _re.finditer(r"^\s*(?:digits|s|text|date|dt)\s*\[\s*:\s*6\s*\]", src, _re.M):
                line = src[:m.start()].count("\n") + 1
                offenders.append(f"{path.name}:{line}")
        self.assertEqual(offenders, [], f"仍有自造月份键的切片：{offenders}")


class TestPeriodUtilsConvergence(unittest.TestCase):
    """★ 根因回归：`tax_risk_utils` 的"伪归一化"曾导致崩溃 / 静默空分析。

    旧 `_normalize_period(ym)` = `ym[:7]`：
        '2025/1/15' → '2025/1/'  → `_period_to_date_range` 抛 ValueError（分析链断）
        '2025年1月'  → '2025年1月' → 同上
        '2025-1'    → '2025-1'   → 长度<7 → 日期区间 ('','') → **整段期间静默无数据**
    """

    def test_normalize_period_all_formats(self):
        from tax_risk_utils import _normalize_period
        for raw in ("2025-01", "2025/1/15", "2025年1月", "2025-1", "2025.1.5", "20250115"):
            self.assertEqual(_normalize_period(raw), "2025-01", raw)
        self.assertEqual(_normalize_period(""), "")
        self.assertEqual(_normalize_period("2025-13"), "")   # 非法月份 → 空串（不再返回伪值）

    def test_period_to_date_range_never_crashes(self):
        from tax_risk_utils import _period_to_date_range
        for raw in ("2025-01", "2025/1/15", "2025年1月", "2025.1.5", "2025-1",
                    "2025-13", "", "无"):
            r = _period_to_date_range(raw)          # 关键：**任何输入都不得抛异常**
            self.assertIsInstance(r, tuple, raw)
            self.assertEqual(len(r), 2, raw)
        self.assertEqual(_period_to_date_range("2025/1/15"), ("2025-01-01", "2025-01-31"))
        self.assertEqual(_period_to_date_range("2025-02"), ("2025-02-01", "2025-02-28"))
        self.assertEqual(_period_to_date_range("2025-13"), ("", ""))

    def test_get_periods_between(self):
        from tax_risk_utils import _get_periods_between
        self.assertEqual(_get_periods_between("2025-01", "2025-03"),
                         ["2025-01", "2025-02", "2025-03"])
        self.assertEqual(_get_periods_between("2025/1/15", "2025-03"),
                         ["2025-01", "2025-02", "2025-03"])
        self.assertEqual(_get_periods_between("2025-11", "2026-02"),
                         ["2025-11", "2025-12", "2026-01", "2026-02"])
        # 不可解析 / 逆序 → 空列表（旧实现抛 IndexError/ValueError 或死循环）
        self.assertEqual(_get_periods_between("", "2025-03"), [])
        self.assertEqual(_get_periods_between("2025-05", "2025-03"), [])

    def test_safe_float_is_actually_safe(self):
        from tax_risk_utils import _safe_float
        # 旧实现 `float(val)` 在这些输入上会抛 ValueError（名为 safe 实则不安全）
        for raw, want in (("1,234.00", 1234.0), ("￥-1,000", -1000.0), ("", 0.0),
                          ("abc", 0.0), (None, 0.0), (0, 0.0), ("12.5", 12.5)):
            self.assertEqual(_safe_float(raw), want, repr(raw))


class TestCrossModuleFieldConsistency(unittest.TestCase):
    """★ 核心：同一张发票在**各模块**读出的字段与结论必须一致。"""

    INV = {
        "购买方名称": "买方公司",          # 只有别名，没有 buyer
        "销售方名称": "卖方公司",
        "商品名称": "*技术服务*开发费",
        "发票状态": "红冲",
        "价税合计": "￥1,200.00",
    }

    def _modules(self):
        import importlib
        out = {}
        for mod, fns in [
            ("engine.external_check_reminder", ("_buyer", "_seller")),
            ("engine.false_invoice", ("_buyer", "_seller")),
            ("engine.invoice_pattern_detector", ("_buyer", "_seller", "_is_void_or_red")),
            ("engine.verified_rule_engine", ("_is_void_or_red",)),
            ("engine.input_voucher", ("_goods",)),
            ("engine.structure_mismatch_detector", ("_goods",)),
        ]:
            try:
                m = importlib.import_module(mod)
            except Exception:  # noqa: BLE001
                continue
            for fn in fns:
                if hasattr(m, fn):
                    out["%s.%s" % (mod, fn)] = getattr(m, fn)
        return out

    def test_buyer_agrees_everywhere(self):
        fns = {k: v for k, v in self._modules().items() if k.endswith("_buyer")}
        self.assertGreaterEqual(len(fns), 3)
        for name, fn in fns.items():
            self.assertEqual(fn(self.INV), "买方公司", name)

    def test_seller_agrees_everywhere(self):
        for name, fn in {k: v for k, v in self._modules().items() if k.endswith("_seller")}.items():
            self.assertEqual(fn(self.INV), "卖方公司", name)

    def test_goods_agrees_everywhere(self):
        for name, fn in {k: v for k, v in self._modules().items() if k.endswith("_goods")}.items():
            self.assertEqual(fn(self.INV), "*技术服务*开发费", name)

    def test_void_or_red_agrees_everywhere(self):
        fns = {k: v for k, v in self._modules().items() if k.endswith("_is_void_or_red")}
        self.assertGreaterEqual(len(fns), 2)
        for name, fn in fns.items():
            self.assertTrue(fn(self.INV), f"{name} 未判出红冲")


if __name__ == "__main__":
    unittest.main()
