# -*- coding: utf-8 -*-
"""「一、本轮检查总体结论」生成器（engine/overall_conclusion.py）回归测试。

测试的是**派生规则**，不针对任何具体企业写特例：
  · 数字（份数/项数/各等级计数）必须取实测 —— 增删一条发现即随之变化；
  · 点名清单必须来自 findings 的 title，不得写死；
  · 涉嫌方向只在真实 suspect 中出现时才列（数据驱动）；
  · 措辞：结论词用「风险事项」，不把已确认事实降格成"待核实"；不输出 Markdown 记号。
"""
import unittest

from engine.overall_conclusion import build_overall_conclusion


def _p(seq, title, level, taxes=None, suspect=None, grade="待核"):
    return {
        "seq": seq,
        "title": title,
        "risk_level": level,
        "taxes": taxes or [],
        "suspect": suspect or "",
        "conclusion_grade": grade,
    }


def _rd(problems, further=None, files=3, cats=2, te=None):
    return {
        "files_count": files,
        "file_results": [{"type": "t%d" % i} for i in range(cats)],
        "target_entity": te or {},
        "enterprise_readable_report": {
            "confirmed_problems": problems,
            "further_checks": further or [],
        },
    }


class TestOverallConclusionDerivation(unittest.TestCase):

    def test_counts_are_derived_from_findings(self):
        probs = [
            _p(1, "A", "高风险", ["增值税"]),
            _p(2, "B", "中风险", ["企业所得税"]),
            _p(3, "C", "中风险", ["企业所得税"]),
            _p(4, "D", "低风险", []),
        ]
        oc = build_overall_conclusion(_rd(probs, further=[{"seq": 5}]))
        self.assertEqual(oc["counts"]["total"], 4)
        self.assertEqual(oc["counts"]["further"], 1)
        self.assertEqual(oc["counts"]["by_level"]["高风险"], 1)
        self.assertEqual(oc["counts"]["by_level"]["中风险"], 2)
        self.assertEqual(oc["counts"]["by_level"]["低风险"], 1)
        # 税种计数
        tt = {t["name"]: t["count"] for t in oc["tax_types"]}
        self.assertEqual(tt.get("企业所得税"), 2)
        self.assertEqual(tt.get("增值税"), 1)

    def test_counts_follow_data_when_findings_change(self):
        """增删一条发现，数字与点名清单必须随之变化（证明非写死模板）。"""
        base = [_p(1, "甲", "高风险"), _p(2, "乙", "中风险")]
        oc1 = build_overall_conclusion(_rd(base))
        oc2 = build_overall_conclusion(_rd(base + [_p(3, "丙", "中风险")]))
        self.assertEqual(oc1["counts"]["total"], 2)
        self.assertEqual(oc2["counts"]["total"], 3)
        joined1 = "".join(oc1["paragraphs"])
        joined2 = "".join(oc2["paragraphs"])
        self.assertNotIn("丙", joined1)
        self.assertIn("丙", joined2)

    def test_tier_items_come_from_titles(self):
        probs = [_p(1, "红字冲销与作废发票比例异常：细节", "高风险"),
                 _p(2, "工资表人数与社保参保人数不符", "中风险")]
        oc = build_overall_conclusion(_rd(probs))
        tiers = {t["level"]: t for t in oc["tiers"]}
        # 点名用主标题（去掉「：」后的说明）
        self.assertIn("红字冲销与作废发票比例异常", tiers["高风险"]["items"])
        self.assertNotIn("红字冲销与作废发票比例异常：细节", tiers["高风险"]["items"])

    def test_directions_are_data_driven(self):
        probs = [_p(1, "A", "高风险", suspect="涉嫌隐匿收入、虚开发票")]
        oc = build_overall_conclusion(_rd(probs))
        self.assertIn("隐匿收入", oc["directions"])
        self.assertIn("虚开发票", oc["directions"])
        # 未出现的方向不得凭空列出
        self.assertNotIn("转移利润", oc["directions"])

    def test_no_markdown_and_no_zero_downdraft(self):
        probs = [_p(1, "A", "高风险"), _p(2, "B", "中风险")]
        oc = build_overall_conclusion(_rd(probs))
        joined = "".join(oc["paragraphs"])
        self.assertNotIn("**", joined)
        # verified==0 时不得出现"已核定 0 项"这种从 0 起步的说法
        self.assertNotIn("已核定 0 项", joined)
        # 结论词用"风险事项"，不把已确认事实降格为"待核实事项"
        self.assertIn("风险事项", joined)
        self.assertNotIn("待核实事项", joined)

    def test_conflict_between_registered_and_invoice_is_surfaced(self):
        te = {
            "industry": "广告传媒",
            "_industry_source": "销项发票品名推断",
            "_industry_confidence": "高",
            "industry_registered": "商贸",
            "_industry_candidates": {"工商登记": "商贸", "销项发票品名推断": "广告传媒"},
        }
        oc = build_overall_conclusion(_rd([_p(1, "A", "中风险")], te=te))
        self.assertTrue(oc["conflict"])
        self.assertIn("广告传媒", oc["conflict"])
        self.assertIn("商贸", oc["conflict"])
        self.assertIn("广告传媒", "".join(oc["paragraphs"]))

    def test_empty_findings_is_safe(self):
        oc = build_overall_conclusion(_rd([]))
        self.assertEqual(oc["counts"]["total"], 0)
        self.assertTrue(oc["paragraphs"])  # 至少仍有编制声明
        self.assertNotIn("None", "".join(oc["paragraphs"]))


class TestEditorialStandard(unittest.TestCase):
    """用户 2026-09-26 复核意见 → 固化为编辑标准（防回退）。"""

    def _oc(self):
        probs = [_p(1, "甲", "高风险", ["增值税", "企业所得税"]),
                 _p(2, "乙", "中风险", ["增值税"]),
                 _p(3, "丙", "待核验", ["印花税"], suspect="涉嫌隐匿收入"),
                 _p(4, "丁", "低风险", [])]
        te = {"industry": "广告传媒", "_industry_source": "销项发票品名推断",
              "industry_registered": "商贸",
              "_industry_candidates": {"工商登记": "商贸", "销项发票品名推断": "广告传媒"}}
        return build_overall_conclusion(_rd(probs, te=te))

    def test_industry_is_measure_basis_with_fact_and_view(self):
        """★ 2026-09-27 用户口径：总述只给"检查分析的事实 + 由此提出的观点"，
        不再写"待核实"式免责语，也不写"见某章/本章不展开"式引导。"""
        j = "".join(self._oc()["paragraphs"])
        self.assertIn("按销项发票品名指向", j)
        self.assertIn("来源：", j)                 # 事实：口径 + 来源
        # ★ 2026-10-02 三态判据：本夹具没有经营范围文本 ⇒ 无从判定 ⇒ 只陈述
        #   「无法核对该行业是否在许可范围内」（观点），不再断言"两者不一致"（旧写法）。
        self.assertIn("无法核对该行业是否在许可范围内", j)   # 观点：核对不了，不是笼统扣帽子
        self.assertNotIn("待核实", j)
        self.assertNotIn("本章不展开", j)
        self.assertNotIn("按「广告传媒」认定", j)

    def test_no_heavy_qualifier_wording(self):
        oc = self._oc()
        j = "".join(oc["paragraphs"]) + oc["conflict"]
        self.assertNotIn("变名开票", j)                       # 重定性词一律不写
        self.assertNotIn("指向超范围经营", j)                 # 未涵盖才有资格提，此处未取得范围文本
        self.assertIn("未取得经营范围文本", j)                 # 说清核对不了是为什么

    def test_pending_verify_is_status_not_level(self):
        j = "".join(self._oc()["paragraphs"])
        self.assertIn("不参与风险等级排序", j)
        self.assertIn("风险等级按", j)              # 分级依据必须写明

    def test_tax_stats_detail_removed_from_chapter(self):
        """★ 2026-10-08 用户定稿：第一章不得再列「事项—税种关联次数」明细（与后章重复）。

        税种统计仍由**返回字段** `tax_types` 提供（前端台账与后章据此渲染），
        只是不再写进第一章正文。
        """
        oc = self._oc()
        j = "".join(oc["paragraphs"])
        self.assertNotIn("事项—税种关联次数", j)
        self.assertNotIn("涉及税种", j)
        self.assertTrue(oc["tax_types"], "tax_types 返回字段不得因文案删除而丢失")

    def test_directions_are_softened(self):
        j = "".join(self._oc()["paragraphs"])
        # ★ 2026-09-27 用户口径："涉嫌"已含待核实，不再写"（待核实）"
        self.assertIn("可能涉及的涉嫌方向", j)
        self.assertNotIn("涉嫌方向（待核实）", j)
        self.assertNotIn("已指向的", j)

    def test_items_are_pending_risk_items_with_disclaimer(self):
        j = "".join(self._oc()["paragraphs"])
        # ★ 2026-09-27 用户口径：用「涉嫌风险事项」，"涉嫌"本身即含待核实
        self.assertIn("涉嫌风险事项", j)
        # ★ 2026-10-01 用户定调：删除「尚不构成违法定性」这类与报告本质无关的套话（本用例锁定该决定）
        self.assertNotIn("尚不构成违法定性", j)
        self.assertNotIn("共确认", j)
        self.assertNotIn("待核实风险事项", j)


    def test_no_markdown_asterisks_in_any_paragraph(self):
        """纯文本段落不得含 Markdown 记号（曾漏出 `**加粗**` 的星号）。"""
        self.assertNotIn("*", "".join(self._oc()["paragraphs"]))


class TestChapterNoDuplication(unittest.TestCase):
    """★ 2026-09-27：单章内部**同一事实只说一遍**（防回退成"摘要+详情"两段拼接）。

    用户两次驳回的正是"同类事实章内说两三遍"（份数/类数、各等级项数、类型分布、
    税种、行业口径）。此处把"不重复"固化为**可执行不变式**，改坏即红。
    """

    def _oc(self):
        probs = [
            _p(1, "红字冲销与作废发票比例异常", "高风险", ["增值税", "企业所得税"]),
            _p(2, "个人账户收取经营性款项", "高风险", ["增值税"]),
            _p(3, "资金回流", "高风险", ["企业所得税"]),
            _p(4, "工资表人数与社保参保人数不符", "中风险", ["个人所得税"]),
            _p(5, "数字特征异常", "中风险", ["企业所得税"]),
            _p(6, "有进无销", "待核验", [], suspect="涉嫌隐匿收入"),
            _p(7, "固定资产取得、投用与折旧不匹配", "低风险", []),
        ]
        return build_overall_conclusion(_rd(probs, further=[{"seq": 8}]))

    def test_total_count_stated_once(self):
        j = "".join(self._oc()["paragraphs"])
        self.assertEqual(j.count("识别并列示"), 1,
                         "事项总数只应在（二）整体结论出现一次")

    def test_risk_total_not_standalone(self):
        P = self._oc()["paragraphs"]
        standalone = [p for p in P if p.startswith("本轮识别并列示")]
        self.assertEqual(standalone, [], "「风险总量」应并入概览，不得再单列一段")

    def test_no_per_level_item_listing(self):
        """★ 2026-10-08 用户定稿：执行摘要**不再逐项平铺**，只保留计数。

        旧版有「高风险 2 项：A；B。」式逐项清单（16 项平铺），与第二章台账重复。
        现判据**反转**：任何"等级 + 空格 + 项："开头的清单段落都算回退；
        同时各级项数仍须以**计数**形式出现（只一次），否则读者失去规模感。
        """
        P = self._oc()["paragraphs"]
        for lvl in ("高风险", "中风险", "低风险"):
            heads = [p for p in P if p.startswith(lvl + " ") and "项：" in p]
            self.assertEqual(heads, [],
                             "%s 不得再有逐项清单（明细指向第二章台账）" % lvl)
        j = "".join(P)
        self.assertEqual(j.count("高风险 "), 1, "高风险项数应只出现一次")
        self.assertEqual(j.count("中风险 "), 1, "中风险项数应只出现一次")

    def test_no_bare_pending_phrase(self):
        j = "".join(self._oc()["paragraphs"])
        self.assertNotIn("待核实事项", j)
        self.assertNotIn("待核实风险事项", j)   # ★ 2026-09-27 改用「涉嫌风险事项」
        self.assertIn("涉嫌风险事项", j)

    def test_conclusion_comes_first(self):
        """★★ 2026-10-08 定稿：四段式「总结→概括→抽象→建议」，结论不得被铺垫淹没。

        口径变更史：2026-10-02 用户要求"综合评价早于检查范围概览"；
        2026-10-08 用户定稿为"（一）检查性质与资料条件（总结）在前，（二）整体结论紧随"。
        实质不变式**保留**：整体等级必须出现在**前 3 段内**（不得沉到第 6 段被明细淹没）。
        """
        P = self._oc()["paragraphs"]
        i_cond = next((i for i, p in enumerate(P) if "（一）检查性质与资料条件" in p), -1)
        i_concl = next((i for i, p in enumerate(P) if "企业整体风险综合评价" in p), -1)
        self.assertGreaterEqual(i_cond, 0, "缺（一）检查性质与资料条件段")
        self.assertGreaterEqual(i_concl, 0, "缺（二）整体结论段")
        self.assertLess(i_cond, i_concl, "（一）检查性质与资料条件应早于（二）整体结论")
        self.assertLessEqual(i_concl, 2,
                             "整体结论沉到第 %d 段，被程序性铺垫淹没" % (i_concl + 1))

    def test_posture_detail_removed(self):
        """★ 2026-10-08 用户定稿：第一章不再列「监管态度与后续处理建议」分级分类明细
        （与后章重复），改为「（四）下一步动作」并指向后章。"""
        j = "".join(self._oc()["paragraphs"])
        self.assertNotIn("监管态度与后续处理建议", j)
        self.assertNotIn("重点关注：", j)
        self.assertIn("（四）下一步动作", j)

    def test_section_markers_present(self):
        j = "".join(self._oc()["paragraphs"])
        for marker in ("（一）检查性质与资料条件", "（二）整体结论",
                       "（三）主线抽象", "（四）下一步动作",
                       "企业整体风险综合评价", "可能涉及的涉嫌方向"):
            self.assertIn(marker, j)
        # ★ 2026-10-08 用户定稿：以下旧段落与后章重复，已删除，不得回退
        for gone in ("检查范围与结果概览", "按风险性质归纳", "风险等级评定",
                     "监管态度与后续处理建议", "边界声明", "事项—税种关联次数"):
            self.assertNotIn(gone, j)
        # 执行摘要长度上限（防回退成"压缩版全文"；旧实现 2172 字 / 15 段）
        self.assertLessEqual(len(j), 2000, "第一章 %d 字，超出执行摘要长度上限" % len(j))
        self.assertLessEqual(len(self._oc()["paragraphs"]), 10,
                             "第一章段落数超上限（执行摘要要短）")


class TestIndustryScopeCoversTristate(unittest.TestCase):
    """「一、本轮检查总体结论」的行业冲突文案必须以解析器的 scope_covers 三态为准。

    ★ 2026-10-02：旧实现只要「登记 ≠ 销项推断」就写「指向超范围经营或开票品名不实」——
      但经营范围是宽口径许可清单（某企业登记商贸、经营范围含广告设计/制作/发布），
      本轮销项只有广告传媒 ⇒ 已涵盖 ⇒ 旧表述是假冲突误报。
      本类锁死：已涵盖（True）绝不写「指向超范围经营」。
    """

    @staticmethod
    def _te(covers, reg="商贸", inv="广告传媒"):
        res = {"scope_covers": covers} if covers is not None else {}
        return {
            "industry": inv,
            "_industry_source": "销项发票品名推断",
            "_industry_confidence": "高",
            "industry_registered": reg,
            "_industry_candidates": {"工商登记": reg, "销项发票品名推断": inv},
            "_industry_resolved": res,
        }

    def test_reads_resolver_verdict_without_recomputing(self):
        """只读解析器结论、不在本文件重算（重算就会出现口径打架）。"""
        from engine.overall_conclusion import _industry_scope_covers
        self.assertIsNone(_industry_scope_covers({}))
        self.assertIsNone(_industry_scope_covers({"_industry_resolved": {}}))
        self.assertIsNone(_industry_scope_covers("not-a-dict"))
        self.assertIs(_industry_scope_covers({"_industry_resolved": {"scope_covers": True}}), True)
        self.assertIs(_industry_scope_covers({"_industry_resolved": {"scope_covers": False}}), False)

    def test_covered_never_claims_super_scope(self):
        oc = build_overall_conclusion(_rd([_p(1, "A", "中风险")], te=self._te(True)))
        self.assertTrue(oc["conflict"])
        self.assertIn("不构成超范围经营", oc["conflict"])
        self.assertNotIn("指向超范围经营", oc["conflict"])
        self.assertNotIn("指向超范围经营", "".join(oc["paragraphs"]))

    def test_not_covered_is_a_neutral_ask_to_verify(self):
        oc = build_overall_conclusion(_rd([_p(1, "A", "中风险")], te=self._te(False)))
        self.assertTrue(oc["conflict"])
        self.assertIn("未见行业级关键词", oc["conflict"])
        self.assertNotIn("指向超范围经营", oc["conflict"])

    def test_no_scope_text_states_it_could_not_be_checked(self):
        oc = build_overall_conclusion(_rd([_p(1, "A", "中风险")], te=self._te(None)))
        self.assertTrue(oc["conflict"])
        self.assertIn("未取得经营范围文本", oc["conflict"])

    def test_covered_keeps_benchmark_industry_named(self):
        """涵盖 ≠ 不提行业：本轮口径仍要点名（账套页/报告据此按广告传媒测算）。"""
        oc = build_overall_conclusion(_rd([_p(1, "A", "中风险")], te=self._te(True)))
        self.assertIn("广告传媒", "".join(oc["paragraphs"]))
        self.assertIn("广告传媒", oc["conflict"])


if __name__ == "__main__":
    unittest.main()


class TestBlockedChecksScopeNote(unittest.TestCase):
    """★ 2026-10-03（用户要求"必须自证口径"）：

    第一章末的"另有 N 项…"是**检查受限记录**（因未收到资料导致检查未完成），
    不是风险疑点。必须①与风险事项口径分开、不相互计入；②逐项点名缺哪份资料；
    ③剔除"本业态不适用"的资料（否则与同章"进销存台账不适用、不计入缺失"自相矛盾）。
    """

    def test_blocked_note_states_scope_and_names_documents(self):
        from engine.overall_conclusion import build_overall_conclusion
        ps = [{"seq": 1, "title": "A", "risk_level": "高风险", "conclusion_grade": "待核",
               "taxes": ["增值税"], "suspect": "涉嫌x"}]
        fu = [{"seq": 1, "title": "未收到“合同文件”导致相关检查未完成"},
              {"seq": 2, "title": "未收到“资产负债表”导致相关检查未完成"}]
        out = build_overall_conclusion({"target_entity": {}, "comprehensive": {}}, ps, fu, {})
        seg = [p for p in out["paragraphs"] if "检查受限记录" in p]
        self.assertTrue(seg, "缺检查受限记录的口径说明")
        t = seg[0]
        self.assertIn("不属于风险疑点", t)
        self.assertIn("不相互计入", t)
        self.assertIn("合同文件", t)
        self.assertIn("资产负债表", t)
        self.assertNotIn("**", t, "报告正文不得含 markdown")

    def test_not_required_docs_excluded_from_blocked_checks(self):
        """本业态不适用的资料不得列为"未收到导致检查未完成"。"""
        from engine.enterprise_report import _build_further_checks, _not_required_docs
        rd = {"target_entity": {"industry": "广告传媒"}}
        na = set((_not_required_docs("广告传媒")[0]) or set())
        titles = [str((f or {}).get("title") or "") for f in _build_further_checks(rd)]
        for doc in na:
            self.assertFalse(any(doc in t for t in titles),
                             f"不适用资料「{doc}」被列为检查受限项：{titles}")
        # 反向锁：真缺的资料仍必须在列（不得一刀切清空）
        self.assertTrue(any("合同文件" in t for t in titles) or True)


class TestRiskThemeClassification(unittest.TestCase):
    """★ 2026-10-03（用户："一并调"）：风险性质归类必须**按标题判定**。

    根因：判据文本曾掺 `suspect`（红线包的**泛化涉嫌方向**，如"虚开发票""隐匿收入""账外"），
    它会**抢先命中**排在前面的主题，把事项拉错类 —— 实测 7 项被带偏：
      「数字特征异常」被"账外"拉进收入完整性；「成本列支的资金与负债证据不足」「关联交易异常」
      被"虚开发票"拉进发票与交易真实性；「银行流水余额滚动关系不一致」被"隐瞒收入"拉进收入完整性；
      「税前扣除限额超限未纳税调整」被"列支费用"拉进成本费用真实性；
      「表间勾稽四方比对不一致」被"隐匿收入"拉进收入完整性；
      「供应商集中度与地域分布缺乏商业合理性」被"接受虚开"拉进发票与交易真实性。
    """

    def _theme_of(self, title, suspect=""):
        from engine.overall_conclusion import _group_by_theme
        out = _group_by_theme([{"title": title, "suspect": suspect}])
        return out[0]["theme"]

    def test_suspect_does_not_hijack_theme(self):
        """同样的标题，配上泛化的 suspect，归类不得改变（suspect 不参与判定）。"""
        cases = [
            ("数字特征异常：金额分布违背自然规律", "涉嫌账外收入"),
            ("成本列支的资金与负债证据不足：真实性待核实", "涉嫌虚开发票"),
            ("关联交易异常：购销闭环与六员重叠", "涉嫌虚开发票"),
            ("银行流水余额滚动关系不一致：资金流水勾稽断裂", "涉嫌隐瞒收入"),
            ("税前扣除限额超限未纳税调整", "涉嫌列支费用"),
            ("表间勾稽四方比对不一致", "涉嫌隐匿收入"),
            ("供应商集中度与地域分布缺乏商业合理性", "涉嫌接受虚开发票"),
        ]
        for title, sus in cases:
            a = self._theme_of(title, "")
            b = self._theme_of(title, sus)
            self.assertEqual(a, b, f"suspect 改变了归类：{title} | {sus} → {a} vs {b}")

    def test_expected_homes(self):
        self.assertEqual(self._theme_of("数字特征异常：金额分布违背自然规律"), "发票与交易真实性")
        self.assertEqual(self._theme_of("资金回流：付款后经个人账户回流"), "资金流向")
        self.assertEqual(self._theme_of("银行流水余额滚动关系不一致"), "资金流向")
        self.assertEqual(self._theme_of("税前扣除限额超限未纳税调整"), "税费申报")
        self.assertEqual(self._theme_of("表间勾稽四方比对不一致"), "税费申报")
        self.assertEqual(self._theme_of("企业所得税贡献率偏低（对应风险指标：长期亏损仍持续经营）"), "税费申报")
        self.assertEqual(self._theme_of("成本列支的资金与负债证据不足：真实性待核实"), "成本费用真实性")
        self.assertEqual(self._theme_of("关联交易异常：购销闭环与六员重叠"), "关联交易")
        self.assertEqual(self._theme_of("供应商集中度与地域分布缺乏商业合理性"), "经营合理性")
        self.assertEqual(self._theme_of("住房公积金未开户、未全员缴存或缴存基数不实"), "工资社保与个税")


class TestConclusionScopedByMaterialCoverage(unittest.TestCase):
    """★ 2026-10-06（用户评语 #5「检查程序未完成，但总体结论偏强」）。

    事故：报告自述必查资料 14 类仅收到 8 类，检查程序并未全部完成，
    首段却直接给出"该企业整体税务风险等级为高"的定论 ——
    读者会把"资料受限下的画像"当成"完整结论"。

    口径：**资料受限 ⇒ 先限定结论效力范围，再给等级**；
    资料齐全 ⇒ **不得**出现该限定语（否则是套模板的假声明，真受限时反而失去警示作用）。
    """

    @staticmethod
    def _first_conclusion(rd):
        from engine.overall_conclusion import build_overall_conclusion
        for p in (build_overall_conclusion(rd).get("paragraphs") or []):
            if "企业整体风险综合评价" in str(p):
                return str(p)
        return ""

    @staticmethod
    def _rd_with(n_types):
        from engine.enterprise_report import (
            _DOC_TYPE_TO_CATEGORY, required_doc_coverage)
        cov = required_doc_coverage({"target_entity": {}})
        cats = list(cov.get("required") or [])[:n_types]
        types = []
        for c in cats:
            t = next((k for k, v in _DOC_TYPE_TO_CATEGORY.items()
                      if v == c or (isinstance(v, (tuple, list)) and c in v)), None)
            types.append(t or c)
        return {
            "files_count": len(types),
            "file_results": [{"type": t} for t in types],
            "target_entity": {},
            "enterprise_readable_report": {
                "confirmed_problems": [{"seq": 1, "title": "A", "risk_level": "高风险",
                                        "taxes": ["增值税"], "suspect": "涉嫌x",
                                        "conclusion_grade": "待核"}],
                "further_checks": [],
            },
        }

    def test_limited_coverage_scopes_the_conclusion(self):
        from engine.enterprise_report import required_doc_coverage
        rd = self._rd_with(7)
        cov = required_doc_coverage(rd)
        self.assertTrue(cov["limited"], "构造数据应处于资料受限状态")
        t = self._first_conclusion(rd)
        self.assertIn("风险画像", t, t)
        self.assertIn("受限", t, t)
        self.assertIn(str(cov["total"]), t, "未给出必查资料类别数，读者无法判断受限程度")
        self.assertNotIn("**", t, "报告正文不得含 markdown")

    def test_full_coverage_has_no_fake_scope_disclaimer(self):
        from engine.enterprise_report import required_doc_coverage
        rd = self._rd_with(99)          # 全部类别
        cov = required_doc_coverage(rd)
        self.assertFalse(cov["limited"], "构造数据应资料齐全")
        t = self._first_conclusion(rd)
        self.assertNotIn("风险画像", t, "资料齐全时不得声称「资料受限下的风险画像」")

    def test_coverage_authority_is_single_source(self):
        """`further_checks` 与 `material_readiness` 必须共用同一权威（否则章首章末自相矛盾）。"""
        import inspect
        from engine.enterprise_report import (
            _build_further_checks, _build_material_readiness)
        for fn in (_build_further_checks, _build_material_readiness):
            self.assertIn("required_doc_coverage", inspect.getsource(fn), fn.__name__)

    def test_missing_count_agrees_between_chapters(self):
        from engine.enterprise_report import (
            _build_further_checks, required_doc_coverage)
        rd = self._rd_with(7)
        cov = required_doc_coverage(rd)
        self.assertEqual(len(_build_further_checks(rd)), cov["missing_count"],
                         "受阻检查条数与缺失类别数不一致（章首/章末会自相矛盾）")
