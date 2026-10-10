# -*- coding: utf-8 -*-
"""D2 剩余半（合并金额键）+ D3（名/判据/读数对齐）——均为通用规则、无特例。

D2：`observed_metrics` 不再给"销项+进项合成"的单一金额键。本条红线讲的是
    "红冲调节销项税额"，影响销项税额的**只有销项侧**；合成数 1,285,450.57
    （= 销项 1,015,900.00 + 进项 269,550.57）既不是本项涉案金额，又与 detail 的
    按方向拆分口径矛盾（实测被当"触发依据"展示）。改按方向分列。
    企业报告敞口取 `_is_expo_key` 命中的**最大值** ⇒ 拆分后自然落到销项侧，口径随之对齐。

D3：类型名"…数量异常"暗示阈值型判据，而判定原则是"存在即触发、不设门槛"，
    要件①又写"占比需评估"却无判据 ⇒ 名/判据/读数三者不一致。修法是把**判据写清**：
    要件①文本明确"现象/前提条、存在即成立、不设比例阈值"，detail 首句给出同一判据。
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


# ── D2：合并金额键 → 方向键 ────────────────────────────────────────────
OLD_METRICS = '''            "observed_metrics": {
                "红字发票_笔数": n_red,
                "作废发票_笔数": n_void,
                "红冲作废金额": abs(total_red),
            },'''
NEW_METRICS = '''            # ★★ 2026-10-04（疑点1 四维自检 D2）：**不再给"销项+进项合成"的单一金额键**。
            #   本条红线讲的是"通过红冲调节**销项税额**"，而影响销项税额的只有销项侧；
            #   合成数（销项 1,015,900.00 + 进项 269,550.57）既不是本项涉案金额，
            #   又与 detail 的按方向拆分口径矛盾 —— 同一疑点里两个口径（实测被当"触发依据"）。
            #   改按方向分列，键名仍保留"红冲作废"字样以便企业报告敞口判据（_is_expo_key）
            #   继续命中；敞口取命中键的**最大值**，故自动落到销项侧，与正文口径一致。
            #   新增同类红线只需照此写方向键，不必改逻辑。
            "observed_metrics": {
                "红字发票_笔数": n_red,
                "作废发票_笔数": n_void,
                "红冲作废金额_销项侧": abs(_red_sales_amt),
                "红冲作废金额_进项侧": sum(
                    abs(to_number(i.get("total", 0))) for i in _pur_red),
            },'''

# ── D3：detail 首句写明判据（正文禁 markdown ⇒ 不用 ** 加粗，不用"字段：值"） ──
OLD_DETAIL = '''        detail = (f"共{len(red_void)}张发票涉及红冲/作废：其中红字发票（红冲）{n_red}张、作废{n_void}张。"'''
NEW_DETAIL = '''        # ★ 2026-10-04（疑点1 四维自检 D3）：**判据必须写在读数前面**。
        #   旧版详情只给读数不给判据，而类型名却叫"…数量异常"、要件①又写"占比需评估"
        #   —— 名（像阈值型）与实（存在即触发、不设门槛）不一致，读者会去找一个不存在的阈值。
        detail = (f"本项为现象/前提条：只要存在红字发票或作废发票即成立，"
                  f"不设比例或张数阈值；占比与张数只作证据，够不够格由人工判断。"
                  f"共{len(red_void)}张发票涉及红冲/作废：其中红字发票（红冲）{n_red}张、作废{n_void}张。"'''

swap("engine/domain_analysis.py", [
    (OLD_METRICS, NEW_METRICS),
    (OLD_DETAIL, NEW_DETAIL),
])

# ── D3：要件①文本改为与判据一致 ───────────────────────────────────────
OLD_CON = '            "存在红字发票或作废发票（红冲行为），其对同期开票额的占比需评估",'
NEW_CON = '            "存在红字发票或作废发票（红冲行为）——本项为现象/前提条，存在即成立，不设比例阈值；占比只作证据",'

swap("engine/tax_redlines.py", [(OLD_CON, NEW_CON)])
