"""
税务知识图谱 —— 实体-关系-属性的图结构推理

设计原则：
  - 节点：企业/供应商/客户/人员/发票/法条/风险类型
  - 边：供应/销售/雇佣/关联/引用/触发
  - 支持多跳推理：企业→供应商→关联人员→其他企业
  - 与因果网络互补：因果网络负责"什么导致什么"，知识图谱负责"谁和谁什么关系"

使用：
  from engine.knowledge_graph import kg
  kg.add_entity("enterprise", "广州纺织", {"industry": "纺织业"})
  kg.add_relation("广州纺织", "深圳染整", "委托加工")
  paths = kg.find_paths("广州纺织", "虚开发票风险")
"""
import json, os, heapq
from datetime import datetime
from typing import Dict, List, Set, Tuple, Any, Optional
from collections import defaultdict, deque


class KnowledgeGraph:
    """税务领域知识图谱"""
    
    def __init__(self):
        self._entities: Dict[str, Dict] = {}     # id → {type, props}
        self._relations: List[Dict] = []          # [{from, to, type, props}]
        self._adjacency: Dict[str, List[Tuple[str, str, Dict]]] = defaultdict(list)  # from → [(to, rel_type, props)]
        self._reverse_adj: Dict[str, List[Tuple[str, str, Dict]]] = defaultdict(list)  # to → [(from, rel_type, props)]
        self._index: Dict[str, List[str]] = defaultdict(list)  # keyword → [entity_ids]
    
    # ── 实体管理 ──
    def add_entity(self, etype: str, eid: str, props: Dict = None):
        """添加或更新实体"""
        if eid in self._entities:
            self._entities[eid].update(props or {})
        else:
            self._entities[eid] = {"type": etype, "props": props or {}, "created_at": datetime.now().isoformat()}
        # 建立关键词索引
        for val in [etype, eid] + list((props or {}).values()):
            if isinstance(val, str) and len(val) > 1:
                self._index[val.lower()].append(eid)
    
    def get_entity(self, eid: str) -> Optional[Dict]:
        return self._entities.get(eid)
    
    def find_entities(self, etype: str = None, keyword: str = None) -> List[str]:
        """查找实体"""
        if keyword:
            ids = set(self._index.get(keyword.lower(), []))
        else:
            ids = set(self._entities.keys())
        if etype:
            ids = {eid for eid in ids if self._entities[eid].get("type") == etype}
        return list(ids)
    
    # ── 关系管理 ──
    def add_relation(self, from_id: str, to_id: str, rel_type: str, props: Dict = None):
        """添加关系"""
        rel = {"from": from_id, "to": to_id, "type": rel_type, "props": props or {}, "timestamp": datetime.now().isoformat()}
        self._relations.append(rel)
        self._adjacency[from_id].append((to_id, rel_type, props or {}))
        self._reverse_adj[to_id].append((from_id, rel_type, props or {}))
    
    # ── 图推理 ──
    def get_neighbors(self, eid: str, rel_type: str = None, direction: str = "out") -> List[Tuple[str, str, Dict]]:
        """获取邻居节点"""
        if direction == "out":
            neighbors = self._adjacency.get(eid, [])
        else:
            neighbors = self._reverse_adj.get(eid, [])
        if rel_type:
            neighbors = [(n, t, p) for n, t, p in neighbors if t == rel_type]
        return neighbors
    
    def find_paths(self, from_id: str, to_id: str, max_depth: int = 3) -> List[List[Dict]]:
        """BFS查找两个实体之间的所有路径"""
        if from_id not in self._adjacency:
            return []
        paths = []
        queue = deque([(from_id, [])])
        visited_paths = set()
        
        while queue:
            current, path = queue.popleft()
            if len(path) >= max_depth:
                continue
            for neighbor, rel_type, props in self._adjacency.get(current, []):
                step = {"from": current, "to": neighbor, "type": rel_type}
                new_path = path + [step]
                path_sig = "→".join(s["to"] for s in new_path)
                if path_sig in visited_paths:
                    continue
                visited_paths.add(path_sig)
                if neighbor == to_id:
                    paths.append(new_path)
                elif len(new_path) < max_depth:
                    queue.append((neighbor, new_path))
        return paths
    
    def find_connected_component(self, eid: str, max_depth: int = 3) -> Dict[str, List]:
        """查找实体的关联子图"""
        nodes = set()
        edges = []
        queue = deque([(eid, 0)])
        visited = set()
        
        while queue:
            current, depth = queue.popleft()
            if current in visited or depth > max_depth:
                continue
            visited.add(current)
            nodes.add(current)
            for neighbor, rel_type, props in self._adjacency.get(current, []):
                edges.append({"from": current, "to": neighbor, "type": rel_type})
                if neighbor not in visited:
                    queue.append((neighbor, depth + 1))
        
        return {"nodes": list(nodes), "edges": edges}
    
    def detect_cycles(self, eid: str, max_depth: int = 4) -> List[List[Dict]]:
        """检测闭环：企业→供应商→...→企业"""
        cycles = []
        
        def dfs(current, start, path, visited, depth):
            if depth > max_depth:
                return
            for neighbor, rel_type, props in self._adjacency.get(current, []):
                if neighbor == start and len(path) >= 1:
                    cycles.append(path + [{"from": current, "to": neighbor, "type": rel_type}])
                    continue
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                dfs(neighbor, start, path + [{"from": current, "to": neighbor, "type": rel_type}], visited, depth + 1)
                visited.discard(neighbor)
        
        dfs(eid, eid, [], {eid}, 0)
        return cycles
    
    # ── 多跳推理 ──
    def multi_hop_query(self, start_id: str, relation_path: List[str]) -> List[str]:
        """多跳查询：企业→供应→关联人员→控制→其他企业"""
        current = {start_id}
        for rel_type in relation_path:
            next_set = set()
            for eid in current:
                for neighbor, rtype, _ in self._adjacency.get(eid, []):
                    if rtype == rel_type:
                        next_set.add(neighbor)
            current = next_set
            if not current:
                break
        return list(current)
    
    # ── 统计与导入 ──
    def get_stats(self) -> Dict:
        return {
            "total_entities": len(self._entities),
            "total_relations": len(self._relations),
            "entity_types": Counter(e["type"] for e in self._entities.values()),
            "relation_types": Counter(r["type"] for r in self._relations),
            "densest_entities": sorted(self._adjacency.items(), key=lambda x: len(x[1]), reverse=True)[:5],
        }
    
    def import_from_analysis(self, company_name: str, findings: List[Dict], invoices: List[Dict] = None, bank_txs: List[Dict] = None):
        """从分析结果导入知识图谱"""
        # 企业节点
        self.add_entity("enterprise", company_name, {"source": "analysis"})
        
        # 供应商节点（从进项发票）
        if invoices:
            suppliers = set()
            for inv in invoices:
                supplier = inv.get("对方公司名称") or inv.get("seller_name") or inv.get("supplier", "")
                if supplier and supplier != company_name:
                    suppliers.add(supplier)
                    self.add_entity("supplier", supplier, {"source": "invoice"})
                    self.add_relation(company_name, supplier, "采购", {"source": "invoice"})
            
            # 客户节点（从销项发票）
            for inv in invoices:
                buyer = inv.get("对方公司名称") or inv.get("buyer_name") or inv.get("customer", "")
                if buyer and buyer != company_name:
                    self.add_entity("customer", buyer, {"source": "invoice"})
                    self.add_relation(buyer, company_name, "采购", {"source": "invoice"})
        
        # 风险节点
        for f in findings:
            risk_type = f.get("type") or f.get("domain", "")
            if risk_type:
                risk_id = f"risk:{risk_type}"
                self.add_entity("risk", risk_id, {"level": f.get("level", ""), "count": 1})
                self.add_relation(company_name, risk_id, "触发", {"finding_count": 1})
    
    def persist(self, filepath: str = None):
        """持久化到JSON"""
        if not filepath:
            filepath = os.path.join(os.path.dirname(__file__), "..", "static", "knowledge_graph.json")
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({
                "entities": {k: {"type": v["type"], "props": v["props"]} for k, v in self._entities.items()},
                "relations": self._relations[-1000:],
                "updated_at": datetime.now().isoformat(),
            }, f, ensure_ascii=False, indent=2, default=str)
    
    def load(self, filepath: str = None):
        """从JSON加载"""
        if not filepath:
            filepath = os.path.join(os.path.dirname(__file__), "..", "static", "knowledge_graph.json")
        if not os.path.exists(filepath):
            return
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        for eid, edata in data.get("entities", {}).items():
            self.add_entity(edata["type"], eid, edata.get("props", {}))
        for rel in data.get("relations", []):
            self.add_relation(rel["from"], rel["to"], rel["type"], rel.get("props", {}))


# ── 全局单例 ──
kg = KnowledgeGraph()

from collections import Counter
