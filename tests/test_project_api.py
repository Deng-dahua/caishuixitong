# -*- coding: utf-8 -*-
"""P0-1 稽查项目模块 —— 四类测试（单元 / 集成 / 权限 / 审计）。

隔离方式：**子进程 + `APP_DATA_DIR` 临时目录**（与 `tests/test_company_api.py`、
`tests/test_llm_api.py` 同一模式）—— 走**真实链路**（认证中间件 / 真实 SQLite / 真实留痕），
但数据落在临时目录 ⇒ **不污染** `data/accounting.db` 与 `data/security.db`。

四类（任务书要求）：
  ① `ProjectServiceUnitTests`     单元测试：Service 层 CRUD（不走 HTTP）
  ② `ProjectApiIntegrationTests`  集成测试：接口 + 数据库（全流程）
  ③ `ProjectPermissionTests`      权限测试：跨租户不可见 / 同租户非成员只读
  ④ `ProjectAuditTests`           审计日志测试：四类动作均留痕 + 中文名可读

★ 每个测试都含**反向判据**（不只是"正例通过"）：
  · 状态机：合法迁移通过 **且** 非法迁移必须 400；
  · 权限：可见者 200 **且** 跨租户必须 404（不是 403 —— 不泄露存在性）；
  · 审计：动作在库 **且** 未知动作不会被静默丢弃（由 audit_trail 自身保证，此处断言中文名齐全）。
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

ROOT = Path(__file__).resolve().parents[1]

ADMIN_USER = "integrationadmin"
ADMIN_PASS = "Integration-Test-2026!"


def _run(script: str, *, timeout: int = 240) -> subprocess.CompletedProcess:
    """在隔离的 `APP_DATA_DIR` 临时目录里跑一段脚本。"""
    with tempfile.TemporaryDirectory() as directory:
        environment = os.environ.copy()
        environment.update({
            "APP_DATA_DIR": directory,
            "APP_COOKIE_SECURE": "0",
            "APP_ALLOWED_ORIGINS": "http://testserver",
            "APP_ADMIN_USERNAME": ADMIN_USER,
            "APP_ADMIN_PASSWORD": ADMIN_PASS,
            "APP_LLM_MASTER_KEY": base64.urlsafe_b64encode(
                bytes(range(32))).decode("ascii"),
        })
        return subprocess.run([sys.executable, "-c", textwrap.dedent(script)],
                              cwd=ROOT, env=environment,
                              capture_output=True, text=True, timeout=timeout)


# --------------------------------------------------------------------------
# ① 单元测试：Service 层 CRUD
# --------------------------------------------------------------------------
class ProjectServiceUnitTests(unittest.TestCase):
    """直接调 `engine.project_service`（不经过 HTTP），验证 CRUD 与状态机。"""

    def test_service_crud_and_status_machine(self):
        result = _run(
            """
            from security import SessionContext
            from engine import project_service as SVC

            sess = SessionContext(
                user_id=1, username="unitadmin", role="admin",
                allowed_company_ids=frozenset(), selected_company_id=None,
                csrf_hash="", expires_at=0,
            )

            # 1) 建：必填校验（空名 ⇒ 400 语义）
            try:
                SVC.create_project({"name": "   "}, sess)
                raise AssertionError("空名竟然成功")
            except SVC.ProjectError as e:
                assert e.status == 400, e.status

            # 2) 建：正常
            p = SVC.create_project({
                "name": "单元测试企业", "taxpayer_id": "91440300MA5UNIT01",
                "industry": "制造业", "region": "深圳",
                "period_start": "2024-01-01", "period_end": "2024-12-31",
                "tax_scopes": ["增值税", "企业所得税", "增值税"],
                "company_id": 900001,
            }, sess)
            pid = p["id"]
            assert p["status"] == "draft" and p["status_cn"] == "草稿", p
            assert p["code"].startswith("PJ-"), p["code"]
            # 税种范围应去重保序
            assert p["tax_scopes"] == ["增值税", "企业所得税"], p["tax_scopes"]
            # 创建人自动成为 owner 成员
            assert any(m["role"] == "owner" for m in p["members"]), p["members"]

            # 3) 查：详情
            got = SVC.get_project(pid, sess)
            assert got["name"] == "单元测试企业"
            assert got["allowed_next_status"] == ["uploading", "archived"], got

            # 4) 列表：搜索/筛选/分页
            lst = SVC.list_projects(sess, q="单元测试")
            assert lst["total"] == 1 and lst["page"] == 1, lst
            assert SVC.list_projects(sess, status="draft")["total"] == 1
            assert SVC.list_projects(sess, status="uploading")["total"] == 0
            assert SVC.list_projects(sess, industry="制造业")["total"] == 1
            assert SVC.list_projects(sess, industry="批发零售")["total"] == 0

            # 5) 改：字段
            upd = SVC.update_project(pid, {"region": "广州", "remark": "改过"}, sess)
            assert upd["region"] == "广州" and upd["remark"] == "改过", upd

            # 6) 改：期间颠倒 ⇒ 400
            try:
                SVC.update_project(pid, {"period_start": "2025-01-01",
                                         "period_end": "2024-01-01"}, sess)
                raise AssertionError("期间颠倒竟然成功")
            except SVC.ProjectError as e:
                assert e.status == 400

            # 7) 状态机：合法迁移逐个走通
            for nxt in ("uploading", "analyzing", "reviewing", "reported", "archived"):
                SVC.update_project(pid, {"status": nxt}, sess)
            assert SVC.get_project(pid, sess)["status"] == "archived"

            # 8) 状态机（反向）：终态不可迁出 ⇒ 400
            try:
                SVC.update_project(pid, {"status": "draft"}, sess)
                raise AssertionError("终态竟然可迁出")
            except SVC.ProjectError as e:
                assert e.status == 400, e.status

            # 9) 状态机（反向）：非法跳级 ⇒ 400
            p2 = SVC.create_project({"name": "跳级测试", "company_id": 900001}, sess)
            try:
                SVC.update_project(p2["id"], {"status": "reported"}, sess)
                raise AssertionError("非法跳级竟然成功")
            except SVC.ProjectError as e:
                assert e.status == 400

            # 10) 状态非法值 ⇒ 400
            try:
                SVC.update_project(p2["id"], {"status": "不存在"}, sess)
                raise AssertionError("非法状态值竟然成功")
            except SVC.ProjectError as e:
                assert e.status == 400

            # 11) 成员：新增 + 重复加入 ⇒ 幂等（视为角色变更）
            SVC.add_member(p2["id"], {"user_id": 77, "user_name": "张三",
                                      "role": "reviewer"}, sess)
            again = SVC.add_member(p2["id"], {"user_id": 77, "user_name": "张三",
                                              "role": "member"}, sess)
            assert again["role"] == "member", again
            ms = SVC.list_members(p2["id"], sess)
            assert ms["total"] == 2, ms           # owner(自己) + 张三
            # 角色非法 ⇒ 400
            try:
                SVC.add_member(p2["id"], {"user_id": 78, "role": "boss"}, sess)
                raise AssertionError("非法角色竟然成功")
            except SVC.ProjectError as e:
                assert e.status == 400

            # 12) 删：连同成员一并清掉
            SVC.delete_project(p2["id"], sess)
            try:
                SVC.get_project(p2["id"], sess)
                raise AssertionError("删除后仍可查到")
            except SVC.ProjectError as e:
                assert e.status == 404, e.status

            # 13) 元数据字典齐全（六态 + 四角色 + 中文名）
            meta = SVC.metadata()
            assert [s["value"] for s in meta["statuses"]] == [
                "draft", "uploading", "analyzing", "reviewing", "reported", "archived"]
            assert [r["value"] for r in meta["roles"]] == [
                "owner", "reviewer", "member", "viewer"]
            assert all(s["label"] and not s["label"].isascii()
                       for s in meta["statuses"]), "状态中文名缺失"

            print("SERVICE UNIT TESTS PASSED")
            """
        )
        self.assertEqual(result.returncode, 0,
                         msg="stdout:\n%s\nstderr:\n%s" % (result.stdout, result.stderr))


# --------------------------------------------------------------------------
# ② 集成测试：接口 + 数据库
# --------------------------------------------------------------------------
class ProjectApiIntegrationTests(unittest.TestCase):
    """`TestClient` 全流程：认证 → 建账套 → 项目 CRUD → 成员 → 删除。"""

    def test_project_api_end_to_end(self):
        result = _run(
            """
            from fastapi.testclient import TestClient
            from main import app

            with TestClient(app) as client:
                base = "/api/v1/projects"

                # 未登录 ⇒ 401
                assert client.get(base).status_code == 401, "未登录竟可读列表"

                login = client.post("/api/auth/login",
                                    json={"username": "integrationadmin",
                                          "password": "Integration-Test-2026!"})
                assert login.status_code == 200, login.text
                h = {"X-CSRF-Token": client.cookies.get("csrf_token")}

                # 元数据（字典）
                meta = client.get(base + "/meta")
                assert meta.status_code == 200, meta.text
                assert len(meta.json()["statuses"]) == 6

                # 建账套（作为租户边界）
                co = client.post("/api/companies", headers=h,
                                 json={"name": "项目测试账套",
                                       "uscc": "91440300MA5PJ00001"})
                assert co.status_code == 200, co.text
                cid = co.json()["id"]

                # 建项目
                created = client.post(base, headers=h, json={
                    "name": "集成测试科技有限公司",
                    "taxpayer_id": "91440300MA5PJ00002",
                    "industry": "信息技术服务", "region": "深圳",
                    "period_start": "2024-01-01", "period_end": "2024-12-31",
                    "tax_scopes": ["增值税", "企业所得税"],
                    "company_id": cid,
                })
                assert created.status_code == 201, created.text
                p = created.json()
                pid, code = p["id"], p["code"]
                assert p["status"] == "draft" and p["status_cn"] == "草稿", p

                # 列表（含搜索）
                lst = client.get(base, params={"q": "集成测试"})
                assert lst.status_code == 200, lst.text
                body = lst.json()
                assert body["total"] == 1 and body["items"][0]["id"] == pid, body
                # 分页字段契约
                for k in ("items", "total", "page", "page_size", "pages"):
                    assert k in body, "分页字段缺失：%s" % k

                # 详情（含成员 + 日志 + 可写标记）
                detail = client.get("%s/%d" % (base, pid))
                assert detail.status_code == 200, detail.text
                d = detail.json()
                assert d["id"] == pid and d["can_write"] is True, d
                assert isinstance(d["members"], list) and d["members"], d
                assert "logs" in d and "allowed_next_status" in d, d

                # 改字段
                upd = client.put("%s/%d" % (base, pid), headers=h,
                                 json={"region": "广州"})
                assert upd.status_code == 200, upd.text
                assert upd.json()["region"] == "广州"

                # 状态迁移（合法）
                mv = client.put("%s/%d" % (base, pid), headers=h,
                                json={"status": "uploading"})
                assert mv.status_code == 200, mv.text
                assert mv.json()["status_cn"] == "资料上传中", mv.json()

                # 状态迁移（反向：非法跳级 ⇒ 400）
                # ⚠ 此处目标必须**确实非法**：当前状态为 uploading，其允许后继为
                #   analyzing/draft/archived（`uploading → archived` 是**合法**的，
                #   初版用例误把它当"非法跳级"，实现是对的、用例错了）。
                #   取 `reported`：uploading → reported 跳过了 analyzing/reviewing ⇒ 非法。
                bad = client.put("%s/%d" % (base, pid), headers=h,
                                 json={"status": "reported"})
                assert bad.status_code == 400, bad.text

                # 成员：POST + GET
                add = client.post("%s/%d/members" % (base, pid), headers=h,
                                  json={"user_id": 55, "user_name": "李四",
                                        "role": "reviewer"})
                assert add.status_code == 201, add.text
                ms = client.get("%s/%d/members" % (base, pid))
                assert ms.status_code == 200, ms.text
                assert ms.json()["total"] == 2, ms.json()

                # 单条不存在 ⇒ 404
                assert client.get(base + "/99999999").status_code == 404

                # 删除 + 二次删除 ⇒ 404
                dele = client.delete("%s/%d" % (base, pid), headers=h)
                assert dele.status_code == 200, dele.text
                assert client.delete("%s/%d" % (base, pid), headers=h).status_code == 404

                # 落库校验（真的进库了，且级联清成员）
                import sqlite3, os
                db = os.path.join(os.environ["APP_DATA_DIR"], "accounting.db")
                conn = sqlite3.connect(db)
                n_p = conn.execute("SELECT COUNT(*) FROM projects WHERE id=?",
                                   (pid,)).fetchone()[0]
                n_m = conn.execute("SELECT COUNT(*) FROM project_members WHERE project_id=?",
                                   (pid,)).fetchone()[0]
                assert n_p == 0 and n_m == 0, (n_p, n_m)

                print("API INTEGRATION TESTS PASSED")
            """
        )
        self.assertEqual(result.returncode, 0,
                         msg="stdout:\n%s\nstderr:\n%s" % (result.stdout, result.stderr))


# --------------------------------------------------------------------------
# ③ 权限测试：跨租户不可见
# --------------------------------------------------------------------------
class ProjectPermissionTests(unittest.TestCase):
    """租户隔离三层：跨租户 404 · 同租户非成员只读 · 未授权账套不可建。"""

    def test_tenant_isolation_and_write_guard(self):
        result = _run(
            """
            import sqlite3, os
            import security
            from fastapi.testclient import TestClient
            from main import app

            base = "/api/v1/projects"
            with TestClient(app) as client:
                admin = client.post("/api/auth/login",
                                    json={"username": "integrationadmin",
                                          "password": "Integration-Test-2026!"})
                assert admin.status_code == 200, admin.text
                ah = {"X-CSRF-Token": client.cookies.get("csrf_token")}

                # 两个账套（两个租户）
                a = client.post("/api/companies", headers=ah,
                                json={"name": "租户A", "uscc": "91440300MA5TN00001"}).json()["id"]
                b = client.post("/api/companies", headers=ah,
                                json={"name": "租户B", "uscc": "91440300MA5TN00002"}).json()["id"]

                # admin 在 A 下建项目
                pa = client.post(base, headers=ah, json={
                    "name": "A租户项目", "company_id": a}).json()
                pid_a = pa["id"]

                # 建普通用户 u，仅授权 B
                uid = security.create_user("tenantuser", "Tenant-User-Pass-2026!",
                                           role="user")
                security.grant_company_to_user(uid, b)

                with TestClient(app) as uc:
                    lg = uc.post("/api/auth/login",
                                 json={"username": "tenantuser",
                                       "password": "Tenant-User-Pass-2026!"})
                    assert lg.status_code == 200, lg.text
                    uh = {"X-CSRF-Token": uc.cookies.get("csrf_token")}

                    # ★ 核心：跨租户 ⇒ 404（**不可见**；不是 403）
                    got = uc.get("%s/%d" % (base, pid_a))
                    assert got.status_code == 404, \\
                        "跨租户竟可访问！status=%s body=%s" % (got.status_code, got.text)
                    # 详情、成员、删除一律 404
                    assert uc.get("%s/%d/members" % (base, pid_a)).status_code == 404
                    assert uc.delete("%s/%d" % (base, pid_a), headers=uh).status_code == 404
                    assert uc.put("%s/%d" % (base, pid_a), headers=uh,
                                  json={"region": "越权"}).status_code == 404

                    # 列表里**不存在** A 的项目（不可见 = 不出现）
                    ids = [p["id"] for p in uc.get(base).json()["items"]]
                    assert pid_a not in ids, "跨租户项目出现在列表中"

                    # ★ 跨租户创建 ⇒ 403
                    mk = uc.post(base, headers=uh, json={"name": "越权项目", "company_id": a})
                    assert mk.status_code == 403, mk.text

                    # 同租户（B）可建；但**非成员**对同租户他人项目 ⇒ 只读
                    pb = uc.post(base, headers=uh, json={
                        "name": "B租户自己的项目", "company_id": b})
                    assert pb.status_code == 201, pb.text
                    assert pb.json()["company_id"] == b

                # admin 在 B 下另建一个项目；u 非其成员 ⇒ 可见但 can_write=False
                pb2 = client.post(base, headers=ah, json={
                    "name": "B租户admin的项目", "company_id": b}).json()
                with TestClient(app) as uc2:
                    uc2.post("/api/auth/login",
                             json={"username": "tenantuser",
                                   "password": "Tenant-User-Pass-2026!"})
                    u2h = {"X-CSRF-Token": uc2.cookies.get("csrf_token")}
                    d2 = uc2.get("%s/%d" % (base, pb2["id"]))
                    assert d2.status_code == 200, d2.text
                    assert d2.json()["can_write"] is False, "同租户非成员竟有写权限"
                    assert uc2.put("%s/%d" % (base, pb2["id"]), headers=u2h,
                                   json={"region": "偷改"}).status_code == 403

                print("PERMISSION TESTS PASSED")
            """
        )
        self.assertEqual(result.returncode, 0,
                         msg="stdout:\n%s\nstderr:\n%s" % (result.stdout, result.stderr))


# --------------------------------------------------------------------------
# ④ 审计日志测试
# --------------------------------------------------------------------------
class ProjectAuditTests(unittest.TestCase):
    """四类项目动作均写入 `audit_logs`，且中文名可读、可按项目追溯。"""

    def test_project_actions_are_audited(self):
        result = _run(
            """
            import sqlite3, os
            from fastapi.testclient import TestClient
            from main import app
            from engine.audit_trail import ACTIONS, ACTION_CN

            # 0) 词表契约：四个项目动作已登记且**中英一一对应**
            for a in ("project.create", "project.update", "project.delete",
                      "project.member_change"):
                assert a in ACTIONS, "动作未登记：%s" % a
                assert ACTION_CN.get(a), "缺中文名：%s" % a
                assert not ACTION_CN[a].isascii(), "中文名疑似英文码：%s" % ACTION_CN[a]

            base = "/api/v1/projects"
            with TestClient(app) as client:
                client.post("/api/auth/login",
                            json={"username": "integrationadmin",
                                  "password": "Integration-Test-2026!"})
                h = {"X-CSRF-Token": client.cookies.get("csrf_token")}
                cid = client.post("/api/companies", headers=h,
                                  json={"name": "审计测试账套",
                                        "uscc": "91440300MA5AU00001"}).json()["id"]

                p = client.post(base, headers=h, json={
                    "name": "审计测试企业", "company_id": cid}).json()
                pid, code = p["id"], p["code"]
                client.put("%s/%d" % (base, pid), headers=h, json={"region": "北京"})
                client.put("%s/%d" % (base, pid), headers=h, json={"status": "uploading"})
                client.post("%s/%d/members" % (base, pid), headers=h,
                            json={"user_id": 66, "user_name": "王五", "role": "member"})

                # 项目操作日志（详情内嵌）
                logs = client.get("%s/%d" % (base, pid)).json()["logs"]
                assert logs, "项目详情未带出操作日志"

                client.delete("%s/%d" % (base, pid), headers=h)

                # 1) 落库断言：四类动作齐全
                db = os.path.join(os.environ["APP_DATA_DIR"], "accounting.db")
                conn = sqlite3.connect(db)
                rows = conn.execute(
                    "SELECT action, COUNT(*) FROM audit_logs "
                    "WHERE target=? AND action LIKE 'project.%' GROUP BY action",
                    (code,)).fetchall()
                seen = dict(rows)
                for a in ("project.create", "project.update",
                          "project.member_change", "project.delete"):
                    assert seen.get(a, 0) >= 1, \\
                        "动作 %s 未留痕（实际见到的：%s）" % (a, list(seen))
                # 2) 留痕含账套归属与时间
                row = conn.execute(
                    "SELECT company_id, user_name, detail, created_at FROM audit_logs "
                    "WHERE target=? AND action='project.create'", (code,)).fetchone()
                assert row is not None, "项目创建未留痕"
                assert int(row[0]) == int(cid), "留痕账套归属错误"
                assert row[1], "留痕缺操作人"
                assert row[3] and len(str(row[3])) >= 19, "留痕缺北京时间戳"
                assert "审计测试企业" in str(row[2]), "留痕缺可读详情"

                # 3) 删除后**日志仍在**（留痕不随对象删除而消失）
                left = conn.execute(
                    "SELECT COUNT(*) FROM audit_logs WHERE target=? AND action='project.delete'",
                    (code,)).fetchone()[0]
                assert left == 1, "删除动作未留痕"

                print("AUDIT TESTS PASSED")
            """
        )
        self.assertEqual(result.returncode, 0,
                         msg="stdout:\n%s\nstderr:\n%s" % (result.stdout, result.stderr))


# --------------------------------------------------------------------------
# ⑤ 前端契约（结果级：页面与脚本**真的可访问**、关键控件**真的在**
# --------------------------------------------------------------------------
class ProjectFrontendContractTests(unittest.TestCase):
    """前端页面/脚本的**可访问性 + 关键控件存在性**（防止"后端有、前端没接"）。"""

    def test_page_and_script_are_reachable_with_controls(self):
        result = _run(
            """
            from fastapi.testclient import TestClient
            from main import app

            with TestClient(app) as client:
                # 未登录 ⇒ 302 到 /login（页面类请求，非 API）
                anon = client.get("/projects", follow_redirects=False)
                assert anon.status_code == 302, anon.status_code

                client.post("/api/auth/login",
                            json={"username": "integrationadmin",
                                  "password": "Integration-Test-2026!"})
                h = {"X-CSRF-Token": client.cookies.get("csrf_token")}

                # 已登录但**未选账套** ⇒ 既有安全策略重定向到 /select-company（不是缺陷）
                noselect = client.get("/projects", follow_redirects=False)
                assert noselect.status_code == 302, noselect.status_code
                assert "/select-company" in noselect.headers.get("location", ""), \\
                    noselect.headers.get("location")

                cid = client.post("/api/companies", headers=h,
                                  json={"name": "前端契约账套",
                                        "uscc": "91440300MA5FE00001"}).json()["id"]
                client.post("/api/auth/select-company", headers=h,
                            json={"company_id": cid})

                page = client.get("/projects")
                assert page.status_code == 200, page.text
                html = page.text
                # 页面级关键元素（任缺一 ⇒ 功能不可用）
                for kw in ("稽查项目管理", "/static/js/projects.js", "/static/js/security.js",
                           "新建项目", "确认删除", "f-status", "f-size", "tbody",
                           "btn-new", "m-form", "m-detail", "m-del"):
                    assert kw in html, "页面缺少关键元素：%s" % kw

                js = client.get("/static/js/projects.js")
                assert js.status_code == 200, js.status_code
                src = js.text
                # 四类交互能力（列表筛选/分页/详情/删除二次确认）**真的实现**
                for kw in ("loadList", "f-status", "page_size", "prev", "next",
                           "openDetail", "openForm", "askDelete", "m-del",
                           "moveStatus", "btn-addmember"):
                    assert kw in src, "脚本缺少实现：%s" % kw

                # 状态/角色字典来自后端 /meta（**前端不得硬编码**，防多头维护）
                assert "/meta" in src, "前端未从后端取字典"
                for hard in ("'已报告'", '"已报告"', "'待复核'", '"待复核"'):
                    assert hard not in src, "前端硬编码了状态中文名：%s" % hard

                # 主界面侧边栏有入口
                idx = client.get("/")
                assert idx.status_code == 200, idx.status_code
                assert "/projects" in idx.text, "主界面缺少项目入口"

                print("FRONTEND CONTRACT TESTS PASSED")
            """
        )
        self.assertEqual(result.returncode, 0,
                         msg="stdout:\n%s\nstderr:\n%s" % (result.stdout, result.stderr))


if __name__ == "__main__":
    unittest.main()