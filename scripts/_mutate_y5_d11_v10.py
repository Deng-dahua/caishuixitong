# -*- coding: utf-8 -*-
"""疑点5 · D11 根因修复：`argumentation.py:542` 的**第二次赋值**把权威值覆盖回旧口径。

★ 根因（对拍 + grep 定位）：我在函数前段把 `_av/_vf/_mc` 改成读引擎层原子数权威，
  但**同一函数更靠后还有一处重新赋值**：
      `_vf = int(evidence.get('verify_count', 0) or 0)`   ← verify_count 是**元素数**
  它把我的 `_vf`（`verify_atom_count` = 3）**覆盖回 1** ⇒ §四 显示 1。
  这就是"改了没生效"的第 4 种形态：**同函数内重复赋值，后者覆盖前者**。

修法：把该行改为**优先读原子数权威**、缺失时回落到旧字段。
★ 不动 `_mm`/`_mc` 的后续用法，不改任何判定。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "argumentation.py")

OLD = "    _vf = int(evidence.get('verify_count', 0) or 0)" + NL
NEW = (
    "    # ★ 2026-08-05（疑点5 D11 根因）：本行是**同函数内的第二次赋值**，会覆盖前面" + NL +
    "    #   已改好的 `_vf`（原子数权威）⇒ §四 显示 1 而 §三 显示 3（D11）。" + NL +
    "    #   改为：优先读 `verify_atom_count`（引擎层原子数权威，与 §三 同源），" + NL +
    "    #   缺失时回落到旧的 `verify_count`（元素数，存量行为不变）。" + NL +
    "    _vf = int(evidence.get('verify_atom_count')" + NL +
    "             if evidence.get('verify_atom_count') is not None" + NL +
    "             else evidence.get('verify_count', 0) or 0)" + NL
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
print("[DONE] §4 同类计数已改读原子数权威")
