"""
从用户一句话提炼规则+线索链+证据链，追加到 audit_chains.json。
用户语句：
"工商登记行业登记为纺织品批发，我们经过对进项发票审核出加工费信号与企业主营业务相关，
且又匹对销项发票的项目与进项发票项目，有些项目是购进与销售相同，
有些项目是购进与销售不同，综合判断企业实质是纺织贸易+外包轻加工模式。"

提炼出的五个步骤（对应五步核查法）：
1. 获取工商登记信息 → 取得注册行业/企业类型
2. 进项发票审核 → 检查加工费信号，列出仅购进品名
3. 销项发票审核 → 列出仅销售品名
4. 进销交叉比对 → 相同品名(纯贸易) vs 不同品名(加工转换)
5. 综合判断 → 工商登记vs实质 → 外包轻加工/纯贸易/制造业
"""
import json
import os

STATIC = os.path.join(os.path.dirname(__file__), 'static')
AUDIT_CHAINS = os.path.join(STATIC, 'audit_chains.json')

# ===== 新线索链 =====
new_clue_chain = {
    "name": "经营实质-工商登记vs发票数据差异检测",
    "chain_type": "线索链",
    "sub_topic": "经营实质核查",
    "steps": [
        {"step": 1, "action": "联网核查获取工商登记行业/企业类型/经营范围"},
        {"step": 2, "action": "对全部进项发票逐票审核：检查加工费信号、列出仅购进品名（拟为原材料）"},
        {"step": 3, "action": "对全部销项发票逐票审核：列出仅销售品名（拟为加工后成品）"},
        {"step": 4, "action": "进销品名交叉比对：相同品名=纯贸易，不同品名=存在加工转换环节"},
        {"step": 5, "action": "综合判断：工商登记行业 vs 发票数据推断 → 确定实质经营模式（纯贸易/外包轻加工/制造业）"}
    ],
    "high_risk_steps": [4, 5],
    "policies": [
        "《税收征收管理法》——实质重于形式原则",
        "《企业所得税法》第八条——成本费用真实性要求",
        "《发票管理办法》——发票品名应与实际经营一致"
    ],
    "tax_impacts": [
        "工商登记≠实质经营→按实质经营模式进行税务处理",
        "外包轻加工→需核实委托加工合同+BOM表+加工费真实性",
        "不符合经营实质的发票→进项税额转出+补缴企业所得税"
    ],
    "description": "通过五步核查法检测企业工商登记行业与发票数据推断的实质经营是否一致。第一步获取工商登记信息，第二步审核进项发票（加工费信号+仅购进品名），第三步审核销项发票（仅销售品名），第四步进销交叉比对（相同品名=纯贸易，不同品名=加工转换），第五步综合判断实质经营模式。全行业适用——不依赖特定行业词库，通过加工费信号+进销品名差异统一检测外包轻加工模式。",
    "trigger_keywords": ["工商登记", "经营实质", "外包轻加工", "进销品名差异", "加工费", "五步核查"],
    "quality_score": 19,
    "covered_rule_ids": [999501],
    "covered_rule_count": 1,
    "related_chains": ["经营实质-进销品名交叉验证闭环"],
    "related_chain_count": 1,
    "investigation_path": [
        {
            "step": "获取工商登记信息",
            "rule_id": 999501,
            "rule_item": "工商登记企业类型与发票推断不一致",
            "level": "高风险",
            "score": 8,
            "detail": "通过联网核查获取企业工商登记信息（行业/企业类型/经营范围），与发票数据推断的实质经营行业进行对比。工商登记为批发业但发票数据显示存在加工费+进销品名转换时，实质经营可能为外包轻加工模式。全行业适用——任何行业都可能存在外包轻加工（如电子元器件→SMT贴片加工→PCBA成品）。",
            "policy_ref": "《税收征收管理法》实质重于形式原则",
            "tax_impact": "按实质经营模式重新定性→可能涉及增值税税率差异、企业所得税成本扣除标准、印花税税目适用等全方位调整",
            "suggestion": "对比工商登记经营范围与实际发票数据反映的经营实质，不一致时按实质重于形式原则确定税务处理方式"
        }
    ],
    "total_steps": 5,
    "code_position": "main.py:_run_analyze(target_entity._has_processing_signal+_goods_analysis)+tax-doc-analysis.js:经营实质核查section"
}

# ===== 新证据链 =====
new_evidence_chain = {
    "name": "经营实质-进销品名交叉验证闭环",
    "chain_type": "证据链",
    "sub_topic": "经营实质核查",
    "steps": [
        {"step": 1, "action": "验证：工商登记行业信息是否准确？来源：联网核查/企查查/国家企业信用信息公示系统"},
        {"step": 2, "action": "验证：进项发票中加工费项目的真实性——核对委托加工合同+银行付款记录"},
        {"step": 3, "action": "验证：仅购进品名确实为原材料/半成品——核对供应商资质+物流单据"},
        {"step": 4, "action": "验证：仅销售品名确实为加工后成品——核对BOM表+产出数量vs原料投入数量"},
        {"step": 5, "action": "验证：进销共同品名的纯贸易部分——核对购销合同+进销价格合理性"}
    ],
    "high_risk_steps": [2, 4],
    "policies": [
        "《发票管理办法》第二十二条——发票品名应与实际交易一致",
        "《企业所得税法》第八条——成本费用须真实、合理、相关",
        "《税收征收管理法》第三十五条——核定征收情形之一：账簿不全/成本资料残缺"
    ],
    "tax_impacts": [
        "加工费无合同→委托加工真实性存疑→可能涉及虚开发票",
        "BOM表缺失→无法验证投入产出→核定征收风险",
        "品名差异无合理解释→进项税额转出+补缴企业所得税"
    ],
    "description": "对经营实质核查的五个证据维度进行闭环交叉验证。通过工商登记信息（法律形式）、加工费合同（商业实质）、供应商资质（业务真实）、BOM表（技术可行）、购销合同（价格公允）五个维度形成完整证据闭环。换一个税务合规员拿同样资料能得出同样结论。全行业适用——不依赖特定行业词库。",
    "trigger_keywords": ["证据闭环", "交叉验证", "BOM表", "委托加工合同", "工商登记验证"],
    "quality_score": 18.5,
    "covered_rule_ids": [999501],
    "covered_rule_count": 1,
    "related_chains": ["经营实质-工商登记vs发票数据差异检测"],
    "related_chain_count": 1,
    "investigation_path": "工商登记信息→加工费合同→供应商资质→BOM表→购销合同五维交叉验证",
    "total_steps": 5,
    "code_position": "main.py:_run_analyze(target_entity._goods_analysis)+tax-doc-analysis.js:经营实质核查section"
}

# ===== 追加到 audit_chains.json =====
with open(AUDIT_CHAINS, 'r', encoding='utf-8') as f:
    data = json.load(f)

data['chains'].append(new_clue_chain)
data['chains'].append(new_evidence_chain)
data['total_chains'] = len(data['chains'])
data['trail_chains'] = len([c for c in data['chains'] if c['chain_type'] == '线索链'])
data['evidence_chains'] = len([c for c in data['chains'] if c['chain_type'] == '证据链'])

with open(AUDIT_CHAINS, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Added 2 chains. Total now: {data['total_chains']} (线索链:{data['trail_chains']}, 证据链:{data['evidence_chains']})")
print("Done ✓")
