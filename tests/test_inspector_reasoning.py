"""税务稽查专家研判内核——像人类专家一样思考的回归测试。

覆盖：
- 行业基准匹配（精确/模糊/biz_model兜底/default）
- 企业画像（规模判断、行业空时从名称推断）
- 行业对标（毛利率偏离方向的专家判断：显著偏低/偏高/合理/购销倒挂）
- 重点线索分级（行业敏感性：服务业供应商地域分散降权 + opposing 行业化）
- 核查路线（证据硬优先 → 实质交易 → 数据质量）
"""
import unittest

from engine.inspector_reasoning import (
    _match_benchmark, _build_entity_profile, _build_industry_benchmark,
    _build_key_clues, _build_investigation_route, build_inspector_reasoning,
)


class TestMatchBenchmark(unittest.TestCase):
    def test_exact_industry(self):
        name, bench = _match_benchmark("广告传媒", "服务业")
        self.assertEqual(name, "广告传媒")
        self.assertIn("毛利率", bench)

    def test_fuzzy_industry(self):
        name, _ = _match_benchmark("海更数字传媒", "服务业", entity_name="深圳海更数字传媒有限公司")
        self.assertIsNotNone(name)

    def test_biz_model_fallback(self):
        name, _ = _match_benchmark("", "制造业")
        self.assertEqual(name, "制造业")

    def test_service_name_inference(self):
        # 餐饮 → 住宿餐饮粗粒度
        name, _ = _match_benchmark("", "服务业", entity_name="北京潘祥记餐饮有限公司")
        self.assertIn("餐饮", name)

    def test_default_fallback(self):
        name, _ = _match_benchmark("", "未知模式")
        self.assertIsNotNone(name)


class TestEntityProfile(unittest.TestCase):
    def test_scale_and_nature(self):
        te = {"name": "某传媒", "industry": "广告传媒", "biz_model": "服务业", "registered_capital": "100万"}
        fs = {"total_sales": 6636800, "total_purchases": 5757171}
        profile, text = _build_entity_profile(te, fs, {})
        self.assertEqual(profile["scale"], "小型")
        self.assertIn("轻资产", profile["nature"])
        self.assertIn("广告传媒", text)

    def test_empty_industry_inferred_from_name(self):
        te = {"name": "北京潘祥记餐饮有限公司", "industry": "", "biz_model": "服务业"}
        profile, text = _build_entity_profile(te, {}, {})
        self.assertNotIn("未标注", profile["industry"])


class TestIndustryBenchmark(unittest.TestCase):
    def test_low_margin(self):
        bench, text = _build_industry_benchmark("广告传媒", "服务业", {"gross_margin_pct": 13.3})
        obs = bench["observations"]
        self.assertEqual(obs[0]["direction"], "显著偏低")
        self.assertIn("隐匿收入", obs[0]["why"])

    def test_normal_margin(self):
        bench, _ = _build_industry_benchmark("纺织制造", "制造业", {"gross_margin_pct": 15.0})
        self.assertEqual(bench["observations"][0]["direction"], "处于合理区间")

    def test_inverted_margin(self):
        # 毛利率为负 → 购销倒挂，而非普通"偏低"
        bench, _ = _build_industry_benchmark("食品加工", "制造业", {"gross_margin_pct": -5232.0})
        self.assertEqual(bench["observations"][0]["direction"], "购销倒挂")


class TestKeyClues(unittest.TestCase):
    def test_service_supplier_geo_opposing_industry_sensitive(self):
        findings = [{
            "type": "待核事实：供应商地域分布与购销集中度核验",
            "level": "中风险", "score": 5,
            "reasonable_explanations": ["原料产地集中或大宗采购"],
        }]
        clues = _build_key_clues(findings, "服务业")
        self.assertIn("广告投放", clues[0]["opposing"][0])
        self.assertNotIn("原料产地", clues[0]["opposing"])

    def test_manufacturing_keeps_original_opposing(self):
        findings = [{
            "type": "待核事实：供应商地域分布与购销集中度核验",
            "level": "中风险", "score": 5,
            "reasonable_explanations": ["原料产地集中或大宗采购"],
        }]
        clues = _build_key_clues(findings, "制造业")
        self.assertIn("原料产地", clues[0]["opposing"][0])

    def test_money_clues_ranked_first(self):
        findings = [
            {"type": "待核事实：现金、聚合支付与个人账户收款闭环", "level": "中风险", "score": 5},
            {"type": "待核事实：供应商地域分布", "level": "中风险", "score": 5},
        ]
        clues = _build_key_clues(findings, "服务业")
        self.assertEqual(clues[0]["tier"], "A")  # 资金线索排最前


class TestInvestigationRoute(unittest.TestCase):
    def test_route_order(self):
        clues = [
            {"type": "公私混同", "tier": "A", "weight": 9},
            {"type": "供应商地域", "tier": "B", "weight": 5},
            {"type": "借贷差额", "tier": "C", "weight": 2},
        ]
        route = _build_investigation_route(clues, "服务业")
        self.assertIn("第一步", route[0])
        self.assertIn("第二步", route[1])
        self.assertIn("第三步", route[2])


class TestBuildInspectorReasoning(unittest.TestCase):
    def test_full_reasoning(self):
        rd = {
            "target_entity": {"name": "深圳海更数字传媒", "industry": "广告传媒", "biz_model": "服务业"},
            "engine_status": {"financial_snapshot": {"total_sales": 6636800, "total_purchases": 5757171, "gross_margin_pct": 13.3}},
            "all_findings": [
                {"type": "待核事实：现金、聚合支付与个人账户收款闭环", "level": "中风险", "score": 5},
                {"type": "待核事实：工资、社保、用工身份与扣缴范围核验", "level": "中风险", "score": 5},
            ],
        }
        r = build_inspector_reasoning(rd)
        self.assertIn("企业画像", r["narrative"])
        self.assertIn("行业对标", r["narrative"])
        self.assertIn("核查路线", r["narrative"])
        self.assertEqual(r["entity_profile"]["scale"], "小型")


if __name__ == "__main__":
    unittest.main()