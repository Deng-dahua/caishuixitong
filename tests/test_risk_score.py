# -*- coding: utf-8 -*-
"""风险分值（0-100）回归锁 —— T-2（2026-10-12）。

**为什么要有这组测试**（实测根因）：
用户确认前端有「按严重程度排序/筛选」需求 ⇒ 需 0-100 分值。但 `tax_risk._report_summary`
**已在累加** `r.get("risk_score", 0)`，而该字段**从未被生产者填充** ⇒ 恒取默认 0
（违反「缺失≠0」铁律），且等级词用 `良好`（不在 `LEGAL_LEVELS`）⇒ 第二套等级词。

本组锁住五件事：
  ① **单调**：分值顺序必须与 `risk_levels.severity` 严格一致（方向只有 等级→分值）；
  ② **非风险态不打分**：待核验（证据状态）/ 正向发现 / 词表外 / 空 ⇒ `None`，**不得为 0**；
  ③ **幂等**：不覆盖上游已显式给的分值（只补"缺"不补"错"）；
  ④ **单一权威**：`config/risk_scores.json` 与 `RISK_SCORE_BANDS` 一一对应；
  ⑤ **封印点注入**：`seal_governed_findings` 产出必须带 `risk_score` / `risk_score_status`。

★ 隔离原则：纯函数 + 合成 execution，不落盘、不碰真实库。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

from engine import risk_levels as RL                     # noqa: E402
from engine.output_governance import (GOVERNANCE_STATUS,  # noqa: E402
                                      seal_governed_findings)


class TestMonotone:
    """① 分值必须由等级单调派生。"""

    def test_bands_order_matches_severity(self):
        by_sev = [k for k, _ in sorted(RL.RISK_SCORE_BANDS.items(),
                                       key=lambda kv: -RL.severity(kv[0]))]
        by_score = [k for k, _ in sorted(RL.RISK_SCORE_BANDS.items(),
                                         key=lambda kv: -kv[1])]
        assert by_sev == by_score

    def test_all_bands_within_0_100(self):
        for lv, sc in RL.RISK_SCORE_BANDS.items():
            assert 0 <= sc <= 100, lv

    def test_every_scoring_level_is_a_risk_grade(self):
        for lv in RL.RISK_SCORE_BANDS:
            assert lv in RL.RISK_GRADES, lv


class TestNonRiskNotScored:
    """② 非风险态不得伪造分值（缺失≠0）。"""

    def test_evidence_state_is_none(self):
        for st in RL.EVIDENCE_STATES:
            assert RL.risk_score_of(st) is None
            assert RL.risk_score_status_of(st) == RL.RISK_SCORE_EVIDENCE_STATE

    def test_non_risk_finding_is_none_by_risk_level_key(self):
        """封后发现用 `risk_level`（不是 `level`）—— 必须也能判出正向。"""
        f = {"risk_level": "优惠机会"}
        assert RL.risk_score_of("优惠机会", f) is None
        assert RL.risk_score_status_of("优惠机会", f) == RL.RISK_SCORE_NON_RISK

    def test_non_risk_finding_is_none_by_level_key(self):
        f = {"level": "政策红利"}
        assert RL.risk_score_of("政策红利", f) is None
        assert RL.risk_score_status_of("政策红利", f) == RL.RISK_SCORE_NON_RISK

    def test_non_risk_finding_by_tax_benefit_field(self):
        f = {"risk_level": "信息", "tax_benefit": "可节税 10 万"}
        assert RL.risk_score_of("信息", f) is None

    def test_unregistered_and_empty_are_none(self):
        assert RL.risk_score_of("") is None
        assert RL.risk_score_of("不存在的档") is None
        assert RL.risk_score_status_of("不存在的档") == RL.RISK_SCORE_UNREGISTERED

    def test_no_zero_fallback(self):
        """★ 核心：绝不返回 0 作默认（0 只有上游显式给出时才存在）。"""
        for lv in RL.EVIDENCE_STATES + ("", "未知档"):
            assert RL.risk_score_of(lv) != 0


class TestStampIdempotent:
    """③ 幂等：只补缺，不覆盖。"""

    def test_stamp_fills_missing(self):
        f = {"risk_level": "高风险"}
        RL.stamp_risk_score(f)
        assert f["risk_score"] == RL.RISK_SCORE_BANDS["高风险"]
        assert f["risk_score_status"] == RL.RISK_SCORE_SCORED

    def test_stamp_does_not_overwrite_explicit_value(self):
        f = {"risk_level": "中风险", "risk_score": 0}
        RL.stamp_risk_score(f)
        assert f["risk_score"] == 0, "不得覆盖上游显式给的分值"

    def test_stamp_is_idempotent(self):
        f = {"risk_level": "低风险"}
        RL.stamp_risk_score(f)
        first = dict(f)
        RL.stamp_risk_score(f)
        assert f == first

    def test_stamp_all_handles_mixed(self):
        out = RL.stamp_risk_score_all([{"risk_level": "高风险"}, "x", {"risk_level": "待核验"}])
        assert out[0]["risk_score"] == RL.RISK_SCORE_BANDS["高风险"]
        assert out[1] == "x"
        assert out[2]["risk_score"] is None


class TestConfigSingleSource:
    """④ 单一权威：config 表 + 代码表一一对应。"""

    def test_config_matches_code(self):
        cfg = json.loads((ROOT / "config" / "risk_scores.json").read_text(encoding="utf-8"))
        cfg_bands = {b["level"]: b["score"] for b in cfg["bands"]}
        assert cfg_bands == dict(RL.RISK_SCORE_BANDS)

    def test_config_declares_non_scoring(self):
        cfg = json.loads((ROOT / "config" / "risk_scores.json").read_text(encoding="utf-8"))
        assert "待核验" in cfg["non_scoring"]
        assert cfg["non_scoring"]["待核验"]["score"] is None


class TestInjectionPointIsReportNotSeal:
    """⑤ 注入点断言：分值在**报告产出点**注入，**不在**封印点。

    ★ 实测教训（本任务踩到并纠正）：最初把注入放在 `seal_governed_findings`，
      真跑 E2E 后 **16/16 项零生效** —— 报告发现的链路**不经**封印函数
      （`confirmed_problems` 由 `enterprise_report._build_confirmed_problems` 产出）。
      且即便注入成功，若在「等级上限压制」**之前**，分值会被压制成陈旧值。
      ⇒ 正确注入点是 `build_enterprise_readable_report` 中**编号定稿之后**。
    本类锁住"封印点不得加分值"这一设计事实，防有人又在封印处加一遍造成双源。
    """

    def _seal(self, findings):
        return seal_governed_findings(
            {"governance_status": GOVERNANCE_STATUS, "findings": findings})

    def test_seal_does_not_inject_risk_score(self):
        out = self._seal([
            {"_scenario_governed": True, "scene_fact_id": "S1", "risk_level": "高风险"},
        ])
        assert "risk_score" not in out[0], (
            "封印点不得注入 risk_score（唯一注入点在报告产出点，避免双源）")

    def test_report_builder_is_the_injection_point(self):
        """报告产出点（编号定稿后）必须注入 —— 用真跑产物验证。"""
        p = ROOT / "tests" / "fixtures" / "company_1_full.json"
        assert p.exists(), "测试夹具缺失：%s" % p
        d = json.loads(p.read_text(encoding="utf-8"))
        er = d.get("enterprise_readable_report") or d
        probs = er.get("confirmed_problems") or []
        if not probs:
            pytest.skip("产物无 confirmed_problems")
        assert any("risk_score" in x for x in probs), (
            "报告发现未带 risk_score ⇒ 注入点失效（应注入在等级定稿之后）")
        assert all("risk_score_status" in x for x in probs)


class TestGateReverse:
    """⑥ 反向验证：破坏单调/伪造分值 ⇒ 闸门必须报红（证明判据非假）。"""

    def _gate(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_t_rs_gate", ROOT / "tools" / "audit_consistency.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_gate_green_now(self):
        assert [i for i in self._gate().check_risk_score_monotone()
                if i[0] == "ERROR"] == []

    def test_reverse_non_monotone_is_flagged(self, monkeypatch):
        g = self._gate()
        import engine.risk_levels as rl
        broken = dict(rl.RISK_SCORE_BANDS)
        broken["低风险"] = 99          # 破坏单调（低风险分值最高）
        monkeypatch.setattr(rl, "RISK_SCORE_BANDS", broken, raising=True)
        errs = [i for i in g.check_risk_score_monotone() if i[0] == "ERROR"]
        assert any("单调" in i[2] for i in errs), errs

    def test_reverse_evidence_state_scored_is_flagged(self, monkeypatch):
        g = self._gate()
        import engine.risk_levels as rl
        broken = dict(rl.RISK_SCORE_BANDS)
        broken["待核验"] = 50          # 证据状态不得打分
        monkeypatch.setattr(rl, "RISK_SCORE_BANDS", broken, raising=True)
        errs = [i for i in g.check_risk_score_monotone() if i[0] == "ERROR"]
        assert any("证据状态" in i[2] for i in errs), errs

    def test_reverse_product_level_score_mismatch_is_flagged(self, monkeypatch):
        """★ 端到端产出断言的反向验证：产物里**等级与分值矛盾** ⇒ 必须报红。

        实测事故：分值若在「等级上限压制」**之前**派生，会被压制成陈旧值
        （`红字冲销…` 等级由「高风险」压到「低风险」，分值却留 80）。只看表抓不到。
        """
        g = self._gate()
        fake = {"enterprise_readable_report": {"confirmed_problems": [
            {"title": "红字冲销与作废发票比例异常", "risk_level": "低风险", "risk_score": 80},
        ]}}
        monkeypatch.setattr(g, "_canonical_report", lambda: fake, raising=True)
        errs = [i for i in g.check_risk_score_monotone() if i[0] == "ERROR"]
        assert any("与等级矛盾" in i[2] for i in errs), errs

    def test_product_consistent_when_level_matches(self, monkeypatch):
        """正例：等级与分值一致时不得报红。"""
        g = self._gate()
        fake = {"enterprise_readable_report": {"confirmed_problems": [
            {"title": "x", "risk_level": "低风险", "risk_score": 40},
            {"title": "y", "risk_level": "待核验", "risk_score": None},
        ]}}
        monkeypatch.setattr(g, "_canonical_report", lambda: fake, raising=True)
        errs = [i for i in g.check_risk_score_monotone() if i[0] == "ERROR"]
        assert errs == [], errs

    def test_real_product_is_consistent(self):
        """真跑产物（若存在）必须等级↔分值一致。"""
        p = ROOT / "tests" / "fixtures" / "company_1_full.json"
        assert p.exists(), "测试夹具缺失：%s" % p
        d = json.loads(p.read_text(encoding="utf-8"))
        er = d.get("enterprise_readable_report") or d
        for it in (er.get("confirmed_problems") or []):
            lv = str(it.get("risk_level") or "").strip()
            sc, expect = it.get("risk_score"), RL.RISK_SCORE_BANDS.get(lv)
            if sc is not None and expect is not None:
                assert int(sc) == int(expect), (it.get("title"), lv, sc, expect)
            if lv in RL.EVIDENCE_STATES:
                assert sc is None, ("证据状态不得有分值", it.get("title"))
                assert it.get("risk_score_status") == RL.RISK_SCORE_EVIDENCE_STATE
