# -*- coding: utf-8 -*-
"""D2 的最后两处同源残留（真跑产物实证）：
  ① 域发现的 `description` 仍写"合计价税合计-1,285,450.57元"（detail 已拆、description 没拆）；
  ② **触发依据**"本项之所以列入检查…（本表 13 行，涉及 10 个对象，金额合计 1,285,450.57 元）"
     —— 那是「逐表概述」把表内**销项 4 行 + 进项 9 行跨方向加总**的结果。

修法：
  ① `description` 与 detail 同口径（销项侧 / 取得侧分列，不跨方向加总）。
  ② 「逐表概述」加**纯结构判据**（不认表名）：表内若有方向/侧别类列且取值多于一种，
     行数与金额**按方向分列**，不跨类加总；无方向列的表行为完全不变。
     与既有先例一致（该函数已有"配对状态表不得当命中明细表"的通用判据）。

⚠ 改文案会移动 `tax_impact.extract_amount` 的金额锚点 ⇒ 改完必须做全量 diff。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)


def swap(path, pairs):
    p = os.path.join(ROOT, path)
    raw = io.open(p, "r", encoding="utf-8", newline="").read()
    crlf = "\r\n" in raw
    s = raw.replace("\r\n", NL)
    for old, new in pairs:
        if s.count(old) != 1:
            print("!! %s: anchor命中 %d次(应为1): %r" % (path, s.count(old), old[:80]))
            sys.exit(2)
        s = s.replace(old, new, 1)
    if crlf:
        s = s.replace(NL, "\r\n")
    io.open(p, "w", encoding="utf-8", newline="").write(s)
    print("OK %s (%d处)" % (path, len(pairs)))


# ① description 与 detail 同口径
OLD_DESC = '''                f"检出{len(red_void)}张涉及红冲/作废的发票（红冲{n_red}张、作废{n_void}张），"
                f"合计价税合计{total_red:,.2f}元。\\n\\n"'''
NEW_DESC = '''                # ★ 2026-10-04（疑点1 D2）：description 必须与 detail **同口径**——
                #   旧版 detail 已按方向拆分，description 仍写"合计价税合计 -1,285,450.57 元"
                #   （销项 1,015,900.00 + 进项 269,550.57），同一疑点里两个口径，
                #   且合成数会被当成"触发依据"金额。措辞与 detail 保持一致，避免锚点漂移。
                f"检出{len(red_void)}张涉及红冲/作废的发票（红字发票（红冲）{n_red}张、作废{n_void}张）。"
                f"按方向拆分：销项（本企业开出）{len(_sales_red_ev)}张、冲减价税合计"
                f"{sum(abs(to_number(i.get('total', 0))) for i in _sales_red_ev):,.2f} 元；"
                f"取得（进项）{len(_pur_red_ev)}张、冲减价税合计"
                f"{sum(abs(to_number(i.get('total', 0))) for i in _pur_red_ev):,.2f} 元，"
                f"不跨方向加总。\\n\\n"'''

swap("engine/domain_analysis.py", [(OLD_DESC, NEW_DESC)])

# ② 逐表概述：表内混方向时按方向分列，不跨类加总
OLD_SEG = '''        seg = "%s（本表 %d 行" % (ttl, len(_rows))
        if _normal:
            seg += "，其中 **%d 行经逐项核对无差异**（不计入金额与对象数）" % _normal
        if names:
            seg += "，涉及 %d 个对象" % len(names)
        if amts:
            seg += "，金额合计 %s 元" % format(sum(amts), ",.2f")
        segs.append(seg + "）")'''
NEW_SEG = '''        # ★★ 2026-10-04（疑点1 四维自检 D2）：**表内混方向时不得跨方向加总**。
        #   事故：本项明细表 13 行含销项（本企业开出）4 行 + 取得（进项）9 行，概述写成
        #   "金额合计 1,285,450.57 元"（= 1,015,900.00 + 269,550.57）——而同一疑点正文已写明
        #   "影响销项税额的只有销项侧" ⇒ 触发依据与正文两个口径，合成数还被当成本项涉案金额。
        #   通用判据（**纯结构、不认表名**）：表内若有方向/侧别类列且**取值多于一种**，
        #   行数与金额按方向分列、不跨类加总；只有一类或无该类列 ⇒ 行为完全不变。
        #   （与相邻的"配对状态表不得当命中明细表"判据同一风格。）
        _DIR_KEYS = ("方向", "开票方向", "收付方向", "借贷方向", "借贷", "侧别")
        _by_dir = {}
        for _k in _DIR_KEYS:
            if any(_k in _r0 for _r0 in _kept):
                for _r0 in _kept:
                    _by_dir.setdefault(str(_r0.get(_k) or "").strip() or "未标注", []).append(_r0)
                break
        if len(_by_dir) < 2:
            _by_dir = {}
        seg = "%s（本表 %d 行" % (ttl, len(_rows))
        if _normal:
            seg += "，其中 **%d 行经逐项核对无差异**（不计入金额与对象数）" % _normal
        if names:
            seg += "，涉及 %d 个对象" % len(names)
        if _by_dir:
            _parts = []
            for _dv, _rs in _by_dir.items():
                _a = 0.0
                for _r0 in _rs:
                    for _k in _AMT_KEYS:
                        if _k in _r0:
                            try:
                                _a += abs(float(str(_r0[_k]).replace(",", "").rstrip("%")))
                            except (TypeError, ValueError):
                                pass
                            break
                _parts.append("%s %d 行、金额合计 %s 元"
                              % (_dv, len(_rs), format(_a, ",.2f")))
            seg += "，按方向分列（不跨方向加总）：" + "；".join(_parts)
        elif amts:
            seg += "，金额合计 %s 元" % format(sum(amts), ",.2f")
        segs.append(seg + "）")'''

swap("engine/enterprise_report.py", [(OLD_SEG, NEW_SEG)])
