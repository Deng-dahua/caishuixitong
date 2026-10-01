# -*- coding: utf-8 -*-
"""向 tests/test_industry_resolver.py 追加 TestReassessIndustry 类（含反向验证）。

测试文件是 CRLF 既有文件：追加块统一 \r\n（bare-LF 必须 0）。
幂等：类已存在则跳过。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "tests", "test_industry_resolver.py")
SENTINEL = "class TestReassessIndustry("

BLOCK = u'''

class TestReassessIndustry(unittest.TestCase):
    """行业「随资料再判读」（reassess_industry）——资料收齐后回头重判行业。

    设计立场（用户观点，2026-10-02）：「行业判断应随系统接收到的资料和信息，
    经重新判读后再次确认或变更」。
    但**只能推翻、不能凭空定**：决策三态 change / keep / insufficient，绝不猜。
    """

    VALID_DECISIONS = ("change", "keep", "insufficient")

    # ——— 正向：什么情况下变更 ———
    def test_fallback_overturned_by_two_evidence_routes(self):
        r = reassess_industry(
            current_industry="商贸",
            material_hints=["广告设计合同_2025.docx"],
            contract_text="甲方委托乙方进行广告创意设计及媒体发布",
        )
        self.assertEqual(r["decision"], "change")
        self.assertEqual(r["industry"], "广告传媒")

    def test_fallback_overturned_by_single_route(self):
        """购销兜底本就低置信，单路弱证据即可推翻（真实场景：先判商贸、后凭合同取证）。"""
        r = reassess_industry(
            current_industry="商贸",
            purchase_goods=["*广告服务*广告费", "*现代服务*广告策划"],
        )
        self.assertEqual(r["decision"], "change")
        self.assertEqual(r["industry"], "广告传媒")

    def test_high_authority_overturned_by_two_routes(self):
        """高权威口径（销项品名/外部工商）需要 ≥2 路证据同时指向新行业才变更。"""
        r = reassess_industry(
            current_industry="信息技术",
            purchase_goods=["*信息技术服务*运维服务"],
            material_hints=["运维服务合同.docx"],
            current_source="销项发票品名",
        )
        self.assertEqual(r["decision"], "change")
        self.assertEqual(r["industry"], "信息技术")

    def test_high_authority_not_overturned_by_single_route(self):
        r = reassess_industry(
            current_industry="信息技术",
            material_hints=["广告设计合同.docx"],
            current_source="销项发票品名",
        )
        self.assertEqual(r["decision"], "keep")
        self.assertEqual(r["industry"], "信息技术")

    def test_no_evidence_is_insufficient_not_change(self):
        r = reassess_industry(current_industry="广告传媒", current_source="销项发票品名")
        self.assertEqual(r["decision"], "insufficient")
        self.assertEqual(r["industry"], "广告传媒", "无证据时必须保持原口径")

    def test_commodity_names_never_count_as_industry(self):
        """铁律 R1：商品/物料名不是行业 —— 买饲料不能据此把行业判成任何服务业态。"""
        r = reassess_industry(
            current_industry="农业生产",
            purchase_goods=["饲料", "宠物食品"],
            material_hints=["饲料采购单.docx"],
            current_source="销项发票品名",
        )
        self.assertIn(r["decision"], ("keep", "insufficient"))
        self.assertEqual(r["industry"], "农业生产")

    def test_tie_has_no_consensus(self):
        r = reassess_industry(
            current_industry="商贸",
            material_hints=["广告设计合同.docx"],
            contract_text="设计服务费结算单 设计劳务",
        )
        self.assertEqual(r["decision"], "keep")
        self.assertEqual(r["industry"], "商贸", "并票＝没有共识，不得挑一个")

    def test_same_industry_keeps(self):
        r = reassess_industry(
            current_industry="广告传媒",
            material_hints=["广告设计合同.docx"],
            purchase_goods=["*广告服务*广告费"],
            current_source="销项发票品名",
        )
        self.assertEqual(r["decision"], "keep")
        self.assertEqual(r["industry"], "广告传媒")

    def test_decision_always_valid(self):
        for kw in (
            dict(current_industry="商贸", material_hints=["广告设计合同.docx"]),
            dict(current_industry="信息技术", current_source="销项发票品名"),
            dict(current_industry="", purchase_goods=["饲料"]),
        ):
            self.assertIn(reassess_industry(**kw)["decision"], self.VALID_DECISIONS)

    def test_changes_are_logged(self):
        log = []
        reassess_industry(current_industry="商贸",
                          material_hints=["广告设计合同.docx"],
                          pipeline_log=log)
        self.assertTrue(any("行业口径变更" in x for x in log), "行业变更必须留痕")

    # ——— 反向验证：证明每条守卫真的在起作用（不是摆设） ———
    def test_reverse_evidence_hunter_disabled(self):
        """摘掉行业线索抽取，两路证据的场景必须无法变更 —— 证明判定确实由证据驱动。"""
        with _mock.patch("engine.industry_resolver.industry_hints_from_text", return_value={}):
            r = reassess_industry(current_industry="商贸",
                                  material_hints=["广告设计合同.docx"],
                                  contract_text="广告创意设计及媒体发布")
        self.assertNotEqual(r["decision"], "change",
                            "没有证据还能变更 = 凭空定行业，违背『只能推翻不能凭空定』")

    def test_reverse_pipeline_call_site_wired(self):
        """源码级防回退：主链路必须真的调用再判读，否则本文件测的是死代码。"""
        import inspect
        from engine import pipeline as pl
        self.assertTrue(
            hasattr(pl, "reassess_industry") or
            "reassess_industry" in inspect.getsource(pl).replace("as _reassess", ""),
            "pipeline.py 不再调用 reassess_industry（行业又变回一次性定死）")

    def test_reverse_fallback_set_nonempty(self):
        from engine import industry_resolver as ir
        self.assertTrue(getattr(ir, "_TRADE_FALLBACK_INDUSTRIES", ()),
                        "购销兜底口径表为空 → 兜底口径会被当成具体行业，再判读将失去分寸")
'''
IMPORTS_NOTE = u'''

# 「行业随资料再判读」相关测试辅助
import unittest as _unittest
from unittest import mock as _mock   # noqa: E402

from engine.industry_resolver import (  # noqa: E402
    reassess_industry,
)
'''


def main():
    with io.open(TARGET, "r", encoding="utf-8", newline="") as f:
        src = f.read()
    if SENTINEL in src:
        print("SKIP: already appended")
        return 0
    # 测试文件是 CRLF 既有文件：块必须整体转成 CRLF，bare-LF 必须为 0
    block = (BLOCK.lstrip("\n").rstrip("\n") + "\n").replace("\n", "\r\n")
    src = src.rstrip("\r\n") + "\r\n\r\n" + block
    with io.open(TARGET, "w", encoding="utf-8", newline="") as f:
        f.write(src)
    raw = io.open(TARGET, "rb").read()
    print("OK: appended TestReassessIndustry | CRLF=%d bareLF=%d"
          % (raw.count(b"\r\n"), raw.replace(b"\r\n", b"").count(b"\n")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
