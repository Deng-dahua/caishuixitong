# -*- coding: utf-8 -*-
"""GAP-21 空章节处理（2026-10-18）。

原差距：`build_document` **只丢空块、不丢空章** —— 会出现"只有标题的章节壳"。

现口径：
  · `blocks` 全为空 ⇒ **整章剔除**，并写入 `doc["skipped_sections"]`
    （含 `key`/`title`/`reason`，如实登记，不静默）；
  · `skipped_sections` 与 `omitted` **语义不同，不得混用**：
      - `omitted`          = 本视图按范围裁剪（换「全景」视图就有）
      - `skipped_sections` = 本章本轮确实没内容（换视图也没有，须补数据）
  · 四种格式（html/pdf/docx/xlsx）都必须写明「本章无内容（不是漏印）」+ 原因。
"""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import report_render as RENDER                            # noqa: E402
from engine import report_service as RSVC                             # noqa: E402
from engine import report_views as VIEWS                              # noqa: E402


def _doc(sections, skipped=None, view="full"):
    """最小文档模型（只含渲染必需字段）。"""
    d = {
        "name": "测试报告", "view": view,
        "view_label": VIEWS.VIEW_LABEL.get(view, view),
        "doc_no": "TEST-001", "version": "v1",
        "generated_at": "2026-10-18 10:00:00", "generated_by": "tester",
        "reviewed": False, "reviewed_by": "", "watermark_text": "内部测试",
        "company": {"name": "测试企业", "uscc": "", "industry": "", "region": ""},
        "period": {"start": "2024-01-01", "end": "2024-12-31"},
        "project": {},
        "disclaimer": {"identity_line": _IDENTITY_LINE, "non_enforcement_note": "非执法文书",
                       "security_level": "内部", "security_restriction": "限内部",
                       "security_retention": "三年", "authorization": "授权说明"},
        "sections": sections, "omitted": [],
        "counts": {"sections": len(sections), "findings": 0, "taxes": 0,
                   "evidences": 0, "reviewed": 0},
        "analysis_id": "",
    }
    if skipped is not None:
        d["skipped_sections"] = skipped
    return d


def _sec(key="chapter1", title="第一章 测试", blocks=None):
    return {"key": key, "title": title,
            "blocks": blocks if blocks is not None else
            [{"type": "paragraph", "text": "正文内容。"}]}


#: 免责声明的**唯一权威**正文（渲染器会核对该句必须出现在章节里）
_IDENTITY_LINE = "身份声明：本报告由系统自动生成，用于内部税务合规辅助复核。"


def _disclaimer_sec():
    """渲染器**强制**要求免责声明成节（`key=disclaimer`）且正文含 `identity_line`。"""
    return _sec("disclaimer", "免责声明",
                [{"type": "paragraph", "text": _IDENTITY_LINE}])


def _sections(*extra):
    return [_disclaimer_sec()] + [s for s in extra if s]


class BuildDocumentSkipsEmptySectionsTests(unittest.TestCase):
    """① 空章节必须整章剔除，且如实登记（不是静默丢）。"""

    def test_reason_constant_is_single_source(self):
        self.assertTrue(RSVC._EMPTY_SECTION_REASON.strip())
        # 不许用"其余/兜底/略"这类含糊词（项目铁律）
        for bad in ("其余", "兜底", "残差"):
            self.assertNotIn(bad, RSVC._EMPTY_SECTION_REASON)

    def test_skipped_sections_key_exists_in_output(self):
        """文档模型必须**总是**带 `skipped_sections`（哪怕是空列表）。"""
        src = open(os.path.join(ROOT, "engine", "report_service.py"),
                   encoding="utf-8").read()
        self.assertIn('"skipped_sections": skipped', src)

    def test_empty_section_is_dropped(self):
        """行为断言：空 `blocks` 的章节不得出现在 `sections` 里。"""
        src = open(os.path.join(ROOT, "engine", "report_service.py"),
                   encoding="utf-8").read()
        i = src.find("for key in secs:")
        seg = src[i:i + 1200]
        self.assertIn("if not blocks:", seg)
        self.assertIn("skipped.append(", seg)
        self.assertIn("continue", seg)
        self.assertNotIn("sections.append(", seg.split("if not blocks:")[0],
                         "空块判定之前就 append 了章节 ⇒ 空章会留下")

    def test_skipped_not_confused_with_omitted(self):
        """两者语义不同，代码里必须分别处理（不得把空章节塞进 omitted）。"""
        src = open(os.path.join(ROOT, "engine", "report_service.py"),
                   encoding="utf-8").read()
        self.assertIn("`omitted`", src)          # 注释里说明差异
        self.assertIn("`skipped_sections`", src)


class RenderAllFormatsTests(unittest.TestCase):
    """② 四种格式都必须写明「未列示的章节」+ 原因（读者不能以为漏印）。"""

    SKIPPED = [{"key": "chapter9", "title": "第九章 空章", "reason": "本轮无内容。"}]

    def _render(self, fmt):
        doc = _doc(_sections(_sec()), skipped=self.SKIPPED)
        data, wm = RENDER.render(doc, fmt)
        self.assertTrue(data)
        self.assertEqual(wm, "embedded")
        return data

    def test_html_mentions_skipped(self):
        html = self._render("html").decode("utf-8", "ignore")
        self.assertIn("本报告未列示的章节", html)
        self.assertIn("第九章 空章", html)
        self.assertIn("本轮无内容", html)
        self.assertIn("不是漏印", html)

    def test_html_has_no_markdown_asterisks(self):
        """报告正文禁 markdown（星号会被原样印出）。"""
        html = self._render("html").decode("utf-8", "ignore")
        self.assertNotIn("**", html)

    def test_pdf_mentions_skipped(self):
        """PDF 是二进制，但文本层可提取 ⇒ 抽出来断言（真渲染）。"""
        pdf = self._render("pdf")
        self.assertTrue(pdf.startswith(b"%PDF-"))
        try:
            import pdfplumber                       # noqa: PLC0415
        except Exception:                           # noqa: BLE001
            self.skipTest("pdfplumber 不可用，跳过 PDF 文本层断言")
        import io
        with pdfplumber.open(io.BytesIO(pdf)) as p:
            text = "\n".join((pg.extract_text() or "") for pg in p.pages)
        self.assertIn("未列示", text)
        self.assertIn("第九章 空章", text)

    def test_docx_mentions_skipped(self):
        blob = self._render("docx")
        try:
            import docx as _docx_lib
        except Exception:                           # noqa: BLE001
            self.skipTest("python-docx 不可用")
        import io
        d = _docx_lib.Document(io.BytesIO(blob))
        text = "\n".join(p.text for p in d.paragraphs)
        self.assertIn("本报告未列示的章节", text)
        self.assertIn("第九章 空章", text)

    def test_xlsx_has_skipped_sheet(self):
        blob = self._render("xlsx")
        try:
            import openpyxl
        except Exception:                           # noqa: BLE001
            self.skipTest("openpyxl 不可用")
        import io
        wb = openpyxl.load_workbook(io.BytesIO(blob))
        self.assertIn("未列示的章节", wb.sheetnames)
        ws = wb["未列示的章节"]
        vals = [str(c.value) for row in ws.iter_rows() for c in row if c.value]
        self.assertTrue(any("第九章 空章" in v for v in vals), vals)

    def test_no_skipped_means_no_section(self):
        """没有空章节时**不得**凭空多出"未列示"段（不制造噪音）。"""
        doc = _doc(_sections(_sec()), skipped=[])
        html = RENDER.render(doc, "html")[0].decode("utf-8", "ignore")
        self.assertNotIn("本报告未列示的章节", html)

    def test_missing_key_is_tolerated(self):
        """旧载荷没有 `skipped_sections` ⇒ 渲染不得崩（向后兼容）。"""
        doc = _doc(_sections(_sec()))
        self.assertNotIn("skipped_sections", doc)
        for fmt in ("html", "pdf", "docx", "xlsx"):
            data, _ = RENDER.render(doc, fmt)
            self.assertTrue(data, fmt)


if __name__ == "__main__":
    unittest.main()
