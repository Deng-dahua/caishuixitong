"""
跨域协商层 — 域间自动对话、阈值联动调整、冲突消解

原理：
  各分析域独立运行后，由协商引擎汇总所有发现，
  按协商规则进行跨域对话——一个域的结论影响其他域的判定。
  
三层协商：
  1. 消解层：域A结论直接推翻域B结论（如"不缺资料"→抹掉"缺资料风险"）
  2. 降级层：域A结论削弱域B结论（如"服务行业"→进销存风险降为提示）
  3. 增强层：域A+B联合触发新结论（如"缺运费+缺仓储+零水电→空壳嫌疑"）
"""
import re
from collections import defaultdict, Counter

# ═══════════ 协商规则定义 ═══════════

NEGOTIATION_RULES = [
    # ── 消解层：A结论直接推翻B ──
    {
        "id": "NEG-001",
        "match_a": {"type": "行业判定", "结论": "服务行业"},
        "negate_b": {"domain_contains": "进销存"},
        "action": "drop",
        "reason": "服务行业不存在实物进销存，进销存风险不适用。闸门已在分析入口跳过该域，此发现为无效残留。"
    },
    {
        "id": "NEG-002",
        "match_a": {"type": "行业判定", "结论": "服务行业"},
        "negate_b": {"type": "BOM表需求判定"},
        "action": "drop",
        "reason": "服务产品无物料清单，BOM判定不适用。"
    },
    {
        "id": "NEG-003",
        "match_a": {"type": "行业判定", "结论": "服务行业"},
        "negate_b": {"domain_contains": "存货"},
        "action": "drop",
        "reason": "服务行业无实物库存，存货周转/库存预警不适用。"
    },
    {
        "id": "NEG-004",
        "match_a": {"type": "行业判定", "结论": "服务行业"},
        "negate_b": {"type_contains": "进销比"},
        "action": "downgrade",
        "new_level": "提示（服务行业不适用进销比）",
        "reason": "服务行业进销比无行业对标意义，降为提示。"
    },
    {
        "id": "NEG-005",
        "match_a": {"type": "行业判定", "结论": "服务行业"},
        "negate_b": {"type_contains": "毛利率"},
        "action": "downgrade",
        "new_level": "提示（服务行业毛利率不可对标）",
        "reason": "服务行业毛利率受品牌溢价、人力成本影响，与制造业对标逻辑不同。"
    },
    
    # ── 资料完备→其他域 ──
    {
        "id": "NEG-010",
        "match_a": {"type": "资料完备度综合评估"},
        "negate_b": {"category_contains": "合同比对"},
        "action": "mark",
        "add_tag": "资料受限结论",
        "reason": "缺少合同资料，客户的正式合同签约率和合同规范性无法判断。结论仅基于发票数据推测。"
    },
    {
        "id": "NEG-011",
        "match_a": {"type": "资料完备度综合评估"},
        "negate_b": {"category_contains": "关联交易"},
        "action": "mark",
        "add_tag": "资料受限结论",
        "reason": "缺少关联方名单/股权结构/关联交易申报表，关联交易检测无法完整执行。"
    },
    {
        "id": "NEG-012",
        "match_a": {"type": "资料完备度综合评估"},
        "negate_b": {"category_contains": "申报比对"},
        "action": "mark",
        "add_tag": "资料受限结论",
        "reason": "缺少增值税申报表/企业所得税申报表，申报数据比对无法执行。"
    },
    
    # ── 经营实质→资金流 ──
    {
        "id": "NEG-020",
        "match_a": {"domain": "经营实质分析"},
        "has_finding": {"type_contains": "经营费用"},
        "negate_b": {"type_contains": "无经营场所"},
        "action": "drop",
        "reason": "经营实质域已检测到经营费用（水电/物业/租金），经营场所存在。'无经营场所'结论与该证据矛盾，以经营实质域为准。"
    },
    {
        "id": "NEG-021",
        "match_a": {"domain": "经营实质分析"},
        "has_finding": {"type_contains": "运输"},
        "negate_b": {"domain_contains": "地理", "type_contains": "运输成本缺失"},
        "action": "downgrade",
        "new_level": "低风险",
        "reason": "经营实质域已检测到运输费用/物流费用，运输成本缺失的判断不成立。降为低风险。"
    },
    
    # ── 资金流→收款分类 ──
    {
        "id": "NEG-030",
        "match_a": {"domain": "资金流向追踪", "type_contains": "收款"},
        "has_field": "收款构成",
        "negate_b": {"type_contains": "收款与开票金额偏差"},
        "action": "mark",
        "add_tag": "含非经营收款",
        "reason": "收款构成分析显示银行流水包含非经营性收款（股东注资/借款/往来款/税费返还等），全量比对夸大了偏差。需按客户逐名匹配。"
    },
    
    # ── 缺失资料连锁效应 ──
    {
        "id": "NEG-040",
        "match_a": {"type": "资料完备度综合评估"},
        "has_item": "缺失资料",
        "negate_b": {"how_found_contains": "缺少", "not_tagged": "资料受限结论"},
        "action": "mark",
        "add_tag": "资料受限结论",
        "reason": "资料完备度域标记了缺失资料，相关域的结论缺少完整的数据支撑。"
    },
    
    # ── 增强层：多域联合触发新结论 ──
    {
        "id": "NEG-AUG-001",
        "trigger_a": {"domain_contains": "经营实质", "type_contains": "经营费用", "level": "高风险"},
        "trigger_b": {"domain_contains": "地理", "type_contains": "运输成本缺失", "level": "高风险"},
        "trigger_c": {"domain_contains": "经营实质", "type_contains": "经营场所"},
        "action": "synthesize",
        "new_finding": {
            "type": "空壳企业综合预警",
            "level": "极高风险",
            "score": 10,
            "detail": "跨域协商引擎自动综合以下信号：经营场所费用缺失+运输成本缺失+经营费用不足。三域交叉指向企业可能无实际经营场所和物流活动，存在空壳企业风险。",
            "how_found": "跨域协商引擎：经营实质域+地理分析域+资金流域三域交叉研判，自动综合生成。",
            "tax_impact": "空壳企业无实际经营→发票为虚开→涉嫌虚开增值税专用发票罪（刑法第201720条），补税+罚款+刑事责任。",
            "policy_ref": "《刑法》第二百零五条（虚开增值税专用发票罪）；《发票管理办法》第二十二条",
            "suggestion": "立即核实：经营场所租赁合同+水电费发票+员工考勤+物流单据。如无法提供→移送税务合规。",
            "category": "跨域协商综合",
            "_negotiated": True,
        }
    },
    {
        "id": "NEG-AUG-002",
        "trigger_a": {"domain_contains": "资金流向", "type_contains": "个人"},
        "trigger_b": {"domain_contains": "收款", "type_contains": "个人待分析"},
        "trigger_c": {"domain_contains": "发票", "type_contains": "个人交易"},
        "action": "synthesize",
        "new_finding": {
            "type": "个人账户收款隐匿收入综合预警",
            "level": "极高风险",
            "score": 10,
            "detail": "跨域协商引擎综合信号：资金流个人收款+收款分类个人待分析+发票个人交易。三域独立检测均指向个人账户收款，交叉验证确认非偶然事件。个人收款未转入对公账户且与开票收入无法对应→疑似隐匿销售收入。",
            "how_found": "跨域协商引擎：资金流向追踪+收款分类+个人交易检测三域交叉研判。",
            "tax_impact": "个人账户收款未申报→偷税（征管法第61720条），处不缴或少缴税款0.5-5倍罚款。",
            "policy_ref": "《税收征收管理法》第六十三条；《刑法》第二百零一条",
            "suggestion": "逐笔核实个人收款来源和性质。如为经营性收款→补申报并补税；如为借款/注资→取得书面协议备查。",
            "category": "跨域协商综合",
            "_negotiated": True,
        }
    },
    {
        "id": "NEG-AUG-003",
        "trigger_a": {"domain_contains": "供应商", "type_contains": "名称异常"},
        "trigger_b": {"domain_contains": "关联交易", "type_contains": "重叠"},
        "trigger_c": {"domain_contains": "供应商", "type_contains": "集中度"},
        "action": "synthesize",
        "new_finding": {
            "type": "供应商群集+关联重叠综合预警",
            "level": "高风险",
            "score": 9,
            "detail": "跨域协商引擎综合信号：供应商名称异常+客户供应商重叠+供应商集中度过高。三域独立检测均指向供应商结构异常，可能为关联方借用外部供应商名义进行对倒开票。",
            "how_found": "跨域协商引擎：供应商穿透+关联交易检测+供应商画像三域交叉研判。",
            "tax_impact": "对倒开票→虚开发票→刑法第201720条。",
            "policy_ref": "《发票管理办法》第二十二条；《刑法》第二百零五条",
            "suggestion": "核实前3大供应商的工商登记信息、实际控制人、与企业的股权关联。",
            "category": "跨域协商综合",
            "_negotiated": True,
        }
    },
    
    # ── 新增：消解层扩展（覆盖原来11720条规则外的常见矛盾）──
    {
        "id": "NEG-050",
        "match_a": {"type_contains": "服务行业"},
        "negate_b": {"type_contains": "制造业成本"},
        "action": "drop",
        "reason": "企业判定为服务行业，制造业成本分析（BOM/进销存/加工费）不适用。"
    },
    {
        "id": "NEG-051",
        "match_a": {"type_contains": "个体户"},
        "negate_b": {"type_contains": "企业所得税"},
        "action": "drop",
        "reason": "个体工商户不缴纳企业所得税，相关风险标记不适用。"
    },
    {
        "id": "NEG-052",
        "match_a": {"type_contains": "小规模纳税人"},
        "negate_b": {"domain_contains": "增值税", "type_contains": "进项税额"},
        "action": "drop",
        "reason": "小规模纳税人不抵扣进项税额，进项税额异常标记不适用。"
    },
    
    # ── 降级层扩展 ──
    {
        "id": "NEG-060",
        "match_a": {"type_contains": "收款与开票金额偏差"},
        "negate_b": {"type_contains": "隐匿收入"},
        "action": "downgrade",
        "new_level": "中风险（需排除非经营收款干扰）",
        "reason": "收款偏差可能含非经营收款（注资/借款/税费返还），不能直接等于隐匿收入。需逐笔核对方可升级。"
    },
    {
        "id": "NEG-061",
        "match_a": {"type_contains": "付款与进项金额偏差"},
        "negate_b": {"type_contains": "虚列成本"},
        "action": "downgrade",
        "new_level": "中风险（需排除非经营付款干扰）",
        "reason": "付款偏差可能含投资/往来款/借款等非采购付款，不能直接等于虚列成本。需逐笔核对方可升级。"
    },
    {
        "id": "NEG-062",
        "match_a": {"domain_contains": "经营实质", "type_contains": "经营费用"},
        "negate_b": {"type_contains": "无实际经营"},
        "action": "drop",
        "reason": "经营实质域已检测到经营费用（水电/物业/租金/通信/物流），企业存在实际经营活动。'无实际经营'结论被否定。"
    },
    {
        "id": "NEG-063",
        "match_a": {"domain_contains": "银行流水"},
        "has_field": "收款构成",
        "negate_b": {"domain_contains": "增值税", "type_contains": "申报销售额偏差"},
        "action": "downgrade",
        "new_level": "低风险（银行流水≠应税收入）",
        "reason": "银行流水含股东注资/借款/往来款/退款等非应税收入，与增值税申报销售额口径不一致。不能直接以银行流水比对申报表。"
    },
    
    # ── 增强层扩展：新增联合触发规则 ──
    {
        "id": "NEG-AUG-004",
        "trigger_a": {"domain_contains": "发票", "type_contains": "红冲"},
        "trigger_b": {"domain_contains": "收款", "type_contains": "收款与开票"},
        "action": "synthesize",
        "new_finding": {
            "type": "红冲发票+收款偏离综合预警",
            "level": "高风险",
            "score": 8,
            "detail": "跨域协商引擎综合信号：存在红冲/作废发票+银行收款与开票金额偏差。可能为开票后红冲但货款已收的交易，或虚假交易后冲销——需核实红冲发票对应的资金流向。",
            "how_found": "跨域协商引擎：发票异常检测+收款分类跨域联合研判。",
            "tax_impact": "开票后红冲但货款未退→涉嫌虚开发票（发票管理办法第21720条）。补税+0.5-5倍罚款。",
            "policy_ref": "《发票管理办法》第二十二条、第三十七条",
            "suggestion": "逐笔核实红冲发票的商业实质：退货/折让/开票错误。如无商业实质→移送税务合规。",
            "category": "跨域协商综合",
            "_negotiated": True,
        }
    },
    {
        "id": "NEG-AUG-005",
        "trigger_a": {"domain_contains": "个税", "type_contains": "工资"},
        "trigger_b": {"domain_contains": "社保", "type_contains": "基数"},
        "action": "synthesize",
        "new_finding": {
            "type": "工资个税+社保基数双重偏离预警",
            "level": "高风险",
            "score": 8,
            "detail": "跨域协商引擎综合信号：个税域发现工资异常+社保域发现基数偏低。两个独立域同时检出薪酬类异常——可能为两套工资表/账外发放工资/虚列人头。",
            "how_found": "跨域协商引擎：个税分析域+社保分析域跨域联合研判。",
            "tax_impact": "两套工资表→偷逃个税+社保费。补税+滞纳金+0.5-5倍罚款。",
            "policy_ref": "《个人所得税法》；《社会保险法》第八十六条",
            "suggestion": "比对：银行代发工资流水 vs 个税申报表 vs 社保缴费基数。检查是否存在未申报的账外工资。",
            "category": "跨域协商综合",
            "_negotiated": True,
        }
    },
    {
        "id": "NEG-AUG-006",
        "trigger_a": {"domain_contains": "发票", "type_contains": "专票超期"},
        "trigger_b": {"domain_contains": "增值税", "type_contains": "进项税额"},
        "action": "synthesize",
        "new_finding": {
            "type": "专票超期未认证综合预警",
            "level": "中风险",
            "score": 7,
            "detail": "跨域协商引擎综合信号：存在增值税专用发票超期未认证+进项税额异常。可能原因：取得发票但故意不认证（隐匿采购→收入成本不配比）或发票来源存疑。",
            "how_found": "跨域协商引擎：发票认证域+增值税域跨域联合研判。",
            "tax_impact": "进项税额未充分抵扣→多缴增值税（可更正申报退税）或隐匿采购→企业所得税少列成本→多缴所得税（不利企业但可能为虚增利润需求）。",
            "policy_ref": "《中华人民共和国增值税法》第八条；国家税务总局公告2019年第45号",
            "suggestion": "核实专票未认证原因。如为真实采购→申请逾期抵扣；如为不实发票→启动税务合规。",
            "category": "跨域协商综合",
            "_negotiated": True,
        }
    },
    {
        "id": "NEG-AUG-007",
        "trigger_a": {"domain_contains": "资金流", "type_contains": "个人"},
        "trigger_b": {"domain_contains": "关联交易", "type_contains": "股东"},
        "action": "synthesize",
        "new_finding": {
            "type": "股东个人账户与企业资金混同预警",
            "level": "极高风险",
            "score": 10,
            "detail": "跨域协商引擎综合信号：资金流向追踪检测到大量个人账户交易+关联交易域检测到股东资金往来。股东个人账户与企业公户资金混同→涉嫌公司人格混同+偷逃税款。",
            "how_found": "跨域协商引擎：资金流向追踪+关联交易检测跨域联合研判。",
            "tax_impact": "公司人格混同→股东对公司债务承担连带责任。个人账户收款未申报→偷税（征管法第61720条）。视同分红→20%个税。",
            "policy_ref": "《公司法》第二十条；《税收征收管理法》第六十三条；《个人所得税法》",
            "suggestion": "立即核实股东个人账户流水的性质和用途。经营性收入→补申报+补税；借款→补签借款协议并约定利息。建议企业开设独立的对公账户。",
            "category": "跨域协商综合",
            "_negotiated": True,
        }
    },
    {
        "id": "NEG-AUG-008",
        "trigger_a": {"domain_contains": "经营实质", "type_contains": "新办企业"},
        "trigger_b": {"domain_contains": "发票", "type_contains": "大额开票"},
        "action": "synthesize",
        "new_finding": {
            "type": "新办企业大额开票综合预警",
            "level": "极高风险",
            "score": 10,
            "detail": "跨域协商引擎综合信号：经营实质域判定为新办企业+发票域检测到大额开票。新办企业在短期内大额开票——可能为虚开团伙设立的空壳开票公司。",
            "how_found": "跨域协商引擎：经营实质分析+发票异常检测跨域联合研判。",
            "tax_impact": "开票后注销跑路→暴力虚开→刑法第201720条虚开增值税专用发票罪。",
            "policy_ref": "《刑法》第二百零五条；《发票管理办法》第二十二条",
            "suggestion": "立即核实：企业实际经营场所+员工+设备+银行流水。如为空壳→立即移送公安经侦。",
            "category": "跨域协商综合",
            "_negotiated": True,
        }
    },
    {
        "id": "NEG-AUG-009",
        "trigger_a": {"domain_contains": "成本费用", "type_contains": "劳务"},
        "trigger_b": {"domain_contains": "个税", "type_contains": "多处"},
        "action": "synthesize",
        "new_finding": {
            "type": "劳务派遣+多处工资综合预警",
            "level": "高风险",
            "score": 8,
            "detail": "跨域协商引擎综合信号：成本费用域检测到劳务派遣成本+个税域检测到多处取得工资。可能通过劳务派遣公司拆分工资、虚列人头降低个税和社保基数。",
            "how_found": "跨域协商引擎：成本费用域+个税域跨域联合研判。",
            "tax_impact": "拆分工资→少缴个税+社保。劳务派遣无实际业务→虚开发票。补税+滞纳金+罚款。",
            "policy_ref": "《个人所得税法》；《劳务派遣暂行规定》",
            "suggestion": "核实劳务派遣合同+派遣人员名单+考勤记录+工资发放记录。如无实际用工→移送税务合规。",
            "category": "跨域协商综合",
            "_negotiated": True,
        }
    },
    {
        "id": "NEG-AUG-010",
        "trigger_a": {"domain_contains": "资金流", "type_contains": "境外"},
        "trigger_b": {"domain_contains": "跨境", "type_contains": "外汇"},
        "action": "synthesize",
        "new_finding": {
            "type": "境外付款+外汇管理综合预警",
            "level": "高风险",
            "score": 8,
            "detail": "跨域协商引擎综合信号：资金流域检测到境外付款+跨域分析域检测到外汇相关信号。境外付款可能涉及：①代扣代缴义务（增值税+预提所得税）②转让定价③利润转移。",
            "how_found": "跨域协商引擎：资金流向追踪+跨域分析联合研判。",
            "tax_impact": "未扣缴预提所得税→补税+滞纳金。转让定价→特别纳税调整。",
            "policy_ref": "《企业所得税法》第三十七条（预提所得税）；《特别纳税调整实施办法》",
            "suggestion": "核实：①境外收款方身份（是否关联方）②合同内容（特许权/服务费/利息/股息）③是否已扣缴税款。",
            "category": "跨域协商综合",
            "_negotiated": True,
        }
    },
]

def run_negotiation(all_findings, pipeline_log=None):
    """
    执行跨域协商：在所有域分析完成后、报告生成前调用。
    
    Args:
        all_findings: [(domain_name, finding_dict), ...] 或 [finding_dict, ...]
        pipeline_log: 可选日志列表
    
    Returns:
        调整后的 findings 列表 + 协商日志
    """
    if pipeline_log is None:
        pipeline_log = []
    
    if not all_findings:
        return all_findings, pipeline_log
    
    # 统一格式：如果是 (domain, findings) 的元组列表，展平
    if isinstance(all_findings[0], tuple):
        flattened = []
        for domain_name, findings in all_findings:
            for f in findings:
                if isinstance(f, dict):
                    f["_domain"] = domain_name
                flattened.append(f)
        all_findings = flattened
    
    # 构建索引：按类型、域、关键词分组
    type_index = defaultdict(list)
    domain_index = defaultdict(list)
    tag_index = defaultdict(list)
    
    for i, f in enumerate(all_findings):
        if not isinstance(f, dict):
            continue
        t = f.get("type", "")
        d = f.get("_domain", "") or f.get("category", "")
        type_index[t].append(i)
        domain_index[d].append(i)
        for tag in (f.get("_tags", []) or []):
            tag_index[tag].append(i)
    
    negotiations_log = []
    dropped = set()
    modified = set()
    synthesized = []
    
    # ── 逐条应用协商规则 ──
    for rule in NEGOTIATION_RULES:
        rule_id = rule["id"]
        action = rule.get("action", "drop")
        
        # 步骤1：查找匹配的条件A
        matched_a = _find_matching_findings(all_findings, rule.get("match_a", {}), type_index, domain_index)
        if not matched_a and "match_a" in rule:
            continue
        
        # 步骤2：对于增强层，检查所有触发器
        if action == "synthesize":
            triggers = [rule.get("trigger_a"), rule.get("trigger_b")]
            if "trigger_c" in rule:
                triggers.append(rule.get("trigger_c"))
            
            all_triggered = True
            for trigger in triggers:
                if not trigger:
                    continue
                matched = _find_matching_findings(all_findings, trigger, type_index, domain_index)
                if not matched:
                    all_triggered = False
                    break
            
            if all_triggered:
                new_f = dict(rule["new_finding"])
                all_findings.append(new_f)
                synthesized.append(new_f)
                negotiations_log.append(f"[NEG {rule_id}] 综合增强: {new_f['type']}")
            continue
        
        # 步骤3：查找需要被消解/降级/标记的发现B
        negate_rule = rule.get("negate_b", {})
        targets = _find_matching_findings(all_findings, negate_rule, type_index, domain_index)
        
        for idx in targets:
            if idx in dropped:
                continue
            f = all_findings[idx]
            
            if action == "drop":
                # 检查额外条件
                if "has_field" in rule and not _has_field(f, rule["has_field"]):
                    continue
                if "not_tagged" in rule and (rule["not_tagged"] in (f.get("_tags", []) or [])):
                    continue
                
                f["_negotiated_drop"] = True
                f["_drop_reason"] = rule["reason"]
                dropped.add(idx)
                negotiations_log.append(f"[NEG {rule_id}] 消解: {f.get('type','?')} — {rule['reason']}")
                
            elif action == "downgrade":
                old_level = f.get("level", "")
                f["level"] = rule.get("new_level", old_level)
                f["score"] = min(f.get("score", 5), 3)
                f["_negotiated"] = True
                f["_negotiation_reason"] = rule["reason"]
                modified.add(idx)
                negotiations_log.append(f"[NEG {rule_id}] 降级: {f.get('type','?')} {old_level}→{f['level']}")
                
            elif action == "mark":
                tag = rule.get("add_tag", "")
                if not f.get("_tags"):
                    f["_tags"] = []
                if tag and tag not in f["_tags"]:
                    f["_tags"].append(tag)
                    f["_negotiated"] = True
                    f["_negotiation_reason"] = rule["reason"]
                    modified.add(idx)
                    negotiations_log.append(f"[NEG {rule_id}] 标记: {f.get('type','?')} +{tag}")
    
    # ── 清理被消解的发现（标记但不删除，让报告知道这是协商结果） ──
    # 保持所有发现，仅标记。报告渲染时可选择隐藏 _negotiated_drop=True 的发现
    
    if pipeline_log is not None:
        pipeline_log.extend(negotiations_log)
        total = len(dropped) + len(modified) + len(synthesized)
        if total > 0:
            pipeline_log.append(f"[协商引擎] 完成：消解{len(dropped)}条 + 降级/标记{len(modified)}条 + 综合增强{len(synthesized)}条")
    
    return all_findings, negotiations_log


def _find_matching_findings(all_findings, match_rule, type_index, domain_index):
    """根据匹配规则查找符合条件的发现索引列表"""
    if not match_rule:
        return []
    
    candidates = set(range(len(all_findings)))
    
    # 按type精确匹配
    if "type" in match_rule:
        t = match_rule["type"]
        if t in type_index:
            candidates &= set(type_index[t])
        else:
            return []
    
    # 按type包含匹配
    if "type_contains" in match_rule:
        tc = match_rule["type_contains"]
        matched = set()
        for t, indices in type_index.items():
            if tc in t:
                matched.update(indices)
        candidates &= matched
        if not candidates:
            return []
    
    # 按domain匹配
    if "domain" in match_rule:
        d = match_rule["domain"]
        if d in domain_index:
            candidates &= set(domain_index[d])
        else:
            return []
    
    # 按domain包含匹配
    if "domain_contains" in match_rule:
        dc = match_rule["domain_contains"]
        matched = set()
        for d, indices in domain_index.items():
            if dc in d:
                matched.update(indices)
        candidates &= matched
        if not candidates:
            return []
    
    # 按how_found内容匹配
    if "how_found_contains" in match_rule:
        hfc = match_rule["how_found_contains"]
        matched = set()
        for i in candidates:
            f = all_findings[i]
            if hfc in (f.get("how_found", "") or ""):
                matched.add(i)
        candidates &= matched
        if not candidates:
            return []
    
    # 按category包含匹配
    if "category_contains" in match_rule:
        cc = match_rule["category_contains"]
        matched = set()
        for i in candidates:
            f = all_findings[i]
            if cc in (f.get("category", "") or ""):
                matched.add(i)
        candidates &= matched
        if not candidates:
            return []
    
    # 按level过滤
    if "level" in match_rule:
        matched = set()
        for i in candidates:
            if all_findings[i].get("level") == match_rule["level"]:
                matched.add(i)
        candidates &= matched
        if not candidates:
            return []
    
    # 按结论字段匹配
    if "结论" in match_rule:
        matched = set()
        for i in candidates:
            f = all_findings[i]
            detail = f.get("detail", "") or ""
            if match_rule["结论"] in detail:
                matched.add(i)
        candidates &= matched
        if not candidates:
            return []
    
    # 清理：排除已标记为消解的
    valid = []
    for i in candidates:
        f = all_findings[i]
        if not f.get("_negotiated_drop"):
            valid.append(i)
    
    return valid


def _has_field(finding, field_name):
    """检查发现是否有指定字段且非空"""
    val = finding.get(field_name)
    if val is None:
        return False
    if isinstance(val, (list, dict)):
        return bool(val)
    if isinstance(val, str):
        return len(val.strip()) > 0
    return bool(val)


def _has_item_keyword(finding, keyword):
    """检查发现的items列表中是否有包含关键词的项"""
    items = finding.get("items", []) or []
    for item in items:
        for k, v in item.items():
            if keyword in str(v):
                return True
    return False
