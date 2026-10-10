# -*- coding: utf-8 -*-
"""疑点3 · 第1项：缺料文案与结构化字段**同一口径**（业态剔除贯穿 + 复合名计数）。

病根（实测）
------------
疑点3「银行收款大于申报收入」：`missing_materials=[]`、`missing_material_names=[]`
（**已被业态剔除清空**，因为销售台账/发货记录/客户对账单对服务型天然不适用），
但 §三 文案仍写「确未提供的有 2 项（销售台账、发货记录、客户对账单与询证函回函）」、
§四 写「还缺 3 项」⇒ **字段说没有、文案说缺 N 项**。
另：「2 项」却列出 3 个名 —— `len(lack)` 把**复合名**（含两项）算成 1 项。

修法（唯一权威 `not_required_docs`，与结构化字段同一份）
------------------------------------------------------
① 生成文案前先过 `_filter_not_required`；全被剔完时**如实写"属本业态天然不适用"**，
   不用"确未提供"口径（企业天然不会有，要了也白要）。
② 项数按**实际材料名数**计（复合名按分隔符拆开去重），声明数与列出的名一致。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "enterprise_report.py")

OLD = (
    '        if lack:' + NL +
    '            _p3 += "；确未提供的有%d项（%s）" % (len(lack), _name_brief(lack))'
)
NEW = (
    '        # ★★ 2026-10-04（疑点3 D13 + 计数观感）：缺料文案必须与**结构化字段同一口径**。' + NL +
    '        #   实测事故：本项的缺料（销售台账/发货记录/客户对账单与询证函回函）对服务型' + NL +
    '        #   **天然不适用** ⇒ `missing_materials` 已被业态剔除清空，但 §三 文案仍写' + NL +
    '        #   「确未提供的有 2 项」⇒ 字段说没有、文案说缺 N 项（同一页自相矛盾）。' + NL +
    '        #   修法：生成文案前过**同一权威** `_filter_not_required`；全被剔完时如实写' + NL +
    '        #   「属本业态天然不适用」，不占用"确未提供"口径。' + NL +
    '        _lack_f = _filter_not_required(list(lack or []), not_required_docs)' + NL +
    '        if lack and not _lack_f:' + NL +
    '            _p3 += "；本项所列资料属本业态天然不适用，不计入确未提供"' + NL +
    '        elif _lack_f:' + NL +
    '            # 项数按**实际材料名数**计：复合名（含两项）拆开去重，避免"声明 2 项、列出 3 个名"' + NL +
    '            _nm_f = []' + NL +
    '            for _x in _lack_f:' + NL +
    '                for _y in re.split(r"[、，,；;／/]|与|和|及|以及|或", str(_x)):' + NL +
    '                    _y = _y.strip()' + NL +
    '                    if _y and _y not in _nm_f:' + NL +
    '                        _nm_f.append(_y)' + NL +
    '            _p3 += "；确未提供的有%d项（%s）" % (len(_nm_f), "、".join(_nm_f[:6]))'
)

raw = io.open(P, "r", encoding="utf-8", newline="").read()
crlf = CRLF in raw
t = raw.replace(CRLF, NL)
if t.count(OLD) != 1:
    print("!! 命中 %d 次" % t.count(OLD))
    sys.exit(2)
t = t.replace(OLD, NEW, 1)
# re 模块是否已导入
if "import re" not in t.split(NL)[0:40][0] and "import re" not in t[:2000]:
    t = t.replace("import json", "import json" + NL + "import re", 1)
io.open(P, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
print("OK 疑点3 D13 + 计数观感 已修（业态剔除贯穿 + 复合名按名数计）")
