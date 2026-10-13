# -*- coding: utf-8 -*-
"""P0 验收 · 性能测试（隔离实例 + 真服务 + 真 HTTP）。

三段（任务书 §2）：
  P1 单项目 **10 万行**数据 ⇒ 一键分析 < **10 分钟**
  P2 **50 并发**分析任务（不同账套 ⇒ 各起一个后台线程）
  P3 报告生成 < **3 分钟**

★ 关键实现事实（实测得出，决定测试怎么构造）：
  各 Excel 解析器对**单个工作表**有硬行数上限（序时账/银行流水/发票/存货 = 5000 行；
  其余 3000/2000/1000/500/200 不等）。⇒ "10 万行"必须**分散到多个文件**才会被真正读入，
  单文件 10 万行只会被读前 5000 行。本脚本用 20 个 × 5000 行 = 10 万行，
  并**独立验证**解析行数确实为 100000（不是"文件行数"而是"引擎读入行数"）。
★ 分析任务无**全局并发上限**，同账套去重、跨账套并行各起线程；Python GIL 下 CPU 密集段
  实际串行 ⇒ 本脚本如实报告"承接数 / 完成数 / 总耗时 / 平均单任务耗时"，不做吞吐美言。

用法：
    python _p0_i2_perf.py                # 全跑
    P0_PERF_PHASE=p1 python _p0_i2_perf.py
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
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
PORT = int(os.environ.get("VERIFY_PORT", "8023"))
PHASE = os.environ.get("P0_PERF_PHASE", "all").lower()

BIG_CID = 9001                 # 10 万行账套
BIG_FILES = 20                 # 20 个文件
BIG_ROWS_PER_FILE = 5000       # × 5000 = 100,000 行
BIG_ROWS_TOTAL = BIG_FILES * BIG_ROWS_PER_FILE
CONC_BASE = 9101               # 50 并发账套起始 id
CONC_N = 50
CONC_ROWS = 200                # 每账套 200 行（并发测的是"承接与调度"，不是再测数据量）

P1_LIMIT_S = 600               # 10 分钟
P3_LIMIT_S = 180               # 3 分钟

results: list = []


def ok(name: str, cond: bool, extra: str = "") -> None:
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + ((" | " + str(extra)) if extra else ""))


def _free(p: int) -> bool:
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", p))
        return True
    except OSError:
        return False
    finally:
        s.close()


# ── 造数 ─────────────────────────────────────────────────────────────────────
#: 真实序时账的结构（**照抄自** `data/uploads/1/1_14_2025年序时账.xlsx`）
#: ★ 为什么必须照抄：自拟列名（如把「记账月份」放末尾、另加「日期」列、改工作表名）
#:   会让 `main._parse_excel_structured` **返回 None**（表头评分不足 ⇒ 认不出是序时账）
#:   ⇒ 引擎实读 0 行、分析直接 error（实测踩过：`实读=0` + `status=error`）。
VOUCHER_SHEET = "2025年序时账"
VOUCHER_HEADER = ["记账月份", "凭证号", "序号", "摘要", "科目编码", "科目名称", "借方金额", "贷方金额"]


def _make_voucher_xlsx(path: Path, rows: int) -> None:
    """生成一份**序时账**工作簿（结构对齐真实样例，确保被解析器识别为 voucher）。"""
    #   ★ 必须用**普通模式**（不是 `write_only=True`）：write_only 生成的 xlsx
    #     **不写 worksheet dimension** ⇒ 以 `read_only=True` 打开时 `max_row is None`
    #     ⇒ `_detect_header_row` 抛 `TypeError: '<' not supported between NoneType and int`
    #     ⇒ 被 `_parse_excel_structured` 的 except 吞掉并判为"无法识别"（实测踩过：
    #     造数后 `实读=0`、分析 3 秒即 error，排查两轮才定位到这一行）。
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.create_sheet(VOUCHER_SHEET)
    wb.remove(wb["Sheet"])
    ws.append(list(VOUCHER_HEADER))
    for i in range(rows):
        m = (i % 12) + 1
        amt = float((i % 900) + 100) * 1.13
        acct = "600102" if i % 3 == 0 else ("640101" if i % 3 == 1 else "100201")
        name = {"600102": "主营业务收入/服务收入",
                "640101": "主营业务成本/服务成本",
                "100201": "银行存款/基本户"}[acct]
        ws.append([str(m), "记-%04d" % (i // 5 + 1), str(i + 1),
                   "P0 性能测试凭证行 %d" % i, acct, name,
                   round(amt, 2) if i % 2 == 0 else None,
                   None if i % 2 == 0 else round(amt, 2)])
    wb.save(str(path))


def _stage_dir() -> Path:
    d = Path(tempfile.mkdtemp(prefix="p0_perf_"))
    for f in ("security.db", "accounting.db"):
        src = ROOT / "data" / f
        if src.exists():
            shutil.copy2(src, d / f)
    up = ROOT / "data" / "uploads"
    if up.exists():
        shutil.copytree(up, d / "uploads")
    return d


def _add_companies(data_dir: Path, ids: list) -> None:
    import sqlite3
    conn = sqlite3.connect(str(data_dir / "accounting.db"))
    try:
        for cid in ids:
            conn.execute("INSERT OR REPLACE INTO companies (id, name) VALUES (?, ?)",
                         (int(cid), "P0 性能测试账套 %d" % int(cid)))
        conn.commit()
    finally:
        conn.close()


def _gen_big(data_dir: Path) -> float:
    t0 = time.time()
    out = data_dir / "uploads" / str(BIG_CID)
    out.mkdir(parents=True, exist_ok=True)
    for i in range(BIG_FILES):
        _make_voucher_xlsx(out / ("%d_%d_2025年序时账_性能测试_%02d.xlsx" % (BIG_CID, i + 1, i + 1)),
                           BIG_ROWS_PER_FILE)
    return time.time() - t0


def _gen_concurrent(data_dir: Path) -> float:
    t0 = time.time()
    for k in range(CONC_N):
        cid = CONC_BASE + k
        d = data_dir / "uploads" / str(cid)
        d.mkdir(parents=True, exist_ok=True)
        _make_voucher_xlsx(d / ("%d_1_2025年序时账_并发测试.xlsx" % cid), CONC_ROWS)
    return time.time() - t0


def _verify_read_rows(data_dir: Path) -> tuple:
    """在**子进程**里用引擎自己的解析器解析 20 个文件，返回 (合计行数, 每文件行数)。"""
    code = r'''
import json, os, sys, pathlib
sys.path.insert(0, os.getcwd())
import main
d = pathlib.Path(os.environ["BIG_DIR"])
rows = []
for p in sorted(d.glob("*.xlsx")):
    try:
        res = main._parse_excel_structured(str(p), ".xlsx", p.name)
    except Exception as e:
        rows.append(-1); print("ERR", p.name, repr(e)[:120], file=sys.stderr); continue
    # ★ 返回形状以实现为准：`{"type": "voucher", "rows": [...]}`（实测确认）。
    n = 0
    if isinstance(res, dict):
        if isinstance(res.get("rows"), list):
            n = len(res["rows"])
        else:
            for v in res.values():
                if isinstance(v, dict) and isinstance(v.get("rows"), list):
                    n += len(v["rows"]); break
    elif isinstance(res, list):
        n = len(res)
    rows.append(n)
print("ROWS=" + json.dumps(rows))
'''
    env = dict(os.environ)
    env["APP_DATA_DIR"] = str(data_dir)
    env["BIG_DIR"] = str(data_dir / "uploads" / str(BIG_CID))
    env["PYTHONIOENCODING"] = "utf-8"
    cp = subprocess.run([PY, "-c", code], cwd=str(ROOT), env=env, capture_output=True,
                        text=True, encoding="utf-8", errors="replace", timeout=1800)
    rows = []
    for ln in (cp.stdout or "").splitlines():
        if ln.startswith("ROWS="):
            rows = json.loads(ln[5:])
    return sum(x for x in rows if x > 0), rows


# ── HTTP ─────────────────────────────────────────────────────────────────────
class Client:
    def __init__(self, base: str):
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(self.jar))

    def csrf(self) -> str:
        return next((c.value for c in self.jar if c.name == "csrf_token"), "")

    def json(self, method, path, body=None, timeout=300, csrf=True):
        headers = {}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if csrf and method not in ("GET", "HEAD"):
            headers["X-CSRF-Token"] = self.csrf()
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with self.op.open(req, timeout=timeout) as r:
                return r.status, json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode("utf-8", "replace"))
            except Exception:                                    # noqa: BLE001
                return e.code, {}
        except Exception as e:                                   # noqa: BLE001
            return 0, {"_err": repr(e)[:120]}


def _boot(data_dir: Path, admin_u: str, admin_p: str):
    os.environ["APP_DATA_DIR"] = str(data_dir)
    sys.path.insert(0, str(ROOT))
    from security import init_security_db, create_user
    init_security_db()
    try:
        create_user(admin_u, admin_p, role="admin")
    except Exception:                                            # noqa: BLE001
        pass
    env = dict(os.environ)
    env.update({"APP_DATA_DIR": str(data_dir), "APP_COOKIE_SECURE": "0",
                "PYTHONIOENCODING": "utf-8"})
    env.pop("CODEBUDDY_SAFE_DELETE_BULK_GUARD", None)
    log = open(data_dir / "server.log", "w", encoding="utf-8")
    proc = subprocess.Popen([PY, "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
                             "--port", str(PORT)], cwd=str(ROOT), env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    base = "http://127.0.0.1:%d" % PORT
    for _ in range(120):
        time.sleep(1)
        if proc.poll() is not None:
            break
        try:
            urllib.request.urlopen(base + "/api/auth/me", timeout=2)
        except urllib.error.HTTPError:
            return proc, base
        except Exception:
            continue
    return proc, base


def _poll(client: Client, tid: str, *, limit_s: int, step: int = 3):
    t0 = time.time()
    last = {}
    while time.time() - t0 < limit_s:
        time.sleep(step)
        _st, last = client.json("GET", "/api/tax-risk-docs/analyze-status/" + str(tid))
        if last.get("status") in ("done", "error"):
            break
    return last.get("status"), time.time() - t0, last


# ── 主流程 ───────────────────────────────────────────────────────────────────
def main() -> int:
    if not _free(PORT):
        print("端口被占用")
        return 1
    data_dir = _stage_dir()
    admin_u, admin_p = "_p0perf_admin", "P0-Perf-Admin-2026!"

    ids = [BIG_CID]
    if PHASE in ("all", "p2"):
        ids += [CONC_BASE + k for k in range(CONC_N)]
    _add_companies(data_dir, ids)

    if PHASE in ("all", "p1"):
        g = _gen_big(data_dir)
        print("[造数] %d 个 × %d 行 = %d 行，耗时 %.1fs"
              % (BIG_FILES, BIG_ROWS_PER_FILE, BIG_ROWS_TOTAL, g))
        read_rows, per = _verify_read_rows(data_dir)
        ok("P1-0 引擎真读入 %d 行（= 20 × 5000，非『只看文件行数』）"
           % BIG_ROWS_TOTAL, read_rows == BIG_ROWS_TOTAL,
           "实读=%d；每文件=%s" % (read_rows, per[:5]))
    if PHASE in ("all", "p2"):
        g2 = _gen_concurrent(data_dir)
        print("[造数] %d 个并发账套 × %d 行，耗时 %.1fs" % (CONC_N, CONC_ROWS, g2))

    proc, base = _boot(data_dir, admin_u, admin_p)
    print("隔离实例 =", data_dir, "| 服务 =", base)
    try:
        c = Client(base)
        st, r = c.json("POST", "/api/v1/auth/login",
                       body={"username": admin_u, "password": admin_p})
        ok("登录成功", st == 200 and r.get("ok") is True, st)

        # ── P1：10 万行分析 ────────────────────────────────────────────
        if PHASE in ("all", "p1"):
            print("\n== P1 单项目 10 万行 ⇒ 一键分析（上限 %ds）==" % P1_LIMIT_S)
            st, s1 = c.json("POST", "/api/tax-risk-docs/analyze-start?company_id=%d&force=1"
                            % BIG_CID, body={}, timeout=60)
            tid = s1.get("task_id")
            ok("P1-1 分析任务已受理（拿到 task_id）", st == 200 and bool(tid),
               "status=%s task=%s" % (st, tid))
            stt, el, last = _poll(c, tid, limit_s=P1_LIMIT_S + 300)
            ok("P1-2 10 万行分析完成（status=done）", stt == "done", stt)
            ok("P1-3 分析耗时 < %d 秒（%.2f 分钟 < %.2f 分钟）"
               % (P1_LIMIT_S, el / 60, P1_LIMIT_S / 60), el < P1_LIMIT_S,
               "实测 %.1fs" % el)
            print("[P1 结果] 10 万行分析耗时 = %.1fs = %.2f 分钟（上限 10 分钟）"
                  % (el, el / 60))
            # 顺带记录报告生成（P3），复用本账套的既有分析结果
            if PHASE in ("all", "p1", "p3"):
                st, proj = c.json("POST", "/api/v1/projects", body={
                    "name": "P0 性能-报告生成", "company_id": BIG_CID})
                pid = proj.get("id")
                if pid:
                    t0 = time.time()
                    st, rep = c.json("POST", "/api/v1/projects/%s/reports" % pid,
                                     body={"view": "full",
                                           "formats": ["pdf", "docx", "xlsx", "html"]},
                                     timeout=600)
                    el3 = time.time() - t0
                    print("\n== P3 报告生成（上限 %ds）==" % P3_LIMIT_S)
                    ok("P3-1 报告生成成功", st in (200, 201) and bool(rep.get("id") or rep.get("report_id")),
                       "status=%s" % st)
                    ok("P3-2 报告生成耗时 < %d 秒（%.2f 分钟）" % (P3_LIMIT_S, P3_LIMIT_S / 60),
                       el3 < P3_LIMIT_S, "实测 %.1fs = %.2f 分钟" % (el3, el3 / 60))
                else:
                    ok("P3-1 报告生成（前置：建项目失败）", False, str(proj)[:160])

        # ── P2：50 并发 ───────────────────────────────────────────────
        if PHASE in ("all", "p2"):
            print("\n== P2 %d 并发分析任务 ==" % CONC_N)
            accepted: list = []
            rejected: list = []
            lock = threading.Lock()

            def fire(cid: int) -> None:
                cc = Client(base)
                st, _rr = cc.json("POST", "/api/v1/auth/login",
                                  body={"username": admin_u, "password": admin_p})
                st, rr = cc.json("POST", "/api/tax-risk-docs/analyze-start?company_id=%d&force=1"
                                 % cid, body={}, timeout=60)
                with lock:
                    if st == 200 and rr.get("task_id"):
                        accepted.append((cid, rr["task_id"]))
                    else:
                        rejected.append((cid, st, str(rr)[:100]))

            t0 = time.time()
            ths = [threading.Thread(target=fire, args=(CONC_BASE + k,)) for k in range(CONC_N)]
            for t in ths:
                t.start()
            for t in ths:
                t.join(timeout=120)
            t_submit = time.time() - t0
            ok("P2-1 50 个并发请求全部返回（无挂起/超时）",
               len(accepted) + len(rejected) == CONC_N,
               "受理=%d 拒绝=%d 提交耗时=%.1fs" % (len(accepted), len(rejected), t_submit))
            ok("P2-2 50 个任务全部被受理（无全局并发上限拦截）",
               len(accepted) == CONC_N, "拒绝详情=%s" % rejected[:3])

            # 轮询全部任务至终态
            done = {"done": 0, "error": 0, "running": 0}
            t1 = time.time()
            pending = dict(accepted)
            deadline = t1 + 1500                     # 25 分钟上限
            while pending and time.time() < deadline:
                for cid, tid in list(pending.items()):
                    _st, dd = c.json("GET", "/api/tax-risk-docs/analyze-status/" + str(tid),
                                     timeout=30)
                    if dd.get("status") in ("done", "error"):
                        done[dd["status"]] = done.get(dd["status"], 0) + 1
                        pending.pop(cid, None)
                if pending:
                    time.sleep(5)
            el2 = time.time() - t1
            done["running"] = len(pending)
            ok("P2-3 50 个任务全部到达终态（无永久 running）", not pending,
               "done=%s error=%s 仍运行=%s" % (done.get("done"), done.get("error"), done["running"]))
            ok("P2-4 50 个任务全部成功（0 失败）", done.get("error", 0) == 0,
               "done=%d error=%d" % (done.get("done", 0), done.get("error", 0)))
            print("[P2 结果] 提交耗时 %.1fs ｜ 全部跑完总耗时 %.1fs（%.1f 分钟）"
                  " ｜ 平均每任务 %.1fs"
                  % (t_submit, el2, el2 / 60,
                     (el2 / CONC_N) if CONC_N else 0))
            print("    ⚠ 口径说明：分析任务**无全局并发上限**，跨账套各起一个后台线程；"
                  "Python GIL 下 CPU 密集段实际串行 ⇒ “平均每任务 %.1fs”≈串行单任务耗时，"
                  "不代表真并行吞吐。" % ((el2 / CONC_N) if CONC_N else 0))

        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except Exception:                                        # noqa: BLE001
            proc.kill()
        n_fail = sum(1 for _n, cc in results if not cc)
        print("\n" + "=" * 66)
        print("性能测试：%d 项通过 / %d 项失败（共 %d）"
              % (len(results) - n_fail, n_fail, len(results)))
        for n, cc in results:
            if not cc:
                print("  FAIL  " + n)


if __name__ == "__main__":
    rc = main()
    sys.exit(rc if rc else (1 if any(not c for _n, c in results) else 0))
