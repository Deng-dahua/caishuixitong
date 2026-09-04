"""行业门类门槛 + 原材料判定 + 服务费剔除（修复 VR023 加价倍数误报）。

回归缺陷（用户 2026-09-04 报告 company 1 深圳海更数字传媒）：
报告误报「进项原材料及生产物资 317,345.27 元、销项成品 6,636,800.57 元、加价倍数 20.91 倍」——
根因：① 广告传媒（服务业）被套制造业「进销物耗投入产出比」规则；② "广告发**布**费"的
"布"字被子串关键词误中成纺织原材料；③ 服务费发票（税码 3 开头）被当成"货物/成品"。
"""
import unittest

from engine.verified_rule_engine import (
    _is_raw_material_goods, _scan_material_output_ratio,
    _industry_to_gate, _spec_applies_to_entity,
)


class TestRawMaterialGoods(unittest.TestCase):
    """原材料判定：税码 3 开头=服务剔除；类别前缀匹配根除子串误中。"""

    def test_advertising_fee_not_raw_material(self):
        # "广告发**布**费" 含"布"字，但税码 3 开头=服务，且类别是"广告服务"不含材料词
        self.assertFalse(_is_raw_material_goods(
            {"goods": "*广告服务*广告发布费", "tax_code": "3070101010000000000", "amount": 350000}))

    def test_textile_goods_is_raw_material(self):
        self.assertTrue(_is_raw_material_goods(
            {"goods": "*纺织产品*针织布", "tax_code": "1040105070000000000", "amount": 100}))

    def test_service_without_taxcode_still_rejected(self):
        # 无税码但品名含服务提示词 → 仍判服务
        self.assertFalse(_is_raw_material_goods(
            {"goods": "*现代服务*咨询服务费", "amount": 50000}))

    def test_bare_material_keyword_with_goods_taxcode(self):
        # 裸品名"坯布"，税码 1 开头（货物）→ 命中兜底关键词
        self.assertTrue(_is_raw_material_goods(
            {"goods": "坯布", "tax_code": "1040000000000000000", "amount": 100}))

    def test_insurance_service_not_raw_material(self):
        # "航空铁路意外险"含"铁"，但税码 3 开头（保险服务）→ 剔除
        self.assertFalse(_is_raw_material_goods(
            {"goods": "*保险服务*意外-航空铁路意外", "tax_code": "3060101010000000000", "amount": 73}))


class TestMaterialOutputRatioIndustryGate(unittest.TestCase):
    """VR023 进销物耗投入产出比：服务业门槛 + 服务费剔除 + 制造业仍触发。"""

    def _spec(self):
        return {"id": "VR023", "required_sources": ["sal_invs", "pur_invs"],
                "industries": ["A", "B", "C", "D", "F", "G", "H", "Q"]}

    def test_service_company_skipped(self):
        data = {
            "target_entity": {"biz_model": "服务业", "industry": "广告传媒"},
            "sal_invs": [{"goods": "*广告服务*广告发布费", "tax_code": "3070", "amount": 6636800}],
            "pur_invs": [{"goods": "*广告服务*广告发布费", "tax_code": "3070", "amount": 317345}],
        }
        self.assertEqual(_scan_material_output_ratio(data, self._spec()), [])

    def test_service_dominant_data_skipped_even_without_biz_model(self):
        # biz_model 识别失败时，销项 >90% 是服务费 → 数据特征兜底跳过
        data = {
            "target_entity": {"biz_model": "", "industry": ""},
            "sal_invs": [{"goods": "*现代服务*服务费", "tax_code": "3040", "amount": 6636800}],
            "pur_invs": [{"goods": "*现代服务*服务费", "tax_code": "3040", "amount": 317345}],
        }
        self.assertEqual(_scan_material_output_ratio(data, self._spec()), [])

    def test_manufacturing_still_triggers(self):
        # 真制造业：针织布采购 100 → 销售 2000，加价 20 倍 → 仍应触发
        data = {
            "target_entity": {"biz_model": "制造业", "industry": "纺织制造"},
            "pur_invs": [{"goods": "*纺织产品*针织布", "tax_code": "1040", "amount": 100}],
            "sal_invs": [{"goods": "*纺织产品*针织布", "tax_code": "1040", "amount": 2000}],
        }
        r = _scan_material_output_ratio(data, self._spec())
        self.assertEqual(len(r), 1)
        self.assertIn("加价倍数", r[0]["detail"])


class TestIndustryGate(unittest.TestCase):
    """行业名 → GB/T 门类映射 + 规则行业门槛判定。"""

    def test_industry_to_gate(self):
        self.assertEqual(_industry_to_gate("广告传媒", ""), "L")
        self.assertEqual(_industry_to_gate("纺织制造", ""), "C")
        self.assertEqual(_industry_to_gate("食品加工", ""), "C")
        self.assertEqual(_industry_to_gate("餐饮", ""), "H")
        self.assertEqual(_industry_to_gate("", "贸易业"), "F")
        self.assertEqual(_industry_to_gate("", "服务业"), "L")

    def test_spec_applies_service_excluded_for_manufacturing_rule(self):
        # VR023 industries 不含 L，广告传媒（服务业→L）应被排除
        spec = {"industries": ["A", "B", "C", "D", "F", "G", "H", "Q"]}
        self.assertFalse(_spec_applies_to_entity(
            spec, {"industry": "广告传媒", "biz_model": "服务业"}))
        self.assertTrue(_spec_applies_to_entity(
            spec, {"industry": "纺织制造", "biz_model": "制造业"}))

    def test_spec_applies_unknown_industry_conservative(self):
        # 行业无法判定 → 保守返回 True（不误杀）
        spec = {"industries": ["A", "B", "C", "D", "F", "G", "H", "Q"]}
        self.assertTrue(_spec_applies_to_entity(spec, {"industry": "", "biz_model": ""}))

    def test_spec_all_always_applies(self):
        self.assertTrue(_spec_applies_to_entity({"industries": ["ALL"]}, {}))


if __name__ == "__main__":
    unittest.main()