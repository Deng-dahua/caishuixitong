# -*- coding: utf-8 -*-
"""经过数据契约验证的原子筛查规则。

这里的规则只计算可复核的数据事实，不作违法定性。只有具备明确字段契约、
来源边界并通过回归测试的计算，才属于“可执行原子规则”。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from engine.audit_coverage import build_coverage_report, format_coverage_text

from engine.vat_reversal import classify_input_tax_reversal


VERIFIED_RULE_CATALOG = [
    {
        "id": "VR001",
        "name": "银行收款与销项开票金额月度差异",
        "layer": "通用基础规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["销售与收入确认", "收付款与资金结算", "开票、红冲与用途确认"],
        "required_sources": ["bank_txs", "sal_invs"],
        "status": "verified_executable_screening",
        "limitation": "收款不等于应税收入，开票也不等于申报收入；必须复核借款、资本往来、代收代付、预收款、退款和跨期。",
    },
    {
        "id": "VR002",
        "name": "会计收入与销项开票金额月度差异",
        "layer": "通用基础规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["会计核算与期末结转", "销售与收入确认", "开票、红冲与用途确认"],
        "required_sources": ["vouchers", "sal_invs"],
        "status": "verified_executable_screening",
        "limitation": "税会确认时点、含税口径、价外费用、不开票收入和非增值税收入须分别复核。",
    },
    {
        "id": "VR003",
        "name": "销项发票号码重复记录",
        "layer": "数据质量与发票规则",
        "industries": ["ALL"],
        "taxes": ["增值税"],
        "lifecycle": ["开票、红冲与用途确认"],
        "required_sources": ["sal_invs"],
        "status": "verified_executable_screening",
        "limitation": "优先排除重复上传、多行商品明细和解析拆分，不能仅凭重复记录推断重复开票。",
    },
    {
        "id": "VR004",
        "name": "进项发票号码重复记录",
        "layer": "数据质量与发票规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["采购与取得", "开票、红冲与用途确认"],
        "required_sources": ["pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "优先排除重复上传、多行商品明细和解析拆分，抵扣状态仍须以合法取得的数据核验。",
    },
    {
        "id": "VR005",
        "name": "工资名册与社会保险人员范围差异",
        "layer": "人员税费协同规则",
        "industries": ["ALL"],
        "taxes": ["个人所得税", "社会保险费"],
        "lifecycle": ["用工、薪酬与扣缴"],
        "required_sources": ["salaries", "social_security"],
        "status": "verified_executable_screening",
        "limitation": "劳务派遣、退休返聘、兼职、入离职月份、异地参保和非雇员劳务必须单独排除。",
    },
    {
        "id": "VR006",
        "name": "库存期末数量为负",
        "layer": "存货数据质量规则",
        "industries": ["A", "B", "C", "F", "G", "H", "Q"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["采购与取得", "生产、加工与服务交付", "存货、物流与资产", "销售与收入确认"],
        "required_sources": ["inventory"],
        "status": "verified_executable_screening",
        "limitation": "负库存可能来自单据时点、跨仓调拨、计量单位转换、在途和退货，首先属于账实及数据质量核验事项。",
    },
    {
        "id": "VR007",
        "name": "库存数量滚动关系不一致",
        "layer": "存货数据质量规则",
        "industries": ["A", "B", "C", "F", "G", "H", "Q"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["采购与取得", "生产、加工与服务交付", "存货、物流与资产", "销售与收入确认"],
        "required_sources": ["inventory"],
        "status": "verified_executable_screening",
        "limitation": "仅在期初、入库、出库和期末字段齐全时计算；合理损耗、盘盈盘亏和单位换算须另行核验。",
    },
    {
        "id": "VR008",
        "name": "同一凭证借贷不平",
        "layer": "会计数据质量规则",
        "industries": ["ALL"],
        "taxes": ["企业所得税", "增值税"],
        "lifecycle": ["会计核算与期末结转"],
        "required_sources": ["vouchers"],
        "status": "verified_executable_screening",
        "limitation": "只评价上传凭证数据的完整性；缺行、解析失败和外币折算应先于涉税判断排除。",
    },
    {
        "id": "VR009",
        "name": "银行流水余额滚动关系不一致",
        "layer": "资金数据质量规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税", "个人所得税"],
        "lifecycle": ["收付款与资金结算", "资料接收"],
        "required_sources": ["bank_txs"],
        "status": "verified_executable_screening",
        "limitation": "仅在同一账户、日期和余额字段可识别时计算；银行借贷方向、日内排序、币种和重复导出须先核对。",
    },
    {
        "id": "VR010",
        "name": "销项发票金额税额价税合计关系不一致",
        "layer": "发票数据质量规则",
        "industries": ["ALL"],
        "taxes": ["增值税"],
        "lifecycle": ["开票、红冲与用途确认", "资料接收"],
        "required_sources": ["sal_invs"],
        "status": "verified_executable_screening",
        "limitation": "只校验上传字段的算术关系；差额可能来自四舍五入、价税字段映射、红字行和多行票面拆分。",
    },
    {
        "id": "VR011",
        "name": "进项发票金额税额价税合计关系不一致",
        "layer": "发票数据质量规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["采购与取得", "开票、红冲与用途确认", "资料接收"],
        "required_sources": ["pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "只校验上传字段的算术关系；抵扣资格、交易真实性和税前扣除仍须单独核验。",
    },
    {
        "id": "VR012",
        "name": "同一交易对手同时出现在客户与供应商清单",
        "layer": "交易关系交叉规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["采购与取得", "销售与收入确认"],
        "required_sources": ["sal_invs", "pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "双向交易在返修、材料互供、平台结算和集团协同中可能正常；必须按合同、货物流、定价和资金净额核验。",
    },
    {
        "id": "VR013",
        "name": "同一资金对手方存在大额双向收付",
        "layer": "资金关系交叉规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税", "个人所得税"],
        "lifecycle": ["收付款与资金结算", "资本投入与融资"],
        "required_sources": ["bank_txs"],
        "status": "verified_executable_screening",
        "limitation": "双向收付可能来自退款、借还款、保证金、代收代付和正常双向贸易；单一资金来源只形成调查线索。",
    },
    {
        "id": "VR014",
        "name": "生产用能源消耗与制造业生产规模不匹配",
        "layer": "生产经营实质规则",
        "industries": ["A", "B", "C", "D"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["生产、加工与服务交付", "采购与取得"],
        "required_sources": ["pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "生产可能外包、外购或使用房东代收的自备能源；能源发票缺失也可能是资料未上传或归集口径不同，不能据此认定无真实生产。",
    },
    {
        "id": "VR015",
        "name": "进项发票品名缺失",
        "layer": "数据质量与发票规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["采购与取得", "资料接收"],
        "required_sources": ["pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "品名缺失可能来自字段映射、汇总导出或票面本身缺项，须回查原始票面后再判断业务性质。",
    },
    {
        "id": "VR016",
        "name": "供应商地域分布与跨省核验",
        "layer": "交易关系交叉规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["采购与取得"],
        "required_sources": ["pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "跨省采购在原料产地集中、大宗采购或集团协同中可能正常；须按合同、物流和实际交付核验业务真实性。",
    },
    {
        "id": "VR017",
        "name": "购销双方集中度核验",
        "layer": "交易关系交叉规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["采购与取得", "销售与收入确认"],
        "required_sources": ["sal_invs", "pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "集中度受行业和商业模式影响；定制生产、代工或单一核心客户模式下，少数客户或供应商占比较高可能正常。",
    },
    {
        "id": "VR018",
        "name": "增值税申报销售额与销项开票金额月度差异",
        "layer": "通用基础规则",
        "industries": ["ALL"],
        "taxes": ["增值税"],
        "lifecycle": ["开票、红冲与用途确认", "销售与收入确认", "税费申报与缴纳"],
        "required_sources": ["tax_declarations", "sal_invs"],
        "status": "verified_executable_screening",
        "limitation": "开票与申报存在时间性差异（纳税义务发生时间与开票时点）、未开票收入、红字发票和税率差异，须逐期复核后判断。",
    },
    {
        "id": "VR019",
        "name": "增值税申报进项税额与进项发票税额月度差异",
        "layer": "通用基础规则",
        "industries": ["ALL"],
        "taxes": ["增值税"],
        "lifecycle": ["采购与取得", "开票、红冲与用途确认", "税费申报与缴纳"],
        "required_sources": ["tax_declarations", "pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "认证抵扣时点与取得发票时点、进项转出、留抵和农产品加计抵扣存在时间差异，须逐期复核。",
    },
    {
        "id": "VR020",
        "name": "六员个人账户与经营资金往来核验",
        "layer": "交易关系交叉规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税", "个人所得税"],
        "lifecycle": ["收付款与资金结算", "资本投入与融资"],
        "required_sources": ["bank_txs"],
        "status": "verified_executable_screening",
        "limitation": "法定代表人、股东、董事等六员个人账户可能与公司存在借款、代垫、报销等正常往来；须逐笔核验款项性质后再判断是否涉及资金回流或隐匿收入。",
    },
    {
        "id": "VR021",
        "name": "供应商与客户名称近似核验",
        "layer": "交易关系交叉规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["采购与取得", "销售与收入确认"],
        "required_sources": ["sal_invs", "pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "名称近似可能来自集团关联企业、同一字号的分设购销公司或巧合；须结合股权、注册地址、人员重叠核验是否构成关联交易或闭环开票。",
    },
    {
        "id": "VR022",
        "name": "用工人数与收入规模核验",
        "layer": "生产经营实质规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税", "个人所得税"],
        "lifecycle": ["用工、薪酬与扣缴", "销售与收入确认"],
        "required_sources": ["sal_invs"],
        "status": "verified_executable_screening",
        "limitation": "人均产值受行业、外包、临时用工和季节性影响；异常偏高可能虚开或空壳，异常偏低可能隐匿收入或挂靠，须结合工资和社保明细逐人核验。",
    },
    {
        "id": "VR023",
        "name": "进销物耗投入产出比核验",
        "layer": "生产经营实质规则",
        "industries": ["A", "B", "C", "D", "F", "G", "H", "Q"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["采购与取得", "生产、加工与服务交付", "销售与收入确认"],
        "required_sources": ["sal_invs", "pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "加价倍数受产品结构、增值环节和存货周期影响；异常偏高可能虚开或空壳，购销倒挂可能隐匿收入或虚抵进项，须结合BOM、存货和产能核验。",
    },
    {
        "id": "VR024",
        "name": "个人或个体工商户供应商客户交易核验",
        "layer": "交易关系交叉规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税", "个人所得税"],
        "lifecycle": ["采购与取得", "销售与收入确认"],
        "required_sources": ["sal_invs", "pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "个人或个体户供应商在农产品收购、劳务、建材等行业可能正常；须核验交易真实性、是否代开发票及是否履行个税扣缴义务。",
    },
    {
        "id": "VR025",
        "name": "资金回流与公私混同检测",
        "layer": "资金关系交叉规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税", "个人所得税"],
        "lifecycle": ["收付款与资金结算", "资本投入与融资"],
        "required_sources": ["bank_txs"],
        "status": "verified_executable_screening",
        "limitation": "企业账户与个人账户的转存转取可能是股东借款、注资、代垫、分红等正常往来；须逐笔核验款项性质、是否履行扣缴义务，不能仅凭转账推断违法。",
    },
    {
        "id": "VR026",
        "name": "增值税税负率与行业区间偏离",
        "layer": "税负率与申报实质规则",
        "industries": ["ALL"],
        "taxes": ["增值税"],
        "lifecycle": ["税费申报与缴纳", "采购与取得", "销售与收入确认"],
        "required_sources": ["tax_declarations", "pur_invs", "sal_invs"],
        "status": "verified_executable_screening",
        "limitation": "税负率受进项结构、留抵、免税、简易计税、农产品加计抵扣和固定资产一次性抵扣影响；行业区间仅为参考，须结合进销项结构逐期解释，不能单凭偏离认定偷税（参考宁夏鑫海德案税负率0.1%被稽查）。",
    },
    {
        "id": "VR027",
        "name": "作废与红冲发票异常占比",
        "layer": "发票数据质量规则",
        "industries": ["ALL"],
        "taxes": ["增值税"],
        "lifecycle": ["开票、红冲与用途确认"],
        "required_sources": ["sal_invs", "pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "作废/红冲可能因开票错误、退货、折让正常发生；临近申报期集中作废、顶额作废或红冲后重新开具是隐匿收入或调节税基的高频信号，须逐票核验原交易是否真实履行。",
    },
    {
        "id": "VR028",
        "name": "银行收款显著大于销项开票（未开票收入隐匿线索）",
        "layer": "收入与申报协同规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["收付款与资金结算", "销售与收入确认", "开票、红冲与用途确认"],
        "required_sources": ["bank_txs", "sal_invs", "tax_declarations"],
        "status": "verified_executable_screening",
        "limitation": "收款大于开票可能源于预收款、借款、代收代付、关联往来、非应税收入或跨期；但长期、大额且无未开票收入申报时，是隐匿收入的典型线索（参考宁夏鑫海德、临潭盛渝案）。",
    },
    {
        "id": "VR029",
        "name": "长期零申报或申报数据异常",
        "layer": "税负率与申报实质规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税", "个人所得税"],
        "lifecycle": ["税费申报与缴纳"],
        "required_sources": ["tax_declarations"],
        "status": "verified_executable_screening",
        "limitation": "零申报在筹建期、停产期可能正常；但当银行流水、发票或工资显示持续经营却长期零申报，是空壳或账外经营的预警，须结合经营实质核对。",
    },
    {
        "id": "VR030",
        "name": "股东借款长期挂账与其他应收款异常",
        "layer": "资金关系交叉规则",
        "industries": ["ALL"],
        "taxes": ["个人所得税", "企业所得税", "增值税"],
        "lifecycle": ["资本投入与融资", "收付款与资金结算", "会计核算与期末结转"],
        "required_sources": ["bank_txs", "vouchers", "target_entity"],
        "status": "verified_executable_screening",
        "limitation": "其他应收款挂股东借款，在纳税年度内归还且用于经营的不视同分红；但跨年未还且无经营用途，依财税〔2003〕158号、国税发〔2005〕120号可视同红利分配按20%征个税，企业还需履行代扣代缴义务（金税四期重点筛查指标）。",
    },
    {
        "id": "VR031",
        "name": "印花税计税依据与购销金额勾稽",
        "layer": "税负率与申报实质规则",
        "industries": ["ALL"],
        "taxes": ["印花税"],
        "lifecycle": ["税费申报与缴纳", "采购与取得", "销售与收入确认"],
        "required_sources": ["sal_invs", "pur_invs", "tax_declarations"],
        "status": "verified_executable_screening",
        "limitation": "购销合同印花税计税依据通常不低于购销金额合计；未申报或明显偏低须核是否享受小微企业免征、是否仅按部分合同申报，不能单凭差额认定漏报（金税四期利润表与申报失真比对漏洞之一）。",
    },
    {
        "id": "VR032",
        "name": "进项税额应转出未转出",
        "layer": "增值税抵扣规则",
        "industries": ["ALL"],
        "taxes": ["增值税"],
        "lifecycle": ["采购与付款", "税费计提与申报"],
        "required_sources": ["pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "用途判定依赖发票品名/摘要关键词，存在上下文误判可能（如餐饮业料酒、酒厂原酒、化工厂酒精属生产原料可抵扣）。须逐张核对用途与对应成本费用科目，结合企业画像豁免后处理（依据增值税法第十条、财税〔2016〕36号）。",
    },
    {
        "id": "VR033",
        "name": "进销品名背离（变名开票）",
        "layer": "发票真实性规则",
        "industries": ["ALL"],
        "taxes": ["增值税"],
        "lifecycle": ["采购与付款", "销售与收款"],
        "required_sources": ["sal_invs", "pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "购进原料、销售成品本就存在合理品名差异（如棉纱→针织布）；只有背离跨越明显不同商品大类、且伴随资金回流/异常才是变名虚开线索。须结合生产工艺与BOM判断。",
    },
    {
        "id": "VR034",
        "name": "成本费用虚列异常",
        "layer": "成本费用真实性规则",
        "industries": ["ALL"],
        "taxes": ["企业所得税"],
        "lifecycle": ["采购与付款", "费用报销"],
        "required_sources": ["vouchers"],
        "status": "verified_executable_screening",
        "limitation": "大额咨询/会议/广告/服务费及现金支出可能是真实经营需要；费用率高于同业可能源于商业模式差异。须逐笔核验合同、成果物、付款对象与现金去向。",
    },
    {
        "id": "VR035",
        "name": "印花税其他税目漏报",
        "layer": "申报与勾稽规则",
        "industries": ["ALL"],
        "taxes": ["印花税"],
        "lifecycle": ["税费计提与申报", "融资与借款", "资产租赁"],
        "required_sources": ["bank_txs", "vouchers", "tax_declarations"],
        "status": "verified_executable_screening",
        "limitation": "借款合同、租赁合同的印花税计税依据与购销不同口径；部分情形（如金融机构借款合同、小微免征）有免税规定。须逐税目核对贴花情况。",
    },
    {
        "id": "VR036",
        "name": "视同销售未计提销项税额",
        "layer": "税会差异与特殊交易规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["销售与收入确认", "资产领用与用途改变", "费用报销与税前扣除"],
        "required_sources": ["sal_invs", "vouchers", "pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "无偿赠送、样品、自产自用、用于集体福利或个人消费的资产移转须视同销售计提销项；凭证明细不足时仅能给出线索，最终以用途与计税依据为准。",
    },
    {
        "id": "VR037",
        "name": "关联交易价格偏离（转让定价探针）",
        "layer": "关联交易与转让定价规则",
        "industries": ["ALL"],
        "taxes": ["增值税", "企业所得税"],
        "lifecycle": ["销售与收入确认", "采购与付款", "关联方交易"],
        "required_sources": ["sal_invs", "pur_invs"],
        "status": "verified_executable_screening",
        "limitation": "转让定价需以独立交易原则(ARM'S LENGTH)比对，权威判定依赖工商股权穿透(关联方识别)与同期资料。本规则仅以'同一品名同单位对不同交易对象的单价离散度'做定量探针，关联定性需补充股权穿透数据。",
    },
    {
        "id": "VR038",
        "name": "业务招待费扣除超限未纳税调整",
        "layer": "成本费用真实性规则",
        "industries": ["ALL"],
        "taxes": ["企业所得税"],
        "lifecycle": ["成本费用归集", "纳税调整"],
        "required_sources": ["vouchers", "declaration"],
        "status": "verified_executable_screening",
        "limitation": "业务招待费按发生额的60%扣除，且最高不得超过当年销售(营业)收入的5‰，超出部分须作纳税调增。本规则据凭证归集招待费并比对收入限额，未做纳税调整即预警。",
    },
    {
        "id": "VR039",
        "name": "广告费和业务宣传费扣除超限未纳税调整",
        "layer": "成本费用真实性规则",
        "industries": ["ALL"],
        "taxes": ["企业所得税"],
        "lifecycle": ["成本费用归集", "纳税调整"],
        "required_sources": ["vouchers", "declaration"],
        "status": "verified_executable_screening",
        "limitation": "广告费和业务宣传费不超过当年销售(营业)收入15%的部分准予扣除，超过部分准予在以后纳税年度结转。本规则据凭证归集并比对收入限额。",
    },
    {
        "id": "VR040",
        "name": "职工福利费扣除超限未纳税调整",
        "layer": "成本费用真实性规则",
        "industries": ["ALL"],
        "taxes": ["企业所得税"],
        "lifecycle": ["成本费用归集", "纳税调整"],
        "required_sources": ["vouchers", "declaration"],
        "status": "verified_executable_screening",
        "limitation": "职工福利费不超过工资薪金总额14%的部分准予扣除，超出须纳税调增。本规则据凭证归集福利费并比对工资总额限额。",
    },
    {
        "id": "VR041",
        "name": "折旧摊销与长期待摊异常（加速/遗漏）",
        "layer": "成本费用真实性规则",
        "industries": ["ALL"],
        "taxes": ["企业所得税"],
        "lifecycle": ["资产购置", "成本费用归集", "纳税调整"],
        "required_sources": ["vouchers", "fixed_assets"],
        "status": "verified_executable_screening",
        "limitation": "固定资产折旧、无形资产摊销、长期待摊费用须依税法最低年限计提，一次性税前扣除(如500万元以下设备器具)须符合政策规定。本规则筛查折旧/摊销凭证异常与实际资产变动背离。",
    },
    {
        "id": "VR042",
        "name": "房产税从价/从租计征勾稽",
        "layer": "财产税与行为税规则",
        "industries": ["ALL"],
        "taxes": ["房产税"],
        "lifecycle": ["资产持有", "成本费用归集", "纳税申报"],
        "required_sources": ["fixed_assets", "contracts", "declaration"],
        "status": "verified_executable_screening",
        "limitation": "自用房产从价计征=原值×(1-扣除比例)×1.2%；出租从租计征=租金收入×12%(个人住房4%)。免租期由产权人从价缴税。本规则据固定资产原值与租赁合同租金测算应缴，与申报勾稽。",
    },
    {
        "id": "VR043",
        "name": "城建税及教育费附加随增值税附征勾稽",
        "layer": "财产税与行为税规则",
        "industries": ["ALL"],
        "taxes": ["城建税", "教育费附加", "地方教育附加"],
        "lifecycle": ["纳税申报", "税款缴纳"],
        "required_sources": ["declaration"],
        "status": "verified_executable_screening",
        "limitation": "城建税=实缴增值税×7%(县城5%/乡村1%)，教育费附加3%，地方教育附加2%，随增值税附征。本规则以申报实缴增值税推算应缴附加，与附加税申报勾稽。",
    },
]


def _number(value, default=0.0):
    try:
        return float(value) if value not in (None, "", "None") else default
    except (TypeError, ValueError):
        return default


def _month(value):
    text = str(value or "").strip().replace("/", "-").replace(".", "-")
    if not text:
        return ""
    digits = "".join(character for character in text if character.isdigit())
    return digits[:6] if len(digits) >= 6 else ""


def _invoice_amount(row, pretax=False):
    if pretax:
        amount = _number(row.get("amount"))
        if amount:
            return amount
        return max(_number(row.get("total")) - _number(row.get("tax")), 0.0)
    total = _number(row.get("total"))
    return total if total else _number(row.get("amount")) + _number(row.get("tax"))


def _finding(spec, detail, metrics, sources, status="clue_pending_investigation", priority="中"):
    return {
        "type": spec["name"],
        "rule_id": spec["id"],
        "category": spec["layer"],
        "level": "信息" if status == "data_quality_limitation" else "中风险",
        "score": 2 if status == "data_quality_limitation" else 5,
        "priority": priority,
        "detail": detail,
        "observed_metrics": metrics,
        "finding_status": status,
        "rule_maturity": spec["status"],
        "conclusion_scope": "screening_and_review_only",
        "required_human_review": True,
        "independent_sources": list(sources),
        "independent_source_count": len(set(sources)),
        "source_lineage_status": "observed_from_uploaded_data",
        "limitations": spec["limitation"],
        "methodology_controls": {
            "applicability_review_required": True,
            "supporting_and_opposing_evidence_required": True,
            "amount_and_legal_characterisation_separate": True,
            "decision_boundary": "该原子规则只形成可复算的数据事实或资料质量事项，不作税务处理、处罚或移送判断。",
        },
    }


def _fmt_yuan(value):
    """金额格式化为千分位中文口径，用于 detail 中给出可回查明细。"""
    try:
        return f"{float(value):,.2f}元"
    except (TypeError, ValueError):
        return str(value)


def _monthly_amount(rows, value_fn, predicate=None):
    totals = defaultdict(float)
    for row in rows or []:
        if predicate and not predicate(row):
            continue
        month = _month(row.get("date") or row.get("invoice_date"))
        if month:
            totals[month] += value_fn(row)
    return totals


def _two_series_gap(left, right, ratio_threshold, amount_threshold):
    items = []
    for month in sorted(set(left) & set(right)):
        left_value, right_value = left[month], right[month]
        baseline = max(min(abs(left_value), abs(right_value)), 1.0)
        gap = left_value - right_value
        if abs(gap) >= amount_threshold and abs(gap) / baseline >= ratio_threshold:
            items.append({
                "month": month,
                "left": round(left_value, 2),
                "right": round(right_value, 2),
                "gap": round(gap, 2),
                "gap_ratio": round(abs(gap) / baseline, 4),
            })
    return items


def _scan_bank_invoice_gap(data, spec):
    bank = _monthly_amount(
        data.get("bank_txs", []),
        lambda row: _number(row.get("credit")),
        lambda row: _number(row.get("credit")) > 0,
    )
    invoices = _monthly_amount(data.get("sal_invs", []), _invoice_amount)
    gaps = _two_series_gap(bank, invoices, 0.25, 100000)
    if len(gaps) < 2:
        return []
    total_gap = sum(item["gap"] for item in gaps)
    return [_finding(
        spec,
        f"在{len(gaps)}个月中，银行贷方收款与销项发票价税合计的差异同时超过25%和10万元；累计方向性差额{total_gap:,.2f}元。该结果只说明两个数据口径需要逐月对账。",
        {"anomaly_months": gaps[:24], "directional_total_gap": round(total_gap, 2)},
        spec["required_sources"],
    )]


def _scan_voucher_invoice_gap(data, spec):
    def is_revenue(row):
        account = str(row.get("account_name") or row.get("account") or "")
        return "主营业务收入" in account or "其他业务收入" in account

    vouchers = _monthly_amount(
        data.get("vouchers", []),
        lambda row: _number(row.get("credit")),
        lambda row: is_revenue(row) and _number(row.get("credit")) > 0,
    )
    invoices = _monthly_amount(data.get("sal_invs", []), lambda row: _invoice_amount(row, pretax=True))
    gaps = _two_series_gap(vouchers, invoices, 0.15, 100000)
    if len(gaps) < 2:
        return []
    return [_finding(
        spec,
        f"在{len(gaps)}个月中，会计收入贷方发生额与销项发票不含税金额的差异同时超过15%和10万元，需要统一税会确认期间及金额口径。",
        {"anomaly_months": gaps[:24]},
        spec["required_sources"],
    )]


def _invoice_identity(row):
    code = str(row.get("inv_code") or row.get("invoice_code") or "").strip()
    number = str(
        row.get("inv_no") or row.get("invoice_no") or row.get("digital_invoice_no") or ""
    ).strip()
    return (code, number) if number else None


def _scan_duplicate_invoices(data, spec, source):
    groups = defaultdict(list)
    for index, row in enumerate(data.get(source, []) or []):
        identity = _invoice_identity(row)
        if identity:
            groups[identity].append(index + 1)
    duplicates = [
        {"invoice_code": key[0], "invoice_number": key[1], "rows": rows[:20]}
        for key, rows in groups.items() if len(rows) > 1
    ]
    if not duplicates:
        return []
    example_text = "；".join(
        f"发票号{d['invoice_number'] or d['invoice_code']}（出现{len(d['rows'])}次，第{'、'.join(str(r) for r in d['rows'][:4])}行）"
        for d in duplicates[:5]
    )
    return [_finding(
        spec,
        (f"上传资料中有{len(duplicates)}个发票号码出现多次，应先核对是否为重复上传、多行明细或解析拆分，再决定是否进入交易核验。"
         f"重复发票号举例：{example_text}。全部明细已留存于工作底稿，可逐笔回查。"),
        {"duplicate_invoice_count": len(duplicates), "examples": duplicates[:30]},
        [source],
        status="data_quality_limitation",
        priority="资料质量",
    )]


def _person_name(row):
    return str(row.get("name") or row.get("employee_name") or row.get("姓名") or "").strip()


def _scan_payroll_social(data, spec):
    salary_names = {_person_name(row) for row in data.get("salaries", []) or [] if _person_name(row)}
    social_names = {_person_name(row) for row in data.get("social_security", []) or [] if _person_name(row)}
    if len(salary_names) < 5 or len(social_names) < 5:
        return []
    only_salary = sorted(salary_names - social_names)
    only_social = sorted(social_names - salary_names)
    mismatch = len(only_salary) + len(only_social)
    denominator = max(len(salary_names | social_names), 1)
    if mismatch < 2 or mismatch / denominator < 0.2:
        return []
    example_text = (
        (f"仅在工资名册的人员举例：{'、'.join(only_salary[:5])}。" if only_salary else "")
        + (f"仅在社保清单的人员举例：{'、'.join(only_social[:5])}。" if only_social else "")
    )
    return [_finding(
        spec,
        (f"工资名册与社会保险人员清单共有{mismatch}人未能双向匹配，占合并人员范围的{mismatch / denominator:.1%}。该差异需要按人员身份和所属月份逐人解释。"
         + example_text),
        {
            "salary_only_count": len(only_salary),
            "social_only_count": len(only_social),
            "salary_only_examples": only_salary[:30],
            "social_only_examples": only_social[:30],
        },
        spec["required_sources"],
    )]


def _inventory_value(row, names):
    for name in names:
        if row.get(name) not in (None, ""):
            return _number(row.get(name)), True
    return 0.0, False


def _scan_negative_inventory(data, spec):
    items = []
    for index, row in enumerate(data.get("inventory", []) or []):
        ending, present = _inventory_value(row, ("end_qty", "ending_qty", "close_qty"))
        if present and ending < -0.000001:
            items.append({
                "row": index + 1,
                "code": str(row.get("code") or ""),
                "name": str(row.get("name") or ""),
                "end_qty": ending,
            })
    if not items:
        return []
    example_text = "；".join(
        f"{it['name'] or it['code'] or '第' + str(it['row']) + '行'}（期末数量{it['end_qty']:g}）"
        for it in items[:5]
    )
    return [_finding(
        spec,
        (f"进销存资料中有{len(items)}项期末数量为负，应先核对单据时点、跨仓调拨、单位换算和解析完整性。"
         f"涉及品项：{example_text}。"),
        {"negative_items": items[:50], "negative_count": len(items)},
        spec["required_sources"],
        status="data_quality_limitation",
        priority="资料质量",
    )]


def _scan_inventory_rollforward(data, spec):
    mismatches, comparable = [], 0
    for index, row in enumerate(data.get("inventory", []) or []):
        opening, has_open = _inventory_value(row, ("open_qty", "begin_qty", "opening_qty"))
        incoming, has_in = _inventory_value(row, ("in_qty", "incoming_qty", "purchase_qty"))
        outgoing, has_out = _inventory_value(row, ("out_qty", "outgoing_qty", "sales_qty"))
        ending, has_end = _inventory_value(row, ("end_qty", "ending_qty", "close_qty"))
        if not all((has_open, has_in, has_out, has_end)):
            continue
        comparable += 1
        expected = opening + incoming - outgoing
        difference = ending - expected
        tolerance = max(0.01, abs(ending) * 0.01)
        if abs(difference) > tolerance:
            mismatches.append({
                "row": index + 1,
                "code": str(row.get("code") or ""),
                "name": str(row.get("name") or ""),
                "expected_end_qty": round(expected, 6),
                "reported_end_qty": round(ending, 6),
                "difference": round(difference, 6),
            })
    if comparable < 3 or not mismatches:
        return []
    example_text = "；".join(
        f"{m['name'] or m['code'] or '第' + str(m['row']) + '行'}（期初＋入库－出库应为{m['expected_end_qty']:g}，账面期末为{m['reported_end_qty']:g}，差{m['difference']:+g}）"
        for m in mismatches[:5]
    )
    return [_finding(
        spec,
        (f"{comparable}项具有完整数量字段的存货中，{len(mismatches)}项不满足“期初＋入库－出库＝期末”的滚动关系。"
         f"涉及品项：{example_text}。"),
        {"comparable_count": comparable, "mismatch_count": len(mismatches), "examples": mismatches[:50]},
        spec["required_sources"],
        status="data_quality_limitation",
        priority="资料质量",
    )]


def _scan_voucher_balance(data, spec):
    groups = defaultdict(lambda: {"debit": 0.0, "credit": 0.0, "rows": []})
    for index, row in enumerate(data.get("vouchers", []) or []):
        number = str(row.get("voucher_no") or "").strip()
        if not number:
            continue
        key = (_month(row.get("date")), number)
        groups[key]["debit"] += _number(row.get("debit"))
        groups[key]["credit"] += _number(row.get("credit"))
        groups[key]["rows"].append(index + 1)
    mismatches = []
    for (month, number), values in groups.items():
        difference = values["debit"] - values["credit"]
        if abs(difference) > 1:
            mismatches.append({
                "month": month,
                "voucher_no": number,
                "debit": round(values["debit"], 2),
                "credit": round(values["credit"], 2),
                "difference": round(difference, 2),
                "rows": values["rows"][:30],
            })
    if not mismatches:
        return []
    top = sorted(mismatches, key=lambda m: -abs(m["difference"]))[:3]
    example_text = "；".join(
        f"{m['month']}月{m['voucher_no']}号凭证：借方{_fmt_yuan(m['debit'])}、贷方{_fmt_yuan(m['credit'])}，差{_fmt_yuan(m['difference'])}"
        for m in top
    )
    return [_finding(
        spec,
        (f"按月份和凭证号汇总后，有{len(mismatches)}张凭证借贷差额超过1元；应优先检查上传是否缺行或解析失败。"
         f"差额最大的凭证：{example_text}。"),
        {"unbalanced_count": len(mismatches), "examples": mismatches[:50]},
        spec["required_sources"],
        status="data_quality_limitation",
        priority="资料质量",
    )]


def _scan_bank_balance_rollforward(data, spec):
    accounts = defaultdict(list)
    for index, row in enumerate(data.get("bank_txs", []) or []):
        if row.get("balance") in (None, ""):
            continue
        account = str(row.get("account") or row.get("account_no") or "未区分账户")
        accounts[account].append((str(row.get("date") or ""), index, row))
    mismatches, comparable = [], 0
    for account, rows in accounts.items():
        rows.sort(key=lambda item: (item[0], item[1]))
        for previous, current in zip(rows, rows[1:]):
            previous_balance = _number(previous[2].get("balance"))
            expected = previous_balance + _number(current[2].get("credit")) - _number(current[2].get("debit"))
            actual = _number(current[2].get("balance"))
            comparable += 1
            if abs(expected - actual) > 1:
                mismatches.append({
                    "account": account[-8:],
                    "date": current[0],
                    "expected_balance": round(expected, 2),
                    "reported_balance": round(actual, 2),
                    "difference": round(actual - expected, 2),
                })
    if comparable < 3 or not mismatches:
        return []
    top = sorted(mismatches, key=lambda m: -abs(m["difference"]))[:3]
    example_text = "；".join(
        f"账户尾号{m['account']}，{m['date']}，应为{_fmt_yuan(m['expected_balance'])}而账面为{_fmt_yuan(m['reported_balance'])}，差{_fmt_yuan(m['difference'])}"
        for m in top
    )
    return [_finding(
        spec,
        (f"在{comparable}组可比较的相邻流水中，有{len(mismatches)}组余额未按“上笔余额＋收入－支出”滚动。"
         f"差异最大的组别：{example_text}。全部{len(mismatches)}组差异明细已留存于工作底稿，可逐笔回查。"),
        {"comparable_count": comparable, "mismatch_count": len(mismatches), "examples": mismatches[:50]},
        spec["required_sources"],
        status="data_quality_limitation",
        priority="资料质量",
    )]


def _scan_invoice_arithmetic(data, spec, source):
    mismatches, comparable = [], 0
    for index, row in enumerate(data.get(source, []) or []):
        if any(row.get(field) in (None, "") for field in ("amount", "tax", "total")):
            continue
        comparable += 1
        amount, tax, total = _number(row.get("amount")), _number(row.get("tax")), _number(row.get("total"))
        difference = total - amount - tax
        if abs(difference) > 1:
            identity = _invoice_identity(row)
            mismatches.append({
                "row": index + 1,
                "invoice_number": identity[1] if identity else "",
                "amount": amount,
                "tax": tax,
                "total": total,
                "difference": round(difference, 2),
            })
    if comparable < 3 or not mismatches:
        return []
    top = sorted(mismatches, key=lambda m: -abs(m["difference"]))[:3]
    example_text = "；".join(
        f"{'发票号' + m['invoice_number'] if m['invoice_number'] else '第' + str(m['row']) + '行'}：金额{_fmt_yuan(m['amount'])}＋税额{_fmt_yuan(m['tax'])}≠价税合计{_fmt_yuan(m['total'])}，差{_fmt_yuan(m['difference'])}"
        for m in top
    )
    return [_finding(
        spec,
        (f"{comparable}条字段齐全的发票记录中，有{len(mismatches)}条不满足“金额＋税额＝价税合计”（容差1元）。"
         f"差异最大的记录：{example_text}。"),
        {"comparable_count": comparable, "mismatch_count": len(mismatches), "examples": mismatches[:50]},
        spec["required_sources"],
        status="data_quality_limitation",
        priority="资料质量",
    )]


def _normalise_party(value):
    text = str(value or "").strip().replace("（", "(").replace("）", ")")
    for suffix in ("有限责任公司", "股份有限公司", "有限公司", "公司"):
        if text.endswith(suffix):
            text = text[:-len(suffix)]
            break
    return "".join(character for character in text if character.isalnum()).lower()


def _scan_customer_supplier_overlap(data, spec):
    customers = defaultdict(set)
    suppliers = defaultdict(set)
    for row in data.get("sal_invs", []) or []:
        name = str(row.get("buyer") or "").strip()
        key = _normalise_party(name)
        if key:
            customers[key].add(name)
    for row in data.get("pur_invs", []) or []:
        name = str(row.get("seller") or "").strip()
        key = _normalise_party(name)
        if key:
            suppliers[key].add(name)
    overlaps = sorted(set(customers) & set(suppliers))
    if not overlaps:
        return []
    examples = [sorted(customers[key] | suppliers[key])[0] for key in overlaps[:50]]
    example_text = "、".join(examples[:5])
    return [_finding(
        spec,
        (f"进销项发票中有{len(overlaps)}个标准化交易对手名称同时出现在客户和供应商范围，应按业务合同和实际履约判断双向交易性质。"
         f"涉及的对手方举例：{example_text}。"),
        {"overlap_count": len(overlaps), "examples": examples},
        spec["required_sources"],
    )]


def _scan_bidirectional_bank(data, spec):
    parties = defaultdict(lambda: {"credit": 0.0, "debit": 0.0, "count": 0})
    for row in data.get("bank_txs", []) or []:
        party = str(row.get("counterparty") or "").strip()
        if not party:
            continue
        key = _normalise_party(party)
        parties[key]["credit"] += _number(row.get("credit"))
        parties[key]["debit"] += _number(row.get("debit"))
        parties[key]["count"] += 1
        parties[key]["name"] = party
    matches = []
    for values in parties.values():
        smaller, larger = min(values["credit"], values["debit"]), max(values["credit"], values["debit"])
        if smaller >= 100000 and larger and smaller / larger >= 0.2:
            matches.append({
                "counterparty": values["name"],
                "receipts": round(values["credit"], 2),
                "payments": round(values["debit"], 2),
                "transaction_count": values["count"],
            })
    if not matches:
        return []
    matches.sort(key=lambda item: -(item["receipts"] + item["payments"]))
    example_text = "；".join(
        f"{m['counterparty']}（累计收款{_fmt_yuan(m['receipts'])}、付款{_fmt_yuan(m['payments'])}，共{m['transaction_count']}笔）"
        for m in matches[:3]
    )
    return [_finding(
        spec,
        (f"有{len(matches)}个资金对手方同时存在累计不低于10万元的收款和付款，且较小方向达到较大方向的20%。"
         f"涉及的对手方：{example_text}。全部对手方累计收付明细已留存于工作底稿，可逐笔回查。"),
        {"counterparty_count": len(matches), "examples": matches[:50]},
        spec["required_sources"],
        priority="调查优先级",
    )]


_PROVINCE_CITIES = {
    "广东": ["广州", "深圳", "东莞", "中山", "佛山", "珠海", "惠州", "江门", "汕头", "湛江", "肇庆", "茂名", "梅州", "揭阳", "潮州", "清远", "河源", "阳江", "韶关", "云浮"],
    "山东": ["济南", "青岛", "淄博", "潍坊", "临沂", "烟台", "日照", "德州", "威海", "菏泽", "泰安", "济宁", "聊城", "滨州", "东营", "枣庄"],
    "江苏": ["南京", "苏州", "无锡", "常州", "南通", "徐州", "扬州", "盐城", "泰州", "镇江", "淮安", "连云港", "宿迁", "吴江", "盛泽", "常熟", "张家港", "江阴", "宜兴"],
    "浙江": ["杭州", "宁波", "温州", "绍兴", "嘉兴", "湖州", "金华", "台州", "衢州", "丽水", "舟山"],
    "福建": ["福州", "厦门", "泉州", "漳州", "莆田", "三明", "南平", "龙岩", "宁德"],
    "上海": ["上海"], "北京": ["北京"], "天津": ["天津"], "重庆": ["重庆"],
    "河北": ["石家庄", "唐山", "秦皇岛", "邯郸", "邢台", "保定", "张家口", "承德", "沧州", "廊坊", "衡水"],
    "河南": ["郑州", "开封", "洛阳", "平顶山", "安阳", "新乡", "焦作", "许昌", "漯河", "南阳", "商丘", "信阳", "周口", "驻马店", "濮阳", "三门峡", "鹤壁", "济源", "鄢陵", "长葛", "禹州", "襄城"],
    "湖北": ["武汉", "黄石", "宜昌", "襄阳", "鄂州", "荆门", "孝感", "荆州", "黄冈", "咸宁", "十堰", "随州", "恩施", "宜城", "枣阳", "老河口", "仙桃", "潜江", "天门"],
    "湖南": ["长沙", "株洲", "湘潭", "衡阳", "邵阳", "岳阳", "常德", "益阳", "郴州", "永州", "怀化", "娄底"],
    "四川": ["成都", "自贡", "泸州", "德阳", "绵阳", "广元", "遂宁", "内江", "乐山", "南充", "眉山", "宜宾", "达州"],
    "安徽": ["合肥", "芜湖", "蚌埠", "淮南", "马鞍山", "铜陵", "安庆", "黄山", "滁州", "阜阳", "宿州", "六安", "宣城", "亳州", "池州"],
    "江西": ["南昌", "景德镇", "萍乡", "九江", "新余", "赣州", "吉安", "宜春", "抚州", "上饶"],
    "辽宁": ["沈阳", "大连", "鞍山", "抚顺", "本溪", "丹东", "锦州", "营口", "盘锦", "辽阳", "铁岭"],
    "陕西": ["西安", "铜川", "宝鸡", "咸阳", "渭南", "延安", "汉中", "榆林", "安康", "商洛"],
    "广西": ["南宁", "柳州", "桂林", "梧州", "北海", "钦州", "贵港", "玉林", "百色", "河池"],
    "云南": ["昆明", "曲靖", "玉溪", "保山", "昭通", "丽江", "普洱", "临沧", "大理", "红河"],
    "贵州": ["贵阳", "六盘水", "遵义", "安顺", "毕节", "铜仁", "黔南", "黔东南"],
    "山西": ["太原", "大同", "阳泉", "长治", "晋城", "晋中", "运城", "忻州", "临汾", "吕梁"],
    "黑龙江": ["哈尔滨", "齐齐哈尔", "大庆", "佳木斯", "牡丹江", "绥化"],
    "吉林": ["长春", "吉林", "四平", "通化", "白山", "松原", "延边"],
    "甘肃": ["兰州", "天水", "武威", "张掖", "平凉", "酒泉", "庆阳", "陇南"],
    "内蒙古": ["呼和浩特", "包头", "赤峰", "通辽", "鄂尔多斯", "呼伦贝尔"],
    "新疆": ["乌鲁木齐", "克拉玛依", "吐鲁番", "哈密", "昌吉", "巴音郭楞"],
    "海南": ["海口", "三亚", "儋州", "琼海"],
    "宁夏": ["银川", "石嘴山", "吴忠", "固原", "中卫"],
    "青海": ["西宁", "海东", "海西"],
    "西藏": ["拉萨", "日喀则", "昌都", "林芝"],
}


def _province_of(text):
    text = str(text or "")
    for province, cities in _PROVINCE_CITIES.items():
        if province in text or any(city in text for city in cities):
            return province
    return None


def _invoice_goods_text(row):
    return str(row.get("goods") or row.get("货物或应税劳务名称") or row.get("品名") or "").strip()


def _scan_production_energy(data, spec):
    pur = data.get("pur_invs", []) or []
    if not pur:
        return []
    energy_keywords = ["电费", "水费", "燃气", "天然气", "蒸汽", "热能", "供热", "供电", "供水", "电力"]
    vehicle_keywords = ["汽油", "柴油", "车用", "加油", "充电桩", "充电"]
    raw_material_keywords = ["纱", "布", "棉", "氨纶", "纤维", "坯布", "面料", "针织", "梭织", "染整",
                             "原料", "钢材", "钢板", "铝", "铜", "铁", "塑料", "化工", "粮食", "木材",
                             "石材", "水泥", "矿产", "原油", "煤炭", "纸浆", "浆粕", "化工原料", "颗粒"]
    raw_material_amount = 0.0
    energy_amount = 0.0
    energy_count = 0
    for row in pur:
        goods = _invoice_goods_text(row)
        if not goods:
            continue
        if any(key in goods for key in vehicle_keywords):
            continue
        amount = _number(row.get("amount"))
        if any(key in goods for key in raw_material_keywords):
            raw_material_amount += amount
        if any(key in goods for key in energy_keywords):
            energy_amount += amount
            energy_count += 1
    # 仅当存在明显原材料/生产物资采购时，才按制造业口径核验能源消耗，避免贸易企业误触发
    if raw_material_amount >= 1000000 and energy_amount < raw_material_amount * 0.001:
        return [_finding(
            spec,
            f"进项发票中原材料及生产物资采购{raw_material_amount:,.0f}元，但未识别到生产用能源（电/水/燃气/蒸汽）发票（能源发票{energy_count}张、{energy_amount:,.0f}元），能源消耗与生产规模不匹配，须核验生产场地、设备及实际生产实质。",
            {
                "raw_material_amount": round(raw_material_amount, 2),
                "production_energy_amount": round(energy_amount, 2),
                "production_energy_invoice_count": energy_count,
            },
            spec["required_sources"],
            priority="调查优先级",
        )]
    return []


def _scan_invoice_goods_missing(data, spec):
    pur = data.get("pur_invs", []) or []
    if not pur:
        return []
    missing = [row for row in pur if not _invoice_goods_text(row)]
    missing_amount = sum(_number(row.get("amount")) for row in missing)
    if missing and (len(missing) >= 30 or missing_amount >= 500000):
        return [_finding(
            spec,
            f"进项发票中有{len(missing)}张品名为空，合计金额{missing_amount:,.2f}元，无法识别购进业务性质，须回查原始票面并补充品名后再进入交易核验。",
            {"missing_count": len(missing), "missing_amount": round(missing_amount, 2), "total_count": len(pur)},
            spec["required_sources"],
        )]
    return []


def _scan_supplier_geo(data, spec):
    pur = data.get("pur_invs", []) or []
    if not pur:
        return []
    suppliers = defaultdict(lambda: {"amount": 0.0, "count": 0, "province": None})
    for row in pur:
        name = str(row.get("seller") or row.get("销方名称") or "").strip()
        if not name:
            continue
        entry = suppliers[name]
        entry["amount"] += _number(row.get("amount"))
        entry["count"] += 1
        if entry["province"] is None:
            entry["province"] = _province_of(name)
    if len(suppliers) < 3:
        return []
    provinces = defaultdict(lambda: {"amount": 0.0, "count": 0})
    for name, entry in suppliers.items():
        province = entry["province"] or "未知"
        provinces[province]["amount"] += entry["amount"]
        provinces[province]["count"] += 1
    cross_province = [p for p in provinces if p != "未知"]
    if len(cross_province) < 2:
        return []
    total_amount = sum(entry["amount"] for entry in suppliers.values())
    top_provinces = sorted(provinces.items(), key=lambda item: -item[1]["amount"])
    detail_parts = []
    for province, agg in top_provinces[:5]:
        ratio = (agg["amount"] / total_amount * 100) if total_amount else 0
        detail_parts.append(f"{province}{agg['count']}家{agg['amount']:,.0f}元({ratio:.0f}%)")
    return [_finding(
        spec,
        f"进项发票供应商分布在{len(cross_province)}个省份，前几大采购来源地：" + "、".join(detail_parts) + "。跨省分散采购须核验各供应商资质、合同、物流和实际交付，识别是否存在无实质交易的票据流转。",
        {
            "supplier_count": len(suppliers),
            "province_count": len(cross_province),
            "province_breakdown": {p: {"count": v["count"], "amount": round(v["amount"], 2)} for p, v in top_provinces[:8]},
        },
        spec["required_sources"],
        priority="调查优先级",
    )]


def _scan_concentration(data, spec):
    sal = data.get("sal_invs", []) or []
    pur = data.get("pur_invs", []) or []
    suppliers = defaultdict(float)
    customers = defaultdict(float)
    for row in pur:
        name = str(row.get("seller") or row.get("销方名称") or "").strip()
        if name:
            suppliers[name] += _number(row.get("amount"))
    for row in sal:
        name = str(row.get("buyer") or row.get("购方名称") or "").strip()
        if name:
            customers[name] += _number(row.get("amount"))
    supplier_total = sum(suppliers.values())
    customer_total = sum(customers.values())
    top3_supplier = sum(sorted(suppliers.values(), reverse=True)[:3])
    top3_customer = sum(sorted(customers.values(), reverse=True)[:3])
    supplier_ratio = (top3_supplier / supplier_total) if supplier_total else 0.0
    customer_ratio = (top3_customer / customer_total) if customer_total else 0.0
    signals = []
    if supplier_total > 0 and len(suppliers) >= 3 and supplier_ratio >= 0.8:
        top_supplier = max(suppliers, key=suppliers.get)
        signals.append(f"前3大供应商占采购额{supplier_ratio*100:.1f}%（最大供应商{top_supplier}）")
    if customer_total > 0 and len(customers) >= 3 and customer_ratio >= 0.8:
        top_customer = max(customers, key=customers.get)
        signals.append(f"前3大客户占销售额{customer_ratio*100:.1f}%（最大客户{top_customer}）")
    if not signals:
        return []
    return [_finding(
        spec,
        "；".join(signals) + "。购销集中度偏高，须核验交易真实性、定价独立性、是否存在关联关系或对单一渠道的异常依赖。",
        {
            "supplier_count": len(suppliers),
            "customer_count": len(customers),
            "supplier_top3_ratio": round(supplier_ratio, 4),
            "customer_top3_ratio": round(customer_ratio, 4),
        },
        spec["required_sources"],
        priority="调查优先级",
    )]


def _declaration_month(value):
    text = str(value or "").strip().replace("/", "-").replace(".", "-").replace("年", "-").replace("月", "")
    if not text:
        return ""
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits[:6] if len(digits) >= 6 else ""


def _scan_vat_declaration_sales_gap(data, spec):
    decls = data.get("tax_declarations", []) or []
    sal = data.get("sal_invs", []) or []
    decl_by_month = defaultdict(float)
    for decl in decls:
        if not isinstance(decl, dict):
            continue
        sales = _number(decl.get("sales_amount"))
        if sales <= 0:
            continue
        month = _declaration_month(decl.get("period"))
        if month:
            decl_by_month[month] += sales
    if not decl_by_month:
        return []
    inv_by_month = defaultdict(float)
    for row in sal:
        month = _month(row.get("date") or row.get("invoice_date") or row.get("开票日期"))
        if month:
            inv_by_month[month] += _number(row.get("amount"))
    total_declared = sum(decl_by_month.values())
    total_invoice = sum(inv_by_month.get(m, 0.0) for m in decl_by_month)
    gap = total_declared - total_invoice
    gaps = []
    for m in sorted(decl_by_month):
        declared = decl_by_month[m]
        invoiced = inv_by_month.get(m, 0.0)
        g = declared - invoiced
        if declared > 0 and abs(g) > max(declared * 0.05, 10000):
            gaps.append({"month": m, "declared_sales": round(declared, 2), "invoice_sales": round(invoiced, 2), "gap": round(g, 2)})
    if not gaps:
        return []
    detail = f"增值税申报表销售额合计{total_declared:,.2f}元，同期销项发票金额合计{total_invoice:,.2f}元，差异{gap:,.2f}元，有{len(gaps)}个月度差异超过5%或1万元："
    detail += "；".join(f"{g['month']}申报{g['declared_sales']:,.0f}vs开票{g['invoice_sales']:,.0f}(差{g['gap']:,.0f})" for g in gaps[:6])
    return [_finding(
        spec,
        detail,
        {"declared_sales_total": round(total_declared, 2), "invoice_sales_total": round(total_invoice, 2), "gap_months": len(gaps), "gaps": gaps[:12]},
        spec["required_sources"],
        priority="调查优先级",
    )]


def _scan_vat_declaration_input_gap(data, spec):
    decls = data.get("tax_declarations", []) or []
    pur = data.get("pur_invs", []) or []
    decl_by_month = defaultdict(float)
    for decl in decls:
        if not isinstance(decl, dict):
            continue
        input_tax = _number(decl.get("input_tax"))
        if input_tax <= 0:
            continue
        month = _declaration_month(decl.get("period"))
        if month:
            decl_by_month[month] += input_tax
    if not decl_by_month:
        return []
    inv_tax_by_month = defaultdict(float)
    for row in pur:
        month = _month(row.get("date") or row.get("invoice_date") or row.get("开票日期"))
        if month:
            inv_tax_by_month[month] += _number(row.get("tax"))
    total_declared = sum(decl_by_month.values())
    total_invoice = sum(inv_tax_by_month.get(m, 0.0) for m in decl_by_month)
    gap = total_declared - total_invoice
    gaps = []
    for m in sorted(decl_by_month):
        declared = decl_by_month[m]
        invoiced = inv_tax_by_month.get(m, 0.0)
        g = declared - invoiced
        if declared > 0 and abs(g) > max(declared * 0.05, 5000):
            gaps.append({"month": m, "declared_input_tax": round(declared, 2), "invoice_input_tax": round(invoiced, 2), "gap": round(g, 2)})
    if not gaps:
        return []
    detail = f"增值税申报表进项税额合计{total_declared:,.2f}元，同期进项发票税额合计{total_invoice:,.2f}元，差异{gap:,.2f}元，有{len(gaps)}个月度差异超过5%或5千元："
    detail += "；".join(f"{g['month']}申报{g['declared_input_tax']:,.0f}vs发票{g['invoice_input_tax']:,.0f}(差{g['gap']:,.0f})" for g in gaps[:6])
    return [_finding(
        spec,
        detail,
        {"declared_input_tax_total": round(total_declared, 2), "invoice_input_tax_total": round(total_invoice, 2), "gap_months": len(gaps), "gaps": gaps[:12]},
        spec["required_sources"],
        priority="调查优先级",
    )]


def _collect_personnel(target_entity):
    """从 target_entity 提取六员姓名集合（法人/股东/董事/监事/财务/经理）。"""
    names = set()
    if not isinstance(target_entity, dict):
        return names
    for key in ("legal_person", "legal_representative"):
        value = target_entity.get(key)
        if value and str(value).strip():
            names.add(str(value).strip())
    for key in ("directors", "supervisors", "finance_contacts", "shareholders", "managers", "contacts"):
        value = target_entity.get(key)
        if isinstance(value, list):
            for item in value:
                name = item.get("name") if isinstance(item, dict) else item
                if name and str(name).strip():
                    names.add(str(name).strip())
    filtered = set()
    for name in names:
        if len(name) >= 2 and not any(suffix in name for suffix in ("有限公司", "公司", "集团", "厂", "店", "事务所")):
            filtered.add(name)
    return filtered


def _scan_personnel_fund_flow(data, spec):
    target_entity = data.get("target_entity", {})
    personnel = _collect_personnel(target_entity)
    if not personnel:
        return []
    bank = data.get("bank_txs", []) or []
    matches = defaultdict(lambda: {"credit": 0.0, "debit": 0.0, "count": 0})
    for row in bank:
        party = str(row.get("counterparty") or "").strip()
        if not party:
            continue
        for name in personnel:
            if name and name in party:
                matches[name]["credit"] += _number(row.get("credit"))
                matches[name]["debit"] += _number(row.get("debit"))
                matches[name]["count"] += 1
                break
    if not matches:
        return []
    total_amount = sum(agg["credit"] + agg["debit"] for agg in matches.values())
    if total_amount < 100000:
        return []
    detail_parts = []
    for name, agg in sorted(matches.items(), key=lambda item: -(item[1]["credit"] + item[1]["debit"])):
        detail_parts.append(f"{name}往来{agg['count']}笔(收{agg['credit']:,.0f}/付{agg['debit']:,.0f})")
    return [_finding(
        spec,
        f"法定代表人、股东、董事等六员个人账户出现在银行流水对手方：" + "、".join(detail_parts) + "。个人账户与公司经营资金往来须核验是否为代收代付、资金回流、隐匿收入或账外经营。",
        {
            "personnel_match_count": len(matches),
            "total_amount": round(total_amount, 2),
            "matches": {name: {"credit": round(agg["credit"], 2), "debit": round(agg["debit"], 2), "count": agg["count"]} for name, agg in sorted(matches.items(), key=lambda item: -(item[1]["credit"] + item[1]["debit"]))[:10]},
        },
        spec["required_sources"],
        priority="调查优先级",
    )]


def _core_entity_name(text):
    """提取企业名称核心字号：去掉企业形式后缀和常见行业后缀。"""
    text = str(text or "").strip()
    for suffix in ("有限责任公司", "股份有限公司", "有限公司", "公司", "集团", "厂", "店", "事务所"):
        if text.endswith(suffix):
            text = text[:-len(suffix)]
            break
    for keyword in ("纺织", "服装", "贸易", "实业", "科技", "制衣", "布业", "纱业", "氨纶", "纤维", "针织", "印染", "染整", "辅料", "面料"):
        if text.endswith(keyword):
            text = text[:-len(keyword)]
            break
    return text


def _scan_name_similarity(data, spec):
    sal = data.get("sal_invs", []) or []
    pur = data.get("pur_invs", []) or []
    customers = {}
    suppliers = {}
    for row in sal:
        name = str(row.get("buyer") or "").strip()
        key = _normalise_party(name)
        if key and len(key) >= 4:
            customers[key] = name
    for row in pur:
        name = str(row.get("seller") or "").strip()
        key = _normalise_party(name)
        if key and len(key) >= 4:
            suppliers[key] = name
    similar_pairs = []
    for skey, sname in suppliers.items():
        score = _core_entity_name(sname)
        for ckey, cname in customers.items():
            if skey == ckey:
                continue
            ccore = _core_entity_name(cname)
            if len(score) >= 2 and len(ccore) >= 2 and (score in ccore or ccore in score):
                similar_pairs.append((sname, cname))
                break
    if not similar_pairs:
        return []
    examples = [{"supplier": s, "customer": c} for s, c in similar_pairs[:10]]
    return [_finding(
        spec,
        f"有{len(similar_pairs)}对供应商与客户名称高度近似：" + "；".join(f"{s}≈{c}" for s, c in similar_pairs[:5]) + "。同字号分设购销公司是虚开、对开和关联交易闭环的常见形态，须核验股权、注册地址、人员重叠和业务实质。",
        {"similar_pair_count": len(similar_pairs), "examples": examples},
        spec["required_sources"],
        priority="调查优先级",
    )]


def _unique_person_count(rows):
    names = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("姓名") or row.get("员工") or "").strip()
        if name:
            names.add(name)
    return len(names)


def _scan_workforce_revenue(data, spec):
    sal_invs = data.get("sal_invs", []) or []
    if not sal_invs:
        return []
    revenue = sum(_number(row.get("amount")) for row in sal_invs)
    if revenue <= 0:
        return []
    salary_count = _unique_person_count(data.get("salaries", []))
    social_count = _unique_person_count(data.get("social_security", []))
    headcount = max(salary_count, social_count)
    if headcount <= 0:
        return []  # 无工资/社保数据，无法核验用工规模
    per_capita = revenue / headcount
    if per_capita > 5000000 or per_capita < 50000:
        direction = "异常偏高" if per_capita > 5000000 else "异常偏低"
        return [_finding(
            spec,
            f"销项收入合计{revenue:,.2f}元，估算用工人数{headcount}人（工资表{salary_count}人/社保{social_count}人），人均产值{per_capita:,.0f}元，{direction}，须核验用工真实性、业务外包情况和收入完整性。",
            {
                "revenue": round(revenue, 2),
                "headcount": headcount,
                "salary_headcount": salary_count,
                "social_headcount": social_count,
                "per_capita_output": round(per_capita, 2),
            },
            spec["required_sources"],
            priority="调查优先级",
        )]
    return []


_RAW_MATERIAL_KEYWORDS = ["纱", "布", "棉", "氨纶", "纤维", "坯布", "面料", "针织", "梭织", "染整",
                          "原料", "钢材", "钢板", "铝", "铜", "铁", "塑料", "化工", "粮食", "木材",
                          "石材", "水泥", "矿产", "原油", "煤炭", "纸浆", "浆粕", "颗粒"]


def _scan_material_output_ratio(data, spec):
    sal_invs = data.get("sal_invs", []) or []
    pur_invs = data.get("pur_invs", []) or []
    if not sal_invs or not pur_invs:
        return []
    raw_amount = sum(
        _number(row.get("amount"))
        for row in pur_invs
        if any(key in str(row.get("goods") or row.get("货物或应税劳务名称") or "") for key in _RAW_MATERIAL_KEYWORDS)
    )
    output_amount = sum(_number(row.get("amount")) for row in sal_invs)
    if raw_amount <= 0 or output_amount <= 0:
        return []
    ratio = output_amount / raw_amount
    if ratio > 5.0 or ratio < 0.8:
        direction = "加价倍数异常高" if ratio > 5.0 else "购销倒挂"
        return [_finding(
            spec,
            f"进项原材料及生产物资{raw_amount:,.2f}元，销项成品{output_amount:,.2f}元，加价倍数{ratio:.2f}倍，{direction}，须核验是否存在虚开、空壳、隐匿收入或虚抵进项，并结合BOM、存货和产能逐项复核。",
            {
                "raw_material_amount": round(raw_amount, 2),
                "output_amount": round(output_amount, 2),
                "markup_ratio": round(ratio, 4),
            },
            spec["required_sources"],
            priority="调查优先级",
        )]
    return []


def _is_individual_entity(name):
    """判断供应商/客户是否为个人或个体工商户（非公司制主体）。"""
    name = str(name or "").strip()
    if not name:
        return False
    if any(key in name for key in ("公司", "有限", "股份", "集团")):
        return False
    if any(key in name for key in ("个体", "经营部", "商行", "经销部", "个人", "厂", "店", "部", "中心", "工作室")):
        return True
    return len(name) <= 4  # 短名称大概率是人名


def _scan_individual_counterparty(data, spec):
    sal = data.get("sal_invs", []) or []
    pur = data.get("pur_invs", []) or []
    suppliers = defaultdict(lambda: {"amount": 0.0, "count": 0})
    customers = defaultdict(lambda: {"amount": 0.0, "count": 0})
    for row in pur:
        name = str(row.get("seller") or row.get("销方名称") or "").strip()
        if name and _is_individual_entity(name):
            suppliers[name]["amount"] += _number(row.get("amount"))
            suppliers[name]["count"] += 1
    for row in sal:
        name = str(row.get("buyer") or row.get("购方名称") or "").strip()
        if name and _is_individual_entity(name):
            customers[name]["amount"] += _number(row.get("amount"))
            customers[name]["count"] += 1
    if not suppliers and not customers:
        return []
    sup_total = sum(agg["amount"] for agg in suppliers.values())
    cus_total = sum(agg["amount"] for agg in customers.values())
    detail_parts = []
    if suppliers:
        detail_parts.append(f"个人/个体户供应商{len(suppliers)}家，合计{sup_total:,.0f}元")
    if customers:
        detail_parts.append(f"个人/个体户客户{len(customers)}家，合计{cus_total:,.0f}元")
    return [_finding(
        spec,
        "；".join(detail_parts) + "。个人或个体工商户交易须核验业务真实性、是否代开发票、是否履行个人所得税扣缴义务，以及是否存在借用个人主体走账或虚开。",
        {
            "individual_supplier_count": len(suppliers),
            "individual_customer_count": len(customers),
            "supplier_amount": round(sup_total, 2),
            "customer_amount": round(cus_total, 2),
            "examples": sorted(set(list(suppliers.keys()) + list(customers.keys())))[:12],
        },
        spec["required_sources"],
        priority="调查优先级",
    )]


_COMPANY_SUFFIX = ["公司", "有限", "集团", "厂", "店", "银行", "税务", "国库", "金库", "ETS", "社保", "公积金",
                   "预算", "中心", "学校", "医院", "政府", "局", "支行", "分理处", "信用社", "合作社", "单位"]


def _scan_fund_recirculation(data, spec):
    """资金回流与公私混同检测：企业↔个人账户大额整数转账。

    核心信号：企业账户向个人账户大额整数转出（20万/30万），摘要为"转存/转取/往来"
    等公私转账，是资金抽逃、回流、私分的典型特征。
    """
    bank = data.get("bank_txs", []) or []
    target_entity = data.get("target_entity", {})
    personnel = _collect_personnel(target_entity)

    person_txs = defaultdict(lambda: {"credit": 0.0, "debit": 0.0, "count": 0, "big_out": [], "big_in": []})
    for row in bank:
        counterparty = str(row.get("counterparty") or "").strip()
        if not counterparty:
            continue
        is_person = counterparty in personnel or any(p and p in counterparty for p in personnel) \
            or (not any(s in counterparty for s in _COMPANY_SUFFIX))
        if not is_person:
            continue
        credit = _number(row.get("credit"))
        debit = _number(row.get("debit"))
        summary = str(row.get("summary") or "").strip()
        date = str(row.get("date") or "")[:10]
        amount = credit if credit > 0 else debit
        entry = person_txs[counterparty]
        entry["credit"] += credit
        entry["debit"] += debit
        entry["count"] += 1
        if amount >= 100000 and abs(amount % 10000) < 0.01:
            rec = {"date": date, "amount": round(amount, 2), "summary": summary[:12]}
            if credit > 0:
                entry["big_in"].append(rec)
            else:
                entry["big_out"].append(rec)

    signals = []
    for name, agg in sorted(person_txs.items(), key=lambda item: -(item[1]["debit"] + item[1]["credit"])):
        out_to_person = agg["debit"]
        in_from_person = agg["credit"]
        big_out = agg["big_out"]
        big_in = agg["big_in"]
        if out_to_person >= 500000 and big_out:
            summary_hint = "、".join(sorted({r["summary"] or "转账" for r in big_out}))[:30]
            signals.append(
                f"{name}：企业向其转出{out_to_person:,.0f}元（{len(big_out)}笔大额整数转账{summary_hint}），"
                f"收到{in_from_person:,.0f}元，公私账户资金混同，须核验资金抽逃、回流、私分或借款性质"
            )

    if not signals:
        return []
    return [_finding(
        spec,
        "；".join(signals) + "。企业账户与个人账户的大额整数转存转取是资金回流、抽逃、账外经营的高发形态，须逐笔核验款项性质、是否计入股东往来或分红、是否履行个人所得税扣缴义务。",
        {
            "person_account_count": len(person_txs),
            "matches": [
                {"name": name, "out_to_person": round(agg["debit"], 2), "in_from_person": round(agg["credit"], 2),
                 "big_out_count": len(agg["big_out"]), "big_in_count": len(agg["big_in"])}
                for name, agg in sorted(person_txs.items(), key=lambda item: -(item[1]["debit"] + item[1]["credit"]))[:10]
            ],
        },
        spec["required_sources"],
        priority="调查优先级",
    )]


# ─────────────────────────────────────────────────────────────────────────────
# 新增风险点扫描器（VR026–VR031，依据 web 稽查案例与税法条款提炼）
# ─────────────────────────────────────────────────────────────────────────────

# 各行业增值税税负率参考区间（行业代码 → 参考区间[低, 高]），仅作偏离筛查参考
_INDUSTRY_VAT_BURDEN = {
    "13": (2.5, 4.5),   # 纺织业
    "14": (2.0, 4.0),   # 服装
    "17": (2.5, 4.5),   # 纺织（达冠样例）
    "C": (2.0, 4.0),
    "A": (1.5, 3.5),
    "B": (2.5, 5.0),
    "D": (3.0, 6.0),
    "F": (2.5, 5.0),
    "G": (1.5, 3.5),
    "H": (2.0, 4.5),
    "Q": (2.0, 4.0),
}


def _scan_vat_burden_rate(data, spec):
    """税负率异常：实际税负率 = 实缴增值税 / 应税销售收入，与行业参考区间偏离。

    依据：金税四期十大预警禁区之“税负率异常”；案例宁夏鑫海德税负率0.1%被稽查。
    """
    decls = data.get("tax_declarations", []) or []
    sal = data.get("sal_invs", []) or []
    if not decls:
        return []

    paid_vat = 0.0          # 实缴/应纳税额
    declared_sales = 0.0    # 申报销售额
    for decl in decls:
        if not isinstance(decl, dict):
            continue
        paid_vat += _number(decl.get("payable_tax") or decl.get("vat_paid") or decl.get("actual_vat") or decl.get("tax_payable"))
        declared_sales += _number(decl.get("sales_amount") or decl.get("output_amount"))

    # 税负率应以实际经营规模（发票反映的销售额）为分母；申报销售额显著低于发票时，
    # 若用申报数作分母会掩盖低税负，故优先采用发票不含税金额作为收入基数。
    invoice_sales = sum(_number(row.get("amount")) for row in sal)
    revenue_base = invoice_sales if invoice_sales > 0 else declared_sales
    if revenue_base <= 0:
        return []

    burden = paid_vat / revenue_base * 100.0

    industry_code = str((data.get("target_entity") or {}).get("industry_code") or "C")
    ref = _INDUSTRY_VAT_BURDEN.get(industry_code) or _INDUSTRY_VAT_BURDEN.get(industry_code[0]) or (2.0, 4.0)
    low, high = ref

    if burden < low - 0.5 and paid_vat >= 0:
        direction = "显著低于行业参考区间"
        flag = burden < 1.0  # 极低税负（如 <1%）属高危
    elif burden > high + 1.0:
        direction = "显著高于行业参考区间"
        flag = False
    else:
        return []

    detail = (
        f"测算增值税税负率约{burden:.2f}%（实缴增值税{paid_vat:,.2f}元 / 应税销售收入{revenue_base:,.2f}元），"
        f"{direction}（行业参考区间{low:.1f}%–{high:.1f}%）。"
        + ("该极低税负率是隐匿收入、虚抵进项或空壳经营的高发信号，须逐期核验进销项结构与未开票收入。"
           if flag else
           "税负率偏高可能源于进项税额不足、简易计税或行业特性，须结合进销项结构解释。")
    )
    return [_finding(
        spec,
        detail,
        {
            "paid_vat": round(paid_vat, 2),
            "revenue_base": round(revenue_base, 2),
            "burden_rate_pct": round(burden, 4),
            "industry_ref_low": low,
            "industry_ref_high": high,
            "extreme_low": flag,
        },
        spec["required_sources"],
        priority="调查优先级" if flag else "中",
    )]


def _is_void_or_red(row):
    """判断发票行是否为作废/红冲。支持字段：is_void/作废、is_red/红字/负数。"""
    status = str(row.get("status") or row.get("发票状态") or "").strip()
    if "作废" in status or "红" in status or "负数" in status:
        return True
    if str(row.get("is_void") or "").strip().lower() in ("1", "true", "y", "是"):
        return True
    if str(row.get("is_red") or "").strip().lower() in ("1", "true", "y", "是"):
        return True
    try:
        if _number(row.get("amount")) < 0 or _number(row.get("total")) < 0:
            return True
    except (TypeError, ValueError):
        pass
    return False


def _scan_void_red_invoice(data, spec):
    """作废/红冲发票异常占比。

    依据：金税四期预警——临近申报期集中作废、顶额作废、红冲后重开是隐匿收入信号。
    """
    sal = data.get("sal_invs", []) or []
    pur = data.get("pur_invs", []) or []
    if not sal and not pur:
        return []
    total = len(sal) + len(pur)
    void_red = [row for row in sal + pur if _is_void_or_red(row)]
    if total < 5 or not void_red:
        return []
    ratio = len(void_red) / total
    near_period_end = 0
    top_amount = 0
    examples = []
    for row in void_red[:30]:
        date = str(row.get("date") or row.get("invoice_date") or "")
        day = date[-2:] if len(date) >= 2 else ""
        if day in ("28", "29", "30", "31") or date[-3:] in ("/12", "-12", "/03", "-03", "/06", "-06", "/09", "-09"):
            near_period_end += 1
        amt = _number(row.get("amount"))
        top_amount = max(top_amount, amt)
        if len(examples) < 5:
            examples.append({
                "invoice_no": str(row.get("inv_no") or row.get("invoice_no") or row.get("发票号码") or "")[:20],
                "amount": round(amt, 2),
                "date": date[:10],
                "status": str(row.get("status") or "红冲/作废")[:8],
            })
    if ratio >= 0.2 or near_period_end >= 3:
        detail = (
            f"作废/红冲发票{len(void_red)}张，占全部发票{total}张的{ratio:.1%}。"
            + (f"其中{near_period_end}张集中在月末/季末，存在临近申报期调节税基嫌疑；" if near_period_end else "")
            + "作废红冲须逐票核验原交易是否真实履行、是否退货折让或变相隐匿收入。"
        )
        return [_finding(
            spec,
            detail,
            {
                "void_red_count": len(void_red),
                "total_count": total,
                "void_red_ratio": round(ratio, 4),
                "near_period_end_count": near_period_end,
                "top_amount": round(top_amount, 2),
                "examples": examples,
            },
            spec["required_sources"],
            priority="调查优先级" if (near_period_end >= 3 or ratio >= 0.3) else "中",
        )]
    return []


def _scan_uninvoiced_income(data, spec):
    """未开票收入隐匿线索（双口径）：

    口径一：银行收款显著大于销项开票（私户走账、账外经营）。
    口径二：销项开票（或银行收款）显著大于增值税申报销售额（申报少列收入）。
    依据：案例 宁夏鑫海德（私户走账隐匿收入）、临潭盛渝（资金回流闭环）。
    """
    bank = data.get("bank_txs", []) or []
    sal = data.get("sal_invs", []) or []
    decls = data.get("tax_declarations", []) or []
    if not sal:
        return []

    bank_credit = sum(_number(row.get("credit")) for row in bank if _number(row.get("credit")) > 0)
    invoice_total = sum(_invoice_amount(row) for row in sal)        # 价税合计（口径一用）
    invoice_amount = sum(_number(row.get("amount")) for row in sal)  # 不含税金额（口径二与申报销售额比对）

    declared_sales = 0.0
    for decl in decls:
        if isinstance(decl, dict):
            declared_sales += _number(decl.get("sales_amount"))

    # 口径二：开票/收款 与 申报销售额 的偏离（核心隐匿信号）
    if declared_sales > 0:
        gap_decl = invoice_amount - declared_sales
        ratio_decl = gap_decl / declared_sales if declared_sales else 0
        if gap_decl >= 500000 and ratio_decl >= 0.3:
            detail = (
                f"销项发票不含税金额合计{invoice_amount:,.2f}元，增值税申报销售额合计{declared_sales:,.2f}元，"
                f"差额{gap_decl:,.2f}元（{ratio_decl:.1%}）。开票规模显著高于申报销售额，"
                "存在少列收入或未开票收入未申报的典型隐匿线索，须逐月核对未开票收入、预收款及视同销售。"
            )
            return [_finding(
                spec,
                detail,
                {
                    "invoice_total": round(invoice_amount, 2),
                    "declared_sales": round(declared_sales, 2),
                    "gap": round(gap_decl, 2),
                    "gap_ratio": round(ratio_decl, 4),
                    "basis": "开票vs申报",
                },
                spec["required_sources"],
                priority="调查优先级",
            )]

    # 口径一：银行收款 显著大于 开票（无申报数据时退化为资金线索）
    if bank_credit > 0 and invoice_total > 0:
        gap = bank_credit - invoice_total
        ratio = gap / invoice_total if invoice_total else 0
        if gap >= 500000 and ratio >= 0.3:
            detail = (
                f"银行贷方收款合计{bank_credit:,.2f}元，销项发票价税合计{invoice_total:,.2f}元，"
                f"差额{gap:,.2f}元（{ratio:.1%}）。收款持续、大幅超过开票且无合理解释，"
                "是隐匿未开票收入的典型线索，须按预收款、借款、代收代付逐笔排除后核实。"
            )
            return [_finding(
                spec,
                detail,
                {
                    "bank_credit_total": round(bank_credit, 2),
                    "invoice_total": round(invoice_total, 2),
                    "declared_sales": round(declared_sales, 2),
                    "gap": round(gap, 2),
                    "gap_ratio": round(ratio, 4),
                    "basis": "收款vs开票",
                },
                spec["required_sources"],
                priority="调查优先级",
            )]
    return []


def _scan_long_zero_filing(data, spec):
    """长期零申报或申报数据异常。"""
    decls = data.get("tax_declarations", []) or []
    if not decls:
        return []
    zero_count = 0
    periods = []
    for decl in decls:
        if not isinstance(decl, dict):
            continue
        sales = _number(decl.get("sales_amount"))
        vat = _number(decl.get("payable_tax") or decl.get("vat_paid") or decl.get("tax_payable"))
        period = str(decl.get("period") or decl.get("申报期间") or "")
        periods.append(period)
        if sales <= 0 and vat <= 0:
            zero_count += 1
    total = len(decls)
    if total >= 6 and zero_count >= max(3, int(total * 0.5)):
        detail = (
            f"在{total}个申报期中，有{zero_count}期销售额与应纳税额均为零（零申报）。"
            "长期零申报与持续经营迹象（银行流水、发票、工资）冲突时，是空壳或账外经营的预警，须结合经营实质核对。"
        )
        return [_finding(
            spec,
            detail,
            {"declaration_count": total, "zero_count": zero_count, "periods": periods[:12]},
            spec["required_sources"],
            priority="中",
        )]
    return []


def _scan_shareholder_loan(data, spec):
    """股东借款长期挂账与其他应收款异常（视同分红线索）。

    依据：财税〔2003〕158号第二条、国税发〔2005〕120号第三十五条、新《公司法》五年实缴。
    """
    bank = data.get("bank_txs", []) or []
    vouchers = data.get("vouchers", []) or []
    target_entity = data.get("target_entity", {}) or {}
    personnel = _collect_personnel(target_entity)
    if not personnel:
        return []

    person_out = defaultdict(float)
    for row in bank:
        party = str(row.get("counterparty") or "").strip()
        if not party:
            continue
        if any(p and p in party for p in personnel) or party in personnel:
            person_out[party] += _number(row.get("debit"))

    receivable = 0.0
    recv_examples = []
    for row in vouchers:
        account = str(row.get("account_name") or row.get("account") or "")
        summary = str(row.get("summary") or "")
        if "其他应收款" in account and any(p and p in summary for p in personnel):
            amt = _number(row.get("debit"))
            receivable += amt
            if len(recv_examples) < 5:
                recv_examples.append({"summary": summary[:20], "debit": round(amt, 2)})

    total_to_person = sum(person_out.values())
    if total_to_person >= 500000 or receivable >= 300000:
        parts = []
        if person_out:
            parts.append("；".join(f"{name}转出{amt:,.0f}元" for name, amt in
                                   sorted(person_out.items(), key=lambda x: -x[1])[:3]))
        if receivable > 0:
            parts.append(f"凭证中其他应收款挂六员合计{receivable:,.0f}元")
        detail = (
            "、".join(parts)
            + "。股东（个人投资者）从企业借款，在纳税年度终了既不归还又未用于生产经营的，依财税〔2003〕158号、"
              "国税发〔2005〕120号可视同红利分配按“利息、股息、红利所得”征20%个税，企业须履行代扣代缴义务；"
              "大额挂账亦触发金税四期其他应收款预警，须核验借款协议、用途及归还时点。"
        )
        return [_finding(
            spec,
            detail,
            {
                "person_out_total": round(total_to_person, 2),
                "other_receivable_to_person": round(receivable, 2),
                "person_out_detail": {name: round(amt, 2) for name, amt in person_out.items()},
                "receivable_examples": recv_examples,
            },
            spec["required_sources"],
            priority="调查优先级",
        )]
    return []


def _scan_stamp_tax(data, spec):
    """印花税计税依据与购销金额勾稽。

    依据：金税四期“利润表与所得税申报失真/印花税漏洞”比对；购销合同印花税计税依据通常≥购销合计。
    """
    sal = data.get("sal_invs", []) or []
    pur = data.get("pur_invs", []) or []
    decls = data.get("tax_declarations", []) or []
    if not sal and not pur:
        return []

    purchase_amount = sum(_number(row.get("amount")) for row in pur)
    sales_amount = sum(_number(row.get("amount")) for row in sal)
    contract_base = purchase_amount + sales_amount
    if contract_base <= 0:
        return []

    declared_base = 0.0
    for decl in decls:
        if isinstance(decl, dict):
            declared_base += _number(decl.get("stamp_tax_base") or decl.get("印花税计税依据"))

    if declared_base <= 0:
        return []
    gap = contract_base - declared_base
    ratio = gap / contract_base if contract_base else 0
    if gap >= 500000 and ratio >= 0.3:
        detail = (
            f"购销发票金额合计{contract_base:,.2f}元（购{purchase_amount:,.2f}+销{sales_amount:,.2f}），"
            f"申报印花税计税依据{declared_base:,.2f}元，差额{gap:,.2f}元（{ratio:.1%}）。"
            "购销合同印花税计税依据通常不低于购销金额合计，差额较大须核是否仅按部分合同申报或未申报，排除小微企业免征后处理。"
        )
        return [_finding(
            spec,
            detail,
            {
                "purchase_amount": round(purchase_amount, 2),
                "sales_amount": round(sales_amount, 2),
                "contract_base": round(contract_base, 2),
                "declared_stamp_base": round(declared_base, 2),
                "gap": round(gap, 2),
                "gap_ratio": round(ratio, 4),
            },
            spec["required_sources"],
            priority="中",
        )]
    return []


# ── VR032 进项税额应转出未转出 ────────────────────────────────────
# 进项专票用途命中不得抵扣情形（业务招待/集体福利/个人消费/免税/简易计税/
# 非正常损失/贷款服务），应做进项税额转出而未转出的线索。
# 复用 engine.vat_reversal 的"初审命中→二审上下文豁免→去误报"两阶段引擎，
# 与 domain_analysis 共用同一套判定逻辑，避免同一张发票两处结论打架。
# 依据：增值税法第十条、财税〔2016〕36号附件1第二十七条。


def _scan_input_tax_reversal(data, spec):
    pur = data.get("pur_invs", []) or []
    if not pur:
        return []
    # 企业画像文本：用于二审豁免（如餐饮/酒厂购酒可抵扣），无则不参与
    profile = " ".join(str(data.get("enterprise_profile", "")).split()) \
        if isinstance(data.get("enterprise_profile"), (str, list)) else ""
    hits = []
    reversal_total = 0.0
    for row in pur:
        if not isinstance(row, dict):
            continue
        # 仅对含税额的专票做筛查（普票本身不可抵扣，不在此列）
        tax = _number(row.get("tax") or row.get("税额") or row.get("tax_amount"))
        if tax <= 0:
            continue
        code = str(row.get("invoice_code", "") or row.get("发票代码", ""))
        is_special = code[:2] in ("01", "04", "10", "11") or row.get("_has_deduction_columns", False) \
            or str(row.get("invoice_category", "") or "").find("专用") >= 0
        if not is_special:
            continue
        # 两阶段判定：初审关键词命中 → 二审上下文豁免
        verdict = classify_input_tax_reversal(row, profile)
        if verdict["needs_reversal"] and not verdict["exempted"]:
            hits.append({
                "invoice_no": row.get("invoice_no") or row.get("发票号码", ""),
                "goods": row.get("goods") or row.get("品名", ""),
                "seller": row.get("seller") or row.get("销方", ""),
                "tax": round(tax, 2),
                "suspicion": verdict["suspicion"],
                "keyword": verdict["keyword"],
                "rationale": verdict["rationale"],
            })
            reversal_total += tax
    if hits:
        detail = (
            f"检出{len(hits)}张专票进项税额存在不得抵扣用途嫌疑（合计税额{reversal_total:,.2f}元），"
            "如用于业务招待、集体福利、个人消费、免税/简易计税项目、非正常损失或贷款服务，"
            "即使取得专票也须做进项税额转出。已结合企业画像与会计科目做上下文豁免排除生产经营用途，"
            "仍命中的须逐张核对用途与对应成本费用科目处理。"
        )
        return [_finding(
            spec,
            detail,
            {
                "hit_count": len(hits),
                "reversal_tax_total": round(reversal_total, 2),
                "examples": hits[:10],
            },
            spec["required_sources"],
            priority="调查优先级",
        )]
    return []


# ── VR033 进销品名背离（变名开票） ────────────────────────────────
# 购进与销售的商品如跨越明显不同大类（原料 vs 完全不同成品，或煤炭→建材类变名），
# 且伴随资金回流/异常，是变名虚开线索。此处仅做品名大类背离筛查，定性留人工。
_GOODS_CATEGORY_MAP = {
    "棉纱": "纺织原料", "纱": "纺织原料", "布料": "纺织品", "针织布": "纺织品",
    "布": "纺织品", "染料": "化工", "化工": "化工", "加工费": "加工服务",
    "煤": "矿产", "炭": "矿产", "钢材": "金属", "钢": "金属", "建材": "建材",
    "水泥": "建材", "设备": "设备", "木材": "木材", "农产品": "农产品", "粮": "农产品",
    "油": "能源", "电": "能源", "酒": "食品饮料", "茶": "食品饮料", "食品": "食品饮料",
}


def _goods_category(name):
    if not name:
        return "未知"
    for kw, cat in _GOODS_CATEGORY_MAP.items():
        if kw in str(name):
            return cat
    return "其他"


def _scan_goods_name_divergence(data, spec):
    sal = data.get("sal_invs", []) or []
    pur = data.get("pur_invs", []) or []
    if not sal or not pur:
        return []
    pur_cats = {_goods_category(r.get("goods")) for r in pur if _goods_category(r.get("goods")) not in ("未知",)}
    sal_cats = {_goods_category(r.get("goods")) for r in sal if _goods_category(r.get("goods")) not in ("未知",)}
    if not pur_cats or not sal_cats:
        return []
    # 合理产业链：原料→成品、加工服务不构成背离
    supply_chain_ok = bool(pur_cats & sal_cats) or "加工服务" in pur_cats
    if supply_chain_ok:
        return []
    # 大类完全不同，构成背离
    divergence = sorted(pur_cats ^ sal_cats)
    if len(divergence) >= 1 and not (pur_cats & sal_cats):
        detail = (
            f"购进商品大类{pur_cats}，销售商品大类{sal_cats}，二者无交集且非加工服务衔接，"
            "存在进销品名严重背离。若伴随资金回流、富余票或异常票流向，是『变名开票』（如煤炭变建材、废钢变设备）"
            "掩饰虚开的高频线索。须结合生产工艺、BOM与物流核验交易实质。"
        )
        return [_finding(
            spec,
            detail,
            {
                "purchase_categories": sorted(pur_cats),
                "sales_categories": sorted(sal_cats),
                "divergence": divergence,
            },
            spec["required_sources"],
            priority="调查优先级",
        )]
    return []


# ── VR034 成本费用虚列异常 ────────────────────────────────────────
# 凭证中出现大额咨询/会议/广告/服务费、以及大额现金支出，或费用率显著高于同业，
# 标注成本费用真实性风险（虚列成本费用的线索）。
_SUSPICIOUS_EXPENSE_KW = ["咨询", "顾问", "会议", "会务", "广告", "推广", "服务费", "中介", "佣金", "劳务", "培训", "营销"]
# 行业参考费用率（费用/收入），超过即预警（分行业粗口径）
_EXPENSE_RATE_WARN = 0.40


def _scan_expense_fabrication(data, spec):
    vs = data.get("vouchers", []) or []
    if not vs:
        return []
    suspicious = []
    cash_total = 0.0
    expense_total = 0.0
    revenue_total = 0.0
    for v in vs:
        if not isinstance(v, dict):
            continue
        amount = _number(v.get("amount") or v.get("金额") or v.get("debit"))
        if amount <= 0:
            continue
        summary = str(v.get("summary") or v.get("摘要") or v.get("subject") or "")
        expense_total += amount
        if "现金" in summary or str(v.get("settle") or "").find("现金") >= 0:
            cash_total += amount
        if any(kw in summary for kw in _SUSPICIOUS_EXPENSE_KW) and amount >= 100000:
            suspicious.append({
                "summary": summary[:40],
                "amount": round(amount, 2),
                "date": v.get("date", ""),
            })
    # 收入口径：优先发票不含税，其次申报
    sal = data.get("sal_invs", []) or []
    decls = data.get("tax_declarations", []) or []
    revenue_total = sum(_number(r.get("amount")) for r in sal)
    if revenue_total <= 0:
        revenue_total = sum(_number(d.get("sales_amount")) for d in decls)
    expense_rate = expense_total / revenue_total if revenue_total > 0 else 0

    findings = []
    if suspicious:
        detail = (
            f"检出{len(suspicious)}笔大额（≥10万）咨询/会议/广告/服务/佣金类费用合计"
            f"{sum(x['amount'] for x in suspicious):,.2f}元，是虚列成本费用、虚开发票套取资金的高频载体。"
            "须逐笔核验合同、成果物、付款对象（是否个体户/空壳）与资金最终去向。"
        )
        findings.append(_finding(
            spec, detail,
            {"suspicious_count": len(suspicious), "suspicious_total": round(sum(x["amount"] for x in suspicious), 2),
             "examples": suspicious[:10], "cash_total": round(cash_total, 2)},
            spec["required_sources"], priority="中",
        ))
    if expense_rate >= _EXPENSE_RATE_WARN and revenue_total > 0:
        detail = (
            f"凭证费用合计{expense_total:,.2f}元，收入口径{revenue_total:,.2f}元，费用率{expense_rate:.1%}，"
            "显著高于常规行业水平。费用率畸高可能源于成本费用虚列、关联交易转移利润或收入隐匿，须结合成本结构核验。"
        )
        findings.append(_finding(
            spec, detail,
            {"expense_total": round(expense_total, 2), "revenue_total": round(revenue_total, 2),
             "expense_rate": round(expense_rate, 4), "cash_total": round(cash_total, 2)},
            spec["required_sources"], priority="中",
        ))
    return findings


# ── VR035 印花税其他税目漏报 ──────────────────────────────────────
# 在 VR031 购销合同基础上，扩展借款合同（bank_txs 借款/其他应收款）、租赁合同
# （vouchers 租赁费）、产权转移等税目，比对申报印花税计税依据，标注漏报线索。
def _scan_stamp_tax_other_items(data, spec):
    bank = data.get("bank_txs", []) or []
    vs = data.get("vouchers", []) or []
    decls = data.get("tax_declarations", []) or []
    if not bank and not vs:
        return []

    # 借款合同计税依据：向银行/非金融借款、其他应收款挂股东款近似
    loan_base = 0.0
    for row in bank:
        txt = " ".join(str(x) for x in row.values())
        if "借款" in txt or "贷款" in txt:
            loan_base += abs(_number(row.get("credit") or row.get("debit")))
    for v in vs:
        txt = " ".join(str(x) for x in v.values())
        if "借款" in txt or "其他应收款" in txt:
            loan_base += abs(_number(v.get("amount") or v.get("debit")))

    # 租赁合同计税依据：租赁费（税额千分之一）
    lease_base = 0.0
    for v in vs:
        txt = str(v.get("summary") or v.get("摘要") or "")
        if "租赁" in txt or "房租" in txt or "租金" in txt:
            lease_base += _number(v.get("amount") or v.get("debit"))

    declared_base = 0.0
    for decl in decls:
        if isinstance(decl, dict):
            declared_base += _number(decl.get("stamp_tax_base") or decl.get("印花税计税依据"))

    other_base = loan_base + lease_base
    if other_base <= 0:
        return []
    if declared_base <= 0:
        # 无申报数据时不强行误报，仅在有申报且明显偏低时提示
        return []
    gap = other_base - declared_base
    ratio = gap / other_base if other_base else 0
    if gap >= 300000 and ratio >= 0.3:
        detail = (
            f"借款/租赁合同推算印花税计税依据约{other_base:,.2f}元（借款{loan_base:,.2f}+租赁{lease_base:,.2f}），"
            f"申报计税依据{declared_base:,.2f}元，差额{gap:,.2f}元（{ratio:.1%}）。"
            "借款合同、租赁合同等分属不同印花税税目，须逐税目核对贴花，排除金融机构借款合同免征、小微免征后处理。"
        )
        return [_finding(
            spec, detail,
            {"loan_base": round(loan_base, 2), "lease_base": round(lease_base, 2),
             "other_base": round(other_base, 2), "declared_stamp_base": round(declared_base, 2),
             "gap": round(gap, 2), "gap_ratio": round(ratio, 4)},
            spec["required_sources"], priority="中",
        )]
    return []


# ── VR036 视同销售未计提销项税额 ──────────────────────────────────
# 下列情形应视同销售计提销项税额，却未对应申报收入的线索：
# ①无偿赠送/样品/赠品（摘要含"赠送/样品/赠品/宣传品"且无对应销项收入）
# ②自产或委托加工货物用于集体福利/个人消费（领用产成品入福利费/在建工程等）
# ③将自产、委托加工或购进货物无偿送其他单位或个人
# 依据：增值税法第十条、财税[2016]36号附件1第十四条。
_GIFT_KEYWORDS = ["赠送", "赠品", "样品", "宣传品", "无偿", "礼盒", "促销赠"]
_SELF_USE_KEYWORDS = ["福利费", "集体福利", "个人消费", "在建工程", "职工", "工会", "食堂"]


def _scan_deemed_sales(data, spec):
    sal = data.get("sal_invs", []) or []
    vs = data.get("vouchers", []) or []
    pur = data.get("pur_invs", []) or []
    if not vs and not sal:
        return []

    gifts = []          # 无偿赠送/样品类
    self_use = []       # 自产自用/集体福利领用类

    # 通道1：凭证摘要中的赠送/样品/福利领用
    for v in vs:
        if not isinstance(v, dict):
            continue
        summary = str(v.get("summary") or v.get("摘要") or v.get("subject") or "")
        amount = _number(v.get("amount") or v.get("金额") or v.get("debit"))
        # 赠送/样品：有支出但无对应收入，且非销售费用-促销（促销已含视同销售处理）
        if any(kw in summary for kw in _GIFT_KEYWORDS):
            gifts.append({
                "summary": summary[:40],
                "amount": round(amount, 2),
                "date": v.get("date", ""),
                "channel": "凭证摘要",
            })
        # 自产自用/集体福利：领用产成品或外购货物入福利/在建工程
        if any(kw in summary for kw in _SELF_USE_KEYWORDS) and amount > 0:
            # 排除明显的工资/社保等常规福利费（已代扣个税路径）
            if "样品" not in summary and "赠送" not in summary:
                self_use.append({
                    "summary": summary[:40],
                    "amount": round(amount, 2),
                    "date": v.get("date", ""),
                    "channel": "凭证摘要",
                })

    # 通道2：销项发票中"样品/赠品"零金额或异常低金额（视同销售未计收入）
    for row in sal:
        if not isinstance(row, dict):
            continue
        goods = str(row.get("goods") or row.get("品名") or "")
        amt = _number(row.get("amount") or row.get("金额"))
        if any(kw in goods for kw in _GIFT_KEYWORDS) and amt <= 0:
            gifts.append({
                "summary": f"销项发票品名含{goods}",
                "amount": 0.0,
                "date": row.get("date", ""),
                "channel": "销项发票零金额",
            })

    findings = []
    if gifts:
        g_total = sum(x["amount"] for x in gifts)
        detail = (
            f"检出{len(gifts)}笔疑似无偿赠送/样品/赠品支出（合计{g_total:,.2f}元），"
            "将自产、委托加工或购进货物无偿赠送其他单位或个人、交付样品，应视同销售计提销项税额。"
            "若未对应确认收入，存在少计销项风险。须逐笔核对受赠对象、是否作销售费用-促销（已含视同销售）"
            "及是否按组成计税价格申报。"
        )
        findings.append(_finding(
            spec, detail,
            {"gift_count": len(gifts), "gift_total": round(g_total, 2),
             "examples": gifts[:10]},
            spec["required_sources"], priority="中",
        ))
    if self_use:
        s_total = sum(x["amount"] for x in self_use)
        detail = (
            f"检出{len(self_use)}笔将货物用于集体福利/个人消费/在建工程的领用（合计{s_total:,.2f}元），"
            "自产或委托加工货物用于集体福利、个人消费，应视同销售计提销项税额。"
            "须核对领用物资是否为自产/委托加工货物，以及对应销项税额计提情况。"
        )
        findings.append(_finding(
            spec, detail,
            {"self_use_count": len(self_use), "self_use_total": round(s_total, 2),
             "examples": self_use[:10]},
            spec["required_sources"], priority="中",
        ))
    return findings


# ── VR037 关联交易价格偏离（转让定价探针） ────────────────────────
# 独立交易原则要求关联方交易价格应等同于非关联方。本规则以可量化信号做探针：
# 同一品名+同单位，对不同交易对手方的单价离散度异常（相对中位数偏离≥阈值），
# 是转让定价偏离（低价输送利润/高价虚增成本）的线索。
# 关联定性（是否真为关联方）需工商股权穿透数据；无该数据时仅提示补充。
# 依据：企业所得税法第四十一条、特别纳税调整实施办法。
_PRICE_DEVIATION_RATIO = 0.40


def _norm_goods(name):
    if not name:
        return "未知"
    name = str(name)
    # 简单归一：去掉规格后缀，保留主体品名（棉纱32S→棉纱；针织布全棉→针织布）
    for kw in ("棉纱", "纱", "针织布", "布", "染料", "加工费", "钢", "建材", "水泥",
               "设备", "木材", "农产品", "粮", "油", "电", "酒", "茶", "食品"):
        if kw in name:
            return kw
    return name


def _scan_related_party_pricing(data, spec):
    sal = data.get("sal_invs", []) or []
    pur = data.get("pur_invs", []) or []
    related = data.get("related_parties", []) or data.get("equity_penetration", []) or []

    # 按 (归一品名, 单位) 分组单价与对手方
    groups = {}
    for row in sal + pur:
        if not isinstance(row, dict):
            continue
        goods = _norm_goods(row.get("goods") or row.get("品名"))
        unit = str(row.get("unit") or row.get("单位") or "").strip()
        # 单价优先读 price/单价，缺失时由 amount/数量 推算
        price = _number(row.get("price") or row.get("单价"))
        if price <= 0:
            amt = _number(row.get("amount") or row.get("金额"))
            qty = _number(row.get("qty") or row.get("数量"))
            if amt > 0 and qty > 0:
                price = amt / qty
        if price <= 0 or not unit or goods == "未知":
            continue
        key = (goods, unit)
        groups.setdefault(key, []).append({
            "price": price,
            "counterparty": row.get("buyer") or row.get("购方名称") or row.get("seller") or row.get("销方名称") or "",
            "invoice_no": row.get("invoice_no") or row.get("发票号码", ""),
            "direction": "销" if row in sal else "进",
        })

    deviations = []
    for (goods, unit), recs in groups.items():
        if len(recs) < 3:     # 至少3笔不同交易才具统计意义
            continue
        prices = sorted(r["price"] for r in recs)
        mid = prices[len(prices) // 2]
        if mid <= 0:
            continue
        for r in recs:
            dev = abs(r["price"] - mid) / mid
            if dev >= _PRICE_DEVIATION_RATIO:
                deviations.append({
                    "goods": goods, "unit": unit,
                    "counterparty": r["counterparty"],
                    "price": round(r["price"], 2),
                    "median_price": round(mid, 2),
                    "deviation": round(dev, 3),
                    "direction": r["direction"],
                    "invoice_no": r["invoice_no"],
                })

    findings = []
    if deviations:
        detail = (
            f"同一品名同单位交易中检出{len(deviations)}笔单价相对中位数偏离≥{_PRICE_DEVIATION_RATIO:.0%}的异常，"
            "偏离独立交易原则(ARM'S LENGTH)，是转让定价（利润输送/成本虚增）的可疑线索。"
            "须结合工商股权穿透识别是否关联方，并准备同期资料举证定价合理性。"
        )
        findings.append(_finding(
            spec, detail,
            {"deviation_count": len(deviations), "threshold": _PRICE_DEVIATION_RATIO,
             "examples": deviations[:10]},
            spec["required_sources"], priority="调查优先级",
        ))
    # 数据完整性提示：若未提供股权穿透，无法做关联定性
    if not related:
        findings.append(_finding(
            spec,
            "未检测到工商股权穿透/关联方清单数据，转让定价无法完成关联定性（仅做价格离散度探针）。"
            "建议接入工商股权穿透数据（股东/对外投资/人员任职交叉）以识别隐性关联方，提升转让定价稽查精度。",
            {"related_party_data": False, "note": "需补充股权穿透数据"},
            spec["required_sources"], priority="提示",
        ))
    return findings


# ── VR038–VR041 企业所得税税前扣除限额与资产摊销 ──────────────────────
def _sum_voucher_by_keywords(vouchers, kw_list, fields=("account_name", "summary")):
    """归集凭证中科目/摘要命中关键词的借方合计与明细。"""
    total = 0.0
    rows = []
    for v in vouchers or []:
        if not isinstance(v, dict):
            continue
        text = " ".join(str(v.get(f) or "") for f in fields)
        if any(kw in text for kw in kw_list):
            amt = _number(v.get("debit") or v.get("借方") or v.get("amount"))
            if amt > 0:
                total += amt
                rows.append({
                    "account": str(v.get("account_name") or v.get("account") or ""),
                    "summary": str(v.get("summary") or v.get("摘要") or "")[:40],
                    "debit": round(amt, 2),
                })
    return total, rows


def _annual_revenue(data):
    """年度销售(营业)收入：优先申报销售额合计，其次销项开票不含税合计。"""
    decls = data.get("declaration", []) or []
    if isinstance(decls, dict):
        decls = [decls]
    rev = sum(_number(d.get("sales_amount") or d.get("output_amount")) for d in decls)
    if rev <= 0:
        rev = sum(_number(r.get("amount")) for r in (data.get("sal_invs") or []))
    return rev


def _wage_total(data):
    """工资薪金总额：优先 payroll 合计，其次应付职工薪酬贷方/工资凭证。"""
    payroll = data.get("payroll")
    if isinstance(payroll, list) and payroll:
        s = sum(_number(p.get("salary") or p.get("工资") or p.get("amount")) for p in payroll)
        if s > 0:
            return s, "payroll"
    vouchers = data.get("vouchers") or []
    wage_kw = ["工资", "薪酬", "应付职工薪酬"]
    total, _ = _sum_voucher_by_keywords(vouchers, wage_kw)
    return total, ("vouchers" if total > 0 else "缺失")


def _scan_biz_entertainment_limit(data, spec):
    """VR038 业务招待费：发生额×60% 与 收入×5‰ 孰低扣除，超限未调增预警。"""
    vouchers = data.get("vouchers") or []
    if not vouchers:
        return []
    occ, rows = _sum_voucher_by_keywords(vouchers, ["业务招待", "招待费", "招待", "应酬"])
    if occ <= 0:
        return []
    rev = _annual_revenue(data)
    if rev <= 0:
        return []
    deduct_cap = min(occ * 0.6, rev * 0.005)
    over = occ - deduct_cap
    if over <= 0:
        return []
    detail = (
        f"业务招待费账面发生额{occ:,.2f}元，按税法规定限额为 min(发生额×60%, 营业收入×5‰)="
        f"{deduct_cap:,.2f}元，超限{over:,.2f}元须作纳税调增。若汇算清缴未做调整，存在少缴企业所得税风险。"
    )
    return [_finding(spec, detail,
                     {"entertainment_total": round(occ, 2), "deduct_cap": round(deduct_cap, 2),
                      "over_limit": round(over, 2), "annual_revenue": round(rev, 2),
                      "examples": rows[:10]},
                     spec["required_sources"], priority="调查优先级")]


def _scan_ad_promo_limit(data, spec):
    """VR039 广告费和业务宣传费：不超过收入15%扣除，超限预警（可结转）。"""
    vouchers = data.get("vouchers") or []
    if not vouchers:
        return []
    occ, rows = _sum_voucher_by_keywords(vouchers, ["广告", "宣传", "业务宣传"])
    if occ <= 0:
        return []
    rev = _annual_revenue(data)
    if rev <= 0:
        return []
    cap = rev * 0.15
    over = occ - cap
    if over <= 0:
        return []
    detail = (
        f"广告费和业务宣传费账面{occ:,.2f}元，扣除限额为营业收入×15%={cap:,.2f}元，"
        f"超限{over:,.2f}元（可在以后纳税年度结转扣除）。若当年未正确区分资本性支出与费用化支出，"
        "或超限部分未作纳税调增，存在所得税风险。"
    )
    return [_finding(spec, detail,
                     {"ad_promo_total": round(occ, 2), "deduct_cap": round(cap, 2),
                      "over_limit": round(over, 2), "annual_revenue": round(rev, 2),
                      "examples": rows[:10]},
                     spec["required_sources"], priority="调查优先级")]


def _scan_welfare_limit(data, spec):
    """VR040 职工福利费：不超过工资薪金总额14%扣除，超限预警。"""
    vouchers = data.get("vouchers") or []
    if not vouchers:
        return []
    occ, rows = _sum_voucher_by_keywords(vouchers, ["福利", "职工福利", "工会经费", "职工教育"])
    if occ <= 0:
        return []
    wage, src = _wage_total(data)
    if wage <= 0:
        # 工资总额缺失：仅提示绝对值，无法精确限额
        return [_finding(spec,
                         f"检出职工福利费等相关支出{occ:,.2f}元，但未获取到工资薪金总额数据，"
                         "无法核对14%扣除限额。须补充工资总额（payroll或应付职工薪酬）以完成限额比对。",
                         {"welfare_total": round(occ, 2), "wage_total": 0, "note": "工资总额缺失"},
                         spec["required_sources"], priority="提示")]
    cap = wage * 0.14
    over = occ - cap
    if over <= 0:
        return []
    detail = (
        f"职工福利费等相关支出{occ:,.2f}元，工资薪金总额{wage:,.2f}元，扣除限额为工资总额×14%="
        f"{cap:,.2f}元，超限{over:,.2f}元须纳税调增（工会经费2%、职工教育经费8%另有专项限额）。"
    )
    return [_finding(spec, detail,
                     {"welfare_total": round(occ, 2), "wage_total": round(wage, 2),
                      "deduct_cap": round(cap, 2), "over_limit": round(over, 2),
                      "wage_source": src, "examples": rows[:10]},
                     spec["required_sources"], priority="调查优先级")]


def _scan_depreciation_anomaly(data, spec):
    """VR041 折旧摊销异常：凭证折旧/摊销与固定资产原值勾稽，或一次性扣除违规。"""
    vouchers = data.get("vouchers") or []
    if not vouchers:
        return []
    dep, dep_rows = _sum_voucher_by_keywords(vouchers, ["折旧", "摊销", "长期待摊"])
    if dep <= 0:
        return []
    fa = data.get("fixed_assets") or []
    fa_total = sum(_number(a.get("original_value") or a.get("原值") or a.get("cost")) for a in fa)
    notes = []
    if fa_total <= 0:
        notes.append("未获取到固定资产原值，无法核对折旧计提充分性")
    else:
        # 年折旧率粗略合理性：若年折旧额/原值 > 50%（远超加速折旧上限）提示异常
        rate = dep / fa_total
        if rate > 0.5:
            notes.append(f"年折旧摊销额占固定资产原值{rate:.0%}，明显高于常规折旧率，疑一次性税前扣除或加速折旧违规")
    if not notes:
        return []
    detail = (
        f"检出折旧/摊销/长期待摊费用合计{dep:,.2f}元。" + "；".join(notes) +
        "。须核对资产计税基础、折旧年限与一次性税前扣除政策适用条件（如单价≤500万元设备器具）。"
    )
    return [_finding(spec, detail,
                     {"dep_amort_total": round(dep, 2), "fixed_assets_total": round(fa_total, 2),
                      "notes": notes, "examples": dep_rows[:10]},
                     spec["required_sources"], priority="提示")]


def _scan_property_tax(data, spec):
    """VR042 房产税从价/从租勾稽：房屋原值从价计征 + 租金从租计征，与申报勾稽。"""
    findings = []
    fa = data.get("fixed_assets") or []
    building_value = sum(
        _number(a.get("original_value") or a.get("原值") or a.get("cost"))
        for a in fa if "房" in str(a.get("name") or a.get("名称") or a.get("类别") or "")
    )
    from_price_tax = building_value * (1 - 0.3) * 0.012 if building_value > 0 else 0.0
    contracts = data.get("contracts") or []
    if isinstance(contracts, dict):
        contracts = [contracts]
    rent_total = 0.0
    rent_notes = []
    for c in contracts:
        if not isinstance(c, dict):
            continue
        txt = " ".join(str(v) for v in c.values())
        if "租" in txt or "租赁" in str(c.get("合同类型") or c.get("type") or ""):
            monthly = _number(c.get("月租金") or c.get("rent_monthly") or c.get("租金"))
            months = _number(c.get("租赁月数") or c.get("months") or 12)
            if monthly > 0:
                rent_total += monthly * (months if months > 0 else 12)
                rent_notes.append(str(c.get("合同编号") or c.get("no") or "租赁合同")[:20])
    from_rent_tax = rent_total * 0.12 if rent_total > 0 else 0.0
    est_total = from_price_tax + from_rent_tax
    if est_total <= 0:
        return []
    decls = data.get("declaration", []) or []
    if isinstance(decls, dict):
        decls = [decls]
    declared_property = sum(
        _number(d.get("property_tax") or d.get("房产税") or d.get("city_tax")
                or d.get("supplementary_tax") or 0)
        for d in decls
    )
    metrics = {"building_value": round(building_value, 2), "from_price_tax": round(from_price_tax, 2),
               "rent_total": round(rent_total, 2), "from_rent_tax": round(from_rent_tax, 2),
               "est_property_tax": round(est_total, 2), "declared_property_tax": round(declared_property, 2),
               "rent_contracts": rent_notes}
    if declared_property <= 0:
        detail = (
            f"据固定资产房屋原值{building_value:,.2f}元测算从价房产税约{from_price_tax:,.2f}元；"
            f"据租赁合同租金{rent_total:,.2f}元测算从租房产税约{from_rent_tax:,.2f}元，"
            f"合计应缴约{est_total:,.2f}元，但未检出房产税申报记录。须确认是否已申报缴纳，避免漏报。"
        )
        findings.append(_finding(spec, detail, metrics, spec["required_sources"], priority="调查优先级"))
    elif declared_property < est_total * 0.9:
        detail = (
            f"测算房产税应缴约{est_total:,.2f}元（从价{from_price_tax:,.2f}+从租{from_rent_tax:,.2f}），"
            f"申报仅{declared_property:,.2f}元，存在少报风险。须核对计税依据（原值扣除比例、租金口径）。"
        )
        findings.append(_finding(spec, detail, metrics, spec["required_sources"], priority="调查优先级"))
    return findings


def _scan_city_constr_tax(data, spec):
    """VR043 城建税及附加随增值税附征勾稽。"""
    decls = data.get("declaration", []) or []
    if isinstance(decls, dict):
        decls = [decls]
    if not decls:
        return []
    paid_vat = sum(_number(d.get("payable_tax") or d.get("vat_paid") or d.get("actual_vat")
                           or d.get("tax_payable")) for d in decls)
    if paid_vat <= 0:
        return []
    city_rate = 0.07
    edu_rate = 0.03
    local_edu_rate = 0.02
    est_city = paid_vat * city_rate
    est_edu = paid_vat * edu_rate
    est_local = paid_vat * local_edu_rate
    declared_supp = sum(
        _number(d.get("supplementary_tax") or d.get("城建税") or d.get("附加税")
                or d.get("city_edu_tax") or 0)
        for d in decls
    )
    est_total = est_city + est_edu + est_local
    metrics = {"paid_vat": round(paid_vat, 2), "est_city_tax": round(est_city, 2),
               "est_edu": round(est_edu, 2), "est_local_edu": round(est_local, 2),
               "est_total": round(est_total, 2), "declared_supplementary": round(declared_supp, 2),
               "note": "城建税率按市区7%测算，县城5%/乡村1%需按实际地区调整"}
    if declared_supp <= 0:
        detail = (
            f"实缴增值税{paid_vat:,.2f}元，应随征城建税及附加约{est_total:,.2f}元"
            f"（城建7%={est_city:,.2f}+教育费附加3%={est_edu:,.2f}+地方教育附加2%={est_local:,.2f}），"
            "但未检出附加税申报记录。城建税及附加须随增值税附征，须确认是否漏报。"
        )
        return [_finding(spec, detail, metrics, spec["required_sources"], priority="调查优先级")]
    if declared_supp < est_total * 0.8:
        detail = (
            f"测算随征附加税约{est_total:,.2f}元，申报仅{declared_supp:,.2f}元，存在少报风险"
            "（注意：县城/乡村城建税率低于市区，须按实际地区核对）。"
        )
        return [_finding(spec, detail, metrics, spec["required_sources"], priority="调查优先级")]
    return []


_SCANNERS = {
    "VR001": _scan_bank_invoice_gap,
    "VR002": _scan_voucher_invoice_gap,
    "VR003": lambda data, spec: _scan_duplicate_invoices(data, spec, "sal_invs"),
    "VR004": lambda data, spec: _scan_duplicate_invoices(data, spec, "pur_invs"),
    "VR005": _scan_payroll_social,
    "VR006": _scan_negative_inventory,
    "VR007": _scan_inventory_rollforward,
    "VR008": _scan_voucher_balance,
    "VR009": _scan_bank_balance_rollforward,
    "VR010": lambda data, spec: _scan_invoice_arithmetic(data, spec, "sal_invs"),
    "VR011": lambda data, spec: _scan_invoice_arithmetic(data, spec, "pur_invs"),
    "VR012": _scan_customer_supplier_overlap,
    "VR013": _scan_bidirectional_bank,
    "VR014": _scan_production_energy,
    "VR015": _scan_invoice_goods_missing,
    "VR016": _scan_supplier_geo,
    "VR017": _scan_concentration,
    "VR018": _scan_vat_declaration_sales_gap,
    "VR019": _scan_vat_declaration_input_gap,
    "VR020": _scan_personnel_fund_flow,
    "VR021": _scan_name_similarity,
    "VR022": _scan_workforce_revenue,
    "VR023": _scan_material_output_ratio,
    "VR024": _scan_individual_counterparty,
    "VR025": _scan_fund_recirculation,
    "VR026": _scan_vat_burden_rate,
    "VR027": _scan_void_red_invoice,
    "VR028": _scan_uninvoiced_income,
    "VR029": _scan_long_zero_filing,
    "VR030": _scan_shareholder_loan,
    "VR031": _scan_stamp_tax,
    "VR032": _scan_input_tax_reversal,
    "VR033": _scan_goods_name_divergence,
    "VR034": _scan_expense_fabrication,
    "VR035": _scan_stamp_tax_other_items,
    "VR036": _scan_deemed_sales,
    "VR037": _scan_related_party_pricing,
    "VR038": _scan_biz_entertainment_limit,
    "VR039": _scan_ad_promo_limit,
    "VR040": _scan_welfare_limit,
    "VR041": _scan_depreciation_anomaly,
    "VR042": _scan_property_tax,
    "VR043": _scan_city_constr_tax,
}


def run_verified_rules(engine_data):
    """运行全部已验证原子规则，返回发现和逐规则执行记录。"""
    findings, executions = [], []
    for spec in VERIFIED_RULE_CATALOG:
        missing = [source for source in spec["required_sources"] if not engine_data.get(source)]
        if missing:
            executions.append({
                "rule_id": spec["id"],
                "status": "not_run_missing_data",
                "missing_sources": missing,
            })
            continue
        try:
            results = _SCANNERS[spec["id"]](engine_data, spec)
            findings.extend(results)
            executions.append({
                "rule_id": spec["id"],
                "status": "triggered" if results else "completed_not_triggered",
                "finding_count": len(results),
            })
        except Exception as error:
            executions.append({
                "rule_id": spec["id"],
                "status": "execution_error",
                "message": str(error)[:240],
            })
    available_sources = {k for k, v in engine_data.items() if v}
    coverage = build_coverage_report(
        VERIFIED_RULE_CATALOG, set(_SCANNERS.keys()),
        {"findings": findings}, available_sources,
    )
    return {
        "version": "1.0.0",
        "executed_at": datetime.now().isoformat(),
        "catalog_count": len(VERIFIED_RULE_CATALOG),
        "findings": findings,
        "executions": executions,
        "coverage": coverage,
        "coverage_text": format_coverage_text(coverage),
    }
