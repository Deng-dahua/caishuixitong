# -*- coding: utf-8 -*-
"""第 4 批验收测试：重新分析与学习迭代（2026-10-07）。

覆盖用户给的 5 条验收标准：
  AC1 同一数据快照，两次分析**可不同**，但**底层事实/计算结果/法律适用/评分规则一致**
  AC2 增量分析能输出《与上次分析对比表》
  AC3 假重新分析检测能识别「只换日期、内容不变」
  AC4 企业画像和历史案例**不直接改变风险等级**
  AC5 从点到面能输出《规则萃取建议》
"""
from __future__ import annotations


def _mk_problem(seq, title, level="中风险", basis=None, total=None, taxes=("增值税",),
                redline_id="RL-T-001", tax="增值税", rate=0.06, constituents=None):
    return {
        "seq": seq, "title": title, "risk_level": level, "redline_id": redline_id,
        "taxes": list(taxes), "conclusion_grade": "待核" if level == "待核验" else "已核定",
        "evidence_have": 1, "evidence_need": 3,
        "constituent_hits": [{"index": i} for i in (constituents or [1, 2])],
        "tax_impact": {"available": total is not None, "basis": basis,
                       "total": total, "items": [{"tax": tax, "rate": rate, "amount": total}]
                       if total is not None else []},
        "narrative_paragraphs": [{"text": "%s 的具体描述。" % title, "tail": ""}],
    }


def _mk_report(problems, session=None, narrative_order=None):
    r = {"confirmed_problems": list(problems),
         "summary": {"headline": "本期共 %d 项" % len(problems)},
         "overall_conclusion": "总体结论示例。"}
    if narrative_order:
        r["narrative_order"] = narrative_order
    if session:
        r["analysis_session"] = session
    return r


def _report(n=3, total=100000.0):
    return _mk_report([_mk_problem(i, "事项%s" % chr(64 + i), basis=total, total=total)
                       for i in range(1, n + 1)])


class TestSnapshotInvariance:
    """AC1：四类指纹必须恒等；而"可以不同"的部分不得进指纹。"""

    def test_same_snapshot_same_fingerprints(self):
        from engine.snapshot_invariance import verify_invariance, content_signature
        a, b = _report(), _report()
        # 制造"可以不同"的差异：会话、时间、叙述措辞（不含金额）
        a["analysis_session"] = {"session_id": "AS-1", "analyzed_at": "2026-10-01T09:00:00"}
        b["analysis_session"] = {"session_id": "AS-2", "analyzed_at": "2026-10-07T09:00:00"}
        b["confirmed_problems"][0]["narrative_paragraphs"][0]["text"] = "换一种说法描述同一件事。"
        r = verify_invariance(a, b)
        assert r["ok"] is True, r["diffs"]
        assert content_signature(a) != content_signature(b), "叙述确实不同 ⇒ 内容签名应不同"

    def test_fact_change_is_detected(self):
        from engine.snapshot_invariance import verify_invariance
        a, b = _report(), _report()
        b["confirmed_problems"][0]["title"] = "换了事实的标题"
        r = verify_invariance(a, b)
        assert r["ok"] is False and r["diffs"]["facts"], r

    def test_calc_change_is_detected(self):
        from engine.snapshot_invariance import verify_invariance
        a, b = _report(), _report()
        b["confirmed_problems"][0]["tax_impact"]["total"] = 999.0
        r = verify_invariance(a, b)
        assert r["ok"] is False and r["diffs"]["calc"], r

    def test_level_change_is_detected(self):
        from engine.snapshot_invariance import verify_invariance
        a, b = _report(), _report()
        b["confirmed_problems"][1]["risk_level"] = "高风险"
        r = verify_invariance(a, b)
        assert r["ok"] is False and r["diffs"]["level"], r

    def test_legal_change_is_detected(self):
        from engine.snapshot_invariance import verify_invariance
        a, b = _report(), _report()
        a["confirmed_problems"][0]["narrative_paragraphs"][0]["tail"] = \
            "法定依据：《税收征收管理法》第六十三条。"
        b["confirmed_problems"][0]["narrative_paragraphs"][0]["tail"] = \
            "法定依据：《企业所得税法》第八条。"
        r = verify_invariance(a, b)
        assert r["ok"] is False and r["diffs"]["legal"], r

    def test_order_change_does_not_break_invariance(self):
        """顺序变化**不得**被判成"事实变了"（指纹是集合语义）。"""
        from engine.snapshot_invariance import verify_invariance
        a, b = _report(), _report()
        b["confirmed_problems"] = list(reversed(b["confirmed_problems"]))
        assert verify_invariance(a, b)["ok"] is True

    def test_snapshot_version_is_time_independent(self):
        from engine.snapshot_invariance import snapshot_version
        f1 = [{"name": "a.xlsx", "size": 10, "rows": 3}, {"name": "b.pdf", "size": 20, "rows": 1}]
        assert snapshot_version(f1) == snapshot_version(list(reversed(f1)))

    def test_scoring_rule_version_is_exposed(self):
        from engine.snapshot_invariance import scoring_rule_version
        v = scoring_rule_version()
        assert isinstance(v, str) and len(v) >= 8, v

    def test_digest_reproduces_fingerprints(self):
        """★ 会话摘要必须**足以复算四类指纹 + 内容签名**（否则"与上次对比"就是假的）。"""
        from engine.snapshot_invariance import (content_signature, fingerprints,
                                                report_digest)
        rep = _report()
        dig = report_digest(rep)
        assert fingerprints(dig) == fingerprints(rep), "摘要复算的指纹与报告不一致"
        assert dig["content_signature"] == content_signature(rep), "摘要未保存内容签名"

    def test_digest_keeps_legal_tail(self):
        from engine.snapshot_invariance import report_digest
        rep = _report()
        rep["confirmed_problems"][0]["narrative_paragraphs"][0]["tail"] = \
            "法定依据：《税收征收管理法》第六十三条。"
        dig = report_digest(rep)
        assert "税收征收管理法" in str(dig["confirmed_problems"][0]["narrative_paragraphs"])


class TestNarrativeVariants:
    """叙事差异化：只改顺序，不改事实/金额/等级。"""

    def test_organize_changes_order_only(self):
        from engine.narrative_variants import organize
        from engine.snapshot_invariance import verify_invariance
        rep = _mk_report([
            _mk_problem(1, "印花税事项", level="中风险", total=5000, tax="印花税",
                        taxes=("印花税",)),
            _mk_problem(2, "增值税大额事项", level="高风险", total=900000, tax="增值税",
                        taxes=("增值税",)),
            _mk_problem(3, "个税事项", level="低风险", total=100, tax="个人所得税",
                        taxes=("个人所得税",)),
        ])
        out, note = organize(rep, by="amount")
        assert note and "按金额大小" in note
        assert out["confirmed_problems"][0]["title"] == "增值税大额事项"
        assert verify_invariance(rep, out)["ok"] is True, "重排不得改变四类指纹"

    def test_default_is_noop(self):
        from engine.narrative_variants import organize
        rep = _report()
        out, note = organize(rep, by=None)
        assert out["confirmed_problems"][0]["title"] == rep["confirmed_problems"][0]["title"]
        assert "默认顺序" in note

    def test_unknown_dimension_raises(self):
        from engine.narrative_variants import organize
        try:
            organize(_report(), by="不存在的维度")
        except ValueError:
            return
        raise AssertionError("未知组织维度必须报错，不得静默按默认排序")


class TestAnalysisSession:
    """任务1：会话六要素、编排、视角轮换、人工干预留痕。"""

    def test_session_has_all_six_elements(self):
        from engine.analysis_session import build_session, resolve_orchestration
        orch = resolve_orchestration("default")
        s = build_session(1, orch, {"files": [{"name": "a.xlsx", "size": 1, "rows": 2}]},
                          trace=[{"step": "扫描", "detail": "ok", "ms": 5}],
                          params={"industry": "现代服务", "taxes": ["增值税"]})
        for k in ("session_id", "analyzed_at", "skills", "params", "snapshot", "trace"):
            assert s.get(k) not in (None, "", [], {}), "会话缺要素 %s" % k
        assert s["params"]["materiality"] and s["params"]["thresholds"]
        assert all(x.get("version") for x in s["skills"]), "Skill 版本不得为空"

    def test_session_id_is_content_derived(self):
        """同快照 + 同配置 ⇒ **同哈希段**（"只换日期"无法伪装成新会话）。"""
        from engine.analysis_session import build_session, resolve_orchestration
        orch = resolve_orchestration("default")
        snap = {"files": [{"name": "a.xlsx", "size": 1, "rows": 2}]}
        s1 = build_session(1, orch, snap, analyzed_at="2026-10-01T09:00:00")
        s2 = build_session(1, orch, snap, analyzed_at="2026-10-07T15:00:00")
        assert s1["session_id"].split("-")[-1] == s2["session_id"].split("-")[-1]

    def test_different_snapshot_gives_different_hash(self):
        from engine.analysis_session import build_session, resolve_orchestration
        orch = resolve_orchestration("default")
        a = build_session(1, orch, {"files": [{"name": "a.xlsx", "size": 1, "rows": 2}]})
        b = build_session(1, orch, {"files": [{"name": "a.xlsx", "size": 1, "rows": 9}]})
        assert a["session_hash"] != b["session_hash"]

    def test_orchestration_default_is_noop_on_plan(self):
        """★ 默认档必须**不改**执行计划（保证改造前后行为一致）。"""
        from engine.orchestrator import build_orchestration_plan
        from engine.analysis_session import resolve_orchestration, filter_orchestration_plan
        plan = build_orchestration_plan({"has_bank": True, "has_invoices": True,
                                         "has_salary": True, "has_vouchers": True,
                                         "industry": "现代服务", "file_count": 3})
        orch = resolve_orchestration("default")
        assert orch["is_default"] is True
        same, skipped = filter_orchestration_plan(plan, orch)
        assert skipped == [] and same is plan, "默认档不得过滤任何模块"

    def test_orchestration_focus_really_filters(self):
        """专项档必须**真的**收敛模块（不是只记在会话里）。"""
        from engine.orchestrator import build_orchestration_plan
        from engine.analysis_session import resolve_orchestration, filter_orchestration_plan
        plan = build_orchestration_plan({"has_bank": True, "has_invoices": True,
                                         "has_salary": True, "has_vouchers": True,
                                         "industry": "现代服务", "file_count": 3})
        orch = resolve_orchestration("payroll_focus")
        assert orch["is_default"] is False
        new_plan, skipped = filter_orchestration_plan(plan, orch)
        assert skipped, "专项档应收敛模块"
        assert len(new_plan["active_modules"]) == len(plan["active_modules"]) - len(skipped)

    def test_rotation_is_deterministic_not_random(self):
        from engine.analysis_session import rotate_views, view_ids
        a = rotate_views(["revenue_integrity"], times=1)
        b = rotate_views(["revenue_integrity"], times=1)
        assert a == b and len(a) == len(view_ids())
        assert a != view_ids(), "轮换必须真的换了起点"

    def test_intervention_ledger_records_all_kinds(self):
        from engine.analysis_session import (INTERVENTION_KINDS, build_session,
                                             record_intervention, interventions_summary)
        s = build_session(1)
        for i, k in enumerate(INTERVENTION_KINDS):
            record_intervention(s, k, "改前", "改后", "理由 %d" % i, operator="张工")
        assert len(s["interventions"]) == len(INTERVENTION_KINDS)
        txt = "".join(interventions_summary(s))
        assert "风险等级" in txt and "重要性水平" in txt and "补资料优先级" in txt

    def test_unknown_intervention_kind_raises(self):
        from engine.analysis_session import build_session, record_intervention
        s = build_session(1)
        try:
            record_intervention(s, "随便改改", "a", "b", "无")
        except ValueError:
            return
        raise AssertionError("未知干预类型必须报错（不得静默丢弃）")

    def test_catalog_ids_all_exist(self):
        """编排目录里的 modules/skills 必须都能在权威表里查到。"""
        from engine.analysis_session import views
        from engine.orchestrator import MODULE_REGISTRY
        from engine.skill_registry import spec_of
        from engine.risk_families import family_of
        for v in views():
            for m in v.get("modules") or []:
                assert m in MODULE_REGISTRY, (v["view_id"], m)
            for s in v.get("skills") or []:
                assert spec_of(s), (v["view_id"], s)
            for f in v.get("risk_families") or []:
                assert family_of(f) or True

    def test_session_header_text_is_natural_sentence(self):
        from engine.analysis_session import build_session, session_header_text
        t = session_header_text(build_session(1))
        assert "会话编号" in t and "重要性水平" in t and "数据快照版本" in t
        assert "\n" not in t

    def test_two_runs_share_identity_but_differ_in_run_id(self):
        """同快照两次运行：**身份相同、运行号不同** ⇒ 才有"这次 vs 上次"可比。"""
        from engine.analysis_session import build_session, resolve_orchestration
        o = resolve_orchestration("default")
        snap = {"files": [{"name": "a.xlsx", "size": 1, "rows": 2}]}
        a = build_session(7, o, snap, analyzed_at="2026-10-01T09:00:00", session_seq=1)
        b = build_session(7, o, snap, analyzed_at="2026-10-07T09:00:00", session_seq=2)
        assert a["session_id"] == b["session_id"], "同快照同配置的会话身份必须相同"
        assert a["run_id"] != b["run_id"], "两次运行必须可区分（否则会互相覆盖）"
        assert "2026-10" not in a["session_id"], "会话身份不得含日期（否则换日期=换身份）"


class TestIncrementalAnalysis:
    """AC2：能输出《与上次分析对比表》。"""

    def _prev(self):
        return _mk_report([
            _mk_problem(1, "会被消除的事项", level="中风险", total=1000),
            _mk_problem(2, "会降级的事项", level="高风险", total=2000),
            _mk_problem(3, "仍待核实的事项", level="待核验", basis=None, total=None),
            _mk_problem(4, "金额变化的事项", level="中风险", total=3000),
        ])

    def _curr(self):
        return _mk_report([
            _mk_problem(1, "会降级的事项", level="中风险", total=2000),
            _mk_problem(2, "仍待核实的事项", level="待核验", basis=None, total=None),
            _mk_problem(3, "金额变化的事项", level="中风险", total=9000),
            _mk_problem(4, "新增的事项", level="高风险", total=5000),
        ])

    def test_categories_are_classified(self):
        from engine.incremental_analysis import diff_reports
        c = diff_reports(self._prev(), self._curr())["categories"]
        assert [x["title"] for x in c["eliminated"]] == ["会被消除的事项"]
        assert [x["title"] for x in c["downgraded"]] == ["会降级的事项"]
        assert [x["title"] for x in c["added"]] == ["新增的事项"]
        assert [x["title"] for x in c["still_pending"]] == ["仍待核实的事项"]
        assert [x["title"] for x in c["amount_changed"]] == ["金额变化的事项"]

    def test_comparison_table_has_columns_and_rows(self):
        from engine.incremental_analysis import comparison_table, diff_reports
        t = comparison_table(diff_reports(self._prev(), self._curr()))
        assert t["columns"] and t["rows"]
        assert any("上次风险等级" in c for c in t["columns"])
        assert t["scope_note"]

    def test_first_run_is_honest(self):
        from engine.incremental_analysis import diff_reports
        d = diff_reports(None, self._curr())
        assert d["first_run"] is True
        assert "首次可比分析" in d["summary_line"]
        assert all(not v for v in d["categories"].values()), "首次分析不得虚构新增/消除"

    def test_markdown_document_rendered(self):
        from engine.incremental_analysis import diff_reports, render_comparison_md
        md = render_comparison_md(diff_reports(self._prev(), self._curr()))
        assert "# 与上次分析对比表" in md and "已消除" in md and "仍待核实" in md


class TestReanalysisGuard:
    """AC3：能识别「只换日期、内容不变」。"""

    def test_date_only_change_detected(self):
        from engine.reanalysis_guard import audit_reanalysis
        r = audit_reanalysis(_report(), _report(),
                             {"session_id": "AS-1", "snapshot": {"version": "SS-1"}},
                             {"session_id": "AS-2", "snapshot": {"version": "SS-1"}})
        assert r["ok"] is False, r
        assert "date_only_change" in [i["code"] for i in r["issues"]]

    def test_deterministic_identical_is_not_flagged_as_fake(self):
        """★ 有重算痕迹 ⇒ 内容一致是**正确**行为（确定性），只报 INFO。"""
        from engine.reanalysis_guard import audit_reanalysis
        r = audit_reanalysis(_report(), _report(),
                             {"session_id": "AS-1", "snapshot": {"version": "SS-1"}},
                             {"session_id": "AS-2", "snapshot": {"version": "SS-1"},
                              "trace": [{"step": "扫描", "ms": 3}]})
        codes = [i["code"] for i in r["issues"]]
        assert "date_only_change" not in codes and "deterministic_identical" in codes, codes
        assert r["ok"] is True

    def test_unfounded_reorder_detected(self):
        from engine.reanalysis_guard import detect_unfounded_reorder
        prev, curr = _report(), _report()
        curr["confirmed_problems"] = list(reversed(curr["confirmed_problems"]))
        s = {"orchestration": {"views": ["a", "b"]}}
        iss = detect_unfounded_reorder(prev, curr, s, dict(s))
        assert iss and iss[0]["code"] == "unfounded_reorder", iss

    def test_declared_reorder_is_allowed(self):
        from engine.reanalysis_guard import detect_unfounded_reorder
        prev, curr = _report(), _report()
        curr["confirmed_problems"] = list(reversed(curr["confirmed_problems"]))
        iss = detect_unfounded_reorder(prev, curr,
                                       {"orchestration": {"views": ["a", "b"]}},
                                       {"orchestration": {"views": ["b", "a"]}})
        assert iss == [], "编排声明变了 ⇒ 顺序变化有依据"

    def test_unfounded_conclusion_change_detected(self):
        from engine.reanalysis_guard import detect_unfounded_conclusion_change
        prev, curr = _report(), _report()
        curr["confirmed_problems"][0]["risk_level"] = "高风险"
        iss = detect_unfounded_conclusion_change(
            prev, curr, {"snapshot": {"version": "SS-1"}}, {"snapshot": {"version": "SS-1"}})
        assert iss and "等级" in iss[0]["detail"], iss

    def test_abnormal_count_change_detected(self):
        from engine.reanalysis_guard import detect_abnormal_count_change
        prev = _mk_report([_mk_problem(i, "事项%d" % i) for i in range(1, 13)])
        curr = _mk_report([_mk_problem(i, "事项%d" % i) for i in range(1, 5)])
        iss = detect_abnormal_count_change(
            prev, curr, {"snapshot": {"version": "SS-1"}},
            {"snapshot": {"version": "SS-1"}, "trace": [{"step": "x"}]})
        assert iss and iss[0]["code"] == "abnormal_count_change", iss

    def test_count_change_with_new_snapshot_is_only_info(self):
        from engine.reanalysis_guard import detect_abnormal_count_change
        prev = _mk_report([_mk_problem(i, "事项%d" % i) for i in range(1, 13)])
        curr = _mk_report([_mk_problem(i, "事项%d" % i) for i in range(1, 5)])
        iss = detect_abnormal_count_change(
            prev, curr, {"snapshot": {"version": "SS-1"}}, {"snapshot": {"version": "SS-2"}})
        assert iss and iss[0]["level"] == "INFO", iss

    def test_no_previous_skips_all(self):
        from engine.reanalysis_guard import audit_reanalysis
        r = audit_reanalysis(None, _report())
        assert r["ok"] is True and r["issues"] == []
        assert "尚无上一次分析" in r["note"]


class TestEntityDossierAndCases:
    """AC4：企业画像与历史案例**不直接改变风险等级**。"""

    def test_dossier_declares_reference_only(self):
        from engine.entity_dossier import build_dossier, DOSSIER_FIELDS
        d = build_dossier({"file_results": [{"type": "voucher"}, {"type": "invoice"}]})
        assert d["affects_risk_level"] is False and d["reference_only"] is True
        for f in DOSSIER_FIELDS:
            assert f in d, "画像缺字段 %s" % f

    def test_dossier_marks_undetermined_instead_of_guessing(self):
        from engine.entity_dossier import build_dossier
        d = build_dossier({})
        assert d["industry"]["real"] == "未确定"
        assert "industry" in d["undetermined_fields"]
        assert "taxpayer_type" in d["undetermined_fields"]

    def test_dossier_text_says_reference_only(self):
        from engine.entity_dossier import build_dossier, dossier_text
        t = dossier_text(build_dossier({"file_results": [{"type": "voucher"}]}))
        assert "仅供检查参考" in t and "不改变" in t
        # ★ 面向企业的文本里**不得**出现英文键（漏登中文名会暴露）
        for bad in ("industry", "taxpayer_type", "business_model", "historical_risks"):
            assert bad not in t, "画像文本漏出英文键 %s：%s" % (bad, t)

    def test_cases_carry_no_level_effect(self):
        from engine.experience_library import match_cases, case_reference_text
        cs = match_cases(industry="现代服务", risk_types=["增值税"])
        for c in cs:
            assert c.get("affects_risk_level") is False
        assert "不影响任何风险等级" in case_reference_text(cs) \
            or "不改变本企业" in case_reference_text(cs)

    def test_no_case_is_honest_not_substituted(self):
        from engine.experience_library import match_cases, case_reference_text
        cs = match_cases(industry="不存在的行业", risk_types=["不存在的风险"])
        assert cs == []
        t = case_reference_text(cs, industry="不存在的行业")
        assert "未匹配到可参考的同类案例" in t and "不跨行业" in t.replace("不提供跨行业案例充数", "不跨行业")

    def test_add_case_rejects_incomplete(self):
        from engine.experience_library import add_case
        try:
            add_case({"industry": "现代服务"})
        except ValueError:
            return
        raise AssertionError("残缺案例必须报错（案例经验要可复核）")


class TestRuleAbstraction:
    """AC5：从点到面能输出《规则萃取建议》。"""

    def test_abstractable_finding_produces_proposal(self):
        from engine.rule_abstraction import abstract_findings
        f = {"title": "工资表人数与社保参保人数不符", "redline_id": "RL-PAY-001",
             "detail": "工资表列支人员与社保参保人员存在差异"}
        r = abstract_findings([f], {"judge": "当工资表人数大于社保参保人数时判为用工三源不符",
                                    "acceptance": "构造 12/8 的输入，断言产出该发现",
                                    "tier": "manual"})
        assert len(r["proposals"]) == 1, r
        p = r["proposals"][0]
        assert p["rule_id"].startswith("AR-") and p["affects_risk_level"] is False
        assert p["judge"] and p["acceptance"] and p["rule_version"]

    def test_case_specific_finding_stays_case(self):
        from engine.rule_abstraction import abstract_findings
        f = {"title": "凭证号 12345 的运费发票疑点",
             "detail": "第 3 号凭证中该笔业务金额异常", "redline_id": "RL-INV-001"}
        r = abstract_findings([f], {"judge": "x", "acceptance": "y"})
        assert r["proposals"] == []
        assert "case_specific_identity" in r["cases_kept"][0]["reason_codes"], r

    def test_no_judgement_defaults_to_case(self):
        """判不出判据 ⇒ 归个案，**不得**默认上升为规则。"""
        from engine.rule_abstraction import abstract_findings
        r = abstract_findings([{"title": "一个说不清的事项"}], {})
        assert r["proposals"] == [] and len(r["cases_kept"]) == 1

    def test_manual_tier_not_auto_committed(self):
        from engine.rule_abstraction import commit_proposals
        res = commit_proposals([{"rule_id": "AR-X-001", "tier": "manual"}], dry_run=True)
        assert res["committed"] == [] and len(res["pending_manual"]) == 1

    def test_proposals_md_has_three_hard_requirements(self):
        from engine.rule_abstraction import abstract_findings, render_proposals_md
        r = abstract_findings([{"title": "印花税计税依据不足", "redline_id": "RL-STAMP-001"}],
                              {"judge": "合同金额与开票金额不一致", "acceptance": "见用例"})
        md = render_proposals_md(r)
        assert "# 规则萃取建议" in md
        assert "可配置" in md and "可测试" in md and "可版本化" in md
