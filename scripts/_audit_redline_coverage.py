# -*- coding: utf-8 -*-
"""红线检测器覆盖率审计：哪些红线有真实检测器(发现带 redline_id)，哪些只靠 _DEFAULT_HIT_INDEX 兜底，哪些是盲区。"""
import ast, os, re, sys, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(ROOT, "engine")

# ★ 2026-10-10 修复：本脚本原先**跑不起来** —— 直接 exec `engine/tax_redlines.py`，
#   而该模块自身 `from engine.industry_benchmark import ...` ⇒ `ModuleNotFoundError: No module named 'engine'`。
#   与既有教训同源：「只读核验脚本必须 `sys.path.insert(0, ROOT)`，否则 import 取数失败」
#   （那次的形态是**静默取空**，这次是**直接崩**；两者都会让"覆盖率审计"给出错结论）。
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

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


# ── 第二来源：**归属唯一权威表**（2026-10-10 A-P0-4 根因修复）────────────────
#   ★ 病根（实测，非设想）：本脚本原先只认"源码里 `redline_id` 旁出现红线 id 字面量"。
#     而本项目存在**第二种合法声明形态**：归属由**一张权威表**给出，检测器不写字面量 ——
#     `engine/subject_consistency.py`：
#       · `REDLINE_SUBJECT_DECL`   —— 红线编号 → 允许声明它的「发现主体短语」（归属层唯一权威）
#       · `RECONCILE_AXIS_REDLINE` —— 勾稽轴标题 → (红线编号, 发现主体样例)
#     实测：`RL-CIT-008`、`RL-PAY-002` 两条的归属**完全来自表**（全仓无字面量）
#     ⇒ 本脚本把它们记成「仅兜底」，而真产物里它们是 `match_mode="declared"`（真认领）。
#     ⇒ **检出能力被系统性低估**（82 报成 80，仅兜底 9 报成 11 的一半）。
#   ⚠ 这不是"加白名单"：读的是**权威表本身**（与 `_map_finding` 判 declared 同源），
#     新增一条勾稽轴/一条主体声明**只需加一行数据**，本脚本自动跟上。
def _declared_by_authority_tables():
    """返回 (ids, detail)：由**归属权威表**声明的红线编号集合 + 来源明细。"""
    ids, detail = set(), {}
    try:
        import importlib
        _sc = importlib.import_module("engine.subject_consistency")
    except Exception as _e:                       # noqa: BLE001
        print("!! 归属权威表读不出来（engine.subject_consistency）：%r" % (_e,))
        return ids, detail
    for rid in (getattr(_sc, "REDLINE_SUBJECT_DECL", {}) or {}):
        if rid in id_set:
            ids.add(rid)
            detail.setdefault(rid, []).append("REDLINE_SUBJECT_DECL")
        else:
            print("!! REDLINE_SUBJECT_DECL 里的 %r 不在红线库（幽灵登记）" % rid)
    for _axis, _v in (getattr(_sc, "RECONCILE_AXIS_REDLINE", {}) or {}).items():
        _rid = (_v[0] if isinstance(_v, (list, tuple)) and _v else "") or ""
        if not _rid:
            continue                              # 刻意留空的轴（设计如此，不套红线）
        if _rid in id_set:
            ids.add(_rid)
            detail.setdefault(_rid, []).append("RECONCILE_AXIS_REDLINE:%s" % _axis)
        else:
            print("!! RECONCILE_AXIS_REDLINE[%r] 指向不存在的红线 %r" % (_axis, _rid))
    return ids, detail


table_ids, table_detail = _declared_by_authority_tables()


# ── 第三形态：**有意不做盲发兜底**（2026-10-10 A-P0-2 冗余裁定）────────────
#   `engine/redline_engine.py::_NO_BLIND_CONSTITUENT_FALLBACK`：这些红线**要件异质**，
#   盲发兜底会把任何命中都记成同一条要件 ⇒ **假闭环**，故**有意**不登记兜底序号。
#   它们不是"盲区"（可达性由软匹配保证，准入闸门 `check_redline_admission` 同等待遇），
#   而是**刻意设计的第三类**。若不认这一类，把红线移出兜底后会被本脚本错记成"盲区"。
def _no_blind_fallback_ids():
    try:
        import importlib
        _re = importlib.import_module("engine.redline_engine")
        return {r for r in (getattr(_re, "_NO_BLIND_CONSTITUENT_FALLBACK", set()) or set())
                if r in id_set}
    except Exception as _e:                       # noqa: BLE001
        print("!! 有意不兜底名单读不出来：%r" % (_e,))
        return set()


no_blind_ids = _no_blind_fallback_ids()
# 自洽性：既在"有意不兜底"名单、又还在兜底表里 ⇒ 半途而废的迁移（必须显式报出）
_contradiction = sorted(r for r in no_blind_ids if r in dh)
for _r in _contradiction:
    print("!! %s 既在 _NO_BLIND_CONSTITUENT_FALLBACK（声明不兜底）又仍在 _DEFAULT_HIT_INDEX ⇒ 矛盾" % _r)

# 字面量口径（静态正则所能看到的）与**并集口径**（= 真实检出能力）分开报，避免口径混淆
has_detector_static = {r for r in all_ids if r in detector_ids}
has_detector = has_detector_static | table_ids
only_fallback = {r for r in all_ids if r in dh and r not in has_detector}
no_blind_no_detector = no_blind_ids - has_detector
blind = [r for r in all_ids if r not in has_detector and r not in dh
         and r not in no_blind_ids]

print("== 红线总数:", len(all_ids))
print("== 有真实检测器: %d  = 字面量声明 %d ∪ 归属权威表声明 %d"
      % (len(has_detector), len(has_detector_static), len(table_ids)))
print("   · 仅由**归属权威表**声明（静态正则看不见）：%d 条 -> %s"
      % (len(table_ids - has_detector_static), sorted(table_ids - has_detector_static)))
print("== 仅 _DEFAULT_HIT_INDEX 兜底:", len(only_fallback))
print("== 有意不做兜底（要件异质，可达性由软匹配保证）: %d 条 -> %s"
      % (len(no_blind_no_detector), sorted(no_blind_no_detector)))
print("== 盲区(既无检测器、也不在兜底、也非有意不兜底):", len(blind))
print()
print()
print("--- 归属权威表声明的红线明细（新增同类只加一行数据）---")
for _r in sorted(table_detail):
    print("  ", _r, "|", ", ".join(sorted(table_detail[_r])))
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
    # ★ 2026-10-10：两个来源分开留痕 —— 口径必须可审，不得把并集混成"一个数字"
    "has_detector_static": sorted(has_detector_static),
    "has_detector_authority_table": sorted(table_ids),
    "declared_table_detail": {k: sorted(v) for k, v in table_detail.items()},
    "only_fallback": sorted(only_fallback),
    "no_blind_fallback_ids": sorted(no_blind_ids),
    "no_blind_fallback_no_detector": sorted(no_blind_no_detector),
    "blind": blind,
    "default_hit_index": dh,
    "script_only_ids": sorted(r for r in id_set if r not in has_detector and r in script_ids),
}
with open(os.path.join(ROOT, "scripts", "_redline_coverage.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("\n[OK] 已写出 scripts/_redline_coverage.json")
