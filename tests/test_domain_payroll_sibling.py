# -*- coding: utf-8 -*-
"""工资/社保分析「同源排查」回归测试（域8比对 / 域人员画像 / VR056 公私混同）。

背景（2026-09-04 同源排查，继 VR005/VR055 修复之后）：
工资社保相关结论层还存在三处同源缺陷——与 VR005/VR055 旧逻辑同一根因：
1. 表头/合计行（合计/姓名/小计）未过滤，被当成真实人员；
2. 人员统计按「逐行记录数」而非「按姓名去重 / 按(姓名,月份)归位」；
3. 域8『有工资无社保』未按月份归位，无法满足『按人员身份和所属月份逐人解释』。

本文件覆盖：_domain_salary_ss_hf_compare（域8）、_domain_workforce_profiling（域人员画像）、
_scan_mixed_payroll（VR056）及 domain_analysis 侧新增的噪声/月份工具。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import domain_analysis as D
from engine import verified_rule_engine as V

VR056 = {"id": "VR056", "name": "公私混同发薪/私户支付薪酬",
         "required_sources": ["salaries", "bank_txs"]}

M12 = ["2025-{0:02d}".format(i) for i in range(1, 13)]


def _sal_items(spec):
    """spec: [(姓名, 金额, [月份])] -> 工资记录（带 period_start）"""
    return [{"name": n, "salary": a, "period_start": m + "-01", "acc_paid": 0.0}
            for n, a, months in spec for m in months]


def _soc_items(spec, noise=True):
    """spec: [(姓名, 基数, [月份])] -> 社保记录；noise=True 附带表头/合计行"""
    rows = [{"name": n, "base": b, "period_start": m + "-01"}
            for n, b, months in spec for m in months]
    if noise:
        rows += [{"name": junk, "base": 0.0, "period_start": "2025-01-01"}
                 for junk in ("合计", "姓名", "小计")]
    return rows


class TestDomainHelpers(unittest.TestCase):
    def test_noise_name_filtered(self):
        for junk in ("合计", "姓名", "小计", "总计", "本月合计", "缴费基数合计", "123"):
            self.assertTrue(D._is_noise_name(junk), f"{junk} 应判为表头/噪声行")
        for real in ("徐瑶", "黄奕珊", "杨莹", "王合计"):  # 王合计 不是噪声
            self.assertFalse(D._is_noise_name(real), f"{real} 是真实姓名，不得过滤")

    def test_row_period(self):
        self.assertEqual(D._row_period({"period_start": "2025-03-01"}), "2025-03")
        self.assertEqual(D._row_period({"费款所属期": "2025年07月"}), "2025-07")
        self.assertEqual(D._row_period({}), "")
        self.assertEqual(D._row_period({"name": "张三"}), "")  # 无月份字段

    def test_number_robust(self):
        self.assertEqual(D._number("12,000.00"), 12000.0)
        self.assertEqual(D._number("¥8,000"), 8000.0)
        self.assertEqual(D._number(None), 0.0)
        self.assertEqual(D._number(8500), 8500.0)

    def test_clean_emp_names(self):
        rows = [{"name": "张三"}, {"name": "合计"}, {"name": "姓名"}, {"name": "小计"}, {"name": ""}]
        self.assertEqual(D._clean_emp_names(rows), {"张三"})


class TestDomainSalarySSHFCompare(unittest.TestCase):
    def test_noise_in_social_not_reported(self):
        """社保清单里的合计/姓名/小计 不得作为『有工资无社保』人员报出。"""
        salaries = _sal_items([("张三", 10000, ["2025-01", "2025-02"]),
                               ("李四", 8000, ["2025-01", "2025-02"])])
        # 张三两月全参保；李四仅 2025-02 参保；社保另含噪声行
        social = _soc_items([("张三", 10000, ["2025-01", "2025-02"]),
                             ("李四", 8000, ["2025-02"])])
        fs = D._domain_salary_ss_hf_compare(salaries, social)
        uninsured = [f for f in fs if f["type"] == "有工资无社保"]
        self.assertEqual(len(uninsured), 1)
        om = uninsured[0]["observed_metrics"]
        self.assertEqual(om["uninsured_person_count"], 1)  # 仅李四
        self.assertEqual(om["uninsured_person_month_count"], 1)  # 李四 2025-01
        names = {r["姓名"] for r in om["person_month_detail"]}
        self.assertNotIn("合计", names)
        self.assertNotIn("姓名", names)
        self.assertNotIn("小计", names)
        self.assertEqual(names, {"李四"})

    def test_month_aware_uninsured(self):
        """李四 2025-01 有工资无社保 -> 人月级未参保；2025-02 已参保不报。"""
        salaries = _sal_items([("李四", 8000, ["2025-01", "2025-02"])])
        social = _soc_items([("李四", 8000, ["2025-02"])])
        fs = D._domain_salary_ss_hf_compare(salaries, social)
        uninsured = [f for f in fs if f["type"] == "有工资无社保"]
        self.assertEqual(len(uninsured), 1)
        om = uninsured[0]["observed_metrics"]
        self.assertEqual(om["uninsured_person_month_count"], 1)
        self.assertEqual(om["person_month_detail"][0]["月份"], "2025-01")
        self.assertEqual(om["person_month_detail"][0]["工资"], 8000.0)

    def test_noise_in_salary_only_excluded(self):
        """工资清单含合计行 -> 不得凭合计行造出『有工资无社保』。"""
        salaries = _sal_items([("张三", 10000, ["2025-01"])])
        salaries += [{"name": "合计", "salary": 10000, "period_start": "2025-01-01"}]
        social = _soc_items([("张三", 10000, ["2025-01"])])
        fs = D._domain_salary_ss_hf_compare(salaries, social)
        self.assertEqual([f for f in fs if f["type"] == "有工资无社保"], [])

    def test_low_base_filtered_noise(self):
        """社保低基数比对同样过滤噪声名。"""
        salaries = _sal_items([("张三", 20000, ["2025-01"])])
        social = _soc_items([("张三", 5000, ["2025-01"])])  # 5000 < 20000*0.6
        fs = D._domain_salary_ss_hf_compare(salaries, social)
        low = [f for f in fs if f["type"] == "社保低基数参保"]
        self.assertEqual(len(low), 1)
        self.assertIn("张三", low[0]["detail"])


class TestDomainWorkforceProfiling(unittest.TestCase):
    def test_noise_excluded_from_counts(self):
        """工资/社保含合计/姓名/小计 -> emp_count/ss_count 仍只计真实员工，不误报人数不一致。"""
        salaries = _sal_items([("张三", 10000, M12)]) + [
            {"name": "合计", "salary": 0}, {"name": "姓名", "salary": 0}, {"name": "小计", "salary": 0}]
        social = _soc_items([("张三", 10000, M12)])
        fs = D._domain_workforce_profiling(salaries, None, [], social)
        mismatch = [f for f in fs if f["type"] == "工资人数与社保人数不一致"]
        self.assertEqual(mismatch, [], "含噪声行时不应误报工资社保人数不一致")
        self.assertFalse(any(f["type"].startswith("人均营收") for f in fs))

    def test_real_mismatch_still_reported(self):
        """真实存在工资有、社保无的人员 -> 仍应报出人数不一致。"""
        salaries = _sal_items([("张三", 10000, M12), ("李四", 8000, M12)])
        social = _soc_items([("张三", 10000, M12)])  # 李四无社保
        fs = D._domain_workforce_profiling(salaries, None, [], social)
        mismatch = [f for f in fs if f["type"] == "工资人数与社保不一致" or f["type"] == "工资人数与社保人数不一致"]
        self.assertEqual(len(mismatch), 1)
        self.assertIn("差异1人", mismatch[0]["detail"])


class TestVR056MixedPayroll(unittest.TestCase):
    def test_employee_count_distinct_not_rows(self):
        """6 名员工 x 12 月 = 72 条记录，employee_count 应为 6（去重），非 72。"""
        salaries = _sal_items([("张三", 10000, M12), ("李四", 8000, M12),
                               ("王五", 12000, M12), ("赵六", 9000, M12),
                               ("钱七", 11000, M12), ("孙八", 9500, M12)])
        data = {"salaries": salaries}  # 无银行流水 -> 盲区分支
        fs = V._scan_mixed_payroll(data, VR056)
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0]["observed_metrics"]["employee_count"], 6)

    def test_noise_row_excluded_from_total_and_count(self):
        """合计行（金额=总额）不得计入 total_payroll 与 employee_count。"""
        salaries = _sal_items([("张三", 10000, ["2025-01", "2025-02"])])  # 2 万
        salaries += [{"name": "合计", "salary": 20000, "period_start": "2025-01-01"}]
        data = {"salaries": salaries}
        fs = V._scan_mixed_payroll(data, VR056)
        self.assertEqual(fs[0]["observed_metrics"]["employee_count"], 1)  # 仅张三
        self.assertEqual(fs[0]["observed_metrics"]["book_payroll_total"], 20000.0)


if __name__ == "__main__":
    unittest.main()
