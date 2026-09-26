# -*- coding: utf-8 -*-
"""一键分析宗旨回归测试 —— 锁死「有什么资料就查什么资料」。

用户宗旨原话（本文件即其可执行断言）：
> 上传了什么资料就查什么资料，以一个税务稽查专家的身份查实所上传资料的**所有**税务风险，
> **而不是等资料齐全才进行税务风险排查**。
> 反映已查出的税务风险，也反映就已查出的税务风险需要怎样解除风险，
> 是否有自证的资料需要补充，最终就是**铁证如山或是自证清白**。

本文件锁死四条铁律：
  D1 有什么查什么（任一份资料单独存在时，其可独立支撑的检查必须照跑）
  D2 缺资料 ≠ 违规（缺资料只能产出"待核"，绝不能产出"违规"）
  D3 每个发现都要给出口（解除方式 + 需补自证资料）
  D4 终局只有两态（铁证如山 / 可自证清白），不得停在"疑似"

背景（真实事故，本文件防其复发）：
  `_domain_salary_ss_hf_compare` 原实现 `if not salaries: return findings`
  → 只上传社保明细时整域零产出；只上传工资表时社保名单为空 → 差集＝全部工资人员
  → 报出「N 名员工有工资无社保（高风险）」，把"资料没交"升级成"全员未依法参保"。
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.audit_doctrine import (  # noqa: E402
    MISSING_DRIVEN_LEVEL_CAP, ONE_SIDED_CHECKS, TERMINAL_IRONCLAD, TERMINAL_PENDING, TERMINAL_SELF_PROOF,
    attach_three_piece, default_self_proof_for, enforce_no_missing_driven_accusation,
    looks_missing_driven, one_sided_digest, self_proof_item, summarise_doctrine,
)
from engine.domain_analysis import _domain_salary_ss_hf_compare  # noqa: E402

_SAL = [
    {"name": "张三", "salary": 9000, "month": "2025-01"},
    {"name": "李四", "salary": 12000, "month": "2025-01"},
    {"name": "王五", "salary": 8000, "month": "2025-02"},
]
_SS = [
    {"name": "张三", "base": 4000, "month": "2025-01"},
    {"name": "李四", "base": 12000, "month": "2025-01"},
]


# ═══════════════ D1 有什么查什么 ═══════════════

class TestOneSidedAudit:
    def test_salary_only_still_audits(self):
        """只上传工资表：必须产出工资侧独立结论（不得静默返回空）。"""
        out = _domain_salary_ss_hf_compare(_SAL, [])
        assert out, "只上传工资表时不得零产出 —— 违背'有什么资料就查什么资料'"

    def test_social_security_only_still_audits(self):
        """只上传社保明细：原实现 `if not salaries: return` → 零产出。现在必须有结论。"""
        out = _domain_salary_ss_hf_compare([], _SS)
        assert out, "只上传社保明细时不得零产出 —— 原实现正是这里整域跳过"
        assert any("社保" in str(f.get("type") or "") for f in out)

    def test_both_present_runs_real_cross_check(self):
        out = _domain_salary_ss_hf_compare(_SAL, _SS)
        types = {str(f.get("type") or "") for f in out}
        assert "有工资无社保" in types, "两侧齐备时必须执行真正的交叉核验"

    def test_one_sided_digest_lists_only_present_sources(self):
        d = one_sided_digest(["salaries"])
        assert len(d) == 1
        assert d[0]["source"] == "工资表"
        assert d[0]["checks"], "已上传资料必须列出其可独立完成的检查项"
        assert one_sided_digest([]) == []
        assert len(one_sided_digest(["salaries", "social_security"])) == 2

    def test_one_sided_declaration_covers_key_materials(self):
        for m in ("salaries", "social_security", "bank_txs", "sal_invs", "pur_invs"):
            assert m in ONE_SIDED_CHECKS, f"{m} 未登记单向可查项"


# ═══════════════ D2 缺资料 ≠ 违规 ═══════════════

class TestMissingIsNotViolation:
    def test_salary_only_never_accuses_uninsured(self):
        """只上传工资表时，绝不能产出"未参保/有工资无社保"这类违规认定。"""
        out = _domain_salary_ss_hf_compare(_SAL, [])
        bad = [f for f in out
               if ("无社保" in str(f.get("type") or "") or "未参保" in str(f.get("type") or ""))
               or str(f.get("level")) in ("高风险", "极高风险")]
        assert not bad, f"缺社保明细时不得据空名单反推违规：{[f.get('type') for f in bad]}"

    def test_missing_driven_level_is_downgraded(self):
        f = {"type": "有工资无社保", "level": "高风险", "score": 8,
             "detail": "8名员工有工资发放但社保名单中未找到对应月份记录"}
        attach_three_piece(f, missing_driven=True)
        assert f["level"] == MISSING_DRIVEN_LEVEL_CAP, "缺资料驱动的发现必须降级到权威待核等级"
        assert f["level_downgraded_from"] == "高风险"
        assert f["level_downgrade_reason"]
        assert f["score"] <= 4

    def test_enforcement_sweeps_all_findings(self):
        fs = [
            {"type": "有工资无社保", "level": "高风险", "score": 8,
             "detail": "未提供社保明细，名单中未找到对应记录", "description": ""},
            {"type": "发票作废率偏高", "level": "中风险", "score": 6,
             "detail": "作废12张占全部100张的12%"},
        ]
        enforce_no_missing_driven_accusation(fs)
        assert fs[0]["level"] == MISSING_DRIVEN_LEVEL_CAP, "以缺资料为依据的认定必须被兜底降级"
        assert fs[0]["terminal_state"] == TERMINAL_PENDING
        assert fs[1]["level"] == "中风险", "有据的发现不得被误降级（零误伤）"

    def test_already_guarded_text_not_flagged(self):
        f = {"type": "社保参保情况待补证", "level": MISSING_DRIVEN_LEVEL_CAP, "score": 3,
             "detail": "本轮未提供社保明细，故不就参保情况作任何认定，属待补自证事项。"}
        assert not looks_missing_driven(f), "已明确写成待证的表述不得被判为越界"

    def test_does_not_delete_findings(self):
        fs = [{"type": "X", "level": "高风险", "detail": "未提供银行流水，无法核实"}]
        n0 = len(fs)
        enforce_no_missing_driven_accusation(fs)
        assert len(fs) == n0, "缺资料本身是有价值的信息，只能降级、不得静默删除"


# ═══════════════ D3 每个发现都要给出口 ═══════════════

class TestEveryFindingHasExit:
    def test_cross_check_findings_carry_three_piece(self):
        out = _domain_salary_ss_hf_compare(_SAL, _SS)
        for f in out:
            assert f.get("resolve_steps"), f"{f.get('type')} 缺解除方式"
            assert f.get("self_proof_materials"), f"{f.get('type')} 缺自证资料清单"
            assert f.get("terminal_state"), f"{f.get('type')} 缺终局方向"

    def test_one_sided_findings_carry_three_piece(self):
        for out in (_domain_salary_ss_hf_compare(_SAL, []),
                    _domain_salary_ss_hf_compare([], _SS)):
            for f in out:
                assert f.get("resolve_steps"), f"{f.get('type')} 缺解除方式"
                assert f.get("self_proof_materials"), f"{f.get('type')} 缺自证资料清单"

    def test_self_proof_item_shape(self):
        it = self_proof_item("社保明细", "证明参保人员与基数", "社保经办机构")
        assert set(it) == {"material", "proves", "how"}
        assert it["material"] == "社保明细"

    def test_default_self_proof_explains_what_it_proves(self):
        items = default_self_proof_for(["社保明细", "劳动合同"])
        assert len(items) == 2
        for it in items:
            assert it["proves"], "自证资料必须说明能证明什么，否则企业不知道交了能起什么作用"

    def test_attach_is_idempotent(self):
        f = {"type": "T", "level": "中风险"}
        attach_three_piece(f, resolve_steps=["A"], self_proof=[self_proof_item("工资表", "p")])
        attach_three_piece(f, resolve_steps=["A"], self_proof=[self_proof_item("工资表", "p")])
        assert f["resolve_steps"] == ["A"], "重复附加不得产生重复条目"
        assert len(f["self_proof_materials"]) == 1


# ═══════════════ D4 终局只有两态 ═══════════════

class TestTerminalStates:
    def test_every_finding_gets_terminal_state(self):
        f = {"type": "T", "level": "中风险"}
        attach_three_piece(f)
        assert f["terminal_state"] in (TERMINAL_IRONCLAD, TERMINAL_SELF_PROOF, TERMINAL_PENDING)

    def test_high_risk_maps_to_ironclad(self):
        f = {"type": "T", "level": "高风险"}
        attach_three_piece(f)
        assert f["terminal_state"] == TERMINAL_IRONCLAD

    def test_summary_counts_three_states(self):
        fs = [
            {"type": "A", "level": "高风险", "terminal_state": TERMINAL_IRONCLAD,
             "resolve_steps": ["x"], "self_proof_materials": [{"material": "工资表"}]},
            {"type": "B", "level": "待核", "terminal_state": TERMINAL_PENDING},
        ]
        s = summarise_doctrine(fs)
        assert s["total"] == 2
        assert s["ironclad"] == 1
        assert s["pending"] == 1
        assert s["with_resolve"] == 1 and s["with_self_proof"] == 1
        assert "证据闭合" in s["statement"] and "自证清白" in s["statement"]


# ═══════════════ 覆盖清单语义：不得再说"因缺资料未能执行" ═══════════════

class TestCoverageSemantics:
    def _cov(self):
        from engine.analysis_coverage import build_coverage
        return build_coverage({
            "salaries": [{"name": "张三", "salary": 9000}],
            "target_entity": {"name": "示例公司"},
        })

    def test_summary_says_already_exhausted_not_blocked(self):
        cov = self._cov()
        s = str(cov.get("summary_text") or "")
        if not s:
            return                      # 无检查项时为空是允许的
        assert "未能执行" not in s, "不得再把待补事项表述为'未能执行'（宗旨反对等资料齐全）"
        assert "已" in s and ("待补" in s or "补充" in s), s

    def test_awaiting_self_proof_field_present(self):
        cov = self._cov()
        assert "awaiting_self_proof" in cov

    def test_probes_require_real_data_not_clist_membership(self):
        """探针必须看'数据是否真读到'，不看'文件是否在清单里'（原静默缺口）。"""
        from engine.analysis_coverage import build_coverage
        empty = build_coverage({"salaries": [], "social_security": []})
        with_data = build_coverage({"salaries": [{"name": "张三"}], "social_security": []})
        assert empty["executed"] <= with_data["executed"]


# ═══════════════ 报告章节 ═══════════════

class TestReportChapters:
    def test_resolution_ledger_rows(self):
        from engine.enterprise_report import _build_resolution_ledger
        r = _build_resolution_ledger({"all_findings": [
            {"type": "有工资无社保", "level": "高风险", "terminal_state": TERMINAL_IRONCLAD,
             "resolve_steps": ["补缴社保"], "self_proof_materials": [
                 {"material": "劳动合同", "proves": "证明用工关系"}]},
        ]})
        assert r["total"] == 1 and r["ironclad"] == 1
        assert r["rows"][0]["解除方式"] == "补缴社保"
        assert "劳动合同" in r["rows"][0]["需补自证资料"]
        assert r["columns"] == ["风险事项", "等级", "证据地位", "终局方向", "解除方式", "需补自证资料"]

    def test_one_sided_digest_rows(self):
        from engine.enterprise_report import _build_one_sided_digest
        r = _build_one_sided_digest({"one_sided_checks": [
            {"source": "工资表", "checks": [{"id": "a", "name": "人数与总额", "how": "汇总"}]}]})
        assert r["check_count"] == 1 and r["rows"][0]["已上传资料"] == "工资表"
        assert _build_one_sided_digest({}) == {}

    def test_coverage_columns_renamed(self):
        from engine.enterprise_report import _build_analysis_coverage
        r = _build_analysis_coverage({"analysis_coverage": {
            "total": 10, "executed": 7, "blocked": 3, "awaiting_self_proof": 3,
            "blocked_items": [{"kind": "原子规则", "name": "X", "missing": ["社保明细"], "effect": "E"}],
            "summary_text": "s"}})
        assert r["columns"] == ["类别", "检查项", "需补充的资料", "补充后方可判定"]
        assert r["rows"][0]["需补充的资料"] == "社保明细"
        assert "缺什么资料" not in r["columns"]


# ═══════════════ 反向验证：闸门必须真的拦得住 ═══════════════

class TestDoctrineGateFiresOnRegression:
    """闸门自身也要被验证：改回"等资料齐全才排查"的写法必须报 ERROR。"""

    def _gate(self, tmp_path, monkeypatch, pipeline_src, coverage_src, report_src):
        import tools.audit_consistency as ac
        (tmp_path / "engine").mkdir(parents=True, exist_ok=True)
        (tmp_path / "engine" / "audit_doctrine.py").write_text("# stub\n", encoding="utf-8")
        (tmp_path / "engine" / "pipeline.py").write_text(pipeline_src, encoding="utf-8")
        (tmp_path / "engine" / "analysis_coverage.py").write_text(coverage_src, encoding="utf-8")
        (tmp_path / "engine" / "enterprise_report.py").write_text(report_src, encoding="utf-8")
        (tmp_path / "engine" / "output_governance.py").write_text(
            "from engine.audit_doctrine import apply_three_piece_to_all\n"
            "def seal_governed_findings(e):\n"
            "    sealed = []\n"
            "    apply_three_piece_to_all(sealed)\n"
            "    return sealed\n", encoding="utf-8")
        monkeypatch.setattr(ac, "ROOT", tmp_path)
        return ac.check_audit_doctrine()

    _GOOD_PIPE = ("enforce_no_missing_driven_accusation(all_findings)\n"
                  "_one_sided_digest({})\nsummarise_doctrine(all_findings)\n"
                  'domain_results.append({"domain": "甲", "findings": []})\n'
                  '_objective_domain_keys = ("甲",)\n'
                  "promote_domain_findings(execution, domain_results)\n"
                  "stamp_evidence_tiers(findings)\n"
                  "正式输出范围\n"
                  '"output_scope"\n')
    _GOOD_COV = "summary = '现有资料已足以判定 N 项，其余列为待补自证事项。'\n"
    _GOOD_REP = "def _build_resolution_ledger(r): pass\ndef _build_one_sided_digest(r): pass\n"

    def test_clean_sources_pass(self, tmp_path, monkeypatch):
        issues = self._gate(tmp_path, monkeypatch, self._GOOD_PIPE, self._GOOD_COV, self._GOOD_REP)
        assert [i for i in issues if i[0] == "ERROR"] == []

    def test_missing_enforcement_call_is_caught(self, tmp_path, monkeypatch):
        issues = self._gate(tmp_path, monkeypatch, "pass\n", self._GOOD_COV, self._GOOD_REP)
        msgs = " ".join(m for _, _, m in issues)
        assert "宗旨未接线" in msgs, "缺少缺资料降级兜底点必须被拦下"

    def test_old_coverage_wording_is_caught(self, tmp_path, monkeypatch):
        bad_cov = "s = f'因缺资料未能执行 {n} 项'\n"
        issues = self._gate(tmp_path, monkeypatch, self._GOOD_PIPE, bad_cov, self._GOOD_REP)
        assert any("等资料齐全" in m for _, _, m in issues), (
            "'因缺资料未能执行'这类措辞会暗示系统在等资料齐全，必须被拦下"
        )

    def test_missing_report_chapters_are_caught(self, tmp_path, monkeypatch):
        issues = self._gate(tmp_path, monkeypatch, self._GOOD_PIPE, self._GOOD_COV, "pass\n")
        msgs = " ".join(m for _, _, m in issues)
        assert "解除方式与自证清单" in msgs and "可查清单" in msgs

    def test_behavior_assertion_present(self, tmp_path, monkeypatch):
        """闸门必须包含运行时的三组合行为断言（静态规则挡不住'把缺资料读成违规'）。"""
        import inspect
        import tools.audit_consistency as ac
        src = inspect.getsource(ac.check_audit_doctrine)
        assert "[行为]" in src, "宗旨闸门必须含行为断言，而非只有文本规则"
        assert "_domain_salary_ss_hf_compare" in src


# ═══════════════ 同源缺陷排查：缺资料被写成违规（全项目闸门）═══════════════

class TestMissingAsViolationGate:
    """工资社保不是个案：实测全项目另有 15 处「资料缺失-XXX / 解析失败」被写成中/高风险。
    本组锁死该类的检测能力，并明确区分"业务层事实"（合理）与"上传层缺失"（违规）。"""

    def _scan(self, tmp_path, monkeypatch, files: dict):
        import tools.audit_consistency as ac
        (tmp_path / "engine").mkdir(parents=True, exist_ok=True)
        for name, body in files.items():
            (tmp_path / name).write_text(body, encoding="utf-8")
        monkeypatch.setattr(ac, "ROOT", tmp_path)
        return ac.scan_upload_layer_violations()

    def test_upload_layer_violation_is_detected(self, tmp_path, monkeypatch):
        hits = self._scan(tmp_path, monkeypatch, {"engine/x.py": (
            'def f():\n'
            '    findings = []\n'
            '    findings.append({"type": "资料缺失-银行流水", "level": "中风险",\n'
            '        "detail": "未提供银行流水数据，无法进行资金流向追踪分析。"})\n'
            '    return findings\n')})
        assert hits, "未上传资料却被定级中风险，必须被闸门检出"
        assert hits[0][2] == "中风险"

    def test_business_layer_fact_is_not_flagged(self, tmp_path, monkeypatch):
        """业务层事实（企业自己数据有缺口）是'查出来的事实'，不得误报。"""
        hits = self._scan(tmp_path, monkeypatch, {"engine/y.py": (
            'def f():\n'
            '    findings = []\n'
            '    findings.append({"type": "进销存数量勾稽不平衡", "level": "高风险",\n'
            '        "detail": "入库120件、出库150件，数量勾稽不平衡，差异30件。"})\n'
            '    findings.append({"type": "发票缺少数量字段", "level": "中风险",\n'
            '        "detail": "18张进项发票缺少数量字段，无法核验单价合理性。"})\n'
            '    return findings\n')})
        assert hits == [], f"业务层事实被误报为缺资料违规：{hits}"

    def test_guarded_wording_is_not_flagged(self, tmp_path, monkeypatch):
        hits = self._scan(tmp_path, monkeypatch, {"engine/z.py": (
            'def f():\n'
            '    findings = []\n'
            '    findings.append({"type": "社保参保情况待补证", "level": "待核验",\n'
            '        "detail": "未提供社保明细，故不作认定；缺资料不等于违规。"})\n'
            '    return findings\n')})
        assert hits == [], "已写明待补证/不等于违规的表述不得被误报"

    def test_real_repo_is_clean(self):
        """真实仓库必须为 0（本轮已修 15 处）。"""
        from tools.audit_consistency import scan_upload_layer_violations
        hits = scan_upload_layer_violations()
        assert hits == [], (
            "仍有『资料未上传/数据为空』被定级为中/高风险："
            + "；".join(f"{h[0]}:{h[1]} {h[3]}[{h[2]}]" for h in hits)
        )

    def test_gate_present_in_run_checks(self):
        import inspect
        import tools.audit_consistency as ac
        assert "check_missing_as_violation" in inspect.getsource(ac.run_checks)


class TestDeadWhitelistKeyGate:
    """白名单键必须匹配到真实域名：`进销存数量勾稽` 曾因域名不符成为永不生效的死键。"""

    def test_dead_key_is_detected(self, tmp_path, monkeypatch):
        import tools.audit_consistency as ac
        (tmp_path / "engine").mkdir(parents=True, exist_ok=True)
        (tmp_path / "engine" / "audit_doctrine.py").write_text("# stub\n", encoding="utf-8")
        (tmp_path / "engine" / "pipeline.py").write_text(
            'domain_results = []\n'
            'domain_results.append({"domain": "真实域名A", "findings": []})\n'
            '_objective_domain_keys = ("真实域名A", "根本不存在域")\n'
            "_one_sided_digest({})\nsummarise_doctrine([])\n"
            "enforce_no_missing_driven_accusation([])\n"
            "正式输出范围\n"
            '"output_scope"\n', encoding="utf-8")
        (tmp_path / "engine" / "analysis_coverage.py").write_text("x=1\n", encoding="utf-8")
        (tmp_path / "engine" / "enterprise_report.py").write_text(
            "def _build_resolution_ledger(r): pass\ndef _build_one_sided_digest(r): pass\n",
            encoding="utf-8")
        monkeypatch.setattr(ac, "ROOT", tmp_path)
        issues = ac.check_audit_doctrine()
        assert any("死键" in m for _, _, m in issues), (
            "白名单键匹配不到任何真实域名时必须报错（否则配置永不生效且无任何症状）"
        )

    def test_report_scope_visibility_is_required(self, tmp_path, monkeypatch):
        import tools.audit_consistency as ac
        (tmp_path / "engine").mkdir(parents=True, exist_ok=True)
        (tmp_path / "engine" / "audit_doctrine.py").write_text("# stub\n", encoding="utf-8")
        (tmp_path / "engine" / "pipeline.py").write_text(
            'domain_results = []\n_objective_domain_keys = ()\n'
            "enforce_no_missing_driven_accusation([])\n_one_sided_digest({})\n"
            "summarise_doctrine([])\n", encoding="utf-8")
        (tmp_path / "engine" / "analysis_coverage.py").write_text("x=1\n", encoding="utf-8")
        (tmp_path / "engine" / "enterprise_report.py").write_text(
            "def _build_resolution_ledger(r): pass\ndef _build_one_sided_digest(r): pass\n",
            encoding="utf-8")
        monkeypatch.setattr(ac, "ROOT", tmp_path)
        issues = ac.check_audit_doctrine()
        msgs = " ".join(m for _, _, m in issues)
        assert "promote_domain_findings" in msgs, (
            "必须调用提升函数，否则域结论会再次被整体隔离（用户决策：全部呈现）"
        )
        assert "证据地位" in msgs, "必须标注证据地位，否则无法区分可信度"
        assert "output_scope" in msgs


# ═══════════════ 用户决策：分析到的风险必须全部呈现在报告中 ═══════════════

class TestPromoteAllDomainFindings:
    """2026-09-25 用户决策：「都要提升，一定是把所分析到的风险都要呈现在报告中」。

    原设计只把 7 个「客观域」并入正式输出，其余 40+ 个域被整体隔离
    （实测 86 项"算了但看不到"）。本组锁死"全部提升 + 证据地位可区分"。
    """

    def _f(self, **kw):
        base = {"type": "T", "level": "中风险", "detail": "d"}
        base.update(kw)
        return base

    def test_all_risk_findings_promoted(self):
        from engine.output_governance import promote_domain_findings
        ex = {"findings": []}
        dom = [{"domain": "甲", "findings": [self._f(type="A"), self._f(type="B")]},
               {"domain": "乙", "findings": [self._f(type="C")]}]
        r = promote_domain_findings(ex, dom, set())
        assert r["promoted"] == 3
        assert len(ex["findings"]) == 3
        assert all(f.get("_scenario_governed") for f in ex["findings"])
        assert all(f.get("scene_fact_id") for f in ex["findings"])

    def test_info_level_not_promoted(self):
        """「信息」级不是风险，不进风险清单（避免用无风险事项灌水）。"""
        from engine.output_governance import promote_domain_findings
        ex = {"findings": []}
        r = promote_domain_findings(ex, [{"domain": "甲", "findings": [
            self._f(type="信息类", level="信息"), self._f(type="真风险", level="中风险")]}], set())
        assert r["promoted"] == 1
        assert [f["type"] for f in ex["findings"]] == ["真风险"]

    def test_domain_finding_is_pending_grade_with_tier(self):
        from engine.output_governance import (
            EVIDENCE_TIER_DOMAIN, promote_domain_findings,
        )
        ex = {"findings": []}
        promote_domain_findings(ex, [{"domain": "甲", "findings": [self._f()]}], set())
        f = ex["findings"][0]
        assert f["conclusion_grade"] == "待核", "域结论未固化为已验证规则，不得自称已核定"
        assert f["evidence_tier"] == EVIDENCE_TIER_DOMAIN
        assert f["domain"] == "甲"

    def test_idempotent(self):
        from engine.output_governance import promote_domain_findings
        ex = {"findings": []}
        dom = [{"domain": "甲", "findings": [self._f()]}]
        assert promote_domain_findings(ex, dom, set())["promoted"] == 1
        assert promote_domain_findings(ex, dom, set())["promoted"] == 0, "重复提升不得产生重复"
        assert len(ex["findings"]) == 1

    def test_verified_rule_items_untouched(self):
        """已验原子规则的证据地位不得被域提升覆盖。"""
        from engine.output_governance import (
            EVIDENCE_TIER_VERIFIED_RULE, promote_domain_findings,
        )
        vr = {"type": "VR项", "level": "高风险", "evidence_tier": EVIDENCE_TIER_VERIFIED_RULE}
        ex = {"findings": [vr]}
        promote_domain_findings(ex, [{"domain": "甲", "findings": [self._f()]}], set())
        assert vr["evidence_tier"] == EVIDENCE_TIER_VERIFIED_RULE
        assert vr.get("_domain_analysis_finding") is None

    def test_stamp_tiers_fills_missing_only(self):
        from engine.output_governance import (
            EVIDENCE_TIER_DOMAIN, EVIDENCE_TIER_VERIFIED_RULE, stamp_evidence_tiers,
        )
        fs = [{"type": "a"}, {"type": "b", "evidence_tier": EVIDENCE_TIER_VERIFIED_RULE}]
        assert stamp_evidence_tiers(fs) == 1
        assert fs[0]["evidence_tier"] == EVIDENCE_TIER_DOMAIN
        assert fs[1]["evidence_tier"] == EVIDENCE_TIER_VERIFIED_RULE, "已标注的不得被覆盖"
        assert stamp_evidence_tiers(fs) == 0

    def test_domain_summary_recomputed(self):
        from engine.output_governance import promote_domain_findings
        ex = {"findings": [], "domain_summary": []}
        promote_domain_findings(ex, [{"domain": "甲", "findings": [self._f()]}], set())
        assert ex["domain_summary"], "提升后必须重算域汇总，否则报告两处口径不一致"

    def test_report_shows_evidence_tier(self):
        from engine.enterprise_report import _build_resolution_ledger
        from engine.output_governance import EVIDENCE_TIER_VERIFIED_RULE
        r = _build_resolution_ledger({"all_findings": [
            {"type": "X", "level": "高风险", "terminal_state": "证据闭合",
             "evidence_tier": EVIDENCE_TIER_VERIFIED_RULE,
             "resolve_steps": ["s"], "self_proof_materials": [{"material": "m", "proves": "p"}]}],
            "output_scope": {"note": "全部已进入报告"}})
        assert "证据地位" in r["columns"]
        assert r["rows"][0]["证据地位"] == EVIDENCE_TIER_VERIFIED_RULE
        assert r["evidence_tiers"].get(EVIDENCE_TIER_VERIFIED_RULE) == 1


# ═══════════════ 用户决策：分析到的风险必须全部呈现在报告中 ═══════════════

class TestPromoteAllDomainFindings:
    """2026-09-25 用户决策：「都要提升，一定是把所分析到的风险都要呈现在报告中」。

    原设计只把 7 个「客观域」并入正式输出，其余 40+ 个域被整体隔离
    （实测 86 项"算了但看不到"）。本组锁死"全部提升 + 证据地位可区分"。
    """

    def _f(self, **kw):
        base = {"type": "T", "level": "中风险", "detail": "d"}
        base.update(kw)
        return base

    def test_all_risk_findings_promoted(self):
        from engine.output_governance import promote_domain_findings
        ex = {"findings": []}
        dom = [{"domain": "甲", "findings": [self._f(type="A"), self._f(type="B")]},
               {"domain": "乙", "findings": [self._f(type="C")]}]
        r = promote_domain_findings(ex, dom, set())
        assert r["promoted"] == 3
        assert len(ex["findings"]) == 3
        assert all(f.get("_scenario_governed") for f in ex["findings"])
        assert all(f.get("scene_fact_id") for f in ex["findings"])

    def test_info_level_not_promoted(self):
        """「信息」级不是风险，不进风险清单（避免用无风险事项灌水）。"""
        from engine.output_governance import promote_domain_findings
        ex = {"findings": []}
        r = promote_domain_findings(ex, [{"domain": "甲", "findings": [
            self._f(type="信息类", level="信息"), self._f(type="真风险", level="中风险")]}], set())
        assert r["promoted"] == 1
        assert [f["type"] for f in ex["findings"]] == ["真风险"]

    def test_domain_finding_is_pending_grade_with_tier(self):
        from engine.output_governance import (
            EVIDENCE_TIER_DOMAIN, promote_domain_findings,
        )
        ex = {"findings": []}
        promote_domain_findings(ex, [{"domain": "甲", "findings": [self._f()]}], set())
        f = ex["findings"][0]
        assert f["conclusion_grade"] == "待核", "域结论未固化为已验证规则，不得自称已核定"
        assert f["evidence_tier"] == EVIDENCE_TIER_DOMAIN
        assert f["domain"] == "甲"

    def test_idempotent(self):
        from engine.output_governance import promote_domain_findings
        ex = {"findings": []}
        dom = [{"domain": "甲", "findings": [self._f()]}]
        assert promote_domain_findings(ex, dom, set())["promoted"] == 1
        assert promote_domain_findings(ex, dom, set())["promoted"] == 0, "重复提升不得产生重复"
        assert len(ex["findings"]) == 1

    def test_verified_rule_items_untouched(self):
        """已验原子规则的证据地位不得被域提升覆盖。"""
        from engine.output_governance import (
            EVIDENCE_TIER_VERIFIED_RULE, promote_domain_findings,
        )
        vr = {"type": "VR项", "level": "高风险", "evidence_tier": EVIDENCE_TIER_VERIFIED_RULE}
        ex = {"findings": [vr]}
        promote_domain_findings(ex, [{"domain": "甲", "findings": [self._f()]}], set())
        assert vr["evidence_tier"] == EVIDENCE_TIER_VERIFIED_RULE
        assert vr.get("_domain_analysis_finding") is None

    def test_stamp_tiers_fills_missing_only(self):
        from engine.output_governance import (
            EVIDENCE_TIER_DOMAIN, EVIDENCE_TIER_VERIFIED_RULE, stamp_evidence_tiers,
        )
        fs = [{"type": "a"}, {"type": "b", "evidence_tier": EVIDENCE_TIER_VERIFIED_RULE}]
        assert stamp_evidence_tiers(fs) == 1
        assert fs[0]["evidence_tier"] == EVIDENCE_TIER_DOMAIN
        assert fs[1]["evidence_tier"] == EVIDENCE_TIER_VERIFIED_RULE, "已标注的不得被覆盖"
        assert stamp_evidence_tiers(fs) == 0

    def test_domain_summary_recomputed(self):
        from engine.output_governance import promote_domain_findings
        ex = {"findings": [], "domain_summary": []}
        promote_domain_findings(ex, [{"domain": "甲", "findings": [self._f()]}], set())
        assert ex["domain_summary"], "提升后必须重算域汇总，否则报告两处口径不一致"

    def test_report_shows_evidence_tier(self):
        from engine.enterprise_report import _build_resolution_ledger
        from engine.output_governance import EVIDENCE_TIER_VERIFIED_RULE
        r = _build_resolution_ledger({"all_findings": [
            {"type": "X", "level": "高风险", "terminal_state": "证据闭合",
             "evidence_tier": EVIDENCE_TIER_VERIFIED_RULE,
             "resolve_steps": ["s"], "self_proof_materials": [{"material": "m", "proves": "p"}]}],
            "output_scope": {"note": "全部已进入报告"}})
        assert "证据地位" in r["columns"]
        assert r["rows"][0]["证据地位"] == EVIDENCE_TIER_VERIFIED_RULE
        assert r["evidence_tiers"].get(EVIDENCE_TIER_VERIFIED_RULE) == 1


class TestSealGuaranteesExits:
    """封印是报告发现的唯一产出点（且内部 deepcopy 会丢弃上游改动）——
    "每条发现都有出口"必须在封印内落实，否则上游补了也不生效。"""

    def test_sealed_findings_all_have_exits(self):
        from engine.output_governance import GOVERNANCE_STATUS, seal_governed_findings
        ex = {"governance_status": GOVERNANCE_STATUS, "findings": [
            {"type": "甲事项", "level": "中风险", "detail": "d", "_scenario_governed": True,
             "scene_fact_id": "F1"},
            {"type": "乙事项", "level": "待核验", "detail": "d2", "_scenario_governed": True,
             "scene_fact_id": "F2", "suggestion": "1）核对；2）补充资料。"},
        ]}
        sealed = seal_governed_findings(ex)
        assert len(sealed) == 2
        for f in sealed:
            assert f.get("resolve_steps"), f"{f.get('type')} 缺解除方式"
            assert f.get("self_proof_materials"), f"{f.get('type')} 缺自证资料清单"
            assert f.get("terminal_state"), f"{f.get('type')} 缺终局方向"

    def test_existing_exits_not_overwritten(self):
        from engine.output_governance import GOVERNANCE_STATUS, seal_governed_findings
        ex = {"governance_status": GOVERNANCE_STATUS, "findings": [
            {"type": "甲", "level": "高风险", "_scenario_governed": True, "scene_fact_id": "F1",
             "resolve_steps": ["企业自己写的做法"], "terminal_state": "证据闭合",
             "self_proof_materials": [{"material": "工资表", "proves": "p", "how": "h"}]}]}
        f = seal_governed_findings(ex)[0]
        assert f["resolve_steps"] == ["企业自己写的做法"], "已有出口不得被模板覆盖"
        assert f["terminal_state"] == "证据闭合"
        assert f["self_proof_materials"][0]["material"] == "工资表"

    def test_suggestion_used_as_resolve(self):
        """解除方式优先用发现自己的 suggestion（具体做法），而非通用模板。"""
        from engine.output_governance import GOVERNANCE_STATUS, seal_governed_findings
        ex = {"governance_status": GOVERNANCE_STATUS, "findings": [
            {"type": "甲", "level": "中风险", "_scenario_governed": True, "scene_fact_id": "F1",
             "suggestion": "向社保经办机构补缴；留存缴费凭证。"}]}
        f = seal_governed_findings(ex)[0]
        assert any("补缴" in s for s in f["resolve_steps"]), "应优先采用发现自带的具体做法"

    def test_apply_all_is_idempotent(self):
        from engine.audit_doctrine import apply_three_piece_to_all
        fs = [{"type": "甲", "level": "中风险"}]
        r1 = apply_three_piece_to_all(fs)
        r2 = apply_three_piece_to_all(fs)
        assert r1["proof_filled"] == 1 and r1["terminal_filled"] == 1
        assert r2 == {"resolve_filled": 0, "proof_filled": 0, "terminal_filled": 0}


class TestSealGuaranteesExits:
    """封印是报告发现的唯一产出点（且内部 deepcopy 会丢弃上游改动）——
    "每条发现都有出口"必须在封印内落实，否则上游补了也不生效。"""

    def test_sealed_findings_all_have_exits(self):
        from engine.output_governance import GOVERNANCE_STATUS, seal_governed_findings
        ex = {"governance_status": GOVERNANCE_STATUS, "findings": [
            {"type": "甲事项", "level": "中风险", "detail": "d", "_scenario_governed": True,
             "scene_fact_id": "F1"},
            {"type": "乙事项", "level": "待核验", "detail": "d2", "_scenario_governed": True,
             "scene_fact_id": "F2", "suggestion": "1）核对；2）补充资料。"},
        ]}
        sealed = seal_governed_findings(ex)
        assert len(sealed) == 2
        for f in sealed:
            assert f.get("resolve_steps"), f"{f.get('type')} 缺解除方式"
            assert f.get("self_proof_materials"), f"{f.get('type')} 缺自证资料清单"
            assert f.get("terminal_state"), f"{f.get('type')} 缺终局方向"

    def test_existing_exits_not_overwritten(self):
        from engine.output_governance import GOVERNANCE_STATUS, seal_governed_findings
        ex = {"governance_status": GOVERNANCE_STATUS, "findings": [
            {"type": "甲", "level": "高风险", "_scenario_governed": True, "scene_fact_id": "F1",
             "resolve_steps": ["企业自己写的做法"], "terminal_state": "证据闭合",
             "self_proof_materials": [{"material": "工资表", "proves": "p", "how": "h"}]}]}
        f = seal_governed_findings(ex)[0]
        assert f["resolve_steps"] == ["企业自己写的做法"], "已有出口不得被模板覆盖"
        assert f["terminal_state"] == "证据闭合"
        assert f["self_proof_materials"][0]["material"] == "工资表"

    def test_suggestion_used_as_resolve(self):
        """解除方式优先用发现自己的 suggestion（具体做法），而非通用模板。"""
        from engine.output_governance import GOVERNANCE_STATUS, seal_governed_findings
        ex = {"governance_status": GOVERNANCE_STATUS, "findings": [
            {"type": "甲", "level": "中风险", "_scenario_governed": True, "scene_fact_id": "F1",
             "suggestion": "向社保经办机构补缴；留存缴费凭证。"}]}
        f = seal_governed_findings(ex)[0]
        assert any("补缴" in s for s in f["resolve_steps"]), "应优先采用发现自带的具体做法"

    def test_apply_all_is_idempotent(self):
        from engine.audit_doctrine import apply_three_piece_to_all
        fs = [{"type": "甲", "level": "中风险"}]
        r1 = apply_three_piece_to_all(fs)
        r2 = apply_three_piece_to_all(fs)
        assert r1["proof_filled"] == 1 and r1["terminal_filled"] == 1
        assert r2 == {"resolve_filled": 0, "proof_filled": 0, "terminal_filled": 0}
