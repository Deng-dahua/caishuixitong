# -*- coding: utf-8 -*-
"""Task 460/461 接线固化测试：6 条义务红线 + 3 条费义务 + 20 条漂移资料。

锁死「单一权威来源」接线，防止未来改动悄无声息地破坏：
  - REDLINES 权威计数 = 80
  - 6 条新义务红线存在、要件/论证完整、domain 在 DOMAIN_ORDER
  - gap_tax_obligations.SPECS 的 redline_id 全部映射到真实红线
  - 20 条 sup_* 补充自证资料同时在识别表与报告分类表登记
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.tax_redlines import REDLINES, get_redline, DOMAIN_ORDER
from engine import gap_tax_obligations as gap
from engine.material_recognition import _SUPPLEMENTARY_RECOGNITION
from engine.enterprise_report import _DOC_TYPE_TO_CATEGORY

NEW_REDLINE_IDS = [
    "RL-SPT-017",  # 文化事业建设费
    "RL-SPT-018",  # 车辆购置税
    "RL-SPT-014",  # 耕地占用税
    "RL-SPT-015",  # 烟叶税
    "RL-SPT-016",  # 船舶吨税
    "RL-VAT-013",  # 增值税留抵退税
    "RL-OTH-007",  # 营业账簿（资金账簿）印花税
]

NEW_MATERIAL_DTS = [
    "sup_farmland_approval", "sup_farmland_area", "sup_vehicle_fixed_asset",
    "sup_land_transfer_contract", "sup_vat_decl_retention", "sup_ad_ent_ledger",
    "sup_tobacco_amount", "sup_culture_decl", "sup_vehicle_invoice",
    "sup_tobacco_ledger", "sup_tobacco_tax_decl", "sup_retention_approval",
    "sup_farmland_tax_decl", "sup_ship_ton_cert", "sup_ship_reg", "sup_ship_entry",
    "sup_vehicle_reg_cert", "sup_vehicle_purchase_cert", "sup_inout_bank_flow",
    "sup_input_invoice_detail",
]

FEE_OBLIGATION_TOPICS = {"残疾人就业保障金", "水利建设基金", "工会经费"}


class ObligationRedlineWiringTests(unittest.TestCase):
    def test_authoritative_redline_count_is_81(self):
        # 权威计数必须实时等于 81（74 原 + 6 新义务红线 + 1 营业账簿印花税），杜绝硬编码漂移
        self.assertEqual(len(REDLINES), 81)

    def test_six_new_redlines_exist_and_well_formed(self):
        for rid in NEW_REDLINE_IDS:
            rl = get_redline(rid)
            self.assertIsNotNone(rl, f"{rid} 缺失")
            consts = rl.get("constituents") or []
            self.assertGreaterEqual(len(consts), 3, f"{rid} 构成要件过少")
            self.assertTrue(rl.get("justifications") or rl.get("justification"),
                            f"{rid} 缺论证/出罪情形")
            self.assertIn(rl.get("domain"), DOMAIN_ORDER,
                          f"{rid} domain={rl.get('domain')} 不在 DOMAIN_ORDER")

    def test_no_redline_id_collision(self):
        ids = [r["id"] for r in REDLINES]
        self.assertEqual(len(ids), len(set(ids)), "REDLINES 存在重复 id")

    def test_gap_specs_redline_id_maps_to_real_redline(self):
        for spec in gap.SPECS:
            rid = spec.get("redline_id")
            if not rid:
                continue
            rl = get_redline(rid)
            self.assertIsNotNone(rl, f"SPECS {spec.get('topic')} 的 redline_id={rid} 无对应红线")
            self.assertIn(rl.get("domain"), DOMAIN_ORDER)

    def test_fee_obligations_present_as_report_level(self):
        topics = {s.get("topic") for s in gap.SPECS}
        for kw in FEE_OBLIGATION_TOPICS:
            self.assertTrue(any(kw in t for t in topics),
                            f"费义务 {kw} 未登记到 gap SPECS")

    def test_twenty_materials_registered_in_both_tables(self):
        # _SUPPLEMENTARY_RECOGNITION 以资料名为键，doc_type 在值内
        rec_dts = {v["doc_type"] for v in _SUPPLEMENTARY_RECOGNITION.values()}
        for dt in NEW_MATERIAL_DTS:
            self.assertIn(dt, rec_dts,
                          f"{dt} 未登记到补充自证资料识别表")
            self.assertIn(dt, _DOC_TYPE_TO_CATEGORY,
                          f"{dt} 未并入报告资料分类表（运行时 closure 失效）")


if __name__ == "__main__":
    unittest.main()
