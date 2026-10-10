# -*- coding: utf-8 -*-
"""正向（非风险）发现**不得被打上风险/待核等级**（A-P0-3，2026-10-10）。

背景（真产物实测，非设想）：`comprehensive.redline_detection.unmapped[]` 里 5 条
税收优惠/红利发现，**同一行**里 `match_note` 明写「税收优惠/红利类发现，属正向机会提示，
**不作为**税务风险事项配对」，而 `level` 却是「待核验」、`review_level` 是「全面复核」
⇒ 自相矛盾：一边说不是风险事项，一边定级"待核、须全面复核"。

根因链（用 `scripts/_probe_incentive_findings.py` 在红线入口实测抓取，非推测）：
  ① `tax_incentive_analyzer` 产出 `level="优惠机会"` + `tax_benefit`（正确）；
  ② 红线入口**收到了**它们 ⇒ `_map_finding` 正确判 `not_a_risk`、理由正确；
  ③ 但 `text_guardrails.review_finding()` 是**无差别递归归一**，按证据成熟度
     **无条件**把 `level` 改成「待核验」；而 `优惠机会` 不在 `LEGAL_LEVELS` 里
     ⇒ 语义（正向机会）被抹平成"待核风险"。

★ 隔离原则：纯函数级断言，不写库、不写产物。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from engine import risk_levels as RL
from engine import text_guardrails as TG

ROOT = Path(__file__).resolve().parents[1]

_RISK_OR_PENDING = tuple(set(RL.RISK_GRADES) - {"信息"}) + tuple(RL.EVIDENCE_STATES)


def _incentive(level="优惠机会", **extra):
    f = {"type": "小微企业税收优惠（应享）", "domain": "税收优惠机会",
         "level": level, "detail": "符合小微企业标准", "score": None}
    f.update(extra)
    return f


class TestSingleAuthority:
    """判据与词表只有一个出处（`engine/risk_levels.py`）。"""

    def test_non_risk_levels_lives_in_risk_levels(self):
        assert RL.NON_RISK_LEVELS == ("优惠机会", "政策红利", "税收优惠")

    def test_redline_engine_thin_forwards(self):
        from engine import redline_engine as RE
        assert set(RE._NON_RISK_LEVELS) == set(RL.NON_RISK_LEVELS)

    def test_is_non_risk_finding_conditions(self):
        assert RL.is_non_risk_finding({"level": "优惠机会"})
        assert RL.is_non_risk_finding({"tax_benefit": "免征残保金"})
        assert not RL.is_non_risk_finding({"level": "高风险"})
        assert not RL.is_non_risk_finding(None)

    def test_normalize_maps_to_mildest_legal_level(self):
        assert RL.normalize("优惠机会") == "信息"
        assert RL.normalize("政策红利") == "信息"


class TestReviewFindingKeepsNonRiskSemantic:
    def test_incentive_not_flagged_as_pending(self):
        f = _incentive()
        TG.review_finding(f)
        assert f["level"] == "信息", \
            "正向优惠发现被打成 %r ⇒ 与 match_note「不作为风险事项」自相矛盾" % f["level"]
        assert f["level"] not in _RISK_OR_PENDING

    def test_incentive_without_tax_benefit_also_kept(self):
        f = _incentive()                       # 只有 level，没有 tax_benefit
        TG.review_finding(f)
        assert f["level"] == "信息"

    def test_original_semantic_is_recorded(self):
        """归一后必须留下原语义，便于复核"它本来是优惠机会"。"""
        f = _incentive()
        TG.review_finding(f)
        assert f.get("non_risk_semantic") == "优惠机会"

    def test_policy_dividend_level_kept(self):
        f = _incentive(level="政策红利")
        TG.review_finding(f)
        assert f["level"] == "信息"

    @pytest.mark.parametrize("level", ["高风险", "中风险", "低风险", "待核验"])
    def test_ordinary_findings_unaffected(self, level):
        """普通发现**必须**保持既有归一行为（本修复不改变风险档口径）。"""
        f = {"type": "某发现", "level": level, "detail": "d", "score": 0}
        TG.review_finding(f)
        assert f["level"] == "待核验", "证据源为 0 时仍应归一到待核验"

    def test_severity_zero_for_non_risk(self):
        f = _incentive()
        TG.review_finding(f)
        assert RL.severity(f["level"]) == 0      # 「信息」是最轻档


class TestReverseVerification:
    def test_removing_snapshot_breaks_the_fix(self):
        """反向：把「快照」这一步去掉（复刻旧实现）⇒ 修复必须失效（证明判据非假）。"""
        src = (ROOT / "engine" / "text_guardrails.py").read_text(encoding="utf-8")
        assert "_non_risk_snapshot = _is_non_risk_finding(finding)" in src, \
            "快照语句不在 ⇒ 修复可能被改回了「末尾再判」（那时 level 已被覆盖）"
        # 直接复刻旧顺序：先把 level 归一到待核验，再判 is_non_risk_finding
        f = _incentive()
        f["level"] = "待核验"                    # 旧实现覆盖后的状态
        assert not RL.is_non_risk_finding(f), \
            "覆盖后再判仍为真 ⇒ 说明判据依赖的是 tax_benefit 而非 level，本反向用例失效"
        assert RL.is_non_risk_finding(_incentive()), "快照后才判得出来"
