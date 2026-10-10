# -*- coding: utf-8 -*-
"""端到端实测：前端取数接口是否真能把「企业文书式报告」交给前端。

★ 目的：把「前端为什么出旧模板」从推断变成**实测证据**。
  前端判定文书式版式的唯一依据（`tax-doc-analysis.js::_isEnterpriseEdition`）是
  结果里的 `enterprise_readable_report.document_meta`。本脚本用**临时账号**走真实 HTTP，
  检查 `/api/tax-risk-docs/last-analysis` 返回的载荷里该字段是否存在，并模拟前端判据。

临时账号用完即删（含其会话），不影响既有 `admin` 账号。
"""
import json
import os
import secrets
import sqlite3
import sys
import urllib.request
import http.cookiejar

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

from security import create_user, list_users          # noqa: E402
from runtime_storage import SECURITY_DB              # noqa: E402

BASE = "http://127.0.0.1:8001"
USER = "_wb_verify_tmp"
PW = "Vr-" + secrets.token_urlsafe(10)


def _login():
    jar = http.cookiejar.CookieJar()
    # 绕开环境代理（本机 127.0.0.1 直连；否则会走代理得到 502）
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(jar),
    )
    req = urllib.request.Request(
        BASE + "/api/auth/login",
        data=json.dumps({"username": USER, "password": PW}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with opener.open(req, timeout=15) as r:
        return opener, json.loads(r.read().decode())


def _get(opener, path):
    with opener.open(BASE + path, timeout=120) as r:
        return r.status, json.loads(r.read().decode())


def main():
    uid = create_user(USER, PW, role="admin", company_ids=[1])
    print("[1] 已创建临时账号 id=%s" % uid)
    try:
        opener, ok = _login()
        print("[2] 登录:", ok)

        st, data = _get(opener, "/api/tax-risk-docs/last-analysis?company_id=1")
        print("[3] /last-analysis HTTP", st, "| 顶层键数", len(data))
        # 前端消费链：data -> data.report -> enterprise_readable_report
        inner = (data or {}).get("report") or {}
        er = inner.get("enterprise_readable_report") or {}
        dm = er.get("document_meta") or {}
        print("    data.ok =", (data or {}).get("ok"), "| data.report 是 dict:", isinstance(inner, dict))
        print("    data.report.enterprise_readable_report 存在:", bool(er))
        print("    document_meta.name =", repr(dm.get("name")),
              "| edition_kind =", repr(dm.get("edition_kind")))

        # 复刻前端判据（含 2026-10-07 修正后的口径）
        is_ent = bool(er) and bool(dm and (dm.get("name") or dm.get("edition_kind")))
        print("    → 前端 _isEnterpriseEdition =>", "True（走企业文书式，不回落 7 章旧模板）" if is_ent
              else "False（会回落 7 章旧模板！）")
        if er:
            print("    文书式章节键:", [k for k in ("summary", "confirmed_problems", "materials",
                                                 "inspection_procedures", "overall_conclusion",
                                                 "recheck", "report_statement") if k in er])

        st2, data2 = _get(opener, "/api/tax-risk-docs/report-smart?company_id=1")
        print("[4] /report-smart HTTP", st2, "| ok =", data2.get("ok"),
              "| tax_burden 项数 =", len(data2.get("tax_burden") or []))
        print("    （修复前该接口返回 500：NameError: name 'findings' is not defined）")
    finally:
        con = sqlite3.connect(str(SECURITY_DB), timeout=10)
        con.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        con.execute("DELETE FROM users WHERE id=?", (uid,))
        con.commit()
        con.close()
        print("[5] 已删除临时账号及其会话；当前用户:",
              [u["username"] for u in list_users()])


if __name__ == "__main__":
    main()
