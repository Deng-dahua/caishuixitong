import sys; sys.path.insert(0,'.')
import engine.verified_rule_engine as E
cap={}
orig=E.run_verified_rules
def pat(d):
    r=orig(d); cap['r']=r; return r
E.run_verified_rules=pat
import _e2e_daguan as M
M.setup_company(); M.make_files()
try: M.run_evolved_audit()
except AssertionError: pass
r=cap['r']
dt=E.build_derivation_tree(r['findings'], E.VERIFIED_RULE_CATALOG)
def find_nodes(tree, rid, acc):
    for n in tree:
        if n.get('rule_id')==rid and not n.get('cycle_ref'): acc.append(n)
        find_nodes(n.get('children',[]), rid, acc)
    return acc
v53=find_nodes(dt['tree'],'VR053',[])
print("VR053 non-cycle nodes:", len(v53))
for i,n in enumerate(v53):
    print(f"  node{i} children:", [(c.get('rule_id'), c.get('cycle_ref')) for c in n.get('children',[])])
