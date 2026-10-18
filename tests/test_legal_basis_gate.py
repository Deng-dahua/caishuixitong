# -*- coding: utf-8 -*-
"""GAP-19 无法规依据的风险降级为线索（2026-10-18）。

原差距：7/19、7/18 风险 `legal_provisions_n = 0` —— 近四成风险详情页"法规依据"为空，
却与有法条支撑的风险**同列同等级**。读者无法分辨"有依据"与"系统觉得可疑"。

现口径（唯一实现 `engine/legal_basis_gate.annotate`，只在读取层派生）：
  · `provisions_n > 0`      ⇒ `grounded`，不动等级
  · `provisions_n == 0`     ⇒ `none`：结论等级封顶 L2（待核线索）、
                              风险等级用权威 `risk_levels.cap_level` 封顶到「待核验」、
                              加 `legal_basis_note`「暂无法规依据」
  · `provisions_n is None`  ⇒ `unavailable`，**不降级**（"读不到"≠"没有依据"）
"""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import legal_basis_gate as GATE                            # noqa: E402
from engine.risk_levels import LEGAL_LEVELS, severity                  # noqa: E402


def _f(**kw):
    d = {"risk_no": "R-1", "risk_level": "高风险", "conclusion_grade": "L3",
         "type": "有销无进"}
    d.update(kw)
    return d


class AnnotateTests(unittest.TestCase):
    def test_grounded_keeps_level(self):
        f = GATE.annotate(_f(), 3)
        self.assertEqual(f["legal_basis_status"], "grounded")
        self.assertEqual(f["risk_level"], "高风险", "有依据的不得被降级")
        self.assertEqual(f["conclusion_grade"], "L3")
        self.assertNotIn("legal_basis_note", f)

    def test_none_downgrades_to_clue(self):
        f = GATE.annotate(_f(), 0)
        self.assertEqual(f["legal_basis_status"], "none")
        self.assertTrue(GATE.is_clue(f))
        self.assertEqual(f["conclusion_grade"], "L2", "无依据必须封顶为「待核线索」")
        self.assertEqual(f["conclusion_grade_before"], "L3", "原等级必须留存（可追溯）")
        self.assertEqual(f["risk_level"], "待核验",
                         "无依据必须封顶等级（用权威 cap_level，不是私自改写）")
        self.assertEqual(f["risk_level_before_clue"], "高风险")
        self.assertTrue(f.get("risk_level_capped_by_legal_basis"))
        self.assertIn("暂无法规依据", f["legal_basis_note"])

    def test_none_gives_visible_warning_words(self):
        f = GATE.annotate(_f(), 0)
        note = f["legal_basis_note"]
        self.assertIn("线索", note)
        self.assertIn("不得作为定性依据", note)

    def test_unavailable_does_not_downgrade(self):
        """取不到依据 ≠ 没有依据 ⇒ 不降级（缺失如实）。"""
        f = GATE.annotate(_f(), None)
        self.assertEqual(f["legal_basis_status"], "unavailable")
        self.assertEqual(f["risk_level"], "高风险")
        self.assertEqual(f["conclusion_grade"], "L3")
        self.assertIn("读取失败", f["legal_basis_note"])

    def test_capped_level_is_legal(self):
        f = GATE.annotate(_f(), 0)
        self.assertIn(f["risk_level"], LEGAL_LEVELS,
                      "封顶后的等级必须在权威词表内（否则会被静默丢弃）")

    def test_level_never_raised(self):
        """原本是「低风险」的无依据项，不得被"降级"抬高成待核验。"""
        f = GATE.annotate(_f(risk_level="低风险"), 0)
        self.assertEqual(f["risk_level"], "低风险",
                         "低风险/信息本来就不构成'认定'，降级不得把它抬重")

    def test_asserted_levels_all_downgraded(self):
        """三种"已认定有风险"的档位都必须降下来。"""
        for lv in ("极高风险", "高风险", "中风险"):
            f = GATE.annotate(_f(risk_level=lv), 0)
            self.assertEqual(f["risk_level"], GATE.CAP_TO, lv)
            self.assertEqual(f["risk_level_before_clue"], lv)

    def test_idempotent(self):
        f = _f()
        GATE.annotate(f, 0)
        first = dict(f)
        GATE.annotate(f, 0)
        self.assertEqual(f["conclusion_grade"], first["conclusion_grade"])
        self.assertEqual(f["risk_level"], first["risk_level"])
        self.assertEqual(f.get("conclusion_grade_before"),
                         first.get("conclusion_grade_before"),
                         "二次标注不得覆盖原始等级")


class SplitTests(unittest.TestCase):
    def test_split_separates_clues(self):
        items = [GATE.annotate(_f(risk_no="R-1"), 2),
                 GATE.annotate(_f(risk_no="R-2"), 0),
                 GATE.annotate(_f(risk_no="R-3"), 0)]
        got = GATE.split_by_basis(items)
        self.assertEqual(got["grounded_n"], 1)
        self.assertEqual(got["clue_n"], 2)
        self.assertTrue(all(x["legal_basis_status"] == "none" for x in got["clues"]))
        self.assertIn("不得", got["note"])

    def test_empty(self):
        got = GATE.split_by_basis([])
        self.assertEqual((got["grounded_n"], got["clue_n"]), (0, 0))


class WiringTests(unittest.TestCase):
    def test_risk_service_uses_the_gate(self):
        src = open(os.path.join(ROOT, "engine", "risk_service.py"),
                   encoding="utf-8").read()
        self.assertIn("legal_basis_gate", src, "风险接口未接入降级标注（GAP-19 会复发）")
        # 列表与详情两处都要接
        self.assertGreaterEqual(src.count("_basis_annotate(f,"), 2,
                                "列表与详情必须同一把尺（两处都要标注）")
        self.assertIn("legal_basis_status", src)

    def test_no_second_implementation(self):
        """`暂无法规依据` 文案只许出现在唯一实现里（防各处自己拼文案）。"""
        import glob
        hits = []
        for p in glob.glob(os.path.join(ROOT, "engine", "*.py")):
            if os.path.basename(p) == "legal_basis_gate.py":
                continue
            s = open(p, encoding="utf-8", errors="ignore").read()
            if "暂无法规依据" in s:
                hits.append(os.path.basename(p))
        self.assertEqual(hits, [], "文案出现第二处实现：%s" % hits)


if __name__ == "__main__":
    unittest.main()
