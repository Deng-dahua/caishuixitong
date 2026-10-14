# -*- coding: utf-8 -*-
"""疑点6 最后一项：幽灵类别名「合同文件」修掉（正文改为使用**具体材料名**）。

★ 根因（读码确认）
  · `argumentation.py:359-388`（2026-10-04 用户复核疑点6 D11/D13）**已修过**「补充提供」，
    改成只列**证据角色名** ⇒ §五 建议已是名称级 ✅；
  · 但 **同文件 532 行**（§四 的"就资料来说…"材质句）仍用
    `_mm = evidence.get('missing_materials') or []`
    —— `missing_materials` 是**15 类类别名**（"劳动合同"按关键词归入"合同文件"）
    ⇒ 读者在正文看到「补充提供**合同文件**」，而真正缺的是「**劳动合同与用工名册**」。

修法（零风险、一行）
------------------
`_mm` **优先**取名称级 `missing_material_names`（今天已加的字段），
缺失时才回落到类别级 `missing_materials`（存量行为不变）。
不动任何判定、不动 §五。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "argumentation.py")

OLD = "    _mm = evidence.get('missing_materials') or []" + NL
NEW = (
    "    # ★★ 2026-10-05（疑点6 幽灵类别名）：**优先用具体材料名**，避免正文出现 15 类类别名。" + NL +
    "    #   实测事故：本疑点正文出现「补充提供**合同文件**」，而真正缺的是「**劳动合同与用工名册**」" + NL +
    "    #   （「劳动合同」按关键词被归入「合同文件」类别）⇒ 类别名与「企业该交的那份材料」不是一回事。" + NL +
    "    #   同文件 359-388（§五 建议）早已改用证据角色名；此处是**同一问题的另一处出口**。" + NL +
    "    #   名称级字段缺失时回落到旧字段（存量行为不变）。" + NL +
    "    _mm = (evidence.get('missing_material_names') or evidence.get('missing_materials') or [])" + NL
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
print("[DONE] 疑点6 幽灵类别名已修（正文改用具体材料名）")
