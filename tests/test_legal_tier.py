# -*- coding: utf-8 -*-
"""GAP-18 法规库税务/背景法分离（2026-10-18）。

原差距：7,680 条里税务口径仅 10.1%（774 条），85% 是民法典/刑法等背景法。
「库很大」掩盖「税务覆盖薄」—— 只报总条数等于用总量掩盖结构。

现口径（唯一实现 `engine/legal_tier`，数据源 `config/legal_law_tiers.json`）：
  · `tier_of(law)` → `tax` / `related` / `background`（显式名单 → 关键词 → 兜底背景法）
  · `library_stats()` 给出各档条数与 `tax_share`
  · `disclosure_line()` 是**唯一**对外写法（总量 + 分档 + 税务占比）
"""
from __future__ import annotations

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import legal_tier as LT                                    # noqa: E402


class TierClassificationTests(unittest.TestCase):
    def test_core_tax_laws_are_tax(self):
        for law in ("中华人民共和国增值税法", "中华人民共和国企业所得税法",
                    "中华人民共和国个人所得税法", "中华人民共和国税收征收管理法",
                    "中华人民共和国印花税法", "中华人民共和国发票管理办法"):
            self.assertEqual(LT.tier_of(law), "tax", law)

    def test_related_laws(self):
        for law in ("中华人民共和国会计法", "中华人民共和国海关法",
                    "中华人民共和国社会保险法", "中华人民共和国公司法"):
            self.assertEqual(LT.tier_of(law), "related", law)

    def test_background_laws(self):
        for law in ("民法典", "中华人民共和国刑法", "中华人民共和国刑事诉讼法",
                    "中华人民共和国民事诉讼法", "中华人民共和国立法法"):
            self.assertEqual(LT.tier_of(law), "background", law)

    def test_prefix_and_space_insensitive(self):
        """「中华人民共和国」前缀与空格差异不得影响分层。"""
        self.assertEqual(LT.tier_of("企业所得税法"), "tax")
        self.assertEqual(LT.tier_of(" 中华人民共和国 企业所得税法 "), "tax")

    def test_unknown_law_never_counted_as_tax(self):
        """不认识的 ⇒ background（**宁可低估，也不把背景法算进税务口径**）。"""
        self.assertEqual(LT.tier_of("某部没登记的地方性规定"), "background")
        self.assertEqual(LT.tier_of(""), "background")

    def test_no_hardcoded_law_names_in_code(self):
        """分层判定必须来自配置，源码不得硬编码法名清单。"""
        src = open(os.path.join(ROOT, "engine", "legal_tier.py"), encoding="utf-8").read()
        import re
        hits = re.findall(r"《?中华人民共和国[\u4e00-\u9fff]{2,12}(?:法|条例|办法)》?", src)
        self.assertEqual(hits, [], "硬编码法名：%s" % hits)


class LibraryStatsTests(unittest.TestCase):
    def test_stats_have_three_tiers_and_share(self):
        st = LT.library_stats()
        tiers = {x["tier"]: x for x in st["by_tier"]}
        self.assertEqual(set(tiers), {"tax", "related", "background"})
        self.assertGreater(st["articles"], 0)
        self.assertEqual(sum(x["articles"] for x in st["by_tier"]), st["articles"],
                         "三档条数之和必须等于总数（不得漏算/重算）")
        self.assertGreater(st["tax_share"], 0)
        self.assertLess(st["tax_share"], 0.5,
                        "税务口径若超过一半，说明分层失效（背景法被算进税务）")

    def test_tax_share_is_not_total(self):
        """核心：**税务条数显著小于总条数** —— 这正是"不能只报总数"的证据。"""
        st = LT.library_stats()
        self.assertLess(st["tax_articles"], st["articles"])
        self.assertLess(st["tax_share"], 0.35)

    def test_stats_exposed_by_library_api(self):
        from engine import legal_library as LIB
        st = LIB.stats()
        self.assertIn("by_tier", st, "库统计接口未分档 ⇒ GAP-18 会复发")
        bt = st["by_tier"]
        self.assertIn("tax_share", bt)
        self.assertTrue(any(x["tier"] == "tax" for x in bt["by_tier"]))
        self.assertIn("不得只给", str(st.get("tier_note") or ""))

    def test_disclosure_line_contains_both(self):
        line = LT.disclosure_line()
        self.assertIn("税务核心法", line)
        self.assertIn("%", line)
        # 单一写法：同一份数据两次调用必须一致
        self.assertEqual(line, LT.disclosure_line())


class ConfigAuthorityTests(unittest.TestCase):
    def test_config_is_the_authority(self):
        p = os.path.join(ROOT, "config", "legal_law_tiers.json")
        self.assertTrue(os.path.exists(p))
        cfg = json.loads(open(p, encoding="utf-8").read())
        self.assertIn("laws", cfg)
        self.assertIn("rules", cfg)
        self.assertIn("_why", cfg, "配置必须写明为什么分档（防后人删掉）")
        for k, v in (cfg.get("laws") or {}).items():
            self.assertIn(v, ("tax", "related", "background"), "非法分层值：%s=%s" % (k, v))


class GateTests(unittest.TestCase):
    def test_gate_is_wired(self):
        txt = open(os.path.join(ROOT, "tools", "audit_consistency.py"),
                   encoding="utf-8").read()
        self.assertIn("def check_legal_library_tier_disclosure", txt)
        self.assertIn("+ check_legal_library_tier_disclosure()", txt,
                      "闸门未接入 run_checks ⇒ 等于没有")


if __name__ == "__main__":
    unittest.main()
