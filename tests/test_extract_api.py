# -*- coding: utf-8 -*-
"""P0-3 解析与标准化 —— 四类测试（单元 / 集成 / 准确率 / 人工校正）+ 反向验证。

隔离方式：**子进程 + `APP_DATA_DIR` 临时目录**（与 P0-1/P0-2 同模式）—— 走**真实链路**
（认证中间件 / 真实 SQLite / 真实解析器 / 真实 xlsx 字节），数据落临时目录 ⇒ 不污染 `data/`。

四类（任务书要求）：
  ① `ExtractUnitTests`          单元测试：解析、映射、校验
  ② `ExtractIntegrationTests`   集成测试：上传 → 解析 → 标准化（含**回链**与幂等重建）
  ③ `ExtractAccuracyTests`      常见格式解析准确率（**阈值 ≥ 90%**，实际值现场打印）
  ④ `ExtractCorrectionTests`    人工校正（含**非法值必须 400**的反向判据）

★ 准确率口径（**必须写明，否则数字无意义**）
  = 「8 类常见资料的 38 个**预期标准字段**中，能被正确取出并归一成功的比例」。
  · **含**既有解析器的类型识别影响（不回避）；
  · **不含**"本字典未声明"的字段（不拿字典外的字段刷分）。
  · 同一份资料重复出现在（资料类型 × 字段）矩阵里，故既测"能不能认"也测"取得对不对"。
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

ADMIN_USER = "integrationadmin"
ADMIN_PASS = "Integration-Test-2026!"


def _run(script: str, *, timeout: int = 480, dedent: bool = True) -> subprocess.CompletedProcess:
    """在隔离的 `APP_DATA_DIR` 里跑一段脚本。

    `dedent=False`：脚本由调用方**自行分段去缩进**后传入（用于"公共前缀 + 测试体"拼接：
    拼接后整体最小缩进为 0，再 dedent 不生效 ⇒ 后半段会保留缩进而顶层不可缩进）。
    """
    if dedent:
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
        })
        return subprocess.run([sys.executable, "-c", script],
                              cwd=ROOT, env=environment,
                              capture_output=True, text=True, timeout=timeout)


# 8 类常见资料（名称, 表内容, 预期可提取的标准字段）—— 供 ①③④ 共用
_CASES_SRC = textwrap.dedent('''
import os, tempfile
import openpyxl

CASES = [
 ("科目余额表2024.xlsx",
  [["科目编码","科目名称","期初借方","期初贷方","本期借方","本期贷方","期末借方","期末贷方"],
   ["1001","库存现金",1000,0,500,200,1300,0],
   ["1002","银行存款",50000,0,20000,10000,60000,0],
   ["2202","应付账款",0,30000,10000,0,0,20000],
   ["6001","主营业务收入",0,0,0,80000,0,80000],
   ["6401","主营业务成本",0,0,60000,0,60000,0]],
  ["account_code","account_name","opening_debit","current_debit","closing_credit"]),
 ("销项发票明细.xlsx",
  [["发票号码","开票日期","购方名称","销方名称","货物或应税劳务名称","金额","税额","价税合计"],
   ["00012345","2024-03-15","甲公司","乙公司","技术服务",10000,600,10600],
   ["00012346","2024-03-20","丙公司","乙公司","软件开发",20000,1200,21200]],
  ["invoice_no","invoice_date","buyer","seller","goods","invoice_amount","invoice_tax","invoice_total"]),
 ("采购发票明细.xlsx",
  [["发票号码","开票日期","购方名称","销方名称","货物或应税劳务名称","金额","税额","价税合计"],
   ["00020001","2024-04-01","乙公司","丁公司","原材料",30000,3900,33900]],
  ["invoice_no","invoice_date","buyer","seller","goods","invoice_amount","invoice_tax"]),
 ("银行流水2024.xlsx",
  [["交易日期","对方户名","借方金额","贷方金额","余额"],
   ["2024-01-05","甲公司",5000,0,95000],
   ["2024-01-08","乙公司",0,12000,107000]],
  ["tx_date","counterparty","debit","credit","balance"]),
 ("增值税申报表.xlsx",
  [["税种","销售额","应纳税额"],["增值税",100000,3000]],
  ["tax_type","taxable_amount","tax_payable"]),
 ("工资表2024.xlsx",
  [["姓名","部门","应发工资"],["张三","财务部",12000],["李四","销售部",9000]],
  ["person_name","salary_pay","salary_dept"]),
 ("资产负债表2024.xlsx",
  [["项目","期末余额"],["资产总计",500000],["负债合计",200000],["所有者权益合计",300000]],
  ["total_assets","total_liabilities","total_equity"]),
 ("现金日记账.xlsx",
  [["科目编码","科目名称","本期借方","本期贷方"],["1001","库存现金",2000,1500]],
  ["account_code","account_name","current_debit"]),
]


def make_xlsx(rows, name):
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    p = os.path.join(tempfile.mkdtemp(), name)
    wb.save(p)
    return p
''')


# --------------------------------------------------------------------------
# ① 单元测试：解析、映射、校验
# --------------------------------------------------------------------------
class ExtractUnitTests(unittest.TestCase):
    def test_field_mapping_and_validation_rules(self):
        result = _run(
            """
            from engine.standard_fields import (
                aliases_of, fields, to_standard_period, normalize_value, value_from_row,
                required_names, metadata,
            )
            from engine.extract_validate import RULES, RULE_CN, validate_rows, summary

            # 1) 字典完整：49 个标准字段（P1-1）、13 条校验规则（P1-3 由 6 扩到 12；2026-10-19 +bank_balance_check）
            assert len(fields()) >= 49, len(fields())
            assert len(RULES) == 13, RULES
            for r in RULES:
                assert RULE_CN.get(r), "规则缺中文名：%s" % r

            # 2) 别名**复用 fieldkit 常量**（不抄第二份）
            from engine import fieldkit as FK
            assert aliases_of("buyer")[:3] == list(FK.BUYER_KEYS)[:3], aliases_of("buyer")
            assert aliases_of("seller")[:2] == list(FK.SELLER_KEYS)[:2]
            assert aliases_of("account_code")[:2] == list(FK.ACCOUNT_CODE_KEYS)[:2]

            # 3) 期间归一（含真实解析器会产出的 `YYYYMMDD` 8 位格式）
            for raw, want in [("2024-01","2024-01"), ("202401","2024-01"),
                              ("2024年1月","2024-01"), ("2024/01","2024-01"),
                              ("20240105","2024-01-05"), ("2024年第2季度","2024-Q2"),
                              ("2024","2024")]:
                got, ok = to_standard_period(raw)
                assert ok and got == want, (raw, got, want)
            for bad in ("乱写", "01", "999", ""):
                assert to_standard_period(bad)[1] is False, bad

            # 4) 金额归一（numparse 同口径）
            assert normalize_value("invoice_amount", "1,234.56")[0] == 1234.56
            assert normalize_value("invoice_amount", "￥100")[0] == 100.0
            assert normalize_value("invoice_amount", "(50)")[0] == -50.0
            assert normalize_value("invoice_amount", "abc")[1] is False
            assert normalize_value("invoice_amount", "")[1] is False

            # 5) 行内取值按别名优先级
            row = {"inv_no": "0001", "发票号码": "9999"}
            # 别名**顺序即优先级**：配置里「发票号码」在 `inv_no` 之前 ⇒ 取前者
            assert value_from_row("invoice_no", row) == "9999", value_from_row("invoice_no", row)
            assert value_from_row("invoice_no", {"inv_no": "0001"}) == "0001"
            assert value_from_row("buyer", {"购方名称": "甲公司"}) == "甲公司"
            assert value_from_row("buyer", {"毫无关系的列": "x"}) is None

            # 6) 校验①必填缺失
            iss = validate_rows([{"科目编码": "1001"}], domain="ledger",
                                standard_names=["account_code", "account_name", "period"])
            rules = {i["rule"] for i in iss}
            assert "required_missing" in rules, rules             # account_name/period 缺
            assert all(i["rule_cn"] for i in iss)

            # 7) 校验②金额格式错误（逐行，带行号）
            iss = validate_rows([{"金额": "100"}, {"金额": "abc"}],
                                standard_names=["invoice_amount"])
            amt = [i for i in iss if i["rule"] == "amount_format"]
            assert amt and amt[0]["severity"] == "error", iss
            assert amt[0]["detail"]["items"][0]["row"] == 2, amt[0]["detail"]
            assert amt[0]["detail"]["items"][0]["raw"] == "abc"

            # 8) 校验③期间错配（**给了期望期间才判**）
            rows = [{"期间": "2024-03"}, {"期间": "2024-04"}]
            assert not [i for i in validate_rows(rows, standard_names=["period"]) 
                        if i["rule"] == "period_mismatch"], "未给期望期间却报了错配"
            iss = validate_rows(rows, standard_names=["period"], expect_period="2024-03")
            pm = [i for i in iss if i["rule"] == "period_mismatch"]
            assert pm and "2024-04" in pm[0]["detail"]["found"], iss

            # 9) 校验④重复数据
            dup = [{"科目编码": "1001", "科目名称": "现金"},
                   {"科目编码": "1001", "科目名称": "现金"},
                   {"科目编码": "1002", "科目名称": "银行"}]
            iss = validate_rows(dup, standard_names=["account_code", "account_name"])
            d = [i for i in iss if i["rule"] == "duplicate"]
            assert d and d[0]["detail"]["items"][0]["row"] == 2, iss

            # 10) 校验⑤借贷不平衡（**缺一侧 ⇒ 跳过，不伪装通过**）
            bal = [{"借方": 100, "贷方": 100}, {"借方": 200, "贷方": 150}]
            iss = validate_rows(bal, standard_names=["debit", "credit"])
            ub = [i for i in iss if i["rule"] == "debit_credit_unbalanced"]
            assert ub and ub[0]["detail"]["diff"] == 50.0, iss
            # 只有借方 ⇒ 无法判定 ⇒ **不报**
            iss2 = validate_rows([{"借方": 100}], standard_names=["debit"])
            assert not [i for i in iss2 if i["rule"] == "debit_credit_unbalanced"], iss2
            # 恰好平衡 ⇒ 不报
            iss3 = validate_rows([{"借方": 100, "贷方": 100}], standard_names=["debit", "credit"])
            assert not [i for i in iss3 if i["rule"] == "debit_credit_unbalanced"], iss3

            # 11) 校验⑥报表勾稽（三项缺一 ⇒ 跳过）
            rep = [{"资产总计": 500, "负债合计": 200, "所有者权益合计": 250}]
            iss = validate_rows(rep, standard_names=["total_assets", "total_liabilities",
                                                     "total_equity"])
            cc = [i for i in iss if i["rule"] == "cross_check"]
            assert cc and cc[0]["detail"]["diff"] == 50.0, iss
            iss2 = validate_rows([{"资产总计": 500, "负债合计": 200}],
                                 standard_names=["total_assets", "total_liabilities"])
            assert not [i for i in iss2 if i["rule"] == "cross_check"], iss2

            # 12) 汇总
            s = summary(iss)
            assert "total" in s and "by_rule_cn" in s, s

            # 13) meta 声明了"复用现有"与"沿用现有表"（可核对，防后人误以为另写解析器）
            from engine.extract_service import metadata as svc_meta
            m = svc_meta()
            assert m["parser_reuse"]["excel_csv"].startswith("main."), m["parser_reuse"]
            assert m["parser_reuse"]["image_ocr"].startswith("main."), m["parser_reuse"]
            assert m["parser_reuse"]["pdf"].startswith("pdfplumber"), m["parser_reuse"]
            assert "sales_invoices" in m["tables"]["reused_existing"]["invoices"], m["tables"]
            assert m["tables"]["optional_not_built"], m["tables"]

            print("EXTRACT UNIT TESTS PASSED")
            """
        )
        self.assertEqual(result.returncode, 0,
                         msg="stdout:\n%s\nstderr:\n%s" % (result.stdout, result.stderr))


# --------------------------------------------------------------------------
# ② 集成测试：上传 → 解析 → 标准化
# --------------------------------------------------------------------------
class ExtractIntegrationTests(unittest.TestCase):
    def test_upload_parse_standardize_end_to_end(self):
        result = _run(
            textwrap.dedent(_CASES_SRC) + textwrap.dedent("""
            import sqlite3
            from fastapi.testclient import TestClient
            from main import app

            base = "/api/v1"
            with TestClient(app) as client:
                assert client.get(base + "/extract/meta").status_code == 401   # 未登录

                client.post("/api/auth/login",
                            json={"username": "integrationadmin",
                                  "password": "Integration-Test-2026!"})
                h = {"X-CSRF-Token": client.cookies.get("csrf_token")}
                cid = client.post("/api/companies", headers=h,
                                  json={"name": "解析集成账套",
                                        "uscc": "91440300MA5EX10001"}).json()["id"]
                client.post("/api/auth/select-company", headers=h, json={"company_id": cid})
                pid = client.post(base + "/projects", headers=h,
                                  json={"name": "解析集成项目", "company_id": cid,
                                        "period_start": "2024-01",
                                        "period_end": "2024-12"}).json()["id"]

                # 上传一份科目余额表（P0-2 链路）
                p = make_xlsx(CASES[0][1], CASES[0][0])
                with open(p, "rb") as fh:
                    blob = fh.read()
                up = client.post(base + "/projects/%d/documents" % pid, headers=h, files=[
                    ("files", (CASES[0][0], blob, "application/octet-stream"))])
                assert up.status_code == 201, up.text
                did = up.json()["uploaded"][0]["id"]

                # 字典
                meta = client.get(base + "/extract/meta")
                assert meta.status_code == 200, meta.text
                assert len(meta.json()["standard_fields"]["fields"]) >= 49
                assert len(meta.json()["rules"]) == 13
                # 字典须说明"沿用现有"（不新建同义表）
                assert meta.json()["tables"]["optional_not_built"], meta.json()["tables"]
                assert "sales_invoices" in meta.json()["tables"]["reused_existing"]["invoices"]

                # 解析
                r = client.post(base + "/documents/%d/extract" % did, headers=h)
                assert r.status_code == 200, r.text
                j = r.json()
                assert j["tables"], "未产出解析表"
                assert j["fields"], "未标准化出任何标准字段"
                got = {f["standard_field"] for f in j["fields"]}
                assert {"account_code", "account_name", "opening_debit"} <= got, got

                # 作业状态可查（复用 analysis_jobs）
                assert j.get("job_id"), j
                jb = client.get(base + "/extract/jobs/%s" % j["job_id"])
                assert jb.status_code == 200, jb.text
                assert jb.json()["status_cn"] == "已完成", jb.json()

                # ★ 回链：每个字段带 source_ref（sheet/row/raw）
                g = client.get(base + "/documents/%d/extracted" % did).json()
                f0 = [x for x in g["fields"] if x["standard_field"] == "account_code"][0]
                assert f0["source"].get("row") == 1, f0["source"]
                assert f0["source"].get("raw") == "1001", f0["source"]
                assert g["source_trace"]["md5"], g["source_trace"]     # 原件指纹（可回链）

                # 解析产物落库
                conn = sqlite3.connect(os.path.join(os.environ["APP_DATA_DIR"], "accounting.db"))
                nt = conn.execute("SELECT COUNT(*) FROM extracted_tables WHERE document_id=?",
                                  (did,)).fetchone()[0]
                nf = conn.execute("SELECT COUNT(*) FROM extracted_fields WHERE document_id=?",
                                  (did,)).fetchone()[0]
                assert nt >= 1 and nf >= 3, (nt, nf)

                # ★ 幂等重建：重复解析**不累积**（登记行数不变）
                r2 = client.post(base + "/documents/%d/extract" % did, headers=h)
                assert r2.status_code == 200, r2.text
                nt2 = conn.execute("SELECT COUNT(*) FROM extracted_tables WHERE document_id=?",
                                   (did,)).fetchone()[0]
                nf2 = conn.execute("SELECT COUNT(*) FROM extracted_fields WHERE document_id=?",
                                   (did,)).fetchone()[0]
                assert (nt, nf) == (nt2, nf2), "重复解析造成登记累积：%s -> %s" % ((nt, nf), (nt2, nf2))

                # 项目级校验异常清单
                li = client.get(base + "/projects/%d/extract-issues" % pid)
                assert li.status_code == 200, li.text
                assert "summary" in li.json(), li.json()

                # PDF 资料（无文字层）⇒ **如实**报"需 OCR"而不是假装成功
                from reportlab.pdfgen import canvas
                import io as _io
                buf = _io.BytesIO()
                c = canvas.Canvas(buf)
                c.drawString(72, 720, "hello")     # 有文字层
                c.showPage(); c.save()
                up2 = client.post(base + "/projects/%d/documents" % pid, headers=h, files=[
                    ("files", ("说明.pdf", buf.getvalue(), "application/pdf"))])
                did2 = up2.json()["uploaded"][0]["id"]
                r3 = client.post(base + "/documents/%d/extract" % did2, headers=h)
                assert r3.status_code == 200, r3.text
                assert r3.json()["tables"], "PDF 有文字层却未解析出内容"

                print("EXTRACT INTEGRATION TESTS PASSED")
            """), dedent=False
        )
        self.assertEqual(result.returncode, 0,
                         msg="stdout:\n%s\nstderr:\n%s" % (result.stdout, result.stderr))


# --------------------------------------------------------------------------
# ③ 常见格式解析准确率（阈值 ≥ 90%）
# --------------------------------------------------------------------------
class ExtractAccuracyTests(unittest.TestCase):
    def test_common_format_accuracy_at_least_90_percent(self):
        result = _run(
            textwrap.dedent(_CASES_SRC) + textwrap.dedent("""
            from engine.extract_service import _parse_file
            from engine.standard_fields import normalize_value, value_from_row

            total = ok = 0
            per_case = []
            for name, rows, expect_fields in CASES:
                p = make_xlsx(rows, name)
                tables, err = _parse_file(p, ".xlsx", name)
                all_rows = []
                for t in tables:
                    all_rows += (t.get("rows") or [])
                hit = miss = 0
                for f in expect_fields:
                    v = None
                    for row in all_rows:
                        v = value_from_row(f, row)
                        if v not in (None, ""):
                            break
                    good = bool(v not in (None, "")) and normalize_value(f, v)[1]
                    total += 1
                    if good:
                        ok += 1
                        hit += 1
                    else:
                        miss += 1
                per_case.append((name, hit, miss))
                print("  %-22s 表%-2d 行%-3d 命中 %d 缺 %d"
                      % (name, len(tables), len(all_rows), hit, miss))
            rate = 100.0 * ok / total
            print("  准确率 = %d/%d = %.1f%%（阈值 90%%）" % (ok, total, rate))
            assert total == 37, "用例总数变了（防用例被静默删减）：%d" % total
            assert rate >= 90.0, "准确率 %.1f%% 低于阈值 90%%（缺 %d 项）" % (rate, total - ok)
            print("EXTRACT ACCURACY TESTS PASSED")
            """), dedent=False
        )
        self.assertEqual(result.returncode, 0,
                         msg="stdout:\n%s\nstderr:\n%s" % (result.stdout, result.stderr))


# --------------------------------------------------------------------------
# ④ 人工校正
# --------------------------------------------------------------------------
class ExtractCorrectionTests(unittest.TestCase):
    def test_correction_and_illegal_value_guard(self):
        result = _run(
            textwrap.dedent(_CASES_SRC) + textwrap.dedent("""
            import sqlite3
            from fastapi.testclient import TestClient
            from main import app

            base = "/api/v1"
            with TestClient(app) as client:
                client.post("/api/auth/login",
                            json={"username": "integrationadmin",
                                  "password": "Integration-Test-2026!"})
                h = {"X-CSRF-Token": client.cookies.get("csrf_token")}
                cid = client.post(base + "/companies" if False else "/api/companies", headers=h,
                                  json={"name": "校正账套",
                                        "uscc": "91440300MA5EX20001"}).json()["id"]
                client.post("/api/auth/select-company", headers=h, json={"company_id": cid})
                pid = client.post(base + "/projects", headers=h,
                                  json={"name": "校正项目", "company_id": cid}).json()["id"]
                p = make_xlsx(CASES[0][1], CASES[0][0])
                with open(p, "rb") as fh:
                    blob = fh.read()
                did = client.post(base + "/projects/%d/documents" % pid, headers=h, files=[
                    ("files", (CASES[0][0], blob, "application/octet-stream"))
                ]).json()["uploaded"][0]["id"]
                client.post(base + "/documents/%d/extract" % did, headers=h)
                fields = client.get(base + "/documents/%d/extracted" % did).json()["fields"]
                by = {f["standard_field"]: f for f in fields}

                # ① 金额字段校正：正常值
                fid = by["opening_debit"]["id"]
                r = client.put(base + "/extracted/%d" % fid, headers=h, json={"value": "8888.88"})
                assert r.status_code == 200, r.text
                assert r.json()["value"] == 8888.88, r.json()
                assert float(r.json()["previous_value"]) == 1000.0, r.json()   # 原值为 value_text
                assert r.json()["corrected"] is True

                # ② ★ 反向：金额字段给非法值 ⇒ **必须 400**（不得静默存错值）
                bad = client.put(base + "/extracted/%d" % fid, headers=h, json={"value": "abc"})
                assert bad.status_code == 400, ("非法金额竟被接受", bad.text)

                # ③ 文本字段给空 ⇒ 400（文本不允许空）
                tf = by["account_name"]["id"]
                assert client.put(base + "/extracted/%d" % tf, headers=h,
                                  json={"value": "   "}).status_code == 400

                # ④ 校正后：marked corrected / 原值保留 / 可查回
                g = client.get(base + "/documents/%d/extracted" % did).json()
                fix = [x for x in g["fields"] if x["id"] == fid][0]
                assert fix["corrected"] == 1, fix
                assert float(fix["original_value"]) == 1000.0, fix   # 原值**永不丢失**
                assert float(fix["value_amount"]) == 8888.88, fix
                assert fix["corrected_by"], fix                    # 留痕操作人
                assert fix["source"].get("row") == 1, fix          # 回链仍在

                # ⑤ 只筛已校正
                only = client.get(base + "/documents/%d/extracted" % did,
                                  params={"only_corrected": "1"}).json()
                assert only["fields"] and all(x["corrected"] == 1 for x in only["fields"])

                # ⑥ 审计留痕
                conn = sqlite3.connect(os.path.join(os.environ["APP_DATA_DIR"], "accounting.db"))
                n = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action='extract.correct'"
                                 ).fetchone()[0]
                assert n >= 1, "人工校正未留痕"

                # ⑦ 跨租户：他人资料 ⇒ 404（不泄露存在性）
                import security
                uid = security.create_user("exuser", "Ex-User-Pass-2026!", role="user")
                other = client.post("/api/companies", headers=h,
                                    json={"name": "他租户", "uscc": "91440300MA5EX20002"}).json()["id"]
                security.grant_company_to_user(uid, other)
                with TestClient(app) as uc:
                    uc.post("/api/auth/login",
                            json={"username": "exuser", "password": "Ex-User-Pass-2026!"})
                    uh = {"X-CSRF-Token": uc.cookies.get("csrf_token")}
                    assert uc.get(base + "/documents/%d/extracted" % did).status_code == 404
                    assert uc.put(base + "/extracted/%d" % fid, headers=uh,
                                  json={"value": "1"}).status_code == 404

                print("EXTRACT CORRECTION TESTS PASSED")
            """), dedent=False
        )
        self.assertEqual(result.returncode, 0,
                         msg="stdout:\n%s\nstderr:\n%s" % (result.stdout, result.stderr))


# --------------------------------------------------------------------------
# ⑤ 反向验证（真跑）
# --------------------------------------------------------------------------
class ExtractReverseVerification(unittest.TestCase):
    def test_reverse_amount_validation_is_real(self):
        """★ 反向验证：「金额格式校验」这条判据**真的在起作用**。

        做法：把 `standard_fields` 的金额归一临时改成"任何值都成功" ⇒
        同一个 `abc` **必须**从"400 被拒"变成"通过" ⇒ 证明拒绝来自该校验，而非偶然。
        """
        result = _run(
            """
            from security import SessionContext
            from engine import extract_service as SVC
            from engine import extract_store as EST
            from engine import project_service as PSVC
            from engine import document_service as DSVC
            from engine import standard_fields as SF
            import openpyxl, os, tempfile

            sess = SessionContext(user_id=1, username="rv", role="admin",
                                  allowed_company_ids=frozenset({1}),
                                  selected_company_id=1, csrf_hash="", expires_at=0)
            pid = PSVC.create_project({"name": "反向验证企业", "company_id": 1}, sess)["id"]
            wb = openpyxl.Workbook(); ws = wb.active
            # ★ 用**完整**科目余额表（既有解析器对 3 列单行简表不产出，属其既有行为；
            #   本反向验证要证的是"金额校验生效"，不该被解析器覆盖面干扰）
            ws.append(["科目编码", "科目名称", "期初借方", "期初贷方", "本期借方", "本期贷方"])
            ws.append(["1001", "库存现金", 1000, 0, 500, 200])
            ws.append(["1002", "银行存款", 50000, 0, 20000, 10000])
            fp = os.path.join(tempfile.mkdtemp(), "科目余额表2024.xlsx")
            wb.save(fp)
            with open(fp, "rb") as fh:
                blob = fh.read()
            up = DSVC.upload_documents(pid, [("科目余额表2024.xlsx", blob)], sess)
            did = up["uploaded"][0]["id"]
            SVC.parse_document(did, sess)
            fields = SVC.get_extracted(did, sess)["fields"]
            fid = [f for f in fields if f["standard_field"] == "opening_debit"][0]["id"]

            # ① 正常：非法金额必须被拒
            try:
                SVC.correct_field(fid, {"value": "abc"}, sess)
                raise AssertionError("非法金额竟被接受")
            except SVC.ExtractError as e:
                assert e.status == 400, e.status

            # ② 放通校验 ⇒ 同一值必须被接受（判据失效）
            orig = SF.normalize_value
            try:
                def _loose(name, value):
                    # 放通后必须返回**能 float 的**值（否则 correct_field 的 float() 仍会拦，
                    # 那就证明不了"拒绝来自金额格式校验"）
                    return 0.0, True, ""
                SF.normalize_value = _loose
                SVC.normalize_value = _loose
                r = SVC.correct_field(fid, {"value": "abc"}, sess)
                assert r["ok"], "校验被放通后仍拒 ⇒ 拒绝并非来自该校验（判据不成立）"
            finally:
                SF.normalize_value = orig
                SVC.normalize_value = orig

            # ③ 还原后再次被拒（可复现）
            try:
                SVC.correct_field(fid, {"value": "xyz"}, sess)
                raise AssertionError("还原后仍放通")
            except SVC.ExtractError as e:
                assert e.status == 400, e.status

            print("REVERSE VERIFICATION PASSED")
            """
        )
        self.assertEqual(result.returncode, 0,
                         msg="stdout:\n%s\nstderr:\n%s" % (result.stdout, result.stderr))


if __name__ == "__main__":
    unittest.main()
