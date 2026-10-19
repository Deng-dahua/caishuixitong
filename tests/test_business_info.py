# -*- coding: utf-8 -*-
"""工商信息查询：清洗 / 落库 / 缓存 / 失败语义（2026-10-18 新增）。

判据取向（按项目铁律）
----------------------
· 只断言**行为**（清洗结果、落库后能否读回、失败时返回什么），不断言"代码里有这行"；
· **缺失如实**：取不到的值必须是 `None` 并留痕，不得是 ""、"其他"、0；
· 失败**不得抛异常**（用户要求"不能阻断项目创建"）；
· 无硬编码 Key/代理 —— 用正则真的扫一遍源码（验收标准第 4 条）。
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
import unittest.mock                                     # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sqlalchemy import create_engine, text                        # noqa: E402

from engine.business_info import dto as DTO                       # noqa: E402
from engine.business_info import providers as PR                  # noqa: E402
from engine.business_info import service as SVC                   # noqa: E402
from engine.business_info import store as ST                      # noqa: E402

CFG = SVC.config()


def _eng():
    d = tempfile.mkdtemp(prefix="biz_")
    return create_engine("sqlite:///" + os.path.join(d, "t.db").replace("\\", "/"))


STATUSES = ["存续（在营、开业、在册）", "在业", "迁入", "迁出", "停业",
            "清算", "注销", "吊销", "撤销", "其他"]
TYPES = ["有限责任公司", "股份有限公司", "有限责任公司分公司", "股份有限公司分公司",
         "个人独资企业", "合伙企业", "个体工商户", "农民专业合作社", "其他"]


class CleaningTests(unittest.TestCase):
    def test_uscc_normalized_and_rejected(self):
        self.assertEqual(DTO.clean_uscc(" 91440300ma5miss001 "), "91440300MA5MISS001")
        self.assertIsNone(DTO.clean_uscc("91440300MA5MISS01"), "17 位应判非法")
        self.assertIsNone(DTO.clean_uscc(""))
        self.assertIsNone(DTO.clean_uscc("统一社会信用代码"), "取不到就是 None，不得猜")

    def test_capital_converted_to_wan(self):
        u = CFG["capital_units"]
        self.assertEqual(DTO.clean_capital("1,000万元人民币", u), (1000.0, "万元"))
        self.assertEqual(DTO.clean_capital("2亿元", u), (20000.0, "亿元"))
        self.assertEqual(DTO.clean_capital("5000000元", u), (500.0, "元"))
        self.assertEqual(DTO.clean_capital("", u), (None, None))
        self.assertEqual(DTO.clean_capital("未公示", u), (None, None))

    def test_date_normalized(self):
        for raw in ("2016/3/8", "2016年3月8日", "20160308", "2016-03-08"):
            self.assertEqual(DTO.clean_date(raw), "2016-03-08", raw)
        self.assertIsNone(DTO.clean_date("长期"))
        self.assertIsNone(DTO.clean_date("2016-13-40"))

    def test_status_prefers_earliest_occurrence(self):
        # ★ 实测坑：「吊销，未注销」曾因按长度排序被误判成「注销」
        self.assertEqual(DTO.clean_status("吊销，未注销", CFG["status_map"], STATUSES)[0], "吊销")
        self.assertEqual(DTO.clean_status("注销", CFG["status_map"], STATUSES)[0], "注销")
        self.assertEqual(DTO.clean_status("存续", CFG["status_map"], STATUSES)[0],
                         "存续（在营、开业、在册）")
        val, note = DTO.clean_status("正常", CFG["status_map"], STATUSES)
        self.assertIsNone(val, "认不出就如实返回 None")
        self.assertIn("无法归一", note or "")

    def test_scope_strips_boilerplate(self):
        s = DTO.clean_scope("钢材、建材的销售；\n依法须经批准的项目，经相关部门批准后方可开展经营活动",
                            1000, CFG["scope_rule"]["scope_stop_words"])
        self.assertNotIn("\n", s)
        self.assertNotIn("依法须经批准", s)
        self.assertIn("钢材", s)

    def test_company_type_mapped_only_to_registered_values(self):
        self.assertEqual(DTO.clean_company_type("有限责任公司(自然人投资或控股)", TYPES),
                         "有限责任公司")
        self.assertEqual(DTO.clean_company_type("个体工商户", TYPES), "个体工商户")
        self.assertIsNone(DTO.clean_company_type("外星企业", TYPES))

    def test_build_profile_records_notes_not_defaults(self):
        p = DTO.build_profile({"企业名称": "东莞市恒达钢材有限公司",
                               "统一社会信用代码": "91441900MA4W8XYZ12",
                               "注册资本": "1,000万元人民币",
                               "登记状态": "吊销，未注销",
                               "成立日期": "2016/3/8",
                               "经营范围": "钢材、建材的销售"},
                              cfg=CFG, source="unit-test", source_detail="单测")
        self.assertEqual(p.name, "东莞市恒达钢材有限公司")
        self.assertEqual(p.tax_id, "91441900MA4W8XYZ12")
        self.assertEqual(p.registered_capital, 1000.0)
        self.assertEqual(p.registration_status, "吊销")
        self.assertEqual(p.established_date, "2016-03-08")
        d = p.to_dict()
        self.assertEqual(d["source"], "unit-test")
        self.assertIn("legal_representative", d["missing"], "未提供的字段必须进 missing")


class StoreTests(unittest.TestCase):
    def test_upsert_then_get_and_link(self):
        eng = _eng()
        p = DTO.build_profile({"name": "深圳测试科技有限公司",
                               "tax_id": "91440300MA5TEST001",
                               "business_scope": "软件开发"},
                              cfg=CFG, source="unit-test", source_detail="单测")
        row = ST.upsert(p, project_id=7, engine=eng)
        self.assertEqual(row["name"], "深圳测试科技有限公司")
        self.assertEqual(row["project_id"], 7)
        got = ST.get("深圳测试科技有限公司", engine=eng)
        self.assertIsNotNone(got)
        self.assertEqual(got["tax_id"], "91440300MA5TEST001")
        self.assertEqual(got["business_scope"], "软件开发")
        # 幂等：同名再写不新增行
        ST.upsert(p, project_id=8, engine=eng)
        with eng.connect() as conn:
            n = conn.execute(text("SELECT COUNT(*) FROM sys_company_info")).scalar()
        self.assertEqual(n, 1, "同名只应有一条档案")
        # 关联项目
        self.assertTrue(ST.link_project("深圳测试科技有限公司", 9, engine=eng))
        self.assertEqual(ST.get("深圳测试科技有限公司", engine=eng)["project_id"], 9)

    def test_name_key_ignores_spaces_and_brackets(self):
        self.assertEqual(ST.name_key(" 东莞市 恒达（钢材）有限公司 "),
                         ST.name_key("东莞市恒达(钢材)有限公司"))

    def test_age_hours_none_when_unparsable(self):
        self.assertIsNone(ST.age_hours({"fetched_at": ""}))
        self.assertIsNone(ST.age_hours({"fetched_at": "昨天"}))
        self.assertGreaterEqual(ST.age_hours({"fetched_at": "2020-01-01 00:00:00"}), 0)


class _Stub:
    """可编程提供方（不联网）。"""

    def __init__(self, name, res):
        self.name = name
        self._res = res
        self.calls = 0

    def query(self, name, cfg, deadline):
        self.calls += 1
        if callable(self._res):
            return self._res(name)
        return self._res


def _ok_res(name="东莞市恒达钢材有限公司"):
    return PR.ProviderResult("stub", True, raw={
        "name": name, "tax_id": "91441900MA4W8XYZ12",
        "legal_representative": "张恒", "registered_capital": "5,000万元人民币",
        "established_date": "2016-03-08", "registration_status": "存续",
        "registered_address": "东莞市长安镇xx路1号", "company_type": "有限责任公司",
        "business_scope": "钢材、建材的销售",
    }, source_detail="单测提供方")


class ServiceTests(unittest.TestCase):
    def test_success_then_cache_hit_without_calling_provider(self):
        eng = _eng()
        stub = _Stub("stub", _ok_res())
        svc = SVC.BusinessInfoService(engine=eng, cfg=dict(CFG, providers=[]))
        with unittest.mock.patch.object(PR, "available", lambda cfg: [stub]):
            r1 = svc.query_company("东莞市恒达钢材有限公司")
        self.assertTrue(r1["ok"], r1)
        self.assertFalse(r1["cache_hit"])
        self.assertEqual(r1["profile"]["tax_id"], "91441900MA4W8XYZ12")
        self.assertEqual(r1["profile"]["registered_capital"], 5000.0)
        # 第二次：命中缓存，提供方**一次都不应被调用**
        calls_before = stub.calls
        r2 = svc.query_company("东莞市恒达钢材有限公司")
        self.assertTrue(r2["ok"])
        self.assertTrue(r2["cache_hit"])
        self.assertEqual(stub.calls, calls_before, "缓存命中后不得再触发取数（防反爬）")

    def test_failure_returns_friendly_message_and_does_not_raise(self):
        eng = _eng()
        bad = _Stub("bad", PR.ProviderResult("bad", False, reason="被风控拦截"))
        svc = SVC.BusinessInfoService(engine=eng, cfg=dict(CFG, providers=[]))
        with unittest.mock.patch.object(PR, "available", lambda cfg: [bad]):
            r = svc.query_company("从未查过的某某有限公司")
        self.assertFalse(r["ok"])
        self.assertIsNone(r["profile"])
        self.assertIn("请手动填写", r["message"], "失败必须给出可操作的提示")
        self.assertIn("被风控拦截", r["detail"], "失败原因必须如实透出")
        self.assertTrue(r["attempts"])

    def test_provider_exception_is_contained(self):
        eng = _eng()

        def boom(_name):
            raise RuntimeError("network down")

        svc = SVC.BusinessInfoService(engine=eng, cfg=dict(CFG, providers=[]))
        with unittest.mock.patch.object(PR, "available", lambda cfg: [_Stub("boom", boom)]):
            r = svc.query_company("某某有限公司")
        self.assertFalse(r["ok"])
        self.assertIn("RuntimeError", " ".join(a.get("reason") or "" for a in r["attempts"]))

    def test_risky_status_produces_warning(self):
        eng = _eng()
        res = _ok_res()
        res.raw["registration_status"] = "吊销，未注销"
        svc = SVC.BusinessInfoService(engine=eng, cfg=dict(CFG, providers=[]))
        with unittest.mock.patch.object(PR, "available", lambda cfg: [_Stub("stub", res)]):
            r = svc.query_company("东莞市恒达钢材有限公司")
        self.assertTrue(r["ok"])
        self.assertEqual(r["profile"]["registration_status"], "吊销")
        self.assertIn("吊销", r["risk_status_warning"] or "")

    def test_stale_cache_returned_with_flag_when_refresh_fails(self):
        eng = _eng()
        stub = _Stub("stub", _ok_res())
        svc = SVC.BusinessInfoService(engine=eng, cfg=dict(CFG, providers=[]))
        with unittest.mock.patch.object(PR, "available", lambda cfg: [stub]):
            svc.query_company("东莞市恒达钢材有限公司")
        # 把 fetched_at 改成 30 天前（超出 ttl=168h）
        with eng.begin() as conn:
            conn.execute(text("UPDATE sys_company_info SET fetched_at='2026-10-05 00:00:00'"))
        down = _Stub("down", PR.ProviderResult("down", False, reason="超时"))
        with unittest.mock.patch.object(PR, "available", lambda cfg: [down]):
            r = svc.query_company("东莞市恒达钢材有限公司")
        self.assertTrue(r["ok"], "宽限期内应回退展示旧数据")
        self.assertTrue(r["stale"], "必须标注为陈旧，否则等于把旧数据冒充新数据")

    def test_empty_name_is_rejected(self):
        r = SVC.BusinessInfoService(engine=_eng(), cfg=CFG).query_company(" ")
        self.assertFalse(r["ok"])
        self.assertEqual(r["code"], "invalid_name")



class ContractTests(unittest.TestCase):
    def test_no_hardcoded_secret_or_proxy(self):
        """验收第 4 条：代码里不得有硬编码的代理或 API Key。"""
        files = []
        for dirpath, _dn, fns in os.walk(os.path.join(ROOT, "engine", "business_info")):
            files += [os.path.join(dirpath, f) for f in fns if f.endswith(".py")]
        files.append(os.path.join(ROOT, "business_api.py"))
        files.append(os.path.join(ROOT, "engine", "business_scope_rule.py"))
        pat = re.compile(r"(?i)(api[_-]?key\s*=\s*[\"'][^\"']{6,}|"
                         r"token\s*=\s*[\"'][^\"']{6,}|"
                         r"proxies\s*=\s*\{\s*[\"']https?[\"']|"
                         r"https?://[0-9]{1,3}(\.[0-9]{1,3}){3}:[0-9]{2,5})")
        hits = []
        for f in files:
            src = open(f, encoding="utf-8").read()
            for m in pat.finditer(src):
                hits.append((os.path.basename(f), m.group(0)[:40]))
        self.assertEqual(hits, [], "发现疑似硬编码 Key/代理：%s" % hits)

    def test_config_is_the_only_place_with_urls_and_thresholds(self):
        """URL / UA / 阈值只许出现在配置里（代码改行为=改配置）。"""
        src = open(os.path.join(ROOT, "engine", "business_info", "providers.py"),
                   encoding="utf-8").read()
        # 只扫**字符串字面量**（docstring 里写域名属说明，不是取数来源）
        self.assertNotIn('"https://', src, "URL 字面量必须来自 config/business_info.json")
        self.assertNotIn("'https://", src, "URL 字面量必须来自 config/business_info.json")
        self.assertIn('gcfg.get("search_url")', src, "URL 必须从配置读")
        svc = open(os.path.join(ROOT, "engine", "business_info", "service.py"),
                   encoding="utf-8").read()
        for literal in ("168", "0.18", "0.5", "9.0"):
            self.assertNotIn("= %s" % literal, svc, "阈值不得写死在服务层")

    def test_api_requires_project_write_permission(self):
        src = open(os.path.join(ROOT, "business_api.py"), encoding="utf-8").read()
        self.assertIn('/api/v1/business', src)
        # ★ 必须定位到 **query 函数体**：`cached` 里也有一行同样的门禁，
        #   只扫全文会让"query 的门禁被删掉"这种退化**照样通过**（反向验证抓出来的）。
        i = src.index("def query_business_info")
        j = src.index("def cached_business_info")
        seg = src[i:j]
        self.assertIn('_require_perm(session, "project.write")', seg,
                      "query 接口必须校验「创建项目的权限」")

    def test_frontend_button_and_perm_registration(self):
        import json
        html = open(os.path.join(ROOT, "static", "projects.html"), encoding="utf-8").read()
        # ★ 必须定位到**该元素自己的标签**：projects.html 里有多个元素都带
        #   `data-perm="project.write"`，全文断言会让"本元素门控被删"照样通过
        #   （反向验证抓出来的假绿）。
        import re as _re
        # ★★ 2026-10-19（用户原话：「我要的是编辑项目页面下所有的信息都是自动获取
        #   自动填列的，然后显示在列表中，而不是甚至一个自动按钮！！！」）：
        #   演变三步：① 最初是可点击按钮【自动查填】→ ② 改为 `role="status"` 状态徽标
        #   → ③ **本轮整个删除**。用户说得明确：任何像按钮的东西都会让人以为还得点它。
        #   故本判据反转为：**该 id 必须不存在**（连徽标都不留）。
        self.assertIsNone(
            _re.search(r'<[a-z]+[^>]*id="btn-fetch-bizinfo"[^>]*>', html),
            "`#btn-fetch-bizinfo` 必须彻底删除（用户 2026-10-19：不要任何自动按钮/徽标）")
        self.assertNotIn("autofill", html.lower().replace("form-autofill", ""),
                         "表单里不得再出现额外的「自动」触发控件（提示区除外）")
        js = open(os.path.join(ROOT, "static", "js", "projects.js"), encoding="utf-8").read()
        self.assertIn("/api/v1/business/query", js)
        self.assertIn("risk_status_warning", js, "注销/吊销警告必须由后端判据驱动")
        # ★ 自动触发的证据（不是"改了就算"）：必须有输入/失焦绑定 + 防抖调度
        self.assertIn("scheduleBizAuto", js, "缺自动触发调度函数（仍是手动？）")
        self.assertIn('nameInput.addEventListener("input"', js,
                      "企业全称输入框必须绑定 input 事件（输入停顿自动查）")
        self.assertIn('nameInput.addEventListener("blur"', js,
                      "企业全称输入框必须绑定 blur 事件（失焦兜底查）")
        # ★ 绝不得覆盖用户已填内容（自动触发下的头号风险）
        self.assertIn("kept", js, "自动填务必区分「已填报」与「因已填写保持不变」")
        # ★ 权限门控不再靠"元素被隐藏"，而是直接问服务端下发的 permissions
        self.assertIn("window.RBAC", js,
                      "自动查填的权限判断必须问 RBAC（服务端 permissions 唯一权威）")
        self.assertIn("'project.write'", js, "自动查填必须校验 project.write")
        # ★ 行业/地区也必须自动填（用户要求"所有信息都自动"），且来源由后端派生
        self.assertIn("d.derived", js, "未使用后端派生的行业/地区（前端不得自建第二套推断）")
        self.assertIn("profile-suggestions", js,
                      "编辑页必须调用自动补全接口（行业/地区/期间/税种/工商 7 项）")
        # ★ 前端权限表不得残留已删元素（残留会让 `test_mapped_entries_carry_attributes` 报红）
        perms = json.load(open(os.path.join(ROOT, "config", "frontend_perms.json"),
                               encoding="utf-8"))
        ids = {x.get("id") for x in (perms["pages"].get("projects.html") or [])}
        self.assertNotIn("btn-fetch-bizinfo", ids,
                         "元素已删除，权限表条目必须同步删除（否则闸门报「元素不存在」）")

    def test_table_created_lazily_and_idempotent(self):
        eng = _eng()
        ST.ensure_schema(eng)
        ST.ensure_schema(eng)          # 二次调用不得报错
        self.assertTrue(ST.has_table(eng))


if __name__ == "__main__":
    unittest.main()
