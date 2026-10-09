# -*- coding: utf-8 -*-
"""WB-TRISK-2026-001 四道质量门禁 —— 回归测试。

基准样本 = 《深圳海更数字传媒有限公司税务风险扫描工作底稿》（夹具见
`tests/fixtures/wb_trisk_001_baseline.json`，由 `scripts/_make_bench_fixture.py` 从
`data/cache/last_analysis_cache.json` 抽取，只保留门禁判据所需字段）。

用例分类（marker 口径见 tests/conftest.py）：
  · plain   正例：缺陷在 ⇒ 必须报红
  · reverse 反向验证：把缺陷修好 ⇒ 该判据必须转绿（防「永远报红」的假闸门）
  · lock    口径锁：不变量，不得报错
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from engine import conclusion_grade as cg
from engine import fact_store as fs
from engine import numbering as nb
from engine import quality_gates as qg
from engine import report_metrics as rm

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "wb_trisk_001_baseline.json"
COMPANY_CODE = "91440300MA5H824G7M"
PERIOD = "202601"


@pytest.fixture(scope="module")
def report() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["report"]


@pytest.fixture()
def fresh(report: dict) -> dict:
    return copy.deepcopy(report)


def _checks(res: dict, gate: str | None = None) -> set[str]:
    out: set[str] = set()
    for g in res["gates"]:
        if gate and g["gate"] != gate:
            continue
        out |= {f"{g['gate']}-{f['check_id']}" for f in g["findings"] if f["severity"] == "ERROR"}
    return out


def _run(r: dict, **kw) -> set[str]:
    return _checks(qg.run_all_gates(r, company_code=COMPANY_CODE, period=PERIOD, **kw))


def _items(r: dict) -> list[dict]:
    return r["enterprise_readable_report"]["confirmed_problems"]


# ================================================================ 门禁 A
class TestGateEvidenceClosure:
    @pytest.mark.plain
    def test_a1_zero_evidence_must_not_carry_mid_or_high(self, fresh):
        """A1：closure=0 / evidence_have=0 却带 中风险及以上 ⇒ 报红。"""
        assert "A-A1" in _run(fresh)

    @pytest.mark.plain
    def test_a9_unclosed_must_not_carry_mid_or_high(self, fresh):
        """A9：closure 已登记但 < 0.8 却带 中风险及以上 ⇒ 报红。"""
        assert "A-A9" in _run(fresh)

    @pytest.mark.plain
    def test_a3_determinative_words_with_missing_evidence(self, fresh):
        """A3：关键证据缺失时仍出现定性词 ⇒ 报红。"""
        assert "A-A3" in _run(fresh)

    @pytest.mark.plain
    def test_a4_conclusion_grade_required(self, fresh):
        """A4：未登记 conclusion_grade ⇒ 报红。"""
        assert "A-A4" in _run(fresh)
        missing = [it["seq"] for it in _items(fresh) if not str(it.get("conclusion_grade") or "").strip()]
        assert missing, "基准样本应存在未登记结论等级的项（否则本用例无效）"

    @pytest.mark.reverse
    def test_a1_a9_green_after_downgrade(self, fresh):
        """反向验证：把无证据/未闭合项降为『待核验』⇒ A1/A9 必须转绿。"""
        for it in _items(fresh):
            h, c = it.get("evidence_have"), it.get("closure")
            if (h is None) or (h == 0) or (c is None) or (float(c) < cg.min_closure()):
                it["risk_level"] = "待核验"
        got = _run(fresh)
        assert "A-A1" not in got and "A-A9" not in got

    @pytest.mark.reverse
    def test_a4_green_after_filling_grade(self, fresh):
        for it in _items(fresh):
            if not str(it.get("conclusion_grade") or "").strip():
                it["conclusion_grade"] = cg.GRADE_L2
        assert "A-A4" not in _run(fresh)


# ================================================================ 门禁 B
class TestGateLogicConsistency:
    @pytest.mark.plain
    def test_b2_numbering_gap(self, fresh):
        """B2：编号跳号（缺 八/十/十二/十六/十七）⇒ 报红。"""
        assert "B-B2" in _run(fresh)
        orders = [_cn_to_int(it.get("办理顺序")) for it in _items(fresh)]
        nums = sorted(n for n in orders if n)
        assert nums and [n for n in range(1, max(nums) + 1) if n not in nums], "样本应存在缺号"

    @pytest.mark.plain
    def test_b6_declared_count_must_equal_actual(self, fresh):
        """B6：total_risks/high_risk/mid_risk/low_risk 等声明计数必须等于实际盘点。"""
        assert "B-B6" in _run(fresh)
        assert fresh["total_risks"] != len(_items(fresh)), "样本的 total_risks 应与实际项数不符"

    @pytest.mark.plain
    def test_b5_contradictory_conclusion(self, fresh):
        """B5：同一事项并存『未认定』与『已查明』⇒ 报红。"""
        assert "B-B5" in _run(fresh)

    @pytest.mark.plain
    def test_b9_closure_self_consistency(self, fresh):
        """B9：closure 必须等于 round(have/need, 2)。"""
        assert "B-B9" in _run(fresh)

    @pytest.mark.plain
    def test_b7_opposite_assertions_across_sections(self, fresh):
        """B7：同一事实在不同章节表述相反 ⇒ 报红。

        ★ 缺陷**显式注入**（不再依赖标本恰好含相反断言）：
          扫描域 = `report_surface`（＝`output_variants.report_text_from` 投影正文），
          报告链修复后标本可能不再含矛盾对，靠标本会**假绿**（实测 2026-10-09）。
        """
        items = _items(fresh)
        items[0]["premise_note"] = "资产总额已取得并核对无误。"
        items[-1]["premise_note"] = "资产总额未取得，无法核对。"
        assert "B-B7" in _run(fresh)
        pairs = qg._contradiction_pairs(fresh)
        assert pairs and any(p["object"] in ("资产总额", "从业人数") for p in pairs)

    @pytest.mark.reverse
    def test_b2_green_after_renumber(self, fresh):
        for i, it in enumerate(_items(fresh), 1):
            it["办理顺序"] = _int_to_cn(i)
        assert "B-B2" not in _run(fresh)

    @pytest.mark.reverse
    def test_b6_green_after_recount(self, fresh):
        from collections import Counter
        cnt = Counter(cg.normalize_level(it.get("risk_level"))[0] for it in _items(fresh))
        n = len(_items(fresh))
        fresh["total_risks"] = n
        fresh["high_risk"] = cnt.get("高风险", 0)
        fresh["mid_risk"] = cnt.get("中风险", 0)
        fresh["low_risk"] = cnt.get("低风险", 0)
        fresh["overall_level"] = rm.conclusion_count_phrase(0, n)
        led = fresh["enterprise_readable_report"].get("resolution_ledger") or {}
        for k in ("total", "ironclad", "self_provable", "pending", "with_resolve", "with_self_proof"):
            if k in led:
                led[k] = n
        assert "B-B6" not in _run(fresh)


# ================================================================ 门禁 C
class TestGateArchiveSpec:
    @pytest.mark.plain
    def test_c_archive_gaps(self, fresh):
        """C1/C2/C5/C7/C8：无底稿号、无风险号、缺索引、签署不全、无审计轨迹 ⇒ 报红。

        ★ 缺陷**显式注入**（不再依赖标本恰好缺项）：报告链已在真实产物中补齐「审批人」
          签署栏（`config/archive_spec.json#signature_block.roles`），原「依赖标本缺审批人」
          的断言随即**假绿**（实测 2026-10-09）。判据语义（角色齐备即通过；是否实际签署
          由 `signed` 字段单独表达）见 `test_c_green_after_archive_completion`。
        """
        fresh.pop("workpaper_no", None)
        err = fresh["enterprise_readable_report"]
        err.pop("workpaper_no", None)
        err.pop("indexes", None)
        err.pop("audit_trail", None)
        fresh.pop("audit_trail", None)
        err["signature_block"] = {"rows": [{"role": "编制人", "name": "待签"}], "signed": False}
        got = _checks(qg.run_all_gates(fresh, company_code=COMPANY_CODE, period=PERIOD), "C")
        for cid in ("C-C1", "C-C2", "C-C5", "C-C7", "C-C8"):
            assert cid in got, f"{cid} 未报红"

    @pytest.mark.reverse
    def test_c_green_after_archive_completion(self, fresh):
        svc = nb.NumberingService(COMPANY_CODE, PERIOD)
        fresh["workpaper_no"] = svc.workpaper_no(1)
        for it in _items(fresh):
            it.setdefault("risk_no", svc.next("risk"))
        err = fresh["enterprise_readable_report"]
        err["indexes"] = {k: [] for k in ("risk", "evidence", "gap", "law", "amount", "attachment", "rectify")}
        err["signature_block"] = {"编制人": "待签", "复核人": "待签", "审批人": "待签"}
        err["audit_trail"] = [{"at": "2026-10-08T00:00:00", "operator": "system", "action": "生成",
                               "target": "报告", "before": "", "after": "", "reason": "首轮"}]
        got = _checks(qg.run_all_gates(fresh, company_code=COMPANY_CODE, period=PERIOD), "C")
        for cid in ("C-C1", "C-C2", "C-C5", "C-C7", "C-C8"):
            assert cid not in got, f"{cid} 修好后仍报红（假闸门）"


# ================================================================ 门禁 D
def _d(render_text: str = "") -> set[str]:
    r = qg.gate_template_hygiene({"enterprise_readable_report": {}}, render_text=render_text)
    return {f"{r.gate}-{f.check_id}" for f in r.errors}


DUP_A = "完全相同的一段超过二十五个字的模板文字用于触发重复度判据。"
DUP_B = "完全不同的一段超过二十五个字的模板文字用于对照重复度判据。"


class TestGateTemplateHygiene:
    @pytest.mark.plain
    @pytest.mark.parametrize("text,expect", [
        ("说明2。要把这一项查清楚，需要：", "D-D2"),
        ("**尚未完成签署**：编制人、复核人、审批人。", "D-D4"),
        ("点击展开 下载 CSV http://127.0.0.1:8001", "D-D1"),
        ("|  |  |\n|  |  |\n|  |  |", "D-D9"),
        ("模板变量未替换：{企业名称}", "D-D3"),
    ])
    def test_render_layer_checks_fire(self, text, expect):
        assert expect in _d(text)

    @pytest.mark.plain
    def test_duplicate_paragraphs_fire(self):
        assert "D-D5" in _d("\n".join([DUP_A] * 5 + [DUP_B] * 5))

    @pytest.mark.reverse
    @pytest.mark.parametrize("bad,good,check", [
        ("说明2。要把这一项查清楚，需要：", "说明2。要把这一项查清楚，需要提供：合同、发票、流水。", "D-D2"),
        ("**尚未完成签署**：编制人。", "尚未完成签署：编制人。", "D-D4"),
        ("点击展开 下载 CSV localhost:8001", "详见附件明细。", "D-D1"),
        ("|  |  |\n|  |  |\n|  |  |", "| 供应商 | 金额 |\n| 甲 | 100.00 |", "D-D9"),
        ("未替换：{企业名称}", "企业名称：甲公司", "D-D3"),
    ])
    def test_render_layer_reverse(self, bad, good, check):
        assert check in _d(bad), "有缺陷未报红"
        assert check not in _d(good), "无缺陷却报红（假阳性）"

    @pytest.mark.reverse
    def test_duplicate_reverse(self):
        uniq = "\n".join([f"{DUP_A[:-1]}{i}。" for i in range(5)] + [f"{DUP_B[:-1]}{i}。" for i in range(5)])
        assert "D-D5" not in _d(uniq)

    @pytest.mark.lock
    def test_scan_domain_excludes_non_report_text(self):
        """口径锁：扫描域必须白名单化 —— 上传的 HTML/JS 不得被当报告正文。"""
        payload = {"file_results": [{"content": '<script>var __x={a:1}</script>'}],
                   "quality_report": {"warnings": ["疑似复制粘贴"]},
                   "enterprise_readable_report": {"confirmed_problems": []}}
        sur = qg.report_surface(payload)
        blob = "\n".join(sur["texts"])
        assert "__x" not in blob and "<script>" not in blob and "复制粘贴" not in blob

    @pytest.mark.lock
    def test_no_silent_truncation(self):
        """口径锁：超过 max_chars 必须留痕（不得静默截断）。"""
        big = {"enterprise_readable_report": {"x": "字" * 10}}
        assert qg.iter_texts(big, char_limit=3)[-1].startswith("<<TRUNCATED")


# ================================================================ 事实库
class TestFactStore:
    @pytest.mark.plain
    def test_same_key_different_value_conflicts(self):
        st = fs.FactStore(period="202601")
        st.declare(kind=fs.KIND_AMOUNT, label="未匹配到任何支付渠道的金额", value="13,432.48")
        st.declare(kind=fs.KIND_AMOUNT, label="未匹配到任何支付渠道的金额", value="1,498,692.68")
        conf = st.conflicts()
        assert conf and len(conf[0].facts) >= 2, "同键不同值必须判冲突（含被覆盖的历史值）"

    @pytest.mark.plain
    def test_idempotent_declare(self):
        st = fs.FactStore()
        a = st.declare(kind=fs.KIND_AMOUNT, label="收入", value="100.00")
        b = st.declare(kind=fs.KIND_AMOUNT, label="收入", value="100.00")
        assert a == b and not st.conflicts()

    @pytest.mark.lock
    def test_declared_scope_group_not_conflict(self):
        """口径锁：已声明口径分组的多值是**合法**的（全口径 vs 剔除口径），不得判冲突。"""
        st = fs.FactStore()
        st.declare(kind=fs.KIND_AMOUNT, label="银行差异", value="1,734,859.35",
                   scope=fs.SCOPE_FULL, related="BANKSET", scope_note="全口径")
        st.declare(kind=fs.KIND_AMOUNT, label="银行差异", value="227,659.35",
                   scope=fs.SCOPE_ADJUSTED, related="BANKSET", scope_note="剔除后")
        assert not st.conflicts()

    @pytest.mark.lock
    def test_unparsable_value_is_none_not_zero(self):
        """口径锁：解析失败 ⇒ None，绝不默认 0（本项目铁律「缺失≠0」）。"""
        st = fs.FactStore()
        fid = st.declare(kind=fs.KIND_AMOUNT, label="测试", value="无法解析")
        assert st.value_of(fid) is None and st.errors

    @pytest.mark.plain
    def test_render_unregistered_is_reported(self):
        st = fs.FactStore()
        assert st.render("F-AMT-NA-XXXX") == "" and st.errors


# ================================================================ 编号服务
class TestNumbering:
    @pytest.mark.plain
    def test_make_and_parse_roundtrip(self):
        svc = nb.NumberingService(COMPANY_CODE, PERIOD)
        no = svc.make("risk", 7)
        assert no == f"WB-R-{COMPANY_CODE}-{PERIOD}-007"
        assert svc.parse(no)["seq"] == 7

    @pytest.mark.plain
    def test_law_number_excludes_company(self):
        svc = nb.NumberingService(COMPANY_CODE, PERIOD)
        assert svc.make("law", 3, tax_code="VAT") == "WB-LAW-VAT-003"

    @pytest.mark.plain
    @pytest.mark.parametrize("seqs,expect_code", [
        ([1, 2, 4], "GAP"),
        ([1, 1, 2], "DUPLICATE"),
        ([2, 3, 4], "BAD_START"),
        ([1, 2, 3], "MAX_MISMATCH"),
    ])
    def test_continuity_issues(self, seqs, expect_code):
        codes = {i.code for i in nb.validate_continuity(seqs, total=4, label="测试")}
        assert expect_code in codes

    @pytest.mark.plain
    def test_missing_number_detected(self):
        codes = {i.code for i in nb.validate_continuity([1, None, 3], total=3, label="测试")}
        assert "MISSING_NUMBER" in codes

    @pytest.mark.lock
    def test_clean_sequence_has_no_issue(self):
        assert not nb.validate_continuity([1, 2, 3], total=3, label="测试")

    @pytest.mark.plain
    def test_cn_numeral_parse(self):
        svc = nb.NumberingService(COMPANY_CODE, PERIOD)
        assert svc.seq_of("十八") is None, "中文数字不由编号服务负责（应由调用方转换）"


# ================================================================ 结论分级
class TestConclusionGrade:
    @pytest.mark.plain
    @pytest.mark.parametrize("verdict,expect", [
        ("已触碰税务违规红线（资料齐全，可作初步判断）", "L3"),
        ("疑似触碰税务违规红线（资料不足，待补充资料后判断）", "L2"),
        ("经核查未触碰违规红线（已有合理解释）", "L2"),
        ("现有资料不足以形成税务疑点", "L1"),
        ("本项已查明的风险；未认定到构成要件（认定范围见本项说明）", "L2"),
    ])
    def test_map_verdict(self, verdict, expect):
        gid, registered = cg.map_verdict(verdict)
        assert gid == expect and registered

    @pytest.mark.plain
    def test_veto_triggers_on_zero_evidence(self):
        hits = {h["id"] for h in cg.veto_triggers({"closure": 0.0, "evidence_have": 0, "evidence_need": 3,
                                                   "conclusion_grade": "待核"})}
        assert "V1" in hits

    @pytest.mark.plain
    def test_apply_veto_caps_level_and_grade(self):
        out = cg.apply_veto({"risk_level": "高风险", "closure": 0.0, "evidence_have": 0,
                             "evidence_need": 3, "verdict": "本项已查明的风险", "conclusion_grade": "待核"})
        assert out["risk_level"] == "待核验"
        assert out["conclusion_grade"] == cg.GRADE_L2
        assert out["_veto_applied"] is True
        assert "关键证据缺失" in out["verdict"]

    @pytest.mark.lock
    def test_level_vocab_matches_authority(self):
        """口径锁：config 等级词表必须与 engine/risk_levels.LEGAL_LEVELS 逐字一致。"""
        assert not cg.vocab_consistency()

    @pytest.mark.lock
    def test_verdict_vocab_complete(self):
        """口径锁：argumentation 的裁决词常量必须全部登记到 verdict_mapping。"""
        assert not cg.verdict_vocab_consistency()

    @pytest.mark.lock
    def test_veto_triggers_all_implemented(self):
        assert not cg.veto_trigger_coverage()


# ================================================================ 注册与契约
class TestGateRegistrationAndHealth:
    @pytest.mark.lock
    def test_config_loads_without_error(self):
        assert not qg.load_errors() and not cg.load_errors() and not nb.load_errors()

    @pytest.mark.lock
    def test_four_gates_registered(self):
        ids = [g["id"] for g in qg.load_spec()["gates"]]
        assert ids == ["A", "B", "C", "D"]

    @pytest.mark.lock
    def test_every_check_id_has_entry_point(self):
        """口径锁：判据表里每条判据都必须能在实现里找到报出点（防止「表里有、代码没做」）。"""
        src = (Path(qg.__file__)).read_text(encoding="utf-8")
        for g in qg.load_spec()["gates"]:
            for c in g["checks"]:
                assert c["id"] in src, f"{c['id']} 在实现中找不到（判据表与代码脱节）"

    @pytest.mark.lock
    def test_skip_is_not_pass(self):
        """口径锁：SKIP 不计通过（policy.skip_is_not_pass）。"""
        r = qg.GateResult("A", "x", "y", status="SKIP")
        assert r.passed is False

    @pytest.mark.plain
    def test_all_gates_fail_on_benchmark(self, fresh):
        """基准样本必须被四道门禁全部拦下（正式底稿不得生成）。"""
        res = qg.run_all_gates(fresh, company_code=COMPANY_CODE, period=PERIOD)
        assert res["all_passed"] is False
        assert res["formal_output_allowed"] is False
        assert set(res["summary"]["failed_gates"]) == {"A", "B", "C", "D"}

    @pytest.mark.lock
    def test_gate_report_renders(self, fresh):
        res = qg.run_all_gates(fresh, company_code=COMPANY_CODE, period=PERIOD)
        md = qg.render_gate_report(res)
        assert "# 质量门禁报告" in md and "门禁A" in md and "修复建议" in md


# ================================================================ P1-2 可信度可复算
class TestConfidenceRecomputability:
    """契约（2026-10-09，P1-2）：**可信度百分比必须可复算**。

    背景：正文「判断可信度约X%」/ 条目 `confidence` / 分项明细 `confidence_breakdown`
    三方曾各说各话（实测真实产物 16 条中 8 条不一致），且前端「可能性档位」（读
    `item.confidence`）与正文叙事会给出**不同档位**。修法：分项明细为唯一账本
    （区间截断与"触碰红线不低于 60%"均登记为显式分项），`confidence=round(Σ贡献,2)`，
    百分比由 `confidence_percent()` 唯一算法产出。D11 门禁对同一判据做端到端断言。
    """

    @staticmethod
    def _arg(**kw):
        from engine.argumentation import build_argumentation
        f = {"type": "T", "level": kw.get("level", "高风险"), "detail": "d"}
        clue_nodes = kw.get("nodes", [{"step": 1, "source": "凭证", "has_data": True, "observed": "x"}])
        return build_argumentation(
            f, {"id": "RL-X", "name": "n", "suspect": "s", "constituents": ["c1"],
                "legal_basis": ["《税收征收管理法》第三十五条"]},
            {"nodes": clue_nodes, "terminal_signal": kw.get("signal", "sig")},
            {"closure": kw.get("closure", 0.5), "elements": []}, [])

    @pytest.mark.lock
    def test_confidence_equals_sum_of_parts(self):
        """口径锁：confidence 必须恒等于 round(Σ分项贡献, 2)（可复算）。"""
        from engine.argumentation import confidence_from_breakdown
        for kw in ({"closure": 0.0, "level": "中风险", "nodes": []},          # 触发 60% 地板
                   {"closure": 1.0, "level": "高风险"},                        # 触发 95% 封顶
                   {"closure": 0.5, "level": "低风险"},
                   {"closure": 0.0, "level": "中风险", "signal": ""}):         # 不触红线
            a = self._arg(**kw)
            assert confidence_from_breakdown(a["confidence_breakdown"]) == round(float(a["confidence"]), 2), kw

    @pytest.mark.lock
    def test_floor_registered_as_explicit_part(self):
        """口径锁：60% 地板不得"隐式改数值" —— 必须落成一条显式分项。"""
        from engine.argumentation import confidence_from_breakdown
        a = self._arg(closure=0.0, level="中风险", nodes=[])
        names = [p.get("项", "") for p in a["confidence_breakdown"]]
        assert any("补足" in n for n in names), names
        assert confidence_from_breakdown(a["confidence_breakdown"]) == 0.60

    @pytest.mark.lock
    def test_reasoning_percent_matches_breakdown(self):
        """口径锁：正文百分比必须由分项复算得出（同源）。"""
        import re
        from engine.argumentation import confidence_from_breakdown, confidence_percent
        for kw in ({"closure": 0.0, "level": "中风险", "nodes": []}, {"closure": 0.5}):
            a = self._arg(**kw)
            m = re.search(r"判断可信度约\s*(\d+)\s*%", a["reasoning"])
            assert m, a["reasoning"][-80:]
            assert int(m.group(1)) == confidence_percent(confidence_from_breakdown(a["confidence_breakdown"]))

    @pytest.mark.plain
    def test_gate_d11_fires_on_inconsistent_confidence(self):
        from engine.argumentation import confidence_formula_text
        from engine.report_pipeline import REPORT_LEVEL_REF
        a = self._arg()
        pct = a["confidence"]
        item = {"seq": 1, "title": "T", "confidence": round(float(a["confidence"]) + 0.08, 2),
                "confidence_breakdown": a["confidence_breakdown"],
                "confidence_formula": REPORT_LEVEL_REF,
                "narrative_paragraphs": [{"text": f"结论X，判断可信度约{int(round(pct * 100))}%。"}]}
        r = qg.gate_template_hygiene({"confirmed_problems": [item],
                                      "report_statement": [confidence_formula_text()]})
        assert any(f.check_id == "D11" for f in r.errors), [f.check_id for f in r.errors]

    @pytest.mark.plain
    def test_gate_d11_fires_when_formula_missing(self):
        from engine.report_pipeline import REPORT_LEVEL_REF
        a = self._arg()
        item = {"seq": 1, "title": "T", "confidence": a["confidence"],
                "confidence_breakdown": a["confidence_breakdown"],
                "confidence_formula": REPORT_LEVEL_REF,
                "narrative_paragraphs": [{"text": "结论X，判断可信度约68%。"}]}
        r = qg.gate_template_hygiene({"confirmed_problems": [item],
                                      "report_statement": ["与可信度无关的说明。"]})
        assert any(f.check_id == "D11" for f in r.errors), [f.check_id for f in r.errors]

    @pytest.mark.reverse
    def test_gate_d11_green_on_consistent_report(self):
        from engine.argumentation import confidence_formula_text
        from engine.report_pipeline import REPORT_LEVEL_REF
        a = self._arg()
        pct = a["confidence"]
        item = {"seq": 1, "title": "T", "confidence": a["confidence"],
                "confidence_breakdown": a["confidence_breakdown"],
                "confidence_formula": REPORT_LEVEL_REF,
                "narrative_paragraphs": [{"text": f"结论X，判断可信度约{int(round(pct * 100))}%。"}]}
        r = qg.gate_template_hygiene({"confirmed_problems": [item],
                                      "report_statement": [confidence_formula_text()]})
        assert not any(f.check_id == "D11" for f in r.errors), "无缺陷却报红（假阳性）"

    @pytest.mark.lock
    def test_formula_text_single_source(self):
        """口径锁：公式文本唯一权威 —— 权重取自 CONFIDENCE_WEIGHTS，锚点可匹配。"""
        from engine.argumentation import (CONFIDENCE_FORMULA_ANCHOR, CONFIDENCE_WEIGHTS,
                                          confidence_formula_text)
        txt = confidence_formula_text()
        assert CONFIDENCE_FORMULA_ANCHOR.search(txt)
        assert f"{CONFIDENCE_WEIGHTS['base']:.2f}" in txt
        assert f"{abs(CONFIDENCE_WEIGHTS['closure']):.2f}" in txt

    @pytest.mark.lock
    def test_breakdown_missing_is_not_recomputable(self):
        """口径锁：缺失/非法分项必须判"不可复算"（否则判据是假的）。"""
        from engine.argumentation import confidence_from_breakdown
        assert confidence_from_breakdown([]) is None
        assert confidence_from_breakdown(None) is None
        assert confidence_from_breakdown([{"项": "x", "贡献": "bad"}]) is None


# ---------------------------------------------------------------- 辅助
_CN = {"〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _cn_to_int(s) -> int | None:
    t = str(s or "").strip()
    if not t:
        return None
    if t.isdigit():
        return int(t)
    if t == "十":
        return 10
    if "十" in t:
        a, _, b = t.partition("十")
        da = _CN.get(a) if a else 1
        db = _CN.get(b) if b else 0
        return None if da is None or db is None else da * 10 + db
    return _CN.get(t)


# ================================================================ P1-3 必要重复口径单一入口
class TestNecessaryRepeatSingleEntry:
    """「必要重复/不计冗余」只许有一个判定入口（防"同一概念多处各判一次"复发）。

    根因（2026-10-09 实测）：同一概念曾有三处口径 ——
    `dedup_pipeline.is_necessary`（服务重复率四项判据）、
    `common_clauses` 登记表（只服务跨章节模板句）、
    `report_pipeline.non_dedupable_values`（只服务 D5）
    ⇒ 同一句在某判据被豁免、在另一判据被计冗余，闸门互相假红。
    """

    @pytest.mark.lock
    def test_registered_clause_is_necessary(self):
        """登记表里的口径：`is_necessary()` 必须认得（即豁免口径已收敛到单一入口）。"""
        from engine.common_clauses import load_registry
        from engine.dedup_pipeline import is_necessary
        reg = load_registry()
        entries = [c for c in (reg.get("hoist") or []) + (reg.get("necessary") or [])
                   if isinstance(c, dict)]
        assert entries, "登记表为空，判据无从验证"
        for c in entries:
            for pat in (c.get("match") or []):
                rx = re.compile(pat)
                # 用正则自身可匹配的最小样本（把 ^ 锚点后的字面量取出）
                literal = re.sub(r"[\\^$.|?*+()\[\]{}]", "", pat).split("\\")[0]
                if literal and rx.search(literal):
                    assert is_necessary(literal), (
                        "登记项 %s 的样本 %r 未被 is_necessary 豁免 ⇒ 豁免口径未收敛"
                        % (c.get("id"), literal))

    @pytest.mark.lock
    def test_necessary_sources_not_empty(self):
        """判定来源清单必须非空（取不到登记表即无法豁免 ⇒ 会静默虚报重复）。"""
        from engine.dedup_pipeline import _necessary_sources
        assert _necessary_sources(), "必要重复来源为空：登记表未接通"

    @pytest.mark.reverse
    def test_multi_sentence_block_not_wholly_exempted(self):
        """反向验证：以登记口径**开头**但含本项特有内容的多句段，不得整体豁免。"""
        from engine.dedup_pipeline import is_necessary
        mixed = ("综合以上，本项结论是疑似触碰税务违规红线。"
                 "本项涉及金额 1,234,567.89 元，属 R7 独有的核算口径。")
        assert not is_necessary(mixed), "多句段落被整体豁免 ⇒ 真冗余会被藏住"


# ================================================================ 工具函数
def _int_to_cn(i: int) -> str:
    d = "〇一二三四五六七八九"
    if i <= 10:
        return "十" if i == 10 else d[i]
    if i < 20:
        return "十" + d[i - 10]
    return d[i // 10] + "十" + (d[i % 10] if i % 10 else "")
