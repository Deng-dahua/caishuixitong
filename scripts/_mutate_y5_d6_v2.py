# -*- coding: utf-8 -*-
"""疑点5 · D6 回填：把分项扣除限额测算的数字**回填**到对应环节的 `observed`。

★ 落点已确认（读调用点实参）：`enterprise_report.py:3081` 是
  `_limit_items_table(rid, findings)` —— `findings` / `rid` / `clue` **三者同在作用域**，
  且该表能渲染出 411,111.53 / 2,729,730.26 ⇒ **`findings` 里就有带 observed_metrics 的发现**
  （不在 `redline_detection`、也不在 `supporting_findings`）。

★ 事故（要修的）：三环 `observed` 全写「本环节未产出对题读数」，而同疑点的
  「分项扣除限额测算」表里**确实有金额** ⇒ 数据在同疑点内可回指，却写"未产出"＝否定已算出的数。

守两条铁律：
  ① 只回填**动作对题**的环节（action/output 含"限额/归集/计算"类词）——
     环3「核对是否作纳税调增」不得被填（它的读数确实缺汇算清缴明细）；
  ② 数字**逐字取自本表**，不新算、不改口径。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "enterprise_report.py")

OLD = (
    "        if _lit:" + NL +
    "            paragraphs[3][\"detail_tables\"] = [_lit]" + NL
)
NEW = (
    "        if _lit:" + NL +
    "            paragraphs[3][\"detail_tables\"] = [_lit]" + NL +
    "            # ★★ 2026-10-05（疑点5 D6）：分项数字**回填**到对题环节的 observed。" + NL +
    "            #   事故：三环都写「本环节未产出对题读数」，而同疑点的分项测算表里" + NL +
    "            #   确实有金额（业务招待费 411,111.53／广宣费 2,729,730.26）" + NL +
    "            #   ⇒ 数据在同疑点内可回指，写「未产出」等于否定已算出的数。" + NL +
    "            #   只回填**动作对题**的环节（环3「核对是否作纳税调增」不得被填）；数字逐字取自本表。" + NL +
    "            try:" + NL +
    "                _lim_txt = \"；\".join(" + NL +
    "                    \"%s 账面 %s、超限 %s\" % (r.get(\"费用项目\")," + NL +
    "                                            r.get(\"账面发生额（元）\"), r.get(\"超限金额（元）\"))" + NL +
    "                    for r in ((_lit.get(\"rows\") or [])[:3]))" + NL +
    "                for _nd in (clue.get(\"nodes\") or []):" + NL +
    "                    if not isinstance(_nd, dict):" + NL +
    "                        continue" + NL +
    "                    _obs5 = str(_nd.get(\"observed\") or \"\")" + NL +
    "                    if \"未产出对题读数\" not in _obs5:" + NL +
    "                        continue" + NL +
    "                    _act5 = str(_nd.get(\"action\") or \"\") + str(_nd.get(\"output\") or \"\")" + NL +
    "                    if not any(_k in _act5 for _k in (\"限额\", \"归集\", \"扣除\", \"计算\", \"发生额\")):" + NL +
    "                        continue" + NL +
    "                    _nd[\"observed\"] = \"本环节读数（来自本项分项扣除限额测算）：\" + _lim_txt" + NL +
    "                    _nd[\"has_data\"] = True" + NL +
    "            except Exception:" + NL +
    "                pass" + NL
)

raw = io.open(P, "r", encoding="utf-8", newline="").read()
crlf = CRLF in raw
t = raw.replace(CRLF, NL)
c = t.count(OLD)
print("锚点命中 =", c)
if c != 1:
    print("!! 锚点异常 ⇒ 不写盘")
    sys.exit(2)
t = t.replace(OLD, NEW, 1)
io.open(P, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
print("OK 疑点5 D6 回填已落地")
