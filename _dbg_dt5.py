import sys; sys.path.insert(0,'.')
import engine.verified_rule_engine as E
import _e2e_daguan as M
M.setup_company(); M.make_files()
# 复刻 run_evolved_audit 的 engine_data：直接调用内部函数获取
# run_evolved_audit 内 engine_data 是局部变量，用 runpy 提取不现实
# 改为：直接调用 M.run_verified_rules 经 patch 拿 result
cap={}
orig=E.run_verified_rules
def pat(data):
    r=orig(data); cap['r']=r; return r
E.run_verified_rules=pat
# 重新跑 run_evolved_audit 但屏蔽它的内部断言（用 patch 让 build_derivation_tree 不抛）
try:
    M.run_evolved_audit()
except AssertionError:
    pass
r=cap['r']
print("result findings:", len(r['findings']))
print("has derivation_tree key:", 'derivation_tree' in r)
dt=r.get('derivation_tree',{})
print("dt root_count:", dt.get('root_count'), "max_depth:", dt.get('max_depth'))
# 关键：triggered 集合
trig={f['rule_id'] for f in r['findings']}
print("VR053 in trig:", 'VR053' in trig)
# 直接以这批 findings 调 build_derivation_tree
dt2=E.build_derivation_tree(r['findings'], E.VERIFIED_RULE_CATALOG)
print("dt2 roots:", [n['rule_id'] for n in dt2['tree']][:5], "max_depth:", dt2['max_depth'])
