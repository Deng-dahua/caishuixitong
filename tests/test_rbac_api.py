# -*- coding: utf-8 -*-
"""P0-8 权限 / 租户 / 审计 / 脱敏 —— 五类测试（任务书 §测试）。

隔离方式：**子进程 + `APP_DATA_DIR` 临时目录**（与 `tests/test_project_api.py`、
`tests/test_document_api.py` 同一模式）—— 走**真实链路**（鉴权中间件 / 真实 SQLite /
真实留痕 / 真实脱敏），数据落在临时目录 ⇒ **不污染** `data/security.db` 与
`data/accounting.db`。

五类（任务书要求）：
  ① `RbacUnitTests`             单元测试：权限判断（角色矩阵 / 未知一律拒绝 / 超管全权）
  ② `AccessIntegrationTests`    集成测试：登录 → 权限 → 数据（全流程走 HTTP）
  ③ `TenantIsolationTests`      租户隔离测试
  ④ `AuditCompletenessTests`    审计日志完整性测试（含越权留痕）
  ⑤ `RedactionTests`            脱敏测试（+ 下载水印机制）

★ 每类都含**反向判据**（不只是"正例通过"）：
  · 权限：有权限 200 **且** 无权限必须 403（不是"静默放行"）；
  · 隔离：跨租户 404 **且** 同租户 200（证明 404 是隔离而非"全都 404"）；
  · 脱敏：脱敏角色被遮盖 **且** 内部角色不遮盖（证明不是"一律遮盖"，数据未被破坏）；
  · 审计：关键动作在库 **且** 越权尝试也在库（"没做成的"同样要留痕）。
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

ADMIN_USER = "rbacadmin"
ADMIN_PASS = "Rbac-Admin-2026!"

_PREAMBLE = """
import base64, os, sys
from pathlib import Path
ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
"""


def _run(script: str, *, timeout: int = 300) -> subprocess.CompletedProcess:
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


def _assert_ok(result: subprocess.CompletedProcess) -> None:
    if result.returncode != 0:
        raise AssertionError(
            "子进程失败（returncode=%s）\n--- stdout ---\n%s\n--- stderr ---\n%s"
            % (result.returncode, result.stdout, result.stderr))


# --------------------------------------------------------------------------
# ① 单元测试：权限判断
# --------------------------------------------------------------------------
_UNIT = _PREAMBLE + """
from security import init_security_db, create_user, SessionContext
from engine import rbac as R
init_security_db(); R.ensure_rbac_schema()

def sess(uid, legacy="user"):
    return SessionContext(user_id=uid, username="u%d" % uid, role=legacy,
                          allowed_company_ids=frozenset(), selected_company_id=None,
                          csrf_hash="", expires_at=0)

# 任务书五个角色必须齐备
for code in ("enterprise_finance", "tax_advisor", "review_expert",
             "system_admin", "auditor"):
    assert code in R.role_codes(), code

perms = R.permission_codes()
assert len(perms) >= 10, perms

# 超管（users.role='admin'）⇒ 全部权限
admin = sess(1, legacy="admin")
assert set(R.session_permission_codes(admin)) == set(perms), "超管权限不完整"

# 企业财务：可建项目/传资料/发起分析，但**不可**管理用户与角色
fin = create_user("unitfin", "Unit-Fin-2026!", role="user")
R.assign_user_roles(fin, ["enterprise_finance"])
f = sess(fin)
assert R.rbac_allows(f, "project.write") is True
assert R.rbac_allows(f, "analysis.run") is True
assert R.rbac_allows(f, "user.manage") is False, "企业财务竟有 user.manage"
assert R.rbac_allows(f, "role.manage") is False
assert R.rbac_allows(f, "audit.view") is False

# 审计员：只读 + 看留痕；一切写权限都没有
aud = create_user("unitaud", "Unit-Aud-2026!", role="user")
R.assign_user_roles(aud, ["auditor"])
a = sess(aud)
assert R.rbac_allows(a, "audit.view") is True
assert R.rbac_allows(a, "user.view") is True
for write in ("project.write", "document.write", "analysis.run",
              "risk.review", "report.generate", "user.manage", "role.manage"):
    assert R.rbac_allows(a, write) is False, ("审计员竟有 %s" % write)

# 复核专家：可复核风险，但**不可**发起分析、不可导出报告
rev = create_user("unitrev", "Unit-Rev-2026!", role="user")
R.assign_user_roles(rev, ["review_expert"])
v = sess(rev)
assert R.rbac_allows(v, "risk.review") is True
assert R.rbac_allows(v, "analysis.run") is False
assert R.rbac_allows(v, "report.generate") is False

# 税务师：可复核 + 可导出
adv = create_user("unitadv", "Unit-Adv-2026!", role="user")
R.assign_user_roles(adv, ["tax_advisor"])
d = sess(adv)
assert R.rbac_allows(d, "risk.review") is True
assert R.rbac_allows(d, "report.generate") is True
assert R.rbac_allows(d, "user.manage") is False

# ---- 反向判据：未知/空一律拒绝，绝不"默认放行" ----
assert R.rbac_allows(f, "not.a.real.permission") is False
assert R.rbac_allows(f, "") is False
assert R.rbac_allows(None, "project.view") is False
assert R.session_permission_codes(None) == frozenset()

# 未指派角色 ⇒ 回落到 default_role（既不是"无权限"也不是"全权限"）
plain = create_user("unitplain", "Unit-Plain-2026!", role="user")
p = sess(plain)
assert R.session_role_codes(p) == frozenset({R.rbac_config()["default_role"]}), \\
    R.session_role_codes(p)
assert R.rbac_allows(p, "project.view") is True, "默认角色应可查看项目"
assert R.rbac_allows(p, "user.manage") is False, "默认角色不应有 user.manage"

# 非法角色不可指派（不静默接受）
try:
    R.assign_user_roles(plain, ["no_such_role"])
    raise AssertionError("非法角色竟被接受")
except AssertionError:
    raise
except Exception as e:
    assert e.__class__.__name__ == "RbacError", e.__class__.__name__

# 不存在的用户（无 user_roles）⇒ 默认角色；绝不能有管理类权限
assert R.rbac_allows(sess(99999), "user.manage") is False, "未知用户竟有 user.manage"
assert R.rbac_allows(sess(99999), "audit.view") is False, "未知用户竟有 audit.view"
print("UNIT-OK")
"""

_REDACT_MAP = _PREAMBLE + """
from engine import rbac as R
from engine.report_compliance import load_config
allowed = set((load_config().get("redaction_roles") or {}).keys())
cfg = R.rbac_config()
bad = {k: v for k, v in (cfg.get("role_redaction") or {}).items() if v not in allowed}
assert not bad, bad
assert cfg.get("fallback_redaction") in allowed, cfg.get("fallback_redaction")
# 反向：未知角色 ⇒ 取 fallback（最严），而不是"不脱敏"
assert R.redaction_role_of_code("__nope__") == cfg["fallback_redaction"]
print("REDACT-MAP-OK", sorted(allowed))
"""


class RbacUnitTests(unittest.TestCase):
    """直接调 `engine.rbac`（不经过 HTTP），验证角色→权限矩阵与拒绝语义。"""

    def test_permission_matrix_and_deny_semantics(self):
        result = _run(_UNIT)
        _assert_ok(result)
        self.assertIn("UNIT-OK", result.stdout)

    def test_role_redaction_maps_to_existing_authority(self):
        """角色→脱敏 的取值必须落在 `report_compliance.redaction_roles` 键集合内。"""
        result = _run(_REDACT_MAP)
        _assert_ok(result)
        self.assertIn("REDACT-MAP-OK", result.stdout)


# --------------------------------------------------------------------------
# ② 集成测试：登录 → 权限 → 数据
# --------------------------------------------------------------------------
_INTEGRATION = _PREAMBLE + """
import base64, os, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from fastapi.testclient import TestClient
import main
from security import init_security_db, create_user
from engine import rbac as R

init_security_db(); R.ensure_rbac_schema()
TENANT = R.default_tenant_id()

fin = create_user("fin01", "Finance-Pass-2026!", role="user", tenant_id=TENANT)
R.assign_user_roles(fin, ["enterprise_finance"])

c = TestClient(main.app)

def csrf():
    t = c.cookies.get("csrf_token")
    return {"X-CSRF-Token": t} if t else {}

fails = []
def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

r = c.post("/api/v1/auth/login", json={"username": "rbacadmin", "password": "Rbac-Admin-2026!"})
ok(r.status_code == 200, "登录 200（公开路径可达）：%s" % r.status_code)
ok(bool(c.cookies.get("csrf_token")), "下发 CSRF cookie")
me = c.get("/api/auth/me").json()
ok("user.manage" in (me["permissions"] or []), "me 返回权限集合")
ok("system_admin" in (me["roles"] or []), "me 返回角色集合")

r = c.get("/api/v1/users")
ok(r.status_code == 200, "GET /api/v1/users 200")
ok(r.json()["total"] >= 2, "用户列表非空：%s" % r.json()["total"])

r = c.post("/api/v1/users", headers=csrf(), json={
    "username": "newbie", "password": "Newbie-Pass-2026!", "roles": ["tax_advisor"]})
ok(r.status_code == 201, "POST /api/v1/users 201：%s %s" % (r.status_code, r.text[:120]))
new_id = (r.json().get("id") if r.status_code == 201 else None)

r = c.put("/api/v1/users/%s" % new_id, headers=csrf(), json={"active": False})
ok(r.status_code == 200 and r.json()["active"] is False, "PUT 停用生效")

r = c.get("/api/v1/roles")
ok(r.status_code == 200, "GET /api/v1/roles 200")
ok(len(r.json()["permissions"]) == 18,
   "权限点 18（P1-5/6 各 +1；P2 +3）：%s" % len(r.json()["permissions"]))

r = c.get("/api/v1/audit-logs")
ok(r.status_code == 200, "GET /api/v1/audit-logs 200")

# ---- 反向：无 CSRF 的写请求必须被拒 ----
r = c.post("/api/v1/users", json={"username": "no_csrf", "password": "Xx-1234567890!"})
ok(r.status_code == 403, "无 CSRF 的 POST ⇒ 403：%s" % r.status_code)

# ---- 反向：无权限角色必须 403（不是静默放行）----
c.cookies.clear()
r = c.post("/api/v1/auth/login", json={"username": "fin01", "password": "Finance-Pass-2026!"})
ok(r.status_code == 200, "企业财务登录 200")
ok(c.get("/api/v1/users").status_code == 403, "企业财务 GET /api/v1/users ⇒ 403")
ok(c.get("/api/v1/roles").status_code == 403, "企业财务 GET /api/v1/roles ⇒ 403")
ok(c.get("/api/v1/audit-logs").status_code == 403, "企业财务 GET /api/v1/audit-logs ⇒ 403")
ok(c.post("/api/v1/users", headers=csrf(),
          json={"username": "z", "password": "Zz-1234567890!"}).status_code == 403,
   "企业财务 POST /api/v1/users ⇒ 403")
# 但有权限的只读接口必须放行（证明 403 不是"全都 403"）
ok(c.get("/api/auth/me").status_code == 200, "企业财务 GET /api/auth/me ⇒ 200")

# ---- 反向：错误口令 401 / 未登录 401 ----
c.cookies.clear()
ok(c.post("/api/v1/auth/login", json={"username": "fin01", "password": "bad"}).status_code == 401,
   "错误口令 ⇒ 401")
ok(c.get("/api/v1/users").status_code == 401, "未登录 ⇒ 401")

print("INTEGRATION-FAILS=%d" % len(fails))
assert not fails, fails
print("INTEGRATION-OK")
"""


class AccessIntegrationTests(unittest.TestCase):
    def test_login_permission_data_flow(self):
        result = _run(_INTEGRATION)
        _assert_ok(result)
        self.assertIn("INTEGRATION-OK", result.stdout)
        self.assertIn("INTEGRATION-FAILS=0", result.stdout)


# --------------------------------------------------------------------------
# ③ 租户隔离测试
# --------------------------------------------------------------------------
_TENANT = _PREAMBLE + """
import base64, os, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from fastapi.testclient import TestClient
import main
from security import init_security_db, create_user
from engine import rbac as R

init_security_db(); R.ensure_rbac_schema()
TA = R.default_tenant_id()
TB = R.create_tenant("org-b", "B 组织", "saas")

u_a = create_user("tenantA", "Tenant-A-2026!", role="user", tenant_id=TA)
R.assign_user_roles(u_a, ["auditor"])
u_b = create_user("tenantB", "Tenant-B-2026!", role="user", tenant_id=TB)
R.assign_user_roles(u_b, ["enterprise_finance"])
aud_b = create_user("auditB", "Tenant-B-2026!", role="user", tenant_id=TB)
R.assign_user_roles(aud_b, ["auditor"])

c = TestClient(main.app)
def login(u, p):
    return c.post("/api/v1/auth/login", json={"username": u, "password": p})

fails = []
def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

# 超管跨组织可见（对照组：证明数据确实存在，隔离不是"查不到"）
login("rbacadmin", "Rbac-Admin-2026!")
r = c.get("/api/v1/users")
ok(r.status_code == 200, "超管 GET /api/v1/users 200")
names = {u["username"] for u in r.json()["items"]}
ok({"tenantA", "tenantB"} <= names, "超管可见两个组织的用户：%s" % sorted(names))

# 组织 A 的审计员：只看得到 A 的用户
c.cookies.clear(); login("tenantA", "Tenant-A-2026!")
r = c.get("/api/v1/users")
ok(r.status_code == 200, "A 组织审计员 GET /api/v1/users 200")
names_a = {u["username"] for u in r.json()["items"]}
ok("tenantB" not in names_a, "A 组织看不到 B 组织用户：%s" % sorted(names_a))
ok("tenantA" in names_a, "A 组织看得到本组织用户")

# 跨组织用户详情 ⇒ 404（不泄露存在性）
ok(c.get("/api/v1/users/%d" % u_b).status_code == 404, "跨组织用户详情 ⇒ 404")
ok(c.get("/api/v1/users/%d" % u_a).status_code == 200, "同组织用户详情 ⇒ 200")

# 指定其他组织 tenant_id ⇒ 403（显式越界）
ok(c.get("/api/v1/users", params={"tenant_id": TB}).status_code == 403,
   "显式指定其他组织 tenant_id ⇒ 403")

# 留痕隔离：A 组织审计员看不到 B 组织成员的留痕
c.cookies.clear(); login("auditB", "Tenant-B-2026!")
r = c.get("/api/v1/audit-logs", params={"page_size": 200})
ok(r.status_code == 200, "B 组织审计员 GET /api/v1/audit-logs 200")
seen = {x["user_name"] for x in r.json()["items"]}
ok("tenantA" not in seen, "B 组织看不到 A 组织成员的留痕：%s" % sorted(seen))
ok(r.json()["total"] >= 0, "留痕计数可用：%s" % r.json()["total"])

# 反向：过滤"不在本组织"的 user_id ⇒ 空结果（而不是 500 或全量）
r = c.get("/api/v1/audit-logs", params={"user_id": u_a})
ok(r.status_code == 200 and r.json()["total"] == 0, "按跨组织 user_id 过滤 ⇒ 空结果")

print("TENANT-FAILS=%d" % len(fails))
assert not fails, fails
print("TENANT-OK")
"""


class TenantIsolationTests(unittest.TestCase):
    def test_tenant_scope(self):
        result = _run(_TENANT)
        _assert_ok(result)
        self.assertIn("TENANT-OK", result.stdout)


# --------------------------------------------------------------------------
# ④ 审计日志完整性测试
# --------------------------------------------------------------------------
_AUDIT = _PREAMBLE + """
import base64, os, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from fastapi.testclient import TestClient
import main
from security import init_security_db, create_user
from engine import rbac as R
from engine import audit_trail as AT

init_security_db(); R.ensure_rbac_schema()
fin = create_user("auditfin", "Audit-Fin-2026!", role="user",
                  tenant_id=R.default_tenant_id())
R.assign_user_roles(fin, ["enterprise_finance"])

c = TestClient(main.app)
def csrf():
    t = c.cookies.get("csrf_token")
    return {"X-CSRF-Token": t} if t else {}
def login(u, p):
    return c.post("/api/v1/auth/login", json={"username": u, "password": p})

fails = []
def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

def cnt(action):
    return AT.count(action=action)

# 登录成功 / 失败 / 登出
login("rbacadmin", "Rbac-Admin-2026!")
ok(cnt("auth.login") >= 1, "登录成功留痕：%s" % cnt("auth.login"))
c.cookies.clear()
login("rbacadmin", "wrong-pass")
ok(cnt("auth.login_failed") >= 1, "登录失败留痕：%s" % cnt("auth.login_failed"))
login("rbacadmin", "Rbac-Admin-2026!")
r = c.post("/api/auth/logout", headers=csrf())
ok(r.status_code == 200, "登出 200")
ok(cnt("auth.logout") >= 1, "登出留痕：%s" % cnt("auth.logout"))

# 越权留痕（CSRF 失败 + 无权限）
login("rbacadmin", "Rbac-Admin-2026!")
denied_before = cnt("auth.denied")
c.post("/api/v1/users", json={"username": "x", "password": "Xx-1234567890!"})   # 无 CSRF
ok(cnt("auth.denied") > denied_before, "CSRF 失败 ⇒ auth.denied 留痕")

# 用户创建 / 修改 / 角色创建
r = c.post("/api/v1/users", headers=csrf(), json={
    "username": "auditnew", "password": "Audit-New-2026!", "roles": ["auditor"],
    "phone": "13800002222"})
ok(r.status_code == 201, "新建用户 201")
uid = r.json()["id"]
ok(cnt("user.create") >= 1, "用户创建留痕：%s" % cnt("user.create"))
r = c.put("/api/v1/users/%d" % uid, headers=csrf(), json={"display_name": "李四"})
ok(r.status_code == 200, "修改用户 200")
ok(cnt("user.update") >= 1, "用户修改留痕：%s" % cnt("user.update"))
r = c.post("/api/v1/roles", headers=csrf(), json={
    "code": "audit_probe_role", "name": "留痕探针角色", "permissions": ["project.view"]})
ok(r.status_code == 201, "新建角色 201")
ok(cnt("role.create") >= 1, "角色创建留痕：%s" % cnt("role.create"))

# 任务书要求的七类业务动作 —— 动作词表必须已登记（中文名可读）
from engine.audit_trail import ACTIONS, ACTION_CN
for a in ("doc.upload", "analysis.start", "doc.delete", "doc.download",
          "report.export", "report.download", "finding.review", "risk.review",
          "project.update", "job.finished"):
    ok(a in ACTIONS, "动作已登记：%s" % a)
    ok(a in ACTION_CN and ACTION_CN[a] and not ACTION_CN[a].isascii(),
       "动作有中文名：%s → %s" % (a, ACTION_CN.get(a)))
for a in ("auth.login", "auth.login_failed", "auth.logout", "auth.denied",
          "user.create", "user.update", "role.create"):
    ok(a in ACTIONS and a in ACTION_CN, "P0-8 新动作已登记且有中文名：%s" % a)

# 留痕可检索（按动作/按人/按关键字）
r = c.get("/api/v1/audit-logs", params={"action": "user.create", "page_size": 50})
ok(r.status_code == 200 and r.json()["total"] >= 1, "按动作检索可用")
ok(all(x["action"] == "user.create" for x in r.json()["items"]), "动作过滤无越界行")
r = c.get("/api/v1/audit-logs", params={"q": "auditnew", "page_size": 50})
ok(r.json()["total"] >= 1, "按关键字检索可用：%s" % r.json()["total"])

# 反向：未登记动作照样记录（不静默丢弃）——由 audit_trail 保证，此处锁行为
AT.record("not.a.registered.action", target="probe", company_id=None)
ok(cnt("not.a.registered.action") == 1, "未登记动作照记原值")
row = AT.list_records(action="not.a.registered.action")[0]
ok(row["company_id"] is None, "无归属不得用 0 冒充（存 NULL）")

print("AUDIT-FAILS=%d" % len(fails))
assert not fails, fails
print("AUDIT-OK")
"""


class AuditCompletenessTests(unittest.TestCase):
    def test_all_actions_recorded(self):
        result = _run(_AUDIT)
        _assert_ok(result)
        self.assertIn("AUDIT-OK", result.stdout)


# --------------------------------------------------------------------------
# ⑤ 脱敏测试（+ 水印机制）
# --------------------------------------------------------------------------
_REDACT = _PREAMBLE + """
import base64, os, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from fastapi.testclient import TestClient
import main
from security import init_security_db, create_user
from engine import rbac as R

init_security_db(); R.ensure_rbac_schema()
T = R.default_tenant_id()
target = create_user("redact_target", "Redact-Pass-2026!", role="user", tenant_id=T,
                     display_name="张会计", phone="13812345678",
                     id_card="110101199001011234", bank_account="6222020200112233")
R.assign_user_roles(target, ["enterprise_finance"])
aud = create_user("redact_auditor", "Redact-Pass-2026!", role="user", tenant_id=T)
R.assign_user_roles(aud, ["auditor"])

c = TestClient(main.app)
def login(u, p):
    return c.post("/api/v1/auth/login", json={"username": u, "password": p})
fails = []
def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)

def row_for(username):
    r = c.get("/api/v1/users", params={"q": username})
    items = [u for u in r.json()["items"] if u["username"] == username]
    assert items, ("未找到用户", username, r.text[:200])
    return items[0]

# 内部角色（超管 ⇒ internal 策略）：**不脱敏**，原文可见（数据未被破坏）
login("rbacadmin", "Rbac-Admin-2026!")
admin_row = row_for("redact_target")
ok(admin_row["phone"] == "13812345678", "internal 不脱敏手机号：%r" % admin_row["phone"])
ok(admin_row["id_card"] == "110101199001011234", "internal 不脱敏身份证号")
ok(admin_row["bank_account"] == "6222020200112233", "internal 不脱敏银行账号")
ok(admin_row["display_name"] == "张会计", "internal 不脱敏姓名")
ok("****" not in admin_row["phone"], "internal 输出不含遮盖痕迹")

# 脱敏角色（审计员 ⇒ auditor 策略）：身份证/银行账号/手机号/姓名**全部**遮盖
c.cookies.clear(); login("redact_auditor", "Redact-Pass-2026!")
aud_row = row_for("redact_target")
ok(aud_row["phone"] == "138****5678", "手机号遮盖：%r" % aud_row["phone"])
ok(aud_row["id_card"] == "110***********1234", "身份证号遮盖：%r" % aud_row["id_card"])
ok(aud_row["bank_account"] == "6222****33", "银行账号遮盖：%r" % aud_row["bank_account"])
ok(aud_row["display_name"] != "张会计" and aud_row["display_name"].endswith("某"),
   "姓名遮盖为『姓氏+某』：%r" % aud_row["display_name"])
ok(aud_row["phone"] != admin_row["phone"], "脱敏确实改变了输出（非空转）")

# 留痕文本同样脱敏
c.cookies.clear(); login("rbacadmin", "Rbac-Admin-2026!")
c.post("/api/v1/users", headers={"X-CSRF-Token": c.cookies.get("csrf_token", "")}, json={
    "username": "leaky", "password": "Leaky-Pass-2026!", "roles": ["auditor"],
    "phone": "13711112222"})
c.cookies.clear(); login("redact_auditor", "Redact-Pass-2026!")
r = c.get("/api/v1/audit-logs", params={"q": "leaky", "page_size": 50})
blob = " ".join((x.get("detail") or "") + " " + (x.get("target") or "")
                for x in r.json()["items"])
ok("13711112222" not in blob, "留痕文本中不得出现明文手机号：%r" % blob[:200])

# ---- 水印：机制层真嵌入（PDF 真嵌入；不可嵌入格式必须如实声明而非静默）----
#   ★ 用 reportlab 造**真实** PDF：手写的最小 PDF 桩会让 `_pdf_watermark` 抛错并
#     退回 sidecar —— 那样断言"字节数增加"会假红，也会掩盖真实行为。
import io
from reportlab.pdfgen import canvas
from engine.document_watermark import apply_watermark, is_embeddable

_buf = io.BytesIO()
_pdf = canvas.Canvas(_buf)
_pdf.drawString(72, 720, "hello")
_pdf.save()
pdf_bytes = _buf.getvalue()

out, mode, msg = apply_watermark("report.pdf", pdf_bytes, "内部使用 · 未经人工复核")
ok(is_embeddable("report.pdf") is True, "PDF 属可嵌入格式")
ok(mode == "embedded", "PDF 水印走嵌入模式（mode=%s, msg=%s）" % (mode, msg))
ok(out != pdf_bytes and len(out) > len(pdf_bytes), "PDF 水印已真嵌入（字节数增加）")

# ---- 反向：不可嵌入格式必须走 sidecar 且**明确声明**（不得假装已加水印）----
out2, mode2, msg2 = apply_watermark("data.xlsx", b"PK\\x03\\x04stub", "内部使用")
ok(mode2 == "sidecar" and out2 == b"PK\\x03\\x04stub", "不可嵌入格式返回原内容")
ok("内部使用" in msg2, "sidecar 必须把水印信息随附声明：%r" % msg2)

# ---- 反向：空水印文字不得被当成"已加水印" ----
out3, mode3, msg3 = apply_watermark("report.pdf", pdf_bytes, "")
ok(mode3 == "sidecar", "空水印文字 ⇒ sidecar（不假装）")

# ---- 报告水印文字必须含复核标识（任务书要求；"未复核"也要显式写出）----
from engine.report_render import watermark_text_of
t1 = watermark_text_of({"name": "标准税务风险分析报告", "doc_no": "WB-TR-01",
                        "version": "V1.0", "reviewed": False, "generated_by": "张三",
                        "generated_at": "2026-10-14 10:00"})
ok("未经人工复核" in t1, "未复核报告的水印必须显式标注『未经人工复核』：%r" % t1)
t2 = watermark_text_of({"name": "标准税务风险分析报告", "doc_no": "WB-TR-01",
                        "version": "V1.0", "reviewed": True, "reviewed_by": "李四",
                        "generated_by": "张三", "generated_at": "2026-10-14 10:00"})
ok("已复核" in t2 and "李四" in t2, "已复核报告的水印含复核人与状态：%r" % t2)

print("REDACT-FAILS=%d" % len(fails))
assert not fails, fails
print("REDACT-OK")
"""


class RedactionTests(unittest.TestCase):
    def test_masking_by_role(self):
        result = _run(_REDACT)
        _assert_ok(result)
        self.assertIn("REDACT-OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
