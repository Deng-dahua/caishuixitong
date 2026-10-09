# -*- coding: utf-8 -*-
"""报告**去重与去元话语**的测试（2026-10-06，用户评语「重复冗余占全文三分之一以上」）。

用户列的重复层次：
  · 结构层：同一内容在「总述/分述/结论/自我反驳/补资料」反复出现；
  · 声明层：「若不补充资料的后果」「未收到"合同文件"…」逐字重复几十次；
  · 元话语层：「本段是系统对自己结论的复核」等系统自述；
  · 表注层：同一表注每张表前都来一遍。

本组锁住四条规则（R1 元话语 / R2 段级上提 / R2b 句级上提 / R3 表注去重）
及其**边界**：只动逐字相同的共性文本，绝不改写本项特有的事实、金额、资料名。
"""
from __future__ import annotations


def _para(head, text):
    return {"heading": head, "text": text}


def _prob(title, paras):
    return {"title": title, "narrative_paragraphs": paras}


class TestMetaAndHoist:
    def test_meta_sentences_removed(self):
        from engine.report_dedup import dedup_report
        rep = {"confirmed_problems": [
            _prob("A", [_para("本轮检查结论",
                              "本项已读得银行流水 12 份。本段是系统对自己结论的复核。")]),
        ]}
        st = dedup_report(rep)
        assert st["meta_removed"] >= 1
        t = rep["confirmed_problems"][0]["narrative_paragraphs"][0]["text"]
        assert "系统对自己结论的复核" not in t
        assert "本项已读得银行流水 12 份" in t, "本项特有事实不得被删"

    def test_identical_paragraph_hoisted_once(self):
        from engine.report_dedup import dedup_report
        common = "如企业未补充上述资料、也未对相关情况作出合理解释，本项风险方向无法排除，可能影响相应期间的申报处理口径。"
        rep = {"confirmed_problems": [
            _prob("T%d" % i, [_para("若不补充资料的后果", common)]) for i in range(1, 5)
        ]}
        st = dedup_report(rep)
        assert st["hoisted"] >= 3
        for p in rep["confirmed_problems"]:
            assert not (p.get("narrative_paragraphs") or []), "共性段应全部从疑点删除"
        assert any(common in c["text"] for c in st["common_statements"])

    def test_idempotent(self):
        from engine.report_dedup import dedup_report
        common = "已取得的资料与待补充的资料：本轮未收到合同文件。"
        rep = {"confirmed_problems": [
            _prob("T%d" % i, [_para("已取得的资料与待补充的资料", common)]) for i in range(1, 5)
        ]}
        dedup_report(rep)
        st2 = dedup_report(rep)
        assert st2["hoisted"] == 0 and st2["sentences_hoisted"] == 0, "去重不是幂等的"


class TestSentenceLevelHoist:
    """R2b：共性段「整段不同、逐句相同」时必须按**句**上提。

    这是用户「同一份资料被要求三次」的直接病根：每个疑点缺的资料不同，
    故段级比对永远打不中，但同一句「未收到…」在 20+ 个疑点里一字不差。
    """

    @staticmethod
    def _rep(n=5):
        probs = []
        for i in range(1, n + 1):
            probs.append(_prob("T%d" % i, [_para(
                "已取得的资料与待补充的资料",
                "本项涉及第 %d 笔业务，已收到银行流水。" % i
                + "未收到「合同文件」导致相关检查未完成，该项风险方向本轮无法排除。")]))
        return {"confirmed_problems": probs}

    def test_repeated_sentence_hoisted_from_all_items(self):
        from engine.report_dedup import dedup_report
        rep = self._rep()
        st = dedup_report(rep)
        assert st["sentences_hoisted"] >= 5, st
        for i, p in enumerate(rep["confirmed_problems"], 1):
            texts = " ".join(x["text"] for x in (p.get("narrative_paragraphs") or []))
            assert "合同文件" not in texts, "共性句应全部从疑点删除（第 %d 项）" % i
            assert "第 %d 笔业务" % i in texts, "本项特有事实不得被删（第 %d 项）" % i
        assert any("合同文件" in c["text"] for c in st["common_statements"]), \
            "被删的共性句必须在报告级可查（否则等于删内容）"

    def test_sentence_hoist_is_idempotent(self):
        from engine.report_dedup import dedup_report
        rep = self._rep()
        dedup_report(rep)
        st2 = dedup_report(rep)
        assert st2["sentences_hoisted"] == 0, "句级去重不是幂等的"

    def test_short_boilerplate_not_hoisted(self):
        """边界：过短的句子不参与（避免误删有效短句）。"""
        from engine.report_dedup import dedup_report, _SENT_HOIST_MIN_CHARS
        assert _SENT_HOIST_MIN_CHARS >= 4
        probs = [_prob("T%d" % i, [_para("已取得的资料与待补充的资料", "同上。本项无差异。")])
                 for i in range(1, 5)]
        st = dedup_report({"confirmed_problems": probs})
        assert st["sentences_hoisted"] == 0, "过短句不应被上提"

    def test_non_hoistable_head_untouched(self):
        """边界：非共性段标题下的重复句**不**上提（那是本项特有叙述）。"""
        from engine.report_dedup import dedup_report
        same = "该条款要求按权责发生制确认收入。"
        probs = [_prob("T%d" % i, [_para("本项结论及理由", same + "第 %d 项差异。" % i)])
                 for i in range(1, 5)]
        st = dedup_report({"confirmed_problems": probs})
        assert st["sentences_hoisted"] == 0
        for p in probs:
            assert same in p["narrative_paragraphs"][0]["text"]


class TestContainerParagraphGuard:
    """★★ 2026-10-09（P0-5 收口）：**容器段不得被整段上提**。

    真实事故：13 个疑点的「五、需企业提供的资料与说明」段 `text` 都是同一句结构性引导句
    「要把这一项查清楚，需要：」（逐字相同）⇒ R2 判"逐字重复的共性段" ⇒ **整段删除**
    ⇒ 各自的 `bullets`（补件清单）与 `detail_table`（补件明细表）被一起删掉。
    前端 `_renderNarrativeBody`/`_renderBullets` 确实渲染这两个字段 ⇒ **用户可见内容真丢**，
    且报告里该疑点**整环消失**（16 项里 13 项缺 request 环）。

    判据（唯一权威 `has_visible_payload`）：段级删除粒度是"整段"，
    带可见载荷的段落一律不参与段级上提；共同的**句子**交给句级（R2b）处理。
    """

    _LEAD = "要把这一项查清楚，需要："

    @staticmethod
    def _rep(with_payload=True):
        probs = []
        for i in range(1, 5):
            para = {"heading": "五、需企业提供的资料与说明", "text": TestContainerParagraphGuard._LEAD}
            if with_payload:
                para["bullets"] = ["本项专属补件材料%d" % i]
                para["detail_table"] = {"title": "补件明细", "rows": [{"材料": "M%d" % i}]}
            probs.append(_prob("T%d" % i, [para]))
        return {"confirmed_problems": probs}

    def test_container_paragraph_survives_with_payload(self):
        from engine.report_dedup import dedup_report
        rep = self._rep(with_payload=True)
        dedup_report(rep)
        for i, p in enumerate(rep["confirmed_problems"], 1):
            paras = p.get("narrative_paragraphs") or []
            assert paras, "容器段被整段删除（第 %d 项）" % i
            bl = paras[0].get("bullets") or []
            assert bl == ["本项专属补件材料%d" % i], "本项专属补件清单被删（第 %d 项）" % i
            dt = paras[0].get("detail_table") or {}
            assert dt.get("rows") == [{"材料": "M%d" % i}], "补件明细表被删（第 %d 项）" % i

    def test_reverse_verification_payload_free_is_still_hoisted(self):
        """反向验证（判据自证非假）：**去掉载荷**后必须照旧被上提 ——
        否则"保住了"只是巧合，不是护栏生效。"""
        from engine.report_dedup import dedup_report
        rep = self._rep(with_payload=False)
        st = dedup_report(rep)
        assert st["hoisted"] >= 3, "无载荷的同文段应照旧上提（护栏不得退化为一律不动）"
        for p in rep["confirmed_problems"]:
            assert not (p.get("narrative_paragraphs") or []), "无载荷同文段应被删除"

    def test_structural_lead_not_hoisted_by_sentence_level(self):
        """结构性引导句（`is_orphan_lead`）不得被句级上提（会渲染成"有标题没内容"）。

        ⚠ 构造要点：段文本**各不相同**（否则段级 R2 会把整段上提，那是正确行为，
          测不到句级判据）。故每段带本项专属句，共性只有那句引导句 + 一句中性共性句。
        """
        from engine.report_dedup import is_structural_lead, dedup_report
        assert is_structural_lead(self._LEAD)
        neutral = "本报告不作定性，在补证核实之前既不认定违法，也不予排除。"
        probs = [_prob("T%d" % i, [
            {"heading": "若不补充资料的后果",
             "text": self._LEAD + "本项第%d项专属情形。" % i + neutral}])
            for i in range(1, 5)]
        rep = {"confirmed_problems": probs}
        st = dedup_report(rep)
        assert any(neutral[:16] in str(c.get("text") or "") for c in st["common_statements"]), \
            "中性共性句应被上提（否则本测试测的不是 R2b 的排除项）"
        assert not any(str(c.get("text") or "").startswith(self._LEAD.rstrip("："))
                       for c in st["common_statements"]), "结构性引导句被上提到报告级"
        for i, p in enumerate(rep["confirmed_problems"], 1):
            t = "".join(x["text"] for x in (p.get("narrative_paragraphs") or []))
            assert self._LEAD.rstrip("：") in t, "引导句被判据误删（第 %d 项）" % i
            assert "第%d项专属情形" % i in t, "本项专属句被误删（第 %d 项）" % i

    def test_real_heading_一_set_is_untouched_by_guard(self):
        """反向锁：护栏只影响带载荷的段，普通同文段照旧上提（不因新护栏退化）。"""
        from engine.report_dedup import dedup_report
        same = "本报告不作定性，在补证核实之前既不认定违法，也不予排除。"
        probs = [_prob("T%d" % i, [_para("若不补充资料的后果", same)]) for i in range(1, 5)]
        rep = {"confirmed_problems": probs}
        st = dedup_report(rep)
        assert st["hoisted"] + st["sentences_hoisted"] >= 4, st


class TestTableNoteDedup:
    def test_same_note_kept_once(self):
        from engine.report_dedup import dedup_report
        note = "本表列出的是该风险事项所依据的基础逐笔明细（全量）。"
        probs = [{"title": "T%d" % i, "detail_table": {"title": "t", "rows": [], "note": note}}
                 for i in range(1, 4)]
        st = dedup_report({"confirmed_problems": probs})
        assert st["table_notes_removed"] >= 2
        kept = [p["detail_table"]["note"] for p in probs]
        assert kept.count(note) == 1, kept

    def test_both_table_shapes_scanned(self):
        """★ 明细表有「单数 detail_table」与「复数 detail_tables」两处，枚举必须两者都扫。"""
        from engine.report_dedup import dedup_report
        note = "本表口径：仅列示与本项方向一致的明细行。"
        probs = [
            {"title": "T1", "detail_table": {"title": "t", "rows": [], "note": note}},
            {"title": "T2", "narrative_paragraphs": [
                {"heading": "要件核对", "detail_tables": [
                    {"title": "t2", "rows": [], "note": note}]}]},
            {"title": "T3", "narrative_paragraphs": [
                {"heading": "要件核对", "detail_tables": [
                    {"title": "t3", "rows": [], "note": note}]}]},
        ]
        st = dedup_report({"confirmed_problems": probs})
        assert st["table_notes_removed"] >= 2, "复数 detail_tables 未被扫描"


class TestLeftoverDuplicateDetector:
    """`find_leftover_duplicates` 是闸门判据的**唯一权威**（闸门不得自写一套计数）。

    反向验证：未去重的报告必须被探测到（段级 + 句级都要），去重后必须归零
    —— 若探测器打不中，"闸门绿"就只是"判据没生效"。
    """

    @staticmethod
    def _dirty():
        probs = []
        for i in range(1, 6):
            probs.append(_prob("T%d" % i, [
                _para("若不补充资料的后果", "如企业未补充上述资料、也未对相关情况作出合理解释，本项风险方向无法排除，可能影响相应期间的申报处理口径。"),
                _para("已取得的资料与待补充的资料",
                      "本项涉及第 %d 笔业务。" % i
                      + "未收到「合同文件」导致相关检查未完成，该项风险方向本轮无法排除。"),
            ]))
        return {"confirmed_problems": probs}

    def test_detects_both_granularities(self):
        from engine.report_dedup import find_leftover_duplicates
        left = find_leftover_duplicates(self._dirty())
        assert left["paragraphs"], "段级残留未被探测到"
        assert left["sentences"], "句级残留未被探测到"
        assert all(n >= 3 for _, n, _ in left["paragraphs"] + left["sentences"])

    def test_clean_after_dedup(self):
        from engine.report_dedup import dedup_report, find_leftover_duplicates
        rep = self._dirty()
        dedup_report(rep)
        left = find_leftover_duplicates(rep)
        assert not left["paragraphs"], left["paragraphs"]
        assert not left["sentences"], left["sentences"]

    def test_same_item_repeats_count_once(self):
        """同一疑点内重复出现只计 1 次（判据是"跨疑点重复"）。"""
        from engine.report_dedup import find_leftover_duplicates
        one = _prob("T1", [
            _para("若不补充资料的后果", "如企业未补充上述资料、也未对相关情况作出合理解释，本项风险方向无法排除，可能影响相应期间的申报处理口径。"),
            _para("若不补充资料的后果", "如企业未补充上述资料、也未对相关情况作出合理解释，本项风险方向无法排除，可能影响相应期间的申报处理口径。"),
            _para("若不补充资料的后果", "如企业未补充上述资料、也未对相关情况作出合理解释，本项风险方向无法排除，可能影响相应期间的申报处理口径。"),
        ])
        left = find_leftover_duplicates({"confirmed_problems": [one]})
        assert not left["paragraphs"], "单疑点内重复被误判为跨疑点共性"


class TestHoistableHeadMatching:
    """★ 2026-10-06 事故（"注释说 A、代码做 B"）：共性段标题匹配曾**精确相等**，
    而真实标题带序号前缀（「三、已取得的资料与待补充的资料」）或用另一种措辞
    （「若不补证的后果」），⇒ 3/3 漏配 ⇒ 去重引擎接上了却**什么都没上提**。

    修法：标题先 `norm_head` 归一（去序号前缀/空白），再按**模式**判定。
    """

    def test_real_headings_are_recognized(self):
        from engine.report_dedup import is_hoistable_head
        for h in ("若不补证的后果", "若不补充资料的后果",
                  "三、已取得的资料与待补充的资料", "五、需企业提供的资料与说明",
                  "本项可能错在哪里：自我反驳与验证清单",
                  "二、已取得的资料与待补充的资料"):
            assert is_hoistable_head(h), h

    def test_item_specific_headings_rejected(self):
        """反向锁：本项特有的段落不得被当成共性段（否则会删掉每项独有内容）。"""
        from engine.report_dedup import is_hoistable_head
        for h in ("四、本项结论及理由", "二、发现的依据", "一、涉及的风险事项",
                  "本项检查过程", "三、证据与金额底稿", ""):
            assert not is_hoistable_head(h), h

    def test_norm_head_strips_ordinal(self):
        from engine.report_dedup import norm_head
        assert norm_head("三、已取得的资料与待补充的资料") == "已取得的资料与待补充的资料"
        assert norm_head("（三）已取得的资料与待补充的资料") == "已取得的资料与待补充的资料"
        assert norm_head("三. 已取得的资料与待补充的资料") == "已取得的资料与待补充的资料"
        assert norm_head(" 若不补证的后果 ") == "若不补证的后果"

    def test_real_heading_dedup_actually_fires(self):
        """端到端：用**真实标题**造的重复报告，去重必须真的生效（修前为 0 上提）。"""
        from engine.report_dedup import dedup_report, find_leftover_duplicates
        probs = []
        for i in range(1, 6):
            probs.append(_prob("T%d" % i, [
                _para("三、已取得的资料与待补充的资料",
                      "本项涉及第 %d 笔业务。" % i
                      + "未收到「合同文件」导致相关检查未完成，该项风险方向本轮无法排除。"),
                _para("若不补证的后果", "如企业未补充上述资料、也未对相关情况作出合理解释，本项风险方向无法排除，可能影响相应期间的申报处理口径。"),
            ]))
        rep = {"confirmed_problems": probs}
        assert find_leftover_duplicates(rep)["paragraphs"], "构造数据应含残留重复"
        st = dedup_report(rep)
        assert st["hoisted"] >= 5 and st["sentences_hoisted"] >= 5, st
        left = find_leftover_duplicates(rep)
        assert not left["paragraphs"] and not left["sentences"]
        for i, p in enumerate(rep["confirmed_problems"], 1):
            t = " ".join(x["text"] for x in (p.get("narrative_paragraphs") or []))
            assert "第 %d 笔业务" % i in t, "本项特有事实被误删（第 %d 项）" % i


class TestNatureAndItemSpecificNotHoisted:
    """★★ 2026-10-06 **真实回归**（比"闸门报错"严重）：上提把**税款专属**法条句抽到报告级，
    报告级那段话对**所有**事项都成立 ⇒ 文建费/社保等**非税**事项也被套上征管法偷税条款，
    用户评语 #4「税费法律适用混同」被去重悄悄打回原形。

    两条保护（数据驱动，新增一种费/基金只加一行）：
      · **性质专属**：句子落在任一 `levy_nature.LEVIES[*].consequence/basis` 内 ⇒ 不上提；
      · **本项专属**：含本项自己涉嫌情形的结论句（「本项存在被认定为…」）⇒ 不上提。
    """

    _TAX_SENT = "主管税务机关可依《税收征收管理法》第三十二条加收滞纳金"
    _NEUTRAL = "本报告不作定性，在补证核实之前既不认定违法，也不予排除。"

    def test_nature_specific_sentence_detected(self):
        from engine.report_dedup import _is_nature_specific, _norm_key
        assert _is_nature_specific(_norm_key(self._TAX_SENT)), self._TAX_SENT
        assert not _is_nature_specific(_norm_key(self._NEUTRAL))

    def test_item_specific_sentence_detected(self):
        from engine.report_dedup import _sentence_not_hoistable, _norm_key
        assert _sentence_not_hoistable(_norm_key("本项存在被认定为「少缴税款」的风险"))
        assert not _sentence_not_hoistable(_norm_key(self._NEUTRAL))

    def test_mixed_nature_report_not_contaminated(self):
        """税项与非税项混排时，非税项的后果段**不得**出现征管法条文。"""
        from engine.report_dedup import dedup_report
        probs = []
        for i in range(1, 5):
            probs.append(_prob("税%d" % i, [_para(
                "若不补充资料的后果",
                "本项存在被认定为少缴税款的风险。" + self._TAX_SENT + "。" + self._NEUTRAL)]))
        for i in range(1, 5):
            probs.append(_prob("非税%d" % i, [_para(
                "若不补充资料的后果",
                "本项存在被认定为未申报的风险。文化事业建设费是政府性基金，不是税，"
                "不适用《税收征收管理法》偷税条款。" + self._NEUTRAL)]))
        rep = {"confirmed_problems": probs}
        dedup_report(rep)
        for p in rep["confirmed_problems"]:
            if not p["title"].startswith("非税"):
                continue
            t = " ".join(x["text"] for x in (p.get("narrative_paragraphs") or []))
            assert "第三十二条" not in t and "第六十三条" not in t, \
                "非税事项被上提的税款专属法条污染：%s" % t

    def test_tax_specific_sentence_stays_in_items(self):
        """税项自己的专属句必须留在该项（不得被抽到报告级）。"""
        from engine.report_dedup import dedup_report
        probs = [_prob("税%d" % i, [_para(
            "若不补充资料的后果",
            "本项存在被认定为少缴税款的风险。" + self._TAX_SENT + "。")]) for i in range(1, 5)]
        rep = {"confirmed_problems": probs}
        st = dedup_report(rep)
        assert not any(self._TAX_SENT[:20] in c["text"] for c in st["common_statements"]), \
            "税款专属句被抽到了报告级（会被套到非税事项上）"
        for i, p in enumerate(rep["confirmed_problems"], 1):
            assert self._TAX_SENT in p["narrative_paragraphs"][0]["text"], \
                "税款专属句应从本项保留（第 %d 项）" % i

    def test_neutral_boilerplate_still_hoisted(self):
        """反向锁：**中性**共性句仍必须被上提（否则去重退化为"什么都做不了"）。"""
        from engine.report_dedup import dedup_report
        probs = [_prob("T%d" % i, [_para("若不补充资料的后果", self._NEUTRAL)])
                 for i in range(1, 5)]
        rep = {"confirmed_problems": probs}
        st = dedup_report(rep)
        assert st["hoisted"] + st["sentences_hoisted"] >= 4, st
        assert any(self._NEUTRAL[:16] in c["text"] for c in st["common_statements"])


class TestConsequenceHeadRecognition:
    """★ 2026-10-06（又一例"注释说 A、代码做 B"）：后果段标题识别必须**唯一权威**。

    闸门原用 `"若不补证" in heading` 识别，而**产物里的标题是「若不补充资料的后果」**
    （"若不补充"里没有子串"若不补证"）⇒ 段长恒为 0 ⇒ 判据形同虚设 / 假报 ERROR
    （实测：文建费项被判"未点出政府性基金"，文本里明明写着）。
    """

    def test_all_real_variants_recognized(self):
        from engine.report_dedup import is_consequence_head
        for h in ("若不补证的后果", "若不补充资料的后果",
                  "若不补充资料可能承担的后果", "二、若不补证的后果",
                  "若不补充资料、也不作出解释的后果"):
            assert is_consequence_head(h), h

    def test_other_headings_rejected(self):
        from engine.report_dedup import is_consequence_head
        for h in ("四、本项结论及理由", "三、已取得的资料与待补充的资料",
                  "为何列入检查", "", "后果说明"):
            assert not is_consequence_head(h), h

    def test_gate_uses_the_authority_not_a_literal(self):
        """闸门不得再写 `"若不补证" in heading` 这类字面判据（会与实际标题错配）。

        ⚠ 必须在**纯代码视图**上判：项目到处是"原先写 X"的修复说明注释，
          直接扫原文会被注释里的旧写法命中（本测试自己就踩过一次）。
        """
        from pathlib import Path
        import sys
        root = Path(__file__).resolve().parents[1]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from tools.audit_consistency import _mask_py_comments_and_strings as _mask
        src = (root / "tools" / "audit_consistency.py").read_text(encoding="utf-8")
        code = _mask(src)
        assert '"若不补证" in' not in code, \
            "闸门仍用字面标题判断后果段（实际标题是「若不补充资料的后果」⇒ 判据失灵）"
        assert "is_consequence_head" in code, "闸门未转发后果段标题的唯一权威"


class TestOffTopicRowsFiltered:
    """★★ 2026-10-06（用户复核疑点2：「工资表人数与社保参保人数不符」下表里 30 行中
    28 行是"工资社保均有"）：
    > 「你给出的数据……不仅不能证明"人数不符"，反而恰恰说明这些人在社保名单里是存在的。
    >   把它们放在"人数不符"的疑点下，属于**证据与论点不匹配**，同时造成了严重的篇幅冗余。」

    通用判据（不认表名、不认企业）：
      R-a 差异/异常类主题下，状态列标记"本行无差异"的行**不是本项证据** ⇒ 剔除（剔空则整表不挂）；
      R-b 多张表**对象集合相同**时只保留最聚合的一张（同一批数据在一项里呈现多遍是纯冗余）。
    ⚠ 标记词必须窄（不得用"一致/相符/正常/未发现"，它们会命中要件核对表的正常行）。
    """

    _SUBJ = "工资表人数与社保参保人数不符"

    @staticmethod
    def _pair_table():
        rows = []
        for m in range(1, 13):
            rows.append({"序号": m, "姓名": "初永伟", "月份": "2025-%02d" % m,
                         "工资": 30000, "社保基数": 6000,
                         "匹配状态": "工资社保均有", "来源资料": "工资名册与社保清单"})
        for m in (1, 2):
            rows.append({"序号": 100 + m, "姓名": "杨莹", "月份": "2025-%02d" % m,
                         "工资": 8500, "社保基数": 0,
                         "匹配状态": "仅有工资无社保", "来源资料": "工资名册与社保清单"})
        return {"title": "工资名册与社会保险人员范围差异（共14笔）",
                "columns": ["序号", "姓名", "月份", "工资", "社保基数", "匹配状态", "来源资料"],
                "rows": rows}

    @staticmethod
    def _agg_table():
        return {"title": "工资名册有、社保参保无（工资表 6 人、社保 5 人，差 1 人）",
                "columns": ["序号", "人员", "工资表内工资合计（元）", "说明"],
                "rows": [{"序号": 1, "人员": "杨莹", "工资表内工资合计（元）": "17,000.00",
                          "说明": "在工资表名册内、未见于社保参保名单"}]}

    def test_normal_rows_dropped_and_duplicate_tables_collapsed(self):
        from engine.enterprise_report import _filter_rows_off_topic
        out, off, notes = _filter_rows_off_topic(
            [self._pair_table(), self._agg_table()], self._SUBJ)
        assert off >= 12, off
        assert len(out) == 1, [t["title"] for t in out]
        # 保留的应是**最聚合**的那张（1 行/对象），而不是 14 行的人月表
        assert len(out[0]["rows"]) == 1, out[0]["rows"]
        assert "17,000.00" in str(out[0]["rows"][0]), out[0]["rows"][0]
        assert out[0].get("scope_note"), "剔除必须如实披露（不得静默丢数据）"

    def test_non_diff_subject_keeps_everything(self):
        """反向锁：**非差异主题**下一行都不动（避免误删正常清单）。"""
        from engine.enterprise_report import _filter_rows_off_topic
        tabs = [self._pair_table()]
        out, off, notes = _filter_rows_off_topic(tabs, "工资表列支情况说明")
        assert off == 0 and len(out[0]["rows"]) == 14

    def test_broad_words_are_not_normal_marks(self):
        """反向锁：宽词（一致/相符/正常/未发现）**不得**被判成"无差异"。"""
        from engine.enterprise_report import _is_normal_row
        for st in ("未单独核对（独立数据源本轮未取得）", "未发现符合该要件情形",
                   "一致", "相符", "正常", "已有", "缺失", "须核对"):
            assert not _is_normal_row({"核对结论": st}), st
        for st in ("工资社保均有", "无差异", "不存在差异", "无异常", "匹配成功"):
            assert _is_normal_row({"匹配状态": st}), st

    def test_dangling_upper_table_reference_removed(self):
        """删表后必须清掉"与上表…"的悬空引用（读者找不到那张表）。"""
        from engine.enterprise_report import _filter_rows_off_topic
        _t = self._agg_table()
        _t["title"] = ("工资名册有、社保参保无（工资表 6 人、社保 5 人，差 1 人）"
                       "（同一批差异：与上表「有工资无社保」是同一批对象，不另计金额）")
        _dup = {"title": "有工资无社保（共2组）", "columns": ["序号", "人员"],
                "rows": [{"序号": 1, "人员": "杨莹"}, {"序号": 2, "人员": "杨莹"}]}
        out, off, notes = _filter_rows_off_topic([self._pair_table(), _dup, _t], self._SUBJ)
        kept = [t for t in out]
        assert len(kept) == 1, [t["title"] for t in kept]
        assert "上表" not in str(kept[0].get("title")), kept[0]["title"]
