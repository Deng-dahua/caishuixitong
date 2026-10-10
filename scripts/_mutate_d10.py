# -*- coding: utf-8 -*-
"""疑点3 · D10 修复：**材料名不得是法条语言**（在证据链组装处收口）。

事故：证据项名被写成「与待证事实相关且依法获准核实的特定账户、期间和交易资料（含已销户账户）」
—— 那是**法条措辞**、不是资料名，读者无法据此准备材料，报告等于在要一份"不存在的东西"。

修法（数据驱动、通用、零特例）
------------------------------
在 `build_evidence_chain` 组装 `elements` 时：若证据项名命中**法条语言特征词**
（依法/应/按规定/第X条/待证事实…），则**显示名回退为该名归到的资料类别**
（唯一权威 `material_names.canonical`）—— 读者看到的是真实存在的材料名；
原文保留在同一条目的说明里（`basis` 已引用原文表述，不丢信息）。

为什么在这一层收口
------------------
该名不来自 `tax_redlines`（那里已是正确写法）、不来自 DB/配置/缓存；
在**证据链组装处**统一规范化，是唯一能覆盖"任何来源"的口子，且对红线库无损。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "evidence_chain.py")

MARKERS = (
    "def _legal_lang_markers() -> tuple:" + NL +
    "    \"\"\"**法条语言**特征词（材料名里不该出现这些）。数据驱动，新增只加一项。\"\"\"" + NL +
    "    return (" + NL +
    "        \"依法\", \"应依照\", \"按照规定\", \"根据法律\", \"法律规定\", \"第%条\" % ()," + NL +
    "        \"待证事实\", \"经批准取得\", \"依法获准\", \"依法核实\", \"依法核验\"," + NL +
    "    )" + NL + NL + NL
)

OLD = (
    "        purpose = str(item.get(\"purpose\") or \"\")" + NL +
    "        if role == \"反证\":"
)
NEW = (
    "        purpose = str(item.get(\"purpose\") or \"\")" + NL +
    "        # ★★ 2026-10-04（疑点3 D10）：**材料名不得是法条语言**。" + NL +
    "        #   实测事故：证据项名写成「与待证事实相关且依法获准核实的特定账户、期间和" + NL +
    "        #   交易资料（含已销户账户）」—— 法条措辞、不是资料名，读者无法据此准备材料。" + NL +
    "        #   命中法条语言特征词 ⇒ 显示名**回退为该名归到的资料类别**（唯一权威" + NL +
    "        #   `material_names.canonical`）；原文不丢（basis 仍引用其表述）。" + NL +
    "        if any(_w and _w in name for _w in _legal_lang_markers()):" + NL +
    "            try:" + NL +
    "                from engine.material_names import canonical as _canon_lg" + NL +
    "                _cat_lg = _canon_lg(name)" + NL +
    "            except Exception:  # noqa: BLE001" + NL +
    "                _cat_lg = None" + NL +
    "            if _cat_lg:" + NL +
    "                name = str(_cat_lg)" + NL +
    "        if role == \"反证\":"
)


def swap(path, old, new, tag):
    raw = io.open(path, "r", encoding="utf-8", newline="").read()
    crlf = CRLF in raw
    t = raw.replace(CRLF, NL)
    if t.count(old) != 1:
        print("!! %s 命中 %d 次" % (tag, t.count(old)))
        sys.exit(2)
    t = t.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
    print("OK " + tag)


swap(P, "def build_evidence_chain(", MARKERS + "def build_evidence_chain(", "插入特征词表")
swap(P, OLD, NEW, "材料名规范化")
print("DONE")
