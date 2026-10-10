# -*- coding: utf-8 -*-
"""端到端实测「一键分析」http 路径（用户实际按钮路径）。

用临时账号走真实 HTTP：login → analyze-start → 轮询 analyze-status → analyze-result。
验证目标：
  · 不再出现「分析异常」；
  · task 最终 status=done；
  · 结果里 overall_level 正常、无 `[域分析异常]`、无公积金逐月假疑点。
用完即删临时账号（含其会话），不影响既有 admin。
"""
import http.cookiejar
import json
import os
import secrets
import sqlite3
import sys
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)

from security import create_user, list_users        # noqa: E402
from runtime_storage import SECURITY_DB            # noqa: E402

BASE = "http://127.0.0.1:8001"
USER = "_wb_verify_analyze"
PW = "Va-" + secrets.token_urlsafe(10)
COMPANY = int(os.environ.get("VERIFY_COMPANY", "1"))
POLL_MAX = 240          # 最多轮询 240 次 × 2s = 8 分钟


def _opener(jar):
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),                  # 绕开环境代理（否则 502）
        urllib.request.HTTPCookieProcessor(jar),
    )


def _cookie(jar, name):
    for c in jar:
        if c.name == name:
            return c.value
    return ""


def main():
    uid = create_user(USER, PW, role="admin", company_ids=[COMPANY])
    print("[1] 临时账号 id=%s" % uid)
    try:
        jar = http.cookiejar.CookieJar()
        op = _opener(jar)
        req = urllib.request.Request(
            BASE + "/api/auth/login",
            data=json.dumps({"username": USER, "password": PW}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with op.open(req, timeout=20) as r:
            print("[2] 登录:", json.loads(r.read().decode()))
        csrf = _cookie(jar, "csrf_token")

        req = urllib.request.Request(
            BASE + "/api/tax-risk-docs/analyze-start?company_id=%d&force=1" % COMPANY,
            data=b"", method="POST",
            headers={"X-CSRF-Token": csrf},
        )
        with op.open(req, timeout=30) as r:
            start = json.loads(r.read().decode())
        print("[3] analyze-start:", start)
        if not start.get("ok"):
            print("!! 启动失败"); return 2
        tid = start["task_id"]

        st, data = None, {}
        for i in range(POLL_MAX):
            time.sleep(2)
            with op.open(BASE + "/api/tax-risk-docs/analyze-status/" + tid, timeout=20) as r:
                data = json.loads(r.read().decode())
            st = data.get("status")
            if st in ("done", "error"):
                print("[4] 第 %d 次轮询到达终态: %s | progress=%s | msg=%s"
                      % (i + 1, st, data.get("progress"), str(data.get("message"))[:120]))
                break
        if st not in ("done", "error"):
            print("!! 超时未结束，最后状态:", st); return 3
        if st == "error":
            print("[!] 分析失败（这就是用户看到的'分析异常'）：", str(data.get("error"))[:600])
            return 4

        with op.open(BASE + "/api/tax-risk-docs/analyze-result/" + tid, timeout=120) as r:
            res = json.loads(r.read().decode())
        rep = (res or {}).get("report") or {}
        inner = rep.get("report") if isinstance(rep.get("report"), dict) else rep
        pl = inner.get("pipeline_log") or []
        print("[5] analyze-result ok =", res.get("ok"),
              "| overall_level =", inner.get("overall_level"),
              "| total_risks =", inner.get("total_risks"))
        print("    域分析异常条数 =", len([x for x in pl if "域分析异常" in x]))
        outs = inner.get("all_findings") or []
        bad = [f for f in outs if "公积金" in str(f.get("type", "")) and "逐月不匹配" in str(f.get("type", ""))]
        print("    公积金逐月假疑点残留 =", len(bad))
        print("    公积金相关发现 =", [f.get("type") for f in outs if "公积金" in str(f.get("type", ""))])
        print("    含企业文书式报告 =", bool(inner.get("enterprise_readable_report")))
        return 0
    finally:
        con = sqlite3.connect(str(SECURITY_DB), timeout=10)
        con.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        con.execute("DELETE FROM users WHERE id=?", (uid,))
        con.commit()
        con.close()
        print("[6] 已删除临时账号；当前用户:", [u["username"] for u in list_users()])


if __name__ == "__main__":
    sys.exit(main())
