# -*- coding: utf-8 -*-
"""GAP-17 覆盖率指标拆两列（2026-10-18）。

原差距：100% 里约 36%~40% 的引用只到法名（`split_citations` 129 段中 52 段无条号）；
指标只判"存在"不判"正确"，拿单一数字当合规度会误导。

现口径（唯一实现 `engine/legal_coverage.compute`）：
  · `law_coverage`     **引用可定位率** —— 该**法规**在正文库里
  · `article_coverage` **条号级可核对率** —— 在**写了条号**的引用中，条号也真对上
  · `no_article_refs`  只写到法名、无法条号核对的引用数（**如实披露**）
  · `coverage`         仅兼容旧键保留，**不得单独作为合规度对外表述**
"""
from __future__ import annotations

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import legal_coverage as LC                       # noqa: E402

#: 一份**受控小库**（不依赖真实 7680 条，判据才稳定可复现）
LIB = [
    {"law": "中华人民共和国增值税法", "article": "第一条", "content": "x", "source": "s"},
    {"law": "中华人民共和国增值税法", "article": "第二十八条", "content": "x", "source": "s"},
    {"law": "中华人民共和国企业所得税法", "article": "第八条", "content": "x", "source": "s"},
]


class _PatchRedlines:
    """临时替换 `engine.tax_redlines.REDLINES`（只在本测试期间）。"""

    def __init__(self, items):
        self.items = items
        self._orig = None

    def __enter__(self):
        from engine import tax_redlines as TR
        self._orig = TR.REDLINES
        TR.REDLINES = self.items
        return self

    def __exit__(self, *a):
        from engine import tax_redlines as TR
        TR.REDLINES = self._orig
        return False


class TwoColumnMetricTests(unittest.TestCase):
    def _compute(self, citations):
        items = [{"id": "RL-T-%02d" % (i + 1), "legal_basis": c}
                 for i, c in enumerate(citations)]
        with _PatchRedlines(items):
            return LC.compute(LIB)

    def test_law_coverage_counts_law_only(self):
        """只写法名 ⇒ 引用可定位率算命中，但条号级不参与。"""
        r = self._compute(["《中华人民共和国增值税法》"])
        self.assertEqual(r["total_refs"], 1)
        self.assertEqual(r["law_coverage"], 1.0)
        self.assertEqual(r["no_article_refs"], 1)
        self.assertEqual(r["article_total_refs"], 0)
        # 没写条号 ⇒ 条号级分母为 0；不得伪造成 100%
        self.assertEqual(r["article_coverage"], 0.0)

    def test_article_coverage_only_counts_article_refs(self):
        r = self._compute(["《中华人民共和国增值税法》第二十八条"])
        self.assertEqual(r["article_total_refs"], 1)
        self.assertEqual(r["article_matched_refs"], 1)
        self.assertEqual(r["article_coverage"], 1.0)
        self.assertEqual(r["no_article_refs"], 0)

    def test_two_columns_diverge(self):
        """同一批引用下两列**必须能不同** —— 否则拆列没意义。"""
        r = self._compute([
            "《中华人民共和国增值税法》第二十八条",   # 条号对上
            "《中华人民共和国企业所得税法》第三十条",   # 法在库、条号不在
            "《中华人民共和国增值税法》",               # 只到法名
        ])
        self.assertEqual(r["total_refs"], 3)
        self.assertEqual(r["law_coverage"], 1.0)                  # 三部法都在库
        self.assertEqual(r["article_total_refs"], 2)
        self.assertEqual(r["article_matched_refs"], 1)
        self.assertEqual(r["article_coverage"], 0.5)              # ★ 只有一半条号可核对
        self.assertEqual(r["no_article_refs"], 1)
        # 两列不相等 —— 单列口径必然误导
        self.assertNotEqual(r["law_coverage"], r["article_coverage"])

    def test_law_missing_kind_is_distinguished(self):
        r = self._compute(["《中华人民共和国印花税法》第五条"])
        self.assertEqual(r["law_coverage"], 0.0)
        kinds = {u["miss_kind"] for u in r["unmatched"]}
        self.assertEqual(kinds, {"law_missing"})

    def test_article_missing_kind_is_distinguished(self):
        r = self._compute(["《中华人民共和国增值税法》第九十九条"])
        self.assertEqual(r["law_coverage"], 1.0)
        self.assertEqual(r["article_coverage"], 0.0)
        kinds = {u["miss_kind"] for u in r["unmatched"]}
        self.assertEqual(kinds, {"article_missing"},
                         "法在库但条号不对，必须与'法没进库'分开报（补库 vs 补条文）")

    def test_registry_contains_both_columns(self):
        """登记文件（闸门比对基线）必须含两列 + 仅到法名的段数。"""
        p = os.path.join(ROOT, "config", "legal_text_coverage.json")
        self.assertTrue(os.path.exists(p))
        cov = json.loads(open(p, encoding="utf-8").read())
        for k in ("law_coverage", "article_coverage", "no_article_refs",
                  "article_total_refs", "article_matched_refs", "law_matched_refs"):
            self.assertIn(k, cov, "登记缺少 GAP-17 指标：%s" % k)
        self.assertIn("不得单独作为合规度", str(cov.get("_note") or ""))

    def test_registry_matches_recompute(self):
        """登记值必须与现算一致（否则闸门会假红/假绿）。"""
        p = os.path.join(ROOT, "config", "legal_text_coverage.json")
        cov = json.loads(open(p, encoding="utf-8").read())
        now = LC.compute()
        for k in ("total_refs", "law_coverage", "article_coverage", "no_article_refs"):
            self.assertEqual(cov.get(k), now.get(k),
                             "%s 登记值 %r 与现算 %r 不一致" % (k, cov.get(k), now.get(k)))


class GateWiringTests(unittest.TestCase):
    """闸门必须真的在比两列（接线自检 + 堵住"把两列合并回一列"）。"""

    def test_gate_compares_both_columns(self):
        txt = open(os.path.join(ROOT, "tools", "audit_consistency.py"),
                   encoding="utf-8").read()
        self.assertIn("law_coverage", txt)
        self.assertIn("article_coverage", txt)
        self.assertIn("no_article_refs", txt)
        self.assertIn("引用可定位率", txt)
        self.assertIn("条号级可核对率", txt)


if __name__ == "__main__":
    unittest.main()
