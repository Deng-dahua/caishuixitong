"""
为 audit_chains.json 中的所有线索链和证据链批量生成 description 和 sub_topic。
使每条链渲染时都有完整的卡片样式（描述区 + 政策依据 + 税务影响 + 步骤详情 + 元信息栏）。
"""
import json
import re
import os

STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')
AUDIT_CHAINS = os.path.join(STATIC_DIR, 'audit_chains.json')

# ===== name prefix → sub_topic 映射表 =====
PREFIX_TO_TOPIC = {
    '发票': '发票稽查', '发票深度': '发票深度稽查',
    '增值税': '增值税稽查', '企业所得税': '企业所得税稽查',
    '个税': '个人所得税稽查', '个税深度': '个税深度稽查',
    '成本': '成本费用稽查', '成本费用配比': '成本费用配比',
    '收入合规': '收入合规稽查', '隐匿收入': '隐匿收入稽查',
    '虚开': '虚开发票稽查', '出口退税': '出口退税稽查',
    '跨境': '跨境税务稽查', '跨境电商': '跨境电商稽查',
    '行业': '行业专项稽查', '经营实质': '经营实质稽查',
    '经营': '经营合规稽查', '经营深度': '经营深度稽查',
    '资金流': '资金流稽查', '资产负债往来': '资产负债往来',
    '稽查': '稽查技术', '风控': '风险控制',
    '风险': '风险排查', '金融': '金融税务稽查',
    '财产税': '财产税稽查', '申报': '申报合规稽查',
    '社保': '社保稽查', '国际': '国际税务稽查',
    '转让定价': '转让定价稽查', '股权资本': '股权资本稽查',
    '知识产权': '知识产权稽查', '政府补贴': '政府补贴稽查',
    '数字经济': '数字经济稽查', '海关': '海关税务稽查',
    '供应链': '供应链核查', '慈善非营利': '慈善非营利稽查',
    '融资租赁': '融资租赁稽查', '破产重组': '破产重组稽查',
    '资料完备': '资料完备检查', '进销存': '进销存稽查',
    '税务': '税务合规',
}

def get_sub_topic(name):
    """从链名提取 sub_topic"""
    if not name: return ''
    parts = name.split('-')
    if len(parts) >= 2:
        key = parts[0] if len(parts) == 2 else name[:name.index('-')] if '-' in name else name
        if key in PREFIX_TO_TOPIC:
            return PREFIX_TO_TOPIC[key]
        # 模糊匹配
        for prefix, topic in PREFIX_TO_TOPIC.items():
            if key.startswith(prefix) or prefix.startswith(key):
                return topic
    return parts[0] if parts else '其他'


def generate_description(chain):
    """基于链结构生成描述"""
    name = chain.get('name', '')
    
    # 1) 已有 description → 保留
    if chain.get('description'):
        return chain['description']
    
    # 2) investigation_path 数组格式（含 detail）
    ip = chain.get('investigation_path')
    if isinstance(ip, list) and len(ip) > 0:
        # 提取步骤摘要
        step_summaries = []
        for s in ip[:5]:  # 取前5步骤
            item = s.get('rule_item') or s.get('step') or ''
            level = s.get('level', '')
            if item and item not in step_summaries:
                step_summaries.append(item)
        
        # 提取第一条 detail 的第1-2句
        detail_text = ip[0].get('detail', '') if ip[0] else ''
        if detail_text:
            # 取前两个句号或200字
            sentences = re.split(r'[。；]', detail_text)
            if len(sentences) > 1:
                desc = '。'.join(sentences[:2]) + '。'
            else:
                desc = sentences[0][:200]
            # 去除纯空格
            desc = desc.strip()
            
            # 补充步骤覆盖范围
            if step_summaries and len(step_summaries) <= 5:
                desc += f" 本链覆盖：{'、'.join(step_summaries[:5])}等风险点。"
            elif step_summaries:
                desc += f" 本链覆盖{len(step_summaries)}个风险点。"
            
            return desc[:400]  # 限400字
        
        # 无detail → 用步骤名合成
        if step_summaries:
            return f"稽查线索链【{name}】，覆盖{'、'.join(step_summaries[:5])}等{'等多个' if len(step_summaries)>5 else ''}风险点。通过多维度数据比对识别异常，确保稽查全覆盖。"
        
        return f"稽查线索链【{name}】，共{len(ip)}个调查步骤，通过多源数据交叉验证识别税务风险。"
    
    # 3) steps 数组格式（新格式）
    steps = chain.get('steps')
    if isinstance(steps, list) and len(steps) > 0:
        actions = [s.get('action', '') for s in steps[:5] if s.get('action')]
        if actions:
            return f"稽查线索链【{name}】，按步骤执行：{'；'.join(actions[:5])}{'...' if len(actions)>5 else ''}，通过逐层筛查锁定风险点。全行业适用，不依赖特定行业词库。"
        return f"稽查线索链【{name}】，共{len(steps)}个步骤，通过逐层筛查锁定风险点。全行业适用。"
    
    # 4) investigation_path 为字符串
    if isinstance(ip, str) and ip:
        return f"稽查线索链【{name}】。调查路径：{ip[:200]}"
    
    # 5) 兜底
    return f"稽查线索链【{name}】，通过多源数据交叉验证识别税务风险。"


def normalize_high_risk_steps(chain):
    """将 high_risk_steps 从数字转为数组格式"""
    hrs = chain.get('high_risk_steps')
    if hrs is None:
        return
    if isinstance(hrs, int):
        chain['high_risk_steps'] = [hrs]
    elif isinstance(hrs, list):
        # 已经是数组，确保全是整数
        chain['high_risk_steps'] = [int(x) if not isinstance(x, int) else x for x in hrs]


def enrich_chains():
    with open(AUDIT_CHAINS, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    chains = data.get('chains', [])
    clue_chains = [c for c in chains if c.get('chain_type') == '线索链']
    evidence_chains = [c for c in chains if c.get('chain_type') == '证据链']
    
    # ===== 线索链 =====
    clue_missing_desc = 0
    clue_missing_topic = 0
    for c in clue_chains:
        if not c.get('description'):
            c['description'] = generate_description(c)
            clue_missing_desc += 1
        if not c.get('sub_topic'):
            c['sub_topic'] = get_sub_topic(c.get('name', ''))
            clue_missing_topic += 1
        normalize_high_risk_steps(c)
    
    # ===== 证据链 =====
    ev_missing_desc = 0
    ev_missing_topic = 0
    for c in evidence_chains:
        if not c.get('description'):
            c['description'] = generate_description(c)
            ev_missing_desc += 1
        if not c.get('sub_topic'):
            c['sub_topic'] = get_sub_topic(c.get('name', ''))
            ev_missing_topic += 1
        normalize_high_risk_steps(c)
    
    # ===== 方法论 =====
    for c in chains:
        if c.get('chain_type') == '方法论':
            normalize_high_risk_steps(c)
    
    # 写回
    with open(AUDIT_CHAINS, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f'线索链 {len(clue_chains)} 条：新增 description {clue_missing_desc} 条，新增 sub_topic {clue_missing_topic} 条')
    print(f'证据链 {len(evidence_chains)} 条：新增 description {ev_missing_desc} 条，新增 sub_topic {ev_missing_topic} 条')
    print('high_risk_steps 已全部标准化为数组格式')
    print('完成 ✓')


if __name__ == '__main__':
    enrich_chains()
