# -*- coding: utf-8 -*-
"""规则分层唯一权威（`config/rule_versions.json::layer_semantics`）的回归锁。

**为什么要有这组测试**（问题来自实测取证，2026-10-11）：
多份文档曾写「规则四层合计 **211** 条」= 红线 91 + 已验证 85 + 专项 25 + 缺口 10。
实测发现：`special_redline_detectors`（25）、`gap_risk_detectors`（10）、
`gap_tax_obligations`（14）的 id **全部落在 91 条红线内** —— 它们是红线的
**检测器实现层**，不是独立规则。把检测器实现层计入规则总数即**重复计数**（虚高约 22%）。

本组锁住四件事：
  ① 权威表与**实测**一致（每层 count == 真实条数；规则主体 = 红线 + 已验证）；
  ② 检测器实现层的 id **必须全部归属既有红线**（一旦出现独立 id ⇒ 分层被破坏）；
  ③ 权威表把 211/215 明确登记为**禁用拼接总量**（防止再次被写回文档）；
  ④ 文档/README/config 里**不得再出现**「四层合计 211」这类拼接表述。

★ 隔离原则：纯只读 + 按文件加载（绕缓存），不落盘、不碰真实库。
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_RV = json.loads((ROOT / "config" / "rule_versions.json").read_text(encoding="utf-8"))


def _load(rel: str, tag: str):
    """按**文件**加载模块（绕 `sys.modules` / `engine` 包属性缓存）。"""
    spec = importlib.util.spec_from_file_location(tag, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _redline_ids() -> set:
    return {str(r["id"]) for r in _load("engine/tax_redlines.py", "_t_rl").REDLINES}


def _special_ids() -> list:
    m = _load("engine/special_redline_detectors.py", "_t_sp")
    return [str(x.get("id") or x.get("redline_id") or "") for x in m.SPECS]


def _gap_risk_ids() -> list:
    m = _load("engine/gap_risk_detectors.py", "_t_gr")
    return [str(x[0]) for x in m.DETECTORS]          # [(redline_id, func), ...]


def _gap_oblig_ids() -> list:
    m = _load("engine/gap_tax_obligations.py", "_t_gp")
    return [str(x.get("redline_id") or x.get("id") or "") for x in m.SPECS]


class TestAuthorityTableConsistency:
    """① 权威表 count 必须等于实测（同概念不得两处各写一遍）。"""

    def test_redlines_count_matches(self):
        assert _RV["layer_semantics"]["layers"]["tax_redlines"]["count"] == len(_redline_ids())

    def test_verified_rules_count_matches(self):
        n = len(_load("engine/verified_rule_engine.py", "_t_vr").VERIFIED_RULE_CATALOG)
        assert _RV["layer_semantics"]["layers"]["verified_rule_engine"]["count"] == n

    def test_detector_layers_count_match(self):
        L = _RV["layer_semantics"]["layers"]
        assert L["special_redline_detectors"]["count"] == len([i for i in _special_ids() if i])
        assert L["gap_risk_detectors"]["count"] == len([i for i in _gap_risk_ids() if i])
        assert L["gap_tax_obligations"]["count"] == len([i for i in _gap_oblig_ids() if i])

    def test_counts_and_layer_semantics_not_divergent(self):
        """`counts` 与 `layer_semantics` 不得两处各写一遍而后不一致。"""
        c = _RV["counts"]
        L = _RV["layer_semantics"]["layers"]
        assert c["tax_redlines"] == L["tax_redlines"]["count"]
        assert c["verified_rule_engine"] == L["verified_rule_engine"]["count"]

    def test_rule_subject_is_redlines_plus_verified(self):
        """规则主体 = 红线 + 已验证规则（检测器实现层不计入）。"""
        L = _RV["layer_semantics"]["layers"]
        assert L["tax_redlines"]["counts_toward_rule_total"] is True
        assert L["verified_rule_engine"]["counts_toward_rule_total"] is True
        for k in ("special_redline_detectors", "gap_risk_detectors",
                  "gap_tax_obligations", "fact_check_rules"):
            assert L[k]["counts_toward_rule_total"] is False, k


class TestDetectorLayerBelongsToRedlines:
    """② 检测器实现层的 id 必须全部归属既有红线（核心判据）。"""

    def test_special_detectors_all_belong(self):
        rl = _redline_ids()
        assert all(i in rl for i in _special_ids())

    def test_gap_risk_detectors_all_belong(self):
        rl = _redline_ids()
        assert all(i in rl for i in _gap_risk_ids())

    def test_gap_tax_obligations_all_belong(self):
        rl = _redline_ids()
        assert all(i in rl for i in _gap_oblig_ids())

    def test_layers_are_not_trivially_empty(self):
        """防止"把层清空"来伪造通过。"""
        assert len(_special_ids()) == 25
        assert len(_gap_risk_ids()) == 10
        assert len(_gap_oblig_ids()) == 14


class TestForbiddenAggregationsRegistered:
    """③ 211 / 215 必须登记为禁用拼接总量（防再次写回）。"""

    def test_values_registered(self):
        vals = {x["value"] for x in _RV["layer_semantics"]["forbidden_aggregations"]}
        assert {211, 215} <= vals

    def test_each_has_reason(self):
        for x in _RV["layer_semantics"]["forbidden_aggregations"]:
            assert x.get("reason"), x
            assert x.get("formula")


class TestNoDoubleCountInDocs:
    """④ 文档/README/config 不得再出现「(四层|合计…) 211/215」拼接表述。"""

    _NUM = re.compile(r"(?<!\d)(?:211|215)(?!\d)")
    _CTX = re.compile(r"(?:四层|各层|合计|总计|共计|系统侧)")
    _EXEMPT = ("勘误", "重复计数", "废止", "禁止", "不得", "虚高", "错误口径",
               "旧口径", "更正", "弃用", "不应相加", "子集")

    def _targets(self):
        out = sorted((ROOT / "docs").rglob("*.md"))
        out.append(ROOT / "README.md")
        out += sorted((ROOT / "config").glob("rulelist_v*.json"))
        return [p for p in out if p.exists()]

    def test_no_forbidden_aggregation_in_docs(self):
        bad = []
        for p in self._targets():
            for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if self._NUM.search(ln) and self._CTX.search(ln) \
                        and not any(e in ln for e in self._EXEMPT):
                    bad.append("%s:%d: %s" % (p.relative_to(ROOT), i, ln.strip()[:60]))
        assert not bad, "仍有拼接总量表述：\n" + "\n".join(bad)


class TestBridgeToGate:
    """⑤ 与审计闸门同源：闸门在当前库上必须 0 ERROR（不假绿）。"""

    def test_gate_reports_zero_errors(self):
        spec = importlib.util.spec_from_file_location(
            "_t_gate", ROOT / "tools" / "audit_consistency.py")
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        assert [i for i in gate.check_rule_layer_no_double_count()
                if i[0] == "ERROR"] == []
