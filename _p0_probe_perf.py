# -*- coding: utf-8 -*-
"""P0 验收 · 性能探测（只读计时）：单次一键分析耗时 + 数据规模。

目的：先量出**基线**，再决定 10 万行 / 50 并发 / 报告生成三段性能测试怎么构造。
本脚本只在**隔离实例**上跑（复制 security.db/accounting.db/uploads 到临时 APP_DATA_DIR），
不触碰生产数据。
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
PORT = int(os.environ.get("VERIFY_PORT", "8021"))
COMPANY = int(os.environ.get("VERIFY_COMPANY", "1"))


def _free(p):
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", p))
        return True
    except OSError:
        return False
    finally:
        s.close()


def main() -> int:
    if not _free(PORT):
        print("端口被占用")
        return 1
    data_dir = Path(tempfile.mkdtemp(prefix="p0_perf_probe_"))
    for f in ("security.db", "accounting.db"):
        src = ROOT / "data" / f
        if src.exists():
            shutil.copy2(src, data_dir / f)
    up = ROOT / "data" / "uploads"
    if up.exists():
        shutil.copytree(up, data_dir / "uploads")

    env = dict(os.environ)
    env["APP_DATA_DIR"] = str(data_dir)
    env["APP_COOKIE_SECURE"] = "0"
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("CODEBUDDY_SAFE_DELETE_BULK_GUARD", None)
    log = open(data_dir / "server.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [PY, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
    base = "http://127.0.0.1:%d" % PORT
    try:
        ready = False
        for _ in range(90):
            time.sleep(1)
            if proc.poll() is not None:
                break
            try:
                urllib.request.urlopen(base + "/api/auth/me", timeout=2)
            except urllib.error.HTTPError:
                ready = True
                break
            except Exception:
                continue
        if not ready:
            print("服务未就绪")
            print((data_dir / "server.log").read_text(encoding="utf-8", errors="ignore")[-2000:])
            return 2

        os.environ["APP_DATA_DIR"] = str(data_dir)
        sys.path.insert(0, str(ROOT))
        from security import create_user
        u, pw = "_p0_probe", "Pp-" + secrets.token_urlsafe(10)
        create_user(u, pw, role="admin", company_ids=[COMPANY])

        jar = http.cookiejar.CookieJar()
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                        urllib.request.HTTPCookieProcessor(jar))
        req = urllib.request.Request(base + "/api/auth/login",
                                     data=json.dumps({"username": u, "password": pw}).encode(),
                                     headers={"Content-Type": "application/json"})
        with op.open(req, timeout=20) as r:
            print("login:", json.loads(r.read().decode()).get("ok"))
        csrf = next((c.value for c in jar if c.name == "csrf_token"), "")

        t0 = time.time()
        req = urllib.request.Request(
            base + "/api/tax-risk-docs/analyze-start?company_id=%d&force=1" % COMPANY,
            data=b"", method="POST", headers={"X-CSRF-Token": csrf})
        with op.open(req, timeout=30) as r:
            start = json.loads(r.read().decode())
        tid = start.get("task_id")
        print("task_id:", tid)
        st = None
        last = {}
        for _ in range(400):            # 400 × 3s = 20 min 上限
            time.sleep(3)
            with op.open(base + "/api/tax-risk-docs/analyze-status/" + str(tid), timeout=20) as r:
                last = json.loads(r.read().decode())
            st = last.get("status")
            if st in ("done", "error"):
                break
        el = time.time() - t0
        print("status=%s  耗时=%.1fs (%.2f 分钟)" % (st, el, el / 60))
        print("progress:", last.get("progress"), "|", str(last.get("message"))[:120])

        with op.open(base + "/api/tax-risk-docs/analyze-result/" + str(tid), timeout=120) as r:
            res = json.loads(r.read().decode())
        rep = (res.get("report") or res)
        print("结果顶层键:", sorted(list(rep.keys()))[:20] if isinstance(rep, dict) else type(rep))
        print("PERF_PROBE_DONE seconds=%.1f status=%s" % (el, st))
        return 0 if st == "done" else 3
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
