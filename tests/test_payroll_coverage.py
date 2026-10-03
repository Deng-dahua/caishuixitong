# -*- coding: utf-8 -*-
"""公积金（住房公积金）用工三方比对 —— 回归测试（2026-10-03）

背景（用户质询「疑点23 又操蛋了，怎么得来了？」）：
  公积金此前**从未接入**域8 的用工比对（函数名叫 `..._ss_hf_compare`，签名却没有 housing_fund）。
  它只被「金额对等勾稽」轴捞走（缴存明细的**个人**部分 vs 账簿科目的**单位+个人**），
  贴上了 RL-SPT-010 的名字，于是：
    · 触发依据是**口径差**造成的假差额（实测 1,200 vs 2,400）；
    · 真正的人数差异（杨莹未缴存）与基数不实（全员按 6,000 最低基数）**一条也没算**。

本测试锁定修复后的契约：**人数与基数的真实性由域8 三方比对负责，金额勾稽不冒充人数结论**。
"""

from __future__ import annotations

import pytest


# ── payroll_rules：口径判定与字段访问器（唯一权威）─────────────────────────────
class TestHousingFundRules:

    def test_scope_personal_when_equal_to_salary_deduct(self):
        """明细合计 == 工资表个人扣缴合计 ⇒ 判定为"个人缴存部分"。"""
        from engine.payroll_rules import hf_detail_scope, HF_SCOPE_PERSONAL
        assert hf_detail_scope(1200.0, 1200.0) == HF_SCOPE_PERSONAL

    def test_scope_unit_total_when_doubled(self):
        """明细合计 ≈ 个人扣缴的 2 倍（含单位部分）⇒ 非个人口径。"""
        from engine.payroll_rules import hf_detail_scope, HF_SCOPE_UNIT_TOTAL
        assert hf_detail_scope(2400.0, 1200.0) == HF_SCOPE_UNIT_TOTAL

    def test_scope_unknown_without_salary_side(self):
        """无从判定时**不臆测**（缺工资表 ⇒ unknown）。"""
        from engine.payroll_rules import hf_detail_scope, HF_SCOPE_UNKNOWN
        assert hf_detail_scope(1200.0, 0.0) == HF_SCOPE_UNKNOWN
        assert hf_detail_scope(0.0, 1200.0) == HF_SCOPE_UNKNOWN

    def test_field_accessors_read_synthetic_counterparty_month(self):
        """公积金明细月份落在合成列名 `counterparty` 上（通用表格解析产物）。"""
        from engine.payroll_rules import hf_month, hf_person, hf_amount
        row = {"person_name": "徐瑶", "id_number": "362204199310096142",
               "counterparty": "2025-01", "amount_col": "300"}
        assert hf_month(row) == "2025-01"
        assert hf_person(row) == "徐瑶"
        assert hf_amount(row) == 300.0

    def test_hf_min_ratio_is_legal_floor(self):
        """法定最低缴存比例 5%（《住房公积金管理条例》第十八条）。"""
        from engine.payroll_rules import HF_MIN_RATIO
        assert HF_MIN_RATIO == 0.05


# ── material_names：公积金缴存明细必须可归类 ──────────────────────────────────
class TestHousingFundMaterialNaming:

    def test_hf_detail_classified_as_social_security(self):
        from engine.material_names import canonical, strict_categories_all
        assert canonical("住房公积金缴存明细") == "社保明细"
        # 要件数据源整串须能全部归类（否则要件永远"未单独核对"）
        assert strict_categories_all("住房公积金缴存明细、工资表、社保参保明细") == ["社保明细", "工资表"]

    def test_registration_receipt_is_not_social_security(self):
        """「缴存登记回执」是"已办理登记"的证明，与"缴费明细"**不是同一实物**，刻意不登记。

        否则"提供了社保明细"会被当成"已提交登记回执"，反证被当成已获取。
        """
        from engine.material_names import strict_categories_all
        assert strict_categories_all("缴存登记回执") is None


class TestOrSemanticsInConstituentSources:
    """★ 2026-10-03：要件数据源里的「或」必须按**或**判（与 evidence_chain 同一契约）。

    事故：要件① 写的是「存在劳动用工关系（工资表**或**个税申报有人员）」，
    而数据源声明「劳动合同、工资表」被当成「且」⇒ 只上传工资表的企业，
    该要件永远停在「独立数据源本轮未取得」（实测疑点23 要件①）。
    """

    def test_and_groups_require_all(self):
        from engine.material_names import strict_category_groups
        g = strict_category_groups("住房公积金缴存明细、工资表、社保参保明细")
        assert g == [[["社保明细"]], [["工资表"]], [["社保明细"]]]

    def test_or_group_is_an_alternative(self):
        from engine.material_names import strict_category_groups
        g = strict_category_groups("工资表或个税申报表")
        assert g and len(g) == 1 and len(g[0]) == 2, g

    def test_unclassifiable_part_invalidates_whole(self):
        from engine.material_names import strict_category_groups
        assert strict_category_groups("缴存登记回执、劳动合同、住房公积金缴存明细") is None

    def test_match_material_honours_or(self):
        """只提供工资表 ⇒ 「工资表或个税申报表」判「已有」（旧实现按「且」判，会误判待核）。"""
        from engine.evidence_chain import _match_material
        m = _match_material("工资表或个税申报表", "", ["工资表", "社保明细", "记账凭证"])
        assert m["status"] == "已有", m

    def test_match_material_still_requires_all_for_and(self):
        """「A、B」＝两样都要：只提供 A ⇒ 不得判「已有」（防 OR 修复被滥用成开口子）。"""
        from engine.evidence_chain import _match_material
        m = _match_material("进项发票与采购台账", "", ["进项发票"])
        assert m["status"] != "已有", m


# ── 域8 公积金比对：产出与要件归属 ────────────────────────────────────────────
def _salary(name, month, gross, hf_deduct=0.0):
    return {"name": name, "salary": gross, "hf_deduct": hf_deduct,
            "period_start": month + "-01", "period_end": month + "-31"}


def _fund(name, month, amount):
    return {"person_name": name, "counterparty": month, "amount_col": str(amount)}


def _run(salaries, ss, fund):
    from engine.domain_analysis import _domain_salary_ss_hf_compare
    return _domain_salary_ss_hf_compare(salaries, ss, fund)


class TestWorkforceComparison:

    def test_unfunded_person_is_reported_with_ironclad_evidence(self):
        """有工资、无公积金 ⇒ 产出 RL-SPT-010，且证据含**具体人名与月份**。"""
        salaries = [_salary("甲", "2025-01", 8000, 300), _salary("乙", "2025-01", 9000, 0)]
        fund = [_fund("甲", "2025-01", 300)]
        out = _run(salaries, [], fund)
        hit = [f for f in out if f.get("type") == "有工资无公积金"]
        assert hit, "应产出「有工资无公积金」"
        f = hit[0]
        assert f["redline_id"] == "RL-SPT-010"
        assert "乙" in f["detail"] and "2025-01" in f["detail"]
        # 要件②（人数差异）必须被认领，且证据带对比数字
        idxs = [h["index"] for h in f["constituent_hits"]]
        assert 2 in idxs
        assert "工资表 2 人、公积金缴存 1 人" in dict(
            (h["index"], h["evidence"]) for h in f["constituent_hits"])[2]

    def test_low_base_detected_by_legal_ratio_reverse_proof(self):
        """个人缴存额 < 工资×5% ⇒ 单向证伪：缴存基数必然低于实际工资。"""
        salaries = [_salary("甲", "2025-01", 12000, 300), _salary("乙", "2025-01", 30000, 300)]
        fund = [_fund("甲", "2025-01", 300), _fund("乙", "2025-01", 300)]
        out = _run(salaries, [], fund)
        hit = [f for f in out if f.get("type") == "公积金缴存基数低于实际工资"]
        assert hit, "应产出「公积金缴存基数低于实际工资」"
        f = hit[0]
        assert f["redline_id"] == "RL-SPT-010"
        idxs = [h["index"] for h in f["constituent_hits"]]
        assert 3 in idxs and 4 in idxs   # 要件③ 基数/比例低于下限、要件④ 基数不实

    def test_adequate_contribution_is_not_flagged(self):
        """缴存额达到工资 5% 以上 ⇒ **不产出**（宁缺勿错；比例可能是 12%，不能反推）。"""
        salaries = [_salary("甲", "2025-01", 6000, 600)]
        fund = [_fund("甲", "2025-01", 600)]
        out = _run(salaries, [], fund)
        assert not [f for f in out if f.get("type") == "公积金缴存基数低于实际工资"]

    def test_fund_only_without_salary_does_not_claim_violation(self):
        """只有公积金明细、无工资表 ⇒ 只做单向核验，**绝不**推断"未全员缴存"。"""
        fund = [_fund("甲", "2025-01", 300)]
        out = _run([], [], fund)
        assert not [f for f in out if f.get("type") == "有工资无公积金"]
        single = [f for f in out if f.get("type", "").startswith("公积金缴存明细已单独核验")]
        assert single, "应产出单向核验结论"
        assert single[0].get("redline_id") in (None, "")

    def test_no_housing_fund_data_produces_nothing_new(self):
        assert _run([_salary("甲", "2025-01", 8000)], [], []) != []


class TestRedlineRequirementLogic:

    def test_hf_redline_declares_indicator_and_violation(self):
        from engine.constituent_checkpoint import redline_verdict_rule
        rule = redline_verdict_rule("RL-SPT-010")
        assert rule["indicator"] == [1]        # ① 存在用工关系 = 前提/指标
        assert rule["any_of"] == [2, 3, 4]     # ②③④ 任一成立才构成违规

    def test_indicator_only_does_not_establish_violation(self):
        """只有"存在劳动用工关系"成立 ⇒ 参与认定要件为空（不得判触红）。"""
        from engine.constituent_checkpoint import participating_indices
        cps = [{"index": 1, "参与认定": True, "checked_hit": True}]
        assert participating_indices(cps, "RL-SPT-010") == []
        # 一旦要件②成立 ⇒ 全部命中要件计入
        cps.append({"index": 2, "参与认定": True, "checked_hit": True})
        assert participating_indices(cps, "RL-SPT-010") == [1, 2]
