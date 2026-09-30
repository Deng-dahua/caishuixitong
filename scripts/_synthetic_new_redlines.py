# -*- coding: utf-8 -*-
"""合成验证：5 条新探测器的"信号对齐风险发生侧"正确性。
- 命中信号且无对应申报 → 触发；见对应申报 → 抑制。
- 精度陷阱：企业间"借款合同"（不征）≠"贷款合同"（征）；"融资租赁合同" ≠ 经营租赁。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.gap_tax_obligations import run_gap_tax_obligation_detection
from engine.special_redline_detectors import run_special_redline_detection


def gap_fire(contracts, decls=None):
    data = {"contracts": contracts, "tax_declarations": decls or []}
    return [f.get("redline_id") for f in run_gap_tax_obligation_detection(data, [])]


def sp_fire(rows):
    data = {"vouchers": rows}
    return [f.get("redline_id") for f in run_special_redline_detection(data, [])]


def sp_fire_sales(rows):
    """销项发票/合同侧（source=sales 的 spec 只看这一侧）。"""
    data = {"sal_invs": rows}
    return [f.get("redline_id") for f in run_special_redline_detection(data, [])]


def sp_fire_purchase(rows):
    """进项侧——用于验证「采购噪声不得误报为销售侧风险」。"""
    data = {"pur_invs": rows}
    return [f.get("redline_id") for f in run_special_redline_detection(data, [])]


cases = []

# RL-OTH-008 产权转移书据
cases.append(("008 股权转让协议 + 无申报 → 触发", "RL-OTH-008" in gap_fire([{"b": "股权转让协议"}])))
cases.append(("008 见产权转移书据申报 → 抑制", "RL-OTH-008" not in gap_fire([{"b": "股权转让协议"}], [{"t": "产权转移书据"}])))
cases.append(("008 不动产转让合同 → 触发", "RL-OTH-008" in gap_fire([{"b": "不动产转让合同"}])))

# RL-OTH-009 借款合同（银行/金融）
cases.append(("009 贷款合同 + 无申报 → 触发", "RL-OTH-009" in gap_fire([{"b": "借款合同：贷款合同"}])))
cases.append(("009 金融借款合同 → 触发", "RL-OTH-009" in gap_fire([{"b": "金融借款合同"}])))
cases.append(("009 见借款合同申报 → 抑制", "RL-OTH-009" not in gap_fire([{"b": "贷款合同"}], [{"t": "借款合同"}])))
cases.append(("009 纯企业间『借款合同』(不征) → 不触发", "RL-OTH-009" not in gap_fire([{"b": "企业与股东签订的借款合同"}])))

# RL-OTH-010 财产租赁（经营租赁）
cases.append(("010 房屋租赁合同 → 触发", "RL-OTH-010" in gap_fire([{"b": "房屋租赁合同"}])))
cases.append(("010 设备租赁合同 → 触发", "RL-OTH-010" in gap_fire([{"b": "设备租赁合同"}])))
cases.append(("010 见租赁合同申报 → 抑制", "RL-OTH-010" not in gap_fire([{"b": "房屋租赁合同"}], [{"t": "租赁合同"}])))
cases.append(("010 融资租赁合同(按借款税目) → 不触发", "RL-OTH-010" not in gap_fire([{"b": "融资租赁合同"}])))

# RL-OTH-011 财产保险
cases.append(("011 财产保险合同 → 触发", "RL-OTH-011" in gap_fire([{"b": "财产保险合同"}])))
cases.append(("011 责任保险合同 → 触发", "RL-OTH-011" in gap_fire([{"b": "责任保险合同"}])))
cases.append(("011 见保险合同申报 → 抑制", "RL-OTH-011" not in gap_fire([{"b": "财产保险合同"}], [{"t": "财产保险合同"}])))

# RL-CIT-010 资本弱化（special detector）
cases.append(("CIT-010 关联方借款 → 触发", "RL-CIT-010" in sp_fire([{"摘要": "关联方借款 统借统还"}])))
cases.append(("CIT-010 无关往来 → 不触发", "RL-CIT-010" not in sp_fire([{"摘要": "正常购销结算"}])))

# RL-SPT-019 残疾人就业保障金
cases.append(("SPT-019 账载残保金 + 无申报 → 触发", "RL-SPT-019" in gap_fire([{"b": "管理费用—残疾人就业保障金"}])))
cases.append(("SPT-019 见残保金申报 → 抑制", "RL-SPT-019" not in gap_fire([{"b": "残疾人就业保障金"}], [{"t": "残疾人就业保障金"}])))
cases.append(("SPT-019 无残保金线索 → 不触发", "RL-SPT-019" not in gap_fire([{"b": "正常购销结算"}])))

# RL-SPT-020 水利建设基金
cases.append(("SPT-020 账载水利建设基金 + 无申报 → 触发", "RL-SPT-020" in gap_fire([{"b": "税金及附加—水利建设基金"}])))
cases.append(("SPT-020 见水利建设基金申报 → 抑制", "RL-SPT-020" not in gap_fire([{"b": "水利建设基金"}], [{"t": "水利建设基金"}])))
cases.append(("SPT-020 无水利基金线索 → 不触发", "RL-SPT-020" not in gap_fire([{"b": "正常购销结算"}])))

# RL-SPT-021 工会经费（计提未拨缴）
cases.append(("SPT-021 账载工会经费 + 无拨缴申报 → 触发", "RL-SPT-021" in gap_fire([{"b": "应付职工薪酬—工会经费"}])))
cases.append(("SPT-021 见工会经费申报/拨缴 → 抑制", "RL-SPT-021" not in gap_fire([{"b": "工会经费"}], [{"t": "工会经费"}])))
cases.append(("SPT-021 无工会经费线索 → 不触发", "RL-SPT-021" not in gap_fire([{"b": "正常购销结算"}])))

# RL-VAT-009 价外费用（source=sales：只看向购买方收取侧）
cases.append(("VAT-009 销项侧『收取包装费』→ 触发", "RL-VAT-009" in sp_fire_sales([{"goods": "价外向购买方收取包装费"}])))
cases.append(("VAT-009 销项侧『违约金』→ 触发", "RL-VAT-009" in sp_fire_sales([{"goods": "向购方收取违约金"}])))
cases.append(("VAT-009 采购侧『包装费』(噪声) → 不触发", "RL-VAT-009" not in sp_fire_purchase([{"goods": "*包装费* 采购包装材料"}])))
cases.append(("VAT-009 销项侧无价外费用字样 → 不触发", "RL-VAT-009" not in sp_fire_sales([{"goods": "*饲料*猫粮"}])))

ok = 0
for name, passed in cases:
    print(("PASS " if passed else "FAIL "), name)
    ok += 1 if passed else 0
print(f"\n{ok}/{len(cases)} synthetic cases passed")
sys.exit(0 if ok == len(cases) else 1)
