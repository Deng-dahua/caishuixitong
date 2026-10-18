# -*- coding: utf-8 -*-
"""规则「超经营范围开票预警」（RL-INV-005，2026-10-18 新增）验收。

判据取向
--------
· 相似度只断言**判断结果**（匹配/不匹配/不确定），不断言内部实现；
· 必守的"不误报"：正常业务（热轧钢板 vs 钢材、水泥 vs 建筑材料）**不得**进预警；
· 必守的"不静默"：拿不到经营范围或销项品名 ⇒ **不产发现**且回执写明原因；
· 必守的"能落地"：红线已登记、条款可解析（`provisions_of` 非空）、
  归属已声明、反证条不可缺 —— 任一缺失都会让发现被封印/降级而无人察觉。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sqlalchemy import create_engine, text                        # noqa: E402

from engine import business_scope_rule as R                       # noqa: E402
from engine.risk_levels import LEGAL_LEVELS                       # noqa: E402

SCOPE = ("钢材、建筑材料、五金产品的销售；金属材料加工"
         "（依法须经批准的项目，经相关部门批准后方可开展经营活动）")


def _eng(scope=SCOPE):
    d = tempfile.mkdtemp(prefix="scope_")
    eng = create_engine("sqlite:///" + os.path.join(d, "t.db").replace("\\", "/"))
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE companies (id INTEGER PRIMARY KEY, business_scope TEXT)"))
        conn.execute(text("CREATE TABLE projects (id INTEGER PRIMARY KEY, company_id INTEGER, "
                          "business_scope TEXT)"))
        conn.execute(text("INSERT INTO companies (id, business_scope) VALUES (1, :s)"),
                     {"s": scope})
        conn.execute(text("INSERT INTO companies (id, business_scope) VALUES (2, '')"))
        conn.execute(text("INSERT INTO projects (id, company_id, business_scope) "
                          "VALUES (10, 2, :s)"), {"s": scope})
    return eng


def _inv(goods, direction="销项"):
    return {"direction": direction, "goods": goods, "invoice_no": "X1"}


class SegmentTests(unittest.TestCase):
    def test_boilerplate_and_parentheses_removed(self):
        segs = R.segments(SCOPE)
        self.assertIn("钢材", segs)
        self.assertIn("建筑材料", segs)
        self.assertIn("金属材料", segs, "括号内容不得把主类目一起带走")
        for s in segs:
            self.assertNotIn("依法须经批准", s)
            self.assertNotIn("批准", s)

    def test_no_segment_from_empty_scope(self):
        self.assertEqual(R.segments(""), [])


class SimilarityTests(unittest.TestCase):
    def _cls(self, goods, scope=SCOPE):
        return R.classify([goods], scope)

    def test_same_category_matched(self):
        for g in ("钢材", "螺纹钢", "热轧钢板", "钢材制品"):
            c = self._cls(g)
            self.assertTrue(c["matched"], "%s 应判匹配：%s" % (g, c))
        for g in ("水泥", "瓷砖", "五金件"):
            self.assertTrue(self._cls(g)["matched"], g)

    def test_unrelated_goods_flagged(self):
        for g in ("软件开发服务", "咨询服务费", "汽车配件", "塑料外壳"):
            c = self._cls(g)
            self.assertTrue(c["unmatched"], "%s 应判不匹配（实测 %s）" % (g, c))

    def test_ambiguous_not_flagged(self):
        """边界情形：不确定的**不报警**（宁缺勿错）。"""
        c = self._cls("建筑工程施工")
        self.assertFalse(c["unmatched"], "边界情形进了预警 ⇒ 误报%s" % c)
        self.assertTrue(c["uncertain"] or c["matched"])

    def test_empty_scope_makes_everything_uncertain(self):
        c = self._cls("钢材", scope="")
        self.assertEqual(c["matched"], [])
        self.assertEqual(c["unmatched"], [], "经营范围为空时不得判不匹配")
        self.assertTrue(c["uncertain"])

    def test_score_bounds(self):
        cfg = R._cfg()
        for g in ("钢材", "软件开发", "热轧钢板"):
            c = R.classify([g], SCOPE)
            it = (c["matched"] + c["unmatched"] + c["uncertain"])[0]
            self.assertGreaterEqual(it["score"], 0.0)
            self.assertLessEqual(it["score"], 1.0)


class SalesGoodsTests(unittest.TestCase):
    def test_only_sales_direction(self):
        goods, n = R.sales_goods([_inv("钢材"), _inv("办公用品", "进项"),
                                  {"goods": "水泥"}])          # 无方向 ⇒ 不算销项
        self.assertEqual(goods, ["钢材"])
        self.assertEqual(n, 1)

    def test_multi_goods_split_and_deduped(self):
        goods, _ = R.sales_goods([_inv("钢材；水泥"), _inv("钢材")])
        self.assertEqual(goods, ["钢材", "水泥"])


class CollectTests(unittest.TestCase):
    def test_finding_shape_and_level(self):
        eng = _eng()
        f, rc = R.collect_findings(1, [_inv("软件开发服务"), _inv("钢材")], engine=eng)
        self.assertEqual(len(f), 1, rc)
        it = f[0]
        self.assertIn(it["level"], LEGAL_LEVELS, "等级必须在权威词表内，否则被封印静默丢弃")
        self.assertTrue(it["_scenario_governed"])
        self.assertTrue(it["_level_locked"])
        self.assertEqual(it["redline_id"], "RL-INV-005")
        self.assertIn("软件开发服务", it["detail"])
        self.assertIn("发票管理办法》第二十一条", it["law_ref"])
        self.assertEqual(rc["matched"], 1)
        self.assertEqual(rc["unmatched"], 1)
        self.assertTrue(rc["participated"])

    def test_no_scope_no_finding(self):
        eng = _eng()
        f, rc = R.collect_findings(999, [_inv("软件开发服务")], engine=eng)
        self.assertEqual(f, [])
        self.assertFalse(rc["participated"])
        self.assertIn("未取得经营范围", rc["note"])
        self.assertIn("未参与", rc["note"])

    def test_scope_falls_back_to_project(self):
        eng = _eng()
        scope, origin = R.scope_of(2, engine=eng)
        self.assertEqual(scope, SCOPE)
        self.assertIn("projects", origin)

    def test_no_sales_invoice_no_finding(self):
        eng = _eng()
        f, rc = R.collect_findings(1, [_inv("软件开发服务", "进项")], engine=eng)
        self.assertEqual(f, [])
        self.assertIn("未取得销项发票品名", rc["note"])

    def test_all_matched_no_finding(self):
        eng = _eng()
        f, rc = R.collect_findings(1, [_inv("钢材"), _inv("水泥")], engine=eng)
        self.assertEqual(f, [])
        self.assertTrue(rc["participated"])
        self.assertIn("未发现", rc["note"])

    def test_never_raises_on_bad_engine(self):
        class Boom:
            def connect(self):
                raise RuntimeError("db down")
        f, rc = R.collect_findings(1, [_inv("x")], engine=Boom())
        self.assertEqual(f, [])
        self.assertIn("未参与", rc["note"])


class RegistryTests(unittest.TestCase):
    def test_redline_registered_with_basis(self):
        from engine.tax_redlines import REDLINES
        hit = [r for r in REDLINES if r.get("id") == "RL-INV-005"]
        self.assertEqual(len(hit), 1, "红线未登记")
        r = hit[0]
        self.assertTrue(r.get("legal_basis"))
        self.assertIn("发票管理办法", " ".join(r["legal_basis"]))
        # 反证条必须存在（否则规则会变成"超范围即违法"的错误口径）
        self.assertTrue(any("不认定为本项" in c for c in (r.get("constituents") or [])),
                        "红线缺反证条 ⇒ 会把合法经营误判为违法")
        self.assertTrue(r.get("required_materials"))
        self.assertTrue(r.get("evidence_chain"))

    def test_provisions_resolvable(self):
        from engine import legal_mapping as LM
        lp = LM.provisions_of("RL-INV-005")
        self.assertTrue(lp, "条款映射缺失 ⇒ legal_basis_gate 会把本条降级为『无依据线索』")
        self.assertTrue(any("第二十一条" in str(x.get("article")) for x in lp))

    def test_spec_registered(self):
        from engine.special_redline_detectors import SPECS
        hits = [s for s in SPECS if s.get("redline_id") == "RL-INV-005"]
        self.assertEqual(len(hits), 1, "专项规格未登记")
        self.assertTrue(hits[0].get("signals"))

    def test_attribution_declared(self):
        p = os.path.join(ROOT, "config", "redline_detector_attribution.json")
        d = json.load(open(p, encoding="utf-8"))
        hits = [x for x in d["declarations"] if x.get("redline_id") == "RL-INV-005"]
        self.assertEqual(len(hits), 1, "检测器归属未声明 ⇒ 覆盖率会把它记成『仅兜底』")
        self.assertEqual(hits[0]["detector_file"], "engine/business_scope_rule.py")
        self.assertEqual(hits[0]["detector_fn"], "collect_findings")

    def test_config_level_is_authoritative(self):
        cfg = R._cfg()
        self.assertIn(str(cfg.get("level")), LEGAL_LEVELS)
        self.assertEqual(cfg.get("redline_id"), "RL-INV-005")




class RealDataRegressionTests(unittest.TestCase):
    """真实账套回归（company_id=1，2026-10-18 实测）：

    ★ 这两条是**真跑出来的缺陷**，不是假想：
      ① 发票品名是 `*税收分类*具体名称`，整串比对会让「设计服务费」凭「服务」
         与「服装零售」沾上；
      ② 字符重合率分母用 `min()` ⇒ 单个汉字重合就 0.33 ⇒ 落进「不确定」档不报警。
    两者叠加的后果：**9 项真实超范围品名，零报警**（规则等于没上线）。
    """

    #: 真实经营范围（该账套库里的原值，含被截断的「服装...」）
    REAL_SCOPE = ("五金产品零售;日用百货销售;针纺织品销售;化妆品零售;包装材料及制品销售;"
                  "橡胶制品销售;日用杂品销售;服装...")
    REAL_GOODS = ["*设计服务*设计服务费", "*广告服务*广告发布费",
                  "*信息技术服务*信息服务费", "*现代服务*其他现代服务",
                  "*现代服务*策划服务费"]

    def test_goods_core_strips_tax_category(self):
        self.assertEqual(R.goods_core("*设计服务*设计服务费"), "设计服务费")
        self.assertEqual(R.goods_core("*钢材*热轧钢板"), "热轧钢板")
        self.assertEqual(R.goods_core("钢材"), "钢材")

    def test_single_char_overlap_is_not_evidence(self):
        # 「设计服务费」与「服装」只共用「服」⇒ 必须判**不匹配**，不能落「不确定」
        c = R.classify(["设计服务费"], self.REAL_SCOPE)
        self.assertTrue(c["unmatched"], "单字重合被当成证据 ⇒ %s" % c)
        self.assertEqual(c["unmatched"][0]["score"], 0.0)

    def test_real_goods_all_flagged(self):
        c = R.classify(self.REAL_GOODS, self.REAL_SCOPE)
        self.assertEqual(len(c["unmatched"]), 5,
                         "真实超范围品名漏报：%s" % c)
        self.assertEqual(c["matched"], [])

    def test_in_scope_goods_still_not_flagged(self):
        """同一账套的**合规**品名不得被误报（否则规则会被用户关掉）。"""
        c = R.classify(["*五金*五金件", "*日用百货*毛巾", "*化妆品*口红"], self.REAL_SCOPE)
        self.assertFalse(c["unmatched"], "在范围内的品名被误报：%s" % c)



class WiringTests(unittest.TestCase):
    """接线自检：规则必须真的接进 `pipeline._run_analyze`，且在**封印之前**。

    ★ 只断言"模块里有这行"不够 —— 必须证明相对位置：
      放在 `seal_governed_findings` 之后，发现会被封印静默丢掉（六条静默机制之一）。
    """

    def setUp(self):
        self.src = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()

    def test_pipeline_calls_the_rule(self):
        self.assertIn("business_scope_rule", self.src, "一键分析未接入超经营范围规则")
        self.assertIn("_scope_collect(company_id, invoices)", self.src,
                      "接入必须同时给 company_id 与 invoices（否则规则无法取数）")

    def test_hook_runs_before_sealing(self):
        # ★ 不能用 `str.index`（"seal_governed_findings" 在注释里先出现 ⇒ 假红灯）。
        #   按**行号**比：接入调用点 必须早于 真正的封印调用点。
        lines = self.src.splitlines()
        hook = next(i for i, ln in enumerate(lines)
                    if "_scope_collect(company_id, invoices)" in ln)
        seal = next(i for i, ln in enumerate(lines)
                    if ln.strip().startswith("all_findings = seal_governed_findings"))
        self.assertLess(hook, seal, "接入点在封印之后 ⇒ 新增发现会被静默丢弃")

    def test_not_silent_on_failure(self):
        seg = self.src[self.src.index("business_scope_rule"):]
        seg = seg[:seg.index("if _objective_injected")]
        self.assertIn("pipeline_log", seg, "接入失败必须在 pipeline_log 留痕（不得静默）")
        self.assertIn("未产预警", seg, "无预警时要写原因（没有数据 ≠ 没有风险）")

    def test_api_registered_in_main(self):
        txt = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
        self.assertIn("from business_api import router as business_router", txt)
        self.assertIn("app.include_router(business_router)", txt)



if __name__ == "__main__":
    unittest.main()
