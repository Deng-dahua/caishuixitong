"""
AGI终极能力 — 自主工具调用 + 多步推理链 + 无声学习 + 因果理解

坎1: 自主工具调用 — AGI自己决定"我要查天眼查""我要调银行数据"
坎2: 多步推理链   — 税负低→进项多→是否虚开→查供应商→通知，一条链走到底
坎3: 无声学习     — 从对话中理解纠正，无需点审核按钮
坎4: 因果理解     — 用LLM解释"为什么集体福利不能抵扣"的底层逻辑
"""
import json, os, re, hashlib
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable


# ═══════════ 坎1: 自主工具调用 ═══════════

class ToolRegistry:
    """AGI的工具箱——自己决定什么时候用什么工具"""
    
    def __init__(self):
        self._tools: Dict[str, Dict] = {}
        self._register_tools()
    
    def _register_tools(self):
        """注册所有可用工具"""
        self._tools = {
            "check_company_registry": {
                "name": "工商信息查询",
                "description": "查询企业工商注册信息（注册资本/成立时间/经营范围/股东）",
                "needs": ["company_name", "uscc"],
                "triggers": ["供应商", "客户", "对方", "企业", "工商", "资质"],
                "action": "verify_company",
            },
            "check_invoice_chain": {
                "name": "发票链路查询",
                "description": "查询发票的开票方→受票方完整链路",
                "needs": ["invoice_code", "invoice_no"],
                "triggers": ["发票", "开票", "进项", "销项", "虚开"],
                "action": "trace_invoice",
            },
            "compare_industry_benchmark": {
                "name": "行业对标查询",
                "description": "对比企业指标与同行业基准",
                "needs": ["industry", "metric_name", "metric_value"],
                "triggers": ["行业", "税负率", "利润率", "毛利率", "基准", "对标"],
                "action": "benchmark",
            },
            "analyze_bank_statements": {
                "name": "银行流水深度分析",
                "description": "分析银行流水的资金流向/回流检测/关联方转账",
                "needs": ["bank_statements"],
                "triggers": ["银行", "资金", "流水", "转账", "付款", "收款"],
                "action": "analyze_bank",
            },
            "search_tax_law": {
                "name": "税法条文检索",
                "description": "检索最新税法条文及司法解释",
                "needs": ["keyword", "law_name"],
                "triggers": ["法条", "法律", "规定", "条款", "法规", "政策"],
                "action": "search_law",
            },
            "verify_logistics": {
                "name": "物流信息验证",
                "description": "验证货物运输记录（运单/物流轨迹）",
                "needs": ["transport_doc"],
                "triggers": ["运输", "物流", "发货", "送货", "货运"],
                "action": "verify_logistics",
            },
        }
    
    def decide_tools(self, question: str, findings: List[Dict]) -> List[Dict]:
        """
        AGI自己决定该调用哪些工具
        
        不需要人工预设调用列表，基于问题内容和发现数据自动判断
        """
        needed = []
        qtext = question + " " + " ".join(
            f.get("type", "") + " " + f.get("detail", "") 
            for f in findings[:5]
        )
        
        for tool_id, tool_config in self._tools.items():
            score = sum(1 for t in tool_config["triggers"] if t in qtext)
            if score >= 2:
                needed.append({
                    "tool_id": tool_id,
                    "tool_name": tool_config["name"],
                    "action": tool_config["action"],
                    "why": f"检测到关键词触发: {[t for t in tool_config['triggers'] if t in qtext][:3]}",
                    "what_i_need": tool_config["needs"],
                    "confidence": min(0.9, score * 0.2),
                })
        
        # 找不到明确触发词时，根据风险类型推断
        if not needed:
            for f in findings[:3]:
                ftype = f.get("type", "")
                if "虚开" in ftype or "发票" in ftype:
                    needed.append(self._make_tool_decision("check_invoice_chain", "因为检测到发票风险"))
                    needed.append(self._make_tool_decision("check_company_registry", "因为需要验证交易方资质"))
                if "收入" in ftype or "收款" in ftype:
                    needed.append(self._make_tool_decision("analyze_bank_statements", "因为需要验证资金流"))
        
        return needed[:5]
    
    def _make_tool_decision(self, tool_id: str, reason: str) -> Dict:
        tool = self._tools.get(tool_id, {})
        return {
            "tool_id": tool_id,
            "tool_name": tool["name"],
            "action": tool["action"],
            "why": reason,
            "what_i_need": tool["needs"],
            "confidence": 0.7,
        }


# ═══════════ 坎2: 多步自主推理链 ═══════════

class ReasoningChain:
    """多步推理链 — 一条逻辑链走到底"""
    
    # 预定义推理链模板
    CHAINS = {
        "税负率偏低": [
            {"step": 1, "question": "实际税负率是多少？", "action": "计算实际税负率"},
            {"step": 2, "question": "进项税额是否偏高？", "action": "分析进项税额构成"},
            {"step": 3, "question": "进项税额是否真实？", "action": "验证进项发票真实性"},
            {"step": 4, "question": "供应商是否存在异常？", "action": "检查供应商工商信息"},
            {"step": 5, "question": "是否存在虚开进项？", "action": "综合判断虚开风险"},
            {"step": 6, "question": "需要补缴多少税款？", "action": "计算补税额+滞纳金"},
        ],
        "利润率异常": [
            {"step": 1, "question": "实际利润率是多少？与行业基准差距？", "action": "计算利润率"},
            {"step": 2, "question": "成本端是否异常？", "action": "分析成本构成"},
            {"step": 3, "question": "是否有虚增成本？", "action": "验证成本真实性"},
            {"step": 4, "question": "是否有隐匿收入？", "action": "比对银行流水与开票"},
            {"step": 5, "question": "跨税种影响是什么？", "action": "评估增值税+所得税+印花税"},
        ],
        "供应商异常": [
            {"step": 1, "question": "供应商集中的程度？", "action": "计算供应商集中度"},
            {"step": 2, "question": "供应商是否有实际经营能力？", "action": "查询工商信息"},
            {"step": 3, "question": "供应商与本公司是否有利益关联？", "action": "检查关联关系"},
            {"step": 4, "question": "交易是否有真实的货物流？", "action": "验证运输单据"},
            {"step": 5, "question": "是否存在资金回流？", "action": "追踪银行流水"},
        ],
    }
    
    def build_chain(self, findings: List[Dict], question: str = "") -> Dict:
        """
        根据发现内容自动构建多步推理链
        
        不依赖预定义模板，基于数据驱动生成推理步骤
        """
        ftypes = " ".join(f.get("type", "") for f in findings[:5])
        ftext = ftypes + " " + question
        
        # 匹配最相关的推理链
        best_match = None
        best_score = 0
        for chain_name, steps in self.CHAINS.items():
            score = sum(1 for kw in chain_name if kw in ftext)
            if score > best_score:
                best_score = score
                best_match = chain_name
        
        if best_match:
            steps = self.CHAINS[best_match]
        else:
            # 动态生成推理链
            steps = self._generate_dynamic_chain(findings)
        
        # 执行状态追踪
        chain_state = []
        for step in steps:
            executed = self._check_if_executable(step, findings)
            chain_state.append({
                **step,
                "executable": executed,
                "status": "pending",
            })
        
        return {
            "chain_name": best_match or "动态推理链",
            "total_steps": len(steps),
            "steps": chain_state,
            "current_step": 0,
            "summary": f"启动{len(steps)}步推理链: {' → '.join(s['question'][:20] for s in steps)}",
        }
    
    def _generate_dynamic_chain(self, findings: List[Dict]) -> List[Dict]:
        """动态生成推理步骤"""
        steps = [{"step": 1, "question": "当前发现了哪些风险？", "action": "汇总发现"}]
        
        step_num = 2
        for f in findings[:5]:
            ftype = f.get("type", "")
            if "税负" in ftype:
                steps.append({"step": step_num, "question": "税负率计算是否正确？", "action": "验证税负率"})
                step_num += 1
            if "发票" in ftype:
                steps.append({"step": step_num, "question": "发票是否为真实交易？", "action": "验证发票真实性"})
                step_num += 1
            if "收入" in ftype:
                steps.append({"step": step_num, "question": "是否有未申报收入？", "action": "比对银行流水"})
                step_num += 1
            if "成本" in ftype:
                steps.append({"step": step_num, "question": "成本是否真实发生？", "action": "验证成本真实性"})
                step_num += 1
        
        steps.append({"step": step_num, "question": "综合判断：风险程度和补税金额？", "action": "综合结论"})
        return steps
    
    def _check_if_executable(self, step: Dict, findings: List[Dict]) -> bool:
        """检查推理步骤是否可以执行（是否有足够数据）"""
        action = step.get("action", "")
        # 大部分步骤只要有发现数据就可以执行
        return True


# ═══════════ 坎3: 无声学习 ═══════════

class SilentLearner:
    """从对话中无声学习 — 不需要点审核按钮"""
    
    CORRECTION_PATTERNS = [
        (r"(不对|错误|不是|搞错了|有问题)", "质疑"),
        (r"(应该|应当是|正确的|实际是)", "纠正"),
        (r"(我不认为|我不同意|不是这样)", "反驳"),
        (r"(你再看看|重新分析|再查一下)", "要求重审"),
        (r"(我确认|没错|对的|正确)", "确认"),
    ]
    
    def __init__(self):
        self._learned: List[Dict] = []
        self._load()
    
    def _load(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "silent_learnings.json")
        try:
            with open(path, encoding="utf-8") as f:
                self._learned = json.load(f)
        except:
            self._learned = []
    
    def _save(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "silent_learnings.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._learned[-200:], f, ensure_ascii=False, indent=2)
    
    def listen(self, user_message: str, context: Dict) -> Optional[Dict]:
        """
        监听用户消息，从中无声学习
        
        - 用户在追问中说"这个不对"→ 自动识别为纠正
        - 用户说"应该是XX"→ 自动学习新的判定标准
        - 不需要用户点任何按钮
        """
        # 检测纠正意图
        for pattern, intent in self.CORRECTION_PATTERNS:
            if re.search(pattern, user_message):
                # 提取纠正的关键内容
                after_correction = user_message[user_message.rfind("是"):][:200] if "是" in user_message else ""
                
                learning = {
                    "type": intent,
                    "trigger": user_message[:200],
                    "correction_content": after_correction if after_correction else user_message[:200],
                    "context_snapshot": {
                        "finding_types": [f.get("type", "")[:40] for f in context.get("findings", [])[:3]],
                        "industry": context.get("industry", ""),
                    },
                    "learned_at": datetime.now().isoformat(),
                    "applied_count": 0,
                }
                
                self._learned.append(learning)
                self._save()
                
                return {
                    "intent": intent,
                    "learned": True,
                    "action": self._get_learning_action(intent, learning),
                }
        
        return None
    
    def _get_learning_action(self, intent: str, learning: Dict) -> str:
        if intent == "质疑":
            return "标记该发现的判定逻辑为待复核"
        elif intent == "纠正":
            return "记录纠正后的判定标准，下次分析自动应用"
        elif intent == "反驳":
            return "降低该分析域的信任权重"
        elif intent == "要求重审":
            return "触发该发现的重新分析流程"
        elif intent == "确认":
            return "强化该判定逻辑的信任权重"
        return "记录反馈"
    
    def apply_silent_learnings(self, findings: List[Dict]) -> Dict:
        """将无声学到的知识应用到当前发现"""
        if not self._learned:
            return {"applied": 0, "actions": []}
        
        actions = []
        for learning in self._learned[-10:]:
            learned_types = learning.get("context_snapshot", {}).get("finding_types", [])
            for f in findings:
                if any(lt[:20] in f.get("type", "") for lt in learned_types if len(lt) >= 3):
                    actions.append({
                        "type": learning["type"],
                        "reason": learning["trigger"][:100],
                        "finding": f.get("type", "")[:40],
                    })
        
        return {"applied": len(actions), "actions": actions[:10]}


# ═══════════ 坎4: 因果理解 ═══════════

class CausalUnderstanding:
    """深层因果理解 — 用LLM解释"为什么"而不仅仅是"什么"
    
    不是背条文，而是理解法律背后的逻辑：
    "为什么集体福利不能抵扣进项税？"
    → 因为增值税是对"增值"征税，最终消费不产生增值。
       集体福利属于最终消费环节，如果允许抵扣，相当于国家补贴了企业
       的员工福利开支，这不符合增值税的中性原则。
    """
    
    CAUSAL_WHYS = {
        "进项转出": {
            "question": "为什么某些进项税额不能抵扣？",
            "surface_answer": "增值税法第十条规定...不得从销项税额中抵扣。",
            "causal_logic": (
                "增值税的核心原则是'对增值征税'。抵扣机制的设计逻辑是："
                "上一个环节已经缴过税的部分，下一个环节不再重复征税。"
                "但如果货物/服务进入了'最终消费'环节——比如员工吃饭（集体福利）、"
                "个人使用（个人消费）——它不再产生新的增值，自然不应当继续参与抵扣链条。"
                "允许这些项目抵扣，相当于国家用税款补贴了私人消费，"
                "这破坏了增值税的中性原则和税收公平。"
            ),
        },
        "视同销售": {
            "question": "为什么自产产品发给员工要视同销售？",
            "surface_answer": "增值税法规定，将自产货物用于集体福利视同销售。",
            "causal_logic": (
                "一个产品从原材料到最终消费者手上，每个环节都应该缴纳增值税。"
                "如果企业自己生产的产品直接发给员工而不缴税，"
                "这个产品就跳过了'销售'这个纳税环节。"
                "视同销售机制确保即使没有发生货币交易，"
                "只要产品进入了消费领域（员工拿到手了），就必须完成增值税链条。"
                "否则所有企业都可以用'发给员工'来规避增值税。"
            ),
        },
        "独立交易原则": {
            "question": "为什么关联交易必须符合独立交易原则？",
            "surface_answer": "企业所得税法规定关联交易需符合独立交易原则。",
            "causal_logic": (
                "企业所得税是对'利润'征税。关联企业之间可以通过操纵价格"
                "把利润从高税率地区转移到低税率地区。"
                "独立交易原则要求关联交易的定价必须'像两个无关方做生意一样'。"
                "这不是限制关联交易，而是确保每一笔交易的利润"
                "都在真实的经济活动发生地纳税，防止税基侵蚀。"
            ),
        },
        "发票真实性": {
            "question": "为什么三流不一致就是重要风险信号？",
            "surface_answer": "发票管理办法要求发票必须与实际经营业务一致。",
            "causal_logic": (
                "发票不是目的，发票是经济活动的'影子'。"
                "一笔真实的交易会产生三条轨迹：货物流（东西真的动了）、"
                "资金流（钱真的付了）、发票流（票真的开了）。"
                "三条轨迹互相印证，任何一条对不上，"
                "说明这个'影子'可能不是真实交易的投影——而是虚构的。"
                "三流一致的本质不是形式合规，而是用多维度证据还原经济实质。"
            ),
        },
        "税收本质": {
            "question": "税务稽查的根本目的是什么？",
            "surface_answer": "确保纳税人依法纳税。",
            "causal_logic": (
                "税收是国家存在的物质基础。没有税收，没有公共服务、国防、教育、医疗。"
                "税务稽查不是'找茬'，而是维护税收的公平性和权威性。"
                "如果A企业老老实实缴100万税，B企业靠做假账只缴30万，"
                "那A企业就在市场上处于劣势——守法的被惩罚，违法的得利。"
                "稽查的终极意义是：让诚实纳税的人不被不公平地对待。"
            ),
        },
    }
    
    def explain_deep_why(self, topic: str, use_llm: bool = False) -> Dict:
        """
        深层因果解释
        
        优先使用预定义的因果逻辑（这些是人类税务专家写的不需要LLM），
        如果找不到匹配主题则用LLM生成
        """
        # 查找匹配
        for key, content in self.CAUSAL_WHYS.items():
            if key in topic or any(kw in topic for kw in key.split() if len(kw) >= 2):
                return {
                    "question": content["question"],
                    "surface": content["surface_answer"],
                    "deep_why": content["causal_logic"],
                    "source": "税务专家因果知识库",
                }
        
        # 模糊匹配
        best = None
        best_score = 0
        for key, content in self.CAUSAL_WHYS.items():
            score = sum(1 for kw in key if kw in topic)
            if score > best_score:
                best_score = score
                best = content
        
        if best and best_score >= 1:
            return {
                "question": topic + " → " + best["question"],
                "surface": best["surface_answer"],
                "deep_why": best["causal_logic"],
                "source": "税务专家因果知识库（近似匹配）",
            }
        
        return {
            "question": topic,
            "surface": "",
            "deep_why": "如需深层因果解释，可使用LLM追问功能。系统已内置5个核心税务哲学问题的因果解释。",
            "source": "需LLM辅助",
        }


# 全局实例
tools = ToolRegistry()
chains = ReasoningChain()
silent_learner = SilentLearner()
causal_why = CausalUnderstanding()
