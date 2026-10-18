# -*- coding: utf-8 -*-
"""GAP-14 字段覆盖率接口：端到端真跑（不再是恒 0）。

原差距：`GET /api/v1/documents/{id}/field-coverage` **恒返 0**。
根因三处（见 `parse_api.field_coverage` docstring）：
  ① tables 里只有 `rows_preview`，`t["rows"]` 取成 `[]` ⇒ 行数 0；
  ② 表里存 `doc_type` 没有 `domain` ⇒ 域恒空，域字段清单恒空；
  ③ 回落读 `got["standard_fields"]`，而 `get_extracted` 不返回该键 ⇒ 字段清单空。

本测试**真起隔离实例**（临时 APP_DATA_DIR + 独立端口）走完整链路：
建账套 → 建项目 → 上传科目余额表 → 解析 → 查覆盖率 → 断言数字**真的不是 0**。
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
ADMIN_USER = "integrationadmin"
ADMIN_PASS = "Integration-Test-2026!"
_PY_BOOT = "import sys; sys.path.insert(0, %r)" % ROOT


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _run(script: str, data_dir: str, port: int, timeout: int = 300):
    environment = dict(os.environ)
    environment.update({
        "APP_DATA_DIR": data_dir,
        "APP_SECRET_KEY": "test-secret-key-for-integration-only",
        "APP_COOKIE_SECURE": "0",
        "APP_ALLOWED_ORIGINS": "http://127.0.0.1:%d" % port,
        "APP_ADMIN_USERNAME": ADMIN_USER,
        "APP_ADMIN_PASSWORD": ADMIN_PASS,
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    return subprocess.run([PY, "-c", script], cwd=ROOT, env=environment,
                          capture_output=True, text=True, timeout=timeout)


class FieldCoverageTests(unittest.TestCase):
    def test_coverage_is_not_all_zero(self):
        data_dir = tempfile.mkdtemp(prefix="gap14_")
        port = _free_port()
        script = textwrap.dedent('''
            %s
            import os, sys, time, json, threading, tempfile
            os.environ.setdefault("APP_DATA_DIR", %r)
            import openpyxl, uvicorn
            from main import app
            from fastapi.testclient import TestClient

            def mkxlsx(rows, path):
                wb = openpyxl.Workbook(); ws = wb.active
                for r in rows: ws.append(r)
                wb.save(path); return path

            ROWS = [
                ["科目编码","科目名称","期初借方","期初贷方","本期借方","本期贷方","期末借方","期末贷方"],
                ["1001","库存现金",1000,0,500,200,1300,0],
                ["1002","银行存款",50000,0,20000,10000,60000,0],
                ["2202","应付账款",0,30000,10000,0,0,20000],
                ["6001","主营业务收入",0,0,0,80000,0,80000],
                ["6401","主营业务成本",0,0,60000,0,60000,0],
            ]

            with TestClient(app) as client:
                client.post("/api/auth/login",
                            json={"username": %r, "password": %r})
                h = {"X-CSRF-Token": client.cookies.get("csrf_token")}
                cid = client.post("/api/companies", headers=h,
                                  json={"name": "覆盖率账套",
                                        "uscc": "91440300MA5COV0001"}).json()["id"]
                client.post("/api/auth/select-company", headers=h, json={"company_id": cid})
                pid = client.post("/api/v1/projects", headers=h, json={
                    "name": "覆盖率企业", "taxpayer_id": "91440300MA5COV0002",
                    "industry": "制造业", "region": "广东省",
                    "period_start": "2024-01-01", "period_end": "2024-12-31",
                    "tax_scopes": ["增值税", "企业所得税"],
                }).json()["id"]
                p = mkxlsx(ROWS, os.path.join(tempfile.mkdtemp(), "科目余额表2024.xlsx"))
                blob = open(p, "rb").read()
                up = client.post("/api/v1/projects/%%d/documents" %% pid, headers=h,
                                 files=[("files", ("科目余额表2024.xlsx", blob,
                                                   "application/octet-stream"))])
                assert up.status_code == 201, up.text
                did = up.json()["uploaded"][0]["id"]
                ex = client.post("/api/v1/documents/%%d/extract" %% did, headers=h)
                assert ex.status_code == 200, ex.text

                cov = client.get("/api/v1/documents/%%d/field-coverage" %% did, headers=h)
                assert cov.status_code == 200, cov.text
                print("COVERAGE_JSON=" + json.dumps(cov.json(), ensure_ascii=False))
            ''' % (_PY_BOOT, data_dir, ADMIN_USER, ADMIN_PASS))

        r = _run(script, data_dir, port)
        line = ""
        for ln in (r.stdout or "").splitlines():
            if ln.startswith("COVERAGE_JSON="):
                line = ln[len("COVERAGE_JSON="):]
        self.assertTrue(line, "未取到覆盖率 JSON\nstdout:\n%s\nstderr:\n%s" % (r.stdout, r.stderr))
        data = json.loads(line)

        self.assertGreaterEqual(data.get("table_count") or 0, 1, data)
        t = data["tables"][0]
        # ① 行数不再恒 0
        self.assertEqual(t.get("row_count"), 5, "覆盖率行数应为 5 行：%s" % t.get("row_count"))
        self.assertEqual((t.get("coverage") or {}).get("rows"), 5)
        # ② 域不再恒空
        self.assertEqual(t.get("domain"), "ledger", "域应由 doc_type 推导：%s" % t.get("doc_type"))
        # ③ 字段清单不再恒空
        fields = (t.get("coverage") or {}).get("fields") or {}
        self.assertGreaterEqual(len(fields), 6, "字段体检面过窄：%s" % sorted(fields))
        # ④ 关键字段**真的被认出来**（不是"有字段但全 0 命中"）
        for n, expect in (("account_code", 5), ("account_name", 5),
                          ("opening_debit", 5), ("current_credit", 5)):
            self.assertIn(n, fields, "缺少字段 %s" % n)
            self.assertEqual(fields[n]["hits"], expect,
                             "%s 命中数应为 %d：%s" % (n, expect, fields[n]))
            self.assertTrue(fields[n]["recognized"])
        # ⑤ 未识别字段如实列出（体检要有"发现问题的能力"）
        self.assertIn("unrecognized_fields", t.get("coverage") or {})
        # ⑥ 全零即回归
        self.assertGreater((t.get("coverage") or {}).get("recognized_ratio") or 0, 0.3,
                           "识别率过低：%s" % (t.get("coverage") or {}).get("recognized_ratio"))


class CoverageFieldNamesUnitTests(unittest.TestCase):
    """字段清单构造（纯函数）——覆盖"未知域靠跨域白名单取数"这条唯一通路。"""

    def test_known_domain_uses_domain_fields(self):
        import parse_api
        names = parse_api._coverage_field_names("ledger", [])
        self.assertIn("account_code", names)
        self.assertIn("opening_debit", names)
        self.assertIn("period", names)            # common 必在
        self.assertEqual(len(names), len(set(names)), "字段清单不得重复")

    def test_unknown_domain_keeps_registered(self):
        """★ 未知域（合同/协议/档案）没有域字段 ⇒ 只有"已登记字段"这条通路，
        缺了它覆盖率永远只有 common 的 period/summary 两项，体检等于没做。"""
        import parse_api
        names = parse_api._coverage_field_names("", ["counterparty", "invoice_no"])
        self.assertIn("counterparty", names)
        self.assertIn("invoice_no", names)
        self.assertIn("period", names)

    def test_unknown_domain_without_registered_is_only_common(self):
        import parse_api
        names = parse_api._coverage_field_names("", [])
        self.assertEqual(sorted(names), sorted(["period", "summary"]))


if __name__ == "__main__":
    unittest.main()
