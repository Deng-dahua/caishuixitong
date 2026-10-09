# -*- coding: utf-8 -*-
"""业态剔除（本业态天然不适用的资料不得作为证据要求）—— **单一权威**契约测试。

## 为什么必须有这个测试文件（根因，非特例）
「把本业态天然不会有的资料从清单里剔掉」这一个概念，此前有 **4 份实现、4 种判法**：
  ① `evidence_chain` 引擎层：**字符级 `str.replace`** 删子串
       ⇒ "采购合同与入库验收单" → "采购合同**与**"（悬空连词残词）；
         "物流单据与承运记录" → "**与**承运记录" 或 ""，**取决于 set 迭代序**（非确定）；
       且它跑在 status/basis/direct_missing **之后** ⇒ 只有名字被改，
       依据与「取得直接证据」清单**仍是原始要求** ⇒ **服务型企业照样被要求补物流单据**。
  ② `enterprise_report._strip_not_required`（段级，判法正确）
  ③ `constituent_checkpoint._decl_na`：切段表**不含「与」** + **双向包含**
       ⇒ "采购合同与入库验收单" 不切段、整段命中"入库验收单"
       ⇒ **整条要件被误判「本业态不适用」**（里面"采购合同"明明适用）
  ④ `enterprise_report._trim_text_materials`（整句文本级）

现全部薄转发到 `engine/industry_resolver`：
  `MATERIAL_SEG_SEP`（唯一分隔符表）/ `classify_not_required_segments` /
  `exclude_not_required_material` / `exclude_not_required_in_text`。

新写函数必须删旧定义：`grep -c "^def exclude_not_required_material" == 1`。
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine.industry_resolver import (                    # noqa: E402
    MATERIAL_SEG_SEP, classify_not_required_segments, exclude_not_required_in_text,
    exclude_not_required_material, has_dangling_separator, not_required_materials)
from engine.evidence_chain import build_evidence_chain     # noqa: E402
from engine.tax_redlines import REDLINES                   # noqa: E402

SERVICE_IND = "广告传媒"          # 服务型：天然无实物货物流转
_RL_SEQ = REDLINES.values() if isinstance(REDLINES, dict) else REDLINES
_RLMAP = {r.get("id"): r for r in (_RL_SEQ or [])}


def _na():
    s, _ = not_required_materials(SERVICE_IND)
    return s


class TestSingleAuthority(unittest.TestCase):
    """唯一权威：段级剔除的结果、幂等、无残词、确定性。"""

    def setUp(self):
        self.na = _na()
        self.assertTrue(self.na, "业态「%s」的不适用资料清单为空 —— 权威表失效" % SERVICE_IND)

    def test_only_one_separator_table(self):
        """分隔符表只能有一处（grep 可证）。"""
        owner = os.path.join(ROOT, "engine", "industry_resolver.py")
        hits = []
        for fn in sorted(os.listdir(os.path.join(ROOT, "engine"))):
            if not fn.endswith(".py") or fn.startswith("_bk"):
                continue
            p = os.path.join(ROOT, "engine", fn)
            with open(p, encoding="utf-8", errors="replace") as f:
                txt = f.read()
            for m in re.finditer(r"re\.compile\(\s*r?[\"'][^\"']*[\"']\s*\)", txt):
                frag = m.group(0)
                if "与" in frag and ("及" in frag or "和" in frag):
                    hits.append((fn, frag))
        self.assertEqual([h for h in hits if h[0] != "industry_resolver.py"], [],
                         "除 industry_resolver.py 外又出现并列分隔符表：%r" % hits)
        self.assertTrue(any(h[0] == "industry_resolver.py" for h in hits),
                        "industry_resolver 里找不到并列分隔符表（权威缺失）")
        _ = MATERIAL_SEG_SEP

    def test_partial_removal_keeps_applicable_segment(self):
        """部分不适用 ⇒ 保留适用段，且**不得**留悬空连词。"""
        cases = {
            "采购合同与入库验收单": "采购合同",
            "物流单据与承运记录": "",
            "销售台账、出库单、发货记录": "销售台账、发货记录",
            "出库单与发货记录": "发货记录",
            "存货盘点表": "",
        }
        for src, want in cases.items():
            got = exclude_not_required_material(src, self.na)
            self.assertEqual(got, want, "「%s」应为「%s」，实得「%s」" % (src, want, got))
            self.assertFalse(has_dangling_separator(got, src),
                             "「%s」→「%s」出现残词/并列连词" % (src, got))
            self.assertEqual(exclude_not_required_material(got, self.na), got,
                             "剔除不幂等：「%s」" % src)

    def test_legit_names_with_conjunction_not_touched(self):
        """含「与/及/和」但**不含**不适用资料的专有名词：**原样返回**，不得切坏。"""
        for name in ("与境外方签署的合同或协议、董事会利润分配决议",
                     "合同台账与全部应税凭证",
                     "付款银行流水或第三方支付凭证",
                     "应付账款明细账及账龄分析"):
            if any(n in name for n in self.na):
                continue
            self.assertEqual(exclude_not_required_material(name, self.na), name,
                             "误改了合法名称：「%s」" % name)
            self.assertFalse(has_dangling_separator(name, name), "合法名称被误判为残词：%s" % name)

    def test_unknown_industry_does_not_strip(self):
        """业态未知/清单为空 ⇒ **不剔**（判不出就不剔，宁可多列不得无据少列）。"""
        for empty in (set(), None, [], ()):
            self.assertEqual(exclude_not_required_material("采购合同与入库验收单", empty),
                             "采购合同与入库验收单")
        self.assertEqual(not_required_materials("")[0], set())

    def test_deterministic_across_set_order(self):
        """★ 确定性：结果与集合迭代序无关（旧字符级实现会因 hash 顺序给出不同残词）。"""
        ordered = sorted(self.na)
        a = exclude_not_required_material("物流单据与承运记录", set(ordered))
        b = exclude_not_required_material("物流单据与承运记录", set(reversed(ordered)))
        c = exclude_not_required_material("物流单据与承运记录", list(ordered))
        self.assertEqual(a, b)
        self.assertEqual(a, c)

    def test_classify_reports_dropped_segments(self):
        """带明细入口：能说清"剔掉了哪几段"（供要件层写依据）。"""
        keep, drop, had = classify_not_required_segments("采购合同与入库验收单", self.na)
        self.assertTrue(had)
        self.assertEqual(keep, ["采购合同"])
        self.assertEqual(drop, ["入库验收单"])
        # ★ 单向包含：段包含不适用名才剔；**不得**反向（"合同" ⊂ "承运合同"）
        self.assertIn("采购合同", keep, "反向包含误删了「采购合同」")


class TestEngineWiring(unittest.TestCase):
    """引擎层：剔除必须发生在 status/basis/direct_missing **之前**，四条链路同源。"""

    def setUp(self):
        self.na = _na()

    def test_names_basis_direct_missing_and_remedy_are_consistent(self):
        rl = {
            "id": "RL-T-1",
            "remedy": "提供付款对应的采购合同、入库验收单、物流单据，并对资金回流路径作出书面说明。",
            "evidence_chain": [
                {"role": "直接证据", "name": "采购合同与入库验收单", "purpose": "证明交易真实"},
                {"role": "间接证据", "name": "物流单据与承运记录", "purpose": "证明货物流真实"},
            ],
        }
        ev = build_evidence_chain({"type": "t"}, rl, [], {"industry": SERVICE_IND})
        names = [e["name"] for e in ev["elements"]]
        self.assertIn("采购合同", names)
        self.assertNotIn("采购合同与", names, "仍是字符级删除留下的残词")
        self.assertNotIn("与承运记录", names)
        blob = " ".join(names + [str(e.get("basis")) for e in ev["elements"]]
                        + list(ev["direct_missing"]) + [str(ev["remedy"])])
        for m in self.na:
            self.assertNotIn(m, blob, "证据链仍要求本业态不适用资料「%s」" % m)

    def test_fully_not_applicable_is_dropped_and_disclosed(self):
        """整项不适用 ⇒ 不进证据角色表，且**如实披露**（不得静默丢）。"""
        rl = {"id": "RL-T-2", "evidence_chain": [
            {"role": "间接证据", "name": "物流单据与承运记录", "purpose": "证明货物流真实"}]}
        ev = build_evidence_chain({"type": "t"}, rl, [], {"industry": SERVICE_IND})
        self.assertEqual([e["name"] for e in ev["elements"]], [])
        ex = ev.get("industry_excluded") or []
        self.assertTrue(any(x.get("name") == "物流单据与承运记录" for x in ex),
                        "整项不适用被静默丢弃，未记入 industry_excluded")

    def test_rebuttal_never_stripped(self):
        """反证 = 正当理由（不是企业要交的材料）⇒ **永不剔除**。"""
        rl = {"id": "RL-T-3", "evidence_chain": [
            {"role": "反证", "name": "物流单据与承运记录", "purpose": "属正当理由"}]}
        ev = build_evidence_chain({"type": "t"}, rl, [], {"industry": SERVICE_IND})
        self.assertEqual([e["name"] for e in ev["elements"]], ["物流单据与承运记录"])
        self.assertEqual(ev.get("industry_excluded") or [], [])

    def test_no_industry_means_no_exclusion(self):
        """业态取不到 ⇒ 行为与改造前一致（不得无据少列）。"""
        rl = {"id": "RL-T-4", "evidence_chain": [
            {"role": "直接证据", "name": "采购合同与入库验收单", "purpose": "p"}]}
        ev = build_evidence_chain({"type": "t"}, rl, [], {})
        self.assertEqual([e["name"] for e in ev["elements"]], ["采购合同与入库验收单"])


class TestCrossLayerConsistency(unittest.TestCase):
    """跨模块一致：报告层/要件层与权威**同一结果**（多头维护即事故）。"""

    def setUp(self):
        self.na = _na()
        self.corpus = [
            "采购合同与入库验收单", "物流单据与承运记录", "销售台账、出库单、发货记录",
            "出库单与发货记录", "存货盘点表", "采购合同", "与境外方签署的合同或协议、董事会利润分配决议",
            "合同台账与全部应税凭证", "应付账款明细账及账龄分析", "缴存登记回执、劳动合同",
        ]

    def test_report_layer_is_thin_forwarder(self):
        from engine import enterprise_report as ER
        for name in self.corpus:
            self.assertEqual(ER._strip_not_required(name, self.na),
                             exclude_not_required_material(name, self.na),
                             "报告层与权威结果不一致：「%s」" % name)

    def test_constituent_layer_matches_authority(self):
        """要件层：段划分与判定必须与权威一致（旧实现切段表不含「与」+ 双向包含 ⇒ 误判整要件不适用）。"""
        keep, drop, _ = classify_not_required_segments("采购合同与入库验收单", self.na)
        self.assertEqual(keep, ["采购合同"])
        self.assertEqual(drop, ["入库验收单"])
        joined = "、".join(keep)
        self.assertEqual(joined, exclude_not_required_material("采购合同与入库验收单", self.na))

    def test_text_level_authority(self):
        txt = "提供付款对应的采购合同、入库验收单、物流单据，并对资金回流路径作出书面说明。"
        got = exclude_not_required_in_text(txt, self.na)
        for m in self.na:
            self.assertNotIn(m, got)
        self.assertIn("采购合同", got)

    def test_no_duplicate_definition(self):
        """新写函数必须删旧定义：每个权威名在权威文件里**恰好一处** `def`。"""
        p = os.path.join(ROOT, "engine", "industry_resolver.py")
        with open(p, encoding="utf-8") as f:
            txt = f.read()
        for fn in ("classify_not_required_segments", "exclude_not_required_material",
                   "exclude_not_required_in_text", "not_required_materials"):
            self.assertEqual(len(re.findall(r"^def %s\(" % fn, txt, re.M)), 1,
                             "`%s` 定义数 ≠ 1（旧定义会静默覆盖新定义）" % fn)


class TestProductLevel(unittest.TestCase):
    """产物级：报告可见字段不得要求服务型企业补货物流资料，且不得有残词。"""

    ART = os.path.join(ROOT, "scripts", "four_reports", "company_1_full.json")

    def setUp(self):
        if not os.path.exists(self.ART):
            self.skipTest("无真跑产物")
        import json
        with open(self.ART, encoding="utf-8") as f:
            d = json.load(f)
        self.d = d.get("report") if isinstance(d.get("report"), dict) else d

    def test_no_not_required_material_in_evidence_fields(self):
        ind = (self.d.get("target_entity") or {}).get("industry")
        na, _ = not_required_materials(ind)
        if not na:
            self.skipTest("该业态无不适用资料")
        rd = ((self.d.get("comprehensive") or {}).get("redline_detection") or {})
        seen = set()
        for key in ("suspicions", "unconfirmed"):
            for s in (rd.get(key) or []):
                rid = s.get("redline_id")
                if rid in seen:
                    continue
                seen.add(rid)
                ev = s.get("evidence_chain") or {}
                vis = [str(e.get("name") or "") for e in (ev.get("elements") or [])]
                vis += [str(e.get("basis") or "") for e in (ev.get("elements") or [])]
                vis += [str(x) for x in (ev.get("direct_missing") or [])]
                vis += [str(x) for x in (ev.get("missing_material_names") or [])]
                vis += [str(x) for x in (ev.get("verify_material_names") or [])]
                vis.append(str(ev.get("remedy") or ""))
                blob = " ".join(vis)
                for m in na:
                    self.assertNotIn(m, blob, "%s：仍要求本业态不适用资料「%s」" % (rid, m))

    def test_no_dangling_residual_in_report(self):
        tpl = set()
        for r in (_RL_SEQ or []):
            for it in (r.get("evidence_chain") or []):
                tpl.add(str(it.get("name") or "").strip())
        rd = ((self.d.get("comprehensive") or {}).get("redline_detection") or {})
        for key in ("suspicions", "unconfirmed"):
            for s in (rd.get(key) or []):
                for e in ((s.get("evidence_chain") or {}).get("elements") or []):
                    nm = str(e.get("name") or "")
                    if nm in tpl:
                        continue
                    self.assertFalse(nm and any(c in nm for c in "与及和"),
                                     "证据名称含残词：「%s」（%s）" % (nm, s.get("redline_id")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
