# -*- coding: utf-8 -*-
"""第三行：`constituent_checkpoint` 的**回退路径**不得用环节 `has_data` 当"资料有无"。

病根（★ 典型的"同一概念两处各判一次"）
--------------------------------------
要件数据源状态有两条路：
  · **优先**：红线声明了 `constituent_sources` ⇒ 走单一权威 `evidence_chain._match_material`
    （材料是否已提供）—— 这条是对的；
  · **回退**（未声明时）：`_match_source(c, _cands)`，而 `_cands` 里节点的状态写成
    `"已有" if n.get("has_data") else "未取得"`。
    `has_data` 的语义是"**本环节有没有对题读数**"，**不是**"这份资料有没有提供"。
    两者一旦混用，就会出现"资料明明已提供，却判『独立数据源本轮未取得』⇒ 要件未单独核对"
    —— 正是疑点2 D13「有数据却放弃核对」，且**本轮的 clue_chain 改造放大了它**
    （对题读数更严 ⇒ 更多环节 has_data=False ⇒ 更多要件被误判"未取得"）。

修法
----
回退路径的状态改由**资料齐备性唯一权威** `clue_chain.materials_available` 判定
（与优先路径同源、与告警三态同源）；`has_data` 仅在权威判不出时**兜底**，且判不出时
如实记"未知"（→ not_checked），不得凭 has_data 就断言"未取得"。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "constituent_checkpoint.py")

OLD = (
    '    for n in _nodes:' + NL +
    '        nm = "、".join(x for x in (_norm(n.get("source")), _norm(n.get("output"))) if x)' + NL +
    '        if nm:' + NL +
    '            _cands.append((nm, "已有" if n.get("has_data") else "未取得"))'
)
NEW = (
    '    # ★★ 2026-10-04（合并批次第三行 / 疑点2 D13）：**回退路径不得用环节 `has_data` 当"资料有无"**。' + NL +
    '    #   `has_data` 的语义是"本环节有没有**对题读数**"，不是"这份资料有没有提供"。' + NL +
    '    #   混用的后果：资料已提供却判「独立数据源本轮未取得」⇒ 要件"未单独核对"——' + NL +
    '    #   正是"有数据却放弃核对"，且对题读数越严、误判越多。' + NL +
    '    #   现改由**资料齐备性唯一权威** `clue_chain.materials_available` 判定（与优先路径同源）；' + NL +
    '    #   权威判不出时如实记"未知"，**不得**凭 has_data 断言"未取得"。' + NL +
    '    for n in _nodes:' + NL +
    '        nm = "、".join(x for x in (_norm(n.get("source")), _norm(n.get("output"))) if x)' + NL +
    '        if not nm:' + NL +
    '            continue' + NL +
    '        _st_node = ""' + NL +
    '        try:' + NL +
    '            from engine.clue_chain import materials_available as _ma_node' + NL +
    '            _ok_node, _miss_node = _ma_node(_norm(n.get("source")), _avail)' + NL +
    '            if _ok_node:' + NL +
    '                _st_node = "已有"' + NL +
    '            elif _miss_node:' + NL +
    '                _st_node = "未取得"' + NL +
    '        except Exception:  # noqa: BLE001' + NL +
    '            _st_node = ""' + NL +
    '        _cands.append((nm, _st_node or "未知"))'
)

s = io.open(P, "r", encoding="utf-8", newline="").read()
has_crlf = CRLF in s
t = s.replace(CRLF, NL)
if t.count(OLD) != 1:
    print("!! anchor 命中 %d 次" % t.count(OLD))
    sys.exit(2)
t = t.replace(OLD, NEW, 1)
io.open(P, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if has_crlf else t)
print("OK constituent_checkpoint 回退路径已改走资料齐备性唯一权威")
