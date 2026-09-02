# -*- coding: utf-8 -*-
"""场景驱动的一键分析执行核心。

解析器和经过回归验证的原子规则只负责产生可复算的观察事实。本模块负责把
观察事实放入共同资料门和适用行业场景，组织调查、正反证据、分析、业务域
协同及政策适用性核验。任何输出均为待核事实，不自动形成违法定性、税额、
处罚、移送或正式报告结论。
"""

from __future__ import annotations

import copy
import json
from collections import defaultdict
from datetime import datetime

from engine.methodology_acceptance import audit_scene_contract
from engine.methodology_portfolio import load_industry_contract, resolve_industry_code
from engine.scenario_methodology import (
    FILE_TYPE_SOURCE_FAMILIES,
    SCENE_SIGNAL_TERMS,
    _available_source_families,
    build_scenario_review_plan,
)
from engine.verified_rule_engine import VERIFIED_RULE_CATALOG, run_verified_rules


EXECUTION_VERSION = "1.0.0"
GOVERNANCE_STATUS = "scenario_contract_governed"


ENGINE_SOURCE_FAMILIES = {
    "bank_txs": {"资金结算", "支付结算"},
    "sal_invs": {"发票申报", "销售履约", "渠道订单"},
    "pur_invs": {"发票申报", "采购成本", "商品库存", "工程材料"},
    "vouchers": {"会计核算"},
    "salaries": {"人员薪酬"},
    "social_security": {"人员薪酬", "税费申报"},
    "inventory": {"生产存货", "仓储物流", "商品库存", "工程材料"},
    "trial_balance": {"会计核算"},
    "tax_declarations": {"税费申报", "发票申报"},
}


COMMON_FACT_CONTRACTS = {
    "COMMON-REVENUE-RECONCILIATION": {
        "name": "收入、开票、收款与会计记录勾稽",
        "rule_ids": {"VR001", "VR002", "VR057"},
        "target_fact": "同一主体和期间的销售履约、收入确认、开票、收款及申报差异能否由逐笔业务事实完整解释。",
        "lead": "收入与申报协同域",
        "supporting": ["销售合同和履约记录", "销项发票明细", "银行收款流水", "会计收入明细", "纳税申报表"],
        "opposing": ["借款或资本往来", "代收代付", "预收及跨期确认", "退款红冲", "非经营性资金流入"],
        "steps": ["按主体、账户和月份重建收款及开票序列", "逐笔连接合同、订单、履约、会计和申报", "对差异分别核验正常解释及未决范围"],
    },
    "COMMON-INVOICE-INTEGRITY": {
        "name": "发票数据完整性与票面关系核验",
        "rule_ids": {"VR003", "VR004", "VR010", "VR011", "VR015"},
        "target_fact": "发票重复、票面金额关系或解析结构差异是否源于重复上传、多行明细、红字处理、四舍五入或字段映射。",
        "lead": "发票数据质量域",
        "supporting": ["原始发票文件", "发票号码代码", "票面金额税额", "红蓝票关联", "上传及解析日志"],
        "opposing": ["同票多行商品明细", "重复上传", "红字发票", "四舍五入", "字段映射或解析拆分"],
        "steps": ["回查原始票面和文件指纹", "按发票代码号码及明细行去重", "修复数据后重新执行相关场景"],
    },
    "COMMON-EMPLOYMENT-COVERAGE": {
        "name": "工资、社保、用工身份与扣缴范围核验",
        "rule_ids": {"VR005", "VR055"},
        "target_fact": "工资名册、社会保险、实际用工、劳务结算和个人所得税扣缴范围差异能否按人员及月份解释。",
        "lead": "人员薪酬与扣缴域",
        "supporting": ["劳动或劳务合同", "考勤及岗位记录", "工资明细", "社会保险明细", "个税扣缴申报"],
        "opposing": ["劳务派遣", "退休返聘", "兼职或非全日制", "入离职月份", "异地参保", "非雇员劳务"],
        "steps": ["建立人员唯一身份和月份主键", "连接合同、考勤、工资、社保和扣缴", "逐人核验差异原因及适用身份"],
    },
    "COMMON-INVENTORY-INTEGRITY": {
        "name": "存货数量、滚动关系与账实截止核验",
        "rule_ids": {"VR006", "VR007"},
        "target_fact": "期初、入库、出库、调拨、损耗和期末数量差异是否源于真实业务、截止口径或数据质量问题。",
        "lead": "存货物流与生产经营域",
        "supporting": ["存货收发存明细", "仓库盘点", "调拨及在途记录", "生产领退料", "出入库单据"],
        "opposing": ["跨仓调拨", "在途物资", "单位换算", "退货冲销", "合理损耗", "单据跨期"],
        "steps": ["统一存货编码、仓库、单位和期间", "逐笔重算期初加收入减发出等于期末", "连接盘点、调拨、在途和损耗记录"],
    },
    "COMMON-ACCOUNTING-INTEGRITY": {
        "name": "会计凭证完整性与借贷关系核验",
        "rule_ids": {"VR008"},
        "target_fact": "上传凭证的借贷差异是否由缺行、解析失败、外币折算或原始凭证本身不完整造成。",
        "lead": "会计数据质量域",
        "supporting": ["原始凭证", "凭证分录", "科目余额表", "总账明细", "解析日志"],
        "opposing": ["缺失分录行", "解析列错位", "外币折算", "汇总导出", "重复或截断文件"],
        "steps": ["按凭证号和期间回查原始分录", "核对币种、方向和借贷合计", "修复资料后重新执行业务场景"],
    },
    "COMMON-FUND-INTEGRITY": {
        "name": "资金流水余额及往来关系核验",
        "rule_ids": {"VR009", "VR013"},
        "target_fact": "同一账户余额滚动或同一对手方双向收付差异是否由排序、币种、退款、借还款、保证金或真实双向交易解释。",
        "lead": "资金结算与往来域",
        "supporting": ["银行原始流水", "账户及币种信息", "收付款指令", "往来合同", "会计银行明细"],
        "opposing": ["日内排序", "借贷方向映射", "外币账户", "退款", "借还款", "保证金", "代收代付"],
        "steps": ["按账户币种日期流水号重建余额", "按对手方穿透双向收付用途", "连接合同、会计及期后结算"],
    },
    "COMMON-COUNTERPARTY-ROLE": {
        "name": "客户供应商双重角色与购销事实核验",
        "rule_ids": {"VR012", "VR021"},
        "target_fact": "同一交易对手兼具客户和供应商身份，或供应商与客户名称高度近似，是否源于真实双向交易、集团分设购销公司、材料互供、返修、平台结算或闭环开票。",
        "lead": "交易对手与合同履约域",
        "supporting": ["购销合同", "订单及货物流", "收付款流水", "发票明细", "定价及结算资料", "股权及注册地址资料"],
        "opposing": ["返修服务", "材料互供", "平台代结算", "集团内部协同", "正常双向贸易", "同字号关联企业"],
        "steps": ["建立交易对手统一身份", "分别复原采购和销售权利义务及履行", "对名称近似主体核验股权、地址和人员重叠", "核对定价、货物、资金和税会处理"],
    },
    "COMMON-PRODUCTION-SUBSTANCE": {
        "name": "生产经营实质与能源消耗核验",
        "rule_ids": {"VR014", "VR023"},
        "target_fact": "登记为生产制造的企业，其进项中是否具备与生产规模相匹配的生产用能源（电、水、燃气、蒸汽）采购，进销物耗投入产出比是否合理，以及是否有真实的生产场地、设备和人员支撑其经营实质。",
        "lead": "存货物流与生产经营域",
        "supporting": ["生产用能源采购发票", "厂房租赁或产权资料", "设备及产能资料", "水电燃气缴费凭证", "BOM和存货记录", "生产记录及考勤"],
        "opposing": ["生产外包或外购成品", "房东代收能源费用", "自备发电或新能源", "资料未上传或归集口径不同", "停产、转产或试生产"],
        "steps": ["统计生产用能源采购金额与生产经营采购规模", "核算进销物耗投入产出比", "连接厂房、设备、人员与产能资料", "核验委外加工或外购成品解释"],
    },
    "COMMON-WORKFORCE-REVENUE": {
        "name": "用工人数与收入规模核验",
        "rule_ids": {"VR022"},
        "target_fact": "销项收入规模与工资、社保所反映的用工人数是否匹配，人均产值异常偏高或偏低是否指向虚开、空壳、隐匿收入或业务外包未申报。",
        "lead": "人员薪酬与扣缴域",
        "supporting": ["工资明细", "社会保险明细", "销项发票", "劳动或劳务合同", "考勤及岗位记录"],
        "opposing": ["业务外包", "临时用工", "季节性生产", "机械化程度高", "高附加值产品", "挂靠经营"],
        "steps": ["按姓名去重统计工资和社保覆盖人数", "计算人均产值并比对行业合理区间", "核验外包、临时用工和高附加值解释", "对异常人均产值逐人核验用工真实性"],
    },
    "COMMON-SUPPLY-CHAIN-PENETRATION": {
        "name": "供应商地域分布与购销集中度核验",
        "rule_ids": {"VR016", "VR017", "VR024"},
        "target_fact": "供应商跨省分布、单一地区群集以及购销双方集中度过高，是否源于真实产业链布局，还是指向无实质交易的票据流转、关联交易或对单一渠道的异常依赖。",
        "lead": "交易对手与合同履约域",
        "supporting": ["采购和销售合同", "物流及交付记录", "供应商和客户资质", "定价及结算资料", "关联关系及股权资料"],
        "opposing": ["原料产地集中或大宗采购", "定制生产或代工模式", "单一核心客户", "集团内部协同", "正常跨省贸易"],
        "steps": ["按省市聚合供应商和客户分布", "计算前3大供应商和客户的金额占比", "对跨省和集中交易逐户核验合同、物流与付款", "核验关联关系及定价独立性"],
    },
    "COMMON-TAX-DECLARATION-RECONCILIATION": {
        "name": "纳税申报与发票勾稽核验",
        "rule_ids": {"VR018", "VR019"},
        "target_fact": "增值税申报表的销售额、进项税额与同期销项开票金额、进项发票税额的差异，能否由未开票收入、认证抵扣时点、红字发票、进项转出和税会差异完整解释。",
        "lead": "收入与申报协同域",
        "supporting": ["增值税申报表（主表及附表）", "销项发票明细", "进项发票明细", "进项抵扣认证清单", "银行缴税凭证"],
        "opposing": ["未开票收入", "纳税义务发生时间与开票时点差异", "红字发票", "进项转出", "留抵税额", "农产品加计抵扣", "认证抵扣跨期"],
        "steps": ["按月度重建申报销售额与销项开票序列", "按月度重建申报进项税额与进项发票税额序列", "对差异逐期核验未开票收入、红冲和抵扣时点", "取得申报表附表后完成正式勾稽"],
    },
    "COMMON-PERSONNEL-FUND-FLOW": {
        "name": "六员个人账户与经营资金往来核验",
        "rule_ids": {"VR020", "VR025", "VR056"},
        "target_fact": "法定代表人、股东、董事等六员个人账户频繁出现在公司银行流水对手方，是否源于借款、代垫、报销等正常往来，还是指向资金回流、代收代付、隐匿收入或账外经营。",
        "lead": "资金结算与往来域",
        "supporting": ["银行原始流水", "借款或代垫协议", "报销凭证", "往来明细账", "个人账户说明"],
        "opposing": ["股东借款或增资", "代垫费用报销", "备用金", "正常工资奖金", "个人代收后转回公司"],
        "steps": ["提取六员姓名并匹配银行流水对手方", "逐笔核验个人往来款项性质", "核对借款、报销、工资与往来账", "对无合理解释的个人收付款追查资金去向"],
    },
    "COMMON-TAX-BURDEN-ANOMALY": {
        "name": "税负率与申报实质核验",
        "rule_ids": {"VR026", "VR029", "VR031"},
        "target_fact": "增值税税负率是否显著偏离行业参考区间，是否存在长期零申报或印花税计税依据明显低于购销金额，能否由进销项结构、留抵、免税、未开票收入申报和合法免征完整解释。",
        "lead": "收入与申报协同域",
        "supporting": ["增值税申报表及附表", "进销项发票明细", "进项抵扣认证清单", "印花税申报及合同台账", "未开票收入说明"],
        "opposing": ["进项结构差异", "留抵结转", "免税或简易计税", "农产品加计抵扣", "固定资产一次性抵扣", "小微企业印花免征", "筹建或停产期"],
        "steps": ["测算实缴增值税与应税收入之比", "比对行业参考区间并解释偏离", "核验长期零申报与经营实质是否冲突", "勾稽印花税计税依据与购销合同金额"],
    },
    "COMMON-INVOICE-LIFE-CYCLE": {
        "name": "作废红冲与未开票收入隐匿核验",
        "rule_ids": {"VR027", "VR028", "VR053", "VR054"},
        "target_fact": "作废/红冲发票占比是否异常，银行收款是否持续、大幅超过销项开票且无未开票收入申报，是否指向临近申报期调节税基或隐匿未开票收入。",
        "lead": "发票数据质量域",
        "supporting": ["销项发票明细含状态", "作废红冲审批与重开记录", "银行原始收款流水", "未开票收入申报", "退货折让凭证"],
        "opposing": ["开票错误正常作废", "真实退货折让", "预收款", "借款或资本往来", "代收代付", "关联往来", "非应税收入"],
        "steps": ["统计作废红冲占比与月末季末集中度", "逐票核验原交易真实履行情况", "重建收款与开票序列并计算差额", "对无合理解释的差额追查未开票收入"],
    },
    "COMMON-SHAREHOLDER-LOAN": {
        "name": "股东借款与其他应收款视同分红核验",
        "rule_ids": {"VR030"},
        "target_fact": "企业账户向六员个人大额转出或其他应收款长期挂股东借款，在纳税年度终了是否既不归还又未用于生产经营，是否依财税〔2003〕158号视同红利分配并按20%代扣个税。",
        "lead": "资金结算与往来域",
        "supporting": ["银行流水对手方", "借款协议与利率", "其他应收款明细账", "股东借款用途凭证", "个税扣缴申报"],
        "opposing": ["年内归还借款", "用于生产经营的借款", "正常工资奖金分红", "代垫费用报销", "注册资本实缴"],
        "steps": ["提取六员并匹配银行转出与其他应收款挂账", "核验借款协议、利率与还款时点", "判断纳税年度终了是否未还且未用于经营", "计算视同分红个税及企业代扣义务"],
    },
    "COMMON-INPUT-TAX-REVERSAL": {
        "name": "进项税额转出用途核验",
        "rule_ids": {"VR032"},
        "target_fact": "取得增值税专用发票并抵扣的进项，是否用于业务招待、集体福利、个人消费、免税/简易计税项目、非正常损失或贷款服务等不得抵扣用途，已抵扣的是否依规做进项税额转出。",
        "lead": "采购与抵扣域",
        "supporting": ["进项发票品名与摘要", "成本费用科目明细账", "用途说明与审批", "福利费/业务招待费明细", "进项税额转出凭证"],
        "opposing": ["生产原料或商品购进", "生产经营用固定资产", "加工修理修配劳务", "正常应税项目购进"],
        "steps": ["提取专票并识别用途关键词", "结合企业画像排除生产经营用途豁免", "逐张核对成本费用科目与用途", "计算应转出未转出税额"],
    },
    "COMMON-GOODS-DIVERGENCE": {
        "name": "进销品名背离与变名开票核验",
        "rule_ids": {"VR033"},
        "target_fact": "购进与销售商品是否跨越明显不同大类且非加工服务衔接，是否伴随资金回流或异常票流，指向变名开票掩饰虚开。",
        "lead": "发票真实性域",
        "supporting": ["购进与销售商品清单", "BOM与生产工艺", "物流单据与出入库", "资金回流证据", "上下游交易实质"],
        "opposing": ["原料→成品合理产业链", "加工服务衔接", "受托加工", "正常贸易品名一致"],
        "steps": ["归集进销商品大类", "判断是否属于合理产业链或加工服务", "对背离项追查物流与资金闭环", "结合上下游协查确认交易实质"],
    },
    "COMMON-EXPENSE-FABRICATION": {
        "name": "成本费用真实性与虚列核验",
        "rule_ids": {"VR034"},
        "target_fact": "大额咨询/会议/广告/服务/佣金费用及现金支出是否真实发生，是否对应真实合同与成果物，费用率畸高是否源于虚列、关联交易转移或收入隐匿。",
        "lead": "成本费用域",
        "supporting": ["费用凭证与合同", "成果物（方案/纪要/验收）", "付款对象工商与纳税信用", "现金去向", "成本结构同行业对比"],
        "opposing": ["真实咨询服务合同", "正常营销推广", "合理会议培训", "经营必需的现金支出"],
        "steps": ["筛查大额敏感费用与现金支出", "逐笔核验合同与成果物", "穿透付款对象（个体户/空壳）", "结合费用率与收入核验真实性"],
    },
    "COMMON-STAMP-OTHER-ITEMS": {
        "name": "印花税其他税目漏报核验",
        "rule_ids": {"VR035"},
        "target_fact": "借款合同、租赁合同等分税目是否按规定贴花，申报印花税计税依据是否覆盖全部应税凭证，是否存在仅按购销申报而漏报其他税目。",
        "lead": "税费申报域",
        "supporting": ["借款合同与银行流水", "租赁合同与租赁费凭证", "印花税各税目申报表", "产权转移书据", "免税情形证明"],
        "opposing": ["金融机构借款合同免征", "小微印花税免征", "已全额贴花", "非应税凭证"],
        "steps": ["推算借款/租赁计税依据", "比对申报印花税计税依据", "逐税目核对贴花", "排除法定免征后认定漏报"],
    },
    "COMMON-DEEMED-SALES": {
        "name": "视同销售销项计提核验",
        "rule_ids": {"VR036"},
        "target_fact": "无偿赠送、样品、自产或委托加工货物用于集体福利/个人消费、在建工程等，是否按规定视同销售计提销项税额，是否存在少计收入。",
        "lead": "税会差异域",
        "supporting": ["赠送/样品凭证与受赠对象", "福利费/在建工程领用明细", "销项发票零金额样品", "组成计税价格依据"],
        "opposing": ["真实销售费用-促销（已含视同销售）", "非应税货物移转", "已按组成计税价格申报", "纯内部调拨不涉税"],
        "steps": ["筛查赠送/样品/福利领用", "核对是否对应确认收入", "按组成计税价格复核销项", "排除已合规处理项"],
    },
    "COMMON-TRANSFER-PRICING": {
        "name": "关联交易转让定价偏离核验",
        "rule_ids": {"VR037"},
        "target_fact": "同一品名同单位对不同交易对手方的单价是否偏离独立交易原则(ARM'S LENGTH)，是否存在利润输送或成本虚增；是否需工商股权穿透识别隐性关联方。",
        "lead": "关联交易域",
        "supporting": ["同品名多对手方交易单价", "工商股权穿透/关联方清单", "同期资料与可比分析", "进销单价倒挂线索"],
        "opposing": ["有同期资料佐证独立交易价格", "市场批量折扣合理", "非关联交易", "成本驱动定价合理"],
        "steps": ["计算同品名单价离散度", "识别偏离中位数异常交易", "股权穿透判定是否关联", "补同期资料举证合理"],
    },
    "COMMON-CIT-LIMITS": {
        "name": "企业所得税税前扣除限额核验",
        "rule_ids": {"VR038", "VR039", "VR040", "VR041"},
        "target_fact": "业务招待费(60%且≤收入5‰)、广告费(≤收入15%)、福利费(≤工资14%)、折旧摊销是否超限或异常，未做纳税调增即少缴所得税。",
        "lead": "所得税域",
        "supporting": ["凭证归集的限额费用", "营业收入/工资总额", "固定资产原值与折旧政策", "纳税调整台账"],
        "opposing": ["已做纳税调增", "未超限", "资本性支出已正确区分", "符合一次性扣除政策"],
        "steps": ["归集限额费用", "测算扣除上限", "比对实际列支", "超限额未调增即预警"],
    },
    "COMMON-DEDUCTIBLE-TAXES": {
        "name": "财产税与附加税计征勾稽",
        "rule_ids": {"VR042", "VR043"},
        "target_fact": "房产税从价(原值×70%×1.2%)/从租(租金×12%)与城建教育附加随增值税附征是否漏报或低报。",
        "lead": "财产行为税域",
        "supporting": ["固定资产房屋原值", "租赁合同租金", "实缴增值税", "附加税与房产税申报"],
        "opposing": ["已申报缴纳", "计税依据一致", "地区税率适用正确"],
        "steps": ["测算从价/从租房产税", "测算随征附加税", "与申报勾稽", "漏报/低报预警"],
    },
    "COMMON-OFFBOOK-EVIDENCE": {
        "name": "账外经营间接证据链风险检查",
        "rule_ids": {"VR044", "VR045", "VR046", "VR047", "VR048", "VR049", "VR052"},
        "target_fact": "账外经营/实物盘点/业务真实性难以直接取证，须以进销存背离、运输费缺失、长期滞销、滚动矛盾、规格不一致、损耗异常等间接证据链推断嫌疑并责令补资。",
        "lead": "风险检查间接证据域",
        "supporting": ["进销存台账", "运输合同/运费凭证", "BOM工艺定额", "发票品名规格", "银行流水"],
        "opposing": ["账面与实物盘点一致", "物流资料齐全", "规格工艺逻辑自洽", "损耗率在定额内", "已提供责令补充资料且排除嫌疑"],
        "steps": ["核算库存收入比/出库入库比", "比对应有物流与实际运费", "筛查长期滞销与滚动矛盾", "核对同名规格与BOM损耗", "形成线索并责令补资"],
    },
    "COMMON-CROSSBORDER-PENETRATION": {
        "name": "跨境交易穿透与取证兜底",
        "rule_ids": {"VR050", "VR051"},
        "target_fact": "跨境交易须经报关单/海关缴款书/外汇凭证穿透境外实控；所有线索型发现须汇成《补充资料责令单》固定证据。",
        "lead": "风险检查取证域",
        "supporting": ["报关单与海关缴款书", "涉外收付款凭证", "境外关联方股权穿透", "各规则线索汇总的补资要求"],
        "opposing": ["已提供完整报关与外汇资料且交易真实", "责令补资后疑点排除"],
        "steps": ["识别境外对手方/外币结算", "检查报关外汇资料", "缺资料即出穿透线索", "聚合全量线索生成责令单"],
    },
}


RULE_CONCEPTS = {
    "VR001": ("收入", "销售", "收款", "开票", "资金", "申报"),
    "VR002": ("收入", "销售", "会计", "开票", "申报"),
    "VR005": ("人员", "用工", "工资", "社保", "扣缴"),
    "VR006": ("库存", "存货", "仓储", "调拨", "期末"),
    "VR007": ("库存", "存货", "入库", "出库", "盘点"),
    "VR012": ("客户", "供应商", "购销", "关联", "交易对手"),
    "VR013": ("资金", "收款", "付款", "结算", "往来", "对手方"),
    "VR014": ("生产", "能源", "水电", "燃气", "产能", "物耗", "实质"),
    "VR015": ("发票", "品名", "数据质量", "缺项", "解析"),
    "VR016": ("供应商", "地域", "跨省", "采购", "分布", "集中"),
    "VR017": ("客户", "供应商", "集中度", "购销", "依赖", "占比"),
    "VR018": ("申报", "销售额", "开票", "勾稽", "收入", "差异"),
    "VR019": ("申报", "进项", "抵扣", "勾稽", "税额", "差异"),
    "VR020": ("六员", "法人", "股东", "个人账户", "资金", "回流"),
    "VR021": ("供应商", "客户", "名称", "近似", "关联", "字号"),
    "VR022": ("用工", "人数", "工资", "社保", "人均", "收入"),
    "VR023": ("进销", "物耗", "投入产出", "加价", "倒挂", "原材料"),
    "VR024": ("个体户", "个人", "供应商", "客户", "经营部", "代开"),
    "VR025": ("资金回流", "公私混同", "个人账户", "转存", "转取", "抽逃"),
    "VR026": ("税负率", "增值税", "行业区间", "偏离", "隐匿", "空壳"),
    "VR027": ("作废", "红冲", "发票", "占比", "月末", "隐匿收入"),
    "VR028": ("未开票收入", "收款", "开票", "隐匿", "资金回流", "私户"),
    "VR029": ("零申报", "长期", "异常申报", "空壳", "账外经营", "预警"),
    "VR030": ("股东借款", "其他应收款", "视同分红", "个税", "挂账", "158号"),
    "VR031": ("印花税", "购销合同", "计税依据", "漏报", "勾稽", "偏差"),
    "VR032": ("进项税额", "转出", "业务招待", "集体福利", "专票", "不得抵扣"),
    "VR033": ("进销", "品名", "变名", "背离", "虚开", "大类"),
    "VR034": ("成本费用", "虚列", "咨询费", "会议费", "现金", "异常"),
    "VR035": ("印花税", "借款合同", "租赁合同", "其他税目", "漏报", "贴花"),
    "VR036": ("视同销售", "赠送", "样品", "集体福利", "自产自用", "销项"),
    "VR037": ("关联交易", "转让定价", "单价偏离", "独立交易", "利润输送", "股权穿透"),
    "VR038": ("业务招待费", "扣除限额", "60%", "收入5‰", "纳税调增", "所得税"),
    "VR039": ("广告费", "业务宣传费", "15%限额", "结转", "所得税", "纳税调增"),
    "VR040": ("职工福利费", "14%限额", "工资总额", "工会经费", "所得税", "纳税调增"),
    "VR041": ("折旧", "摊销", "长期待摊", "一次性扣除", "资产计税基础", "所得税"),
    "VR042": ("房产税", "从价计征", "从租计征", "房屋原值", "租金", "漏报"),
    "VR043": ("城建税", "教育费附加", "地方教育附加", "随增值税附征", "漏报", "勾稽"),
    "VR044": ("账外经营", "库存收入比", "出库入库比", "隐匿存货", "间接证据", "责令补资"),
    "VR045": ("账外发货", "运输费背离", "物流缺失", "第三方代发", "间接证据", "责令补资"),
    "VR046": ("呆滞库存", "长期滞销", "虚假入库", "账外调拨", "实物盘点", "责令补资"),
    "VR047": ("库存滚动", "盘亏未处理", "账外领用", "盘点缺失", "恒等式", "责令补资"),
    "VR048": ("变名开票", "规格不一致", "虚假交易", "BOM工艺", "同名存货", "责令补资"),
    "VR049": ("业务真实性", "物流缺失", "损耗率偏离", "磅单", "出入库计量", "责令补资"),
    "VR050": ("跨境交易", "境外对手方", "外币结算", "报关单", "外汇凭证", "穿透"),
    "VR051": ("补充资料责令单", "取证兜底", "盲区交代", "证据固定", "程序性文书", "责令补资"),
    "VR052": ("委托加工", "地理背离", "舍近求远", "运输费缺失", "委托加工合同", "业务真实性", "虚开发票嫌疑"),
    "VR053": ("作废发票", "资金回流", "开票收款后作废", "对公收款流水", "隐匿已收收入", "三流闭合", "证据链"),
    "VR054": ("作废发票", "未重开", "未申报", "只作废不重开", "系统性隐匿", "申报收入背离", "重开覆盖率"),
}


def _rule_index():
    return {item["id"]: item for item in VERIFIED_RULE_CATALOG}


def _source_families_for_rule(rule_id):
    spec = _rule_index().get(rule_id, {})
    families = set()
    for source in spec.get("required_sources", []):
        families.update(ENGINE_SOURCE_FAMILIES.get(source, set()))
    return families


def _file_inventory(file_results):
    values = []
    for item in file_results or []:
        if not isinstance(item, dict) or item.get("error"):
            continue
        file_type = str(item.get("type", "unknown") or "unknown").strip().lower()
        values.append({
            "file": str(item.get("file") or item.get("original_name") or ""),
            "type": file_type,
            "source_families": sorted(FILE_TYPE_SOURCE_FAMILIES.get(file_type, set())),
        })
    return values


def _trusted_observation(item):
    if not isinstance(item, dict):
        return False
    rule_id = str(item.get("rule_id", ""))
    return (
        rule_id in _rule_index()
        and item.get("source_lineage_status") == "observed_from_uploaded_data"
        and item.get("rule_maturity") == "verified_executable_screening"
    )


def _observation_text(item):
    return " ".join(
        str(item.get(key, "") or "")
        for key in ("type", "detail", "category", "limitations")
    )


def _scene_text(scene):
    payload = {
        "name": scene.get("name"),
        "doubt": scene.get("doubt"),
        "clue_chain": scene.get("clue_chain"),
        "analysis_chain": scene.get("analysis_chain"),
        "domain_collaboration": scene.get("domain_collaboration"),
        "taxes": scene.get("taxes"),
    }
    return json.dumps(payload, ensure_ascii=False)


def _scene_match(observation, scene):
    rule_id = str(observation.get("rule_id", ""))
    concepts = RULE_CONCEPTS.get(rule_id, ())
    if not concepts:
        return 0, []
    text = _scene_text(scene)
    obs_text = _observation_text(observation)
    hits = [term for term in concepts if term in text]
    direct = [
        term for term in SCENE_SIGNAL_TERMS.get(scene.get("id"), ())
        if term in obs_text
    ]
    source_overlap = _source_families_for_rule(rule_id).intersection(
        set((scene.get("applicability") or {}).get("required_source_families", []))
    )
    score = len(hits) * 2 + len(direct) * 5 + min(len(source_overlap), 2)
    if not direct and len(hits) < 2:
        return 0, []
    return score, sorted(set(hits + direct))


def _map_observations_to_scenes(observations, scenes):
    mapped = defaultdict(list)
    unmapped = []
    for observation in observations:
        rule_id = str(observation.get("rule_id", ""))
        if rule_id not in RULE_CONCEPTS:
            continue
        candidates = []
        for scene in scenes:
            score, terms = _scene_match(observation, scene)
            if score:
                candidates.append((score, scene.get("id", ""), terms))
        candidates.sort(key=lambda item: (-item[0], item[1]))
        if not candidates or candidates[0][0] < 5:
            unmapped.append({
                "rule_id": rule_id,
                "name": observation.get("type", ""),
                "reason": "未与适用行业场景形成足够明确的业务语义关联，只保留在跨行业共同事实门。",
            })
            continue
        score, scene_id, terms = candidates[0]
        item = copy.deepcopy(observation)
        item["scenario_match_score"] = score
        item["scenario_match_terms"] = terms
        mapped[scene_id].append(item)
    return mapped, unmapped


def _quality_issues(observations):
    data_quality_ids = {"VR003", "VR004", "VR008", "VR009", "VR010", "VR011"}
    issues = []
    for item in observations:
        rule_id = str(item.get("rule_id", ""))
        if rule_id not in data_quality_ids:
            continue
        issues.append({
            "rule_id": rule_id,
            "name": item.get("type", ""),
            "detail": item.get("detail", ""),
            "affected_source_families": sorted(_source_families_for_rule(rule_id)),
            "status": "须先修复或回查原始资料",
        })
    return issues


def _gate_results(scene, available_families, quality_issues):
    available = set(available_families)
    blocked_families = {
        family
        for issue in quality_issues
        for family in issue.get("affected_source_families", [])
    }
    results = []
    for gate in scene.get("source_gates", []):
        observed = sorted(available.intersection(gate.get("any", [])))
        quality_blocked = bool(set(observed).intersection(blocked_families))
        results.append({
            "name": gate.get("name", ""),
            "satisfied": bool(observed) and not quality_blocked,
            "observed": observed,
            "accepted_families": list(gate.get("any", [])),
            "quality_blocked": quality_blocked,
        })
    return results


def _status_from_gates(gates):
    if not gates:
        return "待补资料_可初筛"
    satisfied = sum(1 for item in gates if item.get("satisfied"))
    if satisfied == 0:
        return "资料不足_未启动"
    if satisfied < len(gates):
        return "待补资料_可初筛"
    return "资料就绪_待人工核验"


def _observation_digest(observation):
    return {
        "rule_id": observation.get("rule_id", ""),
        "name": observation.get("type", ""),
        "detail": observation.get("detail", ""),
        "observed_metrics": copy.deepcopy(observation.get("observed_metrics", {})),
        "source_families": sorted(_source_families_for_rule(observation.get("rule_id", ""))),
        "limitations": observation.get("limitations", ""),
        "source_lineage_status": observation.get("source_lineage_status", ""),
    }


def _merge_observation_details(observed):
    """多条观察合并为一段 detail：各项去尾句号后以"。"分隔，避免 "。；""。。"。"""
    parts = []
    for item in observed:
        text = str(item.get("detail", "") or "").strip()
        if not text:
            continue
        text = text.rstrip("。；;、 ")
        if text:
            parts.append(text)
    merged = "。".join(parts)
    if merged and not merged.endswith(("。", "！", "？")):
        merged += "。"
    return merged


def _merge_observed_metrics(observations):
    """汇总多条观察的 observed_metrics，供企业版报告渲染『可回查明细表』。

    合并策略：标量/集合取并集式合并；同名列表（examples / *_examples）拼接去重，
    避免后一条覆盖前一条导致明细丢失。返回的 dict 可直接挂到 finding 上。
    """
    merged = {}
    list_keys = {"examples", "duplicate_invoice_examples", "balance_mismatch_examples",
                 "invoice_mismatch_examples", "counterparty_examples", "overlap_examples",
                 "voucher_examples", "negative_items", "inventory_mismatch_examples"}
    for item in observations:
        om = (item.get("observed_metrics") if isinstance(item, dict) else {}) or {}
        if not isinstance(om, dict):
            continue
        for k, v in om.items():
            if k in list_keys and isinstance(v, list):
                base = merged.setdefault(k, [])
                seen = {id(x) for x in base}
                for x in v:
                    if id(x) not in seen:
                        base.append(x); seen.add(id(x))
            elif k in merged:
                # 标量冲突：保留首个非空值（多个观察的同名汇总指标取首个）
                if not merged[k]:
                    merged[k] = v
            else:
                merged[k] = v
    return merged


def _common_finding(contract_id, contract, observations, file_inventory):
    observed = [_observation_digest(item) for item in observations]
    source_families = sorted({family for item in observed for family in item["source_families"]})
    detail = _merge_observation_details(observed)
    # 基于观察分数计算汇总分数和等级
    obs_scores = [max(0, int(item.get("score", 0) or 0)) for item in observations]
    max_obs_score = max(obs_scores) if obs_scores else 0
    total_score = sum(obs_scores)
    source_count = len(source_families)
    # 证据驱动复核分级（2026-08-26 审计修复 P0-3：统一政策——所有分支均强制人工复核，
    # 强证据仅进入快速复核通道，不免除复核、不允许自动定性、不提前放行发布。
    # 【原实现备查（已停用）：强证据分支 finding_status="system_assisted_pending_confirmation"、
    #   required_review=False，conclusion_state="系统辅助定性_待人工确认"、
    #   automatic_determination_allowed=True、release_status="可发布_已系统辅助定性"】）
    if source_count >= 3 and max_obs_score >= 7:
        risk_level = "高风险"
        finding_status = "strong_evidence_pending_human_confirmation"
        required_review = True
    elif source_count >= 2 and max_obs_score >= 5:
        risk_level = "中风险"
        finding_status = "multi_source_pending_review"
        required_review = True
    elif source_count >= 1 and max_obs_score >= 3:
        risk_level = "低风险"
        finding_status = "single_source_pending_evidence"
        required_review = True
    else:
        risk_level = "待核验"
        finding_status = "pending_fact_human_review"
        required_review = True
    return {
        "fact_id": contract_id,
        "scene_fact_id": contract_id,
        "scene_id": contract_id,
        "scenario_scope": "common_fact_gate",
        "type": f"待核事实：{contract['name']}",
        "category": "跨行业共同事实门",
        "domain": contract["lead"],
        "level": risk_level,
        "score": min(10, max_obs_score),
        "total_score": total_score,
        "priority": "按资料质量和影响范围人工排序",
        "detail": detail or contract["target_fact"],
        "description": contract["target_fact"],
        "finding_status": finding_status,
        "conclusion_state": "证据充分_待人工确认" if finding_status == "strong_evidence_pending_human_confirmation" else "待人工复核_未定性",
        "conclusion_scope": "observed_fact_and_investigation_only",
        "required_human_review": required_review,
        "automatic_determination_allowed": False,
        "report_release_allowed": False,
        "release_status": "草稿_待人工复核",
        "policy_validity": "待按事实期间、地区、纳税人身份和现行有效依据人工核验",
        "tax_impact": "尚未形成税费影响结论；须完成事实核验、政策适用和金额底稿后另行评价。",
        "target_fact": contract["target_fact"],
        "observations": observed,
        "observed_metrics": _merge_observed_metrics(observed),
        "independent_sources": source_families,
        "independent_source_count": len(source_families),
        "source_files": copy.deepcopy(file_inventory),
        "investigation_steps": list(contract["steps"]),
        "supporting_evidence": [{"source": item, "status": "待逐项取得并回查原始载体"} for item in contract["supporting"]],
        "opposing_evidence": [{"explanation": item, "status": "待使用同一证据标准核验"} for item in contract["opposing"]],
        "reasonable_explanations": list(contract["opposing"]),
        "analysis_plan": ["确定主体、事项和期间", "复算观察差异", "核验支持材料", "核验反向解释", "限定能够证明的范围", "提交人工复核"],
        "domain_collaboration": {"lead": contract["lead"], "partners": []},
        "suggestion": "；".join(contract["steps"]),
        "methodology_controls": {
            "signal_is_not_evidence": True,
            "missing_data_is_not_violation": True,
            "supporting_and_opposing_evidence_same_standard": True,
            "amount_and_legal_characterisation_separate": True,
        },
        "_scenario_governed": True,
        "_canonical_scenario_output": True,
    }


def _industry_finding(industry_code, scene, observations, gates, file_inventory):
    doubt = scene.get("doubt") or {}
    clue = scene.get("clue_chain") or {}
    evidence = scene.get("evidence_chain") or {}
    analysis = scene.get("analysis_chain") or {}
    collaboration = scene.get("domain_collaboration") or {}
    policy = scene.get("policy_applicability") or {}
    status = _status_from_gates(gates)
    observed = [_observation_digest(item) for item in observations]
    source_families = sorted({family for item in observed for family in item["source_families"]})
    missing_gates = [item["name"] for item in gates if not item.get("satisfied")]
    detail = _merge_observation_details(observed)
    steps = [
        {
            "step": item.get("step"),
            "action": item.get("action", ""),
            "join_keys": list(item.get("join_keys", [])),
            "deliverable": item.get("deliverable", ""),
            "branch_if_missing": item.get("branch_if_missing", ""),
        }
        for item in clue.get("steps", [])
    ]
    acceptance = audit_scene_contract(scene)
    # 基于证据和观察计算风险等级
    obs_scores = [max(0, int(item.get("score", 0) or 0)) for item in observations]
    max_obs_score = max(obs_scores) if obs_scores else 0
    total_obs_score = sum(obs_scores)
    source_count = len(source_families)
    # 2026-08-26 审计修复（P0-3）：统一政策——所有分支均强制人工复核，
    # 强证据仅进入快速复核通道（required_review=True / auto_allowed=False / release_allowed=False）。
    # 【原实现备查（已停用）：强证据分支 finding_status="system_assisted_pending_confirmation"、
    #   required_review=False、release_allowed=True、auto_allowed=True、
    #   release_status="可发布_已系统辅助定性"】
    if source_count >= 3 and max_obs_score >= 7 and status == "资料就绪_待人工核验":
        risk_level = "高风险"
        finding_status = "strong_evidence_pending_human_confirmation"
        required_review = True
        release_allowed = False
        auto_allowed = False
    elif source_count >= 2 and max_obs_score >= 5:
        risk_level = "中风险"
        finding_status = "multi_source_pending_review"
        required_review = True
        release_allowed = False
        auto_allowed = False
    elif source_count >= 1 and max_obs_score >= 3:
        risk_level = "低风险"
        finding_status = "single_source_pending_evidence"
        required_review = True
        release_allowed = False
        auto_allowed = False
    else:
        risk_level = "待核验" if status == "资料就绪_待人工核验" else "资料缺口"
        finding_status = "pending_fact_human_review"
        required_review = True
        release_allowed = False
        auto_allowed = False
    return {
        "fact_id": f"{industry_code}:{scene.get('id')}",
        "scene_fact_id": f"{industry_code}:{scene.get('id')}",
        "scene_id": scene.get("id", ""),
        "industry_code": industry_code,
        "scenario_scope": "industry_scene",
        "type": f"待核事实：{scene.get('name', '')}",
        "category": "行业场景待核事实",
        "domain": collaboration.get("lead", "行业经营事实域"),
        "level": risk_level,
        "score": min(10, max_obs_score),
        "total_score": total_obs_score,
        "priority": "按观察信号、资料门槛和法定程序人工排序",
        "detail": detail or doubt.get("observed_signal", ""),
        "description": doubt.get("target_fact", ""),
        "finding_status": finding_status,
        "conclusion_state": status,
        "conclusion_scope": "scene_fact_investigation_only",
        "required_human_review": required_review,
        "automatic_determination_allowed": auto_allowed,
        "report_release_allowed": release_allowed,
        "release_status": "草稿_待人工复核（证据充分，走快速复核通道）" if finding_status == "strong_evidence_pending_human_confirmation" else "草稿_待人工复核",
        "policy_validity": "待按事实期间、地区、纳税人身份、交易性质和程序阶段核验",
        "tax_impact": "尚未形成税费影响结论；政策时效、事实要件和金额底稿完成前不得测算确定税额。",
        "taxes": list(scene.get("taxes", [])),
        "target_fact": doubt.get("target_fact", ""),
        "observed_signal": doubt.get("observed_signal", ""),
        "must_exclude": list(doubt.get("must_exclude", [])),
        "observations": observed,
        "observed_metrics": _merge_observed_metrics(observed),
        "independent_sources": source_families,
        "independent_source_count": len(source_families),
        "source_files": copy.deepcopy(file_inventory),
        "source_gates": copy.deepcopy(gates),
        "missing_source_gates": missing_gates,
        "investigation_start": clue.get("start", ""),
        "investigation_steps": steps,
        "investigation_terminal": clue.get("terminal", ""),
        "supporting_evidence": [
            {"source": item, "status": "待取得、回查并评价真实性关联性合法性"}
            for item in evidence.get("supporting_sources", [])
        ],
        "opposing_evidence": [
            {"source": item, "status": "待使用与支持证据相同标准核验"}
            for item in evidence.get("opposing_sources", [])
        ],
        "reasonable_explanations": list(analysis.get("alternatives", [])),
        "insufficient_when": list(evidence.get("insufficient_when", [])),
        "evidence_quality_checks": list(evidence.get("quality_checks", [])),
        "analysis_proposition": analysis.get("proposition", ""),
        "analysis_plan": list(analysis.get("reasoning", [])),
        "conclusion_ladder": list(analysis.get("conclusion_ladder", [])),
        "tax_boundary": analysis.get("tax_boundary", ""),
        "domain_collaboration": copy.deepcopy(collaboration),
        "policy_applicability": copy.deepcopy(policy),
        "report_contract": copy.deepcopy(scene.get("report_contract", {})),
        "acceptance_passed": acceptance.get("passed", False),
        "acceptance_case_count": acceptance.get("acceptance_case_count", 0),
        "suggestion": "；".join(item.get("action", "") for item in steps[:4] if item.get("action")),
        "methodology_controls": {
            "signal_is_not_evidence": True,
            "missing_data_is_not_violation": True,
            "supporting_and_opposing_evidence_same_standard": True,
            "policy_verification_required": True,
            "amount_and_legal_characterisation_separate": True,
        },
        "_scenario_governed": True,
        "_canonical_scenario_output": True,
    }


def _domain_summary(findings):
    grouped = defaultdict(list)
    for finding in findings:
        grouped[finding.get("domain", "待核事实")].append(finding)
    return [
        {
            "domain": domain,
            "count": len(items),
            "high": 0,
            "mid": 0,
            "status": "待人工复核",
            "findings": items,
        }
        for domain, items in sorted(grouped.items())
    ]


def execute_scenario_methodology(industry, file_results=None, engine_data=None):
    """以原子观察事实驱动共同事实门和适用行业场景。"""
    engine_data = engine_data or {}
    atomic = run_verified_rules(engine_data)
    raw_observations = atomic.get("findings", [])
    observations = [copy.deepcopy(item) for item in raw_observations if _trusted_observation(item)]
    rejected = len(raw_observations) - len(observations)
    industry_code = resolve_industry_code(industry)
    available_families, observed_file_types = _available_source_families(file_results)
    file_inventory = _file_inventory(file_results)
    quality_issues = _quality_issues(observations)
    scenes = []
    mapped = {}
    unmapped = []
    scene_assessments = []
    industry_findings = []
    represented_rule_ids = set()
    review_plan = build_scenario_review_plan(industry, file_results=file_results, findings=observations)
    if industry_code:
        contract = load_industry_contract(industry_code)
        scenes = contract.get("scenarios", [])
        mapped, unmapped = _map_observations_to_scenes(observations, scenes)
        for scene in scenes:
            scene_id = scene.get("id", "")
            gates = _gate_results(scene, available_families, quality_issues)
            status = _status_from_gates(gates)
            scene_observations = mapped.get(scene_id, [])
            assessment = {
                "scene_id": scene_id,
                "name": scene.get("name", ""),
                "applicability_status": "待结合实际经营活动人工确认",
                "source_status": status,
                "source_gates": gates,
                "observation_count": len(scene_observations),
                "target_fact": (scene.get("doubt") or {}).get("target_fact", ""),
                "lead_domain": (scene.get("domain_collaboration") or {}).get("lead", ""),
                "report_release_allowed": False,
            }
            scene_assessments.append(assessment)
            if scene_observations and status != "资料不足_未启动":
                # ═══ 行业门禁：研发场景仅适用于确有研发活动的企业 ═══
                lead_domain = (scene.get("domain_collaboration") or {}).get("lead", "")
                scene_id = scene.get("id", "")
                if "研发" in lead_domain or "研发" in scene_id:
                    # 双重验证：行业匹配 + 实际研发信号
                    industry_text = str(industry or "").lower()
                    tech_kw = ["科技", "技术", "软件", "信息", "医药", "电子", "新能源", "互联网"]
                    is_tech = any(k in industry_text for k in tech_kw)
                    # 检查是否有研发辅助账或研发事项的实际数据
                    has_rd_data = bool(engine_data and (engine_data.get("rd_data") or {}).get("projects")) if engine_data else False
                    if not is_tech and not has_rd_data:
                        scene_assessments[-1]["applicability_status"] = "行业不适用：非科技/制造/IT行业且无研发辅助账"
                        continue
                industry_findings.append(
                    _industry_finding(
                        industry_code,
                        scene,
                        scene_observations,
                        gates,
                        file_inventory,
                    )
                )
                represented_rule_ids.update(item.get("rule_id") for item in scene_observations)

    # 同一原子观察已经进入行业场景时，不再在共同事实门重复展示；资料质量
    # 观察和无法可靠映射到行业场景的观察仍由共同事实门承接。
    findings = []
    for contract_id, contract in COMMON_FACT_CONTRACTS.items():
        matched = [
            item for item in observations
            if item.get("rule_id") in contract["rule_ids"]
            and item.get("rule_id") not in represented_rule_ids
        ]
        if matched:
            findings.append(_common_finding(contract_id, contract, matched, file_inventory))
    findings.extend(industry_findings)

    findings = sorted(
        findings,
        key=lambda item: (
            0 if item.get("scenario_scope") == "common_fact_gate" else 1,
            str(item.get("scene_id", "")),
        ),
    )
    return {
        "version": EXECUTION_VERSION,
        "methodology_version": (review_plan or {}).get("version"),
        "executed_at": datetime.now().isoformat(),
        "governance_status": GOVERNANCE_STATUS,
        "industry_input": str(industry or ""),
        "industry_code": industry_code,
        "industry_resolved": bool(industry_code),
        "status": "待人工复核" if industry_code else "行业待人工确认",
        "decision_boundary": "原子计算只形成观察事实；共同事实门和行业场景只形成待核任务。未经证据、政策时效、金额底稿和有权人员审签，不得形成正式结论。",
        "atomic_rule_version": atomic.get("version"),
        "atomic_rule_count": atomic.get("catalog_count", 0),
        "atomic_executions": copy.deepcopy(atomic.get("executions", [])),
        "trusted_observation_count": len(observations),
        "rejected_observation_count": rejected,
        "available_source_families": available_families,
        "observed_file_types": observed_file_types,
        "source_quality_issues": quality_issues,
        "industry_scene_count": len(scenes),
        "industry_scenes_assessed": len(scene_assessments),
        "industry_scenes_with_observations": sum(bool(item["observation_count"]) for item in scene_assessments),
        "industry_scene_findings": sum(item.get("scenario_scope") == "industry_scene" for item in findings),
        "common_fact_findings": sum(item.get("scenario_scope") == "common_fact_gate" for item in findings),
        "unmapped_industry_observations": unmapped,
        "scenes": scene_assessments,
        "review_plan": review_plan,
        "findings": findings,
        "domain_summary": _domain_summary(findings),
        "report_release_allowed": False,
    }


def seal_scenario_findings(execution):
    """返回场景执行器的规范副本，阻止后续旧模块混入正式发现。"""
    if not isinstance(execution, dict) or execution.get("governance_status") != GOVERNANCE_STATUS:
        raise ValueError("缺少有效的场景执行结果")
    findings = execution.get("findings", [])
    if not isinstance(findings, list):
        raise ValueError("场景执行结果缺少规范待核事实")
    sealed = []
    identities = set()
    for item in findings:
        if not isinstance(item, dict) or item.get("_scenario_governed") is not True:
            continue
        identity = str(item.get("scene_fact_id") or item.get("fact_id") or "").strip()
        if not identity or identity in identities:
            continue
        identities.add(identity)
        canonical = copy.deepcopy(item)
        if canonical.get("conclusion_grade") == "已核定":
            # 两级结论：账面勾稽可核定事项——给出勾稽结论并允许进入报告，
            # 核定范围限于企业所报资料（推翻须更正资料本身），行政定性权仍在人工。
            # 2026-08-26 审计修复（P0-3）：统一政策——即使"已核定"勾稽事项也保留人工复核
            # 要求与不自动定性标志；进入报告不等于免除人工确认。
            # 【原实现备查（已停用）：required_human_review=False、
            #   automatic_determination_allowed=True、report_release_allowed=True】
            canonical["required_human_review"] = True
            canonical["automatic_determination_allowed"] = False
            canonical["report_release_allowed"] = True
            canonical["release_status"] = "已核定_限于所报资料勾稽_待人工确认"
        else:
            canonical["required_human_review"] = True
            canonical["automatic_determination_allowed"] = False
            canonical["report_release_allowed"] = False
            canonical["release_status"] = "草稿_待人工复核"
        sealed.append(canonical)
    return sealed
