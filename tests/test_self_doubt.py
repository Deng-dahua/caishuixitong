# -*- coding: utf-8 -*-
"""契约：疑点自我怀疑层（自我反驳 + 验证清单）（2026-10-06）。

用户要求：
  「给一键分析按钮增加一个**对疑点产生自我怀疑**的能力，然后一键分析按钮会
   **以终为始拆解疑点的关键信息，自我反驳，并再索取资料信息进行自我验证**。」

本文件锁五条：
  ① 以终为始：有证据角色表的项，每条支撑都要有「可能不成立之处」+「什么情况下不成立」；
  ② 只索取**未提供**的资料（已提供的不得再要 —— 否则又是让企业补它已交的东西）；
  ③ 无证据角色表的项（并入第二章的原子规则/域分析/组合画像/专项比对）也必须产出，
     且**必须**附「结论来源（证据地位）」反驳（"可信观察 ≠ 税务违规"是这类项最该说清的一句）；
  ④ 验证清单**不得为空**（用户要的是"再索取资料"，不是"请自行核实"）；
  ⑤ 现状词表**从既有权威派生**：`待核`（内部）与 `已提供同类资料`（输出后）必须归到同一支
     —— 否则同一状态在流程前后长得不一样就会判空（本项目今日已栽过三次）。
"""
import unittest


def _p_ev(**kw):
    base = {
        "seq": 1, "title": "测试疑点", "suspect": "",
        "detail_table": {"columns": ["证据角色", "证据名称", "证明目的", "现状", "依据"],
                         "rows": []},
        "narrative_paragraphs": [],
    }
    base.update(kw)
    return base


class TestSelfDoubt(unittest.TestCase):

    def test_each_support_has_doubt_and_overturn_condition(self):
        """① 以终为始：每条支撑都要有反驳与推翻条件。"""
        from engine.self_doubt import doubt_for_problem
        p = _p_ev(detail_table={"columns": [], "rows": [
            {"证据角色": "直接证据", "证据名称": "费用明细账", "证明目的": "证明费用发生", "现状": "已有"},
            {"证据角色": "反证", "证据名称": "纳税调增明细", "证明目的": "证明已调整", "现状": "缺失"},
        ]})
        r = doubt_for_problem(p, provided_materials=[])
        self.assertTrue(r["available"])
        self.assertGreaterEqual(len(r["key_inputs"]), 2)
        for k in r["key_inputs"]:
            self.assertTrue(str(k.get("doubt") or "").strip(),
                            f"支撑「{k.get('item')}」缺『可能不成立之处』")
            self.assertTrue(str(k.get("overturns_if") or "").strip(),
                            f"支撑「{k.get('item')}」缺『什么情况下不成立』")

    def test_requests_only_unprovided(self):
        """② 只索取未提供的资料；已提供的不得进验证清单。"""
        from engine.self_doubt import doubt_for_problem
        p = _p_ev(detail_table={"columns": [], "rows": [
            {"证据角色": "直接证据", "证据名称": "费用明细账", "证明目的": "x", "现状": "已有"},
            {"证据角色": "反证", "证据名称": "纳税调增明细", "证明目的": "y", "现状": "缺失"},
        ]})
        req = [q["material"] for q in doubt_for_problem(p, provided_materials=[])["requested"]]
        self.assertIn("纳税调增明细", req)
        self.assertNotIn("费用明细账", req, "已提供的资料不得列为待补")

    def test_no_evidence_table_still_produces_with_tier_doubt(self):
        """③ 无证据角色表（非红线来源）也要产出，且要指出「证据地位」这一层反驳。"""
        from engine.self_doubt import doubt_for_problem
        p = _p_ev(evidence_tier="已验原子规则（可信观察）", source="域分析发现",
                  detail_table={"columns": [], "rows": []},
                  narrative_paragraphs=[{"heading": "三、已取得的资料与待补充的资料",
                                         "text": "本项依据的独立数据源：进项发票（已上传）。尚需结合用途明细账核对。"}])
        r = doubt_for_problem(p, provided_materials=[])
        self.assertTrue(r["available"], "非红线来源的项也必须自我怀疑")
        items = " ".join(str(k.get("item") or "") for k in r["key_inputs"])
        self.assertIn("证据地位", items)
        self.assertTrue(r["requested"], "验证清单不得为空")

    def test_requested_never_empty(self):
        """④ 任何能产出结论的项，验证清单都不得为空。"""
        from engine.self_doubt import doubt_for_problem
        for p in (_p_ev(evidence_tier="组合风险信号（跨3个业务环节）",
                        narrative_paragraphs=[{"heading": "三、已取得的资料与待补充的资料",
                                               "text": "本项依据的独立数据源：银行流水（已上传）。"}]),
                  _p_ev(detail_table={"columns": [], "rows": [
                      {"证据角色": "直接证据", "证据名称": "合同", "证明目的": "z", "现状": "待企业提交"}]})):
            r = doubt_for_problem(p, provided_materials=[])
            if r.get("available"):
                self.assertTrue(r.get("requested"), "验证清单不得为空")

    def test_status_vocab_aligned_across_stages(self):
        """⑤ `待核`（内部）与 `已提供同类资料`（输出后改写）必须归到同一支。

        这是本项目"字符串在不同阶段被规范化"的又一实例：
        `report_wording.STATUS_TEXT` 会在输出前把 `待核/待核验/待核实` 改写成「已提供同类资料」。
        """
        from engine.self_doubt import _status_branch
        self.assertEqual(_status_branch("已有"), "provided")
        self.assertEqual(_status_branch("已提供同类资料"), _status_branch("待核"))
        self.assertEqual(_status_branch("待核验"), "pending")
        self.assertEqual(_status_branch("缺失"), "missing")
        self.assertEqual(_status_branch("待企业提交"), "missing")

    def test_no_markdown_in_runtime_text(self):
        """正文禁 markdown：上游字段里的 `**` 必须被清洗掉。"""
        import json
        from engine.self_doubt import doubt_for_problem
        p = _p_ev(tax_impact={"available": True, "basis": 1234.0,
                              "amount_context": "锚定金额为**含税**（价税合计）1,234.00 元"},
                  detail_table={"columns": [], "rows": []},
                  narrative_paragraphs=[])
        r = doubt_for_problem(p, provided_materials=[])
        self.assertNotIn("**", json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()


class TestSelfAuditSymmetry(unittest.TestCase):
    """★ 2026-10-06 **自审执行时暴露**的对称性缺陷。

    现象：非红线来源的 8 条（无证据角色表）自我怀疑**偏松** —— 支撑全标「中」、
    结论写「本项证据面相对完整」；而红线疑点动辄 4~5 条「弱」支撑 + 「不能认定」。
    ⇒ 同一份报告里，**越没做证据核对的项反而显得越扎实**（其中一条还是高风险）。
    """

    @staticmethod
    def _no_table(grade=None, tier="已验原子规则（可信观察）"):
        return {"seq": 9, "title": "测试：无证据角色表的项", "suspect": "",
                "evidence_tier": tier, "source": "域分析发现",
                "conclusion_grade": grade,
                "detail_table": {"columns": [], "rows": []},
                "narrative_paragraphs": [
                    {"heading": "三、已取得的资料与待补充的资料",
                     "text": "本项依据的独立数据源：进项发票（已上传）。"}]}

    def test_no_evidence_table_has_weak_support(self):
        """无证据角色表 ⇒ 必须有一条「弱」支撑（如实登记「未做证据核对」）。"""
        from engine.self_doubt import doubt_for_problem
        r = doubt_for_problem(self._no_table(), provided_materials=[])
        items = " ".join(str(k.get("item") or "") for k in r["key_inputs"])
        self.assertIn("证据核对状态", items, "必须如实登记「本项未做证据角色核对」")
        self.assertTrue([k for k in r["key_inputs"] if k.get("strength") == "弱"],
                        "无证据角色表的项不得呈现「全中」的假象")

    def test_no_evidence_table_never_says_evidence_complete(self):
        """无证据角色表 ⇒ 不得说「本项证据面相对完整」（那是无根据的自信）。"""
        from engine.self_doubt import doubt_for_problem
        r = doubt_for_problem(self._no_table(), provided_materials=[])
        self.assertNotIn("证据面相对完整", str(r.get("verdict_before_verify") or ""))
        self.assertIn("不能认定", str(r.get("verdict_before_verify") or ""))

    def test_with_evidence_table_semantics_unchanged(self):
        """有证据角色表时语义不变（避免「修一处、坏一处」）。"""
        from engine.self_doubt import doubt_for_problem
        p = {"seq": 1, "title": "t", "suspect": "",
             "detail_table": {"columns": [], "rows": [
                 {"证据角色": "直接证据", "证据名称": "x", "证明目的": "y", "现状": "已有"}]},
             "narrative_paragraphs": []}
        r = doubt_for_problem(p, provided_materials=[])
        self.assertNotIn("证据核对状态",
                         " ".join(str(k.get("item") or "") for k in r["key_inputs"]))
