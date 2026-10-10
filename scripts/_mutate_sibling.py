# -*- coding: utf-8 -*-
"""疑点2 最后一项：住房公积金 ≠ 社保 —— 按「选项 B：同族不同物」收口。

问题现状
--------
`CATEGORY_ALIASES["社保明细"]` 里登记了「住房公积金缴存明细/公积金明细/公积金汇缴书」等，
于是 `_covered_by("住房公积金缴存明细", ["社保明细"])` 走 `form == token` 判**「已有」**
⇒ "提供了社保明细"被当成"已有公积金缴存明细"。两者是**两套制度、两张表**。

为什么选 B（不动类别体系）
--------------------------
- 归类/业态剔除/计数都依赖 `CATEGORY_ALIASES` 与 15 类不变量；
  若把公积金别名摘掉，`category_strict` 判不出 ⇒ RL-SPT-010 的要件数据源
  变成"声明了但永远拿不到"⇒ 触发既有闸门 ERROR（实测过：应付账款明细那次）。
- B 方案：**归类照旧**（仍算社保口径，便于剔除与计数），
  只在**覆盖判定**上加第三种关系 —— **同族不同物** ⇒ 不判「已有」，改判「待核」并说明。

唯一权威：`material_names._SIBLING_FAMILIES`（同族表）+ `sibling_conflict(a, b)`。
新增一族只需加一行数据，不改逻辑分支。

★ 文案不含 ASCII 引号。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)
CRLF = chr(13) + chr(10)


def swap(path, pairs):
    p = os.path.join(ROOT, path)
    raw = io.open(p, "r", encoding="utf-8", newline="").read()
    crlf = CRLF in raw
    t = raw.replace(CRLF, NL)
    for _i, _p in enumerate(pairs):
        tag, old, new = (_p if len(_p) == 3 else (str(_i + 1), _p[0], _p[1]))
        c = t.count(old)
        if c != 1:
            print("!! %s 命中 %d 次（应为 1）" % (tag, c))
            sys.exit(2)
        t = t.replace(old, new, 1)
    io.open(p, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
    print("OK %s (%d处)" % (path, len(pairs)))


MN = "engine/material_names.py"
swap(MN, [
    # ① 同族表 + 判据（放在 CATEGORIES 之后）
    ('#: 类别规范名（供外部判断"这个名字是不是类别名"）\nCATEGORIES: List[str] = [c for c, _ in CATEGORY_KEYWORDS]',
     '#: ★★ 2026-10-04（疑点2 收尾，选项 B）**同族不同物**关系表（单一权威）。\n'
     '#:   同一族内的成员**归类相同**（便于业态剔除与计数），但**不是同一份材料**，\n'
     '#:   因此**覆盖判定不得为「已有」**，须判「待核」并说明差在哪。\n'
     '#:   例：社保（养老/医疗/失业/工伤/生育）与住房公积金是**两套制度、两张表**——\n'
     '#:   "已提供社保明细"不能证明"已有公积金缴存明细"。\n'
     '#:   ★ 为什么不摘掉别名：那会让公积金判不出类别 ⇒ 要件数据源恒 not_checked ⇒ 触发既有闸门。\n'
     '#:     故**归类保留、只改覆盖判定**。新增同族只需加一行数据。\n'
     '_SIBLING_FAMILIES: List[Dict[str, Any]] = [\n'
     '    {\n'
     '        "family": "社保与公积金",\n'
     '        "note": "社保与住房公积金分属两套制度、逐人逐月各出一张表，不是同一份材料",\n'
     '        "members": ["社保明细", "社会保险参保明细", "参保缴费明细", "参保缴费记录",\n'
     '                     "社保清单", "社保缴费明细",\n'
     '                     "住房公积金缴存明细", "住房公积金明细", "公积金缴存明细",\n'
     '                     "公积金明细", "公积金汇缴书", "住房公积金汇缴书"],\n'
     '    },\n'
     ']\n'
     '\n'
     '\n'
     'def sibling_conflict(a: Any, b: Any) -> bool:\n'
     '    """`a` 与 `b` 是否**同族但不同物**（同一族、且不是同一个名字）。\n'
     '\n'
     '    覆盖判定用它把"同族"从「已有」降为「待核」；**归类/剔除/计数不受影响**。\n'
     '    """\n'
     '    _x = str(a or "").strip()\n'
     '    _y = str(b or "").strip()\n'
     '    if not _x or not _y or _x == _y:\n'
     '        return False\n'
     '    for _fam in _SIBLING_FAMILIES:\n'
     '        _ms = [str(m) for m in (_fam.get("members") or [])]\n'
     '        _in_x = any(_x == _m or _m in _x for _m in _ms)\n'
     '        _in_y = any(_y == _m or _m in _y for _m in _ms)\n'
     '        if _in_x and _in_y:\n'
     '            return True\n'
     '    return False\n'
     '\n'
     '\n'
     'def sibling_note(a: Any, b: Any) -> str:\n'
     '    """同族不同物时的说明（供证据依据原文使用）。"""\n'
     '    for _fam in _SIBLING_FAMILIES:\n'
     '        _ms = [str(m) for m in (_fam.get("members") or [])]\n'
     '        _x = str(a or "")\n'
     '        if any(_x == _m or _m in _x for _m in _ms):\n'
     '            return "%s：%s" % (_fam.get("family"), _fam.get("note"))\n'
     '    return ""\n'
     '\n'
     '\n'
     '#: 类别规范名（供外部判断"这个名字是不是类别名"）\nCATEGORIES: List[str] = [c for c, _ in CATEGORY_KEYWORDS]'),
])

EC = "engine/evidence_chain.py"
swap(EC, [
    # ② 逐字/别名覆盖时：同族不同物不构成覆盖
    ('            if form == token or token in form:\n'
     '                return {"need": token, "material": str(a), "form": form,\n'
     '                        "exact": form == token}',
     '            # ★ 2026-10-04（选项 B）：**同族不同物不构成覆盖** ——\n'
     '            #   社保与公积金同族（归类相同、便于剔除与计数），但不是同一份材料，\n'
     '            #   不得判「已有」。唯一权威 `material_names.sibling_conflict`。\n'
     '            try:\n'
     '                from material_names import sibling_conflict as _sib\n'
     '                if _sib(token, form):\n'
     '                    continue\n'
     '            except Exception:  # noqa: BLE001\n'
     '                pass\n'
     '            if form == token or token in form:\n'
     '                return {"need": token, "material": str(a), "form": form,\n'
     '                        "exact": form == token}'),
    # ③ 类别层：同族不同物 ⇒ 判待核
    ('            if all(any(set(_alt) <= _have_cats for _alt in _grp) for _grp in _groups):',
     '            # ★ 2026-10-04（选项 B）：类别命中但**同族不同物** ⇒ 不得判「已有」。\n'
     '            _sib_hit = False\n'
     '            try:\n'
     '                from material_names import sibling_conflict as _sib2\n'
     '                for _a2 in _have:\n'
     '                    if _sib2(evidence_name, _a2):\n'
     '                        _sib_hit = True\n'
     '                        break\n'
     '            except Exception:  # noqa: BLE001\n'
     '                _sib_hit = False\n'
     '            if _sib_hit:\n'
     '                try:\n'
     '                    from material_names import sibling_note as _sibn\n'
     '                    _sib_txt = _sibn(evidence_name, "、".join(_have[:2])) or "同族但不是同一份材料"\n'
     '                except Exception:  # noqa: BLE001\n'
     '                    _sib_txt = "同族但不是同一份材料"\n'
     '                return {"status": "待核", "matched": _have, "matched_detail": [],\n'
     '                        "unmet": [evidence_name], "related": [],\n'
     '                        "basis": ("本项要求「%s」；本轮已提供的是「%s"，二者%s，"\n'
     '                                  "须补充该项本身的具体材料后方可核对。"\n'
     '                                  % (evidence_name, "、".join(_have[:3]), _sib_txt)),\n'
     '                        "sibling_conflict": True}\n'
     '            if all(any(set(_alt) <= _have_cats for _alt in _grp) for _grp in _groups):'),
])
print("[DONE] 选项 B 已落地")
