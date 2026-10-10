# -*- coding: utf-8 -*-
"""疑点5 · D11 收口（根因修复）：`argumentation.py` 里**所有**同形的重复赋值一并改。

★ 根因（对拍 + grep 实证）：§四 的「另有 N 项已提供同类资料」在 542 行，
  其上一行 `_vf = int(evidence.get('verify_count', 0) or 0)`（**元素数**）
  把我前段改好的 `_vf`（原子数 3）**覆盖回 1**；且该行**在文件里出现 2 次**。
  ⇒ 这次用 `replace(..., all)` **全部**改，不留漏网。

改法（只换取值优先级，不改任何判定）
------------------------------------
`_vf`/`_av` 优先读引擎层原子数权威 `*_atom_count`，字段缺失时回落到旧的
`verify_count`/`available_count`（**存量行为不变**）。
★ `_mc` 同理（若存在同形赋值也一并改）。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "argumentation.py")

PAIRS = [
    ("_vf",
     "    _vf = int(evidence.get('verify_count', 0) or 0)" + NL,
     "    # ★ 2026-08-05（疑点5 D11）：优先读**原子数权威**（与 §三 同源），缺失回落旧字段。" + NL +
     "    #   ⚠ 本行在文件里出现多次，**必须全部改**（否则后者覆盖前者，§四 又显示元素数）。" + NL +
     "    _vf = int(evidence.get('verify_atom_count')" + NL +
     "             if evidence.get('verify_atom_count') is not None" + NL +
     "             else evidence.get('verify_count', 0) or 0)" + NL),
    ("_av",
     "    _av = int(evidence.get('available_count', 0) or 0)" + NL,
     "    # ★ 2026-08-05（疑点5 D11）：同 _vf，优先读原子数权威（全量替换）。" + NL +
     "    _av = int(evidence.get('available_atom_count')" + NL +
     "             if evidence.get('available_atom_count') is not None" + NL +
     "             else evidence.get('available_count', 0) or 0)" + NL),
    ("_mc",
     "    _mc = int(evidence.get('missing_count', 0) or 0)" + NL,
     "    # ★ 2026-08-05（疑点5 D11）：同 _vf，优先读原子数权威（全量替换）。" + NL +
     "    _mc = int(evidence.get('missing_atom_count')" + NL +
     "             if evidence.get('missing_atom_count') is not None" + NL +
     "             else evidence.get('missing_count', 0) or 0)" + NL),
]

raw = io.open(P, "r", encoding="utf-8", newline="").read()
crlf = CRLF in raw
t = raw.replace(CRLF, NL)
total = 0
for tag, old, new in PAIRS:
    c = t.count(old)
    print("%s 命中 %d 处" % (tag, c))
    if c == 0:
        continue
    t = t.replace(old, new)          # ★ 全部替换
    total += c
if total == 0:
    print("!! 三种赋值都没找到 ⇒ 不写盘")
    sys.exit(2)
io.open(P, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
print("[DONE] 共改 %d 处（含重复赋值）" % total)
