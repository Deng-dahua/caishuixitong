# -*- coding: utf-8 -*-
"""疑点2 D12（双字段改法）：`missing_materials` 保持**类别级**（供业态剔除与计数），
另加 `missing_material_names`（**具体材料名**，给企业看"要补哪几样"）。

为什么是双字段而不是直接换粒度（上一版撞墙的实测教训）：
  · 直接把 `missing_materials` 换成具体名 ⇒ 下游「建议文案」聚合把
    **本业态不适用**的具体名（入库验收单/出库单）写进文案 ⇒ 业态闸门 3 项 ERROR；
    且 `test_verify_and_missing_separated` 锁定类别粒度 ⇒ 1 failed。
  · 双字段则：剔除与计数的**口径不动**（零回归），企业侧另拿到具体名。

本改动**不触碰** `suggestion` / `narrative_paragraphs` 等被闸门扫描的文案，
只新增结构化字段（业态剔除照旧走 `_filter_not_required`）。

★ 文案不含 ASCII 引号。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)
CRLF = chr(13) + chr(10)


def swap(path, pairs):
    p = os.path.join(ROOT, path)
    raw = io.open(p, "r", encoding="utf-8", newline="").read()
    crlf = CRLF in raw
    t = raw.replace(CRLF, NL)
    for tag, old, new in pairs:
        c = t.count(old)
        if c != 1:
            print("!! %s 命中 %d 次（应为 1）" % (tag, c))
            sys.exit(2)
        t = t.replace(old, new, 1)
    io.open(p, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
    print("OK %s (%d处)" % (path, len(pairs)))


EC = "engine/evidence_chain.py"
swap(EC, [
    ("声明两个清单",
     '    missing_materials: List[str] = []' + NL +
     '    verify_materials: List[str] = []',
     '    missing_materials: List[str] = []' + NL +
     '    verify_materials: List[str] = []' + NL +
     '    # ★★ 2026-10-04（疑点2 D12，双字段）：**具体材料名**清单（面向企业"要补哪几样"）。' + NL +
     '    #   `missing_materials` 保持**类别级**不动 —— 它是业态剔除与计数的口径，' + NL +
     '    #   换成具体名会让下游建议文案把本业态不适用的具体名写进去（实测 3 项 ERROR）' + NL +
     '    #   并打破 `test_verify_and_missing_separated` 的粒度锁定。' + NL +
     '    #   两个字段并存：**口径用类别、表达用具体名**，互不干扰。' + NL +
     '    missing_material_names: List[str] = []' + NL +
     '    verify_material_names: List[str] = []'),
    ("逐条追加具体名",
     '        bucket = verify_materials if e["status"] == "待核" else missing_materials' + NL +
     '        text = e["name"]',
     '        bucket = verify_materials if e["status"] == "待核" else missing_materials' + NL +
     '        names_bucket = (verify_material_names if e["status"] == "待核"' + NL +
     '                        else missing_material_names)' + NL +
     '        text = e["name"]'),
    ("append 处并列追加",
     '            bucket.append(category)',
     '            bucket.append(category)' + NL +
     '            if text and text not in names_bucket:' + NL +
     '                names_bucket.append(text)'),
    ("返回体带上新字段",
     '        "missing_materials": missing_materials,',
     '        "missing_materials": missing_materials,' + NL +
     '        "missing_material_names": missing_material_names,' + NL +
     '        "verify_material_names": verify_material_names,'),
])

RE = "engine/redline_engine.py"
swap(RE, [
    ("透传新字段",
     '            "missing_materials": list(ev.get("missing_materials") or []),',
     '            "missing_materials": list(ev.get("missing_materials") or []),' + NL +
     '            # ★ 2026-10-04（疑点2 D12 双字段）：具体材料名一并透传（口径仍用类别级）' + NL +
     '            "missing_material_names": list(ev.get("missing_material_names") or []),' + NL +
     '            "verify_material_names": list(ev.get("verify_material_names") or []),'),
])

ER = "engine/enterprise_report.py"
swap(ER, [
    ("报告层输出新字段",
     '            "missing_materials": _filter_not_required(s.get("missing_materials"), not_required_docs),',
     '            "missing_materials": _filter_not_required(s.get("missing_materials"), not_required_docs),' + NL +
     '            # ★ 2026-10-04（疑点2 D12）：**具体材料名**（面向企业要补哪几样）。' + NL +
     '            #   业态剔除与计数仍用上面的类别级字段，此字段只负责表达，故同样过一遍剔除。' + NL +
     '            "missing_material_names": _filter_not_required(' + NL +
     '                s.get("missing_material_names") or [], not_required_docs),'),
])
