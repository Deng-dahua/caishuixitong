# -*- coding: utf-8 -*-
"""五项报告质量 Skill 的测试用例（含用户指定的**失败样例 / 通过样例**）。

    Skill 1 触发条件与认定要件分离 ...... TestTriggerConstituentSeparation
    Skill 2 金额口径取舍 ................ TestAmountScopeSingleFinal
    Skill 3 字段截断与完整性 ............ TestFieldCompleteness
    Skill 4 占位符与空内容 .............. TestContentPlaceholderGuard
    Skill 5 报告性质一致性 .............. TestReportIdentity
    Skill 登记表与接线一致性 ............ TestSkillWiringConsistency

每个用例都成对出现：`test_*_fail_sample_*`（修复前的失败样例，断言"必须被识别为问题"）
与 `test_*_pass_sample_*`（修复后的通过样例，断言"不再被判为问题/输出符合口径"）。
"""
from __future__ import annotations
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ══════════════════ Skill 1：触发条件与认定要件分离 ══════════════════
class TestTriggerConstituentSeparation:
    #: 红线原文（RL-* 关于红冲/作废发票）——**用户问题1 的原始样本**
    TL = ("存在红字发票或作废发票（红冲行为）——本项为现象/前提条，存在即成立，"
          "不设比例阈值；占比只作证据")
    OTHER = ("红冲无对应退货单、折让协议等合法事由（独立数据源：退货单、折让协议）")

    def test_fail_sample_1_premise_was_not_concluded(self):
        """失败样例（用户疑点1）：已检出 13 张红字发票，第1条**不得**判「未形成核对结论」。"""
        from engine.constituent_checkpoint import build_constituent_checkpoints
        cps = build_constituent_checkpoints(
            {"redline_id": "RL-TEST-1", "constituents": [self.TL, self.OTHER]},
            {"RL-TEST-1": {1: "共13张发票涉及红冲/作废：其中红字发票（红冲）13张、作废0张"}},
        )
        c1 = cps[0]
        assert c1["index"] == 1
        # 前提条已满足 ⇒ 必须是「符合情形」
        assert c1["_conclusion"] == "checked_hit", (
            "前提条（存在即成立）在已检出 13 张红字发票时必须判「符合情形」，"
            "不得落 not_concluded（未形成核对结论）")
        assert c1["核对结论"].startswith("符合情形")
        assert c1["参与认定"] is True

    def test_pass_sample_1_verdict_sentence_layers_correctly(self):
        """通过样例：结论句须写「触发条件→要件共N条已满足M条待核实K条→疑点成立、风险待定」。"""
        from engine.trigger_conditions import verdict_sentence, rollup
        cps = [
            {"index": 1, "_conclusion": "checked_hit"},
            {"index": 2, "_conclusion": "not_concluded"},
            {"index": 3, "_conclusion": "not_checked"},
        ]
        cons = [self.TL, "红冲发生在月末等敏感时点", self.OTHER]
        s = verdict_sentence(cps, cons)
        assert "本项因触发条件" in s
        assert "认定要件共 3 条：已满足 1 条、待核实 2 条" in s
        assert "疑点成立" in s and "风险是否成立待定" in s
        r = rollup(cps, cons)
        assert r["premise_satisfied"] == 1 and r["suspicion_ok"] is True
        assert r["risk_ok"] is False, "其余要件待核实时，风险不得判成立"

    def test_premise_indices_and_marker_driven(self):
        """词表驱动：新增同类只加一行数据（不针对任何一条具体红线）。"""
        from engine.trigger_conditions import is_premise_constituent, premise_indices
        assert is_premise_constituent(self.TL) is True
        assert is_premise_constituent(self.OTHER) is False
        assert premise_indices([self.TL, self.OTHER, "存在即成立：票种为专票"]) == [1, 3]

    def test_no_conclusion_when_no_constituents(self):
        """取不到要件 ⇒ 返回空结论句（不臆造"已满足"）。"""
        from engine.trigger_conditions import verdict_sentence
        assert verdict_sentence([], []) == ""


# ══════════════════ Skill 2：金额口径取舍 ══════════════════
class TestAmountScopeSingleFinal:
    GROSS = 1734859.35
    NET = 227659.35

    def test_fail_sample_2_two_scopes_coexist(self):
        """失败样例（用户疑点4）：毛差额与净敞口并存时，**必须**指明唯一最终口径。"""
        from engine.amount_scope_choice import choose
        c = choose(self.GROSS, self.NET)
        assert c["final_source"] == "net", "有净敞口时最终口径必须是净敞口"
        assert c["final"] == pytest.approx(self.NET, rel=1e-9)
        assert c["gross"] == pytest.approx(self.GROSS, rel=1e-9)
        assert c["gross_note"], "毛差额必须带标注（不得裸列）"

    def test_pass_sample_2_sentence_marks_gross_as_reference_only(self):
        """通过样例：报告句以净敞口为准，毛差额标注「仅作起点参考，不作为最终风险敞口」。"""
        from engine.amount_scope_choice import exposure_sentence, NOTE_GROSS_ONLY
        s = exposure_sentence(self.GROSS, self.NET, item="未开票/账外敞口")
        assert "227,659.35" in s and "最终口径" in s
        assert "1,734,859.35" in s and NOTE_GROSS_ONLY in s

    def test_unquantified_never_substituted_by_gross(self):
        """缺失≠顶替：净敞口未测算时**不得**拿毛差额当最终口径。"""
        from engine.amount_scope_choice import choose, exposure_sentence
        c = choose(self.GROSS, None)
        assert c["final"] is None and c["final_source"] == "none"
        s = exposure_sentence(self.GROSS, None)
        assert "净敞口未测算" in s and "仅作起点参考" in s


# ══════════════════ Skill 3：字段截断与完整性 ══════════════════
class TestFieldCompleteness:
    PERIOD = "2025-01 至 2025-12"

    def test_fail_sample_3_month_truncated(self):
        """失败样例（用户疑点3）：12 个月期间只列到 10 月且无省略号 ⇒ 必须报出。"""
        from engine.field_completeness import check_text
        text = ("初永伟：工资 30,000.00 元，社保缴费基数仅 6,000.00 元（20.00%）；"
                "涉及月份 2025-01、2025-02、2025-03、2025-04、2025-05、2025-06、"
                "2025-07、2025-08、2025-09、2025-10")
        kinds = {i["kind"] for i in check_text(text, self.PERIOD)}
        assert "month_gap" in kinds, "缺少 2025-11/2025-12 必须报 month_gap"
        assert "silent_truncation" in kinds, "无省略号、无范围声明 ⇒ 必须报 silent_truncation"

    def test_pass_sample_3_full_months(self):
        """通过样例：12 个月完整 ⇒ 无问题。"""
        from engine.field_completeness import check_text
        text = ("初永伟：工资 30,000.00 元；涉及月份 " +
                "、".join("2025-%02d" % m for m in range(1, 13)))
        assert check_text(text, self.PERIOD) == []

    def test_truncation_with_mark_is_visible_not_silent(self):
        """截断**可见**（省略号或范围声明）⇒ 不算静默截断。"""
        from engine.field_completeness import check_text
        text = "涉及月份 2025-01、2025-02、…（共 12 个月，此处列示前 2 个）"
        assert [i for i in check_text(text, self.PERIOD) if i["kind"] == "silent_truncation"] == []

    def test_period_unknown_is_not_silent_pass(self):
        """检查期间取不到 ⇒ 显式声明"无法判定"，不得默认通过。"""
        from engine.field_completeness import parse_period, coverage_line
        assert parse_period("") == []
        assert "无法判定" in coverage_line("")
        assert len(parse_period(self.PERIOD)) == 12


# ══════════════════ Skill 4：占位符与空内容 ══════════════════
class TestContentPlaceholderGuard:
    ORPHAN = "要把这一项查清楚，需要："
    NORMAL = "要把这一项查清楚，需要：进项发票——证明采购的金额、税额与供方"

    def test_fail_sample_4_orphan_lead_detected(self):
        """失败样例（文末「说明2」）：孤立引导句必须被识别。"""
        from engine.content_placeholder_guard import is_orphan_lead, scan
        assert is_orphan_lead(self.ORPHAN) is True
        issues = scan(["说明1。 整改过程中不得倒签、补造、篡改、删除或隐匿资料。",
                       self.ORPHAN])
        kinds = {i["kind"] for i in issues}
        assert "orphan_lead" in kinds

    def test_pass_sample_4_normal_lead_with_body(self):
        """通过样例：带正文的引导句**不得**被误判（防误伤）。"""
        from engine.content_placeholder_guard import is_orphan_lead
        assert is_orphan_lead(self.NORMAL) is False

    def test_empty_and_placeholder(self):
        from engine.content_placeholder_guard import is_empty, is_placeholder, assert_clean
        assert is_empty("   ") is True
        assert is_placeholder("待补充") is True
        assert is_placeholder("待补充资料：合同文件与银行流水原件") is False, "正常句子不得误判"
        with pytest.raises(ValueError):
            assert_clean([self.ORPHAN])


# ══════════════════ Skill 5：报告性质一致性 ══════════════════
class TestReportIdentity:
    def test_fail_sample_5_alias_mixed(self):
        """失败样例：出现历史别名 ⇒ 必须报出。"""
        from engine.report_identity import canonical_name, scan_names
        cn = canonical_name()
        issues = scan_names(["本报告为内部辅助分析草稿"])
        assert issues and any(i["kind"] == "alias_used" for i in issues)
        assert cn not in issues[0]["detail"].split("应统一为")[0], "唯一名称本身不得被当成别名"

    def test_pass_sample_5_unified(self):
        """通过样例：三处（标题/文末声明/报告定位）统一为唯一名称。"""
        from engine.report_identity import canonical_name, consistency_report, unify, identity_line
        cn = canonical_name()
        assert cn == "内部辅助分析工作底稿"
        assert unify("本报告为内部辅助分析草稿") == "本报告为" + cn
        assert consistency_report(cn, identity_line(), cn) == []

    def test_consistency_reports_missing_and_mismatch(self):
        from engine.report_identity import consistency_report
        kinds = {i["kind"] for i in consistency_report("", "文末另一种说法", "内部辅助分析草稿")}
        assert "identity_missing" in kinds and "identity_mismatch" in kinds

    def test_name_authority_is_forwarded_by_template(self):
        """唯一权威贯通：合规模板的名称必须等于 `report_identity` 的唯一名称。"""
        from engine.report_compliance import document_meta
        from engine.report_identity import canonical_name
        assert document_meta().get("name") == canonical_name()


# ══════════════════ Skill 登记表与接线一致性（跨模块） ══════════════════
class TestSkillWiringConsistency:
    """跨模块一致性：登记表 / 接线闸门 —— 防"文档说做了、代码没接"。"""

    def test_skill_registry_valid(self):
        from engine.skill_registry import validate, spec_of
        assert validate() == []
        for sid in ("trigger_constituent_separation", "amount_scope_single_final",
                    "field_completeness", "content_placeholder_guard", "report_identity"):
            s = spec_of(sid)
            assert s is not None, "Skill 未登记：%s" % sid
            assert s["version"].count(".") == 2
            assert s["tests"], "必须声明测试文件"

    def test_wiring_gate_is_clean(self):
        """五项 Skill 的接线闸门必须为 0（模块存在 ≠ 接上了线）。"""
        from tools.audit_consistency import check_report_quality_skill_wiring
        assert check_report_quality_skill_wiring() == []

    def test_config_name_single_source(self):
        """报告名称只有一处权威：配置与代码口径一致。"""
        import json
        from engine.report_identity import canonical_name
        cfg = json.loads((ROOT / "config" / "report_identity.json").read_text(encoding="utf-8"))
        comp = json.loads((ROOT / "config" / "report_compliance.json").read_text(encoding="utf-8"))
        cn = canonical_name()
        assert cfg["canonical"] == cn
        assert comp["documents"]["internal_working_paper"]["name"] == cn
