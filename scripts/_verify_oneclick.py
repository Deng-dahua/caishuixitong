# -*- coding: utf-8 -*-
"""核验：这些疑点任务的产出是否真的进了"一键分析按钮"的产物。"""
import json, io
d = json.load(io.open("scripts/_oneclick_result.json", encoding="utf-8"))
rep = d["report"]
blob = json.dumps(rep, ensure_ascii=False)

def cnt(s):
    return blob.count(s)

checks = [
    ("疑点23 公积金：有工资无公积金", "有工资无公积金"),
    ("疑点23 公积金：基数低于实际工资", "公积金缴存基数低于实际工资"),
    ("疑点23 公积金：法定最低缴存比例5%", "缴存比例均不得低于"),
    ("疑点23 公积金：真相自证(人数对比)", "工资表 6 人、公积金缴存 5 人"),
    ("疑点23：旧假差额已消失(公积金缴存合计1,200.00 vs)", "公积金缴存合计1,200.00"),
    ("疑点23：旧轴疑点已消失(公积金缴存对等逐月不匹配)", "公积金缴存对等逐月不匹配"),
    ("疑点24 供应商集中度", "供应商"),
    ("疑点2 资金回流", "资金回流"),
    ("疑点11 未开票收入", "未开票"),
    ("采购来源真实性核验", "采购来源"),
    ("推演层(点→面)", "可能的正常解释"),
    ("业态不适用资料", "本业态不适用"),
]
print("%-46s %s" % ("检查项", "命中次数"))
print("-" * 60)
for name, pat in checks:
    print("%-46s %d" % (name, cnt(pat)))

print("\n=== RL-SPT-010 相关发现 ===")
se = rep.get("scenario_execution") or {}
for f in (se.get("findings") or []):
    if f.get("redline_id") == "RL-SPT-010":
        print("  [%s] %s" % (f.get("level"), f.get("type")))

print("\n=== 采购来源真实性核验 相关发现 ===")
for f in (se.get("findings") or []):
    t = str(f.get("type") or "")
    if "采购来源" in t or "procurement" in t.lower():
        print("  [%s] %s" % (f.get("level"), t))

print("\n=== 域清单（含新增域）===")
doms = []
for dr in (rep.get("domain_summary") or []):
    if isinstance(dr, dict) and dr.get("domain"):
        doms.append(dr["domain"])
seen=[]
for x in doms:
    if x not in seen: seen.append(x)
print("  域数:", len(seen))
print("  ", "、".join(seen))
