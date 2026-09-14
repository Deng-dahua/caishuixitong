# -*- coding: utf-8 -*-
"""VR071 红字发票（红冲）合规性 —— 回归验证。

校验：合规红冲（有确认单 + 与蓝票同额配平）不报；缺确认单或缺配平 → 报；
非红冲的孤立负数行不由本规则处理（由 VR067 负责）；规则已接入 run_verified_rules。
"""
import json, os, glob, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
REPO = r"C:\Users\Administrator\WorkBuddy\2026-08-04-21-37-33\caishuixitong"
sys.path.insert(0, REPO)
from engine.verified_rule_engine import _scan_reversal_compliance, run_verified_rules, VERIFIED_RULE_CATALOG, _SCANNERS

spec = {"id": "VR071", "name": "红字发票（红冲）合规性异常", "required_sources": ["sal_invs"]}


def run(rows):
    return _scan_reversal_compliance({"sal_invs": rows}, spec)


# (0) 注册检查
assert any(s["id"] == "VR071" for s in VERIFIED_RULE_CATALOG), "VR071 未进 catalog"
assert "VR071" in _SCANNERS, "VR071 未注册 scanner"
print("[0] VR071 已注册 catalog + _SCANNERS  OK")

# (1) 真实公司1 全库销项发票（4 笔红冲均有确认单且与蓝票配平）→ 0
TR = os.path.join(REPO, "data", "uploads", "transfer")
sal = []
for p in sorted(glob.glob(os.path.join(TR, "*.json"))):
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        continue
    if isinstance(d, dict) and d.get("type") == "sales_invoice":
        sal += [r for r in d.get("rows", []) if isinstance(r, dict)]
r1 = run(sal)
print(f"[1] 真实销项 {len(sal)} 行（4 笔合规红冲）-> findings={len(r1)}   (expect 0)")
assert not r1, r1

# (2) 红冲有确认单但无同额蓝票配平 → 报「无同购方同额蓝票配平」
r2 = run([{"buyer": "甲", "goods": "*服务*服务费", "amount": -120000,
           "remark": "红字发票信息确认单编号：44030725051001117191"}])
print(f"[2] 有确认单、无蓝票配平 -> findings={len(r2)}   (expect 1)")
assert len(r2) == 1
assert "无同购方同额蓝票配平" in json.dumps(r2[0]["observed_metrics"], ensure_ascii=False)

# (3) 有一正一负配平但无确认单编号 → 报「无红字发票信息确认单编号」
r3 = run([{"buyer": "乙", "goods": "*服务*服务费", "amount": -200000},
          {"buyer": "乙", "goods": "*服务*服务费", "amount": 200000}])
print(f"[3] 有配平、无确认单 -> findings={len(r3)}   (expect 1)")
assert len(r3) == 1
assert "无红字发票信息确认单编号" in json.dumps(r3[0]["observed_metrics"], ensure_ascii=False)

# (4) 合规红冲（确认单 + 同额配平）→ 0
r4 = run([{"buyer": "丙", "goods": "*服务*服务费", "amount": 300000},
          {"buyer": "丙", "goods": "*服务*服务费", "amount": -300000,
           "remark": "被红冲蓝字数电发票号码：25952000000215222521 红字发票信息确认单编号：44030725101001526292"}])
print(f"[4] 合规红冲 -> findings={len(r4)}   (expect 0)")
assert not r4

# (5) 非红冲孤立负数（无标识、无配平）→ 不由本规则处理（归 VR067）
r5 = run([{"buyer": "丁", "goods": "*服务*服务费", "amount": -80000}])
print(f"[5] 非红冲孤立负数 -> findings={len(r5)}   (expect 0，交 VR067)")
assert not r5

# (6) 空 -> 0
print(f"[6] 空 -> findings={len(run([]))}   (expect 0)")
assert run([]) == []

# (7) 端到端：run_verified_rules 在含不合规红冲的数据上应触发 VR071
res = run_verified_rules({
    "sal_invs": [{"buyer": "乙", "goods": "*服务*服务费", "amount": -200000},
                 {"buyer": "乙", "goods": "*服务*服务费", "amount": 200000}],
    "target_entity": {}, "company_profile": {},
})
ex = [e for e in res.get("executions", []) if e.get("rule_id") == "VR071"]
print(f"[7] run_verified_rules 执行 VR071: {ex}")
assert ex and ex[0]["status"] == "triggered", ex
assert any(f.get("rule_id") == "VR071" for f in res.get("findings", []))

print("\nALL PASS")
