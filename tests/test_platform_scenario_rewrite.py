from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class PlatformScenarioContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(
            (STATIC / "platform_scenario_contracts.json").read_text(encoding="utf-8")
        )

    def test_eight_overlay_scenes_have_complete_five_chain_contracts(self):
        scenes = self.payload["scenarios"]
        self.assertEqual(len(scenes), 8)
        self.assertEqual({scene["id"] for scene in scenes}, {f"PLT-{n:02d}" for n in range(1, 9)})
        for scene in scenes:
            self.assertEqual(scene["maturity"], "M2.5_boundary_tested")
            for key in ("doubt", "clue_chain", "evidence_chain", "analysis_chain", "domain_collaboration"):
                self.assertIn(key, scene)
            self.assertGreaterEqual(len(scene["clue_chain"]["steps"]), 5)
            self.assertGreaterEqual(len(scene["evidence_chain"]["fact_elements"]), 6)
            self.assertGreaterEqual(len(scene["evidence_chain"]["opposing_sources"]), 5)
            self.assertGreaterEqual(len(scene["analysis_chain"]["reasoning"]), 7)
            self.assertGreaterEqual(len(scene["domain_collaboration"]["partners"]), 5)
            self.assertEqual(
                {case["case"] for case in scene["validation_cases"]},
                {"positive", "negative", "ambiguous"},
            )

    def test_absorption_is_selective_traceable_and_never_directly_released(self):
        absorbed = []
        no_direct_match = set()
        for scene in self.payload["scenarios"]:
            migration = scene["legacy_absorption"]
            ids = migration["legacy_rule_ids"]
            if ids:
                self.assertEqual(
                    migration["absorption_status"],
                    "absorbed_into_scene_contract_not_released",
                )
                absorbed.extend(ids)
            else:
                self.assertEqual(migration["absorption_status"], "no_direct_legacy_match_new_contract")
                no_direct_match.add(scene["id"])
            self.assertTrue(migration["absorption_reason"])
            self.assertTrue(migration["boundary"])
        self.assertEqual(no_direct_match, {"PLT-01", "PLT-04"})
        self.assertEqual(len(absorbed), 43)
        self.assertEqual(len(absorbed), len(set(absorbed)))

        retail = json.loads(
            (STATIC / "wholesale_retail_scenario_contracts.json").read_text(encoding="utf-8")
        )
        retail_ids = {
            legacy_id
            for scene in retail["scenarios"]
            for legacy_id in scene["legacy_absorption"]["legacy_rule_ids"]
        }
        self.assertTrue(set(absorbed).isdisjoint(retail_ids))

    def test_current_reporting_freight_live_and_privacy_sources_are_present(self):
        sources = {source["id"]: source for source in self.payload["official_sources"]}
        for source_id in (
            "SRC-PLT-REPORT-810", "SRC-PLT-REPORT-15", "SRC-PLT-WORKER-16",
            "SRC-PLT-PENALTY-22", "SRC-PLT-FREIGHT-2026", "SRC-PLT-LIVE-2026",
            "SRC-PLT-PIPL",
        ):
            self.assertIn(source_id, sources)
            self.assertTrue(sources[source_id]["url"].startswith("https://"))
        self.assertIn("privacy_controls", self.payload["common_contract"])
        self.assertIn("自动停业整顿", self.payload["common_contract"]["forbidden_outputs"])


class PlatformScenarioPlannerTests(unittest.TestCase):
    def test_plan_routes_platform_overlay_and_preserves_findings(self):
        from engine.scenario_methodology import build_scenario_review_plan

        files = [
            {"type": "generic_data", "file": "平台基本信息域名业务线系统日志.xlsx"},
            {"type": "generic_data", "file": "平台账户实名认证经营者身份.xlsx"},
            {"type": "generic_data", "file": "平台订单交易流水退货退款.xlsx"},
            {"type": "generic_data", "file": "季度涉税信息报送表及回执.xlsx"},
            {"type": "bank_statement", "file": "平台支付分账结算.xlsx"},
            {"type": "voucher", "file": "平台收入会计凭证.xlsx"},
            {"type": "tax_return", "file": "平台税费申报.xlsx"},
        ]
        findings = [{"type": "平台订单季度报送差异", "detail": "平台结算与报送收入待核"}]
        before = copy.deepcopy(findings)
        plan = build_scenario_review_plan("互联网平台经济", files, findings)

        self.assertTrue(plan["applicable"])
        self.assertEqual(plan["industry_code"], "OVERLAY-PLATFORM")
        self.assertEqual(plan["contract_asset"], "platform_scenario_contracts")
        self.assertEqual(plan["scene_count"], 8)
        by_id = {scene["scene_id"]: scene for scene in plan["scenes"]}
        self.assertEqual(by_id["PLT-03"]["status"], "资料就绪_待人工核验")
        self.assertGreaterEqual(by_id["PLT-03"]["candidate_signal_count"], 1)
        self.assertEqual(findings, before)


class PlatformScenarioIntegrationTests(unittest.TestCase):
    def test_coverage_discloses_overlay_without_claiming_m3(self):
        from engine.methodology_coverage import build_methodology_coverage

        report = build_methodology_coverage(STATIC)
        self.assertEqual(report["version"], "1.7.0")
        self.assertEqual(report["inventory"]["rewritten_m25_scenarios"], 55)
        overlay = report["overlay_scenario_summary"]
        self.assertEqual(overlay["rewritten_m25_scenarios"], 8)
        self.assertEqual(overlay["verified_specific_rules"], 0)
        self.assertIn("待脱敏真实样本验证", overlay["state"])
        rewrite = report["candidate_governance"]["rewrite_program"]["summary"]
        self.assertEqual(rewrite["absorbed_into_scene_contract"], 167)
        self.assertEqual(rewrite["queued_not_rewritten"] + rewrite["absorbed_into_scene_contract"], 1720)
        self.assertEqual(rewrite["released_from_legacy_library"], 0)

    def test_api_frontend_and_cache_publish_guarded_platform_contract(self):
        main_text = (ROOT / "main.py").read_text(encoding="utf-8")
        frontend = (STATIC / "js" / "tax-pipeline-pages.js").read_text(encoding="utf-8")
        index = (STATIC / "index.html").read_text(encoding="utf-8")

        self.assertIn('"platform_scenario_contracts": "platform_scenario_contracts.json"', main_text)
        self.assertIn("/api/methodology/assets/platform_scenario_contracts", frontend)
        self.assertIn("平台经济叠加场景五链配套重写", frontend)
        self.assertIn("平台经济叠加能力", frontend)
        self.assertIn("tax-pipeline-pages.js?v=2026080301", index)


if __name__ == "__main__":
    unittest.main()
