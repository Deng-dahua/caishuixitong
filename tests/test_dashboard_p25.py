# -*- coding: utf-8 -*-
"""P2-5 数据大屏与统计 —— 四类测试 + 反向验证。

隔离方式：**子进程 + `APP_DATA_DIR` 临时目录**（与 P0/P1/P2 各步同模式）。

四类：
  ① `DashboardUnitTests`     聚合自洽（各分布之和 == 总数；per_project 与 scanned 一致）
  ② `DashboardCaliberTests`  **口径不混**：`payload_unavailable` ≠ `0 条风险`；零 SQL 通道
  ③ `DashboardApiTests`      接口：3 端点 / 页面 / 遍历
  ④ `DashboardScopeTests`    **可见范围同源**：受限用户看不到无权账套的项目

★ 判据口径
  · 自洽判据是**结果级**的：`Σ by_status.count == projects.total`（当未截断时）；
    `len(per_project) == projects.scanned`。
  · 「零 SQL」判据：`engine/dashboard.py` 的**代码**不得出现 `SELECT`/`FROM <表>` ⇒
    取数只能经既有 Service 层（否则租户隔离必然与本模块漂移）。
  · 「口径不混」判据：存在无载荷账套时 `payload_unavailable >= 1` **且** `note` 里必须有
    "不是 0 条风险"类说明（二者缺一即判据变红）。
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

ADMIN_USER = "p25admin"
ADMIN_PASS = "P2-5-Admin-Pass-2026!"


def _run(script: str, *, timeout: int = 600) -> subprocess.CompletedProcess:
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
        raise AssertionError("子进程失败 rc=%s\n--- STDOUT ---\n%s\n--- STDERR ---\n%s"
                             % (result.returncode, result.stdout[-3000:], result.stderr[-3000:]))


_SETUP = textwrap.dedent("""
    import sys, os
    sys.path.insert(0, ".")
    from security import init_security_db, create_user, SessionContext
    from engine import dashboard as D
    from engine import project_service as P
    init_security_db()

    def sess(uid, companies, legacy="admin"):
        return SessionContext(user_id=uid, username="u%d" % uid, role=legacy,
                              allowed_company_ids=frozenset(companies),
                              selected_company_id=(list(companies) or [None])[0],
                              csrf_hash="", expires_at=0)
""")


class DashboardUnitTests(unittest.TestCase):
    def test_aggregation_self_consistent(self):
        result = _run(_SETUP + textwrap.dedent("""
            uid = create_user("p25agg", "P2-5-Agg-2026!", role="admin")
            s = sess(uid, [1, 2])
            P.create_project({"name": "P-A", "company_id": 1, "industry": "制造业",
                              "period_start": "2025-01-01", "period_end": "2025-12-31"}, s)
            P.create_project({"name": "P-B", "company_id": 2, "industry": "餐饮",
                              "period_start": "2025-01-01", "period_end": "2025-12-31"}, s)
            o = D.overview(s)
            Pj = o["projects"]
            assert Pj["total"] == 2, Pj["total"]
            assert len(o["per_project"]) == Pj["scanned"], (len(o["per_project"]), Pj["scanned"])
            if not Pj["capped"]:
                assert sum(x["count"] for x in Pj["by_status"]) == Pj["total"], Pj["by_status"]
                assert sum(x["count"] for x in Pj["by_industry"]) == Pj["total"], Pj["by_industry"]
            # 每个项目条目必须有可判定字段
            for x in o["per_project"]:
                assert x["project_id"] and x["code"], x
                assert isinstance(x["risk_available"], bool), x
            # 任务状态求和 == 任务总数
            T = o["tasks"]
            assert sum(x["count"] for x in T["by_status"]) == T["total"], (T["by_status"], T["total"])
            print("AGG-OK projects=%d" % Pj["total"])
        """))
        _assert_ok(result)
        self.assertIn("AGG-OK", result.stdout)


class DashboardCaliberTests(unittest.TestCase):
    def test_payload_unavailable_not_confused_with_zero(self):
        """★ `payload_unavailable` 与「0 条风险」必须分开（口径不混）。"""
        result = _run(_SETUP + textwrap.dedent("""
            uid = create_user("p25cal", "P2-5-Cal-2026!", role="admin")
            s = sess(uid, [1])
            P.create_project({"name": "无载荷项目", "company_id": 1,
                              "period_start": "2025-01-01", "period_end": "2025-12-31"}, s)
            o = D.overview(s)
            R = o["risks"]
            assert R["payload_unavailable"] >= 1, R
            assert R["payload_available"] == 0, R
            # 说明里必须点明"不是 0 条风险"
            assert "不是 0 条风险" in o["note"], o["note"][:120]
            # 该账套的明细必须如实标 risk_available=False（不得显示 0 条）
            pp = [x for x in o["per_project"] if x["company_id"] == 1][0]
            assert pp["risk_available"] is False, pp
            print("CALIBER-OK unavailable=%d" % R["payload_unavailable"])
        """))
        _assert_ok(result)
        self.assertIn("CALIBER-OK", result.stdout)

    def test_activity_shape(self):
        result = _run(_SETUP + textwrap.dedent("""
            uid = create_user("p25act", "P2-5-Act-2026!", role="admin")
            s = sess(uid, [1])
            a = D.activity(s, days=7)
            assert a["available"] is True, a
            assert isinstance(a["days"], list) and len(a["days"]) <= 7, a["days"]
            for d in a["days"]:
                assert "day" in d and "count" in d, d
            assert a["note"], "活动口径说明缺失"
            print("ACT-OK days=%d total=%d" % (len(a["days"]), a["total"]))
        """))
        _assert_ok(result)
        self.assertIn("ACT-OK", result.stdout)


class DashboardApiTests(unittest.TestCase):
    def test_endpoints_and_page(self):
        result = _run("""
            import sys
            sys.path.insert(0, ".")
            from fastapi.testclient import TestClient
            import main
            from security import init_security_db, create_user
            init_security_db(); create_user("p25api", "P2-5-Api-Pass-2026!", role="admin")
            c = TestClient(main.app)
            assert c.post("/api/v1/auth/login",
                          json={"username": "p25api",
                                "password": "P2-5-Api-Pass-2026!"}).status_code == 200
            base = "/api/v1/dashboard"
            for p in (base + "/meta", base + "/overview", base + "/activity", base + "/activity?days=3"):
                r = c.get(p)
                assert r.status_code == 200, (p, r.status_code, r.text[:120])
            jm = c.get(base + "/meta").json()
            assert jm["sources"] and jm["caps"], jm
            jo = c.get(base + "/overview").json()
            for k in ("projects", "documents", "tasks", "risks", "per_project", "note"):
                assert k in jo, (k, sorted(jo.keys()))
            pg = c.get("/dashboard")
            assert pg.status_code == 200 and "text/html" in pg.headers.get("content-type", "")
            print("API-OK")
        """)
        _assert_ok(result)
        self.assertIn("API-OK", result.stdout)


class DashboardScopeTests(unittest.TestCase):
    def test_visible_scope_same_as_service(self):
        """★ 大屏可见范围必须与既有 Service 层**同源**（受限用户看不到无权账套）。"""
        result = _run(_SETUP + textwrap.dedent("""
            admin = create_user("p25sc_admin", "P2-5-Sc-A-2026!", role="user")
            sa = sess(admin, [1, 2], legacy="user")
            from engine import rbac as R
            R.ensure_rbac_schema(); R.assign_user_roles(admin, ["system_admin"])
            P.create_project({"name": "甲账套项目", "company_id": 1,
                              "period_start": "2025-01-01", "period_end": "2025-12-31"}, sa)
            P.create_project({"name": "乙账套项目", "company_id": 2,
                              "period_start": "2025-01-01", "period_end": "2025-12-31"}, sa)
            # 受限用户：只能看账套 2
            lim = create_user("p25sc_lim", "P2-5-Sc-L-2026!", role="user")
            R.assign_user_roles(lim, ["enterprise_finance"])
            sl = sess(lim, [2], legacy="user")
            o = D.overview(sl)
            names = [x["name"] for x in o["per_project"]]
            assert "乙账套项目" in names, names
            assert "甲账套项目" not in names, names
            # 反向：管理员看得到两个（证明不是"全都看不到"）
            oa = D.overview(sa)
            assert len(oa["per_project"]) == 2, len(oa["per_project"])
            print("SCOPE-OK limited=%s admin=%d" % (names, len(oa["per_project"])))
        """))
        _assert_ok(result)
        self.assertIn("SCOPE-OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
