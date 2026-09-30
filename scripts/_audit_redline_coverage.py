# -*- coding: utf-8 -*-
"""红线检测器覆盖率审计：哪些红线有真实检测器(发现带 redline_id)，哪些只靠 _DEFAULT_HIT_INDEX 兜底，哪些是盲区。"""
import ast, os, re, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(ROOT, "engine")

# 1) 红线 id（条数动态，以 len(REDLINES) 为准）
import importlib.util
spec = importlib.util.spec_from_file_location("tax_redlines", os.path.join(ENGINE, "tax_redlines.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
REDLINES = mod.REDLINES
all_ids = [r["id"] for r in REDLINES]
id_set = set(all_ids)

# 2) 检测器：**生产代码**（engine/ + main.py）源码中出现 redline_id 后 8 字符内的红线 id 字面量。
#    ★ 2026-09-30 口径修正：**不得把 scripts/ 计入检测器来源** —— 那里是一次性诊断/注入脚本
#      （如 _apply_460_461.py、_verify_combo_profile.py），运行期根本不执行。
#      原实现把它们算作"有真实检测器"，**虚高了覆盖数**（实测 4 条：RL-PTY-002/SPT-012/SPT-013/VAT-012
#      的 redline_id 只出现在 scripts/，却被报为"有检测器"；真实生产检测器应为 74 而非 78）。
def _scan_ids(bases):
    out = {}
    pat_ = re.compile(r'redline_id[^\n]{0,8}?(RL-[A-Z0-9-]+)')
    for base in bases:
        files = []
        if os.path.isdir(base):
            files = [os.path.join(base, fn) for fn in os.listdir(base) if fn.endswith(".py")]
        elif os.path.isfile(base):
            files = [base]
        for fp in files:
            try:
                txt = open(fp, encoding="utf-8").read()
            except Exception:
                continue
            for m in pat_.finditer(txt):
                out.setdefault(m.group(1), set()).add(os.path.basename(fp))
    return out


detector_ids = _scan_ids((ENGINE, os.path.join(ROOT, "main.py")))          # 生产代码
script_ids = _scan_ids((os.path.join(ROOT, "scripts"),))                    # 仅诊断脚本（不计入覆盖）

# ★ 2026-09-29（#448 修复）：原正则只认 `redline_id="RL-X"` / `"redline_id": "RL-X"` 两种写法，
#   漏掉 `_f["redline_id"] = "RL-PTY-001"`（verified_rule_engine 的赋值写法）→ 把有检测器的红线误判为"盲区"。
#   放宽为：`redline_id` 后 8 字符内出现红线 id 字面量即算检测器（已并入上方 _scan_ids）。
#   ⚠ 静态法仍有天然局限（redline_id=变量 / setdefault 变量形态无法静态识别）——
#     **权威口径见 scripts/_gap_constituent_hits.py 的运行态 match_mode + 逐要件 checkpoint**。

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
print("== 有真实检测器(生产代码 engine/+main.py 声明 redline_id):", len(has_detector))
print("== 仅 _DEFAULT_HIT_INDEX 兜底:", len(only_fallback))
print("== 盲区(既无检测器也不在兜底):", len(blind))
print()
print()
print("--- 检测器仅存在于 scripts/（一次性脚本，不计入生产覆盖；如也在兜底表则归入仅兜底）---")
for _r in sorted(id_set):
    if _r not in detector_ids and _r in script_ids:
        print("  ", _r, "| scripts:", sorted(script_ids[_r]), "| 兜底:", _r in dh)
print()
print("--- 仅兜底红线（%d 条：无生产检测器，依赖 _DEFAULT_HIT_INDEX 兜底 / 或检测器仅存在于 scripts/）---" % len(only_fallback))
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
    "script_only_ids": sorted(r for r in id_set if r not in detector_ids and r in script_ids),
}
with open(os.path.join(ROOT, "scripts", "_redline_coverage.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("\n[OK] 已写出 scripts/_redline_coverage.json")
