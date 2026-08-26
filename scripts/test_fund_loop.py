"""跨企业资金回流闭环 引擎单测（直接构造银行流水 + 合成 cross_enterprise）。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.fund_loop import run_fund_loop_check

# 直接闭环：冠茂既收 60000 又付 120000 → 直接闭环 60000
BANK_DIRECT = [
    {"counterparty": "中山市冠茂建材有限公司", "credit": 60000.0, "debit": 0.0},
    {"counterparty": "中山市冠茂建材有限公司", "credit": 0.0, "debit": 120000.0},
    {"counterparty": "张伟", "credit": 500000.0, "debit": 0.0},  # 仅收，无闭环
]
# 三角闭环：企业付给 B，又从 C 收回；B、C 在跨企业图谱同组
BANK_TRI = [
    {"counterparty": "中山市冠茂建材有限公司", "credit": 0.0, "debit": 300000.0},   # 企业付B
    {"counterparty": "佛山市宏丰贸易有限公司", "credit": 280000.0, "debit": 0.0},  # 企业收C
]
CE_TRI = {
    "total_relationships": 1, "high_risk_relationships": 0,
    "relationships": [
        {"company_a": "中山市冠茂建材有限公司", "company_b": "佛山市宏丰贸易有限公司",
         "type": "same_legal_rep", "entities": ["范善茂"], "risk_level": "medium"},
    ],
    "companies": [{"id": 1, "name": "中山市冠茂建材有限公司"}, {"id": 2, "name": "佛山市宏丰贸易有限公司"}],
}


def test_no_data():
    r = run_fund_loop_check(bank_txs=[])
    assert r["available"] is False
    print("[OK] 无数据占位正常")


def test_direct_loop():
    r = run_fund_loop_check(bank_txs=BANK_DIRECT)
    assert r["available"] is True
    m = r["metrics"]
    assert m["direct_loop_amount"] == 60000.0, m["direct_loop_amount"]
    assert m["circular_amount"] == 60000.0
    assert "直接资金回流闭环" in " ".join(s["signal"] for s in r["signals"])
    print("[OK] 直接闭环正确 amount=%.2f" % m["direct_loop_amount"])


def test_triangular_loop():
    r = run_fund_loop_check(bank_txs=BANK_TRI, cross_enterprise=CE_TRI)
    m = r["metrics"]
    # 三角闭环 = min(付B 300000, 收C 280000) = 280000
    assert m["indirect_loop_amount"] == 280000.0, m["indirect_loop_amount"]
    assert m["circular_amount"] == 280000.0
    assert any("三角" in s["signal"] or "关联" in s["signal"] for s in r["signals"])
    print("[OK] 三角/关联闭环正确 amount=%.2f" % m["indirect_loop_amount"])


if __name__ == "__main__":
    test_no_data()
    test_direct_loop()
    test_triangular_loop()
    print("\n[OK] fund_loop 全部断言通过")
