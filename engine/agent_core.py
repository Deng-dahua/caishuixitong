"""
财税智能体核心引擎 —— AgentCore

五层架构：感知→推理→学习→表达→记忆
设计哲学：不只是规则引擎，而是像一个真正的税务稽查员一样思考。

能力边界：
  ✅ 假设驱动分析 — 基于数据模式主动生成调查假设
  ✅ 跨分析学习 — 从历史案例中归纳行业通用模式
  ✅ 自我反思 — 对每个结论进行反向假设验证
  ✅ 洞见总结 — 生成有因果推理的综合性报告
  ✅ 可追溯解释 — 每个结论可追溯到原始数据

核心创新：
  1. 主动假设生成：不只等规则触发，而是主动问"这个企业可能有什么问题？"
  2. 模式归纳：从多个企业的分析中归纳行业通用风险模式
  3. 自我质疑：每条结论生成反向假设并尝试证伪
  4. 记忆积累：每次分析成为经验，提升下次分析质量
"""
import json, os, time, re, uuid
from datetime import datetime
from collections import defaultdict, Counter
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field, asdict

# ==================== 数据类 ====================

@dataclass
class Hypothesis:
    """调查假设"""
    id: str
    description: str          # 假设描述：这家企业可能虚开进项发票
    trigger_signals: List[str] # 触发信号
    confidence: float          # 初始置信度 0-1
    evidence_for: List[Dict] = field(default_factory=list)
    evidence_against: List[Dict] = field(default_factory=list)
    verified: Optional[bool] = None
    final_confidence: float = 0.0
    causal_chain: List[str] = field(default_factory=list)

@dataclass
class AnalysisMemory:
    """分析记忆——每次分析的完整快照"""
    trace_id: str
    company_id: int
    company_name: str
    industry: str
    biz_model: str
    timestamp: str
    key_findings_count: int
    high_risk_count: int
    generated_hypotheses: int
    verified_hypotheses: int
    learning_points: List[str] = field(default_factory=list)
    data_profile: Dict = field(default_factory=dict)

@dataclass
class IndustryPattern:
    """行业通用风险模式"""
    industry: str
    pattern_name: str
    description: str
    trigger_conditions: List[str]
    occurrence_count: int
    confidence: float
    last_seen: str
    companies_affected: List[str] = field(default_factory=list)

# ==================== 1. 假设生成器 ====================

class HypothesisGenerator:
    """基于数据模式主动生成调查假设
    
    不像规则引擎那样被动等待触发，而是主动思考：
    - 看到进项发票中加工费占比高 → 生成"委托加工真实性"假设
    - 看到供应商高度集中在同城 → 生成"关联交易/虚开发票"假设
    - 看到银行收款远超开票 → 生成"隐匿收入"假设
    """
    
    HYPOTHESIS_TEMPLATES = [
        {
            "id": "H001", "name": "隐匿销售收入",
            "trigger": lambda ctx: ctx.get("bank_in_ratio", 0) > 1.3 and ctx.get("invoice_count", 0) > 5,
            "confidence": lambda ctx: min(0.95, (ctx.get("bank_in_ratio", 1) - 1) * 0.7),
            "description": lambda ctx: f"银行收款为开票收入的{ctx.get('bank_in_ratio',0):.1f}倍，可能存在未申报销售收入",
            "investigation_chain": [
                "逐户比对银行收款方与销项发票客户名称",
                "计算未匹配收款的金额和占比",
                "排查非经营性收款（注资、借款、往来款）",
                "无法说明来源的差额按隐匿收入处理"
            ]
        },
        {
            "id": "H002", "name": "虚开进项发票",
            "trigger": lambda ctx: ctx.get("supplier_concentration", 0) > 0.6 and ctx.get("pur_count", 0) > 10,
            "confidence": lambda ctx: min(0.9, ctx.get("supplier_concentration", 0) * 1.2),
            "description": lambda ctx: f"供应商高度集中({ctx.get('supplier_concentration',0):.0%}集中在少数供应商)，可能虚开进项",
            "investigation_chain": [
                "联网核查主要供应商的工商状态（天眼查/企查查）",
                "比对供应商注册地址是否住宅/虚拟地址",
                "核查银行付款记录——无付款的进项发票进项税额转出",
                "核查物流单据——无运输凭证的采购无法证实货物真实流转"
            ]
        },
        {
            "id": "H003", "name": "委托加工真实性存疑",
            "trigger": lambda ctx: ctx.get("has_processing_fee", False) and ctx.get("pur_count", 0) > 5,
            "confidence": lambda ctx: 0.7 if ctx.get("has_processing_fee") else 0.0,
            "description": "进项发票中含加工费，需核实委托加工的真实性",
            "investigation_chain": [
                "BOM验证：投入产出比率是否合理",
                "加工商地址核查：运输成本是否匹配",
                "加工合同：是否有书面委托加工协议",
                "资金流核查：加工费付款方是否为企业对公账户"
            ]
        },
        {
            "id": "H004", "name": "关联交易转移利润",
            "trigger": lambda ctx: ctx.get("has_related_parties", False) or ctx.get("has_six_personnel_overlap", False),
            "confidence": lambda ctx: 0.8 if ctx.get("has_related_parties") else 0.5,
            "description": "存在关联方或人员重叠，可能存在转移定价/利润转移",
            "investigation_chain": [
                "核查关联交易的定价是否公允（独立交易原则）",
                "比对关联方与非关联方的毛利率差异",
                "检查是否存在资金回流（付款后回流到控制人账户）",
                "评估是否存在不合理分摊费用/让渡利润"
            ]
        },
        {
            "id": "H005", "name": "虚列成本费用",
            "trigger": lambda ctx: ctx.get("pur_without_payment_ratio", 0) > 0.3 and ctx.get("pur_count", 0) > 10,
            "confidence": lambda ctx: min(0.85, ctx.get("pur_without_payment_ratio", 0) * 1.5),
            "description": lambda ctx: f"{ctx.get('pur_without_payment_ratio',0):.0%}的进项发票无对应银行付款，可能虚列成本",
            "investigation_chain": [
                "逐笔核实无付款进项发票的真实性",
                "核查是否存在现金交易——但大额交易必须银行转账",
                "取得供应商确认函或对账单",
                "无法证实真实的进项发票做进项税额转出"
            ]
        },
        {
            "id": "H006", "name": "进销品名不匹配",
            "trigger": lambda ctx: ctx.get("goods_mismatch_ratio", 0) > 0.3 and ctx.get("sal_count", 0) > 5,
            "confidence": lambda ctx: min(0.85, ctx.get("goods_mismatch_ratio", 0) * 2),
            "description": lambda ctx: f"进销品名匹配率仅{1-ctx.get('goods_mismatch_ratio',0):.0%}，可能存在虚开或隐匿收入",
            "investigation_chain": [
                "逐品名比对进销差异",
                "核查是否有委外加工（可解释品名差异）",
                "核查是否有视同销售未申报",
                "如无合理解释→进项税额转出+补缴销项税额"
            ]
        },
        {
            "id": "H007", "name": "会计账簿不健全→核定征收",
            "trigger": lambda ctx: ctx.get("data_quality_score", 100) < 40,
            "confidence": lambda ctx: 0.9 if ctx.get("data_quality_score", 100) < 40 else 0.3,
            "description": lambda ctx: f"资料完整度仅{ctx.get('data_quality_score',0)}分，会计账簿可能不健全",
            "investigation_chain": [
                "确认缺失资料是否无法补全",
                "评估是否触发《税收征收管理法》第35条核定征收条件",
                "测算核定征收对税负的影响",
                "建议补全资料以恢复正常征收方式"
            ]
        },
        {
            "id": "H008", "name": "小型微利企业资格不符",
            "trigger": lambda ctx: ctx.get("near_micro_limit", False),
            "confidence": lambda ctx: 0.6,
            "description": "企业接近但可能超出小微企业标准，需核实是否仍符合条件",
            "investigation_chain": [
                "核实应纳税所得额是否确≤300万",
                "核实从业人数季度平均值是否≤300人",
                "核实资产总额季度平均值是否≤5000万",
                "核实是否属于限制行业（如非金融、非房地产）"
            ]
        },
        {
            "id": "H009", "name": "发票群集性虚开",
            "trigger": lambda ctx: ctx.get("cluster_risk", False),
            "confidence": lambda ctx: 0.85 if ctx.get("cluster_risk") else 0.2,
            "description": "发票开具时间和金额呈现群集性特征，可能批量虚开",
            "investigation_chain": [
                "检查连续发票号码是否来自同一批次",
                "核查开票时间是否集中在非营业时间",
                "比对交易金额是否与经营范围匹配",
                "核查受票方是否为空壳公司"
            ]
        },
    ]
    
    def generate(self, context: Dict) -> List[Hypothesis]:
        """从数据上下文中生成假设"""
        hypotheses = []
        
        for template in self.HYPOTHESIS_TEMPLATES:
            try:
                if template["trigger"](context):
                    conf = template["confidence"](context)
                    if conf > 0.3:  # 过滤低置信度假设
                        desc = template["description"]
                        if callable(desc):
                            desc = desc(context)
                        
                        h = Hypothesis(
                            id=template["id"],
                            description=str(desc),
                            trigger_signals=[template["name"]],
                            confidence=round(conf, 2),
                            causal_chain=list(template["investigation_chain"]),
                        )
                        hypotheses.append(h)
            except Exception:
                pass
        
        # 按置信度排序
        hypotheses.sort(key=lambda h: h.confidence, reverse=True)
        return hypotheses


# ==================== 2. 自我反思器 ====================

class SelfReflector:
    """对分析结论进行自我质疑——反向假设验证
    
    核心逻辑：对每条高风险及以上结论，生成相反假设并尝试证明。
    如果反向假设也能成立 → 原结论可信度降低 → 标记为需要更多证据
    阈值已调低，使反思器更积极地质疑结论。
    """
    
    @staticmethod
    def reflect(findings: List[Dict], context: Dict) -> List[Dict]:
        """对发现列表进行自我反思"""
        reflected = []
        total_checked = 0
        total_uncertain = 0
        total_refuted = 0
        
        for f in findings:
            level = f.get("level", "")
            score = f.get("score", 0)
            ftype = f.get("type", "")
            
            # 反思高风险 + 评分>=6的中风险
            if level == "高风险" or score >= 6:
                total_checked += 1
                reflection = SelfReflector._reflect_single(f, context)
                f["_self_reflection"] = reflection
                # 降低阈值：adj<-0.05→不确定, adj<-0.15→被推翻
                adj = reflection.get("confidence_adjustment", 0)
                if adj < -0.15:
                    reflection["verdict"] = "refuted"
                    total_refuted += 1
                    f["_reflection_verdict"] = "refuted"
                elif adj < -0.05 or abs(adj) > 0.1:
                    reflection["verdict"] = "uncertain"
                    total_uncertain += 1
                    f["_reflection_verdict"] = "uncertain"
            reflected.append(f)
        
        return reflected
    
    @staticmethod
    def _reflect_single(finding: Dict, context: Dict) -> Dict:
        """对单条结论进行自我反思（扩展版：覆盖更多发现类型）"""
        ftype = finding.get("type", "")
        detail = finding.get("detail", "")
        reflections = {
            "counter_hypothesis": "",
            "counter_evidence": [],
            "confirmation_evidence": [],
            "confidence_adjustment": 0,
            "verdict": "confirmed",
        }
        
        # 隐匿收入
        if any(kw in ftype for kw in ["隐匿收", "未申报", "少报", "账外"]):
            reflections["counter_hypothesis"] = "银行收款超额可能因非经营性收款（股东注资/借款/往来款），而非隐匿收入"
            if context.get("has_personal_payments"):
                reflections["counter_evidence"].append("存在个人转账，可能是非经营性收款")
                reflections["confidence_adjustment"] -= 0.15
            if context.get("bank_in_ratio", 0) < 1.2:
                reflections["counter_evidence"].append(f"银行收款超额幅度较小(bank_in_ratio={context.get('bank_in_ratio',0):.2f})")
                reflections["confidence_adjustment"] -= 0.1
            if context.get("data_quality_score", 0) < 30:
                reflections["counter_evidence"].append("资料完整度不足，结论依赖有限数据")
                reflections["confidence_adjustment"] -= 0.1
        
        # 虚开发票
        elif any(kw in ftype for kw in ["虚开", "虚假发票"]):
            reflections["counter_hypothesis"] = "进项发票集中可能因企业与特定供应商有长期稳定合作关系"
            conc = context.get("supplier_concentration", 0)
            if conc < 0.6:
                reflections["counter_evidence"].append(f"供应商集中度{conc:.2f}，未达到极端水平")
                reflections["confidence_adjustment"] -= 0.08
            if conc < 0.4:
                reflections["confidence_adjustment"] -= 0.05
        
        # 品名不匹配
        elif any(kw in ftype for kw in ["品名", "进销不匹配"]):
            reflections["counter_hypothesis"] = "品名差异可能因外发加工导致进料和成品名称不同"
            if context.get("has_processing_fee"):
                reflections["counter_evidence"].append("存在加工费发票，可解释品名差异")
                reflections["confidence_adjustment"] -= 0.2
            if context.get("has_manufacturing"):
                reflections["counter_evidence"].append("企业存在制造业特征，品名变化正常")
                reflections["confidence_adjustment"] -= 0.12
        
        # 账簿不健全
        elif any(kw in ftype for kw in ["账簿", "核定征收", "资料不完整", "资料缺失"]):
            reflections["counter_hypothesis"] = "资料不完整可能因部分资料未上传，而非实质缺失"
            dq = context.get("data_quality_score", 0)
            if dq > 30:
                reflections["counter_evidence"].append(f"仍有部分资料可用(dq_score={dq})，可能只是上传不完整")
                reflections["confidence_adjustment"] -= 0.12
            if dq > 50:
                reflections["confidence_adjustment"] -= 0.08
        
        # 关联交易
        elif any(kw in ftype for kw in ["关联交易", "关联方", "利益输送"]):
            reflections["counter_hypothesis"] = "关联方交易可能存在合理商业目的，未必是利益输送"
            if context.get("has_processing_fee"):
                reflections["counter_evidence"].append("存在委托加工关系，可能为正常业务往来")
                reflections["confidence_adjustment"] -= 0.1
        
        # 资金流不匹配
        elif any(kw in ftype for kw in ["资金流", "银行流水不匹配", "银行收款不匹配"]):
            reflections["counter_hypothesis"] = "资金流与发票流偏差可能因时间差或非对公支付造成"
            mismatch = context.get("bank_in_ratio", 1)
            if 0.8 < mismatch < 1.2:
                reflections["counter_evidence"].append("偏差在合理范围内(±20%)，可能是时间性差异")
                reflections["confidence_adjustment"] -= 0.15
        
        # 供应商集中度风险
        elif any(kw in ftype for kw in ["供应商集中", "集中度", "依赖"]):
            reflections["counter_hypothesis"] = "供应商集中可能因行业特征或特定原材料垄断"
            if context.get("industry") in ["纺织", "服装", "电子"]:
                reflections["counter_evidence"].append("该行业供应商集中属常见现象")
                reflections["confidence_adjustment"] -= 0.08
        
        return reflections


# ==================== 3. 跨分析学习器 ====================

class CrossAnalysisLearner:
    """从多企业分析中归纳行业通用模式
    
    核心：一家企业发现的规律，下次分析同行业企业时自动应用。
    """
    
    MEMORY_FILE = None
    
    @classmethod
    def _get_memory_path(cls):
        if cls.MEMORY_FILE is None:
            base = os.path.dirname(os.path.dirname(__file__))
            cls.MEMORY_FILE = os.path.join(base, "static", "cross_analysis_memory.json")
        return cls.MEMORY_FILE
    
    @classmethod
    def load_memory(cls) -> Dict:
        try:
            with open(cls._get_memory_path(), "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"analyses": [], "industry_patterns": {}, "lesson_learned": []}
    
    @classmethod
    def save_memory(cls, memory: Dict):
        os.makedirs(os.path.dirname(cls._get_memory_path()), exist_ok=True)
        with open(cls._get_memory_path(), "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def record_analysis(cls, memory: AnalysisMemory):
        """记录一次分析的完整快照"""
        store = cls.load_memory()
        store["analyses"].append(asdict(memory))
        
        # 归纳行业模式
        industry = memory.industry
        if industry and industry != "未知":
            if industry not in store["industry_patterns"]:
                store["industry_patterns"][industry] = {
                    "analyses_count": 0,
                    "common_high_risks": Counter(),
                    "avg_risk_score": 0,
                    "typical_data_profile": {},
                }
            
            ip = store["industry_patterns"][industry]
            ip["analyses_count"] += 1
            for lp in memory.learning_points:
                ip["common_high_risks"][lp] += 1
        
        cls.save_memory(store)
    
    @classmethod
    def get_industry_insights(cls, industry: str) -> Dict:
        """获取行业的累积分析洞察——对新分析的指导"""
        store = cls.load_memory()
        ip = store["industry_patterns"].get(industry, {})
        
        if not ip or ip.get("analyses_count", 0) < 2:
            return {"has_insights": False, "message": "该行业分析样本不足，暂无行业洞察"}
        
        common_risks = ip.get("common_high_risks", {})
        top_risks = common_risks.most_common(5) if hasattr(common_risks, 'most_common') else []
        
        return {
            "has_insights": True,
            "industry": industry,
            "analyses_count": ip["analyses_count"],
            "top_risk_patterns": top_risks,
            "guidance": cls._generate_industry_guidance(industry, top_risks),
        }
    
    @staticmethod
    def _generate_industry_guidance(industry: str, top_risks: List) -> str:
        if not top_risks:
            return "暂无"
        lines = [f"根据{industry}行业历史分析经验，建议重点关注："]
        for risk, count in top_risks[:3]:
            lines.append(f"  · {risk}（{count}次出现）")
        return "\n".join(lines)
    
    @classmethod
    def add_lesson(cls, lesson: str, category: str = "通用"):
        """添加一条经验教训"""
        store = cls.load_memory()
        store["lesson_learned"].append({
            "lesson": lesson,
            "category": category,
            "timestamp": datetime.now().isoformat(),
        })
        cls.save_memory(store)


# ==================== 4. 洞见总结引擎 ====================

class InsightSynthesizer:
    """生成有洞见的综合报告——不只是罗列发现
    
    能力：
    1. 风险因果链总结
    2. 核心问题提炼
    3. 对比行业基准
    4. 优先级排序
    5. 可执行建议
    """
    
    @staticmethod
    def synthesize(all_findings: List[Dict], context: Dict) -> str:
        """生成综合洞见报告"""
        sections = []
        
        # 1. 核心画像
        sections.append(InsightSynthesizer._profile_section(context))
        
        # 2. 风险全景
        sections.append(InsightSynthesizer._risk_overview(all_findings))
        
        # 3. 核心问题提炼
        sections.append(InsightSynthesizer._core_issues(all_findings, context))
        
        # 4. 行业对标
        sections.append(InsightSynthesizer._industry_compare(context))
        
        # 5. 优先级行动建议
        sections.append(InsightSynthesizer._action_plan(all_findings))
        
        return "\n\n".join(sections)
    
    @staticmethod
    def _profile_section(ctx: Dict) -> str:
        cp = ctx.get("company_profile", {})
        fs = ctx.get("financial_snapshot", {})
        
        lines = [
            "▌一、企业画像",
            f"行业：{cp.get('industry', '未知')} | 经营模式：{cp.get('biz_model', '未知')}",
            f"经营规模：销项{fs.get('sale_count',0)}张/{fs.get('total_sales',0):,.0f}元 | 进项{fs.get('pur_count',0)}张/{fs.get('total_purchases',0):,.0f}元",
            f"银行流水：收款{fs.get('total_bank_in',0):,.0f}元 | 付款{fs.get('total_bank_out',0):,.0f}元",
        ]
        if fs.get("gross_margin_pct", 0):
            lines.append(f"毛利率：{fs['gross_margin_pct']}%")
        return "\n".join(lines)
    
    @staticmethod
    def _risk_overview(findings: List[Dict]) -> str:
        high = sum(1 for f in findings if f.get("level") == "高风险")
        mid = sum(1 for f in findings if f.get("level") == "中风险")
        
        lines = ["▌二、风险全景"]
        lines.append(f"共{len(findings)}项发现 ：高风险{high}项 | 中风险{mid}项 | 低风险{len(findings)-high-mid}项")
        
        # Top 5 高风险
        top_high = [f for f in findings if f.get("level") == "高风险"][:5]
        for i, f in enumerate(top_high, 1):
            detail = str(f.get("detail", f.get("type", "")))[:80]
            lines.append(f"  {i}. [{f.get('level','')}] {detail}")
        
        return "\n".join(lines)
    
    @staticmethod
    def _core_issues(findings: List[Dict], ctx: Dict) -> str:
        lines = ["▌三、核心问题提炼"]
        
        # 从假设中提取已验证的核心问题
        hypotheses = [f for f in findings if f.get("_hypothesis_verified")]
        if not hypotheses:
            high_risks = [f for f in findings if f.get("level") == "高风险" and f.get("score", 0) >= 7]
            if high_risks:
                lines.append(f"经交叉验证，本企业的核心风险集中在：")
                for hr in high_risks[:3]:
                    lines.append(f"  · {hr.get('type', '')}")
            else:
                lines.append("未发现重大核心风险。企业整体税务合规状况良好。")
        else:
            for h in hypotheses[:3]:
                lines.append(f"  · {h.get('type','')}: {h.get('detail','')[:80]}")
        
        return "\n".join(lines)
    
    @staticmethod
    def _industry_compare(ctx: Dict) -> str:
        cp = ctx.get("company_profile", {})
        industry = cp.get("industry", "未知")
        
        lines = ["▌四、行业对标"]
        
        insights = CrossAnalysisLearner.get_industry_insights(industry)
        
        if insights.get("has_insights"):
            lines.append(insights["guidance"])
        else:
            lines.append(f"{industry}行业暂无足够历史分析样本用于对标比较。")
        
        return "\n".join(lines)
    
    @staticmethod
    def _action_plan(findings: List[Dict]) -> str:
        lines = ["▌五、优先行动建议"]
        
        priorities = {"P0": [], "P1": [], "P2": []}
        for f in findings:
            if f.get("level") == "高风险" and f.get("score", 0) >= 8:
                priorities["P0"].append(f)
            elif f.get("level") == "高风险":
                priorities["P1"].append(f)
            else:
                priorities["P2"].append(f)
        
        if priorities["P0"]:
            lines.append(f"\n【P0 — 立即行动】{len(priorities['P0'])}项")
            for f in priorities["P0"][:3]:
                action = f.get("action", f.get("suggestion", f.get("detail", "")))[:100]
                lines.append(f"  · {action}")
        
        if priorities["P1"]:
            lines.append(f"\n【P1 — 重点关注】{len(priorities['P1'])}项")
            for f in priorities["P1"][:2]:
                action = f.get("action", f.get("suggestion", f.get("detail", "")))[:80]
                lines.append(f"  · {action}")
        
        return "\n".join(lines)


# ==================== 5. 智能体核心 ====================

class TaxAuditAgent:
    """财税稽查智能体核心
    
    统一调度五层引擎，模拟一个真正的税务稽查员的思考过程。
    
    v1.1 进化：
    - 自主推理器(AutonomousReasoner)替代手工模板
    - 从历史分析数据中学习因果关系
    - 多信号条件概率网络驱动假设生成
    - 未知模式检测 → 智哥介入 → 规则注入
    
    工作流：
        analyze() 入口
          ↓
        1. 感知层 — 数据解析 + 特征提取 + 异常检测
          ↓
        2. 推理层 — 自主推理器(因果网络) + 假设生成
          ↓
        2.5 未知模式扫描
          ↓
        3. 学习层 — 历史经验 + 行业模式 + 自愈修正
          ↓
        4. 表达层 — 洞见总结 + 可追溯解释
          ↓
        5. 记忆层 + 因果网络训练 — 保存快照 + 更新因果边
    """
    
    def __init__(self, db_session=None):
        self.db = db_session
        self.reflector = SelfReflector()
        self.learner = CrossAnalysisLearner()
        self.synthesizer = InsightSynthesizer()
        
        # v1.1: 自主推理器替代手工模板
        self.reasoner = None
        try:
            from engine.causal_network import create_autonomous_reasoner
            self.reasoner = create_autonomous_reasoner()
        except Exception:
            self.reasoner = HypothesisGenerator()  # 回退
        
        # v1.2: 语义推理器 + 创造性假设引擎
        self.semantic_reasoner = None
        try:
            from engine.semantic_reasoner import SemanticReasoner
            self.semantic_reasoner = SemanticReasoner()
        except Exception:
            pass
        
        # 未知模式检测器
        self.unknown_detector = None
        try:
            from engine.unknown_pattern_detector import UnknownPatternDetector, route_to_zhige
            self.unknown_detector = UnknownPatternDetector()
        except Exception:
            pass
        
        # 分析状态
        self.context = {}
        self.hypotheses = []
        self.industry_insights = {}
        self.analysis_memory = None
        self.discovery_result = None  # 未知模式发现结果
    
    def perceive(self, bank_txs, invoices, salaries, vouchers, ctx) -> Dict:
        """感知层：数据解析 + 特征提取 + 异常检测"""
        if ctx is None:
            return {}
        
        cp = ctx.company_profile or {}
        fs = ctx.financial_snapshot or {}
        
        # 计算关键比率
        total_sales = fs.get("total_sales", 0)
        total_bank_in = fs.get("total_bank_in", 0)
        total_purchases = fs.get("total_purchases", 0)
        total_bank_out = fs.get("total_bank_out", 0)
        
        bank_in_ratio = total_bank_in / total_sales if total_sales > 0 else 1.0
        bank_out_ratio = total_bank_out / total_purchases if total_purchases > 0 else 1.0
        
        # 进销品名匹配率
        sal_goods = set()
        pur_goods = set()
        for inv in invoices or []:
            goods = str(inv.get("goods", "")).strip()
            if not goods:
                continue
            if inv.get("direction") in ("销项", "sales"):
                sal_goods.add(goods)
            else:
                pur_goods.add(goods)
        
        match_count = len(sal_goods & pur_goods)
        total_goods = len(sal_goods | pur_goods)
        goods_match_ratio = match_count / total_goods if total_goods > 0 else 1.0
        
        # 付款覆盖率
        pur_count = len([i for i in invoices or [] if i.get("direction") in ("进项", "purchase")])
        
        return {
            # 财务指标
            "bank_in_ratio": round(bank_in_ratio, 2),
            "bank_out_ratio": round(bank_out_ratio, 2),
            "goods_match_ratio": round(goods_match_ratio, 2),
            "goods_mismatch_ratio": round(1 - goods_match_ratio, 2),
            
            # 企业特征
            "industry": cp.get("industry", "未知"),
            "biz_model": cp.get("biz_model", "未知"),
            "company_profile": cp,
            "financial_snapshot": fs,
            
            # 信号
            "has_processing_fee": getattr(ctx, 'has_processing_fee', False),
            "has_personal_payments": getattr(ctx, 'has_personal_payments', False),
            "has_related_parties": getattr(ctx, 'has_related_parties', False),
            "has_six_personnel_overlap": getattr(ctx, 'has_six_personnel_overlap', False),
            "supplier_concentration": getattr(ctx, 'supplier_concentration', 0),
            "customer_concentration": getattr(ctx, 'customer_concentration', 0),
            "data_quality_score": getattr(ctx, 'data_quality_score', 100),
            "near_micro_limit": getattr(ctx, 'near_micro_limit', False),
            "cluster_risk": getattr(ctx, 'cluster_risk', False),
            "has_manufacturing": cp.get("has_manufacturing", False),
            
            # 原始数据摘要
            "sal_count": fs.get("sale_count", 0),
            "pur_count": fs.get("pur_count", 0),
            "invoice_count": fs.get("sale_count", 0) + fs.get("pur_count", 0),
            "pur_without_payment_ratio": 1 - bank_out_ratio if bank_out_ratio < 1 else 0,
        }
    
    def reason(self, context: Dict, existing_findings: List[Dict] = None) -> List:
        """推理层：自主推理器(因果网络)驱动假设生成"""
        if self.reasoner is None:
            return []
        
        # v1.1: 使用自主推理器而非模板
        if hasattr(self.reasoner, 'reason'):
            result = self.reasoner.reason(context, existing_findings or [])
            self.hypotheses = [
                Hypothesis(
                    id=f"AR_{i}",
                    description=p.get("finding", ""),
                    trigger_signals=[p.get("trigger", "")],
                    confidence=p.get("confidence", 0.5),
                    causal_chain=[
                        f"因果网络预测: {p.get('trigger','')}",
                        f"置信度: {p.get('confidence',0):.0%}",
                        f"证据: {p.get('evidence','')}"
                    ],
                    verified=None,
                )
                for i, p in enumerate(result.get("predictions", [])[:8])
            ]
            
            # v2.0: SCM因果推理增强
            try:
                from engine.scm_reasoner import scm
                for hp in self.hypotheses:
                    signals_for_scm = hp.trigger_signals if isinstance(hp.trigger_signals, list) else [hp.trigger_signals]
                    for sig in signals_for_scm:
                        intervention = scm.do_intervention(sig, "eliminate")
                        if intervention.get("total_affected", 0) > 0:
                            hp.causal_chain.append(f"SCM干预: 消除{sig}→影响{intervention['total_affected']}个下游变量")
            except Exception:
                pass
            
            return self.hypotheses
        
        # 回退到模板生成器
        if hasattr(self.reasoner, 'generate'):
            self.hypotheses = self.reasoner.generate(context)
            return self.hypotheses
        
        return []
    
    def learn(self, industry: str, all_findings: List[Dict]) -> Dict:
        """学习层：跨分析经验 + 行业模式"""
        self.industry_insights = self.learner.get_industry_insights(industry)
        
        # 提取本次学习要点
        learning_points = []
        for f in all_findings:
            if f.get("level") == "高风险":
                learning_points.append(f.get("type", ""))
        
        return self.industry_insights
    
    def reflect(self, all_findings: List[Dict], context: Dict) -> List[Dict]:
        """反思层：自我质疑 + 反向验证"""
        return self.reflector.reflect(all_findings, context)
    
    def express(self, all_findings: List[Dict], context: Dict) -> str:
        """表达层：洞见总结"""
        return self.synthesizer.synthesize(all_findings, context)
    
    def remember(self, company_id: int, company_name: str, industry: str, 
                 biz_model: str, all_findings: List[Dict], trace_id: str):
        """记忆层：保存分析快照"""
        self.analysis_memory = AnalysisMemory(
            trace_id=trace_id or str(uuid.uuid4())[:8],
            company_id=company_id,
            company_name=company_name,
            industry=industry or "未知",
            biz_model=biz_model or "未知",
            timestamp=datetime.now().isoformat(),
            key_findings_count=len(all_findings),
            high_risk_count=sum(1 for f in all_findings if f.get("level") == "高风险"),
            generated_hypotheses=len(self.hypotheses),
            verified_hypotheses=sum(1 for h in self.hypotheses if h.verified),
            learning_points=[h.description[:80] for h in self.hypotheses if h.verified],
            data_profile={
                "bank_in_ratio": self.context.get("bank_in_ratio", 0),
                "supplier_concentration": self.context.get("supplier_concentration", 0),
                "goods_match_ratio": self.context.get("goods_match_ratio", 0),
            }
        )
        self.learner.record_analysis(self.analysis_memory)
    
    def analyze(self, bank_txs, invoices, salaries, vouchers, ctx, 
                company_id=0, company_name="", db_session=None) -> Dict:
        """完整分析流程——智能体五步思考法"""
        
        # Step 1: 感知
        self.context = self.perceive(bank_txs, invoices, salaries, vouchers, ctx)
        
        # Step 2: 推理
        self.reason(self.context)
        
        # Step 2.5: 语义分析 + 创造性推理
        creative_result = None
        if self.semantic_reasoner and self.unknown_detector:
            try:
                # 语义品名分析
                from engine.semantic_reasoner import SemanticMatcher
                sem = SemanticMatcher()
                
                # 创造性推理：基于当前活跃信号和因果网络
                active_sigs = []
                try:
                    from engine.causal_network import PRIMARY_SIGNALS
                    for sig_id, sig_name, detector in PRIMARY_SIGNALS:
                        if detector(self.context):
                            active_sigs.append(sig_name)
                except: pass
                causal_edges = getattr(self.reasoner, 'network', None)
                if causal_edges:
                    creative_result = self.semantic_reasoner.creative_reason(
                        active_sigs,
                        getattr(causal_edges, 'edges', []),
                        getattr(causal_edges, 'patterns', []),
                    )
            except Exception:
                pass
        
        # Step 3: 学习（获取行业洞察）
        industry = self.context.get("industry", "未知")
        self.learn(industry, [])
        
        # 返回智能体状态
        return {
            "agent_version": "1.1",
            "context": {
                "industry": industry,
                "bank_in_ratio": self.context.get("bank_in_ratio", 0),
                "goods_match_ratio": self.context.get("goods_match_ratio", 0),
                "data_quality_score": self.context.get("data_quality_score", 100),
            },
            "hypotheses": [
                {
                    "id": h.id,
                    "description": h.description,
                    "confidence": h.confidence,
                    "investigation_chain": h.causal_chain[:3],
                }
                for h in self.hypotheses[:5]
            ],
            "industry_insights": self.industry_insights,
            "reflection_pending": True,
        }
    
    def finalize(self, all_findings: List[Dict], trace_id: str, 
                 company_id: int, company_name: str,
                 bank_txs=None, invoices=None, salaries=None, vouchers=None) -> Dict:
        """分析收尾：反思 + 未知模式扫描 + 总结 + 记忆"""
        
        # Step 3.5: 未知模式扫描（在反思之前——先看自己哪里不懂）
        discovery = None
        if self.unknown_detector:
            try:
                discovery = self.unknown_detector.scan(
                    bank_txs or [], invoices or [], salaries or [], vouchers or [],
                    self.context, all_findings, 
                    [{"id": h.id, "description": h.description, "type": h.id} for h in self.hypotheses],
                    company_id, company_name, trace_id
                )
                self.discovery_result = discovery
            except Exception as e:
                import traceback
                self.context["_detector_error"] = f"{e}: {traceback.format_exc()[-200:]}"
        
        # Step 4: 反思
        reflected_findings = self.reflect(all_findings, self.context)
        
        # Step 5: 总结
        insight_text = self.express(reflected_findings, self.context)
        
        # Step 6: 记忆
        self.remember(
            company_id, company_name,
            self.context.get("industry", "未知"),
            self.context.get("biz_model", "未知"),
            all_findings, trace_id
        )
        
        # Step 7: 训练因果网络（从本次分析中学习新的因果边）
        training_result = None
        if hasattr(self.reasoner, 'train_and_update') and self.reasoner is not None:
            try:
                training_result = self.reasoner.train_and_update()
            except Exception:
                pass
        
        result = {
            "agent_version": "1.1",
            "insight_summary": insight_text,
            "reflection": {
                "total_checked": len(all_findings),
                "confirmed": sum(1 for f in reflected_findings if f.get("_self_reflection", {}).get("verdict") == "confirmed"),
                "uncertain": sum(1 for f in reflected_findings if f.get("_self_reflection", {}).get("verdict") == "uncertain"),
                "refuted": sum(1 for f in reflected_findings if f.get("_self_reflection", {}).get("verdict") == "refuted"),
            },
            "memory": {
                "saved": self.analysis_memory is not None,
                "trace_id": trace_id,
                "industry_experience": self.industry_insights.get("analyses_count", 0),
            },
            "causal_network": training_result,  # 因果网络训练结果
            "reflected_findings": reflected_findings,
        }
        
        # 附加未知模式发现
        if discovery:
            try:
                from engine.unknown_pattern_detector import route_to_zhige as _r2z
            except ImportError:
                _r2z = lambda p: {"id": p.id, "routed": False}
            result["unknown_patterns"] = {
                "total_discovered": len(discovery.unknown_patterns),
                "evolution_potential": discovery.evolution_potential,
                "coverage": discovery.known_coverage,
                "patterns": [
                    {
                        "id": p.id, "name": p.name, "dimension": p.dimension,
                        "significance": p.statistical_significance,
                        "why_unknown": p.why_unknown, "best_guess": p.best_guess,
                        "status": p.status,
                    }
                    for p in discovery.unknown_patterns[:10]
                ],
                "routing_to_zhige": [
                    _r2z(p) for p in discovery.unknown_patterns[:3]
                ],
                "message": f"发现{len(discovery.unknown_patterns)}个未知模式，已路由到智哥进行分析" if discovery.unknown_patterns else "系统认知边界内未发现未知模式"
            }
        
        return result


# 便捷入口
def create_agent(db_session=None) -> TaxAuditAgent:
    return TaxAuditAgent(db_session)
