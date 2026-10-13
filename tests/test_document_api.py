# -*- coding: utf-8 -*-
"""P0-2 资料上传与管理 —— 五类测试（单元 / 集成 / 大文件与批量 / 审计 / 前端契约）。

隔离方式：**子进程 + `APP_DATA_DIR` 临时目录**（与 `tests/test_project_api.py`、
`tests/test_company_api.py` 同模式）—— 走**真实链路**（认证中间件 / 真实 SQLite /
真实磁盘落盘 / 真实留痕），数据落在临时目录 ⇒ **不污染** `data/`。

五类（任务书要求）：
  ① `DocumentUnitTests`            单元测试：上传、查重、分类（Service 层，不走 HTTP）
  ② `DocumentIntegrationTests`     集成测试：接口 + 存储（**真落盘 + 真登记 + 桥接既有清单**）
  ③ `DocumentBulkAndLargeTests`    大文件（分片续传）、批量上传
  ④ `DocumentAuditTests`           审计日志：上传 / 删除 / **下载**
  ⑤ `DocumentFrontendContractTests` 前端契约（页面/脚本可访问 + 关键能力存在）

★ 反向验证（真跑，非"断言自己构造的坏数据是坏的"）
  `test_reverse_signature_guard_is_real`：把魔数表清空 ⇒ **伪造扩展名必须能被放行**
  ⇒ 证明"扩展名不可单独信任"这条判据**真的在起作用**（清空即失效）。
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


def _run(script: str, *, timeout: int = 420) -> subprocess.CompletedProcess:
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
# ① 单元测试：上传 / 查重 / 分类
# --------------------------------------------------------------------------
class DocumentUnitTests(unittest.TestCase):
    def test_service_upload_dedup_classify(self):
        result = _run(
            """
            import hashlib
            from security import SessionContext
            from engine import document_service as SVC
            from engine.document_types import guess_category, category_cn, ALLOWED_EXTENSIONS

            sess = SessionContext(user_id=1, username="unitadmin", role="admin",
                                  allowed_company_ids=frozenset(company_ids if False else {1}),
                                  selected_company_id=1, csrf_hash="", expires_at=0)
            # 建一个项目（P0-1）
            from engine import project_service as PSVC
            proj = PSVC.create_project({"name": "资料单元测试企业", "company_id": 1}, sess)
            pid = proj["id"]

            # 1) 扩展名白名单：存量 12 种一个不少 + 新增 xml/ofd/zip
            for e in (".xlsx", ".xls", ".csv", ".pdf", ".txt", ".docx", ".doc",
                      ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".xml", ".ofd", ".zip"):
                assert e in ALLOWED_EXTENSIONS, "白名单缺失 %s" % e
            assert len(ALLOWED_EXTENSIONS) == 15, len(ALLOWED_EXTENSIONS)

            # 2) 分类映射（复用 filename_type_map.json + config/document_categories.json）
            cases = [("资产负债表2024.xlsx", "财务报表"),
                     ("银行流水.xlsx", "银行流水"),
                     ("销项发票明细.xlsx", "发票"),
                     ("增值税申报表.xlsx", "申报表"),
                     ("科目余额表.xlsx", "账簿"),
                     ("采购合同.pdf", "合同"),
                     ("工资表.xlsx", "薪酬")]
            for fn, want in cases:
                c, t = guess_category(fn)
                assert category_cn(c) == want, "%s 期望 %s 实际 %s" % (fn, want, category_cn(c))
            # 未识别 ⇒ **其他**（不猜测）
            c2, t2 = guess_category("某个没有特征的附件.xyz")
            assert t2 == "" and category_cn(c2) == "其他", (c2, t2)

            # 3) 上传（有效文件）
            xlsx = b"PK\\x03\\x04" + b"a" * 200
            r = SVC.upload_documents(pid, [
                ("资产负债表2024.xlsx", xlsx),
                ("不支持的.bin", b"xxx"),
                ("坏签名.xlsx", b"NOTAPKFILE"),
            ], sess)
            assert r["stats"]["uploaded"] == 1, r["stats"]
            assert r["stats"]["rejected"] == 2, r["stats"]
            reasons = " ".join(x["reason"] for x in r["rejected"])
            assert "不支持的文件类型" in reasons, reasons
            assert "内容与扩展名不匹配" in reasons, reasons
            up = r["uploaded"][0]
            assert up["category"] == "financial_statement", up
            assert up["md5"] == hashlib.md5(xlsx).hexdigest(), up
            assert up["sha256"] == hashlib.sha256(xlsx).hexdigest(), up

            # 4) 查重（同一项目内 ⇒ 跳过，且如实回报 duplicate_of）
            r2 = SVC.upload_documents(pid, [("另一个名字.xlsx", xlsx)], sess)
            assert r2["stats"]["uploaded"] == 0 and r2["stats"]["duplicated"] == 1, r2["stats"]
            dup = r2["duplicated"][0]
            assert dup["duplicate_of"] == up["id"] and dup["scope"] == "project", dup

            # 5) 跨项目同内容 ⇒ **不跳过**（合法场景），但提示 same_content_elsewhere
            p2 = PSVC.create_project({"name": "第二项目", "company_id": 1}, sess)
            r3 = SVC.upload_documents(p2["id"], [("同名内容.xlsx", xlsx)], sess)
            assert r3["stats"]["uploaded"] == 1, r3["stats"]
            assert r3["uploaded"][0].get("same_content_elsewhere"), r3["uploaded"][0]

            # 6) 分类人工修正（置 manual，防自动回改）
            c = SVC.classify_document(up["id"], "ledger", sess, note="实为账簿")
            assert c["category"] == "ledger" and c["classify_by"] == "manual", c
            assert c["previous_category"] == "financial_statement", c
            got = SVC.get_document(up["id"], sess)
            assert got["category_cn"] == "账簿" and got["classify_by"] == "manual", got
            # 非法分类 ⇒ 400 语义
            try:
                SVC.classify_document(up["id"], "不存在的类", sess)
                raise AssertionError("非法分类竟然成功")
            except SVC.DocumentError as e:
                assert e.status == 400

            # 7) 解析状态机：合法迁移 + 非法迁移
            SVC.set_parse_status(up["id"], "parsing", sess)
            SVC.set_parse_status(up["id"], "success", sess)
            try:
                SVC.set_parse_status(up["id"], "不存在", sess)
                raise AssertionError("非法状态竟然成功")
            except SVC.DocumentError as e:
                assert e.status == 400
            # manual 只能从已有状态进去；success→manual 合法
            SVC.set_parse_status(up["id"], "manual", sess)
            st = SVC.get_document(up["id"], sess)
            assert st["parse_status_cn"] == "需人工校正", st

            # 8) 分页记录
            SVC.save_pages(up["id"], [{"page_no": 1, "char_count": 12, "excerpt": "x"},
                                      {"page_no": 2, "char_count": 3, "excerpt": "y"}], sess)
            assert SVC.get_document(up["id"], sess)["page_count"] == 2

            # 9) 列表：搜索 / 分类筛选 / 状态筛选
            lst = SVC.list_documents(pid, sess)
            assert lst["total"] == 1 and "账簿" in lst["category_counts_cn"], lst
            assert SVC.list_documents(pid, sess, q="资产负债")["total"] == 1
            assert SVC.list_documents(pid, sess, q="不存在")["total"] == 0
            assert SVC.list_documents(pid, sess, category="ledger")["total"] == 1
            assert SVC.list_documents(pid, sess, category="invoice")["total"] == 0

            # 10) 脱敏：仅掩个人敏感标识；**税号/企业名/金额不脱敏**（主体与金额必须可复核）
            from engine.document_types import mask_sensitive, has_sensitive
            assert mask_sensitive("张三 13812345678") == "张三 138****5678", \
                mask_sensitive("张三 13812345678")
            assert mask_sensitive("身份证440101199001011234") == "身份证440101********1234"
            assert mask_sensitive("卡号6222021234567890123") == "卡号6222********0123"
            # 纳税人识别号 / 正常文件名 **保持不变**（不得脱敏）
            assert mask_sensitive("91440300MA5DC00001") == "91440300MA5DC00001"
            assert mask_sensitive("资产负债表2024.xlsx") == "资产负债表2024.xlsx"
            assert not has_sensitive("91440300MA5DC00001")
            assert has_sensitive("13812345678")
            # 展示字段已脱敏，原件名原样保留（可追溯）
            assert got["original_name_masked"] == got["original_name"]

            # 11) 删除
            d = SVC.delete_document(up["id"], sess)
            assert d["ok"], d
            try:
                SVC.get_document(up["id"], sess)
                raise AssertionError("删除后仍可查到")
            except SVC.DocumentError as e:
                assert e.status == 404

            print("DOCUMENT UNIT TESTS PASSED")
            """
        )
        self.assertEqual(result.returncode, 0,
                         msg="stdout:\n%s\nstderr:\n%s" % (result.stdout, result.stderr))


# --------------------------------------------------------------------------
# ② 集成测试：接口 + 存储
# --------------------------------------------------------------------------
class DocumentIntegrationTests(unittest.TestCase):
    def test_documents_api_end_to_end(self):
        result = _run(
            """
            import glob, os, sqlite3
            from fastapi.testclient import TestClient
            from main import app

            base = "/api/v1"
            with TestClient(app) as client:
                # 未登录 ⇒ 401
                assert client.get(base + "/documents/meta").status_code == 401

                client.post("/api/auth/login",
                            json={"username": "integrationadmin",
                                  "password": "Integration-Test-2026!"})
                h = {"X-CSRF-Token": client.cookies.get("csrf_token")}
                cid = client.post("/api/companies", headers=h,
                                  json={"name": "资料集成账套",
                                        "uscc": "91440300MA5DI00001"}).json()["id"]
                client.post("/api/auth/select-company", headers=h, json={"company_id": cid})
                pid = client.post(base + "/projects", headers=h,
                                  json={"name": "资料集成项目", "company_id": cid}).json()["id"]

                # 字典
                meta = client.get(base + "/documents/meta")
                assert meta.status_code == 200, meta.text
                m = meta.json()
                assert len(m["categories"]) == 9 and len(m["parse_statuses"]) == 5, m
                assert len(m["extensions"]) == 15, m["extensions"]
                assert m["limits"]["max_size"] == 10485760, m["limits"]

                # 上传（批量：1 有效 + 1 类型非法）
                up = client.post(base + "/projects/%d/documents" % pid, headers=h, files=[
                    ("files", ("资产负债表2024.xlsx", b"PK\\x03\\x04" + b"z" * 300,
                               "application/vnd.ms-excel")),
                    ("files", ("非法.bin", b"xx", "application/octet-stream")),
                ])
                assert up.status_code == 201, up.text
                body = up.json()
                assert body["stats"]["uploaded"] == 1 and body["stats"]["rejected"] == 1, body["stats"]
                did = body["uploaded"][0]["id"]
                assert body["uploaded"][0]["category_cn"] == "财务报表", body["uploaded"][0]

                # ★ 真落盘（指定文件名规范 {cid}_{docid}_{原名}）
                files = glob.glob(os.path.join(os.environ["APP_DATA_DIR"], "uploads", str(cid), "*"))
                assert files, "文件未落盘"
                assert os.path.basename(files[0]).startswith("%d_" % cid), files
                assert os.path.getsize(files[0]) == 300 + 4, os.path.getsize(files[0])

                # ★ 桥接既有资料清单（一键分析的输入源）
                import shared_state
                assert any(int(d.get("id") or -1) == int(body["uploaded"][0]["doc_id"])
                           for d in shared_state._tax_risk_docs), "未登记进既有资料清单"

                # 列表 + 概览
                lst = client.get(base + "/projects/%d/documents" % pid)
                assert lst.status_code == 200 and lst.json()["total"] == 1, lst.text
                assert "财务报表" in lst.json()["category_counts_cn"], lst.json()

                # 详情（含 MD5/SHA256/分页）
                det = client.get(base + "/documents/%d" % did)
                assert det.status_code == 200, det.text
                d = det.json()
                assert d["md5"] and d["sha256"] and "pages" in d, d
                assert d["watermark_on_download"] is True

                # 查重（同项目同内容 ⇒ 跳过）
                up2 = client.post(base + "/projects/%d/documents" % pid, headers=h, files=[
                    ("files", ("改名后.xlsx", b"PK\\x03\\x04" + b"z" * 300, "application/octet-stream"))])
                assert up2.json()["stats"]["duplicated"] == 1, up2.json()

                # 分类修正
                cl = client.post(base + "/documents/%d/classify" % did, headers=h,
                                 json={"category": "invoice", "note": "实为发票"})
                assert cl.status_code == 200, cl.text
                assert cl.json()["category_cn"] == "发票" and cl.json()["classify_by"] == "manual"
                # 非法分类 ⇒ 400
                assert client.post(base + "/documents/%d/classify" % did, headers=h,
                                   json={"category": "乱写"}).status_code == 400

                # 下载（水印）：CSV 走 sidecar，头部如实标注
                csv_up = client.post(base + "/projects/%d/documents" % pid, headers=h, files=[
                    ("files", ("流水.csv", b"a,b\\n1,2\\n", "text/csv"))]).json()["uploaded"][0]
                dl = client.get(base + "/documents/%d/download" % csv_up["id"])
                assert dl.status_code == 200, dl.text
                assert dl.headers.get("X-Watermark-Mode") == "sidecar", dl.headers
                assert dl.content == b"a,b\\n1,2\\n", "sidecar 模式内容必须原样（原件不改）"

                # 删除 ⇒ 文件移入回收站、登记消失、既有清单同步移除
                de = client.delete(base + "/documents/%d" % did, headers=h)
                assert de.status_code == 200 and de.json()["moved_to_trash"] is True, de.text
                assert client.get(base + "/documents/%d" % did).status_code == 404
                assert not any(int(x.get("id") or -1) == int(body["uploaded"][0]["doc_id"])
                               for x in shared_state._tax_risk_docs), "删除后既有清单未同步"

                # 落库校验
                conn = sqlite3.connect(os.path.join(os.environ["APP_DATA_DIR"], "accounting.db"))
                n = conn.execute("SELECT COUNT(*) FROM documents WHERE id=?", (did,)).fetchone()[0]
                pg = conn.execute("SELECT COUNT(*) FROM document_pages WHERE document_id=?",
                                  (did,)).fetchone()[0]
                assert n == 0 and pg == 0, (n, pg)

                print("DOCUMENT INTEGRATION TESTS PASSED")
            """
        )
        self.assertEqual(result.returncode, 0,
                         msg="stdout:\n%s\nstderr:\n%s" % (result.stdout, result.stderr))


# --------------------------------------------------------------------------
# ③ 大文件（分片续传）、批量上传
# --------------------------------------------------------------------------
class DocumentBulkAndLargeTests(unittest.TestCase):
    def test_resumable_and_batch(self):
        result = _run(
            """
            import hashlib, os
            from fastapi.testclient import TestClient
            from main import app

            base = "/api/v1"
            big = b"PK\\x03\\x04" + os.urandom(11 * 1024 * 1024)   # 11MB > 10MB 单请求上限
            md5 = hashlib.md5(big).hexdigest()

            with TestClient(app) as client:
                client.post("/api/auth/login",
                            json={"username": "integrationadmin",
                                  "password": "Integration-Test-2026!"})
                h = {"X-CSRF-Token": client.cookies.get("csrf_token")}
                cid = client.post("/api/companies", headers=h,
                                  json={"name": "大文件账套",
                                        "uscc": "91440300MA5BG00001"}).json()["id"]
                client.post("/api/auth/select-company", headers=h, json={"company_id": cid})
                pid = client.post(base + "/projects", headers=h,
                                  json={"name": "大文件项目", "company_id": cid}).json()["id"]

                # ① 单请求超限 ⇒ **可预期被拒**（不是崩溃）
                r = client.post(base + "/projects/%d/documents" % pid, headers=h, files=[
                    ("files", ("大表.xlsx", big, "application/octet-stream"))])
                assert r.status_code == 201, r.text
                assert r.json()["stats"]["rejected"] == 1, r.json()["stats"]
                assert "过大" in r.json()["rejected"][0]["reason"], r.json()["rejected"]

                # ② 分片上传（断点续传）
                ini = client.post(base + "/documents/chunk/init", headers=h,
                                  json={"project_id": pid, "filename": "大表.xlsx",
                                        "size": len(big), "md5": md5}).json()
                uid, cs, n = ini["upload_id"], ini["chunk_size"], ini["chunks_total"]
                assert n == 3 and cs == 5 * 1024 * 1024, ini
                parts = [big[i:i + cs] for i in range(0, len(big), cs)]

                # 只传前 2 片 ⇒ 查询应显示缺第 3 片（**续传依据**）
                for i in (0, 1):
                    assert client.put("%s/documents/chunk/%s/%d" % (base, uid, i), headers=h,
                                      content=parts[i]).status_code == 200
                st = client.get("%s/documents/chunk/%s" % (base, uid)).json()
                assert st["received"] == [0, 1] and st["missing"] == [2], st

                # 重复传第 0 片 ⇒ **幂等**（不重复计数）
                client.put("%s/documents/chunk/%s/0" % (base, uid), headers=h, content=parts[0])
                st2 = client.get("%s/documents/chunk/%s" % (base, uid)).json()
                assert st2["received"] == [0, 1], st2

                # 分片越界 ⇒ 400
                assert client.put("%s/documents/chunk/%s/99" % (base, uid), headers=h,
                                  content=b"x").status_code == 400

                # 补齐并合并
                client.put("%s/documents/chunk/%s/2" % (base, uid), headers=h, content=parts[2])
                fin = client.post("%s/documents/chunk/%s/complete" % (base, uid), headers=h)
                assert fin.status_code == 200, fin.text
                j = fin.json()
                assert j["stats"]["uploaded"] == 1, j
                assert j["uploaded"][0]["size"] == len(big), j["uploaded"][0]
                assert j["uploaded"][0]["md5"] == md5, j["uploaded"][0]

                # 会话已清理（避免残留分片目录）
                sess_dir = os.path.join(os.environ["APP_DATA_DIR"], "upload_sessions")
                left = [x for x in os.listdir(sess_dir)] if os.path.isdir(sess_dir) else []
                assert not left, left

                # ③ 批量上传（10 个不同内容）
                many = [("files", ("批量%d.xlsx" % i, b"PK\\x03\\x04" + bytes([i]) * 50,
                                   "application/octet-stream")) for i in range(10)]
                b = client.post(base + "/projects/%d/documents" % pid, headers=h, files=many)
                assert b.status_code == 201, b.text
                assert b.json()["stats"]["uploaded"] == 10, b.json()["stats"]
                assert client.get(base + "/projects/%d/documents" % pid,
                                  params={"page_size": 50}).json()["total"] == 11, "应为 11（分片大表 1 + 批量 10）"

                print("BULK AND LARGE TESTS PASSED")
            """
        )
        self.assertEqual(result.returncode, 0,
                         msg="stdout:\n%s\nstderr:\n%s" % (result.stdout, result.stderr))


# --------------------------------------------------------------------------
# ④ 审计日志：上传 / 删除 / 下载
# --------------------------------------------------------------------------
class DocumentAuditTests(unittest.TestCase):
    def test_upload_delete_download_are_audited(self):
        result = _run(
            """
            import os, sqlite3
            from fastapi.testclient import TestClient
            from main import app
            from engine.audit_trail import ACTIONS, ACTION_CN

            # 0) 词表契约：三个资料动作已登记且中英一一对应（中文名不得是英文码）
            for a in ("doc.upload", "doc.delete", "doc.download", "doc.classify"):
                assert a in ACTIONS, "动作未登记：%s" % a
                assert ACTION_CN.get(a), "缺中文名：%s" % a
                assert not ACTION_CN[a].isascii(), ACTION_CN[a]

            base = "/api/v1"
            with TestClient(app) as client:
                client.post("/api/auth/login",
                            json={"username": "integrationadmin",
                                  "password": "Integration-Test-2026!"})
                h = {"X-CSRF-Token": client.cookies.get("csrf_token")}
                cid = client.post("/api/companies", headers=h,
                                  json={"name": "审计账套",
                                        "uscc": "91440300MA5AT00001"}).json()["id"]
                client.post("/api/auth/select-company", headers=h, json={"company_id": cid})
                pid = client.post(base + "/projects", headers=h,
                                  json={"name": "审计项目", "company_id": cid}).json()["id"]

                up = client.post(base + "/projects/%d/documents" % pid, headers=h, files=[
                    ("files", ("流水2024.csv", b"a,b\\n1,2\\n", "text/csv"))]).json()
                did = up["uploaded"][0]["id"]
                name = up["uploaded"][0]["original_name"]

                client.get(base + "/documents/%d/download" % did)          # 下载 ⇒ 留痕
                client.post(base + "/documents/%d/classify" % did, headers=h,
                            json={"category": "bank_statement"})           # 分类修正 ⇒ 留痕
                client.delete(base + "/documents/%d" % did, headers=h)     # 删除 ⇒ 留痕

                conn = sqlite3.connect(os.path.join(os.environ["APP_DATA_DIR"], "accounting.db"))
                rows = dict(conn.execute(
                    "SELECT action, COUNT(*) FROM audit_logs WHERE target=? "
                    "AND action LIKE 'doc.%' GROUP BY action", (name,)).fetchall())
                for a in ("doc.upload", "doc.download", "doc.classify", "doc.delete"):
                    assert rows.get(a, 0) >= 1, "动作 %s 未留痕（实际 %s）" % (a, list(rows))

                # 留痕含账套归属 / 操作人 / 北京时间戳 / 可读详情
                row = conn.execute(
                    "SELECT company_id, user_name, detail, created_at FROM audit_logs "
                    "WHERE target=? AND action='doc.upload'", (name,)).fetchone()
                assert int(row[0]) == int(cid) and row[1], row
                assert row[3] and len(str(row[3])) >= 19, row
                # ★ 留痕**不得**包含文件内容（只写文件名/数量/结果）
                assert "a,b" not in str(row[2]), row[2]

                print("DOCUMENT AUDIT TESTS PASSED")
            """
        )
        self.assertEqual(result.returncode, 0,
                         msg="stdout:\n%s\nstderr:\n%s" % (result.stdout, result.stderr))


# --------------------------------------------------------------------------
# ⑤ 前端契约
# --------------------------------------------------------------------------
class DocumentFrontendContractTests(unittest.TestCase):
    def test_page_and_script_expose_required_capabilities(self):
        result = _run(
            """
            from fastapi.testclient import TestClient
            from main import app

            with TestClient(app) as c:
                anon = c.get("/documents", follow_redirects=False)
                assert anon.status_code == 302, anon.status_code     # 未登录跳 /login

                c.post("/api/auth/login", json={"username": "integrationadmin",
                                                "password": "Integration-Test-2026!"})
                h = {"X-CSRF-Token": c.cookies.get("csrf_token")}
                cid = c.post("/api/companies", headers=h,
                             json={"name": "前端账套", "uscc": "91440300MA5FE00002"}).json()["id"]
                c.post("/api/auth/select-company", headers=h, json={"company_id": cid})

                page = c.get("/documents")
                assert page.status_code == 200, page.text
                for kw in ("资料上传与管理", "/static/js/documents.js", "/static/js/security.js",
                           "把文件拖到", "picker", "f-cat", "f-status", "tbody",
                           "m-classify", "m-detail", "m-del", "proj"):
                    assert kw in page.text, "页面缺关键元素：%s" % kw

                js = c.get("/static/js/documents.js")
                assert js.status_code == 200
                src = js.text
                for kw in ("handleFiles", "dataTransfer", "uploadOne", "uploadChunked",
                           "localStorage", "chunk/init", "openClassify", "downloadDoc",
                           "askDelete", "X-Watermark-Mode", "decodeURIComponent",
                           "prev", "next", "f-size"):
                    assert kw in src, "脚本缺实现：%s" % kw

                # 字典必须来自后端（前端**不得**硬编码分类中文名）
                assert "/documents/meta" in src, "前端未从后端取字典"
                for hard in ("'财务报表'", '"财务报表"', "'银行流水'", '"银行流水"'):
                    assert hard not in src, "前端硬编码了分类中文名：%s" % hard

                idx = c.get("/")
                assert "/documents" in idx.text, "主界面缺资料入口"

                print("DOCUMENT FRONTEND CONTRACT TESTS PASSED")
            """
        )
        self.assertEqual(result.returncode, 0,
                         msg="stdout:\n%s\nstderr:\n%s" % (result.stdout, result.stderr))


# --------------------------------------------------------------------------
# ⑥ 反向验证（真跑）
# --------------------------------------------------------------------------
class DocumentReverseVerification(unittest.TestCase):
    def test_reverse_signature_guard_is_real(self):
        """★ 反向验证：「扩展名不得单独可信」这条判据**真的在起作用**。

        做法（同进程、只改内存）：
          ① 正常情况：`坏签名.xlsx`（内容是 `NOTAPK`）⇒ 必须被拒；
          ② 把魔数表清空（`document_types.SIGNATURES = {}`）⇒ **同一文件必须被放行**
             ⇒ 证明"拒绝"确实来自魔数校验，而非别的偶然原因（判据有效）。
        """
        result = _run(
            """
            from security import SessionContext
            from engine import document_service as SVC
            from engine import document_types as DT
            from engine import project_store as PSTOR

            sess = SessionContext(user_id=1, username="rv", role="admin",
                                  allowed_company_ids=frozenset({1}),
                                  selected_company_id=1, csrf_hash="", expires_at=0)
            from engine import project_service as PSVC
            pid = PSVC.create_project({"name": "反向验证企业", "company_id": 1}, sess)["id"]
            bad = ("坏签名.xlsx", b"NOTAPKFILE" + b"0" * 100)

            # ① 正常：必须拒
            r1 = SVC.upload_documents(pid, [bad], sess)
            assert r1["stats"]["rejected"] == 1 and r1["stats"]["uploaded"] == 0, r1["stats"]
            assert "内容与扩展名不匹配" in r1["rejected"][0]["reason"], r1["rejected"]

            # ② 清空魔数表 ⇒ 同一文件必须被放行（判据失效则"拒绝"就不是它造成的）
            saved = dict(DT.SIGNATURES)
            try:
                DT.SIGNATURES.clear()
                r2 = SVC.upload_documents(pid, [bad], sess)
                assert r2["stats"]["uploaded"] == 1, \
                    "魔数表已清空却仍被拒 ⇒ 拒绝并非来自魔数校验（判据不成立）"
            finally:
                DT.SIGNATURES.update(saved)

            # ③ 还原后必须再次拒（确认可复现）
            r3 = SVC.upload_documents(pid, [("坏签名2.xlsx", bad[1])], sess)
            assert r3["stats"]["rejected"] == 1, r3["stats"]

            print("REVERSE VERIFICATION PASSED")
            """
        )
        self.assertEqual(result.returncode, 0,
                         msg="stdout:\n%s\nstderr:\n%s" % (result.stdout, result.stderr))


# --------------------------------------------------------------------------
# ⑦ 租户隔离（跨租户**一律 404**，与 P0-1 同一口径）
# --------------------------------------------------------------------------
class DocumentTenantIsolationTests(unittest.TestCase):
    def test_cross_tenant_is_invisible(self):
        result = _run(
            """
            import security
            from fastapi.testclient import TestClient
            from main import app

            base = "/api/v1"
            with TestClient(app) as c:
                c.post("/api/auth/login", json={"username": "integrationadmin",
                                                "password": "Integration-Test-2026!"})
                h = {"X-CSRF-Token": c.cookies.get("csrf_token")}
                a = c.post("/api/companies", headers=h,
                           json={"name": "租户A", "uscc": "91440300MA5TA00001"}).json()["id"]
                b = c.post("/api/companies", headers=h,
                           json={"name": "租户B", "uscc": "91440300MA5TB00002"}).json()["id"]
                pa = c.post(base + "/projects", headers=h,
                            json={"name": "A项目", "company_id": a}).json()["id"]
                up = c.post(base + "/projects/%d/documents" % pa, headers=h, files=[
                    ("files", ("A的资料.xlsx", b"PK\\x03\\x04" + b"A" * 80,
                               "application/octet-stream"))]).json()
                did = up["uploaded"][0]["id"]

                uid = security.create_user("docuser", "Doc-User-Pass-2026!", role="user")
                security.grant_company_to_user(uid, b)

                with TestClient(app) as uc:
                    uc.post("/api/auth/login",
                            json={"username": "docuser", "password": "Doc-User-Pass-2026!"})
                    uh = {"X-CSRF-Token": uc.cookies.get("csrf_token")}
                    # ★ 六个入口**全部 404**（不是 403 —— 不泄露"对象是否存在"）
                    assert uc.get(base + "/documents/%d" % did).status_code == 404, "详情越权"
                    assert uc.get(base + "/documents/%d/download" % did).status_code == 404, "下载越权"
                    assert uc.delete(base + "/documents/%d" % did,
                                     headers=uh).status_code == 404, "删除越权"
                    assert uc.post(base + "/documents/%d/classify" % did, headers=uh,
                                   json={"category": "invoice"}).status_code == 404, "分类越权"
                    # 无权项目 ⇒ 列表 404
                    assert uc.get(base + "/projects/%d/documents" % pa).status_code == 404
                    # 无权项目 ⇒ 上传 404（项目不可见 ⇒ 不泄露）
                    assert uc.post(base + "/projects/%d/documents" % pa, headers=uh, files=[
                        ("files", ("x.xlsx", b"PK\\x03\\x04z", "application/octet-stream"))
                    ]).status_code == 404
                    # 自己租户内可正常上传
                    pb = uc.post(base + "/projects", headers=uh,
                                 json={"name": "B项目", "company_id": b}).json()["id"]
                    assert uc.post(base + "/projects/%d/documents" % pb, headers=uh, files=[
                        ("files", ("B的资料.xlsx", b"PK\\x03\\x04" + b"B" * 10,
                                   "application/octet-stream"))]).status_code == 201

                print("TENANT ISOLATION TESTS PASSED")
            """
        )
        self.assertEqual(result.returncode, 0,
                         msg="stdout:\n%s\nstderr:\n%s" % (result.stdout, result.stderr))


if __name__ == "__main__":
    unittest.main()
