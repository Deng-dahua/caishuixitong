"""
AGI 处长级能力模块 — 7大高级推理能力

P0: 不确定性量化    — 每条发现标注置信度+不确定性来源+消除方法
P1: 经济实质穿透    — 穿透发票看交易实质（金额/品名/时间/资质四维）
P1: 跨税种综合判断  — 一笔交易同时触发增值税/所得税/印花税连锁判断
P2: 深度调查对话    — 回答末尾追加探测性问题，引导补充资料
P2: 税务筹划建议    — 不仅找问题，还给出合规优化路径
P3: 生命周期自适应  — 初创期/成长期/成熟期不同风险标准
P3: 自主调查决策    — 分析完主动列出资料缺口+影响+建议补充清单
"""
import json, os, math
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict


class DirectorEngine:
    """税务合规处长级推理引擎"""
    
    # ═══════ 不确定因素加权库 ═══════
    UNCERTAINTY_SOURCES = {
        "缺银行对账单": {"weight": 0.3, "desc": "无法比对银行流水真实性，资金回流检测失效"},
        "缺合同": {"weight": 0.2, "desc": "无法核定交易商业实质，印花税无法核定"},
        "缺记账凭证": {"weight": 0.2, "desc": "无法验证账务记录准确性"},
        "缺申报表": {"weight": 0.15, "desc": "无法比对申报数据与实际数据"},
        "缺工资表": {"weight": 0.15, "desc": "无法核实个税申报和社保基数"},
        "缺进销存台账": {"weight": 0.15, "desc": "无法验证进销逻辑和BOM映射"},
        "单源证据": {"weight": 0.15, "desc": "仅单一数据源，缺乏交叉验证"},
        "缺少法条引用": {"weight": 0.1, "desc": "法律依据不明确"},
        "行业数据缺失": {"weight": 0.1, "desc": "无行业基准做对标"},
        "历史数据不足": {"weight": 0.1, "desc": "新企业或数据量少，统计意义弱"},
    }
    
    # ═══════ 经济实质穿透：四维异常检测 ═══════
    ECONOMIC_SUBSTANCE_CHECKS = {
        "咨询费": {
            "require": ["合同", "成果交付物", "服务内容说明"],
            "red_flags": ["大额整数", "集中支付", "无对应咨询成果", "非营业时间内付款"],
            "penetration": "咨询费大额整数且无可核实的服务成果→可能为走账/虚假交易",
        },
        "加工费": {
            "require": ["加工合同", "运输发票", "入库单"],
            "red_flags": ["无运输发票", "加工方无加工能力", "加工费与行业标准偏差>30%"],
            "penetration": "加工费无对应运输发票→货物流真实性存疑→可能为虚开发票",
        },
        "服务费": {
            "require": ["服务合同", "服务成果", "银行流水"],
            "red_flags": ["高频小额", "对私转账", "服务内容模糊"],
            "penetration": "服务费高频小额且对私支付→可能为分解工资或回扣",
        },
        "采购款": {
            "require": ["采购合同", "入库单", "运输发票"],
            "red_flags": ["供应商同城集中", "无物流记录", "采购价格异常偏离"],
            "penetration": "采购款无入库+无运输→存在虚假采购/虚增成本嫌疑",
        },
        "设备款": {
            "require": ["采购合同", "验收单", "固定资产卡片"],
            "red_flags": ["设备价格异常", "设备型号与经营范围不匹配"],
            "penetration": "设备款无验收记录且金额异常→可能为虚假资产/虚增抵扣",
        },
    }
    
    # ═══════ 跨税种影响矩阵 ═══════
    CROSS_TAX_MATRIX = {
        "未开票收入": {
            "增值税": ("少缴销项税额", f"未开票收入×(13%或9%或6%)"),
            "企业所得税": ("隐匿收入", f"未开票收入×25%"),
            "印花税": ("漏缴购销合同印花税", f"未开票收入×0.03%"),
            "城建税教育费附加": ("少缴附加税费", f"少缴增值税×(7%+3%+2%)"),
        },
        "虚开发票": {
            "增值税": ("虚增进项税额", "虚开金额×税率"),
            "企业所得税": ("虚增成本费用", "虚开金额×25%"),
            "印花税": ("虚假合同印花税", "虚开金额×0.03%"),
        },
        "隐匿收入": {
            "增值税": ("少申报销项税额", "隐匿金额×税率"),
            "企业所得税": ("少申报应纳税所得额", "隐匿金额×25%"),
        },
        "虚增成本": {
            "增值税": ("多抵扣进项税额", "虚增金额×税率"),
            "企业所得税": ("少申报应纳税所得额", "虚增金额×25%"),
        },
        "工资两套账": {
            "个人所得税": ("少代扣代缴个税", "未申报工资金额×适用税率"),
            "企业所得税": ("虚增工资费用", "未申报工资金额×25%"),
            "社保费": ("少缴社保费", "未申报工资金额×社保费率"),
        },
    }
    
    # ═══════ 生命周期风险模型 ═══════
    LIFECYCLE_MODEL = {
        "初创期": {  # 成立0-2年
            "risk_tolerance": "宽松",
            "focus": ["企业资质真实性", "初始投资来源", "业务开展能力"],
            "relaxed_rules": ["进销比放宽至1.5", "利润率-30%至+50%均可接受"],
            "strict_rules": ["注册资本实缴情况", "发票领用与业务量匹配"],
        },
        "成长期": {  # 成立2-5年
            "risk_tolerance": "标准",
            "focus": ["收入增速合理性", "人员规模变化", "客户结构变化"],
            "relaxed_rules": [],
            "strict_rules": ["利润率跳跃>30%需说明原因", "大额新增供应商需核查"],
        },
        "成熟期": {  # 成立5年以上
            "risk_tolerance": "严格",
            "focus": ["税负率稳定性", "关联交易合理性", "利润持续性"],
            "relaxed_rules": [],
            "strict_rules": ["税负率波动>1%需核查", "关联交易定价需符合独立交易原则", "利润大起大落需穿透核查"],
        },
    }
    
    # ═══════ 税务筹划建议库 ═══════
    TAX_PLANNING_ADVICE = {
        "增值税税负率异常": "如确因行业特性(如出口占比高)导致税负率偏低，可申请适用简易计税或免税政策。提供完整出口报关单和收汇凭证即可。",
        "企业所得税偏高": "核查是否有符合加计扣除条件的研发费用未申报。研发费用可100%加计扣除。高新技术企业可申请15%优惠税率。",
        "个税申报不足": "合理利用专项附加扣除(子女教育/继续教育/大病医疗/房贷利息/住房租金/赡养老人)可在合法范围内降低税负。",
        "社保基数不符": "社保基数有上下限(社平工资60%-300%)，如在合理范围内可合规调整。非全日制用工可单独缴纳工伤保险。",
        "小型微利企业": "年应纳税所得额≤300万的企业，减按25%计入应纳税所得额按20%税率缴纳。合理拆分公司可适用此优惠但必须符合独立经营标准。",
        "进项税额转出过多": "建立完善的进项税额用途分类制度，对共同用途的进项税额按合理方法分摊可抵扣部分。",
    }
    
    def __init__(self):
        self._history: List[Dict] = []
    
    # ═══════ P0: 不确定性量化 ═══════
    def quantify_uncertainty(self, finding: Dict, materials: Dict) -> Dict:
        """
        量化单条发现的不确定性
        
        返回: {confidence, uncertainties, max_confidence, what_needed}
        """
        ev = finding.get("evidence", []) or finding.get("evidence_rows", []) or finding.get("items", []) or []
        has_policy = bool((finding.get("policy_ref", "") or "").strip())
        has_source = bool((finding.get("how_found", "") or "").strip())
        has_domain = bool(finding.get("domain", "") or finding.get("category", ""))
        
        # 基础分：有证据+3，有法条+2，有溯源+2，有分析域+1
        base_score = 3.0
        uncertainties = []
        
        ev_count = len(ev)
        if ev_count >= 3:
            base_score += 2.0
        elif ev_count >= 1:
            base_score += 1.0
            uncertainties.append({
                "source": "单源证据",
                "impact": self.UNCERTAINTY_SOURCES["单源证据"]["weight"],
                "desc": self.UNCERTAINTY_SOURCES["单源证据"]["desc"],
                "fix": "增加至少1个其他数据源的交叉验证",
            })
        else:
            base_score += 0.0
            uncertainties.append({
                "source": "缺证据材料",
                "impact": 0.25,
                "desc": "该发现无任何具体证据材料支撑",
                "fix": "补充合同/发票/银行对账单等原始资料",
            })
        
        if not has_policy:
            uncertainties.append({
                "source": "缺少法条引用",
                "impact": 0.1,
                "desc": self.UNCERTAINTY_SOURCES["缺少法条引用"]["desc"],
                "fix": "在发现中补充引用的法律条文",
            })
        
        if not has_source:
            uncertainties.append({
                "source": "缺少数据溯源",
                "impact": 0.1,
                "desc": "无法追溯数据分析方法和数据来源",
                "fix": "补充how_found字段说明分析方法",
            })
        
        # 资料缺口带来的不确定性
        if isinstance(materials, dict):
            for k, v in materials.items():
                if isinstance(v, dict) and not v.get("exists", True):
                    src_info = self.UNCERTAINTY_SOURCES.get(f"缺{k}", {})
                    if src_info:
                        uncertainties.append({
                            "source": f"缺{k}",
                            "impact": src_info.get("weight", 0.1),
                            "desc": src_info.get("desc", f"缺少{k}影响判断"),
                            "fix": f"补充{k}资料",
                        })
        
        total_uncertainty = sum(u["impact"] for u in uncertainties)
        confidence = min(0.95, base_score / 10.0)
        confidence -= total_uncertainty * 0.5
        confidence = max(0.1, confidence)
        
        max_confidence = min(0.95, confidence + total_uncertainty * 0.5)
        
        return {
            "confidence": round(confidence, 2),
            "max_confidence": round(max_confidence, 2),
            "uncertainties": uncertainties,
            "level": "高可信" if confidence >= 0.7 else ("中等可信" if confidence >= 0.4 else "低可信"),
            "what_needed": [u["fix"] for u in uncertainties[:3]],
            "summary": (
                f"置信度{confidence:.0%}"
                + (f"（如补充{'、'.join([u['source'] for u in uncertainties[:2]])}可提升至{max_confidence:.0%}）" if uncertainties else "")
            ),
        }
    
    # ═══════ P1: 经济实质穿透 ═══════
    def penetrate_essence(self, finding: Dict, invoices: List[Dict] = None) -> Dict:
        """
        穿透发票看交易经济实质
        
        四维检测：金额/品名/时间/对方资质
        """
        ftype = finding.get("type", "")
        fdetail = finding.get("detail", "")
        ftext = ftype + (fdetail or "")
        
        flags = []
        penetration = ""
        required_docs = []
        
        # 匹配预定义的经济实质检查
        for keyword, check in self.ECONOMIC_SUBSTANCE_CHECKS.items():
            if keyword in ftext:
                required_docs = check["require"]
                
                # 检查红旗信号
                red_flags_found = []
                for rf in check["red_flags"]:
                    trigger_words = rf.replace("服务成果", "").replace("无", "没有").strip()
                    if any(word in ftext for word in trigger_words.split("|")):
                        red_flags_found.append(rf)
                
                if red_flags_found:
                    flags.extend(red_flags_found)
                    penetration = check["penetration"]
                break
        
        # 通用穿透逻辑
        ev = finding.get("evidence_rows", []) or finding.get("items", []) or []
        total_amount = 0
        for ei in ev:
            try:
                if isinstance(ei, dict):
                    total_amount += float(str(ei.get("amount", "0")).replace(",", ""))
            except: pass
        
        # 金额异常检测
        if total_amount > 100000 and total_amount % 10000 == 0:
            flags.append("大额整数交易（可能存在资金回流）")
        
        # 单一对方检测
        counterparties = set()
        for ei in ev:
            cp = ei.get("counterparty", ei.get("对方", "")) if isinstance(ei, dict) else ""
            if cp: counterparties.add(cp)
        if len(counterparties) == 1 and len(ev) > 3:
            flags.append(f"交易集中于单一对方（{list(counterparties)[0]}）")
        
        return {
            "penetrated": bool(flags),
            "flags": flags[:5],
            "penetration_analysis": penetration or "未检测到明显经济实质异常",
            "required_documents": required_docs[:3],
            "substance_risk": "高风险" if len(flags) >= 3 else ("中风险" if flags else "低风险"),
            "recommendation": (
                f"建议补充{'、'.join(required_docs[:2])}以验证交易经济实质" if required_docs
                else "建议核实交易商业目的和定价合理性"
            ),
        }
    
    # ═══════ P1: 跨税种综合判断 ═══════
    def cross_tax_chain(self, findings: List[Dict]) -> Dict:
        """
        一笔交易同时触发多个税种的连锁判断
        """
        chains = []
        
        for f in findings:
            ftype = f.get("type", "")
            
            # 匹配跨税种矩阵
            for pattern, tax_impacts in self.CROSS_TAX_MATRIX.items():
                if pattern in ftype or any(kw in ftype for kw in pattern.split() if len(kw) >= 2):
                    chain = {
                        "trigger": ftype[:60],
                        "finding": f.get("detail", "")[:100],
                        "cross_impacts": [],
                        "total_estimated": {},
                    }
                    
                    for tax_name, (impact_desc, calc_formula) in tax_impacts.items():
                        chain["cross_impacts"].append({
                            "tax": tax_name,
                            "impact": impact_desc,
                            "estimation": calc_formula,
                        })
                    
                    chains.append(chain)
                    break
        
        # 检测潜在跨税种问题（不在发现中但应该检查的）
        all_types = set(f.get("type", "") for f in findings)
        potential = []
        
        if any("增值税" in t for t in all_types) and not any("城建税" in t or "附加" in t for t in all_types):
            potential.append("⚠️ 检测到增值税问题但未触发城建税及教育费附加检查")
        if any("收入" in t or "收款" in t for t in all_types) and not any("所得税" in t for t in all_types):
            potential.append("⚠️ 检测到收入相关问题但未触发企业所得税检查")
        if any("采购" in t or "发票" in t for t in all_types) and not any("印花税" in t for t in all_types):
            potential.append("⚠️ 检测到购销交易但未触发印花税检查")
        
        return {
            "chains_found": chains[:5],
            "potential_gaps": potential,
            "summary": (
                f"发现{len(chains)}条跨税种影响链"
                + (f"，另有{len(potential)}个潜在盲区" if potential else "")
            ),
        }
    
    # ═══════ P2: 深度调查对话 ═══════
    def generate_probing_questions(self, finding: Dict, uncertainty: Dict) -> List[str]:
        """
        生成探测性问题——回答不再是终点，是调查的起点
        """
        questions = []
        ftype = finding.get("type", "")
        flevel = finding.get("level", "")
        gaps = uncertainty.get("uncertainties", [])
        
        # 针对证据缺失
        for gap in gaps[:3]:
            src = gap.get("source", "")
            if "银行" in src or "对账单" in src:
                questions.append("📋 是否有该期间完整的银行对账单？对账单对方户名是否与发票销售方一致？")
            elif "合同" in src:
                questions.append("📄 是否有对应的业务合同？合同金额是否与发票金额一致？")
            elif "运输" in src or "物流" in src:
                questions.append("🚛 该笔交易是否有运输记录或物流单据？发货地址是否与供应商地址匹配？")
            elif "申报表" in src:
                questions.append("📊 是否有该期间的纳税申报表？申报数据与实际账务数据是否一致？")
            elif "记账凭证" in src:
                questions.append("📝 该笔交易的记账凭证是否完整？会计分录是否正确？")
            elif "工资" in src or "社保" in src:
                questions.append("👤 是否有完整的工资表和社保申报记录？实发工资与应发工资是否一致？")
        
        # 针对高风险
        if flevel in ("高风险", "极高风险"):
            questions.append("🔍 建议对该交易进行穿透核查——核实资金最终流向和商业实质。")
        
        # 针对经济实质
        if "虚开" in ftype or "发票" in ftype:
            questions.append("🏢 已查过供应商的工商信息吗？是否有实际经营能力？")
        if "收入" in ftype or "收款" in ftype:
            questions.append("💳 银行流水的对方户名与客户名称是否一致？有无关联方本人转账？")
        
        return questions[:5]
    
    # ═══════ P2: 税务筹划建议 ═══════
    def get_planning_advice(self, finding: Dict) -> Optional[str]:
        """给出合法的税务优化路径"""
        ftype = finding.get("type", "")
        
        for keyword, advice in self.TAX_PLANNING_ADVICE.items():
            if keyword in ftype or any(kw in ftype for kw in keyword.split() if len(kw) >= 2):
                return advice
        
        # 通用建议
        if "风险" in ftype or "异常" in ftype:
            return "建议聘请专业税务顾问进行全面的税务健康检查，评估合规优化空间。"
        
        return None
    
    # ═══════ P3: 企业生命周期自适应 ═══════
    def get_lifecycle_context(self, company_age_years: float) -> Dict:
        """根据企业成立年限返回适配的风险标准"""
        if company_age_years <= 2:
            stage = "初创期"
        elif company_age_years <= 5:
            stage = "成长期"
        else:
            stage = "成熟期"
        
        model = self.LIFECYCLE_MODEL.get(stage, self.LIFECYCLE_MODEL["成熟期"])
        
        return {
            "stage": stage,
            "years": company_age_years,
            "tolerance": model["risk_tolerance"],
            "focus_areas": model["focus"],
            "relaxed_rules": model["relaxed_rules"],
            "strict_rules": model["strict_rules"],
            "advice": (
                f"企业处于{stage}，风险容忍度为「{model['risk_tolerance']}」。"
                f"重点关注：{'、'.join(model['focus'][:3])}。"
            ),
        }
    
    # ═══════ P3: 自主调查决策 ═══════
    def generate_investigation_plan(self, findings: List[Dict], materials: Dict) -> Dict:
        """分析完后主动生成资料缺口+影响+建议补充清单"""
        plan = {
            "missing_materials": [],
            "investigation_steps": [],
            "priority_actions": [],
        }
        
        # 检测缺失资料
        if isinstance(materials, dict):
            for k, v in materials.items():
                if isinstance(v, dict) and not v.get("exists", True):
                    src_info = self.UNCERTAINTY_SOURCES.get(f"缺{k}", {})
                    plan["missing_materials"].append({
                        "material": k,
                        "impact": src_info.get("desc", "影响分析完整性"),
                        "affected_analyses": v.get("affected", []) if isinstance(v, dict) else [],
                    })
        
        # 根据发现生成调查步骤
        high_risk = [f for f in findings if f.get("level") in ("高风险", "极高风险")]
        for f in high_risk[:5]:
            plan["investigation_steps"].append({
                "finding": f.get("type", "")[:60],
                "step": self._get_investigation_step(f),
                "priority": "高" if f.get("level") == "极高风险" else "中",
            })
        
        # 优先行动
        if plan["missing_materials"]:
            plan["priority_actions"].append({
                "action": f"补充缺失的{len(plan['missing_materials'])}类资料",
                "details": [m["material"] for m in plan["missing_materials"][:5]],
            })
        
        if high_risk:
            plan["priority_actions"].append({
                "action": f"对{len(high_risk)}项高风险发现进行穿透核查",
                "details": [f.get("type", "")[:40] for f in high_risk[:3]],
            })
        
        return plan
    
    def _get_investigation_step(self, finding: Dict) -> str:
        ftype = finding.get("type", "")
        if "虚开" in ftype:
            return "调取供应商工商信息+银行对账单+物流单据，四维比对验证交易真实性"
        if "收入" in ftype or "隐匿" in ftype:
            return "比对银行流水收款记录与开票记录，核查差异原因的合理性"
        if "成本" in ftype or "费用" in ftype:
            return "抽查大额成本费用对应的合同+发票+付款凭证，验证三单一致"
        if "发票" in ftype:
            return "调取全量进销项发票，做逐票比对+品名映射+金额匹配分析"
        return "根据发现类型进行专项核查"


# 全局处长引擎
director = DirectorEngine()

def get_director() -> DirectorEngine:
    return director
