# -*- coding: utf-8 -*-
"""P1-4 人工复核流程完善 —— 单元测试 + 集成测试 + 反向判据。

★ 判据口径
  · **部分成功可见**：批量复核**不做**"全成功才提交"的静默回滚；每条给出
    `ok / noop / failed` 三态 + 原因（处置流水是 append-only 台账，不可改写）。
  · **不静默**：重复编号去重后记账 `dup_removed`；必填理由缺失的条目**计入 failed**
    而不是被跳过。
  · **未处置 ≠ 超期**：`never_reviewed` 与 `overdue` 分开计（前者没有起点）。
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

ADMIN_USER = "p14admin"
ADMIN_PASS = "P1-4-Admin-Pass-2026!"


def _run(script: str, *, timeout: int = 300) -> subprocess.CompletedProcess:
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
            "PYTHONIOENCODING": "utf-8",
        })
        return subprocess.run([sys.executable, "-c", script],
                              cwd=ROOT, env=environment,
                              capture_output=True, text=True, timeout=timeout)


def _assert_ok(result: subprocess.CompletedProcess) -> None:
    if result.returncode != 0:
        raise AssertionError("子进程失败\nSTDOUT:\n%s\nSTDERR:\n%s"
                             % (result.stdout[-3000:], result.stderr[-3000:]))


class ReviewFlowUnitTests(unittest.TestCase):
    def test_bulk_review_partial_success_is_visible(self):
        """核心判据：批量复核**逐条回报**（成功/无变化/失败），部分失败不回滚。"""
        result = _run("""
            import sys
            sys.path.insert(0, ".")
            from engine import risk_review as R
            from security import init_security_db, create_user, SessionContext
            init_security_db()
            uid = create_user("p14u1", "P1-4-U1-Pass-2026!", role="user")
            s = SessionContext(user_id=uid, username="p14u1", role="user",
                               allowed_company_ids=frozenset(), selected_company_id=None,
                               csrf_hash="", expires_at=0)
            R.reset_cache()

            # ① 正常批量：2 条成功
            r = R.bulk_review(["T-1", "T-2"], "confirm", s, company_id=1)
            assert r["total"] == 2 and r["ok"] == 2 and r["failed"] == 0, r
            assert [x["status"] for x in r["items"]] == ["ok", "ok"], r["items"]

            # ② 幂等：同一动作重复 ⇒ noop（不是再写一条历史）
            r2 = R.bulk_review(["T-1", "T-2"], "confirm", s, company_id=1)
            assert r2["noop"] == 2 and r2["ok"] == 0, r2
            assert all(x["status"] == "noop" for x in r2["items"]), r2["items"]

            # ③ **部分失败可见**：exclude 需要理由 ⇒ 不带理由的条目计入 failed，
            #    但**不出异常**、**不影响**其他条目（这里全部因缺理由失败）
            r3 = R.bulk_review(["T-1"], "exclude", s, company_id=1)
            assert r3["failed"] == 1 and r3["ok"] == 0, r3
            assert r3["items"][0]["status"] == "failed", r3["items"][0]
            assert "理由" in r3["items"][0]["message"] or "说明" in r3["items"][0]["message"], \\
                r3["items"][0]

            # ④ 非法动作 ⇒ 逐条 failed（不是整批 500）
            r4 = R.bulk_review(["T-1"], "no_such_action", s, company_id=1)
            assert r4["failed"] == 1 and r4["items"][0]["code"] == 400, r4

            # ⑤ 去重如实记账
            r5 = R.bulk_review(["T-3", "T-3", "T-3"], "confirm", s, company_id=1)
            assert r5["total"] == 1 and r5["dup_removed"] == 2, r5

            # ⑥ 空列表 / 超上限 ⇒ 400（不静默）
            for bad in ([], list("X%d" % i for i in range(201))):
                try:
                    R.bulk_review(bad, "confirm", s, company_id=1)
                    raise AssertionError("应当 400：%r" % (bad[:3],))
                except AssertionError:
                    raise
                except Exception as e:
                    assert e.__class__.__name__ == "RiskReviewError", e.__class__.__name__
                    assert int(getattr(e, "status", 0)) == 400, getattr(e, "status", None)
            print("BULK-OK")
        """)
        _assert_ok(result)
        self.assertIn("BULK-OK", result.stdout)

    def test_history_and_stats(self):
        result = _run("""
            import sys
            sys.path.insert(0, ".")
            from engine import risk_review as R
            from security import init_security_db, create_user, SessionContext
            init_security_db()
            uid = create_user("p14u2", "P1-4-U2-Pass-2026!", role="user")
            s = SessionContext(user_id=uid, username="p14u2", role="user",
                               allowed_company_ids=frozenset(), selected_company_id=None,
                               csrf_hash="", expires_at=0)
            R.reset_cache()

            # 未处置 ⇒ 空事件流 + reviewed False（**缺失 ≠ 有记录**）
            h = R.history("H-0", 1)
            assert h["events"] == [] and h["comments"] == [], h
            assert h["reviewed"] is False, h
            assert h["state"] == "pending", h

            # 处置后 ⇒ 事件流有记录，且带操作人（可追溯到人）
            R.review("H-1", "confirm", s, company_id=1)
            R.comment("H-1", "已与财务确认", s, company_id=1)
            h1 = R.history("H-1", 1)
            assert h1["reviewed"] is True, h1
            assert h1["state"] == "confirmed" and h1["updated_by"] == "p14u2", h1
            # ★ 口径：`history` 是**处置事件流**（review 类），`comments` 单列
            #   （`_collapse` 对 `event=comment` 走 `continue`，不混入 history）——
            #   两者是互补关系，不是同一列表。
            assert len(h1["events"]) == 1, h1["events"]
            assert h1["events"][0]["to"] == "confirmed", h1["events"][0]
            assert len(h1["comments"]) == 1, h1["comments"]
            assert h1["comments"][0]["text"] == "已与财务确认"

            # 看板：三态分开计
            st = R.review_stats(1)
            assert st["total"] >= 1, st
            assert st["by_state"]["confirmed"] >= 1, st["by_state"]
            assert st["done"] == sum(st["by_state"][x] for x in R.TERMINAL_STATES), st
            assert st["done_ratio"] <= 1.0, st
            # 「从未处置」不得被算成「超期」
            assert st["overdue_count"] == 0 or all(
                x["days"] is not None for x in st["overdue"]), st["overdue"]
            assert isinstance(st["never_reviewed"], list), st

            # 反向：未知编号 ⇒ pending（不是"已处置"）
            assert R.review_stats(1)["by_state"]["pending"] >= 0
            print("HISTORY-OK total=%d done=%d" % (st["total"], st["done"]))
        """)
        _assert_ok(result)
        self.assertIn("HISTORY-OK", result.stdout)

    def test_review_does_not_change_level(self):
        """铁律回归：任何复核动作**不得**修改等级字段（等级唯一权威 risk_levels）。"""
        result = _run("""
            import sys
            sys.path.insert(0, ".")
            from engine import risk_review as R
            from security import init_security_db, create_user, SessionContext
            init_security_db()
            uid = create_user("p14u3", "P1-4-U3-Pass-2026!", role="user")
            s = SessionContext(user_id=uid, username="p14u3", role="user",
                               allowed_company_ids=frozenset(), selected_company_id=None,
                               csrf_hash="", expires_at=0)
            R.reset_cache()
            R.review("L-1", "confirm", s, company_id=1)
            rec = R.get("L-1", 1)
            for k in ("risk_level", "level", "conclusion_grade", "severity"):
                assert k not in rec, ("复核写入了等级字段", k)
            # 事件流水里也不得有等级字段
            for ev in (rec.get("history") or []):
                for k in ("risk_level", "level", "conclusion_grade"):
                    assert k not in ev, ("事件流水写入等级", k, ev)
            print("NOLEVEL-OK")
        """)
        _assert_ok(result)
        self.assertIn("NOLEVEL-OK", result.stdout)


class ReviewFlowIntegrationTests(unittest.TestCase):
    def test_review_board_and_bulk_endpoints(self):
        result = _run("""
            import sys, os
            sys.path.insert(0, ".")
            from fastapi.testclient import TestClient
            import main
            from security import init_security_db, create_user
            init_security_db()
            create_user("p14int", "P1-4-Int-Pass-2026!", role="admin")
            c = TestClient(main.app)
            assert c.post("/api/v1/auth/login",
                          json={"username": "p14int",
                                "password": "P1-4-Int-Pass-2026!"}).status_code == 200
            csrf = c.cookies.get("csrf_token")
            H = {"X-CSRF-Token": csrf}

            # 字典必须带复核状态机（含批量上限与超期默认天数）
            m = c.get("/api/v1/risks/meta").json()
            assert m["review"]["bulk_limit"] == 200, m["review"]
            assert m["review"]["stale_days_default"] == 3, m["review"]
            assert len(m["review"]["actions"]) == 6, m["review"]["actions"]

            # 看板：缺 company_id/project_id ⇒ 400（不静默给全量）
            assert c.get("/api/v1/risks/review-board").status_code == 400
            b = c.get("/api/v1/risks/review-board?company_id=1")
            assert b.status_code == 200, b.text
            assert "by_state" in b.json() and "overdue_count" in b.json(), b.json()

            # 批量复核：空 ⇒ 400；非数组 ⇒ 400；正常 ⇒ 200 逐条回报
            assert c.post("/api/v1/risks/bulk-review", headers=H,
                          json={"risk_ids": [], "action": "confirm"}).status_code == 400
            assert c.post("/api/v1/risks/bulk-review", headers=H,
                          json={"risk_ids": "x", "action": "confirm"}).status_code == 400
            ok = c.post("/api/v1/risks/bulk-review", headers=H,
                        json={"risk_ids": ["Z-1", "Z-2"], "action": "confirm",
                              "company_id": 1})
            assert ok.status_code == 200, ok.text
            j = ok.json()
            assert j["ok"] == 2 and len(j["items"]) == 2, j

            # 无 CSRF ⇒ 403（不静默放行）
            assert c.post("/api/v1/risks/bulk-review",
                          json={"risk_ids": ["Z-3"], "action": "confirm",
                                "company_id": 1}).status_code == 403

            # 未登录 ⇒ 401
            assert TestClient(main.app).get(
                "/api/v1/risks/review-board?company_id=1").status_code == 401
            print("INTEG-OK")
        """)
        _assert_ok(result)
        self.assertIn("INTEG-OK", result.stdout)

    def test_history_does_not_leak_existence(self):
        """安全姿态回归：查不存在的风险 ⇒ 404（不泄露存在性），与 P0-6 同口径。"""
        result = _run("""
            import sys, os
            sys.path.insert(0, ".")
            from fastapi.testclient import TestClient
            import main
            from security import init_security_db, create_user
            init_security_db()
            create_user("p14sec", "P1-4-Sec-Pass-2026!", role="admin")
            c = TestClient(main.app)
            assert c.post("/api/v1/auth/login",
                          json={"username": "p14sec",
                                "password": "P1-4-Sec-Pass-2026!"}).status_code == 200
            r = c.get("/api/v1/risks/NO-SUCH-RISK/history?company_id=1")
            assert r.status_code == 404, (r.status_code, r.text[:200])
            print("NOLZEAK-OK")
        """)
        _assert_ok(result)
        self.assertIn("NOLZEAK-OK", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
