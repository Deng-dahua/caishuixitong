"""
从 _run_analyze 提取数据并生成税务合规报告
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal
from main import _run_analyze

def clean_for_json(obj):
    if isinstance(obj, dict):
        return {str(k): clean_for_json(v) for k, v in obj.items() 
                if not callable(v) and not str(k).startswith('_')}
    elif isinstance(obj, list):
        return [clean_for_json(i) for i in obj]
    elif callable(obj):
        return None
    return obj

db = SessionLocal()
try:
    result = _run_analyze(1, db)
    report = result.get('report', {})
    
    comp = report.get('comprehensive', {})
    allF = report.get('all_findings', [])
    
    # 风险分级
    high_risks = [f for f in allF if f.get('level') == '高风险']
    mid_risks = [f for f in allF if f.get('level') == '中风险']
    low_risks = [f for f in allF if f.get('level') == '低风险']
    
    mi = comp.get('material_intel', {})
    bi = mi.get('银行流水', {})
    ii = mi.get('发票', {})
    
    # 构建报告数据
    # 文件类型统计
    type_label = {"bank_statement":"银行流水","sales_invoice":"销项发票","purchase_invoice":"进项发票","salary":"工资表","social_security":"社保明细","housing_fund":"公积金","voucher":"记账凭证","inventory":"进销存台账","contract":"合同文件","contract_list":"合同清单","trial_balance":"科目余额表","financial_statements":"财务报表","vat_declaration":"增值税申报","cit_declaration":"企业所得税申报","employee_list":"员工名册","individual_tax":"个税申报","expense_detail":"费用明细"}
    files_by_type = {}
    for fr in report.get("file_results", []):
        ft = fr.get("type", "other")
        label = type_label.get(ft, ft)
        files_by_type[label] = files_by_type.get(label, 0) + 1
    
    report_data = {
        'ok': True,
        'files_count': report.get('files_count', 0),
        'files_by_type': files_by_type,
        'total_risks': len(allF),
        'high_risk': len(high_risks),
        'mid_risk': len(mid_risks),
        'low_risk': len(low_risks),
        'high_list': [{k: v for k, v in f.items() if not callable(v) and k in ['type', 'level', 'score', 'detail', 'description', 'tax_impact', 'policy_ref', 'suggestion', 'category', 'items', 'rule_id', 'level_fixed']} for f in high_risks],
        'mid_list': [{k: v for k, v in f.items() if not callable(v) and k in ['type', 'level', 'score', 'detail', 'description', 'tax_impact', 'policy_ref', 'suggestion', 'category', 'items', 'rule_id', 'level_fixed']} for f in mid_risks],
        'low_list': [{k: v for k, v in f.items() if not callable(v) and k in ['type', 'level', 'score', 'detail', 'description', 'tax_impact', 'policy_ref', 'suggestion', 'category', 'items', 'level_fixed']} for f in low_risks],
        'pipeline_log': report.get('pipeline_log', []),
        'target_entity': report.get('target_entity', {}),
        'cashflow': {
            'monthly': [clean_for_json(m) for m in comp.get('cashflow', {}).get('monthly', [])[:12]],
        },
        'top_receivers': [clean_for_json(r) for r in comp.get('top_receivers', [])[:15]],
        'top_payers': [clean_for_json(p) for p in comp.get('top_payers', [])[:15]],
        'actions': comp.get('actions', {}),
        'rules_used': report.get('rules_used', 0),
    }
    
    with open('report_data.json', 'w', encoding='utf-8') as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"Report data saved: {len(high_risks)} high, {len(mid_risks)} mid, {len(low_risks)} low")
    
finally:
    db.close()
