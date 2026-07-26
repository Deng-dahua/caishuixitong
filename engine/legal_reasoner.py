# ═══════════════════════════════════════════════════════════════
# 法律逻辑推理引擎 (Legal Reasoning Engine)
#
# 设计理念：
#   从"统计相关性"进化为"法律三段论"——
#   大前提：法律条文的规定（X行为 → Y法律后果）
#   小前提：本案事实符合该条文的条件
#   结论：该条文的法律后果适用于本案
#
#   P(虚开|信号)=0.7  →  "根据《中华人民共和国增值税法》第1720条，
#                        发票不合规 → 进项不得抵扣 → 应转出"
#
#  每条法律规则编码为可审计的触发条件+法律后果，
#  结论可直接引用条文，不再使用"可能""疑似"等模糊词。
# ═══════════════════════════════════════════════════════════════

import json
import os
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field


@dataclass
class LegalRule:
    """单条法律规则——大前提"""
    article: str                      # 法律条文引用
    full_text: str                    # 条文原文
    conditions: Dict[str, Any]        # 触发条件（结构化）
    consequence: str                  # 法律后果
    severity: str                     # high/medium/low
    action: str                       # 处理建议
    domain: str = "general"           # 所属领域
    priority: int = 5                 # 检查优先级 1-10


# ═══════════════════════════════════════════════════════════════
# 税法条文库 — 当前支持的主要法律依据
# ═══════════════════════════════════════════════════════════════

_LEGAL_RULES_DB: List[LegalRule] = [
    # ── 增值税 ──
    LegalRule(
        article="《中华人民共和国增值税法》第九条",
        full_text="纳税人购进货物或者应税劳务，取得的增值税扣税凭证不符合法律、"
                  "行政法规或者国务院税务主管部门有关规定的，其进项税额不得从销项税额中抵扣。",
        conditions={
            "finding_types": ["发票不合规", "虚开发票", "进项发票疑点", "供应商异常"],
            "field_checks": {
                "supplier_verified": False,
                "invoice_compliant": False,
                "funds_matched": False,
            }
        },
        consequence="进项税额不得抵扣，应做进项税额转出处理",
        severity="high",
        action="调取涉税发票原件及合同、付款凭证；核实供应商真实性；"
               "如确认不合规，应追缴已抵扣税款并加收滞纳金",
        domain="增值税",
        priority=1
    ),
    LegalRule(
        article="《中华人民共和国增值税法》第一条、第十九条",
        full_text="在中华人民共和国境内销售货物或者加工、修理修配劳务，"
                  "销售服务、无形资产、不动产以及进口货物的单位和个人，为增值税的纳税人。"
                  "发生应税销售行为，增值税纳税义务发生时间为收讫销售款项或者取得索取销售款项凭据的当天。",
        conditions={
            "finding_types": ["隐匿收入", "未开票收入", "账外经营", "个人收款"],
            "field_checks": {
                "revenue_hidden": True,
                "invoice_not_issued": True,
                "payment_received": True,
            }
        },
        consequence="未申报的销售收入应补缴增值税，从滞纳税款之日起按日加收万分之五滞纳金",
        severity="high",
        action="逐笔核实未开票收款的性质；要求企业补充申报未开票收入；"
               "补缴增值税及滞纳金",
        domain="增值税",
        priority=1
    ),
    LegalRule(
        article="《中华人民共和国发票管理办法》第二十二条",
        full_text="开具发票应当按照规定的时限、顺序、栏目，全部联次一次性如实开具，"
                  "并加盖发票专用章。任何单位和个人不得有下列虚开发票行为：（一）为他人、"
                  "为自己开具与实际经营业务情况不符的发票；（二）让他人为自己开具与实际"
                  "经营业务情况不符的发票；（三）介绍他人开具与实际经营业务情况不符的发票。",
        conditions={
            "finding_types": ["虚开发票", "进销品名不匹配", "购销闭环", "对开环开"],
            "field_checks": {
                "goods_mismatch": True,
                "supplier_customer_overlap": True,
                "no_real_transaction": True,
            }
        },
        consequence="构成虚开发票行为，税务机关没收违法所得；虚开金额在1万元以下的"
                   "可并处5万元以下罚款，虚开金额超过1万元的可并处5万元以上50万元以下罚款；"
                   "构成犯罪的依法追究刑事责任",
        severity="high",
        action="逐笔核实交易真实性；调取合同/物流/出入库单/资金凭证；"
               "涉税金额重大的移送税务合规局或公安经侦",
        domain="发票管理",
        priority=1
    ),
    LegalRule(
        article="《中华人民共和国增值税法》第七条",
        full_text="纳税人发生应税销售行为的价格明显偏低并无正当理由的，"
                  "由主管税务机关核定其销售额。",
        conditions={
            "finding_types": ["毛利率异常", "关联交易", "转让定价"],
            "field_checks": {
                "price_too_low": True,
                "related_party": True,
                "no_commercial_reason": True,
            }
        },
        consequence="税务机关有权按照组成计税价格核定销售额，补征增值税差额",
        severity="medium",
        action="核实关联交易定价是否公允；获取可比非受控价格；"
               "如定价明显偏低且无正当理由，依规定核定调整",
        domain="增值税",
        priority=2
    ),

    # ── 企业所得税 ──
    LegalRule(
        article="《中华人民共和国企业所得税法》第八条",
        full_text="企业实际发生的与取得收入有关的、合理的支出，包括成本、费用、税金、损失和其他支出，准予在计算应纳税所得额时扣除。",
        conditions={
            "finding_types": ["虚列成本", "虚假费用", "无票支出", "凭证缺失"],
            "field_checks": {
                "expense_unsupported": True,
                "no_valid_voucher": True,
                "not_business_related": True,
            }
        },
        consequence="不符合真实性、相关性、合理性要求的支出不得税前扣除，"
                   "应调增应纳税所得额",
        severity="medium",
        action="逐项核实支出的真实性、相关性和合理性；"
               "无法提供有效凭证的支出调增应纳税所得额；补缴企业所得税",
        domain="企业所得税",
        priority=2
    ),
    LegalRule(
        article="《中华人民共和国企业所得税法》第四十一条",
        full_text="企业与其关联方之间的业务往来，不符合独立交易原则而减少企业"
                  "或者其关联方应纳税收入或者所得额的，税务机关有权按照合理方法调整。",
        conditions={
            "finding_types": ["关联交易", "转让定价", "利润转移"],
            "field_checks": {
                "related_party_transaction": True,
                "not_arms_length": True,
                "tax_reduced": True,
            }
        },
        consequence="税务机关有权按照独立交易原则进行特别纳税调整，"
                   "补征企业所得税及利息",
        severity="high",
        action="进行转让定价可比性分析；获取关联交易合同及定价依据；"
               "按照独立交易原则调整并补税",
        domain="企业所得税",
        priority=1
    ),

    # ── 税收征收管理法 ──
    LegalRule(
        article="《中华人民共和国税收征收管理法》第三十五条",
        full_text="纳税人有下列情形之一的，税务机关有权核定其应纳税额：（一）依照法律、"
                  "行政法规的规定可以不设置账簿的；（二）依照法律、行政法规的规定应当设置"
                  "账簿但未设置的；（三）擅自销毁账簿或者拒不提供纳税资料的；"
                  "（四）虽设置账簿，但账目混乱或者成本资料、收入凭证、费用凭证残缺不全，"
                  "难以查账的；（五）发生纳税义务，未按照规定的期限办理纳税申报，经税务"
                  "机关责令限期申报，逾期仍不申报的；（六）纳税人申报的计税依据明显偏低，"
                  "又无正当理由的。",
        conditions={
            "finding_types": ["凭证缺失", "资料缺失", "账簿不全", "数据不足", "会计账簿不健全"],
            "field_checks": {
                "missing_vouchers": True,
                "missing_invoices": True,
                "missing_bank_statements": True,
                "data_quality_low": True,
            }
        },
        consequence="税务机关有权核定应纳税额；核定方法包括参照同类行业或类似行业中"
                   "经营规模和收入水平相近的纳税人的税负水平核定、按照营业收入或成本"
                   "加合理的费用和利润的方法核定等",
        severity="high",
        action="评估账簿凭证的完整性；如确实不健全，按行业标准或成本利润率核定应纳税额",
        domain="税收征管",
        priority=1
    ),
    LegalRule(
        article="《中华人民共和国税收征收管理法》第六十三条",
        full_text="纳税人伪造、变造、隐匿、擅自销毁账簿、记账凭证，或者在账簿上多列支出"
                  "或者不列、少列收入，或者经税务机关通知申报而拒不申报或者进行虚假的"
                  "纳税申报，不缴或者少缴应纳税款的，是偷税。对纳税人偷税的，由税务机关"
                  "追缴其不缴或者少缴的税款、滞纳金，并处不缴或者少缴的税款百分之五十"
                  "以上五倍以下的罚款；构成犯罪的，依法追究刑事责任。",
        conditions={
            "finding_types": ["偷税", "隐匿收入", "虚列支出", "虚假申报"],
            "field_checks": {
                "income_hidden": True,
                "expense_inflated": True,
                "tax_underpaid": True,
            }
        },
        consequence="追缴不缴或少缴的税款及滞纳金，并处50%以上5倍以下罚款；"
                   "构成犯罪的依法追究刑事责任",
        severity="high",
        action="固定证据链（资金流/发票流/货物流）；计算少缴税款金额；"
               "移送税务合规局依法处理；涉刑案件移送公安经侦",
        domain="税收征管",
        priority=1
    ),
    LegalRule(
        article="《中华人民共和国税收征收管理法》第三十二条",
        full_text="纳税人未按照规定期限缴纳税款的，扣缴义务人未按照规定期限解缴税款的，"
                  "税务机关除责令限期缴纳外，从滞纳税款之日起，按日加收滞纳税款万分之五"
                  "的滞纳金。",
        conditions={
            "finding_types": ["少缴税款", "延迟申报", "未申报"],
            "field_checks": {
                "tax_underpaid": True,
                "delay_days": 0,
            }
        },
        consequence="从滞纳税款之日起按日加收万分之五的滞纳金",
        severity="medium",
        action="计算滞纳天数及滞纳金金额；责令限期缴纳",
        domain="税收征管",
        priority=3
    ),

    # ── 个人所得税 ──
    LegalRule(
        article="《中华人民共和国个人所得税法》第九条",
        full_text="个人所得税以所得人为纳税人，以支付所得的单位或者个人为扣缴义务人。",
        conditions={
            "finding_types": ["工资未申报", "个税未扣缴", "无工资记录"],
            "field_checks": {
                "salary_paid": True,
                "tax_not_withheld": True,
                "no_payroll_record": True,
            }
        },
        consequence="扣缴义务人应补扣补缴个人所得税；未履行扣缴义务的，"
                   "对扣缴义务人处应扣未扣税款50%以上3倍以下罚款",
        severity="medium",
        action="核实工资发放记录；补扣补缴个人所得税；对扣缴义务人依法处罚",
        domain="个人所得税",
        priority=2
    ),

    # ── 刑法（涉税犯罪） ──
    LegalRule(
        article="《中华人民共和国刑法》第二百零五条",
        full_text="虚开增值税专用发票或者虚开用于骗取出口退税、抵扣税款的其他发票的，"
                  "处三年以下有期徒刑或者拘役，并处二万元以上二十万元以下罚金；虚开的"
                  "税款数额较大或者有其他严重情节的，处三年以上十年以下有期徒刑，并处"
                  "五万元以上五十万元以下罚金；虚开的税款数额巨大或者有其他特别严重情节"
                  "的，处十年以上有期徒刑或者无期徒刑，并处五万元以上五十万元以下罚金"
                  "或者没收财产。",
        conditions={
            "finding_types": ["虚开发票", "虚开增值税专用发票"],
            "field_checks": {
                "fake_invoice_confirmed": True,
                "vat_involved": True,
                "amount_significant": True,
            }
        },
        consequence="构成虚开增值税专用发票罪——三年以下至无期徒刑，并处罚金或没收财产",
        severity="high",
        action="固定虚开证据链（发票/资金/合同/物流）；计算虚开税额；"
               "移送公安经侦立案侦查",
        domain="刑法",
        priority=1
    ),
    LegalRule(
        article="《中华人民共和国刑法》第二百零一条",
        full_text="纳税人采取欺骗、隐瞒手段进行虚假纳税申报或者不申报，逃避缴纳税款"
                  "数额较大并且占应纳税额百分之十以上的，处三年以下有期徒刑或者拘役，"
                  "并处罚金；数额巨大并且占应纳税额百分之三十以上的，处三年以上七年以下"
                  "有期徒刑，并处罚金。",
        conditions={
            "finding_types": ["偷税", "逃税", "虚假申报"],
            "field_checks": {
                "tax_evasion_confirmed": True,
                "amount_large": True,
                "ratio_high": True,
            }
        },
        consequence="构成逃税罪——三年以下至七年有期徒刑，并处罚金。"
                   "五年内因逃避缴纳税款受过刑事处罚或被税务机关给予二次以上行政处罚的除外",
        severity="high",
        action="计算逃税金额及占应纳税额比例；固定电子及纸质证据；"
               "移送公安经侦",
        domain="刑法",
        priority=1
    ),
]


# ═══════════════════════════════════════════════════════════════
# 匹配逻辑
# ═══════════════════════════════════════════════════════════════

class LegalReasoner:
    """
    法律三段论推理器
    
    用法：
        reasoner = LegalReasoner()
        results = reasoner.reason(findings, company_context)
        # results = [{finding, matched_rules, conclusion, legal_basis}, ...]
    """
    
    def __init__(self, rules: List[LegalRule] = None):
        self.rules = rules or _LEGAL_RULES_DB
        self._type_index = self._build_type_index()
    
    def _build_type_index(self) -> Dict[str, List[LegalRule]]:
        """构建 finding_type → rules 索引"""
        index = {}
        for rule in self.rules:
            for ft in rule.conditions.get("finding_types", []):
                ft_key = ft.lower().replace(" ", "")
                if ft_key not in index:
                    index[ft_key] = []
                index[ft_key].append(rule)
        return index
    
    def _match_finding_type(self, finding: Dict) -> List[str]:
        """从 finding 中提取可能的匹配类型"""
        types = []
        finding_type = (finding.get("type") or "").lower().replace(" ", "")
        title = (finding.get("title") or finding.get("name") or "").lower().replace(" ", "")
        desc = (finding.get("description") or finding.get("detail") or "").lower().replace(" ", "")
        
        combined = f"{finding_type} {title} {desc}"
        
        # 关键词匹配
        keywords_map = {
            "隐匿收入": ["隐匿", "未开票", "账外", "体外循环", "个人收款"],
            "虚开发票": ["虚开", "伪造", "变造", "对开", "环开"],
            "发票不合规": ["不合规", "不规范", "品名不匹配", "进销品名"],
            "虚列支出": ["虚列", "虚构", "虚假费用", "无真实交易"],
            "关联交易": ["关联", "关联方", "转让定价", "利润转移"],
            "凭证缺失": ["缺失", "无凭证", "不全", "不健全", "缺乏"],
            "偷税": ["偷税", "逃税", "少缴", "不缴"],
            "毛利率异常": ["毛利", "毛利率", "价格偏低", "低于市场"],
            "工资未申报": ["工资", "个税", "未申报", "未扣缴"],
        }
        
        for type_name, keywords in keywords_map.items():
            if any(kw in combined for kw in keywords):
                types.append(type_name)
        
        # 直接使用 finding.type 作为匹配候选
        if finding_type and finding_type not in types:
            types.append(finding_type)
        
        return types
    
    def _check_field_conditions(self, rule: LegalRule, finding: Dict) -> Tuple[bool, str]:
        """检查 finding 是否满足规则的 field_checks"""
        checks = rule.conditions.get("field_checks", {})
        if not checks:
            return True, "无条件匹配"
        
        matched = []
        unmatched = []
        
        for field, expected in checks.items():
            actual = finding.get(field)
            if isinstance(expected, bool):
                # 布尔条件：finding 中该字段为真值即匹配
                if bool(actual) == expected:
                    matched.append(field)
                else:
                    unmatched.append(f"{field}={actual}(期望{expected})")
            elif isinstance(expected, (int, float)):
                # 数值条件
                if (actual or 0) >= expected:
                    matched.append(f"{field}>={expected}")
                else:
                    unmatched.append(f"{field}={actual}(期望>={expected})")
        
        # 至少匹配一项即认为条件成立（宽松模式）
        # 严格模式：全部匹配
        strict = len(unmatched) == 0
        return strict, f"匹配:{matched}, 未匹配:{unmatched}" if unmatched else f"全部匹配:{matched}"
    
    def reason(self, findings: List[Dict], ctx: Dict = None) -> List[Dict]:
        """
        对每条 finding 进行法律三段论推理
        
        返回: [{finding, matched_rules, conclusion, legal_basis}]
        """
        results = []
        
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            
            matched_rules = []
            types = self._match_finding_type(finding)
            
            for ft in types:
                candidates = self._type_index.get(ft, [])
                for rule in candidates:
                    if rule in matched_rules:
                        continue
                    matched, detail = self._check_field_conditions(rule, finding)
                    if matched:
                        matched_rules.append({
                            "rule": rule,
                            "match_detail": detail
                        })
            
            if matched_rules:
                # 取最高优先级的规则
                best = min(matched_rules, key=lambda r: r["rule"].priority)
                rule = best["rule"]
                
                result = {
                    "finding_id": finding.get("id", finding.get("type", "")),
                    "finding_type": finding.get("type", ""),
                    "finding_title": finding.get("title", finding.get("name", "")),
                    "matched_rules_count": len(matched_rules),
                    "primary_article": rule.article,
                    "primary_full_text": rule.full_text,
                    "primary_consequence": rule.consequence,
                    "primary_action": rule.action,
                    "primary_severity": rule.severity,
                    "reasoning_chain": {
                        "major_premise": f"{rule.article}规定：「{rule.full_text[:80]}...」",
                        "minor_premise": f"经查，该企业存在{finding.get('title', finding.get('type', ''))}行为",
                        "conclusion": rule.consequence,
                    },
                    "all_matched_rules": [
                        {
                            "article": r["rule"].article,
                            "consequence": r["rule"].consequence,
                            "match": r["match_detail"]
                        }
                        for r in matched_rules[:5]  # 最多1720条
                    ],
                    "legal_basis": [
                        {"article": r["rule"].article, "domain": r["rule"].domain}
                        for r in matched_rules[:5]
                    ]
                }
                results.append(result)
        
        return results
    
    def get_rules_by_domain(self, domain: str) -> List[LegalRule]:
        """按领域获取法律规则"""
        return [r for r in self.rules if r.domain == domain]
    
    def get_all_domains(self) -> List[str]:
        """获取所有覆盖的法律领域"""
        return sorted(set(r.domain for r in self.rules))


# ═══════════════════════════════════════════════════════════════
# AGI 集成接口
# ═══════════════════════════════════════════════════════════════

def run_legal_reasoning(findings: List[Dict], ctx: Dict = None) -> Dict:
    """
    一键调用：对全部发现执行法律推理
    
    返回: {
        "total_findings": N,
        "matched_findings": N,
        "results": [...],
        "summary": "本次分析引用X部法律Y条条文..."
    }
    """
    reasoner = LegalReasoner()
    results = reasoner.reason(findings, ctx)
    
    if not results:
        return {
            "total_findings": len(findings),
            "matched_findings": 0,
            "results": [],
            "summary": "本次分析未匹配到具体法律条文"
        }
    
    # 统计引用的法律
    articles = set()
    domains = set()
    for r in results:
        for lb in r.get("legal_basis", []):
            articles.add(lb["article"][:30])
            domains.add(lb["domain"])
    
    return {
        "total_findings": len(findings),
        "matched_findings": len(results),
        "results": results,
        "summary": f"本次分析引用{len(domains)}部法律共{len(articles)}条条文，"
                   f"覆盖{len(results)}项发现的法律依据",
        "domains": list(domains),
        "articles": list(articles)[:20],
    }
