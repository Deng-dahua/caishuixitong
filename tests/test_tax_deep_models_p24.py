# -*- coding: utf-8 -*-
"""P2-4 多税种深度模型 —— 四类测试 + 反向验证。

隔离方式：**子进程 + `APP_DATA_DIR` 临时目录**（与 P0/P1/P2 各步同模式）。

四类：
  ① `TaxDeepModelsUnitTests`    读层：税种/模型/编码唯一/线索强度（**纯数据驱动**）
  ② `TaxDeepModelsCaliberTests` **口径单一权威**：税种范围与税率薄转发；未实现如实标注
  ③ `TaxDeepModelsApiTests`     接口：5 端点/404/路由顺序/页面
  ④ `TaxDeepModelsPermTests`    权限：无 `risk.view` ⇒ 403

★ 判据口径
  · 「不硬编码」是**结果级**判据：读层返回的每个税种必须 ∈ `tax_impact.known_tax_types()` ∪ 本表登记；
    每个 `impl` 非空时必须有对应模块文件；都不靠 grep 源码。
  · 「不假装已实现」判据：`impl` 为空 ⇒ `implemented=False` **且** `impl_note` 非空（如实说明）。
  · 税率判据与权威同源：读层 `default_rate/rate_note/quantifiable` 必须与
    `tax_impact.tax_rate_table()` **逐值一致**。
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

ADMIN_USER = "p24admin"
ADMIN_PASS = "P2-4-Admin-Pass-2026!"


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
    "from engine import tax_deep_models as M\n"
    "from engine import tax_impact as TI\n"
)


def _script(body: str) -> str:
    return _PREAMBLE + textwrap.dedent(body)


class TaxDeepModelsUnitTests(unittest.TestCase):
    def test_read_layer_is_data_driven_and_codes_unique(self):
        result = _run(_script("""
            ts = M.taxes()
            cx = M.cross_tax()
            assert ts["total"] >= 1, "税种为空"
            codes = [m["code"] for x in ts["items"] for m in x["models"]]
            codes += [m["code"] for m in cx["items"]]
            assert codes, "模型为空"
            assert len(codes) == len(set(codes)), ("模型编码重复", len(codes), len(set(codes)))
            # 每个模型必须带线索强度且取值在枚举内
            for m in [mm for x in ts["items"] for mm in x["models"]] + cx["items"]:
                assert m["severity"] in M.SEVERITIES, (m["code"], m["severity"])
                assert m["focus"] and m["data_required"], m["code"]
            print("UNIT-OK taxes=%d models=%d" % (ts["total"], len(codes)))
        """))
        _assert_ok(result)
        self.assertIn("UNIT-OK", result.stdout)

    def test_implemented_flag_matches_module_existence(self):
        """`implemented` 必须与「实现模块文件是否存在」一致（不得假装已实现）。"""
        result = _run(_script("""
            from pathlib import Path
            bad = []
            for m in [mm for x in M.taxes()["items"] for mm in x["models"]] + M.cross_tax()["items"]:
                imp = m["impl"]
                exists = bool(imp) and (Path("engine") / (imp + ".py")).is_file()
                if bool(m["implemented"]) != exists:
                    bad.append((m["code"], imp, m["implemented"], exists))
                # 未实现的必须**如实说明**
                if not m["implemented"] and not m["impl_note"]:
                    bad.append(("no-note", m["code"]))
            assert not bad, bad[:3]
            print("IMPL-OK")
        """))
        _assert_ok(result)
        self.assertIn("IMPL-OK", result.stdout)


class TaxDeepModelsCaliberTests(unittest.TestCase):
    def test_tax_scope_and_rate_are_thin_forward(self):
        """税种范围与税率口径必须与 `tax_impact` **同源**（薄转发）。"""
        result = _run(_script("""
            known = TI.known_tax_types()
            tbl = TI.tax_rate_table()
            bad = []
            for x in M.taxes()["items"]:
                if x["in_scope"] != (x["tax"] in known):
                    bad.append(("in_scope", x["tax"], x["in_scope"], x["tax"] in known))
                info = tbl.get(x["tax"])
                if info:
                    if bool(x["quantifiable"]) != bool(info["quantifiable"]):
                        bad.append(("quantifiable", x["tax"]))
                    if x["default_rate"] != info["rate"]:
                        bad.append(("rate", x["tax"], x["default_rate"], info["rate"]))
                    if (x["rate_note"] or "") != (info["note"] or ""):
                        bad.append(("rate_note", x["tax"]))
            assert not bad, bad[:3]
            print("CALIBER-OK known=%d" % len(known))
        """))
        _assert_ok(result)
        self.assertIn("CALIBER-OK", result.stdout)

    def test_coverage_reports_gaps_honestly(self):
        """覆盖缺口必须如实列出（不得用默认值或删税种掩盖）。"""
        result = _run(_script("""
            cov = M.coverage()
            known = TI.known_tax_types()
            assert cov["taxes_in_scope"] == len(known), (cov["taxes_in_scope"], len(known))
            allset = set(cov["taxes_without_models"]) | {
                x["tax"] for x in M.taxes()["items"] if x["tax"] in known}
            assert allset == set(known), sorted(set(known) ^ allset)
            # 未量化税种的子集关系必须成立
            nonq = set(TI.tax_rate_table().get(t, {}).get("quantifiable", True)
                       for t in cov["taxes_without_rate"])
            assert not any(nonq), cov["taxes_without_rate"]
            print("COVERAGE-OK in_scope=%d with_models=%d" % (
                cov["taxes_in_scope"], cov["taxes_with_models"]))
        """))
        _assert_ok(result)
        self.assertIn("COVERAGE-OK", result.stdout)


class TaxDeepModelsApiTests(unittest.TestCase):
    def test_endpoints_route_order_and_404(self):
        result = _run("""
            import sys, os
            sys.path.insert(0, ".")
            from fastapi.testclient import TestClient
            import main
            from security import init_security_db, create_user
            init_security_db(); create_user("p24api", "P2-4-Api-Pass-2026!", role="admin")
            c = TestClient(main.app)
            assert c.post("/api/v1/auth/login",
                          json={"username": "p24api",
                                "password": "P2-4-Api-Pass-2026!"}).status_code == 200
            base = "/api/v1/tax-models"
            for p in (base + "/meta", base + "/coverage", base + "/cross-tax",
                      base, base + "/增值税"):
                r = c.get(p)
                assert r.status_code == 200, (p, r.status_code, r.text[:120])
            # ★ 路由顺序：/coverage 必须是覆盖信息（不是被 {tax} 吃成"名为 coverage 的税种"）
            jc = c.get(base + "/coverage").json()
            assert "taxes_in_scope" in jc and "coverage" in jc, jc
            # ★ 反向：未登记税种 ⇒ 404
            assert c.get(base + "/不存在税XYZ").status_code == 404
            pg = c.get("/tax-models")
            assert pg.status_code == 200 and "text/html" in pg.headers.get("content-type", "")
            print("API-OK taxes=%d" % c.get(base).json()["total"])
        """)
        _assert_ok(result)
        self.assertIn("API-OK", result.stdout)


class TaxDeepModelsPermTests(unittest.TestCase):
    def test_permission_and_deny_semantics(self):
        result = _run("""
            import sys, os
            sys.path.insert(0, ".")
            from fastapi.testclient import TestClient
            import main
            from security import init_security_db, create_user, get_session
            from engine import rbac as R
            init_security_db(); R.ensure_rbac_schema()
            R.create_role("no_taxmodel", "无风险权限", ["project.view"])
            uid = create_user("p24noright", "P2-4-NoRight-2026!", role="user")
            R.assign_user_roles(uid, ["no_taxmodel"])
            c = TestClient(main.app)
            assert c.post("/api/v1/auth/login",
                          json={"username": "p24noright",
                                "password": "P2-4-NoRight-2026!"}).status_code == 200
            sess = get_session(c.cookies.get("auth_token"))
            has = R.rbac_allows(sess, "risk.view")
            r = c.get("/api/v1/tax-models/meta")
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
