# -*- coding: utf-8 -*-
"""GAP-20 主页面导出走服务端（2026-10-18）。

原差距：`tax-doc-analysis.js` 的"导出PDF"是浏览器打印 ——
  · 只有**草稿版**有 CSS 水印，正式版导出件**无任何防伪标识**；
  · 打印件**没有元数据**（无文档号/版本/复核标识/指纹）；
  · 无服务端留痕（不知道"报告流出去了"）。

现口径：`POST /api/tax-risk-docs/export` 由 `engine.report_render.render()` 真渲染
（4 视图 × 4 格式、水印真嵌入），并写 `report.export` 审计留痕；
响应头回执 `X-Report-Render: server` / `X-Report-Watermark` / `X-Report-Doc-No`。
前端**不再有** `window.print()` / `document.write` 打印路径。
"""
from __future__ import annotations

import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_JS = os.path.join(ROOT, "static", "js", "tax-doc-analysis.js")
_MAIN = os.path.join(ROOT, "main.py")
_PERMS = os.path.join(ROOT, "security_web.py")


def _js_src() -> str:
    return open(_JS, encoding="utf-8").read()


def _strip_comments(js: str) -> str:
    """去掉 // 行注释与 /* */ 块注释（判据不能被"注释里提到旧写法"误伤）。"""
    js = re.sub(r"/\*[\s\S]*?\*/", "", js)
    return re.sub(r"^\s*//.*$", "", js, flags=re.M)


class FrontendNoBrowserPrintTests(unittest.TestCase):
    def test_no_window_print_in_code(self):
        code = _strip_comments(_js_src())
        self.assertNotIn("window.print", code,
                         "前端仍在用浏览器打印 ⇒ 正式版导出件将无防伪、无元数据")
        self.assertNotIn(".print()", code)

    def test_no_document_write_print_pipeline(self):
        code = _strip_comments(_js_src())
        self.assertNotIn("document.write", code,
                         "仍在自拼 HTML 交给浏览器打印（无服务端渲染）")

    def test_export_calls_server_endpoint(self):
        code = _strip_comments(_js_src())
        self.assertIn("/api/tax-risk-docs/export", code)
        self.assertIn("exportTaxDocReportPdf", code)

    def test_export_reads_server_receipt(self):
        """必须读服务端回执（否则"走了服务端"无法自证）。"""
        code = _strip_comments(_js_src())
        for h in ("X-Report-Doc-No", "X-Report-Watermark"):
            self.assertIn(h, code, "未读取回执头 %s" % h)

    def test_no_silent_fallback_to_print(self):
        """渲染失败必须报错，**不得**回退浏览器打印（回退=静默丢防伪）。

        ★ 定位必须用函数**定义**锚点（`function exportTaxDocReportPdf`）——
          否则会命中按钮里的 `onclick="exportTaxDocReportPdf()"`（第一次出现在
          页头 HTML），断言窗口取错，判据就成了假的（本轮反向验证抓出来的）。
        """
        code = _strip_comments(_js_src())
        i = code.find("function exportTaxDocReportPdf")
        self.assertGreater(i, 0, "未找到导出函数定义")
        seg = code[i:i + 3000]
        self.assertNotIn("window.open", seg, "导出函数里仍开新窗口打印")
        self.assertIn("throw new Error", seg)


class ServerEndpointTests(unittest.TestCase):
    def test_endpoint_registered(self):
        src = open(_MAIN, encoding="utf-8").read()
        self.assertIn('"/api/tax-risk-docs/export"', src)
        self.assertIn("def export_tax_risk_report", src)

    def test_endpoint_uses_authoritative_renderer(self):
        """必须复用 `engine.report_render`（不得自写第二套渲染）。"""
        src = open(_MAIN, encoding="utf-8").read()
        i = src.find("def export_tax_risk_report")
        seg = src[i:i + 3000]
        self.assertIn("report_render", seg)
        self.assertIn("build_document", seg)
        self.assertIn("RENDER.render", seg)

    def test_endpoint_writes_audit_trail(self):
        """必须写**审计留痕**，且判据落在**调用点**上。

        ★ 判据不能只搜 `"report.export"` —— 函数 docstring 里也写了这个词，
          字面量一改判据仍然满足（本轮反向验证抓出来的**假判据**）。
          现要求：常量定义 + 调用点用常量（改口径只改一处、且漏改必红）。
        """
        src = open(_MAIN, encoding="utf-8").read()
        self.assertIn('_EXPORT_AUDIT_ACTION = "report.export"', src,
                      "审计动作名必须收敛为一个常量（不得各处重抄字面量）")
        i = src.find("def export_tax_risk_report")
        self.assertGreater(i, 0)
        seg = src[i:i + 3000]
        self.assertIn("_audit_record(", seg)
        self.assertIn("_EXPORT_AUDIT_ACTION, target=filename", seg,
                      "调用点未使用常量 ⇒ 审计动作名可能被改散")
        self.assertIn("audit_trail", seg)

    def test_endpoint_checks_permission(self):
        """必须校验功能权限点（不是"登录即可导出"）。"""
        src = open(_MAIN, encoding="utf-8").read()
        i = src.find("def export_tax_risk_report")
        seg = src[i:i + 3000]
        self.assertIn('_request_perm(request, "report.generate")', seg,
                      "导出端点未校验 report.generate ⇒ 任何登录用户都能导出报告")

    def test_permission_point_registered(self):
        src = open(_PERMS, encoding="utf-8").read()
        # 元组形态是 ("POST", "/api/tax-risk-docs/export", "report.generate")
        self.assertIn('"/api/tax-risk-docs/export", "report.generate"', src,
                      "新增写/导出端点必须在 _LEGACY_WRITE_PERMS 登记权限点"
                      "（与 /deliver 同权：都是「报告流出去了」）")
        # 用 POST（非 GET）⇒ 受 CSRF 保护（GET 无 CSRF，第三方页面可诱导导出）
        self.assertIn('("POST", "/api/tax-risk-docs/export"', src)


class AssetVersionTests(unittest.TestCase):
    def test_index_asset_version_synced(self):
        """改了 JS 必须同步 `?v=`（否则"改了等于没改"）。

        版本号算法以 `tools/sync_asset_versions.py` 为唯一权威（sha1 前 10 位），
        本测试**复制该算法**会形成第二份口径 ⇒ 直接调它的函数取现算值。
        """
        idx = open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8").read()
        m = re.search(r"/static/js/tax-doc-analysis\.js\?v=([0-9a-f]+)", idx)
        self.assertIsNotNone(m, "index.html 未引用带版本号的 tax-doc-analysis.js")
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        try:
            import sync_asset_versions as SYNC          # noqa: PLC0415
            expect = SYNC.asset_version("/static/js/tax-doc-analysis.js")
        finally:
            sys.path.pop(0)
        self.assertTrue(expect, "同步工具取不到该资源版本（路径口径变了？）")
        self.assertEqual(m.group(1), expect,
                         "静态资源版本号与文件内容不一致（跑 tools/sync_asset_versions.py）")


if __name__ == "__main__":
    unittest.main()
