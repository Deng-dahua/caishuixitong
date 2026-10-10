# -*- coding: utf-8 -*-
"""本地核验用：用系统自带的会话机制签发一个管理员会话（不绕过任何校验逻辑）。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import security
UA = os.environ.get("PROBE_UA", "ProbeClient/1.0")
with security._connect() as conn:
    row = conn.execute("select id, username, role, company_ids, active from users where username='admin'").fetchone()
user = {"id": row[0], "username": row[1], "role": row[2],
        "company_ids": row[3] or "", "active": row[4]}
token, csrf = security.create_session(user, client_fingerprint=UA[:256])
print(token)
print(csrf)
