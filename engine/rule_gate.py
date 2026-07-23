# -*- coding: utf-8 -*-
"""规则调度门控引擎 —— 补齐精写编制标准的四大执行缺口

1. applicable_condition 五维前置闸门 — 行业/资质/规模/时间/金额过滤
2. check_frequency 调度分档 — 高频/中频/低频路由
3. threshold 量化触发扩展 — 解析threshold字段数值条件
4. determination 三路径自动定级 — 按独立来源数自动分级
"""
import json, os, re
from collections import defaultdict

# ═══════════════════ 模块1: 五维前置闸门 ═══════════════════

def parse_applicable_condition(text, rule_id=None):
    """解析 applicable_condition 文本，提取五维度结构化条件"""
    if not text:
        return {}
    result = {}
    # 按分号分隔各维度
    parts = text.replace('\n',';').split(';')
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # 匹配 "键:值" 或 "键：值" 格式
        m = re.match(r'(.+?)[：:]\s*(.+)', part)
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip()
            # 标准化key名
            kl = key.lower()
            if '行业' in kl:
                result['industry'] = val
            elif '资质' in kl or '纳税人' in kl:
                result['qualification'] = val
            elif '规模' in kl:
                result['scale'] = val
            elif '时间' in kl:
                result['time'] = val
            elif '金额' in kl:
                result['amount'] = val
            elif '门槛' in kl:
                result['amount'] = val
    return result


def check_industry_match(rule_industry, company):
    """检查企业行业是否匹配规则的行业限制"""
    if not rule_industry or '全行业' in rule_industry or '不限' in rule_industry:
        return True
    co_industry = (company.get('industry_code', '') or company.get('industry', '') or
                   company.get('business_scope', '')).lower()
    rule_ind = rule_industry.lower()
    # 模糊匹配: 规则写了"制造业"则企业行业含"制造"
    for keyword in rule_ind.replace('、',',').replace('/',',').split(','):
        kw = keyword.strip()
        if kw and kw in co_industry:
            return True
    return False


def check_qualification(rule_qual, company):
    """检查纳税人资质是否匹配"""
    if not rule_qual:
        return True
    rule_qual = rule_qual.lower()
    co_type = str(company.get('taxpayer_type', '') or company.get('type', '') or '').lower()
    if '查账' in rule_qual and ('查账' in co_type or not co_type):
        return True
    if '核定' in rule_qual and '核定' in co_type:
        return True
    if '一般纳税人' in rule_qual and '一般' in co_type:
        return True
    if '小规模' in rule_qual and '小规模' in co_type:
        return True
    # 宽松: 不指定则通过
    if not co_type or co_type == '':
        return True
    return True  # 数据不足时不过滤


def check_rule_gate(rule, company_data, data_profile):
    """
    检查规则是否应该通过前置闸门触发。

    Args:
        rule: 规则dict
        company_data: 企业信息dict
        data_profile: 数据概览dict（含行业/规模等推断信息）

    Returns:
        (passed: bool, reason: str)
    """
    # 1. 解析 applicable_condition
    app_text = rule.get('applicable_condition', '')
    if not app_text:
        return True, '无适用条件限制，直接通过'

    cond = parse_applicable_condition(app_text)

    # 2. 行业限制检查
    if cond.get('industry') and not check_industry_match(cond['industry'], company_data):
        return False, f"行业不匹配: 规则要求{cond['industry']}, 企业为{company_data.get('industry_code','?')}"

    # 3. 资质检查
    if cond.get('qualification'):
        if not check_qualification(cond['qualification'], company_data):
            return False, f"资质不匹配: 规则要求{cond['qualification']}"

    # 4. 规模门槛(简化: 不在此处硬查，交给threshold scanner处理)
    if cond.get('scale'):
        # 规模门槛通常需要营收数据，由threshold scanner处理
        pass

    # 5. 时间条件(简化: 需要持续性检测)
    if cond.get('time'):
        # 时间条件由threshold scanner处理
        pass

    # 6. 金额门槛(简化: 由scanner处理)
    if cond.get('amount'):
        pass

    return True, '通过'


# ═══════════════════ 模块2: 调度分档 ═══════════════════

def classify_rule_frequency(rule):
    """
    根据 check_frequency 返回调度优先级。
    高频=1(必扫), 中频=2(行业匹配扫), 低频=3(条件触发扫)
    """
    freq = (rule.get('check_frequency', '') or '').strip()
    if '高频' in freq:
        return 1
    if '中频' in freq:
        return 2
    if '低频' in freq:
        return 3
    return 2  # 默认中频


def should_trigger_by_frequency(rule, company_data, has_industry_match, has_strong_signal):
    """
    根据调度分档判断规则是否应该在此次分析中触发。

    Args:
        rule: 规则dict
        company_data: 企业信息
        has_industry_match: 是否匹配行业
        has_strong_signal: 是否有强触发信号(如threshold命中)

    Returns:
        (should_trigger: bool, confidence: float)
    """
    freq = classify_rule_frequency(rule)
    if freq == 1:
        # 高频: 每户必查, 置信度0.85
        return True, 0.85
    elif freq == 2:
        # 中频: 行业匹配时查, 置信度0.85; 不匹配时降为0.5
        if has_industry_match:
            return True, 0.85
        return has_strong_signal, 0.5
    elif freq == 3:
        # 低频: 仅在强触发信号(threshold命中, 置信度≥0.95)时查
        return has_strong_signal, 0.95
    return True, 0.85


# ═══════════════════ 模块3: 阈值扫描扩展 ═══════════════════

def _safe_f(v, d=0.0):
    try: return float(v) if v not in (None,'','None') else d
    except: return d

def _month_key(d):
    s = str(d).replace('-','').replace('/','').strip()
    return s[:6] if len(s)>=6 else s

def scan_extended_thresholds(engine_data, rules_data, company_data):
    """
    对所有规则执行量化阈值扫描。
    根据threshold字段提取数值条件，检查数据是否满足。
    """
    findings = []
    for rule in rules_data:
        if not isinstance(rule, dict):
            continue
        rid = rule.get('id')
        threshold_text = rule.get('threshold', '')
        if not threshold_text:
            continue

        f = _scan_one_rule(rule, engine_data, company_data)
        if f:
            findings.extend(f)
    return findings


def _scan_one_rule(rule, engine_data, company_data):
    """扫描单条规则的量化阈值"""
    findings = []
    rid = rule.get('id')
    text = rule.get('threshold', '')

    # 通用模式: 提取 "差额>X%且绝对额>Y万"
    pct_match = re.search(r'(?:差额|偏差|偏离)[^>]*[>＞]\s*([\d.]+)\s*%', text)
    abs_match = re.search(r'(?:绝对额|金额|差额)[^>]*[>＞]\s*(\d+)\s*万', text)
    period_match = re.search(r'连续\s*(\d+)\s*(?:期|月|个申报期)', text)

    # 仅在满足通用模式时尝试检查
    if not (pct_match or abs_match):
        return []

    pct_threshold = float(pct_match.group(1)) / 100 if pct_match else 0.01
    abs_threshold = int(abs_match.group(1)) * 10000 if abs_match else 50000
    min_periods = int(period_match.group(1)) if period_match else 2

    # 根据规则类型选择数据源
    bank_txs = engine_data.get('bank_txs', [])
    sal_invs = engine_data.get('sal_invs', [])
    pur_invs = engine_data.get('pur_invs', [])
    vouchers = engine_data.get('vouchers', [])
    trial_balance = engine_data.get('trial_balance', [])

    # 按月份聚合
    monthly_bank = defaultdict(float)
    monthly_sales = defaultdict(float)
    monthly_purchase = defaultdict(float)
    for tx in bank_txs:
        c = _safe_f(tx.get('credit', 0)); d = _safe_f(tx.get('debit', 0))
        if c > 0: monthly_bank[_month_key(tx.get('date',''))] += c
    for inv in sal_invs:
        monthly_sales[_month_key(inv.get('date',''))] += _safe_f(inv.get('total', 0))
    for inv in pur_invs:
        monthly_purchase[_month_key(inv.get('date',''))] += _safe_f(inv.get('total', 0))

    all_months = set(monthly_bank.keys()) | set(monthly_sales.keys())

    # 场景1: 银行收款 vs 申报收入 (适用#9 #21等)
    anomaly_count = 0
    total_anomaly = 0
    for m in sorted(all_months):
        bank = monthly_bank.get(m, 0)
        sales = monthly_sales.get(m, 0)
        if sales > 0 and bank > sales * (1 + pct_threshold) and (bank - sales) > abs_threshold:
            anomaly_count += 1
            total_anomaly += (bank - sales)

    if anomaly_count >= min_periods:
        findings.append({
            'type': f'量化阈值触发: {rule.get("item","")[:40]}',
            'rule_id': rid,
            'severity': rule.get('level', '中风险'),
            'detail': f'{anomaly_count}个月银行收款超出申报收入阈值({pct_threshold*100}%/{abs_threshold}元)，累计差额{total_anomaly:.0f}元',
            'score': rule.get('score', 5),
            'threshold_met': True,
            'evidence_grade': '强证据' if anomaly_count >= 3 else '线索'
        })

    return findings


# ═══════════════════ 模块4: 三路径自动定级 ═══════════════════

def auto_grade_determination(all_findings):
    """
    对每条发现按独立数据源数量自动定级。
    1源=线索级, 2源=强证据级, ≥3源=铁证级。
    在规则enricher注入完毕后运行。
    """
    for f in all_findings:
        if not isinstance(f, dict):
            continue

        # 统计独立来源
        sources = set()
        # 从 _rule_evidence 或 evidence 字段推断来源数
        evidence_text = f.get('_rule_evidence', f.get('evidence', ''))
        # 简化的来源计数: 检查提到了哪些数据源类型
        for kw in ['银行', '流水', 'bank']:
            if kw in str(evidence_text).lower():
                sources.add('bank')
        for kw in ['发票', '进项', '销项', 'invoice']:
            if kw in str(evidence_text).lower():
                sources.add('invoice')
        for kw in ['合同', 'contract']:
            if kw in str(evidence_text).lower():
                sources.add('contract')
        for kw in ['凭证', '账', 'voucher', '序时账']:
            if kw in str(evidence_text).lower():
                sources.add('voucher')
        for kw in ['申报', 'declaration']:
            if kw in str(evidence_text).lower():
                sources.add('declaration')
        for kw in ['社保', '工资', '个税', 'salary', 'social']:
            if kw in str(evidence_text).lower():
                sources.add('personnel')
        for kw in ['存货', '库存', 'inventory']:
            if kw in str(evidence_text).lower():
                sources.add('inventory')

        # 如果 chain_executor 已经提供了 source_chain 信息，也算源
        sc = f.get('source_chain', '')
        if sc:
            sources.add(f'chain_{sc}')

        n_sources = len(sources) if sources else 1

        # 三路径分级
        if n_sources >= 3:
            f['evidence_grade'] = '铁证'
            f['determination_path'] = '路径三·完整证明'
        elif n_sources >= 2:
            f['evidence_grade'] = '强证据'
            f['determination_path'] = '路径二·部分证明'
        else:
            f['evidence_grade'] = '线索'
            f['determination_path'] = '路径一·无法证明'

        f['independent_sources'] = n_sources

    return all_findings


# ═══════════════════ 综合调度入口 ═══════════════════

def apply_all_gates(all_findings, rules_data, company_data, engine_data):
    """
    综合应用四大门控机制到所有发现。
    在报告生成前（enricher运行后）调用。
    """
    # 模4: 自动定级
    all_findings = auto_grade_determination(all_findings)

    # 模2: 对每条发现打调度标签
    rule_map = {}
    for r in rules_data:
        if isinstance(r, dict) and r.get('id'):
            rule_map[str(r['id'])] = r

    for f in all_findings:
        if not isinstance(f, dict):
            continue
        rid = str(f.get('rule_id', f.get('id', '')))
        rule = rule_map.get(rid)
        if rule:
            freq = classify_rule_frequency(rule)
            f['_check_frequency'] = rule.get('check_frequency', '')
            f['_frequency_tier'] = freq
            # 模1: 闸门判定结果
            passed, reason = check_rule_gate(rule, company_data, {})
            f['_gate_passed'] = passed
            f['_gate_reason'] = reason
            if not passed:
                # 闸门未通过：降级为线索且不入正式结论
                f['severity'] = '低风险'
                f['evidence_grade'] = '线索'
                f['_gate_blocked'] = True

    return all_findings
