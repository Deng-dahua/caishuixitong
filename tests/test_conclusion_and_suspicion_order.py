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
        """呈现序必须 极高 < 高 < 中 < 低 < 待核验/信息（数值越小越靠前）。

        ★ 2026-10-06：链中不再含「待核」—— 它是**表外值**（合法词表只有
        `极高/高/中/低/待核验/信息`，见 `engine.risk_levels.LEGAL_LEVELS`），
        历史事故正是误用「待核」导致发现被整条静默丢弃（见 `audit_doctrine` 注释）。
        表外值的行为由下面的 `test_out_of_table_levels_sink_to_bottom` 单独锁住。
        """
        chain = ["极高风险", "高风险", "中风险", "低风险", "待核验", "信息"]
        vals = [_RISK_PRESENT_ORDER[k] for k in chain]
        self.assertEqual(vals, sorted(vals),
                         "疑点呈现顺序表不是单调递增（越小越靠前），顺序会乱：%s" % vals)
        # 风险等级四个档位必须各自一档；「待核验/信息」是**证据状态**，刻意同档且沉底。
        self.assertEqual(len(set(vals[:4])), 4,
                         "极高/高/中/低 四档出现同值（等级之间不再分先后）")
        self.assertEqual(len(set(vals[4:])), 1,
                         "待核验/信息 两种证据状态应同档沉底（现被拆开）")
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


class TestRedlineProblemsPresentOrder(unittest.TestCase):
    """★ **主路径**（有红线疑点）的呈现顺序。

    事故（2026-10-02 用户质疑「为什么二、不是从高风险开始排」）：
      `_build_confirmed_problems` 在有 suspicions 时**直接 return `_build_redline_problems(...)`**，
      而排序写在**旧路径**（无 suspicions）后面 ⇒ 主路径**从不执行排序**（死代码），
      实际顺序＝suspicions 的置信度顺序 → 读者看到"高风险"夹在第 7、14、15 位。
    ⚠ 上面 `TestSuspicionPresentOrder` 的用例走的是**旧路径**，所以它一直是绿的 ——
      这正是"测试覆盖不到主路径"的盲区，故此处单独补主路径用例。
    """

    @staticmethod
    def _s(level, name, rid):
        return {"redline_id": rid, "redline_name": name, "suspect": "涉嫌X", "taxes": ["增值税"],
                "constituents": ["要件一", "要件二"], "level": level, "verdict": "待核",
                "conclusion_grade": "待核", "confidence": 0.5, "closure": 0.3,
                "argumentation": {"claim": "", "reasoning": "", "constituent_hits": [],
                                  "confidence": 0.5, "verdict": "待核", "redline_hit": False,
                                  "redline_name": name, "constituents": ["要件一"]},
                "evidence_chain": {"elements": [], "available_count": 0, "missing_count": 1},
                "clue_chain": {"nodes": []}, "supporting_findings": [], "finding_count": 1}

    def _rd(self, susp):
        return {"comprehensive": {"redline_detection": {"suspicions": susp}},
                "all_findings": []}

    def test_main_path_is_risk_first(self):
        """主路径也必须 高 → 中 → 低 → 待核验（与旧路径同一权威表）。"""
        out = _build_confirmed_problems(self._rd([
            self._s("中风险", "乙项", "RL-X-2"),
            self._s("待核验", "丁项", "RL-X-4"),
            self._s("高风险", "甲项", "RL-X-1"),
            self._s("低风险", "丙项", "RL-X-3"),
        ]))
        got = [p.get("risk_level") for p in out]
        rank = [_RISK_PRESENT_ORDER.get(x, 99) for x in got]
        self.assertEqual(rank, sorted(rank), "主路径未按风险等级降序呈现：%s" % got)
        self.assertEqual(got[0], "高风险")
        self.assertEqual([p.get("seq") for p in out], [1, 2, 3, 4], "排序后未重排 seq")

    def test_out_of_vocabulary_level_normalized(self):
        """词表外等级（如税收优惠分析器产出的「优惠机会」）必须规范化，不得原样进风险清单。"""
        out = _build_confirmed_problems(self._rd([
            self._s("优惠机会", "残保金事项", "RL-X-9"),
            self._s("高风险", "甲项", "RL-X-1"),
        ]))
        levels = [p.get("risk_level") for p in out]
        self.assertNotIn("优惠机会", levels, "词表外等级原样进了风险疑点清单")
        for lv in levels:
            self.assertIn(lv, _RISK_PRESENT_ORDER, f"等级不在权威词表内：{lv}")
        # 规范化后（信息档）必须沉到风险等级之后
        self.assertEqual(out[-1].get("risk_level"), "信息")


if __name__ == "__main__":
    unittest.main()
