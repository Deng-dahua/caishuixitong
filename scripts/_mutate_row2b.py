# -*- coding: utf-8 -*-
"""合并批次第二行：疑点2 D8（汇总行冒充一笔）＋ ㊷（触发信号不丢差异/免责说明）。

写法约束（本轮踩过两次坑）：
  · 不写嵌套的 [(a,b),(c,d)] 字面量，改为「变量 + 逐对调用」，避免括号配平出错；
  · NEW 文本的**结尾**必须与 OLD 文本结尾逐字一致（只换中间内容）。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)
CRLF = chr(13) + chr(10)


def swap(path, old, new):
    p = os.path.join(ROOT, path)
    raw = io.open(p, "r", encoding="utf-8", newline="").read()
    has_crlf = CRLF in raw
    s = raw.replace(CRLF, NL)
    if s.count(old) != 1:
        print("!! %s: anchor命中 %d次(应为1): %r" % (path, s.count(old), old[:70]))
        sys.exit(2)
    s = s.replace(old, new, 1)
    io.open(p, "w", encoding="utf-8", newline="").write(s.replace(NL, CRLF) if has_crlf else s)
    print("OK %s" % path)


# ══ ㊷ clue_chain._terminal_signal：对题优先，不再最长优先 ════════════════
OLD_A = (
    '    if not detail:' + NL +
    '        return ""' + NL +
    '    sentences = split_sentences(str(detail))' + NL +
    '    best = pick_best(sentences[:4]) or ""'
)
NEW_A = (
    '    if not detail:' + NL +
    '        return ""' + NL +
    '    sentences = split_sentences(str(detail))' + NL +
    '    # ★★ 2026-10-04（㊷）：**不再"最长者优先"**。' + NL +
    '    #   旧实现 `pick_best(sentences[:4])` 按长度选，于是触发信号总落在那句最长的' + NL +
    '    #   免责/口径长句上，把差异与口径说明挤掉（实测 80/80 条勾稽发现都不带差异说明）。' + NL +
    '    #   现改为**对题优先**：与本项 type 的字符 2-gram 交集最大者胜；平手取**更短**的' + NL +
    '    #   （短句更可能是结论句，长句更可能是堆砌说明）。判据与环节读数同源（`_two_grams`）。' + NL +
    '    cands = sentences[:6] or sentences' + NL +
    '    if cands:' + NL +
    '        _t = _two_grams(str(finding.get("type", "")))' + NL +
    '        def _score(_s: str):' + NL +
    '            return (len(_t & _two_grams(_s)), -len(_s))' + NL +
    '        best = max(cands, key=_score)' + NL +
    '    else:' + NL +
    '        best = ""'
)
swap("engine/clue_chain.py", OLD_A, NEW_A)

# ══ D8-① enterprise_report：识别并剔除汇总行 ═══════════════════════════════
ER = "engine/enterprise_report.py"

OLD_B = '        _kept, _normal = [], 0'
NEW_B = (
    '        # ★★ 2026-10-04（疑点2 D8）：**汇总行不是一笔明细**。' + NL +
    '        #   事故：`verified_rule_engine` 产出的「【汇总】其他个人／个体往来（未达本要件50万元门槛，' + NL +
    '        #   共8个对象）」被当普通明细行，计入"共N笔"与"金额合计"（实测疑点2 的共3笔／2,246,055.57）；' + NL +
    '        #   渲染时还被截断成"汇总：其他个人／个体往来（未达本要件50万元门槛"（括号不闭合）。' + NL +
    '        #   `pipeline.py` 本有"跳过银行流水汇总行"的机制，但检测器自拼的行没走那道闸——' + NL +
    '        #   故在**消费端**加通用数据判据（不认表名）：实体列取值以「汇总／合计／小计／总计」' + NL +
    '        #   开头或含「【汇总】／汇总：」⇒ 汇总行，不计入笔数与金额，并如实披露行数。' + NL +
    '        _SUMMARY_MARKS = ("汇总", "合计", "小计", "总计")' + NL +
    '        _kept, _normal = [], 0' + NL +
    '        _summary_rows = 0'
)
swap(ER, OLD_B, NEW_B)

# ══ D8-② 在行循环里剔除汇总行 ═══════════════════════════════════════════
OLD_C = (
    '            if _st and any(_m in _st for _m in _NORMAL_MARKS):' + NL +
    '                _normal += 1' + NL +
    '                continue' + NL +
    '            _kept.append(r)'
)
NEW_C = (
    '            if _st and any(_m in _st for _m in _NORMAL_MARKS):' + NL +
    '                _normal += 1' + NL +
    '                continue' + NL +
    '            # 汇总行：实体列（对方单位/人员/姓名/凭证号…）以「汇总/合计/小计/总计」开头' + NL +
    '            _is_sum = False' + NL +
    '            for _k in _NAME_KEYS + ("凭证号", "凭证/单据标识"):' + NL +
    '                _v = str(r.get(_k) or "").strip()' + NL +
    '                if _v and any(_v.startswith(_m) or ("【汇总】" in _v) or ("汇总：" in _v)' + NL +
    '                              for _m in _SUMMARY_MARKS):' + NL +
    '                    _is_sum = True' + NL +
    '                    break' + NL +
    '            if _is_sum:' + NL +
    '                _summary_rows += 1' + NL +
    '                continue' + NL +
    '            _kept.append(r)'
)
swap(ER, OLD_C, NEW_C)

# ══ D8-③ 如实披露被剔除的汇总行数 ═══════════════════════════════════════
OLD_D = (
    '        if _normal:' + NL +
    '            seg += "，其中 **%d 行经逐项核对无差异**（不计入金额与对象数）" % _normal'
)
NEW_D = (
    '        if _normal:' + NL +
    '            seg += "，其中 **%d 行经逐项核对无差异**（不计入金额与对象数）" % _normal' + NL +
    '        if _summary_rows:' + NL +
    '            # 如实披露被排除的汇总行（不得静默少算，也不得把汇总当明细）' + NL +
    '            seg += "，另有 %d 行为汇总结算行（不计入笔数与金额）" % _summary_rows'
)
swap(ER, OLD_D, NEW_D)

print("[DONE] 第二行已落地")
