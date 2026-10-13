# -*- coding: utf-8 -*-
"""P0-4 一键稽查分析任务 —— 五类测试（单元 / 集成 / 并发 / 重试 / 进度与取消）+ 反向验证。

隔离方式：**子进程 + `APP_DATA_DIR` 临时目录**（与 `tests/test_project_api.py`、
`tests/test_document_api.py`、`tests/test_extract_api.py` 同一模式）—— 走**真实链路**
（认证中间件 / 真实 SQLite / 真实作业流水 / 真实留痕），但数据落临时目录 ⇒ 不污染真实库。

五类（任务书要求）：
  ① `AnalysisTaskUnitTests`        单元测试：任务状态机 + 8 步映射（含单调性）
  ② `AnalysisTaskIntegrationTests` 集成测试：发起 → 进度 → 取消 → 终态 → 审计 → 重试
  ③ `AnalysisTaskConcurrencyTests` 并发任务测试：同账套并发闸门 / 不同账套各自成作业
  ④ `AnalysisTaskRetryTests`       失败重试测试：仅失败/已取消可重试
  ⑤ `AnalysisTaskProgressTests`    进度上报测试：状态/进度/当前步骤/8 步清单
  另：`AnalysisTaskReverseVerification` **反向验证**（判据必须真的在起作用）

★ 反向验证不靠"看起来对"：把 `_task_status` 的**终局优先**改成"取消优先" ⇒
  "已完成的作业点取消后仍为 SUCCESS"这条断言**必须变红**（子进程内实测，非纸面声明）。
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

ADMIN_USER = "integrationadmin"
ADMIN_PASS = "Integration-Test-2026!"

_BOOT = """
    import os, io, time
    from fastapi.testclient import TestClient
    from main import app

    BASE = "/api/v1"

    def _login(c, user=%(user)r, pwd=%(pwd)r):
        r = c.post("/api/auth/login", json={"username": user, "password": pwd})
        assert r.status_code == 200, r.text
        return {"X-CSRF-Token": c.cookies.get("csrf_token")}

    def _company(c, h, name, uscc):
        r = c.post("/api/companies", headers=h, json={"name": name, "uscc": uscc})
        assert r.status_code in (200, 201), r.text
        cid = r.json()["id"]
        c.post("/api/auth/select-company", headers=h, json={"company_id": cid})
        return cid

    def _project(c, h, cid, name):
        r = c.post(BASE + "/projects", headers=h, json={"name": name, "company_id": cid})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def _xlsx():
        import openpyxl
        wb = openpyxl.Workbook(); ws = wb.active
        ws.append(["科目编码", "科目名称", "期初借方", "期初贷方", "本期借方", "本期贷方",
                   "期末借方", "期末贷方"])
        ws.append(["1001", "库存现金", 1000, 0, 500, 200, 1300, 0])
        ws.append(["6001", "主营业务收入", 0, 0, 0, 80000, 0, 80000])
        b = io.BytesIO(); wb.save(b)
        return b.getvalue()

    def _upload(c, h, pid):
        r = c.post(BASE + "/projects/%%d/documents" %% pid, headers=h,
                   files=[("files", ("科目余额表2024.xlsx", _xlsx(),
                                     "application/octet-stream"))])
        assert r.status_code in (200, 201), r.text
        return r.json()["uploaded"][0]["id"]

    def _wait_terminal(c, jid, seconds=180):
        from engine.analysis_jobs import get_job
        for _ in range(seconds):
            time.sleep(1)
            j = get_job(jid)
            if j and j.get("is_terminal"):
                return j
        return None
""" % {"user": ADMIN_USER, "pwd": ADMIN_PASS}


def _run(script: str, *, timeout: int = 420, dedent: bool = True) -> subprocess.CompletedProcess:
    """在隔离的 `APP_DATA_DIR` 临时目录里跑一段脚本。

    `dedent=False`：脚本由调用方**自行分段去缩进**后传入。用于"公共前缀 `_BOOT` + 测试体"
    的拼接 —— 拼接后整体最小缩进为 0，再 `dedent` 不生效 ⇒ 后半段会保留缩进而顶层不可缩进
    （实测 `IndentationError`）。故拼接处必须**逐段 dedent**。
    """
    if dedent:
        script = textwrap.dedent(script)
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
        return subprocess.run([sys.executable, "-c", script],
                              cwd=ROOT, env=environment,
                              capture_output=True, text=True, timeout=timeout)


# --------------------------------------------------------------------------
# ① 单元测试：任务状态机 + 8 步映射
# --------------------------------------------------------------------------
class AnalysisTaskUnitTests(unittest.TestCase):
    """直接调 `engine.analysis_task`（不经过 HTTP、不跑引擎）。"""

    def test_state_machine_and_step_model(self):
        result = _run(
            """
            from engine import analysis_task as T

            # 1) 8 步：条数与 1 基编号
            assert T.step_count() == 8, T.step_count()
            assert T.step_of_no(1)["no"] == 1
            assert T.step_of_no(8)["no"] == 8
            # 越界**钳位**（不返回 None，避免前端空窗）
            assert T.step_of_no(0)["no"] == 1
            assert T.step_of_no(99)["no"] == 8
            for i in range(1, 9):
                s = T.step_of_no(i)
                assert s["key"] and s["name"] and s["desc"], s

            # 2) 5 状态与中文名一一对应
            assert T.TASK_STATUSES == ("PENDING", "RUNNING", "SUCCESS", "FAILED", "CANCELLED")
            for s in T.TASK_STATUSES:
                assert T.STATUS_CN.get(s), s
            assert set(T.TASK_TERMINAL) == {"SUCCESS", "FAILED", "CANCELLED"}
            assert set(T.RETRYABLE) == {"FAILED", "CANCELLED"}

            # 3) 引擎步骤 → 任务步号：**单调**（否则前端会跳步）
            seq = [T.ENGINE_STEP_TO_TASK[e] for e in T.ENGINE_REPORT_ORDER]
            assert seq == sorted(seq) and len(set(seq)) == len(seq), seq
            assert seq[0] == 2 and seq[-1] == 8, seq
            # 每个任务步都必须可达（不允许"死步"）
            reachable = set(T.ENGINE_STEP_TO_TASK.values())
            assert reachable == set(range(1, 9)), sorted(reachable)
            # 引擎 0 步（未开始）落在第 1 步
            assert T.ENGINE_STEP_TO_TASK[0] == 1

            # 4) 运行态 → 任务状态：覆盖引擎的**全部**运行态，且目标合法
            for rt in ("running", "done", "error", "blocked", "cancelled", "deleted"):
                assert rt in T.RUNTIME_TO_TASK, rt
                assert T.RUNTIME_TO_TASK[rt] in T.TASK_STATUSES, rt
            assert T.RUNTIME_TO_TASK["done"] == "SUCCESS"
            assert T.RUNTIME_TO_TASK["error"] == "FAILED"
            assert T.RUNTIME_TO_TASK["cancelled"] == "CANCELLED"

            # 5) 8 步清单：reached=4 且 RUNNING ⇒ 1-3 done / 4 active / 5-8 pending
            steps = T._build_steps(4, "RUNNING")
            assert [s["status"] for s in steps] == [
                "done", "done", "done", "active", "pending", "pending", "pending", "pending"], steps
            assert [s["status"] for s in T._build_steps(4, "SUCCESS")][:4] == [
                "done", "done", "done", "done"]
            f = [s["status"] for s in T._build_steps(4, "FAILED")]
            assert f[3] == "failed" and f[2] == "done", f
            c = [s["status"] for s in T._build_steps(4, "CANCELLED")]
            assert c[3] == "cancelled", c

            # 6) 状态判定：终局优先（已完成不得被"取消"覆盖）
            done_p = {"status": "done", "is_terminal": True}
            assert T._task_status(persisted=done_p, runtime={}, cancel_requested=False,
                                  timed_out=False) == "SUCCESS"
            assert T._task_status(persisted=done_p, runtime={}, cancel_requested=True,
                                  timed_out=False) == "SUCCESS", "终局被取消覆盖 ⇒ 与流水对不上"
            # 跑动中 + 取消旗标 ⇒ CANCELLED
            assert T._task_status(persisted=None, runtime={"status": "running"},
                                  cancel_requested=True, timed_out=False) == "CANCELLED"
            # 刚创建（进度 0、步骤 0）⇒ PENDING
            assert T._task_status(persisted=None,
                                  runtime={"status": "running", "progress": 0,
                                           "current_step": 0},
                                  cancel_requested=False, timed_out=False) == "PENDING"
            assert T._task_status(persisted=None,
                                  runtime={"status": "running", "progress": 7,
                                           "current_step": 3},
                                  cancel_requested=False, timed_out=False) == "RUNNING"
            # 落盘说在跑、内存无记录（重启后）⇒ 如实 RUNNING（由超时看门狗兜底）
            assert T._task_status(persisted={"status": "running", "is_terminal": False},
                                  runtime={}, cancel_requested=False,
                                  timed_out=False) == "RUNNING"

            # 7) 超时阈值：非法环境变量 ⇒ 回默认（**不静默当 0**）
            import os as _os
            _os.environ["ANALYSIS_JOB_TIMEOUT_SECONDS"] = "abc"
            assert T._timeout_seconds() == T.DEFAULT_TIMEOUT_SECONDS
            _os.environ["ANALYSIS_JOB_TIMEOUT_SECONDS"] = "0"
            assert T._timeout_seconds() == T.DEFAULT_TIMEOUT_SECONDS
            _os.environ["ANALYSIS_JOB_TIMEOUT_SECONDS"] = "12"
            assert T._timeout_seconds() == 12
            del _os.environ["ANALYSIS_JOB_TIMEOUT_SECONDS"]

            # 8) 字典（前端中文名的唯一来源）：不得缺项
            m = T.metadata()
            assert len(m["steps"]) == 8, m["steps"]
            assert len(m["statuses"]) == 5, m["statuses"]
            assert m["timeout_seconds"] > 0
            assert m["cancel_semantics"], m
            assert "project" in [t["value"] for t in m["triggers"]], m["triggers"]

            # 9) 项目↔作业链接：append-only 往返 + 同 id 最后一次胜出
            T.register_link("job-a", 11)
            T.register_link("job-b", 11, retry_of="job-a")
            T.register_link("job-a", 12)
            assert T.link_of("job-a")["project_id"] == 12, T.link_of("job-a")
            assert T.link_of("job-b")["retry_of"] == "job-a"
            assert sorted(x["job_id"] for x in T.jobs_of_project(11)) == ["job-b"]
            assert sorted(x["job_id"] for x in T.jobs_of_project(12)) == ["job-a"]

            print("ANALYSIS TASK UNIT TESTS PASSED")
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        self.assertIn("ANALYSIS TASK UNIT TESTS PASSED", result.stdout)


# --------------------------------------------------------------------------
# ② 集成测试：发起 → 进度 → 取消 → 终态 → 审计 → 重试
# --------------------------------------------------------------------------
class AnalysisTaskIntegrationTests(unittest.TestCase):
    def test_full_chain_launch_cancel_audit_retry(self):
        result = _run(
            textwrap.dedent(_BOOT) + textwrap.dedent("""
            with TestClient(app) as c:
                h = _login(c)
                cid = _company(c, h, "集成企业", "91440300MA5IT00001")
                pid = _project(c, h, cid, "集成项目")
                _upload(c, h, pid)

                # 1) 发起
                r = c.post(BASE + "/projects/%d/analysis-jobs" % pid, headers=h, json={})
                assert r.status_code == 201, r.text
                body = r.json()
                jid = body["job_id"]
                assert body["ok"] and jid, body
                assert body["status"] == "PENDING", body
                pf = body["preflight"]
                assert pf["ok"] and pf["total"] == 1, pf
                assert "资料" in pf["message"], pf

                # 2) 详情：状态/进度/步骤 齐备
                g = c.get(BASE + "/analysis-jobs/%s" % jid).json()
                assert g["job_id"] == jid and g["project_id"] == pid, g
                assert g["status"] in ("PENDING", "RUNNING"), g["status"]
                assert len(g["steps"]) == 8, g["steps"]
                assert 1 <= g["current_step"] <= 8, g
                assert g["current_step_name"], g
                assert g["timeout_seconds"] > 0
                assert g["trigger"] == "project" and g["trigger_cn"] == "项目发起", g

                # 3) 历史（按项目）
                hist = c.get(BASE + "/projects/%d/analysis-jobs" % pid).json()
                assert hist["total"] == 1 and hist["jobs"][0]["job_id"] == jid, hist

                # 4) 取消
                cc = c.post(BASE + "/analysis-jobs/%s/cancel" % jid, headers=h)
                assert cc.status_code == 200, cc.text
                assert cc.json()["status"] == "CANCELLED", cc.json()
                assert cc.json()["can_retry"] is True, cc.json()

                # 5) 等引擎线程收尾 ⇒ 终态必须落盘为 cancelled（不是 done）
                j = _wait_terminal(c, jid)
                assert j is not None, "180s 内未收尾"
                assert j["status"] == "cancelled", j
                g2 = c.get(BASE + "/analysis-jobs/%s" % jid).json()
                assert g2["status"] == "CANCELLED", g2
                assert g2["cancel_pending"] is False, g2
                assert g2["progress"] < 100, g2   # 不假装跑完
                assert "已取消" in g2["message"], g2["message"]

                # 6) 幂等取消：不覆盖既成事实
                cc2 = c.post(BASE + "/analysis-jobs/%s/cancel" % jid, headers=h)
                assert cc2.json()["cancel_accepted"] is False, cc2.json()
                assert cc2.json()["reason"], cc2.json()

                # 7) 审计：起点 + 取消 + 终态 都有动作（且中文名可读）
                import sqlite3
                from runtime_storage import DATA_DIR
                from engine.audit_trail import ACTION_CN, ACTIONS
                conn = sqlite3.connect(os.path.join(DATA_DIR, "accounting.db"))
                acts = {r[0] for r in conn.execute("select distinct action from audit_logs")}
                for want in ("analysis.start", "job.cancel", "job.finished"):
                    assert want in acts, (want, sorted(acts))
                    assert ACTION_CN.get(want), want
                    assert want in ACTIONS, want

                # 8) 重试（已取消 ⇒ 允许）
                rr = c.post(BASE + "/analysis-jobs/%s/retry" % jid, headers=h)
                assert rr.status_code == 200, rr.text
                assert rr.json()["job_id"] != jid, rr.json()
                assert rr.json()["retry_of"] == jid, rr.json()
                assert c.get(BASE + "/projects/%d/analysis-jobs" % pid).json()["total"] == 2

                # 9) 404 语义
                assert c.get(BASE + "/analysis-jobs/nosuchjob").status_code == 404

                print("ANALYSIS TASK INTEGRATION TESTS PASSED")
            """), dedent=False
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        self.assertIn("ANALYSIS TASK INTEGRATION TESTS PASSED", result.stdout)

    def test_preflight_blocks_empty_project(self):
        """资料完整性闸门：项目下**没有资料** ⇒ 400，不发车（**不静默跑空**）。"""
        result = _run(
            textwrap.dedent(_BOOT) + textwrap.dedent("""
            with TestClient(app) as c:
                h = _login(c)
                cid = _company(c, h, "空资料企业", "91440300MA5EP00001")
                pid = _project(c, h, cid, "空资料项目")
                r = c.post(BASE + "/projects/%d/analysis-jobs" % pid, headers=h, json={})
                assert r.status_code == 400, r.text
                assert "资料" in r.json()["detail"], r.json()
                # 且**不得**留下任何作业（未发车就没作业）
                assert c.get(BASE + "/projects/%d/analysis-jobs" % pid).json()["total"] == 0
                print("ANALYSIS PREFLIGHT GATE TESTS PASSED")
            """), dedent=False
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        self.assertIn("ANALYSIS PREFLIGHT GATE TESTS PASSED", result.stdout)


# --------------------------------------------------------------------------
# ③ 并发任务测试
# --------------------------------------------------------------------------
class AnalysisTaskConcurrencyTests(unittest.TestCase):
    def test_same_company_reuses_and_different_company_isolated(self):
        result = _run(
            textwrap.dedent(_BOOT) + textwrap.dedent("""
            with TestClient(app) as c:
                h = _login(c)
                cid = _company(c, h, "并发企业甲", "91440300MA5CC00011")
                p1 = _project(c, h, cid, "并发项目1")
                p2 = _project(c, h, cid, "并发项目2")
                _upload(c, h, p1)
                _upload(c, h, p2)   # 两个项目都要有资料（否则先被"资料完整性"闸门 400 挡住）

                r1 = c.post(BASE + "/projects/%d/analysis-jobs" % p1, headers=h, json={})
                assert r1.status_code == 201, r1.text
                jid1 = r1.json()["job_id"]

                # 同一账套**再发起** ⇒ 并发闸门：复用现有作业（不新建、不并跑）
                r2 = c.post(BASE + "/projects/%d/analysis-jobs" % p2, headers=h, json={})
                assert r2.status_code == 201, r2.text
                assert r2.json()["job_id"] == jid1, (r2.json(), jid1)
                assert r2.json()["reused"] is True, r2.json()
                # 复用的**不写链接**（它不是一次新作业）⇒ 项目2 历史仍为 0
                assert c.get(BASE + "/projects/%d/analysis-jobs" % p2).json()["total"] == 0

                # 另一个账套：各自成作业（互不干扰）
                cid2 = _company(c, h, "并发企业乙", "91440300MA5CC00012")
                p3 = _project(c, h, cid2, "并发项目3")
                _upload(c, h, p3)
                r3 = c.post(BASE + "/projects/%d/analysis-jobs" % p3, headers=h, json={})
                assert r3.status_code == 201, r3.text
                assert r3.json()["job_id"] != jid1, r3.json()
                assert r3.json()["reused"] is False

                # 清理：两个都取消
                for jid in (jid1, r3.json()["job_id"]):
                    c.post(BASE + "/analysis-jobs/%s/cancel" % jid, headers=h)
                print("ANALYSIS TASK CONCURRENCY TESTS PASSED")
            """), dedent=False
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        self.assertIn("ANALYSIS TASK CONCURRENCY TESTS PASSED", result.stdout)


# --------------------------------------------------------------------------
# ④ 失败重试测试（不跑引擎：直接构造终态作业，快且稳）
# --------------------------------------------------------------------------
class AnalysisTaskRetryTests(unittest.TestCase):
    def test_retry_only_for_failed_or_cancelled(self):
        result = _run(
            """
            from security import SessionContext
            from engine import analysis_task as T
            from engine import project_service as PSVC
            from engine.analysis_jobs import job_started, job_finished, get_job

            sess = SessionContext(user_id=7, username="retry", role="admin",
                                  allowed_company_ids=frozenset({1}),
                                  selected_company_id=1, csrf_hash="", expires_at=0)
            pid = PSVC.create_project({"name": "重试企业", "company_id": 1}, sess)["id"]

            def _mk(jid, status):
                job_started(1, jid, started_by=7, trigger="project")
                job_finished(jid, status, company_id=1, error_message="构造用")
                T.register_link(jid, pid)

            # 1) 已成功 ⇒ 不允许重试（400 且说明原因）
            _mk("donejob000001", "done")
            g = T.get("donejob000001", sess)
            assert g["status"] == "SUCCESS", g
            assert g["can_retry"] is False, g
            try:
                T.retry("donejob000001", sess)
                raise AssertionError("已完成作业竟然可重试")
            except T.AnalysisTaskError as e:
                assert e.status == 400, e.status
                assert "重试" in e.message, e.message

            # 2) 已失败 ⇒ 允许重试（且新作业的 retry_of 指回原作业）
            _mk("failjob000001", "error")
            gf = T.get("failjob000001", sess)
            assert gf["status"] == "FAILED", gf
            assert gf["error"], "失败作业必须带原因（不许空）"
            assert gf["can_retry"] is True, gf

            # 3) 已取消 ⇒ 允许重试
            _mk("canjob0000001", "cancelled")
            gc = T.get("canjob0000001", sess)
            assert gc["status"] == "CANCELLED", gc
            assert gc["can_retry"] is True, gc

            # 4) 拦截图（blocked）⇒ 归 FAILED（对用户即"没出报告"）
            _mk("blkjob0000001", "blocked")
            gb = T.get("blkjob0000001", sess)
            assert gb["status"] == "FAILED", gb

            # 5) 取消**已完成**的作业 ⇒ 不覆盖既成事实（与流水一致）
            out = T.cancel("donejob000001", sess)
            assert out["status"] == "SUCCESS", out
            assert out["cancel_accepted"] is False, out
            assert get_job("donejob000001")["status"] == "done", get_job("donejob000001")

            print("ANALYSIS TASK RETRY TESTS PASSED")
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        self.assertIn("ANALYSIS TASK RETRY TESTS PASSED", result.stdout)


# --------------------------------------------------------------------------
# ⑤ 进度上报测试（含取消旗标与超时）
# --------------------------------------------------------------------------
class AnalysisTaskProgressTests(unittest.TestCase):
    def test_progress_and_timeout_reporting(self):
        result = _run(
            """
            from security import SessionContext
            from engine import analysis_task as T
            from engine import project_service as PSVC
            from engine.analysis_jobs import job_started, job_finished
            import os, time

            sess = SessionContext(user_id=8, username="prog", role="admin",
                                  allowed_company_ids=frozenset({1}),
                                  selected_company_id=1, csrf_hash="", expires_at=0)
            pid = PSVC.create_project({"name": "进度企业", "company_id": 1}, sess)["id"]

            # 1) 引擎各上报步骤 ⇒ 任务步号映射正确且单调
            pairs = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (6, 6), (5, 7), (7, 8)]
            import main as _m
            with _m._analysis_lock:
                _m._analysis_tasks["prog000000001"] = {
                    "status": "running", "progress": 0, "message": "准备中...",
                    "result": None, "error": None, "company_id": 1, "user_id": 8,
                    "started_at": time.time(), "current_step": 0, "current_module": "",
                }
            T.register_link("prog000000001", pid)
            job_started(1, "prog000000001", started_by=8, trigger="project")
            seen = []
            for eng_step, _task_step in pairs:
                with _m._analysis_lock:
                    _m._analysis_tasks["prog000000001"]["current_step"] = eng_step
                    _m._analysis_tasks["prog000000001"]["progress"] = 40 + eng_step
                g = T.get("prog000000001", sess)
                seen.append((eng_step, g["current_step"], g["current_step_name"]))
                assert g["current_step"] == _task_step, (eng_step, g["current_step"])
            assert [x[1] for x in seen] == [1, 2, 3, 4, 5, 6, 7, 8], seen
            # 8 步清单：末轮引擎步=7 ⇒ 任务步=8（前 7 步 done，第 8 步 active）
            g = T.get("prog000000001", sess)
            assert [s["status"] for s in g["steps"]] == [
                "done", "done", "done", "done", "done", "done", "done", "active"], g["steps"]

            # 2) 超时：把阈值压到 1 秒 ⇒ 必须报 timed_out 且请求中止（结果不予采用）
            os.environ["ANALYSIS_JOB_TIMEOUT_SECONDS"] = "1"
            with _m._analysis_lock:
                _m._analysis_tasks["prog000000001"]["started_at"] = time.time() - 5
            g2 = T.get("prog000000001", sess)
            assert g2["timed_out"] is True, g2
            assert g2["status"] == "CANCELLED", g2
            assert "超时" in g2["error"], g2["error"]
            with _m._analysis_lock:
                assert _m._analysis_tasks["prog000000001"].get("cancel_requested") is True
            del os.environ["ANALYSIS_JOB_TIMEOUT_SECONDS"]

            # 3) 作业**已终局**后，超时不再生效（已完成就是已完成，不得被超时改写）
            job_finished("prog000000001", "done", company_id=1)
            with _m._analysis_lock:
                _m._analysis_tasks["prog000000001"]["status"] = "done"
            os.environ["ANALYSIS_JOB_TIMEOUT_SECONDS"] = "1"
            g3 = T.get("prog000000001", sess)
            assert g3["timed_out"] is False, g3
            # ★ 终局优先：即便取消旗标还在，流水已记 done ⇒ 对用户就是"已完成"
            #   （否则 API 的"已取消"会对不上流水里的 done —— 两种事实一个名字）
            assert g3["status"] == "SUCCESS", g3
            del os.environ["ANALYSIS_JOB_TIMEOUT_SECONDS"]
            print("ANALYSIS TASK PROGRESS TESTS PASSED")
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        self.assertIn("ANALYSIS TASK PROGRESS TESTS PASSED", result.stdout)


# --------------------------------------------------------------------------
# 反向验证：判据必须真的在起作用
# --------------------------------------------------------------------------
class AnalysisTaskReverseVerification(unittest.TestCase):
    def test_reverse_terminal_priority_is_real(self):
        """★ 反向验证：「终局优先于取消」这条判据**真的在起作用**。

        做法：把 `_task_status` 的终局判定临时破坏（让取消/超时无视终局），
        同一断言（"已完成作业点取消后仍为 SUCCESS"）**必须变红**；还原后必须恢复绿。
        """
        result = _run(
            """
            from security import SessionContext
            from engine import analysis_task as T
            from engine.analysis_jobs import job_started, job_finished

            sess = SessionContext(user_id=9, username="rv", role="admin",
                                  allowed_company_ids=frozenset({1}),
                                  selected_company_id=1, csrf_hash="", expires_at=0)
            job_started(1, "rvjob00000001", started_by=9, trigger="project")
            job_finished("rvjob00000001", "done", company_id=1)

            def _probe():
                return T.get("rvjob00000001", sess)["status"]

            assert _probe() == "SUCCESS", _probe()

            # 注入缺陷：取消/超时**优先于终局**（即丢掉"终局优先"这条判据）
            orig = T._is_terminal
            try:
                T._is_terminal = lambda p, r: False        # 永远"未终局"
                try:
                    T.get("rvjob00000001", sess).get("status")
                except Exception:
                    pass
                # 置取消旗标后再读 ⇒ 若判据失效，会变成 CANCELLED（= 变红）
                import main as _m
                with _m._analysis_lock:
                    _m._analysis_tasks["rvjob00000001"] = {
                        "status": "done", "progress": 100, "message": "分析完成",
                        "result": None, "error": None, "company_id": 1, "user_id": 9,
                        "started_at": 1.0, "current_step": 7, "current_module": "",
                        "cancel_requested": True,
                    }
                bad = T.get("rvjob00000001", sess)["status"]
                assert bad == "CANCELLED", ("判据未被破坏？实际=%s" % bad)
            finally:
                T._is_terminal = orig
                import main as _m
                with _m._analysis_lock:
                    _m._analysis_tasks.pop("rvjob00000001", None)

            # 还原后：同一场景必须仍是 SUCCESS（终局优先恢复生效）
            job_started(1, "rvjob00000002", started_by=9, trigger="project")
            job_finished("rvjob00000002", "done", company_id=1)
            import main as _m
            with _m._analysis_lock:
                _m._analysis_tasks["rvjob00000002"] = {
                    "status": "done", "progress": 100, "message": "分析完成",
                    "result": None, "error": None, "company_id": 1, "user_id": 9,
                    "started_at": 1.0, "current_step": 7, "current_module": "",
                    "cancel_requested": True,
                }
            good = T.get("rvjob00000002", sess)["status"]
            assert good == "SUCCESS", ("还原后仍未恢复：%s" % good)

            print("ANALYSIS TASK REVERSE VERIFICATION PASSED")
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        self.assertIn("ANALYSIS TASK REVERSE VERIFICATION PASSED", result.stdout)


if __name__ == "__main__":
    unittest.main()
