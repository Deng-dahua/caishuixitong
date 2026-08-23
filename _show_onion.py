import sys; sys.path.insert(0,'.')
import engine.verified_rule_engine as E
import engine.enterprise_report as R
# 捕获 run_evolved_audit 内部第338行的真实 result
_real_dt = {}
_orig_build = E.build_derivation_tree
def spy_dt(findings, catalog=None):
    r=_orig_build(findings, catalog)
    # 只在 findings 较多时记录（达冠样本）
    if len(findings) > 10:
        _real_dt['dt'] = r
        _real_dt['findings'] = findings
    return r
E.build_derivation_tree = spy_dt
import _e2e_daguan as M
M.setup_company(); M.make_files()
try: M.run_evolved_audit()
except AssertionError: pass
report_data={"all_findings": _real_dt['findings'], "derivation_tree": _real_dt['dt']}
rep=R.build_enterprise_readable_report(report_data)
dt=rep.get('derivation_tree_report')
print("="*70)
print(dt['title'])
print("-"*70)
print("摘要:", dt['summary'])
print("原则:", dt['principle'])
print("="*70)
print(dt['body'])
