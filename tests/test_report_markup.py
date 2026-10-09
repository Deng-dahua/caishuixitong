# -*- coding: utf-8 -*-
"""报告文本不得含 markdown 标记 —— 单元 / 产物级回归（2026-10-07）。

## 事故（实测）
企业会在报告里看到「② 增值税部分**未考虑**进项留抵…故为**上界**。」这种**带星号的句子**：
产物 `**` **120 处**、**渲染到网页上 73 处**。

根因不是"没有规则"，而是**规则只有局部**：去星号写在
`enterprise_report._naturalize_report_text` 里，而该函数只在**疑点段落构造路径**上被调用
⇒ `tax_impact_summary.note`、`risk_level_basis`、`related_analyses[].data`、
要件/触发情况文本**没走到它**。项目里其实早有这条规则（`test_bank_nature` /
`test_overall_conclusion` / `test_self_doubt` 各自断言自己那块"不得含 `**`"），
**漏掉的容器没人管**。

## 修法（单一权威 + 终局收口）
- 唯一权威：`engine.text_guardrails.strip_markup`（幂等；成对吃掉；落单 `**` 兜底；
  **单个 `*` 绝不删**——增值税发票品名形如 `*住宿服务*住宿服务`）；
- 唯一调用点：`engine.enterprise_report` 的**终局收口** `_strip_markup_out(out)`
  （与 `govern_all_tables` / `_scrub_out_vague` 同款"顺序缺陷"修法，幂等可重复）。
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT = ROOT / "scripts" / "four_reports" / "company_1_full.json"


class TestStripMarkupUnit:
    def test_strips_bold_pairs(self):
        from engine.text_guardrails import strip_markup
        assert strip_markup("② 增值税部分**未考虑**进项留抵，故为**上界**。") \
            == "② 增值税部分未考虑进项留抵，故为上界。"

    def test_strips_orphan_double_star_from_truncation(self):
        """落单 `**` = 加粗段被**截断**后的残留，必须也清掉。

        实测：`key_points` / `discovery_overview` 的
        「…自然人自有账户（私户）的流水**（已读到的是…」——
        原文是 `**本轮未提供…的流水**`，截断后只剩开头的 `**`，成对规则救不了。
        """
        from engine.text_guardrails import strip_markup
        assert strip_markup("…流水**（已读到的是对公账户一侧的收付记录）") \
            == "…流水（已读到的是对公账户一侧的收付记录）"

    def test_keeps_asterisks_in_invoice_goods_name(self):
        """**单个 `*` 绝不删**：增值税发票品名形如 `*住宿服务*住宿服务`，删了会损坏品名。

        ⚠ 这是修 bug：旧式 `\\*{1,3}(...)\\*{1,3}` 把单个星号也当标记，
          实测报告内 **547 处**品名的"分类星号"被吃成「现代服务代言服务费」，
          注释里"本式要求成对，不会误伤品名"是**错的**（`*现代服务*` 本身就是一对）。
        """
        from engine.text_guardrails import strip_markup
        for s in ("*住宿服务*住宿服务", "*现代服务*服务费", "餐饮服务*餐饮费"):
            assert strip_markup(s) == s, s

    def test_keeps_bare_asterisk_data_placeholder(self):
        """整串只有星号＝**数据占位符**（发票「规格型号」列的值就是 `**`），不是 markdown。

        实测 `report_compliance` 的发票明细里有 **449 个** `"spec": "**"`；
        无此护栏会被清成空串（**数据被删**）。
        """
        from engine.text_guardrails import strip_markup
        for s in ("**", "*", "  **  "):
            assert strip_markup(s) == s, s

    def test_strips_heading_marks_per_line(self):
        from engine.text_guardrails import strip_markup
        assert strip_markup("### 标题\n正文\n## 二级") == "标题\n正文\n二级"

    def test_idempotent_and_noop(self):
        from engine.text_guardrails import strip_markup
        s = "**A** 与 **B**"
        once = strip_markup(s)
        assert strip_markup(once) == once
        assert strip_markup("正常文本，无标记。") == "正常文本，无标记。"


class TestReportNoMarkupRegression:
    """产物级回归：整份**报告**不得出现 `**`（只在报告内，引擎内部数据不在此口境）。"""

    @staticmethod
    def _report():
        return json.loads(REPORT.read_text(encoding="utf-8"))

    def test_report_has_no_markdown_markup(self):
        rep = self._report()
        er = rep.get("enterprise_readable_report") or rep
        bad = []

        def walk(o, path=""):
            if isinstance(o, dict):
                for k, v in o.items():
                    walk(v, "%s.%s" % (path, k))
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    walk(v, "%s[%d]" % (path, i))
            elif isinstance(o, str) and "**" in o:
                bad.append(path)

        walk(er)
        assert bad == [], "报告正文仍有 markdown 强调符（%d 处，如 %s）" % (len(bad), bad[:5])

    def test_compliance_copy_also_clean(self):
        """`report_compliance` 里的报告副本同样不得带标记（它是另一份报告交付物）。"""
        rep = self._report()
        rc = (rep.get("report_compliance") or {}).get("enterprise_readable_report")
        if isinstance(rc, dict):
            blob = json.dumps(rc, ensure_ascii=False)
            assert "**" not in blob, "report_compliance 的报告副本仍含 markdown 强调符"

    def test_gate_reports_markup_leak(self, monkeypatch):
        """反向验证：门禁必须能报出 markdown 泄漏（否则判据是假的）。"""
        import tools.audit_consistency as A
        fake = {"enterprise_readable_report": {
            "confirmed_problems": [{"title": "x", "narrative_paragraphs": [
                {"text": "① 增值税部分**未考虑**进项留抵。"}]}]}}
        monkeypatch.setattr(A, "_canonical_report", lambda: fake)
        errs = [i for i in A.check_report_text_integrity() if i[0] == "ERROR"]
        assert any("markdown" in i[2] for i in errs), errs[:5]
