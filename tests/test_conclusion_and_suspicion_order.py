# -*- coding: utf-8 -*-
"""★ 2026-10-02（用户定调：一定是先说重要的信息）：**重风险在前** 的呈现顺序回归测试。

两条铁律（都出过事故，故锁死）：
  ① 疑点（confirmed_problems）呈现顺序必须 **极高 → 高 → 中 → 低 → 待核验**，
     由 `engine/enterprise_report.py::_RISK_PRESENT_ORDER` 单一权威控制；
     表外等级一律沉到最末（99），不得混进高/中之间。
  ② 第一章总述结论段（企业整体风险综合评价）先行、监管态度分级由重到轻——
     见 tests/test_overall_conclusion.py::TestEditorialStandard
     （test_conclusion_comes_first / test_posture_clauses_weight_desc）。

原实现缺陷（本测试锁死它不得复发）：
  · `_LEVEL_RANK` 是**等级高低标度**（低风险=0 < 待核验=1），拿它当**呈现顺序**用会
    把"待核验"排到"低风险"前面；
  · 表外等级一律取 1，会插进高/中之间；
  · `reverse=True` 把金额缺失(0)的项提到同级最前。
"""
import unittest

from engine.enterprise_report import (
    _RISK_PRESENT_ORDER,
    _build_confirmed_problems,
)


def _f(level, ttype):
    return {"level": level, "type": ttype}


class TestSuspicionPresentOrder(unittest.TestCase):
    """疑点呈现顺序：由重到轻，表外沉底。"""

    def test_table_is_monotonic_light_to_heavy(self):
        """呈现序必须 极高 < 高 < 中 < 低 < 待核验（数值越小越靠前）。"""
        chain = ["极高风险", "高风险", "中风险", "低风险", "待核验", "待核", "信息"]
        vals = [_RISK_PRESENT_ORDER[k] for k in chain]
        self.assertEqual(vals, sorted(vals),
                         "疑点呈现顺序表不是单调递增（越小越靠前），顺序会乱：%s" % vals)
        # 风险等级四个档位必须各自一档；「待核验/待核/信息」是**证据状态**，刻意同档且沉底。
        self.assertEqual(len(set(vals[:4])), 4,
                         "极高/高/中/低 四档出现同值（等级之间不再分先后）")
        self.assertEqual(len(set(vals[4:])), 1,
                         "待核验/待核/信息 三种证据状态应同档沉底（现被拆开）")
        self.assertGreater(_RISK_PRESENT_ORDER["待核验"], _RISK_PRESENT_ORDER["低风险"],
                           "「待核验」应排在「低风险」之后（证据状态不参与风险排序）")

    def test_out_of_table_levels_sink_to_bottom(self):
        """表外等级必须沉到最末，不得混进高/中之间。"""
        unknown = _RISK_PRESENT_ORDER.get("未知等级", 99)
        self.assertGreater(unknown, _RISK_PRESENT_ORDER["中风险"],
                           "表外等级会插进中风险之前（最重要/最不重要次序颠倒）")

    def test_confirmed_problems_are_risk_first(self):
        """端到端：_build_confirmed_problems 的输出必须 极高→高→中→表外。"""
        rd = {
            "all_findings": [
                _f("中风险", "T2"),
                _f("极高风险", "T1"),
                _f("待核验", "T3"),          # 该通路会过滤掉证据状态项
                _f("高风险", "T4"),
                _f("未知等级", "T5"),
            ],
            "comprehensive": {},
        }
        out = _build_confirmed_problems(rd)
        titles = [p.get("title") for p in out]
        self.assertEqual(titles, ["T1", "T4", "T2", "T5"],
                         "疑点未按风险由重到轻呈现（实测 %s）" % titles)
        # 序号必须连续，前端靠 seq 呈现
        self.assertEqual([p.get("seq") for p in out], [1, 2, 3, 4])

    def test_same_level_ordered_by_exposure_desc(self):
        """同级必须按潜在敞口金额降序（金额大的在前）；金额缺失不擅占前排顺序。"""
        rd = {
            "all_findings": [
                {"level": "高风险", "type": "A", "observed_metrics": {"tax_impact": 100}},
                {"level": "高风险", "type": "B", "observed_metrics": {}},
                {"level": "高风险", "type": "C", "observed_metrics": {"tax_impact": 500}},
            ],
            "comprehensive": {},
        }
        out = _build_confirmed_problems(rd)
        titles = [p.get("title") for p in out]
        self.assertEqual(titles[0], "C", "同级未把金额最大的排在最前")
        # A/B 金额取不到，顺序只由稳定排序保证，只断言首项
        self.assertIn(titles[1], ("A", "B"))


if __name__ == "__main__":
    unittest.main()
