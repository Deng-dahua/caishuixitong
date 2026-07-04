# ═══════════════════════════════════════════════════════════════
# 跨企业关系网引擎 (Cross-Enterprise Relationship Graph)
#
# 设计理念：
#   从"单企业独立分析"进化为"跨企业关联检测"——
#   系统内所有企业自动构建关系图谱：
#   共享供应商 → 可能同一控制人控制多家企业做供应链操作
#   共享客户 → 可能通过不同主体分散收入
#   共享人员 → 法定代表人或财务负责人在多家企业任职
#
#   示例输出：
#   "A公司和B公司共享3家供应商（XX公司、YY公司、ZZ公司）
#    → 关联交易风险：两家企业可能为同一实际控制人"
# ═══════════════════════════════════════════════════════════════

import json
import os
from typing import Dict, List, Set, Tuple, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class EnterpriseNode:
    """企业节点"""
    company_id: int
    name: str
    legal_rep: str = ""
    shareholders: List[str] = field(default_factory=list)
    directors: List[str] = field(default_factory=list)
    supervisors: List[str] = field(default_factory=list)
    suppliers: Set[str] = field(default_factory=set)
    customers: Set[str] = field(default_factory=set)
    employees: Set[str] = field(default_factory=set)


@dataclass
class Relationship:
    """企业间关系"""
    company_a: str  # 企业名
    company_b: str
    relation_type: str  # shared_supplier / shared_customer / shared_personnel / same_legal_rep
    entities: List[str]  # 共享的具体实体
    risk_level: str  # high / medium / low
    description: str


class CrossEnterpriseGraph:
    """
    跨企业关系图谱
    
    用法：
        graph = CrossEnterpriseGraph(db)
        relationships = graph.build_graph()
        # relationships: [{company_a, company_b, type, entities, risk}]
    """
    
    def __init__(self, db):
        self.db = db
        self.nodes: Dict[int, EnterpriseNode] = {}
        self.relationships: List[Relationship] = []
    
    def build_graph(self) -> Dict:
        """构建完整关系图"""
        self._load_companies()
        self._load_suppliers()
        self._load_customers()
        self._detect_shared_suppliers()
        self._detect_shared_customers()
        self._detect_shared_personnel()
        self._detect_same_legal_rep()
        return self._summarize()
    
    def _load_companies(self):
        """加载所有企业基本信息"""
        try:
            from database import Company
            companies = self.db.query(Company).all()
            for c in companies:
                node = EnterpriseNode(
                    company_id=c.id,
                    name=c.name or f"企业{c.id}",
                    legal_rep=c.legal_representative or "",
                )
                # 股东
                for s in c.shareholders:
                    node.shareholders.append(s.name or "")
                # 董事
                for d in c.directors:
                    node.directors.append(d.name or "")
                # 监事
                for s in c.supervisors:
                    node.supervisors.append(s.name or "")
                self.nodes[c.id] = node
        except Exception as e:
            print(f"[CrossEnterpriseGraph] 加载企业信息失败: {e}")
    
    def _load_suppliers(self):
        """加载供应商"""
        try:
            from database import PurchaseInvoice
            for company_id in self.nodes:
                suppliers = set()
                try:
                    invoices = self.db.query(PurchaseInvoice).filter(
                        PurchaseInvoice.company_id == company_id
                    ).all()
                    for inv in invoices:
                        seller = inv.seller_name or inv.seller or ""
                        if seller and len(seller) >= 2:
                            suppliers.add(self._normalize(seller))
                except Exception:
                    pass
                if suppliers:
                    self.nodes[company_id].suppliers = suppliers
        except Exception as e:
            print(f"[CrossEnterpriseGraph] 加载供应商失败: {e}")
    
    def _load_customers(self):
        """加载客户"""
        try:
            from database import SalesInvoice
            for company_id in self.nodes:
                customers = set()
                try:
                    invoices = self.db.query(SalesInvoice).filter(
                        SalesInvoice.company_id == company_id
                    ).all()
                    for inv in invoices:
                        buyer = inv.buyer_name or inv.buyer or ""
                        if buyer and len(buyer) >= 2:
                            customers.add(self._normalize(buyer))
                except Exception:
                    pass
                if customers:
                    self.nodes[company_id].customers = customers
        except Exception as e:
            print(f"[CrossEnterpriseGraph] 加载客户失败: {e}")
    
    def _normalize(self, name: str) -> str:
        """名称标准化"""
        if not name:
            return ""
        # 去除常见后缀
        for suffix in ["有限公司", "有限责任公司", "股份有限公司", "（", "）", "(", ")"]:
            name = name.replace(suffix, "")
        return name.strip()[:30]
    
    def _detect_shared_suppliers(self):
        """检测共享供应商"""
        company_ids = list(self.nodes.keys())
        for i in range(len(company_ids)):
            for j in range(i + 1, len(company_ids)):
                a = self.nodes[company_ids[i]]
                b = self.nodes[company_ids[j]]
                shared = a.suppliers & b.suppliers
                if len(shared) >= 2:  # 共享2家以上
                    self.relationships.append(Relationship(
                        company_a=a.name,
                        company_b=b.name,
                        relation_type="shared_supplier",
                        entities=list(shared)[:10],
                        risk_level="high" if len(shared) >= 3 else "medium",
                        description=f"两家企业共享{len(shared)}家供应商，"
                                     f"可能存在关联交易或同一实际控制人"
                    ))
    
    def _detect_shared_customers(self):
        """检测共享客户"""
        company_ids = list(self.nodes.keys())
        for i in range(len(company_ids)):
            for j in range(i + 1, len(company_ids)):
                a = self.nodes[company_ids[i]]
                b = self.nodes[company_ids[j]]
                shared = a.customers & b.customers
                if len(shared) >= 2:
                    self.relationships.append(Relationship(
                        company_a=a.name,
                        company_b=b.name,
                        relation_type="shared_customer",
                        entities=list(shared)[:10],
                        risk_level="medium",
                        description=f"两家企业共享{len(shared)}家客户，"
                                     f"需排查是否通过多主体分散收入或利润转移"
                    ))
    
    def _detect_shared_personnel(self):
        """检测共享人员（法定代表人/股东/董事/监事）"""
        def all_personnel(node: EnterpriseNode) -> Set[str]:
            p = set()
            if node.legal_rep: p.add(node.legal_rep)
            p.update(node.shareholders)
            p.update(node.directors)
            p.update(node.supervisors)
            return {x for x in p if x and len(x) >= 2}
        
        company_ids = list(self.nodes.keys())
        for i in range(len(company_ids)):
            for j in range(i + 1, len(company_ids)):
                a = self.nodes[company_ids[i]]
                b = self.nodes[company_ids[j]]
                ap = all_personnel(a)
                bp = all_personnel(b)
                shared = ap & bp
                if shared:
                    self.relationships.append(Relationship(
                        company_a=a.name,
                        company_b=b.name,
                        relation_type="shared_personnel",
                        entities=list(shared),
                        risk_level="high" if len(shared) >= 2 else "medium",
                        description=f"两家企业有{len(shared)}名人员重合：{', '.join(list(shared)[:5])}，"
                                     f"可能为同一实际控制人控制的关联企业"
                    ))
    
    def _detect_same_legal_rep(self):
        """检测同一法定代表人"""
        reps = defaultdict(list)
        for node in self.nodes.values():
            if node.legal_rep:
                reps[node.legal_rep].append(node.name)
        
        for rep, companies in reps.items():
            if len(companies) >= 2:
                for i in range(len(companies)):
                    for j in range(i + 1, len(companies)):
                        self.relationships.append(Relationship(
                            company_a=companies[i],
                            company_b=companies[j],
                            relation_type="same_legal_rep",
                            entities=[rep],
                            risk_level="high",
                            description=f"同一法定代表人「{rep}」同时担任两家企业的法定代表人，"
                                         f"构成关联企业"
                        ))
    
    def _summarize(self) -> Dict:
        """汇总关系图分析结果"""
        # 去重
        unique_rels = {}
        for rel in self.relationships:
            key = tuple(sorted([rel.company_a, rel.company_b]) + [rel.relation_type])
            if key not in unique_rels:
                unique_rels[key] = rel
        
        self.relationships = list(unique_rels.values())
        
        high_risk = sum(1 for r in self.relationships if r.risk_level == "high")
        medium_risk = sum(1 for r in self.relationships if r.risk_level == "medium")
        
        return {
            "total_companies": len(self.nodes),
            "total_relationships": len(self.relationships),
            "high_risk_relationships": high_risk,
            "medium_risk_relationships": medium_risk,
            "relationships": [
                {
                    "company_a": r.company_a,
                    "company_b": r.company_b,
                    "type": r.relation_type,
                    "shared_entities": r.entities,
                    "risk_level": r.risk_level,
                    "description": r.description,
                }
                for r in self.relationships
            ],
            "companies": [
                {
                    "id": n.company_id,
                    "name": n.name,
                    "legal_rep": n.legal_rep,
                    "supplier_count": len(n.suppliers),
                    "customer_count": len(n.customers),
                }
                for n in self.nodes.values()
            ],
            "summary": (
                f"系统内共{len(self.nodes)}家企业，"
                f"发现{len(self.relationships)}条跨企业关联关系"
                f"（高风险{high_risk}条、中风险{medium_risk}条）。"
                if self.relationships else
                f"系统内{len(self.nodes)}家企业，未发现明显的跨企业关联关系。"
            )
        }


def run_cross_enterprise_analysis(db) -> Dict:
    """
    一键调用：构建跨企业关系图
    
    返回: 关系图分析结果
    """
    graph = CrossEnterpriseGraph(db)
    return graph.build_graph()
