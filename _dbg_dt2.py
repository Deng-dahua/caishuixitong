import sys; sys.path.insert(0,'.')
import engine.verified_rule_engine as E
cat=E.VERIFIED_RULE_CATALOG
child_ids=set()
for c in cat:
    for d in (c.get("derives_to") or []):
        child_ids.add(d.get("child"))
print("child_ids from catalog:", sorted(x for x in child_ids if x))
print("catalog total:", len(cat))
# 直接测 build_derivation_tree 用空 findings
dt=E.build_derivation_tree([{"rule_id":"VR053"},{"rule_id":"VR028"},{"rule_id":"VR051"},{"rule_id":"VR052"}], cat)
print("determinism test roots:", [n['rule_id'] for n in dt['tree']])
v53=[n for n in dt['tree'] if n['rule_id']=='VR053'][0]
print("VR053 children:", [c['rule_id'] for c in v53.get('children',[])])
