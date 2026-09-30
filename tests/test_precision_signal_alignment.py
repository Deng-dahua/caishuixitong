# -*- coding: utf-8 -*-
"""精度回归：信号必须对齐「风险发生侧」。

每条被收紧掉的「通用误报源词」必须不再误触发对应红线；
每条保留的「具体风险信号」必须仍能触发。
不依赖 4 家公司基线文件（其会被重跑覆盖），用合成数据确定性验证。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.special_redline_detectors import run_special_redline_detection
from engine.gap_risk_detectors import detect_asset_loss, detect_vehicle_tax
from engine.gap_tax_obligations import run_gap_tax_obligation_detection


def _ids(findings):
    return {f.get("redline_id") for f in findings if f.get("redline_id")}


class SpecialSignalAlignmentTests(unittest.TestCase):
    # ── 通用误报源词：必须不再误报 ──
    def test_fund004_no_trigger_on_cash_account(self):
        """库存现金/现金日记账 每家企业都有，≠大额现金交易。"""
        data = {"balances": [{"科目名称": "库存现金", "期末借方": 1000}],
                "vouchers": [{"摘要": "登记现金日记账", "金额": 1}]}
        self.assertNotIn("RL-FUND-004", _ids(run_special_redline_detection(data)))

    def test_inv003_no_trigger_on_production_account(self):
        """生产成本/领料 每家制造型企业都有，≠投入产出不匹配。"""
        data = {"vouchers": [{"摘要": "结转生产成本", "科目": "生产成本"},
                              {"摘要": "领料", "科目": "原材料"}]}
        self.assertNotIn("RL-INV-003", _ids(run_special_redline_detection(data)))

    def test_ast002_no_trigger_on_other_income(self):
        """其他收益 标准损益科目，几乎每家企业都有，≠政府补助。"""
        data = {"vouchers": [{"摘要": "确认其他收益（个税手续费返还）", "科目": "其他收益"}]}
        self.assertNotIn("RL-AST-002", _ids(run_special_redline_detection(data)))

    def test_spt004_no_trigger_on_sewage_fee(self):
        """污水 水费发票「污水处理费」每家企业都有，≠直接排放污染物。"""
        data = {"vouchers": [{"摘要": "支付污水处理费", "科目": "管理费用"}]}
        self.assertNotIn("RL-SPT-004", _ids(run_special_redline_detection(data)))

    def test_spt009_no_trigger_on_longterm_equity(self):
        """长期股权投资 每家企业投资都有，≠股权转让。"""
        data = {"balances": [{"科目名称": "长期股权投资", "期末借方": 50000}]}
        self.assertNotIn("RL-SPT-009", _ids(run_special_redline_detection(data)))

    def test_cit002_no_trigger_on_related_party_disclosure(self):
        """关联方 关系披露每家企业都有，≠资金拆借交易。"""
        data = {"vouchers": [{"摘要": "关联方关系披露", "科目": "其他应收款"}]}
        self.assertNotIn("RL-CIT-002", _ids(run_special_redline_detection(data)))

    def test_spt001_no_trigger_on_development_cost(self):
        """开发成本 建设单位都有，≠转让不动产（销售侧才计）。"""
        data = {"balances": [{"科目名称": "开发成本", "期末借方": 900000}]}
        self.assertNotIn("RL-SPT-001", _ids(run_special_redline_detection(data)))

    # ── 保留的具体风险信号：必须仍能触发 ──
    def test_fund004_trigger_on_zuozhi(self):
        data = {"vouchers": [{"摘要": "坐支现金收入", "金额": 8000}]}
        self.assertIn("RL-FUND-004", _ids(run_special_redline_detection(data)))

    def test_inv003_trigger_on_bom(self):
        data = {"vouchers": [{"摘要": "BOM 单位产品耗用异常", "金额": 1}]}
        self.assertIn("RL-INV-003", _ids(run_special_redline_detection(data)))

    def test_ast002_trigger_on_gov_grant(self):
        data = {"vouchers": [{"摘要": "收到政府补助", "科目": "递延收益"}]}
        self.assertIn("RL-AST-002", _ids(run_special_redline_detection(data)))

    def test_spt004_trigger_on_discharge(self):
        data = {"vouchers": [{"摘要": "排污许可证 直接排放", "金额": 1}]}
        self.assertIn("RL-SPT-004", _ids(run_special_redline_detection(data)))

    def test_spt009_trigger_on_equity_transfer(self):
        data = {"vouchers": [{"摘要": "股权转让协议签订", "金额": 1}]}
        self.assertIn("RL-SPT-009", _ids(run_special_redline_detection(data)))

    def test_cit002_trigger_on_fund_lending(self):
        data = {"vouchers": [{"摘要": "关联方资金拆借 未计息", "金额": 1}]}
        self.assertIn("RL-CIT-002", _ids(run_special_redline_detection(data)))

    def test_spt001_trigger_on_real_estate_sale(self):
        data = {"sal_invs": [{"品名": "不动产销售 房地产开发产品", "金额": 1}]}
        self.assertIn("RL-SPT-001", _ids(run_special_redline_detection(data)))


class GapRiskSignalAlignmentTests(unittest.TestCase):
    def test_cit006_no_trigger_on_donation_only(self):
        """营业外支出 含捐赠/罚款，≠资产损失。仅营业外支出不得触发。"""
        data = {"vouchers": [{"摘要": "捐赠支出", "科目": "营业外支出", "金额": 100}]}
        self.assertEqual(detect_asset_loss(data), [])

    def test_cit006_trigger_on_fixed_asset_disposal(self):
        data = {"vouchers": [{"摘要": "固定资产清理 盘亏", "科目": "固定资产清理", "金额": 100}]}
        self.assertTrue(detect_asset_loss(data))

    def test_oth005_no_trigger_on_office_repair(self):
        """维修费 办公/房屋维修都有，≠车辆。仅维修费不得触发。"""
        data = {"bank_txs": [{"摘要": "办公室维修费", "金额": 200}]}
        self.assertEqual(detect_vehicle_tax(data), [])

    def test_oth005_trigger_on_vehicle(self):
        data = {"bank_txs": [{"摘要": "车辆保险 交强险", "金额": 3000}]}
        self.assertTrue(detect_vehicle_tax(data))


class ObligationSignalAlignmentTests(unittest.TestCase):
    def test_culture_fee_no_trigger_on_advertiser(self):
        """广告费（广告主侧，付广告费）≠广告服务方，不得误报。"""
        data = {"vouchers": [{"摘要": "支付广告费", "科目": "销售费用"}]}
        hits = run_gap_tax_obligation_detection(data)
        self.assertFalse(any(f.get("_gap_obligation") == "文化事业建设费" for f in hits))

    def test_culture_fee_trigger_on_ad_service(self):
        data = {"sal_invs": [{"品名": "广告发布 广告服务", "金额": 50000}]}
        hits = run_gap_tax_obligation_detection(data)
        self.assertTrue(any(f.get("_gap_obligation") == "文化事业建设费" for f in hits))


if __name__ == "__main__":
    unittest.main()
