# -*- coding: utf-8 -*-
"""疑点6 幽灵类别名：正文（§四 材质句）禁用资料类别名，优先用具体材料名。

★ 纪律（今晚 6 次返工的共同技术原因，此处严格执行）：
  OLD/NEW 一律用**单行字符串常量**，注释放代码**行尾**，
  不做多行字符串拼接、不另起注释行 ⇒ 不会有拼接/缩进/转义问题。

根因：`argumentation.py` 同一问题有两处出口 ——
  · 359-388（§五 建议）**早已修好**（只用证据角色名）；
  · 532（§四 材质句）仍用类别级 `missing_materials`（15 类类别名）
    ⇒ 正文出现「补充提供合同文件」，而真正缺的是「劳动合同与用工名册」。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "argumentation.py")

OLD = "    _mm = evidence.get('missing_materials') or []"
NEW = "    _mm = (evidence.get('missing_material_names') or evidence.get('missing_materials') or [])  # ★疑点6 D10：正文禁用类别名（合同文件），优先名称级"

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
print("[DONE] 疑点6 幽灵名已修")
