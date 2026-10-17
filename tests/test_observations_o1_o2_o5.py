# -*- coding: utf-8 -*-
"""观察项 O1 / O2 / O5 的回归守护（2026-10-17，b 任务）。

| 编号 | 缺陷（修前） | 修后判据 |
|---|---|---|
| **O1** | `POST /api/remediation/create` 对不存在的账套**仍创建记录**（实测 `company_id=999999` 成功） | 不存在账套 ⇒ **404**，且**不落库** |
| **O2** | `POST /api/tax-risk-docs/review` 对不存在账套返回 **500**（冒充服务端故障） | 不存在账套 ⇒ **404**（4xx） |
| **O5** | `DELETE /api/v1/projects/{id}` **不级联**项目下资料（实测残留 20 条 + 102 条孤儿） | 有资料且未传 `cascade` ⇒ **409**；`cascade=true` ⇒ 资料清除、文件**进回收站**（非永久删除） |

★ 每个用例都带**反向验证**：证明它真的在测"修复后的行为"，而不是恒真。
"""
from __future__ import annotations

import pathlib
import sys
import textwrap

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── 静态判据（不依赖起服务，先锁住"代码里确实有校验"）─────────────────────
def test_o1_source_has_company_guard() -> None:
    """O1：创建整改记录前必须有账套存在性校验。"""
    src = (ROOT / "main.py").read_text(encoding="utf-8")
    i = src.index('@app.post("/api/remediation/create")')
    body = src[i:i + 1600]
    assert "Company.id == company_id" in body, "create_remediation 未校验账套存在性"
    assert 'raise HTTPException(404' in body, "create_remediation 未对不存在账套返回 404"


def test_o2_source_has_company_guard() -> None:
    """O2：复核入口必须有账套存在性校验（不再一路走到分析层抛 500）。"""
    src = (ROOT / "main.py").read_text(encoding="utf-8")
    i = src.index('@app.post("/api/tax-risk-docs/review")')
    body = src[i:i + 1800]
    assert "Company.id == company_id" in body, "review_tax_risk_docs 未校验账套"
    assert 'raise HTTPException(404' in body, "review_tax_risk_docs 未返回 404"


def _func_body(path: pathlib.Path, name: str) -> str:
    """按 **AST 行号**精确取出顶层函数的完整源码。

    ★ 不能用"从 `def x(` 起截 N 个字符"：会截在多行字符串中间 ⇒ 解析失败
      （第一版就这么炸了 SyntaxError）。行号由 AST 给出，绝对准确。
    """
    import ast
    src = path.read_text(encoding="utf-8")
    for node in ast.parse(src).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            lines = src.splitlines()
            return "\n".join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError("%s 中找不到函数 %s" % (path.name, name))


def _calls(fn_src: str):
    """解析函数源码，返回其中**真实调用**的名字集合（注释/字符串不计）。

    ★ 不能对源码做字符串搜索：注释里写"绝不 os.remove"会被误判为调用
      （第一版就这么误报了）⇒ 必须走 AST。
    """
    import ast
    tree = ast.parse(textwrap.dedent(fn_src))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute):
                base = f.value.id if isinstance(f.value, ast.Name) else ""
                out.add(("%s.%s" % (base, f.attr)).lstrip("."))
            elif isinstance(f, ast.Name):
                out.add(f.id)
    return out


def test_o5_source_cascades_documents_and_uses_trash() -> None:
    """O5：删项目必须处置资料，且物理文件走回收站（**不 os.remove**）。"""
    body = _func_body(ROOT / "engine" / "project_service.py", "delete_project")
    assert "cascade" in body, "delete_project 未支持 cascade"
    assert "DELETE FROM documents WHERE project_id" in body, "未级联删除项目下资料"
    assert "409" in body, "项目有资料且未确认时未返回 409"

    # ★ AST 判据：真实调用里有 move_to_trash、且**没有** os.remove
    calls = _calls(body)
    assert "move_to_trash" in calls, "物理文件未走回收站（调用集=%s）" % sorted(calls)
    assert "os.remove" not in calls, "★ 真实调用了 os.remove ⇒ 违反「删除优先进回收站」铁律"


def test_o5_reverse_missing_cascade_would_leak() -> None:
    """反向验证：若把级联语句删掉，判据必须报错（证明判据非空转）。"""
    body = _func_body(ROOT / "engine" / "project_service.py", "delete_project")
    broken = body.replace("DELETE FROM documents WHERE project_id", "SELECT 1", 1)
    assert broken != body, "反向验证锚点未命中"
    assert "DELETE FROM documents WHERE project_id" not in broken


def test_o5_reverse_os_remove_is_detected() -> None:
    """反向验证：把 `move_to_trash(p)` 换成 `os.remove(p)`，AST 判据必须报错。"""
    body = _func_body(ROOT / "engine" / "project_service.py", "delete_project")
    assert "move_to_trash(p)" in body, "反向验证前提失效"
    broken = body.replace("move_to_trash(p)", "os.remove(p)", 1)
    calls = _calls(broken)
    assert "move_to_trash" not in calls and "os.remove" in calls, (
        "反向验证失败：换成 os.remove 后判据仍看不出 ⇒ 判据是假的")


# ── 运行期判据（**子进程** + 隔离 APP_DATA_DIR 走真 HTTP）─────────────────
#: 与项目既有约定一致：用 `APP_ADMIN_USERNAME/PASSWORD` 建管理员账号，
#: 且**必须**在子进程里跑（同进程改 `sys.modules` 会被其它测试的缓存污染 ⇒ 假绿）。
RUNTIME_SCRIPT = r'''
import json, os, sys
from fastapi.testclient import TestClient
import main as app_main

out = {}
with TestClient(app_main.app) as c:
    r = c.post("/api/auth/login", json={"username": os.environ["APP_ADMIN_USERNAME"],
                                        "password": os.environ["APP_ADMIN_PASSWORD"]})
    out["login"] = r.status_code
    h = {"X-CSRF-Token": c.cookies.get("csrf_token") or ""}

    from database import SessionLocal, RemediationRecord

    def count():
        db = SessionLocal()
        try:
            return db.query(RemediationRecord).filter(
                RemediationRecord.company_id == 999999).count()
        finally:
            db.close()

    out["remediation_before"] = count()
    r1 = c.post("/api/remediation/create", params={"company_id": 999999}, headers=h)
    out["remediation_status"] = r1.status_code
    out["remediation_after"] = count()
    out["remediation_body"] = (r1.text or "")[:200]

    r2 = c.post("/api/tax-risk-docs/review", params={"company_id": 999999}, headers=h)
    out["review_status"] = r2.status_code
    out["review_body"] = (r2.text or "")[:200]

    # 反向验证：直接用 ORM 建一条孤儿，证明"若不校验确实能落库"（前置判据有意义）
    db = SessionLocal()
    try:
        db.add(RemediationRecord(company_id=999999, finding_type="probe",
                                 finding_detail="反向验证用", risk_level="中",
                                 status="pending"))
        db.commit()
        out["orm_orphan_ok"] = count() >= 1
    finally:
        db.query(RemediationRecord).filter(
            RemediationRecord.company_id == 999999).delete()
        db.commit()
        db.close()
    out["remediation_final"] = count()

print("RESULT=" + json.dumps(out, ensure_ascii=False))
'''


def _run_runtime(**overrides) -> dict:
    """在隔离子进程里跑运行期用例，返回解析后的结果 dict。"""
    import base64
    import json
    import os
    import subprocess
    import tempfile

    env = os.environ.copy()
    with tempfile.TemporaryDirectory() as d:
        env.update({
            "APP_DATA_DIR": d,
            "APP_COOKIE_SECURE": "0",
            "APP_ALLOWED_ORIGINS": "http://testserver",
            "APP_ADMIN_USERNAME": "o1o2o5admin",
            "APP_ADMIN_PASSWORD": "O1O2O5-Admin-Pass-2026!",
            "APP_LLM_MASTER_KEY": base64.urlsafe_b64encode(bytes(range(32))).decode(),
            "PYTHONIOENCODING": "utf-8",
        })
        env.update({k: str(v) for k, v in overrides.items()})
        cp = subprocess.run([sys.executable, "-c", RUNTIME_SCRIPT], cwd=str(ROOT),
                            env=env, capture_output=True, text=True, timeout=600)
    line = [x for x in (cp.stdout or "").splitlines() if x.startswith("RESULT=")]
    assert line, "子进程未产出 RESULT：stdout=%r stderr=%r" % (
        (cp.stdout or "")[-800:], (cp.stderr or "")[-1200:])
    return json.loads(line[-1][len("RESULT="):])


@pytest.fixture(scope="module")
def runtime():
    return _run_runtime()


def test_runtime_login_ok(runtime) -> None:
    """前置：子进程实例里管理员能登录（否则后续判据无意义）。"""
    assert runtime["login"] == 200, "管理员登录失败（%s）" % runtime["login"]


def test_o1_runtime_rejects_missing_company(runtime) -> None:
    """运行期：不存在账套 ⇒ **404**，且**不落库**（修前 200 且写一条孤儿）。"""
    assert runtime["remediation_status"] == 404, (
        "不存在账套仍被接受（HTTP %s，body=%s）"
        % (runtime["remediation_status"], runtime["remediation_body"]))
    assert runtime["remediation_after"] == runtime["remediation_before"], (
        "★ 仍落库了孤儿整改记录：%s → %s"
        % (runtime["remediation_before"], runtime["remediation_after"]))


def test_o1_reverse_orm_would_create_orphan(runtime) -> None:
    """反向验证：ORM 直写仍能建孤儿 ⇒ 证明上一条的 404 是**校验**带来的，不是天生写不进。"""
    assert runtime["orm_orphan_ok"] is True, (
        "ORM 也无法写孤儿 ⇒ 反向验证不成立，上一条判据可能无意义")
    assert runtime["remediation_final"] == 0, "反向验证数据未清理干净"


def test_o2_runtime_returns_404_not_500(runtime) -> None:
    """运行期：复核不存在账套 ⇒ **404**（修前 500，冒充服务端故障）。"""
    assert runtime["review_status"] == 404, (
        "应为 404，实际 %s（body=%s）"
        % (runtime["review_status"], runtime["review_body"]))


# ── O5 运行期：真 HTTP 建项目 → 挂资料 → 删除（409 / cascade）────────────────
O5_SCRIPT = r'''
import json, os
from fastapi.testclient import TestClient
import main as app_main
from database import engine
from engine.document_store import ensure_schema as _ensure_docs
from sqlalchemy import text
_ensure_docs(engine)          # documents 表是运行时按需建的（不在 Base.metadata）

out = {}
with TestClient(app_main.app) as c:
    c.post("/api/auth/login", json={"username": os.environ["APP_ADMIN_USERNAME"],
                                    "password": os.environ["APP_ADMIN_PASSWORD"]})
    h = {"X-CSRF-Token": c.cookies.get("csrf_token") or ""}
    proj = c.post("/api/v1/projects", headers=h, json={
        "name": "O5级联验证", "taxpayer_id": "91440300MA5O5PROBE", "period_start": "",
        "period_end": "", "industry": "", "region": ""})
    out["create_status"] = proj.status_code
    pid = (proj.json() or {}).get("id")
    out["pid"] = pid
    if pid:
        # documents 不在 ORM 层（project_service 用 raw SQL）⇒ 这里同样用 text()
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO documents (project_id, company_id, doc_id, filename,"
                " original_name, ext, size, md5, sha256, doc_type, category,"
                " parse_status, uploaded_by, storage_path)"
                " VALUES (:p, NULL, :d, :f, :f, :e, 10, 'm', 's', 'other', 'other',"
                " 'success', 'probe', '')"), {"p": int(pid), "d": "o5probe1", "f": "o5probe.xlsx", "e": ".xlsx"})

        def doc_count():
            with engine.begin() as conn:
                return int(conn.execute(text(
                    "SELECT COUNT(*) FROM documents WHERE project_id=:p"),
                    {"p": int(pid)}).scalar() or 0)

        out["docs_before"] = doc_count()
        r1 = c.delete("/api/v1/projects/%s" % pid, headers=h)
        out["delete_no_cascade"] = r1.status_code
        out["delete_no_cascade_body"] = (r1.text or "")[:240]
        out["docs_after_refused"] = doc_count()
        out["project_still_there"] = c.get("/api/v1/projects/%s" % pid, headers=h).status_code

        r2 = c.delete("/api/v1/projects/%s?cascade=true" % pid, headers=h)
        out["delete_cascade"] = r2.status_code
        out["delete_cascade_body"] = (r2.text or "")[:240]
        out["docs_after_cascade"] = doc_count()
        out["project_after_cascade"] = c.get("/api/v1/projects/%s" % pid, headers=h).status_code
print("RESULT=" + json.dumps(out, ensure_ascii=False))
'''


@pytest.fixture(scope="module")
def o5runtime() -> dict:
    import base64
    import json
    import os
    import subprocess
    import tempfile

    env = os.environ.copy()
    with tempfile.TemporaryDirectory() as d:
        env.update({
            "APP_DATA_DIR": d,
            "APP_COOKIE_SECURE": "0",
            "APP_ALLOWED_ORIGINS": "http://testserver",
            "APP_ADMIN_USERNAME": "o5admin",
            "APP_ADMIN_PASSWORD": "O5-Admin-Pass-2026!",
            "APP_LLM_MASTER_KEY": base64.urlsafe_b64encode(bytes(range(32))).decode(),
            "PYTHONIOENCODING": "utf-8",
        })
        cp = subprocess.run([sys.executable, "-c", O5_SCRIPT], cwd=str(ROOT),
                            env=env, capture_output=True, text=True, timeout=600)
    line = [x for x in (cp.stdout or "").splitlines() if x.startswith("RESULT=")]
    assert line, "O5 子进程未产出 RESULT：stdout=%r stderr=%r" % (
        (cp.stdout or "")[-800:], (cp.stderr or "")[-1200:])
    return json.loads(line[-1][len("RESULT="):])


def test_o5_runtime_refuses_without_cascade(o5runtime) -> None:
    """运行期：项目下有资料、未传 cascade ⇒ **409**，且**什么都没删**。"""
    assert o5runtime["create_status"] in (200, 201), "建项目失败：%s" % o5runtime["create_status"]
    assert o5runtime["docs_before"] >= 1, "前置失效：没能给项目挂上资料"
    assert o5runtime["delete_no_cascade"] == 409, (
        "应 409（要求确认），实际 %s（body=%s）"
        % (o5runtime["delete_no_cascade"], o5runtime["delete_no_cascade_body"]))
    assert o5runtime["docs_after_refused"] == o5runtime["docs_before"], "被拒后资料数竟变了"
    assert o5runtime["project_still_there"] == 200, "被拒后项目却没了"


def test_o5_runtime_cascade_removes_documents(o5runtime) -> None:
    """运行期：`cascade=true` ⇒ 项目删除、资料**清零**。"""
    assert o5runtime["delete_cascade"] in (200, 204), (
        "级联删除失败：%s（body=%s）"
        % (o5runtime["delete_cascade"], o5runtime["delete_cascade_body"]))
    assert o5runtime["docs_after_cascade"] == 0, "★ 项目删了但资料还残留 %s 条" % o5runtime["docs_after_cascade"]
    assert o5runtime["project_after_cascade"] == 404, "项目未被真正删除"


def test_o5_reverse_missing_documents_table_is_guarded() -> None:
    """**防复发**：`documents` 表是运行时按需建的（老库可能没有）⇒ delete_project
    必须先判表存在，否则 `SELECT ... FROM documents` 会把"删项目"整个打死。

    本用例锁定源码里确实有 sqlite_master 守卫（2026-10-17 实测踩过：
    `test_project_api::test_project_api_end_to_end` 因 `no such table: documents` 失败）。
    """
    body = _func_body(ROOT / "engine" / "project_service.py", "delete_project")
    assert "sqlite_master" in body, (
        "delete_project 未判断 documents 表是否存在 ⇒ 老库上删项目会抛 "
        "`no such table: documents`")
    # 且不能靠裸 try/except 静默吞掉（那是掩盖而非处理）
    assert "except Exception" not in body, (
        "用了裸 except 吞异常 ⇒ 掩盖问题；应显式判表存在")


def test_o5_runtime_delete_works_without_documents_table() -> None:
    """运行期：库中**没有** documents 表时，删项目仍应成功（不被级联逻辑打死）。"""
    import base64
    import json
    import os
    import subprocess
    import tempfile

    script = r'''
import json, os
from fastapi.testclient import TestClient
import main as app_main
out = {}
with TestClient(app_main.app) as c:
    c.post("/api/auth/login", json={"username": os.environ["APP_ADMIN_USERNAME"],
                                    "password": os.environ["APP_ADMIN_PASSWORD"]})
    h = {"X-CSRF-Token": c.cookies.get("csrf_token") or ""}
    p = c.post("/api/v1/projects", headers=h, json={
        "name": "O5无资料表", "taxpayer_id": "91440300MA5O5NODOC"})
    out["create"] = p.status_code
    pid = (p.json() or {}).get("id")
    out["pid"] = pid
    if pid:
        r = c.delete("/api/v1/projects/%s" % pid, headers=h)
        out["delete"] = r.status_code
        out["body"] = (r.text or "")[:200]
print("RESULT=" + json.dumps(out, ensure_ascii=False))
'''
    env = os.environ.copy()
    with tempfile.TemporaryDirectory() as d:
        env.update({
            "APP_DATA_DIR": d, "APP_COOKIE_SECURE": "0",
            "APP_ALLOWED_ORIGINS": "http://testserver",
            "APP_ADMIN_USERNAME": "o5nodoc", "APP_ADMIN_PASSWORD": "O5-NoDoc-Pass-2026!",
            "APP_LLM_MASTER_KEY": base64.urlsafe_b64encode(bytes(range(32))).decode(),
            "PYTHONIOENCODING": "utf-8",
        })
        cp = subprocess.run([sys.executable, "-c", script], cwd=str(ROOT),
                            env=env, capture_output=True, text=True, timeout=600)
    line = [x for x in (cp.stdout or "").splitlines() if x.startswith("RESULT=")]
    assert line, "子进程未产出 RESULT：stderr=%r" % (cp.stderr or "")[-800:]
    got = json.loads(line[-1][len("RESULT="):])
    assert got["create"] in (200, 201), "建项目失败：%s" % got["create"]
    assert got["delete"] in (200, 204), (
        "无 documents 表时删项目失败：HTTP %s（body=%s）"
        % (got["delete"], got.get("body")))
