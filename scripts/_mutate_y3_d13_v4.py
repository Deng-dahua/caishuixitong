# -*- coding: utf-8 -*-
"""疑点3 · D13 收口：§三 与 §四 与结构化字段**读同一个权威**。

上一版只改了 evidence_chain（登记未归类缺失名）＋ §四（按材料名计），
但 §三 仍自己遍历证据元素 + 自行做业态剔除 ⇒ 出现三处不一致：
  字段 `["客户对账单与询证函回函"]` ／ §三「4 项」／ §四「还缺 2 项」。
差异来源：销售台账、发货记录命中了一个**本业态不适用**的类别 ⇒ `evidence_chain` 正确跳过，
而 §三 自己的剔除没认出那个类别名。

正解：§三 不再自己算，**直接读 `ev["missing_material_names"]`**（`evidence_chain` 已含
业态剔除与未归类登记）⇒ 字段／§三／§四 三处**构造上**一致，不再可能漂移。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "enterprise_report.py")

OLD = (
    "        _lack_names = []" + NL +
    "        for _e8 in (lack or []):" + NL +
    "            _n8 = _e8.get(\"name\") if isinstance(_e8, dict) else _e8" + NL +
    "            _n8 = str(_n8 or \"\").strip()" + NL +
    "            if _n8 and _n8 not in _lack_names:" + NL +
    "                _lack_names.append(_n8)" + NL +
    "        _lack_ok = _filter_not_required(list(_lack_names), not_required_docs)"
)
NEW = (
    "        # ★★ 2026-10-04（疑点3 D13 收口）：**§三 与字段、与 §四 读同一个权威**。" + NL +
    "        #   旧实现自己遍历证据元素并自行做业态剔除 ⇒ 与 `evidence_chain` 的判定不一致" + NL +
    "        #   （销售台账、发货记录命中**本业态不适用**的类别，`evidence_chain` 正确跳过，" + NL +
    "        #    而这里没认出那个类别名）⇒ 字段 1 个 / §三 4 项 / §四 2 项，三处漂移。" + NL +
    "        #   现在直接读 `ev[\"missing_material_names\"]`（已含业态剔除与未归类登记）。" + NL +
    "        _lack_ok = [str(_z8) for _z8 in (ev.get(\"missing_material_names\") or []) if str(_z8).strip()]"
)


def swap(path, old, new):
    raw = io.open(path, "r", encoding="utf-8", newline="").read()
    crlf = CRLF in raw
    t = raw.replace(CRLF, NL)
    if t.count(old) != 1:
        print("!! 命中 %d 次" % t.count(old))
        sys.exit(2)
    t = t.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
    print("OK §三 已改为读字段权威")


swap(P, OLD, NEW)
print("DONE")
