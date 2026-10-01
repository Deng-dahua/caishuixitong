"""特定/专项风险红线探测器单测：零误报 + 命中即产出 + 归属有效 + 打封印标。"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.special_redline_detectors import run_special_redline_detection, SPECS
from engine import tax_redlines


class SpecialRedlineDetectorTests(unittest.TestCase):
    def test_empty_or_blank_data_produces_no_findings(self):
        """零数据必须零误报。"""
        self.assertEqual(run_special_redline_detection({}), [])
        self.assertEqual(run_special_redline_detection({"vouchers": [], "bank_txs": []}), [])
        self.assertEqual(
            run_special_redline_detection({"vouchers": [{"摘要": "正常业务", "金额": 1}]}),
            [],
        )

    def test_signals_produce_findings_with_valid_redline_id(self):
        data = {
            "vouchers": [{"摘要": "暂估入库 原材料", "科目": "原材料", "金额": 100}],
            "bank_txs": [{"摘要": "向非居民企业支付特许权使用费", "付款": 5000}],
            "balances": [{"科目名称": "其他应付款", "期末贷方": 80000}],
        }
        found = run_special_redline_detection(data)
        ids = {f["redline_id"] for f in found}
        self.assertIn("RL-COST-001", ids)
        self.assertIn("RL-SPT-006", ids)
        self.assertIn("RL-INC-004", ids)
        for f in found:
            self.assertIn(f["redline_id"], {s["redline_id"] for s in SPECS})
            self.assertTrue(f.get("_scenario_governed"), "必须打封印标否则被 seal 丢弃")
            self.assertIn("待核", f["type"])

    def test_declared_keyword_suppresses_false_positive(self):
        """已见对应税种申报记录 → 不再置疑。"""
        data = {
            "vouchers": [{"科目": "房屋建筑物", "金额": 1}],
            "tax_declarations": [{"税种": "房产税", "金额": 100}],
        }
        found = run_special_redline_detection(data)
        self.assertNotIn("RL-OTH-002", {f["redline_id"] for f in found})

    def test_forex_goods_import_not_false_positive(self):
        """进口付汇（美元）≠ 向非居民支付境内所得，不应误报源泉扣缴义务。"""
        data = {
            "bank_txs": [{"摘要": "境外支付货款 付汇 USD", "付款": 9000}],
            "pur_invs": [{"品名": "进口原材料", "价税合计": 9000}],
        }
        ids = {f["redline_id"] for f in run_special_redline_detection(data)}
        self.assertNotIn("RL-SPT-006", ids)

    def test_every_spec_declares_existing_redline(self):
        valid = {r["id"] for r in tax_redlines.REDLINES}
        self.assertTrue(SPECS, "SPECS 不应为空")
        for s in SPECS:
            self.assertIn(s["redline_id"], valid, f"{s['redline_id']} 不是有效红线 id")
            self.assertTrue(s.get("signals"), f"{s['redline_id']} 缺少 signals")
            self.assertTrue(s.get("needs"), f"{s['redline_id']} 缺少 needs(需补资料)")


class EquityTransferIITTests(unittest.TestCase):
    """RL-SPT-012 股权转让未申报个人所得税：专用探测器（表驱动 SPECS 之外的一条）。"""

    def _found(self, data):
        return {f["redline_id"]: f for f in run_special_redline_detection(data)}

    def test_fires_on_equity_change_signal(self):
        data = {
            "bank_txs": [{"summary": "股权变更服务费", "amount": "1000"}],
            "contracts": [{"name": "股权转让协议"}],
        }
        f = self._found(data).get("RL-SPT-012")
        self.assertIsNotNone(f, "Real production detector for RL-SPT-012 must fire on equity transfer signal")
        self.assertEqual(f["level"], "待核验")
        self.assertEqual(f["tax_type"], "个人所得税")
        self.assertTrue(f.get("_scenario_governed"), "必须打封印标否则被 seal 丢弃")
        self.assertTrue(f.get("_unconfirmed"), "不得自动定性")
        self.assertTrue(f["needs_material"])

    def test_no_finding_without_equity_signal(self):
        data = {"bank_txs": [{"summary": "支付货款", "amount": "1000"}],
                "vouchers": [{"summary": "计提折旧"}]}
        self.assertNotIn("RL-SPT-012", self._found(data))

    def test_tax_paid_evidence_suppresses(self):
        """出现股权转让完税凭证 → 视为可能已申报，不得置疑。"""
        data = {
            "contracts": [{"name": "股权转让协议"}],
            "tax_declarations": [{"summary": "股权转让个税完税凭证"}],
        }
        self.assertNotIn("RL-SPT-012", self._found(data))

    def test_reports_count_but_not_amount(self):
        """★ 不得把银行手续费当成"股权转让涉及金额"报出去（缺数不得编）。"""
        data = {"bank_txs": [{"summary": "股权变更服务费", "amount": "1000"}],
                "contracts": [{"name": "股权转让协议"}]}
        f = self._found(data)["RL-SPT-012"]
        blob = json.dumps(f, ensure_ascii=False)
        self.assertIn("相关记录", blob)
        self.assertNotIn("涉及金额", blob)
        # 不作试算必须**写明**（缺数不得编），但不能报出数字
        self.assertIn("不作税额试算", f["detail"])
        self.assertNotIn("\u91d1\u989d", blob)

    def test_extra_detectors_are_invoked_by_runner(self):
        """★ 运行器必须真的遍历 _EXTRA_DETECTORS，否则专用探测器是死代码。"""
        import engine.special_redline_detectors as srd

        called = []

        def _sentinel(data, texts=None, pipeline_log=None):
            called.append(1)
            return []

        old = srd._EXTRA_DETECTORS
        srd._EXTRA_DETECTORS = (_sentinel,)
        try:
            srd.run_special_redline_detection({"vouchers": []})
        finally:
            srd._EXTRA_DETECTORS = old
        self.assertTrue(called, "run_special_redline_detection 未调用 _EXTRA_DETECTORS")

    def test_rlspt012_declared_in_production_source(self):
        """覆盖度审计 `_scan_ids` 按 `redline_id…<id>` 字面量扫描生产检测器，须扫得到。"""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        src = open(os.path.join(root, "engine", "special_redline_detectors.py"),
                   encoding="utf-8").read()
        self.assertRegex(src, r'redline_id[^\n]{0,8}?(RL-SPT-012)')


if __name__ == "__main__":
    unittest.main()
