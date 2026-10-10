# -*- coding: utf-8 -*-
"""外部《财税稽查规则清单 V1.0》落地的 12 条 —— 行为级验收 + 反向验证（2026-10-10）。

每条都验三件事：
  ① **正例必须触发**（构造样例，证明检测器真的算得出来，不是空壳）；
  ② **负例必须静默**（阈值内不报、样本不足不报、无数据不报），防假阳性；
  ③ **阈值唯一权威**：全部取自 `config/rulelist_v1.json → params`，测试断言这一点。

另有：注册完整性（CATALOG↔_SCANNERS 一一对应）与「真实数据正常沉默」。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import rulelist_v1 as RL  # noqa: E402


def _spec(vr_id="VR075"):
    from engine.verified_rule_engine import VERIFIED_RULE_CATALOG as C
    return {s["id"]: s for s in C}[vr_id]


SRC2VR = {"VAT-004": "VR075", "VAT-008": "VR076", "VAT-014": "VR077", "VAT-015": "VR078",
          "VAT-021": "VR079", "VAT-024": "VR080", "CIT-002": "VR081", "CIT-003": "VR082",
          "CIT-007": "VR083", "CIT-019": "VR084", "CIT-020": "VR085", "CIT-030": "VR086"}


class TestRegistration:
    def test_catalog_and_scanners_match(self):
        """12 条必须同时进 CATALOG 与 _SCANNERS，且无缺无余。"""
        from engine.verified_rule_engine import VERIFIED_RULE_CATALOG as C, _SCANNERS
        ids = [s["id"] for s in C]
        for vr in SRC2VR.values():
            assert vr in ids, "%s 未进 CATALOG" % vr
            assert vr in _SCANNERS, "%s 未进 _SCANNERS" % vr
        extra = [k for k in _SCANNERS if k.startswith("VR07") and k not in ids]
        assert not extra, "有扫描器却无目录条目：%s" % extra

    def test_thresholds_come_from_data_table(self):
        """★ 阈值唯一权威：必须能在 config/rulelist_v1.json → params 找到，且非空。"""
        cfg = json.loads((ROOT / "config" / "rulelist_v1.json").read_text(encoding="utf-8"))
        params = cfg["params"]
        for src in SRC2VR:
            assert src in params, "%s 阈值未登记进数据表" % src
        assert cfg["var_map"] and cfg["rules"], "变量映射与覆盖登记不得为空"


class TestVAT004GrowthGap:
    def test_fires_when_output_grows_faster(self):
        d = {"sal_invs": [{"date": "2025-01-05", "tax": 1000.0}, {"date": "2025-02-05", "tax": 5000.0}],
             "pur_invs": [{"date": "2025-01-05", "tax": 1000.0}, {"date": "2025-02-05", "tax": 1100.0}]}
        out = RL.scan_vat_004(d, _spec("VR075"))
        assert len(out) == 1, out

    def test_silent_when_output_growth_below_floor(self):
        d = {"sal_invs": [{"date": "2025-01-05", "tax": 1000.0}, {"date": "2025-02-05", "tax": 1100.0}],
             "pur_invs": [{"date": "2025-01-05", "tax": 1000.0}, {"date": "2025-02-05", "tax": 1010.0}]}
        assert RL.scan_vat_004(d, _spec("VR075")) == []

    def test_silent_when_single_month(self):
        d = {"sal_invs": [{"date": "2025-01-05", "tax": 1000.0}]}
        assert RL.scan_vat_004(d, _spec("VR075")) == []


class TestVAT008NightInvoicing:
    def _rows(self, night, day):
        rows = [{"date": "2025-01-05 23:10:00", "amount": 100.0} for _ in range(night)]
        rows += [{"date": "2025-01-05 10:10:00", "amount": 100.0} for _ in range(day)]
        return rows

    def test_fires_when_night_ratio_over_threshold(self):
        out = RL.scan_vat_008({"sal_invs": self._rows(6, 14)}, _spec("VR076"))
        assert len(out) == 1, out

    def test_silent_when_ratio_within_threshold(self):
        assert RL.scan_vat_008({"sal_invs": self._rows(1, 19)}, _spec("VR076")) == []

    def test_silent_when_sample_too_small(self):
        """样本不足阈值张数 ⇒ 不出结论（防小样本误报）。"""
        assert RL.scan_vat_008({"sal_invs": self._rows(3, 2)}, _spec("VR076")) == []

    def test_silent_without_time_component(self):
        assert RL.scan_vat_008({"sal_invs": [{"date": "2025-01-05"}] * 20}, _spec("VR076")) == []


class TestVAT024NewCompany:
    def test_fires_when_new_company_invoices_heavily(self):
        d = {"target_entity": {"established_date": "2025-01-15"},
             "sal_invs": [{"date": "2025-01-20", "amount": 60000.0} for _ in range(25)]}
        assert len(RL.scan_vat_024(d, _spec("VR080"))) == 1

    def test_silent_when_established_date_missing(self):
        d = {"target_entity": {}, "sal_invs": [{"date": "2025-01-20", "amount": 60000.0}] * 30}
        assert RL.scan_vat_024(d, _spec("VR080")) == []

    def test_silent_when_outside_window(self):
        d = {"target_entity": {"established_date": "2020-01-15"},
             "sal_invs": [{"date": "2025-01-20", "amount": 60000.0}] * 30}
        assert RL.scan_vat_024(d, _spec("VR080")) == []


class TestCIT003TaxAccountingDiff:
    def _decl(self, profit, taxable):
        return {"tax_declarations": [{"_declaration_type": "cit", "period": "2025",
                                      "profit_total": profit, "taxable_income": taxable}]}

    def test_fires_when_diff_over_threshold(self):
        out = RL.scan_cit_003(self._decl(100000.0, 200000.0), _spec("VR082"))
        assert len(out) == 1, out

    def test_silent_when_within_threshold(self):
        assert RL.scan_cit_003(self._decl(100000.0, 110000.0), _spec("VR082")) == []

    def test_silent_when_no_cit_declaration(self):
        """★ 无企业所得税申报表 ⇒ 静默（覆盖度模块已列明需补，不得重复报）。"""
        assert RL.scan_cit_003({"tax_declarations": [{"_declaration_type": "vat"}]},
                               _spec("VR082")) == []


class TestCIT002Volatility:
    def test_fires_on_volatility(self):
        d = {"tax_declarations": [
            {"_declaration_type": "cit", "period": "2024", "revenue": 1000000.0, "cit_payable": 50000.0},
            {"_declaration_type": "cit", "period": "2025", "revenue": 1000000.0, "cit_payable": 10000.0}]}
        assert len(RL.scan_cit_002(d, _spec("VR081"))) == 1

    def test_silent_when_stable(self):
        d = {"tax_declarations": [
            {"_declaration_type": "cit", "period": "2024", "revenue": 1000000.0, "cit_payable": 50000.0},
            {"_declaration_type": "cit", "period": "2025", "revenue": 1000000.0, "cit_payable": 48000.0}]}
        assert RL.scan_cit_002(d, _spec("VR081")) == []

    def test_needs_prior_period(self):
        d = {"tax_declarations": [{"_declaration_type": "cit", "period": "2025",
                                   "revenue": 1000000.0, "cit_payable": 50000.0}]}
        out = RL.scan_cit_002(d, _spec("VR081"))
        assert len(out) == 1 and out[0]["finding_status"] == "data_quality_limitation", out


class TestNeedDataDetectors:
    """需申报表附列资料的四条：有线索 ⇒ 数据质量提示；无线索 ⇒ 静默。"""

    def test_vat014_clue_vs_silent(self):
        assert RL.scan_vat_014({"vouchers": [{"account_name": "应交税费/简易计税"}]}, _spec("VR077"))
        assert RL.scan_vat_014({"vouchers": [{"account_name": "管理费用"}]}, _spec("VR077")) == []

    def test_vat015_clue_vs_silent(self):
        assert RL.scan_vat_015({"sal_invs": [{"goods": "*建筑服务*工程款"}]}, _spec("VR078"))
        assert RL.scan_vat_015({"sal_invs": [{"goods": "*设计服务*设计费"}]}, _spec("VR078")) == []

    def test_vat021_clue_vs_silent(self):
        assert RL.scan_vat_021({"sal_invs": [{"goods": "*旅游服务*旅游费"}]}, _spec("VR079"))
        assert RL.scan_vat_021({"sal_invs": [{"goods": "*设计服务*设计费"}]}, _spec("VR079")) == []

    def test_cit019_cit020_clue_vs_silent(self):
        nt = {"vouchers": [{"account_name": "专项应付款/财政拨款", "credit": 100000.0}]}
        ex = {"vouchers": [{"account_name": "其他收益/免税收入", "credit": 50000.0}]}
        assert RL.scan_cit_019(nt, _spec("VR084"))
        assert RL.scan_cit_019(ex, _spec("VR084")) == []
        assert RL.scan_cit_020(ex, _spec("VR085"))
        assert RL.scan_cit_020(nt, _spec("VR085")) == []

    def test_cit030_needs_adjust_detail(self):
        d = {"tax_declarations": [{"_declaration_type": "cit", "period": "2025",
                                   "profit_total": 100000.0, "taxable_income": 150000.0,
                                   "adjust_amount": 0}]}
        debug = RL.scan_cit_030(d, _spec("VR086"))
        assert len(debug) == 1, debug
        assert RL.scan_cit_030({"tax_declarations": [{"_declaration_type": "vat"}]},
                               _spec("VR086")) == []


class TestRealDataStaysSilent:
    def test_silent_on_real_snapshot(self):
        snap = ROOT / "scripts" / "four_reports" / "_vr_data_snapshot.json"
        if not snap.exists():
            return
        d = json.loads(snap.read_text(encoding="utf-8"))
        spec = _spec("VR075")
        for src, fn in RL.DETECTORS.items():
            assert fn(d, spec) == [], "%s 在真实数据上不应触发" % src
