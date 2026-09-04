# -*- coding: utf-8 -*-
"""工资/社保分析「按月份归位 + 过滤表头行 + 明细表格」回归测试。

背景（2026-09-04 修复，实测公司：深圳海更数字传媒）：
上传 12 个月工资表，实为 6 名员工。旧逻辑按「金额」逐行聚合，把同一人分 12 个月领取的
记录计成 12 个人，误报「51 名员工工资高度均一」（12000 元共 24 人 = 徐瑶12月 + 黄奕珊12月）；
社保表的「合计 / 姓名 / 小计」表头合计行也被当作未匹配人员报出。

修复要点：
1. 按 (姓名, 所属月份) 归位，人数按姓名去重；
2. 拆分工资判据改为「同一月份内多人同薪」——同一人分多月领取等额工资属固定薪酬，不算痕迹；
3. 过滤表头/合计行噪声名；
4. 输出逐人逐月明细（person_month_detail / salary_person_month_detail）供报告渲染明细表。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import verified_rule_engine as V

VR005 = {"id": "VR005", "name": "工资名册与社会保险人员范围差异",
         "required_sources": ["salaries", "social_security"]}
VR055 = {"id": "VR055", "name": "工资薪酬均额/拆分疑点", "required_sources": ["salaries"]}

M12 = ["2025-{0:02d}".format(i) for i in range(1, 13)]


def _sal_items(spec):
    """spec: [(姓名, 金额, 月份列表)] → 工资记录（带 period_start）"""
    return [{"name": n, "salary": a, "period_start": m + "-01", "acc_paid": 0.0}
            for n, a, months in spec for m in months]


def _soc_items(spec, noise=True):
    """spec: [(姓名, 基数, 月份列表)] → 社保记录；noise=True 时附带表头/合计行"""
    rows = [{"name": n, "base": b, "period_start": m + "-01"}
            for n, b, months in spec for m in months]
    if noise:
        rows += [{"name": junk, "base": 0.0, "period_start": "2025-01-01"}
                 for junk in ("合计", "姓名", "小计")]
    return rows


class TestHelpers(unittest.TestCase):
    def test_noise_name_filtered(self):
        for junk in ("合计", "姓名", "小计", "总计", "本月合计", "123"):
            self.assertTrue(V._is_noise_name(junk), f"{junk} 应判为表头/噪声行")
        for real in ("徐瑶", "黄奕珊", "初永伟", "杨莹"):
            self.assertFalse(V._is_noise_name(real), f"{real} 是真实姓名，不得过滤")

    def test_row_period(self):
        self.assertEqual(V._row_period({"period_start": "2025-03-01"}), "2025-03")
        self.assertEqual(V._row_period({"period_end": "2025年12月31日"}), "2025-12")
        self.assertEqual(V._row_period({"所属期": "2025-07"}), "2025-07")
        self.assertEqual(V._row_period({}), "")


class TestWageSplittingMonthDimension(unittest.TestCase):
    """核心修复：不再把「同一人分多月等额领取」误报为「多名员工工资均一」。"""

    def test_two_persons_twelve_months_not_reported(self):
        """徐瑶、黄奕珊各 12 个月领 12000（实为 2 人 24 条记录）→ 同月仅 2 人同薪，不得报警。"""
        data = {"salaries": _sal_items([
            ("徐瑶", 12000.0, M12),
            ("黄奕珊", 12000.0, M12),
            ("初永伟", 30000.0, M12),
            ("李昭阳", 20000.0, M12),
            ("吴德昌", 8000.0, M12[:5]),
            ("杨莹", 8500.0, M12[:2]),
        ])}
        self.assertEqual(V._scan_wage_splitting(data, VR055), [],
                         "同一人分多月领取等额工资属固定薪酬，不得误报为拆分工资")

    def test_same_month_three_persons_fires_with_real_headcount(self):
        """同一月份 3 人领取相同整数工资 → 触发，且人数为去重的 3（非记录条数）。"""
        data = {"salaries": _sal_items([
            ("张三", 12000.0, M12[:3]),
            ("李四", 12000.0, M12[:3]),
            ("王五", 12000.0, M12[:3]),
        ])}
        fs = V._scan_wage_splitting(data, VR055)
        self.assertTrue(fs, "同月 3 人同薪应触发拆分工资线索")
        metrics = fs[0].get("observed_metrics", {}) or fs[0]
        groups = metrics.get("uniform_salary_groups") or []
        self.assertTrue(groups)
        self.assertEqual(groups[0]["count"], 3, "人数须按姓名去重（3人），不得按记录条数（9条）")
        self.assertEqual(metrics.get("employee_count"), 3)
        self.assertEqual(metrics.get("person_month_record_count"), 9)

    def test_detail_rows_present_for_table(self):
        """触发时应输出逐人逐月明细，供报告渲染明细表。"""
        data = {"salaries": _sal_items([
            ("张三", 12000.0, M12[:3]),
            ("李四", 12000.0, M12[:3]),
            ("王五", 12000.0, M12[:3]),
        ])}
        fs = V._scan_wage_splitting(data, VR055)
        rows = (fs[0].get("observed_metrics") or {}).get("salary_person_month_detail") or []
        self.assertTrue(rows, "必须输出逐人逐月明细行")
        self.assertIn("姓名", rows[0])
        self.assertIn("月份", rows[0])
        self.assertTrue(all(r["状态"] == "同月多人同薪" for r in rows[:9]))


class TestPayrollSocialMatching(unittest.TestCase):
    """核心修复：过滤表头/合计行 + 按月份逐人解释差异。"""

    def _base_data(self):
        salaries = _sal_items([
            ("徐瑶", 12000.0, M12),
            ("黄奕珊", 12000.0, M12),
            ("初永伟", 30000.0, M12),
            ("李昭阳", 20000.0, M12),
            ("吴德昌", 8000.0, M12[:6]),   # 工资 1-6 月
            ("杨莹", 8500.0, M12[:2]),     # 仅工资、无社保
        ])
        social = _soc_items([
            ("徐瑶", 12000.0, M12),
            ("黄奕珊", 12000.0, M12),
            ("初永伟", 30000.0, M12),
            ("李昭阳", 20000.0, M12),
            ("吴德昌", 8000.0, M12[:3]),   # 社保仅 1-3 月 → 4/5/6 月有工资无社保
            ("赵六", 9000.0, M12),         # 仅社保、无工资
        ])
        return {"salaries": salaries, "social_security": social}

    def test_header_rows_not_reported_as_persons(self):
        """社保表的「合计/姓名/小计」不得被当作未匹配人员报出。"""
        fs = V._scan_payroll_social(self._base_data(), VR005)
        self.assertTrue(fs, "存在真实人员差异（杨莹仅工资、赵六仅社保）应触发")
        body = fs[0]
        social_only = body.get("social_only_examples") or (body.get("observed_metrics") or {}).get("social_only_examples") or []
        salary_only = body.get("salary_only_examples") or (body.get("observed_metrics") or {}).get("salary_only_examples") or []
        for junk in ("合计", "姓名", "小计"):
            self.assertNotIn(junk, social_only, f"表头/合计行「{junk}」不得作为人员报出")
            self.assertNotIn(junk, salary_only)
        self.assertIn("赵六", social_only)
        self.assertIn("杨莹", salary_only)

    def test_month_level_gap_explained(self):
        """吴德昌 4/5/6 月有工资无社保 → 须给出月份级差异，而非只报人员级差异。"""
        fs = V._scan_payroll_social(self._base_data(), VR005)
        metrics = fs[0].get("observed_metrics") or fs[0]
        gaps = metrics.get("month_gaps") or []
        names = [g["姓名"] for g in gaps]
        self.assertIn("吴德昌", names, "应识别『同人部分月份有工资无社保』")
        wu = next(g for g in gaps if g["姓名"] == "吴德昌")
        self.assertEqual(wu["缺失月数"], 3)
        for m in ("2025-04", "2025-05", "2025-06"):
            self.assertIn(m, wu["工资有社保无的月份"])

    def test_person_month_detail_table(self):
        """须输出逐人逐月明细（姓名/月份/工资/社保基数/状态）供表格渲染。"""
        fs = V._scan_payroll_social(self._base_data(), VR005)
        metrics = fs[0].get("observed_metrics") or fs[0]
        rows = metrics.get("person_month_detail") or []
        self.assertTrue(rows, "必须输出逐人逐月明细")
        self.assertIn("姓名", rows[0])
        self.assertIn("月份", rows[0])
        self.assertIn("状态", rows[0])
        # 异常行（非「工资社保均有」）排在前，便于优先查看
        self.assertNotEqual(rows[0]["状态"], "工资社保均有",
                            "明细表应优先展示异常行")

    def test_single_uninsured_person_still_reported(self):
        """仅 1 人『有工资无社保』（占 16.7%，未达 20% 阈值）→ 仍须报出。

        铁律：不得通过抬高阈值放过任何信号。未依法参保属实质违规线索，
        哪怕只有一人也必须作为待证线索报出，由举证责任在企业一方。
        """
        data = {
            "salaries": _sal_items([
                ("徐瑶", 12000.0, M12),
                ("黄奕珊", 12000.0, M12),
                ("初永伟", 30000.0, M12),
                ("李昭阳", 20000.0, M12),
                ("吴德昌", 8000.0, M12),
                ("杨莹", 8500.0, M12[:2]),
            ]),
            "social_security": _soc_items([
                ("徐瑶", 12000.0, M12),
                ("黄奕珊", 12000.0, M12),
                ("初永伟", 30000.0, M12),
                ("李昭阳", 20000.0, M12),
                ("吴德昌", 8000.0, M12),
            ], noise=False),
        }
        fs = V._scan_payroll_social(data, VR005)
        self.assertTrue(fs, "『有工资无社保』属实质违规线索，仅 1 人也不得因比例阈值放过")
        metrics = fs[0].get("observed_metrics") or fs[0]
        self.assertIn("杨莹", metrics.get("salary_only_examples") or [])
        self.assertIn("未依法参保", fs[0].get("detail", "") or "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
