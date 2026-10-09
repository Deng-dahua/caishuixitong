# -*- coding: utf-8 -*-
"""疑点主体一致性自检 —— 单元与行为测试（唯一权威 engine/subject_consistency）。

覆盖四类：
  ① 主体词判据：泛词不参与（"增值税"不能使两条不同税事项"同一主体"）；
  ② 红线归属声明：勾稽轴 → 红线的映射逐条自检通过，且**旧的错配归属会被拒绝**；
  ③ 附表准入：来源不在本疑点支撑发现内 → 拒绝（不是"按字面重叠"放行）；
  ④ 报告行为：真实 suspicions 结构下，错配内容不挂 + 如实说明 + 自检结论进报告字段。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ── ① 主体词判据 ────────────────────────────────────────────────────────────
class TestSubjectTerms:
    def test_generic_words_do_not_make_same_subject(self):
        """同一税种下的两件不同事，不得因为共有"增值税"就被判为同一主体。"""
        from engine.subject_consistency import same_subject
        assert not same_subject("附加税费计税依据与增值税不匹配",
                                "增值税进项税额对等逐月不匹配")

    def test_real_same_subject_recognised(self):
        from engine.subject_consistency import same_subject
        assert same_subject("成本列支的资金与负债证据不足：真实性待核",
                            "主营业务成本资金与负债支撑材料核验")
        assert same_subject("有进无销：大量进项无对应销售实现",
                            "有进无销：进项发票无对应销项")

    def test_period_brackets_stripped(self):
        from engine.subject_consistency import norm_subject_key, strip_period_brackets
        assert strip_period_brackets("待核事实：银行存款支出方对等逐月不匹配（2025-01）") \
            == "待核事实：银行存款支出方对等逐月不匹配"
        k = norm_subject_key("待核事实：银行存款支出方对等逐月不匹配（2025-01）")
        assert not any(c.isdigit() for c in k)


# ── ② 红线归属声明 / 勾稽轴映射 ─────────────────────────────────────────────
class TestAxisRedlineMap:
    def test_axis_map_selfcheck_passes(self):
        """轴 → 红线映射必须逐条通过主体自检（不过即拒绝声明，见 axis_redline）。"""
        from engine.subject_consistency import selfcheck_axis_map
        assert selfcheck_axis_map() == []

    @pytest.mark.parametrize("axis,expect", [
        ("银行存款支出方对等", "RL-FUND-005"),
        ("应付账款发生额对等", "RL-PTY-001"),
        ("增值税进项税额对等", "RL-CIT-008"),
        ("工资多源对等", "RL-PAY-002"),
        ("固定资产原值勾稽", "RL-AST-001"),
    ])
    def test_axis_maps_to_subject_matching_redline(self, axis, expect):
        from engine.subject_consistency import axis_redline
        assert axis_redline(axis)[0] == expect

    def test_fund_reconcile_axis_must_not_claim_spt010(self):
        """★ 2026-10-03（用户质询疑点23）：公积金**金额**勾稽轴不得挂 RL-SPT-010。

        RL-SPT-010 要证的是**人数与缴存基数**（未全员缴存 / 基数不实），
        而本轴比的是**金额**（缴存明细 vs 账簿"住房公积金"科目），且两者口径本就不同
        （明细常只列个人部分、科目含单位+个人）⇒ 相减的"差额"是口径差、不是少缴。
        公积金的人数/基数比对已由域8「工资社保比对」独立承担（见 tests/test_payroll_coverage.py）。
        """
        from engine.subject_consistency import axis_redline
        assert axis_redline("公积金缴存对等")[0] == ""

    def test_axis_without_matching_redline_declares_none(self):
        """账簿记录质量类勾稽轴（账账不符）没有主体对得上的红线 → 不声明，绝不套用。"""
        from engine.subject_consistency import axis_redline
        assert axis_redline("序时账与科目余额表逐科目不一致（账账不符）")[0] == ""

    def test_old_misattributions_are_rejected(self):
        """回归：修复前四处张冠李戴的归属，现在必须**不被允许**。"""
        from engine.subject_consistency import declared_subject_ok
        bad = [
            ("RL-COST-003", "待核事实：银行存款支出方对等逐月不匹配（2025-01）"),
            ("RL-COST-003", "待核事实：应付账款发生额对等逐月不匹配（2025-01）"),
            ("RL-COST-003", "待核事实：序时账与科目余额表逐科目不一致（账账不符）"),
            ("RL-VAT-002", "待核事实：增值税进项税额对等逐月不匹配（2025-01）"),
            ("RL-VAT-001", "待核事实：增值税销项税额对等逐月不匹配（2025-01）"),
            ("RL-INC-001", "待核事实：收入多源对等逐月不匹配（2025-01）"),
        ]
        # 新登记不得变成"开口子"：同红线下无关主体仍必须被拒
        _still_bad = [
            ("RL-FUND-001", "同一供应商同品名单价不一致"),
            ("RL-CIT-004", "工资表人数与社保参保人数不符"),
        ]
        for rid, subject in _still_bad:
            ok2, why2 = declared_subject_ok(rid, subject)
            assert ok2 is False, (rid, subject, why2)
        for rid, subject in bad:
            ok, why = declared_subject_ok(rid, subject)
            assert ok is False, (rid, subject, why)

    def test_legit_declarations_still_allowed(self):
        from engine.subject_consistency import declared_subject_ok
        good = [
            ("RL-COST-003", "待核事实：主营业务成本有票支撑偏低"),
            ("RL-COST-003", "待核事实：取得发票对成本费用合计的支撑不足"),
            ("RL-PTY-001", "主营业务成本资金与负债支撑材料核验"),
            ("RL-OTH-003", "城建税及教育费附加随增值税附征勾稽"),
            ("RL-CIT-008", "待核事实：增值税进项税额对等逐月不匹配（2025-01）"),
            # 由"自检误报"反推补登记的同类表述（同一件事的两种说法）
            ("RL-FUND-001", "需外部数据核实：对私资金往来对象实名与性质"),
            ("RL-CIT-004", "待核事实：企业所得税贡献率偏低"),
        ]
        for rid, subject in good:
            ok, why = declared_subject_ok(rid, subject)
            assert ok is True, (rid, subject, why)


# ── ②·B 建入口那条发现（entry）的选择 ────────────────────────────────────────
class TestEntrySelection:
    """疑点的 entry 决定标题口径/线索链/证据链/附表来源/自检基准，不得 first-finder-wins。"""

    def test_unrelated_soft_match_loses_to_declared_same_subject(self):
        """实测形态：软匹配来的无关发现排在前面，也必须让位给同主体的声明型发现。"""
        from engine.subject_consistency import pick_entry_index
        cands = [
            {"type": "同一供应商同品名单价不一致", "declared": False, "closure": 0.3},
            {"type": "文化事业建设费未申报（待核）", "declared": True, "closure": 0.1},
        ]
        i = pick_entry_index("RL-SPT-017", "广告/娱乐服务未申报文化事业建设费", cands)
        assert cands[i]["type"] == "文化事业建设费未申报（待核）"

    def test_subject_match_beats_declared_but_unrelated(self):
        """主体一致 > 声明型：一条声明错了红线的发现不得代表本红线。"""
        from engine.subject_consistency import pick_entry_index
        cands = [
            {"type": "主营业务成本有票支撑偏低", "declared": False, "closure": 0.9},
            {"type": "某无关发现", "declared": True, "closure": 0.9},
        ]
        assert pick_entry_index("RL-COST-003", "白条入账：无合规凭证列支成本费用", cands) == 0

    def test_declared_wins_within_same_subject_by_closure(self):
        from engine.subject_consistency import pick_entry_index
        cands = [
            {"type": "待核事实：主营业务成本有票支撑偏低", "declared": False, "closure": 0.8},
            {"type": "待核事实：取得发票对成本费用合计的支撑不足", "declared": True, "closure": 0.2},
        ]
        # 两条都主体一致：声明型得 3 分，压倒软匹配的 2 分
        assert pick_entry_index("RL-COST-003", "白条入账：无合规凭证列支成本费用", cands) == 1

    def test_empty_candidates_returns_zero(self):
        from engine.subject_consistency import pick_entry_index
        assert pick_entry_index("RL-X", "任意", []) == 0

    def test_detection_entry_is_subject_consistent(self):
        """端到端（生产函数）：无关软匹配发现不得成为 entry，且 match_mode 仍标 declared。"""
        from engine.redline_engine import run_redline_detection
        findings = [
            {"type": "同一供应商同品名单价不一致", "level": "待核验",
             "detail": "多张发票同一供应商同一品名单价差异超50%，如XX广告服务单价 1000/5000 元。"},
            {"type": "文化事业建设费未申报（待核）", "level": "待核验",
             "redline_id": "RL-SPT-017",
             "detail": "取得广告服务收入 1,000,000 元，未申报文化事业建设费。"},
        ]
        res = run_redline_detection(findings, material_readiness={"provided": ["销项发票"]})
        hit = [s for s in res["suspicions"] if s.get("redline_id") == "RL-SPT-017"]
        assert hit, res["suspicions"]
        s = hit[0]
        assert s.get("finding_type") == "文化事业建设费未申报（待核）", s.get("finding_type")
        assert s.get("match_mode") == "declared"
        # 无关发现仍如实保留（在支撑清单里、或按"未归入已知风险情形"登记，不得静默消失）
        assert any("单价不一致" in str(f.get("type") or "")
                   for f in (s.get("supporting_findings") or [])) or any(
            "单价不一致" in str(u.get("type") or "") for u in (res.get("unmapped") or []))


# ── ③ 附表准入 ──────────────────────────────────────────────────────────────class TestTableAttachment:
    def test_source_outside_support_rejected(self):
        from engine.subject_consistency import norm_subject_key, table_source_ok
        sup = {norm_subject_key("城建税及教育费附加随增值税附征勾稽")}
        ok, why = table_source_ok(sup, "待核事实：增值税进项税额对等逐月不匹配（2025-01）")
        assert ok is False and why

    def test_source_inside_support_accepted(self):
        from engine.subject_consistency import norm_subject_key, table_source_ok
        sup = {norm_subject_key("待核事实：银行存款支出方对等逐月不匹配（2025-01）")}
        ok, _ = table_source_ok(sup, "待核事实：银行存款支出方对等逐月不匹配（2025-02）")
        assert ok is True

    def test_no_support_declared_rejects_everything(self):
        from engine.subject_consistency import table_source_ok
        ok, _ = table_source_ok(set(), "任意表题")
        assert ok is False


# ── ④ 报告行为（真数据无关的构造式验证）────────────────────────────────────
class TestReportBehaviour:
    def _findings(self):
        return [
            {"type": "待核事实：银行存款支出方对等逐月不匹配（2025-01）",
             "level": "待核验", "redline_id": "RL-COST-003",
             "evidence_rows": [{"对方单位": "某某公司", "金额": 100}]},
            {"type": "待核事实：增值税进项税额对等逐月不匹配（2025-01）",
             "level": "待核验", "redline_id": "RL-VAT-002",
             "evidence_rows": [{"对方单位": "某某公司", "金额": 200}]},
        ]

    def _sus(self):
        # 模拟"白条入账"疑点：主体是白条入账，但引擎给它的支撑发现是银行支出对等
        return [{
            "redline_id": "RL-COST-003",
            "redline_name": "白条入账：无合规凭证列支成本费用",
            "suspect": "涉嫌以不合法凭证列支、税前扣除不实",
            "taxes": ["企业所得税"], "domain": "成本",
            "legal_basis": ["《发票管理办法》第二十条"],
            "constituents": ["成本费用列支无发票或其他合规外部凭证",
                             "以收据、白条、内部单据作为唯一扣除依据"],
            "constituent_sources": ["成本明细账", "记账凭证"],
            "clue_chain": {"terminal_signal": "2025-01 各来源金额不一致", "nodes": []},
            "evidence_chain": {}, "argumentation": {"verdict": "已触碰税务违规红线"},
            "finding_type": "待核事实：银行存款支出方对等逐月不匹配（2025-01）",
            "supporting_findings": [], "level": "待核验",
        }]

    def test_subject_mismatch_is_declared_and_audited(self):
        """主体与支撑发现不是同一件事 → 标题声明认定范围 + 自检留痕，且不隐藏事实。"""
        from engine.enterprise_report import _build_redline_problems, _build_subject_audit
        sink = {"issues": [], "by_code": {}}
        ps = _build_redline_problems(self._sus(), self._findings(), audit_sink=sink)
        assert len(ps) == 1
        au = _build_subject_audit(ps, sink)
        assert au["issue_count"] >= 1
        codes = {i["code"] for i in au["issues"]}
        assert "疑点主体与其证据不是同一件事" in codes
        assert "未就" in ps[0]["title"] or "未就" in (ps[0].get("premise_note") or "")

    def test_foreign_table_is_not_attached(self):
        """别的发现的表不得挂到本疑点（这是用户反复报的错配）。"""
        from engine.enterprise_report import _build_redline_problems
        ps = _build_redline_problems(self._sus(), self._findings())
        titles = [str((t or {}).get("title") or "")
                  for p in ps for para in (p.get("narrative_paragraphs") or [])
                  for t in (para.get("detail_tables") or [])]
        assert all("进项税额对等" not in t for t in titles)
        # 本项自己的明细必须还在（不能因为一致性把该有的表也删掉）
        assert any("银行存款支出方对等" in t for t in titles)

    def test_entry_finding_decides_subject_not_any_supporter(self):
        """主判据是**建入口那条发现**：名下另有一条同主体支撑发现也不放行。

        事故形态（实测）：疑点 RL-SPT-017「广告/娱乐服务未申报文化事业建设费」的 entry 是
        软匹配来的「同一供应商同品名单价不一致」，名下却另挂着正当的「文化事业建设费未申报（待核）」；
        旧判据因后者命中而"通过"，但正文线索链/证据链取自 entry，标题与内容仍错配。
        """
        from engine.enterprise_report import _build_redline_problems, _build_subject_audit
        findings = [{"type": "文化事业建设费未申报（待核）", "level": "待核验",
                     "evidence_rows": [{"对方单位": "某广告公司", "金额": 100}]}]
        sus = [{
            "redline_id": "RL-SPT-017",
            "redline_name": "广告/娱乐服务未申报文化事业建设费",
            "suspect": "涉嫌未申报文化事业建设费", "taxes": ["文化事业建设费"],
            "domain": "特定税种", "legal_basis": ["《文化事业建设费征收管理暂行办法》"],
            "constituents": ["提供广告服务并取得收入"],
            "constituent_sources": ["销项发票"],
            "clue_chain": {"terminal_signal": "广告服务收入 X 元未申报", "nodes": []},
            "evidence_chain": {}, "argumentation": {"verdict": "已触碰税务违规红线"},
            # entry = 另一件事；名下另有正当支撑发现
            "finding_type": "同一供应商同品名单价不一致",
            "supporting_findings": [{"type": "文化事业建设费未申报（待核）"}],
            "level": "待核验",
        }]
        sink = {"issues": [], "by_code": {}}
        ps = _build_redline_problems(sus, findings, audit_sink=sink)
        au = _build_subject_audit(ps, sink)
        codes = {i["code"] for i in au["issues"]}
        assert "疑点主体与其证据不是同一件事" in codes, au
        assert any("建入口的发现" in str(i.get("detail") or "") for i in au["issues"])


# ── ⑤ 事实引子：**引子来源必须与本项红线名是同一件事**（P0-4 根因治理）──────────
class TestEntrySubjectFloor:
    """事故形态（公司1 真实产物 R14 / RL-SPT-017）：

    疑点「广告/娱乐服务未申报文化事业建设费」的"为何列入检查"被写成
    「同一供应商同品名单价不一致（共5笔）…金额合计 0.00 元」——
    引子取自一张**主体与本项毫不相干**的附表（那张表来自建入口的软匹配发现）。

    根因：`_evidence_summary(_tables)` 概述的是**附表**，而附表可以来自
    `_ok_sub=False` 的建入口发现 ⇒ 用它当引子必然张冠李戴。
    修法：用 `subject_consistency.same_subject(来源发现类型, 红线名)` 逐张核，
    无一通过 ⇒ 引子退回线索链终局信号（本就是"本项为何触发"的口径），并留痕。

    ⚠ 只动引子、不动附表 —— 附表是本项**实际读到的证据**（既有测试
      `test_foreign_table_is_not_attached` 明确要求保留）。
    """

    def _run(self, entry_type):
        from engine.enterprise_report import _build_redline_problems
        findings = [{"type": entry_type, "level": "待核验", "redline_id": "RL-SPT-017",
                     "evidence_rows": [{"对方单位": "甲公司", "金额（元）": "0.00"},
                                       {"对方单位": "乙公司", "金额（元）": "0.00"}]}]
        sus = [{
            "redline_id": "RL-SPT-017",
            "redline_name": "广告/娱乐服务未申报文化事业建设费",
            "suspect": "涉嫌未申报文化事业建设费", "taxes": ["文化事业建设费"],
            "domain": "特定税种", "legal_basis": ["《文化事业建设费征收管理暂行办法》"],
            "constituents": ["提供广告服务并取得收入"],
            "constituent_sources": ["销项发票"],
            "clue_chain": {"terminal_signal": "检测到涉及「文化事业建设费未申报」的线索",
                           "nodes": []},
            "evidence_chain": {}, "argumentation": {"verdict": "已触碰税务违规红线"},
            "finding_type": entry_type, "supporting_findings": [], "level": "待核验",
        }]
        sink = {"issues": [], "by_code": {}}
        ps = _build_redline_problems(sus, findings, audit_sink=sink)
        txt = ""
        for p in ps:
            for para in (p.get("narrative_paragraphs") or []):
                if str(para.get("heading") or "") == "为何列入检查":
                    txt += str(para.get("text") or "")
        return ps, txt, sink

    def test_offtopic_annex_must_not_become_entry_reason(self):
        """① 附表来源与本项红线名不是同一件事 ⇒ 不得拿它的汇总当引子。"""
        _, txt, sink = self._run("同一供应商同品名单价不一致")
        assert "同一供应商同品名单价不一致" not in txt, txt[:200]
        # 必须退回本项自身的触发信号
        assert "文化事业建设费" in txt, txt[:200]
        # 且**留痕**（不静默）
        assert any("事实引子" in str(i) for i in (sink.get("issues") or [])), sink

    def test_reverse_ontopic_annex_still_used(self):
        """② 反向验证：附表来源**就是**本项主体 ⇒ 引子仍是"证据汇总"口径。

        若不通过（引子退回触发信号），说明上面的断言是"引子本来就空"的同义反复（假闸门）。
        `_evidence_summary` 的口径是"表题 + 本表 N 行 + 涉及 N 个对象 + 金额合计"，
        故用「本表」/「涉及」作为它的指纹；本项触发信号里不含这两个词。
        """
        _, txt, _ = self._run("文化事业建设费未申报（待核）")
        assert ("本表" in txt) or ("涉及" in txt), txt[:200]
