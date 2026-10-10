# -*- coding: utf-8 -*-
"""疑点5 · D7 收口：把红线 `clue_chain` 环2 的 source 与**证据项名逐字对齐**。

★ 根因（读码确认，两行并列可比）
    行 3745：`{"step": 2, "source": "利润表（收入、利润总额、工资总额）", …}`  ← 笼统**类别**
    行 3751：`{"role": "直接证据", "name": "收入/工资/利润总额计算底稿", …}`  ← 具体**材料名**
  ⇒ 环节声称「对应资料＝利润表」，而证据链实际要求「收入/工资/利润总额计算底稿」
     ⇒ **声称的来源与实际取数来源不符**（D7 的真身）。

修法：把 3745 的 source 改成与 3751 **逐字一致**的「收入/工资/利润总额计算底稿」
     —— 数据层自洽，渲染层不用动。
★ 只改这一个字符串；不碰该红线的其它字段、不改任何判定。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "tax_redlines.py")

OLD = '            {"step": 2, "source": "\u5229\u6da6\u8868\uff08\u6536\u5165\u3001\u5229\u6da6\u603b\u989d\u3001\u5de5\u8d44\u603b\u989d\uff09", "action": "\u6309\u9650\u989d\u516c\u5f0f\u8ba1\u7b97\u53ef\u6263\u9664\u989d",'
NEW = '            {"step": 2, "source": "\u6536\u5165/\u5de5\u8d44/\u5229\u6da6\u603b\u989d\u8ba1\u7b97\u5e95\u7a3f", "action": "\u6309\u9650\u989d\u516c\u5f0f\u8ba1\u7b97\u53ef\u6263\u9664\u989d",'

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
print("[DONE] 环2 的 source 已与证据项名逐字对齐")
