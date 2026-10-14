# -*- coding: utf-8 -*-
"""合并批次第二行：疑点2 D8（汇总行冒充一笔）＋ ㊷（触发信号不丢差异/免责说明）。

D8 根因
------
`verified_rule_engine` 产出形如 `【汇总】其他个人／个体往来（未达本要件50万元门槛，共8个对象）`
的**汇总行**（不是一笔交易），下游把它当普通明细行：
  · 渲染成「对方单位＝汇总：…」，还**截断丢了括号与省略号**；
  · 计入"共 N 笔"与"金额合计"（实测疑点2 的"共3笔／2,246,055.57"）。
`pipeline.py` 里本有"跳过银行流水汇总行"的机制，但**资金回流检测器自拼的行没走那道闸**。
⇒ 修法不改生成端（避免各检测器各写一套），而在**消费端**加**通用数据判据**：
   行的实体列取值以「汇总／合计／小计／总计」开头（或含 `【汇总】`／`汇总：`）
   ⇒ 该行是汇总行，**不计入笔数与金额**，并**如实披露**"其中 N 行为汇总行"。
   （与 `_evidence_summary` 里既有的"配对状态表不计入笔数"判据同风格、同函数。）

㊷ 根因
------
`clue_chain._terminal_signal` 用 `pick_best(sentences[:4])`——**最长者优先**，
于是触发信号总是选到最长的那句（往往是免责/口径长句），把**差异/口径说明**挤掉。
⇒ 修法：改为**对题优先**（与本项 type 的字符 2-gram 交集最大；平手取**更短**的），
   与环节读数同一套对题判据（`_two_grams`，唯一权威），不再以长度论优劣。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)
CRLF = chr(13) + chr(10)


def swap(path, pairs):
    p = os.path.join(ROOT, path)
    raw = io.open(p, "r", encoding="utf-8", newline="").read()
    has_crlf = CRLF in raw
    s = raw.replace(CRLF, NL)
    for old, new in pairs:
        if s.count(old) != 1:
            print("!! %s: anchor命中 %d次(应为1): %r" % (path, s.count(old), old[:70]))
            sys.exit(2)
        s = s.replace(old, new, 1)
    io.open(p, "w", encoding="utf-8", newline="").write(s.replace(NL, CRLF) if has_crlf else s)
    print("OK %s (%d处)" % (path, len(pairs)))


# ── ㊷ clue_chain._terminal_signal：对题优先，不再最长优先 ────────────────
swap("engine/clue_chain.py", [(
    '''    if not detail:
        return ""
    sentences = split_sentences(str(detail))
    best = pick_best(sentences[:4]) or ""
    if best:
        return clamp_text(strip_meta_prefix(best), 180)
    if numbers:
        return "涉及金额与占比：" + "、".join(numbers[:4])
    return ""''',
    '''    if not detail:
        return ""
    sentences = split_sentences(str(detail))
    # ★★ 2026-10-04（㊷）：**不再"最长者优先"**。
    #   旧实现 `pick_best(sentences[:4])` 按长度选，于是触发信号总是落在那句最长的
    #   **免责/口径长句**上，把**差异与口径说明**挤掉（实测 80/80 条勾稽发现都不带差异说明）。
    #   现改为**对题优先**：与本项 type 的字符 2-gram 交集最大者胜；平手取**更短**的那句
    #   （短句更可能是结论句，长句更可能是堆砌说明）。判据与环节读数同源（`_two_grams`）。
    cands = sentences[:6] or sentences
    if cands:
        _t = _two_grams(str(finding.get("type", "")))
        def _score(_s: str):
            return (len(_t & _two_grams(_s)), -len(_s))
        best = max(cands, key=_score)
    else:
        best = ""
    if best:
        return clamp_text(strip_meta_prefix(best), 180)
    if numbers:
        return "涉及金额与占比：" + "、".join(numbers[:4])
    return ""'''
)])

# ── D8 enterprise_report._evidence_summary：汇总行不计入笔数与金额 ────────
swap("engine/enterprise_report.py", [(
    '''        _kept, _normal = [], 0''',
    '''        # ★★ 2026-10-04（疑点2 D8）：**汇总行不是一笔明细**。
        #   事故：`verified_rule_engine` 产出的「【汇总】其他个人／个体往来（未达本要件50万元门槛，
        #   共8个对象）」被当普通明细行，计入"共N笔"与"金额合计"（实测疑点2 的共3笔／2,246,055.57）；
        #   渲染时还被截断成"汇总：其他个人／个体往来（未达本要件50万元门槛"（**括号不闭合**）。
        #   `pipeline.py` 本有"跳过银行流水汇总行"的机制，但检测器自拼的行没走那道闸——
        #   故在**消费端**加通用数据判据（不认表名）：实体列取值以「汇总／合计／小计／总计」
        #   开头或含「【汇总】／汇总：」⇒ 汇总行，不计入笔数与金额，并如实披露行数。
        #   （与下方"配对状态表不计入"同风格、同函数。）
        _SUMMARY_MARKS = ("汇总", "合计", "小计", "总计", "【汇总】")
        _kept, _normal = [], 0
        _summary_rows = 0'''),
    ('''        for r in _rows:
            _st = ""
            for _k in _STATE_KEYS:
                if _k in r:
                    _st = str(r.get(_k) or "")
                    break
            if _st and any(_m in _st for _m in _NORMAL_MARKS):
                _normal += 1
                continue
            _kept.append(r)''',
    '''        for r in _rows:
            _st = ""
            for _k in _STATE_KEYS:
                if _k in r:
                    _st = str(r.get(_k) or "")
                    break
            if _st and any(_m in _st for _m in _NORMAL_MARKS):
                _normal += 1
                continue
            # 汇总行：实体列（对方单位/人员/姓名/凭证号…）以「汇总/合计/小计/总计」开头
            _is_sum = False
            for _k in _NAME_KEYS + ("凭证号", "凭证/单据标识"):
                _v = str(r.get(_k) or "").strip()
                if _v and any(_v.startswith(_m) or ("【汇总】" in _v) or ("汇总：" in _v)
                              for _m in _SUMMARY_MARKS):
                    _is_sum = True
                    break
            if _is_sum:
                _summary_rows += 1
                continue
            _kept.append(r)'''),
    ('''        seg = "%s（本表 %d 行" % (ttl, len(_rows))
        if _normal:
            seg += "，其中 **%d 行经逐项核对无差异**（不计入金额与对象数）" % _normal''',
    '''        seg = "%s（本表 %d 行" % (ttl, len(_rows))
        if _normal:
            seg += "，其中 **%d 行经逐项核对无差异**（不计入金额与对象数）" % _normal
        if _summary_rows:
            # 如实披露被排除的汇总行（不得静默少算，也不得把汇总当明细）
            seg += "，另有 %d 行为汇总结算行（不计入笔数与金额）" % _summary_rows'''),
])
