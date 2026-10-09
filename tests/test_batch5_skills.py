# -*- coding: utf-8 -*-
"""第 5 批验收测试：多行业与合规能力（2026-10-07）。

覆盖用户给的 6 条验收标准：
  AC1 新增行业只需配置，不需改代码
  AC2 同一份资料，不同行业下**报告模板、风险等级、补资料优先级可不同，底层事实一致**
  AC3 报告名称改为「税务风险扫描工作底稿」或「风险提示函」
  AC4 增加编制人/复核人/审批人签名栏
  AC5 增加保密等级、数据授权、系统标识、企业申辩机制
  AC6 脱敏规则按角色生效
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path


def _problems(n=3, level="中风险"):
    return {"confirmed_problems": [
        {"seq": i, "title": "事项%d" % i, "risk_level": level, "redline_id": "RL-T-%d" % i,
         "taxes": ["增值税"], "conclusion_grade": "已核定", "evidence_have": 1,
         "evidence_need": 3, "constituent_hits": [{"index": 1}],
         "missing_materials": ["购销存台账"],
         "tax_impact": {"available": True, "basis": 100000.0, "total": 6000.0,
                        "items": [{"tax": "增值税", "rate": 0.06, "amount": 6000.0}]},
         "narrative_paragraphs": [{"text": "事项%d 的具体描述。" % i, "tail": ""}]}
        for i in range(1, n + 1)],
        "summary": {"headline": "本期共 %d 项" % n}, "overall_conclusion": "总体结论。"}


class TestIndustryParams:
    """AC1：新增行业只需配置；配置本身可机检。"""

    def test_registry_is_valid(self):
        from engine.industry_params import validate_params
        assert validate_params() == [], validate_params()

    def test_six_required_industries_present(self):
        from engine.industry_params import industry_ids, industries
        labels = [str(x.get("label")) for x in industries()]
        for want in ("广告传媒", "制造业", "电子商务", "建筑安装", "餐饮", "科技服务"):
            assert want in labels, labels
        assert "advertising_media" in industry_ids()

    def test_benchmark_not_duplicated_but_referenced(self):
        """★ 行业数值**不得**在参数库里复制：必须靠 `benchmark_refs` 引用既有基准库。"""
        from engine.industry_params import industries, benchmark_values_of
        for x in industries():
            assert "benchmark_values" not in x, "参数库复制了基准数值（会形成第二套口径）"
            assert benchmark_values_of(x.get("benchmark_refs")), x.get("industry_id")

    def test_add_new_industry_needs_no_code(self):
        """★ 新增行业 = 只加一条数据：骨架齐备 + 校验器能判它是否合格。"""
        from engine.industry_params import PARAM_FIELDS, new_industry_template
        tpl = new_industry_template("demo_industry", "演示行业")
        for f in PARAM_FIELDS:
            assert f in tpl, "骨架缺字段 %s（那就等于还要改代码）" % f

    def test_unknown_industry_does_not_borrow_other_params(self):
        from engine.industry_params import params_of, material_priority, report_template
        p = params_of("一个没配置过的行业")
        assert p["matched"] is False
        assert material_priority("一个没配置过的行业") == []
        assert report_template("一个没配置过的行业") == {}
        assert "未匹配到已配置行业" in p["note"]

    def test_benchmark_meta_carries_source_period_scope(self):
        """行业基准库管理：来源/版本/期间/口径/适用范围必须登记。"""
        from engine.industry_params import benchmark_meta
        m = benchmark_meta("advertising_media")
        for k in ("source", "period", "scope", "caveat", "refs", "registry_version"):
            assert m.get(k), "基准元数据缺 %s" % k


class TestIndustrySwitch:
    """AC2：同一份资料，不同行业下模板/等级/补资料优先级可不同，**底层事实一致**。"""

    def test_template_differs_by_industry(self):
        from engine.report_template import apply_template, section_order
        rep = _problems()
        adv, m1 = apply_template(rep, "广告传媒")
        mfg, m2 = apply_template(rep, "制造业")
        assert m1["template_id"] != m2["template_id"], (m1, m2)
        assert section_order("制造业") != section_order("广告传媒")
        assert "投入产出与存货" in section_order("制造业")
        assert "投入产出与存货" not in section_order("广告传媒")

    def test_material_priority_differs_by_industry(self):
        from engine.report_template import priority_sort
        items = ["银行流水", "销项发票", "进销存台账", "合同文件"]
        a, _ = priority_sort(items, "制造业")
        b, _ = priority_sort(items, "广告传媒")
        assert a != b, "不同行业的补资料优先级必须能不同"
        assert set(a) == set(items) and set(b) == set(items), "只调顺序，不得增删条目"

    def test_level_can_differ_but_facts_identical(self):
        """★ 核心验收：等级可因行业不同，**事实/计算/法律三层指纹必须一致**。"""
        from engine.industry_params import apply_level_adjustments, evaluate_triggers
        from engine.snapshot_invariance import verify_invariance
        base = _problems(level="低风险")
        # 广告传媒：期间费用率高于行业上限 ⇒ 触发下限调整；制造业：不触发
        trig_adv = evaluate_triggers("广告传媒", {"期间费用率": 9.99})
        adv_levels = [apply_level_adjustments("广告传媒", "", "期间费用率", "低风险", trig_adv)[0]
                      for _ in base["confirmed_problems"]]
        mfg_levels = [apply_level_adjustments("制造业", "", "期间费用率", "低风险", set())[0]
                      for _ in base["confirmed_problems"]]
        assert adv_levels != mfg_levels, "同资料在不同行业下等级应可不同"
        # 按各自等级构造两份报告，比较三层指纹
        adv = json.loads(json.dumps(base))
        mfg = json.loads(json.dumps(base))
        for p, lv in zip(adv["confirmed_problems"], adv_levels):
            p["risk_level"] = lv
        for p, lv in zip(mfg["confirmed_problems"], mfg_levels):
            p["risk_level"] = lv
        r = verify_invariance(adv, mfg, kinds=("facts", "calc", "legal"))
        assert r["ok"] is True, r["diffs"]
        # 而等级层**允许**不同
        from engine.snapshot_invariance import diff_rows
        assert diff_rows(adv, mfg, "level"), "本用例应当体现等级差异"

    def test_no_trigger_means_no_level_change(self):
        """★ 条件未评估成立 ⇒ **不得**调整等级（防"配置写条件、代码无条件执行"）。"""
        from engine.industry_params import apply_level_adjustments, evaluate_triggers
        assert evaluate_triggers("广告传媒", {"期间费用率": 0.001}) == set()
        out, hits = apply_level_adjustments("广告传媒", "", "期间费用率", "低风险")
        assert out == "低风险" and hits == []
        out2, _ = apply_level_adjustments("广告传媒", "", "期间费用率", "低风险",
                                         triggered={"ADV-EXPENSE-RATIO"})
        assert out2 == "中风险"

    def test_template_change_does_not_touch_facts(self):
        from engine.report_template import apply_template
        from engine.snapshot_invariance import verify_invariance
        rep = _problems()
        out, _ = apply_template(rep, "餐饮")
        assert verify_invariance(rep, out)["ok"] is True, "换模板不得改动事实/计算/法律/等级"


class TestReportPositioning:
    """AC3/AC4/AC5：报告定位、签名栏、保密/授权/系统标识/申辩机制。"""

    def test_report_name_changed_and_non_enforceable(self):
        # ★ 2026-10-07（Skill 5「报告性质一致性」）：报告名称的**唯一权威**是
        #   `config/report_identity.json` 的 canonical（对外/对内均可配置）。
        #   本测试不再断言写死的名称字面量 —— 否则每次依法改名都要改测试
        #   （那正是"名称多头维护"的另一种形态）。改为：**模板必须与唯一权威一致**。
        from engine.report_compliance import document_meta
        from engine.report_identity import canonical_name
        cn = canonical_name()
        for kind, want in (("internal_working_paper", cn),
                           ("external_notice", "风险提示函")):
            d = document_meta(kind)
            assert d["name"] == want, d
            assert d["is_enforceable"] is False
            assert "不是税务处理决定" in d["non_enforcement_note"]
        assert cn == "内部辅助分析工作底稿", "唯一名称须为内部辅助分析工作底稿（用户指令）"

    def test_signature_roles_present_and_unsiged_is_flagged(self):
        from engine.report_compliance import signature_block
        b = signature_block({})
        roles = [r["role"] for r in b["rows"]]
        for want in ("编制人", "复核人", "审批人"):
            assert want in roles, roles
        assert b["signed"] is False and set(b["missing_roles"]) == {"编制人", "复核人", "审批人"}
        b2 = signature_block({"编制人": "张工", "复核人": "李工", "审批人": "王主任"})
        assert b2["signed"] is True and b2["missing_roles"] == []

    def test_security_authorization_system_feedback(self):
        from engine.report_compliance import (authorization_block, feedback_block,
                                             security_block, system_block)
        sec = security_block("internal_working_paper")
        assert sec["level"] and "不得外传" in sec["restriction"]
        au = authorization_block()
        assert au["statement"] and au["destruction_rule"]
        sysb = system_block(reviewed=None)
        assert sysb["name"] and sysb["version"] and sysb["generated_at"]
        assert sysb["reviewed"] is False and "尚未人工复核" in sysb["review_status_text"]
        fb = feedback_block()
        assert fb["window_days"] and fb["channels"] and fb["process"]

    def test_compliance_config_valid(self):
        from engine.report_compliance import validate_compliance
        assert validate_compliance() == [], validate_compliance()

    def test_version_control_records_every_generation(self):
        from engine.report_compliance import change_log, internal_edition, next_version
        import time
        cid = "T-VER-%d" % int(time.time() * 1000 % 1e7)
        v1 = next_version(cid)
        internal_edition(_problems(), company_id=cid, change_note="首次")
        internal_edition(_problems(), company_id=cid, change_note="复核后修订")
        rows = change_log(cid)
        assert len(rows) == 2, "每次生成都要留一条版本记录（含重复生成）"
        vers = [r["version"] for r in rows]
        assert len(set(vers)) == 2, vers
        assert v1 == "V1"


class TestRedaction:
    """AC6：脱敏规则按角色生效。"""

    _TEXT = ("张某先生向李小明女士支付1,234,567.89元，账号6222020200112233，"
             "手机13812345678，身份证110101199001011234，邮箱zhangwei@example.com。")

    def test_internal_role_keeps_everything(self):
        from engine.redaction import redact_text, role_policy
        out = redact_text(self._TEXT, role_policy("internal"))
        assert out == self._TEXT, out

    def test_external_role_masks_all_items(self):
        from engine.redaction import redact_text, role_policy
        out = redact_text(self._TEXT, role_policy("external"))
        assert "张某" in out and "李某" in out, out
        for leaked in ("6222020200112233", "13812345678", "110101199001011234",
                       "1,234,567.89", "zhangwei@example.com"):
            assert leaked not in out, "对外版本泄漏了 %s：%s" % (leaked, out)
        assert "约 123 万元" in out

    def test_auditor_role_keeps_amount_only(self):
        from engine.redaction import redact_text, role_policy
        out = redact_text(self._TEXT, role_policy("auditor"))
        assert "1,234,567.89" in out, "检查角色应保留金额"
        assert "6222020200112233" not in out

    def test_unknown_role_is_strictest(self):
        from engine.redaction import role_policy
        pol = role_policy("没登记过的角色")
        assert all(pol[k] for k in ("name", "account", "id_card", "amount", "contact"))

    def test_name_redaction_is_surname_based(self):
        """★ 回归：按"称谓前固定字数"取会吃掉姓氏/吃掉正文（本轮实测两例）。"""
        from engine.redaction import redact_names
        assert redact_names("张某先生向李小明女士支付。")[0] == "张某先生向李某女士支付。"
        assert redact_names("法定代表人王建国签字。")[0] == "法定代表人王某签字。"
        assert redact_names("付款人为欧阳明月，客户张三。")[0] == "付款人为欧阳某，客户张某。"

    def test_redaction_is_traceable(self):
        from engine.redaction import copy_for_role
        clone, counter, note = copy_for_role(_problems(), "external")
        assert "脱敏" in note
        # ★ 数值型金额字段也必须被脱敏（实测初版只扫文本 ⇒ 最大的那个数没动）
        assert counter.get("amount_field", 0) >= 1, counter
        assert "金额（数值字段）" in note, note

    def test_amount_numeric_fields_are_masked(self):
        """数值型金额 ⇒ 按万元量级化；**比例与计数不得被改**。"""
        from engine.redaction import copy_for_role
        rep = {"confirmed_problems": [{"tax_impact": {
            "basis": 1234567.89, "total": 12345.67,
            "items": [{"tax": "增值税", "rate": 0.06, "amount": 12345.67}]},
            "evidence_have": 1}]}
        clone, counter, _ = copy_for_role(rep, "external")
        ti = clone["confirmed_problems"][0]["tax_impact"]
        assert ti["basis"] != 1234567.89 and ti["basis"] % 10000 == 0, ti
        assert ti["items"][0]["amount"] % 10000 == 0, ti
        assert ti["items"][0]["rate"] == 0.06, "税率不得被量级化"
        assert clone["confirmed_problems"][0]["evidence_have"] == 1, "计数不得被量级化"

    def test_external_edition_does_not_touch_internal(self):
        """对外版与内部底稿是**两个对象**：脱敏绝不能改到内部底稿。"""
        from engine.report_compliance import external_edition, internal_edition
        rep = {"confirmed_problems": [{"title": "t", "risk_level": "中风险",
                                       "narrative_paragraphs": [{"text": "张伟先生支付1000.00元。"}]}]}
        internal = internal_edition(rep, company_id="T-X1")
        external = external_edition(rep, company_id="T-X1")
        assert "张伟先生" in json.dumps(internal, ensure_ascii=False)
        assert "张伟先生" not in json.dumps(external, ensure_ascii=False)
        assert "张伟先生" in json.dumps(rep, ensure_ascii=False), "原对象不得被改动"


class TestIndustryProfilesJson:
    """行业关键词从 JSON 可编辑（此前文件缺失 ⇒ 一直在走代码兜底）。"""

    def test_file_exists_and_has_both_sections(self):
        p = Path(__file__).resolve().parent.parent / "static" / "industry_profiles.json"
        assert p.exists(), "static/industry_profiles.json 缺失（『JSON 可编辑』路径会一直走兜底）"
        d = json.loads(p.read_text(encoding="utf-8"))
        for k in ("_processing_keywords", "_biz_keywords"):
            assert d.get(k), k
        assert d["_processing_keywords"].get("pure_service")
        assert d["_biz_keywords"].get("daily_goods")
        assert "industries" not in d, "本文件不得再放行业基准数值（唯一权威是 industry_data.json）"

    def test_loaders_read_from_json_now(self):
        from engine.domain_analysis import _load_biz_keywords, _load_processing_keywords
        pp, part, pure = _load_processing_keywords()
        assert len(pp) == 15 and len(part) == 15 and len(pure) == 23
        daily, mainbiz, imp = _load_biz_keywords()
        assert len(daily) == 12 and len(mainbiz) == 14 and len(imp) == 10
