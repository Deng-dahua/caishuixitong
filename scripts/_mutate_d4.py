# -*- coding: utf-8 -*-
"""D4 收口：把"配平只核销项侧"这个口径从**隐式**变为**显式**（不改变判定结果）。

现状复核：要件④ 现在**不再命中**（`constituent_hits=[1,2,3]`）——
`has_confirm` 直接读发票**备注栏**里的确认单编号，判定口径已是"是否走了确认流程"，
不再是"有没有叫该名字的文件"。D4 的实质已解决。

但配平那一段仍写 `for _r in red_list:`（全部红冲，含进项），只是靠
"进项红冲的对手方（本企业）不在销项蓝票字典的键里"**偶然**被跳过 —— 隐式行为，
换一份数据就可能串味。本改动把它显式限定为销项侧，并写明进项侧配平属另一检查范围
（与 detail 已声明的"取得侧红冲影响的是进项税额抵扣，属进项转出检查范围"一致）。
"""
import io
import os
import sys

NL = chr(10)
P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "engine", "domain_analysis.py")

OLD = '''                _blue_amt = {}
                for _b in invoices:
                    if str(_b.get("direction", "")) != "销项":
                        continue
                    _btype = str(_b.get("status", "")) + str(_b.get("remark", ""))
                    if any(_k in _btype for _k in ("红冲", "作废", "红色", "冲红")):
                        continue
                    _blue_amt.setdefault(str(_b.get("buyer", "")), []).append(
                        round(abs(to_number(_b.get("total", 0))), 2))
                _mismatch = 0
                for _r in red_list:
                    _amts = _blue_amt.get(str(_r.get("buyer", "")))
                    if _amts and round(abs(to_number(_r.get("total", 0))), 2) not in _amts:
                        _mismatch += 1'''
NEW = '''                # ★ 2026-10-04（疑点1 四维自检 D4）：配平**只核销项侧**，且这条口径须显式。
                #   本条红线讲的是"通过红冲调节**销项税额**"；被红冲的销项蓝票由本企业开出，
                #   对手方=购方。取得侧（进项）红冲影响的是进项税额抵扣，其配平属
                #   "进项转出检查范围"（与上文 detail 的声明一致），**不并入本项**——
                #   否则会出现"红线讲销项调节、要件却由进项侧成立"的错配。
                #   旧实现写 `for _r in red_list`（含进项），只因进项红冲的对手方（本企业）
                #   恰好不在销项蓝票字典的键里而被**偶然**跳过 —— 隐式行为，换数据即串味。
                _blue_amt = {}
                for _b in invoices:
                    if str(_b.get("direction", "")) != "销项":
                        continue
                    _btype = str(_b.get("status", "")) + str(_b.get("remark", ""))
                    if any(_k in _btype for _k in ("红冲", "作废", "红色", "冲红")):
                        continue
                    _blue_amt.setdefault(str(_b.get("buyer", "")), []).append(
                        round(abs(to_number(_b.get("total", 0))), 2))
                _mismatch = 0
                for _r in _sales_red:
                    _amts = _blue_amt.get(str(_r.get("buyer", "")))
                    if _amts and round(abs(to_number(_r.get("total", 0))), 2) not in _amts:
                        _mismatch += 1'''

s = io.open(P, "r", encoding="utf-8", newline="").read()
crlf = "\r\n" in s
s = s.replace("\r\n", NL)
if s.count(OLD) != 1:
    print("!! anchor 命中 %d 次" % s.count(OLD))
    sys.exit(2)
s = s.replace(OLD, NEW, 1)
if crlf:
    s = s.replace(NL, "\r\n")
io.open(P, "w", encoding="utf-8", newline="").write(s)
print("OK 配平口径已显式限定为销项侧")
