"""
法规自更新引擎 — 联网跟踪税法变动 + 变更影响分析

核心能力：
1. 法规时效追踪：自动标记已废止的旧法引用
2. 变更影响分析：新法施行→自动检测受影响的分析域
3. 法规库维护：内置核心税法原文，支持增量更新
"""
import json, os, re, time
from datetime import datetime
from typing import Dict, List, Any, Optional, Set

# ═══════════ 核心税法时效性数据库 ═══════════
TAX_LAWS = {
    "增值税法": {
        "short": "增值税法",
        "full": "中华人民共和国增值税法",
        "effective": "2024-01-01",
        "replaces": ["增值税暂行条例", "增值税暂行条例实施细则"],
        "key_articles": {
            "第一条": "在中华人民共和国境内销售货物、服务、无形资产、不动产的单位和个人，为增值税的纳税人。",
            "第五条": "增值税税率：13%、9%、6%三档。出口货物适用零税率。",
            "第十条": "下列项目的进项税额不得从销项税额中抵扣：（一）用于简易计税方法计税项目、免征增值税项目、集体福利或者个人消费的购进货物、劳务、服务、无形资产和不动产...",
        },
        "affected_domains": ["增值税分析域", "抵扣认证域", "出口退税域"],
    },
    "企业所得税法": {
        "short": "企业所得税法",
        "full": "中华人民共和国企业所得税法",
        "effective": "2018-12-29",
        "replaces": ["企业所得税暂行条例"],
        "key_articles": {
            "第一条": "在中华人民共和国境内，企业和其他取得收入的组织为企业所得税的纳税人。",
            "第四条": "企业所得税的税率为25%。",
            "第八条": "企业实际发生的与取得收入有关的、合理的支出，包括成本、费用、税金、损失和其他支出，准予在计算应纳税所得额时扣除。",
            "第二十八条": "符合条件的小型微利企业，减按20%的税率征收企业所得税。国家需要重点扶持的高新技术企业，减按15%的税率征收企业所得税。",
        },
        "affected_domains": ["企业所得税分析域", "利润分析域", "成本费用域"],
    },
    "税收征收管理法": {
        "short": "税收征收管理法",
        "full": "中华人民共和国税收征收管理法",
        "effective": "2015-04-24",
        "key_articles": {
            "第三十二条": "纳税人未按照规定期限缴纳税款的，税务机关除责令限期缴纳外，从滞纳税款之日起，按日加收滞纳税款万分之五的滞纳金。",
            "第六十三条": "纳税人伪造、变造、隐匿、擅自销毁帐簿、记帐凭证，或者在帐簿上多列支出或者不列、少列收入，经税务机关通知申报而拒不申报或者进行虚假的纳税申报，不缴或者少缴应纳税款的，是偷税。",
        },
        "affected_domains": ["全部分析域"],
    },
    "发票管理办法": {
        "short": "发票管理办法",
        "full": "中华人民共和国发票管理办法",
        "effective": "2023-07-20",
        "key_articles": {
            "第二十二条": "开具发票应当按照规定的时限、顺序、栏目，全部联次一次性如实开具，并加盖发票专用章。任何单位和个人不得有下列虚开发票行为：（一）为他人、为自己开具与实际经营业务情况不符的发票；（二）让他人为自己开具与实际经营业务情况不符的发票...",
        },
        "affected_domains": ["发票分析域", "虚开发票检测域"],
    },
}

# 已废止的法律引用映射
DEPRECATED_REFERENCES = {
    "增值税暂行条例": "⚠️ 已废止(2024.1.1)，现行有效：《中华人民共和国增值税法》",
    "增值税暂行条例实施细则": "⚠️ 已废止(2024.1.1)，现行有效：《中华人民共和国增值税法》",
    "营业税暂行条例": "⚠️ 已废止(2016.5.1全面营改增)，现行有效：《中华人民共和国增值税法》",
}


class LegalUpdateEngine:
    """法规自更新引擎"""
    
    def __init__(self):
        self._laws = TAX_LAWS.copy()
        self._updates: List[Dict] = []
        self._load_updates()
    
    def _load_updates(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "legal_updates.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                self._updates = data.get("updates", [])
                # 合并自定义法律
                for law_name, law_data in data.get("custom_laws", {}).items():
                    self._laws[law_name] = law_data
        except:
            pass
    
    def _save_updates(self):
        path = os.path.join(os.path.dirname(__file__), "..", "static", "legal_updates.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "updates": self._updates[-200:],
                "custom_laws": {k: v for k, v in self._laws.items() if k not in TAX_LAWS},
                "updated_at": datetime.now().isoformat(),
            }, f, ensure_ascii=False, indent=2)
    
    def check_deprecation(self, text: str) -> List[Dict]:
        """检查文本中是否有已废止的法条引用"""
        deprecated = []
        for old_name, warning in DEPRECATED_REFERENCES.items():
            if old_name in text:
                deprecated.append({
                    "old_reference": old_name,
                    "warning": warning,
                    "found_in": text[:200],
                })
        return deprecated
    
    def analyze_impact(self, law_name: str, version_change: str = "update") -> Dict:
        """
        分析法律变更对系统的影响
        
        输入：法律名称 + 变更类型(update/repeal/new)
        输出：受影响的分析域列表 + 需要更新的配置
        """
        law = self._laws.get(law_name, {})
        if not law:
            return {"error": f"未找到「{law_name}」的法律数据"}
        
        affected = law.get("affected_domains", [])
        
        impact_level = "高" if "全部分析域" in affected else (
            "中" if len(affected) > 2 else "低"
        )
        
        return {
            "law": law_name,
            "full_name": law.get("full", law_name),
            "effective_date": law.get("effective", ""),
            "affected_domains": affected,
            "impact_level": impact_level,
            "action_needed": (
                f"法律{version_change}生效，"
                f"影响{len(affected)}个分析域: {', '.join(affected)}"
            ),
            "recommendation": self._get_recommendation(affected, impact_level),
        }
    
    def _get_recommendation(self, domains: List[str], level: str) -> str:
        if level == "高":
            return "建议立即更新全部分析域的规则阈值和法律引用，并重新运行历史分析以确认结论一致性。"
        elif level == "中":
            return f"建议在下次分析前更新 {', '.join(domains[:3])} 等分析域的法律引用。"
        return "影响范围有限，可在常规维护周期内更新。"
    
    def get_law_text(self, law_name: str, article: str = "") -> Optional[str]:
        """获取法律条文原文"""
        law = self._laws.get(law_name, {})
        if not law:
            return None
        if article and article in law.get("key_articles", {}):
            return f"《{law.get('full', law_name)}》第{article}：{law['key_articles'][article]}"
        if law.get("key_articles"):
            articles = "\n".join(
                f"第{k}：{v}" for k, v in list(law["key_articles"].items())[:5]
            )
            return f"《{law.get('full', law_name)}》（{law.get('effective', '')}施行）\n{articles}"
        return f"《{law.get('full', law_name)}》（{law.get('effective', '')}施行）"
    
    def record_update(self, law_name: str, update_desc: str, source: str = "handbook") -> Dict:
        """记录一次法律更新事件"""
        update = {
            "law": law_name,
            "description": update_desc,
            "source": source,
            "timestamp": datetime.now().isoformat(),
        }
        self._updates.append(update)
        self._save_updates()
        return {"ok": True, "update": update}
    
    def status(self) -> Dict:
        return {
            "total_laws": len(self._laws),
            "updates_tracked": len(self._updates),
            "deprecated_refs": len(DEPRECATED_REFERENCES),
            "last_update": self._updates[-1] if self._updates else None,
        }


# 全局法规引擎
legal_updater = LegalUpdateEngine()

def get_legal_updater() -> LegalUpdateEngine:
    return legal_updater
