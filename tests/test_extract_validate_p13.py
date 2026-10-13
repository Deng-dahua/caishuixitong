# -*- coding: utf-8 -*-
"""P1-3 数据校验规则扩展 —— 单元测试 + 集成测试 + 反向判据。

★ 判据口径
  · **齐备性**：12 条校验规则（P1-3 由 6 扩到 12）全部有中文名，且与
    `config/standard_fields.json::_validation` 的键集合**完全一致**。
  · **可触发**：6 条新规则各自能被针对性样例触发（不是"写了代码但从不生效"）。
  · **反敏感**：把规则的判据常量改掉 ⇒ 该规则**不再触发**（证明判据真的在读它，
    而不是恒真/恒假的空转判据）。
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

ADMIN_USER = "p13admin"
ADMIN_PASS = "P1-3-Admin-Pass-2026!"


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


class ValidateRulesUnitTests(unittest.TestCase):
    def test_rules_manifest_and_sync(self):
        result = _run("""
            import json, sys
            sys.path.insert(0, ".")
            from engine.extract_validate import RULES, RULE_CN
            d = json.load(open("config/standard_fields.json", encoding="utf-8"))

            assert len(RULES) == 12, RULES
            assert len(set(RULES)) == 12, "规则名重复"
            for r in RULES:
                assert RULE_CN.get(r), ("缺中文名", r)
            # 规则清单 ↔ 配置说明表**必须同集合**（新增规则须两处同步）
            assert set(RULES) == set(d["_validation"].keys()), (
                set(RULES) ^ set(d["_validation"].keys()))
            print("MANIFEST-OK")
        """)
        _assert_ok(result)
        self.assertIn("MANIFEST-OK", result.stdout)

    def test_six_new_rules_actually_fire(self):
        """6 条新规则各自被**针对性样例**触发（防"写了但从不生效"）。"""
        result = _run("""
            import sys
            sys.path.insert(0, ".")
            from engine.extract_validate import validate_rows

            def fired(rows, want):
                got = {i["rule"] for i in validate_rows(rows)}
                assert want in got, (want, sorted(got))

            # ⑦ 金额异常负值（报表类）
            fired([{"资产总计": "-100"}], "amount_negative")
            # ⑧ 关键列缺失率过高（3 行只 1 行有值 ⇒ 33% < 50%）
            fired([{"购方名称": "A"}, {"购方名称": ""}, {"购方名称": ""}], "null_rate")
            # ⑨ 日期超出合理范围
            fired([{"开票日期": "1990-01-01"}], "date_out_of_range")
            # ⑩ 科目编码格式异常
            fired([{"科目编码": "A1"}], "account_code_format")
            # ⑪ 税率非标准档位
            fired([{"税率": "7%"}], "tax_rate_validity")
            # ⑫ 发票号码重复
            fired([{"发票号码": "X"}, {"发票号码": "X"}], "duplicate_invoice_no")

            # ---- 反向：**不该报**的不能报（借贷列负值=红字冲销，不是"报表负值"）----
            got = {i["rule"] for i in validate_rows([{"本期借方": "-50", "本期贷方": "0"}])}
            assert "amount_negative" not in got, "借贷列负值被误判为报表负值"

            # ---- 反向：全空行 / 空表不产出"新规则"噪声 ----
            empty = validate_rows([])
            assert empty == [], empty
            blank = {i["rule"] for i in validate_rows([{}])}
            for r in ("amount_negative", "date_out_of_range", "tax_rate_validity",
                      "duplicate_invoice_no", "account_code_format"):
                assert r not in blank, ("空行竟触发", r)
            print("FIRE-OK")
        """)
        _assert_ok(result)
        self.assertIn("FIRE-OK", result.stdout)

    def test_judgement_constants_are_actually_read(self):
        """反敏感：改判据常量 ⇒ 规则行为随变（防恒真/恒假空转判据）。"""
        result = _run("""
            import sys
            sys.path.insert(0, ".")
            import engine.extract_validate as V

            rows = [{"税率": "7%"}]
            assert "tax_rate_validity" in {i["rule"] for i in V.validate_rows(rows)}
            old = V.STD_TAX_RATES
            try:
                V.STD_TAX_RATES = (7.0,)            # 把 7% 纳入"法定档位"
                got = {i["rule"] for i in V.validate_rows(rows)}
                assert "tax_rate_validity" not in got, "改了档位表却仍报 ⇒ 判据没读常量"
            finally:
                V.STD_TAX_RATES = old
            assert "tax_rate_validity" in {i["rule"] for i in V.validate_rows(rows)}

            # 填充率下限同理
            rows2 = [{"购方名称": "A"}, {"购方名称": ""}, {"购方名称": ""}]
            assert "null_rate" in {i["rule"] for i in V.validate_rows(rows2)}
            oldf = V._FILL_FLOOR
            try:
                V._FILL_FLOOR = 0.0                 # 禁用该判据
                assert "null_rate" not in {i["rule"] for i in V.validate_rows(rows2)}
            finally:
                V._FILL_FLOOR = oldf
            print("SENSITIVE-OK")
        """)
        _assert_ok(result)
        self.assertIn("SENSITIVE-OK", result.stdout)


class ValidateRulesIntegrationTests(unittest.TestCase):
    def test_parse_meta_exposes_twelve_rules_and_notes(self):
        """P1-1 的 `/parse/meta` 必须暴露 12 条校验规则与判定口径说明（供前端与审计引用）。"""
        result = _run("""
            import sys, os
            sys.path.insert(0, ".")
            from fastapi.testclient import TestClient
            import main
            from security import init_security_db, create_user
            init_security_db()
            create_user("p13pm", "P1-3-PM-Pass-2026!", role="admin")
            c = TestClient(main.app)
            assert c.post("/api/v1/auth/login",
                          json={"username": "p13pm",
                                "password": "P1-3-PM-Pass-2026!"}).status_code == 200
            j = c.get("/api/v1/parse/meta").json()
            assert len(j["validation"]) == 12, j["validation"]
            assert len(j["validation_notes"]) == 12, j["validation_notes"]
            assert set(j["validation"]) == set(j["validation_notes"]), (
                set(j["validation"]) ^ set(j["validation_notes"]))
            print("PARSE-META-OK")
        """)
        _assert_ok(result)
        self.assertIn("PARSE-META-OK", result.stdout)

    def test_meta_exposes_twelve_rules(self):
        result = _run("""
            import sys, os
            sys.path.insert(0, ".")
            from fastapi.testclient import TestClient
            import main
            from security import init_security_db, create_user
            init_security_db()
            create_user("p13int", "P1-3-Int-Pass-2026!", role="admin")
            c = TestClient(main.app)
            assert c.post("/api/v1/auth/login",
                          json={"username": "p13int",
                                "password": "P1-3-Int-Pass-2026!"}).status_code == 200
            m = c.get("/api/v1/extract/meta")
            assert m.status_code == 200, m.text
            j = m.json()
            # ★ `rules` 是既有形状 `[{value,label}]`（P0-3 定义，**不改**）
            assert len(j["rules"]) == 12, j["rules"]
            for it in j["rules"]:
                assert it.get("value") and it.get("label"), it
            print("INTEG-OK rules=%d" % len(j["rules"]))
        """)
        _assert_ok(result)
        self.assertIn("INTEG-OK", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
