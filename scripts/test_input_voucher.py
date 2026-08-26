"""进项异常凭证 引擎单测（直接构造 pur_invs，不依赖 HTTP）。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.input_voucher import run_input_voucher_check

PUR = [
    {"seller": "中山市冠茂建材有限公司", "seller_tax": "91442000MA55GUANM",
     "goods": "职工福利用品", "amount": 850000.0, "tax": 110500.0, "invoice_no": "A1", "date": "2026-03-05"},
    {"seller": "佛山市顺德区宏丰贸易有限公司", "seller_tax": "91442000MA55HONGF",
     "goods": "棉纱", "amount": 150000.0, "tax": 19500.0, "invoice_no": "A2", "date": "2026-03-12"},
    {"seller": "中山市冠茂建材有限公司", "seller_tax": "91442000MA55GUANM",
     "goods": "五金配件", "amount": 50000.0, "tax": 6500.0, "invoice_no": "A3", "date": "2026-04-02"},
]


def test_no_data():
    r = run_input_voucher_check(pur_invs=[])
    assert r["available"] is False
    assert "未提供进项发票" in r["verdict"]
    print("[OK] 无数据占位正常")


def test_concentration_and_non_deductible():
    r = run_input_voucher_check(pur_invs=PUR, company_name="测试企业")
    assert r["available"] is True
    m = r["metrics"]
    # 集中度：冠茂 900000 / 总 1050000 = 0.857
    assert m["concentration_ratio"] > 0.85, m["concentration_ratio"]
    # 福利用品应转出：110500
    assert m["should_transfer_out_tax"] == 110500.0, m["should_transfer_out_tax"]
    # 集中度信号 + 应转出信号
    sigs = [s["signal"] for s in r["signals"]]
    assert any("供应商高度集中" in s for s in sigs)
    assert any("应进项转出未转出" in s for s in sigs)
    print("[OK] 集中度与应转出识别正确 ratio=%.3f 转出=%.2f" % (m["concentration_ratio"], m["should_transfer_out_tax"]))


def test_abnormal_list():
    r = run_input_voucher_check(pur_invs=PUR, abnormal_list=["中山市冠茂建材有限公司"])
    m = r["metrics"]
    assert m["abnormal_deduction_tax"] == 117000.0, m["abnormal_deduction_tax"]  # 110500+6500
    assert m["abnormal_supplier_count"] == 1
    assert any("异常凭证供应商" in s["signal"] for s in r["signals"])
    print("[OK] 异常凭证清单命中 税额=%.2f" % m["abnormal_deduction_tax"])


def test_circular_supplier():
    sal = [{"buyer": "中山市冠茂建材有限公司", "amount": 300000.0}]
    r = run_input_voucher_check(pur_invs=PUR, sal_invs=sal)
    assert r["metrics"]["circular_supplier_count"] == 1
    assert any("供应商同时为客户" in s["signal"] for s in r["signals"])
    print("[OK] 供应商=客户自循环识别正确")


if __name__ == "__main__":
    test_no_data()
    test_concentration_and_non_deductible()
    test_abnormal_list()
    test_circular_supplier()
    print("\n[OK] input_voucher 全部断言通过")
