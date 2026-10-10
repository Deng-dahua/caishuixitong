# -*- coding: utf-8 -*-
"""疑点5 · D11 收口（第二步·重做）：§三 与 §四 改读**引擎层原子数权威**。

★ 前置条件已就位（本轮前一步 = 方案 A）：业态剔除已下沉到引擎层
  ⇒ `ev["elements"]` 的名字在两层一致 ⇒ 原子数必然一致。

改动（只换取值来源，不改任何判定，字段缺失即回落旧算法）
--------------------------------------------------
§四（`argumentation`）：`_av/_vf/_mc` 优先读
  `available_atom_count` / `verify_atom_count` / `missing_atom_count`。
§三（`enterprise_report`）：`_have_n`、同类计数、缺料计数、`_need_n` 同样优先读这三个字段。
  ★ `missing_atom_count` 已在引擎层定为「**缺失**」口径（与 §三「确未提供」同口径）。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
ER = os.path.join(ROOT, "engine", "enterprise_report.py")
AR = os.path.join(ROOT, "engine", "argumentation.py")


def swap(path, old, new, tag):
    raw = io.open(path, "r", encoding="utf-8", newline="").read()
    crlf = CRLF in raw
    t = raw.replace(CRLF, NL)
    c = t.count(old)
    print("%s 命中 = %d" % (tag, c))
    if c != 1:
        print("!! %s 锚点异常 ⇒ 全不写盘" % tag)
        sys.exit(2)
    t = t.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
    print("OK " + tag)


# ══ §三：计数改读权威 ═════════════════════════════════════════════════
OLD3 = (
    '        _have_n = len(_at_have)' + NL +
    '        _need_n = _have_n + len(_at_verify) + len(_at_lack)' + NL
)
NEW3 = (
    '        # ★ 2026-08-05（疑点5 D11 收口）：**优先读引擎层原子数权威**' + NL +
    '        #   （`evidence_chain._atoms_count()`，与业态剔除同在引擎层完成 ⇒ 与 §四 同源）。' + NL +
    '        #   权威字段缺失时**回落**旧算法（存量行为不变）。' + NL +
    '        _a3 = (ev.get("available_atom_count"), ev.get("verify_atom_count"),' + NL +
    '               ev.get("missing_atom_count"))' + NL +
    '        if None not in _a3:' + NL +
    '            _have_n = int(_a3[0] or 0)' + NL +
    '            _v_n = int(_a3[1] or 0)' + NL +
    '            _k_n = int(_a3[2] or 0)' + NL +
    '        else:' + NL +
    '            _v_n = len(_at_verify)' + NL +
    '            _k_n = len(_at_lack)' + NL +
    '            _have_n = len(_at_have)' + NL +
    '        _need_n = _have_n + _v_n + _k_n' + NL
)
swap(ER, OLD3, NEW3, "§三 计数切权威")

OLD3B = '                len(_at_verify), _brief_atoms(_at_verify))'
NEW3B = '                _v_n, _brief_atoms(_at_verify))'
swap(ER, OLD3B, NEW3B, "§三 同类段用 _v_n")

OLD3C = '% (len(_at_lack), _brief_atoms(_at_lack))'
NEW3C = '% (_k_n, _brief_atoms(_at_lack))'
swap(ER, OLD3C, NEW3C, "§三 缺料段用 _k_n")

# ══ §四：计数改读权威 ═════════════════════════════════════════════════
OLD4 = "    if _els11:" + NL
NEW4 = (
    "    # ★ 2026-08-05（疑点5 D11 收口）：**优先读引擎层原子数权威**（与 §三 同源）。" + NL +
    "    _a4 = (evidence.get('available_atom_count')," + NL +
    "           evidence.get('verify_atom_count')," + NL +
    "           evidence.get('missing_atom_count'))" + NL +
    "    if None not in _a4:" + NL +
    "        _av = int(_a4[0] or 0)" + NL +
    "        _vf = int(_a4[1] or 0)" + NL +
    "        _mc = int(_a4[2] or 0)" + NL +
    "    elif _els11:" + NL
)
swap(AR, OLD4, NEW4, "§四 切权威")
print("[DONE] 疑点5 D11 收口：§三/§四 均读引擎层原子数权威")
