# -*- coding: utf-8 -*-
"""P2-3 AI 辅助分析 —— 四类测试 + 反向验证。

隔离方式：**子进程 + `APP_DATA_DIR` 临时目录**（与 P0/P1/P2-1/P2-2 同模式）。

四类：
  ① `AiAssistUnitTests`        能力清单 / 清洗 / 确定性线索 / 输入不足不编造
  ② `AiAssistAdvisoryTests`    **核心约束**：所有产出必须声明"只做辅助、不替代规则"
  ③ `AiAssistApiTests`         接口：meta / POST / 400 / 页面 / 路由顺序
  ④ `AiAssistPermTests`        权限：无 `risk.view` ⇒ 403

★ 判据口径
  · 「不替代规则」是**结果级**判据：**遍历全部能力**调用 `assist()`，逐条断言四个声明字段
    齐全且取值正确（不是抽查一个）。
  · 「不冒充 AI」判据：LLM 不可用时 `engine` 必须是 `rule_hint` 且 `is_ai=False`；
    反向验证注入"把线索标成 AI" ⇒ 判据必须变红。
  · 清洗判据必须**双向**：命中词被改写 **且** 命中词被如实记录（只改写不记录＝静默改写）。
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

ADMIN_USER = "p23admin"
ADMIN_PASS = "P2-3-Admin-Pass-2026!"


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


_PREAMBLE = (
    "import sys, os, json\n"
    "sys.path.insert(0, '.')\n"
    "from engine import ai_assist as A\n"
)

_FINDING = ('{"title": "进销倒挂", "level": "高", '
            '"policy_ref": "《增值税暂行条例》第六条"}')


def _script(body: str) -> str:
    return _PREAMBLE + textwrap.dedent(body)


class AiAssistUnitTests(unittest.TestCase):
    def test_capabilities_and_status(self):
        result = _run(_script("""
            caps = A.capabilities()
            st = A.status()
            assert caps["total"] == len(A.CAPABILITIES) >= 1
            assert caps["role"] == "advisory"
            assert caps["replaces_rules"] is False
            assert caps["disclaimer"] == A.DISCLAIMER
            assert set(st.keys()) >= {"available", "backend", "reason", "disclaimer"}
            # 不可用时必须给原因（不得静默）
            if not st["available"]:
                assert st["reason"], "不可用却没给原因"
            print("CAPS-OK n=%d available=%s" % (caps["total"], st["available"]))
        """))
        _assert_ok(result)
        self.assertIn("CAPS-OK", result.stdout)

    def test_sanitize_rewrites_and_records(self):
        """清洗必须**双向**：改写 + 如实记录命中词。"""
        result = _run(_script("""
            text, hits = A.sanitize("该企业已构成违规，应补缴税款，定性为偷税")
            assert "已构成违规" not in text and "应补缴" not in text and "定性为" not in text, text
            assert "（待人工复核）" in text, text
            assert set(hits) >= {"已构成违规", "应补缴", "定性为"}, hits
            # 反向：无禁用词的文本必须**原样**返回（不过度改写）
            t2, h2 = A.sanitize("建议补充合同与资金流水以便进一步核实。")
            assert t2 == "建议补充合同与资金流水以便进一步核实。", t2
            assert h2 == [], h2
            print("SANITIZE-OK hits=%d" % len(hits))
        """))
        _assert_ok(result)
        self.assertIn("SANITIZE-OK", result.stdout)

    def test_rule_hint_deterministic_and_no_fabrication(self):
        result = _run(_script("""
            f = json.loads('''%s''')
            a = A.rule_hint("explain_finding", {"finding": f})
            b = A.rule_hint("explain_finding", {"finding": f})
            assert a == b, (a, b)                      # 确定性（同一输入同结果）
            assert a["title"] == "进销倒挂"
            assert "《增值税暂行条例》第六条" in a["legal_basis"], a["legal_basis"]
            # 输入不足 ⇒ None（**不编造**）
            assert A.rule_hint("summarize_risks", {}) is None
            assert A.rule_hint("explain_finding", {}) is None
            print("HINT-OK")
        """ % _FINDING))
        _assert_ok(result)
        self.assertIn("HINT-OK", result.stdout)


class AiAssistAdvisoryTests(unittest.TestCase):
    def test_every_capability_declares_advisory_and_replaces_rules_false(self):
        """★ 遍历**全部**能力：产出必须声明"只做辅助、不替代规则"。"""
        result = _run(_script("""
            checked = 0
            for cap in A.CAPABILITIES:
                code = cap["code"]
                payload = {"findings": [json.loads('''%s''')],
                           "finding": json.loads('''%s''')}
                r = A.assist(code, payload, allow_llm=False)
                assert r["role"] == "advisory", (code, r["role"])
                assert r["advisory_only"] is True, code
                assert r["replaces_rules"] is False, (code, r["replaces_rules"])
                assert r["disclaimer"] == A.DISCLAIMER, code
                assert r["engine"] in ("llm", "rule_hint", "unavailable"), (code, r["engine"])
                checked += 1
            print("ADVISORY-OK checked=" + str(checked))
        """ % (_FINDING, _FINDING)))
        _assert_ok(result)
        self.assertIn("ADVISORY-OK", result.stdout)

    def test_no_llm_falls_back_honestly(self):
        """LLM 不可用 ⇒ 回落 rule_hint 且 `is_ai=False`（**不冒充 AI**）。"""
        result = _run(_script("""
            r = A.assist("explain_finding", {"finding": json.loads('''%s''')}, allow_llm=False)
            assert r["is_ai"] is False, r["is_ai"]
            assert r["engine"] == "rule_hint", r["engine"]
            assert r["output"], "规则侧线索不应为空"
            assert "规则侧线索" in r["reason"], r["reason"]
            # 输入不足时既不冒充 AI、也不编造内容
            r2 = A.assist("summarize_risks", {}, allow_llm=False)
            assert r2["output"] is None and r2["is_ai"] is False, r2
            print("FALLBACK-OK")
        """ % _FINDING))
        _assert_ok(result)
        self.assertIn("FALLBACK-OK", result.stdout)

    def test_unknown_capability_raises(self):
        result = _run(_script("""
            try:
                A.assist("not_a_cap", {})
                raise AssertionError("未知能力竟被接受")
            except A.AiAssistError as e:
                assert e.status == 400, e.status
            try:
                A.assist("", {})
                raise AssertionError("空 code 竟被接受")
            except A.AiAssistError:
                pass
            print("UNKNOWN-OK")
        """))
        _assert_ok(result)
        self.assertIn("UNKNOWN-OK", result.stdout)


class AiAssistApiTests(unittest.TestCase):
    def test_endpoints_route_order_and_400(self):
        result = _run("""
            import sys, os, json
            sys.path.insert(0, ".")
            from fastapi.testclient import TestClient
            import main
            from security import init_security_db, create_user
            init_security_db(); create_user("p23api", "P2-3-Api-Pass-2026!", role="admin")
            c = TestClient(main.app)
            assert c.post("/api/v1/auth/login",
                          json={"username": "p23api",
                                "password": "P2-3-Api-Pass-2026!"}).status_code == 200
            H = {"X-CSRF-Token": c.cookies.get("csrf_token")}
            m = c.get("/api/v1/ai-assist/meta")
            assert m.status_code == 200, m.text[:120]
            jm = m.json()
            assert jm["advisory_only"] is True and jm["replaces_rules"] is False
            assert "status" in jm and "capabilities" in jm
            r = c.post("/api/v1/ai-assist/explain_finding", headers=H,
                       json={"finding": {"title": "进销倒挂", "level": "高"}})
            assert r.status_code == 200, r.text[:150]
            jr = r.json()
            for k in ("role", "advisory_only", "replaces_rules", "disclaimer", "engine"):
                assert k in jr, (k, sorted(jr.keys()))
            assert jr["replaces_rules"] is False
            # 未知能力 ⇒ 400（不是 500）
            assert c.post("/api/v1/ai-assist/nope", headers=H, json={}).status_code == 400
            pg = c.get("/ai-assist")
            assert pg.status_code == 200 and "text/html" in pg.headers.get("content-type", "")
            print("API-OK caps=%d" % jm["capabilities"]["total"])
        """)
        _assert_ok(result)
        self.assertIn("API-OK", result.stdout)


class AiAssistPermTests(unittest.TestCase):
    def test_permission_and_deny_semantics(self):
        result = _run("""
            import sys, os
            sys.path.insert(0, ".")
            from fastapi.testclient import TestClient
            import main
            from security import init_security_db, create_user, get_session
            from engine import rbac as R
            init_security_db(); R.ensure_rbac_schema()
            R.create_role("no_risk", "无风险权限", ["project.view"])
            uid = create_user("p23noright", "P2-3-NoRight-2026!", role="user")
            R.assign_user_roles(uid, ["no_risk"])
            c = TestClient(main.app)
            assert c.post("/api/v1/auth/login",
                          json={"username": "p23noright",
                                "password": "P2-3-NoRight-2026!"}).status_code == 200
            sess = get_session(c.cookies.get("auth_token"))
            has = R.rbac_allows(sess, "risk.view")
            r = c.get("/api/v1/ai-assist/meta")
            if has:
                assert r.status_code == 200, ("有权限却拒绝", r.status_code)
            else:
                assert r.status_code == 403, ("无权限却放行", r.status_code)
            print("PERM-OK has=%s status=%d" % (has, r.status_code))
        """)
        _assert_ok(result)
        self.assertIn("PERM-OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
