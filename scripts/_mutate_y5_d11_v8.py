# -*- coding: utf-8 -*-
"""方案 A（正确落点）：业态剔除下沉到引擎层。

★ 前几次失败与本版做法
  - 失败①：锚点选在 `return {…}` 字典内部 ⇒ `if` 语句落进 dict ⇒ SyntaxError
  - 失败②：锚点 `    return {` 在文件里有 **3 处** ⇒ 唯一性校验拦下（无损坏）
  - 失败③：锚点带了错误的空行数 ⇒ 命中 0 ⇒ 拦下（无损坏）
  - 本版：锚点 = `rebuttal_status = "…不足以排除本项涉嫌风险"`（`grep -c` 确认**只出现 1 次**），
    插在它**之后**（= `return {` 之前，函数级缩进 4）。

作用
----
`elements` 构造完成、`_na_docs` 就绪后、**return 之前**，把元素名里**本业态天然不适用的段**
剔掉（唯一权威 `_na_docs` = `industry_resolver.not_required_materials`）
⇒ `ev["elements"]` 的名字**本身就是剔除后的**
⇒ §三（报告层）与 §四（引擎层论证）看到**同一份** ⇒ 原子数必然一致（疑点3/5 D11）。

★ 反证（role=反证）**不剔**：它是正当理由，不是企业要交的材料。
★ 剔空则**保留原名**，不制造空名。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "evidence_chain.py")

ANCHOR = (
    '        rebuttal_status = "企业尚未提交正当理由的书面证明，'
    '现有资料不足以排除本项涉嫌风险"' + NL
)

BLOCK_LINES = [
    "",
    "    # ★★ 2026-08-05（疑点3/5 D11 收口，方案 A）：**业态剔除下沉到引擎层**。",
    "    #   根因：§三 的元素名经**报告层** `_nr_el` 重写、§四 用**引擎层原名**",
    "    #   ⇒ 同一页两个数（§三「同类 3」/§四「同类 1」）；报告层 in-place 写回对 §四 无效（时序）。",
    "    #   现改为：**在引擎层就剔除**（唯一权威 `_na_docs`）⇒ 两边看到同一份名字，原子数必然一致。",
    "    #   ⚠ 反证（role=反证）不剔：它是正当理由，不是企业要交的材料；剔空则保留原名。",
    "    if _na_docs:",
    "        for _e8 in elements:",
    "            if not isinstance(_e8, dict) or _e8.get(\"role\") == \"反证\":",
    "                continue",
    "            _n8 = str(_e8.get(\"name\") or \"\")",
    "            if not _n8:",
    "                continue",
    "            for _m8 in _na_docs:",
    "                if _m8 and _m8 in _n8:",
    "                    _n8 = _n8.replace(_m8, \"\")",
    "            _n8 = _n8.strip(\"、，,；; /（ ）()\")",
    "            if _n8 and _n8 != _e8.get(\"name\"):",
    "                _e8[\"name\"] = _n8",
]
BLOCK = NL.join(BLOCK_LINES) + NL

raw = io.open(P, "r", encoding="utf-8", newline="").read()
crlf = CRLF in raw
t = raw.replace(CRLF, NL)

if "_e8" in t:
    print("SKIP 已在（幂等）")
    sys.exit(0)

c = t.count(ANCHOR)
print("锚点命中 =", c)
if c != 1:
    print("!! 锚点不唯一/未找到 ⇒ 不写盘")
    sys.exit(2)

# 块插到锚点行之后（= return { 之前）；BLOCK 自带前导空行
t = t.replace(ANCHOR, ANCHOR + BLOCK, 1)

# 自检：插入后 `if _na_docs:` 必须位于 `return {` 之前且在函数级缩进
i_blk = t.index("        for _e8 in elements:")
i_ret = t.index(ANCHOR) + len(ANCHOR)
if not (i_ret <= i_blk):
    print("!! 插入位置在 return 之后 ⇒ 撤销")
    sys.exit(3)

io.open(P, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
print("[DONE] 业态剔除已下沉到引擎层（return 之前）")
