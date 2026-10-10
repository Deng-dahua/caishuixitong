# -*- coding: utf-8 -*-
"""方案 A（重做）：业态剔除下沉到引擎层 —— 插在 **`return {` 之前**（函数级语句边界）。

★ 上一版失败原因：插在 `"available_count": sum(...)` 之前，而那行**在 return 字典字面量内部**
  ⇒ `if` 语句出现在 dict 里 ⇒ SyntaxError。
★ 本版锚点 `    return {` 是**函数级语句**（缩进 4，其前是 `rebuttal_status = ...` 赋值）⇒ 安全。
  按纪律：先 `py_compile` → 再真跑 → 再闸门 → 最后才汇报。

作用
----
`elements` 构造完成、`_na_docs` 就绪后、**return 之前**，把元素名里**本业态天然不适用的段**
剔掉（唯一权威 `_na_docs` = `industry_resolver.not_required_materials`）
⇒ `ev["elements"]` 的名字**本身就是剔除后的**，
   §三（报告层）与 §四（引擎层论证）看到**同一份** ⇒ 原子数必然一致（疑点3/5 D11）。
★ 反证（role=反证）**不剔**：它是正当理由，不是企业要交的材料。
★ 剔除后为空则**保留原名**（不制造空名）。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "evidence_chain.py")

ANCHOR = (
    '        rebuttal_status = "企业尚未提交正当理由的书面证明'
    + "，现有资料不足以排除本项涉嫌风险"
    + NL + NL + '    return {' + NL)
BLOCK = (
    "    # ★★ 2026-08-05（疑点3/5 D11 收口，方案 A）：**业态剔除下沉到引擎层**。" + NL +
    "    #   根因：§三 的元素名经**报告层** `_nr_el` 重写、§四 用**引擎层原名**" + NL +
    "    #   ⇒ 同一页两个数（§三「同类 3」/§四「同类 1」）；报告层 in-place 写回对 §四 无效（时序）。" + NL +
    "    #   现改为：**在引擎层就剔除**（唯一权威 `_na_docs`）⇒ 两边看到同一份名字，原子数必然一致。" + NL +
    "    #   ⚠ 反证（role=反证）不剔：它是正当理由，不是企业要交的材料。" + NL +
    "    #   ⚠ 剔空则保留原名，不制造空名。" + NL +
    "    if _na_docs:" + NL +
    "        for _e8 in elements:" + NL +
    "            if not isinstance(_e8, dict) or _e8.get(\"role\") == \"反证\":" + NL +
    "                continue" + NL +
    "            _n8 = str(_e8.get(\"name\") or \"\")" + NL +
    "            if not _n8:" + NL +
    "                continue" + NL +
    "            for _m8 in _na_docs:" + NL +
    "                if _m8 and _m8 in _n8:" + NL +
    "                    _n8 = _n8.replace(_m8, \"\")" + NL +
    "            _n8 = _n8.strip(\"、，,；; /（ ）()\")" + NL +
    "            if _n8 and _n8 != _e8.get(\"name\"):" + NL +
    "                _e8[\"name\"] = _n8" + NL
)

raw = io.open(P, "r", encoding="utf-8", newline="").read()
crlf = CRLF in raw
t = raw.replace(CRLF, NL)
c = t.count(ANCHOR)
print("锚点 '    return {' 命中 =", c)
if c != 1:
    print("!! 锚点异常 ⇒ 不写盘")
    sys.exit(2)
t = t.replace(ANCHOR, BLOCK + ANCHOR, 1)
io.open(P, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
print("[DONE] 业态剔除已下沉（return 之前）")
