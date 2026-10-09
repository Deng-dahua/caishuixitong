# -*- coding: utf-8 -*-
"""**要件数据源必须"可达"**（2026-10-06）。

背景：红线 `RL-VAT-007` 要件③「红冲无对应退货单、折让协议等合法事由」的数据源含
「拒收证明」，而它既不在 15 类必查、也未被任何补充类别登记
⇒ `_match_material` 恒判「缺失」⇒ 该要件**永远 not_checked**
（此前用一张 `_ACK_UNREACHABLE` 豁免表把它降为 WARN —— 那是**永久豁口**）。

根因不是"资料拿不到"，而是**没登记**。修法：在 `material_recognition._SUPP_ENTRIES`
登记为**独立补充类别**（新增一类真资料），**不是**硬映射到既存 15 类
（后者会把事实上没拿到的资料说成「已有」，正是本项目明令禁止的）。
"""
from __future__ import annotations


class TestRejectCertRegistered:
    """「拒收证明」已登记为独立补充类别，且三态语义正确（不冒充「已有」）。"""

    def test_registered_as_supplementary(self):
        from engine.material_recognition import (
            _SUPPLEMENTARY_CATEGORIES, _SUPPLEMENTARY_RECOGNITION)
        assert "拒收证明" in _SUPPLEMENTARY_CATEGORIES
        info = _SUPPLEMENTARY_RECOGNITION.get("拒收证明") or {}
        assert info.get("doc_type") == "sup_reject_cert", info
        # 不得把它并回某个既存 15 类（那才是"硬映射冒充已有"）
        assert not (info.get("extra_cats") or ()), \
            "「拒收证明」不得并入既存 15 类（会把没拿到的资料说成已有）"

    def test_doc_type_mapping_generated(self):
        from engine.enterprise_report import _DOC_TYPE_TO_CATEGORY
        assert _DOC_TYPE_TO_CATEGORY.get("sup_reject_cert") == ("拒收证明",)

    def test_recognized_from_filename(self):
        from engine.material_recognition import _recognize_supplementary
        for fn in ("客户拒收单.pdf", "验收不合格通知.docx", "拒收证明.xlsx",
                   "拒收货物通知.pdf"):
            assert _recognize_supplementary(fn) == "sup_reject_cert", fn

    def test_three_state_semantics(self):
        """什么都没提供 → 缺失（诚实）；真提供了 → 已有。绝不无条件判已有。"""
        from engine.evidence_chain import _match_material as mm
        assert (mm("拒收证明", "", []) or {}).get("status") == "缺失"
        assert (mm("拒收证明", "", ["银行流水"]) or {}).get("status") == "缺失"
        assert (mm("拒收证明", "", ["拒收证明"]) or {}).get("status") == "已有"

    def test_all_constituent_sources_are_reachable(self):
        """全库要件数据源必须**可达**（不得再有"声明了但永远拿不到"的名字）。

        这是原 WARN 的根因闸门化：豁免表已清空，任何新增的不可达名字都应被它拦下。
        """
        from engine.enterprise_report import _DOC_TYPE_TO_CATEGORY
        from engine.evidence_chain import _match_material as mm
        from engine.tax_redlines import REDLINES
        cats = set()
        for v in _DOC_TYPE_TO_CATEGORY.values():
            cats.update(str(x) for x in (v if isinstance(v, (tuple, list)) else (v,)))
        _legal = sorted(cats)
        bad = []
        for r in REDLINES:
            for i, src in enumerate(r.get("constituent_sources") or [], 1):
                for n in str(src).replace("，", "、").replace(",", "、").split("、"):
                    n = n.strip()
                    if not n:
                        continue
                    if ((mm(n, "", _legal) or {}).get("status") or "缺失") == "缺失":
                        bad.append("%s 第%d条「%s」" % (r.get("id"), i, n))
        assert not bad, "要件数据源永远拿不到（该要件恒不计入认定）：%s" % bad[:6]
