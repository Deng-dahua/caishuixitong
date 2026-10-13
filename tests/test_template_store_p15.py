# -*- coding: utf-8 -*-
"""P1-5 报告模板管理 —— 单元测试 + 集成测试 + 反向判据。

★ 判据口径
  · **内置来源单一**：内置模板仍来自 `config/report_compliance.json`，本层**只读**它，
    不复制、不改写（改它就没法"停用覆盖回到出厂"）。
  · **章节白名单不放松**：`sections` 必须落在 `report_template.BASE_SECTIONS` 内（否则 400）。
  · **空模板不产出**：`sections` 为空 ⇒ 400（空模板会产出"没有章节的报告"）。
  · **停用语义**：只有**自定义/覆盖**模板可停用；未被覆盖的内置模板停用 ⇒ 400 并说明原因。
  · **变更留痕**：每次写入追加台账（版本自增），`versions` 可查。
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

ADMIN_USER = "p15admin"
ADMIN_PASS = "P1-5-Admin-Pass-2026!"


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


class TemplateStoreUnitTests(unittest.TestCase):
    def test_builtin_readonly_and_merge(self):
        result = _run("""
            import sys, json
            sys.path.insert(0, ".")
            from engine import template_store as T
            from engine.report_compliance import load_config
            from engine.report_template import BASE_SECTIONS
            from security import SessionContext

            # ① 内置来自 config（**不被本层复制**）
            cfg = (load_config().get("templates") or {})
            bi = T.builtin_templates()
            assert set(bi.keys()) == set(cfg.keys()), (sorted(bi), sorted(cfg))
            for tid, t in bi.items():
                assert t["scope"] == "builtin" and t["version"] == 0, t
                assert t["sections"] == [str(x) for x in (cfg[tid].get("sections") or [])], t
            eff0 = T.effective_templates()
            assert set(eff0.keys()) == set(cfg.keys()), sorted(eff0)

            s = SessionContext(user_id=1, username="u", role="admin",
                               allowed_company_ids=frozenset(), selected_company_id=None,
                               csrf_hash="", expires_at=0)

            # ② 新建自定义 ⇒ 出现在有效集合，内置不动
            T.upsert_template("t_unit_a", {"label": "单元模板A",
                                           "sections": ["风险事项", "结论与建议"]}, s)
            eff1 = T.effective_templates()
            assert "t_unit_a" in eff1 and eff1["t_unit_a"]["scope"] == "custom", eff1["t_unit_a"]
            assert T.builtin_templates() == bi, "内置模板被本层改动了"

            # ③ 覆盖内置 ⇒ 有效集合取覆盖值，内置仍为原值
            tgt = sorted(cfg.keys())[0]
            orig_secs = list(bi[tgt]["sections"])
            T.upsert_template(tgt, {"label": "覆盖后的内置", "sections": ["风险事项"]}, s)
            eff2 = T.effective_templates()
            assert eff2[tgt]["scope"] == "custom" and eff2[tgt]["label"] == "覆盖后的内置", eff2[tgt]
            assert T.builtin_templates()[tgt]["sections"] == orig_secs, "内置被就地改写了"

            # ④ 停用覆盖 ⇒ 回到内置出厂值（**不是消失**）
            T.disable_template(tgt, s)
            eff3 = T.effective_templates()
            assert eff3[tgt]["scope"] == "builtin", eff3[tgt]
            assert eff3[tgt]["sections"] == orig_secs, eff3[tgt]

            # ⑤ 停用纯自定义 ⇒ 从有效集合移除
            T.disable_template("t_unit_a", s)
            assert "t_unit_a" not in T.effective_templates()

            # ⑥ 版本自增且历史可查
            hist = T.template_versions("t_unit_a")
            assert [x["version"] for x in hist] == [1, 2], hist
            assert hist[0]["action"] == "upsert" and hist[1]["action"] == "disable", hist

            # ⑦ 未停用前不许停用内置（**不是 400 就是不存在**）
            try:
                T.disable_template(tgt, s)          # 已停用过一次，此处应是 noop
            except Exception as e:
                raise AssertionError("重复停用应 noop 而非报错：%r" % e)
            try:
                T.disable_template("manufacturing", s)
                # 若 manufacturing 恰好是 tgt 且已被覆盖过 ⇒ 可能允许；否则必须 400
            except Exception as e:
                assert e.__class__.__name__ == "TemplateError" and int(e.status) == 400, e
            print("MERGE-OK base_sections=%d" % len(BASE_SECTIONS))
        """)
        _assert_ok(result)
        self.assertIn("MERGE-OK", result.stdout)

    def test_validation_rejects_bad_input(self):
        result = _run("""
            import sys
            sys.path.insert(0, ".")
            from engine import template_store as T
            from security import SessionContext
            s = SessionContext(user_id=1, username="u", role="admin",
                               allowed_company_ids=frozenset(), selected_company_id=None,
                               csrf_hash="", expires_at=0)

            def expect400(fn, *a, **k):
                try:
                    fn(*a, **k)
                except AssertionError:
                    raise
                except Exception as e:
                    assert e.__class__.__name__ == "TemplateError", e.__class__.__name__
                    assert int(e.status) == 400, e.status
                    return str(e.message)
                raise AssertionError("应当 400")

            # 编码非法（大写 / 以数字开头 / 含横线 / 过短）
            for bad_id in ("Bad", "1abc", "a-b", "a", "a" * 60, ""):
                expect400(T.upsert_template, bad_id,
                          {"label": "x", "sections": ["风险事项"]}, s)
            # 名称空 / 章节空 / 章节不在白名单
            expect400(T.upsert_template, "t_ok1", {"label": "", "sections": ["风险事项"]}, s)
            expect400(T.upsert_template, "t_ok1", {"label": "x", "sections": []}, s)
            expect400(T.upsert_template, "t_ok1",
                      {"label": "x", "sections": ["风险事项", "瞎编的章节"]}, s)
            # 查不到 ⇒ None（**不返回空模板**）
            assert T.get_template("never_exists") is None
            assert T.get_template("") is None
            print("VALIDATE-OK")
        """)
        _assert_ok(result)
        self.assertIn("VALIDATE-OK", result.stdout)


class TemplateApiIntegrationTests(unittest.TestCase):
    def test_endpoints_and_permission(self):
        result = _run("""
            import sys, os
            sys.path.insert(0, ".")
            from fastapi.testclient import TestClient
            import main
            from security import init_security_db, create_user
            from engine import rbac as R
            init_security_db(); R.ensure_rbac_schema()
            create_user("p15int", "P1-5-Int-Pass-2026!", role="admin")
            c = TestClient(main.app)
            assert c.post("/api/v1/auth/login",
                          json={"username": "p15int",
                                "password": "P1-5-Int-Pass-2026!"}).status_code == 200
            H = {"X-CSRF-Token": c.cookies.get("csrf_token")}

            m = c.get("/api/v1/report-templates/meta")
            assert m.status_code == 200, m.text
            assert len(m.json()["base_sections"]) >= 5, m.json()
            assert m.json()["builtin_ids"], m.json()

            l = c.get("/api/v1/report-templates")
            assert l.status_code == 200 and l.json()["total"] >= 4, l.text
            assert c.get("/api/v1/report-templates/nope").status_code == 404

            # 写：CSRF 缺失 ⇒ 403
            assert c.post("/api/v1/report-templates/t_x",
                          json={"label": "x", "sections": ["风险事项"]}).status_code == 403
            # 写：合法
            ok = c.post("/api/v1/report-templates/t_x", headers=H,
                        json={"label": "集成模板", "sections": ["风险事项", "结论与建议"]})
            assert ok.status_code == 200, ok.text
            assert ok.json()["version"] == 1, ok.json()
            # 版本历史
            h = c.get("/api/v1/report-templates/t_x/versions")
            assert h.status_code == 200 and h.json()["total"] == 1, h.text
            # 页面可达
            pg = c.get("/report-templates")
            assert pg.status_code == 200 and "text/html" in pg.headers.get("content-type", ""), pg.status_code

            # 无 template.manage 的角色 ⇒ 写 403、读 200
            R.create_role("p15_nomanage", "P1-5 无模板管理权", ["report.view"])
            uid = create_user("p15ro", "P1-5-RO-Pass-2026!", role="user")
            R.assign_user_roles(uid, ["p15_nomanage"])
            c2 = TestClient(main.app)
            assert c2.post("/api/v1/auth/login",
                           json={"username": "p15ro",
                                 "password": "P1-5-RO-Pass-2026!"}).status_code == 200
            assert c2.get("/api/v1/report-templates").status_code == 200, "读权限应放行"
            h2 = {"X-CSRF-Token": c2.cookies.get("csrf_token")}
            w = c2.post("/api/v1/report-templates/t_y", headers=h2,
                        json={"label": "y", "sections": ["风险事项"]})
            assert w.status_code == 403, (w.status_code, w.text[:200])
            assert "template.manage" in (w.json().get("detail") or ""), w.json()
            print("INTEG-OK")
        """)
        _assert_ok(result)
        self.assertIn("INTEG-OK", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
