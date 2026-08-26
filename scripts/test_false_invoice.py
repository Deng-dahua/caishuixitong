"""虚开风险网络 引擎单测（直接构造数据，含合成 cross_enterprise）。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.false_invoice import run_false_invoice_check

SAL = [
    {"buyer": "东莞市大买家纺织有限公司", "amount": 900000.0, "tax": 117000.0, "invoice_no": "S1"},
    {"buyer": "深圳市小客户实业有限公司", "amount": 100000.0, "tax": 13000.0, "invoice_no": "S2"},
    {"buyer": "东莞市大买家纺织有限公司", "amount": 200000.0, "tax": 26000.0, "invoice_no": "S3"},
]
PUR = [
    {"seller": "佛山市顺德区宏丰贸易有限公司", "amount": 150000.0, "tax": 19500.0},
]
BANK = [
    {"counterparty": "东莞市大买家纺织有限公司", "credit": 0.0, "debit": 1100000.0},  # 付给客户
    {"counterparty": "东莞市大买家纺织有限公司", "credit": 1100000.0, "debit": 0.0},  # 客户回款 → 闭环
]
CE = {
    "total_relationships": 2, "high_risk_relationships": 1,
    "relationships": [
        {"company_a": "测试虚开风险企业", "company_b": "东莞市大买家纺织有限公司", "type": "same_legal_rep", "entities": ["范善茂"], "risk_level": "high"},
        {"company_a": "测试虚开风险企业", "company_b": "中山市冠茂建材有限公司", "type": "shared_supplier", "entities": ["棉纱"], "risk_level": "medium"},
    ],
    "companies": [{"id": 1, "name": "测试虚开风险企业"}, {"id": 2, "name": "东莞市大买家纺织有限公司"}],
}


def test_no_data():
    r = run_false_invoice_check(sal_invs=[], pur_invs=[])
    assert r["available"] is False
    print("[OK] 无数据占位正常")


def test_full_signals():
    r = run_false_invoice_check(sal_invs=SAL, pur_invs=PUR, cross_enterprise=CE, bank_txs=BANK)
    assert r["available"] is True
    m = r["metrics"]
    # 集中顶额：大买家 1100000 / 销总 1200000 = 0.917
    assert m["top3_customer_share"] > 0.8, m["top3_customer_share"]
    # 客户=自循环（大买家既是客户，也是关联/供应商？此处仅客户，但 CE 中为高风险的客户）
    # 资金回流：大买家既收又付 1100000 → 闭环 1100000
    assert m["fund_loop_amount"] == 1100000.0, m["fund_loop_amount"]
    # 高风险关联 1
    assert m["high_risk_relationships"] == 1
    # 应触发 high
    assert "虚开" in r["verdict"] and ("重点核查" in r["verdict"] or "高" in r["verdict"]), r["verdict"]
    sigs = " ".join(s["signal"] for s in r["signals"])
    assert "集中顶额开票" in sigs
    assert "资金回流闭环" in sigs
    assert "高风险关联" in sigs
    print("[OK] 虚开特征组合正确：前3客户=%.2f%% 资金回流=%.2f 高风险关联=%d" % (
        m["top3_customer_share"]*100, m["fund_loop_amount"], m["high_risk_relationships"]))


def test_circular_supplier():
    sal = [{"buyer": "中山市冠茂建材有限公司", "amount": 300000.0}]
    pur = [{"seller": "中山市冠茂建材有限公司", "amount": 80000.0, "tax": 10400.0}]
    r = run_false_invoice_check(sal_invs=sal, pur_invs=pur)
    assert r["metrics"]["circular_supplier_count"] == 1
    assert any("供应商=客户" in s["signal"] for s in r["signals"])
    print("[OK] 供应商=客户自循环识别正确")


if __name__ == "__main__":
    test_no_data()
    test_full_signals()
    test_circular_supplier()
    print("\n[OK] false_invoice 全部断言通过")
