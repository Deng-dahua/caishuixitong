# -*- coding: utf-8 -*-
"""项目画像（企业工商信息 + 稽查要素）与资料页删除入口 —— 回归测试。

来源（用户 2026-10-18 三条要求）：
  ① 侧边栏「稽查项目」→「稽查项目管理」；
  ② 稽查项目管理列表：行业/地区/稽查期间等**在建项目这一步收集填列**，
     并补企业重点工商信息（法定代表人/注册资本/成立日期/登记状态/注册地址/经营范围/公司类型）；
  ③ 资料上传与管理：**删除每一行的删除按钮**。

隔离方式沿用 `tests/test_project_api.py`：**子进程 + `APP_DATA_DIR` 临时目录**，
走真实 Service 链路，不污染 `data/`。

★ 含反向判据（不是只有正例）：
  · 缺稽查要素 ⇒ `profile_missing` 必须**逐项列出**（不得静默补默认值）；
  · 日期/资本非法 ⇒ 必须 400（不得"尽力猜"）；
  · 资料页不得再有行内删除按钮，且**权限配置不得还指着已删的按钮**（防悬挂登记）。
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(script: str, *, timeout: int = 240) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as directory:
        environment = os.environ.copy()
        environment.update({
            "APP_DATA_DIR": directory,
            "APP_COOKIE_SECURE": "0",
            "APP_ADMIN_USERNAME": "profileadmin",
            "APP_ADMIN_PASSWORD": "Profile-Test-2026!",
            "APP_LLM_MASTER_KEY": base64.urlsafe_b64encode(
                bytes(range(32))).decode("ascii"),
        })
        return subprocess.run([sys.executable, "-c", textwrap.dedent(script)],
                              cwd=ROOT, env=environment,
                              capture_output=True, text=True, timeout=timeout)


class ProjectProfileServiceTests(unittest.TestCase):
    """Service 层：画像字段落库 / 缺项标注 / 非法值拒绝 / 同步内部账套。"""

    def test_create_persists_profile_and_normalizes_values(self):
        result = _run(
            """
            import json
            from security import SessionContext
            from engine import project_service as SVC

            sess = SessionContext(
                user_id=1, username="unitadmin", role="admin",
                allowed_company_ids=frozenset(), selected_company_id=None,
                csrf_hash="", expires_at=0,
            )
            p = SVC.create_project({
                "name": "画像落库企业", "taxpayer_id": "91440300MA5PROF001",
                "industry": "制造业", "region": "广东省深圳市",
                "period_start": "2024-01-01", "period_end": "2024-12-31",
                "tax_scopes": ["增值税", "印花税"],
                "legal_representative": "张三",
                "registered_capital": 5000,
                "established_date": "2016/3/8",
                "registration_status": "存续（在营、开业、在册）",
                "registered_address": "深圳市南山区某路 1 号",
                "business_scope": "电子元器件研发、生产与销售。",
                "company_type": "有限责任公司",
            }, sess)
            print("JSON:" + json.dumps(p, ensure_ascii=False))
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        payload = json.loads(result.stdout.split("JSON:", 1)[1].strip().splitlines()[0])
        # 画像字段逐项落库
        self.assertEqual(payload["legal_representative"], "张三")
        self.assertEqual(payload["registered_capital"], 5000.0)
        self.assertEqual(payload["established_date"], "2016-03-08",
                         "日期应归一为 YYYY-MM-DD（2016/3/8 ⇒ 2016-03-08）")
        self.assertEqual(payload["registration_status"], "存续（在营、开业、在册）")
        self.assertEqual(payload["registered_address"], "深圳市南山区某路 1 号")
        self.assertEqual(payload["company_type"], "有限责任公司")
        # 稽查要素
        self.assertEqual(payload["industry"], "制造业")
        self.assertEqual(payload["region"], "广东省深圳市")
        self.assertEqual(payload["period_start"], "2024-01-01")
        self.assertEqual(payload["tax_scopes"], ["增值税", "印花税"])
        # 完整度
        self.assertTrue(payload["profile_complete"], payload["profile_missing"])
        self.assertEqual(payload["profile_missing"], [])

    def test_missing_audit_fields_are_flagged_not_defaulted(self):
        """只给名称+税号 ⇒ 五类稽查要素必须**逐项列出**，且不得编造默认值。"""
        result = _run(
            """
            import json
            from security import SessionContext
            from engine import project_service as SVC

            sess = SessionContext(
                user_id=1, username="unitadmin", role="admin",
                allowed_company_ids=frozenset(), selected_company_id=None,
                csrf_hash="", expires_at=0,
            )
            p = SVC.create_project({"name": "缺要素企业",
                                    "taxpayer_id": "91440300MA5MISS001"}, sess)
            out = {k: p[k] for k in ("industry", "region", "period_start", "period_end",
                                     "tax_scopes", "registered_capital",
                                     "profile_missing", "profile_complete")}
            print("JSON:" + json.dumps(out, ensure_ascii=False))
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        payload = json.loads(result.stdout.split("JSON:", 1)[1].strip().splitlines()[0])
        self.assertEqual(payload["profile_missing"],
                         ["行业", "地区", "稽查期间起", "稽查期间止", "税种范围"])
        self.assertFalse(payload["profile_complete"])
        # 缺失 ≠ 默认值：不得出现"未分类"、0、占位日期
        self.assertEqual(payload["industry"], "")
        self.assertEqual(payload["region"], "")
        self.assertIsNone(payload["registered_capital"], "缺失的注册资本必须是 None，不是 0")

    def test_invalid_date_and_capital_are_rejected(self):
        result = _run(
            """
            import json
            from security import SessionContext
            from engine import project_service as SVC

            sess = SessionContext(
                user_id=1, username="unitadmin", role="admin",
                allowed_company_ids=frozenset(), selected_company_id=None,
                csrf_hash="", expires_at=0,
            )
            base = {"name": "非法值企业", "taxpayer_id": "91440300MA5BADV001"}
            out = {}
            for key, val in (("established_date", "2016-13-40"),
                             ("established_date", "不是日期"),
                             ("registered_capital", -1)):
                try:
                    SVC.create_project(dict(base, **{key: val}), sess)
                    out[key + "=" + str(val)] = "ACCEPTED"
                except SVC.ProjectError as e:
                    out[key + "=" + str(val)] = "%d:%s" % (e.status, e.message)
            print("JSON:" + json.dumps(out, ensure_ascii=False))
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        payload = json.loads(result.stdout.split("JSON:", 1)[1].strip().splitlines()[0])
        for key, value in payload.items():
            self.assertTrue(value.startswith("400:"),
                            "非法值竟被接受或不是 400：%s → %s" % (key, value))

    def test_company_sync_carries_profile(self):
        """项目是录入点、内部账套是派生：同步后工商信息必须落到 companies。"""
        result = _run(
            """
            import json, os, sqlite3
            from database import init_db
            init_db()
            from security import SessionContext
            from engine import project_service as SVC

            sess = SessionContext(
                user_id=1, username="unitadmin", role="admin",
                allowed_company_ids=frozenset(), selected_company_id=None,
                csrf_hash="", expires_at=0,
            )
            p = SVC.create_project({
                "name": "同步企业", "taxpayer_id": "91440300MA5SYNC001",
                "industry": "建筑安装", "region": "广东省深圳市",
                "period_start": "2024-01-01", "period_end": "2024-12-31",
                "tax_scopes": ["增值税"],
                "legal_representative": "李四", "registered_capital": 3000,
                "established_date": "2018-06-01",
                "registered_address": "深圳市福田区某大厦",
                "business_scope": "房屋建筑工程施工。",
                "company_type": "有限责任公司",
            }, sess)
            cid = SVC.ensure_company_for_project(sess, p)
            con = sqlite3.connect(os.path.join(os.environ["APP_DATA_DIR"], "accounting.db"))
            con.row_factory = sqlite3.Row
            row = dict(con.execute(
                "SELECT name, uscc, industry_code, legal_representative, registered_capital,"
                " established_date, address, business_scope, company_type"
                " FROM companies WHERE id=?", (cid,)).fetchone())
            print("JSON:" + json.dumps(row, ensure_ascii=False, default=str))
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        row = json.loads(result.stdout.split("JSON:", 1)[1].strip().splitlines()[0])
        self.assertEqual(row["legal_representative"], "李四")
        self.assertEqual(row["established_date"], "2018-06-01")
        self.assertEqual(row["address"], "深圳市福田区某大厦")
        # 中文行业名 → 英文 industry_code（映射来源 = config/industry_params.json）
        self.assertEqual(row["industry_code"], "construction")


class ProjectProfileDictionaryTests(unittest.TestCase):
    """字典必须由后端单一下发（前端不硬编码选项）。"""

    def test_meta_exposes_profile_dicts(self):
        from engine.project_service import metadata
        meta = metadata()
        self.assertGreaterEqual(len(meta["industries"]), 5, "行业字典为空")
        self.assertGreaterEqual(len(meta["regions"]), 31, "地区字典不完整")
        self.assertGreaterEqual(len(meta["tax_types"]), 18, "税种字典不完整")
        self.assertTrue(meta["registration_statuses"])
        self.assertTrue(meta["company_types"])
        self.assertEqual(meta["capital_unit"], "万元")
        keys = [f["key"] for f in meta["profile_fields"]]
        for k in ("legal_representative", "registered_capital", "established_date",
                  "registration_status", "registered_address", "business_scope",
                  "company_type"):
            self.assertIn(k, keys, "画像字段未登记：%s" % k)
        self.assertEqual([f["key"] for f in meta["audit_fields"]],
                         ["industry", "region", "period_start", "period_end", "tax_scopes"])

    def test_tax_types_come_from_levy_authority(self):
        """税种下拉必须来自 `levy_nature`（唯一权威），不得另写一份名单。"""
        from engine.levy_nature import tax_scope_options
        from engine.project_service import metadata
        values = [t["value"] for t in metadata()["tax_types"]]
        self.assertEqual(values, tax_scope_options())
        for must in ("增值税", "企业所得税", "个人所得税", "印花税"):
            self.assertIn(must, values)


class FrontendContractTests(unittest.TestCase):
    """前端交付契约：文案、入口与权限登记必须一一对应。"""

    def _read(self, rel: str) -> str:
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_sidebar_label_renamed(self):
        html = self._read("static/index.html")
        self.assertIn("稽查项目管理", html)
        self.assertNotIn('<span class="icon">📂</span> 稽查项目\n', html,
                         "侧边栏仍残留旧文案「稽查项目」")
        # 页面标题本来就是「稽查项目管理」，改名后应保持唯一说法
        self.assertIn("稽查项目管理", self._read("static/projects.html"))

    def test_project_list_shows_profile_columns(self):
        html = self._read("static/projects.html")
        for th in ("法定代表人", "注册资本", "成立日期", "登记状态",
                   "行业", "地区", "稽查期间"):
            self.assertIn("<th>%s</th>" % th, html, "列表缺列：%s" % th)
        # 表单必须能收集（不是只显示）
        for fid in ("pf-legal_representative", "pf-registered_capital",
                    "pf-established_date", "pf-registration_status",
                    "pf-registered_address", "pf-business_scope",
                    "pf-company_type", "pf-industry", "pf-region",
                    "pf-ps", "pf-pe", "pf-tax-scopes"):
            self.assertIn('id="%s"' % fid, html, "表单缺输入项：%s" % fid)
        self.assertNotIn("发起分析后由系统自动分析确定", html,
                         "旧口径（行业/地区由分析后确定）未清除")

    def test_documents_has_no_row_delete_button(self):
        js = self._read("static/js/documents.js")
        html = self._read("static/documents.html")
        self.assertNotIn('data-act="del"', js, "资料列表仍有行内删除按钮")
        self.assertNotIn('id="m-del"', html, "删除弹窗未清理（无入口的死代码）")
        self.assertNotIn("btn-del-confirm", html + js, "确认删除按钮残留")
        # 反向：删除能力本身不能消失（批量删除 + 后端出口仍在）
        self.assertIn("btn-del-selected", html)
        self.assertIn("__delSelected", js)

    def test_frontend_perm_config_has_no_dangling_entries(self):
        """权限配置里登记的入口必须真实存在（删按钮必须同步删登记）。"""
        cfg = json.loads(self._read("config/frontend_perms.json"))
        ids = [x.get("id") for x in cfg["pages"]["documents.html"]]
        self.assertNotIn("btn-del-confirm", ids)
        markers = [x.get("marker") for x in cfg["dynamic_entries"]["static/js/documents.js"]]
        self.assertNotIn('data-act=\\"del\\"', markers)
        # 静态入口：id 必须能在 html 里找到
        docs_html = self._read("static/documents.html")
        for entry in cfg["pages"]["documents.html"]:
            self.assertIn('id="%s"' % entry["id"], docs_html,
                          "配置登记的入口在页面不存在：%s" % entry["id"])


if __name__ == "__main__":
    unittest.main()
