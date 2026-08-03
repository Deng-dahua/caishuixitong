from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ScenarioExecutionTests(unittest.TestCase):
    def _manufacturing_files(self):
        return [
            {"file": "存货收发存.xlsx", "type": "inventory"},
            {"file": "会计凭证.xlsx", "type": "voucher"},
            {"file": "销售发票.xlsx", "type": "sales_invoice"},
            {"file": "采购发票.xlsx", "type": "purchase_invoice"},
            {"file": "业务合同.xlsx", "type": "contract"},
        ]

    def test_atomic_inventory_observation_enters_governed_scene(self):
        from engine.scenario_execution import execute_scenario_methodology

        result = execute_scenario_methodology(
            "制造业",
            file_results=self._manufacturing_files(),
            engine_data={
                "inventory": [{
                    "code": "SKU-001",
                    "name": "脱敏测试存货",
                    "open_qty": 10,
                    "in_qty": 2,
                    "out_qty": 15,
                    "end_qty": -3,
                }],
            },
        )
        self.assertEqual(result["governance_status"], "scenario_contract_governed")
        self.assertEqual(result["industry_code"], "C")
        self.assertEqual(result["industry_scenes_assessed"], 10)
        self.assertGreaterEqual(result["trusted_observation_count"], 1)
        self.assertGreaterEqual(result["industry_scene_findings"], 1)
        self.assertTrue(all(item["_scenario_governed"] for item in result["findings"]))
        self.assertTrue(all(item["required_human_review"] for item in result["findings"]))
        self.assertTrue(all(not item["automatic_determination_allowed"] for item in result["findings"]))
        self.assertTrue(all(not item["report_release_allowed"] for item in result["findings"]))
        self.assertEqual(
            len({item["scene_fact_id"] for item in result["findings"]}),
            len(result["findings"]),
        )

    def test_data_quality_issue_stays_in_common_gate_and_blocks_release(self):
        from engine.scenario_execution import execute_scenario_methodology, seal_scenario_findings

        result = execute_scenario_methodology(
            "制造业",
            file_results=[{"file": "销项发票.xlsx", "type": "sales_invoice"}],
            engine_data={
                "sal_invs": [
                    {"inv_no": f"TEST-{index:03d}", "amount": 100, "tax": 13, "total": 100, "date": "2026-01-01"}
                    for index in range(1, 4)
                ],
            },
        )
        self.assertTrue(result["source_quality_issues"])
        self.assertGreaterEqual(result["common_fact_findings"], 1)
        sealed = seal_scenario_findings(result)
        self.assertEqual(len(sealed), len(result["findings"]))
        self.assertTrue(all(item["release_status"] == "草稿_待人工复核" for item in sealed))

    def test_unknown_industry_never_falls_back_to_legacy_findings(self):
        from engine.scenario_execution import execute_scenario_methodology

        result = execute_scenario_methodology(
            "待确认行业",
            file_results=[{"file": "存货.xlsx", "type": "inventory"}],
            engine_data={"inventory": [{"code": "A", "end_qty": -1}]},
        )
        self.assertFalse(result["industry_resolved"])
        self.assertEqual(result["industry_scenes_assessed"], 0)
        self.assertTrue(all(item["scenario_scope"] == "common_fact_gate" for item in result["findings"]))
        self.assertTrue(all(item.get("score") == 0 for item in result["findings"]))

    def test_one_click_pipeline_enforces_scenario_boundary(self):
        pipeline = (ROOT / "engine" / "pipeline.py").read_text(encoding="utf-8")
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("execute_scenario_methodology", pipeline)
        self.assertIn("seal_scenario_findings", pipeline)
        self.assertIn("_enforce_scenario_execution_boundary", main)
        self.assertIn('"2.0-scenario-driven"', main)


if __name__ == "__main__":
    unittest.main()
