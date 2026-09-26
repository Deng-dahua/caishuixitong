"""行业口径统一解析器（engine/industry_resolver.py）回归测试。

═══════════════════════════════════════════════════════════════════════════════
测试的是**与行业无关的通用规则**，不针对任何具体行业写特例。
（用户指令：问题不只看表象，要解决根本原因，且方法须适用于所有行业与企业。）
═══════════════════════════════════════════════════════════════════════════════
覆盖：
  R1 不得用"商品/物料名"当行业 —— 经营范围先定业态
  R2 判定必须带来源与置信度；取不到明确输出"未确定"，不静默套默认档
  R3 多来源不一致时全部保留并记为冲突
  R4 阈值对标能自报口径（是否在基准库中、区间出自哪里）
  ⑤ 经营模式五分类：确定、不依赖字典顺序、具体业态优先于宽泛业态
  ⑥ 行业数据加载器**单一来源**（历史上有 3 份重复实现）
"""
import unittest

from engine.industry_resolver import (
    SRC_INVOICE, benchmark_keys, business_category, generalization_note,
    infer_from_goods, is_in_benchmark_base, load_industry_data, match_benchmark,
    normalize_industry_name, resolve_industry,
)


class TestCommodityNameNotIndustry(unittest.TestCase):
    """R1：经营范围里的商品名不得被当作行业（对任何商品品类都成立）。"""

    def test_trade_scope_never_yields_commodity_industry(self):
        # 纯购销经营范围（含两个商品品类 + 销售/零售），未出现制造类词
        scope = "日用百货销售;塑料制品销售;五金产品零售;橡胶制品销售"
        picked, _ = match_benchmark("", "", "", scope)
        for commodity in ("塑料制品", "橡胶制品", "五金加工", "金属加工"):
            self.assertNotEqual(picked, commodity,
                                f"购销型经营范围不应被判成制造/产品类行业：{commodity}")
        # 必须落到商贸口径
        self.assertIn("商贸", picked or "", f"应落到商贸口径，实际={picked}")

    def test_manufacturing_scope_may_yield_product_industry(self):
        # 出现"制造"才允许落到对应制造类基准（同样与具体品类无关）
        picked, bench = match_benchmark("", "", "", "塑料制品制造;塑料制品销售")
        self.assertEqual(picked, "塑料制品")
        self.assertIn("毛利率", bench)

    def test_trade_subdivision_by_wholesale_retail(self):
        self.assertIn("零售", match_benchmark("", "", "", "日用百货零售")[0] or "")
        self.assertIn("批发", match_benchmark("", "", "", "日用百货批发")[0] or "")


class TestMatchDeterminism(unittest.TestCase):
    """最长匹配：结果可解释，不依赖字典插入顺序。"""

    def test_longest_key_wins(self):
        # 同时含"商贸"与"商贸零售"，应取更具体的"商贸零售"
        picked, _ = match_benchmark("", "", "", "日用百货零售;商贸")
        self.assertEqual(picked, "商贸零售")

    def test_name_beats_scope(self):
        picked, _ = match_benchmark("", "", "北京某某餐饮服务有限公司", "日用百货销售")
        self.assertEqual(picked, "餐饮服务")

    def test_exact_industry_wins_first(self):
        for key in benchmark_keys()[:5]:
            self.assertEqual(match_benchmark(key, "", "", "无关文本")[0], key)


class TestResolveIndustry(unittest.TestCase):
    """R2/R3：来源、置信度、冲突。"""

    def test_unknown_is_explicit_not_silent_default(self):
        r = resolve_industry()
        self.assertEqual(r["industry"], "")
        self.assertTrue(r["unknown"])
        self.assertEqual(r["source"], "未确定")
        self.assertEqual(r["confidence"], "无")

    def test_every_resolution_carries_source_and_confidence(self):
        cases = [
            dict(registered_industry="商贸"),
            dict(company_name="某某科技服务有限公司"),
            dict(business_scope="餐饮服务;食品销售"),
            dict(sales_goods=["*广告服务*广告发布费"]),
            dict(biz_model="制造业"),
        ]
        for kw in cases:
            r = resolve_industry(**kw)
            self.assertTrue(r["source"], f"缺少来源: {kw}")
            self.assertTrue(r["confidence"], f"缺少置信度: {kw}")

    def test_conflict_between_registered_and_actual_is_recorded(self):
        r = resolve_industry(registered_industry="商贸",
                             sales_goods=["*广告服务*广告发布费"])
        self.assertIn("商贸", r["candidates"].values())
        # ★ 2026-09-26：销项发票金税分类「广告服务」会先归一到基准库键「广告传媒」，
        #   否则与基准库字面不符 → 下游对标匹配不到 → 回退经营范围（真事故）。
        self.assertIn("广告传媒", r["candidates"].values())
        self.assertTrue(r["conflicts"], "登记口径≠实际口径时应记录冲突")
        # 实际经营口径（销项品名）权威度高于登记口径
        self.assertEqual(r["industry"], "广告传媒")
        self.assertEqual(r["source"], SRC_INVOICE)

    def test_sales_invoice_outranks_registered_and_online(self):
        """★ 2026-09-26：销项发票品名（实际经营产出）为**主口径**，高于外部工商核验与工商登记。"""
        r = resolve_industry(company_name="某某商贸有限公司",
                             registered_industry="商贸",
                             online_industry="商贸",
                             sales_goods=["*广告服务*推广费", "*广告服务*设计费"])
        self.assertEqual(r["industry"], "广告传媒")
        self.assertEqual(r["source"], SRC_INVOICE)

    def test_normalize_industry_name_maps_invoice_category_to_benchmark_key(self):
        """金税分类名 → 基准库键的通用归一（新增同类只需在 industry_map 加一行）。"""
        self.assertEqual(normalize_industry_name("广告服务"), "广告传媒")
        self.assertEqual(normalize_industry_name("广告传媒"), "广告传媒")   # 已是键
        self.assertEqual(normalize_industry_name("商贸零售"), "商贸零售")   # 已是键

    def test_inferred_from_goods_uses_sales_only(self):
        ind, votes = infer_from_goods(["*纺织*坯布", "*纺织*坯布", "*食品*零食"])
        # 返回前归一到基准库键；原始金税分类仍保留在 votes 里作为证据
        self.assertEqual(ind, "纺织制造")
        self.assertEqual(votes.get("纺织"), 2)


class TestBenchmarkBase(unittest.TestCase):
    """R4：能自报"是否在基准库中"，不再谎报。"""

    def test_real_key_is_in_base(self):
        for key in benchmark_keys()[:5]:
            self.assertTrue(is_in_benchmark_base(key))

    def test_gibberish_not_in_base(self):
        self.assertFalse(is_in_benchmark_base("绝无此行业XYZ"))
        self.assertFalse(is_in_benchmark_base(""))

    def test_generalization_note_is_truthful(self):
        key = benchmark_keys()[0]
        self.assertIn("已在", generalization_note(key, "生产型"))
        self.assertIn("不在", generalization_note("绝无此行业XYZ", "生产型"))


class TestBusinessCategory(unittest.TestCase):
    """⑤ 五分类：确定、可解释、具体业态优先。"""

    SCOPE_TRADE = "日用百货销售;塑料制品销售"

    def test_name_outweighs_broad_scope(self):
        # 名称明确是服务型，登记是宽泛的"商贸"，经营范围全是销售 → 应判服务型
        name = "某某数字传媒有限公司"
        r = business_category(industry="商贸", company_name=name,
                              business_scope=self.SCOPE_TRADE)
        self.assertEqual(r["category"], "服务型")
        self.assertTrue(r["scores"])

    def test_wholesale_only_company_is_trade(self):
        r = business_category(industry="商贸", company_name="某某商贸有限公司",
                              business_scope=self.SCOPE_TRADE)
        self.assertEqual(r["category"], "贸易型")

    def test_manufacturing_industry_is_production(self):
        r = business_category(industry="纺织制造", company_name="某某纺织有限公司")
        self.assertEqual(r["category"], "生产型")

    def test_deterministic_same_input_same_output(self):
        args = dict(industry="商贸", company_name="某某数字传媒有限公司",
                    business_scope=self.SCOPE_TRADE)
        self.assertEqual(business_category(**args)["category"],
                         business_category(**args)["category"])

    def test_specific_beats_generic_on_tie(self):
        # 服务型与贸易型同分（都只从经营范围各命中一次）→ 应取更具体的服务型
        r = business_category(industry="", company_name="",
                              business_scope="日用百货销售;技术咨询服务")
        self.assertEqual(r["scores"].get("服务型"), r["scores"].get("贸易型"))
        self.assertEqual(r["category"], "服务型")

    def test_no_signal_falls_back_to_mixed(self):
        r = business_category()
        self.assertEqual(r["category"], "混合型")
        self.assertFalse(r["is_known_industry"])


class TestSingleSourceOfIndustryData(unittest.TestCase):
    """⑥ 行业数据加载器单一来源（历史上 3 份重复实现，2 份无缓存、兜底形状各异）。"""

    def test_all_historical_loaders_share_one_object(self):
        from engine import domain_analysis, enterprise_profile, inspector_reasoning
        a = domain_analysis._load_industry_data()
        b = enterprise_profile._load_industry_data()
        c = inspector_reasoning._load_industry_data()
        d = load_industry_data()
        self.assertIs(a, b)
        self.assertIs(b, c)
        self.assertIs(c, d)

    def test_loader_has_safe_shape(self):
        d = load_industry_data()
        self.assertIn("benchmarks", d)
        self.assertIn("industry_map", d)
        self.assertIsInstance(d.get("benchmarks"), dict)

    def test_no_duplicate_loader_definitions_besides_resolver(self):
        """除解析器外，各模块只应有转发实现，不得再自带第二条加载/兜底逻辑。"""
        import inspect
        from engine import domain_analysis, enterprise_profile, inspector_reasoning
        for mod in (domain_analysis, enterprise_profile):
            src = inspect.getsource(mod._load_industry_data)
            self.assertIn("industry_resolver", src,
                          f"{mod.__name__}._load_industry_data 未委托统一解析器")


if __name__ == "__main__":
    unittest.main()


class TestBenchmarkLibraryMerged(unittest.TestCase):
    """区间库**单一来源**（2026-09-25 合并）：
    历史上存在两套数字 —— industry_data.json→benchmarks（细分）与
    industry_benchmark.py 硬编码的 INDUSTRY_BENCHMARKS（门类），同一概念两套区间。
    合并后：唯一数字源＝industry_data.json；industry_benchmark 全部派生。
    """

    # 合并前 INDUSTRY_BENCHMARKS 的门类原值（用于断言派生结果与历史口径一致）
    HISTORICAL_COARSE = {
        "制造业": {"gross_margin": (8.0, 40.0), "vat_burden": (1.5, 3.5),
                   "expense_ratio": (0.0, 15.0), "purchase_sales": (0.4, 0.95)},
        "批发零售": {"gross_margin": (5.0, 20.0), "vat_burden": (0.5, 1.5),
                     "expense_ratio": (0.0, 12.0), "purchase_sales": (0.6, 0.98)},
        "建筑业": {"gross_margin": (8.0, 20.0), "vat_burden": (2.0, 3.5),
                   "expense_ratio": (0.0, 10.0), "purchase_sales": (0.5, 0.95)},
        # 注意：门类键已由"信息技术"改名为"软件信息服务"——原名与**细分行业名**"信息技术"
        # 冲突，会被细分层遮蔽（细分层更精细，应优先），故门类键改名以消除碰撞。
        "软件信息服务": {"gross_margin": (25.0, 60.0), "vat_burden": (1.0, 3.0),
                         "expense_ratio": (0.0, 35.0), "purchase_sales": (0.1, 0.6)},
        "住宿餐饮": {"gross_margin": (40.0, 65.0), "vat_burden": (1.0, 3.0),
                     "expense_ratio": (0.0, 45.0), "purchase_sales": (0.2, 0.7)},
        "交通运输": {"gross_margin": (12.0, 28.0), "vat_burden": (2.0, 3.5),
                     "expense_ratio": (0.0, 15.0), "purchase_sales": (0.3, 0.85)},
        "房地产业": {"gross_margin": (20.0, 40.0), "vat_burden": (2.5, 5.0),
                     "expense_ratio": (0.0, 15.0), "purchase_sales": (0.3, 0.9)},
        "租赁商务": {"gross_margin": (20.0, 50.0), "vat_burden": (1.5, 4.0),
                     "expense_ratio": (0.0, 30.0), "purchase_sales": (0.15, 0.7)},
        "农林牧渔": {"gross_margin": (10.0, 30.0), "vat_burden": (0.5, 2.0),
                     "expense_ratio": (0.0, 20.0), "purchase_sales": (0.3, 0.9)},
        "电力热力燃气水": {"gross_margin": (10.0, 25.0), "vat_burden": (1.5, 3.0),
                           "expense_ratio": (0.0, 12.0), "purchase_sales": (0.4, 0.9)},
    }

    def test_coarse_values_match_historical(self):
        """门类区间的派生结果必须与合并前的历史口径一致（不得因合并而悄悄改数字）。"""
        from engine.industry_benchmark import INDUSTRY_BENCHMARKS
        for key, expect in self.HISTORICAL_COARSE.items():
            row = INDUSTRY_BENCHMARKS.get(key)
            self.assertIsNotNone(row, f"门类 {key} 在派生表中缺失")
            for metric, rng in expect.items():
                got = row.get(metric)
                self.assertIsNotNone(got, f"{key}.{metric} 缺失")
                self.assertAlmostEqual(got[0], rng[0], places=2, msg=f"{key}.{metric} 下限")
                self.assertAlmostEqual(got[1], rng[1], places=2, msg=f"{key}.{metric} 上限")

    def test_coarse_and_fine_keys_do_not_collide(self):
        """门类键与细分键不得同名（同名会被细分层遮蔽，门类层不可达）。"""
        from engine.industry_resolver import load_industry_data
        d = load_industry_data()
        fine = set(k for k in (d.get("benchmarks") or {}) if k != "_default")
        coarse = set((d.get("benchmarks_coarse") or {}).keys())
        self.assertEqual(fine & coarse, set(), f"门类键与细分键碰撞：{sorted(fine & coarse)}")

    def test_fine_grained_keys_present(self):
        """细分行业也可直接查（合并前只覆盖少数细分名）。"""
        from engine.industry_benchmark import INDUSTRY_BENCHMARKS
        for key in ("商贸", "纺织制造", "广告传媒", "餐饮服务", "咨询服务"):
            self.assertIn(key, INDUSTRY_BENCHMARKS, f"细分行业 {key} 缺失")

    def test_units_are_consistent(self):
        """单位正确性：进销比是比值(≤1.5)，其它是百分比(≤100)。"""
        from engine.industry_benchmark import INDUSTRY_BENCHMARKS, _GENERIC
        for key, row in list(INDUSTRY_BENCHMARKS.items()) + [("_GENERIC", _GENERIC)]:
            ps = row.get("purchase_sales")
            if ps:
                self.assertLessEqual(ps[1], 1.5, f"{key}.purchase_sales 疑似多乘 100：{ps}")
            for m in ("gross_margin", "vat_burden", "expense_ratio"):
                v = row.get(m)
                if v:
                    self.assertLessEqual(v[1], 100.0, f"{key}.{m} 超出百分比范围：{v}")

    def test_expense_ratio_inherited_from_coarse(self):
        """细分行业缺 期间费用率 时按门类继承，不留下空洞。"""
        from engine.industry_benchmark import INDUSTRY_BENCHMARKS
        self.assertIn("expense_ratio", INDUSTRY_BENCHMARKS["纺织制造"])

    def test_no_hardcoded_ranges_in_source(self):
        """源码中不得再出现硬编码区间（数字只允许存在于数据文件）。"""
        import inspect
        import re
        from engine import industry_benchmark as ib
        src = inspect.getsource(ib)
        hits = re.findall(r'"vat_burden"\s*:\s*\(\s*[\d.]+\s*,', src)
        self.assertEqual(hits, [], "industry_benchmark.py 又出现硬编码区间，破坏了单一来源")

    def test_resolve_benchmark_returns_canonical_source(self):
        from engine.industry_benchmark import resolve_benchmark
        matched, bench, source = resolve_benchmark("商贸")
        self.assertTrue(matched)
        self.assertIn("gross_margin", bench)
        self.assertTrue(source)
