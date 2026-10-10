# -*- coding: utf-8 -*-
"""方案 A：把**业态剔除下沉到引擎层**（疑点3/5 D11 收口）。

根因（print 实证）：§三 的 verify 元素名经过**报告层** `_nr_el` 业态剔除重写，
§四 用的是**引擎层原名** ⇒ 同一页 §三「同类 3 项」/§四「同类 1 项」。
`_nr_el` 改成 in-place 写回也无效——§四 文本在引擎层 `build_argumentation` 生成，
**早于**报告层的写回（与 D6 的 2667 教训同源）。

修法
----
在 `build_evidence_chain` 里、`elements` 建成后立刻做**段级业态剔除**
（唯一权威 `_na_docs` = `industry_resolver.not_required_materials`，该作用域已有）
⇒ `ev["elements"]` 的名字**本身就是剔除后的**，
   §三 与 §四 看到**同一份** ⇒ 原子数必然一致。
★ 反证（role=反证）**不剔**（它是正当理由，不是企业要交的材料）。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "evidence_chain.py")

OLD = '        "available_count": sum(1 for e in elements if e["status"] == "已有"),' + NL
NEW = (
    '        # ★★ 2026-08-05（疑点3/5 D11 收口）：**业态剔除下沉到引擎层**。' + NL +
    '        #   根因：§三 的元素名经**报告层** `_nr_el` 重写，§四 用**引擎层原名**' + NL +
    '        #   ⇒ 同一页两个数（§三 3 / §四 1）；报告层 in-place 写回对 §四 无效（时序）。' + NL +
    '        #   现改为：**在引擎层就剔除**本业态天然不适用的段（唯一权威 `_na_docs`）' + NL +
    '        #   ⇒ 两边看到同一份名字，原子数必然一致。' + NL +
    '        #   ⚠ 反证（role=反证）不剔：它是正当理由，不是企业要交的材料。' + NL +
    '        if _na_docs:' + NL +
    '            for _e7 in elements:' + NL +
    '                if not isinstance(_e7, dict) or _e7.get("role") == "反证":' + NL +
    '                    continue' + NL +
    '                _n7 = str(_e7.get("name") or "")' + NL +
    '                if not _n7:' + NL +
    '                    continue' + NL +
    '                for _m7 in _na_docs:' + NL +
    '                    if _m7 and _m7 in _n7:' + NL +
    '                        _n7 = _n7.replace(_m7, "")' + NL +
    '                _n7 = _n7.strip("、，,；; /")' + NL +
    '                if _n7 and _n7 != _e7.get("name"):' + NL +
    '                    _e7["name"] = _n7' + NL +
    OLD
)

raw = io.open(P, "r", encoding="utf-8", newline="").read()
crlf = CRLF in raw
t = raw.replace(CRLF, NL)
c = t.count(OLD)
print("锚点命中 =", c)
if c != 1:
    print("!! 锚点异常 ⇒ 不写盘")
    sys.exit(2)
t = t.replace(OLD, NEW, 1)
io.open(P, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
print("[DONE] 业态剔除已下沉到引擎层")
