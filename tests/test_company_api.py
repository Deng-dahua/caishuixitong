"""账套管理 API 集成测试（修复「新建账套显示不了在选择账套页」的回归防线）。

覆盖前后端契约：
- GET    /api/companies           选择账套页列表（未登录 401；admin 全量；普通用户按授权）
- POST   /api/companies           新建账套（admin 专用；参数校验；创建后立即可见）
- DELETE /api/companies/{id}      删除账套（admin 专用；级联清理授权与会话选中态）

隔离：子进程 + APP_DATA_DIR 临时目录（与 tests/test_llm_api.py 同模式）。
"""
from __future__ import annotations

import base64
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class CompanyApiIntegrationTests(unittest.TestCase):
    def test_company_crud_and_visibility_contract(self):
        root = Path(__file__).resolve().parents[1]
        script = textwrap.dedent(
            """
            import security
            from fastapi.testclient import TestClient
            from main import app

            with TestClient(app) as client:
                # 1. 未登录 → 401
                assert client.get("/api/companies").status_code == 401

                # 2. admin 登录
                login = client.post(
                    "/api/auth/login",
                    json={
                        "username": "integrationadmin",
                        "password": "Integration-Test-2026!",
                    },
                )
                assert login.status_code == 200, login.text
                headers = {"X-CSRF-Token": client.cookies.get("csrf_token")}

                # 3. 初始列表可访问（可能为空）
                before = client.get("/api/companies")
                assert before.status_code == 200, before.text
                before_ids = {c["id"] for c in before.json()}

                # 4. 创建账套（18 位统一社会信用代码）
                uscc = "91440300MA5TEST001"
                created = client.post(
                    "/api/companies",
                    headers=headers,
                    json={"name": "集成测试账套", "uscc": uscc},
                )
                assert created.status_code == 200, created.text
                cid = created.json()["id"]
                assert cid > 0 and cid not in before_ids

                # 4b. 账套种子数据（科目表/增值税科目/部门/期间）——稽查科目余额分析的基础设施
                from database import SessionLocal, Account, Period, Department
                sdb = SessionLocal()
                acct = sdb.query(Account).filter(Account.company_id == cid).count()
                vat = sdb.query(Account).filter(
                    Account.company_id == cid, Account.code == "221001001"
                ).count()
                dept = sdb.query(Department).filter(Department.company_id == cid).count()
                period = sdb.query(Period).filter(Period.company_id == cid).count()
                sdb.close()
                assert acct > 0, "新账套缺少科目种子"
                assert vat == 1, "新账套缺少销项税额科目"
                assert dept > 0, "新账套缺少部门种子"
                assert period > 0, "新账套缺少期间种子"

                # 5. 创建后选择账套页立即可见（字段契约：id/name/uscc/industry/company_type/established_date）
                after = client.get("/api/companies")
                assert after.status_code == 200
                cards = after.json()
                mine = [c for c in cards if c["id"] == cid]
                assert mine, "新建账套未出现在选择账套页列表"
                card = mine[0]
                assert card["name"] == "集成测试账套"
                assert card["uscc"] == uscc
                for field in ("industry", "company_type", "established_date"):
                    assert field in card, f"卡片缺少字段 {field}"

                # 6. 参数校验：重复 uscc → 400
                dup = client.post(
                    "/api/companies",
                    headers=headers,
                    json={"name": "重复账套", "uscc": uscc},
                )
                assert dup.status_code == 400, dup.text

                # 7. 参数校验：uscc 非 18 位 → 400
                bad = client.post(
                    "/api/companies",
                    headers=headers,
                    json={"name": "坏账套", "uscc": "123"},
                )
                assert bad.status_code == 400, bad.text

                # 8. 参数校验：空名称 → 400
                empty = client.post(
                    "/api/companies",
                    headers=headers,
                    json={"name": "   ", "uscc": "91440300MA5TEST0099"},
                )
                assert empty.status_code == 400, empty.text

                # 9. 普通用户：看不到未授权账套；POST/DELETE 均被 403 拦截
                security.create_user(
                    "companyuser", "Company-User-Pass-2026!", role="user"
                )
                with TestClient(app) as uclient:
                    ulogin = uclient.post(
                        "/api/auth/login",
                        json={
                            "username": "companyuser",
                            "password": "Company-User-Pass-2026!",
                        },
                    )
                    assert ulogin.status_code == 200, ulogin.text
                    uheaders = {"X-CSRF-Token": uclient.cookies.get("csrf_token")}

                    ulist = uclient.get("/api/companies")
                    assert ulist.status_code == 200
                    assert all(
                        c["id"] != cid for c in ulist.json()
                    ), "未授权用户不应看到账套"

                    ucreate = uclient.post(
                        "/api/companies",
                        headers=uheaders,
                        json={"name": "越权", "uscc": "91440300MA5TEST0098"},
                    )
                    assert ucreate.status_code == 403, ucreate.text

                    udelete = uclient.delete(
                        f"/api/companies/{cid}", headers=uheaders
                    )
                    assert udelete.status_code == 403, udelete.text

                # 10. admin 删除 → 列表消失
                deleted = client.delete(
                    f"/api/companies/{cid}", headers=headers
                )
                assert deleted.status_code == 200, deleted.text
                final = client.get("/api/companies")
                assert all(
                    c["id"] != cid for c in final.json()
                ), "删除后账套仍存在"

                # 11. 重复删除 → 404
                gone = client.delete(f"/api/companies/{cid}", headers=headers)
                assert gone.status_code == 404, gone.text

            print("ALL COMPANY API TESTS PASSED")
            """
        )
        with tempfile.TemporaryDirectory() as directory:
            environment = os.environ.copy()
            environment.update(
                {
                    "APP_DATA_DIR": directory,
                    "APP_COOKIE_SECURE": "0",
                    "APP_ALLOWED_ORIGINS": "http://testserver",
                    "APP_ADMIN_USERNAME": "integrationadmin",
                    "APP_ADMIN_PASSWORD": "Integration-Test-2026!",
                    "APP_LLM_MASTER_KEY": base64.urlsafe_b64encode(
                        bytes(range(32))
                    ).decode("ascii"),
                }
            )
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=120,
            )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
