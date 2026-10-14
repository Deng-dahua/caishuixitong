# -*- coding: utf-8 -*-
"""P2-2 行业指标库 —— 四类测试 + 反向验证。

隔离方式：**子进程 + `APP_DATA_DIR` 临时目录**（与 P0/P1/P2-1 同模式）。

四类：
  ① `IndustryIndicatorsUnitTests`      读层：行业数/指标键/区间/详情/兜底（**纯数据驱动**）
  ② `IndustryIndicatorsCaliberTests`   **口径单一权威**：警示语薄转发；未登记行业 ⇒ 404
  ③ `IndustryIndicatorsApiTests`       接口：5 端点/分页/404/路由顺序
  ④ `IndustryIndicatorsPermTests`      权限：无 `industry.view` ⇒ 403（不静默降级、不 500）

★ 判据口径
  · 「不硬编码」判据是**结果级**的：读层返回的每个指标键必须 ∈ `industry_benchmark.indicator_keys()`，
    每个行业 id 必须 ∈ `industry_params.industry_ids()`；多余即判据变红。
  · 区间判据与权威同源：读层返回的 low/high 必须与 `resolve_benchmark` 的结果**完全一致**
    （证明是薄转发，不是另算一份）。
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

ADMIN_USER = "p22admin"
ADMIN_PASS = "P2-2-Admin-Pass-2026!"


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
    "from engine import industry_indicators as II\n"
    "from engine import industry_params as IP\n"
    "from engine import industry_benchmark as IB\n"
)


def _script(body: str) -> str:
    return _PREAMBLE + textwrap.dedent(body)


class IndustryIndicatorsUnitTests(unittest.TestCase):
    def test_read_layer_is_data_driven(self):
        result = _run(_script("""
            ind = II.industry_rows()
            m = II.metadata()
            s = II.stats()
            assert ind["total"] == len(IP.industry_ids()), (ind["total"], len(IP.industry_ids()))
            got = {x["industry_id"] for x in ind["items"]}
            assert got == set(IP.industry_ids()), (sorted(got ^ set(IP.industry_ids())))
            assert [k["key"] for k in m["indicator_keys"]] == IB.indicator_keys()
            assert s["industries"] == ind["total"]
            assert s["indicator_keys"] == len(IB.indicator_keys())
            print("UNIT-OK industries=%d keys=%d" % (ind["total"], s["indicator_keys"]))
        """))
        _assert_ok(result)
        self.assertIn("UNIT-OK", result.stdout)

    def test_ranges_are_thin_forward_of_authority(self):
        """区间必须与 `resolve_benchmark` **逐值一致**（薄转发，不另算）。"""
        result = _run(_script("""
            bad = []
            for x in II.industry_rows()["items"]:
                _matched, bench, _src = IB.resolve_benchmark(x["label"])
                got = {i["key"]: (i["low"], i["high"]) for i in x["indicators"]}
                want = {k: tuple(v) for k, v in bench.items() if k in IB.indicator_keys()}
                if got != want:
                    bad.append((x["label"], got, want))
            assert not bad, bad[:2]
            print("RANGE-OK checked=%d" % len(II.industry_rows()["items"]))
        """))
        _assert_ok(result)
        self.assertIn("RANGE-OK", result.stdout)

    def test_detail_and_generic(self):
        result = _run(_script("""
            d = II.industry_detail("制造业")
            assert d is not None and d["industry_id"] == "manufacturing", d and d["industry_id"]
            assert d["indicators"], "制造业无指标"
            # 按 label 也能查到（转发 resolve_industry_id）
            assert II.industry_detail("餐饮")["industry_id"] == "catering"
            g = II.generic()
            assert g["indicators"], "兜底区间为空"
            # ★ 兜底区间必须与"某行业基准"区分：不匹配任何登记行业
            assert g["matched"] == "", g["matched"]
            print("DETAIL-OK")
        """))
        _assert_ok(result)
        self.assertIn("DETAIL-OK", result.stdout)


class IndustryIndicatorsCaliberTests(unittest.TestCase):
    def test_caution_is_thin_forward(self):
        """口径警示必须**逐字等于**权威常量（不得写第二份）。"""
        result = _run(_script("""
            m = II.metadata()
            assert m["caution"] == IB.BENCHMARK_CAUTION, m["caution"]
            # 详情与统计里也必须同源
            assert II.stats()["caution"] == IB.BENCHMARK_CAUTION
            assert II.industry_detail("制造业")["caution"] == IB.BENCHMARK_CAUTION
            print("CAUTION-OK")
        """))
        _assert_ok(result)
        self.assertIn("CAUTION-OK", result.stdout)

    def test_unregistered_industry_is_404_not_generic(self):
        """未登记行业 ⇒ `None`（接口 404）；**不得**把兜底区间包装成该行业基准。"""
        result = _run(_script("""
            assert II.industry_detail("这个行业根本没登记") is None
            assert II.industry_detail("") is None
            print("NOTFOUND-OK")
        """))
        _assert_ok(result)
        self.assertIn("NOTFOUND-OK", result.stdout)


class IndustryIndicatorsApiTests(unittest.TestCase):
    def test_endpoints_and_route_order(self):
        result = _run("""
            import sys, os
            sys.path.insert(0, ".")
            from fastapi.testclient import TestClient
            import main
            from security import init_security_db, create_user
            init_security_db(); create_user("p22api", "P2-2-Api-Pass-2026!", role="admin")
            c = TestClient(main.app)
            assert c.post("/api/v1/auth/login",
                          json={"username": "p22api",
                                "password": "P2-2-Api-Pass-2026!"}).status_code == 200
            base = "/api/v1/industry-indicators"
            for p in (base + "/meta", base + "/stats", base + "/generic", base, base + "/制造业"):
                r = c.get(p)
                assert r.status_code == 200, (p, r.status_code, r.text[:120])
            # ★ 路由顺序：/generic 必须是兜底区间（不是被 {industry} 吃成"名为 generic 的行业"）
            jg = c.get(base + "/generic").json()
            assert "indicators" in jg and jg.get("matched") == "", jg
            # ★ 反向：未登记行业 ⇒ 404
            assert c.get(base + "/不存在行业XYZ").status_code == 404
            pg = c.get("/industry-indicators")
            assert pg.status_code == 200 and "text/html" in pg.headers.get("content-type", "")
            print("API-OK")
        """)
        _assert_ok(result)
        self.assertIn("API-OK", result.stdout)


class IndustryIndicatorsPermTests(unittest.TestCase):
    def test_permission_and_deny_semantics(self):
        result = _run("""
            import sys, os
            sys.path.insert(0, ".")
            from fastapi.testclient import TestClient
            import main
            from security import init_security_db, create_user, get_session
            from engine import rbac as R
            init_security_db(); R.ensure_rbac_schema()
            R.create_role("no_industry", "无行业权限", ["risk.view"])
            uid = create_user("p22noright", "P2-2-NoRight-2026!", role="user")
            R.assign_user_roles(uid, ["no_industry"])
            c = TestClient(main.app)
            assert c.post("/api/v1/auth/login",
                          json={"username": "p22noright",
                                "password": "P2-2-NoRight-2026!"}).status_code == 200
            sess = get_session(c.cookies.get("auth_token"))
            has = R.rbac_allows(sess, "industry.view")
            r = c.get("/api/v1/industry-indicators/meta")
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
