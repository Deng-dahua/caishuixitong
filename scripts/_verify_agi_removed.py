# -*- coding: utf-8 -*-
"""移除 AGI 后：核对 company_1 的 ① 指标是否与移除前 AGI_OFF 基线一致，且 AGI 产物已消失。"""
import json
from collections import Counter

d = json.load(open("scripts/four_reports/company_1_full.json", encoding="utf-8"))
comp = d.get("comprehensive", {})
af = d.get("all_findings", [])
rd = comp.get("redline_detection", {}) if isinstance(comp, dict) else {}
sus = rd.get("suspicions", []) if isinstance(rd, dict) else []

print("=== ① 风险结论（移除后） ===")
print("总风险发现数     :", len(af))
print("红线怀疑项       :", len(sus))
print("带 redline_id    :", sum(1 for s in sus if s.get("redline_id")))
print("overall_level    :", d.get("overall_level"))
print("等级分布         :", dict(Counter(str(f.get("level")) for f in af)))

print("\n=== 基线（移除前 AGI_OFF）===")
print("总风险发现数     : 132")
print("红线怀疑项       : 22")
print("带 redline_id    : 22")
print("overall_level    : 已核定1项/待核131项")
print("等级分布         : {'中风险': 10, '低风险': 3, '待核验': 119}")

print("\n=== ① 一致性判定 ===")
ok_total = len(af) == 132
ok_sus = len(sus) == 22
ok_rl = sum(1 for s in sus if s.get("redline_id")) == 22
ok_lvl = dict(Counter(str(f.get("level")) for f in af)) == {"中风险": 10, "低风险": 3, "待核验": 119}
ok_overall = d.get("overall_level") == "已核定1项/待核131项"
print("发现数一致:", ok_total, "| 红线一致:", ok_sus, "| redline_id一致:", ok_rl,
      "| 等级一致:", ok_lvl, "| 总判定一致:", ok_overall)
print("① 完全一致:", all([ok_total, ok_sus, ok_rl, ok_lvl, ok_overall]))

print("\n=== AGI 产物已消失（应为 False / 0） ===")
print("agi_initialized          :", d.get("agi_initialized"))
print("_agi_report_level present:", "_agi_report_level" in d)
print("comprehensive._agi_meta  :", "_agi_meta" in comp if isinstance(comp, dict) else "?")
print("comprehensive.agi_meta   :", "agi_meta" in comp if isinstance(comp, dict) else "?")
print("counterfactual_analysis  :", "counterfactual_analysis" in comp if isinstance(comp, dict) else "?")
print("agi_generalization       :", "agi_generalization" in comp if isinstance(comp, dict) else "?")
agi_find = sum(1 for f in af if isinstance(f, dict) and any(str(k).startswith("_agi_") for k in f))
print("findings 带 _agi_* 数量  :", agi_find, "(应仅为核心 override_engine 的 _agi_override)")
