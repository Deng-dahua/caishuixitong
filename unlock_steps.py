# -*- coding: utf-8 -*-
"""线索链/证据链步数自然化——去除强制模板，按实际调查逻辑确定步数"""
import json, os, copy

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')

def load_json(name):
    with open(os.path.join(STATIC, name), encoding='utf-8') as f:
        return json.load(f)

def save_json(name, data):
    with open(os.path.join(STATIC, name), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

clues = load_json('cross_domain_clues.json')
evid_data = load_json('cross_domain_evidence.json')
evids = evid_data['evidence_chains']

# ========== #24 线索链: 合并步骤2+3，去物理常识标注 ==========
for i, c in enumerate(clues):
    if isinstance(c, dict) and c.get('id') == 'clue-024':
        new_path = [
            {"step": 1, "action": "数据提取:获取连续36个月文化事业建设费申报表+增值税申报表+销项发票明细\u2192汇总各期计费销售额和增值税应税销售额", "evidence": "文化事业建设费申报表+增值税申报表+销项发票明细"},
            {"step": 2, "action": "计费比对与差异量化:文化事业建设费计费销售额vs增值税广告/娱乐服务销售额\u2192差异>5%=异常\u2192量化差异费额\u2192分析差异来源:未申报/错误适用征收范围/错误适用优惠", "evidence": "计费销售额对比表+差异费额计算"},
            {"step": 3, "action": "征收范围核查:核查企业经营范围和实际业务\u2192是否提供广告服务/娱乐服务\u2192销项发票品名是否包含广告/娱乐服务\u2192有应税服务但未申报=漏报", "evidence": "营业执照+经营范围+销项发票品名汇总"},
            {"step": 4, "action": "优惠适用验证:核查是否适用小微企业免征\u2192月销售额\u226410万或季销售额\u226430万\u2192超标但享免征=违规\u2192核查优惠备案", "evidence": "销售额数据+优惠备案材料+免征条件核查表"},
            {"step": 5, "action": "闭环判定:汇总计费差异+征收范围+优惠适用\u2192有应税服务未申报=漏报;超标享免征=违规;计费基数错误=少缴\u2192定性", "evidence": "全部证据链汇总"}
        ]
        c['investigation_path'] = new_path
        print(f'#24 线索链: 6->5步')

# ========== #26 线索链: 去物理常识标注 ==========
for i, c in enumerate(clues):
    if isinstance(c, dict) and c.get('id') == 'clue-026':
        for s in c['investigation_path']:
            s['action'] = s['action'].replace('(物理常识类)', '')
        print(f'#26 线索链: 移除物理常识标注')

# ========== #27 线索链: 去物理常识标注 ==========
for i, c in enumerate(clues):
    if isinstance(c, dict) and c.get('id') == 'clue-027':
        for s in c['investigation_path']:
            s['action'] = s['action'].replace('(物理常识类)', '')
        print(f'#27 线索链: 移除物理常识标注')

# ========== #29 线索链: 合并步骤2+3 ==========
for i, c in enumerate(clues):
    if isinstance(c, dict) and c.get('id') == 'clue-029':
        new_path = [
            {"step": 1, "action": "数据提取:获取银行流水+房产税申报表+租赁合同\u2192汇总各期租金收入和房产税从租计征申报额", "evidence": "银行流水+房产税申报表+租赁合同"},
            {"step": 2, "action": "租金比对与差异量化:银行租金收入\u00d712%=应缴从租房产税\u2192与房产税从租计征申报额比对\u2192差异>5%=异常\u2192量化差异税额\u2192分析来源:未申报租金/租金低报/免租期处理错误", "evidence": "租金对比表+差异税额计算"},
            {"step": 3, "action": "租赁合同核查(物理常识类):对差异房产索取租赁合同\u2192核查合同租金vs银行收款\u2192合同租金<银行收款=低报租金;无合同但有租金收入=账外出租", "evidence": "租赁合同+银行流水+租金收据"},
            {"step": 4, "action": "免租期/装修期排查:核查租赁合同有无免租期/装修期\u2192免租期间应按房产原值计征房产税\u2192未计征=漏报\u2192核查免租期起始和结束", "evidence": "租赁合同+免租期条款+原值计征核查表"},
            {"step": 5, "action": "闭环判定:汇总租金差异+合同核查+免租期\u2192租金收入>申报=漏报;无合同有收入=账外出租;免租期未计征=漏报\u2192定性", "evidence": "全部证据链汇总"}
        ]
        c['investigation_path'] = new_path
        print(f'#29 线索链: 6->5步')

# ========== 证据链: #24/#26/#27/#28/#29 移除"申报一致性"辅助维度 ==========
for eid in ['evid-024', 'evid-026', 'evid-027', 'evid-028', 'evid-029']:
    for i, e in enumerate(evids):
        if isinstance(e, dict) and e.get('id') == eid:
            old_len = len(e['dimensions'])
            e['dimensions'] = [d for d in e['dimensions'] if '申报一致性' not in d.get('dimension', '')]
            new_len = len(e['dimensions'])
            print(f'{eid} 证据链: {old_len}->{new_len}维')

# Save
save_json('cross_domain_clues.json', clues)
evid_data['evidence_chains'] = evids
evid_data['metadata']['total_chains'] = len(evids)
save_json('cross_domain_evidence.json', evid_data)
print('\n已保存')

# Verify
clues = load_json('cross_domain_clues.json')
evids = load_json('cross_domain_evidence.json')['evidence_chains']

print('\n=== 最终步数 ===')
for num in range(1, 31):
    c = [x for x in clues if isinstance(x,dict) and str(num) in x.get('rule_refs',[])]
    e = [x for x in evids if isinstance(x,dict) and str(num) in x.get('rule_refs',[])]
    cs = len(c[0]['investigation_path']) if c else 0
    es = len(e[0]['dimensions']) if e else 0
    if cs != 6 or es != 5:
        name = (c[0].get('name','') if c else '')[:30]
        print(f'  #{num:02d}: 线索{cs}步 证据{es}维  {name}')
