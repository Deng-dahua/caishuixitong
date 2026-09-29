# -*- coding: utf-8 -*-
"""反向验证：同源排查两道新闸门能真正报错（注入反模式 → 确认报错 → 复原）。

对应 audit_consistency.py 新增：
  · check_domain_missing_material_emits_finding  (A 类：缺主资料须产出资料缺失发现)
  · check_finding_level_legality                (D 类：风险发现 level 必须合法词表)

逻辑（与 _rev_validate_exemptions.py 同构）：
  1) 注入 bom_verify 静默 return 反模式 → 期望 A 闸门报错；
  2) 注入非法 level 风险发现字面量 → 期望 D 闸门报错；
  3) 复原（写回原文件 / 删除临时文件），再跑一次确认归零。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.audit_consistency import (
    check_domain_missing_material_emits_finding,
    check_finding_level_legality,
)

DA = os.path.join(ROOT, "engine", "domain_analysis.py")
TMP = os.path.join(ROOT, "engine", "_rev_tmp_finding.py")

ok = True


def _check(name, cond):
    global ok
    print(("  ✓ PASS " if cond else "  ✗ FAIL ") + name)
    if not cond:
        ok = False


print("═" * 70)
print("反向验证 1：A 闸门（缺主资料静默 return）")
print("═" * 70)
src0 = open(DA, encoding="utf-8").read()
silent_src = re.sub(
    r'    if not bom_data:\n        findings\.append\(\{"type": "资料缺失-BOM配方".*?\n        return findings\n',
    '    if not bom_data:\n        return findings\n',
    src0, count=1, flags=re.S,
)
if silent_src == src0:
    print("  ✗ FAIL 未能注入静默 return（标记不匹配，检查定位）")
    ok = False
else:
    try:
        open(DA, "w", encoding="utf-8").write(silent_src)
        res = check_domain_missing_material_emits_finding()
        _check("注入静默 return 后 A 闸门报错",
               any("bom_verify" in m for _, _, m in res))
    finally:
        open(DA, "w", encoding="utf-8").write(src0)  # 复原
    res2 = check_domain_missing_material_emits_finding()
    _check("复原后 A 闸门归零", len(res2) == 0)


print("═" * 70)
print("反向验证 2：D 闸门（风险发现非法 level）")
print("═" * 70)
tmp_body = (
    '# -*- coding: utf-8 -*-\n'
    '_x = {"type": "测试发现", "level": "未知级别", "detail": "d",\n'
    '      "description": "d", "tax_impact": "t", "suggestion": "s",\n'
    '      "category": "c"}\n'
)
try:
    open(TMP, "w", encoding="utf-8").write(tmp_body)
    res = check_finding_level_legality()
    _check("注入非法 level 风险发现后 D 闸门报错",
           any("_rev_tmp_finding.py" in m for _, _, m in res))
finally:
    if os.path.exists(TMP):
        os.remove(TMP)  # 复原
res2 = check_finding_level_legality()
_any_tmp = any("_rev_tmp_finding" in m for _, _, m in res2)
_check("复原后 D 闸门不再引用临时文件", not _any_tmp)

print("═" * 70)
print("反向验证 3：D 闸门不误报合法 level / 非风险形状")
print("═" * 70)
# 这些都不应被 D 闸门误报（合法 level / 缺六键）
safe_samples = [
    '{"type":"a","level":"中风险","detail":"d","description":"d","tax_impact":"t","suggestion":"s","category":"c"}',  # 合法
    '{"type":"优惠机会","level":"优惠机会","detail":"d","tax_benefit":"b","action":"a","law_ref":"l"}',                # 缺六键
    '{"confidence":0.5,"level":"高可信"}',                                                                          # 置信度
    '{"level":"错误","item":"x","detail":"d","suggestion":"s"}',                                                    # 评审(缺type)
]
TMP2 = os.path.join(ROOT, "engine", "_rev_tmp_safe.py")
open(TMP2, "w", encoding="utf-8").write("# -*- coding: utf-8 -*-\n" + "\n".join("_s%d = %s" % (i, s) for i, s in enumerate(safe_samples)) + "\n")
try:
    res = check_finding_level_legality()
    _check("合法/非风险形状不被 D 闸门误报", not any("_rev_tmp_safe.py" in m for _, _, m in res))
finally:
    if os.path.exists(TMP2):
        os.remove(TMP2)

print("═" * 70)
print("反向验证 4：章节模板去重闸门（P2-7）")
print("═" * 70)
from tools.audit_consistency import check_chapter_template_dedup
JS = os.path.join(ROOT, "static", "js", "tax-doc-analysis.js")
js0 = open(JS, encoding="utf-8").read()
try:
    # 注入反模式：移除前端对 action_plan_note 的渲染（模拟"抽出了却没显示"）
    broken = js0.replace("action_plan_note", "ACTIONNOTE_TOK")  # 不得含原串，否则 substring 检查仍为真
    open(JS, "w", encoding="utf-8").write(broken)
    res = check_chapter_template_dedup()
    _check("注入『未渲染 action_plan_note』后闸门报错",
           any("action_plan_note" in m for _, _, m in res))
finally:
    open(JS, "w", encoding="utf-8").write(js0)  # 复原
_CHECK = check_chapter_template_dedup()
_check("复原后模板去重闸门归零", len(_CHECK) == 0)

print("═" * 70)
print("反向验证 5：逐要件独立数据源闸门（#448）")
print("═" * 70)
import importlib
from tools.audit_consistency import check_constituent_sources_wiring
TR = os.path.join(ROOT, "engine", "tax_redlines.py")
RE = os.path.join(ROOT, "engine", "redline_engine.py")


def _fresh_gate():
    """闸门用 import 读 tax_redlines → 文件改动后须清缓存，否则读到的是旧模块。"""
    sys.modules.pop("engine.tax_redlines", None)
    return check_constituent_sources_wiring()


tr0 = open(TR, encoding="utf-8").read()
# 5a 注入长度错配：给 RL-VAT-007 的 constituent_sources 末尾多塞一项
try:
    broken = tr0.replace(
        '            "开票错误更正说明",    # ⑦ 正当情形（开票错误更正）\n        ],',
        '            "开票错误更正说明",    # ⑦ 正当情形（开票错误更正）\n            "多余项",\n        ],', 1)
    assert broken != tr0, "未能注入长度错配"
    open(TR, "w", encoding="utf-8").write(broken)
    res = _fresh_gate()
    _check("注入长度错配后闸门报错", any("长度" in m for _, _, m in res))
finally:
    open(TR, "w", encoding="utf-8").write(tr0)
# 5b 注入接线断裂：移除 redline_engine 里的 constituent_sources 传递（注入串不得含原串）
re0 = open(RE, encoding="utf-8").read()
try:
    broken2 = re0.replace('"constituent_sources": list(rl.get("constituent_sources") or []),',
                          "# ELIDED", 1)
    assert broken2 != re0, "未能注入接线断裂"
    open(RE, "w", encoding="utf-8").write(broken2)
    res = _fresh_gate()
    _check("注入接线断裂后闸门报错", any("redline_engine" in rel for _, rel, _ in res))
finally:
    open(RE, "w", encoding="utf-8").write(re0)
res2 = _fresh_gate()
_check("复原后数据源闸门归零", len(res2) == 0)

print("═" * 70)
print("总体:", "ALL PASS ✅" if ok else "HAS FAILURE ❌")
sys.exit(0 if ok else 1)
