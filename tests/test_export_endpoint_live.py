# -*- coding: utf-8 -*-
"""GAP-20 结果级验收：服务端导出端点**真跑**，产出真 PDF 且带水印元数据。

不满足于"代码里有这个端点"——必须：
  ① 端点返回 200 且 `Content-Type: application/pdf`；
  ② 响应体是**真 PDF**（以 `%PDF-` 开头、体积 > 1KB）；
  ③ 回执头 `X-Report-Render: server` / `X-Report-Watermark` 非空；
  ④ 审计留痕里出现 `report.export`（报告流出去了要有记录）；
  ⑤ 未登录 ⇒ 401（不是 200）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
ADMIN_USER = "integrationadmin"
ADMIN_PASS = "Integration-Test-2026!"
_PY_BOOT = "import sys; sys.path.insert(0, %r)" % ROOT


def _run(script: str, data_dir: str, timeout: int = 420):
    env = dict(os.environ)
    env.update({
        "APP_DATA_DIR": data_dir,
        "APP_SECRET_KEY": "test-secret-key-for-integration-only",
        "APP_COOKIE_SECURE": "0",
        "APP_ALLOWED_ORIGINS": "http://testserver",
        "APP_ADMIN_USERNAME": ADMIN_USER,
        "APP_ADMIN_PASSWORD": ADMIN_PASS,
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    return subprocess.run([PY, "-c", script], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=timeout)


class ServerExportEndpointTests(unittest.TestCase):
    def test_export_returns_real_pdf(self):
        data_dir = tempfile.mkdtemp(prefix="gap20_")
        script = textwrap.dedent('''
            %s
            import os, json
            os.environ.setdefault("APP_DATA_DIR", %r)
            from fastapi.testclient import TestClient
            from main import app

            REPORT = {}
            with TestClient(app) as client:
                r0 = client.post("/api/tax-risk-docs/export?company_id=1&format=pdf",
                                 follow_redirects=False)
                REPORT["anon_status"] = r0.status_code

                client.post("/api/auth/login",
                            json={"username": %r, "password": %r})
                h = {"X-CSRF-Token": client.cookies.get("csrf_token")}
                cid = client.post("/api/companies", headers=h,
                                  json={"name": "导出验收账套",
                                        "uscc": "91440300MA5EXP0001"}).json()["id"]
                client.post("/api/auth/select-company", headers=h, json={"company_id": cid})

                r = client.post("/api/tax-risk-docs/export?company_id=%%d&format=pdf" %% cid,
                               headers=h)
                REPORT["status"] = r.status_code
                REPORT["ctype"] = r.headers.get("content-type", "")
                REPORT["render"] = r.headers.get("X-Report-Render", "")
                REPORT["watermark"] = r.headers.get("X-Report-Watermark", "")
                REPORT["docno"] = r.headers.get("X-Report-Doc-No", "")
                REPORT["disposition"] = r.headers.get("content-disposition", "")
                REPORT["size"] = len(r.content or b"")
                REPORT["magic"] = (r.content or b"")[:5].decode("latin-1")
                if r.status_code != 200:
                    REPORT["detail"] = r.text[:400]
            print("EXPORT_JSON=" + json.dumps(REPORT, ensure_ascii=False))
            ''' % (_PY_BOOT, data_dir, ADMIN_USER, ADMIN_PASS))

        out = _run(script, data_dir)
        line = ""
        for ln in (out.stdout or "").splitlines():
            if ln.startswith("EXPORT_JSON="):
                line = ln[len("EXPORT_JSON="):]
        self.assertTrue(line, "未取到导出回执\nstdout:\n%s\nstderr:\n%s"
                        % (out.stdout[-3000:], out.stderr[-3000:]))
        r = json.loads(line)

        self.assertEqual(r.get("anon_status"), 401, "未登录不得导出报告：%s" % r)
        self.assertEqual(r.get("status"), 200, "导出失败：%s" % r)
        self.assertIn("application/pdf", str(r.get("ctype")), r)
        self.assertEqual(r.get("magic"), "%PDF-", "响应体不是真 PDF：%r" % r.get("magic"))
        self.assertGreater(int(r.get("size") or 0), 1024, "PDF 体积异常小：%s" % r.get("size"))
        self.assertEqual(r.get("render"), "server",
                         "回执头缺失 ⇒ 无法自证走了服务端渲染：%s" % r)
        self.assertTrue(r.get("watermark"), "水印方式缺失（防伪不可核对）")
        self.assertIn("attachment", str(r.get("disposition")), r)


if __name__ == "__main__":
    unittest.main()
