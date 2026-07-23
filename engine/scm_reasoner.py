"""
SCM 因果推理引擎 —— 从条件概率升级为结构化因果推理

核心能力：
  1. 干预分析（do-calculus 轻量版）：如果消除信号X，结论会怎么变？
  2. 反事实推理：如果当初企业补了合同，风险等级会降吗？
  3. 因果方向判定：X导致Y，还是Y导致X？（基于时间序+领域知识）
  4. 混淆因子检测：是否存在第三个变量同时影响X和Y？

与因果网络(causal_network.py)的关系：
  - 因果网络负责：从数据中挖掘信号→结论的关联模式
  - SCM负责：判断这些关联是不是真正的因果，消除虚假关联
"""
import math
from typing import Dict, List, Tuple, Set, Any
from collections import defaultdict


class CausalVariable:
    """因果变量 —— SCM中的节点"""
    def __init__(self, name: str, parents: List[str] = None, domain: str = ""):
        self.name = name
        self.parents = parents or []     # 直接原因
        self.children: List[str] = []     # 直接结果
        self.domain = domain             # 所属域
        self.is_exogenous = len(self.parents) == 0  # 外生变量
        self.observations: List[bool] = []  # 观测值序列


class SCMReasoner:
    """结构因果模型推理器"""
    
    def __init__(self):
        self.variables: Dict[str, CausalVariable] = {}
        self._domain_knowledge = self._init_domain_knowledge()
    
    def _init_domain_knowledge(self) -> Dict[str, Dict]:
        """税务合规领域的因果先验知识"""
        return {
            # 因果方向：时间序确定 —— 采购在前，进项发票在后
            "进项发票异常": {"causes": ["供应商集中度过高", "品名与经营范围不符", "银行付款方不匹配"], "effects": ["虚开发票风险"]},
            "销项发票异常": {"causes": ["客户过度集中", "月末集中开票", "银行收款方不匹配"], "effects": ["隐匿收入风险"]},
            "虚开发票风险": {"causes": ["进项发票异常", "资金回流", "购销闭环"], "effects": ["进项转出", "补税罚款"]},
            "隐匿收入风险": {"causes": ["销项发票异常", "银行收款>申报收入", "零开票大额收款"], "effects": ["补税罚款", "核定征收"]},
            "账簿不健全": {"causes": ["资料缺失", "凭证不完整", "科目运用错误"], "effects": ["核定征收"]},
            "核定征收": {"causes": ["账簿不健全", "成本资料残缺"], "effects": ["税负增加", "罚款"]},
            "资料缺失": {"causes": [], "effects": ["账簿不健全", "无法交叉验证"]},
            "合同缺失": {"causes": [], "effects": ["无法判断交易实质", "虚开发票风险"]},
        }
    
    def add_variable(self, name: str, parents: List[str] = None, domain: str = ""):
        """添加因果变量"""
        if name not in self.variables:
            self.variables[name] = CausalVariable(name, parents or [], domain)
        # 从领域知识补充因果关系
        if name in self._domain_knowledge:
            dk = self._domain_knowledge[name]
            for cause in dk.get("causes", []):
                if cause not in self.variables:
                    self.variables[cause] = CausalVariable(cause, [], "")
                if name not in self.variables[cause].children:
                    self.variables[cause].children.append(name)
                if cause not in self.variables[name].parents:
                    self.variables[name].parents.append(cause)
    
    def add_edge(self, cause: str, effect: str):
        """添加因果边"""
        self.add_variable(cause)
        self.add_variable(effect)
        if effect not in self.variables[cause].children:
            self.variables[cause].children.append(effect)
        if cause not in self.variables[effect].parents:
            self.variables[effect].parents.append(cause)
    
    def do_intervention(self, target_var: str, action: str = "eliminate") -> Dict:
        """
        干预分析：如果对target_var执行action，会对下游产生什么影响？
        
        action: "eliminate" (消除信号), "amplify" (增强信号)
        返回受影响的所有下游变量及影响程度
        """
        if target_var not in self.variables:
            return {"target": target_var, "effect": "未知变量，无因果信息"}
        
        affected = []
        visited = set()
        
        def propagate(current: str, depth: int, impact: float):
            if current in visited or depth > 4:
                return
            visited.add(current)
            var = self.variables.get(current)
            if not var:
                return
            for child in var.children:
                child_impact = impact * (1.0 / max(len(var.children), 1)) * (1.0 - depth * 0.15)
                if child_impact < 0.05:
                    continue
                affected.append({
                    "variable": child,
                    "depth": depth + 1,
                    "impact": round(child_impact, 3),
                    "direction": "消除" if action == "eliminate" else "增强",
                })
                propagate(child, depth + 1, child_impact)
        
        propagate(target_var, 0, 1.0)
        affected.sort(key=lambda x: x["impact"], reverse=True)
        
        return {
            "target": target_var,
            "action": action,
            "total_affected": len(affected),
            "affected": affected,
            "key_insight": f"若{action}{target_var}，将影响{len(affected)}个下游变量，最大影响{affected[0]['variable']}({affected[0]['impact']})" if affected else "无影响",
        }
    
    def counterfactual(self, finding: Dict, assumed_intervention: str) -> Dict:
        """
        反事实推理：如果当初X不同，结论会怎样？
        
        例：finding = {"type": "虚开发票风险", "signals": ["进项品名不匹配", "无合同"]}
             assumed_intervention = "企业有完整购销合同"
             推理：有合同→交易实质可验证→虚开发票风险降低
        """
        signals = finding.get("signals", []) or []
        finding_type = finding.get("type", "")
        
        # 找出假设干预影响的信号
        affected_signals = []
        for sig in signals:
            intervention = self.do_intervention(sig, "eliminate")
            if intervention.get("total_affected", 0) > 0:
                for aff in intervention.get("affected", []):
                    if finding_type in aff["variable"] or any(kw in aff["variable"] for kw in finding_type.split("风险")[0].split("、")):
                        affected_signals.append(aff)
        
        risk_reduction = sum(a["impact"] for a in affected_signals) / max(len(signals), 1)
        
        return {
            "finding": finding_type,
            "assumed_intervention": assumed_intervention,
            "signals_affected": len(affected_signals),
            "risk_reduction": round(risk_reduction, 3),
            "verdict": "反事实推理：若" + assumed_intervention + "，风险降低约" + str(round(risk_reduction * 100)) + "%",
        }
    
    def detect_confounders(self, signal: str, finding: str) -> List[str]:
        """
        检测混淆因子：是否存在第三个变量Z同时导致signal和finding
        使用领域知识中的因果图做后门路径检测
        """
        if signal not in self.variables or finding not in self.variables:
            return []
        
        # 查找signal和finding的共同原因
        signal_parents = set(self.variables[signal].parents)
        finding_parents = set(self.variables[finding].parents)
        
        # 后门路径：是否存在signal←Z→finding的路径
        confounders = []
        all_vars = set(self.variables.keys())
        for z in all_vars:
            if z == signal or z == finding:
                continue
            z_children = set(self.variables[z].children)
            if signal in z_children and finding in z_children:
                confounders.append(z)
        
        return confounders
    
    def causal_chain(self, from_signal: str, to_finding: str, max_depth: int = 4) -> List[List[str]]:
        """查找从信号到结论的因果链"""
        if from_signal not in self.variables or to_finding not in self.variables:
            return []
        
        chains = []
        def dfs(current: str, path: List[str], visited: set, depth: int):
            if depth > max_depth:
                return
            if current == to_finding:
                chains.append(path + [current])
                return
            for child in self.variables.get(current, CausalVariable("_")).children:
                if child not in visited:
                    visited.add(child)
                    dfs(child, path + [current], visited, depth + 1)
                    visited.discard(child)
        
        dfs(from_signal, [], {from_signal}, 0)
        return chains
    
    def reasoning_report(self, findings: List[Dict]) -> Dict:
        """对一组发现生成综合因果推理报告"""
        interventions = []
        counterfactuals = []
        confounders_found = []
        
        for f in findings[:10]:  # 取前11条
            ftype = f.get("type", "")
            signals = f.get("signals", []) or []
            
            # 干预分析
            for sig in signals[:2]:
                result = self.do_intervention(sig, "eliminate")
                if result.get("total_affected", 0) > 0:
                    interventions.append({"finding": ftype, "signal": sig, "result": result})
            
            # 混淆检测
            for sig in signals[:2]:
                confs = self.detect_confounders(sig, ftype)
                if confs:
                    confounders_found.append({"finding": ftype, "signal": sig, "confounders": confs})
        
        return {
            "interventions": interventions[:10],
            "counterfactuals": counterfactuals,
            "confounders": confounders_found[:10],
            "summary": f"因果推理完成：{len(interventions)}项干预分析，发现{len(confounders_found)}个潜在混淆因子",
        }


# ── 全局单例 ──
scm = SCMReasoner()

# 预加载领域因果知识
for var_name in scm._domain_knowledge:
    scm.add_variable(var_name)
for var_name, dk in scm._domain_knowledge.items():
    for cause in dk.get("causes", []):
        scm.add_edge(cause, var_name)
    for effect in dk.get("effects", []):
        scm.add_edge(var_name, effect)
