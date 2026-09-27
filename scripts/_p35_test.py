# -*- coding: utf-8 -*-
"""P3.5 端到端验证 v4：补充资料上传→识别→证据链状态翻转(缺失→已有)。"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.material_recognition import _SUPPLEMENTARY_RECOGNITION, _SUPPLEMENTARY_CATEGORIES
from engine.tax_redlines import all_redlines
from engine.enterprise_report import _doc_covered_categories
from engine.evidence_chain import build_evidence_chain
from openpyxl import Workbook
from main import _parse_excel_structured

# 找一个红线：证据链模板 element name 命中补充类别且角色非反证（驱动"已有/缺失"状态）
target = None
for rl in all_redlines():
    for it in (rl.get("evidence_chain") or []):
        nm = str(it.get("name") or "")
        if nm in _SUPPLEMENTARY_CATEGORIES and str(it.get("role") or "") != "反证":
            target = (rl, nm)
            break
    if target:
        break
assert target, "未找到可用红线"
rl, M = target
print("[*] 红线:", rl["id"], rl["name"], "| 证据链点名:", M)
doc_type = _SUPPLEMENTARY_RECOGNITION[M]["doc_type"]

# ① 真实文件上传解析
wb = Workbook(); ws = wb.active; ws.append(["项目", "数值"]); ws.append(["测试", 1])
fd, path = tempfile.mkstemp(suffix=".xlsx"); os.close(fd); wb.save(path)
res = _parse_excel_structured(path, ".xlsx", M + ".xlsx")
print("[1] 上传'%s.xlsx' → type=%s (期望 %s)" % (M, (res or {}).get("type"), doc_type))
assert (res or {}).get("type") == doc_type
os.remove(path)

# ② 类别进入 provided
cov = _doc_covered_categories({"file_results": [{"type": doc_type}]})
print("[2] 类别进入 provided:", M in cov)

# ③ 证据链状态翻转（核心诚实判定：逐字命中=已有）
f = {"type": "P35", "redline_id": rl["id"]}
ev0 = build_evidence_chain(f, rl, [], {})
ev1 = build_evidence_chain(f, rl, [M], {})
st0 = next((e["status"] for e in ev0["elements"] if e["name"] == M), None)
st1 = next((e["status"] for e in ev1["elements"] if e["name"] == M), None)
print("[3] 未上传状态=%s | 上传后状态=%s" % (st0, st1))
print("[4] 结论:", "PASS ✅ 上传后由'缺失'翻转为'已有'" if st0 == "缺失" and st1 == "已有"
      else "FAIL ❌ 状态未翻转 (%s→%s)" % (st0, st1))

# ⑤ 正常发票不被误吞为补充类别
wb2 = Workbook(); ws2 = wb2.active; ws2.append(["购方名称", "金额", "税率"]); ws2.append(["甲", 1000, 0.13])
fd2, p2 = tempfile.mkstemp(suffix=".xlsx"); os.close(fd2); wb2.save(p2)
r2 = _parse_excel_structured(p2, ".xlsx", "销项发票2024.xlsx")
print("[5] 上传'销项发票2024.xlsx' → type=%s | 误吞? %s" % ((r2 or {}).get("type"), str((r2 or {}).get("type")).startswith("sup_")))
os.remove(p2)
