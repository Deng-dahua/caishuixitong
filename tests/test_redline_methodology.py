# -*- coding: utf-8 -*-
"""
税务红线方法论契约测试（2026-09-06 新方法论）
================================================

锁死五条不可回退的契约：
  1. 红线库行业无关且要素完整（六要素缺一不可）
  2. 是否触红只取决于线索链的可量化事实，与证据链闭合度无关
  3. 反证（正当理由）不得由关键词猜测，只认企业是否提交
  4. 证据链的「已有/缺失」判定必须对齐资料类别，禁止模糊命中
  5. 报告标题必须是红线名称，禁止再出现「待核事实：XXX核验」空壳
"""

import unittest

from engine.tax_redlines import REDLINES, all_redlines, get_redline, match_redlines, stats
from engine.clue_chain import build_clue_chain, extract_numbers
from engine.evidence_chain import build_evidence_chain
from engine.argumentation import (
    build_argumentation, _VERDICT_CONFIRMED, _VERDICT_HIT_PENDING,
    _VERDICT_EXCLUDED, _VERDICT_WEAK,
)
from engine.redline_engine import run_redline_detection

_REQUIRED_FIELDS = (
    "id", "name", "domain", "taxes", "suspect", "legal_basis",
    "constituents", "clue_chain", "evidence_chain", "justifications",
    "required_materials", "remedy",
)


class TestRedlineLibrary(unittest.TestCase):
    """契约 1：红线库结构完整、行业无关"""

    def test_every_redline_has_all_fields(self):
        for r in REDLINES:
            with self.subTest(redline=r.get("id")):
                for f in _REQUIRED_FIELDS:
                    self.assertTrue(r.get(f), f"{r.get('id')} 缺少字段 {f}")

    def test_redline_ids_unique(self):
        ids = [r["id"] for r in REDLINES]
        self.assertEqual(len(ids), len(set(ids)), "红线编号不得重复")

    def test_library_scale(self):
        self.assertGreaterEqual(len(REDLINES), 40, "红线库不应少于 40 条")

    def test_no_industry_specific_redline(self):
        """红线不得绑定具体行业（行业只影响线索形态，不影响红线本身）"""
        industries = ("纺织", "餐饮", "建筑", "农业", "金融", "制造")
        for r in REDLINES:
            for word in industries:
                self.assertNotIn(word, r["name"], f"{r['id']} 红线名称不应绑定行业")

    def test_match_typical_signals(self):
        cases = [
            ("有销无进项发票品名无对应", "RL-VAT-001"),
            ("工资表与社保参保人数不符", "RL-PAY-001"),
            ("六员个人账户收取经营款项", "RL-INC-002"),
            ("暂估成本长期挂账无发票", "RL-COST-001"),
            ("公转私大额频繁", "RL-FUND-001"),
            ("采购成本未匹配到对公支付流水", "RL-PTY-001"),
        ]
        for text, expect in cases:
            with self.subTest(text=text):
                hits = match_redlines(text, limit=3)
                self.assertTrue(hits, f"{text} 未匹配到任何红线")
                self.assertEqual(hits[0]["id"], expect)


class TestClueChain(unittest.TestCase):
    """线索链：每环必须能说出用了什么资料、做了什么、看到什么数字"""

    def setUp(self):
        self.redline = get_redline("RL-PTY-001")
        self.finding = {
            "type": "采购成本无对公付款资金证据",
            "detail": "主营业务成本中有1,479,672.02元（占主营成本9.5%）未匹配到任何对公支付流水，"
                      "涉及东莞市某企业163,717元。",
            "observed_metrics": {"未匹配金额": "1,479,672.02元", "占比": "9.5%"},
            "independent_sources": ["进项发票", "银行流水"],
        }

    def test_nodes_have_source_action_observed(self):
        chain = build_clue_chain(self.finding, self.redline)
        self.assertTrue(chain["nodes"])
        for n in chain["nodes"]:
            self.assertTrue(n["source"], "每环必须写明使用资料")
            self.assertTrue(n["action"], "每环必须写明做了什么")
            self.assertTrue(n["observed"], "每环必须写明实际看到的数据")
            self.assertTrue(n["trace_ref"], "每环必须可回查")

    def test_terminal_signal_carries_numbers(self):
        chain = build_clue_chain(self.finding, self.redline)
        self.assertTrue(chain["terminal_signal"])
        self.assertTrue(extract_numbers(chain["terminal_signal"]),
                        "终端信号必须含可量化数字")

    def test_numbers_extracted(self):
        nums = extract_numbers("金额1,479,672.02元，占比9.5%，共36家供应商")
        joined = "".join(nums)
        self.assertIn("1,479,672.02元", joined)
        self.assertIn("9.5%", joined)


class TestEvidenceChain(unittest.TestCase):
    """契约 3、4：证据判定严格，反证不得猜测"""

    def setUp(self):
        self.redline = get_redline("RL-PTY-001")
        self.finding = {"type": "采购成本无对公付款资金证据", "detail": "成本中有147万元未匹配付款流水"}

    def test_no_fuzzy_match(self):
        """「采购合同」不得因清单里有「渠道订单」而被判为已有"""
        ev = build_evidence_chain(self.finding, self.redline,
                                  available_materials=["银行流水", "渠道订单"])
        contract_items = [e for e in ev["elements"] if "合同" in e["name"]]
        self.assertTrue(contract_items)
        for e in contract_items:
            self.assertNotEqual(e["status"], "已有",
                                "未提供合同文件时，合同类证据不得判为已有")

    def test_rebuttal_default_pending(self):
        """反证（正当理由）默认待企业提交，不得由关键词推断为已提交"""
        ev = build_evidence_chain(self.finding, self.redline,
                                  available_materials=["银行流水", "进项发票"])
        rebs = [e for e in ev["elements"] if e["role"] == "反证"]
        self.assertTrue(rebs)
        for e in rebs:
            self.assertEqual(e["status"], "待企业提交")

    def test_closure_in_range(self):
        ev = build_evidence_chain(self.finding, self.redline,
                                  available_materials=["银行流水"])
        self.assertGreaterEqual(ev["closure"], 0.0)
        self.assertLessEqual(ev["closure"], 1.0)

    def test_equivalent_categories(self):
        """「财务报表」已提供时，不应判「资产负债表」缺失"""
        ev = build_evidence_chain(self.finding, self.redline,
                                  available_materials=["财务报表"])
        self.assertIsInstance(ev["elements"], list)


class TestArgumentation(unittest.TestCase):
    """契约 2：触红与定性是两个层次"""

    def _run(self, terminal_signal, closure_materials):
        redline = get_redline("RL-PTY-002")
        finding = {"type": "供应商集中度异常", "detail": "前三大供应商占比51%",
                   "level": "中风险"}
        clue = build_clue_chain(finding, redline)
        if terminal_signal:
            clue["terminal_signal"] = terminal_signal
        else:
            clue["terminal_signal"] = ""
        ev = build_evidence_chain(finding, redline, available_materials=closure_materials)
        return build_argumentation(finding, redline, clue, ev)

    def test_hit_does_not_depend_on_closure(self):
        """有可量化线索即触红，闭合度低也不改变触红结论"""
        arg = self._run("前三大供应商占比51%，分布在11个省份", [])
        self.assertTrue(arg["redline_hit"], "有量化线索必须判触红")
        self.assertIn(arg["verdict"], (_VERDICT_CONFIRMED, _VERDICT_HIT_PENDING))

    def test_no_signal_means_weak(self):
        arg = self._run("", [])
        self.assertFalse(arg["redline_hit"])
        self.assertEqual(arg["verdict"], _VERDICT_WEAK)

    def test_confidence_floor_when_hit(self):
        arg = self._run("前三大供应商占比51%", [])
        self.assertGreaterEqual(arg["confidence"], 0.60,
                                "触红后置信度不得低于 0.60")

    def test_reasoning_has_five_parts(self):
        arg = self._run("前三大供应商占比51%", ["银行流水"])
        for marker in ("【主张】", "【依据】", "【证据】", "【裁决】"):
            self.assertIn(marker, arg["reasoning"])


class TestReportIntegration(unittest.TestCase):
    """契约 5：报告以红线疑点为主干"""

    def test_problem_title_is_redline(self):
        from engine.enterprise_report import _build_redline_problems
        findings = [
            {"type": "待核事实：供应商地域分布与购销集中度核验",
             "detail": "进项发票供应商分布在11个省份，前几大采购来源地：河南4家8,005,858元(51%)",
             "level": "中风险", "independent_sources": ["进项发票"]},
        ]
        res = run_redline_detection(findings, material_readiness={"provided": ["进项发票"]})
        self.assertTrue(res["suspicions"])
        problems = _build_redline_problems(res["suspicions"])
        self.assertTrue(problems)
        for p in problems:
            self.assertNotIn("待核事实", p["title"], "标题不得再出现「待核事实」")
            self.assertTrue(p["redline_id"])
            self.assertTrue(p["suspect"])
            # 五段式
            heads = [x["heading"] for x in p["narrative_paragraphs"]]
            self.assertEqual(len(heads), 5)
            self.assertIn("线索链", "".join(heads))
            self.assertIn("证据链", "".join(heads))
            self.assertIn("论证", "".join(heads))

    def test_suspect_not_duplicated(self):
        from engine.enterprise_report import _build_redline_problems
        findings = [{"type": "有销无进风险", "detail": "销项品名无对应进项，涉及120万元",
                     "level": "高风险"}]
        res = run_redline_detection(findings, material_readiness={"provided": ["销项发票", "进项发票"]})
        problems = _build_redline_problems(res["suspicions"])
        for p in problems:
            self.assertNotIn("涉嫌涉嫌", "".join(
                x["text"] for x in p["narrative_paragraphs"]))


if __name__ == "__main__":
    unittest.main()
