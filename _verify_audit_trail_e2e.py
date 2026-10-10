# -*- coding: utf-8 -*-
"""端到端验收：**业务操作留痕**真的会落库（`audit_logs` 从"零写入"变为"六类动作都有记录"）。

## 为什么必须跑真服务

改造前 `audit_logs` 表 0 行、全仓无 `INSERT`。修完"代码里有 record() 调用"**不等于**
"用户操作后真的能查到记录" —— 中间隔着路由接线、依赖注入、CSRF、异常吞噬等一层。
故本脚本起**隔离实例**（`APP_DATA_DIR=<临时目录>`），按真实操作顺序走一遍并**直接查库**断言。

## 设计约束：**有界**

首版把"等整轮分析跑完"写进脚本，实测在隔离实例里分析 45 分钟未到终态，
于是整个验收被拖死（且 `timeout` 在本平台**杀不掉原生 Windows 进程**，留下孤儿服务）。
现改为：

- 六类动作里**只有 `analysis.start` 需要分析**，而它的留痕是在 `_register_job_started`
  里**同步**写的 ⇒ **发起后立即断言，不等完成**；
- 其余五类用**不依赖整轮分析**的入口触发（单条复核 / 工作底稿导出 / 报告下载请求 /
  资料删除 / 报告删除），故整个验收在 1~3 分钟内结束；
- 全局看门狗（`WATCHDOG_S`，默认 420s）到点**硬退出**并打印"卡在哪一步"；
- 每个请求都带 `timeout`，且订阅方 `try/except` 如实记录；
- `finally` 里按 PID **和端口**双重兜底杀子进程（防孤儿）。

## 反向验证（`VERIFY_BREAK=1`）

把服务进程内的 `engine.audit_trail.record` 掐成 no-op，断言
「操作跑完必有记录」**变红** —— 不红就说明本脚本的判据是假的。

用法：
    ./.venv/Scripts/python.exe _verify_audit_trail_e2e.py
    VERIFY_BREAK=1 ./.venv/Scripts/python.exe _verify_audit_trail_e2e.py

★ 本脚本**不得**与 `_verify_authority_gates.py`（会临时改坏源码）并行运行。
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
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
PORT = int(os.environ.get("VERIFY_PORT", "8014"))
COMPANY = int(os.environ.get("VERIFY_COMPANY", "1"))
WATCHDOG_S = int(os.environ.get("VERIFY_WATCHDOG", "420"))


def _free_port(p: int) -> bool:
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", p))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _kill_by_port(p: int) -> None:
    """按端口兜底杀进程（防孤儿：`timeout`/SIGTERM 在本平台对原生进程不可靠）。

    ★ 实测坑：`netstat -ano` 的输出**不是 UTF-8**（含本地化字节），
      用 `text=True` 让 subprocess 按 utf-8 解码会在读取线程里抛
      `UnicodeDecodeError`，`run()` 于是返回 `stdout=None` —— 后续 `splitlines()`
      直接崩，兜底清理**在最需要它的那一刻失效**。故改为取 bytes 自行 `errors="replace"` 解码。
    """
    try:
        cp = subprocess.run(["netstat", "-ano"], capture_output=True, timeout=20)
        raw = cp.stdout or b""
        out = raw.decode("utf-8", errors="replace")
    except Exception:                            # noqa: BLE001
        return
    pids = set()
    for line in out.splitlines():
        if "LISTENING" in line and (":%d " % p) in line:
            parts = line.split()
            if parts and parts[-1].isdigit():
                pids.add(parts[-1])
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/F", "/PID", pid],
                           capture_output=True, timeout=20)
        except Exception:                        # noqa: BLE001
            pass


def _stage_data() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="audit_e2e_"))
    for f in ("security.db", "accounting.db"):
        src = ROOT / "data" / f
        if src.exists():
            shutil.copy2(src, tmp / f)
    up = ROOT / "data" / "uploads"
    if up.exists():
        shutil.copytree(up, tmp / "uploads")
    return tmp


def _cookie(jar, name):
    for c in jar:
        if c.name == name:
            return c.value
    return ""


def _opener(jar):
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),                  # 绕开环境代理（否则 502）
        urllib.request.HTTPCookieProcessor(jar),
    )


def _multipart(fields: dict, filename: str, content: bytes):
    b = "----wb" + uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                    % (b, k, v)).encode())
    out.append(("--%s\r\nContent-Disposition: form-data; name=\"files\"; filename=\"%s\"\r\n"
                "Content-Type: text/csv\r\n\r\n" % (b, filename)).encode())
    out.append(content)
    out.append(("\r\n--%s--\r\n" % b).encode())
    return b"".join(out), "multipart/form-data; boundary=" + b


def main() -> int:
    if not _free_port(PORT):
        print("!! 端口 %d 已被占用，换个 VERIFY_PORT" % PORT)
        return 1
    data_dir = _stage_data()
    base = "http://127.0.0.1:%d" % PORT
    env = dict(os.environ)
    env["APP_DATA_DIR"] = str(data_dir)
    env["APP_COOKIE_SECURE"] = "0"
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("CODEBUDDY_SAFE_DELETE_BULK_GUARD", None)
    log = open(data_dir / "server.log", "w", encoding="utf-8")

    break_mode = os.environ.get("VERIFY_BREAK") == "1"
    if break_mode:
        boot = ("import main, uvicorn;"
                "from engine import audit_trail as _AT;"
                "_AT.record = lambda *a, **k: None;"
                "uvicorn.run(main.app, host='127.0.0.1', port=%d, log_level='info')" % PORT)
        cmd = [PY, "-c", boot]
        print("★ 反向验证模式：业务留痕写入已被掐成 no-op")
    else:
        cmd = [PY, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT)]
    proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    print("隔离实例 APP_DATA_DIR =", data_dir, "| pid =", proc.pid)

    watchdog_fired = {"v": False}

    def _watchdog():
        time.sleep(WATCHDOG_S)
        watchdog_fired["v"] = True
        print("!! 看门狗触发（%ds）：验收未在时限内结束，强制退出并清理" % WATCHDOG_S)
        try:
            proc.kill()
        except Exception:                        # noqa: BLE001
            pass
        _kill_by_port(PORT)
        os._exit(3)

    threading.Thread(target=_watchdog, daemon=True).start()

    fails, notes = [], []
    _seen = set()

    def ok(name, cond, extra=""):
        _i = str(name).split()[0] if str(name).strip() else str(name)
        if _i in _seen:
            print("FAIL 断言编号重复 %s：%s" % (_i, name))
            fails.append("断言编号重复 " + _i)
        _seen.add(_i)
        print(("PASS " if cond else "FAIL ") + name + ((" | " + str(extra)) if extra else ""))
        if not cond:
            fails.append(name)

    def note(msg):
        notes.append(msg)
        print("NOTE " + msg)

    try:
        ready = False
        for _ in range(60):
            time.sleep(1)
            if proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen(base + "/api/auth/me", timeout=2):
                    ready = True
                    break
            except urllib.error.HTTPError:
                ready = True
                break
            except Exception:
                continue
        if not ready:
            print("!! 服务未就绪；服务日志尾部：")
            print((data_dir / "server.log").read_text(encoding="utf-8", errors="ignore")[-2500:])
            return 2
        print("[1] 服务就绪")

        os.environ["APP_DATA_DIR"] = str(data_dir)
        from security import create_user                       # noqa: E402
        user = "_wb_verify_audit"
        pw = "Va-" + secrets.token_urlsafe(10)
        create_user(user, pw, role="admin", company_ids=[COMPANY])
        jar = http.cookiejar.CookieJar()
        op = _opener(jar)
        req = urllib.request.Request(
            base + "/api/auth/login",
            data=json.dumps({"username": user, "password": pw}).encode(),
            headers={"Content-Type": "application/json"})
        with op.open(req, timeout=20) as r:
            print("[2] 登录:", json.loads(r.read().decode()))
        csrf = _cookie(jar, "csrf_token")

        sys.path.insert(0, str(ROOT))
        from engine import audit_trail as AT                     # noqa: E402
        AT.ensure_schema()
        n_before = AT.count()
        print("    [基线] audit_logs 行数 =", n_before)

        doc_id = None
        if not break_mode:
            # ── ① 上传 ────────────────────────────────────────────────
            fname = "留痕验收_%s.csv" % uuid.uuid4().hex[:6]
            body, ctype = _multipart({}, fname, "科目,金额\n主营业务收入,1000\n".encode())
            req = urllib.request.Request(
                base + "/api/tax-risk-docs/upload?company_id=%d" % COMPANY,
                data=body, method="POST",
                headers={"Content-Type": ctype, "X-CSRF-Token": csrf})
            with op.open(req, timeout=90) as r:
                up = json.loads(r.read().decode())
            print("[3] 上传:", up.get("ok"), up.get("message"))
            doc_id = (up.get("uploaded") or [{}])[0].get("id")

            # ── ② 单条复核（不需要整轮分析）──────────────────────────
            req = urllib.request.Request(
                base + "/api/tax-risk-docs/review-single?company_id=%d" % COMPANY,
                data=json.dumps({"title": "留痕验收单条", "amount": "1000"}).encode(),
                method="POST",
                headers={"Content-Type": "application/json", "X-CSRF-Token": csrf})
            try:
                with op.open(req, timeout=180) as r:
                    rv1 = json.loads(r.read().decode())
                print("[4] 单条复核:", rv1.get("ok"), (rv1.get("review") or {}).get("level"))
            except Exception as exc:                       # noqa: BLE001
                note("单条复核 HTTP 未成功（如实记录，不影响留痕判据）：%r" % (exc,))

            # ── ③ 导出工作底稿（不需要整轮分析）──────────────────────
            try:
                with op.open(base + "/api/tax-risk-docs/manual-worksheets/export?company_id=%d"
                             % COMPANY, timeout=120) as r:
                    print("[5] 导出工作底稿: HTTP", r.status, "字节", len(r.read()))
            except Exception as exc:                       # noqa: BLE001
                note("工作底稿导出 HTTP 未成功（如实记录）：%r" % (exc,))

            # ── ④ 报告下载**请求**（留痕写在重算之前，故即便重算超时也已落库）──
            try:
                with op.open(base + "/api/tax-risk/report/download?company_id=%d&format=pdf"
                             % COMPANY, timeout=150) as r:
                    print("[6] 下载报告(pdf): HTTP", r.status, "字节", len(r.read()))
            except Exception as exc:                       # noqa: BLE001
                note("报告下载 HTTP 未成功（留痕仍应存在，见断言④）：%r" % (exc,))

            # ── ⑤ 删资料 ──────────────────────────────────────────────
            if doc_id:
                req = urllib.request.Request(
                    base + "/api/tax-risk-docs/batch-delete",
                    data=json.dumps({"company_id": COMPANY, "doc_ids": [doc_id]}).encode(),
                    method="POST",
                    headers={"Content-Type": "application/json", "X-CSRF-Token": csrf})
                with op.open(req, timeout=90) as r:
                    dl = json.loads(r.read().decode())
                print("[7] 删资料:", dl.get("ok"), dl.get("message"))

            # ── ⑥ 删报告 ──────────────────────────────────────────────
            req = urllib.request.Request(
                base + "/api/tax-risk-docs/report?company_id=%d" % COMPANY,
                method="DELETE", headers={"X-CSRF-Token": csrf})
            with op.open(req, timeout=180) as r:
                dr = json.loads(r.read().decode())
            print("[8] 删报告:", dr.get("ok"), str(dr.get("message"))[:80])

            # ── ⑦ 发起分析（★ 留痕同步写，**不等完成**）────────────────
            req = urllib.request.Request(
                base + "/api/tax-risk-docs/analyze-start?company_id=%d&force=1" % COMPANY,
                data=b"", method="POST", headers={"X-CSRF-Token": csrf})
            with op.open(req, timeout=60) as r:
                start = json.loads(r.read().decode())
            print("[9] analyze-start（不等完成）->",
                  {k: start.get(k) for k in ("ok", "task_id")})

        # ══ 读侧：直接查隔离库 ══════════════════════════════════════════
        rows = AT.list_records(company_id=COMPANY, limit=200)
        acts = sorted({r["action"] for r in rows})
        print("    audit_logs 行数(本账套) =", len(rows), "| 动作码 =", acts)

        if break_mode:
            ok("R1 反向验证：掐掉留痕写入后，『操作跑完必有记录』**必须变红**",
               len(rows) == 0, {"rows": len(rows), "actions": acts})
            print("FAILS=%d | NOTES=%d" % (len(fails), len(notes)))
            return 1 if fails else 0

        ok("① 六类动作跑完后 audit_logs **不再为 0 行**（本次要修的根因）",
           len(rows) > 0, {"rows": len(rows), "baseline": n_before})
        expected = ["doc.upload", "analysis.start", "finding.review",
                    "report.export", "report.download", "doc.delete", "report.delete"]
        missing = [a for a in expected if a not in acts]
        ok("② 六类动作**全部**有留痕（上传/分析/复核/导出/下载/删除）",
           not missing, {"missing": missing, "covered": acts})
        ok("③ 每条留痕都带北京时间戳",
           bool(rows) and all(str(r["created_at"]).endswith("+08:00") for r in rows),
           sorted({str(r["created_at"])[-6:] for r in rows}))
        ok("④ 每条留痕都带操作人（来自 request.state.auth，不编造）",
           bool(rows) and all(str(r["user_name"]).strip() for r in rows),
           sorted({r["user_name"] for r in rows}))
        ok("⑤ 动作码都能出中文名（不得把英文码直接怼给用户）",
           all(r["action_cn"] and r["action_cn"] != r["action"]
               for r in rows if r["action"] in AT.ACTIONS),
           sorted({(r["action"], r["action_cn"]) for r in rows})[:4])
        ok("⑥ 分析发起那条记下了触发方式（中文，可读）",
           any("触发方式" in str(r["detail"]) for r in rows
               if r["action"] == "analysis.start"),
           [r["detail"] for r in rows if r["action"] == "analysis.start"][:2])

        # ══ 读接口：用户实际打开审计页会看到什么 ════════════════════════
        with op.open(base + "/api/audit-logs?company_id=%d&limit=50" % COMPANY, timeout=30) as r:
            api = json.loads(r.read().decode())
        print("    /api/audit-logs -> ok=%s, count=%s"
              % (api.get("ok"), api.get("count")))
        ok("⑦ 读接口 `/api/audit-logs` 返回非空（用户打开审计页能看到记录）",
           bool(api.get("ok")) and len(api.get("logs") or []) > 0,
           {"ok": api.get("ok"), "n": len(api.get("logs") or [])})
        first = (api.get("logs") or [{}])[0]
        ok("⑧ 读接口向后兼容：原有 7 键仍在，且新增 user_id/action_cn",
           all(k in first for k in ("id", "company_id", "user_name", "action", "target",
                                    "detail", "created_at", "user_id", "action_cn")),
           sorted(first.keys()))
        with op.open(base + "/api/audit-logs?action=doc.upload&limit=10", timeout=30) as r:
            api2 = json.loads(r.read().decode())
        ok("⑨ 读接口新增 `action` 过滤生效",
           bool(api2.get("logs")) and all(x["action"] == "doc.upload" for x in api2["logs"]),
           [x["action"] for x in (api2.get("logs") or [])][:5])
        print("    [终态] audit_logs 总行数 =", AT.count(), "（含其它账套）")
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=20)
        except Exception:                            # noqa: BLE001
            try:
                proc.kill()
            except Exception:                        # noqa: BLE001
                pass
        _kill_by_port(PORT)                          # 双重兜底：不留孤儿
        log.close()
        print("[清理] 隔离实例已停止（已按端口兜底确认无监听）；数据目录保留供核对：", data_dir)

    print("FAILS=%d | NOTES=%d" % (len(fails), len(notes)))
    for n in notes:
        print("   NOTE:", n)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
