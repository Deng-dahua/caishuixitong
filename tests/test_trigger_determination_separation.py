# -*- coding: utf-8 -*-
"""触发条件与认定要件分离 —— 单元 / 集成 / 回归测试。

对应用户规格（2026-10-07）：
  单元：疑点1 / 3 / 4 / 12 的触发条件命中、第1条认定要件（前提条）必须写「符合情形」
  集成：全部风险指标都必须同时定义触发条件与认定要件；前提条必须被判「符合情形」
  回归：门禁 `check_trigger_determination_separation` 的配置级判据必须无 ERROR

关键回归点：疑点 3 / 4 / 12 的第1条要件文本里**没有**"现象/前提条"字样
（"…存在差异"、"…不闭合"），只能靠**结构化 `is_precondition`** 判定 ——
这正是本轮修复的核心（词表兜底会漏判）。
"""
from __future__ import annotations
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: 用户点名的 4 个回归样例：(risk_code, 第1条要件原文（取自真实红线）, 触发读数)
SAMPLES = [
    ("RL-VAT-007", "存在红字发票或作废发票（红冲行为）——本项为现象/前提条，存在即成立，"
                   "不设比例阈值；占比只作证据", "共13张发票涉及红冲/作废：红字发票13张、作废0张"),
    ("RL-PAY-001", "工资表列支人数与社保参保人数存在差异", "工资表6人、社保5人，差1人"),
    ("RL-INC-001", "银行账户经营性入账金额与同期申报收入、开票收入存在差异",
                   "9个月差异同时超过25%和10万元"),
    ("RL-AST-001", "固定资产入账、投入使用、计提折旧的时点链条不闭合", "银行流水发现2笔固定资产付款"),
]

#: 各疑点的后续要件（非前提条，应停在"待核实"）
TAILS = {
    "RL-VAT-007": ["红冲发生在月末、季末或申报期前后等敏感时点", "红冲无对应退货单、折让协议等合法事由"],
    "RL-PAY-001": ["差异人员不属于劳务派遣、退休返聘、实习生、非全日制等依法免缴社保的情形"],
    "RL-INC-001": ["上述差额占申报收入比例超过行业基准税负率区间上沿"],
    "RL-AST-001": ["已提折旧但无投用记录，或已投用但未见折旧计提"],
}


# ══════════════════ 单元测试（4 个用户样例） ══════════════════
class TestUnitSamples:
    @pytest.mark.parametrize("risk_code,first,tail_reading", SAMPLES)
    def test_precondition_is_judged_conforming(self, risk_code, first, tail_reading):
        """第1条认定要件（前提条）必须写「符合情形」，**不得**写「未形成核对结论」。"""
        from engine.constituent_checkpoint import build_constituent_checkpoints
        cons = [first] + TAILS[risk_code]
        cps = build_constituent_checkpoints({"redline_id": risk_code, "constituents": cons},
                                            {risk_code: {}})
        c1 = cps[0]
        assert c1["_premise"] is True, "第1条应被识别为前提条（结构化 is_precondition）"
        assert c1["_conclusion"] == "checked_hit"
        assert c1["核对结论"].startswith("符合情形"), c1["核对结论"]
        assert "未形成核对结论" not in c1["核对结论"]
        assert "未单独核对" not in c1["核对结论"]
        # 后续要件仍为待核实（不得被一并判"符合"）
        assert any(c["_conclusion"] in ("not_concluded", "not_checked") for c in cps[1:])

    @pytest.mark.parametrize("risk_code,first,tail_reading", SAMPLES)
    def test_trigger_hit_and_layered_verdict(self, risk_code, first, tail_reading):
        """触发条件命中 ⇒ 疑点成立；认定要件未完 ⇒ 风险不成立；结论句含三要素。"""
        from engine.trigger_conditions import classify
        from engine.constituent_checkpoint import build_constituent_checkpoints
        cons = [first] + TAILS[risk_code]
        cps = build_constituent_checkpoints({"redline_id": risk_code, "constituents": cons},
                                            {risk_code: {}})
        r = classify(risk_code, cps, cons, reading=tail_reading)
        assert r["risk_code"] == risk_code
        assert r["trigger_status"]["hit_count"] >= 1, "已列为疑点却无触发条件命中"
        assert r["suspicion_established"] is True
        assert r["risk_established"] is False
        assert len(r["determination_criteria"]) == len(cons)
        assert r["determination_criteria"][0]["is_precondition"] is True
        assert all(c["is_precondition"] is False for c in r["determination_criteria"][1:])
        s = r["conclusion"]
        assert "本项因触发条件" in s and "而列为疑点" in s
        assert "认定要件共" in s and "已满足" in s and "待核实" in s
        assert "疑点成立" in s
        assert ("风险是否成立待定" in s) or ("风险成立" in s)

    def test_text_marker_is_not_required(self):
        """回归核心：**不含**"现象/前提条"字样的第1条也必须被判前提条（结构化优先）。"""
        from engine.trigger_conditions import is_premise_constituent, is_precondition
        raw = "工资表列支人数与社保参保人数存在差异"
        assert is_premise_constituent(raw) is False, "该文本不含词表标记（确认回归点成立）"
        assert is_precondition("RL-PAY-001", 1, raw) is True, "结构化字段必须判为前提条"

    def test_precondition_not_triggered_then_not_listed(self):
        """前提条未满足 ⇒ 不列为疑点（触发条件未命中的情形）。"""
        from engine.trigger_conditions import classify
        r = classify("RL-PAY-001", [], [], reading="", listed=False)
        assert r["suspicion_established"] is False


# ══════════════════ 集成测试（全部风险指标） ══════════════════
class TestIntegrationAllRisks:
    def test_every_risk_defines_both_sides(self):
        """每条风险指标都必须同时定义触发条件与认定要件（用户"通用性要求"）。"""
        from engine.trigger_conditions import load_risk_conditions
        risks = [r for r in (load_risk_conditions().get("risks") or []) if isinstance(r, dict)]
        assert len(risks) >= 80, "风险指标配置疑似未生成"
        for r in risks:
            rc = r.get("risk_code")
            assert r.get("trigger_conditions"), "%s 缺触发条件" % rc
            assert r.get("determination_criteria"), "%s 缺认定要件" % rc

    def test_all_precondition_criteria_judged_conforming(self):
        """**全量遍历**：凡标记为前提条的认定要件，核对应判「符合情形」。"""
        from engine.trigger_conditions import load_risk_conditions, is_precondition
        from engine.constituent_checkpoint import build_constituent_checkpoints
        bad = []
        for r in (load_risk_conditions().get("risks") or []):
            if not isinstance(r, dict):
                continue
            rc = str(r.get("risk_code") or "")
            cons = [str(c.get("desc") or "") for c in (r.get("determination_criteria") or [])]
            if not cons:
                continue
            cps = build_constituent_checkpoints({"redline_id": rc, "constituents": cons}, {rc: {}})
            for c in cps:
                if is_precondition(rc, int(c.get("index") or 0), c.get("要件")):
                    if c.get("_conclusion") != "checked_hit" or not str(c.get("核对结论")).startswith("符合情形"):
                        bad.append((rc, c.get("index"), c.get("核对结论")))
        assert bad == [], "存在前提条未判「符合情形」：%s" % bad[:5]

    def test_no_listed_problem_without_trigger(self):
        """不得出现"已列为疑点"但"未触发任何触发条件"。"""
        from engine.trigger_conditions import classify
        from engine.constituent_checkpoint import build_constituent_checkpoints
        for rc, first, reading in SAMPLES:
            cons = [first] + TAILS[rc]
            cps = build_constituent_checkpoints({"redline_id": rc, "constituents": cons}, {rc: {}})
            r = classify(rc, cps, cons, reading=reading)
            assert r["suspicion_established"] is True
            assert r["trigger_status"]["hit_count"] >= 1


# ══════════════════ 回归测试（门禁配置级判据） ══════════════════
class TestGateRegression:
    def test_gate_config_level_clean(self):
        """门禁不得对**配置**报 ERROR（产物级判定允许 WARN"无真跑产物"）。"""
        from tools.audit_consistency import check_trigger_determination_separation
        errs = [i for i in check_trigger_determination_separation()
                if i[0] == "ERROR" and "risk_conditions.json" in i[1]]
        assert errs == [], "配置级门禁未通过：%s" % errs[:3]

    def test_pm_phrase_removed_from_templates(self):
        """回归：病句「未涉及任何一条构成要件」不得再作为模板句产出。"""
        src = (ROOT / "engine" / "enterprise_report.py").read_text(encoding="utf-8")
        import re as _re
        # 只允许出现在注释里
        for i, line in enumerate(src.split("\n"), 1):
            if "未涉及任何一条构成要件" in line and not line.lstrip().startswith("#"):
                pytest.fail("第 %d 行仍在代码里产出病句：%s" % (i, line.strip()[:80]))


# ══════════════════ 规格【输出】结构化落盘（2026-10-07 补） ══════════════════
class TestStructuredOutput:
    """规格【输出】8 字段必须**落进产物**（此前只有文本渲染，没有结构化数据）。"""

    FIELD_MIN = ("risk_code", "trigger_conditions", "trigger_status",
                 "determination_criteria", "criterion_status",
                 "suspicion_established", "risk_established", "conclusion")
    #: 用户点名疑点 → 红线编号（实测 seq 映射）
    #: ★ 2026-10-09 重排留痕：P0-5「结论等级 → 风险等级上限」上线 ⇒ L2 待核线索降为低风险
    #:   ⇒ seq 按（等级序, 敞口降序）重排（PAY-001 3→7、INC-001 4→2、AST-001 12→9）。
    #:   已逐条重核前提条断言（C1 为要件、文本含「符合情形」）在新编号下均成立。
    SAMPLE_SEQ = {1: "RL-VAT-007", 2: "RL-INC-001", 7: "RL-PAY-001", 9: "RL-AST-001"}

    @staticmethod
    def _problems():
        import json
        rep = json.loads((ROOT / "scripts" / "four_reports" / "company_1_full.json")
                         .read_text(encoding="utf-8"))
        er = rep.get("enterprise_readable_report") or rep
        return [p for p in (er.get("confirmed_problems") or []) if isinstance(p, dict)]

    def test_every_problem_has_full_structured_block(self):
        probs = self._problems()
        assert probs, "产物为空"
        for p in probs:
            blk = p.get("trigger_determination")
            assert isinstance(blk, dict), (p.get("seq"), "缺 trigger_determination")
            for f in self.FIELD_MIN:
                assert f in blk, (p.get("seq"), f)
            assert blk["trigger_conditions"], (p.get("seq"), "触发条件为空")
            # 认定要件非空只对有要件核对表的疑点要求（无红线绑定的综合疑点认定要件为空是如实）
            _has_ck = any("构成要件" in str((tb or {}).get("title") or "")
                          for np_ in (p.get("narrative_paragraphs") or [])
                          if isinstance(np_, dict)
                          for tb in (np_.get("detail_tables") or []))
            if _has_ck:
                assert blk["determination_criteria"], (p.get("seq"), "认定要件为空")

    def test_trigger_hit_iff_suspicion_established(self):
        """双向一致：触发命中 ⇔ 疑点成立（不得"已列为疑点却无命中触发条件"）。"""
        for p in self._problems():
            blk = p["trigger_determination"]
            hit = int((blk.get("trigger_status") or {}).get("hit_count") or 0)
            assert bool(blk["suspicion_established"]) == bool(hit > 0), (p.get("seq"), hit)

    def test_criteria_and_status_one_to_one(self):
        for p in self._problems():
            blk = p["trigger_determination"]
            ids = sorted(str(c.get("id")) for c in blk["determination_criteria"])
            assert ids == sorted(str(k) for k in blk["criterion_status"]), p.get("seq")

    @pytest.mark.parametrize("seq,risk_code", sorted(SAMPLE_SEQ.items()))
    def test_sample_first_criterion_is_conforming(self, seq, risk_code):
        """样例疑点的第 1 条（前提条）必须写「符合情形」，不得写「未形成核对结论」。

        ★ 2026-10-18：改为**按 risk_code 定位**，不再按 seq 定位。
        原因：本用例原本断言 `seq=7 ⇔ RL-PAY-001`，这是**数据依赖的硬编码** ——
        产物重生后疑点从 18 条变 24 条，seq 随之重排（RL-PAY-001 由 7→8），
        用例就变成"因为编号变了所以失败"，**测的不再是判据本身**。
        按代码定位后语义完全不变（仍要求这 4 个风险的前提条写「符合情形」），
        且不再受疑点条数波动影响。保留 `seq` 参数只为记录历史编号。
        """
        p = [x for x in self._problems()
             if (x.get("trigger_determination") or {}).get("risk_code") == risk_code]
        assert p, "风险 %s 不在产物里（产物可能未重生）" % risk_code
        blk = p[0]["trigger_determination"]
        assert blk["risk_code"] == risk_code, blk["risk_code"]
        first = [c for c in blk["determination_criteria"] if str(c.get("id")) == "C1"]
        assert first, [c.get("id") for c in blk["determination_criteria"]]
        assert first[0]["is_precondition"] is True, first[0]
        txt = str((blk["criterion_status"].get("C1") or {}).get("text") or "")
        assert "符合情形" in txt, txt
        assert "未形成核对结论" not in txt, txt


class TestGateReverseValidation:
    """门禁反向验证（规格明确要求的两条）。"""

    def test_reverse_trigger_not_hit_but_listed(self, monkeypatch):
        """构造"触发条件未命中却列为疑点" ⇒ 门禁必须报错。"""
        import tools.audit_consistency as A
        fake = {"enterprise_readable_report": {"confirmed_problems": [{
            "redline_id": "RL-ZZZ-999", "title": "反向验证用疑点",
            "trigger_determination": {
                "risk_code": "RL-ZZZ-999",
                "trigger_conditions": [{"id": "T1", "desc": "某触发条件"}],
                "trigger_status": {"hit_count": 0, "listed": True,
                                   "conditions": [{"id": "T1", "hit": False}]},
                "determination_criteria": [{"id": "C1", "desc": "某要件",
                                            "is_precondition": True}],
                "criterion_status": {"C1": {"status": "checked_hit",
                                            "text": "符合情形（本项为现象/前提条，存在即成立）",
                                            "is_precondition": True}},
                "suspicion_established": True,     # ← 矛盾点：命中 0 却"成立"
                "risk_established": False, "conclusion": "……"}}]}}
        monkeypatch.setattr(A, "_canonical_report", lambda: fake)
        errs = [i for i in A.check_trigger_determination_separation() if i[0] == "ERROR"]
        assert any("不一致" in i[2] or "触发" in i[2] for i in errs), errs[:3]

    def test_reverse_precondition_not_conforming(self, monkeypatch):
        """构造"前提条已满足却写未形成核对结论" ⇒ 门禁必须报错。"""
        import tools.audit_consistency as A
        fake = {"enterprise_readable_report": {"confirmed_problems": [{
            "redline_id": "RL-ZZZ-999", "title": "反向验证用疑点",
            "trigger_determination": {
                "risk_code": "RL-ZZZ-999",
                "trigger_conditions": [{"id": "T1", "desc": "某触发条件"}],
                "trigger_status": {"hit_count": 1, "listed": True,
                                   "conditions": [{"id": "T1", "hit": True}]},
                "determination_criteria": [{"id": "C1", "desc": "现象条",
                                            "is_precondition": True}],
                "criterion_status": {"C1": {"status": "not_concluded",
                                            "text": "未形成核对结论（资料已取得但缺对应核对证据）",
                                            "is_precondition": True}},
                "suspicion_established": True, "risk_established": False,
                "conclusion": "……"}}]}}
        monkeypatch.setattr(A, "_canonical_report", lambda: fake)
        errs = [i for i in A.check_trigger_determination_separation() if i[0] == "ERROR"]
        assert any("前提条" in i[2] for i in errs), errs[:3]

    def test_reverse_missing_block(self, monkeypatch):
        """构造"疑点没有结构化块" ⇒ 门禁必须报错。"""
        import tools.audit_consistency as A
        fake = {"enterprise_readable_report": {"confirmed_problems": [
            {"redline_id": "RL-ZZZ-999", "title": "反向验证用疑点"}]}}
        monkeypatch.setattr(A, "_canonical_report", lambda: fake)
        errs = [i for i in A.check_trigger_determination_separation() if i[0] == "ERROR"]
        assert any("trigger_determination" in i[2] for i in errs), errs[:3]


class TestManualEntriesNotClobbered:
    """反向锁：**人工登记的 `aliases` 条目不得被生成器覆盖**（2026-10-07 实测事故）。

    事故：本批收口时先跑 `scripts/_gen_risk_conditions.py`（当时是"纯覆盖"）⇒ 3 条
    "无红线/规则键控"的人工登记条目**被静默删掉**（94 → 91），触发源绑定从 16/16 退化回
    13/16，且配置里的 `aliases` 字段一并消失。修法：生成器新增**人工撰写层**；
    本用例锁住"人工条目必须被保留"。
    """

    MANUAL_IDS = ("VR012", "VR019", "SYN-MULTI-TAX-PROFILE")

    def test_config_keeps_manual_entries(self):
        import json
        cfg = json.loads((ROOT / "config" / "risk_conditions.json").read_text(encoding="utf-8"))
        ids = {str(r.get("risk_code")) for r in (cfg.get("risks") or [])}
        for m in self.MANUAL_IDS:
            assert m in ids, "人工登记条目 %s 丢失（配置被生成器覆盖？）" % m
        assert "aliases" in (cfg.get("fields") or []), "配置声明缺 aliases 字段"

    def test_generator_preserves_manual_layer(self):
        """生成器的"人工撰写层"必须把非派生条目识别为保留对象。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_gen_risk_conditions", ROOT / "scripts" / "_gen_risk_conditions.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # 传一个"只含红线派生编号"的集合 ⇒ 3 条人工条目应被识别为需保留
        kept = mod._existing_manual_entries({"RL-VAT-007", "RL-PAY-001"})
        ids = {str(r.get("risk_code")) for r in (kept.get("manual") or [])}
        for m in self.MANUAL_IDS:
            assert m in ids, "人工撰写层未识别出 %s" % m
        assert kept.get("aliases"), "人工撰写层未保留 aliases 字段"

    def test_alias_entries_have_both_sides(self):
        """人工条目同样必须"触发条件 + 认定要件"齐备（用户规格第 1 条）。"""
        from engine.trigger_conditions import trigger_conditions_of, determination_criteria_of
        for m in self.MANUAL_IDS:
            assert trigger_conditions_of(m), m
            assert determination_criteria_of(m), m
            assert determination_criteria_of(m)[0].get("is_precondition") is True, m
