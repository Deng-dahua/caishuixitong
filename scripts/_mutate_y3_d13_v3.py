# -*- coding: utf-8 -*-
"""疑点3 · D13：缺料口径统一（两处根因一起收口）。

根因① `evidence_chain` 只登记**能归入已知类别**的缺失材料 ⇒ 疑点3 的
     「销售台账、发货记录」「客户对账单与询证函回函」归不了任何类别 ⇒
     `missing_materials` 与 `missing_material_names` **都空**，而 §三 文案列的是
     "证据链里状态=缺失的全部元素" ⇒ **字段空 ≠ 文案错**，是"未归类材料"两边都不管。
     修法：**归不了类的缺失证据也要登记具体名**（不做类别归一，业态剔除照常按名判）。

根因② §三 与 §四 **同一批数据、两种计数单位**：§三 按**材料名**（复合名拆开去重 ⇒ 4），
     §四 按 `missing_count`（**证据元素个数** ⇒ 3）⇒ 同一页两个数。
     修法：§四 优先用 `missing_material_names` 并**同样按材料名计**。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)


def swap(path, pairs):
    p = os.path.join(ROOT, path)
    raw = io.open(p, "r", encoding="utf-8", newline="").read()
    crlf = CRLF in raw
    t = raw.replace(CRLF, NL)
    for _i, _p in enumerate(pairs):
        tag, old, new = (_p if len(_p) == 3 else (str(_i + 1), _p[0], _p[1]))
        c = t.count(old)
        if c != 1:
            print("!! %s 命中 %d 次" % (tag, c))
            sys.exit(2)
        t = t.replace(old, new, 1)
    io.open(p, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
    print("OK " + path)


# ══ 根因①：未归类的缺失证据也登记具体名 ══════════════════════════════
OLD1 = (
    "        for category, keywords in _MATERIAL_KEYWORDS:" + NL +
    "            if not any(kw in text for kw in keywords):" + NL +
    "                continue" + NL +
    "            forms = [category] + list(_EQUIVALENT_CATEGORIES.get(category, []))"
)
NEW1 = (
    "        _cls = False" + NL +
    "        for category, keywords in _MATERIAL_KEYWORDS:" + NL +
    "            if not any(kw in text for kw in keywords):" + NL +
    "                continue" + NL +
    "            _cls = True" + NL +
    "            forms = [category] + list(_EQUIVALENT_CATEGORIES.get(category, []))"
)
OLD2 = (
    "            if text and text not in names_bucket:" + NL +
    "                names_bucket.append(text)"
)
NEW2 = (
    "            if text and text not in names_bucket:" + NL +
    "                names_bucket.append(text)" + NL +
    "        # ★★ 2026-10-04（疑点3 D13）：**归不了类的缺失证据也要登记具体名**。" + NL +
    "        #   旧实现只登记能归入 `_MATERIAL_KEYWORDS` 已知类别的材料名；疑点3 的" + NL +
    "        #   「销售台账、发货记录」「客户对账单与询证函回函」归不了任何类别 ⇒ 两个字段都空，" + NL +
    "        #   而 §三 文案列的是全部缺失元素 ⇒ 字段与文案口径分裂。" + NL +
    "        #   这里**不做类别归一**（`missing_materials` 仍只收已归类项，语义不变），" + NL +
    "        #   只把**具体名**补进 `missing_material_names`；业态剔除照常按名判。" + NL +
    "        if (not _cls) and text and text not in names_bucket:" + NL +
    "            names_bucket.append(text)"
)
swap("engine/evidence_chain.py", [(OLD1, NEW1), (OLD2, NEW2)])

# ══ 根因②：§四 与 §三 同口径（都按材料名计）═══════════════════════════
OLD3 = (
    "    if _mm:" + NL +
    "        _mat_txt += \"；尚缺：\" + \"、\".join(str(m) for m in _mm[:6])" + NL +
    "    elif _mc:" + NL +
    "        _mat_txt += f\"；还缺{_mc}项\""
)
NEW3 = (
    "    _mn = evidence.get('missing_material_names') or []" + NL +
    "    if _mm:" + NL +
    "        _mat_txt += \"；尚缺：\" + \"、\".join(str(m) for m in _mm[:6])" + NL +
    "    elif _mn:" + NL +
    "        # ★ 2026-10-04（疑点3 D13）：与 §三 **同一计数单位**（材料名，复合名拆开去重）。" + NL +
    "        #   旧实现用 `missing_count`（**证据元素个数**）⇒ 同一页 §三 4 项 / §四 3 项。" + NL +
    "        import re as _r9" + NL +
    "        _at = []" + NL +
    "        for _x9 in _mn:" + NL +
    "            for _y9 in _r9.split(r\"[、，,；;／/]|与|和|及|以及|或\", str(_x9)):" + NL +
    "                _y9 = _y9.strip()" + NL +
    "                if _y9 and _y9 not in _at:" + NL +
    "                    _at.append(_y9)" + NL +
    "        if _at:" + NL +
    "            _mat_txt += \"；还缺%d项（%s）\" % (len(_at), \"、\".join(_at[:6]))" + NL +
    "        else:" + NL +
    "            _mat_txt += f\"；还缺{_mc}项\""
)
swap("engine/argumentation.py", [(OLD3, NEW3)])
print("DONE")
