# -*- coding: utf-8 -*-
"""疑点5 · D11 收口：让 **§四 与 §三 同一套缺料口径**（上一版因 `.replace()` 链拆行而语法错，已回退）。

★ 判据已用真跑产物抄录验证：
    §三：「需要5项＝逐字2＋同类3」自洽 ✅
    §四：「逐字已提供1项；另有1项」 ❌ ⇒ D11 仍部分存在
  根因：§四 用引擎三态计数（**元素数**），§三 用**材料名原子数**＋业态剔除后的权威字段。

★ 本版所有方法链**一律单行**（上一版拆行缺括号 ⇒ SyntaxError ⇒ 12 ERROR）。
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

NEW_LINES = [
    "    # ★ 2026-10-04（疑点5 D11 收口）：**§四 与 §三 同一套缺料口径**。",
    "    #   实测：§三「需要5项＝逐字2＋同类3」自洽；§四 却写「逐字1＋同类1」⇒ 同页两套口径。",
    "    #   根因：这里用引擎三态计数（**元素数**），§三 用**材料名原子数**（拆复合名、去重）",
    "    #   ＋业态剔除后的权威字段 ⇒ 必然对不上。权威字段缺失时**回落**到原计数（存量行为不变）。",
    "    _SEPS11 = (\"、\", \"，\", \",\", \"；\", \";\", \"／\", \"/\", \"或者\", \"以及\", \"与\", \"和\", \"及\")",
    "",
    "    def _atoms11(_names):",
    "        _o = []",
    "        for _x in (_names or []):",
    "            _n = _x.get(\"name\") if isinstance(_x, dict) else _x",
    "            _s = str(_n or \"\")",
    "            for _p in _SEPS11:",
    "                _s = _s.replace(_p, \"\\x00\")",
    "            for _y in _s.split(\"\\x00\"):",
    "                _y = _y.strip()",
    "                if _y and _y not in _o:",
    "                    _o.append(_y)",
    "        return _o",
    "",
    "    _els11 = evidence.get('elements') or []",
    "    _mn11 = list(evidence.get('missing_material_names') or [])",
    "    if _els11:",
    "        _av = len(_atoms11([e for e in _els11 if e.get('status') == '已有']))",
    "        _vf = len(_atoms11([e for e in _els11 if e.get('status') == '待核']))",
    "        if _mn11:",
    "            _mc = len(_atoms11(_mn11))",
    "        else:",
    "            _mc = int(evidence.get('missing_count', 0) or 0)",
    "    else:",
    "        _av = int(evidence.get('available_count', 0) or 0)",
    "        _vf = int(evidence.get('verify_count', 0) or 0)",
    "        _mc = int(evidence.get('missing_count', 0) or 0)",
    "    _mm = evidence.get('missing_materials') or []",
]
NEW = NL.join(NEW_LINES) + NL

raw = io.open(P, "r", encoding="utf-8", newline="").read()
crlf = CRLF in raw
t = raw.replace(CRLF, NL)
if t.count(OLD) != 1:
    print("!! 命中 %d 次 ⇒ 不写盘" % t.count(OLD))
    sys.exit(2)
t = t.replace(OLD, NEW, 1)
# 原后面还有一句 `if _vf:` 用旧 _vf（已在上方赋值）⇒ 不动
io.open(P, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
print("OK 疑点5 D11：§四 已改为与 §三 同源口径（方法链全单行）")
