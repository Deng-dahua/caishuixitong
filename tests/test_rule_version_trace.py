# -*- coding: utf-8 -*-
"""P0-A 规则版本留痕（`rule_version` / `rule_set_version`）的回归锁。

**为什么要有这组测试**（问题来自实测取证）：
在 P0-A 之前，finding 带 `trace_id` / Provenance / 法规版本 / 报告版本，**却没有规则版本**
—— 规则一改，历史结论无法回答"当时按哪版规则算的"。

本组锁住五件事：
  ① 版本**唯一权威**是 `config/rule_versions.json`，且**全部已发布规则都已登记**；
  ② **未登记 ⇒ 显式标「未登记」**，绝不默认（防伪造版本溯源）；
  ③ 无 `rule_id` 的发现（域分析等）标 `not_applicable`，不制造假归属；
  ④ finding（VR 链 + 红线链）**实际带上了**版本字段；
  ⑤ 报告载荷与作业终态流水**都能读到**规则集版本。

★ 隔离原则：纯函数 + monkeypatch 打桩，不落盘、不碰真实库。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from engine import analysis_jobs as AJ                 # noqa: E402
from engine import rule_versions as RV                 # noqa: E402
from engine.tax_redlines import REDLINES               # noqa: E402
from engine.verified_rule_engine import VERIFIED_RULE_CATALOG as VR_CATALOG  # noqa: E402
from engine.verified_rule_engine import _rule_finding  # noqa: E402
import tax_risk as T                                    # noqa: E402


class TestVersionAuthority:
    """① 唯一权威与登记完整性。"""

    def test_rule_set_version_declared(self):
        assert RV.rule_set_version(), "规则集版本未登记 ⇒ 报告无法自证规则口径"

    def test_every_published_rule_registered(self):
        ids = [r["id"] for r in REDLINES] + [s["id"] for s in VR_CATALOG]
        cov = RV.coverage(ids)
        assert cov["missing"] == [], "以下已发布规则未登记版本：%s" % cov["missing"][:10]
        assert cov["ratio"] == 1.0

    def test_version_of_unknown_returns_none(self):
        """未登记必须返回 None —— 不得回落成某个默认版本号。"""
        assert RV.version_of("RL-NOPE-9999") is None
        assert RV.version_of("") is None
        assert RV.version_of(None) is None

    def test_registered_items_have_version_and_effective_from(self):
        for rid, item in RV.load_versions()["rules"].items():
            assert item.get("version"), "%s 缺 version" % rid
            assert item.get("effective_from"), "%s 缺 effective_from" % rid


class TestStampSemantics:
    """② 打戳三态：registered / unregistered / not_applicable。"""

    def test_registered(self):
        f = {"rule_id": "VR001"}
        RV.stamp(f)
        assert f["rule_version"] == RV.version_of("VR001")
        assert f["rule_version_status"] == "registered"
        assert f["rule_set_version"] == RV.rule_set_version()

    def test_unregistered_marked_explicitly(self):
        f = {"rule_id": "VR-NOPE-9"}
        RV.stamp(f)
        assert f["rule_version"] == "未登记"
        assert f["rule_version_status"] == "unregistered"

    def test_redline_id_fallback(self):
        f = {"redline_id": "RL-VAT-001"}
        RV.stamp(f)
        assert f["rule_version"] == RV.version_of("RL-VAT-001")
        assert f["rule_version_status"] == "registered"

    def test_no_rule_id_not_applicable(self):
        f = {"type": "域分析发现"}
        RV.stamp(f)
        assert f["rule_version_status"] == "not_applicable"
        assert "rule_version" not in f, "无 rule_id 不应硬塞版本（假归属）"

    def test_idempotent(self):
        f = {"rule_id": "VR001"}
        RV.stamp(f)
        first = dict(f)
        RV.stamp(f)
        assert f == first


class TestTraceReachesFindings:
    """④ 版本真的落到了 finding 上（VR 链 + 红线链）。"""

    def test_vr_finding_carries_version(self):
        spec = {"id": "VR001", "name": "测试", "required_sources": ["s"]}
        f = _rule_finding(spec, "d", {}, ["s"])
        assert f["rule_version"] == RV.version_of("VR001")
        assert f["rule_set_version"] == RV.rule_set_version()

    def test_vr_finding_unregistered_marked(self):
        spec = {"id": "VR-NOPE-9", "name": "测试", "required_sources": ["s"]}
        f = _rule_finding(spec, "d", {}, ["s"])
        assert f["rule_version"] == "未登记"
        assert f["rule_version_status"] == "unregistered"

    def test_redline_suspicions_carry_version(self):
        sus = [{"redline_id": "RL-VAT-001", "redline_name": "x"},
               {"redline_id": "RL-NOPE-1", "redline_name": "y"}]
        RV.stamp_all(sus)
        assert sus[0]["rule_version"] == RV.version_of("RL-VAT-001")
        assert sus[0]["rule_version_status"] == "registered"
        assert sus[1]["rule_version_status"] == "unregistered"

    def test_snapshot_reports_hits_and_unregistered(self):
        snap = RV.snapshot([{"redline_id": "RL-VAT-001"}, {"redline_id": "RL-NOPE-1"}])
        assert snap["rule_set_version"] == RV.rule_set_version()
        assert "RL-NOPE-1" in snap["unregistered_rule_ids"]
        assert snap["hit_rule_versions"]["RL-VAT-001"] == RV.version_of("RL-VAT-001")


class TestReportPayload:
    """⑤ 报告载荷能读到规则版本（两个分支都要有）。"""

    def _payload(self, results, available=True):
        summary = T._report_summary(results, 0, analysis_available=available)
        return T._report_payload(
            company_id=1, period_start="2025-01", period_end="2025-06",
            summary=summary, results=results,
            notice="" if available else T._NO_DATA_NOTICE,
            analysis_available=available,
        )

    def test_payload_has_rule_version_block(self):
        p = self._payload([{"redline_id": "RL-VAT-001", "level": "中风险"}])
        assert set(p) == set(T._REPORT_PAYLOAD_KEYS), "键集必须与唯一权威键表一致"
        blk = p["rule_version"]
        assert blk["rule_set_version"] == RV.rule_set_version()
        assert blk["hit_rule_versions"]["RL-VAT-001"] == RV.version_of("RL-VAT-001")

    def test_payload_block_present_when_no_data(self):
        p = self._payload([], available=False)
        assert set(p) == set(T._REPORT_PAYLOAD_KEYS)
        assert p["rule_version"]["rule_set_version"] == RV.rule_set_version()
        assert p["rule_version"]["hit_rule_count"] == 0


class TestJobLedgerVersion:
    """⑤ 作业终态流水带规则集版本（打桩，不落盘）。"""

    def test_finished_row_carries_rule_set_version(self, monkeypatch):
        rows = []
        monkeypatch.setattr(AJ, "_last_terminal", lambda jid: None)
        monkeypatch.setattr(AJ, "_append_row", lambda r: rows.append(r))
        AJ.job_finished("JOB-X", "done", company_id=1, rule_set_version="2026.10")
        assert rows and rows[0]["event"] == "finished"
        assert rows[0]["rule_set_version"] == "2026.10"

    def test_finished_row_defaults_empty_not_fake(self, monkeypatch):
        rows = []
        monkeypatch.setattr(AJ, "_last_terminal", lambda jid: None)
        monkeypatch.setattr(AJ, "_append_row", lambda r: rows.append(r))
        AJ.job_finished("JOB-Y", "done", company_id=1)
        assert rows[0]["rule_set_version"] == "", "取不到版本必须留空，不得伪造"
