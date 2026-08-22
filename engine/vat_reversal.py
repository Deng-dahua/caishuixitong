"""进项税额转出判定引擎（可复用）。

把 domain_analysis 的"上下文豁免二次思考"机制抽离为独立模块，
供两个入口共用：
  1. domain_analysis.py 的扣税凭证分类（逐张发票判定可抵扣性）
  2. verified_rule_engine.py 的 VR032 规则（全量进项发票转出线索筛查）

设计原则（老邓 2026-06-30 亲授）：
  同一个品名关键词（如"酒"），在不同企业类型、不同用途下抵扣结果完全不同：
    餐饮买料酒→调料→可抵扣；酒厂买原酒→原料→可抵扣；
    化工买酒精→燃料→可抵扣；贸易买茅台→招待→不可抵扣。
  系统必须做"企业画像 + 品名 + 用途"三要素综合判定，而非单一关键词匹配。

判定两阶段：
  初审：关键词命中 → 标记不得抵扣嫌疑（宁可错杀不可放过）
  二审（终审）：结合企业画像与会计科目做上下文豁免检查，排除误判
"""
from __future__ import annotations

from engine.memory import (
    VAT_INPUT_TAX_REVERSAL_RULES,
    VAT_CONTEXTUAL_REVERSAL_OVERRIDES,
)

# 企业画像信号来源优先级：发票/凭证文本 > 注入的 enterprise_profile
# 这里只做文本宽松匹配，命中任一条件即豁免。


def classify_input_tax_reversal(invoice_dict, enterprise_profile=""):
    """判定单张进项发票是否应做进项税额转出。

    Args:
        invoice_dict: 单张进项发票字典（含品名、摘要、科目等文本字段）。
        enterprise_profile: 可选的企业画像文本（行业/经营范围），与发票文本合并判定。

    Returns:
        dict: {
            "needs_reversal": bool,
            "suspicion": str,        # 命中的不得抵扣用途
            "keyword": str,         # 触发关键词
            "exempted": bool,        # 二审是否豁免
            "rationale": str,        # 判定说明
        }
    """
    all_text = " ".join(str(v) for v in invoice_dict.values())
    if enterprise_profile:
        all_text = f"{all_text} {enterprise_profile}"
    all_text_lower = all_text.lower()

    if not VAT_INPUT_TAX_REVERSAL_RULES:
        return {"needs_reversal": False, "suspicion": "", "keyword": "",
                "exempted": False, "rationale": "无转出规则"}

    for rule in VAT_INPUT_TAX_REVERSAL_RULES.get("non_deductible_uses", []):
        for kw in rule.get("keywords", []):
            if kw in all_text or kw in all_text_lower:
                suspicion_item = rule["item"]
                # 二审：上下文豁免检查
                exempted = _check_reversal_exemption(all_text, kw)
                if exempted:
                    return {
                        "needs_reversal": False,
                        "suspicion": suspicion_item,
                        "keyword": kw,
                        "exempted": True,
                        "rationale": f"关键词「{kw}」触发{suspicion_item}嫌疑，但上下文豁免通过→维持可抵扣",
                    }
                return {
                    "needs_reversal": True,
                    "suspicion": suspicion_item,
                    "keyword": kw,
                    "exempted": False,
                    "rationale": f"用途为「{suspicion_item}」({kw})→即使取得扣税凭证也须进项税额转出",
                }
    return {"needs_reversal": False, "suspicion": "", "keyword": "",
            "exempted": False, "rationale": "无不得抵扣用途命中"}


def _check_reversal_exemption(all_text, keyword):
    """进项税额转出的上下文豁免检查（系统的'二次思考'机制）。

    同一个关键词在不同语境下税务处理完全不同。判定策略：企业画像 + 品名 +
    会计科目，宽松匹配（命中任一条件即生效）。理由：实际发票数据通常不会
    同时包含企业类型和会计科目，引擎应根据已有信号做最佳判断，而非因数据
    不完整而错判。

    Returns:
        bool: True 表示豁免（维持可抵扣），False 表示不豁免（维持转出判定）。
    """
    if not VAT_CONTEXTUAL_REVERSAL_OVERRIDES:
        return False  # 无豁免规则，维持原判定

    for override in VAT_CONTEXTUAL_REVERSAL_OVERRIDES.get("overrides", []):
        if override.get("keyword") != keyword:
            continue

        for condition in override.get("exempt_when", []):
            # 标记 override_allowed=False 表示硬性规定，不豁免（如贷款服务）
            if condition.get("override_allowed") is False:
                continue

            type_hit = False
            acct_hit = False

            enterprise_types = condition.get("enterprise_types", [])
            if enterprise_types:
                if "*" in enterprise_types:
                    type_hit = True
                else:
                    for et in enterprise_types:
                        if et in all_text:
                            type_hit = True
                            break

            account_keywords = condition.get("account_keywords", [])
            if account_keywords:
                for ak in account_keywords:
                    if ak in all_text:
                        acct_hit = True
                        break

            # 宽松匹配：企业类型 或 会计科目 至少命中一个即豁免
            if type_hit or acct_hit:
                return True  # 豁免！

    return False  # 不豁免，维持转出判定
