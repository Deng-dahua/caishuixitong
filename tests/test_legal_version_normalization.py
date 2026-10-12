# -*- coding: utf-8 -*-
"""法名**文号↔全称归一**的回归锁 —— T-5 第二阶段（2026-10-13）。

**为什么要有这组测试**（实测根因）：
`_VERSION_NOTE_RE` 明确"不认文号括注"，导致**同一部法两套法名**被当成两部法：
  · 引用写「企业所得税核定征收办法（国税发〔2008〕30号）」，登记表存「企业所得税核定征收办法」；
  · 引用只写文号「财税〔2003〕158号」，登记表存全称。
⇒ 法条版本闸门报"未登记"（**假缺口**）。实测 39 个"未登记法名"中 **18 个**属此类。

修法：从登记表自身 `source` 字段**派生**「文号 → 登记法名」别名表（单一权威，不会漂移）。

本组锁住六件事：
  ① 文号写法可归一到登记名；② 全称写法保持稳定（不改坏既有）；③ 「（试行）」类保留；
  ④ **端到端**：红线库中不得再出现"文号可解析却判未登记"的假缺口；
  ⑤ 已废止法必须被 `is_blocking` 拦下（引用失效法是真事故）；
  ⑥ 反向验证：清空别名表 ⇒ 假缺口必须复现（证明 ④ 的判据非空）。

★ 隔离原则：只读 + 缓存重置，不落盘。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

from engine import legal_version as LV                     # noqa: E402
from engine.legal_citation import split_citation           # noqa: E402
from engine.tax_redlines import REDLINES                   # noqa: E402


@pytest.fixture(autouse=True)
def _reset():
    LV.reset_caches()
    yield
    LV.reset_caches()


def _cites():
    out = []
    for r in (REDLINES or []):
        lb = (r or {}).get("legal_basis")
        if isinstance(lb, str):
            lb = [lb]
        for it in (lb or []):
            if isinstance(it, str) and it.strip():
                out.append(it)
    return out


class TestWenhaoNormalization:
    """①②③ 归一行为。"""

    def test_wenhao_inside_parenthetical_resolves(self):
        """引用带「（文号）」⇒ 归一到登记全称。"""
        assert LV.canonical_law("企业所得税核定征收办法（国税发〔2008〕30号）") \
            == "企业所得税核定征收办法"

    def test_wenhao_only_citation_resolves(self):
        """引用**只写文号** ⇒ 归一到登记全称。"""
        got = LV.canonical_law("财税〔2003〕158号")
        assert "规范个人投资者个人所得税征收管理" in got

    def test_gonggao_wenhao_resolves(self):
        got = LV.canonical_law("国家税务总局公告2014年第67号")
        assert got == "股权转让所得个人所得税管理办法（试行）"

    def test_full_name_is_stable(self):
        """登记全称本身不得被改写（防"归一过度"）。"""
        assert LV.canonical_law("税收征收管理法") == "税收征收管理法"
        assert LV.canonical_law("发票管理办法") == "发票管理办法"

    def test_shixing_note_preserved(self):
        """「（试行）」属法名本身，不得剥除。"""
        assert "试行" in LV.canonical_law("股权转让所得个人所得税管理办法（试行）")

    def test_registry_wenhao_named_law_not_rewritten(self):
        """以文号为**登记名**的条目（如 `国家税务总局公告2014年第39号`）不得被改写。"""
        assert LV.canonical_law("国家税务总局公告2014年第39号") \
            == "国家税务总局公告2014年第39号"

    def test_note_inside_book_title_stripped(self):
        """引用把**说明**写进《》内（如「…（引用较早，具体适用须…复核）」）⇒ 归一应剥离。"""
        got = LV.canonical_law(
            "增值税专用发票使用规定（引用较早，具体适用须按业务发生期间取得官方有效文本并由有权人员复核）")
        assert got == "增值税专用发票使用规定"


class TestAliasIndex:
    """别名表机制本身。"""

    def test_alias_index_nonempty(self):
        assert len(LV._wenhao_alias_index()) >= 10, "别名表为空 ⇒ 归一机制未生效"

    def test_alias_values_are_registered_laws(self):
        """别名表的**值**必须都是已登记法名（否则是幽灵指向）。"""
        idx = set(LV.registered_laws())
        bad = {k: v for k, v in LV._wenhao_alias_index().items() if v not in idx}
        assert not bad, "别名指向未登记法名：%s" % list(bad.items())[:3]

    def test_alias_derived_from_registry_source(self):
        """别名表由登记表 `source` 派生（改了登记表即自动同步）。"""
        assert LV._wenhao_alias_index().get("财税〔2003〕158号", "") \
            == LV.canonical_law("财政部 国家税务总局关于规范个人投资者个人所得税征收管理的通知")


class TestNoFalseUnregistered:
    """④ 端到端：假缺口必须为 0。"""

    def test_no_alias_resolvable_but_unregistered(self):
        idx = set(LV.registered_laws())
        unreg = {LV.canonical_law(split_citation(c)[0] or c) for c in _cites()} - idx - {""}
        false_unreg = [n for n in unreg if LV._resolve_alias(n) and LV._resolve_alias(n) not in idx]
        assert not false_unreg, "文号可解析却仍判未登记：%s" % false_unreg[:5]

    def test_unregistered_count_is_low(self):
        """未登记法名应已大幅收敛（修复前 39；别名+登记后应 ≤ 15）。"""
        idx = set(LV.registered_laws())
        unreg = {LV.canonical_law(split_citation(c)[0] or c) for c in _cites()} - idx - {""}
        assert len(unreg) <= 15, "未登记法名仍偏多：%d → %s" % (len(unreg), sorted(unreg)[:5])


class TestExpiredLawBlocked:
    """⑤ 已废止法必须被拦下（引用失效法是真事故）。"""

    def test_export_refund_old_measure_is_expired(self):
        assert LV.status_of("出口货物退（免）税管理办法") == "expired"
        assert LV.is_blocking("出口货物退（免）税管理办法") is True

    def test_current_successor_registered(self):
        """现行依据（2026年公告）必须已登记且为现行有效。"""
        assert LV.is_current("出口业务增值税和消费税退（免）税管理办法")
        got = LV.canonical_law("财政部 税务总局公告2026年第11号")
        assert got and LV.is_current(got)

    def test_redlines_no_longer_cite_expired_law(self):
        """红线库不得再引用已废止法（端到端）。"""
        bad = [c[:60] for c in _cites() if "出口货物退（免）税管理办法" in c]
        assert not bad, "仍引用已废止法：%s" % bad


class TestReverseGuard:
    """⑥ 反向验证：破坏归一 ⇒ 假缺口必须复现（证明判据非空）。

    ★ 教训（本组实测）：归一有**两道防线** ——
      ○ 别名表（文号 → 登记名）
      ○ 剥尾部括注（「…办法（国税发〔2008〕30号）」→「…办法」）
    因此对"带文号括注"的写法，只破坏别名**仍能归一**（假绿）。
    必须用**只有别名能解**的写法（纯文号引用）才能真验证。
    """

    def test_breaking_alias_reproduces_false_unregistered(self, monkeypatch):
        """纯文号引用（`财税〔2003〕158号`）只有别名能解 ⇒ 破坏别名必判未登记。"""
        monkeypatch.setattr(LV, "_wenhao_alias_index", lambda: {}, raising=True)
        got = LV.canonical_law("财税〔2003〕158号")
        assert got not in set(LV.registered_laws()), \
            "判据失真：别名失效后纯文号引用竟仍判为已登记"

    def test_breaking_both_defenses_reproduces_it_for_parenthetical_form(self, monkeypatch):
        """带文号括注的写法需**两道防线同时破坏**才复现（否则是假绿）。"""
        import re as _re
        monkeypatch.setattr(LV, "_wenhao_alias_index", lambda: {}, raising=True)
        monkeypatch.setattr(LV, "_TRAIL_NOTE_RE", _re.compile(r"(?!x)x"), raising=True)
        got = LV.canonical_law("企业所得税核定征收办法（国税发〔2008〕30号）")
        assert got not in set(LV.registered_laws()), \
            "判据失真：两道防线都破坏后竟仍能归一"

    def test_restore_alias_fixes_it(self):
        assert LV.canonical_law("财税〔2003〕158号") in set(LV.registered_laws())
        assert LV.canonical_law("企业所得税核定征收办法（国税发〔2008〕30号）") \
            == "企业所得税核定征收办法"


class TestRegistryIntegrity:
    """登记表自身的完整性（新增条目不破坏 schema）。"""

    def test_registry_audit_clean(self):
        assert LV.audit_registry() == []

    def test_registry_count_grew(self):
        assert len(LV.registered_laws()) >= 50, "T-5 第二阶段应新增登记（现 45+）"
