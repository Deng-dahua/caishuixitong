# -*- coding: utf-8 -*-
"""疑点2 收口：把「如实缺料」变成**可执行的补资料清单**（接在 §五 需企业提供的资料与说明）。

做法（新增一段能力，不改任何既有判定/文案）：
  新函数 `_supplement_table()`：按 **具体材料名** 聚合成清单表，列
    ① 资料名称（具体，面向企业）
    ② 关联的未核对要件（第X条）
    ③ 补齐后可核什么（要件原文，截断）
    ④ 依赖度（多少条要件卡在这个资料上 ⇒ 优先级）
  并挂进 §五 的 `detail_table`。

为什么落在 §五：那一节的语义就是"企业要交什么"，清单表是它的自然载体；
**不改动** §三/§五 的既有文案（闸门扫描 suggestion/叙事段落，动文案风险高）。

数据来源全部是既有字段的组合，**无新判定**：
  · 具体材料名 ← `missing_material_names`（D12 双字段，本次刚加）
  · 未核对要件 ← `checkpoint_table`（构成要件独立核对表）的行
  · 业态剔除 ← 同一 `not_required` 权威

★ 文案不含 ASCII 引号（今天栽过多次）。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "enterprise_report.py")

HELPER = '''def _supplement_table(cp_tbl: Optional[Dict], names: List[str],
                      not_required: Optional[List[str]] = None) -> Optional[Dict]:
    """补资料清单表：按**具体材料名**聚合，标出关联的未核对要件与补齐后可核什么。

    ★ 2026-10-04（疑点2 收口）：把 91 条「如实缺料」变成可执行清单。
      之前只说"缺料"，企业不知道**先补哪一份、补完能核出什么**。
      本表回答三问：缺哪几份（具体名）／卡住哪些要件／补完能核什么。

    `cp_tbl` ＝ 构成要件独立核对表（`constituent_checkpoint.checkpoint_table`）。
    `names`   ＝ 该疑点的**具体材料名**（`missing_material_names`）。
    依赖度 = 卡在该资料上的未核对要件条数（= 补它的收益），按此降序 ⇒ 天然优先级。
    """
    _nr = [str(x) for x in (not_required or []) if str(x).strip()]
    _names = []
    for n in (names or []):
        n = str(n or "").strip()
        if not n or n in _names:
            continue
        # 业态不适用：宁可不出（企业天然不会有，要了也白要）
        if _nr and any((n == _m) or (_m in n) for _m in _nr):
            continue
        _names.append(n)
    if not _names:
        return None
    _rows_cp = ((cp_tbl or {}).get("rows") or []) if isinstance(cp_tbl, dict) else []
    out_rows = []
    for _n in _names:
        _hit = []
        for _r in _rows_cp:
            if not isinstance(_r, dict):
                continue
            _src = str(_r.get("独立数据源") or "")
            _st = str(_r.get("数据源状态") or "")
            _cc = str(_r.get("核对结论") or "")
            if "未取得" not in _st and "待核" not in _st and "未单独核对" not in _cc:
                continue
            if not _src:
                continue
            if _n == _src or _n in _src or _src in _n:
                _hit.append(_r)
        _seqs = "、".join(str(_r.get("要件序号") or "") for _r in _hit[:4]) or "—"
        _what = "；".join(str(_r.get("构成要件") or "") for _r in _hit[:2])
        if len(_what) > 56:
            _what = _what[:56] + "…"
        out_rows.append({
            "待补资料（具体名称）": _n,
            "关联未核对要件": _seqs,
            "补齐后可核什么": _what or "—",
            "依赖度（条）": len(_hit),
        })
    if not out_rows:
        return None
    out_rows.sort(key=lambda r: -int(r["依赖度（条）"]))
    return {
        "title": "补资料清单（按具体材料名，先补依赖度多的）",
        "columns": ["待补资料（具体名称）", "关联未核对要件", "补齐后可核什么", "依赖度（条）"],
        "rows": out_rows,
        "scope_note": ("本清单只列**具体材料名**；已剔除本业态天然不适用的资料；"
                       "依赖度＝卡在该资料上的未核对要件条数，越多越应先补。"),
    }


'''

ANCHOR = 'def _evidence_table('
OLD_SEC5 = (
    '            {"heading": "五、需企业提供的资料与说明", "text": _naturalize_report_text(p5_lead),\n'
    '             "bullets": bullets5 or None, "tail": tail5},'
)
NEW_SEC5 = (
    '            {"heading": "五、需企业提供的资料与说明", "text": _naturalize_report_text(p5_lead),\n'
    '             "bullets": bullets5 or None, "tail": tail5,\n'
    '             # ★ 2026-10-04（疑点2 收口）：补资料清单（具体材料名 + 关联未核对要件 + 依赖度）\n'
    '             "detail_table": _supplement_table(\n'
    '                 _cp_tbl, s.get("missing_material_names") or [], not_required_docs)},'
)

raw = io.open(P, "r", encoding="utf-8", newline="").read()
crlf = CRLF in raw
t = raw.replace(CRLF, NL)
for tag, old, new in (("helper 插入", ANCHOR, HELPER + ANCHOR),
                      ("§五 挂表", OLD_SEC5, NEW_SEC5)):
    c = t.count(old)
    if c != 1:
        print("!! %s 命中 %d 次（应为 1）" % (tag, c))
        sys.exit(2)
    t = t.replace(old, new, 1)
io.open(P, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
print("OK 补资料清单已落地（_supplement_table + §五 挂表）")
