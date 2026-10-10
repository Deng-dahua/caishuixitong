# -*- coding: utf-8 -*-
"""疑点5 · D11 收口：让 **§四 与 §三 用同一套缺料口径**（原子数 + 权威字段）。

★ 判据先在真数据上验证过（抄真实文案）：
    §三（真跑产物）：「本项检查需要5项材料，其中名称逐字对应…有2项（费用明细账、凭证），
                     其中3项已提供同类资料（收入、工资、利润总额计算底稿）」⇒ 2+3=5 ✅
    §四（真跑产物）：「（名称逐字对应已提供**1**项；另有**1**项已提供同类资料…）」⇒ 1+1=2 ❌
  ⇒ 同一页两套口径，D11 仍部分存在（§三 侧已被 D13 顺带修好）。

根因：`argumentation` 的 §四 用引擎三态计数 `available_count` / `verify_count`（**元素数**），
      而 §三 用**材料名原子数**（拆复合名、去重）+ 业态剔除后的权威字段 ⇒ 必然对不上。

修法：§四 改用与 §三 同一套算法（`_atoms` 拆复合名去重；确未提供用 `missing_material_names` 权威），
      **不新增任何判定**；`_av/_vf/_mc` 仅在权威字段缺失时回落（保持存量行为）。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "argumentation.py")

OLD = (
    "    _av = int(evidence.get('available_count', 0) or 0)" + NL +
    "    _mc = int(evidence.get('missing_count', 0) or 0)" + NL +
    "    _mm = evidence.get('missing_materials') or []"
)
NEW = (
    "    # ★ 2026-10-04（疑点5 D11 收口）：**§四 与 §三 同一套缺料口径**。" + NL +
    "    #   实测：§三「需要5项＝逐字2＋同类3」自洽，§四 却写「逐字1＋同类1」⇒ 同页两套口径。" + NL +
    "    #   根因：这里用的是引擎三态计数（**元素数**），而 §三 用**材料名原子数**" + NL +
    "    #   （拆复合名、去重）＋业态剔除后的权威字段 ⇒ 必然对不上。" + NL +
    "    #   现改为同源计算；权威字段缺失时**回落**到原计数（存量行为不变）。" + NL +
    "    _seps11 = (\"、\", \"，\", \",\", \"；\", \";\", \"／\", \"/\", \"或者\", \"以及\", \"与\", \"和\", \"及\")" + NL +
    NL +
    "    def _atoms11(_names):" + NL +
    "        _o = []" + NL +
    "        for _x in (_names or []):" + NL +
    "            _n = _x.get(\"name\") if isinstance(_x, dict) else _x" + NL +
    "            for _y in str(_n or \"\").replace(\"、\", \"\\x00\").replace(\"与\", \"\\x00\")" + NL +
    "                    .replace(\"和\", \"\\x00\").replace(\"及\", \"\\x00\").split(\"\\x00\"):" + NL +
    "                _y = _y.strip()" + NL +
    "                if _y and _y not in _o:" + NL +
    "                    _o.append(_y)" + NL +
    "        return _o" + NL +
    NL +
    "    _els11 = evidence.get('elements') or []" + NL +
    "    _mn11 = list(evidence.get('missing_material_names') or [])" + NL +
    "    if _els11 and (_mn11 or any(e.get('status') == '待核' for e in _els11)):" + NL +
    "        _av = len(_atoms11([e for e in _els11 if e.get('status') == '已有']))" + NL +
    "        _vf = len(_atoms11([e for e in _els11 if e.get('status') == '待核']))" + NL +
    "        _kk11 = len(_atoms11(_mn11)) if _mn11 else int(evidence.get('missing_count', 0) or 0)" + NL +
    "    else:" + NL +
    "        _av = int(evidence.get('available_count', 0) or 0)" + NL +
    "        _vf = int(evidence.get('verify_count', 0) or 0)" + NL +
    "        _kk11 = int(evidence.get('missing_count', 0) or 0)" + NL +
    "    _mc = _kk11" + NL +
    "    _mm = evidence.get('missing_materials') or []"
)

raw = io.open(P, "r", encoding="utf-8", newline="").read()
crlf = CRLF in raw
t = raw.replace(CRLF, NL)
if t.count(OLD) != 1:
    print("!! 命中 %d 次 ⇒ 不写盘" % t.count(OLD))
    sys.exit(2)
t = t.replace(OLD, NEW, 1)
# 后面那句 `if _vf:` 用的是 _vf（已同源）⇒ 无需改；`if _mm: 尚缺…` 仍用类别级 _mm，保持。
# 但"还缺N项"要改用同源计数：
io.open(P, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
print("OK 疑点5 D11：§四 已改为与 §三 同源口径")
