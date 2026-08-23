import sys; sys.path.insert(0,'.')
import engine.verified_rule_engine as E
cap={}
orig=E.run_verified_rules
def pat(data):
    r=orig(data); cap['r']=r; return r
E.run_verified_rules=pat
import _e2e_daguan as M
# 临时禁用内部断言：monkey 掉 run_evolved_audit 里的 assert 不易，改为直接拿 result
# 复刻 engine_data
import re
src=open('_e2e_daguan.py',encoding='utf-8').read()
# 找 run_evolved_audit 中 engine_data 与 result
exec_globals={}
# 去掉 run_evolved_audit 的断言影响：我们只想要 result，直接重跑 run_verified_rules
# 最简单：调用 M.run_evolved_audit 但捕获 AssertionError
M.setup_company(); M.make_files()
try:
    M.run_evolved_audit()
except AssertionError as e:
    print("caught assert:", e)
r=cap['r']
print("findings count:", len(r['findings']))
trig={f['rule_id'] for f in r['findings']}
print("VR027 in trig:", 'VR027' in trig, "VR052:", 'VR052' in trig, "VR053:", 'VR053' in trig)
dt=E.build_derivation_tree(r['findings'], E.VERIFIED_RULE_CATALOG)
print("roots:", [n['rule_id'] for n in dt['tree']])
print("max_depth:", dt['max_depth'])
# 找任一有children的
for n in dt['tree']:
    if n.get('children'):
        print("node", n['rule_id'], "has children:", [c['rule_id'] for c in n['children']])
        break
