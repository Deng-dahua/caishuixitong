# -*- coding: utf-8 -*-
"""回归测试：第三方支付通道（支付宝/财付通等）须被识别为资金通道，而非真实交易对手方。

背景
----
此前系统对「第三方收款占比过高」直接判高风险（domain_analysis._domain_bank_tracking，
score=9），未识别企业经营模式。对零售/电商(B2C)企业（如猩猩织光宠物用品电商，银行流水
大量「收销售款_支付宝支付科技有限公司」）而言，第三方支付通道归集回款占比高是正常结算
方式，与 VR024「零售个人客户误报」同源——属系统不识别经营模式导致的误报。

本测试锁定修复后的行为：
1. is_third_party_payment_channel 正确识别支付宝/财付通/微信支付等通道，且不误伤真实企业；
2. 零售 B2C 企业第三方收款占比高 → 判非风险（normal_business_pattern）；
3. 制造业/批发等非零售企业第三方收款占比高 → 仍判高风险，不得自动放过。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.business_model import detect_business_model, is_third_party_payment_channel
from engine.domain_analysis import _domain_bank_tracking
from engine.verified_rule_engine import _scan_thirdparty_blindspot, VERIFIED_RULE_CATALOG


def _vr057_spec():
    for c in VERIFIED_RULE_CATALOG:
        if c["id"] == "VR057":
            return c
    raise AssertionError("VR057 spec 缺失")


def _alipay_vouchers(n, amount=31150.94):
    """构造 n 组支付宝归集回款序时账（银行入账腿 debit>0 + 应收挂账腿 credit>0 同摘要）。"""
    vs = []
    for i in range(n):
        sm = "1月%d日收销售款_支付宝支付科技有限公司" % (i + 1)
        vs.append({"date": "2026-01-%02d" % (i + 1), "voucher_no": "记-%d" % (i + 1),
                   "summary": sm, "account": "1002001 银行存款", "debit": amount, "credit": 0.0})
        vs.append({"date": "", "voucher_no": "",
                   "summary": sm, "account": "1122001 应收账款_支付宝", "debit": 0.0, "credit": amount})
    return vs


def _build_bank(alipay_count, alipay_amount, other_credit=1000.0):
    bank = [{
        "date": "2026-01-0%d" % (i + 1),
        "counterparty": "支付宝支付科技有限公司",
        "raw": "收销售款_支付宝支付科技有限公司",
        "credit": alipay_amount,
        "debit": 0.0,
    } for i in range(alipay_count)]
    bank.append({
        "date": "2026-01-99", "counterparty": "某真实客户", "raw": "收款",
        "credit": other_credit, "debit": 0.0,
    })
    return bank


def test_is_third_party_payment_channel():
    """通道识别：支付宝/财付通/微信支付等 True，真实企业 False。"""
    assert is_third_party_payment_channel("支付宝支付科技有限公司") is True
    assert is_third_party_payment_channel("财付通支付科技有限公司") is True
    assert is_third_party_payment_channel("微信支付科技有限公司") is True
    assert is_third_party_payment_channel("通联支付网络服务股份有限公司") is True
    # 真实企业不得误判
    assert is_third_party_payment_channel("北京潘祥记餐饮有限公司") is False
    assert is_third_party_payment_channel("深圳海更数字传媒有限公司") is False


def test_retail_third_party_not_risk():
    """零售 B2C 企业第三方收款占比高 → 非风险（normal_business_pattern）。"""
    sal = [{"buyer": "浙江天猫技术有限公司", "amount": 3000.0, "goods": "*宠物用品*猫粮"}] + [
        {"buyer": "张%d（个人）" % i, "amount": 380.0, "goods": "*宠物用品*猫粮"} for i in range(20)
    ]
    bm = detect_business_model({
        "sal_invs": sal,
        "company_profile": {"name": "猩猩织光（北京）商贸有限公司", "business_scope": "宠物食品及用品零售"},
    })
    assert bm["is_b2c_retail"] is True
    bank = _build_bank(10, 31150.94)
    findings = _domain_bank_tracking(bank, bm)
    tp = [f for f in findings if f["type"] == "第三方收款占比过高"]
    assert tp, "应产出第三方收款占比过高发现"
    f = tp[0]
    assert f["level"] in ("低风险", "待核验"), "零售企业不应判高风险，实际=%s" % f["level"]
    assert f.get("score", 9) == 0, "零售企业 score 应为 0，实际=%s" % f.get("score")
    assert f.get("status") == "normal_business_pattern", "应标记 normal_business_pattern"
    assert "不列为税务风险" in (f.get("detail") or ""), "结论应明确不列为税务风险"


def test_manufacturing_third_party_still_flagged():
    """制造业第三方收款占比高 → 仍判高风险（不得因通道识别而漏报）。"""
    sal = [{"buyer": "李伟（个人）", "amount": 520000.0, "goods": "*金属制品*加工费"}]
    bm = detect_business_model({
        "sal_invs": sal,
        "company_profile": {"name": "某制造厂", "business_scope": "金属制品制造；机械加工"},
    })
    assert bm["is_b2c_retail"] is False
    bank = _build_bank(10, 30000.0, other_credit=1000.0)
    findings = _domain_bank_tracking(bank, bm)
    tp = [f for f in findings if f["type"] == "第三方收款占比过高"]
    assert tp, "应产出第三方收款占比过高发现"
    f = tp[0]
    assert f["level"] == "高风险", "制造业应维持高风险，实际=%s" % f["level"]
    assert f.get("score") == 9, "制造业 score 应为 9，实际=%s" % f.get("score")


def test_vr057_scans_vouchers_for_alipay():
    """VR057 须扫描序时账（vouchers）中的支付宝归集回款，不可漏计为『共0笔』。"""
    data = {
        "sal_invs": [{"buyer": "张%d（个人）" % i, "amount": 380.0} for i in range(5)],
        "vouchers": _alipay_vouchers(5),
        "target_entity": {"name": "猩猩织光（北京）商贸有限公司"},
    }
    findings = _scan_thirdparty_blindspot(data, _vr057_spec())
    assert findings, "VR057 应触发"
    f = findings[0]["observed_metrics"]
    # 仅统计银行入账腿（debit>0），应收挂账腿（credit>0）不重复计数
    assert f["third_party_collection_rows"] == 5, "应统计 5 笔，实际=%s" % f["third_party_collection_rows"]
    assert f["voucher_collection_rows"] == 5, "voucher_collection_rows 应为 5，实际=%s" % f["voucher_collection_rows"]
    assert abs(f["third_party_collection_amount"] - 5 * 31150.94) < 0.01


def test_vr057_hard_rule_and_wage_split_linkage():
    """未提供平台结算 + 工资『均额/拆分』模板 → 须打通『平台资金→私户另付工资→个税逃漏』。"""
    salaries = [{"name": n, "salary": 7000.0, "acc_paid": 0.0}
                for n in ("甲", "乙", "丙", "丁")]
    data = {
        "sal_invs": [{"buyer": "张1（个人）", "amount": 380.0}],
        "vouchers": _alipay_vouchers(1),
        "salaries": salaries,
        "target_entity": {"name": "猩猩织光（北京）商贸有限公司"},
    }
    findings = _scan_thirdparty_blindspot(data, _vr057_spec())
    assert findings, "VR057 应触发"
    f = findings[0]
    d = f["detail"]
    assert "硬规定" in d, "应体现『提交平台后台真实记录』的硬规定"
    assert "个税" in d and "私户" in d, "应打通平台资金→私户另付工资→个税逃漏链条"
    assert f["observed_metrics"]["wage_split_linkage"] is True
    dd = f["observed_metrics"]["demand_docs"]
    assert any("对私户" in x for x in dd), "应责令平台提现至对私户流水"
    assert any("个人所得税扣缴申报表" in x for x in dd), "应责令个税扣缴申报表核验账外补差"
    assert f["priority"] == "调查优先级"


def test_vr057_settlement_provided_no_hard_blindspot():
    """已提供平台结算资料 → 不触发『硬规定』盲区责令文案。"""
    data = {
        "sal_invs": [{"buyer": "张1（个人）", "amount": 380.0}],
        "vouchers": _alipay_vouchers(1),
        "platform_settlement": {"orders": 100},
        "target_entity": {"name": "猩猩织光（北京）商贸有限公司"},
    }
    findings = _scan_thirdparty_blindspot(data, _vr057_spec())
    assert findings, "VR057 应触发"
    f = findings[0]
    assert f["observed_metrics"]["settlement_provided"] is True
    assert "硬规定" not in f["detail"]


if __name__ == "__main__":
    test_is_third_party_payment_channel()
    test_retail_third_party_not_risk()
    test_manufacturing_third_party_still_flagged()
    test_vr057_scans_vouchers_for_alipay()
    test_vr057_hard_rule_and_wage_split_linkage()
    test_vr057_settlement_provided_no_hard_blindspot()
    print("[OK] 第三方支付通道识别与经营模式裁决 + VR057 强化测试全部通过")
