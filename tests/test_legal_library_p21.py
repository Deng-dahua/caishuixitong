# -*- coding: utf-8 -*-
"""P2-1 法规库 —— 四类测试 + 反向验证。

隔离方式：**子进程 + `APP_DATA_DIR` 临时目录**（与 P0/P1 各步同模式）。

四类：
  ① `LegalLibraryUnitTests`        读层：条目/法清单/详情/统计/字典（**纯数据驱动**）
  ② `LegalLibraryNoHardcodeTests`  **不硬编码条文**：返回的每条正文都必须能在数据文件中找到
  ③ `LegalLibraryApiTests`         接口：检索/分页/404/路由顺序
  ④ `LegalLibraryPermTests`        权限：无 `legal.view` ⇒ 403（不静默降级、不 500）

★ 判据口径
  · 「不硬编码条文」判据是**结果级**的：把读层返回的每一条 `content` 去数据文件里反查，
    必须**逐字命中**；任何"凭空多出来"的条文都会让判据变红（不是 grep 源码，而是比对产出）。
  · 版本状态判据必须与 `legal_version` 同源：同一法名在读层与权威 register 里状态一致。
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

ADMIN_USER = "p21admin"
ADMIN_PASS = "P2-1-Admin-Pass-2026!"


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


#: 每个子脚本共用的导入头（**0 缩进**）。正文单独 `textwrap.dedent`，
#: 否则 `_PREAMBLE + \"\"\"…\"\"\"` 拼接后整体最小缩进为 0 ⇒ 正文缩进残留 ⇒ IndentationError。
_PREAMBLE = (
    "import sys, os, json\n"
    "sys.path.insert(0, '.')\n"
    "from engine import legal_library as LL\n"
    "from engine import legal_citation as LC\n"
    "from engine import legal_version as LV\n"
)


def _script(body: str) -> str:
    return _PREAMBLE + textwrap.dedent(body)


class LegalLibraryUnitTests(unittest.TestCase):
    def test_read_layer_is_data_driven(self):
        """读层口径：条目数 == 数据文件条目数；法数 == 去重法名数；统计与明细自洽。"""
        result = _run(_script("""
            rows = LC.library_file_entries()
            m = LL.metadata()
            e = LL.article_entries(limit=1000)
            l = LL.laws()
            s = LL.stats()
            print("ROWS=%d ENTRIES=%d LAWS=%d" % (len(rows), e["total"], l["total"]))
            assert e["total"] == len(rows), (e["total"], len(rows))
            assert l["total"] == len({r["law"] for r in rows}), (l["total"],)
            assert s["articles"] == len(rows), (s["articles"], len(rows))
            assert s["laws"] == l["total"], (s["laws"], l["total"])
            files = [x["file"] for x in m["sources"]]
            assert files == ["legal_library.json", "legal_refs.json"], files
            print("UNIT-OK")
        """))
        _assert_ok(result)
        self.assertIn("UNIT-OK", result.stdout)

    def test_version_status_same_source_as_authority(self):
        """版本状态必须与 `legal_version` **同源**（薄转发，不另判）。"""
        result = _run(_script("""
            l = LL.laws()
            bad = []
            for x in l["items"]:
                if x["version"]["status"] != LV.status_of(x["law"]):
                    bad.append((x["law"], x["version"]["status"], LV.status_of(x["law"])))
            assert not bad, bad
            reg = [x for x in l["items"] if x["version"]["registered"]]
            unreg = [x for x in l["items"] if not x["version"]["registered"]]
            assert reg and unreg, ("样本不足", len(reg), len(unreg))
            for x in reg:
                assert LV.entry_of(x["law"]) is not None, x["law"]
            for x in unreg:
                assert LV.entry_of(x["law"]) is None, x["law"]
            print("STATUS-OK reg=%d unreg=%d" % (len(reg), len(unreg)))
        """))
        _assert_ok(result)
        self.assertIn("STATUS-OK", result.stdout)

    def test_detail_and_404_semantics(self):
        result = _run(_script("""
            d = LL.law_detail("企业所得税法")
            assert d is not None and d["articles"], "详情为空"
            assert d["version_note"].startswith("（"), d["version_note"]
            assert LL.law_detail("这部法根本不存在") is None
            print("DETAIL-OK n=%d" % len(d["articles"]))
        """))
        _assert_ok(result)
        self.assertIn("DETAIL-OK", result.stdout)


class LegalLibraryNoHardcodeTests(unittest.TestCase):
    """★ 核心约束验收：「法规库不硬编码条文」—— 结果级反查。"""

    def test_every_returned_article_exists_in_data_file(self):
        result = _run(_script("""
            raw = {}
            for r in LC.library_file_entries():
                raw[(r["law"], r["article"])] = r["content"]
            rows = LL.article_entries(limit=100000)["items"]
            miss = []
            for x in rows:
                k = (x["law"], x["article"])
                if raw.get(k) != x["content"]:
                    miss.append((k, x["content"][:30]))
            assert not miss, miss[:3]
            print("NOHARDCODE-OK checked=%d" % len(rows))
        """))
        _assert_ok(result)
        self.assertIn("NOHARDCODE-OK", result.stdout)

    def test_search_never_invents(self):
        """检索一个**极不可能存在**的词 ⇒ 返回 0（不得编造条文凑结果）；真实词必须能命中。"""
        result = _run(_script("""
            j = LL.article_entries(q="绝无仅有的不存在词组ZZZQQQ")
            assert j["total"] == 0, j["total"]
            j2 = LL.article_entries(q="发票")
            assert j2["total"] > 0, j2["total"]
            print("SEARCH-OK zero=%d hit=%d" % (j["total"], j2["total"]))
        """))
        _assert_ok(result)
        self.assertIn("SEARCH-OK", result.stdout)


class LegalLibraryApiTests(unittest.TestCase):
    def test_endpoints_and_route_order(self):
        """6 个端点 + 路由顺序（字面量段不得被 `{law}` 吃掉）。"""
        result = _run("""
            import sys, os
            sys.path.insert(0, ".")
            from fastapi.testclient import TestClient
            import main
            from security import init_security_db, create_user
            init_security_db(); create_user("p21api", "P2-1-Api-Pass-2026!", role="admin")
            c = TestClient(main.app)
            assert c.post("/api/v1/auth/login",
                          json={"username": "p21api",
                                "password": "P2-1-Api-Pass-2026!"}).status_code == 200
            base = "/api/v1/legal-library"
            for p in (base + "/meta", base + "/stats", base + "/laws", base,
                      base + "?q=发票", base + "/企业所得税法"):
                r = c.get(p)
                assert r.status_code == 200, (p, r.status_code, r.text[:120])
            # ★ 路由顺序：/laws 必须是**法清单**（不是被 {law} 吃成"名为 laws 的法"）
            jl = c.get(base + "/laws").json()
            assert "items" in jl and "total" in jl, jl
            # ★ 反向：不存在的法 ⇒ 404（且不是 500）
            r404 = c.get(base + "/不存在法XYZ")
            assert r404.status_code == 404, (r404.status_code, r404.text[:120])
            pg = c.get("/legal-library")
            assert pg.status_code == 200 and "text/html" in pg.headers.get("content-type", "")
            print("API-OK laws=%d" % jl["total"])
        """)
        _assert_ok(result)
        self.assertIn("API-OK", result.stdout)

    def test_pagination_consistent(self):
        result = _run("""
            import sys, os
            sys.path.insert(0, ".")
            from fastapi.testclient import TestClient
            import main
            from security import init_security_db, create_user
            init_security_db(); create_user("p21pg", "P2-1-Pg-Pass-2026!", role="admin")
            c = TestClient(main.app)
            c.post("/api/v1/auth/login",
                   json={"username": "p21pg", "password": "P2-1-Pg-Pass-2026!"})
            base = "/api/v1/legal-library"
            a = c.get(base + "?page=1&page_size=10").json()
            b = c.get(base + "?page=2&page_size=10").json()
            assert a["total"] == b["total"], (a["total"], b["total"])
            assert len(a["items"]) == 10, len(a["items"])
            assert (a["items"][0]["law"], a["items"][0]["article"]) != \\
                   (b["items"][0]["law"], b["items"][0]["article"]), "分页未推进"
            assert a["pages"] == (a["total"] + 9) // 10, (a["pages"], a["total"])
            print("PG-OK total=%d pages=%d" % (a["total"], a["pages"]))
        """)
        _assert_ok(result)
        self.assertIn("PG-OK", result.stdout)


class LegalLibraryPermTests(unittest.TestCase):
    def test_permission_and_deny_semantics(self):
        """无 `legal.view` ⇒ 403；有权限 ⇒ 200（两侧都断，防"恒 403"假绿）。"""
        result = _run("""
            import sys, os
            sys.path.insert(0, ".")
            from fastapi.testclient import TestClient
            import main
            from security import init_security_db, create_user, get_session
            from engine import rbac as R
            init_security_db(); R.ensure_rbac_schema()
            # 造一个**不含 legal.view** 的自定义角色（create_role 是**位置参数**）
            R.create_role("no_legal", "无法规权限", ["risk.view"])
            uid = create_user("p21noright", "P2-1-NoRight-2026!", role="user")
            R.assign_user_roles(uid, ["no_legal"])
            c = TestClient(main.app)
            assert c.post("/api/v1/auth/login",
                          json={"username": "p21noright",
                                "password": "P2-1-NoRight-2026!"}).status_code == 200
            sess = get_session(c.cookies.get("auth_token"))
            has = R.rbac_allows(sess, "legal.view")
            r = c.get("/api/v1/legal-library/meta")
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
