"""
税务AGI统一知识库引擎

所有知识集中管理，各引擎统一读写，不再分散在代码/JSON/SQLite三处。

结构：
  policies         — 税收优惠政策（条件/税率/有效期）
  causal_edges     — 因果网络边（信号→结论）
  signal_patterns  — 多信号组合模式
  semantic_dict    — 语义同义词库
  industry_profiles — 行业知识画像
  healing_rules    — 自愈规则
  lessons          — 经验教训
  analysis_history — 分析历史摘要
"""
import json, os, time
from datetime import datetime
from typing import Dict, List, Any, Optional
from threading import Lock

# 知识库路径
_KB_PATH = None

def _get_kb_path():
    global _KB_PATH
    if _KB_PATH is None:
        base = os.path.dirname(os.path.dirname(__file__))
        _KB_PATH = os.path.join(base, "static", "tax_agi_knowledge.json")
    return _KB_PATH

# 线程安全写锁
_kb_lock = Lock()

# ═══════════════════ 知识库结构 ═══════════════════

DEFAULT_KNOWLEDGE = {
    "_meta": {
        "version": "1.0",
        "created_at": "",
        "updated_at": "",
        "description": "税务AGI统一知识库 — 所有模块的知识在此汇聚、生长、进化",
    },
    
    # ─── 1. 税收优惠政策 ───
    "policies": {
        "small_micro": {
            "name": "小型微利企业所得税优惠",
            "law": "财政部税务总局公告2025年第5号",
            "expiry": "2027-12-31",
            "conditions": {
                "应纳税所得额上限": 3000000,
                "从业人数上限": 300,
                "资产总额上限": 50000000,
                "减按比例": 25,
                "优惠税率": 20,
                "有效税率": 5,
            },
        },
        "small_taxpayer": {
            "name": "小规模纳税人增值税减免",
            "law": "财政部税务总局公告2023年第1号",
            "expiry": "2027-12-31",
            "conditions": {"年销售额上限": 5000000},
        },
        "rd_deduction": {
            "name": "研发费用加计扣除",
            "law": "财政部税务总局公告2023年第7号",
            "expiry": "长期",
            "conditions": {"加计比例": 100, "制造业加计比例": 120},
        },
        "high_tech": {
            "name": "高新技术企业15%税率",
            "law": "企业所得税法第28条",
            "expiry": "长期",
            "conditions": {"优惠税率": 15},
        },
        "six_tax": {
            "name": "六税两费减半",
            "law": "财政部税务总局公告2022年第10号",
            "expiry": "2027-12-31",
            "conditions": {"减免比例": 50},
        },
        "software_vat": {
            "name": "软件产品即征即退",
            "law": "财税[2011]100号",
            "expiry": "长期",
            "conditions": {"税负超3%即征即退": True},
        },
        "disabled": {
            "name": "残疾人就业保障金减免",
            "law": "财政部公告2019年第98号",
            "expiry": "2027-12-31",
            "conditions": {"在职职工20人以下免征": True},
        },
        "agri": {
            "name": "农林牧渔所得减免",
            "law": "企业所得税法第27条",
            "expiry": "长期",
            "conditions": {},
        },
        "west": {
            "name": "西部大开发15%税率",
            "law": "财政部公告2020年第23号",
            "expiry": "2030-12-31",
            "conditions": {"优惠税率": 15},
        },
    },
    
    # ─── 2. 因果网络 ───
    "causal_edges": [],
    "signal_patterns": [],
    
    # ─── 3. 语义同义词 ───
    "semantic_dict": {
        "加工": ["加工费", "加工", "染整", "染色", "印花", "涂层", "水洗", "砂洗",
                 "定型", "复合", "贴合", "磨毛", "压光", "刺绣", "绗缝"],
        "染整加工": ["染整加工费", "染色加工费", "染费", "委托染整", "外发染色", "外包染色"],
        "委托加工": ["委托加工", "外发加工", "外包加工", "来料加工", "委外加工", "代加工"],
        "运输物流": ["运输", "运费", "快递", "物流", "装卸", "搬运", "配送", "货运"],
        "租金物业": ["房租", "租金", "物业", "水电", "电费", "水费", "租赁"],
        "咨询服务": ["咨询", "顾问", "服务费", "技术服务", "管理服务", "居间", "中介"],
        "维修保养": ["维修", "保养", "修理", "维护", "检测"],
        "办公耗材": ["办公", "文具", "打印", "复印", "纸张", "墨盒", "硒鼓"],
        "差旅招待": ["差旅", "住宿", "餐饮", "机票", "火车票", "招待", "宴请"],
        "广告推广": ["广告", "推广", "营销", "展会", "展览", "促销"],
        "软件服务": ["软件", "系统", "平台", "APP", "小程序", "SaaS", "技术开发", "软件开发"],
        "设备采购": ["设备", "机器", "机械", "仪器", "仪表", "工具"],
        "纺织品原料": ["坯布", "棉纱", "纱线", "涤纶", "锦纶", "氨纶", "粘胶", "天丝",
                       "莫代尔", "羊毛", "羊绒", "真丝", "麻", "竹纤维", "面料", "布料"],
        "化工原料": ["染料", "助剂", "柔软剂", "树脂", "固色剂", "漂白", "双氧水",
                     "烧碱", "醋酸", "液碱", "硫酸", "盐酸"],
    },
    
    # ─── 4. 风险类型同义词 ───
    "risk_synonyms": {
        "隐匿收入": ["隐匿收入", "未申报收入", "账外经营", "少报收入", "不开票收入", "体外循环"],
        "虚开发票": ["虚开", "虚开发票", "假发票", "无真实交易", "空转", "走账"],
        "品名不匹配": ["品名差异", "品名不匹配", "进销品名不一致", "进销不匹配"],
        "账簿问题": ["账外", "内账", "外账", "阴阳账", "假账", "两套账"],
        "关联交易": ["关联交易", "关联方", "关联企业", "转移定价", "利润转移"],
    },
    
    # ─── 5. 行业知识 ───
    # 数据驱动：不预置任何行业画像。由 auto_extract_knowledge() 在每次分析后
    # 从发现(findings)中自动积累各行业的高频风险/常见品名/分析次数，跨企业沉淀。
    # 严禁在此硬编码单一行业（违反"全行业适用"铁律）。
    "industry_profiles": {},
    
    # ─── 6. 自愈规则 ───
    "healing_rules": [],
    
    # ─── 7. 经验教训 ───
    "lessons": [],
    
    # ─── 8. 分析历史摘要 ───
    "analysis_history": [],
    
    # ─── 9. 信号定义 ───
    "signal_definitions": [
        {"id": "bank_income_excess", "name": "银行收款超额", "threshold": "bank_in_ratio > 1.2"},
        {"id": "supplier_concentration", "name": "供应商高度集中", "threshold": "> 60%"},
        {"id": "processing_fee_exists", "name": "存在加工费发票", "threshold": "boolean"},
        {"id": "pur_without_payment", "name": "进项发票无付款", "threshold": "> 30%"},
        {"id": "goods_mismatch", "name": "进销品名不匹配", "threshold": "> 30%"},
        {"id": "low_data_quality", "name": "资料完整度低", "threshold": "< 40分"},
        {"id": "personnel_overlap", "name": "六员跨企业重叠", "threshold": "boolean"},
        {"id": "has_related_parties", "name": "存在关联方", "threshold": "boolean"},
        {"id": "near_micro_limit", "name": "接近小微门槛", "threshold": "boolean"},
        {"id": "customer_concentration", "name": "客户高度集中", "threshold": "> 60%"},
    ],
}


# ═══════════════════ 知识库引擎 ═══════════════════

class KnowledgeBase:
    """税务AGI统一知识库"""
    
    def __init__(self):
        self._data = None
        self._load()
    
    def _load(self):
        """加载知识库"""
        path = _get_kb_path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
            if not isinstance(self._data, dict):
                self._data = {}
        except:
            self._data = dict(DEFAULT_KNOWLEDGE)
        # 补全骨架：无论来自空文件/旧文件/DEFAULT，都保证结构完整，避免后续 KeyError
        self._data.setdefault("_meta", {})
        self._data["_meta"].setdefault("created_at", datetime.now().isoformat())
        for _k, _default in (
            ("policies", {}), ("causal_edges", []), ("signal_patterns", []),
            ("semantic_dict", {}), ("risk_synonyms", {}), ("industry_profiles", {}),
            ("healing_rules", []), ("lessons", []), ("analysis_history", []),
            ("signal_definitions", []),
        ):
            self._data.setdefault(_k, _default)

    def _save(self):
        """保存知识库"""
        with _kb_lock:
            self._data.setdefault("_meta", {})["updated_at"] = datetime.now().isoformat()
            os.makedirs(os.path.dirname(_get_kb_path()), exist_ok=True)
            with open(_get_kb_path(), "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
    
    # ── 查询接口 ──
    
    def get_policy(self, key: str) -> Optional[Dict]:
        return self._data.get("policies", {}).get(key)
    
    def get_all_policies(self) -> Dict:
        return self._data.get("policies", {})
    
    def get_causal_edges(self) -> List:
        return self._data.get("causal_edges", [])
    
    def get_signal_patterns(self) -> List:
        return self._data.get("signal_patterns", [])
    
    def get_semantic_dict(self) -> Dict:
        return self._data.get("semantic_dict", {})
    
    def get_risk_synonyms(self) -> Dict:
        return self._data.get("risk_synonyms", {})
    
    def get_industry_profile(self, industry: str) -> Dict:
        return self._data.get("industry_profiles", {}).get(industry, {})
    
    def get_healing_rules(self) -> List:
        return self._data.get("healing_rules", [])
    
    def get_lessons(self) -> List:
        return self._data.get("lessons", [])
    
    def get_signal_definitions(self) -> List:
        return self._data.get("signal_definitions", [])
    
    # ── 写入接口 ──
    
    def add_causal_edge(self, edge: Dict):
        """添加因果边（去重）"""
        edges = self._data.setdefault("causal_edges", [])
        # 兼容两种字段名：signals/source_signals, finding/target_finding
        sigs = edge.get("signals", edge.get("source_signals", []))
        find = edge.get("finding", edge.get("target_finding", ""))
        key = (tuple(sigs), find)
        existing = [e for e in edges if (tuple(e.get("signals", e.get("source_signals", []))), e.get("finding", e.get("target_finding", ""))) == key]
        if existing:
            existing[0].update(edge)
        else:
            edges.append(edge)
        self._save()
    
    def add_signal_pattern(self, pattern: Dict):
        """添加多信号模式（兼容 finding/target_finding 字段名）"""
        patterns = self._data.setdefault("signal_patterns", [])
        # 统一字段名：target_finding → finding
        if "target_finding" in pattern and "finding" not in pattern:
            pattern["finding"] = pattern.pop("target_finding")
        key = (tuple(pattern.get("signals", [])), pattern.get("finding", ""))
        existing_keys = [(tuple(p.get("signals", [])), p.get("finding", "")) for p in patterns]
        if key not in existing_keys:
            patterns.append(pattern)
            self._save()
    
    def add_healing_rule(self, rule: Dict):
        """添加自愈规则"""
        self._data.setdefault("healing_rules", []).append(rule)
        self._save()
    
    def add_lesson(self, lesson: str, category: str = "通用"):
        """添加经验教训"""
        self._data.setdefault("lessons", []).append({
            "lesson": lesson, "category": category,
            "timestamp": datetime.now().isoformat(),
        })
        self._save()
    
    def add_analysis_to_history(self, analysis: Dict):
        """添加分析摘要到历史"""
        history = self._data.setdefault("analysis_history", [])
        history.append({
            "trace_id": analysis.get("trace_id", ""),
            "company_name": analysis.get("company_name", ""),
            "industry": analysis.get("industry", ""),
            "findings_count": analysis.get("findings_count", 0),
            "high_risk_count": analysis.get("high_risk_count", 0),
            "timestamp": datetime.now().isoformat(),
        })
        # 只保留最近102条
        if len(history) > 100:
            self._data["analysis_history"] = history[-100:]
        self._save()
    
    def update_industry_profile(self, industry: str, profile: Dict):
        """更新行业画像"""
        profiles = self._data.setdefault("industry_profiles", {})
        existing = profiles.get(industry, {})
        existing.update(profile)
        profiles[industry] = existing
        self._save()
    
    def update_policy(self, key: str, policy_update: Dict):
        """更新政策信息"""
        self._data.setdefault("policies", {})[key] = policy_update
        self._save()
    
    # ── 综合查询 ──
    
    def get_full_knowledge(self) -> Dict:
        """获取完整知识库快照"""
        return {
            "meta": self._data.get("_meta", {}),
            "policies_count": len(self._data.get("policies", {})),
            "causal_edges_count": len(self._data.get("causal_edges", [])),
            "patterns_count": len(self._data.get("signal_patterns", [])),
            "semantic_categories": len(self._data.get("semantic_dict", {})),
            "industries_tracked": len(self._data.get("industry_profiles", {})),
            "healing_rules_count": len(self._data.get("healing_rules", [])),
            "lessons_count": len(self._data.get("lessons", [])),
            "analyses_tracked": len(self._data.get("analysis_history", [])),
        }
    
    def query_knowledge(self, query_type: str, query_params: Dict = None) -> Any:
        """通用知识查询接口"""
        if query_type == "policy":
            return self.get_policy(query_params.get("key", ""))
        elif query_type == "industry":
            return self.get_industry_profile(query_params.get("industry", ""))
        elif query_type == "semantic_category":
            goods = query_params.get("goods", "")
            return self._infer_category(goods)
        elif query_type == "similar_risks":
            return self._find_similar_risks(query_params.get("finding_type", ""))
        else:
            return None
    
    def _infer_category(self, goods_name: str) -> str:
        """从语义词典推断品名类别"""
        for cat, words in self._data.get("semantic_dict", {}).items():
            for w in words:
                if w in goods_name:
                    return cat
        return ""
    
    def _find_similar_risks(self, finding_type: str) -> List[str]:
        """从风险同义词中找相似风险类型"""
        for risk, synonyms in self._data.get("risk_synonyms", {}).items():
            if finding_type in synonyms:
                return [r for r in self._data.get("risk_synonyms", {}).keys() if r != risk]
        return []


# ═══ v2.0 知识库自生长 ═══

def auto_extract_knowledge(findings: list, company_name: str = "", industry: str = "") -> dict:
    """从分析结果自动提取知识，无需人工录入
    
    提取规则：
    1. 高频信号模式（≥3次出现）→ 注册为新信号模式
    2. 信号-结论共现（≥2次） → 注册为新因果边
    3. 行业特征风险 → 更新行业画像
    
    质量门禁：所有自动提取的知识初始置信度为0.5，需≥3次独立验证才提升到0.8+
    """
    from collections import Counter
    kb = get_kb()
    extracted = {"new_patterns": 0, "new_edges": 0, "industry_updates": 0}
    
    # ── 1. 提取信号模式 ──
    signal_combos = Counter()
    for f in findings:
        signals = tuple(sorted(set(
            s.strip() for s in (f.get("signals", []) or [])
            if s.strip() and len(s.strip()) > 2
        )))
        if len(signals) >= 2:
            signal_combos[signals] += 1
    
    for combo, count in signal_combos.items():
        if count >= 3:
            pattern_key = " + ".join(combo[:3])
            if pattern_key not in str(kb._data.get("signal_patterns", [])):
                kb._data.setdefault("signal_patterns", []).append({
                    "signals": list(combo),
                    "frequency": count,
                    "confidence": min(0.5 + count * 0.1, 0.9),
                    "source": "auto_extracted",
                    "companies": [company_name] if company_name else [],
                })
                extracted["new_patterns"] += 1
    
    # ── 2. 提取因果边 ──
    for f in findings[:30]:
        ftype = f.get("type") or f.get("domain", "")
        signals = f.get("signals", []) or []
        if not ftype or not signals:
            continue
        
        for sig in signals[:2]:  # 取前2个信号
            edge_key = f"{sig}→{ftype}"
            existing = [e for e in kb._data.get("causal_edges", []) 
                       if sig in e.get("signals", []) and ftype in e.get("finding", "")]
            if not existing:
                kb._data.setdefault("causal_edges", []).append({
                    "signals": [sig],
                    "finding": ftype,
                    "confidence": 0.5,
                    "source": f"auto_extracted:{company_name}",
                })
                extracted["new_edges"] += 1
    
    # ── 3. 行业特征（数据驱动：从发现中自动沉淀行业画像，全行业适用）──
    if industry and industry != "未知":
        ip = kb._data.setdefault("industry_profiles", {}).setdefault(industry, {})
        ip["analysis_count"] = ip.get("analysis_count", 0) + 1
        ip["last_analyzed"] = datetime.now().isoformat()

        # 3a. 累积高频风险
        chr_map = ip.setdefault("common_high_risks", {})
        risk_types = Counter(
            f.get("type", "") for f in findings
            if f.get("type") and f.get("level") and "高" in str(f.get("level"))
        )
        for rt, ct in risk_types.most_common(5):
            chr_map[rt] = chr_map.get(rt, 0) + ct
            extracted["industry_updates"] += 1
        # 3b. 由累积数据导出 typical_risks（Top5，不硬编码）
        ip["typical_risks"] = [r for r, _ in Counter(chr_map).most_common(5)]

        # 3c. 累积常见品名（从发现及其证据行中提取 goods/品名 字段，全行业通用）
        goods_map = ip.setdefault("_goods_freq", {})
        for f in findings:
            cands = []
            for key in ("goods", "product", "品名", "goods_name"):
                v = f.get(key)
                if v:
                    cands.append(str(v))
            for ev in (f.get("evidence_rows") or f.get("items") or []):
                if isinstance(ev, dict):
                    for key in ("goods", "品名", "goods_name", "product", "货物名称"):
                        v = ev.get(key)
                        if v:
                            cands.append(str(v))
            for g in cands:
                g = g.strip()[:30]
                if g:
                    goods_map[g] = goods_map.get(g, 0) + 1
        if goods_map:
            ip["common_goods"] = [g for g, _ in Counter(goods_map).most_common(8)]

    # ── 持久化：数据驱动的知识必须存盘，否则跨会话丢失 ──
    kb._save()

    return extracted


# ═══════════════════ 全局单例 ═══════════════════

_kb_instance = None

def get_kb() -> KnowledgeBase:
    """获取知识库全局单例"""
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = KnowledgeBase()
    return _kb_instance


def init_knowledge_base():
    """初始化知识库（首次运行时创建文件）"""
    kb = get_kb()
    print(f"[KB] 税务AGI知识库已就绪: {kb.get_full_knowledge()['policies_count']}项政策 / {kb.get_full_knowledge()['semantic_categories']}类语义")
    return kb
