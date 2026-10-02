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
        ("公积金缴存对等", "RL-SPT-010"),
        ("固定资产原值勾稽", "RL-AST-001"),
    ])
    def test_axis_maps_to_subject_matching_redline(self, axis, expect):
        from engine.subject_consistency import axis_redline
        assert axis_redline(axis)[0] == expect

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
        ]
        for rid, subject in good:
            ok, why = declared_subject_ok(rid, subject)
            assert ok is True, (rid, subject, why)


# ── ③ 附表准入 ──────────────────────────────────────────────────────────────
class TestTableAttachment:
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
