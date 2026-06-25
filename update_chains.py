#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Update tax_risk_rules_local_export.json and audit_chains.json
"""
import json
import os
import copy

BASE = r"C:\Users\26726\WorkBuddy\2026-05-31-09-56-37\caishuixitong\static"

# ========== PART 1: Update tax_risk_rules_local_export.json ==========

rules_path = os.path.join(BASE, "tax_risk_rules_local_export.json")
with open(rules_path, "r", encoding="utf-8") as f:
    rules = json.load(f)

# Update rule 1500
for rule in rules:
    if rule.get("id") == 1500:
        rule["detail"] = (
            "企业位于XX市，纺织原料和成品均为重物。进项供应商分布在XX等外地城市，"
            "但发票和银行流水中无任何运输/物流/快递费用。重物跨省运输必有运费"
            "（通常占货值3%-8%），无运费则货物流物证链断裂——"
            "发票流和资金流存在但第三流（货物流）无法验证。"
        )
        rule["how_found"] = (
            "提取全部供应商和客户公司名称→按城市关键词解析地址→"
            "检索运输/物流/快递类关键词→发现外地供应商≥3家+运输费=0→"
            "结合行业重物属性判定货物流存疑"
        )
        rule["dataSource"] = "进项发票+销项发票+银行流水+行业基准库"
        # 确保字段顺序: 在evidence之后, policy_ref之前插入dataSource/how_found
        print(f"Updated rule 1500: {rule['item']}")

# Update rule 1501
for rule in rules:
    if rule.get("id") == 1501:
        rule["detail"] = (
            "企业位于XX市，但加工费发票来自XX等外地供应商。XX市是产业集群地，"
            "当地应有大量加工资源。外地加工增加运输成本，在商业上不合理。"
            "同时对比：加工商城市≠供应商城市≠客户城市→三组地址互不重叠。"
        )
        rule["how_found"] = (
            "筛选含'加工'关键词发票→提取供应商名称→解析城市地址→"
            "与原材料供应商和销项客户地址交叉对比→结合本地产业集群判断→发现点→面异常"
        )
        print(f"Updated rule 1501: {rule['item']}")

# Add rule 1504 (after the last rule, before the closing ])
new_rule_1504 = {
    "id": 1504,
    "category": "经营实质",
    "categoryIcon": "🏭",
    "item": "全链条经营实质地理异常",
    "detail": (
        "点→面推理：从单点异常（加工费来自外地/供应商在外地）扩展为全链条分析。"
        "供应商、加工商、客户三组地址完全互不重叠+零运输成本=全链条经营在物理上无法成立。"
    ),
    "score": 9,
    "level": "高风险",
    "suggestion": (
        "路径A：提供全链条物流单据（原料运输+加工往返+成品发货）证明货物流真实性。"
        "路径B：提供合同运费条款证明。"
        "路径C：无法提供→全部跨省交易视为不真实→进项税额转出+成本不得扣除。"
    ),
    "urgency": "紧急",
    "evidence": "三组地址交叉对比+运输成本检测+产业集聚度分析",
    "dataSource": "进项发票+销项发票+银行流水",
    "remark": "点→面推理核心：从单点扩展到面（全链条经营实质存疑）",
    "detectable": True,
    "how_found": (
        "提取供应商/客户/加工商三组地址→城市交叉对比→发现互不重叠→"
        "结合零运输成本→物理推理得出全链条不可行结论"
    ),
    "tax_impact": (
        "全链条经营实质存疑→税务机关可否定全部跨省交易真实性→"
        "所得税成本全部不得扣除+增值税进项全部转出"
    ),
    "policy_ref": "《企业所得税法》第八条；《税收征收管理法》第三十五条；三流一致要求"
}
rules.append(new_rule_1504)
print(f"Added rule 1504: {new_rule_1504['item']}")

# Sort rules by id to maintain order
# rules.sort(key=lambda x: x.get("id", 0))

# Write back with no trailing commas (json.dump handles this correctly)
with open(rules_path, "w", encoding="utf-8") as f:
    json.dump(rules, f, ensure_ascii=False, indent=2)

print(f"Rules file updated. Total rules: {len(rules)}")

# ========== PART 2: Update audit_chains.json ==========

chains_path = os.path.join(BASE, "audit_chains.json")
with open(chains_path, "r", encoding="utf-8") as f:
    data = json.load(f)

chains = data["chains"]

# Define 3 new trail chains following existing format
new_trail_chains = [
    {
        "name": "经营实质-地理分布-重物跨省运输",
        "chain_type": "线索链",
        "steps": 4,
        "high_risk_steps": 2,
        "policies": [
            "《企业所得税法》第八条",
            "三流一致要求"
        ],
        "tax_impacts": [
            "货物流物证链断裂",
            "企业所得税成本扣除资格可能被否定"
        ],
        "investigation_path": [
            {
                "step": "提取企业工商注册地址和发票中确认的企业所在城市",
                "rule_id": 1500,
                "rule_item": "重物跨省经营缺运输成本",
                "level": "高风险",
                "score": 8,
                "detail": "统计全部进项供应商和销项客户的城市分布，区分本地vs外地",
                "policy_ref": "《企业所得税法》第八条",
                "tax_impact": "货物流物证链断裂",
                "suggestion": "提供运输/物流单据验证货物真实性"
            },
            {
                "step": "统计全部进项供应商和销项客户的城市分布",
                "rule_id": 1500,
                "rule_item": "重物跨省经营缺运输成本",
                "level": "高风险",
                "score": 8,
                "detail": "提取供应商名称→按城市关键词解析地址→区分本地vs外地→筛选外地供应商",
                "policy_ref": "《企业所得税法》第八条",
                "tax_impact": "货物流物证链断裂",
                "suggestion": "提供运输/物流单据验证货物真实性"
            },
            {
                "step": "检索运输/物流/快递/货运关键词",
                "rule_id": 1500,
                "rule_item": "重物跨省经营缺运输成本",
                "level": "高风险",
                "score": 8,
                "detail": "检索全部发票品名和银行流水中运输/物流/快递/货运关键词，确认运输费用为零",
                "policy_ref": "三流一致要求",
                "tax_impact": "交易真实性存疑",
                "suggestion": "核实运输费用承担方"
            },
            {
                "step": "判断行业重物属性",
                "rule_id": 1500,
                "rule_item": "重物跨省经营缺运输成本",
                "level": "高风险",
                "score": 8,
                "detail": "判断行业属性：纺织/建材/机械/食品等重物产业跨省运输必有运费",
                "policy_ref": "《企业所得税法》第八条",
                "tax_impact": "企业所得税成本扣除资格可能被否定",
                "suggestion": "如无法提供运输证明，成本不得税前扣除"
            }
        ],
        "total_steps": 4,
        "usage_count": 0,
        "last_triggered": ""
    },
    {
        "name": "经营实质-地理分布-加工费地理存疑",
        "chain_type": "线索链",
        "steps": 4,
        "high_risk_steps": 2,
        "policies": [
            "《企业所得税法》第八条",
            "《发票管理办法》第二十二条"
        ],
        "tax_impacts": [
            "加工费真实性存疑",
            "进项税额可能被要求转出"
        ],
        "investigation_path": [
            {
                "step": "筛选加工费发票并提取供应商地址",
                "rule_id": 1501,
                "rule_item": "外地加工费存疑",
                "level": "高风险",
                "score": 8,
                "detail": "筛选进项发票中含'加工'关键词的发票，提取供应商名称和地址",
                "policy_ref": "《企业所得税法》第八条",
                "tax_impact": "加工费真实性存疑",
                "suggestion": "提供加工合同和物流单据"
            },
            {
                "step": "分析产业集群特征",
                "rule_id": 1501,
                "rule_item": "外地加工费存疑",
                "level": "高风险",
                "score": 8,
                "detail": "分析企业所在城市的产业集群特征：是否有同类加工资源",
                "policy_ref": "《企业所得税法》第八条",
                "tax_impact": "加工费真实性存疑",
                "suggestion": "说明选择外地加工商的商业合理性"
            },
            {
                "step": "三组地址交叉对比",
                "rule_id": 1501,
                "rule_item": "外地加工费存疑",
                "level": "高风险",
                "score": 8,
                "detail": "同时提取原材料供应商地址和销项客户地址，三组对比",
                "policy_ref": "《发票管理办法》第二十二条",
                "tax_impact": "进项税额可能被要求转出",
                "suggestion": "提供全链条地址合理性说明"
            },
            {
                "step": "综合判定风险",
                "rule_id": 1501,
                "rule_item": "外地加工费存疑",
                "level": "高风险",
                "score": 8,
                "detail": "判断：加工商不在本地+本地有集群+三组地址互不重叠→高风险",
                "policy_ref": "《企业所得税法》第八条",
                "tax_impact": "加工费进项税额转出+成本不得扣除",
                "suggestion": "路径A：提供加工物流单据；路径B：证明商业合理性"
            }
        ],
        "total_steps": 4,
        "usage_count": 0,
        "last_triggered": ""
    },
    {
        "name": "经营实质-地理分布-全链条点面推理",
        "chain_type": "线索链",
        "steps": 5,
        "high_risk_steps": 3,
        "policies": [
            "《企业所得税法》第八条",
            "《税收征收管理法》第三十五条",
            "三流一致要求"
        ],
        "tax_impacts": [
            "全链条经营实质存疑",
            "全部跨省交易真实性可被否定",
            "所得税成本全部不得扣除",
            "增值税进项全部转出"
        ],
        "investigation_path": [
            {
                "step": "从单点异常出发",
                "rule_id": 1504,
                "rule_item": "全链条经营实质地理异常",
                "level": "高风险",
                "score": 9,
                "detail": "从单点异常出发：加工费来自外地或供应商分布异常",
                "policy_ref": "《企业所得税法》第八条",
                "tax_impact": "全链条经营实质存疑",
                "suggestion": "梳理全链条经营地址分布"
            },
            {
                "step": "扩展维度提取三组地址",
                "rule_id": 1504,
                "rule_item": "全链条经营实质地理异常",
                "level": "高风险",
                "score": 9,
                "detail": "扩展维度：提取原材料供应商、加工费供应商、销项客户三组地址城市分布",
                "policy_ref": "《企业所得税法》第八条",
                "tax_impact": "全链条经营实质存疑",
                "suggestion": "建立三组地址映射表"
            },
            {
                "step": "交叉比对三组城市集合",
                "rule_id": 1504,
                "rule_item": "全链条经营实质地理异常",
                "level": "高风险",
                "score": 9,
                "detail": "交叉比对：三组城市集合是否互不重叠？",
                "policy_ref": "《税收征收管理法》第三十五条",
                "tax_impact": "全部跨省交易真实性可被否定",
                "suggestion": "如有重叠，分析重叠节点是否具有经营实质"
            },
            {
                "step": "验证运输成本",
                "rule_id": 1504,
                "rule_item": "全链条经营实质地理异常",
                "level": "高风险",
                "score": 9,
                "detail": "验证运输成本：检索银行流水和发票中的运输费用",
                "policy_ref": "三流一致要求",
                "tax_impact": "所得税成本全部不得扣除",
                "suggestion": "提供运输合同和运单"
            },
            {
                "step": "综合判定全链条可行性",
                "rule_id": 1504,
                "rule_item": "全链条经营实质地理异常",
                "level": "高风险",
                "score": 9,
                "detail": "综合判定：三组互不重叠+零运输→全链条物理不可能→经营实质存疑",
                "policy_ref": "《企业所得税法》第八条",
                "tax_impact": "增值税进项全部转出",
                "suggestion": "提供全链条物流单据；无法提供则全部跨省交易不真实"
            }
        ],
        "total_steps": 5,
        "usage_count": 0,
        "last_triggered": ""
    }
]

# Define 3 new evidence chains
new_evidence_chains = [
    {
        "name": "证据链-经营实质-重物运输缺失",
        "chain_type": "证据链",
        "steps": 4,
        "high_risk_steps": 3,
        "policies": [
            "《企业所得税法》第八条"
        ],
        "tax_impacts": [
            "货物流物证链断裂",
            "交易真实性存疑"
        ],
        "investigation_path": [
            {
                "step": "验证供应商城市分布",
                "rule_id": 1500,
                "rule_item": "重物跨省经营缺运输成本",
                "level": "高风险",
                "score": 8,
                "detail": "验证：进项供应商城市是否包含外地城市？外地≥3家？",
                "policy_ref": "《企业所得税法》第八条",
                "tax_impact": "货物流物证链断裂",
                "suggestion": "统计外地供应商数量和金额"
            },
            {
                "step": "验证运输费用",
                "rule_id": 1500,
                "rule_item": "重物跨省经营缺运输成本",
                "level": "高风险",
                "score": 8,
                "detail": "验证：银行流水中运输/物流/快递类支出是否为零？",
                "policy_ref": "《企业所得税法》第八条",
                "tax_impact": "交易真实性存疑",
                "suggestion": "检索银行流水运输类关键词"
            },
            {
                "step": "验证发票品名",
                "rule_id": 1500,
                "rule_item": "重物跨省经营缺运输成本",
                "level": "高风险",
                "score": 8,
                "detail": "验证：发票品名中是否存在运输/物流相关品名？",
                "policy_ref": "《企业所得税法》第八条",
                "tax_impact": "交易真实性存疑",
                "suggestion": "检索发票品名关键词"
            },
            {
                "step": "验证行业属性",
                "rule_id": 1500,
                "rule_item": "重物跨省经营缺运输成本",
                "level": "高风险",
                "score": 8,
                "detail": "验证：行业属性是否为重物产业（纺织/建材/机械等）？",
                "policy_ref": "《企业所得税法》第八条",
                "tax_impact": "货物流物证链断裂",
                "suggestion": "如为重物+无运输，可初步推断货物流断裂"
            }
        ],
        "total_steps": 4,
        "usage_count": 0,
        "last_triggered": ""
    },
    {
        "name": "证据链-经营实质-加工费地理异常",
        "chain_type": "证据链",
        "steps": 3,
        "high_risk_steps": 3,
        "policies": [
            "《企业所得税法》第八条",
            "《发票管理办法》第二十二条"
        ],
        "tax_impacts": [
            "加工真实性存疑",
            "进项税额转出风险"
        ],
        "investigation_path": [
            {
                "step": "验证加工费发票和城市",
                "rule_id": 1501,
                "rule_item": "外地加工费存疑",
                "level": "高风险",
                "score": 8,
                "detail": "验证：是否存在加工费发票？加工商城市是否≠企业所在城市？",
                "policy_ref": "《企业所得税法》第八条",
                "tax_impact": "加工真实性存疑",
                "suggestion": "统计加工费发票金额和供应商城市"
            },
            {
                "step": "验证产业集群",
                "rule_id": 1501,
                "rule_item": "外地加工费存疑",
                "level": "高风险",
                "score": 8,
                "detail": "验证：企业所在城市是否有同类加工产业集群？",
                "policy_ref": "《企业所得税法》第八条",
                "tax_impact": "加工真实性存疑",
                "suggestion": "查询当地产业集聚情况"
            },
            {
                "step": "验证三组地址互不重叠",
                "rule_id": 1501,
                "rule_item": "外地加工费存疑",
                "level": "高风险",
                "score": 8,
                "detail": "验证：加工商城市是否与供应商城市、客户城市互不重叠？",
                "policy_ref": "《发票管理办法》第二十二条",
                "tax_impact": "进项税额转出风险",
                "suggestion": "交叉对比三组城市集合"
            }
        ],
        "total_steps": 3,
        "usage_count": 0,
        "last_triggered": ""
    },
    {
        "name": "证据链-经营实质-全链条点面推理",
        "chain_type": "证据链",
        "steps": 3,
        "high_risk_steps": 3,
        "policies": [
            "《企业所得税法》第八条",
            "《税收征收管理法》第三十五条",
            "三流一致要求"
        ],
        "tax_impacts": [
            "全部跨省交易真实性可被否定",
            "所得税成本不得扣除",
            "增值税进项转出"
        ],
        "investigation_path": [
            {
                "step": "验证三组城市互不重叠",
                "rule_id": 1504,
                "rule_item": "全链条经营实质地理异常",
                "level": "高风险",
                "score": 9,
                "detail": "验证：供应商/加工商/客户三组城市集合是否完全互不重叠？",
                "policy_ref": "《企业所得税法》第八条",
                "tax_impact": "全部跨省交易真实性可被否定",
                "suggestion": "提取三组地址城市集合并交叉比对"
            },
            {
                "step": "验证运输费用为零",
                "rule_id": 1504,
                "rule_item": "全链条经营实质地理异常",
                "level": "高风险",
                "score": 9,
                "detail": "验证：运输/物流/快递费用是否完全为零？",
                "policy_ref": "《税收征收管理法》第三十五条",
                "tax_impact": "所得税成本不得扣除",
                "suggestion": "检索银行流水和发票中的运输类支出"
            },
            {
                "step": "物理不可能推理",
                "rule_id": 1504,
                "rule_item": "全链条经营实质地理异常",
                "level": "高风险",
                "score": 9,
                "detail": "推理：货物在N个城市间反复运输但无任何运输记录→物理上不可能",
                "policy_ref": "三流一致要求",
                "tax_impact": "增值税进项转出",
                "suggestion": "全链条交易视为不真实，进项转出+成本不扣除"
            }
        ],
        "total_steps": 3,
        "usage_count": 0,
        "last_triggered": ""
    }
]

# Append all 6 new chains
chains.extend(new_trail_chains)
chains.extend(new_evidence_chains)
print(f"Added {len(new_trail_chains)} trail chains + {len(new_evidence_chains)} evidence chains")

# Update metadata
data["total_chains"] = 1127  # 1121 + 6
data["trail_chains"] = 389    # 382 → 389
data["evidence_chains"] = 738 # 735 → 738
print(f"Metadata updated: total_chains={data['total_chains']}, trail_chains={data['trail_chains']}, evidence_chains={data['evidence_chains']}")

with open(chains_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("Chains file updated successfully.")
print(f"Total chains now: {len(chains)}")
