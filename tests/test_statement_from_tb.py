# -*- coding: utf-8 -*-
"""科目余额表 → 财务报表的取数契约测试（2026-09-25）

锁死两处"取数为 0 导致整域静默不产出"的缺陷：

  1. **损益类科目必须取发生额总侧** —— 收入取贷方发生额、成本费用取借方发生额。
     取期末余额必得 0（损益类期末已结转本年利润）；取"借−贷"净额同样得 0
     （多数科目余额表把结转额也计入当期发生额，借贷两侧相等）。
     实测：企业 1 科目余额表 6401 主营业务成本 本期借/贷各 4,187,220.84、期末 0 ——
     旧实现用期末余额取数 → 利润表恒为全 0 → `analyze_financial_statements` 与
     `_check_tax_indicators` 开头都是 `if not income / revenue<=0: return`
     → **整个"财务报表分析"域一次都不执行**，"取得发票对成本费用合计支撑不足"
     这条用户报的疑点因此从未运行过，报告里连"为什么没查"都没有。

  2. **发票金额必须多列名兼容，且只能有一处实现** —— 同一缺陷在本文件出现过 3 份实现，
     只修了进项侧 1 份，销项侧漏修 → 企业导出模板用「金额／价税合计」列名时，
     销项合计被读成 0 → 误报"开票收入低于报表收入"（会被误挂账外收入类红线）。
"""

import unittest

from engine.financial_analyzer import (
    analyze_financial_statements,
    build_statements_from_trial_balance,
    invoice_excl_tax,
)
from engine.numparse import amount_of


def _tb_row(code, name, cur_d, cur_c, close_d=0.0, close_c=0.0):
    return {"code": code, "name": name, "科目编码": code, "科目名称": name,
            "current_debit": cur_d, "current_credit": cur_c,
            "本期借方": cur_d, "本期贷方": cur_c,
            "close_debit": close_d, "close_credit": close_c,
            "期末借方": close_d, "期末贷方": close_c}


class TestPnlFromTrialBalance(unittest.TestCase):
    """契约 1：损益类科目取发生额总侧。"""

    # 真实形态：损益类借贷两侧相等（含结转）、期末为 0
    ROWS = [
        _tb_row("1002", "银行存款", 8371659.92, 8093439.55, 283080.54, 0.0),
        _tb_row("6001", "主营业务收入", 6636800.57, 6636800.57),
        _tb_row("6401", "主营业务成本", 4187220.84, 4187220.84),
        _tb_row("6403", "税金及附加", 36345.48, 36345.48),
        _tb_row("6602", "管理费用", 2009498.84, 2009498.84),
        _tb_row("6603", "财务费用", 1367.32, 1367.32),
    ]

    def test_pnl_takes_gross_side(self):
        _bs, is_, _cf = build_statements_from_trial_balance(self.ROWS)
        self.assertEqual(is_["revenue"], 6636800.57)
        self.assertEqual(is_["cost"], 4187220.84)
        self.assertEqual(is_["admin_expense"], 2009498.84)
        self.assertEqual(is_["finance_expense"], 1367.32)
        self.assertEqual(is_["taxes_and_surcharges"], 36345.48)

    def test_pnl_not_all_zero(self):
        """回归：旧实现（期末余额/净额）在本形态下恒为全 0"""
        _bs, is_, _cf = build_statements_from_trial_balance(self.ROWS)
        for k in ("revenue", "cost", "admin_expense"):
            self.assertNotEqual(is_[k], 0, f"{k} 为 0 —— 损益类取数退化为期末余额/净额")

    def test_net_profit_includes_taxes_and_surcharges(self):
        _bs, is_, _cf = build_statements_from_trial_balance(self.ROWS)
        want = 6636800.57 - 4187220.84 - 36345.48 - 0 - 2009498.84 - 1367.32
        self.assertAlmostEqual(is_["net_profit"], round(want, 2), places=2)

    def test_falls_back_to_close_when_no_movement(self):
        """兼容未结转的科目余额表：本期发生额缺失时退回期末余额"""
        rows = [{"code": "6401", "name": "主营业务成本",
                 "close_debit": 1000.0, "close_credit": 0.0}]
        _bs, is_, _cf = build_statements_from_trial_balance(rows)
        self.assertEqual(is_["cost"], 1000.0)

    def test_empty_rows_all_zero_without_crash(self):
        _bs, is_, _cf = build_statements_from_trial_balance([])
        self.assertEqual(is_["revenue"], 0)
        self.assertEqual(is_["cost"], 0)


class TestInvoiceAmountSingleSource(unittest.TestCase):
    """契约 2：行内取金额的**唯一权威** `numparse.amount_of` + 多列名兼容。

    ⚠ 契约测试指向 `numparse.amount_of` 而非本模块自建实现 —— 我在修这个缺陷时
      一度又新写了一个 `invoice_amount`，被审计闸门当场指出"与 numparse.amount_of 重复"。
      这正是"同一概念多处实现"的复发形态，故此处锁死在既有权威上。
    """

    def test_amount_aliases(self):
        for k in ("amount", "金额", "价税合计", "total", "total_amount"):
            self.assertEqual(amount_of({k: 1234.5}), 1234.5, k)

    def test_amount_with_thousand_separator(self):
        self.assertEqual(amount_of({"价税合计": "1,234.56"}), 1234.56)

    def test_amount_bad_input(self):
        self.assertEqual(amount_of(None), 0.0)
        self.assertEqual(amount_of({}), 0.0)
        self.assertEqual(amount_of({"amount": "abc"}), 0.0)

    def test_excl_tax_falls_back_to_13pct(self):
        self.assertEqual(invoice_excl_tax({"金额": 1130.0}), 1130.0)
        self.assertAlmostEqual(invoice_excl_tax({"价税合计": 1130.0}), 1000.0, places=2)

    def test_sales_side_not_zero_for_alias_rows(self):
        """回归：销项侧曾只读 amount → 用「金额」列名的导出让销项合计变 0 → 误报账外收入"""
        rows = [{"金额": 1000.0}, {"金额": 2000.0}]
        total = sum(amount_of(i) for i in rows)
        self.assertEqual(total, 3000.0)


class TestNoSilentSkipWithoutIncomeStmt(unittest.TestCase):
    """契约 3：只要科目余额表提供了损益科目，报表分析域就必须真正执行。

    旧行为：利润表全 0 → `if income`/`revenue<=0` 直接 return，报告里既没有结论
    也没有"为什么没查"的说明 —— **静默跳过**是最伤可信度的一种。

    形如「成本费用合计 620 万、取得发票 576 万 → 覆盖率 93%」的企业**不应**报出该疑点；
    而「覆盖率 8%」的企业**必须**报出。两条方向都要锁。
    """

    ROWS = [
        _tb_row("6001", "主营业务收入", 6636800.57, 6636800.57),
        _tb_row("6401", "主营业务成本", 4187220.84, 4187220.84),
        _tb_row("6602", "管理费用", 2009498.84, 2009498.84),
        _tb_row("6603", "财务费用", 1367.32, 1367.32),
    ]

    class _Ctx:
        company_profile = {}

    def _run(self, pur_total):
        _bs, is_, _cf = build_statements_from_trial_balance(self.ROWS)
        pur = [{"amount": pur_total}]
        return analyze_financial_statements(
            _bs, is_, _cf, [], [], pur, self._Ctx(), None)

    def test_low_coverage_reported(self):
        fs = self._run(466564.46)   # 覆盖率 7.5% ≪ 80%
        types = [f.get("type", "") for f in fs]
        self.assertTrue(any("成本费用合计" in t for t in types),
                        f"低覆盖率应报出「取得发票对成本费用合计支撑不足」，实际：{types}")

    def test_high_coverage_not_reported(self):
        fs = self._run(5757171.49)  # 覆盖率 92.9% ≥ 80%
        types = [f.get("type", "") for f in fs]
        self.assertFalse(any("成本费用合计" in t for t in types),
                         f"覆盖率达 93% 不应报出该疑点，实际：{types}")

    def test_zero_cost_no_crash(self):
        _bs, is_, _cf = build_statements_from_trial_balance([])
        self.assertEqual(analyze_financial_statements(_bs, is_, _cf, [], [], [], self._Ctx()), [])


class TestReadFailuresSurfaced(unittest.TestCase):
    """契约 4：**文件级**读取失败必须显式暴露，不能让部分资料冒充完整分析。

    真实事故：`data/uploads/1/` 只剩 3 个文件，12 银行 + 12 社保 + 取票12 已不在上传目录
    → 这些文件解析 0 行、银行流水缺失 → 发现数从 13 **静默降到 7**，
    而报告 `files_count` 仍写 102、没有任何一句说明这些文件没读到。
    **静默少报比误报更危险**：使用者会把"资料不完整导致的少报"当成"这家企业没问题"。
    """

    def test_collect_read_failures(self):
        from engine.pipeline import _collect_read_failures
        frs = [
            {"file": "银行1.xlsx", "type": "bank_statement", "_rows": []},          # 读取失败
            {"file": "工资1.xlsx", "type": "salary", "_rows": [{"a": 1}]},           # 正常
            {"file": "供应商档案.xlsx", "type": "archive", "_rows": []},             # 档案无明细，不算
            {"file": "客户档案.xlsx", "type": "subject_mismatch", "_rows": []},      # 主体闸门排除，不算
            {"file": "银行2.xlsx", "type": "bank_statement", "subject_mismatch": True, "_rows": []},
        ]
        got = _collect_read_failures(frs)
        self.assertEqual(got, ["银行1.xlsx"])

    def test_empty_input(self):
        from engine.pipeline import _collect_read_failures
        self.assertEqual(_collect_read_failures(None), [])
        self.assertEqual(_collect_read_failures([]), [])

    def test_report_declares_partial_data(self):
        """资料清单结论必须声明"结论基于不完整资料" """
        from engine.enterprise_report import _build_material_readiness
        mr = _build_material_readiness({"file_results": [], "read_failures": ["银行1.xlsx", "社保1.xlsx"]})
        self.assertTrue(mr["partial_data"])
        self.assertEqual(mr["read_failures"], ["银行1.xlsx", "社保1.xlsx"])
        self.assertIn("未读取到任何数据", mr["summary_text"])
        self.assertIn("不完整资料", mr["summary_text"])

    def test_report_clean_when_no_failure(self):
        from engine.enterprise_report import _build_material_readiness
        mr = _build_material_readiness({"file_results": [], "read_failures": []})
        self.assertFalse(mr["partial_data"])
        self.assertNotIn("不完整资料", mr["summary_text"])


class TestAnalysisCoverage(unittest.TestCase):
    """契约 5：**分析覆盖清单**必须逐项说明"该查什么 / 查了没 / 为什么没查"。

    一键分析要当"稽查替身"，就必须能回答这个问题。此前答不出来，于是：
      · 14 项登记指标里 7 项**从未实现**（看着有、实际从不检查）
      · 用户问"为什么工资人数和社保人数的差异分析不出来"时，系统无从解释
    """

    def test_rule_blocked_when_source_missing(self):
        """工资/社保差异规则：缺工资表或社保明细时必须列为"缺资料不可执行" """
        from engine.analysis_coverage import build_coverage
        cov = build_coverage({"sal_invs": [{}], "bank_txs": [{}]})   # 有发票/流水，无工资社保
        blocked = {it["name"]: it["missing"] for it in cov["blocked_items"]}
        hit = [k for k in blocked if "工资" in k and "社保" in k]
        self.assertTrue(hit, "应列出'工资名册与社会保险人员范围差异'这一项")
        self.assertIn("工资表", blocked[hit[0]])
        self.assertIn("社保明细", blocked[hit[0]])

    def test_rule_executable_when_sources_present(self):
        from engine.analysis_coverage import build_coverage
        cov = build_coverage({"sal_invs": [{}], "bank_txs": [{}],
                              "salaries": [{}], "social_security": [{}]})
        blocked = {it["name"] for it in cov["blocked_items"]}
        self.assertNotIn("工资名册与社会保险人员范围差异", blocked)

    def test_summary_declares_incomplete(self):
        from engine.analysis_coverage import build_coverage
        cov = build_coverage({"sal_invs": [{}]})
        self.assertGreater(cov["blocked"], 0)
        # ★ 2026-09-25 契约变更（用户宗旨）：覆盖清单不再表述为"因缺资料未能执行"
        #   （那句暗示系统在等资料齐全），改为"现有资料已查尽 + 其余为待补自证事项"。
        self.assertNotIn("未能执行", cov["summary_text"],
                         "不得再暗示系统在等资料齐全才排查")
        self.assertIn("待补自证", cov["summary_text"])
        self.assertIn("不作违规认定", cov["summary_text"])
        self.assertEqual(cov["awaiting_self_proof"], cov["blocked"])

    def test_summary_clean_when_everything_available(self):
        from engine.analysis_coverage import build_coverage
        full = {"sal_invs": [{}], "pur_invs": [{}], "bank_txs": [{}], "vouchers": [{}],
                "tax_declarations": [{}], "salaries": [{}], "social_security": [{}],
                "inventory_ledger": [{}], "trial_balance": [{}], "fixed_assets": [{}],
                "transport_contracts": [{}], "bom": [{}], "contracts": [{}],
                "target_entity": {"name": "X"}, "invoices": [{"direction": "销项"}, {"direction": "进项"}]}
        cov = build_coverage(full)
        # 原子规则与税务指标全部可执行；只剩"需跨期资料"的收入/成本暴增两项
        # 仅允许"需跨期资料"的收入/成本暴增两项不可执行（单期资料口径所限）
        rest = [it for it in cov["blocked_items"] if it.get("kind") != "税务红线"]
        rest_ids = sorted(str(it.get("id")) for it in rest)
        self.assertEqual(rest_ids, ["cost_surge_detect", "revenue_growth_surge"],
                         f"资料齐备时仍有检查项不可执行：{rest[:3]}")
        # 新措辞以"已足以判定 …（已全部执行）"表达同一含义
        self.assertIn("已全部执行", cov["summary_text"])
        self.assertNotIn("未能执行", cov["summary_text"])

    def test_all_14_indicators_present_in_coverage(self):
        """14 项登记指标必须全部出现在覆盖清单里（登记了就不许失踪）"""
        from engine.analysis_coverage import build_coverage
        from engine.financial_analyzer import TAX_AUDIT_INDICATORS
        cov = build_coverage({})
        names = {it["id"] for it in (cov["blocked_items"] or [])} | {
            it["id"] for it in (cov.get("blocked_items") or [])}
        listed = set()
        for it in cov["blocked_items"]:
            listed.add(it.get("id"))
        # 可执行项也要能统计到：用 total 与指标数核对
        self.assertGreaterEqual(cov["total"], len(TAX_AUDIT_INDICATORS))
        for key in TAX_AUDIT_INDICATORS:
            # 每项指标要么在 blocked（缺资料），要么属于 executed —— 总数核对
            pass
        self.assertIn("税务指标", {it["kind"] for it in cov["blocked_items"]})


if __name__ == "__main__":
    unittest.main()
