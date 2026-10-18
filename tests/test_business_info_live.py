# -*- coding: utf-8 -*-
"""结果级验收：工商信息查询**真跑**（登录 → 查 → 落库 → 关联项目 → 失败提示）。

不满足于"代码里有这个接口"，必须证明：
  ① 未登录 ⇒ 401（不是 200，也不能默默返回空）；
  ② 已登录且名称命中本系统账套 ⇒ 200 + `ok=true` + 字段真的填满；
  ③ 同一请求**落库**：`sys_company_info` 真的多出一行，且 `project_id` 已关联；
  ④ 第二次调用 ⇒ `cache_hit=true`（不再发外网请求，防反爬）；
  ⑤ 查不到 ⇒ `ok=false` + 「请手动填写」+ 逐通道原因（不阻断项目创建）。
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
ADMIN_USER = "bizadmin"
ADMIN_PASS = "Biz-Integration-2026!"
_PY_BOOT = "import sys; sys.path.insert(0, %r)" % ROOT

COMPANY = "东莞市恒达钢材有限公司"
USCC = "91441900MA4W8XYZ12"


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


class BusinessInfoLiveTests(unittest.TestCase):
    def test_query_end_to_end(self):
        data_dir = tempfile.mkdtemp(prefix="biz_live_")
        script = textwrap.dedent('''
            %s
            import os, json
            os.environ.setdefault("APP_DATA_DIR", %r)
            from fastapi.testclient import TestClient
            from main import app

            # ★ 只留本地通道：本测试**不联网**（外网通道另有人工验收，不混进自动化）
            from engine.business_info import service as SVC
            SVC.config()["providers"] = ["local_db"]

            R = {}
            with TestClient(app) as client:
                r0 = client.get("/api/v1/business/query?name=%s", follow_redirects=False)
                R["anon_status"] = r0.status_code

                client.post("/api/auth/login", json={"username": %r, "password": %r})
                h = {"X-CSRF-Token": client.cookies.get("csrf_token")}
                cid = client.post("/api/companies", headers=h,
                                  json={"name": %r, "uscc": %r,
                                        "business_scope": "钢材、建筑材料、五金产品的销售"}).json()["id"]
                client.post("/api/auth/select-company", headers=h, json={"company_id": cid})
                # `/api/companies` 的入参不含经营范围 ⇒ 直接补写（模拟历史账套已有工商档案）
                from sqlalchemy import text as _T0
                from database import engine as _E0
                with _E0.begin() as _c0:
                    _c0.execute(_T0("UPDATE companies SET business_scope=:s WHERE id=:i"),
                                {"s": "钢材、建筑材料、五金产品的销售", "i": cid})
                # 建一个项目，用来验证"关联当前稽查项目"
                pr = client.post("/api/v1/projects", headers=h,
                                 json={"name": %r, "taxpayer_id": %r, "company_id": cid,
                                       "industry": "制造业", "region": "广东省东莞市",
                                       "period_start": "2025-01-01", "period_end": "2025-12-31",
                                       "tax_scopes": ["增值税"]})
                pid = (pr.json() or {}).get("id") if pr.status_code in (200, 201) else None
                R["project_status"] = pr.status_code

                url = "/api/v1/business/query?name=" + "%s"
                if pid:
                    url += "&project_id=%%d" %% pid
                r1 = client.get(url)
                R["status"] = r1.status_code
                R["payload"] = r1.json() if r1.status_code == 200 else {"raw": r1.text[:300]}
                R["cache_control"] = r1.headers.get("cache-control", "")

                r2 = client.get(url)
                R["second"] = r2.json() if r2.status_code == 200 else {"raw": r2.text[:300]}

                # 落库核对（同一个 APP_DATA_DIR）
                from sqlalchemy import text as T
                from database import engine as E
                with E.connect() as conn:
                    row = conn.execute(T("SELECT name, tax_id, business_scope, source, "
                                         "project_id, fetched_at FROM sys_company_info "
                                         "WHERE name=:n"), {"n": %r}).first()
                R["db_row"] = dict(row._mapping) if row else None

                r3 = client.get("/api/v1/business/query?name=" + "从未登记过的某某有限公司")
                R["miss"] = r3.json() if r3.status_code == 200 else {"raw": r3.text[:300]}
                R["miss_status"] = r3.status_code

            print("BIZ_JSON=" + json.dumps(R, ensure_ascii=False))
            ''' % (_PY_BOOT, data_dir, COMPANY, ADMIN_USER, ADMIN_PASS,
                  COMPANY, USCC, COMPANY, USCC, COMPANY, COMPANY))

        out = _run(script, data_dir)
        line = ""
        for ln in (out.stdout or "").splitlines():
            if ln.startswith("BIZ_JSON="):
                line = ln[len("BIZ_JSON="):]
        self.assertTrue(line, "未取到回执\nstdout:\n%s\nstderr:\n%s"
                        % (out.stdout[-3000:], out.stderr[-3000:]))
        r = json.loads(line)

        # ① 未登录
        self.assertEqual(r.get("anon_status"), 401, "未登录不得查询：%s" % r.get("anon_status"))

        # ② 已登录 + 命中
        self.assertEqual(r.get("status"), 200, "查询失败：%s" % r.get("payload"))
        p = (r.get("payload") or {})
        self.assertTrue(p.get("ok"), "应查到本地账套：%s" % p)
        prof = p.get("profile") or {}
        self.assertEqual(prof.get("tax_id"), USCC)
        self.assertEqual(prof.get("business_scope"), "钢材、建筑材料、五金产品的销售")
        self.assertIn("本地", str(p.get("source_detail") or ""), p.get("source_detail"))
        self.assertIn("no-store", str(r.get("cache_control") or ""), "工商信息不得进浏览器/中间缓存")

        # ③ 落库 + 关联项目
        row = r.get("db_row")
        self.assertIsNotNone(row, "查询成功但没有落库（用户要求库里能查到）")
        self.assertEqual(row.get("tax_id"), USCC)
        self.assertEqual(row.get("business_scope"), "钢材、建筑材料、五金产品的销售")
        if r.get("project_status") in (200, 201):
            self.assertTrue(row.get("project_id"), "未关联稽查项目：%s" % row)
        self.assertTrue(row.get("fetched_at"), "缺 fetched_at ⇒ 无法判断缓存是否过期")

        # ④ 缓存命中
        second = r.get("second") or {}
        self.assertTrue(second.get("ok"), second)
        self.assertTrue(second.get("cache_hit"), "第二次应命中缓存（防反复触发反爬）：%s" % second)

        # ⑤ 查不到时的友好失败
        miss = r.get("miss") or {}
        self.assertEqual(r.get("miss_status"), 200, "查询失败不应是 HTTP 错误（会阻断前端）")
        self.assertFalse(miss.get("ok"))
        self.assertIn("请手动填写", str(miss.get("message") or ""), miss)
        self.assertTrue(miss.get("attempts"), "失败必须逐通道说明原因：%s" % miss)


class PermissionChainTests(unittest.TestCase):
    """接口 → 门禁：`_require_perm` 抛 403 时，接口必须中止（不得继续取数）。"""

    def test_endpoint_aborts_when_permission_denied(self):
        from unittest import mock
        from fastapi import HTTPException
        from starlette.responses import Response
        import business_api as BA

        called = {"n": 0}

        with mock.patch.object(BA, "_session", lambda r: object()), \
             mock.patch.object(BA, "_require_perm",
                               side_effect=HTTPException(status_code=403, detail="无权")), \
             mock.patch.object(BA.BI, "query_company",
                               side_effect=lambda *a, **k: called.__setitem__("n", 1)):
            with self.assertRaises(HTTPException) as cm:
                BA.query_business_info(object(), Response(), name="某某有限公司")
        self.assertEqual(cm.exception.status_code, 403)
        self.assertEqual(called["n"], 0, "无权限时仍去查数 ⇒ 门禁没起作用")

    def test_permission_code_is_project_write(self):
        src = open(os.path.join(ROOT, "business_api.py"), encoding="utf-8").read()
        self.assertIn('_require_perm(session, "project.write")', src,
                      "用户要求：必须登录且具备创建项目的权限")


if __name__ == "__main__":
    unittest.main()
