# -*- coding: utf-8 -*-
"""红线**归属声明**回归（A-P0-1，2026-10-10）。

背景（实测真产物，非设想）：`company_1_full.json` 的 26 条嫌疑里 3 条 `match_mode="matched"`
（关键词兜底）。其中 `RL-AST-001`「固定资产取得、投用与折旧不匹配」的**事实已经算出来了**
—— `_domain_depreciation_match` 产出「银行流水发现2笔固定资产类付款，合计20,000.00元。
应相应计提折旧。」—— 但该 finding **没声明 `redline_id`** ⇒ 引擎只能拿标题里的
"固定资产/折旧"两个字去猜归属（`match_reasons=["hint@title","hint@title"]`）。

本组锁住四件事（数据驱动：新增一处 = 在 `config/redline_detector_attribution.json` 加一行）：
  ① 登记表里的每个检测器**真的**产出了带 `redline_id` 的 finding（不是嘴上声明）；
  ② 声明的红线 id 在红线库里；
  ③ 检出**不能被静默低估**：声明后该红线必须落在覆盖率权威的 `has_detector`、不在 `only_fallback`；
  ④ 只声明"归属"、**不认领构成要件**（`constituent_hits` 仍由谁真算过谁声明）。

★ 隔离原则：只做**内存内**的检测器调用与**只读**文件断言，不碰真实库、不写真实产物。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONF = ROOT / "config" / "redline_detector_attribution.json"
COV = ROOT / "scripts" / "_redline_coverage.json"


def _declarations():
    return json.loads(CONF.read_text(encoding="utf-8"))["declarations"]


def _redline_ids():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_rl_ids", ROOT / "engine" / "tax_redlines.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {str(r["id"]) for r in mod.REDLINES}


@pytest.fixture(scope="module")
def coverage():
    if not COV.exists():
        pytest.skip("覆盖率产物不存在（先跑 scripts/_audit_redline_coverage.py）")
    return json.loads(COV.read_text(encoding="utf-8"))


class TestRegistryShape:
    def test_registry_readable_and_non_empty(self):
        rows = _declarations()
        assert rows, "登记表为空 —— 判据等于没跑"
        for r in rows:
            assert r.get("detector_file") and r.get("redline_id")

    def test_detector_file_is_production_code(self):
        """`scripts/` 下的一次性脚本运行期不执行、覆盖率审计也不计入 ⇒ 登记在那里等于没登记。"""
        for r in _declarations():
            f = ROOT / r["detector_file"]
            assert f.exists(), r["detector_file"]
            assert f.parent.name == "engine" or f.name == "main.py", \
                "归属声明必须落在生产代码：%s" % r["detector_file"]

    def test_redline_id_exists(self):
        ids = _redline_ids()
        for r in _declarations():
            assert r["redline_id"] in ids, r


class TestDeclarationIsReal:
    """① 不是"嘴上声明"——把检测器**跑一遍**，看它产出的 finding 真的带 redline_id。"""

    def test_domain_depreciation_declares_ast_001(self):
        from engine import domain_analysis as DA
        bank = [{"summary": "购服务器", "counterparty": "某科技", "debit": 12000.0},
                {"summary": "购设备", "counterparty": "某机电", "debit": 8000.0},
                {"summary": "办公用品", "counterparty": "某商行", "debit": 300.0}]
        out = DA._domain_depreciation_match(bank, [])
        hits = [f for f in out if f.get("type") == "固定资产采购与折旧匹配提示"]
        assert hits, "检测器没产出固定资产提示（样本数据未被识别）"
        for f in hits:
            assert f.get("redline_id") == "RL-AST-001", \
                "检测器已算出事实却没声明归属 ⇒ 引擎只能按关键词猜（match_mode=matched）"

    def test_domain_depreciation_does_not_claim_constituents(self):
        """② 只声明归属、不认领要件：本检测器算不出"是否已计提折旧"，故不得写 constituent_hits。"""
        from engine import domain_analysis as DA
        out = DA._domain_depreciation_match(
            [{"summary": "购设备", "counterparty": "某机电", "debit": 9000.0}], [])
        for f in out:
            assert not f.get("constituent_hits"), \
                "本检测器只算出「有固定资产类付款」，算不出「是否已计提折旧」⇒ 不得认领构成要件"

    def test_missing_data_finding_does_not_declare_redline(self):
        """资料缺失类 finding 不是风险命中，不得借机认领红线。"""
        from engine import domain_analysis as DA
        out = DA._domain_depreciation_match([], [])
        assert out, "无银行流水时应有资料缺失提示"
        for f in out:
            assert not f.get("redline_id"), "资料缺失提示不得声明红线归属"


class TestCoverageNotUnderestimated:
    """③ 检出能力不得被静默低估：声明 ⇒ 覆盖率权威必须认它为「有真实检测器」。"""

    def test_declared_redline_in_has_detector(self, coverage):
        for r in _declarations():
            rid = r["redline_id"]
            assert rid in coverage["has_detector"], \
                "%s 已声明归属，覆盖率权威仍未认作有检测器" % rid

    def test_declared_redline_not_in_only_fallback(self, coverage):
        for r in _declarations():
            assert r["redline_id"] not in coverage["only_fallback"], \
                "%s 仍被记为「仅兜底」" % r["redline_id"]

    def test_coverage_artifact_not_stale(self):
        """产物比源文件旧 ⇒ D 段结论不可信（本闸门同款新鲜度判据）。"""
        if not COV.exists():
            pytest.skip("无覆盖率产物")
        for r in _declarations():
            src = ROOT / r["detector_file"]
            assert src.stat().st_mtime <= COV.stat().st_mtime, \
                "覆盖率产物比 %s 旧，请重跑 scripts/_audit_redline_coverage.py" % r["detector_file"]


class TestCoverageCountsAuthorityTable:
    """归属的**第二种声明形态**：由权威表给出（检测器不写字面量）——覆盖率口径不得漏（A-P0-4）。"""

    def _table_ids(self):
        from engine import subject_consistency as SC
        ids = set(SC.REDLINE_SUBJECT_DECL)
        for v in SC.RECONCILE_AXIS_REDLINE.values():
            rid = (v[0] if isinstance(v, (list, tuple)) and v else "") or ""
            if rid:
                ids.add(rid)
        return ids

    def test_authority_tables_non_empty(self):
        from engine import subject_consistency as SC
        assert SC.REDLINE_SUBJECT_DECL, "归属权威表被清空 ⇒ 归属层失效"
        assert SC.RECONCILE_AXIS_REDLINE, "勾稽轴归属表被清空"

    def test_no_ghost_registration(self):
        assert not (self._table_ids() - _redline_ids()), "归属权威表登记了不存在的红线"

    def test_coverage_counts_table_declared_as_detector(self, coverage):
        """表声明的红线必须算「有真实检测器」，不得落到「仅兜底」。"""
        has = set(coverage["has_detector"])
        only = set(coverage["only_fallback"])
        for rid in sorted(self._table_ids()):
            assert rid in has, "%s 由权威表声明，却不在 has_detector" % rid
            assert rid not in only, "%s 由权威表声明，却被算成仅兜底" % rid

    def test_coverage_artifact_records_both_sources(self, coverage):
        """口径必须可审：字面量来源与表来源分开留痕，不得混成一个数字。"""
        assert "has_detector_static" in coverage and "has_detector_authority_table" in coverage, \
            "覆盖率产物未区分两种声明来源 ⇒ 口径不可审"
        assert set(coverage["has_detector"]) == (set(coverage["has_detector_static"])
                                                | set(coverage["has_detector_authority_table"]))

    def test_the_two_runtime_declared_are_visible_statically_now(self, coverage):
        """实测：这两条的归属**完全来自表**（静态正则看不见）——修正后必须可见。"""
        only_table = set(coverage["has_detector_authority_table"]) - \
            set(coverage["has_detector_static"])
        assert {"RL-CIT-008", "RL-PAY-002"} <= only_table, \
            "预期这两条由表声明（静态不可见），实际：%s" % sorted(only_table)


class TestOverlapLedgerAndNoBlindFallback:
    """同概念红线（A-P0-2 冗余裁定）：必须登记，且**无真检测器的成员不得靠兜底编闭环**。"""

    def _ledger(self):
        p = ROOT / "config" / "redline_overlap_ledger.json"
        return json.loads(p.read_text(encoding="utf-8"))

    def test_ledger_readable(self):
        rows = self._ledger().get("pairs")
        assert isinstance(rows, list) and rows, "同概念红线登记表为空 ⇒ 判据等于没跑"

    def test_members_exist(self):
        ids = _redline_ids()
        for pair in self._ledger()["pairs"]:
            assert len(pair["members"]) >= 2
            for m in pair["members"]:
                assert m in ids, "%s 不在红线库" % m

    def test_duplicate_without_detector_must_not_use_blind_fallback(self, coverage):
        """核心断言：**没有真检测器**的「要件重复」成员，不得登记兜底序号。"""
        from engine.redline_engine import (_DEFAULT_HIT_INDEX as DH,
                                           _NO_BLIND_CONSTITUENT_FALLBACK as NB)
        has = set(coverage["has_detector"])
        for pair in self._ledger()["pairs"]:
            if pair.get("verdict") != "constituent_duplicate":
                continue
            for m in pair["members"]:
                if m in has:
                    continue                     # 有真检测器 ⇒ 要件是真算过的
                assert m in NB, "%s 无检测器却不是「有意不做兜底」" % m
                assert m not in DH, "%s 无检测器却仍登记兜底 ⇒ 软匹配命中即认下要件（假闭环）" % m

    def test_every_member_has_net_increment(self):
        for pair in self._ledger()["pairs"]:
            for m in pair["members"]:
                assert str(pair["net_increment"].get(m) or "").strip(), \
                    "%s 未给出净增量 ⇒ 应提请裁定合并" % m

    def test_coverage_counts_no_blind_fallback_class(self, coverage):
        """覆盖率口径必须把"有意不做兜底"单列，不得混进盲区/仅兜底。

        ★ 2026-10-10（A 轨道）：`RL-VAT-012` 建真检测器后**已从本类归零**（现落 `has_detector`）。
          本判据改为**动态口径恒等式**——`本类 == 有意不兜底名单 − 已有真检测器者`，
          与 `scripts/_audit_redline_coverage.py` 的定义（`no_blind_no_detector = no_blind_ids - has_detector`）
          逐字一致 ⇒ 新增/迁移成员只改数据，判据不必改（否则每条一笔就假红）。
        """
        assert "no_blind_fallback_ids" in coverage and "no_blind_fallback_no_detector" in coverage, \
            "覆盖率产物未单列「有意不做兜底」⇒ 把红线移出兜底后会被误记成盲区"
        from engine.redline_engine import _NO_BLIND_CONSTITUENT_FALLBACK as NB
        _has = set(coverage["has_detector"])
        _nb_no_det = set(coverage["no_blind_fallback_no_detector"])
        assert _nb_no_det == {m for m in NB if m not in _has}, \
            "「有意不做兜底（无检测器）」与 `_NO_BLIND_CONSTITUENT_FALLBACK` 口径不一致：%s" \
            % sorted(_nb_no_det ^ {m for m in NB if m not in _has})
        for m in NB:
            assert m not in (coverage["blind"] or []), "%s 被误记为盲区（实为有意不做兜底）" % m
            assert m not in (coverage["only_fallback"] or []), "%s 被误记为仅兜底（实为有意不做兜底）" % m
        # 本切片的机器证明：012 建检测器后必须离开本类，且仍在 _NO_BLIND（软匹配不得回填要件）
        assert "RL-VAT-012" in _has, "012 应已有真检测器（VR036 通道3）"
        assert "RL-VAT-012" not in _nb_no_det, "012 已有真检测器，不得再留在「无检测器的有意不兜底」"
        assert "RL-VAT-012" in NB

    def test_no_contradiction_between_declaration_and_table(self):
        """既声明"有意不兜底"、又仍在兜底表里 ⇒ 半途状态（自洽性）。"""
        from engine.redline_engine import (_DEFAULT_HIT_INDEX as DH,
                                           _NO_BLIND_CONSTITUENT_FALLBACK as NB)
        assert not (set(NB) & set(DH)), "名单与兜底表交叉：%s" % sorted(set(NB) & set(DH))


class TestReverseVerification:
    """④ 反向验证：把声明改掉 ⇒ 上面的判据必须变红（否则判据是假的）。"""

    def test_removing_declaration_breaks_the_assertion(self):
        from engine import domain_analysis as DA
        orig = DA._domain_depreciation_match
        src = (ROOT / "engine" / "domain_analysis.py").read_text(encoding="utf-8")
        assert '"redline_id": "RL-AST-001"' in src

        def _strip(bank_txs, pur_invs):
            out = orig(bank_txs, pur_invs)
            for f in out:
                f.pop("redline_id", None)
            return out

        DA._domain_depreciation_match = _strip
        try:
            out = DA._domain_depreciation_match(
                [{"summary": "购设备", "counterparty": "x", "debit": 9000.0}], [])
            assert not any(f.get("redline_id") for f in out), \
                "变异无效：去掉声明后仍带 redline_id ⇒ 本组判据是假的"
        finally:
            DA._domain_depreciation_match = orig


class TestCapitalWeakeningAttribution:
    """⑤ 资本弱化（债资比）归属纠正 + RL-CIT-009/010 同概念裁定（2026-10-10，A 轨道）。

    病根：`deduction_limit_detector._check_related_party_debt_equity` **真算的是**
      「关联方借款 ÷ 所有者权益 → 超 2:1」（资本弱化），却把发现挂到
      `RL-CIT-002`「关联方无偿或低价资金往来：未按独立交易原则计息」（**另一概念**）
      ⇒ 一旦命中即产出「疑点主体与内容错配」的报告；同时 `RL-CIT-009` 与 010
      描述同一概念却只靠 `_DEFAULT_HIT_INDEX` 兜底 ⇒ **假闭环**。
    """

    DEBT_FN = "_check_related_party_debt_equity"

    def _ledger_pairs(self):
        data = json.loads((ROOT / "config" / "redline_overlap_ledger.json").read_text(encoding="utf-8"))
        return data.get("pairs") or []

    def test_009_010_registered_as_same_concept(self):
        hits = [p for p in self._ledger_pairs()
                if set(p.get("members") or []) == {"RL-CIT-009", "RL-CIT-010"}]
        assert hits, "RL-CIT-009/010 同概念（资本弱化·债资比超标）必须登记"
        assert hits[0].get("verdict") == "constituent_duplicate"
        ni = hits[0].get("net_increment") or {}
        for m in ("RL-CIT-009", "RL-CIT-010"):
            assert str(ni.get(m) or "").strip(), f"{m} 必须给出净增量（否则应提请合并）"

    def test_009_out_of_blind_fallback_and_not_blind(self, coverage):
        from engine.redline_engine import (_DEFAULT_HIT_INDEX as DH,
                                           _NO_BLIND_CONSTITUENT_FALLBACK as NB)
        assert "RL-CIT-009" not in DH, "009 无真检测器 ⇒ 不得靠兜底认要件（假闭环）"
        assert "RL-CIT-009" in NB, "009 必须声明「有意不做盲发兜底」"
        assert "RL-CIT-009" not in (coverage.get("blind") or []), "009 不是盲区，是「有意不兜底」"

    def test_debt_equity_detector_declares_cit_010(self):
        from engine.deduction_limit_detector import detect_deduction_limits
        bs = {"total_equity": 1_000_000.0}
        vch = [{"account_name": "其他应付款-关联方借款", "credit": 3_000_000.0, "贷方": 3_000_000.0}]
        fs = detect_deduction_limits(vch, {}, bs)
        assert len(fs) == 1, "债资比 3:1 超 2:1 ⇒ 必须产出待核事实"
        f = fs[0]
        assert f.get("redline_id") == "RL-CIT-010", \
            "债资比检测器必须自报 RL-CIT-010（不得再错挂 RL-CIT-002）"
        idx = [h.get("index") for h in (f.get("constituent_hits") or [])]
        assert idx == [1, 2], "只认领真算过的要件①②（存在关联方借款 / 债资比超标准）"

    def test_attribution_registry_row_matches_single_source(self):
        from engine.deduction_limit_detector import _REDLINE_DECL
        rows = [r for r in self._registry_rows() if r.get("detector_fn") == self.DEBT_FN]
        assert rows, "归属登记表必须登记债资比检测器"
        assert rows[0]["redline_id"] == \
            _REDLINE_DECL[self.DEBT_FN]["redline_id"], \
            "登记表与代码唯一来源（_REDLINE_DECL）必须一致，不得两处各写一份"

    def _registry_rows(self):
        data = json.loads((ROOT / "config" / "redline_detector_attribution.json").read_text(encoding="utf-8"))
        return data.get("declarations") or []

    def test_reverse_verification_declaration_is_single_source(self):
        """反向验证：`_REDLINE_DECL` 是运行期唯一来源 —— 改它 ⇒ 检测器产出必须跟着变。"""
        from engine import deduction_limit_detector as D
        key = self.DEBT_FN
        orig = D._REDLINE_DECL[key]["redline_id"]
        bs = {"total_equity": 1_000_000.0}
        vch = [{"account_name": "其他应付款-关联方借款", "credit": 3_000_000.0, "贷方": 3_000_000.0}]
        try:
            D._REDLINE_DECL[key]["redline_id"] = "RL-CIT-002"   # 恢复旧错配
            fs = D.detect_deduction_limits(vch, {}, bs)
            assert fs and fs[0].get("redline_id") == "RL-CIT-002", \
                "变异无效：改声明后产出未跟着变 ⇒ 说明运行期并未消费唯一来源（判据是假的）"
        finally:
            D._REDLINE_DECL[key]["redline_id"] = orig
        fs2 = D.detect_deduction_limits(vch, {}, bs)
        assert fs2 and fs2[0].get("redline_id") == "RL-CIT-010", "还原后必须回到 RL-CIT-010"
