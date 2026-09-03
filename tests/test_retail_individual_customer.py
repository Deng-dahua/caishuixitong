# -*- coding: utf-8 -*-
"""回归测试：零售/B2C 企业（如宠物用品店）面向个人消费者的销售不得被判为税务风险。

背景
----
猩猩织光（北京）商贸有限公司为宠物用品零售企业（经营范围含"宠物食品及用品零售"，
销项经天猫/阿里妈妈等电商平台成交，客户高度分散、票均与户均均为消费级）。
此前的 VR024「个人或个体工商户供应商客户交易核验」见个人主体即报风险，
把"107家个人客户、合计41,705元、户均390元"的正常零售误判为疑点。

本测试锁定修复后的行为：经营模式识别须判定 retail_b2c，VR024 销售侧须判非风险。
"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import business_model as bm
from engine.verified_rule_engine import _scan_individual_counterparty

VR024_SPEC = {
    "id": "VR024",
    "name": "个人或个体工商户供应商客户交易核验",
    "layer": "交易关系交叉规则",
    "industries": ["ALL"],
    "taxes": ["增值税", "企业所得税", "个人所得税"],
    "lifecycle": ["采购与取得", "销售与收入确认"],
    "required_sources": ["sal_invs", "pur_invs"],
    "status": "verified_executable_screening",
    "limitation": "销售侧须先作经营模式裁决：零售/电商企业面向不特定个人消费者的销售属正常经营模式，不列为风险。",
}


def _build_data(rows, scope="一般项目：宠物食品及用品零售；日用百货销售"):
    sal_invs = []
    for r in rows:
        sal_invs.append({"buyer": r[0], "amount": r[1], "goods": r[2]})
    return {
        "sal_invs": sal_invs,
        "pur_invs": [],
        "target_entity": {
            "name": "猩猩织光（北京）商贸有限公司",
            "industry": "食品加工",
            "business_scope": scope,
        },
    }


def test_pet_retail_recognized_as_b2c():
    """宠物用品零售企业必须被识别为 B2C 零售（is_b2c_retail=True，score>=5）。"""
    # 天猫平台 + 大量分散个人客户 + 消费级票额
    rows = [("浙江天猫技术有限公司", 3000.0, "*宠物用品*猫粮")] + [
        ("张%d（个人）" % i, 380.0, "*宠物用品*猫粮") for i in range(107)
    ]
    data = _build_data(rows)
    res = bm.detect_business_model(data)
    assert res["is_b2c_retail"] is True, (
        "宠物用品零售企业应识别为 B2C，实际 model=%s score=%s" % (res["model"], res["score"])
    )
    assert res["score"] >= bm.RETAIL_SCORE_THRESHOLD, "score 应达到零售门槛"


def test_pet_retail_vr024_not_risk():
    """VR024 销售侧：零售模式下个人客户不得列为风险（score=0 / normal_business_pattern）。"""
    rows = [("浙江天猫技术有限公司", 3000.0, "*宠物用品*猫粮")] + [
        ("张%d（个人）" % i, 380.0, "*宠物用品*猫粮") for i in range(107)
    ]
    data = _build_data(rows)
    findings = _scan_individual_counterparty(data, VR024_SPEC)
    # 销售侧必须有一条"非风险"结论
    non_risk = [f for f in findings if f.get("status") == "normal_business_pattern" or (f.get("score") == 0)]
    assert non_risk, "零售企业个人客户应判非风险，实际 findings=%s" % [f.get("detail") for f in findings]
    assert any("不列为税务风险" in (f.get("detail") or "") for f in findings), "结论应明确'不列为税务风险'"


def test_b2b_with_individual_customers_still_flagged():
    """对照组：制造业/批发等非零售企业出现大量个人客户，仍应作为风险/待澄清暴露。"""
    # 经营范围是制造，无平台、客户集中为大额、票额高
    rows = [("李伟（个人）", 520000.0, "*金属制品*加工费") for _ in range(3)]
    data = _build_data(rows, scope="金属制品制造；机械加工")
    res = bm.detect_business_model(data)
    assert res["is_b2c_retail"] is False, "制造企业不应判为零售"
    findings = _scan_individual_counterparty(data, VR024_SPEC)
    assert findings, "非零售企业个人客户应被暴露"
    assert not any("不列为税务风险" in (f.get("detail") or "") for f in findings), "非零售不应判非风险"


if __name__ == "__main__":
    test_pet_retail_recognized_as_b2c()
    test_pet_retail_vr024_not_risk()
    test_b2b_with_individual_customers_still_flagged()
    print("[OK] 零售门店个人客户识别测试全部通过")
