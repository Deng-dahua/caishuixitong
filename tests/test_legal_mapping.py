# -*- coding: utf-8 -*-
"""法规 ⇄ 规则关联链测试（STEP-EXT-LEGAL-FULL-MATCH 步骤 19）。

覆盖三层：
  ① 关联表本身的**内部一致性**（双向索引互逆、确证条款必有正文、id 形态合法）；
  ② 读层的**边界与降级**（空 key / 不存在的规则 ⇒ 明确说明而非抛异常或伪造）；
  ③ **端到端接线**（规则目录 → 报告章 → 风险详情 → 材料层）真出字段。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def lm():
    from engine import legal_mapping
    return legal_mapping


@pytest.fixture(scope="module")
def le():
    from engine import legal_extras
    return legal_extras


class TestMappingTableIntegrity:
    """① 关联表内部一致性（数据自证，不依赖引擎）。"""

    def test_双向索引互逆(self, lm):
        """规则 → 条款 与 条款 → 规则 必须互逆（防两处索引各写一遍）。"""
        from collections import defaultdict
        fwd = defaultdict(set)
        for m in lm._doc().get("mappings") or []:               # noqa: SLF001
            if m.get("verified") and m.get("provision_id"):
                fwd[m["provision_id"]].add(m["rule_id"])
        rev = lm._doc().get("by_provision") or {}                # noqa: SLF001
        for pid, rules in fwd.items():
            assert pid in rev, "条款 %s 缺反向索引" % pid
            assert set(rev[pid]) == rules, "条款 %s 正反索引不一致" % pid

    def test_确证条款必有正文(self, lm):
        """已确证的条款**必须在正文库真有原文**（否则是假确证）。"""
        c = lm.coverage()
        assert c["provisions"] > 0, "关联表为空 ⇒ 步骤 19 无内容可接"
        assert c["with_content"] == c["provisions"], (
            "有确证条款查不到正文：%s" % c["missing_content"][:5])

    def test_条款id与法短码前缀一致(self, lm):
        """`provision_id` 去掉尾部条号后必须等于 `law_code`（防生成器错位）。"""
        for m in lm._doc().get("mappings") or []:                # noqa: SLF001
            if not m.get("verified"):
                continue
            assert lm.law_code_of(m["provision_id"]) == m["law_code"], (
                "%s 的 provision_id(%s) 与 law_code(%s) 不一致"
                % (m["rule_id"], m["provision_id"], m["law_code"]))

    def test_未确证项必须写明原因(self, lm):
        """`unresolved` 每条必须带 `reason`（缺失如实，不得只有半条记录）。"""
        for u in lm._doc().get("unresolved") or []:              # noqa: SLF001
            assert str(u.get("reason") or "").strip(), "未确证项缺 reason：%s" % u


class TestReadLayerBoundary:
    """② 读层边界与降级。"""

    def test_空规则id返回空并说明(self, lm):
        got = lm.for_finding({})
        assert got["provisions"] == []
        assert got["note"], "空规则必须给出说明，不得静默返回空"

    def test_不存在规则不抛异常(self, lm):
        got = lm.for_finding({"rule_id": "RL-NOT-EXIST-000"})
        assert got["provisions"] == []
        assert "未登记" in got["note"]

    def test_law_code_of只剥尾部条号(self, le):
        """短码自身含 `-`（如 TAX-ADMIN-LAW）⇒ 只能剥尾部数字条号。"""
        assert le.law_code_of("TAX-ADMIN-LAW-063") == "TAX-ADMIN-LAW"
        assert le.law_code_of("VAT-LAW-028") == "VAT-LAW"
        assert le.law_code_of("") == ""

    def test_材料关联粒度必显式声明且自洽(self, le):
        """★ 粒度**三态**（2026-10-15 补采材料正文后升级）：`provision`/`law`/`none`。

        任何按条款取材料的接口都必须**显式声明粒度**，且与证据字段自洽 ——
        `provision` 级必须真有条款 ID；无条款级命中时如实退回 `law` 并说明。
        """
        pid = None
        for m in lm_doc_mappings():
            if m.get("verified"):
                pid = m["provision_id"]
                break
        if not pid:
            pytest.skip("关联表无可确证条款")
        got = le.for_provision(pid, limit=2)
        gran = got.get("granularity")
        assert gran in ("provision", "law", "none"), "粒度必须显式且在三态内，实得 %r" % gran
        # 自洽：声明条款级 ⇒ 返回的条目必须真带该条款 ID
        if gran == "provision":
            assert got.get("items"), "声明条款级却无条目"
            assert any(pid in (it.get("provision_ids") or []) for it in got["items"]), \
                "声明条款级，但返回条目里没有该条款 ID ⇒ 假条款级"
        # 两种粒度**都**不得被读成"适用本条"
        note = str(got.get("note") or "")
        assert ("不代表" in note or "不得" in note or "不等于" in note), \
            "粒度说明必须写清「不代表个案适用本条」"


def lm_doc_mappings():
    d = json.loads((ROOT / "config" / "legal_mappings.json").read_text(encoding="utf-8"))
    return d.get("mappings") or []


class TestEndToEndWiring:
    """③ 端到端：规则目录 / 报告 / 风险详情 真出字段。"""

    @staticmethod
    def _session():
        class _S:
            username = "test"
            is_admin = True
            user_id = 0

            def can_access_company(self, cid):                   # noqa: ANN001
                return True
        return _S()

    def test_规则目录详情带条款正文(self):
        from engine import rule_catalog as RC
        from engine import legal_mapping as LM
        rid = next((r["rule_id"] for r in RC.entries() if LM.provisions_of(r["rule_id"])), None)
        if rid is None:
            pytest.skip("无可确证条款的规则")
        got = RC.get(rid)
        assert got["legal_provisions"], "详情未附 legal_provisions"
        assert any(p.get("content") for p in got["legal_provisions"]), "条款未带正文"

    def test_报告法规依据章含条款id与已确证行(self):
        from engine import report_service as RSVC
        doc = RSVC.build_document(1, self._session(), view="full")
        sec = next((s for s in doc["sections"] if s.get("key") == "legal_basis"), None)
        assert sec is not None, "报告缺 legal_basis 章"
        tbl = next((b for b in sec["blocks"] if b.get("type") == "table"), None)
        assert tbl is not None, "法规依据章无表格"
        assert "条款ID" in tbl["columns"], "表未渲染条款 ID 列：%s" % tbl["columns"]
        assert any("已确证" in str(r[-1]) for r in tbl["rows"]), "无一条「已确证」行"

    def test_风险详情带条款与材料(self):
        from engine import risk_service as RSVC
        lst = RSVC.list_risks(1, self._session(), page=1, page_size=1)
        items = lst.get("items") or []
        if not items:
            pytest.skip("无风险发现数据")
        assert "legal_provision_ids" in items[0], "列表条目缺 legal_provision_ids"
        got = RSVC.get_risk(items[0].get("risk_no") or items[0].get("seq"), 1, self._session())
        assert "legal_basis" in got, "详情缺 legal_basis"
        assert "related_materials" in got, "详情缺 related_materials"
        # ★ 三态（2026-10-15）：优先条款级，无命中如实退回法规级；无条款可确证则为 none
        rm = got["related_materials"] or {}
        assert rm.get("granularity") in ("provision", "law", "none"), \
            "related_materials 粒度必须显式且在三态内，实得 %r" % rm.get("granularity")
        if rm.get("granularity") == "provision":
            assert rm.get("matched_provision_ids"), \
                "声明条款级却未给出命中的条款 ID ⇒ 无法复核"


class TestMaterialMatchingDiscipline:
    """材料关联的**纪律**：只认显式引用（本项目铁律）。"""

    def test_匹配方式只允许两类显式引用(self):
        d = json.loads((ROOT / "config" / "legal_materials.json").read_text(encoding="utf-8"))
        allowed = {"书名号引用", "全名提及"}
        bad = set()
        for m in d["materials"]:
            for h in m.get("matched_refs") or []:
                if h.get("matched_by") not in allowed:
                    bad.add(str(h.get("matched_by")))
        assert not bad, "出现非显式引用匹配方式：%s" % bad

    def test_未关联材料照样保留(self):
        """匹配不到法规的材料**不得丢弃**（不静默丢数据）。"""
        d = json.loads((ROOT / "config" / "legal_materials.json").read_text(encoding="utf-8"))
        unlinked = [m for m in d["materials"] if not m.get("related_law_codes")]
        assert len(unlinked) == d["counts"]["unlinked"]

    def test_实施细则不被截成母法(self):
        """★ 实测踩坑：`全名提及` 曾把「…征管法**实施细则**」截成母法 ⇒ 多报一部法。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_gen_legal_materials", str(ROOT / "scripts" / "_gen_legal_materials.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        idx = mod.load_alias_index()
        got = mod.match_laws(
            "按照《中华人民共和国税收征收管理法实施细则》第九十八条处理", idx)
        codes = [h["law_code"] for h in got]
        assert "TAX-ADMIN-LAW-REG" in codes, "未识别实施细则：%s" % codes
        assert "TAX-ADMIN-LAW" not in codes, "实施细则被误报为母法：%s" % codes
