"""直接运行深圳海更(company_id=2)的一键分析"""
import sys, json, time, traceback

sys.path.insert(0, '.')

from database import SessionLocal
from main import _run_analyze

db = SessionLocal()
try:
    start = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] 开始分析 company_id=2 (深圳海更数字传媒)...")
    result = _run_analyze(2, db)
    elapsed = time.time() - start
    print(f"[{time.strftime('%H:%M:%S')}] 分析完成, 耗时 {elapsed:.1f}s")
    
    # Save result
    with open('haigen_report.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    ok = result.get('ok', False)
    print(f"结果: ok={ok}")
    if not ok:
        print(f"错误: {result.get('message', 'unknown')}")
    else:
        # Summary
        te = result.get('target_entity', {})
        print(f"被查单位: {te.get('name', '?')}")
        print(f"行业: {te.get('industry_online', te.get('industry', '?'))}")
        findings = result.get('findings', [])
        print(f"风险发现: {len(findings)} 条")
        narrative = result.get('narrative', {})
        print(f"报告段落: {len(narrative)} 段")
        
except Exception as e:
    print(f"异常: {e}")
    traceback.print_exc()
finally:
    db.close()
