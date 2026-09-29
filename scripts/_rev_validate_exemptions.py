# -*- coding: utf-8 -*-
"""反向验证：确认本轮新增的豁免/修复是「精准」的，不会掩盖真实的未来错误。
逐条注入反模式 → 确认闸门重新报错 → 复原（临时文件/对象均清理）。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools.audit_consistency as AC
from tools.audit_consistency import (
    check_counts, authoritative_values, check_doc_type_category_map,
    check_redline_admission, check_duplicate_definitions,
)
from engine.enterprise_report import _DOC_TYPE_TO_CATEGORY
from engine.tax_redlines import REDLINES
from engine import tax_redlines as _tr

ROOT = AC.ROOT
results = []

def mark(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")

# (A) COUNT 豁免是精准的：非阈值语境下的错误总量仍须 WARN
#     注入 engine/_rev_count_tmp.py 写 "系统有 50 条规则"（无 ≥/采样/原来外 标记）
p_count = ROOT / "engine" / "_rev_count_tmp.py"
p_count.write_text("系统有 50 条规则，覆盖全部税种。\n", encoding="utf-8")
try:
    auth = authoritative_values()
    cnt = check_counts(auth)
    hit = [c for c in cnt if c[0] == "WARN" and c[1].endswith("_rev_count_tmp.py")]
    mark("A-COUNT豁免精准(非阈值错误总量仍WARN)", bool(hit),
         f"命中={[ (c[2],c[3],c[4]) for c in hit]}")
finally:
    p_count.unlink(missing_ok=True)

# (B) doc_type 修复精准：补充自证 doc_type 已豁免，但真正拼错的键仍须 WARN
orig_keys = list(_DOC_TYPE_TO_CATEGORY.keys())
_DOC_TYPE_TO_CATEGORY["sup_nonexistent_xyz"] = ("银行流水",)
try:
    iss = check_doc_type_category_map()
    susp = [i for i in iss if i[0] == "WARN" and "sup_nonexistent_xyz" in i[2]]
    mark("B-doc_type修复精准(真拼错键仍WARN)", bool(susp), f"命中数={len(susp)}")
finally:
    del _DOC_TYPE_TO_CATEGORY["sup_nonexistent_xyz"]

# (C) 盲区红线豁免精准：新增未登记盲区红线仍须 WARN（退化信号保留）
new_r = {
    "id": "RL-REV-NEW", "constituents": ["有事实", "正当情形"],
    "justifications": ["j"], "required_materials": ["银行流水"],
    "legal_basis": ["个人所得税法"], "remedy": ["补正"],
    "match_hints": ["某异常特征"],
}
REDLINES.append(new_r)
try:
    iss = check_redline_admission()
    warn = [i for i in iss if i[0] == "WARN" and "RL-REV-NEW" in i[2]]
    mark("C-盲区红线豁免精准(新增盲线仍WARN)", bool(warn), f"命中数={len(warn)}")
finally:
    REDLINES.remove(new_r)

# (D) 跨模块分歧豁免精准：未登记的新同名真实分歧仍须 WARN
p_a = ROOT / "engine" / "_rev_dup_a.py"
p_b = ROOT / "engine" / "_rev_dup_b.py"
p_a.write_text("def _rev_dup_helper(x):\n    return x + 1\n", encoding="utf-8")
p_b.write_text("def _rev_dup_helper(x):\n    return x * 2\n", encoding="utf-8")
try:
    iss = check_duplicate_definitions()
    warn = [i for i in iss if i[0] == "WARN" and "_rev_dup_helper" in i[2]]
    mark("D-分歧豁免精准(新同名分歧仍WARN)", bool(warn), f"命中数={len(warn)}")
finally:
    p_a.unlink(missing_ok=True)
    p_b.unlink(missing_ok=True)

print("\n=== 反向验证汇总 ===")
all_pass = all(ok for _, ok, _ in results)
for n, ok, d in results:
    print(f"  {'✅' if ok else '❌'} {n}")
print("ALL PASS =", all_pass)
sys.exit(0 if all_pass else 1)
