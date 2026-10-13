# -*- coding: utf-8 -*-
"""P0-8 冒烟（隔离 APP_DATA_DIR，真跑 HTTP 链路）。"""
from __future__ import annotations

import base64
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

TMP = tempfile.mkdtemp(prefix="p08-smoke-")
os.environ.update({
    "APP_DATA_DIR": TMP,
    "APP_COOKIE_SECURE": "0",
    "APP_ALLOWED_ORIGINS": "http://testserver",
    "APP_ADMIN_USERNAME": "smokeadmin",
    "APP_ADMIN_PASSWORD": "Smoke-Admin-2026!",
    "APP_LLM_MASTER_KEY": base64.urlsafe_b64encode(bytes(range(32))).decode("ascii"),
})

from fastapi.testclient import TestClient          # noqa: E402
import main                                        # noqa: E402
from security import init_security_db, create_user  # noqa: E402
from engine import rbac as R                       # noqa: E402

init_security_db()
R.ensure_rbac_schema()
DEFAULT_TENANT = R.default_tenant_id()

# 建三个用户：企业财务（同租户）、审计员（同租户）、另一租户的企业财务
fin = create_user("fin01", "Finance-Pass-2026!", role="user",
                  display_name="张会计", phone="13812345678",
                  id_card="110101199001011234", bank_account="6222020200112233",
                  tenant_id=DEFAULT_TENANT)
R.assign_user_roles(fin, ["enterprise_finance"])
aud = create_user("aud01", "Auditor-Pass-2026!", role="user",
                  display_name="李审计", phone="13987654321", tenant_id=DEFAULT_TENANT)
R.assign_user_roles(aud, ["auditor"])
other_tid = R.create_tenant("org-b", "B 组织", "saas")
other = create_user("fin02", "Finance-Pass-2026!", role="user",
                    display_name="王财务", phone="13700000000", tenant_id=other_tid)
R.assign_user_roles(other, ["enterprise_finance"])

client = TestClient(main.app)
failures = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


def login(username, password):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    return r


def csrf_headers():
    """写请求必须带 CSRF 头（浏览器由 /static/js/security.js 自动附加）。"""
    t = client.cookies.get("csrf_token")
    return {"X-CSRF-Token": t} if t else {}


# 1) 公开路径 + 登录
r = login("smokeadmin", "Smoke-Admin-2026!")
ok(r.status_code == 200, "POST /api/v1/auth/login 管理员 200（公开路径未被拦截）: %s" % r.status_code)
ok("auth_token" in r.cookies or "auth_token" in client.cookies,
   "登录下发 auth_token Cookie")
csrf = client.cookies.get("csrf_token")
ok(bool(csrf), "登录下发 csrf_token Cookie")
admin_at = client.cookies.get("auth_token")

# 2) me 带权限
me = client.get("/api/auth/me").json()
ok("user.manage" in (me.get("permissions") or []), "/api/auth/me 返回权限集合（含 user.manage）")

# 3) 用户列表（管理员：跨组织可见）
r = client.get("/api/v1/users")
ok(r.status_code == 200, "GET /api/v1/users 管理员 200: %s" % r.status_code)
body = r.json()
names = {u["username"] for u in body["items"]}
ok({"smokeadmin", "fin01", "aud01", "fin02"} <= names,
   "管理员可见全部组织的用户（含跨组织 org-b 的 fin02）")
masked = [u for u in body["items"] if u["username"] == "aud01"][0]
ok(masked["phone"] == "13987654321", "internal 策略（system_admin）不脱敏手机号: %r" % masked["phone"])

# 4) 新建用户（管理员）
perm_view_before = client.get("/api/v1/users").json()["total"]
r = client.post("/api/v1/users", headers=csrf_headers(), json={
    "username": "newuser01", "password": "New-User-Pass-2026!",
    "display_name": "新同事", "roles": ["tax_advisor"],
    "phone": "13600001111", "id_card": "310101199203031234",
    "bank_account": "6217000010001234567",
})
ok(r.status_code == 201, "POST /api/v1/users 管理员 201: %s %s" % (r.status_code, r.text[:160]))
ok(client.get("/api/v1/users").json()["total"] == perm_view_before + 1, "新建后总数 +1")

# 5) 角色字典 + 新建自定义角色
r = client.get("/api/v1/roles")
ok(r.status_code == 200, "GET /api/v1/roles 200")
roles_body = r.json()
ok(len(roles_body["roles"]) >= 5, "内置角色 ≥5（实测 %d）" % len(roles_body["roles"]))
ok(len(roles_body["permissions"]) == 13, "权限点 13（实测 %d）" % len(roles_body["permissions"]))
r = client.post("/api/v1/roles", headers=csrf_headers(), json={
    "code": "data_reviewer", "name": "数据复核岗",
    "permissions": ["project.view", "risk.view"], "scope": "tenant"})
ok(r.status_code == 201, "POST /api/v1/roles 201: %s %s" % (r.status_code, r.text[:160]))
r = client.post("/api/v1/roles", headers=csrf_headers(), json={
    "code": "system_admin", "name": "想覆盖内置", "permissions": ["project.view"]})
ok(r.status_code == 400, "重建内置角色被拒 400: %s" % r.status_code)

# 6) 审计日志（管理员，看得到登录留痕）
r = client.get("/api/v1/audit-logs", params={"action": "auth.login"})
ok(r.status_code == 200, "GET /api/v1/audit-logs 200")
ok(r.json()["total"] >= 1, "登录留痕已入库（total=%s）" % r.json()["total"])
r = client.get("/api/v1/audit-logs", params={"action": "user.create"})
ok(r.json()["total"] >= 1, "新建用户留痕已入库（total=%s）" % r.json()["total"])
r = client.get("/api/v1/audit-logs", params={"action": "role.create"})
ok(r.json()["total"] >= 1, "新建角色留痕已入库（total=%s）" % r.json()["total"])

# 7) 企业财务登录：无 user.view / user.manage
client.cookies.clear()
r = login("fin01", "Finance-Pass-2026!")
ok(r.status_code == 200, "企业财务登录 200")
fin_me = client.get("/api/auth/me").json()
ok("user.manage" not in (fin_me.get("permissions") or []),
   "企业财务无 user.manage 权限")
ok("audit.view" not in (fin_me.get("permissions") or []), "企业财务无 audit.view 权限")
r = client.get("/api/v1/users")
ok(r.status_code == 403, "企业财务 GET /api/v1/users ⇒ 403: %s" % r.status_code)
r = client.get("/api/v1/roles")
ok(r.status_code == 403, "企业财务 GET /api/v1/roles ⇒ 403: %s" % r.status_code)
r = client.get("/api/v1/audit-logs")
ok(r.status_code == 403, "企业财务 GET /api/v1/audit-logs ⇒ 403: %s" % r.status_code)
r = client.post("/api/v1/users", headers=csrf_headers(), json={"username": "x", "password": "Abc-123456789!"})
ok(r.status_code == 403, "企业财务 POST /api/v1/users ⇒ 403: %s" % r.status_code)

# 8) 审计员：user.view + audit.view，但无 user.manage
client.cookies.clear()
r = login("aud01", "Auditor-Pass-2026!")
ok(r.status_code == 200, "审计员登录 200")
r = client.get("/api/v1/users")
ok(r.status_code == 200, "审计员 GET /api/v1/users 200（有 user.view）")
aud_body = r.json()
ok(aud_body["redaction_role"] == "auditor", "审计员脱敏策略=auditor（实测 %s）" % aud_body["redaction_role"])
fin_row = [u for u in aud_body["items"] if u["username"] == "fin01"][0]
ok(fin_row["phone"] != "13812345678" and "****" in fin_row["phone"],
   "审计员看手机号被脱敏: %r" % fin_row["phone"])
ok("****" in fin_row["id_card"], "审计员看身份证号被脱敏: %r" % fin_row["id_card"])
ok("****" in fin_row["bank_account"], "审计员看银行账号被脱敏: %r" % fin_row["bank_account"])
ok(fin_row["display_name"] != "张会计", "审计员看姓名被脱敏: %r" % fin_row["display_name"])
r = client.post("/api/v1/users", headers=csrf_headers(), json={"username": "y", "password": "Abc-123456789!"})
ok(r.status_code == 403, "审计员 POST /api/v1/users ⇒ 403: %s" % r.status_code)
r = client.get("/api/v1/audit-logs")
ok(r.status_code == 200, "审计员 GET /api/v1/audit-logs 200")
seen = {x["user_name"] for x in r.json()["items"]}
ok("fin02" not in seen, "审计员看不到其他组织（org-b）用户的留痕")
ok(r.json()["redaction_role"] == "auditor", "审计日志按 auditor 策略输出")

# 9) 另一组织的企业财务：看不到本组织用户
client.cookies.clear()
r = login("fin02", "Finance-Pass-2026!")
ok(r.status_code == 200, "org-b 企业财务登录 200")
ok(client.get("/api/v1/users").status_code == 403, "org-b 企业财务仍无 user.view ⇒ 403")

# 10) 跨租户用户详情（审计员访问 org-b 用户 ⇒ 404 不泄露）
client.cookies.clear()
login("aud01", "Auditor-Pass-2026!")
r = client.get("/api/v1/users/%d" % other)
ok(r.status_code == 404, "审计员访问其他组织用户 ⇒ 404（不泄露存在性）: %s" % r.status_code)
r = client.get("/api/v1/users/%d" % fin)
ok(r.status_code == 200, "审计员访问同组织用户 ⇒ 200")

# 11) 登录失败留痕 + 未登录 401
client.cookies.clear()
r = login("fin01", "wrong-password")
ok(r.status_code == 401, "错误口令 401")
r = client.get("/api/v1/users")
ok(r.status_code == 401, "未登录 GET /api/v1/users ⇒ 401: %s" % r.status_code)

client.cookies.clear()
login("smokeadmin", "Smoke-Admin-2026!")
r = client.get("/api/v1/audit-logs", params={"action": "auth.login_failed"})
ok(r.json()["total"] >= 1, "登录失败留痕已入库（total=%s）" % r.json()["total"])

# 12) 页面路由可达
client.cookies.clear()
login("smokeadmin", "Smoke-Admin-2026!")
for p in ("/users", "/roles", "/audit-logs"):
    rr = client.get(p)
    ok(rr.status_code == 200 and "text/html" in rr.headers.get("content-type", ""),
       "页面 %s 可达: %s" % (p, rr.status_code))

print("\n== 冒烟结论：%d 项失败 ==" % len(failures))
for f in failures:
    print("  - " + f)
sys.exit(1 if failures else 0)
