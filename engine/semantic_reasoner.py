"""
税务语义推理引擎 — 语义理解 + 类比推理

2号工程 — 语义理解层:
  系统不再只做字符串匹配，而是理解"染色加工费"和"委托染整"是同一件事。
  "品名差异"和"进销品名不匹配"是同一类风险。
  
  方法：关键词共现网络 + 编辑距离 + 税务领域词库

3号工程 — 创造性假设引擎:
  当遇到从未见过的新数据模式时，不做"未知"标记载然停止，
  而是找最近邻的已知模式，基于类比推理生成试探性假设。
  "这个模式我没见过，但它最像虚开进项的模式 → 先按虚开方向调查"
"""
import json, os, re, math
from collections import defaultdict, Counter
from typing import List, Dict, Any, Optional, Set, Tuple
from itertools import combinations

# ==================== 1. 税务语义嵌入 ====================

# 税务领域同义词库（品名/摘要/法规）
TAX_SEMANTIC_SYNONYMS = {
    # 加工费
    "加工": ["加工费", "加工", "染整", "染色", "印花", "涂层", "水洗", "砂洗", 
             "定型", "复合", "贴合", "磨毛", "压光", "压花", "刺绣", "绗缝",
             "烫金", "冲孔", "裁片", "缝制", "车缝", "锁边"],
    "染整加工": ["染整加工费", "染色加工费", "染费", "委托染整", "外发染色", "外包染色"],
    # 委托加工
    "委托加工": ["委托加工", "外发加工", "外包加工", "来料加工", "委外加工", "代加工"],
    # 运输
    "运输物流": ["运输", "运费", "快递", "物流", "装卸", "搬运", "配送", "货运"],
    # 租金
    "租金物业": ["房租", "租金", "物业", "水电", "电费", "水费", "租赁"],
    # 咨询服务
    "咨询服务": ["咨询", "顾问", "服务费", "技术服务", "管理服务", "居间", "中介"],
    # 维修
    "维修保养": ["维修", "保养", "修理", "维护", "检测"],
    # 办公
    "办公耗材": ["办公", "文具", "打印", "复印", "纸张", "墨盒", "硒鼓"],
    # 差旅
    "差旅招待": ["差旅", "住宿", "餐饮", "机票", "火车票", "招待", "宴请"],
    # 广告
    "广告推广": ["广告", "推广", "营销", "展会", "展览", "促销"],
    # 保险
    "保险": ["保险", "社保", "公积金", "年金"],
    # 软件
    "软件服务": ["软件", "系统", "平台", "APP", "小程序", "SaaS", "技术开发", "软件开发"],
    # 设备
    "设备采购": ["设备", "机器", "机械", "仪器", "仪表", "工具"],
    # 原材料
    "纺织品原料": ["坯布", "棉纱", "纱线", "涤纶", "锦纶", "氨纶", "粘胶", "天丝",
                   "莫代尔", "羊毛", "羊绒", "真丝", "麻", "竹纤维", "大豆纤维",
                   "面料", "布料", "针织", "梭织", "无纺布"],
    "化工原料": ["染料", "助剂", "柔软剂", "树脂", "固色剂", "漂白", "双氧水",
                 "烧碱", "醋酸", "液碱", "硫酸", "盐酸"],
}

# 风险类型同义词
RISK_TYPE_SYNONYMS = {
    "隐匿收入": ["隐匿收入", "未申报收入", "账外经营", "少报收入", "不开票收入", "体外循环"],
    "虚开发票": ["虚开", "虚开发票", "假发票", "无真实交易", "空转", "走账"],
    "品名不匹配": ["品名差异", "品名不匹配", "进销品名不一致", "进销不匹配"],
    "账簿问题": ["账外", "内账", "外账", "阴阳账", "假账", "两套账"],
    "关联交易": ["关联交易", "关联方", "关联企业", "转移定价", "利润转移"],
}

class SemanticMatcher:
    """税务语义匹配器"""
    
    def __init__(self):
        self.synonym_dict = TAX_SEMANTIC_SYNONYMS
        self.risk_synonyms = RISK_TYPE_SYNONYMS
        self._build_index()
    
    def _build_index(self):
        """构建同义词反向索引"""
        self.word_to_category = {}
        for category, words in self.synonym_dict.items():
            for w in words:
                self.word_to_category[w] = category
    
    def infer_goods_category(self, goods_name: str) -> str:
        """推断品名的语义类别"""
        goods_lower = goods_name.lower()
        for category, keywords in self.synonym_dict.items():
            for kw in keywords:
                if kw in goods_name:
                    return category
        return goods_name[:10]  # 无匹配时返回原始名称前10字
    
    def are_semantically_same(self, goods_a: str, goods_b: str) -> Tuple[bool, float]:
        """判断两个品名是否语义相同
        
        返回：(是否相同, 相似度0-1)
        """
        cat_a = self.infer_goods_category(goods_a)
        cat_b = self.infer_goods_category(goods_b)
        
        # 同类 → 相似
        if cat_a == cat_b and cat_a not in (goods_a[:10], goods_b[:10]):
            return True, 0.9
        
        # 编辑距离
        dist = self._edit_distance(goods_a, goods_b)
        max_len = max(len(goods_a), len(goods_b), 1)
        edit_sim = 1 - dist / max_len
        
        if edit_sim > 0.7:
            return True, edit_sim
        
        return False, edit_sim
    
    def match_risk_type(self, text: str) -> Optional[str]:
        """从文本中识别风险类型"""
        for risk_type, keywords in self.risk_synonyms.items():
            for kw in keywords:
                if kw in text:
                    return risk_type
        return None
    
    @staticmethod
    def _edit_distance(s1: str, s2: str) -> int:
        """计算编辑距离"""
        m, n = len(s1), len(s2)
        dp = [[0] * (n+1) for _ in range(m+1)]
        for i in range(m+1): dp[i][0] = i
        for j in range(n+1): dp[0][j] = j
        for i in range(1, m+1):
            for j in range(1, n+1):
                cost = 0 if s1[i-1] == s2[j-1] else 1
                dp[i][j] = min(dp[i-1][j]+1, dp[i][j-1]+1, dp[i-1][j-1]+cost)
        return dp[m][n]


# ==================== 2. 创造性假设引擎（类比推理） ====================

class CreativeHypothesisEngine:
    """创造性假设引擎 —— 遇到未知模式时，用类比推理生成试探性假设
    
    原理：
      1. 将当前数据模式的信号指纹与所有已知模式比较
      2. 找到最相似的K个已知模式（最近邻）
      3. 如果最相似的已知模式导致结论X → 试探性假设当前模式也可能导致X
      4. 置信度 = 相似度 × 已知模式的置信度
      5. 标记为"创造性假设"→ 需验证
    """
    
    def __init__(self):
        self.semantic = SemanticMatcher()
        self.known_patterns: List[Dict] = []  # 从因果网络加载
        self.creative_hypotheses: List[Dict] = []
    
    def load_known_patterns(self, causal_edges: List, multi_patterns: List):
        """从因果网络加载已知模式"""
        self.known_patterns = []
        
        for edge in causal_edges:
            if hasattr(edge, 'source_signals'):
                signals = edge.source_signals
            elif isinstance(edge, dict):
                signals = edge.get("signals", edge.get("source_signals", []))
            else:
                continue
            
            if hasattr(edge, 'target_finding'):
                finding = edge.target_finding
            elif isinstance(edge, dict):
                finding = edge.get("finding", edge.get("target_finding", ""))
            else:
                continue
            
            if hasattr(edge, 'confidence'):
                conf = edge.confidence
            elif isinstance(edge, dict):
                conf = edge.get("confidence", edge.get("conditional_probability", 0.5))
            else:
                conf = 0.5
            
            self.known_patterns.append({
                "signals": set(signals),
                "finding": finding,
                "confidence": float(conf),
            })
        
        for pattern in multi_patterns:
            if hasattr(pattern, 'signals'):
                signals = pattern.signals
            elif isinstance(pattern, dict):
                signals = pattern.get("signals", [])
            else:
                continue
            
            if hasattr(pattern, 'target_finding'):
                finding = pattern.target_finding
            elif isinstance(pattern, dict):
                finding = pattern.get("finding", pattern.get("target_finding", ""))
            else:
                continue
            
            if hasattr(pattern, 'joint_probability'):
                conf = pattern.joint_probability
            elif isinstance(pattern, dict):
                conf = pattern.get("joint_probability", 0.5)
            else:
                conf = 0.5
            
            self.known_patterns.append({
                "signals": set(signals),
                "finding": finding,
                "confidence": float(conf),
            })
    
    def generate_creative_hypotheses(self, unknown_signals: List[str], 
                                      min_similarity: float = 0.3) -> List[Dict]:
        """为未知信号组合生成创造性假设
        
        类比推理：未知信号组合X 最像 已知模式Y → 试探性假设 X也可能导致Y的结论
        """
        unknown_set = set(unknown_signals)
        if not unknown_set or not self.known_patterns:
            return []
        
        hypotheses = []
        
        for pattern in self.known_patterns:
            known_set = pattern["signals"]
            
            # 计算Jaccard相似度
            intersection = len(unknown_set & known_set)
            union = len(unknown_set | known_set)
            jaccard = intersection / union if union > 0 else 0
            
            # 计算加权相似度（重叠信号越多，相似度越高）
            overlap_ratio = intersection / len(known_set) if known_set else 0
            
            # 综合相似度
            similarity = (jaccard * 0.6 + overlap_ratio * 0.4)
            
            if similarity >= min_similarity:
                # 计算创造性假设的置信度
                creative_confidence = similarity * pattern["confidence"]
                
                # 差异信号（未知模式有而已知没有，反之亦然）
                extra_signals = unknown_set - known_set
                missing_signals = known_set - unknown_set
                
                hypothesis = {
                    "type": "creative_hypothesis",
                    "analogy_source": pattern["finding"],
                    "analogy_similarity": round(similarity, 2),
                    "source_confidence": pattern["confidence"],
                    "creative_confidence": round(creative_confidence, 2),
                    "unknown_signals": list(unknown_set),
                    "matched_known_signals": list(unknown_set & known_set),
                    "extra_vs_known": list(extra_signals),
                    "missing_from_known": list(missing_signals),
                    "predicted_finding": pattern["finding"],
                    "reasoning": (
                        f"当前{len(unknown_set)}个信号中有{intersection}个与'{pattern['finding']}'的已知模式重叠"
                        f"(Jaccard={jaccard:.0%})。额外信号{list(extra_signals)[:2]}可能代表新风险维度。"
                        f"基于类比推理，推测可能存在'{pattern['finding']}'风险。"
                    ),
                    "needs_verification": True,
                    "verification_priority": "高" if creative_confidence > 0.6 else "中",
                }
                hypotheses.append(hypothesis)
        
        # 按创造性置信度排序
        hypotheses.sort(key=lambda h: h["creative_confidence"], reverse=True)
        self.creative_hypotheses = hypotheses
        return hypotheses[:10]
    
    def generate_hypothesis_from_scratch(self, unknown_data_pattern: Dict) -> Optional[Dict]:
        """完全未知的模式 — 从零生成最可能的假设
        
        使用语义匹配在最顶层推断可能的结论类型，然后生成试探性假设。
        """
        dimension = unknown_data_pattern.get("dimension", "未知维度")
        detail = unknown_data_pattern.get("detail", "")
        
        # 语义匹配推断风险类型
        risk_type = self.semantic.match_risk_type(detail)
        
        if risk_type:
            return {
                "type": "creative_scratch",
                "dimension": dimension,
                "semantic_risk_match": risk_type,
                "confidence": 0.3,  # 低置信度
                "hypothesis": f"基于语义匹配，'{detail[:50]}'可能与'{risk_type}'有关，建议核实",
                "needs_verification": True,
                "verification_priority": "中",
            }
        
        return None


# ==================== 3. 统一语义推理器 ====================

class SemanticReasoner:
    """统一的语义推理器 — 语义理解 + 类比推理"""
    
    def __init__(self):
        self.matcher = SemanticMatcher()
        self.creative_engine = CreativeHypothesisEngine()
    
    def analyze_goods_consistency(self, pur_invs: List[Dict], sal_invs: List[Dict]) -> Dict:
        """分析进销品名一致性（语义级别而非字符串级别）"""
        results = []
        
        # 收集并分类品名
        pur_categories = Counter()
        sal_categories = Counter()
        
        for inv in pur_invs or []:
            goods = str(inv.get("goods", "")).strip()
            if goods:
                cat = self.matcher.infer_goods_category(goods)
                pur_categories[cat] += 1
        
        for inv in sal_invs or []:
            goods = str(inv.get("goods", "")).strip()
            if goods:
                cat = self.matcher.infer_goods_category(goods)
                sal_categories[cat] += 1
        
        # 比对语义类别
        all_cats = set(pur_categories.keys()) | set(sal_categories.keys())
        
        for cat in all_cats:
            pur_cnt = pur_categories.get(cat, 0)
            sal_cnt = sal_categories.get(cat, 0)
            
            if pur_cnt > 0 and sal_cnt == 0:
                results.append({
                    "category": cat,
                    "type": "有进无销",
                    "detail": f"语义类别'{cat}'在进项中出现{pur_cnt}次但销项中未出现",
                    "semantic_match": True,
                })
            elif pur_cnt == 0 and sal_cnt > 0:
                results.append({
                    "category": cat,
                    "type": "有销无进",
                    "detail": f"语义类别'{cat}'在销项中出现{sal_cnt}次但进项中未出现",
                    "semantic_match": True,
                })
            else:
                results.append({
                    "category": cat,
                    "type": "进销匹配",
                    "detail": f"语义类别'{cat}'进项{pur_cnt}次/销项{sal_cnt}次",
                    "semantic_match": True,
                })
        
        return {
            "total_categories": len(all_cats),
            "matches": sum(1 for r in results if r["type"] == "进销匹配"),
            "mismatches": sum(1 for r in results if r["type"] != "进销匹配"),
            "details": results,
        }
    
    def discover_semantic_patterns(self, invoices: List[Dict]) -> Dict:
        """从发票品名中发现语义模式
        
        找出高频语义类别、异常类别组合、潜在的未识别业务线。
        """
        categories = Counter()
        for inv in invoices or []:
            goods = str(inv.get("goods", "")).strip()
            if goods:
                cat = self.matcher.infer_goods_category(goods)
                categories[cat] += 1
        
        total = sum(categories.values())
        patterns = []
        
        for cat, cnt in categories.most_common(10):
            ratio = cnt / total if total > 0 else 0
            patterns.append({
                "category": cat,
                "count": cnt,
                "ratio": round(ratio, 3),
                "is_dominant": ratio > 0.3,
            })
        
        # 发现异常：占比极高但名称不匹配业务范围的类别
        anomalies = []
        for p in patterns:
            if p["is_dominant"] and p["category"] not in ("纺织品原料", "化工原料", "加工"):
                anomalies.append(p)
        
        return {
            "total_goods": total,
            "unique_categories": len(categories),
            "patterns": patterns,
            "anomalies": anomalies,
        }
    
    def creative_reason(self, unknown_signals: List[str], causal_edges=None, multi_patterns=None) -> Dict:
        """创造性推理：为未知模式生成试探性假设"""
        self.creative_engine.load_known_patterns(causal_edges or [], multi_patterns or [])
        
        hypotheses = self.creative_engine.generate_creative_hypotheses(
            unknown_signals, min_similarity=0.25
        )
        
        return {
            "unknown_signals": unknown_signals,
            "creative_hypotheses": hypotheses,
            "total_generated": len(hypotheses),
            "has_high_confidence": any(h["creative_confidence"] > 0.6 for h in hypotheses),
        }
