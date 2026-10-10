# -*- coding: utf-8 -*-
"""新增**产物级**闸门：报告正文不得出现 Python 字典/列表字面量。

为什么需要这一条（2026-10-04 18:40 事故）
----------------------------------------
我把缺料清单当字符串列表处理，实际它是**证据元素字典列表** ⇒ 报告渲染出
「确未提供的有 20 项（{'role': '直接证据'}、{'name': '销售台账'}…）」，
而**闸门全绿**。查证：已有的 `①d` 闸门（第 1100 行）查的是**源码 AST** 里
`return {...}` 的值是否含 set/dict/list —— 属**源码级**；
我这次错在**渲染期**把 dict 元素当字符串处理 ⇒ 源码里根本看不出问题。
⇒ 缺的是**产物级**（读真跑产物、扫读者可见文本）这道，二者互补。

实现要点（刻意不用正则：今天栽在转义上）
--------------------------------------
判据 = 文本里出现 `{'` 或 `{"` 即判 ERROR（用 chr() 构造，零转义风险）。
扫描范围：`enterprise_readable_report` 全部字符串叶子（读者实际看到的部分）。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
AUDIT = os.path.join(ROOT, "tools", "audit_consistency.py")

ANCHOR = "        except Exception as _e5:"

GATE = [
    "            # ⑥ 格式泄漏（产物级，2026-10-04）：报告正文不得出现 Python 字典字面量。",
    "            #   与源码级 ①d 闸门（第 1100 行，查 return 字典里含 set/dict/list）互补：",
    "            #   ①d 查不��「渲染期把 dict 元素当字符串处理」——源码看不出问题，产物里才有。",
    "            #   事故：缺料清单实为证据元素字典列表，报告出现",
    "            #   「确未提供的有 20 项（{'role': '直接证据'}…）」，而闸门当时全绿。",
    "            _Q1 = chr(39)",
    "            _Q2 = chr(34)",
    "            _OPEN = (chr(123) + _Q1, chr(123) + _Q2)",
    "            _bad6 = []",
    "",
    "            def _scan6(_o, _p7):",
    "                if isinstance(_o, dict):",
    "                    for _k7, _v7 in _o.items():",
    "                        _scan6(_v7, _p7 + \"/\" + str(_k7))",
    "                elif isinstance(_o, list):",
    "                    for _i7, _v7 in enumerate(_o):",
    "                        _scan6(_v7, _p7 + \"[%d]\" % _i7)",
    "                else:",
    "                    _t7 = str(_o)",
    "                    for _op7 in _OPEN:",
    "                        if _op7 in _t7:",
    "                            _bad6.append((_p7, _t7[:60]))",
    "                            break",
    "",
    "            _scan6(_d5.get(\"enterprise_readable_report\") or {}, \"erp\")",
    "            for _p7, _s7 in _bad6[:5]:",
    "                issues.append((\"ERROR\", \"enterprise_readable_report\",",
    "                               \"报告正文出现字典字面量（格式泄漏）@%s: %s\" % (_p7, _s7)))",
    ANCHOR,
]


def swap(path, old, new):
    raw = io.open(path, "r", encoding="utf-8", newline="").read()
    crlf = CRLF in raw
    t = raw.replace(CRLF, NL)
    if t.count(old) != 1:
        print("!! 命中 %d 次（应为 1）" % t.count(old))
        sys.exit(2)
    t = t.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
    print("OK 产物级格式泄漏闸门已插入")


swap(AUDIT, ANCHOR, NL.join(GATE))
print("DONE")
