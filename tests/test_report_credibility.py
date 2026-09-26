# -*- coding: utf-8 -*-
"""报告可信度契约测试（2026-09-25）

锁死四类"报告说了但没据/说了但读不通"的缺陷：

  1. **切句必须括号感知** —— 朴素 `re.split(r"[。；\n]")` 会把括号内的分号当句末，
     切出「（取销项发票不含税金额」这种括号不闭合的残句，原样进报告即一句读不通。
  2. **红线配对必须有据** —— 不得因"税种名相同/同域"就把发现挂到不相干的红线上
     （事故：一条增值税进项差异发现被挂到「固定资产取得、投用与折旧不匹配」，
     报告随即用固定资产折旧的构成要件去论证它）。
  3. **定性表述不得越界** —— 不得把筛查线索直接断言为已成立的违法事实
     （事故：「部分收入经个人账户归集，**是账外收款的直接证据**」）。
  4. **论证链的资料归属必须按实际** —— 不得把"红线模板声明的应查资料"写成
     "已逐层核对过的资料"（事故：报告称事实取自"固定资产明细账、试生产记录、
     折旧计算表"，而该企业一份都没提交）。

完整锁定的实体结论见 tests/test_redline_methodology.py::TestEvidenceStatusGrounded。
"""

import unittest

from engine.sentencekit import (
    first_sentence, is_balanced, pick_best, split_sentences, strip_meta_prefix,
)


class TestSentenceSplit(unittest.TestCase):
    """契约 1：切句不得切在括号内部。"""

    DETAIL = ("本项目前的性质是：费用率畸高待证事项（非已认定违法）。"
              "已经核实的事实是：凭证费用合计 44,394,561.24元，收入口径 6,636,800.57元"
              "（取销项发票不含税金额；若以申报收入 0.00元计则更高），费用率 668.9%，"
              "超过预设预警线 40%。之所以值得查，是因为存在三种成因。")

    def test_not_split_inside_parenthesis(self):
        for s in split_sentences(self.DETAIL):
            self.assertTrue(is_balanced(s), f"切出的句子括号不闭合：{s!r}")

    def test_parenthetical_semicolon_preserved(self):
        joined = "".join(split_sentences(self.DETAIL))
        self.assertIn("（取销项发票不含税金额；若以申报收入 0.00元计则更高）", joined)

    def test_naive_split_would_break(self):
        """反证：朴素切分确实会切坏（确保本测试有意义）"""
        import re as _re
        naive = _re.split(r"[。；\n]", self.DETAIL)
        self.assertTrue(any(not is_balanced(x) for x in naive),
                        "朴素切分本应切出括号不闭合的片段")

    def test_brackets_of_all_kinds(self):
        for text in ("甲（一；二）。乙",
                     "「甲；乙」以下。",
                     "《某办法》规定；甲。",
                     "【甲；乙】丙。",
                     "“甲；乙”丙。"):
            for s in split_sentences(text):
                self.assertTrue(is_balanced(s), text)

    def test_first_sentence(self):
        self.assertEqual(first_sentence("甲；乙。丙"), "甲")
        self.assertEqual(first_sentence("（甲；乙）。丙"), "（甲；乙）")
        self.assertEqual(first_sentence(""), "")

    def test_pick_best_requires_digit_and_balance(self):
        cands = ["没有数字的句子", "有数字30元（未闭合", "有数字40元（闭合）"]
        self.assertEqual(pick_best(cands), "有数字40元（闭合）")

    def test_strip_meta_prefix(self):
        cases = {
            "已经核实的事实是：金额100元": "金额100元",
            "已核实：金额100元": "金额100元",
            "事实是：金额100元": "金额100元",
            "· 金额100元": "金额100元",
            "1. 金额100元": "金额100元",
            "正常文本不动": "正常文本不动",
            # ★ 2026-09-26 回归：量词前的计数不得被吞（"13张"→"张" 的历史 bug）
            "13张发票被红冲或作废，涉及金额-1,285,450.57元。": "13张发票被红冲或作废，涉及金额-1,285,450.57元。",
            "6名员工创造销项收入7,035,008.58元。": "6名员工创造销项收入7,035,008.58元。",
            "① 9笔异常交易需复核": "9笔异常交易需复核",
        }
        for raw, want in cases.items():
            self.assertEqual(strip_meta_prefix(raw), want, raw)


class TestStripMethodology(unittest.TestCase):
    """契约 5：线索链 numbers 不得混入方法论阈值（如「>=3张触发」）。"""

    def test_strip_methodology_drops_threshold(self):
        from engine.clue_chain import _strip_methodology, extract_numbers
        detail = ("13张发票被红冲或作废，涉及金额-1,285,450.57元。"
                  "可能为虚开后销毁证据。"
                  "税务合规方法：从发票状态、备注、类型字段搜索'红冲''作废'等关键词，"
                  "统计数量和金额。>=3张触发。"
                  "税务影响：高频红冲可能被认定为恶意拖延纳税。")
        clean = _strip_methodology(detail)
        self.assertIn("13张", clean, "事实计数必须保留")
        self.assertNotIn(">=3张触发", clean, "方法论阈值必须剥离")
        nums = extract_numbers(clean)
        # 「3张」作为独立 token 不得出现（注意 "13张" 含 "3张" 子串，故按 token 校验）
        self.assertNotIn("3张", nums, "伪数字 3张 不得作为独立 token 出现")
        self.assertIn("13张", nums)
        self.assertIn("-1,285,450.57元", nums)

    def test_strip_methodology_keeps_fact_at_start(self):
        from engine.clue_chain import _strip_methodology
        # 开头就出现"处理建议"这类词的极端情况：不得误剥事实
        detail = "处理建议：应逐张核验。但事实是 5张发票异常。"
        self.assertIn("处理建议", _strip_methodology(detail))


class TestOverclaimGuard(unittest.TestCase):
    """契约 3：定性越界表述必须被降为待核。"""

    def _clean(self, s):
        from engine.text_guardrails import _apply_overclaim_rules
        return _apply_overclaim_rules(s)

    def test_evidence_overclaim_hedged(self):
        out = self._clean("部分收入经个人账户归集，是账外收款的直接证据，须逐一核验。")
        self.assertNotIn("的直接证据", out)
        self.assertIn("待核", out)

    def test_offence_assertion_hedged(self):
        for raw in ("该情形构成虚开发票行为。",
                    "上述事实已证实偷税。",
                    "该行为必然构成逃税罪。",
                    "该笔款项即是账外收入。"):
            out = self._clean(raw)
            self.assertNotEqual(out, raw, raw)

    def test_no_leftover_offence_char(self):
        """贪婪匹配：罪名必须整体吃掉，不得残留单个「罪」字"""
        out = self._clean("该行为必然构成逃税罪。")
        self.assertNotIn("罪", out)

    def test_legal_citation_untouched(self):
        raw = "依据《税收征收管理法》第六十三条，构成偷税的可处五倍以下罚款。"
        self.assertEqual(self._clean(raw), raw, "法条引文不得被改写")

    def test_normal_text_untouched(self):
        for raw in ("本科目余额与明细账一致，会计处理符合规定。",
                    "该支出构成成本的一部分。",
                    "该公司属小型微利企业。",
                    "该合同构成民事法律行为。"):
            self.assertEqual(self._clean(raw), raw, raw)

    def test_idempotent(self):
        """净化必须幂等：报告闸门可能对同一字符串多次净化"""
        from engine.enterprise_report import _zh_normalize_obj
        for raw in ("部分收入经个人账户归集，是账外收款的直接证据。",
                    "如无真实交易，构成虚开增值税发票→补税+罚款+刑事责任。",
                    "依据《税收征收管理法》第六十三条，构成偷税的可处五倍以下罚款。"):
            once = _zh_normalize_obj(raw)
            self.assertEqual(_zh_normalize_obj(once), once, raw)


class TestRedlineMatchGrounded(unittest.TestCase):
    """契约 2：红线配对必须有具体信号 + 资料可查，否则不配对。"""

    AVAIL = ["银行流水", "销项发票", "进项发票", "记账凭证",
             "工资表", "社保明细", "科目余额表", "增值税申报表"]

    def test_tax_name_overlap_alone_cannot_pair(self):
        """仅"税种名相同"不得配对：增值税进项差异不得挂到固定资产红线"""
        from engine.tax_redlines import match_redline_grounded
        rl, info = match_redline_grounded(
            "增值税申报进项税额与进项发票税额月度差异",
            "增值税申报表进项税额合计192,463.32元，同期进项发票税额合计225,093.81元，差异-32,630.49元",
            self.AVAIL)
        self.assertIsNone(rl, "仅税种名相同就配对，会把不相干的构成要件写进报告")
        self.assertEqual(info["mode"], "unmatched")

    def test_no_material_no_pair(self):
        """红线所需资料本轮一份未提供 → 不得配对"""
        from engine.tax_redlines import match_redline_grounded
        rl, info = match_redline_grounded(
            "设备采购合同、发票与验收单缺失",
            "固定资产取得、投用与折旧的时点链条不闭合",
            ["工资表"])   # 只有工资表，固定资产类资料一份没有
        self.assertIsNone(rl)

    def test_correct_pair_still_works(self):
        from engine.tax_redlines import match_redline_grounded
        cases = [
            ("工资名册与社会保险人员范围差异",
             "工资名册中1人未在社保清单中出现", "工资表人数与社保参保人数不符"),
            ("成本费用虚列异常",
             "凭证费用合计远高于收入口径，费用率畸高", "成本费用虚列"),
            ("同一交易对手同时出现在客户与供应商清单",
             "进销项发票中2个交易对手同时出现在客户和供应商范围", "关联交易异常"),
        ]
        for title, text, expect_name in cases:
            rl, info = match_redline_grounded(title, text, self.AVAIL)
            self.assertIsNotNone(rl, f"{title} 应能配对")
            self.assertIn(expect_name, rl["name"], f"{title} 应配到「{expect_name}」")

    def test_declared_redline_id_always_honored(self):
        """扫描器显式声明 redline_id 时直接采用（无需文本可匹配）"""
        from engine.redline_engine import _map_finding
        rl, info = _map_finding({"type": "自定义发现", "redline_id": "RL-PTY-001"},
                                self.AVAIL)
        self.assertIsNotNone(rl)
        self.assertEqual(rl["id"], "RL-PTY-001")
        self.assertEqual(info["mode"], "declared")


class TestReasoningGrounded(unittest.TestCase):
    """契约 4：论证链的资料归属必须按"实际读取"，不得用模板声明的应查资料。"""

    def test_no_templated_material_claim(self):
        import io, json, os
        path = os.path.join("scripts", "four_reports", "company_1_api_result.json")
        if not os.path.exists(path):
            self.skipTest("无真实结果快照")
        d = json.load(io.open(path, encoding="utf-8"))
        rep = d.get("report") or d
        rd = (rep.get("comprehensive") or {}).get("redline_detection") or {}
        bad = []
        for grp in ("suspicions", "confirmed", "unconfirmed"):
            for s in (rd.get(grp) or []):
                r = str((s.get("argumentation") or {}).get("reasoning") or "")
                # 旧文案特征：把模板声明的资料路径说成"逐层核对出来的"
                if "这几类资料里逐层核对出来的" in r:
                    bad.append(s.get("redline_name"))
        self.assertEqual(bad, [], f"仍有论证链把应查资料写成已核对资料：{bad}")

    def test_reasoning_states_actual_materials(self):
        import io, json, os
        path = os.path.join("scripts", "four_reports", "company_1_api_result.json")
        if not os.path.exists(path):
            self.skipTest("无真实结果快照")
        d = json.load(io.open(path, encoding="utf-8"))
        rep = d.get("report") or d
        rd = (rep.get("comprehensive") or {}).get("redline_detection") or {}
        for grp in ("suspicions", "unconfirmed"):
            for s in (rd.get(grp) or [])[:5]:
                r = str((s.get("argumentation") or {}).get("reasoning") or "")
                self.assertIn("本轮实际读取到的资料是", r,
                              f"{s.get('redline_name')} 的论证未说明实际读取的资料")




class TestMetricKeyCoverage(unittest.TestCase):
    """契约 9：前端 `_renderCapMetrics` **直接打印键名** → metrics 键必须全中文。

    真实事故：`ar_unreceived_total`（应收账款**未**收合计）按词表逐词翻译成
    「**已接收**合计」——`un` 缺词被丢掉、`received`→已接收，**意思正好相反**；
    `ar_max_aging_days` → 「___日」。给企业的报告里出现一句意思反了的话。
    现 *只要有一个片段译不出，就整体保留原键*（宁可露英文，不产出错误中文），
    并由本测试逼出未映射的新键。
    """

    def test_all_known_metric_keys_translate_to_chinese(self):
        import re
        from engine.enterprise_report import _translate_key, KNOWN_ENGINE_METRIC_KEYS
        bad = []
        for k in KNOWN_ENGINE_METRIC_KEYS:
            out = _translate_key(k)
            if re.search(r"[A-Za-z]", out) or "_" in out:
                bad.append((k, out))
        self.assertEqual(bad, [], f"metrics 键未汉化（前端会直接打印给用户）：{bad}")

    def test_no_semantic_inversion(self):
        """关键语义必须正确（`未收` 不得译成 `已接收`）"""
        from engine.enterprise_report import _translate_key
        self.assertEqual(_translate_key("ar_unreceived_total"), "应收账款未收合计")
        self.assertNotIn("已接收", _translate_key("ar_unreceived_total"))

    def test_partial_translation_falls_back_to_original(self):
        """半翻译比不翻译更危险 → 有片段译不出时保留原键"""
        from engine.enterprise_report import _translate_key
        self.assertEqual(_translate_key("ar_unreceived_total_x"), "ar_unreceived_total_x")


class TestTransientNoiseCleanup(unittest.TestCase):
    """契约 10：主体名与诊断日志里的"脏值/内部结构"必须清掉。"""

    def test_subject_name_strips_stamp_annotation(self):
        """真实事故：`_subject_clues_from_text` 产出「公章）深圳海更数字传媒有限公司」。

        根因：旧去噪正则 `^[\\s:：\\-—=_（）()]+` 把「（」当标点先剥掉，
        剩「公章）：…」→ 括号注解再也匹配不上 → 连「公章）：」一起吃进主体名。
        """
        from main import _subject_clues_from_text
        for text in ("纳税人名称（公章）：深圳海更数字传媒有限公司",
                     "纳税人名称（公章）深圳海更数字传媒有限公司",
                     "单位名称（盖章）：某某有限责任公司"):
            names, _ = _subject_clues_from_text(text)
            for n in names:
                self.assertNotIn("公章", n, f"主体名含印章词：{n}")
                self.assertNotIn("（", n)
            self.assertTrue(names, f"{text} 应能提取到主体名")

    def test_subject_name_drops_stamp_only_segment(self):
        from main import _clean_subject_name
        self.assertEqual(_clean_subject_name("公章）深圳海更数字传媒有限公司"), "")
        self.assertEqual(_clean_subject_name("（公章）"), "")
        self.assertEqual(_clean_subject_name("某某有限公司（公章）"), "某某有限公司")

    def test_log_humanised(self):
        from engine.sentencekit import humanise_log_lines
        log = ["[秘笈自更新] 11层连续未触发: ['任务与权限', '全域扫描']",
               "[PROFILE] 数据库查询身份失败",
               "普通日志"]
        out = humanise_log_lines(log)
        for line in out:
            self.assertNotIn("['", line)
            self.assertNotIn("']", line)
        self.assertIn("任务与权限、全域扫描", out[0])
        self.assertEqual(out[1], log[1], "中文方括号前缀不得被误改")
        self.assertEqual(out[2], log[2])

    def test_log_internal_terms_neutralised(self):
        """日志面板也会展示 → 内部术语同样要换成业务语言（走共享护栏，不另写一份）"""
        from engine.sentencekit import humanise_log_lines
        out = humanise_log_lines(["[红线判定] 按红线组织线索链·证据链·论证链",
                                  "多假设推理: 1组竞争假设"])
        for line in out:
            for jargon in ("线索链", "证据链", "竞争假设"):
                self.assertNotIn(jargon, line, line)

    def test_cjk_punct_normalised(self):
        from engine.sentencekit import normalize_cjk_punct
        self.assertEqual(normalize_cjk_punct("激活16/21个模块, 跳过5个"),
                         "激活16/21个模块，跳过5个")
        self.assertEqual(normalize_cjk_punct("完成: 0个集群"), "完成：0个集群")
        # ASCII 语境不得被改
        self.assertEqual(normalize_cjk_punct("16/21 SKU:ABC 0.00"), "16/21 SKU:ABC 0.00")

    def test_guard_covers_all_string_fields(self):
        """文字护栏必须覆盖**全部字符串字段** —— 白名单式字段清单会漏掉新字段。

        真实事故：`adjudication`/`limitations`/`cleared_reason` 不在 `review_finding`
        的字段清单里 → 带着「竞争假设裁决」原样进报告数据。
        """
        from engine.text_guardrails import review_finding
        f = {"type": "测试", "redline_id": "RL-PTY-001",
             "adjudication": "正常经营假设胜出（经竞争假设裁决后排除）",
             "limitations": "销售侧须先作经营模式裁决",
             "cleared_reason": "竞争假设裁决：金额8.68元",
             "some_future_field": "本项证据链已闭环"}
        review_finding(f)
        for k in ("adjudication", "limitations", "cleared_reason", "some_future_field"):
            for jargon in ("裁决", "假设胜出", "竞争假设", "证据链"):
                self.assertNotIn(jargon, f[k], f"{k} 未净化：{f[k]}")
        self.assertEqual(f["redline_id"], "RL-PTY-001", "内部编号字段不得被改动")


class TestNoReprLeak(unittest.TestCase):
    """契约 5：报告文本**永远不得出现 Python repr**（内部数据结构泄漏）。

    真实事故：`clue_chain._metric_rows` 对"值为 list[dict]"的指标用 `str(x)[:16]`，
    报告正文出现：

        第2环：按收款人归集金额与频次，剔除已申报工资与报销——counterparty_count=2；
              examples=[{'counterparty':，{'counterparty'

    ——内部结构泄漏 + `[`/`{` 被截断成括号不闭合的残句。
    """

    REPR_MARKS = ("{'", "{'", "': ", "[{'", "}, {", "'}")

    def _assert_clean(self, s, ctx=""):
        for mark in self.REPR_MARKS:
            self.assertNotIn(mark, s, f"{ctx} 出现 Python repr 记号 {mark!r}: {s}")
        self.assertTrue(is_balanced(s), f"{ctx} 括号不闭合: {s}")

    def test_render_value_list_of_dicts(self):
        from engine.sentencekit import render_value
        v = {"person_account_count": 15,
             "matches": [{"name": "初永伟"}, {"name": "李昭阳"}]}
        out = render_value(v)
        self._assert_clean(out)
        self.assertIn("初永伟", out)
        self.assertNotIn("person_account_count", out, "英文键应已被汉化")

    def test_render_value_nested(self):
        from engine.sentencekit import render_value
        for v in ([{"counterparty": "X"}, {"counterparty": "Y"}],
                  {"a": {"b": {"c": {"d": 1}}}},
                  [1, 2, 3, 4, 5],
                  {"x": [{"k": "v"}, "s"]}):
            self._assert_clean(render_value(v), repr(v)[:40])

    def test_metric_rows_no_repr(self):
        from engine.clue_chain import _metric_rows
        rows = _metric_rows({"counterparty_count": 2,
                             "examples": [{"counterparty": "沙暴文化"}, {"counterparty": "另一家"}]})
        for k, v in rows:
            self._assert_clean(f"{k}={v}", "指标行")

    def test_sample_rows_no_repr(self):
        from engine.clue_chain import _sample_rows
        rows = _sample_rows({"evidence_rows": [
            {"counterparty": "甲", "amount": 100.0, "date": "2025-01-01", "note": "x"},
            {"counterparty": "乙", "amount": 200.0},
        ]})
        for r in rows:
            self._assert_clean(r, "样本行")

    def test_tooltip_style_values_readable(self):
        from engine.sentencekit import render_value
        self.assertEqual(render_value(None), "")
        self.assertEqual(render_value(True), "是")
        self.assertEqual(render_value(False), "否")
        self.assertEqual(render_value(1234.5), "1,234.50")


class TestClampText(unittest.TestCase):
    """契约 6：截断不得把括号切断（`X[:N]` 朴素截断会留下悬空左括号）。"""

    LONG = ("开票收入中有3,579,933.39元（占开票收入41.9%）未匹配到银行流水或第三方平台"
            "（财付通/支付宝等）收款记录。现实中存在三种可能：①客户赊账未付"
            "（应收账款增加，可能跨期回款）；②个人账户代收未转回；③收入未入账。")

    def test_never_unbalanced(self):
        from engine.sentencekit import clamp_text
        for n in range(10, 200, 7):
            out = clamp_text(self.LONG, n)
            self.assertTrue(is_balanced(out), f"clamp_text({n}) 不闭合: {out}")

    def test_short_text_untouched(self):
        from engine.sentencekit import clamp_text
        self.assertEqual(clamp_text("短文本", 200), "短文本")
        self.assertEqual(clamp_text("", 10), "")
        self.assertEqual(clamp_text(None, 10), "")

    def test_close_brackets(self):
        from engine.sentencekit import close_brackets
        self.assertEqual(close_brackets("甲（乙"), "甲（乙）")
        self.assertEqual(close_brackets("甲（乙）"), "甲（乙）")
        self.assertEqual(close_brackets("甲《乙"), "甲《乙》")


class TestEvidenceRequirementSplit(unittest.TestCase):
    """契约 7：证据项名切分也必须括号感知 + 不得剥掉括号字符。"""

    AVAIL = ["银行流水", "销项发票", "进项发票", "记账凭证",
             "工资表", "社保明细", "科目余额表", "增值税申报表"]

    def test_parenthesised_names_balanced(self):
        from engine.evidence_chain import build_evidence_chain
        names = [
            "与待证事实相关且依法获准核验的特定账户、期间和交易资料（含已销户账户）",
            "个人卡资金去向（是否回流公司或用于经营）",
            "六员个人账户完整流水",
        ]
        for n in names:
            ev = build_evidence_chain(
                {"type": "x"},
                {"evidence_chain": [{"role": "直接证据", "name": n, "purpose": ""}]},
                self.AVAIL)
            self.assertTrue(is_balanced(ev["elements"][0]["basis"]), n)

    def test_and_or_split_still_correct(self):
        from engine.evidence_chain import _material_requirements
        self.assertEqual(_material_requirements("劳动合同与用工名册"),
                         [["劳动合同"], ["用工名册"]])
        self.assertEqual(_material_requirements("付款银行流水或第三方支付凭证"),
                         [["付款银行流水", "第三方支付凭证"]])

    def test_all_redline_evidence_basis_balanced(self):
        """全量 68 红线 × 279 个证据项：basis 必须全部括号闭合"""
        from engine.evidence_chain import build_evidence_chain
        from engine.tax_redlines import all_redlines
        bad = []
        for rl in all_redlines():
            ev = build_evidence_chain({"type": "x"}, rl, self.AVAIL)
            for e in ev["elements"]:
                if not is_balanced(e["basis"]):
                    bad.append((rl.get("id"), e["name"]))
        self.assertEqual(bad, [], f"证据依据括号不闭合：{bad[:3]}")


class TestNoInternalMarkers(unittest.TestCase):
    """契约 8：面向读者的表述**不得带内部编号**；自动补全的 how_found 不得被截断成残句。"""

    def test_claim_has_no_redline_id(self):
        from engine.argumentation import build_argumentation
        from engine.clue_chain import build_clue_chain
        from engine.evidence_chain import build_evidence_chain
        from engine.tax_redlines import get_redline
        rl = get_redline("RL-PTY-001")
        f = {"type": "主营业务成本无对公付款",
             "detail": "成本中有100,000元未匹配到对公付款流水。",
             "independent_sources": ["进项发票", "银行流水"]}
        clue = build_clue_chain(f, rl)
        ev = build_evidence_chain(f, rl, ["进项发票", "银行流水"])
        arg = build_argumentation(f, rl, clue, ev)
        import re as _re
        self.assertNotRegex(arg["claim"], r"RL-[A-Z]+-\d+",
                            "claim 不得包含内部红线编号（编号由 redline_id 字段承载）")

    def test_autofilled_how_found_balanced(self):
        from engine.text_guardrails import review_finding
        f = {"type": "测试", "detail": "第一句。第二句（含括号；内含分号）这里是被截断的位置" + "补" * 60}
        review_finding(f)
        self.assertTrue(is_balanced(f.get("how_found", "")),
                        f"自动补全的 how_found 括号不闭合：{f.get('how_found')}")


class TestRealReportClean(unittest.TestCase):
    """真实报告快照的终检（快照不存在时跳过）。"""

    def _load(self):
        import os
        path = os.path.join("scripts", "four_reports", "company_1_api_result.json")
        if not os.path.exists(path):
            self.skipTest("无真实结果快照")
        import json
        d = json.load(open(path, encoding="utf-8"))
        return d.get("report") or d

    def test_no_unbalanced_brackets_in_report_text(self):
        import re
        rep = self._load()
        err = rep.get("enterprise_readable_report") or {}

        texts = []

        def walk(o):
            if isinstance(o, str):
                if len(o) >= 8 and re.search(r"[\u4e00-\u9fa5]", o):
                    texts.append(o)
            elif isinstance(o, dict):
                for k, v in o.items():
                    if k in ("rows", "columns"):
                        continue
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(err)
        unbalanced = [s[:80] for s in texts if not is_balanced(s)]
        self.assertEqual(unbalanced, [], f"报告存在括号不闭合片段：{unbalanced[:3]}")

    def test_no_repr_in_report_text(self):
        import json as _json
        rep = self._load()
        err = rep.get("enterprise_readable_report") or {}
        raw = _json.dumps(err, ensure_ascii=False)
        for mark in ("examples=[", "matches=[{", "'counterparty'", "'name':"):
            self.assertNotIn(mark, raw, f"报告出现内部结构记号 {mark!r}")


if __name__ == "__main__":
    unittest.main()
