import sys; sys.path.insert(0,'.')
import engine.verified_rule_engine as E
orig=E.run_verified_rules
cap={}
def pat(data):
    r=orig(data); cap['r']=r; return r
E.run_verified_rules=pat
import _e2e_daguan as M
M.setup_company(); M.make_files()
try: M.run_evolved_audit()
except SystemExit: pass
r=cap['r']
dt=E.build_derivation_tree(r['findings'], E.VERIFIED_RULE_CATALOG)
print("roots:", [(n['rule_id'], len(n.get('children',[]))) for n in dt['tree']][:6])
print("max_depth:", dt['max_depth'])
# 找VR053 node
def find(nodes, rid):
    for n in nodes:
        if n['rule_id']==rid: return n
        r=find(n.get('children',[]), rid)
        if r: return r
    return None
v53=find(dt['tree'],'VR053')
print("VR053 children:", [c['rule_id'] for c in (v53 or {}).get('children',[])])
