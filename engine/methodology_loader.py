"""
税务合规方法论文本提取 + 结构化加载器
将 tax-auditor-handbook.js 中的方法论转换为引擎可读的配置
"""

METHODOLOGY_KNOWLEDGE = {
    "_meta": {
        "source": "tax-auditor-handbook.js",
        "purpose": "将手册中的税务合规方法论结构化，供引擎在分析时自动匹配应用",
        "total_methods": 0,
        "total_laws": 0,
        "total_documents": 0,
    },
    
    # ═══ 税务合规工作流程 ═══
    "workflow": {
        "stages": [
            {
                "id": "W1",
                "name": "选案",
                "law_ref": "规程第14-20条",
                "description": "税务合规局通过多渠道获取案源信息，集体研究确定税务合规对象",
                "system_mapping": "本系统的一键分析对应选案阶段的计算机分析环节，预先扫描风险",
                "key_rules": [
                    "8类案源信息（第16条）",
                    "举报处理机制（第17-18条）",
                    "计算机分析+人工分析+人机结合分析（第19条）"
                ]
            },
            {
                "id": "W2",
                "name": "检查",
                "law_ref": "规程第21-45条",
                "description": "调取账簿/实地检查/询问/取证/查询存款账户",
                "system_mapping": "系统资料驱动税务合规方法论对应检查阶段的取证要求",
                "key_rules": [
                    "调取账簿：送达后30日内退还（第25条）",
                    "跨区协查机制（第29条）",
                    "证据必须合法/真实/关联（第34条）"
                ]
            },
            {
                "id": "W3",
                "name": "审理",
                "law_ref": "规程第46-53条",
                "description": "对检查结果进行审理，差异补证，拟处理意见",
                "system_mapping": "系统的综合定性(Phase4)对应审理阶段的结论形成",
                "key_rules": [
                    "审理时限15日（第49条）",
                    "差异补证或退卷（第48条）",
                    "集体审理机制（第50-51条）"
                ]
            },
            {
                "id": "W4",
                "name": "执行",
                "law_ref": "规程第54-58条",
                "description": "送达处理决定，监督执行，强制执行",
                "system_mapping": "系统的处理建议(P0-P2)对应执行阶段的整改方案",
                "key_rules": [
                    "当事人陈述申辩（第54条）",
                    "执行期满不履行→强制执行（第56条）"
                ]
            }
        ]
    },
    
    # ═══ 14类必查资料 ═══
    "required_documents": [
        {"id": "D01", "name": "记账凭证", "law": "规程第24条", "purpose": "追溯账务处理全过程原始依据，核查分录准确性/科目运用/原始凭证匹配", "missing_risk": "会计账簿视为不健全→按征管法35条核定征收"},
        {"id": "D02", "name": "银行流水", "law": "规程第26条", "purpose": "核实资金流向、验证交易真实性、发现账外经营", "missing_risk": "无法验证资金流→虚实交易无法判定"},
        {"id": "D03", "name": "进销存台账", "law": "规程第24条", "purpose": "核实存货进销存链条，BOM分析，加工环节验证", "missing_risk": "无法判断是否有进无销/有销无进", "skip_if": "biz_model == '服务'"},
        {"id": "D04", "name": "合同文件", "law": "规程第24条", "purpose": "核实交易真实性、商业目的、权利义务约定", "missing_risk": "无法判断交易实质→可能涉及虚开发票"},
        {"id": "D05", "name": "科目余额表", "law": "征管法第24条", "purpose": "各科目借贷发生额及余额，账务逻辑验证", "missing_risk": "无法交叉验证账表一致性"},
        {"id": "D06", "name": "资产负债表+利润表", "law": "征管法第25条", "purpose": "财务指标分析、行业对标、趋势分析", "missing_risk": "无法进行财务健康诊断"},
        {"id": "D07", "name": "增值税申报表", "law": "增值税条例第23条", "purpose": "开票收入与申报收入比对、税负分析", "missing_risk": "无法核查申报一致性→存在未申报收入风险"},
        {"id": "D08", "name": "企业所得税申报表", "law": "企业所得税法第54条", "purpose": "收入总额/成本费用/纳税调整核查", "missing_risk": "无法判断企业所得申报完整性"},
        {"id": "D09", "name": "个人所得税申报表", "law": "个税法第9条", "purpose": "工资薪金/劳务报酬代扣代缴核查", "missing_risk": "无法核查个税代扣代缴履行情况"},
        {"id": "D10", "name": "其他税种申报表", "law": "各税种条例", "purpose": "印花税/城建税/房产税等核查", "missing_risk": "其他税种漏报风险"},
        {"id": "D11", "name": "发票", "law": "发票管理办法", "purpose": "电子发票+数电票验真、进销比对、税率合规", "missing_risk": "核心经营数据缺失→无法进行进销存分析"},
        {"id": "D12", "name": "工资表", "law": "征管法第35条", "purpose": "人工成本费用合理性、社保公积金匹配", "missing_risk": "无法核实工资费用真实性"},
        {"id": "D13", "name": "社保明细", "law": "社会保险法", "purpose": "参保合规、缴费基数、增减变动", "missing_risk": "无法核查社保合规性"},
        {"id": "D14", "name": "公积金缴存", "law": "公积金管理条例", "purpose": "缴存基数/比例合规、人员匹配", "missing_risk": "无法核查公积金合规性"},
    ],
    
    # ═══ 税务合规方法论 ═══
    "methodologies": [
        {
            "id": "M01",
            "name": "资料驱动税务合规法",
            "principle": "有什么资料审什么，不凭空臆测",
            "steps": ["识别已有资料类型", "评估缺失资料风险", "根据现有资料确定税务合规重点"],
            "code_ref": "_domain_document_completeness()",
            "applicable": "always"
        },
        {
            "id": "M02",
            "name": "四步税务合规分析法",
            "principle": "detect→verify→diagnose→report 统一框架",
            "steps": [
                "detect: 检测现象（进销品名不匹配/收款来源不匹配/付款不匹配）",
                "verify: 交叉验证（进项结构分析/逐名比对付款方/三源交叉）",
                "diagnose: 根因诊断（制造业加工链条/非经营资金/非对公付款/赊购）",
                "report: 输出结论（风险分级+转移+具体建议）"
            ],
            "code_ref": "_four_step_audit_framework()",
            "applicable": "always"
        },
        {
            "id": "M03",
            "name": "进销存数据比对法",
            "principle": "将进项发票品名与销项发票品名逐名比对",
            "steps": ["提取进项品名列表", "提取销项品名列表", "计算品名交集/差集", "分类原材料/成品/中间品"],
            "code_ref": "main.py all_findings 进销比对段",
            "skip_if": "biz_model == '服务'"
        },
        {
            "id": "M04",
            "name": "资金流与发票流双向核对法",
            "principle": "银行收款vs销项/银行付款vs进项，双向不可偏废",
            "steps": ["提取银行收款方→与销项客户逐户比对", "提取银行付款方→与进项供应商逐户比对", "计算匹配率/偏差率"],
            "code_ref": "main.py 四象限核对段",
            "applicable": "has_bank AND has_invoices"
        },
        {
            "id": "M05",
            "name": "供应商及客户穿透分析法",
            "principle": "集中度检测+名称群集检测+人员交叉比对",
            "steps": ["Top3供应商/Top3客户集中度计算", "名称群集(同址/同法人/同电话)", "联网查每家→六员交叉比对"],
            "code_ref": "_online_company_lookup()→_check_six_personnel_risk()",
            "applicable": "has_invoices"
        },
        {
            "id": "M06",
            "name": "经营实质核查法",
            "principle": "从工商登记→发票数据→银行流水→综合判断",
            "steps": ["工商登记核查", "进项发票审核", "销项发票审核", "进销交叉比对", "综合判断"],
            "code_ref": "_deep_biz_substance_check()",
            "variants": {
                "service": "进项/销项审核改为服务类目比对，跳过加工/运输域",
                "manufacturing": "完整五步+加工环节穿透",
                "trading": "完整五步但跳过BOM域"
            }
        },
        {
            "id": "M07",
            "name": "客户维度三源穿透法",
            "principle": "不以总收款vs总开票算偏差，穿透到每个客户维度逐户匹配",
            "steps": ["提取每个销项客户的发票金额", "提取每个银行收款方的收款金额", "逐户匹配：该客户开票金额 vs 该客户收款金额"],
            "code_ref": "main.py 三源穿透段",
            "applicable": "has_bank AND has_sales_invoices"
        },
        {
            "id": "M08",
            "name": "发票五层审计法",
            "principle": "合规→单价→加工→合理性→BOM，层层递进",
            "steps": ["合规检查(数量/单位)", "同品名单价分析", "加工费专项", "金额/数量合理性", "进销品名映射+BOM"],
            "code_ref": "_domain_invoice_audit()",
            "skip_if": "biz_model == '服务'"
        },
        {
            "id": "M09",
            "name": "六员跨企业比对法",
            "principle": "法定代表人/股东/高管/财务/办税/联络员跨企业交叉比对",
            "steps": ["提取被查单位六员信息", "联网查每家供应商/客户的六员", "检测跨企业人员重叠"],
            "code_ref": "_check_six_personnel_risk()",
            "applicable": "has_supply_chain_data"
        },
        {
            "id": "M10",
            "name": "经营实质地理分析法",
            "principle": "从企业地址→供应商/客户/加工商地理分布→运输成本→物流合理性",
            "steps": ["提取企业注册地址", "分析供应商/客户/加工商地理分布", "检测运输成本是否缺失", "加工费供应商是否在企业所在地"],
            "code_ref": "_domain_business_premise_geo()",
            "skip_if": "biz_model == '服务'"
        },
    ],
    
    # ═══ 关键法律条文 ═══
    "law_references": [
        {"id": "L01", "law": "税收征收管理法第35条", "content": "纳税人有下列情形之一的，税务机关有权核定其应纳税额：①依照法律/行政法规的规定可以不设置账簿的 ②依照法律/行政法规的规定应当设置但未设置账簿的 ③擅自销毁账簿或拒不提供纳税资料的 ④虽设置账簿但账目混乱或成本资料/收入凭证/费用凭证残缺不全难以查账的", "trigger": "资料严重缺失"},
        {"id": "L02", "law": "税收征收管理法第63条", "content": "纳税人伪造/变造/隐匿/擅自销毁账簿/记账凭证，或者在账簿上多列支出或不列少列收入，或者经税务机关通知申报而拒不申报或者进行虚假的纳税申报，不缴或者少缴应纳税款的，是偷税", "trigger": "发现虚开发票/隐匿收入/多列成本"},
        {"id": "L03", "law": "发票管理办法第22条", "content": "任何单位和个人不得有下列虚开发票行为：①为他人/为自己开具与实际经营业务情况不符的发票 ②让他人为自己开具与实际经营业务情况不符的发票 ③介绍他人开具与实际经营业务情况不符的发票", "trigger": "进销品名不匹配/购销闭环/金额异常"},
        {"id": "L04", "law": "发票管理办法第35条", "content": "违反本办法规定虚开发票的，由税务机关没收违法所得；虚开金额在1万元以下的，可以并处5万元以下罚款；虚开金额超过1万元的，并处5万元以上50万元以下罚款；构成犯罪的依法追究刑事责任", "trigger": "虚开发票"},
        {"id": "L05", "law": "中华人民共和国增值税法第9条", "content": "纳税人购进货物或者应税劳务，取得的增值税扣税凭证不符合法律/行政法规或者国务院税务主管部门有关规定的，其进项税额不得从销项税额中抵扣", "trigger": "进项发票不合规"},
        {"id": "L06", "law": "企业所得税法第8条", "content": "企业实际发生的与取得收入有关的合理的支出，包括成本/费用/税金/损失和其他支出，准予在计算应纳税所得额时扣除", "trigger": "成本费用合理性存疑"},
        {"id": "L07", "law": "征收管理法第60条", "content": "未按规定设置/保管账簿或保管记账凭证和有关资料的，由税务机关责令限期改正，可以处2000元以下罚款；情节严重的处2000元以上1万元以下罚款", "trigger": "资料缺失"},
    ],
}

# 更新元数据计数
METHODOLOGY_KNOWLEDGE["_meta"]["total_methods"] = len(METHODOLOGY_KNOWLEDGE["methodologies"])
METHODOLOGY_KNOWLEDGE["_meta"]["total_laws"] = len(METHODOLOGY_KNOWLEDGE["law_references"])
METHODOLOGY_KNOWLEDGE["_meta"]["total_documents"] = len(METHODOLOGY_KNOWLEDGE["required_documents"])


def match_methodology(domain_name):
    """按税务合规域名称匹配适用的方法论 — 通过方法名/原理关键词模糊匹配"""
    methods = METHODOLOGY_KNOWLEDGE.get("methodologies", [])
    matched = []
    domain_lower = (domain_name or "").lower()
    # 域→方法关键词映射
    _DOMAIN_KW_MAP = {
        "资料完整": ["资料驱动"],
        "进销": ["进销存", "进项", "销项", "品名", "BOM", "五层审计"],
        "存": ["进销存"],
        "资金": ["资金流", "银行", "收款", "付款", "三源穿透"],
        "发票": ["发票", "五层审计"],
        "供应商": ["供应商", "穿透", "联网"],
        "客户": ["客户", "穿透", "三源"],
        "经营实质": ["经营实质", "工商"],
        "地理": ["地理", "运输"],
        "人员": ["六员"],
        "企业": ["六员", "跨企业"],
    }
    for m in methods:
        m_name = (m.get("name", "") + m.get("principle", "")).lower()
        m_applicable = m.get("applicable", "")
        # 全局适用
        if m_applicable == "always":
            matched.append({"id": m.get("id", ""), "name": m.get("name", ""), "steps": m.get("steps", [])})
            continue
        # 关键词匹配
        matched_kw = False
        for kw_domain, kw_list in _DOMAIN_KW_MAP.items():
            if kw_domain in domain_lower:
                for kw in kw_list:
                    if kw in m_name:
                        matched.append({"id": m.get("id", ""), "name": m.get("name", ""), "steps": m.get("steps", [])})
                        matched_kw = True
                        break
                if matched_kw:
                    break
    return matched


def get_relevant_laws(domain_name):
    """按税务合规域名称获取适用的法条 — 通过触发条件关键词模糊匹配"""
    laws = METHODOLOGY_KNOWLEDGE.get("law_references", [])
    relevant = []
    domain_lower = (domain_name or "").lower()
    _LAW_KW_MAP = {
        "资料": ["资料缺失", "资料", "账簿", "凭证"],
        "发票": ["虚开发票", "发票", "进项"],
        "收入": ["偷税", "隐匿", "收入", "申报"],
        "成本": ["成本", "费用", "支出", "列支"],
        "进项": ["发票", "凭证", "虚开"],
        "销项": ["发票", "虚开"],
        "资金": ["偷税", "隐匿"],
    }
    for law in laws:
        law_trigger = (law.get("trigger", "") + law.get("content", "")).lower()
        # 全局法条
        if not law.get("trigger"):
            relevant.append({"id": law.get("id", ""), "law": law.get("law", ""), "content": law.get("content", "")})
            continue
        for kw_domain, kw_list in _LAW_KW_MAP.items():
            if kw_domain in domain_lower:
                for kw in kw_list:
                    if kw in law_trigger:
                        relevant.append({"id": law.get("id", ""), "law": law.get("law", ""), "content": law.get("content", "")})
                        break
                break
    return relevant
