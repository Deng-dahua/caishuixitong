# -*- coding: utf-8 -*-
"""疑点6 幽灵名收口：§四「尚缺」**追加具体材料名**（保留类别级，不破不变量）。

★ 为什么不能换字段（上一次试改的实测结论）
  把 `_mm` 换成 `missing_material_names` ⇒ 写盘/编译/真跑都过，但**闸门 7 ERROR**
  ⇒ `missing_materials`（类别级）被**剔除判定与不变量**依赖，二者不可互换。

★ 本次做法（最小、零风险）
  `_mn`（名称级）本来就已经取到（543 行），只是 `_mm` 非空时**没用它**。
  现在：类别级列表**照旧**，后面**追加**具体材料名 ⇒ 读者既知类别、也知道要交哪几份。

纪律：OLD/NEW 用**单行常量**，注释放行尾。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "argumentation.py")

OLD = '        _mat_txt += "；尚缺：" + "、".join(str(m) for m in _mm[:6])'
NEW = '        _mat_txt += "；尚缺：" + "、".join(str(m) for m in _mm[:6]) + (("（具体材料：" + "、".join(str(m) for m in _mn[:6]) + "）") if _mn else "")  # ★疑点6 D10：类别级后补具体名'

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
print("[DONE] 疑点6 幽灵名已收口（类别级 + 具体名并存）")
