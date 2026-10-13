# -*- coding: utf-8 -*-
"""P1-2 OCR 引擎治理 —— 单元测试 + 集成测试 + 反向判据。

隔离方式：子进程 + `APP_DATA_DIR` 临时目录（与 P0/P1-1 同模式）。

★ 判据口径（必须写明，否则数字无意义）
  · **行为等价**判据：`record_ocr_run(chunks, engine)` 的返回值必须与
    `"\\n".join(chunks)` **逐字符相同** —— 治理层不得改变 OCR 结果（否则"加了留痕"就换掉了正文）。
  · **不静默**判据：`chunks` 为空时必须给出**非空 reason**（"无可用引擎"或"未识别到文字"），
    且 `empty is True`。
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

ADMIN_USER = "p12admin"
ADMIN_PASS = "P1-2-Admin-Pass-2026!"


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


class OcrEngineUnitTests(unittest.TestCase):
    def test_engines_probe_and_status(self):
        result = _run("""
            import sys
            sys.path.insert(0, ".")
            from engine import ocr_engine as OC

            # 1) 登记表与探测键**必须对齐**（新增引擎只加登记表一行）
            names = [e["name"] for e in OC.ENGINES]
            assert names == ["rapidocr", "easyocr", "tesseract"], names
            probed = OC.probe_engines()
            assert set(probed.keys()) == set(names), (probed, names)

            # 2) 状态：available 与 any_available 必须自洽
            st = OC.engine_status()
            assert st["any_available"] == bool(st["available"]), st
            assert st["preferred"] == (st["available"][0] if st["available"] else ""), st
            for r in st["engines"]:
                assert r["available"] == probed[r["name"]], r
            # 3) 找不到引擎 ⇒ **必须显式说明**（不允许空 note）
            assert st["note"].strip(), "状态说明不得为空"
            if not st["available"]:
                assert "无可用" in st["note"], st["note"]

            # 4) 阈值可查（供前端展示，不硬编码）
            assert isinstance(st["conf_floor"], float) and 0 < st["conf_floor"] < 1, st

            print("UNIT-OK available=%s" % st["available"])
        """)
        _assert_ok(result)
        self.assertIn("UNIT-OK", result.stdout)

    def test_record_is_behavior_equivalent(self):
        """★ 核心判据：治理层的返回值必须与既有 `"\\n".join(chunks)` 逐字符相同。"""
        result = _run("""
            import sys
            sys.path.insert(0, ".")
            from engine import ocr_engine as OC

            cases = [["a", "b", "c"], ["单行"], [], ["a\\nb", "c"]]
            for chunks in cases:
                got = OC.record_ocr_run(chunks, "rapidocr")
                exp = "\\n".join(chunks)
                assert got == exp, (got, exp, chunks)

            # 空结果：必须显式给出原因（不静默）
            OC.reset_runs()
            OC.record_ocr_run([], "none")
            last = OC.last_ocr_run()
            assert last["empty"] is True, last
            assert last["reason"] and "无可用" in last["reason"], last

            OC.record_ocr_run([], "rapidocr")
            last2 = OC.last_ocr_run()
            assert last2["empty"] is True and "未识别到文字" in last2["reason"], last2

            # 低置信度计数（阈值 0.5）
            OC.reset_runs()
            OC.record_ocr_run(["x"], "rapidocr", confidences=[0.2, 0.9, 0.51])
            last3 = OC.last_ocr_run()
            assert last3["conf_n"] == 3 and last3["low_conf"] == 1, last3

            # 有内容 ⇒ empty False 且 reason 为空
            OC.record_ocr_run(["有内容"], "rapidocr")
            assert OC.last_ocr_run()["empty"] is False
            assert OC.last_ocr_run()["reason"] == ""

            print("EQUIV-OK")
        """)
        _assert_ok(result)
        self.assertIn("EQUIV-OK", result.stdout)

    def test_runs_are_bounded(self):
        """留痕有上限（不无限增长）；且 `reset_runs` 后为空（不是"清不掉"）。"""
        result = _run("""
            import sys
            sys.path.insert(0, ".")
            from engine import ocr_engine as OC
            OC.reset_runs()
            assert OC.last_ocr_run() is None, "reset 后应为空（缺失≠0，返回 None 而非空字典）"
            for i in range(80):
                OC.record_ocr_run(["第%d段" % i], "rapidocr")
            meta = OC.engine_metadata()
            assert meta["runs"] <= 50, meta["runs"]
            assert meta["last"] and meta["last"]["engine"] == "rapidocr", meta["last"]
            print("BOUND-OK runs=%d" % meta["runs"])
        """)
        _assert_ok(result)
        self.assertIn("BOUND-OK", result.stdout)


class OcrEngineIntegrationTests(unittest.TestCase):
    def test_ocr_endpoints(self):
        result = _run("""
            import sys, os
            sys.path.insert(0, ".")
            from fastapi.testclient import TestClient
            import main
            from security import init_security_db, create_user
            init_security_db()
            create_user("p12int", "P1-2-Int-Pass-2026!", role="admin")
            c = TestClient(main.app)
            assert c.post("/api/v1/auth/login",
                          json={"username": "p12int",
                                "password": "P1-2-Int-Pass-2026!"}).status_code == 200

            m = c.get("/api/v1/ocr/meta")
            assert m.status_code == 200, m.text
            j = m.json()
            assert len(j["engines"]) == 3, j["engines"]
            assert "any_available" in j and "preferred" in j and j["note"], j
            assert isinstance(j["conf_floor"], float), j["conf_floor"]

            r = c.get("/api/v1/ocr/runs")
            assert r.status_code == 200, r.text
            assert "items" in r.json() and "total" in r.json(), r.json()

            # 未登录 ⇒ 401
            assert TestClient(main.app).get("/api/v1/ocr/meta").status_code == 401
            print("INTEG-OK")
        """)
        _assert_ok(result)
        self.assertIn("INTEG-OK", result.stdout)

    def test_ocr_permission_denied(self):
        """自建空权限角色 ⇒ 403（证明权限判据真的在起作用，而非"谁都能看"）。"""
        result = _run("""
            import sys, os
            sys.path.insert(0, ".")
            from fastapi.testclient import TestClient
            import main
            from security import init_security_db, create_user
            from engine import rbac as R
            init_security_db(); R.ensure_rbac_schema()
            R.create_role("p12_noview", "P1-2 无资料查看权", [])
            uid = create_user("p12noright", "P1-2-NoRight-2026!", role="user")
            R.assign_user_roles(uid, ["p12_noview"])
            c = TestClient(main.app)
            assert c.post("/api/v1/auth/login",
                          json={"username": "p12noright",
                                "password": "P1-2-NoRight-2026!"}).status_code == 200
            resp = c.get("/api/v1/ocr/meta")
            assert resp.status_code == 403, (resp.status_code, resp.text[:200])
            assert "document.view" in (resp.json().get("detail") or ""), resp.json()
            print("PERM-OK")
        """)
        _assert_ok(result)
        self.assertIn("PERM-OK", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
