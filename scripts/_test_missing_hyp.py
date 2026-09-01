# -*- coding: utf-8 -*-
"""缺失型假设模板单元测试：不调用大模型，直接验证竞争假设裁决逻辑。

验证目标：
1) 风险型（类 C2：跨地区购销 + 零运输费 + 制造业无能耗/无场地/无车辆）
   → 缺失型模板被命中，风险假设胜出，但按设计转 unconfirmed（待证，抛置疑清单）。
2) 良性型（运输费/场地/能耗/车辆均在账面体现）
   → 正常假设胜出，风险降级（score 下降，标注“风险降级”）。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import hypothesis_engine as H


class _Ctx:
    def __init__(self, name="", biz_model=""):
        self.company_profile = {"name": name, "biz_model": biz_model}


def _make_ctx(name, biz_model):
    return _Ctx(name, biz_model)


# ── 风险型 fixture：北京企业，对手方分布在 广东/浙江/江苏（跨地区），无任何必要费用物证 ──
RISK_PUR = [
    {"goods": "钢材", "amount": 3000000, "buyer": "北京宏远制造有限公司", "seller": "深圳市某钢贸有限公司"},
    {"goods": "电子元件", "amount": 2000000, "buyer": "北京宏远制造有限公司", "seller": "杭州市某元件厂"},
    {"goods": "包装材料", "amount": 800000, "buyer": "北京宏远制造有限公司", "seller": "苏州市某包装公司"},
]
RISK_SAL = [
    {"goods": "机械设备", "amount": 8000000, "buyer": "广州市某机电公司", "seller": "北京宏远制造有限公司"},
]
RISK_FINDING = {
    "type": "零运输费+跨省购销-货物流断裂",
    "score": 9,
    "desc": "跨省购销却零运输费，货物流断裂",
}

# ── 良性型 fixture：同样跨地区，但运输费/场地/能耗/车辆/加工费均在账面体现 ──
BENIGN_PUR = list(RISK_PUR) + [
    {"goods": "运输费", "amount": 400000, "buyer": "北京宏远制造有限公司", "seller": "德邦物流有限公司"},
    {"goods": "加工费", "amount": 300000, "buyer": "北京宏远制造有限公司", "seller": "天津某加工厂"},
]
BENIGN_SAL = list(RISK_SAL)
# 银行流水体现场地租金与车辆费用、能耗
BENIGN_BANK = [
    {"credit": 0, "counterparty_name": "房东王先生", "summary": "支付厂房租金本月", "remark": "租金"},
    {"credit": 0, "counterparty_name": "国家电网", "summary": "电费缴纳", "remark": "用电"},
    {"credit": 0, "counterparty_name": "中石化", "summary": "加油费", "remark": "油费"},
]
BENIGN_FINDING = {
    "type": "零运输费+跨省购销-货物流断裂",
    "score": 9,
    "desc": "跨省购销却零运输费，货物流断裂",
}


def _run(finding, ctx, bank, pur, sal):
    tpl_key = H._match_template(finding["type"])
    assert tpl_key == "missing_element", f"模板未命中 missing_element，实际={tpl_key}"
    tpl = H.HYPOTHESIS_TEMPLATES[tpl_key]
    res = H._verify_hypothesis(finding, tpl, ctx, bank, None, sal, pur, None)
    assert res is not None, "假设验证返回空"
    return res


def main():
    print("=== 测试1：风险型（类C2 零运费+跨地区+制造业无要素）===")
    ctx = _make_ctx("北京宏远制造有限公司", "制造")
    res = _run(RISK_FINDING, ctx, [], RISK_PUR, RISK_SAL)
    print("  胜出假设:", res["hypothesis_selected"])
    print("  置信度:", res["confidence"])
    print("  推理:", res["reasoning"])
    print("  证据支持:", res["evidence_for"])
    assert res["selected"] == 1, "风险型应风险假设(索引1)胜出"
    assert res["confidence"] > 0.4, "风险假设后验应明显偏高"

    print("\n=== 测试2：良性型（必要费用均在账面体现）===")
    ctx2 = _make_ctx("北京宏远制造有限公司", "制造")
    res2 = _run(BENIGN_FINDING, ctx2, BENIGN_BANK, BENIGN_PUR, BENIGN_SAL)
    print("  胜出假设:", res2["hypothesis_selected"])
    print("  置信度:", res2["confidence"])
    print("  推理:", res2["reasoning"])
    print("  证据支持:", res2["evidence_for"])
    assert res2["selected"] == 0, "良性型应正常假设(索引0)胜出"
    assert res2["confidence"] > 0.4, "正常假设后验应明显偏高"

    print("\n=== 测试3：run_hypothesis_verification 端到端（风险型应转 unconfirmed）===")
    ctx3 = _make_ctx("北京宏远制造有限公司", "制造")
    enhanced, summary = H.run_hypothesis_verification(
        [RISK_FINDING], ctx3, [], None, RISK_SAL, RISK_PUR, None, []
    )
    f0 = enhanced[0]
    print("  score:", f0.get("score"), "note:", f0.get("_hypothesis_note"))
    print("  unconfirmed:", f0.get("_hypothesis_unconfirmed"))
    assert f0.get("_hypothesis_unconfirmed") is True, "缺失型证据不足应转 unconfirmed(待证)"
    assert "置疑" in (f0.get("_hypothesis_note") or ""), "应标注转置疑清单"
    assert summary["total_verified"] == 1

    print("\n全部断言通过 ✅")


if __name__ == "__main__":
    main()
