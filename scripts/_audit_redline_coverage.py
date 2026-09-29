# -*- coding: utf-8 -*-
"""红线检测器覆盖率审计：哪些红线有真实检测器(发现带 redline_id)，哪些只靠 _DEFAULT_HIT_INDEX 兜底，哪些是盲区。"""
import ast, os, re, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(ROOT, "engine")

# 1) 68 条红线 id
import importlib.util
spec = importlib.util.spec_from_file_location("tax_redlines", os.path.join(ENGINE, "tax_redlines.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
REDLINES = mod.REDLINES
all_ids = [r["id"] for r in REDLINES]
id_set = set(all_ids)

# 2) 检测器：源码中出现 redline_id="RL-XXX" 或 redline_id": "RL-XXX"
detector_ids = {}
src_files = []
for base in (ENGINE, os.path.join(ROOT, "scripts"), os.path.join(ROOT, "main.py")):
    if os.path.isdir(base):
        for fn in os.listdir(base):
            if fn.endswith(".py"):
                src_files.append(os.path.join(base, fn))
    elif os.path.isfile(base):
        src_files.append(base)

# ★ 2026-09-29（#448 修复）：原正则只认 `redline_id="RL-X"` / `"redline_id": "RL-X"` 两种写法，
#   漏掉 `_f["redline_id"] = "RL-PTY-001"`（verified_rule_engine 的赋值写法）→ 把有检测器的红线误判为"盲区"。
#   放宽为：`redline_id` 后 8 字符内出现红线 id 字面量即算检测器。
#   ⚠ 静态法仍有天然局限（redline_id=变量 / setdefault 变量形态无法静态识别）——
#     **权威口径见 scripts/_gap_constituent_hits.py 的运行态 match_mode + 逐要件 checkpoint**。
pat = re.compile(r'redline_id[^\n]{0,8}?(RL-[A-Z0-9-]+)')
for fp in src_files:
    try:
        txt = open(fp, encoding="utf-8").read()
    except Exception:
        continue
    for m in pat.finditer(txt):
        rid = m.group(1)
        detector_ids.setdefault(rid, set()).add(os.path.basename(fp))

# 3) _DEFAULT_HIT_INDEX 兜底（位于 redline_engine.py，不能用 import 触发整链依赖，改用 ast 解析）
def _extract_default_hit_index(engine_py):
    src = open(engine_py, encoding="utf-8").read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "_DEFAULT_HIT_INDEX":
                    return ast.literal_eval(node.value)
    return {}
dh = _extract_default_hit_index(os.path.join(ENGINE, "redline_engine.py"))

has_detector = {r for r in all_ids if r in detector_ids}
only_fallback = {r for r in all_ids if r in dh and r not in detector_ids}
blind = [r for r in all_ids if r not in detector_ids and r not in dh]

print("== 红线总数:", len(all_ids))
print("== 有真实检测器(源码声明 redline_id):", len(has_detector))
print("== 仅 _DEFAULT_HIT_INDEX 兜底:", len(only_fallback))
print("== 盲区(既无检测器也不在兜底):", len(blind))
print()
print("--- 仅兜底红线（18条，依赖中枢兜底，检测器为弱）---")
for r in sorted(only_fallback):
    print("  ", r, "hit=", dh.get(r))
print()
print("--- 盲区红线（须补检测器或兜底登记，否则命中即靠 match_redline_grounded 模糊匹配）---")
for r in blind:
    print("  ", r)
print()
print("--- 检测器分布（按文件）---")
from collections import Counter, defaultdict
files = defaultdict(set)
for rid, fs in detector_ids.items():
    for f in fs:
        files[f].add(rid)
for f in sorted(files):
    print(f"  {f}: {len(files[f])} 条")

# 输出 JSON 供后续脚本消费
out = {
    "all_ids": all_ids,
    "has_detector": sorted(has_detector),
    "only_fallback": sorted(only_fallback),
    "blind": blind,
    "default_hit_index": dh,
}
with open(os.path.join(ROOT, "scripts", "_redline_coverage.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("\n[OK] 已写出 scripts/_redline_coverage.json")
