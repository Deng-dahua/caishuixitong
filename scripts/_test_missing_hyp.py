# -*- coding: utf-8 -*-
"""缺失型假设模板单元测试：不调用大模型，直接验证竞争假设裁决逻辑。

新裁决策略（用户 2026-09-01 指令）：
  无论行业，缺失型（"该有的没有"）信号——
  · 风险假设胜出且后验≥0.60 → 直接判定为风险（confirm，score 升）。
  · 正常假设胜出且后验≥0.60 → 判定为非风险（降级）。
  · 两假设后验接近（均<0.60，证据不足）→ 转 unconfirmed（置疑清单待企业自证）。
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

# ── 证据不足（toss-up）fixture：同地区购销，账面有运费/加工费但无场地/无能耗/无车辆 ──
AMB_PUR = [
    {"goods": "钢材", "amount": 3000000, "buyer": "北京宏远制造有限公司", "seller": "北京某钢贸有限公司"},
    {"goods": "运输费", "amount": 400000, "buyer": "北京宏远制造有限公司", "seller": "德邦物流有限公司"},
    {"goods": "加工费", "amount": 300000, "buyer": "北京宏远制造有限公司", "seller": "北京某加工厂"},
]
AMB_SAL = [
    {"goods": "机械设备", "amount": 8000000, "buyer": "北京某机电公司", "seller": "北京宏远制造有限公司"},
]
AMB_FINDING = {
    "type": "基础经营费用缺失",
    "score": 9,
    "desc": "制造业基础经营费用缺失（无场地/无能耗/无车辆）",
}


def _run(finding, ctx, bank, pur, sal):
    tpl_key = H._match_template(finding["type"])
    assert tpl_key == "missing_element", f"模板未命中 missing_element，实际={tpl_key}"
    tpl = H.HYPOTHESIS_TEMPLATES[tpl_key]
    res = H._verify_hypothesis(finding, tpl, ctx, bank, None, sal, pur, None)
    assert res is not None, "假设验证返回空"
    return res


def main():
    print("=== 测试1：风险型（类C2 零运费+跨地区+制造业无要素）→ 直接判定为风险 ===")
    ctx = _make_ctx("北京宏远制造有限公司", "制造")
    res = _run(RISK_FINDING, ctx, [], RISK_PUR, RISK_SAL)
    print("  胜出假设:", res["hypothesis_selected"], "| 后验:", res["best_posterior"])
    print("  推理:", res["reasoning"])
    assert res["selected"] == 1, "风险型应风险假设(索引1)胜出"
    assert res["best_posterior"] >= 0.60, "风险型后验应≥0.60（可判定为风险）"
    enhanced, summary = H.run_hypothesis_verification(
        [RISK_FINDING], ctx, [], None, RISK_SAL, RISK_PUR, None, []
    )
    f0 = enhanced[0]
    print("  [端到端] score:", f0.get("score"), "| note:", f0.get("_hypothesis_note"), "| unconfirmed:", f0.get("_hypothesis_unconfirmed"))
    assert f0.get("_hypothesis_unconfirmed") is not True, "风险型证据充分，应直接判定为风险而非转待证"
    assert f0.get("score") == 10, "确认风险应升级 score 至 10"
    assert "确认风险" in (f0.get("_hypothesis_note") or ""), "应标注「确认风险」"

    print("\n=== 测试2：良性型（必要费用均在账面体现）→ 判定为非风险（降级）===")
    ctx2 = _make_ctx("北京宏远制造有限公司", "制造")
    res2 = _run(BENIGN_FINDING, ctx2, BENIGN_BANK, BENIGN_PUR, BENIGN_SAL)
    print("  胜出假设:", res2["hypothesis_selected"], "| 后验:", res2["best_posterior"])
    print("  推理:", res2["reasoning"])
    assert res2["selected"] == 0, "良性型应正常假设(索引0)胜出"
    assert res2["best_posterior"] >= 0.60, "良性型后验应≥0.60（可判定为非风险）"

    print("\n=== 测试3：证据不足（同地区+有运费有加工费但无场地/能耗/车辆）→ 转置疑清单 ===")
    ctx3 = _make_ctx("北京宏远制造有限公司", "制造")
    res3 = _run(AMB_FINDING, ctx3, [], AMB_PUR, AMB_SAL)
    print("  胜出假设:", res3["hypothesis_selected"], "| 后验:", res3["best_posterior"])
    print("  推理:", res3["reasoning"])
    assert res3["best_posterior"] < 0.60, "证据不足型后验应<0.60（无法明确判定）"
    enhanced3, _ = H.run_hypothesis_verification(
        [AMB_FINDING], ctx3, [], None, AMB_SAL, AMB_PUR, None, []
    )
    fa = enhanced3[0]
    print("  [端到端] unconfirmed:", fa.get("_hypothesis_unconfirmed"), "| note:", fa.get("_hypothesis_note"))
    assert fa.get("_hypothesis_unconfirmed") is True, "证据不足应转 unconfirmed(待证)"
    assert "置疑" in (fa.get("_hypothesis_note") or ""), "应标注转置疑清单"

    print("\n全部断言通过 ✅")


if __name__ == "__main__":
    main()
