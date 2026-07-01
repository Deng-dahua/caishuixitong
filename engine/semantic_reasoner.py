"""
税务语义理解引擎 — 让系统理解"染色加工费"≈"委托染整"

核心能力：
1. 品名词义扩展（同义词/近义词/行业别名映射）
2. 文本语义相似度（基于共现和结构，无需外部embedding）
3. 法条意图匹配（理解"不得抵扣"≈"禁止抵扣"≈"不能作为进项税额"）
4. 行业术语归一化（各地区/各企业对同一事物的不同叫法）
"""
import json, os, re
from collections import defaultdict, Counter
from typing import Dict, List, Any, Optional, Tuple

# ═══════════ 税务语义词典 ═══════════
# 每个词条：标准名 → [同义词列表]
TAX_SEMANTIC_DICT = {
    # 加工类
    "加工费": ["加工费", "加工服务费", "加工劳务费", "委托加工", "外协加工", "代加工", "来料加工",
            "印染加工", "染色加工", "染整加工", "印花加工", "洗水加工", "绣花加工",
            "电镀加工", "喷涂加工", "热处理加工", "机加工", "CNC加工", "数控加工",
            "贴片加工", "组装加工", "切割加工", "焊接加工", "冲压加工"],
    "染色加工": ["染色加工", "染色", "印染", "染整", "漂染", "扎染", "蜡染", "印花", "定型", "后整理", "染色加工费", "印染加工"],
    "包装物": ["纸箱", "纸盒", "包装袋", "塑料袋", "编织袋", "气泡膜", "珍珠棉", "缠绕膜", "胶带", "打包带", "托盘", "木箱", "木托盘"],
    
    # 运输物流
    "运输费": ["运输费", "运费", "物流费", "快递费", "配送费", "搬运费", "装卸费", "货运", "快运", "零担", "整车运输"],
    "物流服务": ["物流服务", "仓储服务", "配送服务", "分拣服务", "供应链管理", "货代", "报关", "报检"],
    
    # 原材料
    "棉纱": ["棉纱", "涤棉纱", "纯棉纱", "混纺纱", "棉线", "缝纫线", "绣花线"],
    "布料": ["布料", "布料加工", "布料采购", "面料", "里料", "辅料", "纺织品", "针织品", "梭织品"],
    "钢材": ["钢材", "钢板", "钢管", "螺纹钢", "线材", "型钢", "槽钢", "角钢", "工字钢", "H型钢", "方管", "圆管"],
    
    # 费用
    "租金": ["租金", "房租", "厂房租金", "办公室租金", "仓库租金", "场地租金", "租赁费"],
    "水电费": ["电费", "水费", "水电费", "燃气费", "暖气费", "动力费", "能源费"],
    "办公费": ["办公用品", "文具", "打印纸", "墨盒", "硒鼓", "办公耗材", "办公设备"],
    "差旅费": ["差旅费", "交通费", "住宿费", "机票", "火车票", "酒店", "出差补贴"],
    "咨询费": ["咨询费", "顾问费", "服务费", "技术服务", "管理咨询", "财务咨询", "法律服务", "律师费"],
    
    # 业务
    "销售收入": ["销售收入", "主营业务收入", "产品销售收入", "商品销售收入", "服务收入", "营业收入", "货款"],
    "采购成本": ["采购成本", "进货成本", "原材料成本", "采购金额", "进货款", "购货款"],
    
    # 资产
    "固定资产": ["设备", "机器", "仪器", "车辆", "房产", "厂房", "建筑物", "生产线"],
    "无形资产": ["软件", "专利", "商标", "著作权", "专有技术", "特许权"],
    
    # 人员
    "工资": ["工资", "薪资", "薪酬", "薪金", "报酬", "劳务费", "奖金", "津贴", "补贴", "加班费"],
    "社保": ["社保", "社会保险", "养老保险", "医疗保险", "失业保险", "工伤保险", "生育保险"],
}

# 法条语义等价
LAW_SEMANTIC_DICT = {
    "不得抵扣": ["不得抵扣", "不允许抵扣", "不可以抵扣", "不能抵扣", "不得从销项税额中抵扣", "不能作为进项抵扣"],
    "免税": ["免征增值税", "免税", "不征收增值税", "增值税免税", "享受免税待遇", "免征"],
    "视同销售": ["视同销售", "视为销售", "按销售处理", "比照销售", "参照销售"],
    "加计扣除": ["加计扣除", "加成扣除", "额外扣除", "加计抵减", "加计摊销"],
    "核定征收": ["核定征收", "核定", "查定征收", "定额征收", "核定应纳税额"],
}

class SemanticEngine:
    """税务语义理解引擎"""
    
    def __init__(self):
        self._build_index()
    
    def _build_index(self):
        """构建反向索引：任意词 → 标准名"""
        self._word_to_standard = {}
        for standard, synonyms in TAX_SEMANTIC_DICT.items():
            for syn in synonyms:
                self._word_to_standard[syn] = standard
        
        # 法条语义索引
        self._law_to_standard = {}
        for standard, synonyms in LAW_SEMANTIC_DICT.items():
            for syn in synonyms:
                self._law_to_standard[syn] = standard
    
    def normalize(self, text: str) -> str:
        """将文本中的行业术语统一为标准名称"""
        if not text: return ""
        result = text
        # 按同义词长度降序替换（优先最长匹配）
        sorted_syns = sorted(self._word_to_standard.keys(), key=len, reverse=True)
        for syn in sorted_syns:
            if syn in result:
                std = self._word_to_standard[syn]
                result = result.replace(syn, f"[{std}]_{syn}")
        return result
    
    def get_standard(self, term: str) -> Optional[str]:
        """获取术语的标准名称（优先最长最精确匹配）"""
        if not term: return None
        # 精确匹配优先
        if term in self._word_to_standard:
            return self._word_to_standard[term]
        # 找所有匹配的synonym，选最长的（最精确）
        matches = []
        for syn, std in self._word_to_standard.items():
            if syn in term:
                matches.append((len(syn), syn, std))
        if matches:
            matches.sort(key=lambda x: -x[0])
            return matches[0][2]
        return None
    
    def get_synonyms(self, standard_term: str) -> List[str]:
        """获取标准术语的所有同义词"""
        return TAX_SEMANTIC_DICT.get(standard_term, [standard_term])
    
    def is_similar(self, term_a: str, term_b: str, threshold: float = 0.6) -> bool:
        """判断两个术语是否语义相似"""
        std_a = self.get_standard(term_a)
        std_b = self.get_standard(term_b)
        if std_a and std_a == std_b:
            return True
        # 字符串相似度兜底
        return self._str_similarity(term_a, term_b) >= threshold
    
    def _str_similarity(self, a: str, b: str) -> float:
        """基于公共子串的字符串相似度"""
        if not a or not b: return 0.0
        a, b = a.lower(), b.lower()
        # Jaccard on bigrams
        a_grams = set(a[i:i+2] for i in range(len(a)-1))
        b_grams = set(b[i:i+2] for i in range(len(b)-1))
        if not a_grams or not b_grams: return 0.0
        intersection = a_grams & b_grams
        union = a_grams | b_grams
        return len(intersection) / len(union)
    
    def match_law_intent(self, query: str, law_text: str) -> bool:
        """判断用户查询和法条文本是否有相同的法律意图"""
        # 将双方都归一化
        q_norm = self.normalize(query)
        l_norm = self.normalize(law_text)
        # 检查共同的标准化标签
        import re
        q_tags = set(re.findall(r'\[(.*?)\]', q_norm))
        l_tags = set(re.findall(r'\[(.*?)\]', l_norm))
        return len(q_tags & l_tags) > 0
    
    def find_similar_products(self, product_name: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """找与给定品名语义最相似的其他品名"""
        std = self.get_standard(product_name)
        if std:
            synonyms = self.get_synonyms(std)
            # 排名：精确匹配 > 同义词 > 字符串相似
            results = [(s, 1.0 if s == product_name else 0.9) for s in synonyms[:top_k]]
            return sorted(results, key=lambda x: -x[1])[:top_k]
        # 无匹配时用字符串相似度
        all_terms = list(self._word_to_standard.keys())
        scored = [(t, self._str_similarity(product_name, t)) for t in all_terms]
        return sorted(scored, key=lambda x: -x[1])[:top_k]
    
    def extract_tax_keywords(self, text: str) -> List[str]:
        """从文本中提取税务关键词（归一化后）"""
        keywords = []
        for syn, std in sorted(self._word_to_standard.items(), key=lambda x: -len(x[0])):
            if syn in text:
                keywords.append(std)
                text = text.replace(syn, "", 1)  # 避免重复计数
        return list(set(keywords))[:10]


# 全局语义引擎
semantic = SemanticEngine()

def get_semantic_engine() -> SemanticEngine:
    return semantic
