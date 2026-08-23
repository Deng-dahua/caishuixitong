import sys; sys.path.insert(0,'.')
import engine.verified_rule_engine as E
print("module file:", E.__file__)
spec=[c for c in E.VERIFIED_RULE_CATALOG if c['id']=='VR053'][0]
print("VR053 derives_to len:", len(spec.get('derives_to',[])))
# 模拟 e2e 的 run_evolved_audit findings
import _e2e_daguan as M
M.setup_company(); M.make_files()
# 直接复刻 engine_data 调用 run_verified_rules（绕过内部断言）
# 从 M 里取 engine_data 构造：直接 import 函数体
import types
# 用 run_evolved_audit 但把内部 build_derivation_tree 的结果存到全局
_real=E.build_derivation_tree
store={}
def spy(findings, catalog=None):
    r=_real(findings, catalog); store['dt']=r; return r
E.build_derivation_tree=spy
try:
    M.run_evolved_audit()
except AssertionError:
    pass
dt=store.get('dt')
if dt:
    print("spy roots:", [n['rule_id'] for n in dt['tree']])
    print("spy max_depth:", dt['max_depth'])
