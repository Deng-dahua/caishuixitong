# -*- coding: utf-8 -*-
"""**风险等级唯一权威**的跨模块一致性测试（2026-10-06，用户评语 #1「风险等级前后矛盾」）。

病根：同仓并存 6 张"等级→序数"表，对「信息 vs 低风险」给出**相反答案**
⇒ 同一事项在不同章节被判成不同等级，读者看到"第 4 章高风险、第 7 章中风险"。

本组测试锁住三件事（任一处漂移即变红）：
  ① 权威表的不变量（单调性、证据状态不受压制、上限压制生效）；
  ② 各消费模块**确实转发**权威（不得再自建第二张表）；
  ③ 跨模块一致性：同一等级在各模块算出的相对次序**完全相同**。
"""
from __future__ import annotations

import inspect


class TestRiskLevelsAuthority:
    """① 权威表不变量。"""

    def test_legal_levels_and_grades(self):
        from engine import risk_levels as RL
        assert RL.LEGAL_LEVELS == ("极高风险", "高风险", "中风险", "低风险", "待核验", "信息")
        # 「待核验」是证据状态，不进入可比风险档
        assert "待核验" not in RL.RISK_GRADES
        assert set(RL.RISK_GRADES) | set(RL.EVIDENCE_STATES) == set(RL.LEGAL_LEVELS)

    def test_severity_is_monotonic_and_info_is_mildest(self):
        from engine import risk_levels as RL
        seq = ["信息", "低风险", "中风险", "高风险", "极高风险"]
        vals = [RL.severity(x) for x in seq]
        assert vals == sorted(vals) and len(set(vals)) == len(vals), vals
        # 关键不变量：「信息」不得重于「低风险」（旧 pipeline._sev 的病根）
        assert RL.severity("信息") < RL.severity("低风险")
        # 未知/空等级低于一切已知等级（不得顶掉真风险）
        assert RL.severity("表外等级") < RL.severity("信息")
        assert RL.severity("") < RL.severity("信息")

    def test_present_order_matches_declared_intent(self):
        from engine import risk_levels as RL
        assert RL.present_order("极高风险") < RL.present_order("高风险") \
            < RL.present_order("中风险") < RL.present_order("低风险")
        # 证据状态放最末，且不得插进风险档之间
        assert RL.present_order("待核验") > RL.present_order("低风险")
        assert RL.present_order("信息") > RL.present_order("低风险")
        assert RL.present_order("表外等级") == 99

    def test_normalize_buckets_unknown_to_info(self):
        from engine import risk_levels as RL
        assert RL.normalize("优惠机会") == "信息"      # 机会流词汇
        assert RL.normalize("高风险") == "高风险"
        assert RL.normalize("") == ""

    def test_cap_level_semantics(self):
        from engine import risk_levels as RL
        assert RL.cap_level("高风险", "中风险") == ("中风险", "高风险")
        assert RL.cap_level("中风险", "高风险") == ("中风险", "")    # 上行不压制
        assert RL.cap_level("高风险", "高风险") == ("高风险", "")
        # ★ 证据状态不参与压制（降级线索一律「待核验」，不得被「信息」压掉）
        assert RL.cap_level("待核验", "信息") == ("待核验", "")
        assert RL.cap_level("信息", "待核验") == ("信息", "")

    def test_worst_and_mildest(self):
        from engine import risk_levels as RL
        assert RL.worst(["低风险", "高风险", "信息"]) == "高风险"
        assert RL.mildest(["低风险", "高风险", "信息"]) == "信息"
        assert RL.worst([]) == "" and RL.mildest([]) == ""


class TestConsumersForwardToAuthority:
    """② 消费模块必须转发权威，不得自建第二张等级表。"""

    def test_enterprise_report_cap_uses_authority(self):
        from engine import enterprise_report as ER
        # 上限压制必须来自权威（不再是内联 `_rank = {...}`）
        src = inspect.getsource(ER._build_redline_problems)
        assert "_cap_level" in src, "上限压制未走权威 cap_level"
        assert '{"信息": -1' not in src, "仍有内联等级表"

    def test_finding_families_uses_authority(self):
        from engine import finding_families as FF
        src = inspect.getsource(FF.merge_families)
        assert "_risk_severity" in src, "同族选主事项未走权威 severity"

    def test_pipeline_uses_authority(self):
        from engine import pipeline as PL
        fn = None
        for name in dir(PL):
            if "merge_same_type" in name:
                fn = getattr(PL, name)
                break
        assert fn is not None, "未找到同 type 合并函数"
        src = inspect.getsource(fn)
        assert "_risk_severity" in src or "risk_levels" in src, "合并取代表未走权威"

    def test_audit_doctrine_levels_is_authority(self):
        from engine import audit_doctrine as AD
        from engine import risk_levels as RL
        assert tuple(AD.SEVERITY_LEVELS) == tuple(RL.LEGAL_LEVELS)


class TestCrossModuleLevelOrderAgrees:
    """③ 跨模块一致性：同一等级在**各模块**算出的相对次序必须完全相同。

    这是本组测试的核心 —— 旧实现下 `pipeline::_sev` 与 `enterprise_report` 的压制表
    对「信息 vs 低风险」相反，本测试在旧实现下必然失败。
    """

    def test_no_module_keeps_a_conflicting_table(self):
        import ast
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        bad = []
        for pat in ("*.py", "engine/**/*.py", "tools/**/*.py"):
            for f in root.glob(pat):
                rel = f.relative_to(root).as_posix()
                if any(s in rel for s in (".venv", "__pycache__", "scripts/_bk", "node_modules")):
                    continue
                if f.name == "risk_levels.py":
                    continue
                try:
                    tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
                except SyntaxError:
                    continue
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Dict):
                        continue
                    keys = [k.value for k in node.keys
                            if isinstance(k, ast.Constant) and isinstance(k.value, str)]
                    ints = [v for v in node.values
                            if isinstance(v, ast.Constant) and isinstance(v.value, int)
                            and not isinstance(v.value, bool)]
                    if "信息" in keys and "低风险" in keys and ints:
                        bad.append("%s:%d" % (rel, node.lineno))
        assert not bad, "仍有第二张等级→序数表（含「信息」与「低风险」）：%s" % bad

    def test_severity_agrees_with_explicit_pairwise_expectations(self):
        """把"谁重于谁"写成显式断言 —— 这是读者看到的"等级矛盾"的判据。"""
        from engine.risk_levels import severity
        pairs = [
            ("信息", "低风险"), ("低风险", "中风险"),
            ("中风险", "高风险"), ("高风险", "极高风险"),
            ("低风险", "待核验"),   # 尚未排除的疑点不应被已确认的轻项顶替
            ("待核验", "中风险"),   # 但也不得越过已确认的中等风险
        ]
        for _lo, _hi in pairs:
            assert severity(_lo) < severity(_hi), (_lo, _hi)


class TestDisplayLabelAuthority:
    """★ 2026-10-06（自检抓到的真实事故）：**结构化枚举字段不得被展示词替换**。

    `overall_conclusion.counts.by_level` 的**键**曾被改写成展示词「已列明」
    ⇒ 自检报「等级「已列明」报告 2 项、实际 0 项」（键与实际 `risk_level` 对不上），
    且字典推导把「待核验」与「尚需核实」合并覆盖、丢计数。

    现行口径：数据层 `by_level` 用**权威等级名**；展示层另给 `by_level_display`
    （唯一权威 `risk_levels.display_label`）。
    """

    def test_display_label_mapping(self):
        from engine.risk_levels import display_label
        # ★ 2026-10-15（用户裁定）：「待核验/待核」呈现为「涉嫌风险」
        #   （未定性 ≠ 没事；原「已列明」口径废止）。见闸门 check_level_display_single_source。
        assert display_label("待核验") == "涉嫌风险"
        assert display_label("待核") == "涉嫌风险"
        assert display_label("信息") == "提示性事项"
        for lv in ("极高风险", "高风险", "中风险", "低风险"):
            assert display_label(lv) == lv
        assert display_label("") == ""

    def test_by_level_keys_are_authoritative(self):
        from engine.overall_conclusion import build_overall_conclusion
        from engine.risk_levels import LEGAL_LEVELS, display_label
        probs = [
            {"seq": 1, "title": "甲", "risk_level": "高风险", "taxes": ["增值税"],
             "suspect": "涉嫌x", "conclusion_grade": "待核"},
            {"seq": 2, "title": "乙", "risk_level": "待核验", "taxes": [],
             "suspect": "", "conclusion_grade": "待核"},
            {"seq": 3, "title": "丙", "risk_level": "待核验", "taxes": [],
             "suspect": "", "conclusion_grade": "待核"},
            {"seq": 4, "title": "丁", "risk_level": "低风险", "taxes": [],
             "suspect": "", "conclusion_grade": "待核"},
        ]
        counts = (build_overall_conclusion(
            {"target_entity": {}, "comprehensive": {}}, probs, [], {}).get("counts") or {})
        by_level = counts.get("by_level") or {}
        assert set(by_level) <= set(LEGAL_LEVELS), \
            "by_level 出现非权威等级键（结构化枚举字段被展示词替换）"
        assert sum(by_level.values()) == len(probs), "等级计数合计不等于疑点数（合并覆盖）"
        assert by_level.get("待核验") == 2, by_level
        by_disp = counts.get("by_level_display") or {}
        assert by_disp.get(display_label("待核验")) == 2, by_disp
        assert by_disp.get("涉嫌风险") == 2, "展示写法必须可用（否则下游会去改 by_level 的键）"

    def test_report_body_avoids_pending_wording(self):
        """用户口径：报告**正文**不得出现「待核实/待核验」这类不确定措辞。

        ⚠ 只扫正文（跳过结构化枚举字段 `risk_level`/`level`）—— 数据层保真，
          措辞问题只存在于给人看的文本。
        """
        from engine.overall_conclusion import build_overall_conclusion
        probs = [{"seq": 1, "title": "甲", "risk_level": "待核验", "taxes": [],
                  "suspect": "", "conclusion_grade": "待核"}]
        paras = build_overall_conclusion(
            {"target_entity": {}, "comprehensive": {}}, probs, [], {}).get("paragraphs") or []
        body = " ".join(str(p) for p in paras)
        for w in ("待核验", "待核实"):
            assert w not in body, "报告正文出现不确定措辞「%s」：%s" % (w, body[:120])


class TestCountSingleSourceAndSequence:
    """★★ 2026-10-06（用户第 1 批 ① ②）：**计数与编号必须同源、且连续**。

    事故（用户实测同一份报告两套口径）：
      · 第 1 页写「16 项风险事项」，第 4 页写「已量化 7 / 26 项」——
        26 来自**同族合并之前**的旧列表（`build_tax_impact_summary` 在定稿前算过一次）。
      · 疑点编号为 1,2,3,4,5,6,7,9,11,13,14,15,18,27,29,34（缺号）——
        `merge_families` 删项、`_promote_standalone_to_problems` 追加项都在编号之后。
    """

    @staticmethod
    def _build(probs):
        from engine.enterprise_report import _build_redline_problems
        return _build_redline_problems(probs, [], None, None) \
            if False else None

    def test_sequence_must_be_continuous(self):
        """连续编号是**显示层契约**（前端渲染「疑点{seq}」）——不得有洞。"""
        import json
        from pathlib import Path
        p = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "company_1_full.json"
        assert p.exists(), "测试夹具缺失：%s（夹具是版本库内样本，不应缺失）" % p
        d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        er = (d.get("report") if isinstance(d.get("report"), dict) else d) \
            .get("enterprise_readable_report") or {}
        cps = er.get("confirmed_problems") or []
        seqs = [c.get("seq") for c in cps]
        assert seqs == list(range(1, len(cps) + 1)), \
            "疑点编号不连续（前端按 seq 渲染「疑点N」，缺号会直接显示给企业）：%s" % seqs

    def test_tax_impact_summary_denominator_matches_report(self):
        """税额敞口汇总的**分母**必须等于报告事项总数（否则第1页与第4页自相矛盾）。"""
        import json
        from pathlib import Path
        p = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "company_1_full.json"
        assert p.exists(), "测试夹具缺失：%s（夹具是版本库内样本，不应缺失）" % p
        d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        er = (d.get("report") if isinstance(d.get("report"), dict) else d) \
            .get("enterprise_readable_report") or {}
        n = len(er.get("confirmed_problems") or [])
        tis = er.get("tax_impact_summary") or {}
        assert tis.get("total_items") == n, \
            "税额敞口汇总分母 %s ≠ 事项总数 %s（口径矛盾）" % (tis.get("total_items"), n)
        assert 0 <= int(tis.get("quantified") or 0) <= n, tis

    def test_no_empty_tables_in_report(self):
        """报告里不得有**无用表格**：无表头 / 无数据 / 行全空（渲染出来只是空框）。"""
        import json
        from pathlib import Path
        p = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "company_1_full.json"
        assert p.exists(), "测试夹具缺失：%s（夹具是版本库内样本，不应缺失）" % p
        d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        er = (d.get("report") if isinstance(d.get("report"), dict) else d) \
            .get("enterprise_readable_report") or {}
        bad = []
        seen = set()

        def walk(o):
            if isinstance(o, (dict, list)):
                if id(o) in seen:
                    return
                seen.add(id(o))
            if isinstance(o, dict):
                if isinstance(o.get("columns"), list) and isinstance(o.get("rows"), list):
                    cols = [str(c) for c in o["columns"]]
                    rows = o["rows"]
                    if not rows or not any(c.strip() for c in cols):
                        bad.append(("无表头或无数据", str(o.get("title"))[:24]))
                    else:
                        blank = True
                        for r in rows:
                            if isinstance(r, dict):
                                for v in r.values():
                                    if str(v if v is not None else "").strip().strip("—－-– "):
                                        blank = False
                                        break
                            if not blank:
                                break
                        if blank:
                            bad.append(("行全空", str(o.get("title"))[:24]))
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(er)
        assert not bad, "报告含空白表格：%s" % bad[:5]
