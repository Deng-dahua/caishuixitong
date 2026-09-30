# -*- coding: utf-8 -*-
"""接线固化测试：义务红线 + 印花税税目 + 资本弱化 + 费用义务 + 漂移资料。

锁死「单一权威来源」接线，防止未来改动悄无声息地破坏：
  - REDLINES 权威计数 = 91
  - 16 条新增红线存在、要件/论证完整、domain 在 DOMAIN_ORDER
  - gap/special SPECS 的 redline_id 全部映射到真实红线（含 3 条费类义务）
  - 32 条 sup_* 补充自证资料同时在识别表与报告分类表登记
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
    "RL-OTH-008",  # 产权转移书据印花税
    "RL-OTH-009",  # 借款合同印花税
    "RL-OTH-010",  # 财产租赁合同印花税
    "RL-OTH-011",  # 财产保险合同印花税
    "RL-CIT-010",  # 资本弱化（关联债资比）
    "RL-SPT-019",  # 残疾人就业保障金
    "RL-SPT-020",  # 水利建设基金
    "RL-SPT-021",  # 工会经费
    "RL-VAT-014",  # 异地预缴增值税
    "RL-VAT-015",  # 农产品收购发票进项真实性
]

NEW_MATERIAL_DTS = [
    "sup_farmland_approval", "sup_farmland_area", "sup_vehicle_fixed_asset",
    "sup_land_transfer_contract", "sup_vat_decl_retention", "sup_ad_ent_ledger",
    "sup_tobacco_amount", "sup_culture_decl", "sup_vehicle_invoice",
    "sup_tobacco_ledger", "sup_tobacco_tax_decl", "sup_retention_approval",
    "sup_farmland_tax_decl", "sup_ship_ton_cert", "sup_ship_reg", "sup_ship_entry",
    "sup_vehicle_reg_cert", "sup_vehicle_purchase_cert", "sup_inout_bank_flow",
    "sup_input_invoice_detail",
    "sup_equity_transfer_contract", "sup_realestate_transfer_contract",
    "sup_property_insurance_contract", "sup_interest_expense_ledger",
    "sup_contemporaneous_docs",
    # 费类义务（RL-SPT-019/020/021）
    "sup_ldf_decl", "sup_ldf_exempt", "sup_water_fund_decl", "sup_payment_voucher",
    "sup_union_payment", "sup_union_receipt", "sup_union_org_proof",
    # 场景红线（RL-VAT-014/015）
    "sup_vat_prepay_decl", "sup_agri_purchase_invoice", "sup_purchase_ledger",
]

FEE_OBLIGATION_TOPICS = {"残疾人就业保障金", "水利建设基金", "工会经费"}


class ObligationRedlineWiringTests(unittest.TestCase):
    def test_authoritative_redline_count_is_89(self):
        # 权威计数必须实时等于 91（74 原 + 6 义务红线 + 1 营业账簿 + 4 印花税合同类
        #   + 1 资本弱化 + 3 费类义务 + 2 场景红线(异地预缴/农产品收购发票)），杜绝硬编码漂移
        self.assertEqual(len(REDLINES), 91)

    def test_fourteen_new_redlines_exist_and_well_formed(self):
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

    def test_fee_obligations_wired_to_redlines(self):
        """3 条费类义务（残保金/水利基金/工会经费）必须已登记 redline_id 并联通真实红线。"""
        topics = {s.get("topic"): s for s in gap.SPECS}
        for kw in FEE_OBLIGATION_TOPICS:
            spec = next((s for t, s in topics.items() if kw in t), None)
            self.assertIsNotNone(spec, f"费义务 {kw} 未登记到 gap SPECS")
            rid = spec.get("redline_id")
            self.assertTrue(rid, f"费义务 {kw} 未登记 redline_id（仍为报告级线索）")
            self.assertIsNotNone(get_redline(rid), f"费义务 {kw} 的 redline_id={rid} 无对应红线")

    def test_all_supplementary_materials_registered_in_both_tables(self):
        # _SUPPLEMENTARY_RECOGNITION 以资料名为键，doc_type 在值内
        rec_dts = {v["doc_type"] for v in _SUPPLEMENTARY_RECOGNITION.values()}
        for dt in NEW_MATERIAL_DTS:
            self.assertIn(dt, rec_dts,
                          f"{dt} 未登记到补充自证资料识别表")
            self.assertIn(dt, _DOC_TYPE_TO_CATEGORY,
                          f"{dt} 未并入报告资料分类表（运行时 closure 失效）")


if __name__ == "__main__":
    unittest.main()
