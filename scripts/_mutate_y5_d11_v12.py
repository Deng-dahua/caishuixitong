# -*- coding: utf-8 -*-
"""疑点5 · D11 收口：5 处同形赋值**全部单行**替换（不破坏 `if/else` body 缩进）。

★ 前 4 次失败与本次做法
  - ① 回填落在 `_clue_narrative`(2667) 之后 ⇒ 文本已固化 → 移到渲染之前（已做，方案 A 之后）
  - ②③④ 锚点选在 dict 内部 / 命中 3 次 / 空行不符 → 唯一性校验拦下（无损坏）
  - ④ 多行替换破坏 `if/else` 单行 body 缩进 → IndentationError（已回退）
  - **本次：只改单行，缩进结构完全不动**，并 `replace(all)` 覆盖全部 5 处。

前提（均已实证）
------------------
方案 A 已落地（业态剔除下沉引擎层）；`_atoms_count` 与 §三 `_atoms_of` 算法一致；
`verify_atom_count = 3`（对拍 YPAI2 证实）⇒ §四 读到它就应显示 3。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "argumentation.py")

# (旧行, 新行) —— 全部保持**单行**，缩进与原行完全一致
PAIRS = [
    ("    _vf = int(evidence.get('verify_count', 0) or 0)",
     "    _vf = int(evidence.get('verify_atom_count') if evidence.get('verify_atom_count') is not None else evidence.get('verify_count', 0) or 0)  # ★D11 原子数权威（单行·全量）"),
    ("    _av = int(evidence.get('available_count', 0) or 0)",
     "    _av = int(evidence.get('available_atom_count') if evidence.get('available_atom_count') is not None else evidence.get('available_count', 0) or 0)  # ★D11 原子数权威（单行·全量）"),
    ("    _mc = int(evidence.get('missing_count', 0) or 0)",
     "    _mc = int(evidence.get('missing_atom_count') if evidence.get('missing_atom_count') is not None else evidence.get('missing_count', 0) or 0)  # ★D11 原子数权威（单行·全量）"),
]

raw = io.open(P, "r", encoding="utf-8", newline="").read()
crlf = CRLF in raw
t = raw.replace(CRLF, NL)
total = 0
for old, new in PAIRS:
    c = t.count(old)
    print("命中 %d 处 : %s" % (c, old.strip()[:56]))
    if c == 0:
        continue
    t = t.replace(old, new)      # ★ 全量替换，单行
    total += c
if total == 0:
    print("!! 一处都没命中 ⇒ 不写盘")
    sys.exit(2)
io.open(P, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
print("[DONE] 共改 %d 处（全部单行）" % total)
