"""资金流比对引擎单元测试（无外部依赖，可直接用 .venv 运行）。

构造与 pipeline 标准化后一致的 bank_txs（credit/debit 为 float），
验证 run_bank_flow_compare 能正确量化未开票敞口、私户收款与资金回流。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.bank_flow import run_bank_flow_compare


# ── 模拟 pipeline 标准化后的银行流水（含一笔私户、一笔未开票对公、一笔第三方）──
bank_txs = [
    {"date": "2026-01-05", "counterparty": "中山市冠茂建材有限公司", "summary": "货款", "credit": 60000.0, "debit": 0.0, "direction": "收入"},
    {"date": "2026-01-12", "counterparty": "佛山市顺德区宏丰贸易有限公司", "summary": "材料款", "credit": 200000.0, "debit": 0.0, "direction": "收入"},
    {"date": "2026-02-03", "counterparty": "张伟", "summary": "货款", "credit": 500000.0, "debit": 0.0, "direction": "收入"},
    {"date": "2026-02-18", "counterparty": "支付宝（中国）网络技术有限公司", "summary": "扫码收款", "credit": 80000.0, "debit": 0.0, "direction": "收入"},
    {"date": "2026-03-09", "counterparty": "李娜", "summary": "货款", "credit": 150000.0, "debit": 0.0, "direction": "收入"},
    {"date": "2026-03-20", "counterparty": "国家税务总局中山市税务局", "summary": "扣税", "credit": 0.0, "debit": 80000.0, "direction": "支出"},
    {"date": "2026-04-11", "counterparty": "中山市冠茂建材有限公司", "summary": "退货款", "credit": 0.0, "debit": 120000.0, "direction": "支出"},
]

sal_invs = [
    {"buyer": "中山市冠茂建材有限公司", "amount": 300000.0},
]

# 增值税申报表销售额（申报侧，优先）
reported_income = 400000.0

cross_enterprise = {"relationships": [
    {"counterparty": "佛山市顺德区宏丰贸易有限公司"},  # 关联方：企业收20万、付0 → 不闭环
]}


def main():
    res = run_bank_flow_compare(
        bank_txs, sal_invs=sal_invs, reported_income=reported_income,
        cross_enterprise=cross_enterprise, company_name="测试企业",
    )
    print("=== available:", res["available"])
    print("=== verdict:", res["verdict"])
    print("=== summary:", res["summary"])
    m = res["metrics"]
    for k in ("flow_receipt", "declared_value", "declared_side", "uninvoiced_gap",
              "corporate_receipt", "personal_receipt", "third_party_receipt", "circular_amount"):
        print(f"    {k}: {m.get(k)}")
    print("=== signals:")
    for s in res["signals"]:
        print("   -", s["signal"])
    print("=== body:\n" + res["body"])

    # 断言
    assert res["available"] is True
    assert m["flow_receipt"] == 990000.0, m["flow_receipt"]   # 60k+200k+500k+80k+150k
    assert m["personal_receipt"] == 650000.0, m["personal_receipt"]  # 张伟50万 + 李娜15万
    assert m["uninvoiced_gap"] == 590000.0, m["uninvoiced_gap"]  # 990k - 400k
    assert "严重背离" in res["verdict"] or "异常" in res["verdict"]
    print("\n[OK] 全部断言通过")


if __name__ == "__main__":
    main()
