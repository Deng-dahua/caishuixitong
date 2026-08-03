from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class CanonicalMethodologyCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from engine.methodology_catalog import (
            SCENARIO_FILES,
            load_canonical_catalog,
            load_flat_analysis,
            load_flat_clues,
            load_flat_evidence,
            load_flat_rules,
            load_reviewed_scenario_contracts,
            methodology_inventory,
        )
        from engine.methodology_portfolio import load_methodology_portfolio

        cls.scenario_files = SCENARIO_FILES
        cls.catalog = load_canonical_catalog()
        cls.portfolio = load_methodology_portfolio()
        cls.payloads = {
            code: load_reviewed_scenario_contracts(code) for code in SCENARIO_FILES
        }
        cls.scenarios = [
            scene
            for payload in cls.payloads.values()
            for scene in payload.get("scenarios", [])
        ]
        cls.rules = load_flat_rules()
        cls.clues = load_flat_clues()
        cls.evidence = load_flat_evidence()
        cls.analysis = load_flat_analysis()
        cls.inventory = methodology_inventory()

    def test_retired_assets_are_not_part_of_release(self):
        retired = (
            "tax_risk_rules_local_export.json",
            "cross_domain_clues.json",
            "cross_domain_evidence.json",
            "cross_domain_analysis.json",
        )
        for filename in retired:
            self.assertFalse((STATIC / filename).exists(), filename)
        self.assertFalse((ROOT / "engine" / "candidate_rule_governance.py").exists())

    def test_common_fact_catalog_is_complete_and_source_anchored(self):
        modules = self.catalog["modules"]
        raw_rules = [rule for module in modules for rule in module["rules"]]
        self.assertEqual(self.catalog["version"], "3.0.0")
        self.assertEqual(len(modules), 20)
        self.assertEqual(len(raw_rules), 67)
        self.assertEqual(len({module["id"] for module in modules}), len(modules))
        self.assertEqual(len({rule["id"] for rule in raw_rules}), len(raw_rules))
        source_ids = {source["id"] for source in self.catalog["official_sources"]}
        self.assertIn("SRC-PROCEDURE-52", source_ids)
        self.assertIn("SRC-CASE-SOURCE", source_ids)
        self.assertIn("SRC-VAT-LAW-2026", source_ids)
        self.assertIn("SRC-EINVOICE", source_ids)
        for module in modules:
            self.assertTrue(module["activation_gate"])
            self.assertTrue(module["clue_paths"])
            self.assertTrue(module["evidence_plan"]["supporting"])
            self.assertTrue(module["evidence_plan"]["opposing"])
            self.assertTrue(module["analysis_tests"])
            self.assertTrue(set(module["source_refs"]).issubset(source_ids))

    def test_portfolio_covers_all_industries_and_overlay_businesses(self):
        contracts = self.portfolio["contracts"]
        self.assertEqual(self.portfolio["version"], "3.0.0")
        self.assertEqual(len(contracts), 23)
        self.assertEqual({item["code"] for item in contracts if len(item["code"]) == 1}, set("ABCDEFGHIJKLMNOPQRST"))
        self.assertEqual(
            {item["code"] for item in contracts if item["code"].startswith("OVERLAY-")},
            {"OVERLAY-PLATFORM", "OVERLAY-CROSS-BORDER", "OVERLAY-GROUP"},
        )
        self.assertEqual(len(self.scenarios), 161)
        counts = [len(item["scenarios"]) for item in contracts]
        self.assertGreater(len(set(counts)), 4)
        self.assertGreaterEqual(min(counts), 5)
        self.assertGreaterEqual(max(counts), 10)
        self.assertGreaterEqual(len(self.inventory["clue_depths"]), 6)
        self.assertLessEqual(min(self.inventory["clue_depths"]), 4)
        self.assertGreaterEqual(max(self.inventory["clue_depths"]), 12)
        self.assertEqual(self.inventory["validation_depths"], [3, 4, 5, 6])
        self.assertEqual(self.inventory["domain_collaboration_depths"], [3, 4, 5])

    def test_every_scene_is_a_complete_integrated_contract(self):
        scene_ids = set()
        for scene in self.scenarios:
            self.assertNotIn(scene["id"], scene_ids)
            scene_ids.add(scene["id"])
            self.assertTrue((scene.get("doubt") or {}).get("target_fact"), scene.get("id"))
            self.assertTrue((scene.get("applicability") or {}).get("required_source_families"), scene.get("id"))
            self.assertTrue((scene.get("clue_chain") or {}).get("steps"), scene.get("id"))
            evidence = scene.get("evidence_chain") or {}
            self.assertTrue(evidence.get("supporting_sources"), scene.get("id"))
            self.assertTrue(evidence.get("opposing_sources"), scene.get("id"))
            self.assertTrue(evidence.get("insufficient_when"), scene.get("id"))
            analysis = scene.get("analysis_chain") or {}
            self.assertTrue(analysis.get("reasoning"), scene.get("id"))
            self.assertTrue(analysis.get("tax_boundary"), scene.get("id"))
            self.assertTrue((scene.get("domain_collaboration") or {}).get("lead"), scene.get("id"))
            self.assertTrue((scene.get("domain_collaboration") or {}).get("partners"), scene.get("id"))
            self.assertTrue((scene.get("report_contract") or {}).get("forbidden"), scene.get("id"))
            self.assertTrue(scene.get("validation_cases"), scene.get("id"))
            encoded = json.dumps(scene, ensure_ascii=False)
            for forbidden in ("legacy_absorption", "已吸收", "1720条", "候选检索", "迁移账册"):
                self.assertNotIn(forbidden, encoded, scene.get("id"))

    def test_newly_expanded_industries_have_scene_specific_authorship(self):
        from engine.methodology_portfolio import (
            DETAILED_CODES,
            PORTFOLIO_CODES,
            SCENARIO_DETAILS,
            _scenario_names,
        )

        for code in PORTFOLIO_CODES:
            if code in DETAILED_CODES:
                continue
            expected_names = set(_scenario_names()[code])
            detail_names = set((SCENARIO_DETAILS.get(code) or {}).keys())
            self.assertEqual(detail_names, expected_names, code)
            for name, detail in SCENARIO_DETAILS[code].items():
                self.assertTrue(detail["target"], (code, name))
                self.assertGreaterEqual(len(detail["sources"]), 4, (code, name))
                self.assertGreaterEqual(len(detail["path"].split("→")), 4, (code, name))
                self.assertGreaterEqual(len(detail["alternatives"]), 2, (code, name))

    def test_flat_assets_include_common_and_industry_contracts(self):
        self.assertEqual(self.inventory["canonical_rules"], 67)
        self.assertEqual(self.inventory["industry_fact_contracts"], 161)
        self.assertEqual(len(self.rules), 228)
        self.assertEqual(len(self.clues), 188)
        self.assertEqual(len(self.evidence), 181)
        self.assertEqual(len(self.analysis), 181)
        for items in (self.rules, self.clues, self.evidence, self.analysis):
            self.assertEqual(len(items), len({item["id"] for item in items}))
        self.assertEqual(
            sum(rule["type"] == "authoritative_review_contract" for rule in self.rules),
            67,
        )
        self.assertEqual(
            sum(rule["type"] == "industry_fact_review_contract" for rule in self.rules),
            161,
        )
        for rule in self.rules:
            self.assertIsNone(rule["threshold"])
            self.assertTrue(rule["human_review_required"])
            self.assertFalse(rule["automatic_determination_allowed"])

    def test_every_industry_can_generate_a_review_plan(self):
        from engine.scenario_methodology import build_scenario_review_plan

        examples = {
            "A": "农业", "B": "矿山", "C": "制造业", "D": "供电企业",
            "E": "建筑施工", "F": "零售", "G": "物流运输", "H": "餐饮",
            "I": "软件服务", "J": "保险公司", "K": "房地产开发", "L": "劳务派遣",
            "M": "技术服务", "N": "污水处理", "O": "维修服务", "P": "教育培训",
            "Q": "医疗机构", "R": "文化演出", "S": "社会组织", "T": "国际组织",
            "OVERLAY-PLATFORM": "互联网平台", "OVERLAY-CROSS-BORDER": "跨境贸易",
            "OVERLAY-GROUP": "集团关联交易",
        }
        for expected_code, industry in examples.items():
            plan = build_scenario_review_plan(industry, [], [])
            self.assertTrue(plan["applicable"], industry)
            self.assertEqual(plan["industry_code"], expected_code, industry)
            self.assertGreaterEqual(plan["scene_count"], 5, industry)
            for scene in plan["scenes"]:
                self.assertIn("观察信号只用于确定核验顺序", scene["observed_signal_boundary"])

    def test_runtime_and_frontend_use_current_portfolio(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        pipeline = (ROOT / "engine" / "pipeline.py").read_text(encoding="utf-8")
        index = (STATIC / "index.html").read_text(encoding="utf-8")
        page = (STATIC / "js" / "methodology-v3.js").read_text(encoding="utf-8")
        framework = (STATIC / "methodology_framework.json").read_text(encoding="utf-8")
        self.assertIn("load_methodology_portfolio", main)
        self.assertIn("完整行业场景已生成核验计划", pipeline)
        self.assertIn("methodology-v3.js", index)
        self.assertIn("/api/methodology/assets/portfolio", page)
        self.assertIn("全行业完整场景合同", page)
        for forbidden in ("1720条", "candidate_layer", "已吸收"):
            self.assertNotIn(forbidden, framework)
            self.assertNotIn(forbidden, page)


if __name__ == "__main__":
    unittest.main()
