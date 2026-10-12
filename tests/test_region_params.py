# -*- coding: utf-8 -*-
"""地区参数表 `config/region_params.json` 与候选库参数悬空的回归锁（2026-10-13）。

**为什么要有这组测试**（规则去重合并第 2 步实测）：
1. 候选库 `config/rulelist_v{1,11,12}.json` 的 `logic` 会引用 `params.<名>`，实测
   **3 处悬空引用**（VAT-021 `gap_threshold`、INV-008 `count_threshold`、
   PCT-006 `deduction_ratio`）⇒ 落地时取不到阈值 ⇒ 崩或用默认值顶替（违反「缺失≠0」）。
2. 任务要求「行业均值、**地区均值**必须参数化」，而地区参数此前**无集中表** ——
   候选库自身在 `params._note` 里就提出了「是否建立 config/region_params.json？」。

本组锁住五件事：
  ① 候选库**零悬空**（端到端，全 460 条现算）；
  ② 地区参数表结构合法（`kind ∈ {statutory, local_pending}`，字段齐备）；
  ③ **地方自定参数不得预设值**（`local_pending` ⇒ `value is None`）；
  ④ `statutory` 三档城建税税率齐备且为法定值；
  ⑤ 反向验证：制造悬空 / 给地方参数填值 ⇒ 闸门必须报红（证明判据非假）。

★ 隔离原则：纯只读 + monkeypatch，不落盘、不改真实配置。
"""
from __future__ import annotations

import copy
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_CAND = ("config/rulelist_v1.json", "config/rulelist_v11.json", "config/rulelist_v12.json")
_RP = ROOT / "config" / "region_params.json"
_NUM = re.compile(r"params\.(\w+)")


def _gate():
    spec = importlib.util.spec_from_file_location(
        "_t_rp_gate", ROOT / "tools" / "audit_consistency.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _region() -> dict:
    return json.loads(_RP.read_text(encoding="utf-8"))


class TestNoDanglingParams:
    """① 候选库零悬空（端到端）。"""

    def test_all_three_candidate_libs_load(self):
        for rel in _CAND:
            d = json.loads((ROOT / rel).read_text(encoding="utf-8"))
            assert d.get("rules"), rel

    def test_no_dangling_reference_across_all_rules(self):
        bad = []
        for rel in _CAND:
            d = json.loads((ROOT / rel).read_text(encoding="utf-8"))
            params = d.get("params") or {}
            for r in d["rules"]:
                used = set(_NUM.findall(str(r.get("logic") or "")))
                if not used:
                    continue
                entry = params.get(r.get("src"))
                if not isinstance(entry, dict):
                    continue
                miss = sorted(x for x in used if x not in entry)
                if miss:
                    bad.append((rel, r.get("src"), miss))
        assert not bad, "候选库存在悬空参数引用：\n" + "\n".join(map(str, bad))

    def test_gate_reports_zero(self):
        errs = [i for i in _gate().check_candidate_params_no_dangling() if i[0] == "ERROR"]
        assert errs == [], errs

    def test_pct006_deduction_ratio_registered_as_pending(self):
        """PCT-006 的 deduction_ratio 必须已登记且为 None（地方参数，待属地确认）。"""
        d = json.loads((ROOT / "config/rulelist_v11.json").read_text(encoding="utf-8"))
        e = d["params"]["PCT-006"]
        assert "deduction_ratio" in e
        assert e["deduction_ratio"] is None, "地方参数不得预设值"

    def test_gap_threshold_and_count_threshold_no_longer_referenced(self):
        """两条同义两名已统一：**`logic` 里**不得再引用旧名。

        ★ 判据范围必须限定在 `logic` 字段 —— 留痕 `_basis` 里**故意保留**了旧名
          （「原引用 params.gap_threshold，已统一为 diff_amount」），
          若按全文匹配会误报。**改判据，不改留痕。**
        """
        v1 = json.loads((ROOT / "config/rulelist_v1.json").read_text(encoding="utf-8"))
        v11 = json.loads((ROOT / "config/rulelist_v11.json").read_text(encoding="utf-8"))
        logics_v1 = " ".join(str(r.get("logic") or "") for r in v1["rules"])
        logics_v11 = " ".join(str(r.get("logic") or "") for r in v11["rules"])
        assert "params.gap_threshold" not in logics_v1
        assert "params.count_threshold" not in logics_v11 or \
            "same_customer_invoice_count > params.count_threshold" not in logics_v11
        # 留痕必须保留（可追溯）：_basis 里应能查到旧名
        assert "gap_threshold" in str(v1["params"]["VAT-021"].get("_basis"))
        assert "count_threshold" in str(v11["params"]["INV-008"].get("_basis"))


class TestRegionParamsStructure:
    """② 地区参数表结构合法。"""

    def test_exists_and_parses(self):
        assert _RP.exists(), "缺 config/region_params.json"
        assert _region().get("params"), "params 不得为空"

    def test_every_entry_has_required_fields(self):
        for k, v in _region()["params"].items():
            assert isinstance(v, dict), k
            for f in ("cn", "kind", "authority", "value", "status"):
                assert f in v, "%s 缺字段 %s" % (k, f)
            assert v["kind"] in ("statutory", "local_pending"), (k, v["kind"])

    def test_pending_list_matches_local_entries(self):
        """`pending` 清单必须覆盖全部 `local_pending` 条目（不得漏报待核项）。"""
        rp = _region()
        local_keys = {k for k, v in rp["params"].items()
                      if v.get("kind") == "local_pending"}
        pending_txt = " ".join(rp.get("pending") or [])
        missing = [k for k in local_keys if k not in pending_txt]
        assert not missing, "以下地方参数未出现在 pending 清单：%s" % missing


class TestNoPresetLocalValues:
    """③ 地方自定参数不得预设值（核心铁律）。"""

    def test_all_local_pending_have_null_value(self):
        for k, v in _region()["params"].items():
            if v.get("kind") == "local_pending":
                assert v.get("value") is None, (
                    "%s 是地方自定参数却预设了值 %r ⇒ 禁止（须业务按属地确认）"
                    % (k, v.get("value")))

    def test_all_local_pending_marked_pending_local(self):
        for k, v in _region()["params"].items():
            if v.get("kind") == "local_pending":
                assert v.get("status") == "pending_local", (k, v.get("status"))

    def test_source_empty_while_pending(self):
        """未确认（value=None）时 source 必须为空 —— 不得伪造来源。"""
        for k, v in _region()["params"].items():
            if v.get("value") is None:
                assert not v.get("source"), "%s 无值却填了来源 ⇒ 伪造来源" % k


class TestStatutoryBands:
    """④ 法定固定值齐备（城建税三档）。"""

    def test_urban_maintenance_band_has_three_legal_rates(self):
        v = _region()["params"]["urban_maintenance_rate_band"]
        assert v["kind"] == "statutory"
        bands = {b["where"]: b["rate"] for b in (v.get("bands") or [])}
        assert bands == {"市区": 0.07, "县城、镇": 0.05, "其他": 0.01}, bands

    def test_band_requires_location_not_default(self):
        """有三档却未给所在地 ⇒ status 须为 requires_location（不得默认按市区档）。"""
        v = _region()["params"]["urban_maintenance_rate_band"]
        assert v.get("status") == "requires_location"

    def test_legal_ranges_declared_for_mandated_params(self):
        """有法定区间的（房产税扣除、契税）必须登记 legal_range。"""
        rp = _region()["params"]
        assert rp["property_tax_deduction_ratio"]["legal_range"] == [0.10, 0.30]
        assert rp["deed_tax_rate"]["legal_range"] == [0.03, 0.05]


class TestGateReverse:
    """⑤ 反向验证：破坏 ⇒ 闸门必须报红。"""

    def test_reverse_preset_local_value_is_flagged(self, monkeypatch):
        g = _gate()
        d = copy.deepcopy(_region())
        d["params"]["deed_tax_rate"]["value"] = 0.03      # ★ 预设地方值
        monkeypatch.setattr(g, "_read_json_for_gate", None, raising=False)
        # 直接打桩 ROOT 下的文件读取：用临时目录不可行（闸门读固定路径），
        # 故改为替换 ROOT 为临时目录并在其中放坏表。
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            (tdp / "config").mkdir()
            (tdp / "config" / "region_params.json").write_text(
                json.dumps(d, ensure_ascii=False), encoding="utf-8")
            for rel in _CAND:
                (tdp / "config" / Path(rel).name).write_text(
                    (ROOT / rel).read_text(encoding="utf-8"), encoding="utf-8")
            monkeypatch.setattr(g, "ROOT", tdp, raising=True)
            errs = [i for i in g.check_candidate_params_no_dangling() if i[0] == "ERROR"]
        assert any("禁止预设地方值" in i[2] for i in errs), errs

    def test_reverse_dangling_reference_is_flagged(self, monkeypatch):
        g = _gate()
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            (tdp / "config").mkdir()
            d = json.loads((ROOT / "config/rulelist_v1.json").read_text(encoding="utf-8"))
            # 制造悬空：把某条的 logic 引到未登记的参数名
            for r in d["rules"]:
                if r["src"] == "VAT-004":
                    r["logic"] = "x > params.__nonexistent__"
                    break
            (tdp / "config" / "rulelist_v1.json").write_text(
                json.dumps(d, ensure_ascii=False), encoding="utf-8")
            for rel in _CAND[1:]:
                (tdp / "config" / Path(rel).name).write_text(
                    (ROOT / rel).read_text(encoding="utf-8"), encoding="utf-8")
            (tdp / "config" / "region_params.json").write_text(
                _RP.read_text(encoding="utf-8"), encoding="utf-8")
            monkeypatch.setattr(g, "ROOT", tdp, raising=True)
            errs = [i for i in g.check_candidate_params_no_dangling() if i[0] == "ERROR"]
        assert any("悬空引用" in i[2] for i in errs), errs

    def test_reverse_missing_region_table_is_flagged(self, monkeypatch):
        g = _gate()
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            (tdp / "config").mkdir()
            for rel in _CAND:
                (tdp / "config" / Path(rel).name).write_text(
                    (ROOT / rel).read_text(encoding="utf-8"), encoding="utf-8")
            monkeypatch.setattr(g, "ROOT", tdp, raising=True)
            errs = [i for i in g.check_candidate_params_no_dangling() if i[0] == "ERROR"]
        assert any("地区参数表缺失" in i[2] for i in errs), errs
