# -*- coding: utf-8 -*-
"""D2 收尾（第二次）：方向判据改按**列的取值**判定，而不是按列名。

第一版按列名找"方向/开票方向/…"——**没生效**（真跑实证触发依据仍写 1,285,450.57）：
本项的侧别信息编码在「来源」列里（取值 = "销项发票"/"进项发票"），列名根本不含"方向"。

修法：声明一张**方向词表** `_SIDE_VALUES`，逐列看取值集合——
若某列的非空取值**全部**落在词表内且**多于一种**，该列即方向列，按其分列金额、不跨类加总。
仍是纯数据驱动（新增一种侧别叫法只需往词表加一行），不认表名、不写任何"红冲"特例。
"""
import io
import os
import sys

NL = chr(10)
P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "engine", "enterprise_report.py")

OLD = '''        _DIR_KEYS = ("方向", "开票方向", "收付方向", "借贷方向", "借贷", "侧别")
        _by_dir = {}
        for _k in _DIR_KEYS:
            if any(_k in _r0 for _r0 in _kept):
                for _r0 in _kept:
                    _by_dir.setdefault(str(_r0.get(_k) or "").strip() or "未标注", []).append(_r0)
                break
        if len(_by_dir) < 2:
            _by_dir = {}'''
NEW = '''        #   ⚠ 第一版按**列名**找"方向/开票方向…"——**实测没生效**：本项侧别信息编码在
        #     「来源」列里（取值 = "销项发票"/"进项发票"），列名不含"方向"。
        #     故改按**列的取值**判：取值集合全部落在方向词表内、且多于一种 ⇒ 该列是方向列。
        #     仍是数据驱动（新增侧别叫法只往 `_SIDE_VALUES` 加一项），不认表名。
        _SIDE_VALUES = (
            "销项", "进项", "销项发票", "进项发票", "开出", "取得",
            "收入", "支出", "收款", "付款", "转出", "转入",
            "借", "贷", "借方", "贷方", "销项税额", "进项税额",
        )
        _by_dir = {}
        for _k in ((_kept[0] or {}).keys()):
            _vals = {str((_r0 or {}).get(_k) or "").strip() for _r0 in _kept}
            _vals.discard("")
            if len(_vals) < 2:
                continue
            if not all(_v in _SIDE_VALUES for _v in _vals):
                continue
            for _r0 in _kept:
                _by_dir.setdefault(str((_r0 or {}).get(_k) or "").strip() or "未标注",
                                   []).append(_r0)
            break
        if len(_by_dir) < 2:
            _by_dir = {}'''

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
print("OK 方向判据已改为按列取值判定")
