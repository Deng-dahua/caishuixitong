# -*- coding: utf-8 -*-
"""为「仅兜底」红线建真检测器（A 轨道，2026-10-10）—— 行为级验收 + 反向验证。

覆盖 6 条：
  RL-INV-004 异常增值税扣税凭证抵扣      engine/gap_risk_detectors.detect_abnormal_input_voucher
  RL-PAY-003 虚列人员（无真实用工痕迹）  engine/gap_risk_detectors.detect_ghost_employees
  RL-CIT-009 关联方借款利率超同期同类     engine/gap_risk_detectors.detect_related_party_interest_rate
  RL-SPT-011 不符合核定征收条件而适用核定 engine/gap_risk_detectors.detect_deemed_collection
  RL-SPT-008 出口退税四单交叉            engine/export_rebate_crosscheck.run_export_rebate_crosscheck
  RL-SPT-013 个人报酬未代扣个税          engine/verified_rule_engine._scan_personal_service_withholding（VR065）

★ 每条都同时验「正例触发」与「负例不报」，并对**真实企业数据**断言正常沉默
  （本账套无这些场景 ⇒ 零输出是正确结果；防止「为了覆盖率而空转/误报」）。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ══════════════════════════════════════════════════════════════════
# RL-INV-004 异常增值税扣税凭证抵扣
# ══════════════════════════════════════════════════════════════════
class TestAbnormalInputVoucher:
    def _fn(self):
        from engine.gap_risk_detectors import detect_abnormal_input_voucher
        return detect_abnormal_input_voucher

    def test_fires_when_abnormal_and_not_reversed(self):
        data = {"pur_invs": [
            {"seller": "某空壳公司", "inv_no": "X1", "goods": "*货物*钢材",
             "tax": 13000.0, "inv_status": "异常-走逃失联", "risk_level": "异常"},
        ], "vouchers": []}
        out = self._fn()(data)
        assert len(out) == 1, out
        assert out[0]["redline_id"] == "RL-INV-004"
        assert out[0]["_scenario_governed"] is True

    def test_silent_when_fully_reversed(self):
        """已足额作进项税额转出 ⇒ 属正当情形（要件⑤），不得报。"""
        data = {"pur_invs": [
            {"seller": "A", "inv_no": "X1", "tax": 13000.0, "inv_status": "异常-走逃失联"},
        ], "vouchers": [
            {"account_name": "应交税费/应交增值税/进项税额转出", "credit": 13000.0},
        ]}
        assert self._fn()(data) == []

    def test_silent_when_status_normal(self):
        data = {"pur_invs": [{"seller": "A", "tax": 100.0, "inv_status": "正常", "risk_level": "正常"}]}
        assert self._fn()(data) == []

    def test_silent_without_invoices(self):
        assert self._fn()({"pur_invs": []}) == []


# ══════════════════════════════════════════════════════════════════
# RL-PAY-003 虚列人员
# ══════════════════════════════════════════════════════════════════
class TestGhostEmployees:
    def _fn(self):
        from engine.gap_risk_detectors import detect_ghost_employees
        return detect_ghost_employees

    def test_fires_for_payroll_without_social_and_without_bank(self):
        """真工资表（无累计预扣法列）：张三 无社保、无代发 ⇒ 触发。"""
        data = {
            "salaries": [{"name": "张三", "应发工资": 8000.0},
                         {"name": "李四", "应发工资": 9000.0},
                         {"name": "王五", "应发工资": 7000.0}],
            "social_security": [{"name": "李四"}],
            "bank_txs": [{"counterparty": "王五", "debit": 7000.0}],
        }
        out = self._fn()(data)
        assert len(out) == 1, out
        assert out[0]["redline_id"] == "RL-PAY-003"
        assert "张三" in out[0]["detail"]

    def test_silent_when_payroll_is_iit_declaration(self):
        """★ 工资表本身即个税扣缴申报明细（含累计列）⇒ 人人已有个税痕迹 ⇒ 不得判虚列。

        这防止把『未参保』（VR005 的主题）重复报成『虚列人员』（跨疑点重复）。
        """
        data = {
            "salaries": [{"name": "杨莹", "income_type": "正常工资薪金",
                          "acc_income": "8500.0", "acc_taxable": "3500.0", "salary": 8500.0}],
            "social_security": [], "bank_txs": [],
        }
        assert self._fn()(data) == []

    def test_silent_when_any_trace_exists(self):
        data = {"salaries": [{"name": "张三"}, {"name": "李四"}, {"name": "王五"}],
                "social_security": [{"name": "张三"}, {"name": "李四"}, {"name": "王五"}],
                "bank_txs": []}
        assert self._fn()(data) == []


# ══════════════════════════════════════════════════════════════════
# RL-CIT-009 关联方借款利率超金融企业同期同类贷款利率
# ══════════════════════════════════════════════════════════════════
class TestRelatedPartyInterestRate:
    def _fn(self):
        from engine.gap_risk_detectors import detect_related_party_interest_rate
        return detect_related_party_interest_rate

    def _case(self, interest_total, period="2025-10"):
        return {
            "balances": [{"name": "长期借款", "close_credit": 1000000.0}],
            "vouchers": [{"account_name": "财务费用/利息支出", "debit": interest_total / 12.0,
                          "month_no": str(i)} for i in range(1, 13)],
            "tax_declarations": [{"period": period}],
        }

    def test_fires_when_rate_over_lpr(self):
        """本金 100 万、年利息 8 万 ⇒ 年化 8% > 2025-10 的 1 年期 LPR 3.00% ⇒ 触发。"""
        out = self._fn()(self._case(80000.0))
        assert len(out) == 1, out
        assert out[0]["redline_id"] == "RL-CIT-009"
        assert "超过" in out[0]["type"]

    def test_silent_when_rate_within_lpr(self):
        """年化 2% ⇒ 未超 3.00% ⇒ 不报（防假阳性）。"""
        assert self._fn()(self._case(20000.0)) == []

    def test_pending_when_benchmark_not_registered(self):
        """基准未登记期间（2022-06，早于 LPR 序列起点）⇒ 只出待核，不得用默认值顶替。"""
        out = self._fn()(self._case(80000.0, period="2022-06"))
        assert len(out) == 1 and out[0]["_unconfirmed"] is True, out
        assert "基准" in out[0]["type"]

    def test_silent_without_any_loan(self):
        assert self._fn()({"balances": [], "vouchers": []}) == []

    def test_pending_when_only_principal(self):
        """有借款无利息 ⇒ 只出待核（缺一侧数据），不得默认利率。"""
        out = self._fn()({"balances": [{"name": "短期借款", "close_credit": 500000.0}]})
        assert len(out) == 1 and out[0]["_unconfirmed"] is True


# ══════════════════════════════════════════════════════════════════
# RL-SPT-011 不符合核定征收条件而适用核定征收
# ══════════════════════════════════════════════════════════════════
class TestDeemedCollection:
    def _fn(self):
        from engine.gap_risk_detectors import detect_deemed_collection
        return detect_deemed_collection

    def test_fires_on_deemed_collection_signal(self):
        data = {"tax_declarations": [{"period": "2025-10", "征收方式": "核定征收", "应税所得率": 0.1}]}
        out = self._fn()(data)
        assert len(out) == 1 and out[0]["redline_id"] == "RL-SPT-011"

    def test_silent_without_signal(self):
        data = {"tax_declarations": [{"period": "2025-10", "_declaration_type": "vat"}]}
        assert self._fn()(data) == []


# ══════════════════════════════════════════════════════════════════
# RL-SPT-008 出口退税四单交叉（已有实现补归属）
# ══════════════════════════════════════════════════════════════════
class TestExportRebateCrosscheck:
    def _run(self, data):
        from engine.export_rebate_crosscheck import run_export_rebate_crosscheck
        return run_export_rebate_crosscheck(data)

    def test_declares_redline_and_constituents(self):
        data = {
            "sal_invs": [{"goods": "出口货物A", "amount": 1000000.0, "total": 1000000.0}],
            "declarations": [{"declared_value": 800000.0}],          # 报关单 800,000
            "bank_txs": [{"摘要": "境外收汇", "amount": 700000.0}],   # 收汇 700,000
            "vouchers": [{"account_name": "原材料", "借方": 100000.0}],  # 产能 100,000（口径键：借方）
        }
        out = self._run(data)
        assert out, "应产出出口退税待核线索"
        for f in out:
            assert f.get("redline_id") == "RL-SPT-008", f
        idx = sorted({h["index"] for f in out for h in (f.get("constituent_hits") or [])})
        assert idx == [2, 3, 4, 5], idx

    def test_missing_docs_finding_claims_no_constituent(self):
        """缺报关单/收汇 ⇒ 属资料缺口，带归属但**不认领任何要件**。"""
        data = {
            "sal_invs": [{"goods": "出口货物A", "amount": 500000.0, "total": 500000.0}],
            "declarations": [], "bank_txs": [], "vouchers": [],
        }
        out = self._run(data)
        assert len(out) == 1, out
        assert out[0]["redline_id"] == "RL-SPT-008"
        assert not out[0].get("constituent_hits"), out[0]

    def test_silent_without_export_business(self):
        assert self._run({"sal_invs": [{"goods": "设计服务", "amount": 100.0}]}) == []


# ══════════════════════════════════════════════════════════════════
# RL-SPT-013 个人报酬未代扣个税（VR065 补归属）
# ══════════════════════════════════════════════════════════════════
class TestPersonalServiceWithholding:
    def _scan(self, bank):
        from engine.verified_rule_engine import _SCANNERS, VERIFIED_RULE_CATALOG
        spec = {s["id"]: s for s in VERIFIED_RULE_CATALOG}["VR065"]
        return _SCANNERS["VR065"]({"bank_txs": bank}, spec)

    def test_declares_spt013_and_claims_constituent_1(self):
        bank = [{"counterparty": "张三", "summary": "支付劳务费", "debit": 60000.0,
                 "date": "2025-03-01"}]
        out = self._scan(bank)
        assert len(out) == 1, out
        assert out[0]["redline_id"] == "RL-SPT-013"
        assert [h["index"] for h in out[0]["constituent_hits"]] == [1]

    def test_silent_below_threshold(self):
        bank = [{"counterparty": "张三", "summary": "支付劳务费", "debit": 1000.0}]
        assert self._scan(bank) == []


# ══════════════════════════════════════════════════════════════════
# 真实企业数据：本账套无以上场景 ⇒ 必须**正常沉默**（零输出）
# ══════════════════════════════════════════════════════════════════
class TestRealDataStaysSilent:
    def _load(self):
        # 真实数据快照由只读探针 `_probe_vr_data.py` 落盘到 `scripts/four_reports/`（gitignore）
        snap = ROOT / "scripts" / "four_reports" / "_vr_data_snapshot.json"
        if not snap.exists():
            return None
        return json.loads(snap.read_text(encoding="utf-8"))

    def test_silent_on_real_company_data(self):
        d = self._load()
        if d is None:
            return                       # 快照未落盘（非生产依赖）⇒ 不误判
        data = {
            "bank_txs": d.get("bank_txs"), "sal_invs": d.get("sal_invs"),
            "pur_invs": d.get("pur_invs"), "vouchers": d.get("vouchers"),
            "salaries": d.get("salaries"), "tax_declarations": d.get("tax_declarations"),
            "balances": d.get("trial_balance"), "social_security": d.get("social_security"),
            "company_profile": d.get("company_profile"), "target_entity": d.get("target_entity"),
        }
        from engine import gap_risk_detectors as g
        assert g.detect_abnormal_input_voucher(data) == []
        assert g.detect_ghost_employees(data) == []
        assert g.detect_related_party_interest_rate(data) == []
        assert g.detect_deemed_collection(data) == []


# ══════════════════════════════════════════════════════════════════
# 覆盖率口径：本轮 6 个目标红线必须都已是「有真检测器」，且不再有「仅兜底」
# ══════════════════════════════════════════════════════════════════
class TestCoverageNowComplete:
    TARGETS = ["RL-CIT-009", "RL-INV-004", "RL-PAY-003", "RL-SPT-008", "RL-SPT-011", "RL-SPT-013"]

    def _cov(self):
        p = ROOT / "scripts" / "_redline_coverage.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def test_targets_have_real_detectors(self):
        cov = self._cov()
        if cov is None:
            return                       # 覆盖率产物缺失 ⇒ 另由审计脚本报（此处不误判）
        has = set(cov["has_detector"])
        for rid in self.TARGETS:
            assert rid in has, "%s 仍无真检测器" % rid
            assert rid not in (cov.get("only_fallback") or []), "%s 仍被记为仅兜底" % rid
            assert rid not in (cov.get("blind") or []), "%s 被记为盲区" % rid
