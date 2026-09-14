# -*- coding: utf-8 -*-
"""VR067 修正回归验证：红冲(红字发票)不再被误判为折扣折让，真折扣仍报。"""
import json, os, glob, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
REPO = r"C:\Users\Administrator\WorkBuddy\2026-08-04-21-37-33\caishuixitong"
sys.path.insert(0, REPO)
from engine.verified_rule_engine import _scan_discount_anomaly

spec = {"id": "VR067", "name": "销售折扣与折让异常", "required_sources": ["sal_invs"]}


def run(rows):
    return _scan_discount_anomaly({"sal_invs": rows}, spec)


# (1) 真实公司1 全库销项发票行 → 期望 0（原误报 958,396.22 元 / 4 笔红冲）
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
print(f"[1] 真实销项发票 {len(sal)} 行 -> findings={len(r1)}   (expect 0，原为 1 条误报)")
assert not r1, r1

# (2) 无反证线索的裸负数行（无红冲标识、无配平）-> 仍触发（防矫枉过正）
r2 = run([{"goods": "*服装*毛衫", "amount": -80000}])
print(f"[2] 裸负数行 -80000（无红冲标识/无配平）-> findings={len(r2)}   (expect 1)")
assert len(r2) == 1

# (3) 带红冲标识的负数行 -> 不触发
r3 = run([{"goods": "*会展服务*策划服务费", "amount": -396886.79,
           "remark": "被红冲蓝字数电发票号码：25952000000215222521 红字发票信息确认单编号：44030725101001526292"}])
print(f"[3] 带红字发票信息确认单的红冲行 -> findings={len(r3)}   (expect 0)")
assert not r3

# (4) 同购方同额一正一负配平（无标识）-> 判红冲，不触发
r4 = run([{"buyer": "广州天与空广告有限公司", "goods": "*广告服务*广告发布费", "amount": -244339.62},
          {"buyer": "广州天与空广告有限公司", "goods": "*广告服务*广告发布费", "amount": 244339.62}])
print(f"[4] 同购方同额一正一负 -> findings={len(r4)}   (expect 0)")
assert not r4

# (5) 真折扣（品名含"折扣"，正数金额）-> 仍触发
r5 = run([{"buyer": "某客户", "goods": "*服装*折扣折让", "amount": 60000}])
print(f"[5] 品名含折扣/折让且≥5万 -> findings={len(r5)}   (expect 1)")
assert len(r5) == 1

# (6) 空数据 -> 0
print(f"[6] 空 sal_invs -> findings={len(run([]))}   (expect 0)")
assert run([]) == []

print("\nALL PASS")
