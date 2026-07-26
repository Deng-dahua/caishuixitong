# -*- coding: utf-8 -*-
"""重构#11-#15三链: 从平行重复改为串联(线索6步/证据5维/分析4步)"""
import json, os

STATIC = os.path.dirname(os.path.abspath(__file__))

def load_json(name):
    with open(os.path.join(STATIC, name), encoding='utf-8') as f:
        return json.load(f)

def save_json(name, data):
    with open(os.path.join(STATIC, name), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ========== #11 进项品名不匹配 ==========
CLUE_11 = {
    "id": "clue-011", "name": "进项品名与经营实质不匹配→虚开发票调查路径",
    "category": "发票进销匹配", "domain": "发票域x经营域x资金域", "sub_topic": "发票进销匹配",
    "trigger_keywords": [], "rule_refs": ["11"],
    "suggestion": "核心:1.品名能否物理转化?买钢材卖软件=不能;2.有实物吗?无仓库无入库=纯虚开;3.资金回流吗?付款回到关联方=虚开闭环。",
    "investigation_path": [
        {"step": 1, "action": "数据提取:提取全部进项发票品名汇总+销项发票品名汇总+营业执照经营范围→建立品名全景图", "evidence": "进项发票明细+销项发票明细+营业执照"},
        {"step": 2, "action": "品名比对:沿原料→加工→成品逻辑逐品名验证→购进品名能否物理转化为销售品名→标记无法转化的品名(如买钢材卖软件)", "evidence": "品名对比表+加工工艺说明"},
        {"step": 3, "action": "异常量化:汇总无法转化品名的金额和占比→计算涉及进项税额→锁定前十大异常品名供应商", "evidence": "异常品名汇总表+进项税额计算"},
        {"step": 4, "action": "实物验证(物理常识类):携带异常品名清单赴现场→查仓库有无该品名存货→查入库单→查领用出库记录→账有实无=纯虚开", "evidence": "仓库实地照片+入库单+盘点表"},
        {"step": 5, "action": "供应商穿透:对前十大异常供应商逐户工商核查→注册资本/成立时间/经营范围/经营场所/社保人数→计算年开票额/注册资本比→>10=异常", "evidence": "供应商工商信息+社保记录+经营场所照片"},
        {"step": 6, "action": "资金追踪:调取付款银行流水→追踪付款后30日内资金流向→检查是否有等额或按比例资金回流至企业关联方/个人账户→回流=虚开闭环→定性", "evidence": "银行流水+供应商账户+关联方个人账户"}
    ]
}

EVID_11 = {
    "id": "evid-011", "name": "进项品名不匹配→虚开发票多源验证闭环",
    "category": "发票进销匹配", "domain": "发票域x经营域x资金域", "sub_topic": "发票进销匹配",
    "trigger_keywords": [], "rule_refs": ["11"], "level": "极高风险",
    "description": "从品名转化、实物存在、供应商能力、资金回流、合同一致五个独立维度并行验证虚开。",
    "suggestion": "min_evidence=3组合:品名不可转化+无实物=虚开铁证。",
    "min_evidence": 3,
    "dimensions": [
        {"dimension": "品名转化链路", "check": "购进品名经加工后能否物理转化为销售品名", "evidence_items": ["进项品名汇总", "销项品名汇总", "加工工艺说明"], "pass_condition": "无法物理转化", "weight": "必备维度"},
        {"dimension": "实物存在性", "check": "异常品名有无仓库/入库单/盘点记录", "evidence_items": ["仓库照片", "入库单", "盘点表"], "pass_condition": "账有实无", "weight": "核心维度"},
        {"dimension": "供应商经营能力", "check": "供应商注册资本vs年开票额/成立时间/社保人数", "evidence_items": ["工商信息", "社保记录"], "pass_condition": "开票额/注册资本>10或空壳", "weight": "核心维度"},
        {"dimension": "资金回流", "check": "付款后30日内资金是否回流至关联方", "evidence_items": ["银行流水", "关联方账户"], "pass_condition": "存在回流", "weight": "核心维度"},
        {"dimension": "合同一致性", "check": "合同标的/金额/时间是否与发票一致", "evidence_items": ["购销合同", "发票", "物流单"], "pass_condition": "不一致或无合同", "weight": "辅助维度"}
    ]
}

ALC_11 = {
    "id": "alc-011", "name": "进项品名不匹配→跨域推理:虚开定性链",
    "category": "跨域分析", "domain": "", "sub_topic": "发票进销匹配",
    "trigger_keywords": [], "rule_refs": ["11"], "level": "极高风险",
    "description": "基于线索链调查发现和证据链验证结果，进行4步跨域推理定性。",
    "suggestion": "",
    "reasoning_path": [
        {"step": 1, "cross": "发票域x经营域", "action": "线索链发现品名无法物理转化(发票域)+证据链确认品名转化链路断裂(经营域)→排除正常加工贸易→虚开嫌疑确立", "evidence_required": "品名对比表+加工工艺说明", "conclusion": "品名不可转化→虚开嫌疑，但需排除委托加工等合法解释"},
        {"step": 2, "cross": "发票域x实物域", "action": "线索链调查发现账有实无(实物域)+证据链确认实物存在性不达标→排除真实采购→纯虚开坐实", "evidence_required": "仓库照片+入库单+盘点表", "conclusion": "无实物=交易未真实发生→虚开发票"},
        {"step": 3, "cross": "资金域x关联域", "action": "线索链追踪发现资金回流(资金域)+证据链确认供应商为空壳/关联方(关联域)→虚开闭环完成", "evidence_required": "银行流水+工商信息+关联方清单", "conclusion": "资金回流+空壳供应商=虚开完整证据链"},
        {"step": 4, "cross": "发票域x申报域x法律域", "action": "前三步结论:虚开发票(发票域)→虚增进项抵扣(申报域)→少缴增值税→依据征管法§63认定偷税+发票管理办法§22虚开→移送公安", "evidence_required": "进项抵扣明细+申报表+全部证据链", "conclusion": "虚开抵扣=偷税(征管法63条);构成犯罪移送公安"}
    ]
}

# ========== #12 销售方vs付款方不匹配 ==========
CLUE_12 = {
    "id": "clue-012", "name": "销售方与付款方不匹配→三流断裂调查路径",
    "category": "发票进销匹配", "domain": "发票域x资金域x合同域", "sub_topic": "发票进销匹配",
    "trigger_keywords": [], "rule_refs": ["12"],
    "suggestion": "核心:1.发票方vs付款方一致吗?不一致=三流断裂;2.有委托付款协议吗?无=虚构;3.付给个人多少?大额=资金体外循环。",
    "investigation_path": [
        {"step": 1, "action": "数据提取:提取全部进项发票销售方名称+银行付款对手方名称→逐笔比对→标记不一致的交易", "evidence": "进项发票明细+银行付款记录"},
        {"step": 2, "action": "差异量化:统计不一致交易笔数和金额→计算占总进项的比例→锁定前十大异常交易", "evidence": "差异交易汇总表+金额占比计算"},
        {"step": 3, "action": "委托协议核查:对不一致交易逐笔索取委托付款协议→核查协议签署时间(是否在交易前)→协议内容是否具体明确→无协议或事后补签=三流断裂", "evidence": "委托付款协议+签署时间证明"},
        {"step": 4, "action": "个人账户追踪(物理常识类):付款到个人的→追踪个人账户资金去向→是否转给发票方?→个人账户是否与企业管理层/股东关联?", "evidence": "银行流水+个人账户明细+关联方清单"},
        {"step": 5, "action": "交易实质验证:对不一致交易核查有无合同/入库单/物流凭证→四流(发票/资金/合同/物流)合一验证→缺一流=交易不完整", "evidence": "合同+入库单+物流凭证+发票"},
        {"step": 6, "action": "闭环判定:汇总三流断裂+委托协议缺失+个人账户+交易实质四维结果→判定:无委托+付个人+无物流=虚构交易→定性", "evidence": "全部证据链汇总"}
    ]
}

EVID_12 = {
    "id": "evid-012", "name": "销售方与付款方不匹配→三流断裂多源验证闭环",
    "category": "发票进销匹配", "domain": "发票域x资金域x合同域", "sub_topic": "发票进销匹配",
    "trigger_keywords": [], "rule_refs": ["12"], "level": "极高风险",
    "description": "从三流一致性、委托协议、个人账户、交易实质、供应商状态五个维度并行验证。",
    "suggestion": "min_evidence=3组合:三流断裂+无委托协议=虚构交易铁证。",
    "min_evidence": 3,
    "dimensions": [
        {"dimension": "三流一致性", "check": "发票销售方vs银行付款对手方是否一致", "evidence_items": ["发票", "银行记录"], "pass_condition": "不一致", "weight": "必备维度"},
        {"dimension": "委托协议", "check": "有无书面委托付款协议且在交易前签署", "evidence_items": ["委托协议", "签署时间"], "pass_condition": "无协议或事后补签", "weight": "核心维度"},
        {"dimension": "个人账户", "check": "付款到个人的金额/频次/资金去向", "evidence_items": ["银行流水", "个人账户"], "pass_condition": "大额且无正当理由", "weight": "核心维度"},
        {"dimension": "交易实质", "check": "有无合同/入库单/物流四流合一", "evidence_items": ["合同", "入库单", "物流单"], "pass_condition": "缺一流", "weight": "核心维度"},
        {"dimension": "供应商状态", "check": "发票方是否存续/有经营场所/与收款方关系", "evidence_items": ["工商信息", "经营场所"], "pass_condition": "已注销或与收款方无关联", "weight": "辅助维度"}
    ]
}

ALC_12 = {
    "id": "alc-012", "name": "销售方与付款方不匹配→跨域推理:虚构交易定性链",
    "category": "跨域分析", "domain": "", "sub_topic": "发票进销匹配",
    "trigger_keywords": [], "rule_refs": ["12"], "level": "极高风险",
    "description": "基于线索链和证据链的发现，进行4步跨域推理定性。",
    "suggestion": "",
    "reasoning_path": [
        {"step": 1, "cross": "发票域x资金域", "action": "线索链发现发票方与付款方不一致(发票域x资金域)+证据链确认三流断裂→排除正常交易→需验证委托关系", "evidence_required": "发票+银行流水", "conclusion": "三流不一致→需委托协议证明合法性"},
        {"step": 2, "cross": "合同域x资金域", "action": "证据链确认无委托协议(合同域)+线索链发现付款到个人(资金域)→排除合法委托付款→虚构交易嫌疑", "evidence_required": "委托协议+银行流水", "conclusion": "无委托+付个人=虚构交易嫌疑"},
        {"step": 3, "cross": "合同域x物流域x实物", "action": "线索链调查发现交易无合同/入库/物流(合同域x物流域)+证据链确认交易实质不达标→交易凭空捏造", "evidence_required": "合同+入库单+物流单", "conclusion": "无交易实质=虚构交易坐实"},
        {"step": 4, "cross": "发票域x资金域x法律域", "action": "前三步结论:虚构交易(发票域)→虚增进项抵扣(资金域)→少缴增值税→征管法§63偷税+发票管理办法§22虚开→移送公安", "evidence_required": "全部证据链", "conclusion": "虚构交易抵扣=偷税(征管法63条);构成犯罪移送公安"}
    ]
}

# ========== #13 毛利率偏离 ==========
CLUE_13 = {
    "id": "clue-013", "name": "毛利率偏离行业基准→隐匿收入或虚列成本调查路径",
    "category": "成本费用配比", "domain": "财务域x资金域x申报域", "sub_topic": "成本费用配比",
    "trigger_keywords": [], "rule_refs": ["13"],
    "suggestion": "核心:1.偏离方向?偏低→隐匿收入或虚列成本;2.银行收款vs申报差多少?差大=隐匿;3.存货盘点一致吗?不一致=虚列。",
    "investigation_path": [
        {"step": 1, "action": "数据提取:获取连续24个月利润表+增值税申报表+企业所得税申报表→计算各月毛利率", "evidence": "利润表+增值税申报表+所得税申报表"},
        {"step": 2, "action": "基准比对:企业毛利率vs行业P25/P75基准→偏离>10个百分点=异常→判定偏离方向(偏低/偏高)", "evidence": "毛利率计算表+行业基准数据"},
        {"step": 3, "action": "收入端穿透(物理常识类):调取全部对公账户+法人/股东个人账户银行流水→汇总银行收款总额→与申报收入比对→收款>申报=隐匿收入", "evidence": "银行流水+收款汇总表+申报表"},
        {"step": 4, "action": "成本端穿透:提取存货明细账→安排实地盘点→盘点vs账面→盘亏=已销未出账=虚列成本;盘点>账面=另有存货未入账", "evidence": "存货明细账+盘点表+差异说明"},
        {"step": 5, "action": "关联交易验证:前十大客户/供应商是否关联方→定价是否偏离独立第三方可比价→偏离>20%且无同期资料=转移利润", "evidence": "客户/供应商清单+关联方清单+价格对比表+同期资料"},
        {"step": 6, "action": "闭环判定:汇总偏离方向+收入端+成本端+关联交易四维结果→偏低+收款>申报=隐匿收入;偏低+盘亏=虚列成本;偏低+关联低价=转移利润→定性", "evidence": "全部证据链汇总"}
    ]
}

EVID_13 = {
    "id": "evid-013", "name": "毛利率偏离→隐匿收入或虚列成本多源验证闭环",
    "category": "成本费用配比", "domain": "财务域x资金域x申报域", "sub_topic": "成本费用配比",
    "trigger_keywords": [], "rule_refs": ["13"], "level": "高风险",
    "description": "从偏离幅度、收入端、成本端、关联交易、持续性五个维度并行验证。",
    "suggestion": "min_evidence=3组合:偏离>10%+收入端或成本端任一定性=违规定论。",
    "min_evidence": 3,
    "dimensions": [
        {"dimension": "偏离幅度", "check": "实际毛利率vs行业P25/P75偏离度", "evidence_items": ["利润表", "行业基准"], "pass_condition": "偏离>10个百分点", "weight": "必备维度"},
        {"dimension": "收入端差额", "check": "银行收款总额vs申报收入差值", "evidence_items": ["银行流水", "申报表"], "pass_condition": "收款>申报>10%", "weight": "核心维度"},
        {"dimension": "成本端盘点", "check": "存货实地盘点vs账面存货", "evidence_items": ["盘点表", "存货明细账"], "pass_condition": "盘亏>5%", "weight": "核心维度"},
        {"dimension": "关联定价", "check": "关联方交易价格vs独立第三方可比价", "evidence_items": ["价格对比表", "同期资料"], "pass_condition": "偏离>20%且无同期资料", "weight": "核心维度"},
        {"dimension": "持续性", "check": "毛利率偏离持续多少期", "evidence_items": ["24个月利润表"], "pass_condition": "持续>12个月", "weight": "辅助维度"}
    ]
}

ALC_13 = {
    "id": "alc-013", "name": "毛利率偏离→跨域推理:隐匿收入或虚列成本定性链",
    "category": "跨域分析", "domain": "", "sub_topic": "成本费用配比",
    "trigger_keywords": [], "rule_refs": ["13"], "level": "高风险",
    "description": "基于线索链和证据链的发现，进行4步跨域推理定性。",
    "suggestion": "",
    "reasoning_path": [
        {"step": 1, "cross": "财务域x行业基准", "action": "线索链计算毛利率(财务域)+证据链确认偏离行业基准>10%→排除正常经营波动→异常确立", "evidence_required": "利润表+行业基准", "conclusion": "偏离>10%→需追查收入端和成本端"},
        {"step": 2, "cross": "资金域x申报域", "action": "线索链追踪发现银行收款>申报收入(资金域x申报域)+证据链确认收入端差额达标→隐匿收入路径确立", "evidence_required": "银行流水+申报表", "conclusion": "收款>申报=隐匿收入→偷税(征管法63条)"},
        {"step": 3, "cross": "财务域x实物域", "action": "线索链盘点发现盘亏(实物域)+证据链确认成本端盘点不达标→已销未出账→虚列成本路径确立", "evidence_required": "盘点表+存货明细账", "conclusion": "盘亏=虚列成本→编造虚假计税依据(征管法64条)"},
        {"step": 4, "cross": "财务域x关联域x法律域", "action": "前三步结论:隐匿收入或虚列成本(财务域)→少缴增值税+所得税(申报域)→关联方转移利润需纳税调整(关联域)→征管法§63偷税或§64编造+所得税法§41调整", "evidence_required": "全部证据链", "conclusion": "偏低+隐匿=偷税§63;偏低+虚列=编造§64;偏低+关联=调整§41"}
    ]
}

# ========== #14 申报毛利率不匹配 ==========
CLUE_14 = {
    "id": "clue-014", "name": "申报毛利率偏离行业基准→低报收入或虚列成本调查路径",
    "category": "成本费用配比", "domain": "申报域x资金域x财务域", "sub_topic": "成本费用配比",
    "trigger_keywords": [], "rule_refs": ["14"],
    "suggestion": "核心:1.申报毛利率偏离方向?偏低→低报收入/虚列成本;2.银行收款vs申报销售额?差大=低报;3.采购量能卖出这么多货吗?物理不匹配=虚列。",
    "investigation_path": [
        {"step": 1, "action": "数据提取:获取连续36个月增值税申报表+企业所得税申报表+利润表→分别计算申报毛利率和会计毛利率", "evidence": "增值税申报表+所得税申报表+利润表"},
        {"step": 2, "action": "基准比对:申报毛利率vs行业基准毛利率→偏离>10个百分点=异常→判定方向(偏低/偏高)→偏低=低报收入或虚列成本", "evidence": "毛利率对比表+行业基准数据"},
        {"step": 3, "action": "收入端穿透(物理常识类):调取银行流水→汇总银行收款→与申报销售额比对→收款>申报=低报收入→逐笔锁定差额对应客户", "evidence": "银行流水+收款汇总+客户清单"},
        {"step": 4, "action": "成本端验证:汇总进项发票采购量+销项发票销售量→物理匹配验证→采购多但销售少且存货不增=虚列成本", "evidence": "进项发票汇总+销项发票汇总+存货明细"},
        {"step": 5, "action": "定价公允性验证:前十大客户售价是否低于成本?→持续亏本销售→转移利润或低开票→核查客户是否关联方", "evidence": "销售合同+成本计算表+客户关联关系"},
        {"step": 6, "action": "闭环判定:汇总偏离方向+收入端+成本端+定价四维→偏低+收款>申报=低报收入;偏低+采购销售不匹配=虚列成本;偏低+亏本销售=转移利润→定性", "evidence": "全部证据链汇总"}
    ]
}

EVID_14 = {
    "id": "evid-014", "name": "申报毛利率偏离→低报收入或虚列成本多源验证闭环",
    "category": "成本费用配比", "domain": "申报域x资金域x财务域", "sub_topic": "成本费用配比",
    "trigger_keywords": [], "rule_refs": ["14"], "level": "高风险",
    "description": "从偏离方向、收入端差额、成本端物理匹配、定价公允、持续性五个维度并行验证。",
    "suggestion": "min_evidence=3组合:偏离>10%+收入端或成本端任一定性=违规定论。",
    "min_evidence": 3,
    "dimensions": [
        {"dimension": "偏离方向", "check": "申报毛利率vs行业基准偏离方向和幅度", "evidence_items": ["申报表", "行业基准"], "pass_condition": "偏离>10个百分点", "weight": "必备维度"},
        {"dimension": "收入端差额", "check": "银行收款vs申报销售额差值", "evidence_items": ["银行流水", "申报表"], "pass_condition": "收款>申报>10%", "weight": "核心维度"},
        {"dimension": "成本端物理匹配", "check": "采购量vs销售量物理匹配度", "evidence_items": ["进项发票", "销项发票", "存货明细"], "pass_condition": "物理不匹配", "weight": "核心维度"},
        {"dimension": "定价公允", "check": "售价是否低于成本或关联方低价", "evidence_items": ["销售合同", "成本表", "关联关系"], "pass_condition": "亏本销售或关联低价", "weight": "核心维度"},
        {"dimension": "持续性", "check": "偏离持续多少期", "evidence_items": ["36个月申报表"], "pass_condition": "持续>12个月", "weight": "辅助维度"}
    ]
}

ALC_14 = {
    "id": "alc-014", "name": "申报毛利率偏离→跨域推理:低报收入定性链",
    "category": "跨域分析", "domain": "", "sub_topic": "成本费用配比",
    "trigger_keywords": [], "rule_refs": ["14"], "level": "高风险",
    "description": "基于线索链和证据链的发现，进行4步跨域推理定性。",
    "suggestion": "",
    "reasoning_path": [
        {"step": 1, "cross": "申报域x行业基准", "action": "线索链计算申报毛利率(申报域)+证据链确认偏离行业基准>10%→排除正常波动→异常确立", "evidence_required": "申报表+行业基准", "conclusion": "偏离>10%→需追查收入端和成本端"},
        {"step": 2, "cross": "申报域x资金域", "action": "线索链追踪发现银行收款>申报销售额(资金域)+证据链确认收入端差额达标→低报收入路径确立", "evidence_required": "申报表+银行流水", "conclusion": "收款>申报=低报收入→偷税(征管法63条)"},
        {"step": 3, "cross": "申报域x财务域x实物", "action": "线索链发现采购量与销售量物理不匹配(财务域x实物)+证据链确认成本端不达标→虚列成本路径确立", "evidence_required": "进项发票+销项发票+存货明细", "conclusion": "物理不匹配=虚列成本→编造虚假计税依据(征管法64条)"},
        {"step": 4, "cross": "申报域x关联域x法律域", "action": "前三步结论:低报收入或虚列成本(申报域)→少缴增值税+所得税→关联方转移利润需调整(关联域)→征管法§63偷税或§64编造+所得税法§41调整", "evidence_required": "全部证据链", "conclusion": "低报收入=偷税§63;虚列成本=编造§64;转移利润=调整§41"}
    ]
}

# ========== #15 费用增长与收入增长背离 ==========
CLUE_15 = {
    "id": "clue-015", "name": "费用增长与收入增长背离→虚列费用调查路径",
    "category": "成本费用配比", "domain": "财务域x发票域x资金域", "sub_topic": "成本费用配比",
    "trigger_keywords": [], "rule_refs": ["15"],
    "suggestion": "核心:1.费用增速>收入增速1.5倍=异常;2.软科目占比高=虚列集中区;3.咨询费有报告吗?无成果=无服务=虚列。",
    "investigation_path": [
        {"step": 1, "action": "数据提取:获取连续36个月利润表+费用明细账→按科目分类(咨询费/会议费/差旅费/办公费等)→计算各科目增速", "evidence": "利润表+费用明细账"},
        {"step": 2, "action": "背离检测:费用增速/收入增速比值→>1.5=异常→聚焦高增长软科目(咨询费/会议费/差旅费)→计算软科目占费用总额比", "evidence": "费用增速计算表+科目占比分析"},
        {"step": 3, "action": "成果验证(物理常识类):对大额咨询费/会议费→索取服务报告/会议纪要/参会人员名单→无成果凭证=无服务=虚列", "evidence": "服务报告+会议纪要+参会名单+签到表"},
        {"step": 4, "action": "供应商穿透:对前十大费用供应商→工商核查(成立时间/经营范围/关联关系/注销状态)→成立<1年或关联方=虚开嫌疑", "evidence": "供应商工商信息+关联方清单+经营场所"},
        {"step": 5, "action": "资金回流追踪:调取付款银行流水→追踪付款后30日内资金流向→检查是否经供应商回流到关联方或员工→回流=虚列闭环", "evidence": "银行流水+供应商账户+关联方/员工账户"},
        {"step": 6, "action": "闭环判定:汇总背离幅度+成果缺失+供应商异常+资金回流四维→背离+无成果=虚列;背离+回流=虚列闭环→定性", "evidence": "全部证据链汇总"}
    ]
}

EVID_15 = {
    "id": "evid-015", "name": "费用收入背离→虚列费用多源验证闭环",
    "category": "成本费用配比", "domain": "财务域x发票域x资金域", "sub_topic": "成本费用配比",
    "trigger_keywords": [], "rule_refs": ["15"], "level": "极高风险",
    "description": "从背离幅度、成果凭证、供应商真实性、资金回流、科目集中度五个维度并行验证。",
    "suggestion": "min_evidence=3组合:背离>1.5倍+无成果凭证=虚列铁证。",
    "min_evidence": 3,
    "dimensions": [
        {"dimension": "背离幅度", "check": "费用增速/收入增速比值", "evidence_items": ["利润表", "费用明细"], "pass_condition": "比值>1.5", "weight": "必备维度"},
        {"dimension": "成果凭证", "check": "咨询费/会议费有无服务报告/会议纪要", "evidence_items": ["服务报告", "会议纪要", "签到表"], "pass_condition": "无成果凭证", "weight": "核心维度"},
        {"dimension": "供应商真实性", "check": "费用供应商成立时间/关联关系/经营场所", "evidence_items": ["工商信息", "关联方清单"], "pass_condition": "成立<1年或关联方", "weight": "核心维度"},
        {"dimension": "资金回流", "check": "付款后资金是否回流到关联方/员工", "evidence_items": ["银行流水", "关联方账户"], "pass_condition": "存在回流", "weight": "核心维度"},
        {"dimension": "科目集中度", "check": "软科目(咨询/会议/差旅)占费用总额比", "evidence_items": ["费用明细账"], "pass_condition": "占比>30%", "weight": "辅助维度"}
    ]
}

ALC_15 = {
    "id": "alc-015", "name": "费用收入背离→跨域推理:虚列费用定性链",
    "category": "跨域分析", "domain": "", "sub_topic": "成本费用配比",
    "trigger_keywords": [], "rule_refs": ["15"], "level": "极高风险",
    "description": "基于线索链和证据链的发现，进行4步跨域推理定性。",
    "suggestion": "",
    "reasoning_path": [
        {"step": 1, "cross": "财务域x经营域", "action": "线索链计算费用增速/收入增速比值(财务域x经营域)+证据链确认背离>1.5倍→排除正常扩张→异常确立", "evidence_required": "利润表+费用明细", "conclusion": "背离>1.5倍→需追查软科目和成果"},
        {"step": 2, "cross": "财务域x实物域", "action": "线索链调查发现咨询费/会议费无成果凭证(财务域x实物)+证据链确认成果凭证不达标→无成果=无服务→虚列费用确立", "evidence_required": "服务报告+会议纪要", "conclusion": "无成果=虚列费用"},
        {"step": 3, "cross": "发票域x关联域x资金域", "action": "线索链穿透发现供应商异常(发票域x关联域)+线索链追踪发现资金回流(资金域)→虚开费用发票闭环完成", "evidence_required": "工商信息+银行流水+关联方清单", "conclusion": "供应商异常+资金回流=虚开闭环"},
        {"step": 4, "cross": "财务域x申报域x法律域", "action": "前三步结论:虚列费用(财务域)→税前扣除虚增(申报域)→少缴所得税→征管法§63偷税+发票管理办法§22虚开", "evidence_required": "申报表+全部证据链", "conclusion": "虚列费用=偷税§63;虚开费用发票=§22移送公安"}
    ]
}

# ========== 执行替换 ==========
def run():
    clues = load_json('cross_domain_clues.json')
    evid = load_json('cross_domain_evidence.json')
    alc = load_json('cross_domain_analysis.json')

    replacements = [
        (CLUE_11, EVID_11, ALC_11),
        (CLUE_12, EVID_12, ALC_12),
        (CLUE_13, EVID_13, ALC_13),
        (CLUE_14, EVID_14, ALC_14),
        (CLUE_15, EVID_15, ALC_15),
    ]

    for new_clue, new_evid, new_alc in replacements:
        # 替换线索链
        for i, c in enumerate(clues):
            if isinstance(c, dict) and c.get('id') == new_clue['id']:
                clues[i] = new_clue
                print(f'替换 {new_clue["id"]}: {len(new_clue["investigation_path"])}步')
                break
        # 替换证据链
        for i, e in enumerate(evid.get('evidence_chains', [])):
            if isinstance(e, dict) and e.get('id') == new_evid['id']:
                evid['evidence_chains'][i] = new_evid
                print(f'替换 {new_evid["id"]}: {len(new_evid["dimensions"])}维')
                break
        # 替换分析链
        for i, a in enumerate(alc.get('analysis_chains', [])):
            if isinstance(a, dict) and a.get('id') == new_alc['id']:
                alc['analysis_chains'][i] = new_alc
                print(f'替换 {new_alc["id"]}: {len(new_alc["reasoning_path"])}步')
                break

    save_json('cross_domain_clues.json', clues)
    save_json('cross_domain_evidence.json', evid)
    save_json('cross_domain_analysis.json', alc)
    print('已保存')

    # 验证
    print('\n验证:')
    for rid in range(11, 16):
        cid = f'clue-{rid:03d}'
        eid = f'evid-{rid:03d}'
        aid = f'alc-{rid:03d}'
        c = next((x for x in clues if isinstance(x, dict) and x.get('id') == cid), {})
        e = next((x for x in evid.get('evidence_chains', []) if isinstance(x, dict) and x.get('id') == eid), {})
        a = next((x for x in alc.get('analysis_chains', []) if isinstance(x, dict) and x.get('id') == aid), {})
        cn = len(c.get('investigation_path', []))
        en = len(e.get('dimensions', []))
        an = len(a.get('reasoning_path', []))
        verdict = '✅串联' if cn != en or en != an else '⚠️平行'
        print(f'  #{rid}: 线索{cn}步 证据{en}维 分析{an}步 {verdict}')

if __name__ == '__main__':
    run()
