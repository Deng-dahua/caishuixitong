# -*- coding: utf-8 -*-
"""缺失型模板扩围验证：无场地租金 / 外省加工费无自有产能。
原则：违法事实不因阈值而消失——缺失败象一律抓取，确认/待证仅区分"现有资料能否直接断言"。
说明：missing_element 为经营实质整体性裁决（7 项必要要素综合），单一要素补全不足以翻案；
      正常型须具备完整经营要素（场地/运输/能耗/车辆）方判良性。
"""
import os, sys
sys.path.insert(0, os.getcwd())
from engine import hypothesis_engine as H


class Ctx:
    def __init__(self, name="中山市达冠纺织有限公司", biz="制造"):
        self.company_profile = {"name": name, "biz_model": biz}


def run(find_type, desc, pur_invs, sal_invs, bank_txs=None):
    f = {"type": find_type, "score": 9, "desc": desc}
    tpl = H.HYPOTHESIS_TEMPLATES["missing_element"]
    return H._verify_hypothesis(f, tpl, Ctx(), bank_txs or [], None, sal_invs, pur_invs, None)


# 同省购销（中山/广州/深圳均属广东 → 不触发跨省零运费）
PUR = [{"goods": "钢材", "amount": 1000000, "seller": "中山市某钢贸有限公司", "direction": "进"}]
SAL = [{"goods": "针织布", "amount": 2000000, "buyer": "广州市某机电公司", "direction": "销"}]

# 完整经营要素流水（租金/运费/电费/车辆维修）
BANK_FULL = [
    {"credit": 0, "counterparty_name": "房东王先生", "summary": "支付厂房租金本月", "remark": "租金"},
    {"credit": 0, "counterparty_name": "德邦物流", "summary": "支付本月运费", "remark": "运输费"},
    {"credit": 0, "counterparty_name": "供电局", "summary": "缴纳生产用电费", "remark": "电费"},
    {"credit": 0, "counterparty_name": "汽修厂", "summary": "车辆维修费", "remark": "维修费"},
]


# ── 无场地租金：风险型（有购销、无任何经营要素证据）──
r1 = run("无场地租金及权属证明", "无场地租金却有购销业务", PUR, SAL)
assert r1["selected"] == 1, f"无场地租金风险型应确认风险, got {r1['selected']}"
assert not r1["unconfirmed"], "风险型不应转待证"
print("✓ 无场地租金·风险型 → 确认风险（score_idx=%s, posterior=%.3f）" % (r1["selected"], r1.get("best_posterior", 0)))

# ── 无场地租金：正常型（场地/运输/能耗/车辆四要素齐全）──
r2 = run("无场地租金及权属证明", "无场地租金却有购销业务", PUR, SAL, BANK_FULL)
assert r2["selected"] == 0, f"经营要素齐全应判正常, got {r2['selected']}"
assert not r2["unconfirmed"], "正常型不应转待证"
print("✓ 无场地租金·正常型（要素齐全）→ 正常解释（score_idx=%s）" % r2["selected"])

# ── 外省加工费无自有产能：风险型（外省加工费发票 + 无设备/能耗/场地）──
PUR_OP = [
    {"goods": "钢材", "amount": 1000000, "seller": "中山市某钢贸有限公司", "direction": "进"},
    {"goods": "加工费", "amount": 300000, "seller": "河南某外协加工厂", "direction": "进"},
]
r3 = run("外省加工费无自有产能佐证", "外省加工费却无自有产能佐证", PUR_OP, SAL)
assert r3["selected"] == 1, f"外省加工费无产能应确认风险, got {r3['selected']}"
assert not r3["unconfirmed"], "风险型不应转待证"
print("✓ 外省加工费·风险型 → 确认风险（score_idx=%s, posterior=%.3f）" % (r3["selected"], r3.get("best_posterior", 0)))

# ── 外省加工费：正常型（有自有设备 + 完整经营要素）──
PUR_OP_EQ = [
    {"goods": "钢材", "amount": 1000000, "seller": "中山市某钢贸有限公司", "direction": "进"},
    {"goods": "加工费", "amount": 300000, "seller": "河南某外协加工厂", "direction": "进"},
    {"goods": "注塑机", "amount": 500000, "seller": "东莞市某机械公司", "direction": "进"},
]
r4 = run("外省加工费无自有产能佐证", "外省加工费却无自有产能佐证", PUR_OP_EQ, SAL, BANK_FULL)
assert r4["selected"] == 0, f"有自有产能+要素齐全应判正常, got {r4['selected']}"
assert not r4["unconfirmed"], "正常型不应转待证"
print("✓ 外省加工费·正常型（有自有设备+要素齐全）→ 正常解释（score_idx=%s）" % r4["selected"])

# ── 证据分支单元校验 ──
ctx = H._build_evidence_context({"type": "x", "desc": ""}, Ctx(), [], None, SAL, PUR, None)
assert H._evaluate_evidence("无场地租金却有购销业务", ctx) is True
assert H._evaluate_evidence("外省加工费却无自有产能佐证", ctx) is False  # 无外省加工费发票
ctx2 = H._build_evidence_context({"type": "x", "desc": ""}, Ctx(), [], None, SAL, PUR_OP, None)
assert H._evaluate_evidence("外省加工费却无自有产能佐证", ctx2) is True  # 外省加工费+无产能
ctx_full = H._build_evidence_context({"type": "x", "desc": ""}, Ctx(), BANK_FULL, None, SAL, PUR, None)
assert H._evaluate_evidence("无场地租金却有购销业务", ctx_full) is False  # 有租金
print("✓ 证据分支单元校验通过")

print("\nALL PASS")
