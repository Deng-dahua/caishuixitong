# -*- coding: utf-8 -*-
"""编排：创建临时账号 → 用真实 Chromium 打开前端导出报告区 → 删除临时账号。

为什么需要它：本会话模型**无法读取图片**，故不能靠截图判断"前端显示成什么样"。
以**浏览器实际渲染出的文本/HTML**为准（客观、可 diff），再与离线产物比对。
"""
import os
import sqlite3
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)

from security import create_user, list_users        # noqa: E402
from runtime_storage import SECURITY_DB            # noqa: E402

USER = "_wb_pw_probe"
PW = "Probe-pw-12345"
NODE = r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"
NODE_MODULES = r"C:\Users\Administrator\.workbuddy\binaries\node\workspace\node_modules"
OUT = r"C:/tmp/frontend_dump"


def _purge(uid=None):
    con = sqlite3.connect(str(SECURITY_DB), timeout=10)
    if uid is not None:
        con.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        con.execute("DELETE FROM users WHERE id=?", (uid,))
    else:
        con.execute("DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE username=?)", (USER,))
        con.execute("DELETE FROM users WHERE username=?", (USER,))
    con.commit()
    con.close()


def main():
    _purge()                                     # 清掉上次残留
    uid = create_user(USER, PW, role="admin", company_ids=[1])
    print("[setup] 临时账号 id=%s" % uid)
    try:
        env = dict(os.environ)
        env["PW_USER"] = USER
        env["PW_PASS"] = PW
        env["NODE_PATH"] = NODE_MODULES
        p = subprocess.run([NODE, "scripts/_pw_dump_report.js", OUT],
                           cwd=REPO, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=420)
        print(p.stdout or "(无 stdout)")
        if p.stderr.strip():
            print("---- stderr ----")
            print(p.stderr[-3000:])
        return p.returncode
    finally:
        _purge(uid)
        print("[teardown] 已删除临时账号；当前用户:", [u["username"] for u in list_users()])


if __name__ == "__main__":
    sys.exit(main())
