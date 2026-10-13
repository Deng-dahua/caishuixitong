# -*- coding: utf-8 -*-
"""P1-6 规则版本管理 —— 单元测试 + 集成测试 + 反向判据。

★ 判据口径
  · **未发布时与基线一致**：台账为空 ⇒ `rule_set_version()` == config 值
    （保证既有报告溯源不受影响）。
  · **不猜**：版本号格式非法 / 重复发布 / 回滚目标不在历史 ⇒ 400 并说明原因。
  · **无快照 ≠ 两版相同**：`diff` 遇到缺快照 ⇒ `comparable=False` + 原因，
    **不返回空差异**（空差异会被误读为"完全相同"）。
  · **回滚可逆**：发布 → 回滚后，生效版本回到原版本。
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

ADMIN_USER = "p16admin"
ADMIN_PASS = "P1-6-Admin-Pass-2026!"


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


class RuleVersionUnitTests(unittest.TestCase):
    def test_baseline_then_publish_then_rollback(self):
        result = _run("""
            import sys
            sys.path.insert(0, ".")
            from engine import rule_versions as RV
            from engine import rule_version_admin as A
            from security import SessionContext
            s = SessionContext(user_id=1, username="p16u", role="admin",
                               allowed_company_ids=frozenset(), selected_company_id=None,
                               csrf_hash="", expires_at=0)

            base = str(RV.load_versions().get("rule_set_version") or "")
            # ① 未发布 ⇒ 与基线**完全一致**（既有报告溯源不受影响）
            assert RV.published_version() == "", RV.published_version()
            assert A.current_version() == base, (A.current_version(), base)
            assert len(RV.registered_ids()) == 176, len(RV.registered_ids())

            # ② 发布 ⇒ 生效版本切换 + 快照落盘（逐条规则版本）
            r = A.publish("2099.01", s, note="单元测试发布")
            assert r["from_version"] == base and r["to_version"] == "2099.01", r
            assert r["rule_count"] == 176, r["rule_count"]
            assert A.current_version() == "2099.01", A.current_version()
            assert RV.rule_set_version() == "2099.01", "唯一判读点未生效"
            snap = A.snapshot_of("2099.01")
            assert snap and len(snap.get("rules") or {}) == 176, snap

            # ③ 差异：从"无快照的基线"到"有快照的新版本" ⇒ **不可比对**（不返回空差异）
            d0 = A.diff(base, "2099.01")
            assert d0["comparable"] is False and d0["reason"], d0
            assert d0["added"] == [] and "无快照" in d0["note"]

            # ④ 发布第二个版本 ⇒ 两版**都有快照**时可比对
            A.publish("2099.02", s, note="第二版")
            d1 = A.diff("2099.01", "2099.02")
            assert d1["comparable"] is True, d1
            assert d1["counts"]["from"] == 176 and d1["counts"]["to"] == 176, d1["counts"]
            assert d1["counts"]["changed"] == 0, d1["changed"]

            # ⑤ **反向**：手工把快照里一条规则的版本改掉 ⇒ diff 必须报"版本变更"
            sp = A._snapshot_path("2099.02")
            import json
            raw = json.loads(sp.read_text(encoding="utf-8"))
            k = sorted(raw["rules"].keys())[0]
            raw["rules"][k] = "9.9.9"
            sp.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            d2 = A.diff("2099.01", "2099.02")
            assert d2["counts"]["changed"] == 1, d2["counts"]
            assert d2["changed"][0]["rule_id"] == k, d2["changed"]
            assert d2["changed"][0]["to"] == "9.9.9", d2["changed"]

            # ⑥ 回滚 ⇒ 回到指定历史版本
            rb = A.rollback_version("2099.01", s, note="回滚")
            assert rb["to_version"] == "2099.01", rb
            assert A.current_version() == "2099.01", A.current_version()

            # ⑦ 清单：当前版本唯一标记；台账事件在清单里
            vs = A.list_versions()
            cur = [x for x in vs if x.get("is_current")]
            assert len(cur) == 1 and cur[0]["version"] == "2099.01", vs
            assert any(x.get("source") == "ledger" for x in vs), vs
            print("FLOW-OK base=%s" % base)
        """)
        _assert_ok(result)
        self.assertIn("FLOW-OK", result.stdout)

    def test_rejects_bad_input(self):
        result = _run("""
            import sys
            sys.path.insert(0, ".")
            from engine import rule_version_admin as A
            from security import SessionContext
            s = SessionContext(user_id=1, username="p16u2", role="admin",
                               allowed_company_ids=frozenset(), selected_company_id=None,
                               csrf_hash="", expires_at=0)

            def expect400(fn, *a, **k):
                try:
                    fn(*a, **k)
                except AssertionError:
                    raise
                except Exception as e:
                    assert e.__class__.__name__ == "RuleVersionError", e.__class__.__name__
                    assert int(e.status) == 400, e.status
                    return str(e.message)
                raise AssertionError("应当 400")

            for bad in ("2026", "26.1", "2026.13", "2026.00", "", None, "v2026.10"):
                expect400(A.publish, bad, s)
                expect400(A.rollback_version, bad, s)
            # 与当前生效版本相同 ⇒ 400（不是"发布成功"）
            cur = A.current_version()
            expect400(A.publish, cur, s)
            expect400(A.rollback_version, cur, s)
            # 回滚目标不在历史 ⇒ 400 且提示历史版本
            m = expect400(A.rollback_version, "2098.12", s)
            assert "历史" in m, m
            # 发布一个已在历史中的版本 ⇒ 400（发布必须用新版本号；改回请用回滚）
            A.publish("2097.01", s)
            A.rollback_version(cur, s)
            m2 = expect400(A.publish, "2097.01", s)
            assert "回滚" in m2, m2
            # diff 版本号非法 ⇒ 400
            expect400(A.diff, "bad", "2026.10")
            print("REJECT-OK")
        """)
        _assert_ok(result)
        self.assertIn("REJECT-OK", result.stdout)


class RuleVersionApiTests(unittest.TestCase):
    def test_endpoints_and_permission(self):
        result = _run("""
            import sys, os
            sys.path.insert(0, ".")
            from fastapi.testclient import TestClient
            import main
            from security import init_security_db, create_user
            from engine import rbac as R
            init_security_db(); R.ensure_rbac_schema()
            create_user("p16int", "P1-6-Int-Pass-2026!", role="admin")
            c = TestClient(main.app)
            assert c.post("/api/v1/auth/login",
                          json={"username": "p16int",
                                "password": "P1-6-Int-Pass-2026!"}).status_code == 200
            H = {"X-CSRF-Token": c.cookies.get("csrf_token")}

            m = c.get("/api/v1/rule-versions/meta")
            assert m.status_code == 200, m.text
            assert m.json()["current_version"], m.json()
            assert m.json()["registered_rule_count"] == 176, m.json()

            l = c.get("/api/v1/rule-versions")
            assert l.status_code == 200 and l.json()["total"] >= 1, l.text
            assert c.get("/api/v1/rule-versions/1999.01").status_code == 404
            assert c.get("/api/v1/rule-versions/2026.10").status_code == 200
            # diff 缺参数 ⇒ 422；非法版本 ⇒ 400
            assert c.get("/api/v1/rule-versions/diff?from=2026.10").status_code == 422
            assert c.get("/api/v1/rule-versions/diff?from=bad&to=2026.10").status_code == 400

            # 写：无 CSRF ⇒ 403；CSRF 但无权限 ⇒ 403
            assert c.post("/api/v1/rule-versions/publish",
                          json={"version": "2096.01"}).status_code == 403
            R.create_role("p16_nomanage", "P1-6 无版本管理权", ["report.view"])
            uid = create_user("p16ro", "P1-6-RO-Pass-2026!", role="user")
            R.assign_user_roles(uid, ["p16_nomanage"])
            c2 = TestClient(main.app)
            assert c2.post("/api/v1/auth/login",
                           json={"username": "p16ro",
                                 "password": "P1-6-RO-Pass-2026!"}).status_code == 200
            assert c2.get("/api/v1/rule-versions").status_code == 200, "读权限应放行"
            h2 = {"X-CSRF-Token": c2.cookies.get("csrf_token")}
            w = c2.post("/api/v1/rule-versions/publish", headers=h2,
                        json={"version": "2096.02"})
            assert w.status_code == 403, (w.status_code, w.text[:200])
            assert "ruleversion.manage" in (w.json().get("detail") or ""), w.json()

            # 管理员：发布 + 回滚 + 页面可达
            assert c.post("/api/v1/rule-versions/publish", headers=H,
                          json={"version": "2096.03", "note": "集成"}).status_code == 200
            assert c.get("/api/v1/rule-versions/meta").json()["current_version"] == "2096.03"
            assert c.post("/api/v1/rule-versions/rollback", headers=H,
                          json={"version": "2026.10"}).status_code == 200
            pg = c.get("/rule-versions")
            assert pg.status_code == 200 and "text/html" in pg.headers.get("content-type", "")
            print("INTEG-OK")
        """)
        _assert_ok(result)
        self.assertIn("INTEG-OK", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
