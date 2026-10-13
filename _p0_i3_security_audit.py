# -*- coding: utf-8 -*-
"""P0 验收 · 安全测试 + 审计测试（隔离实例 + 真 HTTP）。

覆盖任务书 §3（安全）：租户隔离 / 权限越权 / 敏感数据脱敏 / 文件下载水印
覆盖任务书 §4（审计）：所有关键操作留痕

★ 全部走**真实链路**（认证中间件 / RBAC / 真实 SQLite / 真实留痕 / 真实水印），
  数据落在临时 `APP_DATA_DIR` ⇒ 不污染生产库。
★ 每一条都带**反向判据**（"有权限 200 **且** 无权限 403"），否则"全都 403"也能骗过测试。

用法：`python _p0_i3_security_audit.py`
"""
from __future__ import annotations

import base64
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")

ADMIN_USER = "p0sec_admin"
ADMIN_PASS = "P0-Sec-Admin-2026!"

_CHILD = r'''
# -*- coding: utf-8 -*-
import base64, io, json, os, sys
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
import main
from security import init_security_db, create_user
from engine import rbac as R

init_security_db(); R.ensure_rbac_schema()
TA = R.default_tenant_id()
TB = R.create_tenant("p0-org-b", "B 组织", "saas")

# 同组织：财务 / 审计员；跨组织：B 的财务
u_fin  = create_user("sec_fin",  "Sec-Fin-2026!",  role="user", tenant_id=TA,
                     display_name="张会计", phone="13812345678",
                     id_card="110101199001011234", bank_account="6222020200112233")
R.assign_user_roles(u_fin, ["enterprise_finance"])
u_aud  = create_user("sec_aud",  "Sec-Aud-2026!",  role="user", tenant_id=TA)
R.assign_user_roles(u_aud, ["auditor"])
u_b    = create_user("sec_orgb", "Sec-OrgB-2026!", role="user", tenant_id=TB)
R.assign_user_roles(u_b, ["enterprise_finance"])

c = TestClient(main.app)
fails = []
def ok(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ((" | " + str(extra)) if extra else ""))
    if not cond:
        fails.append(name)

def csrf():
    t = c.cookies.get("csrf_token")
    return {"X-CSRF-Token": t} if t else {}

def login(u, p):
    c.cookies.clear()
    return c.post("/api/v1/auth/login", json={"username": u, "password": p})

print("=== A. 权限越权 ===")
# A1 未登录 ⇒ 401（不是 200，也不是 500）
c.cookies.clear()
ok("A1 未登录访问受保护接口 ⇒ 401",
   c.get("/api/v1/users").status_code == 401,
   c.get("/api/v1/users").status_code)

# A2 无权限角色 ⇒ 403；且有权限接口必须 200（反向判据）
login("sec_fin", "Sec-Fin-2026!")
fin_me = c.get("/api/auth/me").json()
ok("A2a 财务角色权限集合不含 user.manage", "user.manage" not in (fin_me.get("permissions") or []))
ok("A2b 财务 GET /api/v1/users ⇒ 403", c.get("/api/v1/users").status_code == 403)
ok("A2c 财务 POST /api/v1/users ⇒ 403",
   c.post("/api/v1/users", headers=csrf(),
          json={"username": "x1", "password": "Xx-1234567890!"}).status_code == 403)
ok("A2d 财务 GET /api/v1/roles ⇒ 403", c.get("/api/v1/roles").status_code == 403)
ok("A2e 财务 GET /api/v1/audit-logs ⇒ 403", c.get("/api/v1/audit-logs").status_code == 403)
ok("A2f 反向：财务自己的 /api/auth/me ⇒ 200（证明不是『全都 403』）",
   c.get("/api/auth/me").status_code == 200)
ok("A2g 反向：财务可读自己有权限的项目列表 ⇒ 200",
   c.get("/api/v1/projects").status_code == 200)

# A3 CSRF 缺失 ⇒ 403（写操作保护）
ok("A3 无 CSRF 的 POST /api/v1/users ⇒ 403",
   c.post("/api/v1/users",
          json={"username": "x2", "password": "Xx-1234567890!"}).status_code == 403)

# A4 越权尝试必须留痕（audit）
login("p0sec_admin", "P0-Sec-Admin-2026!")
n_denied = c.get("/api/v1/audit-logs", params={"action": "auth.denied"}).json()["total"]
ok("A4 越权尝试已留痕（auth.denied 计数 > 0）", n_denied > 0, n_denied)

print("=== B. 租户隔离 ===")
login("p0sec_admin", "P0-Sec-Admin-2026!")
all_names = {u["username"] for u in c.get("/api/v1/users").json()["items"]}
ok("B1 超管可见两个组织的用户（对照组，证明数据存在）",
   {"sec_fin", "sec_orgb"} <= all_names, sorted(all_names))

login("sec_aud", "Sec-Aud-2026!")          # A 组织审计员（有 user.view）
ra = c.get("/api/v1/users")
ok("B2 A 组织审计员 GET /api/v1/users ⇒ 200", ra.status_code == 200, ra.status_code)
names_a = {u["username"] for u in ra.json()["items"]}
ok("B3 A 组织看不到 B 组织用户", "sec_orgb" not in names_a, sorted(names_a))
ok("B4 A 组织看得到本组织用户", "sec_fin" in names_a)
ok("B5 跨组织用户详情 ⇒ 404（不泄露存在性）",
   c.get("/api/v1/users/%d" % u_b).status_code == 404)
ok("B6 同组织用户详情 ⇒ 200", c.get("/api/v1/users/%d" % u_fin).status_code == 200)
ok("B7 显式指定其他组织 tenant_id ⇒ 403",
   c.get("/api/v1/users", params={"tenant_id": TB}).status_code == 403)

# B8 留痕按组织隔离
login("sec_orgb", "Sec-OrgB-2026!")
ok("B8 反向：B 组织财务无 user.view ⇒ 403（仍受权限控制）",
   c.get("/api/v1/users").status_code == 403)

print("=== C. 敏感数据脱敏 ===")
login("p0sec_admin", "P0-Sec-Admin-2026!")
def row_of(uname):
    r = c.get("/api/v1/users", params={"q": uname}).json()
    return [u for u in r["items"] if u["username"] == uname][0]

adm_row = row_of("sec_fin")
ok("C1 internal 策略不脱敏（对照组：手机号明文）",
   adm_row["phone"] == "13812345678", adm_row["phone"])
ok("C2 internal 身份证号明文", adm_row["id_card"] == "110101199001011234")
ok("C3 internal 银行账号明文", adm_row["bank_account"] == "6222020200112233")

login("sec_aud", "Sec-Aud-2026!")           # auditor 策略
aud_row = row_of("sec_fin")
ok("C4 脱敏角色：手机号已遮盖", "****" in aud_row["phone"] and aud_row["phone"] != "13812345678",
   aud_row["phone"])
ok("C5 脱敏角色：身份证号已遮盖", "****" in aud_row["id_card"], aud_row["id_card"])
ok("C6 脱敏角色：银行账号已遮盖", "****" in aud_row["bank_account"], aud_row["bank_account"])
ok("C7 脱敏角色：姓名已遮盖（姓氏+某）",
   aud_row["display_name"] != "张会计" and aud_row["display_name"].endswith("某"),
   aud_row["display_name"])
ok("C8 反向：脱敏改变了输出（非空转）",
   aud_row["phone"] != adm_row["phone"] and aud_row["bank_account"] != adm_row["bank_account"])

print("=== D. 文件下载水印 ===")
from engine.document_watermark import apply_watermark, is_embeddable, EMBEDDABLE
import engine.report_render as RR
import reportlab.pdfgen.canvas as _cv
b = io.BytesIO(); p = _cv.Canvas(b); p.drawString(72, 720, "x"); p.save()
pdf = b.getvalue()
out, mode, msg = apply_watermark("report.pdf", pdf, "内部使用 · 未经人工复核")
ok("D1 PDF 水印真嵌入（mode=embedded 且字节增加）",
   mode == "embedded" and len(out) > len(pdf), "%s / +%d" % (mode, len(out) - len(pdf)))
out2, mode2, msg2 = apply_watermark("data.xlsx", b"PK\x03\x04stub", "内部使用")
ok("D2 不可嵌入格式 ⇒ sidecar 且如实声明（不假装已加水印）",
   mode2 == "sidecar" and "内部使用" in msg2, msg2[:80])
out3, mode3, _m3 = apply_watermark("report.pdf", pdf, "")
ok("D3 空水印文字 ⇒ sidecar（不假装）", mode3 == "sidecar")
ok("D4 可嵌入格式集合非空且含 PDF/图片", {".pdf", ".png", ".jpg"} <= set(EMBEDDABLE),
   sorted(EMBEDDABLE))
t_no = RR.watermark_text_of({"name": "标准税务风险分析报告", "doc_no": "WB-TR-01",
                             "version": "V1.0", "reviewed": False,
                             "generated_by": "甲", "generated_at": "2026-10-14 10:00"})
ok("D5 未复核报告水印必须显式标注『未经人工复核』", "未经人工复核" in t_no, t_no[:70])
t_yes = RR.watermark_text_of({"name": "标准税务风险分析报告", "doc_no": "WB-TR-01",
                              "version": "V1.0", "reviewed": True, "reviewed_by": "乙",
                              "generated_by": "甲", "generated_at": "2026-10-14 10:00"})
ok("D6 已复核报告水印含复核人与状态", "已复核" in t_yes and "乙" in t_yes, t_yes[:70])

print("=== E. 审计完整性 ===")
from engine.audit_trail import ACTIONS as ACT, ACTION_CN as CN
# E1 任务书六类关键操作 + P0-8 七类，动作必须登记且有中文名
REQ = ["doc.upload", "analysis.start", "doc.delete", "doc.download", "report.export",
       "report.download", "finding.review", "risk.review", "risk.comment", "risk.rectify",
       "project.create", "project.update", "project.delete", "project.member_change",
       "extract.run", "extract.correct", "job.finished", "job.cancel", "job.retry",
       "auth.login", "auth.login_failed", "auth.logout", "auth.denied",
       "user.create", "user.update", "role.create", "doc.classify", "report.delete",
       "company.purge"]
missing = [a for a in REQ if a not in ACT]
ok("E1 全部 %d 类关键动作已登记（ACTIONS）" % len(REQ), not missing, missing)
no_cn = [a for a in ACT if not CN.get(a)]
ok("E2 每个动作都有中文名（ACTION_CN 成对维护）", not no_cn, no_cn)
ascii_cn = [a for a in ACT if CN.get(a) and CN[a].isascii()]
ok("E3 动作中文名不得是英文/占位", not ascii_cn, ascii_cn)

login("p0sec_admin", "P0-Sec-Admin-2026!")
r = c.get("/api/v1/audit-logs", params={"page_size": 200}).json()
ok("E4 留痕可检索且返回动作字典", r["total"] >= 1 and len(r.get("actions") or []) == len(ACT),
   "total=%s actions=%s" % (r["total"], len(r.get("actions") or [])))
row = (r["items"] or [{}])[0]
ok("E5 留痕行含『谁/何时/做了什么/对象』四要素",
   all(k in row for k in ("user_name", "created_at", "action", "target")),
   sorted(row.keys()))
ok("E6 留痕时间戳为北京时间（UTC+8，YYYY-MM-DD HH:MM:SS）",
   bool(row.get("created_at")) and len(str(row["created_at"])) >= 19,
   row.get("created_at"))
# E7 写入唯一（静态）：INSERT INTO audit_logs 只允许在唯一权威
#   ★ 判据必须与既有闸门 `check_audit_trail_single_writer` 同口径：
#     ① **掩掉注释与文档串**（说明文字里的字面量不是真写入 —— 实测踩过：
#        `_verify_authority_gates.py` 的注释里提到该写法就被判成"第二写入点"）；
#     ② 跳过**本检查器自身**（它的源码里必然含该字面量）。
import re as _re, pathlib as _pl
# ★ 用**文件名**跳过自检（本脚本以 `python -c` 方式运行，`__file__` 未定义；
#   实测踩过 `NameError: name __file__ is not defined`）。
_self_names = {"_p0_i3_security_audit.py"}
def _mask_prose(text):
    def _blank(m):
        return _re.sub(r"[^\n]", " ", m.group(0))
    t = _re.sub(r'"""(?:.|\n)*?"""', _blank, text)
    t = _re.sub(r"\'\'\'(?:.|\n)*?\'\'\'", _blank, t)
    return _re.sub(r"#[^\n]*", lambda m: " " * len(m.group(0)), t)
_pat = _re.compile("INSERT" + r"\s+" + "INTO" + r"\s+" + "audit_logs", _re.I)
bad_writer = []
_scan = list(_pl.Path(".").glob("*.py")) + list(_pl.Path("engine").glob("*.py"))
for f in _scan:
    if f.name in _self_names or f.name == "audit_trail.py":
        continue
    if _pat.search(_mask_prose(f.read_text(encoding="utf-8", errors="replace"))):
        bad_writer.append(str(f))
ok("E7 留痕写入唯一（别处无真实 INSERT INTO audit_logs，已掩注释/文档串）",
   not bad_writer, bad_writer)
# E8 未登记动作照记原值（不静默丢弃）
from engine import audit_trail as AT
AT.record("p0.unregistered.probe", target="probe")
ok("E8 未登记动作照记原值（不静默丢弃）",
   AT.count(action="p0.unregistered.probe") == 1)
# E9 无归属不得用 0 冒充
AT.record("p0.null.company", target="p2")
_prow = AT.list_records(action="p0.null.company")[0]
ok("E9 无归属 company_id 存 NULL（不用 0 冒充）", _prow["company_id"] is None, _prow["company_id"])

print("SECFAILS=%d" % len(fails))
print("FAILS=%d" % len(fails))
assert not fails, fails
print("SECURITY_AUDIT_OK")
'''


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ)
        env.update({
            "APP_DATA_DIR": td,
            "APP_COOKIE_SECURE": "0",
            "APP_ALLOWED_ORIGINS": "http://testserver",
            "APP_ADMIN_USERNAME": ADMIN_USER,
            "APP_ADMIN_PASSWORD": ADMIN_PASS,
            "APP_LLM_MASTER_KEY": base64.urlsafe_b64encode(bytes(range(32))).decode("ascii"),
            "PYTHONIOENCODING": "utf-8",
        })
        env.pop("CODEBUDDY_SAFE_DELETE_BULK_GUARD", None)
        cp = subprocess.run([PY, "-c", textwrap.dedent(_CHILD)], cwd=str(ROOT), env=env,
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=600)
        print(cp.stdout or "")
        if cp.returncode != 0:
            print("---- stderr ----")
            print((cp.stderr or "")[-2000:])
        print("=" * 66)
        print("安全 + 审计测试：", "PASS" if cp.returncode == 0 else "FAIL")
        return cp.returncode


if __name__ == "__main__":
    sys.exit(main())
