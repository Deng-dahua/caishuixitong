# -*- coding: utf-8 -*-
"""候选规则三件下一步事项的**执行台账**契约测试（2026-10-20）。

用户 2026-10-20 拍板三件事：① 8 条应建开发成检测器；② 59 条业务插件转插件清单；
③ 22 条重复更新清单状态。落成 `config/rule_dispositions.json`（生成器
`scripts/_gen_rule_dispositions.py`）。本测试断言台账的关键契约，含**反向验证**。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DISP = ROOT / "config" / "rule_dispositions.json"
ADJ = ROOT / "config" / "rule_adjudications.json"


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


class TestLedgerExists:
    def test_台账与生成器都在(self):
        assert DISP.exists(), "缺 config/rule_dispositions.json（三件事未落成台账）"
        assert (ROOT / "scripts" / "_gen_rule_dispositions.py").exists(), "缺生成器"

    def test_三类计数与裁定一致(self):
        """台账计数必须与裁定文件逐类相等（防多头维护）。"""
        disp, adj = _load(DISP), _load(ADJ)
        v = adj["verdicts"]
        for key, verdict in (("buildable", "buildable"),
                             ("industry_plugins", "industry_plugin"),
                             ("duplicates", "duplicate")):
            want = sum(1 for x in v.values() if x.get("verdict") == verdict)
            assert disp[key]["count"] == want, (
                "%s 计数 %s ≠ 裁定 %d" % (key, disp[key]["count"], want))


class TestBuildableVerification:
    """★ 核心：「数据源都在」是**声称**，台账必须逐条给实测核实结论。"""

    def test_每条应建都有实测核实结论(self):
        disp = _load(DISP)
        enum = {"structure_ok", "partial", "unfounded", "existing_covered"}
        items = disp["buildable"]["items"]
        assert len(items) == 8, "应建应为 8 条，实得 %d" % len(items)
        for x in items:
            assert str(x.get("data_verified") or "") in enum, (
                "%s 缺实测核实结论（data_verified）" % x.get("rule_id"))
            assert str(x.get("evidence") or "").strip(), (
                "%s 缺实测证据（evidence）" % x.get("rule_id"))

    def test_前提不成立者必须写明怎么补(self):
        disp = _load(DISP)
        for x in disp["buildable"]["items"]:
            if x.get("data_verified") == "unfounded":
                assert str(x.get("action") or "").strip(), (
                    "%s 前提不成立却未写明 action" % x.get("rule_id"))

    def test_已核实前提不成立的条目集合(self):
        """实测结论须与 2026-10-20 的核实一致（防被静默改写为'都在'）。"""
        disp = _load(DISP)
        s = disp["buildable"]["_summary"]
        assert set(s["前提不成立须先补数据源"]) == {"CONS-006", "IIT-004", "IIT-018"}, (
            "前提不成立集合变了 —— 若确已补数据源须同步改核实结论与证据")
        assert s["实为已覆盖"] == ["FIN-001"], "FIN-001 应为'已覆盖'"
        assert "INV-020" in s["可直接开发"], "INV-020（发票 remark 列已存在）应可直接开发"


class TestPluginsAndDuplicates:
    def test_插件分组名干净(self):
        disp = _load(DISP)
        groups = disp["industry_plugins"]["groups"]
        dirty = [k for k in groups if k.startswith("同 ") or "；" in k
                 or k == "未归类插件"]
        assert not dirty, "插件分组名含脏名（应从 data/plugin 规范化）：%r" % dirty
        assert disp["industry_plugins"]["count"] == 59

    def test_重复均注明保留对象(self):
        disp = _load(DISP)
        for x in disp["duplicates"]["items"]:
            assert str(x.get("merge_into") or "").strip(), (
                "%s 未注明并入/保留对象" % x.get("rule_id"))
            assert x.get("list_status") == "merged_or_retired"


class TestGate:
    def test_闸门接入run_checks(self):
        src = (ROOT / "tools" / "audit_consistency.py").read_text(encoding="utf-8")
        assert "+ check_rule_disposition_ledger()" in src, (
            "新闸门未接入 run_checks ⇒ 不会被执行")

    def test_闸门正例通过(self):
        from tools.audit_consistency import check_rule_disposition_ledger
        assert check_rule_disposition_ledger() == [], "台账闸门应无问题"

    def test_反向验证_篡改计数必报(self, monkeypatch):
        """★ 反向验证：篡改台账计数 ⇒ 闸门必须报「失同步」。"""
        import tools.audit_consistency as ac
        real = _load(DISP)
        bad = json.loads(json.dumps(real))
        bad["buildable"]["count"] = 99
        monkeypatch.setattr(ac, "json", ac.json)          # noqa: ARG005 - 保持可读
        # 直接把篡改内容写进临时路径不可行（闸门读固定路径）⇒ 改用 monkeypatch 读函数
        import pathlib

        class _FakePath(type(DISP)):
            pass

        orig_read = pathlib.Path.read_text

        def _patched(self, *a, **k):
            if str(self).endswith("rule_dispositions.json"):
                return json.dumps(bad, ensure_ascii=False)
            return orig_read(self, *a, **k)

        monkeypatch.setattr(pathlib.Path, "read_text", _patched, raising=True)
        try:
            issues = ac.check_rule_disposition_ledger()
            assert any("失同步" in x[2] for x in issues), (
                "篡改计数后闸门未报失同步 ⇒ 判据失效")
        finally:
            monkeypatch.setattr(pathlib.Path, "read_text", orig_read, raising=True)