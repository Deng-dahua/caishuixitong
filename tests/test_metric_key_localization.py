# -*- coding: utf-8 -*-
"""报告「量化结果」的**键与值都必须汉化** —— 契约测试。

## 病根（已复现，非特例）
报告「二、发现的依据」会把引擎 `observed_metrics` 列成「中文键=值」。
历史上**两处**各自 `"%s=%s" % (k, v)` 拼**引擎原始键名**，绕过键汉化唯一权威
`_translate_key`，于是报告正文出现：

    量化结果：declared_input_tax_total=192463.32；invoice_input_tax_total=225093.81；g…
    量化结果：…经营模式=b2b_or_unknown          ← 键已汉化，**值**漏了
    量化结果：…已提供应付账款明细=True          ← 布尔值也是英文

三处都属同一根因（**绕开汉化权威**），且是"一个概念多份实现"的老病。
现两处都薄转发到唯一实现 `enterprise_report._metric_kv_text`。

## 判据
  ① 键过汉化；译不出 ⇒ **整对不写**（绝不用英文顶替）；
  ② 值过汉化：布尔写「是/否」；枚举码（纯小写/下划线）必须译出，译不出 ⇒ 整对不写；
  ③ 幂等确定性：同一输入多次调用结果一致；
  ④ 产物级：报告层任何**文本**字段都不得出现 `标识符=` 形态（变量名入文）。
"""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine.enterprise_report import (                     # noqa: E402
    _ENUM_CODE_CN, _METRIC_CN, _metric_kv_text, _translate_key)

ART = os.path.join(ROOT, "tests", "fixtures", "company_1_full.json")   # ★ 夹具（版本库内固化）
_ENUM_LIKE = re.compile(r"^[a-z][a-z0-9_]*$")
_IDENT_EQ = re.compile(r"(?<![A-Za-z_])[a-z][a-z0-9_]{3,}=")


class TestMetricKvText(unittest.TestCase):
    """唯一实现的键/值汉化契约。"""

    def test_key_is_localized(self):
        out = _metric_kv_text({"declared_input_tax_total": 192463.32, "gap_months": 1})
        self.assertNotIn("declared_input_tax_total", out)
        self.assertIn("申报进项税额合计=192463.32", out)

    def test_unregistered_key_is_omitted_not_english(self):
        out = _metric_kv_text({"this_key_is_not_registered_anywhere": 7,
                               "gap_months": 1})
        self.assertNotIn("this_key_is_not_registered_anywhere", out)
        self.assertIn("差异月份数=1", out)      # 已登记的仍保留，不因邻居未登记而丢

    def test_bool_written_in_chinese(self):
        out = _metric_kv_text({"ap_detail_provided": True, "ap_from_trial_balance": False})
        self.assertNotIn("True", out)
        self.assertNotIn("False", out)
        self.assertIn("已提供应付账款明细=是", out)
        self.assertIn("应付账款取自余额表=否", out)

    def test_enum_value_is_localized(self):
        out = _metric_kv_text({"business_model": "b2b_or_unknown"})
        self.assertNotIn("b2b_or_unknown", out)
        self.assertIn("经营模式=面向企业为主或未标注", out)

    def test_unregistered_enum_value_is_omitted(self):
        out = _metric_kv_text({"business_model": "enum_code_not_registered_zzz"})
        self.assertNotIn("enum_code_not_registered_zzz", out)

    def test_nested_structures_skipped(self):
        out = _metric_kv_text({"examples": [{"counterparty": "x", "receipts": 1.0}],
                               "gap_months": 1})
        self.assertNotIn("{", out)
        self.assertNotIn("counterparty", out)
        self.assertIn("差异月份数=1", out)

    def test_no_ascii_letter_in_output(self):
        """总判据：输出里**不得出现任何 ASCII 字母**（键与值都不许）。"""
        met = {"declared_input_tax_total": 1.0, "gap_months": 2, "book_payroll_total": 3,
               "business_model": "b2b_or_unknown", "ap_detail_provided": True,
               "unknown_key_zzz": 4, "another": "unknown_enum_yyy",
               "examples": [{"k": 1}]}
        out = _metric_kv_text(met)
        self.assertIsNone(re.search(r"[A-Za-z]", out), "仍有英文残留：%r" % out)

    def test_deterministic(self):
        met = {"gap_months": 1, "book_payroll_total": 2, "business_model": "b2b_or_unknown"}
        self.assertEqual(_metric_kv_text(met), _metric_kv_text(met))
        self.assertEqual(_metric_kv_text(met), _metric_kv_text(dict(met)))

    def test_registry_covers_all_emitted_keys(self):
        """登记表**数据驱动**：本测试文件不写具体企业，只用真实产物普查。

        （普查逻辑与 `scripts/_audit_unlocalized_metrics.py` 同一口径：
          缺哪几个就在 `_METRIC_CN` / `_ENUM_CODE_CN` 各补一行，不改逻辑分支。）
        """
        assert os.path.exists(ART), "测试夹具缺失：%s" % ART
        with open(ART, encoding="utf-8") as fh:
            d = json.load(fh)
        rep = d.get("report") if isinstance(d.get("report"), dict) else d
        seen, bad_k, bad_e = set(), set(), set()

        def scan(fs):
            for f in (fs or []):
                if not isinstance(f, dict) or id(f) in seen:
                    continue
                seen.add(id(f))
                for k, v in (f.get("observed_metrics") or {}).items():
                    if not isinstance(v, (int, float, str, bool)):
                        continue
                    if re.search(r"[A-Za-z]", str(_translate_key(k))):
                        bad_k.add(k)
                    if isinstance(v, str) and _ENUM_LIKE.match(v):
                        if re.search(r"[A-Za-z]", str(_translate_key(v))):
                            bad_e.add(v)

        comp = rep.get("comprehensive") or {}
        scan(rep.get("all_findings"))
        scan((comp.get("scenario_execution") or {}).get("findings"))
        scan((rep.get("scenario_execution") or {}).get("findings"))
        for dom in (rep.get("domain_summary") or []):
            scan(dom.get("findings"))
        for dom in ((comp.get("scenario_execution") or {}).get("domain_summary") or []):
            scan(dom.get("findings"))
        self.assertEqual(sorted(bad_k), [],
                         "这些指标键译不出中文，须在 `_METRIC_CN` 各补一行：%r" % sorted(bad_k))
        self.assertEqual(sorted(bad_e), [],
                         "这些枚举值译不出中文，须在 `_ENUM_CODE_CN` 各补一行：%r" % sorted(bad_e))


class TestProductNoIdentifierInText(unittest.TestCase):
    """产物级：报告层**文本**里不得出现「英文标识符=」形态。"""

    def test_no_identifier_eq_in_report_text(self):
        assert os.path.exists(ART), "测试夹具缺失：%s" % ART
        with open(ART, encoding="utf-8") as fh:
            d = json.load(fh)
        rep = d.get("report") if isinstance(d.get("report"), dict) else d
        er = rep.get("enterprise_readable_report") or {}
        bad = []

        def walk(o, path):
            if isinstance(o, dict):
                for k, v in o.items():
                    walk(v, path + "/" + str(k))
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    walk(v, path + "/[%d]" % i)
            elif isinstance(o, str):
                m = _IDENT_EQ.search(o)
                if m:
                    bad.append((path, o[max(0, m.start() - 30):m.start() + 60]))

        walk(er, "")
        self.assertEqual(bad[:3], [], "报告文本里出现英文变量名入文：%r" % bad[:3])

    def test_metric_cn_has_no_english_values(self):
        """登记表本身不得把英文当译文（否则等于没登记）。

        ⚠ 判据只查**小写英文词**（≥2 字母），**不查全大写缩写** ——
          「BOM定额损耗率」「增值税VAT税负率」这类是中文语境里的既有缩写，属正常译文。
        """
        for k, v in list(_METRIC_CN.items()) + list(_ENUM_CODE_CN.items()):
            self.assertIsNone(re.search(r"[a-z]{2,}", str(v)),
                              "汉化表把「%s」译成了含英文词的「%s」" % (k, v))


if __name__ == "__main__":
    unittest.main(verbosity=2)
