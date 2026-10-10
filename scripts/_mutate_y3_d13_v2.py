# -*- coding: utf-8 -*-
"""疑点3 · 第1项（D13 缺料口径一致 + 计数观感）——按 `lack` 的**真实结构**改。

已确认（改前先看代码，吸取今天"凭命名猜类型"的教训）
------------------------------------------------------
`lack = [e for e in _els if e.get("status") == "缺失"]`
⇒ `lack` 是**证据元素字典列表**（元素含 name/status/role），**不是字符串列表**。
原代码用 `_name_brief(lack)` 正确取名；上一轮我改成字符串处理 ⇒ 报告渲染出原始 dict。

两条要修
--------
① **业态剔除贯穿**：结构化字段 `missing_materials` 已被业态剔除清空（服务型企业的
   销售台账/发货记录/客户对账单天然不适用），但 §三 文案仍写「确未提供的有 N 项」
   ⇒ 同一页自相矛盾。生成文案前先过**同一权威** `_filter_not_required`；
   全被剔完 ⇒ 如实写「属本业态天然不适用，不计入确未提供」。
② **计数观感**：`len(lack)` 把**复合名**（含两项，如「客户对账单与询证函回函」）算成 1 项
   ⇒ 出现"声明 2 项、列出 3 个名"。改为按分隔符拆开去重后**计名数**。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "enterprise_report.py")

OLD = (
    "        if lack:" + NL +
    "            _p3 += \"；确未提供的有%d项（%s）\" % (len(lack), _name_brief(lack))"
)
NEW_LINES = [
    "        # ★★ 2026-10-04（疑点3 D13 + 计数观感）：缺料文案与**结构化字段同一口径**。",
    "        #   `lack` 是**证据元素字典列表**（元素含 name/status/role），先取名再谈其它。",
    "        #   ① 业态剔除贯穿：`missing_materials` 已被剔除清空（服务型天然无销售台账/发货记录），",
    "        #      文案若仍写「确未提供」⇒ 字段说没有、文案说缺 N 项，同一页自相矛盾。",
    "        #   ② 计数观感：复合名（含两项）按 `len(lack)` 只算 1 项 ⇒ 声明数与列出的名不一致。",
    "        _lack_names = []",
    "        for _e8 in (lack or []):",
    "            _n8 = _e8.get(\"name\") if isinstance(_e8, dict) else _e8",
    "            _n8 = str(_n8 or \"\").strip()",
    "            if _n8 and _n8 not in _lack_names:",
    "                _lack_names.append(_n8)",
    "        _lack_ok = _filter_not_required(list(_lack_names), not_required_docs)",
    "        if _lack_names and not _lack_ok:",
    "            _p3 += \"；本项所列资料属本业态天然不适用，不计入确未提供\"",
    "        elif _lack_ok:",
    "            _atoms = []",
    "            for _x8 in _lack_ok:",
    "                for _y8 in re.split(r\"[、，,；;／/]|与|和|及|以及|或\", _x8):",
    "                    _y8 = _y8.strip()",
    "                    if _y8 and _y8 not in _atoms:",
    "                        _atoms.append(_y8)",
    "            _p3 += \"；确未提供的有%d项（%s）\" % (len(_atoms), \"、\".join(_atoms[:6]))",
]


def swap(path, old, new):
    raw = io.open(path, "r", encoding="utf-8", newline="").read()
    crlf = CRLF in raw
    t = raw.replace(CRLF, NL)
    if t.count(old) != 1:
        print("!! 命中 %d 次" % t.count(old))
        sys.exit(2)
    t = t.replace(old, new, 1)
    io.open(P, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
    print("OK 疑点3 D13 + 计数观感 已修")


swap(P, OLD, NL.join(NEW_LINES))
print("DONE")
