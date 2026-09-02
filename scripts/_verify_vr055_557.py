"""临验 VR055/056/057：用模拟 company 3 数据 + B2B 对照组验证规则逻辑。"""
import json
import sys
sys.path.insert(0, ".")
from engine import verified_rule_engine as V

CAT = {c["id"]: c for c in V.VERIFIED_RULE_CATALOG}


def build_company3():
    salaries = [
        {"name": "张帅", "salary": 7000.0, "net": 6062.14, "acc_paid": 0.0},
        {"name": "范雪", "salary": 7000.0, "net": 6062.14, "acc_paid": 0.0},
        {"name": "董师超", "salary": 7000.0, "net": 6062.14, "acc_paid": 0.0},
        {"name": "李宪洲", "salary": 7000.0, "net": 6062.14, "acc_paid": 0.0},
    ]
    social = [
        {"name": "张帅", "base": 7162.0},
        {"name": "范雪", "base": 7162.0},
        {"name": "董师超", "base": 7162.0},
        {"name": "李宪洲", "base": 7162.0},
    ]
    sal_invs = [
        {"buyer": "浙江天猫技术有限公司", "amount": 2852.81, "tax": 171.17, "total": 3023.98},
        {"buyer": "杭州阿里妈妈软件服务有限公司", "amount": 4998.8, "tax": 299.93, "total": 5298.73},
        {"buyer": "个人客户A", "amount": 389.0, "tax": 0, "total": 389.0},
    ]
    bank = [
        {"counterparty": "支付宝支付科技有限公司", "credit": 8000.0, "debit": 0.0, "summary": "提现"},
        {"counterparty": "支付宝支付科技有限公司", "credit": 5000.0, "debit": 0.0, "summary": "结算"},
    ]
    return {
        "salaries": salaries,
        "social_security": social,
        "sal_invs": sal_invs,
        "bank_txs": bank,
        "target_entity": {"name": "猩猩织光宠物用品有限公司"},
    }


def build_b2b():
    salaries = [
        {"name": "王经理", "salary": 18500.0, "net": 14020.0, "acc_paid": 1020.0},
        {"name": "李工", "salary": 12300.0, "net": 9520.0, "acc_paid": 430.0},
        {"name": "赵会计", "salary": 9800.0, "net": 7600.0, "acc_paid": 210.0},
        {"name": "钱销售", "salary": 8600.0, "net": 6700.0, "acc_paid": 90.0},
        {"name": "孙采购", "salary": 9100.0, "net": 7100.0, "acc_paid": 150.0},
    ]
    sal_invs = [
        {"buyer": "苏州某某制造有限公司", "amount": 120000.0, "tax": 15600.0, "total": 135600.0},
        {"buyer": "上海某某贸易有限公司", "amount": 85000.0, "tax": 11050.0, "total": 96050.0},
    ]
    bank = [
        {"counterparty": "苏州某某制造有限公司", "credit": 135600.0, "debit": 0.0, "summary": "货款"},
        {"counterparty": "工商银行代发工资", "credit": 0.0, "debit": 59300.0, "summary": "工资代发2026-01"},
    ]
    return {
        "salaries": salaries,
        "social_security": [],
        "sal_invs": sal_invs,
        "bank_txs": bank,
        "target_entity": {"name": "某精密制造有限公司"},
    }


def run_case(name, data):
    print("\n===== %s =====" % name)
    findings = V.run_verified_rules(data)["findings"]
    hits = [f for f in findings if f["rule_id"] in ("VR055", "VR056", "VR057")]
    print("命中 VR055/056/057 数:", len(hits))
    for f in hits:
        print("  -", f["rule_id"], "|", f["type"], "| level=", f["level"], "| score=", f["score"], "| priority=", f["priority"])
        print("    detail:", f["detail"][:240].replace("\n", " "))
        dd = (f.get("observed_metrics") or {}).get("demand_docs")
        if dd:
            print("    demand_docs:", dd[:2])
    return hits


if __name__ == "__main__":
    h1 = run_case("COMPANY_3 (猩猩织光: 均额7000+支付宝+天猫)", build_company3())
    h2 = run_case("B2B 制造对照 (差异化工资+对公代发+无平台)", build_b2b())
    assert h1, "company3 应触发三条规则"
    assert not any(f["rule_id"] == "VR055" for f in h2), "B2B 不应触发 VR055 均额"
    assert not any(f["rule_id"] == "VR057" for f in h2), "B2B 不应触发 VR057 平台盲区"
    print("\n断言通过：company3 触发、B2B 不误报。")
