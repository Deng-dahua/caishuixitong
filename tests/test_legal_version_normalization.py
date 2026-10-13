# -*- coding: utf-8 -*-
"""法名**文号↔全称归一**的回归锁 —— T-5 第二阶段（2026-10-13）。

**为什么要有这组测试**（实测根因）：
`_VERSION_NOTE_RE` 明确"不认文号括注"，导致**同一部法两套法名**被当成两部法：
  · 引用写「企业所得税核定征收办法（国税发〔2008〕30号）」，登记表存「企业所得税核定征收办法」；
  · 引用只写文号「财税〔2003〕158号」，登记表存全称。
⇒ 法条版本闸门报"未登记"（**假缺口**）。实测 39 个"未登记法名"中 **18 个**属此类。

修法：**显式登记** `doc_no` 字段（★ 唯一权威），别名表只由它派生。
  ⚠ 曾用 `source` 自由文本解析（2026-10-13 实测事故）：`source` 天然**交叉引用其它文件文号**
  （「扣除率后经财税〔2017〕37号等调整」）⇒ `财税〔2017〕37号` 被**错误归属**到引用者
  （《农产品…核定扣除…通知》），**报告会显示错的版本**。⇒ 文号归属不得从正文猜。

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

    def test_alias_derived_from_doc_no_field(self):
        """别名表由登记表 `doc_no` **显式字段**派生（改了登记表即自动同步；不从正文猜）。"""
        assert LV._wenhao_alias_index().get("财税〔2003〕158号", "") \
            == LV.canonical_law("财政部 国家税务总局关于规范个人投资者个人所得税征收管理的通知")
        # 每条有文号者必须来自 doc_no 字段（该键须显式声明，可为 null）
        missing = [e.get("law") for e in LV.registry_entries() if "doc_no" not in e]
        assert not missing, "登记项未显式声明 doc_no 键：%s" % missing[:3]


class TestNoFalseUnregistered:
    """④ 端到端：假缺口必须为 0。"""

    def test_no_alias_resolvable_but_unregistered(self):
        idx = set(LV.registered_laws())
        unreg = {LV.canonical_law(split_citation(c)[0] or c) for c in _cites()} - idx - {""}
        false_unreg = [n for n in unreg if LV._resolve_alias(n) and LV._resolve_alias(n) not in idx]
        assert not false_unreg, "文号可解析却仍判未登记：%s" % false_unreg[:5]

    def test_unregistered_count_is_zero(self):
        """未登记法名应收敛为 0（修复前 39 → 别名归一 11 → 本轮逐条核实后 **0**）。"""
        idx = set(LV.registered_laws())
        unreg = {LV.canonical_law(split_citation(c)[0] or c) for c in _cites()} - idx - {""}
        assert len(unreg) == 0, "未登记法名：%d → %s" % (len(unreg), sorted(unreg)[:5])


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


class TestVatLawTransition:
    """★★ 增值税法体系（2026-01-01 施行）—— 本轮实测发现的系统性时效问题。

    事故：《增值税暂行条例》**自 2026-01-01 起废止**（《增值税法》第三十八条），
    但登记表仍标 `current`，且**多条红线**引用它 ⇒ 引用已废止法而未被告警。
    """

    def test_vat_law_registered_and_current(self):
        assert LV.is_current("中华人民共和国增值税法")
        assert LV.is_current("中华人民共和国增值税法实施条例")

    def test_old_vat_regulation_marked_expired(self):
        assert LV.status_of("增值税暂行条例") in ("expired", "superseded")
        assert LV.is_blocking("增值税暂行条例") is True

    def test_implementation_rules_superseded(self):
        assert LV.is_blocking("增值税暂行条例实施细则") is True

    def test_core_laws_points_to_current_vat_law(self):
        """CORE_LAWS 不得再指向已废止的暂行条例。"""
        assert "增值税暂行条例" not in LV.CORE_LAWS
        assert "中华人民共和国增值税法" in LV.CORE_LAWS
        assert LV.unregistered_core_laws() == []

    def test_no_redline_cites_old_vat_regulation(self):
        """端到端：红线库不得再引用《增值税暂行条例》/实施细则。

        ⚠ 判据须精确到**书名号内的全称**：`《中华人民共和国土地增值税暂行条例》`（现行有效的
        另一部法）也含「增值税暂行条例」子串，用裸子串匹配会**误报**。
        """
        bad = [c[:70] for c in _cites()
               if "《增值税暂行条例》" in c or "《中华人民共和国增值税暂行条例》" in c]
        assert not bad, "仍引用已废止的暂行条例：%s" % bad


class TestDocNoIntegrity:
    """★★ 文号归属必须**显式登记**，不得从 `source` 正文猜（实测事故）。"""

    def test_every_entry_declares_doc_no_key(self):
        missing = [e.get("law") for e in LV.registry_entries() if "doc_no" not in e]
        assert not missing, "登记项未显式声明 doc_no：%s" % missing[:5]

    def test_no_duplicate_doc_no_across_entries(self):
        seen, dup = {}, []
        for e in LV.registry_entries():
            dn = e.get("doc_no")
            for w in ([dn] if isinstance(dn, str) else list(dn or [])):
                if not w:
                    continue
                k = LV._norm_wh(w)
                if k in seen and seen[k] != e.get("law"):
                    dup.append((k, seen[k], e.get("law")))
                seen[k] = e.get("law")
        assert not dup, "同一文号被多条登记（归属歧义）：%s" % dup[:3]

    def test_37_is_the_simplified_rate_notice(self):
        """★ 实测事故回归：`财税〔2017〕37号` 必须归一到《简并增值税税率…通知》，
        不得被 `source` 里的交叉引用（「扣除率后经财税〔2017〕37号等调整」）带偏到农产品核定扣除。"""
        got = LV.canonical_law("财税〔2017〕37号")
        assert "简并增值税税率" in got, "文号被错误归属：%s" % got
        assert "核定扣除" not in got

    def test_72_is_the_fund_notice(self):
        got = LV.canonical_law("财税〔2020〕72号")
        assert "民航发展基金" in got, "文号被错误归属：%s" % got

    def test_reverse_wrong_doc_no_mapping_is_detectable(self, monkeypatch):
        """★ 反向验证：把文号指向**错的**法 ⇒ 归一必错（证明上面的判据非空）。"""
        wrong = LV._base_key("财政部 国家税务总局关于在部分行业试行农产品增值税进项税额核定扣除办法的通知")
        monkeypatch.setattr(LV, "_wenhao_alias_index",
                            lambda: {"财税〔2017〕37号": wrong}, raising=True)
        assert LV.canonical_law("财税〔2017〕37号") == wrong, \
            "判据失真：篡改 doc_no 指向后竟仍归一为正确法"


class TestT5BatchRegistered:
    """本轮核实批（逐条经官方渠道核实）已登记且状态正确。"""

    @pytest.mark.parametrize("law", [
        "中华人民共和国工会法",                       # 2021 修正，2022-01-01 施行
        "残疾人就业条例",                             # 国务院令第488号，2007-05-01 施行
        "财政部 国家税务总局关于在部分行业试行农产品增值税进项税额核定扣除办法的通知",   # 财税〔2012〕38号
        "财政部 国家税务总局关于营业税改征增值税试点有关文化事业建设费政策及征收管理问题的通知",      # 财税〔2016〕25号
        "财政部 国家税务总局关于营业税改征增值税试点有关文化事业建设费政策及征收管理问题的补充通知",  # 财税〔2016〕60号
        "财政部 税务总局关于简并增值税税率有关政策的通知",   # 财税〔2017〕37号
        "财政部关于民航发展基金等3项政府性基金有关政策的通知",  # 财税〔2020〕72号
        "财政部 税务总局关于完善增值税期末留抵退税政策的公告",   # 2025年第7号
        "国家税务总局关于办理增值税期末留抵退税有关征管事项的公告",  # 2025年第20号
    ])
    def test_registered(self, law):
        assert LV.canonical_law(law) in set(LV.registered_laws()), "未登记：%s" % law

    def test_abandoned_reit_announcements_are_expired(self):
        """留抵退税 2022 年第 14／21 号已自 2025-09-01 全文废止。"""
        assert LV.is_blocking("财政部 税务总局关于进一步加大增值税期末留抵退税政策实施力度的公告")
        assert LV.is_blocking("财政部 税务总局关于扩大全额退还增值税留抵税额政策行业范围的公告")

    def test_no_redline_cites_abandoned_reit(self):
        bad = [c[:70] for c in _cites() if "2022年第14号" in c or "2022年第21号" in c]
        assert not bad, "仍引用已废止的留抵退税公告：%s" % bad

    def test_vehicle_purchase_tax_implementing_regulation_not_claimed(self):
        """「车辆购置税法实施条例」经核实**并不存在**（车购税具体政策以财政部公告2019年第71号
        + 国家税务总局公告2019年第26号承载）⇒ 不得登记，且红线不得再引用。"""
        assert "车辆购置税法实施条例" not in set(LV.registered_laws())
        bad = [c[:70] for c in _cites() if "车辆购置税法实施条例" in c]
        assert not bad, "仍引用不存在的法规：%s" % bad


class TestT5Acceptance:
    """★ T-5 验收指标：红线库引用的法条**100% 可溯源**（未登记法名 = 0）。"""

    def test_zero_unregistered_law_names(self):
        idx = set(LV.registered_laws())
        unreg = {LV.canonical_law(split_citation(c)[0] or c) for c in _cites()} - idx - {""}
        assert not unreg, "仍有未登记法名：%s" % sorted(unreg)[:6]

    def test_no_blocking_status_citation(self):
        assert LV.audit_citations(_cites()) == [], "存在引用已废止/被取代法条的引用"
