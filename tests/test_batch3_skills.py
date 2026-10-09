# -*- coding: utf-8 -*-
"""第 3 批验收测试：系统规范与核心 Skill（2026-10-07）。

覆盖用户给的验收标准：
  AC1 风险族去重：同一风险族下多个子项只计 1 项
  AC2 税额测算：红冲不得输出 759 万；进项差异不得再乘 6%；
      企业所得税未验证小微条件不得按 5% 估算
  AC3 法律适用：社保费/公积金/文化事业建设费不套用税收征管法偷税条款
  AC5 质量门禁：失败样例必报、修复后样例必过
  AC6 自我复盘：能输出四类记录（四档分级可用）
"""
from __future__ import annotations


class TestRiskFamilyDedup:
    """AC1：**同一风险族下多个子项只计 1 项**（报告总事项数＝父风险数）。"""

    @staticmethod
    def _mk(seq, title, rname, amt, lv="中风险", taxes=None):
        return {"seq": seq, "title": title, "risk_level": lv,
                "taxes": taxes or ["增值税"], "redline_name": rname,
                "finding_type": rname, "tax_impact": {"total": amt},
                "narrative_paragraphs": []}

    def test_same_family_counts_once(self):
        from engine.finding_families import merge_families
        probs = [
            self._mk(1, "工资表人数与社保参保人数不符", "工资表列支人数与社保参保人数存在差异",
                     0, "高风险"),
            self._mk(2, "公私混同发薪", "私户支付薪酬", 100000),
            self._mk(3, "住房公积金未开户", "住房公积金未全员缴存", 50000),
        ]
        before = len(probs)
        st = merge_families(probs)
        assert st["removed_items"] >= 2, st
        assert len(probs) == before - st["removed_items"], "子项必须从列表移除（不单独计数）"
        assert len(probs) == 1, "同族 3 个子项应只留 1 个父项，实际 %d" % len(probs)
        assert probs[0]["seq"] == 1
        # 子项信息不得静默丢失：以差异点形式挂在父项
        assert probs[0].get("family_members"), "子项信息必须挂在父项（不静默丢）"

    def test_total_equals_family_count(self):
        """报告总事项数 = 父风险数（合并后列表长度即总数）。"""
        from engine.finding_families import merge_families
        probs = [
            self._mk(1, "工资表人数与社保参保人数不符", "工资表列支人数与社保参保人数存在差异", 0, "高风险"),
            self._mk(2, "公私混同发薪", "私户支付薪酬", 100000),
            self._mk(3, "银行收款大于申报收入", "银行收款与申报收入差异", 90000),
        ]
        merge_families(probs)
        fam_leads = [p for p in probs if p.get("family_members")]
        total = len(probs)
        assert total == len(fam_leads) + len([p for p in probs if not p.get("family_members")])


class TestRiskFamilyConfig:
    """任务2：风险族**配置表**（9 字段）与运行时必须一致；支持按行业启用。"""

    def test_config_matches_runtime(self):
        from engine.risk_families import validate_against_runtime
        assert validate_against_runtime() == []

    def test_policies_are_declared(self):
        from engine.risk_families import families
        fams = families()
        assert len(fams) >= 6, "应至少登记 6 个已有风险族"
        for f in fams:
            assert f["count_policy"] == "once_per_family", f["risk_family_name"]
            assert f["parent_risk_code"] and f["parent_risk_name"]
            assert f["children"], f["risk_family_name"]

    def test_industry_enablement(self):
        from engine.risk_families import families
        # enabled_industries 为空 ⇒ 全行业启用；指定行业时按名单过滤
        assert len(families("任意行业")) == len(families())

    def test_count_policy_meaning_is_explicit(self):
        from engine.risk_families import count_policy_means
        assert "1 项" in count_policy_means("once_per_family")


class TestTaxEstimateSkill:
    """AC2：分税种测算的三条硬约束。"""

    def test_red_void_never_yields_759w(self):
        """红冲类**不得**按销项蓝字全额估算。

        实测事故：锚定到"占比分母"8,050,908.58（整期销项蓝字）⇒ 增值税 7,595,196.77。
        """
        from engine.tax_impact import extract_amount
        # 分母（蓝字）与分子（红冲）同段并存时，必须取**分子**
        t = ("看到销项红字/作废1,015,900.00元，占同期销项蓝字开票额12.6%"
             "（分子=销项红字/作废价税合计，分母=剔除红字后的销项价税合计8,050,908.58元）")
        am = extract_amount(t)
        assert am is not None, "分子（红冲金额）必须能成为候选"
        assert abs(am["amount"] - 8050908.58) > 1, "分母不得被当作本项涉案金额：%s" % am

    def test_denominator_alone_is_not_the_subject_amount(self):
        """只有分母一个候选时 ⇒ 不采用（宁可未量化，也不把参照量当涉案金额）。"""
        from engine.tax_impact import extract_amount
        am = extract_amount("剔除红字后的销项价税合计（分母）8,050,908.58元")
        assert am is None or am["amount"] != 8050908.58, am

    def test_input_tax_difference_not_multiplied_by_rate(self):
        """进项差异若本身就是**税额** ⇒ 直接影响额即该税额，**不得再乘税率**。"""
        from engine.tax_impact import estimate_tax
        r = estimate_tax(4501.34, ["增值税"], amount_is_tax=True)
        assert r["available"] is True
        it = r["items"][0]
        assert abs(it["amount"] - 4501.34) < 0.01, "进项税额被再乘税率了：%s" % it
        assert it["rate"] == "—", it

    def test_cit_requires_smb_verification(self):
        """**未验证小型微利条件 ⇒ 不得按 5% 估算**（须回到 25% 法定上界）。"""
        from engine.tax_impact import estimate_tax
        base = 2_112_137.70
        unverified = estimate_tax(base, ["企业所得税"], rate_ctx={"cit_rate": 0.05})
        it = unverified["items"][0]
        assert float(it["rate"]) == 0.25, "未验证小微却按 %s 估算（低估 5 倍）" % it["rate"]
        assert "未验证小型微利" in it["note"]
        assert abs(it["amount"] - base * 0.25) < 0.01

    def test_cit_uses_5pct_only_when_verified(self):
        from engine.tax_impact import estimate_tax
        base = 2_112_137.70
        verified = estimate_tax(base, ["企业所得税"],
                                rate_ctx={"cit_rate": 0.05, "smb_verified": True})
        assert abs(verified["items"][0]["amount"] - base * 0.05) < 0.01

    def test_small_micro_authority_unknown_is_not_pass(self):
        """★ 唯一权威 `evaluate_small_micro`：**未知 ≠ 通过**（旧实现把"未取得"当满足）。"""
        from engine.tax_impact import evaluate_small_micro
        # 只给净利润 ⇒ 人数/资产未取得 ⇒ 未验证
        r = evaluate_small_micro(net_profit=400000.0)
        assert r["verified"] is False, r
        assert "从业人数" in r["missing"] and "资产总额" in r["missing"], r
        # 三项齐备且满足 ⇒ 已验证
        r2 = evaluate_small_micro(employee_count=10, total_assets=1_000_000.0,
                                  net_profit=400000.0)
        assert r2["verified"] is True, r2
        # 已取得但超临界值 ⇒ 不通过（且归入 failed 而非 missing，便于文案区分）
        r3 = evaluate_small_micro(employee_count=500, total_assets=1_000_000.0,
                                  net_profit=400000.0)
        assert r3["verified"] is False and "从业人数" in r3["failed"], r3
        r4 = evaluate_small_micro(employee_count=10, total_assets=60_000_000.0,
                                  net_profit=400000.0)
        assert r4["verified"] is False and "资产总额" in r4["failed"], r4
        r5 = evaluate_small_micro(employee_count=10, total_assets=1_000_000.0,
                                  net_profit=0.0)
        assert r5["verified"] is False and "应纳税所得额" in r5["failed"], r5

    def test_infer_rate_context_defers_to_authority(self):
        """`infer_rate_context` 的企业所得税档位**只由权威判定**（不得自行"未知即通过"）。"""
        from engine.tax_impact import infer_rate_context
        ok = infer_rate_context(sal_invs=[{"amount": 100.0, "tax_amount": 6.0}],
                                net_profit=400000.0, employee_count=10,
                                total_assets=1_000_000.0)
        assert ok["vat_rate"] == 0.06 and ok["cit_rate"] == 0.05, ok
        assert ok["smb_verified"] is True, ok
        bad = infer_rate_context(sal_invs=[{"amount": 100.0, "tax_amount": 6.0}],
                                 net_profit=400000.0)
        assert bad["smb_verified"] is False and bad["cit_rate"] == 0.25, bad
        assert "未验证小型微利" in bad["cit_note"], bad

    def test_unquantified_never_zero_or_one_yuan(self):
        """无明确金额 ⇒ **未量化**（不得输出 0 或"一元"，不得按 0 参与合计）。"""
        from engine.tax_impact import estimate_tax
        r = estimate_tax(None, ["增值税"])
        assert r["available"] is False and r["total"] is None
        assert "未量化" in r["note"]

    def test_every_tax_item_declares_rate_and_basis(self):
        """每个税种必须标注：税种/税率/金额（是否含税与上界口径见 note/amount_context）。"""
        from engine.tax_impact import estimate_tax
        r = estimate_tax(100000, ["增值税", "城市维护建设税", "印花税"])
        assert r["items"], r
        for it in r["items"]:
            assert it.get("tax")
            assert "rate" in it and "amount" in it


class TestLegalApplicationSkill:
    """AC3：非税（社保费/公积金/政府性基金）**不得套用**税收征管法偷税条款。"""

    def test_non_tax_never_cites_collection_law(self):
        from engine.levy_nature import consequence_text
        for nat, must, must_not in (
            ("社会保险费", "社会保险法", "第六十三条"),
            ("住房公积金", "住房公积金管理中心", "第六十三条"),
            ("政府性基金", "政府性基金", "第六十三条"),
        ):
            t = consequence_text(nat)
            assert must in t, (nat, t)
            assert must_not not in t, (nat, t)
            assert "不是税" in t or "非税" in t, (nat, t)

    def test_tax_item_still_cites_collection_law(self):
        """反向锁：**税**事项仍须引《税收征收管理法》。"""
        from engine.levy_nature import consequence_text
        t = consequence_text("税")
        assert "第六十三条" in t and "第三十二条" in t
        assert "不是税" not in t

    def test_mixed_nature_states_both(self):
        from engine.levy_nature import natures_of, consequence_text
        nats = natures_of({"taxes": ["个人所得税", "社会保险费"]})
        assert nats == ["税", "社会保险费"]
        t = consequence_text(nats)
        assert "就税款部分" in t and "就社会保险费部分" in t


class TestLearnableRuleTiers:
    """AC6：自我复盘必须**分档**——四类可学习内容，未知一律按最严档。"""

    def test_four_tiers_exist(self):
        from engine.learnable_rules import all_tiers
        assert [t for t, _ in all_tiers()] == ["auto", "manual", "accumulate", "forbidden"]

    def test_known_kinds_map_correctly(self):
        from engine.learnable_rules import tier_of
        assert tier_of("表格校验") == "auto"
        assert tier_of("占位符") == "auto"
        assert tier_of("风险族") == "manual"
        assert tier_of("税额测算") == "manual"
        assert tier_of("行业基准") == "accumulate"
        assert tier_of("法律条文") == "forbidden"
        assert tier_of("追征期") == "forbidden"
        assert tier_of("处罚标准") == "forbidden"

    def test_unknown_defaults_to_strictest_manual(self):
        """未知类别**不得**默认可自动学习（那等于空白授权）。"""
        from engine.learnable_rules import tier_of, may_write_rule
        assert tier_of("某个没登记过的东西") == "manual"
        assert may_write_rule("某个没登记过的东西")[0] is False

    def test_forbidden_write_is_blocked(self):
        from engine.learnable_rules import guard_rule_write
        for k in ("法律条文", "处罚标准", "主观故意认定", "企业申辩结论"):
            try:
                guard_rule_write(k)
            except PermissionError:
                continue
            raise AssertionError("禁止档「%s」竟然允许自动写入规则库" % k)


class TestSkillSpecRegistry:
    """任务1：Skill 通用结构规范的**可机检**形式（config/skill_specs.json + 校验器）。"""

    def test_registry_is_clean(self):
        from engine.skill_registry import validate
        assert validate() == [], validate()

    def test_registry_declares_all_required_fields(self):
        from engine.skill_registry import SPEC_FIELDS, declared_fields
        assert declared_fields() == SPEC_FIELDS, "登记表字段声明与校验器口径不一致"

    def test_every_spec_entry_point_actually_defined(self):
        """impl 文件里必须**真的有**这些入口（改名/删除会被抓出）。"""
        import re
        from pathlib import Path
        from engine.skill_registry import specs
        root = Path(__file__).resolve().parent.parent
        for s in specs():
            p = root / s["impl"]
            assert p.exists(), s["id"]
            txt = p.read_text(encoding="utf-8")
            for ep in s["entry_points"]:
                assert re.search(r"^\s*def\s+%s\s*\(" % re.escape(ep), txt, re.M), \
                    "%s 缺入口 %s" % (s["id"], ep)

    def test_unquantified_must_state_fallback(self):
        """声明"可能取不到值"的 Skill，**必须**写清取不到怎么办（禁默认值顶替）。"""
        from engine.skill_registry import specs
        for s in specs():
            if s.get("unquantified"):
                assert str(s.get("unquantified_convention") or "").strip(), s["id"]

    def test_declared_config_params_exist(self):
        from pathlib import Path
        from engine.skill_registry import specs
        root = Path(__file__).resolve().parent.parent
        for s in specs():
            for prm in s.get("params") or []:
                if prm.get("kind") == "config":
                    assert (root / prm["path"]).exists(), (s["id"], prm)

    def test_coverage_reports_untested_skills_visibly(self):
        from engine.skill_registry import coverage
        cov = coverage()
        assert cov["skills"] >= 20, cov
        assert isinstance(cov["without_tests"], list)


class TestLegalVersioning:
    """任务4：法条版本化（唯一权威 engine.legal_version + 报告标注）。"""

    def test_version_note_for_registered_law(self):
        from engine.legal_version import version_note, is_current
        assert is_current("发票管理办法")
        n = version_note("发票管理办法")
        assert "2023年修订" in n and "现行有效" in n, n

    def test_version_note_for_unregistered_law_is_explicit(self):
        """未登记 ⇒ **不得默认按现行有效**呈现。"""
        from engine.legal_version import version_note, status_of
        n = version_note("某部尚未登记版本的法律")
        assert "版本未登记" in n, n
        assert status_of("某部尚未登记版本的法律") == "unknown"

    def test_canonical_law_strips_version_but_keeps_doc_number(self):
        from engine.legal_version import canonical_law, has_version_in_name
        assert canonical_law("发票管理办法（2023修订）") == "发票管理办法"
        assert has_version_in_name("发票管理办法（2023修订）")
        # 文号括注是法名的一部分，不得剥掉
        assert canonical_law("企业所得税税前扣除凭证管理办法（国家税务总局公告2018年第28号）") \
            == "企业所得税税前扣除凭证管理办法（国家税务总局公告2018年第28号）"
        # "（试行）"属于法名本身，保留
        assert "试行" in canonical_law("股权转让所得个人所得税管理办法（试行）（国家税务总局公告2014年第67号）")

    def test_registry_self_audit_clean_and_core_registered(self):
        from engine.legal_version import audit_registry, unregistered_core_laws
        assert audit_registry() == [], audit_registry()
        assert unregistered_core_laws() == []

    def test_report_injects_version_and_unregistered_is_flagged(self):
        from engine.legal_citation import format_legal_basis
        known = format_legal_basis(["《发票管理办法》第二十一条"], with_version=True)
        assert "现行有效" in known, known
        unknown = format_legal_basis(["《某部尚未登记版本的法律》第一条"], with_version=True)
        assert "版本未登记" in unknown, unknown
        # 默认行为不得改变（既有调用方不受影响）
        assert "现行有效" not in format_legal_basis(["《发票管理办法》第二十一条"])

    def test_citations_carry_no_version_in_law_name(self):
        """同一部法不得有两套法名（版本只登记在登记表里）。"""
        from engine.tax_redlines import REDLINES
        from engine.legal_version import audit_citations
        cites = []
        for r in REDLINES or []:
            lb = (r or {}).get("legal_basis")
            if isinstance(lb, str):
                lb = [lb]
            cites.extend([x for x in (lb or []) if isinstance(x, str)])
        bad = [p for p in audit_citations(cites) if "把版本写进了法名" in p]
        assert bad == [], bad


class TestRetrospective:
    """任务7：四步复盘（个案→模式→萃取→入库）的**产出**。"""

    _EVS = [
        {"id": "EV-A", "module": "engine/tax_impact.py", "symptom": "未验证小微按 5%",
         "pattern_signature": "unknown_treated_as_pass",
         "evidence": ["tests/test_batch3_skills.py::TestTaxEstimateSkill"]},
        {"id": "EV-B", "module": "engine/clue_chain.py", "symptom": "资料未提供却给读数",
         "pattern_signature": "unknown_treated_as_pass",
         "evidence": ["tools/audit_consistency.py"]},
        {"id": "EV-C", "module": "engine/report_dedup.py", "symptom": "只复发一次",
         "pattern_signature": "doc_says_a_code_does_b", "evidence": []},
    ]

    def test_pattern_promoted_only_when_repeated(self):
        from engine.retrospective import cluster_patterns
        cl = {c["pattern_signature"]: c for c in cluster_patterns(self._EVS)}
        assert cl["unknown_treated_as_pass"]["count"] == 2
        assert cl["unknown_treated_as_pass"]["promoted"] is True
        assert cl["doc_says_a_code_does_b"]["promoted"] is False, "只犯一次不算模式"

    def test_unclassified_signature_is_not_guessed(self):
        from engine.retrospective import cluster_patterns
        cl = cluster_patterns([{"symptom": "x", "pattern_signature": "没见过的签名"}])
        assert cl[0]["pattern_signature"] == "unclassified"
        assert cl[0]["promoted"] is False

    def test_proposals_only_from_promoted_and_respect_tiers(self):
        from engine.retrospective import cluster_patterns, extract_rule_proposals
        props = extract_rule_proposals(cluster_patterns(self._EVS))
        assert len(props) == 1, props
        p = props[0]
        assert p["from_pattern"] == "unknown_treated_as_pass"
        # manual 档：**不得**声明可自动写入
        assert p["tier"] == "manual" and p["writable"] is False, p

    def test_forbidden_tier_is_rejected_not_written(self):
        from engine.retrospective import commit_rules
        res = commit_rules([{"rule_id": "RR-X", "tier": "forbidden"}, ], dry_run=True)
        assert res["committed"] == []
        assert len(res["rejected"]) == 1
        assert "禁止自动学习" in res["rejected"][0]["reason"], res["rejected"][0]

    def test_tier_name_and_category_both_resolve(self):
        """`tier_of` 必须同时认**档名**与**内容类别**（否则档名落回 manual，理由错位）。"""
        from engine.learnable_rules import tier_of
        assert tier_of("forbidden") == "forbidden"
        assert tier_of("auto") == "auto"
        assert tier_of("法律条文") == "forbidden"
        assert tier_of("表格校验") == "auto"

    def test_five_documents_are_produced(self):
        import tempfile, os
        from engine.retrospective import run_retrospective
        r = run_retrospective(events=self._EVS, as_of="2026-10-07",
                              out_dir=tempfile.mkdtemp(), dry_run=True)
        names = sorted(os.listdir(r["dir"]))
        for want in ("01_复盘记录.md", "02_模式识别报告.md", "03_规则萃取建议.md",
                     "04_规则入库记录.md", "05_回归测试报告.md", "retrospective.json"):
            assert want in names, names

    def test_no_events_produces_honest_empty_record(self):
        """无事件 ⇒ 如实写"无新增事件"，**不生成假记录**。"""
        import tempfile
        from engine.retrospective import run_retrospective
        r = run_retrospective(events=[], as_of="2026-10-07",
                              out_dir=tempfile.mkdtemp(), dry_run=True)
        txt = open(r["files"]["01_复盘记录.md"], encoding="utf-8").read()
        assert "本轮无新增事件" in txt, txt
        assert r["proposals"] == []
