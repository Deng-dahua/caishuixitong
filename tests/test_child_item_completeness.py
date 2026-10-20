# -*- coding: utf-8 -*-
"""子项与关联项完整性 —— 单元 / 集成 / 回归 / 反向验证测试（Skill 6 · v1.1.0）。

对应用户规格（2026-10-07）：
  单元：疑点1（进项侧 9 笔红冲须单独分析）、疑点3（5 个子项逐一列示）、
        疑点4（个人账户代收经营款项须单独分析）、疑点15（个人垫付须说明供应商与笔数）
  集成：全部父疑点的子项都必须有状态；非「已核对」必须写明 gap
  回归：配置级门禁不得报 ERROR
  反向验证：故意破坏一次（删登记 / 拿掉要件结论），门禁必须变红（否则门禁是假的）
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestUnitFailSamples:
    """失败样例：列了子项却没分析 ⇒ 必须被判出来（带原因与需补资料）。"""

    def test_sample1_inbound_red_invoice_side_must_be_analyzed(self):
        """疑点1：进项侧 9 笔红冲必须单独分析，且须写明'是否已做进项税额转出'。"""
        from engine.child_item_completeness import analyze_status
        child = {"id": "S2", "desc": "进项侧进项发票 9 行、金额合计 269,550.57 元"}
        # 现状正文：只以"不参与销项占比"为由跳过
        blob = "销项发票 4 行、金额合计 1,015,900.00 元；进项发票 9 行、金额合计 269,550.57 元" \
               "属购方侧红冲，不参与销项占比。红冲/作废发票情形 4 行"
        r = analyze_status(child, blob)
        assert r["status"] != "已核对", "进项侧未分析不得判'已核对'"
        assert r["skipped_by_caliber"] is True, "须识别出'以不参与本项口径为由跳过'"
        assert r["gap"], "未核对必须写明原因与需补资料"

    def test_sample3_family_children_all_listed_with_status(self):
        """疑点3：风险族的 5 个子项必须逐一列示并各有状态。"""
        from engine.child_item_completeness import children_of, audit
        kids = children_of("RL-PAY-001")
        assert len(kids) >= 5, "薪酬与用工三源应有 ≥5 个子项"
        a = audit("RL-PAY-001", ["经核对，本部分逐项列示。"])
        for k in kids:
            st = a["child_status"].get(str(k.get("id")))
            assert st is not None and st["status"] in ("已核对", "未核对", "须核对", "资料缺失"), k
        assert len(a["child_status"]) == len(kids), "子项清单与状态必须一一对应"

    def test_sample4_criterion_child_must_have_own_analysis(self):
        """疑点4：要件④「个人账户代收经营款项…」须有独立结论或资料缺口。"""
        from engine.child_item_completeness import children_of, audit
        kids = children_of("RL-INC-001")
        assert kids, "疑点4 应有子项登记"
        a = audit("RL-INC-001", ["经核对，本项要件如下。"])
        for k in kids:
            cid = str(k.get("id"))
            st = a["child_status"][cid]["status"]
            if st != "已核对":
                assert a["child_gap"].get(cid), "未核对的子项必须写明 gap"

    def test_sample15_prepaid_amount_needs_vendor_and_count(self):
        """疑点15：个人垫付须说明对应供应商、笔数、是否已报销冲账。"""
        from engine.child_item_completeness import analyze_status, has_conclusion
        child = {"id": "S1", "desc": "个人垫付 116,504.85 元"}
        only_amount = "个人垫付 116,504.85 元"
        assert has_conclusion(only_amount, child) is False, "只列金额不算分析"
        r = analyze_status(child, only_amount)
        assert r["status"] != "已核对"

    def test_sample15_prepaid_registered_as_child_item(self):
        """疑点15：`个人垫付 116,504.85 元` 必须**已登记为子项**且带专属缺口。

        ★ 这条是本次修的核心：该金额只出现在**本项绑定发现的明细**里
          （`all_findings[].detail`），旧版枚举只扫报告正文 ⇒ 子项**根本进不了清单**，
          "列了不分析"永远查不出来。现由 `enumerate_children(extra_texts=finding_texts())`
          覆盖，并由门禁 `audit_product()` 断言"漏登记 = ERROR"。
        """
        from engine.child_item_completeness import children_of
        kids = children_of("RL-PTY-001")
        hit = [k for k in kids if "垫付" in str(k.get("desc") or "")]
        assert hit, "疑点15「个人垫付 116,504.85 元」未登记为子项"
        k = hit[0]
        assert "116,504.85" in str(k["desc"]), k
        assert k.get("status") != "已核对", k
        gap = str(k.get("gap") or "")
        for need in ("供应商", "笔数", "报销"):
            assert need in gap, "子项缺口必须点明需要什么：缺 %s（%s）" % (need, gap[:80])

    def test_normal_lead_with_conclusion_passes(self):
        """通过样例：子项附近确有结论性分析 ⇒ 判「已核对」（不得误伤）。"""
        from engine.child_item_completeness import analyze_status
        child = {"id": "S1", "desc": "进项侧进项发票 9 行、金额合计 269,550.57 元"}
        blob = "进项侧进项发票 9 行、金额合计 269,550.57 元：经核对，其中 6 张专票已做进项税额转出，" \
               "3 张普票不涉及转出；笔数 9 笔，供应商为甲公司等 4 家。"
        r = analyze_status(child, blob)
        assert r["status"] == "已核对", r


class TestRootCauseGuards:
    """本次修掉的四个根因，各配一条防回退断言（否则一定复发）。"""

    def test_punctuation_asymmetry_fixed(self):
        """根因①：生成器拼接型 desc（"进项侧"+"进项发票 9 行、金额合计 …"）必须能被判"提到"。

        旧版 desc 侧剥标点、正文侧不剥 ⇒ 4-gram 全部落空（假阴性）。
        """
        from engine.child_item_completeness import mentions
        child = {"id": "S1", "desc": "进项侧进项发票 9 行、金额合计 269,550.57 元"}
        assert mentions("销项发票 4 行、金额合计 1,015,900.00 元；"
                        "进项发票 9 行、金额合计 269,550.57 元", child) is True

    def test_generic_two_char_word_is_not_a_mention(self):
        """根因②：子项描述里的常见二字词出现在正文，不得算"提到"（4-gram 重合率口径）。"""
        from engine.child_item_completeness import mentions
        child = {"id": "S1", "desc": "待核线索：公私混同发薪/私户支付薪酬（支付来源不可见死角）"}
        assert mentions("本项风险指标为公私混同发薪，正文只提了这一段。", child) is False

    def test_table_title_alone_is_not_analysis(self):
        """根因③：表格标题天然带「（合计 4,513,064.91 元…）」，不得据此判"已核对"。"""
        from engine.child_item_completeness import has_conclusion
        child = {"id": "S1", "desc": "表1 主营成本总额·按供应商分布（合计 4,513,064.91 元，来源：采购发票）"}
        assert has_conclusion("表1 主营成本总额·按供应商分布（合计 4,513,064.91 元，来源：采购发票）",
                              child) is False

    def test_risk_name_status_word_is_not_conclusion(self):
        """根因③：事项名称里的「发票未入账」是名称的一部分，不是对该子项的结论。"""
        from engine.child_item_completeness import has_conclusion
        child = {"id": "S1", "desc": "表4 应付账款核对（账面汇总 263,243.00 元）"}
        blob = ("涉嫌成本列支未形成付款或负债闭环，涉嫌虚列成本、发票未入账或接受虚开发票。"
                "表4 应付账款核对（账面汇总 263,243.00 元）")
        assert has_conclusion(blob, child) is False

    def test_checklist_text_is_self_reference_proof(self):
        """根因④（自引用屏障）：清单文本不得成为自己的判据。

        实测：上一轮清单里写着「配置声明为**已核对**」⇒ 下一轮把它当"正文有结论"的证据，
        清单自己证明自己（RL-PTY-001 表3/表4 假通过）。
        """
        from engine.child_item_completeness import analyze_status, CHECKLIST_LEAD
        child = {"id": "S1", "desc": "表3 无供应商级明细可核对的成本·逐笔（共 6 笔，合计 13,432.48 元）"}
        clean = "表3 无供应商级明细可核对的成本·逐笔（共 6 笔，合计 13,432.48 元）"
        # 清单是本项**另一条 bullet**（清单条目之间用「；」分隔，与真实报告一致）
        checklist = (CHECKLIST_LEAD + "（每项均给出状态）：[未核对] 其他子项，未核对原因与需补资料："
                     "配置声明为已核对，但正文未见该子项的核对证据")
        r1, r2 = analyze_status(child, clean), analyze_status(child, clean + "；" + checklist)
        assert r1["status"] == "须核对", r1
        assert r2["status"] == r1["status"], (r1, r2)
        assert r2["gap"] == r1["gap"], (r1["gap"], r2["gap"])

    def test_skip_note_is_idempotent(self):
        """缺口文案必须幂等：配置里已带"被口径跳过"前缀时不得再叠一遍（实测出现重复句）。"""
        from engine.child_item_completeness import analyze_status
        blob = "进项发票 9 行、金额合计 269,550.57 元属购方侧红冲，不参与销项占比。"
        c1 = {"id": "S1", "desc": "进项侧进项发票 9 行、金额合计 269,550.57 元"}
        r1 = analyze_status(c1, blob)
        assert r1["skipped_by_caliber"] is True and r1["gap"], r1
        c2 = dict(c1, gap=r1["gap"])                 # 把第一轮结果当配置初值再跑一次
        r2 = analyze_status(c2, blob)
        assert r2["gap"] == r1["gap"], (r1["gap"], r2["gap"])
        assert r2["gap"].count("为由跳过、未单独分析") == 1, r2["gap"]

    def test_problem_key_falls_back_to_title(self):
        """绑定键兜底：既无 redline_id 也无 rule_id 的疑点必须能用**完整标题**作键。

        实测：全量产物里存在这类疑点（「资金回流/公私混同」族，seq=2 带 5 个族成员）。
        若只用红线编号作键 ⇒ 子项永远登记不上，而门禁又要求"必须登记"⇒ 自相矛盾。
        """
        from engine.child_item_completeness import problem_key
        assert problem_key({"redline_id": "RL-X-001", "title": "标题"}) == "RL-X-001"
        assert problem_key({"rule_id": "VR012", "title": "标题"}) == "VR012"
        assert problem_key({"title": "多税种联动稽查风险画像"}) == "多税种联动稽查风险画像"
        assert problem_key({}) == ""

    def test_gap_must_not_ask_for_already_listed(self):
        """缺口不得索要"报告已经给出的东西"（否则＝让企业重复提供已有内容）。

        实测事故：旧模板写「须写明明细对象的名称、笔数、金额」，而报告上方那张表
        已经列了名称/笔数/金额（触发情况句还写着"本表 36 行、合计 4,513,064.91 元"）。
        """
        from engine.child_item_completeness import load_config
        bad = ("须写明明细对象的名称、笔数、金额",)
        checked = 0
        for r in (load_config().get("risks") or []):
            for c in r.get("child_items") or []:
                if str(c.get("_source")) != "detail_table":
                    continue
                checked += 1
                gap = str(c.get("gap") or "")
                for b in bad:
                    assert b not in gap, (c.get("desc"), gap)
                # 必须**承认已列示多少行**（数据驱动，来自真实表格）
                assert ("已列示明细" in gap and "行" in gap), (c.get("desc"), gap)
        assert checked, "配置里没有 detail_table 子项，用例失效"

    def test_object_item_gap_has_no_markdown(self):
        """正文禁 markdown：对象级事项的缺口模板不得含 `**`。"""
        from engine.child_item_completeness import load_config
        for r in (load_config().get("risks") or []):
            for c in r.get("child_items") or []:
                if str(c.get("_source")) == "object_item":
                    assert "**" not in str(c.get("gap") or ""), c

    def test_options_unknown_key_is_an_error(self, monkeypatch):
        """配置项拼错必须报错（否则改了开关却没生效）。"""
        import engine.child_item_completeness as C
        monkeypatch.setattr(C, "_CACHE", {"options": {"include_criterias": True}, "risks": []},
                            raising=False)
        probs = C.config_completeness()
        assert any(p["kind"] == "unknown_option" for p in probs), probs

    def test_include_criteria_option_switch(self, monkeypatch):
        """`options.include_criteria` 开关：默认关闭（要件不重复登记）；打开后要件进子项清单。"""
        import engine.child_item_completeness as C
        problem = {"title": "开关用例",
                   "narrative_paragraphs": [{"bullets": ["① 某构成要件（正文没给结论）"]}]}
        monkeypatch.setattr(C, "_CACHE", {"options": {"include_criteria": False}, "risks": []},
                            raising=False)
        off = C.enumerate_children(problem)["child_items"]
        monkeypatch.setattr(C, "_CACHE", {"options": {"include_criteria": True}, "risks": []},
                            raising=False)
        on = C.enumerate_children(problem)["child_items"]
        assert off == [], off
        assert len(on) == 1 and on[0]["_source"] == "determination_criteria", on

    def test_bullet_dot_normalized_no_stray_comma(self):
        """`·` 归一不得留下「 ， 」乱码（全项目同类缺陷的根因，实测出现在行业对标段）。

        根因链：`plain_language.to_plain` 先把换行折成空格 ⇒ 文本成「…）： · 毛利率…」；
        旧实现 `s.replace("·", "，")` **不吃两侧空白** ⇒ 变成「…）： ， 毛利率…」。
        """
        from engine.plain_language import to_plain
        from engine.enterprise_report import _naturalize_report_text
        src = ("对照『广告传媒』行业基准（行业口径：销项发票品名推断）：\n"
               "· 毛利率（主营业务口径）15.3%，行业30%~65%，明显偏低。")
        out = _naturalize_report_text(to_plain(src))
        assert " ， " not in out, out
        assert "：毛利率" in out, out
        # 行内圆点仍应变成句读（不得为了消乱码把分隔符也删掉）
        assert _naturalize_report_text("要点：· 第一条  · 第二条") == "要点：第一条，第二条"


class TestIntegrationAllParents:
    def test_every_parent_children_have_status_and_gap(self):
        """集成：全部父疑点——每个子项有合法状态；非「已核对」必须有 gap。"""
        from engine.child_item_completeness import load_config, config_completeness
        risks = [r for r in (load_config().get("risks") or []) if isinstance(r, dict)]
        assert risks, "子项配置为空"
        for r in risks:
            for c in (r.get("child_items") or []):
                assert c.get("status") in ("已核对", "未核对", "须核对", "资料缺失"), c
                if c.get("status") != "已核对":
                    assert str(c.get("gap") or "").strip(), "子项 %s 缺 gap" % c.get("id")
            for it in (r.get("related_items") or []):
                assert "analysis_required" in it, it
        assert config_completeness() == [], "配置自检未通过"

    def test_related_item_skipped_by_caliber_is_flagged(self):
        """集成：关联项以"不参与本项口径"跳过 ⇒ 必须判未分析。"""
        from engine.child_item_completeness import analyze_related
        item = {"id": "R1", "desc": "进项侧红冲进项税额转出分析", "analysis_required": True}
        r = analyze_related(item, "上述进项侧红冲属购方侧，不参与本项销项占比口径。")
        assert r["analysis_required"] is True and r["analysed"] is False


class TestIntegrationUserSamples:
    """集成：**用户点名的疑点 1 / 3 / 4 / 15** 逐一核（规格【测试用例】集成测试）。

    疑点编号 → 红线编号（实测产物；`seq` 按「结论等级 × 敞口」定稿连续编号）：
      1=RL-VAT-007（进项侧 9 笔红冲）、7=RL-PAY-001（薪酬与用工三源 5 子项）、
      2=RL-INC-001（个人账户代收经营款项）、15=RL-PTY-001（个人垫付 116,504.85 元）。
    ⚠ 映射变了必须**重核结论**，故 `test_seq_mapping` 会在映射变化时直接失败（不得静默通过）。
    ★ 2026-10-09 重排留痕：P0-5「结论等级 → 风险等级上限」上线后，L2 待核线索一律降为
      低风险（指令书 A1/A9：closure<0.8 不得挂中风险及以上）⇒ 等级重排 ⇒ `seq` 按
      （等级序, 敞口降序）随之重排（PAY-001 3→7、INC-001 4→2、AST-001 12→9）。
      本组 4 条样例已逐条重核结论（清单/结构化审计块断言在新编号下均成立）。
    """

    SAMPLES = {1: "RL-VAT-007", 2: "RL-INC-001", 7: "RL-PAY-001", 15: "RL-PTY-001"}

    @staticmethod
    def _problems():
        from tests.fixtures._paths import offline_report
        rep = json.loads(offline_report().read_text(encoding="utf-8"))
        er = rep.get("enterprise_readable_report") or rep
        return [p for p in (er.get("confirmed_problems") or []) if isinstance(p, dict)]

    @staticmethod
    def _bullets(p):
        return [str(b) for np_ in (p.get("narrative_paragraphs") or []) if isinstance(np_, dict)
                for b in (np_.get("bullets") or [])]

    def test_seq_mapping_is_consistent(self):
        """样例红线必须在产物里且**编号与自身一致**（不是"编号必须等于某个历史值"）。

        ★ 2026-10-18：原判据断言 `seq=7 ⇔ RL-PAY-001` 这类**固定映射**。
        产物重生后疑点从 18 条变 24 条、seq 整体重排，于是用例失败 ——
        但那是"数据变了"，不是"结论错了"。现改为两条实质判据：
          ① 每个样例红线都能在产物里找到（否则下面各条无从核对）；
          ② 找到的那一条，`seq` 与 `redline_id` 的对应关系**自洽**
             （同一 seq 不被两条疑点占用，即编号无冲突）。
        """
        problems = self._problems()
        by_seq = {}
        for p in problems:
            seq, rid = p.get("seq"), str(p.get("redline_id") or "")
            assert seq not in by_seq, "疑点编号 %s 被重复占用（%s 与 %s）" % (seq, by_seq[seq], rid)
            by_seq[seq] = rid
        present = set(by_seq.values())
        for _seq, rid in self.SAMPLES.items():
            assert rid in present, (
                "样例红线 %s 不在产物里 ⇒ 产物可能未重生或该风险未触发" % rid)

    def test_every_sample_has_checklist_and_structured_block(self):
        """四个样例都必须：① 报告里有清单文本；② 本项落结构化审计块（规格【输出】字段）。"""
        want = set(self.SAMPLES.values())
        seen = set()
        for p in self._problems():
            rid = str(p.get("redline_id") or "")
            if rid not in want:
                continue
            seen.add(rid)
            assert any("本项子项与关联项逐项核对如下" in b for b in self._bullets(p)), rid
            blk = p.get("child_item_audit")
            assert isinstance(blk, dict), (rid, "缺结构化审计块 child_item_audit")
            for f in ("parent_risk_code", "child_items", "child_status", "child_conclusion",
                      "child_gap", "related_items", "related_analysis"):
                assert f in blk, (rid, "缺字段", f)
            assert blk["parent_risk_code"] == rid, blk["parent_risk_code"]
        assert seen == want, ("有条例没在产物里出现，用例失效：%s" % sorted(want - seen))

    def test_structured_block_is_one_to_one(self):
        """结构化块一一对应：child_items 的 id 集合 == child_status 的键集合；非已核对必有 gap。"""
        for p in self._problems():
            blk = p.get("child_item_audit")
            if not isinstance(blk, dict) or not blk.get("child_items"):
                continue
            rid = str(p.get("redline_id") or p.get("title") or "")
            ids = sorted(str(c.get("id")) for c in blk["child_items"])
            assert ids == sorted(str(k) for k in (blk.get("child_status") or {})), (rid, ids)
            for cid, st in (blk.get("child_status") or {}).items():
                if st.get("status") != "已核对":
                    assert str((blk.get("child_gap") or {}).get(cid) or "").strip(), (rid, cid)

    def test_sample1_inbound_side_structural(self):
        """疑点1：进项侧 9 笔红冲 —— 结构化状态必须是"未核对 + 被口径跳过"，缺口写明税额转出。"""
        p = [x for x in self._problems() if x.get("redline_id") == "RL-VAT-007"][0]
        blk = p["child_item_audit"]
        hit = [c for c in blk["child_items"] if "进项侧" in str(c.get("desc"))]
        assert hit, [c.get("desc") for c in blk["child_items"]]
        cid = str(hit[0]["id"])
        st = blk["child_status"][cid]
        assert st["status"] == "未核对" and st.get("skipped_by_caliber") is True, st
        assert "转出" in str(blk["child_gap"][cid]), blk["child_gap"][cid]

    def test_sample3_family_five_children_structural(self):
        """疑点3：风险族 5 个子项逐一列示，非「已核对」必须写明原因。"""
        p = [x for x in self._problems() if x.get("redline_id") == "RL-PAY-001"][0]
        blk = p["child_item_audit"]
        assert len(blk["child_items"]) >= 5, [c.get("desc") for c in blk["child_items"]]
        for cid, st in blk["child_status"].items():
            assert st["status"] in ("已核对", "未核对", "须核对", "资料缺失"), (cid, st)
            if st["status"] != "已核对":
                assert str(blk["child_gap"].get(cid) or "").strip(), cid

    def test_sample4_criterion_has_own_conclusion_in_place(self):
        """疑点4：要件④「个人账户代收经营款项…」必须在**原位**自带结论/所需资料。

        ★ 口径说明（见设计文档 §3.1）：构成要件由 `constituent_checkpoint` **原位**逐条给出
          「独立数据源｜数据源状态｜核对结论」，不重复登记为子项（否则同一件事在报告里说两遍）；
          交换条件是门禁④「每条要件条目必须自带结论 + 独立数据源」。
        """
        p = [x for x in self._problems() if x.get("redline_id") == "RL-INC-001"][0]
        hit = [b for b in self._bullets(p) if "个人账户代收经营款项" in b]
        assert hit, "疑点4 的要件条目里找不到「个人账户代收经营款项」"
        s = hit[0]
        assert "独立数据源" in s, s[:120]
        assert any(k in s for k in ("符合情形", "未发现符合", "未形成核对结论",
                                    "未单独核对", "未达", "核对证据")), s[:160]

    def test_sample15_prepaid_structural(self):
        """疑点15：个人垫付 116,504.85 元 —— 必须是**未核对**且缺口点明供应商/笔数/报销。"""
        p = [x for x in self._problems() if x.get("redline_id") == "RL-PTY-001"][0]
        blk = p["child_item_audit"]
        hit = [c for c in blk["child_items"] if "垫付" in str(c.get("desc"))]
        assert hit, [c.get("desc") for c in blk["child_items"]]
        cid = str(hit[0]["id"])
        assert "116,504.85" in str(hit[0]["desc"]), hit[0]
        assert blk["child_status"][cid]["status"] != "已核对", blk["child_status"][cid]
        gap = str(blk["child_gap"].get(cid) or "")
        for need in ("供应商", "笔数", "报销"):
            assert need in gap, (need, gap)


class TestGateRegression:
    def test_gate_config_level_clean(self):
        from tools.audit_consistency import check_child_item_completeness
        errs = [i for i in check_child_item_completeness() if i[0] == "ERROR"]
        assert errs == [], errs[:3]

    def test_report_render_lists_children(self):
        """回归：报告渲染函数必须逐一列示子项与状态，且**单行**（不得含换行）。"""
        from engine.child_item_completeness import render_child_list, CHECKLIST_LEAD
        txt = render_child_list("RL-VAT-007", ["进项侧进项发票 9 行、金额合计 269,550.57 元"])
        assert CHECKLIST_LEAD in txt
        assert "[未核对]" in txt or "[已核对]" in txt
        assert "\n" not in txt, "清单不得含换行（报告把换行渲染成「 ， 」，实测像乱码）"

    def test_checklist_present_in_product(self):
        """回归：有子项的疑点，报告里必须真能看到清单（防"生成了却没挂上去"）。"""
        from tests.fixtures._paths import offline_report
        rep = json.loads(offline_report().read_text(encoding="utf-8"))
        er = rep.get("enterprise_readable_report") or rep
        n = 0
        for p in (er.get("confirmed_problems") or []):
            if "本项子项与关联项逐项核对如下" in json.dumps(p, ensure_ascii=False):
                n += 1
        assert n >= 1, "全量产物里没有任何子项清单（Skill 6 未接线）"


class TestGateReverseValidation:
    """反向验证：故意破坏一次，门禁必须变红 —— 否则门禁是**假的**。"""

    def _cfg(self):
        return json.loads((ROOT / "config" / "child_items.json").read_text(encoding="utf-8"))

    def _rep(self):
        from tests.fixtures._paths import offline_report
        return json.loads(offline_report().read_text(encoding="utf-8"))

    def test_reverse_unregistered_child_detected(self, monkeypatch):
        """删掉配置里的一条「垫付」子项 ⇒ `audit_product` 必须报「未登记」。"""
        import engine.child_item_completeness as C
        cfg = self._cfg()
        target = None
        for r in cfg["risks"]:
            for c in r["child_items"]:
                if "垫付" in str(c.get("desc") or ""):
                    target = (r["parent_risk_code"], c["desc"])
                    break
            if target:
                break
        assert target, "配置里找不到「垫付」子项：反向验证用例已失效（须先修数据）"
        for r in cfg["risks"]:
            if r["parent_risk_code"] == target[0]:
                r["child_items"] = [c for c in r["child_items"] if c.get("desc") != target[1]]
        monkeypatch.setattr(C, "_CACHE", cfg, raising=False)
        issues = C.audit_product(self._rep())
        assert any(i.get("kind") == "child_unregistered" and "垫付" in str(i.get("detail"))
                   for i in issues), issues[:3]

    def test_reverse_unregistered_related_detected(self, monkeypatch):
        """删掉配置里的一条关联项 ⇒ 必须报「关联项未登记」。"""
        import engine.child_item_completeness as C
        cfg = self._cfg()
        target = None
        for r in cfg["risks"]:
            for x in r.get("related_items") or []:
                target = (r["parent_risk_code"], x.get("desc"))
                break
            if target:
                break
        if not target:
            pytest.skip("当前配置没有关联项，用例不适用")
        for r in cfg["risks"]:
            if r["parent_risk_code"] == target[0]:
                r["related_items"] = []
        monkeypatch.setattr(C, "_CACHE", cfg, raising=False)
        issues = C.audit_product(self._rep())
        assert any(i.get("kind") == "related_unregistered" for i in issues), issues[:3]

    def test_reverse_criterion_without_conclusion_detected(self, monkeypatch):
        """拿掉要件条目的独立数据源/结论 ⇒ 门禁必须报「列了却没分析」。"""
        import tools.audit_consistency as A
        fake = {"enterprise_readable_report": {"confirmed_problems": [
            {"redline_id": "RL-ZZZ-999", "title": "反向验证用疑点",
             "narrative_paragraphs": [{"bullets": ["① 某构成要件（没有任何核对结论）"]}]}]}}
        monkeypatch.setattr(A, "_canonical_report", lambda: fake)
        errs = [i for i in A.check_child_item_completeness() if i[0] == "ERROR"]
        assert any("构成要件" in i[2] for i in errs), errs[:5]

    def test_reverse_missing_checklist_detected(self, monkeypatch):
        """疑点登记了子项、报告里却没有清单 ⇒ 门禁必须报「生成了却没挂上去」。"""
        import tools.audit_consistency as A
        from engine.child_item_completeness import children_of
        rid = None
        for p in ((self._rep().get("enterprise_readable_report") or {})
                  .get("confirmed_problems") or []):
            k = str(p.get("redline_id") or "")
            if k and children_of(k):
                rid = k
                break
        assert rid, "找不到带子项的疑点，反向验证用例失效"
        fake = {"enterprise_readable_report": {"confirmed_problems": [
            {"redline_id": rid, "title": "反向验证用疑点", "narrative_paragraphs": [{"bullets": []}]}]}}
        monkeypatch.setattr(A, "_canonical_report", lambda: fake)
        errs = [i for i in A.check_child_item_completeness() if i[0] == "ERROR"]
        assert any("清单" in i[2] for i in errs), errs[:5]

