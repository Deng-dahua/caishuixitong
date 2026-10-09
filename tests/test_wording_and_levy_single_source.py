# -*- coding: utf-8 -*-
"""用词与税费性质的**单一权威**跨模块一致性测试（2026-10-08）。

背景（**同一病根三次出血**，用户要求"解决根本原因、不逐个打补丁"）：
  · 「禁用模糊词」的**判据**曾在 3 处各写一套（`quality_gates` / 审计出口扫描 /
    权威 `report_wording`）。其中审计侧自实现那份**未豁免权威术语** ⇒ 把权威术语
    「待核事项」当模糊词，实测 **25 处 ERROR 误报**；而权威那份未豁免结构标识
    「待核线索：」，反向误报。两份判据**互补地各错一半**。
  · 「法定后果」在 P0-2 收口后**按性质上提报告级一次**（`report_statement`），
    逐项只留「本项情形 + 去向」⇒ 任何"逐项后果段必须含某依据"的旧判据必然误报。

本测试把两条不变量锁死（并**复用常驻闸门**，不再自建第二份判据）：
  ① 同一段文本，在**任何**模块得到的"是否含禁用模糊词"结论必须与权威完全相同；
  ② 每种税费性质的法定后果声明必须可导出且可见；非税不得套用征管法偷税条款；
     逐项后果段必须携带指向报告级声明的引用（否则企业查不到法定后果）。
"""
from __future__ import annotations


class TestVagueHitsSingleSource:
    """禁用模糊词：**判据唯一**（术语/结构标识豁免 + 真禁用词仍拦得住）。"""

    @staticmethod
    def _battery():
        from engine.conclusion_grade import conclusion_terms
        return list(conclusion_terms()) + [
            "待核线索：所有者权益异常变动",
            "账内检出信号待核实",
            "税负尚需核实",
            "其他应付款大额长期挂账（待核）",
            "已提供同类资料",
            "已有", "缺失", "高风险", "待企业提交",
        ]

    def test_authority_exempts_authoritative_terms(self):
        """结论用语四术语（含「待核事项」）不得被判为模糊词。"""
        from engine.report_wording import vague_hits
        from engine.conclusion_grade import conclusion_terms
        assert conclusion_terms(), "结论用语权威表为空，测试前提不成立"
        for t in conclusion_terms():
            assert vague_hits("本项属%s；未认定到构成要件，不作定性" % t) == [], \
                "权威术语「%s」被误判为模糊词" % t

    def test_authority_exempts_structure_prefix(self):
        """结构标识「待核线索：」是降级疑点的机器标识（闸门靠它识别），不得改写/误判。"""
        from engine.report_wording import vague_hits
        assert vague_hits("待核线索：所有者权益异常变动") == []

    def test_authority_still_catches_forbidden_terms(self):
        """阳性对照：真禁用词必须被拦下（否则等于把闸门关掉）。

        ⚠⚠ 2026-10-09（P1-4 正解）：这里的第 3 例取自**真实产物**的字段值
          （`domain_summary[*].findings[*].type` = 「其他应付款大额长期挂账（待核）」）。
          我曾把「合法标签」按**子串**豁免 ⇒ 这条真缺陷被放过、本用例报红 —— 说明
          **豁免口径必须与身份对齐**：字段值（整串）可豁免，叙述/事项名（嵌在句中）不可。
        """
        from engine.report_wording import vague_hits
        for bad in ("账内检出信号待核实", "税负尚需核实",
                    "其他应付款大额长期挂账（待核）",
                    "印花税 — 买卖合同税目税负待核",
                    "股权转让未申报个人所得税（待核）"):
            assert vague_hits(bad), "真禁用词未被拦下：%s" % bad

    def test_authority_exempts_legal_labels_only_as_whole_value(self):
        """★ 2026-10-09（P1-4）：**合法标签只在"整串就是它自己"时豁免**（字段值身份）。

        判据**动态取自权威**（`conclusion_grade.authorized_labels()` ∩ `FORBIDDEN_VAGUE_TERMS`），
        不硬编码具体词 ⇒ 权威表新增同类冲突词时本判据自动覆盖。
        若有人把豁免改回"子串掩码"（把「待核」一律放过），本用例立刻报红。
        """
        from engine.conclusion_grade import authorized_labels, conclusion_terms
        from engine.report_wording import FORBIDDEN_VAGUE_TERMS, vague_hits
        labels = {str(x).strip() for x in authorized_labels() if str(x or "").strip()}
        terms = {str(t).strip() for t in conclusion_terms()}
        # ⚠ 只取**自身不含权威术语**的合法标签：
        #   · 术语（「待核事项」…）身份本就是"可出现在句中" ⇒ 按子串豁免；
        #   · 含术语的长标签（「本项属待核事项」）由术语那条规则覆盖 ⇒ 句中同样豁免；
        #   · 剩下的「字段值型标签」（裸「待核」「待核验」）才适用**整串**判据。
        conflict = sorted(l for l in labels if l not in terms
                          and not any(t and t in l for t in terms)
                          and any(f and f in l for f in FORBIDDEN_VAGUE_TERMS))
        assert conflict, ("权威标签与禁用词表中当前**无**冲突词 ⇒ 本判据前提不成立"
                          "（判据已失效，须重新审视 A5/D7 两表）")
        for lab in conflict:
            assert vague_hits(lab) == [], \
                "合法标签整串「%s」被误判为模糊词（A5 认合法 / D7 认禁用，词表冲突未收敛）" % lab
            # 同一个词**嵌进叙述**时必须仍被拦下（否则豁免过宽 = 关掉闸门）
            assert vague_hits("本项经核对仍属%s" % lab), \
                "标签「%s」嵌在句中却未被拦下（豁免过宽，闸门实效性失效）" % lab
        for t in sorted(terms & labels):
            assert vague_hits("本项属%s；未认定到构成要件，不作定性" % t) == [], \
                "权威术语「%s」嵌在句中却被误判（术语按子串豁免的口径被破坏）" % t

    def test_cross_module_same_verdict(self):
        """★ 核心：任一消费模块对同一文本的判定必须与权威**完全一致**。

        历史缺陷：审计侧自实现判据 ⇒ 与权威互补地各错一半（术语侧 25 处误报）。
        """
        from engine.report_wording import vague_hits
        from engine.quality_gates import _vague_term_hits
        for t in self._battery():
            auth = bool(vague_hits(t))
            qg = bool(_vague_term_hits([t]))
            assert auth == qg, "quality_gates 与权威判定不一致：%r auth=%s qg=%s" % (
                t, auth, qg)

    def test_source_contract_no_private_judge(self):
        """源码契约（复用常驻闸门 `check_vague_wording_single_source`）。

        除 `engine/report_wording.py` 与测试外，任何模块不得 import
        `FORBIDDEN_VAGUE_TERMS` 后自建判据 —— 消费方只能调 `vague_hits`。
        """
        from tools.audit_consistency import check_vague_wording_single_source
        errs = [i for i in check_vague_wording_single_source() if i[0] == "ERROR"]
        assert errs == [], "模糊词判据非单一权威：%s" % errs


class TestLevyDeclarationAuthority:
    """税费性质与法定后果：声明唯一、非税不套用偷税条款、逐项引用不悬空。"""

    def test_declaration_per_nature_nontax_not_citing_63(self):
        from engine.levy_nature import LEVIES, consequence_declaration
        assert LEVIES, "税费性质权威表为空"
        for n in LEVIES:
            d = consequence_declaration(n)
            assert d and LEVIES[n].get("label") in d, "性质「%s」的声明缺标签" % n
            if n != "税":
                assert "第六十三条" not in d, \
                    "非税性质「%s」的声明仍引用征管法第六十三条（偷税）" % n

    def test_item_consequence_carries_reference(self):
        """逐项后果段必须携带报告级引用（P0-2 收口契约）。"""
        from engine.levy_nature import item_consequence_text, consequence_decl_ref
        ref = consequence_decl_ref()
        assert ref, "引用语权威取不到"
        for n in ("税", ["文化事业建设费"], ["社会保险费"]):
            t = item_consequence_text(n, suspect="测试情形")
            assert ref in t, "逐项后果段缺报告级引用（企业将查不到法定后果）：%s" % n

    def test_report_declarations_cover_problem_natures(self):
        """报告级声明入口必须覆盖事项涉及的全部性质（不悬空）。"""
        from engine.enterprise_report import _report_levy_declarations
        from engine.levy_nature import consequence_declaration, natures_of
        prob = {"taxes": ["广告服务未申报文化事业建设费"], "title": "T"}
        out = _report_levy_declarations([prob])
        assert out, "报告级声明入口产出为空"
        for n in natures_of(prob):
            assert consequence_declaration(n) in out, \
                "性质「%s」的声明未进报告级列表（逐项引用会悬空）" % n

    def test_non_tax_item_has_no_63_in_consequence(self):
        """纯非税事项的逐项后果段不得出现征管法偷税条款。"""
        from engine.levy_nature import item_consequence_text
        for n in (["文化事业建设费"], ["住房公积金"], ["社会保险费"]):
            t = item_consequence_text(n, suspect="测试情形")
            assert "第六十三条" not in t, "非税项后果段引用了偷税条款：%s" % n
