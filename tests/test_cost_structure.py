# -*- coding: utf-8 -*-
"""成本费用口径补强测试（2026-09-15）。

覆盖：
A) financial_analyzer ①-2「取得发票 vs 成本费用合计」——触发与去重；
B) structure_mismatch_detector `_check_cost_goods_structure`「成本结构与行业差异」——触发/门槛/行业未命中；
   以及 `_AGRI_INDUSTRY` 白名单修正（"林"不再误伤"吉林"）。
"""

import unittest

from engine.financial_analyzer import _check_tax_audit_indicators
from engine.structure_mismatch_detector import (
    _check_agri_input_mismatch,
    _check_cost_goods_structure,
)


class _Ctx:
    def __init__(self, industry):
        self.company_profile = {"industry": industry}
        self.industry_profile = None


def _indicators(income, pur_invs):
    return _check_tax_audit_indicators({}, income, [], [], pur_invs, None, None)


class CostExpenseCoverageTest(unittest.TestCase):
    def test_total_cost_expense_coverage_fires(self):
        # cost 口径 0.85（① 不报），含期间费用后合计覆盖率 0.708 < 0.8 → ①-2 触发
        income = {"revenue": 2000000, "cost": 1000000,
                  "selling_expense": 100000, "admin_expense": 100000, "finance_expense": 0}
        pur = [{"amount": 850000}]
        hits = [f for f in _indicators(income, pur) if f.get("indicator") == "purchase_invoice_match_total"]
        self.assertEqual(len(hits), 1)
        self.assertIn("成本费用合计", hits[0]["type"])

    def test_both_scopes_report_separately(self):
        """★ 2026-09-25 契约变更：两个口径**各自独立成立即报**，不再互相抑制。

        旧契约（`assertEqual(len(hits), 0)`）是"成本口径已报 → 合计口径不再输出"。
        该去重是错的：企业只要成本侧也缺票（最常见情形），"期间费用缺票"这一**独立事实**
        就永久看不到 —— 用户报的疑点「取得发票占主营业务成本和期间费用合计的比例特别小」
        正是被这条去重压掉的（另一层原因是利润表取数为 0，见 test_statement_from_tb.py）。
        两条结论各自指名分母、`indicator` 不同（purchase_invoice_match /
        purchase_invoice_match_total），不构成"同一事实两条结论"。
        """
        income = {"revenue": 2000000, "cost": 1000000,
                  "selling_expense": 100000, "admin_expense": 100000, "finance_expense": 0}
        pur = [{"amount": 700000}]   # 成本口径 0.70、合计口径 0.583，两者都低于 0.8
        hits = [f for f in _indicators(income, pur) if f.get("indicator") == "purchase_invoice_match_total"]
        self.assertEqual(len(hits), 1, "合计口径不能因成本口径已报而被抑制")
        self.assertIn("成本费用合计", hits[0]["type"])
        self.assertIn("成本单侧口径", hits[0]["how_found"])
        # 分母必须写清楚：合计 = 成本 + 销售 + 管理 + 财务
        self.assertIn("1,200,000.00", hits[0]["detail"])


class CostGoodsStructureTest(unittest.TestCase):
    def test_garden_seedling_share_too_high(self):
        ctx = _Ctx("景观园林工程")
        pur = [{"goods": "苗木（香樟）", "amount": 800000},
               {"goods": "沙子", "amount": 100000}]
        hits = _check_cost_goods_structure(pur, ctx)
        self.assertTrue(hits)
        self.assertTrue(any("成本结构" in h["type"] for h in hits))
        self.assertTrue(all(h["level"] == "待核验" for h in hits))

    def test_industry_unmatched_no_output(self):
        ctx = _Ctx("信息技术服务")
        pur = [{"goods": "苗木", "amount": 800000}]
        self.assertEqual(_check_cost_goods_structure(pur, ctx), [])

    def test_below_amount_threshold_no_output(self):
        ctx = _Ctx("景观园林工程")
        pur = [{"goods": "苗木", "amount": 100000}]  # 合计 < 50 万门槛
        self.assertEqual(_check_cost_goods_structure(pur, ctx), [])

    def test_building_gravel_share_too_low(self):
        ctx = _Ctx("建筑工程")
        pur = [{"goods": "钢材", "amount": 900000}]  # 砂石占比 0，明显低于参考区间
        hits = _check_cost_goods_structure(pur, ctx)
        self.assertTrue(hits)


class AgriIndustryWhitelistTest(unittest.TestCase):
    def test_jilin_no_longer_skipped(self):
        # 旧白名单含裸"林"，"吉林…"会被误判为涉农而跳过；修正后应正常提示
        ctx = _Ctx("吉林贸易有限公司")
        pur = [{"goods": "农产品", "amount": 200000}]
        hits = _check_agri_input_mismatch(pur, ctx)
        self.assertTrue(hits)

    def test_garden_still_skipped(self):
        # 园林本身与农产品相关，仍应跳过（不误报）
        ctx = _Ctx("景观园林工程")
        pur = [{"goods": "农产品", "amount": 200000}]
        self.assertEqual(_check_agri_input_mismatch(pur, ctx), [])


class PeriodExpenseScopeTest(unittest.TestCase):
    """「凭证费用合计」只能是**期间费用**，不得把全序时账借方发生额当费用。

    2026-09-26 真实缺陷（用户质疑"不能区分主营业务成本和期间费用吗"时查出）：
    `_scan_expense_fabrication` 原把**每一张凭证的借方金额**无条件累加成费用合计，
    而借方还含资产购置、存货采购、往来款、银行存款 —— 某账套序时账借方合计
    43,378,566.71 元被算成"费用合计" 44,394,561.24 元，对收入 6,636,800.57 元
    得出"费用率 668.9%"。那不是费用率，是"全部借方发生额/收入"，
    会炮制并不存在的"费用率畸高"疑点。
    """

    def _f(self, subject, amount=100000):
        from engine.verified_rule_engine import _voucher_is_period_expense
        return _voucher_is_period_expense({"subject": subject, "amount": amount})

    def test_period_expenses_counted(self):
        for s in ("管理费用", "销售费用", "营业费用", "财务费用", "办公费", "业务招待费"):
            self.assertTrue(self._f(s), f"{s} 属期间费用，应计入")

    def test_cost_is_not_expense(self):
        for s in ("主营业务成本", "生产成本", "制造费用"):
            self.assertFalse(self._f(s), f"{s} 是成本不是期间费用，不得计入")

    def test_assets_and_receivables_not_expense(self):
        for s in ("固定资产", "原材料", "库存商品", "银行存款", "应收账款", "预付账款"):
            self.assertFalse(self._f(s), f"{s} 不是费用，不得计入")

    def test_unknown_subject_not_counted(self):
        # 判不出来宁可少计，绝不虚增
        self.assertFalse(self._f(""))
        self.assertFalse(self._f("其他"))

    def test_full_ledger_debit_is_not_expense_total(self):
        """回归核心：整本序时账的借方发生额不得被全量计入费用。"""
        from engine.verified_rule_engine import _voucher_is_period_expense
        ledger = [
            {"subject": "银行存款", "amount": 8000000},
            {"subject": "应收账款", "amount": 6000000},
            {"subject": "固定资产", "amount": 5000000},
            {"subject": "原材料", "amount": 4000000},
            {"subject": "主营业务成本", "amount": 3000000},
            {"subject": "管理费用", "amount": 300000},
            {"subject": "销售费用", "amount": 200000},
            {"subject": "财务费用", "amount": 50000},
        ]
        total_debit = sum(r["amount"] for r in ledger)
        expense = sum(r["amount"] for r in ledger if _voucher_is_period_expense(r))
        self.assertEqual(expense, 550000)
        # 旧实现会得到 total_debit（2630 万），虚增约 48 倍
        self.assertLess(expense, total_debit * 0.1,
                       "费用合计必须远小于全部借方发生额")


class CostDualBasisTest(unittest.TestCase):
    """主营成本**双口径勾稽**：账面(科目余额表6401/序时账) vs 进项发票归集口径。

    2026-09-26 新增（用户追问"三源是否都能辅助确定主营成本 / 是否写入一键分析"）：
    两条口径此前**各自为政、从不互相校验**——发票口径报 389 万，却无人拿账面 6401 对照，
    于是"发票分类把期间费用算进成本"这类偏差永远不被发现。
    """

    def _spec(self):
        from engine.verified_rule_engine import VERIFIED_RULE_CATALOG
        return [r for r in VERIFIED_RULE_CATALOG if r.get("id") == "VR060"][0]

    def _run(self, tb=None, vouchers=None, inv_amt=2000000.0):
        from engine.verified_rule_engine import _scan_core_cost_fund_evidence
        data = {
            "pur_invs": [{"seller": "甲供应商", "amount": inv_amt,
                          "goods": "影视素材", "date": "2025-03-01", "invoice_no": "INV1"}],
            "bank_txs": [{"date": "2025-03-05", "amount": -100000,
                          "counterparty": "甲供应商", "direction": "out"}],
        }
        if tb is not None:
            data["trial_balance"] = tb
        if vouchers is not None:
            data["vouchers"] = vouchers
        return _scan_core_cost_fund_evidence(data, self._spec())

    def _gap_findings(self, fs):
        return [f for f in fs if "两个口径" in str(f.get("detail") or "")]

    def test_gap_over_threshold_reported(self):
        # 账面 300 万（序时账借方发生额）vs 发票 200 万 → 差异 100 万(50%) 超阈值
        fs = self._run(vouchers=[{"account_name": "主营业务成本", "debit": 3000000}])
        hits = self._gap_findings(fs)
        self.assertEqual(len(hits), 1, "超阈值必须产出双口径待核事实")
        f = hits[0]
        self.assertEqual(f.get("level"), "待核验", "只陈述差异，不得定性")
        self.assertIn("不作定性", str(f.get("detail")))
        om = f.get("observed_metrics") or {}
        self.assertEqual(om.get("book_cost_total"), 3000000.0)
        self.assertEqual(om.get("cost_basis_gap"), -1000000.0)
        self.assertIn("序时账", str(om.get("book_cost_source") or ""))

    def test_gap_within_threshold_not_reported(self):
        # 差异 2% < 10% 阈值
        fs = self._run(vouchers=[{"account_name": "主营业务成本", "debit": 1960000}],
                       inv_amt=2000000.0)
        self.assertEqual(self._gap_findings(fs), [], "阈值内不得刷屏")

    def test_small_absolute_gap_not_reported(self):
        # 相对差异大但绝对额仅 5 千 < 1 万 → 不提示（避免小额账套噪音）
        fs = self._run(vouchers=[{"account_name": "主营业务成本", "debit": 500}],
                       inv_amt=5500.0)
        self.assertEqual(self._gap_findings(fs), [])

    def test_tb_closing_balance_must_not_be_used_as_cost(self):
        """★ 回归：主营业务成本(6401) 是损益类科目，期末已结转、余额恒为 0。

        科目余额表只有"期末余额"列（close_debit/close_credit）时，d − c 必为 0，
        **绝不能**拿它当账面成本——否则会算出"账面成本 0 vs 发票 389 万，差异 100%"
        这种纯属口径错误的结论（2026-09-26 实测踩过）。
        """
        fs = self._run(tb=[{"code": "6401", "name": "主营业务成本",
                            "close_debit": 0, "close_credit": 0}],
                       inv_amt=2000000.0)
        self.assertEqual(self._gap_findings(fs), [],
                         "期末余额口径不得被当成成本发生额")
        for f in fs:
            self.assertIsNone((f.get("observed_metrics") or {}).get("cost_basis_gap"))

    def test_tb_with_period_debit_used_as_fallback(self):
        # 科目余额表提供"本期发生额"列时可作为回退
        fs = self._run(tb=[{"code": "6401", "name": "主营业务成本",
                            "year_debit": 3000000}], inv_amt=2000000.0)
        hits = self._gap_findings(fs)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["observed_metrics"].get("book_cost_total"), 3000000.0)

    def test_voucher_fallback_used_when_no_tb(self):
        # 科目余额表无 6401 → 序时账按科目名兜底
        fs = self._run(vouchers=[{"account_name": "主营业务成本", "debit": 3000000}],
                       inv_amt=2000000.0)
        hits = self._gap_findings(fs)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["observed_metrics"].get("book_cost_total"), 3000000.0)

    def test_table_title_renamed(self):
        """「未匹配付款成本」易被读成"没付的钱"，实为无供应商级应付明细可核对。"""
        import os
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "engine", "verified_rule_engine.py")
        src = open(p, encoding="utf-8").read()
        self.assertIn("表3 无供应商级明细可核对的成本", src)
        self.assertNotIn('"title": "表3 未匹配付款成本', src, "表标题不得再用旧名")

    def test_no_book_cost_no_gap_finding(self):
        # 两源都没有成本科目 → 不得凭空编造差异
        fs = self._run(inv_amt=2000000.0)
        self.assertEqual(self._gap_findings(fs), [])
        for f in fs:
            self.assertIsNone((f.get("observed_metrics") or {}).get("cost_basis_gap"))


if __name__ == "__main__":
    unittest.main()
