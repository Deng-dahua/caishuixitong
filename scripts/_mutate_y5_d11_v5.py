# -*- coding: utf-8 -*-
"""疑点5 · D11 第二步：§三 与 §四 都改读**引擎层原子数权威**（缺失时回落旧算法）。

权威字段（第一步已就位）：`available_atom_count` / `verify_atom_count` / `missing_atom_count`
—— 由 `evidence_chain._atoms_count()` 产出，与 §三 **同一算法、同一业态剔除权威**。

本步只改**文案里的计数取值**，不改任何判定：
  §三（`enterprise_report`）：`_have_n` / 同类计数 / 缺料计数 / `_need_n`
  §四（`argumentation`）：`_av` / `_vf` / `_mc`
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


# ══ §四：_av/_vf/_mc 优先读权威 ══════════════════════════════════════
OLD4 = (
    "    _els11 = evidence.get('elements') or []" + NL +
    "    _mn11 = list(evidence.get('missing_material_names') or [])" + NL +
    "    if _els11:" + NL
)
NEW4 = (
    "    # ★ 2026-10-05（疑点5 D11 第二步）：**优先读引擎层原子数权威**" + NL +
    "    #   （`evidence_chain._atoms_count()`，与 §三 同算法、同业态剔除）⇒ 两页不可能不一致。" + NL +
    "    _a4 = (evidence.get('available_atom_count')," + NL +
    "           evidence.get('verify_atom_count')," + NL +
    "           evidence.get('missing_atom_count'))" + NL +
    "    _els11 = evidence.get('elements') or []" + NL +
    "    _mn11 = list(evidence.get('missing_material_names') or [])" + NL +
    "    if None not in _a4:" + NL +
    "        _av = int(_a4[0] or 0)" + NL +
    "        _vf = int(_a4[1] or 0)" + NL +
    "        _mc = int(_a4[2] or 0)" + NL +
    "    elif _els11:" + NL
)
swap(AR, OLD4, NEW4, "§四 切权威")

# ══ §三：_have_n/_need_n 与两处文案计数切权威 ═════════════════════════
OLD3 = (
    "        _at_have = _atoms_of(have)" + NL +
    "        _at_verify = _atoms_of(verify)" + NL +
    "        _at_lack = _atoms_of(_lack_ok)" + NL +
    "        _have_n = len(_at_have)" + NL +
    "        _need_n = _have_n + len(_at_verify) + len(_at_lack)" + NL
)
NEW3 = (
    "        _at_have = _atoms_of(have)" + NL +
    "        _at_verify = _atoms_of(verify)" + NL +
    "        _at_lack = _atoms_of(_lack_ok)" + NL +
    "        # ★ 2026-10-05（疑点5 D11 第二步）：**优先读引擎层原子数权威**（§四 同源）" + NL +
    "        _a3 = (ev.get(\"available_atom_count\"), ev.get(\"verify_atom_count\")," + NL +
    "               ev.get(\"missing_atom_count\"))" + NL +
    "        if None not in _a3:" + NL +
    "            _have_n = int(_a3[0] or 0)" + NL +
    "            _v_n = int(_a3[1] or 0)" + NL +
    "            _k_n = int(_a3[2] or 0)" + NL +
    "        else:" + NL +
    "            _v_n = len(_at_verify)" + NL +
    "            _k_n = len(_at_lack)" + NL +
    "            _have_n = len(_at_have)" + NL +
    "        _need_n = _have_n + _v_n + _k_n" + NL
)
swap(ER, OLD3, NEW3, "§三 切权威")

# 同类段与缺料段的**文案计数**改用 _v_n / _k_n
OLD3B = ('            _p3 += "，其中%d项已提供同类资料（%s）、但与本项要求的范围未逐字对应，须确认是否覆盖" % (\n'
         '                len(_at_verify), _brief_atoms(_at_verify))')
NEW3B = ('            _p3 += "，其中%d项已提供同类资料（%s）、但与本项要求的范围未逐字对应，须确认是否覆盖" % (\n'
         '                _v_n, _brief_atoms(_at_verify))')
swap(ER, OLD3B, NEW3B, "§三 同类段用 _v_n")

OLD3C = '            _p3 += "；确未提供的有%d项（%s）" % (len(_at_lack), _brief_atoms(_at_lack))'
NEW3C = '            _p3 += "；确未提供的有%d项（%s）" % (_k_n, _brief_atoms(_at_lack))'
swap(ER, OLD3C, NEW3C, "§三 缺料段用 _k_n")

print("[DONE] 疑点5 D11 第二步完成：§三/§4 均读引擎层原子数权威")
