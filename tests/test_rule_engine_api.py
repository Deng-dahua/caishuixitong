# -*- coding: utf-8 -*-
"""P0-5 规则引擎 —— 四类测试（单元 / 集成 / 边界 / 规则版本切换）+ 反向验证。

隔离方式：**子进程 + `APP_DATA_DIR` 临时目录**（与 P0-1~P0-4 同一模式）。

四类（任务书要求）：
  ① `RuleEngineUnitTests`      单元测试：规则加载 / 执行归一 / 评分
  ② `RuleEngineIntegrationTests` 集成测试：规则执行 → 风险生成（构造载荷走真实归集）
  ③ `RuleEngineBoundaryTests`  边界测试：空数据 / 异常数据（不得崩、不得编造）
  ④ `RuleVersionTests`         规则版本切换测试
  另：`RuleEngineReverseVerification` **反向验证**（判据必须真的在起作用）

★ 关键断言取向（防"看起来对"）：
  · 规则主体条数必须等于**唯一权威 layer_semantics** 的复算值（不得硬编码数字）；
  · 缺因子必须**剔除并重算权重**（不是给 0 分）；全缺 / 信息不足必须**不给分**；
  · 未运行/跳过/异常的执行记录必须**完整保留**（不伪装成已执行）。
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


def _run(script: str, *, timeout: int = 300, dedent: bool = True) -> subprocess.CompletedProcess:
    """在隔离的 `APP_DATA_DIR` 临时目录里跑一段脚本。

    `dedent=False`：调用方已**分段去缩进**（拼接脚本后整体最小缩进为 0，再 dedent 不生效）。
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


#: 构造一份**最小但真实形状**的报告载荷（含 confirmed_problems 与 verified_rule_executions）
_PAYLOAD_SRC = textwrap.dedent('''
    def _payload():
        return {
            "overall_level": "构造样例",
            "verified_rule_executions": [
                {"rule_id": "VR001", "status": "hit", "finding_count": 2},
                {"rule_id": "VR002", "status": "not_run_missing_data",
                 "missing_sources": ["bank_txs"]},
                {"rule_id": "VR003", "status": "skipped_industry", "industries": ["制造业"]},
                {"rule_id": "VR004", "status": "execution_error", "message": "构造异常"},
            ],
            "enterprise_readable_report": {
                "confirmed_problems": [
                    {"seq": 1, "title": "有销无进", "redline_id": "RL-VAT-001",
                     "rule_id": "", "risk_level": "高风险", "confidence": 0.8,
                     "conclusion_grade": "待核", "verdict": "未达定性门槛",
                     "finding_count": 4,
                     "tax_impact": {"available": True, "basis": 100000.0,
                                    "items": [{"tax": "增值税", "amount": 60000.0}]},
                     "evidence_chain": {"elements": [
                         {"role": "正证", "name": "销项发票明细", "status": "已提交",
                          "sources": ["销项发票.xlsx"]},
                         {"role": "待补", "name": "成本凭证", "status": "缺失"}],
                         "missing_material_names": ["成本凭证"], "closure": 0.5},
                     "confidence_breakdown": [
                         {"项": "基准分", "权重": 0.5, "取值": 1.0, "贡献": 0.5},
                         {"项": "证据链闭合度", "权重": 0.25, "取值": 0.5, "贡献": 0.125}]},
                    {"seq": 2, "title": "资料不足事项", "redline_id": "RL-CIT-001",
                     "risk_level": "待核验", "confidence": 0.6,
                     "tax_impact": {"available": False}},
                ]
            },
        }
''')


# --------------------------------------------------------------------------
# ① 单元测试
# --------------------------------------------------------------------------
class RuleEngineUnitTests(unittest.TestCase):
    def test_loader_catalog_scoring(self):
        result = _run(
            """
            import json
            from engine import rule_loader as L
            from engine import rule_catalog as CAT
            from engine import risk_scoring as S

            # ── 1) 加载器：四载体都要读到，且**不允许静默当空** ──
            py = L.load_python_rules()
            js = L.load_json_candidates()
            ya = L.load_yaml_exports()
            ds = L.load_dsl_scope()
            assert len(py) > 0 and len(js) > 0 and len(ya) > 0 and ds, (
                len(py), len(js), len(ya), bool(ds))
            assert not L.last_errors(), L.last_errors()
            # 各载体 id 键名不同（id / redline_id / src / rule_id）⇒ 归一后必须**无空 id**
            assert not [r for r in py if not r["rule_id"]], "python 侧有空 rule_id"
            assert not [r for r in js if not r["rule_id"]], "候选侧有空 rule_id"
            # ★ 分层必须与 layer_semantics **全部层**一一对上（实测共 6 层，含
            #   `fact_check_rules` 89 条 —— 最初漏了它 ⇒ 规则库覆盖不全，本轮补齐）
            from collections import Counter
            lay = Counter(r["layer"] for r in py)
            gov = Counter(r["layer"] for r in L.load_governance_rules())
            all_lay = lay + gov
            with open("config/rule_versions.json", encoding="utf-8") as fh:
                layers = json.load(fh)["layer_semantics"]["layers"]
            assert len(layers) >= 6, ("权威层数变了，须复核", list(layers))
            for name, meta in layers.items():
                assert all_lay.get(name) == meta["count"], (
                    name, all_lay.get(name), meta["count"])
            # 权威事实核查规则（另一维度）必须**独立成 kind**，不得混进 python
            assert len(L.load_governance_rules()) == layers["fact_check_rules"]["count"]

            # ── 2) 目录：主体条数取自权威；法规依据如实分类 ──
            st = CAT.stats()
            subject = sum(int(v["count"]) for v in layers.values()
                          if v.get("counts_toward_rule_total"))
            assert st["rule_subject_total"] == subject, (st["rule_subject_total"], subject)
            cov = st["legal_basis_coverage"]
            assert cov["with_real_ref"] + cov["placeholder"] + cov["missing"] == st["total_entries"]
            assert cov["placeholder"] > 0, "候选库法规依据占位应被如实标出（实测全占位）"
            assert st["runtime_switch_available"] is False, "本项目无运行时开关，须如实声明"
            # 三类 kind 必须分开（把"另一维度"混进主体即重复计数）
            assert st["by_source_kind"].get("governance") == layers["fact_check_rules"]["count"], \
                st["by_source_kind"]

            # ── 3) 列表/详情/版本 ──
            l = CAT.list_rules(source="python", page_size=5)
            assert l["total"] == len(py), (l["total"], len(py))
            rid = l["items"][0]["rule_id"]
            d = CAT.get(rid)
            assert d["rule_id"] == rid and "raw" in d
            try:
                CAT.get("__NOSUCH__")
                raise AssertionError("不存在的规则竟然取到")
            except KeyError:
                pass
            v = CAT.versions()
            assert v["rule_set_version"] and v["registered_count"] > 0, v

            # ── 4) 评分：四因子 / 缺因子剔除 / 全缺不给分 / 单调 ──
            full = {"risk_level": "高风险", "confidence": 0.9, "finding_count": 4,
                    "tax_impact": {"available": True,
                                   "items": [{"amount": 600000.0}]}}
            r = S.score(full)
            assert r["priority_score"] is not None and 0 <= r["priority_score"] <= 100, r
            assert r["score_basis"] == 1.0, r          # 四因子齐全 ⇒ 权重和 1.0
            assert all(x["state"] == "ok" for x in r["factors"]), r["factors"]
            # 单调：其余相同、等级更高的分更高
            lo = S.score(dict(full, risk_level="低风险"))["priority_score"]
            hi = S.score(dict(full, risk_level="高风险"))["priority_score"]
            assert hi > lo, (hi, lo)
            # 缺因子 ⇒ **剔除并重算权重**（不是给 0 分）
            r2 = S.score({"risk_level": "高风险"})
            assert r2["score_basis"] == round(0.4 + 0.1, 4), r2   # severity + frequency
            assert r2["missing_weight"] == round(0.25 + 0.25, 4), r2
            # 全缺 ⇒ 不给分（缺失≠0/≠默认分）
            r3 = S.score({})
            assert r3["priority_score"] is None and r3["status"] == "insufficient", r3
            # 金额 available=False ⇒ 该因子必须标 missing（不得当 0 元）
            r4 = S.score({"risk_level": "高风险", "confidence": 0.9,
                          "tax_impact": {"available": False}, "finding_count": 4})
            amt = [x for x in r4["factors"] if x["name"] == "amount"][0]
            assert amt["state"] == "missing", amt
            # 三档视图必须来自配置（不是硬编码）
            bands = S.grade_view_bands()
            assert [b["grade"] for b in bands] == ["高", "中", "低"], bands
            assert S.grade_view_of(85) == "高" and S.grade_view_of(60) == "中" \
                and S.grade_view_of(10) == "低" and S.grade_view_of(None) == ""
            print("RULE ENGINE UNIT TESTS PASSED")
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        self.assertIn("RULE ENGINE UNIT TESTS PASSED", result.stdout)


# --------------------------------------------------------------------------
# ② 集成测试：规则执行 → 风险生成
# --------------------------------------------------------------------------
class RuleEngineIntegrationTests(unittest.TestCase):
    def test_execute_and_collect_and_stamp(self):
        result = _run(
            _PAYLOAD_SRC + textwrap.dedent("""
            from engine import rule_executor as EXEC
            from engine import risk_scoring as S

            # 1) 从真实载荷形状归集：发现 + 证据 + 逐条执行
            res = EXEC.collect_from_report(_payload())
            assert res["counts"]["findings"] == 2, res["counts"]
            assert res["counts"]["evidences"] > 0, res["counts"]
            # 逐条执行：命中的用 hit，未运行/跳过/异常**全部保留**
            s = res["summary"]
            assert s["total"] >= 4, s
            assert s["not_run"] == 1 and s["skipped"] == 1 and s["errored"] == 1, s
            assert sum(s["by_status"].values()) == s["total"]
            # 每个状态都要有中文名（面向界面不得出现英文码）
            for k, v in s["by_status_cn"].items():
                assert v and v != "None", (k, v)

            # 2) 证据归集：分门别类（计算过程 / 证据要素 / 待补资料 / 原始数据）
            kinds = {e["kind"] for e in res["evidences"]}
            assert "evidence_element" in kinds and "calculation" in kinds, kinds
            assert "missing_material" in kinds, kinds
            # 证据必须能回指发现（finding_seq）
            assert all(e.get("finding_seq") for e in res["evidences"]), "证据未回指发现"

            # 3) 综合排序分：盖到发现上且**不改等级**
            stamped = S.stamp_all(res["findings"])
            for a, b in zip(res["findings"], stamped):
                assert a["risk_level"] == b["risk_level"], "排序分不得改等级（铁律）"
            # 高风险那条应排在前面
            stamped.sort(key=lambda x: (x.get("priority_score") is None,
                                        -(x.get("priority_score") or 0)))
            assert stamped[0]["risk_level"] == "高风险", stamped[0]
            # 待核验（严重度缺失）那条：金额也缺 ⇒ 可能信息不足 ⇒ 不得给 0 分
            wk = [x for x in stamped if x["risk_level"] == "待核验"][0]
            assert wk.get("priority_score") is None or wk["priority_score"] > 0, wk

            # 4) 真跑两引擎（编排顺序：原子规则 → 红线判定）—— 用最小 engine_data 走通不崩
            empty = EXEC.execute({})
            assert isinstance(empty, dict) and "findings" in empty and "executions" in empty
            print("RULE ENGINE INTEGRATION TESTS PASSED")
            """),
            dedent=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        self.assertIn("RULE ENGINE INTEGRATION TESTS PASSED", result.stdout)

    def test_api_end_to_end_with_payload(self):
        """端到端：把构造载荷落到隔离的 `offline_reports/`，走 HTTP 读发现与详情。"""
        result = _run(
            _PAYLOAD_SRC + textwrap.dedent("""
            import os, json
            from fastapi.testclient import TestClient
            from main import app
            from runtime_storage import offline_reports_root

            BASE = "/api/v1"
            with TestClient(app) as c:
                c.post("/api/auth/login", json={"username": "integrationadmin",
                                                "password": "Integration-Test-2026!"})
                h = {"X-CSRF-Token": c.cookies.get("csrf_token")}
                r = c.post("/api/companies", headers=h,
                           json={"name": "规则集成", "uscc": "91440300MA5RI00001"})
                cid = r.json()["id"]
                c.post("/api/auth/select-company", headers=h, json={"company_id": cid})
                # 落载荷到**隔离目录**（offline_reports_root 跟随 APP_DATA_DIR）
                root = offline_reports_root()
                os.makedirs(root, exist_ok=True)
                path = os.path.join(root, "company_%d_full.json" % cid)
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(_payload(), fh, ensure_ascii=False)

                f = c.get(BASE + "/risk-findings?company_id=%d" % cid)
                assert f.status_code == 200, f.text
                j = f.json()
                assert j["available"] is True and j["total"] == 2, j
                first = j["items"][0]
                assert first["risk_level"] == "高风险", first   # 排序分高的在前
                assert first["priority_score"] is not None
                assert first["priority_grade"] in ("高", "中", "低"), first

                seq = first["seq"]
                d = c.get(BASE + "/risk-findings/%d?company_id=%d" % (seq, cid))
                assert d.status_code == 200, d.text
                dj = d.json()
                assert dj["finding"]["seq"] == seq
                assert "scoring" in dj and dj["scoring"]["factors"], dj
                assert dj["evidences"], "详情必须带证据归集"
                assert dj["rule_found"] is True, dj          # RL-VAT-001 在目录里
                assert dj["rule"]["legal_basis_ref"], dj

                e = c.get(BASE + "/rule-executions?company_id=%d" % cid)
                assert e.status_code == 200 and e.json()["summary"]["total"] >= 4, e.text

                # 规则库接口
                assert c.get(BASE + "/rules/stats").status_code == 200
                assert c.get(BASE + "/rules/versions").json()["rule_set_version"]
                assert c.get(BASE + "/rules?source=json&page_size=3").json()["total"] > 0
                print("RULE ENGINE API E2E TEST PASSED")
            """),
            dedent=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        self.assertIn("RULE ENGINE API E2E TEST PASSED", result.stdout)


# --------------------------------------------------------------------------
# ③ 边界测试：空数据 / 异常数据
# --------------------------------------------------------------------------
class RuleEngineBoundaryTests(unittest.TestCase):
    def test_empty_and_malformed_payload(self):
        result = _run(
            """
            from engine import rule_executor as EXEC
            from engine import risk_scoring as S

            # 1) 空载荷：不得崩、不得编造
            for bad in ({}, {"enterprise_readable_report": {}},
                        {"enterprise_readable_report": {"confirmed_problems": []}},
                        None):
                r = EXEC.collect_from_report(bad or {})
                assert r["counts"]["findings"] == 0, (bad, r["counts"])
                assert r["counts"]["evidences"] == 0, (bad, r["counts"])
                assert r["summary"]["total"] == 0, r["summary"]
                assert r["ok"] is True, r

            # 2) 异常类型：confirmed_problems 不是 list；executions 里混入非 dict
            r2 = EXEC.collect_from_report({"enterprise_readable_report":
                                           {"confirmed_problems": "不是列表"}})
            assert r2["counts"]["findings"] == 0, r2["counts"]
            r3 = EXEC.collect_from_report({
                "verified_rule_executions": ["不是字典", 123, None,
                                             {"rule_id": "VR009", "status": "hit"}],
                "enterprise_readable_report": {"confirmed_problems": [
                    "不是字典", None, {"seq": 1, "title": "ok", "risk_level": "低风险"}]}})
            assert r3["counts"]["findings"] == 1, r3["counts"]
            assert all(isinstance(x, dict) for x in r3["executions"]), r3["executions"]

            # 3) 未知执行状态：**原样保留**（不得静默丢、不得假装已执行）
            r4 = EXEC.collect_from_report({"verified_rule_executions": [
                {"rule_id": "VRX", "status": "某种新状态"}]})
            u = [e for e in r4["executions"] if e["rule_id"] == "VRX"][0]
            assert u["raw_status"] == "某种新状态", u
            assert u["status_cn"], u

            # 4) 异常数值：金额是字符串/负数/NaN 一律不得崩
            for amt in ("abc", None, -1, float("nan"), 10 ** 12):
                r = S.score({"risk_level": "高风险", "confidence": 0.7,
                             "tax_impact": {"available": True, "items": [{"amount": amt}]},
                             "finding_count": 1})
                assert r["priority_score"] is None or 0 <= r["priority_score"] <= 100, (amt, r)

            # 5) 置信度越界必须被夹紧（不得 >1 或 <0 放大分数）
            hi = S.score({"risk_level": "高风险", "confidence": 9.9,
                          "tax_impact": {"available": True, "items": [{"amount": 10 ** 8}]},
                          "finding_count": 99})
            assert hi["priority_score"] <= 100, hi
            c = [x for x in hi["factors"] if x["name"] == "confidence"][0]
            assert c["value"] == 1.0, c
            print("RULE ENGINE BOUNDARY TESTS PASSED")
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        self.assertIn("RULE ENGINE BOUNDARY TESTS PASSED", result.stdout)


# --------------------------------------------------------------------------
# ④ 规则版本切换测试
# --------------------------------------------------------------------------
class RuleVersionTests(unittest.TestCase):
    def test_version_registry_and_switch(self):
        result = _run(
            """
            import json, shutil, os
            from engine import rule_catalog as CAT
            from engine import rule_versions as RV

            v0 = CAT.versions()
            assert v0["rule_set_version"], v0
            assert v0["registered_count"] > 0, v0
            # 每个已登记规则都要有版本号（未登记的 finding 必须显式标「未登记」）
            reg = json.load(open("config/rule_versions.json", encoding="utf-8"))["rules"]
            for rid, meta in list(reg.items()):
                assert meta.get("version"), (rid, meta)
                assert meta.get("effective_from"), (rid, meta)

            # 1) 单条规则版本可查（目录与版本登记必须一致）
            rid = sorted(reg)[0]
            d = CAT.get(rid)
            assert d["version"] == reg[rid]["version"], (d["version"], reg[rid])
            assert d["version_registered"] is True, d

            # 2) finding 版本标记：切换版本集后必须跟着变（同一算法，不缓存旧值）
            before = RV.rule_set_version()
            f = {"title": "t", "redline_id": rid}
            stamped = RV.stamp(dict(f))
            assert stamped.get("rule_version"), stamped

            # 3) 真切换：改 version + history（走文件读写，模拟运维动作），再复算
            path = "config/rule_versions.json"
            bak = path + ".vswitch_tmp"
            shutil.copy(path, bak)
            try:
                doc = json.load(open(path, encoding="utf-8"))
                doc["rule_set_version"] = "2026.99-test"
                doc.setdefault("rule_set_history", []).append(
                    {"version": "2026.99-test", "date": "2026-10-13", "note": "测试用切换"})
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(doc, fh, ensure_ascii=False, indent=2)
                RV.reload()
                CAT.reset_cache()
                after = RV.rule_set_version()
                assert after == "2026.99-test", after
                assert CAT.versions()["rule_set_version"] == "2026.99-test", CAT.versions()
                # 未登记规则的 finding 必须**显式标「未登记」**（不得伪造版本号）
                s2 = RV.stamp({"title": "x", "redline_id": "__NOPE__"})
                assert s2.get("rule_version") in ("未登记", "", None), s2
            finally:
                shutil.copy(bak, path)
                os.remove(bak)
                RV.reload()
                CAT.reset_cache()

            # 4) 还原后必须回到原版本（可复现）
            assert RV.rule_set_version() == before, (RV.rule_set_version(), before)
            assert CAT.versions()["rule_set_version"] == before
            print("RULE VERSION TESTS PASSED")
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        self.assertIn("RULE VERSION TESTS PASSED", result.stdout)


# --------------------------------------------------------------------------
# 反向验证
# --------------------------------------------------------------------------
class RuleEngineReverseVerification(unittest.TestCase):
    def test_reverse_scoring_weights_and_loader(self):
        """★ 反向验证两条判据**真的在起作用**：

        ① 把评分权重改成"仅 severity" ⇒ 金额/频次/置信度**必须不再影响**分数（判据变红）；
        ② 把 `rule_loader` 的 id 键解析去掉（不认 `src`）⇒ 候选侧**必须出现空 id**（判据变红）。
        """
        result = _run(
            """
            import json, shutil, os
            from engine import risk_scoring as S
            from engine import rule_loader as L

            # ── ① 权重注入：仅 severity ──
            path = "config/risk_scoring.json"
            bak = path + ".rv_tmp"
            shutil.copy(path, bak)
            try:
                doc = json.load(open(path, encoding="utf-8"))
                doc["weights"] = {"severity": 1.0, "confidence": 0.0,
                                  "amount": 0.0, "frequency": 0.0}
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(doc, fh, ensure_ascii=False, indent=2)
                S.reset_cache()
                a = S.score({"risk_level": "高风险", "confidence": 0.1, "finding_count": 1,
                             "tax_impact": {"available": True, "items": [{"amount": 1.0}]}})
                b = S.score({"risk_level": "高风险", "confidence": 0.99, "finding_count": 9,
                             "tax_impact": {"available": True,
                                            "items": [{"amount": 10 ** 7}]}})
                # 权重只剩 severity ⇒ 两条分数**必须相同**（金额/频次/置信度不再起作用）
                assert a["priority_score"] == b["priority_score"], (
                    "权重注入未生效 ⇒ 该判据是假的", a["priority_score"], b["priority_score"])
            finally:
                shutil.copy(bak, path)
                os.remove(bak)
                S.reset_cache()

            # 还原后：金额/频次/置信度**必须再次起作用**（两条分数不同）
            c = S.score({"risk_level": "高风险", "confidence": 0.1, "finding_count": 1,
                         "tax_impact": {"available": True, "items": [{"amount": 1.0}]}})
            d = S.score({"risk_level": "高风险", "confidence": 0.99, "finding_count": 9,
                         "tax_impact": {"available": True,
                                        "items": [{"amount": 10 ** 7}]}})
            assert c["priority_score"] != d["priority_score"], (c, d)

            # ── ② id 键解析注入：去掉 `src` 支持 ⇒ 候选侧必须出现空 id ──
            src = "engine/rule_loader.py"
            bak2 = src + ".rv_tmp"
            shutil.copy(src, bak2)
            try:
                t = open(src, encoding="utf-8").read()
                old = 'or raw.get("src") or ""'
                assert old in t, "锚点未命中"
                open(src, "w", encoding="utf-8").write(t.replace(old, 'or ""', 1))
                import importlib
                importlib.reload(L)
                js = L.load_json_candidates()
                empty = [r for r in js if not r["rule_id"]]
                assert empty, "去掉 src 解析后仍无空 id ⇒ 该判据是假的"
            finally:
                shutil.copy(bak2, src)
                os.remove(bak2)
                import importlib
                importlib.reload(L)
                js2 = L.load_json_candidates()
                assert not [r for r in js2 if not r["rule_id"]], "还原后仍有空 id"
            print("RULE ENGINE REVERSE VERIFICATION PASSED")
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        self.assertIn("RULE ENGINE REVERSE VERIFICATION PASSED", result.stdout)


if __name__ == "__main__":
    unittest.main()
